# Chọn starter WebFlux phù hợp với ứng dụng Reactive

Khi ứng dụng Spring Boot chạy trên Spring WebFlux, springdoc-openapi cần starter dành cho WebFlux để đọc đúng mô hình web reactive và tạo tài liệu OpenAPI. Lựa chọn quan trọng là ứng dụng chỉ cần endpoint JSON/YAML, cần Swagger UI hay muốn giao diện Scalar. Dùng `springdoc-openapi-starter-webflux-api` nếu chỉ phát hành tài liệu máy đọc; dùng `springdoc-openapi-starter-webflux-ui` cho Swagger UI hoặc `springdoc-openapi-starter-webflux-scalar` cho Scalar. Với Spring Boot 2.x, tên artifact thuộc dòng springdoc 1.x khác với starter của Boot 3.x và 4.x.

Việc chọn WebFlux nên dựa trên kiến trúc xử lý request của toàn ứng dụng. WebFlux phù hợp khi các tầng HTTP, service và truy cập dữ liệu có thể chạy theo mô hình non-blocking. Chỉ đổi kiểu trả về sang `Mono` hoặc `Flux` không tự biến một ứng dụng dùng thư viện blocking thành reactive.

## 1. Khi nào nên chọn Spring WebFlux?

Spring MVC và Spring WebFlux đều có thể xây dựng REST API, nhưng dùng hai mô hình runtime khác nhau:

| Tiêu chí | Spring MVC | Spring WebFlux |
|---|---|---|
| Mô hình xử lý | Servlet và request thread theo mô hình truyền thống | Reactive Streams, event loop và xử lý non-blocking |
| Kiểu trả về thường gặp | DTO, `List<T>`, `ResponseEntity<T>` | `Mono<T>`, `Flux<T>`, `Mono<ResponseEntity<T>>` |
| Truy cập dữ liệu phù hợp | JDBC, JPA và thư viện blocking | R2DBC, reactive MongoDB, reactive HTTP client và driver non-blocking |
| Máy chủ mặc định thường gặp | Tomcat | Reactor Netty |
| Tích hợp tài liệu springdoc | Starter `webmvc-api`, `webmvc-ui` hoặc `webmvc-scalar` | Starter `webflux-api`, `webflux-ui` hoặc `webflux-scalar` |

Nên chọn WebFlux khi ứng dụng có nhu cầu xử lý nhiều I/O đồng thời, streaming hoặc giao tiếp reactive xuyên suốt. Ví dụ một API tổng hợp dữ liệu từ nhiều dịch vụ bằng `WebClient`, truy vấn kho dữ liệu reactive và trả kết quả theo luồng có thể hưởng lợi từ WebFlux.

Nếu phần lớn xử lý dựa vào JPA/JDBC, SDK blocking hoặc công việc CPU-bound thông thường, Spring MVC thường đơn giản hơn. WebFlux vẫn có thể gọi thư viện blocking trong một scheduler riêng, nhưng phải quản lý việc chuyển scheduler và giới hạn tài nguyên; cách đó không làm thao tác blocking trở thành non-blocking.

### Đừng chọn WebFlux chỉ vì controller trả về Mono hoặc Flux

Spring MVC cũng hỗ trợ một số kiểu trả về reactive như `Mono` và `Flux`. Vì vậy, việc một method trả `Mono<Product>` không đủ để kết luận ứng dụng phải chạy WebFlux. Hãy xem xét web runtime, dependency server, data access và cách toàn bộ request được xử lý.

### WebClient không quyết định web server

Một ứng dụng Spring MVC vẫn có thể gọi dịch vụ ngoài bằng `WebClient`. WebClient là HTTP client; việc dùng client reactive không tự yêu cầu server chuyển sang WebFlux.

Với Spring Boot 4, nếu chỉ cần HTTP client, có thể dùng `spring-boot-starter-webclient` mà không thêm reactive web server. Với Spring Boot 3, WebClient nằm trong hệ sinh thái `spring-webflux`, vì vậy một số dự án thêm `spring-boot-starter-webflux` để lấy client. Nếu ứng dụng đồng thời có `spring-boot-starter-web`, Spring Boot mặc định vẫn chọn Spring MVC làm web application type. Trong trường hợp đó, tài liệu phải dùng springdoc WebMVC starter.

