# Đặt ranh giới giao dịch tại thao tác nghiệp vụ nhiều bước trong Hibernate ORM

Trong ứng dụng dùng Hibernate, một thao tác nghiệp vụ thường không chỉ sửa một entity. Khi khách hàng đặt hàng, hệ thống có thể phải **kiểm tra tồn kho, giữ số lượng hàng, tạo đơn, lưu chi tiết, ghi sự kiện và cập nhật trạng thái**. Nếu một bước thất bại, điều gì sẽ xảy ra với những bước trước đó?

Câu trả lời phụ thuộc vào **ranh giới giao dịch** (*transaction boundary*): đoạn công việc nào được xem là **một đơn vị nhất quán**, có thể commit cùng nhau hoặc rollback cùng nhau.

Đây là một trong những quyết định kiến trúc quan trọng nhất khi sử dụng Hibernate ORM. Một chương trình có thể ánh xạ entity chính xác, gọi `persist()` đúng cách, nhưng vẫn để dữ liệu ở trạng thái sai nếu mỗi thao tác ghi được commit độc lập, hoặc nếu transaction chỉ bao phủ một phần quy tắc nghiệp vụ.

**Ý chính của bài:** ranh giới transaction thường nên đặt quanh **một thao tác nghiệp vụ có các bước cập nhật cơ sở dữ liệu phải cùng thành công**, thường tại tầng application service/use case. Tuy nhiên, không nên kéo dài cùng một transaction database qua toàn bộ các lời gọi mạng, thanh toán bên ngoài hoặc tác vụ bất đồng bộ. Những trường hợp đó cần một phương án phối hợp khác, như *transactional outbox*, *saga* hoặc cơ chế bù trừ (*compensation*).

Bài sẽ đi từ mô hình transaction cơ bản đến ví dụ đặt hàng có nhiều bước, các lỗi triển khai trong Spring/Jakarta Persistence, vấn đề cạnh tranh dữ liệu và cách phân tách phần việc không thể nằm trong cùng database transaction.

## 1. Ranh giới giao dịch là gì?

**Transaction** là một phạm vi thao tác trên tài nguyên giao dịch — thường là một cơ sở dữ liệu quan hệ — được xác nhận bằng **commit** hoặc hủy bỏ bằng **rollback**.

Một transaction có thể chứa:

```text
BEGIN TRANSACTION
    INSERT purchase_order
    UPDATE inventory_stock
    INSERT purchase_order_item
    INSERT outbox_event
COMMIT
```

Nếu có lỗi và transaction được rollback:

```text
BEGIN TRANSACTION
    INSERT purchase_order
    UPDATE inventory_stock
    INSERT purchase_order_item  <-- lỗi
ROLLBACK
```

thì những thay đổi ghi vào database bởi transaction đó sẽ không trở thành dữ liệu đã commit, theo bảo đảm giao dịch của hệ quản trị.

**Ranh giới transaction** xác định:

- **Bắt đầu ở đâu:** lúc nào thao tác nghiệp vụ được tham gia một transaction.
- **Gồm những gì:** những truy vấn và cập nhật thuộc cùng unit of work.
- **Kết thúc ở đâu:** thời điểm yêu cầu commit hoặc rollback.
- **Ai sở hữu:** service/transaction manager nào chịu trách nhiệm điều phối.
- **Tài nguyên nào tham gia:** một database, một connection, nhiều connection được điều phối hay một giao dịch phân tán.

Đừng đồng nhất transaction với một method Java bất kỳ. Method là ranh giới mã nguồn; transaction là **ranh giới nhất quán đối với dữ liệu và tài nguyên được transaction manager quản lý**.

### Tại sao một thao tác nghiệp vụ có thể cần nhiều SQL?

Ví dụ “đặt một đơn hàng” có thể yêu cầu:

1. Kiểm tra sản phẩm và số lượng.
2. Giảm lượng hàng có thể bán hoặc giữ chỗ tồn kho.
3. Tạo `PurchaseOrder` ở trạng thái mới.
4. Tạo các `OrderLine`.
5. Lưu một sự kiện gửi sang hệ thống xử lý đơn.

Nếu chỉ thực hiện bước 3 rồi dừng, sẽ có đơn hàng nhưng chưa giữ hàng. Nếu chỉ thực hiện bước 2 rồi bước 3 lỗi, hàng bị trừ nhưng không có đơn. Đó là **trạng thái trung gian sai**, dù từng câu lệnh SQL riêng lẻ đều hợp lệ.

## 2. Tư duy theo invariant nghiệp vụ, không theo số lượng repository

*Invariant* là quy tắc dữ liệu phải đúng sau mỗi thao tác nghiệp vụ được commit.

Với đặt hàng:

- Tồn kho khả dụng không âm.
- Một đơn đã được chấp nhận phải có các dòng hàng phù hợp.
- Lượng hàng đã giữ phải tương ứng với đơn hàng đang sử dụng nó.
- Một yêu cầu đặt hàng có mã chống gửi trùng chỉ tạo tối đa một kết quả nghiệp vụ theo phạm vi đã quy định.
- Nếu cần phát sự kiện sau khi đặt hàng, sự kiện phải gắn với một đơn thực sự đã commit.

Không phải tất cả invariant đều được giải quyết **chỉ bằng transaction**. Chẳng hạn điều kiện “không bán vượt tồn kho” còn cần **kiểm soát cạnh tranh đồng thời**; transaction riêng lẻ ở mức isolation mặc định không bảo đảm mọi phép “đọc rồi kiểm tra rồi cập nhật” đều an toàn.

Tuy vậy, transaction là nền tảng để những thay đổi **cùng một thao tác** được commit hoặc rollback như một nhóm.

### Đặt ranh giới sai theo từng lời gọi repository

```text
HTTP POST /orders
       |
       v
OrderRepository.save(order)
       |-- transaction riêng --> COMMIT
       |
       v
InventoryRepository.reserve(...)
       |-- transaction riêng --> thất bại
       |
       v
HTTP 500

Kết quả có thể:
  Đơn hàng tồn tại, nhưng tồn kho chưa được giữ.
```

Repository có thể được cấu hình transaction riêng, nhưng **mỗi repository method commit riêng không tự tạo tính nguyên tử cho toàn use case**.

### Đặt ranh giới theo use case

```text
HTTP POST /orders
       |
       v
OrderApplicationService.placeOrder(command)
       |
       +---- BEGIN TRANSACTION ---------------------+
       |                                            |
       |   load/lock inventory                      |
       |   validate availability                    |
       |   reserve quantity                         |
       |   persist order and items                  |
       |   persist outbox event                     |
       |                                            |
       +---- COMMIT hoặc ROLLBACK cả nhóm ---------+
       |
       v
HTTP response
```

Đây thường là thiết kế có thể bảo trì: **controller tiếp nhận yêu cầu**, **application service sở hữu ranh giới nghiệp vụ**, **repository/EntityManager thực hiện thao tác dữ liệu trong transaction hiện hành**.

## 3. ACID bảo đảm điều gì, và không bảo đảm điều gì?

Giao dịch cơ sở dữ liệu thường được diễn giải bằng bốn đặc tính ACID:

| Đặc tính | Ý nghĩa trong thao tác nhiều bước | Giới hạn cần nhớ |
|---|---|---|
| **Atomicity** | Các cập nhật trong một transaction commit hoặc rollback như một nhóm | Không tự rollback một HTTP call/email đã gửi ra ngoài |
| **Consistency** | Transaction cùng các ràng buộc và quy tắc phù hợp giúp giữ dữ liệu hợp lệ | Database không tự biết mọi invariant nghiệp vụ nếu chưa được mô hình hóa |
| **Isolation** | Các transaction đồng thời được quan sát theo mức isolation và cơ chế khóa | Không phải mọi mức isolation đều ngăn lost update, phantom hoặc write skew |
| **Durability** | Một commit thành công được bảo vệ theo cam kết durability của database | Không đồng nghĩa mọi downstream service đã nhận sự kiện |

Giả sử trong transaction có:

```text
UPDATE inventory_stock
INSERT purchase_order
HTTP POST đến cổng thanh toán
INSERT outbox_event
```

Nếu HTTP POST đã làm cổng thanh toán thu tiền, rồi `INSERT outbox_event` gây lỗi khiến database rollback, **tiền đã được thu không tự hoàn lại chỉ vì SQL rollback**.

Đó là lý do **ranh giới transaction của database không thể tùy tiện mở rộng bằng một đoạn code gọi dịch vụ bên ngoài**. Một transaction thông thường của Hibernate chỉ điều phối tài nguyên được transaction manager quản lý, không biến mọi tác dụng phụ của chương trình thành một phần của ACID.

## 4. Nên đặt transaction ở tầng nào?

Một kiến trúc phổ biến:

```text
Controller / HTTP adapter
          |
          | request DTO
          v
Application service / Use case
    @Transactional
          |
          +--> Repository A
          +--> Repository B
          +--> Domain methods
          +--> EntityManager
          |
          v
Transaction manager
          |
          v
Hibernate Session + JDBC connection
          |
          v
Database
```

**Application service** thường là nơi biết rõ “một thao tác nghiệp vụ gồm những bước gì”. Vì vậy đây là vị trí tự nhiên để đặt transaction boundary.

### Vì sao không đặt transaction chỉ ở controller?

Controller nên xử lý giao thức và điều phối đầu vào/đầu ra. Nếu transaction mở xuyên suốt controller, nó có thể bao gồm:

- Đọc/parse body hoặc các bước không cần giữ connection.
- Gọi API ngoài.
- Mapping response và serialization.
- Những hoạt động chậm hoặc có thể lỗi vì lý do không liên quan database.

Kéo dài transaction làm tăng thời gian giữ lock, connection và khả năng contention. Controller có thể gọi một use case có transaction, rồi trả về DTO sau khi transaction kết thúc.

### Vì sao không chỉ đặt transaction ở repository?

