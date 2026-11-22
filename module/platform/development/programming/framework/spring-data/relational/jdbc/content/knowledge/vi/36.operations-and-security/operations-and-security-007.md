# Retry lỗi tạm thời với thao tác an toàn và ranh giới giao dịch rõ ràng

Trong một ứng dụng Spring Data JDBC, thao tác ghi dữ liệu có thể thất bại vì những nguyên nhân chỉ tồn tại trong thời gian ngắn: database đang bận, transaction bị deadlock, lock chưa lấy được, kết nối tạm thời gián đoạn hoặc một resource chưa sẵn sàng. Nếu nguyên nhân có khả năng tự hết, ứng dụng có thể thử lại thao tác sau một khoảng chờ ngắn.

Retry không có nghĩa là chạy lại mọi lỗi. Một lỗi validation, câu SQL sai, vi phạm unique constraint hoặc một quy tắc nghiệp vụ bị từ chối sẽ không tự biến mất khi chạy lại. Thử lại vô điều kiện chỉ làm tăng tải và có thể lặp side effect.

Một cơ chế retry an toàn cần ba yếu tố:

1. Chỉ retry những lỗi thực sự có tính tạm thời.
2. Thao tác phải có thể chạy lại mà không tạo kết quả trùng hoặc sai.
3. Mỗi lần thử lại phải có ranh giới transaction rõ ràng để lần thất bại được rollback trước khi bắt đầu lần tiếp theo.

Bài học này trình bày cách phân loại lỗi, thiết kế thao tác idempotent, cấu hình retry trong Spring Framework 7, lựa chọn Spring Retry cho các phiên bản cũ hơn, kết hợp retry với transaction, xử lý kết quả commit không chắc chắn và kiểm thử hành vi retry.

## 1. Retry giải quyết loại lỗi nào?

Retry phù hợp với lỗi có khả năng biến mất nếu chờ rồi thực hiện lại. Trong ứng dụng Spring Data JDBC, các tình huống thường gặp gồm:

- Database tạm thời không nhận kết nối.
- Connection pool chưa có connection khả dụng trong một khoảng ngắn.
- Transaction bị database rollback do deadlock.
- Không lấy được lock vì một transaction khác đang giữ lock.
- Database từ chối transaction do xung đột đồng thời có thể giải quyết bằng cách đọc lại dữ liệu và thực hiện lại nghiệp vụ.
- Một dịch vụ bên ngoài tạm thời không phản hồi hoặc trả lỗi quá tải.

Spring JDBC dịch lỗi JDBC thành hệ exception trong package `org.springframework.dao`. Một số exception thuộc nhóm `TransientDataAccessException`, biểu thị lỗi truy cập dữ liệu có thể thử lại sau khi điều kiện thay đổi.

Ví dụ những nhóm lỗi có thể gặp:

| Tình huống | Exception thường gặp | Cách cân nhắc |
|---|---|---|
| Không lấy được lock | `CannotAcquireLockException` | Có thể retry toàn bộ transaction |
| Deadlock | `PessimisticLockingFailureException` hoặc subclass tương ứng | Có thể retry sau rollback |
| Resource database tạm thời không sẵn sàng | `TransientDataAccessResourceException` | Có thể retry có giới hạn |
| Timeout khi truy cập dữ liệu | `QueryTimeoutException` | Chỉ retry nếu timeout là tạm thời và còn đủ thời gian |
| Optimistic lock conflict | `OptimisticLockingFailureException` | Phải đọc lại và tính lại nghiệp vụ trước khi thử tiếp |
| Vi phạm unique/FK/CHECK | `DataIntegrityViolationException` | Thường không retry |
| SQL sai cú pháp | `BadSqlGrammarException` | Không retry |
| Không đủ quyền | Lỗi quyền truy cập database | Không retry |

Phân loại chính xác còn phụ thuộc JDBC driver, database và exception translator. Hãy dựa vào loại exception được Spring dịch và nguyên nhân gốc, không chỉ dựa vào thông báo lỗi dạng text.

### 1.1. Lỗi tạm thời và lỗi cố định

So sánh hai trường hợp:

- Database từ chối một transaction vì deadlock: một transaction khác vừa giữ các lock xung đột. Sau khi rollback và chờ, lần thử tiếp theo có thể thành công.
- Database từ chối insert vì mã đơn hàng đã tồn tại: nếu không thay dữ liệu đầu vào hoặc quy tắc nghiệp vụ, chạy lại vẫn vi phạm unique constraint.

Retry chỉ có ích với trường hợp đầu tiên.

Một nguyên tắc thực tế là: **nếu chạy lại cùng thao tác với cùng trạng thái và cùng đầu vào thì lỗi có khả năng biến mất không?** Nếu câu trả lời là không, đừng retry một cách tự động.

### 1.2. Không retry mọi DataAccessException

`DataAccessException` là lớp exception gốc rộng của Spring DAO. Nó bao gồm cả lỗi tạm thời và lỗi không thể tự hết.

Ví dụ:

- `TransientDataAccessException` biểu thị nhóm lỗi tạm thời.
- `DataIntegrityViolationException` biểu thị dữ liệu vi phạm constraint.
- `BadSqlGrammarException` biểu thị SQL không hợp lệ.
- `PermissionDeniedDataAccessException` biểu thị thiếu quyền.

Không cấu hình retry cho toàn bộ `DataAccessException` nếu chưa có chính sách phân loại. Với Spring Framework 7, `@Retryable` mặc định thử lại mọi exception; vì vậy phải chỉ định rõ nhóm exception được phép retry.