Chỉ chọn `spring-boot-starter-webflux` làm starter server khi ứng dụng thực sự cần WebFlux xử lý HTTP request. Nếu hệ thống chủ yếu dùng JPA/JDBC và các SDK blocking, Spring MVC thường đơn giản hơn; không nên đổi server chỉ để dùng WebClient.

## 2. Phân biệt các starter WebFlux của springdoc

Springdoc cung cấp các module theo nhu cầu công bố tài liệu:

| Artifact | Chức năng | Endpoint thường dùng |
|---|---|---|
| `springdoc-openapi-starter-webflux-api` | Tạo OpenAPI document từ ứng dụng WebFlux | `/v3/api-docs`, `/v3/api-docs.yaml` |
| `springdoc-openapi-starter-webflux-ui` | Tạo OpenAPI document và tích hợp Swagger UI | `/v3/api-docs`, `/v3/api-docs.yaml`, `/swagger-ui.html` |
| `springdoc-openapi-starter-webflux-scalar` | Tạo OpenAPI document và tích hợp giao diện Scalar | `/v3/api-docs`, `/scalar` |

Chọn `webflux-api` khi tài liệu được tải bởi pipeline, API portal hoặc công cụ client generator và không cần Swagger UI nhúng trong ứng dụng. Chọn `webflux-ui` khi developer cần duyệt endpoint, xem schema và thử gọi API ngay trên trình duyệt.

Chọn `webflux-scalar` nếu nhóm muốn dùng Scalar thay cho Swagger UI. Không thêm đồng thời API, UI và Scalar starter chỉ để có cùng một OpenAPI document. Starter UI/Scalar đã tích hợp phần sinh tài liệu cần thiết; chỉ dùng nhiều giao diện khi có yêu cầu triển khai rõ ràng.

### Trường hợp chỉ cần tài liệu JSON/YAML

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-api</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

Ứng dụng vẫn công bố OpenAPI nhưng không tích hợp Swagger UI. Client hoặc API portal có thể lấy JSON/YAML từ endpoint tài liệu.

### Trường hợp cần Swagger UI

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

Swagger UI đọc OpenAPI document do springdoc tạo và hiển thị endpoint, request, response, schema cùng các security scheme đã khai báo.

## 3. Chọn artifact theo phiên bản Spring Boot

Tên artifact springdoc thay đổi giữa các major version. Không dùng starter mới của Boot 3/4 trong dự án Boot 2 hoặc dependency cũ của v1 trong dự án Boot 3/4.

| Spring Boot | Dòng springdoc | Artifact WebFlux có Swagger UI | Artifact WebFlux chỉ có API docs |
|---|---|---|---|
| 2.x | 1.x | `springdoc-openapi-webflux-ui` | `springdoc-openapi-webflux-core` |
| 3.x | 2.x | `springdoc-openapi-starter-webflux-ui` | `springdoc-openapi-starter-webflux-api` |
| 4.x | 3.x | `springdoc-openapi-starter-webflux-ui` | `springdoc-openapi-starter-webflux-api` |

Với springdoc 2.x và 3.x, có thêm `springdoc-openapi-starter-webflux-scalar` nếu muốn dùng Scalar. Dòng v1 không dùng starter naming và tài liệu WebFlux v1 liệt kê `springdoc-openapi-webflux-ui`; module API-only tương ứng là `springdoc-openapi-webflux-core`.

Đây là hướng dẫn theo major version. Springdoc 1.8.0 là dòng legacy cuối cùng cho Spring Boot 1.x/2.x và đã hết hỗ trợ open-source; dự án mới nên dùng dòng springdoc tương thích với Spring Boot 3.x hoặc 4.x. Cần kiểm tra compatibility matrix và release note để chọn minor/patch version tương ứng với Spring Boot và Spring Framework đang dùng.

