# Gọi dịch vụ HTTP/2 và xử lý lỗi, thời gian chờ trong Java 17

Java 17 có HTTP Client API chính thức trong package `java.net.http`. API này cho phép ứng dụng gọi dịch vụ HTTP đồng bộ hoặc bất đồng bộ, gửi request có header/body, nhận response và chọn phiên bản HTTP ưu tiên. Với dịch vụ hỗ trợ HTTP/2, client có thể sử dụng multiplexing để gửi nhiều request trên cùng kết nối; nếu HTTP/2 không được thương lượng thành công, kết nối có thể dùng HTTP/1.1.

Một lời gọi dịch vụ đáng tin cậy cần xử lý đủ bốn phần:

1. **Giao thức và kết nối:** ưu tiên HTTP/2, tái sử dụng client, hiểu khả năng fallback và TLS/ALPN.
2. **Thời gian chờ:** giới hạn thời gian kết nối và thời gian cho từng request.
3. **Kết quả HTTP:** phân biệt status code thành công, lỗi phía client và lỗi phía server.
4. **Lỗi vận chuyển và phục hồi:** xử lý timeout, DNS, TLS, kết nối bị đóng, interruption và retry có giới hạn.

Bài học sử dụng `HttpClient`, `HttpRequest` và `HttpResponse` có sẵn trong JDK 17. Ví dụ dùng HTTPS endpoint minh họa; hãy thay bằng địa chỉ và hợp đồng API thực tế của dịch vụ cần gọi.

## 1. HTTP/2 trong Java 17

HTTP/2 là phiên bản giao thức HTTP sử dụng binary framing và cho phép multiplex nhiều stream request/response trên cùng một kết nối. So với mô hình HTTP/1.1 truyền thống, multiplexing có thể giảm nhu cầu mở nhiều kết nối khi client gửi nhiều request đồng thời.

Java 17 hỗ trợ HTTP/1.1 và HTTP/2 thông qua `java.net.http.HttpClient`. Lớp này quản lý kết nối và có thể được tái sử dụng cho nhiều request.

### 1.1. Ưu tiên HTTP/2

Tạo client:

```java
import java.net.http.HttpClient;

HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

`version(HttpClient.Version.HTTP_2)` đặt phiên bản ưu tiên cho client. Đây không phải cam kết rằng mọi request đều dùng HTTP/2. Phiên bản thực tế còn phụ thuộc server, TLS, ALPN và các proxy/load balancer trên đường truyền.

### 1.2. Xác nhận phiên bản HTTP thực tế

Sau khi nhận response, kiểm tra `response.version()`:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);

System.out.println("HTTP version: " + response.version());
```

Kết quả là `HttpClient.Version.HTTP_2` hoặc `HttpClient.Version.HTTP_1_1`.

Cần phân biệt:

- `client.version()` cho biết phiên bản client được cấu hình ưu tiên.
- `response.version()` cho biết phiên bản thực tế được dùng cho response đó.

Nếu client ưu tiên HTTP/2 nhưng response dùng HTTP/1.1, hãy kiểm tra server và hạ tầng mạng. Với HTTPS, HTTP/2 thường được thương lượng qua TLS bằng ALPN. Nếu server, proxy hoặc gateway không hỗ trợ HTTP/2 trên kết nối đó, client có thể sử dụng HTTP/1.1.

### 1.3. Tái sử dụng HttpClient

Nên tạo một `HttpClient` dùng chung cho các request đến cùng nhóm dịch vụ hoặc cùng chính sách kết nối:

```java
private static final HttpClient HTTP_CLIENT =
        HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .build();
```

`HttpClient` được thiết kế để tái sử dụng và quản lý kết nối. Tạo client mới cho từng request làm mất cơ hội tái sử dụng connection và có thể tăng chi phí kết nối/TLS handshake.

HTTP/2 multiplexing không có nghĩa mọi request đều chạy nhanh hơn trong mọi tình huống. Throughput và latency còn phụ thuộc server, số stream được cho phép, network, payload, flow control và mức tải. Hãy đo trên workload thật.

## 2. Cấu hình timeout: kết nối và request

Một lời gọi HTTP có thể chờ ở nhiều giai đoạn: thiết lập kết nối, TLS handshake, gửi request, chờ response hoặc đọc body. Java HTTP Client cung cấp hai cấu hình timeout quan trọng.

| Timeout | Cấu hình tại | Mục đích |
| --- | --- | --- |
| Connect timeout | `HttpClient.Builder.connectTimeout(Duration)` | Giới hạn thời gian thiết lập kết nối khi cần tạo kết nối mới. |
| Request timeout | `HttpRequest.Builder.timeout(Duration)` | Đặt thời hạn cho request cụ thể; nếu response không được nhận trong thời hạn, request có thể thất bại với `HttpTimeoutException`. |

### 2.1. Connect timeout

Cấu hình ở cấp client:

```java
import java.time.Duration;
import java.net.http.HttpClient;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .version(HttpClient.Version.HTTP_2)
        .build();
```

