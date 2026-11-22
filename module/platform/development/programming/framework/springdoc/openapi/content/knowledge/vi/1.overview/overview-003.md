# Tài liệu dạng JSON hoặc YAML và giao diện tương tác

## 1. Vai trò của OpenAPI document trong ứng dụng Spring Boot

Một API HTTP cần có hợp đồng rõ ràng để client biết endpoint nào tồn tại, gửi parameter và request body ra sao, nhận response nào, dùng kiểu dữ liệu gì và phải xác thực như thế nào. Nếu hợp đồng chỉ nằm trong mã nguồn hoặc được ghi thủ công ở một nơi khác, tài liệu rất dễ lệch khỏi hành vi thật của ứng dụng.

Springdoc OpenAPI giúp tạo OpenAPI document từ ứng dụng Spring Boot. Thư viện phân tích các request mapping, controller method, DTO, Jackson metadata, Bean Validation và Swagger annotations để mô tả API thành một tài liệu có cấu trúc.

Trong module SPRINGDOC_OPENAPI, mục tiêu là dùng springdoc-openapi để tạo và tùy biến đặc tả OpenAPI cùng Swagger UI từ controller Spring Boot. Tài liệu cần mô tả request, response, schema, bảo mật, nhóm document, xuất JSON/YAML, kiểm thử hợp đồng, quản lý phiên bản và phân phối API document.

Có thể xem luồng tổng quát như sau:

~~~text
Spring Boot application
  |
  +-- Controllers / request mappings
  +-- DTOs / Jackson / Bean Validation
  +-- Swagger annotations / OpenAPI configuration
  |
  v
Springdoc OpenAPI
  |
  +--> OpenAPI JSON
  +--> OpenAPI YAML
  |
  +--> Swagger UI đọc OpenAPI document
  |
  +--> CI, validator, code generator, API catalog
~~~

OpenAPI document là hợp đồng máy có thể đọc. Swagger UI là giao diện giúp con người khám phá và thử API dựa trên hợp đồng đó.

## 2. Phân biệt OpenAPI, JSON/YAML và Swagger UI

Các khái niệm thường xuất hiện cùng nhau nhưng có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| OpenAPI Specification | Chuẩn mô tả HTTP API theo cấu trúc thống nhất |
| OpenAPI document | Một tài liệu cụ thể tuân theo chuẩn OpenAPI |
| JSON | Một cách serialize OpenAPI document |
| YAML | Một cách serialize OpenAPI document khác |
| Springdoc OpenAPI | Sinh và tùy biến document từ ứng dụng Spring |
| Swagger UI | Giao diện trình duyệt đọc document và hỗ trợ thử request |

JSON và YAML không phải hai loại hợp đồng khác nhau. Chúng biểu diễn cùng một mô hình OpenAPI; khác biệt chính là cú pháp và cách trình bày.

JSON thuận tiện cho script, API tooling và xử lý tự động. YAML thường dễ đọc khi review trong pull request hoặc khi con người cần xem schema nhiều tầng.

Swagger UI không phải bộ sinh contract. Nó đọc document được Springdoc tạo ra rồi hiển thị operation, parameter, request body, response, schema và security metadata.

Nếu JSON/YAML sai, Swagger UI thường sẽ hiển thị sai theo. Đổi giao diện không sửa được lỗi trong contract.

## 3. Springdoc tạo tài liệu từ đâu?

Springdoc kết hợp nhiều nguồn thông tin trong ứng dụng:

- Spring MVC hoặc WebFlux request mappings.
- Tên HTTP method và path từ các mapping annotation.
- Path variable, query parameter, header và cookie parameter.
- Request body và response type.
- DTO, Java record, enum và generic type.
- Jackson annotations và cấu hình serialization.
- Bean Validation constraints như @NotNull, @NotBlank, @Size, @Min và @Pattern.
- Swagger annotations như @Operation, @ApiResponse, @Parameter, @Schema và @Tag.
- OpenAPI bean, customizer và document group configuration.

