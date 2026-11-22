# Giữ kết nối trong thời gian ngắn và tránh chờ mạng khi đang giữ giao dịch

## 1. Mục tiêu và thông điệp chính

Khi phát triển tầng truy cập dữ liệu trong Spring Framework, hiệu năng không chỉ phụ thuộc vào câu SQL nhanh hay chậm. Một ứng dụng có thể dùng query mất vài mili-giây nhưng vẫn cạn connection pool nếu mỗi request **giữ transaction mở rồi chờ HTTP, RPC, message broker, file upload hoặc dịch vụ bên ngoài**.

Sau bài này, bạn có thể:

- Phân biệt **physical database connection**, **connection mượn từ pool**, **transaction**, **khóa dữ liệu** và thời điểm mỗi tài nguyên được giải phóng.
- Giải thích vì sao gọi mạng bên trong `@Transactional` làm tăng thời gian mượn connection, độ trễ, khả năng chờ lock và nguy cơ lỗi dây chuyền.
- Chọn ranh giới transaction ngắn: chuẩn bị/kiểm tra dữ liệu và gọi dịch vụ chậm ở bên ngoài; chỉ mở transaction cho các thay đổi cần commit/rollback cùng nhau.
- Áp dụng đúng các lựa chọn **gọi trước transaction**, **gọi sau commit**, **transactional outbox** và **workflow/Saga** theo mức độ nhất quán cần thiết.
- Thiết kế ví dụ Spring Boot + JDBC có SQL, transaction, job phát thông báo và retry mà không thực hiện HTTP trong transaction đang giữ connection.
- Theo dõi HikariCP, transaction duration, PostgreSQL `pg_stat_activity`; phân biệt cách xử lý gốc với timeout/cấu hình pool chỉ giúp giới hạn tác động.

**Quy tắc làm việc:** **giữ transaction đủ ngắn để bảo vệ bất biến dữ liệu**, không biến transaction của database thành ranh giới bao trùm công việc mạng không kiểm soát được thời gian. Đây là nguyên tắc thiết kế, không phải đòi hỏi mọi thao tác phải chạy ngoài transaction.

## 2. Hiểu chính xác: connection, pool, transaction, lock

### 2.1. Database connection là gì?

Với JDBC, đối tượng `java.sql.Connection` đại diện phiên tương tác tới DB. Spring Boot thường dùng `DataSource` được quản lý bởi connection pool như HikariCP. Pool duy trì một tập **physical connections** tới DB để tái sử dụng. Mã ứng dụng mượn một connection, dùng xong trả về pool; gọi `close()` trên wrapper lấy từ pool thường là **trả connection**, không đóng vĩnh viễn kết nối TCP.

| Khái niệm | Vai trò | Điều cần quan sát |
| --- | --- | --- |
| Physical connection | Phiên/kết nối thật tới database | Số phiên, giới hạn kết nối server |
| Borrowed/active connection | Đang được ứng dụng mượn khỏi pool | Hikari active, thời gian checkout |
| Idle connection trong pool | Sẵn có để mượn lại, không đang phục vụ request | Hikari idle; không đồng nghĩa DB đang `idle in transaction` |
| Transaction | Nhóm thao tác DB có ranh giới commit/rollback và isolation | Thời điểm bắt đầu/kết thúc, lock, trạng thái idle |
| Row/table lock | Cơ chế DB bảo vệ thao tác đồng thời | Chờ lock, deadlock, contention |
| Network call | Gọi HTTP/RPC/broker từ ứng dụng tới hệ thống khác | Connect/read timeout, retry, độ trễ đuôi |

Đừng nhầm `idle` của HikariCP với `idle in transaction` của PostgreSQL. Một connection `idle` trong pool là tài nguyên đang rảnh; một backend PostgreSQL `idle in transaction` là phiên **đã mở transaction nhưng hiện không chạy SQL**, có thể tiếp tục giữ lock và cản trở dọn dẹp phiên bản dữ liệu.

### 2.2. Spring @Transactional sở hữu ranh giới nào?

Trong mô hình imperative phổ biến, Spring dùng `PlatformTransactionManager` và transaction interceptor quanh phương thức được gọi qua proxy Spring. Ví dụ:

```java
@Transactional
public void updateOrder() {
    repository.updateStatus(...);
    // các thao tác khác
}
```

Khi phương thức được gọi theo đường Spring proxy hợp lệ, transaction được khởi tạo hoặc tham gia vào transaction sẵn có theo cấu hình `propagation`. Khi phương thức kết thúc bình thường, manager commit nếu đủ điều kiện; ngoại lệ unchecked thoát ra thường kích hoạt rollback mặc định.

**Lưu ý về thời điểm checkout:** transaction bắt đầu về mặt logic không luôn đồng nghĩa connection vật lý đã được mượn ngay tại dòng đầu tiên. `DataSourceTransactionManager` điển hình lấy/bind JDBC connection khi bắt đầu; một số cấu hình lazy connection hoặc JPA provider có thể trì hoãn việc mượn connection đến câu SQL đầu. Dù ở cấu hình nào, **sau khi đã thực thi SQL và đang chờ mạng trước commit, transaction vẫn mở**, và connection/lock có thể còn bị giữ cho tới khi transaction hoàn tất.

Cũng không nên hiểu `@Transactional(readOnly = true)` là “không giữ connection” hoặc “không có transaction”. Đây là gợi ý/thuộc tính transaction phù hợp thao tác đọc; thời gian và tài nguyên thực tế vẫn phụ thuộc transaction manager, JDBC driver, JPA provider và DBMS.

### 2.3. Khóa dữ liệu sống bao lâu?

Một `UPDATE` hoặc `SELECT ... FOR UPDATE` có thể giữ khóa đến cuối transaction. Nếu làm:

```text
T0: bắt đầu transaction
T1: UPDATE orders SET status = 'PROCESSING' WHERE id = 42  (DB: nhanh)
T2: gọi HTTP tới đối tác; chờ phản hồi                         (có thể rất chậm)
T3: UPDATE orders SET status = 'CONFIRMED' WHERE id = 42
T4: COMMIT
```

Khoảng **T2 → T3** không chạy SQL, nhưng transaction vẫn mở, connection có thể vẫn được mượn, và lock từ T1 chưa được giải phóng. Request khác muốn cập nhật cùng đơn có thể phải chờ, dù database gần như không bận xử lý query.

Ở PostgreSQL, một transaction còn mở cũng có thể giữ một snapshot hoặc mốc XID khiến công việc `VACUUM` không thể dọn các phiên bản hàng đã chết như bình thường. Tác động còn tùy isolation level, câu SQL và thời gian mở transaction, nhưng **thời gian chờ bên ngoài DB không miễn phí**.

## 3. Chuỗi sự cố khi giữ connection để chờ mạng

