# HTTP/1.1: Connection Reuse and Content Boundaries

## Objectives

In HTTP/1.1, a client typically does not close the TCP connection immediately after each response. A single connection can carry **multiple consecutive request–response pairs**. This saves the overhead of TCP/TLS setup, but it is only safe when both sides accurately determine **at which byte each HTTP message ends**. If the server under-reads the request body, the remaining bytes may be misinterpreted as the next request. If the client over-reads the response body, bytes from the next response may be swallowed into the previous message.

This lesson explains the relationship between **persistent connections (keep-alive)** and **HTTP message framing**, the precedence rules of `Content-Length`, `Transfer-Encoding: chunked`, bodyless statuses/methods, and responses terminated by closing the connection. You will learn why HTTP/1.1 allows reuse by default yet **does not mean every connection is always reused**, how to detect parser bugs, and how to use Java 17+ instead of implementing your own HTTP parser for real applications.

After this lesson, you will be able to:

1. Distinguish between a **TCP connection**, an **HTTP message**, a **header section**, a **message body**, and **representation/content**.
2. Explain `Connection: close`, default keep-alive in HTTP/1.1, and the rule of reading the entire message before sending/receiving the next message.
3. Correctly determine body boundaries according to the **precedence rules of RFC 9112 §6.3**, including cases with no body.
4. Read `Content-Length` accurately in **number of bytes (octets)**, and decode `chunked` up to the zero-sized chunk and trailer terminator.
5. Identify a close-delimited response and explain why it generally **cannot continue using the same connection**.
6. Understand pipelining, HTTP/1.1 response ordering, differences from HTTP/2 multiplexing, and retry limitations.
7. Run three Java 17+ programs: two requests/responses on **one TCP connection**, reading two consecutive responses using chunk framing, and checking responses whose HTTP message body length is zero by protocol semantics.

## 1. Two Different Lifecycles: Connection and Message

TCP provides an **ordered byte stream**, not HTTP message boundaries. A single `Socket.getOutputStream().write(...)` may be split into multiple `InputStream.read(...)` calls, or multiple writes may be coalesced when read. How HTTP/1.1 formats messages is an **application-layer** mechanism, independent of the number of TCP segments or Java read calls.

A persistent HTTP/1.1 connection typically looks like this:

```text
          A single TCP connection, open across multiple messages
Client                                                       Server
  │   REQUEST #1: start-line + headers + [body]                │
  ├───────────────────────────────────────────────────────────►│
  │   RESPONSE #1: status-line + headers + [body]              │
  │◄───────────────────────────────────────────────────────────┤
  │                                                            │
  │   REQUEST #2: start-line + headers + [body]                │
  ├───────────────────────────────────────────────────────────►│
  │   RESPONSE #2: status-line + headers + [body]              │
  │◄───────────────────────────────────────────────────────────┤
  │                                                            │
  │   Connection: close / server idle timeout / ...            │
  └──────────────────────── close TCP ─────────────────────────┘
```

**A TCP connection is different from an HTTP request**: the connection is the transport channel; requests/responses are messages following HTTP syntax. Ending a request does not automatically mean closing TCP. The same applies to ending a response.

**Connection reuse** means using an already-open connection for multiple requests/responses, while an HTTP client's **connection pool** is the application mechanism that manages multiple connections to reuse them when appropriate. A request might use an idle connection from the pool, or the client might have to create a new connection due to a different origin, a closed old connection, timeout policies, transport errors, or pooling limits.

### HTTP/1.1 Is Not Like HTTP/2

HTTP/1.1 places multiple messages on a single byte stream without stream IDs/multiplexing like HTTP/2. HTTP/1.1 **pipelining** at the protocol level allows a client to send multiple requests before receiving all responses, but the server must return the final responses in the **exact order** the requests were received. It causes application-layer head-of-line blocking and is uncommon in many modern clients.

**Do not treat HTTP/1.1 keep-alive as pipelining**: keep-alive only requires that a connection can carry multiple sequential requests; the lab code in this lesson sends request #2 **after having finished reading response #1**. This is a simple way to observe boundaries and is safe for demos.

## 2. HTTP/1.1 Syntax: Header Section and Body

Conceptually, a request:

```http
POST /echo HTTP/1.1
Host: example.test
Content-Type: text/plain; charset=utf-8
Content-Length: 5

hello
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8
Content-Length: 5

HELLO
```

**In actual wire bytes**, HTTP/1.1 lines are separated by `\r\n` (CRLF), and there is an **empty CRLF line** terminating the header section. The code fences shown above are just for readability; when sending over raw TCP, you must ensure exact CRLF syntax and encoding. `Content-Length: 5` means there are exactly **5 octets of message body** after the blank line, not "read until the next blank line".

Actual structure:

```text
Request:
  request-line CRLF
  *(header-field CRLF)
  CRLF
  [message-body determined by framing rules]

Response:
  status-line CRLF
  *(header-field CRLF)
  CRLF
  [message-body determined by framing rules]
```

HTTP header field names are **case-insensitive**. In the demo code below, the parser converts header names to lowercase for comparison. Do not treat a blank line **inside the body** as the end of the body: the body can contain arbitrary bytes, from JSON, binary images, and compressed data to CRLF characters.

### Content, Message Body, and Transfer Coding

- **HTTP message body**: the octets on the wire after the header section, if any; framed according to HTTP/1.1 rules.
- **Content**: the information carried by the request/response according to HTTP semantics; this may differ from the message body if transfer coding is used.
- **Content-Encoding** such as `gzip`: belongs to content/representation encoding; it is not the rule for determining where an HTTP message ends on the connection.
- **Transfer-Encoding** such as `chunked`: a transport encoding mechanism, where chunked has an **explicit end marker**.
- **Connection**: controls per-connection options; it does not turn a byte stream into message frames.

A response can be `200 OK` without application content (e.g., `Content-Length: 0`), or a response by method/status **must not have an HTTP message body**. Do not infer that "every 200 status response has a body longer than zero".

## 3. Persistent Connections and `Connection: close`

RFC 9112 specifies that **HTTP/1.1 is persistent by default** unless there is a directive or condition requiring the connection to close. Conceptually:

```http
GET /resource HTTP/1.1
Host: example.test
```

There is no need to add `Connection: keep-alive` to enable persistence in HTTP/1.1. The `Connection: keep-alive` header is often seen for compatibility/implementation characteristics, but it is **not a mandatory condition** for persistent HTTP/1.1.