## 2. Trước khi retry, hãy xác định thao tác có an toàn không

Một thao tác idempotent là thao tác có thể được thực hiện nhiều lần với cùng một định danh/yêu cầu mà kết quả cuối cùng tương đương với việc thực hiện một lần.

Ví dụ đặt trạng thái đơn hàng thành PAID:

```sql
UPDATE purchase_orders
SET status = 'PAID'
WHERE id = :orderId;
```

Nếu chạy lại cùng câu lệnh, trạng thái vẫn là PAID. Đây thường là thao tác dễ làm idempotent hơn.

Ngược lại, câu lệnh:

```sql
UPDATE customer_wallets
SET balance = balance - :amount
WHERE customer_id = :customerId;
```

mỗi lần chạy đều trừ tiền thêm một lần. Nếu lần đầu đã commit nhưng ứng dụng mất kết nối trước khi nhận kết quả, retry có thể trừ tiền lần thứ hai.

### 2.1. So sánh các thao tác

| Thao tác | Có thể retry an toàn? | Lý do |
|---|---|---|
| Đặt trạng thái về một giá trị xác định | Thường có | Lặp lại vẫn cho cùng trạng thái |
| Tạo một bản ghi có idempotency key unique | Có thể | Database có thể nhận diện yêu cầu đã xử lý |
| Tăng counter thêm 1 | Không tự động | Mỗi lần thử làm tăng thêm |
| Trừ số dư tài khoản | Không tự động | Có thể áp dụng nhiều lần |
| Thêm một dòng audit mới | Không tự động | Có thể tạo dòng trùng |
| Gửi email | Không tự động | Người nhận có thể nhận nhiều email |
| Gọi API thanh toán | Không tự động | Nhà cung cấp có thể đã xử lý lần gọi trước |
| Đọc dữ liệu | Thường an toàn | Không tạo side effect, nhưng kết quả có thể thay đổi theo thời gian |

Không nên kết luận một thao tác an toàn chỉ vì nó dùng HTTP GET, SQL UPDATE hoặc repository save. Hãy xem xét side effect thực tế và tình huống kết quả của lần gọi trước không được trả về cho caller.

## 3. Idempotency key bảo vệ thao tác ghi

Với nghiệp vụ có khả năng bị gọi lại, hãy tạo một định danh duy nhất cho yêu cầu nghiệp vụ. Ví dụ, mỗi yêu cầu tạo đơn có một `requestId` hoặc `idempotencyKey`.

Schema:

```sql
CREATE TABLE processed_commands (
    command_id VARCHAR(80) PRIMARY KEY,
    result_reference BIGINT NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
```

Khi xử lý command:

1. Kiểm tra command ID đã được ghi nhận chưa.
2. Nếu đã có, trả về kết quả đã lưu.
3. Nếu chưa có, thực hiện thay đổi nghiệp vụ.
4. Ghi command ID và kết quả trong cùng transaction.
5. Commit cả dữ liệu nghiệp vụ lẫn dấu vết idempotency.

Ví dụ khung service:

```java
@Transactional
public Long createOrder(CreateOrderCommand command) {
    return processedCommandRepository
        .findResultReference(command.commandId())
        .orElseGet(() -> {
            PurchaseOrder order = orderRepository.save(
                PurchaseOrder.from(command)
            );

            processedCommandRepository.save(
                new ProcessedCommand(
                    command.commandId(),
                    order.getId(),
                    Instant.now()
                )
            );

            return order.getId();
        });
}
```

Ví dụ giả định bảng processed_commands có primary key/unique constraint trên command_id. Trong triển khai đồng thời, chỉ kiểm tra trước bằng SELECT là chưa đủ: hai request có thể cùng thấy command chưa tồn tại. Unique constraint vẫn cần thiết, và ứng dụng phải xử lý tình huống tranh chấp khi ghi command ID.

Nếu việc tạo order và ghi idempotency record nằm trong cùng transaction, rollback sẽ hoàn tác cả hai. Nếu transaction đã commit nhưng response bị mất, lần gọi lại có thể tìm command ID và trả về kết quả cũ.

### 3.1. Idempotency key phải ổn định qua các lần retry

Không tạo UUID mới ở mỗi lần retry. Key phải đại diện cho cùng một yêu cầu nghiệp vụ và được giữ nguyên qua tất cả lần thử.

Ví dụ:

```java
public record CreateOrderCommand(
    String commandId,
    Long customerId,
    List<OrderLineRequest> lines
) {}
```

Nếu mỗi lần thử tạo command ID mới, database không thể nhận ra đây là cùng một yêu cầu và có thể tạo nhiều đơn hàng.

### 3.2. Unique constraint là lớp bảo vệ cuối cùng

Một đoạn code kiểm tra tồn tại trước khi insert không bảo đảm an toàn khi có nhiều request đồng thời:

```java
if (!repository.existsByCommandId(commandId)) {
    repository.save(command);
}
```

Hai thread có thể cùng vượt qua kiểm tra. Database cần unique constraint trên command ID để bảo vệ tính duy nhất. Service có thể xử lý duplicate-key conflict bằng cách tải lại kết quả đã được request cạnh tranh ghi thành công.

## 4. Retry toàn bộ transaction, không retry một câu lệnh trong transaction đã hỏng

