// Drives the real frontend for end-to-end tests. Load after e2e_camera_mock.js, which provides window.__setFace.
window.__e2e = (() => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const find = (scope, labels) => [...document.querySelectorAll(`${scope} button`)]
    .find((b) => labels.includes(b.innerText.trim()));

  async function waitFor(fn, timeout = 30000, step = 5) {
    const start = performance.now();
    while (performance.now() - start < timeout) {
      const value = fn();
      if (value) return value;
      await sleep(step);
    }
    throw new Error("Timed out waiting for the page");
  }

  // The status banner is a green or red box whose text starts with a tick or a cross.
  function banner() {
    const box = [...document.querySelectorAll("div")].find((d) =>
      /bg-(green|red)-600/.test(d.className) && /^[✅❌]/.test(d.textContent.trim()));
    return box ? box.textContent.trim() : "";
  }

  function setValue(el, value) {
    const proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  }

  async function openTab(label) {
    find("nav", [label]).click();
    await sleep(150);
  }

  async function capture(face) {
    const cancel = find("main", ["Cancel"]);   // start from a closed camera
    if (cancel) { cancel.click(); await sleep(200); }
    await window.__setFace(face);
    (await waitFor(() => find("main", ["Start Camera"]))).click();
    await waitFor(() => { const v = document.querySelector("main video"); return v && v.readyState >= 2 && v.videoWidth > 0; });
    (await waitFor(() => find("main", ["Capture Photo", "Capture"]))).click();
    await waitFor(() => find("main", ["Retake"]));   // shown only once a photo has been captured
  }

  // Click a submit button and return the server's message and the time until it was displayed.
  async function submit(label) {
    const start = performance.now();
    find("main", [label]).click();
    const message = await waitFor(() => { const b = banner(); return b && !b.includes("Image captured") ? b : null; });
    return { message, ms: Math.round(performance.now() - start) };
  }

  async function register(name, matNo, level, face) {
    await openTab("Register User");
    await capture(face);
    setValue(document.querySelector('input[placeholder="Enter full name"]'), name);
    setValue(document.querySelector('input[placeholder="Enter matric number"]'), matNo);
    setValue(document.querySelector("main select"), level);
    await sleep(100);
    return submit("Register User");
  }

  async function markAttendance(face) {
    await openTab("Mark Attendance");
    await capture(face);
    return submit("Mark Attendance");
  }

  async function deleteUser(name) {
    await openTab("Users");
    const row = await waitFor(() => [...document.querySelectorAll("tbody tr")].find((r) => r.innerText.includes(name)));
    row.querySelector('button[title="Delete user"]').click();   // window.confirm is accepted by the test runner
    return waitFor(() => banner());
  }

  async function clearBanner() {
    await waitFor(() => !banner(), 8000, 100);
  }

  return { sleep, waitFor, banner, openTab, capture, register, markAttendance, deleteUser, clearBanner };
})();
