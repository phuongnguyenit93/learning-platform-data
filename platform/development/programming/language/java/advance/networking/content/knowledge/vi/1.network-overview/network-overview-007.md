# Bản đồ API mạng Java: `java.net`, `java.nio.channels`, `java.net.http`, JSSE và `jdk.httpserver`

Trong Java, “làm việc với mạng” có thể là phân giải tên miền, mở kết nối TCP, gửi datagram UDP, xây dựng một giao thức riêng, gọi REST API qua HTTPS hoặc nhận HTTP request. Các công việc này nằm ở **những mức trừu tượng khác nhau**. Chọn đúng API giúp tránh tự triển khai lại HTTP, xử lý sai ranh giới dữ liệu TCP hoặc vô tình bỏ qua xác thực TLS.

Bài này tập trung vào **bản đồ lựa chọn API của JDK**, áp dụng cho **Java 17+**. Một số phần khác biệt theo phiên bản sẽ được ghi rõ. Đây là bài về API mạng Java SE/JDK, chưa đi vào framework web như Spring MVC, WebFlux hay Netty.

## 1. Mục tiêu và bức tranh tổng thể

Sau bài học, bạn có thể:

- Nhận diện đúng package, module, vai trò client/server và giao thức của từng nhóm API.
- Chọn `Socket`/`ServerSocket`, channel + `Selector`, `HttpClient`, JSSE hoặc `HttpServer` theo nhu cầu thực tế.
- Hiểu HTTP là giao thức ứng dụng, TLS là lớp bảo vệ kết nối, TCP/UDP là cơ chế truyền tải; chúng không phải những tên gọi thay thế cho nhau.
- Phân biệt I/O blocking, non-blocking và asynchronous; hiểu vì sao `read()` không đồng nghĩa với “đã nhận đủ một thông điệp”.
- Chạy ví dụ HTTP client/server hoàn toàn bằng JDK, có timeout, đóng tài nguyên và đầu ra kiểm chứng được.

### Bảng định vị nhanh

| Nhóm | Module chứa API | Lớp/kiểu tiêu biểu | Công việc chính | Có sẵn vai trò nào? |
| --- | --- | --- | --- | --- |
| `java.net` | `java.base` | `InetAddress`, `InetSocketAddress`, `URI`, `Socket`, `ServerSocket`, `DatagramSocket` | Địa chỉ, TCP/UDP mức thấp, URI/URL | TCP client/server; UDP endpoint |
| `java.nio.channels` cùng `java.nio.ByteBuffer` | `java.base` | `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`, `Selector`, `SelectionKey` | I/O theo buffer; multiplex nhiều channel; tùy chọn non-blocking | TCP/UDP client/server mức thấp |
| `java.net.http` | `java.net.http` | `HttpClient`, `HttpRequest`, `HttpResponse`, `WebSocket` | HTTP/1.1, HTTP/2 và WebSocket client | **Client**; không phải HTTP server |
| JSSE: `javax.net.ssl` | `java.base` | `SSLContext`, `SSLSocket`, `SSLServerSocket`, `SSLEngine`, `SSLParameters` | TLS, chứng chỉ và xác thực peer | TLS client/server; không định nghĩa HTTP |
| `com.sun.net.httpserver` | `jdk.httpserver` | `HttpServer`, `HttpsServer`, `HttpExchange`, `HttpHandler` | HTTP/HTTPS server nhỏ, đơn giản | **Server**; không phải HTTP client |

> **Điểm dễ nhầm:** `java.net.http` là package thuộc module `java.net.http`; còn `jdk.httpserver` là module **khác**, cung cấp package `com.sun.net.httpserver`. JSSE được gọi bằng tên công nghệ; các lớp chủ chốt của nó thuộc `javax.net.ssl`, không phải package `jsse`.

Có thể hình dung luồng lựa chọn:

~~~text
Bạn muốn trao đổi dữ liệu mạng?
|
+-- Chỉ cần địa chỉ, hostname, port, URI? --> java.net
|
+-- Gọi HTTP(S) API từ Java? -------------> java.net.http.HttpClient
|                                          (TLS HTTPS được xử lý bên dưới)
|
+-- Nhận HTTP request bằng JDK? ----------> jdk.httpserver.HttpServer
|                                          hoặc HttpsServer + cấu hình TLS
|
+-- Giao thức TCP/UDP tùy biến?
    |
    +-- I/O stream blocking, đơn giản ----> java.net.Socket / ServerSocket
    |                                      hoặc DatagramSocket cho UDP
    |
    +-- ByteBuffer, nhiều kết nối,        -> java.nio.channels
    |   multiplex event loop?               (+ Selector khi non-blocking)
    |
    +-- Cần bảo vệ kết nối bằng TLS? ------> JSSE:
                                           SSLSocket hoặc SSLEngine