Ví dụ, controller sau cung cấp thông tin ban đầu để Springdoc mô tả một operation:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderResponse getOrder(@PathVariable String id) {
        return orderService.getOrder(id);
    }
}
~~~

Springdoc có thể nhận biết operation GET /api/orders/{id}, parameter id và kiểu response OrderResponse.

Tuy nhiên, framework không thể tự hiểu mọi quy tắc nghiệp vụ. Những điều như ý nghĩa của trạng thái đơn hàng, điều kiện lỗi, giới hạn nghiệp vụ hoặc cách dùng token cần được mô tả thêm bằng annotation, schema description hoặc OpenAPI configuration.

## 4. Cài đặt Springdoc cho Spring MVC hoặc WebFlux

Với các dòng Springdoc dành cho Spring Boot 3, dependency starter cho Spring MVC thường là:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>PINNED_VERSION</version>
</dependency>
~~~

Với ứng dụng Spring WebFlux, dùng starter tương ứng:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>PINNED_VERSION</version>
</dependency>
~~~

Thay PINNED_VERSION bằng phiên bản được pin theo compatibility matrix chính thức của Springdoc, Spring Boot và Java đang dùng.

Không trộn starter WebMVC với ứng dụng WebFlux hoặc ngược lại. Cũng không trộn dependency generation cũ của Springdoc 1.x với starter 2.x. Các dự án Spring Boot 2 hoặc Spring Boot 4 có thể cần dòng artifact/version khác; kiểm tra tài liệu tương ứng trước khi thêm dependency.

Starter có hậu tố ui thường tích hợp cả OpenAPI endpoint và Swagger UI. Nếu chỉ cần API document cho CI hoặc code generator, có thể chọn module API phù hợp với dòng phiên bản để không đóng gói giao diện không cần thiết.

## 5. Endpoint JSON và YAML mặc định

Với cấu hình mặc định, Springdoc thường cung cấp:

~~~http
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

Endpoint JSON trả OpenAPI document dạng JSON. Endpoint YAML trả cùng document ở dạng YAML.

Ví dụ gọi từ terminal:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output openapi.json

curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output openapi.yaml
~~~

Dùng --fail để lệnh thất bại khi server trả HTTP status lỗi. Trong pipeline, cần kiểm tra thêm file không rỗng và nội dung thật sự là OpenAPI; một trang đăng nhập HTML có thể trả status 200 nhưng không phải document hợp lệ.

Endpoint có thể được thay đổi bằng cấu hình Springdoc. Nếu dự án đổi path, các công cụ CI, Swagger UI, Scalar hoặc code generator phải dùng đúng URL mới.

## 6. Swagger UI là giao diện tương tác

Khi dùng starter UI, Swagger UI thường được truy cập qua:

~~~text
/swagger-ui.html
/swagger-ui/index.html
~~~

Đường dẫn đầu tiên thường redirect tới trang index. URL thực tế có thể thay đổi theo cấu hình swagger-ui.path, context path hoặc reverse proxy.

Swagger UI đọc OpenAPI document rồi trình bày:

- Danh sách tag và operation.
- HTTP method và endpoint path.
- Summary và description.
- Path, query, header và cookie parameter.
- Request body và content type.
- Response status, header và response schema.
- Security scheme và yêu cầu xác thực.
- Schema trong components.

Người dùng có thể mở một operation để xem chi tiết và dùng Try it out để gửi request thử nghiệm.

Try it out thực sự gọi API server được mô tả trong document. Nó không phải mô phỏng offline. Vì vậy, cần chọn môi trường an toàn và tránh gửi thao tác có side effect tới production nếu chưa có quy trình kiểm soát.

## 7. Một OpenAPI document gồm những phần nào?

Ví dụ document rút gọn:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: "1.2.0"
  description: API quản lý đơn hàng

servers:
  - url: https://api.example.com

tags:
  - name: Orders
    description: Các thao tác với đơn hàng

paths:
  /api/orders/{id}:
    get:
      tags:
        - Orders
      summary: Lấy thông tin đơn hàng
      operationId: getOrderById
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Tìm thấy đơn hàng
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderResponse"

