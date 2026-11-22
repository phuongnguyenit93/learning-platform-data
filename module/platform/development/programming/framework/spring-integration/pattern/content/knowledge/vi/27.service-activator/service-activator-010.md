# Chọn method không gây side effect ngoài ý muốn

## 1. Bài toán: message đi đúng channel nhưng gọi sai hành vi

Một hệ thống xử lý đơn hàng có các phương thức cùng liên quan tới `Order`:

~~~java
class OrderOperations {
    OrderPreview preview(PreviewOrderQuery query) {
        // Tính phí dự kiến, không ghi dữ liệu.
        return calculatePreview(query);
    }

    OrderReceipt place(PlaceOrderCommand command) {
        // Ghi đơn hàng và phát event.
        return saveOrderAndPublish(command);
    }

    void cancel(CancelOrderCommand command) {
        // Huỷ đơn hàng.
        performCancellation(command);
    }
}
~~~

Nếu một Service Activator được cấu hình thiếu rõ ràng, thay đổi chữ ký, overload hoặc chuyển nhầm message, kết quả có thể là:

- Một request **chỉ muốn xem trước** nhưng lại **ghi đơn**.
- Retry cùng `PlaceOrderCommand` khiến hệ thống **trừ tồn kho hai lần**.
- Method trả `null` làm Gateway **chờ reply đến timeout**, dù handler đã tạo side effect.
- Một lỗi validation bị catch và trả success, khiến input chưa được xử lý nhưng broker đã ACK.
- Một message mang header giả bị dùng để chọn method có quyền ghi/hủy.

~~~mermaid
flowchart TD
    I["Message đầu vào"] --> SEL{"Chọn method để invoke"}
    SEL -->|"Tường minh, đúng command"| VALID["Validate & authorize"]
    SEL -->|"Nhầm method/loại payload"| WRONG["Side effect ngoài ý muốn"]
    VALID -->|"Hợp lệ"| TX["Business handler có transaction/idempotency"]
    VALID -->|"Không hợp lệ"| REJ["Reject có reasonCode"]
    TX --> RES["Reply / durable outcome"]
    WRONG --> INCIDENT["Double write / cancel nhầm / mất việc"]
~~~

**Service Activator** trong Enterprise Integration Patterns kết nối một **message** với **một method/service** thực thi xử lý. Trong Spring Integration, có thể cấu hình bằng `@ServiceActivator` hoặc Java DSL `.handle(...)`. **Chọn method** là chuyện **routing/invocation**, còn **không gây side effect ngoài ý muốn** đòi hỏi contract nghiệp vụ, validation, authorization, transaction, idempotency và error handling.

Bài thuộc chương **Service activator** trong module **SPRING_INTEGRATION_PATTERN**. Module hướng tới học Enterprise Integration Patterns bằng Spring Integration để xây dựng luồng message ít phụ thuộc, dễ mở rộng; thực hành **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và theo dõi các nhánh xử lý.

Sau bài này, bạn sẽ chọn handler tường minh, hiểu rủi ro overload và binding tham số, tách query khỏi command, giới hạn side effects, thiết kế retry/ACK an toàn và kiểm thử rằng một message không kích hoạt nhầm phương thức có tác động nghiệp vụ.

## 2. Service Activator thực sự làm gì?

Trong message flow:

~~~text
Inbound adapter
  → Channel
  → [Service Activator → method của ứng dụng]
  → Reply channel / bước tiếp theo
~~~

Một Service Activator:

1. Nhận message từ **input channel**.
2. Xác định **method/handler** được cấu hình.
3. Ánh xạ **payload, headers hoặc cả Message** thành tham số phù hợp.
4. Gọi logic ứng dụng.
5. Nếu có return value phù hợp, có thể phát **reply message**.
6. Nếu method ném exception, lỗi đi theo **boundary đồng bộ/bất đồng bộ** đang dùng.

Service Activator **không tự bảo đảm** method được gọi là read-only, có transaction hay idempotent. Việc method có `void`, trả một object hay ném exception là một phần của hợp đồng endpoint, không phải bằng chứng rằng nó an toàn.

Ví dụ một lệnh tạo đơn:

~~~text
Channel orders.place
   ↓
Service Activator: OrderCommandHandler.place(PlaceOrderCommand)
   ↓
Database transaction + outbox
   ↓
OrderReceipt
   ↓
orders.place.result
~~~

Ở đây channel và method có **một mục đích rõ ràng**. Không đặt cả `preview`, `place` và `cancel` vào một endpoint mà không có quy tắc chọn lệnh được kiểm soát.

## 3. “Không gây side effect ngoài ý muốn” không đồng nghĩa “không có side effect”

Một Service Activator dùng để gọi business service **có thể cần side effect hợp lệ**. Ví dụ:

- Ghi một đơn hàng được cho phép.
- Trừ tồn kho tương ứng một logical operation.
- Lưu audit record đã được kiểm soát.
- Ghi outbox event để phát sau commit.

Điều cần tránh là side effects **không nằm trong yêu cầu của message/contract**:

| Side effect | Có thể hợp lệ khi nào? | Bất thường khi nào? |
|---|---|---|
| INSERT order | `PlaceOrderCommand` hợp lệ, đã authorize | `PreviewOrderQuery` bị route vào place |
| UPDATE inventory | Operation được commit và idempotent | Cùng event retry làm trừ hai lần |
| Publish event | Có outbox/đã xác nhận outcome | Publish trước commit rồi transaction rollback |
| HTTP call thanh toán | Có quyền và idempotency key | Được gọi chỉ để validate input |
| Gửi email | Có business intent/consent | Một query read-only tự gửi thông báo |
| Ghi audit | Dữ liệu đã sanitize, có retention | Raw payload chứa PII bị log vô hạn |
| Xóa bản ghi | `CancelOrderCommand` được xác thực | Method bị chọn theo untrusted header |

**Mục tiêu thiết kế:** handler được chọn **đúng ý nghĩa message**, chỉ làm những hiệu ứng được phép, có thể xử lý lỗi/retry mà không nhân đôi các hiệu ứng đã commit.

## 4. Ba lớp phải đúng cùng lúc

Một endpoint an toàn cần cả ba:

| Lớp | Câu hỏi | Biện pháp |
|---|---|---|
| **Invocation correctness** | Message được ánh xạ vào đúng method? | Handler/method tường minh, payload type rõ, tránh overload mơ hồ |
| **Business correctness** | Method có quyền làm việc này không? | Validate command, tenant, operation, state, authorization |
| **Delivery correctness** | Retry, redelivery, crash có gây double effect hoặc mất việc? | Transaction, idempotency, outbox, ACK/DLQ/retry policy |

Chỉ khóa đúng method nhưng thiếu idempotency sẽ không tránh được double-write. Chỉ có transaction nhưng method bị route nhầm vẫn có thể **commit chính xác một hành vi sai**.

## 5. Đặt tên channel và handler theo operation

Không nên dùng một channel chung kiểu:

~~~text
orders.operations
  → OrderService (method được đoán từ payload/header)
~~~

trong khi người đọc không biết nó chỉ có thể gọi những operations nào.

Một topology dễ kiểm soát:

~~~text
orders.preview  → OrderQueryHandler.preview
orders.place    → OrderCommandHandler.place
orders.cancel   → OrderCommandHandler.cancel
~~~

Các phương thức có side effect nên nằm trên các **command endpoints có quyền hạn riêng**, còn các query/read-only endpoints tách khỏi luồng ghi.

**Channel name không thay authorization.** Nếu một producer bên ngoài có thể gửi thẳng vào `orders.cancel`, hệ thống vẫn cần kiểm tra quyền. Chỉ tin channel name là một quyết định bảo mật sai.

## 6. Java 17: command và result có kiểu rõ ràng

Ví dụ:

~~~java
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

record OrderReceipt(
    String orderId,
    String commandId,
    String status
) {}

record PreviewOrderQuery(
    String tenantId,
    String orderId
) {}

record CancelOrderCommand(
    String tenantId,
    String commandId,
    String orderId,
    String reasonCode
) {}

record OrderPreview(
    String orderId,
    BigDecimal estimatedTotal
) {}
~~~

`commandId` đại diện cho **logical operation**; giữ nguyên trên broker redelivery và retry. Nó khác `MessageHeaders.ID`, thường là ID của một Spring message instance.

Tách `PreviewOrderQuery` khỏi `PlaceOrderCommand` giúp tránh chọn nhầm method theo payload. Nếu cả query và command cùng dùng `OrderDto`, chỉ một thay đổi annotation/cấu hình cũng có thể khiến một query gọi phương thức ghi.

**DTO có kiểu rõ chưa đủ để an toàn**: vẫn phải validate `tenantId` đáng tin, `orderId`, số line, quantity, authorization và state hợp lệ. Không dùng một `tenantId` do client tự khai để bỏ qua kiểm tra principal.

