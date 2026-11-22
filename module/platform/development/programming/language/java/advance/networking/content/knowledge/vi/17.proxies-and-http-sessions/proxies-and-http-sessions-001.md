# Proxy HTTP, proxy SOCKS và kết nối trực tiếp: khác nhau thế nào trong Java Networking?

Khi một ứng dụng Java gọi API bên ngoài, kết nối có thể đi **trực tiếp tới máy chủ đích**, đi qua **HTTP forward proxy** hoặc qua **SOCKS proxy**. Cả ba đều đưa dữ liệu từ client tới một dịch vụ, nhưng **điểm mà client kết nối TCP đầu tiên, giao thức điều khiển, quyền hiểu nội dung HTTP, cách phân giải DNS, cách xác thực và API Java cần dùng** không giống nhau. Chọn sai cách sẽ khiến request không đi qua proxy như dự kiến, lỗi TLS/407, lộ DNS, vượt chính sách mạng hoặc làm ứng dụng tưởng rằng đã gửi thành công trong khi chỉ mới kết nối được tới proxy.

Bài học này nằm trong chủ đề **Proxy và phiên HTTP** của module **Java Advance - networking**. Trọng tâm là giải thích **vai trò thực tế và khác biệt kỹ thuật** giữa direct, HTTP proxy và SOCKS trong Java 17+, kèm ví dụ chạy được để tự chứng minh đường đi. Không coi “proxy” là một công tắc toàn JVM tự tác động tới mọi thư viện, không coi SOCKS là HTTP, và không coi proxy đồng nghĩa với VPN hoặc mã hóa.

## 1. Ba con đường tới cùng một tài nguyên

Giả sử ứng dụng muốn truy cập `https://api.example.test/orders`.

### 1.1. Kết nối trực tiếp (DIRECT)

~~~text
Java client
     │  (1) DNS lookup api.example.test -> IP
     │  (2) TCP connect tới IP:443
     │  (3) TLS handshake, verify certificate hostname
     │  (4) HTTP request / response
     ▼
api.example.test:443 (origin)
~~~

Ở đây **TCP peer của client là origin**. Không có proxy ứng dụng được cấu hình trong đường đi logic. Tuy nhiên vẫn có thể có router, NAT, transparent firewall, service mesh hoặc mạng trung gian; “DIRECT” **không** có nghĩa đường truyền vật lý không có thiết bị trung gian.

**Điểm nhận diện:** client gọi `Socket.connect(originAddress)` hoặc dùng HTTP client được cấu hình **không proxy**; cổng đích là của origin. TLS, nếu dùng HTTPS, là phiên TLS client–server đích.

### 1.2. HTTP forward proxy

~~~text
Java HTTP client
      │ TCP tới proxy.corp.test:3128
      │
      ▼
HTTP FORWARD PROXY
      │
      │ proxy xử lý HTTP request / policy / authentication
      │ (với HTTPS thường dùng HTTP CONNECT để tunnel)
      ▼
api.example.test:80 hoặc :443
~~~

HTTP forward proxy hiểu **ngữ nghĩa HTTP** ở chặng client→proxy. Đối với HTTP không mã hóa, client thường gửi request theo **absolute-form target**:

~~~http
GET http://api.example.test/products?id=1 HTTP/1.1
Host: api.example.test
~~~

Đây là **request minh họa** đến HTTP proxy. Với direct HTTP/1.1 origin, request-target phổ biến là **origin-form**:

~~~http
GET /products?id=1 HTTP/1.1
Host: api.example.test
~~~

Hai dạng này **không thể đánh đồng**. Một HTTP proxy có thể làm access control, logging, caching hoặc filtering nếu được phép và được triển khai. Không phải proxy nào cũng cache, thay đổi nội dung hay giải mã TLS.

### 1.3. SOCKS proxy

~~~text
Java TCP Socket
     │  TCP connect tới socks.corp.test:1080
     │  SOCKS greeting / chọn auth / CONNECT hostname:port
     ▼
SOCKS proxy
     │ tạo outbound TCP connection theo yêu cầu
     ▼
api.example.test:443
     │ TLS (nếu ứng dụng tự khởi tạo TLS)
     ▼
giao thức ứng dụng: HTTP, SMTP, custom TCP, ...
~~~

SOCKS là cơ chế **chuyển tiếp kết nối** ở mức thấp hơn HTTP. SOCKS5 (RFC 1928) có các lệnh `CONNECT`, `BIND` và `UDP ASSOCIATE`; ví dụ Java dưới đây sử dụng **SOCKS5 TCP CONNECT**. SOCKS không cần hiểu URI path, HTTP method hoặc HTTP headers chỉ để tạo một đường TCP. Nếu dùng TLS qua SOCKS, ứng dụng **vẫn phải thiết lập và xác thực TLS riêng**.

**SOCKS không phải HTTP forward proxy**; gửi một request HTTP absolute-form tới SOCKS port trước khi hoàn tất SOCKS handshake là sai giao thức.

## 2. Bảng so sánh: điểm khác cốt lõi

| Thuộc tính | DIRECT | HTTP forward proxy | SOCKS5 proxy |
| --- | --- | --- | --- |
| TCP peer đầu tiên của client | Origin IP:port | HTTP proxy IP:port | SOCKS server IP:port |
| Giao thức điều khiển đường đi | TCP/IP + protocol ứng dụng | HTTP methods/headers, có thể `CONNECT` | SOCKS5 greeting, auth negotiation, command/target address |
| Hiểu HTTP method/path | Origin hiểu | Proxy HTTP có thể hiểu (HTTP thường); tunnel CONNECT chỉ chuyển bytes sau khi mở | SOCKS không cần hiểu HTTP |
| HTTP request không TLS | Gửi HTTP tới origin | Thường gửi absolute-form target tới proxy | Sau SOCKS CONNECT, gửi HTTP như qua TCP bình thường |
| HTTPS | TLS trực tiếp tới origin | Thường HTTP CONNECT, rồi TLS trong tunnel tới origin | SOCKS CONNECT, rồi TLS tới origin |
| Khả năng dùng cho non-HTTP TCP | Có, nếu kết nối được | Thường cần CONNECT và proxy cho phép; không tự động | SOCKS CONNECT phù hợp nhiều TCP protocols |
| DNS của origin | Thường do client/OS phân giải | Proxy có thể phân giải khi nhận URI/CONNECT hostname | SOCKS5 có thể nhận hostname (`ATYP=DOMAINNAME`) và phân giải ở phía proxy |
| Authentication | Ứng dụng/origin tùy protocol | Có thể HTTP proxy auth, ví dụ `407`/`Proxy-Authenticate` | SOCKS5 negotiation/auth riêng, không phải HTTP 407 |
| Java 17 phù hợp | `HttpClient.Builder.NO_PROXY`, `new Socket(Proxy.NO_PROXY)` | `HttpClient.Builder.proxy(ProxySelector.of(...))` | `new Socket(new Proxy(Proxy.Type.SOCKS,...))` |
| Dùng một cấu hình cho mọi library | Không nên mặc định | Mỗi library có thể có proxy config riêng | Không nên suy từ `Socket` sang `HttpClient` |
| Bảo mật dữ liệu | Phụ thuộc HTTP/TLS | HTTP có thể thấy plaintext; HTTPS CONNECT thường là tunnel | SOCKS không tự mã hóa app payload |

