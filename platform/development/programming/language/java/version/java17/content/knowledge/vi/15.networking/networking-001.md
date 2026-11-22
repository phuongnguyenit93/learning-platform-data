# HttpClient chính thức và hỗ trợ HTTP/1.1, HTTP/2 trên Java 17

Từ Java 11, JDK cung cấp HTTP Client API chính thức trong package `java.net.http`. API này hỗ trợ gửi yêu cầu HTTP đồng bộ hoặc bất đồng bộ, quản lý request/response theo kiểu bất biến và hỗ trợ cả **HTTP/1.1** lẫn **HTTP/2**. Java 17 đã có sẵn API này, vì vậy ứng dụng có thể sử dụng trực tiếp mà không cần thư viện HTTP bên ngoài cho các nhu cầu HTTP thông thường.

Lớp trung tâm là `HttpClient`. Ta cấu hình client một lần, tạo `HttpRequest` cho từng yêu cầu và gọi `send()` hoặc `sendAsync()` để nhận `HttpResponse`. Client có thể ưu tiên HTTP/2 hoặc giới hạn ở HTTP/1.1; giao thức thực tế được sử dụng cần được xem từ response vì việc thương lượng với máy chủ có thể dẫn đến phiên bản khác với phiên bản mong muốn.

Bài học trình bày cách sử dụng `HttpClient` trên Java 17, sự khác nhau giữa HTTP/1.1 và HTTP/2, cách cấu hình phiên bản, gửi GET/POST, xử lý body, timeout, redirect, lỗi và request bất đồng bộ.

## 1. HTTP Client API chính thức của Java

Trước Java 11, lập trình viên thường sử dụng `HttpURLConnection` hoặc thư viện HTTP của bên thứ ba để gửi request. Từ Java 11, `java.net.http.HttpClient` trở thành API chuẩn của JDK. Java 17 tiếp tục hỗ trợ API này.

Các lớp quan trọng:

| Lớp / kiểu | Vai trò |
| --- | --- |
| `HttpClient` | Cấu hình và thực thi các HTTP request; có thể tái sử dụng cho nhiều request. |
| `HttpClient.Builder` | Cấu hình phiên bản HTTP, timeout kết nối, redirect, proxy, TLS và các tùy chọn client khác. |
| `HttpRequest` | Mô tả request: URI, method, header, timeout và body publisher. |
| `HttpRequest.Builder` | Tạo request theo từng bước. |
| `HttpResponse<T>` | Kết quả phản hồi gồm status, headers, URI, phiên bản HTTP và body kiểu `T`. |
| `HttpResponse.BodyHandler<T>` | Quyết định cách nhận và xử lý response body. |
| `HttpResponse.BodyHandlers` | Các body handler dựng sẵn như `ofString`, `ofByteArray`, `ofFile`, `ofInputStream`. |
| `HttpRequest.BodyPublisher` | Cung cấp dữ liệu request body. |
| `HttpRequest.BodyPublishers` | Các publisher dựng sẵn như `ofString`, `ofByteArray`, `ofFile`, `noBody`. |
| `HttpClient.Version` | Hằng số biểu diễn HTTP/1.1 hoặc HTTP/2. |

Các kiểu này nằm trong module `java.net.http`, thuộc JDK. Khi biên dịch và chạy ứng dụng Java thông thường trên classpath, không cần cài thêm dependency HTTP Client riêng.

