# Bọc REST API hoặc SDK trong dịch vụ công cụ có hợp đồng rõ ràng

Một REST API hoặc SDK không nên được đưa trực tiếp cho mô hình ngôn ngữ sử dụng như một bề mặt gọi hàm tùy ý. Thay vào đó, ứng dụng nên đặt một lớp dịch vụ công cụ (tool service) ở giữa mô hình và hệ thống nghiệp vụ. Lớp này công bố một hợp đồng nhỏ, ổn định và có ý nghĩa nghiệp vụ; kiểm tra đầu vào; xác thực quyền; gọi REST API hoặc SDK bằng credential do ứng dụng quản lý; chuẩn hóa lỗi và chỉ trả về dữ liệu cần thiết.

Trong Spring AI, hợp đồng mà mô hình nhìn thấy được biểu diễn bằng `ToolDefinition` gồm tên, mô tả và JSON Schema đầu vào. Phần thực thi được biểu diễn bằng `ToolCallback`; có thể khai báo bằng `@Tool`, tạo bằng `FunctionToolCallback` hoặc `MethodToolCallback`, hoặc tự triển khai khi cần proxy một nguồn tool khác. Mô hình chỉ đề xuất tool call và arguments; chính ứng dụng chịu trách nhiệm thực thi lời gọi tới dịch vụ phía sau.

Bài viết xây dựng ví dụ tra cứu trạng thái đơn hàng qua REST API, sau đó chỉ ra cách thay gateway REST bằng SDK mà không làm thay đổi hợp đồng tool.

## 1. Vì sao cần lớp dịch vụ công cụ?

Giả sử hệ thống hiện có một API:

~~~http
GET /internal/v3/tenants/{tenantId}/orders/{orderId}/status
Authorization: Bearer <service-token>
X-Region: ap-southeast-1
~~~

Nếu đưa API này ra trực tiếp cho mô hình, mô hình phải biết nhiều chi tiết không thuộc phạm vi suy luận nghiệp vụ: endpoint nội bộ, tenant, token, header, mã trạng thái, cấu trúc phản hồi và quy tắc phân quyền. Điều này làm schema phức tạp và mở rộng bề mặt tấn công.

Thay vào đó, công bố một tool ở mức nghiệp vụ:

~~~text
get_order_status(orderNumber)
~~~

Mô hình chỉ cần cung cấp mã đơn hàng. Ứng dụng tự xác định tenant và người dùng từ ngữ cảnh đã xác thực, kiểm tra quyền đọc đơn hàng, gọi API nội bộ, chuyển đổi response thành kết quả gọn và trả kết quả cho vòng hội thoại.

Các lợi ích chính:

- **Tách hợp đồng khỏi hạ tầng:** đổi endpoint, nhà cung cấp SDK hoặc cách xác thực mà không cần thay schema tool.
- **Giảm quyền của mô hình:** chỉ công bố các hành động được thiết kế rõ ràng, không cho mô hình chọn URL, header hay credential.
- **Đảm bảo quy tắc nghiệp vụ:** validation, authorization, giới hạn số lượng, trạng thái và idempotency được thực hiện trong ứng dụng.
- **Chuẩn hóa lỗi:** chuyển lỗi HTTP hoặc exception của SDK thành lỗi nghiệp vụ an toàn.
- **Dễ kiểm thử:** có thể kiểm tra tool service bằng fake gateway mà không cần gọi LLM hay hệ thống bên ngoài.

## 2. Ba hợp đồng cần phân biệt

Một tích hợp tốt có ba lớp hợp đồng riêng:

| Hợp đồng | Đối tượng sử dụng | Nội dung |
|---|---|---|
| Tool contract | Mô hình | Tên tool, mô tả, JSON Schema đầu vào và hình dạng kết quả |
| Application service contract | Ứng dụng | DTO nghiệp vụ, validation, authorization, kết quả và lỗi nghiệp vụ |
| Remote API/SDK contract | Hệ thống tích hợp | HTTP endpoint, SDK method, credential, timeout, retry và kiểu dữ liệu của nhà cung cấp |

Không nên để chi tiết của hợp đồng thứ ba rò rỉ vào hợp đồng thứ nhất. Ví dụ, `tenantId`, bearer token, URL tùy ý, tên class SDK hoặc mã lỗi nội bộ thường không phải là arguments mà mô hình cần tự quyết định.

Một kiến trúc tham khảo:

