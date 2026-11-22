# Kiểm thử khả năng phục hồi khi cơ sở dữ liệu ngắt kết nối trong JPA

Một ứng dụng sử dụng **Jakarta Persistence (JPA)** có thể hoạt động ổn định trong hàng nghìn requests, rồi đột ngột không thể kết nối cơ sở dữ liệu vì restart, lỗi mạng, failover, firewall, pool giữ connection cũ hoặc database tạm thời không nhận kết nối. Đối với thao tác đọc, ứng dụng có thể trả lỗi tạm thời rồi thực hiện lại; với thao tác ghi, vấn đề khó hơn rất nhiều: **mất kết nối không luôn có nghĩa giao dịch đã rollback**.

Xét thao tác giữ hàng:

```java
@Transactional
public ReservationResult reserve(ReserveCommand command) {
    StockItem item = stockRepository.findForUpdate(
        command.sku()
    );

    item.reserve(command.quantity());

    reservationRepository.save(
        new StockReservation(
            command.requestId(),
            command.sku(),
            command.quantity()
        )
    );

    return new ReservationResult(command.requestId());
}
```

Nếu database ngắt kết nối lúc `flush()` hoặc ngay khi `COMMIT` được gửi, những câu hỏi sau quyết định tính đúng đắn:

- Giao dịch đã rollback hay commit mà ứng dụng không nhận được xác nhận?
- Persistence context và các managed entities có còn đáng tin?
- Connection trong pool có được loại bỏ và thay mới không?
- Caller có thể gửi lại request mà không giữ hàng hai lần không?
- Readiness/liveness có phản ánh chính xác tình trạng dịch vụ?
- Khi DB phục hồi, ứng dụng có tự mở kết nối mới hay cần restart?
- Tests có thực sự cắt đường mạng lúc đang thao tác, hay chỉ mock một exception ở repository?

Bài thuộc **Data Persistence Relational Access ORM JPA**, chương **Vận hành và di trú**, với đề mục trực tiếp **“Kiểm thử khả năng phục hồi khi cơ sở dữ liệu ngắt kết nối”**.

Sau bài học, bạn có thể:

1. Phân loại sự cố theo thời điểm trước kết nối, trong query, trong transaction và tại commit.
2. Hiểu vì sao exception không đủ chứng minh giao dịch đã rollback.
3. Thiết kế lifecycle xử lý `EntityManager`, transaction và connection pool sau failure.
4. Phân biệt lỗi kết nối tạm thời với lỗi authentication, SQL syntax, constraint hoặc deadlock.
5. Xây retry policy có giới hạn, có backoff, đặt **ngoài transaction**.
6. Dùng **idempotency key** và truy vấn đối soát để xử lý commit outcome không rõ.
7. Kiểm thử bằng PostgreSQL Testcontainers, network proxy/fault injection và Spring Boot hoặc RESOURCE_LOCAL.
8. Xác minh rollback/commit sau phục hồi với persistence context mới.
9. Test pool tự phục hồi, readiness/liveness, timeout budget, retry storms và failover.
10. Đo khả năng phục hồi bằng metrics, logs, alarms và runbook vận hành.

**Nguyên tắc trung tâm:** *Một connection failure là sự cố của toàn bộ đơn vị công việc, không phải tín hiệu để tiếp tục dùng cùng EntityManager. Sau lỗi cần rollback/cleanup theo ownership, tạo transaction/context mới khi thích hợp, và xác định kết quả của thao tác trước khi retry bất kỳ write nào có thể trùng lặp.*

---

## 1. “Cơ sở dữ liệu ngắt kết nối” có nhiều dạng

Thông báo “Cannot connect to database” không diễn tả đầy đủ sự cố. Các nguyên nhân có thể là:

- Database process dừng hoặc restart.
- Primary node chuyển sang standby trong quá trình failover.
- DNS hoặc routing đang cập nhật.
- Network connection reset, timeout hoặc packet loss.
- Firewall/network policy chặn traffic mới.
- Proxy/load balancer đóng idle connections.
- PostgreSQL đóng connection vì admin shutdown hoặc maintenance.
- Connection pool cạn vì nhiều transactions chậm.
- TLS handshake/certificate validation thất bại.
- Tài khoản DB bị thu hồi hoặc token hết hạn.
- DB từ chối quá nhiều connections.
- Storage/DB server quá tải khiến query timeout.

**Không được gom mọi lỗi trên vào một nhóm “retry ngay là xong”.** Một password sai không tự đúng lại sau 100 lần thử; database đang xử lý chậm có thể bị đẩy vào outage nghiêm trọng hơn bởi retry storm.

### 1.1. Ma trận theo vị trí lỗi

| Điểm xảy ra | App đã có connection? | Ghi dữ liệu có thể đã chạy? | Rủi ro chính |
| --- | --- | --- | --- |
| Trước khi lấy connection | Chưa | Chưa ở attempt này | Timeout, readiness, retry vô ích |
| Khi mở kết nối/TLS/auth | Chưa usable | Chưa ở attempt này | Credential, certificate, endpoint |
| Trong SELECT | Có | Có thể chưa hoặc đã có writes trước đó | Transaction mất hiệu lực, stale state |
| Trong INSERT/UPDATE/DELETE | Có | Có thể đã thực thi một phần trước lỗi | Rollback, SQL/batch outcome |
| Trong `flush()` | Có | Có thể đã gửi nhiều statements | Failed persistence context |
| Khi gửi/nhận `COMMIT` | Có hoặc vừa mất | **Có thể đã commit** | Ambiguous transaction outcome |
| Sau khi commit đã xác nhận | Transaction xong | Đã commit | Reply/event delivery có thể lỗi |
| Sau failover | Kết nối cũ thường hỏng | Tùy transaction trước | New primary, DNS, replica lag |

### 1.2. Ba khái niệm không được đánh đồng

```text
Network connectivity
        ≠
Transaction outcome
        ≠
Business operation outcome
```

Một connection mới thành công không chứng minh request cũ rollback. Một exception ở repository không chứng minh database chưa nhận SQL. Một API trả HTTP 500 không chứng minh đơn hàng chưa được tạo.

---

## 2. Các lớp tham gia phục hồi

```text
HTTP client / message consumer
            |
            v
Idempotency / business command
            |
            v
Spring transaction interceptor
hoặc application RESOURCE_LOCAL boundary
            |
            v
EntityManager / persistence context
            |
            v
Hibernate/EclipseLink / JDBC
            |
            v
HikariCP / DataSource / connection pool
            |
            v
JDBC driver / TLS / network proxy
            |
            v
Primary database / replica / storage
```

Mỗi lớp có trách nhiệm:

| Lớp | Nên làm gì |
| --- | --- |
| API | Deadline, request ID, error contract, idempotency key |
| Business service | Re-evaluate invariants khi retry |
| Transaction manager | Begin/commit/rollback/cleanup |
| EntityManager | Theo dõi managed state; không thread-safe |
| Pool | Cấp/reuse/loại bỏ connections; không quyết định business idempotency |
| JDBC driver | Truyền SQL/protocol, timeout, phát hiện lỗi kết nối |
| DB | ACID, locks, constraints, commit/rollback |
| Orchestration | Readiness, rollout, restart/failover |
| Monitoring | Ghi nhận outage, latency, failure/recovery |

Bật retry ở JDBC driver, pool, repository, service và API gateway cùng lúc có thể khiến một request tạo ra **nhiều cấp retry lồng nhau**. Phải có một **retry owner** rõ ràng.

---

# Phần I — Semantics của lỗi và transaction

## 3. Mất kết nối trước khi bắt đầu transaction

Ví dụ:

```java
EntityManager em = emf.createEntityManager();

em.getTransaction().begin();
```

Tùy provider/pool, connection vật lý có thể được lấy ngay khi bắt đầu transaction hoặc chỉ khi cần thực thi SQL. Vì vậy lỗi có thể xuất hiện ở:

```java
em.getTransaction().begin();
```

hoặc:

```java
em.find(StockItem.class, "SKU-A");
```

### 3.1. Điều có thể biết

Nếu attempt chưa có bất kỳ SQL write nào và chưa thực hiện external side effect, nó thường an toàn hơn để retry **đọc** hoặc **bắt đầu unit of work mới**, nhưng vẫn cần xác minh điều kiện nghiệp vụ và idempotency.

### 3.2. Không giữ request vô hạn

Nếu pool không lấy được connection, request cần có deadline và thông báo lỗi có kiểm soát, ví dụ HTTP 503 khi database là dependency thiết yếu.

### 3.3. Readiness có thể thất bại

Nếu dịch vụ không thể hoàn thành nghiệp vụ cốt lõi khi DB down, readiness có thể chuyển sang không sẵn sàng. Điều này không nhất thiết có nghĩa liveness phải buộc restart liên tục.

---

## 4. Mất kết nối trong lúc query

Ví dụ:

```java
@Transactional(readOnly = true)
public StockDto load(String sku) {
    StockItem item = em.find(StockItem.class, sku);
    return new StockDto(item.getSku(), item.getAvailable());
}
```

Nếu connection reset trong khi chờ kết quả SELECT:

- Driver có thể ném `SQLException` với SQLSTATE nhóm `08`.
- Provider bọc trong `PersistenceException` hoặc exception riêng.
- Spring có thể dịch thành `DataAccessException`.
- Transaction có thể bị rollback-only.
- Context/connection đang lỗi không nên được tái sử dụng.

### 4.1. Lỗi SELECT có thể retry nhưng cần điều kiện

Một thao tác đọc thuần túy, không có external side effect, thường là ứng viên retry khi lỗi thực sự transient. Tuy nhiên:

- Transaction mới có thể thấy dữ liệu khác theo isolation.
- Read-only transaction của framework không đồng nghĩa ứng dụng không làm side effect ngoài DB.
- Retry có thể vượt deadline người dùng.
- Một query tốn tài nguyên có thể làm outage nặng hơn.
- Authorization/tenant scoping phải được áp lại.

### 4.2. Không tiếp tục query trong transaction lỗi

Sai:

```java
try {
    em.createQuery("SELECT ...").getResultList();
} catch (PersistenceException ex) {
    return em.createQuery("SELECT ...").getResultList();
}
```

