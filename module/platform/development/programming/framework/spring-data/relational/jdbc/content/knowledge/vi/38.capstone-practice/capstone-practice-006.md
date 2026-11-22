# Mô phỏng hai giao dịch cập nhật cùng đơn hàng

Trong ứng dụng **Spring Data Relational JDBC**, hai request có thể cùng đọc một đơn hàng, thay đổi trạng thái trong bộ nhớ và lưu gần như đồng thời. Nếu cả hai transaction ghi mà không kiểm tra phiên bản dữ liệu đã đọc, lần ghi sau có thể ghi đè kết quả của lần ghi trước. Đây là **lost update**.

Bài thực hành này mô phỏng hai transaction độc lập cùng tải một aggregate `PurchaseOrder`. Transaction A và B đều đọc version hiện tại. A cập nhật và commit trước; B tiếp tục lưu snapshot cũ. Khi aggregate dùng `@Version`, Spring Data JDBC phát hiện version không còn khớp và ném `OptimisticLockingFailureException`. Test dùng hai thread, hai transaction và latch để điều khiển thứ tự, sau đó kiểm tra trạng thái cuối cùng trong database.

## 1. Tình huống cần mô phỏng

Giả sử một đơn hàng có trạng thái `PENDING` và version `0`. Hai request đến gần như cùng lúc:

- Request A xác nhận đơn hàng.
- Request B hủy đơn hàng.

Cả hai đều tải cùng một trạng thái ban đầu:

~~~text
Database:
  id = 100
  status = PENDING
  version = 0

Transaction A reads: PENDING, version 0
Transaction B reads: PENDING, version 0
~~~

Nếu không có cơ chế phát hiện xung đột, hai transaction có thể ghi:

~~~text
T1: UPDATE purchase_order SET status = 'CONFIRMED' WHERE id = 100
T2: UPDATE purchase_order SET status = 'CANCELLED'  WHERE id = 100
~~~

Nếu T1 commit trước rồi T2 commit sau, trạng thái cuối cùng là `CANCELLED`. Thay đổi `CONFIRMED` của T1 bị ghi đè mà không có lỗi. Kết quả này có thể vi phạm nghiệp vụ vì đơn hàng đã xác nhận không còn được phép hủy theo luồng thông thường.

## 2. Lost update khi không có optimistic locking

Đầu tiên, entity không có field version:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private OrderStatus status;

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Order is not pending");
        }
        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Order is not pending");
        }
        status = OrderStatus.CANCELLED;
    }
}
~~~

Hai service method có thể cùng tải aggregate rồi lưu:

~~~java
@Transactional
public void confirm(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    order.confirm();
    orders.save(order);
}

@Transactional
public void cancel(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    order.cancel();
    orders.save(order);
}
~~~

Các method này có transaction riêng nếu được gọi qua Spring proxy. Nhưng transaction boundary tự nó không bảo đảm phát hiện stale write. Nếu update không có điều kiện kiểm tra version, hai transaction có thể ghi đè lẫn nhau.

### 2.1. Timeline của lost update

~~~text
Time  Transaction A                 Transaction B                 Database
----  -------------                 -------------                 --------
1     BEGIN                                                        status=PENDING
2     SELECT order ------------------------------------------------> version not used
3                                   BEGIN
4                                   SELECT order ------------------> status=PENDING
5     UPDATE status=CONFIRMED -------------------------------------> status=CONFIRMED
6     COMMIT
7                                   UPDATE status=CANCELLED ------> status=CANCELLED
8                                   COMMIT
~~~

Không có version predicate nên database không biết B đang ghi từ một snapshot cũ. Câu lệnh update vẫn thành công nếu hàng có ID tương ứng.

## 3. Bật optimistic locking bằng @Version

Spring Data JDBC hỗ trợ optimistic locking thông qua thuộc tính `@Version` trên aggregate root:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String orderNumber;
    private OrderStatus status;

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Order is not pending");
        }
        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Order is not pending");
        }
        status = OrderStatus.CANCELLED;
    }
}
~~~

Với entity mới, version được khởi tạo theo cơ chế của Spring Data JDBC. Khi update, framework dùng version đã đọc để xác định hàng có còn ở phiên bản đó không, đồng thời tăng version khi ghi thành công.

SQL có thể hình dung như:

~~~sql
UPDATE purchase_order
SET status = ?,
    version = version + 1
WHERE id = ?
  AND version = ?;
~~~

Nếu một transaction đã tăng version từ `0` lên `1`, transaction khác vẫn cố update với điều kiện `version = 0` sẽ không cập nhật được hàng nào. Spring Data JDBC chuyển kết quả đó thành `OptimisticLockingFailureException`.

### 3.1. Timeline với @Version

~~~text
Database ban đầu: id=100, status=PENDING, version=0

T1: BEGIN
T1: SELECT -> status=PENDING, version=0

T2: BEGIN
T2: SELECT -> status=PENDING, version=0

T1: UPDATE ... WHERE id=100 AND version=0
    -> 1 row updated, version becomes 1
T1: COMMIT

T2: UPDATE ... WHERE id=100 AND version=0
    -> 0 rows updated
T2: OptimisticLockingFailureException
T2: ROLLBACK

Final database: status from T1, version=1
~~~

Optimistic locking không giữ lock trong suốt thời gian người dùng chỉnh sửa. Nó phát hiện xung đột tại thời điểm ghi, phù hợp khi xung đột tương đối hiếm và transaction ngắn.

## 4. Repository và fixture

Repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Trong integration test, tạo một đơn hàng ban đầu rồi lưu bằng repository:

~~~java
PurchaseOrder saved = orders.save(
        PurchaseOrder.pending("PO-100", OrderStatus.PENDING)
);

Long orderId = saved.getId();
~~~

Hãy dùng object trả về từ `save`, vì generated ID và version được cập nhật theo kết quả persistence. Tùy cách thiết kế entity, factory `pending(...)` có thể nhận order number và khởi tạo trạng thái/version phù hợp.

## 5. Vì sao cần hai thread và hai transaction?

Transaction của Spring thường gắn với thread hiện tại. Nếu gọi hai repository method tuần tự trên cùng thread trong cùng transaction, ta không mô phỏng được hai transaction độc lập.

Để tạo concurrency test:

- Dùng hai thread riêng.
- Mỗi thread gọi `TransactionTemplate.execute(...)` để tạo transaction riêng.
- Cấu hình connection pool đủ ít nhất hai connection đồng thời.
- Dùng `CountDownLatch` để đảm bảo cả hai transaction đã đọc cùng version trước khi A ghi.
- Chỉ báo B tiếp tục sau khi transaction A đã commit.

Không đánh dấu test method là `@Transactional` nếu muốn quan sát transaction độc lập trong các thread. Transaction gắn với thread test không tự truyền sang worker thread.

## 6. Test deterministic với TransactionTemplate

Ví dụ dưới đây dùng Spring Boot, JUnit 5 và Testcontainers hoặc database test tương ứng. Entity, repository, schema migration và các import được giả định đã có.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataJdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class PurchaseOrderConcurrencyTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Autowired
    PlatformTransactionManager transactionManager;

    @Test
    void rejectsSecondWriterWhenItUsesAnOldVersion() throws Exception {
        PurchaseOrder saved = orders.save(
                PurchaseOrder.pending("PO-100", OrderStatus.PENDING)
        );
        Long orderId = saved.getId();

        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        CountDownLatch transactionBHasRead = new CountDownLatch(1);
        CountDownLatch transactionAHasCommitted = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Future<?> writerB = executor.submit(() ->
                    tx.execute(status -> {
                        PurchaseOrder stale = orders.findById(orderId)
                                .orElseThrow();

                        transactionBHasRead.countDown();
                        await(transactionAHasCommitted);

                        stale.cancel();
                        orders.save(stale);
                        return null;
                    })
            );

            Future<?> writerA = executor.submit(() -> {
                tx.execute(status -> {
                    await(transactionBHasRead);

                    PurchaseOrder current = orders.findById(orderId)
                            .orElseThrow();
                    current.confirm();
                    orders.save(current);
                    return null;
                });

                // execute() chỉ trả về sau khi transaction A đã commit.
                transactionAHasCommitted.countDown();
            });

            writerA.get(10, TimeUnit.SECONDS);

            assertThatThrownBy(() -> writerB.get(10, TimeUnit.SECONDS))
                    .isInstanceOf(ExecutionException.class)
                    .hasCauseInstanceOf(OptimisticLockingFailureException.class);

            PurchaseOrder finalOrder = orders.findById(orderId)
                    .orElseThrow();

            assertThat(finalOrder.getStatus())
                    .isEqualTo(OrderStatus.CONFIRMED);
            assertThat(finalOrder.getVersion())
                    .isEqualTo(saved.getVersion() + 1);
        } finally {
            executor.shutdownNow();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for transaction");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Concurrency test interrupted", ex);
        }
    }
}
~~~