**Kết luận ngắn:** DIRECT trả kết nối tới đúng origin, HTTP proxy là trung gian **biết HTTP**, SOCKS là trung gian **thiết lập/chuyển tiếp transport**. Chúng có thể cùng dẫn tới một URL nhưng **không tương đương ở tầng giao thức**.

## 3. Vì sao HTTP proxy có hai kiểu xử lý HTTP và HTTPS?

### 3.1. HTTP không mã hóa đi qua forward proxy

Khi client muốn `http://service.example.test/a` thông qua HTTP proxy, request ở chặng client→proxy có thể là:

~~~text
TCP: client ─────► proxy:3128

GET http://service.example.test/a HTTP/1.1
Host: service.example.test
~~~

Proxy tra URL, kiểm tra policy/authorization, sau đó tạo request upstream hoặc đáp từ cache nếu policy/implementation cho phép. Origin không nhất thiết biết địa chỉ IP thật của client: nó thấy kết nối từ proxy (tùy hạ tầng) và có thể nhận forwarding headers do proxy thêm; **không được tự tin tưởng header `X-Forwarded-For` từ bất kỳ client không tin cậy nào**.

Một HTTP proxy trên đường truyền HTTP **có thể đọc method, path, query, headers và body chưa mã hóa**. Vì vậy không gửi secrets trên HTTP plaintext chỉ vì “đã qua proxy nội bộ”.

### 3.2. HTTPS thường dùng HTTP CONNECT

Để truy cập `https://api.example.test:443` qua HTTP proxy HTTP/1.1, client thường mở TCP tới proxy và gửi:

~~~http
CONNECT api.example.test:443 HTTP/1.1
Host: api.example.test:443
~~~

Nếu proxy cho phép, nó trả response 2xx để báo tunnel đã sẵn sàng; từ đó **bytes sau response headers thuộc tunnel**, thường là TLS handshake client ↔ origin:

~~~text
Client                 HTTP proxy                     Origin
  │ TCP connect proxy      │                           │
  ├───────────────────────►│                           │
  │ CONNECT origin:443     │                           │
  ├───────────────────────►│──── TCP connect origin ──►│
  │ HTTP/1.1 200 ...       │◄───────────────────────────│
  │◄───────────────────────│                           │
  │  TLS ClientHello (SNI origin hostname)             │
  ├══════════════════════════════════════════════════►│
  │  certificate verification / encrypted HTTPS       │
  │◄═════════════════════════════════════════════════►│
~~~