Trong nhiều failure modes, transaction hoặc JDBC session đã mất hiệu lực. Cần kết thúc attempt và mở transaction/context mới nếu retry được phép.

---

## 5. Mất kết nối khi flush

```java
em.getTransaction().begin();

StockItem item =
    em.find(StockItem.class, sku);

item.reserve(3);

em.persist(new StockReservation(...));

em.flush(); // Connection lost here.
```

`flush()` gửi các thay đổi đang chờ xuống database; nó **không commit**.

Một số SQL có thể đã được DB xử lý trong transaction, trong khi các SQL khác chưa thực hiện. Không suy từ exception rằng các entities trong Java quay về giá trị ban đầu.

### 5.1. L1 cache sau failure không đáng tin để retry

`StockItem.available` trong Java có thể đã giảm. Nếu transaction rollback, database giữ số lượng cũ nhưng object Java vẫn có thể chứa giá trị đã mutate.

### 5.2. Không thử sửa bằng clear/refresh

```java
em.clear();
em.refresh(item);
```

không phải cách reset một transaction đã lỗi. `clear()` detach, còn `refresh()` có thể cần SQL trên connection không còn usable.

### 5.3. Phương án an toàn

```text
Failed flush
    |
    v
Stop current business work
    |
    v
Rollback if possible
    |
    v
Close/discard affected context
    |
    v
Classify error
    |
    v
New transaction/context + reload state
    |
    v
Retry only when policy permits
```

---

## 6. Mất kết nối ngay quanh COMMIT

Đây là trường hợp quan trọng nhất.

```text
Application                        Database
     |                                |
     |------ COMMIT ----------------->|
     |                                | Commit có thể thành công
     X       Connection lost          |
     |                                |
     | Không nhận ACK                |
```

Có ít nhất ba kết quả có thể quan sát:

1. Database chưa nhận hoặc chưa thực thi commit và transaction bị rollback.
2. Database đã commit, nhưng ACK không đến ứng dụng.
3. Ứng dụng chưa đủ thông tin để khẳng định một trong hai outcome.

**Exception từ `commit()` không tự chứng minh rollback**. Một kết nối bị mất có thể khiến ứng dụng không biết server đã commit hay chưa.

### 6.1. Không gọi rollback rồi mặc định transaction đã bị undo

Nếu database đã commit, một lần `rollback()` sau đó không thể đảo ngược commit cũ.

Nếu connection hoàn toàn mất, rollback cũng có thể thất bại hoặc không có khả năng gửi tới server.

### 6.2. Không retry write mù quáng

Sai:

```java
try {
    createReservation(command);
} catch (Exception ex) {
    createReservation(command);
}
```

Nếu attempt đầu đã commit, lần gọi thứ hai có thể trừ stock hai lần hoặc tạo hai reservations.

### 6.3. Kết quả cần được đối soát

Định danh nghiệp vụ bền vững như `requestId`/idempotency key giúp kiểm tra committed state bằng **connection và transaction mới** sau khi DB phục hồi.

Nếu chưa thể truy vấn DB, outcome vẫn là **unknown**, không tự đổi thành “failed”.

---

## 7. Mất phản hồi HTTP sau khi DB đã commit

Đây là failure mode khác với DB outage:

```text
Client POST /reservations
         |
         v
Service commits DB successfully
         |
         X HTTP response lost
         |
         v
Client retries same request
```

Ngay cả khi database **không bị outage**, client vẫn có thể thực hiện cùng business command hai lần.

Vì vậy idempotency không chỉ dành cho DB commit ambiguity; nó là hợp đồng đáng cân nhắc cho các endpoint ghi không thể an toàn khi lặp.

---

## 8. SQLSTATE và exception wrappers

Một cause chain có thể trông như:

```text
Spring DataAccessException
    -> Hibernate JDBCConnectionException
        -> SQLException(SQLSTATE 08006)
```

Hoặc lỗi có thể xuất hiện dưới:

```text
PersistenceException
    -> SQLTransientConnectionException
```

Không có một exception class portable duy nhất thể hiện mọi kết nối bị ngắt trong mọi JPA provider/JDBC driver.

### 8.1. PostgreSQL SQLSTATE tham khảo

| SQLSTATE | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| Class `08` | Connection exception | Xem phase/outcome, kiểm tra retry |
| `08006` | Connection failure | Thay connection, classify attempt |
| `08001` | SQL client unable to establish connection | Kiểm tra endpoint/network |
| `57P01` | Admin shutdown | Có thể liên quan restart/failover |
| `53300` | Too many connections | Capacity/backpressure |
| `28P01` | Invalid password | Sửa credentials/rotation |
| `42501` | Insufficient privilege | Sửa grants; không retry vô hạn |
| `40001` | Serialization failure | Retry cả transaction có giới hạn |
| `40P01` | Deadlock detected | Retry cả transaction có giới hạn |
| `23505` | Unique violation | Thường business conflict hoặc idempotency reconciliation |
| `23503` | Foreign-key violation | Dữ liệu/mapping/transaction ordering |
| `42P01` | Undefined table | Migration/schema mismatch |

Các mã này dùng để **minh họa PostgreSQL**, không mặc định áp dụng y hệt cho MySQL, Oracle hay SQL Server.

### 8.2. SQLSTATE không cho biết commit outcome

`08006` giúp nhận diện connection failure; nó không tự trả lời “transaction đã commit chưa” nếu lỗi xuất hiện ở ranh giới commit.

### 8.3. Không dùng exception message làm classifier duy nhất

Thông báo có thể thay theo locale/provider/driver. Ưu tiên exception type, SQLSTATE, vendor code, transaction phase và cấu trúc nguyên nhân.

---

# Phần II — Mô hình nghiệp vụ có thể retry an toàn

## 9. Thiết kế giữ hàng với idempotency key

Ví dụ hệ thống giữ kho:

```text
stock_items
+-------+-----------+---------+
| sku   | available | version |
+-------+-----------+---------+
| A-01  |       100 |       4 |
+-------+-----------+---------+

stock_reservations
+------------+-------+----------+
| request_id | sku   | quantity |
+------------+-------+----------+
| req-123    | A-01  |        2 |
+------------+-------+----------+
```

Yêu cầu:

- Một `requestId` chỉ được ghi nhận thành công một lần.
- Reservation và stock decrement xảy ra **trong cùng DB transaction**.
- Nếu client gửi lại cùng `requestId`, trả kết quả tương ứng thay vì giảm kho tiếp.
- Nếu database unavailable, không khẳng định request thất bại vĩnh viễn khi commit outcome chưa biết.

### 9.1. DDL PostgreSQL

```sql
CREATE TABLE stock_items (
    sku VARCHAR(100) PRIMARY KEY,
    available INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_stock_available
        CHECK (available >= 0)
);

CREATE TABLE stock_reservations (
    request_id VARCHAR(100) PRIMARY KEY,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT fk_reservation_stock
        FOREIGN KEY (sku)
        REFERENCES stock_items(sku),

    CONSTRAINT ck_reserved_quantity
        CHECK (quantity > 0)
);
```

`request_id` là durable idempotency key. `stock_items.available` và reservation row được cập nhật dưới cùng transaction.

### 9.2. Request ID phải đúng scope

Nếu nhiều tenants dùng chung bảng, cân nhắc key `(tenant_id, request_id)` hoặc thiết kế global uniqueness có phạm vi xác thực rõ ràng. Không để một client chọn ID thuộc tenant khác rồi đọc kết quả không được phép.

### 9.3. Không chỉ dùng in-memory Set

Một `ConcurrentHashMap` trên một instance không bảo đảm idempotency khi:

- Service restart.
- Có nhiều replicas.
- Request được route sang instance khác.
- Database commit trước khi HTTP response gửi.
- Cache bị evict.

Cần một record durable/unique constraint hoặc một hệ thống idempotency đáng tin tương đương.

---

## 10. JPA entity StockItem

```java
package com.example.recovery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "stock_items")
public class StockItem {

    @Id
    private String sku;

    @Column(nullable = false)
    private int available;

    @Version
    @Column(nullable = false)
    private long version;

    protected StockItem() {
    }

    public StockItem(String sku, int available) {
        if (sku == null || sku.isBlank() ||
                available < 0) {
            throw new IllegalArgumentException(
                "Invalid stock fixture"
            );
        }

        this.sku = sku;
        this.available = available;
    }

    public String getSku() {
        return sku;
    }

    public int getAvailable() {
        return available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        if (available < quantity) {
            throw new IllegalStateException(
                "Insufficient stock"
            );
        }

        available -= quantity;
    }
}
```

`@Version` giúp phát hiện optimistic conflicts khi nhiều transactions cùng update stock item, với điều kiện mapping/transaction flow phù hợp.

### 10.1. Không dùng version như connection-recovery mechanism

Optimistic locking xử lý cạnh tranh cập nhật entity, không sửa lỗi mạng. Khi lỗi connection xảy ra, vẫn cần kết thúc attempt, tạo context mới và đối soát.

---

## 11. JPA entity StockReservation

```java
package com.example.recovery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "stock_reservations")
public class StockReservation {

    @Id
    @Column(name = "request_id", length = 100)
    private String requestId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "sku", nullable = false)
    private StockItem stock;

    @Column(nullable = false)
    private int quantity;

    @Column(
        name = "created_at",
        nullable = false
    )
    private Instant createdAt;

    protected StockReservation() {
    }

    public StockReservation(
            String requestId,
            StockItem stock,
            int quantity,
            Instant createdAt) {

        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException(
                "requestId required"
            );
        }

        if (stock == null || quantity <= 0 ||
                createdAt == null) {
            throw new IllegalArgumentException(
                "Invalid reservation"
            );
        }

        this.requestId = requestId;
        this.stock = stock;
        this.quantity = quantity;
        this.createdAt = createdAt;
    }

    public String getRequestId() {
        return requestId;
    }

    public String getSku() {
        return stock.getSku();
    }

    public int getQuantity() {
        return quantity;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

### 11.1. Một transaction ghi stock và reservation

```java
em.getTransaction().begin();

StockItem item =
    em.find(StockItem.class, sku);

item.reserve(quantity);

em.persist(
    new StockReservation(
        requestId,
        item,
        quantity,
        clock.instant()
    )
);

