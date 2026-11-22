# Vai trò của `HttpClient`, `HttpRequest` và `HttpResponse` (Java 11+)

## 1. Bức tranh tổng thể

Java 11 đưa HTTP Client API vào Java SE dưới package **`java.net.http`**. Ba kiểu chính của API giải quyết ba trách nhiệm khác nhau:

- **`HttpClient`** — *bên gửi/điều phối*: quản lý cấu hình giao tiếp HTTP, gửi request, nhận response, tái sử dụng tài nguyên kết nối khi có thể và hỗ trợ gọi đồng bộ/bất đồng bộ.
- **`HttpRequest`** — *yêu cầu muốn gửi*: mô tả URI đích, HTTP method, headers, timeout riêng của yêu cầu và cách xuất bản request body (nếu có).
- **`HttpResponse<T>`** — *kết quả của một lần gửi*: cung cấp mã trạng thái, headers, URI thực tế, phiên bản giao thức, request gắn với response và body theo kiểu dữ liệu `T` được chọn bởi `BodyHandler<T>`.

Hãy hình dung luồng xử lý:

~~~text
Tạo HttpClient (cấu hình dùng chung)
             |
             v
Tạo HttpRequest (URI + method + headers + BodyPublisher)
             |
             v
HttpClient.send(request, BodyHandler)
hoặc HttpClient.sendAsync(request, BodyHandler)
             |
             v
HTTP server xử lý yêu cầu
             |
             v
Nhận status + headers + response body
             |
             v
HttpResponse<T> (đọc statusCode(), headers(), body(), ...)
             |
             v
Ứng dụng kiểm tra status và xử lý kết quả
~~~

**Câu ghi nhớ:** `HttpClient` **thực thi việc gửi**, `HttpRequest` **đặc tả điều gửi**, `HttpResponse` **mô tả điều nhận**. `BodyPublisher` quyết định **cách gửi body**, còn `BodyHandler` quyết định **cách nhận/biểu diễn body**.

API này vẫn có trong các phiên bản JDK hiện đại. Không cần dùng API HTTP incubator trước Java 11 hay dựa vào thư viện ngoài để thực hiện các HTTP request cơ bản.

## 2. `HttpClient`: cấu hình và thực thi kết nối HTTP

`HttpClient` là điểm vào chính để giao tiếp HTTP. Có hai cách tạo:

~~~java
HttpClient simple = HttpClient.newHttpClient();

HttpClient configured = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

Đây là **đoạn mã minh họa**; cần import `java.net.http.HttpClient` và `java.time.Duration`, đặt trong phương thức/lớp Java.

`HttpClient.newHttpClient()` tạo client với các mặc định của nền tảng. `HttpClient.newBuilder()` cho phép cấu hình có chủ đích. Khi đã xây xong, cấu hình của client không bị thay đổi bằng cách sửa lại builder.

### Các tùy chọn thường gặp

| Thuộc `HttpClient.Builder` | Vai trò | Lưu ý |
| --- | --- | --- |
| `connectTimeout(Duration)` | Giới hạn thời gian thiết lập một **kết nối mới** | Không đồng nghĩa timeout toàn bộ request |
| `followRedirects(Redirect)` | Chính sách theo HTTP redirect | Cần xét an toàn khi chuyển host/protocol |
| `version(HTTP_1_1 / HTTP_2)` | Phiên bản giao thức ưu tiên | Server và điều kiện kết nối có thể khiến phiên bản thực tế khác |
| `proxy(ProxySelector)` | Cấu hình proxy | Quan trọng trong mạng doanh nghiệp |
| `authenticator(Authenticator)` | Cung cấp chính sách xác thực hỗ trợ bởi client | Không thay thế mọi cơ chế token/API authentication |
| `cookieHandler(CookieHandler)` | Quản lý cookie theo chính sách riêng | Không mặc định gửi/nhận session cookie tùy ý |
| `sslContext(SSLContext)` / `sslParameters(...)` | Cấu hình TLS khi có yêu cầu phù hợp | Không vô hiệu hóa kiểm chứng chứng chỉ trong sản phẩm |
| `executor(Executor)` | Chỉ định executor liên quan đến xử lý bất đồng bộ | Cần thiết kế vòng đời thread/executor khi tự cung cấp |