Repository quản lý thao tác truy cập dữ liệu nhưng không nhất thiết hiểu quy tắc **phải cập nhật nhiều entity cùng lúc**. Mỗi repository method có một transaction riêng là quá nhỏ với nhiều use case.

Trong Spring, nhiều repository có hỗ trợ transaction mặc định hoặc tham gia transaction đang có; **nếu một application service dùng `@Transactional` đúng cách**, các repository thường sẽ tham gia cùng transaction thay vì mỗi lời gọi tự commit, theo propagation và transaction manager đã cấu hình.

### Có trường hợp transaction ở tầng khác không?

Có. Trong batch job, message consumer, command handler hoặc scheduled task, **method thực thi một đơn vị nghiệp vụ** cũng có thể là ranh giới transaction.

Nguyên tắc không phải “mọi method service đều có annotation”; nguyên tắc là **đặt transaction quanh đúng unit of work có invariant cần bảo vệ**.

## 5. Ví dụ nghiệp vụ: giữ hàng và tạo đơn

Giả sử hệ thống có bảng tồn kho `inventory_stock`, bảng đơn hàng `purchase_orders` và bảng sự kiện chờ phát `outbox_messages`.

Nhu cầu:

- Khách hàng chọn một sản phẩm với số lượng dương.
- Chỉ chấp nhận nếu tồn kho đủ.
- Giảm tồn kho và tạo đơn **trong cùng transaction database**.
- Ghi một outbox message để tiến trình khác phát sự kiện **sau khi đơn được commit**.
- Không thực hiện thanh toán bên ngoài ở giữa transaction.

### Schema minh họa PostgreSQL

```sql
CREATE TABLE inventory_stock (
    product_id BIGINT PRIMARY KEY,
    available_quantity INTEGER NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_inventory_non_negative
        CHECK (available_quantity >= 0)
);

CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    request_key VARCHAR(120) NOT NULL UNIQUE,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT ck_order_positive_quantity
        CHECK (quantity > 0)
);

CREATE TABLE outbox_messages (
    id UUID PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    aggregate_id UUID NOT NULL,
    payload VARCHAR(2000) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE NULL
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_messages(published_at, created_at);
```

Đây là DDL minh họa cho PostgreSQL. Cú pháp UUID, timestamp và các kiểu dữ liệu phải được điều chỉnh nếu dùng database khác. Trong production nên quản lý schema bằng migration và bổ sung các khóa ngoại/ràng buộc theo mô hình sản phẩm, tenant và chi tiết đơn thực tế.

### Entity tồn kho

```java
import jakarta.persistence.*;

@Entity
@Table(name = "inventory_stock")
public class InventoryStock {

    @Id
    @Column(name = "product_id")
    private Long productId;

    @Column(name = "available_quantity", nullable = false)
    private int availableQuantity;

    @Version
    private long version;

    protected InventoryStock() {
    }

    public void reserve(int requestedQuantity) {
        if (requestedQuantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        if (availableQuantity < requestedQuantity) {
            throw new InsufficientStockException();
        }

        availableQuantity -= requestedQuantity;
    }
}
```

`InsufficientStockException` là exception nghiệp vụ do ứng dụng định nghĩa. Ví dụ:

```java
public class InsufficientStockException
        extends RuntimeException {

    public InsufficientStockException() {
        super("Not enough available inventory");
    }
}
```

Entity đã managed nên method `reserve` chỉ cần sửa trường `availableQuantity`; Hibernate dirty checking có thể sinh `UPDATE` tại flush. `@Version` hỗ trợ phát hiện cạnh tranh cập nhật theo optimistic locking nếu dùng các đường update versioned thông thường.

### Entity đơn hàng

```java
import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private UUID id;

    @Column(name = "request_key", nullable = false, unique = true, length = 120)
    private String requestKey;

    @Column(name = "product_id", nullable = false)
    private Long productId;

    @Column(nullable = false)
    private int quantity;

    @Column(nullable = false, length = 30)
    private String status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            UUID id,
            String requestKey,
            Long productId,
            int quantity) {

        this.id = id;
        this.requestKey = requestKey;
        this.productId = productId;
        this.quantity = quantity;
        this.status = "RESERVED";
        this.createdAt = Instant.now();
    }

    public UUID getId() {
        return id;
    }
}
```

Để ví dụ rõ ràng, khóa UUID được **ứng dụng cấp trước `persist`**, không dựa vào thời điểm database sinh ID. Điều này giúp tạo nội dung sự kiện với `orderId` đã biết. Trong dự án thực, có thể dùng `SEQUENCE` hoặc cơ chế ID khác, nhưng cần hiểu thời điểm sinh khóa.

### Entity outbox

```java
import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "outbox_messages")
public class OutboxMessage {

    @Id
    private UUID id;

    @Column(name = "event_type", nullable = false, length = 100)
    private String eventType;

    @Column(name = "aggregate_id", nullable = false)
    private UUID aggregateId;

    @Column(nullable = false, length = 2000)
    private String payload;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "published_at")
    private Instant publishedAt;

    protected OutboxMessage() {
    }

    public OutboxMessage(
            String eventType,
            UUID aggregateId,
            String payload) {

        this.id = UUID.randomUUID();
        this.eventType = eventType;
        this.aggregateId = aggregateId;
        this.payload = payload;
        this.createdAt = Instant.now();
    }
}
```

Outbox message là **dữ liệu trong cùng database**, chưa phải sự kiện đã được gửi qua mạng. Chính sự phân biệt này cho phép việc tạo đơn và ghi ý định phát sự kiện được commit cùng nhau.

## 6. Application service đặt ranh giới giao dịch

Một command DTO:

```java
public record PlaceOrderCommand(
    Long productId,
    int quantity,
    String requestKey
) {}
```

Service dùng Spring transaction và Jakarta Persistence:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class PlaceOrderService {

    private final EntityManager em;

    public PlaceOrderService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        if (command.productId() == null
                || command.quantity() <= 0
                || command.requestKey() == null
                || command.requestKey().isBlank()) {

            throw new IllegalArgumentException(
                "Invalid order command"
            );
        }

        // Khóa hàng tồn kho trong transaction hiện hành.
        InventoryStock stock = em.find(
            InventoryStock.class,
            command.productId(),
            LockModeType.PESSIMISTIC_WRITE
        );

        if (stock == null) {
            throw new IllegalArgumentException(
                "Inventory record does not exist"
            );
        }

        // Thay đổi entity managed; Hibernate theo dõi dirty state.
        stock.reserve(command.quantity());

        PurchaseOrder order = new PurchaseOrder(
            UUID.randomUUID(),
            command.requestKey(),
            command.productId(),
            command.quantity()
        );

        em.persist(order);

        OutboxMessage event = new OutboxMessage(
            "ORDER_RESERVED",
            order.getId(),
            "orderId=" + order.getId()
        );

        em.persist(event);

        return order.getId();
    }
}
```

Đoạn mã tập trung vào ranh giới transaction, có những giả định rõ ràng:

- Spring đã bật transaction management và service method được gọi qua bean/proxy được Spring quản lý.
- `EntityManager` được kết nối với **transaction manager của database chứa ba bảng**.
- `InventoryStock` tồn tại cho sản phẩm hợp lệ.
- Khóa bi quan `PESSIMISTIC_WRITE` được dialect/database hỗ trợ và được giữ trong transaction phù hợp.
- `requestKey` có unique constraint thực trong database; xử lý trường hợp gửi lại yêu cầu sẽ được thiết kế thêm ở phần idempotency.
- Ví dụ chỉ có **một dòng sản phẩm**; với nhiều dòng cần thống nhất thứ tự lock để hạn chế deadlock.
- Service chưa thực hiện thanh toán, gửi email hay HTTP request nào ra ngoài.

**Mọi cập nhật của `stock`, `order` và `event` nằm trong cùng transaction** nếu các thao tác thật sự sử dụng cùng transaction manager và resource. Khi method hoàn tất thành công, Spring thường yêu cầu flush/commit; khi có unchecked exception dẫn đến rollback, các thay đổi DB trong transaction được hủy bỏ.

### Diễn biến giao dịch

```text
placeOrder()
  |
  +-- BEGIN TRANSACTION
  |
  +-- SELECT inventory_stock ... FOR UPDATE
  |
  +-- stock.reserve(quantity)
  |     [managed state đổi, có thể chưa UPDATE ngay]
  |
  +-- persist(order)
  |     [INSERT có thể đang chờ flush]
  |
  +-- persist(outboxEvent)
  |     [INSERT có thể đang chờ flush]
  |
  +-- flush khi cần / trước commit
  |       UPDATE inventory_stock
  |       INSERT purchase_orders
  |       INSERT outbox_messages
  |
  +-- COMMIT hoặc ROLLBACK cả transaction
  |
  v