components:
  schemas:
    OrderResponse:
      type: object
      properties:
        id:
          type: string
        status:
          type: string
~~~

Các thành phần quan trọng:

| Thành phần | Nội dung |
|---|---|
| openapi | Phiên bản OpenAPI Specification mà document sử dụng |
| info | Tên, phiên bản và mô tả API |
| servers | Base URL để client gọi API |
| tags | Nhóm operation |
| paths | Endpoint, method, parameter, request và response |
| components | Schema, response, parameter, security scheme dùng lại |
| security | Yêu cầu bảo mật ở cấp document hoặc operation |
| externalDocs | Liên kết tới tài liệu bổ sung |

Không nhầm trường openapi với info.version. Trường openapi mô tả phiên bản chuẩn OpenAPI; info.version là phiên bản hợp đồng API do nhóm phát hành.

## 8. Mô tả thông tin API bằng OpenAPI bean

Có thể cung cấp thông tin chung bằng bean OpenAPI:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    OpenAPI orderOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Order API")
                .version("1.2.0")
                .description(
                    "API quản lý vòng đời đơn hàng."
                )
            )
            .servers(List.of(
                new Server()
                    .url("https://api.example.com")
                    .description("Production")
            ));
    }
}
~~~

Bean này giúp kiểm soát metadata mà Springdoc không thể suy ra từ controller, chẳng hạn title, contract version, mô tả tổng quan và server URL.

Không hard-code URL production nếu cùng artifact cần chạy ở nhiều môi trường. Có thể lấy URL từ cấu hình profile hoặc environment property, nhưng cần bảo đảm OpenAPI document được xuất ở CI dùng base URL canonical theo policy.

Nếu dùng nhiều document group, hãy xác định metadata nào dùng chung và metadata nào riêng theo group. Không để document public vô tình mang server URL hoặc description của internal API.

## 9. Mô tả operation bằng annotation

Annotation @Operation bổ sung ngữ nghĩa cho từng method:

~~~java
@GetMapping("/{id}")
@Operation(
    operationId = "getOrderById",
    summary = "Lấy thông tin đơn hàng",
    description = "Trả về chi tiết đơn hàng theo mã định danh."
)
public OrderResponse getOrder(@PathVariable String id) {
    return orderService.getOrder(id);
}
~~~

Các trường có vai trò khác nhau:

- operationId là định danh ổn định của operation, thường được dùng bởi client generator.
- summary là mô tả ngắn trong danh sách operation.
- description giải thích chi tiết cách sử dụng.
- tags phân loại operation trong giao diện.
- deprecated đánh dấu operation đã ngừng khuyến nghị sử dụng.

Không để operationId thay đổi ngẫu nhiên theo tên method hoặc refactor nếu client SDK dựa vào giá trị này. Đối với API public, operationId nên tuân theo convention và được kiểm tra trong CI.

## 10. Mô tả request và response

OpenAPI cần cho client biết dữ liệu nào phải gửi và dữ liệu nào có thể nhận.

Ví dụ DTO:

~~~java
public record CreateOrderRequest(
    @NotBlank
    String customerId,

    @NotEmpty
    List<@Valid OrderLineRequest> lines
) {
}

public record OrderLineRequest(
    @NotBlank
    String productId,

    @Min(1)
    int quantity
) {
}

public record OrderResponse(
    String id,
    String status,
    Instant createdAt
) {
}
~~~

Springdoc có thể dùng kiểu Java và Bean Validation để suy ra schema. Có thể bổ sung @Schema để giải thích field:

~~~java
public record CreateOrderRequest(
    @Schema(
        description = "Mã khách hàng tạo đơn",
        example = "CUS-1001"
    )
    @NotBlank
    String customerId
) {
}
~~~

Ví dụ giúp người đọc hiểu định dạng và ý nghĩa dữ liệu. Không dùng dữ liệu production hoặc thông tin cá nhân thật trong example.

Nếu request và response có cấu trúc khác nhau, nên dùng DTO riêng. Không tái sử dụng một class chỉ vì vài field giống nhau, nếu client cần hiểu rõ field nào được gửi và field nào được trả về.