## 7. Lựa chọn A: `@ServiceActivator` gắn trên đúng method

Một endpoint xử lý command:

~~~java
@MessageEndpoint
class PlaceOrderEndpoint {
    private final OrderCommandHandler handler;

    PlaceOrderEndpoint(OrderCommandHandler handler) {
        this.handler = handler;
    }

    @ServiceActivator(
        inputChannel = "orders.place",
        outputChannel = "orders.place.result")
    public OrderReceipt place(PlaceOrderCommand command) {
        return handler.place(command);
    }
}
~~~

Các điểm tích cực:

- Chỉ có method `place(PlaceOrderCommand)` được annotate cho input channel này.
- Không nhờ framework đoán trong nhiều overload của một service.
- Đầu vào có type xác định.
- Return value là `OrderReceipt`, cho phép downstream/Gateway nhận kết quả có nghĩa.
- Endpoint có thể dễ test bằng cách gửi `PlaceOrderCommand` tới `orders.place`.

**Chú ý:** đây là ví dụ **một trong các cách cấu hình**, không đăng ký đồng thời endpoint annotation và một Java DSL `.handle(...)` khác tiêu thụ cùng channel nếu không có mục đích dispatch cụ thể. Với `DirectChannel` và nhiều subscribers, behavior có thể là competing dispatch chứ không phải tất cả chạy.

## 8. Lựa chọn B: Java DSL `.handle(bean, "methodName")`

Khi muốn tường minh tên method:

~~~java
@Configuration
@EnableIntegration
class PlaceOrderFlow {

    @Bean
    IntegrationFlow placeOrderFlow(
            OrderCommandHandler orderHandler) {
        return IntegrationFlow.from("orders.place")
            .handle(orderHandler, "place")
            .channel("orders.place.result")
            .get();
    }
}
~~~

Ý tưởng: endpoint được cấu hình để gọi method **`place`** trên bean cụ thể, thay vì để một component tự tìm ra phương thức có thể gọi theo nhiều lựa chọn không rõ ràng.

Để tránh overload mơ hồ, hãy giữ **một method `place(PlaceOrderCommand)` phù hợp** trong bean này. Chỉ định tên method **giảm mơ hồ**, nhưng nếu bean có nhiều overload **cùng tên**, framework vẫn cần chọn chữ ký tương thích payload/message và conversion rules.

**Không viết tên method lấy trực tiếp từ header untrusted** kiểu `headers.operationMethod`. Danh sách methods có quyền ghi/hủy không được trở thành API reflection mà client tự chọn.

## 9. Lựa chọn C: Java DSL typed handler lambda

Khi một flow nhỏ chỉ có một operation, có thể dùng handler typed:

~~~java
@Bean
IntegrationFlow typedPlaceFlow(
        OrderCommandHandler orderHandler) {
    return IntegrationFlow.from("orders.place.typed")
        .handle(
            PlaceOrderCommand.class,
            (command, headers) -> orderHandler.place(command))
        .channel("orders.place.typed.result")
        .get();
}
~~~

Đặc điểm:

- Type của payload được thể hiện ngay trong DSL.
- Lambda gọi trực tiếp **một method cụ thể**.
- Không phụ thuộc việc framework chọn một trong nhiều method có cùng tên trên bean.
- Header có thể dùng để **lấy context đã được kiểm tra**, không dùng để thay đổi operation.

Đoạn code là mẫu Spring Integration Java DSL; cần xác minh overload và imports theo phiên bản được sử dụng. Nó **không tự thêm authorization/transaction**: logic nghiệp vụ phải nằm trong Spring-managed service và có các kiểm soát riêng.

Không đăng ký đồng thời ví dụ mục 7, 8, 9 trên **cùng một input channel** nếu không muốn nhiều endpoints cạnh tranh lấy message.

## 10. Overloaded methods: vì sao khó kiểm soát?

Ví dụ một bean:

~~~java
class AmbiguousOrderService {
    OrderReceipt handle(PlaceOrderCommand command) {
        return placeOrder(command);
    }

    OrderPreview handle(PreviewOrderQuery query) {
        return previewOrder(query);
    }

    Object handle(Object anyPayload) {
        return fallbackOperation(anyPayload);
    }
}
~~~

Nếu endpoint cấu hình `handle(service, "handle")`, việc chọn overload có thể chịu ảnh hưởng bởi **runtime payload type, method resolution và conversion rules**. Một message bị deserialize sai thành `Map` hoặc `String` có thể đi vào `Object` overload thay vì bị từ chối.

Tệ hơn, nếu fallback method **có side effect**, một input không đúng contract có thể vẫn thực thi một thao tác không mong muốn.

Khuyến nghị:

1. Không gộp **preview**, **place**, **cancel** vào cùng một method name overload để dựa vào selection ngầm.
2. Đặt tên operation riêng hoặc bean handler riêng.
3. Cấu hình endpoint với **một payload type và method cụ thể**.
4. Không có fallback `handle(Object)` thực thi ghi dữ liệu.
5. Khi framework cần type conversion, kiểm thử trường hợp payload không hợp lệ bị **reject**, không bị ép kiểu rồi gọi nhầm method.

**Không kết luận một overload cụ thể sẽ được Spring chọn trong mọi version/cấu hình.** Cần test endpoint thực tế và tránh thiết kế phụ thuộc vào phỏng đoán.

## 11. Không để input tự chỉ định phương thức cần gọi

Anti-pattern:

~~~text
headers.methodName="cancelAllOrders"
payload={...}
    ↓
Generic reflection-based invoker
    ↓
orderService[headers.methodName](payload)
~~~

Khi header đến từ HTTP/broker bên ngoài, đây có thể là một **arbitrary method invocation vulnerability** hoặc một lỗi routing nghiêm trọng. Không để caller gửi bean name, class name, SpEL expression hay method name để framework đánh giá tùy ý.

Thay vào đó, dùng một **allowlist operation → channel/handler**:

~~~text
operation=PREVIEW → orders.preview  → preview(query)
operation=PLACE   → orders.place    → place(command)
operation=CANCEL  → orders.cancel   → cancel(command)
otherwise         → reject UNSUPPORTED_OPERATION
~~~

**Router chọn channel; Service Activator gọi method đã cố định ở channel đó.** Router cần xác minh message type, source/tenant và quyền trước khi chuyển tới command có side effect. Enum operation không thay thế authorization.

## 12. Binding tham số: payload, header hay nguyên Message?

Spring Integration hỗ trợ các dạng method handler phổ biến:

~~~java
@ServiceActivator(inputChannel = "orders.simple")
public OrderReceipt place(PlaceOrderCommand command) {
    return handler.place(command);
}
~~~

hoặc:

~~~java
@ServiceActivator(inputChannel = "orders.verified")
public OrderReceipt placeVerified(
        @Payload PlaceOrderCommand command,
        @Header("verifiedTenantId") String verifiedTenantId) {
    authorization.verifyTenant(command, verifiedTenantId);
    return handler.place(command);
}
~~~

hoặc nhận nguyên message:

~~~java
@ServiceActivator(inputChannel = "orders.full-message")
public OrderReceipt placeFromMessage(
        Message<PlaceOrderCommand> message) {
    PlaceOrderCommand command = message.getPayload();
    String tenant = (String) message.getHeaders()
        .get("verifiedTenantId");
    authorization.verifyTenant(command, tenant);
    return handler.place(command);
}
~~~

Các đoạn trên là **những phương án độc lập**, không phải ba endpoint cùng sử dụng trong một flow sản xuất. Với header:

- `@Header` lấy giá trị header, nhưng chỉ **tin** khi adapter nội bộ đã xác thực và ngăn bên ngoài giả mạo.
- `@Payload` đánh dấu tham số payload, giúp method contract rõ.
- `Message<T>` phù hợp khi cần payload **và** metadata như correlation.
- Không dùng một `Map<String,Object>` chung để nhận mọi loại command nếu có thể khai báo model cụ thể.

**Header tồn tại không đồng nghĩa header được xác thực**. Giữ authorization ở business boundary thay vì tin vào cách Message được tạo.

## 13. Chọn method dựa trên kiểu command, không dựa trên thứ tự tham số tình cờ

Một handler tốt có tên và chữ ký ổn định:

~~~java
OrderReceipt place(PlaceOrderCommand command)
~~~

Một handler khó hiểu:

~~~java
Object handle(Object payload, Map<String, Object> headers)
~~~

Nhược điểm của chữ ký quá tổng quát:

- Không phát hiện sai type ở compile time.
- Logic thường phụ thuộc `instanceof`/cast trong method.
- Khó audit method có ghi database/publish không.
- Dễ có nhánh fallback được kích hoạt bởi payload từ schema mới.
- Test ma trận đầu vào phức tạp hơn.

