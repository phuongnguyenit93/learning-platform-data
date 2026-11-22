# WebSocket.request(n): throttling receive invocations, not complete messages (Java 17)

## 1. The problem: `request(1)` was called, so why haven't I received an entire message yet?

When building a WebSocket client with `java.net.http.HttpClient` in Java 17, learners often encounter the snippet:

```java
@Override
public void onOpen(WebSocket webSocket) {
    webSocket.request(1);
}
```

A tempting but **incorrect** assumption is: “`request(1)` asks the WebSocket to deliver **one complete text or binary message** to the listener.” In reality, the API defines `request(n)` in terms of **the number of invocations of `WebSocket.Listener` receive methods**. A single text/binary message can arrive across **multiple `onText`/`onBinary` invocations**, each with a `last` flag indicating whether that part ends the message.

For example, suppose a WebSocket peer sends the logical message `Hello`. The listener might receive:

```text
onText("Hel", false)     # part 1: message not finished yet
onText("lo",  true)      # part 2: message ends
```

If the application has only granted **1** turn via `request(1)`, the first callback has already consumed that turn. The second callback will **not be invoked** until more demand is granted. If the code only calls `request(1)` after seeing `last == true`, it can deadlock itself mid-message: it hasn't received the final part so it doesn't request more, and without requesting more there is no final part to receive.

Furthermore, `onPing`, `onPong`, and `onClose` are also **receive methods** under the Java 17 contract. A Ping/Pong/Close can consume a turn of demand **without completing any text/binary business message**. Therefore, `request(5)` **does not mean “allow five complete messages”**, much less a promise to receive exactly five messages.

**Lesson focus:** understand `WebSocket`'s internal receive counter, distinguish *callback invocation*, *data fragment*, *WebSocket message*, and *business message*, how to use `last` to assemble content, continue calling `request(1)` at the right time, control backpressure, handle Ping/Pong/Close/Error, and the interaction between demand and the `CompletionStage` returned by the listener.

This lesson applies the Java SE 17 `java.net.http.WebSocket` and `WebSocket.Listener` APIs.

## 2. Exact definition of `request(n)`

According to the Java 17 Javadoc, a `WebSocket` object maintains **a counter of the number of receive method invocations still permitted**.

The process:

1. A newly created WebSocket starts with **a counter of 0**.
2. Calling `webSocket.request(n)` with **`n > 0`** **increases the counter by n**.
3. Each time the WebSocket invokes **a receive method** on the listener, the counter decreases by **one**.
4. When the counter is 0, the WebSocket **does not invoke receive methods**, even if some frames have arrived at the transport and there is still work to deliver to the application.
5. The application can call `request` multiple times to add turns; this is **cumulative demand**, not a convention of “each request creates a new message.”

### Callbacks counted toward demand

| `WebSocket.Listener` callback | Consumes one turn of demand? | What content does it receive? |
|---|---|---|
| `onText(ws, data, last)` | **Yes** | Part or all of a **text message** |
| `onBinary(ws, buffer, last)` | **Yes** | Part or all of a **binary message** |
| `onPing(ws, message)` | **Yes** | A Ping control message (up to 125 bytes payload) |
| `onPong(ws, message)` | **Yes** | A Pong control message (up to 125 bytes payload) |
| `onClose(ws, status, reason)` | **Yes** | Close control message and signal that input has closed |
| `onOpen(ws)` | **No** | Notification that the WebSocket connection has opened |
| `onError(ws, error)` | **No** | Error, may be invoked regardless of whether demand remains |

**Most important takeaway:** the counter controls **invocations of the five receive methods**; it does not directly count payload bytes, WebSocket frames, the number of times the application parses JSON, or the number of committed business events.

### Distinguishing four kinds of “units”

| Unit | Example | Relationship with `request(n)` |
|---|---|---|
| TCP byte | A chunk of bytes returned by the socket | `request(n)` is **not** counted in bytes |
| WebSocket frame/fragment | A piece of data encapsulated in the protocol | You must not assume one frame always equals one Java callback |
| Listener invocation | One `onText`, `onBinary`, `onPing`, `onPong`, or `onClose` call | **The exact unit** of demand |
| WebSocket message | A text/binary message ending when `last == true` | May require **multiple** listener invocations |
| Business record | A JSON object, transaction, or business event | One WebSocket message may contain multiple records, or the business protocol may have its own rules |

The mechanism for choosing how to fragment data, coalesce frames, or deliver callbacks depends on the API/implementation and the actual data. Do not invent the formula `request(1) == 1 frame == 1 JSON`.

## 3. The counter model: adding demand, subtracting per callback

Suppose the listener proactively calls:

```java
webSocket.request(3);
```

A sequence of callbacks **might** unfold as follows:

| Step | Event | Demand before | Demand after | Complete text messages |
|---|---|---:|---:|---:|
| 0 | `request(3)` | 0 | 3 | 0 |
| 1 | `onText("Hel", false)` | 3 | 2 | 0 |
| 2 | `onText("lo", true)` | 2 | 1 | **1** |
| 3 | `onPing(emptyBuffer)` | 1 | 0 | Still **1** |
| 4 | More bytes received, `request` not yet called | 0 | 0 | No next callback yet |
| 5 | `request(1)` | 0 | 1 | Does not create a message by itself |
| 6 | `onText("Bye", true)` | 1 | 0 | **2** |