Giả sử mỗi thao tác chỉ cần 10 ms SQL nhưng chờ đối tác thanh toán 3 giây giữa hai lệnh SQL. Khi có nhiều request đồng thời, mỗi request có thể mượn một connection trong vài giây. Pool 10 connection sẽ nhanh chóng trở thành điểm nghẽn; request mới phải đợi connection dù CPU của DB chưa đầy tải.

```text
Request A: [BEGIN][SQL]--------------- HTTP WAIT ---------------[SQL][COMMIT]
Connection A: [======================= in use ==============================]

Request B: [BEGIN][SQL]------------------ HTTP WAIT ----------------[COMMIT]
Connection B: [=========================== in use ==========================]

Request C:                [WAIT FOR POOL CONNECTION ...]
```

Hậu quả thường xảy ra theo chuỗi:

1. **Pool exhaustion:** số connection đang mượn tăng cao; thời gian chờ lấy connection vượt ngưỡng `connectionTimeout` của Hikari.
2. **Queueing và độ trễ đuôi:** request mới chờ ở pool, dẫn đến p95/p99 tăng dù query riêng lẻ vẫn nhanh.
3. **Lock contention:** transaction đang chờ HTTP giữ khóa; những transaction khác phải chờ cùng hàng hoặc bảng.
4. **Timeout và retry chồng nhau:** client retry HTTP, service retry DB, đối tác retry webhook, làm số request tăng thêm.
5. **Rủi ro nhất quán:** đối tác đã thực hiện tác động bên ngoài nhưng transaction DB rollback; retry không có idempotency có thể lặp tác động.
6. **Tăng chi phí vận hành:** nhiều DB sessions, stack đang chờ connection, áp lực trên pool và lock manager; tăng `maximumPoolSize` thiếu kiểm soát còn có thể đẩy tải sang database.

Đánh giá thiết kế bằng **thời gian connection được mượn** và **thời gian transaction mở**, không chỉ bằng thời gian chạy SQL. Hai khoảng này liên quan nhưng không đồng nhất tuyệt đối trong mọi implementation.

## 4. Anti-pattern trong Spring: gọi HTTP bên trong @Transactional

Ví dụ dưới đây là **mã minh họa lỗi thiết kế** đặt trong service Spring:

```java
@Service
public class UnsafeCheckoutService {
    private final OrderRepository orders;
    private final PaymentGateway gateway;

    public UnsafeCheckoutService(
            OrderRepository orders, PaymentGateway gateway) {
        this.orders = orders;
        this.gateway = gateway;
    }

    @Transactional
    public long checkout(CheckoutCommand command) {
        long orderId = orders.insertPending(command); // SQL / giữ transaction
        gateway.charge(command.paymentToken(), command.amount()); // HTTP
        orders.markPaid(orderId);                    // SQL
        return orderId;                              // COMMIT sau khi return
    }
}
```

`OrderRepository`, `PaymentGateway` và `CheckoutCommand` là các kiểu minh họa; đoạn này không phải class hoàn chỉnh tự biên dịch. Sai lầm không nằm ở chữ `@Transactional` tự nó: **transaction DB bao quanh một lệnh HTTP có thời gian không chắc chắn**.

Các tình huống khó giải quyết bằng đoạn mã này:

- Đối tác trả lời sau 5 giây: DB transaction có thể giữ connection và lock trong toàn bộ thời gian đó.
- Đối tác báo thành công nhưng `orders.markPaid` hoặc `COMMIT` thất bại: DB rollback **không thể hoàn tác** giao dịch đã chạy ở hệ thống thanh toán.
- Đối tác xử lý thành công nhưng response mất trên mạng: ứng dụng tưởng thất bại và retry, dẫn đến nguy cơ thu tiền hai lần.
- Tăng `@Transactional(timeout = 5)` không làm HTTP tự nhiên thành thao tác nguyên tử với DB; timeout transaction không phải cơ chế chắc chắn để ngắt mọi I/O bên ngoài DB.

**Không được hiểu transaction của một database là distributed transaction.** `@Transactional` quản lý các tài nguyên phù hợp mà transaction manager biết, không tự làm HTTP và database cùng commit/rollback.

## 5. Thiết kế lại bằng cách xác định thứ tự nghiệp vụ

Trước khi di chuyển lời gọi mạng, trả lời hai câu hỏi:

1. Lời gọi đó chỉ **đọc dữ liệu từ hệ thống khác** (giá, hạn mức, quyết định rủi ro), hay nó tạo **side effect** (thu tiền, gửi email, phát message, tạo ticket)?
2. Nghiệp vụ đòi hỏi **một thao tác đồng bộ duy nhất** hay cho phép **trạng thái trung gian, xử lý nền và eventual consistency**?

Không có một mẫu duy nhất đúng cho mọi hệ thống. Có ba nhóm thường gặp.

### 5.1. Lấy dữ liệu từ xa trước transaction

Nếu cần lấy tỷ giá hoặc kiểm tra thông tin đối tác rồi mới lưu DB, có thể gọi từ xa bên ngoài transaction và chỉ mở transaction cho thao tác ghi:

```text
HTTP request
  -> validate input
  -> external service: fetch quote / risk result            (không có DB transaction)
  -> application service: kiểm tra kết quả từ đối tác
  -> [BEGIN -> kiểm tra bất biến DB -> INSERT/UPDATE -> COMMIT]
  -> HTTP response
```

Ví dụ **mã minh họa**:

```java
@Service
public class QuoteOrderService {
    private final QuoteGateway quoteGateway;
    private final ShortOrderWriter writer;

    public QuoteOrderService(
            QuoteGateway quoteGateway, ShortOrderWriter writer) {
        this.quoteGateway = quoteGateway;
        this.writer = writer;
    }

    public long placeOrder(NewOrder input) {
        Quote quote = quoteGateway.fetch(input.productCode()); // network trước TX
        return writer.save(input, quote);                     // TX ngắn
    }
}

@Service
class ShortOrderWriter {
    private final OrderRepository repository;

    ShortOrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long save(NewOrder input, Quote quote) {
        return repository.insert(input, quote);
    }
}
```

Các kiểu `QuoteGateway`, `NewOrder`, `Quote` và `OrderRepository` là interface/model cần khai báo trong ứng dụng; ví dụ tập trung vào vị trí ranh giới transaction. `QuoteOrderService` gọi `writer.save(...)` trên **bean khác**, để Spring proxy áp dụng `@Transactional` đúng cách. Không tự gọi `this.save(...)` rồi giả định interceptor sẽ hoạt động.

