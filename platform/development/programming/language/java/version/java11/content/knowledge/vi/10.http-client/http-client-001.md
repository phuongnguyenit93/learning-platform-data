# java.net.http và HTTP Client chuẩn của Java 11+

## 1. Vì sao Java 11 có HTTP Client chuẩn?

Trong ứng dụng Java, **HTTP client** là thành phần chủ động gửi yêu cầu đến một HTTP server rồi nhận phản hồi: đọc API REST, gửi JSON, tải tài liệu, gọi dịch vụ nội bộ hoặc trao đổi dữ liệu với một endpoint từ xa.

Từ **Java 11**, module **`java.net.http`** cung cấp API HTTP Client chuẩn, ổn định và vẫn được sử dụng trong Java hiện đại. Bộ API này hỗ trợ:

- **HTTP/1.1 và HTTP/2**, với khả năng thương lượng giao thức; không phải mọi server đều sử dụng HTTP/2.
- **Gửi đồng bộ** bằng `send(...)` và **bất đồng bộ** bằng `sendAsync(...)` dựa trên `CompletableFuture`.
- Tạo request qua builder: URL/URI, phương thức GET/POST/PUT/DELETE, header, timeout và request body.
- Chọn cách nhận response body: `String`, `byte[]`, file, stream hoặc bỏ qua nội dung.
- Cấu hình kết nối, redirect, proxy, cookie, TLS, xác thực và executor khi bài toán cần.

Ví dụ Java 11 **không cần thư viện HTTP bên thứ ba**:

```java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/")).GET().build();
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Đoạn trên là **mảnh mã trong một phương thức** đã khai báo hoặc xử lý `IOException` và `InterruptedException`; cần import `java.net.URI` và các kiểu `java.net.http`. Nó cần Internet để gửi yêu cầu thật. Ví dụ độc lập ở mục 7 sử dụng HTTP server cục bộ, giúp biên dịch/chạy và xác minh kết quả mà **không phụ thuộc mạng ngoài**.

**Phạm vi:** bài học tập trung vào API HTTP Client công khai trong Java 11 trở lên. Không dùng hướng dẫn về một phiên bản HTTP Client thử nghiệm cũ, không thay `HttpClient` bằng `HttpURLConnection` chỉ vì thói quen và không giả định các phương thức quản lý vòng đời được bổ sung ở JDK mới hơn có mặt trong Java 11.

## 2. Năm thành phần chính cần nhớ

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `HttpClient` | Cấu hình và thực hiện request; nên **tái sử dụng**. | `HttpClient.newBuilder().build()` |
| `HttpRequest` | Mô tả **một yêu cầu**: URI, method, header, timeout và body. | `HttpRequest.newBuilder(uri).GET().build()` |
| `HttpResponse<T>` | Kết quả gồm status, headers, URI, protocol version và body kiểu `T`. | `response.statusCode()`, `response.body()` |
| `HttpRequest.BodyPublishers` | Xác định **cách phát nội dung request** lên mạng. | `ofString(json, UTF_8)` |
| `HttpResponse.BodyHandlers` | Xác định **cách tiêu thụ nội dung response**. | `ofString(UTF_8)`, `ofFile(path)` |

Một chu trình điển hình:

```text
URI và dữ liệu nghiệp vụ
        |
        v
HttpRequest.Builder -> HttpRequest
        |                  |
        v                  v
HttpClient cấu hình ---> send(...) / sendAsync(...)
                                |
                                v
                       HttpResponse<T>
                      /       |        \
                 status     headers   body<T>
