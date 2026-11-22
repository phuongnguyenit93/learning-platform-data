# DTLS với SSLEngine cho giao tiếp datagram (Java 9+)

## 1. DTLS giải quyết vấn đề gì?

**Datagram Transport Layer Security (DTLS)** mang các đặc tính bảo mật của TLS vào môi trường truyền **datagram** như UDP: xác thực bên giao tiếp khi được cấu hình, bảo vệ tính bí mật và toàn vẹn của payload. Khác với TLS thông thường đặt trên một luồng byte đáng tin cậy như TCP, UDP có thể **mất gói, trùng gói, đảo thứ tự hoặc truyền nhiều datagram với độ trễ khác nhau**. DTLS thiết kế record và handshake phù hợp với đặc tính đó; nó **không biến UDP thành TCP**, không hứa mọi payload ứng dụng được nhận hoặc đúng thứ tự.

Java 9 bổ sung DTLS vào Java Secure Socket Extension (JSSE) và nhà cung cấp SunJSSE thông qua `SSLEngine`. Các JDK hiện đại vẫn cung cấp DTLS 1.2. Theo tài liệu SunJSSE đang được sử dụng, phiên bản được công bố là `DTLSv1.2` và `DTLSv1.0`; **chọn DTLS 1.2** cho thực hành hiện nay. DTLS 1.0 bị vô hiệu theo chính sách bảo mật mặc định của JDK hiện đại và không nên kích hoạt lại. RFC 9147 đã định nghĩa DTLS 1.3, nhưng việc một bản đặc tả tồn tại không có nghĩa `SSLContext.getInstance("DTLS")` trong JDK hiện tại đã triển khai `DTLSv1.3`; phải kiểm tra khả năng của provider, không đổi tên giao thức theo suy đoán.

### DTLS, UDP và SSLEngine ở các tầng nào?

```text
Ứng dụng                  Ứng dụng
  |                          ^
  v                          |
Plaintext ByteBuffer     Plaintext ByteBuffer
  |                          ^
  v                          |
SSLEngine.wrap()         SSLEngine.unwrap()
  |                          ^
  v                          |
DTLS record bytes        DTLS record bytes
  |                          ^
  v                          |
DatagramSocket.send() -> mạng UDP -> DatagramSocket.receive()
```

`SSLEngine` **không mở socket, không gửi UDP, không tự chờ timeout**. Nó xử lý mã hóa/giải mã và tiến độ handshake. Ứng dụng sở hữu `DatagramSocket` hoặc `DatagramChannel`, danh tính địa chỉ peer, queue packet, lịch timer và vòng lặp sự kiện.

So sánh thực tế:

| Cơ chế | Dữ liệu ứng dụng | Mối quan tâm chính |
| --- | --- | --- |
| UDP thường | Datagram chứa dữ liệu chưa được DTLS bảo vệ | Không có bảo đảm mặc định về xác thực, mã hóa, toàn vẹn, giao hàng |
| TLS + TCP | Luồng byte bảo mật trên kết nối TCP | TCP bảo đảm thứ tự/truyền lại; ứng dụng vẫn tự đóng khung thông điệp |
| DTLS + UDP | Record bảo mật được gửi trong datagram | Bảo vệ payload, nhưng ứng dụng vẫn xử lý mất gói, trễ, trùng, thứ tự |
| `SSLEngine` | Chuyển `ByteBuffer` plaintext ↔ TLS/DTLS record | Vòng lặp I/O và tiến độ handshake hoàn toàn do ứng dụng điều khiển |

**Khi dùng:** giao thức ứng dụng thực sự cần semantics datagram (chẳng hạn telemetry, tín hiệu thời gian thực, hệ thống dùng UDP) nhưng vẫn cần bảo vệ trao đổi. Nếu chỉ muốn bảo mật một kết nối thông thường trên TCP, `SSLSocket` hoặc API TLS ở tầng cao có thể đơn giản hơn. Không nên dùng DTLS chỉ vì nghĩ UDP luôn nhanh hơn TCP; độ tin cậy và vận hành sẽ do ứng dụng gánh.

## 2. Tạo DTLS engine an toàn

Hai phía phải có vai trò đối lập: **client** `setUseClientMode(true)` và **server** `setUseClientMode(false)`. Tạo engine bằng `SSLContext.getInstance("DTLS")`; đặt giao thức và `SSLParameters` **trước** `beginHandshake()`.

Ví dụ cấu hình lõi (các biến `context`, `peerHost`, `peerPort` là tham số của ứng dụng, đoạn mã này nằm trong phương thức hiện có):

