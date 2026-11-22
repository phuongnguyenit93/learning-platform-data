# Java 11 — HTTP/1.1, HTTP/2 và phiên bản được thương lượng

**Chủ đề:** Java 11 → HTTP Client. Bài học giải thích chính xác sự khác biệt giữa **phiên bản HTTP client muốn sử dụng** và **phiên bản thực tế được dùng cho từng phản hồi**, cách `java.net.http.HttpClient` của Java 11 chọn HTTP/1.1 hoặc HTTP/2, vai trò của TLS/ALPN, server/proxy, và cách kiểm chứng bằng `HttpResponse.version()`. Chỉ trình bày kiến thức còn hữu ích và được hỗ trợ cho Java 11; không dùng API incubator cũ hoặc giả định Java 11 có HTTP/3.

**Sau bài học, bạn có thể:** chọn HTTP version ở mức client/request, đọc version thực tế sau khi gửi, hiểu khi nào HTTP/2 có thể fallback về HTTP/1.1, chạy một demo offline có stdout xác định, đo phiên bản của HTTPS endpoint thực, phân biệt lỗi thương lượng với HTTP status/error, và thiết kế khả năng tương thích ở môi trường proxy, load balancer và CI.

## 1. Phiên bản HTTP là thuộc tính của một lần trao đổi, không phải một nhãn cấu hình duy nhất

**HTTP/1.1** và **HTTP/2** là các phiên bản của giao thức trao đổi HTTP giữa client và điểm kết thúc HTTP mà client đang kết nối. Cả hai đều dùng các khái niệm cốt lõi quen thuộc: URI, method như GET/POST, header, status code, body và các quy tắc cache/cookie theo hợp đồng. Điểm khác lớn nằm ở **cách đóng khung và truyền thông điệp trên kết nối**.

Ví dụ: cùng một lệnh GET có thể nhận `200 OK` dù được truyền qua HTTP/1.1 hoặc HTTP/2. `200` là **mã trạng thái nghiệp vụ/giao thức HTTP của response**, không cho biết phiên bản truyền tải.

Trong Java 11 có ba cấp thông tin phải tách:

1. **Client preference** — `HttpClient.version()`: phiên bản mà client muốn dùng mặc định.
2. **Request preference** — `HttpRequest.version()`: `Optional<HttpClient.Version>`, chỉ có giá trị nếu request builder đã đặt version riêng. Khi rỗng, request kế thừa preference của client gửi nó.
3. **Actual response version** — `HttpResponse.version()`: phiên bản **thực sự được dùng cho response đó**. Đây là câu trả lời chuẩn khi muốn biết một request đã chạy HTTP/1.1 hay HTTP/2.

Sự khác nhau quan trọng:

~~~text
Client muốn HTTP_2
         |
Request có override?
    |             |
  Có            Không
  |               |
Dùng preference   Kế thừa preference
của request       của client
    \             /
     \           /
      Server / TLS ALPN / proxy / khả năng của kết nối
                        |
          Response.version() = phiên bản thực tế
~~~

Đây là flow diễn giải, **không phải lời hứa rằng mọi yêu cầu HTTP_2 sẽ thành công trên HTTP/2**. Kết quả cuối có thể là HTTP/1.1; lỗi kết nối/TLS có thể khiến **không có response nào**.

## 2. HTTP/1.1 và HTTP/2: khác nhau ở đâu?

| Khía cạnh | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Biểu diễn thông điệp | Dạng văn bản ở tầng framing truyền thống (start line, headers, body). | Binary framing với các frame và stream. |
| Nhiều request trên kết nối | Có persistent connection và tái sử dụng, nhưng concurrency trên một kết nối bị hạn chế; pipelining không phải giải pháp phổ biến trong thực tế. | Multiplex nhiều stream đồng thời trên một kết nối khi hai phía hỗ trợ; client vẫn có thể dùng hơn một kết nối tùy tình huống. |
| Header | Truyền theo cách HTTP/1.1. | Dùng cơ chế nén header HPACK trong HTTP/2. |
| Thứ tự phản hồi | Cách HTTP/1.1 truyền trên cùng kết nối hạn chế xử lý nhiều request chồng lấp. | Các frame của nhiều stream có thể xen kẽ; từng stream vẫn có ngữ nghĩa response riêng. |
| Mã trạng thái và phương thức | GET/POST/PUT..., 2xx/4xx/5xx. | Vẫn GET/POST/PUT..., 2xx/4xx/5xx; **không** phải một API nghiệp vụ khác. |
| Trên HTTPS | HTTP/1.1 có thể chạy qua TLS. | Thông thường HTTP/2 qua TLS sử dụng ALPN để chọn `h2`. |
| Trên HTTP không TLS | HTTP/1.1 thông thường. | HTTP/2 cleartext (`h2c`) có cơ chế riêng/upgrade nếu client, server và các trung gian hỗ trợ; không suy đoán rằng luôn được dùng. |
| Hiệu năng | Đủ tốt cho nhiều tải và hạ tầng; phụ thuộc keep-alive, caching, kết nối và độ trễ. | Có thể tốt hơn khi nhiều request cùng origin, nhưng lợi ích phụ thuộc server, proxy, mất gói, tải và ứng dụng. |

Một số hiểu lầm cần tránh:

- **HTTP/1.1 không đồng nghĩa một request = một TCP connection.** Kết nối có thể được tái sử dụng.
- **HTTP/2 không làm mọi request nhanh hơn**: framing và multiplexing không loại bỏ độ trễ ứng dụng, CPU server hoặc sự nghẽn tại TCP. HTTP/2 vẫn có thể chịu head-of-line blocking ở **tầng TCP** khi mất gói.
- **HTTP/2 không tự nén body.** HPACK là về header; `Content-Encoding: gzip`/br và cơ chế nén payload là một chuyện khác, được thương lượng/cấu hình riêng.
- **HTTP/2 không mặc nhiên bảo mật nếu chạy cleartext.** Dùng HTTPS và xác minh chứng chỉ cho lưu lượng cần bảo vệ; version và TLS là hai khái niệm khác nhau.
- **HTTP/2 không thay thế thiết kế lỗi/idempotency.** Request gửi theo HTTP/2 vẫn có thể timeout, bị 429/503 hoặc bị xử lý một phần.

