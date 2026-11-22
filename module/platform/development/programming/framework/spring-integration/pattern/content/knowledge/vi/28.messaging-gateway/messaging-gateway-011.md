# Gateway và boundary giữa application code với flow

## 1. Bài toán: application code không nên biết bên trong message flow

Một ứng dụng thương mại điện tử cần hai thao tác:

- **Xem báo giá**: tính tổng tiền, không tạo đơn.
- **Đặt hàng**: xác thực yêu cầu, ghi đơn và trả kết quả.

Nếu controller/service phụ thuộc trực tiếp vào `MessageChannel`, `MessageBuilder` và headers nội bộ, business code bắt đầu chứa logic tích hợp:

~~~java
// Ví dụ thiết kế gắn quá chặt application code với messaging.
public OrderReceipt place(PlaceOrderCommand command) {
    Message<PlaceOrderCommand> message =
        MessageBuilder.withPayload(command)
            .setHeader("replyChannel", temporaryChannel)
            .setHeader("errorChannel", errorChannel)
            .build();
    orderRequestChannel.send(message);
    Message<?> reply = temporaryChannel.receive(5_000);
    return (OrderReceipt) reply.getPayload();
}
~~~

Code phải tự quản lý **reply channel, timeout, cast, error path và message identity**. Khi kiến trúc chuyển từ một DirectChannel đồng bộ sang executor/broker hoặc thêm Router–Transformer–Aggregator, controller có thể phải sửa theo.

**Messaging Gateway** tạo một **cổng gọi có kiểu** để application code tương tác với hệ thống message-driven:

~~~java
OrderReceipt receipt = orderGateway.place(command);
~~~

Application code gọi một method như service thông thường; Spring Integration đưa request vào flow, chờ hoặc nhận reply theo cấu hình và chuyển kết quả về kiểu trả về đã khai báo.

~~~mermaid
flowchart LR
    APP["Application / Controller"] --> IFACE["Java Gateway interface"]
    IFACE --> PROXY["Spring Integration gateway proxy"]
    PROXY --> REQ["Request channel"]
    REQ --> FLOW["Filter → Router → Transformer → Handler"]
    FLOW --> REP["Reply / error path"]
    REP --> PROXY
    PROXY --> APP
~~~

**Ranh giới quan trọng:** Gateway **che giao thức message khỏi caller**, không che **trách nhiệm định nghĩa business contract**. Người gọi vẫn cần biết thao tác là query hay command, có thể timeout, retry an toàn hay không và trạng thái kết quả nghĩa là gì.

Bài thuộc chương **Messaging gateway** trong module **SPRING_INTEGRATION_PATTERN**. Module học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng message flow ít phụ thuộc, dễ mở rộng, thực hành **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và theo dõi các nhánh xử lý.

Sau bài này bạn sẽ phân biệt gateway proxy với adapter/gateway giao thức, thiết kế API request–reply hoặc one-way, đặt boundary theo nghiệp vụ, hiểu timeout và error semantics, giữ correlation qua flow phân tán và viết các bài kiểm thử chứng minh application code không phụ thuộc vào cấu trúc channel nội bộ.

## 2. Gateway khác Service Activator như thế nào?

| Thành phần | Vai trò | Góc nhìn |
|---|---|---|
| **Messaging Gateway proxy** | Cho code ứng dụng gọi message flow qua method | **Ứng dụng → messaging** |
| **Service Activator** | Đưa một message vào method thực thi nghiệp vụ | **Messaging → ứng dụng/service** |
| **Message Channel** | Truyền message giữa endpoints | Kết nối trong flow |
| **Router** | Chọn nhánh xử lý | Điều phối |
| **Transformer** | Đổi biểu diễn payload/message | Chuyển contract |
| **Gateway giao thức** | Trao đổi request/reply với HTTP, AMQP... | Ranh giới external transport |

Một chu trình có thể là:

~~~text
Application service
   → Messaging Gateway interface
   → request channel
   → Transformer
   → Service Activator
   → reply
   → Messaging Gateway proxy
   → application service
~~~

**Không đảo chiều trách nhiệm.** `@MessagingGateway` không tự chạy nghiệp vụ: nó chuyển request vào flow. `@ServiceActivator` không tự tạo public application API: nó xử lý message đến endpoint.

Với transport, cụm từ “inbound gateway” và “outbound gateway” có nghĩa riêng: **inbound gateway** đưa request từ thế giới ngoài vào Spring Integration rồi trả response; **outbound gateway** gửi request từ flow ra hệ thống ngoài và nhận response. Chúng vẫn tuân theo pattern request–reply nhưng không phải cùng một bean/proxy với interface `@MessagingGateway`.

## 3. Kiến trúc Ports and Adapters: application port trước, flow sau

Một application port:

~~~java
public interface OrderApplicationPort {
    QuoteResult quote(QuoteRequest request);
    PlaceOrderResult place(PlaceOrderCommand command);
}
~~~

Gateway có thể triển khai cổng này thông qua một interface do Spring Integration tạo proxy, hoặc một adapter Java mỏng ủy quyền tới gateway.

Đường phụ thuộc mong muốn:

~~~text
Controller / Use case
    ↓ uses
OrderApplicationPort (DTO thuần)
    ↓ implemented by
MessagingGateway adapter
    ↓ sends to
IntegrationFlow
    ↓ invokes
Domain / infrastructure components
~~~

**Application code không nên biết:** `DirectChannel` hay `ExecutorChannel`, tên Spring bean của Router, `replyChannel`, `MessageHeaders.ID` hoặc số endpoints trong flow.

**Application code cần biết:** request schema, output schema, business status, timeout/cancel behavior, retry/idempotency contract và cách phân biệt input invalid với infrastructure failure.

Đây là một **boundary ổn định về API**, không phải lời hứa rằng mọi thay đổi phía sau luôn trong suốt. Nếu đổi flow đồng bộ sang xử lý hàng giờ, giữ return type đồng bộ như cũ có thể không còn hợp lý.

## 4. Định nghĩa DTO theo nghiệp vụ, không theo Spring Message

Ví dụ Java 17:

~~~java
record QuoteRequest(
    String tenantId,
    String productId,
    int quantity
) {}

record QuoteResult(
    String productId,
    BigDecimal total,
    String currency
) {}

record PlaceOrderCommand(
    String tenantId,
    String commandId,
    String orderId,
    List<OrderLine> lines
) {}

record OrderLine(
    String sku,
    int quantity
) {}

record PlaceOrderResult(
    String orderId,
    String commandId,
    String status
) {}
~~~

DTO là **contract ứng dụng**, không phải Spring Integration classes. `commandId` nhận diện một **logical operation** qua retry; không dùng `MessageHeaders.ID` hoặc `traceId` thay thế.

Với multi-tenant, `tenantId` trong payload có thể chỉ là **claim cần xác minh**, không tự động là danh tính đáng tin. Bước ingress/gateway adapter phải đối chiếu principal/verified identity trước khi cho một command tác động dữ liệu.

Nếu cần domain status phong phú, ưu tiên enum/sealed result có nghĩa rõ như `ACCEPTED`, `SUCCEEDED`, `REJECTED`, `PENDING` thay vì string tùy ý hoặc HTTP status được truyền sâu vào domain.

## 5. Cấu hình Messaging Gateway interface đầu tiên

Spring Integration có thể tạo implementation cho interface được annotate:

~~~java
@MessagingGateway(
    defaultRequestChannel = "orders.quote.requests")
public interface QuoteGateway {
    QuoteResult quote(QuoteRequest request);
}
~~~

Đăng ký hỗ trợ annotation scanning theo cấu hình dự án, ví dụ:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
class MessagingConfiguration {
}
~~~

`@IntegrationComponentScan` giúp phát hiện các interface được annotate theo package scanning; nếu dự án dùng cách đăng ký gateway khác như `@Bean`/factory, cần chỉ áp một cách tương ứng. Với Spring Boot, kiểm tra chính xác package scan, dependency Spring Integration và auto-configuration đang bật.

Sau đó code ứng dụng có thể inject:

~~~java
@Service
class CheckoutUseCase {
    private final QuoteGateway quotes;

    CheckoutUseCase(QuoteGateway quotes) {
        this.quotes = quotes;
    }

    QuoteResult preview(QuoteRequest request) {
        return quotes.quote(request);
    }
}
~~~

**Không cần tự tạo `Message<?>` ở caller.** Proxy xây request message từ method argument và đưa tới `orders.quote.requests`. Đây là lợi ích chính của Gateway boundary.

## 6. Bổ sung flow cho request–reply

Một service thuần:

~~~java
@Service
class QuoteCalculator {
    QuoteResult calculate(QuoteRequest request) {
        if (request.quantity() <= 0) {
            throw new IllegalArgumentException(
                "INVALID_QUANTITY");
        }
        BigDecimal unitPrice = new BigDecimal("12.50");
        BigDecimal total = unitPrice.multiply(
            BigDecimal.valueOf(request.quantity()));
        return new QuoteResult(
            request.productId(), total, "USD");
    }
}
~~~

Flow Java DSL:

~~~java
@Bean
IntegrationFlow quoteFlow(QuoteCalculator calculator) {
    return IntegrationFlow.from("orders.quote.requests")
        .handle(
            QuoteRequest.class,
            (request, headers) -> calculator.calculate(request))
        .get();
}
~~~

Đây là ví dụ **đồng bộ, một handler tạo một reply payload**. Spring Integration dùng cơ chế reply channel của request–reply để trả giá trị về gateway; không cần tạo thủ công một QueueChannel chỉ để trả reply.

`QuoteCalculator` là business service mẫu, chưa xử lý tenant authorization, currency sourcing hay pricing concurrency đầy đủ. Điều quan trọng của ví dụ: **caller gọi method; flow xử lý message; result về dưới dạng DTO**.

Không đưa cùng input channel vào nhiều cạnh tranh subscribers chỉ vì tạo thêm một flow test; khi cần broadcast dùng Publish-Subscribe Channel theo đúng semantics.

## 7. Request–reply có nghĩa là gì?

Một method:

~~~java
QuoteResult quote(QuoteRequest request);
~~~

ngầm cho caller biết có **reply thuộc request đó** hoặc có **error/timeout**. Trong flow đồng bộ:

~~~mermaid
sequenceDiagram
    participant A as Application
    participant G as Gateway proxy
    participant C as Request channel
    participant H as Quote handler
    A->>G: quote(request)
    G->>C: Message + replyChannel
    C->>H: QuoteRequest
    H-->>G: QuoteResult reply
    G-->>A: QuoteResult
~~~

Trong flow bất đồng bộ, message có thể đi qua executor/broker trước khi reply về Gateway. Lúc ấy request–reply cần **correlation, return address, deadline và handling of late replies**; không thể chỉ giả định mọi handler hoàn tất ngay.

**Một reply không tự chứng minh business đã commit.** Nếu handler chỉ đưa lệnh vào durable queue rồi trả `ACCEPTED`, caller phải hiểu đó là **đã tiếp nhận**, không phải `SUCCEEDED`.

## 8. Gateway proxy che `Message<?>` nhưng không bỏ qua message semantics

Trong ứng dụng:

~~~java
QuoteResult result = quoteGateway.quote(request);
~~~

Trong flow vẫn tồn tại:

- `Message<?>` có payload.
- `MessageHeaders.ID` của từng Spring message.
- Reply/error channels.
- Correlation metadata nếu flow có Splitter/Aggregator hoặc request–reply qua transport.
- Các headers phục vụ trace, tenant context (đã xác thực), content type và routing.

**Boundary tốt:** application service không trực tiếp khai báo những headers nội bộ, nhưng Gateway adapter/flow vẫn truyền những metadata cần thiết.

Khi một DTO không đủ mô tả transport security/identity, một application adapter có thể nhận `AuthenticatedCommand`/envelope đã xác minh rồi gọi gateway. Không nên đưa toàn bộ HTTP request, Kafka ConsumerRecord hoặc Spring `MessageHeaders` vào public domain interface.

## 9. `@Gateway` ở method cho nhiều operations

Một interface có thể khai báo các method theo request channel:

~~~java
@MessagingGateway
public interface OrderGateway {

    @Gateway(requestChannel = "orders.quote.requests")
    QuoteResult quote(QuoteRequest request);

    @Gateway(requestChannel = "orders.place.requests")
    PlaceOrderResult place(PlaceOrderCommand command);
}
~~~

Mỗi method diễn đạt một **operation** và một **request channel**. Điều này giúp:

- Tránh một method generic `execute(Object payload)` cho cả query và command.
- Hạn chế việc runtime payload type làm chọn nhầm nhánh.
- Cho phép Gateway có policy khác nhau theo nghiệp vụ.
- Dễ mock/stub cổng ứng dụng trong unit test.

Đừng cho client tự cung cấp tên channel/method rồi route vào handler có quyền ghi theo một chuỗi tùy ý. Với operations động, dùng Router allowlist có authorization và validation.

## 10. Gateway interface khác với HTTP Controller

Một controller có thể gọi gateway:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderGateway gateway;

    OrderController(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @PostMapping
    PlaceOrderResult place(@RequestBody PlaceOrderCommand cmd) {
        return gateway.place(cmd);
    }
}
~~~

**Ví dụ trên chưa phải cấu hình production bảo mật:** HTTP controller phải validate request bytes/schema, xác thực principal, xác minh tenant và map exception/timeout sang HTTP status phù hợp. Không cho client tự điền `tenantId` rồi mặc nhiên cho phép ghi mọi tenant.

HTTP boundary nhận HTTP semantics; Gateway nhận typed Java call; IntegrationFlow nhận message. Nhờ vậy HTTP API có thể thay đổi response mapping mà không yêu cầu mọi business handler biết `ResponseEntity`, status 400/503 hay HTTP headers.

Ngược lại, một **HTTP inbound gateway của Spring Integration** có thể thay thế một phần controller bằng cách trực tiếp kết nối HTTP request vào message flow. Đó là lựa chọn kiến trúc khác, vẫn cần authentication, validation và response mapping riêng.

## 11. Cổng nghiệp vụ read-only và cổng command phải có semantics khác

| Thuộc tính | `quote()` | `place()` |
|---|---|---|
| Side effect nghiệp vụ | Không | Có |
| Retry caller sau timeout | Thường an toàn hơn | Chỉ an toàn với idempotency key |
| Transaction | Có thể không cần write transaction | Phải kiểm soát commit/rollback |
| Reply | Giá/điều kiện tính | Order receipt hoặc outcome |
| Timeout | Không có giá tại thời điểm gọi | Không chứng minh order chưa được tạo |
| Authorization | Được phép xem báo giá | Được phép tạo đơn/chi tiền |
| Idempotency | Có thể cache kết quả | Cần durable dedupe cho logical command |

**Gọi qua cùng Gateway abstraction không khiến hai method có cùng hành vi.** Khi kết quả lệnh ghi chưa rõ do timeout, caller không nên tạo một `commandId` mới cho cùng ý định đặt hàng, vì sẽ bị xem như một operation mới và có thể double create.

## 12. One-way Gateway và `void`: “đã gửi” không phải “đã xử lý”

Một API fire-and-forget:

~~~java
@MessagingGateway(
    defaultRequestChannel = "audit.events")
interface AuditGateway {
    void record(AuditEvent event);
}
~~~

Với một input channel đồng bộ, method có thể trả sau khi việc send/dispatch tương ứng hoàn tất; với queue/executor/broker, downstream có thể còn đang xử lý hoặc chưa nhận. **`void` không có business reply**, không nên diễn giải rằng audit record đã được durable commit chỉ vì method return.

Nếu ứng dụng cần bảo đảm event được lưu bền vững trước khi xác nhận:

- Ghi vào một **durable queue/outbox** trong transaction phù hợp; hoặc
- Định nghĩa acknowledgement/result có nghĩa rõ khi receiver đã persist; hoặc
- Để workflow quản lý status bất đồng bộ và cung cấp cách tra cứu.

