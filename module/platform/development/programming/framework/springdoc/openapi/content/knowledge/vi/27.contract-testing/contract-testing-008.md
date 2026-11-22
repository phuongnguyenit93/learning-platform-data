# Kiểm tra hợp đồng sinh ra bằng MockMvc trong ứng dụng Servlet

Trong ứng dụng Spring MVC chạy trên Servlet stack, `MockMvc` cho phép gửi request qua `DispatcherServlet`, handler mapping, controller, converter và exception handler ngay trong test. Không cần mở cổng HTTP hoặc khởi chạy embedded server. Đây là cách thuận tiện để kiểm tra hợp đồng ở hai nơi: response thực tế của endpoint và OpenAPI document mà springdoc sinh ra từ controller.

Một test chỉ xác nhận controller trả `200` chưa chứng minh tài liệu OpenAPI mô tả đúng response. Ngược lại, test chỉ kiểm tra `/v3/api-docs` cũng chưa chứng minh endpoint thật sự trả đúng status và `Content-Type`. Hãy dùng cùng một test context để xác minh cả hai phía, sau đó đối chiếu chúng với nhau.

## 1. MockMvc kiểm tra những gì?

Trong một ứng dụng Servlet, request được xử lý qua các thành phần chính:

1. `MockMvc` tạo request mô phỏng HTTP.
2. `DispatcherServlet` tìm handler phù hợp.
3. Controller thực thi và trả kết quả.
4. `HttpMessageConverter` ghi response body và Content-Type.
5. `@ControllerAdvice` xử lý exception nếu có.
6. Test kiểm tra status, header và body.

springdoc cũng chạy trong Spring application context và thu thập metadata từ controller, annotation và cấu hình. Vì vậy, cùng test context có thể gọi `/v3/api-docs`, đọc JSON document và kiểm tra status code/media type đã được mô tả.

MockMvc không mở socket HTTP thật. Nó kiểm tra luồng xử lý của Spring MVC bên trong application context. Nếu cần xác minh reverse proxy, TLS, container Servlet, gateway hoặc cấu hình triển khai bên ngoài ứng dụng, cần thêm smoke test chạy qua HTTP server thật ở môi trường phù hợp.

## 2. Chuẩn bị dependency và test context

Ứng dụng cần Spring MVC, springdoc WebMVC và Spring Boot Test:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
        <version>SPRINGDOC_VERSION</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Chỉ cần nếu test có Spring Security / @WithMockUser -->
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu cần Swagger UI trong ứng dụng, có thể dùng `springdoc-openapi-starter-webmvc-ui`; module UI đã cung cấp phần sinh OpenAPI document. Chỉ cần module API khi test và consumer chỉ cần endpoint tài liệu JSON/YAML.

Chọn dòng springdoc tương thích với dòng Spring Boot đang sử dụng. Dependency test `spring-boot-starter-test` cung cấp JUnit Jupiter, MockMvc, JSONPath, AssertJ và Mockito integration.

### Dùng full application context

Để kiểm tra tài liệu do springdoc sinh, cấu hình tối thiểu là:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class MvcTestSetup {

    @Autowired
    MockMvc mockMvc;
}
~~~

Đây là khung cấu hình rút gọn; phần test đầy đủ được trình bày ở mục tiếp theo.

`@SpringBootTest` nạp application context đầy đủ, bao gồm cấu hình springdoc và các bean liên quan. `@AutoConfigureMockMvc` tạo MockMvc để gửi request qua Servlet MVC mà không khởi động server.

`@WebMvcTest` phù hợp khi chỉ muốn test một lát cắt controller. Tuy nhiên, slice test không nhất thiết nạp toàn bộ auto-configuration và bean của springdoc. Nếu mục tiêu là kiểm tra `/v3/api-docs` được sinh từ ứng dụng, hãy dùng full context hoặc chủ động import đầy đủ cấu hình cần thiết. Đừng kết luận springdoc lỗi chỉ vì một MVC slice test không có endpoint tài liệu.

## 3. Controller mẫu có response contract rõ ràng

