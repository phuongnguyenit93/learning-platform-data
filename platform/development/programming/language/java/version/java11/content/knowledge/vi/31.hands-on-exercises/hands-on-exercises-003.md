# Thực hành Java 11: HTTP client tái sử dụng với timeout và xử lý response có kiểu

## Mục tiêu và tình huống

Bạn đang xây dựng một ứng dụng Java thường xuyên gọi REST API. Mỗi lời gọi cần giới hạn thời gian chờ, trả về dữ liệu đúng kiểu Java, phân biệt lỗi HTTP với lỗi mạng, và dùng chung cấu hình kết nối. Bài này thực hành với API chuẩn `java.net.http` có từ Java 11, vẫn dùng tốt trong các phiên bản Java hiện hành.

Sau bài học, bạn có thể:

- Tạo **một `HttpClient` dùng chung**, thay vì khởi tạo lại cho từng yêu cầu; tạo `HttpRequest` riêng cho từng lần gọi.
- Đặt **connect timeout** trên client và **request timeout** trên request, hiểu trường hợp mỗi timeout phát huy tác dụng.
- Dùng `HttpResponse<T>`, `BodyHandler<T>` và `BodySubscribers.mapping(...)` để chuyển body thành đối tượng có kiểu, đồng thời giữ được mã trạng thái và thông tin lỗi.
- Xử lý `200`, `404`, timeout, ngoại lệ I/O và luồng bất đồng bộ; thay bộ giải mã ví dụ bằng giải mã JSON khi làm việc với REST API thực tế.

## 1. Phân biệt client, request, response

| Thành phần | Vai trò | Vòng đời nên dùng |
| --- | --- | --- |
| `HttpClient` | Quản lý cấu hình chung: kết nối, TLS, proxy, redirect, HTTP/1.1 hoặc HTTP/2; có thể tái sử dụng kết nối | Tạo một lần cho một nhóm cấu hình rồi chia sẻ giữa nhiều lời gọi |
| `HttpRequest` | URI, method, header, body, timeout của **một yêu cầu** | Tạo riêng cho từng thao tác; đối tượng sau `build()` là immutable |
| `HttpResponse<T>` | Status, headers, URI, protocol và body kiểu `T` | Nhận theo từng lần `send` / `sendAsync` |
| `BodyHandler<T>` | Chọn cách tiêu thụ/chuyển đổi body khi đã có status và headers | Xác định theo kiểu dữ liệu mong đợi và quy tắc API |

`HttpClient` bất biến sau `build()` và dùng được đồng thời từ nhiều luồng. Một instance thường quản lý pool kết nối riêng, nên tạo client mới cho mỗi request làm giảm cơ hội tái sử dụng kết nối. Hãy lưu client trong service sống lâu hoặc truyền qua constructor (dependency injection). Không chia sẻ một `HttpRequest.Builder` đang bị sửa giữa các luồng.

Trong dự án nhắm Java 11, **không viết `try (HttpClient client = ...)`**: các phương thức quản lý vòng đời như `close()` của `HttpClient` được bổ sung ở JDK mới hơn, không thuộc API Java 11. Ví dụ dưới đây biên dịch với `--release 11`.

## 2. Hai timeout khác nhau

| Cấu hình | Đặt ở đâu? | Tác dụng |
| --- | --- | --- |
| `HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1))` | Client | Giới hạn việc thiết lập **kết nối mới**. Nếu có kết nối đã tái sử dụng, thiết lập này không phải bộ hẹn giờ cho request đó. Quá hạn có thể phát sinh `HttpConnectTimeoutException`. |
| `HttpRequest.newBuilder(uri).timeout(Duration.ofMillis(250))` | Mỗi request | Giới hạn thời gian thực thi yêu cầu. Nếu hết hạn, `send` ném `HttpTimeoutException`; `sendAsync` hoàn thành lỗi. Không đặt timeout này có thể khiến thao tác chờ rất lâu. |