**Tái sử dụng client:** nên xây một `HttpClient` phù hợp với nhóm dịch vụ/chính sách cấu hình rồi dùng cho nhiều request, thay vì tạo client mới vô điều kiện ở mỗi lời gọi. Client có thể quản lý kết nối và tài nguyên phục vụ nhiều trao đổi HTTP; việc tái sử dụng giúp tránh cấu hình lặp và cho phép triển khai tối ưu kết nối.

**HTTP/2 không được bảo đảm chỉ bằng `version(HTTP_2)`**: đó là lựa chọn ưu tiên. Kiểm tra `response.version()` nếu chương trình cần biết giao thức thật sự sử dụng. Ví dụ hoàn chỉnh trong bài cố ý dùng HTTP/1.1 vì server kiểm thử nội bộ cung cấp HTTP/1.1.

### Hai phương thức gửi quan trọng

~~~java
// Đồng bộ: chờ phản hồi theo BodyHandler đã cung cấp.
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

// Bất đồng bộ: nhận CompletableFuture<HttpResponse<String>>.
CompletableFuture<HttpResponse<String>> pending =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
~~~

Các dòng trên là **mã minh họa**: giả định `client` và `request` đã được tạo hợp lệ, import `HttpResponse` và `CompletableFuture`.

- `send(...)` có thể chặn thread đang gọi; khai báo `throws IOException, InterruptedException`.
- `sendAsync(...)` trả về `CompletableFuture<HttpResponse<T>>`. Lỗi thường được biểu diễn bằng một future hoàn tất *exceptionally*, và `join()` có thể ném `CompletionException` bọc nguyên nhân.
- **Bất đồng bộ không có nghĩa việc xử lý body tự động không tốn tài nguyên.** Nếu callback xử lý CPU dài hoặc gọi `join()` trên thread quan trọng, ứng dụng vẫn có thể bị nghẽn.

### Vòng đời `HttpClient` theo phiên bản Java

**Điểm tương thích dễ bỏ sót:** Trong **Java 11**, `HttpClient` **không triển khai `AutoCloseable`**, vì vậy ví dụ Java 11 không thể viết `try (HttpClient client = ...) { ... }`. Từ **Java 21**, API bổ sung các phương thức quản lý vòng đời như `close()` và hỗ trợ `AutoCloseable`; trên những JDK đó cần xử lý đúng cả các response body dạng streaming trước khi đóng client.

Đây không phải lý do dùng API đã lỗi thời: `java.net.http.HttpClient` của Java 11 vẫn được hỗ trợ, chỉ cần phân biệt phần lõi có từ Java 11 với khả năng được thêm ở phiên bản mới.

## 3. `HttpRequest`: đặc tả một yêu cầu, không tự gửi

`HttpRequest` biểu diễn **thông tin cần thiết cho HTTP request**. Dùng builder để tạo:

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/items"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Đoạn này minh họa cấu trúc; nếu chạy thực cần import `HttpRequest`, `URI`, `Duration` và một endpoint thật. Chỉ tạo `HttpRequest` **không mở kết nối và không gửi bất kỳ byte nào**. Việc gửi bắt đầu khi gọi `client.send(...)` hoặc `client.sendAsync(...)`.

### Những thành phần trong `HttpRequest`

| Thành phần | API điển hình | Ý nghĩa |
| --- | --- | --- |
| URI đích | `.uri(URI)` / `request.uri()` | Địa chỉ HTTP/HTTPS muốn gọi |
| HTTP method | `.GET()`, `.POST(...)`, `.PUT(...)`, `.DELETE()`, `.method(...)` | Kiểu thao tác HTTP |
| Headers | `.header(name, value)` / `request.headers()` | Metadata như `Accept`, `Content-Type`, `Authorization` |
| Timeout request | `.timeout(Duration)` / `request.timeout()` | Giới hạn thời gian theo hợp đồng của request |
| Request body | `BodyPublisher` | Chuyển dữ liệu thành byte để gửi đi |
| HTTP version ưu tiên | `.version(Version)` | Ưu tiên riêng cho request (nếu đặt) |

