# Vị trí của tài liệu API trong phát triển, kiểm thử và tích hợp

Tài liệu API không chỉ là trang Swagger UI được mở sau khi controller đã viết xong. Trong một sản phẩm có nhiều service và nhiều nhóm phát triển, tài liệu API là phương tiện để thống nhất cách một capability được công bố, cách consumer sử dụng nó, cách kiểm chứng hành vi và cách quản lý thay đổi qua các lần phát hành.

Với Spring Boot và springdoc-openapi, OpenAPI document có thể được sinh từ controller, DTO, annotation và cấu hình của ứng dụng. Tài liệu đó trở thành artifact có thể review, validate, so sánh, phân phối và dùng trong kiểm thử. Swagger UI là một cách trình bày artifact; nó không phải bản thân hợp đồng và cũng không phải API runtime.

Bài học đặt tài liệu API vào toàn bộ vòng đời phần mềm:

1. **Thiết kế**: thống nhất operation, request, response, lỗi, bảo mật và quy tắc tương thích.
2. **Triển khai**: biến thiết kế thành controller, DTO, validation và OpenAPI document.
3. **Kiểm thử**: đối chiếu document với request/response thật, phát hiện drift và breaking change.
4. **Tích hợp**: giúp consumer khám phá API, tạo client, cấu hình authentication và xử lý lỗi.
5. **Phát hành, vận hành và quản trị**: version hóa, phân phối, bảo vệ, theo dõi và ngừng hỗ trợ contract cũ.

## 1. Tài liệu API nằm ở đâu trong kiến trúc?

Một API có ít nhất ba thành phần cần phân biệt:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| API runtime | Thực thi request và trả response qua HTTP | Spring MVC controller tại `/api/products`. |
| API contract | Mô tả operation và quy tắc trao đổi mà consumer có thể dựa vào | OpenAPI JSON/YAML tại `/v3/api-docs`. |
| API documentation UI | Trình bày contract để con người khám phá và thử request | Swagger UI tại `/swagger-ui.html`. |

Các thành phần liên quan khác gồm source code, test suite, generated client, API catalog, gateway configuration và release artifact. Chúng có thể được tạo từ cùng một contract nhưng không nên bị xem là một thứ.

~~~mermaid
flowchart LR
    A[API design and decisions] --> B[OpenAPI contract]
    B --> C[Spring Boot implementation]
    C --> D[Runtime HTTP behavior]
    C --> E[springdoc-generated OpenAPI]
    E --> F[Swagger UI / API portal]
    E --> G[Contract validation and diff]
    B --> H[Client SDK generation]
    G --> I[CI release gate]
    H --> J[Consumer integration]
    F --> J
    D --> J
~~~

Trong mô hình code-first, source code và annotation thường là đầu vào để springdoc sinh contract. Trong mô hình design-first, OpenAPI được review trước rồi implementation phải đáp ứng contract đã duyệt. Dù chọn cách nào, nhóm cần chỉ rõ artifact nào là nguồn hợp đồng có thẩm quyền tại thời điểm review và phát hành.

## 2. Vì sao cần tài liệu API trong cả vòng đời?

Không có contract được duy trì, mỗi nhóm dễ tự suy đoán:

- Frontend đoán field nào bắt buộc và giá trị enum nào hợp lệ.
- Mobile team tự giả định format ngày giờ hoặc cách phân trang.
- Service consumer đoán error response và retry behavior.
- QA viết test theo implementation tình cờ thay vì hành vi đã thống nhất.
- Vận hành không biết endpoint nào cần credential, scope hoặc server URL nào.
- Nhóm phát triển thay DTO mà không nhận ra client cũ sẽ bị ảnh hưởng.

Tài liệu API làm rõ kỳ vọng trước khi consumer tích hợp. Nó không thay thế giao tiếp giữa các nhóm, nhưng tạo một artifact chung để các quyết định có thể được kiểm tra và tái sử dụng.

### 2.1. Lợi ích theo vai trò