```

Hai điểm thường gây nhầm:

1. **`HttpRequest` chỉ mô tả yêu cầu**, gọi `build()` không làm phát sinh kết nối mạng.
2. **`HttpResponse<T>` không tự quyết định kiểu body.** Kiểu `T` đến từ `BodyHandler` dùng khi gửi request, ví dụ `ofString` cho `String`, `ofByteArray` cho `byte[]` hoặc `ofInputStream` cho `InputStream`.

## 3. Tạo và tái sử dụng HttpClient

### 3.1. Cấu hình một client

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Đây là đoạn minh họa trong phương thức; cần import `java.net.http.HttpClient` và `java.time.Duration`.

- `version(HTTP_2)` đặt **giao thức ưu tiên**, không đảm bảo kết nối thực tế luôn là HTTP/2. Server, TLS/proxy và khả năng thương lượng có thể khiến request chạy HTTP/1.1. Kiểm tra `response.version()` nếu ứng dụng cần biết phiên bản đã dùng.
- `connectTimeout(...)` giới hạn **thời gian tạo kết nối mới**. Khi tái sử dụng một kết nối đã thiết lập, thiết lập này có thể không phát huy tác dụng. Nó **không phải** giới hạn toàn bộ quá trình nhận response body.
- `followRedirects(NEVER)` không tự theo chuyển hướng. Với builder không chỉ định redirect, chính sách mặc định của Java 11 cũng là `NEVER`. Có thể chọn `NORMAL` nếu nghiệp vụ cho phép, nhưng cần hiểu nơi request sẽ được gửi tiếp và nguy cơ chuyển hướng đến đích không mong muốn.
- `build()` tạo client; muốn gửi yêu cầu thật phải gọi `send` hoặc `sendAsync`.

Cách ngắn gọn:

```java
HttpClient client = HttpClient.newHttpClient();
```

Client mặc định dùng những cấu hình mặc định do JDK cung cấp. Khi cần chính sách timeout/redirect rõ ràng, builder dễ kiểm soát hơn.

### 3.2. Vì sao không tạo client mới cho mọi request?

`HttpClient` quản lý các kết nối mạng và tài nguyên liên quan. **Tái sử dụng một client** có thể giúp tái sử dụng kết nối thay vì thiết lập kết nối mới cho mỗi lần gọi. Một client có thể gửi nhiều request và được thiết kế để chia sẻ giữa các tác vụ.

Ví dụ kiến trúc ứng dụng:

```java
final class ProductApi {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    // Các phương thức trong lớp dùng lại cùng client.
}
```

Đây là **đoạn minh họa**, cần các import tương ứng. Không tạo `HttpClient` trong vòng lặp lớn nếu có thể tái sử dụng; cũng không coi một client là nơi lưu trạng thái nghiệp vụ của từng request.

Trong Java 11, hãy viết code dựa trên bộ API Java 11 thực có. **Không đặt `HttpClient` trực tiếp vào `try-with-resources` trong ví dụ Java 11**: các phương thức quản lý vòng đời bổ sung ở JDK sau không phải điều kiện có thể giả định khi biên dịch cho `--release 11`. Ngược lại, các stream phản hồi mà ứng dụng sở hữu vẫn phải được đóng đúng cách.

## 4. Tạo HttpRequest: URI, method, header và body

### 4.1. Yêu cầu GET

```java
URI uri = URI.create("https://api.example.com/items");
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();
```

Mã minh họa giả định endpoint có tồn tại; không phải lời cam kết URL giả `api.example.com` có API hoạt động.

- `URI` xác định scheme, host, port, path, query...
- `timeout(...)` thuộc **một request**; khác với `connectTimeout` đặt trên client.
- Header `Accept` cho biết loại nội dung client muốn nhận; nó không tự giải mã JSON thành Java object.
- `GET()` mô tả method GET (không có request body).
- `build()` vẫn chưa gửi request.

Khi URI có dữ liệu nhập từ người dùng, **mã hóa đúng cấu trúc URI**. Không nối trực tiếp tên người dùng có khoảng trắng, dấu `&`, `?` hoặc `#` vào query string rồi mong API hiểu chính xác; dùng giải pháp tạo/encode từng thành phần phù hợp với quy ước endpoint. `URI.create(...)` chỉ phân tích cú pháp URI, không tự mã hóa mọi dữ liệu tùy ý.

### 4.2. Yêu cầu POST gửi văn bản hoặc JSON

```java
String json = "{\"name\":\"Lan\",\"active\":true}";
HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items"))
        .timeout(Duration.ofSeconds(10))
        .header("Content-Type", "application/json; charset=utf-8")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
```

Đây là đoạn minh họa trong phương thức; cần import `StandardCharsets` và các kiểu HTTP. `BodyPublishers.ofString(...)` biến `String` thành byte theo charset đã chỉ định, **không** tự xác nhận chuỗi là JSON hợp lệ. `Content-Type` phải phù hợp thực tế body được gửi. Với JSON có cấu trúc phức tạp, nên sử dụng thư viện serialize JSON đáng tin cậy thay vì tự ghép và escape thủ công.

