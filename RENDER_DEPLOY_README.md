# VoiceGuard KZ (SpoofCeleb) — Render deploy

1. Upload the CONTENTS of this zip to the GitHub repository root. You should see Dockerfile, requirements.txt, and app/ in the repository root.
2. Render: New -> Web Service -> connect repo -> Runtime: Docker. Root Directory: leave empty (unless you put the files in a subfolder).
3. Dockerfile Path: ./Dockerfile. Docker CMD already starts the server on the PORT environment variable. Do not set Start Command to start.bat.
4. Deploy and check https://YOUR-SERVICE.onrender.com/api/status.
5. The model checkpoint models/spoofceleb_cnn.pt is NOT included. Analysis needs a legitimately trained SpoofCeleb MelCNN checkpoint (see README.md). The website must not report fake predictions without a checkpoint.
6. Note that PyTorch image may exceed free-tier resources. Use a service with sufficient RAM/disk when required.
