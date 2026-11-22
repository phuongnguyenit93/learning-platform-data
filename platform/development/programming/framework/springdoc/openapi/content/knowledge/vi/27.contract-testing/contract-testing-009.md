# Kiểm tra hợp đồng sinh ra bằng WebTestClient trong ứng dụng Reactive

Trong ứng dụng Spring WebFlux, springdoc-openapi tạo OpenAPI document từ controller hoặc functional endpoint, DTO, Spring mapping và Swagger annotations. Có thể dùng WebTestClient để gọi endpoint tài liệu ngay trong integration test, đọc JSON/YAML được sinh ra rồi xác nhận operation, parameter, request body, response và schema đúng với hợp đồng mong đợi.

Một bài kiểm thử hợp đồng nên kiểm tra hai mặt có liên quan: OpenAPI document mô tả API như thế nào và endpoint HTTP thực tế phản hồi ra sao. WebTestClient hỗ trợ gửi request HTTP đến cả ứng dụng WebFlux đang chạy và web context giả lập. Tuy nhiên, bản thân nó không tự so sánh payload với mọi ràng buộc OpenAPI; test cần kiểm tra các phần quan trọng hoặc kết hợp thêm OpenAPI/JSON Schema validator.

## 1. Mục tiêu của kiểm thử hợp đồng

OpenAPI document là hợp đồng mà client, code generator, tester và developer portal sử dụng. Nếu controller thay đổi nhưng tài liệu không cập nhật đúng, client có thể được sinh từ schema sai. Ngược lại, tài liệu có thể mô tả response 201 trong khi endpoint thực tế trả 200.

Trong ứng dụng Reactive, kiểm thử bằng WebTestClient có thể xác minh:

- Endpoint tài liệu /v3/api-docs trả về OpenAPI JSON hợp lệ.
- Trường openapi có phiên bản mong đợi.
- Operation xuất hiện đúng path và HTTP method.
- operationId ổn định và đúng tên.
- Path/query/header parameter có đúng tên, vị trí, kiểu và required.
- Request body có đúng media type và schema.
- Response có đúng status code, content type và schema.
- Các schema tham chiếu trong components.schemas tồn tại.
- Group document chỉ chứa operation dự kiến.
- Request thật gửi đến API có hành vi phù hợp với hợp đồng được công bố.

Nên chia kiểm thử thành hai nhóm:

| Nhóm test | Điều cần xác nhận |
|---|---|
| OpenAPI document test | Metadata và schema được springdoc sinh ra đúng |
| Runtime API test | Endpoint HTTP thật trả status, header và body đúng |

Hai nhóm bổ sung cho nhau. Chỉ kiểm tra document chưa chứng minh controller thực thi đúng; chỉ gọi controller chưa chứng minh OpenAPI document mô tả đúng.

## 2. Chuẩn bị dependency cho WebFlux và springdoc

Ứng dụng cần Spring WebFlux và starter springdoc tương ứng. Nếu chỉ cần endpoint JSON/YAML, dùng starter API; nếu cần Swagger UI, dùng starter UI.

Ví dụ Maven cho ứng dụng có Swagger UI:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
        <version>SPRINGDOC_VERSION</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Thay SPRINGDOC_VERSION bằng phiên bản springdoc tương thích với Spring Boot của dự án. Với ứng dụng không cần giao diện, có thể thay springdoc-openapi-starter-webflux-ui bằng springdoc-openapi-starter-webflux-api.

spring-boot-starter-test cung cấp JUnit Jupiter, AssertJ và Spring Test. Spring Boot tự cấu hình WebTestClient cho bài kiểm thử WebFlux khi dùng annotation test phù hợp.

Nếu endpoint tài liệu được bảo vệ bằng Spring Security và cần giả lập người dùng/token, thêm spring-security-test trong test scope.

## 3. Ví dụ API Reactive để kiểm tra