If you want to signal not to reuse the connection after the current response:

```http
GET /resource HTTP/1.1
Host: example.test
Connection: close
```

or the server side returns:

```http
HTTP/1.1 200 OK
Connection: close
Content-Length: 2

OK
```

Upon receiving the `close` option, the connection is no longer considered persistent after the corresponding response. The client **must not continue sending new requests on that connection**. The server may have a policy to close idle connections even without `Connection: close`; no client should assume a connection can stay open indefinitely.

### 3.1. Differences Between HTTP/1.1 and HTTP/1.0

| Characteristic | HTTP/1.1 | HTTP/1.0 |
|---|---|---|
| Default persistence | Yes, unless close directive/condition | Not by default |
| To stop reuse | `Connection: close` | Closing is the default behavior without negotiation |
| `Connection: keep-alive` | Not needed to enable by default | Legacy keep-alive mechanism, depends on both sides |
| Body framing suitable for reuse | Length-delimited or transfer-delimited | More limited; close-delimited historically common |
| Proxy compatibility | Must comply with HTTP/1.1 and hop-by-hop fields | Must not maintain a persistent connection with an HTTP/1.0 client per RFC 9112 §9.3 |

`Connection: close` is an **HTTP protocol option**, not a Java `Socket.close()` command executed the moment the parser reads the header. The current message still needs to be transmitted/read according to the rules. A response with a complete `Content-Length`, `Connection: close`, and then a TCP FIN is valid.

### 3.2. The Real Condition for Safe Reuse

Both sides must **know the exact end of the previous message**. RFC 9112 §9.3 requires:

- **The server** must read the entire request body or close the connection after sending the response; it must not under-read bytes of request #1 and then interpret those bytes as request #2.
- **The client** wanting to reuse the same connection must read the entire response body of response #1 (or handle it according to the client library contract to safely release the connection).
- Every message on a persistent connection must have a **self-defined length** — not relying on closing the connection to determine the end of the body.

This is the most important relationship in this lesson: **keep-alive is only feasible when framing does not depend on EOF**.

## 4. Body Length Decision Table per RFC 9112 §6.3

HTTP/1.1 has **precedence** rules; you cannot simply write "if `Content-Length` is present, read that exact amount" for every response. You must consider **the corresponding request's method, response status, Transfer-Encoding, and Content-Length**.

| Evaluation Order | Condition | Message Body Boundary | Reuse Conclusion |
|---|---|---|---|
| 1 | Response to `HEAD`, or status `1xx`, `204`, `304` | Ends immediately after the blank line ending headers; **no message body** | Can continue parsing the next appropriate message on the connection |
| 2 | `2xx` response to `CONNECT` | After headers, connection switches to a **tunnel**, no longer normal HTTP message framing | Do not parse tunnel bytes as the next HTTP response |
| 3 | Both `Transfer-Encoding` and `Content-Length` present | TE **takes precedence** per RFC, but this is suspicious framing and should not be accepted | Should be treated as an error; for such requests, RFC requires the server to close after the response |
| 4 | `Transfer-Encoding` present with **final coding = chunked** | Read and decode chunks up to last-chunk, trailers, and blank line | Has a definite endpoint; can reuse if other conditions allow |
| 5 | `Transfer-Encoding` present, but **final coding is not chunked** | Response: read until server closes; request: cannot be reliably determined, server must return `400` and close | Response cannot be reused; request must be rejected/closed |
| 6 | No TE, valid `Content-Length` present | Exactly **n octets** per the length field | Can reuse once fully read |
| 7 | Request not in the above branches, no TE/CL | Body length **is zero** | Can parse the next request |
| 8 | Remaining response without length-defining framing | Body ends by **closing the connection** | Cannot reuse that connection for the next message |

This is the true order of applying **framing**, not a simplified table of "whether every status has content or not". The following sections explain each branch, special cases, and security reasons.

### Rules to Remember Immediately

- For a **request** without `Content-Length`/`Transfer-Encoding`, **do not wait for EOF** to determine the request body: the body length is 0.
- For a normal **response** without CL/TE that is allowed to have a body, you must read until the peer closes; there is no longer an opportunity for reuse.
- For **HEAD/1xx/204/304 responses**, do not read a body even if some content-length-related headers are present. They are higher-precedence exceptions.
- For **2xx CONNECT**, after the headers are tunnel bytes, which must not be interpreted by the HTTP parser as a sequence of normal responses.
- **TE + CL coexisting is a dangerous signal**. Do not build production systems with two parsers that interpret them differently.

## 5. `Content-Length`: Exact Byte Count, Not String Length

`Content-Length: n` announces the **message body size in octets**, not the number of Java code points or UTF-16 code units.

Example:

```java
String text = "Chào";
byte[] bytes = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);
System.out.println("Java String length: " + text.length());
System.out.println("UTF-8 byte count: " + bytes.length);
```

This is an **illustrative code snippet**, without a standalone `main` class. For `Chào`, the number of UTF-16 code units and the number of UTF-8 bytes differ. If constructing a raw HTTP response, you must use `bytes.length` for `Content-Length`, not `text.length()`.

### 5.1. Reading Exactly n Bytes of Body

If the headers specify `Content-Length: 5`, then the parser must:

```text
... CRLF
Content-Length: 5 CRLF
CRLF
HELLO
[next HTTP message bytes if connection remains persistent]
```

For a body of length 5, you must read **exactly 5 bytes**. If the first `read` receives only 2 and the next receives 3, combining both gives the complete body. You must not treat `read` returning less than the buffer length as the end of the body. Once 5 bytes are read, the next byte **does not** belong to this body.

Java 17 has `InputStream.readNBytes(int)`, which returns up to `n` bytes, or fewer if EOF is reached. You must compare the result:

```java
// Illustrative excerpt: 'in' is an InputStream, 'length' has been
// validated within the application's safe limits.
byte[] body = in.readNBytes(length);
if (body.length != length) {
    throw new java.io.EOFException("Incomplete HTTP body");
}
```

This is an **illustrative snippet**, not a complete HTTP/1.1 parser; it does not yet handle TE, no-body statuses, conflicting headers, or large sizes. For large bodies, you should read using a small buffer/streaming rather than allocating an arbitrary array based on a peer-supplied length.

### 5.2. Do Not Read More Than n Bytes

On a persistent connection, immediately following the 5 bytes could be `HTTP/1.1 ...` of the next response (in a pipeline) or when the server starts sending another message. If the parser over-reads and discards the excess, it can cause **protocol desynchronization**.

