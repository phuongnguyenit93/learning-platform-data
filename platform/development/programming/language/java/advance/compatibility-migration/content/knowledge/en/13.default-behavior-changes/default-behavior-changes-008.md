# I/O and Networking Implementation Changes and Edge-Case Handling

When upgrading Java, source code may still compile, method signatures remain intact, and unit tests pass normally, yet the application fails in less common scenarios: a socket closes while a thread is reading, DNS returns addresses in a different order, a UDP packet is truncated, a single `read()` does not receive all the data, an HTTP client reuses an expired connection, or a file containing Vietnamese characters is read using a different charset than before. These symptoms are easily labeled generically as a "new Java bug", whereas the cause may lie in the JVM, networking libraries, operating system, DNS/TLS configuration, the application's protocol, or longstanding incorrect assumptions about the API.

In Java Advance Compatibility Migration, the **default behavior** aspects to watch go beyond removed APIs or bytecode types. Some JDKs change the **implementation behind a public API** while keeping the contract intact; some releases change **environment defaults** such as the charset; others add new I/O mechanisms that an application only uses when actively adopted. Discrepancies often surface in edge cases: timeouts, concurrent resource closure, thread interruption, partial reads/writes, network failures, malformed input, and race conditions.

This lesson explains those layers of change, how to distinguish what is a Java API contract from what is merely the observed behavior of an implementation, how to build reproducible tests, and a verification workflow when moving between JDKs.

## 1. Distinguishing API Contracts from Underlying Implementations

### 1.1. Keeping the Public API Does Not Mean All Observed Details Are Immutable

For example, the familiar API:

```java
Socket socket = new Socket();
socket.connect(new InetSocketAddress("example.org", 443), 3_000);
socket.setSoTimeout(5_000);
InputStream input = socket.getInputStream();
```

may continue to exist across many JDK versions. However, internal details such as native socket structures, synchronization, how threads are managed while waiting on I/O, error reporting order, close mechanisms, or interoperability with virtual threads may change.

Distinguish between:

- **API contract:** what Javadoc/JLS/JVMS guarantees, such as the meaning of `read()`, timeouts, close, and exceptions.
- **Implementation details:** how the JDK uses native libraries, selectors, file descriptors, thread parking, or data structures.
- **Operating system behavior:** TCP stack, file descriptor limits, DNS resolver, buffer sizes, IPv4/IPv6, and error codes.
- **Third-party library behavior:** HTTP client pools, JDBC drivers, reactive frameworks, serializers, or observability agents.
- **Application protocol contract:** message framing, retries, idempotency, encoding, and error handling.

A behavior that previously occurred on an older JDK without being guaranteed by the API should not be treated as a default compatibility requirement. If the application genuinely depends on that behavior, record it as a tested assumption, then fix the code or design an adaptation plan.

### 1.2. Classifying Changes During Migration Investigation

| Type of change | Example | Verification approach |
|---|---|---|
| Internal implementation change | Socket/DatagramSocket rewritten | Test close, concurrent I/O, timeouts, and network errors |
| Default change | Default charset becomes UTF-8 starting in JDK 18 | Test file and payload reads/writes |
| New API/mechanism, opt-in | Unix-domain socket channels, virtual threads | Test only branches that use them |
| Platform data change | Certificate store, timezone, Unicode | Verify by vendor and JDK update |
| OS/container change | DNS, IPv6, ulimit, network namespace | Compare in equivalent environments |
| Dependency change | HTTP client, TLS provider, framework, agent | Pin and compare the dependency graph |

Do not attribute every different outcome to the JDK if the test environment also changed the OS, base image, CA bundle, proxy, or dependency versions.

## 2. Directly Relevant JDK Milestones

The following milestones help locate the scope; they do not mean every application is affected:

| Milestone | Change | Migration significance |
|---|---|---|
| JDK 11 | `java.net.http.HttpClient` becomes a standard API (JEP 321) | New HTTP client available for opt-in use; does not automatically replace `HttpURLConnection` |
| JDK 13 | Reimplement Legacy Socket API (JEP 353) | Changes the implementation of `Socket` and `ServerSocket` beneath the public API |
| JDK 15 | Reimplement Legacy DatagramSocket API (JEP 373) | Changes the implementation of `DatagramSocket` and `MulticastSocket` |
| JDK 16 | Unix-Domain Socket Channels (JEP 380) | Adds the ability to use Unix-domain sockets in NIO channels on supported systems |
| JDK 18 | UTF-8 by Default (JEP 400) | APIs relying on the default charset may read/write differently than before |
| JDK 18 | Internet-Address Resolution SPI (JEP 418) | Adds an SPI to replace hostname resolution; does not mean default DNS changed for every app |
| JDK 21 | Virtual Threads (JEP 444) | Enables opt-in use of lightweight threads with blocking I/O; requires checking pinning and resource limits |

Specifically, if the migration is **JDK 17 → 21**, the Socket API and DatagramSocket API reimplementations were already present in JDK 17. They remain worth knowing when investigating historical bugs or differences between build environments, but should not be described as features newly introduced in JDK 21. Conversely, JEP 400 from JDK 18 is a default change lying directly on the 17 → 21 path.

Changes to CAs, disabled TLS algorithms, timezone data, and security patches also depend on the **specific JDK update**. Therefore, when gathering evidence, record both vendor and build number, not just "Java 17" or "Java 21".

## 3. Reimplementation of the Socket API: JEP 353

### 3.1. What Does "Legacy Socket API" Refer To?

The longstanding Java networking classes include `java.net.Socket`, `ServerSocket`, and socket read/write streams. JEP 353 introduced a new implementation for these legacy socket APIs starting in JDK 13, aiming for easier maintainability and support for future JDK I/O evolution.

