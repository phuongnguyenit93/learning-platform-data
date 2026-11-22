# WebClient: Gửi yêu cầu reactive và thiết lập URI, header, cookie, body

## Mục tiêu

Bài học này hướng dẫn sử dụng Spring WebFlux `WebClient` để **gửi HTTP request theo phong cách reactive**, cấu hình **URI, header, cookie, body**, đọc response và xử lý lỗi đúng cách. Sau bài học, bạn có thể tự xây GET/POST có tham số động, gửi JSON/form/multipart, ghép pipeline `Mono`/`Flux` và tránh các lỗi hay gặp khi kết hợp HTTP với Reactive Streams. Ví dụ dùng Java 17+, Spring Framework 6.x và Spring Boot 3.x.

## 1. WebClient hoạt động như thế nào?

`WebClient` là HTTP client có fluent API, hỗ trợ non-blocking I/O và streaming. Nó thuộc `org.springframework.web.reactive.function.client` và dùng Reactor để mô tả kết quả bất đồng bộ. Một pipeline thông thường:

```text
WebClient
  -> GET / POST / PUT / PATCH / DELETE
  -> URI (path, path variable, query parameter)
  -> request headers + cookies + body nếu có
  -> retrieve() hoặc exchangeToMono(...)
  -> bodyToMono(...) / bodyToFlux(...) / toEntity(...)
  -> subscription -> HTTP I/O -> decode response
```

Ví dụ:

```java
WebClient client = WebClient.create("https://api.example.com");

Mono<String> pending = client.get()
        .uri("/health")
        .retrieve()
        .bodyToMono(String.class);
```

`Mono<T>` biểu diễn tối đa một phần tử; `Flux<T>` biểu diễn nhiều phần tử. **Tạo `Mono` chưa có nghĩa request đã được gửi**: publisher của WebClient là *cold*, HTTP I/O được kích hoạt khi có subscriber. Trong ứng dụng WebFlux, trả `Mono`/`Flux` để framework quản lý subscription. Trong console demo, có thể dùng `block` tại ranh giới đồng bộ có chủ đích.

Không gọi `subscribe()` tùy tiện trong service chỉ để “cho request chạy”: việc tách pipeline làm mất đường truyền lỗi, cancellation và ngữ cảnh xử lý. Mỗi lần subscribe một publisher lạnh có thể tạo request mới; điều đó đặc biệt quan trọng với POST có tác dụng phụ.

## 2. Khởi tạo client và cấu hình mặc định

Khi dự án Spring Boot đã quản lý phiên bản thư viện, dependency thông dụng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Có thể sử dụng WebClient trong ứng dụng Spring MVC để gọi dịch vụ HTTP; việc thêm client không bắt buộc chuyển controller sang WebFlux. Spring Boot cung cấp `WebClient.Builder` đã được cấu hình theo môi trường ứng dụng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ClientConfig {
    @Bean
    WebClient catalogClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.example.com/api")
                .defaultHeader("X-Application", "web-learning")
                .build();
    }
}
```

Có thể khởi tạo nhanh bằng `WebClient.create()`, `WebClient.create(baseUrl)` hoặc `WebClient.builder()`. Dùng client cấu hình chung và tái sử dụng thay vì tạo HTTP client/connection pool mới trong mỗi request.

`baseUrl` là tiền tố URI chung; `defaultHeader`, `defaultCookie` đặt giá trị mặc định; `filter` dùng cho xử lý chung như logging an toàn, correlation hoặc auth; `clientConnector` cấu hình tầng HTTP. `mutate()` tạo builder từ cấu hình có sẵn. Không đặt token hay cookie **riêng của từng người dùng** trong singleton client dùng chung.

## 3. Thiết lập URI an toàn

### 3.1. URI template với path variable

```java
Mono<String> response = client.get()
        .uri("/orders/{id}", 42)
        .retrieve()
        .bodyToMono(String.class);
```

Với base URL `https://api.example.com`, request hướng đến `https://api.example.com/orders/42`. `{id}` là vị trí thay biến; sử dụng URI template dễ đọc và an toàn về encoding hơn nối chuỗi thủ công.

### 3.2. URI builder với query parameter

```java
Mono<String> response = client.get()
        .uri(uriBuilder -> uriBuilder
                .path("/books")
                .queryParam("keyword", "spring reactive")
                .queryParam("page", 1)
                .queryParam("size", 20)
                .build())
        .retrieve()
        .bodyToMono(String.class);
```