If using `BufferedInputStream`, the buffer may prefetch multiple bytes from TCP, **but they must be kept within the same parser/input wrapper**. Prefetching is not wrong when buffer state is preserved; what is wrong is reading headers with a `BufferedReader` and then suddenly reading the body directly from `Socket.getInputStream()`: the reader may have already buffered bytes of the body/next message in its own internal buffer.

### 5.3. Empty Body Does Not Need EOF

A response with `Content-Length: 0` ends immediately after the headers. If the client calls `readAllBytes()` on the raw socket to "read the entire response", it ends up waiting for **connection EOF**; the server keeps the connection open for reuse, causing the program to block indefinitely. The right rule is to read exactly `0` bytes in that case.

### 5.4. Invalid Lengths

A `Content-Length` value that is not a valid decimal number, is too large, negative, or has conflicting CL lines is a **framing error**; you should not try to "guess" and continue reusing. HTTP specs have some situations where a list of **identical** repeated CL values is allowed to be normalized, but the demo parser in this lesson **deliberately rejects duplicates** to avoid ambiguity. In real production systems, let a trusted HTTP library handle standard cases and cross-proxy/server discrepancies; do not write a raw parser for untrusted data.

## 6. `Transfer-Encoding: chunked` and last-chunk

When the body size is not known in advance or streaming is desired, an HTTP/1.1 sender can use the `chunked` transfer coding, in which each chunk consists of:

```text
<chunk-size in hex>[;extensions] CRLF
<exact chunk-size bytes> CRLF
...
0[;extensions] CRLF
[trailer-field CRLF]*
CRLF
```

**The message body does not end the moment an arbitrary `0` line is seen in the payload**; the parser must be in the exact state of reading a **chunk-size line**, decoding the hex 0, and then continuing to read the **trailer section up to the blank line**. Only then can the first byte position of the next HTTP message be determined.

Example of a valid chunked response:

```http
HTTP/1.1 200 OK
Transfer-Encoding: chunked

4
Wiki
5
pedia
0
X-Demo: yes

```

This is a **line-by-line** representation. On the wire are `\r\n` sequences, and sizes `4` and `5` are in bytes. After decoding, the content is `Wikipedia`. `X-Demo: yes` after the last-chunk is an illustrative trailer, not part of the 9 bytes of content.

### 6.1. `chunked` Is Not `Content-Length`

Do not emit `Content-Length` simultaneously with `Transfer-Encoding`. The RFC states that a sender must not do so; the risk of proxy/server parsers interpreting boundaries differently can lead to **HTTP request smuggling** or response splitting.

When `Transfer-Encoding` is present and **chunked is the final coding**, the message boundary is the zero-sized chunk/trailer terminator, not EOF. If a header like `Transfer-Encoding: gzip, chunked` appears, chunked framing is still based on the final coding, and then earlier transfer codings are decoded in the appropriate order. The chunk parser demo in the lab section only accepts exact `Transfer-Encoding: chunked` and rejects other codings.

### 6.2. Do Not Confuse with `Content-Encoding: gzip`

`Content-Encoding: gzip` means the content is compressed. `Content-Length` can still be used to frame the number of **compressed bytes on the wire**, or `transfer-encoding: chunked` can be used for transport. Do not infer "body ends when the gzip decoder stops" instead of HTTP framing. The parser must handle the exact message length first; the library can provide a decoding stream afterward.

### 6.3. Trailers Are Not a New Request

HTTP chunk trailers appear **after the zero-sized chunk** and before the final blank line. Avoid stopping the parser as soon as `0\r\n` is seen without reading all trailers. Otherwise, the remaining trailer bytes could be mistaken for a new HTTP message on the persistent connection.

Some fields in trailers have specific restrictions; applications must not by default use unvalidated trailers to override fields that determine routing, body framing, or security. The goal here is **accurately determining boundaries**.

## 7. Responses Without an HTTP Message Body

This is a case that breeds many bugs even when `Content-Length` or `Transfer-Encoding` appears to be present. RFC 9112 gives **method/status** precedence over framing headers:

| Response | Has HTTP Message Body? | Response Endpoint |
|---|---|---|
| Response to `HEAD` | No | Immediately after the blank line ending headers |
| Any `1xx` response (e.g. `100 Continue`) | No | Immediately after headers; a final response may still follow |
| `204 No Content` | No | Immediately after headers |
| `304 Not Modified` | No | Immediately after headers |
| `2xx` to `CONNECT` | Not a normal HTTP body; switches to tunnel | Immediately after headers, subsequent bytes belong to the tunnel |
| `200 OK` to `GET` | May have a body or 0-length body | Uses CL/TE/close per the corresponding rules |

**HEAD with Content-Length:** a server may provide `Content-Length` indicating the size of the representation a corresponding GET request would return, but **must not send a message body** in the HEAD response itself. If the client sees `Content-Length: 1048576` after HEAD and tries to read 1,048,576 bytes on a persistent connection, it may block or swallow another message.

**`304 Not Modified`:** may also include some metadata about the representation, but the response body is still absent. `204` similarly has a zero-length message body per HTTP rules. `1xx` is not a final response, so the client must continue reading the corresponding terminating response in the request lifecycle.

**`CONNECT 2xx`:** a proxy agrees to establish a tunnel (commonly used for TLS over an HTTP proxy). Bytes after the headers of a successful response become **tunnel traffic**, not a second HTTP/1.1 response. `Connection: Upgrade`/`101 Switching Protocols` also changes the protocol after headers per the corresponding contract, requiring a separate parser; do not continue treating upgraded bytes as normal HTTP/1.1.

### Do Not Read "Until Server Closes" for Every Status

If a connection is persistent and the client calls `readAllBytes()` after a `204` response, it may wait indefinitely; the server has not closed because it expects to reuse the connection for another request. Properly, `204` ends immediately after the headers.

If a parser applies `Content-Length` **before** status/method, it may treat a no-body response as a message with a body and lose synchronization. For special statuses, **the order of framing rules** is a core requirement.

## 8. Responses Terminated by Closing the Connection

If a response allowed to have a body **has neither `Transfer-Encoding` nor `Content-Length`**, the body boundary is typically determined by **EOF when the server closes the connection**.

```http
HTTP/1.1 200 OK
Content-Type: text/plain
Connection: close

This body ends only when the peer closes its output.
```