This is a change **beneath the public API**, not a requirement to rewrite every `Socket` call to `SocketChannel`. Applications using `Socket`/`ServerSocket` generally do not need code changes solely due to JEP 353; however, races, socket closure, and interactions with native/JVM internals need regression testing.

### 3.2. Scenarios That Can Expose Implementation Dependencies

An application may unintentionally rely on:

- The order in which threads blocked in `read()` or `accept()` are woken up when another thread calls `close()`.
- The specific exception type and message when closing a connection concurrently with I/O.
- Timing of `connect()`/`accept()`/`read()` at timeout boundaries.
- How file descriptors are released or how a long blocking operation is handled.
- Synchronizing on the socket object or assuming multiple threads calling the same method are always serialized in a fixed order.
- Behavior not guaranteed by Javadoc for a custom socket implementation.

Do not claim all of the above **definitely changed** in a specific JDK. They are areas to test because they commonly depend on timing and implementation. If a regression occurs, identify the JDK/build, OS, stack trace, and exact call path before concluding the cause.

### 3.3. Example of Explicit Timeouts

```java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

public final class SimpleTcpClient {
    public static void main(String[] args) throws IOException {
        try (Socket socket = new Socket()) {
            socket.connect(
                new InetSocketAddress("example.org", 443),
                3_000
            );

            socket.setSoTimeout(5_000);

            // Read/write according to the defined protocol.
            // Do not assume a single read() returns the entire message.
        }
    }
}
```

There are **at least two different timeouts**:

- The timeout passed to `Socket.connect(endpoint, timeout)` bounds the connection establishment phase per the API contract.
- `setSoTimeout(...)` bounds the wait time of a single blocking `read()` operation on the socket input stream; it is not an overall deadline for the entire request/response.

An application may also need a **business deadline** covering DNS, connect, writing the request, reading the response, and retries. An overall deadline cannot be replaced by setting a read timeout.

### 3.4. Closing a Socket and Blocked Threads

A thread may be blocked in `read()`; another thread requests shutdown and closes the socket. The read operation will then have to exit via the appropriate mechanism and exception. However, code should not depend on the **exception message string** or the exact ordering between close and data arriving right around the time of close.

A sound lifecycle management model:

1. Have a clear owner responsible for closing the socket.
2. Shutdown marks the stopped state and closes resources.
3. I/O workers record exceptions during shutdown as a distinct case, not always as a production error.
4. Do not close/read the same socket from multiple places without a concurrency contract.
5. Test cleanup across normal close, remote reset, timeout, cancellation, and process shutdown.

The `socket.isConnected()` state describes a history of having connected successfully; it is not a "ping" proving the peer is currently alive. Even after a socket is closed, `isConnected()` may still return `true`. Rely on the I/O contract, `isClosed()`, and actual error handling.

## 4. DatagramSocket and MulticastSocket: JEP 373

### 4.1. Implementation Change, Unchanged UDP Semantics

JEP 373 from JDK 15 reimplements the legacy datagram APIs including `DatagramSocket`/`MulticastSocket`. Despite the new implementation, the UDP protocol retains its nature:

- Datagrams have message boundaries, unlike a TCP byte stream.
- No guarantee of delivery, ordering, or single copy.
- Packets can be lost, duplicated, delayed, or truncated at the receive buffer.
- Datagram size and fragmentation are subject to network stack limits.
- Multicast depends on interfaces, routing, switch/network policy, and the OS.

Therefore, the fact that an application has "not lost UDP packets so far" does not mean UDP has reliability. During migration, verify application-layer retry, sequence number, or acknowledgment mechanisms if required by the business logic.

### 4.2. Short Receive Buffers Can Truncate the Tail of a Datagram

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public final class UdpReceiver {
    public static void main(String[] args) throws Exception {
        byte[] buffer = new byte[2048];

        try (DatagramSocket socket = new DatagramSocket(9999)) {
            socket.setSoTimeout(2_000);

            DatagramPacket packet =
                new DatagramPacket(buffer, buffer.length);

            try {
                socket.receive(packet);

                String message = new String(
                    packet.getData(),
                    packet.getOffset(),
                    packet.getLength(),
                    StandardCharsets.UTF_8
                );

                System.out.println(message);
            } catch (SocketTimeoutException timeout) {
                System.out.println("No datagram in time window");
            }
        }
    }
}
```

Do not use `buffer.length` as the number of received bytes; use `packet.getLength()`. If the datagram is larger than the packet/buffer capacity, excess data may be discarded. The application cannot recover that portion with a subsequent `receive()` call as with TCP.

When reusing a `DatagramPacket`, pay attention to the packet length left by the previous receive operation; reset the maximum length appropriately before a new receive if you want to reuse the full buffer:

```java
packet.setLength(buffer.length);
socket.receive(packet);
```

This is a real edge case: the first packet is short and the second is longer, yet the program does not reset the packet length and accidentally receives truncated data.

### 4.3. Multicast Depends on the Environment

With `MulticastSocket`, check the selected network interface, multicast address, TTL/hop limit, firewall, container network mode, IPv4/IPv6 support, and group join/leave behavior. Do not assume localhost will fully simulate production multicast.

When the JDK changes implementation, undocumented assumptions about join/leave timing, socket options, and multicast interfaces can be exposed. Tests must use an environment close to the real network topology.

## 5. TCP Is a Byte Stream: Partial Reads/Writes Are Not Regressions

One of the most common networking bugs mistaken for a "Java behavior change" is assuming TCP preserves message boundaries.

### 5.1. One `write()` Does Not Correspond to One `read()`

Suppose the sender executes:

```java
output.write(firstMessage);
output.write(secondMessage);
```

The receiver may read:

- A portion of `firstMessage`.
- Multiple consecutive chunks of the same message.
- Both messages completely in a single read.
- A byte count dependent on buffering, scheduling, and the network.

TCP provides an ordered byte stream, not message framing. A single `InputStream.read(buffer)` call can return fewer bytes than the application expects even when the peer has not closed the connection.

### 5.2. Use Explicit Framing

A common approach is **length-prefix framing**: send the length and then send that exact number of bytes.

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public final class MessageFrame {
    private static final int MAX_BYTES = 1024 * 1024;

    public static void writeMessage(
            DataOutputStream out,
            String value) throws IOException {
        byte[] payload = value.getBytes(StandardCharsets.UTF_8);

        if (payload.length > MAX_BYTES) {
            throw new IOException("Message too large");
        }

        out.writeInt(payload.length);
        out.write(payload);
        out.flush();
    }

    public static String readMessage(
            DataInputStream in) throws IOException {
        int length = in.readInt();

        if (length < 0 || length > MAX_BYTES) {
            throw new IOException("Invalid frame length: " + length);
        }

        byte[] payload = new byte[length];
        in.readFully(payload);

        return new String(payload, StandardCharsets.UTF_8);
    }
}
```