Các phương thức khác:
- `PUT(BodyPublisher)` và `DELETE()` có sẵn trên builder.
- `method(String, BodyPublisher)` cho method tùy chỉnh khi API thực sự yêu cầu.
- `BodyPublishers.noBody()` dùng khi cần chỉ định rõ không gửi nội dung.
- `BodyPublishers.ofByteArray(bytes)`, `ofFile(path)` và `ofInputStream(supplier)` phù hợp với nguồn dữ liệu tương ứng, nhưng phải quản lý kích thước, khả năng đọc lại và lỗi I/O.

**Không mặc định POST an toàn để tự gửi lại** sau timeout: một thao tác tạo đơn hàng/thanh toán có thể đã được server thực hiện dù client chưa nhận phản hồi. Retry phải dựa trên tính *idempotent*, chính sách endpoint và có thể cần idempotency key.

## 5. Gửi đồng bộ bằng send và xử lý status

Cách dùng cơ bản:

```java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

int status = response.statusCode();
String text = response.body();
HttpClient.Version protocol = response.version();
```

Mã minh họa giả định đã có `client` và `request`. `send` **chặn luồng gọi** cho đến khi phần xử lý phản hồi theo `BodyHandler` hoàn thành theo hợp đồng tương ứng. Nó có thể ném `IOException` (lỗi kết nối, truyền dữ liệu, timeout...), `InterruptedException` (luồng bị ngắt) hoặc các lỗi do tham số không hợp lệ.

**HTTP 404, 401, 403, 429 hoặc 500 không tự động là `IOException`.** Đây là **HTTP response thật**, nên phải đọc `statusCode()`:

```java
if (status >= 200 && status < 300) {
    // Xử lý kết quả thành công theo hợp đồng API.
} else if (status == 404) {
    // Tài nguyên không tìm thấy.
} else if (status == 429) {
    // Cần xử lý giới hạn tốc độ theo chính sách phía server.
} else {
    // Xử lý phản hồi không thành công khác.
}
```

Nếu không kiểm tra status, code có thể xem body chứa thông báo lỗi như dữ liệu thành công. Mặt khác, **không chỉ dựa vào 200**: API có thể sử dụng những mã 2xx khác (201, 202, 204...), và một số mã không có body.

Headers đọc qua `response.headers()`, ví dụ:

```java
response.headers().firstValue("Content-Type")
        .ifPresent(System.out::println);
```

Mảnh mã này cần nằm trong phương thức phù hợp. `HttpHeaders` cung cấp các accessor; tên header HTTP không phân biệt hoa/thường. Đừng giả định header luôn có mặt, không in/log dữ liệu nhạy cảm như bearer token, cookie hay giá trị ủy quyền.

## 6. Gửi bất đồng bộ bằng sendAsync

`sendAsync` trả về `CompletableFuture<HttpResponse<T>>`, cho phép tổ chức công việc tiếp theo mà không chặn luồng gọi ngay tại lúc gửi:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

