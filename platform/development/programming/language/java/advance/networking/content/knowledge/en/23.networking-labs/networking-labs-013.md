# Building a JDK, Protocol, and API Compatibility Matrix for Reproducible Examples

## 1. Purpose and Principles of a Compatibility Matrix

A Java networking example that “works” can mean several different things: **compiles on a given JDK**, **runs on the target runtime**, **actually connects to a peer**, and **negotiates the exact protocol under test**. These are four criteria that must be distinguished when building a compatibility matrix.

For example, `HttpClient.Version.HTTP_2` exists, yet the peer only responds with HTTP/1.1; `SSLContext` lists TLSv1.3 in its supported list, yet the actual handshake uses TLSv1.2; `UnixDomainSocketAddress` code compiles on Java 17, yet cannot bind on a restricted OS; or `--release 8` compiles successfully on JDK 24, yet has never been run on a JVM 8.

This Knowledge article provides a **JDK × protocol × API × evidence compatibility matrix**, accompanied by **four standalone Java programs** tested on loopback/capability:

- `NetworkBaseline8.java`: TCP and UDP echo on `127.0.0.1`, Java 8–compatible source/API.
- `HttpClientCompatibility11.java`: HTTP/1.1 `HttpClient` + `HttpServer`, HTTP/2/WebSocket API capability, supported JSSE TLS list.
- `UnixDomainApi17.java`: checks that the Unix-domain address API can compile targeting Java 17.
- `VirtualThreadApi21.java`: official virtual-thread executor since Java 21.

**Verified experimental scope:** all four sources **compile** with `--release 8/11/17/21` respectively and **run on OpenJDK 24.0.2**. This does **not** prove they have been run on real JVM 8/11/17/21, nor does it prove HTTP/2, WebSocket, or TLS handshake negotiation. The table must honestly record what was actually measured.

## 2. Three Compatibility Layers and One Environment Condition

| Layer | Question | How to Verify | Pitfall to Avoid |
| --- | --- | --- | --- |
| **Source + API** | Does the compiler target have the API and syntax? | `javac --release N`, official API `Since` | Looking at `java -version` and guessing the source target |
| **Class file + runtime** | Does the real runtime run the bytecode and API? | Run `java` on the target version, check exit/exception | Assuming `--release 8` on JVM24 means JVM8 was tested |
| **Protocol negotiated** | Do both sides use the right TCP/UDP/HTTP1.1/HTTP2/TLS version? | Echo bytes, `HttpResponse.version()`, `SSLSession.getProtocol()` | Equating preference configuration with the actual protocol |
| **Environment** | Do OS/JDK vendor/cert/network allow it? | Record metadata, peer config, timeouts, bind address | Attributing every failure to the API or JDK version |

**Compile PASS does not equal Runtime PASS; Runtime PASS does not equal Protocol PASS.** A socket that connects successfully does not automatically carry a valid HTTP request. An HTTP 200 request does not prove HTTP/2 if the response is HTTP/1.1. A TLS provider supporting TLS1.3 does not prove the peer negotiated TLS1.3.

You should separately record the fields `compiler`, `target_release`, `runtime`, `requested_protocol`, `observed_protocol`, `peer`, `OS`, `status`, and `evidence`.

## 3. JDK Compatibility Table by Release Version

Table updated as of **01/11/2026**: Java **27 was released on 15/09/2026**; Java **25 is LTS**. JDK 26 was released on 17/03/2026, JDK25 LTS was released on 16/09/2025. Later versions continue to provide the stable APIs of earlier versions, but security defaults, module images, and actual vendor/build behavior still need to be re-tested.