`DataInputStream.readFully(...)` reads the exact number of requested bytes or throws `EOFException` if the stream ends early. Do not omit the `MAX_BYTES` limit: a faulty or untrusted peer could declare a huge length and cause excessive memory consumption.

The example focuses on framing; in a real system, add authentication, checksums/integrity if required by the protocol, deadlines, retries/idempotency, and resource protection.

### 5.3. EOF, Timeout, and I/O Errors Are Three Distinct States

With streams:

- `read() == -1` usually indicates EOF: the peer ended the read stream per stream semantics.
- `SocketTimeoutException` indicates the read operation exceeded the configured timeout.
- Other `IOException`s may indicate connection reset, socket closed, or OS errors.

Do not treat a timeout as EOF, or treat EOF as proof that the response is valid. If the protocol requires 100 bytes but receives 40 bytes followed by EOF, that is a truncated message that must be handled per the protocol contract.

If the application is designed to read until EOF to determine the end of a response, the connection becomes difficult to reuse because EOF typically means terminating one direction of the stream. With persistent connections, use length framing, escaped delimiters, or a protocol with explicit support.

### 5.4. `available()` Is Not the Byte Count of the Entire Message

`InputStream.available()` is an estimate of bytes that can be read immediately without blocking per the implementation's API contract; it is not the total remaining bytes in the message or on the network.

Code like the following is unreliable:

```java
if (input.available() == 0) {
    // Wrong if concluding the remote side has finished sending.
}
```

There may be no bytes in the current buffer yet while the remote side is still sending. Read according to framing and deadlines, rather than relying on `available()` to measure message length.

## 6. NIO Channels: Zero-Byte Reads and Buffer State

NIO provides `SocketChannel`, `ServerSocketChannel`, `Selector`, and `ByteBuffer`. In non-blocking mode, a read operation may return **0** if no data is currently available even though the connection remains open. This is contract behavior, not EOF.

```java
int n = channel.read(buffer);

if (n == -1) {
    // Peer ended the stream: handle EOF.
} else if (n == 0) {
    // No bytes yet; with a non-blocking channel, wait for readiness.
} else {
    // n new bytes were placed into the buffer.
}
```

In non-blocking mode, code should not continuously busy-loop `while (read(...) == 0)`, as that can burn CPU. Use `Selector`, readiness mechanisms, or an appropriate abstraction.

### 6.1. `ByteBuffer` Has Position and Limit

The read/decode flow is typically:

```java
ByteBuffer buffer = ByteBuffer.allocate(4096);

int count = channel.read(buffer);

if (count > 0) {
    buffer.flip();

    while (buffer.hasRemaining()) {
        byte b = buffer.get();
        // Pass the byte into the decoder/frame parser.
    }

    buffer.compact();
}
```

In this simple example, the parser consumes all bytes. For a protocol frame that may not be completely received yet, preserve unconsumed bytes with `compact()` and continue reading on the next pass.

Migration bugs often emerge when changing an NIO library or event loop while a parser implicitly assumes a single read always delivers a full header. Test with frames split at every boundary, especially mid-header, mid-UTF-8 multibyte sequence, and mid-payload.

### 6.2. Partial Writes Must Also Be Handled

With channels:

```java
while (buffer.hasRemaining()) {
    int written = channel.write(buffer);

    if (written == 0) {
        // In non-blocking mode: wait for the writable event instead of busy-spinning.
        break;
    }
}
```

This is only an illustration: if stopping at `written == 0`, the application must retain the unsent `buffer` and register for write readiness to continue writing. Never discard the remaining bytes.

With blocking channels, you can continue writing until `buffer.hasRemaining()` becomes false, but you must still handle close errors, application-level timeouts, and remote disconnects. Do not assume "one write has sent everything to the peer and the peer processed it successfully".

## 7. DNS, IP Addresses, and Endpoint Selection

### 7.1. DNS Is Not a Constant

When the application calls:

```java
InetAddress[] addresses =
    InetAddress.getAllByName("service.example.org");
```

the result can depend on the DNS server, search domain, network namespace, TTL/cache, IPv4/IPv6, VPN, split-horizon DNS, container resolver, and OS/JDK policy. It may return multiple addresses or a different ordering.

Do not assume:

- A hostname always resolves to a single IP.
- The first address is always IPv4.
- IPs never change during the application's lifetime.
- The same hostname returns the same IP across laptops, CI, containers, and production.
- DNS record TTLs are automatically honored identically by every caching layer.

### 7.2. Caching and Negative Caching

Java has a mechanism to cache address resolution results. Security properties such as:

```properties
networkaddress.cache.ttl=30
networkaddress.cache.negative.ttl=5
```

control the caching policy within what the implementation supports. These are **security properties**; do not assume they behave like ordinary `-D` system properties. Configure them using the mechanism supported by the JDK/vendor and verify in the actual runtime.