| Vai trò | Cách sử dụng tài liệu API |
|---|---|
| Product owner / analyst | Review capability, dữ liệu đầu vào/đầu ra và hành vi lỗi ở mức nghiệp vụ. |
| API designer / architect | Chuẩn hóa path, method, schema, security, version và convention. |
| Backend developer | Triển khai controller, DTO, validation và đối chiếu OpenAPI được sinh. |
| Frontend / mobile developer | Hiểu request, response, enum, pagination, lỗi và authentication để tích hợp. |
| QA / test engineer | Tạo test case, fixture và contract test từ operation/schema. |
| DevOps / platform engineer | Validate artifact, publish spec, cấu hình gateway và kiểm soát release. |
| Security engineer | Review authentication scheme, scope, dữ liệu nhạy cảm và quyền truy cập tài liệu. |
| Consumer team | Khám phá API, generate client và kiểm tra tương thích trước khi nâng version. |

Một contract tốt giảm các câu hỏi lặp lại như “field này có thể null không?”, “404 trả schema gì?” hoặc “token cần scope nào?”. Khi câu trả lời thay đổi, thay đổi đó có thể được review trong cùng luồng phát triển.

## 3. Tài liệu API trong giai đoạn khám phá và thiết kế

Tài liệu nên bắt đầu từ nhu cầu của consumer, không phải từ danh sách method Java. Trước khi triển khai, nhóm cần xác định:

1. Consumer là ai: browser, mobile app, partner, service nội bộ hay administrator?
2. Capability nào được cung cấp và ranh giới trách nhiệm của service ở đâu?
3. Resource và operation nào cần có?
4. Request parameters, headers và body được truyền thế nào?
5. Response thành công và response lỗi có cấu trúc gì?
6. Authentication, authorization và scope nào được yêu cầu?
7. Pagination, filtering, sorting, idempotency và concurrency được xử lý ra sao?
8. Thay đổi nào được coi là breaking change?

Ví dụ, thay vì chỉ ghi “API tạo sản phẩm”, contract cần thể hiện method, path, body, status và schema:

~~~yaml
paths:
  /api/products:
    post:
      operationId: createProduct
      summary: Tạo sản phẩm
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateProductRequest"
      responses:
        "201":
          description: Sản phẩm đã được tạo
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ProductResponse"
        "400":
          description: Request không hợp lệ
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
~~~

Contract ở giai đoạn thiết kế giúp consumer review sớm, trước khi backend hoàn tất. Nhờ đó, các vấn đề như thiếu field, tên enum khó hiểu, response lỗi không thống nhất hoặc scope quá rộng có thể được sửa trước khi tạo phụ thuộc trong nhiều client.

### 3.1. Design-first và code-first

| Cách tiếp cận | Quy trình | Điểm mạnh | Rủi ro cần quản lý |
|---|---|---|---|
| Design-first | Review OpenAPI trước, sau đó triển khai và kiểm tra implementation theo contract | Consumer có thể tích hợp sớm; contract được review độc lập với code | Contract và code có thể drift nếu thiếu kiểm thử tự động. |
| Code-first | Viết controller/DTO/annotation rồi sinh OpenAPI bằng springdoc | Tài liệu gần với implementation; phù hợp dự án Spring Boot hiện có | Annotation có thể phản ánh chưa đủ ý định nghiệp vụ hoặc contract bị thay đổi ngoài ý muốn khi sửa code. |
| Hybrid | Phác thảo và review contract, triển khai code, sau đó so sánh document được sinh với baseline | Kết hợp khả năng review sớm và kiểm chứng runtime | Cần quy định rõ nguồn sự thật và quy trình xử lý diff. |

Không có cách nào tự bảo đảm contract chính xác. Design-first cần kiểm tra implementation; code-first cần review tài liệu được sinh như một artifact phát hành.

## 4. Tài liệu API trong giai đoạn triển khai

Khi triển khai Spring Boot, controller, DTO, validation và cấu hình serialization tạo nên hành vi HTTP thực tế. Springdoc đọc thông tin từ ứng dụng để tạo OpenAPI document.

Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
            operationId = "createProduct",
            summary = "Tạo sản phẩm",
            description = "Tạo một sản phẩm mới trong catalog."
    )
    @ApiResponse(
            responseCode = "201",
            description = "Sản phẩm đã được tạo",
            content = @Content(
                    schema = @Schema(implementation = ProductResponse.class)
            )
    )
    ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
        return new ProductResponse("p-100", request.name(), request.price());
    }
}

record CreateProductRequest(
        @NotBlank String name,
        @Positive long price
) {}

record ProductResponse(String id, String name, long price) {}
~~~