Ví dụ tài liệu springdoc v2 dành cho Spring Boot 3.x hiện dùng starter `springdoc-openapi-starter-webflux-ui` hoặc `springdoc-openapi-starter-webflux-api`. Dòng springdoc v1 dành cho Spring Boot 2.x dùng tên artifact cũ không có hậu tố `starter`. Tài liệu springdoc hiện hành có ví dụ WebFlux cho Spring Boot 4 và dòng springdoc 3.x.

## 4. Cấu hình Maven cho WebFlux và springdoc

Một ứng dụng WebFlux có Swagger UI cần Spring Boot WebFlux starter và springdoc WebFlux UI starter:

```xml
<properties>
    <java.version>21</java.version>
    <springdoc.version>3.2.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

Ví dụ dùng Spring Boot 4.x và springdoc 3.x. `spring-boot-starter-webflux` nên được quản lý version bởi Spring Boot parent hoặc dependency management của dự án. Không sao chép số version ví dụ vào một dự án Boot 3.x nếu compatibility matrix yêu cầu một dòng springdoc khác.

Nếu chỉ cần OpenAPI JSON/YAML, thay artifact `springdoc-openapi-starter-webflux-ui` bằng `springdoc-openapi-starter-webflux-api`.

### Maven với Spring Boot 3.x

Giữ cùng dependency Spring Boot WebFlux, nhưng chọn springdoc 2.x:

```xml
<properties>
    <springdoc.version>2.10.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

Version trong ví dụ minh họa một bản thuộc dòng springdoc 2.x. Hãy chọn bản tương thích với minor Spring Boot đang dùng thay vì coi đây là version bắt buộc.

## 5. Cấu hình Gradle

Với Gradle Kotlin DSL:

```kotlin
val springdocVersion = "3.2.0" // Spring Boot 4; với Spring Boot 3, dùng một bản 2.x tương thích
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springdoc:springdoc-openapi-starter-webflux-ui:$springdocVersion")
}
```

Nếu chỉ cần API docs:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springdoc:springdoc-openapi-starter-webflux-api:$springdocVersion")
}
```

Nếu dùng Scalar, thay artifact UI bằng `springdoc-openapi-starter-webflux-scalar`. Với Spring Boot 3.x, đặt `springdocVersion` về một bản 2.x tương thích; với Boot 4.x, dùng springdoc 3.x. Với Spring Boot 2.x, dùng artifact v1 cũ và kiểm tra hướng dẫn migration trước khi nâng major.

Nên khai báo version springdoc ở một property/version catalog để UI starter và các module springdoc khác trong cùng dự án dùng chung một version. Không để dependency graph kéo đồng thời nhiều phiên bản `springdoc-openapi` hoặc `swagger-core`.

## 6. Không trộn starter WebFlux với starter Web MVC

Một lỗi phổ biến là thêm cả hai dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Khi cả Spring MVC và WebFlux cùng có trên classpath, Spring Boot thường chọn Spring MVC làm web application type. Điều này có thể khiến ứng dụng khởi chạy trên servlet stack dù developer nghĩ mình đang dùng WebFlux.

Nếu ứng dụng thực sự cần WebFlux, hãy loại `spring-boot-starter-web` và dependency kéo theo Spring MVC nếu không cần. Cũng chọn đúng springdoc starter:

```text
spring-boot-starter-webflux
springdoc-openapi-starter-webflux-ui
```

Tránh cấu hình:

```text
spring-boot-starter-web
springdoc-openapi-starter-webflux-ui
```

hoặc:

```text
spring-boot-starter-webflux
springdoc-openapi-starter-webmvc-ui
```

### Có thể ép application type thành reactive không?

Spring Boot có property:

```yaml
spring:
  main:
    web-application-type: reactive