Builder là đối tượng cấu hình có thể thay đổi; **`HttpRequest` tạo bởi `build()` có cấu hình bất biến**. Có thể tạo nhiều request từ cùng cấu hình builder sau khi thay đổi, nhưng đừng chia sẻ builder mutable giữa nhiều thread khi chưa đồng bộ.

**Đúng vai trò:** `HttpRequest` không chứa HTTP response, không tự kiểm tra status, không phải một kết nối socket và không làm việc tương đương `HttpClient.send`.

### GET không có request body và POST có body

GET thường dùng:

~~~java
HttpRequest get = HttpRequest.newBuilder(
        URI.create("https://example.com/items"))
        .GET()
        .build();
~~~

POST gửi text:

~~~java
HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://example.com/items"))
        .header("Content-Type", "text/plain; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                "name=Lan", StandardCharsets.UTF_8))
        .build();
~~~

Hai đoạn là **mã minh họa**, cần import `HttpRequest`, `URI`, `StandardCharsets`. `BodyPublishers.ofString(...)` tạo nguồn phát byte theo encoding. Nó **không tự chọn hay thêm header `Content-Type`** đại diện chính xác cho dữ liệu nghiệp vụ; cần khai báo header theo API server yêu cầu.

Các publisher phổ biến:

- `BodyPublishers.noBody()`: không có request body.
- `BodyPublishers.ofString(text, charset)`: encode chuỗi thành byte.
- `BodyPublishers.ofByteArray(bytes)`: gửi nội dung từ mảng byte.
- `BodyPublishers.ofFile(path)`: lấy body từ tệp; có thể báo `IOException`.
- `BodyPublishers.ofInputStream(supplier)`: cung cấp nguồn stream theo lúc gửi; phải hiểu vòng đời và khả năng tạo lại stream.

**Không có JSON serializer tự động trong `java.net.http`.** Nếu endpoint yêu cầu JSON, bạn phải tạo JSON đúng cấu trúc bằng logic/thư viện chuyên dụng, rồi dùng publisher gửi chuỗi/byte và đặt `Content-Type: application/json`. Đừng coi `BodyPublishers.ofString("...")` là hàm biến object Java thành JSON.

### Có thể gửi lại cùng `HttpRequest` không?

`HttpRequest` giữ cấu hình bất biến và có thể được sử dụng cho những lần gửi phù hợp; tuy nhiên, **khả năng gửi lại phụ thuộc `BodyPublisher`**. Với stream chỉ đọc được một lần, nếu có redirect, authentication challenge hoặc retry, dữ liệu body có thể không còn để phát lại.

Không tự retry các yêu cầu không idempotent như POST khi chưa hiểu kết quả gửi trước, vì server có thể đã xử lý lần đầu dù client thấy timeout hoặc mất kết nối. Thiết kế retry theo HTTP method, idempotency key hoặc hợp đồng API cụ thể.

## 4. `HttpResponse<T>`: kết quả, không phải yêu cầu

Một lần gửi thành công ở mức giao tiếp HTTP tạo ra `HttpResponse<T>` (hoặc một future chứa response):

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

int code = response.statusCode();
String text = response.body();
~~~

Đoạn mã minh họa giả định đã có `client`, `request` và imports phù hợp. **`T` là kiểu của body do `BodyHandler<T>` chọn**, không phải kiểu của cả HTTP response. Ví dụ:

- `HttpResponse<String>` với `BodyHandlers.ofString(...)`.
- `HttpResponse<byte[]>` với `BodyHandlers.ofByteArray()`.
- `HttpResponse<Path>` với `BodyHandlers.ofFile(path)`.
- `HttpResponse<InputStream>` với `BodyHandlers.ofInputStream()`.

Các thông tin quan trọng:

| API `HttpResponse<T>` | Ý nghĩa |
| --- | --- |
| `statusCode()` | Mã trạng thái HTTP, như 200, 201, 204, 400, 404, 500 |
| `headers()` | `HttpHeaders` chỉ đọc của response; tra header bằng `firstValue(...)` |
| `body()` | Body theo kiểu `T` đã chọn |
| `request()` | `HttpRequest` liên quan tới response |
| `uri()` | URI thực tế nhận phản hồi; có thể khác URI gốc nếu redirect |
| `version()` | HTTP version thật sự được sử dụng |
| `previousResponse()` | Có thể có response trước đó trong chuỗi redirect |
| `sslSession()` | `Optional<SSLSession>` khi có kết nối TLS tương ứng |

**Hai kết luận quan trọng:**

1. `HttpResponse` không phải object để tự gắn thêm headers rồi “gửi trở lại”. Nó là **kết quả đọc** của một lần `send`/`sendAsync`.
2. `HttpResponse<T>` **không đồng nghĩa toàn bộ body đã về bộ nhớ** trong mọi trường hợp. Với `BodyHandlers.ofString` hoặc `ofByteArray` thì body đã được tích lũy cho kiểu tương ứng; với `ofInputStream`, response có thể xuất hiện khi mới nhận xong headers và body còn được đọc dần từ stream.

### HTTP status không phải ngoại lệ Java

`client.send(...)` **không tự ném `IOException` chỉ vì server trả HTTP 404 hoặc 500**. Đó vẫn là phản hồi HTTP có status, headers và có thể có body. Bạn phải kiểm tra:

~~~java
int status = response.statusCode();
if (status >= 200 && status < 300) {
    // Thành công theo quy ước 2xx.
} else {
    // Xử lý status, thông báo lỗi và policy retry theo API.
}
~~~

Đoạn trên là mã minh họa; cần được đặt trong ngữ cảnh đã có `response`. Một phản hồi **204 No Content** có thể không có body, nên không được mặc định JSON/string dữ liệu luôn có nội dung.

**Phân biệt lớp lỗi:**

- **HTTP 4xx/5xx:** server đã tạo phản hồi HTTP; có `HttpResponse.statusCode()`.
- **`IOException` / timeout / lỗi TLS / kết nối:** có thể chưa nhận được response hữu ích.
- **`InterruptedException`:** thread bị interrupt trong lời gọi `send` đồng bộ; nên tôn trọng chính sách interrupt của ứng dụng.
- **Lỗi xử lý nội dung:** status có thể 200 nhưng body vẫn không hợp lệ theo schema hoặc không giải mã đúng. Cần validation độc lập.

## 5. `BodyPublisher` và `BodyHandler`: hai chiều khác nhau

~~~text
Ứng dụng muốn gửi dữ liệu
    |
    v
BodyPublisher <--- thuộc HttpRequest (POST/PUT/...)
    |
    v
HTTP bytes đi đến server
    |
    v
Server trả status, headers, response bytes
    |
    v
BodyHandler<T>  <--- truyền lúc gọi HttpClient.send/sendAsync
    |
    v
BodySubscriber<T> nhận/biến đổi byte
    |
    v
HttpResponse<T>.body()
~~~

`HttpRequest.BodyPublisher` là giao diện phát ra chuỗi `ByteBuffer` cho body **đầu ra**. `HttpResponse.BodyHandler<T>` chọn cách nhận body **đầu vào**, tạo `BodySubscriber<T>` phù hợp. Handler có thể xem status và headers trước khi chọn subscriber.

Ví dụ:

~~~java
// Gửi một chuỗi UTF-8.
HttpRequest.BodyPublisher outgoing =
        HttpRequest.BodyPublishers.ofString(
                "ping", StandardCharsets.UTF_8);

// Khi nhận phản hồi, đọc thành chuỗi UTF-8.
HttpResponse.BodyHandler<String> incoming =
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8);
~~~

