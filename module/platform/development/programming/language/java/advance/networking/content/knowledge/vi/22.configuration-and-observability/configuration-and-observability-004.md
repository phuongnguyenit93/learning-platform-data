# Đọc địa chỉ local/remote, thời gian từng giai đoạn và số byte truyền trong Java Networking

Khi một kết nối TCP, UDP hoặc HTTP hoạt động chậm, chỉ ghi log “đã kết nối” hay “HTTP 200” thường không đủ để xác định lỗi. Bạn cần biết **kết nối/trao đổi đang chạy giữa hai endpoint nào**, **giai đoạn nào tốn thời gian** và **bao nhiêu byte thực sự đi qua phần chương trình bạn đang đo**. Java 17+ có nhiều API hữu ích, nhưng **không phải mọi API đều công bố tất cả các phép đo tầng mạng**. Quan sát chính xác phải luôn chỉ rõ **điểm đo, hướng dữ liệu, đơn vị và giới hạn suy luận**.

Bài thuộc nhóm **Cấu hình và quan sát** trong Java Advance – networking, tập trung ba nhóm thông tin:

1. **Local/remote address:** `Socket.getLocalSocketAddress()`, `Socket.getRemoteSocketAddress()`, `ServerSocket.accept()`, `SocketChannel.getLocalAddress()/getRemoteAddress()`, `HttpExchange.getLocalAddress()/getRemoteAddress()` và địa chỉ của datagram.
2. **Thời gian theo giai đoạn:** DNS lookup, TCP connect, TLS handshake, gửi request, chờ response, đọc response body và xử lý ở server. Dùng `System.nanoTime()` tính khoảng thời gian; **phân biệt thời điểm bạn đo được với giai đoạn bạn chỉ suy đoán**.
3. **Số byte:** tính **application payload bytes thực sự được đọc/ghi**, sử dụng `InputStream/OutputStream` wrappers, số byte trả về từ NIO `read/write`, `ByteBuffer.remaining()`, `HttpExchange` request/response body; phân biệt với `Content-Length`, ký tự UTF-8 và bytes truyền thật trên wire (có framing/TLS/header/retransmission).

Hai chương trình độc lập cuối bài dùng **Java 17**: TCP loopback echo PING/PONG và HTTP loopback POST/response. Cả hai được biên dịch bằng `javac --release 17`, chạy trên JDK tương thích và có output kiểm chứng; các giá trị milliseconds là **số đo động**, không cố định giữa các lần chạy.

## 1. Local và remote nghĩa là gì?

Một kết nối TCP có **hai đầu**: địa chỉ IP và port tại process của bạn (**local**) và tại peer ở phía kia (**remote**).

~~~text
                      Kết nối TCP duy nhất
        Client                                     Server
  local  = 127.0.0.1:ephemeral  ------------>  remote = 127.0.0.1:ephemeral
  remote = 127.0.0.1:serverPort <------------  local  = 127.0.0.1:serverPort
             |                                     |
       Socket phía client                   Socket sau accept()
~~~

Trong một kết nối trực tiếp trên cùng network namespace, *local của client* thường trùng *remote của socket server*, và *remote của client* trùng *local của socket server*. Nhưng đây là **hai góc nhìn về socket endpoints**, không phải tên DNS của service hay danh tính người dùng. Khi có NAT, load balancer, reverse proxy, SSH tunnel hoặc service mesh, địa chỉ trên một socket **không nhất thiết là địa chỉ gốc của end user hoặc máy đích nghiệp vụ**.

| Giá trị | Hỏi điều gì? | Ví dụ |
| --- | --- | --- |
| Local IP | Process này đã dùng interface/IP nào để trao đổi? | `127.0.0.1`, `192.0.2.10`, một IPv6 |
| Local port | Cổng trên process đang kết nối | Port ngẫu nhiên của client, port listener của server |
| Remote IP | IP của **socket peer trực tiếp** | Server, proxy hoặc upstream |
| Remote port | Port bên peer | `443`, `8080` hoặc ephemeral client |
| DNS hostname | Tên logic được resolve để tìm địa chỉ | `api.example.test` |
| HTTP URI | Đích logic và path mà ứng dụng yêu cầu | `https://api.example.test/orders` |
| X-Forwarded-For/Forwarded | Metadata do proxy/header gửi, **không phải socket peer** | Chuỗi có thể do client tự bịa |

**Không dùng `getRemoteSocketAddress()` để tự kết luận đó là user đã được xác thực.** Một IP có thể đại diện nhiều người, bị NAT, thay đổi khi reconnect hoặc bị che sau proxy. Nếu xử lý security/rate limiting, phải xác định **trust boundary** của proxy và áp authentication/authorization riêng.

## 2. Lấy địa chỉ trên Socket và ServerSocket

Với TCP truyền thống:

~~~java
// Fragment trong chương trình Java 17+ có một Socket đã connect.
SocketAddress local = socket.getLocalSocketAddress();
SocketAddress remote = socket.getRemoteSocketAddress();

System.out.println("local=" + local);
System.out.println("remote=" + remote);
~~~

`Socket.getLocalSocketAddress()` trả endpoint mà socket đã bind; `getRemoteSocketAddress()` trả endpoint mà socket đang/đã kết nối. Khi socket chưa bind/chưa connect, chúng có thể trả `null`; không dereference bừa. `Socket.getLocalAddress()`/`getLocalPort()` và `getInetAddress()`/`getPort()` cung cấp các phần IP/port riêng nhưng có giá trị sentinel khi chưa có kết nối.

### Listener khác accepted socket

`ServerSocket` chỉ **lắng nghe ở local endpoint**. Nó không biểu diễn một remote peer cụ thể, vì nhiều client có thể kết nối cùng một listener:

~~~java
// Fragment Java 17+.
try (ServerSocket listener = new ServerSocket(
        0, 50, InetAddress.getLoopbackAddress())) {

    SocketAddress listeningOn = listener.getLocalSocketAddress();

    try (Socket accepted = listener.accept()) {
        SocketAddress localOnConnection =
                accepted.getLocalSocketAddress();
        SocketAddress remoteOnConnection =
                accepted.getRemoteSocketAddress();
        // localOnConnection: phía server của kết nối cụ thể
        // remoteOnConnection: phía client trực tiếp
    }
}
~~~

Mẫu trên là **fragment**, sẽ block ở `accept()` tới khi có client; không phải tệp chạy độc lập. Đo địa chỉ **sau** `accept()` mới biết peer cho kết nối cụ thể. Nếu lắng nghe trên địa chỉ wildcard như `0.0.0.0`, địa chỉ bind của listener có thể là wildcard, còn địa chỉ local trên accepted socket có thể là interface cụ thể được dùng cho kết nối.

### InetSocketAddress và định dạng log

Để lấy số cổng hoặc IP, có thể cast sang `InetSocketAddress` **sau khi kiểm tra kiểu**:

~~~java
// Fragment chỉ khi remote thực sự là InetSocketAddress đã resolved.
if (socket.getRemoteSocketAddress() instanceof InetSocketAddress peer) {
    int port = peer.getPort();
    String ip = peer.getAddress() == null
            ? "(unresolved)" : peer.getAddress().getHostAddress();
    System.out.println("peerIp=" + ip + ",peerPort=" + port);
}
~~~

- `InetSocketAddress.getAddress()` có thể là `null` nếu địa chỉ chưa resolve.
- `getHostAddress()` trả chuỗi biểu diễn IP, không yêu cầu reverse DNS.
- `getHostName()` có thể thực hiện reverse name lookup tùy đối tượng; trong hot path logging, đừng vô tình biến mỗi request thành DNS lookup.
- IPv6 có dấu hai chấm; khi trình bày IP+port để copy vào URI, cần quy tắc bracket `[2001:db8::1]:443` chứ không nối chuỗi ngây thơ.
- Đối với UNIX-domain sockets (nếu API/kênh cho phép), `SocketAddress` có thể không phải InetSocketAddress. Đừng cast vô điều kiện.

### Trạng thái đóng socket và địa chỉ

Một số socket methods vẫn có thể giữ thông tin endpoint **sau khi socket đã đóng**. Ví dụ `Socket.isConnected()` có thể vẫn trả `true` vì socket từng kết nối thành công; nó **không** chứng minh hiện tại còn trao đổi dữ liệu được. Cần phân biệt `isClosed()`, I/O lỗi, EOF và trạng thái nghiệp vụ. Khi log endpoint cuối cùng để chẩn đoán, hãy chụp tại thời điểm mở/đã kết nối và gắn correlation ID, thay vì đoán từ trạng thái Boolean.

