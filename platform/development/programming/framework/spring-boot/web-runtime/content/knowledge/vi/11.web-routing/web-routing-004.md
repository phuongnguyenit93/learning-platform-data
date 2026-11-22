# Biến đường dẫn, kiểu dữ liệu và trường hợp không khớp trong Spring Boot

## 1. Mục tiêu: tách routing khỏi chuyển kiểu dữ liệu

Trong ứng dụng Spring Boot, một endpoint có thể sử dụng **URI template variable** (biến đường dẫn), ví dụ `/users/42`, `/orders/PAID` hoặc `/documents/550e8400-e29b-41d4-a716-446655440000`. Hai bước cơ bản của Spring MVC và WebFlux là:

1. **Route matching**: so khớp HTTP method, URL path, các điều kiện mapping như `params`, `headers`, `consumes`, `produces` để chọn handler.
2. **Argument resolution và conversion**: lấy giá trị chuỗi được capture từ path rồi chuyển sang tham số Java của handler, như `long`, `UUID`, `enum` hoặc kiểu domain tùy biến.

Sự phân biệt này giải thích một tình huống dễ nhầm:

- Path **không khớp** pattern → thường HTTP **404 Not Found** nếu không có handler khác.
- Path **khớp** nhưng không chuyển được giá trị sang kiểu Java → thường HTTP **400 Bad Request**.
- Path khớp, HTTP method sai → thường HTTP **405 Method Not Allowed**.
- `Content-Type` request không phù hợp `consumes` → thường **415 Unsupported Media Type**.
- `Accept` không phù hợp `produces` → thường **406 Not Acceptable**.

Status và body lỗi cuối cùng còn phụ thuộc custom exception handler, Spring Security, embedded server, reverse proxy và phiên bản Framework. Không viết API contract theo giả định mọi lỗi đều trả một định dạng body giống nhau.

## 2. Luồng xử lý biến đường dẫn trong Spring MVC

Ví dụ:

```java
@GetMapping("/users/{id}")
public UserDto get(@PathVariable("id") long id) {
    return new UserDto(id, "Lan");
}
```

Với `GET /users/42`, quá trình khái quát:

```text
HTTP GET /users/42
        |
        v
DispatcherServlet
        |
        v
RequestMappingHandlerMapping
  - Pattern /users/{id} khớp URL
  - Method GET phù hợp
  - Capture id = "42"
        |
        v
HandlerAdapter + argument resolver
  - ConversionService: "42" -> long 42
        |
        v
Controller method get(42)
        |
        v
HttpMessageConverter / View rendering
        |
        v
HTTP response
```

Nếu URL là `/users/abc`, route `/users/{id}` **vẫn khớp** vì `{id}` không mặc nhiên là số. Lỗi phát sinh ở conversion `"abc"` thành `long`. Controller chưa được gọi và mặc định thường trả 400.

Trong WebFlux, `DispatcherHandler`, `HandlerMapping` và `HandlerAdapter` đảm nhận các vai trò tương ứng, nhưng runtime và exception handling là reactive; đừng dùng `DispatcherServlet` để giải thích pipeline của WebFlux.

## 3. @PathVariable và tên biến

Một biến được đặt trong dấu ngoặc nhọn của mapping:

```java
@GetMapping("/products/{productId}")
public ProductDto find(
        @PathVariable("productId") long productId) {
    return new ProductDto(productId, "Laptop");
}
```

Đây là method minh họa bên trong `@RestController`, không phải file Java độc lập. `productId` trong `{productId}` là tên biến mà route capture; `@PathVariable("productId")` chỉ rõ biến được inject vào tham số.

Tên tham số Java có thể khác tên biến:

```java
@GetMapping("/products/{productId}")
public ProductDto find(@PathVariable("productId") long id) {
    return new ProductDto(id, "Laptop");
}
```

Nếu bỏ tên khỏi annotation, ví dụ `@PathVariable long productId`, Spring cần metadata tên tham số như khi compiler bật `-parameters`. Ghi tên tường minh giúp ví dụ ổn định và tránh lỗi binding do cấu hình biên dịch.

**Phân biệt:** `/products/7?details=true` có `7` là path variable, còn `details=true` là query parameter thường đọc bằng `@RequestParam`. `@RequestBody` lại xử lý request body, không thay cho `@PathVariable`.