Đây là **đoạn mã minh họa**, không tự gửi request; cần đặt trong lớp có imports phù hợp.

| Chọn `BodyHandlers...` | `HttpResponse<T>` tương ứng | Nên dùng khi |
| --- | --- | --- |
| `ofString(StandardCharsets.UTF_8)` | `HttpResponse<String>` | Response text nhỏ/vừa có UTF-8 |
| `ofByteArray()` | `HttpResponse<byte[]>` | Cần byte nguyên bản và kích thước có kiểm soát |
| `ofFile(path)` | `HttpResponse<Path>` | Ghi dữ liệu xuống tệp theo option và chính sách quyền/overwrite |
| `discarding()` | `HttpResponse<Void>` | Không cần giữ body nhưng vẫn cần status/headers |
| `ofInputStream()` | `HttpResponse<InputStream>` | Cần đọc body từng phần để không nạp toàn bộ vào RAM |
| `ofLines()` | `HttpResponse<Stream<String>>` | Cần xử lý dòng; phải đóng/tiêu thụ stream đúng cách |

**Quản lý body dạng streaming:** nếu dùng `ofInputStream()` hoặc `ofLines()`, phải đọc đến EOF và/hoặc đóng luồng trả về đúng hợp đồng. Không bỏ mặc stream mở vì có thể giữ kết nối/tài nguyên HTTP. Đối với request tải dữ liệu không đáng tin, cần giới hạn kích thước, timeout và kiểm soát định dạng; `ofByteArray()`/`ofString()` không phải lựa chọn phù hợp cho mọi payload lớn.

