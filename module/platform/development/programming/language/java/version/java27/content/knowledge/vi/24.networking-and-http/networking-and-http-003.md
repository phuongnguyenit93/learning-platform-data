# `HttpClient`, `HttpRequest` và `HttpResponse` trong Java 27

Trong chương **Mạng và HTTP**, ứng dụng Java thường phải gọi REST API, gửi dữ liệu JSON, tải tệp, kiểm tra trạng thái dịch vụ hoặc kết nối với một hệ thống bên ngoài. Từ Java 11, module **`java.net.http`** cung cấp HTTP Client API hiện đại, gồm ba thành phần trung tâm: **`HttpClient`**, **`HttpRequest`** và **`HttpResponse<T>`**. Những API này tiếp tục được hỗ trợ trong **Java 27** và là lựa chọn tiêu chuẩn khi không cần chức năng đặc thù của một thư viện HTTP bên thứ ba.

Mô hình tư duy:

```text
                  Cấu hình dùng chung
                 +--------------------+
                 |     HttpClient     |
                 | timeout/connect    |
                 | HTTP version       |
                 | proxy/redirect/TLS |
                 +----------+---------+
                            |
         HttpRequest        | send / sendAsync         HttpResponse<T>
   +------------------+     |                    +-----------------------+
   | URI, method       +-----+---- HTTP --------> | statusCode(), version()|
   | headers, body     |                          | headers(), body()     |
   | request timeout   |                          | request(), uri()      |
   +------------------+                          +-----------------------+
         BodyPublisher                                    BodyHandler<T>
         (dữ liệu gửi)                                    (cách nhận body)
```

`HttpClient` quản lý cấu hình và kết nối có thể tái sử dụng; `HttpRequest` mô tả **một yêu cầu HTTP**; còn `HttpResponse<T>` chứa trạng thái, header và dữ liệu nhận được dưới kiểu `T` do **response body handler** quyết định.

> Phạm vi: bài tập trung vào **HTTP client** Java 27, không phải viết HTTP server. Mọi ví dụ tránh API đã lỗi thời, không dùng `HttpURLConnection` làm cách tiếp cận mặc định và không giả định các endpoint công cộng luôn khả dụng. Ví dụ tích hợp cuối bài chạy với HTTP server cục bộ để có thể kiểm thử mà không cần Internet.

## 1. Chuẩn bị module và import

Nếu dự án dùng Java Platform Module System (JPMS), module sử dụng HTTP Client khai báo:

```java
module com.example.app {
    requires java.net.http;
}
```

Trong một ứng dụng classpath thông thường, có thể import trực tiếp các class:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
```

Các API thường dùng:

| API | Trách nhiệm |
| --- | --- |
| `HttpClient` | Gửi request, quản lý cấu hình, phiên kết nối và vòng đời client |
| `HttpClient.Builder` | Đặt connect timeout, redirect, proxy, authenticator, version, executor |
| `HttpRequest` | Đối tượng request bất biến sau `build()` |
| `HttpRequest.Builder` | Thiết lập URI, method, header, request timeout, body |
| `HttpRequest.BodyPublishers` | Biến dữ liệu thành nội dung request body |
| `HttpResponse<T>` | Kết quả gồm status, headers, version, URI, request, body |
| `HttpResponse.BodyHandlers` | Chọn cách đọc body: `String`, `byte[]`, file, stream, `Void`... |
| `HttpHeaders` | Truy cập các HTTP response headers |
| `HttpTimeoutException` | Lỗi thời hạn request |
| `HttpConnectTimeoutException` | Lỗi thời hạn thiết lập kết nối |

`java.net.http` là module có sẵn trong các JDK Java hiện đại. Đây là **HTTP client API**, không phải thư viện ánh xạ JSON thành record; nếu cần parse/generate JSON tổng quát, chọn thư viện JSON phù hợp với project.

## 2. Ví dụ đơn giản nhất: gửi GET và đọc body

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class GetExample {
    public static void main(String[] args) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://example.com/"))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
            );

            System.out.println("Status: " + response.statusCode());
            System.out.println("Version: " + response.version());
            System.out.println(response.body());
        }
    }
}
```

Đây là ví dụ minh họa cách dùng API, **không phụ thuộc** vào cấu trúc nội dung của `example.com`. Việc truy cập thật cần DNS, mạng, chứng chỉ TLS hợp lệ và endpoint khả dụng.

**Luồng xử lý:**

1. `HttpRequest.newBuilder()` tạo builder có thể thay đổi cấu hình.
2. `.uri(...)`, `.timeout(...)`, `.GET()` cấu hình request.
3. `.build()` tạo một `HttpRequest` bất biến.
4. `client.send(request, BodyHandlers.ofString(...))` thực thi đồng bộ.
5. `HttpResponse<String>` cho phép lấy status, header và body kiểu `String`.
6. `HttpClient.close()` được gọi khi thoát `try-with-resources`.

**Quan trọng:** `send()` *không* tự ném exception chỉ vì server trả `404`, `429` hay `500`. Đó là HTTP response hợp lệ; muốn coi chúng là thất bại nghiệp vụ, phải kiểm tra `response.statusCode()`.

## 3. `HttpClient`: cấu hình và tái sử dụng

Một client cấu hình tường minh:

```java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))
    .followRedirects(HttpClient.Redirect.NORMAL)
    .version(HttpClient.Version.HTTP_2)
    .build();
```

Client sau khi được xây dựng là **immutable** về cấu hình và có thể dùng để gửi nhiều request, kể cả từ nhiều thread. Nó có thể duy trì connection pool để tái sử dụng kết nối.

### 3.1. Không tạo client mới cho mọi request nếu không cần

**Thiết kế kém cho một dịch vụ gọi API lặp lại:**

```java
// Không nên tạo client mới và bỏ mặc sau mỗi lần gọi:
HttpClient client = HttpClient.newHttpClient();
client.send(request, HttpResponse.BodyHandlers.ofString());
```

Việc tạo mới liên tục làm giảm cơ hội tái sử dụng connection và có thể gia tăng số tài nguyên giữ trong runtime. Nên quản lý một client theo **vòng đời component hoặc service**, ví dụ một object sở hữu client dùng cho nhiều request, rồi đóng tại shutdown.

