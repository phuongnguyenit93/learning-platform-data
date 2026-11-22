# Đàm phán HTTP/2, nâng cấp giao thức và khả năng quay về HTTP/1.1 trong Java HttpClient

## 1. Vấn đề: yêu cầu HTTP/2 không đồng nghĩa chắc chắn dùng HTTP/2

Khi dùng `java.net.http.HttpClient` (Java 17+), ta có thể viết:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

Nhưng **`HTTP_2` ở đây là phiên bản ưu tiên/yêu cầu nếu có thể**, không phải bằng chứng mọi request sẽ đi bằng HTTP/2. Nếu server, proxy, TLS ALPN hoặc điều kiện triển khai không hỗ trợ HTTP/2, client **có thể dùng HTTP/1.1**. Với `HttpClient.Builder` của Java 17, khi không gọi `version(...)`, client **mặc định ưu tiên HTTP/2**.

Câu hỏi cần trả lời sau một request không phải "tôi đã cấu hình version nào?", mà là **"response thực tế đi qua phiên bản HTTP nào?"**. API để xác định là:

```java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.version());
```

Đây là *mảnh code* cần có biến `client`, `request` cùng import `HttpResponse`. `response.version()` trả `HTTP_2` hoặc `HTTP_1_1` theo phiên bản **thực tế dùng cho response**; `client.version()` chỉ trả **phiên bản ưu tiên ở client**. Đừng nhầm hai giá trị.

Bài học này phân biệt ba trường hợp quan trọng:

1. `https://` → lựa chọn HTTP/2 bằng **TLS Application-Layer Protocol Negotiation (ALPN)**, không dùng HTTP/1.1 `Upgrade`/`101` để bật HTTP/2.
2. `http://` (không TLS) → Java 17 `HttpClient` có thể thử **HTTP/1.1 `Upgrade: h2c`** trong một số kết nối; nếu server không nâng cấp, response tiếp tục ở HTTP/1.1. **Cơ chế h2c Upgrade là đường lịch sử, đã bị RFC 9113 deprecate**, không phải khuyến nghị mặc định cho hệ thống mới.
3. Client đặt `HTTP_2` nhưng phía đối tác chỉ hỗ trợ HTTP/1.1 → client có thể **fallback** về HTTP/1.1; cần đo kết quả thực, không tự ép server thành HTTP/2.

## 2. HTTP/1.1 và HTTP/2 khác nhau ở tầng biểu diễn trên đường truyền

Hai phiên bản thường có cùng **HTTP semantics**: method `GET/POST`, URI, status code, `Content-Type`, caching, authentication và nhiều header field vẫn có ý nghĩa quen thuộc. Khác biệt lớn nằm ở cách đóng khung và multiplexing.

| Khía cạnh | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Biểu diễn trên kết nối | Start-line/header section dạng text, byte framing theo HTTP/1.1 | Frame nhị phân với các loại như `HEADERS`, `DATA`, `SETTINGS` |
| Đồng thời nhiều trao đổi | Thường cần nhiều connection để giảm head-of-line blocking ứng dụng; pipelining ít dùng | Nhiều **stream** đồng thời trên một HTTP/2 connection |
| Nén header | Không có HPACK HTTP/2 | HPACK cho trường header |
| Phân biệt thông điệp | HTTP/1.1 framing, `Content-Length` hoặc transfer coding theo RFC | Stream ID, flags/frame và end-of-stream; không dùng HTTP/1.1 chunk syntax |
| Điều tiết dữ liệu | Chủ yếu dựa vào transport và quy tắc message | HTTP/2 có **flow control** theo stream và connection |
| Request/response semantics | Method/status/header fields | Phần lớn được giữ, dù cú pháp wire khác |
| Bảo mật | Có thể chạy trên TCP cleartext hoặc TLS | Có thể HTTP/2 over TLS (`h2`) hoặc HTTP/2 cleartext với prior knowledge (`h2c`, không TLS) |

**HTTP/2 không đồng nghĩa tất cả request đều nhanh hơn.** Multiplexing giảm nhu cầu nhiều TCP connection, nhưng còn chịu network latency, server load, TLS, flow control, tổ chức stream, proxy và TCP-level head-of-line blocking khi mất packet. HTTP/2 còn có giới hạn tài nguyên như số stream đồng thời; không được coi nó là nút bật throughput tự động.

Với Java `HttpClient`, việc đóng khung HTTP/1.1 hay HTTP/2 do thư viện đảm nhận. Không viết application code cố chèn `Transfer-Encoding: chunked` vào HTTP/2; transfer coding đó thuộc HTTP/1.1, HTTP/2 có cách biểu diễn DATA frames riêng.

## 3. `https://`: đàm phán HTTP/2 qua TLS ALPN, không phải 101

Với URL HTTPS, client tạo kết nối TCP/TLS. Trong TLS handshake, client và server đàm phán **giao thức ứng dụng** qua ALPN:

```text
Java HttpClient                         HTTPS Server
       |                                     |
       +--------- TCP connect ------------->|
       |                                     |
       | TLS ClientHello                     |
       | ALPN: h2, http/1.1  --------------->|
       |                                     |
       | TLS handshake, certificate           |
       |<--------- ALPN chọn "h2" ----------|
       |                                     |
       |   HTTP/2 connection preface         |
       |   SETTINGS + HEADERS/DATA frames    |
       +------------------------------------>|
       |<--------- HTTP/2 frames ------------|
       |
       +--> response.version() == HTTP_2
```