**HTTP body handler mặc định không tự kiểm tra 2xx:** `BodyHandlers.ofString()` vẫn nhận body của 4xx/5xx. Nếu cần chọn cách tiêu thụ dựa trên status hoặc headers, có thể xây `BodyHandler` tùy biến; trong phần lớn ứng dụng nhỏ, đọc rồi kiểm tra `response.statusCode()` là đủ nếu body có kích thước giới hạn.

## 6. Ví dụ Java 11 hoàn chỉnh — chạy HTTP server nội bộ, gửi GET và POST

Để ví dụ chạy mà **không cần internet hoặc API key**, chương trình dùng `com.sun.net.httpserver.HttpServer` (module `jdk.httpserver` của JDK) tạo server HTTP/1.1 trên loopback `127.0.0.1` và cổng tự chọn. **Mục tiêu bài là ba lớp HTTP client**, server chỉ đóng vai trò đối tác kiểm thử.

Tạo tệp **HttpRolesDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class HttpRolesDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/hello", exchange ->
                respond(exchange, 200, "Hello, Java 11!"));
        server.createContext("/echo", exchange -> {
            try {
                if (!exchange.getRequestMethod().equals("POST")) {
                    respond(exchange, 405, "Method Not Allowed");
                    return;
                }
                String requestBody = new String(
                        exchange.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8);
                respond(exchange, 200, "echo:" + requestBody);
            } catch (IOException e) {
                exchange.close();
            }
        });
        server.start();

        try {
            URI base = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            HttpRequest getRequest = HttpRequest.newBuilder(
                            base.resolve("hello"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "text/plain")
                    .GET()
                    .build();
            HttpResponse<String> getResponse = client.send(
                    getRequest,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            System.out.println("method=" + getResponse.request().method());
            System.out.println("status=" + getResponse.statusCode());
            System.out.println("header=" +
                    getResponse.headers().firstValue("X-Demo").orElse("missing"));
            System.out.println("body=" + getResponse.body());
            System.out.println("version=" + getResponse.version());

            HttpRequest postRequest = HttpRequest.newBuilder(
                            base.resolve("echo"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type", "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "name=Lan", StandardCharsets.UTF_8))
                    .build();

            CompletableFuture<HttpResponse<String>> pending =
                    client.sendAsync(
                            postRequest,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
            HttpResponse<String> postResponse = pending.join();
            System.out.println("postMethod=" + postResponse.request().method());
            System.out.println("postStatus=" + postResponse.statusCode());
            System.out.println("postBody=" + postResponse.body());
        } finally {
            server.stop(0);
        }
    }

    private static void respond(HttpExchange exchange,
                                int status, String message) throws IOException {
        try {
            byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.getResponseHeaders().set("X-Demo", "local");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }
}
~~~

**Biên dịch và chạy trên JDK đầy đủ có module `jdk.httpserver`:**

~~~bash
javac --release 11 --add-modules jdk.httpserver HttpRolesDemo.java
java --add-modules jdk.httpserver HttpRolesDemo
~~~

Đầu ra đã kiểm chứng bằng JDK 24 khi biên dịch với `--release 11`:

~~~text
method=GET
status=200
header=local
body=Hello, Java 11!
version=HTTP_1_1
postMethod=POST
postStatus=200
postBody=echo:name=Lan
~~~

### Phân tích chính xác từng vai trò trong ví dụ

1. **`HttpClient`** chỉ được tạo **một lần**, cấu hình `connectTimeout(3s)`, `Redirect.NEVER` và HTTP/1.1. Cùng client được dùng để gửi GET đồng bộ rồi POST bất đồng bộ.
2. **`HttpRequest getRequest`** mô tả đường dẫn `/hello`, method GET, `Accept: text/plain` và timeout riêng 5 giây. `build()` chưa giao tiếp với server.
3. **`HttpResponse<String> getResponse`** đến từ `client.send(...)`. `statusCode()` cho 200, `headers().firstValue("X-Demo")` cho `local`, `body()` cho text `Hello, Java 11!`; `request().method()` xác nhận request tương ứng là GET.
4. **`getResponse.version()`** trả `HTTP_1_1` do ví dụ dùng server HTTP/1.1 và client được cấu hình ưu tiên cùng phiên bản.
5. **`HttpRequest postRequest`** mô tả một POST khác, body được encode từ `name=Lan` bằng `BodyPublishers.ofString`. Header `Content-Type` chỉ rõ text UTF-8.
6. **`client.sendAsync(...)`** tạo `CompletableFuture<HttpResponse<String>>`. `pending.join()` chủ động chờ để ví dụ in ra kết quả ổn định, **không biến thao tác gửi thành synchronous API**; future vẫn là phần trả về của `sendAsync`.
7. **`postResponse.body()`** là `echo:name=Lan` vì server demo đọc request body và trả chuỗi tương ứng. Không có thư viện JSON hoặc API ngoài nào tham gia.
8. **`server.stop(0)`** kết thúc HTTP server nội bộ. `HttpClient` trong ví dụ Java 11 không được đặt trong try-with-resources vì API ở Java 11 chưa hỗ trợ `AutoCloseable`.

Mẫu trên **có thực hiện HTTP thật**, nhưng chỉ đến loopback của máy chạy và một cổng tạm do hệ điều hành cấp. Nếu máy không cho bind socket loopback hoặc dùng JRE tùy biến không có `jdk.httpserver`, cần cấp môi trường JDK phù hợp. Module `jdk.httpserver` là tiện ích test/demo được JDK cung cấp, không phải thiết kế server production cho yêu cầu phức tạp.

## 7. Khi nào chọn `send`, khi nào chọn `sendAsync`?

| Nhu cầu | Phương thức | Kết quả trả về | Cần lưu ý |
| --- | --- | --- | --- |
| Logic tuyến tính, CLI nhỏ, batch tuần tự | `send(request, handler)` | `HttpResponse<T>` | Thread hiện tại chờ; `IOException`/`InterruptedException` |
| Nhiều request đồng thời, pipeline không muốn block caller | `sendAsync(request, handler)` | `CompletableFuture<HttpResponse<T>>` | Quản lý future, lỗi, timeout, cancellation và concurrency |
| Xử lý kết quả sau khi hoàn tất | `sendAsync(...).thenApply(HttpResponse::body)` | Future của body | Phải kiểm tra status trước khi tin vào body |
| Có thao tác liên tiếp cần đồng bộ thứ tự | `send` hoặc chuỗi future có điều phối | Tùy thiết kế | Không gọi `join()` bừa bãi trên event loop/UI thread |

Một pattern async tách kiểm tra status:

~~~java
CompletableFuture<String> bodyFuture = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8))
        .thenApply(response -> {
            int status = response.statusCode();
            if (status < 200 || status >= 300) {
                throw new IllegalStateException(
                        "Unexpected HTTP status: " + status);
            }
            return response.body();
        });