At step 3, Ping consumed a turn even though the count of complete text messages did not increase. At step 4, the program must not infer that the peer stopped sending; it only knows **there is no remaining credit to invoke another receive method**.

### `request(0)` or `request(-1)`

`request(n)` requires `n > 0`. Per Java 17, if `n <= 0`, the method throws `IllegalArgumentException`.

**Wrong:**

```java
// For illustrating the API error only; do not run standalone.
webSocket.request(0);   // IllegalArgumentException
webSocket.request(-1);  // IllegalArgumentException
```

Do not use `request(0)` as a pause command, and do not use `request(-1)` to return credit to the counter. **To pause**, temporarily **stop granting additional demand**, while managing any remaining outstanding turns. Once you have called `request(1000)`, there is no `unrequest(999)` API to retract demand immediately; the receive window should be designed intentionally from the start.

### `request(n)` is not a waiting method

`request(n)` is not like `Future.get(n, unit)`; it does not wait for n callbacks and then return. It is an operation that **declares additional receive capacity**. Network errors or timeouts are not turned into message-completion policies simply by calling `request` again.

## 4. Text/Binary fragmentation and the `last` flag

Java 17 receives text via:

```java
CompletionStage<?> onText(
        WebSocket webSocket, CharSequence data, boolean last);
```

and binary via:

```java
CompletionStage<?> onBinary(
        WebSocket webSocket, ByteBuffer data, boolean last);
```

The `last` argument is **the indicator of whether the current fragment ends the WebSocket message**:

- `last == false`: more data of **the same message** will arrive in subsequent appropriate receive invocations.
- `last == true`: the current part ends the message; the application can finish assembling/parsing that message.
- A small message **may** be reported in a single callback with `last == true`; however, that is not a contract for every message.

**Do not guess the end of a message from the number of `request` turns or the buffer size.** Nor should you treat `CharSequence.length() < X` or `ByteBuffer.remaining()==0` as a sign that the message has ended. `last` is the end-of-message signal in the listener API.

### Two-fragment text message pattern

```text
Application: request(1)
WebSocket: onText("Cof", false)    -> consumes 1 credit
Application: append "Cof" to StringBuilder
Application: request(1)
WebSocket: onText("fee", true)     -> consumes 1 credit
Application: assemble into "Coffee", then process the message
```

`request(1)` itself **does not let you force the runtime to split a message into a specific callback**; this is just an example of one valid receive sequence.

### Binary is read within position–limit

`onBinary` receives a `ByteBuffer`: the data is in the region from `buffer.position()` to `buffer.limit()`. Do not read the entire `buffer.array()` because:

- The buffer may be direct or read-only, without an accessible backing array.
- Position/limit define the valid data region; the array may contain other bytes outside the slice.
- The buffer's lifetime is managed by the runtime and may no longer be valid after the completion stage finishes.

When you need to retain the data longer, **copy** the remaining bytes into a buffer/array owned by the application. Do not keep a reference to the `ByteBuffer` provided by the callback and use it later after reporting the stage complete.

## 5. `onOpen`, default methods, and the risk of exhausting demand

`WebSocket.Listener` is an interface with **default** methods. Several default behaviors in Java 17 help a simple listener keep receiving:

- Default `onOpen` is equivalent to `webSocket.request(1)`.
- Default `onText`, `onBinary`, `onPing`, and `onPong` all call `webSocket.request(1)` and return `null`.
- Default `onClose` returns `null`, allowing the output side to close per the contract; it **does not request more**.
- Default `onError` is not a receive method and does not increase demand.

### When overriding `onOpen`

If you override `onOpen` **without** calling `request(...)`, the counter remains at 0, and the application may not receive any other text/binary/control callbacks. For example:

```java
// Error illustration: onOpen is overridden without granting demand.
@Override
public void onOpen(WebSocket socket) {
    logConnected();
    // Missing socket.request(1).
}
```

If you want to leverage the default, you can omit overriding `onOpen` or call `WebSocket.Listener.super.onOpen(socket)` when overriding, though it is usually clearer to call `socket.request(1)` directly after setting up state.

### When overriding `onText`

A very common mistake:

```java
// Error illustration: receives one callback and fails to grant further demand.
@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence part, boolean last) {
    accumulator.append(part);
    if (last) {
        handleComplete(accumulator.toString());
    }
    return null; // Does not automatically request more!
}
```

This method **has replaced** the default implementation that automatically requests more. If only one credit remained previously, the connection will not invoke the next `onText`. Fix: according to your chosen policy, call `request(1)` once ready to receive the next callback, even when `last == false`.

### Ping/Pong can “eat” credit

Suppose you override `onText`, but do not override `onPing`/`onPong`. The default `onPing`/`onPong` **automatically grant 1 more credit**; that is the specific behavior of the default listener. If you override Ping/Pong just to log and forget `request(1)`, a single Ping can exhaust the last credit and stall data delivery.

**Separate protocol Ping/Pong from business count:** Ping/Pong are WebSocket control messages, not application text/binary messages. The Java WebSocket client automatically sends a corresponding Pong when receiving a Ping per the contract; most listeners do not need to call `sendPong` manually just to respond to a Ping.

## 6. A controlled text-receiving listener