Với ứng dụng Java hiện nay, lựa chọn thường là **cho phép thương lượng HTTP/2 nếu hạ tầng hỗ trợ**, giữ khả năng tương thích HTTP/1.1 và quan sát `response.version()` để ra quyết định. Chỉ “ép phiên bản” khi có yêu cầu kỹ thuật được xác minh, chẳng hạn workaround với proxy hoặc thử nghiệm so sánh.

## 3. Java 11 cung cấp API HTTP Client chuẩn nào?

Module `java.net.http` trở thành API chuẩn từ **Java 11** (JEP 321). Các kiểu chính:

- `HttpClient` — client dùng chung, có cấu hình preference, proxy, redirect, timeout kết nối, SSL và executor.
- `HttpClient.Builder` — cấu hình client trước khi `build()`; client tạo xong là immutable về cấu hình.
- `HttpClient.Version` — trên **JDK 11 chỉ có `HTTP_1_1` và `HTTP_2`**. Không viết `HttpClient.Version.HTTP_3` trong mã nhắm Java 11.
- `HttpRequest` và `HttpRequest.Builder` — URI, method, header, timeout, body và version preference của từng request.
- `HttpResponse<T>` — status, headers, body, URI, request liên quan, actual protocol version, previous response khi có redirect/authentication.
- `HttpResponse.BodyHandlers` — cách nhận body; `ofString(StandardCharsets.UTF_8)`, `ofByteArray()`, `ofFile(path)`, `discarding()`, v.v.
- `client.send(request, handler)` — đồng bộ và có checked `IOException`/`InterruptedException`.
- `client.sendAsync(request, handler)` — bất đồng bộ, trả `CompletableFuture<HttpResponse<T>>`.

Import Java 11:

~~~java
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
~~~

Đây là **đoạn import** cho chương trình Java 11, không phải toàn bộ chương trình độc lập. Không dùng các package HTTP incubator của Java 9/10 cho bài học Java 11; cũng không dùng thư viện bên ngoài chỉ để hỏi `response.version()`.

### 3.1. Giá trị mặc định là preference cho HTTP/2

~~~java
HttpClient client = HttpClient.newHttpClient();
System.out.println(client.version());
~~~

Đây là đoạn minh họa cần đặt trong method. Trên JDK 11, stdout của dòng in version là:

~~~text
HTTP_2
~~~

**Nhưng đây chỉ là phiên bản được ưu tiên.** Ngay cả khi client mặc định ưu tiên `HTTP_2`, một request tới server chỉ hỗ trợ HTTP/1.1 vẫn có thể nhận `response.version() == HTTP_1_1`. Nói “Java 11 mặc định gửi mọi request bằng HTTP/2” là không chính xác.

### 3.2. Đặt preference ở cấp client

~~~java
HttpClient preferHttp2 = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_2)
    .build();

HttpClient preferHttp11 = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_1_1)
    .build();
~~~

Đây là **đoạn minh họa**; mặc định HTTP/2 nên gọi `version(HTTP_2)` hữu ích chủ yếu để truyền đạt ý đồ rõ ràng. Lời gọi `version(...)` yêu cầu phiên bản cụ thể **khi có thể**, không biến client thành trình thương lượng giao thức độc lập với server/proxy.

### 3.3. Đặt preference riêng cho một request

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
    .version(HttpClient.Version.HTTP_1_1)
    .GET()
    .build();
~~~

Đây là **đoạn minh họa**, import `java.net.URI`. Nếu client ưu tiên HTTP/2 nhưng request đặt `HTTP_1_1`, preference của request là thứ được sử dụng cho lần gửi đó; cấu hình `HttpClient` không đổi. Đặt version **không tự gửi request** và **không xác nhận server có hỗ trợ phiên bản đó**.

### 3.4. Phân biệt ba lời gọi kiểm tra

| Lệnh | Kiểu trả về | Thực sự nói điều gì |
| --- | --- | --- |
| `client.version()` | `HttpClient.Version` | Preference mặc định của **client**, không phải kết quả kết nối. |
| `request.version()` | `Optional<HttpClient.Version>` | Preference được đặt **trực tiếp trên request**, có thể empty để kế thừa client. |
| `response.version()` | `HttpClient.Version` | Phiên bản HTTP **thực tế dùng cho response** đã nhận. |

Để audit hệ thống, ưu tiên ghi nhận cả **preference và actual**; đừng dùng mỗi `client.version()` làm bằng chứng traffic đang chạy HTTP/2.

## 4. HTTPS và ALPN: HTTP version được chọn như thế nào?

Với **HTTPS** (HTTP qua TLS), client và server thường dùng phần mở rộng **ALPN — Application-Layer Protocol Negotiation** trong TLS handshake. Client đưa ra danh sách giao thức ứng dụng mà nó hỗ trợ/chấp nhận; server chọn giao thức phù hợp, thường là:

- `h2` — HTTP/2 qua TLS.
- `http/1.1` — HTTP/1.1 qua TLS.

Mô hình khái quát:

~~~text
Client gửi HTTPS request, ưu tiên HTTP/2
    |
    v
Kết nối TCP + TLS handshake
    |
    v
ALPN client/server thống nhất giao thức ứng dụng
    |
    +-- chọn h2 --------> HTTP/2 frames, response.version() == HTTP_2
    |
    +-- chọn http/1.1 --> HTTP/1.1, response.version() == HTTP_1_1
    |
    +-- không thể thiết lập TLS/HTTP hợp lệ --> exception, không có response
~~~

Đây là mô hình **đơn giản hóa**: proxy, TLS termination, connection reuse và chính sách của HttpClient có thể ảnh hưởng từng bước. Khi đã có kết nối thích hợp được tái sử dụng, không phải mọi request đều thực hiện TLS handshake mới. ALPN được thương lượng trên **kết nối TLS**, không phải một HTTP header do ứng dụng tự đặt.

