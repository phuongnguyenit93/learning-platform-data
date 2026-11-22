# Kiểm tra endpoint đặc tả trả đúng mã trạng thái và kiểu nội dung

Một API contract không chỉ mô tả dữ liệu JSON. Nó còn quy định endpoint trả HTTP status nào, response dùng media type nào và trong trường hợp lỗi thì client nhận được định dạng gì. Nếu OpenAPI công bố `200` với `application/json` nhưng ứng dụng thực tế trả `500`, hoặc trả `text/plain` thay vì JSON, consumer có thể không xử lý được dù URL và controller vẫn hoạt động.

Với springdoc-openapi, có thể kiểm tra hợp đồng ở hai lớp liên quan:

1. **Tài liệu OpenAPI:** operation công bố đúng status code và response content type.
2. **Endpoint đang chạy:** request thực tế nhận đúng status code, `Content-Type` và cấu trúc body tương ứng.

Kiểm thử cả hai lớp giúp phát hiện trường hợp tài liệu sai so với implementation và trường hợp implementation thay đổi nhưng hợp đồng chưa được cập nhật.

## 1. Status code và Content-Type là một phần của contract

Mỗi response HTTP có status line, header và có thể có body. Trong các phần này:

- **Status code** cho biết kết quả xử lý ở mức HTTP, ví dụ `200 OK`, `201 Created`, `204 No Content`, `400 Bad Request`, `404 Not Found`.
- **Content-Type** cho biết media type của body response, ví dụ `application/json` hoặc `application/problem+json`.
- **Accept** là header của request, thể hiện media type client muốn nhận; server có thể dùng nó để content negotiation.
- **Request Content-Type** mô tả định dạng body client gửi lên, ví dụ `application/json`.

Không nhầm `Accept` với `Content-Type`. Client gửi `Accept: application/json` không có nghĩa request body là JSON. Ngược lại, `Content-Type: application/json` ở request không bảo đảm server sẽ trả JSON nếu endpoint không khai báo hoặc không hỗ trợ định dạng đó.

Ví dụ một endpoint đọc đơn hàng:

| Tình huống | Status mong đợi | Content-Type mong đợi |
|---|---:|---|
| Tìm thấy đơn hàng | `200 OK` | `application/json` |
| Không tìm thấy đơn hàng | `404 Not Found` | `application/problem+json` |
| Request body sai định dạng | `415 Unsupported Media Type` | Có thể là `application/problem+json` nếu ứng dụng chuẩn hóa lỗi theo định dạng này |
| Client yêu cầu media type không hỗ trợ | `406 Not Acceptable` | Phụ thuộc error handler và negotiation policy |
| Tạo đơn hàng thành công | `201 Created` | Thường là `application/json` nếu trả representation; có thể không có body tùy contract |
| Xóa thành công, không trả body | `204 No Content` | Không có response body, vì vậy không cần Content-Type |

Một status code đúng nhưng media type sai vẫn là contract violation. Ví dụ, consumer chờ JSON để deserialize response `404` nhưng server trả HTML error page thì client có thể thất bại khi xử lý lỗi.

## 2. Mô tả status code và media type trong OpenAPI

OpenAPI biểu diễn response theo status code dưới `responses`. Mỗi response có thể khai báo `content` với một hoặc nhiều media type.

Ví dụ tài liệu cho endpoint đọc đơn hàng:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Tìm thấy đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Không tìm thấy đơn hàng
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ProblemDetail'
~~~

Đọc hợp đồng theo từng nhánh:

- Khi đơn hàng tồn tại, server trả status `200` và representation JSON theo schema `OrderResponse`.
- Khi đơn hàng không tồn tại, server trả `404` và body theo media type `application/problem+json`.
- Nếu response `204`, thường chỉ khai báo `description`, không khai báo `content` vì response không có body.

Không khai báo `200` cho mọi trường hợp chỉ vì controller trả object. Status của lỗi, redirect hoặc response rỗng cần được mô tả riêng.

## 3. Khai báo response bằng annotation springdoc

springdoc đọc metadata OpenAPI từ annotation của `swagger-annotations`. Có thể mô tả status và content type bằng `@Operation`, `@ApiResponse`, `@Content` và `@Schema`.

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