Khi cần nhiều loại message, để **Router/Normalizer/Transformer** xử lý type/format trước và đưa một canonical command đến Service Activator. **Không biến Service Activator thành một dynamic dispatcher biết mọi schema, mọi operation và mọi side effect.**

## 14. Command–Query Separation: method chỉ đọc và method ghi phải tách biệt

Một query:

~~~java
@Service
class OrderQueryHandler {
    private final OrderReadRepository orders;

    OrderQueryHandler(OrderReadRepository orders) {
        this.orders = orders;
    }

    public OrderPreview preview(PreviewOrderQuery query) {
        return orders.preview(query.tenantId(), query.orderId());
    }
}
~~~

Một command:

~~~java
@Service
class OrderCommandHandler {
    private final OrderWriteRepository orders;
    private final OrderAuthorization authorization;

    OrderCommandHandler(
            OrderWriteRepository orders,
            OrderAuthorization authorization) {
        this.orders = orders;
        this.authorization = authorization;
    }

    public OrderReceipt place(PlaceOrderCommand command) {
        authorization.verifyCanPlace(command);
        return orders.place(command);
    }
}
~~~

Các repository/authorization service ở trên là **abstraction của ứng dụng**, không phải bean có sẵn của Spring Integration. Ở đây mới diễn giải **phân quyền và trách nhiệm**, chưa phải phiên bản transaction/idempotency hoàn chỉnh.

**Query endpoint** không nên âm thầm ghi sổ cái, trừ tồn kho, tạo invoice hoặc gửi email. Việc lưu metric/audit phục vụ quan sát là side effect kỹ thuật có thể được cho phép, nhưng phải **giới hạn và không tạo hành vi nghiệp vụ mới**.

**Command endpoint** có thể ghi, nhưng phải chịu trách nhiệm transaction, retry và idempotency. Tách hai loại giúp code review và test dễ phát hiện side effect sai.

## 15. Những side effect “ẩn” mà method selection không phát hiện

Một method tên `validate()` nghe như read-only, nhưng:

~~~java
boolean validateAndReserve(PlaceOrderCommand command) {
    inventory.reserve(command.lines());
    return true;
}
~~~

Method đã **giữ tồn kho** ngay trong bước validation. Nếu Filter gọi nó để kiểm tra `true/false`, một message bị thử nhiều lần có thể đặt nhiều reservations rồi mới vào handler chính.

Các side effect khó nhìn:

- `validator.isValid()` gọi API tạo customer nếu thiếu.
- `mapper.normalize()` dùng `save()` để cache dưới dạng record nghiệp vụ.
- `toString()`, getter/lazy ORM access kích hoạt I/O ngoài ý định.
- Một method “preview” gửi event `OrderCreated`.
- Advice/interceptor chạy trước method đã lưu dedupe marker **không rollback** khi handler lỗi.
- Một callback retry chạy lại method gửi HTTP POST nhưng remote không hỗ trợ idempotency.
- Một exception handler ghi một kết quả `SUCCESS` giả để ACK broker.

Nguyên tắc: đánh dấu rõ **pure validation**, **read-only query**, **business command**, **external side effect**, **audit/diagnostic**. Không gộp mọi thao tác vào một method tên chung rồi hi vọng người gọi biết nội bộ.

## 16. Kiểm tra input trước khi chạm vào repository hoặc remote service

Một validation service thuần:

~~~java
@Service
class PlaceOrderValidator {
    void validate(PlaceOrderCommand command) {
        if (command == null) {
            throw new InvalidCommandException("MISSING_COMMAND");
        }
        if (command.commandId() == null
                || command.commandId().isBlank()) {
            throw new InvalidCommandException("MISSING_COMMAND_ID");
        }
        if (command.orderId() == null
                || command.orderId().isBlank()) {
            throw new InvalidCommandException("MISSING_ORDER_ID");
        }
        if (command.lines() == null
                || command.lines().isEmpty()
                || command.lines().size() > 100) {
            throw new InvalidCommandException("INVALID_LINES");
        }
        for (OrderLine line : command.lines()) {
            if (line == null
                    || line.sku() == null
                    || line.sku().isBlank()
                    || line.quantity() <= 0) {
                throw new InvalidCommandException(
                    "INVALID_ORDER_LINE");
            }
        }
    }
}
~~~

`InvalidCommandException` là một exception ứng dụng mang reason code ổn định. Validator này **không ghi database, không gọi external API và không phát message**, vì vậy khi Filter hoặc pre-handler validation gọi nhiều lần, nó không làm thay đổi business state.

**Không đồng nhất validation với authorization.** Input đủ trường vẫn có thể thuộc tenant khác hoặc vi phạm quyền thao tác. Authorization phải lấy principal/tenant từ context đã tin cậy; không cho phép client tự khai `tenantId` rồi thao tác tùy ý.

Giới hạn bytes, nested depth và số lượng line items nên được áp **tại ingress trước khi deserialize/fan-out**, vì validator trên object không chống mọi cuộc tấn công tài nguyên.

## 17. Bảo vệ method ghi bằng authorization ở boundary đáng tin

Một handler cần kiểm tra **người gọi có được thực hiện operation**:

~~~java
interface OrderAuthorization {
    void verifyTenant(
        PlaceOrderCommand command, String verifiedTenantId);
    void verifyCanPlace(PlaceOrderCommand command);
    void verifyCanCancel(CancelOrderCommand command);
}
~~~

Trong triển khai thật, service có thể đọc security principal từ Spring Security context hoặc một verified identity envelope có provenance; nó phải kiểm chứng:

- Tenant context thực sự thuộc người gửi.
- `orderId` thuộc tenant được phép.
- Operation đang được phép theo business state.
- Người gửi chỉ có quyền `PREVIEW` hay có quyền `PLACE/CANCEL`.
- Headers từ broker/HTTP không thể giả mạo identity nội bộ.

Khi Spring Integration chuyển message qua executor hoặc broker, thread-local security context **không mặc nhiên được giữ**. Nếu dựa vào context cho authorization, phải cấu hình context propagation được tin cậy hoặc đưa verified identity vào một envelope có contract và integrity đúng.

**Chọn đúng method không đủ để cấp quyền.** Một message `CancelOrderCommand` đúng kiểu vẫn phải bị từ chối nếu caller không có quyền hủy.

## 18. Transaction boundary phải bao gồm các side effect thuộc cùng database

Một implementation cho command `PLACE`:

~~~java
@Service
class TransactionalOrderCommandHandler {
    private final PlaceOrderValidator validator;
    private final OrderAuthorization authorization;
    private final ProcessedCommandRepository inbox;
    private final OrderWriteRepository orders;
    private final OutboxRepository outbox;
    private final CommandFingerprint fingerprint;

    TransactionalOrderCommandHandler(
            PlaceOrderValidator validator,
            OrderAuthorization authorization,
            ProcessedCommandRepository inbox,
            OrderWriteRepository orders,
            OutboxRepository outbox,
            CommandFingerprint fingerprint) {
        this.validator = validator;
        this.authorization = authorization;
        this.inbox = inbox;
        this.orders = orders;
        this.outbox = outbox;
        this.fingerprint = fingerprint;
    }

    @Transactional
    public OrderReceipt place(PlaceOrderCommand command) {
        validator.validate(command);
        authorization.verifyCanPlace(command);

        String hash = fingerprint.canonicalHash(command);
        boolean first = inbox.insertIfAbsent(
            command.tenantId(),
            command.commandId(),
            "PLACE",
            hash);

        if (!first) {
            inbox.assertSameFingerprint(
                command.tenantId(),
                command.commandId(),
                "PLACE",
                hash);
            return inbox.loadCommittedReceipt(
                command.tenantId(),
                command.commandId(),
                "PLACE");
        }

        OrderReceipt receipt = orders.create(command);
        outbox.recordOrderPlaced(command, receipt);
        inbox.saveReceipt(
            command.tenantId(),
            command.commandId(),
            "PLACE",
            receipt);
        return receipt;
    }
}
~~~

Các interfaces `ProcessedCommandRepository`, `OutboxRepository`, `CommandFingerprint` và methods của chúng là **ví dụ contract do ứng dụng tự triển khai**, không phải Spring Integration APIs. Ý tưởng:

1. Validate/authorize trước các ghi nghiệp vụ.
2. Chỉ một transaction được claim key `(tenant, commandId, operation)` nhờ **database unique constraint**.
3. Ghi order, outbox và receipt **trong cùng transaction**.
4. Nếu exception xảy ra trước commit, **rollback cả marker lẫn business changes**.
5. Nếu broker redeliver sau commit, trả receipt đã lưu, **không tạo order lần hai**.
6. Nếu cùng key nhưng payload hash khác, trả **idempotency key conflict**, không im lặng chấp nhận.