Nếu không thể thiết lập kết nối trong thời hạn, lời gọi có thể thất bại với lỗi timeout. Connect timeout có ý nghĩa khi client cần thiết lập kết nối; nếu client tái sử dụng một kết nối đã có, không có bước connect mới để áp dụng timeout này.

### 2.2. Request timeout

Cấu hình trên từng request:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/v1/status"))
        .timeout(Duration.ofSeconds(8))
        .GET()
        .build();
```

Request timeout giúp ngăn một request chờ vô hạn khi dịch vụ không phản hồi đúng hạn. Mỗi request có thể có thời hạn khác nhau tùy nghiệp vụ: truy vấn nhỏ có thể ngắn, còn thao tác tải file có thể cần dài hơn.

Không nhầm request timeout với SLA tổng thể của một nghiệp vụ. Nếu ứng dụng thực hiện nhiều request tuần tự, retry hoặc xử lý thêm dữ liệu, tổng thời gian nghiệp vụ có thể dài hơn timeout của một request. Hãy đặt deadline tổng thể ở tầng nghiệp vụ nếu cần giới hạn toàn bộ quy trình.

### 2.3. Chọn giá trị timeout

Giá trị timeout cần dựa trên latency bình thường, tail latency, SLA và thời gian phục hồi mà ứng dụng chấp nhận.

Ví dụ minh họa:

| Loại request | Connect timeout | Request timeout |
| --- | ---: | ---: |
| Đọc trạng thái dịch vụ | 2–3 giây | 3–5 giây |
| Truy vấn dữ liệu thông thường | 2–3 giây | 5–10 giây |
| Gửi tác vụ xử lý lâu | 2–3 giây | Theo hợp đồng nghiệp vụ |
| Tải file lớn | 2–5 giây | Theo kích thước và tốc độ dự kiến |

Đây không phải giá trị mặc định bắt buộc. Nếu timeout quá ngắn, request hợp lệ có thể thất bại trong thời điểm tải cao. Nếu quá dài, thread và tài nguyên ứng dụng có thể bị giữ lâu, làm tăng hàng đợi và ảnh hưởng request khác.

## 3. Gửi GET đồng bộ và đọc response

`send()` gửi request rồi chờ response hoàn tất theo body handler. Phương thức này phù hợp với luồng xử lý có thể chờ kết quả.

Ví dụ:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class GetServiceExample {

    private static final HttpClient CLIENT =
            HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

    public static void main(String[] args)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/v1/users/42"))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = CLIENT.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        System.out.println("Status: " + response.statusCode());
        System.out.println("HTTP version: " + response.version());
        System.out.println("Content-Type: "
                + response.headers()
                        .firstValue("Content-Type")
                        .orElse("not provided"));
        System.out.println(response.body());
    }
}
```

Các bước:

1. Tạo và tái sử dụng `HttpClient` với phiên bản HTTP ưu tiên và connect timeout.
2. Tạo `HttpRequest` có URI, request timeout, header và method.
3. Gọi `send(request, BodyHandlers.ofString(...))`.
4. Đọc status code, HTTP version, header và body.

`BodyHandlers.ofString(StandardCharsets.UTF_8)` đọc response body thành `String`. Cách này thuận tiện cho JSON hoặc văn bản có kích thước vừa phải. Với body lớn, cân nhắc ghi trực tiếp xuống file hoặc đọc theo stream.

Ví dụ dùng `api.example.com` chỉ để minh họa. Endpoint thực tế có thể cần authentication, query parameter hoặc header riêng theo API contract.

## 4. HTTP status code không tự động trở thành exception

Một điểm quan trọng khi dùng `HttpClient` là response status 404, 429 hoặc 500 vẫn là một HTTP response hợp lệ ở tầng giao thức. `send()` không tự ném exception chỉ vì status code nằm trong nhóm lỗi.

Ứng dụng phải kiểm tra `response.statusCode()`:

```java
int status = response.statusCode();

if (status >= 200 && status < 300) {
    System.out.println("Request thành công");
} else {
    System.err.println("HTTP error: " + status);
}
```

Có thể phân loại sơ bộ:

| Nhóm status | Ý nghĩa | Hướng xử lý thường gặp |
| --- | --- | --- |
| 2xx | Request thành công | Xử lý response body theo API contract. |
| 3xx | Redirect | Kiểm tra redirect policy hoặc xử lý Location. |
| 4xx | Request/client/authentication có vấn đề | Sửa request, quyền truy cập hoặc dữ liệu; thường không retry tự động. |
| 5xx | Server/gateway gặp lỗi | Có thể retry có giới hạn nếu thao tác an toàn và lỗi có tính tạm thời. |

Một số status đáng chú ý:

- `400 Bad Request`: dữ liệu hoặc cú pháp request không hợp lệ.
- `401 Unauthorized`: thiếu hoặc sai thông tin xác thực.
- `403 Forbidden`: danh tính đã xác thực nhưng không được phép.
- `404 Not Found`: tài nguyên không tồn tại hoặc không được công khai.
- `408 Request Timeout`: server/proxy không nhận đủ request trong thời gian quy định.
- `409 Conflict`: xung đột trạng thái nghiệp vụ.
- `422 Unprocessable Content`: nội dung hợp lệ về cú pháp nhưng không đáp ứng quy tắc xử lý.
- `429 Too Many Requests`: vượt giới hạn tần suất.
- `500 Internal Server Error`: lỗi xử lý phía server.
- `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout`: lỗi hoặc quá tải ở gateway/service trung gian.