## 4. PathPattern và số lượng segment

Spring MVC hiện đại sử dụng `PathPattern` để so khớp URL theo cấu trúc segment. Các quy tắc quan trọng:

| Pattern | URL | Kết quả |
|---|---|---|
| `/users/{id}` | `/users/42` | Match, capture `id="42"` |
| `/users/{id}` | `/users/abc` | Vẫn match; conversion xử lý sau |
| `/users/{id}` | `/users` | Không match vì thiếu segment |
| `/users/{id}` | `/users/42/profile` | Không match vì thừa segment |
| `/shops/{shop}/items/{item}` | `/shops/acme/items/7` | Match hai biến |
| `/assets/*.png` | `/assets/logo.png` | Match wildcard trong một segment |
| `/assets/{*path}` | `/assets/icons/logo.png` | Catch-all, capture nhiều segment |

`{name}` capture một segment, không tự bắt nhiều đoạn có dấu gạch chéo. `{*path}` bắt toàn bộ phần đuôi nhiều segment; trong tài liệu Spring, với `/resources/{*file}`, URL `/resources/images/a.png` có thể capture `file="/images/a.png"`.

Cú pháp `**` cũng bắt nhiều path segments nhưng không gắn tên biến. Trong `PathPattern`, wildcard catch-all kiểu `**` và `{*path}` phải đứng **ở cuối pattern**; không dùng chúng ở giữa route rồi thêm một segment khác.

## 5. ConversionService và những kiểu Java thường gặp

Sau khi route match, Spring có thể chuyển chuỗi URI variable sang kiểu Java của tham số bằng `ConversionService`, `Converter` hoặc `Formatter`.

| Kiểu tham số | URL ví dụ | Lỗi thường gặp |
|---|---|---|
| `String` | `/codes/AB-42` | Hiếm khi lỗi vì conversion; vẫn cần validation |
| `int` | `/items/42` | Chuỗi chữ hoặc vượt phạm vi 32 bit |
| `long` / `Long` | `/users/987654321` | Không phải số hoặc vượt phạm vi 64 bit |
| `UUID` | `/docs/550e8400-e29b-41d4-a716-446655440000` | Không thể parse UUID |
| `enum` | `/orders/PAID` | Giá trị không thuộc enum hoặc sai case |
| `BigDecimal` | `/prices/19.50` | Giá trị không convert được |
| Kiểu domain | `/order-keys/acme-42` | Chưa có Converter hoặc parser ném lỗi |

Ví dụ `/users/abc` với route `/users/{id}` và `@PathVariable long id`: Spring MVC có thể ném `MethodArgumentTypeMismatchException` và xử lý thành 400. Giá trị `-7` vẫn parse được thành `long`, nhưng API có cho phép ID âm không là vấn đề **nghiệp vụ**, không phải vấn đề chuyển kiểu.

Một kiểu đã parse được cũng không chứng minh tài nguyên có tồn tại trong database. Đừng trộn lỗi nhập liệu (400) với việc không tìm thấy record (thường 404).

## 6. Regex giới hạn path trước khi binding

Có thể ràng buộc biến đường dẫn bằng cú pháp `{variable:regex}`:

```java
@GetMapping("/numbers/{value:[0-9]+}")
public NumberDto get(@PathVariable("value") long value) {
    return new NumberDto(value);
}
```

Pattern `[0-9]+` chỉ match một hay nhiều chữ số ASCII. So sánh:

| Request | Match URL pattern? | Conversion | Status thường gặp |
|---|---|---|---|
| `/numbers/42` | Có | `long(42)` | 200 nếu controller xử lý thành công |
| `/numbers/abc` | Không | Không diễn ra | 404 nếu không có route khác |
| `/numbers/-3` | Không | Không diễn ra | 404 nếu không có route khác |
| `/numbers/0007` | Có | `long(7)` | 200 hoặc theo nghiệp vụ |
| `/numbers/999999999999999999999` | Có | Overflow `long` | 400 điển hình |

Regex làm thay đổi **route matching**; kiểu `long` làm thay đổi **argument conversion**. Vì thế cùng chuỗi `abc` có thể tạo 404 với route regex và 400 với route `/{id}` không regex. Không nên viết regex phức tạp nếu không có nhu cầu rõ ràng; regex có nguy cơ xử lý tốn tài nguyên khi thiết kế kém.

