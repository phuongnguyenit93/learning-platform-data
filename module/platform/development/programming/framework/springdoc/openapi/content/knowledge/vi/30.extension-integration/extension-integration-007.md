# Ánh xạ operation thành công cụ và yêu cầu metadata rõ ràng

OpenAPI mô tả các operation mà một API cung cấp. Một hệ thống tích hợp có thể chuyển một phần operation đó thành công cụ để ứng dụng khác, agent hoặc nền tảng điều phối gọi theo một giao diện có cấu trúc. Tuy nhiên, một operation HTTP không tự động trở thành tool an toàn và dễ dùng. Cần chọn operation phù hợp, xác định input/output, giữ đúng ý nghĩa của parameter, bổ sung metadata rõ ràng và áp dụng chính sách xác thực, phân quyền ở phía server.

springdoc-openapi giúp tạo OpenAPI document từ controller Spring Boot và các annotation. Tài liệu này có thể làm nguồn đầu vào cho adapter sinh tool definition, MCP server hoặc function-calling integration. springdoc không tự biến mọi endpoint thành tool và cũng không quyết định operation nào được phép thực thi. Phần ánh xạ cần một lớp tích hợp có quy tắc riêng.

Bài này trình bày cách chọn operation, chuẩn hóa tên và mô tả tool, ánh xạ request/response schema, khai báo extension metadata, giữ security context, xử lý side effect và kiểm thử contract của tool sau khi sinh từ OpenAPI.

## 1. Operation HTTP và tool có mục đích khác nhau

OpenAPI Operation Object mô tả một hành động HTTP tại một path, ví dụ GET /api/orders/{id}. Tool definition mô tả một hành động có tên, mục đích, input schema và đôi khi output schema để một hệ thống khác có thể lựa chọn và gọi.

Hai khái niệm liên quan nhưng không đồng nhất:

| OpenAPI operation | Tool definition |
|---|---|
| Được xác định bởi path và HTTP method | Được xác định bởi tên tool trong registry |
| Có parameters, requestBody và responses | Có input schema và kết quả trả về |
| Dùng server URL, security scheme và HTTP semantics | Dùng tool runtime, credential context và chính sách gọi |
| Có summary, description, operationId, tags | Có name, description và metadata phục vụ lựa chọn |
| Mô tả hợp đồng HTTP | Mô tả một khả năng mà consumer có thể yêu cầu thực hiện |

Ví dụ một operation đọc đơn hàng:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
      summary: Lấy thông tin đơn hàng
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Đơn hàng được tìm thấy
~~~

Lớp tích hợp có thể chuyển operation trên thành tool tên get_order_by_id với input gồm mã đơn hàng. Khi tool được gọi, adapter tạo HTTP GET đến endpoint tương ứng và trả kết quả cho hệ thống gọi.

Không nên coi đây là phép đổi tên đơn giản. Adapter phải hiểu parameter nằm ở path, query hay header; request body được serialize thế nào; credential được cung cấp ra sao; và response/error được biểu diễn thế nào.

## 2. Kiến trúc ánh xạ từ Spring Boot đến tool runtime

Một kiến trúc dễ kiểm soát tách việc sinh tài liệu, lựa chọn operation và thực thi HTTP:

~~~mermaid
flowchart TD
    A[Spring Boot controllers] --> B[springdoc-openapi]
    B --> C[OpenAPI JSON document]
    C --> D[Operation selection and policy]
    D --> E[Tool definition adapter]
    E --> F[Tool registry: MCP or function calling]
    G[Tool invocation] --> H[Input validation]
    H --> I[Authentication and authorization context]
    I --> J[HTTP client adapter]
    J --> K[Spring Boot API]
    K --> L[Response and error mapping]
    L --> M[Tool result]
~~~

Các thành phần có trách nhiệm riêng:

- **Spring Boot API:** thực thi nghiệp vụ và kiểm tra quyền truy cập.
- **springdoc-openapi:** sinh OpenAPI document phản ánh operation và schema.
- **Operation selector:** chọn operation nào được phép công bố dưới dạng tool.
- **Tool definition adapter:** chuyển metadata và schema OpenAPI sang định dạng tool đích.
- **Tool runtime:** nhận lời gọi, kiểm tra input và quản lý phiên thực thi.
- **HTTP client adapter:** tạo request với đúng path, query, header, body và credential.
- **Result mapper:** chuyển status, header, response body và lỗi thành kết quả tool.

Không nên để tool runtime gọi tùy ý mọi URL do model cung cấp. Adapter phải lấy URL và method từ operation đã được chọn trong OpenAPI document hoặc registry đã kiểm duyệt. Điều này giúp giới hạn destination, method và phạm vi hành động.