Đây là skeleton integration test. Cần thêm import của entity/repository/domain exception phù hợp, và bảo đảm test configuration không mở một transaction bao ngoài.

### 6.1. Thứ tự thực thi được điều khiển như thế nào?

1. Thread B mở transaction B, đọc order ở version ban đầu rồi giảm latch `transactionBHasRead`.
2. Thread B chờ latch `transactionAHasCommitted`; transaction B vẫn giữ snapshot đã đọc.
3. Thread A bắt đầu transaction A sau khi B đã đọc.
4. A đọc order, thay đổi status và gọi `save`.
5. `TransactionTemplate.execute` của A hoàn tất và commit; sau đó A giảm latch `transactionAHasCommitted`.
6. B được tiếp tục, thay đổi object cũ và gọi `save`.
7. Version trong database đã tăng, nên update của B không khớp version cũ và ném optimistic locking exception.
8. Transaction B rollback.

Test không dựa vào tốc độ scheduler hoặc sleep ngẫu nhiên. Hai latch xác định rõ thời điểm mỗi transaction đã đọc và thời điểm transaction thắng đã commit.

### 6.2. Vì sao cần connection pool có ít nhất hai connection?

Transaction B giữ một connection trong lúc chờ A commit. Nếu pool chỉ có một connection, A không lấy được connection để chạy; test có thể timeout hoặc deadlock ở tầng pool.

Đảm bảo datasource pool có ít nhất hai connection khả dụng cho test này. Database container cũng phải cho phép hai session đồng thời.

### 6.3. Tắt transaction bao ngoài của @DataJdbcTest

`@DataJdbcTest` mặc định chạy test method trong một transaction do Spring Test quản lý. Chỉ bỏ annotation `@Transactional` khỏi method là chưa đủ để tắt transaction này. Vì concurrency test cần hai transaction worker độc lập và cần fixture đã commit, ví dụ đặt `@Transactional(propagation = Propagation.NOT_SUPPORTED)` trên test class.

Khi đó, lệnh `orders.save` tạo fixture chạy bằng transaction repository thông thường và hoàn tất trước khi hai worker bắt đầu. Mỗi worker dùng `TransactionTemplate` để mở transaction riêng trên thread của nó.

Nếu muốn test được rollback tự động, hãy dùng một test khác cho setup/cleanup đơn giản. Với concurrency test, dọn dữ liệu sau khi cả hai worker đã kết thúc hoặc dùng database riêng cho test class. Nếu không tắt test-managed transaction, worker thread không kế thừa transaction của thread test và có thể không nhìn thấy fixture chưa commit.

## 7. Bắt và kiểm tra OptimisticLockingFailureException

Trong ví dụ, `Future.get()` bọc exception của thread worker trong `ExecutionException`. Vì vậy test kiểm tra cause:

~~~java
assertThatThrownBy(() -> writerB.get(10, TimeUnit.SECONDS))
        .isInstanceOf(ExecutionException.class)
        .hasCauseInstanceOf(OptimisticLockingFailureException.class);
~~~

Trong service thông thường, exception có thể được bắt để chuyển thành kết quả nghiệp vụ:

~~~java
@Transactional
public void cancel(Long orderId) {
    PurchaseOrder order = orders.findById(orderId).orElseThrow();
    order.cancel();

    try {
        orders.save(order);
    } catch (OptimisticLockingFailureException ex) {
        throw new OrderChangedByAnotherRequestException(orderId, ex);
    }
}
~~~

Lưu ý transaction có thể đã được đánh dấu rollback-only khi persistence operation thất bại. Không bắt exception rồi tiếp tục ghi các thay đổi khác trong cùng transaction như thể thao tác vẫn an toàn.

## 8. Kết quả khi bỏ @Version