**Bẫy dữ liệu cũ:** giữa lúc lấy quote và commit, giá/trạng thái có thể đổi. Cần hạn sử dụng quote, version/ETag, kiểm tra lại điều kiện cập nhật ở DB hoặc quy tắc từ chối phù hợp. Đưa HTTP vào transaction **không** tự bảo đảm trạng thái của một dịch vụ khác luôn nhất quán, vì DB không khóa được đối tác.

### 5.2. Gọi mạng sau khi transaction đã commit

Nếu DB ghi thành công rồi mới cần gửi tín hiệu phụ, có thể thực hiện:

```text
BEGIN -> INSERT/UPDATE -> COMMIT -> HTTP call
```

Cách này giảm thời gian giữ DB transaction. Tuy nhiên nếu process chết ngay sau commit và trước HTTP, tín hiệu có thể **bị mất**. Nếu HTTP thất bại, DB vẫn đã commit. Với thông báo không thiết yếu hoặc chấp nhận được xử lý best-effort, cần công bố rõ chính sách. Với tác động bắt buộc phải gửi cuối cùng, dùng **transactional outbox** hoặc một quy trình đáng tin tương đương.

### 5.3. Transactional outbox cho thao tác “lưu rồi thông báo”

Outbox ghi **bản ghi nghiệp vụ và nhiệm vụ gửi** trong cùng một transaction DB ngắn. Một worker riêng gửi HTTP/message sau khi transaction đó đã commit.

```text
API / application service
    |
    v
 [BEGIN]
    INSERT purchase_orders
    INSERT notification_outbox (PENDING)
 [COMMIT]  ----------------------------------------------------+
    |                                                          |
    +--> trả OrderCreated                                     |
                                                               v
                                             Outbox dispatcher / worker
                                            [claim row + COMMIT ngắn]
                                                               |
                                                    HTTP tới đối tác
                                                               |
                                            [mark DONE + COMMIT ngắn]
```

Điều kiện đảm bảo:

- Nếu tạo đơn thất bại: cả đơn và outbox cùng rollback.
- Nếu tạo đơn thành công: outbox tồn tại bền vững để worker có thể thử gửi sau khi process khởi động lại.
- Worker **không giữ DB transaction trong lúc gọi HTTP**; claim và cập nhật trạng thái là những transaction riêng.
- Nếu gửi thành công nhưng đánh dấu DONE thất bại, sự kiện có thể được gửi lại. Đây là **at-least-once delivery**; bên nhận cần idempotency/deduplication theo event ID, không được quảng cáo là “exactly once” chỉ nhờ outbox.

## 6. Ví dụ Spring Boot: transaction ngắn + outbox + HTTP bên ngoài DB

Ví dụ này dùng **Java 17+**, Spring Boot **3.3.x** (Spring Framework 6.1), Spring JDBC, PostgreSQL và `RestClient`. Để áp dụng, đặt các class trong cùng package `demo.outbox` của một dự án Spring Boot đã cấu hình. Migration dùng cú pháp PostgreSQL; các lệnh tạo bảng chỉ chạy trên database học tập.

### 6.1. Dependency và cơ sở dữ liệu

Trong `build.gradle` của dự án đã cấu hình plugin Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.flywaydb:flyway-core'
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Tệp `src/main/resources/db/migration/V1__orders_and_outbox.sql`:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key VARCHAR(100) NOT NULL UNIQUE,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('CREATED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE notification_outbox (
    event_id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    event_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'DONE')),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_until TIMESTAMPTZ,
    lease_token UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_notification_outbox_pending
    ON notification_outbox (status, available_at, event_id)
    WHERE status <> 'DONE';
```

Bảng `purchase_orders` có `request_key` duy nhất để phân biệt yêu cầu tạo đơn. Bảng `notification_outbox` giữ một event duy nhất với `event_id` ổn định. Trạng thái `IN_FLIGHT` và `lease_until` cho phép worker phục hồi một công việc bị gián đoạn. `lease_token` giúp tránh worker cũ đánh dấu nhầm công việc đã được worker khác nhận lại. Chọn lease dài hơn timeout HTTP và có cơ chế gia hạn nếu tác vụ có thể lâu; dù vậy bên nhận **vẫn phải chống gửi lặp**.

Cột `available_at` phục vụ retry. Index cần được xem lại bằng `EXPLAIN (ANALYZE, BUFFERS)` theo tải thật, đặc biệt khi số bản ghi DONE tăng cao.

### 6.2. Kiểu dữ liệu chung không chứa tài nguyên DB

`src/main/java/demo/outbox/OutboxModels.java`:

```java
package demo.outbox;

import java.math.BigDecimal;
import java.util.UUID;

public final class OutboxModels {
    private OutboxModels() {}

    public record NewOrder(String requestKey, BigDecimal amount) {}

    public record CreatedOrder(long orderId, UUID eventId) {}

    public record OutboxJob(UUID eventId, long orderId, UUID leaseToken) {}

    public record Notification(UUID eventId, long orderId) {}
}
```

Các record là dữ liệu ứng dụng và message gửi đi. Không có `Connection`, `ResultSet` hoặc JDBC driver lộ ra ngoài repository.

### 6.3. Transaction tạo đơn thật ngắn

`src/main/java/demo/outbox/OrderWriteService.java`:

```java
package demo.outbox;

import java.util.UUID;