This is an **illustrative code snippet**, not a standalone Java program. It shows the receive loop using one credit at a time, assembling fragments, and then processing the message:

```java
WebSocket.Listener listener = new WebSocket.Listener() {
    private final StringBuilder partial = new StringBuilder();

    @Override
    public void onOpen(WebSocket socket) {
        socket.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket socket, CharSequence data, boolean last) {
        partial.append(data);

        if (last) {
            String message = partial.toString();
            partial.setLength(0);
            processCompleteMessage(message); // application-defined
        }

        socket.request(1); // NEXT receive invocation.
        return null;
    }
};
```

**Meaning:**

1. `onOpen` grants the initial demand.
2. `onText` accumulates each part into `partial`, **not processing the message before `last==true`**.
3. After each callback, the application grants one more turn. Thus, a message can be assembled across multiple callbacks without getting stuck on the first fragment.
4. `return null` is interpreted by the API as a normally completed completion stage, meaning the runtime may reclaim the provided `CharSequence`. The code does not retain the original reference to `data`, instead appending/copying the data into an application-owned buffer.
5. This is an **unbounded queue/memory** strategy; for large or asynchronous processing, you need buffer limits/backpressure as described later.

**Do not both call `request(1)` in `onOpen` and call the default `super.onOpen` if both together grant unintended demand.** One credit or multiple credits is a policy decision, not “number of HTTP requests” or “number of messages.”

## 7. `onPing`, `onPong`, `onClose`, `onError`, and credit

### 7.1. `onPing` and `onPong` are receive methods

These two callbacks receive a `ByteBuffer` with a payload of at most **125 bytes** per the WebSocket protocol. Each invocation, like `onText`, consumes **one** unit of demand.

```java
// Illustrative snippet: overriding Ping while maintaining receive demand.
@Override
public CompletionStage<?> onPing(
        WebSocket socket, ByteBuffer payload) {
    recordPing();   // application-defined
    socket.request(1);
    return null;
}
```

If you override Ping and forget to rearm, and the peer sends a Ping when only one credit remains, the next event may be held back. `onPong` behaves similarly. The Java implementation automatically sends a corresponding Pong upon receiving a Ping, so there is no need to emit a second Pong manually to satisfy the standard Ping/Pong handshake.

### 7.2. `onClose` is the final receive method

`onClose(socket, statusCode, reason)` consumes credit just like the other receive callbacks. When it is invoked, the **input** side of the WebSocket has closed per the contract, and this is the **final** callback for that socket. There is no reason to request more data from an already closed connection.

If the output side has not yet closed, `onClose`'s completion stage also participates in deciding when output can close accordingly; it is not merely a method for logging the status code. Default `onClose` returns `null`, allowing output closure per the contract.

### 7.3. `onError` does not require demand

`onError(socket, error)` does not belong to the group of receive methods throttled by `request(n)`. It can be invoked when demand is 0. Java 17 describes it as the final callback when an error occurs (after `onOpen`); when the callback begins, both input and output are closed. Code should clean up/log in a controlled manner and not call `request` to “fix the error.”

An exception thrown from a listener callback or a receive callback's `CompletionStage` completing exceptionally can cause the WebSocket to invoke `onError`. Therefore, do not let parsers/handlers throw unexpected exceptions without a handling policy.

### 7.4. `sendClose` differs from `request`

- `webSocket.sendClose(...)` is a **send operation** for Close, relating to the output side.
- `webSocket.request(n)` is **receive credit** for callbacks from the input side.
- `webSocket.abort()` abruptly closes input/output; it is not backpressure.
- `isInputClosed()` and `isOutputClosed()` are for observing state, not for replacing the throttling counter.

If the client has sent Close but input is not yet closed, the receive side may still need to handle the corresponding Close callback according to the lifecycle. Do not use `request(1)` as a close command or `sendClose` to “grant more credit.”

## 8. `CompletionStage` and `request(n)` are two different mechanisms

The listener methods `onText`, `onBinary`, `onPing`, and `onPong` return `CompletionStage<?>` (or `null`), but **CompletionStage is not a demand counter**.

- **`request(n)`:** allows the WebSocket to **invoke n more receive methods** on the listener.
- **Stage completion:** tells the WebSocket that the callback has finished using the data object passed by the implementation (`CharSequence`/`ByteBuffer`), so the implementation can **reclaim resources/close the receive loop** per the contract.
- Completing the stage does not automatically call `request(1)`.
- Calling `request(1)` does not automatically complete the stage.
- Per the Java 17 Javadoc, the WebSocket **is not required to wait for the previous callback's `CompletionStage` to complete** before invoking the next callback when demand is available. Therefore, callback logic must manage state and data properly.

### A seemingly small race condition

```text
onText(data1, last=false)
  -> application keeps reference to data1
  -> request(1)
  -> return completedFuture(null)
WebSocket is allowed to reclaim data1
  -> asynchronous worker is still reading data1
  -> WRONG: data lifetime is no longer guaranteed
```

The right way is to **copy the content to be processed** into an application-owned buffer/string before returning a completed stage, or keep the stage incomplete until the callback data is truly no longer needed. At the same time, regulate demand according to the worker/queue capacity.

### Sequential callbacks do not mean all async tasks are ordered

