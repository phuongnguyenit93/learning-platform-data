# Phiên bản HTTP mong muốn khác với phiên bản phản hồi thực tế trong Java HttpClient

## 1. Vấn đề cốt lõi: yêu cầu HTTP/2 nhưng server trả HTTP/1.1 có phải lỗi?

Trong Java `java.net.http.HttpClient`, khi viết:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

bạn đang thiết lập **phiên bản HTTP được ưu tiên/yêu cầu nếu có thể (preferred version)**, **không** ký một hợp đồng bảo đảm mọi request đều được trao đổi bằng HTTP/2.

Nếu kết nối hoặc máy chủ không dùng được HTTP/2 trong tình huống đó, Java HttpClient **có thể dùng HTTP/1.1** và trả về `HttpResponse` bình thường. Chẳng hạn:

~~~text
Mong muốn của client: HTTP_2
Phiên bản response: HTTP_1_1
HTTP status: 200
Body: local-ok

=> Đây có thể là fallback hợp lệ, KHÔNG tự đồng nghĩa lỗi.
~~~

Quan trọng nhất là phân biệt **ba giá trị**:

1. `HttpClient.version()`: **mức ưu tiên cấu hình ở client**, mặc định Java 17 là `HTTP_2`.
2. `HttpRequest.version()`: một `Optional<HttpClient.Version>` chứa **ưu tiên ghi riêng trên request**, hoặc empty khi để request kế thừa thiết lập của client.
3. `HttpResponse.version()`: **phiên bản HTTP thực tế được dùng cho response đó**, chẳng hạn `HTTP_1_1` hoặc `HTTP_2`.

Trong ngữ cảnh bài học **Java Advance - networking → HttpClient**, tiêu đề **“Phiên bản HTTP mong muốn khác với phiên bản phản hồi thực tế”** nhắc bạn không lấy cấu hình mong muốn làm bằng chứng đàm phán giao thức đã thành công. **Quan sát `response.version()` mới cho biết version thực tế của response đã nhận.**

Bài sử dụng **API Java 17+ ở mức tương thích Java 17**. Với Java 17, enum `HttpClient.Version` có `HTTP_1_1` và `HTTP_2`; các JDK mới hơn có thể bổ sung phiên bản/giao thức, nên luôn đọc tài liệu theo **JDK mục tiêu**, không suy diễn rằng một enum tại Java 17 là danh sách vĩnh viễn.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích nghĩa chính xác của **preferred/requested HTTP version**, **actual response version**, **fallback** và **protocol negotiation**.
- Hiểu ưu tiên `HttpClient.Builder.version(...)` và `HttpRequest.Builder.version(...)`, kể cả trường hợp request không thiết lập version.
- Đọc `client.version()`, `request.version()` và `response.version()`; tránh so sánh sai `Optional` với enum.
- Giải thích vì sao HTTPS thường dùng **TLS ALPN** để thương lượng HTTP/2, còn HTTP thường có thể thử **HTTP/1.1 Upgrade (h2c)**, với kết quả tùy server/proxy.
- Phân biệt HTTP/1.1 fallback với lỗi **TCP, DNS, TLS, HTTP status 4xx/5xx**, và với việc chuyển HTTPS thành HTTP không bảo mật.
- Biết vì sao **server, proxy, HTTPS endpoint, connection reuse, redirect** có thể ảnh hưởng version thật.
- Kiểm tra từng `HttpResponse.version()` thay vì dựa vào `HttpClient.version()` để đưa ra metric hoặc áp policy.
- Chạy **hai ví dụ Java 17** trên loopback: HTTP/2 preference → HTTP/1.1 actual; request-level override và `sendAsync`.
- Thiết kế chính sách “HTTP/2 **bắt buộc**” phù hợp, hiểu rằng kiểm tra version **sau response** không ngăn được request đã gửi.
- Đọc log/troubleshoot khi kỳ vọng và thực tế khác nhau, không retry mù quáng request có side effect.

## 3. Một request có những version nào?

### 3.1. Phân biệt cấp cấu hình và cấp trao đổi

~~~text
HttpClient.Builder
    .version(HTTP_2)             (A) default preference của client
        |
        v
HttpClient client
    .version() -> HTTP_2
        |
        +--------+-------------------------------------------+
        |                                                    |
        v                                                    v
HttpRequest req1                                     HttpRequest req2
  không gọi .version(...)                            .version(HTTP_1_1)
  req1.version() -> Optional.empty                   req2.version() -> Optional[HTTP_1_1]
  => kế thừa preferred HTTP_2                         => ưu tiên riêng HTTP_1_1
        |                                                    |
        v                                                    v
  client.send(req1, ...)                               client.send(req2, ...)
        |                                                    |
        +----------------------+-----------------------------+
                               |
                  negotiation / routing / proxy
                               |
                               v
                    HttpResponse<?> resp
                    resp.version() -> ACTUAL VERSION
                      HTTP_1_1 hoặc HTTP_2
~~~

**Không** có phép suy luận chung `client.version() == response.version()`. Có thể đúng, có thể khác; API nói rõ client/request **đề nghị một version nếu khả thi**, còn response mang version **đã dùng**.

### 3.2. Bảng chọn đúng API

| API Java 17 | Kiểu trả về / tham số | Giá trị đó nói lên điều gì? |
| --- | --- | --- |
| `HttpClient.newBuilder().version(HTTP_2)` | Builder setting | Mức ưu tiên ở cấp client |
| `HttpClient.newHttpClient()` | HttpClient | Mặc định ưu tiên HTTP/2 ở Java 17 |
| `client.version()` | `HttpClient.Version` | Preferred version của client, **không phải version giao tiếp gần nhất** |
| `HttpRequest.newBuilder(uri).version(HTTP_1_1)` | Builder setting | Preferred version riêng của request |
| `request.version()` | `Optional<HttpClient.Version>` | Optional **ghi trên request**; empty nghĩa là dùng client preference |
| `client.send(request, handler)` | `HttpResponse<T>` | Trả response sau khi giao tiếp thành công ở cấp I/O; status có thể 4xx/5xx |
| `client.sendAsync(request, handler)` | `CompletableFuture<HttpResponse<T>>` | Response bất đồng bộ, cùng nguyên tắc chọn HTTP version |
| `response.version()` | `HttpClient.Version` | **Version thực tế đã dùng cho response này** |
| `response.statusCode()` | `int` | HTTP status code, **khác version** |
| `response.uri()` | `URI` | URI thực sự của response, có thể khác URI ban đầu do redirect |
| `response.previousResponse()` | `Optional<HttpResponse<T>>` | Response trung gian do redirect/authentication; có thể có version khác |
| `response.request()` | `HttpRequest` | Request tương ứng với response này; sau redirect có thể không phải request đầu tiên |

Tất cả ba `version()` liên quan client/request/response **không phải cùng một phương thức** về semantics:

~~~java
HttpClient.Version wantByClient = client.version();
Optional<HttpClient.Version> wantByRequest = request.version();
HttpClient.Version actual = response.version();
~~~

Đây là **mảnh code** cần các biến `client`, `request`, `response` đã tạo từ request thật và import `java.net.http.*`, `java.util.Optional`. Nếu chưa nhận được response vì DNS/TLS/connect lỗi, **không có** `response.version()` để lấy — đừng sinh ra một version “actual” giả.

