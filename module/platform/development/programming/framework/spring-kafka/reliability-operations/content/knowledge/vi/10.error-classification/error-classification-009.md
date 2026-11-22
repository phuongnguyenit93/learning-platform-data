# Database deadlock

Trong hệ thống Spring Kafka, **Database deadlock** là tình huống hai hoặc nhiều transaction trong cơ sở dữ liệu giữ các khóa mà transaction khác cần, tạo thành một vòng chờ không thể tự giải quyết. Database phát hiện vòng chờ và thường chọn một transaction làm deadlock victim, rollback transaction đó để giải phóng lock cho transaction còn lại.

Deadlock thường xuất hiện ở consumer khi nhiều message được xử lý đồng thời và các listener cập nhật những hàng dữ liệu có quan hệ với nhau. Kafka có thể giao record đúng thứ tự trong từng partition, nhưng các consumer, service hoặc request bên ngoài vẫn có thể cùng cập nhật một tập dữ liệu. Vì vậy, deadlock là lỗi phối hợp transaction ở database; nó cần được chẩn đoán bằng lock graph và query của database, sau đó xử lý bằng cách giảm xung đột khóa, rút ngắn transaction và retry có kiểm soát.

Trong Spring Kafka, điều quan trọng là **để transaction database rollback hoàn tất trước khi thử xử lý message lần nữa**. Nếu retry bên trong transaction đã bị đánh dấu rollback-only, các lần thử tiếp theo không tạo ra một giao dịch sạch và có thể tiếp tục thất bại.

## 1. Deadlock là gì?

Một transaction thường khóa hàng, trang hoặc tài nguyên khác khi đọc hoặc ghi dữ liệu. Lock giúp database bảo vệ tính nhất quán khi nhiều transaction chạy đồng thời.

Deadlock xảy ra khi có một chu trình phụ thuộc lock. Ví dụ:

- Transaction T1 đã khóa hàng A và cần khóa hàng B.
- Transaction T2 đã khóa hàng B và cần khóa hàng A.
- T1 phải đợi T2 nhả B.
- T2 phải đợi T1 nhả A.

Cả hai transaction đều không thể tiếp tục. Database phát hiện chu trình và chọn một transaction để rollback. Transaction còn lại sau đó có thể lấy lock và tiếp tục.

~~~mermaid
flowchart TD
    A["T1 giữ lock hàng A"] --> B["T1 chờ lock hàng B"]
    C["T2 giữ lock hàng B"] --> D["T2 chờ lock hàng A"]
    B --> C
    D --> A
    E["Database phát hiện chu trình"] --> F["Chọn deadlock victim"]
    F --> G["Rollback victim, giải phóng lock"]
    G --> H["Transaction còn lại tiếp tục"]
~~~

Deadlock không đơn giản là một transaction chạy chậm. Điểm cốt lõi là các transaction đang giữ tài nguyên và chờ lẫn nhau theo một chu trình.

## 2. Ví dụ deadlock ở tầng database

Giả sử hệ thống có hai bảng:

- **orders** lưu trạng thái đơn hàng.
- **inventory** lưu số lượng tồn kho theo sản phẩm.

Một transaction xử lý đơn hàng có thể cập nhật đơn hàng rồi giảm tồn kho. Một transaction khác cập nhật tồn kho rồi cập nhật đơn hàng.

~~~sql
-- Transaction T1
BEGIN;

UPDATE orders
SET status = 'ALLOCATING'
WHERE order_id = 1001;

UPDATE inventory
SET available = available - 1
WHERE product_id = 77;

COMMIT;
~~~

~~~sql
-- Transaction T2
BEGIN;

UPDATE inventory
SET available = available + 1
WHERE product_id = 77;

UPDATE orders
SET status = 'AVAILABLE'
WHERE order_id = 1001;

COMMIT;
~~~

Nếu T1 khóa hàng trong orders trước, còn T2 khóa hàng trong inventory trước, hai transaction có thể chờ lock của nhau. Database sẽ chọn một transaction làm victim.

Thứ tự câu lệnh trong ví dụ minh họa một dạng lock cycle. Deadlock thực tế còn phụ thuộc execution plan, index, isolation level, lock granularity, trigger, foreign key và các transaction khác cùng chạy. Một deadlock graph từ database mới cho biết chính xác tài nguyên và câu lệnh tham gia chu trình.

## 3. Deadlock khác lock wait timeout như thế nào?

Hai lỗi này có biểu hiện giống nhau ở chỗ transaction không lấy được lock, nhưng nguyên nhân và cách xử lý khác nhau.

| Đặc điểm | Deadlock | Lock wait timeout |
|---|---|---|
| Nguyên nhân | Có chu trình chờ lock giữa các transaction | Một transaction chờ lock quá thời gian cho phép |
| Quan hệ chờ | Tạo thành vòng phụ thuộc | Có thể chỉ là một chiều, không có chu trình |
| Cách database phản ứng | Thường tự chọn victim và rollback | Hủy hoặc báo lỗi transaction đang chờ tùy DB/configuration |
| Dấu hiệu điều tra | Deadlock graph, victim, lock resource, SQL statement | Blocking session, thời gian giữ lock, wait event |
| Cách khắc phục | Phá chu trình bằng thứ tự lock, transaction ngắn hơn, giảm contention | Giảm thời gian giữ lock, tìm blocking transaction, điều chỉnh timeout khi có căn cứ |

Tăng lock wait timeout không giải quyết được deadlock cycle. Một chu trình không tự biến mất chỉ vì transaction được phép chờ lâu hơn; database cần phát hiện và phá chu trình.

## 4. Database deadlock xuất hiện trong luồng Spring Kafka ra sao?