Avoid picking an arbitrary TTL just as a quick workaround. A short TTL can increase DNS lookup volume; a long TTL can hold onto a changed IP during failover. Determine the system's discovery and failure-recovery requirements.

### 7.3. IPv4/IPv6 and localhost

A service bound to `127.0.0.1` is not automatically listening on `::1`. If the hostname `localhost` resolves to IPv6 first, a client may attempt to connect to a different endpoint than the developer expected.

When testing, specify the address or bind appropriately:

```java
InetSocketAddress endpointV4 =
    new InetSocketAddress("127.0.0.1", 8080);

// If the environment supports IPv6:
InetSocketAddress endpointV6 =
    new InetSocketAddress("::1", 8080);
```

Binding to a wildcard address, selecting the default interface, and dual-stack behavior also depend on the OS/JDK. If the application must support both, test on IPv4-only, IPv6-only, or dual-stack configurations according to product scope.

The JDK provides address-selection configuration properties such as `java.net.preferIPv4Stack` and `java.net.preferIPv6Addresses`. Do not use them as a global workaround before identifying endpoints, DNS, and environment constraints.

### 7.4. JEP 418 Does Not Mean Default DNS Definitely Changed

JEP 418 (JDK 18) adds the **Internet-Address Resolution SPI**, allowing custom implementations to provide hostname resolution services. This is an extension point; the JDK providing an SPI does not by itself mean that every application upgrading from JDK 17 to 21 gets different DNS results.

If an application or agent uses a custom resolver, check the selected provider, fallback, lookup errors, caching, and interactions with HTTP/database clients. If no custom resolver is in use, investigate DNS using actual data and configuration rather than attributing it directly to JEP 418.

## 8. HTTP Clients: Redirects, Timeouts, Pools, and Protocols

### 8.1. Do Not Treat All HTTP Clients in Java as Identical

Common HTTP mechanisms include:

- `HttpURLConnection` from the longstanding APIs.
- `java.net.http.HttpClient`, the standard API since JDK 11.
- Apache HttpClient, OkHttp, Netty, and framework-provided clients.
- Proprietary SDKs from cloud/database/service providers.

They can differ in redirects, connection pooling, HTTP/2, proxies, DNS, TLS, timeouts, retries, and streaming handling. Upgrading the JDK does not automatically replace a third-party client with `java.net.http.HttpClient`.

If the migration simultaneously switches HTTP libraries, record that as an independent change to isolate regressions accurately.

### 8.2. Example of Java HttpClient with Explicit Timeouts

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HttpExample {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://example.org/api/status"))
            .timeout(Duration.ofSeconds(8))
            .GET()
            .build();

        HttpResponse<byte[]> response =
            client.send(request, HttpResponse.BodyHandlers.ofByteArray());

        int status = response.statusCode();

        if (status < 200 || status >= 300) {
            throw new IllegalStateException(
                "Unexpected HTTP status: " + status
            );
        }

        // Interpret bytes according to Content-Type and the API contract.
        System.out.println("bytes=" + response.body().length);
    }
}
```

This is an illustrative example. `connectTimeout` and request timeout have different scopes; a business deadline may also span multiple requests, retries, or processing steps outside the HTTP client.

HTTP 4xx/5xx statuses are typically valid HTTP responses at the transport layer and do not automatically turn into Java exceptions in every client. Classify transport exceptions, timeouts, and application errors from status/body separately.

### 8.3. Redirects Can Alter Security Semantics

When permitting redirects, determine:

- Whether redirects to a different host are allowed.
- Whether credentials, cookies, or authorization headers are forwarded or stripped per client policy.
- Whether redirects from HTTPS to HTTP are blocked.
- How redirects between POST/GET or method/body semantics behave.
- Whether there is a redirect count limit to prevent loops.

Do not enable automatic redirects merely to mask an incorrect endpoint configuration or SSL error. Exact redirect behavior must be verified against the client version and tested with a simulated server.

### 8.4. Connection Reuse and Stale Connections

HTTP keep-alive/pooling reduces TCP/TLS handshake overhead, but a server or proxy may close idle connections. A subsequent send can then fail because the client attempts to use an already-closed connection.

Instead of concluding the new runtime is "unstable", check:

- Pool idle timeout and max lifetime.
- Proxy/load balancer idle timeout.
- Keep-alive and server close behavior.
- Retry policy for idempotent requests.
- HTTP/1.1 vs. HTTP/2 actually negotiated.
- Whether streaming response bodies are properly consumed/closed.

Performance may shift when updating the JDK, but a single throughput result should not be used to infer that a protocol contract changed.

## 9. TLS, Certificates, and Security Policies

### 9.1. SSL Handshake Is an Independent Integration Step

A program being able to connect over TCP does not mean the TLS handshake will succeed. TLS also requires matching protocols/ciphers, certificate chains, truststores, hostname verification, SNI, and sometimes client certificates.

When upgrading the JDK, security defaults can change across updates: weak algorithms are disabled, truststores change, providers are updated, or TLS negotiation differs. These changes can expose legacy servers that only support ciphers/protocols no longer accepted.

Typical errors:

- `SSLHandshakeException` when the handshake fails.
- `PKIX path building failed` when the trust chain cannot be verified.
- Hostname mismatch when the certificate does not match the endpoint.
- `protocol_version` or `handshake_failure` from the server/proxy.

### 9.2. Do Not Fix by Disabling Security Checks

Do not:

- Disable certificate validation.
- Use a trust-all TrustManager.
- Skip hostname verification.
- Downgrade the TLS protocol or enable weak algorithms across the entire JVM just to establish a connection.

The proper fix is to inspect the chain, domain name, server TLS policy, proxy, truststore, and JDK policy, and then update the server/certificates/configuration according to security requirements.

To investigate in an authorized environment, the JVM provides TLS debug options such as:

```bash
java -Djavax.net.debug=ssl,handshake -jar application.jar
```

Logs may contain certificates, hosts, and internal network metadata. Collect logs only within the necessary scope and redact sensitive data before sharing.

### 9.3. Distinguishing JDK Major Versions from JDK Updates

When comparing JDK 17 and 21, record the vendor, patch level, base image, truststore, and TLS provider. An issue may result from a CA update or policy change within a JDK update of the same line, not necessarily from changing major versions.

## 10. File I/O and Encoding: JEP 400

### 10.1. UTF-8 Becomes the Default Charset Starting in JDK 18

Before JDK 18, many Java APIs used an OS/locale-dependent default charset. Starting in JDK 18, JEP 400 standardized UTF-8 as the default charset for APIs relying on this default, subject to compatibility mechanisms or exceptions documented in the API.

Therefore, when upgrading **JDK 17 → 21**, code such as:

```java
String text = new String(bytes);
byte[] output = text.getBytes();
```

may read/write differently than before if the old runtime used a non-UTF-8 encoding. The same applies to overloads that do not specify a charset in `FileReader`, `FileWriter`, `InputStreamReader`, `OutputStreamWriter`, and some I/O libraries.

### 10.2. Specify Encoding at Data Boundaries

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "customers.csv");

String content =
    Files.readString(path, StandardCharsets.UTF_8);

Files.writeString(path, content, StandardCharsets.UTF_8);
```