em.getTransaction().commit();
```

Đoạn này biểu diễn thay đổi atomic ở database nếu commit thành công. `clock` là `java.time.Clock` được inject để tests kiểm soát thời gian.

### 11.2. Không đưa external payment call vào giữa transaction

Nếu giữ stock kèm gửi yêu cầu thanh toán, không nên gọi payment gateway trong một DB transaction mở lâu. External side effect không tự rollback cùng database.

Dùng workflow/saga/outbox và idempotency ở từng boundary phù hợp.

---

## 12. Luồng idempotency và đối soát

Một flow minh họa:

```text
Receive command(requestId, sku, quantity)
                     |
                     v
             Validate/authenticate
                     |
                     v
           Query existing requestId
                     |
           +---------+-----------+
           |                     |
         Exists                Not found
           |                     |
           v                     v
  Verify same payload      Begin NEW transaction
  Return prior result      Recheck current stock
                             Insert reservation
                             Update stock
                             COMMIT
                                   |
                      +------------+------------+
                      |                         |
                      v                         v
                 Success ACK                Connection lost
                      |                         |
                      v                         v
                 Return result            Outcome UNKNOWN
                                                |
                                                v
                                     Reconnect/read by requestId
                                                |
                                     +----------+---------+
                                     |                    |
                                   Found             Not found
                                     |                    |
                                     v                    v
                                  Verify           Assess authoritative
                                  payload          state/timeouts, retry
                                  return           only per policy
```

### 12.1. Pre-check không thay unique constraint

Hai concurrent requests với cùng requestId đều có thể thấy “not found” trước khi một transaction INSERT thành công. DB primary/unique key là hàng rào cuối.

### 12.2. Conflict phải so sánh payload

Nếu `requestId=req-123` đã dùng cho `sku=A, quantity=2`, một request mới cùng key nhưng `quantity=99` không được trả thành công như thể cả hai cùng operation.

Lưu hoặc tái tạo một payload fingerprint/fields để xác minh retry cùng ý định nghiệp vụ.

### 12.3. Not found không luôn là bằng chứng rollback

Khi DB vừa failover hoặc transaction trước còn pending trên server, một truy vấn quá sớm có thể không nhìn thấy kết quả. Đọc từ replica lag cũng không đủ để kết luận không có commit trên primary.

Chỉ coi outcome là có thể retry sau khi có đủ điều kiện reconciliation được thiết kế cho stack cụ thể.

### 12.4. Idempotency phải có chính sách retention

Nếu xóa key quá sớm, client gửi lại request cũ có thể thực hiện thao tác lần nữa. Cần TTL/retention phù hợp với thời gian tối đa client có thể retry và yêu cầu audit.

---

# Phần III — EntityManager và transaction cleanup

## 13. RESOURCE_LOCAL: mỗi attempt có EntityManager riêng

Một pattern đơn giản:

```java
public final class ReservationUnitOfWork {

    private final EntityManagerFactory emf;
    private final Clock clock;

    public ReservationUnitOfWork(
            EntityManagerFactory emf,
            Clock clock) {
        this.emf = emf;
        this.clock = clock;
    }

    public void reserveOnce(ReserveCommand command) {
        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            StockReservation existing =
                em.find(
                    StockReservation.class,
                    command.requestId()
                );

            if (existing != null) {
                verifySameCommand(existing, command);
                em.getTransaction().commit();
                return;
            }

            StockItem item = em.find(
                StockItem.class,
                command.sku()
            );

            if (item == null) {
                throw new IllegalArgumentException(
                    "Unknown sku"
                );
            }

            item.reserve(command.quantity());

            em.persist(new StockReservation(
                command.requestId(),
                item,
                command.quantity(),
                clock.instant()
            ));

            em.flush();
            em.getTransaction().commit();

        } catch (RuntimeException primary) {
            try {
                if (em.getTransaction().isActive()) {
                    em.getTransaction().rollback();
                }
            } catch (RuntimeException rollbackError) {
                primary.addSuppressed(rollbackError);
            }

            throw primary;

        } finally {
            em.close();
        }
    }

    private static void verifySameCommand(
            StockReservation existing,
            ReserveCommand command) {

        if (!existing.getSku().equals(command.sku()) ||
                existing.getQuantity() != command.quantity()) {
            throw new IllegalStateException(
                "Idempotency key reused with different payload"
            );
        }
    }
}
```

Command:

```java
public record ReserveCommand(
    String requestId,
    String sku,
    int quantity
) {
}
```

Đây là **skeleton cho một attempt**. Nó chưa tự giải quyết concurrency race của pre-check, unknown commit outcome hoặc retry orchestration. Các phần đó cần được xử lý ở lớp bên ngoài.

### 13.1. Vì sao close sau lỗi?

Một failed flush/SQL/connection có thể để persistence context mang snapshot/managed state không đáng tin. Thay vì tái sử dụng `em` cho lần hai, đóng rồi tạo mới.

### 13.2. Rollback cũng có thể ném exception

Nếu đường mạng đã mất, `rollback()` có thể không thực hiện được hoặc báo lỗi. Ghi suppressed failure giúp giữ nguyên exception ban đầu.

### 13.3. Commit trả thành công mới xác nhận attempt thành công

`flush()` thành công không đủ. Commit có thể thất bại hoặc outcome unknown.

### 13.4. Close không undo một commit đã xảy ra

`em.close()` giải phóng context/resources. Nó không có quyền đảo ngược dữ liệu đã commit.

### 13.5. Không giữ EntityManager trong singleton

`EntityManager` không thread-safe. Không dùng một EM global cho nhiều requests hoặc giữ EM đã lỗi để “tiết kiệm tạo connection”.

---

## 14. Spring và JTA: không đóng EntityManager được quản lý hộ

Trong Spring:

```java
@PersistenceContext
private EntityManager entityManager;
```

thường là transaction-aware proxy. `@Transactional`/transaction manager quản lý EntityManager thực và connection lifecycle.

### 14.1. Không tự close proxy trong catch

Sai:

```java
catch (PersistenceException ex) {
    entityManager.close();
}
```

với Spring-managed hoặc container-managed EntityManager. Để framework rollback/cleanup; retry bắt đầu qua transaction boundary mới.

### 14.2. Spring default rollback policy

Spring thường rollback với unchecked exceptions thoát khỏi `@Transactional` method. Nhưng nếu code catch một exception rồi return bình thường, transaction có thể vẫn bị rollback-only từ tầng dưới.

Không “nuốt” lỗi kết nối rồi tiếp tục ghi trong cùng transaction.

### 14.3. `REQUIRES_NEW` không phải công cụ reset EM ngay trong catch

Nó tạo transaction mới khi được gọi qua Spring proxy đúng cách, nhưng không tự giải quyết idempotency/commit ambiguity. Không dùng self-invocation `this.someRequiresNewMethod()` rồi giả định interceptor hoạt động trong proxy-based setup.

### 14.4. JTA và extended contexts

Container-managed JTA transaction có status/rollback semantics riêng. Extended persistence contexts còn có thể giữ entity state qua nhiều transactions; cần chiến lược discard/reload conversation khi lỗi nghiêm trọng. Không mặc định “transaction manager rollback” đã tự rewind mọi Java object.

---

## 15. Retry phải nằm ngoài transaction thất bại

Sai:

```java
@Transactional
public void reserveWithRetry(ReserveCommand command) {
    for (int i = 0; i < 3; i++) {
        try {
            doJpaWrites(command);
            return;
        } catch (PersistenceException ex) {
            // Vẫn ở transaction lỗi!
        }
    }
}
```

Nếu lần đầu đã đánh dấu rollback-only, những lần sau có thể tiếp tục thất bại và cuối cùng `UnexpectedRollbackException`.

### 15.1. Cấu trúc đúng

```text
Outer retry coordinator (NOT transactional)
         |
         v
Attempt 1: NEW transaction/context
         |
         v
Failure -> rollback/cleanup
         |
         v
Classify + bounded backoff OUTSIDE transaction
         |
         v
Attempt 2: NEW transaction/context
         |
         v
Reload, re-evaluate, commit
```

### 15.2. Không giữ backoff trong DB transaction

Chờ 500 ms trong transaction có thể giữ locks/connection và làm outage nặng hơn.

### 15.3. Một retry owner

Nếu web gateway retry hai lần, service retry ba lần và DB client retry bốn lần, một yêu cầu có thể dẫn tới 24 attempts. Phải tính budget trên toàn request path.

---

## 16. Retry classifier phải hẹp

Ví dụ:

```java
public enum FailureCategory {
    CONNECTION_UNAVAILABLE,
    TRANSACTION_RETRYABLE,
    COMMIT_OUTCOME_UNKNOWN,
    AUTHENTICATION,
    DATA_CONSTRAINT,
    PROGRAMMING_ERROR,
    BUSINESS_CONFLICT,
    UNKNOWN
}
```

Một policy:

| Loại | Có thể retry tự động? | Ghi chú |
| --- | --- | --- |
| Connection unavailable trước SQL write | Có điều kiện | New attempt, deadline/backoff |
| Read-only SELECT bị ngắt | Thường có điều kiện | New transaction/context |
| Deadlock/serialization failure | Có điều kiện | Retry **toàn transaction** |
| Connection lost ở COMMIT | **Không retry write mù** | Reconciliation/idempotency |
| Invalid credentials | Không | Rotation/configuration |
| Schema/mapping error | Không | Fix migration/code |
| UNIQUE violation | Không theo kiểu generic | Conflict hoặc idempotency lookup |
| FK/NOT NULL/CHECK violation | Không | Fix data/invariant |
| Insufficient stock | Không | Business result |
| Query chậm cố hữu | Không nên retry lặp | Query plan/index/capacity |
| Pool exhausted | Chỉ có điều kiện | Backpressure/capacity |

### 16.1. SQLSTATE class `08` chưa đủ

Một lỗi connection trước khi bắt đầu SQL write khác lỗi cùng class xuất hiện trong commit. Classifier nên nhận cả **transaction phase**:

```java
public enum DbPhase {
    ACQUIRE_CONNECTION,
    BEGIN,
    READ,
    WRITE,
    FLUSH,
    COMMIT,
    ROLLBACK
}
```

### 16.2. Không coi mọi RuntimeException là transient

Một `NullPointerException` hoặc `IllegalArgumentException` trong business code không phải lỗi database outage.

### 16.3. Không retry quá deadline

Khi request hết thời gian và client đã hủy, tiếp tục thực hiện write trong nền mà không có workflow/ownership rõ có thể tạo kết quả bất ngờ.

---

## 17. Retry với TransactionTemplate

Một ví dụ Spring phác thảo:

```java
@Service
public class ReservationCoordinator {

