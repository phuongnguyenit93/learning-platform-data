# Bổ sung tác vụ nền dùng lại ca sử dụng đang có

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, trong chương **Thực hành hệ thống đơn hàng**. Module hướng tới cách tổ chức phần mềm theo kiến trúc phân tầng, trong đó presentation tiếp nhận yêu cầu, application điều phối ca sử dụng, business/domain bảo vệ quy tắc và data access/infrastructure làm việc với cơ sở dữ liệu hoặc hệ thống bên ngoài. Khi bổ sung tác vụ nền, mục tiêu là thêm một cách kích hoạt công việc mà vẫn dùng lại hành vi ứng dụng đã có, giữ nguyên quy tắc nghiệp vụ và quản lý đúng transaction, lỗi, tính lặp và tính nhất quán.

Một tác vụ nền có thể được kích hoạt bởi lịch chạy, message từ broker, yêu cầu vận hành hoặc một quy trình khác. Dù nguồn kích hoạt khác HTTP, nó vẫn có thể gọi cùng application use case mà controller đang dùng. Nhờ vậy, một hành vi như xác nhận đơn hàng, giải phóng giữ chỗ hoặc tạo hóa đơn chỉ có một nơi điều phối và bảo vệ quy tắc.

## 1. Vì sao tác vụ nền nên dùng lại ca sử dụng?

Giả sử hệ thống đơn hàng đã có chức năng xác nhận đơn. Người dùng có thể xác nhận qua REST API sau khi kiểm tra điều kiện. Sau đó, nghiệp vụ bổ sung yêu cầu tự động xác nhận những đơn đủ điều kiện vào một thời điểm nhất định, hoặc xử lý đơn được phát ra từ một message.

Nếu viết một luồng xử lý riêng trong scheduler, nhóm có thể vô tình nhân đôi các bước:

- Tải đơn hàng và kiểm tra trạng thái.
- Kiểm tra quyền hoặc điều kiện nghiệp vụ.
- Tính toán dữ liệu liên quan.
- Cập nhật tồn kho hoặc trạng thái.
- Ghi dữ liệu và phát sự kiện.

Sau một thời gian, luồng HTTP có thể được cập nhật quy tắc mới nhưng tác vụ nền vẫn dùng logic cũ. Kết quả là cùng một hành động nghiệp vụ nhưng cho kết quả khác nhau tùy cách kích hoạt.

Nên tách rõ hai việc:

- **Trigger/adapter:** quyết định khi nào công việc được gọi, đọc payload hoặc tìm các ứng viên cần xử lý, rồi chuyển thành command.
- **Application use case:** thực hiện ca sử dụng, phối hợp repository/gateway, gọi domain và xác định transaction boundary.

Tác vụ nền không nên gọi controller để tái sử dụng nghiệp vụ. Controller là adapter HTTP, có trách nhiệm xử lý URL, header, request/response và mã trạng thái. Scheduler hoặc message consumer là adapter khác. Cả hai cùng gọi application contract.

## 2. Nhìn luồng theo kiến trúc phân tầng

Một luồng đồng bộ và một luồng nền có thể cùng đi vào một use case:

```text
                 +----------------------+
HTTP request --->| OrderController      |
                 +----------+-----------+
                            |
                            |
                            v
                 +----------------------+
                 | ConfirmOrderUseCase  |
                 | Application          |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Domain: Order        |
                 | Business rules       |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Repository / Outbox  |
                 | Data access adapter  |
                 +----------+-----------+
                            |
                            v
                         Database

                 +----------------------+
Scheduler ------>| OrderConfirmationJob |
                 +----------+-----------+
                            |
                            +-----------> ConfirmOrderUseCase

                 +----------------------+
Message -------->| OrderMessageConsumer |
                 +----------+-----------+
                            |
                            +-----------> ConfirmOrderUseCase
```

Controller, scheduler và message consumer chỉ khác nhau ở cách nhận tín hiệu và chuyển đổi dữ liệu. Use case không cần biết nó được gọi từ HTTP, cron hay broker. Domain không cần biết thread nào hoặc lịch nào đã kích hoạt thao tác.

Đây là ranh giới logic. Các adapter có thể chạy trong cùng một ứng dụng Spring Boot, hoặc worker có thể được đóng gói thành một tiến trình triển khai riêng. Việc tách tiến trình là quyết định triển khai; nó không đòi hỏi phải viết lại use case.

