# Phạm vi transaction trong một lần gọi công cụ

Một tool call có thể đọc nhiều bảng, cập nhật nhiều bản ghi và ghi audit event. Những thao tác thuộc cùng một thay đổi nghiệp vụ thường cần thành công hoặc thất bại cùng nhau. Spring AI giúp ứng dụng dispatch ToolCallback và đưa kết quả về mô hình, nhưng bản thân tool-calling loop không tự tạo một database transaction cho mỗi tool call.

Ứng dụng phải quyết định ranh giới transaction. Với một tool thực hiện một use case nghiệp vụ, ranh giới phù hợp thường là một service method ngắn, bao gồm các thao tác database cần atomic. Khi service method kết thúc, transaction commit hoặc rollback trước khi tool result được chuyển về mô hình. Những lần gọi model tiếp theo và các hệ thống bên ngoài nằm ngoài transaction đó.

Bài này dùng Spring AI 2.1.0 và Spring Framework làm mốc. Nội dung tập trung vào:

- Ranh giới của một lần thực thi ToolCallback và một transaction nghiệp vụ.
- Cách đặt @Transactional trong service được Spring quản lý.
- Phạm vi của REQUIRED, REQUIRES_NEW và NESTED.
- Rollback, exception và cách xử lý lỗi tool.
- Các giới hạn khi tool gọi nhiều hệ thống hoặc nhiều tool call cùng một lượt.
- Kiểm thử để chứng minh transaction thực sự commit hoặc rollback.

## Một tool invocation không tự động là một transaction

Trong Spring AI 2.x, ToolCallingAdvisor quản lý vòng gọi công cụ. Khi model trả về tool call, advisor chuyển yêu cầu đến ToolCallingManager. Manager tìm ToolCallback tương ứng, thực thi callback, nối tool result vào conversation history rồi gọi model tiếp. Chu trình lặp cho đến khi model trả về câu trả lời không còn tool call.

Luồng này mô tả việc điều phối AI. Nó không định nghĩa ranh giới transaction của database. ToolCallback chỉ là hợp đồng thực thi công cụ và trả kết quả dạng String; transaction phụ thuộc vào code nghiệp vụ và transaction manager mà ứng dụng cấu hình.

~~~mermaid
sequenceDiagram
    participant Model as Mô hình
    participant Advisor as ToolCallingAdvisor
    participant Manager as ToolCallingManager
    participant Tool as ToolCallback
    participant Service as Application Service
    participant DB as Database

    Model->>Advisor: Tool call + arguments
    Advisor->>Manager: Dispatch tool call
    Manager->>Tool: call(input, context)
    Tool->>Service: Gọi use case
    activate Service
    Service->>DB: Begin transaction / đọc và ghi
    DB-->>Service: Kết quả truy vấn
    Service->>DB: Commit hoặc rollback
    DB-->>Service: Transaction kết thúc
    Service-->>Tool: DTO hoặc domain result
    deactivate Service
    Tool-->>Manager: Tool result
    Manager-->>Advisor: Tool execution result
    Advisor->>Model: Tool response trong lịch sử
    Model-->>Advisor: Câu trả lời hoặc tool call tiếp theo
~~~

Các bước quan trọng:

1. Model đề xuất tool name và arguments. Chưa có transaction nghiệp vụ nào bắt đầu chỉ vì model tạo ra tool call.
2. ToolCallingManager dispatch callback.
3. Callback gọi service nghiệp vụ.
4. Spring transaction interceptor mở hoặc tham gia transaction khi lời gọi đi qua proxy của service.
5. Service thực hiện các thao tác database và kết thúc transaction.
6. Callback nhận kết quả rồi Spring AI chuyển kết quả thành tool response.
7. Advisor gửi tool response cho model để tiếp tục hội thoại.

Một transaction nên bao trùm các thao tác database cần atomic trong use case của tool. Nó không nên bao trùm thời gian model suy luận, stream token, chờ người dùng phê duyệt hoặc toàn bộ vòng ToolCallingAdvisor.