### 3.3. Thứ tự ưu tiên khi request có override

- Nếu `request.version().isEmpty()`, request dùng preferred version của **`HttpClient`** gửi nó.
- Nếu `request.version()` có giá trị, **giá trị đó là preferred version của request**, thay cho preference client trong lần gửi này.
- Cả hai chỉ là **preference**, không phải kết quả bắt buộc của negotiation.
- `HttpResponse.version()` cho biết lựa chọn thực sự của lần trao đổi/response; nếu version này không như mong muốn, **API vẫn có thể trả response bình thường**.

Ví dụ:

~~~text
Client preferred | Request override | Effective preferred | Actual response
-----------------|------------------|---------------------|----------------
HTTP_2           | empty            | HTTP_2              | HTTP_2 (nếu hỗ trợ)
HTTP_2           | empty            | HTTP_2              | HTTP_1_1 (fallback)
HTTP_2           | HTTP_1_1         | HTTP_1_1            | HTTP_1_1 (thường gặp)
HTTP_1_1         | HTTP_2           | HTTP_2              | HTTP_2 (nếu hỗ trợ)
HTTP_1_1         | HTTP_2           | HTTP_2              | HTTP_1_1 (fallback)
~~~

Các hàng là **tình huống có thể xảy ra**, không phải kết quả bảo đảm độc lập với server/OS/proxy/JDK. Đừng cho rằng gọi `.version(HTTP_2)` khiến máy chủ HTTP/1.1 bắt buộc phải dùng HTTP/2 hoặc sinh lỗi.

## 4. Tại sao HTTP/2 mong muốn lại có HTTP/1.1 thực tế?

### 4.1. Server chỉ hỗ trợ HTTP/1.1

Trường hợp dễ hiểu nhất: client đề nghị HTTP/2 nhưng origin server chỉ triển khai HTTP/1.1.

~~~text
Java HttpClient
  preferred = HTTP_2
       |
       | HTTP/2 capable request / attempted negotiation
       v
HTTP/1.1-only server
       |
       | HTTP/1.1 200 OK
       v
Java HttpResponse
  version() = HTTP_1_1
  statusCode() = 200
~~~

**Không có lỗi ứng dụng bắt buộc phải xảy ra.** HTTP semantics như GET/POST, URI, status, headers và body vẫn có thể được thực hiện bằng HTTP/1.1. Khác biệt chủ yếu ở framing và những tính năng version-specific như HTTP/2 stream multiplexing.

Trong phần thực hành, dùng `com.sun.net.httpserver.HttpServer` của JDK với HTTP/1.1 để **tạo hoàn cảnh có thể tái hiện** trên loopback, không phụ thuộc website công khai, certificate hay proxy doanh nghiệp.

### 4.2. HTTPS và TLS ALPN

Với **HTTPS qua TCP/TLS**, HTTP/2 thường được thương lượng trong **TLS handshake** qua ALPN (*Application-Layer Protocol Negotiation*). Client có thể công bố giao thức như `h2` và `http/1.1`, server chọn giao thức mà hai phía hỗ trợ theo quy tắc triển khai.

~~~text
Client muốn HTTP/2
    |
    v
TCP connect -> TLS handshake + ALPN
    |
    +--> h2 được chọn           -> HTTP/2 frames -> response.version()=HTTP_2
    |
    +--> http/1.1 được chọn     -> HTTP/1.1      -> response.version()=HTTP_1_1
    |
    +--> handshake/TLS lỗi      -> IOException/TLS exception, KHÔNG có response
~~~

**HTTP/1.1 fallback qua HTTPS không tự động có nghĩa mất TLS**. Connection vẫn có thể dùng TLS hợp lệ; **HTTP version** và **TLS version** là hai thước đo khác nhau. Ví dụ `HTTP_1_1` trên TLS 1.3 vẫn có thể là HTTPS được bảo vệ đầy đủ, tùy kiểm tra certificate và cấu hình bảo mật.

Ngược lại, `HTTP_2` không tự chứng minh certificate đúng hoặc client đã kiểm tra quyền truy cập. TLS security phải được đánh giá riêng; HTTP/2 preference không thay authorization hoặc chính sách TLS.

### 4.3. HTTP không mã hóa (h2c upgrade)

Với URI `http://`, HTTP/2 trên cleartext còn được gọi là **h2c**. Java HttpClient khi ưu tiên HTTP/2 có thể **thử nâng cấp (upgrade)** từ HTTP/1.1 sang HTTP/2 theo khả năng triển khai, chẳng hạn dùng cơ chế `Upgrade`. Nếu máy chủ không chấp nhận upgrade, request/response **có thể tiếp tục bằng HTTP/1.1**.

~~~text
Java client -> HTTP/1.1 request kèm cơ chế đề nghị nâng cấp
                  |
                  v
          Server hỗ trợ HTTP/2 upgrade?
                  |
        +---------+-----------+
        |                     |
       có                   không
        |                     |
        v                     v
      HTTP/2               HTTP/1.1
  response.version()    response.version()
     = HTTP_2              = HTTP_1_1
~~~

Đây là mô hình khái niệm. Wire-level thực tế có nhiều điều kiện về upgrade, connection reuse, server/proxy và request. Không nên tự viết header `Upgrade` hoặc `HTTP2-Settings` bằng tay trong `HttpRequest.Builder` rồi nghĩ đã triển khai đúng HTTP/2; dùng HTTP stack.

**Cảnh báo:** `h2c` không có TLS, nên **không** phù hợp truyền nội dung nhạy cảm trên mạng không tin cậy chỉ vì tên chứa “HTTP/2”. Khi muốn HTTPS, URI phải là `https://` và certificate được kiểm tra đúng.

### 4.4. Proxy hoặc gateway làm giới hạn version

Một request có thể đi qua forward proxy hoặc reverse proxy. Java HttpClient có thể không hỗ trợ một kiểu HTTP/2 cụ thể qua proxy, hoặc proxy chỉ giao tiếp bằng HTTP/1.1 ở một hop.

~~~text
HttpClient (prefer h2) --proxy/route--> origin
             |
     proxy capability / route
             v
      response HTTP/1.1 vẫn hợp lệ
~~~

**Đừng suy diễn** rằng version của client-to-proxy, client-to-origin và proxy-to-backend luôn giống nhau. `HttpResponse.version()` mô tả version được sử dụng cho **response mà Java client nhận**, không chứng minh backend phía sau reverse proxy dùng version gì.

Một cấu hình corporate proxy, VPN, gateway hoặc service mesh có thể làm khác kết quả so với gọi trực tiếp. Điều tra phải ghi rõ **đường đi thật của request**, không chỉ nhìn một server-side setting.

### 4.5. Connection reuse và mỗi request không giống nhau

`HttpClient` có thể giữ và tái sử dụng các kết nối. Negotiation là thuộc tính của **kết nối/đường đi**, không phải “mỗi lần `send` gọi là HTTP/2 handshake mới”.

Các request cùng client nhưng khác origin, khác proxy, redirect, server instance hoặc thời điểm có thể cho **response versions khác nhau**. Điều đó không nhất thiết do method GET/POST khác. Cần ghi log theo từng response, bao gồm URI/authority và các thông tin tuyến phù hợp.