Request mang các tham số `keyword`, `page`, `size` trong query string. Dấu cách trong `keyword` cần được encode; tùy cấu hình URI builder, ký tự khoảng trắng có thể được biểu diễn bằng `%20`. Không tự nối `?`/`&` hoặc encode lại giá trị đã mã hóa.

Kết hợp path variable và query:

```java
Mono<String> response = client.get()
        .uri(builder -> builder
                .path("/customers/{customerId}/orders")
                .queryParam("status", "OPEN")
                .queryParam("page", 0)
                .build(7))
        .retrieve()
        .bodyToMono(String.class);
```

Đường dẫn đại diện resource, ví dụ `/customers/7/orders`; query cho bộ lọc và phân trang, ví dụ `?status=OPEN&page=0`. `pathSegment(...)` hữu ích khi thêm từng segment độc lập; `queryParamIfPresent(...)` hữu ích khi chỉ muốn gửi tham số nếu `Optional` có giá trị.

### 3.3. Địa chỉ tương đối và tuyệt đối

`baseUrl(...)` áp dụng cho URI tương đối. Một absolute URI được truyền trực tiếp có thể thay thế base URL. Nếu URI/host đến từ input bên ngoài, cần kiểm soát scheme và danh sách host được phép để tránh SSRF; mã hóa URI không phải là kiểm tra quyền gọi đích.

## 4. HTTP method và header

Các HTTP method thường gặp:

| Method | Mục đích phổ biến | WebClient |
| --- | --- | --- |
| GET | Đọc một resource hoặc danh sách | `client.get()` |
| POST | Tạo resource, gửi lệnh hoặc dữ liệu | `client.post()` |
| PUT | Thay thế resource | `client.put()` |
| PATCH | Cập nhật một phần | `client.patch()` |
| DELETE | Xóa resource | `client.delete()` |

Hợp đồng API quyết định ngữ nghĩa chính xác. GET thường truyền điều kiện đọc bằng URI/query chứ không có body.

### 4.1. Gắn các header

```java
Mono<String> product = client.get()
        .uri("/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "req-42")
        .headers(h -> h.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(String.class);
```

Các API quan trọng:

- `header("X-Request-Id", "req-42")` thêm giá trị header cho request.
- `headers(h -> h.set("X-Request-Id", "req-42"))` thao tác trực tiếp trên `HttpHeaders`; `set` thay thế giá trị trước đó của header cùng tên.
- `accept(MediaType.APPLICATION_JSON)` khai báo định dạng phản hồi mong muốn: `Accept: application/json`.
- `contentType(MediaType.APPLICATION_JSON)` khai báo định dạng payload **gửi lên**: `Content-Type: application/json`.
- `headers(h -> h.setBearerAuth(token))` tạo `Authorization: Bearer ...`.
- `headers(h -> h.setBasicAuth(username, password))` tạo Basic auth; chỉ dùng với HTTPS.

**Dễ nhầm:** `Accept` mô tả loại dữ liệu muốn *nhận*; `Content-Type` mô tả loại dữ liệu đang *gửi*. Đặt `Content-Type` không tự tạo body. GET không có body thông thường chỉ cần `Accept` nếu quan tâm định dạng phản hồi.

HTTP header names không phân biệt chữ hoa/chữ thường. `header(...)` có thể thêm nhiều giá trị; khi muốn một giá trị duy nhất, dùng `headers(h -> h.set(...))`. Không log Authorization, cookie hay secret, và không hardcode mật khẩu/token vào source.

## 5. Cookie trong request

Cookie được gửi qua header `Cookie`, thường mang định danh phiên hoặc giá trị theo hợp đồng API:

```java
Mono<String> profile = client.get()
        .uri("/me")
        .cookie("session", sessionToken)
        .cookies(c -> c.add("locale", "vi-VN"))
        .retrieve()
        .bodyToMono(String.class);
```

Dạng HTTP tương đương thường là `Cookie: session=...; locale=vi-VN`. Nếu có cookie chung cho mọi request của một client:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.com")
        .defaultCookie("locale", "vi-VN")
        .build();
```

Phân biệt rõ: `Cookie` là request header; `Set-Cookie` là response header. WebClient không tự duy trì cookie jar giống trình duyệt. Nếu cần lưu `Set-Cookie` và gửi lại ở request sau, ứng dụng phải quản lý rõ ràng, tránh rò rỉ giữa người dùng.

Không đưa session token của từng user vào `defaultCookie` trên client singleton; gắn cookie theo request và chỉ truyền dữ liệu nhạy cảm qua HTTPS tới đích tin cậy.

## 6. Gửi request body

HTTP body chứa payload, phổ biến với POST, PUT và PATCH. WebClient dùng Spring HTTP message writers/codecs để mã hóa đối tượng Java sang JSON, text, form hoặc multipart.

### 6.1. JSON DTO có sẵn: bodyValue

```java
record CreateBookRequest(String title, int quantity) {}

