# Xây dựng REST API MVC với cấu hình máy chủ, validation và lỗi nhất quán

Một REST API Spring Boot chạy được bằng `@RestController` mới là điểm khởi đầu. Để ứng dụng có thể được kiểm thử, triển khai, bảo trì và phục vụ client thật, cần thống nhất đồng thời **cấu hình HTTP server**, **thiết kế resource/HTTP methods**, **DTO và Bean Validation**, **xử lý lỗi có cấu trúc**, **request correlation** và **kiểm thử hợp đồng đầu-cuối**.

Bài thực hành tổng hợp này hướng dẫn xây một **REST API quản lý sản phẩm** với **Java 17+, Spring Boot 3.3.x, Spring MVC/embedded Tomcat, Jakarta Bean Validation và RFC 9457 Problem Details**. Không cần database để chạy lab: repository là bộ nhớ đồng bộ hóa để minh họa HTTP contract và luồng ứng dụng. Từ đó, ta chuyển sang cách áp dụng với database, Spring Security, reverse proxy, Kubernetes và production.

**Kết quả cuối:** API có `GET /api/v1/products`, `POST /api/v1/products`, `GET /api/v1/products/{id}`, `PUT /api/v1/products/{id}`, `DELETE /api/v1/products/{id}`. Lệnh hợp lệ tạo/list/update/xóa; lệnh không hợp lệ tạo cùng kiểu lỗi:

```http
HTTP/1.1 400
Content-Type: application/problem+json
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
```

```json
{
  "type": "about:blank",
  "title": "Validation failed",
  "status": 400,
  "detail": "Dữ liệu đầu vào không hợp lệ.",
  "instance": "/api/v1/products",
  "code": "VALIDATION_FAILED",
  "requestId": "550e8400-e29b-41d4-a716-446655440000",
  "errors": [
    { "field": "name", "rule": "NotBlank" },
    { "field": "price", "rule": "DecimalMin" }
  ]
}
```

Response chỉ **minh họa cấu trúc**, UUID và danh sách violations thay đổi theo request; thứ tự JSON fields không phải hợp đồng bắt buộc. Các `errors` không chứa `rejectedValue` hay nguyên request body để tránh sao chép dữ liệu nhạy cảm vào HTTP error response.

**Điểm quan trọng:** tùy cấu hình, lỗi do container, security filters, reverse proxy hoặc serialization xảy ra bên ngoài MVC advice có thể có representation khác. Bài thực hành thống nhất **những lỗi được Spring MVC/application xử lý** và nêu cách mở rộng chính sách ở các tầng khác, không hứa một `@RestControllerAdvice` kiểm soát mọi byte của mọi response trong hệ thống phân tán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích đường đi của request: Tomcat → Servlet filters → DispatcherServlet → HandlerMapping → controller → service → exception resolver → HTTP response.
2. Chọn status codes hợp lý: 200, 201, 204, 400, 404, 405, 409, 415 và 500.
3. Tạo DTO Java `record` có `@NotBlank`, `@Size`, `@Pattern`, `@DecimalMin`, `@Digits`, `@NotNull`, `@Min` và `@Max`.
4. Kích hoạt validation thực bằng `spring-boot-starter-validation` và `@Valid @RequestBody`.
5. Dùng `ResponseEntity` để điều khiển `Location`, status, body và headers.
6. Phân biệt sai cú pháp JSON, lỗi validation field, lỗi kiểu dữ liệu URL và xung đột nghiệp vụ.
7. Viết `@RestControllerAdvice` kế thừa `ResponseEntityExceptionHandler` để thống nhất Spring MVC errors bằng `ProblemDetail`.
8. Trả mã lỗi máy đọc ổn định như `VALIDATION_FAILED`, `PRODUCT_NOT_FOUND`, `SKU_ALREADY_EXISTS` và `INVALID_JSON`.
9. Thêm request ID phía server bằng `OncePerRequestFilter`, trả `X-Request-ID` và đưa ID vào body lỗi.
10. Cấu hình `server.port`, `server.address`, `server.shutdown`, `server.compression`, `server.error.*` và resource mapping.
11. Phân biệt cấu hình lab loopback với triển khai Docker/Kubernetes và proxy trusted headers.
12. Kiểm thử CRUD, validation, duplicate, malformed JSON, unsupported media type, unsupported method, unknown route bằng `MockMvc`.
13. Kiểm thử HTTP thật qua `RANDOM_PORT` và `TestRestTemplate`.
14. Nhận biết giới hạn của repository in-memory, security, concurrency, idempotency và optimistic locking.
15. Đưa API lên môi trường production với checklist về timeout, observability, data durability và versioning.

## 2. Thiết kế HTTP contract trước khi viết code

API dùng collection resource `/api/v1/products` và individual resource `/api/v1/products/{id}`. Các trạng thái chính:

| Method | URL | Mục đích | Thành công | Lỗi thường gặp |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/products` | Danh sách sản phẩm | 200 và `[]`/JSON array | 500 nội bộ |
| POST | `/api/v1/products` | Tạo sản phẩm | **201** + `Location` + JSON | 400, 409, 415 |
| GET | `/api/v1/products/{id}` | Lấy theo ID | 200 + JSON | 400 ID sai định dạng, 404 không có |
| PUT | `/api/v1/products/{id}` | Thay toàn bộ representation có thể chỉnh | 200 + JSON | 400, 404, 409, 415 |
| DELETE | `/api/v1/products/{id}` | Xóa sản phẩm | **204** không body | 400/404 |
| PATCH | Chưa hỗ trợ | Partial update | Không được triển khai | **405** Method Not Allowed |

Không nhất thiết trả 201 cho PUT thay thế một resource đã tồn tại. Với lab này, PUT **chỉ update ID có sẵn**, trả 404 nếu chưa tồn tại. DELETE chưa có ID trả 404 theo chính sách lab; nhiều API production có thể chọn DELETE idempotent 204 cả khi resource đã mất, nhưng phải tài liệu hóa và giữ nhất quán.

### 2.1. Payload hợp lệ

```json
{
  "name": "Mechanical keyboard",
  "sku": "KEY-001",
  "price": 129.90,
  "stock": 12
}
```

`name` là chuỗi không blank, dài 2..100 ký tự. `sku` là mã 3..32 ký tự, chỉ cho phép chữ hoa ASCII A–Z, số 0–9 và dấu gạch ngang. `price` là số thập phân dương tối thiểu 0.01 và tối đa 10 chữ số phần nguyên, 2 chữ số phần thập phân. `stock` là số nguyên 0..100000.

**API không tin client gửi một ID để tạo sản phẩm.** ID do server cấp và trả trong body `id` cùng `Location`. Đơn giá dùng `BigDecimal` thay vì `double` để tránh sai số nhị phân trong phép tính tiền. Sản phẩm demo không có currency; production phải xác định currency, cách làm tròn, thuế, precision và quy tắc thay đổi giá.

### 2.2. Phân biệt lỗi client và lỗi server

- **400 Bad Request:** JSON sai cú pháp, DTO không hợp lệ, path variable không chuyển được sang `long`.
- **404 Not Found:** product ID hợp lệ về cú pháp nhưng không có; hoặc không có MVC route nào match.
- **405 Method Not Allowed:** URL đã tồn tại nhưng HTTP method không được hỗ trợ; nên giữ header `Allow` nếu framework cung cấp.
- **409 Conflict:** SKU đã tồn tại, vi phạm tính duy nhất ở trạng thái hiện tại.
- **415 Unsupported Media Type:** POST/PUT yêu cầu JSON nhưng client gửi `text/plain`/media type khác.
- **500 Internal Server Error:** unexpected server-side failure; không trả stack trace, SQL, JSON input hoặc exception message thô cho client.

**Không gộp 404 và 400**: `/api/v1/products/abc` có route pattern đúng nhưng `abc` không convert được sang long (400); `/api/v1/products/123` convert được nhưng chưa tồn tại (404).

### 2.3. Một hợp đồng lỗi duy nhất

Sử dụng **RFC 9457 Problem Details** thay vì tự đặt một JSON không chuẩn chỉ có `success:false`. Các fields chuẩn:

| Field | Ý nghĩa |
| --- | --- |
| `type` | URI định danh loại vấn đề; default `about:blank` |
| `title` | Tiêu đề ngắn, có thể ổn định |
| `status` | HTTP status code |
| `detail` | Giải thích ngắn, an toàn để hiển thị |
| `instance` | URI định danh trường hợp cụ thể, có thể là request path |
| `code` | Extension do ứng dụng thêm để client phân nhánh |
| `requestId` | Extension để correlation với server-side logs |
| `errors` | Extension tùy chọn, danh sách field/constraint, không chứa giá trị bị từ chối |

Client nên phân nhánh logic trên **HTTP status + `code`**; không parse văn bản `detail` vì có thể thay đổi/ngôn ngữ hóa. Status nằm trong body không thay thế HTTP status thực. `ProblemDetail` được Spring/Jackson xuất dưới content type `application/problem+json` khi được xử lý đúng.

## 3. Luồng xử lý Spring MVC trong demo

```text
HTTP client
    |
    v
Embedded Tomcat :8080
    |
    v
RequestIdFilter
  tạo UUID + X-Request-ID + request attribute
    |
    v
DispatcherServlet
    |
    +--> HandlerMapping chọn ProductController
    |         |
    |         v
    |    Jackson đọc JSON -> ProductInput record
    |         |
    |         v
    |    Bean Validation (@Valid)
    |         |
    |         v
    |    ProductCatalog (in-memory synchronized)
    |         |
    |         v
    |    ResponseEntity / Jackson serialization
    |
    +--> Nếu lỗi: ExceptionHandlerExceptionResolver
                   |
                   v
          ApiErrorHandler (ProblemDetail)
                   |
                   v
         application/problem+json
    |
    v