Ngược lại, một chương trình nhỏ gọi vài request rồi kết thúc có thể đặt client trong `try-with-resources`. Không có quy tắc một client duy nhất cho toàn bộ JVM: những service cần proxy, credentials, cookie policy hoặc trust configuration khác nhau có thể dùng client khác nhau.

### 3.2. Các lựa chọn cấu hình thường gặp

| Cấu hình | Ảnh hưởng | Lưu ý |
| --- | --- | --- |
| `connectTimeout(Duration)` | Thời hạn thiết lập kết nối mới | Không phải giới hạn toàn bộ thời gian request |
| `followRedirects(policy)` | Có tự theo HTTP redirect hay không | Mặc định không tự theo redirect |
| `version(version)` | Phiên bản giao thức ưu tiên | Không bảo đảm phiên bản thực tế được chọn |
| `proxy(ProxySelector)` | Cách chọn proxy cho request | Tùy mạng và cấu hình |
| `authenticator(Authenticator)` | Hỗ trợ xác thực HTTP/proxy theo implementation | Không phải cơ chế xử lý mọi dạng OAuth |
| `cookieHandler(CookieHandler)` | Chính sách lưu/gửi cookie | Cần cân nhắc chia sẻ state giữa người dùng |
| `sslContext(SSLContext)` | Ngữ cảnh TLS | Giữ xác thực chứng chỉ/hostname an toàn |
| `executor(Executor)` | Executor phục vụ các tác vụ bất đồng bộ nội bộ | Cần quản lý vòng đời executor được cung cấp |

Thực thi trong môi trường có nhiều user/tenant cần đặc biệt lưu ý cookie, proxy và thông tin xác thực của client dùng chung: một client có state phải được cấu hình theo đúng trust boundary.

## 4. `HttpRequest`: URI, method và bất biến

`HttpRequest` được tạo bằng builder:

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items")
    )
    .header("Accept", "application/json")
    .timeout(Duration.ofSeconds(10))
    .GET()
    .build();
```

Một khi `build()`, **request object bất biến** và có thể gửi nhiều lần nếu các thành phần của request, nhất là request-body publisher, hỗ trợ thao tác đó. Builder **có thể thay đổi**, không nên dùng chung một builder giữa các thread mà không đồng bộ.

### 4.1. HTTP methods

| Phương thức | Cách tạo |
| --- | --- |
| GET | `.GET()` hoặc mặc định nếu không đặt method khác |
| HEAD | `.HEAD()` |
| POST | `.POST(BodyPublisher)` |
| PUT | `.PUT(BodyPublisher)` |
| DELETE | `.DELETE()` |
| Method khác phù hợp với giao thức/implementation | `.method("PATCH", BodyPublishers.ofString(...))` |

Ví dụ PATCH:

```java
HttpRequest patch = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items/42")
    )
    .header("Content-Type", "application/json; charset=UTF-8")
    .method(
        "PATCH",
        HttpRequest.BodyPublishers.ofString(
            "{\"enabled\":true}",
            StandardCharsets.UTF_8
        )
    )
    .build();
```

Đây là payload JSON cố định chỉ để minh họa. **Không nối trực tiếp dữ liệu không tin cậy vào JSON**: cần serializer có xử lý escape đúng, validation và giới hạn kích thước.

### 4.2. `header` và `setHeader`

```java
var builder = HttpRequest.newBuilder(
    URI.create("https://api.example.com/items")
);

builder.header("Accept", "application/json");
builder.header("Accept", "text/plain"); // Thêm một giá trị nữa
builder.setHeader("Accept", "application/json"); // Thay các giá trị trước
```

`header(name, value)` **thêm** giá trị; `setHeader(name, value)` **thay thế** những giá trị đã đặt cùng tên.

Không phải HTTP header nào cũng cho phép tự set; implementation có thể hạn chế `Content-Length`, header phục vụ kết nối hoặc các header đặc biệt khác. `BodyPublisher` cung cấp thông tin để client quản lý nhiều header liên quan đến truyền body.

### 4.3. Mã hóa query parameter

Không tạo URI bằng cách nối trực tiếp input người dùng chưa encode:

```java
// Rủi ro: giá trị q có ký tự &, #, khoảng trắng...
// URI.create("https://api.example.com/search?q=" + userQuery)
```

Với **query parameter**:

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String userQuery = "Java HTTP & virtual threads";
String encoded = URLEncoder.encode(
    userQuery, StandardCharsets.UTF_8
);

URI uri = URI.create(
    "https://api.example.com/search?q=" + encoded
);
```

`URLEncoder` áp dụng cách mã hóa `application/x-www-form-urlencoded`, phù hợp cho nhiều giá trị query/form nhưng **không phải encoder tổng quát cho path segment**. Nếu cần tạo URL từ nhiều thành phần, dùng API URI/URL phù hợp hoặc thư viện URI builder có hợp đồng rõ.

Đối với endpoint lấy từ input không tin cậy, việc encode **không thay thế** kiểm tra scheme, hostname/IP và quyền truy cập mạng nhằm tránh SSRF.

## 5. `BodyPublisher`: dữ liệu được gửi đi như thế nào?

`HttpRequest.BodyPublisher` mô tả nguồn byte của request body. Các factory phổ biến nằm trong `HttpRequest.BodyPublishers`.

| Factory | Phù hợp |
| --- | --- |
| `noBody()` | Request không có body |
| `ofString(text, charset)` | Text, JSON đã serialize |
| `ofByteArray(bytes)` | Dữ liệu nhị phân trong bộ nhớ |
| `ofFile(path)` | Đọc dữ liệu gửi từ file |
| `ofInputStream(supplier)` | Tạo input stream cho lần gửi body |
| `fromPublisher(...)` | Tích hợp dữ liệu theo Flow Publisher |
| `concat(...)` | Ghép các body publisher theo thứ tự |

Ví dụ gửi JSON:

```java
String json = "{\"name\":\"Java 27\",\"active\":true}";

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://api.example.com/courses"))
    .header("Content-Type", "application/json; charset=UTF-8")
    .header("Accept", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(
        json, StandardCharsets.UTF_8
    ))
    .timeout(Duration.ofSeconds(15))
    .build();
```