This is an example of a close-delimited response; there is **no** other message-end marker in the headers. If the TCP connection does not close, the client cannot be sure it has read the entire body. Therefore, reuse on **that same connection** is impossible: the very EOF that marks the end of the response means the connection can no longer be used to send the next request.

Another weakness: if the network connection is dropped abruptly, it is very hard to distinguish a **truly complete body** from a **truncated body** when framing relies only on closing the connection. RFC 9112 recommends senders use length-delimited/chunked when possible.

**Requests do not have a close-delimited mode.** If a request does not declare CL/TE per the rules, the body length is **0**, not "wait for the client to close output". A server calling `readAllBytes()` for every HTTP request will easily deadlock: the client holds the connection open to receive the response while the server waits for EOF.

### Deadlock Example

```text
Client: POST /demo + Content-Length: 5 + "hello"
        -> waits for response, keeps connection persistent

Buggy server: reads entire Socket InputStream until EOF
              -> waits for client to close connection

Both wait on each other even though all 5 bytes have arrived.
```

The fix: the server parses the headers, reads **exactly 5 bytes**, and then produces the response. Do not "wait a little longer", increase buffer size, or add `Thread.sleep()` to solve a protocol framing bug.

## 9. Java 17+: Two Requests/Responses on **One TCP Connection**

The following standalone example uses `java.net.ServerSocket` and `Socket` on loopback to **directly observe HTTP/1.1 bytes**. The server calls `accept()` **only once**, then parses two sequential requests on the same socket:

1. Client sends `POST /echo` with `Content-Length: 5` and body `hello`.
2. Server replies `HELLO` with `Content-Length: 5` and `Connection: keep-alive`.
3. Client **reads exactly 5 response bytes** and then sends `GET /status` (no `Content-Length`, request body length 0).
4. Server replies `OK` with `Content-Length: 2` and `Connection: close`, then closes the accepted socket.
5. Client reads exactly 2 bytes and observes EOF.

**This is a limited demo parser**, supporting only start-line, ASCII headers, single `Content-Length`, body up to 1,024 bytes, and **rejecting Transfer-Encoding**. Do not use this code as-is for a public HTTP server; a production HTTP parser has many syntax rules, limits/timeouts/security checks that the example does not handle.

**File `Http11KeepAliveDemo.java`:**

```java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public class Http11KeepAliveDemo {
    private record Message(String firstLine, byte[] body) {}

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream data = new ByteArrayOutputStream();
        while (true) {
            int b = in.read();
            if (b == -1) throw new EOFException("Unexpected EOF in header");
            if (b == '\r') {
                if (in.read() != '\n') throw new IOException("Expected CRLF");
                return data.toString(StandardCharsets.US_ASCII);
            }
            if (b == '\n' || data.size() >= 8192)
                throw new IOException("Invalid or oversized header line");
            data.write(b);
        }
    }

    private static Message readMessage(InputStream in) throws IOException {
        String first = readLine(in);
        int length = 0;
        boolean foundLength = false;
        for (int i = 0; i < 32; i++) {
            String header = readLine(in);
            if (header.isEmpty()) {
                byte[] body = in.readNBytes(length);
                if (body.length != length) throw new EOFException("Short body");
                return new Message(first, body);
            }
            int colon = header.indexOf(':');
            if (colon <= 0) throw new IOException("Bad header");
            String name = header.substring(0, colon).toLowerCase(Locale.ROOT);
            String value = header.substring(colon + 1).trim();
            if (name.equals("transfer-encoding"))
                throw new IOException("Chunked not supported by this demo");
            if (name.equals("content-length")) {
                if (foundLength || !value.matches("[0-9]+"))
                    throw new IOException("Ambiguous Content-Length");
                try { length = Integer.parseInt(value); }
                catch (NumberFormatException e) { throw new IOException("Too large", e); }
                if (length > 1024) throw new IOException("Body exceeds demo limit");
                foundLength = true;
            }
        }
        throw new IOException("Too many headers");
    }

    private static void send(OutputStream out, String start, String extra,
                             String body) throws IOException {
        byte[] payload = body.getBytes(StandardCharsets.UTF_8);
        String head = start + "\r\n" + extra
                + "Content-Length: " + payload.length + "\r\n\r\n";
        out.write(head.getBytes(StandardCharsets.US_ASCII));
        out.write(payload);
        out.flush();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            InetAddress loopback = InetAddress.getLoopbackAddress();
            listener.bind(new InetSocketAddress(loopback, 0));
            listener.setSoTimeout(4000);

            Future<List<String>> server = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(4000);
                    InputStream in = peer.getInputStream();
                    OutputStream out = peer.getOutputStream();
                    Message first = readMessage(in);
                    if (!first.firstLine().equals("POST /echo HTTP/1.1"))
                        throw new IOException("Unexpected first request");
                    String body = new String(first.body(), StandardCharsets.UTF_8);
                    send(out, "HTTP/1.1 200 OK", "Connection: keep-alive\r\n",
                            body.toUpperCase(Locale.ROOT));

                    Message second = readMessage(in);
                    if (!second.firstLine().equals("GET /status HTTP/1.1"))
                        throw new IOException("Unexpected second request");
                    send(out, "HTTP/1.1 200 OK", "Connection: close\r\n", "OK");
                    return List.of(
                            "TCP connections accepted: 1",
                            "Server first: " + first.firstLine() + " / " + body,
                            "Server second: " + second.firstLine()
                                    + " / body-bytes=" + second.body().length);
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(loopback, listener.getLocalPort()), 4000);
                client.setSoTimeout(4000);
                InputStream in = client.getInputStream();
                OutputStream out = client.getOutputStream();

                send(out, "POST /echo HTTP/1.1",
                        "Host: localhost\r\nConnection: keep-alive\r\n", "hello");
                Message first = readMessage(in);

                out.write(("GET /status HTTP/1.1\r\nHost: localhost\r\n"
                        + "Connection: close\r\n\r\n")
                        .getBytes(StandardCharsets.US_ASCII));
                out.flush();
                Message second = readMessage(in);
                int eof = in.read();

                for (String line : server.get(5, TimeUnit.SECONDS))
                    System.out.println(line);
                System.out.println("Client response1: "
                        + new String(first.body(), StandardCharsets.UTF_8));
                System.out.println("Client response2: "
                        + new String(second.body(), StandardCharsets.UTF_8));
                System.out.println("EOF after second response: " + eof);
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
```

**Compile and run with JDK 17 or newer:**