Giả sử ứng dụng cung cấp API tạo đơn hàng, liệt kê đơn hàng và đọc đơn hàng. Đặt mỗi record DTO trong một file Java riêng. Các DTO dùng kiểu Java rõ ràng để springdoc có thể sinh schema:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;
import java.util.UUID;

@Schema(name = "CreateOrderRequest", description = "Dữ liệu tạo đơn hàng")
public record CreateOrderRequest(
        @Schema(description = "Mã khách hàng", example = "CUS-100")
        @NotBlank
        String customerCode,

        @Schema(description = "Tổng tiền đơn hàng", example = "125.50", minimum = "0.01")
        @Positive
        BigDecimal amount
) {}

@Schema(name = "OrderResponse", description = "Thông tin đơn hàng")
public record OrderResponse(
        @Schema(description = "Mã đơn hàng", format = "uuid")
        UUID id,

        @Schema(description = "Mã khách hàng", example = "CUS-100")
        String customerCode,

        @Schema(description = "Tổng tiền", example = "125.50")
        BigDecimal amount,

        @Schema(description = "Trạng thái đơn hàng", example = "CREATED")
        String state
) {}
~~~

Controller trả về reactive types:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders")
class OrderController {

    @PostMapping
    @Operation(operationId = "createOrder", summary = "Tạo đơn hàng")
    @ApiResponse(
            responseCode = "201",
            description = "Đơn hàng đã được tạo",
            content = @Content(
                    mediaType = MediaType.APPLICATION_JSON_VALUE,
                    schema = @Schema(implementation = OrderResponse.class)))
    Mono<ResponseEntity<OrderResponse>> create(
            @Valid @RequestBody Mono<CreateOrderRequest> request) {
        return request.map(body -> new OrderResponse(
                        UUID.randomUUID(),
                        body.customerCode(),
                        body.amount(),
                        "CREATED"))
                .map(response -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(response));
    }

    @GetMapping
    @Operation(operationId = "listOrders", summary = "Liệt kê đơn hàng")
    Flux<OrderResponse> list() {
        return Flux.just(new OrderResponse(
                UUID.fromString("a8f5f167-f44f-4c5a-9d9c-6f3f3a2b1c00"),
                "CUS-100",
                new java.math.BigDecimal("125.50"),
                "CREATED"));
    }

    @GetMapping("/{id}")
    @Operation(operationId = "getOrderById", summary = "Lấy đơn hàng theo ID")
    Mono<OrderResponse> getById(@PathVariable UUID id) {
        return Mono.just(new OrderResponse(
                id,
                "CUS-100",
                new java.math.BigDecimal("125.50"),
                "CREATED"));
    }

    @GetMapping("/internal")
    @Operation(operationId = "getInternalOrder", summary = "Lấy thông tin đơn hàng nội bộ")
    Mono<OrderResponse> getInternalOrder() {
        return Mono.just(new OrderResponse(
                UUID.randomUUID(),
                "CUS-100",
                new java.math.BigDecimal("125.50"),
                "CREATED"));
    }
}
~~~

Ví dụ dùng Mono để minh họa cách Spring WebFlux nhận request body bất đồng bộ và trả response reactive. Trong ứng dụng thật, handler thường gọi service và repository thay vì tự tạo dữ liệu như ví dụ.

Springdoc xử lý các wrapper reactive như Mono<T> để mô tả kiểu payload T. Với collection, Flux<T> và cách ghi response quyết định nội dung trên HTTP wire; hãy kiểm tra schema được sinh thay vì suy luận chỉ từ tên reactive type.

## 4. Khởi tạo integration test với WebTestClient

Để kiểm tra endpoint OpenAPI được đăng ký trong toàn bộ ứng dụng, dùng @SpringBootTest với server trên cổng ngẫu nhiên:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OpenApiContractTest {

    @Autowired
    WebTestClient webTestClient;

    // Các test được đặt ở đây.
}
~~~

