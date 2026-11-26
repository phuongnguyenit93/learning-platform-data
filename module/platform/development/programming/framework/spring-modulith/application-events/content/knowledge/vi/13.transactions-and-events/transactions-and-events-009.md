# Isolation trong giao dịch và Application Events của Spring Modulith

## 1. Isolation là gì?

**Isolation** (tính cô lập giao dịch) là khả năng cơ sở dữ liệu kiểm soát việc một transaction nhìn thấy và tương tác với các thay đổi từ transaction khác. Đây là chữ **I** trong ACID. Trong ứng dụng có nhiều thao tác chạy đồng thời, isolation ảnh hưởng trực tiếp đến tính đúng đắn của số dư, điểm thưởng, tồn kho, đơn hàng và các phép tính dựa trên dữ liệu nhiều hàng.

Với **Spring Modulith Application Events**, phải phân biệt rõ hai ý nghĩa:

1. **Transaction isolation:** các mức `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`... áp dụng trong phạm vi transaction do database và transaction manager quản lý.
2. **Sự độc lập của các module/listener:** module `orders` có thể commit đơn hàng rồi các module `notifications`, `loyalty` xử lý sự kiện trong những transaction riêng.

Đây là **hai chiều thiết kế khác nhau**. Listener chạy transaction riêng không có nghĩa nó chia sẻ snapshot dữ liệu với publisher, cũng không đồng nghĩa hệ thống có một distributed transaction.

~~~mermaid
flowchart LR
    subgraph T1["T1 — orders"]
        O["Lưu đơn"] --> P["publishEvent(OrderPlaced)"]
    end
    T1 -->|"Commit"| E(("AFTER_COMMIT"))
    E --> T2["T2 — loyalty<br/>Ghi điểm"]
    E --> T3["T3 — notifications<br/>Lưu trạng thái gửi"]
    E --> T4["T4 — analytics<br/>Cập nhật projection"]
~~~

Sơ đồ mô tả luồng khi các consumer sử dụng `@ApplicationModuleListener` sau commit; nó không cam kết thứ tự thực thi giữa các listener.

### Mục tiêu bài học

Sau bài học thuộc chương **Giao dịch và event**, người học có thể:

- Nhận diện dirty read, non-repeatable read, phantom read, lost update và write skew.
- Phân biệt các mức transaction isolation của Spring/JDBC và giới hạn tùy hệ quản trị cơ sở dữ liệu.
- Cấu hình `@Transactional(isolation = ...)` có xét propagation và Spring proxy.
- Hiểu dữ liệu listener có thể đọc sau commit và tại sao event payload đôi khi cần snapshot.
- Kết hợp isolation, optimistic locking, unique constraint, idempotency và Event Publication Registry.
- Kiểm thử tranh chấp transaction và giám sát các publication xử lý thất bại.

## 2. Tình huống: tạo đơn và cộng điểm ở hai transaction

Giả sử khách đặt đơn `O-100`. Module `orders` thực hiện:

1. Kiểm tra yêu cầu, tính tổng tiền đã chốt.
2. Lưu order vào database trong transaction **T1**.
3. Công bố `OrderPlaced(eventId=E-100, orderId=O-100)` trong T1.
4. T1 commit.
5. Listener `loyalty` được kích hoạt sau commit và ghi điểm trong transaction **T2**.

Trong lúc listener chờ được thực thi, một request khác có thể sửa địa chỉ giao hàng hoặc trạng thái được phép sửa và commit ở transaction **T3**. Nếu T2 đọc order sau đó, nó có thể nhìn thấy trạng thái đã bị T3 thay đổi.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant O as orders / T1
    participant DB as Database
    participant E as Application Events
    participant U as Request khác / T3
    participant L as loyalty / T2

    C->>O: placeOrder()
    O->>DB: INSERT order O-100
    O->>E: publish OrderPlaced(E-100)
    O->>DB: COMMIT T1
    E-->>L: Kích hoạt sau commit
    U->>DB: UPDATE O-100; COMMIT T3
    L->>DB: SELECT O-100
    DB-->>L: Có thể thấy trạng thái từ T3
    L->>DB: Ghi điểm; COMMIT T2
~~~

Điều quan trọng: **AFTER_COMMIT chỉ nói event listener được kích hoạt sau commit của publisher; nó không đồng nghĩa T2 được đọc snapshot của T1 tại lúc phát event**.

Nếu loyalty cần chính xác số tiền tại thời điểm đặt đơn, nên truyền số tiền đã chốt trong event. Nếu loyalty cần trạng thái hiện tại của đơn, truy vấn một API công khai có thể phù hợp hơn. Isolation level không tự quyết định yêu cầu nghiệp vụ này.

## 3. Các hiện tượng tranh chấp khi transaction chạy đồng thời

### 3.1. Dirty read — đọc dữ liệu chưa commit