Giả sử API đọc đơn hàng có hai trường hợp: tìm thấy đơn hàng trả `200 application/json`; không tìm thấy trả `404 application/problem+json`.

DTO:

~~~java
public record OrderResponse(
    long id,
    String status
) {}
~~~

Controller:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    @Operation(
        operationId = "getOrderById",
        summary = "Lấy đơn hàng theo ID",
        responses = {
            @ApiResponse(
                responseCode = "200",
                description = "Tìm thấy đơn hàng",
                content = @Content(
                    mediaType = MediaType.APPLICATION_JSON_VALUE,
                    schema = @Schema(implementation = OrderResponse.class)
                )
            ),
            @ApiResponse(
                responseCode = "404",
                description = "Không tìm thấy đơn hàng",
                content = @Content(
                    mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
                    schema = @Schema(implementation = ProblemDetail.class)
                )
            )
        }
    )
    public OrderResponse getById(@PathVariable long id) {
        return orderService.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
    }
}
~~~

Exception handler:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            OrderNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            exception.getMessage()
        );
        problem.setTitle("Order not found");

        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

`produces` là điều kiện mapping của Spring, ảnh hưởng đến content negotiation ở runtime. `@ApiResponse` mô tả response trong OpenAPI. Exception handler quyết định response lỗi thật sự. Test cần xác minh ba phần này thống nhất.

## 4. Kiểm tra endpoint OpenAPI bằng MockMvc

Trước hết, gọi endpoint tài liệu do springdoc sinh:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiContractMvcTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void apiDocsEndpointReturnsOpenApiJson() throws Exception {
        mockMvc.perform(
                get("/v3/api-docs")
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.info.title").exists())
            .andExpect(jsonPath("$.paths").exists());
    }
}
~~~

Test này kiểm tra chính endpoint tài liệu:

- HTTP status là `200`.
- Response Content-Type tương thích với `application/json`.
- Body có trường `openapi`, `info` và `paths`.

Nếu dự án thay đổi `springdoc.api-docs.path`, thay `/v3/api-docs` bằng path đã cấu hình. Nếu tài liệu được chia group, gọi `/v3/api-docs/{groupName}` để kiểm tra đúng document.

Không nên chỉ kiểm tra status `200`: một reverse proxy hoặc error handler có thể trả HTML với status thành công. Kiểm tra Content-Type và cấu trúc JSON giúp xác nhận endpoint thật sự trả OpenAPI document.

## 5. Kiểm tra response code và media type được sinh trong document

Một OpenAPI document hợp lệ có thể vẫn mô tả thiếu response. Hãy kiểm tra trực tiếp `paths`, `responses` và `content`:

~~~java
@Test
void generatedDocumentDeclaresOrderResponseContract() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.operationId"
        ).value("getOrderById"))
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['200'].description"
        ).value("Tìm thấy đơn hàng"))
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['200'].content['application/json']"
        ).exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['404'].description"
        ).value("Không tìm thấy đơn hàng"))
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['404'].content['application/problem+json']"
        ).exists());
}
~~~

Các assertion khóa những phần quan trọng của hợp đồng:

| JSONPath | Điều được xác minh |
|---|---|
| `paths['/api/orders/{id}'].get.operationId` | Operation có ID ổn định |
| `responses['200'].description` | Có response thành công |
| `responses['200'].content['application/json']` | Response 200 công bố JSON |
| `responses['404'].description` | Có response lỗi không tìm thấy |
| `responses['404'].content['application/problem+json']` | Response 404 công bố Problem JSON |

JSONPath dùng bracket notation để truy cập path có dấu `/`, `{}` và media type có dấu `/` hoặc `+`. Cách này tránh lỗi khi viết biểu thức cho tên property đặc biệt.

Không nên khóa mọi chi tiết của document nếu chúng không thuộc contract cần bảo vệ. Ví dụ, thay đổi thứ tự property trong JSON thường không phải thay đổi API contract. Hãy ưu tiên assertion cho path, method, status, media type, schema reference và các field có ý nghĩa với consumer.