Ví dụ import:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
```

## 2. HTTP/1.1 và HTTP/2 khác nhau thế nào?

`HttpClient` hỗ trợ hai phiên bản giao thức:

- **HTTP/1.1:** giao thức HTTP truyền thống, trao đổi request/response theo định dạng văn bản trên kết nối TCP. Kết nối có thể được tái sử dụng; khi cần xử lý nhiều request đồng thời, client có thể quản lý nhiều kết nối.
- **HTTP/2:** sử dụng framing nhị phân, hỗ trợ multiplex nhiều stream request/response trên cùng một kết nối, đồng thời nén header. Điều này giúp giảm chi phí mở nhiều kết nối và tránh việc một request chậm trên cùng kết nối chặn hoàn toàn các request khác như cách triển khai tuần tự đơn giản.

Bảng so sánh:

| Đặc điểm | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Định dạng giao thức | Văn bản cho message syntax, truyền qua TCP. | Binary framing trên TCP. |
| Xử lý nhiều request | Thường dùng kết nối persistent và có thể mở nhiều kết nối. | Multiplex nhiều stream trên một kết nối. |
| Header | Header lặp lại theo request. | Có cơ chế nén header HPACK. |
| Thứ tự request | Có thể gặp head-of-line blocking ở tầng HTTP khi các request được xếp hàng trên một kết nối. | Multiplex ở tầng HTTP; vẫn có thể chịu ảnh hưởng của mất gói ở tầng TCP. |
| Mức độ hỗ trợ trong Java 17 | Có. | Có. |
| Chọn trong `HttpClient` | `HttpClient.Version.HTTP_1_1` | `HttpClient.Version.HTTP_2` |

HTTP/2 không làm cho mọi request tự động nhanh hơn. Hiệu quả phụ thuộc độ trễ mạng, kích thước dữ liệu, số request, máy chủ, proxy và cách ứng dụng sử dụng kết nối.

### HTTP/2 được thương lượng như thế nào?

Với kết nối HTTPS, HTTP/2 thường được thương lượng qua TLS bằng cơ chế **ALPN** (Application-Layer Protocol Negotiation). Client và server thống nhất giao thức ứng dụng trong quá trình bắt tay TLS. Nếu server hoặc hạ tầng trung gian không hỗ trợ HTTP/2 trong kết nối đó, client có thể sử dụng HTTP/1.1.

Vì vậy cần phân biệt:

- Phiên bản **ưu tiên** được cấu hình trên client.
- Phiên bản **thực tế** được sử dụng cho một response.

Không nên chỉ nhìn cấu hình client rồi kết luận mọi request đều đã chạy bằng HTTP/2.

## 3. Tạo HttpClient và chọn phiên bản HTTP

### 3.1. Tạo client mặc định

Có thể tạo client bằng factory method:

```java
HttpClient client = HttpClient.newHttpClient();
```

Client mặc định ưu tiên HTTP/2. Nếu máy chủ hoặc kết nối không sử dụng được HTTP/2, HTTP Client có thể sử dụng HTTP/1.1 theo khả năng thương lượng.

Một `HttpClient` nên được tái sử dụng cho nhiều request thay vì tạo mới liên tục. Client quản lý tài nguyên kết nối và có thể tận dụng kết nối đã thiết lập cho các request tiếp theo.

### 3.2. Cấu hình ưu tiên HTTP/2

Dùng builder khi cần khai báo rõ phiên bản:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

`version(HTTP_2)` yêu cầu client ưu tiên HTTP/2. Đây không phải cam kết rằng mọi response đều là HTTP/2; server, TLS ALPN, proxy hoặc môi trường mạng có thể khiến kết nối dùng HTTP/1.1.

### 3.3. Giới hạn ở HTTP/1.1

Nếu hệ thống đích yêu cầu HTTP/1.1 hoặc cần tương thích với hạ tầng cũ, cấu hình:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();
```

Khi đó client dùng HTTP/1.1 cho request của nó. Đây là lựa chọn cấu hình giao thức rõ ràng, hữu ích khi tích hợp với máy chủ hoặc proxy chỉ hỗ trợ HTTP/1.1.

### 3.4. So sánh hai cách cấu hình

```java
HttpClient http2Client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();

HttpClient http11Client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();
```

Có thể dùng hai client riêng nếu ứng dụng gọi nhiều dịch vụ có yêu cầu giao thức khác nhau. Không có thuộc tính phiên bản HTTP riêng trên `HttpRequest.Builder` trong Java 17; phiên bản được cấu hình ở cấp `HttpClient`.

## 4. Gửi GET request đồng bộ

Phương thức `send()` gửi request và chờ response. Đây là cách đơn giản để gọi một API HTTP khi luồng hiện tại có thể chờ kết quả.