## 3. Chọn operation phù hợp để công bố thành tool

Không phải mọi endpoint đều có ích hoặc phù hợp với tool calling. Hãy chọn theo mục tiêu nghiệp vụ và khả năng thực thi an toàn.

Những operation thường phù hợp:
- Tra cứu thông tin bằng một định danh rõ ràng.
- Tìm kiếm có giới hạn và phân trang.
- Đọc trạng thái một tác vụ hoặc tài nguyên.
- Tạo yêu cầu nghiệp vụ có input schema rõ ràng và quy trình xác nhận phù hợp.
- Thực hiện một hành động có side effect nhưng được kiểm soát bằng quyền và policy.

Những operation cần cân nhắc kỹ hoặc thường nên loại khỏi tool registry:
- Endpoint quản trị, debug, actuator hoặc nội bộ.
- Endpoint thực thi SQL, shell, proxy URL hoặc truy cập tài nguyên tùy ý.
- Endpoint xóa hàng loạt hoặc thao tác không thể hoàn tác.
- Endpoint nhận file lớn, stream liên tục hoặc payload nhị phân phức tạp nếu tool protocol không hỗ trợ.
- Endpoint yêu cầu session/cookie gắn với browser mà adapter không quản lý đúng.
- Endpoint có input mơ hồ, thiếu giới hạn hoặc mô tả không đủ để chọn chính xác.

Một tool nên đại diện cho một hành động có mục tiêu dễ hiểu. Nếu một operation cần hàng chục tham số kỹ thuật và nhiều bước điều phối, cân nhắc tạo một API facade chuyên biệt với input đơn giản hơn thay vì đưa nguyên endpoint phức tạp ra ngoài.

## 4. Metadata cần có trên mỗi operation

Một operation có thể chạy được nhưng vẫn khó chuyển thành tool nếu metadata thiếu hoặc mơ hồ. Tối thiểu nên xác định:

| Metadata | Vai trò khi ánh xạ tool |
|---|---|
| operationId | Định danh ổn định để liên kết operation và tool |
| summary | Tên hành động ngắn, dễ hiểu |
| description | Giải thích mục đích, điều kiện, giới hạn và side effect |
| tags | Nhóm operation theo miền nghiệp vụ |
| parameters | Định nghĩa input nằm ở path/query/header/cookie |
| requestBody | Schema và media type của dữ liệu gửi |
| responses | Schema kết quả và status code |
| security | Cơ chế xác thực và scope cần thiết |
| deprecated | Báo operation đang trong giai đoạn ngừng sử dụng |
| servers | Base URL và môi trường gọi |
| examples | Ví dụ input/output giúp consumer hiểu cách dùng |
| vendor extensions | Metadata riêng như tool name, enabled, read-only hoặc confirmation policy |

Trong OpenAPI, các trường metadata của operation thuộc Operation Object. springdoc có thể sinh chúng từ annotation hoặc cấu hình OpenAPI customizer.

Không dùng description thay cho schema. Một câu “id là mã đơn hàng” không đủ để thay thế parameter có name, location, required và type. Tool adapter cần dữ liệu có cấu trúc để tạo input schema và request.

## 5. Viết operationId ổn định và duy nhất

operationId là định danh tốt để liên kết operation với tool vì nó không phụ thuộc trực tiếp vào URL. Theo OpenAPI, nếu operationId được cung cấp thì cần duy nhất trong document.

Ví dụ:

~~~yaml
get:
  operationId: getOrderById
  summary: Lấy thông tin đơn hàng
~~~

Có thể chuẩn hóa thành tool name get_order_by_id. Tên tool nên:
- Duy nhất trong registry mà consumer nhìn thấy.
- Ổn định qua các lần refactor path.
- Ngắn gọn, dùng động từ và đối tượng nghiệp vụ.
- Không chứa thông tin môi trường hoặc secret.
- Tuân theo giới hạn ký tự của tool protocol đích.
- Có quy tắc xử lý trùng tên giữa document group hoặc API version.

Nếu nhiều service cùng có operationId getOrderById, registry có thể thêm namespace theo service hoặc group, ví dụ orders_get_order_by_id. Nếu có x-tool-name thì dùng theo policy đã thống nhất; không âm thầm tạo tên khác nhau mỗi lần export.

Đổi operationId có thể không làm wire request thay đổi nhưng có thể làm generated SDK hoặc tool registry đổi tên hàm. Vì vậy, operationId nên được xem là metadata có tính ổn định và thay đổi cần review.