## 7. Ví dụ hoàn chỉnh Spring Boot 3.5 + Java 17

Tạo project Spring Boot 3.5 với Java 17 và `spring-boot-starter-web`. Đoạn dependency trong `pom.xml` dưới đây giả định project đã có Spring Boot parent hoặc dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Cấu trúc file:

```text
src/main/java/com/example/routes/
    RoutesApplication.java
    RoutingController.java
src/main/resources/
    application.properties
```

File `src/main/java/com/example/routes/RoutesApplication.java`:

```java
package com.example.routes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutesApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutesApplication.class, args);
    }
}
```

File `src/main/java/com/example/routes/RoutingController.java`:

```java
package com.example.routes;

import java.util.UUID;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RoutingController {

    @GetMapping("/api/users/{id}")
    public UserResponse user(@PathVariable("id") long id) {
        return new UserResponse(id, "user-" + id);
    }

    @GetMapping("/api/numbers/{value:[0-9]+}")
    public NumberResponse number(
            @PathVariable("value") long value) {
        return new NumberResponse(value);
    }

    @GetMapping("/api/documents/{id}")
    public DocumentResponse document(
            @PathVariable("id") UUID id) {
        return new DocumentResponse(id, "document");
    }

    @GetMapping("/api/orders/{status}")
    public OrderResponse order(
            @PathVariable("status") OrderStatus status) {
        return new OrderResponse(status.name());
    }

    public enum OrderStatus { NEW, PAID, SHIPPED }

    public record UserResponse(long id, String name) {}
    public record NumberResponse(long value) {}
    public record DocumentResponse(UUID id, String kind) {}
    public record OrderResponse(String status) {}
}
```

File `src/main/resources/application.properties`:

```properties
server.port=8080
```

Các record trong Java 17 được Jackson JSON converter serialize theo cấu hình Spring Web starter thông thường. Ví dụ này không kết nối database: response cố định theo input để minh họa routing.

Chạy bằng Maven Wrapper đã có trong project:

```bash
./mvnw spring-boot:run
```

## 8. Gửi request thành công và dự kiến response

```bash
curl -s http://localhost:8080/api/users/42
curl -s http://localhost:8080/api/numbers/7
curl -s http://localhost:8080/api/orders/PAID
curl -s http://localhost:8080/api/documents/550e8400-e29b-41d4-a716-446655440000
```

Mỗi lệnh là một HTTP request riêng. Body JSON mong đợi:

```json
{"id":42,"name":"user-42"}
{"value":7}
{"status":"PAID"}
{"id":"550e8400-e29b-41d4-a716-446655440000","kind":"document"}
```

Các response được trình bày theo từng dòng cho dễ đọc, không phải bản ghi stdout byte-for-byte của bốn lệnh `curl -s` liên tiếp, bởi JSON body không nhất thiết kết thúc bằng newline.

Để xem status và headers:

```bash
curl -i http://localhost:8080/api/users/42
```

Với ví dụ đang chạy trên port 8080, request hợp lệ thường có status 200 và `Content-Type` tương thích với JSON.

## 9. Gửi request sai và phân biệt 400, 404, 405

```bash
curl -i http://localhost:8080/api/users/not-a-number
curl -i http://localhost:8080/api/numbers/abc
curl -i http://localhost:8080/api/orders/paid
curl -i http://localhost:8080/api/documents/not-a-uuid
curl -i -X POST http://localhost:8080/api/users/42
```

Dự kiến trong Spring MVC mặc định:

| Request | Status | Lý do |
|---|---|---|
| GET `/api/users/not-a-number` | 400 | Match path, nhưng `long` conversion thất bại |
| GET `/api/numbers/abc` | 404 | Regex `[0-9]+` không match |
| GET `/api/orders/paid` | 400 | Enum mặc định có `PAID`, không có `paid` |
| GET `/api/documents/not-a-uuid` | 400 | UUID conversion thất bại |
| POST `/api/users/42` | 405 | Path có handler GET nhưng không có POST tương ứng |
| GET `/api/users` | 404 | Route thiếu segment `{id}` |

Body lỗi phụ thuộc Boot version, `@ControllerAdvice`, `ErrorAttributes` và Spring Security. Khi Spring MVC chưa chọn được handler, controller code không chạy; không dùng breakpoint ở controller làm bằng chứng rằng request chưa vào server.