`Content-Type` cho server biết định dạng request body. `Accept` mô tả định dạng response mà client ưu tiên. Hai header có vai trò khác nhau.

### 5.1. Gửi file mà không tự tải hết vào heap

```java
import java.nio.file.Path;
import java.io.FileNotFoundException;

HttpRequest upload = HttpRequest.newBuilder()
    .uri(URI.create("https://api.example.com/upload"))
    .header("Content-Type", "application/octet-stream")
    .POST(HttpRequest.BodyPublishers.ofFile(
        Path.of("report.bin")
    ))
    .build();
```

`ofFile` cung cấp publisher từ file; lỗi khi tạo hoặc đọc file cần được xử lý theo hợp đồng (ví dụ `FileNotFoundException` khi factory không thể mở file). Đừng giả định file input luôn tồn tại hoặc application được phép đọc nó.

### 5.2. Cẩn thận với body publisher chỉ dùng được một lần

Một `HttpRequest` có thể được gửi nhiều lần, nhưng tính lặp lại của **nội dung request** phụ thuộc publisher. Với `ofInputStream(supplier)`, supplier có thể được gọi để cung cấp stream cho một lần phát; nếu supplier luôn trả lại **cùng** stream đã đọc hết, việc gửi lại sẽ không đáng tin cậy.

Điều này đặc biệt quan trọng khi thiết kế **retry** hoặc **redirect**: phải xem publisher có khả năng tái tạo đúng body hay không và endpoint có cho phép thao tác lặp lại không.

### 5.3. Chưa có JSON object mapper tích hợp trong API này

`BodyPublishers.ofString()` chỉ biết gửi **chuỗi**, không tự chuyển record Java thành JSON. Tương tự, `BodyHandlers.ofString()` chỉ trả **chuỗi**, không tự parse thành POJO/record.

```java
record User(int id, String name) { }

// Cần thư viện JSON để:
// User user = mapper.readValue(response.body(), User.class);
```

Chọn một thư viện JSON phù hợp dự án để serialize/deserialize; kiểm tra kích thước, validation, charset, versioning của schema và không truyền dữ liệu nhạy cảm vào log.

## 6. `HttpResponse<T>`: không chỉ có `body()`

Một HTTP response thường cho phép đọc:

```java
HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
);

int status = response.statusCode();
String body = response.body();
HttpHeaders headers = response.headers();
URI finalUri = response.uri();
HttpClient.Version actualVersion = response.version();
HttpRequest sentRequest = response.request();
```

Các phương thức tiêu biểu:

| API | Ý nghĩa |
| --- | --- |
| `statusCode()` | Mã HTTP như 200, 404, 503 |
| `headers()` | Response headers, dạng read-only |
| `body()` | Kết quả body theo `T` của handler |
| `version()` | Phiên bản HTTP thực tế sử dụng |
| `uri()` | URI tương ứng với response nhận được |
| `request()` | Request gắn với response |
| `previousResponse()` | Response trước trong chuỗi chuyển hướng nếu có |
| `sslSession()` | Thông tin TLS session khi có và được cung cấp |

### 6.1. Đọc một header có thể vắng mặt

```java
import java.util.Optional;

Optional<String> contentType =
    response.headers().firstValue("Content-Type");

String type = contentType.orElse("unknown");
```

Header có thể xuất hiện nhiều lần; API `HttpHeaders` hỗ trợ xem danh sách giá trị nếu cần. Tên header HTTP không phân biệt chữ hoa/thường khi tra cứu theo hợp đồng API.

Không mặc định server luôn trả `Content-Type`, `Content-Length` hoặc `Retry-After`.

### 6.2. Kiểm tra HTTP status trước khi tin dữ liệu

```java
int code = response.statusCode();

if (code >= 200 && code < 300) {
    System.out.println("Success");
} else if (code == 404) {
    System.out.println("Resource not found");
} else if (code == 429) {
    System.out.println("Rate limited");
} else {
    System.out.println("HTTP error: " + code);
}
```

Mã `2xx` thường biểu thị thành công ở cấp HTTP, nhưng kết quả nghiệp vụ vẫn có thể cần kiểm tra schema. Có API trả `202 Accepted` khi tác vụ chưa hoàn tất; `204 No Content` không có response body mang nội dung cần parse.

**Không giả định `send()` ném exception cho `4xx`/`5xx`.** Trong phần lớn client API, việc nhận response HTTP hoàn chỉnh là thành công ở tầng vận chuyển; ứng dụng phải tự phân loại lỗi nghiệp vụ.

## 7. `BodyHandler<T>` quyết định kiểu và vòng đời response body

Mỗi lần `send()` hoặc `sendAsync()` cần cung cấp một `BodyHandler<T>`:

```java
HttpResponse<String> text = client.send(
    request, HttpResponse.BodyHandlers.ofString()
);

HttpResponse<byte[]> binary = client.send(
    request, HttpResponse.BodyHandlers.ofByteArray()
);

HttpResponse<Void> ignored = client.send(
    request, HttpResponse.BodyHandlers.discarding()
);
```

Bảng lựa chọn:

| Handler | Kiểu trả về `T` | Phù hợp |
| --- | --- | --- |
| `ofString()` / `ofString(charset)` | `String` | Response text vừa phải |
| `ofByteArray()` | `byte[]` | Binary payload nhỏ/vừa |
| `ofFile(path)` | `Path` | Ghi body ra tệp |
| `ofInputStream()` | `InputStream` | Đọc dần dữ liệu, tránh materialize toàn bộ |
| `ofLines()` | `Stream<String>` | Xử lý response theo dòng |
| `discarding()` | `Void` | Không cần lưu body |
| `ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Pipeline reactive/backpressure phức tạp |
| `limiting(handler, maxBytes)` | Theo handler bên trong | Giới hạn số byte body đưa đến subscriber |

### 7.1. `ofString()` và `ofByteArray()` có chi phí bộ nhớ

Cả hai thường materialize response body trước khi trả kết quả đầy đủ cho caller. Với dữ liệu lớn hoặc server không đáng tin cậy, dùng streaming, giới hạn kích thước hoặc tải vào file thay vì gom hết vào heap.

**Java 27 có `BodyHandlers.limiting`** (API có từ Java 25), giúp giới hạn số byte chuyển tới handler bên trong:

```java
var safeHandler = HttpResponse.BodyHandlers.limiting(
    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8),
    1_048_576L
);