Khi một câu SQL thất bại do deadlock hoặc serialization conflict, database có thể đã rollback transaction hoặc đánh dấu transaction không thể tiếp tục.

Nếu ứng dụng bắt exception rồi chạy tiếp trong cùng transaction, câu lệnh tiếp theo có thể tiếp tục thất bại. Đặc biệt, một số database đánh dấu transaction ở trạng thái lỗi sau một câu SQL không thành công.

Luồng phù hợp:

```text
Lần thử 1
  Bắt đầu transaction A
  Đọc aggregate
  Thực hiện thay đổi
  Database báo deadlock
  Rollback transaction A

Chờ theo backoff

Lần thử 2
  Bắt đầu transaction B
  Đọc lại aggregate
  Thực hiện lại nghiệp vụ
  Commit transaction B
```

Mỗi lần thử phải bắt đầu từ một transaction sạch. Nếu lần đầu đã đọc dữ liệu rồi thất bại, lần sau nên đọc lại dữ liệu và thực hiện lại quy tắc nghiệp vụ trên trạng thái mới.

### 4.1. Không chỉ retry repository.save()

Giả sử nghiệp vụ cần:

1. Đọc tồn kho.
2. Kiểm tra đủ số lượng.
3. Giảm tồn kho.
4. Tạo reservation.
5. Ghi audit.

Nếu chỉ retry bước save cuối cùng, các bước đọc và tính toán trước đó có thể đã dựa trên dữ liệu cũ. Hãy retry toàn bộ use case transaction có liên quan để lần thử mới đọc lại trạng thái database.

### 4.2. Transaction phải rollback trước khi retry

Một exception cần thoát khỏi phương thức transactional để transaction interceptor có thể áp dụng rollback. Nếu code bắt exception rồi trả về bình thường, transaction có thể commit hoặc không được đánh dấu rollback theo ý định.

Ví dụ không nên:

```java
@Transactional
public void reserveStock(Long productId, int quantity) {
    try {
        repository.reserve(productId, quantity);
    } catch (TransientDataAccessException exception) {
        log.warn("Temporary failure", exception);
        // Trả về bình thường có thể khiến transaction không rollback.
    }
}
```

Hãy để exception được truyền ra ngoài transaction boundary hoặc đánh dấu rollback-only theo chính sách phù hợp. Retry interceptor cần nhận được exception để quyết định có thử lại hay không.

### 4.3. Checked exception và rollback

Mặc định Spring rollback với `RuntimeException` và `Error`. Checked exception không làm rollback theo mặc định.

Nếu thao tác có thể ném checked exception và exception đó là điều kiện retry, hãy cấu hình `rollbackFor` phù hợp:

```java
@Transactional(rollbackFor = IOException.class)
public void importOrder() throws IOException {
    // Các thao tác persistence.
}
```

Đối với exception truy cập dữ liệu do Spring dịch, đa số là unchecked exception. Tuy nhiên, hãy kiểm tra chính sách rollback của các exception thực tế trong ứng dụng.

## 5. Retry trong Spring Framework 7

Từ **Spring Framework 7.0**, framework lõi có các resilience feature gồm `@Retryable`, `@ConcurrencyLimit` và `RetryTemplate`.

Với ứng dụng dùng Spring Framework 7, có thể bật xử lý annotation bằng `@EnableResilientMethods`:

```java
@Configuration
@EnableResilientMethods
public class ResilienceConfiguration {
}
```

Import:

```java
import org.springframework.resilience.annotation.EnableResilientMethods;
import org.springframework.resilience.annotation.Retryable;
```

### 5.1. Chỉ định exception được retry

Ví dụ service cập nhật trạng thái đơn hàng:

```java
@Service
public class OrderCommandService {

    private final PurchaseOrderRepository repository;

    public OrderCommandService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Retryable(
        includes = TransientDataAccessException.class,
        excludes = OptimisticLockingFailureException.class,
        maxRetries = 3,
        delay = 100,
        multiplier = 2,
        jitter = 25,
        maxDelay = 1000
    )
    @Transactional
    public void markPaid(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow();

        order.markPaid();
        repository.save(order);
    }
}
```

Trong ví dụ:

- `includes` giới hạn retry cho exception thuộc nhóm transient.
- `excludes` loại optimistic locking failure khỏi retry tự động.
- `maxRetries = 3` cho phép tối đa ba lần thử lại sau lần chạy đầu tiên, tức tối đa bốn lần gọi.
- `delay = 100` đặt thời gian chờ ban đầu là 100 ms.
- `multiplier = 2` tăng khoảng chờ theo cấp số nhân.
- `jitter = 25` thêm độ ngẫu nhiên vào khoảng chờ.
- `maxDelay = 1000` giới hạn thời gian chờ ở 1.000 ms.

Ví dụ này giả định nghiệp vụ thanh toán có thể được thực hiện lại an toàn và không gọi dịch vụ thanh toán bên ngoài bên trong transaction. Nếu có side effect bên ngoài, cần idempotency key hoặc outbox như các phần sau.

### 5.2. Đừng giữ cấu hình mặc định cho production

`@Retryable` của Spring Framework 7 mặc định có thể retry mọi exception. Cấu hình mặc định cũng cho phép ba lần retry sau lần gọi ban đầu và delay một giây.

Việc retry mọi exception là quá rộng cho nhiều nghiệp vụ database. Một lỗi unique constraint, validation hoặc SQL sai không được giải quyết bằng cách chạy lại cùng request.