Trả kết quả ở boundary
```

Đây là **transaction database nguyên tử** cho trạng thái đặt hàng. Không phải một transaction cho “toàn bộ vòng đời đơn hàng” từ lúc khách click đến lúc giao hàng thành công.

## 7. Bước nào phải cùng commit, bước nào nên tách?

Một cách quyết định:

> Nếu chỉ một phần thao tác được commit mà phần còn lại thất bại, invariant nghiệp vụ nào sẽ bị phá vỡ?

Ví dụ:

| Bước | Nên thuộc transaction tạo đơn? | Lý do |
|---|---|---|
| Kiểm tra và cập nhật tồn kho của DB hiện tại | Thường có | Gắn tính hợp lệ của đặt hàng với số lượng đã giữ |
| Tạo đơn hàng và các dòng hàng | Có | Đơn phải nhất quán với dữ liệu nguồn |
| Ghi outbox message cho đơn vừa tạo | Có | Không để có đơn đã commit mà thiếu ý định phát sự kiện |
| Cập nhật một bảng thống kê trong cùng DB | Tùy invariant | Nếu buộc phải chính xác ngay, có thể cùng transaction; nếu chỉ phục vụ analytics, thường tách |
| Gửi email xác nhận | Không nên thực hiện trực tiếp trong transaction DB | Email không được rollback bằng SQL |
| Gọi API thanh toán bên ngoài | Không nên giữ transaction DB xuyên qua lời gọi | Latency, lỗi mạng và external side effect |
| Tạo file ở object storage | Thường cần phối hợp riêng | DB rollback không tự xóa file đã upload |
| Đẩy message trực tiếp lên broker | Không tự thuộc cùng transaction DB | Cần outbox hoặc giao thức phối hợp tương đương |
| Chạy báo cáo tổng hợp tốn nhiều giây | Thường tách | Transaction dài giữ tài nguyên và tăng contention |

Đối với các bước chỉ đọc, có thể xác định có cần thực hiện trong cùng **snapshot/transaction** với ghi dữ liệu không. Một validation quan trọng để quyết định ghi phải nhìn thấy trạng thái nhất quán tương ứng; nhưng nhiều truy vấn phụ như lấy danh sách gợi ý hoặc tính dashboard có thể được thực hiện ngoài transaction ghi.

## 8. Tại sao không gọi dịch vụ ngoài khi đang giữ transaction?

Giả sử code:

```java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    reserveStockInDatabase(command);
    createOrderInDatabase(command);

    paymentGateway.charge(...); // Lời gọi HTTP bên ngoài.

    savePaymentResultInDatabase(...);
}
```

Có ít nhất ba vấn đề:

1. **Transaction kéo dài:** giữ JDBC connection và có thể giữ lock trong lúc chờ mạng.
2. **Không có rollback phân tán:** nếu payment thành công rồi SQL cuối thất bại, database rollback nhưng tiền đã bị trừ.
3. **Không chắc trạng thái sau timeout:** HTTP timeout không chứng minh bên ngoài chưa xử lý. Retry thiếu idempotency có thể tạo thu tiền lặp.

Một phương án thường phù hợp:

```text
Transaction 1 (DB):
    reserve inventory
    create order [PENDING_PAYMENT]
    create outbox event [PAYMENT_REQUESTED]
    COMMIT

Outbox publisher:
    publish message với event ID cố định
    retry nếu cần

Payment worker:
    gọi gateway với idempotency key
    nhận kết quả

Transaction 2 (DB):
    cập nhật order [PAID] hoặc [PAYMENT_FAILED]
    tạo event tiếp theo
    COMMIT

Nếu thanh toán thất bại:
    transaction bù trừ để trả lại phần stock đã giữ,
    theo chính sách nghiệp vụ.
```

Đây không còn là một transaction ACID duy nhất giữa database và payment gateway. Nó là **một workflow nhiều giao dịch cục bộ**, cần state machine và xử lý thất bại/đền bù (*saga*).

### Không đồng nhất afterCommit callback với outbox bền vững

Một ứng dụng có thể dùng callback chỉ chạy sau khi commit để gửi message. Cách này tránh gửi message khi transaction rollback, nhưng vẫn còn một cửa sổ lỗi:

```text
DB COMMIT thành công
       |
       | ứng dụng crash
       v
chưa kịp gửi message
```

**Transactional outbox** giảm rủi ro đó bằng cách lưu message vào cùng database transaction với business change. Sau commit, một publisher độc lập đọc outbox và phát message có retry.

Tuy nhiên, outbox thường cung cấp **at-least-once delivery** chứ không tự đảm bảo exactly-once end-to-end. Consumer phải xử lý trùng một cách idempotent.

## 9. `@Transactional` trong Spring: ranh giới thực sự nằm ở đâu?

Ví dụ:

```java
@Service
public class OrderApplicationService {

    @Transactional
    public void execute() {
        // Các lời gọi repository cùng tham gia transaction
        // nếu propagation và transaction manager phù hợp.
    }
}
```

Trong Spring transaction management kiểu proxy thông dụng, interceptor mở/tham gia transaction trước khi chạy method và commit/rollback sau khi method kết thúc.

Một luồng gọi:

```text
Controller -> Spring proxy -> Service method
                    |
                    +-- transaction begin / join
                    |
                    +-- method body
                    |
                    +-- commit hoặc rollback
```

Vì vậy, không phải mọi lời gọi Java đến một method được gắn annotation đều chắc chắn đi qua interceptor.

### 9.1. Self-invocation

Ví dụ:

```java
@Service
public class OrderService {

    public void handleRequest() {
        placeOrderInternal(); // Gọi trực tiếp trong cùng object.
    }

    @Transactional
    public void placeOrderInternal() {
        // Tưởng rằng đã mở transaction.
    }
}
```

Với mô hình Spring proxy AOP thông dụng, lời gọi từ `handleRequest()` sang `placeOrderInternal()` là **self-invocation**, có thể bỏ qua transaction interceptor.

Phương án phổ biến:

- Đặt transaction lên public entry-point thực sự được gọi từ bean khác.
- Tách use case thành một bean service riêng và gọi qua bean được Spring quản lý.
- Dùng cấu hình weaving phù hợp nếu ứng dụng chủ động lựa chọn mô hình khác, nhưng không xem đó là mặc định.

### 9.2. Method private/final và việc proxy hóa

Khả năng áp dụng `@Transactional` phụ thuộc kiểu proxy (JDK dynamic proxy, class-based proxy), visibility và phương thức có thể intercept. Với class-based proxy, `final` method không thể được subclass override để intercept theo cách thông thường; private method cũng không được intercept như public service method.

Để tránh mơ hồ, hãy đặt transaction trên **method use case được truy cập qua Spring-managed bean** theo hình thức được version/configuration hỗ trợ.

### 9.3. Không dùng `new Service()` thay Spring bean

```java
OrderService service = new OrderService();
service.placeOrder(...);
```

Một instance tạo thủ công không đi qua container injection/proxy sẽ không được Spring tự động áp transaction như một bean đã quản lý. Đảm bảo luồng ứng dụng lấy service từ dependency injection phù hợp.

### 9.4. Đừng suy luận từ annotation nếu không biết transaction manager

Ứng dụng có thể có nhiều database hoặc nhiều transaction manager. Một `@Transactional` không nhất thiết gom các thao tác trên **hai datasource độc lập** vào cùng một transaction ACID.

Cần xác định đúng transaction manager quản lý connection/Hibernate Session của từng thao tác. Nếu nhiều nguồn dữ liệu tham gia, phải dùng một cơ chế điều phối được thiết kế cho yêu cầu ấy; không chỉ đặt cùng một annotation.

## 10. Propagation: method con có dùng cùng transaction không?

Spring định nghĩa nhiều chế độ *transaction propagation*. Chúng ảnh hưởng trực tiếp đến **một thao tác nghiệp vụ nhiều bước có thật sự nằm trong một transaction hay không**.

| Propagation | Cách hoạt động thông dụng | Rủi ro nếu dùng sai |
|---|---|---|
| **`REQUIRED`** (mặc định) | Tham gia transaction hiện có; nếu chưa có thì tạo mới | Cần nhớ các method con có thể đánh dấu transaction chung rollback-only |
| **`REQUIRES_NEW`** | Tạm dừng transaction hiện tại và tạo transaction độc lập | Bước con có thể commit ngay cả khi bước cha rollback |
| **`SUPPORTS`** | Có transaction thì tham gia, không có thì chạy không transaction | Bước ghi có thể không có boundary như mong muốn |
| **`MANDATORY`** | Bắt buộc đã có transaction | Hữu ích để bảo vệ một method chỉ được gọi trong unit of work |
| **`NOT_SUPPORTED`** | Chạy không tham gia transaction hiện tại | Không thích hợp cho bước ghi phải cùng commit |
| **`NEVER`** | Từ chối khi đang có transaction | Dùng cho API có hợp đồng đặc thù, không phải tạo đơn nhiều bước |
| **`NESTED`** | Có thể dùng savepoint trong transaction hiện hữu nếu TM/resource hỗ trợ | Không đồng nghĩa một transaction độc lập; hỗ trợ JPA có giới hạn |

### 10.1. Vì sao `REQUIRED` thường phù hợp?

Giả sử:

```java
@Service
public class OrderService {

    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    @Transactional
    public void placeOrder(...) {
        inventoryService.reserve(...);
        orderRepository.save(...);
    }
}
```

Nếu `inventoryService.reserve` và repository dùng `REQUIRED` với **cùng transaction manager**, chúng thường tham gia transaction của `placeOrder`. Khi bước cuối thất bại, bước reserve trong cùng DB transaction cũng rollback.

Đây là hành vi mong muốn khi hai bước phải cùng thành công.

### 10.2. Sai lầm với `REQUIRES_NEW`

```java
@Service
public class InventoryService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void reserve(...) {
        // UPDATE inventory_stock
    }
}
```

Nếu `placeOrder` đã mở transaction, lời gọi tới method trên qua proxy Spring có thể mở **transaction riêng**. Khi `reserve` thành công và commit, sau đó tạo đơn thất bại và transaction ngoài rollback, **tồn kho vẫn bị trừ**.

```text
Outer transaction: placeOrder()
     |
     +-- inner REQUIRES_NEW: reserve stock -> COMMIT
     |
     +-- persist order -> lỗi
     |
     +-- outer ROLLBACK

