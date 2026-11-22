# MCP trong những nhánh Springdoc có cung cấp tích hợp

Model Context Protocol (MCP) là giao thức chuẩn hóa cách ứng dụng AI khám phá và gọi các khả năng do một máy chủ cung cấp. Với tích hợp MCP của springdoc-openapi, các operation REST đã được mô tả bằng OpenAPI có thể được chuyển thành MCP tools để MCP client hoặc AI agent khám phá và gọi. Nhờ đó, nhóm phát triển có thể tái sử dụng metadata của controller, parameter, request body và response thay vì duy trì một bộ mô tả tool riêng biệt.

Tích hợp này chỉ có trong những nhánh Springdoc cung cấp module MCP. Theo tài liệu hiện hành, MCP được thêm ở springdoc 3.0.3 thuộc nhánh Spring Boot 4; nhánh Spring Boot 3 dùng springdoc 2.x không có các starter MCP tương ứng. Từ 3.1.1, tích hợp chuyển sang opt-in và mặc định tắt. Vì MCP có thể làm AI agent gọi trực tiếp API nghiệp vụ, cần chọn đúng phiên bản, lọc operation được công bố và bảo vệ các endpoint MCP bằng Spring Security trước khi kết nối client bên ngoài.

## 1. MCP là gì và giải quyết vấn đề nào?

Một REST API thường được thiết kế cho ứng dụng hoặc người dùng gọi trực tiếp bằng HTTP. Một AI agent cần thêm một lớp mô tả để biết:

- Có thể thực hiện những hành động nào?
- Mỗi hành động cần tham số nào?
- Tham số nào bắt buộc và có kiểu dữ liệu gì?
- Hành động trả về loại dữ liệu nào?
- Hành động nào chỉ đọc và hành động nào có thể thay đổi dữ liệu?

MCP cung cấp giao thức để client khám phá và gọi các tool do server công bố. Springdoc có sẵn thông tin operation trong OpenAPI, vì vậy có thể chuyển metadata này thành tool definition:

~~~text
Spring @RestController
        |
        v
Springdoc tạo OpenAPI operation
        |
        v
OpenAPI operation -> MCP ToolCallback
        |
        v
MCP Server công bố tools
        |
        v
MCP Client / AI Agent khám phá và gọi tool
        |
        v
Springdoc gọi REST endpoint tương ứng
~~~

Ví dụ, operation GET /orders/{id} có operationId là getOrderById có thể trở thành tool get_order_by_id. Agent đọc mô tả và JSON Schema đầu vào, sau đó gọi tool bằng các tham số phù hợp. Springdoc chuyển lời gọi đó thành HTTP request tới endpoint REST gốc và trả kết quả về MCP client.

## 2. Phân biệt MCP với OpenAPI và Swagger UI

Ba thành phần có liên quan nhưng phục vụ những đối tượng khác nhau:

| Thành phần | Mục đích | Người hoặc hệ thống sử dụng |
|---|---|---|
| OpenAPI | Mô tả HTTP API, path, method, parameter, request/response và security scheme | Developer, API gateway, validator, code generator |
| Swagger UI | Hiển thị OpenAPI thành giao diện tài liệu và thử request | Developer, người tích hợp API |
| MCP | Công bố các khả năng dưới dạng tools để AI client khám phá và gọi theo giao thức chuẩn | MCP client và AI agent |

OpenAPI là nguồn metadata mà tích hợp MCP của Springdoc sử dụng. Swagger UI và MCP có thể cùng tồn tại trong một ứng dụng, nhưng Swagger UI không phải MCP client và endpoint /v3/api-docs không phải MCP endpoint.

MCP specification có nhiều loại capability như tools, resources và prompts. Phần tích hợp Springdoc được mô tả trong bài này chủ yếu chuyển các operation REST thành tools. Nó không tự biến mọi REST endpoint thành MCP resource hoặc prompt. Nếu ứng dụng cần tài nguyên hoặc prompt MCP độc lập, có thể bổ sung khả năng MCP native bằng Spring AI theo nhu cầu.

## 3. Xác định nhánh Springdoc có hỗ trợ MCP

Không phải mọi phiên bản springdoc-openapi đều có MCP:

| Nhánh Springdoc | Nền tảng Spring Boot | MCP integration |
|---|---|---|
| 1.x | Spring Boot 1/2 | Không có module MCP |
| 2.x | Spring Boot 3.x | Không có starter MCP của Springdoc |
| 3.x | Spring Boot 4.x | Có module MCP từ 3.0.3 |

Các mốc quan trọng của nhánh 3.x:

- 3.0.3: bổ sung tích hợp Springdoc OpenAPI MCP.
- 3.1.1: MCP chuyển sang opt-in; nếu chỉ thêm dependency thì không đăng ký MCP bean, endpoint hoặc dashboard. Bản này cũng chứa các sửa lỗi bảo mật liên quan đến MCP.
- 3.2.0: bổ sung đăng ký tool với McpStatelessSyncServer khi dùng Spring AI STATELESS protocol.

Tài liệu Springdoc hiện hành công bố version 3.2.0 cho Spring Boot 4.1.x. Đây là version minh họa trong các dependency bên dưới. Hãy kiểm tra compatibility matrix và release notes của đúng dự án trước khi chọn version; không thêm starter 3.x vào ứng dụng Spring Boot 3 đang dùng nhánh springdoc 2.x.

