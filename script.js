// Function to show the Google Calendar iframe
function showCalendar() {
    const iframe = document.getElementById('calendar-iframe');
    iframe.style.display = 'block'; // Show the iframe
}

// Listen for events from Dialogflow
function handleDialogflowEvent(event) {
    if (event.name === 'SHOW_CALENDAR') {
        showCalendar(); // Show the Google Calendar iframe
    }
}

// Fetch available slots from the backend
async function fetchSlots() {
    try {
        const response = await fetch('https://1654-102-176-75-159.ngrok-free.app/slots');
        const data = await response.json();
        const slotsDiv = document.getElementById('slots');
        slotsDiv.innerHTML = ''; // Clear previous slots
        data.slots.forEach(slot => {
            slotsDiv.innerHTML += `<button onclick="bookSlot('${slot}')">${slot}</button>`;
        });
    } catch (error) {
        console.error('Error fetching slots:', error);
    }
}

// Book a slot
async function bookSlot(slot) {
    try {
        const response = await fetch('https://1654-102-176-75-159.ngrok-free.app/book', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ slot }),
        });
        const result = await response.json();
        alert(result.message);
    } catch (error) {
        console.error('Error booking slot:', error);
    }
}

// Fetch slots when the page loads
document.addEventListener('DOMContentLoaded', fetchSlots);

// Listen for Dialogflow events
document.addEventListener('DOMContentLoaded', () => {
    // Simulate receiving an event from Dialogflow
    const event = { name: 'SHOW_CALENDAR', data: {} };
    handleDialogflowEvent(event);
});