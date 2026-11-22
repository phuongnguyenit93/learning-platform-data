# Xác thực, phân quyền và hành vi gọi API thật qua MCP

Khi một MCP client gọi tool do Springdoc tạo từ OpenAPI, ứng dụng thực hiện lời gọi tới operation REST tương ứng. Đây là một HTTP request có đích đến, method, path, parameter, header và body; request đi qua web stack và các lớp bảo vệ của API đích. Vì vậy, bảo mật MCP phải kiểm soát được cả request đi vào MCP server lẫn request được tạo ra khi tool chạy.

Có ba câu hỏi cần trả lời riêng:

1. Ai được kết nối tới MCP endpoint và khám phá tool?
2. Ai được phép gọi một tool cụ thể và thực hiện nghiệp vụ tương ứng?
3. Khi tool gọi REST API qua HTTP, API đích nhận danh tính và credential nào?

Một Bearer token hợp lệ ở request MCP không tự chứng minh rằng request REST tiếp theo cũng mang token đó. Tương tự, việc yêu cầu người dùng xác nhận thao tác ghi không thay thế authentication hoặc authorization. Bài này đi từ luồng request thật tới cách cấu hình Spring Security, chọn mô hình credential, kiểm tra quyền theo tài nguyên và xác minh side effect trong integration test.

## 1. Ba lớp bảo mật trong một lần gọi tool

Một lần gọi tool qua Springdoc có thể đi qua ba lớp:

~~~text
MCP Client / AI Agent
        |
        | 1. MCP request + credential của MCP client
        v
Spring Security: bảo vệ MCP endpoint
        |
        v
Springdoc MCP ToolCallback
        |
        | 2. HTTP request tới base-url
        v
Spring Security: bảo vệ REST API đích
        |
        v
Controller -> Service -> Repository / Database
        |
        v
HTTP response -> Tool result -> MCP Client
~~~

Lớp thứ nhất xác thực và phân quyền client đối với MCP server. Lớp thứ hai xác thực và phân quyền request REST được tạo khi thực thi tool. Lớp thứ ba là kiểm tra quyền nghiệp vụ đối với đối tượng cụ thể, chẳng hạn người dùng chỉ được xem đơn hàng thuộc tenant hoặc tài khoản của mình.

Không nên gộp ba lớp thành một kiểm tra duy nhất. Một client có quyền gọi MCP server vẫn có thể không có quyền đọc một đơn hàng cụ thể. Một tool được liệt kê cũng không đồng nghĩa người gọi được phép thực thi nó.

## 2. Springdoc MCP thực hiện lời gọi HTTP thật

Springdoc quét các operation đã mô tả trong OpenAPI và tạo ToolCallback. Khi MCP client gọi tool, callback chuyển input thành request cho operation tương ứng:

- operationId xác định tên tool.
- Path parameter được đưa vào URL.
- Query parameter được mã hóa vào query string.
- Header parameter được đưa vào HTTP headers theo metadata operation.
- Request body được chuyển thành body của HTTP request.
- Method và path được lấy từ OpenAPI operation.
- Response từ API đích được chuyển thành kết quả của tool.

Ví dụ API:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    @Operation(operationId = "getOrderById")
    public OrderResponse getOrder(@PathVariable UUID id) {
        return orderService.getOrder(id);
    }
}
~~~

Tool có thể được công bố với tên get_order_by_id. Khi agent gọi tool với id, Springdoc tạo HTTP GET tới đường dẫn tương ứng trên base URL đã cấu hình.

Request đó đi qua HTTP routing, servlet filter hoặc WebFilter, Spring Security, controller advice, validation và các thành phần ứng dụng liên quan. Nó có thể tạo log, metric, trace, truy vấn database hoặc side effect giống một request REST được gửi từ ứng dụng khác.

Vì vậy, không xem tool callback như một lời gọi Java trực tiếp tới method controller. Đặc biệt, không giả định SecurityContext của request MCP tự động được mang sang một HTTP request mới tới REST endpoint.

## 3. Phân biệt MCP endpoint và REST endpoint

Các endpoint MCP mặc định của Springdoc gồm:

| Endpoint | Chức năng |
|---|---|
| /mcp | Giao tiếp MCP qua HTTP |
| /mcp-ui | MCP Developer Dashboard nếu được bật |
| /api/mcp-admin/** | API quản trị dashboard, gồm liệt kê và thực thi tool |

Các endpoint REST gốc có thể là /api/orders/**, /api/customers/** hoặc các path nghiệp vụ khác. Chúng là một bề mặt HTTP riêng và phải có chính sách bảo vệ riêng.

Springdoc không tự áp dụng authentication hoặc authorization cho các endpoint MCP. Nếu không đặt security layer, client có thể truy cập endpoint theo network reachability và cấu hình web hiện tại. Spring AI cũng mô tả HTTP MCP transports là authentication-agnostic: transport thiết lập giao thức, còn việc bảo vệ endpoint thuộc về ứng dụng.

Không chỉ bảo vệ /mcp rồi để API đích mở công khai. Ngược lại, chỉ bảo vệ REST API mà để /mcp công khai cũng có thể làm lộ danh sách capability, dashboard hoặc các tool khác không có kiểm tra quyền đầy đủ.

## 4. OpenAPI security metadata không thực thi bảo mật

OpenAPI có thể mô tả Bearer authentication để Swagger UI, code generator và client hiểu cách gọi API:

~~~java
@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiSecurityConfiguration {
}
~~~

Áp dụng scheme cho operation:

~~~java
@GetMapping("/{id}")
@Operation(
    operationId = "getOrderById",
    security = @SecurityRequirement(name = "bearerAuth")
)
public OrderResponse getOrder(@PathVariable UUID id) {
    return orderService.getOrder(id);
}
~~~

Security scheme mô tả rằng API yêu cầu Bearer token. Nó không tạo token, không kiểm tra chữ ký JWT và không chặn request trái phép. Việc thực thi phải do Spring Security hoặc security layer khác đảm nhiệm.

Không khai báo Authorization như một header parameter thông thường trong OpenAPI. OpenAPI có Security Scheme dành riêng cho cơ chế xác thực HTTP; dùng @SecurityScheme và @SecurityRequirement để mô tả.

## 5. Xác thực request đi vào MCP server

Với HTTP transport, MCP server là một web endpoint. Có thể bảo vệ nó bằng Spring Security giống các endpoint khác.

Ví dụ ứng dụng sử dụng OAuth2 Resource Server với JWT:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Ví dụ SecurityFilterChain:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/mcp", "/mcp/**")
                    .hasAuthority("SCOPE_mcp.invoke")
                .requestMatchers("/mcp-ui/**", "/api/mcp-admin/**")
                    .hasRole("MCP_ADMIN")
                .requestMatchers("/api/**")
                    .authenticated()
                .anyRequest()
                    .denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là ví dụ phân quyền minh họa. Scope, role, URL và thứ tự matcher phải khớp identity provider cùng cấu trúc ứng dụng. Nếu ứng dụng có nhiều SecurityFilterChain, kiểm tra @Order và securityMatcher để chắc chắn request MCP đi vào chain dự kiến.

Lưu ý CSRF: HTTP MCP có request POST. Nếu /mcp chỉ dùng Bearer token trong Authorization header và không xác thực bằng cookie trình duyệt, có thể loại riêng endpoint này khỏi CSRF:

~~~java
.csrf(csrf -> csrf.ignoringRequestMatchers("/mcp", "/mcp/**"))
~~~

Đặt cấu hình này trong cùng SecurityFilterChain trước build(). Không tắt CSRF toàn ứng dụng theo ví dụ rút gọn. Nếu dashboard hoặc API quản trị dùng session cookie, giữ CSRF cho các request trình duyệt đó và cung cấp token CSRF theo cấu hình Spring Security.

Với JWT, cần kiểm tra issuer, chữ ký, thời hạn, audience và scope phù hợp với MCP resource. Việc token được ký hợp lệ chưa đủ để chứng minh nó được phát hành cho đúng API.

## 6. Phân biệt 401 và 403

Hai status thường gặp:

| Status | Ý nghĩa | Ví dụ |
|---|---|---|
| 401 Unauthorized | Request chưa có credential hợp lệ | Thiếu Bearer token, token hết hạn hoặc chữ ký sai |
| 403 Forbidden | Danh tính đã được xác thực nhưng không có quyền | Token thiếu scope mcp.invoke hoặc orders.read |

Nếu MCP client nhận 401 ở endpoint /mcp, hãy kiểm tra cách client gửi credential tới MCP server. Nếu MCP request qua được nhưng tool gọi REST API nhận 401, kiểm tra credential của request downstream. Nếu API đích trả 403, kiểm tra scope, role, tenant và quyền trên đối tượng.

Không chuyển mọi lỗi thành thông báo thành công có nội dung rỗng. Kết quả tool phải giữ đủ thông tin để client biết request thất bại, đồng thời không làm lộ stack trace, secret hoặc chi tiết nội bộ.

## 7. Credential của MCP client và credential của REST API là hai việc khác nhau

Giả sử agent gửi:

~~~http
POST /mcp
Authorization: Bearer <mcp-access-token>
Content-Type: application/json
~~~

Spring Security xác thực token ở request này. Sau đó, Springdoc tạo một HTTP request khác tới API đích theo springdoc.ai.mcp.base-url.

Không được mặc định rằng header Authorization của MCP request sẽ tự động trở thành header Authorization của request REST mới. Tài liệu Springdoc công bố rõ việc chuyển tiếp header xác thực từ MCP Developer Dashboard tới API bên dưới trong luồng thực thi dashboard. Đây là mô tả dành cho dashboard; không nên suy rộng thành cam kết rằng mọi MCP client hoặc transport đều tự động chuyển credential của caller sang REST backend.

Hãy kiểm thử luồng thực tế của phiên bản đang dùng. Nếu API đích yêu cầu token mà callback không gửi credential, request REST sẽ bị từ chối dù MCP request ban đầu đã được xác thực.

## 8. Kiểm tra base-url và đường đi của request downstream

Property springdoc.ai.mcp.base-url xác định base URL dùng khi tool callback thực thi HTTP call. Mặc định là http://localhost:8080; nếu không đặt, Springdoc suy ra từ server.port.

Ví dụ:

~~~yaml
server:
  port: 8080

springdoc:
  ai:
    mcp:
      enabled: true
      base-url: http://localhost:8080
~~~

Nếu ứng dụng chạy dưới context path /store, URL thực tế có thể cần là:

~~~yaml
springdoc:
  ai:
    mcp:
      base-url: http://localhost:8080/store
~~~

Nếu API đích nằm ở một service khác, base-url phải trỏ tới host và context path của service đó. Trong container, localhost là chính container hiện tại; nếu MCP server và API backend nằm ở hai container khác nhau, dùng hostname service trong network của môi trường chạy.

Base URL là đích đến của request. Nó không tự cấu hình OAuth client, không cấp token và không thay thế chính sách authorization của backend.

## 9. Ba mô hình credential downstream

Khi tool callback cần gọi một API được bảo vệ, cần chọn mô hình danh tính rõ ràng:

| Mô hình | API đích nhìn thấy ai? | Phù hợp khi |
|---|---|---|
| Service identity | Ứng dụng MCP hoặc một service account | Tác vụ máy-với-máy có quyền cố định |
| User delegation | Người dùng cuối đang tương tác với agent | Quyền API phải theo từng người dùng |
| Native tool/service call | Principal hiện tại trong luồng ứng dụng, nếu security context được duy trì đúng | Muốn gọi service layer trực tiếp thay vì HTTP loopback |

Không chọn service identity chỉ để làm cho 401 biến mất nếu nghiệp vụ cần quyền theo từng người dùng. Cũng không chuyển tiếp token người dùng một cách mù quáng tới backend khác có audience hoặc scope khác.

## 10. Service identity với client credentials

Với tác vụ máy-với-máy, có thể cấp một service account riêng cho MCP integration. Token được lấy từ authorization server bằng client credentials và chỉ chứa scope tối thiểu, ví dụ orders.read hoặc orders.create.

Luồng:

~~~text
MCP client
   |
   | token dành cho MCP server
   v
MCP server xác thực caller
   |
   | tool callback cần gọi backend
   v
OAuth client lấy service token
   |
   | Bearer token của service account
   v
REST API kiểm tra scope và quyền service
~~~

Service identity phù hợp khi API đích chỉ cần biết hệ thống nào đang gọi. Nó không tự giữ được danh tính người dùng cuối. Nếu service account có quyền đọc mọi đơn hàng, việc MCP endpoint chỉ cho một người dùng phổ thông truy cập không đủ để bảo đảm người đó chỉ đọc được đơn hàng của mình.

Springdoc MCP properties công bố base-url, endpoint, timeout, filter, guardrail và audit; không có property chung để khai báo client secret hoặc downstream bearer token. Vì vậy, việc lấy và gắn service token cần được thực hiện bởi security integration, gateway hoặc custom execution layer có kiểm soát. Không tự thêm một property không được tài liệu hỗ trợ vào application.yml rồi giả định Springdoc sẽ dùng nó.

## 11. User delegation và token exchange

Nếu backend phải đánh giá quyền theo người dùng cuối, cần giữ ngữ cảnh người dùng tới API đích bằng cơ chế được thiết kế rõ ràng:

- Authorization server hỗ trợ token exchange hoặc on-behalf-of flow.
- Token downstream được cấp cho đúng audience của API đích.
- Scope chỉ bao gồm hành động mà người dùng được phép thực hiện.
- API đích kiểm tra tenant, owner và quyền đối tượng như mọi request khác.

Không gửi token dành cho MCP resource sang một API khác nếu audience không khớp. Không chuyển tiếp cookie phiên hoặc toàn bộ header đến host ngoài phạm vi tin cậy.

Nếu phiên bản hoặc execution adapter không cung cấp cơ chế chuyển tiếp danh tính theo request, cân nhắc viết native MCP tool dùng Spring AI và gọi service layer với security context được kiểm soát, hoặc xây dựng một adapter riêng có khả năng thực hiện token exchange. Hãy kiểm tra cách security context được truyền qua thread/reactive boundary trước khi dựa vào principal hiện tại.

## 12. Không biến tham số tool thành nguồn danh tính đáng tin cậy

Không thiết kế tool như sau:

~~~json
{
  "userId": "user-100",
  "tenantId": "tenant-a",
  "orderId": "order-900"
}
~~~

và sau đó tin rằng userId hoặc tenantId do agent gửi là danh tính thật của caller. Tool arguments là dữ liệu đầu vào do client cung cấp; chúng không chứng minh người gọi có quyền đại diện cho người dùng hoặc tenant đó.

Danh tính nên lấy từ Authentication đã được xác thực, claim đã được kiểm tra hoặc context do backend đáng tin cậy thiết lập. Nếu API cần tenant ID, hãy xác minh tenant đó thuộc danh tính hoặc service principal đang gọi.

Các giá trị do agent cung cấp như customerId, accountId hoặc orderId vẫn cần kiểm tra quyền sở hữu. Không dùng việc tool schema mô tả một ID hợp lệ để thay thế authorization.

## 13. Phân quyền ở request level và method level

Request-level authorization phù hợp để giới hạn bề mặt endpoint:

- Chỉ MCP client có scope mcp.invoke mới được vào /mcp.
- Chỉ MCP administrator được vào dashboard và API quản trị.
- Chỉ caller đã xác thực mới được gọi nhóm REST API.

Method-level authorization phù hợp với quyền nghiệp vụ:

- Có scope orders.read mới được đọc đơn hàng.
- Chỉ chủ sở hữu hoặc nhân viên có role phù hợp mới xem chi tiết.
- Chỉ người có quyền orders.cancel mới hủy đơn.

Spring Security cần bật method security tường minh:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Ví dụ ở service:

~~~java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderResponse findById(UUID orderId) {
        return orderRepository.findResponseById(orderId);
    }
}
~~~

Spring Boot Security starter không tự bật method-level authorization. Nếu dùng @PreAuthorize, hãy xác nhận @EnableMethodSecurity đã có và method được gọi qua Spring-managed proxy.

## 14. Kiểm tra quyền trên từng tài nguyên

Scope orders.read chỉ trả lời caller có thể đọc loại tài nguyên đơn hàng. Nó chưa trả lời caller có thể đọc đơn hàng cụ thể nào.

Có thể dùng authorization bean:

~~~java
@Service
public class OrderService {

    @PreAuthorize("@orderAuthorization.canRead(#orderId, authentication)")
    public OrderResponse getOrder(UUID orderId) {
        return repository.findResponseById(orderId)
            .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Bean orderAuthorization cần kiểm tra quan hệ giữa principal và đơn hàng: owner, tenant, vai trò hỗ trợ hoặc chính sách chia sẻ. Cùng một kiểm tra phải áp dụng cho request REST trực tiếp và request được tạo bởi MCP tool.

Không chỉ kiểm tra quyền trên controller rồi bỏ qua service. Service layer là nơi thích hợp để bảo vệ nghiệp vụ được gọi từ nhiều entry point như REST, MCP native tool, message consumer hoặc scheduled job.

## 15. Không công bố principal thành input parameter

Các tham số như Principal, Authentication, HttpServletRequest và @AuthenticationPrincipal là dữ liệu context do framework cung cấp. Chúng không nên trở thành property mà agent tự điền trong tool input.

Springdoc thường bỏ qua các injectable parameter này khi tạo tài liệu. Nếu một parameter bảo mật xuất hiện trong OpenAPI, kiểm tra lại controller signature và annotation.

Không thêm một parameter userId chỉ để thay thế @AuthenticationPrincipal. Nếu nghiệp vụ cần biết người dùng hiện tại, lấy từ security context đã xác thực hoặc truyền một context tin cậy tới service layer.

## 16. Bảo vệ dashboard và API quản trị riêng

MCP Developer Dashboard có thể khám phá tool, xem schema và thực thi tool bằng JSON input. Dashboard REST API thường có:

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | /api/mcp-admin/tools | Liệt kê tools |
| POST | /api/mcp-admin/tools/execute | Thực thi tool theo tên và arguments |

Dashboard là bề mặt quản trị vì người dùng có thể gọi API thật. Hãy giới hạn nó cho role riêng, chỉ bật khi cần và cân nhắc không công bố trong production nếu không có nhu cầu vận hành.

Springdoc ghi nhận dashboard có thể chuyển tiếp header xác thực như Authorization hoặc API key từ dashboard tới API đích. Hãy dùng credential test có quyền tối thiểu và tránh lưu token vào browser storage lâu hơn cần thiết.

Không bảo vệ dashboard bằng cách chỉ ẩn link trong trang. Phải kiểm tra authorization ở server cho cả /mcp-ui/** và /api/mcp-admin/**.

## 17. Human-in-the-Loop không phải authorization

Springdoc phân loại tool theo HTTP method:

| Phân loại mặc định | Method |
|---|---|
| Safe/read-only | GET, HEAD, OPTIONS |
| Mutating | POST, PUT, PATCH, DELETE và method khác |

Khi require-approval-for-mutating-tools bật, một tool mutating trả về kết quả approval-required thay vì thực hiện HTTP request ngay.

Ví dụ:

~~~json
{
  "requires_human_approval": true,
  "tool_name": "cancel_order",
  "http_method": "POST",
  "path": "/api/orders/ORD-1001/cancel",
  "arguments": {
    "reason": "Customer request"
  },
  "message": "This mutating operation requires human approval before execution."
}
~~~

Agent cần trình bày yêu cầu để người dùng xem xét. Nhưng HITL không xác thực caller và không phân quyền. Tài liệu Springdoc cảnh báo người có thể truy cập MCP endpoint cũng có thể hoàn tất luồng approval, kể cả qua API quản trị bằng cách gửi approved=true.

Do đó, approval chỉ là bước xác nhận tác động. Spring Security và quyền nghiệp vụ vẫn phải kiểm tra caller có quyền hủy đơn hàng hay không.

## 18. Phân loại safe theo HTTP method không đủ

Một endpoint GET có thể gây side effect nếu được thiết kế sai, ví dụ GET /cache/invalidate. Một endpoint POST có thể chỉ tạo báo cáo xem trước nhưng mặc định bị xếp mutating.

Có thể thay đổi safe-methods ở mức toàn cục hoặc dùng McpToolCustomizer để ghi đè một operation:

~~~java
@Bean
McpToolCustomizer classifyOperations() {
    return (context, path, method, operation) -> {
        if (method == PathItem.HttpMethod.GET
                && "/api/cache/invalidate".equals(path)) {
            context.setSafeEndpoint(false);
        }
        return context;
    };
}
~~~

Chỉ đánh dấu POST là safe khi chắc chắn operation không thay đổi trạng thái nghiệp vụ. Việc phân loại là guardrail cho agent, không thay đổi ngữ nghĩa HTTP và không ngăn caller gửi request REST trực tiếp.

## 19. Tool input không thay thế validation của REST API

Springdoc chuyển parameter và request body từ OpenAPI thành JSON Schema input cho tool. Schema giúp MCP client biết kiểu dữ liệu, required marker và ràng buộc trước khi gọi.

Nhưng agent có thể gửi dữ liệu sai, client có thể không tuân thủ schema và người dùng có thể gọi REST endpoint trực tiếp. API đích vẫn phải thực hiện:

- Jackson deserialization.
- Bean Validation với @Valid.
- Kiểm tra nghiệp vụ.
- Kiểm tra quyền tài nguyên.
- Kiểm tra trạng thái hiện tại trước khi ghi.

Không dựa vào LLM để kiểm tra số tiền, tenant, trạng thái đơn hàng hoặc quyền người dùng. Validation và authorization phải nằm ở server.

## 20. Hành vi của HTTP request khi tool được gọi

Khi tool được thực thi, các thành phần của OpenAPI operation quyết định request:

| OpenAPI operation | HTTP request thực tế |
|---|---|
| Path parameter | Thay vào path template |
| Query parameter | Mã hóa vào query string |
| Header parameter | Đưa vào header tương ứng |
| Request body | Serialize thành body theo content type |
| HTTP method | GET, POST, PUT, PATCH, DELETE... |
| Server/base URL | Xác định host và context path |

Ví dụ tool input:

~~~json
{
  "id": "ORD-1001",
  "notifyCustomer": true,
  "body": {
    "reason": "Customer requested cancellation"
  }
}
~~~

Có thể tạo request tương ứng:

~~~http
POST /api/orders/ORD-1001/cancel?notifyCustomer=true
Content-Type: application/json
Authorization: Bearer <downstream-token>

{
  "reason": "Customer requested cancellation"
}
~~~

Header Authorization trong ví dụ chỉ xuất hiện nếu execution path đã được cấu hình để gửi credential downstream. Không giả định nó tự có chỉ vì MCP client gửi Bearer token ở request /mcp.

## 21. Response và lỗi từ API đích

Tool callback phải xử lý kết quả HTTP từ API đích. Các trường hợp thường gặp:

- 2xx: operation hoàn thành theo response contract.
- 400 hoặc 422: input không hợp lệ hoặc vi phạm quy tắc nghiệp vụ.
- 401: request downstream thiếu hoặc có credential không hợp lệ.
- 403: principal downstream không có quyền.
- 404: tài nguyên không tồn tại hoặc không được phép hiển thị theo chính sách che giấu tài nguyên.
- 409: trạng thái tài nguyên xung đột.
- 429: rate limit.
- 5xx: API đích gặp lỗi.
- Timeout/connection error: không xác định chắc chắn backend đã xử lý hay chưa.

Không biến 401 downstream thành lỗi đăng nhập MCP nếu hai lớp dùng credential khác nhau. Log cần xác định rõ lỗi xảy ra ở MCP transport hay HTTP call tới API đích.

Không trả stack trace, SQL, token hoặc dữ liệu nhạy cảm trong tool result. Dùng error response ổn định với mã lỗi, thông điệp an toàn và correlation ID để điều tra.

## 22. Timeout, retry và idempotency

Tool callback gọi API qua network nên có thể gặp timeout hoặc mất kết nối. Một tình huống quan trọng:

1. Agent gọi create order.
2. Backend ghi đơn hàng thành công.
3. Response bị mất trên network.
4. MCP client thấy timeout và thử lại.
5. Backend có thể tạo đơn hàng thứ hai.

Không có bảo đảm exactly-once chỉ vì request được gọi qua MCP. Với thao tác ghi, cân nhắc:

- Idempotency key theo yêu cầu nghiệp vụ.
- Unique constraint hoặc deduplication ở backend.
- Trạng thái operation có thể truy vấn lại.
- Timeout hữu hạn và retry policy có kiểm soát.
- Không tự retry POST nếu chưa biết operation có idempotent hay không.

Nếu API đích hỗ trợ Idempotency-Key, hãy mô tả và truyền nó theo một thiết kế rõ ràng. Không để agent tự tạo key tùy tiện rồi kỳ vọng backend luôn chống trùng.

## 23. Tenant isolation và dữ liệu đa khách hàng

Trong hệ thống multi-tenant, quyền truy cập không chỉ phụ thuộc role. Cần xác định tenant từ token claim hoặc context tin cậy.

Ví dụ:

- Token có claim tenant_id.
- Service lấy tenant hiện tại từ principal đã xác thực.
- Repository query luôn giới hạn theo tenant.
- Object-level authorization kiểm tra resource thuộc tenant đó.

Không cho agent truyền tenantId bất kỳ rồi dùng trực tiếp trong query. Nếu tool cần tenant selector, server phải xác minh người dùng được phép truy cập tenant đó.

Nếu downstream call dùng service account chung, backend sẽ chỉ thấy service principal. Khi đó, cần một cơ chế delegation đáng tin cậy để truyền user/tenant context đã được xác minh; không tin một header X-Tenant-Id do caller tự đặt nếu chưa có kiểm tra chữ ký hoặc nguồn tin cậy.

## 24. Header forwarding và ranh giới tin cậy

Tài liệu Springdoc mô tả dashboard có thể chuyển tiếp Authorization và API key tới API call bên dưới. Với các MCP client khác, hãy xác minh rõ phiên bản và transport có cơ chế forwarding nào; không suy ra chỉ từ việc request MCP đã có header.

Nếu cần chuyển tiếp header:

- Chỉ allowlist header thực sự cần thiết.
- Không chuyển tiếp Cookie, Host, Content-Length hoặc header hop-by-hop.
- Không chuyển token tới host khác nếu audience không phù hợp.
- Không ghi credential thô vào log.
- Kiểm tra header không bị client giả mạo.
- Ưu tiên token exchange thay vì chuyển tiếp nguyên token khi có nhiều resource server.

Đừng đưa Authorization thành tool argument hoặc OpenAPI query parameter. Credential phải đi qua cơ chế authentication, không phải JSON input do agent điều khiển.

## 25. Bảo vệ Origin và network boundary

HTTP MCP endpoint có thể được gọi từ browser hoặc mạng nội bộ. Spring AI lưu ý HTTP transports không tự xác thực Origin trong cấu hình mặc định; ứng dụng hoặc reverse proxy cần kiểm tra Origin để phòng DNS rebinding, đặc biệt với server chỉ bind localhost.

Các biện pháp nên xem xét:

- TLS ở điểm kết nối MCP.
- Xác thực client và authorization.
- Origin allowlist cho browser-accessible endpoint.
- Giới hạn network ingress và egress.
- Rate limit theo principal hoặc client.
- Giới hạn request body và thời gian xử lý.
- Không cho tool input điều khiển URL tùy ý của backend.
- Không để base-url bị thay đổi từ dữ liệu do agent gửi.

Không xem localhost là biên bảo mật. Một trang web độc hại có thể cố gửi request từ browser tới dịch vụ chạy trên localhost hoặc mạng riêng nếu transport không có lớp bảo vệ phù hợp.

## 26. Audit và che dữ liệu nhạy cảm

Springdoc ghi structured JSON audit event ở logger:

~~~text
org.springdoc.ai.mcp.audit
~~~

Khi dashboard bật, một số event cũng được giữ trong bộ nhớ để hiển thị. Đây không phải kho audit bền vững; nếu cần retention dài hạn, gửi log tới hệ thống tập trung có kiểm soát truy cập.

Từ Springdoc 3.1.1, audit redaction mặc định che giá trị nằm trong các key có hình dạng bí mật như authorization, password, token, api-key, secret và cookie. Tài liệu hiện hành mô tả việc che trong tool arguments, query string của request URL, request body và response body.

Cấu hình:

~~~yaml
springdoc:
  ai:
    mcp:
      audit:
        redact: true
~~~

Giữ redaction bật. Nó không thay thế việc giảm dữ liệu nhạy cảm trong payload; một trường chứa thông tin cá nhân nhưng tên không giống key bí mật có thể không được nhận diện. Không đưa password, access token hoặc secret vào description, tool arguments hay response nếu không cần.

## 27. Kiểm thử riêng từng ranh giới bảo mật

Một bộ integration test nên phân biệt lỗi ở MCP endpoint với lỗi ở REST API đích:

| Kịch bản | Kỳ vọng |
|---|---|
| Không gửi token tới /mcp | 401 |
| Token hết hạn hoặc chữ ký sai | 401 |
| Token hợp lệ nhưng thiếu mcp.invoke | 403 |
| MCP caller hợp lệ, downstream không có credential | REST API từ chối; test chứng minh hai lớp tách biệt |
| Downstream service token thiếu orders.read | REST API trả 403 |
| Token có scope nhưng resource thuộc tenant khác | Từ chối theo object/tenant policy |
| Caller có đủ quyền | Tool nhận response đúng |
| Tool mutating cần approval | API đích chưa nhận request |
| Tool mutating đã được duyệt | API đích nhận đúng một request theo test |
| Dashboard không có role admin | 403 |
| Audit chứa token trong payload | Giá trị bí mật bị che |

Không chỉ mock ToolCallback rồi kết luận bảo mật hoạt động. Cần khởi chạy ứng dụng hoặc test server để request thật đi qua security filter và API mapping.

## 28. Integration test cho hành vi gọi API thật

Một test end-to-end có thể dùng Spring Boot test server với port cố định trong môi trường test hoặc lấy port thực tế rồi cấu hình base-url phù hợp. API đích có thể là chính ứng dụng hoặc một test service riêng.

Các bước:

1. Khởi động ứng dụng với MCP enabled.
2. Chờ OpenAPI preloading và MCP server sẵn sàng.
3. Kết nối MCP test client bằng credential test.
4. Gọi tools/list và xác nhận tool cần kiểm tra có mặt.
5. Gọi tools/call với input hợp lệ.
6. Xác minh API đích nhận method, path, query, body và credential mong đợi.
7. Xác minh response được trả về MCP client.
8. Gọi lại với token thiếu scope và xác nhận API từ chối.
9. Kiểm tra database hoặc event log để xác nhận side effect đúng số lần.

Nếu dùng base-url localhost với server.port=0, không giả định callback tự biết port ngẫu nhiên. Hãy truyền port thực tế vào cấu hình test hoặc dùng một port test được cấp rõ ràng.

## 29. Kiểm tra authorization propagation

Đây là bài test quan trọng nhất khi API đích cần danh tính người dùng:

1. Gửi MCP request bằng user A.
2. Gọi tool đọc tài nguyên của user A.
3. Xác nhận backend nhận principal hoặc delegation context tương ứng user A.
4. Gọi tài nguyên thuộc user B.
5. Xác nhận backend từ chối dù tool input có chứa ID hợp lệ.
6. Gửi request bằng user B và xác nhận quyền khác nhau được áp dụng.

Nếu cả user A và user B đều được backend nhìn thấy dưới một service account, kiểm tra chính sách delegation và tenant context. Không tuyên bố authorization theo user hoạt động nếu backend chỉ thấy danh tính service.

Nếu không thể truyền danh tính an toàn qua HTTP call, hãy thay đổi thiết kế: dùng native MCP tool gọi service layer trong cùng security context đã được xác minh, hoặc triển khai token exchange/adapter chuyên biệt. Đừng khắc phục bằng cách tin userId từ arguments.

## 30. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| MCP client nhận 401 | Token thiếu, hết hạn hoặc issuer sai | Kiểm tra resource server và Authorization header |
| MCP client nhận 403 | Thiếu scope/role để vào MCP | Cấp quyền mcp.invoke phù hợp |
| Tool hiện ra nhưng gọi bị 401 | Downstream HTTP request thiếu credential | Kiểm tra credential riêng cho API đích |
| Dashboard gọi được nhưng MCP client không gọi được | Dashboard có header forwarding riêng | Kiểm thử luồng MCP client và thiết kế propagation tường minh |
| Tool nhận 403 ở API đích | Scope, role, tenant hoặc object permission không đủ | Kiểm tra principal mà backend thực sự nhận |
| Request vào sai service | base-url, context path hoặc DNS sai | Kiểm tra URL và network từ process MCP |
| Tool trả 404 | Path parameter hoặc base URL sai; resource có thể bị ẩn | Kiểm tra request đã gửi và policy resource |
| Tạo dữ liệu trùng sau timeout | Retry mutation không idempotent | Dùng idempotency key và deduplication |
| Approval bật nhưng request vẫn chạy | Nhầm approval với authorization hoặc dùng luồng admin | Bảo vệ /mcp và /api/mcp-admin/** |
| Người dùng đọc dữ liệu tenant khác | Tin tenantId do tool input gửi | Lấy tenant từ identity đã xác thực và kiểm tra ownership |
| Method security không có hiệu lực | Thiếu @EnableMethodSecurity hoặc gọi không qua proxy | Kiểm tra cấu hình và đường gọi service |
| Token bị gửi nhầm backend | Forward credential không xét audience | Dùng token exchange hoặc service identity phù hợp |
| Log lộ secret | Redaction tắt hoặc payload có key không được nhận diện | Bật redact và giảm dữ liệu nhạy cảm |
| MCP localhost bị gọi từ browser ngoài ý muốn | Thiếu Origin validation hoặc network boundary | Áp dụng Origin allowlist và security layer |

Khi điều tra, ghi nhận riêng HTTP status của request MCP và request REST downstream. Hai request có thể có hai principal, hai token và hai correlation ID khác nhau.

## 31. Quy trình triển khai bảo mật

Thực hiện theo thứ tự:

1. Xác định MCP client, transport, resource server và API backend.
2. Xác định caller cần danh tính người dùng hay service identity.
3. Bảo vệ /mcp bằng Spring Security và scope riêng.
4. Bảo vệ dashboard cùng API quản trị bằng role riêng.
5. Bảo vệ REST endpoint và service method bằng quyền nghiệp vụ.
6. Kiểm tra audience, issuer, expiry và scope của token.
7. Cấu hình base-url đúng host, port và context path.
8. Thiết kế credential downstream bằng service account, token exchange hoặc native tool/service call.
9. Không tin userId, tenantId hoặc role do tool arguments gửi.
10. Giữ approval cho mutation và xem nó là guardrail bổ sung.
11. Bật audit redaction và chuyển log tới hệ thống được kiểm soát.
12. Thêm Origin validation, TLS, rate limit và network policy.
13. Chạy integration test cho cả MCP request và REST request thật.
14. Xác minh side effect, retry, idempotency và tenant isolation.

Trước khi mở endpoint cho client bên ngoài, phải trả lời được API đích nhìn thấy principal nào khi tool chạy và chính sách nào giới hạn principal đó.

## 32. Ghi nhớ

- Springdoc tạo MCP tools từ OpenAPI operation và thực thi chúng bằng HTTP call tới API đích.
- MCP endpoint và REST endpoint là hai request boundary riêng.
- OpenAPI Security Scheme chỉ mô tả cơ chế bảo mật; Spring Security mới thực thi authentication và authorization.
- Credential dùng để vào /mcp không mặc nhiên là credential dùng cho request REST downstream.
- Springdoc công bố header forwarding cho dashboard; không suy rộng thành forwarding tự động cho mọi MCP client.
- base-url xác định đích HTTP call, không tự cấp token.
- Chọn service identity, user delegation hoặc native service call theo yêu cầu nghiệp vụ.
- Không dùng userId hoặc tenantId từ tool arguments làm danh tính đáng tin cậy.
- Dùng request-level security cho endpoint và method/object-level security cho dữ liệu cụ thể.
- Bật @EnableMethodSecurity khi dùng @PreAuthorize.
- Approval cho mutation không phải authorization.
- Tool input schema không thay thế Jackson, Bean Validation hoặc kiểm tra nghiệp vụ.
- Xem timeout và retry như tình huống có thể lặp side effect; dùng idempotency cho thao tác ghi.
- Bật audit redaction và không ghi credential thô.
- Bảo vệ Origin, network boundary và MCP endpoint kể cả khi chỉ nghe trên localhost.
- Integration test phải xác minh cả request MCP lẫn HTTP request thật tới API đích.

Một MCP tool có thể làm thay đổi dữ liệu thật vì nó gọi operation REST thật. Bảo mật đúng cần xác thực client tại MCP endpoint, xác định credential mà request downstream sử dụng và kiểm tra quyền nghiệp vụ tại API đích. Hãy chứng minh ba lớp này bằng integration test với principal, scope, tenant và side effect thực tế trước khi công bố tool cho agent.

## Tài liệu tham khảo

- Springdoc OpenAPI – MCP Support: https://springdoc.org/#mcp
- Springdoc OpenAPI – MCP Configuration Properties: https://springdoc.org/properties.html
- Spring AI – Securing the MCP Server: https://docs.spring.io/spring-ai/reference/api/mcp/mcp-server-boot-starter-docs.html
- Spring AI – MCP Security: https://docs.spring.io/spring-ai/reference/api/mcp/mcp-security.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- MCP Specification – Authorization: https://modelcontextprotocol.io/specification/draft/basic/authorization