~~~mermaid
flowchart TD
    U[Người dùng] --> C[ChatClient]
    C --> M[Mô hình: tool definition và JSON arguments]
    M --> A[ToolCallingAdvisor / ToolCallingManager]
    A --> T[Tool facade: @Tool / ToolCallback]
    T --> S[Application service]
    S --> V[Validation và authorization]
    V --> G[REST gateway hoặc SDK adapter]
    G --> R[Hệ thống nghiệp vụ]
    R --> G
    G --> S
    S --> T
    T --> A
    A --> M
    M --> C
~~~

Tool facade là adapter dành cho giao thức AI. Application service là nơi thực thi quy tắc nghiệp vụ. REST gateway hoặc SDK adapter là nơi cô lập chi tiết tích hợp bên ngoài.

## 3. Chọn cách khai báo tool trong Spring AI

Spring AI cung cấp ba cách chính để tạo `ToolCallback`:

| Cách khai báo | Khi nên dùng |
|---|---|
| `@Tool` | Bạn sở hữu method và muốn khai báo trực tiếp trên lớp facade |
| `FunctionToolCallback` | Muốn bọc một `Function`, `BiFunction`, method reference hoặc lambda |
| `MethodToolCallback` | Cần tạo callback từ method có sẵn hoặc đăng ký động |

Cả ba cách đều tạo ra `ToolCallback` có thể được truyền cho `ChatClient` hoặc cơ chế điều phối tool.

### `@Tool`: lựa chọn mặc định cho facade

Dùng `@Tool` khi lớp tool do ứng dụng kiểm soát:

~~~java
@Component
public class OrderTools {

    private final OrderApplicationService orderService;