import demo.outbox.OutboxModels.CreatedOrder;
import demo.outbox.OutboxModels.NewOrder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWriteService {
    private final JdbcTemplate jdbc;

    public OrderWriteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public CreatedOrder create(NewOrder order) {
        Long orderId = jdbc.queryForObject(
                """
                INSERT INTO purchase_orders(request_key, amount, status)
                VALUES (?, ?, 'CREATED')
                RETURNING id
                """,
                Long.class,
                order.requestKey(),
                order.amount()
        );
        if (orderId == null) {
            throw new IllegalStateException("Database did not return order ID");
        }

        UUID eventId = UUID.randomUUID();
        jdbc.update(
                """
                INSERT INTO notification_outbox
                    (event_id, order_id, event_type, status)
                VALUES (?, ?, 'ORDER_CREATED', 'PENDING')
                """,
                eventId,
                orderId
        );

        return new CreatedOrder(orderId, eventId);
    }
}
```

**Ranh giới:** chỉ có hai lệnh SQL được thực thi trong transaction. Không có `RestClient`, `Thread.sleep`, `CompletableFuture.join` hay cuộc gọi tới broker trong `create(...)`. Nếu insert outbox lỗi, transaction rollback cả đơn; nếu commit thành công, công việc gửi đã được lưu bền vững. Đây là **atomicity của DB**, còn phát HTTP diễn ra độc lập sau commit.

`UUID.randomUUID()` tạo khóa idempotency dành riêng cho event. Nếu client retry việc tạo đơn sau khi mất HTTP response, `request_key` duy nhất giúp phát hiện cùng yêu cầu; để API thực sự idempotent còn cần kiểm tra payload lặp, trả kết quả cũ và xử lý xung đột chính sách theo nghiệp vụ. Không tự cho rằng `UNIQUE` biến mọi request thành retry an toàn.

### 6.4. Claim một event trong transaction rất ngắn

`src/main/java/demo/outbox/OutboxStore.java`:

```java
package demo.outbox;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import demo.outbox.OutboxModels.OutboxJob;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class OutboxStore {
    private final JdbcTemplate jdbc;

    public OutboxStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public Optional<OutboxJob> claimOne() {
        UUID token = UUID.randomUUID();
        List<OutboxJob> jobs = jdbc.query(
                """
                WITH candidate AS (
                    SELECT event_id
                    FROM notification_outbox
                    WHERE
                        (status = 'PENDING' AND available_at <= now())
                        OR (status = 'IN_FLIGHT' AND lease_until < now())
                    ORDER BY event_id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE notification_outbox o
                SET status = 'IN_FLIGHT',
                    lease_token = ?,
                    lease_until = now() + interval '60 seconds',
                    attempt_count = attempt_count + 1
                FROM candidate
                WHERE o.event_id = candidate.event_id
                RETURNING o.event_id, o.order_id, o.lease_token
                """,
                (rs, row) -> new OutboxJob(
                        rs.getObject("event_id", UUID.class),
                        rs.getLong("order_id"),
                        rs.getObject("lease_token", UUID.class)
                ),
                token
        );
        return jobs.stream().findFirst();
    }

    @Transactional
    public int markDone(OutboxJob job) {
        return jdbc.update(
                """
                UPDATE notification_outbox
                SET status = 'DONE',
                    lease_token = NULL,
                    lease_until = NULL
                WHERE event_id = ?
                  AND lease_token = ?
                  AND status = 'IN_FLIGHT'
                """,
                job.eventId(),
                job.leaseToken()
        );
    }

    @Transactional
    public int scheduleRetry(OutboxJob job) {
        return jdbc.update(
                """
                UPDATE notification_outbox
                SET status = 'PENDING',
                    available_at = now() + interval '30 seconds',
                    lease_token = NULL,
                    lease_until = NULL
                WHERE event_id = ?
                  AND lease_token = ?
                  AND status = 'IN_FLIGHT'
                """,
                job.eventId(),
                job.leaseToken()
        );
    }
}
```

`claimOne()` dùng PostgreSQL `FOR UPDATE SKIP LOCKED` để nhiều worker không cùng chờ một hàng đang bị claim. Câu `UPDATE ... RETURNING` và thao tác claim nằm trong transaction rất ngắn; **transaction kết thúc trước khi worker gọi HTTP**. `markDone` và `scheduleRetry` cũng mỗi phương thức một transaction ngắn, không dùng lại connection cũ từ `claimOne`.

`lease_token` ngăn việc worker đã mất quyền claim cập nhật trạng thái của lease mới. Nếu kết quả `markDone` hoặc `scheduleRetry` là `0`, cần ghi nhận rằng event đã bị worker khác claim, trạng thái thay đổi hoặc event không còn hợp lệ. Ví dụ cố ý chỉ claim một event mỗi lần để thấy ranh giới; trong vận hành có thể claim theo batch phù hợp, không được ôm connection khi xử lý toàn bộ batch qua HTTP.

**Giới hạn của mẫu rút gọn:** retry hiện là 30 giây cố định và chưa có dead-letter, giới hạn số lần thử, phân biệt 4xx/5xx, khóa heartbeat hay giám sát event kẹt. Production cần backoff có jitter, retry budget, chính sách lỗi không hồi phục, alert và dọn dữ liệu hoàn tất theo retention.

### 6.5. HTTP client có timeout nhưng không có transaction DB

`src/main/java/demo/outbox/PartnerNotificationClient.java`:

```java
package demo.outbox;

import demo.outbox.OutboxModels.Notification;
import demo.outbox.OutboxModels.OutboxJob;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PartnerNotificationClient {
    private final RestClient client;

    public PartnerNotificationClient(
            RestClient.Builder builder, Environment environment) {
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1500);
        factory.setReadTimeout(3000);

        this.client = builder
                .requestFactory(factory)
                .baseUrl(environment.getRequiredProperty("partner.base-url"))
                .build();
    }

    public void send(OutboxJob job) {
        client.post()
                .uri("/notifications")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Idempotency-Key", job.eventId().toString())
                .body(new Notification(job.eventId(), job.orderId()))
                .retrieve()
                .toBodilessEntity();
    }
}
```

Ở đây timeout **connect 1,5 giây** và timeout **read 3 giây** là cấu hình minh họa, phải chỉnh theo SLA của hệ thống đích. `SimpleClientHttpRequestFactory` dùng trong ví dụ để timeout rõ ràng; production có thể chọn HTTP client với pool kết nối, timeout, metrics và resilience policy phù hợp.

Header `Idempotency-Key` chỉ có tác dụng nếu **đối tác thực sự triển khai deduplication** với khóa này. Việc server của ta gửi header không tự bảo đảm tác động phía đối tác được thực thi tối đa một lần. Không gửi thông tin thẻ, token bí mật hoặc dữ liệu nhạy cảm vào payload minh họa.

### 6.6. Worker chạy mạng ngoài transaction

`src/main/java/demo/outbox/OutboxPublisher.java`:

```java
package demo.outbox;

import java.util.Optional;

import demo.outbox.OutboxModels.OutboxJob;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;

@Component
public class OutboxPublisher {
    private static final Logger log =
            LoggerFactory.getLogger(OutboxPublisher.class);

    private final OutboxStore outbox;
    private final PartnerNotificationClient partner;

    public OutboxPublisher(
            OutboxStore outbox, PartnerNotificationClient partner) {
        this.outbox = outbox;
        this.partner = partner;
    }