## Xác định ranh giới theo use case nghiệp vụ

Đừng quyết định transaction chỉ dựa trên số câu lệnh SQL hoặc số repository được gọi. Hãy bắt đầu từ invariant nghiệp vụ: dữ liệu nào phải cùng thay đổi hoặc cùng không thay đổi?

Ví dụ xác nhận đơn hàng:

- Đơn hàng chuyển từ PENDING sang CONFIRMED.
- Các dòng reservation được ghi nhận.
- Lịch sử thay đổi trạng thái được thêm.
- Outbox event OrderConfirmed được lưu cùng database.

Nếu bốn thay đổi này nằm trong cùng một database và cần atomic, chúng nên tham gia một transaction. Nếu chỉ cập nhật trạng thái đơn hàng nhưng không ghi reservation hoặc event, dữ liệu có thể rơi vào trạng thái không nhất quán.

| Phạm vi | Nên nằm trong transaction? | Lý do |
|---|---|---|
| Đọc trạng thái đơn và kiểm tra điều kiện cập nhật | Có, nếu cần cùng snapshot/lock với thao tác ghi. | Tránh kiểm tra một trạng thái rồi cập nhật dựa trên trạng thái đã cũ. |
| Cập nhật đơn hàng và các dòng liên quan trong cùng database | Có. | Các thay đổi tạo thành một use case atomic. |
| Ghi audit/outbox row trong cùng database | Thường có. | Không để dữ liệu chính commit nhưng mất dấu vết hoặc sự kiện cần phát. |
| Gọi model để diễn giải tool result | Không. | Network/model latency không thuộc transaction dữ liệu. |
| Gọi API thanh toán hoặc gửi email | Không nằm trong local DB transaction. | Transaction manager không thể rollback side effect ở hệ thống ngoài. |
| Stream câu trả lời cuối về browser | Không. | Stream có thể kéo dài và bị hủy sau khi transaction đã commit. |
| Chờ người dùng xác nhận | Không. | Không giữ connection, lock hoặc transaction trong lúc chờ con người. |

### Một tool nên đại diện cho một thao tác nghiệp vụ có ý nghĩa

Nếu model phải gọi ba tool liên tiếp để hoàn thành một thao tác mà nghiệp vụ yêu cầu atomic, không nên dựa vào việc model sẽ luôn gọi đúng thứ tự hoặc không dừng giữa chừng.

Ví dụ, nếu xác nhận đơn cần cập nhật order, giữ tồn kho và tạo audit event, hãy cung cấp một tool confirmOrder. Tool này gọi một application service thực hiện cả ba thao tác trong cùng transaction.

Nếu ba bước thực sự độc lập, chúng có thể là ba tool riêng và có transaction riêng. Nếu chúng là một workflow nhiều hệ thống, hãy dùng workflow/saga và trạng thái bền vững; một transaction database không thể bao trùm toàn bộ quá trình.

## Đặt transaction ở application service

Một cách triển khai dễ kiểm soát là để phương thức @Tool làm adapter mỏng: nhận arguments, lấy context đáng tin cậy, gọi service nghiệp vụ và trả DTO. Service riêng chịu trách nhiệm transaction.

Ví dụ:

~~~java
public record ConfirmOrderResult(
        String orderId,
        String status,
        String eventId) {
}

@Component
class OrderTools {

    private final OrderCommandService orderCommandService;

    OrderTools(OrderCommandService orderCommandService) {
        this.orderCommandService = orderCommandService;
    }

    @Tool(description = "Xác nhận đơn hàng nếu đơn đang ở trạng thái có thể xác nhận")
    public ConfirmOrderResult confirmOrder(
            @ToolParam(description = "Mã đơn hàng") String orderId,
            ToolContext toolContext) {

        String tenantId = (String) toolContext.getContext().get("tenantId");
        String actorId = (String) toolContext.getContext().get("actorId");

        return orderCommandService.confirm(orderId, tenantId, actorId);
    }
}
~~~

Service nghiệp vụ:

~~~java
@Service
class OrderCommandService {

