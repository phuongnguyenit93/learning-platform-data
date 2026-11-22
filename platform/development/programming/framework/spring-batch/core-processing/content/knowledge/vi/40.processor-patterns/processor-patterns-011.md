# Processor side effect và rollback

Trong Spring Batch, `ItemProcessor` thường được dùng để validate, enrich, transform hoặc filter từng item trước khi writer ghi kết quả. Một processor có thể gọi database, REST API, message broker, filesystem hoặc một service khác. Những lời gọi này có thể tạo side effect: cập nhật trạng thái, gửi email, phát event, ghi audit hoặc thay đổi dữ liệu ở hệ thống bên ngoài.

Vấn đề xuất hiện khi chunk bị rollback, step retry, item bị skip hoặc job restart. Transaction của chunk có thể hoàn tác các thay đổi database tham gia cùng transaction, nhưng không tự hoàn tác một HTTP request đã gửi, email đã phát, file đã ghi hoặc transaction độc lập đã commit. Khi processor được gọi lại, side effect có thể lặp; khi processor đã tạo side effect nhưng chunk không commit, hệ thống có thể giữ lại một phần kết quả không nhất quán.

Vì vậy, processor nên ưu tiên thực hiện công việc tính toán và chuyển đổi có thể lặp lại an toàn. Nếu nghiệp vụ cần ghi dữ liệu, hãy đặt thao tác ở writer hoặc service tham gia transaction chunk. Nếu cần side effect ngoài transaction, dùng outbox, idempotency key, staging hoặc một bước publish riêng để kiểm soát retry và restart.

## 1. Processor nên làm gì?

`ItemProcessor<I, O>` nhận một item đầu vào và trả về item đầu ra. Processor có thể:

- Kiểm tra dữ liệu và ném exception nếu item không hợp lệ.
- Tính toán hoặc chuẩn hóa dữ liệu.
- Enrich item bằng dữ liệu đã có sẵn hoặc tra cứu phù hợp.
- Chuyển DTO đầu vào thành DTO đầu ra.
- Trả `null` để filter một item theo business rule.

Ví dụ processor thuần:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    @Override
    public OrderOutput process(OrderInput input) {
        if (input.getAmount() == null || input.getAmount().signum() < 0) {
            throw new InvalidOrderException("amount must be non-negative");
        }

        BigDecimal tax = input.getAmount()
                .multiply(new BigDecimal("0.10"));
        BigDecimal total = input.getAmount().add(tax);

        return new OrderOutput(
                input.getOrderId(),
                input.getCustomerId(),
                total);
    }
}
~~~

Processor này tính toán từ input và tạo output. Nếu Spring Batch gọi lại cùng item sau rollback, kết quả vẫn giống nhau và không tạo thêm side effect.

## 2. Side effect là gì?

Side effect là thay đổi quan sát được bên ngoài giá trị mà method trả về. Trong processor, side effect có thể là:

| Hành động | Side effect |
|---|---|
| `jdbcTemplate.update(...)` | Ghi hoặc cập nhật database |
| Gọi REST API | Tạo/cập nhật dữ liệu ở service khác |
| Gửi message | Phát event hoặc command đến broker |
| Gửi email/SMS | Tạo thông báo không thể thu hồi |
| Ghi file | Thay đổi artifact trên filesystem/object storage |
| Gọi payment service | Tạo giao dịch tài chính |
| Ghi audit bên ngoài transaction | Tạo record audit độc lập |
| Tăng counter từ xa | Thay đổi metric hoặc trạng thái hệ thống khác |

Không phải mọi side effect đều sai. Một số nghiệp vụ cần chúng. Vấn đề là phải biết side effect thuộc transaction nào, có thể rollback hay không, và điều gì xảy ra khi cùng một item được xử lý lại.

## 3. Chunk transaction bao quanh processor như thế nào?

Trong chunk-oriented step, Spring Batch quản lý một transaction cho một chunk. Về khái niệm, transaction bao trùm việc đọc, xử lý và ghi các item trong chunk, sau đó commit khi chunk hoàn tất.

~~~mermaid
flowchart TD
    A[Begin chunk transaction] --> B[Read items]
    B --> C[Process each item]
    C --> D[Write chunk]
    D --> E[Update stream and checkpoint state]
    E --> F{Commit succeeds?}
    F -->|Yes| G[Chunk committed]
    F -->|No| H[Rollback chunk]
    H --> I[Retry, skip or fail according to policy]
~~~

Nếu processor dùng cùng transaction-managed database resource với step, lệnh SQL của processor có thể tham gia transaction chunk. Khi writer hoặc một bước sau đó ném exception trước commit, thay đổi database đó có thể rollback cùng chunk.

Transaction không tự bao trùm mọi hệ thống mà processor gọi. HTTP service, email server, filesystem và một broker được cấu hình độc lập thường nằm ngoài transaction database. Cần xác định rõ ranh giới cho từng side effect.

## 4. Database side effect trong cùng transaction

Một processor có thể gọi `JdbcTemplate` để cập nhật database. Nếu `JdbcTemplate` dùng cùng `DataSource` được quản lý bởi transaction manager của step, connection thường được lấy từ transaction hiện tại và thay đổi sẽ commit/rollback cùng chunk.

Ví dụ:

~~~java
public class OrderEnrichmentProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    private final JdbcTemplate jdbcTemplate;

    public OrderEnrichmentProcessor(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public OrderOutput process(OrderInput input) {
        jdbcTemplate.update("""
                update source_order
                   set validation_status = ?
                 where order_id = ?
                """,
                "VALIDATED",
                input.getOrderId());

        return new OrderOutput(input.getOrderId(), input.getAmount());
    }
}
~~~

Nếu lệnh update tham gia cùng transaction chunk, một exception trong chunk trước commit sẽ rollback update đó. Tuy nhiên, việc ghi trạng thái trong processor có thể làm code khó hiểu: processor vừa transform item vừa thay đổi persistence state. Nếu mục tiêu là ghi kết quả nghiệp vụ, thường nên chuyển thao tác sang writer.