## 6. Summary và description phải giúp chọn đúng tool

Summary nên nêu hành động bằng một cụm ngắn, thường theo dạng động từ + đối tượng. Description giải thích điều kiện sử dụng và kết quả.

Ví dụ tốt:

~~~yaml
operationId: cancelOrder
summary: Hủy đơn hàng
description: >
  Hủy một đơn hàng chưa được giao. Cần quyền orders:cancel.
  Không thể hủy đơn đã hoàn tất hoặc đã bàn giao cho đơn vị vận chuyển.
~~~

Ví dụ kém:

~~~yaml
operationId: updateStatus
summary: Update
description: API cập nhật trạng thái.
~~~

Mô tả rõ cần trả lời:
- Tool dùng để làm gì?
- Khi nào nên gọi?
- Input có ý nghĩa gì?
- Điều kiện trước khi thực hiện là gì?
- Hành động có tạo, sửa hoặc xóa dữ liệu không?
- Kết quả thành công thể hiện thế nào?
- Trường hợp nào sẽ bị từ chối?
- Có cần xác nhận từ người dùng trước khi gọi không?

Tránh nhồi toàn bộ tài liệu nghiệp vụ vào description. Nội dung nên ngắn nhưng đủ để chọn đúng tool và chuẩn bị input. Chi tiết về kiểu dữ liệu, required, enum và constraint cần đặt trong schema.

## 7. Ánh xạ parameter theo đúng vị trí HTTP

OpenAPI phân biệt parameter theo trường in:

- path: nằm trong URL path.
- query: nằm trong query string.
- header: nằm trong HTTP header.
- cookie: nằm trong cookie.

Tool protocol thường nhận một JSON object làm input. Adapter cần giữ thông tin vị trí để khi thực thi có thể tạo request đúng.

Một cách biểu diễn rõ ràng là nhóm input theo vị trí:

~~~json
{
  "path": {
    "id": "order-1001"
  },
  "query": {
    "includeItems": true
  }
}
~~~

Tool schema tương ứng có thể mô tả path và query là hai object con. Adapter dùng path.id để thay placeholder và query.includeItems để tạo query string.

Một số hệ thống muốn flatten tất cả field vào cùng một object. Nếu chọn cách đó, cần có quy tắc xử lý trường trùng tên và metadata mapping ngược về vị trí HTTP. Không được tự suy ra một field nằm ở path hay query chỉ từ tên.

Parameter path luôn phải được cung cấp để tạo URL hợp lệ. Required của query/header/cookie phải được giữ theo OpenAPI. Default chỉ nên áp dụng khi hợp đồng và runtime có hành vi mặc định tương ứng.

## 8. Ánh xạ requestBody và media type

Request body thường là phần input lớn nhất của tool. Adapter cần xác định media type và schema được hỗ trợ.

Ví dụ operation nhận JSON:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required: [customerId]
        properties:
          customerId:
            type: string
~~~

Tool input có thể đặt payload trong field body:

~~~json
{
  "body": {
    "customerId": "customer-42",
    "items": [
      {
        "sku": "SKU-100",
        "quantity": 2
      }
    ]
  }
}
~~~

Adapter serialize body thành JSON và gửi Content-Type application/json.

Các trường hợp cần adapter chuyên biệt:
- application/x-www-form-urlencoded.
- multipart/form-data và file upload.
- application/octet-stream.
- XML hoặc media type tùy biến.
- Streaming request hoặc event stream.

Không chuyển mọi schema body thành JSON rồi gửi bất kể media type. Nếu tool protocol không hỗ trợ một dạng payload, hãy loại operation khỏi registry hoặc cung cấp adapter riêng. Đừng công bố tool mà runtime không thể thực thi đúng hợp đồng.

Nếu operation có nhiều media type, cần chọn representation được hỗ trợ và ghi rõ trong metadata. Không tự chọn một content type bất kỳ khi các representation có semantics khác nhau.

## 9. Giữ nguyên required, nullable, enum và constraint

Khi chuyển OpenAPI Schema Object thành input schema của tool, cần giữ các quy tắc quan trọng:

- required: field bắt buộc phải xuất hiện.
- type: kiểu JSON được chấp nhận.
- enum: tập giá trị được phép.
- minimum/maximum: giới hạn số.
- minLength/maxLength/pattern: ràng buộc chuỗi.
- minItems/maxItems/uniqueItems: ràng buộc mảng.
- nullable hoặc union có null: khả năng nhận giá trị null theo OpenAPI version.
- additionalProperties: quy tắc với field không khai báo.
- oneOf/anyOf/allOf: schema composition.