Status code cần được hiểu theo hợp đồng API. Ví dụ, một số API có thể dùng 404 để che giấu tài nguyên mà người gọi không được quyền truy cập.

## 5. Xây dựng ngoại lệ cho HTTP status lỗi

Ứng dụng có thể chuyển response ngoài nhóm 2xx thành exception riêng để tầng gọi xử lý thống nhất.

Ví dụ:

```java
public final class RemoteServiceException extends RuntimeException {

    private final int statusCode;
    private final String responseBody;

    public RemoteServiceException(int statusCode, String responseBody) {
        super("Remote service returned HTTP " + statusCode);
        this.statusCode = statusCode;
        this.responseBody = responseBody;
    }

    public int statusCode() {
        return statusCode;
    }

    public String responseBody() {
        return responseBody;
    }
}
```

Helper kiểm tra response:

```java
import java.net.http.HttpResponse;

static String requireSuccess(HttpResponse<String> response) {
    int status = response.statusCode();

    if (status < 200 || status >= 300) {
        throw new RemoteServiceException(
                status,
                response.body()
        );
    }

    return response.body();
}
```

Dùng:

```java
HttpResponse<String> response = CLIENT.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);

String json = requireSuccess(response);
```

Giữ lại status và một phần error body có thể giúp chẩn đoán. Tuy nhiên, không ghi toàn bộ body vào log một cách vô điều kiện: response có thể chứa token, thông tin cá nhân hoặc dữ liệu nội bộ. Nên giới hạn kích thước, lọc trường nhạy cảm và kiểm soát quyền truy cập log.

Không giả định body của response lỗi luôn là JSON. Một proxy có thể trả HTML hoặc text; hãy kiểm tra Content-Type và parse theo API contract.

## 6. Xử lý timeout và lỗi mạng khi dùng send()

`HttpClient.send()` khai báo hai nhóm exception chính:

- `IOException`: lỗi I/O trong quá trình gửi/nhận.
- `InterruptedException`: thread đang chờ bị interrupt.

`HttpTimeoutException` là subclass của `IOException` và có thể được ném khi request timeout.

Một số exception có thể gặp:

| Exception | Tình huống có thể xảy ra |
| --- | --- |
| `HttpTimeoutException` | Request không hoàn tất trong thời hạn được cấu hình. |
| `ConnectException` | Không thiết lập được kết nối tới host/port. |
| `UnknownHostException` | Không phân giải được hostname. |
| `SSLHandshakeException` | TLS handshake thất bại, ví dụ certificate hoặc protocol không phù hợp. |
| `IOException` | Kết nối bị đóng, lỗi đọc/ghi hoặc lỗi mạng khác. |
| `InterruptedException` | Thread chờ request bị interrupt. |

Ví dụ xử lý:

```java
import java.io.IOException;
import java.net.http.HttpTimeoutException;

try {
    HttpResponse<String> response = CLIENT.send(
            request,
            HttpResponse.BodyHandlers.ofString()
    );

    String body = requireSuccess(response);
    System.out.println(body);

} catch (HttpTimeoutException ex) {
    System.err.println("HTTP request timed out: " + ex.getMessage());

} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "HTTP request was interrupted",
            ex
    );

} catch (IOException ex) {
    System.err.println("HTTP transport failure: " + ex.getMessage());
}
```

Cần bắt `HttpTimeoutException` trước `IOException` vì nó là lớp con. Khi bắt `InterruptedException`, khôi phục interrupt bằng `Thread.currentThread().interrupt()` nếu không tiếp tục ném nguyên exception. Không nuốt interrupt rồi tiếp tục xử lý như thể request hoàn tất bình thường.

Status error được chuyển thành `RemoteServiceException` ở helper trước đó; nó khác với lỗi transport. Hai nhóm nên được xử lý riêng để tránh retry sai.

## 7. Gửi POST JSON và xử lý response

Để gửi request body, dùng `HttpRequest.BodyPublishers`. Ví dụ gửi JSON:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class PostServiceExample {

    private static final HttpClient CLIENT =
            HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

    public static void main(String[] args)
            throws Exception {

        String json = """
                {
                    "name": "Lan",
                    "role": "developer"
                }
                """;

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/v1/users"))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json; charset=UTF-8")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        json,
                        StandardCharsets.UTF_8
                ))
                .build();

        HttpResponse<String> response = CLIENT.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        if (response.statusCode() < 200
                || response.statusCode() >= 300) {
            throw new RemoteServiceException(
                    response.statusCode(),
                    response.body()
            );
        }

        System.out.println("HTTP version: " + response.version());
        System.out.println(response.body());
    }
}
```

Header `Content-Type` mô tả định dạng request body; `Accept` mô tả loại response ứng dụng mong muốn. `ofString(json, UTF_8)` tạo body theo UTF-8.

Text block giúp viết JSON nhiều dòng dễ đọc, nhưng không tự serialize hoặc validate object. Với dữ liệu động, dùng thư viện JSON tương thích để serialize object thay vì nối chuỗi thủ công.

### 7.1. Body publisher khác

| Publisher | Công dụng |
| --- | --- |
| `BodyPublishers.ofString` | Gửi text hoặc JSON. |
| `BodyPublishers.ofByteArray` | Gửi dữ liệu nhị phân có sẵn trong bộ nhớ. |
| `BodyPublishers.ofFile` | Gửi nội dung từ file. |
| `BodyPublishers.noBody` | Request không có body. |
| `BodyPublishers.fromPublisher` | Dùng Flow publisher để cung cấp body theo luồng. |

Ví dụ gửi file:

```java
import java.nio.file.Path;

