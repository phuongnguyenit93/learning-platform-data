# Đường hầm CONNECT khi truy cập HTTPS qua proxy trong Java

## 1. Khi HTTPS phải đi qua HTTP proxy, có điều gì khác với HTTP thường?

Khi Java `HttpClient` gửi một request tới `https://api.example.com/orders` **qua một HTTP proxy**, proxy không thể đơn giản đọc một GET có URL rồi trả về nội dung HTTPS như đang xử lý HTTP cleartext. Client cần một kênh truyền byte tới **origin server** để tự thực hiện **TLS handshake** và trao đổi HTTP bên trong kênh đã mã hóa. Cơ chế phổ biến nhất là HTTP method **`CONNECT`**.

Ý chính:

- Client mở **TCP connection đến proxy**, không phải trực tiếp đến origin.
- Client gửi HTTP/1.1 `CONNECT api.example.com:443` cho proxy; đích có dạng **authority-form `host:port`**, không chứa path hay query.
- Proxy quyết định có được phép kết nối tới `api.example.com:443` hay không và, nếu đồng ý, mở kết nối từ proxy tới đích.
- Proxy trả một response **2xx**, thường là `HTTP/1.1 200 Connection Established`.
- **Ngay sau dòng trống kết thúc headers của response 2xx**, kết nối được chuyển sang **tunnel mode**. Các byte sau đó được chuyển tiếp hai chiều, không còn là các HTTP/1.1 requests gửi *đến proxy*.
- Client bắt đầu **TLS handshake qua tunnel** để xác thực origin theo tên miền/certificate, thỏa thuận khóa và thường thương lượng HTTP/1.1 hoặc HTTP/2 bằng ALPN.
- Client gửi request HTTPS thực tế (ví dụ GET `/orders`) **bên trong TLS**, rồi nhận response HTTPS của origin server. Với một forward proxy không chặn TLS, proxy chủ yếu relay các byte đã mã hóa, không được quyền đọc URI path, authorization hay body của HTTP bên trong.

~~~text
                      TRƯỚC TUNNEL
Java HttpClient               HTTP proxy                  HTTPS origin
     |                            |                            |
     |--- TCP connect ----------->|                            |
     |--- CONNECT host:443 ------>|                            |
     |                            |--- TCP connect host:443 -->|
     |<--- HTTP/1.1 200 ----------|<--- TCP established -------|
     |                            |                            |
     |                 TUNNEL HAI CHIỀU ĐÃ THIẾT LẬP           |
     |                            |                            |
     |--- TLS ClientHello =======>|==== opaque TLS bytes =====>|
     |<== TLS ServerHello ========|<=== opaque TLS bytes ======|
     |--- HTTPS GET /orders =====>|==== TLS ciphertext =======>|
     |<== HTTP 200 encrypted =====|<=== TLS ciphertext ========|
     |                            |                            |
     |             close/cancel/timeout của cả hai phía         |
~~~

**Đừng nhầm hai lần “HTTP 200” trong hình.** `200 Connection Established` là response **của proxy cho CONNECT**, cho biết tunnel được tạo. `200 OK` sau TLS là response **của origin** đối với GET/POST thật. Java `HttpClient.send(request, ...)` thông thường trả về `HttpResponse` đại diện cho **origin HTTP response**, không phải object riêng cho response 200 của CONNECT.

Bài thuộc **Java Advance - networking → Proxy và phiên HTTP**, tập trung vào **đường hầm CONNECT khi truy cập HTTPS qua proxy**, mô hình wire protocol, Java 17+, security và cách điều tra sự cố.

## 2. Mục tiêu học tập

Sau bài học bạn có thể:

1. Mô tả chính xác chuỗi **client → HTTP proxy → CONNECT → tunnel → TLS → HTTPS request/response**.
2. Đọc request `CONNECT host:port HTTP/1.1` ở **authority-form** và hiểu tại sao không gửi `/path` hay `https://.../path` làm target của CONNECT.
3. Phân biệt **response 2xx của CONNECT** với **HTTP response của tài nguyên đích**.
4. Hiểu tunnel là **forward byte stream hai chiều**, khác proxy đọc, cache, sửa HTTP messages.
5. Biết TLS certificate, hostname verification, SNI và ALPN hoạt động như thế nào **sau khi tunnel được thiết lập**.
6. Phân biệt HTTP proxy dùng để tiếp cận HTTPS origin với **HTTPS proxy** (bản thân kết nối tới proxy cũng dùng TLS), SOCKS proxy và reverse proxy.
7. Cấu hình Java 17 `HttpClient.Builder.proxy(ProxySelector.of(...))`, `SSLContext` khi cần và `Authenticator` cho proxy authentication.
8. Nhận biết `407 Proxy Authentication Required`, `403`, `502`, TLS handshake failure, `ConnectException`, `UnknownHostException` và timeout theo từng bước.
9. Chạy ví dụ raw CONNECT với local TCP echo để quan sát proxy chuyển từ HTTP headers sang forwarding.
10. Chạy ví dụ có **HTTPS server + HTTP CONNECT proxy + Java HttpClient thực sự**, dùng test certificate được trust rõ ràng **không tắt hostname verification**.
11. Nhìn ra các rủi ro: arbitrary CONNECT destinations, SSRF, port 25, proxy credential leakage, TLS interception, certificate trust, open proxy và resource exhaustion.
12. Thiết kế proxy policy, retry, observability, test và shutdown đúng trách nhiệm.

## 3. CONNECT nằm ở đâu trong bộ giao thức?

CONNECT là **HTTP method dành chủ yếu cho proxy**. HTTP RFC 9110 `9.3.6` định nghĩa phương thức này với mục đích yêu cầu intermediary mở một **tunnel** đến máy chủ đích, rồi **chuyển tiếp dữ liệu hai chiều** mà không diễn giải nội dung bên trong.

### 3.1. Wire request HTTP/1.1

~~~http
CONNECT api.example.com:443 HTTP/1.1
Host: api.example.com:443

~~~

Trên wire, mỗi dòng kết thúc bằng `\r\n` và dòng trống cuối cùng là `\r\n\r\n`. Đây là message **client gửi cho proxy**, không phải GET/POST tới HTTPS origin.

- **`CONNECT`**: method đặc biệt dùng để tạo tunnel.
- **`api.example.com:443`**: authority-form gồm host và **port bắt buộc**; không có mặc định 443 nếu thiếu.
- **`Host: api.example.com:443`**: HTTP/1.1 host/authority metadata của request.
- **Không có body request CONNECT** theo semantics.
- **Không có `GET /orders`** ở bước này: URI path nằm trong HTTP message **được mã hóa sau TLS**, nếu tunnel thành công.

RFC 9110 yêu cầu explicit port trong CONNECT request-target ngay cả khi URL `https://api.example.com/orders` bỏ qua port và ngầm dùng 443. Những request như sau là sai hoặc không phải CONNECT authority-form hợp lệ:

~~~text
CONNECT https://api.example.com/orders HTTP/1.1  # SAI: URL đầy đủ
CONNECT /orders HTTP/1.1                   # SAI: chỉ path
CONNECT api.example.com HTTP/1.1          # SAI: thiếu port
CONNECT api.example.com:443 HTTP/1.1      # ĐÚNG
~~~

Các dấu `#` trong ví dụ trên là **chú thích diễn giải**, không phải nội dung request HTTP. Với IPv6 literal, target dạng authority bao gồm địa chỉ đặt trong ngoặc vuông:

~~~http
CONNECT [2001:db8::10]:443 HTTP/1.1
Host: [2001:db8::10]:443

~~~

Địa chỉ `2001:db8::/32` dành cho tài liệu, **không** phải server thực tế. Không tự bỏ ngoặc vuông trong IPv6 authority vì dấu `:` còn nằm trong địa chỉ.

### 3.2. 2xx chuyển chế độ, không phải trả file

Proxy có thể phản hồi:

~~~http
HTTP/1.1 200 Connection Established

~~~

Từ byte **ngay sau header terminator** của response 2xx, hai phía phải hiểu rằng kết nối không còn chuyên chở HTTP request–response message thường gửi cho proxy nữa. Dữ liệu sau đó thuộc **tunnel stream**: TLS records, protocol bytes, hoặc payload khác mà client và origin thỏa thuận.

Các điểm chính trong chuẩn:

- **Bất kỳ successful 2xx response** của CONNECT đều biểu thị tunnel được thiết lập (200 chỉ là giá trị phổ biến).
- Response CONNECT **không thành công** (ví dụ 403, 407, 502) nghĩa là **chưa có tunnel**; client phải xử lý status như proxy response.
- Proxy **không được gửi** `Content-Length` hoặc `Transfer-Encoding` trong response 2xx CONNECT. Client phải **bỏ qua** những header này nếu lỡ nhận được trong response thành công.
- Đừng mong có JSON body kèm response 200 CONNECT; byte sau dòng trống là byte từ tunnel.
- Response cho CONNECT **không được cache** theo HTTP semantics.
- Khi một bên đóng, proxy cần cố gắng chuyển nốt dữ liệu đang chờ rồi đóng/giải phóng cả hai đầu theo hợp đồng tunnel.