    private final OrderRepository orderRepository;
    private final ReservationRepository reservationRepository;
    private final OrderEventRepository orderEventRepository;
    private final OutboxRepository outboxRepository;

    OrderCommandService(
            OrderRepository orderRepository,
            ReservationRepository reservationRepository,
            OrderEventRepository orderEventRepository,
            OutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.reservationRepository = reservationRepository;
        this.orderEventRepository = orderEventRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public ConfirmOrderResult confirm(
            String orderId,
            String tenantId,
            String actorId) {

        Order order = orderRepository.findByIdAndTenantId(orderId, tenantId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm(actorId);
        reservationRepository.markForOrderConfirmed(orderId);

        OrderEvent event = OrderEvent.confirmed(orderId, actorId);
        orderEventRepository.save(event);

        OutboxMessage message = OutboxMessage.from(event);
        outboxRepository.save(message);

        return new ConfirmOrderResult(
                orderId,
                order.getStatus().name(),
                event.getId()
        );
    }
}
~~~

Lời gọi từ OrderTools sang OrderCommandService đi qua Spring bean proxy. Transaction interceptor mở transaction trước khi vào method service và kết thúc khi method trả về hoặc ném exception. Các repository dùng cùng transaction manager và cùng resource sẽ tham gia transaction đó theo propagation mặc định REQUIRED.

Đây là một ranh giới rõ ràng: tool adapter không quản lý transaction; service quản lý use case; repository không tự tạo transaction độc lập nếu không cần.

### Vì sao không nên chỉ đặt @Transactional ở mọi repository?

Nếu mỗi repository method tự mở transaction, từng thao tác có thể commit riêng. Khi thao tác thứ ba thất bại, hai thao tác đầu đã commit và dữ liệu bị cập nhật một phần.

Đặt transaction ở service facade giúp nhiều repository operation cùng tham gia một transaction. Repository vẫn có thể có transaction metadata, nhưng thông thường các method được gọi từ service sẽ tham gia transaction hiện tại bằng REQUIRED.

## Proxy và những trường hợp @Transactional không có hiệu lực

Spring dùng AOP proxy để áp dụng transaction interceptor. Annotation @Transactional chỉ là metadata; transaction hoạt động khi lời gọi đi qua bean proxy có transaction management được bật và có transaction manager phù hợp.

Các lỗi thường gặp:

| Trường hợp | Hệ quả |
|---|---|
| Tạo tool bằng new OrderCommandService(...) | Không có Spring proxy; @Transactional không được áp dụng. |
| Method trong cùng class tự gọi method @Transactional khác | Self-invocation không đi qua proxy mặc định; transaction của method bên trong không được mở riêng. |
| Đặt @Transactional trên private/static tool method | Proxy-based transaction không chặn được lời gọi theo cách mong đợi. |
| Không bật transaction management hoặc thiếu transaction manager | Annotation không tạo transaction runtime. |
| Gọi một bean không được Spring quản lý | Không có transaction advice. |
| Chạy data access trên thread mới với imperative transaction | Transaction thread-bound không tự truyền sang thread mới. |

Spring AI cho phép @Tool trên nhiều visibility, kể cả private hoặc static method. Khả năng phát hiện và gọi tool không có nghĩa mọi method đó đều là một transactional proxy boundary. Cách ổn định là để tool method gọi một public service method trên bean Spring riêng như ví dụ trên.

Kiểm thử rollback thực tế quan trọng hơn chỉ kiểm tra annotation có mặt. Hãy xác minh dữ liệu đã rollback trong database sau khi service ném exception.

## Propagation: transaction của service tham gia như thế nào?

Spring mặc định dùng PROPAGATION_REQUIRED. Nếu chưa có transaction, service tạo transaction mới; nếu đã có transaction cùng resource và thread/context, service tham gia transaction hiện tại.

| Propagation | Hành vi | Dùng khi |
|---|---|---|
| REQUIRED | Tham gia transaction hiện tại hoặc tạo transaction mới. | Mặc định phù hợp cho application service và repository cùng use case. |
| REQUIRES_NEW | Tạm dừng transaction hiện tại và tạo transaction vật lý độc lập. | Một ghi nhận cần commit độc lập với transaction ngoài, sau khi đánh giá kỹ tài nguyên. |
| NESTED | Tạo savepoint trong cùng transaction vật lý nếu transaction manager hỗ trợ. | Cần rollback một phần scope JDBC nhưng outer transaction tiếp tục. |
| SUPPORTS | Tham gia transaction nếu có; nếu không thì chạy không transaction. | Operation có thể chạy trong hoặc ngoài transaction mà không yêu cầu bắt buộc. |
| MANDATORY | Yêu cầu phải có transaction hiện tại. | Một bước nội bộ chỉ hợp lệ khi caller đã mở transaction. |
| NOT_SUPPORTED | Tạm dừng transaction hiện tại và chạy không transaction. | Tác vụ không nên giữ transaction hiện có, sau khi đánh giá tác động. |

### REQUIRED là lựa chọn thường dùng cho một tool use case

Nếu confirm() gọi orderRepository, reservationRepository và outboxRepository, cả ba cùng tham gia transaction của confirm() khi dùng cùng transaction manager. Một lỗi khiến transaction bị đánh dấu rollback-only sẽ ảnh hưởng đến toàn bộ transaction vật lý.

Nếu inner scope đánh dấu rollback-only nhưng outer scope vẫn cố commit, Spring có thể ném UnexpectedRollbackException để caller không tưởng rằng transaction đã commit.

### REQUIRES_NEW không phải cách mặc định để tách mọi tool call

REQUIRES_NEW tạo transaction vật lý độc lập. Transaction ngoài bị suspend; transaction mới cần tài nguyên riêng, thường là một connection khác. Nếu nhiều request đồng thời đều giữ transaction ngoài rồi chờ connection cho REQUIRES_NEW, connection pool có thể cạn hoặc deadlock.

Chỉ dùng khi có yêu cầu commit độc lập rõ ràng, ví dụ ghi một audit record cần tồn tại ngay cả khi transaction nghiệp vụ bên ngoài rollback. Cần cân nhắc thứ tự, tính đúng đắn của audit và cấu hình connection pool.

### NESTED thường dựa trên savepoint JDBC

NESTED không phải một transaction độc lập. Nó thường dùng savepoint trong cùng transaction vật lý, cho phép rollback phần nested scope mà outer scope tiếp tục. Hỗ trợ phụ thuộc transaction manager và JDBC resource; không giả định mọi database hoặc reactive transaction manager đều hỗ trợ.

## Rollback rules và cách tool xử lý exception

Theo mặc định của Spring:

- RuntimeException và Error làm transaction rollback.
- Checked exception không tự làm transaction rollback.
- Có thể cấu hình rollbackFor/noRollbackFor để điều chỉnh.

Ví dụ:

~~~java
@Transactional(rollbackFor = InventoryUnavailableException.class)
public ConfirmOrderResult confirm(String orderId) throws InventoryUnavailableException {
    // Đọc order, giữ tồn kho, cập nhật order và ghi event.
}
~~~

Nếu nghiệp vụ cần rollback khi gặp checked exception, khai báo rollbackFor rõ ràng. Không dựa vào tên exception hoặc suy đoán rằng mọi exception đều rollback.

### Không nuốt exception rồi trả lỗi dạng bình thường nếu cần rollback

Đoạn code sau có thể commit các thay đổi trước đó vì exception đã bị bắt và method trả về bình thường:

~~~java
@Transactional
public ToolResult updateOrder(String orderId) {
    orderRepository.updateStatus(orderId, "PROCESSING");

    try {
        reservationService.reserve(orderId);
        return ToolResult.success();
    }
    catch (ReservationException ex) {
        return ToolResult.failure("Không thể giữ hàng");
    }
}
~~~

Nếu muốn cả thay đổi trạng thái order rollback, hãy để exception phù hợp thoát khỏi transactional method:

~~~java
@Transactional
public ToolResult updateOrder(String orderId) {
    orderRepository.updateStatus(orderId, "PROCESSING");
    reservationService.reserve(orderId);
    return ToolResult.success();
}
~~~

Hoặc nếu cần bắt lỗi để bổ sung ngữ cảnh, phải đánh dấu transaction rollback-only theo cách có chủ đích hoặc dùng rollback rule phù hợp. Không trả một failure DTO rồi kỳ vọng Spring tự hiểu rằng cần rollback.

### ToolExecutionExceptionProcessor nằm sau ranh giới service

Spring AI bọc lỗi thực thi tool trong ToolExecutionException và chuyển tới ToolExecutionExceptionProcessor. Processor có thể:

- Tạo error message để gửi lại mô hình, cho phép mô hình giải thích hoặc thử cách khác.
- Ném exception để caller xử lý.

Trong cấu hình mặc định Spring AI 2.1.0, thông điệp của RuntimeException có thể được gửi lại mô hình; có thể đặt spring.ai.tools.throw-exception-on-error=true để ném lỗi cho caller.

Điều này không thay đổi rollback rule của Spring transaction. Nếu RuntimeException thoát khỏi service proxy, transaction có thể rollback trước khi lỗi được chuyển thành tool error message. Nhưng nếu service bắt exception và trả failure DTO, transaction có thể commit trước khi Spring AI nhìn thấy kết quả đó.

Không gửi exception message thô chứa SQL, tên bảng, stack trace, internal URL hoặc secret cho mô hình. Hãy dùng lỗi nghiệp vụ đã lọc và giữ chi tiết kỹ thuật trong log an toàn.

## Thời điểm commit và tool result serialization

Với một tool method trả DTO, service transaction thường kết thúc trước khi Spring AI chuyển DTO thành String để tạo tool response message:

1. Tool method gọi transactional service.
2. Service commit hoặc rollback.
3. Tool method nhận DTO hoặc exception.
4. Tool callback/result converter serialize DTO thành String.
5. ToolCallingManager thêm kết quả vào conversation history.
6. Advisor gọi model tiếp.

Điều này tạo ra một trường hợp cần thiết kế trước: database đã commit nhưng serialization hoặc request model tiếp theo thất bại. Người dùng có thể không nhận được câu trả lời dù thao tác nghiệp vụ đã thành công.

Với tool có side effect:

- Tạo operation ID/idempotency key trước khi thực thi.
- Lưu kết quả và trạng thái operation cùng transaction nếu phù hợp.
- Nếu client/model retry, tra cứu operation cũ và trả kết quả đã lưu thay vì thực thi lại.
- Có API truy vấn trạng thái theo operation ID khi kết quả trả về bị mất.

Không xem việc mô hình chưa nhận được tool result là bằng chứng transaction đã rollback.

## Không giữ transaction qua model loop

ToolCallingAdvisor có thể gọi model nhiều lần và thực thi nhiều tool call trước khi trả câu trả lời cuối. Đừng đặt @Transactional trên một method bao trùm toàn bộ ChatClient.call() hoặc toàn bộ workflow nếu mục tiêu chỉ là atomic một thao tác database.

Trong blocking flow, transaction imperative dùng thread-bound context. Nếu một transaction bên ngoài còn mở trong lúc ChatClient chạy loop, các service call dùng REQUIRED trên cùng thread có thể tham gia transaction ngoài. Điều đó có thể giữ connection và lock trong khi ứng dụng chờ network/model hoặc nhiều vòng suy luận.

Trong streaming/reactive flow, reactive transaction dùng Reactor Context; không thể suy ra rằng transaction thread-bound tự truyền qua scheduler hoặc thread mới. Các thao tác tham gia reactive transaction phải nằm trong cùng reactive pipeline/context. Tool method đồng bộ hoặc callback chạy trên thread khác không tự động tham gia transaction reactive của caller.

Thiết kế nên là:

- Mỗi service use case mở một transaction ngắn quanh các thao tác database cần atomic.
- Transaction kết thúc trước khi tool result được gửi lại model.
- Mỗi tool invocation tiếp theo mở transaction riêng nếu cần.
- Nếu cần một workflow nhiều bước, lưu trạng thái workflow bền vững và phối hợp qua saga/outbox hoặc cơ chế phù hợp.

## Isolation, locking và cập nhật đồng thời

Transaction không tự giải quyết mọi race condition. Isolation mặc định thường là ISOLATION_DEFAULT, nghĩa là dùng cấu hình của transaction manager/database. Hãy xác định invariant cần bảo vệ:

| Vấn đề | Cơ chế thường dùng |
|---|---|
| Hai request cùng cập nhật một order | Optimistic locking bằng @Version hoặc pessimistic row lock. |
| Hai request cùng giữ đơn vị tồn kho cuối cùng | Atomic conditional update, row lock hoặc constraint phù hợp. |
| Đọc rồi cập nhật dựa trên trạng thái có thể thay đổi | Kiểm tra trạng thái trong transaction và dùng locking/version. |
| Không cho phép trùng mã nghiệp vụ | Unique constraint ở database, không chỉ kiểm tra bằng Java trước insert. |
| Một tool được retry sau timeout | Idempotency key và operation ledger. |
| Transaction giữ lock quá lâu | Thu hẹp phạm vi transaction, không gọi model/API ngoài trong transaction. |

### Optimistic locking

Với entity có version:

~~~java
@Entity
class Order {

    @Id
    private String id;

    @Version
    private long version;

    private OrderStatus status;
}
~~~

Nếu hai transaction cùng đọc một version và cùng ghi, transaction cập nhật sau có thể gặp optimistic locking failure. Ứng dụng phải quyết định retry, trả conflict hoặc đọc lại trạng thái rồi xử lý.

### Pessimistic locking

Khi cần khóa bản ghi trong thời gian ngắn để kiểm tra và cập nhật, repository có thể dùng lock mode phù hợp:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select o from Order o where o.id = :id and o.tenantId = :tenantId")
Optional<Order> findForUpdate(
        @Param("id") String id,
        @Param("tenantId") String tenantId);
~~~

Lock chỉ bảo vệ trong transaction và phụ thuộc database. Không giữ pessimistic lock trong lúc gọi model hoặc đợi một tool khác.

## Một transaction không thể tự bao trùm hệ thống bên ngoài

Một tool có thể cập nhật database rồi gọi API thanh toán, gửi email hoặc publish message. Transaction manager của database không thể tự rollback side effect ở dịch vụ khác.

Ví dụ nguy hiểm:

~~~java
@Transactional
public PaymentResult payOrder(String orderId) {
    Order order = orderRepository.findById(orderId).orElseThrow();
    order.markPaymentPending();

    paymentClient.capture(order.getPaymentReference());

    order.markPaid();
    return PaymentResult.paid(orderId);
}
~~~

Nếu payment provider capture thành công nhưng database commit thất bại, hệ thống có thể thu tiền nhưng order chưa được đánh dấu PAID. Ngược lại, timeout khi gọi provider không cho biết provider đã xử lý hay chưa.

Đừng giả định @Transactional làm hai hệ thống commit/rollback cùng nhau. Hãy dùng idempotency key của provider, lưu operation state, đối soát kết quả và áp dụng outbox/saga/compensation khi workflow cần phối hợp nhiều hệ thống. Phần thiết kế outbox và compensation có thể được triển khai như một chủ đề riêng.

## Timeout và read-only transaction

Một transaction của tool nên có timeout phù hợp với thời gian xử lý database, không phải toàn bộ thời gian AI suy luận:

~~~java
@Transactional(timeout = 5)
public OrderSnapshot loadOrder(String orderId, String tenantId) {
    return orderRepository.findSnapshot(orderId, tenantId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));
}

@Transactional(readOnly = true)
public OrderSnapshot findOrder(String orderId, String tenantId) {
    return orderRepository.findSnapshot(orderId, tenantId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));
}
~~~