~~~

Đây là **mã minh họa**, `client` và `request` được khai báo ở nơi khác. Nên dùng `exceptionally`/`handle`/`whenComplete` để quan sát lỗi đúng chính sách, không bỏ qua future thất bại. Đừng chia sẻ dữ liệu mutable không đồng bộ giữa các callback.

**Timeout hai tầng:**

- `client.connectTimeout(Duration)` giới hạn việc thiết lập **kết nối mới**, không nhất thiết áp dụng khi client đã có kết nối có thể tái dùng.
- `request.timeout(Duration)` ràng buộc thời gian chờ phản hồi theo hợp đồng của request; cần hiểu giới hạn thực tế khi BodyHandler trả về kiểu streaming.
- Với `sendAsync`, timeout/lỗi có thể hoàn tất future bằng exception; không bảo đảm server chưa nhận request.
- Nếu hệ thống có hạn mức độ trễ từ đầu đến cuối, cần ngân sách timeout riêng ở nghiệp vụ và quản lý việc tiêu thụ response body.

## 8. Những lỗi hiểu nhầm phổ biến

| Ngộ nhận | Thực tế | Hướng xử lý |
| --- | --- | --- |
| “Tạo `HttpRequest` là đã gửi request.” | Builder chỉ tạo mô tả bất biến | Gọi `HttpClient.send` hoặc `sendAsync` |
| “`HttpClient` chính là một request.” | Client cấu hình/điều phối **nhiều** request | Tái dùng client, tạo request theo thao tác |
| “`HttpResponse<String>` chỉ gồm body.” | Có status, headers, URI, HTTP version, request | Kiểm tra `statusCode()` trước khi xử lý body |
| “HTTP 404 làm `send` ném `IOException`.” | 404 là response HTTP hợp lệ | Phân biệt HTTP status và lỗi transport |
| “`BodyPublisher` giúp đọc response.” | Publisher phát **request** body | Response dùng `BodyHandler<T>` |
| “`BodyHandlers.ofString` tự giải mã JSON thành object.” | Chỉ giải mã body thành String theo charset | JSON parse bằng công cụ/schema riêng |
| “`response.version()` luôn là version đã request.” | Version thực tế có thể được thương lượng/thay đổi | Dựa vào `response.version()` |
| “`sendAsync` không bao giờ chặn.” | Gửi trả future, nhưng `join()` hoặc callback blocking vẫn chặn | Thiết kế xử lý future thích hợp |
| “Bất kỳ status nào cũng nghĩa là thành công.” | 4xx/5xx là lỗi ứng dụng/giao thức ở tầng HTTP | Chính sách status theo API |
| “`ofString` phù hợp mọi response lớn.” | Nạp body vào bộ nhớ | Dùng stream hoặc file handler khi cần |
| “Đã lấy `ofInputStream` thì không cần đóng.” | Stream có thể giữ tài nguyên/kết nối | Tiêu thụ/đóng body theo hợp đồng |
| “Mọi Java 11 `HttpClient` đều `AutoCloseable`.” | API quản lý vòng đời được bổ sung từ Java 21 | Viết code đúng theo Java version |
| “Đặt `connectTimeout` đủ để chống chờ mãi mọi request.” | Connect timeout không đồng nhất request timeout | Cấu hình đúng cả client và request |
| “POST thất bại thì cứ tự động gửi lại.” | Có thể gây xử lý trùng | Dùng retry policy/idempotency theo API |