Đây không phải `HTTP 101 Switching Protocols`. CONNECT thành công dùng **2xx** để chuyển thành tunnel; HTTP Upgrade/h2c/WebSocket handshake có cơ chế riêng. Đừng dùng 101 làm chỉ báo CONNECT thông thường.

### 3.3. 2 lớp trạng thái HTTP

~~~text
LỚP NGOÀI: PROXY CONTROL (trước tunnel)
Client -> Proxy: CONNECT target:443
Proxy  -> Client: 200 / 403 / 407 / 502 ...

LỚP BÊN TRONG: HTTPS APPLICATION (sau TLS)
Client -> Origin: GET /v1/orders HTTP/1.1 (bên trong TLS)
Origin -> Client: 200 / 401 / 404 / 500 ... (bên trong TLS)
~~~

**Ví dụ:** Nếu Java client nhận `HttpResponse.statusCode() == 404` cho request GET `https://api.example.com/missing`, đó thường là response **của origin sau tunnel/TLS**, **không** phải proxy nói CONNECT 404. Ngược lại, nếu proxy trả 407 và authentication không thành công, Java client có thể fail **trước khi tạo được HTTPS response**; không có body/headers của origin để xử lý.

## 4. So sánh ba cách đi qua proxy

| Đường đi | Client gửi tới proxy | Proxy thấy HTTP nội dung gì? | Bảo mật |
| --- | --- | --- | --- |
| HTTP `http://...` qua HTTP proxy | Thường HTTP request với target dạng absolute-form như `GET http://example.com/a HTTP/1.1` | Proxy có thể đọc method, path, headers, body nếu hop cleartext | Không có TLS origin theo scheme HTTP thuần |
| HTTPS `https://...` qua HTTP proxy | Thường `CONNECT example.com:443`, sau đó TLS bên trong tunnel | Thấy CONNECT target/metadata và traffic metadata; không đọc HTTP payload bên trong TLS nếu không chặn TLS | TLS end-to-end giữa client và origin trong mô hình forwarding đúng chuẩn |
| HTTPS `https://...` qua proxy có **TLS trên hop proxy** | TLS client–proxy trước, CONNECT bên trong TLS đó, rồi TLS client–origin qua tunnel | Proxy vẫn biết target sau khi giải mã TLS client–proxy; origin payload vẫn mã hóa bằng TLS bên trong | Có hai lớp TLS trên những đoạn khác nhau, phụ thuộc khả năng hỗ trợ của client/proxy |

**HTTP proxy** không có nghĩa “chỉ truy cập website HTTP”. Nó có thể tạo tunnel cho HTTPS bằng CONNECT. Ngược lại, tên gọi **HTTPS proxy** thường chỉ proxy endpoint được bảo vệ bằng TLS từ client tới proxy, **khác** việc proxy HTTP thường dùng để tiếp cận HTTPS origin.

SOCKS proxy điều phối kết nối bằng **SOCKS protocol**, không phải HTTP CONNECT; Java `java.net.http.HttpClient` proxy support trong API Java 17 cần đọc theo khả năng implementation, không giả định một `ProxySelector` bất kỳ khiến Java tự hỗ trợ mọi dạng SOCKS handshake.

Reverse proxy trước origin là thành phần khác: Java client có thể kết nối HTTPS tới reverse proxy trực tiếp và **không cần CONNECT**. CONNECT đặc trưng cho **forward proxy/tunnel policy** và một số trường hợp proxy protocols mở rộng.

## 5. TLS handshake xảy ra **sau** khi CONNECT thành công

Dòng thời gian chính xác của một HTTPS request đi qua HTTP proxy thường là:

~~~text
T0  Java resolve/connect tới proxyHost:proxyPort
T1  Client -> Proxy: CONNECT origin.example:443 HTTP/1.1
T2  Proxy kiểm tra ACL / authentication / policy
T3  Proxy resolve/connect tới origin.example:443
T4  Proxy -> Client: HTTP/1.1 200 Connection Established
T5  Client -> Origin (qua tunnel): TLS ClientHello
T6  Origin -> Client (qua tunnel): TLS handshake messages
T7  Client kiểm tra certificate chain + hostname
T8  TLS handshake xong; có thể ALPN chọn h2 hoặc http/1.1
T9  Client -> Origin (encrypted): GET /resource ...
T10 Origin -> Client (encrypted): HTTP response
T11 Giữ hoặc đóng connection/tunnel theo lifecycle
~~~

Lưu ý:

- **CONNECT 200 không xác nhận TLS thành công**; TLS handshake có thể thất bại ngay sau đó.
- **TLS handshake thành công không chứng minh HTTP status 200**; origin vẫn có thể trả 401/404/500.
- Proxy có thể thấy `origin.example:443` ở CONNECT và các metadata mạng (thời gian, lưu lượng, địa chỉ). Trong nhiều cấu hình không dùng ECH, tên SNI trong ClientHello cũng có thể quan sát được. **Không** coi tunnel là ẩn danh hoàn toàn.
- Với proxy forwarding thuần, proxy **không có private key** của origin và không tự giải mã các HTTP requests/bodies bên trong TLS.
- Client phải validate certificate/hostname theo HTTPS URI; nếu proxy chuyển tới endpoint giả, hostname verification đúng sẽ giúp phát hiện.
- ALPN (thông thường qua TLS) có thể thương lượng `h2` hoặc `http/1.1` **giữa Java client và HTTPS endpoint** trong tunnel. CONNECT của proxy bản thân nó có thể là HTTP/1.1 mà **HTTPS bên trong lại là HTTP/2**.
- TLS record/handshake traffic **không giống text GET/POST**; không thể đọc payload sau CONNECT bằng cách parse dòng HTTP/1.1 từ proxy.
- Nếu proxy enterprise cài đặt **TLS interception** với một CA do thiết bị client tin cậy, proxy có thể làm TLS endpoint và giải mã/kiểm tra request. Đó **không còn** là mô hình blind forwarding tới origin như trên; phải theo chính sách doanh nghiệp, cảnh báo bảo mật và trust model. Không hướng dẫn vô hiệu certificate verification để “giúp proxy chạy”.

### 5.1. Ai thực hiện DNS cho origin?

Client phải biết cách tìm **proxy** để mở TCP connection trước. Origin hostname được gửi trong `CONNECT hostname:port`; **proxy thường** thực hiện DNS resolution và mở TCP tới origin. Tuy nhiên hành vi DNS cụ thể còn phụ thuộc client implementation, route, proxy chaining và policy.

Đừng nói chắc “client không bao giờ resolve origin” hoặc “proxy luôn resolve origin”: client có thể resolve hostname để thực thi chính sách/caching/diagnostics, và proxy có thể chuyển tiếp CONNECT tới proxy tiếp theo. Phân biệt **ai mở TCP origin hop** và **ai thực hiện DNS query** theo thiết kế thật.

### 5.2. CONNECT không “nâng” một request HTTP thường thành HTTPS

Giả sử Java code dùng URI `http://api.example.com/a` nhưng cấu hình HTTP proxy. Chỉ có proxy không có nghĩa dữ liệu tự được mã hóa TLS; client có thể gửi HTTP cleartext `GET http://api.example.com/a` cho proxy. Nếu muốn HTTPS, phải dùng **`https://` URI** và xác thực TLS.

Cũng đừng nghĩ CONNECT 200 là một “chứng nhận origin đáng tin”. Nó chỉ báo proxy tuyên bố đã tạo tunnel. **TLS xác thực origin** diễn ra sau đó.

## 6. Dùng Java 17 HttpClient: không cần viết CONNECT thủ công

Ở tầng ứng dụng, cấu hình HTTP proxy bằng `ProxySelector`:

~~~java
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.example.net", 3128)))
        .connectTimeout(Duration.ofSeconds(5))
        .version(HttpClient.Version.HTTP_2)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/v1/items"))
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.statusCode());
~~~

Đây là **mảnh code dùng trong method `throws Exception`**; tên miền/port chỉ minh họa, không có stdout xác thực. Java `HttpClient` **tự xử lý proxy selection, CONNECT, TLS handshake và HTTP framing**; ứng dụng không cần tự xây request `CONNECT` hoặc đẩy TLS records qua `Socket`.

**Những phân biệt quan trọng:**