```java
SSLEngine engine = context.createSSLEngine(peerHost, peerPort);
engine.setUseClientMode(isClient);
engine.setEnabledProtocols(new String[] {"DTLSv1.2"});

SSLParameters params = engine.getSSLParameters();
params.setMaximumPacketSize(1200);
params.setEnableRetransmissions(true);
if (isClient) {
    params.setEndpointIdentificationAlgorithm("HTTPS");
}
engine.setSSLParameters(params);
engine.beginHandshake();
```

- `SSLContext` giữ bộ quản lý khóa (`KeyManager`) và mức tin cậy (`TrustManager`). Server cần khóa riêng và chứng chỉ phù hợp để xác thực; client cần nguồn tin cậy để xác minh chứng chỉ server. Không sử dụng custom “trust everything” manager.
- `peerHost` và `peerPort` khi gọi `createSSLEngine` là thông tin gợi ý cho provider/xác minh định danh, **không** làm engine tự kết nối UDP. Chỉ `DatagramSocket`/`DatagramChannel` thực sự chọn địa chỉ nhận/gửi.
- `setEndpointIdentificationAlgorithm("HTTPS")` yêu cầu kiểm tra danh tính host trong chứng chỉ khi client dùng tên DNS/IP tương ứng; cách dùng này phù hợp khi service sử dụng kiểu danh tính đó. Trust chain hợp lệ **chưa đủ** nếu không xác minh đúng peer mà ứng dụng định kết nối. Certificate demo bên dưới khai báo SAN `localhost`/`127.0.0.1`.
- `setMaximumPacketSize(1200)` đặt giới hạn packet được mong đợi để provider cân nhắc kích thước DTLS record/fragment. Giá trị này cần chọn theo MTU đường truyền và cả overhead IP/UDP. Đây không phải bảo đảm mạng không mất gói hoặc không phân mảnh ở mọi path; không tự xé đôi byte của một DTLS record thành hai gói tùy ý.
- `setEnableRetransmissions(true)` bật hỗ trợ retransmission của DTLS engine đối với **handshake**; ứng dụng vẫn phải cung cấp timer và kích hoạt `wrap()` khi chờ nhận quá hạn.
- Với server cần xác thực client (mTLS), cấu hình `setNeedClientAuth(true)` **và** cung cấp KeyManager/TrustManager phù hợp hai phía. Không bật mTLS chỉ bằng cách đổi một boolean khi client không có chứng chỉ.

Tài liệu `SSLParameters` có thêm `setApplicationProtocols(...)` cho **ALPN**, giúp hai bên thống nhất giao thức ứng dụng trong handshake. Phần demo đầy đủ sẽ dùng ALPN với nhãn riêng `telemetry/1`; nhãn này chỉ là ví dụ, không phải chuẩn chung của mọi dịch vụ.

## 3. Một SSLEngine là một state machine

`SSLEngine.wrap(plain, network)` tiêu thụ plaintext từ `plain` và ghi record DTLS đã bảo vệ vào `network`. Khi handshake, `plain` có thể là buffer rỗng nhưng `wrap` vẫn tạo ClientHello, ServerHello, certificate, Finished hoặc bản truyền lại. Một lời gọi `wrap` của DTLS sinh **tối đa một DTLS record** theo mô tả của SunJSSE; nếu còn `NEED_WRAP`, gọi tiếp để tạo các record còn lại của cùng handshake flight.

`SSLEngine.unwrap(network, plain)` đọc record nhận từ mạng và ghi plaintext đã kiểm tra vào `plain` hoặc thúc đẩy handshake. Không đưa payload ứng dụng nhận qua UDP vào business logic **trước khi** `unwrap` xác thực thành công.

### HandshakeStatus: ứng dụng làm gì?

| `engine.getHandshakeStatus()` | Việc ứng dụng phải thực hiện |
| --- | --- |
| `NEED_WRAP` | Gọi `wrap` với app buffer rỗng; lấy byte từ net buffer và **gửi UDP tới đúng peer**. Lặp tiếp nếu status vẫn cần wrap |
| `NEED_UNWRAP` | Nhận datagram từ peer rồi gọi `unwrap`; khi timeout trong handshake, có thể gọi `wrap` để yêu cầu engine sinh bản truyền lại |
| `NEED_UNWRAP_AGAIN` | **Không chờ thêm UDP**; gọi `unwrap` lần nữa, có thể với `ByteBuffer.allocate(0)`, để xử lý handshake message engine đã buffer |
| `NEED_TASK` | Lấy và chạy mọi tác vụ từ `getDelegatedTask()`, sau đó đọc lại trạng thái |
| `NOT_HANDSHAKING` | Bắt tay ban đầu hoàn thành hoặc engine hiện không trong handshake; sau `beginHandshake` và xử lý đủ các trạng thái, có thể xử lý application data |

