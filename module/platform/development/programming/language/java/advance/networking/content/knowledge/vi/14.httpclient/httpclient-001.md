# HttpClient, HttpRequest và HttpResponse trong module java.net.http

Từ Java 11, JDK có **HTTP Client API chuẩn** trong module **`java.net.http`**. Ba kiểu cốt lõi tạo thành một luồng HTTP rõ ràng:

- **`HttpClient`**: cấu hình và thực thi kết nối HTTP/HTTPS, tái sử dụng tài nguyên giữa nhiều lời gọi; có thể gửi đồng bộ hoặc bất đồng bộ.
- **`HttpRequest`**: mô tả **một yêu cầu** gồm `URI`, HTTP method, headers, timeout và bộ phát request body.
- **`HttpResponse<T>`**: kết quả nhận được, gồm HTTP status, headers, phiên bản HTTP, URI cuối cùng và body đã được xử lý theo kiểu `T`.

Ví dụ điển hình:

~~~java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
        .GET()
        .build();

HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());

System.out.println(response.statusCode());
System.out.println(response.body());
~~~

Đây là **snippet**: cần imports `java.net.URI`, `java.net.http.*` và xử lý `IOException`/`InterruptedException`. Nó cần kết nối Internet tới một host thực nên không phải bài test offline. Hai chương trình hoàn chỉnh bên dưới thay thế host Internet bằng HTTP server chạy trên **`127.0.0.1`**, có thể biên dịch/chạy với Java 17+.

## 1. Vì sao dùng java.net.http thay cho lập trình socket thủ công?

HTTP nằm trên một transport: HTTP/1.1 thường dùng TCP, còn HTTP/2 multiplex nhiều luồng HTTP trên kết nối phù hợp. Nếu chỉ có `Socket` hoặc `SocketChannel`, ứng dụng phải tự viết logic cho method, request line, headers, response status, transfer framing, redirect, phiên bản HTTP, TLS và các chi tiết giao thức.

`HttpClient` cung cấp API ở **mức yêu cầu/phản hồi HTTP**, không yêu cầu bạn tự nối chuỗi `"GET / HTTP/1.1\r\n..."` hoặc giải mã HTTP/2 frames.

~~~text
Ứng dụng Java
       |
       | tạo HttpRequest (URI, method, headers, body)
       v
   HttpClient
       |  HTTP/1.1 hoặc HTTP/2
       |  quản lý kết nối, redirect/timeout theo cấu hình
       |  HTTPS/TLS theo policy
       v
    Network
       |
       v
    HTTP server
       |
       | status + headers + body
       v
HttpClient + BodyHandler<T>
       |
       v
 HttpResponse<T>
       |
       +--> statusCode(), headers(), version(), uri(), body()
~~~

Mô hình này phù hợp khi gọi REST API, lấy tài liệu, gọi dịch vụ nội bộ, gửi JSON, tải tệp hoặc fan-out nhiều HTTP requests. Nó **không** phải HTTP server API; việc nhận inbound HTTP requests thuộc về server framework hoặc server implementation khác.

Module `java.net.http` được chuẩn hóa từ Java 11 (thay cho HTTP Client ươm tạo ở những phiên bản JDK cũ). Nó cũng chứa các API WebSocket client, nhưng bài này tập trung vào **HTTP request/response**.

## 2. Ba kiểu đóng vai trò khác nhau

| Kiểu / thành phần | Sở hữu dữ liệu gì? | Ví dụ method |
| --- | --- | --- |
| `HttpClient` | Cấu hình chung: protocol preference, redirect, connect timeout, proxy, authenticator, cookie handler, SSL context, executor | `newHttpClient()`, `newBuilder()`, `send()`, `sendAsync()` |
| `HttpRequest` | Một yêu cầu cụ thể: URI, method, request headers, timeout, body publisher | `newBuilder(uri)`, `GET()`, `POST(...)`, `build()` |
| `HttpRequest.BodyPublisher` | Phát dữ liệu body của **request** thành chuỗi bytes | `BodyPublishers.noBody()`, `ofString(...)`, `ofByteArray(...)`, `ofFile(...)` |
| `HttpResponse<T>` | HTTP response metadata và body loại `T` | `statusCode()`, `headers()`, `body()`, `version()` |
| `HttpResponse.BodyHandler<T>` | Quyết định cách xử lý dữ liệu body **response** | `BodyHandlers.ofString()`, `ofByteArray()`, `ofInputStream()`, `ofFile(...)` |
| `HttpHeaders` | Header map phía response, bất biến qua public API | `firstValue(name)`, `allValues(name)`, `map()` |
| `CompletableFuture<HttpResponse<T>>` | Kết quả của một thao tác gửi bất đồng bộ | `thenApply(...)`, `thenCompose(...)`, `allOf(...)`, `get()` |

**Phân biệt publisher và handler:** `BodyPublisher` nằm trên **đường đi ra** (request). `BodyHandler` nằm trên **đường đi về** (response). Một client có thể gửi request không có body nhưng vẫn nhận response có body.

**Tính bất biến:** `HttpClient` đã `build()` là immutable ở mức cấu hình; `HttpRequest` đã build cũng là immutable. Builder được sử dụng trong lúc cấu hình, sau đó có thể tái sử dụng hoặc tạo builder mới theo nhu cầu. Tránh để nhiều threads thay đổi chung một builder không có đồng bộ.

## 3. Tạo HttpClient: cấu hình dùng chung, tái sử dụng nhiều lần

Cách ngắn nhất:

~~~java
HttpClient client = HttpClient.newHttpClient();
~~~

Mẫu có cấu hình rõ ràng:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .version(HttpClient.Version.HTTP_2)
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
~~~

Đây là **snippet** (cần imports `java.net.http.HttpClient`, `java.time.Duration`). Ý nghĩa:

- `connectTimeout(...)` giới hạn thời gian **thiết lập một kết nối mới**, không phải tổng thời gian tải toàn bộ response.
- `version(HTTP_2)` đặt **phiên bản mong muốn** khi có thể, không buộc server phải hỗ trợ HTTP/2.
- `followRedirects(NORMAL)` cho phép client xử lý redirect thông thường theo policy của API; cần cân nhắc redirect đến host khác, nhất là khi request mang credentials.
- `build()` tạo client có thể được dùng lại cho nhiều requests và nhiều threads.
- `HttpClient.newHttpClient()` dùng cấu hình mặc định; không nhất thiết là lựa chọn tốt nhất cho mọi hệ thống vì bạn có thể cần timeout, proxy hoặc redirect policy tường minh.

**Mặc định đáng nhớ ở Java 17:**
- Nếu không yêu cầu protocol version, client **ưu tiên HTTP/2** nhưng có thể dùng HTTP/1.1.
- Nếu không cấu hình redirect, policy mặc định là **`NEVER`**.
- Không có cookie handler đặc biệt được tự cấu hình cho mọi ứng dụng; thêm `CookieHandler` nếu cần lưu/đọc cookies theo policy.
- Cấu hình `connectTimeout` chưa đặt không có nghĩa request có deadline phù hợp với nghiệp vụ; nên đặt cả request timeout nếu cần.

**Tái sử dụng client:** Tạo một `HttpClient` dùng cho một nhóm yêu cầu liên quan thay vì tạo mới với mỗi request, bởi client giữ cấu hình và cơ hội dùng lại tài nguyên/kết nối. Tuy nhiên, **không ép một client duy nhất chia sẻ mọi tenant** nếu họ cần proxy, auth, cookies hoặc SSL configuration khác nhau.

**Chi tiết phiên bản:** Trong **Java 17**, `HttpClient` không có vòng đời `AutoCloseable`/`close()` giống các API mới hơn; không viết `try (HttpClient client = ...)` rồi khẳng định code đó chạy ở JDK 17. Hai ví dụ bên dưới để client được quản lý bởi runtime và đóng server thử nghiệm; không giả định API `close()` xuất hiện trên Java 17.

## 4. Tạo HttpRequest: URI, HTTP method, headers, timeout

Một GET request:

~~~java
HttpRequest get = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/items?page=1"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Một POST gửi UTF-8:

~~~java
String json = "{\"name\":\"An\",\"active\":true}";

HttpRequest post = HttpRequest.newBuilder(
                URI.create("https://api.example.com/items"))
        .timeout(Duration.ofSeconds(10))
        .header("Content-Type", "application/json; charset=utf-8")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
~~~

Cả hai là **snippets**, dùng hostname minh họa và cần imports `java.net.URI`, `java.net.http.HttpRequest`, `java.time.Duration`, `java.nio.charset.StandardCharsets`. Không tự gửi mạng cho tới khi truyền request vào `HttpClient.send/sendAsync`.

Một số method:
- `GET()` — request không có body, thường để lấy tài nguyên.
- `POST(BodyPublisher)` — gửi body đến endpoint, thường tạo mới/thực hiện hành động theo API.
- `PUT(BodyPublisher)` — gửi body để cập nhật/thay thế tài nguyên theo HTTP contract.
- `DELETE()` — tạo yêu cầu DELETE không có body.
- `method("PATCH", publisher)` — dùng method khác như PATCH theo giao thức/đích hỗ trợ.
- `header(name, value)` **thêm** giá trị header, trong khi `setHeader(name, value)` đặt/thay giá trị trên builder. Tên và giá trị phải hợp lệ.

**URI khác URL string tùy tiện:** `URI.create(...)` không tự percent-encode dữ liệu người dùng được nối vào đường dẫn hay query. Nếu chèn query parameter động, hãy encode đúng ngữ cảnh. `URLEncoder` chủ yếu tạo dạng `application/x-www-form-urlencoded`; không nên dùng máy móc để ghép toàn bộ URL path. Đặc biệt không cộng chuỗi rồi đưa host tùy ý do người dùng nhập vào mà không kiểm tra scheme/host/IP để tránh SSRF.

### Request timeout không giống connect timeout

`HttpRequest.Builder.timeout(Duration)` đặt thời hạn cho request. Nó **không** thay thế connect timeout toàn client, và connect timeout cũng **không** giới hạn các giai đoạn response body theo cách bạn kỳ vọng. Môi trường production nên có cả timeout policy và retry/backoff được thiết kế theo nghiệp vụ.

## 5. BodyPublisher: dữ liệu đi ra ở request

`HttpRequest.BodyPublisher` mô tả **cách cung cấp bytes** của request body cho client. Những factory phổ biến:

| Factory | Dùng khi | Điều cần chú ý |
| --- | --- | --- |
| `BodyPublishers.noBody()` | Method/request không cần body | Không đồng nghĩa là response body cũng rỗng |
| `BodyPublishers.ofString(text, UTF_8)` | JSON, form text, văn bản | UTF-8 quyết định bytes; **Content-Type** header vẫn nên đặt rõ |
| `BodyPublishers.ofByteArray(bytes)` | Payload binary đã nằm trong RAM | Với file lớn cần tránh đưa toàn bộ vào bộ nhớ |
| `BodyPublishers.ofFile(path)` | Upload content từ file trên disk | File phải đọc được; cân nhắc thay đổi file giữa các lần retry |
| `BodyPublishers.ofInputStream(supplier)` | Dữ liệu streaming qua InputStream | Supplier cần hỗ trợ tạo stream mới khi cần replay; quản lý lifecycle |
| `BodyPublishers.fromPublisher(flowPublisher)` | Ghép vào Java Flow pipeline | Chú ý backpressure, content length và khả năng lặp lại |
| `BodyPublishers.concat(...)` | Kết hợp nhiều publishers | Kiểm soát nội dung/length và semantics khi retry |

Ví dụ upload text:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "text/plain; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                "Nội dung", StandardCharsets.UTF_8))
        .build();
~~~

Đây là snippet với biến `uri` đã có. **Đừng lấy `String.length()` làm độ dài byte**: ký tự Unicode có thể có nhiều bytes trong UTF-8. Client/publisher quản lý cách phát bytes của body; đừng gắn `Content-Length` thủ công nếu không có lý do và quy tắc header cho phép.