Ví dụ:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class GetExample {
    public static void main(String[] args)
            throws Exception {

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(10))
                .header("Accept", "text/html")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        System.out.println("Status: " + response.statusCode());
        System.out.println("HTTP version: " + response.version());
        System.out.println("Body:");
        System.out.println(response.body());
    }
}
```

Các bước:

1. Tạo `HttpClient` với phiên bản HTTP ưu tiên và timeout kết nối.
2. Tạo `HttpRequest` với URI, timeout riêng cho request, header và method GET.
3. Gọi `client.send(request, BodyHandlers.ofString(...))`.
4. Đọc status code, phiên bản HTTP thực tế và body.

`BodyHandlers.ofString(StandardCharsets.UTF_8)` đọc response body thành `String` theo UTF-8. Có thể chọn charset khác nếu giao thức/API yêu cầu.

Trong ví dụ, `example.com` là địa chỉ minh họa. Khi chạy thật, hãy thay bằng endpoint có thể truy cập và chính sách xác thực phù hợp.

## 5. Đọc thông tin từ HttpResponse

`HttpResponse<T>` cung cấp nhiều thông tin hữu ích:

| Phương thức | Ý nghĩa |
| --- | --- |
| `statusCode()` | Mã trạng thái HTTP, ví dụ 200, 404 hoặc 500. |
| `body()` | Response body theo kiểu `T` do body handler quyết định. |
| `headers()` | Các response header. |
| `uri()` | URI của response. |
| `version()` | Phiên bản HTTP thực tế của response. |
| `request()` | Request tương ứng với response. |
| `previousResponse()` | Response trước đó nếu có chuỗi redirect được theo dõi. |
| `sslSession()` | Thông tin TLS session nếu kết nối sử dụng SSL/TLS. |

Ví dụ đọc status và header:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);

int status = response.statusCode();
String contentType = response.headers()
        .firstValue("Content-Type")
        .orElse("Không có Content-Type");

System.out.println("Status: " + status);
System.out.println("Content-Type: " + contentType);
System.out.println("Version: " + response.version());
```

### Phân biệt phiên bản ưu tiên và phiên bản thực tế

`client.version()` trả về phiên bản ưu tiên của client. `response.version()` cho biết phiên bản HTTP được dùng cho response cụ thể.

Ví dụ, client được cấu hình `HTTP_2` nhưng response báo `HTTP_1_1`. Điều này có thể xảy ra khi HTTP/2 không được thương lượng hoặc server/hạ tầng chỉ hỗ trợ HTTP/1.1.

Khi cần xác nhận giao thức thực tế, hãy kiểm tra `response.version()` thay vì chỉ kiểm tra `client.version()`.

## 6. Gửi POST request có body

Để gửi dữ liệu trong request body, dùng `HttpRequest.BodyPublishers`.

Ví dụ gửi JSON:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class PostExample {
    public static void main(String[] args)
            throws Exception {

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .build();

        String json = """
                {
                    "name": "Lan",
                    "role": "developer"
                }
                """;

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/users"))
                .timeout(Duration.ofSeconds(15))
                .header("Content-Type", "application/json; charset=UTF-8")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        json,
                        StandardCharsets.UTF_8
                ))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        System.out.println(response.statusCode());
        System.out.println(response.body());
    }
}
```

`BodyPublishers.ofString(json, UTF_8)` tạo request body từ chuỗi với charset UTF-8. Header `Content-Type` cho server biết body được gửi theo định dạng JSON và charset tương ứng.

Text block trong ví dụ giúp viết JSON nhiều dòng dễ đọc. Nó không tự kiểm tra JSON hợp lệ; với dữ liệu động, nên dùng thư viện JSON phù hợp để serialize object thay vì tự nối chuỗi.

### Gửi byte array

Nếu request body đã là dữ liệu nhị phân, có thể dùng `ofByteArray`:

```java
byte[] payload = {0x01, 0x02, 0x03};

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/upload"))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
        .build();
```

### Gửi file

Có thể dùng `ofFile`:

```java
import java.nio.file.Path;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/upload"))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofFile(Path.of("upload.bin")))
        .build();
```

`ofFile` đọc dữ liệu từ file để tạo request body. File phải tồn tại và có thể đọc được; lỗi truy cập file có thể được báo khi tạo publisher hoặc trong quá trình gửi, tùy thao tác và implementation.

## 7. Chọn BodyHandler phù hợp

Response body có thể là văn bản, byte array, file hoặc stream. Chọn body handler theo loại dữ liệu và kích thước nội dung.

| Body handler | Kiểu body | Khi phù hợp |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `String` | JSON, HTML, XML hoặc văn bản có kích thước vừa phải. |
| `BodyHandlers.ofByteArray()` | `byte[]` | Dữ liệu nhị phân cần giữ trong bộ nhớ. |
| `BodyHandlers.ofFile(path)` | `Path` | Tải file xuống đĩa. |
| `BodyHandlers.ofInputStream()` | `InputStream` | Xử lý dữ liệu theo stream khi cần kiểm soát việc đọc. |
| `BodyHandlers.discarding()` | `Void` | Không cần response body. |
| `BodyHandlers.replacing(value)` | Giá trị thay thế | Bỏ body và trả về giá trị xác định. |

### Đọc body thành String

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
);
```