Ví dụ:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId, items]
  properties:
    customerId:
      type: string
      minLength: 1
    items:
      type: array
      minItems: 1
      items:
        type: object
        required: [sku, quantity]
        properties:
          sku:
            type: string
          quantity:
            type: integer
            minimum: 1
~~~

Tool adapter không nên bỏ constraint chỉ để đơn giản hóa schema. Nếu JSON Schema dialect hoặc tool protocol chỉ hỗ trợ một tập con, cần phát hiện và xử lý rõ ràng. Có thể từ chối operation không tương thích, tạo schema tương đương có kiểm chứng hoặc bổ sung validation runtime; không âm thầm làm input trở nên rộng hơn.

Đặc biệt, required trong request schema là yêu cầu của provider. Nếu adapter bỏ required, model có thể gửi payload thiếu field và chỉ nhận lỗi khi request tới server.

## 10. Không biến credential thành input do model điều khiển

OpenAPI có thể mô tả security scheme như Bearer authentication, API key hoặc OAuth2. Khi ánh xạ operation thành tool, không nên đưa access token, API key hay client secret thành property trong input schema để model tự điền.

Credential nên được cung cấp từ context tin cậy:
- User session hoặc identity của người đang yêu cầu.
- Token được cấp qua OAuth flow của ứng dụng.
- Service identity giới hạn quyền cho integration.
- Secret store hoặc credential provider của runtime.

Luồng thực thi nên:
1. Xác định principal của người gọi.
2. Lấy credential tương ứng từ hệ thống xác thực.
3. Kiểm tra principal có quyền gọi tool hay không.
4. Gửi credential qua HTTP client.
5. Để Spring Security hoặc API gateway xác thực và phân quyền lại ở provider.

Security requirement trong OpenAPI giúp adapter biết operation cần scheme/scope nào. Nó không thay thế authorization runtime. Provider vẫn phải kiểm tra quyền trên từng request, kể cả khi tool registry đã ẩn operation khỏi người dùng không đủ quyền.

## 11. Mô tả side effect và mức độ rủi ro

Tool có thể đọc dữ liệu hoặc thay đổi trạng thái. Metadata cần giúp runtime và người vận hành nhận diện hành vi.

Ví dụ phân loại:

| Hành động | HTTP thường gặp | Side effect |
|---|---|---|
| Tra cứu đơn hàng | GET | Không chủ đích thay đổi tài nguyên |
| Tạo đơn hàng | POST | Tạo dữ liệu mới |
| Cập nhật địa chỉ | PUT/PATCH | Thay đổi dữ liệu |
| Hủy đơn hàng | POST/DELETE | Có thể gây hậu quả nghiệp vụ |
| Xuất báo cáo | POST | Có thể tạo job hoặc file |

Không chỉ dựa vào HTTP method để phân loại. Một GET triển khai sai vẫn có thể ghi log nghiệp vụ, tạo job hoặc thay đổi trạng thái; một POST có thể chỉ chạy truy vấn. Hãy kiểm tra semantics thực tế của endpoint.

Nếu tool protocol hỗ trợ annotation như read-only, destructive hoặc idempotent, hãy ánh xạ dựa trên hành vi đã xác minh. Các annotation này là metadata/hint để consumer đưa ra quyết định; chúng không phải cơ chế authorization và không thay thế xác nhận người dùng.

Với hành động có side effect:
- Mô tả rõ hậu quả.
- Xác định quyền cần thiết.
- Dùng idempotency key nếu API hỗ trợ và thao tác có thể retry.
- Xác định khi nào cần confirmation.
- Trả về định danh tài nguyên hoặc operation để kiểm tra kết quả.
- Không tự retry thao tác không idempotent khi chưa biết request trước có thành công hay không.

## 12. Dùng vendor extension để bổ sung tool metadata

OpenAPI cho phép thêm specification extension có tên bắt đầu bằng x-. Có thể dùng extension để mô tả chính sách tích hợp riêng của dự án.

Ví dụ:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
      summary: Lấy thông tin đơn hàng
      description: Tra cứu một đơn hàng theo mã.
      x-tool-enabled: true
      x-tool-name: get_order
      x-tool-read-only: true
      x-tool-confirmation-required: false
      x-tool-category: orders
~~~

Một extension khác có thể mô tả thao tác ghi:

~~~yaml
paths:
  /api/orders/{id}/cancel:
    post:
      operationId: cancelOrder
      summary: Hủy đơn hàng
      description: Hủy đơn chưa bàn giao vận chuyển.
      x-tool-enabled: true
      x-tool-name: cancel_order
      x-tool-read-only: false
      x-tool-destructive: true
      x-tool-confirmation-required: true
      x-tool-category: orders