HttpRequest upload = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/v1/files"))
        .timeout(Duration.ofMinutes(2))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofFile(Path.of("report.bin")))
        .build();
```

Đặt timeout theo kích thước file và SLA upload. Không tải toàn bộ file vào byte array nếu file lớn và không cần thiết.

## 8. Chọn BodyHandler phù hợp

Response body có thể là văn bản, byte array, file hoặc stream.

| BodyHandler | Kiểu body | Khi phù hợp |
| --- | --- | --- |
| `ofString(UTF_8)` | `String` | JSON/text có kích thước vừa phải. |
| `ofByteArray()` | `byte[]` | Payload nhị phân nhỏ cần xử lý trong bộ nhớ. |
| `ofFile(path)` | `Path` | Tải file xuống đĩa. |
| `ofInputStream()` | `InputStream` | Xử lý stream và tự quản lý việc đọc/đóng. |
| `discarding()` | `Void` | Không cần body. |

Ví dụ tải file:

```java
import java.nio.file.Path;

HttpResponse<Path> response = CLIENT.send(
        request,
        HttpResponse.BodyHandlers.ofFile(Path.of("download.bin"))
);

if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    System.out.println("Saved: " + response.body());
} else {
    throw new RemoteServiceException(
            response.statusCode(),
            "File download failed"
    );
}
```

Nếu tải file trực tiếp vào đường dẫn đích, hãy kiểm tra status và xử lý file không hợp lệ khi server trả lỗi. Với yêu cầu an toàn cao, có thể tải vào file tạm, xác minh status/content/checksum rồi mới chuyển sang vị trí cuối cùng.

Với `ofInputStream()`, ứng dụng phải đóng stream sau khi đọc xong:

```java
HttpResponse<java.io.InputStream> response = CLIENT.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream()
);

try (java.io.InputStream input = response.body()) {
    byte[] firstChunk = input.readNBytes(4096);
    System.out.println("Read: " + firstChunk.length);
}
```

Ví dụ chỉ đọc tối đa 4096 byte đầu tiên. Code thực tế cần lặp đến EOF hoặc chuyển stream sang nơi xử lý phù hợp. Đóng stream giúp giải phóng tài nguyên liên quan.

## 9. Redirect và HTTPS

Mặc định, `HttpClient` không tự động theo redirect. Có thể cấu hình:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

Các chính sách:

| Giá trị | Hành vi |
| --- | --- |
| `Redirect.NEVER` | Không tự động theo redirect; đây là mặc định. |
| `Redirect.NORMAL` | Theo redirect, ngoại trừ chuyển từ HTTPS xuống HTTP. |
| `Redirect.ALWAYS` | Theo cả redirect từ HTTPS xuống HTTP. |

Với request chứa token hoặc dữ liệu nhạy cảm, cần thận trọng khi theo redirect vì đích mới có thể khác host hoặc scheme. Tránh cho phép hạ từ HTTPS xuống HTTP khi truyền thông tin xác thực.

Có thể xem response trước đó qua `previousResponse()` khi client theo một chuỗi redirect.

## 10. Gọi HTTP bất đồng bộ bằng sendAsync()

`send()` chặn thread hiện tại trong lúc chờ. `sendAsync()` trả về `CompletableFuture<HttpResponse<T>>` để ứng dụng tiếp tục công việc khác.

Ví dụ:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class AsyncHttpExample {

    private static final HttpClient CLIENT =
            HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

    static CompletableFuture<String> getUser() {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/v1/users/42"))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        return CLIENT.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8
                        )
                )
                .thenApply(response -> {
                    if (response.statusCode() < 200
                            || response.statusCode() >= 300) {
                        throw new java.util.concurrent.CompletionException(
                                new RemoteServiceException(
                                        response.statusCode(),
                                        response.body()
                                )
                        );
                    }

                    return response.body();
                });
    }

    public static void main(String[] args) {
        getUser()
                .thenAccept(body -> System.out.println(body))
                .exceptionally(error -> {
                    System.err.println("Request failed: " + error);
                    return null;
                });
    }
}
```

`sendAsync` bắt đầu request và trả future. `thenApply` kiểm tra status, sau đó chuyển response thành body. Nếu status không thành công, code hoàn tất future theo hướng exceptional với `RemoteServiceException` được bọc trong `CompletionException`.