    private final TransactionTemplate template;
    private final ReservationAttempt attempt;
    private final RetryPolicy retryPolicy;

    public ReservationCoordinator(
            PlatformTransactionManager manager,
            ReservationAttempt attempt,
            RetryPolicy retryPolicy) {

        this.template = new TransactionTemplate(manager);
        this.template.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );

        this.attempt = attempt;
        this.retryPolicy = retryPolicy;
    }

    public ReservationResult execute(ReserveCommand command) {
        RuntimeException last = null;

        for (int number = 1; number <= 3; number++) {
            try {
                return template.execute(status ->
                    attempt.executeInCurrentTransaction(command)
                );

            } catch (RuntimeException error) {
                if (!retryPolicy.mayRetry(
                        error, number, command)) {
                    throw error;
                }

                last = error;
                retryPolicy.backoff(number);
            }
        }

        throw last;
    }
}
```

`ReservationAttempt`, `ReservationResult` và `RetryPolicy` là interfaces/classes của ứng dụng, cần được định nghĩa. Đây là **cấu trúc minh họa**, không phải một retry implementation đã an toàn cho mọi outage.

### 17.1. Điều kiện bắt buộc cho bản production

`mayRetry` phải biết transaction phase và commit outcome. Không được retry write khi chưa xử lý ambiguity/idempotency.

### 17.2. TransactionTemplate execute có thể lỗi khi commit

Exception có thể xuất hiện **sau callback** ở transaction commit. Vì vậy không chỉ bắt lỗi trong `attempt.executeInCurrentTransaction(...)`.

### 17.3. `REQUIRES_NEW` và outer transaction

`REQUIRES_NEW` có thể tạm ngưng outer transaction nếu có. Nhưng khi outer transaction vẫn giữ connection và coordinator mở một transaction mới, connection pool có thể cần capacity bổ sung. Thường nên tổ chức coordinator ngoài mọi business transaction thay vì lạm dụng nested new transactions.

### 17.4. Backoff cần giới hạn

Một policy có thể dùng bounded exponential backoff + jitter, chẳng hạn base 100 ms, tăng theo attempt và giới hạn tối đa. Không dùng retry vô tận hoặc `Thread.sleep()` tùy tiện trong async/reactive workloads.

---

# Phần IV — Timeouts, pool và sự phục hồi kết nối

## 18. HikariCP không tự tạo idempotency

HikariCP quản lý pool của JDBC connections. Nó có thể phát hiện và loại bỏ connection không còn usable, nhưng không biết `reserve(requestId)` có bị thực thi hai lần hay không.

### 18.1. Các tham số thường gặp

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1800000
```

Các con số là ví dụ. Trong HikariCP, các tham số thời gian trên thường tính bằng **milliseconds**. Không tự áp làm cấu hình production tối ưu cho mọi hệ thống.

### 18.2. `connection-timeout`

Giới hạn thời gian chờ lấy connection từ pool. Không có nghĩa mọi JDBC query/commit đều bị hủy sau từng ấy milliseconds.

### 18.3. `validation-timeout`

Giới hạn thao tác kiểm tra connection validity theo pool/driver behavior; không bảo đảm query nghiệp vụ có deadline giống vậy.

### 18.4. `max-lifetime`

Giới hạn vòng đời connection theo pool semantics, giúp chủ động thay connections. Nó **không** sửa transaction outcome ambiguity và không tự bảo đảm connections cũ biến mất tức thì khi DB crash.

### 18.5. Cạn pool không giống database offline

Pool exhausted có thể do transactions dài, connection leaks hoặc tải cao. Nếu mọi lỗi pool timeout đều kích hoạt 10 retry attempts, tình trạng tắc nghẽn có thể tệ hơn.

---

## 19. JDBC connect timeout và socket timeout

Với PostgreSQL JDBC, một JDBC URL có thể dùng:

```text
jdbc:postgresql://db.example.internal:5432/shop?connectTimeout=3&socketTimeout=10&sslmode=verify-full
```

Theo pgJDBC, `connectTimeout` và `socketTimeout` thường được khai báo bằng **giây**. Cần xác minh theo version driver đang dùng.

**Không đưa password vào URL** để tránh lộ qua log/config dumps.

### 19.1. Socket timeout không phải transaction outcome guarantee

Nếu socket timeout đúng lúc chờ commit ACK, app có thể mất phản hồi nhưng DB đã commit. Timeout giúp giới hạn chờ, không trả lời outcome.

### 19.2. Query timeout là lớp khác

```java
query.setHint(
    "jakarta.persistence.query.timeout",
    2_000
);
```

Hint timeout có semantics/hỗ trợ tùy provider và DB. Một query timeout khác với connection acquisition timeout hoặc tổng transaction timeout.

### 19.3. Budget ở nhiều tầng

Một request có thể gồm:

```text
HTTP deadline:             8 seconds
Pool acquisition budget:   1 second
Connection setup budget:   2 seconds
Query budget:              3 seconds
Retry/backoff budget:      within remaining deadline
```

Đây là ví dụ thiết kế, không phải bảo đảm rằng thời gian của mọi tầng cộng lại đúng cứng trong mọi thread.

### 19.4. Timeout quá thấp gây false outages

Một query bình thường chậm 200 ms trong peak hours nhưng timeout đặt 100 ms có thể dẫn đến failures/retries quá mức. Cần dùng metrics và SLO để quyết định.

---

## 20. Readiness và liveness phải có mục đích riêng

### 20.1. Readiness

Trả lời: **service có thể nhận traffic và thực hiện chức năng thiết yếu lúc này không?**

Nếu database là dependency bắt buộc, readiness có thể thất bại trong outage.

### 20.2. Liveness

Trả lời: **process có bị kẹt và cần khởi động lại không?**

Database down không tự có nghĩa JVM bị deadlock. Restart tất cả replicas liên tục có thể làm pool reconnect storm sau DB hồi phục.

### 20.3. Ví dụ Spring Boot Actuator

Trong một deployment Spring Boot có Actuator, có thể dùng các health groups/probes để đưa readiness/liveness ra endpoints riêng. Phải xác định DB health indicator nằm trong group nào theo phiên bản/cấu hình.

Không mặc định rằng khi dependency DB unavailable, liveness phải trả DOWN.

### 20.4. Khả năng phục hồi không phải chỉ trả HTTP 200 health

Một ứng dụng có thể luôn trả `/health=UP` nhưng mọi business endpoint báo 500. Test readiness và business behavior đều cần thiết.

---

## 21. Circuit breaker và bulkhead

Circuit breaker có thể hạn chế gọi một dependency đang lỗi, giảm resource exhaustion.

```text
CLOSED  -> Cho requests qua
OPEN    -> Fail fast khi dependency đang lỗi
HALF_OPEN -> Cho một số probes thử phục hồi
```

### 21.1. Circuit breaker không quyết định transaction outcome

Nếu commit acknowledgment bị mất, circuit breaker OPEN không có nghĩa transaction trước đã rollback.

### 21.2. Không dùng circuit breaker thay timeout

Nếu mỗi query treo rất lâu, breaker chỉ có thể phản ứng sau khi đã quan sát failures; cần timeout budgets phù hợp.

### 21.3. Half-open probe nên an toàn

Probe có thể là read-only query nhẹ. Không dùng một real payment/reservation write chỉ để kiểm tra DB đã hồi phục.

### 21.4. Backpressure thay vì hàng đợi vô hạn

Khi DB outage kéo dài, chấp nhận và giữ vô hạn hàng triệu HTTP requests trong memory không phải “khả năng phục hồi”. Cần giới hạn concurrency/queue, trả lỗi tạm thời hoặc lưu command qua một durable queue có chính sách được thiết kế.

---

# Phần V — Kiểm thử fault injection

## 22. Unit test với mock chưa đủ

Một test như:

```java
when(repository.findById(any()))
    .thenThrow(new DataAccessResourceFailureException(
        "DB unavailable"
    ));
```

hữu ích để kiểm tra error mapping và retry classifier. Nhưng nó **không chứng minh**:

- Driver phát hiện connection reset.
- Pool loại bỏ invalid connections.
- JPA rollback/close đúng.
- Queries sau reconnect thành công.
- Commit outcome sau loss.
- Recovery từ replica failover.
- SQLSTATE thực.
- Transaction atomicity.

Cần integration test cắt kết nối thật qua database/proxy hoặc một môi trường chaos đã cô lập.

---

## 23. Testcontainers PostgreSQL

Khởi động PostgreSQL trong môi trường test:

```java
@Testcontainers
class DatabaseOutageIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>(
            "postgres:16-alpine"
        );

    // Khởi tạo DataSource/EntityManagerFactory
    // với JDBC URL, username, password của container.
}
```

Các dependencies gồm Testcontainers PostgreSQL, JUnit Jupiter, PostgreSQL JDBC và JPA provider.

### 23.1. Môi trường test phải tách production

Không dùng tài khoản production, network production hoặc dữ liệu khách hàng thực cho fault injection.

### 23.2. Dùng migrations thật

Nếu test cần khẳng định ứng dụng phục hồi với schema hiện hành, chạy Flyway/Liquibase migrations thay vì mặc định `hbm2ddl.auto=create-drop` che vấn đề.

### 23.3. Dùng version có kiểm soát

Container tag, JDBC driver, Hibernate/Spring và server versions nên gần production theo mục tiêu kiểm thử. Không suy từ H2 in-memory rằng failover PostgreSQL hoạt động y hệt.

---

## 24. Vì sao nên có network fault proxy?

Chỉ gọi:

```java
postgres.stop();
```

làm DB server ngừng hoạt động. Điều này hữu ích để test mất dependency hoàn toàn, nhưng khó tái tạo chính xác:

- Connection reset giữa một query.
- Blackhole khiến request treo đến timeout.
- Lỗi chỉ một chiều.
- Loss đúng ở pha commit.
- Chập chờn vài giây rồi tự phục hồi.
- Packet latency/jitter.
- Connection cũ hỏng nhưng new connections hoạt động sau recovery.

Một proxy kiểm thử như **Toxiproxy** có thể được đặt giữa application và PostgreSQL:

```text
JPA application
      |
      v
HikariCP / JDBC
      |
      v
Test-only Toxiproxy
      |
      v
PostgreSQL Testcontainer
```

Test có thể bật/tắt toxic hoặc cắt đường truyền mà không cần sửa application code.

### 24.1. Proxy phải nằm trên đường JDBC thực

Nếu test điều khiển Toxiproxy nhưng DataSource vẫn trỏ thẳng `postgres.getJdbcUrl()`, fault injection không tác động JDBC traffic.

### 24.2. Có thể dùng network alias

Trong Testcontainers có thể tạo shared Docker network, để Toxiproxy tiếp cận PostgreSQL container bằng alias và cổng 5432.

### 24.3. Không giả định proxy bắt được mọi race ở commit

Để kiểm thử **commit ACK lost** có tính xác định, chỉ cắt network vào một thời điểm gần commit chưa chắc đủ. Cần công cụ/failpoint có thể xác định chính xác server đã commit nhưng ACK bị chặn, hoặc kiểm thử các outcome có thể xảy ra qua một harness kiểm soát.

---

## 25. Toxiproxy setup minh họa

Với Testcontainers Java có module Toxiproxy (API tùy version), một dạng cấu trúc:

```java
Network network = Network.newNetwork();

PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine")
        .withNetwork(network)
        .withNetworkAliases("postgres");

ToxiproxyContainer toxiproxy =
    new ToxiproxyContainer(
        "ghcr.io/shopify/toxiproxy:2.9.0"
    )
    .withNetwork(network);

postgres.start();
toxiproxy.start();

ToxiproxyContainer.ContainerProxy dbProxy =
    toxiproxy.getProxy(postgres, 5432);
```

Sau đó application test DataSource phải dùng host/port được **dbProxy** cung cấp, thay vì direct JDBC URL. Tên class/method và container image tag cần đối chiếu với Testcontainers/Toxiproxy version của project trước khi chạy; mã trên minh họa kiến trúc kết nối.

### 25.1. Không đưa credentials vào log

Dùng username/password riêng do PostgreSQL Testcontainer cấp. Log proxy host/port là đủ để debug connection routing; không in password.

### 25.2. Cắt kết nối

Ở một số Testcontainers Toxiproxy versions, có API dạng:

```java
dbProxy.setConnectionCut(true);
```

và:

```java
dbProxy.setConnectionCut(false);
```

để mô phỏng mất và phục hồi kết nối. Với các versions khác, có thể phải điều khiển toxics qua Toxiproxy client API.

### 25.3. Test cần tự cleanup

Dùng `try/finally` để bật lại proxy sau test, tránh các test khác thừa hưởng outage:

```java
try {
    dbProxy.setConnectionCut(true);
    // Chạy assertions trong thời gian DB unavailable.
} finally {
    dbProxy.setConnectionCut(false);
}
```

Ngoài ra cần đóng EntityManagerFactory, DataSource/pool và Docker network theo test lifecycle.

### 25.4. Cắt toàn đường mạng không phân biệt chính xác từng SQL phase

Một proxy cut thường ảnh hưởng connections đang mở và mới. Để gây lỗi ở một điểm cụ thể, cần synchronization/failpoint, không dùng `Thread.sleep()` rồi khẳng định lỗi chắc chắn xảy ra ở commit.

---

# Phần VI — Bộ kịch bản phục hồi

## 26. Test 1: DB down trước khi lấy connection

**Given:** database/proxy unavailable trước khi request bắt đầu.

**When:** application gọi repository hoặc lấy EntityManager connection để SELECT.

**Then:**

- Request thất bại có giới hạn thời gian.
- Không bị treo vô hạn.
- Exception được phân loại dependency unavailable.
- Không trả dữ liệu giả thành công.
- Không ghi nhận business operation đã hoàn tất.
- Readiness phản ánh dependency thiết yếu không sẵn sàng theo policy.
- Liveness không cần restart-loop chỉ vì DB down.
- Logs không lộ credentials.

### 26.1. Test skeleton

```java
@Test
void returnsUnavailableWhenDatabaseIsDown() {
    faultController.disconnect();

    try {
        assertThrows(
            DataAccessException.class,
            () -> stockRepository.findById("A-01")
        );
    } finally {
        faultController.reconnect();
    }
}
```

Đây là pseudocode test harness: `faultController` là abstraction test-only điều khiển Toxiproxy/DB, còn exception class phụ thuộc Spring transaction/pool mapping. Không đặt production code vào test chỉ vì cần tạo lỗi.

### 26.2. Không assert đúng một exception class không ổn định

Nếu muốn test portable, assert error category và dữ liệu không thay đổi. Với Spring/Hibernate/pgJDBC cụ thể, có thể thêm assertion cause/SQLSTATE tương ứng.

---

## 27. Test 2: phục hồi mà không restart service

**Given:** service đã khởi động, database bị cắt trong một khoảng ngắn.

**When:** proxy được bật lại hoặc PostgreSQL restart xong.

**Then:**

- Pool có thể cấp connections mới.
- Một transaction/context **mới** thực hiện query thành công.
- Readiness trở lại trạng thái sẵn sàng.
- Không cần sửa thủ công connection object bị hỏng.
- Không có hàng đợi retry vô hạn.
- Connection/pool metrics ổn định trở lại.

### 27.1. Không chỉ kiểm tra TCP port đã mở

Kết nối TCP thành công không chứng minh JPA queries chạy được hoặc migration/schema/credentials đã đúng.

### 27.2. Dùng polling với deadline

Thay vì:

```java
Thread.sleep(1000);
assertTrue(dbHealthy());
```

có thể dùng Awaitility hoặc polling có timeout:

```java
await()
    .atMost(Duration.ofSeconds(20))
    .pollInterval(Duration.ofMillis(250))
    .untilAsserted(() -> {
        assertTrue(databaseReadSucceeds());
    });
```

`databaseReadSucceeds()` là helper test mở **new transaction/context**, thực hiện một query nhẹ và cleanup. Không giữ EntityManager từ attempt lỗi.

### 27.3. Không dùng retry không giới hạn

Test phải dừng khi hết budget và báo lỗi thực nếu DB không hồi phục.

---

## 28. Test 3: lỗi khi đang đọc một result set

**Given:** một query đủ lâu hoặc streaming result đang hoạt động.

**When:** cắt connection trong lúc driver chờ/fetch dữ liệu.

**Then:**

- Request không trả partial result như thành công toàn phần nếu contract yêu cầu kết quả đầy đủ.
- Transaction/context được cleanup.
- Pool không tiếp tục cấp connection hỏng.
- New read attempt chỉ chạy trong transaction/context mới.
- Query sau recovery trả dữ liệu đúng theo committed state.

### 28.1. Cần deterministic synchronization

Dùng test-only database function, latch/failpoint hoặc proxy toxic để chặn ở vị trí xác định.

Một `Thread.sleep(100)` trên thread chính **không bảo đảm** query của thread phụ đang ở đúng pha muốn cắt.

### 28.2. Streaming đặc biệt quan trọng

Nếu JPA query streaming trả data từng phần, connection có thể được giữ lâu. Cần test cleanup stream/result handle và đảm bảo API không trả HTTP 200 với JSON bị cắt mà client hiểu là dữ liệu đầy đủ.

### 28.3. Read-only không đồng nghĩa query vô hại

Một `SELECT ... FOR UPDATE` lấy locks. Nếu connection mất, lock release và rollback phụ thuộc DB transaction/session state. Không coi mọi SELECT là ứng viên retry vô điều kiện.

---

## 29. Test 4: ngắt kết nối sau SQL write, trước commit

**Given:** transaction đã update StockItem và INSERT StockReservation nhưng chưa gửi COMMIT.

**When:** đường mạng bị cắt.

**Then:**

- Application nhận lỗi và kết thúc attempt.
- Không tái sử dụng EntityManager lỗi.
- Sau DB recovery, kiểm tra committed state từ connection mới.
- Không suy từ `StockItem` Java object rằng stock đã bị giảm.
- Không phát business success event dựa trên flush.
- Nếu transaction trước chưa commit, DB phải rollback theo protocol/session outcome sau khi nhận biết disconnect/timeout.

### 29.1. Không dựa vào flush như dấu hiệu commit

```java
em.flush();
```

đồng bộ SQL, nhưng connection outage trước commit có thể khiến toàn transaction bị rollback.

### 29.2. Server-side session có thể sống thêm một lúc

Nếu lỗi là **blackhole** khiến server chưa biết client đã mất, transaction có thể tạm giữ locks cho đến timeout/connection cleanup. Test nên có timeout budget và không mặc định locks biến mất ngay trong microseconds.

### 29.3. Cần verify atomicity

Nếu DB xác nhận attempt rollback, cả reservation row và stock decrement phải được hoàn tác; không chấp nhận chỉ một trong hai được committed.

---

## 30. Test 5: commit outcome không xác định

**Given:** server có thể đã nhận và xử lý COMMIT.

**When:** client mất kết nối trước khi nhận kết quả.

**Then:**

- Application đánh dấu outcome là `UNKNOWN` trong flow xử lý, không tự báo `ROLLED_BACK`.
- Không retry write mù.
- Sau recovery, tìm durable idempotency record bằng `requestId`.
- Nếu record có và payload trùng: trả kết quả cũ.
- Nếu record có nhưng payload khác: báo idempotency conflict.
- Nếu record không có: áp chính sách reconciliation/settling rồi mới quyết định một attempt mới.
- Không tạo stock decrement thứ hai.

### 30.1. Muốn test cả hai nhánh

Một test suite nghiêm túc cần có:

```text
Scenario A: Server committed, ACK lost
Scenario B: Server rolled back, connection lost
```

Một lệnh `disconnect()` ngay trước `commit()` có thể chỉ test Scenario B mà **không bao giờ** tạo được Scenario A.

### 30.2. Cách có kết quả xác định