Nếu response B có version giống response A, cũng không đủ chứng minh B đã tái sử dụng cùng một TCP connection. `response.version()` **không** phải connection ID.

## 5. HTTP/1.1 và HTTP/2 khác nhau ở đâu, còn gì giữ nguyên?

| Thuộc tính | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| HTTP semantics | Method, target URI, status, headers, representation | Vẫn giữ những semantics chung |
| Framing trên wire | Dòng mở đầu, headers dạng text, quy tắc length/chunked | Binary frames và logical streams |
| Header compression | Không dùng HPACK | Dùng HPACK |
| Multiplex nhiều exchanges trên một connection | Không có stream multiplexing tương đương HTTP/2 | Nhiều streams song song trên một TCP connection |
| TCP transport | Phổ biến, có thể có TLS | Phổ biến qua TLS/TCP, có h2c trên cleartext trong một số triển khai |
| Connection reuse | Có (persistent connections) | Có, với multiplexing |
| Head-of-line blocking | Hạn chế do exchanges trên h1 connection | Còn TCP-level head-of-line blocking |
| HTTP status `200`/`404` | Có | Có |
| Java 17 HttpClient.Version | `HTTP_1_1` | `HTTP_2` |

Một request GET trả 200 bằng HTTP/1.1 **không mặc nhiên là ít đúng hơn** GET trả 200 bằng HTTP/2. Nhưng nếu sản phẩm cần **tính năng đặc thù HTTP/2** (ví dụ nhiều streams đồng thời trên một connection, một số gRPC deployment), fallback có thể làm sai giả định của **hạ tầng/giao thức ứng dụng**. Khi đó cần policy rõ thay vì tin configuration.

**HTTP/3 ở Java đời mới:** Java 17 không có enum `HttpClient.Version.HTTP_3` và bài lab dùng Java 17. Các JDK tương lai hoặc hiện đại hơn có thể thêm hỗ trợ HTTP/3; hãy đọc `HttpClient.Version` của phiên bản JDK triển khai thay vì dùng tài liệu Java 17 để kết luận mọi JDK đều chỉ hỗ trợ 1.1/2.

## 6. Thực hành 1: preferred HTTP/2, actual HTTP/1.1 — chương trình Java 17+

### 6.1. Mục tiêu demo

Chương trình dưới đây:

1. Tạo một HTTP/1.1-only server bằng module chuẩn `jdk.httpserver`, bind địa chỉ `127.0.0.1` với port `0` để OS chọn cổng trống.
2. Tạo `HttpClient` với `version(HTTP_2)`.
3. Gửi request GET **không có override** để quan sát `request.version().isPresent() == false`.
4. Đọc `HttpResponse.version()` và `statusCode()`. Server trả `200` cùng body `local-ok`.
5. Gửi request thứ hai **chỉ định HTTP_1_1**; response thực tế HTTP/1.1.
6. Gửi request thứ ba **chỉ định HTTP_2**; server vẫn HTTP/1.1 nên actual còn là HTTP/1.1.
7. Dừng server trong `finally` và không yêu cầu Internet.

**Tệp: `PreferredVsActualHttpVersion.java`**

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class PreferredVsActualHttpVersion {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/version", exchange -> {
            try (exchange) {
                byte[] payload = "local-ok".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "text/plain");
                exchange.sendResponseHeaders(200, payload.length);
                exchange.getResponseBody().write(payload);
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/version");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpRequest inherited = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();
            HttpResponse<String> first = client.send(
                    inherited, HttpResponse.BodyHandlers.ofString());

            System.out.println("Client preferred: " + client.version());
            System.out.println("Request override present: " +
                    inherited.version().isPresent());
            System.out.println("Response actual: " + first.version());
            System.out.println("HTTP status: " + first.statusCode());
            System.out.println("Body: " + first.body());

            HttpRequest explicitH1 = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_1_1)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();
            HttpResponse<Void> second = client.send(
                    explicitH1, HttpResponse.BodyHandlers.discarding());
            System.out.println("Request preferred: " +
                    explicitH1.version().orElseThrow());
            System.out.println("Second response actual: " + second.version());

            HttpRequest explicitH2 = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_2)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();
            HttpResponse<Void> third = client.send(
                    explicitH2, HttpResponse.BodyHandlers.discarding());
            System.out.println("H2 requested, response actual: " +
                    third.version());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch bằng API Java 17 và chạy:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver PreferredVsActualHttpVersion.java
java --add-modules jdk.httpserver PreferredVsActualHttpVersion
~~~

**Stdout được kiểm chứng khi chạy với OpenJDK 24 và biên dịch `--release 17`:**

~~~text
Client preferred: HTTP_2
Request override present: false
Response actual: HTTP_1_1
HTTP status: 200
Body: local-ok
Request preferred: HTTP_1_1
Second response actual: HTTP_1_1
H2 requested, response actual: HTTP_1_1
~~~

### 6.2. Phân tích sâu đầu ra

- `Client preferred: HTTP_2` đọc từ `client.version()`, **không phải** thành công của negotiation.
- `Request override present: false` chứng minh request đầu **không có .version(...) riêng**; nên lấy preference từ client.
- `Response actual: HTTP_1_1` là dữ kiện thật: ở exchange đầu, client đã dùng HTTP/1.1 cho response, dù cấu hình thích HTTP/2.
- `HTTP status: 200` và `Body: local-ok` cho thấy request vẫn xử lý thành công. **Version mismatch không tự tương đương failure.**
- Request thứ hai chọn `HTTP_1_1` riêng; response là HTTP/1.1 như dự kiến.
- Request thứ ba chọn `HTTP_2` riêng, nhưng server chỉ hỗ trợ HTTP/1.1; response vẫn là HTTP/1.1. Đây là bằng chứng **request-level preference cũng không phải hard requirement**.

**Vì sao kết quả tái hiện được?** Module `jdk.httpserver` cung cấp HTTP server nhúng dùng HTTP/1.1; client kết nối tới server nội bộ. Không có proxy ngoài, TLS, DNS công khai hoặc hạ tầng cần cài đặt.

### 6.3. Giới hạn của ví dụ

- Đây là lab **HTTP không mã hóa trên loopback** để kiểm chứng negotiation/version, không phải mô hình gửi credential qua Internet.
- Nếu OS hoặc sandbox chặn mở listening TCP socket, ví dụ có thể thất bại vì quyền mạng; môi trường Java 17 với loopback bình thường có thể chạy.
- Không rút ra rằng server nào cũng fallback, hoặc mọi JDK đưa ra HTTP/1.1 ở mọi request HTTP/2. **Bản chất bài học là đọc `response.version()`.**
- `HttpServer` là server nhúng tối giản thích hợp cho demo/kiểm thử, không tự cung cấp toàn bộ tính năng của một production server.
- `HttpClient` ở **Java 17** không có `close()`/`AutoCloseable` theo API Java 17; không nên dùng mẫu `try (HttpClient client = ...)` khi mục tiêu là tương thích `--release 17`.
- `send(..., BodyHandlers.discarding())` vẫn đợi/trả response; chỉ **bỏ qua body**, không chứng minh thiếu HTTP response hoặc lỗi status.
- `server.stop(0)` kết thúc server của demo trong `finally` để không để lại listener.