**Đừng tự thêm header `ALPN: h2` hay `HTTP-Version: 2`** và mong server chuyển sang HTTP/2. HTTP/2 có binary framing, mã thông báo ALPN nằm trong tầng TLS, và JDK HTTP Client quản lý chi tiết giao thức. Các HTTP/2 pseudo-header như `:method`, `:path` không được cấu hình như header ứng dụng thông thường.

### 4.1. HTTP/2 không yêu cầu bạn tự điều khiển SSLParameters

`HttpClient` trên Java 11 tự xử lý các phần cần thiết cho kết nối HTTPS và thương lượng phiên bản. Khi không có nhu cầu đặc biệt, hãy để implementation quản lý ALPN, SNI, trust store và SSLParameters theo cấu hình an toàn. Tự sửa danh sách application protocols hoặc tắt kiểm tra chứng chỉ chỉ để “bật HTTP/2” có thể phá thương lượng hoặc làm mất an toàn.

**TLS protocol version khác HTTP protocol version**. Ví dụ “TLSv1.3” là phiên bản TLS, “HTTP_2” là phiên bản HTTP. `response.sslSession()` cung cấp thông tin TLS khi response đi qua HTTPS, nhưng `sslSession().getProtocol()` cho biết **TLS**, còn `response.version()` cho biết **HTTP**. Chúng không thay thế nhau.

### 4.2. HTTP/2 qua cleartext (h2c) là chuyện khác

Với URI `http://`, **không có TLS/ALPN**. HTTP/2 cleartext có cơ chế upgrade/`h2c` khi endpoint và các thành phần trung gian hỗ trợ; API của Java 11 có thể thử upgrade nếu prefer HTTP/2. Nếu server không nâng cấp, response có thể tiếp tục HTTP/1.1. Vì vậy không dùng lời gọi `version(HTTP_2)` tới một địa chỉ `http://` làm bằng chứng rằng request chắc chắn dùng HTTP/2.

Trong production, thường sử dụng **HTTPS** cho giao tiếp qua mạng cần bảo vệ. Demo local `http://127.0.0.1` ở phần sau chỉ nhằm kiểm chứng hành vi Java mà không cần Internet/chứng chỉ, không phải khuyến nghị dùng HTTP cleartext cho dữ liệu nhạy cảm.

## 5. Vì sao yêu cầu HTTP/2 mà vẫn nhận HTTP/1.1?

Đó có thể là **hành vi fallback hợp lệ**, không nhất thiết là lỗi:

1. **Server chỉ hỗ trợ HTTP/1.1**, hoặc endpoint TLS không quảng bá/không chọn `h2`.
2. **Reverse proxy, API gateway, CDN, service mesh hoặc load balancer** nằm giữa client và backend có chính sách phiên bản riêng. Kết nối client→proxy có thể khác proxy→backend; client chỉ trực tiếp quan sát phiên bản ở kết nối phía mình.
3. **HTTP proxy** hoặc tính năng của JDK/implementation giới hạn dùng HTTP/2 trong mode đang yêu cầu. Tài liệu Java 11 ghi rõ proxy có thể khiến HTTP/1.1 được chọn thay thế.
4. **Request override** đặt `HTTP_1_1` dù client mặc định `HTTP_2`.
5. **Endpoint khác sau redirect** có thể hỗ trợ phiên bản khác; response cuối cùng có phiên bản riêng.
6. **URI `http://`** không có ALPN; việc dùng h2c phụ thuộc khả năng upgrade của server và đường truyền.
7. **Cấu hình TLS/certificate/ALPN** không thống nhất: một số tình huống fallback, tình huống khác thất bại kết nối hoàn toàn. Không gom mọi lỗi TLS thành “đã downgrade”.

Một số trường hợp **không có HttpResponse**: DNS fail, TCP connect fail, handshake TLS/certificate fail, request timeout hoặc interruption. Khi đó không được in ra một “HTTP version thực tế” do tự đoán.

**Nguyên tắc:** Chỉ có thể kết luận `HTTP_2` hay `HTTP_1_1` cho request hoàn thành khi đọc `response.version()` (hoặc version từ `HttpResponse.ResponseInfo` trong body handler). Preference là đầu vào lựa chọn; actual là kết quả.

## 6. Chương trình Java 11 chạy độc lập và có stdout xác định

Ví dụ sau tạo một HTTP server chỉ hỗ trợ HTTP/1.1 tại `127.0.0.1` với cổng ngẫu nhiên. Một client **ưu tiên HTTP/2** được dùng để gửi:

- Request 1 **override HTTP/1.1**: response chắc chắn phản ánh HTTP/1.1 của server cục bộ.
- Request 2 **không đặt version riêng**: request kế thừa preference HTTP/2; server không hỗ trợ HTTP/2 nên thực tế vẫn là HTTP/1.1 khi fallback hợp lệ.

Không phụ thuộc website bên ngoài, DNS công cộng hoặc chứng chỉ HTTPS. Dùng `com.sun.net.httpserver.HttpServer` từ module **`jdk.httpserver`** để tạo server demo/test; đây là JDK HTTP server nhỏ, không phải framework production.

**Tệp:** `HttpVersionDemo.java`

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class HttpVersionDemo {
    private HttpVersionDemo() {
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/hello", exchange -> {
            byte[] data = "hello".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, data.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(data);
            }
        });

        server.start();
        try {
            URI uri = URI.create(
                "http://127.0.0.1:" + server.getAddress().getPort() + "/hello");

            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

            HttpRequest pinned = HttpRequest.newBuilder(uri)
                .version(HttpClient.Version.HTTP_1_1)
                .timeout(Duration.ofSeconds(5))
                .GET().build();

            HttpResponse<String> first = client.send(pinned,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            System.out.println("client.preferred=" + client.version());
            System.out.println("request.override=" +
                pinned.version().orElseThrow());
            System.out.println("response.actual=" + first.version());
            System.out.println("status=" + first.statusCode());
            System.out.println("body=" + first.body());

            HttpRequest inherited = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5)).GET().build();
            System.out.println("inherited.version.set=" +
                inherited.version().isPresent());

            HttpResponse<String> second = client.send(inherited,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("inherited.actual=" + second.version());
        } finally {
            server.stop(0);
        }
    }
}
~~~