Nếu server chỉ chấp nhận HTTP/1.1 và hai phía vẫn thống nhất được giao thức phù hợp:

```text
TLS ALPN chọn "http/1.1"
      |
      v
TLS handshake thành công
      |
      v
Ứng dụng trao đổi HTTP/1.1 trên kết nối TLS
      |
      v
response.version() == HTTP_1_1
```

**Lưu ý quan trọng:**

- Chuỗi định danh ALPN của HTTP/2 over TLS là **`h2`**, còn HTTP/1.1 là **`http/1.1`**.
- **`h2c` không phải ALPN cho HTTP/2 over TLS.** RFC 9113 yêu cầu HTTP/2 trên HTTPS thương lượng qua ALPN.
- Nếu ALPN chọn `h2`, hai bên dùng **HTTP/2 connection preface và frames** sau TLS handshake. **Không có bước gửi HTTP/1.1 `Upgrade: h2c` rồi chờ `101 Switching Protocols`** trong con đường HTTPS này.
- TLS vẫn phải kiểm tra certificate chain và **hostname**, không tự giảm bảo mật khi protocol version là HTTP/1.1. Quay về HTTP/1.1 **bên trong HTTPS** không biến `https://` thành `http://`.
- Phiên bản HTTP do ALPN lựa chọn khác với **TLS version**: HTTP/2 có thể chạy trên TLS 1.2 hoặc TLS 1.3 theo các ràng buộc chuẩn, không phải cứ `HTTP_2` là `TLSv1.3`.
- Nếu server không cung cấp certificate hợp lệ, handshake fail, lỗi TLS/certificate **không được xử lý bằng cách tắt verification** để ép một kết nối "fallback".

ALPN và SNI cũng khác nhau: **SNI** gửi hostname logic để server chọn virtual host/certificate; **ALPN** thương lượng giao thức ứng dụng; **certificate validation** xác thực danh tính server. Không dùng SNI như bằng chứng đã chọn HTTP/2 hoặc đã kiểm tra hostname.

## 4. Khi không có hỗ trợ HTTP/2 qua TLS

Có thể gặp các tình huống:

| Server / đường truyền HTTPS | Dấu hiệu | Hành vi cần hiểu |
| --- | --- | --- |
| ALPN đàm phán thành công `h2` | Response thực tế `HTTP_2` | Client gửi/nhận HTTP/2 frames |
| ALPN chọn `http/1.1` | Response `HTTP_1_1` | Đây là HTTP/1.1 **vẫn được bảo vệ bằng TLS** |
| Server/thiết bị trung gian không hỗ trợ `h2` | Có thể dùng HTTP/1.1 nếu khả dụng | Phải xác nhận qua response thực tế |
| Không có giao thức chung/TLS không tương thích | Request có thể **thất bại** | Không có bảo đảm lúc nào cũng fallback thành công |
| Chứng chỉ/hostname không đáng tin | TLS handshake lỗi | Không retry bằng cách trust-all hoặc đổi sang `http://` |
| HTTP/2 chỉ hỗ trợ ở CDN, origin dùng HTTP/1.1 | Client thấy version của kết nối **nó đã dùng** | Không suy ra version trên hop từ CDN đến origin |

Đừng hiểu "fallback" là mỗi request HTTP/2 sẽ tự động gửi lại bằng HTTP/1.1 trong mọi tình huống. Nó thường mô tả **lựa chọn protocol version khi thiết lập kết nối hoặc xác nhận server không chấp nhận nâng cấp**, nhưng lỗi mạng giữa một request, timeout giữa body, response lỗi nghiệp vụ hay proxy failure có thể không cho phép gửi lại an toàn. Cơ chế retry của HTTP có quy tắc riêng, đặc biệt với request thay đổi trạng thái.

## 5. `http://`: h2c, HTTP/1.1 Upgrade và lịch sử tiêu chuẩn

Với HTTP cleartext (không TLS), **ALPN không được trao đổi trong TLS handshake** vì không có TLS. Có hai đường lịch sử để bắt đầu HTTP/2 over cleartext TCP:

1. **HTTP/1.1 `Upgrade: h2c`**: client gửi request HTTP/1.1 đề nghị chuyển sang HTTP/2. Một server đồng ý có thể trả `101 Switching Protocols`; sau đó hai phía chuyển sang HTTP/2 connection preface và frame. Đây là cơ chế được mô tả trong RFC 7540 (2015).
2. **HTTP/2 prior knowledge**: client **biết trước** server chấp nhận HTTP/2 cleartext và gửi HTTP/2 connection preface ngay, không bắt đầu bằng request HTTP/1.1 Upgrade. RFC 9113 (2022) mô tả đường này.

**Điểm cập nhật chuẩn rất quan trọng:** RFC 9113 đã **deprecate** cơ chế HTTP/1.1 `Upgrade: h2c` và trường `HTTP2-Settings` liên quan, vì chúng không được triển khai rộng rãi; tài liệu hiện hành mô tả cleartext HTTP/2 chủ yếu bằng **prior knowledge**. Tuy nhiên, Java 17 `HttpClient` trong một trường hợp cụ thể vẫn có thể **phát đề nghị h2c Upgrade** khi ưu tiên HTTP/2 trên `http://`. Bài test ở mục 8 sẽ cho thấy hành vi thực nghiệm của JDK được dùng, không tuyên bố tất cả client/JDK/server hiện tại đều hành xử giống nhau.