Điểm quan trọng:
- `CONNECT` là **HTTP method gửi tới HTTP proxy**, không phải SOCKS command.
- Target dùng **host:port**, không phải URL path.
- Proxy có thể thấy hostname:port cần nối, thời điểm và lưu lượng; nhưng với **TLS end-to-end và không có chặn TLS**, nó **không** đọc plaintext HTTPS payload.
- Nếu tổ chức triển khai **TLS interception** có CA nội bộ được client tin cậy, TLS thực tế có thể kết thúc ở proxy rồi tạo chặng TLS mới tới origin. Đây là mô hình khác; cần policy, quản lý certificate và audit.
- `CONNECT` thành công không có nghĩa TLS certificate hợp lệ hoặc HTTP response thành công. Client vẫn phải xác thực TLS peer/origin và gửi HTTP request đúng phiên bản.
- Proxy có thể chỉ cho phép tunnel tới các cổng đích đã được kiểm soát để giảm rủi ro relay bị lạm dụng. <RFC 9110 `9.3.6> mô tả CONNECT và những yêu cầu bảo vệ đó.

Trong HTTP/2, CONNECT có representation riêng qua pseudo-headers; bảng trên minh họa **HTTP/1.1 CONNECT**, không phải frame HTTP/2 trên dây.

### 3.3. HTTP proxy có thể bị yêu cầu xác thực bằng HTTP 407

- `401 Unauthorized`: thường là origin yêu cầu authentication, đi kèm `WWW-Authenticate`.
- `407 Proxy Authentication Required`: HTTP proxy yêu cầu authentication, đi kèm `Proxy-Authenticate`.
- `Authorization` và `Proxy-Authorization` có **phạm vi khác nhau**; không sao chép credential origin sang proxy hoặc ngược lại.

Trong Java, `HttpClient.Builder.authenticator(Authenticator)` có thể cấp thông tin theo challenge và scheme được implementation hỗ trợ. Không hardcode mật khẩu trong source, không đưa secrets vào URL/query/log, và không giả định mọi loại proxy auth đều được JSSE/HTTP client hỗ trợ như nhau. Với HTTPS CONNECT, một số chế độ auth (như Basic) có thể bị chính sách JDK cấm trong tunneling mặc định; xem cấu hình security do tổ chức quản lý, **không tùy tiện nới policy** chỉ để bỏ qua 407.

## 4. SOCKS5: handshake khác hoàn toàn HTTP

SOCKS5 theo RFC 1928 có bước thương lượng phương thức authentication, sau đó client gửi yêu cầu tạo connection. Với trường hợp **TCP CONNECT**:

~~~text
Client                          SOCKS5 proxy
   │ TCP connect proxy:1080           │
   ├─────────────────────────────────►│
   │ VER=05, NMETHODS, METHODS        │
   ├─────────────────────────────────►│
   │ VER=05, METHOD selected          │
   │◄─────────────────────────────────┤
   │ CONNECT request:                 │
   │   VER=05, CMD=01, RSV=00         │
   │   ATYP, DST.ADDR, DST.PORT       │
   ├─────────────────────────────────►│
   │ Reply: VER=05, REP, RSV, BND...  │
   │◄─────────────────────────────────┤
   │ Nếu REP=00: TCP tunnel sẵn sàng  │
   │◄════════════════════════════════►│
   │ app bytes: TLS/HTTP/custom TCP   │
~~~

Các trường:
- `VER=0x05`: SOCKS phiên bản 5.
- `CMD=0x01`: TCP CONNECT (khác HTTP CONNECT trên dây).
- `ATYP=0x01`: địa chỉ IPv4; `0x03`: hostname có length-prefix; `0x04`: IPv6.
- `DST.PORT`: hai bytes network byte order.
- `REP=0x00`: thành công; giá trị khác báo lỗi proxy-level (refused, network unreachable, không hỗ trợ address type...).
- Bước auth có thể dùng no-auth, username/password hoặc cơ chế khác tùy SOCKS server; **không** gửi HTTP `Proxy-Authorization` để thay SOCKS auth.

SOCKS5 còn định nghĩa `UDP ASSOCIATE`, nhưng **Java `new Socket(Proxy.Type.SOCKS...)` trong bài chỉ đang thực hiện TCP CONNECT**. Không xem đó là bằng chứng mọi `DatagramSocket`, `DatagramChannel` hay `HttpClient` dùng được SOCKS UDP; muốn có UDP proxy phải xét API/implementation/protocol riêng.

## 5. DNS được phân giải ở đâu?

Đây là khác biệt hay bị bỏ qua.

### 5.1. DIRECT

Thông thường ứng dụng/OS giải `api.example.test` thành IP rồi tạo TCP tới IP đích. Cơ chế thực có thể qua DNS resolver, cache, IPv4/IPv6 và corporate DNS. Không thể suy vị trí DNS lookup chỉ từ việc Java truyền một `URI`.

### 5.2. HTTP proxy

Với HTTP forward proxy, client gửi URI chứa hostname hoặc CONNECT host:port tới proxy. Proxy **có thể** tự tra DNS của origin. Client vẫn phải phân giải địa chỉ **proxy** (trừ khi cấu hình bằng IP hoặc giải pháp khác) và có thể có hoạt động DNS khác ở tầng thư viện, redirect, PAC hoặc security.

HTTPS qua HTTP CONNECT thường để proxy mở TCP tới hostname trong CONNECT; client vẫn kiểm tra TLS identity của hostname đích. Đừng kết luận proxy “che DNS tuyệt đối” vì thực tế hệ thống có thể còn DNS request ngoài đường proxy.

### 5.3. SOCKS5 và `createUnresolved`

Với `java.net.Socket`:

~~~java
Proxy socks = new Proxy(
        Proxy.Type.SOCKS,
        new InetSocketAddress("socks.corp.test", 1080));

try (Socket socket = new Socket(socks)) {
    socket.connect(
            InetSocketAddress.createUnresolved(
                    "api.example.test", 443), 5000);
    // Sau SOCKS handshake thành công, giao tiếp với origin qua socket.
}
~~~

Đây là **đoạn minh họa** trong phương thức có `throws IOException`, import `java.net.*`. `InetSocketAddress.createUnresolved` không thực hiện DNS lookup tại thời điểm tạo endpoint. Với SOCKS5 implementation hỗ trợ hostname, socket gửi `ATYP=DOMAINNAME` và để proxy xử lý hostname; ví dụ chạy được ở phần 11 xác nhận đúng điều đó trong bài test.

Nếu thay bằng `new InetSocketAddress("api.example.test",443)`, constructor có thể thực hiện DNS lookup cục bộ. Điều này thay đổi cách tên được giải quyết và có thể ảnh hưởng bảo mật/đường mạng. Nhưng **remote DNS không phải một lời hứa cho mọi SOCKS phiên bản, provider hoặc thư viện**; phải kiểm thử điểm đích và DNS flows trên OS/JDK mục tiêu.

**Chỉ định hostname chưa được phân giải không phải cách vượt qua chính sách truy cập.** Proxy phải thực thi ACL cho địa chỉ đích sau DNS, tránh DNS rebinding/SSRF, lọc private IP/cổng không được phép và bảo vệ dịch vụ nội bộ. Khi test, dùng hostname `*.test` không phân giải thật và một SOCKS mock an toàn trên loopback.

## 6. Cấu hình Java 17: ba API không giống nhau

### 6.1. `java.net.http.HttpClient`: DIRECT hoặc HTTP proxy

~~~java
// DIRECT rõ ràng, bỏ qua default proxy selector.
HttpClient direct = HttpClient.newBuilder()
        .proxy(HttpClient.Builder.NO_PROXY)
        .build();

// HTTP forward proxy cho HTTP/HTTPS.
HttpClient viaHttpProxy = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.corp.test", 3128)))
        .build();
~~~

Đoạn này là **minh họa Java 17**, cần import `java.net.*` và `java.net.http.*`. Câu lệnh `ProxySelector.of(InetSocketAddress)` theo Javadoc tạo selector dùng **HTTP proxy cho HTTP/HTTPS requests**; **không** tạo SOCKS proxy chỉ vì server ở cổng 1080.

Nếu không gọi `builder.proxy(...)`, default `HttpClient` **thường sử dụng `ProxySelector.getDefault()`**, có thể chịu ảnh hưởng system properties hoặc environment của JVM. Việc `client.proxy()` trả `Optional.empty()` không chứng minh client đang DIRECT: API này chỉ lộ **selector tường minh** đã đưa vào builder; implementation có thể dùng default selector không expose.

Muốn chắc chắn DIRECT cho một client, dùng `HttpClient.Builder.NO_PROXY`. Khi client cần route per-host/per-scheme, có thể cài `ProxySelector` custom hoặc cấu hình library theo chính sách, **không** tự đoán rằng một proxy được áp dụng cho mọi request sau redirect, mọi URI scheme hay tất cả frameworks.

**Giới hạn quan trọng của JDK built-in HttpClient:** dù `java.net.Proxy.Type.SOCKS` tồn tại, không được mặc nhiên cho rằng `HttpClient.Builder.proxy(...)` sẽ dùng SOCKS. Trên implementation `java.net.http.HttpClient` được cung cấp bởi OpenJDK/JDK 17, SOCKS proxy không được hỗ trợ như đường routing HTTP client chuẩn. Nếu thật sự cần HTTP request qua SOCKS, dùng HTTP client/library có SOCKS support đã được xác minh hoặc triển khai transport tunnel phù hợp; kiểm tra bằng proxy-side logs, không chỉ nhìn `ProxySelector.select(...)`.

### 6.2. `java.net.Socket`: DIRECT hoặc SOCKS ở tầng TCP

~~~java
// Bỏ qua proxy configuration khác của JVM cho socket này.
try (Socket directSocket = new Socket(Proxy.NO_PROXY)) {
    directSocket.connect(
            new InetSocketAddress("service.example.test", 9000), 5000);
    directSocket.setSoTimeout(5000);
    // app protocol của service tự quản lý.
}

// Route TCP qua SOCKS.
Proxy socksProxy = new Proxy(
        Proxy.Type.SOCKS,
        new InetSocketAddress("socks.corp.test", 1080));

try (Socket socksSocket = new Socket(socksProxy)) {
    socksSocket.connect(
            InetSocketAddress.createUnresolved(
                    "service.example.test", 9000), 5000);
    socksSocket.setSoTimeout(5000);
    // Data stream sau khi SOCKS connect được xem như TCP byte stream.
}
~~~

Đây là **đoạn minh họa**, không nên chạy với các hostname `*.test` vì chúng không phải server thật. `new Socket(Proxy.NO_PROXY)` là **DIRECT** ngay cả khi JVM có SOCKS settings khác. `new Socket(Proxy.Type.SOCKS, ...)` không phải HTTP proxy và không giúp HTTP framing tự diễn ra. Nếu muốn nói HTTP qua TCP socket, ứng dụng vẫn phải sử dụng HTTP protocol đúng chuẩn và TLS/hostname verification cho HTTPS.

`SocketChannel.open()` / non-blocking `Selector` không có cùng constructor `SocketChannel(Proxy)` tường minh như `Socket(Proxy)`. Đừng lấy ví dụ SOCKS blocking `Socket` rồi hứa rằng mọi NIO channel tự route qua SOCKS. Nếu cần NIO qua SOCKS, cần transport adapter/handshake/proxy library hỗ trợ asynchronous operation.

### 6.3. `URL.openConnection(Proxy)` thuộc API khác

Với legacy `URLConnection` / `HttpURLConnection`, có thể truyền proxy theo request:

~~~java
URL url = new URL("http://service.example.test/status");
Proxy proxy = new Proxy(
        Proxy.Type.HTTP,
        new InetSocketAddress("proxy.corp.test", 3128));

URLConnection conn = url.openConnection(proxy);
conn.setConnectTimeout(5000);
conn.setReadTimeout(5000);
// Đọc input/error streams và đóng đúng cách khi request thực hiện.
~~~

Đây là **đoạn minh họa**. `URL.openConnection(Proxy)` có thể hỗ trợ `Proxy.Type.HTTP` và ở một số protocol handler có thể `Proxy.Type.SOCKS`, **nhưng không được suy ra mọi custom URL protocol handler đều hỗ trợ**; Javadoc nêu handler không hỗ trợ có thể bỏ qua proxy và kết nối trực tiếp. `URL.openConnection(Proxy.NO_PROXY)` là cách yêu cầu DIRECT rõ ràng cho handler.

Không trộn các API thành một mẫu sai như `HttpClient.newBuilder().proxy(new Proxy(...))`: **builder.proxy nhận `ProxySelector`**, không nhận `Proxy`. Tương tự, `Socket(Proxy)` nhận `Proxy`, không nhận `ProxySelector`.

### 6.4. Bảng mapping API

| Nhu cầu | Java 17 API | Ghi nhớ |
| --- | --- | --- |
| HTTP request DIRECT | `HttpClient.Builder.proxy(NO_PROXY)` | Bỏ qua default selector |
| HTTP/HTTPS qua HTTP proxy | `HttpClient.Builder.proxy(ProxySelector.of(addr))` | `ProxySelector.of` cho HTTP và HTTPS |
| TCP socket DIRECT | `new Socket(Proxy.NO_PROXY)` | Không dựa vào SOCKS system properties |
| TCP socket qua SOCKS5 | `new Socket(new Proxy(Proxy.Type.SOCKS, addr))` | App vẫn làm TLS/HTTP nếu cần |
| URLConnection qua HTTP proxy | `url.openConnection(new Proxy(HTTP, addr))` | Legacy API, handler có thể khác nhau |
| Rule routing per URL/host | Custom `ProxySelector` | Chọn DIRECT hoặc proxy theo chính sách |
| HTTP via SOCKS trên JDK HttpClient | **Không mặc định hỗ trợ** | Dùng thư viện/transport đã xác minh |

## 7. Lệnh cấu hình proxy theo JVM system properties

JDK 17 có các networking properties liên quan:

~~~bash
java -Dhttp.proxyHost=proxy.corp.test -Dhttp.proxyPort=3128 MyApp
java -Dhttps.proxyHost=proxy.corp.test -Dhttps.proxyPort=3128 MyApp
java -DsocksProxyHost=socks.corp.test -DsocksProxyPort=1080 MyApp
~~~

Đây chỉ là **ví dụ cú pháp chạy Java**, không có proxy thực trong `*.test`. Theo Oracle Networking Properties:

- `http.proxyHost`, `http.proxyPort` (mặc định 80) cho HTTP protocol handler.
- `https.proxyHost`, `https.proxyPort` (mặc định 443 theo tài liệu) cho HTTPS protocol handler.
- `http.nonProxyHosts` là danh sách hosts bypass HTTP proxy, các pattern phân cách `|` và `*` wildcard; HTTPS handler dùng cùng thuộc tính này.
- `socksProxyHost`, `socksProxyPort` (mặc định 1080 nếu không cấu hình) cho TCP SOCKS nơi implementation hỗ trợ, thêm `socksProxyVersion` với giá trị thường dùng 5.
- `java.net.useSystemProxies=true` cho phép một số môi trường sử dụng system proxy settings và được đọc **một lần lúc JVM startup**; do đó nên truyền bằng `-D` khi khởi động.

**System properties không là hợp đồng ép tất cả libraries đi qua proxy.** Một `HttpClient` có explicit selector khác có thể bỏ qua default, `Socket(Proxy.NO_PROXY)` bỏ qua SOCKS settings, native libraries/Netty/Apache clients có cấu hình riêng. Hãy kiểm tra **đường đi thật** bằng test hoặc logs.

Ví dụ cấu hình bypass:

~~~bash
java '-Dhttp.nonProxyHosts=localhost|127.*|*.internal.test' \
     -Dhttp.proxyHost=proxy.corp.test \
     -Dhttp.proxyPort=3128 MyApp
~~~

Trong shell thực, cú pháp quote và nối dòng khác nhau giữa Linux shell, PowerShell và cmd; nếu chạy Windows PowerShell, nên đặt các `-D...` trong một dòng hoặc quote phù hợp, không dùng backslash continuation của Unix. Tránh bật global system proxy sau khi đã tạo các `HttpClient`: JDK HttpClient có thể chụp default settings lúc build và không phản ánh thay đổi sau đó.

**Cảnh báo:** `http.nonProxyHosts` nếu cấu hình quá rộng có thể làm request đi DIRECT ngoài dự kiến, vi phạm egress policy. Không sửa global JVM proxy để “fix một request” nếu ứng dụng có nhiều tenants/chức năng cần chính sách khác.

## 8. `ProxySelector`: chọn route, nhưng không phải mạng đã đi đúng

Theo `ProxySelector` Javadoc, `select(URI)` trả về danh sách `Proxy` ứng viên theo thứ tự ưu tiên. Một custom selector có thể trả `Proxy.NO_PROXY` nếu cần direct; `connectFailed` nhận báo cáo khi kết nối tới proxy không thành công để xử lý availability/failover.

Đoạn minh họa (nằm trong phương thức/class có import thích hợp):

~~~java
Proxy httpProxy = new Proxy(Proxy.Type.HTTP,
        InetSocketAddress.createUnresolved("proxy.corp.test", 3128));

ProxySelector selector = new ProxySelector() {
    @Override
    public List<Proxy> select(URI uri) {
        String host = uri.getHost();
        if (host == null) throw new IllegalArgumentException("No host");
        if ("localhost".equalsIgnoreCase(host)
                || host.endsWith(".internal.test")) {
            return List.of(Proxy.NO_PROXY);
        }
        return List.of(httpProxy);
    }

    @Override
    public void connectFailed(
            URI uri, SocketAddress address, IOException error) {
        System.err.println("HTTP proxy connect failed for " + uri.getHost());
    }
};
~~~

Đây là **pseudocode để học route policy**, không phải một class độc lập (cần `List`, `URI`, `IOException`, `Proxy`, `ProxySelector`, `InetSocketAddress`). Nếu gắn vào `HttpClient.Builder.proxy(selector)`, phải nhớ **HTTP client implementation thực tế** có thể chỉ hỗ trợ một số proxy types. Việc trả `List.of(Proxy.Type.SOCKS)` từ custom selector không chứng minh HTTP client đã dùng SOCKS.

Trong production, xây policy cẩn thận:
- Chỉ proxy những URI schemes thực hỗ trợ.
- Normalize/validate hostname theo IDNA/IP literal, tránh bypass bằng mixed-case, suffix tricks (ví dụ `evilinternal.test` không phải `*.internal.test`).
- Tránh redirect làm chuyển route không mong muốn qua private IP hoặc loopback; kiểm soát SSRF và network egress.
- **Không thêm `Proxy.NO_PROXY` làm fallback sau proxy** nếu policy cấm direct. Một default fail-open không kiểm soát có thể làm lộ traffic.
- ProxySelector chỉ là **quyết định định tuyến**, không phải bằng chứng TCP connection đã chạm proxy.
- Nếu proxy thất bại, xử lý theo policy: fail closed, retry another approved proxy hoặc explicit direct chỉ khi được phép.

## 9. Ví dụ Java 17+ hoàn chỉnh 1: DIRECT khác HTTP forward proxy

Đây là chương trình **chạy hoàn toàn trên loopback**, không có DNS/Internet hay proxy thật. Nó tạo:
1. `HttpServer` làm **origin**, trả `FROM_ORIGIN`.
2. Một `ServerSocket` đóng vai **HTTP proxy mock**, đọc request line/headers và trả `FROM_PROXY`.
3. Hai `HttpClient` gửi **cùng một URL**: một client explicit DIRECT, một client dùng `ProxySelector.of(...)` chỉ tới mock.

**Proxy mock không thật sự chuyển request tới origin**: đây là thí nghiệm **kiểm chứng lựa chọn route và dạng request target**, không phải ví dụ xây proxy production. Port do OS chọn động nên không hardcode số port vào stdout.

Tạo file **`HttpProxyRouteDemo.java`**:

~~~java
import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.*;

public final class HttpProxyRouteDemo {
    private static void respond(
            HttpExchange ex, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        ex.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress host = InetAddress.getLoopbackAddress();
        HttpServer origin = HttpServer.create(
                new InetSocketAddress(host, 0), 0);
        origin.createContext("/demo",
                ex -> respond(ex, "FROM_ORIGIN"));
        origin.start();

        try (ServerSocket proxy =
                new ServerSocket(0, 1, host)) {
            proxy.setSoTimeout(5000);

            FutureTask<String> captured = new FutureTask<>(() -> {
                try (Socket peer = proxy.accept()) {
                    peer.setSoTimeout(5000);
                    BufferedReader in = new BufferedReader(
                            new InputStreamReader(peer.getInputStream(),
                                    StandardCharsets.ISO_8859_1));
                    String first = in.readLine();
                    String line;
                    while ((line = in.readLine()) != null
                            && !line.isEmpty()) {
                        // Bỏ qua headers trong mock này.
                    }

                    byte[] body =
                            "FROM_PROXY".getBytes(StandardCharsets.UTF_8);
                    byte[] head = (
                            "HTTP/1.1 200 OK\r\nContent-Length: "
                            + body.length
                            + "\r\nConnection: close\r\n\r\n")
                            .getBytes(StandardCharsets.ISO_8859_1);

                    OutputStream out = peer.getOutputStream();
                    out.write(head);
                    out.write(body);
                    out.flush();
                    return first;
                }
            });

            Thread worker =
                    new Thread(captured, "one-shot-http-proxy");
            worker.setDaemon(true);
            worker.start();

            URI url = new URI("http", null, host.getHostAddress(),
                    origin.getAddress().getPort(),
                    "/demo", null, null);
            HttpRequest req = HttpRequest.newBuilder(url)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();

            HttpClient direct = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpResponse<String> a = direct.send(req,
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("direct body: " + a.body());

            HttpClient throughProxy = HttpClient.newBuilder()
                    .proxy(ProxySelector.of(new InetSocketAddress(
                            host, proxy.getLocalPort())))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpResponse<String> b = throughProxy.send(req,
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("proxy body: " + b.body());

            String firstLine = captured.get(
                    5, TimeUnit.SECONDS);
            System.out.println("proxy saw absolute-form: " +
                    firstLine.startsWith("GET http://"));
        } finally {
            origin.stop(0);
        }
    }
}
~~~

Biên dịch/chạy với JDK 17+ (module `jdk.httpserver` nằm trong JDK phổ biến):

~~~bash
javac --release 17 HttpProxyRouteDemo.java
java HttpProxyRouteDemo
~~~

Khi local loopback và Java HTTP stack hoạt động, **stdout** là:

~~~text
direct body: FROM_ORIGIN
proxy body: FROM_PROXY
proxy saw absolute-form: true
~~~

Ba kết luận chính:
- `direct` dùng `HttpClient.Builder.NO_PROXY` nên request tới **origin** và nhận `FROM_ORIGIN`.
- `throughProxy` chọn explicit HTTP proxy cho **cùng URL**, nên kết nối tới **mock proxy** và nhận `FROM_PROXY`; điều đó không có nghĩa origin đã được gọi ở lần thứ hai.
- Mock quan sát request-line dạng `GET http://127.0.0.1:<ephemeralPort>/demo HTTP/1.1` hoặc URI IPv6 tương đương: **absolute-form** theo cách HTTP client nói chuyện với forward proxy.
- Bản code không mở proxy ra Internet, không forward tới arbitrary host, không có authentication/caching hoặc TLS interception. Nó cố ý dùng HTTP/1.1 để quan sát request line; khi làm HTTP/2/proxy h2, framing khác.
- `HttpServer` tạo origin thật trên loopback; một HTTP client có cấu hình direct rõ ràng không phụ thuộc default environment proxy cho test.
- `proxy.setSoTimeout(5000)` và `captured.get(5,TimeUnit.SECONDS)` ngăn test treo vô hạn nếu request không tới mock.
- Dùng `try-with-resources` cho mock server socket và accepted TCP connection; `origin.stop(0)` trong `finally`.