Tồn kho đã commit, đơn không có.
```

`REQUIRES_NEW` có trường hợp hợp lý, như ghi một **audit of failure** độc lập có chủ đích, nhưng không phù hợp nếu bước con phải rollback cùng thao tác nghiệp vụ chính.

Ngoài ra, transaction độc lập có thể cần thêm connection khi transaction ngoài vẫn giữ connection, tăng áp lực connection pool và nguy cơ chờ tài nguyên.

### 10.3. `NESTED` không phải “rollback riêng mãi mãi”

`NESTED` thường dựa vào database savepoint trong transaction vật lý hiện hành, nếu transaction manager và driver hỗ trợ. Có thể rollback một đoạn về savepoint, nhưng commit của transaction ngoài vẫn quyết định các thay đổi còn lại có thực sự commit không.

Với JpaTransactionManager/EntityManager, hỗ trợ nested và đồng bộ persistence context có giới hạn; không nên mặc định việc dùng `NESTED` có semantics giống nested transaction của database cho mọi JPA mapping.

Khi nhu cầu là “bước nào thất bại cũng rollback cả đặt hàng”, `REQUIRED` đơn giản hơn và dễ hiểu hơn.

## 11. Rollback trong Spring: đừng để exception làm thay đổi ý nghĩa nghiệp vụ

Mặc định, Spring `@Transactional` thường rollback khi có **unchecked exception** (`RuntimeException`) hoặc `Error` thoát khỏi method. Checked exception (`Exception` nhưng không phải RuntimeException) **không mặc định** kích hoạt rollback trong nhiều cấu hình Spring truyền thống, trừ khi được khai báo hoặc có chính sách global khác.

Ví dụ:

```java
@Transactional
public void placeOrder(...) {
    reserveStock();
    persistOrder();

    throw new IllegalStateException(
        "Cannot complete order"
    );
}
```

Với unchecked exception thoát ra qua transaction interceptor, transaction thông thường được rollback.

### 11.1. Checked exception cần policy rõ

```java
@Transactional(rollbackFor = BusinessValidationException.class)
public void placeOrder(...) throws BusinessValidationException {
    reserveStock();

    if (someBusinessRuleFails()) {
        throw new BusinessValidationException(
            "Order is not allowed"
        );
    }

    persistOrder();
}
```

Ví dụ giả định `BusinessValidationException` là một **checked exception** của ứng dụng. `rollbackFor` làm rõ ý định rollback trong cấu hình Spring hỗ trợ thuộc tính này.

Tùy version/configuration, Spring có thể hỗ trợ các quy tắc rollback mặc định mở rộng. Đừng áp dụng một câu khẳng định tuyệt đối mà không xem transaction policy của dự án.

### 11.2. Catch exception rồi vẫn return bình thường

Đoạn code nguy hiểm:

```java
@Transactional
public void placeOrder(...) {
    reserveStock();

    try {
        persistOrderAndNotify();
    } catch (RuntimeException ex) {
        log.warn("Order failed", ex);
    }

    // Method kết thúc bình thường.
}
```

Nếu exception chỉ bị bắt và không làm transaction bị đánh dấu rollback-only, interceptor có thể **commit các thay đổi đã làm trước đó**. Không nên nuốt lỗi rồi giả định transaction tự biết business operation đã thất bại.

Hướng xử lý:

- Để exception phù hợp được truyền ra boundary.
- Hoặc đánh dấu rollback-only có chủ đích khi được framework hỗ trợ, đồng thời trả về lỗi nhất quán.
- Nếu muốn cho phép một nhánh optional thất bại nhưng vẫn commit phần còn lại, hãy thiết kế invariant và propagation có chủ đích thay vì catch tùy tiện.

### 11.3. `UnexpectedRollbackException`

Một method con tham gia transaction `REQUIRED` có thể đánh dấu transaction chung rollback-only. Method ngoài bắt exception và cố return bình thường, nhưng cuối cùng transaction manager vẫn không thể commit và có thể ném `UnexpectedRollbackException`.

Đó không phải lỗi ngẫu nhiên: **transaction đã được đánh dấu không thể commit**, dù code ngoài cố che exception. Phải sửa luồng rollback/error handling, không tìm cách ép commit bằng flush.

## 12. Flush nằm ở đâu trong transaction nhiều bước?

Trong Hibernate, thay đổi của managed entity thường được giữ trong persistence context cho đến khi `flush` xảy ra. Flush có thể được kích hoạt:

- Bởi `entityManager.flush()`.
- Khi một truy vấn cần thấy thay đổi chưa đồng bộ, theo flush mode phù hợp.
- Khi transaction hoàn tất bằng commit ở các chế độ thông thường.
- Một số hành vi sinh ID hoặc truy vấn native có thể thực thi SQL sớm tùy mapping/API.

Ví dụ:

```java
@Transactional
public void reserveAndCreate(...) {
    InventoryStock stock = em.find(
        InventoryStock.class, productId
    );

    stock.reserve(quantity); // Chưa chắc đã UPDATE ngay.

    PurchaseOrder order = new PurchaseOrder(...);
    em.persist(order);       // Chưa chắc đã INSERT ngay.

    // Hibernate đồng bộ SQL khi cần và trước commit.
}
```

**Flush không phải commit.** Nếu Hibernate đã chạy `UPDATE inventory_stock` và `INSERT purchase_orders` rồi bước sau xảy ra lỗi, rollback transaction vẫn có thể hủy những thay đổi SQL đó.

### Vì sao có SQL trước bước cuối?

Giả sử giữa các bước có truy vấn JPQL kiểm tra số đơn đang ở trạng thái `RESERVED`. Ở flush mode `AUTO`, Hibernate có thể flush các thay đổi liên quan trước truy vấn để kết quả query phản ánh state đang pending.

Do đó, **thứ tự SQL trong log không nhất thiết giống thứ tự lời gọi Java**, và sự xuất hiện SQL không đồng nghĩa transaction đã kết thúc.

### Có nên gọi flush để phát hiện lỗi sớm?

Đôi khi hợp lý nếu bước tiếp theo phụ thuộc vào constraint hoặc giá trị do database sinh:

```java
em.persist(order);
em.flush(); // Có thể phát hiện lỗi unique/foreign-key sớm.
```

Nhưng flush:

- Không bảo đảm commit sẽ thành công.
- Có thể làm giảm cơ hội JDBC batching nếu gọi quá thường xuyên.
- Không thay thế validation/locking.
- Một số ràng buộc được database trì hoãn đến commit, nên flush chưa phát hiện tất cả lỗi.

Nếu flush thất bại, transaction và persistence context có thể không còn an toàn để tiếp tục; thông thường cần rollback unit of work và thử lại trong context mới nếu nghiệp vụ cho phép.

## 13. Transaction nguyên tử chưa đủ để ngăn bán vượt tồn kho

Hai người đặt mua cùng một sản phẩm còn một đơn vị:

```text
inventory.available = 1