## 6. Kiểm tra schema của response

Chỉ xác nhận media type tồn tại chưa đảm bảo schema được gắn đúng. Có thể kiểm tra `$ref`:

~~~java
@Test
void generatedDocumentReferencesExpectedSchemas() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['200'].content['application/json'].schema['$ref']"
        ).value("#/components/schemas/OrderResponse"))
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['404'].content['application/problem+json'].schema['$ref']"
        ).exists())
        .andExpect(jsonPath(
            "$.components.schemas.OrderResponse.properties.id.type"
        ).value("integer"))
        .andExpect(jsonPath(
            "$.components.schemas.OrderResponse.properties.status.type"
        ).value("string"));
}
~~~

Schema có thể được inline hoặc tham chiếu qua `$ref`, tùy cấu hình và cách springdoc xử lý model. Nếu dự án thay đổi cách resolve schema, assertion nên kiểm tra ngữ nghĩa tương đương thay vì phụ thuộc vào một cách serialize duy nhất.

Nếu `OrderResponse` đổi từ `long` sang `String`, test schema sẽ phát hiện contract document thay đổi. Nếu thay đổi đó không tương thích với consumer, cần review như một thay đổi API, không chỉ là thay đổi Java model.

## 7. Kiểm tra response thật của controller bằng MockMvc

Sau khi xác minh document, hãy gọi chính endpoint để kiểm tra hành vi runtime. Trong test context đầy đủ, có thể thay service bằng mock để dữ liệu ổn định.

Với Spring Framework 6.2 và Spring Boot 3.4 trở lên, dùng `@MockitoBean`:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@SpringBootTest
@AutoConfigureMockMvc
class OrderEndpointContractMvcTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void existingOrderReturns200AndJson() throws Exception {
        given(orderService.findById(42L))
            .willReturn(Optional.of(new OrderResponse(42L, "PAID")));