Java 17 `WebSocket.Listener` guarantees that callback invocations for **the same WebSocket** are **non-reentrant**: the next invocation does not start before the previous invocation **returns**. However, a callback may spawn async tasks that continue running **after** the callback method returns. Those tasks may run concurrently or complete out of message order if you do not serialize them yourself.

Therefore:

- Separate `onText` appending/copying inside the callback from async business tasks.
- If messages must be processed in order, use a per-connection queue/serial executor.
- Ensure a listener shared across **multiple WebSockets** does not share a mutable `StringBuilder`/`ByteBuffer` without synchronization or per-socket state partitioning.
- Do not issue more demand beyond actual processing capacity merely because the callback method has returned.

## 9. Scenario: `request(1)` called, yet no complete message yet

Suppose the peer sends **a single message** of 50 KiB. The implementation might split callbacks as follows:

```text
request(1)              credit = 1
onBinary(chunk A,false) credit = 0, complete messages = 0

request(1)              credit = 1
onBinary(chunk B,false) credit = 0, complete messages = 0

request(1)              credit = 1
onBinary(chunk C,true)  credit = 0, complete messages = 1
```

There were **3 `onBinary` invocations**, yet only **1 message**. If callback B gets stuck due to lack of demand, a buffer for the incomplete message may remain waiting for a long time; timeout and cleanup management are required.

Conversely, a small message may be delivered in **a single** `onText("OK", true)`. Thus you cannot calculate:

```text
number of complete messages = sum of request(n) called
```

Rather, **count messages when `last == true` is seen**, and count callbacks separately if you want to observe demand. For business protocols that pack multiple records into one message, you must also parse according to the schema to determine the number of business events.

### ByteBuffer and backpressure

Whether each binary callback carries 1 KiB or 64 KiB, `request(1)` is still **one callback**. It does not guarantee delivering exactly n bytes or directly controlling individual TCP reads. The JVM may have buffers or protocol frames already received before the listener is invoked. Therefore, demand is **application receive backpressure on callback delivery**, not a substitute for bounded queues, max message size, transport-layer flow control, or timeouts.

## 10. Runnable Java 17 program: simulating the WebSocket counter

To demonstrate **the exact difference between callbacks and complete messages** without depending on a real WebSocket server, the demo below creates a **test harness `DemoSocket implements WebSocket`**. This class only simulates the **demand counter and listener invocations**; it does not perform a handshake, send WebSocket frames/TCP, or implement a full network client.

The program uses **real Java 17 interfaces** (`WebSocket`, `WebSocket.Listener`), so it compiles and runs without external libraries.

Scenario:

1. `onOpen` calls `request(2)`.
2. The harness calls `onText("Hel", false)`, then `onText("lo", true)` → **2 credits consumed**, but only **1 message `Hello`** completed.
3. Credit drops to 0; the harness attempts to deliver a Ping but **does not invoke the listener** when credit is lacking, returning `false` to make the issue visible.
4. Calls `request(1)` for Ping, then `request(1)` for text `Bye`, and finally `request(1)` for Close.
5. In total there are **5 receive method invocations**, but **only 2 complete text messages**.

Create the file **`WebSocketDemandDemo.java`**:

```java
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class WebSocketDemandDemo {
    static final class DemoSocket implements WebSocket {
        private long demand;
        private WebSocket.Listener listener;
        private boolean inputClosed;
        private boolean outputClosed;

        void open(WebSocket.Listener newListener) {
            listener = newListener;
            listener.onOpen(this);
        }

        long remaining() {
            return demand;
        }

        private boolean consumeOne() {
            if (demand == 0) {
                return false;
            }
            demand--;
            return true;
        }

        boolean deliverText(String part, boolean last) {
            if (!consumeOne()) {
                return false;
            }
            CompletionStage<?> stage =
                    listener.onText(this, part, last);
            if (stage != null) {
                stage.toCompletableFuture().join();
            }
            return true;
        }

        boolean deliverPing() {
            if (!consumeOne()) {
                return false;
            }
            CompletionStage<?> stage =
                    listener.onPing(this, ByteBuffer.allocate(0));
            if (stage != null) {
                stage.toCompletableFuture().join();
            }
            return true;
        }

        boolean deliverClose(int status, String reason) {
            if (!consumeOne()) {
                return false;
            }
            inputClosed = true;
            CompletionStage<?> stage =
                    listener.onClose(this, status, reason);
            if (stage != null) {
                stage.toCompletableFuture().join();
            }
            outputClosed = true;
            return true;
        }

        @Override
        public void request(long n) {
            if (n <= 0) {
                throw new IllegalArgumentException(
                        "n must be positive");
            }
            demand = n > Long.MAX_VALUE - demand
                    ? Long.MAX_VALUE : demand + n;
        }

        @Override
        public String getSubprotocol() {
            return "";
        }

        @Override
        public boolean isInputClosed() {
            return inputClosed;
        }

        @Override
        public boolean isOutputClosed() {
            return outputClosed;
        }

        @Override
        public void abort() {
            inputClosed = true;
            outputClosed = true;
        }

        @Override
        public CompletableFuture<WebSocket> sendText(
                CharSequence data, boolean last) {
            throw new UnsupportedOperationException(
                    "No network in demo");
        }

        @Override
        public CompletableFuture<WebSocket> sendBinary(
                ByteBuffer data, boolean last) {
            throw new UnsupportedOperationException(
                    "No network in demo");
        }

        @Override
        public CompletableFuture<WebSocket> sendPing(
                ByteBuffer message) {
            throw new UnsupportedOperationException(
                    "No network in demo");
        }

        @Override
        public CompletableFuture<WebSocket> sendPong(
                ByteBuffer message) {
            throw new UnsupportedOperationException(
                    "No network in demo");
        }

        @Override
        public CompletableFuture<WebSocket> sendClose(
                int statusCode, String reason) {
            throw new UnsupportedOperationException(
                    "No network in demo");
        }
    }

    static final class CountingListener
            implements WebSocket.Listener {
        private final StringBuilder partial = new StringBuilder();
        private final List<String> messages = new ArrayList<>();

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(2);
            System.out.println("onOpen: request(2)");
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence data, boolean last) {
            partial.append(data);
            System.out.println(
                    "onText: " + data + " last=" + last);
            if (last) {
                String complete = partial.toString();
                messages.add(complete);
                partial.setLength(0);
                System.out.println("complete message: " + complete);
            }
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onPing(
                WebSocket socket, ByteBuffer message) {
            System.out.println("onPing: received");
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket socket, int status, String reason) {
            System.out.println("onClose: " + status);
            return CompletableFuture.completedFuture(null);
        }

        int completeMessageCount() {
            return messages.size();
        }
    }

    public static void main(String[] args) {
        DemoSocket socket = new DemoSocket();
        CountingListener listener = new CountingListener();
        socket.open(listener);

        socket.deliverText("Hel", false);
        socket.deliverText("lo", true);
        System.out.println("remaining demand: "
                + socket.remaining());

        boolean pingDelivered = socket.deliverPing();
        System.out.println("ping delivered with zero demand: "
                + pingDelivered);

        socket.request(1);
        socket.deliverPing();
        socket.request(1);
        socket.deliverText("Bye", true);
        socket.request(1);
        socket.deliverClose(1000, "done");

        System.out.println("complete messages: "
                + listener.completeMessageCount());
    }
}
```