    public OrderTools(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @Tool(
        name = "get_order_status",
        description = """
            Tra cứu trạng thái hiện tại của một đơn hàng mà người dùng
            được phép xem. Dùng khi người dùng hỏi đơn hàng đang ở bước nào.
            Chỉ nhận mã đơn hàng; không dùng tool này để hủy hoặc sửa đơn.
            """
    )
    public OrderStatusResult getOrderStatus(
            @ToolParam(description = "Mã đơn hàng, ví dụ ORD-8F31A2")
            String orderNumber,
            ToolContext toolContext) {

        ActorContext actor = requireActor(toolContext);
        return orderService.getStatus(orderNumber, actor);
    }

    private ActorContext requireActor(ToolContext toolContext) {
        Object value = toolContext.getContext().get("actor");
        if (!(value instanceof ActorContext actor)) {
            throw new MissingActorContextException();
        }
        return actor;
    }
}
~~~

`ToolContext` có kiểu `org.springframework.ai.chat.model.ToolContext`. Tham số này dành cho dữ liệu thực thi nội bộ, không phải argument do mô hình tạo ra. Đưa nó vào method giúp facade nhận được ngữ cảnh đã được ứng dụng gắn vào request.

Khi tạo `ChatClient` hoặc gửi prompt, truyền actor được suy ra từ principal đã xác thực:

~~~java
ActorContext actor = actorContextFactory.from(authentication);

String answer = chatClient.prompt()
    .user(question)
    .toolContext(Map.of("actor", actor))
    .call()
    .content();
~~~

`authentication` ở ví dụ là danh tính do Spring Security xác thực trong ứng dụng. Không lấy `actor`, `tenantId`, role hoặc quyền từ nội dung prompt hay từ JSON arguments mà mô hình sinh ra.

### `FunctionToolCallback`: khi muốn bọc function hoặc SDK method

Nếu tool phù hợp với một function có input/output kiểu rõ ràng, có thể tạo callback bằng builder:

~~~java
@Bean
ToolCallback getOrderStatusTool(OrderApplicationService orderService) {
    return FunctionToolCallback
        .builder(
            "get_order_status",
            (OrderStatusQuery query, ToolContext context) ->
                orderService.getStatus(
                    query.orderNumber(),
                    actorFrom(context)
                )
        )
        .description(
            "Tra cứu trạng thái đơn hàng mà người dùng hiện tại được phép xem."
        )
        .inputType(OrderStatusQuery.class)
        .build();
}
~~~

`inputType(...)` cung cấp kiểu Java để Spring AI sinh JSON Schema. Với function có nhu cầu nhận `ToolContext`, dùng overload nhận `BiFunction` như ví dụ trên.

### Khi nào tự triển khai `ToolCallback`?

Chỉ nên implement trực tiếp `ToolCallback` khi cần kiểm soát đầy đủ `ToolDefinition`, cách parse input, gọi nguồn tool từ xa hoặc cách chuyển đổi kết quả. Một REST API thông thường không bắt buộc phải có callback tùy chỉnh: một facade `@Tool` gọi application service rồi tới REST gateway thường dễ bảo trì hơn.

## 4. Thiết kế tool contract nhỏ và rõ

`ToolDefinition` là hợp đồng mà mô hình nhìn thấy. Nó gồm:

- `name`: tên duy nhất trong tập tool được cung cấp cho một request.
- `description`: tool làm gì, dùng trong tình huống nào và có giới hạn gì.
- `inputSchema`: JSON Schema mô tả arguments.

Ví dụ, tool tra cứu trạng thái đơn hàng chỉ cần một mã đơn:

~~~json
{
  "type": "object",
  "properties": {
    "orderNumber": {
      "type": "string",
      "description": "Mã đơn hàng, ví dụ ORD-8F31A2"
    }
  },
  "required": ["orderNumber"],
  "additionalProperties": false
}
~~~

Các nguyên tắc thiết kế:

1. **Dùng ngôn ngữ nghiệp vụ.** `get_order_status` dễ hiểu hơn `invokeOrderStatusEndpoint`.
2. **Mô tả cả mục đích và giới hạn.** Nêu khi nào nên gọi, dữ liệu nào được phép truyền và hành động nào tool không thực hiện.
3. **Chỉ công bố input cần thiết.** Không đưa URL, HTTP method, header, bearer token, câu SQL hoặc tên tenant vào schema.
4. **Phân biệt bắt buộc và tùy chọn.** Đừng đánh dấu một trường là required nếu mô hình không thể biết giá trị đó.
5. **Dùng kiểu và miền giá trị có giới hạn.** Ưu tiên enum, số có min/max, chuỗi có format hoặc record có field cụ thể thay cho `Map<String, Object>` tùy ý.
6. **Đặt tên ổn định và duy nhất.** Không dùng cùng tên cho hai callback có ý nghĩa hoặc quyền khác nhau.
7. **Giữ schema tương thích.** Thêm field tùy chọn thường ít phá vỡ hơn việc đổi tên hoặc đổi ý nghĩa field bắt buộc.

Spring AI sinh JSON Schema từ tham số method hoặc kiểu input của function. `@ToolParam` có thể cung cấp mô tả và trạng thái required; mặc định các tham số là bắt buộc. Có thể dùng `@Nullable` hoặc các annotation được hỗ trợ để biểu thị trường tùy chọn.

Ví dụ một tham số tùy chọn:

~~~java
@Tool(description = "Tìm đơn hàng theo mã và trạng thái tùy chọn")
public List<OrderSummary> searchOrders(
        @ToolParam(description = "Mã đơn hàng hoặc một phần mã")
        String query,
        @ToolParam(
            description = "Chỉ lấy đơn hàng ở trạng thái này",
            required = false
        )
        OrderStatus status) {
    // ...
}
~~~

Không dựa vào JSON Schema để thay thế validation ở server. Schema giúp mô hình tạo input đúng hơn; client vẫn có thể gửi JSON sai, model có thể đoán sai, và các quy tắc nghiệp vụ vẫn phải được kiểm tra trong ứng dụng.

## 5. Đặt validation và authorization trong application service

Tool facade không nên là nơi duy nhất kiểm tra dữ liệu hoặc quyền. Hãy đặt các quy tắc có thể tái sử dụng trong application service để REST gateway, SDK adapter, controller và tool đều dùng cùng một chính sách.

Ví dụ DTO và ngữ cảnh:

~~~java
public record OrderStatusQuery(
    @NotBlank
    @Pattern(regexp = "ORD-[A-Z0-9]{6,12}")
    String orderNumber
) {}

public record ActorContext(
    String subjectId,
    String tenantId
) {}

public record OrderStatusResult(
    String orderNumber,
    String status,
    Instant lastUpdated,
    String nextStep
) {}
~~~

Application service kiểm tra input, quyền và sau đó mới gọi gateway:

~~~java
@Service
public class OrderApplicationService {

    private final Validator validator;
    private final OrderAuthorization authorization;
    private final OrderGateway orderGateway;
    private final OrderResultMapper mapper;