readOnly=true là hint cho transaction manager/provider và có thể giúp tối ưu truy cập dữ liệu. Không coi nó là cơ chế authorization hoặc bảo đảm tuyệt đối rằng database không thể ghi.

Timeout có thể không được hỗ trợ đồng nhất bởi mọi transaction manager/resource. Hãy kiểm tra hành vi của database driver và cấu hình thực tế. Timeout của transaction cũng khác timeout của model request, HTTP client hoặc toàn workflow.

## Khi một response có nhiều tool call

Một response của model có thể chứa nhiều tool call. ToolCallingManager dispatch các callback tương ứng, nhưng không có một transaction chung mặc định bao trùm tất cả tool call chỉ vì chúng nằm trong cùng một assistant response.

Ví dụ model đề xuất:

1. getOrderDetails(orderId)
2. getShipmentStatus(orderId)
3. addOrderNote(orderId, note)

Mỗi invocation có thể dùng transaction riêng. Nếu bước 3 thất bại, kết quả đọc từ bước 1 và 2 vẫn hợp lệ; không có nghĩa các thao tác trước phải rollback.

Nếu ba bước phải thành công cùng nhau, hãy xây dựng một tool command cấp use case và một service transaction cho các thay đổi local atomic. Nếu chúng gồm nhiều hệ thống hoặc cần chờ, dùng workflow bền vững và compensation. Không dựa vào mô hình để tạo một transaction kéo dài qua nhiều tool call.