## 7. Thực hành 2: request override, sendAsync và policy cần HTTP/2

### 7.1. Mục tiêu

Ví dụ thứ hai minh họa hai hiểu nhầm thực tế:

- Client ưu tiên HTTP/1.1, **một request riêng** ưu tiên HTTP/2. Request preference thắng preference client trong lần gửi.
- `sendAsync()` **không** khiến phiên bản HTTP trở nên mặc định là HTTP/2. Nó chỉ thay cách ứng dụng chờ **HTTP response**, chứ không thay quyền năng negotiation.

Khi response thực tế là HTTP/1.1, code tính cờ `strict HTTP/2 satisfied` là false. Đây là **kiểm tra sau response**, không thể quay ngược thời gian để ngăn server đã nhận GET.

**Tệp: `PerRequestVersionPolicyDemo.java`**

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class PerRequestVersionPolicyDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/check", exchange -> {
            try (exchange) {
                exchange.sendResponseHeaders(204, -1);
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/check");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_2)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();

            HttpResponse<Void> response = client.sendAsync(
                    request, HttpResponse.BodyHandlers.discarding())
                    .get(6, TimeUnit.SECONDS);

            System.out.println("Client preferred: " + client.version());
            System.out.println("Request preferred: " +
                    request.version().orElseThrow());
            System.out.println("Response actual: " + response.version());
            System.out.println("Status: " + response.statusCode());
            System.out.println("Strict HTTP/2 satisfied: " +
                    (response.version() == HttpClient.Version.HTTP_2));
        } finally {
            server.stop(0);
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver PerRequestVersionPolicyDemo.java
java --add-modules jdk.httpserver PerRequestVersionPolicyDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
Client preferred: HTTP_1_1
Request preferred: HTTP_2
Response actual: HTTP_1_1
Status: 204
Strict HTTP/2 satisfied: false
~~~

### 7.2. Bài học từ phép kiểm tra sau khi gửi

- `request.version().orElseThrow()` trả `HTTP_2` vì builder đã set; `request.version()` **không empty**.
- `response.version()` = `HTTP_1_1` vì server local là HTTP/1.1; đối với server này việc ưu tiên HTTP/2 không dẫn đến 101 upgrade thành công.
- `sendAsync(...)` trả `CompletableFuture<HttpResponse<Void>>`; `get(...)` trong `main` chỉ để demo chờ kết quả, **không** biến async API thành lựa chọn protocol khác.
- `204 No Content` là status HTTP hợp lệ, không có response body; `BodyHandlers.discarding()` chỉ là lựa chọn xử lý body.
- `strict HTTP/2 satisfied: false` là **kết quả policy của ứng dụng**, không phải `HttpClient` tự throw lỗi khi protocol fallback.

**Cảnh báo nghiệp vụ:** nếu đó là POST thanh toán, server có thể đã thực thi thao tác trước khi bạn nhìn thấy `response.version()`. Do đó không nên “thấy version thấp hơn rồi retry POST” mà không có thiết kế idempotency/deduplication. Nếu phiên bản HTTP là yêu cầu bắt buộc trước khi cho phép thao tác nhạy cảm, cần có **kiểm tra khả năng phía server/proxy từ trước và enforcement ở hệ thống nhận**, không chỉ assert trên response sau khi request chạy.

## 8. HTTP status và HTTP version không thể thay thế nhau

Giả sử:

~~~text
Mong muốn HTTP_2 | Actual HTTP_1_1 | Status 200
Mong muốn HTTP_2 | Actual HTTP_2   | Status 404
Mong muốn HTTP_2 | Actual HTTP_1_1 | Status 503
~~~

Ba tình huống trên cần xử lý **khác nhau**:

- **Hàng 1:** request thành công về mặt HTTP status, nhưng dùng version khác mong muốn. Nếu HTTP/2 chỉ là tối ưu hiệu năng, có thể chấp nhận và ghi metric.
- **Hàng 2:** version đúng mong muốn, nhưng server trả 404; ứng dụng phải xử lý tài nguyên/URI/authorization, **không** kết luận vì dùng HTTP/2 nên thành công.
- **Hàng 3:** actual HTTP/1.1 và 503; cần phân tích server availability/rate limiting/gateway, **không** tự kết luận 503 do protocol downgrade.

**Mã lỗi I/O thì khác nữa:**

| Triệu chứng | Có `HttpResponse.version()`? | Chẩn đoán |
| --- | --- | --- |
| `HttpClient` nhận HTTP `200` | Có | Kiểm tra status/body và actual version |
| Nhận HTTP `404`/`500` | Có | Đây vẫn là HTTP response |
| Không resolve DNS | Không | Lỗi DNS/`UnknownHostException`, chưa có HTTP response |
| TCP connect refused/timeout | Không | Lỗi transport/connect, chưa negotiated HTTP exchange |
| TLS certificate/handshake lỗi | Không | Lỗi TLS/SSL; đừng gọi là HTTP/1.1 fallback nếu chưa có response |
| Request timeout trước khi nhận response | Có thể không | Kiểm tra cancellation/deadline; không tự tạo actual version |
| Proxy trả HTTP `502`/`504` | Có nếu nhận được response | Phiên bản phản hồi client có thể khác giao thức upstream |
| Redirect được follow tự động | Có | `version()` ở final response; xem intermediate nếu cần |

**Không** dùng `response.version()==HTTP_2` như thước đo thành công của request: client vẫn phải kiểm tra `statusCode()`, nội dung hợp lệ và business response schema.

## 9. Khi nào thật sự cần ép HTTP version?

### 9.1. Trường hợp chỉ tối ưu hiệu năng

Nhiều REST API hoạt động tốt qua cả HTTP/1.1 và HTTP/2. Nếu đây là tình huống của bạn:

- Đặt `HTTP_2` làm preference.
- Cho phép fallback HTTP/1.1 nếu server/gateway không hỗ trợ h2.
- Ghi metric actual version để đo adoption của HTTP/2 và các yếu tố như proxy/server version.
- Đánh giá latency/throughput trên tải thật: HTTP/2 có multiplexing nhưng một kết nối TCP vẫn có head-of-line blocking khi mất segment.
- **Không** retry request ngay chỉ vì actual version là HTTP/1.1.

Đây là cách phù hợp khi tính năng HTTP/2 là **tối ưu**, không phải hợp đồng nghiệp vụ.

### 9.2. Trường hợp giao thức ứng dụng cần HTTP/2

Một số giao thức/triển khai yêu cầu đặc tính HTTP/2 (ví dụ một số deployment gRPC). Khi đó:

1. **Xác định yêu cầu version ở từng hop**: client-to-edge, edge-to-backend, proxy-to-upstream. `response.version()` của Java client chỉ quan sát **hop/protocol client sử dụng** cho response.
2. **Triển khai server/proxy có HTTP/2 và TLS ALPN thích hợp**; xác thực kết quả trên môi trường staging giống production.
3. **Nếu cần fail closed**, dùng policy tại gateway/server hoặc một cơ chế capability/health preflight đáng tin. Không giả định `HttpClient.Builder.version(HTTP_2)` tự từ chối fallback.
4. Kiểm tra `response.version()` để phát hiện mismatch và log/alert. Phát hiện sau khi gửi chỉ là **postcondition**, không thay precondition.
5. Không thực thi lại thao tác có side effect chỉ vì postcondition mismatch; thiết kế idempotency keys/transaction boundaries.
6. Cân nhắc thư viện đúng giao thức (ví dụ gRPC implementation chính thức) thay vì tự ép Java `HttpClient` và xử lý HTTP/2 frames thủ công.

**Phân biệt cấp độ:** muốn *“prefer h2”* thì `.version(HTTP_2)` phù hợp. Muốn *“h2 or reject before business operation”* thì phải có enforcement thêm ở hạ tầng/giao thức, không chỉ riêng tham số `version`.

### 9.3. Khi nào cố tình ưu tiên HTTP/1.1?

Có thể chọn `HTTP_1_1` để:

- Kiểm thử tương thích với một legacy server hoặc gateway.
- Tách lỗi liên quan HTTP/2 proxy/settings/stream multiplexing.
- Tái hiện production lỗi chỉ xảy ra ở HTTP/1.1.
- Giảm biến số khi dạy cấu trúc request/response text HTTP/1.1.

Ví dụ:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();
~~~

Đây là **mảnh code**, cần `import java.net.http.HttpClient;`. Đừng coi lựa chọn HTTP/1.1 là một bảo đảm về bảo mật hay vấn đề “HTTP/1.1 không cần TLS”. Phiên bản HTTP và HTTPS là hai khái niệm khác.

## 10. Những chỗ thường gây hiểu sai khi debug

### 10.1. Ngộ nhận do method `version()` trùng tên

Các dòng sau **không tương đương**:

~~~java
client.version();     // Preferred trên client
request.version();    // Optional preferred riêng ở request
response.version();   // Actual trên response
~~~

Với request chưa gọi `.version(...)`, `request.version()` trả `Optional.empty()` — không có nghĩa request không dùng giao thức HTTP, không có nghĩa nó mặc định HTTP/1.1. Nó **kế thừa preferred của client** và **version thật vẫn do response quyết định**.

Một lỗi thường gặp:

~~~java
// SAI Ý NGHĨA: điều kiện này chỉ so cấu hình và actual.
boolean h2Guaranteed =
        client.version() == HttpClient.Version.HTTP_2;

// ĐÚNG VỀ KHẢ NĂNG QUAN SÁT response:
boolean thisResponseUsedH2 =
        response.version() == HttpClient.Version.HTTP_2;
~~~

Mảnh mã trên cần `client` và `response` đã có; hai boolean có phạm vi khác nhau. `thisResponseUsedH2` **không** chứng minh server upstream nội bộ dùng HTTP/2 hay tất cả requests cùng client đều dùng h2.

### 10.2. Nhìn `request.version()` thay vì `response.version()`

Request builder chỉ có quyền **đề nghị**; response cho biết **thực tế**. Nếu code phân tích:

~~~java
request.version().orElse(client.version())
~~~

kết quả là **effective preference**. Nó có giá trị để log cấu hình, nhưng **không** thể dùng làm nhãn actual protocol. Để ghi metric:

~~~java
HttpClient.Version wanted =
        request.version().orElse(client.version());
HttpClient.Version actual = response.version();
boolean matched = wanted == actual;
~~~

Đây là **mảnh code** được đặt sau một lần gửi thành công, cần `client`/`request`/`response`. Ghi metric "wanted", "actual" và "matched" rõ ràng, không gom vào một field tên `http_version` gây hiểu nhầm.

### 10.3. Không thiết lập version nhưng vẫn có sự khác biệt

`HttpClient.newHttpClient()` ở **Java 17** có preferred default `HTTP_2`. Vì vậy nếu request không gọi `.version(HTTP_2)` và response vẫn `HTTP_1_1`, đó không nhất thiết là client chưa “bật” HTTP/2. Client có thể đã mặc định thích HTTP/2 nhưng server/hops không đáp ứng.

Mảnh kiểm tra:

~~~java
HttpClient client = HttpClient.newHttpClient();
System.out.println(client.version()); // Java 17: HTTP_2
~~~

Lệnh in trên phản ánh Java 17 spec; không chứng minh request nào đã thực hiện hay đã negotiated HTTP/2.

### 10.4. Thử HTTP/2 qua plain HTTP mà server không nâng cấp

Khi URL `http://localhost:port`, việc HTTP/2 được chọn có thể cần **h2c upgrade**. Nếu server chỉ nói HTTP/1.1, version actual = HTTP/1.1 có thể là hoàn toàn bình thường.

Không nên đem kết quả h2c trên localhost so sánh trực tiếp với website HTTPS production rồi kết luận “Java HttpClient thất thường”. Hai path negotiation khác: **Upgrade vs TLS ALPN**.

### 10.5. Kết quả thay đổi khi bật proxy

Một client có proxy có thể dùng h1 cho một kiểu proxy path không hỗ trợ HTTP/2 dù server đích tự nó có HTTP/2. Vì vậy, log tối thiểu nên chứa:

- Scheme/authority/URI đích phù hợp, đã lược dữ liệu nhạy cảm.
- Effective preferred (client hoặc request).
- Actual `response.version()`.
- Status code.
- Proxy/network route mode (direct/proxy), nếu được phép ghi.
- Redirect final URI và intermediate responses khi cần.
- JDK runtime version (không chỉ compiler `--release 17`).
- TLS/ALPN diagnostics ở môi trường kiểm soát, không log raw tokens/cookies.

**Không** phải bật debug network/TLS quá chi tiết trên production chứa credentials; log có thể phơi metadata và nội dung nhạy cảm.

### 10.6. Redirect làm bạn nhìn nhầm response

Giả sử request đầu tới `https://a.example/path` nhận redirect sang `https://b.example/final`. Client có thể kết nối đến **origin khác**, negotiation khác và response final có version khác response redirect.

Theo Java API:

- `response.uri()` là URI của response hiện tại (có thể khác URI request đầu).
- `response.request()` là request tương ứng với response này (có thể khác request khởi tạo).
- `response.previousResponse()` cung cấp previous/intermediate response (redirect/authentication) nếu có.

Ví dụ diagnostic (mảnh code, `response` là response nhận về):

~~~java
System.out.println("Final URI: " + response.uri());
System.out.println("Final HTTP version: " + response.version());

var earlier = response.previousResponse();
while (earlier.isPresent()) {
    var intermediate = earlier.get();
    System.out.println("Earlier URI: " + intermediate.uri());
    System.out.println("Earlier version: " + intermediate.version());
    earlier = intermediate.previousResponse();
}
~~~

**Mảnh code** cần response `HttpResponse<?>` đã có; không phải chương trình độc lập. Với Java 17 có thể dùng `var` trong local variables. Các intermediate responses này có thể không chứa body như response cuối. Không giả định mọi redirect tự được follow: `HttpClient.Redirect.NEVER` là chính sách redirect mặc định trong Java 17, trừ khi builder được cấu hình khác.

Nếu mục tiêu là log toàn bộ negotiation giữa nhiều origins, cần quan sát từng hop thực tế và có thể thêm tracing ở proxy/server; `HttpResponse.version()` final không tự mô tả mọi kết nối downstream.

## 11. Version mismatch có làm mất tính an toàn của HTTP không?

**HTTP version** và **transport security** không phải một cặp “cao hơn là bảo mật hơn”:

| Trường hợp | Có TLS? | Actual HTTP version | Kết luận |
| --- | --- | --- | --- |
| `https://` dùng TLS 1.3, ALPN chọn `http/1.1` | Có | HTTP/1.1 | Có thể là HTTPS hợp lệ được bảo mật |
| `https://` dùng TLS, ALPN chọn `h2` | Có | HTTP/2 | HTTP/2 trên TLS |
| `http://` cleartext server không nhận h2c | Không | HTTP/1.1 | Không mã hóa do scheme, **không phải** vì version bị fallback |
| `http://` cleartext h2c upgrade thành công | Không | HTTP/2 | HTTP/2 vẫn có thể là cleartext |
| `https://` TLS handshake lỗi | Không hoàn thành | Chưa có HTTP response | Không nên đặt actual HTTP version |

Đừng phản ứng với `HTTP_1_1` bằng cách tắt TLS certificate verification hoặc đổi `https` sang `http`. Đó là **hạ mức bảo mật đường truyền**, hoàn toàn không cần thiết để khắc phục mismatch protocol version.

Nếu cần đảm bảo TLS version/cipher/certificate, kiểm tra bằng chính **TLS/SSL APIs và chính sách xác thực endpoint**; `response.version()` chỉ là **HTTP protocol version**, không phải TLS phiên bản.

## 12. Logging, metric và quan sát protocol version đúng cách

Một mẫu logging ý tưởng:

~~~java
HttpClient.Version preferred =
        request.version().orElse(client.version());
HttpClient.Version actual = response.version();
int status = response.statusCode();

System.out.printf(
    "preferred=%s actual=%s matched=%s status=%d%n",
    preferred, actual, preferred == actual, status);
~~~

Đây là **mảnh code** dùng trong method sau khi nhận response, với `client`, `request`, `response` đã có. Để đánh giá HTTP/2 rollout:

- Tỷ lệ **actual HTTP_2**, tách theo scheme/hostname/proxy và nhóm request (không log token/user ids).
- Số response **preferred HTTP_2 nhưng actual HTTP_1_1**.
- Distribution theo JDK runtime và môi trường network.
- HTTP status/latency đi kèm, nhưng **không gộp mismatch vào lỗi mạng**.
- Số request thực sự bị fail trước khi có response (DNS/connect/TLS), tách khỏi version mismatch.
- Latency p50/p95/p99 dưới workload tương đương, tránh kết luận chỉ từ version label.
- Tính nhất quán với thông tin server/proxy (ALPN, version negotiated, upstream protocol) khi có quyền xem.

`HttpResponse.version()` đo **version của response**, không chứng minh throughput, TCP connection reuse hoặc header compression thực tế. Đừng dùng nó thay việc đo hiệu năng.

### 12.1. Kế hoạch điều tra khi HTTP/2 không xuất hiện

1. **Xác minh kỳ vọng**: `client.version()` có phải `HTTP_2`? Có `request.version()` riêng không?
2. **Lấy actual**: `response.version()` ngay sau `send()` hoặc khi `sendAsync()` hoàn tất.
3. **Tách lỗi**: request có response status/body bình thường hay đã văng exception? Không có response thì không gọi là fallback thành công.
4. **Kiểm tra URL**: `http://` và `https://` thương lượng khác nhau (h2c vs TLS ALPN).
5. **Kiểm tra server hỗ trợ h2**: chứng cứ từ config/log/server capabilities, không chỉ nhìn trang web "chạy được".
6. **Kiểm tra proxy/gateway**: đường đi client thực tế có trung gian nào? HTTP/2 có được hỗ trợ ở hop liên quan không?
7. **Kiểm tra redirect**: `response.uri()` có thay đổi? `previousResponse()` chứa versions của responses trước không?
8. **Kiểm tra JDK/runtime**: Java 17 enum và hành vi có đúng runtime đang chạy? Có đang dùng HTTP client/library khác không?
9. **Kiểm tra connection reuse**: requests cùng origin có thể dùng kết nối đã thương lượng; không giả định mỗi request tự mới handshake.
10. **Đo & quyết định policy**: nếu cần h2 vì tính năng bắt buộc, enforce ở hạ tầng và ứng dụng; nếu chỉ muốn hiệu năng, ghi metric và chấp nhận h1 fallback khi hợp lệ.

Không nên bắt đầu bằng việc **ép thêm header `Connection: Upgrade` vào `HttpRequest`**. Java HttpClient quản lý headers đặc biệt và protocol negotiation; tự làm có thể tạo request sai/chặn bởi JDK.

## 13. Khi nào phải giải quyết vấn đề ở server/proxy, không phải Java code?

| Hiện tượng | Thay đổi phù hợp | Không nên làm |
| --- | --- | --- |
| Server HTTP/1.1-only | Cấu hình/triển khai HTTP/2 ở server hoặc edge nếu cần | Chỉ đặt `version(HTTP_2)` rồi coi h2 chắc chắn |
| HTTPS không thương lượng `h2` | Kiểm tra TLS ALPN và hỗ trợ của hai phía | Tắt xác thực certificate để tìm h2 |
| Proxy chỉ dùng h1 | Kiểm tra proxy support và đường đi | Tưởng client config buộc proxy nâng cấp |
| Redirect sang origin h1 | Quan sát final URI, các intermediate responses | Gắn một version cho toàn bộ chain |
| Chỉ một số requests có h2 | Xem origin/connection/server pool/timing | Kết luận “HttpClient random” chưa có evidence |
| Cần gRPC h2-specific | Dùng stack và infrastructure hỗ trợ HTTP/2 end-to-end | Chỉ check response sau POST quan trọng |
| Mismatch nhưng HTTP status 200 và API ổn | Theo dõi metric và đánh giá có cần điều chỉnh | Retry lại toàn bộ request không cần thiết |
| Có `SSLHandshakeException` | Sửa certificate/TLS protocol trust và endpoint policy | Gọi lỗi TLS là HTTP/1.1 downgrade |
| Có `HTTP_1_1` nhưng latency cao | Phân tích concurrency, connection pooling, proxy, response size | Xem mỗi version label là nguyên nhân duy nhất |

**Tư duy đúng:** chính sách protocol nằm trên **toàn bộ đường đi**, không nằm một mình ở một enum Java.

## 14. Kiểm thử để tránh diễn giải sai

Hãy viết các test có điều kiện rõ:

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Mặc định Java 17 | `HttpClient.newHttpClient()` | `client.version() == HTTP_2` (preferred) |
| Request không override | `newBuilder(uri).GET().build()` | `request.version().isEmpty()` |
| Request override HTTP/1.1 | `.version(HTTP_1_1)` | `request.version().get()==HTTP_1_1` |
| Server h1-only, client thích h2 | Gửi GET tới `jdk.httpserver` | `response.version()==HTTP_1_1`; status vẫn có thể 200 |
| Server h1-only, request thích h2 | Request override HTTP_2 | Actual vẫn HTTP_1_1 |
| Client thích h1, request thích h2 | Request override HTTP_2 | Effective preference h2, actual phụ thuộc server |
| `sendAsync` | `client.sendAsync(...).get()` | Async completion không buộc h2 |
| Server thực sự hỗ trợ h2 TLS | HTTPS + ALPN chọn `h2` | Actual `HTTP_2` khi negotiation thành công |
| ALPN không chọn h2 | Server/proxy không chọn `h2` nhưng có h1 | Actual `HTTP_1_1` nếu fallback hợp lệ |
| TLS handshake failure | Certificate/TLS không hợp lệ | Exception, không có HTTP response version |
| Redirect giữa origins | `followRedirects(...)` được cấu hình | Quan sát final & intermediate versions riêng |
| HTTP status 404 | Response HTTP hợp lệ | `response.version()` vẫn đọc được |
| Policy đòi h2 | `if (resp.version()!=HTTP_2)` | Mismatch được phát hiện **sau request** |
| Client dùng proxy | Cấu hình proxy trong test staging | Version được xác nhận từ actual trên path đó |
| Nhiều responses từ cùng client | Gửi tuần tự tới h1/h2 servers | Không suy mọi response cùng version |

Khi test có HTTPS, tạo server với certificate **test tin cậy** và kiểm soát ALPN; đừng tắt validation trong code chính. Khi test nội bộ qua `http://127.0.0.1`, chỉ đo **version negotiation của môi trường đó**, không suy rộng cho production.

### 14.1. Test không nên phụ thuộc môi trường ngoài

Hai chương trình ở phần 6–7 dùng loopback và server trong JDK, nên:

- Không phụ thuộc website Internet thay đổi chính sách.
- Không phụ thuộc chứng chỉ công khai/proxy/VPN.
- Không cần đo thời gian handshake h2 để xác nhận mục tiêu.
- Có output deterministic theo cách server chỉ hỗ trợ h1.
- Kết luận được **h2 preference != h2 actual**, không kết luận toàn bộ JDK/OS bất kỳ chỉ luôn dùng h1.

Giải thích quan trọng: **sự khác biệt là hành vi được cho phép theo hợp đồng API**, không phải một exception khi client không nhận được HTTP/2.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “`client.version()==HTTP_2` nghĩa là request vừa dùng h2” | `client.version()` chỉ preferred | Dùng `response.version()` |
| “`request.version()` empty nghĩa là h1” | Empty = chưa đặt override | Kế thừa client preference |
| “Request chỉ định HTTP/2 sẽ fail nếu server h1” | `version` là preferred where possible | Client có thể fallback và trả response h1 |
| “`response.version()` cho biết TLS 1.3 hay 1.2” | Đây là HTTP version | Dùng TLS diagnostics riêng |
| “HTTP/1.1 response qua HTTPS chắc chắn không mã hóa” | HTTP version không quyết định scheme/TLS | Kiểm tra HTTPS/SSL |
| “Fallback h1 tự tạo lỗi status 500” | Status độc lập với protocol version | Quan sát `statusCode()` |
| “HTTP 404 là vì server không hỗ trợ h2” | 404 nói về resource/request semantics | Kiểm tra URL/auth/router |
| “Mọi request cùng HttpClient có actual version giống nhau” | Origin/proxy/redirect/reuse khác nhau | Ghi log từng response |
| “`sendAsync` sẽ ưu tiên h2 hơn `send`” | Hai API khác cách chờ kết quả, không quyết định server support | Xem same preference/actual |
| “HTTPS client hỗ trợ h2 thì server tự phải hỗ trợ h2” | Cần ALPN, server/edge setup tương thích | Kiểm tra h2 từng hop |
| “HTTP cleartext dùng ALPN giống HTTPS” | H2c upgrade là cơ chế khác | Phân biệt `http` và `https` |
| “Proxy dùng h1 thì backend chắc chắn h1” | Proxy có thể đổi protocol giữa hops | Quan sát trên từng hop |
| “Nếu `response.version()==HTTP_1_1`, cứ retry POST” | Request có thể đã thực hiện side effects | Không retry mù, có idempotency |
| “Gọi .version(HTTP_2) là strict mode” | Không có lời hứa hard fail trong builder | Policy/enforcement bổ sung |
| “Server HTTP/1.1 trả 200 nghĩa là client không hề thử nâng cấp” | Kết quả chỉ cho biết actual, không toàn bộ sequence negotiation | Xem logs/traces đúng scope |
| “Chạy Java 24 với code Java 17 nghĩa enum hỗ trợ HTTP_3” | `--release 17` giới hạn API compile; runtime có thể khác | Đọc API theo JDK compile/runtime |
| “Java 17 `HttpClient` được try-with-resources” | `HttpClient` Java 17 không là `AutoCloseable` | Không dùng cú pháp try-with-resources đó ở `--release 17` |
| “Kết quả h1 là lỗi TCP” | HTTP/1.1 là protocol hợp lệ | Phân biệt transport errors |
| “Header tự thêm sẽ buộc HTTP/2 handshake” | Negotiation do HTTP stack/proxy/server quản lý | Dùng API/config hạ tầng |
| “Response.version của final mô tả mọi redirect” | Mỗi response có thể thuộc origin/version khác | `previousResponse()` khi cần |
| “Version cao hơn tự có latency tốt hơn mọi request” | Performance phụ thuộc mạng, concurrency, server, head-of-line, cache | Benchmark và telemetry |
| “Response actual h2 chứng minh backend dùng h2” | Có proxy/gateway có thể đổi version | Xác minh backend hop nếu cần |

## 16. Bài tập có lời giải

### Bài 1 — Client thích h2 nhưng h1 trả 200

~~~text
client.version()   = HTTP_2
response.version() = HTTP_1_1
response.statusCode() = 200
~~~

Có nhất thiết phải throw exception?

**Đáp án:** Không. Đây có thể là fallback hợp lệ. Nếu HTTP/2 chỉ là ưu tiên hiệu năng, chấp nhận response và ghi nhận actual version; nếu HTTP/2 là bắt buộc, cần **policy riêng**, không trông chờ client tự throw theo cấu hình preferred.

### Bài 2 — Optional.empty là gì?

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .GET().build();
System.out.println(request.version());
~~~

Nếu output là `Optional.empty`, request sẽ dùng HTTP/1.1 mặc định đúng không?

**Đáp án:** Sai. `Optional.empty` chỉ nói **request không set override**. Client gửi request quyết định preferred default; Java 17 mặc định client thích `HTTP_2`, nhưng actual phải đọc từ `HttpResponse.version()`. Đoạn trên là **mảnh code** cần `uri` đã xác định và import `HttpRequest`.

### Bài 3 — Client và request xung đột

Client cấu hình `HTTP_1_1`; request cấu hình `HTTP_2`. Effective preferred version là gì? Có chắc actual = HTTP_2?

**Đáp án:** Request có override nên **effective preferred** là `HTTP_2`; **actual** vẫn phụ thuộc khả năng server, TLS/proxy/network, có thể là `HTTP_1_1`.

### Bài 4 — HTTPS TLS 1.3 trả h1

Một response đến từ `https://` với TLS 1.3, `response.version()==HTTP_1_1`. Có phải kết nối đã hạ từ HTTPS xuống HTTP không?

**Đáp án:** Không. HTTP/1.1 vẫn có thể chạy qua TLS 1.3. TLS version/bảo mật độc lập với HTTP version; nếu HTTPS được xác thực đúng thì fallback h1 không tự làm mất encryption.

### Bài 5 — Server không h2, request thành công

Server nội bộ chỉ hỗ trợ HTTP/1.1. Client ưu tiên HTTP/2 và gửi GET. Tại sao `HttpClient.send()` có thể trả HTTP 200 mà không ném exception?

**Đáp án:** Vì version selection cho phép HTTP/1.1 fallback. HTTP status 200 cho biết response thành công ở HTTP semantics; `response.version()` = HTTP_1_1 cho biết actual.

### Bài 6 — Async và version

`client.sendAsync(request, handler)` có bảo đảm HTTP_2 hơn `client.send(request, handler)` không?

**Đáp án:** Không. `sendAsync` nói về **async Java API**, không phải HTTP protocol version. Cả hai đều tuân thủ client/request preferences và server/proxy negotiation.

### Bài 7 — Redirect giữa hai origin

Client gửi tới origin A, được redirect tới B. Final response version là HTTP/1.1, trong khi A hỗ trợ HTTP/2. Có thể kết luận A chỉ dùng HTTP/1.1 không?

**Đáp án:** Không. Final response thuộc origin B và có thể khác version A. Xem `response.uri()`, `response.request()` và `response.previousResponse()`, hoặc logs của từng hop.

### Bài 8 — Bắt buộc HTTP/2 trước thanh toán

Một ứng dụng tạo order bằng POST và sau response mới phát hiện actual HTTP_1_1, không phải h2. Có nên POST lại để “được h2”?

**Đáp án:** Không. Server có thể đã tạo order. Việc gửi lại dễ gây trùng; nếu business yêu cầu h2 thì enforce capability/policy ở phía server/gateway và dùng idempotency key để phòng mạng lỗi, **không** dùng version mismatch làm lý do retry mù.

### Bài 9 — Proxy và upstream

Java client nhận HTTP/2 response từ reverse proxy nhưng proxy gửi HTTP/1.1 tới backend. `response.version()==HTTP_2` có mâu thuẫn không?

**Đáp án:** Không. Java response version là **version client dùng cho response của hop phía client**; proxy có thể sử dụng protocol khác với upstream backend.

### Bài 10 — Xác định lỗi

Client gọi `send()` và nhận `SSLHandshakeException`. Có thể ghi metric `actualVersion=HTTP_1_1` cho request đó không?

**Đáp án:** Không. TLS handshake không hoàn tất nên không có `HttpResponse`; **actual HTTP version chưa quan sát được**. Ghi lỗi TLS riêng, đừng tự điền h1.

### Bài 11 — HTTP/3 và Java 17

Đoạn code sau có compile với `javac --release 17` không?

~~~java
HttpClient.Version desired = HttpClient.Version.HTTP_3;
~~~

**Đáp án:** Không. Java 17 chỉ định nghĩa `HTTP_1_1` và `HTTP_2`. Nếu ứng dụng dùng JDK mới hơn, phải đọc docs đúng version; không tự suy ra hỗ trợ HTTP/3 từ API Java 17.

### Bài 12 — Lấy preferred và actual để log

Viết một biểu thức để xác định preferred hiệu lực khi request có hoặc không có override; sau đó lấy actual.

**Đáp án:**

~~~java
HttpClient.Version preferred =
        request.version().orElse(client.version());
HttpClient.Version actual = response.version();
boolean mismatch = preferred != actual;
~~~

Đây là **mảnh code** sau khi có response. Kết quả dùng cho quan sát hoặc policy; không chứng minh các request khác từ cùng client cũng mismatch.

## 17. Checklist áp dụng cho HTTP client Java

- [ ] Tôi phân biệt `client.version()` = preferred, `request.version()` = Optional override, `response.version()` = actual.
- [ ] Nếu `request.version().isEmpty()`, tôi dùng client preference chứ không tự gán HTTP/1.1.
- [ ] Tôi biết Java 17 ưu tiên `HTTP_2` theo mặc định, không đồng nghĩa mọi response đều h2.
- [ ] Tôi không coi `version(HTTP_2)` là hard requirement.
- [ ] Tôi log actual version **từ response của từng request**, cùng status và URI đã lược dữ liệu nhạy cảm.
- [ ] Tôi tách DNS/TCP/TLS errors khỏi HTTP status và HTTP version mismatch.
- [ ] Tôi phân biệt h2c upgrade trên HTTP cleartext và ALPN của HTTPS/TLS.
- [ ] Tôi kiểm tra proxy/redirect/backend-hop khi version khác kỳ vọng.
- [ ] Nếu h2 cần cho nghiệp vụ, có server/proxy enforcement và test giao thức riêng; không chỉ assert sau response.
- [ ] Tôi không retry POST/payment do actual version khác mong muốn mà thiếu idempotency policy.
- [ ] Tôi xem thử fallback h1 vẫn giữ HTTPS/TLS nếu URI/connection phù hợp.
- [ ] Tôi không trộn HTTP_1_1 / HTTP_2 với TLS_1_2 / TLS_1_3.
- [ ] Tôi không dùng Java 17 API để tuyên bố mọi JDK đời sau đều chỉ có hai enum.
- [ ] Tôi thử hành vi với `javac --release 17` nếu cần tương thích Java 17.
- [ ] Tôi không dùng `try (HttpClient ...)` khi compile target Java 17.
- [ ] Tôi test loopback với server kiểm soát được để phân biệt “không hỗ trợ h2” và network failure.

## 18. Tài liệu tham khảo chính thức

- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `client.version()` là preferred, mặc định HTTP/2, lưu ý proxy constraints.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `version(HTTP_2)` ưu tiên khi khả thi, hành vi HTTP/2 upgrade và fallback HTTP/1.1.
- [Java SE 17 — HttpClient.Version](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Version.html): các enum constants `HTTP_1_1` và `HTTP_2` ở Java 17.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): `request.version()` trả Optional; empty thì client quyết định preferred version.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request-level `version(...)` preference.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `version()` thực tế, `request()`, `uri()`, `previousResponse()`.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server nhúng trong `jdk.httpserver` phục vụ demo local HTTP/1.1.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): method/status/resource chung giữa HTTP versions.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): HTTP/1.1 message/framing.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 framing/connection, h2c và TLS contexts.
- [RFC 7301 — TLS ALPN](https://www.rfc-editor.org/rfc/rfc7301): negotiation application-layer protocol qua TLS.
- [Java SE 26 — HttpClient.Version](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Version.html): ví dụ một JDK mới hơn có thể có enum HTTP_3; luôn chốt docs theo version triển khai.

**Kết luận cần nhớ:** `HttpClient.Builder.version(...)` và `HttpRequest.Builder.version(...)` biểu thị **phiên bản muốn dùng**, còn `HttpResponse.version()` biểu thị **phiên bản đã dùng**. HTTP/2 mong muốn nhưng HTTP/1.1 thực tế có thể là fallback bình thường do server, TLS ALPN, h2c, proxy hoặc routing; nó **không đồng nghĩa lỗi HTTP, lỗi TLS hay mất bảo mật HTTPS**. Khi cần HTTP/2 thật sự, hãy xác minh response và thiết kế enforcement ở đúng hop và đúng thời điểm — đừng chỉ dựa vào builder.