```bash
javac --release 17 -encoding UTF-8 Http11KeepAliveDemo.java
java Http11KeepAliveDemo
```

**Verified stdout from TCP loopback run:**

```text
TCP connections accepted: 1
Server first: POST /echo HTTP/1.1 / hello
Server second: GET /status HTTP/1.1 / body-bytes=0
Client response1: HELLO
Client response2: OK
EOF after second response: -1
```

**Key analysis:**

- `listener.accept()` happens **only once**. Both requests are read via `readMessage(in)` on the same `peer.getInputStream()`. This is a clear demonstration that one TCP connection can carry multiple sequential HTTP/1.1 requests/responses.
- `POST` sends the body `hello` and the server reads exactly 5 bytes; the end-of-request signal is not based on EOF.
- The first response has `Content-Length: 5`; the client stops reading the body after 5 bytes and immediately sends the second GET. The server is still waiting for the GET on the same socket, with no deadlock.
- The second GET request has no CL/TE, so `readMessage` sets the body length to 0 according to the rule for **requests**.
- The server returns response #2 of 2 bytes and signals `Connection: close`. After the server exits `try`, the TCP socket closes; the client observes `read()==-1`.
- The 4-second timeout prevents the experiment from hanging indefinitely if loopback behaves abnormally. When the environment disallows TCP loopback or is too slow, the program may throw an exception; the stdout above is the verified result of a successful run.
- The parser reads each header line by CRLF **without using two wrappers with different read-ahead buffers**. That keeps the body/next message bytes in the exact stream, but **does not mean the parser is strict enough for the Internet**.
- The number of headers and body size are bounded to prevent unbounded allocation; the example does not implement full security checks, proxy routing, Host validation, chunked, informational responses, hop-by-hop headers, or close-delimited responses.

The practical takeaway is **you must read the entire message** before reusing a connection, without needing to close TCP after each request.

## 10. Java 17+: Decoding Chunked and Reading the Next Response

The second experiment does not need to open a socket; it uses `ByteArrayInputStream` containing **two consecutive HTTP responses on the same byte stream**. This is a deterministic way to test framing logic before adding networking factors.

Response #1 has `Transfer-Encoding: chunked`, two chunks `Wiki` and `pedia`, followed by the last-chunk, trailer `X-Demo: yes`, and a blank line. Response #2 has `Content-Length: 2` with body `OK`. The parser must stop response #1 **right after the trailer terminator** and begin reading the status line of response #2 immediately afterward.

**File `Http11ChunkedBoundaryDemo.java`:**

```java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class Http11ChunkedBoundaryDemo {
    private record Message(String status, byte[] body) {}

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        while (true) {
            int b = in.read();
            if (b == -1) throw new EOFException("Incomplete line");
            if (b == '\r') {
                if (in.read() != '\n') throw new IOException("Expected CRLF");
                return bytes.toString(StandardCharsets.US_ASCII);
            }
            if (b == '\n' || bytes.size() >= 8192)
                throw new IOException("Malformed line");
            bytes.write(b);
        }
    }

    private static byte[] exact(InputStream in, int count) throws IOException {
        byte[] bytes = in.readNBytes(count);
        if (bytes.length != count) throw new EOFException("Incomplete body");
        return bytes;
    }

    private static byte[] chunks(InputStream in) throws IOException {
        ByteArrayOutputStream decoded = new ByteArrayOutputStream();
        while (true) {
            String line = readLine(in);
            String token = line.split(";", 2)[0].trim();
            if (!token.matches("[0-9a-fA-F]+"))
                throw new IOException("Invalid chunk size");
            long size = Long.parseLong(token, 16);
            if (size > 1024 - decoded.size())
                throw new IOException("Body exceeds demo limit");
            if (size == 0) {
                for (int i = 0; i < 32; i++) {
                    String trailer = readLine(in);
                    if (trailer.isEmpty()) return decoded.toByteArray();
                    if (trailer.indexOf(':') <= 0)
                        throw new IOException("Invalid trailer field");
                }
                throw new IOException("Too many trailers");
            }
            decoded.write(exact(in, (int) size));
            if (in.read() != '\r' || in.read() != '\n')
                throw new IOException("Missing chunk terminator");
        }
    }

    private static Message readResponse(InputStream in) throws IOException {
        String status = readLine(in);
        String transfer = null;
        Integer contentLength = null;
        for (int i = 0; i < 32; i++) {
            String header = readLine(in);
            if (header.isEmpty()) {
                if (transfer != null && contentLength != null)
                    throw new IOException("Ambiguous framing");
                if (transfer != null) {
                    if (!transfer.equalsIgnoreCase("chunked"))
                        throw new IOException("Unsupported transfer coding");
                    return new Message(status, chunks(in));
                }
                if (contentLength == null)
                    throw new IOException("Length required in this demo");
                return new Message(status, exact(in, contentLength));
            }
            int colon = header.indexOf(':');
            if (colon <= 0) throw new IOException("Malformed header");
            String name = header.substring(0, colon).toLowerCase(Locale.ROOT);
            String value = header.substring(colon + 1).trim();
            if (name.equals("transfer-encoding")) {
                if (transfer != null) throw new IOException("Duplicate TE");
                transfer = value;
            }
            if (name.equals("content-length")) {
                if (contentLength != null || !value.matches("[0-9]+"))
                    throw new IOException("Bad Content-Length");
                try { contentLength = Integer.parseInt(value); }
                catch (NumberFormatException e) { throw new IOException("Too large", e); }
                if (contentLength > 1024) throw new IOException("Body too large");
            }
        }
        throw new IOException("Too many headers");
    }

    public static void main(String[] args) throws Exception {
        String stream =
                "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                + "4\r\nWiki\r\n5\r\npedia\r\n"
                + "0\r\nX-Demo: yes\r\n\r\n"
                + "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK";
        try (InputStream input = new ByteArrayInputStream(
                stream.getBytes(StandardCharsets.US_ASCII))) {
            Message first = readResponse(input);
            Message second = readResponse(input);
            System.out.println("First body: "
                    + new String(first.body(), StandardCharsets.UTF_8));
            System.out.println("Second status: " + second.status());
            System.out.println("Second body: "
                    + new String(second.body(), StandardCharsets.UTF_8));
            System.out.println("Bytes remaining: " + input.available());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 Http11ChunkedBoundaryDemo.java
java Http11ChunkedBoundaryDemo
```

**Verified stdout:**