future.thenAccept(response -> {
    System.out.println("HTTP " + response.statusCode());
    System.out.println(response.body());
});
```

Đây là **mảnh mã minh họa**, cần import `java.util.concurrent.CompletableFuture`. Lời gọi `sendAsync` khởi động xử lý bất đồng bộ; callback chỉ thực hiện khi future hoàn thành. Trong ứng dụng ngắn chạy xong `main`, cần có cơ chế chờ/điều phối để không kết thúc chương trình trước khi kết quả được xử lý.

Chẳng hạn `future.join()` chờ và lấy kết quả; nếu giao dịch thất bại, nó ném ngoại lệ runtime bao bọc nguyên nhân (thường `CompletionException`). Với `future.get()`, lỗi bất đồng bộ được báo bằng `ExecutionException`. Có thể dùng `handle` hoặc `whenComplete` để xử lý thành công/thất bại thay vì bỏ qua exception.

**Không coi `sendAsync` là “tự xử lý lỗi”**: timeout, DNS, TLS hoặc I/O vẫn có thể khiến future hoàn thành thất bại. Gọi `join()` trong thread giao diện/ngữ cảnh nhạy cảm với độ trễ có thể lại gây blocking; chọn mô hình phù hợp với ứng dụng.

### Khi nào chọn send, khi nào chọn sendAsync?

| Nhu cầu | `send` | `sendAsync` |
| --- | --- | --- |
| Một lệnh CLI hoặc tác vụ xử lý tuần tự | Dễ hiểu và xử lý lỗi bằng `try/catch`. | Vẫn dùng được, nhưng cần điều phối future. |
| Gọi nhiều API độc lập và ghép kết quả | Có thể làm tuần tự hoặc dùng executor riêng. | Phù hợp với chuỗi `CompletableFuture` và kết hợp tác vụ. |
| Ứng dụng cần tránh giữ thread chờ network | Tự nó chặn thread gọi. | Trả future, không cần chờ ngay. |
| Xử lý lỗi | `IOException`, `InterruptedException` trực tiếp. | Lỗi đi qua completion bất đồng bộ. |
| HTTP 4xx/5xx | Phải kiểm tra `statusCode()`. | Vẫn phải kiểm tra `statusCode()` khi future thành công. |

## 7. Ví dụ Java 11+ hoàn chỉnh, không cần Internet ngoài

Để kết quả có thể tái lập trên máy học, chương trình mở một **HTTP server cục bộ** tại `127.0.0.1` với cổng hệ điều hành tự chọn, rồi dùng **`java.net.http.HttpClient`** thực hiện GET, POST và một request bất đồng bộ nhận lỗi 404.

Phần server chỉ là **fixture kiểm thử** sử dụng `com.sun.net.httpserver.HttpServer` (module JDK `jdk.httpserver`); nó không thay thế HTTP client của bài học. Đối với dự án dùng `module-info.java`, cần khai báo `requires java.net.http;` và, chỉ nếu dùng server fixture như dưới đây, `requires jdk.httpserver;`. Ví dụ đặt trên **classpath** để chạy đơn giản.

Tạo tệp **`StandardHttpClientDemo.java`**:

```java
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