Đoạn code minh họa cách controller và annotation đóng góp vào OpenAPI document. Trong ứng dụng thực tế, cần xử lý nghiệp vụ, persistence, exception, authorization và mapping DTO phù hợp. Annotation mô tả contract nhưng không thay thế logic kiểm tra request hoặc test response.

### 4.1. Những nội dung cần phản ánh trong contract

| Nội dung | Cách mô tả hoặc nguồn thông tin |
|---|---|
| Path và HTTP method | Mapping của Spring MVC/WebFlux và operation metadata. |
| Path/query/header parameter | `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@Parameter`. |
| Request body | DTO, `@RequestBody`, `@Schema`, OpenAPI request-body annotation. |
| Field constraint | Bean Validation như `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@Max`. |
| Response schema | DTO response và `@ApiResponse`, `@Schema`. |
| Error response | Exception handler, `ProblemDetail` hoặc error DTO cùng response annotation. |
| Security | Spring Security runtime và OpenAPI security scheme/requirement. |
| Examples | `@ExampleObject`, example trong schema hoặc OpenAPI customizer. |
| Server và version | `OpenAPI` bean, configuration hoặc release process. |

### 4.2. Contract không chỉ là tên method

Một operation có thể có method và path đúng nhưng vẫn khó tích hợp nếu thiếu:

- `operationId` ổn định để SDK generator tạo tên method dễ dùng.
- Summary và description giải thích mục đích, điều kiện và side effect.
- Required/nullable, format, enum và giới hạn dữ liệu.
- Content-Type, Accept và response media type.
- Status code và schema lỗi.
- Security requirement và scope.
- Pagination, filtering và semantics của empty result.

Không đưa bí mật, token mẫu thật, dữ liệu cá nhân hoặc thông tin production vào description/example. Ví dụ nên dùng dữ liệu giả lập, có tính đại diện và không gây hiểu nhầm.

## 5. Springdoc tạo artifact từ ứng dụng như thế nào?

Với starter phù hợp cho Spring MVC hoặc WebFlux, Springdoc thường cung cấp:

| Endpoint mặc định | Kết quả |
|---|---|
| `/v3/api-docs` | OpenAPI JSON. |
| `/v3/api-docs.yaml` | OpenAPI YAML. |
| `/v3/api-docs/{group}` | OpenAPI document của group được đặt tên. |
| `/swagger-ui.html` | Trang Swagger UI. |
| `/v3/api-docs/swagger-config` | Cấu hình mà Swagger UI tải để tìm document và UI options. |

Có thể tải JSON/YAML bằng:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs \
  -o build/openapi.json

curl -fsS http://localhost:8080/v3/api-docs.yaml \
  -o build/openapi.yaml
~~~

Nếu ứng dụng dùng context path, reverse proxy hoặc custom `springdoc.api-docs.path`, URL cần được điều chỉnh theo deployment thực tế.

### 5.1. OpenAPI document và Swagger UI không giống nhau

- OpenAPI JSON/YAML là artifact contract có thể lưu, validate, diff và dùng cho tooling.
- Swagger UI là giao diện đọc OpenAPI document.
- Swagger UI config là JSON chỉ dẫn UI tải document nào và áp dụng tùy chọn nào.
- API runtime là server thực thi HTTP request.

Ẩn Swagger UI không làm API ngừng hoạt động. Tắt OpenAPI endpoint không tự bảo vệ controller. Chỉ hiển thị một URL trong dropdown cũng không xóa những document khác. Quyền truy cập phải được enforce bằng Spring Security, gateway hoặc network policy.

## 6. Tài liệu API trong kiểm thử

Tài liệu chỉ có ích nếu nó phản ánh hành vi thật. Kiểm thử nên xác minh hai hướng:

1. **Contract → implementation**: request/response runtime có tuân theo OpenAPI đã duyệt không?
2. **Implementation → contract**: thay đổi code có làm tài liệu sinh ra thay đổi ngoài ý muốn không?

Các cấp độ kiểm thử:

| Loại test | Mục tiêu | Ví dụ |
|---|---|---|
| Unit test | Logic nghiệp vụ trong service/controller | Giá, trạng thái đơn hàng, quyền nghiệp vụ. |
| MVC/WebFlux integration test | Request đi qua framework và được serialize thành HTTP response | MockMvc hoặc WebTestClient. |
| OpenAPI conformance test | Request/response khớp operation và schema trong document | OpenAPI Request Validator. |
| Consumer-driven contract test | Provider đáp ứng expectation của consumer cụ thể | Pact hoặc Spring Cloud Contract. |
| End-to-end test | Hành vi qua gateway, network, identity provider và service phụ thuộc | Gọi môi trường tích hợp đã triển khai. |