~~~text
T1: BEGIN; UPDATE orders SET status='PAID' WHERE id='O-100';
T2: SELECT status FROM orders WHERE id='O-100'; -- đọc PAID khi T1 chưa commit
T1: ROLLBACK;
~~~

T2 đã dựa vào trạng thái chưa bao giờ được commit. Đây là dirty read. `READ_COMMITTED` thường ngăn hiện tượng này; một số hệ quản trị (như PostgreSQL) không cho dirty read ngay cả khi yêu cầu mức `READ_UNCOMMITTED`.

### 3.2. Non-repeatable read — cùng hàng, hai lần đọc khác nhau

~~~text
T1: BEGIN; SELECT status FROM orders WHERE id='O-100'; -- CREATED
T2: BEGIN; UPDATE orders SET status='CANCELLED' ...; COMMIT;
T1: SELECT status FROM orders WHERE id='O-100';        -- có thể CANCELLED
T1: COMMIT;
~~~

Với `READ_COMMITTED`, câu truy vấn thứ hai có thể thấy commit mới từ transaction khác. `REPEATABLE_READ` được thiết kế để các lần đọc trong một transaction ổn định hơn, nhưng chi tiết phụ thuộc database.

**Chú ý JPA:** trong cùng persistence context, một entity đã load có thể được trả từ first-level cache. Việc `EntityManager.find` trả cùng object không chứng minh database đang ở `REPEATABLE_READ`; khi kiểm thử DB isolation, cần kiểm soát cache và câu SQL thực sự chạy.

### 3.3. Phantom read — tập kết quả truy vấn thay đổi

~~~text
T1: SELECT COUNT(*) FROM orders WHERE status='NEW'; -- 10
T2: INSERT INTO orders(status) VALUES('NEW'); COMMIT;
T1: SELECT COUNT(*) FROM orders WHERE status='NEW'; -- có thể 11
~~~

T1 nhìn thấy “hàng ma” vì T2 đã thêm một hàng thỏa predicate. Theo phân loại SQL truyền thống, `REPEATABLE_READ` không bắt buộc cấm mọi phantom; nhưng PostgreSQL `REPEATABLE READ` áp dụng snapshot theo transaction nên ngăn dạng phantom này. Phải đánh giá **hệ quản trị đang dùng**, không suy ra chỉ từ tên mức cô lập.

### 3.4. Lost update — mất cập nhật

Hai listener hoặc request cùng đọc số điểm ban đầu 100, rồi cộng lần lượt 20 và 30:

~~~text
T1: đọc points=100; chuẩn bị ghi 120
T2: đọc points=100; chuẩn bị ghi 130
T1: ghi 120; COMMIT
T2: ghi 130; COMMIT
Kết quả mong đợi = 150; thực tế có thể = 130
~~~

Một số database/isolation tự phát hiện xung đột và làm một transaction thất bại. Trong ứng dụng, nên bảo vệ một cách tường minh bằng **atomic update**, `@Version`, khóa hàng hoặc ledger với unique constraint.

Ví dụ cập nhật cộng nguyên tử:

~~~sql
UPDATE loyalty_accounts
SET points = points + :earnedPoints
WHERE customer_id = :customerId;
~~~

Lệnh này giúp tránh mô hình đọc-sửa-ghi giá trị cũ cho phép cộng đơn giản; vẫn cần bảo vệ trường hợp cùng **event** bị giao lại hai lần.

### 3.5. Write skew — phá invariant trải trên nhiều hàng

Hai transaction cùng kiểm tra có ít nhất một nhân viên trực ca. Mỗi transaction nhìn thấy hai nhân viên đang trực nên cho một người nghỉ; kết quả sau hai commit là không còn ai trực.

Write skew có thể xuất hiện trong một số triển khai **snapshot isolation**, dù không xảy ra dirty read. Với invariant xuyên hàng, cần constraint/lock hoặc mức `SERIALIZABLE` phù hợp, kèm xử lý khi transaction bị database yêu cầu retry.

## 4. Các mức isolation trong Spring/JDBC

Spring cung cấp `org.springframework.transaction.annotation.Isolation`. Bảng dưới thể hiện **định hướng chung**; kết quả cụ thể tùy DB, driver, MVCC/locking và transaction manager.

| Mức | Ý nghĩa thường gặp | Lưu ý thiết kế |
| --- | --- | --- |
| `READ_UNCOMMITTED` | Cho phép mức cô lập thấp theo chuẩn; dirty read có thể xảy ra. | Không phù hợp mặc định cho tiền/điểm; DB có thể thực thi mạnh hơn. |
| `READ_COMMITTED` | Không đọc dữ liệu transaction khác chưa commit. | Các câu query khác nhau có thể thấy commit mới. |
| `REPEATABLE_READ` | Đọc ổn định hơn trong một transaction. | Phantoms, write skew, lock và snapshot khác nhau giữa DB. |
| `SERIALIZABLE` | Kết quả tương đương một thứ tự transaction tuần tự theo mô hình DB hỗ trợ. | Có thể tăng contention/abort, cần retry **toàn transaction** khi serialization failure. |
| `DEFAULT` | Dùng mức mặc định của datasource/database. | Không đồng nghĩa cố định với `READ_COMMITTED` ở mọi DB. |