**BodyPublisher không phải serializer JSON**: `ofString(json)` chỉ chuyển chính chuỗi bạn cung cấp thành bytes; nó không tự kiểm tra JSON hợp lệ và không tự tạo một object JSON từ POJO. Dùng JSON library phù hợp nếu cần serialization/deserialization.

## 6. BodyHandler<T>: dữ liệu đi về ở response

Với `client.send(request, handler)`, handler quyết định kiểu body `T` trong `HttpResponse<T>`.

| BodyHandler | Kiểu response | Khi dùng |
| --- | --- | --- |
| `BodyHandlers.ofString(UTF_8)` | `HttpResponse<String>` | Body text vừa đủ nhỏ, charset đã biết |
| `BodyHandlers.ofByteArray()` | `HttpResponse<byte[]>` | Binary payload nhỏ/vừa |
| `BodyHandlers.ofInputStream()` | `HttpResponse<InputStream>` | Muốn streaming, **phải đọc hoặc đóng stream** |
| `BodyHandlers.ofFile(path)` | `HttpResponse<Path>` | Tải response ra file; xử lý file permissions và status |
| `BodyHandlers.discarding()` | `HttpResponse<Void>` | Không cần giữ body, nhưng vẫn xử lý/loại bỏ response payload |
| `BodyHandlers.ofLines()` | `HttpResponse<Stream<String>>` | Xử lý stream dòng; phải đóng `Stream` |
| `BodyHandlers.ofPublisher()` | `HttpResponse<Flow.Publisher<List<ByteBuffer>>>` | Reactive streaming và downstream backpressure |

Ví dụ:

~~~java
HttpResponse<byte[]> binary =
        client.send(request, HttpResponse.BodyHandlers.ofByteArray());

HttpResponse<String> text =
        client.send(request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
~~~

Đây là hai lời gọi **riêng biệt** trong snippet, không nên gửi trùng một request thay đổi dữ liệu chỉ để đổi kiểu trả về. Với response lớn, `ofByteArray` hay `ofString` có thể buộc tích lũy toàn bộ trong RAM; dùng streaming/file và giới hạn dung lượng theo policy.

**Streaming đặc biệt:** `ofInputStream()` có thể trả response sau khi nhận headers, **trước khi tải hết body**. Caller phải đọc tới EOF **hoặc đóng stream** để giải phóng tài nguyên liên quan. Với `ofLines()`, cần đóng `Stream<String>` theo contract. Không để response stream “trôi” mà không tiêu thụ/đóng.

**BodyHandler mặc định không xét HTTP status code để từ chối body**. `BodyHandlers.ofString()` vẫn có thể đọc toàn bộ body của một HTTP 404 hoặc 500; muốn xử lý theo status, kiểm tra `response.statusCode()` hoặc viết custom handler dựa trên `HttpResponse.ResponseInfo`.

## 7. HttpResponse<T>: status, headers, body, HTTP version và URI

Sau khi gửi request:

~~~java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());

int status = response.statusCode();
HttpHeaders headers = response.headers();
String body = response.body();
HttpClient.Version negotiated = response.version();
URI finalUri = response.uri();
~~~

Trong snippet, `HttpHeaders` thuộc `java.net.http`. Các thuộc tính quan trọng:

- `statusCode()`: mã HTTP, ví dụ 200, 201, 204, 301, 404, 500.
- `headers()`: metadata HTTP response. Có thể đọc `firstValue("Content-Type")` hoặc `allValues("Set-Cookie")`. Giá trị đầu tiên trả `Optional<String>`; header có thể vắng mặt.
- `body()`: kiểu `T` do BodyHandler quyết định, không nhất thiết là String. Với streaming handler, `body()` có thể là stream chưa đọc.
- `version()`: **phiên bản HTTP thực tế dùng cho response**, không nhất thiết bằng preference khi tạo client.
- `uri()`: URI nhận response cuối, có thể khác request URI ban đầu nếu redirect.
- `request()`: request tương ứng response; trong redirect có thể là request đích mới.
- `previousResponse()`: optional intermediate response như redirect/auth, không phải lúc nào cũng tồn tại.
- `sslSession()`: optional TLS session metadata với HTTPS, thường rỗng cho HTTP thuần.

### 200 khác 404 như thế nào đối với HttpClient?

**HTTP error status không phải IOException mặc định.** Nếu server trả `404 Not Found` hợp lệ, `client.send(...)` thường hoàn tất và bạn nhận `HttpResponse<T>` có `statusCode() == 404`. Chỉ khi xảy ra lỗi network/protocol, deadline, TLS hoặc hệ thống I/O mới có exception.

Vì vậy hãy tự phân loại:

~~~java
int code = response.statusCode();
if (code >= 200 && code < 300) {
    // Thành công theo HTTP status policy thường gặp.
} else if (code >= 400 && code < 500) {
    // Client error: 400, 401, 403, 404, 429, ...
} else if (code >= 500) {
    // Server error: 500, 502, 503, ...
} else {
    // 1xx, 3xx hoặc status khác tùy flow và redirect policy.
}
~~~

Đây là snippet, không phải bộ HTTP policy hoàn chỉnh. Một số mã 3xx có thể được auto-follow; 204 không có response body; API cần hiểu nghiệp vụ riêng. Không tự mặc định mọi 4xx đều retry.

## 8. Gửi đồng bộ với HttpClient.send(...)

API:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
~~~

`send(...)` **chặn thread gọi** cho đến khi operation đã hoàn tất theo semantics của BodyHandler. Với `ofString`, body đã được xử lý thành String trước khi response trả về. Với streaming handlers, một số dữ liệu body còn được tiêu thụ sau khi metadata xuất hiện.