RANDOM_PORT khởi động server thật trên một cổng khả dụng. WebTestClient được Spring Boot cấu hình để gửi request đến server đó. Cách này kiểm tra được web stack, filter chain, security configuration và springdoc auto-configuration trong application context gần với lúc chạy thực tế.

Nếu test cần database hoặc service ngoài, hãy dùng profile test, database test hoặc mock bean phù hợp. Không để integration test phụ thuộc vào dữ liệu hoặc dịch vụ production.

## 5. Gọi endpoint OpenAPI JSON

Test đầu tiên xác nhận endpoint tài liệu trả về JSON:

~~~java
@Test
void openApiDocumentIsAvailable() {
    webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody(JsonNode.class)
            .value(document -> {
                assertThat(document.path("openapi").asText())
                        .startsWith("3.");
                assertThat(document.path("info").path("title").asText())
                        .isNotBlank();
                assertThat(document.path("paths").isObject()).isTrue();
            });
}
~~~

expectStatus().isOk() kiểm tra HTTP status. contentTypeCompatibleWith xác nhận response có media type JSON tương thích. expectBody(JsonNode.class) dùng Jackson decoder để đọc document thành cây JSON; AssertJ sau đó kiểm tra các trường cần thiết.

Không chỉ kiểm tra response không rỗng. Một trang HTML đăng nhập hoặc lỗi proxy có thể không rỗng nhưng không phải OpenAPI document. Kiểm tra media type và parse JSON giúp phát hiện trường hợp đó.

## 6. Kiểm tra path và operationId

Trong OpenAPI JSON, path là key nằm dưới paths; HTTP method là key con. Có thể truy cập node bằng JSON Pointer:

~~~java
@Test
void createOrderOperationHasExpectedIdentity() {
    webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody(JsonNode.class)
            .value(document -> {
                JsonNode operation = document.at(
                        "/paths/~1api~1orders/post");

                assertThat(operation.isMissingNode()).isFalse();
                assertThat(operation.path("operationId").asText())
                        .isEqualTo("createOrder");
                assertThat(operation.path("summary").asText())
                        .isEqualTo("Tạo đơn hàng");
            });
}
~~~

Trong JSON Pointer, ký tự / bên trong một key được escape thành ~1, vì vậy /api/orders trở thành ~1api~1orders. Ký tự ~ được escape thành ~0. Đây là quy tắc của JSON Pointer, không phải quy tắc riêng của springdoc.

Nên kiểm tra operationId vì client generator có thể dùng nó làm tên method. Nếu đổi operationId không có chủ đích, SDK sinh ra có thể thay đổi API bề mặt dù URL HTTP không đổi.

## 7. Kiểm tra request body và schema

Operation tạo đơn hàng cần có request body với media type JSON và schema tương ứng:

~~~java
@Test
void createOrderOperationDocumentsRequestBody() {
    webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody(JsonNode.class)
            .value(document -> {
                JsonNode operation = document.at(
                        "/paths/~1api~1orders/post");
                JsonNode requestBody = operation.path("requestBody");
                JsonNode schema = requestBody.at(
                        "/content/application~1json/schema");

                assertThat(requestBody.path("required").asBoolean()).isTrue();
                assertThat(schema.isMissingNode()).isFalse();

                JsonNode requestSchema = document.at(
                        "/components/schemas/CreateOrderRequest");
                assertThat(requestSchema.path("properties")
                        .has("customerCode")).isTrue();
                assertThat(requestSchema.path("properties")
                        .has("amount")).isTrue();
            });
}
~~~

JSON Pointer escape / trong media type application/json thành application~1json. Nếu schema được cấu hình inline hoặc component schema có tên khác, điều chỉnh đường dẫn assertion theo document thực tế.

Test có thể kiểm tra thêm requestBody.required, content.application/json.schema, field type/format, danh sách required và constraint như minLength, minimum hoặc maxLength nếu chúng là phần hợp đồng quan trọng.