Đây là lựa chọn tiện lợi cho API trả JSON hoặc văn bản có kích thước phù hợp. Với response rất lớn, đọc toàn bộ vào `String` có thể tiêu tốn nhiều bộ nhớ.

### Tải body xuống file

```java
import java.nio.file.Path;

HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(Path.of("download.bin"))
);

System.out.println("Saved to: " + response.body());
```

Body handler ghi nội dung response vào file đã chỉ định và body của response là đường dẫn file. Hãy chọn vị trí lưu có quyền ghi và kiểm soát tên file nếu tên đến từ bên ngoài.

### Nhận InputStream

```java
import java.io.InputStream;

HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream()
);

try (InputStream input = response.body()) {
    byte[] buffer = input.readNBytes(4096);
    System.out.println("Read bytes: " + buffer.length);
}
```

Khi dùng `ofInputStream()`, ứng dụng phải đóng stream body sau khi đọc xong. Nếu không, tài nguyên liên quan có thể bị giữ lại lâu hơn cần thiết. Ví dụ đọc `readNBytes(4096)` chỉ lấy tối đa 4096 byte đầu tiên; ứng dụng thực tế cần lặp đọc đến EOF hoặc chuyển stream sang nơi xử lý phù hợp.

## 8. Cấu hình timeout

Có hai loại timeout thường cần phân biệt:

- **Connect timeout:** giới hạn thời gian thiết lập kết nối.
- **Request timeout:** giới hạn thời gian chờ request hoàn thành theo cấu hình của request.

Ví dụ:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/data"))
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
```

`connectTimeout` thuộc `HttpClient.Builder`, còn `timeout` thuộc `HttpRequest.Builder`.

Không đặt timeout có thể khiến thao tác chờ lâu hơn dự kiến khi server hoặc mạng không phản hồi. Giá trị phù hợp phụ thuộc loại tác vụ: request đọc dữ liệu nhỏ có thể có timeout ngắn hơn request tải file lớn.

Khi timeout xảy ra, request có thể hoàn thành bất thường với `HttpTimeoutException` (là một dạng `IOException`). Cần xử lý ngoại lệ và quyết định có retry hay trả lỗi cho người gọi.

Timeout ở client không thay thế timeout nghiệp vụ, giới hạn kích thước body hoặc giới hạn thời gian xử lý ở server.

## 9. Xử lý redirect

HTTP server có thể trả mã redirect như 301, 302, 303, 307 hoặc 308 cùng header `Location`. Mặc định, `HttpClient` không tự động theo redirect.

Có thể cấu hình chính sách:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

Các lựa chọn:

| Giá trị | Hành vi |
| --- | --- |
| `HttpClient.Redirect.NEVER` | Không tự động theo redirect. Đây là mặc định. |
| `HttpClient.Redirect.NORMAL` | Theo redirect, ngoại trừ chuyển từ HTTPS xuống HTTP. |
| `HttpClient.Redirect.ALWAYS` | Theo cả redirect từ HTTPS xuống HTTP. |

Với dữ liệu nhạy cảm, cần thận trọng khi theo redirect vì đích mới có thể khác host hoặc scheme. Đặc biệt, không nên hạ từ HTTPS xuống HTTP khi truyền thông tin xác thực. Chọn chính sách phù hợp với yêu cầu bảo mật và kiểm soát đích đến.

Có thể xem response trước đó bằng `previousResponse()` nếu client đã theo chuỗi redirect.

## 10. Xử lý lỗi và status code

`client.send()` không tự ném exception chỉ vì server trả status 404 hoặc 500. Đây là response HTTP hợp lệ ở tầng giao thức; ứng dụng phải đọc `statusCode()` và quyết định ý nghĩa nghiệp vụ.

Ví dụ:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);

if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    System.out.println("Request thành công");
    System.out.println(response.body());
} else {
    System.err.println("HTTP error: " + response.statusCode());
    System.err.println(response.body());
}
```