| JDK Line | Group | Notable Java Networking Milestones | Testing Guidance |
| --- | --- | --- | --- |
| **8** | LTS, 2014 | `Socket`, `ServerSocket`, `DatagramSocket`, `HttpURLConnection`, `SSLSocket`, core NIO | TCP/UDP/HTTP1.1 client baseline; no standard `java.net.http` yet |
| **11** | LTS, 2018 | `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `WebSocket`; JSSE implements TLS 1.3 | HTTP1.1/HTTP2 **client**, WebSocket client, TLS capability |
| **17** | LTS, 2021 | Includes Java 11 APIs and Unix-domain socket APIs available **since Java 16** | Unix-domain address API; separate OS bind/connect test |
| **21** | LTS, 2023 | Virtual threads finalized; `Executors.newVirtualThreadPerTaskExecutor()`, `Thread.isVirtual()` | Executor/virtual thread test, does not change wire protocol |
| **25** | LTS, 16/09/2025 | The baseline APIs above remain valid source | Run regression on the actual JDK25/patch/provider |
| **26** | Non-LTS, 17/03/2026 | The baseline APIs above; additional networking/security changes depending on release | Re-test runtime and protocol negotiation |
| **27** | Non-LTS, 15/09/2026 | The baseline APIs; TLS1.3 enhanced with hybrid post-quantum key exchange | Test handshake/cipher/group with a real peer, do not guess |

JDK 11 includes TLS 1.3 per JEP 332, but **some JDK 8 updates/vendors may backport TLS 1.3**, so do not state “all JDK 8 releases do not support TLS 1.3”. Conversely, a higher release number does not guarantee a specific protocol/cipher is enabled by default; security properties, certificates, and the server determine the handshake.

JDK 9/10 had an incubating HTTP client. **The stable `java.net.http` API in this article chooses JDK11 as the baseline**, avoiding incubating module names so code remains reproducible across JDK versions.

## 4. Protocol × API × Minimum JDK Level Compatibility Table

| Protocol/Capability | Appropriate API | Stable Java Milestone | Peer-Side Condition | Evidence to Mark PASS |
| --- | --- | --- | --- | --- |
| **TCP stream** | `Socket`, `ServerSocket`, `InputStream`, `OutputStream` | **Java 8 or older** | TCP peer or local listener | Connect to exact address/port, exact echo, EOF |
| **UDP datagram** | `DatagramSocket`, `DatagramPacket` | **Java 8 or older** | UDP receiver with deadline | Exact payload/length echo, no timeout |
| **HTTP/1.1 legacy client** | `HttpURLConnection` | **Java 8 or older** | HTTP/1.1 server | Correct status/headers/body |
| **HTTP/1.1 modern client** | `HttpClient`, `HttpRequest`, `HttpResponse` | **Java 11** | Compatible HTTP server | `response.version()==HTTP_1_1` |
| **HTTP/2 client** | `HttpClient.Version.HTTP_2` | **Java 11** | HTTP/2 server and compatible negotiation/ALPN | `response.version()==HTTP_2` |
| **Simple JDK HTTP server** | `com.sun.net.httpserver.HttpServer` / `jdk.httpserver` | **JDK-specific module since Java 9** | HTTP client | Real HTTP/1.1 response, do not infer HTTP/2 server |
| **WebSocket client** | `HttpClient.newWebSocketBuilder()`, `WebSocket` | **Java 11** | RFC6455 WebSocket server | Handshake, frames, receive callbacks, Close |
| **TLS1.2** | `SSLSocket`, `SSLEngine`, `SSLContext` | **Java 8 baseline** | Certificate/trust + TLS peer | `SSLSession.getProtocol()==TLSv1.2` |
| **TLS1.3** | JSSE `SSLContext`, `SSLSession` | **JDK11 implementation**; JDK8 updates may backport | TLS1.3 peer/cert/cipher policy | Negotiated protocol `TLSv1.3` |
| **NIO TCP channels** | `SocketChannel`, `ServerSocketChannel`, `Selector` | **Java 8 or older** | Socket peer | Nonblocking I/O/readiness and correct bytes |
| **Unix-domain socket** | `UnixDomainSocketAddress`, `StandardProtocolFamily.UNIX`, NIO | **Java 16** | OS/FS/permissions AF_UNIX | Actual bind/connect, not just class presence |
| **Virtual threads for I/O** | `Executors.newVirtualThreadPerTaskExecutor` | **Java 21** | Does not change network protocol | `Thread.currentThread().isVirtual()` inside task |

**Do not confuse the layers:** HTTP/2 is a protocol, `HttpClient.Version.HTTP_2` is an API preference; the WebSocket client API does not create a server; `SSLContext` supporting TLS does not mean a handshake succeeded. Virtual threads are a **concurrency tool**, not a new HTTP/3/TCP/UDP protocol.

For JDK 8, `com.sun.net.httpserver` was distributed as a JDK-specific API rather than part of the portable Java SE baseline; this table selects Java 11 when building the `jdk.httpserver` fixture to avoid depending on runtime image differences across older lines.

## 5. What Should a Compatibility Test Result Record Store?

| Column | Example Value | Meaning |
| --- | --- | --- |
| `test_id` | `HTTP11-LOCAL-001` | Fixed scenario |
| `source_file` | `HttpClientCompatibility11.java` | Actual source filename |
| `compiler_version` | `javac 24.0.2` | Compiler tool used |
| `target_release` | `11` | API/bytecode boundary |
| `runtime_version` | `OpenJDK 24.0.2` | Actual JVM that executed |
| `vendor/build` | OpenJDK + vendor/build metadata | Security/providers differ |
| `OS/architecture` | Windows x64, Linux x64... | AF_UNIX, firewall, path behavior |
| `requested_protocol` | `HTTP_2` | Preference, not yet the result |
| `observed_protocol` | `HTTP_1_1` | Protocol actually used by server/client |
| `endpoint` | `127.0.0.1:<OS port>` | Do not hard-code port |
| `assertions` | status 200, exact body | Prevents false PASS |
| `result` | PASS/FAIL/SKIP/NOT_TESTED | Distinguishes missing conditions |
| `exception/exit_code` | 0, `SocketTimeoutException` | Debugging data |
| `scope` | compile target11 + runtime24 | Scope/limits of evidence |

If there is no real runtime 8 yet, **do not record “runtime8 PASS”** even if the JDK24 compiler can compile `--release 8`. If there is no HTTP/2/TLS/WebSocket peer yet, record `SKIP_NO_PEER` or `API_PRESENT_ONLY`; do not equate API presence with protocol completion.

## 6. `--release`, Bytecode, and the Java Runtime

Since JDK 9, `javac --release N` constrains **syntax, the corresponding public APIs, and the class file major version**. Using only `-source N -target N` on a newer JDK without locking the platform API can accidentally access APIs that only exist in the newer JDK.

~~~bash
# Compiler compatible with target 8, e.g., javac 24.0.2 tested:
javac --release 8 NetworkBaseline8.java
java NetworkBaseline8

# Compiler supporting release 11/17/21 respectively:
javac --release 11 HttpClientCompatibility11.java
javac --release 17 UnixDomainApi17.java
javac --release 21 VirtualThreadApi21.java
~~~

**The `java` used at runtime must support the corresponding class file/APIs.** A target21 class will not run on JVM17. Target8 code can usually run on a higher JVM if dependencies/behavior match, but **to prove runtime8, you must run it on an actual JVM8**.

On a JDK8 compiler, the `--release` option does not exist yet:

~~~bash
javac NetworkBaseline8.java
java NetworkBaseline8
~~~

Newer compilers may warn that target8 is obsolete, and a future compiler may drop overly old targets. Check `javac --help`. During testing, compiler **24.0.2** accepted `--release 8` but warned that source/target 8 is “obsolete”, which is not a compile failure.

| Target Java | Class file major version |
| --- | --- |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |
| 27 | 71 |

Use `javap -verbose ClassName` to inspect `major version`, but major version **does not prove** TLS/HTTP2/OS runtime compatibility.

## 7. Environment Rules for Reproducible Examples

1. **Bind IPv4 loopback `127.0.0.1`** on both sides. `localhost` may resolve to IPv6 `::1`, which differs from the address the server bound to.
2. **Bind port `0`** so the OS assigns an ephemeral port, and retrieve the actual port with `getLocalPort()` or `getAddress().getPort()`. Do not open a temporary socket to grab a port and close it before rebinding, because that has a race condition.
3. The server must already be **bound/listening** before the client connects. If `accept()` is a blocking call, run the server worker and client on appropriate threads.
4. Set **timeouts** for connect/accept/read/request; avoid tests hanging indefinitely. `SO_TIMEOUT` is not a whole-session deadline.
5. Verify **exact content**: TCP UTF-8 echo, UDP byte-for-byte, HTTP 200 + body + version.
6. **Close sockets/servers and executors** in `finally` or `try-with-resources`.
7. Do not print **random port numbers** to stdout when exact matching is needed; print `port > 0`, and use the actual port only when constructing the endpoint.
8. Do not treat loopback tests as a guarantee of delivery/security over the Internet. TCP does not preserve message boundaries; UDP does not guarantee delivery/order/uniqueness.

## 8. Program 1 — Java 8 Baseline: Real TCP and UDP on Loopback

`NetworkBaseline8.java` runs two cases in the same process:

- **TCP:** `ServerSocket(0,16,127.0.0.1)` and a thread handling `accept()`. The client connects to the OS-assigned port, sends the UTF-8 line `xin chào`, receives `ECHO:xin chào`, and checks exact equality. `shutdownOutput()` half-closes the send direction while still reading the echo.
- **UDP:** The `DatagramSocket` receiver also binds port 0, receives four bytes `{0,1,0xff,10}`, echoes the exact `DatagramPacket.getLength()`, and the client compares with `Arrays.equals`. UDP packets can be lost on real networks, so receive has a timeout.

The code uses Java 8 syntax/APIs, with no `var`, `record`, virtual threads, or `java.net.http`.

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class NetworkBaseline8 {
    public static void main(String[] args) throws Exception {
        final InetAddress loopback = InetAddress.getByName("127.0.0.1");
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            try (ServerSocket listener = new ServerSocket(0, 16, loopback)) {
                listener.setSoTimeout(5_000);
                Future<String> served = worker.submit(new Callable<String>() {
                    @Override public String call() throws Exception {
                        try (Socket peer = listener.accept()) {
                            peer.setSoTimeout(5_000);
                            BufferedReader in = new BufferedReader(
                                    new InputStreamReader(peer.getInputStream(),
                                            StandardCharsets.UTF_8));
                            BufferedWriter out = new BufferedWriter(
                                    new OutputStreamWriter(peer.getOutputStream(),
                                            StandardCharsets.UTF_8));
                            String request = in.readLine();
                            out.write("ECHO:" + request);
                            out.newLine();
                            out.flush();
                            return request;
                        }
                    }
                });
                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            loopback, listener.getLocalPort()), 3_000);
                    client.setSoTimeout(5_000);
                    BufferedWriter out = new BufferedWriter(
                            new OutputStreamWriter(client.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedReader in = new BufferedReader(
                            new InputStreamReader(client.getInputStream(),
                                    StandardCharsets.UTF_8));
                    out.write("xin chào");
                    out.newLine();
                    out.flush();
                    client.shutdownOutput();
                    String answer = in.readLine();
                    if (!"ECHO:xin chào".equals(answer)) {
                        throw new AssertionError("TCP echo mismatch: " + answer);
                    }
                    System.out.println("tcp loopback: "
                            + listener.getInetAddress().isLoopbackAddress());
                    System.out.println("tcp ephemeral port: "
                            + (listener.getLocalPort() > 0));
                    System.out.println("tcp echo: " + answer);
                }
                System.out.println("tcp server request: "
                        + served.get(5, TimeUnit.SECONDS));
            }

            try (DatagramSocket receiver =
                         new DatagramSocket(new InetSocketAddress(loopback, 0))) {
                receiver.setSoTimeout(5_000);
                Future<Integer> served = worker.submit(new Callable<Integer>() {
                    @Override public Integer call() throws Exception {
                        byte[] buffer = new byte[32];
                        DatagramPacket input = new DatagramPacket(buffer, buffer.length);
                        receiver.receive(input);
                        DatagramPacket echoed = new DatagramPacket(
                                input.getData(), input.getLength(),
                                input.getAddress(), input.getPort());
                        receiver.send(echoed);
                        return input.getLength();
                    }
                });
                try (DatagramSocket sender =
                             new DatagramSocket(new InetSocketAddress(loopback, 0))) {
                    sender.setSoTimeout(5_000);
                    byte[] payload = new byte[] {0, 1, (byte) 0xff, 10};
                    sender.send(new DatagramPacket(payload, payload.length,
                            loopback, receiver.getLocalPort()));
                    byte[] receivedBytes = new byte[32];
                    DatagramPacket reply = new DatagramPacket(
                            receivedBytes, receivedBytes.length);
                    sender.receive(reply);
                    byte[] exact = Arrays.copyOf(
                            reply.getData(), reply.getLength());
                    boolean matched = Arrays.equals(payload, exact);
                    if (!matched) throw new AssertionError("UDP echo mismatch");
                    System.out.println("udp ephemeral port: "
                            + (receiver.getLocalPort() > 0));
                    System.out.println("udp echo exact: " + matched);
                }
                System.out.println("udp server bytes: "
                        + served.get(5, TimeUnit.SECONDS));
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Run with a newer compiler supporting `--release 8`:

~~~bash
javac --release 8 NetworkBaseline8.java
java NetworkBaseline8
~~~

Expected stdout measured on **runtime JDK24.0.2**:

~~~text
tcp loopback: true
tcp ephemeral port: true
tcp echo: ECHO:xin chào
tcp server request: xin chào
udp ephemeral port: true
udp echo exact: true
udp server bytes: 4
~~~

The lines `tcp ephemeral port: true`/`udp ephemeral port: true` do not mean the port is always the same: the port number **is chosen by the operating system** and can change every run. `udp echo exact: true` proves that the packet in **this test run** returned intact, not a promise that UDP never drops packets on real networks.

## 9. Interpreting the TCP and UDP Results of Program 1

**TCP:** `ServerSocket` is a listening socket; `accept()` returns a `Socket` for the connection. `BufferedReader.readLine()` uses a newline defined by **the application**; TCP itself is just a byte stream and does not split messages per `write` call. The client calls `flush()` before `shutdownOutput()` to transmit all bytes; the server writes the echo and closes the peer. The client checks `ECHO:xin chào` and exits.

**UDP:** `DatagramPacket` represents one datagram, but the OS/network may drop or delay it and datagrams have size limits. The server sends back to the client’s `input.getAddress()/getPort()`, and must use `input.getLength()` so it does not echo garbage bytes from the unused remainder of the buffer. In the payload, `(byte)0xff` has signed value `-1` in Java, which is **not the EOF** of `InputStream.read()`. We use `Arrays.equals` to check the exact byte bit pattern.

**Do not hard-code `8080`** when the listener bound port `0`. Do not connect the client to port `0`: 0 is a request to allocate a port at **bind** time, not a peer address.

## 10. Program 2 — Java 11 HTTP Client and Server on Loopback

Since Java 11, the JDK provides the standard `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, and `WebSocket` APIs. To test real HTTP/1.1, the program starts an internal `HttpServer` from the `jdk.httpserver` module on `127.0.0.1:0` and sends a GET using `HttpClient.Version.HTTP_1_1`.