**Biên dịch và chạy với Java 11** (hoặc JDK mới có `--release 11`), trên máy cho phép dùng cổng loopback:

~~~bash
javac --release 11 --add-modules jdk.httpserver HttpVersionDemo.java
java --add-modules jdk.httpserver HttpVersionDemo
~~~

**Stdout dự kiến chính xác** khi server loopback hoạt động bình thường:

~~~text
client.preferred=HTTP_2
request.override=HTTP_1_1
response.actual=HTTP_1_1
status=200
body=hello
inherited.version.set=false
inherited.actual=HTTP_1_1
~~~

Lưu ý mã này yêu cầu môi trường có quyền bind/connect loopback, và HTTP server cục bộ chỉ hỗ trợ HTTP/1.1; không có kết nối Internet. Nếu môi trường cấm socket local, chương trình có thể lỗi I/O trước khi in đủ stdout.

### 6.1. Đọc kỹ kết quả

- `client.version()` là `HTTP_2` vì builder đã yêu cầu preference. Nó **không đổi** sau khi gửi đến HTTP/1.1 server.
- `pinned.version().orElseThrow()` là `HTTP_1_1` vì request override có mặt. Đây vẫn là **requested version**, chưa phải actual.
- `first.version()` là `HTTP_1_1` vì endpoint local trả response HTTP/1.1.
- `status=200` là status của response; nó độc lập với version.
- `inherited.version().isPresent()==false`: request thứ hai **không khai báo override**, không có nghĩa nó đã yêu cầu HTTP/1.1. Nó kế thừa preference `HTTP_2` từ client.
- `second.version()` cũng là `HTTP_1_1` do server local không hỗ trợ HTTP/2; Java có thể dùng HTTP/1.1 khi thương lượng/upgrade không thành công.
- `server.stop(0)` dừng test server. Không hard-code cổng 8080 để tránh trùng; JDK cấp cổng khả dụng từ số 0.

**Mấu chốt:** Trong cùng một chương trình, `client.version()==HTTP_2` nhưng cả hai response thực tế có `HTTP_1_1`. Đó không phải mâu thuẫn của API; nó là bản chất **preference vs actual**.

## 7. Probe một HTTPS endpoint thật: kết quả phụ thuộc môi trường

Khi cần xác minh HTTP/2 qua TLS/ALPN, viết một chương trình kiểm tra response thực. **Không gán stdout phiên bản cố định** cho ví dụ mạng công cộng: cùng URL có thể được phục vụ qua CDN, proxy hoặc các chính sách khác tại các thời điểm/mạng khác nhau.

**Tệp:** `HttpsVersionProbe.java`

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HttpsVersionProbe {
    private HttpsVersionProbe() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                "Usage: java HttpsVersionProbe https://host/path");
            return;
        }

        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException("HTTPS is required");
        }

        HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_2)
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpResponse<Void> response = client.send(
            request, HttpResponse.BodyHandlers.discarding());

        System.out.println("client.preferred=" + client.version());
        System.out.println("request.override.present=" +
            request.version().isPresent());
        System.out.println("response.actual=" + response.version());
        System.out.println("status=" + response.statusCode());
        System.out.println("final.uri=" + response.uri());
    }
}
~~~

Lệnh:

~~~bash
javac --release 11 HttpsVersionProbe.java
java HttpsVersionProbe https://example.com/
~~~

**Dòng đầu có thể dự đoán:**

~~~text
client.preferred=HTTP_2
request.override.present=false
~~~

**Các dòng còn lại không có stdout cố định:** `response.actual` có thể là `HTTP_2` hoặc `HTTP_1_1`; `status` phụ thuộc endpoint; `final.uri` là URI cuối được nhận (trong ví dụ đang tắt tự follow redirect nên thường chính là URI đã gửi). Lệnh có thể ném `IOException`/`InterruptedException` nếu DNS, mạng, proxy, TLS hoặc server không đáp ứng. Ví dụ dùng `BodyHandlers.discarding()` để không giữ body trong bộ nhớ; client vẫn phải nhận/phân loại response.

**Tránh SSRF khi biến thành dịch vụ:** Chương trình probe dòng lệnh cho người vận hành nhập URL là một demo. Nếu triển khai dưới dạng API nhận URL từ người dùng bên ngoài, phải áp dụng allowlist host/scheme, chống truy cập IP nội bộ/metadata endpoints, kiểm soát DNS rebinding/redirect và chính sách proxy. Không biến demo thành một HTTP-fetch service mở tùy ý.

## 8. Cách đặt version đúng cho từng yêu cầu

Tùy hệ thống, bạn có ba lựa chọn:

### 8.1. Mặc định ưu tiên HTTP/2

~~~java
HttpClient client = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_2)
    .build();
~~~

Tốt khi endpoint và gateway hỗ trợ H2 nhưng cần fallback HTTP/1.1 để tương thích. **Đo actual**, đừng suy từ preference. Một `HttpClient` có thể tái sử dụng cho nhiều request; không tạo client mới cho từng lời gọi nếu không có lý do quản lý kết nối/cấu hình rõ ràng.

### 8.2. Ưu tiên HTTP/1.1 khi phải tương thích hệ thống đặc biệt

~~~java
HttpClient client = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_1_1)
    .build();
~~~

Ví dụ cần workaround cho HTTP/2 gateway bị lỗi, thử nghiệm tương thích hoặc một môi trường upstream chỉ được chứng nhận HTTP/1.1. Ghi lý do bằng tài liệu cấu hình và theo dõi khi hạ tầng được sửa; tránh cài cứng H1.1 khắp hệ thống chỉ vì chưa đo được H2.

### 8.3. Chỉ override một request

~~~java
HttpRequest legacyEndpoint = HttpRequest.newBuilder(
        URI.create("https://service.example/resource"))
    .version(HttpClient.Version.HTTP_1_1)
    .GET()
    .build();