    @Scheduled(fixedDelay = 1000)
    public void publishOne() {
        Optional<OutboxJob> claimed = outbox.claimOne();
        if (claimed.isEmpty()) {
            return;
        }

        OutboxJob job = claimed.get();

        try {
            partner.send(job); // network: KHÔNG nằm trong DB transaction
        } catch (RestClientException remoteFailure) {
            log.warn(
                    "Remote notification failed for event {}",
                    job.eventId(),
                    remoteFailure
            );
            int updated = outbox.scheduleRetry(job);
            if (updated == 0) {
                log.warn("Retry claim is no longer owned: {}", job.eventId());
            }
            return;
        }

        int updated = outbox.markDone(job);
        if (updated == 0) {
            log.warn("Completion claim is no longer owned: {}", job.eventId());
        }
    }
}
```

`OutboxPublisher.publishOne()` **không** gắn `@Transactional`. Nó gọi các phương thức transaction trên bean `OutboxStore`. Khi `claimOne()` trả về, transaction đã commit. Sau đó `partner.send(...)` có thể mất hàng giây nhưng không mang theo transaction/connection của claim. Xong HTTP, worker gọi `markDone(...)` để mở một transaction riêng, ngắn.

Nếu process chết sau HTTP thành công nhưng trước `markDone`, lease hết hạn và event có thể được gửi lại. Do đó, **bên nhận phải deduplicate** hoặc xử lý message theo cơ chế idempotent. Nếu thời gian HTTP lâu hơn lease, một worker khác có thể claim và gửi lặp trước khi worker đầu kết thúc; timeout và thời gian lease cần đồng bộ, hoặc gia hạn lease khi cần.

Nếu `markDone` bị lỗi DB sau khi HTTP thành công, để job ở trạng thái chờ phục hồi là chấp nhận được trong mô hình at-least-once. Tuyệt đối không kéo transaction của `markDone` lên để bọc cả `partner.send`.

### 6.7. Entry point và cấu hình

`src/main/java/demo/outbox/OutboxApplication.java`:

```java
package demo.outbox;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class OutboxApplication {
    public static void main(String[] args) {
        SpringApplication.run(OutboxApplication.class, args);
    }
}
```

Tệp `src/main/resources/application.yml` (minh họa với biến môi trường):

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      connection-timeout: 2000

partner:
  base-url: ${PARTNER_BASE_URL}
```

Lựa chọn `maximum-pool-size: 10` và `connection-timeout: 2000` chỉ minh họa, **không phải thông số mặc định nên sao chép cho mọi hệ thống**. Pool size phải dựa trên tài nguyên DB, số instance, mức song song thực, query latency và phép đo; tăng vô hạn chỉ dời nút nghẽn sang DB.

`connection-timeout` của Hikari giới hạn **thời gian chờ mượn connection từ pool**, không giới hạn thời gian SQL hay HTTP. Timeout HTTP đặt riêng trong client; giới hạn SQL/lock có thể đặt ở DB hoặc lớp data-access theo chính sách.

Với Gradle Spring Boot đã được cấu hình đúng, có thể chạy:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Cần PostgreSQL khả dụng, biến môi trường `DB_JDBC_URL`, `DB_USER`, `DB_PASSWORD`, `PARTNER_BASE_URL` và endpoint đối tác hỗ trợ hợp đồng `POST /notifications`. Ví dụ là các class có thể biên dịch khi ở đúng project/dependency, không phải chương trình Java thuần chạy chỉ bằng `javac` mà không có thư viện Spring.

Để học luồng, gọi `OrderWriteService.create(...)` từ controller/test, kiểm tra đơn và một outbox event ở `PENDING`, rồi quan sát worker claim → gửi → DONE. Trong môi trường học tập nên dùng mock HTTP server thay cho hệ thống đối tác thật.

## 7. Đọc đúng tình huống thất bại

| Thời điểm xảy ra lỗi | Trạng thái DB | Hành vi mong muốn |
| --- | --- | --- |
| Insert order thành công, insert outbox thất bại | Cả transaction rollback | Không có đơn đã commit mà thiếu outbox |
| Commit transaction tạo đơn thất bại | Không coi là đã thành công; trạng thái thực cần kiểm tra trong trường hợp kết quả commit không rõ | Client/API dùng request key và tra cứu lại theo chính sách |
| Commit thành công, process chết trước khi worker chạy | Có order và event PENDING | Worker có thể xử lý lại khi hệ thống lên |
| Claim thành công, worker chết trước HTTP | Event IN_FLIGHT với lease | Hết lease rồi worker khác nhận lại |
| HTTP thành công, markDone thất bại | Event chưa DONE | Có thể gửi lặp; đối tác phải idempotent |
| HTTP timeout sau khi đối tác đã xử lý | Không biết chắc side effect đã xảy ra | Retry cùng event ID, không phát sinh khóa mới |
| Hai worker cùng hoạt động | `SKIP LOCKED` và claim token giúp phân phối công việc | Vẫn thiết kế cho duplicate do lease/retry |
| Lỗi HTTP vĩnh viễn (ví dụ 400 sai payload) | Không nên retry vô hạn | Phân loại, dead-letter/alert và xử lý vận hành |
| DB down khi worker cần claim | Không lấy được job | Không thực hiện HTTP không có job; retry theo vòng đời worker |

Không giải quyết trường hợp “đã thu tiền ở đối tác nhưng DB rollback” bằng việc giữ database transaction mở trong khi gọi mạng: việc này thường **tăng** thời gian giữ tài nguyên và vẫn không mang lại commit nguyên tử xuyên hệ thống.

## 8. Các mẫu khác và khi nào dùng

### 8.1. Best-effort sau commit

Có thể dùng Spring `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` cho công việc phụ có thể mất mà vẫn chấp nhận được, hoặc để đánh thức worker outbox. Listener chỉ chạy sau khi transaction commit thành công trong flow phù hợp. Nhưng event chỉ nằm trong bộ nhớ sẽ **mất nếu process chết sau commit mà listener chưa xử lý**; vì vậy đừng dùng listener như hàng đợi bền vững thay outbox.

Khi listener sau commit muốn ghi thêm vào DB, phải chú ý tài nguyên transaction cũ có thể vẫn được thread bind; Spring docs khuyến cáo dùng transaction mới phù hợp như `REQUIRES_NEW` cho tác động ghi mới. Đừng vô tình chạy một transaction lâu trong callback sau commit.

### 8.2. Sử dụng message broker

Thay HTTP bằng Kafka/RabbitMQ không tự giải quyết atomicity giữa “commit SQL” và “publish message”. Nếu publish khi transaction đang mở, broker chậm vẫn giữ transaction. Nếu publish sau commit, có khoảng trống mất message. Outbox + relay tới broker là một chiến lược; cũng có thể dùng cơ chế tích hợp giao dịch/CDC có ngữ nghĩa đã được chứng minh theo hạ tầng thực tế.

### 8.3. Saga/workflow cho nghiệp vụ nhiều dịch vụ

Với payment + inventory + shipment, một database transaction cục bộ không đủ để điều phối nhiều dịch vụ độc lập. Dùng trạng thái ứng dụng như `PENDING_PAYMENT`, `CONFIRMED`, `FAILED`, bù trừ có kiểm soát và idempotency ở từng bước. Mỗi bước cập nhật DB trong transaction ngắn, giao tiếp mạng diễn ra ở ngoài. Trạng thái trung gian là một phần hợp đồng nghiệp vụ, không phải lỗi kiến trúc.

### 8.4. Gọi mạng trước transaction không luôn đủ