Một consumer thường đọc record, gọi service nghiệp vụ và cập nhật database. Nếu nhiều record được xử lý đồng thời, các transaction database có thể cạnh tranh trên cùng hàng hoặc các nhóm hàng liên quan.

Ví dụ:

~~~mermaid
flowchart TD
    A["Kafka topic<br/>orders.events"] --> B["Consumer group"]
    B --> C["Consumer 1"]
    B --> D["Consumer 2"]
    C --> E["Listener xử lý event A"]
    D --> F["Listener xử lý event B"]
    E --> G["Database transaction T1"]
    F --> H["Database transaction T2"]
    G --> I["Cùng tập dữ liệu / lock"]
    H --> I
    I --> J["Deadlock detector"]
    J --> K["Rollback một transaction"]
    K --> L["Listener/container nhận lỗi"]
    L --> M["Retry sau rollback hoặc recovery"]
~~~

Deadlock có thể phát sinh khi:

- Nhiều message cập nhật cùng một order, account, inventory item hoặc aggregate.
- Các listener cập nhật nhiều bảng theo thứ tự khác nhau.
- Một consumer group có concurrency cao và xử lý nhiều record cùng lúc.
- Nhiều service hoặc HTTP request cùng cập nhật database với consumer.
- Trigger, foreign key cascade hoặc index làm transaction giữ thêm lock mà code ứng dụng không nhìn thấy trực tiếp.
- Transaction giữ lock trong lúc gọi API hoặc thực hiện công việc chậm khác.

Kafka không tạo deadlock trong database. Kafka chỉ đưa các record đến consumer; deadlock xảy ra khi các transaction database cạnh tranh trên tài nguyên dùng chung.

## 5. Vì sao concurrency và partition có thể ảnh hưởng deadlock?

Concurrency cao cho phép nhiều listener invocation chạy đồng thời hơn. Điều này thường tăng throughput, nhưng cũng làm tăng số transaction database hoạt động cùng lúc và khả năng tranh chấp lock.

Một topic có nhiều partition có thể phân phối record cho nhiều consumer. Nếu các record từ những partition khác nhau cùng cập nhật một hàng inventory hoặc account, chúng vẫn có thể deadlock dù mỗi partition giữ thứ tự riêng.

Partition key có thể giúp giữ thứ tự cho cùng một aggregate trong một consumer group:

- Các event có cùng key thường đi vào cùng partition.
- Một partition trong cùng consumer group chỉ được giao cho một consumer tại một thời điểm.
- Các event trên partition được đọc theo thứ tự offset.

Điều này có thể giảm xử lý đồng thời cho cùng một aggregate trong một group. Tuy nhiên, nó không bảo vệ database khỏi writer khác, consumer group khác hoặc HTTP request cập nhật cùng hàng. Nếu hai service cùng sửa một account, việc partition theo account ID ở một topic không tự tuần tự hóa tất cả transaction trong database.

Không nên tăng concurrency chỉ dựa trên số partition. Cần đo lock wait, deadlock rate, transaction duration, connection pool và năng lực database.

## 6. Dấu hiệu và exception trong Spring

Database driver thường trả về lỗi vendor-specific. Spring JDBC, Spring Data hoặc Hibernate có thể dịch lỗi đó thành exception trong hệ thống phân cấp của Spring.

Một số ví dụ thường gặp:

| Database | Dấu hiệu thường thấy |
|---|---|
| MySQL / InnoDB | Error 1213, SQLSTATE 40001: deadlock found when trying to get lock |
| PostgreSQL | SQLSTATE 40P01: deadlock detected |
| SQL Server | Error 1205: transaction was deadlocked on lock resources |
| Oracle | ORA-00060: deadlock detected while waiting for resource |

Thông tin thực tế phụ thuộc driver, phiên bản database và lớp truy cập dữ liệu. Spring có thể bọc lỗi gốc thành các loại như **PessimisticLockingFailureException**, **CannotAcquireLockException** hoặc exception chuyên biệt khác. Một số codebase cũ có thể gặp **DeadlockLoserDataAccessException**.

Không nên chỉ kiểm tra tên exception ở lớp ngoài cùng. Hãy ghi nhận cause chain, SQLState, vendor error code và thông tin transaction từ database log. Không phải mọi **PessimisticLockingFailureException** đều là deadlock; nó cũng có thể đại diện cho lỗi khóa khác.

### Phân biệt deadlock với các lỗi database khác

- **ConstraintViolationException** hoặc lỗi unique constraint thường là vi phạm dữ liệu, không phải lock cycle có thể retry tùy ý.
- **CannotAcquireLockException** có thể phản ánh deadlock hoặc lỗi lấy lock khác tùy driver và exception translation.
- **DataIntegrityViolationException** thường cần xử lý dữ liệu hoặc nghiệp vụ.
- **TransientDataAccessException** biểu thị nhóm lỗi tạm thời rộng; không nên giả định tất cả đều là deadlock.
- **Connection failure** hoặc database unavailable là sự cố kết nối/hạ tầng và cần chính sách retry riêng.

Phân loại dựa trên exception gốc và mã lỗi database, không chỉ dựa vào một tên lớp tổng quát.

## 7. Transaction boundary trong ứng dụng Spring

Một listener thường nên giao công việc database cho service có transaction riêng. Khi service ném lỗi deadlock, transaction interceptor rollback transaction trước khi exception quay lại listener container.

Ví dụ:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final OrderProcessingService processingService;

    public OrderEventListener(OrderProcessingService processingService) {
        this.processingService = processingService;
    }

    @KafkaListener(
        topics = "orders.events",
        groupId = "order-processor"
    )
    public void onOrderEvent(OrderEvent event) {
        processingService.process(event);
    }
}
~~~

