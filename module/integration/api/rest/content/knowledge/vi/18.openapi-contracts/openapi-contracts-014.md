# springdoc-openapi và chọn phiên bản phù hợp Spring Boot

## 1. Mục tiêu: tài liệu OpenAPI phải chạy cùng phiên bản ứng dụng

Hợp đồng REST cho frontend, đối tác và kiểm thử cần mô tả **URI, method, parameter, schema, status và xác thực**. Viết OpenAPI tay dễ lệch code; sinh tự động cũng có thể bỏ sót **điều kiện nghiệp vụ**.

**springdoc-openapi** phân tích Spring MVC/WebFlux, controller, DTO, Bean Validation và annotation để sinh tài liệu **OpenAPI 3** (JSON/YAML), kèm Swagger UI nếu chọn UI starter. Đây là thư viện cộng đồng, **không thuộc Spring Boot core** và **không thay thế bảo mật hay kiểm thử hợp đồng**.

**springdoc 2.x không phải OpenAPI 2**: 2.x là phiên bản *thư viện*, tài liệu vẫn là **OpenAPI 3.x**. **Boot 3.x và 4.x dùng nhánh springdoc khác nhau**; chọn sai có thể gây lỗi startup, HTTP 500 hoặc UI không đọc được spec.

Bài thuộc chương **Hợp đồng OpenAPI** của module **INTEGRATION_API_REST**. Sau bài học, bạn sẽ:

1. Chọn **major/minor springdoc** theo Spring Boot và web stack bằng ma trận chính thức.
2. Cài đúng starter Maven/Gradle và kiểm chứng endpoint `/v3/api-docs` cùng Swagger UI.
3. Viết annotation OpenAPI và mô tả những điều **không thể suy ra tự động từ code**.
4. Bảo vệ endpoint tài liệu, xử lý lỗi tương thích, test contract và quản lý nâng cấp.

