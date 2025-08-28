// -------- Config --------
const BASE_URL = "https://portfoliobot-jqqv.onrender.com/"; // update when ngrok changes

// -------- Calendar iframe visibility --------
function showCalendar() {
  const iframe = document.getElementById("calendar-iframe");
  if (iframe) iframe.style.display = "block";
}

function hideCalendar() {
  const iframe = document.getElementById("calendar-iframe");
  if (iframe) iframe.style.display = "none";
}

// -------- Dialogflow event handler --------
function handleDialogflowEvent(event) {
  if (!event || !event.name) return;
  if (event.name === "BOOK_APPOINTMENT" || event.name === "SHOW_CALENDAR") {
    showCalendar();
    fetchSlots();
  }
}

// -------- Fetch available slots --------
async function fetchSlots() {
  const slotsDiv = document.getElementById("slots");
  if (!slotsDiv) return;

  try {
    const res = await fetch(`${BASE_URL}/slots`);
    const data = await res.json();

    slotsDiv.innerHTML = "";
    const slots = (data && data.slots) || [];
    if (!slots.length) {
      slotsDiv.textContent = "No available slots right now.";
      return;
    }

    for (const slot of slots) {
      const btn = document.createElement("button");
      btn.textContent = slot;
      btn.addEventListener("click", () => bookSlot(slot));
      slotsDiv.appendChild(btn);
    }
  } catch (err) {
    console.error("Error fetching slots:", err);
    if (slotsDiv) slotsDiv.textContent = "Failed to load slots.";
  }
}

// -------- Book a slot (calls backend + (optionally) EmailJS on frontend) --------
async function bookSlot(slot) {
  // If you want to collect name/email/phone/details on the page, fetch them here:
  const name = document.getElementById("name")?.value || "";
  const email = document.getElementById("email")?.value || "";
  const phone = document.getElementById("phone")?.value || "";
  const details = document.getElementById("details")?.value || "";

  try {
    const res = await fetch(`${BASE_URL}/book`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot, name, email, phone, details }),
    });
    const result = await res.json();

    const msg = document.getElementById("message");
    if (result.status === "success") {
      if (msg) msg.textContent = result.message;
      else alert(result.message);
      hideCalendar();
      // (Optional) If you prefer sending EmailJS from the client instead of server, trigger here.
    } else {
      if (msg) msg.textContent = result.message || "Booking failed.";
      else alert(result.message || "Booking failed.");
    }
  } catch (error) {
    console.error("Error booking slot:", error);
    alert("Booking failed. Please try again.");
  }
}

// -------- On page load --------
document.addEventListener("DOMContentLoaded", () => {
  // In production, call handleDialogflowEvent(...) when your agent triggers it.
  // This simulation is for local testing:
  const simulated = { name: "BOOK_APPOINTMENT", data: {} };
  handleDialogflowEvent(simulated);
});

// -------- Google OAuth (to create token.json once) --------
function loginWithGoogle() {
  window.location.href = `${BASE_URL}/authorize`;
}