Service quản lý transaction database:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProcessingService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderProcessingService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void process(OrderEvent event) {
        var order = orderRepository.findForUpdate(event.orderId())
                .orElseThrow();

        var inventory = inventoryRepository.findForUpdate(event.productId())
                .orElseThrow();

        inventory.reserve(event.quantity());
        order.markAllocated();
    }
}
~~~

Trong ví dụ, repository có thể dùng locking query phù hợp với database, chẳng hạn pessimistic write lock. Khi database phát hiện deadlock và ném lỗi, transaction service bị rollback. Listener nhận exception sau khi lời gọi service kết thúc và container có thể áp dụng retry policy.

### Vì sao phải để exception thoát khỏi transaction?

Nếu service bắt deadlock exception rồi tiếp tục trả về bình thường, Spring có thể không nhận được tín hiệu để rollback theo mong đợi. Transaction cũng có thể đã bị database rollback hoặc Spring đánh dấu rollback-only. Những câu lệnh tiếp theo có thể thất bại hoặc lần commit cuối cùng ném **UnexpectedRollbackException**.

Khi deadlock xảy ra, hãy để exception đi qua ranh giới transaction để transaction kết thúc. Chỉ sau đó mới bắt đầu một lần thử mới bằng transaction mới.

### Self-invocation và transaction proxy

Spring transaction thường được áp dụng qua proxy. Nếu một method trong cùng object gọi trực tiếp method khác có **@Transactional**, lời gọi nội bộ có thể không đi qua proxy và annotation không tạo transaction mới như mong đợi.

Tách nghiệp vụ transaction thành một Spring service bean được inject vào listener giúp ranh giới transaction rõ ràng. Khi cần retry ngoài transaction, cũng nên đặt retry ở lớp gọi service transaction qua proxy, hoặc để listener container thực hiện retry sau khi lời gọi transaction trước đã kết thúc.

## 8. Retry deadlock đúng cách

Deadlock thường là lỗi tạm thời: database đã rollback một transaction để transaction khác có thể tiếp tục. Retry có thể thành công khi transaction cạnh tranh đã kết thúc. Tuy nhiên, nếu cấu trúc truy cập dữ liệu luôn tạo lock cycle, retry liên tục chỉ lặp lại cùng sự cố.

Một retry phù hợp cần:

1. Để transaction lỗi rollback hoàn toàn.
2. Chờ một khoảng thời gian ngắn trước khi thử lại.
3. Mỗi lần thử chạy trong transaction mới.
4. Giới hạn số lần retry.
5. Phân loại deadlock là lỗi có thể retry; không retry lỗi dữ liệu vĩnh viễn.
6. Nếu hết retry, chuyển sang recovery/DLT hoặc quy trình xử lý có thể phục hồi.
7. Bảo đảm side effect idempotent để redelivery không gây tác động trùng.

### Retry tại listener container

Khi listener method ném exception ra ngoài, **DefaultErrorHandler** có thể retry record theo BackOff đã cấu hình. Với một listener gọi service có transaction database, mỗi lần container gọi lại listener sẽ gọi lại service và mở transaction mới, miễn là transaction trước đã rollback trước khi exception thoát ra.

Ví dụ cấu hình minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.ExponentialBackOff;

@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler databaseRetryErrorHandler() {
        ExponentialBackOff backOff = new ExponentialBackOff(250L, 2.0);
        backOff.setMaxInterval(4_000L);
        backOff.setMaxElapsedTime(15_000L);

        DefaultErrorHandler handler = new DefaultErrorHandler(backOff);

        handler.addRetryableExceptions(
                PessimisticLockingFailureException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler databaseRetryErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(databaseRetryErrorHandler);

        return factory;
    }
}
~~~

Đây là ví dụ minh họa cho các phiên bản Spring Kafka có **CommonErrorHandler** và **DefaultErrorHandler**. Tùy phiên bản, API BackOff và exception translation có thể khác. Trong ứng dụng thực tế, chỉ đăng ký loại exception thực sự đại diện cho deadlock hoặc lỗi khóa tạm thời của database đang dùng. Nếu driver ném exception vendor-specific chưa được Spring dịch, cần phân loại cause chain hoặc dịch lỗi ở lớp truy cập dữ liệu.

Không dùng cấu hình retry chung cho mọi exception. Lỗi validation, dữ liệu không hợp lệ hoặc vi phạm nghiệp vụ thường không tự biến mất sau vài lần thử.

### Retry bên trong service có transaction

Không nên viết vòng lặp retry bên trong method đã mở transaction:

~~~java
@Transactional
public void process(OrderEvent event) {
    for (int attempt = 0; attempt < 3; attempt++) {
        try {
            updateDatabase(event);
            return;
        } catch (PessimisticLockingFailureException ex) {
            // Không an toàn nếu tiếp tục dùng transaction đã lỗi.
        }
    }
}
~~~

Sau deadlock, transaction hiện tại có thể đã bị rollback hoặc đánh dấu rollback-only. Tiếp tục sử dụng nó không tạo ra một lần thử độc lập.

Nếu cần retry ở tầng service, cấu trúc nên là một method không transaction gọi method transaction qua proxy, mỗi lần thử mở transaction mới. Ví dụ khái niệm:

~~~java
@Service
public class RetryingOrderProcessor {

    private final TransactionalOrderWriter writer;

    public RetryingOrderProcessor(TransactionalOrderWriter writer) {
        this.writer = writer;
    }

    public void processWithRetry(OrderEvent event) {
        // Retry ở ngoài transaction.
        // Mỗi lần gọi writer.process() đi qua transaction proxy.
        writer.process(event);
    }
}

@Service
public class TransactionalOrderWriter {