Không nên tự động chọn mức cao nhất. Isolation càng mạnh có thể tạo thêm contention, deadlock hoặc serialization failures dưới tải lớn. Cần biết **invariant nghiệp vụ nào phải bảo vệ**, rồi lựa chọn transaction, constraint, lock và mức cô lập phù hợp.

### READ_COMMITTED có đủ cho đơn hàng không?

Nhiều nghiệp vụ tạo đơn có thể hoạt động tốt với `READ_COMMITTED` kết hợp transaction, unique constraint và quy tắc cập nhật thích hợp. Nhưng nếu “chấp nhận đơn” còn yêu cầu giới hạn tồn kho hoặc ngân sách mà nhiều request cùng tranh chấp, một quy trình chỉ `SELECT` rồi `UPDATE` có thể chưa đủ. Cần atomic update có điều kiện, versioning/locking hoặc isolation mạnh hơn tùy DB.

**Isolation không phải bảo đảm đúng một lần giao event.** Ngay cả với `SERIALIZABLE`, cùng một event được phát lại sau hai transaction tuần tự vẫn có thể tạo hai lần cộng điểm nếu thiếu idempotency.

## 5. Cấu hình `@Transactional(isolation = ...)`

Một phương thức nghiệp vụ có thể yêu cầu isolation:

~~~java
package com.acme.shop.payments.internal;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LimitReservationService {

    private final CreditLimitRepository limits;

    public LimitReservationService(CreditLimitRepository limits) {
        this.limits = limits;
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void reserve(String accountId, long amount) {
        var account = limits.findByAccountId(accountId).orElseThrow();
        account.reserve(amount);
        limits.save(account);
    }
}
~~~

`CreditLimitRepository` và mô hình account là các thành phần minh họa do dự án định nghĩa. Với database chọn `SERIALIZABLE`, hệ thống cần có cách xử lý rollback khi gặp serialization conflict; không mặc định mọi request sẽ thành công ngay lần đầu.

**Các bẫy cần tránh:**

- Mức isolation được yêu cầu thường chỉ có hiệu lực khi **mở một transaction mới**. Với propagation `REQUIRED`, method tham gia transaction sẵn có thường dùng isolation của transaction đó thay vì âm thầm thay đổi mức.
- Có thể cấu hình transaction manager để kiểm tra sự không nhất quán của khai báo isolation với transaction hiện có; không giả định việc kiểm tra này đã được bật.
- `@Transactional` trong Spring AOP proxy thông thường chỉ có hiệu lực khi lời gọi đi qua proxy. Self-invocation có thể bỏ qua interceptor.
- Không phải mọi driver/database hỗ trợ cùng một bộ isolation; phải thử trên DB thật.
- Thay isolation của transaction publisher không làm transaction listener nhận cùng isolation.

~~~java
@Service
class BadTransactionalCall {

    void outer() {
        inner(); // Gọi nội bộ: có thể không đi qua proxy transaction.
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void inner() {
        // Không nên giả định isolation này đã có hiệu lực.
    }
}
~~~

## 6. Publisher và transaction T1

Trong module `orders`, sự kiện nên được phát từ một use case có transaction rõ ràng.

~~~java
package com.acme.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        BigDecimal payableTotal,
        String currencyCode,
        Instant occurredAt
) {}
~~~

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.events.OrderPlaced;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        var saved = orders.save(Order.create(command));

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                saved.getId(),
                saved.getCustomerId(),
                saved.getPayableTotal(),
                saved.getCurrencyCode(),
                clock.instant()
        ));
        return saved.getId();
    }
}
~~~

`OrderRepository`, `Order` và `PlaceOrderCommand` là kiểu minh họa, cần được định nghĩa trong dự án; code giả định `save` trả về order có ID và giá trị đã chốt. Cần cấu hình `Clock` bean thích hợp.

**T1 chịu trách nhiệm tạo đơn**, không phải gửi email hay cộng điểm. `publishEvent` trong T1 là thao tác công bố application event, **không tự buộc tất cả listener chờ commit**:

- `@EventListener` thông thường chạy đồng bộ ở lúc publish theo cấu hình mặc định, nên có thể đã chạy **trước khi T1 commit**.
- `@TransactionalEventListener(AFTER_COMMIT)` kích hoạt sau commit.
- `@ApplicationModuleListener` của Spring Modulith sử dụng kiểu xử lý sau commit, bất đồng bộ và transaction riêng.