## 5. Cùng database server chưa chắc cùng transaction

Hai thao tác cùng ghi một database vẫn có thể nằm trong transaction khác nhau nếu:

- Dùng DataSource hoặc connection độc lập không được transaction manager quản lý.
- Dùng transaction manager khác.
- Tự mở connection rồi bật `autoCommit`.
- Gọi service với propagation `REQUIRES_NEW`.
- Stored procedure hoặc trigger thực hiện autonomous commit.
- Gọi một service khác có transaction boundary riêng.

Nếu processor commit side effect trong transaction riêng rồi chunk rollback, dữ liệu đã commit vẫn tồn tại. Khi retry hoặc restart, processor có thể thực hiện lại thao tác và tạo duplicate.

Kiểm tra DataSource, transaction manager và transaction propagation thực tế. Không kết luận rằng hai thao tác atomic chỉ vì chúng cùng trỏ đến một hostname/database.

## 6. Transaction propagation và REQUIRES_NEW

Spring transaction propagation ảnh hưởng việc side effect có tham gia chunk transaction hay không:

| Propagation | Hành vi tổng quát khi đã có chunk transaction |
|---|---|
| `REQUIRED` | Tham gia transaction hiện tại |
| `REQUIRES_NEW` | Tạm dừng transaction hiện tại và tạo transaction độc lập |
| `SUPPORTS` | Tham gia nếu có transaction; nếu không thì chạy không transaction |
| `NOT_SUPPORTED` | Tạm dừng transaction hiện tại và chạy ngoài transaction |
| `MANDATORY` | Yêu cầu phải có transaction hiện tại |

Ví dụ service dùng `REQUIRES_NEW`:

~~~java
@Service
public class AuditService {

    private final AuditRepository repository;

    public AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(Long orderId) {
        repository.save(new AuditRecord(orderId, "PROCESSING"));
    }
}
~~~

Nếu processor gọi service này, audit record có thể commit ngay cả khi chunk transaction bên ngoài rollback. Khi processor được gọi lại, audit record thứ hai có thể được tạo.

`REQUIRES_NEW` có thể phù hợp cho audit độc lập nếu đó là yêu cầu được chủ đích thiết kế. Nhưng cần idempotency hoặc một event key để phân biệt attempt với kết quả nghiệp vụ cuối. Không dùng nó chỉ để “đảm bảo ghi được” mà không xem xét rollback/retry.

Lưu ý rằng `@Transactional` hoạt động qua proxy trong các cấu hình Spring thông dụng. Self-invocation trong cùng object có thể không đi qua proxy, vì vậy propagation thực tế có thể khác kỳ vọng nếu method gọi trực tiếp method khác trên `this`.

## 7. Side effect ngoài database transaction

Ví dụ processor gọi REST API:

~~~java
public OrderOutput process(OrderInput input) {
    partnerClient.reserveInventory(input.getOrderId());
    return map(input);
}
~~~

Nếu API reserve thành công nhưng writer thất bại, transaction database rollback không thể tự hủy reservation. Khi chunk được retry, API có thể được gọi lần nữa.

Các side effect ngoài transaction thường gặp:

- HTTP request đã được service khác xử lý.
- Message đã được broker nhận.
- Email/SMS đã được gửi.
- File đã được upload.
- Payment hoặc reservation đã được tạo.

Ngay cả khi transport hỗ trợ transaction riêng, transaction đó không tự động atomic với transaction JDBC của chunk. Cần cơ chế phối hợp rõ ràng nếu cả hai phải thành công hoặc thất bại cùng nhau.

## 8. Processor được gọi lại sau rollback

Fault-tolerant step có thể retry một thao tác hoặc rollback rồi xử lý lại chunk. Khi processor có side effect, việc được gọi lại là một rủi ro thực tế.

Ví dụ:

1. Processor gọi API tạo reservation cho order 1001.
2. Processor trả về OrderOutput.
3. Writer ghi database nhưng một item khác trong chunk gây lỗi.
4. Chunk rollback.
5. Spring Batch retry theo policy.
6. Processor có thể được gọi lại cho order 1001.
7. API tạo reservation lần nữa nếu request không idempotent.

Không giả định mỗi item chỉ đi qua processor đúng một lần. Với retry/rollback, số lần gọi thực tế phụ thuộc fault-tolerant configuration, vị trí lỗi và version. Thiết kế processor nên an toàn khi gọi lặp.

## 9. processorNonTransactional và processor caching

Trong fault-tolerant step, Spring Batch có tùy chọn `processorNonTransactional()` để khai báo processor không cần được gọi lại khi chunk rollback. Framework có thể cache output của processor trong bộ nhớ để tái sử dụng khi xử lý lại chunk.

Ví dụ cấu hình:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .processorNonTransactional()
        .build();
~~~

Tùy chọn này có thể giảm việc gọi lại processor khi retry trong cùng execution, nhưng không phải cơ chế rollback side effect:

- Side effect đã phát ra vẫn không tự biến mất.
- Cache không phải durable checkpoint và không thay thế restart state.
- Process crash có thể làm mất cache trong memory.
- Restart JobInstance có thể phải thực hiện lại processor cho item chưa commit.
- Cấu hình này không làm một HTTP request trở thành transactional.

Chỉ dùng khi semantics của processor thực sự phù hợp với việc tái sử dụng kết quả đã tính. Không dựa vào tùy chọn này để bảo vệ payment, message publish hoặc side effect không idempotent.

## 10. Processor trả null và side effect

`ItemProcessor` có thể trả `null` để filter item. Item bị filter sẽ không được chuyển tới writer. Nhưng nếu processor thực hiện side effect trước khi trả null, side effect vẫn có thể xảy ra.

Ví dụ nguy hiểm:

~~~java
public OrderOutput process(OrderInput input) {
    notificationClient.send(input.getCustomerId(), "Order received");

    if (input.getAmount().signum() == 0) {
        return null;
    }

    return map(input);
}
~~~

Order amount bằng zero bị filter nhưng notification đã được gửi. Nếu business rule yêu cầu item bị filter không tạo thông báo, thứ tự logic này sai.

Nên quyết định filter trước, sau đó mới thực hiện công việc phù hợp. Tốt hơn nữa, processor chỉ trả kết quả hoặc null; writer/publisher thực hiện side effect cho những item thực sự được chấp nhận.

## 11. Không dùng processor để gửi email hoặc SMS

Gửi email/SMS thường không thể rollback. Nếu processor gửi thông báo rồi chunk rollback, người nhận vẫn nhận được thông báo dù dữ liệu nghiệp vụ chưa commit.

Một quy trình an toàn hơn:

1. Processor xác định nội dung thông báo cần gửi và tạo notification intent.
2. Writer lưu kết quả nghiệp vụ và notification intent vào database trong cùng chunk transaction.
3. Sau commit, publisher riêng đọc notification intent chưa gửi.
4. Publisher gửi qua provider bằng idempotency key nếu provider hỗ trợ.
5. Publisher đánh dấu đã gửi hoặc ghi trạng thái delivery.

Nếu gửi thất bại, notification intent vẫn còn để retry. Nếu publisher chết sau khi provider đã gửi nhưng trước khi đánh dấu, provider idempotency key hoặc reconciliation giúp tránh gửi trùng.

## 12. Không publish message trực tiếp từ processor

Gọi `KafkaTemplate.send(...)`, `JmsTemplate.convertAndSend(...)` hoặc `RabbitTemplate.convertAndSend(...)` trong processor tạo side effect ngoài transaction chunk trừ khi có cấu hình phối hợp transaction cụ thể.

Ví dụ:

~~~java
public OrderOutput process(OrderInput input) {
    kafkaTemplate.send("order-events", toEvent(input));
    return map(input);
}
~~~

Nếu writer hoặc một item sau đó làm chunk rollback, Kafka record đã được gửi có thể vẫn tồn tại. Khi retry, processor có thể publish record lần nữa.

Nếu cần event tương ứng với business update, dùng transactional outbox. Ghi event vào bảng outbox trong cùng database transaction với business data; publisher riêng gửi event sau commit. Điều này tách transaction của batch với transaction của broker nhưng vẫn giữ được khả năng phát lại.

## 13. Transactional outbox pattern

Outbox giải quyết crash window giữa database commit và publish message:

~~~mermaid
flowchart TD
    A[ItemProcessor creates result and event intent] --> B[Chunk writer]
    B --> C[Business table]
    B --> D[Outbox table]
    C --> E[Same database transaction]
    D --> E
    E --> F[Commit]
    F --> G[Outbox publisher]
    G --> H[Message broker]
    H --> I[Consumer with deduplication]
~~~

Trong chunk writer, ghi business data và outbox row bằng cùng transaction:

~~~java
public class OrderAndOutboxWriter
        implements ItemWriter<ProcessedOrder> {

    private final JdbcTemplate jdbcTemplate;

    @Override
    public void write(Chunk<? extends ProcessedOrder> chunk) {
        for (ProcessedOrder order : chunk) {
            jdbcTemplate.update("""
                    insert into processed_order(order_id, amount)
                    values (?, ?)
                    """,
                    order.orderId(),
                    order.amount());

            jdbcTemplate.update("""
                    insert into outbox_event(event_id, event_type, payload, status)
                    values (?, ?, ?, ?)
                    """,
                    order.eventId(),
                    "OrderProcessed",
                    order.eventPayload(),
                    "NEW");
        }
    }
}
~~~

Nếu chunk rollback, cả business row và outbox row đều rollback. Sau commit, publisher có thể gửi event độc lập. Publisher cần xử lý redelivery và trạng thái gửi; consumer nên deduplicate theo eventId.

Outbox không tự cung cấp exactly-once delivery. Nó bảo đảm event intent được lưu cùng business update; publish có thể at-least-once và cần idempotency ở consumer.

## 14. Processor tạo intent, writer thực hiện persistence

Một cách phân chia rõ trách nhiệm là để processor tạo output DTO chứa dữ liệu cần ghi, thay vì tự ghi database:

~~~java
public record ProcessedOrder(
        Long orderId,
        BigDecimal amount,
        String eventId,
        String eventPayload) {
}

public class OrderProcessor
        implements ItemProcessor<OrderInput, ProcessedOrder> {

    @Override
    public ProcessedOrder process(OrderInput input) {
        OrderValidated validated = validateAndNormalize(input);
        OrderEvent event = createEvent(validated);

        return new ProcessedOrder(
                validated.orderId(),
                validated.amount(),
                event.eventId(),
                serialize(event));
    }
}
~~~

Writer ghi `ProcessedOrder` và outbox row trong transaction. Cách này giúp processor dễ unit test, còn transaction boundary tập trung ở nơi ghi dữ liệu.

Event ID nên ổn định theo business operation. Nếu processor tạo UUID ngẫu nhiên mỗi lần gọi, rollback/retry có thể tạo event ID mới cho cùng một item. Có thể derive ID từ source ID + business key + event type/version, hoặc tạo ID một lần ở nguồn và truyền qua pipeline.

## 15. Idempotency key cho side effect

Nếu bắt buộc gọi API từ processor hoặc một service được gọi trong pipeline, request cần một idempotency key ổn định. API nhận cùng key nhiều lần phải trả cùng kết quả hoặc coi các request sau là replay.

Ví dụ:

~~~java
String idempotencyKey =
        "reserve-order-" + input.getOrderId();

partnerClient.reserveInventory(
        input.getOrderId(),
        idempotencyKey);
~~~

Key nên đại diện một business operation cụ thể. Nếu cùng order có thể reserve lại theo version hoặc attempt nghiệp vụ mới, cần đưa operation/version vào key để không vô tình gộp hai yêu cầu khác nhau.