    @Transactional
    public void process(OrderEvent event) {
        // Các thao tác database trong một transaction ngắn.
    }
}
~~~

Đoạn code trên chỉ thể hiện ranh giới. Muốn retry nhiều lần ở lớp ngoài, cần thêm retry mechanism với BackOff và exception classifier, hoặc dùng listener container. Không tự tạo vòng retry vô hạn.

## 9. Trường hợp listener dùng Kafka transaction

Nếu listener container dùng **KafkaTransactionManager**, đường xử lý exception khác với một listener chỉ dùng database transaction.

Trong transactional listener container:

- Container bắt đầu Kafka transaction cho quá trình xử lý.
- Listener thực hiện nghiệp vụ và có thể gửi record đầu ra.
- Nếu listener ném exception, Kafka transaction rollback.
- **AfterRollbackProcessor** xử lý việc seek/redelivery và số lần thử sau rollback.
- Sau khi retry hết giới hạn, recovery có thể được thực hiện theo cấu hình processor.

Nếu listener đồng thời cập nhật database, cần hiểu rõ database transaction và Kafka transaction được phối hợp như thế nào. Kafka transaction không tự rollback database transaction, và một deadlock database phải được xử lý bởi transaction manager của database.

Không mặc định rằng **DefaultErrorHandler** là cơ chế retry duy nhất cho transactional listener container. Với container transaction, hãy cấu hình và kiểm tra **DefaultAfterRollbackProcessor** hoặc AfterRollbackProcessor phù hợp với phiên bản Spring Kafka.

Nếu listener chỉ dùng database transaction qua **@Transactional** và không dùng Kafka transaction cho container, error handler của listener container thường là nơi phù hợp để retry exception sau khi transaction database đã rollback.

## 10. Bảo đảm idempotency khi Kafka giao lại record

Giả sử listener cập nhật database thành công nhưng process dừng trước khi offset Kafka được commit. Khi consumer khởi động lại, record có thể được giao lại. Nếu không có idempotency, nghiệp vụ có thể chạy hai lần.

Một mẫu phổ biến là lưu event ID trong inbox table cùng transaction với cập nhật nghiệp vụ:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Service xử lý event theo hướng idempotent:

~~~java
@Transactional
public void process(OrderEvent event) {
    boolean inserted = processedEventRepository.insertIfAbsent(
            event.eventId(),
            Instant.now()
    );

    if (!inserted) {
        return;
    }

    orderRepository.apply(event);
}
~~~

Đoạn code minh họa yêu cầu **insertIfAbsent** phải được triển khai bằng thao tác atomic phù hợp với database, ví dụ insert có xử lý conflict hoặc unique constraint. Không dùng cách đọc rồi insert không có constraint vì hai consumer có thể đồng thời thấy event chưa tồn tại.

Inbox marker và thay đổi nghiệp vụ phải nằm trong cùng database transaction. Nếu transaction rollback do deadlock, marker cũng rollback; lần retry có thể xử lý lại. Nếu transaction commit nhưng Kafka offset chưa commit, record giao lại sẽ gặp unique event ID và không áp dụng side effect lần nữa.

Nếu nghiệp vụ cập nhật nhiều bảng, marker phải commit cùng toàn bộ thay đổi cần bảo vệ. Nếu listener phát event đầu ra, dùng outbox để lưu sự kiện đầu ra cùng transaction database.

## 11. Nguyên nhân thường gặp và cách giảm deadlock

### Không nhất quán thứ tự lấy lock

Đây là nguyên nhân dễ nhận biết. Một luồng cập nhật bảng A rồi B, luồng khác cập nhật B rồi A. Hãy thống nhất thứ tự truy cập tài nguyên ở tất cả code path.

Ví dụ, mọi luồng cập nhật đơn hàng và tồn kho đều lấy lock theo thứ tự:

1. Hàng orders.
2. Hàng inventory.
3. Hàng shipment.

Nếu có nhiều product trong một đơn hàng, sắp xếp product ID trước khi khóa để các transaction lấy lock theo cùng thứ tự. Thứ tự nhất quán làm giảm khả năng tạo chu trình chờ.

### Transaction quá dài

Transaction giữ lock càng lâu thì cơ hội transaction khác đụng vào cùng tài nguyên càng lớn. Tránh:

- Gọi REST API trong khi transaction database đang mở.
- Gửi email hoặc gọi dịch vụ ngoài trong transaction.
- Chờ message hoặc thread khác trong khi giữ lock.
- Xử lý file lớn hoặc tính toán lâu trước khi commit.
- Thực hiện nhiều truy vấn không cần thiết trong transaction.

Hãy chuẩn bị dữ liệu ngoài transaction nếu an toàn, rồi mở transaction ngắn chỉ để đọc/ghi những gì cần thiết. Với side effect bên ngoài, dùng outbox hoặc workflow phù hợp.

### Thiếu index hoặc query khóa quá rộng

Một câu lệnh UPDATE hoặc SELECT FOR UPDATE không dùng index phù hợp có thể quét và khóa nhiều hàng hơn dự kiến. Query plan và index ảnh hưởng số tài nguyên bị khóa cũng như thời gian giữ lock.

Kiểm tra execution plan, điều kiện WHERE, index, foreign key và trigger. Tránh cập nhật theo điều kiện quá rộng nếu nghiệp vụ chỉ cần một hàng. Với các truy vấn khóa, xác nhận database dùng index mong muốn.

### Batch quá lớn

Một batch listener có thể cập nhật hàng trăm hoặc hàng nghìn record trong một transaction. Transaction dài và giữ nhiều lock có thể làm deadlock dễ xảy ra hơn.