Khi xử lý lỗi bất đồng bộ, cần xem nguyên nhân bên trong `CompletionException` hoặc `ExecutionException` tùy cách chờ future. Không nên chỉ ghi một chuỗi exception rồi bỏ mất root cause.

### 10.1. Kết hợp nhiều request

Có thể gửi nhiều request độc lập và đợi tất cả hoàn tất:

```java
CompletableFuture<HttpResponse<String>> first =
        CLIENT.sendAsync(request1, HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<String>> second =
        CLIENT.sendAsync(request2, HttpResponse.BodyHandlers.ofString());

CompletableFuture<Void> all =
        CompletableFuture.allOf(first, second);

all.thenRun(() -> {
    System.out.println(first.join().statusCode());
    System.out.println(second.join().statusCode());
});
```

Các request được khởi chạy bất đồng bộ. `allOf` hoàn tất khi tất cả future hoàn tất; nếu một future thất bại, future tổng hợp cũng hoàn tất bất thường. Trong callback của `all`, các future con đã hoàn tất nên có thể lấy kết quả bằng `join()`.

HTTP/2 multiplexing và `sendAsync` là hai khái niệm riêng:

- HTTP/2 là phiên bản giao thức, có multiplexing nhiều stream trên một kết nối.
- `sendAsync` là API bất đồng bộ, cho phép caller không phải chờ trực tiếp trong thread hiện tại.

Có thể dùng `sendAsync` với HTTP/1.1 hoặc `send` với client ưu tiên HTTP/2.

## 11. Xử lý lỗi trong CompletableFuture

Khi `sendAsync` gặp lỗi, future hoàn tất bất thường. Các lỗi thường được bọc trong `CompletionException` khi xử lý qua stage hoặc lấy kết quả.

Ví dụ tách nguyên nhân:

```java
import java.util.concurrent.CompletionException;

static Throwable unwrap(Throwable error) {
    if (error instanceof CompletionException
            && error.getCause() != null) {
        return error.getCause();
    }

    return error;
}
```

Dùng:

```java
getUser().whenComplete((body, error) -> {
    if (error == null) {
        System.out.println("Success: " + body);
        return;
    }

    Throwable cause = unwrap(error);

    if (cause instanceof java.net.http.HttpTimeoutException) {
        System.err.println("Request timed out");
    } else if (cause instanceof RemoteServiceException remote) {
        System.err.println(
                "HTTP status: " + remote.statusCode()
        );
    } else {
        System.err.println("Transport/processing error: " + cause);
    }
});
```

Không phải mọi lỗi trong future đều là lỗi mạng. Một callback như JSON parsing hoặc mapping response cũng có thể ném exception. Hãy phân biệt lỗi transport, HTTP status và lỗi xử lý dữ liệu trong ứng dụng.

Request timeout vẫn nên được đặt trong `HttpRequest`. Đừng dựa hoàn toàn vào việc chờ future hoặc tự đặt timeout ở callback mà không quản lý request đang chạy.

## 12. Phân loại lỗi để quyết định hành động

Một thiết kế tốt tách lỗi thành các nhóm:

### 12.1. Lỗi cấu hình hoặc request

Ví dụ URI sai, header không hợp lệ hoặc request builder nhận tham số không hợp lệ. Những lỗi này thường cần sửa code/cấu hình; retry không giúp ích.

### 12.2. Lỗi transport

Ví dụ DNS failure, connection refused, connection reset, TLS handshake failure hoặc timeout. Một số lỗi có thể tạm thời, nhưng cần xem loại lỗi và tính an toàn của thao tác trước khi retry.

### 12.3. HTTP response lỗi

Server đã trả response nhưng status nằm ngoài nhóm thành công. Dựa vào status và API contract để quyết định sửa request, xác thực lại, chờ rate limit hoặc báo lỗi.

### 12.4. Lỗi parse/validation

Response có thể là 200 nhưng body sai schema, thiếu trường hoặc chứa giá trị không hợp lệ. Đây là lỗi xử lý dữ liệu, không phải lỗi kết nối. Không retry vô hạn một response sai định dạng.

Bảng gợi ý:

| Nhóm | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Request/configuration | URI/header không hợp lệ | Sửa đầu vào/cấu hình. |
| Authentication | 401 | Làm mới credential/token theo cơ chế bảo mật; thử lại có giới hạn nếu phù hợp. |
| Authorization | 403 | Kiểm tra quyền; không retry mù. |
| Business/client error | 400, 404, 409, 422 | Trả lỗi nghiệp vụ hoặc sửa request. |
| Rate limit | 429 | Xem `Retry-After` và backoff. |
| Transient service error | 502, 503, 504 | Có thể retry nếu thao tác an toàn và còn deadline. |
| Network/timeout | IOException, HttpTimeoutException | Đánh giá tính idempotent, retry policy và trạng thái request. |
| Response processing | JSON parse/validation failure | Điều tra contract/schema; thường không retry ngay. |

## 13. Retry có giới hạn và an toàn

Retry có thể giúp vượt qua lỗi tạm thời, nhưng retry sai cách có thể làm hệ thống quá tải hoặc thực hiện một thao tác nhiều lần.