HTTP response
```

Filter trong demo **không đọc request body**, không ghi Authorization/Cookie hoặc raw query. Việc phát `X-Request-ID` từ filter giúp client báo lại lỗi với ID ngẫu nhiên do server sinh. DTO validation diễn ra sau khi HTTP JSON đã được chuyển thành Java object thành công. Nếu JSON không parse được, `@Valid` không có cơ hội chạy; lỗi được xử lý tại `handleHttpMessageNotReadable`.

### 3.1. Spring MVC không phải WebFlux

Bài dùng `spring-boot-starter-web` và `jakarta.servlet.*`. Nếu chuyển sang Spring WebFlux sẽ dùng `ServerWebExchange`, `WebExceptionHandler` hoặc `@RestControllerAdvice` cho reactive stack, `WebTestClient` và Reactor semantics; không bê nguyên `OncePerRequestFilter`/`MockMvc` vào WebFlux.

### 3.2. Không tự bắt Exception ở từng controller

Phản ví dụ:

```java
// Phản ví dụ: sinh nhiều response formats khác nhau.
try {
    return service.create(request);
} catch (Exception e) {
    return Map.of("error", e.getMessage());
}
```

Cách này dễ trả 200 cho lỗi vì không đặt status, làm lộ exception message, và khiến các endpoint có schema lỗi khác nhau. Controller nên diễn đạt business action, để `@RestControllerAdvice` chịu trách nhiệm chuyển exceptions thành HTTP errors.

## 4. Tạo project chạy được với Java 17 và Spring Boot 3.3

Dùng [Spring Initializr](https://start.spring.io/) chọn:

- Build: **Gradle, Groovy DSL**;
- Language: **Java**;
- Spring Boot: **3.3.x**, ví dụ `3.3.13`;
- Java: **17+**;
- Dependencies: **Spring Web**, **Validation**, **Spring Boot Actuator**;
- Test: `spring-boot-starter-test`.

Nếu khởi tạo project bằng Initializr, Gradle Wrapper (`gradlew`, `gradlew.bat` và `gradle/wrapper/*`) được tạo. Nếu chỉ copy file Gradle xuống một thư mục rỗng không có wrapper, cần tạo wrapper bằng Gradle tương thích hoặc dùng Initializr.

### 4.1. settings.gradle

```groovy
rootProject.name = 'catalog-api-lab'
```

### 4.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Điểm thường bị quên:** `spring-boot-starter-web` không đủ để bảo đảm Jakarta Bean Validation được thực thi; cần `spring-boot-starter-validation`. Với Boot 3.x, annotation packages là `jakarta.validation.*`, `jakarta.servlet.*`, không dùng `javax.validation.*` từ thời Boot 2.x.

### 4.3. Cấu trúc thư mục

```text
catalog-api-lab/
  settings.gradle
  build.gradle
  gradlew
  gradlew.bat
  gradle/wrapper/...
  src/
    main/
      java/demo/
        CatalogApiApplication.java
        ProductInput.java
        Product.java
        ProductCatalog.java
        ProductController.java
        RequestIdFilter.java
        ApiErrorHandler.java
      resources/
        application.properties
    test/
      java/demo/
        ProductApiMockMvcTest.java
        ProductApiHttpTest.java
```

Mọi Java class trong package `demo`, dưới `CatalogApiApplication` để component scanning thấy controller, service, filter và advice. File name phải trùng tên `public class/record` tương ứng. Không cần database schema vì lưu trong memory. Khi restart, dữ liệu mất; đây là tính chất lab, không phải lỗi cần xử lý bằng `@PreDestroy`.

## 5. Cấu hình HTTP server trong application.properties

File `src/main/resources/application.properties`:

```properties
spring.application.name=catalog-api-lab

# Dành cho local lab. Deploy container cần override bind address.
server.address=127.0.0.1
server.port=8080

# Spring Boot 3.3: graceful HTTP shutdown là opt-in.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

# Gzip chỉ dành cho response đủ kích thước/đúng MIME type.
server.compression.enabled=true
server.compression.min-response-size=2KB

# Hạn chế việc phơi lỗi nội bộ ở fallback /error.
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
server.error.include-exception=false

# Tắt một số log request details tại DEBUG/TRACE.
spring.mvc.log-request-details=false

# Pure REST lab không phục vụ static assets, tránh fallback /**.
spring.web.resources.add-mappings=false

# Dùng @RestControllerAdvice tự viết bên dưới;
# tránh đồng thời Boot auto-register problem handler riêng.
spring.mvc.problemdetails.enabled=false

# Trong lab không tin Forwarded/X-Forwarded headers từ Internet.
server.forward-headers-strategy=none

# Management Actuator chỉ trên loopback lab.
management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=never
```

Đây là **cấu hình local**, không áp nguyên xi vào Kubernetes: `server.address=127.0.0.1` khiến web server chỉ nhận localhost, nên kubelet/Service/Ingress gọi Pod IP sẽ bị connection refused. Khi chạy container, override `SERVER_ADDRESS=0.0.0.0` hoặc dùng profile phù hợp. Quyền truy cập vẫn phải được bảo vệ bởi firewall, network policy và authentication, không phải bằng bind address duy nhất.

### 5.1. Vì sao tắt static mapping trong lab REST?

Trong Spring Boot 3.3, static resources thường được map `/**`. Nếu một API path không khớp controller, request có thể rơi vào `ResourceHttpRequestHandler` và tạo `NoResourceFoundException`, không phải `NoHandlerFoundException`. Với demo thuần JSON API, `spring.web.resources.add-mappings=false` tắt default static handler, làm 404 route dễ thống nhất hơn trong MVC advice.

Nếu ứng dụng có UI hoặc assets, **không** tắt static một cách máy móc. Thay vào đó cấu hình `spring.mvc.static-path-pattern=/assets/**`, static locations, và xử lý cả `NoHandlerFoundException` lẫn `NoResourceFoundException`. Không đưa private files/uploads vào thư mục static public.

### 5.2. Vì sao spring.mvc.problemdetails.enabled=false nhưng vẫn dùng ProblemDetail?

Property trên bật **Boot auto-configured handler** cho Problem Details của MVC exceptions. Trong bài ta **tự tạo** `ApiErrorHandler extends ResponseEntityExceptionHandler` và trả `ProblemDetail` qua `@RestControllerAdvice`, nên không cần Boot tạo một advice khác. Spring MVC/Jackson vẫn hỗ trợ RFC 9457 khi ta trả `ProblemDetail` bằng code. Nếu dự án chọn bật Boot auto handler, cần xem thứ tự `@Order` để advice tùy chỉnh không bị handler khác xử lý trước.

### 5.3. Cấu hình server khác business logic

- `server.port`: cổng TCP listener; không quyết định path nào đúng.
- `server.address`: network interface bind; local loopback và container Pod IP khác nhau.
- `server.servlet.context-path`: prefix cho toàn servlet application nếu cấu hình; đừng nhầm với `@RequestMapping`.
- `server.compression.*`: điều kiện cho response compression; client phải gửi Accept-Encoding phù hợp, MIME và kích thước đủ.
- `server.shutdown=graceful`: cơ hội drain HTTP requests khi context đóng; không đảm bảo hoàn tất khi SIGKILL hoặc hết Pod grace.
- `server.error.*`: giới hạn fallback error details; không thay custom advice và không che raw exception messages do code tự log/return.
- `server.forward-headers-strategy`: quyết định xử lý Forwarded/X-Forwarded-* từ reverse proxy, phải có trust boundary rõ.
- `management.*`: Actuator health/metrics, không phải business routes.

## 6. CatalogApiApplication.java — Spring Boot entry point

File `src/main/java/demo/CatalogApiApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApiApplication.class, args);
    }
}
```

`@SpringBootApplication` bao gồm auto-configuration, component scan và cấu hình Spring Boot app. Đặt lớp ở root package `demo` giúp tự quét các classes bên dưới. Không phải tự tạo `DispatcherServlet` hoặc `TomcatServletWebServerFactory` nếu dùng defaults.

## 7. ProductInput.java — validation ở ranh giới HTTP

File `src/main/java/demo/ProductInput.java`:

```java
package demo;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ProductInput(

    @NotBlank
    @Size(min = 2, max = 100)
    String name,

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,32}")
    String sku,

    @NotNull
    @DecimalMin("0.01")
    @Digits(integer = 10, fraction = 2)
    BigDecimal price,

    @NotNull
    @Min(0)
    @Max(100000)
    Integer stock
) {
}
```

### 7.1. Ý nghĩa từng ràng buộc

- `@NotBlank`: String phải khác null và có ký tự không phải whitespace.
- `@Size(min=2,max=100)`: giới hạn độ dài chuỗi name. `@Size` **không tự kiểm null**; vì thế kết hợp `@NotBlank`.
- `@Pattern`: áp dụng cho String, chỉ nhận SKU theo regex; `@NotBlank` xử lý null/blank.
- `@NotNull`: bắt buộc có price/stock; dùng wrapper `Integer` thay `int` để phân biệt missing/null với 0.
- `@DecimalMin("0.01")`: giá trị BigDecimal phải ≥ 0.01.
- `@Digits(integer=10,fraction=2)`: độ dài phần nguyên và thập phân được giới hạn.
- `@Min(0)`/`@Max(100000)`: stock nằm trong khoảng.
- `record`: tạo constructor/accessors/equals/hashCode/toString dựa trên components, Jackson của Boot 3.3 hỗ trợ bind JSON tới record.

**Không log `ProductInput.toString()`** trong production: record in cả giá trị request. Với DTO có email/token/PII, log raw payload hoặc rejectedValue có thể gây lộ dữ liệu. Advice dưới đây chỉ trả **field name + constraint code** được server xác định.

### 7.2. Khi validation chạy?

Trong controller, `@Valid @RequestBody ProductInput input` yêu cầu Spring áp Jakarta Bean Validation sau khi Jackson parse JSON. Nếu vi phạm, Spring MVC phát sinh `MethodArgumentNotValidException`. Nếu JSON sai cú pháp, không convert được BigDecimal hoặc type mismatch trong JSON, xảy ra `HttpMessageNotReadableException` trước validation.

**Không có `spring-boot-starter-validation`**, dự án có thể thiếu validation provider hoặc annotation classes tùy dependency tree. Không chỉ nhìn thấy `@Valid` trong source rồi kết luận API đã validate.

### 7.3. DTO validation khác business rules

Một SKU syntactically hợp lệ có thể đã tồn tại trong catalog. `@Pattern` không thể biết trạng thái repository; uniqueness phải kiểm tra ở service/DB. Ngược lại, lỗi `stock=-5` là shape/range của request và được Bean Validation phát hiện trước service. Tách hai loại giúp lỗi HTTP 400 vs 409 có ý nghĩa.

## 8. Product.java — mô hình trả về

File `src/main/java/demo/Product.java`:

```java
package demo;

import java.math.BigDecimal;

public record Product(
        long id,
        String name,
        String sku,
        BigDecimal price,
        int stock
) {
}
```

Trong demo, domain model cũng là JSON response model vì tất cả fields đều công khai. Với production có cost price, internal notes, supplier secrets hoặc entity relationships, phải dùng **response DTO** riêng để tránh lộ fields hoặc JPA lazy-loading/serialization cycles. Không trực tiếp expose entity JPA chỉ vì code ngắn.

JSON success ví dụ:

```json
{
  "id": 1,
  "name": "Mechanical keyboard",
  "sku": "KEY-001",
  "price": 129.90,
  "stock": 12
}
```

Jackson có thể xuất BigDecimal theo representation số phù hợp; client không nên phụ thuộc format số có luôn giữ hai chữ số thập phân. Nếu API có contract tiền tệ nghiêm ngặt, hãy xác định rõ encoding/scaling, currency và test serialization.

## 9. ProductCatalog.java — service và repository giả

File `src/main/java/demo/ProductCatalog.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

@Service
public class ProductCatalog {

    private final Map<Long, Product> products =
            new LinkedHashMap<>();

    private long nextId = 1;

    public static final class MissingProduct
            extends RuntimeException {
    }

    public static final class DuplicateSku
            extends RuntimeException {
    }

    public synchronized List<Product> list() {
        return new ArrayList<>(products.values());
    }

    public synchronized Product get(long id) {
        Product found = products.get(id);

        if (found == null) {
            throw new MissingProduct();
        }

        return found;
    }

    public synchronized Product create(ProductInput input) {
        ensureSkuAvailable(input.sku(), null);

        long id = nextId++;

        Product created = new Product(
                id,
                input.name(),
                input.sku(),
                input.price(),
                input.stock()
        );

        products.put(id, created);
        return created;
    }

    public synchronized Product replace(
            long id, ProductInput input) {

        if (!products.containsKey(id)) {
            throw new MissingProduct();
        }

        ensureSkuAvailable(input.sku(), id);

        Product updated = new Product(
                id,
                input.name(),
                input.sku(),
                input.price(),
                input.stock()
        );

        products.put(id, updated);
        return updated;
    }

    public synchronized void delete(long id) {
        if (products.remove(id) == null) {
            throw new MissingProduct();
        }
    }

    private void ensureSkuAvailable(
            String sku, Long currentId) {

        boolean exists = products.values().stream()
                .anyMatch(product ->
                    product.sku().equals(sku)
                    && (currentId == null
                        || product.id() != currentId));

        if (exists) {
            throw new DuplicateSku();
        }
    }
}
```

### 9.1. Vì sao có synchronized?

`LinkedHashMap` không thread-safe. Các public methods dùng `synchronized` để việc kiểm tra SKU rồi insert/update xảy ra trong cùng critical section, tránh hai request concurrent cùng thông qua check uniqueness ở **một instance demo**. `synchronized` trên instance service đơn giản nhưng giới hạn throughput; nó không thay transaction hay unique constraint ở nhiều replicas.

### 9.2. Vì sao throw domain exception?

`MissingProduct` và `DuplicateSku` là tín hiệu business thuần, không phụ thuộc HTTP. Controller không tự sinh `ResponseEntity` trong service. `ApiErrorHandler` sẽ ánh xạ:

- `MissingProduct` → HTTP 404 + `PRODUCT_NOT_FOUND`.
- `DuplicateSku` → HTTP 409 + `SKU_ALREADY_EXISTS`.

Dù Java exceptions không có message chi tiết, client vẫn nhận code/title/detail phù hợp. Không nhúng raw SKU/user-supplied data vào exception message chỉ để debug.

### 9.3. Những gì lab cố ý chưa giải quyết

- Data **mất khi restart** vì nằm trong heap.
- Nhiều Pod có bản đồ products khác nhau; không có shared state.
- Không có transaction, database unique index, optimistic locking, soft delete, audit hay authentication.
- SKU uniqueness là case-sensitive theo regex chữ hoa; production phải quyết định normalize Unicode/case/whitespace.
- ID long tăng dần, có thể suy đoán; authorization vẫn bắt buộc.
- Giá và stock không bảo đảm consistency dưới distributed concurrency.
- `synchronized` không làm một cluster đúng về dữ liệu; production dùng database/constraints.

Đây là **lab HTTP contract**, không phải catalog repository cho sản phẩm thật.

## 10. ProductController.java — REST endpoints

File `src/main/java/demo/ProductController.java`:

```java
package demo;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {

    private final ProductCatalog catalog;

    public ProductController(ProductCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping
    public List<Product> list() {
        return catalog.list();
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Product> create(
            @Valid @RequestBody ProductInput input) {

        Product created = catalog.create(input);

        URI location = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .path("/{id}")
                .buildAndExpand(created.id())
                .toUri();

        return ResponseEntity.created(location)
                .body(created);
    }

    @GetMapping("/{id}")
    public Product get(@PathVariable("id") long id) {
        return catalog.get(id);
    }

    @PutMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Product replace(
            @PathVariable("id") long id,
            @Valid @RequestBody ProductInput input) {

        return catalog.replace(id, input);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(
            @PathVariable("id") long id) {

        catalog.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

### 10.1. Vì sao dùng constructor injection?

`ProductCatalog` được Spring tạo bean `@Service` rồi truyền vào controller qua constructor. Điều này dễ unit test, không dựa vào static globals hoặc field injection khó kiểm soát. Với một constructor, Spring không yêu cầu `@Autowired` tường minh.

### 10.2. URL mapping và HTTP methods

- `@RequestMapping("/api/v1/products")` xác định collection prefix.
- `@GetMapping` không có thêm path xử lý collection.
- `@GetMapping("/{id}")` dùng `@PathVariable` chuyển URL segment thành long.
- `@PostMapping(consumes="application/json")` chỉ cho phép JSON request body; media type sai được Spring MVC xử lý thành 415.
- `@Valid` chạy validation cho create/replace. Không đặt `@Valid` ở service rồi kỳ vọng HTTP request tự validate.
- `@DeleteMapping` dùng 204 với empty body, không trả một string `"deleted"` kèm 204.

### 10.3. Vì sao Location sinh từ current request?

Theo HTTP semantics, 201 Created nên chỉ ra resource mới bằng `Location`. `ServletUriComponentsBuilder.fromCurrentRequestUri()` dựa trên request URL hiện tại, thêm segment ID, tránh hardcode `http://localhost:8080` trong controller. Nếu bật context path hoặc reverse proxy đã được **tin cậy và normalize**, nó giúp phản ánh public request URI tương ứng.

**Bảo mật:** đừng tin trực tiếp `X-Forwarded-Host`, `X-Forwarded-Proto` từ client Internet chưa qua trusted proxy. Nếu forward headers bị spoof, Location/redirect có thể bị thao túng (host header poisoning). Lab đặt `server.forward-headers-strategy=none`. Production phải cấu hình proxy strip/overwrite headers và ứng dụng tin đúng hop.

### 10.4. PUT khác PATCH

PUT trong demo là **replace toàn bộ các fields có thể chỉnh**: client phải gửi đủ name, sku, price, stock, tất cả validate lại. Nếu chỉ muốn update một field, `PATCH` cần contract riêng và validation sau merge, không nhận JSON thiếu fields rồi dùng PUT để thay nửa vời. Không triển khai PATCH trong lab; gọi nó sẽ thấy 405.

### 10.5. Không trộn HTTP responsibilities vào service

Controller tạo `Location` và chọn `201`; service kiểm tra uniqueness và quản lý state; advice chuyển exception thành status/body. Sự tách lớp làm tests rõ ràng: unit test business rules, MockMvc test HTTP contract, live test embedded server.

## 11. RequestIdFilter.java — request correlation an toàn

File `src/main/java/demo/RequestIdFilter.java`:

```java
package demo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String REQUEST_ID_ATTR =
            "demo.requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();

        request.setAttribute(REQUEST_ID_ATTR, requestId);
        response.setHeader("X-Request-ID", requestId);

        chain.doFilter(request, response);
    }
}
```

### 11.1. Tại sao ID tạo ở server?

Header `X-Request-ID` từ client có thể bị giả, quá dài, có control chars hoặc chứa PII. Trong demo, filter **không dùng** header client gửi tới mà luôn tạo UUID mới. Khi có trusted gateway trong production, có thể propagate ID đã được gateway generate/normalize với allowlist length/charset; phải có hợp đồng rõ ai là nguồn đáng tin.

### 11.2. Vì sao không đọc body trong filter?

Filter chỉ đặt request attribute/response header. Nó không gọi `getInputStream()`, `getReader()` hay `getParameterMap()` nên không vô tình tiêu thụ JSON trước `@RequestBody`. Không log raw Authorization, Cookie, query string hoặc product input. Việc đo metrics/HTTP traces có thể dùng Actuator/Micrometer thay vì tự serialize body.

### 11.3. Giới hạn

`OncePerRequestFilter` có dispatch semantics; với async/error dispatch, response wrapper/security filters có thể chạy khác. Header có thể đã committed, container errors/proxy-generated errors có thể không đi qua filter. Vì thế không hứa **mọi** HTTP error ngoài app đều có request ID. Muốn correlation toàn tuyến, cần gateway-generated trace/request IDs và logging policy thống nhất.

## 12. ApiErrorHandler.java — lỗi nhất quán kiểu ProblemDetail

Đây là phần cốt lõi của bài. Spring Framework 6.1 có `ResponseEntityExceptionHandler` để xử lý các MVC exceptions thông thường: JSON parse, validation, thiếu parameter, 405, 415, type mismatch, 404 và nhiều lỗi khác. Ta kế thừa nó, override một số trường hợp cần mã lỗi rõ, rồi dùng `createResponseEntity` để bổ sung `code` và `requestId` cho tất cả những lỗi đi qua advice.

File `src/main/java/demo/ApiErrorHandler.java`:

```java
package demo;

import java.util.Comparator;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.beans.TypeMismatchException;
import org.springframework.web.ErrorResponse;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiErrorHandler
        extends ResponseEntityExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ApiErrorHandler.class);

    public record FieldViolation(String field, String rule) {
    }

    @ExceptionHandler(ProductCatalog.MissingProduct.class)
    public ResponseEntity<Object> missing(
            ProductCatalog.MissingProduct exception,
            WebRequest request) {

        return problem(
                HttpStatus.NOT_FOUND,
                "PRODUCT_NOT_FOUND",
                "Product not found",
                "Sản phẩm không tồn tại.",
                request
        );
    }

    @ExceptionHandler(ProductCatalog.DuplicateSku.class)
    public ResponseEntity<Object> duplicate(
            ProductCatalog.DuplicateSku exception,
            WebRequest request) {

        return problem(
                HttpStatus.CONFLICT,
                "SKU_ALREADY_EXISTS",
                "Duplicate SKU",
                "Mã SKU đã được sử dụng.",
                request
        );
    }

    @ExceptionHandler(RuntimeException.class)
    public ResponseEntity<Object> unexpected(
            RuntimeException exception,
            WebRequest request) {

        // Không log payload, rejectedValue hoặc exception message.
        log.error(
                "Unhandled type={} requestId={}",
                exception.getClass().getSimpleName(),
                requestId(request)
        );

        return problem(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "Internal server error",
                "Đã xảy ra lỗi nội bộ.",
                request
        );
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = detail(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED",
                "Validation failed",
                "Dữ liệu đầu vào không hợp lệ."
        );

        List<FieldViolation> errors =
                exception.getBindingResult()
                        .getFieldErrors()
                        .stream()
                        .map(error -> new FieldViolation(
                                error.getField(),
                                error.getCode() == null
                                        ? "Invalid"
                                        : error.getCode()
                        ))
                        .distinct()
                        .sorted(
                            Comparator.comparing(
                                    FieldViolation::field)
                                .thenComparing(
                                    FieldViolation::rule)
                        )
                        .toList();

        body.setProperty("errors", errors);

        return handleExceptionInternal(
                exception, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = detail(
                HttpStatus.BAD_REQUEST,
                "INVALID_JSON",
                "Invalid JSON",
                "JSON sai cú pháp hoặc không thể chuyển kiểu."
        );

        return handleExceptionInternal(
                exception, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = detail(
                HttpStatus.BAD_REQUEST,
                "INVALID_PARAMETER",
                "Invalid parameter",
                "Tham số URL hoặc query không đúng kiểu dữ liệu."
        );

        return handleExceptionInternal(
                exception, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleNoHandlerFoundException(
            NoHandlerFoundException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = detail(
                HttpStatus.NOT_FOUND,
                "ROUTE_NOT_FOUND",
                "Route not found",
                "Không có API route tương ứng."
        );

        return handleExceptionInternal(
                exception, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleNoResourceFoundException(
            NoResourceFoundException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = detail(
                HttpStatus.NOT_FOUND,
                "ROUTE_NOT_FOUND",
                "Resource not found",
                "Không có API hoặc tài nguyên tương ứng."
        );

        return handleExceptionInternal(
                exception, body, headers, status, request);
    }

    private ResponseEntity<Object> problem(
            HttpStatus status,
            String code,
            String title,
            String message,
            WebRequest request) {

        ProblemDetail body = detail(
                status, code, title, message);

        return createResponseEntity(
                body, new HttpHeaders(), status, request);
    }

    private static ProblemDetail detail(
            HttpStatusCode status,
            String code,
            String title,
            String message) {

        ProblemDetail body =
                ProblemDetail.forStatusAndDetail(
                        status, message);

        body.setTitle(title);
        body.setProperty("code", code);
        return body;
    }

    private static String requestId(WebRequest request) {
        Object value = request.getAttribute(
                RequestIdFilter.REQUEST_ID_ATTR,
                WebRequest.SCOPE_REQUEST
        );

        return value instanceof String id
                ? id : "unavailable";
    }

    @Override
    protected ResponseEntity<Object> createResponseEntity(
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem =
                body instanceof ProblemDetail existing
                        ? existing
                        : ProblemDetail.forStatus(status);

        if (problem.getProperties() == null
                || !problem.getProperties()
                           .containsKey("code")) {

            problem.setProperty(
                    "code", "HTTP_" + status.value());

            problem.setTitle(
                    status.is5xxServerError()
                            ? "Internal server error"
                            : "HTTP request failed");

            problem.setDetail(
                    status.is5xxServerError()
                            ? "Đã xảy ra lỗi nội bộ."
                            : "Không thể xử lý yêu cầu HTTP.");
        }

        problem.setProperty(
                "requestId", requestId(request));

        HttpHeaders outputHeaders = new HttpHeaders();
        outputHeaders.addAll(headers);
        outputHeaders.setContentType(
                MediaType.parseMediaType(
                        "application/problem+json"));

        return super.createResponseEntity(
                problem, outputHeaders, status, request);
    }
}
```

### 12.1. Lưu ý về imports và framework version

Các hook signatures ở trên là của **Spring Framework 6.1 / Spring Boot 3.3**, đặc biệt:

```java
handleMethodArgumentNotValid(
    MethodArgumentNotValidException,
    HttpHeaders, HttpStatusCode, WebRequest)

createResponseEntity(
    Object, HttpHeaders, HttpStatusCode, WebRequest)
```

Không copy mù các chữ ký cũ từ Spring 5/Boot 2 có `HttpStatus` thay vì `HttpStatusCode`. Dùng `@Override` giúp compiler báo sai version/signature ngay.

Trong listing, `org.springframework.web.ErrorResponse` được import để dễ đối chiếu với Spring MVC RFC 9457 APIs; nó không được gọi trực tiếp. Java cho phép unused imports không gây compilation failure trong cấu hình Gradle Java mặc định. Nếu dùng Checkstyle/Spotless, có thể loại bỏ unused import này theo style của dự án.

### 12.2. Cách một lỗi đi qua advice

**Dữ liệu lỗi validation**:

1. Jackson parse JSON thành `ProductInput`.
2. `@Valid` áp constraints và tạo `MethodArgumentNotValidException`.
3. `handleMethodArgumentNotValid` tạo ProblemDetail code `VALIDATION_FAILED`.
4. `errors` chứa field name + constraint code, không chứa value.
5. `handleExceptionInternal` gọi `createResponseEntity`.
6. `createResponseEntity` gắn `requestId` và content type, giữ HTTP status 400.

**Lỗi domain**: service ném `MissingProduct`/`DuplicateSku`, advice tạo ProblemDetail 404/409 và cùng `requestId`.

**Lỗi framework**: method không hỗ trợ 405 hoặc content type sai 415 được `ResponseEntityExceptionHandler` xử lý; `createResponseEntity` bổ sung code mặc định `HTTP_405`/`HTTP_415` và giữ các headers thích hợp từ framework (ví dụ `Allow` cho 405).

**Lỗi JSON parse**: body có dấu ngoặc sai hoặc price không thể convert → code `INVALID_JSON`, 400; không trả chuỗi Jackson exception thô.

### 12.3. Vì sao không trả rejectedValue?

Các lỗi như email không hợp lệ, password quá ngắn hoặc mã OTP sai có thể khiến BindingResult chứa giá trị client gửi. Việc serialize `exception.getBindingResult().getAllErrors()` hoặc `error.getRejectedValue()` ra HTTP response hay logs có thể lộ PII. Trong demo, `FieldViolation` chỉ chứa `field` và `rule`. Constraint codes như `NotBlank`, `Size`, `Pattern` do server định nghĩa, không phải raw user input.

### 12.4. Tại sao lại có mã HTTP_415 thay vì một code riêng?

Các lỗi framework không được tùy biến riêng trong demo dùng mã `HTTP_<status>`. Client có thể xử lý chung theo status; với API lớn nên định nghĩa taxonomy rõ hơn, ví dụ `UNSUPPORTED_MEDIA_TYPE`, `METHOD_NOT_ALLOWED`, `MISSING_PARAMETER`. **Đừng dùng text từ exception làm error code**, vì nó có thể chứa dữ liệu nhạy cảm và đổi theo version/locale.

### 12.5. Lỗi không được advice bao trọn 100%

`@RestControllerAdvice` xử lý lỗi đi qua Spring MVC exception resolvers trong phạm vi handler tương ứng. Nó không tự kiểm soát:

- Kết nối bị Tomcat từ chối trước khi tới DispatcherServlet;
- TLS handshake failure hoặc request-line/header parse errors;
- Spring Security authentication/authorization failures ở FilterChain trước controller;
- NGINX 413/502/504, CDN/WAF 403;
- Response đã commit, lỗi mạng khi streaming;
- JSON serialization failed sau khi headers/body đã gửi một phần;
- Một `/error` fallback sinh từ dispatch ngoài advice;
- Client disconnect hoặc JVM SIGKILL.

Để thống nhất lỗi toàn tuyến, phải có policies tương ứng: Spring Security `AuthenticationEntryPoint`/`AccessDeniedHandler`, gateway error mapping, correlation ID, container configuration và tests cho từng tầng. **Đừng thêm `@ExceptionHandler(Exception.class)` rồi hứa tất cả 5xx đều có JSON hoàn chỉnh**.

## 13. Khởi chạy ứng dụng

Từ project có Gradle Wrapper:

```bash
./gradlew clean test bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test bootRun
```

Nếu muốn đóng gói trước:

```bash
./gradlew bootJar
java -jar build/libs/catalog-api-lab-0.0.1-SNAPSHOT.jar
```

Spring Boot phụ thuộc classpath và Gradle BOM, không thể compile toàn ứng dụng chỉ với `javac CatalogApiApplication.java` trên JDK trần. `./gradlew` chỉ tồn tại khi Initializr/Gradle Wrapper đã được tạo. Dependency tải từ Maven Central cần kết nối mạng hoặc local cache.

### 13.1. Trạng thái khởi đầu

`GET` collection khi mới khởi động:

```bash
curl -i http://127.0.0.1:8080/api/v1/products
```

HTTP 200 với JSON:

```json
[]
```

Nếu app đang chạy từ trước hoặc tests cùng context đã thêm items, array có thể không rỗng. Lab này không có persistent DB, nên chạy JAR mới sẽ khởi tạo map rỗng.

### 13.2. Tạo sản phẩm

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/v1/products' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Mechanical keyboard","sku":"KEY-001","price":129.90,"stock":12}'
```

Response minh họa trên một app mới chưa có products:

```http
HTTP/1.1 201
Content-Type: application/json
Location: http://127.0.0.1:8080/api/v1/products/1
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000

{"id":1,"name":"Mechanical keyboard","sku":"KEY-001","price":129.90,"stock":12}
```

Thứ tự headers, serialization scale, UUID và ID phụ thuộc trạng thái thực tế. **Location phải là URL của resource được tạo**, không phải URL collection. `201 Created` không đồng nghĩa mọi database transaction production đã được commit; đó là hợp đồng server công bố tạo resource thành công.

### 13.3. Đọc, cập nhật, xóa

Dùng ID thật nhận từ bước tạo:

```bash
curl -i http://127.0.0.1:8080/api/v1/products/1

curl -i -X PUT \
  http://127.0.0.1:8080/api/v1/products/1 \
  -H 'Content-Type: application/json' \
  -d '{"name":"Mechanical keyboard V2","sku":"KEY-001","price":139.50,"stock":10}'

curl -i -X DELETE \
  http://127.0.0.1:8080/api/v1/products/1

curl -i http://127.0.0.1:8080/api/v1/products/1
```

Đây là chuỗi **minh họa** với ID 1 khi app mới tạo đúng sản phẩm đầu tiên; nếu response POST cấp ID khác, thay mọi số 1 bằng ID thực. GET trước DELETE trả 200, PUT trả 200 body updated, DELETE trả 204 empty, GET sau DELETE trả 404 `PRODUCT_NOT_FOUND`.

### 13.4. Kiểm tra duplicate SKU: 409

Nếu `KEY-001` vẫn tồn tại:

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/products \
  -H 'Content-Type: application/json' \
  -d '{"name":"Another keyboard","sku":"KEY-001","price":99.00,"stock":5}'
```

Response:

```http
HTTP/1.1 409
Content-Type: application/problem+json

{"type":"about:blank","title":"Duplicate SKU","status":409,"detail":"Mã SKU đã được sử dụng.","code":"SKU_ALREADY_EXISTS","requestId":"..."}
```

Dấu `...` ở ví dụ JSON là ký hiệu mô tả request ID động, **không phải JSON response chính xác**; header/body thực có UUID và có thể thêm `instance`. Nếu đã DELETE sản phẩm có SKU này, POST mới sẽ thành công; đó là đúng business state.

### 13.5. Validation 400

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/products \
  -H 'Content-Type: application/json' \
  -d '{"name":" ","sku":"lowercase","price":0,"stock":-1}'
```

Ví dụ có các violations như `NotBlank`/`Size`, `Pattern`, `DecimalMin`, `Min`. Response HTTP 400 ProblemDetail code `VALIDATION_FAILED`. **Không assert cứng thứ tự tất cả lỗi trong response** vì nhiều constraints có thể cùng fail và iteration/validation provider có thể thay đổi thứ tự.

### 13.6. JSON malformed: 400

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/products \
  -H 'Content-Type: application/json' \
  --data '{'
```

Kết quả code `INVALID_JSON` với HTTP 400. Không cần parse stack trace từ body để tìm loại lỗi; dùng `code` và requestId.

### 13.7. Unsupported Media Type: 415

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/products \
  -H 'Content-Type: text/plain' \
  --data 'this is not json'
```

Do `@PostMapping(consumes="application/json")`, Spring MVC trả HTTP 415. Advice tạo code mặc định `HTTP_415`, giữ `application/problem+json` nếu response nằm trong MVC pipeline.

### 13.8. Unsupported Method: 405

```bash
curl -i -X PATCH \
  http://127.0.0.1:8080/api/v1/products/1 \
  -H 'Content-Type: application/json' \
  -d '{"stock":9}'
```

Demo không khai báo `@PatchMapping`. Framework phản hồi 405 `HTTP_405`; `Allow` header thể hiện methods được phép khi được framework cung cấp. Không tự biến mọi lỗi HTTP method thành 404 vì client cần biết route tồn tại nhưng method sai.

### 13.9. Unknown route 404 khác ID không tồn tại

```bash
curl -i http://127.0.0.1:8080/api/v1/unknown

curl -i http://127.0.0.1:8080/api/v1/products/99999
```

Cả hai là HTTP 404 nhưng có thể phân biệt qua `code`: `ROUTE_NOT_FOUND` và `PRODUCT_NOT_FOUND`. Với lab đã tắt static resource mapping, NoHandlerFound đi qua advice. Nếu bật lại static handler `/**`, cần hỗ trợ `NoResourceFoundException` (advice đã có override) và test lại để không lộ trang HTML/404 khác.

### 13.10. Path variable sai kiểu: 400

```bash
curl -i http://127.0.0.1:8080/api/v1/products/abc
```

String `abc` không chuyển thành `long` được; Spring MVC xử lý type mismatch, advice trả `INVALID_PARAMETER` HTTP 400. Không nhầm đây là product ID không tìm thấy 404.

## 14. MockMvc integration tests kiểm tra contract

`MockMvc` chạy trên mock Servlet objects với Spring MVC context; không dùng TCP hoặc embedded server networking thực. Nó rất phù hợp kiểm tra JSON binding, validation, status, exception resolver, headers và controller/service. Khi cấu hình server/proxy/compression/connection timeouts cần bổ sung live HTTP tests.

Tạo file `src/test/java/demo/ProductApiMockMvcTest.java`:

```java
package demo;

import java.util.Locale;
import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductApiMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper json;

    private String sku() {
        return "SKU-"
                + UUID.randomUUID().toString()
                      .substring(0, 8)
                      .toUpperCase(Locale.ROOT);
    }

    private String body(String value) {
        return """
            {
              "name":"Mechanical keyboard",
              "sku":"%s",
              "price":129.90,
              "stock":12
            }
            """.formatted(value);
    }

    @Test
    void createReadReplaceDeleteWork() throws Exception {
        String sku = sku();

        MvcResult created = mvc.perform(
                post("/api/v1/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body(sku)))
            .andExpect(status().isCreated())
            .andExpect(header().exists(HttpHeaders.LOCATION))
            .andExpect(header().exists("X-Request-ID"))
            .andExpect(jsonPath("$.sku").value(sku))
            .andReturn();

        JsonNode result = json.readTree(
                created.getResponse().getContentAsString());

        long id = result.get("id").asLong();
        assertThat(id).isPositive();

        mvc.perform(get("/api/v1/products/{id}", id))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(id))
            .andExpect(jsonPath("$.sku").value(sku));

        String changed = """
            {
              "name":"Mechanical keyboard V2",
              "sku":"%s",
              "price":139.50,
              "stock":10
            }
            """.formatted(sku);

        mvc.perform(put("/api/v1/products/{id}", id)
                .contentType(MediaType.APPLICATION_JSON)
                .content(changed))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.stock").value(10));

        mvc.perform(delete("/api/v1/products/{id}", id))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/v1/products/{id}", id))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                    .value("PRODUCT_NOT_FOUND"));
    }

    @Test
    void validationReturnsProblemWithoutInputValues()
            throws Exception {

        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name":"",
                      "sku":"bad-sku",
                      "price":0,
                      "stock":-1
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(header().string(
                    HttpHeaders.CONTENT_TYPE,
                    containsString("application/problem+json")))
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.requestId")
                    .isNotEmpty())
            .andExpect(jsonPath("$.errors").isArray());
    }

    @Test
    void duplicateSkuIs409() throws Exception {
        String sku = sku();

        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body(sku)))
            .andExpect(status().isCreated());

        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body(sku)))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code")
                    .value("SKU_ALREADY_EXISTS"));
    }

    @Test
    void malformedJsonUsesStableCode() throws Exception {
        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_JSON"));
    }

    @Test
    void unsupportedContentTypeIs415() throws Exception {
        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.TEXT_PLAIN)
                .content("plain text"))
            .andExpect(status().isUnsupportedMediaType())
            .andExpect(jsonPath("$.code").value("HTTP_415"));
    }

    @Test
    void unsupportedHttpMethodIs405() throws Exception {
        mvc.perform(patch("/api/v1/products/1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"stock\":2}"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().exists(HttpHeaders.ALLOW))
            .andExpect(jsonPath("$.code").value("HTTP_405"));
    }

    @Test
    void unknownRouteAndBadIdAreDifferent()
            throws Exception {

        mvc.perform(get("/api/v1/unknown"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                    .value("ROUTE_NOT_FOUND"));

        mvc.perform(get("/api/v1/products/abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_PARAMETER"));
    }
}
```

### 14.1. Những gì test kiểm chứng

- **201 + Location + X-Request-ID**: POST tạo resource và trả headers mong đợi.
- **200 read/update**: GET theo ID, PUT thay đầy đủ và JSON vẫn bind đúng.
- **204 delete**: resource biến mất, GET sau xóa trả 404.
- **400 validation**: `@Valid` hoạt động, schema ProblemDetail có `code`/`errors`.
- **409 duplicate**: uniqueness service thành business conflict.
- **400 invalid JSON**: parser lỗi được map sang `INVALID_JSON`.
- **415**: consumes mapping hoạt động.
- **405 + Allow**: method mapping và headers framework được giữ.
- **404 unknown route** vs **400 nonnumeric id**: tránh trộn nguyên nhân lỗi.
- **Request ID**: filter được đăng ký và chạy trong MockMvc.

### 14.2. Tránh test phụ thuộc thứ tự

Tests tạo SKU có UUID để không trùng giữa methods. Không assert ID phải là 1, không giả định tests chạy theo thứ tự, không dùng tên SKU cố định qua cả suite. Vì `ProductCatalog` giữ state trong Spring context giữa tests, cách này tránh flakiness khi JUnit thay order. Nhưng nếu tests chạy parallel và cùng thay đổi một object hoặc port, vẫn cần quản lý isolation.

### 14.3. Kiểm thử không phản chiếu rejectedValue

Bài test validation kiểm schema cơ bản; để kiểm tra leak, có thể bổ sung:

```java
MvcResult failed = mvc.perform(
        post("/api/v1/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"name":"SECRET-SENTINEL",
                 "sku":"x","price":0,"stock":-1}
                """))
    .andExpect(status().isBadRequest())
    .andReturn();

assertThat(failed.getResponse().getContentAsString())
    .doesNotContain("SECRET-SENTINEL");
```

Đây là **snippet mở rộng** chèn trong một test method có `mvc` và `assertThat` imports. Nó chứng minh response không echo giá trị test sentinel; test không phát hiện được logging ở reverse proxy, APM hoặc server khác. Khi dùng Bean Validation message templates chứa giá trị input, tránh trả raw `getDefaultMessage()` mà không review.

### 14.4. Không coi MockMvc là kiểm thử Tomcat networking

MockMvc không kiểm thử thật: cổng 8080 bind, TLS, thread pool, HTTP header size, compression negotiation, reverse proxy forwarding, container errors trước DispatcherServlet, startup/shutdown socket behavior hoặc Kubernetes probes. Cần thêm `RANDOM_PORT` và deployment tests.

## 15. HTTP integration test với embedded server thật

`@SpringBootTest(webEnvironment=RANDOM_PORT)` khởi động Tomcat trên port ngẫu nhiên. `TestRestTemplate` dùng HTTP thật và không ném exception chỉ vì response HTTP 4xx/5xx, phù hợp test error contract.

Tạo `src/test/java/demo/ProductApiHttpTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ProductApiHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    @Test
    void validationIsProblemJsonOverRealHttp() {

        String url = "http://127.0.0.1:"
                + port + "/api/v1/products";

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<String> request = new HttpEntity<>(
            """
            {
              "name":" ",
              "sku":"invalid",
              "price":0,
              "stock":-1
            }
            """,
            headers
        );

        ResponseEntity<String> response =
                client.exchange(
                    url,
                    HttpMethod.POST,
                    request,
                    String.class
                );

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);

        assertThat(response.getHeaders()
                .getContentType())
            .isNotNull()
            .satisfies(type ->
                assertThat(type.toString())
                    .startsWith(
                        "application/problem+json"));

        assertThat(response.getHeaders()
                .getFirst("X-Request-ID"))
            .isNotBlank();

        assertThat(response.getBody())
            .contains("\"code\":\"VALIDATION_FAILED\"")
            .contains("\"requestId\"")
            .doesNotContain("invalid");
    }
}
```

**Cần chú ý một điểm kiểm thử:** Body trên chứa chuỗi `"invalid"` làm SKU, còn code problem detail không nên echo SKU. Dòng `.doesNotContain("invalid")` có thể vô tình match chữ “invalid” trong một title/error code chung nếu thay format/ngôn ngữ về sau. Với contract lâu dài, dùng sentinel khó trùng `"SENTINEL-SECRET-PAYLOAD"` trong một field invalid và assert không có đúng sentinel, thay vì một từ phổ thông. Đây là khác biệt giữa test “safety property” và test phụ thuộc wording.

### 15.1. Live test chứng minh gì?

- Tomcat bind một TCP port thật.
- Client có thể POST JSON tới Spring MVC stack.
- Validation, advice và Jackson thực hiện như trên network.
- Response thực có HTTP 400, `Content-Type: application/problem+json` và `X-Request-ID`.
- Response body chứa mã lỗi máy đọc `VALIDATION_FAILED`.

Nó **không** thử TLS, NGINX, CDN, Kubernetes, DB transactions hoặc concurrency giữa nhiều replicas. Vì `RANDOM_PORT` dùng port ngẫu nhiên, CI không cần giữ 8080 rảnh.

### 15.2. Tại sao không dùng @Transactional test rollback?

Trong live HTTP test, Tomcat xử lý request trên thread khác test method. Một `@Transactional` ở test thread không tự rollback transaction được thực thi qua HTTP request. Nếu chuyển lab sang JPA, cần isolated test DB, fixtures và cleanup; đừng suy rằng mọi thay đổi DB được test transaction tự động cuộn lại.

### 15.3. Test HTTP method và content type trên network

Có thể bổ sung vào class live test:

- POST với `text/plain` → 415/`HTTP_415`.
- GET một route không tồn tại → 404/`ROUTE_NOT_FOUND`.
- Gửi JSON rất lớn → container/proxy có thể trả 413 hoặc 400 trước controller, tùy cấu hình.
- `Accept: application/problem+json` với lỗi → vẫn có ProblemDetail.
- GET success có `Content-Type: application/json`.
- Gửi `Accept-Encoding: gzip` với JSON đủ kích thước → kiểm tra compression thực, không chỉ property.

Đây là các test chọn lọc theo hợp đồng production; không ép MockMvc chứng minh hệ thống mạng.

## 16. Cấu hình máy chủ cho các môi trường khác nhau

### 16.1. Bind address và port

Lab:

```properties
server.address=127.0.0.1
server.port=8080
```

`127.0.0.1` chỉ nhận kết nối từ chính máy. Khi chạy Docker/Kubernetes cần bind trên interface container, thường:

```properties
server.address=0.0.0.0
server.port=8080
```

**0.0.0.0 không tự làm API có authentication**; nó chỉ mở listener trên mọi network interfaces. Cần bảo vệ bằng Security, network policy, firewall và ingress. Để override local config khi deploy container có thể dùng env `SERVER_ADDRESS=0.0.0.0`, `SERVER_PORT=8080` hoặc profile-specific properties, tránh sửa source giữa environments.

### 16.2. Context path khác API version prefix

Tùy chọn trong một profile môi trường:

```properties
server.servlet.context-path=/shop
```

Khi đó `@RequestMapping("/api/v1/products")` vẫn giữ nguyên, nhưng URL ngoài là `/shop/api/v1/products`. Không đặt thêm `/shop` trong controller nếu đã dùng context path, tránh nhân đôi prefix. Test lại `Location` sinh bằng `ServletUriComponentsBuilder`, redirects, security matchers, ingress rewrite và health endpoints.

### 16.3. Server compression

```properties
server.compression.enabled=true
server.compression.min-response-size=2KB
```

Một JSON nhỏ có thể không được nén dù property enabled; response phải đủ điều kiện về kích thước, MIME type và client `Accept-Encoding`. Mặc định Spring Boot 3.3 không bật compression, threshold là 2KB. Khi NGINX/CDN nén tại edge, nên xác định chủ thể nén để tránh nén hai lần, sai Content-Length hoặc cache variants.

Kiểm chứng với HTTP thật:

```bash
curl -i -H 'Accept-Encoding: gzip' \
  http://127.0.0.1:8080/api/v1/products
```

`curl -i` có thể hiển thị compressed bytes khó đọc nếu endpoint trả gzip. Dùng `curl --compressed -i` để client tự giải nén cho hiển thị; kiểm tra `Content-Encoding: gzip` trên response **chỉ khi đủ điều kiện**. Bài demo thường có few products, chưa đạt 2KB, nên không hứa sẽ thấy gzip ở ví dụ nhỏ.

### 16.4. Graceful shutdown

`server.shutdown=graceful` cho Spring Boot 3.3 có cơ hội chờ HTTP requests đang chạy khi context đóng. `spring.lifecycle.timeout-per-shutdown-phase=20s` là budget theo phase, không phải chỉ định Pod sẽ luôn chờ 20s. Khi Kubernetes Pod có `terminationGracePeriodSeconds=30`, còn có `preStop`, route propagation và lifecycle phases khác; phải tính toàn budget thực.

`SIGKILL`/OOMKill không cho Java shutdown hooks hoàn tất. Business operations phải có transactions, idempotency và persistence chứ không chỉ trông chờ `@PreDestroy`.

### 16.5. Forwarded headers và TLS termination

Ở local:

```properties
server.forward-headers-strategy=none
```

Khi reverse proxy đáng tin cậy terminate HTTPS, app có thể cần hiểu original scheme/host để tạo `Location`/redirect đúng:

```properties
server.forward-headers-strategy=framework
```

**Chỉ bật khi proxy là trust boundary**: edge phải strip/overwrite `Forwarded` và `X-Forwarded-*` từ Internet, app không được public trực tiếp qua route khác cho attacker gửi forged headers. Xử lý sai có thể khiến Location trỏ hostname do attacker tạo. Trên Tomcat, tùy architecture có thể dùng native strategy và RemoteIpValve; đọc docs đúng phiên bản.

### 16.6. Error fallback và debug

`server.error.include-stacktrace=never`, `server.error.include-message=never`, `server.error.include-binding-errors=never` làm default fallback `/error` ít lộ internal details hơn. Nhưng chúng không xóa stack traces được app chủ động trả qua `ex.getMessage()`, và không ngăn logs/headers do proxy tạo. Dùng correlation IDs, sanitized error codes, metrics/traces và internal logs có quyền truy cập thích hợp.

## 17. Xử lý validation nâng cao

### 17.1. Nested DTO và @Valid cascade

Ví dụ một request có địa chỉ lồng nhau:

```java
public record AddressInput(
        @NotBlank String city,
        @NotBlank String street) {
}

public record CheckoutInput(
        @NotNull @Valid AddressInput address,
        @NotBlank String customerRef) {
}
```

Đây là **snippet minh họa** cần imports Jakarta validation và class files riêng nếu muốn sử dụng. `@Valid` trên nested component cho phép cascade validation; chỉ đặt `@NotNull` không tự validate fields bên trong. Với collections, có thể dùng `List<@Valid AddressInput>` và các constraints cho size/pattern.

### 17.2. Cross-field validation

Một vài business constraints cần nhiều fields: startDate ≤ endDate, discount ≤ price, stock not negative when reserved. Có thể viết custom class-level Jakarta validation constraint hoặc check trong service. Đừng cố ép một regex lớn lên một field để kiểm tra quan hệ nhiều fields. Cần phân biệt lỗi **400 request representation invalid** với **409 conflict theo trạng thái hệ thống**.

### 17.3. DTO groups

Jakarta Bean Validation hỗ trợ groups, nhưng groups tăng độ khó khi create/PUT/PATCH có ràng buộc khác nhau. Với API vừa và nhỏ, **DTO riêng cho create/update/patch** thường dễ hiểu hơn. Không biến groups thành lý do để bỏ validate PATCH sau merge.

### 17.4. @Validated và method validation

`@Valid @RequestBody` trigger validation của body DTO. `@Validated` trên class/service dùng cho method-level constraints tùy Spring/Bean Validation integration, nhưng Spring MVC 6.1 cũng có built-in method validation cho trực tiếp constraints trên handler parameters. Không áp lời giải Boot 2.x cho Boot 3.3 mà không kiểm tra exception type: method validation có thể tạo `HandlerMethodValidationException`, không phải `MethodArgumentNotValidException` của body.

Advice kế thừa `ResponseEntityExceptionHandler` có thể xử lý framework exception; muốn trả `errors` có cấu trúc riêng cho method parameters, hãy override hook tương ứng và viết thêm tests. Không giả định mọi lỗi `@Min` trên `@RequestParam` đi qua duy nhất `handleMethodArgumentNotValid`.

### 17.5. Message localization không được dùng làm error code

`@NotBlank(message="...")` có thể xuất thông báo theo `MessageSource` và `Accept-Language`. Nhưng client không nên branch logic theo message đã dịch. Trả `code` ổn định và `field`/`rule`; nếu cần localized `detail`, phiên dịch ở server theo locale với fallback rõ ràng và test i18n.

### 17.6. Không lạm dụng validation để thay authorization

`@Pattern` trên SKU không ngăn user B sửa sản phẩm của user A. `@Valid` kiểm input shape; authorization phải xác minh actor/resource/tenant ở service/security boundary. Không dùng ID khó đoán hoặc UUID như cơ chế thay authentication.

## 18. Thiết kế lỗi nhất quán: các trường hợp khó

### 18.1. 404: không có route vs không có resource

Một `GET /api/v1/products/5` có route hợp lệ, nhưng catalog không có id 5 → `PRODUCT_NOT_FOUND`. Một `GET /api/v1/ghost` không có controller mapping → `ROUTE_NOT_FOUND`. Cùng HTTP 404 nhưng client/support có thêm ngữ cảnh. Tuy nhiên đừng trả resource existence quá chi tiết cho user không có quyền vì có thể tạo enumeration; production có thể trả 404 chung cho unauthorized resource.

### 18.2. 405: giữ Allow header

Spring MVC biết route tồn tại nhưng HTTP method sai; nó có thể trả `Allow`. Khi sửa lỗi toàn cục, **đừng bỏ header gốc**. `ApiErrorHandler.createResponseEntity` copy `HttpHeaders` từ base handler, rồi chỉ chỉnh `Content-Type` sang Problem JSON. Test kiểm `Allow` tồn tại. Với `OPTIONS`/CORS preflight, có semantics riêng; không đồng nhất mọi OPTIONS thành 405.

### 18.3. 415 và 406

`415 Unsupported Media Type`: client gửi **request** Content-Type không phù hợp với `consumes`. `406 Not Acceptable`: client yêu cầu **response** format qua `Accept` nhưng server không thể tạo. Khi trả ProblemDetail cho 406, content negotiation có thể có ràng buộc đặc biệt: nếu client chỉ chấp nhận `text/html`, không thể hứa body `application/problem+json` sẽ luôn được gửi trọn vẹn. Kiểm tra Accept/Content-Type cả hai phía thay vì áp một handler bắt tất cả.

### 18.4. JSON null, missing và kiểu dữ liệu

Nếu JSON thiếu `stock`, Java record component `Integer` có thể nhận null và `@NotNull` phát hiện 400 validation. Nếu dùng primitive `int`, missing có thể mặc định 0 và vô tình vượt qua rule nếu 0 hợp lệ. Vì vậy trong input DTO cần phân biệt absence/null với giá trị 0 khi contract yêu cầu field bắt buộc. Jackson lỗi parse khi client gửi `"stock":"abc"` sẽ gây `INVALID_JSON`, khác với `stock=-1` hợp kiểu nhưng vi phạm `@Min`.

### 18.5. Unknown properties

Tùy Jackson/Boot defaults, unknown JSON fields có thể bị bỏ qua thay vì báo lỗi. Một API cần schema nghiêm ngặt có thể cấu hình Jackson fail-on-unknown-properties ở profile được kiểm soát và test 400; cần xem tác động backward compatibility. Không chỉ dùng Bean Validation rồi mặc định cho rằng mọi field không khai báo đều bị từ chối.

### 18.6. Concurrency và 409

Trong lab, `synchronized` giữ check+insert nhất quán trong cùng JVM. Với nhiều replicas/DB, hai request tạo cùng SKU có thể vượt kiểm tra service ở hai Pod; **database unique index** mới là nguồn bảo đảm cuối cùng. Mapping database constraint violation sang 409 phải xác định đúng unique constraint (SKU) và không rò rỉ SQL/query/record values ra HTTP response.

### 18.7. Optimistic locking / 412

Khi client GET product rồi PUT sau một client khác, có nguy cơ lost update. Production có thể dùng JPA `@Version`, ETag và `If-Match`; lỗi stale representation thường dùng HTTP `412 Precondition Failed` khi điều kiện If-Match thất bại, hoặc 409 cho một business conflict đã định nghĩa. Không thêm optimistic locking giả vào repository in-memory bằng cách chỉ dùng synchronized: critical section không biết phiên bản mà client đã đọc.

### 18.8. 500 và fallback path

Unexpected failure nên trả message chung, log category + request ID phía server trong kênh nội bộ. Không trả stack trace, SQL, credentials hoặc raw Java class package names ra public ProblemDetail. Nếu đã commit headers/response body, handler có thể không gửi lại ProblemDetail đầy đủ — đó là giới hạn HTTP streaming, không phải cú pháp `@ExceptionHandler`.

## 19. Observability cho REST API

### 19.1. Request ID, trace ID và log

`X-Request-ID` trong demo là UUID per request, không phải authentication token. Khách hàng có thể gửi ID khi báo lỗi; backend tìm được các log tương ứng nếu app log hợp lý. Trong production nên dùng structured logs (service, route template, status, duration, requestId, traceId) và correlation giữa services, không log full JSON body hoặc Authorization/Cookie.

### 19.2. Metrics Actuator

Với starter Actuator, Spring Boot/Micrometer có thể tạo HTTP server metrics như `http.server.requests`, hữu ích cho latency, throughput, 4xx/5xx rates. Dùng route template `/api/v1/products/{id}` làm tag thay raw URL chứa IDs; không gắn requestId/userId/SKU vào metric labels vì high cardinality.

Ở lab chỉ bind loopback:

```bash
curl -sS http://127.0.0.1:8080/actuator/health
curl -sS http://127.0.0.1:8080/actuator/metrics
curl -sS http://127.0.0.1:8080/actuator/metrics/http.server.requests
```

Kết quả metrics phụ thuộc số requests đã chạy và registry. Actuator metrics/health production cần private management networking/authentication; đừng expose các endpoint debug/admin khác ra Internet.

### 19.3. Rate limit, timeouts, circuit breaker

REST API cần bảo vệ trước request bursts, oversized bodies và slow clients. Tomcat thread pool/connections/timeout cần được tune bằng load tests, không tăng vô hạn. API gọi dependencies khác cần connection/read timeouts, retry có giới hạn và circuit breaker; không đặt blocking remote call trong filter hoặc health endpoint mỗi request.

### 19.4. Security errors có thể khác JSON advice

Với Spring Security, authentication failures (401) và forbidden (403) thường xử lý trong servlet filter chain, **trước** controller advice. Muốn ProblemDetail nhất quán cho 401/403, cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` riêng, sử dụng error factory chung hoặc converter HTTP đúng chính sách. Đừng dùng `@ExceptionHandler(Exception.class)` để giả định nó sẽ nhìn thấy mọi security exception.

## 20. Chuyển lab sang database/JPA trong production

Một lộ trình hợp lý:

1. Tạo domain entity/repository riêng, không expose JPA entity trực tiếp làm API JSON.
2. Thêm `spring-boot-starter-data-jpa` và JDBC driver phù hợp, migrations Flyway/Liquibase.
3. Định nghĩa bảng products có ID/price/stock, unique index trên normalized SKU.
4. Service dùng `@Transactional` cho create/replace/delete theo isolation phù hợp.
5. Tạo mapping giữa `ProductInput`, entity và response DTO.
6. Bắt `DataIntegrityViolationException` **có chọn lọc** (đúng unique constraint) để trả 409; các integrity errors khác không được che là duplicate.
7. Xử lý lost update với version/ETag khi nhiều writers.
8. Tách test repository integration với Testcontainers hoặc test DB, không dùng in-memory fake để khẳng định transactions đúng.
9. Dùng connection pool, DB timeouts, schema migration/rollback plan.
10. Bổ sung authentication/authorization/tenant isolation vào every read and write path.

### 20.1. Vì sao unique check ở service chưa đủ?

Nếu hai requests đồng thời tới hai Pods, mỗi Pod có thể quan sát “SKU chưa tồn tại”. Nếu chỉ check trước insert mà DB không có unique index, cả hai có thể commit. Database constraint cần là nguồn chân lý, còn check ở service có thể giúp trả message thân thiện trong tình huống thường.

### 20.2. Không biến API thành transaction coordinator không bền vững

Nếu POST product còn gọi payment/inventory service, một HTTP response thất bại không đồng nghĩa tất cả downstream side effects đã rollback. Dùng outbox/saga/idempotency keys khi có distributed transactions và retries; ProblemDetail trả lỗi rõ ràng nhưng không tự tạo consistency guarantee.

## 21. Deployment: cấu hình từ môi trường và reverse proxy

Dự án lab có `server.address=127.0.0.1`, nên Docker image sẽ không nhận kết nối từ port publishing nếu không override. Một Dockerfile ví dụ sau khi build JAR:

```dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app

COPY build/libs/catalog-api-lab-0.0.1-SNAPSHOT.jar /app/app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Build và chạy local container:

```bash
./gradlew bootJar

docker build -t catalog-api-lab:local .

docker run --rm -p 8080:8080 \
  -e SERVER_ADDRESS=0.0.0.0 \
  catalog-api-lab:local
```

**Exec-form ENTRYPOINT** cho JVM nhận stop signal trực tiếp hơn; nếu có shell wrapper, cần đảm bảo `exec java ...`/signal forwarding. Khi deploy thật, image tag và registry phải là của tổ chức, bật network policies, Security, liveness/readiness/startup probes phù hợp và Pod shutdown grace lớn hơn thời gian app cần.

### 21.1. Cấu hình tách môi trường

Không hardcode production secrets trong `application.properties` hoặc commit credentials vào Git. Dùng environment variables/Kubernetes Secrets/secret manager và Spring config import/profile. Ví dụ env `SERVER_PORT=8080`, `SERVER_ADDRESS=0.0.0.0`, `SPRING_PROFILES_ACTIVE=prod` được Boot binding. Đừng đặt production database URL/password vào code examples hoặc logs.

### 21.2. HTTPS và trusted proxies

Nếu proxy terminate HTTPS và gửi tới Java HTTP nội bộ, cần chiến lược forwarded headers đúng. Tại reverse proxy:

- Strip các forwarded headers do client tự gửi.
- Set `X-Forwarded-Proto`/`Host`/`Forwarded` theo public request được tin cậy.
- App chỉ cho phép traffic từ proxy/network phù hợp.
- Xem xét `server.forward-headers-strategy=framework` hoặc native với security review.
- Test `Location` khi POST qua public HTTPS URL, không trỏ ngược `http://localhost`.
- Test cookies Secure/SameSite nếu sau này thêm session login.

### 21.3. Kubernetes readiness và graceful không tự bảo đảm idempotency

Pod Ready có nghĩa phù hợp với nhận traffic theo health policy, không có nghĩa business transaction chắc thành công. Khi terminate, readiness rút traffic bất đồng bộ, keep-alive requests có thể còn. Với POST dễ tạo side effect, client retry cần idempotency key và server dedup nếu muốn tránh tạo hai sản phẩm khi response đầu bị mất.

### 21.4. Không làm hỏng routing với context path

Khi ingress rewrite `/catalog/api/v1/products` sang `/api/v1/products`, còn app cũng có `server.servlet.context-path=/catalog`, có thể thành double prefix/sai mapping. Đặt rõ nguồn sở hữu prefix: proxy rewrite hay servlet context path. Test curl qua ingress và kiểm tra header Location thực.

## 22. Kiểm thử bổ sung nên có trước production

| Bài test | Mục đích | Tầng phù hợp |
| --- | --- | --- |
| DTO null/blank/size/pattern/price/stock | Phát hiện validation regressions | MockMvc |
| JSON syntax sai | Kiểm tra INVALID_JSON và 400 | MockMvc/live |
| Request thiếu Content-Type hoặc text/plain | Chứng minh consumes 415 | MockMvc/live |
| Unknown API route và malformed ID | 404/400 khác nhau | MockMvc/live |
| PUT missing fields | Full replacement validation | MockMvc |
| Duplicate SKU concurrent | Business 409, atomicity | Integration/database |
| POST Location absolute đúng sau TLS proxy | Không lỗi scheme/host/path | Staging qua gateway |
| GET/PUT/DELETE unauthorized | Object-level permissions | Spring Security integration |
| Header Accept JSON/Problem JSON | Content negotiation | Live HTTP |
| Very large body/headers | Container/proxy limits | Live HTTP/ingress |
| Compression gzip and Vary | HTTP server/edge owner | Live HTTP/CDN |
| X-Request-ID consistency | Header/body correlation | MockMvc/live |
| 500 does not leak stacktrace | Safe fallback error | Integration với synthetic fault |
| Database unique constraint race | Không tạo duplicate giữa Pods | DB integration |
| Graceful SIGTERM | Active HTTP requests drain | Process/container test |
| 404 static fallback behavior | MVC advice vs static resource | Boot full context |
| 401/403 error format | Security chain outside advice | Security integration |
| Actuator not exposed public | Network/security posture | Staging/cloud |
| Retry/idempotency | Side effects không lặp | Integration/E2E |

### 22.1. Test với controller-only slice

`@WebMvcTest(ProductController.class)` chạy MVC slice và có thể yêu cầu mock/import `ProductCatalog`. Phù hợp cho binding/HTTP mapping khi muốn tốc độ cao, nhưng không chứng minh repository và full app wiring. Trong bài dùng `@SpringBootTest + @AutoConfigureMockMvc` để chạy service/advice/filter thực; còn `RANDOM_PORT` để kiểm tra HTTP listener.

### 22.2. JSON response không nên phụ thuộc field order

Jackson không cam kết client phải parse theo thứ tự keys. Test dùng `jsonPath`/JSON parser, không `assertEquals` toàn bộ response string với ordering cố định. Cũng không nên so sánh trực tiếp error `detail` nếu localization có thể thay, trừ khi wording được định nghĩa là public contract.

### 22.3. UUID và timestamps động

Request ID, ID sản phẩm, timestamps (nếu thêm) thay đổi theo runtime. Test assert `requestId` không rỗng, đồng nhất header/body trong cùng request, đúng UUID format nếu contract yêu cầu. Không hardcode UUID minh họa. Đảm bảo test không leak IDs vào metrics labels.

## 23. Ma trận chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `@Valid` không báo 400 | Thiếu starter-validation hoặc thiếu `@Valid` | Kiểm tra dependencies và controller |
| Boot 3 compile báo javax validation | Dùng import Boot 2.x | Chuyển sang `jakarta.validation.*` |
| POST hợp lệ trả 415 | Header `Content-Type` không phải JSON | Gửi application/json |
| POST JSON sai trả 400 INVALID_JSON | Jackson parse/bind fail | Kiểm tra JSON types/format |
| POST value sai trả 400 VALIDATION_FAILED | Bean Validation vi phạm | Đọc field/rule, không rejectedValue |
| SKU bị trùng trả 409 | Uniqueness business rule | Chọn SKU khác, xử lý conflict |
| URL `/products/abc` trả 400 | PathVariable long conversion fail | Gửi ID số |
| URL `/products/9999` trả 404 | Không có product ID | Kiểm tra state, không nhầm route |
| Unknown API path trả 404 HTML | BasicErrorController/static handler/config | Kiểm tra resource mappings và advice |
| 405 không có Allow header | Custom handler bỏ headers gốc | Preserve ResponseEntityExceptionHandler headers |
| Một error 200 với body lỗi | Bắt exception trong controller rồi return JSON | Trả status đúng qua advice |
| 500 lộ stacktrace | Return ex.toString/getMessage hoặc Boot debug | Sanitize details, server.error.* |
| ProblemDetail không có code | Advice custom không chạy/được ordered khác | Kiểm tra @RestControllerAdvice và Boot auto handler |
| Body có `errors` chứa email/password | Serialize BindingResult/rejectedValue | Chỉ field/rule, test leak |
| Content-Type JSON thay vì problem+json | Handler trả Map thay ProblemDetail | Dùng RFC 9457 và converter đúng |
| Location trỏ http sau HTTPS | Forwarded headers/proxy trust sai | Strip/normalize trusted headers |
| Location thiếu context prefix | Hardcode URI trong controller | Generate current request URI, test ingress |
| Docker curl connection refused | server.address=127.0.0.1 trong container | Override 0.0.0.0/network policy |
| GET list rỗng sau restart | In-memory store bị reset | DB persistent |
| Concurrent duplicate trên nhiều Pods | synchronized chỉ trong một JVM | DB unique constraint |
| PUT mất thay đổi của client khác | Không có ETag/version check | Optimistic locking, If-Match |
| CORS preflight 403 | Security/CORS config thiếu | Cấu hình trusted origins và OPTIONS |
| HTTP client retries tạo đôi | POST không có idempotency | Idempotency key/dedup |
| MockMvc pass, gateway trả 413 | Proxy/container body limit | Live HTTP/ingress tests |
| Gzip không xuất hiện | Response nhỏ hơn threshold/Accept-Encoding | Test đủ điều kiện |
| Actuator metrics public | Management exposure/network sai | Private listener + auth |
| Error không có X-Request-ID | Lỗi trước filter hoặc gateway trả | Correlation ở edge và test boundary |

## 24. Bài tập tự kiểm tra

**1.** Vì sao phải thêm `spring-boot-starter-validation` nếu đã có `spring-boot-starter-web`?  
**Đáp án:** Validation provider/annotations cần dependency phù hợp; `@Valid` không tự biến mọi web app thành ứng dụng Bean Validation đầy đủ.

**2.** `@NotNull` trên String có thay `@NotBlank` không?  
**Đáp án:** Không. Chuỗi `"   "` khác null nhưng blank, nên NotBlank phù hợp hơn.

**3.** Vì sao DTO stock dùng `Integer` thay `int`?  
**Đáp án:** Có thể phân biệt null/missing với 0, từ đó `@NotNull` bắt thiếu field.

**4.** JSON malformed và JSON hợp lệ nhưng `price=-1` nên có cùng error code không?  
**Đáp án:** Không nhất thiết. Demo dùng `INVALID_JSON` và `VALIDATION_FAILED`, cả hai HTTP 400.

**5.** Khi POST thành công, tại sao cần `Location`?  
**Đáp án:** 201 Created nên chỉ ra URI của resource mới, giúp client GET tiếp.

**6.** Client gửi duplicate SKU; đây là validation syntax hay conflict state?  
**Đáp án:** Conflict business state, nên demo trả 409 `SKU_ALREADY_EXISTS`.

**7.** Khi client gọi GET /api/v1/products/abc, nên trả 404?  
**Đáp án:** Không. Không convert được path variable sang long → 400 `INVALID_PARAMETER`.

**8.** Tại sao không trả `MethodArgumentNotValidException.getMessage()` trong body?  
**Đáp án:** Có thể lộ rejected values, thông tin nội bộ và không ổn định theo framework version.

**9.** Nếu client yêu cầu PATCH mà controller chỉ hỗ trợ PUT, nên trả gì?  
**Đáp án:** 405 Method Not Allowed, giữ Allow header.

**10.** `spring.mvc.problemdetails.enabled=false` có cấm dùng `ProblemDetail`?  
**Đáp án:** Không. Nó tắt auto handler của Boot; custom advice vẫn dùng Spring MVC ProblemDetail.

**11.** Vì sao `spring.web.resources.add-mappings=false` giúp 404 trong lab API?  
**Đáp án:** Tắt default resource handler `/**`, tránh unknown paths bị static handler bắt, để MVC no-handler đi vào advice.

**12.** Khi app được reverse proxy HTTPS nhưng Location trỏ HTTP, nguyên nhân nào?  
**Đáp án:** Forwarded headers/strategy/trust boundary hoặc URL hardcoded sai.

**13.** `synchronized` đủ đảm bảo SKU unique giữa ba Kubernetes Pods không?  
**Đáp án:** Không. Đồng bộ hóa chỉ trong JVM; phải có DB unique constraint/transaction.

**14.** Vì sao test `MockMvc` pass không chứng minh server nén gzip?  
**Đáp án:** MockMvc không chạy networking/embedded compression logic; cần live HTTP response.

**15.** Khi DELETE thành công, response 204 nên có body JSON `{"ok":true}` không?  
**Đáp án:** Không. 204 No Content không có representation body.

**16.** HTTP 500 từ NGINX/nginx upstream có chắc đi qua `@RestControllerAdvice` không?  
**Đáp án:** Không. Gateway tạo error ngoài Spring MVC; cần policy riêng tại gateway/edge.

**17.** Tại sao requestId không nên làm metric tag?  
**Đáp án:** Mỗi request ID khác nhau gây high cardinality/time-series explosion.

**18.** PUT trong demo có phải partial update không?  
**Đáp án:** Không. Nó thay đầy đủ các fields cho resource đã có; PATCH cần contract riêng.

**19.** Khi POST retry sau timeout có thể tạo duplicate product không?  
**Đáp án:** Có, nếu server đã commit nhưng client chưa nhận response. Cần idempotency/dedup khi contract yêu cầu.

**20.** Response `application/problem+json` với `status:409` nhưng HTTP status thực 200 có đúng không?  
**Đáp án:** Không. Client/proxy dựa vào HTTP status thực; body status phải nhất quán.

## 25. Checklist hoàn thành

- [ ] Controller chỉ nhận DTO hợp lệ, xử lý HTTP mapping/status/Location rõ ràng.
- [ ] Java 17, Boot 3.3 và `jakarta.*` imports phù hợp.
- [ ] Có `spring-boot-starter-validation`, `@Valid`, test negative input.
- [ ] Domain uniqueness kiểm tra trong service và database constraint trong production.
- [ ] POST trả 201 + Location, GET/PUT trả 200, DELETE trả 204.
- [ ] Missing product trả 404, duplicate trả 409, malformed JSON trả 400, unsupported media type trả 415.
- [ ] 405 trả Allow, 404 unknown route không lộ HTML/stacktrace ngoài contract.
- [ ] Lỗi là RFC 9457 ProblemDetail có `code` và `requestId`, không chứa rejectedValue.
- [ ] Content-Type lỗi là application/problem+json trong MVC-handled cases.
- [ ] RequestIdFilter không đọc/log payload/credentials.
- [ ] Đã kiểm tra server.port, address, context path và bind interface theo deployment.
- [ ] Compression có owner rõ (app/proxy/CDN) và HTTP live test phù hợp.
- [ ] Forwarded headers chỉ được tin từ proxy trusted, Location/redirect đúng scheme/host.
- [ ] Graceful shutdown được bật cho Boot 3.3, Pod timeout đủ.
- [ ] Error fallback không lộ exception messages, stacktrace, sensitive binding values.
- [ ] Security authentication/authorization/CSRF/CORS/rate limits được bổ sung theo threat model.
- [ ] DB migrations/unique indexes/transactions/optimistic locking khi chuyển sang persistent store.
- [ ] Có MockMvc tests và RANDOM_PORT tests cho HTTP contracts và error content type.
- [ ] Test concurrency, retries, idempotency và failover nếu có nhiều replicas.
- [ ] Actuator/metrics được bảo vệ, low-cardinality tags và correlation đúng.
- [ ] CI build JAR và smoke test qua container/ingress production-like.
- [ ] Có playbook chẩn đoán theo status, code, requestId, route và trace.

## Tài liệu tham khảo

1. [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
2. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
3. [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
4. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
5. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
6. [Spring Framework 6.1 — Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller.html)
7. [Spring Framework 6.1 — Error Responses / ProblemDetail](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-ann-rest-exceptions.html)
8. [Spring Framework 6.1 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
9. [Spring Framework 6.1 — Validation](https://docs.spring.io/spring-framework/reference/6.1/core/validation/beanvalidation.html)
10. [Spring Framework 6.1 — MVC Input/Validation](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-validation.html)
11. [Jakarta Validation Specification](https://jakarta.ee/specifications/bean-validation/)
12. [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
13. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
14. [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
15. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

**Kết luận:** Một REST API MVC có chất lượng không chỉ có `@GetMapping` và `@PostMapping`. Nó cần **HTTP status/Location chính xác, server properties phù hợp môi trường, validation ở boundary, business constraints ở service/DB, RFC 9457 errors ổn định không lộ dữ liệu, request correlation và tests ở cả MVC lẫn HTTP server thật**. Tách đúng trách nhiệm của controller, service, advice, filter và infrastructure là nền tảng để chuyển từ demo Spring Boot sang dịch vụ có thể vận hành an toàn.