## Kiểm thử transaction của tool

Không chỉ kiểm tra service trả về đúng DTO. Cần xác minh dữ liệu commit/rollback trong database và kiểm tra transaction có thực sự được kích hoạt qua Spring proxy.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Một tool cập nhật hai bảng trong cùng service | Cả hai thay đổi commit cùng nhau. |
| Lỗi sau lần ghi đầu tiên | Tất cả thay đổi trong transaction rollback. |
| Checked exception | Rollback chỉ xảy ra khi rollbackFor được cấu hình phù hợp. |
| Service bắt exception và trả failure DTO | Kiểm tra rõ transaction commit hay rollback theo policy. |
| Tool được tạo bằng new thay vì Spring bean | Test phát hiện transaction proxy không hoạt động. |
| Self-invocation tới method @Transactional | Test chứng minh lời gọi nội bộ không tạo transaction mới trong proxy mode. |
| REQUIRED trong transaction ngoài | Service tham gia transaction hiện tại. |
| REQUIRES_NEW | Inner transaction commit/rollback độc lập với outer transaction. |
| NESTED với savepoint | Chỉ nested scope rollback khi transaction manager/database hỗ trợ. |
| Hai request cập nhật cùng bản ghi | Optimistic/pessimistic locking bảo vệ invariant. |
| Tool result serialization thất bại sau commit | Operation đã commit vẫn được truy vấn lại bằng operation ID. |
| Model call tiếp theo thất bại | Transaction tool trước đó vẫn ở trạng thái commit đã ghi nhận. |
| Tool gọi API bên ngoài rồi DB rollback | Test xác minh API ngoài không tự rollback và policy đối soát được kích hoạt. |
| Nhiều tool call trong một response | Không giả định chúng dùng chung một transaction. |
| Transaction timeout | Transaction kết thúc theo hành vi thực tế của transaction manager. |