```

Property này có thể ép loại web application khi cần xử lý classpath đặc biệt. Tuy nhiên, nó không loại bỏ các dependency MVC và không giải quyết xung đột cấu hình do hai stack cùng xuất hiện. Cách rõ ràng hơn là giữ dependency đúng với web runtime mà ứng dụng thực sự sử dụng.

## 7. Springdoc tự nhận diện WebFlux controller

Với controller annotation-based, sau khi thêm đúng starter, springdoc tự đọc các mapping như `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping` và metadata từ Swagger annotations.

Ví dụ controller reactive:

```java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Tra cứu sản phẩm")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    Mono<ProductResponse> getById(@PathVariable UUID id) {
        return productService.findById(id);
    }

    @GetMapping
    Flux<ProductResponse> findAll() {
        return productService.findAll();
    }
}
```

Springdoc đọc path, HTTP method, tham số và kiểu phần tử của reactive return type để tạo operation. Có thể dùng `@Operation`, `@ApiResponse`, `@Parameter` và `@Schema` như với controller MVC.

Ví dụ service:

```java
interface ProductService {
    Mono<ProductResponse> findById(UUID id);
    Flux<ProductResponse> findAll();
}
```

`Mono<T>` biểu diễn tối đa một phần tử hoặc không có phần tử; `Flux<T>` biểu diễn một chuỗi từ không đến nhiều phần tử. Khi trả `Flux<T>` với media type JSON thông thường, API thường được tiêu thụ như một collection; khi dùng `text/event-stream` hoặc định dạng streaming khác, cần mô tả content type và hành vi stream rõ ràng trong OpenAPI.

## 8. WebFlux functional endpoints cũng dùng WebFlux starter

Ứng dụng có thể khai báo route bằng `RouterFunction` và handler thay vì controller annotation. Vẫn dùng starter `webflux-api`, `webflux-ui` hoặc `webflux-scalar` tương ứng với nhu cầu tài liệu.

Ví dụ route hàm:

```java
@Configuration
class ProductRoutes {

    @Bean
    RouterFunction<ServerResponse> productRouter(ProductHandler handler) {
        return RouterFunctions.route(
                RequestPredicates.GET("/api/products"),
                handler::findAll
            )
            .andRoute(
                RequestPredicates.GET("/api/products/{id}"),
                handler::findById
            );
    }
}
```

Với functional routes, springdoc cần metadata để biết operationId, summary, parameter và response. Có thể dùng `@RouterOperation` cho một route hoặc `@RouterOperations` cho nhiều route trong cùng bean. `operationId` là metadata quan trọng và cần được khai báo duy nhất.

Ví dụ khai báo nhiều route:

```java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "findAll",
        operation = @Operation(
            operationId = "products_findAll",
            summary = "Liệt kê sản phẩm",
            tags = {"Products"},
            responses = @ApiResponse(
                responseCode = "200",
                description = "Danh sách sản phẩm",
                content = @Content(
                    schema = @Schema(
                        type = "array",
                        implementation = ProductResponse.class
                    )
                )
            )
        )
    ),
    @RouterOperation(
        path = "/api/products/{id}",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "findById",
        operation = @Operation(
            operationId = "products_findById",
            summary = "Lấy sản phẩm theo ID",
            tags = {"Products"}
        )
    )
})
RouterFunction<ServerResponse> productRouter(ProductHandler handler) {
    return RouterFunctions.route(
            RequestPredicates.GET("/api/products"), handler::findAll
        )
        .andRoute(
            RequestPredicates.GET("/api/products/{id}"), handler::findById
        );
}
```

Đây là ví dụ định hướng; import `RouterOperation`/`RouterOperations` từ package springdoc của major version đang dùng và hoàn thiện response metadata cho từng operation. Với một bean chứa nhiều route, khai báo `path` và HTTP method cho từng route để springdoc ghép metadata với endpoint chính xác.

Springdoc cũng hỗ trợ functional DSL để gắn operation metadata ngay trong quá trình khai báo route. Cách này hữu ích nếu nhóm phát triển muốn route và mô tả OpenAPI nằm cạnh nhau thay vì tách annotation.

## 9. Chọn WebFlux API hay WebFlux UI theo cách phân phối tài liệu

Không phải mọi ứng dụng đều cần nhúng Swagger UI vào production runtime.

| Tình huống | Lựa chọn gợi ý | Lý do |
|---|---|---|
| API nội bộ, developer cần thử request trực tiếp | `webflux-ui` | Có Swagger UI cùng OpenAPI |
| CI tải OpenAPI để lint hoặc so sánh contract | `webflux-api` | Chỉ cần JSON/YAML, không cần UI |
| Tài liệu được publish lên API portal riêng | `webflux-api` | Portal có thể lấy document từ endpoint hoặc build artifact |
| Microservice production không muốn cung cấp UI | `webflux-api` hoặc chỉ expose document theo policy | Giảm giao diện runtime không cần thiết |
| Developer portal muốn giao diện Scalar tích hợp trong ứng dụng | `webflux-scalar` | Có giao diện Scalar và OpenAPI document |
| Developer portal cần nhiều API group | `webflux-ui` hoặc `webflux-api` tùy nơi render | Grouped OpenAPI vẫn được tạo; UI chỉ cần khi muốn xem trực tiếp |

Có thể tắt Swagger UI theo profile nếu dùng UI starter nhưng không muốn cung cấp giao diện ở một số môi trường:

```yaml
springdoc:
  swagger-ui:
    enabled: false