Ví dụ chính dùng **Spring Boot 3.5.x + springdoc 2.10.0 + Spring MVC**; các điểm khác của Boot 4 sẽ được nêu riêng. **Thông tin phiên bản được đối chiếu với tài liệu springdoc ngày 18/11/2026** và có thể thay đổi: khi cài thật luôn kiểm tra lại [compatibility matrix chính thức của nhánh v2](https://springdoc.org/v2/) và [FAQ nhánh hiện hành](https://springdoc.org/faq.html).

## 2. Chọn phiên bản: đừng đoán từ số major

### 2.1. Ma trận được công bố

| Spring Boot | Nhánh springdoc-openapi | Khoảng phiên bản được tài liệu chính thức liệt kê | Ghi chú |
|---|---|---|---|
| **4.1.x** | **3.x** | **3.1.x – 3.2.x** | Tài liệu nhánh 3.x |
| **4.0.x** | **3.x** | **3.0.x** | Ưu tiên đối chiếu patch/test cho Boot 4.0 cụ thể |
| **3.5.x** | **2.x** | **2.8.x – 2.10.x** | Ví dụ bài chọn 2.10.0 |
| **3.4.x** | **2.x** | **2.7.x – 2.8.x** | Không tự nâng major lên 3.x |
| **3.3.x** | **2.x** | **2.6.x** | Kiểm tra patch/compatibility trước nâng |
| **3.2.x** | **2.x** | **2.3.x – 2.5.x** | Có khác biệt parameter name discovery |
| **3.1.x** | **2.x** | **2.2.x** | Không mặc định dùng starter mới nhất |
| **3.0.x** | **2.x** | **2.0.x – 2.1.x** | Dòng Boot 3 đời đầu |
| **2.x** | **1.x** | Nhánh legacy, không nên khởi tạo dự án mới | Lên kế hoạch nâng Boot và springdoc đồng thời |

Theo tài liệu tại thời điểm biên soạn, bản ổn định mới được nhánh 2.x giới thiệu là **2.10.0**, nhánh 3.x là **3.2.0**. Đây **không** phải lời khuyên “luôn thay dependency bằng 3.2.0”: trước hết xác định **Boot major/minor**, sau đó chọn springdoc trong khoảng đã được xây dựng/kiểm thử tương ứng và chạy test ở chính môi trường của bạn.

**Lưu ý về ma trận:** đây là những khoảng mà dự án springdoc công bố đã build/kiểm thử, **không phải một định lý rằng mọi phiên bản ngoài khoảng đều chắc chắn hỏng**. Với thay đổi patch hoặc backport, hãy căn cứ release notes, dependency tree và integration test thay vì phỏng đoán.

### 2.2. Ba con số dễ nhầm

~~~text
Spring Boot 3.5.x  ->  springdoc-openapi 2.10.0  ->  OpenAPI 3.x
Spring Boot 4.1.x  ->  springdoc-openapi 3.2.0   ->  OpenAPI 3.x
       ^                    ^                         ^
 runtime/framework    thư viện sinh docs       định dạng hợp đồng
~~~

Đường dẫn `/v3/api-docs` cũng **không có nghĩa** springdoc phải là phiên bản 3.x. `v3` ở URL này là convention của endpoint tài liệu OpenAPI 3.

### 2.3. Quy trình chọn dependency

1. Xác định **Boot version đang được BOM/plugin quản lý**, stack **MVC/WebFlux** và nhu cầu **API-only/UI**.
2. Tra đúng [springdoc v2](https://springdoc.org/v2/) cho Boot 3 hoặc [springdoc 3.x](https://springdoc.org/) cho Boot 4; chọn patch phù hợp, **pin version**.
3. Kiểm tra dependency graph, khởi động, GET `/v3/api-docs` và test hợp đồng/security.

**Java:** Spring Boot 3 và 4 đều yêu cầu baseline Java phù hợp phiên bản Boot; nhiều cấu hình điển hình dùng Java 17+. Tuy nhiên hãy tuân thủ **yêu cầu Java của đúng Boot release đang chạy**, không lấy “Java 17+” làm bằng chứng mọi tổ hợp dependency đều tương thích.

## 3. Chọn starter theo stack và nhu cầu

| Ứng dụng | Chỉ sinh `/v3/api-docs` | Cần cả Swagger UI |
|---|---|---|
| **Spring MVC** | `springdoc-openapi-starter-webmvc-api` | `springdoc-openapi-starter-webmvc-ui` |
| **Spring WebFlux** | `springdoc-openapi-starter-webflux-api` | `springdoc-openapi-starter-webflux-ui` |

Các artifact trên thuộc group **`org.springdoc`**. UI starter thường kéo theo phần API cần thiết; **không thêm đồng thời cả `-api` và `-ui` khi không có lý do cụ thể**. Dùng **cùng version springdoc** cho các module bổ sung, tránh lắp hỗn hợp 2.x/3.x.

### 3.1. Maven cho Spring Boot 3.5.x + Spring MVC

~~~xml
<!-- Trích đoạn pom.xml: Boot parent/BOM và starter-web đã được cấu hình -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Nếu chỉ muốn file OpenAPI mà không phục vụ UI, đổi artifact thành `springdoc-openapi-starter-webmvc-api`. Đây là ví dụ cho **Boot 3.5.x**: **không** copy 2.10.0 sang ứng dụng Boot 4.

### 3.2. Gradle tương ứng

~~~groovy
// build.gradle của dự án Boot 3.5.x / MVC
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-ui:2.10.0'
}
~~~

Nếu dự án dùng WebFlux thật, thay `webmvc-ui` bằng `webflux-ui` và xác nhận không vô tình kéo cả Web MVC/WebFlux làm thay đổi web application type. Phần dependency cho Spring Security, Validation, tests cần bổ sung tùy chức năng ứng dụng.

### 3.3. Nếu dự án đã nâng sang Spring Boot 4

Ví dụ cho **Boot 4.1.x** theo ma trận hiện hành:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Tương tự, Boot 4.0.x cần xem khoảng 3.0.x được công bố và kiểm thử trước khi chọn patch. **Major của springdoc phải đi cùng major của Boot theo ma trận**, không nâng “để mới nhất” một cách độc lập. Khi đổi Boot 3 → 4, hãy nâng Spring/Security/Jackson/Jakarta dependencies theo hướng dẫn Boot, không chỉ sửa một dòng springdoc.

### 3.4. Tránh thư viện cũ và dependency trùng

Tránh trộn `springdoc-openapi-ui`/`webmvc-core` nhánh cũ hoặc **Springfox** với starter mới: handler/converter có thể xung đột. Khi nâng v1 → v2, dùng starter thay module rời; import `GroupedOpenApi` đổi sang `org.springdoc.core.models.GroupedOpenApi`. Xem [migration guide](https://springdoc.org/v2/migrating-from-springdoc-v1.html).

## 4. Khởi động và xác minh endpoint OpenAPI

Khi starter đã tương thích và ứng dụng khởi động bình thường, mặc định:

~~~text
GET /v3/api-docs       -> tài liệu OpenAPI JSON
GET /v3/api-docs.yaml  -> tài liệu OpenAPI YAML
GET /swagger-ui.html   -> trang khởi đầu Swagger UI (khi dùng -ui)
~~~

Swagger UI có thể chuyển hướng đến trang trong `/swagger-ui/`; **endpoint JSON mới là nguồn đặc tả**, không phải HTML của UI. Đường dẫn thực còn phụ thuộc `server.servlet.context-path`, servlet path, reverse proxy hoặc cấu hình springdoc.

Kiểm tra thủ công trên môi trường local:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -i http://localhost:8080/swagger-ui.html
~~~

Response JSON hợp lệ có các phần:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Order Service API",
    "version": "1.0.0"
  },
  "paths": {
    "/v1/orders": {
      "post": {"responses": {"201": {"description": "Created"}}}
    }
  }
}
~~~