## 3. Thiết kế application use case có thể dùng từ nhiều adapter

Use case nên nhận một command chứa đủ dữ liệu để thực hiện hành động. Không nên truyền trực tiếp `HttpServletRequest`, HTTP DTO, `SecurityContext` hoặc message payload vào domain/application core.

Ví dụ:

```java
public record ConfirmOrderCommand(
        OrderId orderId,
        ActorId actorId,
        String correlationId
) {}

public record ConfirmOrderResult(
        OrderId orderId,
        OrderStatus status
) {}

public interface ConfirmOrderUseCase {
    ConfirmOrderResult handle(ConfirmOrderCommand command);
}
```

Command biểu diễn ý định xác nhận một đơn hàng. `actorId` giúp use case biết ai hoặc thành phần nào thực hiện hành động; `correlationId` giúp theo dõi một lần xử lý qua log và trace. Nếu một trường không cần cho nghiệp vụ hay quan sát, không nên thêm chỉ để giống HTTP request.

Implementation có thể điều phối nghiệp vụ và lưu dữ liệu:

```java
@Service
class ConfirmOrderService implements ConfirmOrderUseCase {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    ConfirmOrderService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Override
    @Transactional
    public ConfirmOrderResult handle(ConfirmOrderCommand command) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(() ->
                        new OrderNotFoundException(command.orderId()));

        order.confirm(command.actorId());

        orders.save(order);
        outbox.save(OrderConfirmedEvent.from(
                order, command.correlationId()));

        return new ConfirmOrderResult(order.id(), order.status());
    }
}
```

Ví dụ giả định `Order.confirm` kiểm tra các bất biến và quyền nghiệp vụ phù hợp, còn `OrderRepository` và `OutboxRepository` dùng cùng database và transaction manager. Khi đó cập nhật đơn hàng và ghi outbox record có thể commit hoặc rollback cùng nhau.

Nếu sự kiện được gửi tới broker, không nên gửi trực tiếp trước khi transaction database commit. Ghi outbox trong cùng transaction giúp lưu bền vững ý định phát sự kiện. Một dispatcher sẽ publish sau đó; phần này được trình bày ở mục về tính nhất quán.

Use case không nên phụ thuộc vào scheduler, Kafka, RabbitMQ hoặc Spring MVC. Các framework có thể xuất hiện ở adapter hoặc application orchestration theo lựa chọn của dự án, nhưng hợp đồng use case nên diễn đạt hành động nghiệp vụ.

## 4. Giữ controller và tác vụ nền là hai adapter riêng

Controller chuyển HTTP request thành command và chuyển kết quả thành response:

```java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final ConfirmOrderUseCase confirmOrder;
    private final CurrentActor currentActor;

    OrderController(
            ConfirmOrderUseCase confirmOrder,
            CurrentActor currentActor) {
        this.confirmOrder = confirmOrder;
        this.currentActor = currentActor;
    }

    @PostMapping("/{id}/confirm")
    ResponseEntity<ConfirmOrderResponse> confirm(
            @PathVariable UUID id) {
        var command = new ConfirmOrderCommand(
                new OrderId(id),
                currentActor.id(),
                UUID.randomUUID().toString());

        var result = confirmOrder.handle(command);

        return ResponseEntity.ok(
                new ConfirmOrderResponse(
                        result.orderId().value(),
                        result.status().name()));
    }
}
```

Tác vụ nền có thể tìm các đơn hàng đến hạn rồi gọi cùng use case:

```java
@Component
class OrderConfirmationJob {
    private static final int BATCH_SIZE = 100;

    private final OrderCandidateQuery candidates;
    private final ConfirmOrderUseCase confirmOrder;

    OrderConfirmationJob(
            OrderCandidateQuery candidates,
            ConfirmOrderUseCase confirmOrder) {
        this.candidates = candidates;
        this.confirmOrder = confirmOrder;
    }

    @Scheduled(fixedDelayString = "${jobs.order-confirmation.delay:30000}")
    public void runBatch() {
        List<OrderId> ids =
                candidates.findDueOrderIds(BATCH_SIZE);

        for (OrderId id : ids) {
            try {
                var command = new ConfirmOrderCommand(
                        id,
                        ActorId.system("order-confirmation-job"),
                        UUID.randomUUID().toString());

                confirmOrder.handle(command);
            } catch (OrderNotEligibleException exception) {
                // Đơn đã đổi trạng thái hoặc không còn đủ điều kiện.
                // Ghi nhận kết quả bỏ qua theo chính sách của job.
            } catch (RuntimeException exception) {
                // Ghi lỗi theo orderId; không đánh dấu thành công.
                // Việc retry được quyết định theo loại lỗi và chính sách job.
                log.error("Không thể xác nhận đơn {}", id, exception);
            }
        }
    }
}
```