Không dùng `void` cho một Gateway mà caller **bắt buộc cần biết** `OrderReceipt` hoặc business failure. Nếu handler return `null` trong đường request–reply, caller có thể chờ reply đến timeout thay vì nhận kết quả có nghĩa.

## 13. Gateway là boundary API, không phải authorization boundary mặc định

Một method có tên:

~~~java
PlaceOrderResult place(PlaceOrderCommand command);
~~~

không chứng minh người gọi được phép tạo đơn. Gateway interface là một **programming interface**, không tự xác thực principal hoặc tenant.

Ở boundary ingress:

1. Authenticate HTTP/broker producer theo transport.
2. Xác minh quyền trên tenant và operation.
3. Validate request schema và business invariants.
4. Tạo verified identity/context khi đưa vào flow.
5. Re-check domain authorization tại command service boundary khi phù hợp.

Với ExecutorChannel hoặc broker, security context theo thread **không tự động được propagate**. Nếu flow cần quyền sau boundary async, hãy thiết kế verified identity envelope/claims với integrity và lifetime đúng, không tin raw headers từ client.

Đặc biệt không dùng `businessCorrelationId` như một token cấp quyền, và không cho external caller tự gửi header `replyChannel`/`errorChannel` để điều khiển response tới channel nội bộ tùy ý.

## 14. Reply channel: return address của invocation, không phải business ID

Một Gateway đồng bộ tạo hoặc sử dụng cơ chế **return address** để reply quay về đúng caller. Trong Spring Messaging, reply address thường được biểu diễn qua `MessageHeaders.REPLY_CHANNEL`/`replyChannel`.

~~~text
Gateway request #A
  replyChannel=A-return-address
  commandId=C-801
  businessCorrelationId=tenant-a|O-801

Gateway request #B
  replyChannel=B-return-address
  commandId=C-801        (caller retry cùng logical command)
  businessCorrelationId=tenant-a|O-801
~~~

**A và B có thể có hai reply addresses khác nhau** dù là cùng business operation. Không dùng return address làm idempotency key hoặc group key.

| Thông tin | Chức năng | Có ổn định qua retry/broker không? |
|---|---|---|
| `replyChannel` | Nơi trả reply cho lời gọi hiện tại | Không nên giả định |
| `errorChannel` | Đường nhận lỗi tùy topology | Không nên giả định |
| `MessageHeaders.ID` | ID Spring message instance | Có thể đổi |
| `commandId` | Logical command/idempotency identity | Phải giữ ổn định theo contract |
| `businessCorrelationId` | Nhóm một workflow | Phải scoped theo domain |
| `traceId` | Truy vết request | Không thay business ID |

Một channel object nội bộ JVM thường **không phải nội dung có thể serialize nguyên trạng qua Kafka/AMQP**. External gateway/protocol adapter có thể cần reply-to destination, correlation ID và một gateway reply listener riêng, tùy giao thức.

## 15. Timeout gửi request và timeout chờ reply là hai vấn đề khác nhau

Một Gateway request–reply có thể gặp:

- **Request/send timeout**: chưa gửi thành công message vào channel có capacity/buffer/ràng buộc gửi; với DirectChannel call blocking, ngữ nghĩa deadline có thể khác một queue-backed channel.
- **Reply/receive timeout**: đã gửi request nhưng không nhận reply trong khoảng cho phép.
- **Business deadline**: request không còn hữu ích sau một thời điểm; downstream phải có quy tắc riêng.
- **Transport timeout**: AMQP/HTTP/Kafka request–reply chờ response hoặc kết nối hết hạn.

Ví dụ:

~~~text
T0 Gateway.place(C-801) bắt đầu.
T1 Request đã vào flow.
T2 Handler đang ghi database.
T3 Caller hết reply timeout.
T4 Handler COMMIT.
T5 Reply đến sau deadline; caller trước đó đã nhận timeout.
~~~

**Timeout không có nghĩa downstream bị hủy hoặc rollback.** Caller không thể tự suy rằng lệnh chưa chạy và lập tức gọi lại với một `commandId` mới.

Khi cấu hình timeout, kiểm tra chính xác **đơn vị, thuộc tính của annotation/factory, và loại request channel** theo Spring Integration version thực tế. Không dùng một con số timeout như lời hứa end-to-end cho transaction, queue delay và remote handler.

## 16. Cấu hình thời hạn: tầng Gateway khác tầng xử lý nghiệp vụ

Một API có thể công bố:

~~~text
Gateway reply timeout: ví dụ 3 giây
Business operation deadline: ví dụ 15 giây
Broker message expiration: policy riêng
Remote service timeout: policy riêng
Retry budget: tối đa 3 attempts
~~~

Những ngưỡng này phải tương thích. Ví dụ caller đã hết deadline sau 3 giây, nhưng worker tiếp tục 15 giây và commit: nếu client retry ở giây 4, **idempotency** phải chặn duplicate. Hủy được hay không còn tùy handler, transport, interruption và transaction state; **không có automatic cancellation xuyên toàn flow**.

Lựa chọn contract:

1. **Truy vấn ngắn, read-only**: đồng bộ với reply timeout, cho phép retry theo read semantics.
2. **Command ngắn, có side effect**: đồng bộ nếu hệ thống thực sự đảm bảo response trong SLA và có idempotency.
3. **Command dài, có fan-out**: trả `ACCEPTED/PENDING` sau khi durable intent được lưu; cung cấp status endpoint/event callback.

Không tạo `OrderResult(status="SUCCESS")` chỉ vì Gateway đã nhận ACK từ queue hoặc task được đưa vào ExecutorChannel.

## 17. Exception có thể được truyền qua Gateway như thế nào?

Với flow đồng bộ:

~~~text
Application → Gateway → DirectChannel → Service Activator
                                      ↘ throws InvalidOrderException
Application ← exception / wrapper
~~~

Khi exception lan về caller, API layer có thể:

- Map **validation/authorization/business permanent errors** thành phản hồi cụ thể.
- Map **temporary DB/network failures** thành lỗi có thể retry theo policy.
- Giữ **unknown outcome** của remote side effect ở trạng thái cần reconcile.
- Giữ cause chain cho logs bảo vệ, không trả raw stack trace.

Spring có thể bọc lỗi thành các dạng `MessagingException`, `MessageHandlingException` hoặc exception khác tùy endpoint. Đừng gắn logic application vào **nguyên văn message của exception**; ưu tiên exception typed/reasonCode và kiểm tra cause chain.

Với flow async, lỗi ném **sau khi caller send trả về** thường đi theo error channel/container recoverer, không tự “dịch chuyển ngược thời gian” để ném trực tiếp vào caller. Cần thiết kế **error reply** hoặc status có chủ đích.

## 18. Error channel không đồng nghĩa error reply

Hai đường xử lý phải phân biệt:

~~~text
Đường A: Gateway request ─→ Service Activator ─→ reply

Đường B: Gateway request ─→ async handler throws
                           └→ ErrorMessage → errorChannel → recoverer
~~~

Một `ErrorMessage` là message chứa `Throwable`; nó có thể tới channel được xác định bởi source/poller/adapter/header hoặc cấu hình hệ thống. **Chỉ có ErrorMessage trong một monitoring channel không có nghĩa caller nhận được một business error response.**

Nếu caller yêu cầu reply:

- Với exception đồng bộ, cho phép exception lan về Gateway và map tại application boundary.
- Với async flow, xây error response **đúng correlation/reply-to protocol** nếu reply còn khả thi.
- Nếu caller đã timeout, lưu **durable terminal outcome** để client truy vấn/reconcile.
- Nếu Gateway chỉ có one-way contract, error channel xử lý recovery mà không giả vờ có reply.

**Cần tránh vòng lặp:** error handler ném lại exception vào cùng error channel không có recoverer có thể làm che lỗi ban đầu. Recovery logic phải có owner, retry budget và endpoint semantics.

## 19. Missing reply và Filter: một lỗi input có thể bị biến thành timeout

Flow sai:

~~~text
Gateway.quote(request)
   → Filter.isValid(request) == false
   → discard im lặng
   → Gateway đợi reply cho đến timeout
~~~

Caller nhận timeout và tưởng network chậm, dù input `quantity=-1` sẽ không bao giờ hợp lệ.

Các lựa chọn rõ ràng:

1. **Fail-fast:** Filter bật `throwExceptionOnRejection(true)` rồi API mapper chuyển thành validation error có reasonCode.
2. **Typed decision:** Validation service trả `QuoteRejected(reasonCode)` hoặc `QuoteAccepted(result)` trên **cùng request–reply contract**.
3. **Quarantine:** Với broker ingestion không cần reply, đưa input malformed vào durable rejection flow.

**Một discard channel không tự tạo typed reply.** Nếu muốn trả lỗi từ discard flow, phải đảm bảo message đến đúng request reply address hoặc có bước xử lý reply có cấu trúc; điều này phức tạp khi request đã timeout hoặc replyChannel bị mất qua broker.

## 20. Typed result: phân biệt accepted, rejected, pending

Thay vì buộc mọi kết quả vào `PlaceOrderResult(status="SUCCESS")`, có thể dùng sealed interface Java 17:

~~~java
sealed interface PlaceOrderDecision
    permits OrderPlaced, OrderRejected, OrderPending {}

record OrderPlaced(
    String orderId,
    String commandId
) implements PlaceOrderDecision {}

record OrderRejected(
    String commandId,
    String reasonCode
) implements PlaceOrderDecision {}

record OrderPending(
    String commandId,
    String statusReference
) implements PlaceOrderDecision {}
~~~

Gateway contract:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.decide")
interface OrderDecisionGateway {
    PlaceOrderDecision place(PlaceOrderCommand command);
}
~~~

Ý nghĩa:

- `OrderPlaced`: operation đã đạt mốc success **được định nghĩa trong contract**.
- `OrderRejected`: business/validation terminal rejection, **không cần retry cùng payload**.
- `OrderPending`: durable accepted nhưng chưa thể kết luận final outcome; caller có status reference.

Đây là **kiểu ứng dụng tự thiết kế**, không phải Spring Integration tự sinh các lớp trên từ annotation. Flow phải thực sự tạo reply đúng kiểu, và nếu một message bị discard hoặc error channel chỉ ghi logs thì Gateway vẫn không có `PlaceOrderDecision` để trả.

## 21. Boundary ghi dữ liệu: transaction thuộc handler, không thuộc interface Gateway

Một Gateway interface không tự tạo transaction bền vững:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.place.requests")
interface PlaceOrderGateway {
    PlaceOrderDecision place(PlaceOrderCommand command);
}
~~~

Ranh giới transaction đúng thường nằm trong **service bean thực thi command**:

~~~java
@Service
class PlaceOrderService {
    private final CommandInbox inbox;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    PlaceOrderService(
            CommandInbox inbox,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.inbox = inbox;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public PlaceOrderDecision execute(PlaceOrderCommand command) {
        validateAndAuthorize(command);
        String key = command.tenantId() + ":" + command.commandId();
        boolean first = inbox.claimIfAbsent(key, command);
        if (!first) {
            inbox.assertSameFingerprint(key, command);
            return inbox.loadCommittedDecision(key);
        }
        OrderPlaced result = orders.place(command);
        outbox.recordOrderPlaced(command, result);
        inbox.saveDecision(key, result);
        return result;
    }

    private void validateAndAuthorize(PlaceOrderCommand command) {
        // Trusted tenant, request validation, operation authorization.
    }
}
~~~

`CommandInbox`, `OrderRepository` và `OutboxRepository` là **application interfaces**, không có sẵn trong Spring Integration. Dữ liệu cần có unique constraint và transaction manager thật. Lưu ý key ghép chuỗi ở đây là minh họa: production cần encoded/composite key không nhập nhằng, có tenant/operation scope và payload fingerprint.

**Nếu mọi repository cùng database transaction**, lỗi trước COMMIT rollback cả inbox, order và outbox. Redelivery sau COMMIT có thể đọc decision đã lưu và không tạo order lần hai. Nhưng `@Transactional` không tự rollback một HTTP payment đã commit, một Redis marker ngoài transaction hoặc một publish đến broker khác.

## 22. Gateway không làm một lệnh có side effect trở thành exactly-once

Timeline:

~~~text
T1 Application gọi gateway.place(commandId=C-901).
T2 Flow đưa command vào Service Activator.
T3 Database COMMIT order + inbox + outbox.
T4 Caller timeout hoặc process crash trước nhận reply.
T5 Caller retry cùng logical operation.
T6 Gateway lại gửi một message.
~~~

**Gateway có thể gửi lại request, nhưng domain effect không được lặp.** Kết hợp:

- Stable `commandId` trong domain contract.
- Transactional inbox/processed record với unique constraint.
- Payload fingerprint để nhận diện cùng key nhưng content khác.
- Cached result hoặc durable status cho duplicate completed.
- Transactional outbox nếu cần publish sau commit.
- Remote idempotency key và reconciliation nếu có external payment/HTTP mutation.

Không dùng `MessageHeaders.ID`, `replyChannel` hoặc attempt-specific UUID làm idempotency key. Mỗi retry có thể tạo Spring message mới nhưng phải đại diện **cùng logical command**.

## 23. Transaction context qua async boundary

Ví dụ:

~~~text
Caller thread:
  @Transactional CheckoutUseCase.place()
    → Gateway
    → ExecutorChannel.enqueue()
    → return

Worker thread:
  ServiceActivator.place()
    → database writes
~~~

Transaction local gắn với caller thread **không mặc nhiên đi theo** task sang worker thread. Nếu worker cần transaction, mở transaction **trong service thực sự chạy ở worker**, dưới một transaction manager phù hợp.

**Đừng đặt `@Transactional` trên Gateway caller rồi cho rằng database writes trong queue/broker transaction chung với caller.** Ngay cả với flow đồng bộ, khi có nhiều resources hoặc remote calls, vẫn cần biết transaction manager bao trùm thao tác nào.

Một phương án vững hơn cho asynchronous command:

~~~text
Caller → Gateway → durable command inbox/queue
        ← OrderPending(commandId, statusRef)

Worker → claim → business commit + outbox
       → durable status SUCCEEDED/FAILED

Caller → query status / consume completion event
~~~

OrderPending phải được trả sau khi **đã lưu durable intent**, không phải sau khi chỉ gọi `executor.submit()` trong memory.

## 24. External API request–reply: outbound gateway khác outbound adapter

Giả sử flow cần lấy thuế từ một HTTP service:

~~~text
QuoteGateway.quote()
  → local request channel
  → HTTP outbound gateway: GET tax estimate
  ← HTTP response
  → Transformer
  → QuoteResult reply
~~~

**Outbound gateway** thích hợp khi cần **request–reply** với hệ thống ngoài. **Outbound channel adapter** thường có contract **one-way**: gửi message ra ngoài, không trả business reply theo kiểu Gateway.

Đừng ép một outbound adapter one-way vào request–reply rồi cho rằng ACK send là câu trả lời nghiệp vụ từ remote. Với broker, cần xem giao thức request–reply, reply-to destination, correlation và timeout; không phải transport nào cũng hỗ trợ cùng một mô hình.

Khi outbound gateway timeout, phân loại:

| Operation remote | Retry có an toàn? |
|---|---|
| GET/lookup thuần, idempotent | Có thể retry bounded |
| POST tạo charge/payment | Chỉ khi có remote idempotency/reconciliation |
| Tra cứu tình trạng order | Thường có thể retry, tùy side effects và rate limit |
| Gửi email | Có thể đã gửi dù response mất; cần message/provider idempotency |

Gateway boundary che cách gọi external service, **không tự suy ra** một thao tác là idempotent.

## 25. Inbound gateway và public API boundary

Một **HTTP inbound gateway** của Spring Integration nhận request HTTP và phát message vào flow rồi chờ reply để trả HTTP response. Nó là lựa chọn thay controller gọi `@MessagingGateway`:

~~~text
Option A:
HTTP Controller
  → Java @MessagingGateway interface
  → IntegrationFlow

Option B:
Spring Integration HTTP inbound gateway
  → IntegrationFlow
  → HTTP response
~~~

Điểm chung: cần decode, authenticate, validate, HTTP status mapping, timeout/error policy. Điểm khác: Option A có **application Java port** rõ cho nhiều callers (controller, scheduled job, service); Option B đặt inbound messaging boundary gần transport.

**Không bắt buộc dùng cả hai.** Chọn topology theo yêu cầu tái sử dụng application use cases, cách tổ chức security/validation và kinh nghiệm vận hành. Nếu chọn inbound gateway, đừng nghĩ authentication/authorization tự có chỉ vì endpoint là Spring Integration.

## 26. Correlation khi flow tách, phân nhánh và gom kết quả

Ví dụ báo giá cần ba service:

~~~text
QuoteGateway.quote(Q-901)
  → Splitter:
       PriceTask #1
       DiscountTask #2
       TaxTask #3
  → workers xử lý song song
  → Aggregator
  → QuoteResult
  → Gateway reply
~~~

~~~mermaid
flowchart TD
    G["Gateway request Q-901"] --> SPLIT["Splitter: 3 tasks"]
    SPLIT --> P["Pricing"]
    SPLIT --> D["Discount"]
    SPLIT --> T["Tax"]
    P --> A["Aggregator"]
    D --> A
    T --> A
    A --> R["QuoteResult"]
    R --> G
~~~

Để Gateway nhận **một reply đúng request**, cần:

- **Parent business correlation** duy nhất theo tenant/request/revision khi phù hợp.
- **Member IDs/sequence metadata** để Aggregator biết có đủ kết quả.
- Xử lý duplicate child không làm đủ count giả.
- Release strategy so với expected member manifest nếu cần.
- Output Processor trả đúng kiểu `QuoteResult`.
- Reply channel/return address còn hợp lệ hoặc giao thức external request–reply có correlation bền.

**Correlation ID của Aggregator khác Gateway reply address.** Một request có thể tạo nhiều child messages cùng group; return address là nơi trả **kết quả cuối**, không phải định danh nhóm nghiệp vụ.

## 27. Một child lỗi không được biến thành Gateway timeout vô nghĩa

Trường hợp:

~~~text
QuoteGateway.quote(Q-901)
  → PriceTask success
  → DiscountTask success
  → TaxTask invalid payload / HTTP 503
  → Aggregator chỉ có 2/3 outcomes
  → Gateway reply timeout
~~~

Đây là failure mode quan trọng: lỗi một child có thể **trông như lỗi Gateway** dù Gateway hoạt động đúng. Cần phân biệt:

1. **Permanent child error**: phát một `TaskOutcome(failed, reasonCode)` giữ đúng parent correlation + member ID, nếu contract cho phép tổng hợp partial/failure.
2. **Transient child error**: retry bounded tại worker; khi hết budget, durable failure outcome hoặc workflow recovery rõ.
3. **Group expiry**: không tự coi partial group là success; định nghĩa timeout/release/cleanup policy.
4. **Gateway timeout trước group completion**: caller nhận pending/timeout, nhưng group/worker có thể còn chạy; lưu durable result và late reply policy.

**Không giảm `sequenceSize` từ 3 xuống 2 chỉ để release.** Một `TaxTask` lỗi là thông tin nghiệp vụ cần được phản ánh hoặc làm thất bại toàn request, không được âm thầm bỏ khỏi tổng.

## 28. Gateway được đặt ở đâu trong một ứng dụng nhiều lớp?

Một cấu trúc dễ kiểm soát:

~~~text
Presentation
  └── OrderController
Application
  ├── CheckoutUseCase
  ├── OrderApplicationPort (interface)
  └── DTO/decision contracts
Integration adapter
  ├── SpringOrderMessagingGateway (proxy/adapter)
  └── IntegrationFlows
Domain + infrastructure
  ├── QuoteCalculator
  ├── PlaceOrderService
  ├── Repository/Outbox
  └── Remote gateway adapters
~~~

Đây là cách **tổ chức trách nhiệm**, không phải yêu cầu một cấu trúc package duy nhất. Có hai lựa chọn:

- Application inject trực tiếp `@MessagingGateway` interface khi bạn chấp nhận Spring Integration annotation tại boundary interface.
- Application chỉ inject `OrderApplicationPort` thuần Java, một adapter bên dưới ủy quyền vào Spring Integration Gateway để giữ application layer không phụ thuộc framework.

Nếu bạn muốn domain độc lập hoàn toàn, đừng để `Message<?>`, `ErrorMessage` hoặc `MessagingException` lọt vào domain method signatures. Dịch thành typed result/exception ứng dụng tại adapter boundary.

**Boundary không loại bỏ nhu cầu observability.** Khi application debug, cần biết request nào đi vào flow nào; nên dùng tracing/structured logs do integration adapter tạo, không bắt controller tự set Spring-specific headers.

## 29. Thiết kế adapter thuần Java bao một gateway proxy

Ví dụ giữ Spring annotation ngoài application port:

~~~java
public interface OrderApplicationPort {
    QuoteResult quote(QuoteRequest request);
}

@MessagingGateway(
    defaultRequestChannel = "orders.quote.requests")
interface SpringQuoteMessagingGateway {
    QuoteResult quote(QuoteRequest request);
}

@Component
class OrderApplicationAdapter implements OrderApplicationPort {
    private final SpringQuoteMessagingGateway gateway;

    OrderApplicationAdapter(SpringQuoteMessagingGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public QuoteResult quote(QuoteRequest request) {
        return gateway.quote(request);
    }
}
~~~

Caller chỉ thấy `OrderApplicationPort`:

~~~java
@Service
class CheckoutApplicationService {
    private final OrderApplicationPort orders;

    CheckoutApplicationService(OrderApplicationPort orders) {
        this.orders = orders;
    }

    QuoteResult preview(QuoteRequest query) {
        return orders.quote(query);
    }
}
~~~

**Giá trị:** Unit test application code có thể fake `OrderApplicationPort`, không cần khởi tạo Spring Integration context. Integration test adapter/flow là một tầng khác.

Nếu chỉ có một flow nhỏ trong một Spring-centric project, lớp adapter thêm này có thể không cần thiết. Quan trọng là **boundary nhất quán**, không phải tạo lớp trung gian chỉ vì khuôn mẫu.

## 30. Unit test application code không cần Spring Integration

JUnit 5 + một fake port:

~~~java
@Test
void checkoutUseCaseUsesTypedPortWithoutChannels() {
    OrderApplicationPort fakePort = request ->
        new QuoteResult(
            request.productId(),
            new BigDecimal("25.00"),
            "USD");

    CheckoutApplicationService useCase =
        new CheckoutApplicationService(fakePort);

    QuoteResult reply = useCase.preview(
        new QuoteRequest("tenant-a", "SKU-9", 2));

    assertEquals("SKU-9", reply.productId());
    assertEquals(
        0,
        new BigDecimal("25.00").compareTo(reply.total()));
}
~~~

**Đây là unit test của application boundary**, không kiểm tra request channel/Transformer/Service Activator. Nó chứng minh caller **chỉ phụ thuộc hợp đồng method và DTO**, chứ không phải `MessageBuilder`, `@Header` hay `QueueChannel`.

Thử đổi triển khai `OrderApplicationPort` sang fake HTTP adapter hoặc in-memory service; application use case vẫn compile và có cùng business semantics nếu contract giữ nguyên.

## 31. Integration test cho Gateway proxy qua một flow thực

Test Spring context:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
class QuoteGatewayTestConfig {

    @Bean
    QuoteCalculator calculator() {
        return new QuoteCalculator();
    }