Không dùng random UUID được tạo lại trong mỗi lần process. Khi processor chạy lại, key mới sẽ khiến service coi đó là thao tác mới và tạo side effect trùng.

## 16. Idempotency ở database

Database có thể bảo vệ side effect bằng unique constraint hoặc một bảng ledger:

~~~sql
create table processed_operation (
    operation_key varchar(200) primary key,
    business_key varchar(100) not null,
    payload_hash varchar(64) not null,
    processed_at timestamp not null
);
~~~

Trước khi thực hiện operation, kiểm tra/insert `operation_key` trong cùng transaction với thay đổi nghiệp vụ. Nếu key đã tồn tại:

- Cùng payload hash: có thể là replay hợp lệ.
- Payload hash khác: có thể là conflict cần xử lý.
- Trạng thái chưa hoàn tất: cần quy trình recovery theo state machine.

Không chỉ kiểm tra bằng SELECT rồi INSERT nếu có nhiều worker đồng thời; race condition có thể cho phép cả hai cùng thấy key chưa tồn tại. Unique constraint là lớp bảo vệ cuối cùng.

## 17. Processor gọi service có transaction REQUIRED

Một service được gọi từ processor có thể dùng `@Transactional` với propagation mặc định `REQUIRED`. Khi method được gọi qua Spring proxy và dùng cùng transaction manager, nó thường tham gia transaction chunk hiện tại.

~~~java
@Service
public class OrderValidationService {

    private final OrderRepository repository;

    @Transactional
    public void markValidated(Long orderId) {
        repository.updateValidationStatus(orderId, "VALIDATED");
    }
}
~~~

Nếu service và step dùng cùng transaction manager, thay đổi có thể rollback khi chunk rollback. Tuy vậy, hãy xem xét lại trách nhiệm: cập nhật trạng thái trong processor có thể gây khó hiểu khi filter, retry hoặc skip.

Nếu status là kết quả nghiệp vụ cuối cùng, writer thường là nơi phù hợp hơn để persist cùng output. Service có thể được gọi từ writer và tham gia transaction hiện tại.

## 18. Side effect trước khi processor ném exception

Một processor có thể thực hiện side effect rồi phát hiện dữ liệu lỗi:

~~~java
public OrderOutput process(OrderInput input) {
    auditService.recordAttempt(input.getOrderId());

    if (input.getAmount().signum() < 0) {
        throw new InvalidOrderException("Negative amount");
    }

    return map(input);
}
~~~

Nếu `recordAttempt` dùng transaction độc lập, audit row có thể tồn tại dù item bị skip hoặc chunk rollback. Nếu audit row nằm trong chunk transaction, nó có thể rollback theo chunk.

Hãy xác định audit cần ghi nhận điều gì:

- Attempt đã bắt đầu: có thể tồn tại ngay cả khi xử lý thất bại.
- Validation result: nên ghi sau khi validation xác định kết quả.
- Business operation completed: chỉ ghi sau khi kết quả được commit.

Ba khái niệm này không giống nhau. Dùng tên event/status riêng để operator không hiểu nhầm một attempt thành một kết quả đã hoàn tất.

## 19. Retry exception trong processor

Nếu processor ném exception tạm thời, step có thể được cấu hình retry:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TemporaryLookupException.class)
        .retryLimit(3)
        .build();
~~~

Retry chỉ hợp lý nếu thao tác có khả năng thành công ở lần thử sau. Ví dụ lookup service bị timeout có thể retry; validation error cố định thường không nên retry.

Nếu processor gọi API có side effect rồi timeout, không biết server đã thực hiện operation hay chưa. Đây là trường hợp cần idempotency key hoặc API truy vấn trạng thái. Retry mù có thể tạo duplicate.

## 20. Skip exception trong processor

Một lỗi dữ liệu có thể được cấu hình skip nếu record độc lập và nghiệp vụ cho phép bỏ qua:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .listener(orderSkipListener)
        .build();
~~~

Nếu processor đã gọi side effect rồi mới ném `InvalidOrderException`, skip item không tự hoàn tác side effect ngoài transaction. Vì vậy, validate trước side effect và để writer/publisher thực hiện công việc sau khi item đã hợp lệ.

Skip limit giúp giới hạn số item lỗi. Khi vượt limit, step thất bại. Hãy ghi nhận business key và nguyên nhân skip, tránh lưu toàn bộ payload nhạy cảm vào log.

## 21. Retry và skip không giống rollback

Ba khái niệm cần phân biệt:

- **Rollback:** hoàn tác các thay đổi tham gia transaction hiện tại.
- **Retry:** thử lại thao tác/chunk theo policy.
- **Skip:** loại item lỗi khỏi quá trình xử lý sau khi policy cho phép.

Rollback không tự động gọi lại API để đảo ngược side effect. Retry không bảo đảm side effect cũ đã được xóa. Skip không tự undo những thay đổi processor đã thực hiện trước khi ném exception.

Nếu cần bù trừ side effect, đó là một business operation riêng, ví dụ release reservation hoặc cancel request. Compensation cũng có thể thất bại và cần retry/idempotency riêng; không nên coi nó như database rollback.

## 22. Compensation và saga

Với quy trình nhiều service, một thao tác có thể cần hành động bù trừ:

~~~text
Reserve inventory
       |
       v
Persist order
       |
       +---- success -> continue
       |
       +---- failure -> release inventory
~~~

Đây là dạng saga/compensation. Hành động bù trừ không làm cho side effect ban đầu chưa từng xảy ra; nó tạo một business event mới để đưa hệ thống về trạng thái chấp nhận được.

Nếu dùng compensation:

- Lưu operation ID của hành động ban đầu.
- Đảm bảo compensation idempotent.
- Theo dõi trạng thái PENDING/COMPLETED/FAILED.
- Retry compensation có giới hạn và cảnh báo khi cần can thiệp.
- Không xóa audit trail của thao tác ban đầu.