Compile and run on **JDK 17+**, no network required:

```bash
javac -encoding UTF-8 --release 17 WebSocketDemandDemo.java
java WebSocketDemandDemo
```

**Exact stdout of the program:**

```text
onOpen: request(2)
onText: Hel last=false
onText: lo last=true
complete message: Hello
remaining demand: 0
ping delivered with zero demand: false
onPing: received
onText: Bye last=true
complete message: Bye
onClose: 1000
complete messages: 2
```

### Detailed explanation of the output

- `request(2)` creates **two initial receive turns**; it does **not** create one or two messages.
- The two fragments `"Hel"` and `"lo"` each consume one turn; only when `last==true` on the second fragment does the listener add a complete message `Hello`.
- `remaining demand: 0` after the two callbacks is exact in this simulation.
- `ping delivered with zero demand: false` means the harness **does not invoke `onPing`** when the counter is 0. In a real network implementation, the frame may have been read/buffered internally, but the callback is not invoked when demand is lacking.
- After `socket.request(1)`, Ping is delivered, **not increasing** the complete text-message count.
- `Bye` is a short message arriving in a single `last=true` callback and consuming one credit.
- `onClose` also consumes credit; it ends reception according to the lifecycle model.
- Total 2 + 1 + 1 + 1 = **5 receive callbacks**, but only **2** complete text messages.

### Why must we state clearly that this is a simulation?

`DemoSocket` **does not** simulate the full semantics of the JDK WebSocket implementation such as network reads, TLS, close handshake, auto Pong, async callback scheduling, thread safety, frame buffering, or event queueing. It is merely a **deterministic harness** for observing the counter. A real WebSocket server may split a text message into a **different** number of callbacks than the example, and the timing of `onPing`/`onClose` invocations also depends on the peer and runtime.

In production code, **do not implement WebSocket manually like DemoSocket**. Use `HttpClient.newWebSocketBuilder().buildAsync(uri, listener)` to build a real WebSocket client; `DemoSocket` is only suitable as a conceptual test.

## 11. Real connection via HttpClient: where does the code go?

A Java 17 WebSocket client typically has the structure:

```java
// Illustrative snippet; listener is a valid WebSocket.Listener;
// URI must point to a real WebSocket endpoint (wss://...).
CompletableFuture<WebSocket> connected =
        HttpClient.newHttpClient()
                .newWebSocketBuilder()
                .buildAsync(
                        URI.create("wss://example.com/socket"),
                        listener);

// When no longer needed: send close per protocol and manage timeout;
// if forced closing of input/output is needed, use abort().
```

`HttpClient.newWebSocketBuilder()` initiates the client-side handshake; `buildAsync` returns a future of the WebSocket once connection establishment completes. **This is an illustrative snippet**, not standalone runnable because `listener` is not declared and the endpoint is an example.

Once connected, the listener's `onOpen` is invoked. If using the default `onOpen`, there will be 1 demand; if overriding it, you must decide the demand amount. In `onText`/`onBinary`, **use `last` to assemble messages**; do not infer the message count from `request(n)`.

### A useful listener for text fragments (illustrative)