    @Bean
    IntegrationFlow quoteTestFlow(QuoteCalculator calculator) {
        return IntegrationFlow
            .from("orders.quote.requests")
            .handle(
                QuoteRequest.class,
                (request, headers) ->
                    calculator.calculate(request))
            .get();
    }
}
~~~

Nếu test class nằm trong phạm vi component scan phù hợp:

~~~java
@Autowired
QuoteGateway quoteGateway;

@Test
void gatewayReturnsTypedReplyFromFlow() {
    QuoteResult result = quoteGateway.quote(
        new QuoteRequest("tenant-a", "SKU-9", 2));

    assertNotNull(result);
    assertEquals("SKU-9", result.productId());
    assertEquals(
        0,
        result.total().compareTo(new BigDecimal("25.00")));
}
~~~

Trong snippet này, `QuoteCalculator` dùng unit price 12.50 nên quantity 2 cho tổng 25.00. Các imports/bootstrapping của JUnit/Spring test được lược bỏ; cần setup `@SpringJUnitConfig` hoặc equivalent và đảm bảo **gateway interface được scan**. Nếu project đã có `QuoteCalculator` bean, không đăng ký duplicate bean trong test.

**Kiểm tra test context thực:** Không có một endpoint production khác cùng consume `orders.quote.requests`. Với shared channel và nhiều consumers, kết quả test có thể không ổn định hoặc sai về mặt dispatch.

## 32. Test request–reply không nhận nhầm kết quả khi concurrent

Hai callers:

~~~text
Caller A: quote(Q-A, product=SKU-A)
Caller B: quote(Q-B, product=SKU-B)

Flow:
  Q-B xử lý trước
  Q-A xử lý sau

Expected:
  A nhận QuoteResult của SKU-A
  B nhận QuoteResult của SKU-B
~~~

Test:

1. Dùng một executor/test barrier để kiểm soát thứ tự completion.
2. Gửi đồng thời hai requests với **unique logical request IDs** nếu contract cần.
3. Đảo thứ tự trả replies.
4. Assert mỗi caller nhận đúng product/request.
5. Test timeout của một request không ảnh hưởng reply của request khác.
6. Khi external broker, kiểm tra correlation mapper/reply-to destination đúng.

**Không dùng một `QueueChannel` chia sẻ do caller tự tạo rồi `receive()` theo thứ tự như bằng chứng Gateway correlation an toàn.** Nếu hai callers lấy ngẫu nhiên từ một queue, họ có thể nhận reply của nhau. Gateway/protocol correlation cần đúng ở tầng request–reply adapter.

## 33. Test Gateway timeout mà downstream vẫn commit

Fault injection:

~~~text
T0 Gateway.place(C-901)
T1 Handler bắt đầu
T2 Caller reply timeout
T3 Handler COMMIT order
T4 Reply đến muộn, caller không còn đợi
T5 Caller query status(C-901) → SUCCEEDED
T6 Caller retry C-901 → cùng committed receipt, không order thứ hai
~~~

Một integration test nên assert:

- Gateway nhận timeout/response pending theo contract, **không tự khẳng định FAILED**.
- Domain state có thể chuyển SUCCEEDED sau timeout.
- Retry với **cùng commandId** không tạo business side effect mới.
- Late reply không kích hoạt thêm một lần gọi `place()`.
- Có thể tra cứu durable outcome theo commandId.

**Cẩn thận với test timing:** `Thread.sleep()` ngẫu nhiên dễ flaky. Dùng `CountDownLatch` hoặc test barrier để giữ handler tại đúng điểm, kích hoạt timeout có chủ đích, rồi cho handler commit. Không cần thay đổi production code để test nếu có mock clock, injected executor hoặc điều khiển test fixtures phù hợp.

## 34. Test một Gateway request sai không timeout vô nghĩa

Nếu quantity phải dương, request:

~~~java
new QuoteRequest("tenant-a", "SKU-9", -1);
~~~

nên được **từ chối có nghĩa**, không biến thành “service timeout”.

Hai cách test:

| Cấu hình | Assertion |
|---|---|
| Handler ném typed invalid request | Gateway/caller nhận exception có mã `INVALID_QUANTITY` hoặc wrapper có cause tương ứng |
| Flow tạo typed `QuoteRejected` | Gateway trả decision/result phù hợp |
| Filter discard im lặng | Test phát hiện lỗi thiết kế do reply thiếu/timeout |

Với ví dụ `QuoteCalculator` ở mục 6, lỗi hiện dùng `IllegalArgumentException("INVALID_QUANTITY")` chỉ nhằm minh họa. Production nên có **exception typed/reasonCode** và mapping rõ giữa application boundary, HTTP response, log và broker recovery.

Không bật retry policy cho mọi `IllegalArgumentException` rồi kỳ vọng quantity âm trở thành hợp lệ ở lần thử tiếp theo.

## 35. Test lỗi async không bị nhận nhầm thành lỗi đồng bộ

Một flow:

~~~text
Gateway → ExecutorChannel → Service Activator
                         → throws on worker
                         → ErrorMessage / recoverer
~~~

Test nên xác minh:

- Exception xuất hiện trên worker/error boundary theo cấu hình.
- Không giả định `gatewayMethod()` ném trực tiếp cause từ worker nếu không có error reply.
- Nếu Gateway có reply timeout, nó sẽ thực thi contract timeout/pending tương ứng.
- Error handler giữ logical request ID/correlation để query status hoặc gửi compensating outcome.
- Không ACK một command có side effect chưa durable chỉ vì executor nhận task.

**Exception path trong `DirectChannel` không giống `ExecutorChannel`.** Một test chỉ kiểm tra synchronous flow chưa đủ để chứng minh được error channel, transaction context và retry semantics của async flow.

## 36. Test mất header qua broker và bảo toàn identity

Giả sử một Transformer xây lại message hoặc broker adapter không map custom headers. Một test contract cần đảm bảo:

~~~text
commandId=C-901 (payload)
tenantId=verified tenant context
businessCorrelationId=tenant-a|O-901
reply-to=transport-defined return destination
~~~

Nếu mất `replyChannel` JVM object khi message vượt process boundary, điều đó không có nghĩa flow mất luôn khả năng trả reply: **outbound/inbound gateway theo giao thức phải ánh xạ reply-to/correlation** đúng. Nhưng nếu chỉ gửi bare payload qua broker mà không có protocol, caller sẽ timeout.

Kiểm tra:

1. Headers được phép serialize, có whitelist.
2. Logical command ID vẫn ổn định qua retry/rebuild.
3. Reply được correlate đúng request, không chỉ theo productId/orderId không scoped.
4. Invalid header/tenant claim bị reject.
5. Late reply có đường cleanup, không tạo leak trong pending-reply registry.
6. ID của Spring message mới **không thay** business idempotency key.

Không truyền nguyên `replyChannel`/`errorChannel` objects qua external trust boundary như một yêu cầu tương thích bắt buộc.

## 37. Security boundary: chống gọi lệnh ghi qua một gateway công khai

Một application Gateway method `place()` là một cổng có side effect. Những rủi ro:

- HTTP caller giả tenant hoặc role.
- Broker producer gửi nhầm operation qua channel đã cho phép.
- Header nội bộ `verifiedTenantId` bị client tự khai.
- Router chọn flow theo method name/SpEL do input tự cung cấp.
- Một message gửi đến service khác mang `replyChannel`/`errorChannel` giả.
- Logs/error replies vô tình chứa raw payment/PII.

Biện pháp:

- Xác thực ở adapter ingress.
- Domain authorization tại service xử lý command.
- Chỉ route qua **allowlist operation/channel**, không arbitrary reflection.
- Giữ token/credentials ngoài DTO business khi không cần, tránh log.
- Xác thực lại identity khi qua broker/service boundary.
- Đặt quotas, max payload, timeout và allowed schema versions.

**Không dùng `@MessagingGateway` như một security mechanism.** Annotation chỉ khai báo cách vào message flow; nó không quyết định ai được phép gọi `place()`.

## 38. Observability: Gateway call khác business completion

Để phân biệt proxy hoạt động và nghiệp vụ hoàn tất, có thể theo dõi:

| Metric gợi ý | Ý nghĩa |
|---|---|
| `gateway.requests.count` | Số caller invocations |
| `gateway.request.send.failure.count` | Không gửi được request |
| `gateway.reply.received.count` | Replies đúng contract |
| `gateway.reply.timeout.count` | Requests không có reply trong deadline |
| `gateway.reply.late.count` | Replies đến sau caller timeout |
| `gateway.error.received.count` | Errors được map tới caller |
| `gateway.calls.duration` | Caller-visible latency |
| `flow.command.accepted.count` | Durable accepted intents |
| `flow.command.committed.count` | Business commits |
| `flow.command.duplicate.count` | Logical duplicates |
| `flow.command.unknown.outcome.count` | Remote status chưa xác minh |
| `flow.aggregate.pending.count` | Groups đang đợi children |
| `flow.aggregate.expired.count` | Groups hết hạn |
| `flow.outbox.pending.count` | Events chờ publish |

Đây là **metric đề xuất**, không phải danh sách meter mặc định Spring Integration. Tag phải có cardinality thấp như `gatewayMethod`, `flowName`, `outcome`, `reasonCode` và `operation`. **Không đặt commandId, eventId, traceId, email hoặc raw payload thành metric labels.**

Structured log/tracing được giới hạn quyền:

~~~text
gatewayMethod=place
commandId=C-901
operation=PLACE
requestAccepted=true
replyOutcome=TIMEOUT
businessOutcome=PENDING
correlationId=tenant-a|O-901
elapsedMillis=3000
~~~

Khi operation hoàn tất sau đó, một log/event khác:

~~~text
commandId=C-901
businessOutcome=SUCCEEDED
transactionOutcome=COMMITTED
replayedMessage=false
~~~

**Đừng phát metric “order failed” mỗi khi Gateway reply timeout.** Timeout là trạng thái caller chưa nhận response trong deadline, không chứng minh domain operation đã thất bại.

## 39. Method arguments và headers: chỉ đưa metadata cần thiết qua boundary

Gateway có thể ánh xạ payload và một số method arguments vào headers. Ví dụ minh họa:

~~~java
@MessagingGateway
interface TenantQuoteGateway {