Một số nhóm status thường gặp:

| Nhóm | Ý nghĩa |
| --- | --- |
| 2xx | Request được xử lý thành công. |
| 3xx | Cần redirect hoặc có hành vi điều hướng khác. |
| 4xx | Request hoặc quyền truy cập có vấn đề, ví dụ 400, 401, 403, 404. |
| 5xx | Server hoặc gateway gặp lỗi, ví dụ 500, 502, 503. |

Các lỗi ở tầng client/network có thể phát sinh exception:

- `IOException`: lỗi I/O, kết nối hoặc đọc/ghi dữ liệu.
- `HttpTimeoutException`: request vượt timeout.
- `InterruptedException`: thread đang chờ bị interrupt.
- `IllegalArgumentException`: có thể phát sinh khi cấu hình URI/request không hợp lệ.

### Giữ trạng thái interrupt

Nếu phương thức đồng bộ bị interrupt, nên khôi phục trạng thái interrupt khi xử lý hoặc chuyển tiếp lỗi:

```java
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
    );

    System.out.println(response.statusCode());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("HTTP request bị interrupt", ex);
} catch (java.io.IOException ex) {
    throw new IllegalStateException("Không thể gọi HTTP endpoint", ex);
}
```

Việc gọi `Thread.currentThread().interrupt()` giữ lại tín hiệu interrupt cho lớp gọi hoặc cơ chế quản lý thread ở phía trên. Không nên nuốt `InterruptedException` rồi tiếp tục chạy như thể không có chuyện gì xảy ra.

## 11. Gửi request bất đồng bộ bằng sendAsync()

`send()` chặn thread hiện tại cho đến khi response hoàn tất. Khi ứng dụng cần xử lý nhiều request đồng thời hoặc không muốn giữ thread chờ I/O, dùng `sendAsync()`.

Phương thức này trả về `CompletableFuture<HttpResponse<T>>`.

Ví dụ:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class AsyncGetExample {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        CompletableFuture<HttpResponse<String>> future =
                client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8
                        )
                );

        future.thenApply(response -> {
                    System.out.println("Status: " + response.statusCode());
                    System.out.println("Version: " + response.version());
                    return response.body();
                })
                .thenAccept(body -> System.out.println(body.length()))
                .exceptionally(error -> {
                    System.err.println("Request failed: " + error);
                    return null;
                });
    }
}
```

Các bước:

1. `sendAsync` gửi request và trả về future ngay.
2. `thenApply` xử lý response khi future hoàn tất và chuyển đổi kết quả.
3. `thenAccept` nhận kết quả nhưng không cần trả giá trị tiếp theo.
4. `exceptionally` xử lý lỗi trong chuỗi future.

Ví dụ dùng `main()` chỉ để minh họa API. Khi ứng dụng cần giữ tiến trình đến khi tác vụ hoàn tất, hãy tích hợp future vào vòng đời ứng dụng hoặc cơ chế điều phối phù hợp. Không nên tùy tiện gọi `join()` ngay sau `sendAsync()` trong code cần bất đồng bộ, vì làm vậy lại chặn thread hiện tại.

### Kết hợp nhiều request

Có thể gửi nhiều request bất đồng bộ và đợi tất cả hoàn tất:

```java
CompletableFuture<HttpResponse<String>> first =
        client.sendAsync(request1, HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<String>> second =
        client.sendAsync(request2, HttpResponse.BodyHandlers.ofString());

CompletableFuture<Void> all = CompletableFuture.allOf(first, second);

all.thenRun(() -> {
    System.out.println(first.join().statusCode());
    System.out.println(second.join().statusCode());
});
```

`CompletableFuture.allOf` hoàn tất khi tất cả future truyền vào hoàn tất. Nếu một future hoàn tất bất thường, future tổng hợp cũng hoàn tất bất thường. Trong callback chỉ nên gọi `join()` với các future đã được bảo đảm hoàn tất bởi `allOf`.

HTTP/2 multiplexing có thể giúp nhiều request chia sẻ một kết nối, nhưng `sendAsync` và HTTP/2 là hai khái niệm khác nhau: bất đồng bộ là cách ứng dụng chờ kết quả; HTTP/2 là phiên bản giao thức. Có thể dùng `sendAsync` với client HTTP/1.1, và có thể dùng `send` với client ưu tiên HTTP/2.

## 12. Cấu hình client: proxy, authenticator và TLS

`HttpClient.Builder` có thể cấu hình thêm các thành phần kết nối.

### Proxy

Nếu ứng dụng phải đi qua proxy:

```java
import java.net.ProxySelector;

HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.getDefault())
        .build();