Nếu sandbox chặn bind loopback hoặc Java runtime image thiếu `jdk.httpserver`, test có thể không chạy dù API logic đúng. Tên file/class phải đúng như trên; không cần một proxy ngoài hay internet để hiểu sự khác biệt.

## 10. HTTPS qua HTTP proxy: cần kiểm tra TLS dù CONNECT thành công

Ví dụ trước chỉ dùng **HTTP** vì mock trả response giả, nên **không** dùng nó như ví dụ kiểm tra HTTPS và CONNECT. Với HTTPS, JDK HttpClient có thể tạo tunnel qua HTTP proxy; sau đó **TLS handshake tới hostname đích** được thực hiện qua tunnel.

Một client đúng:

~~~java
HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.corp.test", 3128)))
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://api.example.test/v1"))
        .timeout(Duration.ofSeconds(10)).GET().build();

HttpResponse<String> resp =
        client.send(req, HttpResponse.BodyHandlers.ofString());
~~~

Đây là **đoạn minh họa**, không chạy độc lập (thiếu import và không có proxy/origin thực ở `*.test`). Đừng đặt `SSLParameters.setEndpointIdentificationAlgorithm("")` hoặc cài trust-all manager chỉ vì HTTPS qua proxy gây lỗi certificate. Cần giữ truststore/hostname verification đúng. `407` là lỗi/challenge của proxy (có thể ngay ở CONNECT), còn `SSLHandshakeException` hoặc hostname mismatch có thể xảy ra **sau tunnel** trong TLS.