## 9. Thực hành an toàn khi làm việc với HTTP Client

### Bảo mật và giao thức

- Dùng **HTTPS** cho dữ liệu thật khi yêu cầu bảo mật; ví dụ dùng HTTP thuần chỉ vì server nằm trên loopback để học API.
- Không tự vô hiệu hóa kiểm chứng TLS, hostname verification hoặc certificate validation để “sửa lỗi kết nối”.
- Không log trực tiếp `Authorization`, cookie, token và body nhạy cảm.
- Không giả định mọi redirect đều an toàn; nếu tự động redirect, cân nhắc host đích, giao thức và headers bí mật.
- Với URI do người dùng cung cấp, kiểm soát đích mạng để tránh biến HTTP client thành công cụ gọi đến endpoint nội bộ ngoài ý muốn (SSRF).
- Xác định giới hạn kích thước body và nội dung chấp nhận; HTTP status 200 không có nghĩa body hợp lệ.

### Tính đúng đắn của dữ liệu

- Đặt `Accept` theo kiểu response mong muốn và `Content-Type` theo request body thực gửi.
- Chọn `StandardCharsets.UTF_8` rõ ràng khi hợp đồng API là UTF-8. Với `BodyHandlers.ofString()` không đối số, charset được suy ra từ response header hoặc dùng UTF-8 fallback; dùng overload có charset để tránh nhầm khi biết trước encoding.
- Không dùng `BodyHandlers.ofFile` mà không kiểm tra đường dẫn đích và quyền ghi; phải xử lý tình huống file đã tồn tại, nội dung chưa hoàn tất và lỗi I/O.
- `response.headers()` là dữ liệu do phía bên kia trả; header có thể vắng mặt, nên dùng `firstValue(...).orElse(...)` hoặc xử lý `Optional`.
- Khi xử lý JSON/XML, kiểm tra schema và lỗi parse một cách độc lập với HTTP status.
- Khi API đòi retry, phân biệt **kết nối chưa gửi**, **đã gửi nhưng chưa nhận response**, **đã nhận HTTP error**; không suy luận quá mức từ `IOException`.