```

OpenAPI JSON/YAML vẫn có thể được bật độc lập qua `springdoc.api-docs.enabled`. Nếu muốn ẩn cả tài liệu máy đọc ở production, cấu hình `springdoc.api-docs.enabled: false` hoặc bảo vệ endpoint bằng Spring Security theo chính sách triển khai.

## 10. Endpoint tài liệu và cấu hình cơ bản

Với cấu hình mặc định, springdoc công bố:

| Endpoint | Nội dung |
|---|---|
| `/v3/api-docs` | OpenAPI JSON |
| `/v3/api-docs.yaml` | OpenAPI YAML |
| `/swagger-ui.html` | Trang Swagger UI hoặc redirect tới resource UI |
| `/scalar` | Giao diện Scalar khi dùng Scalar starter |

Có thể đổi đường dẫn tài liệu:

```yaml
springdoc:
  api-docs:
    path: /api/openapi
  swagger-ui:
    path: /docs
```

Khi dùng API-only starter, `swagger-ui.path` không có tác dụng vì không có Swagger UI được cài. Đổi `api-docs.path` không thay đổi controller mapping của ứng dụng.

Nếu có nhiều group, springdoc có thể công bố document theo group, ví dụ `/v3/api-docs/public` và `/v3/api-docs/admin`. Group vẫn phải được cấu hình riêng bằng `GroupedOpenApi` hoặc cơ chế tương ứng.

## 11. WebFlux không tự làm mọi thao tác trở thành non-blocking

Một ứng dụng có thể chạy WebFlux nhưng vẫn gọi database hoặc SDK blocking. Điều này dễ gây nghẽn event loop nếu thao tác blocking chạy trực tiếp trên thread xử lý request.

Ví dụ không nên làm trong WebFlux handler:

```java
Mono<ProductResponse> findById(UUID id) {
    ProductEntity entity = jpaRepository.findById(id).orElseThrow();
    return Mono.just(mapper.toResponse(entity));
}
```

`jpaRepository.findById(...)` là blocking. Nó chạy trước khi `Mono` được trả về và có thể giữ thread xử lý request trong suốt thời gian truy vấn.

Giải pháp tốt hơn là dùng reactive driver/repository nếu kiến trúc yêu cầu non-blocking end-to-end. Nếu phải gọi thư viện blocking, cô lập thao tác đó trên scheduler phù hợp và giới hạn concurrency:

```java
Mono<ProductResponse> findById(UUID id) {
    return Mono.fromCallable(() -> jpaRepository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id)))
        .subscribeOn(Schedulers.boundedElastic())
        .map(mapper::toResponse);
}
```

Đây là cách cô lập blocking call, không phải cách biến JPA thành reactive. Cần đo tải, đặt timeout và giới hạn tài nguyên; nếu phần lớn request phụ thuộc JPA, Spring MVC có thể là lựa chọn phù hợp hơn.

Trong controller/handler, tránh gọi `.block()` hoặc `.subscribe()` thủ công để lấy dữ liệu trước khi trả response. Hãy trả publisher để framework điều phối subscription và lifecycle.

## 12. Tránh xung đột dependency và classpath

Khi ứng dụng khởi động sai web stack hoặc springdoc không tạo tài liệu, kiểm tra dependency tree:

```bash
mvn dependency:tree
```

Hoặc Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm các dependency sau:

- `spring-boot-starter-webflux` có mặt khi ứng dụng chọn WebFlux.
- Không có `spring-boot-starter-web` ngoài chủ đích.
- Dùng `springdoc-openapi-starter-webflux-api` hoặc `springdoc-openapi-starter-webflux-ui` đúng major version.
- Không có `springdoc-openapi-starter-webmvc-*` trong ứng dụng WebFlux.
- Không có nhiều phiên bản `springdoc-openapi`, `swagger-core` hoặc Swagger annotations xung đột.

Một thư viện khác có thể kéo `spring-boot-starter-web` transitively. Nếu dependency đó không cần servlet stack, loại trừ dependency MVC theo đúng module gây ra nó. Không thêm `spring.main.web-application-type=reactive` chỉ để che xung đột mà không hiểu nguồn dependency.

## 13. Kiểm tra ứng dụng đang chạy trên WebFlux

Sau khi khởi động, xác nhận ứng dụng dùng reactive web application context. Có thể kiểm tra log startup, dependency tree và server runtime. Nếu dùng Actuator, một số endpoint thông tin có thể giúp kiểm tra nhưng cần bảo vệ chúng.

Sau đó xác minh tài liệu:

1. Gọi `/v3/api-docs` và xác nhận HTTP 200 với JSON hợp lệ.
2. Gọi `/v3/api-docs.yaml` nếu cần phát hành YAML.
3. Nếu dùng UI starter, mở `/swagger-ui.html` và xác nhận Swagger UI tải document đúng.
4. Kiểm tra controller annotation-based xuất hiện trong `paths`.
5. Kiểm tra functional route có metadata `@RouterOperation`/DSL xuất hiện trong `paths`.
6. Kiểm tra reactive return type được mô tả thành response schema đúng, không lộ `Mono` hoặc `Flux` như một object nghiệp vụ.
7. Kiểm tra media type cho endpoint streaming như SSE/NDJSON.

Ví dụ dùng curl:

```bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -i http://localhost:8080/swagger-ui.html
```

Lệnh cuối chỉ áp dụng nếu dùng UI starter và không đổi đường dẫn Swagger UI.

## 14. Kiểm thử WebFlux bằng WebTestClient

WebFlux hỗ trợ `WebTestClient` để kiểm thử endpoint reactive. Có thể dùng client này kiểm tra OpenAPI document mà không cần phụ thuộc vào giao diện trình duyệt:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OpenApiWebFluxTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void exposesOpenApiJson() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.paths['/api/products']").exists();
    }

    @Test
    void exposesSwaggerUiWhenUiStarterIsInstalled() {
        webTestClient.get()
            .uri("/swagger-ui.html")
            .exchange()
            .expectStatus().is3xxRedirection();
    }
}
```