## 3. Với NIO, Datagram và HTTP Server, đọc endpoint ở đâu?

### 3.1. SocketChannel và ServerSocketChannel

Khi dùng NIO:

~~~java
// Fragment: channel đã kết nối (SocketChannel).
SocketAddress local = channel.getLocalAddress();
SocketAddress remote = channel.getRemoteAddress();

// Số bytes READ thực tế trả về từ call này.
ByteBuffer buffer = ByteBuffer.allocate(1024);
int n = channel.read(buffer);
if (n > 0) {
    payloadBytesRead += n; // Số byte đã đọc từ channel trong call.
} else if (n == 0) {
    // Chưa đọc được byte nào, thường gặp ở nonblocking channel.
} else {
    // n == -1: EOF.
}
~~~

`SocketChannel.read(ByteBuffer)` trả số byte đặt vào buffer, **không** phải luôn bằng capacity; `write(ByteBuffer)` trả số byte đã thực sự ghi nhận trong lần gọi, **không** phải luôn toàn bộ buffer. Trong nonblocking mode, lần gọi có thể trả 0; phải giữ phần `remaining()` và chờ tiếp khi phù hợp. `ServerSocketChannel.accept()` trả một `SocketChannel` của client được chấp nhận; đo endpoint trên **accepted channel**, không chỉ trên listener.

Ví dụ write đúng:

~~~java
// Fragment: outbound là ByteBuffer có bytes cần gửi.
while (outbound.hasRemaining()) {
    int written = channel.write(outbound);
    if (written > 0) {
        payloadBytesWritten += written;
    } else if (written == 0) {
        // Nonblocking: đăng ký OP_WRITE / chờ writable,
        // KHÔNG quay busy-spin vô hạn.
        break;
    }
}
~~~

Nếu loop thoát vì 0 mà buffer còn data, phải **tiếp tục gửi ở lần ready kế tiếp**; không coi message đã đi hết. Với scatter/gather I/O, tổng các byte trả từ `read/write(ByteBuffer[])` phản ánh toàn bộ buffers trong lần gọi.

### 3.2. DatagramSocket và DatagramChannel

UDP **không có kết nối TCP**. Một socket UDP chưa gọi `connect()` có thể có local address sau bind nhưng `getRemoteSocketAddress() == null`. Địa chỉ **nguồn thực tế của từng datagram** nằm trong `DatagramPacket.getSocketAddress()` hoặc giá trị `DatagramChannel.receive(ByteBuffer)` trả về.

~~~java
// Fragment DatagramSocket Java 17+.
byte[] storage = new byte[2048];
DatagramPacket packet =
        new DatagramPacket(storage, storage.length);
udpSocket.receive(packet);

SocketAddress sender = packet.getSocketAddress();
int bytesReceived = packet.getLength();
// bytesReceived là datagram payload đã được chép vào buffer.
~~~

~~~java
// Fragment DatagramChannel Java 17+.
ByteBuffer data = ByteBuffer.allocate(2048);
SocketAddress sender = datagramChannel.receive(data);
if (sender != null) {
    int receivedBytes = data.position();
    // Bởi position ban đầu = 0; tổng vị trí thay đổi là byte nhận.
}
~~~

Ở trường hợp ByteBuffer đã có position khác 0, phải đo **delta** position trước/sau, không lấy toàn bộ position làm số byte mới. Datagram lớn hơn receiving buffer có thể **bị cắt**, vì vậy số byte đọc là số thực vào buffer, không chứng minh payload gốc gửi từ peer nhỏ như vậy. Gọi UDP `connect(peer)` chỉ lọc peer/cho phép read-write thuận tiện, **không thực hiện TCP handshake**, không tự chứng minh peer sống.

UDP datagram có message boundary ở tầng UDP, nhưng byte count vẫn chưa bao gồm IP/UDP headers, fragmentation overhead hoặc retransmission do ứng dụng tự triển khai.

### 3.3. HttpExchange của jdk.httpserver

Trong HTTP server tích hợp JDK:

~~~java
// Fragment trong HttpHandler.handle(HttpExchange exchange).
InetSocketAddress local = exchange.getLocalAddress();
InetSocketAddress remote = exchange.getRemoteAddress();

String method = exchange.getRequestMethod();
URI uri = exchange.getRequestURI();
String protocol = exchange.getProtocol(); // Ví dụ HTTP/1.1.
~~~

`getLocalAddress()` là endpoint local server nhận request; `getRemoteAddress()` là **socket peer trực tiếp** gọi server. Nếu server đứng sau Nginx/Envoy/load balancer, remote có thể là **proxy**. Các header `Forwarded` hoặc `X-Forwarded-For` không được coi là nguồn tin cậy nếu client được tự gửi/ghi đè; chỉ đọc theo proxy trust configuration cụ thể, chặn spoofing và đánh giá quyền theo danh tính thực.

`HttpExchange` không công bố một API “đã có bao nhiêu TCP/TLS bytes trên wire”. Để biết **bytes trong HTTP request/response body**, hãy đo những byte bạn đọc từ `getRequestBody()` và ghi vào `getResponseBody()`. Kích thước headers, chunk framing, compression, TLS records và retransmission nằm ở tầng khác.

## 4. Với java.net.http.HttpClient, không có API socket endpoint công khai tương đương

Đối với Java 17 `HttpClient` và `HttpResponse<T>`:

- `HttpResponse.uri()` trả URI gắn với response, **có thể khác URI gốc do redirect**.
- `HttpResponse.statusCode()`, `headers()`, `version()`, `sslSession()` cho phép quan sát status, metadata protocol và TLS session (nếu HTTPS).
- **`HttpResponse` không có phương thức công khai `getLocalSocketAddress()/getRemoteSocketAddress()`**. Vì vậy **không được ghi “remoteIp = response.uri().getHost()”** rồi gọi nó là địa chỉ TCP peer. URI host có thể là DNS name, proxy có thể làm peer khác, DNS có nhiều địa chỉ, keep-alive reuse có thể giữ socket cũ và redirect có thể đổi đích.
- **`HttpClient` không cung cấp public DNS/TCP/TLS per-phase timing breakdown** giống một số HTTP client libraries có event listener. Bạn có thể đo wall elapsed ở ranh giới API, nhưng không tự phân chia thành connect/TLS/request-write chỉ bằng một `sendAsync()`.

~~~java
// Fragment Java 17+, response là HttpResponse<String>.
URI effectiveUri = response.uri();
int status = response.statusCode();
HttpClient.Version httpVersion = response.version();
boolean secureResponse = response.sslSession().isPresent();

// Không có: response.getRemoteSocketAddress()
// Không có: response.getDnsDuration() hoặc response.getTlsDuration()
~~~

`sslSession()` mang thông tin TLS negotiated session/peer identity (khi có) nhưng **không phải API trả số byte encrypted TCP hay địa chỉ peer socket**. Nếu yêu cầu business chỉ cần biết target host/path/HTTP status, log URI đã được chuẩn hóa và status là đủ; nếu cần chính xác socket tuple hoặc từng giai đoạn mạng, cần lớp instrumentation khác ở boundary TCP, proxy hoặc HTTP client implementation cung cấp hooks hợp lệ.

## 5. Định nghĩa các giai đoạn thời gian trước khi đo

Các mốc phổ biến cho một HTTP call:

~~~text
t0       tDNS      tConnect     tTLS     tWrite      tHeaders      tBodyDone
|--------|---------|------------|--------|-----------|-------------|
   DNS      TCP       TLS          upload    wait/        body
   lookup   connect   handshake    request   headers     read/consume
         \_______________________________/
             có thể overlap, reuse, retry hoặc redirect
~~~

Sơ đồ đơn giản hóa đường đi của một request **mở kết nối mới**. Trong thực tế DNS có cache, TCP connection có thể tái sử dụng, HTTP/2 có multiplexing, proxy có thêm giai đoạn, TLS session có thể resume, và request body có thể **được phát đồng thời với xử lý response**. Do đó không phải request nào cũng có đủ mọi giai đoạn, và không phải mọi giai đoạn luôn nối tiếp không chồng lấp.

