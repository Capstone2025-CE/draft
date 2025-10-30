import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:camera/camera.dart';
import 'package:http/http.dart' as http; // <-- ADD THIS
import 'dart:io'; // <-- ADD THIS

// IMPORTANT: Replace this with your PC's IP address from Step 1
const String yourServerIp = "YOUR_PC_IP_ADDRESS";
final String apiUrl = "http://$yourServerIp:8000/recognize-frame";

void main() async {
  // Ensure widgets are initialized
  WidgetsFlutterBinding.ensureInitialized();

  // Get available cameras
  final cameras = await availableCameras();
  final firstCamera = cameras.first;

  runApp(MyApp(camera: firstCamera));
}

class MyApp extends StatelessWidget {
  final CameraDescription camera;
  const MyApp({super.key, required this.camera});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Demo',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
      ),
      // Pass the camera to MyHomePage
      home: MyHomePage(title: 'Flutter Demo Home Page', camera: camera),
    );
  }
}

class MyHomePage extends StatelessWidget {
  final String title;
  final CameraDescription camera; // <-- Pass camera here

  const MyHomePage({super.key, required this.title, required this.camera});

  Future<void> _openCamera(BuildContext context) async {
    var status = await Permission.camera.request();
    if (status.isGranted) {
      Navigator.push(
        context,
        MaterialPageRoute(
          // Pass the camera to the preview page
          builder: (context) => CameraPreviewPage(camera: camera),
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
                "Open Camera",
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

class CameraPreviewPage extends StatefulWidget {
  final CameraDescription camera;
  const CameraPreviewPage({super.key, required this.camera});

  @override
  State<CameraPreviewPage> createState() => _CameraPreviewPageState();
}

class _CameraPreviewPageState extends State<CameraPreviewPage> {
  late CameraController _controller;
  late Future<void> _initializeControllerFuture;
  bool _isProcessing = false; // To prevent multiple requests

  @override
  void initState() {
    super.initState();
    _controller = CameraController(widget.camera, ResolutionPreset.high);
    _initializeControllerFuture = _controller.initialize();
  }

  // --- NEW FUNCTION TO SEND IMAGE TO SERVER ---
  Future<void> _recognizeFace(XFile picture) async {
    if (_isProcessing) return;

    setState(() {
      _isProcessing = true;
    });

    // Show a loading dialog
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => const Center(child: CircularProgressIndicator()),
    );

    try {
      // Create a multipart request
      var request = http.MultipartRequest('POST', Uri.parse(apiUrl));

      // Add the file to the request
      request.files.add(
        await http.MultipartFile.fromPath(
          'frame', // This MUST match the argument name in FastAPI: `frame: UploadFile`
          picture.path,
        ),
      );

      // Send the request
      final streamedResponse = await request.send();

      // Get the response
      final response = await http.Response.fromStream(streamedResponse);

      // Close the loading dialog
      Navigator.of(context).pop();

      if (response.statusCode == 200) {
        // The server returns the name as plain text (e.g., "John Doe" or "Unknown")
        String recognizedName = response.body;

        // Show result in an alert dialog
        showDialog(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text("Recognition Result"),
            content: Text("Server recognized: $recognizedName"),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text("OK"),
              ),
            ],
          ),
        );
      } else {
        // Show error
        _showErrorDialog("Server Error: ${response.statusCode}\n${response.body}");
      }
    } catch (e) {
      // Close loading dialog
      Navigator.of(context).pop();
      // Show network or other error
      _showErrorDialog("Error sending image: $e");
    }

    setState(() {
      _isProcessing = false;
    });
  }

  void _showErrorDialog(String message) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text("Error"),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text("OK"),
          ),
        ],
      ),
    );
  }
  // --- END OF NEW FUNCTION ---

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Camera")),
      body: FutureBuilder<void>(
        future: _initializeControllerFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.done) {
            return CameraPreview(_controller);
          } else {
            return const Center(child: CircularProgressIndicator());
          }
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          // MODIFIED: Send to server instead of just saving
          if (_isProcessing) return; // Don't take picture if already processing

          try {
            await _initializeControllerFuture;
            final picture = await _controller.takePicture();

            // Call our new function
            await _recognizeFace(picture);

          } catch (e) {
            print("Error taking picture: $e");
            _showErrorDialog("Error taking picture: $e");
          }
        },
        child: _isProcessing
            ? const CircularProgressIndicator(color: Colors.white)
            : const Icon(Icons.camera_alt),
      ),
    );
  }
}

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