Để quan sát lost update, bỏ `@Version` khỏi entity và chạy cùng một kịch bản hai transaction:

- B đọc `PENDING`.
- A đọc `PENDING`.
- A lưu `CONFIRMED` và commit.
- B lưu `CANCELLED` từ snapshot cũ và commit.

Nếu SQL update chỉ dựa trên ID, cả hai update đều có thể thành công. Kết quả cuối phụ thuộc transaction commit sau cùng.

Một test lost update nên xác nhận B đã ghi đè trạng thái A để thể hiện rủi ro. Sau đó thêm `@Version` và chạy lại test optimistic locking để xác nhận B bị từ chối.

## 9. Phân biệt optimistic locking với isolation level

Isolation level và optimistic locking giải quyết các vấn đề liên quan nhưng không giống nhau.

| Cơ chế | Vai trò |
| --- | --- |
| READ COMMITTED | Một query chỉ đọc dữ liệu đã commit tại thời điểm query theo semantics database |
| REPEATABLE READ | Có thể giữ snapshot ổn định hơn trong transaction, tùy database |
| SERIALIZABLE | Database cố bảo đảm kết quả tương đương một thứ tự tuần tự; có thể phát sinh serialization failure |
| `@Version` | Kiểm tra version mà aggregate đã đọc khi thực hiện update |
| Pessimistic row lock | Khóa hàng trong transaction để ngăn writer khác sửa theo cơ chế lock của database |

Không nên giả định chọn isolation level cao là thay thế hoàn toàn cho version check. Hành vi phụ thuộc database và transaction pattern; optimistic locking diễn đạt trực tiếp yêu cầu rằng aggregate chỉ được ghi nếu version chưa đổi.

## 10. Nếu muốn mô phỏng pessimistic locking

Một cách khác là khóa hàng khi đọc, ví dụ SQL:

~~~sql
SELECT id, status, version
FROM purchase_order
WHERE id = :id
FOR UPDATE;
~~~

Database giữ row lock đến khi transaction commit hoặc rollback. Writer khác muốn khóa/cập nhật cùng hàng có thể phải chờ.

Đây là cơ chế phụ thuộc database và cần chạy trong transaction. Có thể triển khai bằng custom repository method dùng `JdbcTemplate`/`NamedParameterJdbcTemplate` để đọc hàng với `FOR UPDATE`, rồi thực hiện cập nhật trong cùng transaction.

Pessimistic locking phù hợp khi xung đột thường xuyên hoặc nghiệp vụ cần tuần tự hóa thao tác. Nó làm tăng thời gian giữ lock và nguy cơ blocking/deadlock. Optimistic locking thường đơn giản hơn khi xung đột ít.

## 11. Xử lý conflict trong nghiệp vụ

Khi B nhận optimistic locking failure, không nên tự động ghi lại snapshot cũ. Có một số lựa chọn:

### 11.1. Trả conflict cho caller

Phù hợp với màn hình chỉnh sửa đơn hàng: thông báo dữ liệu đã thay đổi và yêu cầu tải lại.

### 11.2. Tải lại và áp dụng lại command

Nếu command có thể áp dụng an toàn trên trạng thái mới:

1. Rollback transaction cũ.
2. Mở transaction mới.
3. Tải aggregate mới nhất.
4. Kiểm tra invariant.
5. Áp dụng lại command.
6. Lưu và xử lý conflict nếu vẫn xảy ra.

Không retry bên trong transaction đã lỗi hoặc rollback-only. Mỗi lần retry phải có transaction mới.

### 11.3. Dùng thao tác idempotent

Nếu command là đánh dấu đã nhận thanh toán hoặc thêm một sự kiện đã xử lý, thiết kế idempotency key hoặc unique constraint có thể phù hợp hơn việc ghi đè một trạng thái bằng snapshot cũ.

### 11.4. Không retry vô hạn

Đặt giới hạn số lần retry, backoff và metric. Nếu conflict liên tục, có thể aggregate quá nóng hoặc transaction quá dài; cần xem lại thiết kế.