### Cách đề nghị HTTP/1.1 Upgrade trông như thế nào?

Một minh họa của yêu cầu cleartext có thể chứa:

```http
GET /version HTTP/1.1
Host: 127.0.0.1:8080
Connection: Upgrade, HTTP2-Settings
Upgrade: h2c
HTTP2-Settings: <giá trị cấu hình được mã hóa hợp lệ>

```

Đây là **minh họa cấu trúc headers**, không phải raw request có thể copy để gửi: `HTTP2-Settings` cần một giá trị đúng định dạng, và HTTP/1.1 phải dùng CRLF ở wire. **`Connection` chỉ định các hop-by-hop field**; intermediaries không được chuyển tiếp chúng không đúng ngữ nghĩa.

Theo cơ chế Upgrade HTTP/1.1 nói chung, server có thể **bỏ qua** đề nghị và trả response HTTP/1.1 bình thường:

```http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Length: 2

OK
```

Khi đó nó vẫn là HTTP/1.1; client không được coi chỉ vì đã gửi `Upgrade: h2c` là server đã bật HTTP/2. Nếu server thực sự chấp nhận cơ chế Upgrade lịch sử, phản hồi `101 Switching Protocols` thể hiện bước chuyển giao, rồi connection sẽ nói giao thức mới. Nhưng **không thiết kế hệ thống HTTP/2 mới bằng cách mặc định phải dùng h2c Upgrade**, bởi cơ chế này đã deprecated trong RFC hiện hành và thường không xuyên qua proxy như mong đợi.

### HTTP/2 prior knowledge không phải "client cứ gửi h2c rồi sẽ được"

Nếu client gửi HTTP/2 preface vào server chỉ hiểu HTTP/1.1, server có thể coi đây là request không hợp lệ và đóng kết nối. Vì vậy **prior knowledge đòi hỏi biết trước capability**, không phải phương án thử mù luôn có fallback. Tùy Java API/version, không thể suy từ `client.version(HTTP_2)` rằng nó tự chuyển mọi `http://` request sang prior-knowledge mode.

**Ranh giới an toàn:** h2c dùng HTTP/2 **không mã hóa**. Nó không cung cấp TLS certificate, xác thực tên máy hay tính bảo mật trên đường truyền. Nếu dữ liệu nhạy cảm, ưu tiên `https://` có TLS xác thực.

## 6. HTTP/1.1 `Upgrade` và `101 Switching Protocols` không đồng nghĩa với HTTP/2

`Upgrade` là cơ chế HTTP/1.1 chung theo RFC 9110, có thể dùng để đề nghị chuyển sang **một giao thức khác trên cùng connection**, ví dụ WebSocket trong những trường hợp phù hợp.

```text
HTTP/1.1 request:
  Connection: Upgrade
  Upgrade: <requested-protocol>

Server có thể:
  - 101 Switching Protocols + Upgrade: ...   -> chấp nhận chuyển
  - response thường (ví dụ 200)              -> bỏ qua đề nghị
  - từ chối/lỗi theo chính sách
```

Cần phân biệt:

- HTTP/2 **qua HTTPS** không được bật bằng `101`; nó được thỏa thuận bằng **TLS ALPN**.
- **h2c Upgrade** là lộ trình HTTP/1.1 **lịch sử** để vào HTTP/2 cleartext, hiện deprecated theo RFC 9113.
- **WebSocket Upgrade** trong HTTP/1.1 có cơ chế `101` riêng. `java.net.http.HttpClient.newWebSocketBuilder()` phục vụ WebSocket; không phải API để ép một HTTP request thông thường lên HTTP/2.
- `101` không phải status code nói rằng "request đã hoàn tất thành công bằng HTTP/2"; nó thông báo thay đổi protocol. Sau chuyển đổi vẫn phải xử lý payload/response theo giao thức mới.

Nếu một proxy trả response `101` cho một giao thức khác, đừng nhầm nó với HTTP/2. Nếu một request HTTPS có response.version()==HTTP_2 nhưng không có 101, **đó là bình thường**.

## 7. API Java 17: client preference, request override và response thực tế

Java `HttpClient` có các chỗ chọn protocol version:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .GET()
        .build();
```

*Mảnh code trong phương thức có `URI uri` và các import.* Ở đây `client.version() == HTTP_2` chỉ mô tả **preference**. `request.version()` là một `Optional<HttpClient.Version>`; nếu không set per-request thì nó **rỗng**, và request kế thừa preference của HttpClient khi gửi.

Nếu chỉ một request muốn dùng HTTP/1.1:

```java
HttpRequest request11 = HttpRequest.newBuilder(uri)
        .version(HttpClient.Version.HTTP_1_1)
        .GET()
        .build();
```

Đây là **request-level override** (preference áp dụng cho request đó), không đổi cấu hình client cho các request khác. Không cần tạo một client mới cho mỗi request chỉ để chuyển version; `HttpClient` được thiết kế để tái sử dụng connection pool.

Sau khi gửi:

```java
HttpResponse<Void> response = client.send(
        request11, HttpResponse.BodyHandlers.discarding());