### Kiểm thử rollback bằng dữ liệu thật trong test transaction

Một bài test có thể kiểm tra cả số bản ghi trước và sau lỗi:

~~~java
@SpringBootTest
class OrderCommandServiceTest {

    @Autowired
    OrderCommandService service;

    @Autowired
    OrderRepository orderRepository;

    @Autowired
    ReservationRepository reservationRepository;

    @Test
    void rollsBackAllChangesWhenReservationFails() {
        String orderId = "ORD-100";
        seedPendingOrder(orderId);

        assertThatThrownBy(() ->
                service.confirm(orderId, "tenant-a", "user-1"))
                .isInstanceOf(ReservationException.class);

        Order order = orderRepository.findById(orderId).orElseThrow();
        assertThat(order.getStatus()).isEqualTo(OrderStatus.PENDING);
        assertThat(reservationRepository.existsForOrder(orderId)).isFalse();
    }
}
~~~

Test này cần cấu hình fake reservation failure tại đúng thời điểm. Nếu test method bên ngoài cũng được gắn @Transactional và tự rollback khi kết thúc, hãy chú ý cách dữ liệu được seed, flush và đọc lại để không nhầm rollback của test với rollback của service. Có thể dùng test không transactional hoặc kiểm tra transaction boundary qua integration test riêng.