### Vòng đời và kiểm thử

- Giữ một `HttpClient` cho những trao đổi cùng cấu hình, tránh tạo liên tục trong vòng lặp.
- Với Java 21+ và client do ứng dụng sở hữu, xem xét `close()`/`try-with-resources` theo vòng đời hợp lý; **không áp dụng trực tiếp cú pháp đó cho Java 11**.
- Với `HttpResponse<InputStream>`, đọc và đóng stream đúng cách; future hoàn tất không có nghĩa nội dung streaming đã được tiêu thụ.
- Dùng server HTTP nội bộ hoặc test double khi test không muốn phụ thuộc mạng ngoài. Kiểm thử cả 2xx, 4xx, 5xx, timeout, redirect, charset và body lớn.
- Tách logic tạo `HttpRequest`, gọi `HttpClient` và giải mã/validate `HttpResponse` để dễ mock, log theo chính sách và nâng cấp.

## 10. Checklist trước khi viết code Java 11

1. **Client:** đã chọn cấu hình connect timeout, redirect, HTTP version và chính sách TLS/proxy phù hợp?
2. **Request:** URI có hợp lệ không? HTTP method đúng? Header `Content-Type`/`Accept` đúng? Có timeout riêng?
3. **Body gửi:** `BodyPublisher` có phát đúng bytes/charset không? Có thể gửi lại nếu retry/redirect không?
4. **Gửi:** cần `send` đồng bộ hay `sendAsync` với future, callback và kiểm soát lỗi?
5. **Response:** đã kiểm `statusCode()` và xử lý 4xx/5xx khác lỗi I/O chưa?
6. **Body nhận:** `BodyHandler<T>` chọn đúng kiểu `T`? Nếu là stream, đã đóng/đọc hết chưa?
7. **Tài nguyên:** client được tái sử dụng đúng vòng đời? Chỗ nào sở hữu server/body stream/executor?
8. **Bảo mật:** đã tránh log token, dùng HTTPS hợp lý, kiểm redirect và đích mạng?
9. **Phiên bản Java:** code chạy Java 11 có tránh API chỉ thêm ở Java 21+ như `HttpClient.close()` không?
10. **Kiểm thử:** có test status, header, body, timeout, async exception và tình huống lỗi mạng?

**Tóm lại:** `HttpClient` làm nhiệm vụ **gửi và quản lý giao tiếp**, `HttpRequest` mô tả **yêu cầu**, `HttpResponse<T>` cung cấp **kết quả đã nhận**. Luồng dữ liệu đi qua `BodyPublisher` khi gửi và `BodyHandler<T>` khi nhận. Ba khái niệm này là nền tảng HTTP client hiện đại trong Java 11+ và vẫn được sử dụng ngày nay.

## Tài liệu tham khảo chính thức

- [Java SE 11 — `HttpClient`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): cách tạo client và `send`/`sendAsync` ở phiên bản nền tảng.
- [Java SE 11 — `HttpRequest`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html): request builder, headers, URI, method và body publisher.
- [Java SE 11 — `HttpResponse<T>`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): response status, headers, body, request và version.
- [Java SE 26 — `HttpClient`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): hợp đồng hiện hành và các bổ sung quản lý vòng đời từ Java 21.
- [Java SE 25 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): cách nhận body theo kiểu dữ liệu và nghĩa vụ đóng streaming body.
- [Java SE 25 — `HttpRequest.BodyPublishers`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): tạo nguồn phát request body.
- [Java SE 25 — `HttpResponse.BodyHandler`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): chọn body subscriber dựa trên thông tin response.
- [Java SE 11 — module `jdk.httpserver`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/module-summary.html): server dùng riêng cho ví dụ kiểm thử.

Bài học dùng API chuẩn còn được hỗ trợ và nêu rõ phần có từ Java 11 so với API thêm sau đó; không dựa vào các kỹ thuật đã bị loại bỏ.