Các exception cần nắm:
- `IOException`: có thể do DNS/network/TLS/protocol/timeout theo loại lỗi.
- `InterruptedException`: thread đang chờ bị interrupt; HTTP exchange có thể đã gửi request hoặc chưa hủy hoàn toàn ở network.
- `HttpTimeoutException`: timeout của request.
- `HttpConnectTimeoutException`: timeout khi thiết lập kết nối, là một nhánh chuyên biệt của timeout HTTP.

Mẫu xử lý interrupt trong phương thức nghiệp vụ:

~~~java
try {
    return client.send(request, HttpResponse.BodyHandlers.ofString());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw e;
}
~~~

Đây là snippet đặt trong method trả `HttpResponse<String>` và khai báo `throws IOException, InterruptedException`. Khôi phục interrupt flag khi bạn quyết định propagate phù hợp; không nuốt interrupt rồi tiếp tục retry vô hạn.

**Khi dùng:** Đơn giản, rõ ràng cho số lượng yêu cầu nhỏ hoặc code chạy trên thread chấp nhận chờ. Với nhiều requests cần overlap, `sendAsync` tránh block trực tiếp ở lời gọi gửi.

## 9. Ví dụ 1 — Java 17+: GET và POST trên server localhost

Ví dụ tự tạo HTTP server nhỏ trong **cùng tiến trình**, không cần Internet:

- Server thử nghiệm dùng `com.sun.net.httpserver.HttpServer` từ **module `jdk.httpserver`**, khác module client `java.net.http`. Đây chỉ là fixture cho bài thực hành, không phải HTTP server production.
- Server bind `127.0.0.1` và **port 0**; hệ điều hành chọn cổng trống.
- GET `/hello` trả 200 + `"hello"`.
- POST `/echo` đọc body request rồi trả 201 + `"echo:"` + body.
- Client đặt HTTP/1.1 để stdout không phụ thuộc HTTP/2 negotiation; kiểm tra status, body, header và negotiated version.