HttpResponse<String> response = client.send(request, safeHandler);
```

Nếu lượng byte nhận vượt mức giới hạn, subscriber phía dưới được báo lỗi `IOException` và subscription nguồn bị hủy. Với response compressed/chunked, cần hiểu số byte mà handler nhận và các lớp giải mã thực tế; không coi đây là biện pháp giải quyết mọi nguy cơ decompression bomb hoặc JSON quá sâu.

### 7.2. `ofFile(path)` và việc lưu cả lỗi HTTP

```java
HttpResponse<Path> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofFile(Path.of("download.bin"))
);
```

Handler `ofFile` ghi **response body** ra file mà không tự từ chối status `404` hay `500`. Nếu server gửi một trang lỗi HTML, chính trang lỗi đó có thể được lưu thành `download.bin`.

Trong ứng dụng thật:
- Xác thực `statusCode`, `Content-Type` và độ dài khi phù hợp.
- Dùng đường dẫn đích an toàn do ứng dụng kiểm soát.
- Cân nhắc ghi file tạm rồi đổi tên sau khi xác thực thành công.
- Không dùng filename từ response header không tin cậy mà không kiểm tra path traversal/đè file.

### 7.3. `ofInputStream()`: phải đóng hoặc đọc hết stream

```java
import java.io.InputStream;

HttpResponse<InputStream> response = client.send(
    request, HttpResponse.BodyHandlers.ofInputStream()
);

try (InputStream body = response.body()) {
    byte[] prefix = body.readNBytes(256);
    System.out.println("Read " + prefix.length + " bytes");
}
```

Với handler này, `HttpResponse` có thể sẵn sàng **trước khi nhận toàn bộ body**. Caller phải đóng stream, đọc đến hết hoặc chủ động hủy theo hợp đồng để giải phóng resource và giúp HTTP exchange hoàn tất.

Đừng để `InputStream` thoát scope mà không có owner được chỉ định. Một client đang chờ đóng có thể bị giữ lại bởi những streaming body chưa được tiêu thụ/đóng.

### 7.4. `ofLines()` cũng có vòng đời

```java
HttpResponse<java.util.stream.Stream<String>> response =
    client.send(request, HttpResponse.BodyHandlers.ofLines());

try (var lines = response.body()) {
    lines.limit(10).forEach(System.out::println);
}
```

`limit(10)` chưa chắc tiêu thụ hết HTTP response. `try-with-resources` đóng stream khi rời scope, giúp không giữ kết nối/response body không cần thiết. Không dùng `ofLines()` rồi chỉ gọi một terminal operation ngắn mà bỏ quên việc đóng nguồn streaming.

## 8. Gửi bất đồng bộ với `sendAsync()`

`sendAsync()` trả về `CompletableFuture<HttpResponse<T>>` thay vì chặn thread gọi cho đến khi có response.

```java
import java.util.concurrent.CompletableFuture;

CompletableFuture<HttpResponse<String>> pending =
    client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
    );

CompletableFuture<String> result = pending.thenApply(response -> {
    if (response.statusCode() != 200) {
        throw new IllegalStateException(
            "Unexpected HTTP status: " + response.statusCode()
        );
    }
    return response.body();
});

String value = result.join();
```

`join()` **chặn cho tới khi future hoàn tất** và có thể ném `CompletionException` nếu pipeline lỗi. Trong service bất đồng bộ, có thể trả lại `CompletableFuture` cho tầng trên thay vì `join()` ngay.

### 8.1. Xử lý lỗi bất đồng bộ

```java
var future = client.sendAsync(
    request,
    HttpResponse.BodyHandlers.ofString()
).handle((response, error) -> {
    if (error != null) {
        return "Transport error: " + error.getClass().getSimpleName();
    }
    return "HTTP " + response.statusCode();
});
```

`handle` chạy cho cả trường hợp thành công và thất bại. Trong production không nên chỉ trả message chung: phải phân biệt lỗi mạng/timed out, status HTTP và lỗi parse hoặc business logic, đồng thời giữ cause cho log có kiểm soát.

### 8.2. Có thể gửi nhiều request đồng thời

```java
HttpRequest a = HttpRequest.newBuilder(
    URI.create("https://api.example.com/a")
).GET().build();

HttpRequest b = HttpRequest.newBuilder(
    URI.create("https://api.example.com/b")
).GET().build();

var fa = client.sendAsync(a, HttpResponse.BodyHandlers.ofString());
var fb = client.sendAsync(b, HttpResponse.BodyHandlers.ofString());

CompletableFuture<Void> both = CompletableFuture.allOf(fa, fb);

// Chỉ lấy kết quả sau khi cả hai future hoàn tất.
both.join();
System.out.println(fa.join().statusCode());
System.out.println(fb.join().statusCode());
```

Điểm tốt: các request có thể chồng lấn thời gian I/O. Nhưng số lượng request đồng thời có thể làm quá tải server, proxy hoặc chính client. Nên đặt **concurrency limit** và chính sách timeout/retry phù hợp với hệ thống thực tế.

### 8.3. Async không đồng nghĩa “không cần quan tâm tài nguyên”

Khi dùng body streaming hoặc publisher, response exchange vẫn có lifecycle riêng. Nếu hủy một future, cancellation được **cố gắng áp dụng**, nhưng không bảo đảm server chưa xử lý request hoặc toàn bộ resource đã được đóng ngay. `CompletableFuture.orTimeout(...)` còn là cách đặt deadline cho **future**, không phải một thay thế hoàn toàn cho HTTP request timeout và resource cleanup.

## 9. Đồng bộ với `send()`: phù hợp cả virtual threads

`HttpClient.send()` là lời gọi **blocking** theo hợp đồng. Trên virtual thread, kiểu code tuần tự dễ đọc có thể phù hợp với workload gồm nhiều tác vụ I/O:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Integer> task = executor.submit(() -> {
        HttpResponse<Void> response = client.send(
            request,
            HttpResponse.BodyHandlers.discarding()
        );
        return response.statusCode();
    });

    System.out.println(task.get());
}
```