`produces` là điều kiện mapping của Spring, ảnh hưởng đến content negotiation ở runtime. `@ApiResponse` mô tả response trong OpenAPI. Hai khai báo nên thống nhất nhưng đảm nhiệm hai nhiệm vụ khác nhau: một khai báo hành vi mapping, một khai báo hợp đồng tài liệu.

Khi response có nhiều media type, khai báo từng `@Content` hoặc định nghĩa tương ứng trong OpenAPI. Đừng khai báo `application/json` trong annotation nếu controller thực tế có thể trả HTML hoặc một media type khác trong cùng tình huống.

## 4. Chuẩn hóa response lỗi bằng ProblemDetail

Spring Framework hỗ trợ `ProblemDetail` để biểu diễn lỗi theo Problem Details for HTTP APIs. Với Spring Boot 3 trở lên, có thể dùng kiểu này để trả lỗi có cấu trúc.

Ví dụ exception handler:

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
    public ResponseEntity<ProblemDetail> handleOrderNotFound(
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

Việc đặt content type tường minh giúp response lỗi giữ đúng contract. Nếu ứng dụng có nhiều loại lỗi, hãy chuẩn hóa mapping giữa exception, status và body trong một nơi để tránh mỗi controller trả một định dạng khác nhau.

Ví dụ body:

~~~json
{
  "type": "about:blank",
  "title": "Order not found",
  "status": 404,
  "detail": "Order 42 does not exist"
}
~~~

Nếu ứng dụng dùng error format riêng thay vì ProblemDetail, hãy mô tả schema riêng và dùng media type đúng với body thực tế. Không nên đổi mọi lỗi sang `application/problem+json` chỉ bằng annotation nếu exception handler vẫn trả body dạng khác.

## 5. Kiểm thử endpoint Spring MVC bằng MockMvc

Với ứng dụng Spring MVC, `MockMvc` gửi request qua Spring MVC infrastructure mà không cần khởi chạy HTTP server thật. Đây là lựa chọn phù hợp để kiểm tra status, response header, Content-Type và body.

Giả sử `OrderService` trả về một đơn hàng có ID `42`, test có thể kiểm tra:

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
class OrderContractTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void getExistingOrderReturns200AndJson() throws Exception {
        mockMvc.perform(
                get("/api/orders/{id}", 42)
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.id").value(42));
    }
}
~~~

Các assertion kiểm tra ba điều:

1. Server trả status `200`.
2. Response có Content-Type tương thích với `application/json`.
3. Body có trường `id` như contract mong đợi.

`contentTypeCompatibleWith` so sánh media type tương thích và không làm test thất bại chỉ vì response có thêm parameter như `charset`. Nếu hợp đồng yêu cầu một giá trị header chính xác, hãy kiểm tra header cụ thể bằng `header().string(...)` hoặc so sánh `MediaType` sau khi parse.

### Kiểm tra nhánh 404

Test lỗi cần xác minh cả status và media type, không chỉ xác minh body có thông báo:

~~~java
@Test
void getMissingOrderReturns404ProblemJson() throws Exception {
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

Ở đây client chấp nhận cả `application/json` và `application/problem+json`: response thành công dùng JSON, còn response lỗi dùng Problem JSON. Đây là một contract hợp lệ nếu tài liệu OpenAPI công bố response `404` với đúng media type đó.

Nếu API có Spring Security, test cần thiết lập authentication/authorization phù hợp, chẳng hạn `@WithMockUser` cho MVC test. Nếu không, request có thể nhận `401` hoặc `403` trước khi đi tới controller và khiến test contract thất bại vì lý do bảo mật.

## 6. Kiểm tra chính OpenAPI document do springdoc sinh

Kiểm tra response runtime vẫn chưa đủ. Tài liệu có thể đang công bố sai status hoặc content type. Hãy đọc trực tiếp `/v3/api-docs` thay vì chỉ mở Swagger UI.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void openApiDocumentDeclaresExpectedResponses() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON
        ))
        .andExpect(jsonPath("$.openapi").exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['200'].content['application/json']"
        ).exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['404'].content['application/problem+json']"
        ).exists());
}
~~~

Test này xác minh document có OpenAPI version ở cấp root, response `200` với content `application/json` và response `404` với content `application/problem+json`.

Nếu path, group hoặc media type của dự án khác ví dụ, thay JSONPath tương ứng. Nếu dùng API group, kiểm tra URL `/v3/api-docs/{groupName}`. Nếu tài liệu bị bảo vệ bởi Spring Security, test phải có quyền đọc endpoint tài liệu.