### 13.1. Chỉ retry thao tác an toàn

Các method có semantics idempotent theo HTTP thường phù hợp hơn để retry, nếu API thực tế tuân thủ contract:

- GET: đọc dữ liệu.
- PUT: đặt trạng thái tài nguyên theo representation được gửi.
- DELETE: yêu cầu xóa tài nguyên.
- HEAD/OPTIONS: truy vấn metadata/capability.

POST thường không idempotent. Nếu server đã xử lý POST nhưng response bị mất, retry có thể tạo đơn hàng hoặc giao dịch lần thứ hai. Chỉ retry POST khi API có cơ chế idempotency key/deduplication được server hỗ trợ và client dùng đúng contract.

Đừng chỉ dựa vào tên method. Một API có thể triển khai semantics khác với kỳ vọng của HTTP; hãy xác nhận hành vi nghiệp vụ.

### 13.2. Dùng bounded exponential backoff

Một retry policy thường có:

1. Số lần thử tối đa.
2. Backoff tăng dần giữa các lần thử.
3. Jitter để nhiều client không retry đồng loạt.
4. Deadline tổng thể.
5. Danh sách lỗi/status có thể retry.
6. Điều kiện idempotency.
7. Tôn trọng `Retry-After` khi server cung cấp.

Ví dụ quy tắc:

| Lần thử | Backoff cơ sở minh họa |
| --- | ---: |
| Lần 1 | Không chờ |
| Lần 2 | 200 ms |
| Lần 3 | 400 ms |
| Lần 4 | 800 ms |

Thời gian thực tế nên thêm jitter và giới hạn tối đa. Không dùng bảng trên như thông số mặc định cho mọi hệ thống.

### 13.3. Status có thể cân nhắc retry

- 429: tuân thủ rate limit và `Retry-After` nếu có.
- 502/503/504: có thể là lỗi tạm thời của gateway/service.
- 408: có thể retry tùy contract và trạng thái request.
- Một số lỗi transport: có thể retry nếu request idempotent và còn deadline.

Không mặc định retry tất cả 5xx. Ví dụ 500 có thể là lỗi logic ổn định; retry liên tục chỉ tăng tải. 4xx thường cần sửa request hoặc quyền, không phải retry tự động.

### 13.4. Retry-After

Header `Retry-After` có thể chỉ số giây cần chờ hoặc thời điểm HTTP-date. Nếu server gửi header này, client nên tôn trọng theo API/rate-limit policy, đồng thời vẫn áp dụng giới hạn thời gian tối đa và deadline của ứng dụng.

Không retry sớm hơn thời gian server yêu cầu chỉ vì backoff nội bộ ngắn hơn.

### 13.5. Tránh retry storm

Nếu nhiều instance đồng loạt retry khi service quá tải, lượng request có thể tăng mạnh và làm sự cố nghiêm trọng hơn. Dùng bounded retries, jitter, circuit breaker/bulkhead ở tầng kiến trúc khi phù hợp và giới hạn concurrency. Không tạo vòng lặp retry không giới hạn trong callback hoặc executor.

## 14. Redirect, authentication và header nhạy cảm

Request có thể mang header như `Authorization`, API key hoặc cookie. Khi cấu hình redirect, cần hiểu header nào được chuyển tiếp và đích redirect có thể khác host hay không.

Nguyên tắc:

- Chỉ gửi credential tới host và scheme được tin cậy.
- Tránh redirect từ HTTPS xuống HTTP.
- Không ghi token/API key vào log.
- Không đặt secret trực tiếp trong source code.
- Dùng secret manager hoặc cơ chế cấu hình bảo mật.
- Kiểm tra response trước khi dùng dữ liệu trả về.

Ví dụ đặt bearer token:

```java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/v1/profile"))
        .timeout(Duration.ofSeconds(5))
        .header("Authorization", "Bearer " + accessToken)
        .header("Accept", "application/json")
        .GET()
        .build();
```

`accessToken` cần được lấy từ nguồn bảo mật và không được ghi vào log hoặc exception message. Khi token hết hạn, refresh theo giao thức authentication; không retry liên tục với token cũ.

## 15. TLS và lỗi certificate

Với URI HTTPS, `HttpClient` sử dụng cấu hình SSL/TLS mặc định của JDK nếu không cung cấp cấu hình riêng. Lỗi handshake có thể đến từ:

- Certificate hết hạn hoặc chain không được trust.
- Hostname không khớp certificate.
- Server chỉ hỗ trợ protocol/cipher không tương thích với policy client.
- Trust store không có CA cần thiết.
- Proxy hoặc TLS inspection thay đổi certificate chain.
- Mutual TLS yêu cầu client certificate nhưng client chưa cấu hình.

Không tắt kiểm tra certificate hoặc chấp nhận mọi hostname để “sửa nhanh”. Cần xác minh certificate chain, hostname, trust store và cấu hình server.

Trong production, không log private key hoặc credential. Khi chẩn đoán, lưu exception và thông tin endpoint/certificate cần thiết theo chính sách bảo mật.

## 16. Giới hạn body và xử lý dữ liệu lớn