Nếu proxy chỉ chấp nhận một số host/port, nhận `403`/`502` từ proxy không được hiểu là origin trả ra. Kiểm tra access logs ở đúng chặng, nhưng không log `Proxy-Authorization`, tokens hay HTTP body bí mật.

**Một proxy HTTP có thể bản thân được tiếp cận bằng HTTP plaintext** trong khi tunnel bên trong dùng HTTPS. Việc này không giống HTTPS-proxy (TLS tới proxy). Mỗi hop có yêu cầu bảo mật riêng; không nghĩ tất cả đường đi từ client đến proxy đã mã hóa chỉ vì URL origin bắt đầu bằng `https://`.

## 11. Ví dụ Java 17+ hoàn chỉnh 2: SOCKS5 TCP CONNECT dùng hostname chưa phân giải

Để tự nhìn thấy giao thức SOCKS khác HTTP, chương trình này chạy một **SOCKS5 mock trên loopback**, thực hiện:
1. Nhận greeting client và trả `VER=5, METHOD=0 (no-auth)`.
2. Nhận `SOCKS5 CONNECT` với hostname chưa phân giải (`ATYP=3`).
3. Trả một SOCKS success frame tối giản.
4. Nhận application text `PING` và trả `PONG` qua cùng socket.

**SOCKS mock KHÔNG kết nối tới host đích thật**. Tên `target.example.test` được dùng chỉ để kiểm chứng định dạng hostname; không có truy cập Internet hoặc bypass kiểm soát mạng.