Hãy chỉ định `includes` và `excludes` để biểu diễn chính sách retry của use case.

### 5.3. Hiểu rõ maxRetries

Trong Spring Framework 7:

```text
Tổng số lần gọi = 1 lần đầu + maxRetries
```

Ví dụ:

| maxRetries | Tổng số lần gọi tối đa |
|---:|---:|
| 0 | 1 |
| 1 | 2 |
| 2 | 3 |
| 3 | 4 |
| 4 | 5 |

Đừng nhầm `maxRetries` với `maxAttempts` của Spring Retry. Hai framework dùng tên và cách tính khác nhau.

### 5.4. Retry và transaction advice

Spring Framework 7 quy định thứ tự advice mặc định:

```text
Retry (OUTER)
    |
Transaction (INNER)
    |
Method
```

Khi phương thức có cả `@Retryable` và `@Transactional`:

1. Retry interceptor gọi transaction interceptor.
2. Transaction interceptor mở transaction cho lần thử.
3. Method thực hiện nghiệp vụ.
4. Nếu method ném exception, transaction rollback.
5. Retry interceptor nhận exception sau rollback và quyết định có thử lại không.
6. Lần thử tiếp theo đi qua transaction interceptor và mở transaction mới.

Đây là thứ tự mong muốn cho lỗi tạm thời như deadlock.

Tuy nhiên, nếu caller đã mở một transaction bên ngoài, transaction với propagation `REQUIRED` có thể tham gia transaction đó. Trong use case cần transaction mới cho từng lần thử, hãy đặt retry boundary ở nơi không có transaction bao quanh hoặc tách retry coordinator khỏi transactional worker.

### 5.5. Proxy và self-invocation

`@Retryable` và `@Transactional` dựa trên Spring proxy trong cấu hình thông thường. Chỉ các lời gọi đi qua proxy mới được interceptor xử lý.

Ví dụ self-invocation:

```java
public void process() {
    retryableOperation(); // Gọi nội bộ trong cùng object.
}

@Retryable
@Transactional
public void retryableOperation() {
    // ...
}
```

Lời gọi nội bộ có thể bỏ qua proxy, nên annotation không được áp dụng như mong đợi.

Hãy gọi method từ một Spring bean khác hoặc tách phần retry/transaction thành các bean có trách nhiệm rõ ràng.

## 6. Tách retry coordinator và transactional worker

Với use case quan trọng, tách hai trách nhiệm thành hai bean giúp ranh giới transaction dễ quan sát hơn.

Retry coordinator:

```java
@Service
public class OrderRetryFacade {

    private final OrderTransactionalWorker worker;

    public OrderRetryFacade(OrderTransactionalWorker worker) {
        this.worker = worker;
    }

    @Retryable(
        includes = TransientDataAccessException.class,
        excludes = OptimisticLockingFailureException.class,
        maxRetries = 3,
        delay = 100,
        multiplier = 2,
        jitter = 25,
        maxDelay = 1000
    )
    public ReservationResult reserve(ReserveCommand command) {
        return worker.reserve(command);
    }
}
```

Transactional worker:

```java
@Service
public class OrderTransactionalWorker {

    private final InventoryRepository inventoryRepository;
    private final ReservationRepository reservationRepository;

    public OrderTransactionalWorker(
            InventoryRepository inventoryRepository,
            ReservationRepository reservationRepository) {
        this.inventoryRepository = inventoryRepository;
        this.reservationRepository = reservationRepository;
    }

    @Transactional
    public ReservationResult reserve(ReserveCommand command) {
        Inventory inventory = inventoryRepository
            .findByProductId(command.productId())
            .orElseThrow();

        inventory.reserve(command.quantity());

        inventoryRepository.save(inventory);

        Reservation reservation =
            Reservation.from(command);

        reservationRepository.save(reservation);

        return ReservationResult.from(reservation);
    }
}
```

Coordinator gọi worker qua bean khác, nên lời gọi worker đi qua proxy transaction. Nếu không có transaction bên ngoài, mỗi lần coordinator thử lại sẽ gọi worker và mở transaction mới.

Nếu coordinator có thể được gọi từ một transaction bên ngoài, cần quyết định rõ có nên tạm ngưng transaction đó trong lúc retry hay không. Có thể dùng một ranh giới orchestration với propagation `NOT_SUPPORTED` để tránh worker tham gia transaction của caller, nhưng phải cân nhắc vì transaction ngoài sẽ bị tạm ngưng trong toàn bộ khoảng retry.

Không nên thêm `REQUIRES_NEW` một cách máy móc. Nó làm transaction worker commit độc lập với transaction bên ngoài và có thể khiến một phần nghiệp vụ tồn tại dù transaction caller rollback.

## 7. RetryTemplate khi cần điều khiển bằng code

Spring Framework 7 cung cấp `org.springframework.core.retry.RetryTemplate` cho trường hợp cần xây dựng chính sách retry bằng Java.

Ví dụ cấu hình:

```java
@Bean
RetryTemplate orderRetryTemplate() {
    RetryPolicy policy = RetryPolicy.builder()
        .includes(TransientDataAccessException.class)
        .excludes(OptimisticLockingFailureException.class)
        .maxRetries(3)
        .delay(Duration.ofMillis(100))
        .jitter(Duration.ofMillis(25))
        .multiplier(2)
        .maxDelay(Duration.ofSeconds(1))
        .build();

    return new RetryTemplate(policy);
}
```

Dùng template bên ngoài transactional worker:

```java
@Service
public class OrderRetryCoordinator {

    private final RetryTemplate retryTemplate;
    private final OrderTransactionalWorker worker;

    public OrderRetryCoordinator(
            RetryTemplate retryTemplate,
            OrderTransactionalWorker worker) {
        this.retryTemplate = retryTemplate;
        this.worker = worker;
    }

    public ReservationResult reserve(ReserveCommand command) {
        return retryTemplate.invoke(
            () -> worker.reserve(command)
        );
    }
}
```

Trong ví dụ, coordinator không mở transaction. Mỗi lần `invoke` gọi worker, worker đi qua transaction proxy và thực hiện một transaction riêng.

`RetryTemplate` phù hợp khi:

- Retry policy thay đổi theo use case.
- Cần đặt retry quanh một đoạn code thay vì một method annotation.
- Cần kết hợp retry với xử lý kết quả hoặc logging riêng.
- Muốn kiểm thử policy độc lập với method proxy.

Đừng đặt transaction bao quanh `retryTemplate.invoke` nếu mục tiêu là mỗi lần gọi worker có một transaction riêng. Nếu đã có transaction ngoài, worker propagation REQUIRED có thể tham gia transaction đó.

## 8. Spring Retry cho dự án chưa dùng Spring Framework 7

Với dự án dùng Spring Framework 6.x hoặc release train cũ hơn, có thể dùng thư viện Spring Retry nếu phiên bản dependency tương thích với stack đang chạy.

Spring Retry có package annotation riêng:

```java
import org.springframework.retry.annotation.EnableRetry;
import org.springframework.retry.annotation.Retryable;
import org.springframework.retry.annotation.Backoff;
```

Bật annotation processing:

```java
@Configuration
@EnableRetry
public class RetryConfiguration {
}
```

Ví dụ:

```java
@Service
public class LegacyOrderService {

    @Retryable(
        retryFor = TransientDataAccessException.class,
        noRetryFor = OptimisticLockingFailureException.class,
        maxAttempts = 4,
        backoff = @Backoff(
            delay = 100,
            multiplier = 2,
            maxDelay = 1000
        )
    )
    @Transactional
    public void markPaid(Long orderId) {
        // Đọc lại aggregate, kiểm tra quy tắc và lưu.
    }
}
```

Trong Spring Retry:

- `maxAttempts = 4` bao gồm lần gọi đầu tiên, tức tối đa bốn lần gọi tổng cộng.
- `retryFor` chỉ định exception được retry.
- `noRetryFor` loại exception khỏi retry.
- `@Backoff` cấu hình thời gian chờ.

Đừng nhầm import `org.springframework.retry.annotation.Retryable` với `org.springframework.resilience.annotation.Retryable` của Spring Framework 7. Cùng tên annotation nhưng API và cách đếm số lần thử khác nhau.

Khi dùng Spring Retry với transaction, hãy kiểm tra thứ tự advice của phiên bản và cấu hình thực tế. Nếu muốn tránh phụ thuộc vào thứ tự annotation, có thể dùng retry template bên ngoài và gọi một transactional bean qua proxy.

## 9. Optimistic locking cần xử lý khác retry deadlock

Spring Data JDBC hỗ trợ optimistic locking qua property `@Version`. Nếu hai transaction cùng đọc một aggregate version 5, transaction đầu có thể cập nhật thành version 6. Transaction thứ hai lưu với version 5 sẽ bị từ chối.

Lỗi này thường được biểu diễn bằng `OptimisticLockingFailureException`.

Không nên lấy cùng object stale rồi save lại nhiều lần. Version vẫn cũ nên lần sau có thể thất bại tiếp.

Cách xử lý hợp lý:

1. Bắt conflict ở tầng use case nếu nghiệp vụ cho phép xử lý lại.
2. Đọc lại aggregate mới nhất.
3. Đánh giá lại điều kiện nghiệp vụ trên trạng thái mới.
4. Tính lại thay đổi.
5. Thử lưu với version mới, trong một transaction mới.

Ví dụ minh họa:

```java
@Transactional
public void reserve(Long productId, int quantity) {
    Inventory inventory = inventoryRepository
        .findByProductId(productId)
        .orElseThrow();

    if (inventory.availableQuantity() < quantity) {
        throw new InsufficientInventoryException(productId);
    }

    inventory.reserve(quantity);
    inventoryRepository.save(inventory);
}
```

Nếu lần lưu bị optimistic locking conflict, lần retry phải gọi lại toàn bộ method để tải inventory mới và kiểm tra số lượng còn lại. Không truyền lại object cũ đã có version lỗi.

Có thể retry một use case có optimistic conflict nếu việc đọc lại và đánh giá lại nghiệp vụ là đúng. Nhưng không nên xem mọi optimistic locking failure là lỗi tạm thời có thể xử lý bằng cách lặp lại cùng câu lệnh.

## 10. Side effect bên ngoài và Transactional Outbox

Một transaction JDBC không thể tự rollback email, HTTP request, message broker hoặc giao dịch thanh toán đã hoàn tất ở hệ thống khác.

Ví dụ không an toàn:

```java
@Transactional
@Retryable
public void payOrder(Long orderId) {
    paymentGateway.charge(orderId);
    orderRepository.markPaid(orderId);
}
```

Nếu payment gateway đã thu tiền nhưng thao tác database sau đó deadlock, transaction database rollback. Retry có thể gọi payment gateway lần nữa và thu tiền lần thứ hai.