~~~

Sơ đồ thể hiện **điểm vào của lập trình viên**, không khẳng định mỗi package tương ứng một tầng OSI. Chẳng hạn `HttpClient` dùng transport và TLS qua triển khai bên dưới; thông thường người gọi không phải tự tạo socket.

## 2. Phân biệt giao thức, kết nối và dữ liệu

- **IP/địa chỉ:** xác định điểm đến ở tầng mạng. `InetAddress` biểu diễn địa chỉ IP; `InetSocketAddress` ghép địa chỉ/tên host với port.
- **TCP:** dòng byte **có thứ tự, đáng tin cậy trong phạm vi kết nối còn hoạt động**, không giữ ranh giới message của ứng dụng. Một lần gửi có thể được nhận qua nhiều lần `read()`, hoặc nhiều lần gửi có thể được gộp khi đọc.
- **UDP:** truyền từng datagram, giữ ranh giới gói ở API nhưng không bảo đảm giao hàng, thứ tự hay loại bỏ trùng lặp. Datagram quá lớn có thể bị phân mảnh/mất.
- **HTTP:** giao thức ứng dụng gồm method, URI, headers, status và body; chạy trên kết nối do client/server HTTP quản lý. `HttpClient` xử lý cú pháp/giao thức để ứng dụng tập trung vào request và response.
- **TLS:** cơ chế mật mã để bảo vệ tính bí mật, toàn vẹn và xác thực peer bằng chứng chỉ/cấu hình tin cậy. **HTTPS = HTTP qua TLS** trong các phiên bản HTTP phù hợp; TLS tự nó không tạo HTTP request.

Ví dụ: “gửi JSON POST đến `https://api.example.com/items`” là **HTTP client**, vì vậy bắt đầu bằng `HttpClient`. “Gửi frame nhị phân của giao thức riêng qua TCP” là **socket/channel**, sau đó cân nhắc JSSE nếu cần TLS. Không chọn API thấp chỉ vì HTTP cũng dùng mạng.

## 3. `java.net`: địa chỉ, URI và socket truyền thống

### 3.1. Các kiểu địa chỉ và tài nguyên

- `InetAddress`: biểu diễn IPv4/IPv6; `InetAddress.getByName("example.com")` có thể thực hiện phân giải tên. Việc phân giải phụ thuộc DNS/môi trường và có thể thất bại (`UnknownHostException`).
- `InetSocketAddress`: endpoint gồm host/IP và port. Dùng khi `connect`, `bind`; `new InetSocketAddress("127.0.0.1", 8080)` là endpoint loopback port 8080.
- `NetworkInterface`: truy vấn interface và địa chỉ mạng của máy; hữu ích khi làm việc đa NIC, IPv4/IPv6 hoặc multicast.
- `URI`: mô hình cú pháp một định danh, có scheme, authority, path, query, fragment; tạo `URI` không tự kết nối mạng. URI có thể tương đối.
- `URL`/`URLConnection`: API cũ hơn để định vị/mở kết nối tài nguyên. Với HTTP client mới, thường ưu tiên `java.net.http.HttpClient`; `URI` vẫn dùng để chỉ địa chỉ request.

Ví dụ phân biệt:

~~~java
URI endpoint = URI.create("https://example.com:443/api/items?page=2");
String scheme = endpoint.getScheme(); // "https"
String host = endpoint.getHost();     // "example.com"
int port = endpoint.getPort();        // 443
~~~

Đây là **đoạn mã minh họa bên trong một phương thức** (cần `import java.net.URI;`), không gửi request. Khi nhận URI từ nguồn không tin cậy, cần kiểm soát scheme, host, port và chính sách redirect để tránh SSRF/truy cập đích nội bộ ngoài ý muốn.

### 3.2. TCP blocking: `Socket` và `ServerSocket`