        mockMvc.perform(
                get("/api/orders/{id}", 42)
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

Với Spring Boot cũ chưa có `@MockitoBean`, có thể dùng `@MockBean` từ Spring Boot Test. Tên annotation thay đổi theo phiên bản nền tảng; cách kiểm tra MockMvc không đổi.

Test trên xác minh controller thực sự trả `200`, JSON và body có dữ liệu đúng. Nếu chỉ test document mà bỏ qua endpoint, có thể bỏ sót lỗi trong exception handler, converter hoặc controller logic.

## 8. Kiểm tra response lỗi và Content-Type

Stub service trả về `Optional.empty()` để kiểm tra nhánh không tìm thấy:

~~~java
@Test
void missingOrderReturns404AndProblemJson() throws Exception {
    given(orderService.findById(999L))
        .willReturn(Optional.empty());

    mockMvc.perform(
            get("/api/orders/{id}", 999)
                .accept(
                    MediaType.APPLICATION_JSON,
                    MediaType.APPLICATION_PROBLEM_JSON
                )
        )
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.status").value(404))
        .andExpect(jsonPath("$.title").value("Order not found"));
}
~~~

Client chấp nhận cả media type thành công và lỗi. Response lỗi phải giữ đúng `404` và `application/problem+json` như OpenAPI document đã công bố.

Nếu exception handler trả `application/json` thay vì `application/problem+json`, test phải thất bại. Khi đó cần xác định hợp đồng dự kiến rồi sửa handler hoặc tài liệu; không nên nới assertion chỉ để test pass.

## 9. Kiểm tra Content-Type request và content negotiation

MockMvc có thể mô phỏng header `Content-Type` và `Accept` để kiểm tra điều kiện mapping:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Request gửi sai media type:

~~~java
mockMvc.perform(
        post("/api/orders")
            .contentType(MediaType.TEXT_PLAIN)
            .content("not-json")
    )
    .andExpect(status().isUnsupportedMediaType());
~~~

Request yêu cầu response media type không được hỗ trợ:

~~~java
mockMvc.perform(
        get("/api/orders/{id}", 42)
            .accept(MediaType.TEXT_HTML)
    )
    .andExpect(status().isNotAcceptable());
~~~

Các kết quả `415` và `406` phụ thuộc mapping, converter, exception handler và cấu hình content negotiation. Nếu ứng dụng chuẩn hóa body lỗi, hãy kiểm tra thêm Content-Type và schema lỗi. Nếu không có policy body ổn định, trước tiên chỉ khóa status theo hành vi đã xác định.

## 10. Dùng ObjectMapper khi JSONPath không đủ

Với document lớn hoặc assertion phức tạp, có thể lấy response body và parse thành `JsonNode`. Cách này hữu ích khi cần kiểm tra nhiều operation trong một test:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;

@Autowired
ObjectMapper objectMapper;

@Test
void generatedDocumentContainsExpectedStatusAndMediaTypes() throws Exception {
    MvcResult result = mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andReturn();

    JsonNode document = objectMapper.readTree(
        result.getResponse().getContentAsByteArray()
    );

    JsonNode operation = document
        .path("paths")
        .path("/api/orders/{id}")
        .path("get");

    JsonNode responses = operation.path("responses");

    assertThat(responses.has("200")).isTrue();
    assertThat(responses.has("404")).isTrue();
    assertThat(
        responses.path("200").path("content").has("application/json")
    ).isTrue();
    assertThat(
        responses.path("404").path("content")
            .has("application/problem+json")
    ).isTrue();
}
~~~

`JsonNode.path()` trả về node rỗng nếu field không tồn tại, vì vậy các assertion `has(...)` giúp phát hiện chính xác phần bị thiếu. Có thể tạo helper để kiểm tra response code và media type cho nhiều operation mà không lặp JSONPath dài.

Không nên so sánh toàn bộ chuỗi JSON bằng `content().json(expected)`, trừ khi mục tiêu thật sự là khóa toàn bộ document. OpenAPI có thể thay đổi thứ tự property hoặc metadata phụ mà không làm thay đổi contract. Assertion theo cấu trúc thường bền vững hơn.

## 11. Kiểm tra OpenAPI group

Nếu ứng dụng có nhiều `GroupedOpenApi`, mỗi group có document riêng. Test cần gọi đúng endpoint:

~~~java
@Test
void partnerGroupContainsOnlyPartnerOperation() throws Exception {
    mockMvc.perform(get("/v3/api-docs/partner"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['200']"
        ).exists())
        .andExpect(jsonPath(
            "$.paths['/admin/users'].get"
        ).doesNotExist());
}
~~~

Đừng chỉ kiểm tra document mặc định nếu Swagger UI đang trỏ tới group riêng. Một group có thể bị cấu hình sai package/path dù document mặc định vẫn đầy đủ.

Nếu group name hoặc `springdoc.api-docs.path` được thay đổi, cập nhật URL trong test theo cấu hình. Có thể dùng property riêng cho test profile, nhưng không nên tạo test config khác xa cấu hình production đến mức test không còn xác minh đúng document sẽ phát hành.

## 12. Kiểm tra security khi tài liệu được bảo vệ

Trong ứng dụng Servlet, Spring Security filter chạy trước controller. Nếu `/v3/api-docs` yêu cầu xác thực, test cần cung cấp user có quyền:

~~~java
import org.springframework.security.test.context.support.WithMockUser;

@Test
@WithMockUser(roles = "API_READER")
void authorizedUserCanReadOpenApiDocument() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON
        ));
}
~~~

Có thể có test riêng cho người chưa đăng nhập:

~~~java
@Test
void anonymousUserCannotReadProtectedOpenApiDocument() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isUnauthorized());
}
~~~

Status thực tế có thể là `302` nếu ứng dụng dùng form login hoặc redirect, thay vì trả `401`. Hãy viết assertion theo chính sách security của API.

Không dùng `@AutoConfigureMockMvc(addFilters = false)` trong test security contract. Thuộc tính này tắt filter chain và có thể khiến endpoint tài liệu có vẻ public dù production đang bảo vệ nó. Chỉ tắt filter khi mục tiêu test được giới hạn rõ ràng ở controller và security đã được kiểm thử riêng.