```

`ProxySelector.getDefault()` sử dụng cấu hình proxy mặc định của môi trường Java nếu có. Với ứng dụng cần proxy cụ thể, có thể cấu hình `ProxySelector` riêng.

### Authenticator

Có thể cung cấp `Authenticator` cho các cơ chế xác thực HTTP được hỗ trợ:

```java
import java.net.Authenticator;
import java.net.PasswordAuthentication;

Authenticator authenticator = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        return new PasswordAuthentication(
                "api-user",
                System.getenv("API_PASSWORD").toCharArray()
        );
    }
};

HttpClient client = HttpClient.newBuilder()
        .authenticator(authenticator)
        .build();
```

Ví dụ chỉ minh họa vị trí cấu hình. Cần giới hạn phạm vi credential, lấy secret từ secret manager hoặc cấu hình bảo mật phù hợp và tránh ghi mật khẩu vào log hoặc source code. Với API token kiểu Bearer, thường đặt header `Authorization` theo hợp đồng API và bảo vệ token như thông tin bí mật.

### TLS/HTTPS

Với URI HTTPS, `HttpClient` sử dụng cấu hình SSL/TLS mặc định của JDK nếu không cung cấp cấu hình riêng. Trong production, giữ việc xác thực chứng chỉ và hostname theo cấu hình an toàn.

Không tắt xác thực chứng chỉ hoặc chấp nhận mọi hostname để “sửa nhanh” lỗi TLS. Cần cài đúng CA/certificate, kiểm tra trust store hoặc cấu hình `SSLContext` theo chính sách bảo mật của hệ thống.

## 13. Đặt header và method tùy chỉnh

Request builder hỗ trợ thêm header:

```java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/items"))
        .header("Accept", "application/json")
        .header("X-Request-Id", "req-123")
        .GET()
        .build();
```

Một số method dựng sẵn:

- `GET()`
- `POST(BodyPublisher)`
- `PUT(BodyPublisher)`
- `DELETE()`

Có thể dùng `method(String, BodyPublisher)` cho method khác hoặc khi cần khai báo body theo API:

```java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/items/42"))
        .header("Content-Type", "application/json")
        .method("PATCH", HttpRequest.BodyPublishers.ofString(
                "{\"name\":\"Updated\"}"
        ))
        .build();
```

Chỉ dùng method và body phù hợp với API server. Một số method thường không có body theo quy ước hoặc bị server/proxy xử lý khác nhau.

## 14. Giới hạn kích thước và cách đọc response

`BodyHandlers.ofString()` và `ofByteArray()` đọc toàn bộ body vào bộ nhớ. Điều này thuận tiện với response nhỏ, nhưng không phù hợp nếu server có thể trả dữ liệu rất lớn.

Với file lớn, cân nhắc `BodyHandlers.ofFile(path)`. Nếu dùng `ofInputStream()`, đọc theo từng buffer và đóng stream sau khi hoàn tất.

Ngoài ra, ứng dụng nên kiểm soát:

- Kích thước file tải xuống và dung lượng đĩa.
- Thời gian request và thời gian đọc body.
- Loại nội dung qua `Content-Type`.
- Tên file và đường dẫn lưu, tránh path traversal khi tên do server/client cung cấp.
- Trạng thái HTTP trước khi xử lý body như dữ liệu thành công.

Body handler quyết định cách nhận body, nhưng không tự thay thế validation nội dung. Ví dụ response khai báo JSON vẫn cần được parse và kiểm tra schema/dữ liệu theo hợp đồng ứng dụng.

## 15. HTTP/2 và việc xác nhận giao thức thực tế

Để ưu tiên HTTP/2:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

Sau khi gửi request, xem:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);

System.out.println("Preferred: " + client.version());
System.out.println("Used: " + response.version());
```

`client.version()` cho biết phiên bản client ưu tiên; `response.version()` cho biết phiên bản dùng cho response.