Mono<String> created = client.post()
        .uri("/books")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateBookRequest("Java", 2))
        .retrieve()
        .bodyToMono(String.class);
```

Khi có Jackson JSON codec, record sẽ được mã hóa thành object JSON gồm `title` và `quantity`. `bodyValue` dùng khi bạn có một giá trị bình thường như DTO, record hoặc chuỗi.

### 6.2. Đầu vào là Mono/Flux: body(Publisher, Class)

```java
Mono<CreateBookRequest> requestBody =
        Mono.just(new CreateBookRequest("Java", 2));

Mono<String> created = client.post()
        .uri("/books")
        .contentType(MediaType.APPLICATION_JSON)
        .body(requestBody, CreateBookRequest.class)
        .retrieve()
        .bodyToMono(String.class);
```

`body(publisher, elementClass)` dùng khi dữ liệu đầu vào đã là publisher reactive. **Đừng truyền `Mono` vào `bodyValue`**; publisher không phải DTO cần serialize. Với `Flux<T>`, server phải hỗ trợ media type/định dạng streaming phù hợp; một endpoint nhận JSON object đơn lẻ không tự nhiên trở thành endpoint stream.

### 6.3. Form URL encoded

```java
Mono<String> response = client.post()
        .uri("/login")
        .body(BodyInserters.fromFormData("username", "demo")
                .with("locale", "vi"))
        .retrieve()
        .bodyToMono(String.class);
```

Import `org.springframework.web.reactive.function.BodyInserters`. Data được writer biểu diễn theo `application/x-www-form-urlencoded`. Form body và query parameter đều có key/value nhưng nằm tại vị trí khác trong HTTP request.

### 6.4. Multipart với tệp

```java
MultipartBodyBuilder parts = new MultipartBodyBuilder();
parts.part("description", "Tập tin minh họa");
parts.part("file", new FileSystemResource(Path.of("report.txt")));

Mono<String> response = client.post()
        .uri("/upload")
        .bodyValue(parts.build())
        .retrieve()
        .bodyToMono(String.class);
```

Import `org.springframework.http.client.MultipartBodyBuilder`, `org.springframework.core.io.FileSystemResource`, `java.nio.file.Path`. Đoạn minh họa giả định file `report.txt` tồn tại và API nhận `description`/`file`. Để writer thiết lập multipart boundary; không tự thêm `Content-Type: multipart/form-data` thủ công mà quên boundary.

### 6.5. Phân biệt bốn nhóm thông tin

| Phần request | Ví dụ | Vai trò |
| --- | --- | --- |
| URI/path/query | `/books/42?lang=vi` | Resource đích và tham số URL |
| Header | `Accept: application/json` | Metadata và thương lượng định dạng |
| Cookie | `Cookie: session=abc` | Thông tin trạng thái/phiên |
| Body | `{"title":"Java","quantity":2}` | Dữ liệu gửi tới server |

Không đặt password hoặc access token vào query khi có thể dùng header phù hợp: URL dễ bị ghi trong log, cache hoặc lịch sử truy cập.

## 7. Demo Java 17+ có thể chạy: gửi URI, header, cookie, JSON body

Ví dụ sau tự chạy một HTTP server cục bộ bằng JDK `HttpServer`, rồi dùng WebClient POST tới server đó. Server kiểm tra bốn yếu tố của request; nếu đúng, trả HTTP 201 và JSON, nếu sai trả 400. Mục đích là kiểm chứng pipeline đầy đủ mà không cần API bên ngoài.

**Cấu trúc dự án:**

```text
webclient-demo/
  build.gradle
  src/main/java/demo/WebClientRequestDemo.java