APIs such as `Files.readString(Path)` were already defined to use UTF-8 from Java 11 onward; not every API relies on the default charset. `Properties.load(InputStream)` has its own encoding contract (ISO-8859-1 in the classic properties format). Therefore, check the Javadoc of the exact overload rather than modifying based on guesses.

If a legacy file truly uses a different encoding, specify the exact charset where it is read:

```java
Charset legacyCharset = Charset.forName("windows-1258");

try (BufferedReader reader =
         Files.newBufferedReader(path, legacyCharset)) {
    // Read legacy data according to the verified contract.
}
```

The charset name is an example; verify the encoding of the actual file. Do not change the default for the entire JVM merely to accommodate a single legacy file.

### 10.3. Network Payload Encoding Is a Protocol Contract

TCP/UDP transmits bytes, not ready-made "Java Strings". Each protocol must define how encoding/decoding works. For HTTP, check `Content-Type` and payload specifications; for JSON, follow the encoding rules of the standard and communicating APIs.

If code calls `new String(bytes)` on socket data, changing the default charset can corrupt the payload even though TCP is completely stable. This is a classic example of a "networking" bug whose real cause is encoding.

### 10.4. Unicode Can Be Split Between Two Reads

With UTF-8, a single character can span multiple bytes. If a parser decodes each chunk independently, splitting a buffer mid-character between bytes can produce replacement characters or decoding errors.

When receiving a stream, use `InputStreamReader` or a `CharsetDecoder` that maintains state across chunks, rather than arbitrarily calling `new String(chunk, UTF_8)` on each piece without knowing character boundaries.

## 11. File System Behavior and Edge Cases

### 11.1. Compatibility Does Not Depend Solely on the JDK

File paths, permissions, symlinks, case sensitivity, atomic renames, and file locking also depend on the file system/OS. If a migration simultaneously moves from Windows to Linux or from a VM to a container, errors may appear even though the JDK API did not change.

Examples:

- `report.csv` and `Report.csv` may be two separate files on one file system, but not on another.
- The path separator is `\` or `/` depending on the platform; avoid manual string concatenation.
- File permissions and owner/group differ between containers and hosts.
- Symlinks can cause read/write operations to point to unexpected resources.
- File lock semantics vary by file system, OS, and process.
- Atomic moves are not supported by every provider or across two file stores.

### 11.2. Using Path and Files According to Contract

```java
Path base = Path.of("data", "export");
Path file = base.resolve("report.csv");

Files.createDirectories(base);
Files.writeString(file, "id,name\n1,An\n", StandardCharsets.UTF_8);
```

`Path.resolve` reduces separator concatenation mistakes. However, it does not automatically protect against path traversal if a path segment comes from untrusted input. Normalize/validate and check containment per security policy, while also considering symlinks/races.

### 11.3. Atomic Move May Not Be Available

When writing a file using a publish-as-one-step pattern, you can create a temporary file and then move it to the target:

```java
Path temp = Files.createTempFile(target.getParent(), ".new-", ".tmp");