Nếu kết quả là `HTTP_1_1` dù client ưu tiên `HTTP_2`, hãy kiểm tra:

1. Server có hỗ trợ HTTP/2 không.
2. Với HTTPS, TLS/ALPN có thương lượng HTTP/2 thành công không.
3. Proxy, load balancer hoặc gateway có can thiệp và giới hạn giao thức không.
4. Endpoint cụ thể có chính sách hỗ trợ giao thức khác với endpoint khác không.

Không nên kết luận Java 17 không hỗ trợ HTTP/2 chỉ vì một endpoint trả về HTTP/1.1. Java 17 có hỗ trợ HTTP/2; giao thức cuối cùng phụ thuộc khả năng của peer và kết nối.

## 16. Những giới hạn và điểm cần lưu ý của Java 17 HttpClient

- `HttpClient.Version` trong Java 17 cung cấp `HTTP_1_1` và `HTTP_2`. API này không cung cấp HTTP/3.
- Phiên bản được cấu hình ở cấp client, không phải tùy chọn độc lập trên từng `HttpRequest`.
- `HttpClient` và `HttpRequest` được thiết kế bất biến sau khi tạo; dùng builder để tạo cấu hình mới.
- Không gọi lại terminal method trên cùng `CompletableFuture` như thể future có thể khởi chạy request lần nữa; muốn gửi request mới, tạo request và gọi client lại.
- HTTP status lỗi không tự động trở thành exception; ứng dụng phải kiểm tra status code.
- Redirect mặc định là `NEVER`.
- `send()` có thể ném `IOException` và `InterruptedException`.
- `sendAsync()` trả future, lỗi được thể hiện qua completion bất thường.
- Body handler cần được chọn theo loại dữ liệu; stream body phải được đóng.
- Không nên tạo một `HttpClient` mới cho từng request nếu có thể tái sử dụng client đã cấu hình.

## 17. Ví dụ tổng hợp: client có cấu hình và xử lý lỗi

Ví dụ dưới đây gói cấu hình và cách gọi GET vào một lớp nhỏ:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class ApiClient {

    private final HttpClient client;

    public ApiClient() {
        this.client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    public String getText(URI uri)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri)
                .timeout(Duration.ofSeconds(10))
                .header("Accept", "text/plain")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8
                )
        );

        if (response.statusCode() < 200
                || response.statusCode() >= 300) {
            throw new IOException(
                    "HTTP request failed with status "
                            + response.statusCode()
            );
        }

        System.out.println("Protocol: " + response.version());

        return response.body();
    }
}
```

Cách sử dụng:

```java
ApiClient apiClient = new ApiClient();

