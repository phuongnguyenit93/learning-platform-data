# Xử lý kết quả commit chưa xác định khi kết nối bị gián đoạn trong JPA

Trong ứng dụng Java Persistence API (JPA), `commit()` là một ranh giới quan trọng: transaction kết thúc thành công thì những thay đổi cần được lưu bền vững theo chính sách database; nếu rollback thì những thay đổi của transaction không được công nhận. Tuy nhiên, có một trường hợp khó hơn “thành công” hoặc “thất bại”:

> Ứng dụng đã gửi yêu cầu COMMIT, nhưng kết nối với database bị gián đoạn trước khi nó nhận được câu trả lời đáng tin cậy. **Transaction có thể đã commit, có thể đã rollback, hoặc kết quả vẫn chưa xác minh được.**

Tình huống này được gọi là **ambiguous commit outcome**, **uncertain transaction outcome** hoặc **commit result unknown**. Nó có thể xảy ra khi mất mạng, TCP connection reset, database restart/failover, client timeout, proxy ngắt kết nối hoặc ứng dụng bị crash đúng cửa sổ giữa việc gửi commit và nhận kết quả.

Đây là bài toán về **độ tin cậy của hệ thống phân tán**, không phải chỉ là một exception của ORM. Hibernate, EclipseLink, Spring hoặc JDBC driver có thể bọc tình huống thành những exception khác nhau, nhưng khi acknowledgment không đến được client, chỉ nhìn exception class chưa chắc đủ để kết luận dữ liệu đã được lưu hay chưa.

Bài học thuộc chương **Lỗi và phục hồi** trong chủ đề **Data Persistence Relational Access ORM JPA**. Mục tiêu là thiết kế quy trình sao cho:

- Không nhầm `flush` với `commit`.
- Không tự kết luận “mất kết nối nghĩa là rollback”.
- Không retry như một thao tác hoàn toàn mới, dẫn đến duplicate orders, transfers hoặc external charges.
- Có **idempotency key**, ràng buộc uniqueness và **bằng chứng commit** được lưu atomically với dữ liệu nghiệp vụ.
- Xác minh bằng một transaction/kết nối mới, trên nguồn dữ liệu có consistency phù hợp.
- Biết khi nào phải trả `UNKNOWN`, yêu cầu retry cùng key, hoặc chuyển đối soát/manual review.
- Tách kết quả database commit khỏi publish message, gọi payment gateway và những side effects khác.
- Kiểm thử trường hợp mất ACK và những race conditions mà unit test bình thường khó mô phỏng.

---

## 1. Timeline của một database transaction

Một luồng JPA thường trông như sau:

```text
Ứng dụng                            Persistence provider                Database
    |                                      |                                |
    |  em.persist(order)                   |                                |
    |------------------------------------->|                                |
    |                                      |                                |
    |  em.flush() hoặc flush khi commit    |                                |
    |------------------------------------->|  INSERT/UPDATE SQL             |
    |                                      |------------------------------->|
    |                                      |  SQL đã thực thi trong tx      |
    |                                      |<-------------------------------|
    |                                      |                                |
    |  tx.commit()                         |                                |
    |------------------------------------->|  COMMIT                        |
    |                                      |------------------------------->|
    |                                      |                                |
    |                                      |  DB quyết định commit/rollback |
    |                                      |                                |
    |                                      |  ACK kết quả                    |
    |                                      |<-------------------------------|
    |  commit() trả bình thường            |                                |
    |<-------------------------------------|                                |
```

Ở luồng bình thường, sau khi nhận thành công từ `commit()`, caller có cơ sở để coi transaction database đã commit theo contract của DB/driver/transaction manager.

Nhưng nếu đường truyền bị đứt **sau khi database đã nhận COMMIT** mà trước khi client nhận ACK:

```text
JPA / JDBC Client                         Database
       |                                       |
       |---------- COMMIT ------------------->|
       |                                       |
       |                        COMMIT đã hoàn tất
       |                                       |
       |        X mất kết nối trước ACK        |
       |                                       |
       |<---- ACK không đến được client ------|
       |
       v
   Exception / timeout
   KẾT QUẢ CHƯA XÁC ĐỊNH
```

Client không thể suy ra “DB chưa ghi gì” chỉ vì nó không đọc được response.

### 1.1. Một COMMIT có hai khía cạnh

Cần phân biệt:

1. **Quyết định của database**: transaction đã được commit bền vững hay rollback theo database semantics?
2. **Tri thức của client**: ứng dụng đã nhận được kết quả commit đáng tin cậy chưa?

Một transaction có thể **đã commit trên database** trong khi client **không biết điều đó**.

### 1.2. Kết nối hỏng không xóa một transaction đã commit

Nếu database đã commit, gọi `rollback()` trên kết nối cũ sau đó không thể quay ngược commit. Kết nối có thể đã bị đóng hoặc bị transaction manager loại bỏ; thử rollback chỉ có thể thất bại, không phải bằng chứng transaction đã bị hủy.

### 1.3. Chưa gửi COMMIT là tình huống khác

Nếu chắc chắn ứng dụng chưa gửi COMMIT và database session bị ngắt, database thường rollback transaction đang mở khi session chấm dứt theo semantics tương ứng. Nhưng phân loại một sự cố mạng theo thời điểm chính xác đó không phải lúc nào cũng khả thi từ phía client.

**Không dùng một thông điệp “connection lost” chung để kết luận commit chưa tới server.**

---

## 2. Flush không đồng nghĩa commit

Một lỗi tư duy rất phổ biến:

```java
em.persist(order);
em.flush();

System.out.println("Order đã lưu thành công");
```

`em.flush()` đồng bộ những thay đổi cần thiết của persistence context xuống database **trong transaction**. Nó không tự biến transaction thành committed transaction.

### 2.1. Flush thành công vẫn có thể rollback

```text
BEGIN
    INSERT order
    FLUSH thành công
    INSERT ledger -> constraint violation
ROLLBACK

=> order không được commit
```

### 2.2. @PostPersist cũng không phải after-commit

Một callback `@PostPersist` có thể chạy sau INSERT/flush, nhưng transaction có thể rollback sau đó. Không dùng callback để phát external event với ý nghĩa “đã commit”.

### 2.3. Generated ID không phải biên nhận commit

Với `GenerationType.IDENTITY`, provider có thể phải INSERT sớm để nhận ID. Một `order.getId()` khác null **không chứng minh** transaction đã commit.

### 2.4. Commit bị mất ACK sau một flush thành công

Đây chính là trường hợp nguy hiểm: SQL trong transaction đã chạy, ứng dụng gọi commit, nhưng connection reset. Không biết liệu database đã commit những SQL đó.

---

## 3. Phân biệt các trạng thái kết quả

| Trạng thái | Ứng dụng biết gì? | Hành động khái quát |
|---|---|---|
| `CONFIRMED_COMMITTED` | Có xác nhận đáng tin cậy transaction đã commit | Trả thành công, phát workflow theo contract |
| `CONFIRMED_ABORTED` | Có xác nhận đáng tin cậy transaction bị rollback/không commit | Có thể retry theo business policy |
| `OUTCOME_UNKNOWN` | Không có bằng chứng chắc chắn commit hay rollback | Đối soát; không retry bằng identity mới |
| `BUSINESS_REJECTED` | Validation/invariant từ chối trước khi ghi hoặc transaction abort rõ | Trả lỗi nghiệp vụ, không nhầm unknown |
| `ALREADY_APPLIED` | Tìm được transaction trước đã commit cùng idempotency key và payload | Trả lại kết quả đã xác nhận |
| `CONFLICTING_REQUEST` | Cùng idempotency key nhưng payload khác | Báo xung đột, không ghi thêm |

Đây là **trạng thái ứng dụng thiết kế**, không phải một enum chuẩn của JPA. JPA API không cung cấp một method portable tên `getCommitOutcome()` để cho biết chính xác transaction đã tới đâu sau khi connection bị mất.

### 3.1. `OUTCOME_UNKNOWN` khác `FAILED`

Một exception từ commit boundary có thể phản ánh:

- Transaction đã rollback thực sự.
- Transaction đã commit nhưng ACK bị mất.
- Transaction chưa hoàn tất tại thời điểm client ngắt kết nối.
- Một lỗi provider/driver khiến thông tin không còn đủ để phân loại.

Nếu không có evidence để phân biệt, trả “thất bại và chưa ghi gì” là tuyên bố vượt quá điều ứng dụng biết.

### 3.2. Không được coi mọi commit exception là ambiguous

Một số database errors cung cấp thông tin đủ rõ rằng transaction đã aborted, chẳng hạn một conflict hoặc constraint failure được báo trước commit thành công. Điều cần thiết là **classify theo đường thực thi, driver/database và transaction manager**, không chuyển tất cả errors thành “unknown”.

Tuy nhiên, khi mất kết nối hoặc timeout ở cửa sổ COMMIT mà không có definitive outcome, nên xử lý theo hướng **có thể đã commit**.

---

## 4. Ví dụ nghiệp vụ: Tạo đơn hàng

Giả sử khách gửi yêu cầu:

```http
POST /orders
Idempotency-Key: 9b7d1a4d-73a5-4a56-bcf2-f9b29a63c908
Content-Type: application/json

{
  "tenantId": 42,
  "customerId": 801,
  "items": [
    { "productId": 125, "quantity": 2 }
  ]
}
```

Backend thực hiện:

1. Tạo Order.
2. Lưu OrderLine và các bản ghi nghiệp vụ liên quan.
3. Ghi transaction receipt.
4. Commit.
5. Trả HTTP response cho client.

Nếu connection tới database mất đúng tại bước 4, backend có thể không biết Order đã được commit.

### 4.1. Retry không an toàn

Nếu backend hoặc client thử lại bằng một request ID mới:

```text
Attempt 1: CREATE Order#1001 -> DB đã commit, ACK bị mất
Attempt 2: CREATE Order#1002 -> DB commit
```

Một thao tác nghiệp vụ có thể biến thành **hai đơn hàng**.

### 4.2. Điều kiện để retry an toàn

Cả hai attempts phải được nhận diện là **cùng một operation** nhờ idempotency key ổn định; database phải ngăn cùng operation tạo nhiều Orders.

### 4.3. Trả lỗi mạng không đồng nghĩa nghiệp vụ thất bại

Ngay cả nếu HTTP request kết thúc bằng 500/503/timeout, Order có thể đã tồn tại. API contract cần nói rõ caller phải retry bằng **cùng idempotency key**, không tự tạo request mới.

---

## 5. Idempotency là gì?