Tạo file **`HttpClientLocalDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpClientLocalDemo {
    private static void respond(
            HttpExchange exchange, int status, String text)
            throws IOException {

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static void hello(HttpExchange exchange)
            throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "wrong method");
            return;
        }
        respond(exchange, 200, "hello");
    }

    private static void echo(HttpExchange exchange)
            throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "wrong method");
            return;
        }

        byte[] content = exchange.getRequestBody().readAllBytes();
        respond(exchange, 201, "echo:" + new String(
                content, StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/hello", exchange -> {
            try {
                hello(exchange);
            } catch (IOException e) {
                exchange.close();
            }
        });
        server.createContext("/echo", exchange -> {
            try {
                echo(exchange);
            } catch (IOException e) {
                exchange.close();
            }
        });

        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            HttpRequest get = HttpRequest.newBuilder(
                            base.resolve("/hello"))
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    get, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println("GET status: " + response.statusCode());
            System.out.println("GET body: " + response.body());
            System.out.println("GET Content-Type: "
                    + response.headers()
                    .firstValue("content-type").orElse("-"));
            System.out.println("GET version: " + response.version());

            HttpRequest post = HttpRequest.newBuilder(
                            base.resolve("/echo"))
                    .timeout(Duration.ofSeconds(3))
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "greeting", StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> posted = client.send(
                    post, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println("POST status: " + posted.statusCode());
            System.out.println("POST body: " + posted.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch/chạy từ thư mục chứa file, trên **JDK 17+**:

~~~bash
javac -encoding UTF-8 HttpClientLocalDemo.java
java HttpClientLocalDemo
~~~

**Stdout đã kiểm tra trên JDK tương thích Java 17:**

~~~text
GET status: 200
GET body: hello
GET Content-Type: text/plain; charset=utf-8
GET version: HTTP_1_1
POST status: 201
POST body: echo:greeting
~~~

**Cơ chế xảy ra:**

1. Server tạo socket HTTP loopback trên cổng tạm thời; không chạm mạng Internet.
2. `HttpClient` được build **một lần** cho cả GET và POST, với HTTP/1.1 tường minh.
3. `HttpRequest get` có URI và request timeout riêng; `GET()` là request không body.
4. `client.send(get, BodyHandlers.ofString(UTF_8))` chuyển HTTP response bytes thành `HttpResponse<String>`.
5. `response.statusCode()` = 200, `body()` = `"hello"`, `headers().firstValue(...)` lấy một header có thể thiếu, ở đây được server đặt.
6. POST dùng `BodyPublishers.ofString("greeting", UTF_8)`, thêm `Content-Type`; server đọc bytes và phản hồi HTTP 201.
7. `finally` đóng fixture server bằng `server.stop(0)`, không gọi phương thức `HttpClient.close()` (không có trên Java 17).

**Giới hạn ví dụ:** Server dùng `readAllBytes()` mà không giới hạn request size chỉ vì nó là fixture localhost điều khiển hoàn toàn bởi bài test. Không áp dụng cách này cho server public khi không có giới hạn bytes, deadline và xử lý method/header nghiêm ngặt.

Nếu viết ứng dụng có **`module-info.java`** với named module, khai báo quan hệ module:

~~~java
module http.training {
    requires java.net.http;
    requires jdk.httpserver; // Chỉ cần vì fixture server ở ví dụ.
}
~~~

Khi biên dịch chương trình dạng classpath/unnamed module với JDK phù hợp, không cần thêm `module-info.java`. Client API thực tế nằm trong **`java.net.http`**, còn `jdk.httpserver` chỉ để dựng server localhost phục vụ demo.

## 10. Gửi bất đồng bộ bằng sendAsync và CompletableFuture

API:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
~~~

Lời gọi `sendAsync(...)` trả **`CompletableFuture`** để mô tả kết quả HTTP operation. Thường không block thread gọi tại bước bắt đầu request; response được hoàn tất khi đủ dữ liệu theo BodyHandler.

Có thể nối các phép biến đổi:

~~~java
CompletableFuture<String> bodyFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(HttpResponse::body);
~~~

Hoặc chờ một nhóm requests:

~~~java
CompletableFuture<?> all =
        CompletableFuture.allOf(firstFuture, secondFuture, thirdFuture);
all.join(); // Chỉ block tại vị trí đang chờ kết quả.
~~~

Các đoạn trên là **snippets**, giả định `client`, `request` và các futures đã khai báo/import phù hợp. `join()` có thể ném `CompletionException` khi một future thất bại. `get()` có thể ném `ExecutionException` / `InterruptedException`, hoặc `TimeoutException` nếu dùng overload có deadline.

**Bất đồng bộ không có nghĩa ứng dụng bỏ qua xử lý kết quả:** request có thể thất bại; không “fire-and-forget” rồi mất exception, không bỏ futures khi nghiệp vụ cần response.

**Không mặc định thứ tự hoàn tất = thứ tự gửi.** Nếu gửi ba yêu cầu song song, callback nhận kết quả theo tiến độ của server/network; muốn in có thứ tự, lưu future theo thứ tự request rồi đọc kết quả sau `allOf`.

## 11. Ví dụ 2 — Java 17+: ba requests đồng thời và status 404

Chương trình này dùng server localhost có endpoint `/item/{id}`:
- `/item/1`, `/item/2`, `/item/3` trả body `item-1`, `item-2`, `item-3` với HTTP 200.
- `/item/99` trả HTTP **404**, vẫn là một `HttpResponse<String>` hợp lệ.
- Client gửi ba request đầu bằng `sendAsync`; chờ cả nhóm; in kết quả theo thứ tự đã tạo, không phụ thuộc completion order.
- Request cuối cho thấy lỗi HTTP status không tự chuyển thành I/O exception.

Tạo file **`HttpClientAsyncDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class HttpClientAsyncDemo {
    private static void respond(
            HttpExchange exchange, int status, String body)
            throws IOException {

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/item/", exchange -> {
            try {
                String id = exchange.getRequestURI().getPath()
                        .substring("/item/".length());

                if (Arrays.asList("1", "2", "3").contains(id)) {
                    respond(exchange, 200, "item-" + id);
                } else {
                    respond(exchange, 404, "missing");
                }
            } catch (IOException e) {
                exchange.close();
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            List<CompletableFuture<HttpResponse<String>>> replies =
                    new ArrayList<>();

            for (int id = 1; id <= 3; id++) {
                HttpRequest request = HttpRequest.newBuilder(
                                URI.create("http://127.0.0.1:"
                                        + port + "/item/" + id))
                        .timeout(Duration.ofSeconds(3))
                        .GET()
                        .build();

                replies.add(client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8)));
            }

            CompletableFuture.allOf(
                    replies.toArray(new CompletableFuture<?>[0]))
                    .get(4, TimeUnit.SECONDS);

            for (int i = 0; i < replies.size(); i++) {
                HttpResponse<String> response = replies.get(i).join();
                System.out.println("Async " + (i + 1) + ": "
                        + response.statusCode() + " " + response.body());
            }

            HttpRequest absent = HttpRequest.newBuilder(
                            URI.create("http://127.0.0.1:"
                                    + port + "/item/99"))
                    .GET()
                    .build();

            HttpResponse<String> missing = client.sendAsync(
                    absent, HttpResponse.BodyHandlers.ofString())
                    .get(3, TimeUnit.SECONDS);

            System.out.println("Missing status: " + missing.statusCode());
            System.out.println("Missing is success: "
                    + (missing.statusCode() >= 200
                    && missing.statusCode() < 300));
        } finally {
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 HttpClientAsyncDemo.java
java HttpClientAsyncDemo
~~~

**Kết quả đã kiểm tra:**

~~~text
Async 1: 200 item-1
Async 2: 200 item-2
Async 3: 200 item-3
Missing status: 404
Missing is success: false
~~~

Giải thích:
- Ba lời gọi `sendAsync` được **khởi tạo** trước khi chờ `allOf`, nên chúng có thể cùng in-flight; điều này không chứng minh server xử lý trên ba threads hay HTTP/2 multiplexing (demo chọn HTTP/1.1).
- `allOf(...).get(4, SECONDS)` là điểm đồng bộ để main không kết thúc trước khi ba responses xong.
- Vòng `for` đọc futures theo index, vì vậy output có thứ tự ổn định dù thời điểm completion không được đảm bảo.
- Server nhận `/item/99` và trả **404**. Client vẫn đọc `HttpResponse<String>`, kiểm tra `statusCode()` rồi tính success theo quy tắc 2xx.
- Trong thực tế, `CompletableFuture.allOf` có thể hoàn tất lỗi nếu một request/network operation thất bại; code cần xử lý `ExecutionException`/`CompletionException` và dọn các tasks liên quan. Bài test đơn giản cho đường thành công và HTTP 404.
- Demo chọn cổng ngẫu nhiên và không dùng Internet, thích hợp để chạy đi chạy lại; trên môi trường sandbox cấm TCP loopback, có thể gặp I/O exception thay vì stdout trên.

## 12. Timeout và exception: đừng nhầm HTTP error với I/O failure

Có ít nhất **ba lớp tình huống** khác nhau:

| Tình huống | API quan sát | Diễn giải |
| --- | --- | --- |
| Server trả HTTP 404 hoặc 500 hợp lệ | `response.statusCode()` | Request đã có HTTP response; tự phân loại nghiệp vụ |
| Không thể kết nối/truyền hoặc TLS handshake lỗi | `IOException` hay future hoàn tất lỗi | Không có response HTTP thành công theo flow bình thường |
| Connect hoặc request vượt thời gian | `HttpConnectTimeoutException` / `HttpTimeoutException` theo giai đoạn | Timeouts không chứng minh server chưa xử lý request |

Cấu hình ở hai mức:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(7))
        .GET()
        .build();
~~~

`connectTimeout` áp dụng khi client cần **tạo kết nối mới**; nếu kết nối đã được dùng lại thì không phải mọi request đều thực hiện TCP connect mới. `request.timeout` là giới hạn request theo API; không nên suy ra sẽ luôn dừng mọi xử lý trên remote server ngay thời điểm deadline.