- **Client:** `Socket` kết nối tới TCP endpoint; `getInputStream()` và `getOutputStream()` đọc/ghi byte.
- **Server:** `ServerSocket.bind(...)` mở cổng lắng nghe; `accept()` trả về **một `Socket` mới cho kết nối đã chấp nhận**. Socket lắng nghe và socket kết nối có vòng đời khác nhau.
- `connect(endpoint, timeoutMillis)` giới hạn thời gian **thiết lập kết nối**; `socket.setSoTimeout(timeoutMillis)` giới hạn thời gian chờ của thao tác đọc blocking tương ứng. Chúng không phải một timeout chung cho toàn bộ giao dịch.
- `InputStream.read(...)` có thể nhận ít byte hơn yêu cầu, trả `-1` khi hết stream; điều đó **không** có nghĩa mỗi `read` tương ứng một message.
- Đóng `Socket` bằng try-with-resources; thiết kế cách phát hiện EOF, lỗi và hủy kết nối.

Mẫu cấu hình TCP client (đoạn mã minh họa trong phương thức; cần server thật tại `host:port`):

~~~java
try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress("host.example", 9000), 2_000);
    socket.setSoTimeout(3_000);
    InputStream in = socket.getInputStream();
    OutputStream out = socket.getOutputStream();
    // Gửi/nhận theo framing của giao thức ứng dụng.
}
~~~

Các import cho đoạn trên: `java.net.Socket`, `java.net.InetSocketAddress`, `java.io.InputStream`, `java.io.OutputStream`. Port và hostname chỉ là **giá trị ví dụ**, không phải địa chỉ dịch vụ được bảo đảm hoạt động.

Với TCP, ứng dụng **phải tự định nghĩa framing**, ví dụ:

1. Mỗi message kết thúc bằng `\\n` (cần quy ước escape và charset).
2. Mỗi message có prefix độ dài 4 byte theo thứ tự byte xác định, rồi chính xác N byte dữ liệu.
3. Có delimiter hoặc cấu trúc tương đương (cần xử lý giới hạn kích thước).

Không được dùng `in.available()` để kết luận đã nhận đủ message; nó chỉ cho biết lượng byte có thể đọc ngay mà không blocking trong điều kiện triển khai, không phải tổng độ dài message.

### 3.3. UDP: `DatagramSocket`, `DatagramPacket`

`DatagramSocket` gửi/nhận các `DatagramPacket` gồm byte, địa chỉ và port. Khác TCP, không có `accept()` cho từng kết nối; ứng dụng cần tự giải quyết mất gói, retry, thứ tự và trùng lặp **nếu giao thức đòi hỏi**. `MulticastSocket` liên quan đến multicast; mức channel có `DatagramChannel`.

Ví dụ send một UDP datagram loopback (minh họa trong phương thức; không có receiver nên không mong đợi output):

~~~java
byte[] payload = "ping".getBytes(StandardCharsets.UTF_8);
try (DatagramSocket udp = new DatagramSocket()) {
    DatagramPacket packet = new DatagramPacket(
        payload, payload.length, InetAddress.getLoopbackAddress(), 9999);
    udp.send(packet);
}
~~~

Các import: `java.net.DatagramSocket`, `java.net.DatagramPacket`, `java.net.InetAddress`, `java.nio.charset.StandardCharsets`. Gửi thành công **không** chứng minh bên nhận đã nhận hay xử lý gói.

## 4. `java.nio.channels`: channel, buffer và multiplexing

NIO không đồng nghĩa “tự động nhanh hơn” hoặc “luôn non-blocking”. Nhiều channel có thể hoạt động **blocking**; `SocketChannel` mới tạo thường ở chế độ blocking. Chỉ khi gọi `configureBlocking(false)` trên selectable channel mới thực hiện các thao tác theo mô hình non-blocking phù hợp và đăng ký `Selector`.

| Thành phần | Vai trò |
| --- | --- |
| `SocketChannel` | TCP endpoint cho kết nối, đọc/ghi qua `ByteBuffer` |
| `ServerSocketChannel` | TCP listener; `accept()` trả `SocketChannel` |
| `DatagramChannel` | UDP qua `ByteBuffer` |
| `Selector` | Chờ sự kiện readiness của nhiều `SelectableChannel` trong một event loop |
| `SelectionKey` | Dùng `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE` để theo dõi điều kiện sẵn sàng |
| `AsynchronousSocketChannel` / `AsynchronousServerSocketChannel` | API asynchronous hoàn tất qua `Future` hoặc `CompletionHandler`; khác với event loop `Selector` |

### 4.1. Vòng đời `ByteBuffer`

