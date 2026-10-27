// Replaces the webcam with a 640 x 480 canvas stream for automated tests through the real frontend.
// window.__setFace(dataUrl) shows a test photo; window.__setFace(null) shows an empty grey frame.
(() => {
  const canvas = document.createElement("canvas");
  canvas.width = 640;
  canvas.height = 480;
  const ctx = canvas.getContext("2d");
  let face = null;

  function draw() {
    ctx.fillStyle = "#7a828c";
    ctx.fillRect(0, 0, 640, 480);
    if (face) {
      const h = 480, w = face.width * (480 / face.height);
      ctx.drawImage(face, (640 - w) / 2, 0, w, h);
    }
    ctx.fillStyle = "rgba(0,0,0,0.6)";
    ctx.fillRect(0, 456, 250, 24);
    ctx.fillStyle = "#fff";
    ctx.font = "14px sans-serif";
    ctx.fillText("SIMULATED CAMERA: TEST IMAGE", 8, 473);
  }
  setInterval(draw, 100);
  draw();

  window.__setFace = (dataUrl) => new Promise((resolve) => {
    if (!dataUrl) { face = null; draw(); return resolve(); }
    const img = new Image();
    img.onload = () => { face = img; draw(); resolve(); };
    img.src = dataUrl;
  });

  navigator.mediaDevices.getUserMedia = async () => canvas.captureStream(15);
})();