Không nên đặt một saga dài bên trong `ItemProcessor` mà không có state machine bền vững. Tách orchestration ra service/workflow hoặc các step riêng nếu quy trình có nhiều trạng thái.

## 23. Side effect trong ItemProcessListener

Listener như `beforeProcess`, `afterProcess` và `onProcessError` hữu ích để quan sát processor. Tuy nhiên, listener cũng chạy trong lifecycle processing và có thể bị gọi trong các tình huống retry/error tùy execution path.

Không nên dùng `afterProcess` để gửi email hoặc publish event rồi giả định nó chỉ chạy sau commit. Callback này không phải commit hook của database transaction.

Nếu listener ghi audit vào cùng transaction, xác định rõ nó có tham gia transaction hiện tại không. Nếu listener ghi sang hệ thống ngoài, áp dụng cùng nguyên tắc idempotency/outbox như processor.

Listener phù hợp cho metric, trace, log và ghi nhận trạng thái có transaction semantics rõ ràng. Nó không thay thế writer hoặc after-commit publisher.

## 24. Không dùng afterWrite như afterCommit

`ItemWriteListener.afterWrite` được gọi sau khi writer method hoàn tất, nhưng điều đó không có nghĩa chunk transaction đã commit. Sau callback vẫn có thể xảy ra lỗi ở phần còn lại của chunk lifecycle hoặc transaction commit.

Không gửi thông báo “đã hoàn tất” từ `afterWrite` nếu consumer hiểu đó là dữ liệu đã commit. Nếu cần phản ứng sau commit, dùng transaction synchronization hoặc outbox.

Transaction synchronization `afterCommit` có thể hữu ích cho một số tác vụ nhẹ:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                metricsPublisher.recordCommittedChunk();
            }
        });
~~~

Callback sau commit tránh chạy khi transaction rollback, nhưng process có thể chết sau commit trước khi callback hoàn tất. Với side effect cần bảo đảm bền vững như publish business event, outbox đáng tin cậy hơn callback trong memory.

## 25. File side effect từ processor

Nếu processor trực tiếp ghi file:

~~~java
public OrderOutput process(OrderInput input) throws IOException {
    Files.writeString(
            auditPath,
            input.getOrderId() + System.lineSeparator(),
            StandardOpenOption.CREATE,
            StandardOpenOption.APPEND);
    return map(input);
}
~~~

File write thông thường không tham gia JDBC transaction. Khi chunk rollback, dòng đã append vẫn còn. Khi processor chạy lại, dòng có thể bị ghi thêm.

Một số writer chuẩn của Spring Batch có cơ chế buffering/transaction-aware behavior riêng. Không suy rộng behavior đó sang `Files.write`, custom file writer hoặc mọi filesystem. Nếu output file cần rollback/restart, dùng writer phù hợp, staging file, record key hoặc bước tạo artifact riêng có thể chạy lại.

## 26. Cập nhật cache hoặc trạng thái in-memory

Processor có thể cập nhật cache, counter hoặc mutable singleton:

~~~java
cache.put(input.getOrderId(), "PROCESSED");
~~~

Rollback database không khôi phục cache. Nếu chunk thất bại, cache có thể nói item đã processed dù business transaction đã rollback. Retry có thể đọc trạng thái cũ và bỏ qua item.

Nếu cache chỉ là optimization, phải có cách invalidate/rebuild từ source of truth và không để cache quyết định correctness. Không dùng in-memory flag làm checkpoint bền vững. Với step chạy song song, cache còn cần thread safety và isolation giữa JobInstance.

## 27. Processor gọi hệ thống ngoài để enrich dữ liệu

Không phải mọi HTTP call từ processor đều tạo side effect. Một GET lookup thuần có thể chỉ đọc dữ liệu. Tuy nhiên, nó vẫn có thể:

- Trả kết quả khác ở lần retry.
- Tốn quota hoặc tạo audit/access log ở service ngoài.
- Timeout sau khi server đã trả response nhưng client không nhận.
- Làm processor không deterministic nếu dữ liệu thay đổi giữa hai lần gọi.

Nếu enrichment phải nhất quán qua restart, cân nhắc:

- Lưu snapshot/version dữ liệu lookup.
- Cache kết quả theo key và version.
- Ghi kết quả enrich vào staging table.
- Dùng immutable reference data.
- Xác định rõ lookup có thể được gọi nhiều lần.

GET thường không tạo business mutation, nhưng vẫn có chi phí và semantics cần được kiểm soát. Nếu gọi POST để “lookup” nhưng service tạo record hoặc reservation, đó là side effect.

## 28. Processor và tính deterministic

Processor deterministic khi cùng input và cùng reference context tạo cùng output. Tính chất này hữu ích cho retry, restart, test và đối soát.

Những nguồn làm processor không deterministic:

- Dùng `Instant.now()` hoặc `LocalDate.now()` trực tiếp.
- Dùng random UUID mới mỗi lần process.
- Gọi service trả dữ liệu mutable.
- Dựa vào trạng thái singleton thay đổi theo thứ tự item.
- Đọc dữ liệu không có snapshot/version.
- Dựa vào timezone hoặc locale mặc định của JVM.

Nếu cần thời gian nghiệp vụ, truyền business timestamp qua job parameters hoặc input event. Nếu cần ID ổn định, dùng source event ID/business key hoặc một quy tắc deterministic. Nếu cần random value, tạo một lần và lưu bền vững trước khi retry.

## 29. Processor có nên gọi repository không?

Không có quy tắc cứng rằng processor tuyệt đối không được gọi repository. Một lookup read-only để enrich có thể hợp lý. Nhưng việc ghi persistence state từ processor cần được cân nhắc:

- Ghi kết quả chính thường thuộc writer.
- Ghi outbox thường thuộc cùng writer transaction với business data.
- Audit attempt có thể cần service riêng với semantics rõ.
- Lookup reference data có thể thuộc processor nếu không tạo side effect.
- Cập nhật trạng thái nguồn có thể cần writer hoặc claim step riêng.