Test Swagger UI phụ thuộc cách starter phục vụ resource và path tùy chỉnh; có thể trả redirect hoặc HTML theo cấu hình. Nếu dùng API-only starter, bỏ test UI vì endpoint đó không tồn tại.

Với functional routes, thêm assertion để kiểm tra operationId và response schema trong document. Nếu route có chạy nhưng không xuất hiện trong OpenAPI, kiểm tra metadata router annotation/DSL và path/method đã khai báo.

## 15. Những lỗi thường gặp khi chọn starter

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `/v3/api-docs` trả 404 | Thiếu springdoc starter hoặc dùng sai starter web stack | Dùng đúng `webflux-api`/`webflux-ui` |
| Swagger UI trả 404 nhưng OpenAPI JSON hoạt động | Chỉ cài `webflux-api` | Đổi sang `webflux-ui` nếu cần giao diện |
| WebFlux controller chạy nhưng ứng dụng thực tế là MVC | Có cả `spring-boot-starter-web` và `webflux` | Kiểm tra dependency tree và loại starter không cần |
| Class `org.springdoc...` không tồn tại khi compile | Dùng import/API của major version khác | Đối chiếu springdoc 1.x, 2.x hoặc 3.x |
| Spring Boot báo lỗi tương thích Spring Framework | Chọn springdoc major/minor không khớp Boot | Kiểm tra compatibility matrix và dependency management |
| Functional route không xuất hiện trong tài liệu | Chưa khai báo `@RouterOperation`, `@RouterOperations` hoặc DSL metadata | Bổ sung operationId, path, method và response metadata |
| Schema hiển thị `Mono`/`Flux` sai như model | Dùng custom wrapper hoặc converter không được nhận diện | Kiểm tra kiểu trả về và schema annotation trong document |
| Ứng dụng WebFlux bị chậm hoặc nghẽn | Có blocking call trên event loop | Dùng reactive driver hoặc cô lập blocking work có giới hạn |
| Swagger UI hoạt động nhưng Try it out gọi sai URL | Server URL/context path/proxy config không đúng | Kiểm tra OpenAPI `servers`, forwarded headers và proxy |
| API docs chạy ở local nhưng bị 401/403 trên môi trường | Spring Security bảo vệ endpoint tài liệu | Cấu hình quyền truy cập cho `/v3/api-docs/**` và Swagger UI theo policy |