Dùng test-specific commit failpoint hoặc một adapter có khả năng mô phỏng “commit đã được database chấp nhận nhưng response cho caller bị mất”; đồng thời integration test database thật để verify idempotency/reconciliation.

Không tuyên bố một network cut tùy thời điểm chứng minh cả hai outcomes.

### 30.3. Test qua idempotency key

Sau khi transaction đầu thực sự đã commit, retry cùng `requestId` phải:

- Không tạo reservation thứ hai.
- Không giảm stock thêm.
- Trả cùng logical outcome.
- Không gọi side effect ngoài DB lần hai.

---

## 31. Test 6: lỗi auth không được retry vô hạn

**Given:** DB password sai hoặc role bị thu hồi.

**When:** application cần new connection.

**Then:**

- Failure được phân loại auth/config issue.
- Không retry vô hạn.
- Không fallback sang password yếu/default.
- Logs không in credential.
- Alert/health phản ánh sự cố.
- Sau rotation/redeploy hợp lệ, new connections thành công.

### 31.1. Test đúng lớp

Không nên mô phỏng auth error bằng một `SQLException` 08006, vì đây là lỗi connection khác. Với PostgreSQL có thể gặp SQLSTATE `28P01` cho invalid password.

### 31.2. Active connections có thể còn sống sau rotation

Một số database cho phép sessions đang mở tiếp tục trong khi new connections bằng password cũ bị từ chối. Test phải buộc tạo **new connection** để xác minh credential mới.

---

## 32. Test 7: pool giữ stale connections sau DB restart

**Given:** pool đã mở vài connections trước khi DB restart.

**When:** PostgreSQL khởi động lại và pool mượn connection cũ.

**Then:**

- Invalid connection được phát hiện/loại bỏ.
- Pool không cấp hỏng vô hạn.
- New connections có thể được tạo.
- Business read phục hồi trong timeout budget.
- Pool active/idle/pending metrics không kẹt mãi.

### 32.1. Test không được restart JVM để “chữa pool”

Một bài test về pool recovery cần giữ **cùng service process/pool instance**. Nếu mỗi failure làm test tạo DataSource mới, không kiểm tra được pool tự phục hồi.

### 32.2. DB restart có thể làm mất dữ liệu chưa commit

Sau restart, test chỉ so sánh committed state. Đừng dùng in-memory entity từ trước restart.

### 32.3. Pool reconnect storm

Khi nhiều replicas cùng phục hồi, mọi pool có thể mở nhiều connections cùng lúc. Test load cần xem DB `max_connections` và backoff/pool warm-up.

---

## 33. Test 8: failover và read replica lag

Nếu kiến trúc có primary + replica:

```text
Before failover:
Primary A  ---> Replica B

After failover:
Old A unavailable
New primary B
```

Những điều cần kiểm tra:

- Driver/DNS/proxy route sang primary mới.
- Connections cũ được hủy/loại.
- New writes không đi vào read-only replica.
- Last acknowledged commits có thể được xác minh theo HA replication policy.
- Reads không dùng replica đang lag để quyết định commit outcome của một write.
- Không hình thành split-brain; cần fencing/leadership controls ở hạ tầng.
- TLS hostname verification vẫn hợp lệ cho endpoint mới.

### 33.1. Không cho rằng mọi failover là zero data loss

Synchronous/asynchronous replication có các rủi ro dữ liệu và latency khác nhau. Test theo HA architecture thực tế.

### 33.2. DNS TTL và connection pool

DNS thay đổi không tự đưa những TCP connections đã mở sang IP mới. Pool phải tạo connections mới; DNS caching/driver behavior có thể ảnh hưởng recovery time.

### 33.3. Replica lag làm idempotency lookup khó hơn

Nếu một write vừa commit trên primary nhưng replica chưa nhận, truy vấn lookup từ replica có thể trả “not found”. Reconciliation sau ambiguous commit nên đọc từ nguồn authoritative theo topology và consistency contract.

---

## 34. Test 9: mất kết nối trong batch import

Một job nhập 10.000 rows có thể:

```text
BEGIN
  persist 1..100
  flush
  persist 101..200
  flush
  ...
  COMMIT
```

Nếu connection mất ở record 9.000, các flush trước đó **chưa phải commits** trong một transaction lớn.

### 34.1. Test all-or-nothing

Nếu import contract yêu cầu một transaction, sau rollback phải không có rows của attempt đó được committed.

### 34.2. Test chunk commits

Nếu mỗi 500 rows là một transaction, những chunks trước có thể committed. Job cần checkpoint, request/batch IDs, resume policy, duplicate protection và error reporting.

### 34.3. Không chạy lại toàn file mà không có idempotency

Nếu một số chunks đã commit, retry toàn file có thể duplicate rows hoặc gây UNIQUE errors. Test resume từ checkpoint và kiểm tra tổng row count.

---

# Phần VII — Kiểm thử với Spring và JPA

## 35. Controller không nên quyết định retry bằng cách đọc exception message

Ví dụ một API:

```java
@PostMapping("/reservations")
public ResponseEntity<?> reserve(
        @RequestBody ReserveCommand command) {

    ReservationResult result =
        coordinator.execute(command);

    return ResponseEntity.ok(result);
}
```

Controller cần dựa trên service outcome/error categories. Không viết:

```java
if (exception.getMessage().contains("connection")) {
    retry();
}
```

Thông điệp không phải error protocol ổn định.

### 35.1. API error contract khi dependency down

Nếu DB không sẵn sàng và request không thể xử lý:

```json
{
  "code": "DATABASE_UNAVAILABLE",
  "message": "Service temporarily unavailable",
  "requestId": "req-123"
}
```

HTTP 503 có thể phù hợp khi service tạm thời không thể xử lý. Nếu retry được phép, cần nói rõ client phải gửi lại **cùng idempotency key**.

### 35.2. Không khẳng định “operation failed” khi outcome unknown

Một thông báo có thể nói không xác định được kết quả và hướng client truy vấn trạng thái theo request ID sau khi service phục hồi.

### 35.3. 202 Accepted không phải câu trả lời mặc định khi DB down

HTTP 202 thường biểu thị request đã được chấp nhận để xử lý. Nếu server **chưa ghi nhận command vào nguồn bền vững**, đừng trả 202 như thể đã nhận trách nhiệm xử lý về sau.

---

## 36. Spring @DataJpaTest và bẫy transaction rollback

Một bài test:

```java
@DataJpaTest
class RepositoryTest {

    @Autowired
    TestEntityManager em;

    @Test
    void savesStock() {
        em.persistAndFlush(
            new StockItem("SKU-TEST", 10)
        );
    }
}
```

thường chạy trong transaction mà Spring test framework rollback khi test kết thúc.

### 36.1. Không chứng minh commit recovery

`persistAndFlush()` chưa commit. Nếu muốn test outage **tại commit**, cần transaction boundary thật, không chỉ query trong outer test transaction.

### 36.2. Test cần chủ động tách transactions

Có thể dùng `@SpringBootTest` không có outer test transaction, `TransactionTemplate`, hoặc JPA RESOURCE_LOCAL test fixture riêng.

### 36.3. Verify bằng context mới

Sau recovery, đọc bằng EntityManager/transaction mới. Không assert từ Java object giữ trong transaction đã lỗi.

### 36.4. Không chỉ mock JpaRepository

Unit test với mock hỗ trợ retry orchestration, nhưng không kiểm tra pool, driver, server disconnect hay actual DB commit.

---

## 37. Synchronization trong concurrent fault tests

Để cắt kết nối giữa query/transaction:

```text
Worker thread:
    BEGIN
    SIGNAL "transaction active"
    WAIT on test gate
    WRITE/COMMIT

Test controller thread:
    WAIT "transaction active"
    CUT network proxy
    RELEASE gate
```

Một `CountDownLatch` hoặc test-specific hook có thể giúp tạo thứ tự xác định.

### 37.1. Latch có thể đặt ở application boundary

Ví dụ một hook test-only sau khi load entity nhưng trước `flush()`. Với commit ACK loss cần hook sâu hơn ở driver/network/server boundary nếu muốn phân biệt commit đã đến server.

### 37.2. Không đưa latch hooks vào production path vô tình

Test hooks phải được đặt trong test-only adapters/profiles hoặc có cơ chế không thể bật từ request ngoài.

### 37.3. Luôn cleanup fault

Nếu test assertion throw trước khi reconnect, các tests sau không được kế thừa proxy cut.

---

# Phần VIII — Xác minh database sau phục hồi

## 38. Đọc bằng fresh connection/context

Một helper RESOURCE_LOCAL:

```java
private static <T> T readFresh(
        EntityManagerFactory emf,
        Function<EntityManager, T> action) {

    EntityManager em =
        emf.createEntityManager();

    try {
        return action.apply(em);
    } finally {
        em.close();
    }
}
```

Imports:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.util.function.Function;
```

### 38.1. Không dùng lại entity từ transaction lỗi

Một `StockItem` có thể vẫn mang `available=98` sau rollback, dù database còn 100.

### 38.2. Query dữ liệu bền vững

Ví dụ:

```java
StockReservation reservation =
    readFresh(emf, em ->
        em.find(
            StockReservation.class,
            requestId
        )
    );
```

Nếu cần xác minh cả stock quantity, đọc cả hai trong một transaction phù hợp và dùng nhất quán một authoritative source.

### 38.3. Không nhầm replica với primary

Nếu reading từ replica có replication lag, nó có thể bỏ sót commit đã được primary xác nhận.

### 38.4. Không dùng cache như bằng chứng

L2 cache/query cache hoặc application cache có thể chứa state cũ. Với reconciliation sau failure, cần cân nhắc bypass/evict/primary read theo stack và correctness contract.

---

## 39. Assert atomicity chứ không chỉ “không có exception”

Với một successful reservation:

```text
stock.available = 98
stock_reservations:
    req-123 -> qty 2
```

Với một definitively rolled-back attempt:

```text
stock.available = 100
stock_reservations:
    req-123 -> absent
```

Không chấp nhận:

```text
stock.available = 98
stock_reservations:
    req-123 -> absent