The program also **checks the API presence** of the `HTTP_2` enum and `WebSocket` interface, and reads the **list of TLS protocols the provider reports as supported**. That does **not** perform an HTTP/2 request, WebSocket handshake, or TLS handshake.

Create `HttpClientCompatibility11.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import javax.net.ssl.SSLContext;

public class HttpClientCompatibility11 {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 16);
        server.createContext("/probe", (HttpExchange exchange) -> {
            try {
                byte[] bytes = "jdk-httpserver".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, bytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/probe");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1).build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            if (response.statusCode() != 200
                    || !response.body().equals("jdk-httpserver")) {
                throw new AssertionError("HTTP response mismatch");
            }
            System.out.println("http status: " + response.statusCode());
            System.out.println("http response protocol: " + response.version());
            System.out.println("http body: " + response.body());
            System.out.println("http2 preference constant: "
                    + HttpClient.Version.HTTP_2);
            System.out.println("websocket client API present: "
                    + (WebSocket.class != null));
            boolean tls13 = Arrays.asList(SSLContext.getDefault()
                    .getSupportedSSLParameters().getProtocols())
                    .contains("TLSv1.3");
            System.out.println("tls13 supported by runtime: " + tls13);
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile/run:

~~~bash
javac --release 11 HttpClientCompatibility11.java
java HttpClientCompatibility11
~~~

Stdout tested on JDK24.0.2:

~~~text
http status: 200
http response protocol: HTTP_1_1
http body: jdk-httpserver
http2 preference constant: HTTP_2
websocket client API present: true
tls13 supported by runtime: true
~~~

**The `tls13 supported by runtime` line may differ on other runtimes/vendors/security configs.** It is a capability probe of `SSLContext.getDefault().getSupportedSSLParameters()`, with no real TLS connection. When recording matrix results, copy the **value observed on the running JVM** rather than forcing every JVM to print “true”.

## 11. HTTP/1.1 and HTTP/2: Requested Does Not Mean Negotiated

In Program 2, the client sets the `HTTP_1_1` preference and the demo server responds with HTTP/1.1; `response.version()` shows `HTTP_1_1`. If you change the preference to `HTTP_2`, there is **no guarantee** that a server supporting only HTTP/1.1 will return HTTP/2. The connection may fall back or fail depending on the peer/protocol negotiation.

Illustrative example inside an HTTP client that already has `request`:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2).build();
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.version()); // This is the observed protocol.
~~~

*Not yet a standalone program; requires request/exception handling and an actual HTTP/2 server.*

With HTTPS, HTTP/2 is usually negotiated via **ALPN in TLS**; cleartext HTTP/h2c requires corresponding peer support. **`jdk.httpserver.HttpServer` in the demo is a simple HTTP server for testing HTTP/1.1, not an HTTP/2 test fixture**. To mark HTTP2 PASS, use a suitable HTTP/2 peer and assert `response.version()==HTTP_2` after a successful response.

Record two separate columns: `requested_version=HTTP_2` and `observed_version=HTTP_1_1/HTTP_2`. Do not turn a valid HTTP/1.1 fallback into “HTTP/2 API does not exist”.

## 12. WebSocket Client: Class Presence Differs from Frame Exchange

`java.net.http.WebSocket` has existed since Java 11 as a client API. Verifying WebSocket requires a real RFC6455 WebSocket server, not merely `WebSocket.class != null`.

A real positive test should: connect via `buildAsync(uri, listener)` successfully; send text/binary and await the **send** future; receive echoes through `Listener.onText/onBinary` with receive demand `request(n)`; send Ping and await Pong via `Listener.onPong`; and finally send and receive Close according to the protocol. **Completing the `sendPing` future only proves Ping was sent**, not that Pong was received.

A simple HTTP `HttpServer` does not automatically become a WebSocket server by returning a 101 response; a WebSocket server must also handle RFC6455 framing, masking, and control frames. When no peer is set up yet, record **WebSocket API PRESENT, protocol NOT_TESTED**.

## 13. TLS: Supported, Enabled, and Negotiated

| Question | API/Condition | Does It Prove the TLS Handshake Used That Protocol? |
| --- | --- | --- |
| Does the runtime/provider support TLS1.3? | `SSLContext.getSupportedSSLParameters().getProtocols()` | No, only capability |
| Does the configuration allow TLS1.3? | `SSLSocket.getEnabledProtocols()` or `SSLEngine.getEnabledProtocols()` | Not yet, still candidates |
| Did the TLS handshake with the peer complete? | `socket.startHandshake()`, valid trust/cert | Session succeeded, not necessarily TLS1.3 |
| Is the session using TLS1.3? | `SSLSession.getProtocol()` after handshake | **Yes**, if the value is `TLSv1.3` |

In a program that already has a connected `SSLSocket socket` with proper certificate/hostname verification:

~~~java
socket.startHandshake();
String protocol = socket.getSession().getProtocol();
System.out.println("negotiated TLS protocol: " + protocol);
~~~

*Illustrative snippet depending on peer and TLS configuration; no fixed stdout, not a self-contained runnable program.*

JDK11 brought the TLS1.3 implementation into JSSE per JEP332; backports/vendor updates on JDK8 may vary. JDK27 updates hybrid post-quantum key exchange for TLS1.3, but that does **not** prove every communication session uses that algorithm: you must inspect negotiated details on the peer/provider and security policy conditions. Do not disable TLS verification and do not use trust-all in tests.

## 14. Program 3 — Unix-Domain Socket API with Java 17

`UnixDomainSocketAddress` has **Since 16**; this article uses the **`--release 17`** baseline because it is a convenient LTS line for comparison. Create `UnixDomainApi17.java`:

~~~java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.file.Path;

public class UnixDomainApi17 {
    public static void main(String[] args) {
        UnixDomainSocketAddress address =
                UnixDomainSocketAddress.of(Path.of("network-demo.sock"));
        System.out.println("unix address API: "
                + address.getClass().getSimpleName());
        System.out.println("unix family enum: "
                + StandardProtocolFamily.UNIX);
        System.out.println("socket file: "
                + address.getPath().getFileName());
    }
}
~~~

Run:

~~~bash
javac --release 17 UnixDomainApi17.java
java UnixDomainApi17
~~~

Stdout:

~~~text
unix address API: UnixDomainSocketAddress
unix family enum: UNIX
socket file: network-demo.sock
~~~

**What is tested:** compiler target17 and runtime JDK24 recognize the address class/enum. **What is not tested:** whether the OS supports/permits AF_UNIX bind/connect, and whether the socket file path has valid permissions/length. To verify real Unix socket runtime behavior, add a `ServerSocketChannel`/`SocketChannel` server/client on `StandardProtocolFamily.UNIX` and test cleanup on the running OS.

If you compile the same `UnixDomainApi17.java` source with `--release 11`, the compiler **must reject** API symbols introduced in Java16. That is a useful negative compile gate, not a networking bug.

## 15. Program 4 — Java 21 Virtual Threads

Virtual threads became an official API in **Java 21**. They can help handle many blocking socket operations with appropriate thread-management cost, but they do not change TCP/UDP packets, HTTP framing, TLS handshakes, or backpressure requirements.

Create `VirtualThreadApi21.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class VirtualThreadApi21 {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Boolean> task = executor.submit(
                    () -> Thread.currentThread().isVirtual());
            System.out.println("virtual thread: "
                    + task.get(5, TimeUnit.SECONDS));
        }
    }
}
~~~