Cân nhắc chia thành chunk nhỏ với transaction riêng cho mỗi chunk. Tuy nhiên, khi chia chunk, cần xác định semantics nghiệp vụ: nếu chunk trước đã commit và chunk sau thất bại, record có thể được retry. Consumer phải idempotent hoặc có checkpoint nghiệp vụ để tiếp tục an toàn.

### Isolation level và locking strategy

Isolation level cao có thể tăng số lock hoặc thời gian giữ lock tùy database. Pessimistic locking có thể cần thiết khi tranh chấp cao, nhưng cũng làm tăng khả năng chờ lock. Optimistic locking dùng version column có thể phù hợp khi xung đột hiếm.

Không hạ isolation level chỉ để giảm deadlock nếu chưa đánh giá nguy cơ đọc dữ liệu không nhất quán. Chọn chiến lược dựa trên invariants nghiệp vụ và đặc tính DB engine.

### Giảm cạnh tranh bằng partition key và concurrency

Nếu event cùng aggregate có thể được định tuyến về cùng partition, một consumer group sẽ xử lý tuần tự các event đó. Điều này có thể giảm cạnh tranh trên cùng aggregate. Hãy cân nhắc key như **accountId**, **orderId** hoặc **inventoryId** tùy ranh giới nghiệp vụ.

Giảm concurrency của listener có thể giảm số transaction cạnh tranh đồng thời, nhưng cũng làm throughput giảm. Hãy thử nghiệm bằng metric deadlock, transaction duration, consumer lag và database CPU/IO.

## 12. Chẩn đoán deadlock bằng dữ liệu database

Log ứng dụng thường chỉ cho biết một transaction đã thất bại. Deadlock graph hoặc diagnostic report của database mới cho thấy các transaction, lock resource và câu lệnh tạo thành chu trình.

Thông tin cần thu thập:

- Thời điểm và database instance.
- Transaction ID hoặc session ID của các bên tham gia.
- SQL statement đang chạy và câu lệnh đã lấy lock trước đó.
- Bảng, index, row/page hoặc resource bị khóa.
- Lock mode của từng transaction.
- Transaction được chọn làm victim.
- Isolation level và execution plan liên quan.
- Event ID, topic, partition, offset và consumer instance để liên kết với message.

### MySQL / InnoDB

InnoDB cung cấp thông tin deadlock gần nhất qua **SHOW ENGINE INNODB STATUS**. Trong môi trường cần điều tra thường xuyên, có thể cân nhắc cấu hình ghi deadlock vào error log theo chính sách DBA. Deadlock report thể hiện transaction, lock đang giữ, lock đang chờ và câu lệnh liên quan.

Không bật logging quá mức mà không cân nhắc dung lượng và chính sách vận hành. Thu thập report gần thời điểm sự cố vì thông tin “latest detected deadlock” có thể bị một deadlock khác ghi đè.

### PostgreSQL

PostgreSQL ghi thông báo deadlock vào server log khi phát hiện chu trình. Các thiết lập logging như **log_lock_waits** và **deadlock_timeout** giúp quan sát lock wait, nhưng log lock wait không đồng nghĩa mọi wait đều là deadlock.

Kết hợp server log với **pg_stat_activity**, **pg_locks** và thông tin query để tìm blocking session và quan hệ lock. Khi transaction bị hủy do deadlock, SQLSTATE thường là **40P01**.

### SQL Server

SQL Server có thể thu thập deadlock graph qua Extended Events, thường thông qua event **xml_deadlock_report**. Graph cho biết victim, process list và resource list. Dùng graph để xác định bảng/index và thứ tự lock.

### Oracle

Oracle ghi nhận deadlock qua thông báo **ORA-00060** và trace file tương ứng. Trace giúp xác định câu lệnh và resource liên quan. DBA cần đối chiếu execution plan, session và transaction tại thời điểm lỗi.

Tên công cụ và vị trí log tùy phiên bản, quyền DBA và cấu hình hệ thống. Ứng dụng không nên cố tự truy vấn thông tin quản trị nhạy cảm nếu principal của nó không có quyền.

## 13. Logging và metric ở phía Spring Kafka

Để liên kết deadlock ở database với message đã kích hoạt nó, log ứng dụng cần có ngữ cảnh của consumer và nghiệp vụ.

Các trường hữu ích:

| Trường | Mục đích |
|---|---|
| service và environment | Xác định workload |
| consumer group | Xác định group xử lý record |
| topic, partition, offset | Định vị record trong Kafka |
| event ID / correlation ID | Liên kết với nghiệp vụ và inbox/outbox |
| database transaction/session ID | Liên kết với DB deadlock report nếu có |
| exception class, SQLState, vendor code | Phân loại lỗi database |
| retry attempt và backoff | Theo dõi quá trình phục hồi |
| processing duration | Phát hiện transaction hoặc listener chậm |
| instance / client ID | Xác định consumer tạo transaction |

Không log mật khẩu, token, connection string có secret hoặc toàn bộ payload chứa dữ liệu nhạy cảm. Dùng event ID và các trường đã được phép để tra cứu dữ liệu gốc.

### Metric nên theo dõi

- Deadlock count theo database và service.
- Số transaction rollback do deadlock.
- Lock wait duration và số lock timeout.
- Listener failure rate theo exception class.
- Retry attempt và recovery/DLT rate.
- Consumer lag theo topic, partition và group.
- Transaction duration và connection pool utilization.
- Throughput trước và sau khi điều chỉnh concurrency.

Một deadlock đơn lẻ được retry thành công vẫn cần được theo dõi. Nếu tỷ lệ deadlock tăng, retry chỉ che triệu chứng và có thể làm tải database nặng hơn.

## 14. Retry, backoff và DLT