| Giai đoạn | Điểm bắt đầu/kết thúc khả dụng | Điều bạn thực sự đo |
| --- | --- | --- |
| DNS resolution | Trước/sau `InetAddress.getAllByName(host)` nếu tự gọi | Thời gian API name resolution trong process, có thể dùng cache; không phải toàn bộ recursive DNS network latency |
| TCP connect | Trước/sau `socket.connect(remote, connectTimeoutMs)` | Thời gian lời gọi connect cho socket đó; có thể bị ảnh hưởng ARP/routing/scheduling |
| TLS handshake | Trước/sau `SSLSocket.startHandshake()` khi chủ động quản lý socket TLS | Thời gian handshake trong thời gian đo; không bao gồm mọi chi phí liên quan trước đó |
| Gửi request | Trước/sau ghi và `flush()` của OutputStream/SocketChannel | Thời gian code hoàn tất thao tác ghi/flush, **không** phải ACK của server |
| Chờ response headers | Từ lúc bắt đầu request tới lúc headers sẵn sàng ở API | **Gần đúng thời gian có response object** nếu dùng streaming BodyHandler, không phải thuần server processing |
| Đọc response body | Từ khi body stream sẵn sàng đến EOF/terminal | Bao gồm tốc độ peer, scheduling và xử lý/copy local |
| Tổng request | Trước khi bắt đầu công việc tới khi body/processing cần thiết hoàn tất | End-to-end elapsed tại boundary do ứng dụng chọn |
| Server request-body read | Trước/sau vòng đọc `getRequestBody()` | Đọc body trong handler, không bao gồm accept/DNS/TLS trước handler |
| Server response write | Trước/sau ghi/close `getResponseBody()` | Ghi body ở application boundary, không có bảo đảm client đã xử lý |

**TTFB (time to first byte)** trong monitoring sản phẩm thường là mốc network layer cụ thể; `sendAsync(...,BodyHandlers.ofInputStream())` hoàn tất có thể **gần** thời điểm headers/body stream sẵn sàng, nhưng còn scheduling/JDK internals. Không gọi con số này là **TTFB chính xác trên wire** nếu instrumentation chỉ đứng ở application boundary.

### Sử dụng System.nanoTime(), không dùng currentTimeMillis() để đo duration

~~~java
long start = System.nanoTime();
// Thao tác cần đo.
long elapsedNanos = System.nanoTime() - start;
double elapsedMs = elapsedNanos / 1_000_000.0;
~~~

`System.nanoTime()` là một **nguồn thời gian monotonic phù hợp đo thời gian trôi trong cùng JVM** (không phải wall-clock timestamp). Nó không cho ngày giờ và không nên lưu số absolute rồi so sánh giữa các máy. `Instant.now()` thích hợp timestamp log, nhưng đồng hồ wall-clock có thể được chỉnh; không dùng nó thay `nanoTime()` cho latency duration chính xác.

Đối với timeout, nên dùng Duration/TimeUnit và deadline tổng. Nếu có 10 bước nối tiếp, không cho mỗi bước một timeout bằng tổng budget rồi nói đã giới hạn tổng: cần thời gian **còn lại** của cùng deadline.

### DNS, TCP connect và TLS handshake được tách bằng cách nào?

Khi **bạn tự sở hữu Socket**:

~~~java
// Fragment Java 17+, host và port được xác định bởi ứng dụng.
long dnsStart = System.nanoTime();
InetAddress[] candidates = InetAddress.getAllByName(host);
long dnsDone = System.nanoTime();

Socket socket = new Socket();
long connectStart = System.nanoTime();
socket.connect(new InetSocketAddress(candidates[0], port), 3_000);
long connectDone = System.nanoTime();

// Với TCP plaintext, chỉ có DNS + connect.
// Với TLS socket, cần SSLContext, kiểm tra endpoint identity
// và đo riêng startHandshake() sau khi tạo SSLSocket hợp lệ.
~~~

Đây là fragment, không tự chạy độc lập. Chọn `candidates[0]` chỉ minh họa và **không phải chiến lược Happy Eyeballs/failover** production. DNS có thể trả IPv4/IPv6 nhiều địa chỉ, đôi khi có cache. Với HttpClient, **đừng tự gọi DNS rồi gán đó là DNS duration của HttpClient**: client có thể dùng DNS/cache/connection khác, proxy, redirect hoặc tiếp tục reuse connection có sẵn.

Khi tự quản lý TLS, một fragment đúng hướng:

~~~java
// Fragment TLS Java 17+, context là SSLContext đã xác minh trust
// và raw là TCP Socket MỚI đã connect tới host:port.
try (SSLSocket tls = (SSLSocket) context.getSocketFactory()
        .createSocket(raw, host, port, true)) {
    SSLParameters params = tls.getSSLParameters();
    params.setEndpointIdentificationAlgorithm("HTTPS");
    tls.setSSLParameters(params);

    long handshakeStart = System.nanoTime();
    tls.startHandshake();
    long handshakeNanos = System.nanoTime() - handshakeStart;
}
~~~

Đây là **fragment**: cần tạo/configure context, raw socket, host/port, exceptions và policy TLS đầy đủ. Đo thời gian startHandshake không có nghĩa được quyền **bỏ xác minh certificate**; nếu không bật endpoint identity thì số liệu nhanh hơn nhưng bảo mật sai. Trong thực tế HTTPS client có thể dùng TLS 1.3 resumption hoặc HTTP/2 connection reuse nên nhiều request không mở handshake mới.

## 6. Số byte nào đang được đếm?

“Đã gửi 100 byte” chỉ có nghĩa khi nói rõ **100 byte ở tầng nào**.

| Đơn vị đếm | Bao gồm | Không bao gồm |
| --- | --- | --- |
| Byte của `text.getBytes(UTF_8)` | Bytes của text sau encode | HTTP headers, TCP/IP, TLS overhead |
| InputStream/OutputStream ứng dụng | Bytes read/write thành công tại boundary | Không tự biết bytes đã đến peer hoặc được ACK |
| `SocketChannel.read/write` | Giá trị n do API trả (thành công của thao tác cục bộ) | Không bao gồm mọi retries/overhead/retransmissions |
| HTTP request body bytes | Bytes đọc từ `HttpExchange.getRequestBody()` | Headers, chunk framing, TLS/IP overhead |
| HTTP response body bytes | Bytes handler ghi vào `getResponseBody()` | Headers, chunk framing, encrypted bytes trên wire |
| HTTP `Content-Length` | Giá trị khai báo nếu có | Không chứng minh số byte thực đã được nhận |
| TLS on-wire bytes | Encrypted TLS records | Không có qua plain `Socket.getInputStream()` của SSLSocket như payload counter |
| Lưu lượng tại NIC/OS | Các bytes/packets tầng transport/interface | Có thể gồm traffic khác, headers, retries hoặc sampling |

Đối với Unicode:

~~~java
String s = "café";
int utf16Units = s.length();                     // 4.
int utf8Bytes = s.getBytes(StandardCharsets.UTF_8).length; // 5.
~~~

Một ký tự có dấu có thể dùng nhiều byte UTF-8. Trong HTML/JSON còn có escaping, gzip/br compression hoặc transfer framing; **không lấy Java String.length() hay Content-Length làm số byte wire**.

### Content-Length không phải phép đo

Trên HTTP request, `Content-Length` có thể do client khai báo và có thể thiếu khi chuyển chunked. Một header có thể sai, spoofed hoặc không áp dụng sau proxy. Nếu cần chính xác body thực nhận, **đếm bytes trên InputStream**.

Trên HTTP response, nếu handler gọi `sendResponseHeaders(200,5)` và ghi đúng 5 bytes, đó là **5 body bytes tại server API**; tổng wire bytes còn có status line/headers và TCP framing. `sendResponseHeaders(200,0)` trong `jdk.httpserver` chọn chunked encoding (không phải body rỗng). Nếu body không có, API cho phép `-1` phù hợp trạng thái HTTP.

### Count stream mà không đếm đôi

Một lỗi trong Java là subclass `FilterOutputStream` rồi override đồng thời `write(int)` và `write(byte[],off,len)` nhưng **gọi `super.write(byte[],off,len)`** trong method sau. Default implementation có thể lần lượt gọi `write(int)` cho từng byte; nếu bạn lại cộng len, counter bị **double-count**. Trong hai chương trình dưới đây, method bulk-write gọi **`out.write(b,off,len)` trực tiếp**, rồi cộng đúng len.