## 11. JSON và YAML nên dùng trong trường hợp nào?

| Nhu cầu | JSON | YAML |
|---|---|---|
| CI và script | Rất phù hợp | Phù hợp nếu tool hỗ trợ |
| Review thủ công | Có thể đọc nhưng nhiều dấu ngoặc | Thường dễ đọc hơn |
| Code generation | Phổ biến | Phổ biến |
| Lưu artifact release | Phù hợp | Phù hợp |
| Debug bằng jq | Có | Cần parse/chuyển đổi trước |
| Comment trong file | Không hỗ trợ comment JSON chuẩn | Có thể dùng comment |

Hai định dạng nên thể hiện cùng một contract. Nếu JSON và YAML khác nhau về nội dung, cần kiểm tra quá trình export, customizer hoặc cách lưu file.

Có thể chọn một định dạng canonical cho CI và phát hành thêm định dạng còn lại để phục vụ người đọc. Không nên chỉnh sửa JSON và YAML độc lập bằng tay, vì chúng sẽ lệch nhau theo thời gian.

## 12. Cấu hình đường dẫn API docs và Swagger UI

Ví dụ cấu hình:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
~~~

api-docs.enabled bật/tắt OpenAPI endpoint. api-docs.path đổi đường dẫn document. swagger-ui.enabled điều khiển giao diện Swagger UI. swagger-ui.path điều chỉnh URL giao diện theo cấu hình được hỗ trợ bởi phiên bản.

Có thể tắt Swagger UI nhưng giữ OpenAPI endpoint để công cụ khác đọc document:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Đây là cách hữu ích khi production không cần giao diện tương tác nhưng CI, developer portal hoặc API catalog vẫn cần contract. Tuy nhiên, endpoint API docs vẫn phải được bảo vệ nếu document chứa thông tin nội bộ.

## 13. Nhóm API thành nhiều document

Một ứng dụng lớn có thể cung cấp API cho nhiều audience:

- Public API dành cho khách hàng.
- Partner API dành cho đối tác.
- Internal API dành cho các service nội bộ.

Springdoc hỗ trợ nhóm operation bằng GroupedOpenApi:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .build();
}
~~~

Document group có endpoint riêng, thường có dạng:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

Mỗi group có thể được xuất và kiểm tra riêng. Hãy xác minh endpoint thực tế theo phiên bản Springdoc và cấu hình path của ứng dụng.

Group filter giúp chia nội dung document, nhưng không thay thế authorization. Một endpoint internal vẫn phải được bảo vệ ở runtime kể cả khi nó không xuất hiện trong public document.

## 14. Mô tả bảo mật trong OpenAPI

OpenAPI có thể mô tả cách client gửi credential. Ví dụ bearer token:

~~~java
@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class ApiSecurityConfiguration {
}
~~~

Gắn security requirement cho operation:

~~~java
@GetMapping("/{id}")
@Operation(
    summary = "Lấy đơn hàng",
    security = @SecurityRequirement(name = "bearerAuth")
)
public OrderResponse getOrder(@PathVariable String id) {
    return orderService.getOrder(id);
}
~~~

Security scheme mô tả hợp đồng; nó không tự cấu hình Spring Security. Ứng dụng vẫn phải xác thực token, kiểm tra role/scope và từ chối request không hợp lệ.

Swagger UI có thể hiển thị nút Authorize để người dùng nhập credential. Không nhúng token thật trong OpenAPI example, description hoặc cấu hình giao diện.

## 15. Dùng Swagger UI để thử request

Try it out cho phép người dùng:

1. Chọn operation.
2. Nhập path/query/header parameter.
3. Nhập request body.
4. Chọn server URL.
5. Nhập credential nếu operation yêu cầu.
6. Gửi request.
7. Xem HTTP status, response headers và body.

Đây là công cụ hữu ích khi kiểm tra nhanh API contract và giúp người tích hợp hiểu request thực tế.

Tuy nhiên, thao tác thử gửi request thật tới backend. Một POST có thể tạo dữ liệu, PUT có thể cập nhật tài nguyên và DELETE có thể xóa dữ liệu. Dùng staging hoặc test environment với dữ liệu có thể khôi phục.