Nếu T1 rollback, các listener gắn phase AFTER_COMMIT không xử lý sự kiện của T1, nhưng object `OrderPlaced` có thể đã được tạo trong bộ nhớ trước rollback. Vì vậy **object được tạo** không đồng nghĩa **sự thật nghiệp vụ đã commit**.

## 7. Consumer và transaction T2 của `@ApplicationModuleListener`

~~~java
package com.acme.shop.loyalty.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class AwardPointsOnOrderPlaced {

    private final LoyaltyAwardService awards;

    AwardPointsOnOrderPlaced(LoyaltyAwardService awards) {
        this.awards = awards;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        awards.creditOnce(
                event.eventId(),
                event.orderId(),
                event.customerId(),
                event.payableTotal(),
                event.currencyCode()
        );
    }
}
~~~

`creditOnce` là API nội bộ **do dự án phải triển khai** với idempotency và transaction phù hợp, không phải hàm sẵn của Spring.

Với `@ApplicationModuleListener`, listener sau commit xử lý trong **transaction riêng T2** so với T1 của publisher. Hệ quả:

1. T1 đã commit nên T2 không rollback ngược đơn được.
2. Nếu T2 lỗi, notifications hoặc analytics vẫn có thể hoàn tất độc lập.
3. T2 có isolation theo transaction manager/database mà nó dùng, không mang snapshot của T1.
4. Nếu T2 thực hiện nhiều truy vấn, các hiện tượng concurrent read/write trong T2 vẫn cần được xử lý.
5. Có thể có thời gian trễ giữa T1 commit và T2 bắt đầu; các transaction khác đã kịp cập nhật dữ liệu.

**Transaction riêng không đồng nghĩa cách ly nghiệp vụ tuyệt đối.** Nếu module loyalty cùng truy cập một bảng với các use case khác, khóa/constraint/versioning vẫn quan trọng.

## 8. `@TransactionalEventListener` và rủi ro ghi sau commit

Spring Framework cung cấp transactional event listener:

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderPlaced event) {
    // Handler được gọi sau khi transaction phát hành commit.
}
~~~

Tuy nhiên, **callback chạy sau commit không tự mở một transaction ghi database mới**. Trong quá trình transaction synchronization, một số resource của transaction đã commit có thể vẫn gắn với thread. Việc ghi dữ liệu từ callback theo cách không mở transaction mới phù hợp có thể gây kết quả khó hiểu hoặc không được commit như mong đợi.

Một giải pháp thường dùng là gọi một bean dịch vụ riêng có `REQUIRES_NEW`:

~~~java
package com.acme.shop.audit.internal;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditWriteService {

    private final AuditRepository repository;

    public AuditWriteService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(UUID eventId, UUID orderId) {
        repository.insertIfAbsent(eventId, orderId);
    }
}
~~~

`AuditRepository.insertIfAbsent` là thành phần minh họa. Gọi qua bean riêng giúp lời gọi đi qua Spring proxy, mở transaction độc lập.

Khi **thật sự cần isolation riêng**, có thể khai báo trong service mở transaction mới:

~~~java
@Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.READ_COMMITTED
)
public void record(UUID eventId, UUID orderId) {
    // Một transaction mới với isolation được yêu cầu.
}
~~~

Không chồng annotation transaction tùy tiện lên `@ApplicationModuleListener`: annotation đó đã mang cơ chế transaction riêng. Nếu có nhu cầu chọn isolation đặc biệt cho một bước, cần tổ chức ranh giới transaction/proxy rõ ràng và kiểm tra bằng integration test.

| Listener | Quan hệ với T1 | Transaction để ghi DB |
| --- | --- | --- |
| `@EventListener` đồng bộ | Có thể chạy ngay trong T1. | Phụ thuộc transaction đang hoạt động. |
| `@TransactionalEventListener(AFTER_COMMIT)` | Được kích hoạt sau T1 commit. | Không mặc nhiên có T2 mới. |
| `@ApplicationModuleListener` | Sau T1 commit, bất đồng bộ. | Có transaction riêng cho listener. |

Theo mặc định, `@TransactionalEventListener` không được kích hoạt khi publisher **không có transaction đang hoạt động**; `fallbackExecution = true` có thể thay đổi hành vi này khi được lựa chọn có chủ đích.

## 9. READ_COMMITTED không tạo snapshot của thời điểm phát event

Một lỗi thiết kế thường gặp: listener nghe `OrderPlaced(orderId)` rồi đọc bảng orders và coi đó là đúng trạng thái **tại lúc event xảy ra**.

~~~text
10:00:00  T1 tạo Order O-1, total=500000; COMMIT
10:00:01  OrderPlaced(E-1) chờ listener
10:00:02  T3 điều chỉnh một trường của Order O-1; COMMIT
10:00:03  T2 bắt đầu SELECT O-1 ở READ_COMMITTED
~~~