## Bài tập thực hành

Xây dựng tool confirmOrder:

1. Tool nhận orderId và lấy tenantId/actorId từ ToolContext đáng tin cậy.
2. Tool gọi OrderCommandService thay vì trực tiếp thực hiện nhiều repository operation.
3. Service có @Transactional và cập nhật order, reservation, audit event trong cùng database.
4. Tạo một lỗi sau lần ghi đầu tiên và xác minh tất cả thay đổi rollback.
5. Thử checked exception và cấu hình rollbackFor.
6. Thử bắt exception rồi trả failure DTO để quan sát transaction có commit hay không.
7. Thử REQUIRED và REQUIRES_NEW để thấy sự khác biệt về transaction vật lý.
8. Thêm @Version để kiểm thử hai request xác nhận cùng một đơn.
9. Thêm idempotency key để một tool call retry không xác nhận hoặc ghi event trùng.
10. Mô phỏng lỗi xảy ra sau commit nhưng trước khi model nhận tool result; truy vấn lại operation để trả kết quả cũ.

Bạn hoàn thành khi có thể chỉ ra transaction bắt đầu tại service method nào, những repository operation nào tham gia, điều gì làm transaction rollback và trạng thái nào vẫn tồn tại sau khi tool result hoặc model call gặp lỗi.