Việc test `/v3/api-docs` cũng giúp phát hiện annotation bị xóa, `@ApiResponse` bị thay đổi hoặc controller không còn được springdoc quét. Đây là kiểm tra contract document; nó không thay thế test gọi endpoint thật ở phần trước.

## 7. Kiểm thử ứng dụng Spring WebFlux bằng WebTestClient

Với ứng dụng WebFlux, có thể dùng `WebTestClient` để gửi request và kiểm tra response. Khi chạy integration test trên server thật, cấu hình như sau:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveOrderContractTest {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void getOrderReturns200AndJson() {
        webTestClient.get()
            .uri("/api/orders/{id}", 42)
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            )
            .expectBody()
            .jsonPath("$.id").isEqualTo(42);
    }
}
~~~

Với WebFlux, ý nghĩa assertion không đổi: kiểm tra status, Content-Type và body. `WebTestClient` có thể hoạt động với mock server hoặc server thật; chọn cách khởi tạo phù hợp với mục tiêu test. Dùng `RANDOM_PORT` khi cần xác minh cả HTTP server đang chạy và cấu hình thực tế.

Không dùng `MockMvc` cho ứng dụng WebFlux thuần. Hãy chọn test client phù hợp với web stack để test đi qua đúng infrastructure.

## 8. Kiểm tra request Content-Type và Accept

Response contract còn phụ thuộc request header. Spring mapping có thể khai báo `consumes` và `produces`:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<OrderResponse> create(
        @RequestBody CreateOrderRequest request) {
    OrderResponse created = orderService.create(request);
    URI location = URI.create("/api/orders/" + created.id());

    return ResponseEntity
        .created(location)
        .contentType(MediaType.APPLICATION_JSON)
        .body(created);
}
~~~

Kiểm thử request gửi JSON và nhận `201`:

~~~java
mockMvc.perform(
        post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content(objectMapper.writeValueAsString(request))
    )
    .andExpect(status().isCreated())
    .andExpect(header().string("Location", endsWith("/api/orders/42")))
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ));
~~~

Hai tình huống lỗi negotiation cần phân biệt:

| Request | Điều kiện mapping | Kết quả thường mong đợi |
|---|---|---|
| Gửi `Content-Type: text/plain` tới endpoint chỉ `consumes: application/json` | Request body không đúng media type được chấp nhận | `415 Unsupported Media Type` |
| Gửi `Accept: text/html` tới endpoint chỉ `produces: application/json` | Server không thể tạo representation client chấp nhận | `406 Not Acceptable` |

Có thể kiểm tra:

~~~java
mockMvc.perform(
        post("/api/orders")
            .contentType(MediaType.TEXT_PLAIN)
            .content("not-json")
    )
    .andExpect(status().isUnsupportedMediaType());

mockMvc.perform(
        get("/api/orders/{id}", 42)
            .accept(MediaType.TEXT_HTML)
    )
    .andExpect(status().isNotAcceptable());
~~~

Các status negotiation có thể chịu ảnh hưởng bởi filter, exception handler, proxy và cấu hình content negotiation. Hãy xác định policy của ứng dụng rồi khóa policy đó bằng test. Không giả định mọi API đều phải trả cùng một error body nếu ứng dụng chưa chuẩn hóa error handling.

## 9. Trường hợp 204 No Content

`204 No Content` báo rằng thao tác thành công nhưng response không có body. Vì không có representation nên không nên kiểm tra `Content-Type: application/json`.

Ví dụ endpoint xóa:

~~~java
@DeleteMapping("/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable long id) {
    orderService.delete(id);
}
~~~

Test:

~~~java
mockMvc.perform(delete("/api/orders/{id}", 42))
    .andExpect(status().isNoContent())
    .andExpect(content().string(""));
~~~

OpenAPI tương ứng:

~~~yaml
responses:
  '204':
    description: Đã xóa đơn hàng
~~~

Không khai báo `content` cho response 204 nếu server không trả body. Một test đòi JSON ở response này sẽ kiểm tra sai hợp đồng.

## 10. Đối chiếu response runtime với OpenAPI

Một bộ contract test tối thiểu nên ghép test document và test endpoint thành ma trận:

| Operation | OpenAPI response | Runtime assertion |
|---|---|---|
| `GET /api/orders/{id}` khi tìm thấy | `200` + `application/json` | `isOk()` + Content-Type JSON |
| `GET /api/orders/{id}` khi không tìm thấy | `404` + `application/problem+json` | `isNotFound()` + Content-Type Problem JSON |
| `POST /api/orders` hợp lệ | `201` + `application/json` và `Location` | `isCreated()` + JSON + Location |
| `POST /api/orders` sai Content-Type | `415` + error format đã chuẩn hóa | `isUnsupportedMediaType()` + media type lỗi |
| `DELETE /api/orders/{id}` thành công | `204`, không có content | `isNoContent()` + body rỗng |

Nếu tài liệu khai báo response `200` nhưng implementation trả `201`, cần quyết định hợp đồng nào đúng rồi sửa controller hoặc tài liệu. Không nên đổi assertion để test pass mà chưa xác định API contract mong muốn.

Khi dùng springdoc, có thể giữ các test sau:

- Test document: kiểm tra `responses` có đúng status và media type.
- Test provider: gọi endpoint thật, kiểm tra status/header/body.
- Test consumer: kiểm tra client có xử lý được các status và media type đã công bố.

Với hệ thống nhiều service, consumer-driven contract testing bằng Pact hoặc Spring Cloud Contract có thể bổ sung việc xác nhận tương tác giữa provider và consumer. Các công cụ này không thay thế việc mô tả OpenAPI; chúng kiểm tra kỳ vọng tương tác cụ thể của consumer và có thể chạy trong pipeline của cả hai bên.

## 11. Kiểm tra response có nhiều media type

Một endpoint có thể hỗ trợ nhiều định dạng response, ví dụ JSON và XML:

~~~java
@GetMapping(
    value = "/{id}",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
public OrderResponse getById(@PathVariable long id) {
    return orderService.getById(id);
}
~~~

OpenAPI cần công bố cả hai media type nếu ứng dụng thực sự serialize được cả JSON và XML:

~~~yaml
responses:
  '200':
    description: Tìm thấy đơn hàng
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderResponse'
      application/xml:
        schema:
          $ref: '#/components/schemas/OrderResponse'
~~~

Test hai lựa chọn:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ));

mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_XML
    ));
~~~

Chỉ khai báo `application/xml` trong OpenAPI nếu ứng dụng có XML message converter và endpoint thực sự trả XML. Annotation `produces` có thể làm Spring chọn mapping, nhưng nếu converter không hỗ trợ media type đó thì request vẫn có thể lỗi.

## 12. Kiểm tra OpenAPI endpoint cũng là một HTTP contract

Endpoint tài liệu do springdoc cung cấp cũng có status và Content-Type riêng. Với JSON document mặc định, có thể kiểm tra:

~~~java
mockMvc.perform(get("/v3/api-docs")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ))
    .andExpect(jsonPath("$.openapi").exists())
    .andExpect(jsonPath("$.paths").exists());
~~~

Nếu ứng dụng công bố YAML tại `/v3/api-docs.yaml`, hãy kiểm tra status, header và nội dung theo đúng media type mà phiên bản springdoc đang trả. Không hard-code `application/yaml` hoặc `text/yaml` theo phỏng đoán; hãy quan sát response của phiên bản đang dùng và thống nhất contract đó trong test.

Nếu tài liệu được bảo vệ bằng Spring Security, test cần xác minh cả hai nhánh: người có quyền nhận `200` và người không có quyền nhận status từ chối phù hợp. Đây là HTTP contract của tài liệu OpenAPI, tách biệt với contract của business endpoint.