Một buffer có `capacity`, `position`, `limit`:

~~~text
Khi nhận byte:
channel.read(buffer) -> buffer.flip() -> xử lý byte hợp lệ
                   -> buffer.compact() hoặc clear() -> lần đọc kế tiếp
Khi gửi byte:
buffer chứa byte -> buffer.flip() -> channel.write(buffer)
                  -> ghi tiếp khi buffer.hasRemaining()
~~~

- `flip()`: chuyển từ trạng thái ghi vào buffer sang đọc ra buffer.
- `clear()`: đặt lại chỉ số để ghi mới; **không xóa byte vật lý**.
- `compact()`: giữ phần byte chưa tiêu thụ rồi chuyển vị trí để ghi tiếp.
- `SocketChannel.read(buffer)` trong non-blocking có thể trả `0`; trong cả hai chế độ có thể đọc ít hơn số byte mong muốn; `-1` báo peer đã đóng hướng gửi.
- `write(buffer)` có thể ghi **một phần** số byte còn trong buffer. Phải giữ phần còn lại và ghi tiếp theo điều kiện phù hợp; không giả định một lần `write` đã gửi hết.
- UTF-8 có thể bị chia giữa nhiều lần `read`; decoder/framing phải xử lý byte chưa đủ, không tùy tiện giải mã từng mảnh thành `String`.

### 4.2. Selector làm gì?

Quy trình điển hình:

1. Mở `ServerSocketChannel`, bind và `configureBlocking(false)`.
2. Mở `Selector`, đăng ký server channel với `OP_ACCEPT`.
3. Vòng lặp `selector.select()` đợi ít nhất một channel sẵn sàng; duyệt `selectedKeys()`.
4. Với `OP_ACCEPT`, gọi `accept()`, cấu hình accepted channel thành non-blocking và đăng ký `OP_READ`.
5. Với `OP_READ`, đọc buffer, tích lũy frame, xử lý; với `OP_WRITE`, phát phần dữ liệu còn chưa gửi.
6. Xóa key đã xử lý khỏi tập selected, xử lý kết nối lỗi/EOF và đóng tài nguyên.

**Readiness không bảo đảm** rằng một thao tác sẽ đọc/ghi đủ dữ liệu. Đặc biệt, để `OP_WRITE` luôn đăng ký khi không có dữ liệu chờ có thể làm event loop quay liên tục vì socket thường sẵn sàng ghi. Nên bật nó khi có dữ liệu tồn đọng và tắt khi đã gửi hết.

Mô hình này phù hợp khi phải quản lý nhiều kết nối đồng thời, framing và trạng thái rõ ràng. Đổi lại, ứng dụng chịu trách nhiệm state machine, backpressure, partial I/O và dọn dẹp key/channel. Với số kết nối vừa phải và xử lý đơn giản, blocking I/O thường dễ đọc, kiểm thử và bảo trì hơn. Java 21+ còn có virtual threads giúp diễn đạt nhiều tác vụ blocking theo kiểu trực quan; đó là **lựa chọn concurrency**, không thay đổi semantics của TCP hay framing.

## 5. `java.net.http`: HTTP client cấp cao

Đây là API chuẩn từ Java 11 để gửi HTTP request, nhận HTTP response và tạo WebSocket client. Package này thuộc module `java.net.http`, độc lập với module `jdk.httpserver`.

- `HttpClient`: cấu hình HTTP version ưu tiên, redirect policy, proxy, executor, cookie handler, authenticator, TLS, connect timeout. Tái sử dụng instance để hưởng lợi từ quản lý kết nối.
- `HttpRequest`: URI, method (`GET`, `POST`, ...), headers, body publisher, timeout mỗi request.
- `HttpResponse<T>`: status code, headers, URI/version và body kiểu `T`, thông qua `BodyHandlers` (String, byte array, file, stream...).
- `send(request, handler)`: gọi **đồng bộ**, đợi kết quả; `sendAsync(...)`: trả `CompletableFuture<HttpResponse<T>>`, không chặn thread gọi cho đến khi response hoàn tất.
- `WebSocket`: client giao thức WebSocket; có builder/listener, không biến `HttpClient` thành WebSocket server.

HTTP/2 được hỗ trợ và thường là phiên bản ưu tiên, nhưng phiên bản dùng thực tế tùy server, TLS/ALPN và negotiation; có thể về HTTP/1.1. Đừng mặc định mọi request đều là HTTP/2. API này **không triển khai HTTP/3 như một khả năng tiêu chuẩn của Java 17/21**.