`BodyHandlers.ofString()` và `ofByteArray()` đọc toàn bộ body vào bộ nhớ. Điều này tiện với response nhỏ, nhưng có thể gây áp lực heap khi response rất lớn hoặc nhiều request đồng thời.

Với dữ liệu lớn:

- Dùng `BodyHandlers.ofFile(path)` để lưu file.
- Dùng `ofInputStream()` và đọc theo buffer khi cần stream processing.
- Đặt giới hạn kích thước ở tầng ứng dụng hoặc gateway.
- Kiểm tra `Content-Length` nếu có, nhưng không coi header đó là bảo đảm duy nhất.
- Kiểm tra Content-Type và validate nội dung.
- Đóng stream/file resource đúng cách.

Nếu API trả dữ liệu JSON rất lớn, cân nhắc streaming parser thay vì parse toàn bộ thành một chuỗi trong heap.

## 17. Ví dụ tổng hợp: client đồng bộ có timeout và phân loại lỗi

Ví dụ dưới đây tái sử dụng client, ưu tiên HTTP/2, đặt connect/request timeout, kiểm tra status và giữ nguyên interrupt:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class UserApiClient {

    private final HttpClient client;

    public UserApiClient() {
        this.client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    public String getUser(String userId) {
        URI uri = URI.create(
                "https://api.example.com/v1/users/" + userId
        );

        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri)
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        try {
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8
                    )
            );

            if (response.statusCode() < 200
                    || response.statusCode() >= 300) {
                throw new RemoteServiceException(
                        response.statusCode(),
                        response.body()
                );
            }

            System.out.println("HTTP version: " + response.version());
            return response.body();

        } catch (HttpTimeoutException ex) {
            throw new IllegalStateException(
                    "User service timed out",
                    ex
            );

        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "User request was interrupted",
                    ex
            );

        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Cannot communicate with user service",
                    ex
            );
        }
    }
}
```

Lớp `RemoteServiceException` là exception được định nghĩa ở phần trước. Trong code production, cần validate `userId` trước khi ghép vào URI hoặc dùng URI builder để encode path segment phù hợp. Ví dụ tập trung vào cách gọi và xử lý response.

## 18. Ví dụ tổng hợp: gọi bất đồng bộ với HTTP/2

Một API service có thể trả `CompletableFuture` cho tầng gọi:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public final class AsyncUserApiClient {

    private final HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_2)
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    public CompletableFuture<String> getUser(String userId) {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(
                        "https://api.example.com/v1/users/" + userId
                ))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        return client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8
                        )
                )
                .thenApply(response -> {
                    if (response.statusCode() < 200
                            || response.statusCode() >= 300) {
                        throw new CompletionException(
                                new RemoteServiceException(
                                        response.statusCode(),
                                        response.body()
                                )
                        );
                    }

                    return response.body();
                });
    }
}
```

Caller quyết định cách kết hợp future với workflow:

```java
client.getUser("42")
        .thenAccept(body -> processUserJson(body))
        .exceptionally(error -> {
            Throwable cause = error instanceof CompletionException
                    && error.getCause() != null
                    ? error.getCause()
                    : error;

            logRequestFailure(cause);
            return null;
        });
```

Tên `processUserJson` và `logRequestFailure` là các hàm ứng dụng minh họa. Tránh block bằng `join()` ngay sau `sendAsync()` nếu mục tiêu là xử lý bất đồng bộ.

## 19. Checklist vận hành cho HTTP/2 client

Trước khi đưa client vào production, xác nhận:

- Client được tái sử dụng, không tạo mới cho từng request.
- Phiên bản HTTP ưu tiên được cấu hình phù hợp.
- Có kiểm tra `response.version()` khi cần xác nhận HTTP/2.
- Server, proxy và load balancer hỗ trợ HTTP/2/ALPN theo kiến trúc thực tế.
- Connect timeout và request timeout được đặt theo SLA.
- Status code được kiểm tra rõ ràng.
- Transport exception và HTTP status error được phân loại riêng.
- InterruptedException được xử lý đúng.
- Retry có giới hạn, backoff/jitter và điều kiện idempotency.
- `Retry-After` được xem xét với rate limiting.
- Redirect không làm lộ credential hoặc hạ HTTPS xuống HTTP.
- TLS certificate/hostname được xác thực.
- Body handler phù hợp với kích thước dữ liệu.
- Stream được đóng sau khi xử lý.
- Log không chứa token, secret hoặc body nhạy cảm.
- Metrics có latency, status, timeout, retry và error rate.

## 20. Những lỗi thường gặp