try {
    String body = apiClient.getText(
            URI.create("https://example.com/")
    );

    System.out.println(body);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    System.err.println("Request interrupted");
} catch (IOException ex) {
    System.err.println("Request failed: " + ex.getMessage());
}
```

Trong ứng dụng thực tế, nên bổ sung chính sách retry có giới hạn và chỉ retry những method/tác vụ phù hợp. Không tự động retry mọi POST vì request có thể đã được server thực hiện dù response bị mất trên đường truyền. Với thao tác cần retry, thiết kế idempotency key hoặc cơ chế bảo đảm nghiệp vụ phù hợp.

## 18. Kiểm thử ứng dụng sử dụng HttpClient

Khi kiểm thử code gọi HTTP, nên tách phần tạo request và xử lý response khỏi endpoint cụ thể để có thể thay đổi URI hoặc dùng server giả lập.

Một số cách kiểm thử:

- **Unit test:** kiểm tra việc tạo URI, method, header, body và cách xử lý status thông qua một abstraction nhỏ bao quanh HTTP client.
- **Integration test:** chạy HTTP server thử nghiệm trên localhost và gửi request đến server đó.
- **Kiểm thử HTTP/1.1:** server test đơn giản có thể hỗ trợ HTTP/1.1 để xác nhận request/response và body.
- **Kiểm thử HTTP/2:** dùng endpoint hoặc test server có hỗ trợ HTTP/2 thực sự, TLS và ALPN khi phù hợp; sau request kiểm tra `response.version()`.
- **Kiểm thử timeout/lỗi:** mô phỏng endpoint chậm, không khả dụng, trả status lỗi hoặc đóng kết nối.

`com.sun.net.httpserver.HttpServer` trong module `jdk.httpserver` có thể hữu ích cho một HTTP server cục bộ đơn giản, nhưng nó không phải server HTTP/2. Không dùng việc test thành công với server này để kết luận đã kiểm tra HTTP/2.

Đối với test cần xác nhận protocol, hãy kiểm tra `response.version()` và dùng server có hỗ trợ đúng giao thức. Không phụ thuộc vào một website công cộng bên ngoài trong unit test vì kết quả có thể thay đổi theo mạng, server và chính sách truy cập.

## 19. Bài thực hành

### Bài 1 — gửi GET bằng HTTP/2 preference

Tạo `HttpClient` với `version(HTTP_2)`, gửi GET đến một endpoint HTTPS có thể truy cập, đọc status code và in `response.version()`. Giải thích vì sao kết quả thực tế có thể là HTTP/1.1.

### Bài 2 — ép dùng HTTP/1.1

Tạo một client khác với `version(HTTP_1_1)`. Gửi cùng request và quan sát `response.version()`. So sánh cấu hình ưu tiên và giao thức thực tế.

### Bài 3 — POST JSON

Tạo request POST có body JSON bằng text block. Đặt `Content-Type: application/json` và `Accept: application/json`. Dùng `BodyPublishers.ofString` với UTF-8 và xử lý status response.

### Bài 4 — timeout

Cấu hình connect timeout 3 giây và request timeout 5 giây. Gọi endpoint thử nghiệm có độ trễ, xử lý `HttpTimeoutException` hoặc `IOException` phù hợp. Giải thích hai timeout kiểm soát hai giai đoạn khác nhau.

### Bài 5 — tải file

Dùng `BodyHandlers.ofFile` để tải nội dung xuống một đường dẫn do ứng dụng kiểm soát. Kiểm tra status code trước khi sử dụng file đã tải và đảm bảo thư mục đích có quyền ghi.

### Bài 6 — bất đồng bộ

Dùng `sendAsync` và `thenApply` để lấy status code, tiếp theo `thenAccept` để xử lý body. Thêm `exceptionally` để ghi nhận lỗi. Không gọi `join()` ngay sau khi gửi nếu mục tiêu là giữ luồng xử lý bất đồng bộ.

### Bài 7 — kiểm tra redirect

Tạo client với `Redirect.NEVER` và một client với `Redirect.NORMAL`. Gọi endpoint test trả redirect, so sánh status, URI cuối và `previousResponse()` khi có.

## 20. Ghi nhớ nhanh

| Nhu cầu | API |
| --- | --- |
| Tạo HTTP client mặc định | `HttpClient.newHttpClient()` |
| Ưu tiên HTTP/2 | `version(HttpClient.Version.HTTP_2)` |
| Chỉ dùng HTTP/1.1 | `version(HttpClient.Version.HTTP_1_1)` |
| Gửi request đồng bộ | `client.send(request, bodyHandler)` |
| Gửi request bất đồng bộ | `client.sendAsync(request, bodyHandler)` |
| Tạo GET | `HttpRequest.Builder.GET()` |
| Tạo POST | `POST(BodyPublishers.ofString(...))` |
| Thêm header | `header(name, value)` |
| Timeout kết nối | `HttpClient.Builder.connectTimeout(duration)` |
| Timeout request | `HttpRequest.Builder.timeout(duration)` |
| Đọc body văn bản | `BodyHandlers.ofString(UTF_8)` |
| Đọc body byte | `BodyHandlers.ofByteArray()` |
| Ghi body vào file | `BodyHandlers.ofFile(path)` |
| Kiểm tra status | `response.statusCode()` |
| Kiểm tra protocol thực tế | `response.version()` |
| Theo redirect | `followRedirects(Redirect.NORMAL)` |
| Đọc header | `response.headers()` |

**Nguyên tắc cốt lõi:** Java 17 có HTTP Client API chính thức trong `java.net.http`, hỗ trợ HTTP/1.1 và HTTP/2. Tạo và tái sử dụng `HttpClient`, xây `HttpRequest` cho từng lần gọi, chọn `BodyHandler` phù hợp và kiểm tra status/response. Cấu hình `HTTP_2` là ưu tiên giao thức; hãy xem `response.version()` để biết request thực tế dùng HTTP/1.1 hay HTTP/2.