Một minh họa cho lời gọi HTTPS (đoạn mã trong phương thức, cần kết nối mạng):

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
System.out.println(response.statusCode());
~~~

Các import: `java.net.URI`, `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `java.time.Duration`, `java.nio.charset.StandardCharsets`. Phương thức chứa đoạn này phải xử lý/khai báo `IOException` và `InterruptedException`. Trạng thái HTTP 4xx/5xx **vẫn là response hợp lệ**; tự kiểm tra `statusCode()`, không kỳ vọng `send()` luôn ném exception cho lỗi ứng dụng.

Với async:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
future.thenAccept(r -> System.out.println(r.statusCode()));
~~~

Đây là đoạn minh họa sử dụng `client` và `request` đã tạo ở trên; cần import `java.util.concurrent.CompletableFuture`. Code production cần quản lý completion, timeout, hủy tác vụ và lỗi `CompletableFuture`; nếu chương trình kết thúc trước khi future hoàn tất thì callback không được bảo đảm đã chạy.

**Timeout khác nhau:** `connectTimeout` chỉ khống chế giai đoạn kết nối; `HttpRequest.Builder.timeout` là timeout cho request/response được định nghĩa bởi API. Các tác vụ streaming, retry, cancellation và deadline toàn nghiệp vụ vẫn phải được thiết kế rõ ràng. Tránh đọc toàn bộ body lớn vào RAM khi có thể stream hoặc ghi file.

## 6. JSSE (`javax.net.ssl`): bảo vệ kết nối bằng TLS

JSSE là Java Secure Socket Extension, cho phép TLS ở lớp truyền tải. Nó **không** tự xây HTTP request, routing hay JSON. Những thành phần trung tâm gồm:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `SSLContext` | Cấu hình giao thức TLS và tạo factory/`SSLEngine`; có thể khởi tạo bằng key/trust manager |
| `SSLSocket` / `SSLServerSocket` | TCP socket có TLS, thích hợp với mô hình stream blocking |
| `SSLEngine` | Bộ xử lý TLS độc lập transport; lập trình viên phải tự điều phối wrap/unwrap, handshake, buffer và I/O, thường khi dùng NIO |
| `SSLParameters` | Cấu hình TLS như endpoint identification, cipher suites/protocols thích hợp, SNI/ALPN khi cần |
| `KeyManager` / `KeyManagerFactory` | Cung cấp chứng chỉ và private key của **bên mình**, khi cần TLS server hoặc mutual TLS |
| `TrustManager` / `TrustManagerFactory` | Xây dựng quyết định tin cậy đối với chứng chỉ **bên kia** |
| `KeyStore` (`java.security`) | Nơi lưu key/chứng chỉ hoặc tập chứng chỉ tin cậy, tùy cấu hình |

Ở **HTTPS client** thông thường, `HttpClient` sử dụng TLS/cơ chế trust mặc định của nền tảng; ứng dụng không cần trực tiếp gọi `SSLSocket`. JSSE quan trọng khi xây giao thức TCP bảo mật riêng, yêu cầu mTLS/truststore tùy biến hoặc tích hợp TLS vào event loop.

Ví dụ minh họa **chỉ bắt tay TLS**, chưa gửi HTTP (đặt trong phương thức `throws Exception`, có mạng tới example.com:443):

~~~java
SSLContext context = SSLContext.getDefault();
try (SSLSocket socket = (SSLSocket) context.getSocketFactory()
        .createSocket("example.com", 443)) {
    SSLParameters params = socket.getSSLParameters();
    params.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(params);
    socket.startHandshake();
}
~~~

Các import: `javax.net.ssl.SSLContext`, `SSLSocket`, `SSLParameters`. Thiết lập `HTTPS` endpoint identification **trước handshake** để kiểm tra tên host so với chứng chỉ. Với raw `SSLSocket`/`SSLEngine`, không được mặc định ứng dụng đã có hostname verification phù hợp; phải cấu hình/xác minh chủ động. Đồng thời cần chain-of-trust phù hợp. Bỏ kiểm tra certificate, viết trust manager “tin mọi chứng chỉ” hoặc vô hiệu hóa hostname verification chỉ để “chạy được” tạo lỗ hổng MITM.

Các bước TLS khái quát: tạo kết nối TCP → thương lượng phiên bản/cipher và nhận chứng chỉ → xác thực peer và hoàn tất handshake → truyền application data được bảo vệ. Với `SSLEngine`, trạng thái `NEED_WRAP`, `NEED_UNWRAP`, `NEED_TASK` và kích thước buffer phải được điều phối đúng; dùng `SSLEngine` không tự biến channel thành HTTPS.

### Hai câu hỏi bảo mật phải tách biệt

- **Truststore:** “Tôi tin CA/chứng chỉ nào để xác thực bên kia?”
- **Keystore/identity:** “Tôi trình ra chứng chỉ/private key nào để chứng minh danh tính mình?” (server TLS thường cần; client chỉ cần khi mTLS yêu cầu).

Cần thêm kiểm tra **host name** (dịch vụ được gọi có đúng tên được chứng nhận không), thời hạn chứng chỉ và các giới hạn TLS theo chính sách JDK. TLS mã hóa đường truyền nhưng không thay thế xác thực/ủy quyền nghiệp vụ ở HTTP hay ứng dụng.

## 7. `jdk.httpserver`: HTTP server gọn nhẹ của JDK

Module `jdk.httpserver` xuất package `com.sun.net.httpserver`, với:

- `HttpServer`: tạo HTTP listener, đăng ký context theo path, start/stop.
- `HttpHandler`: xử lý `HttpExchange` cho request.
- `HttpExchange`: đọc method/URI/request headers/body; thiết lập response headers, status, độ dài và ghi response body.
- `HttpsServer` + `HttpsConfigurator`: biến listener thành HTTPS khi được cấu hình `SSLContext` và chứng chỉ đúng cách.
- `jwebserver`/`SimpleFileServer` (JDK hiện đại): tiện phục vụ tài nguyên tĩnh cho phát triển, thử nghiệm.

`HttpServer` có ích cho demo, mock, callback hoặc HTTP endpoint nhỏ trong môi trường được kiểm soát. Nó **không phải web framework đầy đủ**: thiếu nhiều tiện ích có sẵn cho validation, dependency injection, observability, reverse proxy, middleware bảo mật... Khi xây API production public, phải thiết kế rõ xác thực, giới hạn payload, timeout, thread/executor, logging, chống lạm dụng và triển khai TLS/proxy; framework/server chuyên dụng thường phù hợp hơn.

`HttpServer.create(address, backlog)` bind socket; `createContext(path, handler)` đăng ký xử lý; `start()` cho phép nhận request; `stop(delaySeconds)` dừng server. Handler phải đóng response stream/exchange để tài nguyên được giải phóng. Với response dài cố định, `sendResponseHeaders(status, byteLength)` cần **số byte UTF-8 thực tế**, không phải `String.length()`; ghi đúng số byte đã khai báo.

## 8. Ví dụ chạy được: Java HTTP server và HTTP client trong cùng một tiến trình

Ví dụ dùng hai nhóm API: `com.sun.net.httpserver.HttpServer` **nhận** HTTP request và `java.net.http.HttpClient` **gửi** HTTP request. Hai bên giao tiếp qua `127.0.0.1`; port `0` yêu cầu hệ điều hành chọn cổng còn trống, tránh xung đột cố định. Đây là HTTP rõ ràng trên loopback để minh họa bản đồ API, **chưa có TLS**.

Tạo tệp **`NetworkApiMapDemo.java`** với nội dung:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class NetworkApiMapDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/hello", exchange -> {
            byte[] payload = "Xin chào từ JDK HTTP Server"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, payload.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(payload);
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();
            URI uri = URI.create(
                    "http://127.0.0.1:" + port + "/hello");

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            System.out.println("HTTP " + response.statusCode());
            System.out.println(response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file bằng JDK 17+:

~~~bash
javac --add-modules jdk.httpserver NetworkApiMapDemo.java
java --add-modules jdk.httpserver NetworkApiMapDemo
~~~

**Stdout kỳ vọng khi môi trường cho phép bind loopback:**

~~~text
HTTP 200
Xin chào từ JDK HTTP Server
~~~

Giải thích từng bước:

1. `HttpServer.create(..., 0)` tạo server lắng nghe địa chỉ `127.0.0.1`, dùng cổng ngẫu nhiên được hệ điều hành chọn.
2. `createContext("/hello", ...)` đăng ký handler; server trả header `Content-Type` và status `200`.
3. `payload.length` là độ dài **byte** UTF-8; `try` đóng response stream sau khi ghi đúng lượng byte.
4. `server.start()` cho phép server nhận kết nối. `getAddress().getPort()` đưa đúng cổng đã bind cho client.
5. `HttpClient` xây HTTP GET, gửi đồng bộ, nhận body kiểu `String` và in status/body.
6. `finally` đảm bảo dừng listener kể cả khi gửi request hoặc đọc response ném exception.

**Cần nhớ:** ví dụ này không cần tạo `Socket`, `SocketChannel` hay `SSLSocket` bằng tay, vì HTTP client/server đã che phần transport. Khi đổi sang `https://`, không thể đơn thuần thay scheme cho `HttpServer`: cần triển khai `HttpsServer`, cấu hình chứng chỉ/`SSLContext` và dùng URI HTTPS.