```

nếu contract yêu cầu stock decrement và reservation insert atomic trong cùng database transaction.

### 39.1. Với outcome unknown

Test phải đợi DB phục hồi và reconcile; trước đó không assert rolled-back/committed chỉ từ lỗi client.

### 39.2. Kiểm tra cùng requestId retry

Sau successful commit và một lần retry cùng ID:

```text
stock.available vẫn = 98
reservation count cho req-123 vẫn = 1
```

### 39.3. Tránh test assertions phụ thuộc Java memory

Một object `item` từ transaction cũ không thay cho một query mới đến DB.

---

# Phần IX — Observability, alerting và runbook

## 40. Metrics cần đo

| Metric | Ý nghĩa |
| --- | --- |
| DB connection acquisition p95/p99 | Pool bị nghẽn hay không |
| Pool active/idle/pending | Capacity và connections chờ |
| JDBC connection errors | Lỗi driver/network |
| SQLSTATE counts | Phân loại nguyên nhân |
| Transaction commit failures | Các failures ở phase rủi ro |
| Rollback attempt failures | Cleanup không hoàn tất |
| Retry attempts per request | Có retry storm không |
| Retry success after recovery | Khả năng tự phục hồi |
| Idempotency hit/conflict count | Retries/dedup |
| Unknown outcome count | Những lệnh cần reconciliation |
| Readiness unavailable duration | Độ dài gián đoạn |
| Recovery time | Từ DB restored đến request thành công |
| DB connection count | Tránh reconnect storm |
| DLQ/pending commands | Durable backlog chưa xử lý |

### 40.1. Không log password hoặc full JDBC URL có credentials

Troubleshooting outage dễ khiến team bật logging chi tiết. Cần redaction trước khi đưa traces/logs lên hệ thống tập trung.

### 40.2. Transaction phase phải có trong log

```text
operation=reserveStock
requestId=req-123
attempt=1
dbPhase=COMMIT
errorCategory=CONNECTION_UNAVAILABLE
outcome=UNKNOWN
nextAction=RECONCILE
```

Đây là telemetry đúng mục đích hơn:

```text
Database error, retrying...
```

### 40.3. Correlation IDs không thay idempotency key

Correlation ID dùng trace một request execution. Idempotency key đại diện **cùng một business command qua retries**. Có thể liên quan nhưng không đồng nhất.

---

## 41. Runbook khi DB mất kết nối

Một runbook vận hành có thể theo thứ tự:

1. Xác nhận phạm vi: một instance hay toàn cluster?
2. Kiểm tra readiness, pool pending, connection acquisition errors.
3. Xác định điểm lỗi: acquire, query, flush hay commit.
4. Kiểm tra DB primary/replica, network, DNS, TLS, auth và `max_connections`.
5. Ngăn retry storms bằng backpressure/circuit breaker nếu cần.
6. Bảo đảm failed EntityManagers/transactions được cleanup theo framework.
7. Khôi phục đường kết nối, secret hoặc DB service.
8. Kiểm tra new connections và business read/write an toàn.
9. Đối soát requests có outcome unknown bằng idempotency records.
10. Resume durable work queues/jobs theo checkpoint.
11. Theo dõi backlog, error rates, lock waits và pool size.
12. Ghi incident timeline, nguyên nhân, thời gian phục hồi và preventive actions.

### 41.1. Không “restart tất cả” như thao tác duy nhất

Restart có thể làm pool mới kết nối lại nhưng không giải quyết:

- Password đã bị revoke.
- TLS certificate sai.
- Migration/schema mismatch.
- DB primary không có leader.
- Commit outcomes còn phải reconcile.
- Retry storm sau khởi động.

### 41.2. Không xóa idempotency records để “chạy lại cho sạch”

Xóa history có thể khiến các requests đã commit được thực hiện lần hai. Cần retention/audit đúng.

---

# Phần X — Ma trận kiểm thử

## 42. Bộ kịch bản tối thiểu

| Kịch bản | Trigger | Điều cần khẳng định |
| --- | --- | --- |
| DB down trước request | Cut proxy | Fail fast theo timeout, không false success |
| DB down trong SELECT | Cắt query đang chạy | Cleanup, new-context read phục hồi |
| DB down trước flush | Cut trước flush | No partial commit, cleanup |
| DB down sau flush trước commit | Cut khi transaction active | Không suy flush là commit |
| COMMIT ACK lost | Controlled failpoint | Reconcile, idempotency, không duplicate |
| Response HTTP lost sau commit | Drop response | Same requestId trả same outcome |
| DB restart | Stop/start test container hoặc proxy | Pool tự cấp new connections |
| DB primary failover | HA test environment | Writes đi primary mới, DNS/TLS đúng |
| Replica lag | Delay replication | Không dùng stale read để đoán commit |
| Invalid password | Revoke/rotate auth | Không retry vô hạn, không log secret |
| TLS hostname mismatch | Untrusted endpoint | Connection bị từ chối an toàn |
| Pool exhausted | Giữ connections/queries | Backpressure, bounded waiting |
| Deadlock/serialization | Concurrent transactions | Retry entire unit of work mới |
| Unique conflict | Duplicate requestId | Deduplicate/verify payload |
| Batch import outage | Cut giữa chunks | Atomicity hoặc checkpoint semantics |
| Concurrent retries cùng ID | Two callers | Chỉ một logical reservation |
| DB unavailable dài | Extended proxy cut | Không leak threads/queue/memory |
| DB trở lại | Reconnect | Readiness phục hồi và metric ghi nhận |
| Unknown outcome queue | Reconciliation worker | Pending requests được xử lý theo contract |
| Rollback fails | Lost connection | Original error được bảo toàn |

### 42.1. Một test case không thay toàn bộ ma trận

Chỉ test `postgres.stop()` rồi thấy repository ném exception chưa đủ kết luận application phục hồi an toàn sau commit ambiguity.

### 42.2. Một phần cần kiểm thử ở HA environment

Testcontainers một PostgreSQL instance không mô phỏng đầy đủ primary election, replication lag, fencing hoặc DNS failover. Những phần đó cần môi trường tích hợp phù hợp.

---

# Phần XI — Những ngộ nhận thường gặp

## 43. “Mất connection nghĩa là transaction chắc chắn rollback”

Không đúng khi mất ACK quanh commit. Outcome có thể không xác định từ góc nhìn client.

## 44. “`em.isOpen()` true nghĩa là có thể tiếp tục”

Không đúng. EntityManager có thể còn open nhưng transaction/context đã lỗi.

## 45. “`em.clear()` sửa được connection hỏng”

Không. Clear detach entities, không làm DB session hoặc transaction rollback-only khỏe lại.

## 46. “Gọi `flush()` thành công nghĩa là dữ liệu đã được lưu bền vững”

Không. Flush không phải commit; các writes chưa commit có thể rollback.

## 47. “Chỉ cần retry cùng SQL statement”

Không đúng sau transaction failure. Retry cần unit of work mới và re-read/re-evaluate business state.

## 48. “Một `@Retryable` trên `@Transactional` luôn tạo transaction mới”

Không được suy như vậy nếu chưa biết proxy/advice ordering, method invocation và transaction boundaries. Test thực tế flow retry và rollback.

## 49. “Hikari tự động bảo đảm request không chạy hai lần”

Không. Pool chỉ quản lý connections, không hiểu idempotency của business commands.

## 50. “HTTP 500 nghĩa là DB không commit”

Không. Response có thể mất sau commit, hoặc commit ACK bị mất.

## 51. “Không tìm thấy record trên replica chứng minh primary chưa commit”

Không. Replica có thể lag; reconciliation cần đọc nguồn authoritative.

## 52. “Tăng retry count luôn tăng độ ổn định”

Không. Retry storm có thể làm database outage kéo dài hơn. Cần retry budget/backoff/circuit breaker.

## 53. “Mọi SQLException class 08 đều có thể retry write”

Không. Phải biết transaction phase và commit outcome.

## 54. “Authentication failed cứ retry cho đến khi thành công”

Không. Có thể credential sai/revoked; cần rotation/config fix.

## 55. “DB restart rồi restart app là đủ”

Có thể còn requests outcome unknown, stale pool metrics và job checkpoints chưa reconcile.

## 56. “Test với mock repository đã chứng minh failover”

Không. Mock không kiểm tra TCP, JDBC driver, pool hoặc DB state.

## 57. “Dùng `Thread.sleep(200)` bảo đảm đúng pha commit”

Không. Scheduling không deterministic; dùng synchronization/failpoints phù hợp.

## 58. “`@DataJpaTest` persistAndFlush đã test commit”

Không. Spring test thường rollback; cần commit boundary thật.

## 59. “Outbox event gửi hai lần là lỗi outbox”

Outbox thường cung cấp ít nhất một lần giao tùy thiết kế; consumer nên idempotent/deduplicate bằng event ID. Không suy exactly-once end-to-end từ một database transaction.

## 60. “Mất kết nối đang giữ locks thì locks lập tức biến mất”

Không luôn. Với network blackhole, server có thể chưa phát hiện client mất và session/transaction có thể sống đến timeout.

---

# Phần XII — Bài tập tình huống có lời giải

## 61. Ba mươi tình huống

### Bài 1. DB không kết nối được trước khi query

**Lời giải:** Phân loại dependency unavailable, timeout có giới hạn; nếu retry, phải mở transaction/context mới.

### Bài 2. EntityManager vẫn open sau SQLException

**Lời giải:** `isOpen()` không chứng minh transaction/context an toàn. Rollback/cleanup theo ownership và discard context.

### Bài 3. Một UPDATE đã flush rồi network mất

**Lời giải:** Flush không commit. Sau recovery dùng fresh context để verify DB state; không dùng Java object từ failed attempt.

### Bài 4. Network mất sau khi gửi COMMIT

**Lời giải:** Outcome có thể unknown. Không retry write mù; reconcile theo idempotency key.

### Bài 5. Client không nhận HTTP 200 nhưng DB đã commit

**Lời giải:** Client retry cùng requestId, server trả prior result, không tạo operation thứ hai.

### Bài 6. RequestId trùng nhưng quantity khác

**Lời giải:** Báo idempotency conflict; không coi hai commands khác nhau là một kết quả.

### Bài 7. Chỉ check exists(requestId) trước INSERT

**Lời giải:** Race condition vẫn tồn tại; cần UNIQUE/PK ở DB và xử lý conflict.

### Bài 8. Query từ read replica trả “not found”

**Lời giải:** Replica có thể lag. Không dùng để kết luận commit trên primary thất bại.

### Bài 9. Mất kết nối trong read-only transaction

**Lời giải:** Có thể retry trên new context nếu thực sự không có side effects, vẫn áp deadline/backoff.

### Bài 10. SQLSTATE 08006 ở pha COMMIT

**Lời giải:** Connection failure nhưng chưa biết commit outcome. Reconcile.

### Bài 11. SQLSTATE 28P01

**Lời giải:** Invalid password PostgreSQL; điều tra credentials/rotation, không retry vô hạn.

### Bài 12. SQLSTATE 40001

**Lời giải:** Serialization failure; có thể retry **toàn transaction** bằng context mới nếu business operation an toàn.

### Bài 13. SQLSTATE 23505 khi retry requestId

**Lời giải:** Có thể record cũ đã commit. Query và so sánh payload; không chỉ trả generic 500.

### Bài 14. Hikari `connection-timeout=3000`

**Lời giải:** Thường giới hạn 3 giây chờ lấy connection, không phải 3 giây cho mọi SQL query.

### Bài 15. pgJDBC `connectTimeout=3`

**Lời giải:** Thường tính bằng giây theo pgJDBC; khác đơn vị Hikari milliseconds.

### Bài 16. Socket timeout khi chờ commit response

**Lời giải:** Giới hạn chờ, không bảo đảm rollback; outcome cần đối soát.

### Bài 17. Database down, liveness trả DOWN và Kubernetes restart mọi pods

**Lời giải:** Có thể gây restart storm. Phân biệt readiness/liveness và điều chỉnh policy theo kiến trúc.

### Bài 18. Breaker OPEN

**Lời giải:** Fail fast với dependency, không tự xác nhận transaction cũ rollback.

### Bài 19. Test stop PostgreSQL rồi restart app

**Lời giải:** Chưa test pool self-recovery. Giữ cùng process/pool, phục hồi DB rồi verify new connections.

### Bài 20. Toxiproxy cut nhưng DataSource vẫn dùng direct JDBC URL

**Lời giải:** Fault injection không có tác dụng. Phải route toàn bộ JDBC traffic qua proxy.

### Bài 21. Sleep rồi cut “ngay trước commit”

**Lời giải:** Timing không deterministic. Dùng test-specific latch/failpoint để kiểm soát phase.

### Bài 22. Test chỉ assert SQLException

**Lời giải:** Chưa đủ. Verify rollback/commit state, cleanup, recovery, retry bound và idempotency.

### Bài 23. Connection pool trả stale connection sau restart

**Lời giải:** Test pool validation/eviction/new connection và success sau recovery.

### Bài 24. Worker nhập 10.000 rows, commit theo chunks

**Lời giải:** Resume bằng checkpoint/idempotency, không retry toàn file gây duplicates.

### Bài 25. App dùng `@Transactional` với retry loop bên trong

**Lời giải:** Có thể tiếp tục trong rollback-only transaction. Đặt retry ngoài transaction boundaries.

### Bài 26. Spring self-invocation tới REQUIRES_NEW

**Lời giải:** Có thể bypass proxy advice. Dùng bean khác/TransactionTemplate và kiểm tra transaction boundaries.

### Bài 27. Không log DB password nhưng log full JDBC URL chứa password

**Lời giải:** Vẫn rò secret. Tách credential khỏi URL và redact logs.

### Bài 28. Failed rollback cũng ném exception

**Lời giải:** Bảo toàn primary error và gắn suppressed rollback failure, cleanup context.

### Bài 29. Server down lâu khiến queue request tăng vô hạn

**Lời giải:** Áp concurrency/queue limits, backpressure, error contract hoặc durable work queue có ownership rõ.

### Bài 30. Database hồi phục nhưng vẫn còn commands unknown outcome

**Lời giải:** Chạy reconciliation theo requestId trên authoritative database, xử lý payload mismatch và cập nhật kết quả trước khi retry.

---

## 62. Checklist thiết kế kiểm thử phục hồi

### Fault model

1. Có phân biệt lỗi trước connect, trong read/write, flush và commit?
2. Có kiểm thử connection reset khác read timeout không?
3. Có kiểm thử DB restart và failover riêng?
4. Có test authentication/TLS failure để tránh retry nhầm?
5. Có xác nhận fault proxy nằm trên JDBC path thật?
6. Có điều khiển fault bằng synchronization thay vì sleep may rủi?
7. Có cleanup/reconnect trong finally?
8. Có chạy fault tests trên môi trường tách production?

### Transaction và JPA

9. Có rollback/close failed application-managed EM?
10. Với Spring/JTA, có để transaction manager quản lý cleanup?
11. Có tránh tái sử dụng managed entity state sau rollback?
12. Có mở new transaction/context cho retry?
13. Có test exception phát tại `commit()`?
14. Có phân biệt flush và committed data?
15. Có test rollback atomicity trên nhiều bảng?
16. Có verify bằng fresh connection/EM?

### Retry và idempotency

17. Retry owner có rõ không?
18. Có bounded attempts, backoff, jitter và deadline?
19. Có phân loại transient, auth, constraint, business error?
20. Có coi commit ACK lost là UNKNOWN?
21. Có durable idempotency key/unique constraint?
22. Có so sánh payload khi requestId trùng?
23. Có đối soát qua authoritative source, không replica lag?
24. Có tránh duplicate external effects?
25. Có retention policy cho idempotency records?
26. Có test two concurrent retries cùng key?

### Pool và vận hành

27. Hikari connection acquisition có finite timeout?
28. JDBC connect/socket timeout có đúng đơn vị theo driver?
29. Có test pool thay stale connections sau DB restart?
30. Có test service hồi phục không restart JVM?
31. Readiness/liveness có semantics riêng?
32. Có giới hạn request concurrency khi DB down?
33. Có tránh reconnect/retry storm?
34. Có metrics recovery time, rollback failures, unknown outcomes?
35. Có runbook/alert và reconciliation backlog?

### Test environment

36. Có dùng DB/driver/provider version phù hợp?
37. Có chạy migrations thật khi test schema fidelity?
38. Có tránh `@DataJpaTest` rollback che commit?
39. Có tránh dùng entity object từ failed context để assert DB?
40. Có test success/rollback/unknown outcome paths?
41. Có test startup unavailable lẫn runtime disconnect?
42. Có test stale replica và failover nếu hệ thống dùng HA?
43. Có giới hạn timeout để test không treo CI?
44. Có giữ faults test-only, không tạo outage production?
45. Có báo cáo rõ những failure modes chưa mô phỏng được?

---

## 63. Sơ đồ quyết định sau database disconnect

```text
                  Database connection failure
                              |
                              v
                      Identify error phase
                              |
        +---------------------+---------------------+
        |                     |                     |
        v                     v                     v
  Before any write       During active TX        Around COMMIT
        |                     |                     |
        v                     v                     v
  Stop attempt          Stop/rollback/close      OUTCOME UNKNOWN
        |                     |                     |
        v                     v                     v
  Retry only with       Do not reuse failed      Reconnect and
  budget/new context    persistence context      reconcile by key
        |                     |                     |
        +----------+----------+                     |
                   |                                |
                   v                                v
          Classify failure                    Committed record?
                   |                         /              \
          +--------+--------+              Yes             Unclear/no
          |                 |                |                  |
          v                 v                v                  v
     Retryable         Not retryable     Verify payload    Follow settlement/
          |                 |            return prior      idempotent retry
          v                 v            outcome           policy
   Bounded backoff     Fix/return error
          |
          v
   NEW transaction/context
   Reload current state
   Re-evaluate business invariants
   Commit and confirm