### 10.1. Dùng idempotency key với nhà cung cấp bên ngoài

Nếu payment provider hỗ trợ idempotency key, dùng cùng một key cho mọi lần gửi cùng một yêu cầu thanh toán:

```java
paymentGateway.charge(
    command.paymentRequestId(),
    command.amount()
);
```

Provider cần bảo đảm cùng key không tạo thêm giao dịch mới. Ứng dụng vẫn phải lưu và đối chiếu kết quả để xử lý trường hợp response bị mất.

### 10.2. Dùng transactional outbox

Với sự kiện cần gửi sau khi dữ liệu nghiệp vụ commit:

1. Trong transaction, cập nhật aggregate.
2. Trong cùng transaction, ghi một outbox event.
3. Commit cả aggregate và outbox row.
4. Worker đọc outbox và gửi message.
5. Nếu gửi thất bại tạm thời, worker retry việc publish.
6. Consumer xử lý idempotent vì message có thể được gửi lại.

Ví dụ:

```sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
```

Outbox giúp thay đổi database và ý định gửi event được ghi nguyên tử trong cùng transaction. Nó không tự bảo đảm broker nhận message đúng một lần; worker có thể gửi lại sau khi crash, nên consumer cần idempotency.

### 10.3. Không giữ transaction mở trong lúc chờ dịch vụ ngoài

Gọi HTTP, email hoặc payment provider bên trong một transaction database dài có thể giữ connection và lock trong suốt thời gian chờ mạng.

Nên giới hạn transaction cho thao tác database cần atomicity, sau đó xử lý side effect ngoài qua outbox hoặc một quy trình có idempotency phù hợp.

## 11. Backoff, jitter và giới hạn retry

Retry liên tục không có thời gian chờ có thể làm database hoặc dịch vụ đang quá tải càng khó phục hồi.

Ba cơ chế thường dùng:

- **Backoff:** tăng thời gian chờ giữa các lần thử.
- **Jitter:** thêm độ ngẫu nhiên để các client không cùng retry vào một thời điểm.
- **Maximum delay:** giới hạn thời gian chờ lớn nhất.

Ví dụ exponential backoff:

```text
Lần thử lại 1: khoảng 100 ms
Lần thử lại 2: khoảng 200 ms
Lần thử lại 3: khoảng 400 ms
Lần thử lại 4: khoảng 800 ms
```

Nếu có jitter, thời gian thực tế dao động quanh các mốc trên trong giới hạn cấu hình.

### 11.1. Chọn giới hạn theo deadline nghiệp vụ

Không chọn số lần retry chỉ vì một ví dụ có bốn lần. Hãy xem xét:

- Request timeout của API.
- Deadline của job hoặc message consumer.
- Thời gian transaction và lock.
- Thời gian chờ connection pool.
- Mức độ quá tải database.
- Khả năng người dùng chờ kết quả.

Nếu một request chỉ có deadline hai giây, chính sách retry với tổng thời gian chờ năm giây sẽ không phù hợp.

### 11.2. Tránh retry amplification

Nếu API gateway, service A, service B và database client đều tự retry ba lần, một request ban đầu có thể tạo ra rất nhiều lần gọi ở tầng dưới.

Hãy chọn một tầng chịu trách nhiệm retry cho từng loại lỗi. Các tầng khác cần tôn trọng deadline và truyền lỗi có ý nghĩa thay vì nhân số lần thử.

### 11.3. Không retry khi request đã bị hủy

Nếu caller đã hủy request hoặc deadline đã hết, tiếp tục retry có thể tiêu tốn connection và tài nguyên mà không còn tạo giá trị. Cần tích hợp retry policy với timeout/cancellation của hệ thống.

## 12. Theo dõi và ghi log retry

Một hệ thống retry tốt phải cho biết:

- Use case nào đang retry.
- Exception nào kích hoạt retry.
- Lần thử hiện tại và số lần tối đa.
- Thời gian chờ giữa các lần thử.
- Retry cuối cùng thành công hay thất bại.
- Tổng thời gian bị tiêu tốn do retry.

Không nên log toàn bộ payload, thông tin thanh toán hoặc dữ liệu cá nhân trong mỗi lần retry. Hãy dùng command ID hoặc correlation ID để liên kết các lần thử.

Spring Framework 7 phát hành `MethodRetryEvent` cho mỗi exception từ method đang được retry. Có thể dùng event listener để thu thập metric và log có cấu trúc.

Với `RetryTemplate`, có thể đăng ký `RetryListener` để quan sát các giai đoạn trước/sau lần thử và kết quả exhaustion.

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| Retry attempts theo exception type | Xác định lỗi tạm thời phổ biến |
| Retry success rate | Đo mức độ retry thực sự giúp phục hồi |
| Retry exhausted count | Phát hiện sự cố không tự phục hồi |
| Backoff duration | Theo dõi chi phí thời gian |
| Transaction rollback count | Theo dõi tác động lên database |
| Idempotency duplicate count | Phát hiện request được gửi lại |

Nếu retry rate tăng mạnh, cần xử lý nguyên nhân gốc như connection pool, lock contention, database capacity hoặc query chậm. Retry không thay thế việc khắc phục sự cố hạ tầng.

## 13. Kiểm thử retry và transaction boundary

Không chỉ kiểm tra method được gọi nhiều lần. Cần chứng minh lần thất bại rollback và lần tiếp theo bắt đầu trong transaction mới.

