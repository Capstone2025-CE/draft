import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:camera/camera.dart';
import 'package:http/http.dart' as http;
import 'package:flutter/cupertino.dart';
import 'package:image_picker/image_picker.dart'; // For registration

class MyHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..badCertificateCallback =
          (X509Certificate cert, String host, int port) => true;
  }
}

// --- Your ngrok URL ---
const String serverIp = "https://intertuberal-niki-nonexhibitionistic.ngrok-free.dev"; // UPDATE THIS
final String recognizeApiUrl = "$serverIp/recognize-frame";
final String registerApiUrl = "$serverIp/student/register";

List<CameraDescription> cameras = [];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  HttpOverrides.global = MyHttpOverrides();
  try {
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
      initialRoute: '/',
      routes: {
        '/': (context) => MyHomePage(title: 'Flutter Demo Home Page', cameras: cameras),
        '/student_dashboard': (context) => const StudentDashboard(),
        '/register_face': (context) => const RegisterFacePage(),
      },
    );
  }
}

class MyHomePage extends StatelessWidget {
  final String title;
  final List<CameraDescription> cameras;

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
          builder: (context) => CameraStreamPage(cameras: cameras),
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Camera permission denied")),
      );
    }
  }

  void _openStudentDashboard(BuildContext context) {
    Navigator.pushNamed(context, '/student_dashboard');
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
                "Start Recognition",
                style: TextStyle(fontSize: 20, color: Colors.white),
              ),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.green,
                minimumSize: const Size(200, 60),
              ),
              onPressed: () => _openStudentDashboard(context),
              child: const Text(
                "Student Dashboard",
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
// Recognition Page (Multi-face)
// ======================================================
class CameraStreamPage extends StatefulWidget {
  final List<CameraDescription> cameras;
  const CameraStreamPage({super.key, required this.cameras});

  @override
  State<CameraStreamPage> createState() => _CameraStreamPageState();
}

class _CameraStreamPageState extends State<CameraStreamPage> {
  CameraController? _controller;
  Future<void>? _initializeControllerFuture;

  Timer? _frameTimer;
  bool _isProcessing = false;
  List<Map<String, dynamic>> _recognizedFaces = [];
  int _selectedCameraIndex = 0;

  @override
  void initState() {
    super.initState();
    _initCamera(widget.cameras[_selectedCameraIndex]);
  }

  void _initCamera(CameraDescription cameraDescription) {
    _frameTimer?.cancel();
    _controller = CameraController(
      cameraDescription,
      ResolutionPreset.medium,
      enableAudio: false,
    );
    _initializeControllerFuture = _controller!.initialize().then((_) {
      if (!mounted) return;
      _startFrameStream();
    });
    if (this.mounted) {
      setState(() {});
    }
  }

  Future<void> _flipCamera() async {
    _frameTimer?.cancel();
    _selectedCameraIndex = (_selectedCameraIndex + 1) % widget.cameras.length;
    if (_controller != null) {
      await _controller!.dispose();
    }
    _initCamera(widget.cameras[_selectedCameraIndex]);
  }

  void _startFrameStream() {
    if (_controller == null || !_controller!.value.isInitialized) return;
    _frameTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      _sendCurrentFrame();
    });
  }

  Future<void> _sendCurrentFrame() async {
    if (_isProcessing) return;
    if (_controller == null || !_controller!.value.isInitialized) return;

    setState(() { _isProcessing = true; });

    try {
      final picture = await _controller!.takePicture();
      var request = http.MultipartRequest('POST', Uri.parse(recognizeApiUrl));
      request.files.add(
        await http.MultipartFile.fromPath('frame', picture.path),
      );

      final streamedResponse = await request.send().timeout(const Duration(seconds: 5));
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        setState(() {
          _recognizedFaces = data.cast<Map<String, dynamic>>();
        });
      } else {
        setState(() {
          _recognizedFaces = [{"name": "Server Error", "sap_id": "HTTP ${response.statusCode}"}];
        });
      }
    } catch (e) {
      // Handle known errors
      print("Error sending frame: $e");
      if (e is TimeoutException) {
        _recognizedFaces = [{"name": "Connection Timeout", "sap_id": "Firewall?"}];
      } else if (e is SocketException) {
        _recognizedFaces = [{"name": "Broken Pipe", "sap_id": "Server Crash?"}];
      } else {
        _recognizedFaces = [{"name": "Client Error", "sap_id": "Unknown"}];
      }
      setState(() {}); // Update UI with error
    }

    setState(() { _isProcessing = false; });
  }

  @override
  void dispose() {
    _frameTimer?.cancel();
    _controller?.dispose();
    super.dispose();
  }

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
      backgroundColor: Colors.black,
      body: FutureBuilder<void>(
        future: _initializeControllerFuture,
        builder: (context, snapshot) {
          if (_controller == null || snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }

          return Stack(
            fit: StackFit.expand,
            children: [
              Center(
                child: AspectRatio(
                  aspectRatio: 9 / 16, // Force 9:16
                  child: CameraPreview(_controller!),
                ),
              ),
              Positioned(
                bottom: 0,
                left: 0,
                right: 0,
                child: Container(
                  padding: const EdgeInsets.all(8.0),
                  color: Colors.black.withOpacity(0.6),
                  constraints: BoxConstraints(
                    maxHeight: MediaQuery.of(context).size.height * 0.25,
                  ),
                  child: _buildRecognizedFacesList(),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildRecognizedFacesList() {
    if (_recognizedFaces.isEmpty) {
      return const Center(
        child: Text(
          "No faces detected",
          style: TextStyle(color: Colors.white, fontSize: 16),
        ),
      );
    }

    return ListView.builder(
      itemCount: _recognizedFaces.length,
      itemBuilder: (context, index) {
        final face = _recognizedFaces[index];
        final name = face['name'];
        final sapId = face['sap_id'];
        final color = name == 'Unknown' ? Colors.red : Colors.green;

        return Text(
          "Name: $name, SAP: $sapId",
          textAlign: TextAlign.center,
          style: TextStyle(
            color: color,
            fontSize: 16.0,
            fontWeight: FontWeight.bold,
          ),
        );
      },
    );
  }
}

// ======================================================
// --- NEW: Student Dashboard Page ---
// ======================================================
class StudentDashboard extends StatelessWidget {
  const StudentDashboard({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Student Dashboard")),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.purple,
                minimumSize: const Size(200, 60),
              ),
              onPressed: () {
                Navigator.pushNamed(context, '/register_face');
              },
              child: const Text(
                "Register My Face",
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
// --- NEW: Face Registration Page (1 Photo) ---
// ======================================================
class RegisterFacePage extends StatefulWidget {
  const RegisterFacePage({super.key});

  @override
  State<RegisterFacePage> createState() => _RegisterFacePageState();
}

class _RegisterFacePageState extends State<RegisterFacePage> {
  final _sapIdController = TextEditingController();
  final _nameController = TextEditingController();
  final _passwordController = TextEditingController();
  final ImagePicker _picker = ImagePicker();

  XFile? _photo; // Only one photo
  bool _isRegistering = false;

  Future<void> _pickImage() async {
    final XFile? image = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 50,
      preferredCameraDevice: CameraDevice.front,
    );
    setState(() {
      _photo = image;
    });
  }

  Future<void> _register() async {
    if (_photo == null) {
      _showErrorDialog("Please take a photo.");
      return;
    }
    if (_sapIdController.text.isEmpty || _nameController.text.isEmpty || _passwordController.text.isEmpty) {
      _showErrorDialog("Please fill in all details.");
      return;
    }

    setState(() { _isRegistering = true; });

    try {
      var request = http.MultipartRequest('POST', Uri.parse(registerApiUrl));

      request.fields['sap_id'] = _sapIdController.text;
      request.fields['name'] = _nameController.text;
      request.fields['password'] = _passwordController.text;

      // Changed to 'file' to match backend
      request.files.add(await http.MultipartFile.fromPath('file', _photo!.path));

      final response = await request.send().timeout(const Duration(seconds: 15));

      if (response.statusCode == 201) { // 201 means "Created"
        Navigator.pop(context); // Go back to dashboard
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Registration Successful!"), backgroundColor: Colors.green),
        );
      } else {
        final respStr = await response.stream.bytesToString();
        final data = json.decode(respStr);
        // Use 'detail' from FastAPI's HTTPException
        _showErrorDialog("Registration Failed: ${data['detail']}");
      }
    } on TimeoutException catch (_) {
      _showErrorDialog("Registration timed out. Check your connection.");
    } catch (e) {
      _showErrorDialog("An error occurred: $e");
    }

    setState(() { _isRegistering = false; });
  }

  void _showErrorDialog(String message) {
    if (!mounted) return;
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Register Face")),
      body: _isRegistering
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            TextField(
              controller: _sapIdController,
              decoration: const InputDecoration(labelText: 'SAP ID'),
              keyboardType: TextInputType.number,
            ),
            TextField(
              controller: _nameController,
              decoration: const InputDecoration(labelText: 'Full Name'),
            ),
            TextField(
              controller: _passwordController,
              decoration: const InputDecoration(labelText: 'Password'),
              obscureText: true,
            ),
            const SizedBox(height: 20),

            // --- NEW: 1 Photo Picker ---
            Card(
              child: ListTile(
                leading: CircleAvatar(
                  child: _photo == null
                      ? const Icon(Icons.person)
                      : ClipOval(child: Image.file(File(_photo!.path), fit: BoxFit.cover, width: 40, height: 40)),
                ),
                title: Text(_photo == null ? 'Take Photo' : 'Photo Saved'),
                trailing: Icon(_photo == null ? Icons.camera_alt : Icons.check_circle, color: _photo == null ? null : Colors.green),
                onTap: _pickImage,
              ),
            ),

            const SizedBox(height: 20),
            ElevatedButton(
              style: ElevatedButton.styleFrom(minimumSize: const Size(double.infinity, 50)),
              onPressed: _register,
              child: const Text('Register'),
            ),
          ],
        ),
      ),
    );
  }
}