`FINISHED` là `SSLEngineResult.HandshakeStatus` được báo **khi một lệnh `wrap/unwrap` vừa hoàn tất handshake**; tài liệu Java ghi rõ `engine.getHandshakeStatus()` không trả `FINISHED`. Kiểm tra `SSLEngineResult.getHandshakeStatus()` nếu cần phát hiện đúng sự kiện, hoặc thấy `NOT_HANDSHAKING` sau quá trình handshake đã khởi tạo.

### Status của một lần wrap/unwrap

`SSLEngineResult` còn có `getStatus()`, `bytesConsumed()`, `bytesProduced()` và `getHandshakeStatus()`. Đừng nhầm `Status` với `HandshakeStatus`:

- `OK`: thao tác hợp lệ; vẫn cần xem số byte tiêu thụ/sinh ra và handshake status kế tiếp.
- `BUFFER_OVERFLOW`: buffer đích không đủ. Mở rộng theo `SSLSession.getPacketBufferSize()` hoặc `getApplicationBufferSize()` rồi thử lại. Không tự phát datagram nửa vời.
- `BUFFER_UNDERFLOW`: không đủ dữ liệu để đọc record; trong giao tiếp DTLS phải kiểm tra datagram/record thực nhận. Không mặc định nối byte của hai datagram tùy ý thành một bản ghi như luồng TCP.
- `CLOSED`: engine đã hoặc đang đóng; xử lý cảnh báo và quy trình kết thúc phiên.

Mỗi `ByteBuffer` có `position`/`limit`: sau `wrap`, gọi `flip()` trước khi lấy byte để gửi; sau `unwrap`, gọi `flip()` cho buffer ứng dụng trước khi decode. Cấp phát buffer dựa trên `getSession().getPacketBufferSize()` và `getSession().getApplicationBufferSize()`; khi cần, cập nhật sau handshake vì kích thước record có thể thay đổi.

### Timer retransmission: điểm khác TLS/TCP

DTLS có cơ chế truyền lại **handshake message**, nhưng `SSLEngine` không biết UDP socket và không có đồng hồ mạng. Khi `NEED_UNWRAP` kéo dài quá timeout, ứng dụng gọi `wrap` với app buffer rỗng; DTLS provider có thể phát lại handshake flight phù hợp. Thời gian chờ, backoff, số lần thử và tổng deadline do ứng dụng quyết định. Không suy ra handshake thất bại ngay sau một gói mất; cũng không lặp vô hạn trong môi trường lỗi.

`NEED_UNWRAP_AGAIN` giải quyết trường hợp engine giữ handshake message đến sớm và sau đó có thể xử lý nội bộ. Đây **không** phải yêu cầu nhận lại datagram. Hai cơ chế **truyền lại** và **xử lý bản tin đã buffer** khác nhau.

Dữ liệu ứng dụng sau handshake **không được DTLS tự động truyền lại để bảo đảm delivery**. Nếu yêu cầu giao hàng đúng một lần, đúng thứ tự hoặc xác nhận đã nhận, giao thức ứng dụng phải tự thiết kế sequence, ACK, timeout, idempotency hay dùng transport khác phù hợp.

## 4. Ví dụ hoàn chỉnh: client/server trao đổi datagram DTLS 1.2 trên localhost

Demo dùng **Java 17+**, PKCS#12 keystore, một server và một client chạy trong cùng JVM nhưng dùng **hai `DatagramSocket` UDP thật** trên loopback. Server có chứng chỉ; client tin cậy đúng chứng chỉ này và kiểm tra tên `localhost`. Hai phía thực hiện handshake DTLS, cùng chọn ALPN `telemetry/1`, client mã hóa một thông điệp, server giải mã.

**Đây là bài lab chạy được**, không phải cấu hình triển khai Internet: self-signed certificate và password cố định chỉ dành cho môi trường local. Demo chỉ trao đổi một datagram ngắn, không thay thế tầng mạng thực tế cần nhiều kết nối, phân quyền, giám sát, rate limit và đóng phiên đúng giao thức.

### 4.1. Tạo chứng chỉ cho lab

Đứng trong một thư mục làm việc riêng, dùng `keytool` thuộc JDK (mỗi lệnh trên một dòng):

```bash
keytool -genkeypair -alias dtls-server -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -dname "CN=localhost" -ext "SAN=DNS:localhost,IP:127.0.0.1" -storetype PKCS12 -keystore server.p12 -storepass changeit -keypass changeit -noprompt
keytool -exportcert -alias dtls-server -keystore server.p12 -storepass changeit -rfc -file server.cer
keytool -importcert -alias dtls-server -file server.cer -keystore trust.p12 -storetype PKCS12 -storepass changeit -noprompt
```