Không nên assert mọi thuộc tính schema một cách cứng nhắc nếu chúng không phải phần hợp đồng quan trọng. Một thay đổi mô tả hoặc thứ tự metadata không nên làm test thất bại nếu hành vi API không đổi.

## 8. Kiểm tra response status và response schema

Operation POST trong ví dụ trả HTTP 201. Kiểm tra response được khai báo:

~~~java
@Test
void createOrderDocumentsCreatedResponse() {
    webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody(JsonNode.class)
            .value(document -> {
                JsonNode response = document.at(
                        "/paths/~1api~1orders/post/responses/201");
                JsonNode schema = response.at(
                        "/content/application~1json/schema");

                assertThat(response.isMissingNode()).isFalse();
                assertThat(response.path("description").asText())
                        .isNotBlank();
                assertThat(schema.isMissingNode()).isFalse();
            });
}
~~~

Nếu controller trả Mono<ResponseEntity<OrderResponse>>, springdoc có thể suy luận response body từ generic type và status mặc định/annotation. Tuy nhiên, status code được chọn động trong handler có thể không được suy luận đầy đủ. Khi cần hợp đồng chính xác, khai báo @ApiResponse hoặc @ApiResponses tường minh.

Không nên chỉ kiểm tra response 200 nếu endpoint thực tế trả 201, 204, 400, 404 hoặc 409 ở các nhánh khác nhau.

## 9. Kiểm tra path parameter

Với route GET /api/orders/{id}, OpenAPI cần có path parameter tên id, vị trí path và trạng thái bắt buộc.

~~~java
@Test
void getOrderDocumentsRequiredUuidPathParameter() {
    webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody(JsonNode.class)
            .value(document -> {
                JsonNode parameters = document.at(
                        "/paths/~1api~1orders~1{id}/get/parameters");

                boolean idFound = false;
                for (JsonNode parameter : parameters) {
                    if ("id".equals(parameter.path("name").asText())) {
                        idFound = true;
                        assertThat(parameter.path("in").asText())
                                .isEqualTo("path");
                        assertThat(parameter.path("required").asBoolean())
                                .isTrue();
                        assertThat(parameter.path("schema").path("format").asText())
                                .isEqualTo("uuid");
                    }
                }
                assertThat(idFound).isTrue();
            });
}
~~~

Path parameter luôn bắt buộc trong OpenAPI. Nếu parameter bị thiếu hoặc tên không khớp với {id}, hãy kiểm tra Spring mapping, @PathVariable hoặc @Parameter và document thực tế.

## 10. Kiểm tra component schema

Schema được tham chiếu nhiều nơi thường nằm trong components.schemas. Có thể xác nhận model có đủ các property quan trọng:

~~~java
@Test
void orderResponseSchemaContainsContractFields() {
    webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody(JsonNode.class)
            .value(document -> {
                JsonNode schema = document.at(
                        "/components/schemas/OrderResponse");
                JsonNode properties = schema.path("properties");

                assertThat(properties.has("id")).isTrue();
                assertThat(properties.has("customerCode")).isTrue();
                assertThat(properties.has("amount")).isTrue();
                assertThat(properties.has("state")).isTrue();
                assertThat(properties.path("id").path("format").asText())
                        .isEqualTo("uuid");
            });
}
~~~

Nếu một schema được inline, không có $ref đến components.schemas. Nếu dùng @Schema(name = ...), cấu hình naming hoặc generic model phức tạp, tên component có thể khác. Hãy đọc output một lần để xác định cấu trúc thực rồi viết assertion theo hợp đồng mong muốn.

## 11. Kiểm tra API runtime bằng cùng WebTestClient

Sau khi xác nhận OpenAPI document, gọi endpoint nghiệp vụ để kiểm tra hành vi thật:

~~~java
@Test
void createOrderReturnsDocumentedStatusAndBody() {
    webTestClient.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                    {
                      "customerCode": "CUS-100",
                      "amount": 125.50
                    }
                    """)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.customerCode").isEqualTo("CUS-100")
            .jsonPath("$.amount").isEqualTo(125.50)
            .jsonPath("$.state").isEqualTo("CREATED");
}
~~~

Test này xác nhận request JSON được xử lý và response runtime có status/body như mong đợi. Nó không tự chứng minh mọi field response đều phù hợp schema; cần kết hợp assertion schema hoặc validator nếu muốn kiểm tra sâu hơn.

Kiểm tra GET:

~~~java
@Test
void getOrderReturnsTheRequestedIdentifier() {
    String id = "a8f5f167-f44f-4c5a-9d9c-6f3f3a2b1c00";

    webTestClient.get()
            .uri("/api/orders/{id}", id)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo(id)
            .jsonPath("$.state").isEqualTo("CREATED");
}
~~~

Trong ứng dụng có database, nên chuẩn bị dữ liệu test xác định trước khi gọi API và dọn dữ liệu sau test. Không dựa vào thứ tự chạy test hoặc dữ liệu còn lại từ test trước.

## 12. Kiểm tra YAML endpoint

Nếu pipeline hoặc consumer sử dụng YAML, kiểm tra endpoint YAML riêng:

~~~java
@Test
void openApiYamlDocumentIsAvailable() {
    webTestClient.get()
            .uri("/v3/api-docs.yaml")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(yaml -> {
                assertThat(yaml).contains("openapi:");
                assertThat(yaml).contains("paths:");
                assertThat(yaml).contains("/api/orders");
            });
}
~~~

Đây là kiểm tra cơ bản cho response YAML. Kiểm tra chuỗi giúp xác nhận endpoint trả nội dung có hình dạng mong đợi, nhưng không phải YAML parser và cũng không thay thế OpenAPI validator. Nếu cần bảo đảm cú pháp và schema, parse YAML bằng thư viện YAML phù hợp rồi chạy validator.

## 13. Kiểm tra document theo group

Nếu ứng dụng khai báo nhiều GroupedOpenApi, test endpoint group thay vì chỉ kiểm tra document mặc định:

Ví dụ khai báo group public và loại route nội bộ khỏi tài liệu public:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/**")
                .pathsToExclude("/api/orders/internal")
                .build();
    }
}
~~~

~~~java
@Test
void publicGroupContainsOnlyPublicOperations() {
    webTestClient.get()
            .uri("/v3/api-docs/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(JsonNode.class)
            .value(document -> {
                assertThat(document.at(
                        "/paths/~1api~1orders/get").isMissingNode()).isFalse();
                assertThat(document.at(
                        "/paths/~1api~1orders~1internal/get").isMissingNode()).isTrue();
            });
}
~~~

Đường dẫn group mặc định thường là /v3/api-docs/{group}. Nếu ứng dụng đổi springdoc.api-docs.path, dùng path đã cấu hình. Group YAML có endpoint riêng; cần kiểm tra URL theo phiên bản springdoc đang dùng.

Test group giúp phát hiện filter pathsToMatch, pathsToExclude, package filter hoặc cấu hình group bị thay đổi ngoài ý muốn. Việc operation không xuất hiện trong group public không thay thế authorization trên endpoint runtime.

## 14. Kiểm tra khi OpenAPI endpoint được bảo vệ

Nếu Spring Security giới hạn tài liệu cho một authority, test cần cung cấp principal phù hợp. Với reactive security và spring-security-test, có thể dùng mock user:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void docsAreAvailableToAuthorizedUser() {
    webTestClient.mutateWith(mockUser().roles("API_DOCS"))
            .get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk();
}
~~~

Nếu endpoint dùng JWT resource server, có thể dùng mockJwt() từ SecurityMockServerConfigurers và gán authority phù hợp. Cấu hình test phải phản ánh rule thực tế của ứng dụng.

Nên có test đối chứng:

- Không có principal: nhận 401 hoặc challenge theo cấu hình.
- Đã xác thực nhưng thiếu role: nhận 403.
- Có role tài liệu: tải được document.
- User chỉ có quyền public: không tải được group admin nếu group đó bị giới hạn.

Đừng cấu hình test security để luôn permitAll rồi kết luận endpoint production đã được bảo vệ đúng.

## 15. Dùng JSON Pointer để viết assertion dễ bảo trì

JSON Pointer là cách truy cập node sâu trong document JSON. Một số ví dụ:

| Thành phần | JSON Pointer |
|---|---|
| OpenAPI version | /openapi |
| Operation POST /api/orders | /paths/~1api~1orders/post |
| OperationId của POST | /paths/~1api~1orders/post/operationId |
| Request body | /paths/~1api~1orders/post/requestBody |
| Response 201 | /paths/~1api~1orders/post/responses/201 |
| Schema OrderResponse | /components/schemas/OrderResponse |

JsonNode.at(...) trả về MissingNode nếu đường dẫn không tồn tại. Kiểm tra isMissingNode() trước khi đọc sâu giúp test báo lỗi rõ ràng thay vì lấy giá trị rỗng rồi gây hiểu nhầm.

Đối với key chứa ký tự đặc biệt:

- Escape ~ thành ~0.
- Escape / thành ~1.
- Các ký tự khác giữ nguyên.

Nên gom các pointer thường dùng thành hằng số hoặc helper method nếu nhiều test cùng kiểm tra một operation. Điều này giảm lỗi gõ sai path.

## 16. Tách test document khỏi test controller slice

@WebFluxTest phù hợp để kiểm tra một lát cắt web, chẳng hạn mapping và serialization của controller. Tuy nhiên, slice test chỉ nạp một tập bean được chọn và có thể không tái hiện đầy đủ cấu hình springdoc, group, security hoặc customizer của toàn ứng dụng.

| Cách khởi tạo | Phạm vi phù hợp |
|---|---|
| @WebFluxTest(Controller.class) | Test controller, mapping và web behavior trong slice |
| @SpringBootTest(webEnvironment = MOCK) | Nạp application context đầy đủ với mock web environment |
| @SpringBootTest(webEnvironment = RANDOM_PORT) + @AutoConfigureWebTestClient | Test HTTP qua server thật trên cổng ngẫu nhiên |
| WebTestClient.bindToApplicationContext(context).build() | Tự bind client vào application context trong test |

Nếu mục tiêu là xác nhận endpoint /v3/api-docs được cấu hình đúng như ứng dụng chạy, ưu tiên integration test với application context đầy đủ. Nếu dùng @WebFluxTest, cần import rõ các cấu hình và bean cần thiết, sau đó xác minh springdoc endpoint thực sự được đăng ký trong test context.

## 17. Kiểm tra reactive stream và collection response

Với WebFlux, controller có thể trả Mono<T> hoặc Flux<T>. Cần kiểm tra schema theo representation thực tế:

- Mono<OrderResponse> thường được mô tả thành một object response.
- Flux<OrderResponse> được serialize thành một chuỗi phần tử; với application/json, response thường được biểu diễn như JSON array.
- text/event-stream hoặc application/x-ndjson có semantics streaming khác JSON array.

Ví dụ test JSON array:

~~~java
@Test
void listOrdersReturnsJsonArray() {
    webTestClient.get()
            .uri("/api/orders")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$[0].customerCode").isEqualTo("CUS-100");
}
~~~

OpenAPI document phải mô tả đúng array schema nếu client nhận JSON array. Nếu route trả Server-Sent Events, hãy kiểm tra media type và event format tương ứng; không mặc định mọi Flux đều là array.

## 18. Xác minh request validation và error response

Nếu request DTO dùng Bean Validation, test runtime nên gửi cả payload hợp lệ và không hợp lệ:

~~~java
@Test
void createOrderRejectsBlankCustomerCode() {
    webTestClient.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                    {
                      "customerCode": "",
                      "amount": 125.50
                    }
                    """)
            .exchange()
            .expectStatus().isBadRequest();
}
~~~