## 10. UUID, enum và quy tắc biểu diễn ổn định

Với `@PathVariable UUID id`, Spring có thể chuyển chuỗi UUID bằng converter có sẵn. Nếu parse thành công nhưng resource không tồn tại trong database, controller/service mới cần chủ động trả 404. UUID format hợp lệ và ID có tồn tại là hai điều khác nhau.

Với enum:

```java
public enum OrderStatus { NEW, PAID, SHIPPED }

@GetMapping("/orders/{status}")
public String find(@PathVariable("status") OrderStatus status) {
    return status.name();
}
```

Đoạn trên minh họa trong controller, không phải Java file độc lập. Với converter mặc định, `PAID` hợp lệ trong khi `paid` không được tự coi là giống `PAID`. Nếu API muốn không phân biệt hoa/thường hoặc dùng slug như `in-progress`, cần một converter tùy chỉnh và API contract được kiểm thử.

Nên chọn biểu diễn path ổn định và độc lập với tên enum nội bộ khi API được phát hành cho nhiều client. Đổi tên enum có thể vô tình phá đường dẫn nếu URL chính là `enum.name()`.

## 11. Số đúng kiểu nhưng sai nghiệp vụ

`@PathVariable long id` cho phép dữ liệu parse được thành long, kể cả số âm hoặc 0; nhưng nhiều hệ thống quy định ID phải dương.

Nếu mong muốn `/users/0` trả lỗi client 400, có thể validate trong service/controller hoặc dùng Bean Validation phù hợp.

Ví dụ fragment:

```java
if (id <= 0) {
    throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "id phải là số dương");
}
```

Cần import `org.springframework.web.server.ResponseStatusException` và `org.springframework.http.HttpStatus` trong method chứa đoạn code trên.

Những tình huống khác:

- `/users/999999999999999999999999`: overflow `long`, conversion fail → thường 400.
- `/users/0`: parse hợp lệ, nhưng domain không cho phép → ứng dụng tự quyết định 400 hoặc contract khác.
- `/users/42`: parse hợp lệ, nhưng DB không có record → thường 404 do business lookup.
- `/users/42`: record có, nhưng người dùng không được quyền → authorization quyết định 401/403 hoặc chính sách hạn chế tiết lộ tồn tại.

Đừng nhầm Spring tự convert được ID với việc Spring đã kiểm tra database hay quyền truy cập.

## 12. Nhiều biến, path thiếu segment và required=false

Route có nhiều biến:

```java
@GetMapping("/tenants/{tenantId}/orders/{orderId}")
public OrderDto findOrder(
        @PathVariable("tenantId") String tenantId,
        @PathVariable("orderId") long orderId) {
    return service.find(tenantId, orderId);
}
```

GET `/tenants/acme/orders/42` cung cấp đủ hai giá trị. GET `/tenants/acme/orders` không match vì thiếu một segment.

Nếu cần lấy tất cả biến theo tên:

```java
@GetMapping("/route-info/{tenant}/{resource}")
public Map<String, String> pathVars(
        @PathVariable Map<String, String> vars) {
    return vars;
}
```

Đây là method minh họa trong `@RestController`; import `java.util.Map` và các annotation Spring liên quan. Với `/route-info/acme/products`, Map thường chứa hai cặp `tenant=acme` và `resource=products`.

**Lưu ý:** `@PathVariable(required=false)` không làm pattern `/products/{id}` tự match `/products`. Route matching diễn ra trước. Nếu cần cả danh sách và chi tiết, dùng `@GetMapping("/products")` và `@GetMapping("/products/{id}")` riêng; hoặc định nghĩa nhiều pattern rõ ràng và xử lý nullable theo contract.

`MissingPathVariableException` khi method đã được chọn nhưng annotation yêu cầu biến không có có thể là lỗi cấu hình của server, khác với lỗi kiểu dữ liệu của client. Không ép cả hai về 400 một cách vô điều kiện.

## 13. Route specificity và xung đột mapping

Giả sử:

```java
@GetMapping("/users/me")
public Profile me() { /* ... */ }

@GetMapping("/users/{id}")
public Profile byId(@PathVariable("id") String id) { /* ... */ }
```

Khi GET `/users/me`, route literal `/users/me` cụ thể hơn `/users/{id}`, nên thường được ưu tiên. Thứ tự khai báo method trong file Java không phải yếu tố quyết định.