Ở đây `client` nên được quản lý ở scope lớn hơn nếu có nhiều task dùng chung. **Virtual threads không làm network latency biến mất**, không tự tăng băng thông và không thay thế timeout/concurrency limits. Chọn `send()` trong virtual thread hay `sendAsync()` tùy kiến trúc ứng dụng, error handling và cách tổ chức task.

## 10. Connect timeout và request timeout khác nhau

Hai API đặt giới hạn ở các giai đoạn khác nhau:

```java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))
    .build();

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://api.example.com/items"))
    .timeout(Duration.ofSeconds(12))
    .GET()
    .build();
```

| Loại | Đặt ở đâu? | Diễn giải |
| --- | --- | --- |
| Connection timeout | `HttpClient.Builder.connectTimeout` | Giới hạn việc thiết lập **kết nối mới** |
| Request timeout | `HttpRequest.Builder.timeout` | Giới hạn thời gian request theo contract của API |
| Deadline nghiệp vụ toàn chuỗi | Do ứng dụng định nghĩa | Bao gồm retry, chờ hàng đợi, parse, downstream stages... |

Theo Java 27, request timeout áp dụng từ khi bắt đầu thực thi ít nhất đến lúc tạo `HttpResponse`; **implementation mặc định của JDK áp dụng thời hạn đến khi body subscriber hoàn tất** nếu có. Tuy vậy, khi chọn `ofInputStream()` hoặc một streaming handler, việc xử lý body do caller điều khiển có lifecycle riêng và phải tự quản lý việc đọc/đóng/cancel.

Nếu không đặt request timeout, không nên mặc định request sẽ tự dừng nhanh. Thời hạn phải là số dương; `Duration.ZERO` hoặc âm không hợp lệ ở builder.

### 10.1. Bắt lỗi timeout đồng bộ

```java
import java.io.IOException;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpTimeoutException;

try {
    HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString()
    );
    System.out.println(response.statusCode());
} catch (HttpConnectTimeoutException ex) {
    System.err.println("Connection timed out");
} catch (HttpTimeoutException ex) {
    System.err.println("HTTP request timed out");
} catch (IOException ex) {
    System.err.println("Network/IO error");
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    System.err.println("Request interrupted");
}
```

`HttpConnectTimeoutException` là trường hợp chuyên biệt của `HttpTimeoutException`; vì vậy catch lớp cụ thể **trước** lớp cha. Nếu method cần tôn trọng interruption, khôi phục interrupt flag hoặc truyền exception lên đúng ranh giới.

## 11. Redirect: `NEVER`, `NORMAL`, `ALWAYS`

Cấu hình khi xây client:

```java
HttpClient client = HttpClient.newBuilder()
    .followRedirects(HttpClient.Redirect.NORMAL)
    .build();
```

Các policy chính:

| Giá trị | Ý nghĩa |
| --- | --- |
| `NEVER` | Không tự động theo redirect; là lựa chọn mặc định |
| `NORMAL` | Cho phép redirect với hạn chế, đặc biệt không tự hạ cấp HTTPS xuống HTTP |
| `ALWAYS` | Có thể theo redirect rộng hơn, kể cả hướng không phù hợp với một số yêu cầu bảo mật |

Không tự chọn `ALWAYS` chỉ để “mọi URL đều chạy”. Trong dịch vụ xử lý URL không tin cậy, redirect có thể dẫn request tới host/IP ngoài dự kiến (SSRF) hoặc làm thay đổi nơi gửi thông tin nhạy cảm. Chính sách redirect cần đi cùng kiểm tra destination, scheme, credential propagation và trust boundary.

### 11.1. Redirect có thể thay đổi URI và cách gửi

```java
System.out.println(response.uri());
System.out.println(response.request().uri());
```

Đường redirect và hành vi đổi method/body tùy mã HTTP (301/302/303/307/308), client và giao thức. **Không giả định POST luôn được phát lại giữ nguyên body** sau mọi redirect. Với nghiệp vụ nhạy cảm, chỉ tự động theo redirect khi hiểu rõ server contract; có thể đặt `NEVER` và xử lý từng response 3xx theo logic có kiểm soát.

## 12. HTTP/1.1, HTTP/2 và HTTP/3 trong Java 27

API hiện đại của `HttpClient` hỗ trợ các phiên bản:

```java
HttpClient.Version.HTTP_1_1
HttpClient.Version.HTTP_2
HttpClient.Version.HTTP_3
```

**HTTP/3 đã xuất hiện trong Java SE 26 và vẫn được hỗ trợ ở Java 27**. Không nên dựa vào tài liệu cũ chỉ nói HTTP/1.1 và HTTP/2 khi đang học Java 27.

Chọn **phiên bản ưu tiên** cho client:

```java
HttpClient client = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_2)
    .build();
```

Hoặc cho một request:

```java
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://example.com/"))
    .version(HttpClient.Version.HTTP_3)
    .GET()
    .build();
```

**Phiên bản ưu tiên không bảo đảm phiên bản thực tế**. Hãy đọc:

```java
HttpClient.Version used = response.version();
System.out.println("Negotiated: " + used);
```

HTTP/2 có thể cần TLS ALPN hoặc cơ chế upgrade, tùy HTTPS/HTTP và proxy. HTTP/3 không được chọn mặc định, muốn dùng phải cấu hình ưu tiên HTTP/3. Với implementation mặc định của JDK, HTTP/3 chỉ dùng trên **HTTPS** và không dùng khi request đi qua proxy được chọn; tùy server/discovery/TLS và điều kiện mạng, phiên bản thực tế có thể khác.

Nếu cấu hình HTTP/3 không được implementation hỗ trợ, có thể gặp `UnsupportedProtocolVersionException` trong các điều kiện API mô tả. Không xây logic dựa trên việc server nào cũng hỗ trợ HTTP/3.

### 12.1. Hints cấu hình HTTP/3 là kiến thức nâng cao

Java 27 có `HttpOption.H3_DISCOVERY` và `HttpRequest.Builder.setOption(...)` để đưa **hints** về cách khám phá HTTP/3. Hints không phải command bảo đảm server sử dụng một transport nhất định.