    public OrderApplicationService(
            Validator validator,
            OrderAuthorization authorization,
            OrderGateway orderGateway,
            OrderResultMapper mapper) {
        this.validator = validator;
        this.authorization = authorization;
        this.orderGateway = orderGateway;
        this.mapper = mapper;
    }

    public OrderStatusResult getStatus(
            String orderNumber,
            ActorContext actor) {

        OrderStatusQuery query = new OrderStatusQuery(orderNumber);
        Set<ConstraintViolation<OrderStatusQuery>> violations =
            validator.validate(query);

        if (!violations.isEmpty()) {
            throw new InvalidToolInputException(
                "Mã đơn hàng không hợp lệ."
            );
        }

        authorization.requireCanReadOrder(
            actor.subjectId(),
            actor.tenantId(),
            query.orderNumber()
        );

        OrderApiResponse response = orderGateway.getStatus(
            actor.tenantId(),
            query.orderNumber()
        );

        return mapper.toToolResult(response);
    }
}
~~~

Trong ví dụ, `Validator` được gọi rõ ràng. Không giả định rằng việc khai báo `@NotBlank`, `@Pattern` hoặc `@Valid` trên một method tool tự động kích hoạt toàn bộ cơ chế validation của Spring MVC.

Authorization phải kiểm tra quyền trên tài nguyên cụ thể. Việc người dùng đã đăng nhập hoặc được phép dùng tool không đồng nghĩa họ được phép đọc mọi đơn hàng. Với dữ liệu đa tenant, luôn ràng buộc truy vấn theo tenant đã xác thực và kiểm tra quyền ở application service hoặc dịch vụ nghiệp vụ có thẩm quyền.

`ToolContext` là phương tiện truyền ngữ cảnh, không phải cơ chế xác thực. Chỉ đưa vào đó giá trị do server tạo ra từ principal, session hoặc credential store. Không cho mô hình tự chọn `subjectId`, `tenantId`, danh sách role hay token.

## 6. Bọc REST API bằng gateway có kiểu dữ liệu

Không để `@Tool` gọi `RestClient` trực tiếp. Tạo một gateway chuyên trách cho API bên ngoài:

~~~java
public interface OrderGateway {
    OrderApiResponse getStatus(String tenantId, String orderNumber);
}
~~~

Cấu hình `RestClient` với base URL cố định do ứng dụng quản lý:

~~~java
@Configuration
class OrderApiConfiguration {

    @Bean
    RestClient orderRestClient(
            RestClient.Builder builder,
            OrderApiProperties properties) {

        return builder
            .baseUrl(properties.baseUrl())
            .build();
    }
}
~~~

Gateway chuyển lời gọi nghiệp vụ thành HTTP request:

~~~java
@Component
public class RestOrderGateway implements OrderGateway {

    private final RestClient restClient;

    public RestOrderGateway(RestClient orderRestClient) {
        this.restClient = orderRestClient;
    }

    @Override
    public OrderApiResponse getStatus(
            String tenantId,
            String orderNumber) {

        return restClient.get()
            .uri(
                "/v1/tenants/{tenantId}/orders/{orderNumber}/status",
                tenantId,
                orderNumber
            )
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .onStatus(
                status -> status.value() == 404,
                (request, response) -> {
                    throw new OrderNotFoundException();
                }
            )
            .onStatus(
                HttpStatusCode::is4xxClientError,
                (request, response) -> {
                    throw new OrderApiRejectedException();
                }
            )
            .onStatus(
                HttpStatusCode::is5xxServerError,
                (request, response) -> {
                    throw new OrderApiUnavailableException();
                }
            )
            .body(OrderApiResponse.class);
    }
}
~~~

Đây là ví dụ minh họa; `OrderApiProperties`, các exception và DTO response là kiểu của ứng dụng. Cấu hình thật cần thiết lập request factory, connect/read timeout, TLS, credential và interceptor phù hợp với hạ tầng.

`RestClient` là HTTP client đồng bộ, có API fluent và chuyển đổi request/response sang kiểu Java. Khi cần kiểm soát status cụ thể, `retrieve().onStatus(...)` cho phép chuyển HTTP error thành exception của ứng dụng. Mặc định `RestClient` ném `RestClientException` cho response 4xx/5xx.

Một số lưu ý khi bọc REST:

- Base URL phải đến từ cấu hình tin cậy, không phải argument do model cung cấp.
- Dùng URI template và path variable đã được validate; tránh nối chuỗi URL tùy ý.
- Credential được lấy từ OAuth2 authorized client, secret manager hoặc cơ chế service-to-service; không đặt token trong tool schema.
- Nếu cần truyền tenant xuống API, dùng tenant đã được xác thực và đã qua kiểm tra quyền.
- Chuyển response từ API sang DTO nội bộ; không trả toàn bộ raw response nếu chứa PII, token, debug field hoặc metadata nội bộ.

### Dùng HTTP Service Client thay vì viết từng request

Nếu API có nhiều endpoint và hợp đồng ổn định, Spring Framework cho phép khai báo Java interface bằng `@HttpExchange`, `@GetExchange`, `@PostExchange` và tạo proxy bằng `HttpServiceProxyFactory`. Proxy có thể dùng `RestClient`, `WebClient` hoặc `RestTemplate` làm transport.

Lợi ích là application service gọi một Java interface có kiểu dữ liệu thay vì thao tác trực tiếp với URL và HTTP headers. Lớp tool facade vẫn không đổi:

~~~text
@Tool facade
    -> OrderApplicationService
        -> OrderApi interface proxy
            -> REST endpoint
~~~

## 7. Bọc SDK của nhà cung cấp theo cùng một cách

Khi hệ thống tích hợp có SDK Java, hãy giữ SDK ở phía sau một adapter. Không expose trực tiếp tất cả method, class hoặc exception của SDK cho mô hình.

Ví dụ:

~~~java
public interface PaymentGateway {
    PaymentStatusResponse getStatus(
        String tenantId,
        String paymentReference
    );
}

@Component
public class VendorPaymentGateway implements PaymentGateway {