~~~

Các extension x-tool-* ở trên là quy ước riêng của dự án, không phải field chuẩn của OpenAPI. Hãy định nghĩa schema hoặc tài liệu governance cho extension để mọi service và adapter hiểu giống nhau.

Extension chỉ nên điều khiển việc công bố và mô tả tool. Nó không được làm provider bỏ qua security, validation hoặc authorization. Nếu extension thiếu hoặc sai kiểu, adapter nên fail validation hoặc bỏ operation theo policy rõ ràng, không tự đoán giá trị.

## 13. Khai báo metadata cơ bản bằng Swagger annotations

springdoc đọc các annotation của swagger-core để sinh operation metadata. Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @Operation(
        operationId = "getOrderById",
        summary = "Lấy thông tin đơn hàng",
        description = "Tra cứu một đơn hàng theo mã. "
            + "Yêu cầu quyền orders:read. "
            + "Trả về 404 nếu mã đơn hàng không tồn tại.",
        tags = {"orders"},
        responses = {
            @ApiResponse(
                responseCode = "200",
                description = "Đơn hàng được tìm thấy"
            ),
            @ApiResponse(
                responseCode = "404",
                description = "Không tìm thấy đơn hàng"
            )
        }
    )
    @GetMapping("/api/orders/{id}")
    OrderResponse getOrderById(
        @Parameter(
            name = "id",
            in = ParameterIn.PATH,
            required = true,
            description = "Mã đơn hàng",
            schema = @Schema(type = "string", minLength = 1)
        )
        @PathVariable String id
    ) {
        // Gọi service và trả DTO
        return orderService.findById(id);
    }
}
~~~

Ví dụ giả định ứng dụng có service và DTO tương ứng. Annotation mô tả contract; chúng không tự bảo đảm response runtime khớp status hoặc schema. Hãy xác nhận tài liệu được sinh và kiểm thử endpoint thật.

Với operation ghi, mô tả request body và response rõ ràng:

~~~java
@Operation(
    operationId = "createOrder",
    summary = "Tạo đơn hàng",
    description = "Tạo đơn mới cho khách hàng hiện tại."
)
@ApiResponse(responseCode = "201", description = "Đơn hàng đã được tạo")
@PostMapping("/api/orders")
ResponseEntity<OrderResponse> createOrder(
    @Valid @RequestBody CreateOrderRequest request
) {
    // ...
}
~~~

Dùng DTO riêng cho request và response khi chúng có quyền ghi/đọc hoặc field khác nhau. Không dùng một entity nội bộ làm schema công khai nếu nó chứa dữ liệu không nên đưa ra ngoài.

## 14. Bổ sung x-tool bằng OpenApiCustomizer

Có thể thêm extension vào OpenAPI model bằng OpenApiCustomizer:

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ToolMetadataConfiguration {

    @Bean
    OpenApiCustomizer toolMetadata() {
        return openApi -> {
            var paths = openApi.getPaths();
            if (paths == null) {
                return;
            }

            var orderPath = paths.get("/api/orders/{id}");
            if (orderPath == null || orderPath.getGet() == null) {
                return;
            }

            var operation = orderPath.getGet();
            operation.addExtension("x-tool-enabled", true);
            operation.addExtension("x-tool-name", "get_order");
            operation.addExtension("x-tool-read-only", true);
            operation.addExtension("x-tool-confirmation-required", false);
            operation.addExtension("x-tool-category", "orders");
        };
    }
}
~~~

Ví dụ trên dùng OpenApiCustomizer để thêm extension dạng scalar trực tiếp vào operation. Nếu dùng nhiều document group, kiểm tra customizer được áp dụng cho document nào. Với metadata cần áp dụng toàn cục cho các group, xem GlobalOpenApiCustomizer hoặc cấu hình customizer riêng cho từng GroupedOpenApi theo version springdoc đang dùng.

Không dựa vào vị trí operation trong file hoặc thứ tự map để gắn metadata. Hãy tìm theo path và method, sau đó xác minh operationId. Nếu path thay đổi, customizer có thể không tìm thấy operation; nên có test phát hiện extension bắt buộc bị thiếu.

Khi có nhiều operation, nên dùng một registry cấu hình có kiểm tra thay vì viết các nhánh path/method rải rác. Registry có thể khai báo operationId, tool name, enabled, side-effect classification và policy, rồi customizer áp dụng vào OpenAPI model.

## 15. Thiết kế tool definition từ OpenAPI operation