Các loại test bổ sung cho nhau. Unit test không kiểm chứng Content-Type; OpenAPI conformance test không chứng minh authorization nghiệp vụ đúng; end-to-end test không nên là cách duy nhất để kiểm tra hàng trăm schema vì thường chậm và khó chẩn đoán.

### 6.1. Kiểm tra document được sinh

Có thể dùng MockMvc để xác minh operation và schema quan trọng vẫn xuất hiện:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesCreateProductOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi").exists())
                .andExpect(jsonPath("$.paths['/api/products'].post").exists())
                .andExpect(jsonPath(
                        "$.paths['/api/products'].post.operationId"
                ).value("createProduct"));
    }
}
~~~

Test này chứng minh document có operation mong muốn; nó chưa chứng minh request thật được xử lý đúng. Cần test controller/runtime riêng.

### 6.2. Kiểm tra response runtime với contract

Ví dụ dùng MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsProductWithJsonResponse() throws Exception {
        mockMvc.perform(post("/api/products")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "Mechanical Keyboard",
                                  "price": 790000
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ));
    }
}
~~~

Test trên xác minh status và media type. Để chứng minh response body khớp OpenAPI schema, có thể thêm JSON assertions hoặc dùng OpenAPI validator adapter. Một test không nên chỉ kiểm tra `status().isOk()` rồi kết luận contract đã được xác minh.

### 6.3. Kiểm thử lỗi cũng là kiểm thử contract

Consumer cần biết cách xử lý các trường hợp:

- `400 Bad Request`: body hoặc parameter không hợp lệ.
- `401 Unauthorized`: chưa xác thực.
- `403 Forbidden`: không đủ quyền.
- `404 Not Found`: tài nguyên không tồn tại.
- `409 Conflict`: xung đột trạng thái hoặc version.
- `415 Unsupported Media Type`: request dùng media type không được hỗ trợ.
- `429 Too Many Requests`: bị giới hạn tốc độ nếu API có rate limit.
- `5xx`: lỗi server; response công khai không được để lộ stack trace hoặc secret.

OpenAPI nên mô tả các response có ý nghĩa, content type và error schema. Test cần xác minh exception handler thực sự trả đúng status/body. Không mô tả một error response trong tài liệu rồi để runtime trả HTML hoặc một JSON shape khác.

## 7. Tài liệu API và consumer integration

Khi consumer tích hợp, tài liệu đóng vai trò là bản hướng dẫn có cấu trúc:

1. Khám phá base URL và operation.
2. Xác định HTTP method, path và parameters.
3. Tạo request body theo schema.
4. Chuẩn bị token, API key hoặc credential.
5. Gửi request với Content-Type/Accept đúng.
6. Parse response thành model phù hợp.
7. Xử lý status code và error schema.
8. Thực hiện pagination, retry hoặc idempotency theo quy tắc đã công bố.

### 7.1. Generated client

OpenAPI document có thể được dùng làm đầu vào cho client generator. SDK giúp giảm việc tự viết model, serialization và HTTP request, nhưng không loại bỏ việc review:

- Tên `operationId` có ổn định và dễ hiểu không?
- Schema có thể được biểu diễn trong ngôn ngữ mục tiêu không?
- Nullable, union, enum và polymorphism có được generator hỗ trợ không?
- Security scheme có map đúng vào cơ chế cấp token của consumer không?
- Error response có đủ thông tin để client xử lý không?

Không đổi `operationId` hoặc tên schema tùy tiện nếu nhiều consumer đã dựa vào SDK được generate. Một thay đổi có vẻ nhỏ trong document có thể làm thay đổi public method hoặc model name của client.

### 7.2. Mock server và tích hợp song song

Consumer có thể dùng mock server được tạo từ OpenAPI contract để phát triển trước khi provider hoàn tất. Cách này cho phép frontend và backend làm song song, nhưng mock phải phản ánh contract đã được review.

Mock không chứng minh provider runtime đã đáp ứng contract. Khi provider sẵn sàng, chạy contract test hoặc integration test với response thật để tránh tình trạng consumer tích hợp với mock behavior không tồn tại trên server.