Deadlock có thể retry vì database đã rollback victim và giải phóng lock. Nhưng retry cần có giới hạn và khoảng nghỉ. Nếu tất cả consumer retry ngay lập tức, chúng có thể va chạm lại trên cùng các hàng và tạo một đợt deadlock mới.

Một chính sách thường dùng:

- Retry một số lần nhỏ.
- Dùng exponential backoff với giới hạn tối đa.
- Thêm jitter nếu nhiều consumer có thể retry cùng thời điểm.
- Không retry lỗi dữ liệu không thể tự khắc phục.
- Sau khi hết retry, chuyển record sang DLT hoặc recovery store có thể quan sát và replay.
- Alert khi deadlock vượt ngưỡng hoặc event tồn đọng quá lâu.

DLT là một phần của quy trình phục hồi, không phải nơi để che lỗi. Khi record được chuyển DLT, cần lưu exception, event ID, topic gốc, partition, offset và timestamp để điều tra. Replay phải giữ idempotency và có kiểm soát thứ tự nếu nghiệp vụ yêu cầu.

Nếu dùng transactional listener container, recovery và offset commit cần được cấu hình qua AfterRollbackProcessor phù hợp. Nếu chỉ dùng database transaction với listener container thông thường, có thể dùng DefaultErrorHandler sau khi transaction database rollback.

## 15. Deadlock trong batch listener

Batch listener nhận nhiều record trong một lần gọi. Nếu xử lý toàn bộ batch trong một transaction, số hàng được cập nhật và số lock đang giữ có thể lớn. Một record gây deadlock có thể làm rollback toàn bộ transaction của batch.

Các lựa chọn:

- Giảm batch size để giảm số record và lock được xử lý trong một transaction.
- Chia batch thành chunk và commit từng chunk nếu nghiệp vụ cho phép.
- Sắp xếp các khóa theo một thứ tự ổn định trước khi cập nhật.
- Dùng sub-batch theo partition nếu ranh giới xử lý/transaction theo partition phù hợp.
- Dùng idempotency để chịu được việc một phần công việc đã commit trước khi batch tiếp theo thất bại.

Không mặc định chia batch theo partition sẽ giải quyết deadlock. Nếu hai partition vẫn cập nhật cùng account hoặc inventory row, các transaction vẫn có thể cạnh tranh. Phải sửa thứ tự lock hoặc mô hình dữ liệu ở database.

## 16. Runbook xử lý production

Khi consumer phát sinh database deadlock:

1. Xác định service, consumer group, topic, partition, offset và event ID.
2. Thu thập exception gốc, SQLState, vendor code và cause chain.
3. Ghi nhận database instance, transaction/session ID và timestamp.
4. Lấy deadlock graph hoặc report từ database.
5. Xác định victim, transaction còn lại, lock resource và câu lệnh tham gia.
6. Kiểm tra các code path cập nhật cùng bảng/hàng có thứ tự lấy lock khác nhau hay không.
7. Đo transaction duration, query plan, index, batch size và số consumer đồng thời.
8. Xác nhận transaction database đã rollback trước khi retry.
9. Kiểm tra error handler hoặc AfterRollbackProcessor và số lần retry thực tế.
10. Kiểm tra event đã được xử lý một phần hay chưa; xác minh inbox/idempotency.
11. Điều chỉnh thứ tự lock, transaction boundary, query/index hoặc concurrency dựa trên bằng chứng.
12. Kiểm thử lại với tải cạnh tranh tương tự production.
13. Theo dõi deadlock rate, listener retry, DLT, consumer lag và database load sau triển khai.

Nếu retry thành công nhưng deadlock lặp lại, không đóng sự cố chỉ dựa vào việc consumer đã tiếp tục. Ghi nhận nguyên nhân gốc và lên kế hoạch loại bỏ chu trình lock.

## 17. Kiểm thử deadlock và khả năng phục hồi

Kiểm thử deadlock nên dùng cùng loại database engine với production vì lock behavior khác nhau giữa các DB. H2 hoặc mock repository không thể thay thế kiểm thử lock semantics của MySQL, PostgreSQL, SQL Server hoặc Oracle.

Một kịch bản kiểm thử có kiểm soát:

1. Chuẩn bị hai hàng A và B.
2. Mở transaction T1 và khóa A.
3. Mở transaction T2 và khóa B.
4. Cho T1 yêu cầu B.
5. Cho T2 yêu cầu A.
6. Xác nhận database phát hiện deadlock và một transaction bị rollback.
7. Xác nhận service nhận exception sau khi transaction kết thúc.
8. Cho listener container retry record theo BackOff.
9. Xác nhận lần retry chạy trong transaction mới.
10. Xác nhận side effect chỉ được áp dụng một lần nhờ idempotency.
11. Xác nhận offset chỉ được commit sau khi listener/recovery hoàn tất theo cấu hình.

Trong test tự động, cần dùng barrier hoặc latch để điều phối thứ tự lock thay vì dựa vào sleep tùy ý. Giữ timeout hữu hạn để test không treo nếu deadlock không xảy ra. Dọn dữ liệu test trong transaction hoặc fixture riêng.

### Các tình huống cần bao phủ

| Tình huống | Kết quả mong đợi |
|---|---|
| Deadlock xảy ra một lần | Victim rollback, retry trong transaction mới có thể thành công |
| Deadlock lặp quá số lần | Record đi vào recovery/DLT theo chính sách |
| Lỗi unique constraint | Không retry như deadlock nếu lỗi không thể tự phục hồi |
| Listener dừng sau DB commit trước Kafka offset commit | Record có thể redeliver nhưng idempotency ngăn side effect trùng |
| Retry nhiều consumer cùng lúc | Backoff giảm va chạm; deadlock rate được theo dõi |
| Batch có một record gây lỗi | Transaction/chunk rollback đúng phạm vi đã thiết kế |
| DB unavailable | Áp dụng chính sách kết nối riêng, không gắn nhầm thành deadlock |