### 13.1. Unit test chính sách retry

Có thể kiểm tra logic phân loại exception hoặc cấu hình policy riêng bằng unit test. Test nên xác nhận:

- Exception transient được phép retry.
- Exception validation không được retry.
- Optimistic lock không bị lặp lại với object stale.
- Số lần gọi tối đa đúng.
- Backoff được giới hạn.

### 13.2. Integration test transaction retry

Một kịch bản tích hợp có thể mô phỏng lần đầu thất bại do lỗi transient và lần sau thành công:

1. Transaction đầu ghi một thay đổi tạm thời rồi ném exception.
2. Transaction đầu rollback.
3. Retry gọi lại service.
4. Transaction mới đọc dữ liệu đã rollback.
5. Lần thứ hai lưu thành công.
6. Database chỉ có một kết quả nghiệp vụ cuối cùng.

Ví dụ kiểm thử ở mức khái niệm:

```java
@SpringBootTest
class RetryTransactionIntegrationTest {

    @Autowired
    OrderRetryFacade retryFacade;

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void retriesAfterTheFailedTransactionRollsBack() {
        retryFacade.processWithOneTransientFailure(42L);

        PurchaseOrder order = repository.findById(42L)
            .orElseThrow();

        assertThat(order.getStatus()).isEqualTo(OrderStatus.PAID);
    }
}
```

Để test thực sự có ý nghĩa, dependency được gọi trong lần đầu cần tạo ra một lỗi transient có kiểm soát. Sau đó xác nhận side effect của lần đầu không còn tồn tại và chỉ kết quả của lần thành công được commit.

### 13.3. Không bọc test trong transaction ngoài khi cần kiểm tra commit thật

Một test có `@Transactional` ở cấp test có thể làm thay đổi cách quan sát transaction service. Nếu cần xác nhận transaction do service tự mở đã commit hoặc rollback, hãy chạy test không có transaction ngoài, hoặc dùng propagation phù hợp.

Ví dụ:

```java
@SpringBootTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class RetryCommitIntegrationTest {
    // Gọi service để mỗi lần thử quản lý transaction của riêng nó.
}
```

### 13.4. Kiểm thử idempotency

Gửi cùng command ID hai lần và xác nhận:

- Chỉ có một order được tạo.
- Chỉ có một idempotency record.
- Hai lần gọi trả về cùng result reference.
- Không có audit/payment side effect bị nhân đôi.

Test nên chạy trên database production-compatible nếu dựa vào unique constraint hoặc transaction isolation.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Retry lặp cả lỗi validation | Retry mọi exception | Chỉ định includes/excludes |
| Deadlock xảy ra nhưng lần retry vẫn lỗi | Retry trong transaction đã rollback-only | Retry toàn bộ transaction trong transaction mới |
| Mỗi lần retry tạo thêm bản ghi | Thao tác không idempotent | Dùng idempotency key và unique constraint |
| Tiền bị trừ nhiều lần | Retry một thao tác cộng/trừ không có bảo vệ | Dùng command ID, transaction ledger hoặc idempotency ở provider |
| Lần thử sau vẫn dùng dữ liệu cũ | Retry lại cùng aggregate stale | Đọc lại và tính lại nghiệp vụ |
| Annotation không có tác dụng | Self-invocation hoặc bean chưa qua proxy | Gọi qua Spring bean proxy |
| Retry không tạo transaction mới | Caller đã mở transaction bên ngoài | Đặt retry boundary ngoài transaction hoặc tách coordinator/worker |
| Database quá tải hơn sau khi bật retry | Không có backoff, jitter hoặc giới hạn | Dùng exponential backoff và max delay |
| Request vượt deadline | Tổng retry time lớn hơn timeout nghiệp vụ | Giới hạn attempts, delay và timeout |
| Message được gửi hai lần | Retry publish sau khi broker đã nhận nhưng ACK bị mất | Idempotent consumer hoặc outbox event ID |
| Retry không xử lý được optimistic lock | Lưu lại cùng object/version cũ | Reload, kiểm tra invariant và tính lại |
| Retry lồng nhiều tầng gây nhiều request | Mỗi tầng tự retry | Chỉ định một tầng sở hữu retry policy |
| Test pass dù transaction không rollback | Test bị bao trong transaction ngoài hoặc chỉ mock repository | Integration test với database và kiểm tra dữ liệu sau rollback |

## 15. Quy trình thiết kế retry cho một use case Spring Data JDBC

Trước khi thêm annotation hoặc RetryTemplate, hãy trả lời lần lượt:

1. Lỗi nào có thể tạm thời và tự hết?
2. Exception nào từ Spring DAO đại diện cho các lỗi đó?
3. Thao tác có idempotent không?
4. Nếu kết quả commit không rõ ràng, làm sao nhận diện request đã được xử lý?
5. Retry có bao trùm toàn bộ nghiệp vụ database cần atomicity không?
6. Mỗi lần thử có một transaction mới không?
7. Có transaction ngoài nào khiến các lần thử tham gia cùng transaction không?
8. Số lần thử, backoff, jitter và deadline có phù hợp không?
9. Side effect bên ngoài có dùng idempotency key hoặc outbox không?
10. Integration test có chứng minh rollback và kết quả cuối cùng không?

Nếu không thể bảo đảm thao tác an toàn khi lặp, hãy bổ sung idempotency hoặc thiết kế lại ranh giới side effect trước khi bật retry tự động.

## 16. Bài thực hành