Giá/quote có thể thay đổi giữa “đọc từ xa” và “ghi DB”. Kiểm tra lại version/expiry, dùng conditional update ở DB hoặc thiết kế trạng thái cần xác nhận sau. Nếu hệ thống đòi hỏi tính nguyên tử xuyên DB và dịch vụ khác, cần xác định lại ranh giới nghiệp vụ, giao thức đảm bảo hoặc workflow bù trừ; `@Transactional` một mình không đạt được điều đó.

### 8.5. Không khắc phục bằng propagation sai cách

Đặt `@Transactional(propagation = Propagation.NOT_SUPPORTED)` quanh HTTP bên trong một transaction ngoài chỉ **suspend transaction về mặt quản lý**, không bảo đảm connection của transaction ngoài đã trả về pool; nó có thể tiếp tục bị giữ để resume. Gọi `REQUIRES_NEW` để “tách” phần HTTP còn có thể tăng số connection cần thiết nếu một transaction ngoài vẫn giữ tài nguyên. Cách chắc chắn là **kết thúc transaction ngoài trước khi bắt đầu network call**, hoặc thiết kế thành hai service/worker có commit boundary rõ.

## 9. Tại sao timeout không thể thay thế transaction ngắn?

Timeout bảo vệ biên thời gian nhưng không sửa thứ tự công việc.

| Timeout | Giới hạn điều gì | Không giới hạn điều gì |
| --- | --- | --- |
| HTTP connect timeout | Thời gian thiết lập kết nối tới remote | Toàn bộ thời gian xử lý remote |
| HTTP read/response timeout | Chờ dữ liệu/response theo client implementation | Độ dài transaction nếu HTTP nằm trong transaction |
| Hikari `connectionTimeout` | Chờ lấy connection từ pool | Thời gian một request đã mượn connection |
| Spring `@Transactional(timeout = ...)` | Timeout logic của transaction tùy transaction manager/driver và thao tác được quản lý | Không đảm bảo ngắt mọi `Thread.sleep`, HTTP hoặc remote side effect |
| PostgreSQL `statement_timeout` | Giới hạn thời gian chạy câu SQL phía server | Chờ HTTP bên Java giữa các câu SQL |
| PostgreSQL `lock_timeout` | Giới hạn thời gian chờ lấy lock | Chờ network ngoài DB |
| PostgreSQL `idle_in_transaction_session_timeout` | Ngắt session đang idle trong một transaction quá lâu | Thiết kế lại transaction; có thể khiến request thất bại và connection bị hủy |

**Quan trọng:** nếu set `idle_in_transaction_session_timeout` quá thấp, DB có thể ngắt cả những request hợp lệ đang xử lý lâu; pool/ứng dụng phải hồi phục kết nối lỗi. Đây là “guardrail” vận hành, không phải lý do để giữ HTTP trong transaction. Cân nhắc theo DBMS/phiên bản và cấu hình cụ thể.

Trong Spring JDBC/JPA, timeout transaction cũng không nên bị nhầm với deadline tổng của request. Ngay cả khi DB rollback do timeout, một yêu cầu HTTP đã gửi sang đối tác có thể hoàn thành và tạo side effect. Luôn thiết kế idempotency, cancellation và retry đúng ý nghĩa nghiệp vụ.

## 10. Các nguồn giữ connection lâu dù không gọi HTTP trực tiếp

### 10.1. Stream ResultSet hoặc dữ liệu rất lớn

Dùng `JdbcTemplate.queryForStream(...)` có thể giữ `ResultSet`, `Statement` và connection đến khi stream được **đóng**. Ví dụ sai là trả `Stream` chưa đóng từ repository lên controller để serialize JSON dần trong một response chậm. DB connection sẽ gắn với tốc độ network/client.

Ưu tiên:

- Đọc một trang có giới hạn, map sang DTO rồi đóng tài nguyên trước khi gửi HTTP response.
- Nếu dữ liệu lớn và cần stream thật, chủ động quản lý lifetime, backpressure, cursor và timeout; không để stream DB mặc định sống theo tốc độ đường truyền tới browser.
- Với JDBC thủ công, luôn dùng `try-with-resources` cho `Connection`, `PreparedStatement`, `ResultSet`; với Spring, tuân theo cơ chế đóng stream/transaction của API đang dùng.

### 10.2. JPA lazy loading và Open Session in View

Khi serialize entity có quan hệ lazy, một web response có thể phát sinh thêm SQL ngoài ranh giới service dự kiến. Spring Boot cho ứng dụng web JPA có cơ chế Open EntityManager in View (OSIV) tùy cấu hình, giữ persistence context mở qua request; điều này không đồng nghĩa luôn giữ cùng physical connection suốt request nhưng có thể gây truy vấn muộn, N+1 và khó dự đoán lifecycle.

Với REST API, cân nhắc `spring.jpa.open-in-view=false` và chuẩn bị DTO/projection trong service với fetch plan rõ ràng. Đây là một lựa chọn kiến trúc cần kiểm thử, không phải công tắc chữa mọi connection leak.

### 10.3. Xử lý CPU/blocking bên trong transaction

Dù không có network, các thao tác như tạo PDF, đọc file lớn, nén dữ liệu, tính toán tốn CPU hoặc chờ mutex ngay giữa hai SQL cũng kéo dài transaction. Tách phần chuẩn bị dữ liệu khỏi transaction khi có thể; chỉ giữ các thao tác cần nhất quán trong cùng commit.

### 10.4. Transaction xuyên vòng lặp nhiều bản ghi

`@Transactional` quanh toàn bộ vòng lặp có hàng nghìn item, mỗi item gọi DB hoặc HTTP, có thể giữ connection/lock rất lâu. Xác định mức atomicity thật cần: theo item, theo batch nhỏ, hay toàn tác vụ; dùng chunking, queue và idempotency khi phù hợp. Không tự tách một giao dịch nghiệp vụ bắt buộc nguyên tử thành nhiều transaction chỉ để nhanh hơn.

### 10.5. Thread hoặc coroutine ngoài ranh giới transaction

Với transaction imperative của Spring, tài nguyên thường được bind theo thread; gọi `CompletableFuture.supplyAsync(...)` hoặc mở thread mới bên trong `@Transactional` **không tự truyền transaction sang thread mới**. Điều này vừa có thể phá kỳ vọng nhất quán, vừa tạo cơ hội chờ `join()` trong khi transaction gốc còn mở. Reactive transaction với `ReactiveTransactionManager` sử dụng Reactor context, không dựa theo ThreadLocal theo cùng cách; không áp dụng máy móc quy tắc JDBC imperative cho R2DBC.

## 11. Quan sát connection pool và transaction trong vận hành

### 11.1. Metric nên theo dõi cùng lúc

Trong Spring Boot Actuator + Micrometer + HikariCP, những metric phổ biến gồm (tên thực tế phụ thuộc version và registry):