### 7.3. Tài liệu không thay thế quy trình tích hợp

Một OpenAPI document không thể tự giải thích đầy đủ:

- Cách đăng ký client và nhận credential.
- Quy trình cấp quyền hoặc phê duyệt scope.
- Rate limit, quota và support escalation nếu không được mô tả.
- SLA, lịch bảo trì hoặc chính sách deprecation.
- Cách xử lý webhook delivery/retry và bảo mật callback.
- Điều kiện dữ liệu nghiệp vụ hoặc workflow nhiều bước.

Những nội dung này nên nằm trong developer portal, onboarding guide hoặc tài liệu vận hành liên kết với OpenAPI. Không nhồi mọi quy trình vào operation description.

## 8. Tài liệu API trong CI/CD và release

OpenAPI document nên được xử lý như một artifact của build:

~~~mermaid
flowchart TD
    A[Commit controller DTO annotations] --> B[Build application]
    B --> C[Start test context]
    C --> D[Export OpenAPI JSON/YAML]
    D --> E[Validate syntax and references]
    E --> F[Lint conventions]
    F --> G[Diff against released baseline]
    G --> H[Run contract and integration tests]
    H --> I[Review and approve changes]
    I --> J[Publish versioned API artifact]
    J --> K[Update API catalog / consumer SDK]
~~~

Một pipeline có thể thực hiện:

1. Build đúng artifact ứng dụng.
2. Khởi động ứng dụng với test profile và dữ liệu xác định.
3. Tải `/v3/api-docs` hoặc từng group document.
4. Validate OpenAPI version, syntax và `$ref`.
5. Lint naming, operationId, description, security và convention.
6. So sánh với baseline của release trước để phát hiện breaking change.
7. Chạy contract tests và integration tests.
8. Lưu JSON/YAML, validation report và dependency/version metadata.
9. Chỉ publish artifact sau khi các gate cần thiết đã pass và thay đổi được review.

Không nên lấy file cũ còn sót trong build folder khi endpoint export thất bại. Pipeline cần kiểm tra HTTP status, content type, file không rỗng và thời điểm tạo artifact.

### 8.1. Version hóa contract

Nên phân biệt:

- Version của API, thường thể hiện qua `info.version` hoặc chính sách versioning của endpoint.
- Version của OpenAPI Specification, nằm trong trường `openapi`.
- Version của springdoc-openapi dependency.
- Version của client SDK được sinh từ contract.

Các version này không tự động đồng bộ. Release process cần ghi lại mối quan hệ giữa API artifact, ứng dụng provider và SDK được generate.

### 8.2. Review breaking change

Những thay đổi có thể làm consumer cũ lỗi:

- Xóa path hoặc HTTP method.
- Đổi path parameter hoặc tên query/header parameter.
- Thêm required request field.
- Đổi kiểu field, enum value hoặc format.
- Xóa response field mà client đang dùng.
- Đổi status code hoặc media type.
- Thay security requirement hoặc scope.
- Đổi server URL, path prefix hoặc `operationId` ảnh hưởng SDK.

Không phải mọi thay đổi schema đều có cùng mức độ tương thích. Ví dụ, thêm optional response field thường ít rủi ro hơn thêm required request field, nhưng consumer dùng strict deserialization vẫn có thể bị ảnh hưởng. Cần xem xét cách client thực sự parse dữ liệu.

## 9. Phân phối tài liệu cho nhiều nhóm và môi trường

Springdoc có thể tạo nhiều OpenAPI document bằng `GroupedOpenApi`. Swagger UI có thể liệt kê các document bằng `springdoc.swagger-ui.urls`.

Ví dụ:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
}

@Bean
GroupedOpenApi internalApi() {
    return GroupedOpenApi.builder()
            .group("internal")
            .pathsToMatch("/api/internal/**")
            .build();
}
~~~

Các URL tương ứng thường là `/v3/api-docs/public` và `/v3/api-docs/internal`. Một UI nội bộ có thể liệt kê cả hai; một portal public chỉ nên hiển thị document công khai.

### 9.1. Tách tài liệu theo audience không phải biện pháp bảo mật

Group filter chỉ quyết định operation nào xuất hiện trong document. Nó không tự bảo vệ URL tài liệu hoặc controller.