Run:

~~~bash
javac --release 21 VirtualThreadApi21.java
java VirtualThreadApi21
~~~

Stdout:

~~~text
virtual thread: true
~~~

`Executors.newVirtualThreadPerTaskExecutor()` and `Thread.isVirtual()` do not exist in the Java17 public API target. The same source with `--release 17` must compile FAIL, even if the primary compiler in use is JDK24. The runtime must be Java21+ to run level65 class files. In a real TCP server application, virtual threads do not automatically limit connections/body bytes; quotas and bounded resource policies are still required.

## 16. Negative Compile Gates: Testing What Must Be Rejected

An accurate compatibility matrix has both **positive** and **negative** gates:

~~~bash
# FAIL is the expected result because java.net.http is not part of Java 8:
javac --release 8 HttpClientCompatibility11.java

# FAIL is the expected result because UnixDomainSocketAddress is Since 16:
javac --release 11 UnixDomainApi17.java

# FAIL is the expected result because virtual-thread APIs are official since 21:
javac --release 17 VirtualThreadApi21.java
~~~

In QA, it was confirmed that **the last two checks** produced nonzero exit codes, meaning the compiler properly rejected the APIs when constrained to those releases. So that CI does not treat the compile failure as a job failure, a negative-gate test must expect a nonzero exit code while also checking the missing-API cause; **do not blindly accept any nonzero exit code caused by a syntax error**.