System.out.println("preferred at client: " + client.version());
System.out.println("actual on response: " + response.version());
```

*Đoạn code không standalone.* Phân biệt ba giá trị:

| Giá trị | Ý nghĩa |
| --- | --- |
| `client.version()` | Phiên bản **client ưu tiên**, mặc định Java 17 là `HTTP_2` |
| `request.version()` | `Optional` chứa override khi request tự đặt; rỗng nếu kế thừa client |
| `response.version()` | Phiên bản HTTP **thực sự dùng** để nhận response |

**Lưu ý Java 17:** `HttpClient` ở JDK 17 **không implements AutoCloseable**, nên không viết `try (HttpClient c = HttpClient.newHttpClient())` cho mã nhắm `--release 17`. Sử dụng một instance có thể tái sử dụng; các JDK mới hơn có thêm API vòng đời client, nhưng bài mẫu giữ tương thích Java 17.

## 8. Ví dụ Java 17 chạy được: ưu tiên HTTP/2, server chỉ có HTTP/1.1

Ví dụ loopback sau không cần Internet, certificate hay server bên ngoài. Ta dùng `com.sun.net.httpserver.HttpServer` làm server HTTP **chỉ xử lý HTTP/1.1**, rồi dùng Java 17 `HttpClient` ưu tiên HTTP/2.

Chương trình còn cho server ghi lại **các header nhận được**: trên JDK 17 đã kiểm thử, client gửi `Upgrade: h2c` và `HTTP2-Settings`. Server **không chấp nhận nâng cấp**, chỉ trả status `200` bằng HTTP/1.1. Client báo phiên bản thực tế là `HTTP_1_1`, không bị lỗi chỉ vì request ưu tiên HTTP/2.

**Tệp `Http2NegotiationDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class Http2NegotiationDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/version", exchange -> {
            try (exchange) {
                String upgrade = exchange.getRequestHeaders()
                        .getFirst("Upgrade");
                boolean hasSettings = exchange.getRequestHeaders()
                        .getFirst("HTTP2-Settings") != null;
                String body = "upgrade=" + (upgrade == null ? "-" : upgrade)
                        + ", settings=" + hasSettings;
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=UTF-8");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/version");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpRequest preferredH2 = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            HttpResponse<String> first = client.send(preferredH2,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("client preference: " + client.version());
            System.out.println("actual response: " + first.version());
            System.out.println("server saw: " + first.body());

            HttpRequest forceHttp11 = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_1_1)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            HttpResponse<Void> second = client.send(forceHttp11,
                    HttpResponse.BodyHandlers.discarding());
            System.out.println("request override: "
                    + forceHttp11.version().orElseThrow());
            System.out.println("override response: " + second.version());
        } finally {
            server.stop(0);
        }
    }
}
```

Chạy bằng JDK 17 có module `jdk.httpserver`:

```bash
javac --release 17 --add-modules jdk.httpserver Http2NegotiationDemo.java
java --add-modules jdk.httpserver Http2NegotiationDemo
```

**Stdout được xác minh trên môi trường Java 17 thử nghiệm:**

```text
client preference: HTTP_2
actual response: HTTP_1_1
server saw: upgrade=h2c, settings=true
request override: HTTP_1_1
override response: HTTP_1_1
```

Phân tích:

1. **`client preference: HTTP_2`** chứng minh client ưu tiên HTTP/2 — **chưa có bảo đảm server hỗ trợ**.
2. **`actual response: HTTP_1_1`** là dữ kiện đúng để biết request nhận response qua HTTP/1.1.
3. **`server saw: upgrade=h2c, settings=true`** cho thấy trong runtime Java 17 đã dùng, request cleartext ban đầu có `Upgrade: h2c` và `HTTP2-Settings`. Server không chấp nhận; không trả `101`; kết quả vẫn là HTTP/1.1. **Không xem đây là lời hứa JDK/HTTP client nào cũng phát h2c Upgrade**.
4. **`request override: HTTP_1_1`** xác nhận request thứ hai yêu cầu HTTP/1.1. **`override response: HTTP_1_1`** xác nhận kết quả thực tế.

**Giới hạn ví dụ:** đây là local HTTP cleartext không chứa dữ liệu nhạy cảm. Nó **không** kiểm thử TLS ALPN, server HTTP/2 thật hoặc giao tiếp qua proxy/CDN. Mục đích chỉ là chứng minh **preference khác negotiated version** và hành vi HTTP/1.1 response khi server không nâng cấp. `HttpServer` ở đây là công cụ dạy học, không phải ví dụ triển khai server HTTP/2 hay h2c prior knowledge.

Nếu chạy bằng phiên bản JDK khác, hoặc sau proxy hay với connection đã được cache/thiết lập theo trạng thái khác, các header đề nghị nâng cấp có thể khác; hãy nhìn `response.version()` trước khi kết luận.

## 9. Ví dụ Java 17 biên dịch được để kiểm tra server HTTPS thực

Với một server HTTPS hợp lệ thực tế, kiểm tra ALPN qua việc gửi request với HTTP/2 preference rồi **đọc phiên bản response**. Không hard-code stdout cho ví dụ này vì còn tùy server, proxy, TLS và chính sách DNS.

**Tệp `HttpsVersionProbe.java`:**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HttpsVersionProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !args[0].startsWith("https://")) {
            throw new IllegalArgumentException("Pass an HTTPS URL");
        }
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .followRedirects(HttpClient.Redirect.NEVER)
                .connectTimeout(Duration.ofSeconds(5))
                .build();
        HttpRequest request = HttpRequest.newBuilder(URI.create(args[0]))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();
        HttpResponse<Void> response = client.send(request,
                HttpResponse.BodyHandlers.discarding());
        System.out.println("preferred=" + client.version());
        System.out.println("actual=" + response.version());
        System.out.println("status=" + response.statusCode());
        System.out.println("uri=" + response.uri());
    }
}
```