## 9. Lựa chọn API theo tình huống thực tế

| Tình huống | Bắt đầu từ API | Lý do |
| --- | --- | --- |
| Java service gọi REST/JSON tới HTTPS endpoint | `java.net.http.HttpClient` | Có sẵn method, header, status, body, TLS, HTTP version và async |
| Mock webhook/callback server local hoặc demo HTTP | `jdk.httpserver.HttpServer` | Dựng endpoint nhỏ mà không cần framework |
| TCP client/server cho giao thức byte riêng, ít kết nối | `java.net.Socket`/`ServerSocket` | Stream blocking đơn giản, dễ gắn framing |
| UDP telemetry/game protocol tự định nghĩa | `DatagramSocket` hoặc `DatagramChannel` | Gửi/nhận datagram, chấp nhận semantics UDP |
| Một event loop quản lý nhiều TCP connection và buffer | `SocketChannel` + `Selector` | Multiplex readiness, điều khiển backpressure |
| Giao thức TCP riêng phải mã hóa và xác thực | `SSLSocket` hoặc `SSLEngine` + socket/channel | JSSE bảo vệ byte stream, không tự định nghĩa giao thức |
| HTTP server có yêu cầu production lớn | Framework/server được thiết kế cho môi trường đó | `jdk.httpserver` chỉ cung cấp bộ API server tối giản |