## 13. Kiểm tra YAML document

springdoc có thể cung cấp OpenAPI YAML tại `/v3/api-docs.yaml`. Nếu dự án phát hành YAML cho API portal hoặc code generation, có thể kiểm tra endpoint đó bằng MockMvc:

~~~java
@Test
void yamlApiDocsEndpointIsAvailable() throws Exception {
    mockMvc.perform(get("/v3/api-docs.yaml"))
        .andExpect(status().isOk())
        .andExpect(content().string(org.hamcrest.Matchers.containsString(
            "openapi:"
        )));
}
~~~

Content-Type của YAML có thể khác theo phiên bản springdoc và cách cấu hình. Hãy đọc response header của ứng dụng đang chạy rồi thêm assertion chính xác theo contract của dự án; không đoán media type rồi khóa một giá trị sai.

Nếu muốn kiểm tra cấu trúc YAML sâu hơn, parse body bằng YAML parser đã có trong test classpath, sau đó kiểm tra cùng các field `paths`, `responses` và `content`. Tránh chỉ kiểm tra chuỗi `openapi:` nếu pipeline phụ thuộc vào status và media type của endpoint YAML.

## 14. Tổ chức test để tránh trùng lặp và flaky

Một suite MVC có thể chia theo trách nhiệm:

| Test class hoặc nhóm test | Mục tiêu |
|---|---|
| `OpenApiDocumentMvcTest` | Endpoint `/v3/api-docs`, path, operation, status và media type được sinh |
| `OrderEndpointMvcTest` | Response runtime của controller: status, Content-Type, body và header |
| `ApiErrorMvcTest` | Exception handler, ProblemDetail và error response |
| `OpenApiGroupMvcTest` | Document của từng group và phạm vi operation |
| `OpenApiSecurityMvcTest` | Quyền truy cập tài liệu và response khi không đủ quyền |

Một số nguyên tắc giúp test ổn định:

- Dùng dữ liệu cố định hoặc stub service; không phụ thuộc database dùng chung nếu mục tiêu chỉ là HTTP contract.
- Không so sánh toàn bộ OpenAPI JSON nếu chỉ cần khóa vài phần của contract.
- Chỉ assert `Content-Type` của response có body; response `204` không cần content.
- Dùng `contentTypeCompatibleWith` nếu không cần khóa parameter như charset.
- Dùng `@SpringBootTest` cho document sinh từ toàn bộ ứng dụng; dùng `@WebMvcTest` cho controller slice khi không cần auto-configuration springdoc.
- Giữ test security bật filter chain khi kiểm tra quyền truy cập.
- Không dựa vào thứ tự operation hoặc thứ tự property trong JSON.

## 15. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `/v3/api-docs` trả 404 trong `@WebMvcTest` | MVC slice không nạp auto-configuration springdoc | Dùng `@SpringBootTest` hoặc import cấu hình cần thiết có chủ đích |
| `/v3/api-docs` trả 401/403 | Spring Security bảo vệ endpoint tài liệu | Dùng user/role phù hợp hoặc kiểm tra chính sách anonymous |
| Document trả 200 nhưng Content-Type là HTML | Redirect/login/error page hoặc route khác đang trả response | Kiểm tra filter chain, redirect và endpoint path |
| OpenAPI không có response 404 | Thiếu metadata `@ApiResponse` hoặc exception response | Bổ sung mô tả response lỗi và kiểm tra document được sinh |
| Response document có status nhưng thiếu `content` | Annotation không khai báo schema/media type hoặc response thực sự không có body | Kiểm tra `@Content` và contract của response |
| Runtime trả Problem JSON nhưng OpenAPI chỉ công bố JSON | Exception handler và annotation không đồng nhất | Mô tả `application/problem+json` cho response lỗi |
| JSONPath không tìm thấy path có `{id}` | Biểu thức JSONPath không escape path property đúng | Dùng bracket notation `['/api/orders/{id}']` |
| Test fail sau khi đổi OpenAPI version | Assertion khóa một giá trị version không còn phù hợp | Chỉ khóa version nếu đó là yêu cầu; nếu không, kiểm tra field tồn tại và validate document |
| Test pass nhưng production trả khác | Test profile khác mapping, security hoặc converter production | Giữ cấu hình test sát production và thêm smoke test qua server/proxy |
| `@MockitoBean` không tồn tại | Spring Framework/Boot đang dùng chưa có annotation này | Dùng `@MockBean` tương thích với phiên bản Boot hoặc nâng cấp test stack |
| Test 204 đòi Content-Type | Response không có body | Chỉ xác minh status và body rỗng |
| Test 406/415 không ổn định | Converter, filter hoặc error handler thay đổi | Khóa cấu hình content negotiation và kiểm tra status/header thực tế |