**Điều kiện tiên quyết:** inbox, order repository và outbox phải dùng **cùng database transaction/transaction manager**. `@Transactional` không tự đưa Redis hoặc HTTP side effect vào cùng atomic commit.

## 19. Vì sao cần outbox thay vì publish trực tiếp trong transaction?

Một implementation dễ gây sự cố:

~~~java
@Transactional
public OrderReceipt place(PlaceOrderCommand command) {
    OrderReceipt receipt = orders.create(command);
    eventPublisher.publish(new OrderPlaced(command.orderId()));
    return receipt;
}
~~~

Nếu broker send thành công nhưng database rollback, downstream nhận một event **cho đơn chưa tồn tại**. Nếu database commit rồi process crash trước send, downstream lại **không nhận event**.

**Transactional Outbox** lưu bản ghi event intent cùng transaction với order:

~~~text
BEGIN
  INSERT processed_command
  INSERT orders
  INSERT outbox_event
COMMIT
  → Outbox publisher đọc và gửi
  → Downstream consumer tự dedupe eventId/outboxId
~~~

Outbox **không ngăn broker nhận duplicate** nếu publisher crash sau send nhưng trước mark-published. Nó giữ ý định publish bền vững và cho phép phát lại; consumer vẫn cần idempotency.

**Side effect được phép phải có ranh giới rõ.** Nếu Service Activator được thiết kế chỉ lưu order và outbox, nó không nên trực tiếp thêm hành vi gửi email, charge payment và publish trên hai broker mà không có workflow/transaction protocol.

## 20. Method có `@Transactional` vẫn có thể bị bypass proxy

Một lỗi phổ biến:

~~~java
@Service
class UnsafeOrderService {
    public OrderReceipt place(PlaceOrderCommand command) {
        return doPlace(command); // self-invocation
    }

    @Transactional
    public OrderReceipt doPlace(PlaceOrderCommand command) {
        // Ghi inbox + order.
        return writeOrder(command);
    }
}
~~~

Với transaction proxy mặc định của Spring, lời gọi nội bộ `this.doPlace(...)` có thể không đi qua proxy, khiến `@Transactional` không tạo transaction mong muốn.

Một hướng rõ hơn: để **Service Activator gọi trực tiếp một Spring-managed transactional service bean**, không tạo handler thủ công bằng `new`, không giấu transaction trong private method/self-call.

Ngoài ra, mặc định rollback của Spring transaction chủ yếu áp dụng với unchecked exceptions; nếu dùng checked exceptions, cấu hình rollback rules phù hợp. Tránh catch exception rồi trả success làm transaction commit marker mặc dù business failed.

**`@Transactional(readOnly=true)` không phải một security guarantee ngăn mọi write**; nó là hint/transaction configuration có hành vi phụ thuộc persistence provider/DB. Query handler phải **không gọi phương thức ghi theo thiết kế**, cộng với tests và DB permission nếu cần.

## 21. Retry sau handler failure: method có thể bị gọi nhiều lần

Trong môi trường message-driven, `at-least-once delivery` là tình huống thường gặp. Một lỗi:

~~~text
T1 Broker gửi PlaceOrderCommand commandId=C-801.
T2 Handler ghi order và commit.
T3 Process crash trước ACK.
T4 Broker gửi lại C-801.
T5 Handler bị gọi lần hai.
~~~

**Không được giả định “một message = một method invocation”.** Bảo đảm cần hướng tới là **một logical operation không tạo side effect trùng**.

| Thời điểm lỗi | Điều cần bảo đảm |
|---|---|
| Trước transaction | Có thể retry |
| Sau claim marker nhưng trước commit | Marker phải rollback hoặc state retryable |
| Sau DB commit nhưng trước broker ACK | Dedupe nhận duplicate completed |
| Trong HTTP POST đến remote | Outcome có thể chưa biết, dùng remote idempotency/reconcile |
| Sau publish event nhưng trước mark sent | Downstream dedupe |
| Khi retry exhausted | Có DLQ/recovery plan, không trả success giả |

RetryAdvice hoặc broker redelivery có thể kích hoạt **cùng method nhiều lần**. Thiết kế handler phải an toàn với điều đó, không dựa vào một biến `boolean handled` trong JVM.

## 22. Thứ tự Retry Advice và Idempotent Receiver không thay transaction đúng

Hai cách bọc:

~~~text
RetryAdvice(
    IdempotentAdvice(
        ServiceActivator.handle()
    )
)

IdempotentAdvice(
    RetryAdvice(
        ServiceActivator.handle()
    )
)
~~~

Nếu một `IdempotentReceiverInterceptor` dùng `MetadataStoreSelector` **ghi dấu seen trước handler**, retry ở tầng ngoài có thể thấy marker và coi lần thử tiếp theo là duplicate **dù handler trước đã thất bại**.

Đặt RetryAdvice bên trong có thể giúp các attempts nội bộ tới handler, nhưng **nếu hết retry mà marker còn**, broker redelivery vẫn có thể bị chặn. **Thay thứ tự advice không tự sửa được marker semantics**.

Giải pháp an toàn hơn:

- Marker và business side effect **atomic trong một DB transaction**, hoặc
- Inbox có states `PROCESSING/FAILED_RETRYABLE/SUCCEEDED`, lease/fencing, và recovery rõ; hoặc
- Với external side effect, remote idempotency key/reconciliation.

Mọi lời khuyên về advice chain phải được xác minh theo version Spring Integration và cấu hình selector/metadata store thực tế. **Không suy đoán một interceptor tự rollback marker** nếu storage ngoài transaction.

## 23. External side effect không được rollback bằng JDBC

Một handler:

~~~text
BEGIN database transaction
  INSERT order
  HTTP POST /payment/capture
  UPDATE local order status
COMMIT
~~~

Nếu remote đã capture nhưng client timeout, local transaction có thể rollback mà tiền vẫn bị trừ. Lần retry gửi một HTTP request **với key mới** có thể trừ tiếp.

**Nguyên tắc**:

1. Dùng **business idempotency key ổn định**, cùng remote key qua mọi retry khi provider hỗ trợ.
2. Ghi durable operation intent và outcome state.
3. Phân biệt `FAILED_RETRYABLE` với `UNKNOWN_OUTCOME`.
4. Với timeout sau external call, **reconcile** thay vì tự kết luận remote chưa thực hiện.
5. Không thêm remote charge chỉ vì query/preview/validation method được gọi.
6. Tách các operations thành workflow/steps có compensation nếu domain cho phép.

Nếu provider không có idempotency/query API, không tự động retry một lệnh nguy hiểm như charge/refund chỉ vì timeout; cần một protocol xác minh hoặc manual review.

## 24. `void`, `null` và reply contract của Service Activator

Một one-way handler:

~~~java
@ServiceActivator(inputChannel = "audit.events")
public void audit(AuditEvent event) {
    auditSink.record(event);
}
~~~

Điều này có thể phù hợp khi upstream **không mong reply**. Nhưng nếu một Gateway đồng bộ gọi qua endpoint `void` và mong kết quả, caller có thể **timeout**, dù side effect đã xảy ra.

Trường hợp khác:

~~~java
public OrderReceipt place(PlaceOrderCommand command) {
    orders.create(command);
    return null; // Không có response để Gateway nhận.
}
~~~

Một `null` không tự tạo reply thành công. Cần quy định:

- **Request–reply:** trả typed result, hoặc ném exception được map đúng.
- **One-way:** không giả định caller đang chờ reply; xác nhận delivery/recovery theo adapter.
- **Async accepted:** có thể trả trạng thái `ACCEPTED/PENDING` nếu đã lưu durable intent, không báo business `SUCCEEDED` giả.
- **Command failure:** ném exception/cấu trúc terminal outcome đúng, không catch rồi return fake receipt.

**Business side effect và reply là hai sự kiện khác nhau.** Một Gateway timeout không tự hủy transaction/HTTP call đang xử lý phía sau; caller retry cần giữ cùng command ID.

## 25. Đồng bộ và bất đồng bộ: invocation boundary quyết định ai thấy lỗi

~~~mermaid
flowchart TD
    IN["Incoming message"] --> B{"Channel boundary"}
    B -->|"DirectChannel/sync"| H1["Handler on caller thread"]
    B -->|"ExecutorChannel/async"| H2["Handler on worker thread"]
    H1 -->|"Exception"| C["Caller / Gateway exception path"]
    H2 -->|"Exception"| EC["Error channel / container handler"]
    H1 -->|"Return"| R1["Synchronous reply"]
    H2 -->|"Return"| R2["Async reply or completion"]
~~~

Nếu Service Activator ném exception trên `DirectChannel` đồng bộ, lỗi thường lan ngược tới sender/Gateway. Với `ExecutorChannel` hoặc broker/poller, upstream `send()` có thể trả trước khi handler chạy; lỗi thuộc **error boundary của worker/container**, không mặc nhiên ném về caller.