Nếu processor gọi repository để ghi, test phải chứng minh transaction participation và hành vi khi rollback/retry. Đừng dựa vào tên method `save()` hoặc annotation `@Transactional` để kết luận thay đổi chắc chắn rollback cùng chunk.

## 30. Processor gọi service có thể retry độc lập

Một service có thể có retry riêng, ví dụ retry HTTP timeout bên trong method. Khi kết hợp với retry của step, số lần gọi thực tế có thể nhân lên:

- Step retry tối đa 3 lần.
- Service retry tối đa 4 lần mỗi lần gọi.
- Một item có thể dẫn tới tối đa nhiều request hơn dự kiến.

Hãy tính tổng retry budget, timeout và backoff ở các tầng. Tránh retry lồng nhau không giới hạn. Một retry ở service có thể xử lý lỗi transport; retry ở step có thể xử lý lỗi transaction/chunk. Cần xác định tầng nào sở hữu từng nhóm exception.

## 31. Batch writer là nơi thích hợp cho persistence

Một processor thuần trả về kết quả:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, ProcessedOrder> {

    @Override
    public ProcessedOrder process(OrderInput input) {
        return validateAndBuild(input);
    }
}
~~~

Writer ghi output:

~~~java
@Bean
public JdbcBatchItemWriter<ProcessedOrder> processedOrderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                    insert into processed_order(order_id, amount)
                    values (:orderId, :amount)
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

Writer được gọi trong chunk transaction. Nếu insert thất bại, transaction có thể rollback toàn bộ chunk cùng checkpoint. Tập trung persistence ở writer giúp transaction boundary dễ hiểu và integration test rõ hơn.

## 32. Khi side effect phải xảy ra trước khi writer

Một số nghiệp vụ thực sự yêu cầu reserve resource trước khi ghi database. Trong trường hợp đó, hãy mô hình hóa reservation như một operation có trạng thái:

1. Tạo operation key ổn định.
2. Gọi reserve API với idempotency key.
3. Lưu reservation ID và trạng thái vào output/staging.
4. Ghi business result cùng operation reference.
5. Nếu chunk không commit, lần retry truy vấn hoặc tái sử dụng reservation hiện có.
6. Nếu nghiệp vụ thất bại vĩnh viễn, phát compensation để release reservation.

Không gọi API rồi bỏ response. Nếu không lưu reservation ID, lần retry khó biết operation cũ đã thành công hay chưa.

## 33. Side effect trong processor khi item bị skip

Giả sử processor:

1. Gọi API tạo shipment.
2. Validate địa chỉ.
3. Ném InvalidAddressException.

Nếu exception được cấu hình skip, item bị bỏ qua nhưng shipment có thể vẫn tồn tại. Đây là trạng thái nghiệp vụ nguy hiểm.

Thứ tự tốt hơn:

1. Validate tất cả dữ liệu nội bộ trước.
2. Tạo output/command hợp lệ.
3. Ghi intent hoặc reservation theo idempotency key.
4. Chỉ thực hiện external side effect ở bước được kiểm soát.
5. Nếu lỗi sau side effect, lưu state để retry/compensate.

Một lỗi dữ liệu có thể dự đoán nên được phát hiện trước khi tạo side effect không thể đảo ngược.

## 34. Chunk rollback không phải rollback toàn job

Chunk transaction chỉ bao phủ một chunk. Các chunk trước đã commit vẫn tồn tại nếu chunk sau thất bại:

~~~text
Chunk 1 -> COMMIT
Chunk 2 -> COMMIT
Chunk 3 -> PROCESSOR ERROR -> ROLLBACK
Job -> FAILED
~~~

Restart cùng JobInstance tiếp tục từ checkpoint của chunk commit cuối cùng. Nếu processor đã tạo side effect ngoài transaction ở chunk 3, side effect đó có thể còn lại dù chunk 3 rollback.

Nếu yêu cầu nghiệp vụ là toàn bộ job phải all-or-nothing, không thể dựa vào rollback của từng chunk. Hãy ghi vào staging/version riêng rồi publish khi toàn job hoàn tất; hoặc dùng workflow compensation nếu side effect không thể staging.

## 35. Side effect và remote chunking

Trong remote chunking, manager gửi chunk qua broker để worker xử lý. Worker có thể nhận lại cùng chunk khi message redelivery hoặc manager retry.

Nếu processor chạy ở worker và tạo side effect:

- Worker có thể xử lý cùng chunk nhiều lần.
- Message ack và database commit có thể không atomic.
- Worker chết sau side effect nhưng trước ack có thể được giao lại.
- Manager có thể không nhận response dù worker đã commit.

Dùng chunk ID/event ID ổn định, worker idempotency ledger và transaction phù hợp. Đừng coi việc broker có acknowledgement là bảo đảm worker side effect chỉ xảy ra một lần.

## 36. Side effect và remote partitioning

Trong remote partitioning, mỗi worker xử lý một partition. Side effect có thể xảy ra song song:

- Hai partition không được xử lý cùng business key nếu partitioning có overlap.
- Writer/processor dùng idempotency key theo business operation.
- External service phải chịu được concurrency và retry.
- Partition restart phải nhận cùng input range/configuration.
- Audit phải có partition/job correlation để truy vết.

Nếu processor cập nhật một shared counter hoặc trạng thái global, nhiều worker có thể race. Dùng atomic database operation hoặc thiết kế aggregation step sau khi các partition hoàn tất.

## 37. Side effect trong asynchronous processor

Một số cấu hình Spring Batch có thể xử lý processor bất đồng bộ. Khi đó, side effect có thể diễn ra trên thread khác hoặc transaction context khác. Không giả định transaction của chunk tự truyền sang thread worker.

Các điểm cần kiểm tra:

- Transaction context có được truyền qua hay không.
- Service gọi từ async thread có mở transaction riêng không.
- Kết quả processor được chờ hoàn tất trước commit như thế nào.
- Exception từ future được truyền về step ra sao.
- Side effect có thể hoàn tất sau khi chunk đã rollback hay không.
- Delegate có thread-safe không.

Không dùng async processing cho side effect quan trọng nếu chưa xác định transaction và cancellation semantics. Nếu async task đã gọi external API, cancel future không có nghĩa request đã bị hủy ở server.

## 38. Không dùng listener để bù rollback một cách tùy tiện

Có thể nghĩ rằng khi chunk rollback thì gọi API undo trong `afterChunkError`. Cách này có thể hữu ích như compensation nhưng không phải database rollback:

- Callback compensation có thể thất bại.
- Callback có thể chạy lại trong recovery.
- Process có thể chết trước khi callback được thực hiện.
- Không phải side effect nào cũng có thao tác undo.
- Compensation có thể cần business authorization hoặc trạng thái riêng.

Nếu cần compensation, lưu một operation record bền vững và chạy bằng step/worker có retry, thay vì chỉ dựa vào callback trong memory.

## 39. Logging và audit side effect

Khi processor gọi hệ thống ngoài, log nên giúp điều tra:

- Job/Step execution reference.
- Business key.
- Operation/idempotency key.
- Correlation ID.
- External request ID nếu có.
- Loại side effect.
- Trạng thái request/response.
- Số lần thử.

Không log access token, credential, full payment data hoặc toàn bộ payload nhạy cảm. Log “request sent” không có nghĩa external operation đã thành công; cần phân biệt SENT, ACKNOWLEDGED, COMMITTED và CONFIRMED theo semantics.

## 40. Kiểm thử processor thuần

Unit test processor nên xác nhận transformation và validation mà không phụ thuộc database/broker:

~~~java
class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void calculatesTotalWithoutExternalSideEffect() throws Exception {
        OrderInput input = new OrderInput(
                1001L,
                "C001",
                new BigDecimal("100.00"));

        OrderOutput output = processor.process(input);