**Quy trình quyết định hợp lý:**

1. Xác định **giao thức ứng dụng**: HTTP, WebSocket hay frame nhị phân riêng?
2. Xác định **vai trò**: outbound client, inbound server hay cả hai?
3. Chọn **transport**: TCP hay UDP? Có yêu cầu thứ tự/độ tin cậy/ranh giới message không?
4. Chọn **mô hình I/O**: blocking, non-blocking event loop hay asynchronous completion; cân nhắc độ phức tạp và số kết nối.
5. Quyết định **bảo mật**: TLS/mTLS, hostname validation, truststore, key material; `https` đã có TLS ở tầng HTTP client.
6. Thiết kế **protocol framing, timeout, giới hạn kích thước, retry/idempotency, đóng tài nguyên và quan sát lỗi** trước khi scale.

Không có quy tắc “NIO luôn tốt hơn socket” hoặc “HTTPS cần tự code `SSLSocket`”. Hãy chọn mức trừu tượng cao nhất đủ thể hiện đúng giao thức của bài toán.

## 10. Lỗi thường gặp và cách tự kiểm tra

| Nhầm lẫn/lỗi | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `Socket` rồi tự ghép chuỗi `GET / HTTP/1.1` cho REST API | Phải tự xử lý framing HTTP, redirect, content length, proxy, TLS... | Dùng `HttpClient` |
| Tưởng `Socket.read()` nhận trọn một request | Message bị thiếu/cắt/gộp | Định nghĩa framing và lặp đọc đủ dữ liệu |
| Gọi `write(ByteBuffer)` một lần rồi bỏ phần còn lại | Mất byte ở tầng ứng dụng khi non-blocking | Kiểm tra `buffer.hasRemaining()` và gửi tiếp |
| `register(OP_WRITE)` liên tục khi không có dữ liệu gửi | Event loop có thể quay nóng, tốn CPU | Chỉ bật `OP_WRITE` khi pending output |
| Tưởng `java.net.http` chứa HTTP server | Chọn nhầm module/API | `HttpClient` ở `java.net.http`, `HttpServer` ở `jdk.httpserver` |
| Tưởng `SSLSocket` luôn xác minh hostname giống HTTPS client | Có thể chấp nhận peer sai tên | Đặt endpoint identification algorithm và kiểm tra chuỗi chứng chỉ |
| Dùng trust manager chấp nhận mọi chứng chỉ | Dễ bị MITM | Thiết lập truststore hợp lệ, không tắt verification |
| Xem HTTP 404/500 là lỗi socket tự động ném exception | Không xử lý trạng thái nghiệp vụ | Đọc `HttpResponse.statusCode()` |
| Chỉ cấu hình connect timeout | Có thể treo ở đọc response/ứng dụng | Thêm request/read deadline và cancellation thích hợp |
| Bind demo server vào mọi interface thay vì loopback | Vô tình mở endpoint ra mạng | Với demo local dùng `127.0.0.1` |
| Quên đóng stream/socket/exchange | Rò rỉ descriptor/kết nối | `try-with-resources`, `finally`, dừng listener |
| Nhầm `String.length()` với byte count khi gửi HTTP UTF-8 | Sai `Content-Length`, response bị ngắt | Tạo `byte[]`, dùng `bytes.length` |