**Không đặt `@Transactional` trên caller rồi tin transaction sẽ trải qua mọi worker thread.** Transaction context thường gắn với thread và manager; cần transaction boundary tại service được worker thực sự gọi.

Một test bắt exception từ `input.send()` trên DirectChannel không đủ chứng minh cách async flow gửi `ErrorMessage` hoặc ACK broker.

## 26. Message headers không thay quyền hoặc business identity

Một message có:

~~~text
headers.verifiedTenantId=tenant-a
headers.businessCorrelationId=tenant-a|O-801|revision-2
headers.traceId=...
headers.replyChannel=<temporary channel>
payload.commandId=C-801
~~~

Hãy phân biệt:

- `commandId`: idempotency của logical command.
- `businessCorrelationId`: nhóm workflow như Order → children/replies.
- `traceId`: quan sát luồng, không quyết định quyền.
- `replyChannel`: return address, thường tạm thời/không được serialize ra broker.
- `MessageHeaders.ID`: ID của message object, có thể đổi sau Transformer/replay.
- `verifiedTenantId`: chỉ đáng tin **khi do adapter được xác thực gắn vào và bảo vệ**.

Đừng dùng `traceId` làm idempotency key; retry khác trace vẫn là cùng logical command. Đừng cho `businessCorrelationId` quyết định người dùng có quyền hủy/ghi đơn.

**Khi message qua broker/Transformer**, header mapping có thể làm mất metadata. Những identity cần phục hồi nên nằm trong wire contract hoặc một durable mapping; không tin mọi header Spring luôn được giữ nguyên.

## 27. Một command handler phải độc lập với số lần delivery

Mô hình tốt:

~~~text
Receive logical command C-801
  → validate/authorize
  → transactional inbox claim
  → apply side effect + write outbox
  → commit
  → reply/ACK

Redelivery C-801
  → same fingerprint + committed inbox
  → cached receipt / duplicate completed
  → no new business side effect
~~~

Mô hình nguy hiểm:

~~~text
Receive C-801
  → in-memory HashSet.add(C-801)
  → HTTP charge
  → local DB update
  → crash

Restart/redelivery
  → HashSet empty
  → charge again
~~~

Đối với multi-instance, một `HashSet` trên từng JVM không đồng bộ, không bền qua restart, và không phải distributed idempotency store. Dùng unique constraint/inbox durable hoặc một protocol có atomic claim thích hợp.

## 28. Router, Filter và Transformer nên làm gì trước Service Activator?

Một luồng có chủ đích:

~~~mermaid
flowchart LR
    IN["Incoming command"] --> PARSE["Decode + schema validation"]
    PARSE --> FILTER["Filter: structural acceptance"]
    FILTER --> ROUTER["Router: operation"]
    ROUTER --> TRANS["Transformer: canonical command"]
    TRANS --> ACT["Service Activator: explicit method"]
    ACT --> OUT["Business reply / outbox"]
~~~

| Endpoint | Vai trò | Không nên làm |
|---|---|---|
| **Filter** | Kiểm tra điều kiện tiếp tục, reject malformed input | Thực hiện reserve/charge trong predicate |
| **Router** | Chọn channel/nhánh cho operation đã xác thực | Gọi phương thức tùy ý từ header |
| **Transformer** | Chuẩn hóa payload/type, giữ IDs cần thiết | Tạo payment/ghi order khi chỉ đang chuyển kiểu |
| **Service Activator** | Gọi service method có contract nghiệp vụ rõ | Tự đoán operation hoặc tự xử lý mọi schema |
| **Gateway** | Giao diện request–reply qua message flow | Xem timeout như bằng chứng command rollback |
| **Splitter** | Chia một message thành nhiều child messages | Mặc nhiên bảo đảm từng child đúng quyền |
| **Aggregator** | Gom outcomes theo correlation/release policy | Tự bù missing child bằng success giả |

**Tách nhiệm vụ không có nghĩa tránh mọi method calls ở Router/Filter/Transformer**, mà là **giữ logic ở đó thuần và dự đoán được**, không tạo business side effects không được phép.

Nếu một Filter cần hỏi database để kiểm tra một business rule, hãy phân biệt **kết quả business negative** với **database timeout**. Không catch timeout rồi return `false` khiến message hợp lệ bị reject vĩnh viễn.

## 29. Splitter/Aggregator: mỗi child có một method và idempotency key riêng

Một order:

~~~text
PlaceOrder C-801
  → Splitter
      → Line L1 → inventory.reserveOneLine
      → Line L2 → inventory.reserveOneLine
      → Line L3 → inventory.reserveOneLine
  → Aggregator
  → PlaceOrderResult
~~~

Không dùng **cùng một idempotency key là `C-801`** cho cả ba child nếu receiver dedupe theo key đó; child đầu có thể làm hai child sau bị coi là duplicate.

Một child key phù hợp:

~~~text
tenantId + parentCommandId + operation + lineId
~~~

Ngoài ra:

- `correlationId` nhóm các kết quả về một parent.
- `lineId` nhận diện member của group.
- `sequenceNumber/sequenceSize` giúp thể hiện vị trí/số child theo topology.
- `attemptId` chỉ theo dõi lần retry, **không là child identity**.

Nếu Service Activator xử lý child L2 thất bại vĩnh viễn, cần **LineOutcome(success=false, reasonCode=...)** hoặc failure policy rõ cho cả group. Nếu error handler chỉ log rồi drop L2, Aggregator có thể chờ mãi hoặc release partial sai.

Không tính duplicate outcome L1 như member mới để đạt số đếm expected. Aggregator cần distinct member IDs và manifest/release strategy.

## 30. Không để một method ghi bị gọi lại do late reply hoặc completion logic

Một Gateway/Scatter-Gather flow có thể có:

~~~text
Gateway gửi command C-801
  → worker A success
  → worker B late reply
  → aggregator/group completion
  → caller timeout rồi retry C-801
~~~

Những tình huống cần thiết kế:

1. Completed-group/tombstone policy ngăn **late reply** làm group xuất output thứ hai.
2. Reply mang business correlation chính xác; không gộp hai tenant có cùng `orderId`.
3. Gateway timeout không hủy worker hay undo side effect.
4. Caller retry **cùng logical commandId**, không tạo UUID mới khi thực hiện lại cùng operation.
5. Duplicate reply không được kích hoạt một Service Activator **có hành vi ghi** thêm lần nữa.

**Chỉ dùng output channel khác hoặc rename method không giải quyết được replay/late replies.** Cần domain idempotency và aggregator completion policy.

## 31. Service Activator cần phân loại lỗi, không catch tất cả thành success

Một error contract:

~~~java
final class InvalidCommandException extends RuntimeException {
    private final String reasonCode;

    InvalidCommandException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    String reasonCode() {
        return reasonCode;
    }
}
~~~

Các loại lỗi thường gặp:

| Lỗi | Nguồn | Hướng xử lý |
|---|---|---|
| `MISSING_COMMAND_ID` | Input validation | Reject permanent |
| `FORBIDDEN_ORDER_OPERATION` | Authorization | Reject/audit, không retry hạ tầng |
| `IDEMPOTENCY_KEY_CONFLICT` | Cùng key nhưng nội dung khác | Quarantine/investigate |
| `ORDER_ALREADY_CANCELED` | Domain state | Terminal business result theo contract |
| `DB_DEADLOCK` | Persistence | Retry bounded, transaction mới |
| `PAYMENT_OUTCOME_UNKNOWN` | Remote side effect | Reconcile |
| `UNEXPECTED_HANDLER_EXCEPTION` | Code defect | Alert/recovery, không đổ lỗi producer |

Tránh:

~~~java
try {
    orderHandler.place(command);
} catch (Exception failure) {
    return new OrderReceipt(
        command.orderId(),
        command.commandId(),
        "SUCCESS"); // Sai: tạo success giả.
}
~~~

Handler cần ném lỗi hoặc trả **business outcome có cấu trúc** phù hợp, để caller/adapter biết nên retry, ACK, DLQ hay báo lỗi. Exception message raw không nên được gửi công khai nếu chứa thông tin DB, tenant hoặc secret.

## 32. Error channel không mặc nhiên được gọi với mọi exception

Trong flow đồng bộ:

~~~text
DirectChannel → Service Activator throws
  → exception lan về sender/Gateway
~~~

Trong flow bất đồng bộ:

~~~text
ExecutorChannel / poller / broker listener
  → Service Activator throws trên worker thread
  → error handler/container hoặc ErrorMessage/errorChannel
~~~

Một Spring `ErrorMessage` mang `Throwable` làm payload. Nếu exception thuộc nhóm `MessagingException`, có thể có `getFailedMessage()` để lấy header/correlation. Nhưng:

- Lỗi deserialize có thể xảy ra **trước khi có Spring Message**.
- `failedMessage` có thể null hoặc mang kiểu payload khác dự kiến.
- Một error channel được cấu hình sai/unsubscribed có thể làm mất đường recovery.
- RetryAdvice chỉ bắt exception trong **phạm vi handler nó bao quanh**.

**Không catch ở error handler rồi ACK để “sạch queue” khi business chưa commit.** Cần policy bền vững cho recovery, DLQ/reconciliation và thông tin diagnostic đủ để tái xử lý.

## 33. ACK/DLQ gắn với kết quả thực thi, không gắn với tên method

Một Service Activator được gọi thành công về mặt Java chưa chắc business đã thành công:

~~~java
public void handle(PlaceOrderCommand command) {
    executor.submit(() -> placeOrder(command));
    // Method return ngay, background task chưa commit.
}
~~~

Nếu broker ACK ngay vì `handle()` return, còn background task thất bại và không có durable queue/recovery, **công việc bị mất**.

Một chính sách có thể là:

| Outcome | ACK/recovery thường xem xét |
|---|---|
| Business commit thành công | ACK |
| Duplicate đã SUCCEEDED, fingerprint khớp | ACK, không side effect mới |
| Input invalid/unauthorized | Quarantine/terminal response, ACK theo adapter policy |
| Database transient failure trước commit | Retry bounded/backoff, không ACK mất việc |
| Async task đã lưu durable intent nhưng chưa xử lý | Có thể ACK theo async-accepted contract |
| External outcome chưa rõ | Durable reconciliation, không báo success giả |
| DLQ/quarantine unavailable | Không drop nếu chưa có nguồn recovery khác |

Không có ACK API chung đúng cho Kafka, AMQP, JMS. Thứ tự transaction, requeue, offset commit và error handler phụ thuộc adapter/container; cần test với transport thật.

**Một async accepted result là một trạng thái khác SUCCEEDED.** Khi chọn method chỉ enqueue công việc, tên và return type phải thể hiện điều đó.

## 34. Thread safety và concurrency của handler

Spring-managed singleton service có thể được gọi đồng thời từ nhiều worker threads:

~~~java
@Service
class UnsafeSequenceHandler {
    private long nextOrderNumber = 0L;

    public OrderReceipt place(PlaceOrderCommand command) {
        long n = ++nextOrderNumber; // Race condition.
        return saveWithNumber(command, n);
    }
}
~~~

Một field mutable trên singleton không bảo đảm uniqueness/thread safety. Nếu nhiều instances chạy, `AtomicLong` trong một JVM cũng **không bảo đảm** một số thứ tự unique trên cluster.

Sử dụng database sequence/unique constraint, durable state và transaction khi cấp số ID cần global uniqueness. Khi hai consumer nhận cùng command:

~~~text
W1: INSERT inbox key C-801
W2: INSERT inbox key C-801
→ unique constraint/transaction serialize outcome
→ chỉ một committed business side effect
~~~

Test concurrency bằng latch/barrier và nhiều transactions; gọi tuần tự hai lần không phơi bày race. Cũng cần test deadlocks/serialization failures có retry policy phù hợp.

## 35. Logging và metrics cũng là side effects cần giới hạn

Một handler có thể ghi log mỗi lần retry:

~~~text
INFO customerEmail=... paymentToken=... fullOrderPayload=...
~~~

Đây không phải side effect nghiệp vụ nhưng có thể gây **rò dữ liệu**, storage growth và log injection. Với diagnostics:

- Log `commandId`/`correlationId` ở nơi có quyền truy cập phù hợp.
- Không log raw credentials, token hoặc PII khi không cần thiết.
- Hạn chế full payload và stack traces theo chính sách retention.
- Giới hạn độ dài field/cause từ untrusted input.
- Không dùng ID duy nhất làm metric labels (cardinality không giới hạn).

Metrics được thiết kế để trả lời **method nào thực sự được gọi, lần thứ mấy và có commit hay không**, thay vì chỉ đếm inbound messages.

## 36. Quy ước thiết kế lựa chọn method để dễ review

| Quy ước | Mục đích |
|---|---|
| Một channel biểu diễn một operation được đặt tên | Dễ truy vết và đặt quyền |
| Handler method public, name rõ theo hành vi | Dễ audit side effect |
| Tránh overload cùng tên cho command/query khác mục đích | Giảm method-resolution ambiguity |
| DTO typed theo logical operation | Sai type bị phát hiện sớm |
| Không có reflection từ untrusted headers | Giới hạn surface được invoke |
| Validation thuần và authorization trước write | Không tạo hiệu ứng khi reject |
| Transactional service bean riêng | Proxy/transaction boundary rõ |
| Durable idempotency theo logical command | Chịu được retry và restart |
| Outbox thay direct broker publish trước commit | Đồng bộ durable intent với business |
| Gateway reply/one-way contract tường minh | Không timeout hay báo success giả |
| Error classifier theo permanent/transient/unknown | Retry/DLQ/reconciliation đúng |

Không nhất thiết mỗi operation cần một class riêng. Điều quan trọng là **không có một endpoint mơ hồ cho phép message tự chọn một hành vi có quyền ghi**.

## 37. Unit test: query tuyệt đối không gọi command handler

Một test cơ bản dùng Mockito:

~~~java
@Test
void previewDoesNotPlaceOrCancelOrder() {
    OrderQueryHandler queryHandler =
        mock(OrderQueryHandler.class);
    OrderCommandHandler commandHandler =
        mock(OrderCommandHandler.class);

    PreviewOrderQuery query =
        new PreviewOrderQuery("tenant-a", "O-801");
    when(queryHandler.preview(query)).thenReturn(
        new OrderPreview("O-801", new BigDecimal("29.00")));

    OrderPreview preview = queryHandler.preview(query);

    assertEquals("O-801", preview.orderId());
    verify(queryHandler, times(1)).preview(query);
    verifyNoInteractions(commandHandler);
}
~~~

Test này mới xác nhận **các lời gọi trong test code**, chưa chứng minh Spring Integration chọn method đúng. Giá trị của nó là thiết lập một **invariant rõ**: preview/query path không được chạm tới command handler.

Ở integration test tiếp theo, đưa message qua đúng Spring channel rồi xác minh cùng invariant; vì lỗi method selection thường xảy ra **tại cấu hình endpoint**, không phải tại logic nội bộ của POJO.

## 38. Integration test: input preview chỉ tới đúng Service Activator

Một test-only flow:

~~~java
@Configuration
@EnableIntegration
class PreviewFlowTestConfig {
    @Bean
    IntegrationFlow previewFlow(OrderQueryHandler queryHandler) {
        return IntegrationFlow.from("test.orders.preview")
            .handle(
                PreviewOrderQuery.class,
                (query, headers) -> queryHandler.preview(query))
            .channel("test.orders.preview.reply")
            .get();
    }

    @Bean("test.orders.preview.reply")
    PollableChannel previewReplyQueue() {
        return new QueueChannel();
    }
}
~~~

Test trong một Spring context riêng có `queryHandler` và `commandHandler` là mocks:

~~~java
@Autowired ApplicationContext context;
@Autowired OrderQueryHandler queryHandler;
@Autowired OrderCommandHandler commandHandler;

@Test
void previewChannelNeverInvokesPlace() {
    PreviewOrderQuery query =
        new PreviewOrderQuery("tenant-a", "O-801");
    when(queryHandler.preview(query)).thenReturn(
        new OrderPreview("O-801", new BigDecimal("29.00")));

    MessageChannel input = context.getBean(
        "test.orders.preview", MessageChannel.class);
    PollableChannel replies = context.getBean(
        "test.orders.preview.reply", PollableChannel.class);

    assertTrue(input.send(new GenericMessage<>(query)));
    Message<?> reply = replies.receive(1_000);

    assertNotNull(reply);
    assertInstanceOf(OrderPreview.class, reply.getPayload());
    verify(queryHandler).preview(query);
    verifyNoInteractions(commandHandler);
}
~~~

**Các mock beans, test context và imports cần được cấu hình trong dự án.** Đây là mẫu minh họa điều kiện cần assert, không phải một test class hoàn chỉnh có sẵn. Chạy context độc lập để không có production endpoint khác subscribe vào channel.

Với method selection nguy hiểm, test thêm **runtime payload sai kiểu** hoặc source schema mới: phải reject/không đi vào một fallback `handle(Object)` có side effect.

## 39. Test: invalid command phải dừng trước khi ghi

Một test dùng fake/mock repositories:

~~~java
@Test
void invalidQuantityDoesNotReachWriteRepository() {
    PlaceOrderValidator validator =
        new PlaceOrderValidator();

    PlaceOrderCommand invalid = new PlaceOrderCommand(
        "tenant-a",
        "C-802",
        "O-802",
        List.of(new OrderLine("SKU-1", -2)));

    InvalidCommandException failure = assertThrows(
        InvalidCommandException.class,
        () -> validator.validate(invalid));

    assertEquals(
        "INVALID_ORDER_LINE",
        failure.reasonCode());
}
~~~

Để chứng minh invariant **không có side effect**, còn cần test handler/flow được lắp với fake repositories hoặc Mockito spies:

~~~java
verify(orderWriteRepository, never()).create(any());
verify(outboxRepository, never()).recordOrderPlaced(
    any(), any());
~~~

Hai assertion trên là **phần bổ sung cho test đã invoke handler hoặc IntegrationFlow**, không áp dụng cho test chỉ gọi trực tiếp Validator vì repository chưa được kết nối. Test thực cần dựng toàn bộ đường nhận message, inject input invalid và assert những lời gọi trên.

**Không coi việc Filter trả `false` là bằng chứng method ghi chưa chạy** nếu Filter predicate hoặc một interceptor trước đó đã tạo side effect. Với validation thuần, test `verifyNoInteractions(...)` các collaborator ghi khi rejection xảy ra.

## 40. Test: retry sau rollback và redelivery sau commit

Đối với `TransactionalOrderCommandHandler` ở mục 18:

~~~text
Case A: lỗi trước COMMIT
  inbox marker INSERT
  order INSERT
  throw transient DB exception
  ROLLBACK toàn transaction
  retry same commandId
  → được xử lý lại, đúng một committed order

Case B: lỗi sau COMMIT, trước ACK
  inbox marker + order + outbox COMMIT
  crash before ACK
  broker redelivery same commandId
  → DUPLICATE_COMPLETED / cached receipt
  → không thêm order/outbox record
~~~

Với database thật hoặc Testcontainers:

~~~java
@Test
void redeliveryAfterCommitDoesNotCreateSecondOrder() {
    PlaceOrderCommand command = sampleCommand("C-801");

    OrderReceipt first = transactionalHandler.place(command);
    OrderReceipt second = transactionalHandler.place(command);

    assertEquals(first, second);
    assertEquals(
        1, orderRepository.countByCommandId("C-801"));
    assertEquals(
        1, outboxRepository.countByCommandId("C-801"));
}
~~~

`sampleCommand` và các repository count methods là **test fixtures do ứng dụng triển khai**. Test cần chạy với **mỗi lần gọi qua transaction boundary thực**; nếu cả test method đang nằm trong một `@Transactional` bao ngoài, nó có thể che commit/rollback behavior production.

**Chỉ gọi handler hai lần chưa chứng minh ACK của broker.** Muốn xác minh crash sau commit trước ACK, sử dụng integration test với adapter/container thật và fault injection tại đúng điểm.

## 41. Test concurrency: hai consumers cùng một logical command

Một test tuần tự không phát hiện race:

~~~text
call place(C-801)
call place(C-801)
assert one order
~~~

Cần một test với **hai transactions/threads** cùng tranh chấp:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant DB as Database
    A->>DB: Claim key C-801
    B->>DB: Claim key C-801
    DB-->>B: Wait/conflict on unique key
    A->>DB: Insert order + outbox + COMMIT
    DB-->>B: Duplicate committed key
    B->>DB: Read same fingerprint/result
    Note over A,B: Expected committed order count = 1
~~~

Checklist:

- Dùng unique constraint thật theo `(tenant, operation, commandId)`.
- Test hai concurrent callers có IDs giống nhau.
- Test same key nhưng fingerprint **khác** phải báo conflict.
- Test winner rollback: loser được xử lý/retry khi safe, không bị đánh success giả.
- Test dưới DB isolation level của ứng dụng thực.
- Đặt timeout cho concurrency tests để không treo pipeline.
- Nếu nhiều instances, kiểm thử across processes/nodes chứ không chỉ trong một JVM.

Một method `synchronized` trong singleton bean không giải quyết được idempotency trên cluster hoặc sau restart.

## 42. Test error handling: lỗi handler phải tới đúng boundary

Thử một handler cố tình thất bại:

~~~java
@ServiceActivator(inputChannel = "test.orders.fail")
public OrderReceipt fail(PlaceOrderCommand command) {
    throw new InvalidCommandException("INVALID_ORDER_LINE");
}
~~~

Trong **DirectChannel**, kiểm tra exception/root cause từ `input.send()` hoặc Gateway. Trong **ExecutorChannel**, cần gửi error tới error channel tương ứng và xác minh `ErrorMessage`, cause chain và failed-message context.

Assertions cần có:

1. Lỗi permanent **không retry nóng vô hạn**.
2. Lỗi transient được retry có giới hạn.
3. Invalid command **không tạo business side effect**.
4. Error record có `commandId`, `operation` và `reasonCode` đã sanitize nếu các IDs đáng tin.
5. Gateway không trả success giả hoặc timeout vô nghĩa khi có lỗi xác định.
6. DLQ/quarantine không bị coi là durable khi publish thất bại.
7. Một lỗi ở child handler không làm Aggregator thiếu member vô thời hạn.

**Không mặc định mọi exception đều đi vào global errorChannel.** Hãy test cấu hình thật của poller, adapter, channel, retry advice và error handler được dùng ở production.

## 43. Ma trận kiểm thử method selection và side effects

| Test case | Input/fault | Điều cần chứng minh |
|---|---|---|
| Preview request | `PreviewOrderQuery` | Chỉ `preview()` chạy; không có write |
| Place request | `PlaceOrderCommand` | Chỉ `place()` được chọn |
| Cancel request | `CancelOrderCommand` | Chỉ `cancel()` sau authorization |
| Wrong payload type | JSON/Map/String không đúng command | Không rơi vào fallback ghi |
| Unknown operation | Header `methodName` lạ | Reject; không reflection invoke |
| Untrusted tenant | Header giả mạo tenant | Security rejection |
| Invalid lines | Quantity âm hoặc quá nhiều | Không ghi DB/outbox |
| Duplicate completed command | Cùng `commandId`/fingerprint | Không double write; cached result |
| Same key different payload | Fingerprint mismatch | Conflict và audit |
| Failure before commit | Exception khi ghi order | Rollback cả inbox và order |
| Crash after commit before ACK | Broker redelivery | Không double write |
| Publish before rollback | Event send trước DB rollback | Cần outbox thay thiết kế lỗi |
| Remote timeout | HTTP provider đã commit | Reconcile/cùng idempotency key |
| `@Transactional` self-call | Method nội bộ | Test chứng minh transaction boundary thật |
| Gateway void reply | Caller chờ result | Contract/timeout có chủ đích |
| ExecutorChannel failure | Handler throw trên worker | ErrorMessage/container recovery đúng |
| DLQ unavailable | Quarantine write failure | Không ACK mất công việc |
| Concurrent same key | Hai workers | Unique committed effect |
| Splitter child failure | L2 không thành công | Outcome nhóm chính xác |
| Duplicate aggregate reply | Member L1 lặp | Không release giả |
| Late reply after completion | Result đến chậm | Không kích hoạt side effect lại |
| Restart after delivery | JVM mất state | Idempotency vẫn bền |

**Đừng chỉ assert receipt payload**. Side effects cần được kiểm tra bằng **database row counts, outbox records, external fake-provider call counts, authorization mocks và error-channel events**.

## 44. Observability: thấy được method nào thật sự được gọi

Những metric sau là **đề xuất**, không phải meter mặc định của Spring Integration:

| Metric | Mục đích |
|---|---|
| `service_activator.message.received.count` | Số message đến endpoint |
| `service_activator.method.invoked.count` | Số lần method thực sự chạy |
| `service_activator.method.success.count` | Handler hoàn thành theo contract |
| `service_activator.method.failure.count` | Exception theo nhóm lỗi |
| `service_activator.duplicate.completed.count` | Redelivery đã xử lý |
| `service_activator.idempotency.conflict.count` | Same key, different payload |
| `service_activator.side_effect.committed.count` | Business commits thực |
| `service_activator.outbox.pending.count` | Durable events chưa publish |
| `service_activator.retry.attempts.count` | Retry amplification |
| `service_activator.retry.exhausted.count` | Công việc không tự hoàn tất |
| `service_activator.authorization.rejected.count` | Method bị từ chối vì quyền |
| `service_activator.unexpected_method.count` | Endpoint nhận sai method/type |
| `service_activator.ack.failure.count` | Nguy cơ redelivery |
| `service_activator.duration` | Latency per operation |

Tag nên gồm **tập hữu hạn**: `flowName`, `operation`, `handlerName`, `outcome`, `reasonCode`. **Không dùng `commandId`, `orderId`, email hoặc raw header làm metric label**, vì cardinality và nguy cơ rò dữ liệu.