Ví dụ rút gọn, cần bổ sung logger, cấu hình scheduling và cách phân loại lỗi phù hợp trong ứng dụng thực tế. `OrderCandidateQuery` chỉ tìm các ứng viên có vẻ đến hạn; nó không thay thế kiểm tra nghiệp vụ. Giữa lúc truy vấn và lúc use case chạy, đơn hàng có thể đã bị người dùng hủy hoặc một worker khác xử lý. Use case/domain phải kiểm tra lại trạng thái hiện tại.

Điểm quan trọng là job không tự sửa entity hoặc lặp lại quy tắc xác nhận. Nó chọn công việc cần thử và gọi `ConfirmOrderUseCase`. Controller và job dùng cùng use case nhưng có thể có actor, quyền, correlation ID và chính sách lỗi khác nhau.

## 5. Đặt transaction tại ranh giới của từng lần thực hiện

Một lỗi thiết kế phổ biến là mở transaction bao quanh toàn bộ batch rồi xử lý hàng nghìn đơn hàng. Nếu batch kéo dài, transaction sẽ giữ connection, lock và persistence context lâu; một lỗi ở cuối có thể làm rollback toàn bộ công việc đã xử lý, đồng thời tăng nguy cơ timeout.

Thông thường, job nên làm nhiệm vụ điều phối batch, còn use case xử lý một đơn hàng trong transaction riêng:

```text
OrderConfirmationJob (không mở transaction cho toàn batch)
       |
       +--> ConfirmOrderUseCase.handle(order-1)
       |       BEGIN -> load -> validate -> update -> COMMIT
       |
       +--> ConfirmOrderUseCase.handle(order-2)
       |       BEGIN -> load -> validate -> update -> COMMIT
       |
       +--> ConfirmOrderUseCase.handle(order-3)
               BEGIN -> load -> validate -> update -> COMMIT
```

Với Spring, `@Transactional` trên implementation use case được áp dụng khi lời gọi đi qua proxy của Spring. Job nên inject interface/bean use case và gọi từ bean khác như ví dụ. Không nên đặt `@Transactional` trên một phương thức rồi gọi nội bộ bằng `this.handle(...)` và kỳ vọng proxy mở transaction cho mỗi lần; self-invocation thường không đi qua proxy trong cấu hình proxy mặc định.

Nếu một batch nhỏ cần tất cả bản ghi cùng thành công hoặc thất bại, transaction theo chunk có thể là lựa chọn có chủ đích. Khi đó cần xác định rõ kích thước chunk, thời gian chạy, lock, rollback và khả năng chạy lại. Đừng mặc định toàn bộ job phải là một transaction duy nhất.

### 5.1. Phân biệt transaction của use case và transaction của trigger

- Scheduler không cần giữ transaction trong lúc chờ lịch hoặc duyệt danh sách.
- Truy vấn lấy ứng viên có thể dùng một transaction đọc ngắn.
- Mỗi lần gọi use case mở transaction ghi riêng nếu đó là đơn vị nghiệp vụ độc lập.
- Message consumer cần bảo đảm transaction xử lý dữ liệu hoàn tất trước khi xác nhận message theo cấu hình broker/container.
- Gọi HTTP hoặc gửi email ra ngoài không tự tham gia transaction database.

Một transaction database không thể rollback một HTTP request đã tới dịch vụ khác hoặc một email đã gửi. Nếu use case cần yêu cầu tác động ngoài, hãy ghi outbox hoặc thiết kế quy trình bù trừ/idempotency phù hợp.

### 5.2. Khi nào dùng `@Async`?

`@Async` có thể hữu ích khi cần chuyển một thao tác sang executor trong cùng ứng dụng và không cần hàng đợi bền vững. Tuy nhiên:

- Công việc thường nằm trong bộ nhớ của tiến trình; tiến trình dừng đột ngột có thể làm mất tác vụ chưa chạy.
- Không nên giả định transaction của thread gọi được truyền sang thread nền.
- Cần cấu hình executor, giới hạn queue và xử lý từ chối khi quá tải.
- Lỗi của phương thức bất đồng bộ không được trả trực tiếp như lỗi của request đã kết thúc; cần cơ chế quan sát và xử lý.
- Lời gọi qua proxy cần đúng cách; self-invocation có thể khiến `@Async` không được áp dụng.

Hãy truyền ID hoặc command bất biến, không truyền JPA entity đang được quản lý hoặc persistence context sang thread khác. Nếu công việc cần độ bền, retry sau restart, phân phối nhiều worker hoặc quản lý backlog, message broker hay bảng job thường phù hợp hơn `@Async`.

## 6. Chọn cơ chế kích hoạt: scheduler, queue hay bảng job?

Không phải mọi tác vụ nền đều cần message broker. Chọn cơ chế theo cách công việc được phát sinh và yêu cầu phục hồi.

| Cơ chế | Phù hợp khi | Đánh đổi |
|---|---|---|
| `@Scheduled` polling | Công việc định kỳ, có thể tìm ứng viên từ database | Mỗi instance có thể chạy lịch; cần phối hợp khi scale ngang |
| Message broker | Công việc phát sinh theo sự kiện, cần buffering và worker độc lập | Có delivery lặp, retry, DLQ và vận hành broker |
| Bảng job trong database | Cần lưu trạng thái, lịch chạy, lease và tiến độ | Cần thiết kế claim, polling, cleanup và khả năng mở rộng |
| `@Async`/executor | Công việc ngắn, không cần đảm bảo bền vững sau restart | Tác vụ trong bộ nhớ, giới hạn tài nguyên và xử lý lỗi do ứng dụng tự chịu |

Có thể bắt đầu bằng scheduler polling đơn giản khi lưu lượng thấp. Nếu công việc tăng, cần xử lý bất đồng bộ theo sự kiện hoặc nhiều worker, có thể chuyển sang queue hoặc bảng job. Dù thay cơ chế kích hoạt, application use case vẫn giữ hợp đồng và quy tắc.

## 7. Chạy nhiều instance và tránh xử lý trùng

Trong môi trường có nhiều replica của ứng dụng, mỗi instance có thể kích hoạt cùng một `@Scheduled` method. Ví dụ ba pod cùng chạy mỗi 30 giây có thể cùng truy vấn một danh sách đơn hàng và cùng gọi use case.

Không thể giải quyết đầy đủ vấn đề này chỉ bằng một biến `boolean` trong bộ nhớ, vì mỗi instance có trạng thái riêng và có thể khởi động lại. Cần phối hợp ở nơi dùng chung hoặc làm thao tác xử lý an toàn khi được giao nhiều lần.

### 7.1. Khóa hoặc lease cho lịch chạy

Một distributed lock hoặc scheduler lock có thể bảo đảm chỉ một instance thực hiện một lần lịch trong khoảng thời gian nhất định. Cần đặt thời hạn khóa lớn hơn thời gian dự kiến, có cơ chế gia hạn nếu cần và xử lý trường hợp tiến trình chết khi đang giữ khóa.

Khóa lịch chỉ giảm khả năng nhiều instance cùng chạy batch. Nó không thay thế idempotency của từng đơn hàng: job có thể chạy lại sau restart, lock hết hạn hoặc một lần xử lý trước đã commit nhưng worker chưa ghi nhận hoàn tất.

### 7.2. Claim từng công việc bằng database

Với nhiều worker, có thể dùng trạng thái `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED` cùng lease hoặc thời điểm hết hạn. Worker claim một nhóm bản ghi bằng thao tác nguyên tử rồi xử lý từng công việc.

```text
PENDING
   |
   | claim atomically, set owner + lease
   v
PROCESSING
   |                 |
   | success         | retryable failure
   v                 v
COMPLETED          PENDING (nextAttemptAt)
                     |
                     | permanent failure / retry limit
                     v
                   FAILED
```

Cách claim cụ thể phụ thuộc database. Một số database hỗ trợ `SELECT ... FOR UPDATE SKIP LOCKED`; đây là khả năng đặc thù cần kiểm tra theo hệ quản trị và driver. Một lựa chọn khác là câu lệnh cập nhật có điều kiện và kiểm tra số dòng bị cập nhật. Không nên đọc trạng thái rồi cập nhật riêng rẽ mà không khóa hoặc kiểm tra version, vì hai worker có thể cùng nghĩ rằng mình đã claim thành công.