```text
First body: Wikipedia
Second status: HTTP/1.1 200 OK
Second body: OK
Bytes remaining: 0
```

Explanation:

1. `readResponse` reads the status line and header section. In the demo, if both `Transfer-Encoding` and `Content-Length` appear, the parser **rejects** it rather than trying to pick an ambiguous value. This is a safe policy for the example, even though the RFC describes a precedence order when received.
2. For `chunked`, `chunks` reads the hex size, the exact number of data bytes, the CRLF after the chunk, and loops. When size is `0`, it reads **through the entire trailer section**; only after the final blank line does it return the content.
3. The stream still has response #2 intact. The parser reads `Content-Length: 2` accurately and returns `OK`; finally `available()==0` in **this ByteArrayInputStream** verifies that all test data has been consumed. **Do not** use `available()==0` on a network socket to conclude that an HTTP message has ended.
4. This is an **educational parser**: 1,024-byte limit, maximum 32 headers/trailers, supports only a single `Transfer-Encoding: chunked` or a single CL, and does not handle all statuses/methods/transfer codings/syntax cases. `Long.parseLong` with an extremely large chunk-size value may error; production needs normalization, overflow handling, extension/trailer policies, and stricter validation.
5. The content buffer after decoding is converted to a UTF-8 string when printed; **chunk byte count** is measured before converting to a string, never using character count to read the payload.

This example proves that the **zero-sized chunk + trailer terminator**, not TCP EOF, determines the point where the next HTTP message can begin.

## 11. Java 17+: Checking the HEAD, 1xx, 204, 304, and CONNECT Exceptions

The following small program does not parse sockets; it isolates the **decision branch** for whether a response belongs to the **no HTTP message body** group per RFC 9112 §6.3.

**File `Http11NoBodyRulesDemo.java`:**

```java
public class Http11NoBodyRulesDemo {
    static boolean hasHttpMessageBody(String requestMethod, int status) {
        if (requestMethod.equals("HEAD")) return false;
        if (status >= 100 && status < 200) return false;
        if (status == 204 || status == 304) return false;
        if (requestMethod.equals("CONNECT")
                && status >= 200 && status < 300) return false;
        return true;
    }

    public static void main(String[] args) {
        System.out.println("HEAD 200 HTTP body: "
                + hasHttpMessageBody("HEAD", 200));
        System.out.println("GET 204 HTTP body: "
                + hasHttpMessageBody("GET", 204));
        System.out.println("GET 304 HTTP body: "
                + hasHttpMessageBody("GET", 304));
        System.out.println("GET 200 HTTP body: "
                + hasHttpMessageBody("GET", 200));
        System.out.println("CONNECT 200 HTTP body: "
                + hasHttpMessageBody("CONNECT", 200));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 Http11NoBodyRulesDemo.java
java Http11NoBodyRulesDemo
```

**Verified stdout:**

```text
HEAD 200 HTTP body: false
GET 204 HTTP body: false
GET 304 HTTP body: false
GET 200 HTTP body: true
CONNECT 200 HTTP body: false
```

**Limitation of this boolean table:** `true` only means **not belonging to the special no-body/tunnel groups being checked**, not that the body is guaranteed to have bytes. A GET 200 can have `Content-Length: 0`. A complete parser must also parse the status/method matched against the pending request, support TE/CL/close branches in order, handle 101 protocol upgrade, and obey other semantic requirements such as `205 Reset Content` not generating content.

Do not use this boolean function as a complete HTTP parser; it is only a reminder that **method/status are evaluated before header lengths**.

## 12. Using Java 17's `java.net.http.HttpClient` for Proper Reuse Responsibilities

In regular applications, **do not build a raw TCP parser** like the three examples. Java 17 provides `java.net.http.HttpClient`, which supports HTTP/1.1 and HTTP/2, handling HTTP message framing, connection pooling, and many protocol aspects.

Usage pattern:

```java
// Illustrative snippet, requires importing java.net.URI;
// java.net.http.HttpClient, HttpRequest, HttpResponse.
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(java.time.Duration.ofSeconds(3))
        .build();

HttpRequest first = HttpRequest.newBuilder(
        URI.create("https://example.com/status"))
        .timeout(java.time.Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> firstResult =
        client.send(first, HttpResponse.BodyHandlers.ofString());

HttpResponse<String> secondResult =
        client.send(first, HttpResponse.BodyHandlers.ofString());
```

This is a **non-standalone illustrative snippet**: it requires the noted imports, exception/business-status checks, and a genuinely suitable endpoint. Do not run tests against public endpoints just to verify reuse in this lesson; the raw loopback demo in the previous section is a more deterministic verification.

Implications:

- **Reusing the same `HttpClient` instance** for multiple requests is how you allow the connection pool to operate when possible. Creating a new `HttpClient.newHttpClient()` on every request can defeat reuse opportunities.
- `.version(HTTP_1_1)` requests using HTTP/1.1 for this example; do not interpret HTTP/2 behavior as identical to HTTP/1.1.
- `BodyHandlers.ofString()` consumes the body into a string and gives you a completed result; with streaming handlers like `ofInputStream()`, the application must **read completely or close the stream properly** to avoid holding resources/connections stuck.
- The client library handles `Content-Length`, `chunked`, and no-body cases under supported conditions. You **do not** need `readAllBytes()` on a raw socket for an HTTP response.
- **There is no guarantee that "two `send` calls will definitely use the same TCP connection".** The pool may open a new connection due to server close, idle timeout, TLS/proxy configuration, different origin, retries, or internal policies.
- Connection reuse and **HTTP caching** are two different concepts. A cached response can avoid sending a network request, whereas an uncached request can still use an already-open TCP connection.

### Connection Reuse Does Not Make Requests Idempotent

If a client sends a state-changing POST, times out, and the application retries, not receiving a response **does not prove the server did not process it**. Using a new or old connection does not solve duplicate execution. For operations with side effects, there must be a request ID/idempotency key and appropriate server-side logic when the API has a retry contract. Retry only when you know the operation is safe or an anti-duplicate mechanism is in place.

## 13. Framing and Security: Avoiding Request Smuggling, Desync, and DoS

HTTP/1.1 framing is not just about performance; it is a **trust boundary** between clients, reverse proxies, load balancers, and backends. When two parsers understand **different request lengths**, leftover bytes can be interpreted as a new unintended request. This is a form of **HTTP request smuggling/desynchronization**.

### 13.1. Signals That Must Be Handled Consistently