Biên dịch Java 17:

```bash
javac --release 17 HttpsVersionProbe.java
java HttpsVersionProbe https://your-valid-https-host.example/path
```

Địa chỉ ở dòng lệnh chỉ là **placeholder cú pháp**: thay bằng URL HTTPS bạn thực sự sở hữu hoặc được phép kiểm thử và có certificate tin cậy. Compile đã được xác minh, **không có stdout của một server công khai được tuyên bố**.

Ý nghĩa:

- `preferred=HTTP_2`: chương trình đã yêu cầu HTTP/2.
- `actual=HTTP_2`: response thực tế dùng HTTP/2; khi HTTPS, thường là kết quả ALPN chọn `h2`.
- `actual=HTTP_1_1`: response thực tế dùng HTTP/1.1; có thể vì server/intermediary không hỗ trợ HTTP/2, ALPN chọn HTTP/1.1, hoặc giới hạn triển khai.
- `status=...` là **HTTP status code**, không phải phiên bản. Một response `200 OK` có thể chạy bằng HTTP/1.1 hoặc HTTP/2.
- `uri=...` cho biết request URI của response. Chương trình đặt `Redirect.NEVER` để tránh hiểu nhầm một redirect sang URL khác là cùng endpoint ban đầu.

**Không tắt TLS certificate verification hoặc hostname checking để đạt được `HTTP_2`**. Java `HttpClient` mặc định có chính sách TLS/HTTPS của nền tảng; dùng trust store/CA hợp lệ nếu làm việc với hạ tầng nội bộ.

## 10. Vì sao proxy, reverse proxy và load balancer có thể khiến fallback?

Một đường đi HTTP có thể có nhiều **hop**:

```text
Java HttpClient
      |
      | HTTPS, ALPN h2 hoặc HTTP/1.1
      v
Corporate Proxy / CDN / Gateway
      |
      | upstream có thể là HTTP/1.1 hoặc HTTP/2 khác
      v
Backend / Origin Server
```

Trong các môi trường đó:

- Client có thể đàm phán HTTP/2 đến edge nhưng edge nói HTTP/1.1 với origin, hoặc ngược lại tùy hệ thống.
- Một HTTP proxy có thể không hỗ trợ HTTP/2 cho kiểu kết nối được yêu cầu hoặc có chính sách đặc biệt; tài liệu `HttpClient.Builder.version(...)` của JDK 17 cảnh báo ràng buộc triển khai **có thể khiến HTTP/1.1 được dùng khi qua proxy**.
- `Upgrade: h2c` và `Connection` là hop-by-hop trên HTTP/1.1; không mong đợi chúng xuyên qua nhiều proxy như end-to-end header. Việc h2c Upgrade hiếm được triển khai càng khiến không thể dựa vào nó.
- TLS interception proxy trong môi trường doanh nghiệp có thể thay đổi đối tác TLS thực tế và certificate chain. Đây là chính sách bảo mật/PKI riêng, không phải vì Java ngẫu nhiên chọn HTTP/1.1.
- `response.version()` cho biết phiên bản **client dùng để nhận response** theo implementation, không chứng minh backend nội bộ sử dụng cùng phiên bản hay status của từng hop.

Khi kiểm tra performance production, đo cả protocol version ở **client edge** và ở các upstream connections quan trọng nếu bạn có quyền quan sát; không kết luận backend hỗ trợ HTTP/2 chỉ từ response.version()==HTTP_2 ở client.

## 11. Redirect, origin và connection reuse: đừng suy luận từ một request

HTTP/2 connection có thể được reuse cho nhiều request/stream tới một origin theo các ràng buộc của HTTP/2 và client, nhưng không có nghĩa mọi request mãi mãi dùng cùng một connection/version.

Ví dụ:

```text
GET https://api.example.test/data
        |
        v
302 Location: https://login.example.test/
        |
        v
GET https://login.example.test/
```

Hai hostname có thể dẫn đến các điểm cuối khác nhau, chứng chỉ khác nhau, ALPN capability khác nhau. Nếu Java `HttpClient` được cấu hình tự đi theo redirect, `response.version()` ở response cuối **không nhất thiết phản ánh phiên bản của từng response trung gian**. Khi cần phân tích, xem redirect chain theo API phù hợp, log URI, status và version của từng response. Trong ví dụ HTTPS ở trên, `Redirect.NEVER` giữ kết quả ở request đầu để quan sát chính xác.

Tương tự, HTTP/2 **coalescing** hoặc connection reuse giữa origins, nếu được triển khai, phải tuân theo chính sách quyền hạn/certificate của server và implementation; không giả định một kết nối HTTP/2 cho mọi hostname hoặc cố dùng cùng kết nối bỏ qua certificate validation.

Khi debug, cần phân biệt:

1. Phiên bản **được yêu cầu** ở client/request.
2. Phiên bản **được chọn trên một connection**.
3. Phiên bản **được trả về cho một response cụ thể**.
4. Phiên bản của **upstream hop** sau proxy.
5. Phiên bản **TLS** (TLSv1.2/TLSv1.3) và HTTP version — hai đại lượng khác nhau.