        assertEquals(1001L, output.getOrderId());
        assertEquals(new BigDecimal("110.00"), output.getTotal());
    }

    @Test
    void rejectsNegativeAmount() {
        OrderInput input = new OrderInput(
                1002L,
                "C002",
                new BigDecimal("-1.00"));

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
~~~

Với processor có dependency read-only, mock dependency và xác nhận lookup được gọi theo contract. Nếu mục tiêu là pure transformation, không cần mock persistence hay external client.

## 41. Kiểm thử database side effect rollback

Integration test cần chứng minh database update trong processor tham gia transaction chunk:

1. Dùng database test thực tế hoặc container phù hợp.
2. Processor cập nhật một bảng qua JdbcTemplate dùng cùng DataSource.
3. Writer/test double cố ý ném exception sau khi processor chạy.
4. Step rollback.
5. Query database và xác nhận thay đổi từ processor không tồn tại.
6. Chạy lại với điều kiện thành công và xác nhận thay đổi được commit.

Đừng chỉ verify `JdbcTemplate.update()` đã được gọi. Mock interaction không chứng minh transaction rollback.

## 42. Kiểm thử REQUIRES_NEW

Tạo một service test dùng `REQUIRES_NEW`, gọi từ processor, rồi làm chunk rollback. Xác nhận:

- Business update tham gia chunk transaction bị rollback.
- Audit row từ transaction REQUIRES_NEW vẫn tồn tại.
- Retry không tạo audit duplicate ngoài policy.

Test này giúp cả nhóm hiểu rõ transaction boundary. Dùng database integration test thay vì chỉ mock service để xác nhận propagation thực tế qua Spring proxy.

## 43. Kiểm thử external side effect và retry

Dùng fake HTTP server hoặc stub broker để ghi lại request:

1. Processor gửi request có idempotency key.
2. Fake server ghi nhận operation thành công nhưng client nhận timeout.
3. Step retry cùng item.
4. Fake server nhận lại cùng key.
5. Xác nhận chỉ có một business operation được tạo.
6. Xác nhận processor/step kết thúc theo policy.

Nếu external service không hỗ trợ idempotency, test cần phơi bày rủi ro duplicate và xác định cơ chế reconciliation/compensation. Không giả lập server luôn thất bại trước khi xử lý request vì như vậy bỏ qua crash window quan trọng nhất.

## 44. Kiểm thử processorNonTransactional

Nếu cấu hình `processorNonTransactional()`, cần integration test xác nhận processor output được tái sử dụng trong rollback/retry path đúng như version Spring Batch của dự án.

Test nên:

- Đếm số lần processor được gọi cho cùng item.
- Làm writer thất bại có chủ đích rồi retry.
- So sánh behavior khi bật/tắt processorNonTransactional.
- Xác nhận cache không được coi là durable sau process restart.
- Kiểm tra output cuối và side effect thực tế.

Không viết test chỉ để chứng minh số lần gọi ít hơn; mục tiêu là xác nhận business correctness khi processor không được gọi lại trong một số rollback path.

## 45. Kiểm thử filter và side effect

Tạo input bị processor filter và xác nhận:

- Processor trả null.
- Writer không nhận item đó.
- Không có notification/reservation hoặc external mutation ngoài ý muốn.
- Read/filter/write counts phản ánh semantics mong đợi.

Nếu processor có side effect được phép trước filter, ghi rõ lý do và test riêng. Thông thường, filter decision nên được xác định trước side effect.

## 46. Kiểm thử outbox

Integration test cho outbox nên xác nhận:

- Business row và outbox row cùng commit.
- Nếu writer ném exception, cả hai cùng rollback.
- Nếu commit thành công, publisher có thể đọc outbox row.
- Publisher retry không làm mất event.
- Gửi lại cùng event ID không tạo business effect trùng ở consumer.
- Publisher chết sau send nhưng trước khi mark sent vẫn được xử lý an toàn.

Không chỉ kiểm tra outbox table có row. Hãy test crash window giữa send và update trạng thái, vì đây là nơi duplicate thường xuất hiện.

## 47. Kiểm thử skip và compensation

Nếu processor thực hiện side effect rồi ném exception được cấu hình skip, test cần xác nhận side effect không bị bỏ lại ngoài ý muốn. Nếu business flow yêu cầu compensation, xác nhận:

- Operation ban đầu có ID bền vững.
- Compensation được tạo khi skip/failure.
- Compensation có thể retry.
- Trạng thái cuối được lưu rõ.
- Error ledger cho biết item bị skip và side effect đã được xử lý thế nào.

Nếu không thể compensation, policy có thể cần fail job thay vì skip item. Skip chỉ an toàn khi loại bỏ item không làm hệ thống ở trạng thái dở dang.

## 48. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| API bị gọi hai lần sau rollback | Processor có external side effect và được gọi lại | Idempotency key hoặc outbox |
| Audit row còn sau chunk rollback | Audit service dùng REQUIRES_NEW | Xác định audit là attempt hay committed result; deduplicate |
| Database update trong processor không rollback | Dùng connection/transaction manager độc lập | Dùng transaction resource của step hoặc chuyển ghi sang writer |
| Email đã gửi dù job FAILED | Gửi email trước commit | Ghi notification intent vào outbox và publish sau commit |
| Message được publish nhưng business row rollback | Broker không cùng transaction với database | Transactional outbox/inbox |
| Item bị filter nhưng side effect vẫn xảy ra | Side effect thực hiện trước khi trả null | Quyết định filter trước, chuyển side effect sang writer |
| Skip item nhưng reservation vẫn tồn tại | Processor tạo reservation rồi validation fail | Validate trước hoặc compensation có state |
| Retry lồng nhau tạo quá nhiều request | Service retry và step retry cộng dồn | Phân chia retry budget và timeout |
| processorNonTransactional bị hiểu là rollback | Cache output chỉ tránh một số lần gọi lại | Vẫn dùng idempotency và durable state |
| afterWrite gửi thông báo quá sớm | afterWrite không phải afterCommit | Outbox hoặc commit-aware mechanism |
| Cache nói item đã xử lý dù DB rollback | Mutable in-memory state ngoài transaction | Rebuild/invalidate cache từ source of truth |
| Async processor chạy ngoài transaction | Transaction context không tự truyền qua thread | Thiết kế transaction riêng và idempotency |
| Compensation không chạy sau crash | Chỉ gọi undo trong callback in-memory | Lưu compensation intent bền vững |
| Test pass nhưng production duplicate | Chỉ mock API hoặc repository | Integration test failure sau side effect |

## 49. Quy trình thiết kế processor có side effect

1. **Liệt kê side effect:** database, HTTP, broker, file, notification, cache và audit.
2. **Xác định transaction owner:** side effect có tham gia chunk transaction không?
3. **Giữ processor đơn giản:** ưu tiên validation, mapping, calculation và output DTO.
4. **Chuyển persistence sang writer:** ghi business result và outbox trong cùng transaction khi phù hợp.
5. **Phân loại external call:** read-only lookup hay operation tạo mutation?
6. **Thiết kế idempotency:** dùng operation/event key ổn định qua retry và restart.
7. **Quy định retry/skip:** phân biệt transient error với business validation error.
8. **Xem xét filter:** không tạo side effect cho item cuối cùng bị loại nếu business rule không yêu cầu.
9. **Đánh giá propagation:** tránh REQUIRES_NEW/connection riêng nếu cần rollback cùng chunk.
10. **Dùng outbox hoặc staging:** cho message, email, file và external publication cần độ tin cậy.
11. **Thiết kế compensation:** khi side effect không thể rollback và có thao tác bù trừ.
12. **Test transaction thật:** xác nhận database rollback, retry, skip, duplicate và restart.
13. **Theo dõi operation:** log business key, correlation ID, idempotency key và trạng thái.

## 50. Những nguyên tắc cần nhớ

- `ItemProcessor` nên tập trung validate, transform, enrich và filter; tránh tạo side effect không cần thiết.
- Chunk transaction có thể bao trùm processor, nhưng chỉ hoàn tác những thay đổi tham gia cùng transaction resource.
- JDBC update trong processor chỉ rollback cùng chunk khi dùng đúng transaction-managed DataSource/manager.
- `REQUIRES_NEW`, connection tự mở và service/database độc lập có thể commit ngoài chunk.
- HTTP, email, broker và filesystem thường không tự rollback cùng transaction database.
- Processor có thể được gọi lại trong retry/rollback path; không giả định mỗi item chỉ được process một lần.
- `processorNonTransactional()` có thể cache output để tránh một số lần gọi lại trong cùng execution; nó không undo side effect và không phải durable checkpoint.
- Trả `null` là filter; side effect đã thực hiện trước khi trả null vẫn có thể tồn tại.
- Validate trước side effect và để writer thực hiện persistence khi có thể.
- Dùng idempotency key ổn định cho external operation và business key/unique constraint cho database.
- Dùng transactional outbox để lưu event intent cùng business data; consumer nên có inbox/deduplication.
- `afterWrite` không đồng nghĩa transaction đã commit; callback in-memory sau commit vẫn có crash window.
- Compensation là business operation riêng, không phải rollback tự động.
- Test bằng transaction/database thật và fake external service để mô phỏng timeout sau khi side effect đã xảy ra.
- Kiểm tra retry, skip, filter, rollback, restart và duplicate ở cả output lẫn external system.

Processor side effect và rollback cần được thiết kế theo ranh giới transaction thực tế. Khi processor chủ yếu tạo kết quả có thể lặp lại, writer sở hữu persistence, outbox quản lý publication và external operation có idempotency/compensation, Spring Batch có thể retry hoặc restart mà không để lại side effect trùng hay trạng thái nghiệp vụ nửa chừng.