```java
// Illustrative callback logic, not a standalone class.
final class TextListener implements WebSocket.Listener {
    private final StringBuilder partial = new StringBuilder();
    private final int maxChars = 1_000_000;

    @Override
    public void onOpen(WebSocket socket) {
        socket.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket socket, CharSequence chunk, boolean last) {
        if (chunk.length() > maxChars - partial.length()) {
            socket.abort(); // policy: message exceeds limit
            return null;
        }

        partial.append(chunk);

        if (last) {
            String complete = partial.toString();
            partial.setLength(0);

            // Assume handleMessage is application-defined,
            // synchronous, fast, and does not throw unhandled errors.
            handleMessage(complete);
        }

        socket.request(1);
        return null;
    }
}
```

Here you need to import `java.net.http.WebSocket` and `java.util.concurrent.CompletionStage`; `handleMessage` is application-defined. **The `maxChars` limit is only a limit on the number of accumulated UTF-16 code units**, not a substitute for byte/protocol frame limits. If the handler takes a long time to process, you need a bounded queue and backpressure policy rather than continuing to issue requests unboundedly.

**Error note:** if `handleMessage` throws an exception, the WebSocket may go through `onError`. A real application should catch/log/classify parser errors and decide to close safely. `abort` is a forced close, not a graceful Close handshake; when the protocol allows and the connection is healthy, you can choose to send `sendClose` with an appropriate status/reason.

## 12. Does backpressure actually control load?

`request(n)` helps throttle **the number of receive callbacks delivered to the application**, but it **does not automatically**:

- Limit the total bytes of a message.
- Guarantee that the server stops sending bytes immediately.
- Block a malicious peer from sending large frames or many frames.
- Limit the number of business jobs you have already submitted to a thread pool.
- Handle memory leaks from `StringBuilder`/`ByteBuffer` instances you created.
- Guarantee a callback is a valid JSON message or an entire business event.
- Set deadlines/timeouts for message processing.
- Replace bounded queues and error handling.

To truly operate safely, you must design a **bounded receive pipeline**: grant just enough demand for the listener to **copy/parse** fragments, assemble messages within limits, process them, or hand them off to a downstream with capacity.

### Strategy A — grant one more credit per callback

```java
public CompletionStage<?> onText(
        WebSocket ws, CharSequence part, boolean last) {
    accumulator.append(part);
    if (last) {
        processQuickly(accumulator.toString());
        accumulator.setLength(0);
    }
    ws.request(1);
    return null;
}
```

This is an **illustrative pattern**, not a complete class. Pro: simple, does not stall when a message is split into multiple parts. Con: if `processQuickly` is actually time-consuming or the downstream queue is unbounded, it can slow down the callback thread or increase memory usage.

### Strategy B — grant credit only when downstream has capacity

```text
onText(fragment, last=false)
  -> copy/append within limits
  -> request(1) to fetch the next part, if capacity remains

onText(fragment, last=true)
  -> create completeMessage
  -> enqueue into bounded worker queue
  -> request more only when the queue has space
```

You must account for Ping/Pong and the fact that fragmentation can produce multiple callbacks for one message; do not let the business queue decide demand purely based on “one message = one credit.”

### Strategy C — bounded multi-credit window

A fast-processing receiver can request `n > 1` to keep a window of callbacks ready. However, you must remember **n is callbacks**, not messages; a large message uses up multiple credits, and Ping also uses credits. With high outstanding demand, the application must have sufficient memory/capacity and must not expect `request(100)` to create an exact limit of 100 business jobs.

**Do not try calling `request(0)` to pause** because Java throws `IllegalArgumentException`. Simply stop granting new credit and wait for already-issued credits to be consumed. If a strict stop is needed, use state/cancellation/close according to policy; the counter has no direct decrement API.

## 13. `CompletionStage` and asynchronous processing pipelines

A listener may process business messages using an executor or an async service. There are two different management styles:

### 13.1. Copy data then return a completed stage

```java
// Illustrative snippet: data must be copied before the callback ends.
String owned = data.toString();
queue.submit(owned);  // application-managed bounded queue
ws.request(1);
return null;
```

This is **safe regarding data lifetime** if `toString()` creates the necessary snapshot, but **insufficient for backpressure**: `queue.submit` must have a rejection/bounding policy, and `ws.request(1)` must not grant more demand when the queue is overloaded.

### 13.2. Return an incomplete `CompletionStage`

```java
// Illustrative snippet: processAsync returns CompletionStage<?>.
// Do not retain the original data after the stage completes.
CompletionStage<?> processed = processAsync(data);
return processed;
```

The stage signals when the callback data can be reclaimed. It is **not** proof that receive demand has been automatically re-granted. If `request(1)` is not called somewhere else, reception may stop when the counter reaches 0.

At the same time, Java 17 explicitly states that a pending stage **does not necessarily block subsequent listener invocations** when demand remains. If `processAsync` operates on the same `StringBuilder`/`ByteBuffer` or database state, concurrency and ordering must be protected.

### 13.3. Processing complete messages after `last=true`

A reasonable pattern:

```text
On each callback:
  - check connection / frame type
  - copy + accumulate data within quota
  - if last=false: grant next credit when capacity is available
  - if last=true:
      create immutable complete message
      push to bounded queue
      grant next credit when downstream queue has space
      avoid long CPU/blocking work on the callback thread
```

If processing a logical message must be split across multiple deliveries, the deadline/size limit should be calculated **from the first fragment**, not reset to a fresh long timeout on every fragment, which would open the door to an unbounded slow-drip attack.