Kết quả là `server.p12` (chứa private key và chứng chỉ của server) cùng `trust.p12` (chứa chứng chỉ được client tin cậy). File `server.cer` trung gian phục vụ import; lab đọc hai file `.p12`. Không đưa keystore thật hoặc password production vào repository.

### 4.2. DtlsAlpnDemo.java

Lưu nội dung này vào **`DtlsAlpnDemo.java`** trong cùng thư mục với hai tệp PKCS#12:

```java
import javax.net.ssl.*;
import java.net.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.concurrent.*;

public class DtlsAlpnDemo {
    private static final ByteBuffer EMPTY = ByteBuffer.allocate(0);

    private static SSLContext serverContext() throws Exception {
        char[] password = "changeit".toCharArray();
        KeyStore keys = KeyStore.getInstance("PKCS12");
        try (var in = Files.newInputStream(Path.of("server.p12"))) {
            keys.load(in, password);
        }
        KeyManagerFactory kmf =
                KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, password);

        SSLContext context = SSLContext.getInstance("DTLS");
        context.init(kmf.getKeyManagers(), null, new SecureRandom());
        return context;
    }

    private static SSLContext clientContext() throws Exception {
        char[] password = "changeit".toCharArray();
        KeyStore trusted = KeyStore.getInstance("PKCS12");
        try (var in = Files.newInputStream(Path.of("trust.p12"))) {
            trusted.load(in, password);
        }
        TrustManagerFactory tmf =
                TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trusted);

        SSLContext context = SSLContext.getInstance("DTLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    private static SSLEngine configure(
            SSLContext context, boolean client, String peerHost, int peerPort) {
        SSLEngine engine = context.createSSLEngine(peerHost, peerPort);
        engine.setUseClientMode(client);
        engine.setEnabledProtocols(new String[] {"DTLSv1.2"});

        SSLParameters parameters = engine.getSSLParameters();
        parameters.setMaximumPacketSize(1200);
        parameters.setEnableRetransmissions(true);
        parameters.setApplicationProtocols(new String[] {"telemetry/1"});
        if (client) {
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
        }
        engine.setSSLParameters(parameters);
        return engine;
    }

    // Tạo tối đa một record DTLS và gửi nó qua UDP, kể cả khi app buffer rỗng.
    private static void sendHandshakeRecord(
            SSLEngine engine, DatagramSocket socket, SocketAddress peer)
            throws Exception {

        ByteBuffer network =
                ByteBuffer.allocate(engine.getSession().getPacketBufferSize());
        SSLEngineResult result = engine.wrap(EMPTY.duplicate(), network);

        switch (result.getStatus()) {
            case OK, CLOSED -> { }
            case BUFFER_OVERFLOW ->
                    throw new SSLException("Network buffer too small");
            case BUFFER_UNDERFLOW ->
                    throw new SSLException("Unexpected wrap underflow");
        }

        network.flip();
        if (network.hasRemaining()) {
            byte[] bytes = new byte[network.remaining()];
            network.get(bytes);
            socket.send(new DatagramPacket(bytes, bytes.length, peer));
        }
    }

    private static void unwrapHandshake(
            SSLEngine engine, ByteBuffer network) throws Exception {

        ByteBuffer application =
                ByteBuffer.allocate(engine.getSession().getApplicationBufferSize());
        int attempts = 8;

        do {
            if (--attempts < 0) {
                throw new SSLException("Too many unwrap operations");
            }

            SSLEngineResult result = engine.unwrap(network, application);
            switch (result.getStatus()) {
                case OK -> { }
                case BUFFER_OVERFLOW ->
                        throw new SSLException("Application buffer too small");
                case BUFFER_UNDERFLOW ->
                        throw new SSLException("Incomplete DTLS datagram");
                case CLOSED ->
                        throw new SSLException("Peer closed during handshake");
            }

            if (result.bytesConsumed() == 0 && result.bytesProduced() == 0) {
                break;
            }
        } while (network.hasRemaining());
    }

    private static void handshake(
            SSLEngine engine, DatagramSocket socket, SocketAddress peer)
            throws Exception {

        engine.beginHandshake();
        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(20);
        socket.setSoTimeout(350);
        int attempts = 0;

        while (System.nanoTime() < deadline && attempts++ < 300) {
            switch (engine.getHandshakeStatus()) {
                case NEED_TASK -> {
                    Runnable task;
                    while ((task = engine.getDelegatedTask()) != null) {
                        task.run();
                    }
                }
                case NEED_WRAP ->
                        sendHandshakeRecord(engine, socket, peer);

                case NEED_UNWRAP -> {
                    DatagramPacket packet =
                            new DatagramPacket(new byte[4096], 4096);
                    try {
                        socket.receive(packet);
                        if (!peer.equals(packet.getSocketAddress())) {
                            continue;
                        }
                        unwrapHandshake(engine, ByteBuffer.wrap(
                                packet.getData(),
                                packet.getOffset(),
                                packet.getLength()));
                    } catch (SocketTimeoutException timeout) {
                        // Trong DTLS, wrap() khi đang NEED_UNWRAP
                        // có thể yêu cầu gửi lại handshake records.
                        sendHandshakeRecord(engine, socket, peer);
                    }
                }

                case NEED_UNWRAP_AGAIN ->
                        unwrapHandshake(engine, ByteBuffer.allocate(0));

                case NOT_HANDSHAKING, FINISHED -> {
                    return;
                }
            }
        }
        throw new SSLException("DTLS handshake timed out");
    }

    private static void sendMessage(
            SSLEngine engine, DatagramSocket socket,
            SocketAddress peer, String message) throws Exception {

        ByteBuffer plaintext =
                ByteBuffer.wrap(message.getBytes(StandardCharsets.UTF_8));

        while (plaintext.hasRemaining()) {
            ByteBuffer network =
                    ByteBuffer.allocate(engine.getSession().getPacketBufferSize());
            SSLEngineResult result = engine.wrap(plaintext, network);
            if (result.getStatus() != SSLEngineResult.Status.OK) {
                throw new SSLException(
                        "Cannot encrypt: " + result.getStatus());
            }

            network.flip();
            byte[] bytes = new byte[network.remaining()];
            network.get(bytes);
            socket.send(new DatagramPacket(bytes, bytes.length, peer));
        }
    }

    private static String receiveMessage(
            SSLEngine engine, DatagramSocket socket,
            SocketAddress peer) throws Exception {

        DatagramPacket packet = new DatagramPacket(new byte[4096], 4096);
        socket.setSoTimeout(2500);

        do {
            socket.receive(packet);
        } while (!peer.equals(packet.getSocketAddress()));

        ByteBuffer plaintext =
                ByteBuffer.allocate(engine.getSession().getApplicationBufferSize());
        SSLEngineResult result = engine.unwrap(
                ByteBuffer.wrap(
                        packet.getData(),
                        packet.getOffset(),
                        packet.getLength()),
                plaintext);

        if (result.getStatus() != SSLEngineResult.Status.OK) {
            throw new SSLException("Cannot decrypt: " + result.getStatus());
        }

        plaintext.flip();
        return StandardCharsets.UTF_8.decode(plaintext).toString();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (DatagramSocket serverSocket = new DatagramSocket(0, loopback);
             DatagramSocket clientSocket = new DatagramSocket(0, loopback)) {

            SocketAddress serverAddress =
                    new InetSocketAddress(loopback, serverSocket.getLocalPort());
            SocketAddress clientAddress =
                    new InetSocketAddress(loopback, clientSocket.getLocalPort());

            SSLEngine server = configure(
                    serverContext(), false, "localhost", clientSocket.getLocalPort());
            SSLEngine client = configure(
                    clientContext(), true, "localhost", serverSocket.getLocalPort());

            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> serverReceived = executor.submit(() -> {
                    handshake(server, serverSocket, clientAddress);
                    return receiveMessage(server, serverSocket, clientAddress);
                });

                handshake(client, clientSocket, serverAddress);
                sendMessage(client, clientSocket, serverAddress, "Xin chao DTLS");

                System.out.println(
                        "negotiated: " + client.getSession().getProtocol());
                System.out.println(
                        "ALPN: " + client.getApplicationProtocol());
                System.out.println(
                        "server read: " + serverReceived.get(10, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy (đang ở thư mục có `server.p12` và `trust.p12`):

```bash
javac -encoding UTF-8 DtlsAlpnDemo.java
java DtlsAlpnDemo
```

Kết quả trên JDK có provider SunJSSE hỗ trợ các cơ chế được cấu hình (đã kiểm tra thực chạy trên JDK 24):

```text
negotiated: DTLSv1.2
ALPN: telemetry/1
server read: Xin chao DTLS
```

**Điều đã xảy ra:**

1. `serverContext` nạp private key và chứng chỉ từ `server.p12`; `clientContext` nạp danh tính được tin cậy từ `trust.p12`. Không có bước bỏ qua kiểm tra chứng chỉ.
2. `configure` tạo hai engine, gán vai trò khác nhau, giới hạn `DTLSv1.2`, đặt packet size 1200 byte và cùng quảng bá ALPN `telemetry/1`.
3. Hai `DatagramSocket` mở cổng ngẫu nhiên trên loopback. Mỗi engine có địa chỉ peer tương ứng; không có TCP connection.
4. Server và client chạy `handshake` đồng thời. Khi `NEED_WRAP`, gọi `wrap(EMPTY, ...)` rồi gửi record qua socket. Khi `NEED_UNWRAP`, đợi UDP và đưa datagram vào `unwrap`. `NEED_TASK`/`NEED_UNWRAP_AGAIN` được xử lý riêng.
5. Client hoàn thành handshake, `sendMessage` mã hóa thông điệp ứng dụng; server `receiveMessage` nhận UDP, gọi `unwrap` rồi mới decode thành `Xin chao DTLS`.
6. Sau handshake, `getSession().getProtocol()` phản ánh DTLSv1.2 và `getApplicationProtocol()` trả ALPN đã chọn. **ALPN là giao thức ứng dụng trên phiên DTLS**, không phải phiên bản DTLS và không thay cho mã hóa.

**Giới hạn có chủ đích của lab:** một peer tại localhost, một thông điệp ngắn, một lần giải mã application record, timeout cố định và chưa gửi `close_notify` khi kết thúc. Đối với service thật cần socket/event loop nhiều kết nối, tối ưu buffer và timer, đóng phiên theo giao thức, xử lý địa chỉ thay đổi và lỗi mạng. Đừng dùng demo này làm server UDP phục vụ Internet mà không bổ sung các cơ chế đó.

## 5. Đưa SSLEngine vào vòng lặp UDP thực tế

### 5.1. Mỗi phiên gắn với một peer được xác định

DTLS không có TCP connection để phân biệt khách. Server nhận `DatagramPacket` có nguồn `SocketAddress`; nó cần xác định phiên phù hợp và cấp một `SSLEngine` riêng cho phiên đã được chấp nhận. Không chia sẻ cùng một engine để giải mã datagram tùy ý từ nhiều client.

Nhiều ứng dụng lập map session theo địa chỉ peer hoặc định danh phiên được xác thực, nhưng phải cân nhắc NAT rebinding, spoofing địa chỉ UDP, cookie/challenge ở handshake, giới hạn tài nguyên, timeout phiên và cách hủy session. **Chỉ kiểm tra `packet.getSocketAddress()` như trong lab là tối thiểu cho loopback; chưa phải cơ chế chống DoS đầy đủ.** Không cho phép datagram từ địa chỉ lạ làm thay đổi peer đang tin cậy.

### 5.2. Ranh giới datagram, bộ đệm và MTU

- Với datagram đầu vào, dùng **đúng offset và length** thực nhận khi tạo `ByteBuffer.wrap(packet.getData(), packet.getOffset(), packet.getLength())`. Không đưa cả vùng byte chưa dùng của buffer vào `unwrap`.
- DTLS record có framing; giữ đúng record khi gửi. SunJSSE có thể phân mảnh handshake message thành nhiều DTLS records để phù hợp packet size. Không tự cắt đôi ciphertext record hay gộp tùy tiện nhiều datagram thành “stream”.
- Gọi `wrap` nhiều lần nếu engine còn `NEED_WRAP`, gửi **mỗi record được tạo** trước khi chuyển sang nhận. Chú ý trạng thái `bytesProduced() == 0` để tránh phát packet rỗng.
- Xử lý `BUFFER_OVERFLOW` bằng buffer lớn hơn; với `BUFFER_UNDERFLOW`, kiểm tra kích thước datagram, framing/record hợp lệ và nguồn nhận, thay vì mặc định nối hai UDP packet. Nếu provider buffer handshake message đến sớm, trạng thái phù hợp là `NEED_UNWRAP_AGAIN`.
- Kích thước datagram hiệu quả bị giới hạn bởi path MTU, overhead IP/UDP và DTLS; cấu hình 1200 byte là một **lựa chọn lab**, không phải hằng số đúng cho mọi mạng.

### 5.3. Timer và mất gói

Khi đang `NEED_UNWRAP` và socket hết thời gian chờ, gọi `wrap` để provider xem có cần phát lại handshake record. Ứng dụng phải phát mọi record retransmission được tạo, đặt deadline và backoff phù hợp, đồng thời ngừng sau ngưỡng thử hợp lý. Nếu một bên đã nhận đủ handshake còn phía kia thiếu flight cuối, ứng dụng cũng cần xử lý trạng thái/timer phù hợp.

Ví dụ lỗi dễ gặp:

- **Không có timeout:** hai bên chờ `NEED_UNWRAP` mãi khi packet mất.
- **Luôn gọi `unwrap` trên buffer rỗng:** khác với trạng thái đặc biệt `NEED_UNWRAP_AGAIN`, việc đang `NEED_UNWRAP` thông thường cần một datagram mới.
- **Chỉ gọi `wrap` một lần cho cả handshake flight:** có thể chưa phát hết các record cần gửi.
- **Tưởng handshake hoàn tất là dữ liệu đã có ACK:** DTLS xác thực/bảo mật payload, nhưng không xác nhận việc ứng dụng đã xử lý record.
- **Dùng duy nhất một thời hạn không giới hạn tác vụ:** cần giới hạn tổng thời gian, số vòng lặp, kích thước packet và resource cho từng peer để bảo vệ server.

### 5.4. Đóng phiên

Khi dừng phiên DTLS, ứng dụng cần `engine.closeOutbound()`, tiếp tục `wrap` để tạo cảnh báo đóng (`close_notify`) và gửi qua UDP; đồng thời nhận/xử lý cảnh báo đóng từ peer qua `unwrap`, rồi kết thúc phần inbound đúng lúc. `closeInbound()` trước khi nhận thông báo đóng hợp lệ có thể báo lỗi do kết thúc bất thường. Vì UDP không bảo đảm gói đóng được nhận, production cần quy tắc timeout/cleanup và không tái sử dụng engine đã đóng.

### 5.5. ALPN có vai trò gì?

`SSLParameters.setApplicationProtocols(String[])` có thể khai báo danh sách protocol ứng dụng theo thứ tự ưu tiên, ví dụ demo `telemetry/1`. Sau handshake, `engine.getApplicationProtocol()` cho biết kết quả lựa chọn nếu provider và peer đã thương lượng; ứng dụng cần bảo đảm kết quả là protocol mình hỗ trợ **trước khi** dispatch payload vào decoder tương ứng.

ALPN giúp tránh đoán payload thuộc protocol nào, nhưng **không tự xử lý retransmission hoặc định nghĩa serialization**. Một hệ thống chỉ có một định dạng thông điệp có thể không cần ALPN. Trong demo, cả client và server cùng cấu hình một nhãn nên kết quả dễ xác nhận.

## 6. Kiểm tra và xử lý sự cố

| Triệu chứng | Khả năng gây ra | Kiểm tra/cách xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException: DTLS` | Provider/JDK không hỗ trợ `DTLS` | Kiểm tra JDK và JSSE provider; không giả định bản DTLS 1.3 có sẵn |
| `SSLHandshakeException` / certificate path validation | Client không tin cậy chứng chỉ server, hoặc thiếu khóa riêng/chuỗi chứng chỉ | Kiểm tra PKCS#12, trust anchors, thời hạn cert và cấu hình KeyManager/TrustManager |
| `No subject alternative DNS name matching localhost` | SAN của chứng chỉ không khớp host đã cấu hình | Phát hành chứng chỉ có SAN phù hợp và xác minh đúng tên; không tắt hostname verification |
| Handshake treo ở `NEED_UNWRAP` | Datagram mất, gửi sai peer/port, thiếu timer | Kiểm tra địa chỉ, trạng thái, UDP receive timeout và đường retransmission |
| Luôn nhận `NEED_UNWRAP_AGAIN` nhưng không tiến | Không gọi `unwrap` để xử lý dữ liệu buffered | Gọi `unwrap` theo trạng thái đặc biệt, không chờ socket khi chưa cần |
| `BUFFER_OVERFLOW` / `BUFFER_UNDERFLOW` | Buffer quá nhỏ, datagram không đầy đủ hoặc xử lý vị trí `ByteBuffer` sai | Dùng buffer sizes từ session, `flip/clear` đúng chỗ, kiểm tra `offset/length` |
| Handshake thành công, không đọc được app data | Mất gói UDP, nhầm engine/session, sai vòng decode | Gắn datagram với đúng peer, xử lý `getStatus()` và kiểm tra thiết kế delivery ứng dụng |
| ALPN rỗng hoặc khác kỳ vọng | Không cùng danh sách, provider không thương lượng, chưa hoàn tất handshake | Kiểm tra `setApplicationProtocols` ở hai phía và kết quả sau handshake |
| Dùng `DTLSv1.3` gây `IllegalArgumentException` | Provider không công bố phiên bản được yêu cầu | Dùng danh sách supported protocols thực tế; với SunJSSE hiện nay tài liệu xác nhận DTLS 1.2 |

