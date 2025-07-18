# ---------------------------------------------------------------------------
#  lens_uploader.py — Google Lens image upload via Local HTML Bridge
# ---------------------------------------------------------------------------
#
#  Strategy:
#    Instead of uploading via Python `requests` (which is slow and causes
#    session mismatch errors in Chrome), we generate a temporary local HTML
#    file containing the image as Base64. When opened in the user's browser,
#    it uses Javascript's DataTransfer API to natively construct a File object,
#    attach it to a hidden form, and POST directly to Google Lens.
#
#    This guarantees the upload uses the browser's native cookies/session
#    and eliminates all 403 or "not associated with your account" errors.
# ---------------------------------------------------------------------------

import os
import time
import base64
import tempfile
import webbrowser
import threading


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>Searching with Google Lens...</title>
    <style>
        body {
            background-color: #202124;
            color: white;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .loader {
            border: 4px solid #3c4043;
            border-top: 4px solid #8ab4f8;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="loader"></div>
    <h2>Opening Google Lens...</h2>

    <!-- Hidden form that submits to Google Lens -->
    <form id="lensForm" action="https://lens.google.com/upload?ep=ccm&s=&st=" method="POST" enctype="multipart/form-data" style="display: none;">
        <input type="file" name="encoded_image" id="fileInput" />
    </form>

    <script>
        const b64 = "{base64_data}";

        async function submitToLens() {
            try {
                // 1. Convert base64 to Blob
                const res = await fetch("data:image/jpeg;base64," + b64);
                const blob = await res.blob();
                
                // 2. Create a File object
                const file = new File([blob], "image.jpg", { type: "image/jpeg" });
                
                // 3. Use DataTransfer to simulate file selection
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(file);
                
                // 4. Attach to form and native-submit
                const fileInput = document.getElementById("fileInput");
                fileInput.files = dataTransfer.files;
                
                document.getElementById("lensForm").submit();
            } catch (err) {
                document.body.innerHTML = "Error launching Lens: " + err.message;
            }
        }

        // Execute immediately
        submitToLens();
    </script>
</body>
</html>
"""


def search_image(image_path: str, callback=None):
    """
    Reads the cropped image, embeds it in an auto-submitting HTML file,
    and opens it in the default browser.
    """
    def _worker():
        try:
            # 1. Read image as Base64
            with open(image_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("ascii")

            # 2. Generate HTML content
            html_content = HTML_TEMPLATE.replace("{base64_data}", b64_data)

            # 3. Write to a temporary HTML file
            # We don't delete this immediately so the browser has time to load it
            fd, tmp_html = tempfile.mkstemp(suffix=".html", prefix="lens_search_")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # 4. Open in default browser
            webbrowser.open(f"file:///{tmp_html.replace(os.sep, '/')}")

            if callback:
                callback(True, "")

        except Exception as exc:
            if callback:
                callback(False, f"Failed to launch browser: {exc}")

        finally:
            # Clean up the original screenshot JPEG
            try:
                os.unlink(image_path)
            except Exception:
                pass

    # Run in background to keep UI responsive
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