Transaction A                  Transaction B
---------------------------    ---------------------------
READ available = 1             READ available = 1
check >= 1 -> true             check >= 1 -> true
set available = 0              set available = 0
INSERT order A                 INSERT order B
COMMIT                         COMMIT
```

Nếu không có cơ chế concurrency thích hợp, cả hai request có thể tưởng đã giữ hàng, dẫn tới **hai đơn cho một đơn vị tồn**. Transaction giúp mỗi request atomic nhưng **không tự bảo đảm logic đọc–kiểm tra–ghi là serializable** ở mọi isolation level.

### 13.1. Pessimistic locking

Trong ví dụ service chính, ta dùng:

```java
InventoryStock stock = em.find(
    InventoryStock.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Với database/dialect hỗ trợ khóa hàng, transaction đang xử lý tồn kho có thể giữ lock ngăn transaction khác cập nhật cùng hàng cho đến khi transaction kết thúc.

Các transaction khác phải chờ hoặc gặp timeout/lock exception theo DB/configuration. Điều này giúp tuần tự hóa thao tác giữ tồn kho ở phạm vi hàng đang khóa.

**Không phải mọi truy vấn read hoặc mọi thao tác trên các hàng khác cũng bị khóa**. Kiểu SQL khóa, phạm vi khóa và ảnh hưởng isolation phụ thuộc database.

### 13.2. Optimistic locking bằng `@Version`

Một phương án khác là:

```java
@Version
private long version;
```

Hibernate có thể sinh update tương đương:

```sql
UPDATE inventory_stock
SET available_quantity = ?,
    version = ?
WHERE product_id = ?
  AND version = ?;
```

Nếu hai transaction cùng dùng version cũ, một transaction có thể update thành công, transaction kia gặp optimistic locking conflict khi flush/commit.

Khi đó, cần rollback **toàn bộ thao tác đặt hàng** của transaction thua và có chính sách retry/reject phù hợp; không chỉ retry riêng câu update tồn kho trong cùng persistence context đã lỗi.

### 13.3. Atomic conditional update

Trong một số workload, dùng câu SQL cập nhật có điều kiện cũng là lựa chọn mạnh:

```sql
UPDATE inventory_stock
SET available_quantity = available_quantity - :qty
WHERE product_id = :productId
  AND available_quantity >= :qty;
```

Ứng dụng kiểm tra **số hàng được cập nhật**: nếu 0, không thể giữ số lượng theo điều kiện. Đây là cách tránh khoảng trống giữa đọc và cập nhật khi database thực thi điều kiện update một cách nguyên tử.

Tuy nhiên, bulk/native update **không tự đồng bộ state của entity managed** đang nằm trong Hibernate persistence context; cần kiểm soát `flush`, `refresh` hoặc `clear` và không trộn state cũ vào quyết định tiếp theo. Cũng cần phối hợp với version nếu ứng dụng dùng optimistic locking.

**Bài học:** chọn transaction boundary là bước đầu. Với invariant có cạnh tranh, còn phải chọn một chiến lược **locking/atomic update/isolation** phù hợp.

## 14. Isolation level ảnh hưởng đến thao tác nhiều bước ra sao?

Database hỗ trợ các mức cô lập khác nhau. Một số mức được biết đến là:

- **READ UNCOMMITTED**: cho phép mức quan sát yếu hơn; hỗ trợ/semantics tùy database.
- **READ COMMITTED**: một transaction thường không đọc dữ liệu chưa commit của transaction khác, nhưng có thể thấy giá trị mới giữa các lần đọc.
- **REPEATABLE READ**: hạn chế một số thay đổi quan sát trong transaction; chi tiết phantom/write skew khác nhau theo DB.
- **SERIALIZABLE**: cố bảo đảm kết quả tương đương một thứ tự thực thi tuần tự các transaction, nhưng có thể từ chối một transaction do xung đột và đòi hỏi retry.

Không nên suy diễn cùng một isolation name sẽ có semantics y hệt ở PostgreSQL, MySQL, SQL Server và Oracle. Hệ quản trị có các cách triển khai locking/MVCC khác nhau.

### Một ví dụ write skew

Giả sử quy tắc: một ca trực phải luôn có ít nhất một bác sĩ trực. T1 đọc thấy B đang trực rồi tắt A; T2 đọc thấy A đang trực rồi tắt B. Nếu mỗi transaction cập nhật một hàng khác, optimistic locking của **từng hàng riêng lẻ** có thể không phát hiện invariant “luôn còn một bác sĩ”.

Trong trường hợp ấy, cần một constraint/lock/quy tắc transaction bảo vệ **toàn bộ điều kiện**, hoặc isolation thích hợp với xử lý retry.

Điều này cho thấy không thể giải quyết mọi invariant chỉ bằng `@Transactional` và `@Version` trên từng entity.

### Chọn isolation ở đâu?

Ví dụ Spring:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void placeOrder(...) {
    // ...
}
```

Khả năng áp dụng mức isolation phụ thuộc transaction manager, datasource và việc method có thực sự tạo transaction mới hay chỉ tham gia transaction hiện hành. Khi tham gia transaction đã tồn tại, yêu cầu isolation mới có thể không được áp dụng như mong đợi.

Đừng tùy tiện nâng tất cả transaction lên SERIALIZABLE: điều đó có thể tăng xung đột/retry và giảm throughput. Nên bắt đầu từ **invariant cụ thể** và cách DB thực hiện khóa.

## 15. Nhiều sản phẩm trong một đơn: thêm vấn đề deadlock

Giả sử đơn có hai sản phẩm:

```text
Order A: đặt Product 10, rồi Product 20
Order B: đặt Product 20, rồi Product 10
```

Nếu cả hai transaction dùng `PESSIMISTIC_WRITE` theo thứ tự riêng:

```text
T1 lock Product 10
T2 lock Product 20
T1 chờ Product 20
T2 chờ Product 10

=> Có thể xảy ra deadlock.
```

Database thường có cơ chế phát hiện deadlock và rollback một transaction, nhưng ứng dụng vẫn phải xử lý lỗi.

Một chiến lược giảm rủi ro:

1. Chuẩn hóa, gộp số lượng theo product ID nếu request có nhiều dòng trùng nhau.
2. **Sắp product IDs theo một thứ tự cố định**.
3. Lấy lock/cập nhật các hàng theo cùng thứ tự cho mọi transaction.
4. Thực hiện kiểm tra và giảm tồn kho trong cùng transaction.
5. Khi gặp deadlock hoặc serialization failure, rollback và cân nhắc retry **toàn bộ thao tác** với giới hạn hợp lý.

```java
List<Long> sortedProductIds = request.productIds()
    .stream()
    .distinct()
    .sorted()
    .toList();

for (Long id : sortedProductIds) {
    InventoryStock stock = em.find(
        InventoryStock.class,
        id,
        LockModeType.PESSIMISTIC_WRITE
    );
    // Kiểm tra, giữ chỗ theo quy tắc domain.
}
```

Thứ tự lock nhất quán **giảm** deadlock nhưng không cam kết loại bỏ mọi deadlock từ index, FK, trigger hoặc các workflow khác.

## 16. Idempotency khi request nhiều bước bị gửi lại

Trong thực tế, client có thể timeout rồi gửi lại request đặt hàng. Timeout không chứng minh transaction trước đã rollback: có thể database đã commit nhưng response bị mất trên đường mạng.

Nếu thiếu idempotency, retry có thể tạo **hai đơn hàng và trừ tồn kho hai lần**.

### Sử dụng idempotency key

Request có một khóa ổn định cho một lần đặt hàng:

```text
requestKey = "customer-42:checkout-session-abc"
```

Database đặt unique constraint cho phạm vi phù hợp:

```sql
UNIQUE (request_key)
```

Ví dụ đơn giản dùng unique toàn cục; hệ thống đa tenant hoặc nhiều loại thao tác thường cần khóa kết hợp `(tenant_id, operation_type, request_key)`.

Khi hai request cùng key chạy đồng thời, **chỉ kiểm tra `SELECT` trước rồi insert là chưa đủ**:

```text
Request A: SELECT key -> chưa có
Request B: SELECT key -> chưa có
Request A: INSERT key -> thành công
Request B: INSERT key -> unique conflict
```

Unique constraint ở database là lớp bảo vệ cuối cùng. Ứng dụng cần xử lý duplicate một cách có chủ đích:

- Nếu cùng khóa và cùng payload nghiệp vụ, trả lại kết quả đã lưu (nếu hợp đồng yêu cầu).
- Nếu cùng khóa nhưng payload khác, từ chối như một xung đột.
- Nếu transaction đầu chưa hoàn tất, có thể chờ hoặc trả trạng thái đang xử lý theo thiết kế.
- Nếu insert gây lỗi constraint và transaction đã ở trạng thái thất bại, **không cố tiếp tục query trong cùng EntityManager/transaction đã lỗi**; truy vấn kết quả đã commit trong một unit of work mới khi thích hợp.

Idempotency là vấn đề **đúng hành vi khi retry**, không phải chỉ là cách bắt ngoại lệ duplicate key rồi bỏ qua.

## 17. Outbox: gắn sự kiện với transaction tạo đơn

Nếu đặt hàng thành công phải dẫn đến thông báo cho service khác, cách trực tiếp nhưng rủi ro là:

```java
@Transactional
public void placeOrder(...) {
    em.persist(order);
    kafkaProducer.send(...); // Gửi trực tiếp giữa transaction.
}
```

Hai cửa sổ lỗi:

- Message đã gửi, nhưng DB rollback → downstream nhận sự kiện cho đơn không tồn tại.
- DB commit thành công, nhưng ứng dụng crash trước khi gửi → downstream không nhận sự kiện.

### Transactional outbox

Trong transaction tạo đơn:

```java
em.persist(order);
em.persist(new OutboxMessage(
    "ORDER_RESERVED",
    order.getId(),
    payload
));
```

Cả business row và outbox row được commit/rollback trong cùng database transaction.

Sau đó publisher:

```text
Publisher transaction nhỏ:
    chọn một nhóm outbox messages chưa phát
    claim/lock phù hợp
    COMMIT (tùy thiết kế)

Publish qua broker:
    gửi event với eventId cố định

Publisher transaction tiếp:
    mark published
    COMMIT
```

Việc claim, gửi và đánh dấu đã gửi có những cửa sổ lỗi khác nhau. Nếu gửi thành công nhưng publisher crash trước khi đánh dấu, message có thể được gửi lại. Vì vậy consumer nên có cơ chế:

```text
if eventId đã xử lý:
    bỏ qua/return kết quả cũ
else:
    thực hiện cập nhật và ghi nhận eventId
    trong cùng transaction local
```

**Outbox không biến broker thành một phần của transaction database.** Nó tạo một record bền vững làm cơ sở cho retry và giúp liên kết business change với ý định phát message.

### Không giữ lock DB trong lúc publish qua mạng

Một triển khai outbox không nên mở transaction giữ khóa hàng rồi chờ message broker trong thời gian dài nếu có thể tránh. Có nhiều chiến lược claim/lease, `SKIP LOCKED` hoặc change-data-capture tùy database/hạ tầng, nhưng phải chọn phù hợp với semantics giao hàng và retry.

## 18. Saga: thao tác nghiệp vụ vượt qua một database

Có những workflow gồm nhiều bước ở nhiều service:

```text
Order service DB
      |
      v
Payment service DB
      |
      v
Shipping service DB
```

Nếu mỗi service có database riêng, một `@Transactional` ở OrderService **không tự bao phủ** Payment DB và Shipping DB.

Một *saga* chia workflow thành các transaction cục bộ:

```text
T1: tạo đơn PENDING, giữ inventory
       |
       v
Event/Command: request payment
       |
       +--- payment success ---> T2: mark PAID
       |                            |
       |                            v
       |                      request shipping
       |                            |
       |                            v
       |                      T3: mark SHIPPED
       |
       +--- payment failed ----> T4: release inventory
                                  mark CANCELLED
```

Nếu một bước đã commit nhưng bước sau thất bại, hệ thống không “rollback ngược” mọi database. Nó chạy **compensating transaction** theo quy tắc nghiệp vụ.

Điều cần thiết kế:

- Trạng thái trung gian rõ ràng (`PENDING_PAYMENT`, `PAID`, `CANCELLED`, ...).
- Idempotency cho command/event.
- Retry có giới hạn, dead-letter hoặc quy trình xử lý thủ công.
- Khả năng bù trừ có thật: hoàn tiền là một nghiệp vụ khác, không phải `ROLLBACK SQL`.
- Phát sự kiện đáng tin cậy (outbox).
- Cách xử lý message đến trễ hoặc sai thứ tự.
- Theo dõi tiến trình và đối soát.

### Khi nào không cần saga?

Nếu cả ba bước cập nhật **cùng một database** và được bảo vệ đúng bằng transaction manager, một transaction ACID duy nhất thường đơn giản và mạnh hơn. Không nên triển khai saga phức tạp chỉ để phối hợp hai repository thuộc cùng nguồn dữ liệu.

## 19. JTA, resource-local và phạm vi tài nguyên

Hibernate có thể chạy trong các môi trường quản lý transaction khác nhau.

### Resource-local transaction

Trong ứng dụng Java SE, `EntityManager` có thể tự quản lý transaction qua `EntityTransaction`:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    InventoryStock stock = em.find(
        InventoryStock.class,
        productId,
        LockModeType.PESSIMISTIC_WRITE
    );
    stock.reserve(quantity);

    PurchaseOrder order = new PurchaseOrder(
        UUID.randomUUID(),
        requestKey,
        productId,
        quantity
    );
    em.persist(order);

    em.persist(new OutboxMessage(
        "ORDER_RESERVED",
        order.getId(),
        "orderId=" + order.getId()
    ));

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Ở đây, toàn bộ thao tác nằm giữa `begin` và `commit` của một `EntityManager` resource-local phù hợp. Không gọi `commit` sau mỗi `persist`.

Nếu API của ứng dụng đã có framework transaction manager, thường nên để transaction manager sở hữu boundary thay vì bắt mỗi repository tự gọi `EntityTransaction`.

### JTA / container-managed transaction

Trong môi trường JTA, transaction thường được quản lý bởi container/framework. Code nghiệp vụ không gọi `em.getTransaction().begin()` theo kiểu resource-local. EntityManager tham gia transaction được môi trường quản lý.

JTA có thể điều phối nhiều tài nguyên XA với giao thức như two-phase commit nếu hệ thống **thực sự** được cấu hình các resource/transaction manager tương thích. Nhưng:

- Hai datasource thông thường không tự động trở thành XA chỉ vì có JTA trên classpath.
- Distributed transaction tăng độ phức tạp, thời gian giữ tài nguyên và tình huống phục hồi.
- Một HTTP service, email hay hệ thống bên ngoài không có XA participant tương thích không trở thành transactional chỉ nhờ JTA.

Đối với kiến trúc microservices, nhiều hệ thống chọn transaction cục bộ + outbox/saga thay vì cố dùng một giao dịch phân tán xuyên mọi thành phần.

## 20. Transaction ngắn nhưng đủ bao trùm invariant

Hai kiểu sai đối lập:

### Transaction quá ngắn

```text
BEGIN -> reserve stock -> COMMIT
BEGIN -> create order -> COMMIT
BEGIN -> outbox insert -> COMMIT
```

Nếu ba bước phải cùng đúng, ranh giới này gây ra partial commit.

### Transaction quá dài

```text
BEGIN
    load product
    lock stock
    call pricing service (2 giây)
    call payment service (10 giây)
    upload file (5 giây)
    persist order
    send email
COMMIT
```

Transaction có thể giữ connection/lock rất lâu; chi phí contention và nguy cơ timeout tăng, trong khi các hoạt động bên ngoài vẫn không cùng rollback.

### Ranh giới thực tế hơn

```text
Trước transaction:
    parse request
    kiểm tra cú pháp, authentication
    đọc cấu hình ít biến động
    tính toán thuần túy nếu hợp lý

Trong transaction ngắn:
    tải/lock state đang cạnh tranh
    xác minh invariant trên state mới nhất
    thay đổi managed entities
    persist aggregate/outbox
    commit

Sau commit / workflow riêng:
    publish events
    call payment
    send notification
    reconcile/retry khi cần
```

Điều này không có nghĩa mọi validation đều phải ở ngoài transaction. **Validation phụ thuộc dữ liệu đang cạnh tranh** — ví dụ tồn kho còn đủ, quyền sở hữu hiện tại, hạn mức đang sử dụng — thường cần thực hiện trong transaction với mức bảo vệ concurrency phù hợp.

## 21. Đọc trước transaction có an toàn không?

Giả sử controller kiểm tra tồn kho trước:

```java
int available = inventoryRepository.findAvailable(productId);

if (available >= quantity) {
    orderService.placeOrder(...);
}
```

Giữa bước kiểm tra và lúc `placeOrder` lấy lock/ghi tồn kho, người khác có thể đặt hàng. Giá trị `available` vừa đọc đã **stale**.

Do đó:

- Kiểm tra sớm có thể hữu ích để phản hồi UX nhanh.
- Nhưng thao tác commit **phải kiểm tra lại invariant quan trọng trong transaction ghi**, với locking hoặc conditional update phù hợp.
- Không dựa vào kết quả đọc trước đó như một “vé đặt hàng” bảo đảm số lượng vẫn có.

Nguyên tắc này áp dụng cho kiểm tra username unique, số chỗ còn lại, hạn mức tín dụng, số người trong một nhóm và nhiều rule có cạnh tranh khác.

## 22. Tránh dùng entity detached như dữ liệu transaction tiếp nối

Một use case nhiều bước thường có nhiều service. Nếu service A trả một entity đã đóng persistence context rồi service B sử dụng nó để ghi, object có thể đã **detached**.

Ví dụ:

```java
PurchaseOrder order = orderQueryService.load(id);
// Query service đã đóng transaction/context riêng.

order.changeStatus("PAID");

// Không có bảo đảm Hibernate của service ghi đang theo dõi object này.
```

Giải pháp thường rõ nhất là truyền **ID/command**, rồi tải entity managed tại transaction của thao tác thay đổi:

```java
@Transactional
public void markPaid(UUID orderId) {
    PurchaseOrder managed = em.find(
        PurchaseOrder.class,
        orderId
    );

    if (managed == null) {
        throw new IllegalArgumentException("Order not found");
    }

    managed.markPaid();
}
```

Ví dụ giả định entity có method `markPaid()` thực thi state transition hợp lệ. Khi workflow chạy qua nhiều transaction, không nên coi cùng một Java entity object là unit of work xuyên các transaction.

Dùng `merge(detached)` có thể phù hợp trong một số trường hợp, nhưng nó sao chép **state của detached graph** và có thể ghi đè cập nhật mới nếu không có kiểm soát. Với command thay đổi ít trường, tải managed entity rồi gọi domain method thường an toàn và dễ đọc hơn.

## 23. Transaction context không tự truyền sang thread khác

Một transaction của Spring/Hibernate thông thường gắn với thread/context thực thi theo cơ chế tích hợp của framework. Nếu code:

```java
@Transactional
public void placeOrder(...) {
    em.persist(order);

    CompletableFuture.runAsync(() -> {
        // Không nên giả định đang ở cùng transaction hoặc EntityManager.
        updateInventory();
    });
}
```

thì task bất đồng bộ có thể chạy ở thread khác, không được tham gia transaction/persistence context của lời gọi ban đầu.

Ngoài ra, Hibernate `Session` và JPA `EntityManager` thông thường **không thread-safe**. Chia sẻ cùng Session giữa các thread là sai thiết kế.

Nếu một bước bắt buộc commit cùng thao tác đặt hàng, thực hiện nó **đồng bộ trong cùng unit of work** hoặc tái cấu trúc thành một thao tác DB phù hợp. Nếu bước đó có thể bất đồng bộ, tạo message/outbox và chấp nhận nó là **transaction riêng với trạng thái trung gian rõ ràng**.

### `@Async` và `@Transactional`

Việc đặt cả hai annotation lên cùng method hoặc gọi method async từ transaction hiện tại không tạo ra một database transaction chung xuyên thread một cách tự nhiên. Nếu một async worker có `@Transactional`, nó thường làm việc với **transaction riêng của worker**.

Phải xác định rõ **thời điểm message/event được phát sau commit** và cách retry/idempotency, thay vì chỉ thêm annotation để hy vọng tính nguyên tử.

## 24. Đừng giữ transaction xuyên vòng lặp xử lý rất lớn

Một batch job nhập 500.000 bản ghi có thể gồm nhiều bước cho mỗi item. Có hai cấp độ:

- **Transaction cho một item nghiệp vụ:** mỗi item có đủ các thay đổi cần cùng commit.
- **Transaction cho cả batch:** mọi item phải cùng commit hoặc rollback.

Không có lựa chọn đúng cho mọi bài toán. Nếu batch yêu cầu “hoặc toàn bộ 500.000 item thành công hoặc không có gì”, đó là yêu cầu atomicity rất mạnh và có thể khiến transaction dài, lock lâu, undo/WAL lớn và khó vận hành.

Nếu nghiệp vụ cho phép từng item hoặc từng chunk được xử lý độc lập, có thể dùng **chunk transactions**, ví dụ 100–1.000 item mỗi transaction, và lưu checkpoint/retry.

### Phân biệt chunk boundary với flush/clear

```java
for (int i = 0; i < items.size(); i++) {
    persistItem(items.get(i));

    if ((i + 1) % 50 == 0) {
        em.flush();
        em.clear();
    }
}
```

`flush()/clear()` **không tự tạo một transaction mới**. Nếu toàn bộ vòng lặp chạy trong một transaction, vẫn chỉ có một commit cuối cùng; rollback cuối có thể hủy các SQL đã flush trước đó.

Muốn commit từng chunk, cần transaction boundary thực sự cho từng chunk, được quản lý đúng bởi transaction manager. Đồng thời phải xác định semantics retry và tránh xử lý trùng.

## 25. Ảnh hưởng đến lazy loading và transaction ở tầng service

Khi repository trả entity có association lazy:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
```

Nếu controller/serializer cố đọc một association chưa initialized sau khi transaction/persistence context đóng, có thể gặp `LazyInitializationException`.

Giải pháp **không phải** kéo dài transaction ghi qua toàn bộ HTTP serialization chỉ để mọi getter hoạt động. Nên thiết kế query/fetch plan và trả DTO:

```java
@Transactional(readOnly = true)
public OrderView getOrder(UUID id) {
    PurchaseOrder order = em.find(PurchaseOrder.class, id);

    if (order == null) {
        throw new IllegalArgumentException("Order not found");
    }

    return new OrderView(
        order.getId(),
        order.getStatus()
    );
}
```

`OrderView` là DTO/record có constructor phù hợp; entity cần có getter tương ứng. Với view cần association, query nên chủ động fetch/projection dữ liệu sẽ dùng **trong phạm vi đọc phù hợp**.

Transaction boundary theo use case không có nghĩa phải trả **entity managed** ra mọi tầng của ứng dụng.

## 26. Read-only transaction không phải transaction tạo đơn

Spring hỗ trợ:

```java
@Transactional(readOnly = true)
public OrderView findOrder(UUID id) {
    // ...
}
```

Read-only có thể giúp framework/ORM tối ưu đường đọc, tùy cấu hình. Nhưng **không nên dùng `readOnly = true` cho workflow cần dirty checking và commit những thay đổi ghi**. Một số integration có thể đặt Hibernate flush mode để hạn chế flush, khiến setter trên managed entity không phát sinh UPDATE như mong đợi.

Ngược lại, `readOnly = true` không phải cơ chế bảo mật hoặc database constraint bảo đảm tuyệt đối không thể ghi trong mọi môi trường. Các quyền database vẫn cần cấu hình thích hợp khi yêu cầu thực sự là chặn write.

Với thao tác nhiều bước có ghi dữ liệu, dùng transaction ghi phù hợp và thể hiện rõ intent.

## 27. Timeout và việc quản lý transaction dài

Một transaction nhiều bước có thể thất bại vì:

- Chờ lock quá lâu.
- Query chậm.
- Deadlock.
- Transaction timeout.
- Connection interruption.
- Dữ liệu không còn thỏa optimistic lock.
- Constraint violation khi flush.
- Database restart/failover.

Có thể đặt timeout theo chính sách:

```java
@Transactional(timeout = 10)
public void placeOrder(...) {
    // ...
}
```

Cấu hình này có ý nghĩa qua transaction manager tương ứng; không bảo đảm ngắt được **mọi** external network call hoặc mọi lệnh đang chạy ở mọi driver sau đúng 10 giây.

Với operation chứa nhiều bước, timeout phải được xem là một **kết quả thất bại của toàn unit of work**, không phải tín hiệu “bỏ qua phần update tồn kho nhưng vẫn giữ đơn”.

Nếu retry:

- Chỉ retry khi lỗi thuộc loại có thể retry (ví dụ một số deadlock/serialization conflict hoặc trạng thái tạm thời).
- Retry **toàn bộ unit of work** trên transaction mới.
- Sử dụng idempotency key nếu request có thể đã commit nhưng response bị mất.
- Không retry vô hạn và không retry charge/payment không idempotent.
- Không tiếp tục tái sử dụng EntityManager sau khi transaction thất bại nghiêm trọng.

## 28. Đảm bảo invariants bằng database constraint

Transaction giúp các bước commit cùng nhau, nhưng dữ liệu vẫn cần **rào chắn ở mức schema**.

Ví dụ:

```sql
ALTER TABLE inventory_stock
    ADD CONSTRAINT ck_stock_non_negative
    CHECK (available_quantity >= 0);
```

Với idempotency:

```sql
ALTER TABLE purchase_orders
    ADD CONSTRAINT uq_order_request_key
    UNIQUE (request_key);
```

Đây là các ví dụ ràng buộc quan trọng, nhưng nếu schema đã có constraint tương đương thì không thêm trùng. Migration thực tế phải dựa vào trạng thái schema hiện hữu.

### Điều gì xảy ra nếu constraint bị vi phạm?

Hibernate có thể phát hiện ở **flush** hoặc commit, tùy thời điểm SQL/constraint được kiểm tra. Nếu vi phạm, exception thường khiến transaction cần rollback.

Code không nên làm:

```java
try {
    em.persist(order);
    em.flush();
} catch (PersistenceException ex) {
    // Sai: coi như chỉ insert order hỏng,
    // rồi tiếp tục commit phần inventory đã sửa.
}
```

Trừ khi đã thiết kế savepoint/transaction policy cụ thể, một transaction JPA gặp persistence exception có thể đã không còn trạng thái phù hợp để tiếp tục. Thông thường, rollback toàn unit of work là lựa chọn đúng.

### Validation ở Java và constraint ở DB bổ sung nhau

- Validation Java giúp trả lỗi nghiệp vụ sớm, có thông điệp rõ.
- Constraint DB giúp bảo vệ mọi writer, kể cả job/migration/service khác.
- Locking/isolation bảo vệ invariant có yếu tố concurrency.
- Transaction đảm bảo một tập thay đổi được commit/rollback như một nhóm.

Không thể dùng **chỉ một** trong bốn cơ chế để thay thế toàn bộ ba cơ chế còn lại.

## 29. Phạm vi nghiệp vụ nhiều bước không phải lúc nào cũng một transaction

Ví dụ onboarding người dùng:

1. Tạo tài khoản.
2. Gửi email xác minh.
3. Người dùng click link.
4. Kiểm tra mã OTP.
5. Kích hoạt tài khoản.

Không thể giữ một transaction database mở từ bước 1 cho đến lúc người dùng click email vài giờ sau. Workflow này cần **trạng thái trung gian và nhiều transaction**.

```text
T1: create User(status=PENDING_VERIFICATION) + outbox email
COMMIT

Email delivered (external)
User clicks link

T2: verify token, activate User, store audit/outbox
COMMIT
```

Mỗi transaction là **một đơn vị atomic cục bộ**, còn cả workflow được điều phối bằng trạng thái và sự kiện.

Nguyên tắc tổng quát:

- **Một tương tác nghiệp vụ ngắn, ghi vào cùng DB với invariant thống nhất:** thường dùng một transaction.
- **Workflow kéo dài qua thời gian, con người, service ngoài hoặc nhiều DB:** chia thành nhiều transaction và dùng cơ chế phối hợp được thiết kế rõ.

## 30. Testing transaction boundary: cần chứng minh điều gì?

Với use case nhiều bước, bài kiểm tra có giá trị nhất là kiểm tra **trạng thái database sau khi thao tác thành công hoặc thất bại**, không chỉ kiểm tra method repository được gọi bao nhiêu lần.

### 30.1. Thành công

Một integration test có thể xác nhận:

- Đơn hàng được lưu.
- Số lượng tồn kho giảm đúng mức.
- Outbox event được ghi.
- Request key được bảo vệ không tạo trùng.
- Trạng thái được commit khi transaction thành công.

### 30.2. Thất bại ở bước cuối

Ví dụ ép một ràng buộc unique của order gây lỗi sau khi đã sửa tồn kho:

```text
BEGIN
  update stock
  insert order -> UNIQUE violation
ROLLBACK

Kỳ vọng:
  stock không bị giảm so với dữ liệu đã commit trước đó
  order mới không xuất hiện
  outbox event mới không xuất hiện
```

Không chỉ kiểm tra exception; cần xác minh **không có partial commit**.

### 30.3. Cạnh tranh đồng thời

Chạy hai transaction cùng đặt số lượng vượt tổng tồn kho. Kỳ vọng chỉ những đơn phù hợp invariant được commit; transaction còn lại thất bại hoặc retry theo chính sách.

Nếu dùng optimistic locking, test cả phiên bản stale. Nếu dùng pessimistic locking, test lock timeout và thứ tự lock trên nhiều product.

### 30.4. Tác dụng phụ ngoài database

Với outbox, kiểm tra:

- Business commit → outbox row tồn tại.
- Business rollback → outbox row không tồn tại.
- Publisher crash/retry → cùng event ID có thể phát lại nhưng consumer xử lý idempotent.
- Payment fail → workflow có trạng thái lỗi và bù trừ phù hợp.

### 30.5. Cẩn thận với test có `@Transactional`

Trong Spring Test, một số integration tests có `@Transactional` được rollback tự động sau test. Nếu code under test tham gia transaction do test mở, bạn có thể **không thực sự kiểm chứng boundary commit production**.

Vì thế, khi kiểm tra commit/rollback của use case, phải thiết kế test transaction boundaries rõ ràng (ví dụ gọi service qua proxy trong transaction độc lập hoặc sử dụng phương án test transaction phù hợp). Không dựa vào một test tự rollback để kết luận việc commit production chính xác.

## 31. Các lỗi thường gặp khi đặt transaction boundary

| Lỗi thiết kế | Hậu quả có thể xảy ra | Hướng giải quyết |
|---|---|---|
| Mỗi repository save có transaction riêng | Đơn lưu nhưng tồn kho chưa cập nhật, hoặc ngược lại | Dùng application service quản lý cùng transaction |
| Gọi API thanh toán bên trong transaction DB | Giữ lock lâu; rollback DB không hoàn tiền | Outbox/saga, transaction cục bộ ngắn |
| Nuốt exception rồi return thành công | Transaction có thể commit phần thay đổi còn lại | Propagate lỗi hoặc đánh dấu rollback đúng policy |
| Dùng checked exception nhưng không có rollback rule phù hợp | Transaction có thể commit dù nghiệp vụ báo lỗi | Cấu hình rollbackFor/chính sách transaction |
| Dùng `REQUIRES_NEW` cho bước phải cùng rollback | Bước con commit độc lập trước khi outer fail | Dùng `REQUIRED` và cùng TM khi cần atomicity |
| Gọi `@Transactional` qua self-invocation | Transaction interceptor có thể không chạy | Gọi qua Spring bean/proxy thực sự |
| Chia sẻ `EntityManager` qua thread | Hành vi không an toàn, context không được truyền tự nhiên | Mỗi unit of work có context riêng |
| Cho rằng `flush` là commit | Phản hồi thành công quá sớm; hiểu sai rollback | Tách flush SQL và commit transaction |
| Không khóa/không kiểm soát cạnh tranh | Hai transaction cùng pass validation, phá invariant | Pessimistic/optimistic lock, atomic update, isolation |
| Chỉ dùng `SELECT` kiểm tra unique | Race khi hai request cùng insert | Unique constraint + idempotency handling |
| Retry transaction bằng cùng Session sau lỗi | Context/transaction có thể không còn nhất quán | Rollback, mở transaction/context mới |
| Kéo transaction xuyên quá nhiều xử lý chậm | Connection/lock contention, timeout | Chia phần ngoài DB, giữ transaction ngắn |
| Dùng `MANUAL` flush mode nhưng quên flush | Commit có thể không ghi pending updates | Để TM quản lý flush, hiểu rõ MANUAL |
| Bulk DML rồi dùng entity managed cũ | State stale dẫn tới quyết định sai | Flush/clear/refresh hoặc tách workflow |
| Gửi event trước DB commit | Downstream thấy sự kiện cho dữ liệu rollback | Ghi outbox trong cùng transaction |
| Không xử lý duplicate event | Consumer làm tác dụng phụ hai lần khi retry | Idempotent consumer/inbox |

## 32. Cách chọn ranh giới cho ba tình huống tiêu biểu

### A. Chuyển tiền giữa hai tài khoản cùng database

Các bước:

```text
BEGIN
  lock/load sender
  kiểm tra đủ số dư
  giảm sender.balance
  tăng receiver.balance
  ghi transfer record
COMMIT
```

Nếu một bước lỗi, rollback tất cả. Cần locking/isolation/constraint để bảo vệ số dư khi các giao dịch cạnh tranh. Với hai tài khoản, áp thứ tự lock nhất quán theo ID để giảm deadlock.

### B. Đặt hàng + thanh toán bên ngoài

```text
T1:
  reserve inventory
  create order PENDING_PAYMENT
  record outbox PaymentRequested
COMMIT

Payment worker:
  call provider with idempotency key

T2:
  record payment result
  update order status
COMMIT

Nếu fail:
  T3 release reservation / cancel order
```

Không thể thay toàn bộ chuỗi bằng một `@Transactional` ở OrderService và kỳ vọng SQL rollback tác động đến payment gateway.

### C. Sửa hồ sơ và ghi audit trong cùng database

Nếu yêu cầu là “audit row phải tồn tại chính xác khi thay đổi hồ sơ commit”:

```text
BEGIN
  update profile
  insert audit_row
COMMIT
```

Hai bước nên cùng transaction. Ngược lại, nếu cần ghi **attempted failed update** ngay cả khi profile update rollback, đó là một mục tiêu audit khác. Có thể cần transaction độc lập `REQUIRES_NEW` hoặc logging service riêng, và phải xác định rõ rằng audit của một **attempt** không phải audit của một **committed change**.

Không nên dùng một kiểu propagation cho cả hai ý nghĩa.

## 33. Quy trình thiết kế transaction cho một use case mới

Có thể áp dụng các bước sau để quyết định ranh giới đúng:

1. **Viết tên thao tác nghiệp vụ** bằng động từ rõ ràng: “Đặt đơn”, “Chuyển khoản”, “Duyệt yêu cầu”, “Hủy đặt chỗ”.
2. **Liệt kê các thay đổi dữ liệu** cần thiết: bảng, entity, aggregate, outbox record.
3. **Ghi các invariant sau commit:** những điều kiện nào nhất thiết phải đúng khi thao tác thành công?
4. **Phân loại tài nguyên:** cùng database/transaction manager hay nằm ở service/file/broker khác?
5. **Chọn phần atomic cục bộ:** gom những cập nhật cùng DB cần thành công cùng nhau vào một transaction.
6. **Đặt boundary tại use case/application service** hoặc handler tương ứng, để repository tham gia cùng transaction.
7. **Xác định thứ tự lock và cơ chế concurrency** cho dữ liệu có thể bị nhiều transaction sửa đồng thời.
8. **Xác định rollback policy:** runtime/checked exceptions, xử lý validation, timeout, retry.
9. **Tách tác dụng phụ bên ngoài:** outbox, event, saga/compensation khi cần.
10. **Thiết kế idempotency:** request trùng, response mất, message gửi lại, commit chưa biết kết quả.
11. **Giữ transaction ngắn:** không chờ mạng, người dùng hoặc xử lý nặng không cần thiết trong lúc giữ lock.
12. **Kiểm tra thành công và thất bại bằng trạng thái database:** không có partial commit; concurrency không phá invariant.
13. **Quan sát vận hành:** duration, lock wait, deadlock, rollback, connection pool usage và outbox backlog.

Mục tiêu không phải có càng nhiều `@Transactional` càng tốt; mục tiêu là **có đúng transaction boundary**.

## 34. Các câu hỏi tự kiểm tra

### Câu 1: Repository đều có transaction, có cần transaction ở service nữa không?

Nếu use case phải ghi ba entity trong **một nhóm nguyên tử**, thường **có**. Transaction riêng của từng repository không bảo đảm cả nhóm cùng commit. Một outer service transaction với propagation phù hợp giúp repository cùng tham gia unit of work.

### Câu 2: Một method `@Transactional` gọi ba repository thì luôn cùng một transaction?

Không tuyệt đối. Còn phụ thuộc lời gọi có đi qua proxy/interceptor không, propagation, transaction manager, datasource, thread và một số cấu hình khác. Phải hiểu **boundary thực thi**, không chỉ đếm annotation.

### Câu 3: Gọi `em.flush()` sau reserve rồi order insert lỗi, tồn kho có bị trừ vĩnh viễn?

Nếu cả hai thuộc **cùng một database transaction** và transaction rollback thành công, cập nhật tồn kho đã flush vẫn rollback. Flush không commit.

### Câu 4: Có thể dùng `REQUIRES_NEW` để “chắc chắn” reserve hàng được ghi không?

Điều đó làm reserve commit **độc lập**, có thể dẫn đến hàng bị giữ dù tạo đơn thất bại. Đây thường là điều **không mong muốn** cho một thao tác đặt đơn nguyên tử.

### Câu 5: `@Transactional` có đảm bảo hai người không đặt vượt tồn kho?

Không đủ. Cần một cơ chế phù hợp để giải quyết cạnh tranh, như pessimistic locking, optimistic locking với retry, atomic conditional update hoặc isolation/constraint.

### Câu 6: Gửi email sau khi service return có đáng tin cậy không?

Không hoàn toàn. Ứng dụng có thể crash giữa commit và gửi email; hoặc gửi email rồi lỗi/timeout. Với yêu cầu giao hàng sự kiện/thông báo đáng tin cậy, cân nhắc outbox và retry.

### Câu 7: Một thao tác có thể kéo dài nhiều giờ có phải một database transaction?

Thông thường không. Nó nên được mô hình hóa thành workflow nhiều state transition với nhiều local transactions và cơ chế bù trừ khi cần.

### Câu 8: Bắt exception trong transaction có luôn rollback?

Không. Nếu exception bị nuốt và transaction chưa được đánh dấu rollback-only, code có thể kết thúc bình thường và commit. Rollback policy phải được thiết kế rõ ràng.

### Câu 9: Chuyển tiền qua hai cơ sở dữ liệu khác nhau có thể chỉ dùng `@Transactional`?

Một annotation không tự tạo giao dịch ACID xuyên nhiều datasource độc lập. Cần resource coordination thích hợp (chẳng hạn JTA/XA khi thực sự hỗ trợ), hoặc một kiến trúc nhiều giao dịch có trạng thái và xử lý nhất quán theo thiết kế.

### Câu 10: Có cần gọi `save` sau khi sửa entity managed không?

Thông thường không nếu entity được quản lý bởi Hibernate trong transaction ghi phù hợp. Dirty checking và flush xử lý cập nhật. Cần chú ý mapping read-only/immutable và flush mode.

## 35. Ghi nhớ

- **Transaction boundary nên đi theo thao tác nghiệp vụ** mà các bước database phải cùng thành công, không mặc định theo từng câu SQL hoặc từng repository method.
- **Application service/use case** thường là nơi phù hợp để bắt đầu/kết thúc transaction vì nó biết toàn bộ invariant của thao tác.
- **Một transaction cùng database** cho phép các bước như giữ tồn kho, tạo đơn và ghi outbox row commit/rollback như một nhóm.
- **`@Transactional` không tự bảo đảm mọi lời gọi đều nằm trong transaction**: còn phụ thuộc proxy/self-invocation, propagation, thread và transaction manager.
- **`REQUIRED`** thường phù hợp khi method con phải tham gia transaction hiện có; **`REQUIRES_NEW`** tạo transaction độc lập và có thể phá tính nguyên tử mong muốn.
- Trong Spring, rollback mặc định thường áp dụng cho unchecked exceptions; checked exceptions có thể cần quy tắc rollback rõ ràng.
- **Flush khác commit**: SQL có thể được gửi xuống DB trước khi transaction kết thúc và vẫn rollback được.
- **Atomicity khác isolation**: transaction riêng lẻ không ngăn mọi race condition. Tồn kho, hạn mức, chuyển tiền và invariant nhiều hàng cần locking/constraint/chiến lược concurrency phù hợp.
- **Không giữ transaction database xuyên lời gọi mạng chậm** và không kỳ vọng rollback DB hoàn tác payment, email hoặc message đã gửi.
- **Outbox** gắn sự kiện với thay đổi đã commit; **saga/compensation** quản lý workflow nhiều giao dịch và external side effects.
- **Idempotency và retry** cần thiết khi client timeout, transaction có deadlock hoặc event được giao lại.
- **Transaction càng ngắn càng tốt nhưng phải đủ rộng để bảo vệ invariant**: không cắt nhỏ tùy tiện và không kéo dài qua toàn bộ workflow nhiều giờ.
- Kiểm tra bằng cả **success, failure và concurrency cases**, xác minh dữ liệu không ở trạng thái partial commit.

**Kết luận:** Hibernate đảm nhận ánh xạ và đồng bộ entity với database, nhưng **ứng dụng phải xác định đơn vị nghiệp vụ nào cần tính nguyên tử**. Một ranh giới giao dịch đặt đúng chỗ giúp giữ các thay đổi liên quan nhất quán khi thành công hoặc thất bại. Khi thao tác vượt ra ngoài một tài nguyên ACID, hãy phân tách thành các giao dịch cục bộ có trạng thái rõ ràng, phối hợp bằng outbox, idempotency và các bước bù trừ, thay vì cố kéo một transaction database vượt quá khả năng bảo đảm của nó.