Để xem handshake ở môi trường lab, chạy:

```bash
java -Djavax.net.debug=ssl,handshake DtlsAlpnDemo
```

Debug JSSE rất nhiều dòng, có thể chứa metadata nhạy cảm về phiên/chứng chỉ. Bật ở môi trường kiểm thử phù hợp và không lấy nội dung debug làm giao thức ứng dụng.

## 7. Những gì ứng dụng production còn phải chịu trách nhiệm

1. **Kiểm soát danh tính:** truststore phù hợp với PKI, kiểm tra peer hostname hoặc danh tính được thiết kế; cân nhắc mTLS nếu cần định danh hai chiều. Không dùng `TrustManager` bỏ qua mọi chứng chỉ.
2. **Kiểm soát datagram:** định tuyến record tới đúng engine/session; phân biệt record chưa xác thực với payload đã giải mã, hạn chế dùng tài nguyên cho peer chưa hoàn tất handshake.
3. **Mất gói và thứ tự:** bổ sung ACK/sequence/idempotency hoặc lựa chọn giao thức khác khi business yêu cầu bảo đảm giao hàng; DTLS không thực hiện thay.
4. **Kích thước/tốc độ:** tính MTU, xử lý `BUFFER_OVERFLOW`, giới hạn bộ nhớ/socket buffer, timeout và số retry. Tránh một datagram lớn gây IP fragmentation không kiểm soát.
5. **Quản lý vòng đời:** bắt đầu handshake, kiểm tra kết quả, đổi trạng thái sang application data, đóng bằng `close_notify` khi có thể, dọn timeout sessions.
6. **Khả năng tương thích:** kiểm thử thực sự với JDK, provider, cipher suites và thiết bị mạng dự kiến; SunJSSE công bố DTLS 1.2, còn đặc tả DTLS 1.3 tồn tại ở cấp tiêu chuẩn quốc tế nhưng không tự động xuất hiện trong mọi JDK.
7. **ALPN (nếu dùng):** dispatch theo protocol thực tế đã thương lượng, không tin một chuỗi protocol do peer tự khai báo trong payload mà chưa qua handshake.