Tương tự, `FilterInputStream.read(byte[],off,len)` cần cập nhật counter từ **số n thực trả về**, không cộng `len` khi chỉ đọc được một phần. `read() == -1` là EOF, không phải một byte âm; `read(byte[]) == 0` không tự có bytes mới.

## 7. Chương trình TCP hoàn chỉnh: endpoint và bytes hai chiều

Chương trình **`TcpObserveDemo.java`** có một `ServerSocket` loopback, một thread server nhận kết nối và một TCP client. Client gửi đúng bốn byte UTF-8 `PING`, server đọc đúng bốn byte rồi ghi bốn byte `PONG`. Hai stream wrappers tự đếm byte đọc/ghi. Mọi địa chỉ được lấy **sau khi kết nối/accept** và các mốc thời gian được ghi với `System.nanoTime()`.

Lưu tệp **`TcpObserveDemo.java`**:

~~~java
import java.io.FilterInputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TcpObserveDemo {
    static class CountedIn extends FilterInputStream {
        long count;
        CountedIn(java.io.InputStream in) { super(in); }

        @Override
        public int read() throws IOException {
            int b = in.read();
            if (b >= 0) count++;
            return b;
        }

        @Override
        public int read(byte[] b, int off, int len)
                throws IOException {
            int n = in.read(b, off, len);
            if (n > 0) count += n;
            return n;
        }
    }

    static class CountedOut extends FilterOutputStream {
        long count;
        CountedOut(java.io.OutputStream out) { super(out); }

        @Override
        public void write(int b) throws IOException {
            out.write(b);
            count++;
        }

        @Override
        public void write(byte[] b, int off, int len)
                throws IOException {
            out.write(b, off, len); // Tránh double-count.
            count += len;
        }
    }

    record ServerResult(
            InetSocketAddress local, InetSocketAddress remote,
            long payloadIn, long payloadOut) { }

    static ServerResult handleOnce(ServerSocket listener)
            throws Exception {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5_000);

            InetSocketAddress local =
                    (InetSocketAddress) peer.getLocalSocketAddress();
            InetSocketAddress remote =
                    (InetSocketAddress) peer.getRemoteSocketAddress();

            CountedIn in = new CountedIn(peer.getInputStream());
            CountedOut out = new CountedOut(peer.getOutputStream());

            byte[] message = in.readNBytes(4);
            if (!"PING".equals(new String(
                    message, StandardCharsets.UTF_8))) {
                throw new IOException("Unexpected request");
            }

            out.write("PONG".getBytes(StandardCharsets.UTF_8));
            out.flush();

            return new ServerResult(
                    local, remote, in.count, out.count);
        }
    }

    public static void main(String[] args)
            throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        ExecutorService worker =
                Executors.newSingleThreadExecutor();

        try (ServerSocket listener =
                     new ServerSocket(0, 10, loopback)) {
            Future<ServerResult> task =
                    worker.submit(() -> handleOnce(listener));

            try (Socket client = new Socket()) {
                long start = System.nanoTime();
                client.connect(
                        new InetSocketAddress(
                                loopback, listener.getLocalPort()),
                        3_000);
                long connected = System.nanoTime();
                client.setSoTimeout(5_000);

                InetSocketAddress clientLocal =
                        (InetSocketAddress) client.getLocalSocketAddress();
                InetSocketAddress clientRemote =
                        (InetSocketAddress) client.getRemoteSocketAddress();

                CountedIn in = new CountedIn(
                        client.getInputStream());
                CountedOut out = new CountedOut(
                        client.getOutputStream());

                long writeStart = System.nanoTime();
                out.write("PING".getBytes(StandardCharsets.UTF_8));
                out.flush();
                long written = System.nanoTime();

                byte[] response = in.readNBytes(4);
                long readDone = System.nanoTime();

                ServerResult server =
                        task.get(5, TimeUnit.SECONDS);

                System.out.println("serverLocalLoopback="
                        + server.local().getAddress()
                                .isLoopbackAddress());
                System.out.println("serverRemoteLoopback="
                        + server.remote().getAddress()
                                .isLoopbackAddress());
                System.out.println("clientLocalMatchesServerRemote="
                        + clientLocal.equals(server.remote()));
                System.out.println("clientRemoteMatchesServerLocal="
                        + clientRemote.equals(server.local()));
                System.out.println("clientPayloadSent=" + out.count);
                System.out.println("clientPayloadReceived=" + in.count);
                System.out.println("serverPayloadReceived="
                        + server.payloadIn());
                System.out.println("serverPayloadSent="
                        + server.payloadOut());
                System.out.println("reply="
                        + new String(
                                response, StandardCharsets.UTF_8));

                System.out.printf(
                        Locale.ROOT, "connectMs=%.3f%n",
                        (connected - start) / 1_000_000.0);
                System.out.printf(
                        Locale.ROOT, "writeAndFlushMs=%.3f%n",
                        (written - writeStart) / 1_000_000.0);
                System.out.printf(
                        Locale.ROOT, "responseReadMs=%.3f%n",
                        (readDone - written) / 1_000_000.0);
                System.out.printf(
                        Locale.ROOT, "totalMs=%.3f%n",
                        (readDone - start) / 1_000_000.0);
                System.out.println("durationsNonNegative="
                        + (connected >= start
                        && written >= writeStart
                        && readDone >= written));
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac --release 17 TcpObserveDemo.java
java TcpObserveDemo
~~~

**Một lần chạy thực tế đã quan sát** (các giá trị mili giây của lần thử chỉ để minh họa; không hứa cố định):

~~~text
serverLocalLoopback=true
serverRemoteLoopback=true
clientLocalMatchesServerRemote=true
clientRemoteMatchesServerLocal=true
clientPayloadSent=4
clientPayloadReceived=4
serverPayloadReceived=4
serverPayloadSent=4
reply=PONG
connectMs=1.782
writeAndFlushMs=0.731
responseReadMs=0.067
totalMs=10.826
durationsNonNegative=true
~~~

**Phần ổn định** của output là giá trị địa chỉ loopback, đối chiếu hai endpoint, số byte 4 ở từng phía và nội dung `PONG`. **Các số connect/write/read/totalMs thay đổi theo OS scheduling, JVM/JIT, timing, socket buffer và tải máy.** `totalMs` không nhất thiết bằng tổng ba giai đoạn in ra vì có thêm thời gian chuẩn bị buffer, gọi task.get(), đồng bộ hai threads và công việc Java khác.

### Kiểm chứng ý nghĩa byte counts

- `clientPayloadSent=4`: wrapper đã hoàn tất ghi **4 bytes** vào OutputStream tại client.
- `serverPayloadReceived=4`: wrapper server đã đọc **4 bytes** từ accepted socket.
- `serverPayloadSent=4` và `clientPayloadReceived=4`: server ghi và client đọc đúng PONG.
- Đây không phải “tổng số byte trên dây” vì **không gồm TCP/IP headers, SYN/ACK/FIN, retransmission và mọi traffic của OS**.
- Counter kiểu `long` tránh overflow nhanh như int đối với luồng lớn, nhưng production còn cần đối phó trường hợp long overflow nếu chạy vô hạn quá dài, và concurrency/atomicity khi nhiều threads cùng cập nhật.

### Vì sao timeout khác measurement?

`client.connect(addr, 3000)` đặt **connect timeout 3.000 ms** cho lời gọi; nó **không yêu cầu connect mất đúng 3 giây**. `client.setSoTimeout(5000)` giới hạn mỗi blocking read của socket theo API, không tự bảo đảm tổng hoạt động upload/download hoàn tất trong 5 giây nếu luôn có những lần nhận nhỏ trước hạn. Với SLA, dùng end-to-end deadline và cancel/close theo chính sách.

## 8. Chương trình HTTP hoàn chỉnh: địa chỉ peer và thời gian handler/body

Lớp **`HttpObserveDemo.java`** dùng server `com.sun.net.httpserver.HttpServer` trên loopback, route POST `/observe`. Server đọc **request body** và đếm byte, viết **response body** và đếm byte. Client dùng **`HttpClient.sendAsync(..., BodyHandlers.ofInputStream())`**, đo thời gian từ bắt đầu send đến khi response object có sẵn, rồi đọc body tới EOF, đo body-read duration.

**Điểm quan trọng:** `BodyHandlers.ofInputStream()` trả một stream mà caller cần đọc/close; response Future có thể hoàn tất sau khi headers đã có nhưng body chưa đọc hết. Bài cố ý dùng handler này để tách khoảng thời gian **response object available** và **body fully consumed**. Hai khoảng này không thể tự gọi là DNS/TCP/TLS riêng biệt.

Server dùng hai Counting wrappers giống demo TCP nhưng xử lý ở `HttpExchange.getRequestBody()` và `getResponseBody()`. Chỉ request body và response body bytes mới được đếm, **không đếm HTTP headers/TCP/TLS bytes**.

Lưu tệp **`HttpObserveDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class HttpObserveDemo {
    static final java.nio.charset.Charset UTF8 = StandardCharsets.UTF_8;
    static final CountDownLatch handled = new CountDownLatch(1);
    static final AtomicReference<Metrics> serverData =
            new AtomicReference<>();

    record Metrics(
            InetSocketAddress local, InetSocketAddress remote,
            long requestPayloadBytes, long responsePayloadBytes,
            long inputNanos, long responseHeadersNanos,
            long outputNanos, long handlerNanos) { }

    static final class CountedIn extends FilterInputStream {
        long count;

        CountedIn(InputStream in) { super(in); }

        @Override
        public int read() throws IOException {
            int x = in.read();
            if (x >= 0) count++;
            return x;
        }

        @Override
        public int read(byte[] b, int off, int len)
                throws IOException {
            int n = in.read(b, off, len);
            if (n > 0) count += n;
            return n;
        }
    }

    static final class CountedOut extends FilterOutputStream {
        long count;

        CountedOut(OutputStream out) { super(out); }

        @Override
        public void write(int value) throws IOException {
            out.write(value);
            count++;
        }

        @Override
        public void write(byte[] b, int off, int len)
                throws IOException {
            out.write(b, off, len);
            count += len;
        }
    }

    static void handle(HttpExchange exchange)
            throws IOException {
        long entered = System.nanoTime();

        try (exchange) {
            InetSocketAddress local =
                    exchange.getLocalAddress();
            InetSocketAddress remote =
                    exchange.getRemoteAddress();

            long startRead = System.nanoTime();
            CountedIn input =
                    new CountedIn(exchange.getRequestBody());
            ByteArrayOutputStream gathered =
                    new ByteArrayOutputStream();

            try (input) {
                byte[] buffer = new byte[16];
                int n;
                while ((n = input.read(buffer)) != -1) {
                    if (n > 32 - gathered.size()) {
                        throw new IOException(
                                "Body exceeds lab limit");
                    }
                    gathered.write(buffer, 0, n);
                }
            }
            long finishedRead = System.nanoTime();

            byte[] response =
                    ("ACK:" + input.count).getBytes(UTF8);
            exchange.getResponseHeaders().set(
                    "Content-Type",
                    "text/plain; charset=UTF-8");

            long startHeaders = System.nanoTime();
            exchange.sendResponseHeaders(200, response.length);
            long finishedHeaders = System.nanoTime();

            CountedOut output =
                    new CountedOut(exchange.getResponseBody());
            long startWrite = System.nanoTime();
            try (output) {
                output.write(response);
            }
            long finishedWrite = System.nanoTime();

            serverData.set(new Metrics(
                    local, remote, input.count, output.count,
                    finishedRead - startRead,
                    finishedHeaders - startHeaders,
                    finishedWrite - startWrite,
                    finishedWrite - entered));
        } finally {
            handled.countDown();
        }
    }

    public static void main(String[] args)
            throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 16);
        ExecutorService pool =
                Executors.newFixedThreadPool(2);
        server.createContext(
                "/observe", HttpObserveDemo::handle);
        server.setExecutor(pool);
        server.start();

        try {
            String root = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpRequest request = HttpRequest.newBuilder(
                    URI.create(root + "/observe"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "HELLO", UTF8))
                    .build();

            long beforeSend = System.nanoTime();
            HttpResponse<InputStream> response =
                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofInputStream())
                    .get(5, TimeUnit.SECONDS);
            long responseAvailable = System.nanoTime();

            byte[] responseBytes;
            try (InputStream input = response.body()) {
                // Demo server trả đúng 5 byte; KHÔNG dùng
                // readAllBytes() vô hạn cho response không tin cậy.
                responseBytes = input.readAllBytes();
            }
            long readCompleted = System.nanoTime();

            if (!handled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Server did not finish");
            }
            Metrics metrics = serverData.get();

            System.out.println(
                    "httpStatus=" + response.statusCode());
            System.out.println(
                    "serverLocalLoopback="
                    + metrics.local().getAddress()
                            .isLoopbackAddress());
            System.out.println(
                    "serverRemoteLoopback="
                    + metrics.remote().getAddress()
                            .isLoopbackAddress());
            System.out.println(
                    "serverRequestPayloadBytes="
                    + metrics.requestPayloadBytes());
            System.out.println(
                    "serverResponsePayloadBytes="
                    + metrics.responsePayloadBytes());
            System.out.println(
                    "clientResponsePayloadBytes="
                    + responseBytes.length);
            System.out.println(
                    "responseText="
                    + new String(responseBytes, UTF8));

            System.out.printf(
                    Locale.ROOT,
                    "timeUntilResponseObjectMs=%.3f%n",
                    (responseAvailable - beforeSend)
                            / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "clientBodyReadMs=%.3f%n",
                    (readCompleted - responseAvailable)
                            / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "clientTotalMs=%.3f%n",
                    (readCompleted - beforeSend)
                            / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "serverRequestReadMs=%.3f%n",
                    metrics.inputNanos() / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "serverResponseHeadersMs=%.3f%n",
                    metrics.responseHeadersNanos()
                            / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "serverResponseWriteMs=%.3f%n",
                    metrics.outputNanos() / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "serverHandlerMs=%.3f%n",
                    metrics.handlerNanos() / 1_000_000.0);
        } finally {
            server.stop(1);
            pool.shutdown();
            if (!pool.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Lệnh Java 17+:

~~~bash
javac --release 17 HttpObserveDemo.java
java HttpObserveDemo
~~~

**Một lần chạy thực tế được ghi nhận trên JDK tương thích** (các thời gian có thể khác hoàn toàn trên máy khác):

~~~text
httpStatus=200
serverLocalLoopback=true
serverRemoteLoopback=true
serverRequestPayloadBytes=5
serverResponsePayloadBytes=5
clientResponsePayloadBytes=5
responseText=ACK:5
timeUntilResponseObjectMs=70.043
clientBodyReadMs=0.703
clientTotalMs=70.747
serverRequestReadMs=4.692
serverResponseHeadersMs=19.544
serverResponseWriteMs=0.223
serverHandlerMs=28.447
~~~

**Giải thích số đo thật:**

- `serverRequestPayloadBytes=5`: handler đã thực sự **đọc 5 byte** từ HTTP request body `HELLO`.
- `serverResponsePayloadBytes=5`: handler đã thực sự **ghi 5 byte** qua response body stream `ACK:5`.
- `clientResponsePayloadBytes=5`: client nhận 5 byte vào byte[] sau khi đọc InputStream tới EOF.
- Các bytes này **không gồm HTTP request line/status line, headers, chunked framing hoặc TCP/IP overhead**.
- `timeUntilResponseObjectMs` đo từ trước lời gọi `sendAsync` tới lúc `get(...)` trả response object với streaming body. Nó bao gồm scheduling, kết nối nếu cần, gửi request, server response và việc API có response; **không thể tách riêng DNS/connect/TLS/TTFB chỉ từ con số này**.
- `clientBodyReadMs` là khoảng đọc stream đến EOF; với response lớn, nó bao gồm tốc độ mạng và thời gian thực hiện read phía Java.
- `serverRequestReadMs` đo vòng đọc body **sau khi handler đã được gọi**, không bao gồm thời gian DNS/TCP connect của client hay thời gian request headers được parse trước handler.
- `serverResponseHeadersMs` đo một lời gọi `sendResponseHeaders(200,5)`; **không có nghĩa client chắc chắn đã nhận headers** ở mốc đó.
- `serverResponseWriteMs` đo việc ghi và đóng OutputStream ở server boundary; không đảm bảo peer đã xử lý bytes.
- `serverHandlerMs` không nhất thiết bằng tổng ba durations thành phần vì còn công việc khởi tạo response bytes, header map, di chuyển code và scheduling.

**Giới hạn bảo mật của demo:** server không phân biệt method trước khi xử lý, không có authentication, và client gửi body 5 byte đã biết. Handler giới hạn 32 bytes và báo exception nếu quá nhưng chưa biến exception thành 413/4xx hợp lệ; production phải có error policy, request timeout, input validation, bounded concurrency và logging an toàn. `InputStream.readAllBytes()` trong demo client chỉ đúng vì response dài 5 byte; không dùng vô hạn cho endpoint không tin cậy.

## 9. Gắn metric vào HTTP request lifecycle đúng thời điểm

Với một HTTP server nhận request, thường có nhiều mức quan sát:

~~~text
Socket/TLS/server infrastructure:
  TCP accept -> TLS handshake -> parse request line/headers
                                    |
                                    v
HttpHandler entry:
  request-body read -> validation -> business processing
       -> response headers -> response-body write -> exchange close
                                    |
                                    v
Client:
  response object available -> body read/consume -> app processing done
~~~

**`HttpHandler.handle()` chỉ bắt đầu khi request đã được server giao handler.** Vì vậy đo `System.nanoTime()` ngay đầu handler **không** bao gồm thời gian TCP connection được tạo hoặc thời gian đọc toàn bộ request headers trước đó. Nếu muốn đo toàn pipeline, cần thêm timestamp ở reverse proxy/network instrumentation và truyền request ID/tracing context tin cậy.

### Filter và counting stream

`HttpExchange.setStreams(InputStream,OutputStream)` cho phép Filter **wrap** request/response streams cho các handler sau nó. Một Filter có thể bắt đầu timer ở đầu `doFilter`, đo byte counts qua wrapper, gọi `chain.doFilter(exchange)`, rồi xuất metrics cuối cùng.

~~~java
// Fragment trong một subclass của com.sun.net.httpserver.Filter.
@Override
public void doFilter(HttpExchange exchange, Chain chain)
        throws IOException {
    long began = System.nanoTime();
    // Có thể wrap getRequestBody/getResponseBody bằng CountedIn/CountedOut
    // và gọi exchange.setStreams(...), nhưng phải giữ nguyên stream gốc,
    // tuân thủ lifecycle và không double-count.
    try {
        chain.doFilter(exchange);
    } finally {
        long elapsed = System.nanoTime() - began;
        // Record elapsed, status, bytes và outcome với metric tags an toàn.
    }
}
~~~

Đây là fragment, không chạy độc lập; tên `CountedIn/CountedOut` được định nghĩa ở hai chương trình đầy đủ. Hãy nhớ:

1. Filter chỉ đo từ khi **Filter được gọi**, không từ DNS/TCP connect của client.
2. Một request có thể bị từ chối trong Filter trước khi handler; vẫn phải đo status/error.
3. `setStreams` phải dùng wrappers **của streams gốc** để không làm mất dữ liệu.
4. Đóng/hủy exchange đúng, không đọc body vô hạn chỉ để metrics đầy đủ.
5. Nếu có gzip middleware, đặt counter **trước hoặc sau compression** sẽ ra hai loại byte counts khác nhau; đặt tên metric rõ `compressed_bytes` và `uncompressed_bytes`.
6. Nếu nhiều filters wrap cùng stream, cần tránh đếm cùng một byte lặp ở nhiều mức rồi cộng chúng như tổng network traffic.

### HttpClient và BodyHandler

Với `HttpClient.sendAsync`:

- `BodyHandlers.ofString()` thường khiến Future hoàn tất sau khi body đã được tập hợp thành String. Timer bao quanh `future.get()` đo nhiều giai đoạn **gộp**.
- `BodyHandlers.ofInputStream()` cho phép Future hoàn tất khi body stream đã có; người gọi phải **đọc tới EOF hoặc close** stream. Timer kết thúc tại Future không có nghĩa body đã tiêu thụ hết.
- `BodyHandlers.ofPublisher()` cần subscribe và nhận `onComplete/onError` hoặc cancel; timer quanh Future chỉ đo tới lúc publisher object được trả, không phải body completion.
- Muốn đếm body bytes phía client, đếm từng bytes được đọc từ `InputStream` hoặc mỗi `ByteBuffer.remaining()` đã xử lý trong subscriber. **Không dùng `HttpResponse.headers().firstValueAsLong("Content-Length")` làm byte count quan sát thực tế.**
- `HttpResponse.uri()` là **effective URI**, không phải socket remote address.

## 10. NIO và TCP socket: giá trị write() chưa phải số byte peer đã đọc

Giả sử `SocketChannel.write()` trả 128:

- 128 bytes đã được chấp nhận bởi thao tác ghi channel theo API.
- Không chứng minh network peer đã nhận đủ 128 bytes, ứng dụng phía kia đã parse message hoặc server đã commit transaction.
- Khi nonblocking, channel write có thể trả 0, và một write không đủ đưa hết một `ByteBuffer`. Phải tiếp tục khi writable, không bỏ phần còn lại.
- Khi lỗi xảy ra sau đó, có thể đã gửi một phần payload trước failure. Retry application-level cần protocol idempotency và framing rõ.

Với `OutputStream.write(bytes)`, method thành công nghĩa lời gọi ghi phía local hoàn tất theo API; nó có thể đã buffer bytes trong OS/JDK. `flush()` không đảm bảo dữ liệu đã được ACK và xử lý bởi peer. Nếu cần ACK, xây giao thức response/ack riêng và đo latency tới khi response business đến.

### TLS và proxy khiến số byte khác nhau thế nào?

| Trường hợp | Application byte counter nhìn thấy | Số byte trên network thực |
| --- | --- | --- |
| Plain TCP echo | PING 4 bytes, PONG 4 bytes | 4 payload mỗi chiều **cộng** TCP/IP/ethernet overhead và control packets |
| TLS application data | Bytes plaintext qua `SSLSocket` | Encrypted TLS records có overhead, có thể có handshake/resumption |
| HTTP/1.1 request | Request-body bytes đã đọc từ HttpExchange | Headers, chunk framing, TCP/IP và có thể TLS |
| HTTP/2 | HTTP message DATA payload ở app boundary | Frames, headers (HPACK), flow control, multiplexing, TLS |
| GZIP response | Có thể là compressed hoặc decompressed bytes tùy vị trí hook | HTTP/TLS/transport khác tùy compression và chunking |
| Retry/redirect | Có thể nhiều HTTP exchanges cho một business call | Tổng bytes phát có thể vượt payload logic ban đầu |

Khi dùng Java HTTP server API, request body stream **đã qua tầng HTTP parsing**. Khi dùng SSLSocket, bạn thường đọc dữ liệu **đã giải mã TLS** ở application layer, không tự thấy TLS record size. Nếu cần NIC-level bytes, sử dụng OS/network monitoring hoặc proxy metrics, và nêu rõ những overhead/traffic mà công cụ đang đếm. Đừng lấy `Content-Length + headers.length` rồi gọi nó là traffic thật nếu có chunked framing, compression, retransmissions hoặc TLS.

## 11. Thiết kế metric names, tags và correlation ID

Các counter/timer nên có định nghĩa rõ:

| Metric gợi ý | Đơn vị | Phạm vi đo |
| --- | --- | --- |
| `tcp_connect_duration_seconds` | seconds (histogram) | Bao quanh `Socket.connect` khi thực sự mở kết nối mới |
| `tcp_payload_bytes_sent_total` | bytes | Số bytes thành công qua app output wrapper |
| `tcp_payload_bytes_received_total` | bytes | Số bytes app input wrapper đã đọc |
| `http_request_body_bytes_read_total` | bytes | Body bytes đọc từ HttpExchange input |
| `http_response_body_bytes_written_total` | bytes | Body bytes ghi ra HttpExchange output |
| `http_client_response_available_seconds` | seconds | Trước sendAsync tới Future của streaming BodyHandler hoàn tất |
| `http_client_body_consume_seconds` | seconds | Từ body stream sẵn có tới EOF/onComplete |
| `http_server_handler_duration_seconds` | seconds | Đầu/cuối handler, không tính pre-handler network phases |
| `http_server_request_body_read_seconds` | seconds | Thời gian đọc request body trong handler |
| `http_server_response_write_seconds` | seconds | Thời gian ghi/đóng response stream |
| `network_io_failures_total` | events | IOException, timeout, unexpected EOF, cancellation theo loại |

**Seconds** là đơn vị phổ biến cho timer/histogram khi xuất metric; các demo in **milliseconds** chỉ để người học dễ nhìn. Đừng đổi đơn vị từ ms sang seconds mà vẫn giữ tên metric cũ, hoặc vừa ghi bytes vừa nói kilobytes mà thiếu conversion.

### Tránh high-cardinality tags

Một metric theo `remote_ip + remote_port + full_uri + request_id` có thể tạo **vô hạn time series** và làm hỏng storage/monitoring. Nên dùng tags ổn định như:

- `protocol=tcp/http/https`
- `direction=inbound/outbound`
- `route=/orders/{id}` thay vì full URI kèm query và IDs
- `method=GET/POST`
- `status_class=2xx/4xx/5xx`
- `outcome=success/error/timeout/cancelled`
- `peer_service=known-service-name` thay vì IP:port ephemeral

Địa chỉ IP và port có thể đưa vào **diagnostic logs/traces có sampling, retention và access control**, không phải mặc định làm Prometheus label. URI có query có thể chứa secrets; tránh log raw query hoặc Authorization headers. Một địa chỉ IP cũng có thể là dữ liệu cá nhân; áp chính sách bảo mật và lưu giữ phù hợp.

### Correlation ID và trace/span

Gắn `requestId` riêng cho mỗi HTTP exchange, truyền trace context an toàn qua các service đáng tin cậy. Khi log:

~~~text
requestId=...          (chỉ dùng để tìm một request, không làm metric label)
route=/observe
method=POST
status=200
peerSocketAddress=...  (optional, privacy/access controlled)
requestPayloadBytes=5
responsePayloadBytes=5
handlerElapsedMs=...
outcome=success
~~~

Không bịa thời gian DNS/TLS từ `handlerElapsedMs`. Nếu có reverse proxy/gateway, dùng trace/span của từng tầng với đồng bộ context để phân tích *client send* → *proxy* → *upstream handler* → *client body done*.

## 12. Phân biệt latency và throughput

**Latency** là duration cho một operation: `connectMs`, `bodyReadMs`, `serverHandlerMs`. **Throughput** thường là tốc độ bytes/time cho một cửa sổ:

\[ \text{throughput (bytes/s)} = \frac{\text{bytes đã xử lý}}{\text{elapsedSeconds}} \]

Nếu tải 10.000.000 bytes trong 2 giây, throughput trung bình ở boundary đó là 5.000.000 bytes/s. Nhưng cần nêu rõ gồm bước nào: có tính DNS/connect/TLS? Chỉ gồm thời gian đọc body? Có compression? Có retries? Không nên so sánh throughput của hai hệ thống nếu định nghĩa thời gian/bytes khác nhau.

Dùng `System.nanoTime()` để tính elapsed và xử lý trường hợp elapsed gần 0 khi tính tốc độ. Không chia cho 0, không tính tốc độ “vô hạn” chỉ vì độ phân giải timer/chunks nhỏ. Với request cỡ vài bytes trên loopback như demo, throughput tức thời sẽ cực kỳ nhiễu và gần như vô nghĩa; đo nhiều lần/histogram và phân phối p50/p95/p99 trong điều kiện tải hợp lý sẽ hữu ích hơn.

**p95 latency** cho biết khoảng 95% observations có latency không vượt một ngưỡng tương ứng, nhưng phải tính trên **tập measurements có cùng định nghĩa**. Đừng cộng p95 của DNS+connect+body để suy ra p95 tổng: percentiles không cộng tuyến tính. Với nhiều concurrent requests, đo span từng request và aggregate theo cohort.

## 13. Những bẫy quan sát phổ biến

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `getRemoteSocketAddress() == null` | Socket chưa connect | Kiểm tra trạng thái, lấy endpoint sau khi connect/accept |
| Server ghi nhầm remote là mình | Đảo local/remote của accepted socket | Nhớ local=server, remote=client trực tiếp |
| HTTP remote IP luôn là IP proxy | Server nhận kết nối từ reverse proxy | Không coi socket peer là end user; dùng trusted proxy policy |
| Dùng `HttpResponse.uri().getHost()` làm remote IP | URI host không phải socket peer | Log logical target URI; muốn socket tuple cần hooks tầng thấp |
| Latency tự dưng âm | Trừ sai các timestamp hoặc dùng đồng hồ khác nhau | Dùng System.nanoTime trong cùng JVM và đúng thứ tự |
| Nói HttpClient có DNS/TCP/TLS timings trực tiếp | Java17 public API không công bố per-phase event timings | Đo API bounds hoặc dùng instrumentation phù hợp |
| `sendAsync().get()` đo body time sai | Dùng `ofInputStream` và chưa đọc body tới EOF | Đo thêm từ stream available đến EOF/close |
| HTTP Content-Length khác body thật | Header là khai báo, có thể chunked/invalid | Đếm bytes stream read/write |
| Số bytes = số ký tự | UTF-8 có ký tự nhiều byte | `getBytes(UTF_8).length` hoặc counter thực |
| CountingOutputStream báo gấp đôi | Bulk write gọi super.write và cộng len | Gọi out.write trực tiếp như demo |
| CountingInputStream tăng cả EOF | Cộng count khi n=-1 hoặc n=0 | Chỉ cộng n >0, read() >=0 |
| NIO write() trả ít hơn remaining | Partial write, nonblocking | Giữ buffer và ghi tiếp khi writable |
| NIO read() trả 0 bị coi là EOF | Nonblocking chưa có data | Phân biệt 0 và -1 |
| UDP peer lấy từ socket unconnected | getRemoteSocketAddress null | Lấy DatagramPacket source hoặc receive() return |
| Bytes app ít hơn NIC bytes | TCP/IP/TLS/HTTP overhead, retry | Đặt tên rõ tầng đo, kết hợp OS/proxy counters |
| Response 200 nhưng xử lý chưa xong | Handler/body consumer/DB stage còn chạy | Đo kết thúc nghiệp vụ, không chỉ headers |
| HTTP/2 reused connection khiến connectMs=0 | Request không mở socket mới | Ghi connection reused/metric missing, không gán connect latency |
| Số đo rất khác khi debug | JIT, warmup, logging/blocking, scheduling | Warmup, sample đủ, tránh benchmark micro thiếu kiểm soát |
| Metrics labels tăng vô hạn | Dùng IP:port/URI/requestId làm tag | Dùng route template và bounded tags |
| Log chứa token hoặc dữ liệu cá nhân | Logging quá rộng | Redact, retention/access controls |
| Timer không khớp tổng bước | Có gaps, overlap, scheduling hoặc phase khác | Ghi mô hình timeline và timestamps rõ |
| Timings sau timeout bị bỏ | Không ghi outcome khi exception | Record success/error/timeout/cancelled trong finally |

### Không đếm nhiều lần do wrappers lồng nhau

Nếu request body đã qua gzip, một wrapper đặt ở nguồn stream có thể đếm **bytes compressed**, trong khi một wrapper sau decompression đếm **bytes decompressed**. Cả hai hữu ích nhưng **không nên cộng lại** và gọi là total network bytes. Tương tự, proxy inbound/outbound đo cùng một payload ở hai chiều khác nhau; nếu muốn tổng traffic toàn hạ tầng phải định nghĩa chính xác để tránh double-count.

### Không giả định write() trả về là ACK

Hoàn tất `OutputStream.write()` hoặc `SocketChannel.write()` không chứng minh đối tác đã nhận đến ứng dụng, chưa nói đến đã xử lý nghiệp vụ. Nếu một POST tạo bản ghi nhưng connection rớt sau write, retry có thể gây duplicate. Hãy dùng idempotency key, correlation ID và ACK ở tầng ứng dụng để đo *business completion*.

## 14. Quy tắc production khi thu thập local/remote, latency và bytes

1. **Đặt tên rõ “local/remote” của tầng nào:** socket peer, proxy peer, upstream service, logical HTTP authority hoặc forwarded client identity.
2. **Lấy endpoint đúng thời điểm:** sau connect/accept, và xử lý null/unresolved/IPv6.
3. **Dùng `nanoTime` cho duration, `Instant.now` cho timestamp:** không so sánh absolute nanoTime giữa JVM/máy.
4. **Đo đủ lifecycle:** create/resolve/connect/handshake/write/response/body/process tùy API thực sự sở hữu. Không tự tạo phase không quan sát được.
5. **Ghi rõ reused connection:** request qua keep-alive/HTTP/2 không có TCP connect mới; không cộng giả connect time.
6. **Đếm bytes thực từ return value hoặc wrappers:** không dựa solely Content-Length/String.length.
7. **Phân biệt “payload application” và “wire bytes”:** không có bytes TLS/IP headers/retries chỉ nhờ một InputStream.
8. **Bound memory và I/O:** max body, deadlines, backpressure, connection limits, queue limits.
9. **Quan sát cả lỗi và hủy:** metric trong finally, status/outcome rõ; đừng báo thành công nếu stream/callback chưa hoàn tất.
10. **Chú ý quyền riêng tư:** địa chỉ IP, hostname, URL và query có thể nhạy cảm; sampling/redaction/retention.
11. **Hạn chế cardinality:** dùng route templates và service labels cho metrics; giữ raw endpoint trong logs truy cập có kiểm soát nếu cần.
12. **Phân biệt connection time và server processing:** server HttpHandler không đo DNS/connect của client; client HttpResponse không thấy actual socket peer.
13. **Định nghĩa latency tổng:** tính từ mốc bắt đầu tới khi body và xử lý cần thiết xong; chỉ dùng riêng time-to-headers khi chủ đích.
14. **Dùng units rõ:** `bytes`, `seconds`, `milliseconds`, `requests`; thống nhất conversion.
15. **Test bất thường:** partial reads/writes, 0-byte nonblocking, EOF, DNS failure, connect timeout, TLS error, body truncated, 413, proxy, redirect, cancellation.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Local/remote của TCP client và socket mà server accept có quan hệ thế nào?  
**Đáp án:** Với kết nối trực tiếp trên cùng network view, local của client trùng remote của accepted socket; remote client trùng local accepted socket. Listener ServerSocket chỉ có local bind endpoint, không có một remote peer duy nhất.

**Câu 2.** Vì sao `socket.getRemoteSocketAddress()` có thể null?  
**Đáp án:** Socket chưa connect hoặc không có peer tương ứng. Không dereference; lấy sau connect/accept.

**Câu 3.** Dùng remote IP để xác định người dùng đã đăng nhập được không?  
**Đáp án:** Không. IP là địa chỉ socket peer, có thể là proxy/NAT; cần authentication/authorization.

**Câu 4.** `HttpResponse.uri()` là socket remote address của Java HttpClient không?  
**Đáp án:** Không. Đây là effective logical URI; có thể qua DNS, proxy, redirect và connection reuse. Public HttpResponse Java17 không có getRemoteSocketAddress().

**Câu 5.** `HttpExchange.getRemoteAddress()` cho biết IP của end user sau Nginx không?  
**Đáp án:** Thường là IP của Nginx/proxy trực tiếp kết nối. Header forwarded chỉ đáng tin nếu được xử lý theo trusted proxy policy.

**Câu 6.** `System.nanoTime()` dùng cho ngày giờ hay duration?  
**Đáp án:** Duration trong cùng JVM. Với timestamp thực dùng Instant/clock wall-time.

**Câu 7.** Đo `InetAddress.getAllByName()` có chắc bằng latency của một DNS request thật trên mạng không?  
**Đáp án:** Không. API có cache, resolver/OS behavior; đây là thời gian lời gọi tại process, không phải toàn bộ recursive lookup bắt buộc.

**Câu 8.** `Socket.connect(addr,3000)` có nghĩa connect luôn mất 3.000ms không?  
**Đáp án:** Không. 3000 là timeout tối đa của lời gọi connect theo API; duration thực đo bằng nanoTime.

**Câu 9.** Với `HttpClient.sendAsync(...,BodyHandlers.ofInputStream())`, Future complete có nghĩa body đã đọc hết không?  
**Đáp án:** Không. Cần đo thêm thời gian đọc stream tới EOF hoặc close khi không dùng tiếp.

**Câu 10.** Vì sao không thể gán `responseFutureCompletionMs` bằng `tcpConnectMs + tlsMs`?  
**Đáp án:** Nó gồm nhiều giai đoạn gộp và scheduling, có connection reuse, proxy/redirect và không công bố phase internals.

**Câu 11.** `Content-Length: 1000` có chứng minh handler đọc 1000 bytes chưa?  
**Đáp án:** Không. Đó là header khai báo; đo bytes đã đọc thực tế từ InputStream.

**Câu 12.** Đếm bytes phía server bằng `String.length()` có chính xác với tiếng Việt không?  
**Đáp án:** Không. UTF-8 có nhiều byte cho một ký tự; dùng encoded bytes hoặc counter stream.

**Câu 13.** Vì sao CountingOutputStream có thể đếm đôi?  
**Đáp án:** Override bulk write gọi super.write (có thể gọi write(int) từng byte) rồi tự cộng len; cách đúng như demo gọi out.write trực tiếp.

**Câu 14.** `SocketChannel.read(buffer) == 0` có phải EOF không?  
**Đáp án:** Không. 0 là chưa nhận byte nào trong lần đọc; -1 mới là EOF.

**Câu 15.** `SocketChannel.write(buffer)` trả 17 mà buffer còn remaining có được coi đã gửi hết message không?  
**Đáp án:** Không. Còn bytes phải gửi tiếp khi writable.

**Câu 16.** DatagramSocket UDP unconnected biết source của packet ở đâu?  
**Đáp án:** Từ DatagramPacket.getSocketAddress() sau receive, không phải getRemoteSocketAddress của socket chưa connect.

**Câu 17.** `HttpExchange.getResponseBody()` count=5000 thì NIC đã gửi đúng 5000 bytes không?  
**Đáp án:** Không. Đây là response body bytes ở app boundary, chưa gồm HTTP/TLS/TCP/IP và overhead/retries.

**Câu 18.** Response status 200 có nghĩa handler business đã commit xong và client nhận đủ response không?  
**Đáp án:** Không tự động. Cần kiểm tra lifecycle body, write completion, nghiệp vụ và ACK theo protocol.

**Câu 19.** Có nên làm metric label theo remote IP:port và toàn bộ request URI không?  
**Đáp án:** Không nên: cardinality rất cao và có rủi ro dữ liệu nhạy cảm; dùng route templates/known service names.

**Câu 20.** Có thể cộng p95 DNS, p95 TCP connect và p95 body để ra p95 total không?  
**Đáp án:** Không. Percentile không cộng tuyến tính; đo total duration từng request rồi tính phân phối.

## 16. Tài liệu chính thức

- Oracle Java SE 17 — `Socket`, địa chỉ local/remote và connect timeout: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- Oracle Java SE 17 — `ServerSocket`, bind/local/accept: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- Oracle Java SE 17 — `InetSocketAddress` và resolved/unresolved host: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html
- Oracle Java SE 17 — `InetAddress` và name lookup: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html
- Oracle Java SE 17 — `SocketChannel`, read/write, local/remote: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html
- Oracle Java SE 17 — `DatagramSocket`, packet peer vs connected address: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html
- Oracle Java SE 17 — `DatagramChannel`, receive source and ByteBuffer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html
- Oracle Java SE 17 — `HttpExchange`, getLocalAddress/getRemoteAddress/getRequestBody/getResponseBody: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle Java SE 17 — `HttpClient`, request timeout, send/sendAsync: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 17 — `HttpResponse`, URI/status/headers/version/sslSession and body semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Oracle Java SE 17 — `HttpResponse.BodyHandlers.ofInputStream` streaming: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Oracle Java SE 17 — `FilterInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilterInputStream.html
- Oracle Java SE 17 — `FilterOutputStream` (cẩn thận bulk write): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilterOutputStream.html
- Oracle Java SE 17 — `System.nanoTime()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()
- Oracle Java SE 17 — `SSLSocket`/startHandshake, TLS: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html
- Oracle Java SE 17 — `HttpExchange.setStreams` cho Filters: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html#setStreams(java.io.InputStream,java.io.OutputStream)