## 16. Quy trình chọn và thêm starter

Khi tích hợp springdoc vào một ứng dụng reactive, thực hiện theo thứ tự:

1. Xác nhận ứng dụng đang dùng Spring MVC hay Spring WebFlux.
2. Kiểm tra dependency server và các thư viện truy cập dữ liệu; xác định có cần non-blocking end-to-end không.
3. Xác định Spring Boot major version để chọn springdoc 1.x, 2.x hoặc 3.x tương ứng.
4. Chọn `webflux-api` nếu chỉ cần OpenAPI JSON/YAML; chọn `webflux-ui` nếu cần Swagger UI.
5. Loại dependency MVC không cần thiết và kiểm tra dependency tree.
6. Bổ sung metadata cho controller hoặc functional routes.
7. Khởi động ứng dụng và kiểm tra `/v3/api-docs`, YAML và UI nếu có.
8. Kiểm thử reactive endpoint, streaming media type, security và proxy path.
9. So sánh OpenAPI document với hợp đồng mong muốn trước khi phát hành.

Chọn đúng WebFlux starter giúp springdoc đọc đúng web stack và tạo tài liệu phù hợp với kiến trúc reactive. Quyết định WebFlux nên dựa trên mô hình I/O của ứng dụng; còn quyết định `api` hay `ui` dựa trên cách nhóm phát triển và consumer cần sử dụng tài liệu.

## 17. Tài liệu tham khảo

- [Springdoc OpenAPI – Spring WebFlux support](https://springdoc.org/modules.html): starter WebFlux API và Swagger UI.
- [Springdoc OpenAPI – Scalar support](https://springdoc.org/modules.html): starter WebFlux Scalar cho dòng springdoc hiện hành.
- [Springdoc OpenAPI v2 – Spring WebFlux support](https://springdoc.org/v2/modules.html): artifact `springdoc-openapi-starter-webflux-api` và `springdoc-openapi-starter-webflux-ui` cho Spring Boot 3.
- [Springdoc OpenAPI v1 – Spring WebFlux support](https://springdoc.org/v1/modules.html): artifact WebFlux của dòng springdoc 1.x.
- [Springdoc OpenAPI – Migrating from v1 to v2](https://springdoc.org/v2/migrating-from-springdoc-v1.html): ánh xạ `springdoc-openapi-webflux-core` sang `springdoc-openapi-starter-webflux-api`.
- [Springdoc OpenAPI – Compatibility Matrix](https://springdoc.org/#what-is-the-compatibility-matrix-of-spring-boot-with-springdoc-openapi-): tương thích giữa Spring Boot và springdoc.
- [Springdoc OpenAPI – Functional Endpoints](https://springdoc.org/features.html#spring-webfluxwebmvc-fn-with-functional-endpoints): `@RouterOperation`, `@RouterOperations` và functional DSL.
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): kiến trúc reactive web framework.
- [Spring Boot – Web Reactive](https://docs.spring.io/spring-boot/reference/web/reactive.html): cấu hình reactive web application và lựa chọn server.
- [Spring Boot – Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): starter WebClient riêng của Spring Boot 4 và các starter web.
- [Reactor – Reactive Programming](https://projectreactor.io/docs/core/release/reference/): `Mono`, `Flux`, scheduler và nguyên tắc không blocking event loop.