## Danh sách kiểm tra trước khi triển khai

- [ ] Mỗi tool command có use case và invariant nghiệp vụ rõ ràng.
- [ ] Transaction bao trùm các thao tác database cần atomic trong use case.
- [ ] Tool method là adapter mỏng và gọi service bean qua Spring proxy.
- [ ] Không tạo transactional service bằng new hoặc dựa vào self-invocation.
- [ ] Không mở transaction bao trùm ChatClient model loop hoặc thời gian chờ người dùng.
- [ ] Các repository cùng resource tham gia transaction service theo propagation phù hợp.
- [ ] Đã chọn REQUIRED, REQUIRES_NEW hoặc NESTED dựa trên yêu cầu thật.
- [ ] Đã cấu hình rollbackFor cho checked exception khi cần.
- [ ] Không bắt exception rồi trả failure result nếu vẫn kỳ vọng tự động rollback.
- [ ] ToolExecutionExceptionProcessor không bị nhầm với rollback policy của transaction.
- [ ] Tool result serialization/model continuation thất bại không làm ứng dụng thực thi side effect lần nữa.
- [ ] Có idempotency key và operation lookup cho command có side effect.
- [ ] Đã kiểm tra isolation, optimistic/pessimistic locking và unique constraints.
- [ ] Không gọi model hoặc dịch vụ ngoài trong transaction database ngắn.
- [ ] Không giả định transaction local rollback được payment, email hoặc message đã gửi.
- [ ] Có test commit, rollback, proxy, propagation, concurrency và lỗi sau commit.

Transaction trong một lần gọi công cụ nên đại diện cho một use case dữ liệu có thể commit hoặc rollback rõ ràng. Spring AI điều phối tool call và conversation; application service quyết định phạm vi atomic của dữ liệu. Giữ transaction ngắn, đặt ranh giới qua Spring proxy và xử lý riêng các tác động ngoài database giúp kết quả tool nhất quán ngay cả khi model loop tiếp tục, thất bại hoặc bị retry.

## Tài liệu tham khảo

- [Spring AI 2.1.0 – Tool Calling và ToolCallback lifecycle](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework – Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework – Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring AI 2.1.0 – Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