Đây là **minh họa cấu trúc**, không phải body đầy đủ do springdoc sinh. Số OpenAPI có thể khác tùy phiên bản và thiết lập `springdoc.api-docs.version`; không kiểm tra bằng cách so chuỗi cố định `3.1.0` cho mọi môi trường.

### 4.1. Cấu hình cần thiết và cấu hình không cần thiết

Trong nhiều ứng dụng, thêm đúng starter là đã đủ để endpoint hoạt động. Chỉ tùy chỉnh khi có nhu cầu:

~~~yaml
# application.yml; các giá trị path tương ứng mặc định phổ biến
springdoc:
  api-docs:
    path: /v3/api-docs
    version: openapi_3_1
  swagger-ui:
    path: /swagger-ui.html
~~~

`springdoc.api-docs.version` chỉ chọn **phiên bản đặc tả**, không sửa lỗi sai nhánh springdoc/Boot hoặc `NoSuchMethodError`.

Nếu UI báo **“Failed to load API definition”**, gọi thẳng `/v3/api-docs`: HTML 200 không chứng minh JSON schema đã sinh đúng.

### 4.2. Cấu hình package, đường dẫn và nhóm

Với nhiều module REST, chỉ công bố những controller được phép:

~~~yaml
springdoc:
  packages-to-scan: com.example.orders.api
  paths-to-match: /v1/**
~~~

Không xem filtering tài liệu như một lớp bảo mật: endpoint `/internal/**` bị ẩn khỏi spec **vẫn có thể được gọi** nếu Spring Security cho phép. Với nhiều hợp đồng/đối tác, có thể dùng `GroupedOpenApi`:

~~~java
@Configuration
class OpenApiGrouping {
    @Bean
    GroupedOpenApi publicOrdersApi() {
        return GroupedOpenApi.builder()
            .group("public-orders")
            .pathsToMatch("/v1/orders/**")
            .build();
    }
}
~~~

Nhánh Spring Boot 3/springdoc 2.x dùng import `org.springdoc.core.models.GroupedOpenApi`. Có thể xem JSON theo group qua `/v3/api-docs/public-orders` khi cấu hình phù hợp. Không tạo hàng chục nhóm tùy tiện: mỗi nhóm cần có owner và test contract riêng.

## 5. Ví dụ Java/Spring: DTO, endpoint và chú thích hợp đồng

`@PostMapping` cung cấp method/path nhưng springdoc **không tự biết** lý do 409, TTL idempotency, quyền tenant hoặc schema lỗi. Các chi tiết ấy cần tài liệu và test riêng.

### 5.1. OpenAPI metadata và Bearer security scheme

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Order Service API",
        version = "1.0.0",
        description = "REST API quản lý đơn hàng"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiConfig {}
~~~

Security scheme **mô tả cách client gọi API** và giúp Swagger UI hiển thị `Authorize`. **Nó không tự xác minh JWT**; Spring Security vẫn cần cấu hình OAuth2 Resource Server hoặc bộ xác thực tương đương.

### 5.2. DTO có Bean Validation và Schema

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

@Schema(description = "Yêu cầu tạo đơn")
public record CreateOrderRequest(
    @NotBlank
    @Schema(description = "Mã sản phẩm", example = "SKU-120")
    String productCode,

    @Min(1)
    @Schema(description = "Số lượng, ít nhất 1", example = "2")
    int quantity
) {}

public record OrderResponse(
    String id,
    String status,
    long totalAmount
) {}
~~~

`@NotBlank`, `@Min` là **ràng buộc runtime** khi controller sử dụng `@Valid` và validation được cấu hình; `@Schema` giải thích hợp đồng và ví dụ. Java record với `int quantity` là primitive **không thể null**; nếu cần phân biệt “field vắng mặt” với “0”, dùng `Integer` kèm `@NotNull`. Tài liệu sinh ra phải phản ánh serialization thật; không giả định mọi annotation tạo ra cùng `required` trong mọi phiên bản.

### 5.3. Controller mô tả method, status, header và security

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/orders")
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @Operation(
        summary = "Tạo đơn hàng",
        description = "Cùng Idempotency-Key và payload chỉ tạo một ý định.",
        security = @SecurityRequirement(name = "bearerAuth")
    )
    @ApiResponses({
        @ApiResponse(responseCode = "201", description = "Đã tạo đơn",
            content = @Content(schema =
                @Schema(implementation = OrderResponse.class))),
        @ApiResponse(responseCode = "400",
            description = "Payload hoặc header không hợp lệ"),
        @ApiResponse(responseCode = "401",
            description = "Chưa xác thực"),
        @ApiResponse(responseCode = "403",
            description = "Không đủ quyền tạo đơn"),
        @ApiResponse(responseCode = "409",
            description = "Xung đột trạng thái hoặc request đang xử lý")
    })
    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest input,
        @Parameter(
            description = "Khóa chống trùng của cùng một ý định",
            required = true,
            in = ParameterIn.HEADER
        )
        @RequestHeader("Idempotency-Key") String idempotencyKey
    ) {
        // Service phải lấy principal/tenant đã được xác thực.
        OrderResponse result = service.create(input, idempotencyKey);
        return ResponseEntity
            .created(URI.create("/v1/orders/" + result.id()))
            .body(result);
    }
}
~~~

Ví dụ minh họa cách **document API**, không cung cấp implementation của `OrderService`, import `URI`, Spring Security hay handler lỗi. Khi dùng trong dự án thật, service phải lấy actor/tenant từ security context đã xác thực, có idempotency ledger, xử lý lỗi và phân quyền đúng; không để controller hoặc Swagger UI tự thay thế các kiểm tra đó.

Hợp đồng nên nêu rõ `201` kèm `Location`, retry cùng key/payload, trường hợp key bị tái dùng cho payload khác (có thể là `422` nếu sản phẩm chọn), và response `application/problem+json`. Springdoc **không tự suy ra tất cả những nghiệp vụ này** từ method signature; cần annotation bổ sung hoặc customizer thích hợp.

### 5.4. Mã trạng thái và response không thành công

Kiểm tra status **thực tế** như 201/202/204/409, không mặc định 200. `@ApiResponse` chỉ tạo tài liệu: nếu service ném exception không được map, runtime vẫn trả 500. Lỗi nên có schema `ProblemDetail`/`application/problem+json` theo hợp đồng, không chỉ mô tả “Bad Request”.

## 6. Những phần springdoc sinh được và những phần phải kiểm tra thủ công

| Thành phần hợp đồng | Springdoc thường suy được từ | Phần vẫn cần tác giả API làm rõ |
|---|---|---|
| URI và method | `@RequestMapping`, `@GetMapping`, `@PostMapping` | Resource modeling, lifecycle và business semantics |
| Query/path/header parameters | Controller signature, `@RequestParam`, `@PathVariable` | Default thật, sort/filter whitelist, giới hạn, đặc tả lỗi |
| JSON schema | DTO/record, Jackson, Bean Validation, `@Schema` | Nullability, polymorphism, kiểu tiền, định dạng thời gian, dữ liệu ẩn |
| Response status | Return type, annotation `@ApiResponse`, `@ResponseStatus` | Điều kiện chính xác của 201/202/204/409/412/429, body lỗi |
| Auth mechanism | `@SecurityScheme`, `@SecurityRequirement` | Runtime authentication/authorization, tenant/owner/role policy |
| Pagination | Pageable/converter, các parameter tự định nghĩa | Stable sort, cursor opaque, replay/filter consistency |
| Idempotency | Header được chú thích | Scope, fingerprint, TTL, retry, replay outcome |
| Async jobs và file upload | Mapping/body/content type được khai báo | Polling, status state-machine, scan/approval, file limits |

Trong spec sinh ra, kiểm tra `paths./v1/orders.post` có `parameters` (Idempotency-Key), `requestBody` (CreateOrderRequest), `responses.201` và `security: [{bearerAuth: []}]`. **Security scheme** trong `components.securitySchemes` và **operation security requirement** là hai thành phần khác nhau; chỉ khai báo bearerAuth trong components **chưa khiến mọi operation yêu cầu token**.

### 6.1. OpenAPI 3.0 và 3.1 không cùng schema semantics

Đặc tả OpenAPI 3.1 đồng bộ hơn với JSON Schema hiện đại; ví dụ một field có thể mô tả null bằng:

~~~yaml
type:
  - string
  - "null"
~~~

OpenAPI 3.0 thường dùng `nullable: true`. Không nên biến JSON Schema 3.1 thành 3.0 bằng cách thay mỗi dòng `openapi: 3.1.0` thành `openapi: 3.0.3`. Nếu đối tác hoặc công cụ codegen chưa hỗ trợ OpenAPI 3.1 đầy đủ, có thể chọn đầu ra 3.0 qua cấu hình **nếu phiên bản springdoc hỗ trợ**, nhưng phải **validate đặc tả được sinh và test client generator thực tế**.

### 6.2. Bean Validation không tự đại diện mọi quy tắc nghiệp vụ

`@NotBlank`/`@Min` mô tả ràng buộc đơn giản, không tự bảo vệ hạn mức tổ chức, quyền duyệt hay giỏ đã checkout. Các quy tắc nghiệp vụ cần response code, mô tả và test riêng.

### 6.3. Không làm lộ model nội bộ qua tài liệu

Dùng **DTO công khai**, không xuất JPA entity có password hash hay field nội bộ. `@Schema(hidden = true)` chỉ ẩn field **trong tài liệu**, không chặn serialization; `@Hidden` chỉ ẩn operation khỏi spec, không chặn truy cập endpoint. Bảo mật ở runtime vẫn bắt buộc.

## 7. Bảo mật Swagger UI và endpoint tài liệu

Tài liệu có thể tiết lộ cấu trúc API và field nội bộ. Phân loại rõ **public**, **partner** và **internal-only**.

### 7.1. Tách môi trường local khỏi production

Một lựa chọn phổ biến: cho truy cập tài liệu trên **local/dev**, không phát UI/spec qua public production:

~~~yaml
# application-prod.yml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Hai switch **độc lập**: tắt UI không tắt `/v3/api-docs`. Nếu phải công bố tài liệu ở production, dùng gateway/portal có quyền riêng hoặc publish artifact đã kiểm tra.

### 7.2. Spring Security cho môi trường phát tài liệu

Trong local/dev **đã được giới hạn mạng**, có thể cho phép truy cập các resource tài liệu và yêu cầu xác thực với endpoint nghiệp vụ:

~~~java
@Configuration
@Profile("local")
class LocalSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/v3/api-docs/**",
                "/swagger-ui.html",
                "/swagger-ui/**"
            ).permitAll()
            .anyRequest().authenticated()
        );
        http.oauth2ResourceServer(oauth -> oauth.jwt(
            Customizer.withDefaults()
        ));
        return http.build();
    }
}
~~~

Đây là **cấu hình minh họa cho profile local**; cần import và cấu hình Resource Server/JWT đầy đủ, đồng thời có SecurityFilterChain phù hợp ở những profile khác. Không copy `permitAll` cho docs vào production nếu chính sách yêu cầu bảo vệ tài liệu. Với ứng dụng dùng session/cookie thay vì bearer stateless, cần thiết kế **CSRF và session security** đúng với loại client; springdoc không tự cấu hình các phần này.

Nút `Authorize` chỉ hỗ trợ `Try it out`; **không bảo vệ UI/spec**. Server/gateway phải kiểm soát quyền đọc tài liệu **và** quyền gọi API.

### 7.3. Reverse proxy, context path và browser security

Với `server.servlet.context-path=/shop`, URL docs/UI thêm tiền tố `/shop`. Chỉ tin forwarded headers từ **proxy tin cậy**. Giới hạn CORS, không nhập token production vào Swagger UI không đáng tin và cẩn thận với `Try it out` trên POST có side effect.

## 8. Chẩn đoán sự cố do sai phiên bản hoặc cấu hình

| Triệu chứng | Nguyên nhân cần kiểm tra trước | Cách xác minh/sửa |
|---|---|---|
| Startup lỗi `NoSuchMethodError` / `NoClassDefFoundError` liên quan Spring hoặc swagger | Nhánh springdoc không hợp Boot, dependency transitives bị trộn | Đối chiếu ma trận, kiểm tra dependency tree, loại version ép tay không phù hợp |
| Boot 3.x nhưng dùng springdoc 3.x | Nhầm major thư viện với OpenAPI 3 | Chuyển về springdoc **2.x** phù hợp Boot minor |
| Boot 4.x nhưng dùng springdoc 2.x | Spring Framework/Boot API không cùng thế hệ | Dùng springdoc **3.x** phù hợp Boot minor |
| `GET /v3/api-docs` trả 404 | Chưa có starter, docs bị tắt, context path/custom path | Kiểm tra dependency và property, request đúng base URL |
| Docs trả 401/403 | Security filter/gateway chặn | Kiểm tra policy docs, không tắt authentication bừa |
| Swagger UI hiển thị HTML nhưng “Failed to load API definition” | JSON docs trả lỗi, UI fetch sai URL/path, CORS hoặc proxy | Mở network tab và gọi trực tiếp `/v3/api-docs` |
| JSON docs trả 500 | Converter, schema introspection, version mismatch hoặc cấu hình đặc thù | Đọc server stack trace, kiểm tra bản springdoc/Boot và converter |
| Path parameter hiện không đúng tên | Java thiếu metadata tên parameter hoặc mapping chưa rõ | Compile với `-parameters`, kiểm tra `@PathVariable("id")` |
| Endpoint không xuất hiện trong spec | `packages-to-scan` / `paths-to-match`, `@Hidden`, profile/conditional bean | Xem endpoint runtime và filter tài liệu |
| UI mở sai scheme/host sau proxy | Context path và forwarding không nhất quán | Kiểm tra trusted proxy, `Forwarded` headers và UI config URL |
| Spec chạy nhưng client generate sai nullable/type | Khác biệt OpenAPI 3.0/3.1, codegen chưa hỗ trợ | Validate schema và chạy codegen/contract test có kiểm soát |

### 8.1. Đừng sửa lỗi bằng cách thêm nhiều jar vào classpath

Nếu `/v3/api-docs` trả 500, thêm `swagger-core` hoặc `swagger-annotations` bản bất kỳ để “đủ class” có thể tạo ra mâu thuẫn runtime mới. Hãy xác định **một ma trận version nhất quán**, kiểm tra dependencies do starter kéo về và tìm nơi nào **BOM hoặc dependency override** đang ép phiên bản khác.

Một trình tự chẩn đoán tốt là: xác định Boot version → xác định springdoc starter/version → in dependency tree → gọi JSON docs trực tiếp → đọc stack trace → tạo integration test tối thiểu. Chỉ khi biết nguyên nhân mới override một dependency, kèm test để tránh tái phát.

### 8.2. Parameter discovery trên Spring Boot 3.2+

Tài liệu springdoc ghi nhận sự thay đổi trong **parameter name discovery** từ Spring Boot 3.2. Với Java, nên biên dịch có metadata `-parameters`. Ví dụ Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Hoặc Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Đồng thời khai báo tên `@PathVariable("orderId")` / `@RequestParam("page")` tường minh khi giúp code dễ đọc. Nếu tài liệu thiếu parameter, đừng kết luận ngay rằng springdoc sai phiên bản: kiểm tra cả annotation, compiler metadata và filter paths.

## 9. Kiểm thử hợp đồng và nâng cấp có kiểm soát

Đừng dừng ở việc **Swagger UI mở được**. Một regression có thể âm thầm đổi `required`, media type, security requirement, field nullable hoặc response status khiến SDK đối tác hỏng dù Java build thành công.

### 9.1. Kiểm thử spec thực sự do ứng dụng sinh

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("local") // Profile local bật API docs
class OpenApiContractTest {
    @Autowired MockMvc mvc;

    @Test
    void generatedSpecificationContainsOrderContract()
            throws Exception {
        mvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.info.title")
                .value("Order Service API"))
            .andExpect(jsonPath(
                "$.paths['/v1/orders'].post.responses['201']")
                .exists())
            .andExpect(jsonPath(
                "$.paths['/v1/orders'].post.security[0].bearerAuth")
                .isArray())
            .andExpect(jsonPath(
                "$.components.securitySchemes.bearerAuth.scheme")
                .value("bearer"));
    }
}
~~~

Đoạn code cần import JUnit/MockMvc/jsonPath và ứng dụng mẫu; `@ActiveProfiles("local")` giả định local security cho phép đọc docs. Nếu sản phẩm dùng một policy khác, test phải gửi credential thích hợp. Không ép giá trị `openapi` luôn là `3.1.0` nếu dự án cho phép cấu hình 3.0.

**Bộ test tối thiểu khi đổi springdoc hoặc Boot:**

| Ca | Xác minh |
|---|---|
| V01 | Ứng dụng khởi động, `/v3/api-docs` trả JSON hợp lệ |
| V02 | Mọi public operation quan trọng vẫn có path, method, request/response schema |
| V03 | 201/202/204, 400/401/403/409 và Problem Details đúng hợp đồng |
| V04 | Security scheme **và** security requirement xuất hiện đúng operation |
| V05 | `required`, enum, nullable, `format`, constraints và content type không trôi ngoài dự kiến |
| V06 | UI tải schema thành công qua context path/proxy, nếu được bật |
| V07 | API runtime vẫn từ chối thiếu quyền, không phụ thuộc việc operation được ẩn trong spec |
| V08 | Production không công bố UI/docs ngoài chính sách; không rò DTO nội bộ |

Lưu một **bản spec đã được duyệt**, chạy OpenAPI validator/linter, rồi dùng **semantic diff** để phát hiện thay đổi breaking; đặc biệt hữu ích trước khi phát hành SDK. Test `/v3/api-docs` là **integration test**; unit test controller không thay thế được việc kiểm tra các converter, auto-configuration và classpath thật.

### 9.2. Quy trình nâng Spring Boot mà không làm lệch hợp đồng

Khi nâng Boot 3.5 → 4.1: xác nhận yêu cầu JDK/framework → đổi springdoc **2.x → 3.x** tương ứng → đối chiếu migration notes → kiểm tra dependency tree → chạy test OpenAPI/security → so sánh spec trước/sau → thử Swagger UI và client SDK. Nếu fail, **không chỉ quay lại bằng cách đổi springdoc version** mà bỏ qua các thay đổi Boot/Security/serialization đã được nâng cùng lúc.

## 10. Bài tập lựa chọn phiên bản và xử lý sự cố

**Tình huống A:** một dự án dùng **Spring Boot 3.5.x** với `springdoc-openapi-starter-webmvc-ui:3.2.0`. Khi truy cập `/v3/api-docs` nhận 500; người phát triển định đổi `springdoc.api-docs.version` từ OpenAPI 3.1 sang 3.0.

**Trả lời:** phải sửa **nhánh springdoc 3.x → 2.x**, chọn phiên bản đã kiểm thử với Boot 3.5 như **2.10.0**. Đổi phiên bản đặc tả OpenAPI **không sửa** vấn đề tương thích framework. Sau đó kiểm tra dependency tree, startup và spec.

**Tình huống B:** dự án **Spring Boot 4.1.x** muốn dùng Swagger UI và `/v3/api-docs`. Hãy chọn dependency.

**Trả lời:** với Spring MVC dùng `org.springdoc:springdoc-openapi-starter-webmvc-ui:3.2.0` theo ma trận đang được công bố; với WebFlux chọn artifact `-webflux-ui` cùng nhánh/phiên bản. Nếu chỉ cần JSON/YAML, chọn starter `-api`. Kiểm tra lại bản patch phù hợp lúc triển khai.

**Tình huống C:** Swagger UI hiển thị nhưng không tải spec; request trong browser trả 403 cho `/v3/api-docs`.

**Trả lời:** kiểm tra SecurityFilterChain/gateway, quyền đọc docs, context path và cookie/token. Đừng thêm `permitAll("/**")` để “sửa nhanh”; nó có thể mở cả các endpoint nghiệp vụ. Cấp quyền có chủ đích cho tài liệu hoặc tắt UI ở môi trường không cho phép.

**Tình huống D:** Springdoc sinh đủ path POST nhưng thiếu response 409 và không thể hiện tenant permission. Phải thay phiên bản springdoc?

**Trả lời:** chưa đủ cơ sở. Thêm `@ApiResponse(409)`, mô tả Problem Details và policy nghiệp vụ; test hành vi thật. Authorization theo tenant **phải được thực thi trong service**, không chỉ mô tả ở OpenAPI.

## 11. Checklist phát hành

- [ ] Đã xác định **Boot major/minor**, web stack MVC/WebFlux và JDK của ứng dụng.
- [ ] Chọn đúng **springdoc 2.x cho Boot 3 / 3.x cho Boot 4**, đối chiếu matrix và patch hiện hành.
- [ ] Dùng starter `-api` hoặc `-ui` đúng nhu cầu, không trộn jar cũ/v1/Springfox không cần thiết.
- [ ] `/v3/api-docs` sinh JSON/YAML hợp lệ; Swagger UI tải được nếu bật.
- [ ] Spec phản ánh URI, method, DTO, validation, media type và **HTTP status thực**.
- [ ] Đã mô tả bearer/OAuth2 **trên operation**, không nhầm với runtime Spring Security.
- [ ] Đã mô tả các quy tắc không suy được tự động: tenant ACL, cursor, idempotency, async workflow.
- [ ] Docs/UI được kiểm soát theo môi trường; thông tin nội bộ không bị public do mặc định.
- [ ] Kiểm tra context path/proxy, `-parameters` và các converter nếu tài liệu thiếu hoặc lỗi 500.
- [ ] Có integration test spec, test runtime security và diff contract trước khi nâng phiên bản.

**Tài liệu chính thức:** [springdoc v2 cho Boot 3](https://springdoc.org/v2/), [springdoc 3.x cho Boot 4](https://springdoc.org/), [Getting started v2](https://springdoc.org/v2/getting-started.html), [Migration v1 → v2](https://springdoc.org/v2/migrating-from-springdoc-v1.html), [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.0), [Springdoc properties v2](https://springdoc.org/v2/properties.html).

**Kết luận:** chọn springdoc theo **phiên bản Spring Boot và web stack trước**, rồi mới chọn UI/API starter và phiên bản OpenAPI được sinh. Một hợp đồng đáng tin cần **endpoint docs chạy được, schema đúng nghiệp vụ, bảo mật thực thi và kiểm thử phát hiện drift** — không chỉ một trang Swagger UI đẹp.