- `hikaricp.connections.active`: số connection được mượn.
- `hikaricp.connections.idle`: connection đang rảnh trong pool.
- `hikaricp.connections.pending`: số thread đang chờ connection.
- `hikaricp.connections.timeout`: số lần không mượn được connection trong hạn.
- Thời gian acquire/usage nếu đã bật instrumentation; p95/p99 của request, thời gian transaction và thời gian gọi đối tác.

Một bức tranh gợi ý: SQL latency ổn định, remote latency tăng, `active` gần `maximumPoolSize`, `pending` tăng và DB có nhiều session `idle in transaction`. Mẫu này **gợi ý** transaction đang ôm connection khi chờ việc ngoài SQL; cần xác minh bằng trace và DB state trước khi kết luận.

### 11.2. PostgreSQL pg_stat_activity

Trên môi trường thử nghiệm hoặc với quyền quan sát phù hợp:

```sql
SELECT
    pid,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Quan sát transaction già, `idle in transaction` và những session chờ lock. `pg_stat_activity` chỉ là **snapshot tức thời**; không đủ để chứng minh request nào gây chậm nếu thiếu request ID/tracing. Cột `query` có thể chứa dữ liệu nhạy cảm nên ví dụ cố ý không lấy. Trong hệ thống thật cần công cụ liên kết HTTP trace ↔ transaction ↔ DB session theo chính sách quan sát và phân quyền.

Có thể xem session chờ lock:

```sql
SELECT
    pid, state, wait_event_type, wait_event,
    now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
  AND datname = current_database();
```

Một session chờ lock không tự nói ai đang giữ lock; dùng `pg_blocking_pids(pid)` và catalog PostgreSQL khi cần phân tích quan hệ blocker/waiter. Không tùy tiện `pg_terminate_backend` trên production chỉ vì thấy session già; phải tìm owner và chính sách vận hành.

### 11.3. Hikari leak detection

Hikari `leakDetectionThreshold` có thể ghi log stack trace khi connection được mượn quá lâu, hỗ trợ điều tra. Đây là **cảnh báo thời gian checkout**, không khẳng định có leak vĩnh viễn; transaction hợp lệ nhưng lâu cũng có thể bị cảnh báo. Chỉ bật ngưỡng hợp lý và có thời hạn khi điều tra, đọc log theo kiểm soát dữ liệu nhạy cảm; sửa code giữ connection lâu thay vì chỉ tăng ngưỡng để im cảnh báo.

### 11.4. Đo đúng đoạn thời gian

Khi trace một request, phân biệt:

```text
request total
  ├── validation / auth
  ├── external call latency
  ├── transaction time
  │     ├── pool acquisition
  │     ├── SQL execution
  │     ├── waiting for locks
  │     └── commit/rollback
  └── response serialization