Nguyên tắc:

- Literal path thường cụ thể hơn biến `{id}`.
- Wildcard một segment khác catch-all nhiều segment.
- `PathPattern` dùng quy tắc specificity khi nhiều pattern có thể match.
- Trùng handler mapping có thể gây lỗi `Ambiguous mapping` lúc startup hoặc khi dispatch.
- Điều kiện HTTP method, `params`, `headers`, `produces`, `consumes` cũng ảnh hưởng việc chọn handler.

Nếu ứng dụng có `/users/me` và `/users/{id}`, tránh vô tình để literal `me` bị convert sang `long`; sử dụng route rõ ràng và kiểm thử. Nếu pattern có regex quá hẹp, một đường dẫn cần hỗ trợ có thể bị 404 trước khi controller nhận dữ liệu.

## 14. Converter tùy biến cho kiểu domain

Đôi khi ID trên URL có cấu trúc riêng, ví dụ `/order-keys/acme-42`. Thay vì tự parse ở từng controller, có thể đăng ký một `Converter<String, OrderKey>`.

File `src/main/java/com/example/routes/OrderKey.java`:

```java
package com.example.routes;

public record OrderKey(String tenant, long number) {
}
```

File `src/main/java/com/example/routes/OrderKeyConverter.java`:

```java
package com.example.routes;

import org.springframework.core.convert.converter.Converter;

public final class OrderKeyConverter
        implements Converter<String, OrderKey> {

    @Override
    public OrderKey convert(String text) {
        String[] parts = text.split("-", 2);
        if (parts.length != 2 || parts[0].isBlank()) {
            throw new IllegalArgumentException("Invalid order key");
        }
        try {
            long value = Long.parseLong(parts[1]);
            if (value <= 0) {
                throw new IllegalArgumentException("Invalid order key");
            }
            return new OrderKey(parts[0], value);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Invalid order key", ex);
        }
    }
}
```

File `src/main/java/com/example/routes/RoutingConversionConfiguration.java`:

```java
package com.example.routes;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class RoutingConversionConfiguration
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new OrderKeyConverter());
    }
}
```

Một `@RestController` trong cùng project có thể nhận:

```java
@GetMapping("/order-keys/{key}")
public OrderKey find(@PathVariable("key") OrderKey key) {
    return key;
}
```

`acme-42` chuyển thành `OrderKey("acme", 42)`; `acme-abc` gây lỗi conversion. Converter nên thuần, nhanh, không gọi database hoặc HTTP. Nếu tenant cho phép dấu `-`, parser của ví dụ chưa đáp ứng; cần một grammar khác có đặc tả rõ ràng.

## 15. Lỗi conversion và cách trả error response ổn định

Spring MVC có thể chuyển lỗi chuyển kiểu thành 400 mặc định. Nếu cần body API thống nhất, có thể tạo `@RestControllerAdvice`:

File `src/main/java/com/example/routes/PathErrorAdvice.java`:

```java
package com.example.routes;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class PathErrorAdvice {

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<Map<String, String>> mismatch(
            MethodArgumentTypeMismatchException ex) {
        return ResponseEntity.badRequest().body(
                Map.of("error", "INVALID_PATH_VARIABLE"));
    }
}
```

Khi advice này bắt được conversion mismatch, response JSON có nội dung tương đương:

```json
{"error":"INVALID_PATH_VARIABLE"}
```

Đừng tiết lộ nội dung nhạy cảm, stacktrace, SQL, token hoặc cấu trúc hệ thống trong body lỗi. Nếu cần thông tin lỗi chi tiết, dùng `ProblemDetail` hoặc error schema có mã lỗi và request ID đã chuẩn hóa.

Advice kiểu này **không xử lý** trường hợp một URL không match route trước khi handler được chọn. Để xử lý 404, cần cơ chế not-found/error handling riêng, không dựa vào `MethodArgumentTypeMismatchException`.

## 16. Spring WebFlux: @PathVariable và functional routing

WebFlux annotated controller cũng hỗ trợ type conversion:

```java
package com.example.reactive;

import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {

    @GetMapping("/api/docs/{id}")
    public Mono<Document> document(
            @PathVariable("id") UUID id) {
        return Mono.just(new Document(id, "ready"));
    }

    public record Document(UUID id, String state) {}
}
```