Structured log có kiểm soát:

~~~text
eventId=EV-801
commandId=C-801
operation=PLACE
endpoint=orders.place
handler=OrderCommandHandler.place
attempt=2
idempotencyState=SUCCEEDED
transactionOutcome=COMMITTED
businessSideEffectCount=0
result=DUPLICATE_COMPLETED
~~~

Một redelivery đã `SUCCEEDED` có thể có **handler invocation count tăng** nhưng **business side effect count không tăng**. Đó là khác biệt quan trọng để điều tra mà metrics chỉ đếm “message processed” không thể hiện.

## 45. Runbook: phát hiện một method được gọi ngoài ý định

Khi nhận thông tin “người dùng chỉ preview nhưng order đã được đặt”:

1. **Tìm message thực** từ transport reference/event ID, xác minh payload type.
2. **Xem channel nhận**: message đi vào `orders.preview` hay `orders.place`?
3. **Xem endpoint binding**: `@ServiceActivator`, `.handle(bean,"method")` hay typed lambda nào được đăng ký?
4. **Xem overloads**: bean có `handle(Object)` hoặc nhiều method cùng tên không?
5. **Xem routing**: operation có được lấy từ untrusted headers/SpEL/reflection không?
6. **Xem authorization**: verified principal/tenant được kiểm tra ở đâu?
7. **Xem validation**: Filter/validator có tạo side effect trước khi reject?
8. **Đối chiếu commits**: order, inventory, outbox và external provider có thay đổi chưa?
9. **Xem retries**: commandId/attemptId có bị đổi; một redelivery có tạo effect mới?
10. **Xem transaction**: `@Transactional` có đi qua Spring proxy và bao cả inbox/domain writes không?
11. **Xem async boundaries**: caller đã ACK khi mới enqueue vào thread pool chưa?
12. **Xem error/compensation**: có permanent failure, unknown remote outcome hoặc DLQ không?
13. **Khắc phục an toàn**: ngăn route sai, reconcile side effects đã xảy ra, dùng compensation theo domain; **không tự xóa inbox markers rồi replay**.
14. **Thêm regression tests**: preview không gọi command, wrong type không vào fallback, retry không double-commit.

**Ưu tiên xác định hiệu ứng nghiệp vụ đã thực sự commit trước khi replay hoặc rollback thủ công.** Exception ở caller không chứng minh remote system chưa xử lý lệnh.

## 46. Bài thực hành: ba command/query endpoints không bị gọi nhầm

Xây mini project **SafeOrderActivator** trong Spring Integration:

1. Định nghĩa `PreviewOrderQuery`, `PlaceOrderCommand` và `CancelOrderCommand` riêng.
2. Đặt tên channels `orders.preview`, `orders.place`, `orders.cancel`.
3. Cấu hình một endpoint `@ServiceActivator` cho preview, một endpoint Java DSL `.handle(bean, "place")` cho command; test không có competing subscribers.
4. Thử tạo overload `handle(Object)` để quan sát rủi ro, sau đó loại bỏ thiết kế mơ hồ.
5. Thêm Filter/Validator thuần trước command handler.
6. Thêm authorization dựa vào trusted principal/tenant.
7. Dùng `@Transactional` cho inbox + order + outbox trong cùng DB.
8. Thêm unique constraint `(tenantId, operation, commandId)` và fingerprint check.
9. Cho handler ném exception trước commit: lần retry phải thành công và marker phải rollback.
10. Inject crash sau commit trước ACK: redelivery không tạo order thứ hai.
11. Cấu hình Retry Advice có giới hạn và error-channel recovery.
12. Thử một Gateway mong reply; không dùng `void` hoặc trả `null` cho request–reply.
13. Chạy một async flow và chứng minh transaction/error boundary thuộc worker thread.
14. Thêm Splitter cho ba line tasks, mỗi child có idempotency key riêng.
15. Thêm Aggregator và failure outcome cho một member lỗi.
16. Test hai consumers đồng thời xử lý cùng command ID.
17. Gắn fake external payment provider, thử timeout sau remote commit; không gửi key mới.
18. Đo invocation count, committed effect count, retry và duplicate metrics.

**Tiêu chí hoàn thành:** một preview không tạo side effect ghi; message sai type/header không gọi nhầm method; command có side effect chỉ chạy sau validation và authorization; duplicate/retry không nhân đôi DB/outbox/remote effect; Gateway/error channel/DLQ đúng semantics; các test chứng minh cả **đúng method** và **đúng hiệu ứng**.

## 47. Những hiểu lầm thường gặp

**“Chỉ cần phương thức có tên `preview` là nó read-only.”** Sai. Cần kiểm tra implementation, collaborators và side effects.

**“`@ServiceActivator` tự chọn method an toàn theo nghiệp vụ.”** Không. Framework invoke theo cấu hình/chữ ký, không tự biết quyền ghi.

**“`handle(bean, "handle")` luôn không mơ hồ.”** Không khi bean có overloads cùng tên và payload/conversion khác nhau.

**“Một `handle(Object)` fallback giúp hệ thống tương thích tốt hơn.”** Có thể che invalid payload và gọi side effect không mong muốn.

**“Header `methodName` là cách linh hoạt để điều khiển service.”** Nguy hiểm khi không có allowlist/trust boundary; có thể trở thành arbitrary invocation.

**“Channel `orders.cancel` đủ chứng minh caller được quyền hủy.”** Không. Channel không thay authorization.

**“Filter validation không có side effect vì chỉ trả Boolean.”** Không nếu predicate gọi `reserve()`/ghi DB.

**“`@Transactional(readOnly=true)` cấm mọi thao tác ghi.”** Không phải cam kết bảo mật tuyệt đối.

**“Có `@Transactional` trên method nội bộ thì self-call luôn kích hoạt proxy.”** Không với cách proxy mặc định.

**“Một message chỉ được gọi handler một lần.”** Không với retry, broker redelivery và workflow replay.

**“RetryAdvice tự làm method idempotent.”** Không; side effect phải được bảo vệ riêng.

**“Một Redis seen marker trước handler nghĩa là business đã hoàn tất.”** Sai nếu handler lỗi và marker không rollback.

**“DB transaction rollback cả HTTP payment.”** Không. Remote side effect có ranh giới riêng.

**“Publish broker trực tiếp trong transaction là atomic.”** Không khi không có protocol transaction liên hệ; outbox thường phù hợp hơn.

**“Method `void` thích hợp cho Gateway chờ reply.”** Thường không; có thể gây timeout.

**“`send()` trả true nghĩa là async handler đã commit.”** Sai nếu worker chưa thực thi.

**“Mọi exception đều đi vào global errorChannel.”** Phụ thuộc sync/async boundary và cấu hình.

**“Một `synchronized` handler là đủ cho idempotency trên cluster.”** Không khi nhiều instances và sau restart.

**“Có đủ N replies nghĩa là đủ N child members.”** Sai khi duplicates; cần manifest và distinct members.

**“Đã ACK là chắc chắn business thành công.”** Có thể chỉ là durable async acceptance, tùy contract/adapter.

## 48. Ghi nhớ

**Chọn method không gây side effect ngoài ý muốn** trong Service Activator đòi hỏi cả **method selection tường minh** và **business side-effect discipline**. Đặt operation rõ trên channel, dùng `@ServiceActivator` ở đúng method, `.handle(bean, "specificMethod")` hoặc typed handler lambda; tránh overload/fallback `handle(Object)` mơ hồ và không cho untrusted message tự chọn method bằng reflection/SpEL.

Hãy tách **query/read-only** khỏi **command/write**, validate và authorize trước side effect, dùng một **transaction** cho inbox/domain/outbox khi cùng database, và bảo vệ logical command bằng durable idempotency key xuyên retry/redelivery. Với external payment/HTTP, dùng remote idempotency key và reconciliation thay vì giả định JDBC rollback bao hết.

Kiểm tra cả **reply contract**, `DirectChannel` so với async/error channel, ACK/DLQ, Splitter/Aggregator correlation và concurrency. Test không chỉ “handler trả đúng `OrderReceipt`”, mà còn phải chứng minh **method ghi không chạy khi không được phép**, **commit không lặp khi retry** và **outcome lỗi không biến thành success giả**. Đó là nền tảng để Service Activator vừa linh hoạt vừa đáng tin cậy trong hệ thống message-driven.

### Tài liệu tham khảo

- Enterprise Integration Patterns, **Service Activator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingAdapter.html
- Spring Integration Reference, **Service Activator**: https://docs.spring.io/spring-integration/reference/service-activator.html
- Spring Integration Reference, **Message Filter**: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference, **Router**: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference, **Gateway**: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Idempotent Receiver**: https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
- Spring Framework Reference, **Declarative Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