Trong async flow:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .whenComplete((response, error) -> {
            if (error != null) {
                // Unwrap CompletionException nếu cần, ghi log phù hợp.
            } else {
                // Vẫn cần kiểm tra response.statusCode().
            }
        });
~~~

Đây là snippet; callback lỗi không có `HttpResponse` như đường thành công. `CompletableFuture.cancel(...)` và timeout trên future không được xem như xác nhận remote đã hủy request. Với POST thay đổi dữ liệu, retry sau timeout có thể tạo tác dụng **lặp** dù lần gửi đầu đã được server xử lý.

Phân loại ngoại lệ thường thấy:
- `UnknownHostException` hoặc `ConnectException` khi DNS/kết nối thất bại (nguồn gốc cụ thể tùy OS).
- `SSLHandshakeException` khi TLS trust/cipher/identity handshake không hợp lệ.
- `HttpConnectTimeoutException` nếu tạo connection mới vượt hạn.
- `HttpTimeoutException` nếu HTTP request vượt timeout được cấu hình.
- `InterruptedException` trong đường `send` khi thread chờ bị interrupt.
- `ExecutionException`/`CompletionException` khi dùng `get/join` trên async future bị lỗi; cần xem nguyên nhân gốc.
- HTTP 401/403/404/429/500 **không mặc định** là Java exception.

## 13. HTTP/1.1 và HTTP/2: preference khác negotiated version

`HttpClient.Version` có ít nhất `HTTP_1_1` và `HTTP_2` trong Java 17. Chọn:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

chỉ là **ưu tiên** khi có thể. Server, proxy, TLS/ALPN, khả năng upgrade và các ràng buộc của implementation ảnh hưởng phiên bản thực tế. Khi yêu cầu HTTP/2 mà không thể sử dụng, Java client có thể quay về HTTP/1.1.

Kiểm tra:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

System.out.println(response.version());
~~~

Nếu cần kiểm chứng HTTP/2 hoạt động, **đọc phiên bản từ response** và thử với endpoint thực hỗ trợ; không suy đoán từ `client.version()`. HTTP/2 hỗ trợ multiplexed streams trên kết nối phù hợp, nhưng API `sendAsync` của client vẫn có thể dùng với HTTP/1.1. Ngược lại, `send` là synchronous call từ phía Java dù transport chọn HTTP/2.

Trong hai demo localhost, dùng HTTP/1.1 để kết quả ổn định vì fixture `HttpServer` là HTTP server đơn giản, không cần implement HTTP/2. Đây là quyết định **kiểm thử**, không phải kết luận Java HttpClient thiếu hỗ trợ HTTP/2.

## 14. Redirect, cookie, authentication, proxy và HTTPS

Những cấu hình ở **mức client**:

~~~java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
~~~

Về redirects:
- `NEVER` không tự follow.
- `NORMAL` cho phép follow theo quy tắc API, không tự follow downgrade HTTPS → HTTP.
- `ALWAYS` có policy rộng hơn; không nên mặc định bật cho code xử lý dữ liệu/credential nhạy cảm.
- Nếu follow, `response.uri()` có thể khác request ban đầu, và `previousResponse()` giúp truy vết response trung gian.
- Redirect vượt host có thể làm thay đổi security boundary; không gửi bearer token/cookie tới host mới nếu chưa kiểm tra policy.

Về cookies:
- Một `CookieManager`/`CookieHandler` có thể được cung cấp bằng `HttpClient.Builder.cookieHandler(...)`.
- Không mặc định mọi cookie response đều được ghi nhớ/gửi lại nếu không cấu hình phù hợp.
- Khi chia sẻ client, cân nhắc **phân vùng cookies** theo người dùng/tenant để tránh rò rỉ session.

Về credentials:
- Dùng `Authenticator` của client khi phù hợp với authentication challenge; API auth không đồng nghĩa mọi loại token/API key đều được tự tạo.
- Với bearer token, ứng dụng có thể đặt `Authorization: Bearer ...` trên từng request sau khi quản lý token an toàn.
- Không hardcode secrets vào source, không log nguyên văn Authorization, Cookie hoặc body chứa dữ liệu cá nhân.
- HTTPS/TLS dùng trust configuration của runtime hoặc `SSLContext` được cấu hình; **không dùng trust-all certificate manager** để “chữa” lỗi TLS trên production.

Về proxy:
- Dùng `HttpClient.Builder.proxy(ProxySelector)` khi cần chính sách proxy.
- Proxy, DNS và redirects có thể thay đổi nơi request thực sự tới; không coi URI ban đầu là kiểm soát truy cập đủ mạnh nếu có untrusted destinations.

## 15. Xử lý response body lớn, streaming và tài nguyên

Một lỗi thường gặp là dùng `BodyHandlers.ofString()` hoặc `ofByteArray()` cho response có thể rất lớn. Điều đó có thể gây memory pressure/OOM. Chọn handler theo nhu cầu:

~~~java
HttpResponse<java.io.InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (java.io.InputStream in = response.body()) {
    // Đọc dần và giới hạn tổng số byte theo policy.
}
~~~

Đây là snippet cần imports và `client/request` đã tạo. Với streaming body:
- **Đọc tới EOF hoặc đóng `InputStream`** nếu không đọc hết.
- Bắt `IOException` trong quá trình tiêu thụ body, không chỉ trong giai đoạn request headers.
- Đặt giới hạn bytes/chunk/time trên content không tin cậy.
- Nếu lưu file, chọn path hợp lệ, tránh overwrite tùy ý/đường dẫn do remote cung cấp và validate nội dung.
- Một số BodyHandlers trả về response sau headers, trước khi body được tiêu thụ hết; ứng dụng phải quản lý vòng đời streaming riêng.

Ví dụ `BodyHandlers.ofFile(path)` trả `HttpResponse<Path>` khi đã xử lý body xuống file theo contract. Không nhầm response body type này với `String`. Với text body, nếu chưa biết encoding, kiểm tra `Content-Type` và quy tắc ứng dụng trước khi decode. JSON chủ yếu dùng UTF-8, nhưng điều đó không có nghĩa mọi `text/*` response là UTF-8.