Đoạn Java trên là một controller chạy trong project Spring Boot WebFlux với `spring-boot-starter-webflux`. Khi UUID không convert được, lỗi đầu vào thường trở thành 400 trong reactive error flow mặc định. Path không match vẫn là bài toán routing và thường 404.

Functional WebFlux routing khác ở cách đọc biến:

```java
@Bean
RouterFunction<ServerResponse> router() {
    return RouterFunctions.route(
        RequestPredicates.GET("/api/items/{id}"),
        request -> {
            try {
                long id = Long.parseLong(
                        request.pathVariable("id"));
                return ServerResponse.ok().bodyValue(
                        Map.of("id", id));
            } catch (NumberFormatException ex) {
                return ServerResponse.badRequest().bodyValue(
                        Map.of("error", "INVALID_ID"));
            }
        });
}
```

Fragment là một method bên trong class `@Configuration`, cần import `java.util.Map`, `org.springframework.context.annotation.Bean` và các thành phần `org.springframework.web.reactive.function.server.*`. Trong functional route này, `request.pathVariable("id")` trả `String` nên parser được gọi **thủ công**, khác annotated method có tham số `long` được tự convert.

Spring Boot có cả `spring-boot-starter-web` và `spring-boot-starter-webflux` thường ưu tiên MVC theo mặc định; đừng suy đoán runtime reactive chỉ vì controller trả `Mono`.

## 17. Dấu chấm, trailing slash và URL encoding

Một segment trong URL có thể chứa dấu chấm:

```text
/files/report.v2.pdf
```

Spring MVC hiện đại không mặc nhiên dùng hậu tố `.pdf` hoặc `.json` làm cơ chế tự suy luận representation, cũng không nên giả định tên view hoặc media type tự đổi theo extension.

Trailing slash cần kiểm thử: ở Spring Framework 6.x, matching thêm dấu `/` cuối path không còn mặc định như một số ứng dụng cũ. `/users/42` và `/users/42/` có thể không match cùng một mapping. Định nghĩa URL canonical và điều chỉnh client/proxy thống nhất.

Đối với `%2F` (encoded slash), `%2e` hoặc backslash encoded, cách giải mã có thể khác nhau giữa reverse proxy, servlet container và WebFlux server. Đừng dựa vào việc encoded slash luôn giữ nguyên thành một segment. `PathPattern` xử lý path theo segment để giảm mơ hồ, nhưng cần test đúng runtime và cấu hình mạng.

**An toàn:** Không dùng `@PathVariable` trực tiếp làm đường dẫn file, SQL fragment hay redirect URL. Xác thực quyền truy cập với tài nguyên thực tế sau khi đã chuẩn hóa ID, tránh bất nhất giữa proxy, Spring Security và handler routing. Không để token hoặc thông tin nhạy cảm trong URL vì URL dễ xuất hiện trong access log.

## 18. Kiểm thử với MockMvc: phân biệt path không match và conversion fail

Trong project MVC của mục 7, thêm `spring-boot-starter-test` theo cấu hình Maven thường dùng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

File `src/test/java/com/example/routes/RoutingControllerTest.java`:

```java
package com.example.routes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RoutingControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validIdConvertsToLong() throws Exception {
        mvc.perform(get("/api/users/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42));
    }

    @Test
    void invalidLongIsBadRequest() throws Exception {
        mvc.perform(get("/api/users/not-a-number"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void regexRejectsNonDigitBeforeConversion() throws Exception {
        mvc.perform(get("/api/numbers/abc"))
            .andExpect(status().isNotFound());
    }

    @Test
    void numericOverflowFailsAfterRegexMatch() throws Exception {
        mvc.perform(get("/api/numbers/999999999999999999999"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidUuidIsBadRequest() throws Exception {
        mvc.perform(get("/api/documents/not-a-uuid"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void enumCaseMattersByDefault() throws Exception {
        mvc.perform(get("/api/orders/paid"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void wrongMethodReturnsMethodNotAllowed() throws Exception {
        mvc.perform(post("/api/users/42"))
            .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void missingSegmentDoesNotMatch() throws Exception {
        mvc.perform(get("/api/users"))
            .andExpect(status().isNotFound());
    }
}
```

Chạy:

```bash
./mvnw test
```