Trong phần lớn ứng dụng, bắt đầu với HTTP/2 hoặc lựa chọn mặc định, kiểm tra `response.version()` và chỉ tinh chỉnh HTTP/3 khi có yêu cầu hiệu năng/giao thức và có hạ tầng kiểm thử phù hợp.

## 13. TLS, certificate và authentication

`https://` sử dụng TLS, và `HttpClient` có thể dùng cấu hình SSL/TLS được cung cấp qua `sslContext`/`sslParameters`.

**Không triển khai “trust all certificates”, tắt hostname verification hoặc tin mọi chứng chỉ chỉ để làm request thành công.** Các workaround này khiến ứng dụng dễ bị tấn công man-in-the-middle và không phải hướng dẫn vận hành đúng cho Java 27.

Nếu hệ thống dùng private CA, hãy cấu hình truststore hoặc `SSLContext` tin cậy theo chính sách tổ chức. Phải kiểm thử hiệu lực chứng chỉ, tên máy và thời hạn.

### 13.1. Bearer token

```java
String token = obtainTokenSecurely();

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://api.example.com/private"))
    .header("Authorization", "Bearer " + token)
    .header("Accept", "application/json")
    .GET()
    .build();
```

`obtainTokenSecurely()` đại diện cho hệ thống quản lý secrets và token; không ghi token cứng trong source code hoặc log.

Nếu dùng `Authenticator` cho HTTP authentication, phải hiểu phương thức thực tế implementation hỗ trợ và ranh giới giữa HTTP authentication/proxy authentication và OAuth/OIDC token workflows. Không giả định `Authenticator` tự refresh OAuth access token.

### 13.2. CookieHandler và state dùng chung

Có thể cấu hình `CookieManager`:

```java
import java.net.CookieManager;
import java.net.CookiePolicy;

CookieManager cookies = new CookieManager(
    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER
);

HttpClient client = HttpClient.newBuilder()
    .cookieHandler(cookies)
    .build();
```

Cookie được lưu theo policy và có thể tạo **shared session state**. Một `HttpClient` dùng chung cho nhiều người dùng trong server cần xác định rõ chính sách cách ly cookie; không lưu lẫn session của user A và user B trong cùng một cookie store thiếu phân tách.

## 14. Phân biệt lỗi mạng, lỗi HTTP và lỗi dữ liệu

Ba nhóm lỗi có cách xử lý khác nhau:

| Nhóm | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Transport | DNS failure, connection reset, TLS handshake lỗi, timeout | Bắt `IOException` và subtype; quan sát cause |
| HTTP status | 400, 401, 404, 429, 500, 503 | Có `HttpResponse`, kiểm tra `statusCode()` |
| Dữ liệu/ứng dụng | JSON sai schema, field thiếu, payload không hợp lệ | Validate/parsing tại tầng ứng dụng |

Một adapter gọn:

```java
import java.io.IOException;
import java.net.http.HttpResponse;

static String requireSuccess(HttpResponse<String> response)
        throws IOException {
    int status = response.statusCode();

    if (status < 200 || status >= 300) {
        throw new IOException("Unexpected HTTP status: " + status);
    }

    return response.body();
}
```

Ví dụ này cố ý **không ghi response body vào lỗi**, vì body có thể chứa dữ liệu nhạy cảm hoặc cực lớn. Trong ứng dụng cần phân loại 4xx/5xx tốt hơn, hãy sử dụng exception có trường status code và correlation ID, giới hạn log, không leak secrets.

### 14.1. `InterruptedException` không phải lỗi HTTP status

Nếu một thread bị interrupt khi `send()` đang chờ, implementation mặc định của JDK cố gắng hủy exchange, nhưng **không bảo đảm server chưa thực hiện request**. Một POST có thể đã được xử lý ở phía server trước khi local client phát hiện interruption.

Đừng tự động retry request có side effect chỉ vì xuất hiện `InterruptedException` hoặc timeout. Cần xem idempotency key hoặc cơ chế xác nhận trạng thái nghiệp vụ.

## 15. Retry, timeout và idempotency: thiết kế tại tầng ứng dụng

Một cơ chế retry hợp lý cần xét đồng thời:

1. Request method và **tính idempotent thật sự** của endpoint.
2. Loại lỗi: timeout, `IOException`, status `429`/`503`...
3. **Số lần retry tối đa** và tổng deadline.
4. Exponential backoff và jitter để tránh nhiều client retry cùng lúc.
5. `Retry-After` nếu API cung cấp và ứng dụng cho phép.
6. Khả năng phát lại body publisher và tính nhất quán của payload.
7. Hạn mức concurrency và cơ chế circuit breaker khi backend lỗi kéo dài.

Không đưa mọi `IOException` vào vòng lặp vô hạn. Với `POST` tạo tài nguyên, gửi lại có thể tạo **hai bản ghi** nếu request trước đã được server xử lý nhưng response bị mất.

HTTP Client API không tự biến các request thất bại thành một hệ thống retry nghiệp vụ đúng đắn. Cách thức xử lý redirect, authentication challenge hoặc kết nối ở tầng transport **khác** với retry chính sách nghiệp vụ; cần hiểu behavior thực tế và tài liệu API.

### 15.1. `Retry-After` chỉ là tín hiệu server

```java
var retryAfter = response.headers()
    .firstValue("Retry-After");
```

Giá trị có thể là số giây hoặc ngày HTTP; không ép kiểu mọi giá trị bằng `Long.parseLong(...)` mà không kiểm tra. Áp dụng trần delay, deadline tổng, và không chờ vô hạn. Retry policy cũng cần tránh ghi dữ liệu nhạy cảm vào log.

## 16. Phòng vệ khi gọi URL từ nguồn không tin cậy

Một HTTP client có thể trở thành điểm mở cho **Server-Side Request Forgery (SSRF)** nếu nhận URL người dùng rồi gọi thẳng đến địa chỉ bất kỳ.

```java
URI target = URI.create(userSuppliedUrl);
// KHÔNG tự gửi ngay nếu target chưa được kiểm soát:
```

Những lớp kiểm soát thường cần:

- Chỉ chấp nhận scheme được cho phép (thường `https`).
- Giới hạn host và port bằng allowlist hoặc policy rõ ràng.
- Không cho phép host nội bộ, loopback, link-local, metadata endpoint và dải IP bị cấm tùy môi trường.
- Kiểm soát DNS rebind, chuyển hướng, proxy, IPv4/IPv6 và kết nối thực tế theo chính sách bảo mật.
- Không tự chuyển `Authorization` hoặc cookie sang host ngoài phạm vi.
- Đặt request timeout, response size limit, concurrency limit và quota.
- Không tải file trực tiếp vào đường dẫn mà người dùng không tin cậy kiểm soát.

Chỉ kiểm tra chuỗi `target.getHost()` ở thời điểm tạo URI **không tự giải quyết toàn bộ SSRF**; có thể cần egress filtering ở hạ tầng mạng và chính sách redirect nghiêm ngặt.

## 17. Kiểm soát tài nguyên và vòng đời `HttpClient`

`HttpClient` triển khai `AutoCloseable` (các phương thức lifecycle được bổ sung từ Java 21):

```java
try (HttpClient client = HttpClient.newHttpClient()) {
    HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString()
    );
    System.out.println(response.statusCode());
}
```

`close()` cố gắng shutdown có trật tự, chờ các request đã được gửi hoàn tất; không chấp nhận request mới. Ngoài `close()`, implementation có `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)` và `isTerminated()` để hỗ trợ quản lý vòng đời theo yêu cầu.

**Không đóng client dùng chung sau mỗi request**: hãy đóng khi component sở hữu client thật sự kết thúc. Ngược lại, không dựa vào garbage collector để đóng kết nối đúng thời điểm.

### 17.1. Body streaming chưa đóng có thể cản shutdown

```java
HttpResponse<java.io.InputStream> response = client.send(
    request, HttpResponse.BodyHandlers.ofInputStream()
);

// Nếu không đóng/đọc hết stream, exchange có thể chưa hoàn tất.
try (var input = response.body()) {
    input.transferTo(java.io.OutputStream.nullOutputStream());
}
```

Ở ví dụ này `transferTo` đọc đến hết response rồi đóng stream khi rời `try`. Với payload lớn, đừng làm thao tác tải toàn bộ khi chỉ cần một phần; có thể đóng stream sớm và chấp nhận hủy phần còn lại theo contract.

`HttpClient.close()` **có thể chờ rất lâu** khi một streaming exchange không kết thúc. Cần xây dựng shutdown policy với timeout và cancellation ở mức ứng dụng, không xem `close()` là “release tức thì, không blocking”.

### 17.2. Executor do caller cung cấp cũng có owner

Nếu cấu hình:

```java
var executor = java.util.concurrent.Executors.newFixedThreadPool(4);

HttpClient client = HttpClient.newBuilder()
    .executor(executor)
    .build();
```

Client sử dụng executor đã được cung cấp, nhưng ứng dụng phải có chính sách **đóng cả client và executor** khi không còn tác vụ liên quan. Không shutdown executor trong khi request vẫn cần dùng nó. `HttpClient.close()` không nên được hiểu là lời hứa tự quản lý toàn bộ vòng đời executor bên ngoài do caller tạo.

### 17.3. Không lạm dụng client hay executor dùng chung

Tái sử dụng tốt khi client có cùng proxy, cookie/auth, TLS và timeout policy. Nếu nhiều tenant khác nhau cần credentials hoặc cookie isolation, phải lựa chọn instance/cấu trúc riêng theo trust boundary thay vì ép chia sẻ một client không an toàn.

## 18. Ví dụ tích hợp hoàn chỉnh: HTTP server cục bộ và HttpClient

Ví dụ sau dùng `HttpServer` từ module JDK **`jdk.httpserver`** để tạo một endpoint cục bộ, sau đó dùng `HttpClient` gửi request đến chính endpoint đó. Đây là **server thử nghiệm đi kèm JDK**, không phải một HTTP server framework cho production; `jdk.httpserver` là module của JDK, không đồng nghĩa luôn có trong mọi custom runtime image.

Lưu tạm chương trình dưới tên `LocalHttpClientDemo.java` (tự thực hiện ngoài quy trình ghi tài liệu này):

```java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class LocalHttpClientDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        InetSocketAddress bind = new InetSocketAddress(loopback, 0);

        HttpServer server = HttpServer.create(bind, 0);
        server.createContext("/ping", exchange -> {
            byte[] body = "pong from Java 27"
                .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8"
            );
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();
        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build()) {

            int port = server.getAddress().getPort();
            URI url = new URI(
                "http", null,
                loopback.getHostAddress(), port,
                "/ping", null, null
            );

            HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(5))
                .header("Accept", "text/plain")
                .GET()
                .build();

            HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8
                )
            );

            if (response.statusCode() != 200) {
                throw new IOException(
                    "Unexpected status: " + response.statusCode()
                );
            }

            System.out.println(response.statusCode()); // 200
            System.out.println(response.body()); // pong from Java 27
        } finally {
            server.stop(0);
        }
    }
}
```

Có thể biên dịch/chạy khi dùng JDK có module `jdk.httpserver`:

```text
javac --add-modules jdk.httpserver LocalHttpClientDemo.java
java --add-modules jdk.httpserver LocalHttpClientDemo
```

**Lưu ý về loopback:** địa chỉ server bind có thể là IPv4 `127.0.0.1` hoặc IPv6 `::1` tùy máy. Ví dụ lấy chính địa chỉ đã bind để xây URI (constructor `URI` xử lý phần host theo cấu trúc URI), không phụ thuộc việc tên `localhost` được phân giải thành IPv4 hay IPv6.

Ví dụ này kiểm thử các thành phần:
- Tạo endpoint HTTP cục bộ, không cần dịch vụ bên ngoài.
- Gửi GET qua một client được quản lý vòng đời.
- Dùng request timeout.
- Nhận `HttpResponse<String>` theo body handler.
- Kiểm tra status và đọc body.
- Dừng server và đóng client cả khi xảy ra lỗi.

Trong dự án dùng JPMS, cần khai báo cả `requires java.net.http;` và `requires jdk.httpserver;` đối với module chạy ví dụ. Với production server, chọn framework và cách cấu hình phù hợp thay vì coi `HttpServer` thử nghiệm là kiến trúc mẫu.