## 4. Các module MCP của Springdoc

Springdoc chia tích hợp thành các module:

| Module | Trách nhiệm |
|---|---|
| springdoc-openapi-starter-common-mcp | Core engine, cấu hình MCP, tool callback, schema converter, customizer, annotation, dashboard controller và frontend assets |
| springdoc-openapi-starter-webmvc-mcp | Tích hợp Spring MVC/Servlet, resource configurer và xử lý API version cho servlet |
| springdoc-openapi-starter-webflux-mcp | Tích hợp Spring WebFlux, resource configurer và xử lý API version reactive |

Thông thường, ứng dụng chỉ khai báo starter tương ứng với web stack. Module common-mcp được kéo vào như dependency liên quan; không cần tự ghép các module nội bộ nếu không có yêu cầu đặc biệt.

## 5. Chọn dependency theo Spring MVC hoặc WebFlux

Với Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-mcp</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Với Spring WebFlux:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-mcp</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Chọn một starter phù hợp với web stack đang chạy. Không thêm cả MVC và WebFlux chỉ để thử MCP. Nếu dự án đang dùng starter Springdoc có Swagger UI hoặc API-only, hãy kiểm tra dependency tree và cách kết hợp module theo hướng dẫn của version hiện tại để tránh kéo hai cấu hình web không cần thiết.

Dependency chỉ đưa khả năng MCP vào classpath. Từ version 3.1.1, tích hợp không tự bật khi ứng dụng khởi động.

## 6. Bật MCP một cách tường minh

Trong application.yml:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
~~~

Hoặc trong application.properties:

~~~properties
springdoc.ai.mcp.enabled=true
~~~

Khi property được bật, Springdoc tạo MCP integration và đăng ký các operation REST đủ điều kiện thành tools. Nếu chỉ thêm starter nhưng không bật property, MCP surface vẫn tắt ở các phiên bản từ 3.1.1 trở đi.

Để tắt tích hợp:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: false
~~~

Có thể dùng profile để bật MCP ở môi trường thử nghiệm hoặc môi trường tích hợp agent:

~~~yaml
# application-agent.yml
springdoc:
  ai:
    mcp:
      enabled: true
      dashboard-enabled: true
~~~

Chỉ kích hoạt profile đó khi môi trường đã có security policy phù hợp. Không dùng việc ẩn link dashboard làm cơ chế bảo vệ MCP.

## 7. Cấu hình endpoint, base URL và thời gian khởi tạo

Các thuộc tính chính nằm dưới prefix springdoc.ai.mcp:

| Property | Mặc định | Ý nghĩa |
|---|---|---|
| springdoc.ai.mcp.enabled | false | Bật/tắt MCP integration |
| springdoc.ai.mcp.base-url | http://localhost:8080; tự suy theo server.port nếu không đặt | Base URL dùng để gọi REST operation khi thực thi tool |
| springdoc.ai.mcp.init-timeout-seconds | 30 | Thời gian chờ OpenAPI spec sẵn sàng lúc khởi động |
| springdoc.ai.mcp.paths-to-exclude | Không có | Các Ant pattern loại khỏi tool generation |
| springdoc.ai.mcp.mcp-endpoint | /mcp | Đường dẫn MCP endpoint |
| springdoc.ai.mcp.dashboard-enabled | false | Bật dashboard dành cho developer |
| springdoc.ai.mcp.dashboard-path | /mcp-ui | Đường dẫn dashboard |

Ví dụ cấu hình:

~~~yaml
server:
  port: 8080