Bộ test dùng Spring MVC `MockMvc`, không tạo một HTTP port thật. Nếu project có Spring Security, custom error handlers hoặc mapping khác thì cần điều chỉnh test context/kỳ vọng. Với WebFlux, dùng `@WebFluxTest` và `WebTestClient` thay vì `MockMvc`.

## 19. Các trường hợp không khớp: bảng chẩn đoán

| Trường hợp | Nguyên nhân | Hướng xử lý |
|---|---|---|
| 404 với `/users/abc` và regex digits | Pattern không nhận chữ cái | Kiểm tra `{id:regex}` và contract URL |
| 400 với `/users/abc` và kiểu `long` | Conversion sau match thất bại | Kiểm tra input và converter |
| 400 với số rất lớn | Vượt giới hạn kiểu Java | Chọn kiểu đúng hoặc giới hạn độ dài ID |
| 404 với `/users` | Thiếu path segment bắt buộc | Thêm route riêng cho collection |
| 400 với `/orders/paid` | Enum mặc định case-sensitive | Quy định canonical slug/case hoặc converter riêng |
| 404 với `/users/42/profile` | Thừa segment | Kiểm tra route nesting |
| 405 với POST tới GET route | HTTP method không được mapping | Thêm mapping hợp lệ nếu cần |
| 406 khi client chỉ chấp nhận XML | `Accept` không khớp `produces` | Kiểm tra representation hỗ trợ |
| 415 khi POST `text/plain` | `Content-Type` không phù hợp `consumes` | Gửi đúng input media type |
| Controller không chạy nhưng có 401/403 | Security filter ngăn request | Kiểm tra authentication/authorization |
| Status khác kỳ vọng trên production | Proxy/gateway rewrite hoặc trả lỗi trước Spring | Kiểm tra log và URL sau proxy |
| Ambiguous mapping | Nhiều handler cạnh tranh | Thiết kế route cụ thể và không trùng pattern |

Phân biệt **routing**, **conversion**, **validation**, **resource lookup**, **security** và **content negotiation** giúp đặt lỗi ở đúng tầng thay vì bắt tất cả rồi trả 400.

## 20. Quy trình debug và checklist thiết kế

1. Đọc HTTP method và URL **thực tế tới ứng dụng**, không chỉ URL phía browser.
2. Xác nhận handler mapping gồm literal segment, `{id}`, regex hoặc catch-all.
3. Kiểm tra route có match không; đừng vội debug controller khi handler chưa được chọn.
4. Đối chiếu tên `@PathVariable("...")` và biến trong template.
5. Kiểm tra conversion `String` → `int/long/UUID/enum/custom domain`, bao gồm overflow.
6. Tách lỗi syntactic conversion khỏi validation nghiệp vụ (ID dương, tenant hợp lệ, enum hợp lệ).
7. Tách tài nguyên không tồn tại (404 do service quyết định) khỏi invalid input.
8. Kiểm tra HTTP method và `produces/consumes` để phân biệt 405/406/415.
9. Kiểm thử dấu chấm, trailing slash, encoded slash và proxy rewrite khi hệ thống sử dụng.
10. Đồng bộ route matching với Spring Security; không log path secrets.
11. Dùng `WebMvcConfigurer.addFormatters` cho custom converter của MVC, tránh `@EnableWebMvc` nếu chỉ muốn mở rộng.
12. Viết test happy path, mismatch type, missing segment, regex không match, UUID sai, enum sai, wrong method và not-found resource.

**Ghi nhớ:** `/{id}` cho phép capture chuỗi rồi mới parse; `/{id:[0-9]+}` loại phần không phải chữ số ngay từ routing. Với kiểu `long`, một path chứa chữ cái thường thành 400, còn bị regex loại trước khi parse thường thành 404. Hành vi lỗi là một phần API contract cần tài liệu và test.

## 21. Tài liệu tham khảo

- Spring Framework — Mapping Requests, URI patterns, regex và specificity: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — Type Conversion cho controller arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework — URI Variables và @PathVariable: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/uri-variables.html
- Spring Framework — MVC Path Matching: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/path-matching.html
- Spring Framework — WebFlux annotated request mapping: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Framework — WebFlux Type Conversion: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/typeconversion.html
- Spring Boot — Servlet Web Applications: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- RFC 9110 — HTTP Semantics (400, 404, 405, 406, 415): https://www.rfc-editor.org/rfc/rfc9110