Lease cần có thời hạn để công việc không bị kẹt vĩnh viễn khi worker chết. Nếu xử lý lâu hơn lease, worker có thể gia hạn hoặc hệ thống có thể cho worker khác claim lại. Khi đó, cần fencing token/version hoặc idempotency để một worker cũ không ghi đè kết quả của worker mới sau khi lease đã hết.

## 8. Idempotency và trạng thái nghiệp vụ

Một tác vụ nền có thể được chạy lại vì:

- Scheduler chạy lại sau khi ứng dụng restart.
- Message broker redeliver vì consumer chưa xác nhận.
- Worker xử lý thành công nhưng chết trước khi cập nhật trạng thái job.
- Client hoặc dispatcher gửi lại sau timeout.
- Người vận hành yêu cầu chạy lại một công việc thất bại.

Vì vậy, xử lý lặp là tình huống bình thường cần thiết kế, không phải trường hợp hiếm có thể bỏ qua.

### 8.1. Bảo vệ bằng chuyển trạng thái hợp lệ

Nếu use case chỉ cho phép xác nhận đơn nháp, gọi lại sau khi đơn đã xác nhận phải có kết quả xác định: trả kết quả đã hoàn thành, bỏ qua như một thao tác idempotent hoặc trả lỗi nghiệp vụ tùy hợp đồng. Không được tạo thêm một đơn hàng hoặc ghi nhận thanh toán lần nữa.

Có thể dùng optimistic locking:

```java
@Entity
class OrderJpaEntity {
    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Version
    private long version;
}
```

Nếu hai transaction cùng đọc một version và cùng cập nhật, một transaction có thể commit; transaction còn lại nhận lỗi optimistic locking. Application cần phân loại lỗi xung đột, đọc lại trạng thái và quyết định bỏ qua, retry toàn bộ use case trong transaction mới hoặc báo lỗi.

Với trạng thái cần loại trừ đồng thời mạnh hơn, có thể dùng pessimistic lock hoặc cập nhật có điều kiện. Lựa chọn phụ thuộc tần suất xung đột và khả năng database.

### 8.2. Idempotency key cho một công việc logic

Với công việc có ID duy nhất như `jobId`, `messageId` hoặc `paymentRequestId`, có thể lưu một processing record với unique constraint theo phạm vi phù hợp. Khi nhận lại cùng ID:

- Nếu đã hoàn thành, trả hoặc sử dụng kết quả đã lưu.
- Nếu đang xử lý, không khởi chạy song song một bản sao không được phép.
- Nếu thất bại tạm thời, lên lịch retry theo chính sách.
- Nếu payload khác nhưng dùng lại cùng ID, từ chối hoặc đưa vào xử lý lỗi vì hợp đồng đã bị vi phạm.

Không chỉ kiểm tra “đã tồn tại chưa” rồi mới insert, vì hai worker có thể cùng kiểm tra thấy chưa có. Ràng buộc unique và transaction cần bảo vệ thao tác nhận quyền xử lý.

Idempotency phải bao phủ side effect thực sự. Nếu use case cập nhật database rồi gửi thanh toán qua provider, việc chống lặp trong database không tự bảo đảm provider không thu tiền hai lần. Hãy dùng idempotency key mà provider hỗ trợ hoặc quy trình tra cứu/đối soát.

## 9. Tính nhất quán khi phát sự kiện sau use case

Một use case có thể cần vừa cập nhật đơn hàng vừa thông báo cho dịch vụ vận chuyển hoặc phát event `OrderConfirmed`. Nếu ghi database rồi publish message trực tiếp, có hai tình huống lỗi:

- Database commit thành công nhưng publish thất bại: dịch vụ khác không biết đơn đã xác nhận.
- Publish thành công nhưng database rollback: dịch vụ khác nhận event cho một thay đổi chưa tồn tại.

### 9.1. Transactional outbox

Với database hỗ trợ transaction cục bộ, có thể ghi thay đổi nghiệp vụ và outbox record trong cùng transaction:

```java
@Transactional
public ConfirmOrderResult handle(ConfirmOrderCommand command) {
    Order order = loadAndConfirm(command);

    orders.save(order);
    outbox.save(OutboxMessage.of(
            "OrderConfirmed",
            order.id().value(),
            command.correlationId()));

    return resultOf(order);
}
```