- `ProxySelector.of(InetSocketAddress)` tạo selector sử dụng một proxy được chỉ định. Với Java 17 `HttpClient.Builder.proxy(...)`, đây là cách phổ biến để chọn HTTP proxy cụ thể.
- `HttpClient.newBuilder().proxy(...)` ghi proxy policy ở **client**. Sau khi build, thay default `ProxySelector` hệ thống thường không tự thay đổi client đã tạo.
- Nếu không gọi `.proxy(...)`, Java HttpClient có thể dùng default/system proxy selector tùy runtime/config. `HttpClient.proxy()` có thể trả `Optional.empty()` dù vẫn có default selector không được expose.
- `ProxySelector` có thể chọn direct hoặc proxy tùy URI; nếu muốn bypass, dùng selector/policy phù hợp. Không suy rằng mọi request sẽ luôn đi proxy nếu application/hệ thống cấu hình nhiều routes.
- `version(HTTP_2)` là **preference**; HTTP response thực tế có thể là `HTTP_1_1`. Đọc `response.version()` thay vì coi proxy dùng HTTP/1.1 nghĩa origin chắc chắn h1.
- `HttpClient` Java 17 chưa `AutoCloseable` theo API Java 17; không dùng `try (HttpClient client = ...)` khi compile `--release 17`.
- `connectTimeout` áp dụng giai đoạn thiết lập connection theo API; `HttpRequest.timeout` áp dụng request deadline. Không coi hai option này tự đặt một timeout riêng cho mọi bước proxy/TLS/response trong mọi implementation. Dùng tổng deadline/monitoring thích hợp.
- **Không** tự thêm `Proxy-Authorization` như một header của request ứng dụng để “bắt proxy CONNECT” nếu HTTP stack quản lý authentication; dùng `Authenticator`/policy thích hợp và kiểm tra đặc tính của JDK.

### 6.1. Khi cần proxy authentication

HTTP CONNECT có thể yêu cầu đăng nhập proxy:

~~~http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Basic realm="private-proxy"

~~~

Dòng trên là ví dụ **challenge của proxy**, không phải lỗi authorization từ origin. Client được phép thực hiện authentication theo scheme được hỗ trợ và policy security; một retry CONNECT có thể mang `Proxy-Authorization` cho proxy:

~~~http
CONNECT api.example.com:443 HTTP/1.1
Host: api.example.com:443
Proxy-Authorization: Basic <credential-value>

~~~

Giá trị `<credential-value>` trong ví dụ là **placeholder mô tả**, không phải credential có thể dùng. Nếu copy vào HTTP request thật, phải thay bằng cơ chế authentication chuẩn và giá trị có thực; không log token/password. Việc base64 hóa Basic **không** phải encryption. Khi hop client–proxy là HTTP cleartext, Basic credentials có thể bị quan sát; ưu tiên proxy connection được bảo vệ và auth scheme/policy thích hợp.

Ví dụ Java 17 skeleton dùng `Authenticator`:

~~~java
HttpClient client = HttpClient.newBuilder()
    .proxy(ProxySelector.of(
        new InetSocketAddress("proxy.example.net", 3128)))
    .authenticator(new java.net.Authenticator() {
        @Override
        protected java.net.PasswordAuthentication getPasswordAuthentication() {
            // Chỉ trả thông tin khi đây là proxy được tin cậy,
            // không lấy từ literal hard-coded trong source code.
            if (getRequestorType() != RequestorType.PROXY) {
                return null;
            }
            return new java.net.PasswordAuthentication(
                    usernameFromSecureStore, passwordCharsFromSecureStore);
        }
    })
    .build();
~~~

**Mảnh code**, cần những biến `usernameFromSecureStore`/`passwordCharsFromSecureStore` và imports `HttpClient`, `ProxySelector`, `InetSocketAddress`; không standalone. Trong code thật, còn phải xác minh đúng proxy host/port/realm trước khi trả credential để tránh cấp cho proxy khác do cấu hình bị thay đổi.

**Java 17 có lưu ý bảo mật:** property `jdk.http.auth.tunneling.disabledSchemes` mặc định bao gồm **`Basic`** đối với HTTPS tunneling qua CONNECT. Vì thế có `Authenticator` **không bảo đảm** Java sẽ gửi Basic auth cho CONNECT. Đây là một trong các nguyên nhân gặp repeated 407. Đọc tài liệu Oracle Networking System Properties và chính sách cơ quan trước khi thay cấu hình; **không** tùy tiện bỏ `Basic` khỏi danh sách disable chỉ để test chạy, đặc biệt trên mạng không tin cậy. Chọn proxy và scheme authentication được tổ chức hỗ trợ an toàn.

### 6.2. Java HttpClient không biểu diễn CONNECT như request nghiệp vụ

Mục tiêu application vẫn là:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/resource")).GET().build();
HttpResponse<String> result = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

Client library có thể tự phát sinh CONNECT ở **protocol layer** trước khi gửi GET. Đừng tự tạo:

~~~java
HttpRequest.newBuilder(URI.create("https://api.example.com"))
    .method("CONNECT", HttpRequest.BodyPublishers.noBody())
    .build();
~~~

để rồi mong Java tự mở tunnel cho một HTTPS GET khác. Đó là yêu cầu **ứng dụng tự gửi method CONNECT** tới URI, khác với cơ chế CONNECT nội bộ do HTTP stack quản lý để dùng proxy. Không phải cách sử dụng bình thường của `HttpClient.proxy(...)`; ứng dụng thường không có quyền xem/điều khiển raw tunnel socket trực tiếp qua `HttpResponse`.

## 7. Chương trình Java 17+ số 1: mô phỏng raw CONNECT và relay byte

Ví dụ đầu tiên chỉ minh họa **bước HTTP CONNECT và chuyển sang tunnel**; nó **không làm TLS handshake**. Sau khi proxy tạo tunnel tới một local TCP echo server, client gửi bốn byte `PING` và nhận `PONG`. Điều này giúp quan sát chính xác rằng **sau CONNECT 2xx, proxy không còn parse request như HTTP nữa, mà chỉ forward bytes hai chiều**.

Không nên hiểu `PING` và `PONG` là HTTPS; chúng là byte thô để kiểm tra tunnel. Ví dụ HTTPS thực sự với chứng chỉ được kiểm tra nằm ở phần 8.

### 7.1. File `HttpConnectEchoDemo.java`

~~~java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class HttpConnectEchoDemo {
    private static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int state = 0;
        while (buf.size() < 4096) {
            int b = in.read();
            if (b == -1) throw new IOException("Headers incomplete");
            buf.write(b);
            state = switch (state) {
                case 0 -> b == '\r' ? 1 : 0;
                case 1 -> b == '\n' ? 2 : b == '\r' ? 1 : 0;
                case 2 -> b == '\r' ? 3 : 0;
                default -> b == '\n' ? 4 : b == '\r' ? 1 : 0;
            };
            if (state == 4) return buf.toString(StandardCharsets.US_ASCII);
        }
        throw new IOException("Header limit exceeded");
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        ExecutorService workers = Executors.newFixedThreadPool(3);
        try (ServerSocket origin = new ServerSocket(0, 1, loopback);
             ServerSocket proxy = new ServerSocket(0, 1, loopback)) {
            origin.setSoTimeout(5000);
            proxy.setSoTimeout(5000);
            Future<String> originTask = workers.submit(() -> {
                try (Socket upstream = origin.accept()) {
                    upstream.setSoTimeout(5000);
                    String request = new String(
                            upstream.getInputStream().readNBytes(4),
                            StandardCharsets.US_ASCII);
                    upstream.getOutputStream().write(
                            "PONG".getBytes(StandardCharsets.US_ASCII));
                    return request;
                }
            });
            Future<String> proxyTask = workers.submit(() -> {
                try (Socket incoming = proxy.accept()) {
                    incoming.setSoTimeout(5000);
                    String headers = readHeaders(incoming.getInputStream());
                    String requestLine = headers.split("\r\n", 2)[0];
                    String expected = "CONNECT 127.0.0.1:" +
                            origin.getLocalPort() + " HTTP/1.1";
                    if (!requestLine.equals(expected)) {
                        incoming.getOutputStream().write(
                                "HTTP/1.1 403 Forbidden\r\n\r\n".getBytes(
                                        StandardCharsets.US_ASCII));
                        return requestLine;
                    }
                    try (Socket outgoing = new Socket(
                            loopback, origin.getLocalPort())) {
                        outgoing.setSoTimeout(5000);
                        incoming.getOutputStream().write(
                                "HTTP/1.1 200 Connection Established\r\n\r\n"
                                        .getBytes(StandardCharsets.US_ASCII));
                        Future<?> toOrigin = workers.submit(() -> {
                            try {
                                incoming.getInputStream()
                                        .transferTo(outgoing.getOutputStream());
                                outgoing.shutdownOutput();
                            } catch (IOException error) {
                                throw new RuntimeException(error);
                            }
                        });
                        outgoing.getInputStream()
                                .transferTo(incoming.getOutputStream());
                        incoming.shutdownOutput();
                        toOrigin.get(5, TimeUnit.SECONDS);
                    }
                    return requestLine;
                }
            });

            try (Socket client = new Socket(loopback, proxy.getLocalPort())) {
                client.setSoTimeout(5000);
                String target = "127.0.0.1:" + origin.getLocalPort();
                String connect = "CONNECT " + target + " HTTP/1.1\r\n" +
                        "Host: " + target + "\r\n\r\n";
                client.getOutputStream().write(
                        connect.getBytes(StandardCharsets.US_ASCII));
                String status = readHeaders(client.getInputStream())
                        .split("\r\n", 2)[0];
                System.out.println("Proxy reply: " + status);
                client.getOutputStream().write(
                        "PING".getBytes(StandardCharsets.US_ASCII));
                client.shutdownOutput();
                String reply = new String(
                        client.getInputStream().readNBytes(4),
                        StandardCharsets.US_ASCII);
                System.out.println("Tunnel reply: " + reply);
            }
            System.out.println("Origin received: " +
                    originTask.get(5, TimeUnit.SECONDS));
            System.out.println("Valid CONNECT seen: " +
                    proxyTask.get(5, TimeUnit.SECONDS).startsWith(
                            "CONNECT 127.0.0.1:"));
        } finally {
            workers.shutdownNow();
        }
    }
}
~~~