Nếu browser báo CORS, kiểm tra origin của Swagger UI và policy trên API server. Nếu request gửi sai host, kiểm tra trường servers trong OpenAPI document và cấu hình reverse proxy.

## 16. Bảo vệ Swagger UI và API docs

Swagger UI và OpenAPI endpoint có thể tiết lộ:

- Internal endpoint.
- Request/response schema.
- Security scheme.
- Tên hệ thống phụ thuộc.
- Server URL.
- Operation quản trị.

Không phải mọi API đều nên công khai tài liệu cho tất cả người dùng.

Có thể bảo vệ các URL docs bằng Spring Security:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
            "/swagger-ui/**",
            "/swagger-ui.html",
            "/v3/api-docs",
            "/v3/api-docs/**"
        ).hasRole("API_DOCS")
        .anyRequest().authenticated()
    );

    return http.build();
}
~~~

Ví dụ này minh họa Servlet Security. Ứng dụng thực tế cần tích hợp với filter chain hiện có, login mechanism, CSRF và CORS.

Tắt Swagger UI không đồng nghĩa API docs đã bị ẩn. Nếu /v3/api-docs vẫn mở, client vẫn có thể tải document trực tiếp.

## 17. Document có thể dùng ngoài ứng dụng

OpenAPI document không chỉ phục vụ Swagger UI. Nó còn là đầu vào cho nhiều công cụ:

- OpenAPI Generator để tạo client SDK hoặc server stub.
- Validator để kiểm tra cấu trúc document.
- Linter để áp dụng quy ước đặt tên và governance.
- Contract test để so sánh API implementation với đặc tả.
- API gateway hoặc developer portal.
- Công cụ so sánh breaking change.
- Hệ thống catalog để quản lý API theo service và version.

Do đó, OpenAPI document cần ổn định và có thể truy vết. Không nên xem nó là file tạm chỉ để giao diện Swagger UI render.

Khi phát hành, hãy lưu document cùng API contract version, application artifact version, source revision và checksum theo chính sách release của tổ chức.

## 18. Kiểm tra OpenAPI document trong CI

Một pipeline cơ bản có thể:

1. Build ứng dụng từ commit hiện tại.
2. Chạy unit/integration tests.
3. Khởi động đúng artifact với profile contract.
4. Chờ ứng dụng sẵn sàng.
5. Tải /v3/api-docs hoặc /v3/api-docs.yaml.
6. Kiểm tra file không rỗng và parse được.
7. Validate theo OpenAPI Specification version.
8. Lint theo quy ước tổ chức.
9. So sánh với baseline để phát hiện breaking change.
10. Lưu artifact sau khi tất cả gate thành công.

Ví dụ:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output target/openapi.yaml

test -s target/openapi.yaml

openapi-generator-cli validate \
  -i target/openapi.yaml

oasdiff breaking \
  previous/openapi.yaml \
  target/openapi.yaml
~~~

Các công cụ cần được pin version trong CI. Baseline phải thuộc cùng service, audience và document group.

Nếu fetch hoặc validate thất bại, pipeline phải dừng và không publish candidate. Không dùng document cũ làm fallback cho build mới.

## 19. Những lỗi phổ biến khi dùng JSON/YAML và Swagger UI

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| /v3/api-docs trả 404 | API docs bị tắt hoặc path cấu hình khác |
| Swagger UI mở được nhưng không có operation | URL document sai hoặc OpenAPI document rỗng |
| Swagger UI báo lỗi parse | JSON/YAML không hợp lệ hoặc version không được hỗ trợ |
| JSON có nhưng YAML không tải được | Sai YAML endpoint hoặc export configuration |
| Swagger UI hiển thị localhost | Server URL hoặc forwarded header sai |
| Try it out bị CORS | API server chưa cho phép origin của UI |
| Endpoint docs trả 401/403 | Spring Security chưa cho phép user hiện tại |
| Schema thiếu field | Jackson visibility, DTO accessor hoặc annotation |
| Operation thiếu response | Chưa mô tả response/error đầy đủ |
| Document group thiếu endpoint | pathsToMatch hoặc packagesToScan không khớp |
| CI nhận HTML thay vì JSON | Redirect login hoặc proxy error page |
| Client generator tạo model sai | Schema, enum, type hoặc component name không chính xác |