Sau commit, một dispatcher đọc các outbox record chưa publish, gửi message và cập nhật trạng thái gửi. Nếu transaction rollback, cả đơn hàng và outbox record đều không được commit. Nếu commit thành công, ý định phát event đã được lưu bền vững.

Outbox không tạo một transaction nguyên tử giữa database và broker. Có thể dispatcher publish thành công rồi chết trước khi đánh dấu record đã gửi, khiến message được publish lại. Consumer vẫn cần idempotency hoặc deduplication.

### 9.2. Consumer xử lý và xác nhận message

Một consumer có thể chuyển message thành command rồi gọi cùng use case:

```java
@Component
class PaymentCapturedConsumer {
    private final ConfirmOrderUseCase confirmOrder;

    PaymentCapturedConsumer(ConfirmOrderUseCase confirmOrder) {
        this.confirmOrder = confirmOrder;
    }

    // Chữ ký listener và acknowledgement phụ thuộc broker/framework.
    public void onMessage(PaymentCapturedMessage message) {
        var command = new ConfirmOrderCommand(
                new OrderId(message.orderId()),
                ActorId.system("payment-event-consumer"),
                message.correlationId());

        confirmOrder.handle(command);
        // Chỉ trả thành công sau khi lời gọi use case hoàn tất.
    }
}
```

Nếu transaction của use case được quản lý qua Spring proxy, transaction commit/rollback hoàn tất trước khi lời gọi proxy trả về bình thường hoặc ném lỗi. Cấu hình listener/container phải xác nhận message sau khi xử lý thành công theo semantics của broker. Chi tiết acknowledgement, transaction integration và redelivery khác nhau giữa Kafka, RabbitMQ và các nền tảng khác; không nên giả định chỉ thêm `@Transactional` vào listener là database và broker đã cùng commit nguyên tử.

Ngay cả khi xác nhận message sau commit database, vẫn có khoảng thời gian consumer commit dữ liệu rồi chết trước khi broker nhận acknowledgement. Broker có thể gửi lại message; vì vậy consumer cần idempotent. Với một số hệ thống, có thể lưu message ID đã xử lý trong cùng transaction với dữ liệu nghiệp vụ.

## 10. Retry, lỗi vĩnh viễn và dead-letter

Không phải lỗi nào cũng cần retry. Tác vụ nền cần phân biệt:

- **Lỗi tạm thời:** timeout, connection reset, database deadlock hoặc dependency tạm quá tải; có thể retry có giới hạn.
- **Lỗi nghiệp vụ:** đơn đã hủy, không đủ điều kiện, dữ liệu không hợp lệ; thường cần bỏ qua hoặc chuyển trạng thái theo quy tắc, không retry vô hạn.
- **Lỗi cấu hình/lập trình:** sai endpoint, schema không tương thích hoặc bug; cần cảnh báo và điều tra.
- **Lỗi không xác định kết quả:** timeout sau khi thao tác có thể đã commit; cần idempotency hoặc tra cứu trạng thái trước khi chạy lại.

Một chính sách retry nên có số lần tối đa, exponential backoff, jitter, deadline và phân loại exception. Với queue, message vượt quá số lần thử có thể chuyển sang dead-letter queue (DLQ) để điều tra và xử lý thủ công hoặc theo quy trình sửa dữ liệu.

Không nên bắt mọi exception rồi log và tiếp tục như thể công việc đã hoàn tất. Nếu xử lý thất bại, trạng thái job/message phải phản ánh điều đó để hệ thống có thể retry hoặc báo người vận hành. Cũng tránh retry ở nhiều tầng cùng lúc mà không tính tổng số lần thử, vì có thể khuếch đại tải.

## 11. Truyền danh tính, tenant và ngữ cảnh chạy nền

HTTP request thường có security context, tenant, locale, correlation ID và thông tin người dùng trong thread hiện tại. Tác vụ nền không có các giá trị đó một cách tự nhiên. Không nên giả định `SecurityContextHolder`, `RequestContextHolder` hoặc MDC tự động có sẵn trong thread scheduler/worker.

Hãy quyết định rõ:

- **Actor:** thao tác được thực hiện bởi người dùng, hệ thống hay một tài khoản dịch vụ? Ghi nhận actor có ý nghĩa kiểm toán.
- **Authorization:** use case có kiểm tra quyền không? Tác vụ hệ thống cần quyền riêng và phạm vi hẹp; không nên bỏ qua kiểm tra chỉ vì chạy nền.
- **Tenant:** job xử lý một tenant hay nhiều tenant? Tenant ID phải được truyền tường minh và truy vấn phải luôn giới hạn đúng phạm vi.
- **Correlation/trace:** tạo hoặc truyền correlation ID để nối log giữa scheduler, worker, use case và downstream.
- **Dữ liệu nhạy cảm:** không ghi payload, token hoặc thông tin cá nhân vào log chỉ để theo dõi job.

Nếu một use case được gọi từ HTTP và background, đừng lấy actor bằng cách đọc thread-local bên trong domain. Adapter nên xác định actor và truyền vào command hoặc một context application được thiết kế rõ. Với job hệ thống, có thể dùng service identity được phân quyền cụ thể.

## 12. Backpressure, batch và vòng đời worker

Tác vụ nền có thể tạo tải lớn hơn request đồng bộ vì nó chạy liên tục hoặc xử lý backlog. Cần giới hạn công việc để bảo vệ database và dependency.

- Lấy ứng viên theo trang hoặc batch có giới hạn, không tải toàn bộ bảng vào bộ nhớ.
- Giới hạn số worker đồng thời theo khả năng database và dịch vụ phụ thuộc.
- Dùng queue có dung lượng và chính sách backpressure; không tăng thread vô hạn.
- Đặt timeout cho lời gọi ngoài và giới hạn thời gian một job.
- Dùng transaction ngắn; tránh giữ entity manager trong lúc chờ mạng.
- Có thể tạm dừng nhận công việc khi dependency quá tải.
- Khi shutdown, ngừng claim công việc mới, cho phép công việc đang chạy hoàn tất trong thời gian giới hạn và để lease/message redelivery xử lý phần chưa hoàn tất.
- Theo dõi tuổi của công việc lâu nhất trong backlog, không chỉ tổng số message.

Với batch lớn, có thể chia thành trang hoặc chunk và lưu checkpoint. Checkpoint cần được cập nhật theo semantics rõ ràng: nếu checkpoint ghi trước khi xử lý commit, có thể bỏ sót công việc; nếu ghi sau commit nhưng trước acknowledgement, có thể xử lý lặp. Thiết kế idempotency giúp xử lý trường hợp lặp an toàn.

## 13. Quan sát và vận hành tác vụ nền

Một tác vụ nền không có người dùng đang chờ trên màn hình, nhưng vẫn cần khả năng chẩn đoán. Nên ghi nhận:

- Tên job/consumer, batch ID hoặc message ID.
- Thời điểm bắt đầu, kết thúc và thời lượng.
- Số công việc tìm thấy, claim, hoàn thành, bỏ qua và thất bại.
- Số lần retry, lỗi theo loại và số message chuyển DLQ.
- Tuổi backlog và thời điểm xử lý gần nhất.
- Tenant hoặc phạm vi dữ liệu ở dạng an toàn.
- Correlation ID để truy vết qua các thành phần.

Log cần có ngữ cảnh đủ để tìm một đơn hàng nhưng không chứa dữ liệu nhạy cảm không cần thiết. Metric nên dùng nhãn có cardinality giới hạn; không đưa order ID hoặc message ID duy nhất vào label metric. Những ID đó phù hợp hơn trong log hoặc trace.

Cần có cảnh báo khi job không chạy trong khoảng thời gian dự kiến, backlog tăng liên tục, lease hết hạn bất thường, tỷ lệ lỗi vượt ngưỡng hoặc DLQ có message mới. Một job có thể không ném exception nhưng vẫn không làm được việc nếu truy vấn ứng viên trả về rỗng do sai điều kiện; vì vậy nên theo dõi kết quả nghiệp vụ và tiến độ, không chỉ trạng thái tiến trình.

## 14. Kiểm thử khi bổ sung tác vụ nền

Không cần kiểm thử toàn bộ hệ thống qua một E2E test cho mọi trường hợp. Hãy kiểm tra từng ranh giới và các rủi ro quan trọng.