```

**build.gradle** (Gradle và JDK 17+, BOM Spring Boot 3.3.x cố định phiên bản tương thích):

```groovy
plugins {
    id 'application'
}
repositories {
    mavenCentral()
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.6')
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
application {
    mainClass = 'demo.WebClientRequestDemo'
}
```

**src/main/java/demo/WebClientRequestDemo.java:**

```java
package demo;

import com.sun.net.httpserver.HttpServer;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class WebClientRequestDemo {
    public record CreateOrderRequest(String product, int quantity) {}
    public record OrderResult(long id, boolean accepted) {}

    public static void main(String[] args) throws Exception {
        // Cổng 0 để hệ điều hành chọn cổng local còn trống.
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/api/orders/", exchange -> {
            try {
                String uri = exchange.getRequestURI().toString();
                String requestId = exchange.getRequestHeaders()
                        .getFirst("X-Request-Id");
                String cookie = exchange.getRequestHeaders()
                        .getFirst("Cookie");
                String contentType = exchange.getRequestHeaders()
                        .getFirst("Content-Type");
                String json = new String(
                        exchange.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8);

                boolean valid = "POST".equals(exchange.getRequestMethod())
                        && "/api/orders/42?source=guide".equals(uri)
                        && "req-42".equals(requestId)
                        && "session=demo-token".equals(cookie)
                        && "application/json".equals(contentType)
                        && json.contains("\"product\":\"book\"")
                        && json.contains("\"quantity\":2");

                int status = valid ? 201 : 400;
                String data = valid
                        ? "{\"id\":42,\"accepted\":true}"
                        : "{\"error\":\"invalid request\"}";
                byte[] responseBytes = data.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders()
                        .set("Content-Type", "application/json");
                exchange.sendResponseHeaders(status, responseBytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(responseBytes);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();
            WebClient client = WebClient.builder()
                    .baseUrl("http://127.0.0.1:" + port)
                    .build();

            Mono<OrderResult> pending = client.post()
                    .uri(uri -> uri.path("/api/orders/{id}")
                            .queryParam("source", "guide")
                            .build(42))
                    .header("X-Request-Id", "req-42")
                    .cookie("session", "demo-token")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .bodyValue(new CreateOrderRequest("book", 2))
                    .retrieve()
                    .bodyToMono(OrderResult.class);

            // block chỉ ở biên console demo; không block trong event loop.
            OrderResult result = pending.block(Duration.ofSeconds(5));
            System.out.println("id=" + result.id()
                    + ", accepted=" + result.accepted());
        } finally {
            server.stop(0);
        }
    }
}
```

Chạy trong thư mục demo bằng `gradle run` nếu có Gradle; hoặc `./gradlew run` khi dự án đã tạo Gradle Wrapper.

**Dòng do chương trình in ra stdout:**

```text
id=42, accepted=true
```

Giải thích lần lượt:

1. `uri(...)` dựng `/api/orders/42?source=guide` từ template/path/query.
2. `header(...)` tạo `X-Request-Id: req-42` để định danh request.
3. `cookie(...)` gửi `session=demo-token`.
4. `contentType(...)` và `bodyValue(...)` gửi record dưới dạng JSON.
5. `retrieve().bodyToMono(OrderResult.class)` giải mã response JSON; mã 400 sẽ phát lỗi HTTP.
6. `block` tại `main` cho console chờ kết quả rồi in; WebFlux service thực tế nên trả lại `Mono<OrderResult>`.

Ứng dụng mẫu không phải server sản xuất. Nó chỉ giúp quan sát rằng thiếu/sai bất cứ thành phần nào sẽ làm HTTP request không đạt hợp đồng đã đặt.

## 8. Nhận response, status và lỗi

Các phương thức thường dùng:

```java
Mono<String> text = client.get()
        .uri("/status")
        .retrieve()
        .bodyToMono(String.class);

Mono<ResponseEntity<String>> full = client.get()
        .uri("/status")
        .retrieve()
        .toEntity(String.class);

Flux<EventDto> events = client.get()
        .uri("/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(EventDto.class);
```

Ở đoạn này `EventDto` chỉ là kiểu DTO minh họa do ứng dụng định nghĩa; server phải thực sự trả luồng tương ứng mới dùng `bodyToFlux` theo kiểu đó. `toEntity` đọc cả status và headers; `bodyToMono` đọc tối đa một body object; với response không có body (ví dụ HTTP 204), dùng `toBodilessEntity()` hoặc `bodyToMono(Void.class)` khi phù hợp.

### 8.1. Lỗi HTTP mặc định và onStatus

`retrieve()` mặc định chuyển status 4xx và 5xx thành lỗi `WebClientResponseException` và các subtype. Xử lý 404 có ngữ nghĩa riêng bằng `onStatus`:

```java
Mono<Book> book = client.get()
        .uri("/books/{id}", 42)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> new IllegalStateException(
                                "Book not found: " + body)))
        .bodyToMono(Book.class)
        .timeout(Duration.ofSeconds(3));
```

`Book` là DTO giả định đã khai báo. `onStatus` xử lý một status xác định; lỗi khác vẫn dùng xử lý mặc định. `timeout` giới hạn thời gian ở tầng reactive; khi cần, cấu hình thêm connect/read timeout tại HTTP connector.

Nếu cần tự quyết định theo status và xử lý response ở cấp thấp:

```java
Mono<String> result = client.get()
        .uri("/status")
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(String.class);
            }
            return response.createException().flatMap(Mono::error);
        });