**Bài 1.** Database trả deadlock khi lưu aggregate. Có nên retry không?

*Đáp án:* Có thể, nếu retry toàn bộ transaction sau rollback và thao tác nghiệp vụ an toàn khi chạy lại.

**Bài 2.** Unique constraint từ chối mã đơn hàng đã tồn tại. Có nên retry cùng dữ liệu không?

*Đáp án:* Không. Đây là lỗi dữ liệu/logic cố định; cần xử lý xung đột hoặc trả lỗi nghiệp vụ.

**Bài 3.** Spring Framework 7 có retry tích hợp từ phiên bản nào?

*Đáp án:* Từ Spring Framework 7.0, qua `@Retryable` và `RetryTemplate` trong core framework.

**Bài 4.** `maxRetries = 3` của Spring Framework 7 có nghĩa tổng cộng ba lần gọi không?

*Đáp án:* Không. Có một lần gọi ban đầu cộng tối đa ba lần retry, tức tối đa bốn lần gọi.

**Bài 5.** Vì sao phải giới hạn exception được retry?

*Đáp án:* Vì validation, lỗi SQL, constraint hoặc thiếu quyền không tự hết khi thử lại. Retry những lỗi này chỉ làm tăng tải.

**Bài 6.** Khi dùng `@Retryable` cùng `@Transactional` trong Spring Framework 7, advice mặc định có thứ tự nào?

*Đáp án:* Retry ở ngoài và transaction ở trong. Mỗi lần thử đi qua transaction interceptor và có thể dùng transaction mới khi không có transaction bên ngoài đang hoạt động.

**Bài 7.** Vì sao không nên retry cùng object đã bị optimistic locking conflict?

*Đáp án:* Object vẫn mang version cũ. Cần tải lại aggregate mới nhất, đánh giá lại quy tắc nghiệp vụ rồi mới thử lưu.

**Bài 8.** Retry có thể làm email hoặc thanh toán bị gửi hai lần không?

*Đáp án:* Có. Side effect ngoài database cần idempotency key, outbox hoặc consumer idempotent.

**Bài 9.** Tại sao cần jitter?

*Đáp án:* Jitter phân tán thời điểm retry giữa nhiều client, tránh tất cả cùng gọi lại database sau một khoảng delay giống nhau.

**Bài 10.** Nếu caller đã mở transaction ngoài rồi gọi retryable method, có chắc mỗi lần thử là transaction riêng không?

*Đáp án:* Không. Propagation REQUIRED có thể tham gia transaction ngoài. Cần đặt retry boundary phù hợp hoặc tách coordinator khỏi transactional worker.

**Bài 11.** Dự án dùng Spring Framework 6.x có thể dùng native `org.springframework.resilience.annotation.Retryable` không?

*Đáp án:* Không. Native resilience annotation có từ Spring Framework 7.0. Dự án cũ có thể dùng Spring Retry nếu dependency tương thích, hoặc tự triển khai retry boundary phù hợp.

## 17. Điều cần ghi nhớ

- Retry dành cho lỗi có tính tạm thời; không retry mọi exception.
- Phân loại exception bằng hệ Spring DAO và chỉ định rõ nhóm được retry.
- Một thao tác retry an toàn cần idempotency hoặc cơ chế nhận diện request đã xử lý.
- Retry toàn bộ transaction, để lần thất bại rollback trước khi lần tiếp theo bắt đầu.
- Spring Framework 7.0 có `@Retryable` và `RetryTemplate` tích hợp trong core.
- Với Spring Framework 7, `maxRetries` là số lần thử lại sau lần đầu; tổng số lần gọi bằng một cộng maxRetries.
- Retry advice mặc định nằm ngoài transaction advice, giúp mỗi lần thử chạy trong transaction riêng khi không có transaction ngoài bao quanh.
- Không lưu lại aggregate stale sau optimistic locking conflict; hãy đọc lại và tính lại nghiệp vụ.
- Dùng backoff, jitter, max delay và deadline để tránh retry storm.
- Không retry side effect bên ngoài nếu chưa có idempotency key, outbox hoặc cơ chế chống trùng.
- Với dự án dùng Spring Framework trước 7.0, có thể dùng Spring Retry; cần phân biệt package và cách đếm maxAttempts.
- Integration test phải chứng minh transaction rollback, lần thử mới và kết quả cuối cùng trong database.

### Tài liệu tham khảo chính thức

- [Spring Framework — Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html): `@Retryable`, `@EnableResilientMethods`, `RetryTemplate`, backoff và thứ tự retry/transaction.
- [Spring Framework — Retryable API 7.0](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/resilience/annotation/Retryable.html): exception includes/excludes, maxRetries, delay, jitter, multiplier và maxDelay.
- [Spring Framework — RetryTemplate API 7.0](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/core/retry/RetryTemplate.html): retry policy và cách thực thi retry bằng code.
- [Spring Data Relational — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction mặc định của repository và transaction boundary ở service.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy, propagation và rollback rules.
- [Spring Retry — Retryable API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html): annotation và thuộc tính của thư viện Spring Retry cho các stack chưa dùng resilience feature của Framework 7.

Khi thêm retry, hãy bắt đầu từ tính an toàn của thao tác và transaction boundary. Chỉ khi biết rõ lỗi nào có thể thử lại, mỗi lần thử sẽ rollback/commit ra sao và request được nhận diện thế nào, retry mới giúp hệ thống phục hồi mà không nhân đôi side effect.