~~~

Đây là **đoạn minh họa**, địa chỉ ví dụ không phải endpoint được xác nhận; cần import `java.net.URI`. Cách này giúp giữ preference H2 toàn cục nhưng yêu cầu riêng cho endpoint đã biết có vấn đề. Một request mới không gọi `version()` sẽ kế thừa cấu hình của client, không kế thừa override của request khác.

**Không nhầm “yêu cầu ưu tiên” với “yêu cầu bắt buộc”.** Nếu hợp đồng ứng dụng thực sự **chỉ chấp nhận HTTP/2**, phải kiểm tra `response.version()==HTTP_2` và quyết định xử lý khi không đạt (theo yêu cầu dịch vụ); chỉ gọi `request.version(HTTP_2)` là không đủ.

## 9. HTTP status, TLS và response version là ba trục khác nhau

Giả sử:

~~~java
HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

int status = response.statusCode();
HttpClient.Version actual = response.version();
~~~

Đây là đoạn minh họa, các biến `client`/`request` và import đã được khai báo; lệnh `send` có thể ném `IOException`/`InterruptedException`.

Một response có thể là:

| Actual version | HTTP status | Cách hiểu |
| --- | --- | --- |
| HTTP_2 | 200 | Phản hồi thành công ở tầng HTTP trên H2. |
| HTTP_2 | 404 | Server trả “không tìm thấy” **qua H2**; không phải lỗi thương lượng. |
| HTTP_1_1 | 200 | Thành công qua H1.1; có thể do preference H1.1 hoặc fallback. |
| HTTP_1_1 | 503 | Server/proxy không sẵn sàng, nhưng phản hồi đã đến qua H1.1. |
| Không có response | Không có status | DNS, kết nối, TLS, timeout hoặc lỗi khác khiến client không có response để đọc version. |

Đừng viết:

~~~java
if (response.statusCode() == 200) {
    // "Đã sử dụng HTTP/2" — suy luận sai.
}
~~~

**Kiểm tra đúng:** `response.version()` quyết định version thực tế; `response.statusCode()` quyết định status mà server trả. Với HTTPS, `sslSession()` cung cấp session TLS nếu có, nhưng TLSv1.2/TLSv1.3 cũng không chứng minh H2 hay H1.1.

### 9.1. Nếu cần từ chối fallback khi nghiệp vụ đòi H2

~~~java
if (response.version() != HttpClient.Version.HTTP_2) {
    throw new IllegalStateException(
        "Server did not negotiate HTTP/2");
}
~~~

Đây là **đoạn minh họa** trong method đã có `response`. Phải nhận thức rằng **request đã được gửi và có thể đã được xử lý** trước khi code kiểm tra version. Với POST/PUT hoặc giao dịch có side effect, **không tự gửi lại ngay trên H2** nếu không có idempotency key/quy tắc retry hợp lệ. Nếu “H2 bắt buộc” là yêu cầu bảo mật/kiến trúc, nên kiểm tra capability ngay trong health-check/handshake và cấu hình gateway, thay vì chỉ phát hiện sau thao tác ghi dữ liệu.

## 10. Redirect và nhiều chặng có thể khiến version khác nhau

Java 11 `HttpClient` có thể được cấu hình follow redirects:

~~~java
HttpClient client = HttpClient.newBuilder()
    .followRedirects(HttpClient.Redirect.NORMAL)
    .version(HttpClient.Version.HTTP_2)
    .build();
~~~

Đây là đoạn minh họa. Với các redirect thực sự được theo, URL đích, server, certificate, proxy và phiên bản thực tế có thể khác nhau. `HttpResponse.version()` của response cuối cho biết **phiên bản của response cuối**, không tự khẳng định mọi chặng trước đó cũng dùng cùng version.

Để xem các response trung gian khi API cung cấp:

~~~java
HttpResponse<?> current = response;
while (current != null) {
    System.out.println(
        current.statusCode() + " " + current.version() + " " + current.uri());
    current = current.previousResponse().orElse(null);
}
~~~

Đây là **đoạn minh họa**, giả sử `response` đã có. `previousResponse()` có thể có các response trung gian do redirect hoặc authentication. Kết quả in ra phụ thuộc chuỗi response thực tế; không có stdout cố định. Cấu hình `Redirect.NEVER` trong chương trình probe ở trên cố tình tránh vấn đề này khi muốn đo chính endpoint được truyền vào.

**An toàn:** Khi follow redirects từ URL không tin cậy, giới hạn điểm đến và chuyển scheme/host theo chính sách; không chuyển token nhạy cảm một cách thiếu kiểm soát. Nếu request không idempotent, hãy hiểu cơ chế và chính sách redirect riêng của API, không mặc định việc tự follow là an toàn.

## 11. Timeout, lỗi kết nối và bất đồng bộ

Thương lượng phiên bản xảy ra cùng đường đi của network/TLS; lỗi trong quá trình đó có thể ngăn hoàn toàn việc tạo response. Vì vậy cần phân biệt:

- **`connectTimeout` trên client:** thời gian giới hạn cho quá trình thiết lập kết nối mới.
- **`timeout` trên request:** giới hạn thời gian chờ request theo hợp đồng Java.
- **`HttpConnectTimeoutException`:** timeout kết nối; là subclass của `HttpTimeoutException`.
- **`HttpTimeoutException`:** timeout HTTP request ở phạm vi rộng hơn.
- **`SSLHandshakeException`/`SSLException`:** lỗi TLS/certificate/handshake; không có nghĩa được phép vô hiệu hóa kiểm tra chứng chỉ để “thử H2”.
- **`IOException`:** các lỗi I/O khác; **`InterruptedException`** từ `send` cần bảo toàn interrupted flag nếu bắt để xử lý.

Mẫu phân loại:

~~~java
try {
    HttpResponse<Void> response = client.send(
        request, HttpResponse.BodyHandlers.discarding());
    System.out.println("actual=" + response.version());
} catch (java.net.http.HttpConnectTimeoutException e) {
    report("CONNECT_TIMEOUT", e);
} catch (java.net.http.HttpTimeoutException e) {
    report("REQUEST_TIMEOUT", e);
} catch (java.io.IOException e) {
    report("IO_OR_TLS_ERROR", e);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    report("INTERRUPTED", e);
}
~~~

Đây là **đoạn minh họa**, `client`/`request` và hàm `report` thuộc ứng dụng. Thứ tự catch đặt subclass cụ thể trước superclass. Nếu lỗi xảy ra trước khi nhận response, **không có `response.version()` để log**; lưu trạng thái như “no_response” thay vì điền HTTP_1_1 tùy tiện.

Đối với async:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.discarding())
    .thenAccept(r -> System.out.println("actual=" + r.version()))
    .exceptionally(error -> {
        System.err.println("Request failed: " + error.getClass().getName());
        return null;
    });
~~~

Đây là **đoạn minh họa**, `client` và `request` đã có; ứng dụng cần giữ/làm việc với `CompletableFuture` để bảo đảm tác vụ hoàn thành đúng vòng đời. Async không bảo đảm HTTP/2; nó là cơ chế thực thi, còn response vẫn có `version()`. Với nhiều request, multiplexing H2 có thể có lợi, nhưng số kết nối/stream, tải backend, backpressure và timeout vẫn cần quản lý.

## 12. Proxy, gateway và observability

Một kiến trúc thường gặp:

~~~text
Java HttpClient ── HTTPS/HTTP2 ──> CDN / API Gateway
                                       |
                                       | HTTP/1.1 hoặc HTTP/2
                                       v
                                  Backend Service
~~~

Ví dụ này minh họa **hai kết nối/tầng giao thức độc lập**. Nếu `response.version()==HTTP_2`, bạn biết giao thức giữa client và điểm HTTP mà client trực tiếp trao đổi qua kết nối đó; **không chứng minh** gateway đã dùng HTTP/2 đến backend. Tương tự, log backend thấy H1.1 không phủ định việc client→gateway dùng H2.

Cần quan sát ở từng tầng:

| Điểm đo | Nguồn | Câu hỏi trả lời |
| --- | --- | --- |
| Java client | `client.version()` và `request.version()` | Ứng dụng **muốn** dùng phiên bản nào? |
| Java client | `response.version()` | Response đến trên **HTTP version nào**? |
| Java client | `statusCode()`, latency, timeout, exception | Request thành công, bị từ chối hay hỏng ở đâu? |
| Edge/API Gateway | Log access/TLS/ALPN, protocol upstream | Frontend và backend của gateway dùng protocol nào? |
| Backend | Access logs, proxy headers được tin cậy, tracing | Backend nhận request theo giao thức nào? |

Khi log, dùng trường rõ nghĩa như `http.client.preferred_version`, `http.response.actual_version`, `http.status_code`, `error.type`; không coi đây là tên trường bắt buộc của một schema telemetry. Ghi tách version và error, tránh cardinality không kiểm soát bởi raw URL/query/token. Khi trace request qua nhiều proxy, dùng correlation ID và nguồn telemetry đáng tin; không tự đặt phiên bản backend bằng giá trị quan sát ở client.

**Nếu một proxy làm downgrade:** không mặc định đó là lỗi bảo mật; có thể là cấu hình/giao thức bình thường của từng hop. Chỉ báo lỗi khi hợp đồng/kỳ vọng kỹ thuật yêu cầu một hop cụ thể dùng HTTP/2 và có bằng chứng từ telemetry của chính hop đó.

## 13. Chẩn đoán khi HTTP/2 không được dùng

Quy trình có ích, theo thứ tự:

1. **Kiểm tra request thực sự gửi qua client nào.** `HttpClient` được tái sử dụng hay instance mới? `client.version()` ra sao?
2. **Kiểm tra override:** `request.version().isPresent()` có `true` không? Nếu có, nó yêu cầu version nào? Override có thể giải thích toàn bộ vấn đề.
3. **Lấy actual:** từ response thật, in `response.version()`, `statusCode()` và `uri()`. Nếu request lỗi trước response, phân loại exception.
4. **Tách HTTPS và HTTP:** URI `https://` thì xem TLS/ALPN; `http://` thì xem khả năng h2c/upgrade. Không suy luận ALPN cho cleartext.
5. **Kiểm tra origin/gateway:** phía server/CDN có công bố `h2` không? Cấu hình TLS termination có khác giữa domain, port hoặc route không?
6. **Kiểm tra proxy của tiến trình Java:** môi trường dev, CI, container và production có thể dùng proxy khác nhau. Cùng URL có thể cho kết quả khác.
7. **Kiểm tra redirect:** nếu auto-follow, ghi từng hop hoặc tắt follow để đo endpoint đầu; server cuối có thể là origin khác.
8. **So sánh bằng client HTTP độc lập** chỉ như dữ kiện bổ sung: nhiều công cụ hỗ trợ hiển thị negotiated protocol. Kết quả công cụ khác không thay thế `response.version()` của **chính Java process** vì proxy/TLS stack khác nhau.
9. **Xem JDK/runtime và chính sách bảo mật:** dùng JDK 11 được cập nhật bản vá, không giả định mọi patch/JDK vendor/proxy có hành vi hoàn toàn giống nhau.
10. **Kiểm chứng hiệu năng/bất thường:** số kết nối, stream, retry, timeout, 4xx/5xx, server latency, network loss; đừng kết luận chỉ từ một dòng version.

Nếu ứng dụng chạy sau ingress/mesh, hãy mô tả rõ **hop cần kiểm tra**. Nói “hệ thống đang dùng HTTP/2” mà không chỉ ra hop rất dễ gây hiểu lầm.

## 14. Hiệu năng: lợi ích của HTTP/2 không tự động xuất hiện

HTTP/2 có thể giảm chi phí nhiều request qua multiplexing và nén header, nhất là nhiều request đồng thời đến cùng origin. Nhưng thời gian hoàn thành còn phụ thuộc:

- DNS, TCP connect, TLS handshake và connection reuse.
- Số stream và policy của server/proxy, congestion control và chất lượng mạng.
- Kích thước response, compression của **body**, cache, database và thời gian xử lý backend.
- Số lượng request thực sự được gửi đồng thời. Code `send()` trong vòng for tuần tự không tự trở thành tải song song chỉ vì dùng H2.
- HTTP/2 stream flow control/backpressure, giới hạn kết nối, memory, timeout và retry.
- Đường truyền TCP: mất gói có thể làm các stream cùng kết nối bị ảnh hưởng, dù H2 giải quyết hạn chế của HTTP/1.1 ở tầng ứng dụng.

Khi thử nghiệm, giữ đồng nhất endpoint/payload/network, đo **p50/p95/p99 latency**, throughput, timeout rate và tài nguyên client/server. So sánh H1.1/H2 trên cùng hạ tầng và cấu hình, warm-up hợp lý, xem cả trường hợp nhiều request nhỏ và response lớn. Không khẳng định một protocol luôn nhanh hơn chỉ từ vài lượt thử.

**Không cố ép HTTP/2 để sửa lỗi API chậm** khi bottleneck thực nằm ở SQL, backend queue, tải CPU hoặc payload lớn. Chọn version là một thành phần của thiết kế, không phải thay thế performance profiling.

## 15. Kiểm thử với JUnit và test server

### 15.1. Unit test các preference không cần mạng

Khi dự án đã cấu hình **JUnit Jupiter 5.x tương thích JDK 11**, có thể kiểm thử ý nghĩa của các builder ngay lập tức. Ví dụ file `HttpVersionPreferenceTest.java`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class HttpVersionPreferenceTest {
    @Test
    void java11DefaultClientPrefersHttp2() {
        HttpClient client = HttpClient.newHttpClient();
        assertEquals(HttpClient.Version.HTTP_2, client.version());
    }

    @Test
    void requestWithoutOverrideDefersToClient() {
        HttpRequest request = HttpRequest.newBuilder(
            URI.create("https://example.com/")).GET().build();
        assertFalse(request.version().isPresent());
    }

    @Test
    void perRequestOverrideIsVisible() {
        HttpRequest request = HttpRequest.newBuilder(
            URI.create("https://example.com/"))
            .version(HttpClient.Version.HTTP_1_1)
            .GET().build();
        assertEquals(HttpClient.Version.HTTP_1_1,
            request.version().orElseThrow());
    }
}
~~~

Đây là **lớp test hoàn chỉnh khi dự án đã có dependency JUnit Jupiter và test runner của Maven/Gradle**, không phải file Java tự chạy chỉ bằng JDK. Ba test trên **không gửi mạng**, nên không nên kiểm tra actual negotiated version: chưa có response nào để hỏi.

### 15.2. Integration test để xác nhận actual

Dùng **test server HTTP/1.1** như chương trình `HttpVersionDemo`, gửi request thực và assert:

~~~java
assertEquals(HttpClient.Version.HTTP_1_1, response.version());
assertEquals(200, response.statusCode());
~~~

Đây là **đoạn assertion minh họa**, với `response` đã được nhận từ local server. Dùng `@BeforeEach`/`@AfterEach` hoặc fixture quản lý vòng đời server/port. Đừng chạy integration test phụ thuộc một website công cộng rồi ép kết quả lúc nào cũng `HTTP_2`; hạ tầng bên ngoài, CDN, proxy và network không thuộc quyền kiểm soát của unit test.

Để kiểm chứng **HTTP/2 thật**, cần một HTTPS server/test fixture có TLS/ALPN và hỗ trợ H2 được cấu hình rõ, trust store/certificate test phù hợp, và test `response.version()==HTTP_2`. JDK `HttpServer` nhỏ trong ví dụ này **không phải một HTTP/2 test server**; không dùng nó để “kiểm thử thương lượng h2 thành công”.

### 15.3. Những case quan trọng

| Case | Điều cần xác minh |
| --- | --- |
| Default client | `client.version()==HTTP_2`; đó là preference. |
| Request không override | `request.version().isEmpty()`; kế thừa client lúc gửi. |
| Request override H1.1 | `request.version()==Optional.of(HTTP_1_1)`. |
| Local H1.1 server | `response.version()==HTTP_1_1`, bất kể client có prefer H2. |
| HTTPS H2 fixture | `response.version()==HTTP_2` nếu fixture thật sự hỗ trợ H2/ALPN. |
| Endpoint fallback | Không crash chỉ vì không đạt H2 nếu hợp đồng cho phép H1.1. |
| Redirect qua origin khác | Actual version gắn với response từng hop. |
| Kết nối timeout/TLS error | Không có response.version, lỗi được phân loại; không giả mạo actual. |
| POST với side effect | Không retry tự động chỉ vì actual H1.1 khi đã nhận response. |

## 16. Những lỗi lập trình và cách sửa

| Cách làm sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `client.version()==HTTP_2` → log “HTTP/2 used” | Đây là preference, không phải actual. | Log `response.version()` sau khi nhận response. |
| `request.version().isEmpty()` → kết luận H1.1 | Empty chỉ nghĩa là không đặt override. | Xem `client.version()` và `response.version()`. |
| Set `version(HTTP_2)` rồi giả định bắt buộc H2 | Server/proxy/ALPN có thể fallback. | Chấp nhận H1.1 hoặc kiểm tra actual nếu hợp đồng đòi H2. |
| Dùng status 200 làm chứng cứ HTTP/2 | Status và version độc lập. | Đọc cả `statusCode` lẫn `version`. |
| Gắn header “ALPN”, “Upgrade” tùy ý để ép H2 | Sai tầng giao thức/có header bị hạn chế. | Để HttpClient và TLS stack thương lượng đúng cách. |
| Vô hiệu hóa certificate validation để “bật H2” | Mở rủi ro MITM và che lỗi TLS thật. | Sửa trust store/certificate/cấu hình endpoint an toàn. |
| Ghi actual=HTTP_1_1 khi send ném exception | Không có response nào để kiểm chứng. | Ghi error category và actual=unknown/no_response. |
| Mặc định client→backend và proxy→backend cùng version | Các hop có thể thương lượng khác. | Đo tại từng hop bằng telemetry riêng. |
| Cho rằng H2 tự nén body | HPACK liên quan header, không phải payload. | Xử lý `Content-Encoding` riêng. |
| Retry POST vì response dùng H1.1 | Request có thể đã hoàn thành side effect. | Thiết kế idempotency/retry policy theo nghiệp vụ. |
| Dùng HTTP_3 trong code JDK 11 | Enum Java 11 chỉ có HTTP_1_1 và HTTP_2. | Giữ target Java 11 hoặc nâng JDK sau khi đánh giá yêu cầu. |
| Tạo HttpClient mới liên tục để “thử H2” | Mất lợi ích reuse kết nối/cấu hình. | Dùng lại client theo lifecycle phù hợp, đo từ response. |