try {
    Files.writeString(temp, output, StandardCharsets.UTF_8);
    Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    // Decide whether to allow a fallback based on consistency requirements.
    throw ex;
} finally {
    Files.deleteIfExists(temp);
}
```

This snippet is an illustrative pattern; `target`, `output`, and the corresponding imports must exist in the actual context. If the destination already exists, replacement semantics during atomic move may depend on the provider. Do not automatically fall back to a non-atomic move if the system requires guaranteeing an incomplete file is never visible.

In production, also evaluate fsync/durability, permissions, ownership, and crash consistency. An atomic rename does not guarantee data is durably persisted to the storage device in all cases.

### 11.4. TOCTOU: Check-Then-Use Can Race

Code:

```java
if (Files.exists(path)) {
    byte[] bytes = Files.readAllBytes(path);
}
```

does not guarantee the file still exists when `readAllBytes` executes. Between check and use, another process may delete, replace, or change permissions on the file.

Handle exceptions on the operation itself, use atomic APIs where available, and avoid turning a single `exists()` call into a promise about future state.

## 12. Closing, Canceling, and Interrupting I/O Operations

### 12.1. Blocking I/O Has Its Own Lifecycle

A thread calling `read()` may be waiting for data. An application wanting to shut down needs a mechanism to cancel the wait or intentionally close resources. The effect of `Thread.interrupt()` depends on the channel/stream type, how I/O is implemented, and the thread in use; do not assume an interrupt is always equivalent to `Socket.close()`.

Errors/conditions that may be encountered include:

- `SocketTimeoutException`.
- `SocketException` due to a closed/reset connection.
- `ClosedChannelException`.
- `ClosedByInterruptException`.
- `AsynchronousCloseException`.
- `EOFException` or `read() == -1` when data is missing/stream ends.

Do not handle all exceptions with a broad catch and infinite retry. Classify intentional shutdown, timeouts, protocol errors, and network errors to decide the follow-up policy.

### 12.2. Try-With-Resources Is an Ownership Boundary

```java
try (Socket socket = new Socket()) {
    socket.connect(endpoint, 3_000);
    socket.setSoTimeout(5_000);
    // Perform I/O communication.
}
```

Try-with-resources ensures the socket is closed when exiting scope, even if an exception occurs. However, if a socket is shared across multiple tasks, the scope must reflect true ownership; closing prematurely can cause other tasks to fail.

### 12.3. Do Not Retry All I/O Failures the Same Way

Suppose a client sends a money transfer request and then loses the connection before receiving the response. The client does not know for sure whether the server processed it or not. Uncontrolled retries can cause duplicate processing.

For requests with side effects, use idempotency keys, transaction status lookups, or reliable protocol acknowledgments. This is an important distinction between:

- **Transport failure:** no result was received.
- **Business failure:** the server returned a business error.
- **Unknown outcome:** the server may have processed the request, but the response was lost.

A timing shift when upgrading the JDK can expose more unknown-outcome cases; the issue must be solved at the business contract level, not merely by increasing timeouts.

## 13. Virtual Threads and Blocking I/O on JDK 21

### 13.1. Does Not Mean Applications Automatically Switch to Virtual Threads

JEP 444 finalized virtual threads in JDK 21. Simply upgrading the runtime to Java 21 does not automatically turn every `Thread` into a virtual thread. Applications must explicitly use the appropriate APIs or framework configuration.

Example:

```java
try (ExecutorService executor =
         Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> result = executor.submit(() -> readFromService());
    System.out.println(result.get());
}
```

This snippet requires the appropriate imports and a `readFromService()` method provided by the application. Its purpose is to illustrate the one-virtual-thread-per-task model.

### 13.2. I/O-Bound Workloads Can Benefit

Virtual threads make it easier to write readable blocking code in systems with many concurrent tasks waiting on I/O. However, they do not automatically make the CPU faster, do not increase database connection counts or remote capacity, and do not replace backpressure.

If a small thread pool previously acted as an unintentional cap on concurrent requests, switching to virtual threads can cause a surge in requests to databases/APIs. Enforce real resource bounds using connection pools, semaphores, concurrency budgets, or rate limits.

### 13.3. Pinning on JDK 21

On JDK 21, a virtual thread can become **pinned** to its carrier thread while performing blocking operations in certain situations, especially while holding a `synchronized` monitor or inside a native/foreign function call. This can affect scalability if many virtual threads stay pinned for long durations.

When testing virtual threads on JDK 21:

- Look for `synchronized` blocks holding locks during long network I/O calls.
- Check native/JNI libraries or I/O drivers with special characteristics.
- Use Java Flight Recorder and events such as `jdk.VirtualThreadPinned` to investigate when appropriate.
- Measure latency, throughput, carrier/platform thread count, and connection utilization.
- Do not assume every framework/driver is already optimized for virtual threads simply because it runs on JDK 21.

Some pinning mechanics change in later JDKs; evaluate against the exact runtime version the product uses rather than inferring from another JDK's behavior.

## 14. Edge-Case Table Requiring Special Testing

| Scenario | Common wrong assumption | Required behavior/check |
|---|---|---|
| TCP read returns fewer bytes | "One read equals one message" | Framing, loop/readFully, timeout |
| TCP read returns -1 | "The request must be complete" | Check complete frame and protocol |
| NIO read returns 0 | "EOF reached" | In non-blocking mode: wait for readiness |
| NIO write does not empty buffer | "write sent everything" | Retain remaining bytes and continue when writable |
| UDP packet larger than buffer | "Receive the rest on the next receive" | Control packet size, detect/reduce truncation |
| Reused DatagramPacket | "Packet length always equals original capacity" | Reset length before a new receive |
| Socket read timeout | "Entire request deadline expired" | Maintain a separate overall deadline |
| DNS returns multiple IPs | "Picking one fixed IP is enough" | Address selection/failover policy |
| Localhost supports both IPv4/IPv6 | "Binding 127.0.0.1 also accepts ::1" | Test both address families |
| TLS handshake error | "Just disable certificate validation" | Fix certificate, truststore, protocol |
| HTTP 503 | "Every HTTP error throws IOException" | Check status code and body |
| Remote closes pooled connection | "Every reuse always succeeds" | Pool lifecycle, controlled retries |
| File changes encoding | "new String(bytes) is always the same as before" | Specify charset and contract |
| UTF-8 split across chunks | "Each chunk can be decoded independently" | Stateful decoding |
| File exists then disappears | "exists guarantees read succeeds" | Handle races on the operation |
| Atomic move unsupported | "Every file system supports atomic rename" | Handle AtomicMoveNotSupportedException |
| Shutdown while thread is reading | "Any exception is a production error" | Distinguish expected cancellation from failure |
| Timeout after write | "Server did not process it" | Idempotency/unknown outcome |
| Virtual thread concurrency rises | "I/O backend capacity also rises" | Resource limits, backpressure |

This list serves as input to test design. Not every application needs all cases; choose based on the actual protocol, dependencies, OS, and operational requirements.

## 15. Designing Tests to Reproduce I/O and Networking Failures

### 15.1. The Baseline Must Be Pinned

Before changing the JDK, record:

- JDK vendor, major/minor/update/build.
- OS, kernel, architecture, container image.
- JVM flags and security properties.
- DNS, proxy, firewall, certificates/truststore.
- Versions of HTTP libraries, Netty, database drivers, and frameworks.
- Network topology: localhost, internal network, Internet, load balancer, service mesh.
- Connection pools, executors, thread models, timeouts, and retries.
- Representative payloads and pre-existing errors in the baseline.

If comparing two JDKs in different environments, clearly state any uncontrolled variables. Avoid drawing conclusions about root cause from a single test.

### 15.2. Testing with a Controllable Server

A test server or network fault proxy enables creating scenarios:

1. Accept a TCP connection without sending data.
2. Send headers and pause before sending the body.
3. Send frames byte by byte.
4. Close the connection mid-message.
5. Reset the connection unexpectedly.
6. Return an HTTP redirect loop or 429/503.
7. Return a chunked response or truncated body.
8. Perform a TLS handshake with an expired/mismatched certificate.
9. Fail DNS lookup or make the endpoint unreachable.
10. Drop, duplicate, reorder, or oversize UDP packets beyond the buffer.

Each test should have a hard timeout to avoid hanging the pipeline. Use dynamically allocated ports if the framework supports it, rather than hardcoded ports that easily conflict across parallel builds.

### 15.3. Testing by Runtime and Environment Matrix

| Verification dimension | Minimum cases | Extended cases when needed |
|---|---|---|
| JDK | Baseline and target JDK | Multiple patches/vendors |
| OS | Production OS | Relevant Windows/Linux/macOS |
| Network | localhost and real staging | IPv4-only, IPv6-only, dual-stack |
| DNS | Host with single/multiple A/AAAA | Failover, cache expiry, negative lookup |
| HTTP | 2xx, 4xx, 5xx, timeout | Redirects, HTTP/2, proxy, stale pool |
| TLS | Valid trust chain | Expired cert, hostname mismatch, mTLS |
| Payload | ASCII and accented UTF-8 | Legacy files, Unicode boundaries, malformed bytes |
| Stream | Full frames and partial frames | EOF mid-header/body, slow client |
| Concurrency | Normal load | Concurrent close, shutdown, saturation |
| File I/O | Normal files | Permissions, symlinks, locks, atomic move unsupported |

There is no need to multiply every dimension into a huge matrix. Use risk-based selection: pick combinations representing the application's risks and the JDK/OS changes actually taking place.

### 15.4. Measure Metrics Instead of Only Observing Pass/Fail

Monitor:

- DNS resolution latency and lookup error counts.
- TCP connect time, read timeouts, resets, and EOFs.
- HTTP status distribution and retry counts.
- TLS handshake successes/failures.
- Connection pool active/idle/waiting counts.
- Thread counts and virtual-thread events/pinning where applicable.
- Request latency p50/p95/p99 and throughput.
- File I/O errors, queue backlog, and payload decode errors.
- Resource leaks: socket/file descriptors, heap, direct buffers, and threads.

JFR, application tracing/metrics, and structured logs can aid investigation. However, do not enable byte-level payload logging or TLS debug logging long-term if there is a risk of exposing secrets or imposing excessive overhead.

## 16. Investigation Process When Behavior Differs Between Two JDKs

### Step 1: Describe the Difference Accurately

Instead of "Java 21 has networking bugs", write: "On JDK 17, endpoint A responds in 300 ms; on JDK 21, 2% of requests hit `SocketTimeoutException` at the read stage when going through proxy B".

Include stack traces, timestamps, frequency, JDK build, client type, and environment.

### Step 2: Identify the Failing Layer

Classify:

- DNS lookup.
- TCP connect/accept.
- TLS handshake.
- HTTP protocol/client pool.
- Application framing/serialization.
- Database/network driver.
- File read/write/charset.
- Shutdown/cancellation.
- OS/container/network infrastructure.

Do not start by increasing timeouts or changing JDK flags before identifying the failing layer.

### Step 3: Check the API Contract

Ask whether the code relies on wrong assumptions about partial reads, zero reads, socket state, DNS ordering, EOF, timeouts, or encoding. Many bugs did not appear on older JDKs solely due to favorable timing.

### Step 4: Compare Variables

Run the exact same artifact, dependencies, and configuration on both JDKs if possible. Then vary one parameter at a time: JDK update, HTTP client version, OS/container image, TLS provider, or JVM flags. Keep evidence to avoid confusing correlation with causation.

### Step 5: Create a Minimal Regression Test

Simulate the edge case using a test server/proxy or file fixture. Choose sufficiently reliable repeatable conditions so the test does not depend heavily on random timing.

### Step 6: Fix at the Right Layer

For example:

- Partial read: fix the framing parser.
- Charset: specify the encoding.
- Stale DNS cache: adjust discovery/caching with solid justification.
- TLS: fix certificates/policy.
- Timeout: define deadlines and retries.
- Runtime pool: adjust lifecycle rather than changing global JVM socket settings first.
- Concurrent close: clarify the ownership/cancellation contract.

### Step 7: Re-verify on the Final Artifact

Run tests with the actual JAR/WAR/container and production JDK, with a similar proxy/TLS/DNS setup. Running unit tests directly from an IDE alone is not enough.

## 17. End-to-End Example: A Single TCP Read Does Not Receive the Full Header

Suppose a legacy service has a custom protocol. The first four bytes are the message length, followed by the payload. Old code:

```java
byte[] header = new byte[4];
int count = input.read(header);