Một operation **idempotent** khi việc thực hiện lại cùng yêu cầu có cùng tác động nghiệp vụ như thực hiện một lần theo contract.

Đối với create-order:

```text
Operation key: K
Payload: P

Lần đầu    -> tạo Order O
Lần retry  -> xác nhận/trả lại Order O
Lần retry  -> vẫn là Order O
```

Không được tạo thêm O2, O3 cho cùng K/P.

### 5.1. Idempotency không phải chỉ là “đừng gửi request trùng”

Network retry, reverse proxy, client timeout và ứng dụng crash là những hành vi bình thường trong hệ thống phân tán. Server phải hỗ trợ duplicate delivery nếu nghiệp vụ không chấp nhận duplicate effect.

### 5.2. Khóa phải ổn định qua retries

Một UUID mới được sinh trong mỗi retry vô hiệu hóa idempotency. Khóa nên do caller tạo và lưu ổn định cho một command, hoặc được server cấp trước khi chạy command.

### 5.3. Phạm vi khóa

Thường cần uniqueness theo `(tenant_id, idempotency_key)` hoặc phạm vi account/merchant phù hợp. Chỉ dùng key global mà không kiểm soát tenant scope có thể gây collision/security issues.

### 5.4. Cùng key, payload khác

Nếu request key K đã được dùng để tạo một đơn với items A, một request mới dùng K nhưng items B không được trả success như cùng operation. Phải kiểm tra **payload fingerprint** và trả conflict.

### 5.5. Key không phải bí mật hay auth token

Idempotency key phục vụ định danh operation, không thay authentication/authorization. Server phải xác minh caller có quyền với tenant/customer trước khi trả receipt hoặc resource đã tạo.

---

## 6. Ràng buộc UNIQUE ở database là lớp bảo vệ quyết định

Một process-local cache hoặc một `ConcurrentHashMap` không đủ khi hệ thống có nhiều app instances hoặc restart.

Ví dụ bảng Orders:

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    request_id VARCHAR(100) NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,

    CONSTRAINT uk_orders_tenant_request
        UNIQUE (tenant_id, request_id)
);
```

Điều kiện:

```text
Cùng tenant + request_id => tối đa một Order
```

### 6.1. Precheck không đủ

```java
if (!repository.existsByRequestId(requestId)) {
    repository.save(new Order(...));
}
```

Hai requests đồng thời đều có thể thấy chưa có, rồi cùng INSERT. Chỉ database constraint/locking phù hợp mới giải quyết race bền vững.

### 6.2. UNIQUE constraint không đồng nghĩa mọi workflow đã idempotent

Nếu transaction còn gọi payment gateway **trước khi INSERT unique key**, hai retries vẫn có thể charge hai lần. Thiết kế phải bao phủ **mọi side effect**, không chỉ số Order rows.

### 6.3. Khóa cần đại diện cho operation thật

Nếu cùng business operation có nhiều bảng, cần bảo đảm receipt và business writes nằm trong cùng transaction; nếu riêng bảng Orders có UNIQUE nhưng ledger/outbox ghi ngoài transaction, duplicate side effects vẫn có thể xảy ra.

---

## 7. Transaction receipt: Bằng chứng để đối soát

Một cách thiết kế đáng tin cậy là ghi **receipt row** trong **cùng database transaction** với dữ liệu nghiệp vụ.

SQL minh họa:

```sql
CREATE TABLE order_operation_receipt (
    tenant_id BIGINT NOT NULL,
    request_id VARCHAR(100) NOT NULL,
    payload_digest CHAR(64) NOT NULL,
    order_id UUID NOT NULL,
    outcome VARCHAR(30) NOT NULL,
    committed_at TIMESTAMP NOT NULL,

    CONSTRAINT pk_order_operation_receipt
        PRIMARY KEY (tenant_id, request_id),

    CONSTRAINT uk_receipt_order
        UNIQUE (order_id)
);
```

`outcome` của receipt lưu trong cùng transaction có thể là `"SUCCEEDED"` cho operation đã hoàn tất business writes. Tên cột `committed_at` trong ví dụ là timestamp mang ý nghĩa nghiệp vụ/ghi nhận; nếu nó được điền **trước** COMMIT, không nên coi là database commit timestamp chính xác. Trong hệ thống thực, đặt tên như `recorded_at` thường ít gây hiểu lầm hơn.

### 7.1. Tại sao ghi cùng transaction?

```text
BEGIN TRANSACTION
    INSERT orders(...)
    INSERT order_line(...)
    INSERT order_operation_receipt(...)
COMMIT
```

Nếu cùng một transactional database bảo đảm atomicity:

- Commit thành công → cả Order, Lines và Receipt đều committed.
- Rollback → cả ba đều không committed.

Receipt sẽ trở thành dấu vết có thể tra lại sau khi ứng dụng mất câu trả lời của `commit()`.

### 7.2. Receipt không phải log ghi trước giao dịch độc lập

Nếu receipt được commit ở transaction A, rồi Order ở transaction B, hệ thống có thể có receipt “thành công” trong khi Order chưa commit. Khi mục tiêu là xác nhận **một business transaction**, receipt phải ghi atomically với business state.

### 7.3. Có thể dùng chính row nghiệp vụ làm receipt

Nếu bảng Orders có `(tenant_id, request_id)` UNIQUE, `payload_digest` và đủ trạng thái, việc tìm Orders theo request ID cũng có thể xác nhận commit. Bảng receipt riêng hữu ích khi một operation tạo nhiều entities hoặc cần kết quả tổng hợp.

### 7.4. Giữ payload digest

`payload_digest` cần được tính trên representation đã canonicalize ổn định của command. Không hash chuỗi JSON ngẫu nhiên nếu thứ tự fields, whitespace hoặc số học có thể đổi mà cùng meaning.

---

## 8. Mô hình JPA cho idempotent order

Entity Order:

```java
@Entity
@Table(
    name = "orders",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_orders_tenant_request",
        columnNames = {"tenant_id", "request_id"}
    )
)
public class PurchaseOrder {

    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "request_id", nullable = false)
    private String requestId;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(nullable = false)
    private String status;

    protected PurchaseOrder() {}

    public PurchaseOrder(
            UUID id,
            Long tenantId,
            String requestId,
            Long customerId) {

        this.id = id;
        this.tenantId = tenantId;
        this.requestId = requestId;
        this.customerId = customerId;
        this.status = "CREATED";
    }

    public UUID getId() { return id; }
}
```

Receipt:

```java
@Embeddable
public class OrderRequestKey implements Serializable {

    @Column(name = "tenant_id")
    private Long tenantId;

    @Column(name = "request_id")
    private String requestId;

    protected OrderRequestKey() {}

    public OrderRequestKey(Long tenantId, String requestId) {
        this.tenantId = tenantId;
        this.requestId = requestId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderRequestKey that)) {
            return false;
        }

        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(requestId, that.requestId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, requestId);
    }
}
```

```java
@Entity
@Table(name = "order_operation_receipt")
public class OrderOperationReceipt {

    @EmbeddedId
    private OrderRequestKey key;

    @Column(name = "payload_digest", nullable = false)
    private String payloadDigest;

    @Column(name = "order_id", nullable = false)
    private UUID orderId;

    @Column(nullable = false)
    private String outcome;

    @Column(name = "committed_at", nullable = false)
    private Instant recordedAt;

    protected OrderOperationReceipt() {}

    public OrderOperationReceipt(
            OrderRequestKey key,
            String payloadDigest,
            UUID orderId) {
        this.key = key;
        this.payloadDigest = payloadDigest;
        this.orderId = orderId;
        this.outcome = "SUCCEEDED";
        this.recordedAt = Instant.now();
    }

    public String getPayloadDigest() {
        return payloadDigest;
    }

    public UUID getOrderId() { return orderId; }

    public String getOutcome() { return outcome; }
}
```

Các imports trong code minh họa dùng `jakarta.persistence.*`, `java.io.Serializable`, `java.util.*`, `java.time.Instant`. Phần thực hành có thể thêm getters, validation, entity lifecycle/column types tương ứng với database.

### 8.1. UUID được tạo trước INSERT

Ở ví dụ này Order ID là UUID do application tạo, để receipt/outbox có thể tham chiếu ID trước khi database phát generated identity. Đây là một lựa chọn; có thể dùng database-generated ID nếu workflow được thiết kế đúng.

### 8.2. Composite receipt key

`@EmbeddedId` giúp ánh xạ `(tenant_id, request_id)` thành identity. `equals/hashCode` phải ổn định, đúng kiểu và tránh phụ thuộc mutable state.

### 8.3. Đừng tự suy ra receipt chắc chắn là committed từ field recordedAt

Row chỉ chứng minh commit khi được **đọc thấy ở một transaction độc lập qua nguồn dữ liệu đáng tin cậy**, không phải vì app vừa gán `recordedAt`.

---

## 9. Ghi dữ liệu và receipt trong cùng transaction

Một Spring service riêng chịu trách nhiệm ghi transaction:

```java
@Service
public class OrderTransactionalWriter {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public UUID writeOnce(CreateOrderCommand command) {

        UUID orderId = UUID.randomUUID();

        PurchaseOrder order = new PurchaseOrder(
            orderId,
            command.tenantId(),
            command.requestId(),
            command.customerId()
        );

        OrderOperationReceipt receipt =
            new OrderOperationReceipt(
                new OrderRequestKey(
                    command.tenantId(),
                    command.requestId()
                ),
                command.payloadDigest(),
                orderId
            );

        em.persist(order);
        em.persist(receipt);

        // Có thể persist Lines và outbox ở đây
        // trong cùng transaction.

        return orderId;
    }
}
```

### 9.1. `@Transactional` commit sau khi method body hoàn tất

Với Spring AOP proxy thông thường, method body `writeOnce()` có thể return UUID trước khi transaction interceptor commit. Exception tại commit được caller nhìn thấy khi lời gọi qua proxy hoàn tất **với exception**, không nên coi việc method nội bộ đã `return` là commit thành công.

### 9.2. Không gọi `writeOnce()` bằng self-invocation

Nếu gọi một `@Transactional` method từ method khác trong **cùng bean** bằng `this.writeOnce(...)` dưới Spring proxy mode mặc định, transaction interceptor có thể không chạy. Ví dụ tách writer thành bean riêng để facade gọi qua proxy.

### 9.3. `em.flush()` không làm receipt được xác nhận

Ngay cả nếu thêm `em.flush()` sau persist, receipt vẫn thuộc uncommitted transaction. Dùng flush để kiểm tra SQL constraints sớm trong những tình huống cần thiết, không dùng nó làm commit acknowledgment.

---

## 10. Đối soát trên một kết nối/transaction mới

Khi kết quả commit không rõ, không tiếp tục kiểm tra trên EntityManager/connection đã gặp sự cố. Hãy mở **transaction mới** và query bằng một đường đọc có consistency phù hợp, ưu tiên primary database.

Ví dụ repository reader:

```java
@Service
public class OrderReceiptReader {