## 17. Bài tập áp dụng

**Bài 1 — dự đoán:** Một client có `version(HTTP_2)`, request override `HTTP_1_1`, server chỉ H1.1. Hãy dự đoán `client.version()`, `request.version()`, `response.version()`. **Đáp án:** `HTTP_2`; `Optional.of(HTTP_1_1)`; `HTTP_1_1`.

**Bài 2 — không override:** Request không gọi `version(...)`, client prefer H2, server H1.1. Tại sao `request.version().isEmpty()` là `true` mà `response.version()==HTTP_1_1`? **Gợi ý:** empty ở request là “kế thừa preference”, actual do kết nối/endpoint quyết định.

**Bài 3 — chạy offline:** Chạy `HttpVersionDemo.java`, đối chiếu bảy dòng stdout. Thay client preference bằng `HTTP_1_1` và giải thích dòng nào đổi; quan sát response vẫn H1.1.

**Bài 4 — HTTPS probe:** Biên dịch `HttpsVersionProbe.java`, chạy với một HTTPS endpoint được phép truy cập. Ghi actual version, status và redirect policy. Thử một endpoint khác hoặc mạng khác; không coi sự khác nhau là lỗi chương trình nếu server/proxy không giống nhau.

**Bài 5 — proxy:** Vẽ đường client → CDN → reverse proxy → backend, với H2 ở hop đầu và H1.1 ở hop sau. Chỉ ra log nào đủ để khẳng định từng hop dùng version nào. Giải thích vì sao `HttpResponse.version()` không chứng minh version của backend.

**Bài 6 — tải đồng thời:** Gửi N GET request tới cùng service test với `sendAsync` và đo thời gian/timeout trên H1.1 và H2, giữ các điều kiện so sánh công bằng. Thảo luận vì sao không nhất thiết H2 nhanh hơn ở mọi trường hợp.

**Bài 7 — kiểm tra bảo mật:** Một API nội bộ yêu cầu HTTPS và H2. Hãy đề xuất cách phát hiện fallback ở health-check, cách báo lỗi khi server chỉ H1.1, và tại sao không được retry request ghi dữ liệu chỉ vì response đã dùng H1.1.

**Bài 8 — lỗi thương lượng:** Chương trình nhận `SSLHandshakeException` trước khi có response. Có nên báo “server chỉ hỗ trợ HTTP/1.1”? **Không.** Đây là lỗi TLS; cần phân tích certificate, protocol, proxy và handshake trước khi kết luận về khả năng H2.

## 18. Checklist vận hành

Trước khi chốt cấu hình HTTP version:

1. Đã phân biệt **client preference**, **request preference** và **response actual** trong code/log chưa?
2. Có xác định đúng URL, scheme HTTPS/HTTP, origin và proxy trung gian không?
3. Nếu yêu cầu H2, endpoint có thực sự hỗ trợ ALPN `h2` và một test đã kiểm chứng response actual chưa?
4. Nếu fallback H1.1, nghiệp vụ có cho phép không? Nếu không, phát hiện và xử lý ở chỗ nào để không tạo side effect trùng?
5. Đã cấu hình connect timeout, request timeout và xử lý lỗi TLS/I/O có giữ cause/chính sách retry đúng chưa?
6. Nếu redirect, có xác minh version của response cuối và các hop cần thiết không?
7. Đã dùng lại HttpClient phù hợp, tránh tạo kết nối không cần thiết và xem xét backpressure khi concurrency cao chưa?
8. Đã đo latency, throughput và lỗi thực tế thay vì phỏng đoán từ protocol name chưa?
9. Có test H1.1 offline ổn định và H2 fixture phù hợp khi cần bắt buộc H2 không?
10. Đã tránh tiết lộ raw URL/token/header nhạy cảm trong telemetry chưa?

## 19. Tài liệu chính thức và ghi nhớ

- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): preference mặc định HTTP_2, cách dùng client.
- [Java SE 11 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `version(...)` yêu cầu version nơi có thể, fallback và ràng buộc proxy.
- [Java SE 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): override preference cho từng request.
- [Java SE 11 — HttpRequest](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html): `version()` trả `Optional`, empty nghĩa là kế thừa.
- [Java SE 11 — HttpResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `version()` là phiên bản thực tế, `statusCode()` và `previousResponse()`.
- [Java SE 11 — HttpClient.Version](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Version.html): enum `HTTP_1_1` và `HTTP_2`.
- [JEP 321 — HTTP Client API](https://openjdk.org/jeps/321): API chính thức hóa trong JDK 11.

**Ghi nhớ quan trọng nhất:** `client.version()` chỉ phản ánh HTTP version **được ưu tiên**; `request.version()` chỉ nói có override hay không; **`response.version()` mới phản ánh phiên bản HTTP đã dùng thực tế**. Java 11 mặc định ưu tiên HTTP/2 nhưng vẫn có thể trao đổi HTTP/1.1, nhất là khi server/proxy không hỗ trợ H2. Với HTTPS, hiểu TLS/ALPN và từng hop; dùng quan sát và kiểm thử thay cho giả định rằng một cấu hình đồng nghĩa với một giao thức đã được thương lượng.