    @Gateway(requestChannel = "orders.quote.requests")
    QuoteResult quote(
        @Payload QuoteRequest request,
        @Header("sourceApp") String sourceApp);
}
~~~

`@Payload` xác định payload; `@Header` gắn một metadata field cho message. Nhưng **chỉ có header không chứng minh giá trị đó đáng tin**. Nếu application caller là một HTTP controller, nó phải xác minh `sourceApp` hoặc tạo thông tin này từ identity đã xác thực thay vì chép nguyên header từ HTTP client.

Một nguyên tắc thực dụng:

- Đặt **business required IDs** trong DTO/wire contract nếu cần tồn tại qua broker hoặc restart.
- Đặt **transient technical context** như tracing hint, source application vào headers đã whitelist.
- Đừng đưa framework `replyChannel`/`errorChannel` vào domain DTO.
- Không truyền raw security token trong header có thể bị copy tới nhiều services.
- Khi service cần authorization, lấy verified identity có nguồn gốc rõ ở trust boundary.

Nếu interface có quá nhiều `@Header` technical arguments, hãy cân nhắc một **adapter** giữ framework details và chỉ cung cấp một method business-friendly cho application code.

## 40. Khi nào nên dùng Messaging Gateway, khi nào chỉ gửi message?

| Mục tiêu | Lựa chọn thường phù hợp |
|---|---|
Java application cần gọi flow và nhận typed result | `@MessagingGateway` request–reply |
| Java application cần phát event one-way | Gateway `void` hoặc adapter gửi channel, với durable delivery policy |
| External HTTP client gọi API | Controller + Gateway hoặc HTTP inbound gateway |
| Flow gọi external HTTP và chờ response | HTTP outbound gateway |
| Flow publish event lên broker không cần response nghiệp vụ | Outbound channel adapter / publisher |
| Công việc kéo dài hàng phút | Durable command queue + status/events, không ép synchronous reply |
| Flow có Splitter/Aggregator tạo một kết quả tổng | Gateway với correlation/release/deadline rõ |
| Batch processor đơn giản chỉ gửi vào flow | Có thể dùng `MessageChannel` tại integration adapter, không cần Gateway proxy nếu không mang lợi ích |

**Gateway không phải lúc nào cũng cần thiết.** Nếu một application port đã đủ đơn giản và không có message flow thật sự, gọi trực tiếp business service có thể rõ ràng hơn. Đừng ép business code qua Gateway chỉ để thêm số lượng endpoints.

Ngược lại, khi flow có Router, Transformer, error channel và adapters, Gateway giúp application caller **không phụ thuộc vào topology** và làm kiểm thử/application contracts rõ ràng hơn.

## 41. Contract evolution: giữ port ổn định khi flow thay đổi

Giả sử ban đầu:

~~~text
QuoteGateway.quote()
  → QuoteCalculator
  → QuoteResult
~~~

Sau đó mở rộng:

~~~text
QuoteGateway.quote()
  → validate
  → enrich product catalog
  → route regional pricing
  → split price/discount/tax
  → aggregate
  → QuoteResult
~~~

Nếu cùng **input/output semantics và latency contract** được giữ, application code có thể không cần đổi. Đây là ích lợi của một boundary tốt.

Tuy nhiên, có những thay đổi không nên che:

- Flow mới mất 30 giây thay vì 30 ms.
- Result bây giờ chỉ là `PENDING` thay vì giá cuối.
- Currency semantics thay đổi từ gross sang net.
- Gateway trước đây read-only nay có side effect.
- Method bắt đầu ném một nhóm failure mới cần caller xử lý.
- Command được chấp nhận durable nhưng final completion chuyển sang event callback.

Đó là **thay đổi application contract**. Hãy version hóa DTO/API và rollout có chủ đích, không chỉ sửa flow rồi tin rằng annotation Gateway làm mọi thứ tương thích.

## 42. Runbook: Gateway timeout nhưng không biết nghiệp vụ đã hoàn tất chưa

Một quy trình điều tra:

1. **Xác định method và operation:** `quote()` (read-only) hay `place()` (side effect)?
2. **Xác định logical ID:** commandId, tenant, orderId và request/correlation scope.
3. **Kiểm tra request send:** message đã vào request channel/queue chưa, có bị capacity/timeout không?
4. **Kiểm tra flow:** Filter có discard, Router có nhầm nhánh, Transformer có lỗi?
5. **Kiểm tra Service Activator:** handler có bắt đầu, kết thúc, commit hay throw?
6. **Kiểm tra transaction:** inbox, domain row và outbox có cùng commit không?
7. **Kiểm tra error boundary:** exception lan về caller hay vào error channel/container?
8. **Kiểm tra reply correlation:** return address còn hợp lệ, reply-to đúng, reply có đến muộn không?
9. **Kiểm tra Splitter/Aggregator:** có child thiếu, duplicate member hoặc group expire không?
10. **Kiểm tra external service:** timeout có thể là remote outcome chưa biết?
11. **Đối chiếu durable outcome:** operation SUCCEEDED, FAILED, PENDING hay UNKNOWN_OUTCOME?
12. **Quyết định retry:** giữ **cùng commandId** cho cùng logical work; reconcile trước nếu remote effect không rõ.
13. **Khắc phục và hồi quy:** bổ sung fault-injection test đúng cửa sổ lỗi, metrics và status reply policy.

**Không tự xóa idempotency marker rồi replay hàng loạt** khi chưa kiểm tra side effects đã commit. Một lỗi reply từ Gateway không chứng minh handler không thành công.

## 43. Ma trận kiểm thử end-to-end cho Gateway boundary

| Tình huống | Fault/input | Kỳ vọng |
|---|---|---|
| Typed query | `QuoteRequest` hợp lệ | `QuoteResult` đúng loại/giá trị |
| Typed command | `PlaceOrderCommand` hợp lệ | `OrderPlaced` hoặc decision đúng |
| Wrong payload type | Schema không tương thích | Reject, không gọi nhầm handler |
| Missing required field | `quantity=-1` | Validation error, không timeout im lặng |
| Filter discard | Predicate false | Phát hiện thiếu error reply nếu contract cần |
| Gateway request cannot send | Queue capacity/dispatch failure | Lỗi gửi rõ, không báo business success |
| Gateway no reply | Handler trả void/null hoặc child drop | Reply timeout theo contract |
| Synchronous handler error | Exception trên DirectChannel | Cause/reasonCode tới caller |
| Asynchronous handler error | Exception trên ExecutorChannel | Error channel/recoverer và durable status đúng |
| Two concurrent requests | Replies đảo thứ tự | Caller nhận đúng reply |
| Broker header mapping | Reply-to/correlation được chuyển | Không lẫn reply hoặc mất metadata |
| Caller timeout before commit | Worker còn chạy | Không báo chắc chắn failure |
| Retry same command | Cùng commandId và fingerprint | Không double business effect |
| Same ID, changed payload | Fingerprint mismatch | Conflict/reject |
| Crash after commit before reply | Redelivery/retry | Cached result, không tạo order lần hai |
| Remote HTTP timeout after commit | Outcome unknown | Reconcile/cùng remote key |
| Splitter child missing | Aggregator thiếu member | Failure/timeout/pending đúng, không partial success giả |
| Duplicate child outcome | Hai replies của một member | Không đạt expected count giả |
| Late reply | Caller đã timeout | Không kích hoạt side effect mới |
| DLQ/recovery unavailable | Không persist được failed command | Không ACK làm mất công việc |
| Unauthorized tenant | Header/payload giả mạo | Reject trước business write |
| Schema evolution | Flow mới nhưng contract giữ nguyên | Caller không cần sửa |
| Breaking contract | Result đổi sang async pending | API migration có chủ đích |

**Đừng chỉ assert `Gateway.quote()` trả object.** Với command, kiểm tra **database row counts, outbox records, external-provider call counts, status transition và retry duplicate behavior**. Với async, kiểm tra error channel/container recovery thực chứ không chỉ unit test Java method.

## 44. Những hiểu lầm thường gặp

**“Messaging Gateway chỉ là một tên khác của Service Activator.”** Không. Gateway cho code ứng dụng gọi vào flow; Service Activator gọi service từ message.

**“Có `@MessagingGateway` thì không cần validation/authorization.”** Sai. Annotation chỉ cấu hình messaging boundary, không cấp quyền hay chứng minh input hợp lệ.

**“Gateway trả object là đủ chứng minh transaction đã commit.”** Chỉ khi handler và contract thật sự bảo đảm mốc commit đó.

**“Reply timeout nghĩa là operation đã bị hủy.”** Không. Worker có thể tiếp tục và commit.

**“Timeout của Gateway là deadline cho mọi service trong flow.”** Không mặc nhiên. Request, reply, broker và business deadlines khác nhau.

**“Một `void` Gateway nghĩa là downstream side effect đã hoàn tất.”** Không với async queues/executors và delivery chưa durable.

**“Filter drop input thì Gateway tự tạo validation reply.”** Không. Caller có thể timeout.

**“ErrorMessage trong errorChannel tức là caller đã được thông báo.”** Không. Cần error reply hoặc status protocol.

**“Gateway sẽ tự retry mọi lỗi an toàn.”** Không. Retry policy phải xét side effect, idempotency và failure classification.

**“Mỗi lần retry tạo commandId mới để chắc chắn delivery.”** Ngược lại, có thể tạo duplicate business operation.

**“ReplyChannel là business correlation ID.”** Không. Nó là return address của invocation.

**“Spring Message ID bền qua broker redelivery.”** Không được giả định.

**“Có Splitter/Aggregator là Gateway luôn nhận một kết quả.”** Không nếu thiếu child/expire/duplicate và release policy sai.

**“Synchronous test bảo đảm async error handling hoạt động.”** Không. Thread/transaction/error boundaries khác.

**“JDBC transaction rollback một HTTP payment đã capture.”** Không. External side effect cần remote idempotency/reconciliation.

**“Inbound gateway và Java `@MessagingGateway` là cùng một endpoint.”** Không. Một cái là transport-facing adapter, một cái là application interface proxy.

**“Một gateway interface che được mọi breaking change phía sau.”** Không khi semantics, latency hay outcome contract đổi.

**“Đưa toàn bộ HTTP headers vào message sẽ giữ đủ context.”** Có thể lộ secrets và đưa untrusted values vào routing/authorization.

## 45. Bài thực hành: từ controller gọi channel sang application port

Xây mini project **CheckoutMessagingBoundary**:

1. Định nghĩa `QuoteRequest`, `QuoteResult` và `PlaceOrderCommand`, `PlaceOrderDecision`.
2. Tạo `QuoteGateway` với `@MessagingGateway(defaultRequestChannel=...)`.
3. Lắp flow `IntegrationFlow.from(...).handle(QuoteCalculator)` tạo typed reply.
4. Viết `CheckoutApplicationService` chỉ phụ thuộc một application port.
5. Test unit với fake port: **không cần Spring context hay MessageChannel**.
6. Test integration Gateway proxy: request chuyển tới đúng handler và return đúng DTO.
7. Thêm một Filter reject quantity âm; đảm bảo caller nhận lỗi có nghĩa, không chỉ reply timeout.
8. Tạo `PlaceOrderGateway` và handler transaction với inbox + order + outbox.
9. Test duplicate command và same key/different payload conflict.
10. Inject crash sau commit trước reply; retry cùng commandId không tạo order thứ hai.
11. Chèn `ExecutorChannel`; quan sát lỗi thuộc worker/error boundary, không phải caller thread.
12. Tạo một request fan-out 3 children qua Splitter/Aggregator.
13. Fault injection một child lỗi; định nghĩa failure outcome/group expiry rõ.
14. Test concurrent requests với replies đảo thứ tự và late reply.
15. Thêm HTTP controller hoặc HTTP inbound gateway, map validation/timeout thành HTTP response phù hợp.
16. Thử outbound gateway đọc dữ liệu external, mô phỏng HTTP 503 và timeout.
17. Ghi dashboard gateway timeout khác business committed/error metrics.
18. Thử thay topology nội bộ mà vẫn giữ API quote đồng bộ; ghi nhận chỗ cần versioning khi đổi sang pending async.

**Tiêu chí hoàn thành:** application code gọi **method + DTO** chứ không biết `replyChannel`, internal channels hoặc broker records; Gateway correlation không lẫn; timeout không bị hiểu là business failure chắc chắn; lệnh ghi có idempotency; lỗi sync/async được xử lý đúng; flow mới không làm vỡ caller contract khi semantics vẫn giữ nguyên.

## 46. Ghi nhớ

**Messaging Gateway là boundary giữa application code và message flow.** Nó cho phép controller/use case gọi **một Java interface có kiểu dữ liệu** trong khi Spring Integration chuyển request thành message, đưa qua Router/Filter/Transformer/Service Activator và đưa reply về caller. Gateway giúp **giảm coupling với topology**, không làm mất đi các quy tắc request–reply, error handling và business semantics.

Phân biệt **Java `@MessagingGateway` proxy** với **inbound/outbound gateways theo giao thức**. Giữ application port rõ theo **query, command và kết quả mong đợi**. Không nhầm `replyChannel` với business correlation, `MessageHeaders.ID` với idempotency key, hay Gateway timeout với transaction rollback.

Với request–reply phân tán hoặc fan-out, phải có **correlation, reply-to, deadline, retry/error channel và late-reply policy**. Với command có side effect, kết hợp **durable inbox, transaction, outbox, remote idempotency và reconciliation**. Kiểm thử tại cả application port, Spring Integration flow và transport boundary để Gateway thực sự tách ứng dụng khỏi messaging **mà không che giấu lỗi hoặc tạo side effect trùng**.

### Tài liệu tham khảo

- Enterprise Integration Patterns, **Messaging Gateway**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html
- Spring Integration Reference, **Messaging Gateways**: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference, **Service Activator**: https://docs.spring.io/spring-integration/reference/service-activator.html
- Spring Integration Reference, **HTTP Support**: https://docs.spring.io/spring-integration/reference/http.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Idempotent Receiver**: https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
- Spring Framework Reference, **Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