```

Với `exchangeToMono`, phải xử lý/tiêu thụ body đúng nhánh để không giữ tài nguyên kết nối. Không dùng API thấp hơn chỉ để đọc body khi `retrieve` đã đáp ứng.

### 8.2. Retry và timeout

Retry sẽ đăng ký lại pipeline và **có thể gửi lại HTTP request**. Chỉ retry khi hành vi được coi là an toàn/idempotent hoặc API hỗ trợ idempotency key, có giới hạn lần thử và phân loại lỗi cần retry. POST tạo đơn hàng không nên retry mù quáng. Timeout ở client giúp tránh chờ vô hạn nhưng không đảm bảo server chưa thực hiện hành động.

## 9. Sai lầm thường gặp

1. **Tạo Mono nhưng không có subscriber:** request chưa được gửi. Trong WebFlux, trả publisher; đừng chèn `subscribe()` tùy tiện rồi bỏ lỗi.
2. **Gọi `block()` trong event-loop:** phá mô hình non-blocking, giảm thông lượng hoặc bị Reactor từ chối. `block` trong demo console có chủ đích, không phải mẫu code dùng trong controller reactive.
3. **Ghép URI bằng chuỗi từ input:** dễ lỗi encoding, thiếu `?`/`&` hoặc bị đổi host ngoài ý muốn. Dùng URI template/builder và kiểm soát đích.
4. **Nhầm `Accept` với `Content-Type`:** cái đầu mô tả response mong muốn, cái sau mô tả request payload.
5. **Đưa `Mono<Dto>` vào `bodyValue`:** dùng `body(mono, Dto.class)` cho publisher; `bodyValue(dto)` cho DTO đã có.
6. **Cho rằng WebClient tự lưu cookie từ `Set-Cookie`:** phải có cơ chế quản lý/chuyển tiếp riêng.
7. **Để token hoặc session của người dùng trong default headers/cookies toàn cục:** nguy cơ lẫn dữ liệu giữa users. Gắn credential cho từng request.
8. **Bỏ qua status HTTP:** 4xx/5xx thường tạo tín hiệu lỗi, không tự giải mã thành DTO thành công.
9. **Retry mọi lỗi POST:** có thể tạo dữ liệu trùng. Cần tiêu chuẩn idempotent và số lần retry hữu hạn.
10. **Kỳ vọng `Flux` luôn nhận stream từng phần:** media type và server phải hỗ trợ streaming thật; client reactive không tự biến một response JSON đơn thành nguồn sự kiện vô hạn.
11. **Tạo WebClient mới ở mọi lời gọi:** làm cấu hình phân tán và có thể lãng phí tài nguyên kết nối.
12. **Log body/header nhạy cảm:** password, access token, cookie và dữ liệu riêng tư cần được che trong tracing và logs.

## 10. Tự kiểm tra

Trước khi gửi request, rà soát: HTTP method đúng chưa? URI path và query đã encode? Host có được phép? `Accept`/`Content-Type` đúng không? Header/cookie có rò bí mật? Body là DTO hay publisher? Server nhận JSON, form hay multipart? Pipeline được subscribe ở đâu? 4xx/5xx, timeout và retry được xử lý thế nào?

**Bài tập A:** Với `baseUrl("https://api.example.com")`, viết GET `/books/12?lang=vi&page=1`, gắn `Accept: application/json` và `X-Request-Id: learning-1`, kết quả là `Mono<String>`. Dùng `uri(builder -> ...)`, `accept(...)`, `header(...)`, `retrieve()`.

**Bài tập B:** Viết POST `/books` gửi record `BookCreate(String title, int quantity)` bằng `bodyValue`. Khi body đầu vào chuyển thành `Mono<BookCreate>`, đổi sang `body(mono, BookCreate.class)`. Giải thích lý do.

**Bài tập C:** Chạy ví dụ server cục bộ; thử bỏ header `X-Request-Id` hoặc đổi tên cookie rồi dự đoán lỗi. Khôi phục request và kiểm chứng output thành công.

## Tài liệu chính thức

- WebClient tổng quan: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- WebClient builder/configuration: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Request body, form, multipart: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html
- retrieve / response / onStatus: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- URI building: https://docs.spring.io/spring-framework/reference/web/webflux/uri-building.html