if (count != 4) {
    throw new IOException("Invalid header");
}
```

In the previous environment, by coincidence most calls to `read(header)` received all four bytes. After changing the JDK or network proxy, the header arrives in two parts; `read()` returns 2 and the code treats it as an error.

This is not evidence that the JDK violated TCP. The stream contract does not require a single read to fill the buffer. Correct code must read until the entire header is received or EOF/error occurs:

```java
DataInputStream in = new DataInputStream(input);

byte[] header = new byte[4];
in.readFully(header);
```

Then decode the length according to the defined endianness/protocol, enforce a payload limit, and use `readFully` or a stateful parser to read the body.

Regression tests should intentionally send each byte of the header in separate writes, insert pauses, or use network fault injection. Testing only normal payloads is insufficient to confirm the parser tolerates TCP fragmentation.

## 18. End-to-End Example: HTTPS Endpoint After a JDK Upgrade

An application uses a Java HTTP client to call service B. When switching from JDK 17 to 21, some requests fail with `SSLHandshakeException`.

Handling process:

1. Identify host/port, SNI, proxy, and JDK vendor/build.
2. Distinguish successful DNS/connect from failures during the TLS handshake.
3. Collect filtered TLS errors, certificate chains, and protocol/cipher negotiation details.
4. Check truststore/container CAs and hostname verification.
5. Check whether there was a simultaneous JDK update or proxy/load balancer change.
6. Test connecting to a properly TLS-configured server in staging.
7. Do not disable certificate validation or enable weak ciphers system-wide.
8. Run real test requests, mTLS if needed, and verify retry/timeout behavior after fixing.

If the finding is that the server only supports a weak algorithm no longer permitted by policy, the primary fix is updating the server's TLS configuration. Any local client workaround must undergo security review and be strictly scoped, rather than becoming an uncontrolled new default.

## 19. End-to-End Example: Legacy CSV File After JEP 400

A batch job on Windows JDK 17 uses:

```java
String data = Files.readString(path);
```

In this case, read the **exact method contract**: `Files.readString(Path)` already used UTF-8 since JDK 11, so you cannot conclude it changed encoding merely because of JEP 400. If the batch job actually uses `new FileReader(path.toFile())` or `new String(bytes)` without specifying a charset, those APIs are the candidates affected by the default charset.

Process:

1. Identify the actual overload.
2. Check the source file encoding at the byte level or via the supplier contract.
3. Create fixtures containing Vietnamese characters, punctuation, and non-ASCII characters.
4. Specify the charset at the read boundary.
5. Test both input reading and output writing.
6. Check rollback behavior if the old and new versions process shared files during the transition period.

Distinguishing based on Javadoc helps avoid modifying APIs that already used UTF-8 regardless of the JVM default charset.

## 20. Release, Monitoring, and Rollback

I/O issues are often sensitive to load, latency, and network topology, so they do not always surface in local tests. Use a phased rollout:

1. **Baseline:** record metrics for socket errors, HTTP/TLS, DNS, latency, throughput, and resource usage.
2. **Staging:** run a representative workload with the target JDK/container.
3. **Canary:** route a small portion of traffic and compare error rates and p95/p99.
4. **Scale-up:** conditionally increase traffic when metrics remain within thresholds.
5. **Halt/rollback:** have clear triggers for timeouts, TLS failures, connection resets, queue backlogs, or data corruption.
6. **Post-rollout monitoring:** inspect batch jobs, scheduled tasks, and rarely invoked code paths.

Rollback is not necessarily just changing a JDK flag. Keep the old image/artifact, JVM flags, and accompanying dependencies. If file formats, protocols, or data changed, determine compatibility between the old and new versions. For request failures with an unknown outcome, avoid retries/rollbacks that execute side-effect operations twice.

## 21. Handoff Record and Checklist

The migration record should contain:

- **Environment record:** JDK vendor/update, OS/container, kernel, DNS, proxy, TLS, and relevant JVM flags.
- **I/O inventory:** sockets, datagrams, NIO, HTTP clients, file I/O, parsers, and encoding.
- **Behavior assumptions:** framing, EOF, timeouts, shutdown, DNS ordering, retries, charset, and resource ownership.
- **Dependency matrix:** HTTP/network frameworks, drivers, TLS providers, logging/tracing agents, and tested versions.
- **Verification evidence:** unit, integration, fault injection, TLS/HTTP contract, and performance tests.
- **Release evidence:** artifact checksums, image, metric baseline, canary status, and rollback plan.

### Checklist Before Finalizing Migration

- [ ] Distinguished public API changes, internal implementation changes, JDK defaults, and OS environment changes.
- [ ] Clearly documented milestones JEP 353, JEP 373, JEP 400, and new features actually used.
- [ ] Verified TCP framing, partial reads, and partial writes.
- [ ] Distinguished EOF, timeout, reset, and cancellation.
- [ ] Handled `SocketChannel.read() == 0` in non-blocking mode.
- [ ] Checked UDP truncation, `DatagramPacket` reuse, and multicast where applicable.
- [ ] Verified DNS caching, IPv4/IPv6, localhost, and failover.
- [ ] Defined connect/read/request/deadline timeouts and retry semantics.
- [ ] Verified HTTP statuses, redirects, pooling, stale connections, and TLS.
- [ ] Audited I/O APIs relying on the default charset and legacy data.
- [ ] Tested Unicode payloads split across multiple chunks and malformed input.
- [ ] Checked file permissions, symlinks, atomic moves, and file races.
- [ ] Verified resource cleanup, concurrent close, and graceful shutdown.
- [ ] If using virtual threads, bounded resources and checked pinning on the exact JDK.
- [ ] Tested failure injection and edge cases on the final artifact.
- [ ] Compared metrics against the baseline in equivalent environments.
- [ ] Prepared halt thresholds, rollback, and an unknown-outcome handling plan.

Changes in I/O and networking implementations do not mean Java broke the contracts of its published APIs. However, migration can expose previously untested assumptions about timing, message framing, DNS, charset, timeouts, close, and resource lifecycles. The right approach is to **stick to contracts, isolate the failing layer, write tests for edge cases, and measure behavior on the real runtime/artifact**. Doing so allows the team to find and fix the true cause instead of relying on workarounds tied to a single JDK or environment.