T2 có thể thấy bản ghi đã thay đổi bởi T3. **READ_COMMITTED không phải chức năng “quay về trạng thái ở thời điểm emit event”.** `REPEATABLE_READ` cũng không tự làm điều đó nếu T2 bắt đầu sau T3: nó có thể có một snapshot *ổn định hơn*, nhưng snapshot ấy vẫn mới hơn event.

### Hai chiến lược dữ liệu

**Snapshot trong event:**

~~~java
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        BigDecimal payableTotal,
        String currencyCode,
        Instant occurredAt
) {}
~~~

Phù hợp khi loyalty cần tính từ **số tiền đã chốt lúc đặt đơn**, hoặc analytics cần một sự thật lịch sử. Record bất biến giảm phụ thuộc vào trạng thái mutable ở module publisher.

**Reference rồi truy vấn:**

~~~java
public record OrderPlaced(UUID eventId, UUID orderId) {}
~~~

Phù hợp khi consumer cần **trạng thái mới nhất**, với một API truy vấn công khai và khả năng xử lý lỗi/trễ phù hợp. Không truy cập trực tiếp repository thuộc package nội bộ của module khác chỉ vì cần tra cứu.

**Câu hỏi thiết kế quan trọng:** consumer cần dữ kiện lịch sử hay trạng thái mới nhất? Isolation level không thể tự trả lời câu hỏi nghiệp vụ này.

## 10. Chống lost update bằng `@Version` và cập nhật nguyên tử

Một cách bảo vệ các cập nhật đồng thời trong JPA là optimistic locking.

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class LoyaltyAccount {

    @Id
    private String customerId;

    @Version
    private long version;

    private long points;

    protected LoyaltyAccount() {}

    public void addPoints(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("amount < 0");
        }
        points += amount;
    }
}
~~~

Khi hai transaction cùng đọc version cũ rồi đều muốn cập nhật, cơ chế optimistic locking có thể làm một transaction thất bại thay vì ghi đè im lặng. Ứng dụng cần lựa chọn **retry có giới hạn** hay trả lỗi. Không nên lặp vô hạn trong cùng transaction đã đánh dấu rollback-only.

Các cách bảo vệ khác gồm:

- **Atomic SQL update:** tránh vòng đọc-ghi giá trị cũ nếu chỉ cần cộng điểm.
- **Pessimistic locking:** khóa hàng/tài nguyên cần bảo vệ, có đánh đổi về throughput và deadlock.
- **Unique constraint:** bảo vệ một quy tắc như “mỗi eventId chỉ tạo một khoản điểm”.
- **Serializable transaction:** có ích cho một số invariant xuyên nhiều hàng, nhưng cần retry transaction khi bị abort.

Không có một isolation level tự thay thế các invariant và constraint nghiệp vụ.

## 11. Isolation không giải quyết giao event trùng: idempotency

Giả sử:

1. T1 tạo đơn và commit `OrderPlaced(eventId=E-1)`.
2. T2 (loyalty) cộng 20 điểm và commit.
3. Ứng dụng dừng trước khi publication được đánh dấu hoàn tất.
4. Hệ thống khôi phục và listener nhận lại `E-1` trong T3.

Ngay cả khi T2 và T3 đều ở `SERIALIZABLE`, **T3 vẫn có thể cộng 20 điểm nữa**: hai transaction chạy tuần tự nhưng vẫn thực hiện một thao tác nghiệp vụ lặp lại.

Cần một khóa idempotency ổn định, ví dụ `(consumerName, eventId)` hoặc ledger với `event_id` duy nhất:

~~~sql
CREATE TABLE loyalty_awards (
    event_id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    awarded_points BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Trong cùng transaction, consumer ghi khoản thưởng và điều chỉnh số dư một cách nguyên tử:

~~~java
@Transactional
public void creditOnce(OrderPlaced event) {
    // API giả định: insertUnique thực hiện thao tác nguyên tử;
    // trả false nếu eventId đã có trong ledger.
    boolean firstDelivery = awards.insertUnique(
            event.eventId(), event.orderId(), event.customerId()
    );
    if (!firstDelivery) {
        return;
    }
    balances.addPointsAtomically(
            event.customerId(), calculatePoints(event)
    );
}
~~~

`awards.insertUnique`, `balances.addPointsAtomically` và `calculatePoints` là API minh họa, cần triển khai và kiểm thử ở dự án thật. Một số database sẽ đánh dấu transaction lỗi khi vi phạm unique constraint; không được tùy tiện bắt duplicate-key exception rồi tiếp tục ghi trong transaction đã hỏng. Có thể dùng SQL insert-if-absent được DB hỗ trợ hoặc cơ chế giao dịch phù hợp.

**Phân biệt vai trò:** isolation hạn chế tranh chấp giữa transaction; idempotency bảo vệ tác dụng phụ khi **cùng event được xử lý nhiều lần**.

## 12. Event Publication Registry và ranh giới độ tin cậy

Spring Modulith cung cấp **Event Publication Registry** để theo dõi việc giao event tới các transactional event listener. Khi cấu hình persistence integration phù hợp, publication chưa hoàn tất có thể được ghi nhận, quan sát và phục hồi theo cơ chế recovery/republication mà hệ thống sử dụng.

~~~text
OrderPlaced(E-1) — transaction orders COMMITTED
├── notifications listener: COMPLETED
├── loyalty listener      : INCOMPLETE
└── analytics listener    : COMPLETED
~~~

Đây là mô hình **logic theo từng consumer**, không phải schema bảng cố định. Một listener lỗi không tự rollback đơn đã commit hay listener khác đã hoàn tất.

| Vấn đề | Cơ chế liên quan |
| --- | --- |
| Tránh đọc dữ liệu DB chưa commit | Isolation của database transaction. |
| Chỉ kích hoạt consumer sau commit | `@TransactionalEventListener` hoặc `@ApplicationModuleListener`. |
| Biết listener nào chưa hoàn tất | Registry + storage phù hợp. |
| Phát lại publication tồn | Recovery/republication đã cấu hình. |
| Tránh ghi điểm hai lần | Idempotency + constraint trong consumer. |
| Tránh email gửi trùng | Quy trình gửi và idempotency của hệ thống ngoài. |
| Tránh import implementation của module khác | Named interface/module verification. |

**Registry không phải một isolation level và không mang lại exactly-once side effects.** Việc lưu event bền vững và tính nguyên tử giữa business data với publication còn phụ thuộc cách chọn storage và transaction manager. Không suy ra mọi ứng dụng chỉ cần thêm `@ApplicationModuleListener` là có persistent recovery hoặc tự retry với backoff.

## 13. Fan-out: mỗi listener có transaction và nhu cầu isolation riêng

Một `OrderPlaced` có thể được notifications, loyalty và analytics nhận độc lập.

| Module | Tác vụ | Bảo vệ thường quan trọng |
| --- | --- | --- |
| Orders | Tạo đơn, giữ invariant. | Transaction, unique constraint, lock/versioning khi có tranh chấp. |
| Loyalty | Cộng điểm không trùng, không lost update. | Unique `eventId`, atomic update/optimistic lock. |
| Analytics | Cập nhật projection có thể trễ. | Idempotent upsert, version khi event đến sai thứ tự. |
| Notifications | Gửi xác nhận sau commit. | Delivery log, timeout, idempotency key và recovery. |

Không cần mặc định mọi listener dùng `SERIALIZABLE` “cho chắc”. Isolation mạnh làm tăng chi phí nhưng vẫn không thay thế idempotency, error handling và các bảo đảm của downstream.

Nếu nghiệp vụ yêu cầu “thanh toán thành công **trước** khi vận chuyển”, không thể chỉ cho hai handler cùng nghe `OrderPlaced` và tin vào thứ tự callback. Cần event tiếp theo `PaymentCaptured` hoặc workflow điều phối trạng thái rõ ràng. **Eventual consistency** không đồng nghĩa sự phụ thuộc nghiệp vụ được tự động giải quyết.

## 14. Đọc từ replica sau commit cũng có thể chưa thấy dữ liệu

Một listener được kích hoạt sau T1 commit nhưng lại đọc từ **read replica** chưa đồng bộ:

~~~text
Primary: T1 COMMIT Order O-100
Replica: chưa nhận bản ghi O-100
Listener AFTER_COMMIT: SELECT trên replica -> chưa thấy Order O-100
~~~

Đây là rủi ro **replication lag**, không chỉ do `READ_COMMITTED` hay `REPEATABLE_READ`. Cần lựa chọn phù hợp:

1. Đọc từ nguồn có bảo đảm read-after-write tương ứng nếu cần dữ liệu vừa commit ngay.
2. Dùng snapshot trong event khi consumer cần dữ kiện lịch sử.
3. Retry có giới hạn và theo dõi replica lag nếu trạng thái có thể đến trễ.
4. Không suy ra một transaction annotation cục bộ tạo atomicity xuyên các datasource.

Với DB khác nhau hoặc hệ thống ngoài (email, HTTP, broker), một `@Transactional` đơn lẻ không biến mọi tài nguyên thành một distributed transaction.

## 15. Kiểm thử isolation cần transaction đồng thời thật

### 15.1. Test commit và rollback của publisher

- T1 lưu order rồi publish; nếu T1 commit, listener after-commit có thể được kích hoạt.
- Cho T1 rollback sau publish; kiểm tra không có tác dụng phụ từ listener after-commit.
- Test `@EventListener` đồng bộ riêng để chứng minh nó có thể chạy trước commit.

Cẩn thận với `@Transactional` ở cấp test: nhiều test framework sẽ rollback khi test kết thúc. Nếu listener chờ after-commit mà transaction test chưa commit, việc “không thấy listener chạy” có thể chỉ là test chưa commit. Dùng transaction thực sự được commit hoặc `TestTransaction` khi phù hợp.

### 15.2. Test non-repeatable read bằng hai transaction

~~~text
T1: BEGIN READ_COMMITTED; SELECT order.status;
[đồng bộ để T1 chờ]
T2: BEGIN; UPDATE order.status; COMMIT;
[cho T1 tiếp tục]
T1: SELECT order.status; COMMIT;
~~~

Kiểm tra kết quả theo database cụ thể; thử lại với `REPEATABLE_READ`. Có thể dùng `CountDownLatch` hoặc barrier để điều khiển thứ tự, **không dựa vào một `Thread.sleep` cố định**. Nếu dùng JPA, lưu ý first-level cache; cần truy vấn SQL/clear context phù hợp để quan sát chính database.

### 15.3. Test optimistic lock và giao trùng

- Hai transaction đồng thời cập nhật cùng `LoyaltyAccount`: bảo đảm `@Version` phát hiện xung đột hoặc lệnh SQL atomic cho kết quả đúng.
- Hai lượt giao cùng `eventId`: bảo đảm ledger chỉ có một dòng và số điểm chỉ cộng một lần.
- Test transaction retry khi serialization failure/optimistic conflict; không mặc định dùng lại transaction đã rollback.
- Tạo listener lỗi rồi phục hồi publication với registry storage thực tế khi hệ thống cần bảo đảm này.

### 15.4. Test snapshot và trạng thái mới nhất

Sau T1 commit, cho một transaction khác cập nhật đơn trước khi listener xử lý; kiểm tra listener tính điểm từ **snapshot event** nếu đó là hợp đồng, thay vì đọc nhầm trạng thái mới hơn. Nếu use case cần dữ liệu hiện tại, test đường truy vấn API công khai và các tình huống thông tin chưa có sẵn.

Unit test mock `ApplicationEventPublisher` không đủ để xác nhận isolation, after-commit hoặc recovery sau sự cố. Cần integration test tương đương hệ quản trị cơ sở dữ liệu production.

## 16. Quan sát isolation và lỗi listener trong vận hành

Một hệ thống thực tế cần biết **listener lỗi vì xung đột dữ liệu hay vì delivery**, không chỉ biết publisher đã phát event:

| Tín hiệu | Tác dụng |
| --- | --- |
| `eventId`, `orderId`, `listenerName` | Truy vết cùng event qua các lần giao. |
| `occurredAt`, `processedAt` | Đo độ trễ từ event tới consumer. |
| `deadlocks`, `serializationFailures` | Theo dõi xung đột transaction DB. |
| `optimisticLockFailures` | Phát hiện cập nhật cùng aggregate. |
| `duplicateDeliverySkips` | Kiểm tra logic idempotency. |
| `replicaLag` nếu có | Nhận diện read-after-write chưa nhất quán. |
| `incompletePublications` | Biết consumer nào còn pending. |
| `attempt`, `errorType` | Phân biệt lỗi tạm thời và lỗi cần can thiệp. |

Ví dụ log do ứng dụng **tự thiết kế**, không phải output mặc định của Spring Modulith:

~~~text
event=OrderPlaced eventId=E-100 listener=loyalty attempt=1 status=FAILED reason=OPTIMISTIC_LOCK
event=OrderPlaced eventId=E-100 listener=loyalty attempt=2 status=COMPLETED
event=OrderPlaced eventId=E-100 listener=notifications attempt=1 status=COMPLETED
~~~

Đừng log nguyên payload có dữ liệu nhạy cảm để gỡ lỗi. Metrics về deadlock, retry, thời gian transaction, độ trễ listener và publication tồn đọng hữu ích hơn một dòng “event published”.

## 17. Các hiểu lầm phổ biến

1. **“AFTER_COMMIT luôn đọc đúng trạng thái khi publish.”** Sai. Listener có transaction khác, có thể chạy trễ và thấy commit mới hơn; dùng snapshot khi cần lịch sử.
2. **“SERIALIZABLE ngăn xử lý event trùng.”** Sai. Hai transaction tuần tự vẫn có thể xử lý cùng event hai lần nếu thiếu idempotency.
3. **“REQUIRES_NEW làm các module commit cùng nhau.”** Sai. Nó tạo transaction mới, không tạo distributed transaction.
4. **“Thêm `@Transactional(isolation=...)` vào method con chắc chắn có hiệu lực.”** Sai khi method tham gia transaction cũ hoặc self-invocation bỏ qua proxy.
5. **“REPEATABLE_READ giống nhau trên mọi database.”** Sai; MVCC, lock, phantom và write skew phụ thuộc DB.
6. **“Publish trong transaction nghĩa mọi listener chỉ chạy sau commit.”** Sai; `@EventListener` mặc định có thể chạy ngay khi publish.
7. **“Có Event Publication Registry là exactly-once.”** Sai; registry theo dõi publication, consumer cần idempotency riêng.
8. **“Sau commit đọc replica chắc chắn thấy dữ liệu.”** Sai; replica lag có thể tồn tại.
9. **“Module boundary là transaction isolation.”** Sai; module boundary kiểm soát phụ thuộc mã nguồn, transaction isolation kiểm soát tranh chấp dữ liệu.

## 18. Ma trận lựa chọn thiết kế

| Nhu cầu | Biện pháp ưu tiên | Tránh ngộ nhận |
| --- | --- | --- |
| Chỉ phản ứng khi đơn đã commit | Listener sau commit | `publishEvent` tự đồng nghĩa commit |
| Dùng giá đã chốt lúc đặt đơn | Snapshot bất biến trong event | Isolation DB tự giữ snapshot T1 cho T2 |
| Tránh mất cập nhật điểm | Atomic update / optimistic lock | READ_COMMITTED tự ngăn mọi lost update |
| Không cộng điểm hai lần | Unique constraint theo eventId | SERIALIZABLE thay cho idempotency |
| Invariant nhiều hàng có tranh chấp | Constraint/lock hoặc SERIALIZABLE + retry | Mọi transaction đều thành công ở isolation mạnh |
| Ghi DB sau `AFTER_COMMIT` | Transaction mới phù hợp | Callback luôn có transaction ghi hợp lệ |
| Phục hồi listener lỗi | Registry/storage/recovery + monitoring | Annotation listener tự retry vô hạn |
| Hạn chế phụ thuộc module | Event contract/named interface/verify | DB isolation bảo vệ Java package |
| Đọc ngay dữ liệu vừa commit qua replica | Read source phù hợp hoặc retry/snapshot | Replica luôn nhất quán tức thì |

## 19. Bài thực hành: OrderPlaced và tranh chấp điểm thưởng

**Bối cảnh:** Khách hàng `C-100` có 100 điểm. Đơn `O-100` trị giá 500.000 VND được tạo và đủ điều kiện cộng 20 điểm. Module loyalty phải bảo đảm cuối cùng khách có **120 điểm**, kể cả khi cùng `OrderPlaced` được giao nhiều lần.

Thực hiện:

1. Tạo record `OrderPlaced(eventId, orderId, customerId, payableTotal, currencyCode, occurredAt)`.
2. Trong `OrderService.placeOrder` có `@Transactional`, lưu đơn rồi publish event.
3. Đăng ký `@ApplicationModuleListener` trong loyalty, nhận event và cập nhật điểm.
4. Tạo ledger `loyalty_awards` với unique `event_id`, ghi ledger và cập nhật số dư nguyên tử trong transaction.
5. Giao lại cùng `eventId`: số điểm cuối phải là **120**, không phải 140.
6. Mở hai transaction đồng thời cập nhật điểm; kiểm chứng atomic update hoặc `@Version` ngăn lost update.
7. Cho publisher rollback sau publish: listener after-commit không được cộng điểm.
8. Cho T3 cập nhật order sau commit của T1 nhưng trước T2 đọc, rồi so sánh sử dụng snapshot và truy vấn DB hiện tại.
9. Nếu có read replica, thử độ trễ sao chép và quyết định consumer cần read-after-write hay retry.
10. Khi có Registry persistence/recovery, mô phỏng listener lỗi, phát lại publication và xác nhận không cộng trùng.

**Câu hỏi tự kiểm tra:** Vì sao T2 không có cùng snapshot với T1? Isolation và idempotency giải quyết hai vấn đề gì khác nhau? Khi nào `REPEATABLE_READ` chưa đủ cho invariant? Vì sao `SERIALIZABLE` có thể làm transaction thất bại để ứng dụng retry? Tại sao after-commit và read replica không tự tạo read-after-write guarantee?

**Ghi nhớ:** Isolation kiểm soát **các transaction truy cập dữ liệu đồng thời**, không tự biến các listener thành một giao dịch chung và không bảo đảm consumer đọc đúng trạng thái lịch sử khi event được phát. Trong Spring Modulith, xử lý sau commit tách transaction của publisher khỏi transaction listener. Để hệ thống đúng đắn và đáng tin cậy, cần kết hợp isolation phù hợp, event snapshot khi cần, optimistic locking/atomic update/constraint, idempotency, Event Publication Registry với recovery khi cần, cùng kiểm thử tranh chấp thực tế và observability.