## 19. Các lỗi thường gặp

| Sai lầm | Vì sao sai? | Hướng xử lý |
| --- | --- | --- |
| Tạo client mới cho mọi request liên tục | Không tái sử dụng connection hiệu quả | Sở hữu và tái sử dụng client theo service lifecycle |
| Không kiểm tra `statusCode()` | 404/500 vẫn có thể tạo response bình thường | Xử lý response status theo nghiệp vụ |
| Nghĩ `BodyPublishers.ofString` tự serialize object JSON | Nó chỉ nhận text | Dùng serializer JSON đúng |
| Nghĩ `BodyHandlers.ofString` tự parse JSON thành record | Nó chỉ trả `String` | Deserialize và validate riêng |
| Chỉ đặt `connectTimeout` rồi tin toàn request có deadline | Nó chỉ giới hạn thiết lập kết nối mới | Đặt `request.timeout` và deadline nghiệp vụ |
| Gửi `POST` lại sau timeout mà không có idempotency | Server có thể đã xử lý request trước | Thiết kế retry an toàn và idempotency key |
| Đọc `ofByteArray` cho dữ liệu rất lớn | Có thể tăng heap mạnh | Streaming/file + giới hạn bytes |
| Quên đóng `ofInputStream`/`ofLines` | Giữ exchange/kết nối và cản shutdown | Đọc hết, đóng hoặc cancel rõ |
| Dùng `ofFile` mà không xem status | Lưu trang lỗi thành file đầu ra | Validate HTTP status và chính sách tệp |
| Chọn `HTTP_3` rồi khẳng định request chạy HTTP/3 | Chỉ là preferred protocol | Kiểm tra `response.version()` |
| Bật redirect `ALWAYS` vô điều kiện | Rủi ro hạ cấp/SSRF/credential forwarding | Chọn policy và kiểm soát destination |
| Dùng `URLEncoder` cho toàn URL/path | Nó dành cho form/query, không phải mọi thành phần URI | Encode từng thành phần đúng |
| Dùng URL người dùng truyền thẳng vào client | Có thể dẫn đến SSRF | Allowlist, kiểm soát DNS/redirect, egress policy |
| Bỏ xác minh TLS để “sửa” lỗi chứng chỉ | Mất bảo mật MITM | Cấu hình truststore/certificate đúng |
| Tin `cancel(true)` chắc chắn server chưa thực thi | Hủy là best effort, request có thể đã gửi | Thiết kế retry/ack/idempotency |
| Đóng client dùng chung sau một request | Những request khác có thể bị từ chối | Đóng ở application/component shutdown |
| Quên shutdown executor cấp cho client | Resource/thread tồn tại quá vòng đời cần thiết | Quản lý executor bên ngoài đúng scope |

## 20. Checklist khi đưa HTTP client vào production

Trước khi tích hợp một API bên ngoài:

1. URI và HTTP method có đúng contract không? Có encode query/path đúng và kiểm soát SSRF chưa?
2. `HttpClient` có được sở hữu và tái sử dụng theo vòng đời hợp lý không?
3. Có đặt cả connect timeout, request timeout và tổng deadline nghiệp vụ chưa?
4. Redirect policy đã được đánh giá theo bảo mật và service contract chưa?
5. JSON serialization/deserialization có an toàn, validate schema và xử lý encoding không?
6. Có giới hạn response size và chọn streaming khi nội dung lớn không?
7. Các response code `2xx`, `3xx`, `4xx`, `5xx` đã được xử lý riêng chưa?
8. Retry có giới hạn, jitter, idempotency và `Retry-After` phù hợp không?
9. Có cơ chế auth/TLS/cookie isolation theo tenant và chính sách secrets không?
10. Nếu dùng `sendAsync`, có quản lý cancellation, exception và callback executor hợp lý không?
11. Streaming body có được đọc hết, đóng hoặc cancel để giải phóng exchange không?
12. Nếu chọn HTTP/3, đã kiểm tra HTTPS, hỗ trợ server và `response.version()` thực tế chưa?
13. Có request correlation ID, metric latency/status và log che giấu token/body nhạy cảm không?
14. Có integration test chạy với HTTP server giả lập/cục bộ cho timeout, redirect, error status và body lớn không?
15. Có chính sách shutdown client/executor mà không bỏ dở tác vụ quan trọng không?

**Nguyên tắc cốt lõi:** `HttpClient` quản lý kết nối và cấu hình dùng chung; `HttpRequest` mô tả điều cần gửi; `HttpResponse<T>` chứa dữ liệu trả về theo `BodyHandler<T>`. Cách dùng đúng không chỉ là gọi được một endpoint mà còn phải **phân biệt HTTP status với lỗi transport**, đặt deadline, giới hạn dữ liệu, bảo vệ bí mật và đóng resource đúng thời điểm.

## Tài liệu tham khảo chính thức

- [Java SE 27 API — `HttpClient`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html): xây client, gửi đồng bộ/bất đồng bộ, kết nối, vòng đời và phiên bản HTTP.
- [Java SE 27 API — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): connect timeout, redirect, proxy, auth, cookie và executor.
- [Java SE 27 API — `HttpRequest`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.html): request bất biến.
- [Java SE 27 API — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): URI, method, headers, request timeout và options.
- [Java SE 27 API — `HttpRequest.BodyPublishers`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): các cách cung cấp request body.
- [Java SE 27 API — `HttpResponse<T>`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpResponse.html): status, headers, body, version và URI.
- [Java SE 27 API — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): xử lý `String`, file, stream và `limiting`.
- [Java SE 27 API — `HttpClient.Version`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.Version.html): HTTP/1.1, HTTP/2 và HTTP/3.
- [Java SE 27 API — `HttpOption`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpOption.html): gợi ý cấu hình liên quan đến HTTP/3.
- [Java SE 27 API — `HttpHeaders`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpHeaders.html): truy cập response headers.
- [Java SE 27 API — `HttpTimeoutException`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): timeout trong thực thi HTTP.
- [Java SE 27 API — `HttpConnectTimeoutException`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html): timeout khi kết nối.
- [Java SE 27 API — `HttpServer` (JDK module)](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server cục bộ phục vụ ví dụ kiểm thử.