## 18. Những cách xử lý sai thường gặp

**Retry ngay trong transaction đã lỗi.** Transaction có thể đã rollback hoặc rollback-only. Kết thúc transaction rồi bắt đầu lần thử mới.

**Retry vô hạn.** Deadlock lặp lại có thể làm tăng tải database, consumer lag và số transaction rollback. Giới hạn số lần và có recovery.

**Chỉ tăng timeout.** Timeout không phá lock cycle. Hãy dùng deadlock graph để tìm nguyên nhân.

**Giảm concurrency mà không đo.** Có thể giảm contention nhưng cũng giảm throughput. Dùng metric trước và sau thay đổi để đánh giá.

**Cập nhật bảng theo thứ tự khác nhau ở từng service.** Chuẩn hóa thứ tự lấy lock trên tất cả code path.

**Giữ transaction mở khi gọi API ngoài.** Thời gian giữ lock tăng và khả năng deadlock tăng. Đưa network call ra ngoài transaction hoặc dùng outbox/workflow.

**Dùng batch quá lớn.** Transaction giữ nhiều lock lâu hơn. Chia chunk nếu semantics nghiệp vụ cho phép.

**Bắt exception rồi trả listener bình thường.** Container có thể xem message đã xử lý và tiến offset dù database transaction thất bại. Hãy để lỗi đi qua đúng ranh giới để retry/recovery.

**Chuyển mọi database exception vào DLT.** Lỗi tạm thời có thể phục hồi bằng retry. Phân loại exception và chỉ recovery sau chính sách retry phù hợp.

**Cho rằng Kafka partition loại bỏ deadlock.** Partition ordering chỉ áp dụng trong phạm vi một topic-partition và một consumer group. Các writer khác vẫn có thể cạnh tranh cùng hàng database.

## 19. Checklist vận hành

**Chẩn đoán database**

- [ ] Có exception gốc, SQLState và vendor error code.
- [ ] Đã thu thập deadlock graph hoặc report của database.
- [ ] Xác định được victim, transaction còn lại và resource bị khóa.
- [ ] Đã kiểm tra execution plan, index, trigger và foreign key liên quan.
- [ ] Đã so sánh thứ tự lấy lock của các code path.

**Spring transaction và retry**

- [ ] Transaction database kết thúc/rollback trước lần retry tiếp theo.
- [ ] Mỗi lần thử sử dụng transaction mới.
- [ ] Exception deadlock được phân loại là retryable có chủ đích.
- [ ] Backoff và số lần retry có giới hạn.
- [ ] Lỗi dữ liệu không thể phục hồi không bị retry vô hạn.
- [ ] Transactional listener dùng AfterRollbackProcessor phù hợp nếu có Kafka transaction.

**Kafka và nghiệp vụ**

- [ ] Listener không nuốt exception sau khi DB rollback.
- [ ] Consumer có idempotency/inbox để chịu redelivery.
- [ ] Batch/chunk có ranh giới transaction rõ ràng.
- [ ] DLT/recovery lưu đủ metadata để điều tra và replay.
- [ ] Offset chỉ tiến theo semantics xử lý/recovery đã cấu hình.

**Quan sát và phòng ngừa**

- [ ] Log có topic, partition, offset, event ID và consumer instance.
- [ ] Có liên kết timestamp/session với database deadlock report.
- [ ] Theo dõi deadlock rate, rollback, retry, DLT, lag và transaction duration.
- [ ] Thứ tự lock được chuẩn hóa và transaction được giữ ngắn.
- [ ] Đã kiểm thử deadlock trên đúng loại database engine.

## 20. Nguyên tắc xử lý

Database deadlock là xung đột giữa các transaction đang giữ và chờ lock theo một chu trình. Kafka consumer có thể làm tăng mức đồng thời của các transaction, nhưng nguyên nhân gốc nằm ở cách database truy cập và khóa tài nguyên.

Trong Spring Kafka, hãy để transaction database rollback hoàn tất, sau đó retry message trong một transaction mới với BackOff và giới hạn rõ ràng. Dùng deadlock graph để tìm câu lệnh và resource tạo chu trình; thống nhất thứ tự lấy lock, rút ngắn transaction, kiểm tra index và cân nhắc concurrency hoặc batch size theo số liệu. Kết hợp idempotency với commit offset để record được giao lại không tạo side effect trùng.

## 21. Ví dụ triển khai retry ở lớp service ngoài transaction

Trong một số hệ thống, đội phát triển muốn retry ở tầng service thay vì để container retry. Khi đó, retry phải bao quanh một method transaction riêng được gọi qua Spring proxy. Mỗi lần gọi method transaction là một transaction mới.

Ví dụ dùng Spring Retry nếu ứng dụng đã có dependency và cấu hình tương ứng:

~~~java
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class RetryingOrderApplicationService {

    private final TransactionalOrderWriter writer;

    public RetryingOrderApplicationService(TransactionalOrderWriter writer) {
        this.writer = writer;
    }

    @Retryable(
        retryFor = PessimisticLockingFailureException.class,
        maxAttempts = 4,
        backoff = @Backoff(delay = 250, multiplier = 2.0, maxDelay = 4_000)
    )
    public void process(OrderEvent event) {
        writer.write(event);
    }
}

@Service
public class TransactionalOrderWriter {

    @Transactional
    public void write(OrderEvent event) {
        // Lock rows in a consistent order and apply the database changes.
    }
}
~~~

Method **process** không mở transaction. Nó gọi **write** qua một bean khác, nên transaction proxy của writer có thể tạo và kết thúc transaction cho từng lần thử. Nếu lần thử thất bại do deadlock, exception thoát khỏi writer sau rollback; retry interceptor gọi lại method và tạo transaction mới.