**Backpressure:** Trong `Flow.Publisher/Subscriber`, tốc độ tiêu thụ phải được kiểm soát; custom subscribers không được block hoặc cấp phát không giới hạn trên thread quan trọng. Chỉ chuyển sang reactive streaming khi bạn thực sự cần và hiểu lifecycle, error handling, cancellation.

## 16. Retry, idempotency và tính lặp lại của request body

Không phải mọi HTTP request đều có thể retry an toàn.

- `GET` thường có tính chất idempotent theo HTTP, nhưng backend/side effects bên ngoài vẫn cần xem xét.
- `PUT` và `DELETE` có semantics idempotent theo HTTP khi server tuân thủ.
- `POST` có thể tạo tài nguyên/thay đổi dữ liệu; gửi lại có thể nhân đôi tác dụng nếu thiếu idempotency key.
- `429 Too Many Requests` hoặc `503 Service Unavailable` có thể yêu cầu backoff và đọc `Retry-After` theo policy; không retry không giới hạn.
- Timeout hay connection reset **không** chứng minh server chưa xử lý request.
- Một `BodyPublisher` đọc từ nguồn không thể tua lại (one-shot stream) có thể không phát lại được khi request cần retry hoặc authentication/redirect. Cần supplier tạo stream mới phù hợp hoặc chuyển sang nguồn repeatable.

Gợi ý retry policy:
1. Xác định loại operation và khả năng idempotent của nghiệp vụ.
2. Giới hạn số lần và tổng deadline.
3. Dùng backoff có jitter và tôn trọng server load.
4. Chỉ retry khi request body có thể phát lại.
5. Theo dõi request ID/idempotency token ở cả hai phía nếu cần tránh double-processing.
6. Log ngữ cảnh an toàn (method, sanitized host/path, status, latency, attempt count) nhưng không log secrets.

Không dùng một `HttpClient` có tự động retry mọi lỗi theo cách bạn chưa kiểm tra; khi semantics nghiệp vụ quan trọng, ứng dụng cần kiểm soát retry ở tầng cao hơn.

## 17. Lưu ý bảo mật: SSL, SSRF và kiểm soát URL

Một client HTTP có thể trở thành điểm rủi ro nếu server backend nhận **URL do người dùng cung cấp** rồi tự fetch:

- Kiểm tra **scheme**: thường chỉ cho phép `https` (hoặc `http` cho môi trường local được kiểm soát).
- Dùng **allowlist** host/service khi có thể; validate hostname sau canonicalization và kiểm soát DNS rebinding/IP private/loopback/link-local theo mô hình an ninh.
- Không cho untrusted request fetch tới metadata endpoints/cloud credentials hay dịch vụ nội bộ không được phép.
- Khi bật auto redirects, phải tái kiểm tra **destination sau redirect**; tránh chuyển từ public host sang private endpoint.
- Giới hạn response bytes, timeout, số redirects, số request đồng thời và kích thước output.
- Đảm bảo TLS certificate/hostname verification đang hoạt động; không disable khi gặp lỗi môi trường.
- Không log URI có chứa token trong query hay Authorization header/cookies.
- Nếu dùng proxy, đánh giá nơi proxy có thể truy cập và có làm lộ credentials hay không.

**Ví dụ localhost trong bài chỉ để kiểm chứng API**; trên production nên dùng HTTPS, authentication, request/response validation, giới hạn tài nguyên và policy outbound network phù hợp. `HttpClient` không thay thế authorization logic của dịch vụ.

## 18. Hiệu năng và thiết kế ứng dụng

Những quyết định ảnh hưởng hiệu quả khi gọi HTTP thường xuyên:
- **Reuse client:** Tránh tạo mới `HttpClient` cho mỗi request. Connection reuse giảm overhead trong nhiều trường hợp.
- **Bound concurrency:** `sendAsync` cho phép nhiều in-flight requests, nhưng nếu khởi tạo không giới hạn có thể bão hòa peer, executor và bộ nhớ.
- **Keep operations short:** Không block lâu trong callbacks của future mà không có chủ đích; dùng executor riêng cho logic CPU/DB lớn nếu cần.
- **Choose body handler:** Không gom response lớn vào `String` hay `byte[]` nếu có thể stream.
- **Timeout policy:** Phân biệt connect timeout, request timeout, timeout chờ kết quả của layer ngoài và deadline tổng của nghiệp vụ.
- **Separate auth contexts:** Không chia sẻ cookies/tokens across users hay tenants không có cách ly.
- **Observe metrics:** Method, sanitized host, HTTP status, latency, retries, timeout cause, response size và negotiated protocol version.
- **Respect interrupts:** Với synchronous `send`, không nuốt `InterruptedException` hoặc retry một request đã có side effects một cách âm thầm.

Một API bất đồng bộ không làm network nhanh hơn về mặt vật lý; lợi ích là dễ điều phối **nhiều requests đang chờ** mà không phải block thread khởi tạo request. HTTP/2 có thể giảm kết nối cần dùng trong tình huống phù hợp, nhưng throughput còn tùy server, bandwidth, flow control và TLS.

## 19. Những sai lầm phổ biến