    @PersistenceContext
    private EntityManager em;

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        readOnly = true
    )
    public Optional<OrderOperationReceipt> find(
            Long tenantId,
            String requestId) {

        OrderRequestKey key =
            new OrderRequestKey(tenantId, requestId);

        OrderOperationReceipt receipt = em.find(
            OrderOperationReceipt.class,
            key,
            Map.of(
                "jakarta.persistence.cache.retrieveMode",
                CacheRetrieveMode.BYPASS
            )
        );

        return Optional.ofNullable(receipt);
    }
}
```

`CacheRetrieveMode.BYPASS` là một cách diễn đạt chuẩn để bỏ qua shared entity cache retrieval khi provider hỗ trợ; nó không tự ép data source thành primary, không giải quyết L1 đang có instance cũ và không bảo đảm database replication consistency.

### 10.1. Tại sao REQUIRES_NEW?

Đọc trên transaction khác giúp tránh phụ thuộc persistence context/connection bị hỏng. Nếu đang trong Spring, `REQUIRES_NEW` có thể suspend transaction hiện tại và tạo transaction khác theo transaction manager.

### 10.2. Facade không nên bao toàn bộ quy trình trong một transaction

Nếu facade cũng có một transaction lớn đang rollback-only, việc “đọc xác minh” có thể lẫn với transaction hỏng hoặc không nhìn thấy state committed. Có thể dùng một **facade không `@Transactional`**, gọi writer bean có transaction rồi gọi reader bean mở transaction độc lập.

### 10.3. Query primary, không mặc định replica

Một replica có thể chậm apply transaction. Nếu đọc replica và không thấy receipt, chưa thể suy ra primary chưa commit.

### 10.4. Receipt đọc thấy là bằng chứng mạnh; không thấy là bằng chứng yếu

Nếu receipt được ghi atomically với business state và đọc thấy trong một transaction tin cậy, có thể xác nhận business changes đã commit theo database consistency assumptions. Nhưng **không thấy receipt tại một thời điểm** không chứng minh transaction chắc chắn không commit: nó có thể chưa hoàn tất, nguồn đọc bị lag hoặc đường đối soát đang gặp lỗi.

---

## 11. Facade chuyển kết quả thành CONFIRMED, UNKNOWN hoặc CONFLICT

Một ví dụ Spring theo hướng tách transaction boundaries:

```java
public sealed interface SubmitOrderOutcome
    permits ConfirmedOrder, UnknownOrder, RejectedOrder {}

public record ConfirmedOrder(UUID orderId)
    implements SubmitOrderOutcome {}

public record UnknownOrder(String requestId)
    implements SubmitOrderOutcome {}

public record RejectedOrder(String reason)
    implements SubmitOrderOutcome {}
```

Facade:

```java
@Service
public class OrderSubmissionFacade {

    private final OrderTransactionalWriter writer;
    private final OrderReceiptReader reader;

    public OrderSubmissionFacade(
            OrderTransactionalWriter writer,
            OrderReceiptReader reader) {
        this.writer = writer;
        this.reader = reader;
    }

    public SubmitOrderOutcome submit(
            CreateOrderCommand command) {

        // Validate schema, actor, tenant và payload
        // trước khi thực hiện transaction.

        try {
            UUID id = writer.writeOnce(command);
            return new ConfirmedOrder(id);

        } catch (BusinessRejectedException rejected) {
            return new RejectedOrder(
                rejected.getSafeMessage()
            );

        } catch (RuntimeException failure) {

            // Ở đây còn có thể bao gồm lỗi definite,
            // duplicate-key hoặc commit outcome unknown.
            // Phải phân loại exception theo integration.

            Optional<OrderOperationReceipt> found;

            try {
                found = reader.find(
                    command.tenantId(),
                    command.requestId()
                );
            } catch (RuntimeException probeFailure) {
                return new UnknownOrder(
                    command.requestId()
                );
            }

            if (found.isPresent()) {
                OrderOperationReceipt receipt = found.get();

                if (!receipt.getPayloadDigest().equals(
                        command.payloadDigest())) {
                    return new RejectedOrder(
                        "Idempotency key reused with different payload"
                    );
                }

                return new ConfirmedOrder(
                    receipt.getOrderId()
                );
            }

            // Chưa thấy receipt KHÔNG chứng minh rollback.
            // Có thể cần bounded reconciliation/retry với
            // chính key này.
            return new UnknownOrder(command.requestId());
        }
    }
}
```

**Đây là skeleton minh họa flow**, không phải production-ready error taxonomy. `BusinessRejectedException`, `CreateOrderCommand` và DTOs cần được định nghĩa; exception classification và timeout policy phải gắn với stack thực tế.

### 11.1. Không classify mọi RuntimeException là commit-unknown một cách máy móc

Trong ví dụ, nhánh catch tổng quát **bảo thủ** chuyển sang probe/unknown để không tuyên bố rollback nhầm. Ứng dụng production cần phân biệt:
- Validation failure có thể xác định trước transaction.
- SQL integrity errors có thể xác định transaction abort.
- Connection I/O failure đúng cửa sổ commit.
- Duplicate-key conflict do retry cùng idempotency key.
- Timeout hoặc database failover.

### 11.2. Reader fail cũng có thể là UNKNOWN

Nếu database vẫn unavailable và không thể đọc receipt, không được trả “Order không tồn tại”.

### 11.3. Digest mismatch phải được xử lý an toàn

Cùng key nhưng payload khác là conflict. Không trả Order ID của request trước như thể request mới đã được xử lý.

### 11.4. Không để facade transaction phủ lên writer/readback

Façade nên giữ ranh giới rõ: writer transaction do proxy quản lý và reader có transaction mới, đồng thời route primary cho đối soát.

---

## 12. Vì sao không thể dùng rollback() để giải quyết tất cả?

JPA RESOURCE_LOCAL có thể viết:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    em.persist(order);
    em.persist(receipt);

    tx.commit();

} catch (RuntimeException failure) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
    }

    throw failure;

} finally {
    em.close();
}
```

Đây là mẫu dọn dẹp thường gặp khi lỗi, nhưng **không cung cấp bằng chứng rằng rollback đã đảo ngược một COMMIT có thể đã thành công**.

### 12.1. Commit có thể đã kết thúc trên database

Nếu database đã commit trước khi TCP connection reset, lệnh rollback trên client không thể hoàn tác committed transaction.

### 12.2. Transaction status cục bộ có thể thiếu thông tin

`tx.isActive()` chủ yếu phản ánh transaction state mà API/provider biết. Khi connection hỏng, nó không phải phép truy vấn magic về durable commit decision ở server.

### 12.3. Đóng EntityManager/connection hỏng

Sau lỗi nghiêm trọng trong JDBC/commit path, nên để transaction manager/pool loại bỏ connection không còn đáng tin cậy và không tiếp tục dùng EntityManager đó cho business work. Mở scope mới để đối soát.

### 12.4. Đừng nuốt lỗi cleanup

Nếu rollback/close cũng thất bại, giữ exception gốc và ghi nhận cleanup errors như suppressed details cho chẩn đoán; không thay kết luận outcome unknown thành “đã rollback”.

---

## 13. Trường hợp JTA và transaction manager

Trong môi trường Jakarta EE hoặc Spring với JTA, transaction manager có thể quản lý transaction thay vì ứng dụng trực tiếp gọi `EntityTransaction.commit()`.

### 13.1. Commit exception nằm ở transaction boundary

Một method EJB/Spring `@Transactional` có thể hoàn tất code body, nhưng exception xảy ra khi container/transaction interceptor cố commit sau đó.

### 13.2. Không tự gọi em.getTransaction() với JTA-managed EntityManager

Transaction ownership thuộc container/transaction manager. Không dùng RESOURCE_LOCAL code vào môi trường JTA như thể cùng semantics.

### 13.3. JTA status không phải oracle sau mất kết nối

Transaction manager có thể giữ transaction status hoặc recovery log, nhưng nếu tài nguyên DB mất liên lạc ở thời điểm quyết định commit, hệ thống vẫn có thể cần recovery/heuristic handling. Không dùng một status cục bộ thiếu kết nối để tuyên bố bền vững của mọi resources.

### 13.4. Distributed/XA transactions

Với nhiều resources XA, một số failure modes có thể dẫn tới trạng thái heuristic hoặc in-doubt. Đây là bài toán recovery transaction manager/XA logs và resource managers, khác với chỉ kiểm tra một row trong một database đơn. Không mặc định một JPA transaction bao nhiều hệ thống ngoài DB một cách atomic.

---

## 14. Spring @Transactional: Catch lỗi ở vị trí nào?

Giả sử:

```java
@Transactional
public UUID createOrder(CreateOrderCommand command) {
    em.persist(...);
    return orderId;
}
```

Code trong method có thể chạy đến `return`. Sau đó proxy thực hiện commit. Nếu commit ACK mất, **caller của proxy** nhận exception, không phải block `try/catch` nằm bên trong method lúc code đã return.

### 14.1. Tách facade và transactional writer

Một bean không transactional gọi một bean transactional khác:

```text
OrderSubmissionFacade.submit()
    |
    +--> OrderTransactionalWriter.writeOnce()
    |        [@Transactional begin ... commit]
    |
    +--> OrderReceiptReader.find()
             [new transaction / primary]
```

Đây là cách làm boundary rõ để facade có thể nhận commit exception.

### 14.2. Self-invocation làm mất proxy advice

`this.writeOnce()` trong cùng bean không nhất thiết đi qua Spring proxy. Khi đó `@Transactional` annotation trên writeOnce có thể không được áp dụng như mong đợi.

### 14.3. Transaction rollback rules khác commit ambiguity

Spring thường rollback khi unchecked exception thoát transactional method theo default rules, nhưng điều đó **không thể đảo ngược database COMMIT đã xảy ra**. Rollback policy của framework và durable DB outcome là hai khái niệm khác nhau.

---

## 15. Recovery: Chỉ tìm receipt có đủ không?

Nếu đọc thấy receipt với cùng key và digest từ primary, kết quả đã được xác nhận theo transaction atomicity. Nhưng nếu không thấy, cần cân nhắc:

- Transaction ban đầu chưa đến commit.
- Database đã rollback.
- COMMIT đang xử lý/chưa được quan sát.
- Đối soát đọc từ replica lag.
- Failover đang diễn ra hoặc connection mới tới node chưa có đầy đủ dữ liệu.
- Cache/intermediary trả stale data.
- Transaction record không được viết atomically do lỗi thiết kế.

### 15.1. Không tự đồng nhất “không thấy” với “abort”

Đặc biệt ngay sau network loss, một read miss không đủ để khẳng định commit sẽ không xuất hiện sau đó.

### 15.2. Cần bounded reconciliation

Một chiến lược có thể thử đọc primary trong một thời gian hữu hạn với backoff/jitter. Khi xác nhận receipt, trả success. Nếu quá deadline mà vẫn chưa có bằng chứng, giữ trạng thái `UNKNOWN` và cho caller retry **cùng key**.

### 15.3. Retry với cùng key thay vì identity mới

Nếu business effect được bảo vệ bằng database uniqueness, một transaction mới với **cùng request ID** có thể giúp hội tụ:
- Transaction trước commit → attempt mới bị duplicate-key, sau đó đọc receipt.
- Transaction trước rollback → attempt mới có thể tạo record.
- Transaction trước còn in-flight → attempt mới có thể chờ lock hoặc timeout; vẫn cần bounded retries.

### 15.4. Đối soát cũng có thể gặp ambiguous outcome

Nếu một retry đồng thời ghi transaction mới rồi tiếp tục mất ACK, quay lại cùng cơ chế; không tạo request ID mới để “thoát trạng thái unknown”.

---

## 16. Hai retries đồng thời cùng idempotency key

Timeline:

```text
Request A                          Request B
---------                          ---------
BEGIN                              BEGIN
INSERT orders(request_id=K)
                                   INSERT orders(request_id=K)
                                   -> có thể chờ unique-key lock
COMMIT
ACK của A bị mất
                                   -> duplicate key/conflict
A đối soát hoặc trả UNKNOWN         B đọc receipt K bằng tx mới
                                   -> trả lại cùng Order ID
```

### 16.1. Phải có DB-level uniqueness

Một mutex trong một JVM không bảo vệ khi A và B chạy trên hai pods khác nhau.

### 16.2. Duplicate constraint exception không tự là “request trước thành công”

Nó có thể là key collision với payload khác, một row ở trạng thái chưa đầy đủ hoặc một unique constraint khác bị vi phạm. Phải xác định **constraint nào** và đọc receipt/biz record trong transaction mới.

### 16.3. Đừng query tiếp trong failed transaction

Khi một INSERT gây constraint violation, nhiều databases/providers sẽ đưa transaction vào trạng thái failed/rollback-only. Cách an toàn là kết thúc transaction đó rồi tra receipt bằng transaction mới.

### 16.4. Timeout chờ unique lock cũng không chứng minh abort của attempt trước

Nếu attempt A vẫn đang commit/in-flight, request B có thể timeout. Đừng đổi sang request key khác; trả pending/unknown theo contract.

---

## 17. Định nghĩa payload fingerprint đúng cách

Giả sử request body JSON:

```json
{
  "customerId": 801,
  "items": [
    { "productId": 125, "quantity": 2 }
  ]
}
```

Một payload digest cần ổn định khi client retry cùng logical command.

### 17.1. Canonicalization

Có thể chuẩn hóa theo một representation đã được đặc tả:
- Tenant ID.
- Authenticated principal hoặc merchant scope nếu cần.
- Command type/version.
- Product/quantity/amount/currency.
- Các trường làm thay đổi business effect.
- Quy tắc sắp xếp các items nếu order không quan trọng.
- Quy tắc biểu diễn BigDecimal/tiền tệ, timezone và Unicode.

### 17.2. Không hash raw request body mù quáng

JSON whitespace, field order hoặc number formatting khác nhau có thể tạo digest khác dù cùng meaning; ngược lại, bỏ qua một trường quan trọng có thể khiến hai commands khác nhau bị coi như một.

### 17.3. Chọn thuật toán digest phù hợp

Một SHA-256 digest trên canonical representation thường đủ để so sánh nội dung theo yêu cầu integrity nhận diện operation. Nó không thay authentication. Nếu có adversarial input và cần bảo vệ integrity/secrecy, xem xét HMAC hoặc cách ràng buộc key với authenticated identity.

### 17.4. Không log toàn bộ payload nhạy cảm

Đủ dùng request ID/correlation ID, digest, tenant ID được kiểm soát và outcome. Tránh đưa payment data/PII lên logs.

---

## 18. Thời gian sống của idempotency key

Key/receipt phải tồn tại đủ lâu để bao phủ:
- Client retries.
- Proxy/API gateway retries.
- Mobile app offline sync.
- Job scheduling retries.
- Payment provider callbacks.
- Incident reconciliation window.
- Audit/business retention requirements.

### 18.1. Xóa key quá sớm tạo duplicate

Nếu receipt bị xóa sau 5 phút nhưng client retry cùng command sau 30 phút, cùng key có thể bị coi là chưa từng tồn tại và tạo Order mới.

### 18.2. TTL không chỉ là cache config

Đối với tiền, đơn hàng hoặc nghiệp vụ quan trọng, cần quyết định retention theo business lifecycle. Có thể giữ lightweight tombstone/operation record lâu hơn entity data trong cache.

### 18.3. Xóa key phải có policy

Nếu do privacy/retention phải xóa, hãy xác định retry contract sau khi hết hạn. Không hứa “same key always exactly once forever” nếu hệ thống thực tế chỉ giữ key 24 giờ.

---

## 19. Read-after-write và replica lag

Một luồng có primary và read replica:

```text
App -> Primary database: COMMIT
                 |
                 v
          Async replication
                 |
                 v
            Read replica
```

Sau COMMIT, replica có thể chưa nhìn thấy receipt ngay. Nếu sau mất ACK ứng dụng đọc replica:

```text
SELECT receipt WHERE request_id=K
-> 0 rows
```

Kết quả đó không chứng minh primary chưa commit.

### 19.1. Đối soát trên primary khi cần xác nhận

Read routing/failover framework phải biết transaction receipt lookup được gửi tới authoritative source, không chỉ dùng `@Transactional(readOnly=true)` rồi hy vọng middleware không route sang replica.

### 19.2. L2 cache có thể che dữ liệu mới

Một JPA second-level cache hoặc application cache lưu trạng thái cũ có thể khiến lookup không phản ánh source of truth. Đối soát commit nên dùng read path có cache policy được kiểm chứng, thường bypass shared cache khi cần.

### 19.3. Primary failover làm vấn đề phức tạp hơn

Trong cụm database dùng async replication, failover/rpo policy có thể ảnh hưởng những transactions đã được node cũ xác nhận. Sau failover, cần hiểu durability/recovery contract của database cluster; “đọc primary mới không thấy” không tự chứng minh điều gì đã xảy ra ở primary cũ theo mọi topology.

### 19.4. Isolation level không giải quyết mất ACK

READ COMMITTED, REPEATABLE READ hay SERIALIZABLE mô tả tính hiển thị/cạnh tranh trong DB; chúng không biến việc nhận ACK qua mạng thành một thao tác đáng tin tuyệt đối.

---

## 20. Không dùng EntityManager cũ để xác nhận

Sau lỗi connection/commit:

```java
try {
    tx.commit();
} catch (RuntimeException ex) {
    // Không nên tiếp tục:
    Order old = em.find(Order.class, orderId);
}
```

Các vấn đề:
- Connection có thể đã invalid.
- Persistence context có thể giữ managed entity chưa được commit.
- `find` có thể trả object từ first-level cache mà không query DB.
- Transaction có thể đang rollback-only/failed.
- Provider đang trong trạng thái xử lý exception.

### 20.1. Managed entity không phải bằng chứng commit

Một `Order` đã được `persist` vẫn nằm trong memory dù DB transaction rollback.

### 20.2. Mở fresh context và fresh transaction

Sau khi transaction cũ hoàn toàn rời scope, dùng `EntityManager` mới, không tái sử dụng object managed state cũ làm evidence.

### 20.3. Không dựa vào `contains()`

`em.contains(order)` chỉ nói entity có managed trong persistence context đó hay không. Nó không xác nhận durable database commit.

### 20.4. `EntityManagerFactory.getCache().contains()` cũng không đủ

Shared cache entry presence không phải nguồn sự thật về committed row, nhất là khi provider/cache có invalidation và write timing riêng.

---

## 21. Outbox giải quyết việc phát sự kiện sau commit

Sau khi tạo Order, ứng dụng thường phải publish `OrderCreated` cho hệ thống kho vận, search index hoặc notification service.

Sai:

```java
@PostPersist
void sendOrderCreated() {
    broker.publish(new OrderCreatedEvent(id));
}
```

Hoặc:

```java
em.persist(order);
broker.publish(event);
tx.commit();
```

Trong cả hai trường hợp, broker có thể nhận event trong khi DB transaction về sau rollback.

### 21.1. Transactional outbox

Ghi Order và Outbox event cùng transaction:

```text
BEGIN
  INSERT orders(...)
  INSERT order_operation_receipt(...)
  INSERT outbox_message(...)
COMMIT
```

Nếu COMMIT outcome unknown:
- Nếu DB commit → cả Order, Receipt và Outbox committed.
- Nếu DB rollback → không có cả ba.

Một publisher riêng đọc outbox đã committed và gửi broker.

### 21.2. Outbox không đồng nghĩa exactly-once delivery

Publisher có thể gửi message thành công rồi crash trước khi đánh dấu đã gửi, dẫn tới duplicate delivery. Consumer phải idempotent theo event ID.

### 21.3. Outbox và idempotency bảo vệ những bài toán khác nhau

- **Idempotency key** ngăn một client command tạo duplicate business effects.
- **Outbox** đảm bảo event được ghi cùng transaction và có thể publish sau commit.
- **Consumer idempotency** ngăn xử lý lại cùng event gây duplicate downstream effects.

Ba lớp nên phối hợp thay vì chọn một và coi như đã giải quyết toàn bộ.

---

## 22. Payment gateway: Không có một DB transaction cho mọi thứ

Ví dụ nguy hiểm:

```java
@Transactional
public void payOrder(PayCommand command) {
    paymentGateway.charge(command.card(), command.amount());
    em.persist(new PaymentRecord(...));
}
```

Nếu gateway charge thành công nhưng DB commit mất ACK hoặc rollback, application có thể không biết payment effect bên ngoài đã xảy ra. Retry mù quáng có thể **charge hai lần**.

### 22.1. Tách financial operation identity

Dùng một payment operation ID/idempotency key được gửi ổn định cho gateway nếu gateway hỗ trợ.