| Vấn đề | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Cấu hình HTTP/2 nhưng response là HTTP/1.1 | Server/proxy không thương lượng HTTP/2 hoặc kết nối fallback. | Kiểm tra `response.version()`, TLS/ALPN và hạ tầng. |
| Request chờ quá lâu | Thiếu request timeout hoặc timeout quá rộng. | Đặt `HttpRequest.timeout` theo SLA. |
| Không kết nối được host | DNS, route, firewall hoặc port. | Kiểm tra endpoint và network path. |
| TLS handshake thất bại | Certificate, hostname, truststore hoặc protocol/cipher. | Sửa trust/certificate/server config; không tắt xác thực. |
| HTTP 404 nhưng không có IOException | HTTP status là response hợp lệ ở tầng transport. | Kiểm tra `statusCode()`. |
| Retry làm tạo hai giao dịch | POST không idempotent hoặc server đã xử lý lần đầu. | Dùng idempotency key/deduplication hoặc không retry. |
| Async error khó đọc | Exception bị bọc trong CompletionException. | Unwrap cause và phân loại root cause. |
| CPU/heap tăng khi tải file | Đọc toàn bộ body vào String/byte array. | Dùng file/stream handler và giới hạn kích thước. |
| Token xuất hiện ở endpoint redirect khác | Redirect policy và credential handling không phù hợp. | Giới hạn redirect và bảo vệ credential. |
| Nhiều request timeout cùng lúc | Service quá tải, connection pool/network hoặc deadline quá ngắn. | Đối chiếu metrics, server load, retry và concurrency. |

## 21. Bài thực hành

### Bài 1 — gọi GET với HTTP/2 preference

Tạo client ưu tiên `HTTP_2`, gửi GET đến HTTPS endpoint hỗ trợ HTTP/2. In status, body và `response.version()`. Thử một endpoint chỉ hỗ trợ HTTP/1.1 để quan sát kết quả thực tế.

### Bài 2 — phân biệt hai timeout

Đặt connect timeout 2 giây và request timeout 5 giây. Dùng endpoint thử nghiệm không phản hồi hoặc không thể kết nối. Ghi exception và giải thích timeout nào được kích hoạt.

### Bài 3 — xử lý status code

Gọi endpoint trả 200, 404, 429 và 503. Viết hàm phân loại response. Đảm bảo status error được xử lý dù `send()` không ném IOException chỉ vì status đó.

### Bài 4 — POST JSON

Tạo request POST dùng `BodyPublishers.ofString` với UTF-8. Đặt Content-Type và Accept đúng. Kiểm tra response body và status code.

### Bài 5 — bất đồng bộ

Dùng `sendAsync`, `thenApply` và `exceptionally`. Phân biệt lỗi HTTP status với lỗi transport. Không gọi `join()` ngay sau khi gửi request.

### Bài 6 — retry an toàn

Tạo một GET request tới endpoint có thể trả 503 tạm thời. Viết retry tối đa ba lần với exponential backoff và jitter. Không retry 400/401/403/404 một cách mù quáng.

### Bài 7 — POST và idempotency

Thử mô phỏng POST tạo tài nguyên. Giải thích tình huống server đã xử lý nhưng response bị mất. Thiết kế idempotency key theo contract API để retry không tạo tài nguyên trùng.

### Bài 8 — tải file

Dùng `BodyHandlers.ofFile` hoặc `ofInputStream` để tải file lớn. Kiểm tra status, kích thước và checksum; đảm bảo đóng stream và xử lý file tạm khi thất bại.

### Bài 9 — redirect và TLS

Tạo client với `Redirect.NEVER` và `Redirect.NORMAL`. So sánh response khi endpoint redirect. Kiểm tra certificate/hostname và bảo đảm credential không bị gửi tới đích không tin cậy.

## 22. Ghi nhớ nhanh

| Nhu cầu | API |
| --- | --- |
| Tạo client ưu tiên HTTP/2 | `HttpClient.newBuilder().version(HttpClient.Version.HTTP_2)` |
| Timeout kết nối | `HttpClient.Builder.connectTimeout(Duration)` |
| Timeout request | `HttpRequest.Builder.timeout(Duration)` |
| Gửi đồng bộ | `client.send(request, bodyHandler)` |
| Gửi bất đồng bộ | `client.sendAsync(request, bodyHandler)` |
| Tạo GET | `HttpRequest.Builder.GET()` |
| Tạo POST JSON | `POST(BodyPublishers.ofString(json, UTF_8))` |
| Kiểm tra status | `response.statusCode()` |
| Kiểm tra HTTP thực tế | `response.version()` |
| Đọc response text | `BodyHandlers.ofString(UTF_8)` |
| Tải file | `BodyHandlers.ofFile(path)` |
| Đọc stream | `BodyHandlers.ofInputStream()` |
| Theo redirect | `followRedirects(Redirect.NORMAL)` |
| Lấy response header | `response.headers()` |
| Xử lý timeout | `HttpTimeoutException` |
| Giữ interrupt | `Thread.currentThread().interrupt()` |
| Lỗi async | `CompletionException.getCause()` |

**Nguyên tắc cốt lõi:** Dùng một `HttpClient` tái sử dụng và ưu tiên HTTP/2; xác nhận giao thức thực tế bằng `response.version()`. Đặt connect timeout ở client và request timeout cho từng request. Kiểm tra status code vì HTTP 4xx/5xx không tự trở thành exception; phân loại riêng lỗi transport, timeout và lỗi nghiệp vụ. Chỉ retry có giới hạn khi thao tác an toàn, tôn trọng `Retry-After` và deadline, đồng thời bảo vệ TLS, credential và response body.