Do not try to match exact verbatim compiler error text because wording can vary across JDKs/vendors. Compile each gate into a separate output directory so stale class files are not left behind and an artifact from an earlier build is not accidentally executed.

## 17. The Module System and Missing Modules at Runtime

Java 8 has no `module-info.java`. Java 9+ has the module system, and HTTP client/server code in a **named module** must declare it properly:

~~~java
module demo.network {
    requires java.net.http;
    requires jdk.httpserver;
}
~~~

*This is a sample `module-info.java` for a module using both API groups, not a standalone Java main program.*

`java.base` contains `Socket`/`ServerSocket`/`DatagramSocket`/JSSE and is read automatically. `java.net.http` contains the HTTP/WebSocket client. `jdk.httpserver` is a JDK-specific module since Java 9 exporting `com.sun.net.httpserver`. When simple examples run on the **classpath**, no module descriptor like the above needs to be provided.

If the runtime is packaged with `jlink` and omits `java.net.http`/`jdk.httpserver`, the program can hit module/class resolution errors even though the source compiled on a full JDK. In that case, classify it as a **packaging/runtime-image mismatch**, not an HTTP transport failure.

## 18. Evidence Matrix Tested on an Actual Toolchain

| Program/Gate | Compile Target | Runtime/Capability Actually Measured | Status |
| --- | --- | --- | --- |
| `NetworkBaseline8` | `--release 8` | JVM24.0.2: TCP loopback Unicode echo, UDP byte echo | **PASS for compile8 + run24**, not run8 |
| `HttpClientCompatibility11` | `--release 11` | JVM24.0.2: HTTP 200/HTTP_1_1, WebSocket API, TLS supported flag | **PASS for compile11 + run24** |
| `UnixDomainApi17` | `--release 17` | JVM24.0.2: address + enum API | **PASS API-only**, Unix socket not bound |
| `VirtualThreadApi21` | `--release 21` | JVM24.0.2: task running on virtual thread | **PASS compile21 + run24** |
| Unix API compiled with release11 | `--release 11` | Compiler rejects non-existent API | **EXPECTED FAIL / gate PASS** |
| Virtual thread source release17 | `--release 17` | Compiler rejects Java21 APIs | **EXPECTED FAIL / gate PASS** |
| HTTP/2 network | API available | No HTTP2 peer in this article | **NOT_TESTED**, do not report negotiated |
| WebSocket network | API available | No WebSocket server started in this article | **NOT_TESTED**, do not report echo |
| TLS handshake | Provider supports TLSv1.3 | No TLS peer/cert/trust in this article | **NOT_TESTED**, do not report negotiated |
| Unix-domain socket transport | Unix address object present | AF_UNIX bind/connect not attempted | **NOT_TESTED** |