### 22.2. Persist workflow state

Có thể dùng payment intent/state machine với durable operation key:

```text
CREATED -> SUBMISSION_PENDING -> PROVIDER_CONFIRMED -> ACCOUNTED
                    |                    |
                    v                    v
                 UNKNOWN             FAILED/REVERSED
```

State transitions cần thiết kế transaction boundaries và recovery. Không gọi gateway với một key mới mỗi retry.

### 22.3. Gateway result cũng có ambiguous outcome

Nếu HTTP request charge bị timeout, gateway có thể đã xử lý. Phải query provider bằng operation key/transaction reference hoặc đối soát settlement/webhook, không suy ra “chưa charge”.

### 22.4. Không coi DB outbox là atomic với gateway

Transactional outbox giúp publish **ý định giao tiếp** sau DB commit, nhưng không biến gateway thành cùng database transaction. Cần idempotency, reconciliation và có thể là compensating actions/refunds theo nghiệp vụ.

---

## 23. Money transfer nội bộ: Giữ ledger idempotent

Nếu một transfer giữa hai tài khoản nằm trong cùng database, toàn bộ debit/credit/ledger phải được thực hiện atomically dưới một unique operation key.

Ví dụ:

```sql
CREATE TABLE transfer_operation (
    transfer_id UUID PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    request_id VARCHAR(100) NOT NULL,
    from_account_id BIGINT NOT NULL,
    to_account_id BIGINT NOT NULL,
    amount DECIMAL(19, 4) NOT NULL,

    CONSTRAINT uk_transfer_request
        UNIQUE (tenant_id, request_id)
);
```

Đối với cùng request ID, chỉ một transfer được phép commit. Nếu ACK mất, đối soát `transfer_operation` và ledger entries theo operation identity.

### 23.1. Không kiểm tra balances bằng phép trừ để đoán transfer có chạy

Balances có thể thay đổi bởi nhiều transfers khác trong lúc đó. Chỉ nhìn `balance_before`/`balance_after` không xác định duy nhất một operation đã commit.

### 23.2. Ledger có transaction reference

Entries debit và credit cần tham chiếu transfer/operation ID và được ràng buộc để không duplicate effect khi retry.

### 23.3. DB constraints/locking bảo vệ concurrency

Idempotency ngăn lặp cùng operation, nhưng không tự ngăn overspending từ hai operations khác nhau; cần account locking/conditional updates/ledger invariants phù hợp.

---

## 24. Tại sao `@Version` không thay idempotency key?

JPA optimistic locking:

```java
@Version
private long version;
```

giúp phát hiện concurrent updates trên cùng entity nếu provider mapping và transaction semantics phù hợp.

Nhưng hai retries có thể tạo **hai entity mới**:

```text
Attempt 1 -> Order#A @Version=0
Attempt 2 -> Order#B @Version=0
```

Không có shared entity identity để optimistic lock coi là conflict.

### 24.1. Unique operation key mới ngăn duplicate creates

Ràng buộc `(tenant_id, request_id)` đảm bảo cả hai attempts không tạo hai business records cho cùng operation.

### 24.2. @Version vẫn hữu ích

Khi retry cập nhật **cùng entity**, optimistic locking bảo vệ lost update, nhưng vẫn cần idempotent command semantics để tránh cộng tiền/trừ tồn kho hai lần.

### 24.3. `quantity = quantity - 1` không tự idempotent

Nếu retry chạy lại DML sau khi first commit đã thành công, quantity có thể giảm hai lần. Cần operation record/conditional update có key tương ứng.

---

## 25. Những câu lệnh có vẻ idempotent nhưng không đủ

So sánh:

```sql
UPDATE account
SET status = 'ACTIVE'
WHERE id = 10;
```

Lặp lại có thể có cùng final state trong một số điều kiện.

Trong khi:

```sql
UPDATE inventory
SET available = available - 1
WHERE product_id = 125;
```

Lặp lại **thay đổi state thêm lần nữa**.

### 25.1. Idempotency theo business effect, không chỉ SQL syntax

Dù `SET status = 'ACTIVE'` là idempotent về column value, operation vẫn có thể kích hoạt audit rows, version increments, triggers, outbox events hoặc external workflows. Phải đánh giá toàn transaction.

### 25.2. Upsert không phải bảo chứng hoàn chỉnh

`INSERT ... ON CONFLICT DO UPDATE` hoặc database `MERGE` có thể giúp bảo vệ uniqueness nhưng không tự giải quyết conflicting payload, duplicate side effects, isolation và lost response.

### 25.3. Exactly-once processing là mục tiêu có điều kiện

Trong thực tế, thường xây **at-least-once delivery + idempotent effects + reconciliation**. Không tuyên bố exactly-once end-to-end nếu không có hợp đồng đủ chặt qua mọi systems.

---

## 26. Khi nào retry được phép?

Trước khi retry, trả lời:

1. Lần trước **chắc chắn không commit** hay outcome unknown?
2. Operation có idempotency key ổn định?
3. Database có unique constraint bảo vệ key?
4. Mọi business writes có cùng transaction?
5. External effects có idempotency riêng?
6. Retry có dùng lại cùng payload digest?
7. Có giới hạn thời gian/số lần và backoff?
8. Có reconciliation khi nhiều attempts cùng chạy?

### 26.1. Retry sau confirmed abort

Nếu có bằng chứng transaction đã rollback và business rule cho phép retry, có thể thử lại cùng operation key.

### 26.2. Retry sau unknown

Chỉ retry khi cùng key và implementation có cơ chế ngăn duplicate effects. Nếu không bảo đảm idempotency, chọn **manual reconciliation** hoặc quy trình an toàn hơn thay vì gửi lại.

### 26.3. Không retry lỗi nghiệp vụ vô ích

Validation error, thiếu quyền, payload conflict hoặc số dư không đủ thường không trở thành thành công chỉ nhờ retry ngay.

### 26.4. Không retry quá gắt

Sử dụng exponential backoff/jitter/budget để tránh tạo bão request sau database failover.

---

## 27. Chính sách timeout và trạng thái UNKNOWN

Một API cần phân biệt:

```text
Client request timeout  != DB transaction rollback
JDBC socket timeout     != DB transaction rollback
SQL statement timeout   != luôn là commit outcome unknown
COMMIT ACK lost         => outcome có thể unknown
```

### 27.1. Timeout ở giai đoạn trước commit

Nếu database trả error cụ thể và transaction được xác nhận abort, có thể phân loại definite failure. Nhưng mất connection chung chung không nói đủ giai đoạn.

### 27.2. Timeout ở commit boundary

Nếu không có kết quả chắc chắn, đánh dấu outcome unknown trong điều khiển ứng dụng.

### 27.3. Deadline phải có điểm dừng

Không giữ HTTP request vô hạn để chờ primary. Sau một bounded probe/retry, trả trạng thái theo API contract và cho phép status endpoint hoặc client retry cùng key.

### 27.4. Không nói “transaction pending” nếu chưa durable

Nếu không có operation record đã commit, trả 202 Accepted với ngụ ý “server chắc chắn đã nhận và sẽ xử lý” có thể sai. Phải phân biệt `accepted-and-durable` với `outcome-unknown`.

---

## 28. Mapping HTTP responses

| Tình huống | Response tham khảo | Điều cần thể hiện |
|---|---|---|
| Order commit confirmed | `201 Created` | Resource ID/URI |
| Retry same key/payload, record đã commit | `200 OK` hoặc replay original successful result | Cùng Order ID |
| Key trùng nhưng payload khác | `409 Conflict` | Không tạo resource mới |
| Workflow accepted và durable state có sẵn nhưng chưa xong | `202 Accepted` | Status endpoint/operation ID |
| Commit outcome unknown, không có durable pending record xác nhận | `503/504/5xx` hoặc error contract riêng | Không khẳng định rollback; retry cùng key |
| Client validation sai | `400/422` theo API | Không thực hiện command |
| Unauthorized tenant | `401/403/404` theo security policy | Không lộ operation của tenant khác |

Đây là gợi ý API design, không phải quy tắc bắt buộc HTTP từ JPA. Quan trọng nhất là **response không khẳng định outcome khác với evidence**.

### 28.1. Response cần nêu khóa retry

Nếu trả lỗi tạm thời hoặc unknown, cung cấp operation/request ID và hướng dẫn dùng lại idempotency key; không bắt client tự tạo command mới.

### 28.2. Không leak database internals

Không trả full SQL, JDBC URL, connection credentials, stack trace hoặc raw transaction log ra response.

### 28.3. Status endpoint

Một endpoint:

```http
GET /operations/{requestId}
```

có thể trả trạng thái xác nhận theo authenticated tenant. Nếu chưa có receipt, có thể trả `UNKNOWN/NOT_YET_CONFIRMED`, **không** suy luận definitive not-found ngay sau sự cố nếu operation còn trong reconciliation window.

### 28.4. Không coi HTTP 200 là bằng chứng duy nhất của caller

HTTP success response cũng có thể bị mất trên đường truyền. Client nên dùng idempotency key/status API để xử lý trường hợp server đã commit nhưng response HTTP không đến.

---

## 29. State machine cho operation bền vững

Với quy trình dài nhiều bước, có thể cần state machine:

```text
REQUESTED (durable)
      |
      v
PROCESSING (leased/fenced)
      |
      +----> SUCCEEDED (durable result)
      |
      +----> FAILED (definite)
      |
      +----> UNKNOWN (cần reconciliation)
                     |
                     +--> SUCCEEDED
                     +--> FAILED/RETRYABLE
                     +--> MANUAL_REVIEW
```

### 29.1. Đây là workflow nhiều transaction

Khác với receipt atomically ghi cùng Order trong một transaction, trạng thái REQUESTED có thể được commit trước để đảm bảo request được nhận. Khi đó worker phải có cơ chế lease/fencing/idempotency để tránh hai workers cùng tạo effect.

### 29.2. `PROCESSING` không có nghĩa đã commit Order

Một request record trước đó có thể cho biết workflow được nhận, nhưng effect có thể chưa thành công. Không suy luận chỉ từ processing flag.

### 29.3. Leases và fencing

Nếu worker A bị timeout và worker B nhận lại job, A có thể tỉnh lại sau đó. Cần token generation/fencing hoặc optimistic version để old worker không ghi đè state mới; các business effects vẫn phải idempotent theo operation ID.

### 29.4. Manual review có chỗ đứng

Khi mất khả năng chứng minh outcome và business effect không thể retry an toàn (ví dụ external provider không có idempotency), hệ thống cần quy trình đối soát con người thay vì tiếp tục tự động thử.

---