## 8. Câu hỏi tự kiểm tra

1. Vì sao `SSLEngine` không đủ để tạo ứng dụng DTLS nếu không có `DatagramSocket` hoặc `DatagramChannel`?
2. Khi `engine.getHandshakeStatus() == NEED_WRAP`, dữ liệu nguồn `ByteBuffer.allocate(0)` có thể tạo bản tin gì?
3. Khi gặp `NEED_UNWRAP_AGAIN`, vì sao chờ thêm UDP packet có thể khiến handshake treo?
4. Ai cấp timer và ra quyết định retransmission handshake? DTLS có tự gửi lại payload ứng dụng bị mất không?
5. `SSLParameters.setMaximumPacketSize` liên quan đến vấn đề gì? Vì sao phải quan tâm UDP path MTU?
6. Vì sao phải ánh xạ peer/session và kiểm tra chứng chỉ server ngay cả khi mạng UDP “đã mã hóa”?
7. Trong ví dụ, `getSession().getProtocol()` và `getApplicationProtocol()` trả hai loại thông tin khác nhau ra sao?
8. Đổi `trust.p12` sang một file rỗng sẽ ảnh hưởng handshake như thế nào? Tại sao không nên sửa bằng cách bỏ qua trust validation?

**Điều cần nhớ:** `SSLEngine` mang bảo mật DTLS vào record; **ứng dụng** phải tạo/chuyển UDP datagram, điều khiển handshake state, timeout, retransmission và vòng đời peer. Dùng `DTLSv1.2` được SunJSSE hỗ trợ, certificate/trust validation thật, ALPN khi có nhu cầu và thiết kế xử lý mất gói ở tầng ứng dụng.

## Tài liệu chính thức

- [Oracle Java 25 — JSSE Reference Guide, SSLEngine for DTLS Protocols](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html): tạo engine, handshake state, retransmission, `NEED_UNWRAP_AGAIN` và một record cho mỗi `wrap` DTLS.
- [Oracle Java 25 — SSLEngine API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html): `wrap`, `unwrap`, trạng thái, kích thước buffer và đóng phiên.
- [Oracle Java 25 — SSLParameters API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setMaximumPacketSize`, `setEnableRetransmissions`, ALPN, xác minh endpoint.
- [Oracle Java 25 — SunJSSE protocol support](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html): giao thức DTLS nhà cung cấp công bố.
- [IETF RFC 9147 — DTLS 1.3](https://www.rfc-editor.org/rfc/rfc9147.html): đặc tả mới hơn để phân biệt trạng thái chuẩn DTLS với khả năng provider cụ thể.
