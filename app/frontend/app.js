const form = document.getElementById("query-form");
const replyEl = document.getElementById("reply");
const clearBtn = document.getElementById("clear");

function appendText(text) {
  replyEl.textContent += text;
  // keep scroll at bottom
  replyEl.scrollTop = replyEl.scrollHeight;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  replyEl.textContent = "";

  const user_id = document.getElementById("user-id").value.trim();
  const model_hint = document.getElementById("model-hint").value || null;
  const use_memory = document.getElementById("use-memory").checked;
  const prompt = document.getElementById("prompt").value.trim();

  if (!user_id || !prompt) {
    alert("user_id and prompt are required");
    return;
  }

  const payload = { user_id, prompt, model_hint, use_memory };

  try {
    const resp = await fetch("/api/v1/stream_query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const text = await resp.text();
      appendText(`[Error: ${resp.status}] ${text}`);
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE events are separated by double newline
      let parts = buffer.split("\n\n");
      buffer = parts.pop(); // remainder

      for (const part of parts) {
        if (!part) continue;
        // lines may be "data: {...}" or "event: name" / "data: {...}"
        const lines = part.split("\n").map(l => l.trim()).filter(Boolean);
        let eventName = null;
        let dataLines = [];
        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventName = line.slice("event:".length).trim();
          } else if (line.startsWith("data:")) {
            dataLines.push(line.slice("data:".length).trim());
          }
        }
        const dataStr = dataLines.join("\n");
        if (dataStr) {
          try {
            const obj = JSON.parse(dataStr);
            if (obj.chunk) {
              appendText(obj.chunk);
            } else if (obj.error) {
              appendText(`\n[Error] ${obj.error}\n`);
            } else if (obj.status) {
              appendText(`\n[Status] ${obj.status}\n`);
            } else {
              appendText(JSON.stringify(obj));
            }
          } catch (e) {
            // not JSON: just append raw data
            appendText(dataStr);
          }
        }
        if (eventName === "done") {
          appendText("\n\n[Stream complete]\n");
        } else if (eventName === "error") {
          appendText("\n\n[Stream error]\n");
        }
      }
    }
  } catch (err) {
    appendText(`\n[Client error] ${err.message}\n`);
    console.error(err);
  }
});

clearBtn.addEventListener("click", () => {
  document.getElementById("prompt").value = "";
  replyEl.textContent = "";
});