## 30. “Không thấy receipt” sau timeout nên làm gì?

Một decision flow:

```text
Commit trả exception / connection lost
                |
                v
      Có definite abort evidence?
         /                 \
       Có                  Không
        |                    |
        v                    v
   FAILED/RETRYABLE     OUTCOME_UNKNOWN
                              |
                              v
                     New transaction + primary
                              |
                   +----------+-----------+
                   |                      |
                   v                      v
               Có receipt             Không thấy
                   |                      |
                   v                      v
            Digest khớp?            Retry probe bounded
              /      \                    |
            Có       Không                v
             |         |             Có evidence?
             v         v                /      \
          CONFIRMED  CONFLICT          Có      Không
                                       |         |
                                       v         v
                                    RESOLVED   UNKNOWN
                                                |
                                                v
                                    Retry same key only
                                    if effects idempotent;
                                    otherwise reconcile
```

### 30.1. Positive evidence và negative evidence không đối xứng

Receipt tồn tại và digest khớp, khi atomicity contract được đảm bảo, là evidence mạnh. Không tìm thấy ngay sau connection loss là evidence yếu.

### 30.2. Một deadline không thay đổi chân lý

Hết 30 giây mà chưa thấy record không tự chứng minh DB sẽ không commit, nhất là khi failover/network partition. Deadline chỉ quyết định **bao lâu hệ thống chờ tự động** trước khi chuyển trạng thái phục hồi tiếp theo.

---

## 31. Database failover và durability contract

Một database cluster có nhiều replication modes, quorum policies và failover behaviors. Hệ quả của một commit acknowledgment phụ thuộc cả DB và topology.

### 31.1. Single-node database

Với một database instance và durable transaction log, sau khi commit được xác nhận, dữ liệu được xử lý theo durability contract của DB. Mất ACK vẫn khiến client không biết outcome.

### 31.2. Asynchronous replication

Một primary có thể nhận commit nhưng replica chưa bắt kịp. Nếu failover xảy ra trước replication, số phận transaction trên new primary phụ thuộc recovery/RPO contract. Cần hiểu topology để quyết định read verification.

### 31.3. Synchronous/quorum replication

Có thể giảm rủi ro mất committed data khi failover, nhưng không loại bỏ vấn đề **client không nhận được ACK**.

### 31.4. Driver error code cần đặt trong ngữ cảnh

SQLSTATE, vendor error code và exception chain có thể giúp phân loại một lỗi, nhưng không có một quy tắc JPA portable “mọi SQLException với mã X nghĩa là transaction chắc chắn rollback” áp cho mọi DB/driver/topology.

### 31.5. Không suy từ kết nối mới thành công rằng old transaction đã rollback

Recovery cần kiểm tra operation identity/receipt, không chỉ health check “DB đã online lại”.

---

## 32. JPA exception và provider wrappers

Ở các stack khác nhau, commit failure có thể xuất hiện qua:

- `jakarta.persistence.RollbackException`.
- `jakarta.persistence.PersistenceException`.
- Spring `TransactionSystemException`.
- Spring `DataAccessException` subtype.
- Hibernate JDBC/transaction exceptions.
- JDBC `SQLException` trong cause chain.
- Container/JTA-specific transaction exceptions.

Không phải tất cả những classes này đều có cùng commit semantics.

### 32.1. `RollbackException` không phải phép tiên đoán mạng

Một exception class có tên rollback có thể cho biết transaction không commit thành công theo transaction manager, nhưng nếu sự cố mạng khiến DB outcome thực sự không biết, ứng dụng cần tin vào bằng chứng cụ thể từ manager/driver và recovery logs, không chỉ đoán theo tên.

### 32.2. Đừng parse message text làm logic cốt lõi

Thông báo “connection reset” có thể thay đổi theo driver/version/locale. Logic phân loại nên dùng error code/cause types và kiểm thử fault scenarios, đồng thời có fallback UNKNOWN khi bằng chứng không đủ.

### 32.3. Preserve cause chain

Khi chuyển thành domain/infrastructure exception, giữ original cause và transaction phase trong telemetry. Không ném `new RuntimeException("Failed")` khiến mất SQLSTATE hoặc network diagnostic quan trọng.

### 32.4. Có thể không biết chính xác phase

Trong Spring interceptor, exception đến từ commit call được wrapper; cần tracing để biết SQL/flush đã hoàn thành và `COMMIT` đã được attempt. Dù tracing tốt, vẫn có trường hợp không thể quyết định durable outcome từ phía client.

---

## 33. Connection pooling và EntityManager lifecycle

Connection pool có thể tự đóng/evict connection bị hỏng. Tuy nhiên không nên:

- Đưa một JDBC Connection hỏng về pool như connection khỏe.
- Dùng cùng EntityManager để query xác minh sau commit exception.
- Coi pool health check là bằng chứng rollback.
- Tự mở transaction mới trên same physical connection không xác định state.

### 33.1. Kết thúc scope cũ

Đóng EntityManager/để container dispose transaction resources theo framework contract, log exception rồi chuyển reconciliation sang scope mới.

### 33.2. Đối soát cần connection mới

Một fresh EntityManager/transaction thường sẽ lấy connection phù hợp. Nhưng nếu middleware route tới replica, phải chủ động đảm bảo query authoritative.

### 33.3. Timeout các lớp có thể khác nhau

Phân biệt pool acquisition timeout, socket timeout, statement timeout và transaction timeout. Chúng có các ảnh hưởng khác nhau và không tự có cùng recovery semantics.

---

## 34. Khi nào nên dùng transaction-status API?

Một số transaction managers hoặc database services có recovery/status APIs. Nếu được thiết kế để truy vấn bằng **transaction ID bền vững** và cung cấp authoritative outcome, có thể dùng chúng.

### 34.1. JPA portable không có commit receipt API

`EntityTransaction.isActive()` không trả lời “server đã commit lúc kết nối mất hay chưa”. JPA `EntityManager` không có method portable trả durable transaction decision sau khi session bị mất.

### 34.2. XA recovery

Trong hệ thống XA, transaction manager có recovery log/Xid và cơ chế reconcile in-doubt branches. Cần quy trình vận hành riêng, không tự resolve heuristic outcomes bằng cách đọc một business table rồi giả định mọi resources đồng nhất.

### 34.3. Business receipt thường dễ bảo trì hơn

Một row có unique operation ID và atomic business state hỗ trợ kết luận nghiệp vụ trực tiếp, không buộc application phải phụ thuộc internals của DB commit protocol.

---

## 35. Transactional inbox cho consumers

Khi event từ broker bị gửi lại, consumer cũng có thể gặp ambiguous DB commit:

```text
Broker delivers OrderPaid(eventId=E)
Consumer updates DB + saves processed_event(E)
COMMIT ACK lost
Broker redelivers E
```

Nếu consumer không lưu event ID, nó có thể xử lý hai lần.

### 35.1. Inbox pattern

Trong cùng DB transaction:

```sql
INSERT INTO processed_event (consumer_name, event_id)
VALUES ('inventory-consumer', 'E-123');

UPDATE inventory
SET reserved = reserved + 1
WHERE product_id = 125;
```

Đặt UNIQUE `(consumer_name,event_id)`. Khi redelivery, duplicate inbox key cho biết event đã được xử lý trong một committed transaction, nhưng vẫn cần kiểm tra payload/handler semantics và có thể đọc receipt riêng nếu operation phức tạp.

### 35.2. Không ACK broker trước khi DB commit

Nếu consumer ACK sớm rồi DB rollback, event có thể bị mất. Nếu ACK sau commit và ACK bị mất, broker có thể redeliver; inbox/idempotency giải quyết duplicate delivery.

### 35.3. Inbox và outbox phối hợp

Outbox bảo vệ publish từ transaction nguồn; inbox bảo vệ processing tại đích. Cả hai đều cần operation identity ổn định và durable constraints.

---

## 36. Test tình huống lỗi thật: Không chỉ mock commit exception

Một unit test có thể viết:

```java
when(transactionManager.commit(any()))
    .thenThrow(new RuntimeException("connection reset"));
```

Nó kiểm tra application branching nhưng **không chứng minh** database đã commit hay rollback khi connection bị ngắt ở từng thời điểm.

### 36.1. Các fault windows cần mô phỏng

| Cửa sổ lỗi | Khả năng | Kỳ vọng hệ thống |
|---|---|---|
| Trước BEGIN | Chưa có transaction | Không effect |
| Sau BEGIN, trước INSERT | Có transaction chưa commit | Không duplicate sau retry |
| Sau INSERT/FLUSH, trước COMMIT | Uncommitted writes | Không tuyên bố commit |
| Sau gửi COMMIT, trước DB quyết định | Unknown từ client | Reconcile |
| Sau DB commit, trước ACK | DB đã commit, client nhận lỗi | Retry không tạo duplicate |
| Sau ACK DB, trước HTTP response | Server biết commit, client timeout | Retry trả cùng result |
| Trong primary failover | Outcome phụ thuộc DB topology | Không kết luận chỉ từ timeout |
| Trong outbox publish | Broker có thể đã nhận | Consumer idempotent |
| Khi consumer commit, trước broker ACK | DB đã apply, event redelivery | Inbox ngăn duplicate |

### 36.2. Network proxy/fault injection

Trong môi trường test cô lập, dùng network proxy hoặc test harness để cắt connection tại giai đoạn COMMIT/ACK. Không làm thí nghiệm này trên database production.

### 36.3. Không thể tái hiện hoàn toàn bằng sleep đơn giản

Thêm `Thread.sleep()` trước `commit()` chỉ làm chậm, không đảm bảo kết nối bị ngắt sau database commit nhưng trước ACK. Test cần kiểm soát failure point hoặc xác minh database state cuối.

### 36.4. Xác minh outcome bằng khóa nghiệp vụ

Dù client nhận timeout, sau recovery phải assert không có hơn một Order/Transfer với cùng key, và receipt đúng với business state.

---

## 37. Kịch bản integration test: Commit thực sự thành công nhưng ACK bị mất

Giả định test harness có thể gây fault đúng cửa sổ sau khi database commit thành công.

Các bước:

1. Chuẩn bị request K với digest P.
2. Gọi create-order; fault injector làm client không nhận COMMIT ACK.
3. Facade nhận error/UNKNOWN.
4. Mở fresh transaction trên primary.
5. Truy vấn `(tenantId,K)` và xác nhận receipt tồn tại.
6. Retry cùng K/P.
7. Assert cùng Order ID được trả.
8. Assert chỉ có một Order và đúng số OrderLines.
9. Assert chỉ có một outbox event logical ID (hoặc duplicate delivery được dedupe).
10. Assert không có side effect ngoài DB bị gọi hai lần.