```

Nếu network call lồng **bên trong transaction**, hai khoảng thời gian chồng nhau. Sau khi refactor, mong đợi transaction time giảm, pool pending giảm và tần suất lock wait ít hơn. Chỉ tăng `maximumPoolSize` có thể che dấu nút thắt trong thời gian ngắn nhưng không làm transaction ngắn đi.

## 12. Kiểm thử ranh giới và lỗi phục hồi

### 12.1. Test đúng đặc tính mong muốn

Với ví dụ outbox, nên có các kiểm thử sau:

1. **Atomicity:** cố tình làm insert outbox thất bại; xác minh không có purchase order nào được commit từ request đó.
2. **Claim tách transaction:** sau khi `OutboxStore.claimOne()` trả về, fake HTTP client được gọi ở thread worker **không còn transaction imperative active**.
3. **Timeout của đối tác:** fake server giữ response lâu hoặc đóng kết nối; worker không giữ transaction DB mở, event được chuyển về PENDING để retry.
4. **Crash sau gửi:** giả lập HTTP thành công nhưng `markDone` lỗi; khi lease hết, event được claim lại với cùng `event_id`.
5. **Nhiều worker:** chạy claim đồng thời; một event tại một thời điểm chỉ có một lease hợp lệ; cập nhật bằng lease token cũ phải ảnh hưởng 0 hàng.
6. **Idempotency bên nhận:** gửi cùng `Idempotency-Key` hai lần; hệ nhận chỉ tạo một tác động nghiệp vụ theo hợp đồng đã thỏa thuận.
7. **Kiểm tra tải:** mô phỏng remote chậm, so sánh active/pending pool trước và sau refactor bằng metrics/tracing.

Đối với transaction JDBC, sử dụng integration test bằng PostgreSQL thật hoặc Testcontainers PostgreSQL để đánh giá `FOR UPDATE SKIP LOCKED`, lease và isolation đúng dialect. H2 hoặc database giả có thể không mô phỏng giống PostgreSQL các câu lệnh và khóa.

### 12.2. Guard đơn giản để phát hiện gọi remote trong transaction

Ở client HTTP imperative, có thể thêm một assertion dùng trong test/giám sát:

```java
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class TransactionGuard {
    private TransactionGuard() {}

    public static void requireNoActiveTransaction() {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException(
                    "Remote HTTP call started inside a DB transaction"
            );
        }
    }
}
```

Gọi `TransactionGuard.requireNoActiveTransaction()` **ngay trước lệnh gửi HTTP** trong test hoặc tại adapter đã chủ động quy định “không được gọi trong transaction”. Đây là kiểm tra trạng thái transaction Spring **trên thread hiện tại**; nó không chứng minh không có connection đang bị giữ ở thread khác, không áp dụng thay cho quản trị transaction reactive và không thay thế integration/performance test.

### 12.3. Kiểm thử thời điểm và dữ liệu trả về

Đừng chỉ kiểm tra exception. Với outbox, xác minh trạng thái DB trước/sau commit, tên event và idempotency key, cũng như thời điểm remote call thực sự xảy ra. Đặc biệt, trạng thái DONE **không** thể được coi là thành công nếu đối tác chưa xác nhận theo giao thức, và HTTP timeout không chứng minh đối tác chưa thực hiện side effect.

## 13. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Gọi HTTP ở giữa hai câu SQL trong `@Transactional` | Giữ transaction, connection và lock khi chờ mạng | Di chuyển HTTP ra ngoài; dùng outbox/workflow nếu cần |
| Tăng pool từ 10 lên rất lớn ngay khi timeout | DB giới hạn connections, lock contention vẫn còn | Đo transaction/checkout time; sửa lifetime trước |
| Tin `@Transactional(timeout)` tự ngắt HTTP | Timeout DB không đồng nghĩa HTTP cancel | Timeout riêng cho HTTP và ranh giới transaction ngắn |
| Gửi HTTP ngay sau commit nhưng yêu cầu không mất event | Crash gap giữa commit và gửi | Lưu outbox cùng transaction |
| Nghĩ outbox bảo đảm “exactly once” | Crash/lease/retry gây duplicate delivery | Event ID ổn định + dedupe bên nhận |
| Dùng `REQUIRES_NEW` bọc HTTP trong transaction ngoài | Outer transaction có thể vẫn giữ connection | Commit transaction ngoài trước |
| Gọi `this.save()` vào method `@Transactional` khác cùng bean | Proxy Spring thông thường bị bypass | Tách bean/đi qua proxy hoặc dùng `TransactionTemplate` |
| Bọc file upload/serialization/CPU nặng trong TX | Transaction dài dù không có SQL | Chuẩn bị/stream ở ngoài khi nghiệp vụ cho phép |
| Trả `Stream<ResultSet>` lên controller | Connection gắn với tốc độ response/client | Materialize trang nhỏ, đóng stream đúng lifecycle |
| Chỉ đo thời gian query, bỏ transaction duration | Không nhìn thấy chờ HTTP, lock, pool | Trace từ request qua transaction, pool và remote |
| `readOnly=true` được xem là “không giữ tài nguyên” | Transaction đọc vẫn có lifecycle/connection | Giữ read transaction ngắn, tránh xử lý dư trong scope |
| Retry charge với khóa mới sau timeout | Không biết remote đã xử lý chưa | Idempotency key giữ nguyên, reconciliation |
| Bắt lỗi rồi trả bình thường trong transaction | Rollback có thể không xảy ra như mong đợi | Chọn propagation, rollback policy và xử lý lỗi rõ |
| HTTP ngoài TX nhưng dùng quote cũ vô hạn | Dữ liệu bên ngoài thay đổi trước DB write | TTL/version/conditional update, chính sách stale data |

## 14. Bài tập thực hành

**Bài 1 — phân tích timeline.** Một service gọi `UPDATE account`, chờ REST API 4 giây rồi `INSERT audit`, tất cả trong `@Transactional`. Liệt kê những tài nguyên có thể bị giữ trong 4 giây và giải thích vì sao chỉ tối ưu `UPDATE` từ 8 ms xuống 2 ms có thể không giải quyết pool exhaustion.

**Bài 2 — chọn mẫu.** Với ba yêu cầu (a) lấy tỷ giá để hiển thị; (b) tạo đơn rồi bắt buộc gửi thông báo; (c) thu tiền, xuất kho, tạo vận đơn ở ba dịch vụ, chọn lần lượt ranh giới transaction và một trong những mẫu: gọi trước transaction, outbox, Saga/workflow. Nêu caveat của tính nhất quán cho từng trường hợp.

**Bài 3 — sửa code.** Cho phương thức `@Transactional` có các dòng `repository.save()`, `restClient.post()`, `repository.markSent()`. Thiết kế lại thành transaction ghi entity + outbox, worker claim/commit, HTTP bên ngoài, markDone/commit. Nêu hành vi khi worker crash giữa HTTP và markDone.

**Bài 4 — giám sát.** Trong một biểu đồ, `hikaricp.connections.active` gần ngưỡng tối đa, `pending` tăng, SQL latency thấp nhưng remote p99 lớn. Đề xuất các bước xác minh từ trace tới `pg_stat_activity`; phân biệt connection đang mượn và connection idle trong pool.

**Bài 5 — kiểm thử.** Viết test với fake HTTP server có timeout, Testcontainers PostgreSQL và hai worker, xác minh không gửi trong transaction, không mất outbox sau commit, duplicate delivery có cùng event ID và không phá bất biến nghiệp vụ.

**Gợi ý đáp án:** Bài 1 có thể giữ transaction, borrowed connection và lock từ UPDATE tới COMMIT; tăng tốc query ít tác động lên 4 giây chờ. Bài 2: (a) gọi remote ngoài DB transaction, chú ý TTL; (b) outbox; (c) workflow/Saga kèm idempotency và bù trừ. Bài 3: bảo đảm database atomicity cho entity/outbox và at-least-once cho gửi; không hứa exactly-once. Bài 4: xem checkout/transaction time cùng remote traces, phân biệt Hikari idle với PostgreSQL idle in transaction. Bài 5: kiểm tra trạng thái database và tác động thực tế, không chỉ việc phương thức ném exception.

## 15. Checklist trước khi đưa vào production

- Mỗi use case đã xác định rõ **bất biến nào thực sự phải nằm trong cùng transaction** chưa?
- Có gọi HTTP/RPC/broker, chờ future, sleep, file I/O, CPU nặng, stream response hoặc chạy vòng lặp dài trong `@Transactional` không?
- Các thao tác ngoài DB có timeout, retry budget và idempotency key rõ ràng không?
- Nếu cần lưu DB rồi bắt buộc phát sự kiện, có durable outbox hoặc cơ chế đảm bảo tương đương không?
- Worker có commit claim **trước** khi gọi network và mở transaction khác để markDone không?
- Lease, retry, dead-letter, phân loại lỗi vĩnh viễn và deduplication có được thiết kế và thử nghiệm không?
- Pool sizing có dựa trên tải thật, giới hạn DB và active/pending metrics thay vì chỉ tăng theo cảm tính không?
- Có thể đo transaction duration, connection checkout time, lock wait, remote latency và quan sát `idle in transaction` không?
- Các ngoại lệ, rollback, self-invocation và propagation đã được thử bằng integration test chưa?
- API đã công bố rõ trạng thái xử lý đồng bộ/bất đồng bộ, trường hợp đang chờ và retry an toàn chưa?

**Kết luận:** tối ưu connection không chỉ là tăng số connection. Cách bền vững là **bắt đầu transaction khi đã sẵn sàng ghi dữ liệu, thực hiện SQL cần thiết, commit sớm rồi mới chờ mạng ở một bước tách biệt**. Với tác vụ gửi không được mất sau commit, transactional outbox cho phép transaction ngắn, worker retry bền vững và giao diện có hợp đồng trạng thái rõ ràng. Mỗi phần vẫn phải xử lý duplicate, timeout và eventual consistency đúng ngữ nghĩa nghiệp vụ.

## Tài liệu tham khảo

- Spring Framework — Declarative transaction management, `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction interceptor và thread-bound transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Transaction-bound events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework — JDBC `JdbcTemplate`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — REST Client: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- HikariCP — Pool configuration (`connectionTimeout`, `maximumPoolSize`, `leakDetectionThreshold`): https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby
- PostgreSQL — Client connection defaults and `idle_in_transaction_session_timeout`: https://www.postgresql.org/docs/current/runtime-config-client.html
- PostgreSQL — `pg_stat_activity`: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL — `SELECT ... FOR UPDATE SKIP LOCKED`: https://www.postgresql.org/docs/current/sql-select.html