## 12. Fallback không phải tự động retry mọi lỗi

Bật `HTTP_2` preference cho phép fallback ở những điều kiện hợp lệ, nhưng **không bảo đảm gửi lại toàn bộ request bằng HTTP/1.1 khi đang lỗi**. Cần phân biệt ba loại sự kiện:

| Loại | Ví dụ | Diễn giải |
| --- | --- | --- |
| **Negotiation / capability** | Server chỉ hỗ trợ HTTP/1.1, client nhận response HTTP/1.1 | Fallback protocol bình thường |
| **HTTP response** | Server trả 404, 500, 429 hoặc 421 | Response ở tầng HTTP; không tự chứng minh ALPN/upgrade fail |
| **Transport / TLS error** | TLS handshake/certificate fail, timeout, connection reset, GOAWAY, stream error | Có thể cần xử lý lỗi/retry riêng; không mặc định an toàn hoặc thành công |

Với HTTP/2, một connection có thể có nhiều stream; khi connection đóng, các stream chưa hoàn thành có trạng thái khác nhau. Không được **blindly retry POST hoặc request non-idempotent** chỉ vì gặp exception trong lúc gửi bằng HTTP/2. Một phía có thể đã xử lý tác vụ dù client chưa đọc được response.

Nguyên tắc thực tế:

- Thiết kế retry dựa trên **tính idempotent và semantics của request**, kết hợp idempotency key cho các thao tác tạo đơn/thu tiền/kích hoạt side effect.
- Cài `HttpRequest.Builder.timeout(...)` và `HttpClient.Builder.connectTimeout(...)` để kiểm soát một số pha chờ; đây không phải chính sách deadline toàn hệ thống cho mọi background job.
- Không hạ từ `https://` xuống `http://` khi HTTPS ALPN/TLS lỗi. Điều đó là **downgrade bảo mật**, hoàn toàn khác với chọn HTTP/1.1 bên trong HTTPS.
- Nếu dịch vụ **bắt buộc HTTP/2**, sau response có thể kiểm tra `response.version()!=HTTP_2` và coi là **protocol requirement không đạt**, thay vì mặc định gửi tiếp những thao tác phụ thuộc tính năng HTTP/2.

Ví dụ enforcement ở tầng ứng dụng (mảnh code trong phương thức có `response`):

```java
if (response.version() != HttpClient.Version.HTTP_2) {
    throw new IllegalStateException(
            "This operation requires HTTP/2");
}
```

Lưu ý: enforcement này diễn ra **sau khi đã gửi request và nhận response**, không bảo đảm một operation có side effect chưa xảy ra. Nếu bắt buộc HTTP/2 trước khi gửi dữ liệu nhạy cảm hoặc không thể retry, thiết kế API, routing và cơ chế khám phá capability phải giải quyết từ trước; không chỉ throw sau phản hồi.

## 13. Khi nào phải giữ HTTP/1.1, khi nào nên ưu tiên HTTP/2?

| Bối cảnh | Cách tiếp cận |
| --- | --- |
| Dịch vụ HTTPS hiện đại, server hỗ trợ HTTP/2 | Thường ưu tiên HTTP/2; kiểm tra response.version thực tế |
| Service cũ chỉ có HTTP/1.1 | Để fallback tự nhiên nếu phù hợp, hoặc chọn `HTTP_1_1` chủ động |
| Hạ tầng proxy có giới hạn HTTP/2 | Đo/đọc capability proxy, version actual, điều chỉnh cấu hình |
| Giao thức phụ thuộc vào WebSocket | Dùng API WebSocket; không đồng nhất WebSocket Upgrade với HTTP/2 |
| Dịch vụ yêu cầu tính năng HTTP/2 như multiplexing hoặc protocol cụ thể | Xác minh compatibility end-to-end và có policy reject nếu version sai |
| Test trên `http://localhost` với `HttpServer` | Dùng để dạy fallback và h2c Upgrade của JDK17, không phải đo ALPN |
| Hệ thống cần truyền credential/sensitive payload | Giữ HTTPS + trust/hostname validation; HTTP/2 không thay TLS |
| Cleartext h2c mới thiết kế | Xem RFC 9113 prior knowledge, khả năng hỗ trợ thực tế của thư viện/server; không dựa mặc định vào Upgrade đã deprecated |

HTTP/2 giúp multiplexing và giảm overhead header ở nhiều workload, nhưng throughput/latency còn tùy số connection, stream, flow control và tài nguyên. Đừng chọn HTTP/2 bằng niềm tin "nhanh gấp đôi": benchmark bằng workload thực tế và quan sát negotiated version ở production.

## 14. Kiểm thử theo ma trận thay vì chỉ chạy một URL

Khi xây dựng một `HttpClient` library hoặc service dùng nhiều môi trường, nên test ít nhất:

| Trường hợp | Dự kiến nếu hệ thống đáp ứng | Kiểm tra |
| --- | --- | --- |
| HTTPS server có TLS ALPN `h2` và client hỗ trợ | `HTTP_2` | `response.version()` + TLS/proxy logs |
| HTTPS server chỉ có HTTP/1.1 | `HTTP_1_1` nếu có đường fallback | Không có 101/h2c cho HTTPS |
| HTTPS certificate không trusted hoặc sai hostname | Handshake thất bại | Không tự hạ sang HTTP cleartext |
| HTTP cleartext server chỉ HTTP/1.1 | `HTTP_1_1` khi server không upgrade | Kiểm tra header và response.version |
| HTTP h2c prior-knowledge server | Tùy khả năng client thực sự hỗ trợ đường đó | Không suy từ `version(HTTP_2)` rằng gửi prior-knowledge preface |
| Có HTTP proxy | Version phụ thuộc đường kết nối và implementation | Ghi nhận cấu hình proxy + actual version |
| Client HTTP_2, một request override HTTP_1_1 | Request riêng có preference HTTP/1.1 | Không thay client global preference |
| Redirect tới origin khác | Có thể thay version theo endpoint sau redirect | Kiểm tra từng URI/response trong chain |
| HTTP/2 connection bị đóng/reset | Có thể phát sinh lỗi/timeout | Không tự retry request có side effect |
| Nhiều request đồng thời | HTTP/2 multiplexing nếu được thương lượng | Đo concurrency, throughput và flow-control/backpressure |

Nếu tự tạo server thử nghiệm bằng Java `HttpServer` của module `jdk.httpserver`, đừng nhầm nó với server HTTP/2. Dùng thêm một server HTTPS/HTTP2 có hỗ trợ ALPN, như môi trường staging đã cấu hình, để test **nhánh HTTP_2 thành công**. Kết quả staging phải được quan sát thật; không viết stdout giả định cho một server chưa chạy.

## 15. Gợi ý logging và chẩn đoán khi "đã bật HTTP_2 nhưng vẫn HTTP_1_1"

Ưu tiên thu thập các thông tin có thể kiểm chứng:

```text
URI scheme:        https hay http
Original host:     api.example.com
Client preference: HTTP_2
Request override:  absent / HTTP_1_1 / HTTP_2
Response version:  HTTP_1_1
HTTP status:       200
Redirect:          followed? final URI?
Proxy configured:  yes/no, loại proxy/transport
TLS negotiated:    h2 / http/1.1 (nếu có log ALPN)
```

Câu hỏi chẩn đoán theo trình tự:

1. URL thực sự là `https://` hay `http://`? Với HTTPS xem **ALPN**; với HTTP cleartext xem kiểu khám phá HTTP/2 (h2c/prior knowledge).
2. Chỉ kiểm tra `client.version()` hay đã kiểm tra `response.version()`?
3. Có `request.version(HTTP_1_1)` vô tình override không?
4. Server có **bật ALPN `h2`** trên chính endpoint/cổng không, hay chỉ quảng cáo hỗ trợ HTTP/2 ở một port/CDN khác?
5. Có proxy/VPN/service mesh/load balancer ở giữa không?
6. Certificate và TLS handshake có pass không? Đừng dùng fallback HTTP insecure để "giải quyết" lỗi TLS.
7. Có redirect sang một host khác với capability khác không?
8. Có lỗi server HTTP/2, connection reset hoặc giới hạn concurrent stream đang gây fallback/exception không?
9. Mã có tự đặt các header hop-by-hop `Connection`, `Upgrade`, `HTTP2-Settings` hoặc cố ép frame wire? Để thư viện quản lý negotiated protocol.
10. Khả năng HTTP/2 được **đo ở client edge** có cùng với yêu cầu của backend service không?

Để xác định lỗi, có thể dùng logging TLS/HTTP client phù hợp phiên bản JDK và công cụ server, nhưng không log authorization tokens, cookie bí mật hoặc payload cá nhân. Debug logging rất chi tiết có thể làm tăng chi phí/độ trễ và lộ dữ liệu.

## 16. Lỗi phổ biến và cách sửa

| Hiểu sai / code sai | Vì sao không đúng | Cách xử lý |
| --- | --- | --- |
| `client.version()==HTTP_2` nên mọi response HTTP/2 | Đây chỉ là preference | Dùng `response.version()` |
| `Request.Builder.version(HTTP_2)` đảm bảo server có HTTP/2 | Client không điều khiển server/proxy | Quan sát negotiated version và capability |
| `https://` cần `Upgrade: h2c` và status 101 | HTTPS HTTP/2 dùng TLS ALPN | Không tự thêm h2c header |
| `http://` có HTTP/2 nên dữ liệu đã được mã hóa | h2c không có TLS | Chọn HTTPS khi cần bảo mật |
| Thấy `Upgrade: h2c` là chắc chắn đã lên HTTP/2 | Server có thể ignore và trả 200 | Đọc response.version / protocol thực tế |
| Coi h2c Upgrade là chuẩn khuyến nghị hiện nay | RFC 9113 đã deprecate cơ chế này | Dùng TLS ALPN hoặc prior knowledge theo hỗ trợ thực |
| HTTP/1.1 fallback bên trong HTTPS làm mất TLS | Version application khác transport security | Giữ cert verification, vẫn HTTPS |
| TLS certificate sai, tắt trust manager để "dùng HTTP/2" | Mất xác thực server | Sửa chứng chỉ/trust/hostname |
| Dùng status 200 để chứng minh HTTP/2 | Status và version độc lập | Log cả status và response.version |
| Dùng response.version cuối để kết luận redirect chain ban đầu | Redirect có thể đổi endpoint/version | Xem từng response/URI |
| Dùng `HttpClient` trong try-with-resources với `--release 17` | Java 17 HttpClient chưa AutoCloseable | Tái sử dụng instance; quản lý vòng đời theo phiên bản JDK |
| HTTP/2 luôn giảm latency/không có head-of-line blocking | Flow control/TCP mất packet vẫn ảnh hưởng | Benchmark và quan sát hiệu năng |
| Gửi lại POST vô điều kiện sau GOAWAY/timeout | Side effect có thể đã chạy | Retry/idempotency policy |
| Một origin có HTTP/2 đồng nghĩa mọi proxy/backend hop có HTTP/2 | Version theo từng hop | Đo mỗi hop khi cần |
| Ép header `Connection`/`Upgrade` thủ công trong Java HttpClient | Thư viện tự kiểm soát framing và một số header | Dùng API version preference, để HTTP stack tạo request |
| Không xử lý trường hợp server không có HTTP/2 | Tính năng yêu cầu h2 có thể thất bại | Policy fallback hoặc fail-closed khi h2 là bắt buộc |