| Mức kiểm thử | Nội dung cần xác minh |
|---|---|
| Unit test use case/domain | Quy tắc xác nhận, trạng thái không hợp lệ, quyền và kết quả |
| Unit test scheduler/job | Tìm ứng viên, giới hạn batch, gọi use case và phân loại lỗi |
| Adapter test cho message | Chuyển payload thành command, xử lý schema và acknowledgement/error |
| Integration test transaction | Mỗi use case commit/rollback đúng; lỗi không để dữ liệu một phần |
| Concurrency test | Hai worker cùng claim hoặc cùng xử lý một đơn không tạo tác động trùng |
| Outbox/consumer integration test | Outbox được ghi cùng transaction; message lặp được xử lý an toàn |
| Operational test | Retry, DLQ, shutdown, lease hết hạn và backlog được quan sát |

Ví dụ unit test cho job có thể xác minh nó gọi use case với từng ID được chọn và không tự sửa trạng thái đơn hàng. Dùng fake query và mock use case là đủ cho logic điều phối.

Integration test cần kiểm tra hành vi thực tế của transaction. Ví dụ, ép lưu outbox thất bại sau khi đơn hàng đã được thay đổi trong persistence context; sau khi transaction rollback, đọc lại bằng transaction mới để xác minh trạng thái đơn vẫn như cũ và không có outbox record. Với message consumer, gửi cùng message ID hai lần và xác minh chỉ có một tác động nghiệp vụ.

Test chạy nhiều instance cần mô phỏng claim đồng thời hoặc dùng database thật phù hợp với cơ chế khóa. Mock repository không chứng minh `SKIP LOCKED`, unique constraint hoặc optimistic locking hoạt động như dự kiến.

## 15. Checklist trước khi phát hành tác vụ nền

Trước khi bật job hoặc consumer, hãy kiểm tra:

1. Tác vụ có gọi application use case hiện có thay vì sao chép quy tắc nghiệp vụ không?
2. Command có chứa actor, tenant và correlation context cần thiết không?
3. Trigger có chỉ tìm/nhận công việc và chuyển đổi payload, không tự quyết định nghiệp vụ không?
4. Transaction nằm ở đúng đơn vị xử lý: mỗi item, chunk hay toàn batch? Lý do chọn đã rõ chưa?
5. Có lời gọi mạng hoặc side effect bên ngoài nằm trong transaction không?
6. Nếu chạy nhiều instance, công việc được claim hoặc khóa như thế nào?
7. Nếu cùng một ID được gửi hai lần, kết quả có an toàn và xác định không?
8. Nếu worker chết sau commit nhưng trước acknowledgement, hệ thống xử lý redelivery ra sao?
9. Retry có giới hạn, backoff, jitter và phân loại lỗi không? Lỗi vĩnh viễn được đưa vào đâu?
10. Nếu phát event sau commit, có outbox hoặc cơ chế đảm bảo ý định phát không bị mất không?
11. Batch, concurrency, timeout và shutdown có giới hạn rõ không?
12. Có log, metric, trace, cảnh báo và hướng dẫn xử lý DLQ/backlog không?
13. Unit test, integration test và concurrency test đã bảo vệ các rủi ro quan trọng chưa?

## 16. Ghi nhớ

- Scheduler, message consumer và controller là các adapter khác nhau; chúng có thể gọi chung application use case.
- Tác vụ nền nên chuyển tín hiệu thành command rõ ràng, truyền actor/tenant/correlation context cần thiết và để use case/domain thực hiện quy tắc.
- Không gọi controller để tái sử dụng nghiệp vụ và không sao chép logic vào scheduler.
- Đặt transaction ở đơn vị xử lý phù hợp, thường là một use case cho mỗi bản ghi; tránh giữ transaction cho toàn batch dài nếu không có yêu cầu nguyên tử rõ ràng.
- `@Transactional` cần lời gọi qua Spring proxy; không dựa vào self-invocation để mở transaction mới cho từng lần xử lý.
- `@Async` phù hợp với một số công việc ngắn không cần độ bền; queue hoặc bảng job phù hợp hơn khi cần phục hồi, retry và phân phối worker.
- Nhiều instance có thể chạy cùng lịch hoặc nhận cùng message; cần claim/lease, locking, version hoặc cơ chế idempotency.
- Transaction database không tự bao phủ broker, email hoặc HTTP service; dùng outbox và consumer idempotent khi cần phát sự kiện tin cậy.
- Retry phải phân loại lỗi và có giới hạn; lỗi nghiệp vụ không nên bị retry vô hạn.
- Tác vụ nền cần backpressure, shutdown có kiểm soát, quan sát vận hành và kiểm thử transaction/concurrency thực tế.