## 12. Những lỗi thường gặp khi viết concurrency test

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chạy hai lời gọi tuần tự trên một thread | Không tạo hai transaction độc lập đồng thời | Dùng hai thread và transaction riêng |
| Dùng sleep để đoán thứ tự | Test chập chờn theo scheduler | Dùng `CountDownLatch` hoặc `CyclicBarrier` |
| Cả hai thread dùng cùng transaction context | Không mô phỏng hai connection/transaction | Dùng `TransactionTemplate` trong từng thread |
| Test method có transaction ngoài | Fixture chưa commit, worker không thấy dữ liệu | Bỏ transaction bao ngoài hoặc commit setup trước |
| Connection pool chỉ có một connection | Transaction thứ hai không thể chạy | Cấp ít nhất hai connection |
| Entity không có `@Version` | Update stale có thể ghi đè | Thêm version property cho aggregate root |
| Bắt exception rồi tiếp tục cùng transaction | Transaction có thể rollback-only | Kết thúc transaction và retry bằng transaction mới |
| Chỉ assert exception | Chưa chứng minh trạng thái cuối đúng | Đọc lại aggregate và assert status/version |
| Dùng H2 nhưng production dùng DB khác | Khác biệt lock/isolation có thể làm test sai | Test bằng database production qua Testcontainers |
| Thread bị treo khi test thất bại | Test suite chạy mãi | Dùng timeout cho latch/future và shutdown executor |

## 13. Mở rộng mô phỏng cho aggregate có child

Nếu `PurchaseOrder` có `OrderLine`, cả hai transaction có thể cùng thay đổi root và child. Khi dùng `@Version` ở aggregate root, version của root đóng vai trò kiểm soát cập nhật aggregate theo ranh giới persistence.

Ví dụ:

~~~java
@Transactional
public void changeLineQuantity(Long orderId, Long lineId, int quantity) {
    PurchaseOrder order = orders.findById(orderId).orElseThrow();
    order.changeLineQuantity(lineId, quantity);
    orders.save(order);
}
~~~

Test concurrency nên xác nhận:

- Hai transaction đọc cùng root version.
- Transaction thắng lưu root/child và tăng version.
- Transaction còn lại không thể ghi snapshot aggregate cũ.
- Trạng thái child cuối cùng khớp với transaction thắng.

Không chỉ assert root status. Đọc lại collection child để bảo đảm không có dữ liệu bị ghi đè hoặc mất.

## 14. Quy trình thực hành từ đầu đến cuối

1. Tạo bảng `purchase_order` với ID, status và version.
2. Khai báo aggregate root với `@Id` và `@Version`.
3. Tạo repository kế thừa `CrudRepository`.
4. Insert một order ở trạng thái `PENDING`.
5. Dùng hai thread để mở hai transaction độc lập.
6. Cho cả hai transaction đọc cùng order version.
7. Cho transaction A cập nhật và commit.
8. Cho transaction B tiếp tục lưu snapshot cũ.
9. Xác nhận B nhận `OptimisticLockingFailureException`.
10. Đọc lại order và xác nhận status/version thuộc transaction A.
11. Bỏ `@Version` trong một biến thể test để quan sát lost update.
12. Chạy test trên database cùng loại với production.

## Ghi nhớ

Hai transaction có thể cùng đọc một aggregate version và đưa ra hai quyết định khác nhau. Nếu update chỉ dựa trên ID, transaction commit sau có thể ghi đè kết quả trước (lost update). Thêm `@Version` vào aggregate root để Spring Data JDBC kiểm tra version khi lưu. Transaction đầu tiên tăng version; transaction thứ hai dùng version cũ sẽ không cập nhật được hàng và nhận `OptimisticLockingFailureException`.

Để mô phỏng đáng tin cậy, dùng hai thread, hai transaction độc lập và ít nhất hai database connection. `TransactionTemplate` giúp tạo transaction trong từng thread; `CountDownLatch` điều khiển để cả hai cùng đọc trước khi transaction thắng commit. Sau đó assert exception của writer stale và đọc lại database để xác nhận trạng thái/version cuối cùng. Không dùng sleep để đoán thứ tự, không đặt transaction bao ngoài test, và không retry trong transaction đã rollback-only. Khi xử lý conflict, tải lại aggregate trong transaction mới, kiểm tra invariant và áp dụng lại command có giới hạn nếu nghiệp vụ cho phép.

## Tài liệu tham khảo

- [Spring Data Relational — Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Transaction-bound Events and Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers for Java](https://java.testcontainers.org/)