## 14. Common mistakes directly related to `request(n)`

| Mistake | Symptom | Correct approach |
|---|---|---|
| Thinking `request(1)` = one complete message | Reading one fragment then failing JSON parse | Assemble `onText/onBinary` by `last` |
| Calling `request(1)` only when `last==true` | Stuck on `last=false` fragment | Keep granting credit for next fragment when capacity remains |
| Overriding `onOpen` without requesting | No data callbacks received | Call `request(1)` or use an explicit demand policy |
| Overriding `onText` and just returning `null` | Counter can stay at 0 forever | Request more when ready |
| Overriding `onPing`/`onPong` and forgetting to request | Ping/Pong consumes the last credit | Re-grant demand appropriately or rely on default |
| Thinking `onError` also needs a request | Error cleanup doesn't run when counter is 0 | `onError` is not a receive method |
| Thinking `onClose` doesn't consume credit | Delayed Close callback | `onClose` is one of the receive methods |
| Using `request(0)` to pause | `IllegalArgumentException` | Temporarily stop granting credit |
| Using `request(-1)` to reduce demand | `IllegalArgumentException` | Define window/capacity properly |
| Receiving many fragments without a limit | `StringBuilder`/byte array grows unboundedly | Max complete-message size + timeout |
| Treating `CompletionStage` completion as auto-requesting more | Reception stalls | Two independent mechanisms |
| Treating `request(1)` as allowing callbacks only after previous stage completes | Async tasks unexpectedly overlap | Callbacks are non-reentrant, but async tasks can overlap |
| Returning a completed stage then keeping the callback `ByteBuffer` | Using data past its lifecycle | Copy bytes or hold the stage for the proper duration |
| Trusting `ByteBuffer.array()` is always usable | Direct/read-only buffers fail | Read from position to limit, copy what is needed |
| Counting business messages by callback count | Metrics wrong during fragmentation/Ping/Pong | Count `last=true` and parse business records |
| Requesting too much credit before having capacity | Weak backpressure, queue overflow | Bounded demand + real backpressure |
| Using a shared `StringBuilder` for multiple sockets | Races/garbled messages | Per-WebSocket state, concurrency-safe |
| Not handling terminal close/error | Resource leaks | Cleanup, close/abort, and terminal state |
| Not testing fragmentation | Code works on small messages but breaks in production | Test multiple partial callbacks, interleaved Ping, Close |

## 15. Testing the right semantics: one callback does not equal one message

A unit test suite for a listener should include **sequences of callbacks**, not just a single `onText("hello", true)`:

| Scenario | Callback sequence | Expectation |
|---|---|---|
| Single-part text | `onText("Hi", true)` | 1 complete text message, 1 credit |
| Two-part text | `onText("Hel", false)`, `onText("lo", true)` | 1 complete text message, 2 credits |
| Three-part text | false, false, true | 1 message, 3 credits |
| Two-part binary | `onBinary(bufA,false)`, `onBinary(bufB,true)` | Exact byte assembly, 2 credits |
| Interleaved Ping | Text fragment, `onPing`, final text | Ping consumes extra credit, does not create a text message |
| Pong | `onPong` | 1 credit, does not create a text message |
| Close | `onClose` | 1 credit; ends listener callbacks |
| Error when demand is 0 | `onError` | May be invoked, does not require credit |
| Demand 0 | More data available but no request yet | No new receive method invoked |
| `request(0)` | Invalid argument | Throws `IllegalArgumentException` |
| Slow stage | Callback returns pending stage then requests more | Do not assume next callback must wait for stage completion |
| Large message | Multiple fragments exceeding limit | Close/reject per policy, do not buffer unboundedly |

**Separate two kinds of tests:**

- **Unit test/harness** (like `WebSocketDemandDemo`) deterministically tests assembly logic and credit management. The harness can actively invoke callbacks in the desired sequence.
- **Integration test** against a real WebSocket server tests handshake, fragmentation on the wire, Ping/Pong, Close handshake, TLS, timeouts, and the behavior of the actual Java runtime. **Do not force the JDK to split a message into an exact number of callbacks guessed from frame counts**; verify correctness across all valid splits.

### Metrics that should be tracked separately

- `receiveInvocations`: number of entries into `onText`, `onBinary`, `onPing`, `onPong`, `onClose`.
- `completeTextMessages`: incremented only when `onText(..., last=true)` finishes a message.
- `completeBinaryMessages`: similarly `onBinary(..., last=true)`.
- `controlMessages`: Ping/Pong/Close separately, not added to business text count.
- `partialBytes / partialChars`: size of the currently accumulating message.
- `queuedMessages`, `processingLatency`, `timeouts`, `errors`, `inputClosed`: reflect application state; do not infer from demand alone.

An application might receive 10 callbacks for one binary message and 3 Pings, meaning 13 credits were used for just one complete business message.

## 16. FAQ: frequently confused questions

### Does `request(3)` mean I will receive exactly three messages?

**No.** It grants the ability to invoke **at most three more receive method invocations**. That could be three fragments of one message, one text fragment + Ping + Pong, three small messages, or fewer than three callbacks if the peer does not send enough events or the connection ends.

### If the peer only sends a small text message, is `request(1)` enough?

**It may be enough** if the runtime delivers the entire message via a single `onText(..., last=true)`. However, you **must not depend** on that assumption for every message. The listener must work correctly when there are multiple partial callbacks.