Nếu cả hai method nằm trong cùng một bean và method retry gọi trực tiếp method transaction, self-invocation có thể bỏ qua proxy. Tách bean như ví dụ giúp ranh giới dễ nhìn thấy. Khi dùng Spring Retry, cần bật retry annotation support và kiểm tra thứ tự advisor/interceptor theo phiên bản ứng dụng.

Không bật đồng thời nhiều tầng retry mà không tính tổng số lần thử. Nếu service retry bốn lần và container cũng retry bốn lần, một record có thể tạo tới mười sáu lần gọi database, chưa tính retry ở tầng driver hoặc downstream. Chọn một nơi sở hữu chính sách retry chính, hoặc đặt ngân sách tổng thể rõ ràng.

## 22. Lựa chọn giữa retry ở container và retry ở service

| Tiêu chí | Container error handler | Service retry |
|---|---|---|
| Phạm vi | Toàn bộ listener invocation | Một thao tác nghiệp vụ hoặc lời gọi service |
| Transaction boundary | Exception phải thoát khỏi transaction listener để container xử lý | Retry bao quanh transaction method được gọi qua proxy |
| Có thể dùng khi | Muốn retry record và điều khiển offset/recovery ở Kafka listener | Muốn tái sử dụng retry cho nhiều caller ngoài Kafka |
| Recovery | Có thể kết hợp DLT/recoverer và offset handling | Service cần truyền lỗi cuối cùng cho caller/container |
| Rủi ro | Cấu hình sai có thể retry lỗi không phù hợp | Retry nằm trong transaction hoặc chồng nhiều tầng retry |

Nếu retry ở service, khi hết số lần thử nên để exception thoát ra listener để container áp dụng recovery cuối cùng. Nếu service tự nuốt lỗi rồi trả về bình thường, container có thể commit offset như một xử lý thành công.

## 23. Xác định ngân sách retry

Một record có thể đi qua nhiều lớp: Kafka client, listener container, service retry và database driver. Mỗi lớp đều có thể có timeout hoặc retry riêng. Tổng thời gian xử lý cần nằm trong giới hạn poll và vận hành của consumer.

Khi thiết kế, tính:

- Số lần thử tối đa ở mỗi lớp.
- Backoff ban đầu và mức tăng.
- Backoff tối đa.
- Thời gian tối đa của một transaction database.
- Thời gian tối đa một listener invocation có thể chạy.
- **max.poll.interval.ms** và ảnh hưởng nếu xử lý batch kéo dài.
- Thời gian event được phép nằm trong backlog trước khi cần alert.
- Chính sách DLT/replay sau khi hết retry.

Exponential backoff giúp giảm khả năng nhiều consumer va chạm liên tục, nhưng không bảo đảm deadlock sẽ biến mất. Nếu deadlock xuất phát từ thứ tự lock cố định, retry có thể liên tục chọn lại cùng một chu trình.

Một số hệ thống cần thêm jitter để các consumer không cùng retry vào một thời điểm. Nếu BackOff được dùng chung, kiểm tra khả năng cấu hình randomization theo phiên bản Spring và cách handler được khởi tạo. Không tự thêm sleep vào listener trong lúc transaction còn mở.

## 24. Xử lý dữ liệu và side effect khi một phần đã hoàn tất

Deadlock làm database rollback transaction victim. Nếu tất cả thay đổi liên quan nằm trong cùng transaction, database khôi phục chúng theo tính nguyên tử của transaction. Tuy nhiên, side effect ngoài database có thể đã xảy ra trước khi deadlock được phát hiện.

Ví dụ listener gọi API thanh toán, sau đó cập nhật database và bị deadlock. Database rollback không thể hoàn tác lời gọi API đã thành công. Khi record được retry, API có thể bị gọi lần nữa.

Để tránh vấn đề này:

- Không gọi side effect ngoài transaction trước khi biết database transaction sẽ commit nếu không có idempotency.
- Dùng idempotency key khi gọi API bên ngoài.
- Dùng outbox để phát event sau khi database transaction commit.
- Ghi nhận trạng thái workflow nếu nghiệp vụ gồm nhiều bước không thể rollback cùng nhau.
- Thiết kế thao tác bù trừ khi không thể có transaction nguyên tử xuyên hệ thống.

Đảm bảo idempotency phải bao trùm toàn bộ nghiệp vụ có thể được thực hiện lại, không chỉ lệnh SQL cuối cùng.

## 25. Khi nào cần thay đổi mô hình dữ liệu?

Nếu deadlock xảy ra thường xuyên dù đã chuẩn hóa thứ tự lock và rút ngắn transaction, có thể mô hình dữ liệu hoặc cách phân chia workload tạo contention quá lớn.

Cân nhắc:

- Chia một hàng nóng thành các bucket hoặc shard nghiệp vụ nếu invariants cho phép.
- Dùng atomic update thay vì đọc rồi ghi nhiều bước khi có thể.
- Dùng optimistic locking/version column khi xung đột thấp và có thể xử lý conflict.
- Chuyển cập nhật tuần tự theo aggregate key vào một consumer group chuyên trách.
- Dùng queue/partition key phù hợp để phân luồng cùng aggregate.
- Thiết kế batch nhỏ hơn hoặc xử lý theo chunk.
- Giảm số service cùng sở hữu quyền cập nhật một tập dữ liệu.

Không thay đổi schema chỉ để loại bỏ một deadlock đơn lẻ. Hãy dùng deadlock report và metric để chứng minh hotspot, sau đó đánh giá trade-off về throughput, tính nhất quán và khả năng mở rộng.