Adapter có thể chuyển một operation thành cấu trúc trung gian trước khi xuất ra MCP hoặc function-calling format.

Ví dụ cấu trúc trung gian:

~~~json
{
  "name": "get_order",
  "description": "Lấy thông tin một đơn hàng theo mã.",
  "source": {
    "group": "public",
    "operationId": "getOrderById",
    "method": "GET",
    "path": "/api/orders/{id}"
  },
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1
          }
        },
        "required": ["id"],
        "additionalProperties": false
      }
    },
    "required": ["path"],
    "additionalProperties": false
  },
  "policy": {
    "readOnly": true,
    "confirmationRequired": false,
    "securityScopes": ["orders:read"]
  }
}
~~~

Cấu trúc trên là ví dụ nội bộ, không phải một chuẩn tool protocol. Adapter đích sẽ chuyển nó thành đúng cấu trúc mà MCP server, function-calling API hoặc nền tảng tích hợp yêu cầu.

Giữ source mapping trong registry để runtime biết tool name tương ứng với operation nào. Không nhận method/path từ input do model gửi. Input chỉ chứa giá trị nghiệp vụ; method và path là metadata đã được xác định trước.

## 16. Ánh xạ sang MCP tools

MCP tools thường có tên, mô tả và input schema. Server công bố danh sách tool và xử lý lời gọi dựa trên tên cùng arguments. Một số phiên bản protocol còn hỗ trợ output schema và annotations.

Khi tạo MCP tool từ OpenAPI:
- Dùng operationId hoặc x-tool-name làm nguồn tên.
- Dùng summary/description làm mô tả.
- Chuyển parameter và requestBody thành inputSchema.
- Chuyển schema kết quả nếu outputSchema được hỗ trợ và phù hợp.
- Ánh xạ read-only/destructive/idempotent thành annotations khi có căn cứ.
- Giữ authorization và credential trong MCP server/runtime.
- Trả lỗi theo cấu trúc tool result của MCP.

Annotations như readOnlyHint hoặc destructiveHint là gợi ý cho client. Chúng không ngăn server thực hiện thao tác và không thể thay thế kiểm tra quyền.

Một tool MCP có thể gọi nhiều API operation nội bộ nếu đó là hành động nghiệp vụ được thiết kế rõ ràng. Ngược lại, không bắt buộc một operation OpenAPI phải trở thành một MCP tool. Server nên công bố danh sách nhỏ, ổn định và phù hợp với người dùng.

## 17. Ánh xạ sang function calling

Một số nền tảng model nhận danh sách function/tool definition gồm name, description và JSON Schema parameters. Adapter có thể tạo function definition từ OpenAPI operation:

~~~json
{
  "type": "function",
  "name": "get_order",
  "description": "Lấy thông tin một đơn hàng theo mã.",
  "parameters": {
    "type": "object",
    "properties": {
      "id": {
        "type": "string",
        "description": "Mã đơn hàng"
      }
    },
    "required": ["id"],
    "additionalProperties": false
  }
}
~~~

Đây là ví dụ minh họa một dạng function definition; mỗi API/provider có thể yêu cầu cấu trúc và tập JSON Schema khác nhau. Không gửi nguyên OpenAPI Operation Object vào trường parameters và kỳ vọng model hiểu được.

Tool call từ model chỉ là yêu cầu gọi hàm. Ứng dụng vẫn phải:
1. Parse arguments.
2. Validate theo schema.
3. Kiểm tra tool có được phép dùng trong context hiện tại không.
4. Kiểm tra quyền và confirmation policy.
5. Thực thi adapter.
6. Trả kết quả tool cho model theo protocol đích.

Nếu provider hỗ trợ strict schema mode, adapter cần chuyển đổi schema sang tập keyword được hỗ trợ và bật chế độ strict theo đúng tài liệu provider. Không tự bỏ composition, nullable hoặc constraint mà không ghi nhận giới hạn.

## 18. Ánh xạ response và lỗi

OpenAPI operation có thể có nhiều response code và media type. Tool adapter cần xác định cách biểu diễn kết quả.

Một quy ước đơn giản:

| HTTP response | Tool result |
|---|---|
| 2xx có JSON body | Trả structured data theo schema |
| 204 No Content | Trả kết quả thành công không có body |
| 400/422 | Lỗi input/validation có thể sửa |
| 401 | Thiếu hoặc hết hạn credential |
| 403 | Không đủ quyền |
| 404 | Không tìm thấy tài nguyên |
| 409 | Xung đột trạng thái hoặc idempotency |
| 429 | Rate limit, có thể cần retry theo policy |
| 5xx | Lỗi provider; trả thông báo an toàn và correlation ID |