### Should I call `request(1)` after every `onText`?

This is **the simple pattern illustrated by the Javadoc** and prevents getting stuck mid-fragment. However, when downstream is overloaded, you must grant demand **only when capacity actually remains**, not unboundedly. Either way, do not forget that `last=false` still needs to continue reading to complete the message.

### Is `request(1)` an ACK for the peer's message?

No. It is an **internal credit** throttling callback delivery of the JDK WebSocket client; it does not send a business ACK, does not confirm JSON has been processed, and does not acknowledge a transaction. If the application protocol needs an ACK, design a separate message and send it with `sendText`/`sendBinary` under the corresponding contract.

### Does `CompletionStage.completedFuture(null)` automatically grant more demand?

No. The stage indicates that the callback has finished using the data/allows the runtime to reclaim it; **the demand counter is independent**. When needed, the listener must call `request` explicitly.

### If I ignore Ping/Pong callbacks, does that affect demand?

Yes. Ping/Pong are **receive methods** and consume credit. The default `onPing`/`onPong` in Java 17 call `request(1)`, so if not overridden they have a mechanism to grant more; when overriding, you must review your policy. Do not count Ping/Pong as complete business messages.

### Does `onError` get stuck when the counter is 0?

Not in terms of demand. `onError` is **not** one of the receive methods; Java 17 allows it to be invoked at any time after `onOpen`. It is a terminal callback on error and is not a message to be counted.

### Does `onClose` count toward `request(n)`?

**Yes.** `onClose` is among the five throttled receive methods. After `onClose`, there will be no further callbacks on that WebSocket, regardless of remaining credit.

### If I return a pending stage, is the WebSocket guaranteed to stop invoking callbacks?

**No.** The Javadoc states that `CompletionStage` and the invocation counter are two separate mechanisms; a subsequent invocation can still occur when demand has been granted. To reduce receive rate, manage demand and queues; to preserve buffer lifetime, manage the completion stage.

### Does `request(n)` throttle the sending side `sendText`?

**No.** `sendText` and `sendBinary` are send operations returning a `CompletableFuture` describing send-side completion. `request(n)` throttles the listener's **receive methods**, not send quota.

### What if a message is aborted mid-way due to a parser error?

There must be a clear termination/closing policy. Do not leave a partial `StringBuilder`/`ByteBuffer` around and keep the connection open indefinitely; you can send Close per protocol if still valid, or `abort` in situations requiring forced termination. You should clean up connection state and log the error without exposing sensitive content.

## 17. Checklist for writing a production `WebSocket.Listener`

1. **Read the Java 17 API accurately:** `request(n)` counts **receive callbacks**, not complete messages or raw frames.
2. **Set initial demand in `onOpen`** if overridden; remember default `onOpen` calls `request(1)` automatically.
3. **Assemble text/binary by `last`**, do not parse a complete message when `last=false`.
4. **After each non-final fragment, have a mechanism to grant further credit** when capacity suffices; avoid getting stuck mid-message.
5. **Account for Ping/Pong/Close in the receive budget**; `onOpen`/`onError` do not consume credit.
6. **Do not use `request(0)`/`request(-1)`**, because n must be positive; multiple requests accumulate demand and there is no API to retract credit.
7. **Understand default listener methods**: `onText`/`onBinary`/`onPing`/`onPong` have a default `request(1)` mechanism; overriding means taking responsibility yourself.
8. **Separate `CompletionStage` from demand**, do not use stage completion in place of `request` or vice versa.
9. **Protect callback data lifetime**: copy text/bytes before returning a completed stage if needed for later processing; do not retain runtime `ByteBuffer`s after completion.
10. **Bound message size, queue size, and processing time**; demand does not replace streaming/bounded backpressure.
11. **Maintain per-connection state**, avoiding shared mutable `StringBuilder`s across multiple WebSockets.
12. **Handle terminal close/error**, do not make pointless requests after input has closed; distinguish `sendClose` and `abort`.
13. **Do not block long on the callback thread**, coordinate async processing with data ownership and message ordering.
14. **Measure callbacks, complete messages, and business records separately**, do not use the demand counter as a business KPI.
15. **Test fragmentation, control frames, and demand 0** with a unit harness; test handshake/network/TLS with real integration tests.
16. **Clearly document the limits of examples**, do not treat an in-memory simulator as a real WebSocket server.

**Conclusion:** `WebSocket.request(n)` in Java 17 grants **n more receive invocations** via `onText`, `onBinary`, `onPing`, `onPong`, and `onClose`. A text/binary message may take one or more turns and is only considered complete when the corresponding fragment has `last == true`. `onOpen` and `onError` do not consume demand; `CompletionStage` is a separate completion/lifetime management mechanism. A proper design must manage **credit, fragmentation, buffer ownership, and downstream capacity** as four related responsibilities that cannot substitute for one another.

### Official references

- [Java SE 17 — WebSocket.request(long) and receive-invocation counter](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html#request(long))
- [Java SE 17 — WebSocket.Listener: onText/onBinary/onPing/onPong/onClose/onError](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [Java SE 17 — WebSocket.Builder, buildAsync, and WebSocket lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [RFC 6455 — WebSocket Protocol: fragmentation and control frames](https://www.rfc-editor.org/rfc/rfc6455)