    private final VendorPaymentSdk sdk;

    public VendorPaymentGateway(VendorPaymentSdk sdk) {
        this.sdk = sdk;
    }

    @Override
    public PaymentStatusResponse getStatus(
            String tenantId,
            String paymentReference) {

        VendorPayment raw = sdk.payments().get(
            tenantId,
            paymentReference
        );

        return new PaymentStatusResponse(
            raw.reference(),
            raw.status().name(),
            raw.updatedAt()
        );
    }
}
~~~

Application service không nên phụ thuộc trực tiếp vào kiểu trả về của vendor SDK. Gateway chịu trách nhiệm:

- Chuyển DTO nghiệp vụ thành request của SDK.
- Chọn đúng credential và tenant scope.
- Chuẩn hóa kiểu dữ liệu, timezone, tiền tệ và enum.
- Chuyển exception riêng của vendor thành exception của ứng dụng.
- Che giấu thông tin nội bộ không cần thiết trong kết quả.
- Cô lập thay đổi phiên bản SDK khỏi tool contract.

Nhờ vậy, khi chuyển từ REST sang SDK hoặc thay nhà cung cấp, `@Tool` và JSON Schema có thể giữ nguyên.

## 8. Xử lý lỗi từ REST API hoặc SDK

Không nên để exception thô của thư viện HTTP hoặc SDK truyền thẳng về mô hình. Hãy chuyển lỗi theo nhóm nghiệp vụ và quyết định ứng dụng nên tiếp tục hay dừng:

| Nguồn lỗi | Cách chuẩn hóa gợi ý | Có nên retry? |
|---|---|---|
| Input sai format hoặc thiếu field | `InvalidToolInputException` với thông báo ngắn | Không |
| Không tìm thấy tài nguyên | `OrderNotFoundException` | Không |
| Người dùng không có quyền | `AccessDeniedException` hoặc lỗi từ chối chung | Không |
| API từ chối request 4xx | `UpstreamRejectedException` | Thường không |
| API giới hạn tốc độ 429 | `UpstreamRateLimitException` | Có thể, theo `Retry-After` và ngân sách |
| Timeout hoặc lỗi mạng tạm thời | `UpstreamTimeoutException` | Có thể nếu thao tác an toàn |
| API 5xx | `UpstreamUnavailableException` | Có thể với retry giới hạn |

### Quy tắc retry

- Chỉ retry lỗi có khả năng tạm thời, với số lần và tổng thời gian chờ có giới hạn.
- Dùng exponential backoff và jitter; tôn trọng `Retry-After` nếu dịch vụ cung cấp.
- GET thường có thể retry, nhưng vẫn phải xem xét semantics của API.
- Không retry POST/PUT/PATCH có side effect nếu không có cơ chế idempotency rõ ràng.
- Với thao tác tạo thanh toán, hoàn tiền, đặt hàng hoặc gửi thông báo, tạo idempotency key ở phía server và lưu trạng thái thực thi để một lần retry không tạo hành động trùng.
- Timeout của HTTP client phải phù hợp với timeout tổng của tool và vòng gọi model. Không để một tool chờ vô hạn.

### Không tiết lộ lỗi nội bộ cho mô hình

Spring AI bọc lỗi thực thi thành `ToolExecutionException` và chuyển cho `ToolExecutionExceptionProcessor`. Processor có thể chuyển thông báo lỗi thành tool result để mô hình phản hồi, hoặc ném exception ra caller.

Theo mặc định trong Spring AI 2.1.0, `DefaultToolExecutionExceptionProcessor` gửi message của `RuntimeException` về mô hình; checked exception và `Error` được ném lại. Có thể cấu hình `spring.ai.tools.throw-exception-on-error=true` để yêu cầu lỗi được ném cho caller xử lý.

Vì vậy, không đặt raw HTTP body, stack trace, SQL, hostname nội bộ, token hoặc thông tin debug trong message của exception. Hãy dùng thông báo đã chuẩn hóa như:

~~~json
{
  "ok": false,
  "code": "ORDER_SERVICE_UNAVAILABLE",
  "message": "Dịch vụ đơn hàng tạm thời không khả dụng. Vui lòng thử lại sau."
}
~~~

Với lỗi phân quyền, tránh tiết lộ đơn hàng có tồn tại hay không nếu chính sách bảo mật không cho phép. Một lỗi từ chối chung có thể phù hợp hơn.

## 9. Bảo vệ tool có side effect

Các tool đọc dữ liệu và các tool thay đổi trạng thái không có cùng mức rủi ro. Có thể chia nhóm:

| Nhóm | Ví dụ | Kiểm soát |
|---|---|---|
| Read-only | Tra cứu đơn hàng, xem trạng thái thanh toán | Authorization theo tài nguyên, giới hạn kết quả |
| Reversible write | Cập nhật ghi chú, đổi lịch hẹn | Authorization, validation, audit |
| High-impact write | Hủy đơn, hoàn tiền, chuyển tiền | Authorization chặt, idempotency, xác nhận người dùng |
| Irreversible/destructive | Xóa dữ liệu, đóng tài khoản | Phê duyệt rõ ràng, audit và chính sách riêng |

Spring AI 2.1.0 hỗ trợ đánh dấu tool cần xác nhận bằng `requiresConfirmation = true`:

~~~java
@Tool(
    name = "cancel_order",
    description = "Hủy đơn hàng khi người dùng có quyền và đã xác nhận.",
    requiresConfirmation = true
)
public CancellationResult cancelOrder(
        @ToolParam(description = "Mã đơn hàng cần hủy")
        String orderNumber,
        ToolContext toolContext) {
    ActorContext actor = requireActor(toolContext);
    return orderService.cancel(orderNumber, actor);
}
~~~

Cơ chế confirmation giúp vòng tool calling tạm dừng để ứng dụng thu thập quyết định allow/deny trước khi thực thi. Tuy nhiên, confirmation không thay thế authorization: ứng dụng vẫn phải xác thực người phê duyệt và kiểm tra quyền đối với tài nguyên. Không coi việc mô hình yêu cầu gọi tool là sự đồng ý của người dùng.

## 10. Trả kết quả có cấu trúc và vừa đủ

Kết quả tool thường được chuyển thành chuỗi để gửi lại cho mô hình. Spring AI dùng `ToolCallResultConverter`; converter mặc định dùng Jackson để serialize object.

Ưu tiên trả DTO nhỏ, có tên field rõ nghĩa:

~~~json
{
  "orderNumber": "ORD-8F31A2",
  "status": "IN_TRANSIT",
  "lastUpdated": "2026-11-27T08:30:00Z",
  "nextStep": "Đơn hàng đang được vận chuyển đến địa chỉ nhận."
}
~~~

Không trả nguyên object domain hoặc response vendor nếu nó có hàng chục field không liên quan. Một tool tra cứu trạng thái không cần trả toàn bộ lịch sử giao dịch, thông tin thanh toán, địa chỉ đầy đủ hoặc dữ liệu cá nhân khác.

Các nguyên tắc cho output:

- Chỉ trả field cần để mô hình trả lời câu hỏi.
- Dùng enum hoặc mã trạng thái ổn định, kèm mô tả dễ hiểu nếu cần.
- Chuẩn hóa timezone và định dạng ngày giờ.
- Giới hạn kích thước danh sách, phân trang và độ dài chuỗi.
- Không trả secret, bearer token, session cookie, stack trace hoặc internal ID không cần thiết.
- Nếu kết quả quá lớn, trả summary và một handle an toàn để ứng dụng có thể lấy chi tiết ở bước riêng.

`returnDirect = true` chỉ phù hợp khi kết quả tool chính là đầu ra mong muốn và không cần mô hình tổng hợp thêm. Với kết quả cần giải thích hoặc kết hợp với ngữ cảnh hội thoại, để tool result quay lại mô hình là lựa chọn thông thường.

## 11. REST client đồng bộ, SDK bất đồng bộ và giới hạn kiểu trả về

`RestClient` phù hợp với một tool đồng bộ có request/response rõ ràng. `WebClient` hỗ trợ I/O non-blocking, reactive và streaming; tuy nhiên không nên giả định một method tool có thể trả mọi kiểu reactive hoặc future.

Với `MethodToolCallback`, Spring AI không hỗ trợ `Optional`, `CompletableFuture`, `Future`, `Mono`, `Flux`, `Flow` hoặc functional types làm kiểu tham số/return value của method tool. Các kiểu này không được chuyển thành schema hoặc kết quả tool theo cách method callback mong đợi.

Nếu SDK hoặc API chỉ cung cấp reactive result:

- Có thể tạo adapter đồng bộ có timeout hữu hạn nếu kiến trúc cho phép và không block event-loop.
- Nếu tác vụ kéo dài, tách thành hai tool: `submit_operation` trả `operationId`, và `get_operation_status` truy vấn trạng thái.
- Nếu cần streaming tiến độ, dùng một workflow hoặc endpoint SSE/WebSocket riêng cho ứng dụng thay vì cố serialize `Flux` thành tool result.
- Không gọi `.block()` tùy tiện trên reactive event-loop.

Hãy chọn mô hình thực thi dựa trên bản chất của SDK và cách ứng dụng chạy; không chỉ dựa vào việc một kiểu Java có thể biên dịch.

## 12. Kiểm thử hợp đồng từ tool tới dịch vụ ngoài

Kiểm thử nên bao phủ cả hợp đồng mà mô hình nhìn thấy và hành vi thật của ứng dụng.

| Lớp kiểm thử | Điều cần xác minh |
|---|---|
| Tool definition | Tên duy nhất, mô tả rõ, schema đúng và không chứa field nhạy cảm |
| Input validation | Chuỗi rỗng, sai format, giá trị vượt giới hạn đều bị từ chối |
| ToolContext | Actor/tenant lấy từ context server; thiếu context thì không gọi API |
| Authorization | Người dùng tenant A không đọc hoặc sửa tài nguyên tenant B |
| Application service | Chỉ gọi gateway sau khi input và quyền hợp lệ |
| REST gateway | URL, method, header, serialization và mapping status đúng |
| SDK adapter | Mapping input/output và exception vendor đúng |
| Retry/idempotency | Timeout không gây side effect trùng |
| Result conversion | Kết quả là JSON gọn, không chứa secret hoặc dữ liệu thừa |
| Tool confirmation | Tool rủi ro cao phải chờ quyết định hợp lệ |
| Integration | Tool call đi qua ChatClient và trả kết quả theo đúng contract |

Một unit test cho application service có thể dùng gateway giả:

~~~java
@Test
void deniesAccessBeforeCallingGateway() {
    ActorContext actor = new ActorContext("user-1", "tenant-A");

    doThrow(new AccessDeniedException("Access denied"))
        .when(authorization)
        .requireCanReadOrder("user-1", "tenant-A", "ORD-8F31A2");

    assertThatThrownBy(() ->
        service.getStatus("ORD-8F31A2", actor)
    ).isInstanceOf(AccessDeniedException.class);

    verifyNoInteractions(orderGateway);
}
~~~

Đây là ví dụ minh họa với `requireCanReadOrder(...)` ném exception khi người dùng không có quyền. Điều quan trọng là kiểm tra rằng gateway không bị gọi khi quyền bị từ chối.

Nên có thêm contract test cho `ToolCallback.getToolDefinition()` hoặc callback được sinh từ `@Tool`: xác minh tên, mô tả, JSON Schema, trường required và các giá trị enum. Với REST gateway, dùng HTTP stub như MockRestServiceServer hoặc WireMock để kiểm tra mapping status, timeout và payload. Với SDK, mock interface adapter thay vì mock mọi class nội bộ của vendor.

## 13. Các lỗi thiết kế thường gặp

| Thiết kế sai | Rủi ro | Cách thay thế |
|---|---|---|
| Cho mô hình truyền URL hoặc host tùy ý | SSRF, gọi nhầm dịch vụ nội bộ | Cố định base URL trong cấu hình |
| Cho mô hình truyền bearer token hoặc header tùy ý | Rò rỉ credential và giả mạo danh tính | Credential do server quản lý |
| Cho mô hình tự truyền tenant/user ID | Truy cập chéo tenant | Lấy actor từ `ToolContext` do server tạo |
| Gọi SDK trực tiếp từ `@Tool` | Facade dính chặt vendor, khó test | Application service và gateway adapter |
| Trả raw response của API | Lộ PII và tăng token | Map sang DTO kết quả tối thiểu |
| Chỉ dựa vào JSON Schema | Input không hợp lệ vẫn có thể đến runtime | Validate lại trong application service |
| Dùng một tool tổng quát với `operation` và `payload` tùy ý | Hợp đồng mơ hồ, quyền khó kiểm soát | Tách tool theo hành động nghiệp vụ |
| Retry mọi exception | Tạo side effect trùng hoặc làm quá tải hệ thống | Phân loại lỗi và dùng idempotency |
| Dùng tool calling như authorization | Model có thể yêu cầu hành động trái quyền | Kiểm tra quyền tại mỗi lần thực thi |
| Trả `Mono`/`CompletableFuture` từ method tool | Kết quả không được serialize như mong muốn | Trả DTO đồng bộ hoặc dùng job workflow |

## 14. Checklist trước khi công bố tool

- [ ] Tool name duy nhất, ổn định và thể hiện hành động nghiệp vụ.
- [ ] Description nêu rõ mục đích, trường hợp sử dụng và giới hạn.
- [ ] JSON Schema chỉ chứa arguments mà mô hình thực sự cần cung cấp.
- [ ] Trường required/optional và enum được khai báo chính xác.
- [ ] Tool facade không gọi endpoint tùy ý hoặc nhận credential từ model.
- [ ] Application service validate lại input ở server.
- [ ] Tenant và actor lấy từ context đáng tin cậy, không lấy từ prompt.
- [ ] Authorization kiểm tra quyền trên từng tài nguyên và từng hành động.
- [ ] REST gateway hoặc SDK adapter cô lập chi tiết của nhà cung cấp.
- [ ] Timeout, retry, circuit breaker và idempotency phù hợp với thao tác.
- [ ] Lỗi upstream được chuẩn hóa và không làm lộ thông tin nội bộ.
- [ ] Output DTO gọn, có cấu trúc và đã loại bỏ dữ liệu nhạy cảm.
- [ ] Tool có side effect được phân loại rủi ro và yêu cầu confirmation khi phù hợp.
- [ ] Unit test, contract test và integration test bao phủ đường đi từ tool đến dịch vụ.
- [ ] Logs, metrics và traces không ghi raw secret hoặc dữ liệu cá nhân không cần thiết.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): định nghĩa tool, `@Tool`, `ToolCallback`, `ToolContext`, JSON Schema, result conversion, exception handling và observability.
- [Spring AI 2.1.x — ToolCallback API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/ToolCallback.html): hợp đồng callback và phương thức thực thi.
- [Spring AI 2.1.x — FunctionToolCallback API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/function/FunctionToolCallback.html): callback dựa trên `Function`, `BiFunction`, `Supplier` và `Consumer`.
- [Spring AI 2.1.x — ToolContext API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/model/ToolContext.html): ngữ cảnh thực thi không được gửi cho mô hình.
- [Spring AI — Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html): tạm dừng và yêu cầu phê duyệt trước khi chạy tool.
- [Spring Framework 7 — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `WebClient`, HTTP Service Clients và xử lý lỗi HTTP.

Một tool service tốt không phải là bản sao của REST endpoint hoặc SDK method. Nó là một hợp đồng nghiệp vụ nhỏ, có kiểu dữ liệu, được bảo vệ bởi validation và authorization, còn chi tiết giao tiếp bên ngoài được giữ trong gateway. Cách phân lớp này giúp tích hợp Spring AI an toàn hơn, dễ thay đổi và có thể kiểm thử độc lập với mô hình.