## 13. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Status đúng nhưng test Content-Type thất bại | Controller hoặc exception handler trả sai media type | Kiểm tra `produces`, converter và `ResponseEntity.contentType` |
| Response JSON bị test fail vì charset | So sánh Content-Type quá chặt | Dùng `contentTypeCompatibleWith` nếu charset không phải phần cần khóa |
| API trả 404 nhưng body là HTML | Error page hoặc proxy xử lý lỗi trước controller advice | Chuẩn hóa error handling và kiểm tra cả proxy/gateway |
| OpenAPI có 200 nhưng thiếu 404 | Chưa mô tả `@ApiResponse` hoặc exception response | Khai báo response lỗi trong annotation/customizer |
| OpenAPI công bố JSON nhưng runtime trả XML | `produces`, message converter và annotation không thống nhất | Kiểm tra content negotiation và chỉ công bố media type runtime hỗ trợ |
| Test nhận 401/403 thay vì status business | Security filter chặn request trước controller | Thiết lập user/role trong test hoặc kiểm tra policy security |
| Test 204 thất bại vì thiếu Content-Type | Test đang đòi media type cho response không có body | Chỉ kiểm tra status và body rỗng |
| Request JSON bị 415 | Thiếu hoặc sai request `Content-Type`, mapping `consumes` không khớp | Gửi đúng `Content-Type` và xác minh consumes contract |
| Request nhận 406 | `Accept` không tương thích với `produces` | Gửi Accept được hỗ trợ hoặc điều chỉnh contract |
| Test OpenAPI trả 404 | Chưa cài springdoc API/UI starter, docs bị tắt hoặc path đã đổi | Kiểm tra dependency và `springdoc.api-docs.path` |
| Test document pass nhưng endpoint runtime fail | Chỉ kiểm tra file OpenAPI mà không gọi provider | Bổ sung integration test cho status/header/body thực tế |
| Swagger UI hiển thị đúng nhưng contract test fail | UI có thể render tài liệu dù operation response khai báo thiếu hoặc sai | Kiểm tra JSON `/v3/api-docs` và assertion trực tiếp |

## 14. Quy trình đưa contract test vào CI

Một pipeline cơ bản có thể thực hiện:

1. Build ứng dụng và khởi tạo Spring test context.
2. Gọi `/v3/api-docs` để xác minh tài liệu sinh thành công.
3. Kiểm tra OpenAPI document có operation, response code và media type bắt buộc.
4. Gọi từng endpoint quan trọng với request hợp lệ và không hợp lệ.
5. Kiểm tra status, Content-Type, header quan trọng và body.
6. So sánh document mới với baseline để phát hiện thay đổi contract.
7. Chạy consumer contract tests hoặc smoke tests nếu có service tích hợp.
8. Chỉ phát hành artifact khi tài liệu và hành vi runtime cùng thỏa contract.

Các kiểm tra status và media type thường chạy nhanh, nên có thể đặt trong suite integration test ở pull request. Test cần bao phủ cả nhánh thành công, lỗi nghiệp vụ, lỗi validation và negotiation nếu đó là hành vi được công bố.

## 15. Checklist trước khi phát hành API

- [ ] Mỗi operation có status code thành công chính xác.
- [ ] Các status lỗi quan trọng như 400, 401, 403, 404, 409, 415 được mô tả nếu API có thể trả chúng.
- [ ] Mỗi response có body đều khai báo media type phù hợp.
- [ ] Response không có body như 204 không khai báo content không cần thiết.
- [ ] Request `Content-Type` và `Accept` được kiểm tra riêng.
- [ ] Error response dùng một định dạng ổn định, chẳng hạn `application/problem+json`.
- [ ] `@ApiResponse`/OpenAPI document thống nhất với controller và exception handler.
- [ ] Integration test xác minh status và Content-Type thực tế.
- [ ] Test OpenAPI JSON xác minh response code và media type được công bố.
- [ ] Test có xác thực đúng security context nếu endpoint được bảo vệ.
- [ ] Pipeline kiểm tra contract trước khi phát hành.

## 16. Tài liệu tham khảo chính thức

- [springdoc-openapi — Getting Started and Features](https://springdoc.org/) — cách tích hợp springdoc và xuất OpenAPI document từ Spring Boot.
- [OpenAPI Specification — Responses Object](https://spec.openapis.org/oas/latest.html#responses-object) — cấu trúc response theo HTTP status code.
- [OpenAPI Specification — Response Object](https://spec.openapis.org/oas/latest.html#response-object) — mô tả response và content.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html) — kiểm thử Spring MVC request/response mà không cần server thật.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — kiểm thử WebFlux và HTTP endpoint bằng reactive test client.
- [Spring Framework — Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html) — chuẩn hóa lỗi HTTP với ProblemDetail.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) — status code, content negotiation và ý nghĩa HTTP header.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html) — định dạng `application/problem+json` cho response lỗi.

Kiểm thử hợp đồng với springdoc cần xác minh cả những gì OpenAPI công bố và những gì endpoint thật sự trả về. Với mỗi nhánh response, hãy khóa status code và Content-Type trước, sau đó kiểm tra body/header cần thiết; điều này giúp consumer nhận đúng loại phản hồi mà tài liệu đã hứa.