Khi debug, kiểm tra trực tiếp OpenAPI JSON/YAML trước. Sau đó mới kiểm tra Swagger UI. Cách này giúp phân biệt lỗi nằm ở bước sinh document hay ở renderer.

## 20. Quy trình làm việc hằng ngày với Springdoc

Một workflow thực tế:

**Khi thêm endpoint**

- Tạo controller mapping và DTO.
- Thêm validation cho input.
- Bổ sung summary, description, operationId và response.
- Mô tả security requirement nếu cần.
- Tải JSON/YAML để kiểm tra operation và schema.

**Khi thay đổi DTO**

- Kiểm tra Jackson serialization.
- Kiểm tra required, nullable, enum và format.
- Xem components.schemas và các $ref.
- So sánh contract với release trước.

**Khi phát hành**

- Xuất document từ đúng application artifact.
- Validate và lint.
- Kiểm tra breaking change.
- Gắn API contract version và source revision.
- Lưu JSON/YAML cùng release.

**Khi hỗ trợ client**

- Dùng Swagger UI để khám phá và thử request.
- Cung cấp document JSON/YAML cho code generator.
- Công bố migration guide khi contract thay đổi.
- Bảo vệ tài liệu theo audience.

## 21. Checklist chất lượng tài liệu

Trước khi coi một OpenAPI document là sẵn sàng cho client:

- Title và API contract version có ý nghĩa.
- Server URL đúng môi trường.
- Mỗi operation có summary và operationId ổn định.
- Parameter được mô tả đúng vị trí và kiểu dữ liệu.
- Request body có schema và required flag phù hợp.
- Response có status code và media type cần thiết.
- Error response được mô tả nhất quán.
- Schema có type, format, enum và validation constraints đúng.
- Security scheme khớp với cơ chế xác thực runtime.
- Components và $ref resolve được.
- Document group chỉ chứa operation dành cho audience tương ứng.
- JSON/YAML validate thành công.
- Không chứa secret hoặc dữ liệu production trong example.
- Contract diff đã được review.

Swagger UI giúp nhìn tài liệu dễ hơn, nhưng chất lượng contract vẫn phụ thuộc vào schema và metadata do ứng dụng cung cấp.

## 22. Nguyên tắc sử dụng tài liệu JSON/YAML và giao diện tương tác

Khi triển khai Springdoc OpenAPI:

1. Xem OpenAPI document là hợp đồng chính thức của API.
2. Dùng JSON cho xử lý tự động và YAML cho review khi phù hợp.
3. Giữ Springdoc làm nguồn sinh document từ controller và model.
4. Dùng Swagger UI để khám phá và thử request trong môi trường an toàn.
5. Phân biệt OpenAPI Specification version với API contract version.
6. Mô tả rõ operation, parameter, request, response và security.
7. Tách document group theo audience nhưng vẫn bảo vệ endpoint runtime.
8. Kiểm tra JSON/YAML trực tiếp trước khi debug UI.
9. Validate, lint và so sánh contract trong CI.
10. Phát hành document cùng source revision và application artifact tương ứng.

JSON/YAML cung cấp hợp đồng có thể được máy đọc và công cụ xử lý; Swagger UI cung cấp giao diện để con người khám phá và thử API. Khi Springdoc sinh document từ đúng controller, DTO, validation và security metadata, rồi nhóm phát triển kiểm tra document trước khi phát hành, tài liệu sẽ theo sát hành vi API và hỗ trợ client tích hợp đáng tin cậy.

## 23. Tài liệu tham khảo

- Springdoc OpenAPI: https://springdoc.org/
- Springdoc Configuration Properties: https://springdoc.org/properties.html
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
- Swagger UI: https://swagger.io/tools/swagger-ui/
- OpenAPI Generator: https://openapi-generator.tech/