This is the most important pedagogical takeaway of the article: **knowing how to label evidence**. You cannot replace “NOT_TESTED” with “PASS” simply because an API class was imported. You cannot treat a test run on JDK24 as a test run on JDK8 just because its bytecode was built with release8.

## 19. CI Plan Across Target Runtimes

| Real CI Runtime | Sources to Compile/Run | Meaning |
| --- | --- | --- |
| **JDK 8** | `NetworkBaseline8` | Proves Java8 runtime TCP/UDP, using compiler8 without `--release` |
| **JDK 11** | Baseline8 + HttpClientCompatibility11 | Tests JDK11 HTTP/1.1 and the TLS provider of JVM11 itself |
| **JDK 17** | Above + UnixDomainApi17 | Unix API Since16; can test OS AF_UNIX separately |
| **JDK 21** | Above + VirtualThreadApi21 | Virtual executor running on JVM21 |
| **JDK 25 LTS** | All four sources | Regression on the new LTS release, exact vendor/patch |
| **JDK 27** | All four sources | Regression on newest release, plus TLS1.3 peer testing as needed |

If you only have a JDK24 compiler, running `--release 8/11/17/21` only builds a **compile-target matrix**, not a **runtime matrix**. To prove runtime compatibility, you must select the `java` binary of that version or a CI job with the corresponding JDK image. Record the exact `java -version`, `javac -version`, OS, and vendor in artifacts; do not use compiler values in place of runtime values.