Không biến mọi HTTP response thành tool success. Adapter cần phân biệt success/error dựa trên status code và contract của operation.

Không đưa stack trace, SQL, internal hostname, token hoặc dữ liệu nhạy cảm vào tool result. Có thể trả mã lỗi ổn định, thông báo có thể hành động, status và correlation ID. Chi tiết kỹ thuật nên nằm trong log server được kiểm soát.

Nếu response có nhiều success schema, ví dụ 200 và 202, hãy mô tả rõ từng trạng thái. 202 có thể chỉ xác nhận job đã được tiếp nhận; tool không nên báo nghiệp vụ hoàn tất nếu API mới chỉ tạo một tác vụ nền.

### 18.1. Chọn output schema từ response thành công

Khi tool protocol có output schema, adapter nên lấy schema từ response thành công được chọn theo policy, thường là response JSON chính của operation. Không lấy schema của response lỗi làm output thành công. Nếu operation có nhiều response thành công với cấu trúc khác nhau, có thể dùng union schema nếu protocol hỗ trợ hoặc trả một envelope có trường status và data để giữ rõ trạng thái.

Ví dụ operation trả JSON cho 200 và không có body cho 204 cần hai nhánh kết quả riêng. Với 204, không tạo một object rỗng rồi khẳng định nó là response body của API. Nếu tool runtime yêu cầu mọi kết quả có cấu trúc, adapter có thể bọc kết quả thành metadata nội bộ như {status: 204, body: null}; đây là định dạng của adapter, không phải body HTTP.

## 19. Những giới hạn schema khi chuyển OpenAPI sang JSON Schema của tool

OpenAPI Schema Object và JSON Schema có liên quan nhưng không phải lúc nào cũng dùng cùng dialect hoặc cùng tập keyword. Tool protocol có thể chỉ hỗ trợ một phần JSON Schema.

Các điểm cần kiểm tra:
- OpenAPI 3.0 nullable khác cách biểu diễn null trong JSON Schema 2020-12.
- OpenAPI 3.1 hỗ trợ nhiều JSON Schema keyword hơn.
- Reference có thể cần resolve hoặc giữ reference theo định dạng đích.
- allOf, oneOf, anyOf và discriminator có thể không được tool runtime hỗ trợ đầy đủ.
- readOnly/writeOnly là annotation có ý nghĩa theo hướng request/response.
- format như date-time, uuid, binary có thể chỉ là metadata đối với một số validator.
- multipart và binary cần cơ chế truyền dữ liệu riêng.
- Recursive schema có thể gây khó cho tool schema strict hoặc UI hiển thị.

Adapter cần biết OpenAPI version và dialect trước khi chuyển. Nên có test fixtures cho các schema phức tạp đang dùng trong API, thay vì giả định mọi schema đều có thể flatten an toàn.

Nếu một operation có schema không thể chuyển chính xác, có ba lựa chọn:
1. Không công bố operation đó thành tool.
2. Viết adapter/schema đơn giản hơn nhưng vẫn giữ validation tương đương.
3. Tạo API facade có contract phù hợp với tool runtime.

Không âm thầm xóa constraint để schema qua được validator. Việc đó làm model có thể gửi dữ liệu mà provider không chấp nhận.

## 20. Bảo vệ tool registry và HTTP execution

Tool registry là một bề mặt tích hợp có thể kích hoạt hành động trong hệ thống. Cần kiểm soát cả lúc đăng ký và lúc thực thi.

Các nguyên tắc:
- Chỉ nạp OpenAPI document từ nguồn đã tin cậy.
- Chỉ cho phép server URL thuộc allowlist.
- Không cho tool input thay đổi host, scheme hoặc port.
- Chỉ cho phép HTTP method đã đăng ký.
- Giới hạn redirect để tránh chuyển request sang host khác.
- Không forward mọi header từ tool input đến provider.
- Không đưa Authorization, Cookie hoặc API key vào input schema.
- Áp dụng timeout, response size limit và rate limit.
- Kiểm tra quyền trên từng invocation.
- Ghi audit event với tool name, principal, operationId và kết quả.
- Không log credential hoặc payload nhạy cảm.
- Có giới hạn retry riêng cho operation không idempotent.

OpenAPI document có thể chứa external reference hoặc URL trong server, callback và link. Adapter không nên tự động truy cập URL bất kỳ chỉ vì nó xuất hiện trong document. Resolve reference và gọi server cần tuân theo allowlist và policy của hệ thống.

## 21. Kiểm thử lớp ánh xạ operation thành tool