- `Content-Length` malformed, negative, exceeding limits, too long, or unrepresentable as a number.
- Multiple `Content-Length` headers with inconsistent values.
- `Transfer-Encoding` and `Content-Length` appearing together.
- `Transfer-Encoding` whose final coding is not `chunked` in a request.
- Invalid hex chunk size, missing CRLF after a chunk, unterminated last-chunk/trailer, or total bytes exceeding limits.
- Header line not properly terminated with CRLF, header folding/obs-fold not handled under a consistent policy, or request line containing invalid bytes.
- Actual body shorter than `Content-Length` when the peer closes or times out: the message is **incomplete** and must close the connection/fail rather than be treated as a successful response.
- Server sends a response without having read the entire request body, yet reuses the connection: remaining bytes can become another request.

**A dangerous design pattern:** proxy A prioritizes `Transfer-Encoding: chunked`, while backend B prioritizes `Content-Length`. Both sides split the stream into messages at different positions; you should not send malformed HTTP to "probe" systems outside authorized scope. When framing inconsistencies are found in systems you manage, fix the parser/library/proxy, align versions, reject ambiguous messages, and close the connection appropriately.

### 13.2. What Does the RFC Say About TE + CL?

RFC 9112 states that TE **takes precedence for message length** when both are present, while warning that this is a case that should be treated as an error. A server **may reject** a request containing both; if it still processes according to TE, the server **must close the connection after the response** to reduce the chance of desync. An intermediary that chooses to forward must remove the received CL and process TE per the rules before forwarding.

The safest design rule for your application: **never intentionally send both headers** and do not write a parser that guesses how to resolve conflicting messages. Modern HTTP libraries, reverse proxies, and backends must be consistent in normalization and limits.

### 13.3. Resource Limits

A production parser needs limits on total header bytes, number of fields, length of each field, body bytes, chunk count, trailer bytes, time to receive headers, and total request time. If a peer sends `Content-Length: 999999999999999999`, do not try to allocate a buffer of that size. If a client sends bytes very slowly, a deadline is needed against resource exhaustion, not just a timeout between individual reads.

### 13.4. EOF and Timeout Are Two Different Cases

- `InputStream.read() == -1`: the other end has closed its sending side, after all bytes before EOF have been read.
- `SocketTimeoutException`: within the wait interval there was insufficient progress to read; **does not by itself mean the message has ended**.
- `IOException`/`SocketException`: I/O error; the message may be truncated.
- For close-delimited responses, EOF can serve as the protocol boundary, but it does not completely eliminate the risk of partial content loss on connection errors.
- For `Content-Length` or `chunked`, if the connection closes before reaching the complete boundary, that is an **incomplete message** and must not be turned into a successful response.

## 14. Observing and Debugging HTTP/1.1 Persistent Connections

### 14.1. Do Not Treat `write()`/`read()` Counts as Message Counts

TCP can split/coalesce bytes depending on buffers and scheduling. A 10 KB response may be read in multiple parts; two pipelined responses may sit in the same network buffer. Proper observation requires **header framing, request ID/timing, and parser state**, not "how many bytes the first read received".

### 14.2. Symptom Matrix

| Symptom | Priority Check | Next Evidence |
|---|---|---|
| Request #1 OK but request #2 hangs | Client/server reading until EOF instead of CL/chunked; connection still open | Check headers and bytes read; is there EOF-waiting logic? |
| Server parses request #2 starting at the last bytes of body #1 | Request #1 was not fully read; wrong CL or lost parser read-ahead | Log expected/actual content length, remaining buffer |
| Client receives corrupted status line on response #2 | Response #1 was under-consumed or over-read | Compare response #1 framing against bytes received |
| A POST is executed twice on connection drop | Business retry without idempotency | Cross-check request ID, commit, and retry policy |
| Very many new TCP connections | Pool not reusing, server sending close, idle timeout, or different origin | Enable client connection logs, server TCP accept count |
| HTTP/1.1 keep-alive still sees TCP FIN | Peer may close idle connections or use `Connection: close` | Cross-check headers, timestamps, and TCP trace |
| HEAD hangs even though response headers arrived | Parser tries to read body per CL | Check request method and status precedence |
| Chunked response "sticks" trailers onto the next message | Parser stops at zero chunk, skipping trailer terminator | Check chunk state machine and trailer parsing |
| Chunked parser receives incomplete data | Check hex chunk size, CRLF, partial read, timeout | Compare wire bytes with parser state |
| `400 Bad Request` when reverse proxy processes | Ambiguous header framing, non-chunked final TE, bad CL | Check proxy/backend validation and error logs, avoid guessing |
| Client holds socket when only wanting one response | `readAllBytes()` on a persistent socket | Use CL/chunk parser or HttpClient |
| Reading text shows corrupted multi-byte characters | Decoding UTF-8 per read fragment, splitting between code points | Assemble body bytes properly before streaming/whole-message decode |
| HTTP client uses a different connection despite same host | Old connection closed/ineligible, library pool policy | Log connection ID/remote port, TLS/proxy, and timeouts |

### 14.3. Minimum Evidence in Logs

```text
timestamp | connectionId | remoteEndpoint | requestId
          | method | path | httpVersion | status
          | transferEncoding | contentLength
          | bodyBytesConsumed | messageComplete
          | connectionCloseRequested | socketClosed
          | elapsedMs | errorClass
```

Do not arbitrarily log bodies or sensitive credentials. With multiple requests on the same TCP connection, **connectionId** will repeat in the logs while **requestId** changes — a positive sign of reuse if requests are properly identified.

### 14.4. How to Inspect Messages with Tools

Example of checking headers using an authorized HTTP/1.1 client:

```bash
curl --http1.1 -v https://example.com/
```

This command can show headers and connection info, but **a single curl invocation does not prove connection reuse**. To verify reuse, the same client session must perform multiple requests to the same origin and inspect connection logs/IDs; policies of curl, proxies, TLS, and servers may differ. Do not use endpoints you do not manage to test malformed protocol errors.

With Wireshark/tcpdump and unencrypted HTTP, you can inspect the request line, headers, and byte stream. With HTTPS, TLS encrypts the data so normal packet captures do not show HTTP headers/bodies in clear text. To debug the HTTP layer, use client/server logging or **authorized** capture/decryption mechanisms.

## 15. Scenarios to Answer Yourself

**Scenario 1.** A client sends `GET / HTTP/1.1` with no CL/TE and keeps the TCP connection open. Should the server wait for EOF to know the request has ended?  
**Answer:** No. The request body length is **0** per RFC 9112 if there are no framing fields and it does not fall into earlier branches. The request ends after the header section.