## 17. Bài tập tự kiểm tra

**Câu 1.** `HttpClient.newBuilder().version(HTTP_2).build()` gửi request đến server chỉ hỗ trợ HTTP/1.1 và nhận response bình thường. `client.version()` và `response.version()` có thể lần lượt bằng gì? Trường nào chứng minh phiên bản đã dùng?

**Câu 2.** Ứng dụng gọi URL `https://api.example.test/data` và muốn HTTP/2. Nó có cần gửi HTTP/1.1 `Upgrade: h2c` không? Giao thức ứng dụng nào được gửi trong ALPN?

**Câu 3.** JDK17 HttpClient gửi `Upgrade: h2c` tới HTTP/1.1 loopback server, server trả `200 OK` mà không trả `101`. Client đã chuyển sang HTTP/2 chưa? Tại sao?

**Câu 4.** Server mới muốn hỗ trợ cleartext HTTP/2. Vì sao không nên thiết kế chỉ dựa vào h2c Upgrade lịch sử? `prior knowledge` có điều kiện gì?

**Câu 5.** Có reverse proxy: client nói HTTP/2 với CDN, nhưng CDN nói HTTP/1.1 với origin. `response.version()` ở client có thể là gì? Điều đó tiết lộ được phiên bản upstream không?

**Câu 6.** HTTPS handshake lỗi certificate, developer đề xuất đổi URL sang `http://` hoặc dùng trust-all để chạy được HTTP/2. Đâu là rủi ro? Fallback HTTP version khác downgrade bảo mật ở điểm nào?

**Câu 7.** Một POST thanh toán đã gửi trên stream HTTP/2, connection reset trước response. Có nên tự động gửi lại ngay không? Cần cơ chế gì?

**Câu 8.** Client mặc định HTTP_2 nhưng một request có `.version(HTTP_1_1)`. Request-level setting có thay đổi client version cho các request còn lại không? Kiểm tra kết quả tại đâu?

**Câu 9.** Khi `response.statusCode()==200` và `response.version()==HTTP_1_1`, có thể nói API thành công nhưng không sử dụng HTTP/2 không? Khi nào phải coi version là điều kiện nghiệp vụ?

**Đáp án gợi ý:**

1. Client preference `HTTP_2`; response thực tế có thể `HTTP_1_1`. Phải dùng `response.version()`.
2. Không. HTTPS dùng TLS ALPN với `h2` (và có thể `http/1.1`), không đi qua `101/h2c Upgrade`.
3. Chưa. Server ignore đề nghị và trả HTTP/1.1; status 200 là response bình thường, không phải upgrade.
4. RFC 9113 deprecate h2c Upgrade. Prior knowledge chỉ hợp lệ khi client **biết trước** server chấp nhận HTTP/2 cleartext và có implementation hỗ trợ.
5. Client có thể thấy `HTTP_2` cho client↔CDN, nhưng không chứng minh CDN↔origin cũng H2.
6. Chuyển sang HTTP cleartext hoặc trust-all làm mất bảo mật/xác thực; chọn HTTP/1.1 **trên cùng HTTPS an toàn** khác với bỏ HTTPS.
7. Không retry mù. Dùng idempotency key, kiểm tra trạng thái xử lý và policy retry an toàn.
8. Không; override áp dụng cho request riêng. Kiểm tra `response.version()`, client.version vẫn là preference cấp client.
9. Có thể. Nếu ứng dụng bắt buộc HTTP/2, phải có policy verify/reject ở cấp protocol/capability, không chỉ status code.

## Tài liệu chính thức

- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `version(HttpClient.Version)`, HTTP/2 preference, HTTP/1.1 fallback và proxy constraints.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `version()`, `send(...)` và connection/client configuration.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): per-request version preference, `timeout`.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): `version()` trả Optional; override hay inherit.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `version()` là phiên bản response thực tế.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html): ALPN `h2` cho HTTPS, cleartext prior knowledge, và deprecation của h2c HTTP/1.1 Upgrade.
- [RFC 9110 — HTTP Semantics, §7.8 Upgrade](https://www.rfc-editor.org/rfc/rfc9110.html#section-7.8): `Upgrade` và `101 Switching Protocols` của HTTP/1.1 nói chung.
- [RFC 7540 — HTTP/2 (đã được RFC 9113 thay thế)](https://www.rfc-editor.org/rfc/rfc7540.html): lịch sử h2c Upgrade/HTTP2-Settings, không phải khuyến nghị triển khai mới.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server HTTP cục bộ dùng kiểm thử HTTP/1.1 fallback.