Không chỉ kiểm thử endpoint Spring Boot. Cần kiểm thử adapter và registry độc lập.

| Lớp test | Điều cần xác minh |
|---|---|
| Document test | Operation có operationId, summary, schema và security metadata |
| Selection test | Chỉ operation được phép mới xuất hiện trong tool registry |
| Name test | Tool name ổn định, duy nhất và đúng quy tắc |
| Input mapping test | Path/query/header/body được chuyển đúng vị trí |
| Schema test | Required, enum, nullable và constraint không bị mất |
| Auth test | Credential lấy từ trusted context, không từ model input |
| Policy test | Read/write/destructive/confirmation được phân loại đúng |
| Execution test | Method, URL, media type và body đúng |
| Result test | Success/error mapping đúng status và schema |
| Security test | URL ngoài allowlist và operation bị cấm đều bị từ chối |

Một test fixture có thể lưu OpenAPI JSON đã biết và expected tool definition. Khi nâng springdoc hoặc đổi annotation, chạy test để phát hiện tên tool, description, input schema hoặc extension thay đổi ngoài dự kiến.

Ngoài unit test, chạy integration test với Spring Boot thật để xác nhận endpoint docs có nội dung mong đợi và tool adapter đọc được document được sinh từ runtime. Nếu dùng nhiều GroupedOpenApi, test từng group.

## 22. Ví dụ kiểm tra metadata trong OpenAPI output

Sau khi khởi động ứng dụng, tải document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Dùng jq kiểm tra operation và extension:

~~~bash
jq '.paths["/api/orders/{id}"].get |
  {
    operationId,
    summary,
    description,
    toolEnabled: .["x-tool-enabled"],
    toolName: .["x-tool-name"],
    toolReadOnly: .["x-tool-read-only"]
  }' openapi.json
~~~

Kết quả cần phản ánh metadata mà adapter dựa vào. Nếu extension không xuất hiện, kiểm tra customizer đã được nạp vào document đúng group hay chưa và operation path/method có khớp không.

Không chỉ kiểm tra extension. Hãy kiểm tra parameters, requestBody, responses và security:

~~~bash
jq '.paths["/api/orders/{id}"].get |
  {
    parameters,
    responses,
    security
  }' openapi.json
~~~

Nếu document output đúng nhưng tool registry vẫn sai, lỗi nằm ở lớp chuyển đổi hoặc policy chứ không nhất thiết ở springdoc.

## 23. Checklist trước khi công bố operation thành tool

- [ ] Operation có mục tiêu nghiệp vụ rõ ràng.
- [ ] Operation không phải endpoint nội bộ hoặc debug ngoài ý muốn.
- [ ] operationId có mặt, duy nhất và ổn định.
- [ ] Summary là tên hành động dễ hiểu.
- [ ] Description nêu điều kiện, giới hạn và side effect.
- [ ] Parameter có name, location, type và required chính xác.
- [ ] Request body có schema và media type được adapter hỗ trợ.
- [ ] Required, enum, nullable và constraint được giữ.
- [ ] Response success và error được mô tả rõ.
- [ ] Security scheme/scope được ánh xạ vào policy.
- [ ] Credential được lấy từ trusted context, không từ model input.
- [ ] Server URL và HTTP method đến từ registry tin cậy.
- [ ] Read-only, idempotent, destructive và confirmation được phân loại theo semantics thực.
- [ ] Vendor extension có schema/quy ước và được validate.
- [ ] Tool name duy nhất trong registry.
- [ ] Tool result không làm lộ secret hoặc thông tin nội bộ.
- [ ] Adapter xử lý timeout, retry, rate limit và response size.
- [ ] Có test cho selection, schema mapping, execution và authorization.
- [ ] Mỗi document group được kiểm tra riêng.
- [ ] Có quy trình review khi OpenAPI diff làm thay đổi tool registry.

## Tài liệu tham khảo

- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): operationId, summary, description, parameters, requestBody, responses và extensions.
- [Swagger Annotations – Operation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/Operation.html): annotation mô tả operation trong Java.
- [springdoc-openapi](https://springdoc.org/): sinh OpenAPI document và tùy biến bằng customizer.
- [Model Context Protocol – Tools](https://modelcontextprotocol.io/specification/latest/server/tools): cấu trúc tool, input schema, output schema và annotations.
- [JSON Schema](https://json-schema.org/): mô hình schema cho dữ liệu JSON và các ràng buộc.
- [OpenAI – Function calling](https://developers.openai.com/api/docs/guides/function-calling): định nghĩa tool/function và xử lý tool call trong ứng dụng.