- Bảo vệ `/v3/api-docs/internal` bằng authorization phù hợp.
- Bảo vệ `/v3/api-docs/swagger-config` và Swagger UI nếu portal là nội bộ.
- Enforce quyền gọi `/api/internal/**` ở Spring Security hoặc gateway.
- Không đưa credential hoặc dữ liệu nhạy cảm vào examples.
- Kiểm tra cả JSON và YAML endpoints nếu phát hành cả hai.

Ẩn một group khỏi dropdown không ngăn người dùng tải trực tiếp URL OpenAPI. Phải bảo vệ ở server/network boundary.

### 9.2. Phân biệt URL tài liệu và server URL

`springdoc.swagger-ui.urls[].url` là URL của OpenAPI document mà UI tải. `servers[].url` trong OpenAPI là base URL của API runtime mà consumer gọi. Hai URL phục vụ hai mục đích khác nhau.

Nếu document được tải từ `/docs/openapi.json` nhưng API runtime nằm ở `https://api.example.com/v1`, contract cần khai báo server URL đúng. Khi chạy sau reverse proxy, kiểm tra forwarded headers và public base path để `servers` không trỏ vào hostname nội bộ.

## 10. Tài liệu API trong vận hành và quản trị

Sau khi phát hành, tài liệu vẫn cần được quản lý:

- Lưu artifact theo release và giữ baseline để diff.
- Gắn owner cho từng API/group.
- Ghi trạng thái lifecycle: experimental, active, deprecated hoặc retired theo chính sách.
- Công bố lịch deprecation và phiên bản thay thế.
- Bảo đảm API catalog trỏ tới artifact đúng môi trường và release.
- Theo dõi consumer còn sử dụng version cũ trước khi ngừng hỗ trợ.
- Giữ lại release notes và quyết định contract để điều tra sự cố.

Tài liệu runtime có thể thay đổi khi deployment đổi config hoặc dependency. Vì vậy, nên lưu thêm artifact đã được phê duyệt cùng release thay vì chỉ dựa vào endpoint `/v3/api-docs` của một môi trường đang chạy.

### 10.1. Tài liệu và observability

OpenAPI giúp biết operation nào được công bố; logs, metrics và traces giúp biết operation nào thực sự được sử dụng và đang hoạt động ra sao. Có thể liên kết:

- `operationId` với route metrics hoặc tracing span.
- API version với dashboard lỗi và latency.
- Deprecation notice với consumer usage.
- Error schema với log correlation ID và support workflow.

Không ghi token, password hoặc body chứa dữ liệu nhạy cảm vào log chỉ để làm tài liệu/trace dễ tra cứu. Tài liệu API và observability cần cùng một chính sách bảo vệ dữ liệu.

## 11. Chọn mức độ tài liệu phù hợp

Không phải endpoint nào cũng cần description dài. Mức độ cần thiết phụ thuộc vào độ phức tạp và đối tượng consumer.

| Loại API | Tài liệu tối thiểu nên có |
|---|---|
| API CRUD nội bộ đơn giản | Summary, parameters, request/response schema, status và security. |
| Public partner API | Mô tả nghiệp vụ, examples, errors, auth, pagination, rate limit và version policy. |
| API tài chính hoặc giao dịch | Precision, idempotency, state transition, concurrency, error semantics và audit requirements. |
| Webhook | Event schema, signature verification, retry, ordering, duplicate delivery và acknowledgement. |
| File upload/download | Media type, size limits, binary response, filename và error handling. |
| Async API | Message/event schema, delivery guarantees, correlation và retry semantics. |

Một contract ngắn nhưng chính xác tốt hơn một trang dài có nhiều nội dung không được runtime thực thi.

## 12. Những hiểu lầm thường gặp