Status cụ thể phụ thuộc validation, exception handler và error contract của ứng dụng. Nếu ứng dụng chuẩn hóa lỗi thành ProblemDetail hoặc ApiErrorResponse, hãy kiểm tra cả response body và so sánh với schema lỗi trong OpenAPI.

OpenAPI có thể hiển thị minLength, minimum hoặc required property từ Bean Validation, nhưng chỉ khi springdoc nhận biết constraint và cấu hình tương ứng. Test document và test runtime nên cùng xác nhận ràng buộc quan trọng để tránh tài liệu nói một đằng, server xử lý một nẻo.

## 19. Kiểm tra bằng validator ngoài WebTestClient

Các assertion trên phù hợp để khóa các phần hợp đồng quan trọng. Tuy nhiên, chúng không xác nhận toàn bộ document tuân thủ OpenAPI specification và không tự validate mọi response body theo schema.

Trong pipeline có thể bổ sung:

1. Tải OpenAPI JSON từ /v3/api-docs.
2. Parse document thành OpenAPI model.
3. Chạy OpenAPI validator tương thích với phiên bản openapi trong document.
4. Dùng JSON Schema validator phù hợp để kiểm tra payload mẫu nếu cần.
5. Chạy contract test với request/response thực tế.
6. So sánh artifact với bản trước để phát hiện breaking change.