## 16. Đưa MockMvc contract test vào CI

Một pipeline CI cho ứng dụng Servlet có thể chạy theo trình tự:

1. Resolve dependency springdoc tương thích với Spring Boot.
2. Khởi tạo full application context trong test.
3. Gọi `/v3/api-docs` bằng MockMvc và kiểm tra status/Content-Type.
4. Kiểm tra các operation quan trọng, response code, media type và schema reference.
5. Gọi endpoint business bằng MockMvc để kiểm tra status/header/body thật.
6. Kiểm tra error handler, content negotiation và security theo các nhánh quan trọng.
7. So sánh document mới với baseline nếu nhóm có quy trình phát hiện breaking change.
8. Chỉ tạo artifact phát hành khi document và endpoint đều thỏa contract.

Test document và test endpoint nên chạy ở pull request vì thường nhanh hơn test end-to-end qua nhiều service. Khi có reverse proxy, gateway hoặc container-specific behavior, bổ sung một lớp smoke test qua server thật để kiểm tra phần nằm ngoài phạm vi MockMvc.

## 17. Checklist trước khi merge

- [ ] Test dùng `@SpringBootTest` và `@AutoConfigureMockMvc` khi cần xác minh document springdoc đầy đủ.
- [ ] `/v3/api-docs` trả status thành công.
- [ ] Endpoint tài liệu trả Content-Type JSON phù hợp.
- [ ] OpenAPI document có path và HTTP method mong đợi.
- [ ] Response code thành công và lỗi được công bố.
- [ ] Mỗi response có body công bố đúng media type.
- [ ] Schema hoặc `$ref` của response trỏ tới component mong đợi.
- [ ] MockMvc xác minh endpoint runtime trả status và Content-Type đúng.
- [ ] Exception handler trả body lỗi khớp document.
- [ ] Group document được kiểm tra riêng nếu ứng dụng có nhiều group.
- [ ] Security filter không bị vô hiệu hóa trong test security contract.
- [ ] Test không phụ thuộc thứ tự property hoặc toàn bộ chuỗi JSON.
- [ ] CI chạy suite trước khi phát hành OpenAPI artifact.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html) — cách gửi request qua Spring MVC `DispatcherServlet` trong test.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html) — `@SpringBootTest`, `@AutoConfigureMockMvc` và test application context.
- [springdoc-openapi — Getting Started](https://springdoc.org/) — tích hợp springdoc với Spring Boot và endpoint OpenAPI JSON/YAML.
- [OpenAPI Specification — Responses Object](https://spec.openapis.org/oas/latest.html#responses-object) — cách khai báo response theo HTTP status code.
- [OpenAPI Specification — Response Object](https://spec.openapis.org/oas/latest.html#response-object) — mô tả response, header và media type.
- [Spring Framework — Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html) — chuẩn hóa response lỗi bằng `ProblemDetail`.

MockMvc giúp kiểm tra hợp đồng HTTP của ứng dụng Servlet mà không cần mở server thật. Khi kết hợp assertion trên `/v3/api-docs` với assertion gọi endpoint business, nhóm có thể phát hiện cả tài liệu mô tả sai lẫn implementation trả khác hợp đồng đã công bố.