**Scenario 2.** Response `HTTP/1.1 200 OK` has `Content-Length: 5`; the client reads 2 bytes and waits. Has the response ended?  
**Answer:** No. It must read all **5 octets**; if the socket closes after 2 bytes, the response is incomplete.

**Scenario 3.** The server uses `Transfer-Encoding: chunked`, and after last-chunk `0` sends trailer `X-Demo: yes` followed by a blank line. Can the response be considered finished right after reading the `0` line?  
**Answer:** No. The entire trailer section must be read, including the terminating blank line. Only after that can the next byte belong to the following message.

**Scenario 4.** The server returns a response to `HEAD` with `Content-Length: 1000`. Must the client read 1,000 bytes?  
**Answer:** No. A HEAD response **has no HTTP message body**; the header may describe the representation size corresponding to a GET.

**Scenario 5.** A client receives `HTTP/1.1 204 No Content` without `Content-Length` and keeps the connection. Must it read until EOF?  
**Answer:** No. The message body length is zero and ends immediately after the headers.

**Scenario 6.** A GET 200 response has neither CL nor TE. When does the body end?  
**Answer:** When the server closes its sending side/connection under close-delimited framing. That connection cannot be reused further; the risk of a truncated body is hard to distinguish from a normal end.

**Scenario 7.** A response has both `Transfer-Encoding` and `Content-Length`. Should the client just pick whichever header is easier to process?  
**Answer:** No. While the RFC has a precedence order, this is a suspicious message with desync risk; the application should use a standard parser and handle errors/close appropriately.

**Scenario 8.** A client sends two consecutive requests on an HTTP/1.1 TCP connection and the server finishes processing the second request faster. Can the server return the final response for #2 before #1 in pipelining?  
**Answer:** Not in HTTP/1.1 pipelining response ordering: the server must preserve response order matching the requests. HTTP/2 introduces a multiplexing model with distinct stream identifiers.

**Scenario 9.** `Connection: keep-alive` is absent from an HTTP/1.1 response. Does that mean the connection cannot be reused?  
**Answer:** No. HTTP/1.1 is persistent by default when there is no close condition. However, server/client policies, framing, and connection health still apply.

**Scenario 10.** The same Java `HttpClient` instance sends two requests to one origin. Is it guaranteed to use one TCP connection?  
**Answer:** No. It enables pooling/reuse, without guaranteeing the actual number of connections; instrumentation/observability is needed to confirm.

**Scenario 11.** Calling `InputStream.available()==0` after receiving response headers. Does that mean the body has ended?  
**Answer:** No. `available` only indicates immediate readability, not HTTP framing or EOF. You must apply the body length determination method.

**Scenario 12.** Response #1 has `Content-Length: 4`, but the sender sends `OK` and closes the socket. Should the client treat `OK` as complete?  
**Answer:** No. The received body is only 2 octets, so the message is incomplete and the connection must be handled as an error.

**Scenario 13.** A client wants to send a POST body `Chào` in UTF-8. Should it use `String.length()` as `Content-Length`?  
**Answer:** No. It must measure `text.getBytes(UTF_8).length`, because `Content-Length` is counted in octets.

**Scenario 14.** A reverse proxy keeps `Content-Length` from the client while adding `Transfer-Encoding: chunked` when forwarding. Is this safe?  
**Answer:** No. An HTTP/1.1 sender must not emit both; an intermediary must process/remove the received CL per the RFC when forwarding a message using TE, or reject suspicious messages.

**Scenario 15.** A client has finished receiving `Content-Length: 0` but continues waiting for the socket to close before sending request #2. What is the bug?  
**Answer:** Confusing **HTTP message completion** with **TCP EOF**, losing the benefit of keep-alive and potentially causing a deadlock if the server is still waiting for the next request.

## 16. Application Checklist and Summary

When reviewing an HTTP/1.1 component, check:

- [ ] Clearly distinguish a **TCP connection** from each **HTTP message** on that connection.
- [ ] HTTP/1.1 is persistent by default, but respect `Connection: close` and idle closes from the peer.
- [ ] For responses, evaluate **HEAD/1xx/204/304** and `2xx CONNECT` **before** TE/CL.
- [ ] If `Transfer-Encoding` with final chunked is present, read through **zero-size chunk + trailers + blank line**.
- [ ] If a valid CL is present, read **the exact number of bytes**; excess bytes belong to another message or are a protocol error, never mix them.
- [ ] For requests without CL/TE, body length is **0**, do not wait for EOF.
- [ ] For normal responses without TE/CL, the body is **close-delimited**, so do not continue reusing.
- [ ] Do not intentionally send TE+CL or arbitrarily accept ambiguous framing.
- [ ] Do not use `read()` count, `available()`, `readAllBytes()`, or packet boundaries as HTTP message boundaries.
- [ ] The server reads the entire request body before reusing; the client reads the entire response body before reusing.
- [ ] UTF-8 body size is counted in bytes, not `String.length()`.
- [ ] Have limits on headers/body/trailers/chunks, timeouts, error policies, and incomplete message handling.
- [ ] Use `java.net.http.HttpClient` or a production HTTP library for real services; raw socket parsers are only for learning the protocol.
- [ ] When debugging reuse, track **connection ID** separately from **request ID** and inspect logs on both client and server.
- [ ] Retrying a non-idempotent request requires its own business contract, not reliance on TCP keep-alive.

**Core takeaway:** HTTP/1.1 allows **multiple messages on a single connection** because each message has **explicit termination rules**. Failing to read boundaries accurately either hangs waiting for EOF or loses synchronization and causes serious bugs/security issues. `Content-Length`, `chunked`, and no-body cases are tools for determining **message completion**; `Connection: close` and idle policies are **connection lifecycle** concerns.

### Standards and Java 17 Documentation

- [RFC 9112 — HTTP/1.1, §6 Message Body, §6.3 Message Body Length, §9.3 Persistence](https://www.rfc-editor.org/rfc/rfc9112.html)
- [RFC 9110 — HTTP Semantics, §8.6 Content-Length, status semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [Java 17 `Socket` — TCP streams and SO_TIMEOUT](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Java 17 `InputStream` — `readNBytes`, `readAllBytes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [Java 17 `HttpClient` — version/connection management](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java 17 `HttpResponse.BodyHandlers` — handling and consuming response bodies](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