Các giá trị phải là `Duration` dương. Request timeout **không đồng nghĩa với một cấu hình “read timeout” riêng cho mỗi gói dữ liệu**. Hợp đồng API bảo đảm giới hạn đến khi có response; triển khai HTTP Client trong JDK còn áp dụng nó qua quá trình tiêu thụ response body đối với các body subscriber tích lũy dữ liệu. Khi stream body rất lớn hoặc theo dõi dài hạn, cần thiết kế giới hạn thời gian và đóng/cancel luồng riêng.

`HttpConnectTimeoutException` là một dạng của `HttpTimeoutException`: khi cần xử lý khác nhau, bắt ngoại lệ kết nối trước ngoại lệ timeout tổng quát.

## 3. Chương trình hoàn chỉnh, chạy offline trên Java 11+

Để kết quả tái hiện được mà không phụ thuộc Internet hay token, chương trình tự mở một HTTP server nhỏ trên `127.0.0.1`. Endpoint mô phỏng trả dữ liệu dạng `text/plain` có ba trường `id|name|active`. Đây **chỉ là định dạng bài tập** để thấy rõ cơ chế chuyển từ chuỗi sang `Profile`, không phải kỹ thuật phân tích JSON. Mục 5 hướng dẫn thay bằng JSON cho API thật.

Tạo file **`HttpClientPractice.java`**:

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
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.function.Function;

public class HttpClientPractice {
    static final class Profile {
        final int id;
        final String name;
        final boolean active;

        Profile(int id, String name, boolean active) {
            this.id = id;
            this.name = name;
            this.active = active;
        }

        static Profile parse(String text) {
            String[] parts = text.split("\\|", -1);
            if (parts.length != 3 ||
                    (!parts[2].equals("true") && !parts[2].equals("false"))) {
                throw new IllegalArgumentException("Invalid profile payload");
            }
            return new Profile(Integer.parseInt(parts[0]), parts[1],
                    Boolean.parseBoolean(parts[2]));
        }
    }

    static final class ApiResult<T> {
        final T data;
        final String errorText;

        private ApiResult(T data, String errorText) {
            this.data = data;
            this.errorText = errorText;
        }

        static <T> ApiResult<T> success(T value) {
            return new ApiResult<>(value, null);
        }

        static <T> ApiResult<T> failure(String errorText) {
            return new ApiResult<>(null, errorText);
        }
    }

    static final class ApiClient {
        private final HttpClient httpClient;
        private final Duration requestTimeout;

        ApiClient(Duration connectTimeout, Duration requestTimeout) {
            this.httpClient = HttpClient.newBuilder()
                    .connectTimeout(connectTimeout)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();
            this.requestTimeout = requestTimeout;
        }

        private HttpRequest request(URI uri) {
            return HttpRequest.newBuilder(uri)
                    .timeout(requestTimeout)
                    .header("Accept", "text/plain")
                    .GET()
                    .build();
        }

        private static <T> HttpResponse.BodyHandler<ApiResult<T>> handler(
                Function<String, T> decoder) {
            return info -> HttpResponse.BodySubscribers.mapping(
                    HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8),
                    raw -> info.statusCode() == 200
                            ? ApiResult.success(decoder.apply(raw))
                            : ApiResult.failure(raw));
        }

        <T> HttpResponse<ApiResult<T>> get(URI uri, Function<String, T> decoder)
                throws IOException, InterruptedException {
            return httpClient.send(request(uri), handler(decoder));
        }