- **“Swagger UI là tài liệu API”**: UI chỉ render một OpenAPI document; artifact JSON/YAML mới là contract có cấu trúc.
- **“Sinh được OpenAPI nghĩa là contract đúng”**: document có thể thiếu response lỗi, security, constraint hoặc mô tả sai hành vi runtime.
- **“Annotation thay thế test”**: annotation không chứng minh serialization và HTTP response thật khớp schema.
- **“Tài liệu chỉ dành cho frontend”**: QA, service consumer, platform, security và vận hành đều dùng contract.
- **“Code-first luôn cập nhật tài liệu đúng”**: code thay đổi có thể làm contract drift hoặc tạo breaking change ngoài ý muốn.
- **“Design-first không cần kiểm tra runtime”**: implementation vẫn có thể không tuân thủ OpenAPI đã duyệt.
- **“Ẩn Swagger UI là bảo mật”**: JSON/YAML endpoint và API runtime vẫn có thể truy cập trực tiếp.
- **“OpenAPI là toàn bộ developer portal”**: onboarding, credential, SLA, quota và support process cần nội dung bổ sung.
- **“Một lần publish là đủ”**: contract cần versioning, deprecation, owner và baseline.
- **“Tất cả thay đổi schema đều breaking”**: phải phân tích ngữ nghĩa và cách consumer xử lý, không chỉ nhìn diff text.
- **“Mock server chứng minh provider đúng”**: mock chỉ mô phỏng contract; cần test provider runtime riêng.
- **“API docs endpoint là artifact phát hành bất biến”**: runtime config và dependency có thể làm output thay đổi; hãy lưu bản đã review theo release.

## 13. Quy trình làm việc đề xuất

1. **Khám phá consumer và capability**: xác định ai sẽ gọi API và vấn đề nghiệp vụ cần giải quyết.
2. **Thiết kế contract**: thống nhất paths, methods, parameters, schema, lỗi, security và versioning.
3. **Review contract**: kiểm tra tính rõ ràng, tính nhất quán và khả năng tương thích với consumer.
4. **Triển khai Spring Boot**: viết controller, DTO, validation, serialization và authorization.
5. **Sinh OpenAPI bằng springdoc**: xuất JSON/YAML và group document nếu cần.
6. **So sánh implementation với contract**: phát hiện operation thiếu, field sai hoặc response không được mô tả.
7. **Kiểm thử**: chạy unit, MVC/WebFlux, OpenAPI conformance, consumer contract và E2E theo ranh giới phù hợp.
8. **Tích hợp consumer**: cung cấp artifact, examples, auth guidance và client SDK nếu cần.
9. **Gate CI và release**: validate, lint, diff baseline, review breaking change và publish artifact.
10. **Quản trị sau phát hành**: theo dõi consumer, deprecation, version lifecycle và cập nhật tài liệu.

## 14. Checklist đánh giá một API có tài liệu sẵn sàng tích hợp

- [ ] Xác định rõ consumer và mục tiêu operation.
- [ ] Có summary, description và operationId ổn định.
- [ ] Path, method và parameters phản ánh đúng HTTP runtime.
- [ ] Request body có media type và schema rõ ràng.
- [ ] Required, nullable, enum, format và validation constraints được mô tả đúng.
- [ ] Response thành công có status, content type và schema.
- [ ] Error responses quan trọng có status và error schema.
- [ ] Security scheme và operation requirements phù hợp với runtime.
- [ ] Examples dùng dữ liệu giả lập, không chứa secret.
- [ ] OpenAPI JSON/YAML được validate và lưu thành artifact.
- [ ] Contract được so sánh với baseline trước khi release.
- [ ] Có test document và test HTTP behavior thật.
- [ ] Consumer có thể hiểu cách xác thực, gọi API và xử lý lỗi.
- [ ] Tài liệu được phân phối đúng audience và bảo vệ phù hợp.
- [ ] Có owner, version, deprecation và release policy.

## 15. Tài liệu tham khảo

- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html)
- [springdoc-openapi – Configuration properties](https://springdoc.org/properties.html)
- [springdoc-openapi – FAQ and multiple OpenAPI definitions](https://springdoc.org/faq.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Swagger UI – Usage and configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Security – Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Pact – Consumer-driven contract testing](https://docs.pact.io/)
- [Spring Cloud Contract – Reference documentation](https://docs.spring.io/spring-cloud-contract/reference/)

Tài liệu API là một artifact xuyên suốt vòng đời phần mềm: nó giúp thống nhất thiết kế, hướng dẫn triển khai, cung cấp cơ sở kiểm thử, hỗ trợ consumer tích hợp và làm đầu vào cho release/governance. Springdoc giúp sinh OpenAPI từ ứng dụng Spring Boot; Swagger UI giúp con người khám phá tài liệu; CI và contract tests giúp kiểm chứng tài liệu với hành vi runtime. Khi contract được review, version hóa, kiểm thử và phân phối có chủ đích, nó trở thành điểm phối hợp đáng tin cậy giữa provider và consumer thay vì chỉ là một trang giao diện sau khi code hoàn tất.