Chọn validator hiểu đúng OpenAPI 3.0 hoặc 3.1 đang được sinh ra. Validator chỉ hỗ trợ 3.0 có thể không hiểu đầy đủ Schema Object theo JSON Schema Draft 2020-12 của OpenAPI 3.1.

## 20. Chạy test trong CI

Một pipeline kiểm thử hợp đồng reactive có thể gồm:

1. Biên dịch ứng dụng và test source.
2. Khởi tạo application context bằng @SpringBootTest.
3. Chạy test endpoint /v3/api-docs và group docs bằng WebTestClient.
4. Chạy test runtime API bằng cùng client.
5. Tải artifact OpenAPI JSON/YAML nếu pipeline cần lưu riêng.
6. Chạy OpenAPI validator và contract diff.
7. Lưu kết quả test cùng OpenAPI artifact của build.

Ví dụ lệnh Maven:

~~~bash
mvn -B test
~~~

Ví dụ lệnh Gradle:

~~~bash
./gradlew test
~~~

Không cần khởi động một server riêng nếu integration test đã dùng RANDOM_PORT; Spring Boot test sẽ quản lý server trong vòng đời test. Nếu pipeline có bước export ngoài test, cần chờ ứng dụng sẵn sàng trước khi gọi endpoint.

## 21. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| /v3/api-docs trả 404 trong test | Springdoc auto-configuration không được nạp hoặc API docs bị tắt | Dùng full application context và kiểm tra starter/config |
| Test controller pass nhưng docs test fail | @WebFluxTest không nạp đủ cấu hình springdoc | Chuyển docs test sang @SpringBootTest hoặc import cấu hình cần thiết |
| JsonNode.at(...) trả MissingNode | JSON Pointer sai, path/method khác hoặc operation không được sinh | Kiểm tra raw document và escape / thành ~1 |
| operationId không đúng | Thiếu hoặc thay đổi @Operation(operationId = ...) | Đặt operationId ổn định và duy nhất |
| Request body schema không xuất hiện | Reactive wrapper hoặc DTO không được nhận diện như mong đợi | Kiểm tra @RequestBody, generic type và OpenAPI JSON |
| Response schema bị inline | Springdoc không tạo component $ref trong cấu hình hiện tại | Assertion theo schema thực tế, không ép buộc $ref nếu không phải hợp đồng |
| Response 201 không có trong document | Status được tạo động mà không khai báo metadata | Dùng @ApiResponse để mô tả status rõ ràng |
| Test docs nhận 401/403 | Endpoint bị bảo vệ và test không có principal phù hợp | Dùng mockUser()/mockJwt() hoặc cấu hình credential |
| JSON parse lỗi | Endpoint trả HTML hoặc response bị cắt | Kiểm tra status, Content-Type và response body |
| YAML test chỉ tìm được text nhưng cú pháp sai | Chỉ kiểm tra substring | Parse bằng YAML parser và chạy validator |
| Flux schema không phải array như mong đợi | Media type hoặc cách ghi response là streaming | Kiểm tra HTTP Content-Type và schema thực tế |
| Test phụ thuộc dữ liệu cũ | Không seed/reset dữ liệu | Chuẩn bị fixture độc lập cho mỗi test |
| Test pass nhưng SDK client vẫn sai | Assertion chưa kiểm tra constraint hoặc generator khác cách hiểu | Thêm validator, generate SDK thử nghiệm và contract test |