        <T> CompletableFuture<HttpResponse<ApiResult<T>>> getAsync(
                URI uri, Function<String, T> decoder) {
            return httpClient.sendAsync(request(uri), handler(decoder));
        }
    }

    private static void reply(HttpExchange exchange, int code, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/users/42", ex -> reply(ex, 200, "42|Linh|true"));
        server.createContext("/users/0", ex -> reply(ex, 404, "user not found"));
        server.createContext("/slow", ex -> {
            try {
                Thread.sleep(800);
                reply(ex, 200, "99|Slow|true");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (IOException e) {
                // Client may have closed the timed-out connection.
            }
        });
        server.start();

        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            ApiClient api = new ApiClient(Duration.ofSeconds(1), Duration.ofMillis(250));

            HttpResponse<ApiResult<Profile>> ok =
                    api.get(URI.create(base + "/users/42"), Profile::parse);
            System.out.println("OK " + ok.statusCode() + " -> "
                    + ok.body().data.id + " / " + ok.body().data.name);

            HttpResponse<ApiResult<Profile>> missing =
                    api.get(URI.create(base + "/users/0"), Profile::parse);
            System.out.println("ERROR " + missing.statusCode() + " -> "
                    + missing.body().errorText);

            HttpResponse<ApiResult<Profile>> async =
                    api.getAsync(URI.create(base + "/users/42"), Profile::parse).join();
            System.out.println("ASYNC " + async.statusCode() + " -> "
                    + async.body().data.active);

            try {
                api.get(URI.create(base + "/slow"), Profile::parse);
            } catch (HttpTimeoutException timeout) {
                System.out.println("TIMEOUT request");
            }
        } finally {
            server.stop(1);
        }
    }
}
```

Chạy từ thư mục chứa file, với JDK 11 trở lên:

```bash
javac --release 11 --add-modules jdk.httpserver HttpClientPractice.java
java --add-modules jdk.httpserver HttpClientPractice
```

Kết quả kiểm chứng khi chạy chương trình trên JDK 24 với chế độ biên dịch Java 11:

```text
OK 200 -> 42 / Linh
ERROR 404 -> user not found
ASYNC 200 -> true
TIMEOUT request
```

`jdk.httpserver` chỉ dùng để mô phỏng server tại máy, không phải phần bắt buộc của ứng dụng client gọi một REST API ngoài. Trong ứng dụng thật, hãy thay URI loopback bằng endpoint tin cậy qua HTTPS.

## 4. Đọc dòng xử lý và phân loại kết quả

1. `new ApiClient(...)` tạo đúng **một** `HttpClient` rồi giữ trong field `httpClient`; các lần `get` / `getAsync` đều gửi qua instance đó.
2. `request(uri)` tạo `HttpRequest` mới, áp dụng timeout 250 ms và header `Accept`. Mỗi request độc lập nên có thể có URI, timeout, token khác nhau.
3. `handler(decoder)` nhận `ResponseInfo`, sau đó `BodySubscribers.ofString(UTF_8)` gom body và `mapping` chuyển chuỗi thành **`ApiResult<T>`**. Vì vậy kiểu trả về là **`HttpResponse<ApiResult<Profile>>`**, được trình biên dịch kiểm tra kiểu.
4. Chỉ status **`200`** mới được giải mã thành `Profile`. Status `404` giữ nguyên chuỗi lỗi trong `errorText`. Việc chọn `200` là hợp đồng riêng của endpoint minh họa; API khác có thể chấp nhận `201`, `204` hoặc mọi `2xx`, nhưng `204` không có body để parse.
5. Lệnh `statusCode()` vẫn cung cấp trạng thái HTTP riêng biệt với dữ liệu đã giải mã. Đừng truy cập `body().data` trước khi xác nhận kết quả là thành công.
6. `sendAsync` trả `CompletableFuture`. `join()` trong demo chỉ để in kết quả xác định; trong chương trình non-blocking, nên tiếp tục xử lý bằng `thenApply` / `thenCompose` / `exceptionally` hoặc `whenComplete`.

**Phân biệt ba nhóm lỗi:**

- **HTTP 4xx/5xx:** server đã trả một response hợp lệ. `send` / `sendAsync` không tự biến status này thành Java exception. Đọc `statusCode()` và body lỗi, sau đó quyết định phản hồi nghiệp vụ, chẳng hạn 404 không tìm thấy, 401 cần xác thực lại, 429 cần xét `Retry-After`.
- **I/O hoặc timeout:** chưa có response hoàn chỉnh theo yêu cầu; `send` có thể ném `IOException`, `HttpTimeoutException` hoặc `HttpConnectTimeoutException`. `InterruptedException` cần được truyền tiếp hoặc khôi phục interrupt flag nếu đã bắt để xử lý.
- **Sai định dạng response:** `Profile.parse` có thể ném `IllegalArgumentException` / `NumberFormatException`. Nếu lỗi phát sinh trong `BodySubscribers.mapping`, quá trình hoàn thành body có thể thất bại; với `sendAsync`, future hoàn thành exceptional. Đó là lỗi dữ liệu, không nên báo thành 404 hay timeout.

Một mẫu xử lý exception bên ngoài `ApiClient` (không nuốt interrupt):

```java
try {
    HttpResponse<ApiResult<Profile>> response = api.get(uri, Profile::parse);
    if (response.statusCode() == 200) {
        Profile profile = response.body().data;
        // Dùng profile; dữ liệu đã có kiểu.
    } else {
        // Ghi nhận status và mã lỗi nghiệp vụ; tránh log token/bí mật.
        String error = response.body().errorText;
    }
} catch (java.net.http.HttpConnectTimeoutException e) {
    // Thiết lập kết nối mới quá thời gian.
} catch (java.net.http.HttpTimeoutException e) {
    // Request quá thời gian.
} catch (IOException e) {
    // DNS, TLS, socket hoặc lỗi đọc/ghi khác.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Dừng công việc hoặc truyền lỗi cho tầng gọi.
}
```

Đoạn trên là **mã đặt trong một method có `api` và `uri` đã khởi tạo**, không phải file Java độc lập. Tùy hợp đồng API, xử lý `errorText` và lỗi parse bằng kiểu lỗi/domain error cụ thể hơn.

## 5. Khi REST API trả JSON: giải mã sang DTO có kiểu

Java 11 có `HttpClient` nhưng **không cung cấp sẵn JSON object mapper tổng quát**. Với REST JSON, có thể dùng Jackson Databind 2.x đang được duy trì và tương thích Java 11. Ví dụ dependency Maven sau sử dụng nhánh Jackson 2.21 LTS, bản vá 2.21.8 (phát hành tháng 10/2026); nếu dự án có BOM quản lý Jackson, ưu tiên để BOM chọn **các module cùng phiên bản**.

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.21.8</version>
</dependency>
```