springdoc:
  ai:
    mcp:
      enabled: true
      base-url: http://localhost:8080
      init-timeout-seconds: 30
      mcp-endpoint: /mcp
      paths-to-exclude:
        - /internal/**
        - /admin/**
      dashboard-enabled: true
      dashboard-path: /mcp-ui
      guardrails:
        require-approval-for-mutating-tools: true
        safe-methods: GET,HEAD,OPTIONS
      audit:
        redact: true
~~~

base-url phải trỏ tới chính ứng dụng có các REST endpoint mà tool sẽ gọi. Nếu ứng dụng chạy dưới context path hoặc phía sau reverse proxy, hãy kiểm tra URL đầy đủ và cách ứng dụng định tuyến request. Một base URL sai có thể khiến tool được liệt kê nhưng khi gọi lại nhận connection error, 404 hoặc redirect.

init-timeout-seconds giới hạn thời gian chờ tài liệu OpenAPI trong giai đoạn khởi tạo. Nếu ứng dụng có nhiều group hoặc OpenAPI generation nặng, hãy kiểm tra log startup và thời gian tạo spec trước khi tăng timeout.

## 8. Springdoc cần OpenAPI sẵn sàng lúc khởi động

Quy trình MCP dựa trên OpenAPI operation để tạo tool definition. Vì vậy, khi MCP được bật, Springdoc tự động ép springdoc.pre-loading-enabled thành true qua environment post-processor để tài liệu được nạp sớm và sẵn sàng cho việc đăng ký tool.

Luồng khởi tạo:

1. Spring Boot tạo ApplicationContext và các bean.
2. Springdoc quét các @RestController endpoint.
3. Springdoc tạo OpenAPI document.
4. OpenAPI operation được chuyển thành tool callback.
5. Customizer chain áp dụng tên, mô tả, schema và quy tắc loại trừ.
6. MCP server đăng ký tools sau khi các singleton cần thiết đã được tạo.

Việc đăng ký sau khi singleton được khởi tạo giúp tránh một số deadlock khi khởi động. Nếu ứng dụng không tạo được OpenAPI document, MCP tools cũng không thể được đăng ký đầy đủ. Khi startup timeout, kiểm tra lỗi OpenAPI trước khi điều chỉnh timeout MCP.

## 9. Từ REST operation thành MCP tool

Springdoc quét các operation được mô tả từ @RestController. Mỗi OpenAPI operation được chuyển thành ToolCallback với các thành phần:

- Tên tool: lấy từ operationId và chuyển sang snake_case.
- Mô tả: lấy từ summary/description, sau đó bổ sung thông tin kiểu trả về.
- Input schema: JSON Schema được tạo từ path parameter, query parameter, header parameter và request body.
- Nhóm: lấy từ @Tag đầu tiên của controller.
- Hành động thực tế: tool callback gọi REST endpoint tương ứng qua base URL.

Ví dụ:

~~~java
@RestController
@RequestMapping("/orders")
@Tag(name = "Orders", description = "Tra cứu và quản lý đơn hàng")
public class OrderController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Tra cứu đơn hàng theo mã"
    )
    public OrderResponse getOrderById(@PathVariable String id) {
        return orderService.findById(id);
    }
}
~~~

Tool name được tạo:

~~~text
get_order_by_id
~~~

Nên khai báo operationId ổn định và có ý nghĩa nghiệp vụ. Tránh để tên method Java vô tình trở thành tên tool khó hiểu hoặc thay đổi theo một lần refactor nội bộ.

## 10. Chất lượng OpenAPI quyết định chất lượng tool

MCP tool được sinh từ OpenAPI nên metadata kém sẽ tạo tool khó sử dụng. Mỗi operation nên có:

- operationId duy nhất và ổn định.
- summary mô tả hành động bằng động từ rõ ràng.
- description nêu điều kiện, phạm vi và tác động nghiệp vụ.
- Parameter name và description dễ hiểu.
- Required marker chính xác.
- Request body schema đầy đủ, có giới hạn dữ liệu.
- Response schema thể hiện đúng kết quả.
- Tag phù hợp với nhóm nghiệp vụ.

Ví dụ operation:

~~~java
@PostMapping
@Operation(
    operationId = "createOrder",
    summary = "Tạo đơn hàng",
    description = "Tạo đơn hàng mới cho khách hàng đã xác thực."
)
public OrderResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Nếu description chỉ ghi "Create order" mà không nói điều kiện hay tác động, agent có thể chọn tool sai ngữ cảnh. Mô tả cần trả lời tool làm gì, khi nào dùng và dữ liệu nào cần cung cấp.

## 11. Cách Springdoc chuyển parameter và request body

OpenApiSchemaConverter chuyển thông tin operation thành JSON Schema cho input của tool:

| Thành phần REST | Cách biểu diễn trong tool input |
|---|---|
| Path parameter | Property có kiểu và mô tả tương ứng |
| Query parameter | Property có kiểu, mô tả và required marker |
| Header parameter | Property tương ứng với header |
| Request body | Property tên body chứa schema của request |

Ví dụ REST endpoint:

~~~java
@PostMapping("/orders/{id}/notes")
@Operation(operationId = "addOrderNote")
public OrderResponse addNote(
        @PathVariable String id,
        @RequestParam(defaultValue = "false") boolean notifyCustomer,
        @RequestBody AddOrderNoteRequest request) {
    return orderService.addNote(id, notifyCustomer, request);
}
~~~

Input của tool có thể có cấu trúc tương tự:

~~~json
{
  "id": "ORD-1001",
  "notifyCustomer": false,
  "body": {
    "content": "Khách hàng yêu cầu giao sau 17 giờ"
  }
}
~~~

Đối với nhiều media type, bộ chuyển đổi hỗ trợ request body và ưu tiên application/json khi phù hợp. Hãy kiểm tra schema tool sinh ra nếu operation nhận multipart/form-data, file upload hoặc nhiều content type; không giả định mọi dạng body đều được agent truyền giống JSON object.

Nếu path template có {id} nhưng không khai báo parameter tương ứng trong OpenAPI, converter có thể tự bổ sung property chuỗi bắt buộc cho path variable. Đây là cơ chế dự phòng; API nên khai báo parameter tường minh để description và kiểu dữ liệu chính xác.

## 12. Các schema nâng cao được chuyển đổi

OpenApiSchemaConverter hỗ trợ nhiều cấu trúc JSON Schema thường gặp:

- $ref và giải quyết tham chiếu schema.
- allOf, anyOf và oneOf.
- Object lồng nhau và property lồng nhau.
- Schema đệ quy có phát hiện circular reference.
- pattern.
- minimum, maximum, exclusiveMinimum, exclusiveMaximum.
- minLength, maxLength.
- minItems, maxItems.
- multipleOf, enum và default.

Ví dụ request DTO:

~~~java
public class CreateOrderRequest {

    @NotBlank
    private String customerId;

    @NotEmpty
    private List<OrderLineRequest> items;

    @Size(max = 500)
    private String note;
}
~~~

Những ràng buộc được biểu diễn trong OpenAPI có thể trở thành JSON Schema input để agent biết giới hạn trước khi gọi tool. Tuy nhiên, tool schema không thay thế Bean Validation hoặc validation nghiệp vụ trên server. Server vẫn phải kiểm tra request như khi nhận một HTTP request bình thường.

## 13. Mô tả kiểu trả về cho AI agent

Tool description được bổ sung thông tin về kiểu trả về. Ví dụ operation trả về OrderResponse có thể được diễn giải thêm:

~~~text
Returns OrderResponse (id, customerId, status, total)
~~~

Thông tin này giúp agent hiểu kết quả dự kiến và chọn cách xử lý output. Dù vậy, mô tả kiểu trả về không thay thế response schema, error handling hoặc ví dụ response.

Nếu endpoint trả dữ liệu lớn, nên dùng DTO gọn cho tool-facing API. Dashboard có cảnh báo payload response lớn để nhắc nhóm xem xét giảm dữ liệu đưa vào context window của agent.

## 14. Nhóm tool bằng @Tag

Tool được nhóm theo @Tag đầu tiên của controller. Ví dụ:

~~~java
@RestController
@RequestMapping("/customers")
@Tag(name = "Customers")
public class CustomerController {
    // customer operations
}

@RestController
@RequestMapping("/products")
@Tag(name = "Products")
public class ProductController {
    // product operations
}
~~~

Dashboard có thể hiển thị hai nhóm Customers và Products. Tool không có tag sẽ nằm trong nhóm Other. Native MCP tools được khai báo bằng @McpTool hoặc @Tool được nhóm riêng dưới mcp-tools trong dashboard.

Tag nên phản ánh miền nghiệp vụ hoặc nhóm tác vụ. Tránh gắn mọi operation vào một tag chung như API vì agent và developer sẽ khó tìm đúng tool.

## 15. Loại endpoint khỏi MCP tool list

Không phải mọi REST endpoint đều phù hợp cho AI agent. Ví dụ:

- Endpoint nội bộ chỉ dành cho health hoặc debug.
- Endpoint quản trị tài khoản và quyền.
- Endpoint thao tác dữ liệu nhạy cảm.
- Endpoint chỉ phục vụ callback giữa các hệ thống.
- Endpoint có payload hoặc tác động không phù hợp cho agent.

Có thể loại path theo cấu hình:

~~~yaml
springdoc:
  ai:
    mcp:
      paths-to-exclude:
        - /internal/**
        - /admin/**
        - /actuator/**
~~~

Đây là Ant patterns áp dụng cho việc tạo MCP tools. Đồng thời, nên giới hạn phạm vi API được tài liệu hóa bằng springdoc.packages-to-scan, springdoc.paths-to-match hoặc GroupedOpenApi nếu phù hợp.

Loại operation khỏi tool list không đồng nghĩa endpoint REST đã bị bảo vệ. Client vẫn có thể gọi URL REST trực tiếp nếu network và security policy cho phép. Authorization phải được kiểm tra ở server.

## 16. Tùy chỉnh tên, mô tả và input schema bằng McpToolCustomizer

McpToolCustomizer là extension point để chỉnh định nghĩa tool sau khi Springdoc tạo từ OpenAPI. Có thể:

- Đổi tên tool.
- Viết lại description.
- Điều chỉnh input schema.
- Loại tool hoàn toàn khỏi danh sách.
- Ghi đè phân loại safe/mutating cho một operation cụ thể.

Ví dụ:

~~~java
@Bean
McpToolCustomizer customizeOrderTools() {
    return (context, path, method, operation) -> {
        if ("getOrderById".equals(context.getName())) {
            context.setName("find_order");
            context.setDescription(
                "Tìm một đơn hàng theo mã định danh duy nhất."
            );
        }

        if (path.startsWith("/internal")) {
            context.setExclude(true);
        }

        return context;
    };
}
~~~

McpToolDefinitionContext cung cấp các thao tác chính:

| Getter/setter | Ý nghĩa |
|---|---|
| getName / setName | Đọc hoặc đổi tên tool |
| getDescription / setDescription | Đọc hoặc đổi mô tả |
| getInputSchema / setInputSchema | Đọc hoặc thay JSON Schema đầu vào |
| isExclude / setExclude | Loại tool khỏi danh sách |
| getSafeEndpoint / setSafeEndpoint | Ghi đè phân loại safe/mutating |

Có thể trả null để loại tool, nhưng tài liệu hiện hành ưu tiên gọi context.setExclude(true) để thể hiện ý định rõ ràng. Nếu có nhiều customizer, chúng được áp dụng theo thứ tự đăng ký/order; hãy tránh để các bean cùng đổi một trường theo cách xung đột.

## 17. Viết mô tả dành riêng cho AI bằng @McpToolDescription

OpenAPI summary/description thường được viết cho developer. Có thể cần một mô tả trực tiếp hơn cho AI agent. Annotation @McpToolDescription đặt trên method controller cho phép ghi đè mô tả và tùy chọn tên tool:

~~~java
@GetMapping("/orders/{id}")
@Operation(
    summary = "Tra cứu đơn hàng",
    operationId = "getOrderById"
)
@McpToolDescription(
    value = "Tìm một đơn hàng theo mã duy nhất. Dùng khi người dùng hỏi trạng thái hoặc chi tiết một đơn hàng cụ thể.",
    name = "find_order"
)
public OrderResponse getOrderById(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Thuộc tính:

| Thuộc tính | Bắt buộc | Ý nghĩa |
|---|---|---|
| value | Có | Mô tả tối ưu cho AI agent |
| name | Không | Tên tool tùy chỉnh; nếu bỏ trống dùng operationId |

Customizer mặc định đọc annotation này với độ ưu tiên cao. Các McpToolCustomizer do ứng dụng đăng ký có thể tiếp tục chỉnh sửa giá trị sau đó.

Mô tả cho AI nên ngắn gọn nhưng có ngữ cảnh: trường hợp nên dùng, dữ liệu cần có và tác động chính. Không đưa secret, token, thông tin nội bộ hoặc hướng dẫn có thể khiến agent vượt qua chính sách nghiệp vụ vào description.

## 18. Phân loại safe và mutating tool

Springdoc tự phân loại tool theo HTTP method:

| Nhóm | HTTP method mặc định |
|---|---|
| Safe/read-only | GET, HEAD, OPTIONS |
| Mutating | POST, PUT, DELETE, PATCH và các method còn lại |

Danh sách safe có thể cấu hình bằng:

~~~yaml
springdoc:
  ai:
    mcp:
      guardrails:
        safe-methods: GET,HEAD,OPTIONS
~~~

Phân loại theo method là quy tắc mặc định, không phải phân tích ngữ nghĩa nghiệp vụ. Ví dụ POST /reports/generate có thể chỉ tạo một báo cáo xem trước, trong khi GET /cache/invalidate lại thay đổi trạng thái. Với các trường hợp đặc biệt, dùng McpToolCustomizer và context.setSafeEndpoint(Boolean) để ghi đè phân loại.

Không đánh dấu một endpoint là safe chỉ vì nó dùng GET. Nếu GET có side effect, phải phân loại lại thành mutating và sửa thiết kế HTTP nếu có thể.

## 19. Human-in-the-Loop cho thao tác thay đổi dữ liệu

Mặc định:

~~~yaml
springdoc:
  ai:
    mcp:
      guardrails:
        require-approval-for-mutating-tools: true
~~~

Khi agent gọi tool bị phân loại mutating, Springdoc không thực hiện HTTP request ngay. Thay vào đó, tool trả một phản hồi có cấu trúc, ví dụ:

~~~json
{
  "requires_human_approval": true,
  "tool_name": "create_order",
  "http_method": "POST",
  "path": "/orders",
  "arguments": {
    "customerId": "CUS-100"
  },
  "message": "This mutating operation requires human approval before execution."
}
~~~

Agent cần chuyển yêu cầu xác nhận tới người dùng hoặc quy trình phê duyệt của ứng dụng. Khi được chấp thuận theo flow hỗ trợ, operation mới được thực thi.

Có thể tắt yêu cầu approval:

~~~yaml
springdoc:
  ai:
    mcp:
      guardrails:
        require-approval-for-mutating-tools: false
~~~

Chỉ nên cân nhắc trong môi trường tin cậy, đã có authorization độc lập và có kiểm soát tác động. Không tắt approval chỉ để agent thao tác thuận tiện.

## 20. Approval không thay thế authentication và authorization

Human-in-the-Loop là bước xác nhận, không phải ranh giới bảo mật. Người có thể truy cập MCP endpoint và API quản trị có thể tự hoàn tất một yêu cầu approval. Vì vậy:

- Authentication phải xác định danh tính client hoặc người dùng.
- Authorization phải quyết định danh tính đó được gọi tool nào.
- Approval bổ sung bước xác nhận cho hành động có tác động.
- Audit ghi lại hoạt động để điều tra và giám sát.

Không dùng approval để thay thế role, scope hoặc quyền nghiệp vụ. Server REST vẫn phải kiểm tra quyền trên từng request, vì một agent có thể gọi API ngoài MCP hoặc một tool có thể bị gọi từ client khác.

## 21. Bật MCP Developer Dashboard

Dashboard mặc định tắt. Để bật:

~~~yaml
springdoc:
  ai:
    mcp:
      dashboard-enabled: true
      dashboard-path: /mcp-ui
~~~

Dashboard hỗ trợ:

- Khám phá tools đã đăng ký, phân nhóm theo OpenAPI tag.
- Xem tên, mô tả, HTTP method, path và input schema.
- Thử gọi tool với JSON input ngay trong browser.
- Xem response body, status code và thời gian thực thi.
- Hiển thị cảnh báo với tool mutating đang chờ approval.
- Chuyển tiếp header xác thực như Authorization hoặc API key tới REST call bên dưới.
- Cấu hình credential Bearer, Basic Auth hoặc API key cho thử nghiệm.
- Xem audit event, thời gian và thông tin payload.
- Sao chép cURL invocation để tái hiện request.

Dashboard hữu ích khi phát triển tool và kiểm tra schema, nhưng cũng là giao diện có khả năng thực thi operation. Hãy bảo vệ nó như một trang quản trị, đặc biệt khi ứng dụng kết nối dữ liệu thật.

## 22. Dashboard REST API và audit logging

Dashboard REST API được phục vụ dưới /api/mcp-admin:

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | /api/mcp-admin/tools | Liệt kê tools, bao gồm group |
| POST | /api/mcp-admin/tools/execute | Thực thi tool theo tên và JSON arguments |

Mỗi lần thực thi tool tạo structured JSON audit event ở logger:

~~~text
org.springdoc.ai.mcp.audit
~~~

Audit event được ghi ở mức INFO. Khi dashboard hoạt động, event cũng được lưu trong bộ nhớ để hiển thị ở tab audit. Dữ liệu in-memory không nên được xem như kho audit bền vững; nếu cần lưu lâu dài, hãy chuyển log sang hệ thống log tập trung có quyền truy cập và retention policy phù hợp.

Từ 3.1.1, giá trị ở các key có hình dạng bí mật như authorization, password, token, api-key, secret và cookie được che trước khi log hoặc lưu cho dashboard:

~~~yaml
springdoc:
  ai:
    mcp:
      audit:
        redact: true
~~~

Giữ redact bật trong hầu hết môi trường. Không tắt che dữ liệu nếu log sink hoặc dashboard có thể bị người không được phép truy cập. Redaction không thay thế việc giảm dữ liệu nhạy cảm trong tool input/output.

## 23. Bảo vệ các MCP endpoint bằng Spring Security

Các endpoint tích hợp chính:

| Endpoint | Vai trò |
|---|---|
| /mcp | MCP protocol endpoint |
| /mcp-ui/** | Dashboard UI và tài nguyên tĩnh |
| /api/mcp-admin/** | API quản trị và thực thi tool từ dashboard |

Springdoc không tự áp dụng authentication hoặc authorization cho các endpoint này. Ví dụ cấu hình một security chain:

~~~java
@Bean
SecurityFilterChain mcpSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher(
            "/mcp",
            "/mcp-ui/**",
            "/api/mcp-admin/**"
        )
        .authorizeHttpRequests(requests -> requests
            .anyRequest().hasRole("MCP_ADMIN")
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Ví dụ dùng role MCP_ADMIN để minh họa. Trong production, nên chọn OAuth2 Resource Server, session hoặc cơ chế xác thực phù hợp với hệ thống. Nếu có nhiều SecurityFilterChain, kiểm tra @Order và securityMatcher để request MCP được xử lý bởi chain đúng.

MCP endpoint qua HTTP nhận các request theo transport đang cấu hình; không kiểm tra transport bằng một GET đơn lẻ nếu giao thức yêu cầu request khác. Nếu ứng dụng bật CSRF protection, cấu hình CSRF cho endpoint machine-to-machine một cách có chủ đích và chỉ trong phạm vi cần thiết; không tắt CSRF toàn ứng dụng chỉ để MCP client kết nối được.

Ngoài Spring Security, hãy đặt reverse proxy hoặc gateway có TLS, rate limit, network policy và kiểm soát Origin phù hợp. Không mặc định localhost là ranh giới an toàn: một trang web chạy trong browser có thể tìm cách gửi request tới dịch vụ localhost hoặc mạng riêng nếu server không có lớp bảo vệ phù hợp.

## 24. Giới hạn tool surface và quyền theo từng API

Một operation xuất hiện trong OpenAPI có thể trở thành tool. Vì vậy, việc lựa chọn controller và path có ý nghĩa như một quyết định công bố capability.

Nên áp dụng nhiều lớp:

1. Dùng packages-to-scan và paths-to-match để giới hạn tài liệu OpenAPI.
2. Dùng springdoc.ai.mcp.paths-to-exclude để loại endpoint khỏi MCP tool generation.
3. Dùng McpToolCustomizer để loại tool theo operation, method hoặc path.
4. Dùng Spring Security để phân quyền ở MCP endpoint và REST endpoint.
5. Kiểm tra danh sách tools sau khi ứng dụng khởi động.

Không chỉ loại endpoint admin khỏi dashboard rồi cho rằng nó không thể được gọi. Nếu REST route vẫn mở và tool khác có thể gọi nó, server vẫn phải kiểm tra quyền ở tầng nghiệp vụ.

## 25. Kết hợp Springdoc MCP với Spring AI native MCP tools

Springdoc MCP tạo tools từ OpenAPI operation. Spring AI còn có cách khai báo capability MCP trực tiếp, ví dụ dùng @McpTool cho method hoặc bean ToolCallbackProvider.

Hai nguồn có thể cùng xuất hiện trong một ứng dụng:

- OpenAPI-backed tools: tự sinh từ @RestController operation.
- Native MCP tools: do ứng dụng định nghĩa trực tiếp bằng API hoặc annotation Spring AI.

Dashboard hiện có thể khám phá cả ToolCallbackProvider và các MCP tool specification native. Tuy nhiên, cần quản lý tên tool và trách nhiệm rõ ràng để tránh trùng tên hoặc hai tool cùng thực hiện một tác vụ với quyền khác nhau.

Nếu cần MCP resources hoặc prompts, hãy định nghĩa chúng theo khả năng native tương ứng của Spring AI. Đừng thêm REST endpoint chỉ với kỳ vọng Springdoc tự biến nó thành resource hoặc prompt.

## 26. Dùng Spring AI STATELESS protocol

Từ springdoc 3.2.0, tool có thể được đăng ký với McpStatelessSyncServer khi ứng dụng dùng Spring AI STATELESS protocol:

~~~yaml
spring:
  ai:
    mcp:
      server:
        protocol: STATELESS
~~~

Đây là lựa chọn giao thức server, không phải property bật MCP của Springdoc. Vẫn cần:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
~~~

Hãy kiểm tra version Spring AI được quản lý bởi Spring Boot/Springdoc và transport mà MCP client hỗ trợ. Không bật STATELESS chỉ vì muốn bỏ session; cần kiểm tra hành vi discovery, context, notification và tool invocation của client/server cụ thể.

## 27. Kiểm tra tích hợp trên môi trường local

Sau khi thêm dependency và cấu hình:

1. Khởi động ứng dụng bằng đúng profile.
2. Xác nhận OpenAPI document được tạo.
3. Xác nhận MCP integration được bật.
4. Kiểm tra endpoint /mcp theo giao thức và client MCP được sử dụng.
5. Kiểm tra tool list có tên, mô tả và input schema mong đợi.
6. Gọi một tool GET chỉ đọc.
7. Gọi một tool mutating và xác nhận approval được yêu cầu theo cấu hình.
8. Thử một path bị loại và xác nhận nó không xuất hiện.
9. Kiểm tra dashboard nếu đã bật.
10. Kiểm tra security khi chưa xác thực và với tài khoản có quyền.

Dashboard có thể giúp xem nhanh tool và chạy thử, nhưng nên kiểm tra thêm bằng MCP client thật. Một tool hiển thị trong dashboard chưa chứng minh client production có thể khởi tạo phiên, khám phá tool và gọi đúng transport.

## 28. Kiểm thử contract và hành vi của tool

Nên có test bao phủ:

| Trường hợp | Kỳ vọng |
|---|---|
| OpenAPI operation có operationId | Tên tool ổn định, dễ hiểu |
| Path/query/header parameter | Input schema chứa đúng property và required marker |
| Request body | Input schema thể hiện body và nested schema |
| Operation có $ref | Schema converter resolve được tham chiếu |
| Controller có @Tag | Tool được nhóm đúng |
| Operation bị paths-to-exclude | Không được công bố thành tool |
| Customizer đổi tên | Client nhìn thấy tên mới |
| Customizer loại tool | Tool không xuất hiện trong list |
| GET read-only | Được phân loại safe theo mặc định |
| POST/PUT/PATCH/DELETE | Yêu cầu approval khi guardrail bật |
| Caller không có quyền | MCP request bị từ chối |
| REST endpoint không có quyền | Tool invocation vẫn bị server từ chối |
| Audit event | Có event và secret được redacted |

Nên test cả tool discovery lẫn tool execution. Discovery kiểm tra metadata; execution kiểm tra base URL, HTTP method, path, header forwarding, request body, authorization và response mapping.

## 29. Tích hợp MCP vào CI

Một pipeline kiểm tra MCP có thể gồm:

~~~text
Build Spring Boot application
          |
          v
Start with MCP-enabled profile
          |
          v
Wait for OpenAPI preloading and MCP registration
          |
          v
Connect MCP test client
          |
          v
List and inspect tools
          |
          v
Verify schemas, tags and exclusions
          |
          v
Invoke read-only test tool
          |
          v
Verify mutation approval and authorization
          |
          v
Check audit redaction
          |
          v
Stop application and publish test results
~~~

Không nên để CI gọi tool mutating trên dữ liệu dùng chung. Dùng test database hoặc service giả lập và xác minh approval trước khi thực thi. Nếu cần test thực thi mutation, chỉ chạy trong môi trường cô lập có dữ liệu có thể khôi phục.

Khi nâng Springdoc hoặc Spring AI, chạy lại test tool list vì tên, schema, transport hoặc server registration có thể thay đổi theo version.

## 30. Lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Không tìm thấy artifact MCP | Dùng nhánh Springdoc không hỗ trợ | Kiểm tra Spring Boot 4 và Springdoc 3.x |
| Có dependency nhưng /mcp không xuất hiện | MCP chưa được bật hoặc đang dùng version 3.1.1+ | Đặt springdoc.ai.mcp.enabled=true |
| Ứng dụng chờ lâu khi startup | OpenAPI preloading hoặc endpoint chưa sẵn sàng | Xem lỗi tạo OpenAPI và init-timeout-seconds |
| Tool list rỗng | Không có operation được scan hoặc tất cả đều bị lọc | Kiểm tra controller, OpenAPI paths và exclusions |
| Tool name không rõ | operationId thiếu hoặc không ổn định | Đặt operationId rõ ràng |
| Tool input thiếu parameter | OpenAPI operation chưa mô tả parameter | Bổ sung @PathVariable, @RequestParam hoặc @Parameter metadata |
| Body không đúng shape | Client gửi sai property body hoặc content type | Kiểm tra input schema được converter sinh ra |
| Tool gọi nhầm host/port | base-url hoặc context path sai | Cấu hình base URL theo runtime |
| Tool xuất hiện nhưng trả 401/403 | REST endpoint yêu cầu quyền | Forward credential và kiểm tra quyền tại API |
| Dashboard không mở | dashboard-enabled=false hoặc security chặn | Bật dashboard có chủ đích và cấp quyền |
| Tool mutating bị chặn | Approval đang bật | Hoàn tất flow xác nhận hoặc giữ guardrail theo policy |
| Tool nhạy cảm vẫn xuất hiện | Chưa lọc OpenAPI hoặc MCP path | Thêm paths-to-exclude hoặc McpToolCustomizer |
| Audit có dữ liệu nhạy cảm | Redaction bị tắt hoặc key không được nhận diện | Giữ redact=true và giảm payload nhạy cảm |
| WebFlux có hành vi khác MVC | Khác biệt reactive context hoặc version | Dùng starter WebFlux đúng version đã vá và kiểm thử concurrency |
| STATELESS không hoạt động | Spring AI server protocol chưa được cấu hình đúng | Kiểm tra version và spring.ai.mcp.server.protocol |

Khi chẩn đoán, tách ba lớp: OpenAPI có mô tả đúng operation không, MCP có đăng ký tool từ operation đó không, và tool callback có gọi được REST endpoint với quyền phù hợp không. Điều này giúp xác định lỗi nằm ở tài liệu, quá trình đăng ký MCP hay ở request thực tế.

## 31. Quy trình triển khai MCP an toàn

Thực hiện theo thứ tự:

1. Xác nhận ứng dụng dùng Spring Boot 4 và nhánh springdoc 3.x có module MCP.
2. Chọn starter WebMVC hoặc WebFlux tương ứng.
3. Khai báo operationId, summary, description, parameter, request body và response rõ ràng.
4. Bật springdoc.ai.mcp.enabled trong profile cần thiết.
5. Cấu hình base-url, timeout và endpoint path.
6. Loại endpoint nội bộ hoặc nhạy cảm khỏi tool generation.
7. Gắn @Tag theo miền nghiệp vụ và viết mô tả phù hợp cho agent.
8. Thêm McpToolCustomizer hoặc @McpToolDescription khi cần.
9. Giữ approval cho tool mutating và kiểm tra phân loại safe/mutating.
10. Bảo vệ /mcp, /mcp-ui/** và /api/mcp-admin/** bằng Spring Security.
11. Bảo vệ REST endpoint gốc bằng authorization theo từng tài nguyên.
12. Giữ audit redaction và kiểm soát nơi lưu log.
13. Kiểm thử discovery, schema, execution, approval và từ chối truy cập.
14. Theo dõi release notes của Springdoc/Spring AI và nâng lên bản vá mới nhất phù hợp.

Không công bố MCP endpoint ra Internet trước khi xác định rõ ai được khám phá tool, ai được gọi từng tool và ai có quyền thực hiện thao tác thay đổi dữ liệu.

## 32. Ghi nhớ

- MCP chuẩn hóa cách AI client khám phá và gọi tools.
- Springdoc MCP chuyển OpenAPI operation của @RestController thành MCP tools.
- Tích hợp bắt đầu ở springdoc 3.0.3, nhánh Spring Boot 4; springdoc 2.x cho Boot 3 không có starter MCP.
- Từ 3.1.1, MCP opt-in và mặc định tắt; cần đặt springdoc.ai.mcp.enabled=true.
- Dùng springdoc-openapi-starter-webmvc-mcp hoặc springdoc-openapi-starter-webflux-mcp đúng web stack.
- OpenAPI operationId tạo tên tool; summary/description tạo mô tả; parameter và request body tạo JSON Schema input.
- @Tag nhóm tool; @McpToolDescription viết mô tả riêng cho AI.
- McpToolCustomizer có thể đổi tên, mô tả, schema, loại tool và ghi đè safe/mutating.
- GET, HEAD, OPTIONS mặc định là safe; các method còn lại mặc định là mutating.
- Approval cho mutation là bước xác nhận, không phải authorization.
- Dashboard mặc định tắt và có thể khám phá, thử gọi, xem audit.
- /mcp, /mcp-ui và /api/mcp-admin/** không tự có authentication/authorization.
- Bảo vệ cả MCP endpoint lẫn REST endpoint gốc bằng Spring Security.
- Giữ audit redaction và hạn chế payload nhạy cảm.
- Từ 3.2.0 có thể đăng ký stateless MCP server khi cấu hình Spring AI STATELESS.
- Kiểm thử tool discovery, input schema, authorization, approval và execution trong CI.

MCP trong các nhánh Springdoc có tích hợp giúp tái sử dụng OpenAPI để đưa REST API tới AI agent dưới dạng tools. Hãy chọn đúng nhánh Spring Boot 4/Springdoc 3.x, bật tích hợp tường minh, thiết kế operation và mô tả rõ ràng, lọc tool theo nghiệp vụ, rồi bảo vệ MCP endpoint và REST endpoint bằng quyền thực tế. Guardrail approval hỗ trợ xác nhận thao tác thay đổi dữ liệu, nhưng không thay thế authentication, authorization hoặc audit.

## Tài liệu tham khảo

- Springdoc OpenAPI – MCP Support: https://springdoc.org/#mcp
- Springdoc OpenAPI – Configuration Properties: https://springdoc.org/properties.html
- Springdoc OpenAPI – Modules: https://springdoc.org/modules.html
- Springdoc OpenAPI – Releases: https://github.com/springdoc/springdoc-openapi/releases
- Spring AI – MCP Server Boot Starter: https://docs.spring.io/spring-ai/reference/api/mcp/mcp-server-boot-starter-docs.html
- Spring AI – MCP Overview: https://docs.spring.io/spring-ai/reference/api/mcp/mcp-overview.html