For dependencies outside the JDK, each job must pin versions and check module/API availability. For security/network experiments, pin certificates/truststores or local peer fixtures to avoid unexpected Internet, DNS, and TLS certificate failures.

## 20. Useful PASS/FAIL/SKIP Classification

| Case | Proper Classification | Should Not Be Called |
| --- | --- | --- |
| `cannot find symbol HttpClient` on target8 | API compatibility compile FAIL | HTTP/2 network FAIL |
| `UnsupportedClassVersionError` | JVM too old for class file | TLS/HTTP server bug |
| `NoClassDefFoundError` due to missing module/runtime image | Packaging/JPMS failure | UDP unsupported |
| `BindException` port already in use | Bind/address conflict | JDK lacks ServerSocket |
| `ConnectException` | Cannot connect to listener/port | API was removed |
| `SocketTimeoutException` | Timed out waiting for connect/accept/read | Server definitely not processing |
| UDP echo timeout | Datagram/peer/permissions | Byte arrays incompatible with Java |
| `SSLHandshakeException` | TLS cert/trust/cipher/hostname/protocol | Wrong HTTP method GET/POST |
| Preferred HTTP_2 but observed HTTP_1_1 | Negotiation/fallback | HttpClient lacks HTTP/2 API |
| WebSocket handshake rejected | Peer/endpoint/protocol/auth | WebSocket class does not exist |
| Unix-domain bind failed | OS/filesystem/permission | JDK lacks address class |
| Virtual thread symbol missing on target17 | Java API gate | Broken TCP stack |

A CI environment may forbid TCP/UDP sockets on loopback, or firewalls/namespaces may alter behavior. That is an **environment restriction**; record the reason and choose SKIP if policy allows, rather than replacing it with a test that opens no network and claiming PASS.

## 21. Security and Reproducibility When Running Experiments

- Bind `127.0.0.1` instead of `0.0.0.0` so the test server is not exposed on external interfaces. Even so, untrusted processes on the same host/namespace may still attempt to access loopback.
- Use port `0` so the OS assigns it, then have the client connect to **the exact bound port**. Do not open and close a temporary socket to “reserve” a port; there is a race condition.
- Do not send secrets over plaintext TCP/HTTP; when testing TLS, use valid SAN certificates and a proper truststore, **never trust-all**.
- `Socket.setSoTimeout` limits a single read, not the total duration of the entire session. Add overall deadlines/body byte limits if extending to production.
- UDP **does not guarantee delivery/order/uniqueness**. Testing a single loopback datagram does not substitute for testing on lossy networks.
- TCP does not preserve write/read boundaries; for multiple messages, use length-prefixing or delimiters and handle partial reads.
- Bound worker pools, connection counts, payload bytes, and time. Use try-with-resources/finally to clean up and prevent the runner from hanging.
- Do not log tokens/keystore passwords/private keys to test stdout. Vendor/JDK version metadata may be saved, but avoid secret environment variables.

## 22. Workflow for Creating a New Compatibility Matrix

For another networking example, follow this sequence:

1. **Identify the actual protocol** to test (TCP/UDP/HTTP/2/WebSocket/TLS...).
2. **Choose the public API** and read the Javadoc `Since` field or JEP; set a reasonable minimum JDK.
3. **Set source/target release** explicitly, separating compiler version and runtime version.
4. **Build a local peer** or record the exact server version/config/TLS cert when a remote peer is needed.
5. **Write deterministic tests** with port 0, loopback, timeouts, byte/status/version assertions, and cleanup.
6. **Add negative compile gates** at lower target levels to catch unintended use of newer APIs.
7. **Run on real runtimes** of the claimed supported JDKs, not just cross-compilation.
8. **Measure the observed protocol**, rather than equating it with the requested enum or supported JSSE protocols.
9. **Record PASS/FAIL/SKIP/NOT_TESTED** with reasons, stdout, exceptions, and versions.
10. **Re-run when upgrading runtime/OS/vendor/protocol peer** to catch changes in security defaults or runtime behavior.

An illustrative record:

~~~text
test_id: HTTP11-LOCAL-001
source: HttpClientCompatibility11.java
compiler: javac 24.0.2
target: --release 11
runtime: OpenJDK 24.0.2
server: jdk.httpserver / 127.0.0.1:ephemeral
expected: 200, HTTP_1_1, body=jdk-httpserver
observed: 200, HTTP_1_1, body=jdk-httpserver
status: PASS
scope: compile Java11 API + run JDK24, NOT a runtime11 test
~~~

## 23. Self-Check Questions

**Question 1.** `javac --release 8` succeeds, but `java -version` reports JVM24. Can you mark Java8 runtime PASS?