## 22. Checklist kiểm thử hợp đồng

- [ ] Integration test nạp application context có springdoc.
- [ ] WebTestClient gọi được endpoint OpenAPI JSON.
- [ ] OpenAPI version và metadata info đúng.
- [ ] Path và HTTP method xuất hiện đúng.
- [ ] operationId ổn định, duy nhất và đúng tên.
- [ ] Path/query/header parameter có đúng tên, vị trí và required.
- [ ] Request body có đúng media type và schema.
- [ ] Response status, content type và schema đúng.
- [ ] Component schema và $ref được phân giải.
- [ ] Group document chứa đúng operation.
- [ ] Security rule cho docs được kiểm tra với principal phù hợp.
- [ ] API runtime được gọi và trả kết quả đúng.
- [ ] Validation/error response khớp hợp đồng.
- [ ] YAML được parse nếu pipeline sử dụng YAML.
- [ ] OpenAPI validator và contract diff được chạy khi cần.

## 23. Nguyên tắc thiết kế

- Dùng WebTestClient để kiểm tra endpoint tài liệu và endpoint nghiệp vụ trong ứng dụng Reactive.
- Dùng full application context khi cần xác minh springdoc auto-configuration, group và customizer.
- Dùng RANDOM_PORT để kiểm tra qua server HTTP thật.
- Kiểm tra OpenAPI document bằng JsonNode/JSON Pointer thay vì chỉ xác nhận response không rỗng.
- Khóa các phần hợp đồng quan trọng: operationId, parameter, request body, response code và schema.
- Kiểm tra API runtime riêng để xác nhận hành vi thực tế.
- Phân biệt Mono, Flux, JSON array và streaming media type.
- Kiểm tra security của endpoint docs bằng user/token giả lập phù hợp.
- Không giả định WebTestClient tự động validate OpenAPI schema.
- Kết hợp OpenAPI validator, JSON Schema validator và contract diff trong CI khi phạm vi dự án yêu cầu.

## Kết luận

WebTestClient giúp kiểm tra OpenAPI document được springdoc sinh ra ngay trong integration test của ứng dụng Spring WebFlux. Dùng @SpringBootTest(webEnvironment = RANDOM_PORT) cùng @AutoConfigureWebTestClient để nạp đầy đủ cấu hình và gọi /v3/api-docs; sau đó đọc JSON bằng JsonNode để xác nhận version, path, operationId, parameter, request body, response và component schema. Dùng cùng client gọi API runtime để kiểm tra status, header và body thực tế. Với group, YAML, security hoặc validation, bổ sung test riêng theo cấu hình ứng dụng. Cuối cùng, kết hợp OpenAPI/JSON Schema validator khi cần kiểm tra toàn bộ ngữ nghĩa hợp đồng, vì các assertion của WebTestClient không tự thay thế validator.

## Tài liệu tham khảo

- [Spring Framework Reference: WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Boot Reference: Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [springdoc-openapi v2 documentation](https://springdoc.org/v2/)
- [Spring Security Reference: Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