Model cho ví dụ JSON `{"id":42,"name":"Linh","active":true}` (file **`UserDto.java`**):

```java
public class UserDto {
    public int id;
    public String name;
    public boolean active;

    public UserDto() {
    }
}
```

Tạo `ObjectMapper` một lần, cấu hình xong rồi mới chia sẻ. Thay `Accept: text/plain` trong phương thức `request` thành **`Accept: application/json`** để báo server định dạng mong muốn. Đoạn gọi sau đặt **bên trong method** có biến `api` là `ApiClient` từ mục 3:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpResponse;
import java.util.function.Function;

// Các import nằm đầu file; các dòng dưới nằm trong method.
ObjectMapper mapper = new ObjectMapper(); // Thực tế nên tiêm một instance dùng chung.
Function<String, UserDto> decodeJson = json -> {
    try {
        return mapper.readValue(json, UserDto.class);
    } catch (JsonProcessingException e) {
        throw new IllegalArgumentException("Invalid JSON response", e);
    }
};

HttpResponse<ApiResult<UserDto>> response = api.get(
        URI.create("https://api.example.com/users/42"), decodeJson);
if (response.statusCode() == 200) {
    UserDto user = response.body().data;
    System.out.println(user.name);
} else {
    System.err.println("HTTP " + response.statusCode());
}
```

Địa chỉ `api.example.com` chỉ minh họa và **không cần chạy** ở bài offline. Với JSON array hoặc kiểu generic, Jackson cần `TypeReference<List<UserDto>>` hoặc `JavaType` để giữ kiểu phần tử; không ép `List.class` rồi cast từng phần tử một cách mù quáng. Trong ứng dụng thực tế, kiểm tra `Content-Type`, schema/field bắt buộc và cách xử lý dữ liệu không hợp lệ. Tùy API, cần giới hạn kích thước body và tách decode nặng khỏi callback nhận mạng.

## 6. Mở rộng, quan sát và các lỗi thường gặp

- **Dùng chung client theo cấu hình:** một service có thể giữ `private final HttpClient`, được tạo trong constructor hoặc DI container. Không khởi tạo ở mỗi lần gọi và cũng không thay đổi cấu hình client đã `build()`; khi cần proxy/cert khác, tạo client riêng có chủ đích.
- **Timeout theo từng endpoint:** có thể đặt `Duration.ofSeconds(2)` cho endpoint nhanh, thời gian dài hơn cho endpoint xử lý nặng. Có thể sửa `request(uri)` để nhận thêm tham số `Duration` và gọi `timeout(...)`; không chia sẻ builder mutable.
- **Bất đồng bộ:** `sendAsync` không chặn luồng gọi. HTTP lỗi 4xx/5xx vẫn là response thường, còn timeout/I/O/parse làm `CompletableFuture` thất bại; `join()` thường bọc nguyên nhân trong `CompletionException`. Đừng nghĩ `CompletableFuture.orTimeout(...)` tự thay thế cấu hình `HttpRequest.timeout(...)` ở tầng HTTP.
- **Retry có kiểm soát:** chỉ thử lại khi lỗi tạm thời và thao tác an toàn/idempotent theo hợp đồng API; giới hạn số lần, exponential backoff và chú ý `Retry-After` khi nhận 429/503. Tránh tự động lặp POST có tác dụng phụ khi thiếu idempotency key.
- **Status và decode:** `BodyHandlers.ofString()` cũng đọc body cho 4xx/5xx. Nếu decode JSON thành DTO thành công trước khi kiểm tra status, một error JSON khác schema có thể bị hiểu nhầm là lỗi giải mã, che mất mã HTTP. Mẫu `ApiResult<T>` tách rõ hai nhánh.
- **Tài nguyên:** `ofString` / `ofByteArray` gom body vào bộ nhớ, hợp với payload nhỏ và có giới hạn. Với response lớn, dùng chiến lược stream/file, đọc hết hoặc đóng stream đúng cách để giải phóng kết nối. Luồng của `BodyHandlers.ofInputStream()` phải được đóng khi dùng xong.
- **Bảo mật thực tế:** gọi HTTPS cho dịch vụ ngoài, validate URI đầu vào để tránh yêu cầu đến địa chỉ nội bộ ngoài ý muốn, đặt token phù hợp trên từng request, không in header nhạy cảm hay toàn bộ response chứa dữ liệu cá nhân. Chỉ follow redirect khi API và chính sách xác thực cho phép.
- **Kiểm thử:** dùng mock HTTP server để kiểm tra 200 + DTO, 404 + body lỗi, 204 không body, JSON lỗi, timeout, cancel và request bất đồng bộ. Test tái sử dụng bằng cách kiểm tra cùng một instance client được tiêm/chia sẻ; đừng khẳng định pool chắc chắn dùng lại một TCP connection trong mọi điều kiện.

## 7. Bài tập tự luyện và tiêu chí hoàn thành

1. Thay `requestTimeout` thành tham số mỗi lần gọi, đặt 100 ms cho `/slow` và 2 s cho `/users/42`; quan sát timeout khác nhau dù chung một client.
2. Bổ sung endpoint `/users/43` với dữ liệu profile khác. Gọi đồng thời hai request bằng `getAsync(...)`, dùng `thenCombine(...)` để ghép kết quả, không gọi `join()` sớm trong mỗi nhánh.
3. Thêm phản hồi `204 No Content` và điều chỉnh `ApiResult<T>` để biểu diễn thành công không có body mà không parse chuỗi rỗng.
4. Với dự án có Jackson, xây DTO đúng contract của endpoint thật, đổi `Accept` sang `application/json`, thử JSON hợp lệ và không hợp lệ. Chỉ truy cập DTO khi status hợp lệ, báo lỗi rõ nhóm HTTP / transport / decoding.

**Đạt yêu cầu** khi chương trình dùng lại cùng một `HttpClient` cho nhiều lời gọi, phân biệt hai timeout, không parse response lỗi theo schema thành công, giữ status đi cùng dữ liệu có kiểu, xử lý async và interrupt đúng, và không sử dụng API chỉ có ở Java mới hơn nếu mục tiêu là Java 11.

## Tài liệu chuẩn để đối chiếu

- [Oracle Java 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Oracle Java 11 — HttpRequest.Builder và timeout](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html).
- [Oracle Java 11 — HttpResponse, BodyHandler và BodySubscribers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html) và [BodySubscribers.mapping](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html).
- [FasterXML — Jackson 2.21 (LTS) và khả năng tương thích JDK](https://github.com/FasterXML/jackson/wiki/Jackson-Release-2.21).