Tạo file **`Socks5SocketDemo.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class Socks5SocketDemo {
    private static int readByte(InputStream in) throws IOException {
        int value = in.read();
        if (value < 0) {
            throw new EOFException("SOCKS frame truncated");
        }
        return value;
    }

    private static String readHost(
            InputStream in, int type) throws IOException {
        if (type == 3) {
            int length = readByte(in);
            return new String(in.readNBytes(length),
                    StandardCharsets.US_ASCII);
        }
        if (type == 1) {
            return InetAddress.getByAddress(
                    in.readNBytes(4)).getHostAddress();
        }
        if (type == 4) {
            return InetAddress.getByAddress(
                    in.readNBytes(16)).getHostAddress();
        }
        throw new IOException(
                "Unexpected SOCKS address type " + type);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocket fakeSocks =
                new ServerSocket(0, 1, loopback)) {
            fakeSocks.setSoTimeout(5000);

            FutureTask<String> accepted = new FutureTask<>(() -> {
                try (Socket peer = fakeSocks.accept()) {
                    peer.setSoTimeout(5000);
                    InputStream in = peer.getInputStream();
                    OutputStream out = peer.getOutputStream();

                    int version = readByte(in);
                    int methodsCount = readByte(in);
                    byte[] methods = in.readNBytes(methodsCount);
                    if (version != 5
                            || methods.length != methodsCount) {
                        throw new IOException("Not SOCKS5 greeting");
                    }
                    out.write(new byte[]{5, 0});
                    out.flush();

                    if (readByte(in) != 5
                            || readByte(in) != 1
                            || readByte(in) != 0) {
                        throw new IOException(
                                "Not SOCKS5 CONNECT");
                    }

                    String dst = readHost(in, readByte(in));
                    int port =
                            (readByte(in) << 8) | readByte(in);

                    out.write(new byte[]{
                            5, 0, 0, 1, 127, 0, 0, 1, 0, 0
                    });
                    out.flush();

                    String incoming = new BufferedReader(
                            new InputStreamReader(in,
                                    StandardCharsets.US_ASCII))
                            .readLine();
                    out.write("PONG\n".getBytes(
                            StandardCharsets.US_ASCII));
                    out.flush();
                    if (!"PING".equals(incoming)) {
                        throw new IOException(
                                "Unexpected app payload");
                    }
                    return dst + ":" + port;
                }
            });

            Thread worker = new Thread(
                    accepted, "one-shot-socks5-mock");
            worker.setDaemon(true);
            worker.start();

            Proxy setting = new Proxy(
                    Proxy.Type.SOCKS,
                    new InetSocketAddress(
                            loopback, fakeSocks.getLocalPort()));

            try (Socket client = new Socket(setting)) {
                client.connect(
                        InetSocketAddress.createUnresolved(
                                "target.example.test", 443),
                        5000);
                client.setSoTimeout(5000);
                client.getOutputStream().write(
                        "PING\n".getBytes(
                                StandardCharsets.US_ASCII));

                String answer = new BufferedReader(
                        new InputStreamReader(
                                client.getInputStream(),
                                StandardCharsets.US_ASCII))
                        .readLine();
                System.out.println(
                        "SOCKS tunnel data: " + answer);
            }

            System.out.println(
                    "SOCKS requested: " +
                    accepted.get(5, TimeUnit.SECONDS));
        }
    }
}
~~~

~~~bash
javac --release 17 Socks5SocketDemo.java
java Socks5SocketDemo
~~~

**Stdout đã kiểm tra** trên JDK cục bộ:

~~~text
SOCKS tunnel data: PONG
SOCKS requested: target.example.test:443
~~~

Giải thích:
- `new Proxy(Proxy.Type.SOCKS,...)` thiết lập SOCKS route cho **một `java.net.Socket`**, không phải `HttpClient`.
- `createUnresolved("target.example.test",443)` không resolve DNS locally trước khi gọi `connect`; mock nhận hostname ở SOCKS `ATYP=DOMAINNAME`, rồi quan sát đúng tên/port.
- Chương trình đã hoàn tất SOCKS handshake rồi mới gửi `PING`; thông điệp này là **application data minh họa**, không phải HTTP GET hay TLS handshake.
- Mock trả SOCKS reply success rồi nhận `PING`, **không relay thật tới origin**. Vì vậy output không chứng minh target.example.test có server TCP:443 hoặc TLS certificate.
- Khi viết SOCKS5 server thật, cần parse chặt lengths/address types/methods/credentials, kiểm tra ACL và thực sự tạo tunnel rồi relay hai chiều; code mock ở đây không phải proxy triển khai production.
- `Socket.connect(...,5000)` là connect timeout, `setSoTimeout(5000)` là read timeout; không có một absolute deadline chung cho cả exchange.
- Mô hình này không dùng UDP Associate và không tự mã hóa payload. Nếu application cần HTTPS qua SOCKS, nó phải thiết lập `SSLSocket`/TLS client với hostname verification đúng sau khi tunnel được tạo.
- Chỉ nên dùng SOCKS server được phép, có policy bảo vệ DNS, allowed destinations và authentication; đừng dùng proxy tùy tiện để vượt egress controls.

## 12. Proxy authentication: đừng trộn danh tính proxy với origin

Một HTTP request qua proxy có thể cần xác thực **hai lần**:
1. **Proxy auth:** quyền sử dụng proxy. HTTP thường báo `407` với `Proxy-Authenticate`.
2. **Origin auth:** quyền truy cập tài nguyên. HTTP thường báo `401` với `WWW-Authenticate`.

**Hai credential sets có phạm vi khác nhau**. Ở HTTPS CONNECT, proxy auth có thể xảy ra **trước TLS handshake tới origin**. Nếu dùng Basic auth qua chặng client→proxy không mã hóa, credential header có thể bị người quan sát trên chặng đó đọc được (Base64 **không phải mã hóa**). Luôn bảo vệ proxy connection/credentials và dùng secret storage.

Với SOCKS5, authentication là **SOCKS protocol method negotiation**, ví dụ username/password theo RFC 1929, không dùng HTTP `407` hoặc `Proxy-Authorization`. Cơ chế xác thực SOCKS5 username/password truyền trên kênh SOCKS theo cơ chế giao thức và không mặc định mã hóa; bảo vệ chặng client→proxy theo yêu cầu môi trường.

Không ghi trực tiếp username/password trong source:

~~~java
// Không lưu credentials trong code:
// new PasswordAuthentication("user", "hardcoded-secret".toCharArray());

// Trong ứng dụng thật lấy secrets từ secret manager / secure config
// và chỉ áp dụng cho host:port proxy được phép.
~~~

Đoạn trên là **minh họa policy**, không phải cách khai báo `Authenticator` chạy độc lập. Nếu cần dùng `java.net.Authenticator` với SOCKS hoặc HTTP, phải kiểm tra `RequestorType.PROXY`, hostname/port và permission; không trả proxy password cho một challenge từ origin ngoài dự kiến. Luôn dùng API/flow đã hỗ trợ, đừng tự chế authentication HTTP proxy thành SOCKS handshake.

## 13. Security: proxy không tự cung cấp riêng tư hay bảo mật

### 13.1. Proxy không thay TLS

- **DIRECT HTTPS:** TLS client ↔ origin, xác thực certificate/hostname.
- **HTTP proxy + HTTPS CONNECT:** tunnel qua proxy, **TLS client ↔ origin** (trừ khi chủ động dùng TLS interception).
- **SOCKS + HTTPS:** proxy chuyển TCP bytes, **TLS client ↔ origin**.
- **HTTP plaintext qua HTTP proxy hoặc SOCKS:** nội dung vẫn plaintext trên những chặng không được mã hóa.

Một SOCKS proxy không mặc định cung cấp end-to-end encryption. HTTP proxy không phải VPN. Nếu doanh nghiệp dùng TLS interception, trust model và policy khác phải được công bố rõ ràng.

### 13.2. DNS leaks và đích nội bộ

Kể cả khi kết nối data qua proxy, DNS lookup có thể đi trực tiếp do một thành phần khác hoặc do tạo resolved endpoint. Kiểm tra cả:
- Bên nào resolve hostname origin?
- Bên nào resolve hostname proxy?
- Redirects/embedded resources có dùng cùng proxy policy không?
- URL host có thể trỏ đến loopback, link-local, RFC1918/private network, metadata service hay protected services không?
- Bypass list có wildcard quá rộng, case normalization, IPv4/IPv6 variants hay DNS rebinding risk không?

Một proxy được dùng như **egress control boundary** thường phải fail closed khi proxy không khả dụng. Tự động thử DIRECT sau lỗi proxy có thể khiến traffic đi ra ngoài tuyến phê duyệt; đừng dùng fail-open không có chính sách.

### 13.3. Kiểm tra hostname cho HTTPS

Chỉ biết đã dùng proxy không thay đổi quy tắc TLS. Client vẫn phải xác minh origin certificate cho đúng hostname; SNI giúp chọn virtual host nhưng không tự xác thực. Không cài trust-all `X509TrustManager`, tắt endpoint identification hoặc bỏ qua certificate errors để “cho qua proxy”. Nếu cert sai sau CONNECT, sửa CA chain/hostname/truststore/proxy interception config một cách có kiểm soát.

## 14. Proxy có thể tác động HTTP phiên/connection reuse ra sao?

Tùy cách routing, **TCP connection đầu tiên** có peer là origin hoặc proxy. Điều đó ảnh hưởng:
- Connection pooling: direct connections thường tái sử dụng theo origin/policy; proxied connections tái sử dụng theo proxy/target và implementation.
- HTTP/1.1 vs HTTP/2: `HttpClient.Version.HTTP_2` là preference; proxy capability/ALPN có thể làm phiên thực dùng HTTP/1.1. `HttpResponse.version()` mới xác nhận phiên bản thực của response.
- TLS session: với HTTPS CONNECT, TLS được tạo bên trong tunnel tới origin; HTTP proxy có thể chỉ thấy CONNECT và thống kê lưu lượng.
- DNS/route: proxy có thể resolver thay client; hoặc một app vẫn resolve locally tùy thiết lập.
- Failure mode: proxy connection refused, CONNECT refused, proxy 407, upstream DNS fail, origin 5xx và TLS handshake fail là các lỗi ở **những chặng khác nhau**.
- Timeouts: `connectTimeout` tới proxy không bao trùm tất cả thời gian proxy nối origin, TLS handshake và response body; dùng request/deadline policy phù hợp.

Không suy “HTTP/2 = một TCP connection duy nhất cho mọi requests” khi đi qua proxy. Cấu hình proxy, scheme, authority, security policy và route có thể khiến client mở kết nối khác hoặc fallback HTTP/1.1.

## 15. Chẩn đoán nhanh: request thực sự đi đâu?

| Triệu chứng | Nguyên nhân thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| HTTP qua proxy trả nội dung khác direct | Proxy/cache/filter/mock khác origin | Logs, response source, request target và route |
| `407 Proxy Authentication Required` | Proxy cần credentials / scheme không được chấp nhận | `Proxy-Authenticate`, auth policy, không nhầm 401 |
| `401 Unauthorized` | Origin yêu cầu credentials | `WWW-Authenticate`, quyền tài nguyên |
| `Connection refused` tới proxy | Proxy host:port sai, service down hoặc firewall | TCP tới proxy, DNS proxy, port, policy |
| `CONNECT` bị `403` | Proxy ACL cấm host/port | Egress rules, allowed ports, target |
| TLS hostname mismatch sau CONNECT | Sai origin/SNI/certificate hoặc interception policy | Certificate chain, SAN, truststore |
| SOCKS báo unsupported method | Proxy không chấp nhận auth methods | SOCKS5 method negotiation |
| SOCKS báo address type unsupported | Proxy không hỗ trợ hostname/IP family | `ATYP`, DNS side, IPv4/IPv6 |
| Java HttpClient không đi qua SOCKS | JDK HttpClient không có đường SOCKS được hỗ trợ như `Socket` | Dùng SOCKS-capable client, kiểm tra traffic thật |
| Cấu hình system properties nhưng vẫn DIRECT | Client explicit NO_PROXY, bypass list hoặc lib bỏ qua settings | Chính sách của đúng library/client |
| ProxySelector đã chọn proxy nhưng request vẫn không tới | Implementation không hỗ trợ proxy type, redirect policy hoặc lỗi route | Proxy-side accept/log/packet trace có quyền |
| Truy cập được HTTP nhưng không HTTPS | Proxy cấm CONNECT, auth/cert/TLS issue | Phân biệt 407/CONNECT/TLS/ALPN |
| Kết nối qua proxy thành công nhưng body timeout | Origin chậm, proxy buffering, TCP flow/timeout | Tách connect, request, read timeout và proxy logs |

Khi debug nên log (không chứa secrets): method, scheme, origin hostname, requested proxy mode, selected proxy host:port, target port, thời gian connect/tunnel/TLS/response, HTTP status, response.version và exception category. Đừng log authentication headers, bearer tokens hoặc đầy đủ nội dung cá nhân.

## 16. Chọn tuyến nào cho từng tình huống?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Java service gọi internal API được cho phép trực tiếp | DIRECT | Đơn giản, ít hop; vẫn TLS khi cần |
| Doanh nghiệp bắt buộc audit outbound HTTP/HTTPS | HTTP forward proxy | Chính sách HTTP, CONNECT, authentication, logging tập trung |
| Một ứng dụng TCP custom cần đi qua proxy | SOCKS5 TCP CONNECT hoặc HTTP CONNECT nếu server cho phép | Không cần HTTP semantics ở SOCKS |
| Cần dùng một HTTP client Java 17 chuẩn với proxy doanh nghiệp | HTTP proxy qua `HttpClient.Builder.proxy(ProxySelector.of(...))` | API được hỗ trợ rõ ràng |
| Cần route raw Java `Socket` qua SOCKS | `Socket(new Proxy(Proxy.Type.SOCKS,...))` | API hỗ trợ SOCKS5 TCP |
| HTTP request Java 17 phải đi qua SOCKS | Chọn HTTP client chuyên dụng có SOCKS support, xác nhận behavior | JDK HttpClient không tự động hỗ trợ chỉ từ Proxy.Type.SOCKS |
| Không cho phép direct fallback | Explicit enforced proxy + fail-closed policy | Bảo vệ egress/compliance |
| Chỉ một vài domain được đi DIRECT | Selector có allowlist/bypass rõ | Giảm rủi ro bypass rộng |
| Cần bảo mật nội dung giữa client và origin | HTTPS/TLS end-to-end phù hợp | Proxy là tuyến, không phải encryption layer |

**Không chọn SOCKS chỉ vì mong “ẩn danh tuyệt đối”**. Proxy operator vẫn có thể log metadata; origin có thể vẫn nhận identifiers ở application headers/cookies; DNS/TLS/IP policy khác nhau. Mục tiêu kỹ thuật là chọn đúng transport/routing/authentication theo yêu cầu hợp pháp và an toàn.

## 17. Bài tập tự kiểm tra

**Câu 1.** Một ứng dụng `HttpClient` gọi cùng URL qua `NO_PROXY` và qua `ProxySelector.of(...)`, kết quả khác nhau. Có mâu thuẫn không?  
**Đáp án:** Không. Đường đi khác nhau: direct tới origin, proxied tới HTTP proxy; proxy có thể xử lý/trả response khác.

**Câu 2.** Gọi `ProxySelector.of(new InetSocketAddress("proxy",1080))` có tự tạo SOCKS proxy vì dùng port 1080 không?  
**Đáp án:** Không. `ProxySelector.of` trả HTTP proxy selector cho HTTP/HTTPS. Port không quyết định protocol.

**Câu 3.** Dùng `new Socket(new Proxy(Proxy.Type.SOCKS,addr))` có tự gửi HTTP GET và parse JSON response không?  
**Đáp án:** Không. Nó tạo TCP connection qua SOCKS. Ứng dụng phải nói giao thức HTTP/TLS phù hợp.

**Câu 4.** Với HTTPS qua HTTP proxy, `CONNECT` kết thúc và trả 200 nghĩa là server certificate hợp lệ?  
**Đáp án:** Không. Sau tunnel, TLS tới origin vẫn phải handshake/verify.

**Câu 5.** `HTTP 407` và `HTTP 401` có phải cùng loại auth?  
**Đáp án:** Không. 407 từ HTTP proxy; 401 từ origin.

**Câu 6.** SOCKS5 `ATYP=0x03` nghĩa là gì?  
**Đáp án:** Địa chỉ đích được đưa dưới dạng **hostname/domain name** có prefix độ dài; proxy có thể resolve.

**Câu 7.** `InetSocketAddress.createUnresolved` có gọi DNS ngay khi tạo không?  
**Đáp án:** Không; nó tạo một unresolved hostname+port object, hữu ích khi đưa tên đích qua SOCKS5.

**Câu 8.** Vì sao `HttpClient.proxy()` trả empty không chứng minh DIRECT?  
**Đáp án:** Nó chỉ nói không có explicit selector trong builder; client vẫn có thể dùng default selector.

**Câu 9.** Khi HTTP proxy xuống, có nên tự fallback DIRECT ngay?  
**Đáp án:** Chỉ khi policy cho phép. Với mạng doanh nghiệp egress bắt buộc, phải fail closed hoặc retry proxy được duyệt.

**Câu 10.** Proxy SOCKS5 có tự mã hóa nội dung TCP giữa client và origin?  
**Đáp án:** Không. HTTPS/TLS là lớp khác.

**Câu 11.** Với HTTP/2 qua proxy, `client.version()==HTTP_2` có chứng minh response chạy HTTP/2 không?  
**Đáp án:** Không. Kiểm tra `response.version()` của response thực.

**Câu 12.** Cần kiểm tra proxy traffic bằng cách nào, ngoài đọc cấu hình?  
**Đáp án:** Proxy-side request logs/counters hoặc packet capture trong mạng test được phép, đối chiếu origin, target, CONNECT/SOCKS handshake và status; không đọc lén traffic người khác.

## 18. Checklist triển khai an toàn

1. **Định nghĩa route** cho mỗi kind of request: DIRECT, HTTP_PROXY hoặc SOCKS; không dùng một string “proxy=true” chung.
2. **Chọn đúng API**: JDK `HttpClient` cho HTTP proxy, `Socket(Proxy.Type.SOCKS)` cho SOCKS TCP; không trộn `Proxy` và `ProxySelector`.
3. **Phân biệt HTTP plaintext forward proxy và HTTPS CONNECT tunnel**; kiểm tra port, SNI, TLS verification.
4. **Quy định DNS**: origin hostname được resolve ở đâu; xác minh bằng test, không suy từ URI.
5. **Phân biệt authentication scopes**: 401 origin, 407 HTTP proxy, SOCKS method negotiation.
6. **Explicit NO_PROXY** khi cần direct; kiểm tra default proxy, nonProxyHosts và system properties khi không explicit.
7. **Không fail-open ngoài policy** khi proxy gặp lỗi; không cho bypass nội bộ/SSRF ngoài allowlist.
8. **Giữ TLS** giữa client và origin khi cần confidentiality/integrity, không tự tắt certificate validation.
9. **Hạn chế resource**: connect/read/request timeouts, body size, open sockets, retries, connection pool.
10. **Không mặc nhiên một proxy có thể nói nhiều protocol** chỉ vì dùng cổng 8080 hoặc 1080; thử handshake.
11. **Theo dõi route thật** ở integration test (proxy accept logs, direct origin logs) thay vì chỉ kiểm tra selector output.
12. **Đọc Javadoc đúng JDK version**, kiểm thử trên OS/provider/proxy tương ứng và nhớ library HTTP khác có support khác.
13. **Quản lý credentials an toàn** trong secret manager, không log Proxy-Authorization/username/password.
14. **Không xem proxy là VPN** hoặc bảo đảm giấu origin/domain/IP hoàn toàn; xác định threat model và data-flow thật.

## Tài liệu chuẩn và Javadoc

- [Java SE 17 — `java.net.Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Proxy.html): `Proxy.Type.HTTP`, `Proxy.Type.SOCKS` và `Proxy.NO_PROXY`.
- [Java SE 17 — `java.net.ProxySelector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html): `select`, `connectFailed`, `of` cho HTTP/HTTPS và default selector.
- [Java SE 17 — `java.net.Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `Socket(Proxy)` và ví dụ SOCKS/direct.
- [Java SE 17 — `InetSocketAddress`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): `createUnresolved` và DNS behavior.
- [Java SE 17 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `proxy(ProxySelector)`, `NO_PROXY` và HTTP proxy example.
- [Java SE 17 — `HttpClient`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): default selector, `client.proxy()`, HTTP/1.1 vs HTTP/2 support.
- [Java SE 17 — Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): `http.proxyHost`, `https.proxyHost`, `socksProxyHost`, `http.nonProxyHosts`, `java.net.useSystemProxies`.
- [Java SE 17 — `URL.openConnection(Proxy)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html): per-URL proxy và giới hạn protocol handler.
- [RFC 9110, `9.3.6 — HTTP CONNECT](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.6): tunnel semantics, authority-form target, rủi ro mở cổng.
- [RFC 1928 — SOCKS Protocol Version 5](https://www.rfc-editor.org/rfc/rfc1928.html): greeting, methods, CONNECT, BIND, UDP ASSOCIATE, ATYP, status.
- [OpenJDK issue JDK-8214516 — SOCKS proxy support in java.net.http.HttpClient](https://bugs.openjdk.org/browse/JDK-8214516): giới hạn cần kiểm tra khi muốn dùng JDK HttpClient với SOCKS.

**Tóm lại:** **DIRECT** kết nối tới origin, **HTTP proxy** xử lý routing ở tầng HTTP (và có thể `CONNECT` để tunnel HTTPS), còn **SOCKS5 proxy** thiết lập đường TCP dựa trên hostname/IP:port ở tầng thấp hơn HTTP. Java 17 cung cấp API **khác nhau** cho các route này; luôn kiểm tra **đường kết nối thực, DNS, TLS và authentication** thay vì chỉ nhìn thấy một đối tượng proxy trong cấu hình.