### 37.1. Positive case là bài test quan trọng nhất

Rất nhiều hệ thống chỉ test “commit fail và rollback” rồi tự tin retry. Cửa sổ **đã commit nhưng không nhận ACK** mới là nơi duplicate bugs xuất hiện.

### 37.2. Đừng chỉ assert HTTP status

Dù HTTP trả 500 ở first attempt, database state có thể đã commit. Test phải đọc data qua transaction độc lập và kiểm tra business uniqueness.

---

## 38. Kịch bản integration test: Transaction bị rollback

Thiết kế test có database trả definitive abort, chẳng hạn constraint violation trước commit.

1. Gửi request K/P.
2. Gây lỗi constraint khiến transaction rollback.
3. Xác nhận bằng fresh transaction không thấy Order/Receipt/Outbox.
4. Nếu business policy cho retry sau sửa input, retry K/P hoặc key mới tùy contract.
5. Assert không có partial business writes.

### 38.1. Không giả lập lỗi bằng commit ACK lost

Một connection reset không cho phép assert “rollback chắc chắn”. Để test confirmed abort, cần một điều kiện làm transaction thực sự abort và có evidence.

### 38.2. Không bỏ qua constraint error

Nếu transaction bị rollback vì unique constraint khác (ví dụ product SKU), hãy trả đúng conflict/rejected outcome, không tự chuyển thành commit unknown không có thông tin.

---

## 39. Kịch bản integration test: Hai retries đồng thời

Dùng cùng `(tenantId,requestId)` nhưng gửi hai concurrent requests.

Kỳ vọng:

- Một winner có thể INSERT/COMMIT.
- Request còn lại có thể chờ, nhận unique conflict hoặc trả UNKNOWN tùy timeout/driver.
- Sau reconciliation, cả hai clients cùng nhận **một Order ID** khi payload khớp.
- Nếu payload khác, second request nhận `CONFLICTING_REQUEST`.
- Không có hai business effects và không có external double-charge.

### 39.1. Unique key có thể gây lock waits

Concurrent INSERT cùng unique key có thể chờ transaction trước kết thúc. Cần connection/pool timeout và retry budget hợp lý.

### 39.2. Đừng query trên aborted transaction

Khi second attempt nhận unique violation, mở transaction mới để đọc receipt; không cố SELECT tiếp trong một transaction đã failed.

### 39.3. Tests phải dùng DB thật

Một in-memory mock không kiểm tra database uniqueness, transaction isolation hoặc lock behavior.

---

## 40. Kịch bản integration test: Primary/replica lag

1. App ghi Order/Receipt lên primary.
2. Cắt ACK/giả lập mất response.
3. Đọc replica ngay sau đó; có thể chưa thấy receipt.
4. Đọc primary; nếu thấy receipt, xác nhận commit theo consistency contract.
5. Đảm bảo recovery không phân loại thất bại chỉ vì replica read miss.
6. Retry cùng key và assert không duplicate.

Nếu production dùng primary routing tự động theo `readOnly=true`, cần test để đảm bảo reader thực sự đi primary.

---

## 41. Kịch bản integration test: Process crash

Một process crash có thể xảy ra:

- Trước khi transaction được bắt đầu.
- Sau khi INSERT/FLUSH nhưng trước COMMIT.
- Sau khi COMMIT được chấp nhận nhưng trước khi HTTP response.
- Sau khi response đã được build nhưng trước khi gửi hết bytes.

### 41.1. Key phải tồn tại ở client/job scheduler

Nếu request ID chỉ được server sinh trong RAM sau khi nhận request, một crash có thể khiến client không biết key để retry. API cần chiến lược cung cấp/nhận operation key trước business effect.

### 41.2. Process restart không được xóa idempotency evidence

Receipt cần durable DB storage, không chỉ cache RAM của application instance.

### 41.3. Recovery worker

Nếu có durable workflow request table, worker sau restart có thể tìm operations chưa rõ kết quả, đối soát và re-drive bằng cùng idempotency key.

---

## 42. Quan sát và metrics khi commit outcome unknown

Nên thu thập:

| Metric | Tác dụng |
|---|---|
| `db_commit_attempts` | Tổng số commit attempts |
| `db_commit_errors` | Lỗi quan sát tại transaction boundary |
| `commit_outcome_unknown_total` | Số operations cần đối soát |
| `receipt_probe_success_total` | Số unknown được xác nhận qua receipt |
| `receipt_probe_errors_total` | Lỗi đường đối soát |
| `idempotency_replay_total` | Số retries đã trả lại kết quả cũ |
| `idempotency_payload_conflict_total` | Cùng key nhưng payload khác |
| `reconciliation_age_seconds` | Thời gian từ unknown tới resolved |
| `manual_review_backlog` | Operations cần con người |
| `duplicate_business_effect_incidents` | Chỉ số correctness quan trọng |
| `outbox_delivery_retry_total` | Retry publish after commit |
| `db_failover_events` | Correlate unknown spikes với DB topology |

### 42.1. Correlation IDs

Log một `requestId`/operation ID xuyên suốt API, service, DB receipt, outbox và message consumers.

### 42.2. Không log dữ liệu nhạy cảm

Không ghi raw payment credentials, toàn customer details hoặc SQL parameter values không cần thiết để đối soát.

### 42.3. Alert theo business effect

Một lần commit ACK lost có thể là incident nhỏ nếu reconciliation tự giải quyết. Nhưng duplicate charge hoặc unconfirmed money transfer là correctness incident cần ưu tiên cao hơn latency thông thường.

---

## 43. Runbook vận hành khi phát hiện unknown commits

1. Xác định operation ID, tenant scope, payload digest và thời điểm sự cố.
2. Không yêu cầu khách tạo một operation mới để “thử lại”.
3. Kiểm tra database cluster primary/failover/replication status.
4. Đọc receipt hoặc business row bằng transaction mới trên nguồn authoritative.
5. Nếu thấy receipt có cùng digest, kết luận business transaction committed.
6. Nếu thấy receipt khác digest, xử lý idempotency-key conflict.
7. Nếu chưa thấy, xác định liệu operation cũ còn in-flight hoặc hệ thống đang failover.
8. Khi an toàn, retry cùng key qua path có unique constraint/idempotent effects.
9. Nếu có external payment/service, tra provider transaction bằng key gốc.
10. Chuyển manual review nếu không thể bảo đảm retry an toàn.
11. Kiểm tra outbox/inbox để bảo đảm event downstream không thiếu hoặc nhân đôi effect.
12. Ghi kết quả reconciliation/correlation ID cho support, không chỉnh database bằng SQL tùy tiện.
13. Thêm regression test và cập nhật error classification nếu phát hiện failure mode mới.

### 43.1. Support không nên kết luận từ HTTP 500

Một request trả 500 do commit acknowledgment mất có thể đã tạo Order. Trước khi hủy/hoàn tiền/tạo lại cần tra durable operation identity.

### 43.2. Không sửa thủ công nếu chưa nắm liên kết

Dedupe Orders hay Payment records có thể ảnh hưởng inventory, ledger, notifications và audit. Business remediation phải có quy trình rõ.

---

## 44. Những anti-pattern cần tránh

| Anti-pattern | Vì sao nguy hiểm | Hướng đúng |
|---|---|---|
| “Commit ném exception nên chắc chắn rollback” | ACK có thể mất sau DB commit | UNKNOWN + reconcile |
| Retry với UUID/request ID mới | Tạo duplicate effect | Cùng idempotency key |
| Dùng `em.flush()` làm success flag | Flush chưa commit | Commit/receipt |
| Dùng generated ID làm commit proof | ID có thể cấp trước commit | Đọc committed row |
| Gọi rollback rồi tin effect biến mất | Không hoàn tác commit đã xảy ra | Fresh transaction verification |
| Query lại bằng EntityManager hỏng | L1/connection state không đáng tin | New context/connection |
| Đọc replica rồi kết luận không tồn tại | Replication lag | Authoritative read |
| Chỉ dùng process-local dedupe map | Không chống multi-node/restart | DB uniqueness |
| `existsByKey` rồi INSERT không constraint | Race condition | UNIQUE key |
| Cùng key khác payload vẫn trả success | Nhầm hai operations | Digest conflict |
| Xóa receipt quá sớm | Retry sau TTL tạo duplicate | Retention policy |
| Publish message trước DB commit | Event có thể đi ra cho tx rollback | Transactional outbox |
| Charge payment gateway trong DB tx rồi retry | Double charge | External idempotency + reconciliation |
| `@Version` thay unique operation key | Không chặn duplicate creates | Business key uniqueness |
| Catch mọi exception rồi trả FAILED | Che ambiguous outcomes | Error taxonomy |
| Không bounded retry | DB overload, request treo | Backoff/budget |
| `202 Accepted` khi chưa lưu durable state | Hứa xử lý mà không có bằng chứng | Explicit UNKNOWN |
| Ghi receipt ở tx khác business data | Receipt sai sự thật | Atomic receipt |
| Unit mock thay fault injection | Không tái tạo lost ACK | Integration/network tests |
| Không kiểm tra downstream consumers | Có thể nhân đôi business effect | Inbox/idempotency |

---

## 45. Bài tập thực hành

### Bài 1. Flush thành công nhưng commit ACK mất

`em.flush()` thành công; `tx.commit()` ném connection exception.

**Đáp án:** Không suy ra rollback. Commit outcome có thể unknown. Dùng operation key/receipt đối soát.

### Bài 2. Rollback sau commit có thành công không?

Database đã commit nhưng client không nhận ACK.

**Đáp án:** Rollback trên connection cũ không đảo ngược committed transaction.

### Bài 3. Retry tạo UUID mới

First attempt Order#A có thể đã commit; retry tạo Order#B.

**Đáp án:** Có nguy cơ duplicate. Retriable operation phải giữ cùng idempotency key và DB uniqueness.

### Bài 4. Receipt cùng transaction

Order và receipt cùng transaction; fresh primary read thấy receipt.

**Đáp án:** Có bằng chứng mạnh Order đã commit nếu atomicity/schema assumptions được bảo đảm, và digest khớp.

### Bài 5. Không thấy receipt trên replica

**Đáp án:** Không chứng minh rollback; replica có thể lag. Đọc authoritative primary.

### Bài 6. Không thấy receipt ngay trên primary

**Đáp án:** Chưa hẳn chứng minh transaction abort vì original transaction có thể in-flight hoặc failover chưa ổn định. Tiếp tục bounded reconciliation hoặc retry an toàn cùng key.

### Bài 7. Cùng key nhưng payload khác