Biên dịch bằng API Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 HttpConnectEchoDemo.java
java HttpConnectEchoDemo
~~~

**Stdout đã được biên dịch và chạy trên OpenJDK 24 với `--release 17`:**

~~~text
Proxy reply: HTTP/1.1 200 Connection Established
Tunnel reply: PONG
Origin received: PING
Valid CONNECT seen: true
~~~

### 7.2. Giải thích code

- `ServerSocket origin` đại diện cho TCP endpoint, chỉ nghe trên loopback và OS tự chọn port.
- `ServerSocket proxy` đại diện HTTP proxy tối giản, cũng chỉ nghe loopback.
- `readHeaders(...)` đọc **đúng cho tới CRLF CRLF**, có hạn mức 4096 byte để tránh một header vô tận trong demo. Vì đọc từng byte, nó **không vô tình đọc trước byte của tunnel** vào buffer khi chuyển chế độ.
- Proxy kiểm tra request line **bằng whitelist target của chính demo**; nếu target sai, trả 403 và không kết nối tới server khác. Chặn arbitrary CONNECT destinations là một nguyên tắc an toàn thực tế.
- Khi kết nối origin được thiết lập, proxy gửi `HTTP/1.1 200 Connection Established` rồi thực hiện `transferTo` trên streams ở **cả hai hướng**.
- Client sau khi đọc headers 200 **không gửi thêm một HTTP request tới proxy**. Nó gửi raw `PING`; origin trả `PONG`.
- `client.shutdownOutput()` là thao tác **TCP half-close** phía client, báo hết chiều gửi nhưng vẫn đọc chiều nhận được.
- Thread relay client→origin gọi `outgoing.shutdownOutput()` sau khi EOF, cho origin biết client đã gửi xong. Chiều origin→client vẫn được relay độc lập.
- Server/proxy dùng try-with-resources và `ExecutorService.shutdownNow()` để dọn tài nguyên demo.

**Giới hạn:** đây là một proxy tối giản chỉ chấp nhận **đúng một CONNECT tới port do chính ứng dụng tạo**, không implement RFC-complete HTTP parser, proxy authentication, production logging, TLS, request limits toàn diện, forwarding lifecycle của nhiều sockets, rate limits, DNS policy hay graceful shutdown. **Không triển khai thành public proxy trên Internet**. Nó tồn tại để dạy chuyển từ HTTP control sang byte-tunnel và chỉ được chạy trên loopback.

## 8. Chương trình Java 17+ số 2: HTTPS thật qua HTTP CONNECT proxy

Ví dụ thứ hai dùng chính `java.net.http.HttpClient` để truy cập **một HTTPS origin nội bộ** thông qua **một HTTP CONNECT proxy nội bộ**. Khác với ví dụ trước, client thực hiện **TLS handshake và certificate/hostname validation thực sự**.

Các thành phần:

- `HttpsServer` thuộc module chuẩn `jdk.httpserver` làm **HTTPS origin**, bind `127.0.0.1` với port tạm.
- `ServerSocket` làm **HTTP CONNECT proxy** tối giản, chỉ mở tunnel tới đúng origin/port đã biết.
- `HttpClient` có `ProxySelector.of(...)` trỏ tới proxy.
- `SSLContext` client được khởi tạo từ **truststore chứa certificate test** để xác thực local server. **Không dùng trust-all `X509TrustManager`, không tắt hostname verification.**
- Một certificate **tạm thời, self-signed cho `localhost`**, có Subject Alternative Name phù hợp, được tạo bằng `keytool` chỉ để kiểm thử.
- Response 200 và body `secure-ok` là **origin response sau TLS**, trong khi proxy đã nhìn thấy CONNECT.

### 8.1. Chuẩn bị test keystore/truststore

**Yêu cầu:** JDK 17+ có lệnh `keytool`, shell trong một thư mục test riêng do bạn sở hữu. Tạo certificate mới, có SAN cho `localhost`, hiệu lực 2 ngày và chỉ dùng với loopback:

~~~bash
keytool -genkeypair -alias origin -keyalg RSA -keysize 2048 -storetype PKCS12 -keystore origin.p12 -storepass changeit -keypass changeit -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1" -validity 2 -noprompt
keytool -exportcert -alias origin -keystore origin.p12 -storepass changeit -rfc -file origin.pem
keytool -importcert -alias origin -file origin.pem -storetype PKCS12 -keystore trust.p12 -storepass changeit -noprompt
~~~

**Bảo mật:** `changeit` ở đây là mật khẩu **cố định cho file test tạm, không được dùng trong production**. Không commit `origin.p12` (chứa private key) lên Git, không tải nó lên Internet, không import certificate test vào truststore hệ thống hay JDK toàn cục. Sau bài thực hành, xóa `origin.p12`, `origin.pem` và `trust.p12` trong thư mục test. Certificate self-signed sẽ không được JVM tin cậy nếu bạn **không** cung cấp truststore test riêng — đó là hành vi bảo mật đúng.

### 8.2. Tệp `HttpsThroughConnectProxyDemo.java`

