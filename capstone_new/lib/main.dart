import 'dart:async'; // For the Timer
import 'dart:convert'; // For json.decode
import 'dart:io'; // For HttpOverrides
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:camera/camera.dart';
import 'package:http/http.dart' as http;

// --- FIX 1: HTTP OVERRIDE FOR SSL (Handshake Error) ---
class MyHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..badCertificateCallback =
          (X509Certificate cert, String host, int port) => true;
  }
}
// -----------------------------------------------------

// --- Your ngrok URL ---
const String serverIp = "https://intertuberal-niki-nonexhibitionistic.ngrok-free.dev";
final String apiUrl = "$serverIp/recognize-frame";

List<CameraDescription> cameras = []; // Make cameras list global

Future<void> main() async {
  // Ensure widgets are initialized
  WidgetsFlutterBinding.ensureInitialized();

  // --- FIX 1 (Continued): Apply the override ---
  HttpOverrides.global = MyHttpOverrides();

  try {
    // Get available cameras
    cameras = await availableCameras();
  } on CameraException catch (e) {
    print("Error fetching cameras: $e");
  }

  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Demo',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
      ),
      // Pass the camera list to MyHomePage
      home: MyHomePage(title: 'Flutter Demo Home Page', cameras: cameras),
    );
  }
}

class MyHomePage extends StatelessWidget {
  final String title;
  final List<CameraDescription> cameras; // <-- Pass camera list

  const MyHomePage({super.key, required this.title, required this.cameras});

  Future<void> _openCamera(BuildContext context) async {
    var status = await Permission.camera.request();
    if (status.isGranted) {
      if (cameras.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("No cameras found on device")),
        );
        return;
      }
      Navigator.push(
        context,
        MaterialPageRoute(
          // Pass the camera list to the preview page
          builder: (context) => CameraStreamPage(cameras: cameras),
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Camera permission denied")),
      );
    }
  }

  void _openForm(BuildContext context) {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (context) => const UserFormPage()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        title: Text(title),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.blue,
                minimumSize: const Size(200, 60),
              ),
              onPressed: () => _openCamera(context),
              child: const Text(
                "Start Recognition", // Changed text
                style: TextStyle(fontSize: 20, color: Colors.white),
              ),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.blue,
                minimumSize: const Size(200, 60),
              ),
              onPressed: () => _openForm(context),
              child: const Text(
                "Open User Form",
                style: TextStyle(fontSize: 20, color: Colors.white),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ======================================================
// RENAMED and HEAVILY MODIFIED this page
// ======================================================
class CameraStreamPage extends StatefulWidget {
  final List<CameraDescription> cameras;
  const CameraStreamPage({super.key, required this.cameras});

  @override
  State<CameraStreamPage> createState() => _CameraStreamPageState();
}

class _CameraStreamPageState extends State<CameraStreamPage> {
  // --- FIX: Make controller and future nullable ---
  CameraController? _controller;
  Future<void>? _initializeControllerFuture;
  // ------------------------------------------------

  Timer? _frameTimer;
  bool _isProcessing = false;
  String _displayName = "Initializing...";
  String _displaySapId = "N/A";
  int _selectedCameraIndex = 0; // 0 for back, 1 for front

  @override
  void initState() {
    super.initState();
    // Start with the back camera (index 0)
    _initCamera(widget.cameras[_selectedCameraIndex]);
  }

  // --- FIX: This function is now synchronous and assigns the future immediately ---
  void _initCamera(CameraDescription cameraDescription) {

    // If a controller already exists, cancel its timer
    _frameTimer?.cancel();

    // Create new controller
    _controller = CameraController(
      cameraDescription,
      ResolutionPreset.medium,
      enableAudio: false,
    );

    // Assign the future SYNCHRONOUSLY
    _initializeControllerFuture = _controller!.initialize().then((_) {
      // This block runs AFTER the future is complete
      if (!mounted) return;
      // Now we start the stream
      _startFrameStream();
    });

    // Update the UI to show the new FutureBuilder (or loading state)
    if (this.mounted) {
      setState(() {});
    }
  }

  // --- FIX: This function now properly disposes the old controller ---
  Future<void> _flipCamera() async {
    // Stop the timer
    _frameTimer?.cancel();

    // Toggle camera index
    _selectedCameraIndex = (_selectedCameraIndex + 1) % widget.cameras.length;

    // Dispose old controller *if it exists*
    if (_controller != null) {
      await _controller!.dispose();
    }

    // Re-initialize with the new camera
    // This will set the new _initializeControllerFuture and restart the stream
    _initCamera(widget.cameras[_selectedCameraIndex]);
  }

  // --- This function is correct ---
  void _startFrameStream() {
    // Make sure controller is initialized before starting timer
    if (_controller == null || !_controller!.value.isInitialized) {
      return;
    }
    _frameTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      _sendCurrentFrame();
    });
  }

  // --- This function is correct ---
  Future<void> _sendCurrentFrame() async {
    if (_isProcessing) return;
    if (_controller == null || !_controller!.value.isInitialized) {
      return; // Safety check
    }

    setState(() {
      _isProcessing = true;
    });

    try {
      final picture = await _controller!.takePicture();

      var request = http.MultipartRequest('POST', Uri.parse(apiUrl));
      request.files.add(
        await http.MultipartFile.fromPath('frame', picture.path),
      );

      final streamedResponse = await request.send();
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        setState(() {
          _displayName = data['name'];
          _displaySapId = data['sap_id'];
        });
      } else {
        setState(() {
          _displayName = "Server Error";
          _displaySapId = "${response.statusCode}";
        });
      }
    } catch (e) {
      print("Error sending frame: $e");
      setState(() {
        _displayName = "Client Error";
        _displaySapId = "N/A";
      });
    }

    setState(() {
      _isProcessing = false;
    });
  }

  @override
  void dispose() {
    _frameTimer?.cancel();
    _controller?.dispose(); // Use ?. to safely dispose
    super.dispose();
  }

  // In _CameraStreamPageState class, inside main.dart

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Live Recognition"),
        actions: [
          IconButton(
            icon: const Icon(Icons.flip_camera_ios_outlined),
            onPressed: _flipCamera,
          ),
        ],
      ),
      // --- FIX: Set background color for letterboxing ---
      backgroundColor: Colors.black,
      body: FutureBuilder<void>(
        future: _initializeControllerFuture,
        builder: (context, snapshot) {
          if (_controller == null ||
              snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }

          // --- FIX: Force the 9:16 Aspect Ratio ---
          return Stack(
            fit: StackFit.expand,
            children: [
              // Center the camera preview
              Center(
                child: AspectRatio(
                  aspectRatio: 3 / 4, // Your desired ratio
                  child: CameraPreview(_controller!),
                ),
              ),
              // --- This overlay is unchanged ---
              Positioned(
                bottom: 0,
                left: 0,
                right: 0,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      vertical: 12.0, horizontal: 8.0),
                  color: Colors.black.withOpacity(0.6),
                  child: Text(
                    "Name: $_displayName\nSAP ID: $_displaySapId",
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18.0,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
// ======================================================

class UserFormPage extends StatelessWidget {
  const UserFormPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("User Form")),
      body: const Center(
        child: Text("Form will go here", style: TextStyle(fontSize: 22)),
      ),
    );
  }
}