Khi chẩn đoán lỗi, tách các tầng:

- **DNS/địa chỉ:** `UnknownHostException`, sai host/port, firewall.
- **TCP/UDP:** `ConnectException`, timeout, EOF, peer đóng kết nối, UDP mất gói.
- **TLS:** `SSLHandshakeException`, CA không tin cậy, tên host sai, giao thức/cipher không tương thích.
- **HTTP:** status, redirect, body, media type, header, timeout; 4xx/5xx khác với việc không kết nối được.
- **I/O loop:** partial read/write, buffer state, selector key và timeout/cancellation chưa được dọn.

## 11. Bài tập tự kiểm tra có đáp án

**Bài 1.** Một ứng dụng cần gọi `POST https://api.example.com/orders` với JSON. Có nên bắt đầu bằng `SocketChannel` không?

**Đáp án:** Thông thường không. Dùng `HttpClient` + `HttpRequest.BodyPublishers.ofString(json, UTF_8)`, thêm `Content-Type: application/json`, timeout và kiểm tra status/body. Channel mức thấp chỉ cần khi có ràng buộc giao thức đặc biệt mà HTTP client không đáp ứng.

**Bài 2.** TCP server đọc một lần được 3 byte trong khi frame đã khai báo 100 byte. Điều đó có chứng minh bên gửi chỉ gửi 3 byte?

**Đáp án:** Không. TCP là byte stream; ứng dụng cần vòng lặp đọc đủ 100 byte (hoặc phát hiện EOF/timeout), kiểm tra giới hạn và ghép các lần đọc.

**Bài 3.** `SocketChannel` và `Selector` có tự mã hóa dữ liệu không?

**Đáp án:** Không. Chúng là cơ chế I/O. Nếu cần TLS cho giao thức riêng, phải tích hợp JSSE (thường `SSLEngine` cho event loop), hoặc chọn abstraction đã hỗ trợ TLS.

**Bài 4.** Một `HttpClient` gọi `https://` có nhất thiết phải được truyền `SSLSocket` bằng tay không?

**Đáp án:** Không. HTTP client tích hợp TLS qua triển khai/JDK; chỉ tùy biến `SSLContext`/cấu hình TLS khi có nhu cầu rõ ràng (mTLS, CA nội bộ, chính sách chứng chỉ).

**Bài 5.** Muốn viết một endpoint HTTP local phục vụ test, package nào có `HttpServer`? Nó có nằm trong `java.net.http` không?

**Đáp án:** `com.sun.net.httpserver.HttpServer` thuộc module `jdk.httpserver`, **không** thuộc `java.net.http`. Có thể compile/run với `--add-modules jdk.httpserver`.

## 12. Tài liệu chuẩn để tra cứu sâu

- `java.net` (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/package-summary.html
- `java.nio.channels` (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/package-summary.html
- `java.net.http` (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/module-summary.html
- `HttpClient` (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html
- Java Secure Socket Extension (JSSE) Reference Guide: https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html
- `jdk.httpserver` module (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/module-summary.html
- `HttpExchange.sendResponseHeaders` (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html

**Kết nối kiến thức:** từ yêu cầu nghiệp vụ, nhận diện HTTP hay protocol riêng; từ protocol xác định client/server và TCP/UDP; từ đặc tính tải chọn blocking/NIO; từ yêu cầu bảo mật quyết định TLS/JSSE. Đây chính là bản đồ để chọn đúng điểm vào của Java Networking API.