~~~java
import com.sun.net.httpserver.HttpsServer;
import com.sun.net.httpserver.HttpsConfigurator;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.Socket;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class HttpsThroughConnectProxyDemo {
    private static String readHeaders(InputStream input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int state = 0;
        while (output.size() < 8192) {
            int b = input.read();
            if (b < 0) throw new IOException("Unexpected EOF in proxy headers");
            output.write(b);
            state = switch (state) {
                case 0 -> b == '\r' ? 1 : 0;
                case 1 -> b == '\n' ? 2 : b == '\r' ? 1 : 0;
                case 2 -> b == '\r' ? 3 : 0;
                default -> b == '\n' ? 4 : b == '\r' ? 1 : 0;
            };
            if (state == 4) {
                return output.toString(StandardCharsets.US_ASCII);
            }
        }
        throw new IOException("Proxy header exceeded limit");
    }

    private static SSLContext serverTls(Path store) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(store)) {
            ks.load(stream, "changeit".toCharArray());
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(ks, "changeit".toCharArray());
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), null, new SecureRandom());
        return context;
    }

    private static SSLContext clientTls(Path trust) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(trust)) {
            ks.load(stream, "changeit".toCharArray());
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(ks);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException(
                "Usage: java HttpsThroughConnectProxyDemo origin.p12 trust.p12");

        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpsServer origin = HttpsServer.create(
                new InetSocketAddress(loopback, 0), 0);
        origin.setHttpsConfigurator(new HttpsConfigurator(
                serverTls(Path.of(args[0]))));

        origin.createContext("/secret", exchange -> {
            try (exchange) {
                byte[] content = "secure-ok".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "text/plain");
                exchange.getResponseHeaders().set("Connection", "close");
                exchange.sendResponseHeaders(200, content.length);
                exchange.getResponseBody().write(content);
            }
        });

        ExecutorService workers = Executors.newFixedThreadPool(2);
        try (ServerSocket proxy = new ServerSocket(0, 1, loopback)) {
            proxy.setSoTimeout(10000);
            origin.start();
            Future<String> connectLine = workers.submit(() -> {
                try (Socket incoming = proxy.accept()) {
                    incoming.setSoTimeout(10000);
                    String headers = readHeaders(incoming.getInputStream());
                    String line = headers.split("\r\n", 2)[0];
                    String expected = "CONNECT localhost:" +
                            origin.getAddress().getPort() + " HTTP/1.1";

                    if (!line.equals(expected)) {
                        incoming.getOutputStream().write(
                                "HTTP/1.1 403 Forbidden\r\n\r\n".getBytes(
                                        StandardCharsets.US_ASCII));
                        return line;
                    }

                    try (Socket upstream = new Socket(
                            loopback, origin.getAddress().getPort())) {
                        upstream.setSoTimeout(10000);
                        incoming.getOutputStream().write(
                                "HTTP/1.1 200 Connection Established\r\n\r\n"
                                        .getBytes(StandardCharsets.US_ASCII));

                        Future<?> up = workers.submit(() -> {
                            try {
                                incoming.getInputStream()
                                        .transferTo(upstream.getOutputStream());
                            } catch (IOException e) {
                                // Expected when the short demonstration closes.
                            }
                        });

                        upstream.getInputStream().transferTo(
                                incoming.getOutputStream());
                        up.get(10, TimeUnit.SECONDS);
                    }
                    return line;
                }
            });

            HttpClient client = HttpClient.newBuilder()
                    .proxy(ProxySelector.of(new InetSocketAddress(
                            loopback, proxy.getLocalPort())))
                    .sslContext(clientTls(Path.of(args[1])))
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(5))
                    .build();

            URI uri = URI.create("https://localhost:" +
                    origin.getAddress().getPort() + "/secret");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(8))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

            System.out.println("HTTPS status: " + response.statusCode());
            System.out.println("HTTPS body: " + response.body());
            System.out.println("Protocol: " + response.version());

            origin.stop(0);
            System.out.println("CONNECT observed: " + connectLine
                    .get(10, TimeUnit.SECONDS).startsWith(
                            "CONNECT localhost:"));
        } finally {
            origin.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

### 8.3. Compile, run, kết quả đã kiểm chứng

Chạy trong **cùng thư mục** nơi vừa tạo `origin.p12` và `trust.p12`:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver HttpsThroughConnectProxyDemo.java
java --add-modules jdk.httpserver HttpsThroughConnectProxyDemo origin.p12 trust.p12
~~~

**Stdout được kiểm chứng trên OpenJDK 24, code biên dịch tương thích `--release 17`:**

~~~text
HTTPS status: 200
HTTPS body: secure-ok
Protocol: HTTP_1_1
CONNECT observed: true
~~~

Các thông điệp từ `keytool` khi tạo/trust certificate phụ thuộc ngôn ngữ của máy và không phải stdout ứng dụng Java. Vì port do OS tự chọn, chương trình in boolean xác nhận request `CONNECT localhost:...` thay vì in một port cố định.

### 8.4. Phân tích từng giai đoạn

1. `HttpsServer` nhận HTTPS trên `127.0.0.1`, port OS chọn. Tên URL là **`localhost`**, và certificate có **SAN dns:localhost**; Java client trust certificate từ `trust.p12` và kiểm tra hostname bình thường.
2. Proxy `ServerSocket` chỉ accept **một CONNECT** và đối chiếu đúng target. Đây không phải open proxy.
3. `HttpClient.Builder.proxy(ProxySelector.of(...))` yêu cầu dùng HTTP proxy local. Java library tự phát sinh `CONNECT localhost:<port>` vì URI đích là `https://localhost:<port>/secret`.
4. Proxy nhận CONNECT, **chỉ mở TCP** tới local HTTPS server; sau đó trả `200 Connection Established`.
5. Java client khởi tạo **TLS handshake thông qua tunnel**. Proxy không cài server certificate trong vai trò CA và không giải mã HTTP payload.
6. Java client thực hiện GET `/secret` trên HTTPS connection. Origin gửi body `secure-ok`.
7. `HttpResponse.statusCode()==200` là **origin HTTP status**. `HttpResponse.version()==HTTP_1_1` vì ví dụ ép HTTP/1.1 để ổn định kết quả; nó **không** cho biết CONNECT proxy status.
8. `CONNECT observed: true` xác nhận proxy đã thấy CONNECT line. Với một proxy thật, request thường còn có headers và authentication policy; lab chỉ cần kiểm tra line.
9. `origin.stop(0)` và `workers.shutdownNow()` kết thúc các service local sau khi trao đổi. Trong deployment lâu dài phải quản lý connection pool/tunnels, graceful drain, futures, exceptions và timeout đầy đủ.

**Ranh giới bảo mật:** demo dùng certificate self-signed nhưng **không bỏ qua kiểm tra certificate**; nó tin cậy một **CA/certificate test đã nhập riêng vào `trust.p12`**, không ảnh hưởng truststore hệ thống. Không copy `changeit` hay tư duy “trust mọi certificate” vào sản phẩm.

**Giới hạn của proxy demo:** `readHeaders` chưa phải HTTP parser hoàn chỉnh, chưa xử lý nhiều concurrent CONNECTs, retry authentication, partial shutdown tinh vi, DOS mitigations, header limits đa tầng hoặc HTTP/2 CONNECT mapping. SocketTimeout ở đây chỉ giữ bài test không treo vô hạn. **Không sử dụng code làm proxy production.**

## 9. Những lỗi phổ biến trong vòng đời CONNECT/TLS

Một HTTPS request qua proxy có **nhiều điểm lỗi** độc lập.

~~~text
(1) Resolve/connect tới proxy
        |-- DNS proxy fail / ConnectException / timeout
        v
(2) CONNECT tới origin host:port
        |-- 400 malformed target
        |-- 403 policy denied
        |-- 407 proxy auth required
        |-- 502/504 proxy không kết nối được upstream
        v
(3) CONNECT 2xx, tunnel ready
        |-- origin TCP bị reset / proxy relay timeout
        v
(4) TLS handshake trong tunnel
        |-- certificate không tin cậy / wrong hostname / TLS mismatch
        v
(5) HTTPS request/response tại origin
        |-- 401/403/404/429/500/503 ở HTTP application layer
        v
(6) Drain/close response/tunnel đúng lifecycle
~~~

| Triệu chứng | Tầng chịu trách nhiệm chủ yếu | Hướng chẩn đoán |
| --- | --- | --- |
| Không resolve được proxy hostname | DNS của proxy | Kiểm tra tên proxy, resolver, VPN, network |
| TCP connect tới proxy bị từ chối | Transport client→proxy | Host/port/listener/firewall |
| Proxy trả 400 cho CONNECT | Proxy control HTTP | Authority-form, host:port, header syntax |
| Proxy trả 403 | Proxy policy | ACL, đích/port không được phép, danh sách deny |
| Proxy trả 407 | Proxy authentication | `Proxy-Authenticate`, `Authenticator`, scheme disabled, credentials |
| Proxy trả 502 | Proxy upstream hop | Proxy không thể kết nối origin; kiểm tra DNS/firewall/origin |
| Proxy trả 504 | Proxy upstream timeout | Upstream/connect/relay deadline |
| Proxy trả 200, sau đó `SSLHandshakeException` | TLS client↔HTTPS origin | Certificate SAN/chain, TLS versions, truststore, inspection |
| TLS thành công nhưng HTTPS GET trả 404 | HTTP application ở origin | URI/route/authorization/caching |
| 200 CONNECT nhưng body của request thật không đến | Tunnel/flow control/timeout | Hai chiều relay, half-close, backpressure, socket lifetimes |
| `HttpClient.send` timeout dù proxy đã kết nối | Nhiều bước có thể | Phân biệt connect/TLS/request/response phase qua trace |
| Chỉ lỗi trên mạng công ty | Proxy/PAC/auth/SSL inspection | So sánh route, cert, ALPN và policy |
| Proxy thấy target đúng nhưng client nhận certificate domain khác | TLS identity / route | Không bypass verification, sửa route/trust hợp pháp |

**Không** gán mọi lỗi tới “HTTP CONNECT fail”. Ví dụ `SSLHandshakeException` sau CONNECT 200 là lỗi ở **bước TLS**, không phải proxy đã từ chối CONNECT. Ngược lại, proxy 407 xảy ra **trước** handshake end-to-end origin.

### 9.1. 407 khác 401

- `407 Proxy Authentication Required` là **proxy** yêu cầu xác thực (thường trước tunnel).
- `401 Unauthorized` của HTTPS origin là **origin application** yêu cầu xác thực đối với resource (sau tunnel/TLS).
- `Proxy-Authenticate` và `Proxy-Authorization` thuộc proxy-auth trao đổi; `WWW-Authenticate` và `Authorization` thường thuộc origin-auth trao đổi.
- Không đưa credentials của proxy vào `Authorization` của origin hoặc ngược lại.
- Không log raw `Proxy-Authorization` hoặc token vì có thể lộ bí mật qua log/telemetry.

### 9.2. TLS truststore và interception

Nếu hệ thống dùng TLS interception có chủ đích, client có thể thấy certificate do corporate CA cấp cho đích. Điều này chỉ hợp lệ khi doanh nghiệp có chính sách và certificate trust phù hợp. **Không** sửa Java bằng trust-all manager hoặc bỏ hostname verification; đó là cách che giấu sự cố bảo mật, có thể cho phép MITM độc hại.

Đối với local test, dùng `SSLContext` với truststore test riêng. Đối với production, ưu tiên truststore/PKI được tổ chức phê duyệt; nếu phải cài CA proxy, phải hiểu **ai có thể giải mã traffic** và dữ liệu nào nhạy cảm.

### 9.3. Timeouts và retries phải chia theo phase

- **Proxy TCP connect timeout**: thời gian tới proxy host:port; không đợi vô hạn.
- **CONNECT response timeout**: proxy có thể đang resolve hoặc thiết lập origin hop; cần deadline request tổng.
- **TLS handshake timeout**: proxy tunnel đã tạo nhưng origin handshake có thể chậm hoặc bị filter; xác định nguyên nhân đúng.
- **Origin response deadline**: application xử lý request có thể chậm; status 200 CONNECT không phải bằng chứng origin GET xong.
- **Idle/read timeout**: một tunnel sống lâu nhưng không có byte; quản lý theo policy.
- **Cancellation**: đóng resources/cancel future và chấp nhận proxy/origin có thể còn nhận một phần dữ liệu.

**Đừng retry POST thanh toán chỉ vì CONNECT/TLS bị timeout hoặc socket bị reset** nếu không biết request có tới origin chưa. Tùy điểm lỗi, request có thể chưa gửi hoặc đã được origin thực thi rồi response bị mất. Dùng idempotency keys/operation IDs và policy nghiệp vụ thay vì retry mù.

## 10. Proxy thấy được gì trong tunnel?

| Dữ liệu | HTTP proxy forwarding thông thường có thể biết? | Ghi chú |
| --- | --- | --- |
| Proxy client IP và proxy TCP port | Có | Nó trực tiếp nhận kết nối từ client |
| CONNECT target `hostname:port` | Có | Gửi trước TLS origin, để proxy chọn nơi kết nối |
| Origin IP mà proxy kết nối | Có | Proxy mở upstream TCP connection |
| Thời gian, số byte, kết nối đóng/reset | Có | Traffic metadata |
| TLS ClientHello metadata / SNI | Nhiều trường hợp có thể quan sát | ECH có thể thay đổi mức lộ; không giả định TLS handshake hoàn toàn ẩn |
| URL path `/private/orders` của HTTPS request | Thông thường **không** | Nằm trong TLS HTTP message; ngoại lệ TLS interception có chủ đích |
| HTTP `Authorization` header gửi origin | Thông thường **không** | Được gửi trong TLS origin |
| Request body / response JSON của HTTPS | Thông thường **không** | Có thể đọc nếu proxy chặn/terminate TLS |
| Proxy credentials trong `Proxy-Authorization` | Có | Gửi tới proxy trước tunnel; có rủi ro nếu hop cleartext |
| TLS certificate chain và hostname identity | Client kiểm tra; proxy có thể quan sát metadata một phần | Certificate/handshake visibility khác TLS versions/cấu hình |

**Không gọi CONNECT là VPN hoặc ẩn danh tuyệt đối.** Tunnel cho phép vận chuyển byte xuyên proxy, không tự che origin hostname/port, client identity hay traffic metadata. Bảo vệ content phụ thuộc **TLS end-to-end và certificate validation**.

## 11. CONNECT đúng port: an toàn cho ai?

Proxy cho phép client tùy ý gửi `CONNECT host:anyPort` có thể bị lạm dụng để tiếp cận dịch vụ không phải web, quét hệ thống nội bộ hoặc chuyển tiếp spam. RFC 9110 cảnh báo rõ việc CONNECT tới **SMTP port 25** vì có thể bị dùng làm relay spam.

**Proxy sản xuất** nên:

1. Hạn chế **đích và port** theo allowlist/policy (ví dụ chỉ 443 khi phù hợp; không mặc định cho mọi port).
2. Xác thực/ủy quyền ai được tạo tunnel; chính sách theo user/group/tenant.
3. Kiểm tra DNS answers/route sau resolve, chống **DNS rebinding/SSRF** và kết nối tới private/loopback/link-local/metadata IP nếu không được phép.
4. Có thể cấm IP literals hoặc yêu cầu allowlist đặc biệt; xử lý IPv4, IPv6, IDN/punycode đồng nhất.
5. Không cho người dùng vượt policy bằng host alias, hostname thay đổi, alternate numeric IP representations hoặc redirect/chained proxy.
6. Giới hạn concurrent connections, bytes, tốc độ tạo tunnel, idle timeout, max lifetime.
7. Log tối thiểu **principal, target policy decision, status/latency**; tránh ghi passwords hoặc payload.
8. Bảo vệ proxy listener (network ACL/firewall), không chạy open proxy cho Internet.
9. Áp dụng TLS client→proxy nếu gửi credentials hoặc metadata nhạy cảm qua mạng không tin cậy và stack hỗ trợ.
10. Đặt rõ trách nhiệm **đóng cả hai chiều** khi một đầu disconnect; tránh leak sockets/file descriptors.
11. Không tự coi “tunnel” là protocol security: vẫn cần endpoint TLS validation, policy application và lưu vết phù hợp.

**Rủi ro SSRF:** nếu ứng dụng cho người dùng cung cấp URI/proxy target tùy ý, application có thể trở thành cầu nối tới dịch vụ nội bộ qua proxy. Việc chỉ kiểm tra chuỗi `host.endsWith(".trusted.com")` là không đủ nếu không chuẩn hóa, resolve, kiểm tra IP và chống vòng đổi tên. Dùng policy được duyệt thay vì tự triển khai parser network bảo mật trong bài lab.

## 12. HTTP/2 CONNECT có phải hệt HTTP/1.1 CONNECT?

**Semantics của CONNECT** nằm ở HTTP chung, nhưng cách biểu diễn khác theo version:

- **HTTP/1.1:** request line `CONNECT host:port HTTP/1.1`, proxy 2xx, sau header terminator toàn bộ **TCP connection đó** chuyển thành byte tunnel.
- **HTTP/2:** CONNECT được biểu diễn bằng một request stream dùng pseudo-headers như `:method = CONNECT` và `:authority = host:port`; sau 2xx, **DATA frames của stream đó** mang byte tunnel. Các HTTP/2 streams khác có thể vẫn hoạt động trên cùng một underlying connection.
- **Extended CONNECT** (ví dụ dùng cho WebSocket trên HTTP/2) có semantics bổ sung, không nên đồng nhất với CONNECT TCP tunnel thông thường.
- **HTTP/3:** có mapping CONNECT tương ứng với QUIC streams/các extension, nhưng không phải `CONNECT host:port HTTP/1.1` in plaintext trên một UDP datagram.

Java 17 `HttpClient` hỗ trợ HTTP/1.1 và HTTP/2 cho **application HTTP** theo API; điều đó **không** tự nói rằng proxy control CONNECT hop sẽ luôn là HTTP/2. Hai bên có thể chọn HTTP/1.1 cho proxy tunnel và HTTP/2 cho HTTPS origin trong TLS.

Đối với bài lab, cả hai ví dụ cố ý dùng **HTTP/1.1 CONNECT** để có thể quan sát byte text rõ ràng; ví dụ TLS chọn `HttpClient.Version.HTTP_1_1` cho HTTPS inner response. Trong production, phải xem capability của proxy, JDK, origin và cách các hops thương lượng.

## 13. Thiết lập/quan sát proxy trong Java

### 13.1. Có proxy ở đâu?

Có hai cách phổ biến:

- **Explicit proxy:** tạo `HttpClient.Builder.proxy(ProxySelector.of(proxyAddress))` cho client cụ thể.
- **Default proxy selection:** để `HttpClient` dùng selector mặc định của JDK/OS theo system properties và cấu hình môi trường. Theo tài liệu Java 17 có các properties `http.proxyHost`, `http.proxyPort`, `https.proxyHost`, `https.proxyPort`, `http.nonProxyHosts` và `java.net.useSystemProxies` (tùy runtime/handler).

**Chú ý:** tên `https.proxyHost` trong system properties **không** tự có nghĩa proxy endpoint là HTTPS/TLS. Nó thường là cấu hình proxy dùng để truy cập **HTTPS URL**; cần phân biệt với một HTTP proxy endpoint chạy TLS riêng. Cũng có `http.nonProxyHosts` mặc định có localhost patterns trong một số handlers; demo dùng **explicit `ProxySelector.of`** nên đã xác minh request CONNECT tới proxy local thay vì vô tình bypass.

Đừng thay system properties của toàn bộ JVM chỉ để áp proxy cho một client khi có thể cấu hình explicit builder. Nếu đã tạo `HttpClient`, thay `ProxySelector.getDefault()` có thể không ảnh hưởng instance cũ.

### 13.2. Basic authentication bị disable theo mặc định cho tunnel

Oracle Java 17 Networking System Properties ghi nhận `jdk.http.auth.tunneling.disabledSchemes` mặc định **`Basic`**. Điều này được thiết kế để giảm nguy cơ credential exposure. Nếu proxy chỉ hỗ trợ Basic, một Java HttpClient có `Authenticator` vẫn có thể gặp 407 vì scheme bị chặn.

**Định hướng xử lý:** hỏi người quản lý proxy về scheme/endpoint chính thức, dùng protected proxy transport nếu có, cấu hình auth hợp lệ theo policy tổ chức và kiểm thử ở staging. Không xem việc hạ cấu hình security thành giải pháp đầu tiên.

### 13.3. Đọc kết quả origin chứ không nhầm CONNECT result

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

System.out.println(response.statusCode()); // Origin HTTP status
System.out.println(response.version());    // HTTP version actual của response
System.out.println(response.uri());        // URI origin cuối (có thể redirect)
~~~

Đây là **mảnh code** với `client`/`request` đã có. `HttpResponse.version()` biểu thị HTTP version thực nhận cho response của application, không phải “protocol của proxy” một cách chắc chắn. Nếu muốn chẩn đoán CONNECT 407/200 hay ALPN, dùng logging/debugging an toàn ở network/proxy stack mà bạn sở hữu, không giả định public `HttpResponse` có sẵn object riêng cho CONNECT handshake.

### 13.4. Không dùng raw proxy password trong source

Nếu phải triển khai proxy credential support:

- Tách credential vào secret manager hoặc cơ chế xác thực môi trường; không commit vào source.
- Không in `Proxy-Authorization`, password chars, secret token ra log.
- Giới hạn `Authenticator` trả credential theo đúng proxy/port/realm; không cấp bừa cho mọi host.
- Kiểm tra scheme được JDK hỗ trợ và không bị `disabledSchemes` vô hiệu.
- Dùng encrypted proxy hop khi thích hợp và được hỗ trợ; Basic over cleartext có nguy cơ.
- Khi gặp 407, phân biệt proxy challenge với origin 401; đừng đổi Authorization header của origin để “sửa proxy”.

## 14. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách hiểu/sửa |
| --- | --- | --- |
| Gửi `GET https://origin/path` qua proxy rồi cho rằng TLS tự xuất hiện | Sai semantics nếu proxy/client không tạo tunnel | HTTPS qua HTTP proxy thường cần CONNECT và TLS sau 2xx |
| Dùng `CONNECT https://origin/path` | Sai request-target | Dùng `CONNECT origin:443` authority-form |
| Bỏ port khỏi `CONNECT origin` | Vi phạm cú pháp request-target | Port bắt buộc, kể cả port mặc định |
| Nghĩ `200 Connection Established` là response GET | Nhầm proxy control với origin HTTP | TLS rồi origin response mới là kết quả GET |
| Gửi `GET /path` plaintext ngay sau CONNECT 2xx tới origin TLS | Origin mong TLS handshake, gây lỗi protocol | Client thực hiện TLS trước |
| Tưởng CONNECT 2xx đồng nghĩa TLS valid | Có thể SSLHandshakeException sau đó | Check hostname/certificate chain |
| Coi HTTP/1.1 proxy hop cản origin HTTP/2 | Hai giao thức ở hai lớp khác nhau | TLS ALPN origin có thể chọn h2 |
| Coi proxy tunnel là VPN ẩn danh | Lộ CONNECT target/IP/metadata | TLS bảo vệ content, nhưng metadata vẫn hiện |
| Tin proxy không bao giờ thấy HTTP body | TLS interception là ngoại lệ quan trọng | Xác định trust model |
| Gửi proxy password bằng Basic qua mạng plaintext | Credential bị lộ | Proxy transport/auth security |
| Cho phép arbitrary host:port | Open proxy/SSRF/spam relay | Allowlist, ACL, DNS/IP checks |
| Không dọn hai đầu connection khi peer disconnect | File descriptor leak | Half-close/EOF/close hai phía |
| Dùng `readAllBytes()` trên stream tunnel bất tận | Có thể treo/OOM | Forwarding/backpressure và timeout |
| Tự đọc CONNECT header bằng BufferedReader rồi chuyển stream với data prefetch | Có thể nuốt byte đầu TLS handshake | HTTP parser xử lý boundary chính xác; demo đọc byte-by-byte |
| Tự viết proxy từ demo rồi public internet | Thiếu auth, parsing, rate limit, logging security | Dùng proxy được duy trì/bảo trì |
| Thấy `407` lại đổi `Authorization` cho origin | Nhầm identity domains | Proxy-Authorization/Authenticator |
| Tắt TLS certificate validation khi handshake fail | Mở cửa MITM | Sửa truststore/SAN/routes đúng chính sách |
| Nghĩ `https.proxyHost` chắc chắn là proxy TLS | Nhầm đích HTTPS với proxy scheme | Kiểm tra capability proxy thực tế |
| Gửi request POST lại sau timeout mà không kiểm tra idempotency | Có thể gây giao dịch trùng | Idempotency key / operation status |
| Nghĩ proxy nhận được hết URI path HTTPS | Path nằm trong TLS end-to-end | Proxy bình thường thấy CONNECT authority, không phải path |
| Coi `ProxySelector.of` là SOCKS handshake | HTTP client/proxy behavior khác SOCKS | Dùng API/provider phù hợp |
| Giả định CONNECT proxy chỉ trả 200 mới thành công | RFC định nghĩa mọi 2xx | Xử lý theo HTTP CONNECT semantics |
| Gửi `Content-Length` trong 2xx CONNECT reply | Vi phạm RFC 9110/9112 | Proxy không được gửi nó |
| Coi Content-Length của CONNECT 2xx là số byte TLS | Tunnel không đóng khung theo HTTP body | Bỏ qua trường này trong 2xx |
| Đánh đồng HTTPS proxy với HTTPS origin | Hai đoạn TLS khác nhau | Phân biệt client–proxy TLS và client–origin TLS |

## 15. Ma trận kiểm thử CONNECT/HTTPS proxy

| Test | Chuẩn bị | Kết quả nên kiểm tra |
| --- | --- | --- |
| CONNECT tới local allowed target | Proxy có allowlist exact origin/port | Response 2xx rồi relay byte |
| CONNECT target sai | Proxy chỉ cho host:port đã biết | 403/no upstream connection |
| Cú pháp CONNECT thiếu port | Raw client gửi invalid target | 400/deny theo policy |
| Proxy cần auth | Trả 407 + Proxy-Authenticate | Client không mở tunnel nếu chưa auth |
| Auth scheme disabled | JDK mặc định Basic tunneling disabled | Không gửi Basic ngoài policy; báo lỗi rõ |
| Proxy không resolve được origin | DNS fail ở upstream | 502/504 hoặc lỗi proxy tương ứng |
| Proxy mở TCP tới origin nhưng origin TLS chưa sẵn sàng | CONNECT 2xx, TLS fails | Phân biệt CONNECT success và handshake failure |
| HTTPS origin với cert test được trust | Custom client SSLContext truststore | TLS pass, origin HTTP response |
| HTTPS origin cert untrusted | Dùng default truststore | Handshake fail, **không** bypass TLS |
| Certificate SAN sai hostname | URI `https://localhost` nhưng cert sai | Hostname validation fail |
| Proxy tunnel end-to-end | Log chỉ CONNECT line + timing | Không parse plaintext origin GET |
| Inner HTTP/1.1 | `client.version(HTTP_1_1)` | `response.version()==HTTP_1_1` |
| Inner HTTP/2 | TLS origin/ALPN hỗ trợ h2 | `response.version()==HTTP_2` nếu thực sự negotiated |
| Proxy có TLS interception được tổ chức duyệt | Corporate CA được trust | Audit đúng chủ thể đang giải mã |
| CONNECT to port 25 | Port allowlist chỉ 443 | Denied, chống abuse SMTP relay |
| IPv6 target | `CONNECT [2001:db8::10]:443` | Authority bracketed/port |
| Redirect HTTPS giữa origins | Policy followRedirects được bật | CONNECT/tunnel tới origin mới nếu cần, bảo toàn security |
| Half-close/EOF | Client shutdownOutput trong echo demo | Proxy chuyển dữ liệu trả về rồi đóng |
| Timeout/connection cancellation | Origin chậm/blackhole trong staging | Không leak sockets, phân biệt phase lỗi |
| Nhiều concurrent tunnels | Proxy production có resource budgets | Không starvation/OOM/file-descriptor exhaustion |

**Không** chạy các test cố ý thất bại tới proxy của tổ chức hoặc host bên ngoài nếu chưa được phép. Hãy dựng local/staging proxy và server do bạn sở hữu, với giới hạn port rõ ràng.

## 16. Bài tập có lời giải

### Bài 1 — CONNECT gửi tới đâu?

Client Java muốn tải `https://api.example.com/v1/data` qua HTTP proxy `proxy.local:3128`. Đầu tiên nó mở TCP tới ai và gửi request gì?

**Đáp án:** Client mở TCP tới **`proxy.local:3128`** và gửi **`CONNECT api.example.com:443 HTTP/1.1`** tới proxy (kèm headers phù hợp như Host). Nó chưa gửi GET path ở giai đoạn này.

### Bài 2 — Vì sao không có path trong CONNECT?

**Đáp án:** CONNECT authority-form dùng **host:port** để yêu cầu một TCP tunnel. Path/query của HTTPS resource thuộc HTTP request **sau TLS handshake** tới origin, không phải target của CONNECT.

### Bài 3 — 200 nào của ai?

Proxy trả `HTTP/1.1 200 Connection Established`, sau TLS origin trả `HTTP/1.1 404 Not Found`. `HttpResponse.statusCode()` của Java request GET thường là gì?

**Đáp án:** `404`, vì đó là **HTTP response của origin** đối với GET; CONNECT 200 chỉ là control response cho tunnel.

### Bài 4 — 407 và 401 khác nhau thế nào?

**Đáp án:** `407` yêu cầu **proxy authentication** và xảy ra trước hoặc trong thiết lập tunnel. `401` của HTTPS origin yêu cầu **origin/application authentication** sau TLS. Headers tương ứng là `Proxy-Authenticate/Proxy-Authorization` và `WWW-Authenticate/Authorization`.

### Bài 5 — CONNECT 200 đã an toàn chưa?

Proxy báo CONNECT 200 nhưng Java ném `SSLHandshakeException` khi gọi HTTPS URL. Tunnel có thể đã tạo chưa? Có nên tắt certificate check?

**Đáp án:** Tunnel **có thể đã tạo thành công**, nhưng TLS identity/trust failed. **Không** tắt certificate/hostname verification; kiểm tra truststore, SAN, TLS/certificate chain và route phù hợp.

### Bài 6 — HTTP/2 bên trong HTTP/1.1 CONNECT

Proxy tạo CONNECT bằng HTTP/1.1. Liệu HTTPS response bên trong có thể là HTTP/2 không?

**Đáp án:** **Có**, nếu client/origin thương lượng ALPN `h2` qua TLS trong tunnel và hỗ trợ. Phiên bản proxy control hop không bắt buộc trùng inner HTTPS version.

### Bài 7 — Proxy có đọc được `/private` không?

Với proxy chuyển byte mù và TLS end-to-end tới origin, proxy có đọc được path `/private`, headers và body của GET không?

**Đáp án:** Thông thường **không**; chúng nằm trong TLS encryption. Proxy vẫn biết CONNECT host:port, upstream IP và traffic metadata, thường có thể quan sát một phần TLS handshake (như SNI nếu không ECH). TLS interception với CA được tin cậy là trường hợp khác.

### Bài 8 — Mật khẩu proxy và Basic

Một `Authenticator` Java 17 được cài đặt nhưng proxy chỉ trả `407 Basic` và client không thể tạo tunnel. Giải thích một nguyên nhân cấu hình có thể?

**Đáp án:** `jdk.http.auth.tunneling.disabledSchemes` mặc định chứa `Basic`; Java có thể không dùng Basic cho HTTPS tunneling dù có `Authenticator`. Làm việc với proxy/security team để chọn auth scheme/hop được bảo vệ thay vì vội bỏ chặn Basic.

### Bài 9 — Rủi ro port 25

Tại sao proxy thường từ chối `CONNECT mail.example:25` dù vẫn cho `CONNECT api.example:443`?

**Đáp án:** Arbitrary TCP tunnels có thể bị lạm dụng làm relay tới SMTP hoặc dịch vụ nội bộ. RFC 9110 khuyến nghị giới hạn các port/destinations an toàn, chống abuse/open proxy.

### Bài 10 — Raw PING/PONG có chứng minh HTTPS không?

**Đáp án:** Không. Nó chứng minh **byte forwarding** qua tunnel. HTTPS còn yêu cầu **TLS handshake, certificate/hostname verification** và HTTP request/response bên trong TLS như demo thứ hai.

### Bài 11 — Proxy DNS và client DNS

Ai thường resolve origin hostname khi Java gửi CONNECT?

**Đáp án:** **Proxy thường** resolve/connect origin vì nó mở upstream TCP. Nhưng DNS behavior cụ thể có thể khác theo route/chain/implementation, nên không đưa ra một mệnh đề tuyệt đối về mọi client.

### Bài 12 — Sau tunnel gửi GET bằng cách nào?

Sau khi CONNECT 200, client gửi literal text `GET /secret HTTP/1.1` không mã hóa lên TCP tunnel dẫn đến HTTPS server. Kết quả?

**Đáp án:** Có thể bị TLS error/connection reset vì HTTPS origin mong **TLS ClientHello trước**, không phải plaintext HTTP request. Thư viện HTTPS client phải tạo TLS session trong tunnel rồi mới gửi HTTP request encrypted.

### Bài 13 — Retry sau timeout

Client gửi POST qua proxy, rồi mất kết nối trước khi đọc origin response. Có an toàn để gửi lại ngay?

**Đáp án:** Không thể kết luận origin chưa xử lý. Cần idempotency key, operation id hoặc kiểm tra outcome; nếu retry mù có thể tạo giao dịch trùng.

### Bài 14 — Chính sách TLS interception

Một proxy công ty thay origin certificate bằng certificate cấp bởi corporate CA được trust, đồng thời đọc nội dung HTTPS. Còn là “blind tunnel” đúng nghĩa không?

**Đáp án:** Không ở tầng end-to-end: proxy đang trở thành TLS intermediary có thể giải mã, kiểm tra và mã hóa lại. Cần audit quyền, compliance, CA trust và minh bạch dữ liệu. Đừng giả định mọi proxy 200 CONNECT đều mù trước content.

### Bài 15 — Chọn API

Ứng dụng Java 17 muốn gọi REST API HTTPS qua HTTP proxy. Có nên tự viết Socket, gửi CONNECT, parse TLS rồi gửi GET không?

**Đáp án:** **Không** cho trường hợp thông thường. Dùng `HttpClient.Builder.proxy(ProxySelector.of(...))` và Java TLS stack; chỉ dùng raw socket trong lab hoặc một protocol implementation được bảo trì chuyên nghiệp.

## 17. Checklist triển khai

- [ ] URL đích là `https://...` khi cần bảo mật HTTPS.
- [ ] HTTP proxy đúng host/port được cấu hình ở `HttpClient.Builder.proxy(...)` hoặc proxy selector tin cậy.
- [ ] Phân biệt TCP connect proxy, CONNECT proxy control, TLS origin và HTTP origin response.
- [ ] CONNECT dùng authority-form host:port; port bắt buộc.
- [ ] Không nhầm proxy 200 CONNECT với origin GET/POST 200.
- [ ] Sau CONNECT 2xx, phải thực hiện TLS handshake và xác minh hostname/certificate.
- [ ] Không tắt TLS validation để vượt lỗi proxy.
- [ ] Proxy ACL hạn chế target/destination port; không tạo open proxy/SSRF gateway.
- [ ] Có proxy authentication phù hợp; `407` khác origin `401`.
- [ ] Biết `jdk.http.auth.tunneling.disabledSchemes` có thể disable Basic mặc định.
- [ ] Không lộ proxy credentials trên cleartext hop hoặc log.
- [ ] Chỉ dùng credential từ secret manager/secure configuration.
- [ ] Phân biệt `http.proxyHost`/`https.proxyHost` với mô hình proxy endpoint TLS.
- [ ] Quan sát actual response version và status thay vì suy từ proxy CONNECT.
- [ ] Có timeout/deadline cho connect, CONNECT, TLS, request và idle tunnel theo policy.
- [ ] Có graceful close/half-close/backpressure, không leak sockets.
- [ ] Không tự viết public proxy theo code lab.
- [ ] Không retry POST có side effect khi chưa biết request đã xử lý hay chưa.
- [ ] Kiểm thử certificate SAN/truststore, proxy bypass, direct/proxy route và redirect.
- [ ] Không cho phép CONNECT tới port/dịch vụ bị cấm (ví dụ SMTP 25).
- [ ] Có monitoring không log token/Authorization hoặc payload bí mật.
- [ ] Đã test trên đúng JDK/runtime và proxy policy của môi trường triển khai.

## 18. Tài liệu chính thức

- [RFC 9110 `9.3.6 — CONNECT](https://www.rfc-editor.org/rfc/rfc9110#section-9.3.6): authority-form, port bắt buộc, 2xx thành tunnel, non-2xx chưa tạo tunnel, proxy restrictions và security.
- [RFC 9112 `3.2.3 — authority-form](https://www.rfc-editor.org/rfc/rfc9112#section-3.2.3): biểu diễn CONNECT request-target của HTTP/1.1.
- [RFC 9112 `6.3 — Message body length](https://www.rfc-editor.org/rfc/rfc9112#section-6.3): 2xx CONNECT chuyển sang tunnel ngay sau header, bỏ Content-Length/Transfer-Encoding trong trường hợp đó.
- [RFC 8441 — Bootstrapping WebSockets with HTTP/2](https://www.rfc-editor.org/rfc/rfc8441): extended CONNECT là cơ chế đặc biệt khác CONNECT TCP tunnel thường.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 CONNECT trên stream/pseudo-headers và multiplexing.
- [RFC 7301 — TLS ALPN](https://www.rfc-editor.org/rfc/rfc7301): chọn application protocol trong TLS handshake.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): proxy, SSLContext, API `send`, `sendAsync` và response.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `proxy(ProxySelector)`, `authenticator`, `sslContext`, timeout và version.
- [Java SE 17 — ProxySelector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html): chọn proxy/direct theo URI và `ProxySelector.of`.
- [Java SE 17 — Authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Authenticator.html): proxy authentication và `RequestorType.PROXY`.
- [Java SE 17 — Java Networking / System Properties](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): `http.proxyHost`, `https.proxyHost`, `http.nonProxyHosts` và `jdk.http.auth.tunneling.disabledSchemes` mặc định Basic.
- [Java SE 17 — HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HTTPS origin nhúng dùng trong lab.
- [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): cấu hình TLS, KeyManagers và TrustManagers.
- [Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): key store/trust store riêng cho test TLS.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): response status/body/version từ HTTP exchange sau tunnel.

**Kết luận:** Khi đi tới một **HTTPS origin qua HTTP proxy**, `CONNECT origin:443` tạo **đường hầm TCP hai chiều**; response 2xx của proxy **chỉ báo tunnel thành công**. Client vẫn phải hoàn tất **TLS handshake và certificate/hostname validation**, rồi mới trao đổi **HTTP request–response thực tế bên trong TLS**. Ứng dụng Java 17 nên dùng `HttpClient.Builder.proxy(ProxySelector.of(...))` để library tự xử lý CONNECT và TLS, nhưng phải quản lý đúng **proxy authentication, destination ACL, timeout, truststore, observability và retry semantics**.