| Sai lầm | Triệu chứng hoặc hậu quả | Cách sửa |
| --- | --- | --- |
| Tưởng `HttpClient` chứa một URL cố định | Tạo nhiều client không cần thiết | Một client có thể gửi nhiều `HttpRequest` khác nhau |
| Tưởng `HttpRequest` thực thi ngay lúc `build()` | Không thấy network call | Gọi `client.send` hoặc `sendAsync` |
| Nhầm `BodyPublisher` với `BodyHandler` | Encode/decode sai chiều | Publisher cho request; handler cho response |
| Gọi `response.body()` luôn trả String | ClassCast/logic sai với byte[], Path, InputStream | Chọn đúng `HttpResponse<T>` và handler |
| Tin HTTP 404 tự ném IOException | Bỏ qua response error body/status | Kiểm tra `statusCode()` của response |
| Gọi `sendAsync` rồi bỏ future | Không biết request thành công/lỗi | Nối callback, collect futures, log và cleanup |
| Tin `sendAsync` đảm bảo thứ tự hoàn tất | Dữ liệu xử lý không đúng thứ tự | Gắn correlation ID/đọc futures theo yêu cầu |
| Set `version(HTTP_2)` và tin response luôn HTTP/2 | Chẩn đoán sai protocol | Đọc `response.version()` |
| Không cấu hình request timeout | Có thể chờ vượt deadline nghiệp vụ | Thiết lập timeouts và retry policy |
| Tưởng timeout chứng minh server chưa xử lý POST | Retry nhân đôi tác dụng | Idempotency token, giới hạn retry |
| Dùng `ofString()` cho body khổng lồ | OOM hoặc memory pressure | Streaming/file handler, giới hạn kích thước |
| Không đóng `BodyHandlers.ofInputStream()` stream | Rò rỉ resources / kết nối bị giữ | Đọc EOF hoặc close stream |
| Không đặt Content-Type cho JSON | Server giải mã/validate sai | Đặt header và encoding phù hợp |
| Nối query/path trực tiếp từ input | URL sai hoặc SSRF | Encode đúng ngữ cảnh, allowlist URL |
| Dùng `try-with-resources` cho HttpClient trên Java 17 | Không biên dịch vì thiếu AutoCloseable API | Kiểm tra phiên bản JDK; Java 17 chỉ reuse client |
| Dùng trust-all SSL manager để qua lỗi cert | Mất xác thực peer, dễ MITM | Dùng trust store/cert hợp lệ |
| Tự follow redirect tới host ngoài trust boundary | Rò credentials hoặc SSRF | Kiểm tra redirect và auth policy |
| Gửi requests async không giới hạn | Quá tải server và client | Semaphore/rate limit/queue có giới hạn |

## 20. Câu hỏi tự kiểm tra

**1.** Ba kiểu cốt lõi của Java HTTP Client API giữ vai trò nào?  
**Đáp án:** `HttpClient` quản lý cấu hình/vận hành, `HttpRequest` mô tả request, `HttpResponse<T>` chứa HTTP metadata và body kiểu `T`.

**2.** `HttpRequest.newBuilder(...).GET().build()` có gửi network request ngay không?  
**Đáp án:** Không. Phải gọi `HttpClient.send` hoặc `sendAsync`.

**3.** `BodyPublishers.ofString(...)` và `BodyHandlers.ofString(...)` khác nhau?  
**Đáp án:** Publisher mã hóa request body để gửi đi; Handler giải mã/tạo String từ response body.

**4.** Một HTTP server trả 404 hợp lệ. `client.send` chắc chắn ném `IOException` không?  
**Đáp án:** Không. Thường nhận được `HttpResponse` có `statusCode() == 404`.

**5.** `HttpClient.Version.HTTP_2` có đảm bảo nhận response HTTP/2 không?  
**Đáp án:** Không. Cần đọc `response.version()`; server/proxy/negotiation có thể dẫn tới HTTP/1.1.

**6.** `sendAsync` trả kiểu gì và có tự block caller như `send` không?  
**Đáp án:** Trả `CompletableFuture<HttpResponse<T>>` để xử lý completion, lời gọi gửi không block chờ toàn response như `send`.

**7.** `Future.get(3, SECONDS)` timeout chứng minh server chưa xử lý POST không?  
**Đáp án:** Không. Timeout chờ kết quả không đảm bảo remote hủy thao tác; cần idempotency/retry policy.

**8.** Vì sao không nên dùng `BodyHandlers.ofByteArray()` cho tệp không giới hạn kích thước?  
**Đáp án:** Vì có thể gom toàn bộ vào RAM; chọn stream/file và giới hạn tài nguyên.

**9.** Với `ofInputStream()`, nhận được `HttpResponse<InputStream>` nghĩa là body đã đọc hết chưa?  
**Đáp án:** Chưa chắc. Cần đọc cho đến EOF hoặc đóng stream.

**10.** Default redirect policy của Java 17 `HttpClient` là gì?  
**Đáp án:** `NEVER` trừ khi được cấu hình khác.

**11.** Có nên tạo một client mới cho từng GET tới cùng service không?  
**Đáp án:** Thường không. Reuse client để chia sẻ cấu hình và tài nguyên.

**12.** Bài test localhost dùng `com.sun.net.httpserver.HttpServer` thuộc module nào?  
**Đáp án:** `jdk.httpserver`, chỉ làm HTTP server thử nghiệm; ba kiểu client thuộc `java.net.http`.

**13.** Tại sao nội dung `Content-Type: application/json` không biến một chuỗi bất kỳ thành JSON hợp lệ?  
**Đáp án:** Header khai báo loại dữ liệu; `BodyPublisher` không tự serialize hoặc validate JSON.

**14.** Nếu request URL do người dùng gửi vào backend, rủi ro gì ngoài lỗi URI?  
**Đáp án:** SSRF, DNS rebinding, truy cập dịch vụ nội bộ và redirects sang host không tin cậy; cần policy outbound/allowlist và giới hạn mạng.

## Tài liệu tham khảo chính thức

- [Java SE 17 — Module java.net.http](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/module-summary.html): module và các API HTTP client/WebSocket.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client builder, cấu hình, send/sendAsync, versions và thread safety.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): connectTimeout, redirect, preferred version, proxy, executor.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): URI, method, headers và body publisher.
- [Java SE 17 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): string, bytes, file, streams, Flow publisher.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): statusCode, headers, body, uri, version và previousResponse.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): xử lý string/bytes/file/stream và resource lifecycle.
- [Java SE 17 — HttpHeaders](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html): truy cập response headers bằng Optional và danh sách giá trị.
- [Java SE 17 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html) và [HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html): các loại HTTP timeout.
- [Java SE 17 — jdk.httpserver module](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): fixture HTTP server nhỏ dùng trong hai chương trình local.