```

Điểm quyết định quan trọng nhất không phải “có bắt được exception không”, mà là **điều gì đã xảy ra trong transaction, dữ liệu nào còn đáng tin và việc thực hiện lại business command có gây hiệu ứng trùng lặp không**.

---

## 64. Kết luận

Kiểm thử khả năng phục hồi khi cơ sở dữ liệu ngắt kết nối là kiểm thử **tính đúng đắn và vận hành**, không chỉ là kiểm tra ứng dụng có reconnect được sau một exception.

Những điều cần ghi nhớ:

1. **Phân biệt thời điểm outage:** trước connect, trong query, khi flush hay tại commit dẫn đến rủi ro khác nhau.
2. **Mất connection không luôn đồng nghĩa rollback**, đặc biệt khi commit ACK không đến.
3. **Không dùng tiếp EntityManager/persistence context đã lỗi** nếu chưa có bảo đảm an toàn; cleanup và tạo context mới.
4. **Rollback không tự undo Java object fields**; kiểm tra persisted state bằng new context.
5. **`flush()` không bảo đảm commit**; exception có thể đến ở commit hoặc transaction outcome không rõ.
6. **Retry phải nằm ngoài failed transaction**, có classifier, backoff, jitter, deadline và attempt budget.
7. **Write retries cần idempotency**: durable request key, unique constraint, payload matching và reconciliation.
8. **Không dùng replica lag làm bằng chứng commit chưa xảy ra**.
9. **Connection pool chỉ quản lý connections**, không giải quyết duplicate business operations.
10. **Readiness khác liveness**; tránh restart/retry storms khi database tạm thời down.
11. **Testcontainers + Toxiproxy** giúp mô phỏng fault thực; mocks chỉ kiểm tra một lớp logic.
12. **Kiểm thử commit ACK lost cần fault model đủ chính xác**, không chỉ cắt mạng ngẫu nhiên rồi suy luận kết quả.
13. **Sau recovery, verify bằng fresh EntityManager và authoritative DB**, không đọc lại object cũ trong L1.
14. **Kiểm thử cả lỗi và tự phục hồi**, pool stale connections, failover, startup down, timeout budgets và operational metrics.
15. **Một hệ thống phục hồi đúng phải giữ nguyên business invariants**: không trừ kho hai lần, không tạo duplicate reservations và không báo thành công khi dữ liệu chưa được xác minh.

**Khả năng phục hồi thực sự không chỉ là “kết nối lại được”, mà là sau một sự cố mạng, hệ thống biết khi nào nên dừng, khi nào cần đối soát, khi nào có thể retry và làm thế nào để tiếp tục phục vụ mà không tạo ra trạng thái dữ liệu sai.**