public class StandardHttpClientDemo {
    private static void reply(HttpExchange exchange, int status, String text)
            throws IOException {
        try {
            byte[] payload = text.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(status, payload.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(payload);
            }
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/hello",
                exchange -> reply(exchange, 200, "Xin chào Java 11"));
        server.createContext("/echo", exchange -> {
            if (!"POST".equals(exchange.getRequestMethod())) {
                reply(exchange, 405, "method not allowed");
                return;
            }
            String text = new String(
                    exchange.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);
            reply(exchange, 200, "received:" + text);
        });
        server.createContext("/missing",
                exchange -> reply(exchange, 404, "not found"));
        server.start();

        try {
            URI base = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            HttpRequest get = HttpRequest.newBuilder(base.resolve("/hello"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "text/plain")
                    .GET()
                    .build();
            HttpResponse<String> received =
                    client.send(get, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("get.status=" + received.statusCode());
            System.out.println("get.body=" + received.body());
            System.out.println("get.version=" + received.version());

            HttpRequest post = HttpRequest.newBuilder(base.resolve("/echo"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "dữ liệu", StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> echoed =
                    client.send(post, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("post.status=" + echoed.statusCode());
            System.out.println("post.body=" + echoed.body());

            HttpRequest missing = HttpRequest.newBuilder(
                    base.resolve("/missing")).GET().build();
            CompletableFuture<HttpResponse<String>> future =
                    client.sendAsync(missing, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            HttpResponse<String> absent = future.join();
            System.out.println("missing.status=" + absent.statusCode());
            System.out.println("missing.body=" + absent.body());
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy trên JDK có hỗ trợ mức Java 11:

```bash
javac -encoding UTF-8 --release 11 StandardHttpClientDemo.java
java StandardHttpClientDemo
```

**Kết quả thực tế đã kiểm chứng trên JDK 24 với mục tiêu biên dịch Java 11:**

```text
get.status=200
get.body=Xin chào Java 11
get.version=HTTP_1_1
post.status=200
post.body=received:dữ liệu
missing.status=404
missing.body=not found
```

Giải thích:
- Server sử dụng địa chỉ loopback `127.0.0.1` và cổng tự chọn `0` lúc tạo; sau `start()`, client lấy cổng thực qua `server.getAddress().getPort()`. Chương trình không cần gọi một API Internet bên ngoài.
- `GET /hello` trả văn bản UTF-8; `BodyHandlers.ofString(UTF_8)` chuyển byte phản hồi thành `String`. `version(HTTP_1_1)` được chọn để kết quả ví dụ ổn định.
- `POST /echo` gửi chuỗi tiếng Việt qua `BodyPublishers.ofString(..., UTF_8)` và server trả nội dung `received:dữ liệu`.
- `sendAsync` với `GET /missing` trả `HttpResponse` có status **404**. Future hoàn thành bình thường vì server đã trả phản hồi HTTP hợp lệ; **404 không phải lỗi truyền thông**.
- `finally` đảm bảo dừng server fixture ngay cả khi request gặp lỗi. Ví dụ dùng `throws Exception` để phần mã demo gọn; ứng dụng thật nên phân loại lỗi có chủ đích.

**Quan trọng:** `jdk.httpserver` được dùng ở đây chỉ để **lập endpoint cục bộ có thể kiểm thử**. Trong dự án thực tế khi chỉ là HTTP client, không cần import `com.sun.net.httpserver` hay chạy server.

## 8. BodyPublisher và BodyHandler: chọn theo kích thước dữ liệu

### 8.1. Gửi request body

| `HttpRequest.BodyPublishers` | Khi nào dùng | Lưu ý |
| --- | --- | --- |
| `noBody()` | Request không có body. | Không mang payload. |
| `ofString(text, charset)` | Gửi văn bản hoặc JSON nhỏ. | Encode đúng charset, header `Content-Type` thích hợp. |
| `ofByteArray(bytes)` | Đã có nội dung dạng byte trong bộ nhớ. | Tốn RAM theo dung lượng mảng. |
| `ofFile(path)` | Gửi nội dung từ file. | File phải đọc được; cần xử lý lỗi file/I/O. |
| `ofInputStream(supplier)` | Tạo nguồn stream khi cần. | Supplier có thể được gọi nhiều lần nếu request cần gửi lại; nguồn phải được quản lý đúng. |

### 8.2. Nhận response body

| `HttpResponse.BodyHandlers` | Kiểu body `T` | Khi nào dùng |
| --- | --- | --- |
| `ofString(StandardCharsets.UTF_8)` | `String` | Nội dung text/JSON nhỏ có charset rõ ràng. |
| `ofByteArray()` | `byte[]` | Dữ liệu byte nhỏ/vừa có thể chứa trọn trong bộ nhớ. |
| `ofFile(path)` | `Path` | Tải trực tiếp body xuống file đích được phép ghi. |
| `ofInputStream()` | `InputStream` | Đọc response theo luồng để kiểm soát bộ nhớ/giới hạn. |
| `discarding()` | `Void` | Chủ động đọc và loại bỏ body khi không cần dữ liệu. |
| `ofLines()` | `Stream<String>` | Xử lý các dòng văn bản theo luồng. |

**`BodyHandlers.ofString()` không tự biến JSON thành Java object.** Nếu muốn parse JSON, cần thêm bộ parser JSON đúng yêu cầu.

Với `ofString` hoặc `ofByteArray`, body có thể chiếm bộ nhớ lớn; **không dùng một cách vô điều kiện cho dữ liệu từ endpoint không tin cậy**. Với `ofInputStream` và `ofLines`, ứng dụng phải tiêu thụ và **đóng** stream tương ứng. Nếu không đọc hết/không đóng, kết nối và tài nguyên có thể tiếp tục bị giữ. Với `ofFile`, phải chọn thư mục/đường dẫn an toàn và làm rõ chính sách xử lý file ghi dở khi có lỗi.

Đoạn đọc stream minh họa (nằm trong phương thức có khai báo/xử lý `IOException` và `InterruptedException`):

```java
HttpResponse<java.io.InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());
try (java.io.InputStream input = response.body()) {
    byte[] buffer = new byte[8192];
    long total = 0;
    int n;
    while ((n = input.read(buffer)) != -1) {
        total += n;
        if (total > 1_000_000) {
            throw new IOException("Response too large");
        }
        // Chỉ xử lý hoặc lưu n byte sau khi đã kiểm tra giới hạn.
    }
}
```

Hạn mức **1.000.000 byte** chỉ là ví dụ; đặt mức phù hợp nghiệp vụ. Mẫu này không ghi dữ liệu trước khi kiểm tra, nhưng kiểm soát tổng kích thước cần được kết hợp với timeout, giới hạn tài nguyên server/proxy và chính sách hủy yêu cầu. Vì `InputStream` được trả trước khi nhất thiết đã nhận hết body, không coi việc có response headers là bằng chứng toàn bộ nội dung đã tải xong.

## 9. Timeout, ngoại lệ, interrupt và retry

### 9.1. Hai timeout không giống nhau

- **`client.connectTimeout(duration)`**: thời gian cho việc thiết lập **kết nối mới**; không có hiệu lực nếu tái sử dụng kết nối sẵn có.
- **`request.timeout(duration)`**: thời gian chờ phản hồi theo hợp đồng của request; nếu vượt quá có thể gặp `HttpTimeoutException`. Với body dạng stream, API có những thời điểm hoàn tất khác nhau nên không được coi nó là giới hạn cứng cho toàn bộ khối dữ liệu lớn sau khi đã trả stream.

Các duration truyền vào phải dương. Trong môi trường thực tế, ngoài timeout cần có giới hạn phản hồi lớn, timeout ở các tầng vận hành và khả năng hủy request khi phù hợp.

### 9.2. Xử lý ngoại lệ đồng bộ

```java
try {
    HttpResponse<String> res = client.send(request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    if (res.statusCode() >= 200 && res.statusCode() < 300) {
        // Thành công theo quy ước HTTP.
    } else {
        // Lỗi HTTP: 4xx/5xx vẫn là một response.
    }
} catch (java.net.http.HttpConnectTimeoutException ex) {
    // Không thiết lập được kết nối trong thời gian cho phép.
} catch (java.net.http.HttpTimeoutException ex) {
    // Vượt giới hạn chờ response của request.
} catch (IOException ex) {
    // Lỗi I/O khác: DNS, socket, đọc response, TLS...
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Dừng/đẩy lỗi lên tầng điều phối; không bỏ qua interrupt.
}
```

Đây là **mảnh mã minh họa**, cần `client` và `request` đã tạo trong phạm vi, cùng import `IOException` hoặc dùng tên đầy đủ. `HttpConnectTimeoutException` là dạng chuyên biệt của `HttpTimeoutException`, vì thế phải bắt subtype trước. Không gom tất cả lỗi vào một thông báo “server trả 500”: **lỗi mạng/I/O và HTTP status là hai loại kết quả khác nhau**.

### 9.3. Retry phải có điều kiện

Trước khi tự retry, xem xét:
- Phương thức có **idempotent** theo hợp đồng server không? GET thường phù hợp hơn POST có tác dụng phụ.
- Status `429` hoặc `503` có cung cấp hướng dẫn như `Retry-After` không?
- Giới hạn tổng số lần thử, backoff, jitter và timeout toàn hoạt động có phù hợp không?
- Khi dùng `BodyPublisher` từ stream, nguồn có thể phát lại hay không?
- Request có thông tin nhạy cảm hay cần khóa chống gửi lặp không?

Không tự động retry vô hạn hoặc giả định mọi exception nghĩa là server chưa xử lý request. Một timeout có thể xảy ra sau khi server đã thực hiện hành động.

## 10. HTTP/2, redirect, TLS và bảo mật

### 10.1. Ưu tiên HTTP/2 không phải cam kết

`HttpClient.Version.HTTP_2` và `HTTP_1_1` chọn phiên bản mong muốn. Phiên bản thực dùng còn phụ thuộc khả năng thương lượng và môi trường mạng; kiểm tra `response.version()` thay vì suy luận từ builder. Các cơ chế như multiplexing của HTTP/2 có thể hữu ích, nhưng không biến mọi request thành song song tức thì hay thay thế giới hạn tài nguyên.

### 10.2. Redirect cần chính sách rõ

Mặc định của builder Java 11 là `HttpClient.Redirect.NEVER`. Nếu chọn `NORMAL` để theo redirect được phép, cần lưu ý đích cuối, method/body và thông tin ủy quyền. **Không vô điều kiện gửi token hoặc cookie đến host mới** qua redirect. Nếu endpoint có yêu cầu tuân thủ bảo mật chặt, cân nhắc từ chối redirect hoặc chỉ cho phép host/schema đã được duyệt.

### 10.3. Dùng HTTPS đúng cách

Trong giao tiếp thực tế qua Internet, ưu tiên **`https://`** và giữ xác minh chứng chỉ/TLS mặc định. Không tắt xác thực hostname hoặc tạo trust manager chấp nhận mọi chứng chỉ chỉ để “chạy cho được”. Mọi điều chỉnh `SSLContext`/`SSLParameters` phải phục vụ yêu cầu an ninh cụ thể và được kiểm thử.

HTTP trong chương trình ở mục 7 là **localhost chỉ dùng làm fixture**, không phải khuyến nghị truyền dữ liệu nhạy cảm không mã hóa qua mạng.

### 10.4. Kiểm soát URI và dữ liệu không tin cậy

Một dịch vụ phía server nhận URL do người dùng nhập rồi dùng `HttpClient` tải nội dung có thể gặp **SSRF (Server-Side Request Forgery)**. Khi người dùng kiểm soát đích, cần xác thực scheme, domain/port, phân giải DNS, địa chỉ nội bộ và đường redirect theo chính sách. Không chỉ kiểm tra chuỗi `startsWith("https://")` rồi xem là an toàn.

Không ghi log token, API key, header `Authorization` hay body chứa dữ liệu riêng tư. Không nhúng bí mật vào source code hoặc URI query khi có lựa chọn an toàn hơn. Nếu cần xác thực, sử dụng cơ chế phù hợp với API và lưu bí mật bằng phương án cấu hình đáng tin cậy.

## 11. Các lỗi thường gặp

| Triệu chứng / hiểu nhầm | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Nghĩ `HttpRequest.build()` đã gọi HTTP | `build` chỉ tạo mô tả request. | Gọi `client.send` hoặc `sendAsync`. |
| HTTP 404/500 nhưng code không vào `catch(IOException)` | Status lỗi HTTP là response hợp lệ về giao thức. | Kiểm tra `response.statusCode()`. |
| `sendAsync` trả ngay mà chương trình chưa in gì | Callback/future chưa hoàn tất trước khi luồng điều phối kết thúc. | Đợi/ghép `CompletableFuture` theo lifecycle ứng dụng. |
| `future.join()` báo lỗi runtime khó đọc | Exception bất đồng bộ được bao bọc. | Xử lý completion và nguyên nhân gốc; không giấu lỗi. |
| Đặt `connectTimeout` nhưng request vẫn lâu | Timeout kết nối không giới hạn mọi giai đoạn truyền nhận. | Thêm `request.timeout` và các giới hạn tài nguyên khác. |
| Nghĩ `version(HTTP_2)` bắt buộc server chạy HTTP/2 | Giao thức thực phụ thuộc thương lượng. | Kiểm tra `response.version()`. |
| Dùng `BodyHandlers.ofString()` để tải file nhiều GB | Toàn bộ nội dung có thể được giữ trong bộ nhớ. | Streaming hoặc `ofFile` kèm giới hạn/quy trình tệp an toàn. |
| Dùng `ofInputStream` rồi không đọc/đóng stream | Body chưa tiêu thụ hết, có thể giữ tài nguyên. | `try-with-resources` và xử lý hủy/kết thúc thích hợp. |
| Gửi JSON nhưng không khai báo charset/Content-Type | Server có thể diễn giải khác dự kiến. | Chọn UTF-8 rõ ràng, header phù hợp và serialize JSON đúng cách. |
| Gửi lại POST ngay sau timeout | Server có thể đã xử lý request trước khi client mất phản hồi. | Retry theo hợp đồng API/idempotency key. |
| Tin rằng HTTP 2xx bảo đảm dữ liệu đúng cấu trúc | Status không kiểm tra schema/ý nghĩa của body. | Parse/validate dữ liệu đáp ứng nghiệp vụ. |
| Vô tình cho phép redirect tới host không tin cậy | Chính sách chuyển hướng chưa kiểm soát. | Kiểm tra host, protocol và xác thực ở từng bước. |

## 12. Bài tập thực hành có đáp án

**Câu 1.** API trả 404 nhưng `HttpClient.send` kết thúc bình thường. Đây có phải lỗi của `HttpClient` không?

**Đáp án:** Không. HTTP 404 là một phản hồi hợp lệ mang status thất bại ở tầng ứng dụng; phải dùng `response.statusCode()` để xử lý.

**Câu 2.** Sự khác nhau giữa `connectTimeout` và `request.timeout` là gì?

**Đáp án:** Cái đầu giới hạn thiết lập **kết nối mới**; cái sau gắn với thời gian chờ phản hồi cho **một request**. Không dùng một cái thay cho mọi giới hạn khác.

**Câu 3.** Gọi `client.sendAsync(request, BodyHandlers.ofString())` có làm thread hiện tại chờ nhận response không?

**Đáp án:** Không ngay tại lúc gửi. Nó trả `CompletableFuture`; nếu sau đó gọi `join()` thì thread gọi `join` vẫn chờ kết quả.

**Câu 4.** Vì sao `HttpResponse<String>` khác `HttpResponse<byte[]>`?

**Đáp án:** `BodyHandler` quyết định kiểu và cách tiêu thụ body. `ofString` giải mã byte thành văn bản, `ofByteArray` giữ byte trong mảng.

**Câu 5.** Làm sao biết kết nối thực tế chạy HTTP/1.1 hay HTTP/2?

**Đáp án:** Kiểm tra `response.version()`. `client.version()` chỉ cho biết phiên bản ưu tiên trên client.

**Câu 6.** Đang gửi POST tạo bản ghi, request timeout. Có thể cứ thử lại vô hạn không?

**Đáp án:** Không. Không biết chắc server đã tạo bản ghi hay chưa; phải tuân theo hợp đồng retry, giới hạn số lần thử và cơ chế chống trùng nếu cần.

**Câu 7.** Vì sao ví dụ mục 7 dùng `com.sun.net.httpserver.HttpServer` trong khi bài học là client chuẩn?

**Đáp án:** Chỉ để có **endpoint cục bộ kiểm thử không cần Internet**. API gửi request vẫn là `java.net.http.HttpClient`. Dự án chỉ là client không cần tích hợp HTTP server này.

**Câu 8.** Nếu URL đến từ input không tin cậy, kiểm tra `url.startsWith("https://")` có đủ phòng SSRF không?

**Đáp án:** Không. Cần chính sách xác thực đích, host, DNS/IP, port, redirect và các giới hạn khác phù hợp với môi trường.

## 13. Ghi nhớ và tài liệu chính thức

- **`java.net.http` là HTTP Client chuẩn từ Java 11**, hỗ trợ HTTP/1.1 và HTTP/2 cùng mô hình đồng bộ/bất đồng bộ.
- `HttpClient` nên được cấu hình rõ và **tái sử dụng**; `HttpRequest` mô tả yêu cầu; `HttpResponse<T>` chứa status/headers/body.
- `BodyPublishers` quyết định cách gửi request body; `BodyHandlers` quyết định cách nhận response body.
- **HTTP status 4xx/5xx khác lỗi I/O**: luôn kiểm tra mã trạng thái và tính hợp lệ của nội dung.
- **`send` chặn** luồng gọi; **`sendAsync` trả future**. Cả hai cần xử lý timeout, lỗi mạng và lifecycle thích hợp.
- `connectTimeout` không giới hạn mọi giai đoạn; `response.version()` mới phản ánh phiên bản HTTP thực tế.
- Với nội dung lớn và nguồn không tin cậy, kiểm soát **bộ nhớ, stream, kích thước, thời gian và đích URL**; giữ TLS và chính sách redirect an toàn.
- Code biên dịch cho Java 11 không được giả định những API quản lý vòng đời chỉ xuất hiện ở JDK mới hơn.

Nguồn tham khảo API chính thức, áp dụng cho Java 11 trở lên:

- [Java SE 11 — Module java.net.http](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/module-summary.html).
- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java SE 11 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html).
- [Java SE 11 — HttpRequest và BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html).
- [Java SE 11 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpTimeoutException.html).