*Answer:* No. You tested target8 compilation/API and JVM24 execution; you must run on JVM8 to prove runtime8.

**Question 2.** `HttpClient.Version.HTTP_2` exists and the client is configured for HTTP_2, but the response reports HTTP_1_1. Does Java not support HTTP/2?

*Answer:* No. The API supports HTTP/2, but the peer/negotiation on that request used HTTP/1.1; you need an HTTP/2 server and must check `response.version()`.

**Question 3.** TLSv1.3 is in `getSupportedSSLParameters()`. Can you record “TLSv1.3 negotiated PASS”?

*Answer:* No. No real handshake has occurred yet. You need a valid `SSLSocket` handshake and `SSLSession.getProtocol()`.

**Question 4.** `UnixDomainSocketAddress` compiles cleanly targeting 17; does that mean an AF_UNIX socket can bind on the current OS?

*Answer:* No. API presence differs from runtime OS/FS support; you need a bind/connect test.

**Question 5.** Why cannot `Executors.newVirtualThreadPerTaskExecutor()` be used with `--release 17`?

*Answer:* The virtual threads API became official in Java21 and is not in the Java17 API.

**Question 6.** Does a 4-byte UDP echo PASS on loopback prove UDP is reliable over the Internet?

*Answer:* No. UDP has no delivery guarantee; the test proves that a single local datagram arrived and echoed accurately.

**Question 7.** Why is port 0 useful for CI?

*Answer:* The OS allocates an available port at bind time, reducing collisions; the client must connect to the actual port reported by the listener, not port 0.

**Question 8.** Does `UnsupportedClassVersionError` belong to compile API, runtime, or TLS errors?

*Answer:* Runtime/bytecode compatibility: the JVM does not understand the class file version.

## 24. Practice Exercises

1. Use an **actual** JDK8 to compile/run `NetworkBaseline8`, then try JDK11, 17, 21, 25. Record compiler, runtime, OS, stdout, PASS/FAIL.
2. Use a newer compiler with `--release 8` and run the class on a real JVM8; compare the two forms of evidence and run `javap -verbose` to inspect major52.
3. In `HttpClientCompatibility11`, change the HTTP1.1 preference to HTTP2; measure `response.version()` and explain why there is no HTTP2 server fixture.
4. Set up an HTTP2-capable HTTPS test server with proper certificate/trust; verify that an HTTP2 request returns response.version()==HTTP_2.
5. Set up a loopback RFC6455 WebSocket server and Java11 client; assert text/binary echo, onPong, Close, and receive demand.
6. Create a TLS test with a valid SAN certificate, measure `SSLSession.getProtocol()` after handshake, and compare with `getSupportedSSLParameters()`.
7. Compile UnixDomainApi17 with `--release 11` to verify the negative compile gate; add AF_UNIX bind/connect on a supported OS.
8. Compile VirtualThreadApi21 with `--release 17` to observe the expected failure, then run target21 on an actual JVM21.
9. Design a JSON/CSV matrix with fields `test_id`, compile/runtime vendor+version, requested/observed protocol, OS, evidence, result.
10. Test an occupied fixed port versus dynamic port0 to observe the difference; do not use the time-of-check/time-of-use free-port trick.
11. Test an IP family mismatch `localhost` IPv6 vs `127.0.0.1` IPv4 and classify `ConnectException`, without treating it as a Java API bug.
12. Intentionally block the UDP response to verify the timeout; do not equate a timeout with “Java does not support UDP”.
13. Create a custom runtime with `jlink`, try omitting the `java.net.http` or `jdk.httpserver` module to identify module packaging errors.
14. Compare JDK25 LTS and JDK27 against a proper TLS1.3 endpoint; record negotiated protocol/cipher/cert without inferring hybrid key exchange from the release name.
15. Write a CI checklist ensuring **tests execute on each runtime** rather than only cross-compiling on a single runtime.

## Official References

- [Oracle Java SE Support Roadmap](https://www.oracle.com/technetwork/java/javase/tech/eol-135779.html): JDK8/11/17/21/25 LTS and non-LTS releases.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): Java27 GA 15/09/2026.
- [Oracle Java 27 announcement](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/): hybrid post-quantum key exchange updates for TLS1.3.
- [Oracle JDK 11 Release Notes](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): JEP332 TLS1.3 implementation.
- [`javac --release` — Java SE21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): source/API/bytecode constraints and supported targets.
- [`HttpClient` — Java SE11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP1.1/HTTP2 API and version preference.
- [`HttpResponse` — Java SE11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `version()` and response.
- [`WebSocket` — Java SE11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html): WebSocket client API.
- [`ServerSocket` — Java SE17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): TCP listener and ephemeral port.
- [`DatagramSocket` — Java SE17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html): UDP datagram.
- [`jdk.httpserver` — Java SE17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): simple HTTP server module.
- [`UnixDomainSocketAddress` — Java SE17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/UnixDomainSocketAddress.html): Since16, Unix-domain address.
- [Virtual Threads — Java SE21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual-thread executor.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113), [RFC 6455 — WebSocket](https://www.rfc-editor.org/rfc/rfc6455), [RFC 8446 — TLS1.3](https://www.rfc-editor.org/rfc/rfc8446): standard protocols.