**Đáp án:** Trả conflict, không replay success cho command mới.

### Bài 8. Hai pods xử lý cùng request

**Đáp án:** Dùng DB-level unique constraint và retry/readback logic. Local mutex không đủ.

### Bài 9. Unique violation ở retry

**Đáp án:** Không tự kết luận duplicate request hợp lệ. Xác định constraint, kết thúc failed transaction, đọc receipt và so digest.

### Bài 10. Payment gateway charge timeout

**Đáp án:** Không gọi charge lại bằng key mới. Dùng provider idempotency/status API và reconciliation.

### Bài 11. Spring method đã return

`@Transactional` method body `return orderId`, nhưng proxy commit ném exception.

**Đáp án:** Caller chưa nhận completed success; code trong method return không đồng nghĩa commit success. Catch ở facade ngoài transactional proxy.

### Bài 12. Self-invocation

`this.writeOnce()` gọi method cùng bean có `@Transactional`.

**Đáp án:** Spring proxy advice mặc định có thể không áp dụng. Tách bean hoặc dùng transaction management phù hợp.

### Bài 13. `EntityManager.contains(order)`

**Đáp án:** Chỉ cho biết managed state, không chứng minh committed state.

### Bài 14. `@Version` trên Order

Hai retry tạo hai Order IDs.

**Đáp án:** @Version không chặn duplicate create; unique request key mới cần thiết.

### Bài 15. Outbox publish hai lần

Publisher gửi rồi crash trước khi mark sent.

**Đáp án:** At-least-once delivery; consumer idempotency cần để tránh duplicate effect.

### Bài 16. Broker redelivery sau consumer commit ACK lost

**Đáp án:** Transactional inbox/processed event unique key ngăn xử lý nghiệp vụ trùng.

### Bài 17. `202 Accepted`

Không có durable operation record nhưng DB commit outcome unknown.

**Đáp án:** Không mặc định trả 202 với ý nghĩa đã accepted bền vững; API cần trạng thái UNKNOWN/error contract trung thực.

### Bài 18. Timeout 30 giây không thấy receipt

**Đáp án:** Hết deadline chưa tự chứng minh rollback. Chuyển UNKNOWN/reconciliation và retry cùng key nếu idempotent.

### Bài 19. Connection pool online trở lại

**Đáp án:** Pool health không cho biết old transaction đã commit hay chưa; phải tra operation identity.

### Bài 20. Primary failover với async replica

**Đáp án:** Xem replication/RPO/durability contract; new primary read miss chưa thể coi là bằng chứng bất biến cho mọi topology.

### Bài 21. Precheck tồn tại rồi INSERT

**Đáp án:** Có race. UNIQUE constraint bảo vệ concurrency.

### Bài 22. `SET available = available - 1` retry

**Đáp án:** Không idempotent. Cần operation guard/receipt và transaction atomicity.

### Bài 23. Receipt ghi trong transaction độc lập trước Order

**Đáp án:** Có thể có receipt success mà Order chưa commit; không bảo đảm cùng business transaction.

### Bài 24. Sau mất ACK, app tiếp tục query bằng EM cũ

**Đáp án:** Không đáng tin vì connection/L1/transaction state. Mở EntityManager/transaction mới.

### Bài 25. Retry không giới hạn

**Đáp án:** Không an toàn về tải hệ thống. Cần bounded retry, backoff và escalation.

### Bài 26. Service trả FAILED cho mọi SQL timeout

**Đáp án:** Không phân biệt được commit ambiguity. Cần error classification + reconciliation.

### Bài 27. Không có idempotency ở downstream

DB order unique nhưng mỗi retry lại gọi email/charge.

**Đáp án:** Chưa idempotent end-to-end. Dùng outbox và external operation key.

### Bài 28. Hash raw JSON

Hai requests cùng nội dung logic nhưng JSON property order khác, digest khác.

**Đáp án:** Dùng canonical representation theo business semantics.

### Bài 29. Receipt tồn tại nhưng digest không khớp

**Đáp án:** Không trả kết quả cũ như cùng command. Báo idempotency conflict theo security policy.

### Bài 30. Test mock `commit()` ném SQLException

**Đáp án:** Kiểm tra branching thôi; cần integration/fault injection để xác minh behavior ở cửa sổ DB committed nhưng ACK lost.

---

## 46. Checklist thiết kế phục hồi commit không rõ kết quả

1. Operation có idempotency key bền vững, được dùng lại khi retry?
2. Key được scope theo authenticated tenant/account/merchant?
3. Cùng key/payload được replay cùng business result?
4. Cùng key/khác payload được phát hiện conflict?
5. Database có UNIQUE constraint trên operation identity?
6. Business writes và receipt/outbox có cùng transaction?
7. Receipt có lưu result identifier/payload digest?
8. Receipt không được xem là committed chỉ vì vừa persist/flush?
9. Có phân biệt success, definite abort và unknown?
10. Error classifier có hiểu commit-phase network failures?
11. Có giữ exception causes và correlation IDs?
12. Có chặn mọi retry với key mới cho cùng command?
13. Có quy trình retry bounded/backoff/jitter?
14. Có đường đối soát dùng fresh transaction/connection?
15. Có route reconciliation tới authoritative source?
16. Có tránh stale JPA L1/L2/application cache?
17. Có tránh kết luận abort chỉ từ một receipt read miss?
18. Có xử lý original transaction còn in-flight/unique lock wait?
19. Có giới hạn retention idempotency phù hợp business SLA?
20. Có loại bỏ duplicate effects của external services?
21. Gateway/payment provider có idempotency/status lookup?
22. Có transactional outbox để phát events sau DB commit?
23. Consumers có idempotent inbox/processed event guard?
24. Có rollback/error policy đúng với Spring/JTA transaction boundaries?
25. Có không dùng `em.flush()`/`@PostPersist`/generated ID làm commit proof?
26. Có xử lý failover/replica lag theo DB topology?
27. Có status endpoint hoặc API error contract cho UNKNOWN?
28. Có support/manual review path cho unresolved operations?
29. Có metrics cho unknown outcomes và reconciliation age?
30. Có test lost ACK sau successful commit, không chỉ test rollback?
31. Có test concurrent same-key retries?
32. Có test same-key payload conflict?
33. Có test transaction constraint failure và cleanup?
34. Có test process crash trước/sau commit?
35. Có test actual database/driver/transaction manager stack?
36. Có xác nhận không duplicate Order/Payment/Ledger effect dưới failure injection?
37. Có runbook rõ trách nhiệm SRE/DBA/business reconciliation?
38. Có contract về consistency/retention/khả năng mất dữ liệu khi failover?

---

## 47. Quy trình thực hành tổng thể

```text
                   Client gửi command K/P
                            |
                            v
                 Validate auth/tenant/payload
                            |
                            v
                 Đã có committed receipt K?
                     /              \
                   Có               Không
                    |                 |
                    v                 v
              Digest khớp?     Transactional writer
               /      \          /         \
             Có       Không  commit OK    commit error
              |         |        |            |
              v         v        v            v
          Replay      Conflict  CONFIRMED  Classify evidence
          result                               |
                                   +-----------+-----------+
                                   |                       |
                              Definite abort             Unknown
                                   |                       |
                                   v                       v
                            Retry/reject policy    Fresh primary receipt probe
                                                          |
                                                +---------+---------+
                                                |                   |
                                              Found              Not found/
                                                |                 read failed
                                                v                   |
                                          Digest check              v
                                          + confirm          UNKNOWN + bounded
                                                             reconciliation
                                                                    |
                                                                    v
                                                         Retry SAME key only
                                                         if business effects
                                                         are idempotent
```

Không có bước nào trong sơ đồ yêu cầu client tự tạo operation identity mới chỉ vì một response bị mất. Những lần thực hiện lại chỉ được phép khi cùng request key và các side effects có phương án chống trùng.

---

## 48. Tổng kết

1. **Mất kết nối trong cửa sổ COMMIT không đồng nghĩa transaction rollback.** Database có thể đã commit trước khi ACK đến client.
2. **Flush, generated ID và PostPersist không phải bằng chứng commit.** Chúng có thể xảy ra trước khi transaction được xác nhận.
3. **Một exception của JPA/JDBC/Spring không luôn cho biết durable outcome.** Phải phân loại error theo transaction phase, driver/database và evidence.
4. **Hãy biểu diễn trạng thái `OUTCOME_UNKNOWN` trung thực** nếu không thể xác nhận committed/aborted.
5. **Idempotency key ổn định qua retries** là nền tảng chống duplicate commands.
6. **UNIQUE constraint ở database** bảo vệ khi có nhiều app instances, concurrent retries và process restart.
7. **Lưu receipt/business records atomically** để đối soát qua operation key bằng transaction độc lập.
8. **Receipt đọc thấy từ authoritative source là positive evidence** khi key/digest/atomicity đúng; **receipt chưa thấy không tự chứng minh rollback** ngay sau sự cố.
9. **Không dùng EntityManager/connection hỏng để xác minh.** Tạo persistence context/transaction mới.
10. **Read replica lag và failover topology ảnh hưởng reconciliation.** Cần hiểu primary routing/durability/RPO.
11. **Retry với cùng key**, có bounded budget, backoff và xử lý unique conflicts; không retry mù quáng với key mới.
12. **Transactional outbox và consumer inbox/idempotency** bảo vệ luồng message khỏi duplicate effects.
13. **External payments/HTTP calls cần idempotency và reconciliation riêng**; một database transaction không thể atomic với mọi hệ thống ngoài.
14. **Spring @Transactional commit có thể lỗi sau khi method body return**, nên catch/reconcile ở boundary phù hợp, không dựa vào self-invocation.
15. **API phải truyền tải trạng thái chưa chắc chắn**, không nói “failed and not saved” khi có thể đã commit.
16. **Kiểm thử cửa sổ đã commit nhưng mất ACK** cùng các kịch bản failover, concurrency, crash và downstream redelivery.
17. **Có runbook/metrics và manual review** cho những operations không thể xác nhận an toàn.

Điểm cốt lõi của bài học là: **khi không biết COMMIT đã thành công hay chưa, không nên đoán rồi thực hiện lại như một operation mới.** Thay vào đó, thiết kế dữ liệu sao cho cùng một command có identity bền vững, database ngăn duplicate effects, và ứng dụng có đường đối soát tin cậy sau khi kết nối được khôi phục. Với những hệ thống cần tính đúng đắn cao như thanh toán, sổ cái, tồn kho và đặt hàng, đây là điều kiện thiết yếu để phục hồi an toàn trước lỗi mạng xảy ra ngay tại ranh giới transaction.
