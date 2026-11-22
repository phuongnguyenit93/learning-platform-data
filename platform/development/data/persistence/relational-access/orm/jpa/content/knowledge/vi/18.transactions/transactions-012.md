# Thiết kế một giao dịch cho toàn bộ thay đổi nghiệp vụ liên quan

Một yêu cầu nghiệp vụ hiếm khi chỉ làm thay đổi đúng một hàng trong database. Khi khách hàng đặt hàng, hệ thống có thể phải tạo đơn, tạo các dòng hàng, giữ tồn kho, ghi trạng thái xử lý và lưu một sự kiện để các hệ thống khác biết đơn đã được tạo. Nếu chỉ một phần thành công, dữ liệu có thể mâu thuẫn: đơn hàng tồn tại nhưng tồn kho chưa được giữ, hoặc tồn kho đã giảm mà không có đơn tương ứng.

Trong JPA, **transaction là ranh giới nhất quán cho một đơn vị công việc nghiệp vụ**. Thay vì tạo transaction riêng cho từng lời gọi `save()`, ta thường đặt **một transaction ở tầng application service** bao trùm toàn bộ các thay đổi phải cùng thành công hoặc cùng thất bại.

Đây là nguyên tắc trung tâm:

> Những thay đổi trong **cùng một database transaction** mà nghiệp vụ coi là một hành động nguyên tử phải được thực hiện dưới **cùng một ranh giới commit/rollback**. Với email, HTTP API, message broker hoặc database độc lập, cần cơ chế phối hợp riêng; một transaction JPA thông thường không thể tự cam kết tất cả tài nguyên ấy.

Bài này hướng dẫn cách xác định ranh giới giao dịch dựa trên nghiệp vụ, tổ chức code JPA/Spring, xử lý lỗi, khóa cạnh tranh, kiểm chứng rollback và thiết kế tác động ngoài database.

---

## 1. Bài toán xuyên suốt: đặt hàng và giữ tồn kho

Giả sử khách hàng đặt hai sản phẩm:

- 2 cuốn sách `JAVA-101`.
- 1 cuốn sách `DB-201`.

Hệ thống cần:

1. Kiểm tra khách hàng đang hoạt động và sản phẩm được phép bán.
2. Kiểm tra tồn kho khả dụng cho **tất cả** dòng hàng.
3. Giảm/giữ tồn kho của từng sản phẩm.
4. Tạo `PurchaseOrder` và các `OrderLine`.
5. Ghi `OutboxEvent` thông báo “đơn đã được tạo”, để một worker phát đi sau commit.

Nghiệp vụ yêu cầu: **không có đơn hợp lệ nào chỉ được giữ một phần tồn kho**. Nếu sản phẩm thứ hai hết hàng, mọi thay đổi database của yêu cầu phải được hoàn tác.

Một transaction mong muốn:

~~~text
API: POST /orders
        |
        v
Application service: placeOrder(command)
        |
        +-- kiểm tra khách hàng
        +-- khóa/kiểm tra tồn kho JAVA-101
        +-- khóa/kiểm tra tồn kho DB-201
        +-- thay đổi tồn kho của cả hai
        +-- tạo PurchaseOrder và OrderLine
        +-- ghi outbox event
        |
        +-- nếu tất cả hợp lệ: COMMIT
        |
        +-- nếu có bất kỳ lỗi bắt buộc: ROLLBACK
        |
        v
Worker xử lý outbox sau khi commit
        |
        +-- gửi thông báo / gọi hệ thống ngoài
~~~

Điểm quan trọng: **gửi email hoặc gọi cổng thanh toán không nằm trong cùng tính nguyên tử của transaction database**. Ghi ý định phát thông báo vào outbox là một thay đổi của database và có thể commit cùng Order.

### 1.1. Trạng thái đúng và sai

Giả sử tồn kho ban đầu:

| Sản phẩm | Khả dụng trước yêu cầu | Số lượng đặt |
|---|---:|---:|
| JAVA-101 | 5 | 2 |
| DB-201 | 3 | 1 |

Khi thành công:

| Thành phần | Sau commit |
|---|---|
| `inventory(JAVA-101)` | Còn 3 |
| `inventory(DB-201)` | Còn 2 |
| `purchase_orders` | Có một đơn mới |
| `order_lines` | Có hai dòng đúng số lượng |
| `outbox_events` | Có sự kiện chờ xử lý |

Khi DB-201 chỉ còn 0 và nghiệp vụ không cho đặt thiếu:

| Thành phần | Sau rollback |
|---|---|
| `inventory(JAVA-101)` | Vẫn 5 |
| `inventory(DB-201)` | Vẫn 0 |
| `purchase_orders` | Không có đơn mới của yêu cầu |
| `order_lines` | Không có dòng mới của yêu cầu |
| `outbox_events` | Không có event mới của yêu cầu |

Nếu service tạo Order trong transaction A, rồi giữ JAVA-101 trong transaction B, tiếp tục giữ DB-201 trong transaction C, các phần đã commit trước đó **không tự rollback** khi bước sau gặp lỗi. Vì vậy ranh giới giao dịch phải xuất phát từ quy tắc **toàn bộ thay đổi nào cần cùng thành công**.

---

## 2. Transaction bảo vệ điều gì?

Các thuộc tính ACID thường dùng để giải thích transaction:

| Thuộc tính | Ý nghĩa cho ví dụ đặt hàng |
|---|---|
| **Atomicity** (tính nguyên tử) | Tạo đơn, cập nhật tồn kho và ghi outbox trong cùng giao dịch: commit tất cả hoặc rollback tất cả |
| **Consistency** (tính nhất quán) | Các constraint và business invariant phải được giữ trước/sau commit, ví dụ không được có số lượng tồn âm |
| **Isolation** (tính cô lập) | Hai request đặt cùng sản phẩm không được cùng dựa vào một thông tin tồn kho cũ để bán vượt số lượng |
| **Durability** (tính bền vững) | Sau commit thành công, dữ liệu phải được DBMS duy trì theo bảo đảm của hệ thống lưu trữ |

Không nên hiểu “có `@Transactional`” là mọi business invariant đều tự động đúng. Transaction cung cấp khung làm việc; ứng dụng vẫn cần:

- Ràng buộc database: `NOT NULL`, `UNIQUE`, FK, `CHECK`.
- Điều kiện nghiệp vụ: khách hàng hoạt động, sản phẩm được bán, số lượng hợp lệ.
- Cơ chế concurrency: optimistic lock, pessimistic lock hoặc atomic conditional SQL.
- Cách xử lý tác động ngoài database: outbox, idempotency, saga nếu cần.

### 2.1. Đơn vị kỹ thuật khác đơn vị nghiệp vụ

Có hai cách hiểu “một giao dịch”:

1. **Một câu SQL**: ví dụ cập nhật tồn kho một sản phẩm.
2. **Một hành động nghiệp vụ**: ví dụ tạo đơn gồm nhiều dòng, giảm tồn kho và ghi outbox.

Một hành động nghiệp vụ có thể cần **nhiều câu SQL**, nhưng chúng vẫn có thể thuộc cùng một database transaction.

Ngược lại, không nên kéo toàn bộ hành trình khách hàng từ lúc xem giỏ hàng đến khi giao hàng thành một transaction database kéo dài hàng giờ. Hành trình lớn cần chia thành các **bước nghiệp vụ có trạng thái**, mỗi bước có transaction ngắn và quy tắc chuyển trạng thái rõ ràng.

### 2.2. Tiêu chí nhận biết những thay đổi phải cùng transaction

Hỏi:

- Nếu thao tác thứ hai thất bại, thao tác đầu tiên có được phép tồn tại không?
- Nếu chỉ một số dòng cập nhật thành công, dữ liệu có hợp lệ không?
- Các thay đổi có dùng cùng database và transaction manager không?
- Điều kiện nào phải đúng tại thời điểm commit, dưới tải đồng thời?
- Có side effect nào không thể rollback theo database không?

Nếu nghiệp vụ yêu cầu “A và B phải cùng commit hoặc cùng rollback” **và A/B thuộc cùng database transaction resource**, đó là dấu hiệu rõ ràng cần một ranh giới transaction bao trùm.

---

## 3. JPA persistence context và transaction không phải một thứ

**Persistence context** theo dõi các managed entity và đồng bộ các thay đổi bằng dirty checking. **Transaction** quyết định các thay đổi database được commit hay rollback cùng nhau.

Ví dụ:

~~~java
entityManager.getTransaction().begin();

Inventory javaStock =
    entityManager.find(Inventory.class, "JAVA-101");

javaStock.reserve(2);

entityManager.persist(order);

entityManager.getTransaction().commit();
~~~

Ở đây:

- `javaStock` là managed entity trong context.
- `reserve(2)` thay đổi trạng thái Java của entity.
- `persist(order)` đưa Order mới vào persistence context.
- Provider có thể phát `UPDATE`/`INSERT` tại flush, hoặc sớm hơn tùy mapping.
- **Transaction commit thành công** mới xác nhận toàn bộ thay đổi database.

Có thể có nhiều managed entity trong một context; đó không đồng nghĩa mọi thay đổi của chúng tự được commit nếu transaction cuối cùng rollback.

### 3.1. persist(), flush() và commit()

| Thao tác | Vai trò | Có bảo đảm transaction đã commit? |
|---|---|---|
| `em.persist(entity)` | Đưa entity mới vào trạng thái managed, đăng ký lưu | Không |
| Sửa field của managed entity | Dirty checking ghi nhận thay đổi | Không |
| `em.remove(entity)` | Đánh dấu entity cần xóa | Không |
| `em.flush()` | Đồng bộ thao tác pending qua SQL | Không |
| `tx.commit()` | Hoàn tất transaction; flush nếu cần | Có nếu thành công |
| `tx.rollback()` | Hoàn tác thay đổi database chưa commit | Không |

Một ví dụ dễ nhầm:

~~~java
tx.begin();

Order order = createOrder();
em.persist(order);

em.flush(); // Có thể đã gửi INSERT.

if (somethingFailed) {
    tx.rollback(); // INSERT đó không được commit.
}
~~~

Flush không “cố định” một nửa công việc. Nếu transaction rollback, các SQL đã flush cũng bị rollback theo bảo đảm transaction của DB.

### 3.2. ID được cấp chưa có nghĩa dữ liệu đã tồn tại bền vững

Với SEQUENCE, ID có thể được cấp trước INSERT. Với IDENTITY, Hibernate có thể INSERT sớm để nhận ID. Cả hai không thay đổi kết luận: **ID khác null và SQL đã chạy không chứng minh commit thành công**.

Không phát sự kiện “đã đặt hàng thành công” ra bên ngoài chỉ dựa vào `order.getId() != null`.

---

## 4. Xác định transaction boundary ở tầng application service

Kiến trúc phổ biến:

~~~text
Controller
    |
    v
Application Service
    |  @Transactional
    +--> Domain validation
    +--> EntityManager / Repository
    +--> Entity business methods
    +--> Outbox persistence
    |
    v
Commit/rollback
    |
    v
Controller trả kết quả
~~~

Service nghiệp vụ là nơi biết một use case cần thay đổi những entity nào. Một repository đơn lẻ thường chỉ biết truy cập một tập dữ liệu, không biết toàn bộ điều kiện “đặt hàng hợp lệ”.

Vì vậy transaction boundary thường nằm ở **public application service method** đại diện cho một hành động có nghĩa như:

- `placeOrder(...)`.
- `transferMoney(...)` trong cùng một sổ cái/database.
- `approveRequest(...)` cập nhật trạng thái và tạo lịch sử duyệt.
- `assignEmployeeToProject(...)` cập nhật phân công và chỉ tiêu liên quan.
- `reserveStock(...)` cho một đơn hàng.

Không nên đặt mỗi lời gọi repository trong một transaction riêng chỉ vì đó là một thao tác ghi.

### 4.1. Ví dụ sai: nhiều commit cho một yêu cầu

~~~java
public void placeOrder(Command command) {
    orderService.createOrder(command);       // Commit transaction A.
    inventoryService.reserve(command);      // Commit transaction B.
    notificationService.recordEvent(command);// Commit transaction C.
}
~~~

Nếu transaction B hoặc C thất bại, những transaction đã commit không tự bị hoàn tác. Mô hình này chỉ phù hợp nếu nghiệp vụ chấp nhận **nhiều bước độc lập** và có quy trình phục hồi/compensation cụ thể.

### 4.2. Ví dụ đúng với cùng database transaction

~~~java
@Transactional
public UUID placeOrder(PlaceOrderCommand command) {
    // Kiểm tra khách hàng.
    // Giữ tồn kho.
    // Tạo order và lines.
    // Ghi outbox event.
    // Nếu có lỗi bắt buộc: throw exception để rollback.
    return orderId;
}
~~~

Khi dùng Spring transaction manager cho cùng `EntityManagerFactory`/datasource, các repository và EntityManager tham gia transaction hiện tại theo cấu hình thường gặp. Chỉ khi **method transaction kết thúc và commit thành công**, lời gọi của controller mới được coi là hoàn thành.

Quan trọng: annotation không thay khả năng kỹ thuật của database. Nếu các service ghi qua các database/transaction manager độc lập, một `@Transactional` đơn giản không tự tạo atomicity xuyên hệ thống.

---

## 5. Thiết kế một mô hình nhất quán cho việc đặt hàng

Để giữ ví dụ rõ ràng, ta dùng bốn phần dữ liệu:

1. `Customer`: khách hàng đang hoạt động.
2. `Inventory`: tồn kho theo SKU.
3. `PurchaseOrder` và `OrderLine`: đơn hàng và các dòng.
4. `OutboxEvent`: sự kiện chờ worker phát đi sau commit.

Trong ví dụ này, các lớp nằm cùng persistence unit và các bảng thuộc cùng **một cơ sở dữ liệu transactional**.

### 5.1. Ràng buộc database cơ bản

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    active BOOLEAN NOT NULL
);

CREATE TABLE inventory (
    sku VARCHAR(40) PRIMARY KEY,
    available BIGINT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_inventory_available
        CHECK (available >= 0)
);

CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    request_id VARCHAR(120) NOT NULL,
    customer_id BIGINT NOT NULL
        REFERENCES customers(id),
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_purchase_orders_request UNIQUE (request_id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id UUID NOT NULL
        REFERENCES purchase_orders(id),
    sku VARCHAR(40) NOT NULL,
    quantity BIGINT NOT NULL CHECK (quantity > 0)
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    event_type VARCHAR(80) NOT NULL,
    aggregate_id UUID NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE
);
~~~

Ràng buộc `UNIQUE(request_id)` là cơ sở cho **idempotency**: một yêu cầu nghiệp vụ được nhận diện bằng mã request duy nhất, tránh tạo hai đơn do retry.

`CHECK (available >= 0)` là tuyến phòng thủ dữ liệu, nhưng bản thân nó không thay thế chiến lược locking hay atomic decrement phù hợp.

Tùy nghiệp vụ, có thể cần ràng buộc bổ sung như không cho trùng SKU trong một Order, giới hạn trạng thái hợp lệ, index cho truy vấn outbox và audit. Ví dụ chỉ tập trung vào transaction boundary.

### 5.2. Entity Inventory và business method

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "inventory")
public class Inventory {

    @Id
    @Column(length = 40)
    private String sku;

    @Column(nullable = false)
    private long available;

    @Version
    private long version;

    protected Inventory() {}

    public String getSku() {
        return sku;
    }

    public long getAvailable() {
        return available;
    }

    public void reserve(long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Số lượng phải lớn hơn 0"
            );
        }

        if (available < quantity) {
            throw new InsufficientStockException(sku);
        }

        available -= quantity;
    }
}
~~~

Exception nghiệp vụ:

~~~java
public class InsufficientStockException
        extends RuntimeException {

    public InsufficientStockException(String sku) {
        super("Không đủ tồn kho cho SKU: " + sku);
    }
}
~~~

Lệnh `reserve()` thay đổi một entity managed. **Không cần `save(inventory)` sau mỗi lần giảm số lượng** nếu nó được tải trong cùng persistence context đang hoạt động. Hibernate sẽ đồng bộ qua dirty checking.

Bản thân đoạn code `if (available < quantity) ...` chưa đủ chống race giữa hai transaction. Chúng ta sẽ dùng khóa trong service và xem các lựa chọn khác ở mục concurrency.

### 5.3. Entity Order và OrderLine

Để không phụ thuộc vào thời điểm database sinh ID, ví dụ dùng UUID **do ứng dụng tự cấp** làm khóa chính Order:

~~~java
import jakarta.persistence.*;
import java.time.Instant;
import java.util.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private UUID id;

    @Column(name = "request_id", nullable = false, unique = true)
    private String requestId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(nullable = false, length = 30)
    private String status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(
        UUID id,
        String requestId,
        Customer customer,
        Instant createdAt
    ) {
        this.id = Objects.requireNonNull(id);
        this.requestId = Objects.requireNonNull(requestId);
        this.customer = Objects.requireNonNull(customer);
        this.createdAt = Objects.requireNonNull(createdAt);
        this.status = "PLACED";
    }

    public void addLine(String sku, long quantity) {
        OrderLine line = new OrderLine(this, sku, quantity);
        lines.add(line);
    }

    public UUID getId() {
        return id;
    }
}
~~~

Dòng hàng:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false, length = 40)
    private String sku;

    @Column(nullable = false)
    private long quantity;

    protected OrderLine() {}

    public OrderLine(
        PurchaseOrder order,
        String sku,
        long quantity
    ) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Số lượng phải dương"
            );
        }

        this.order = order;
        this.sku = java.util.Objects.requireNonNull(sku);
        this.quantity = quantity;
    }
}
~~~

`cascade = PERSIST` từ Order sang OrderLine phù hợp vì các dòng hàng được tạo như thành phần của Order. Nó khác với cascade `REMOVE` sang một sản phẩm danh mục dùng chung — một việc có thể xóa nhầm dữ liệu của các đơn khác.

Không bắt buộc phải dùng UUID trong mọi hệ thống. Nếu Order dùng IDENTITY/SEQUENCE, cách nhận ID và lịch INSERT có thể khác, nhưng nguyên tắc **cùng transaction** không thay đổi.

### 5.4. Entity OutboxEvent

~~~java
import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "outbox_events")
public class OutboxEvent {

    @Id
    private UUID id;

    @Column(name = "event_type", nullable = false, length = 80)
    private String eventType;

    @Column(name = "aggregate_id", nullable = false)
    private UUID aggregateId;

    @Column(nullable = false, columnDefinition = "text")
    private String payload;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "published_at")
    private Instant publishedAt;

    protected OutboxEvent() {}

    public static OutboxEvent orderPlaced(
        UUID orderId,
        Instant now
    ) {
        OutboxEvent e = new OutboxEvent();
        e.id = UUID.randomUUID();
        e.eventType = "ORDER_PLACED";
        e.aggregateId = orderId;
        e.payload = "{\"orderId\":\"" + orderId + "\"}";
        e.createdAt = now;
        return e;
    }
}
~~~

Payload JSON ở ví dụ rất nhỏ và an toàn do chỉ chứa UUID định dạng chuẩn. Khi hệ thống có payload phức tạp, dùng serializer JSON được cấu hình rõ, version schema event và không nối chuỗi tùy tiện từ dữ liệu người dùng.

---

## 6. Cài đặt use case trong một Spring @Transactional

Giả sử `Customer` là JPA entity có khóa `Long id`, method `isActive()`, và các lớp ở trên cùng persistence unit.

Command:

~~~java
import java.util.List;

public record OrderItemRequest(
    String sku,
    long quantity
) {}

public record PlaceOrderCommand(
    String requestId,
    Long customerId,
    List<OrderItemRequest> items
) {}
~~~

Service:

~~~java
import jakarta.persistence.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;
import java.time.Instant;
import java.util.*;

@Service
public class PlaceOrderService {

    @PersistenceContext
    private EntityManager em;

    private final Clock clock;

    public PlaceOrderService(Clock clock) {
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        validateCommand(command);

        Customer customer = em.find(
            Customer.class,
            command.customerId()
        );

        if (customer == null || !customer.isActive()) {
            throw new IllegalStateException(
                "Khách hàng không hợp lệ"
            );
        }

        // Khóa theo thứ tự nhất quán để giảm nguy cơ deadlock.
        List<OrderItemRequest> sortedItems =
            command.items().stream()
                .sorted(Comparator.comparing(
                    OrderItemRequest::sku
                ))
                .toList();

        // Tất cả Inventory đều đang managed trong cùng transaction.
        for (OrderItemRequest item : sortedItems) {
            Inventory inventory = em.find(
                Inventory.class,
                item.sku(),
                LockModeType.PESSIMISTIC_WRITE
            );

            if (inventory == null) {
                throw new IllegalArgumentException(
                    "Không tìm thấy SKU: " + item.sku()
                );
            }

            inventory.reserve(item.quantity());
        }

        Instant now = clock.instant();

        PurchaseOrder order = new PurchaseOrder(
            UUID.randomUUID(),
            command.requestId(),
            customer,
            now
        );

        for (OrderItemRequest item : sortedItems) {
            order.addLine(item.sku(), item.quantity());
        }

        // Cascade PERSIST lưu các OrderLine.
        em.persist(order);

        // Event được ghi trong CÙNG transaction với Order/Inventory.
        em.persist(OutboxEvent.orderPlaced(
            order.getId(), now
        ));

        return order.getId();
        // Spring sẽ commit khi method thoát qua transaction proxy.
    }

    private void validateCommand(PlaceOrderCommand c) {
        if (c == null || c.customerId() == null
                || c.requestId() == null
                || c.requestId().isBlank()
                || c.items() == null
                || c.items().isEmpty()) {
            throw new IllegalArgumentException(
                "Yêu cầu đặt hàng thiếu thông tin"
            );
        }

        Set<String> skuSet = new HashSet<>();

        for (OrderItemRequest item : c.items()) {
            if (item == null
                    || item.sku() == null
                    || item.sku().isBlank()
                    || item.quantity() <= 0) {
                throw new IllegalArgumentException(
                    "Dòng hàng không hợp lệ"
                );
            }

            if (!skuSet.add(item.sku())) {
                throw new IllegalArgumentException(
                    "SKU bị lặp trong một yêu cầu"
                );
            }
        }
    }
}
~~~

Ví dụ chọn chính sách **mỗi SKU xuất hiện một lần** trong command, nên không phải cộng gộp số lượng. Một thiết kế khác có thể normalize nhiều dòng cùng SKU thành một dòng với kiểm tra tràn số.

### 6.1. Vì sao đây là một transaction đúng nghĩa?

Trong cấu hình Spring JPA thông thường, method `placeOrder()` được gọi thông qua Spring proxy sẽ:

1. Bắt đầu hoặc tham gia transaction theo `Propagation.REQUIRED`.
2. Sử dụng persistence context/EntityManager gắn với transaction.
3. Giữ khóa pessimistic trên các hàng Inventory trong transaction.
4. Thay đổi tồn kho qua managed entities.
5. Persist Order, OrderLine và OutboxEvent.
6. Flush các SQL cần thiết, kiểm tra constraint database.
7. Commit nếu không có lỗi buộc rollback.
8. Rollback nếu có RuntimeException chưa được xử lý phù hợp, lỗi flush/constraint hoặc transaction bị đánh dấu rollback-only.

Không cần gọi `save()` trên Inventory sau `reserve()` vì nó đã managed. Không cần mở một transaction mới cho OutboxEvent. **Tất cả thay đổi cùng thành công hoặc cùng thất bại trong một DB transaction.**

### 6.2. Nếu sản phẩm thứ hai hết hàng?

Giả sử JAVA-101 còn 5, DB-201 còn 0. Service có thể:

- Tải/khóa JAVA-101.
- Giảm Java inventory từ 5 xuống 3 ở managed entity.
- Tải/khóa DB-201.
- `reserve(1)` ném `InsufficientStockException`.

Exception đi ra khỏi method `@Transactional` theo mặc định rollback của Spring đối với RuntimeException. Thay đổi Inventory JAVA-101 chưa commit sẽ bị rollback; Order và OutboxEvent sẽ không được tạo/commit trong đường code này.

Ngay cả nếu SQL UPDATE của JAVA-101 đã được flush vì provider cần thiết, rollback DB vẫn hoàn tác UPDATE đó.

### 6.3. Tại sao cần unique requestId?

Nếu client gửi cùng request hai lần, cả hai đều có thể tạo Order mới dù từng transaction đơn lẻ đều atomic. Transaction không tự giải quyết **idempotency ở cấp yêu cầu**.

`UNIQUE(request_id)` chặn hai Order có cùng requestId ở database. Khi request trùng gây constraint violation, transaction lỗi cần được rollback; ứng dụng có thể đọc lại Order đã commit theo requestId trong **transaction/context mới** rồi trả kết quả tương ứng, sau khi xác minh payload/request thuộc cùng người dùng và cùng nội dung.

Không bắt `ConstraintViolationException` rồi cố tiếp tục ghi và commit trong transaction đã lỗi.

---

## 7. Transaction boundary không có nghĩa gom mọi thứ vào một method khổng lồ

Một use case có thể gọi nhiều component:

~~~java
@Transactional
public UUID placeOrder(Command command) {
    Customer customer = customerPolicy.requireActive(command);
    reservationService.reserve(command);
    PurchaseOrder order = orderFactory.create(command, customer);
    orderRepository.persist(order);
    outboxRepository.append(OrderPlaced.from(order));
    return order.getId();
}
~~~

Các collaborator có thể là service/domain object/repository riêng, miễn chúng:

- Sử dụng cùng DB transaction resource theo cấu hình.
- Không tự mở giao dịch độc lập trái ý định.
- Không nuốt exception khiến lỗi nghiệp vụ mất tín hiệu rollback.
- Không thực hiện side effect ngoài DB trước khi transaction được xác nhận, trừ khi có quy trình khôi phục rõ ràng.

Phân chia code theo trách nhiệm giúp dễ đọc, test và thay đổi domain. **Ranh giới transaction nằm ở use case; ranh giới class/method là vấn đề tổ chức mã**.

### 7.1. Đặt transaction ở đâu?

| Vị trí | Ưu điểm | Hạn chế |
|---|---|---|
| Controller | Dễ nhìn endpoint | Gắn transaction với HTTP/serialization, dễ kéo dài transaction và trộn tầng |
| Repository từng thao tác | Từng thao tác dễ quản lý | Không bao trùm invariant xuyên nhiều repository |
| **Application service use case** | Bao trùm toàn bộ thay đổi cần atomic; biểu đạt nghiệp vụ | Cần xác định propagation và dependencies rõ |
| Entity/domain method | Logic quy tắc nghiệp vụ tập trung | Entity thường không sở hữu transaction manager; không nên tự mở DB transaction |
| Event listener bất kỳ | Có thể tách chức năng | Dễ rơi ra ngoài transaction hoặc thành side effect không rollback |

Trong ứng dụng Spring/JPA thông thường, **application service** là lựa chọn mặc định hữu ích nhất. Không phải quy tắc tuyệt đối cho mọi kiến trúc, nhưng dễ giữ tính nhất quán.

---

## 8. @Transactional: rollback mặc định và exception

Trong Spring, `@Transactional` thường rollback khi:

- Một `RuntimeException` không bị xử lý thoát ra khỏi phạm vi transaction.
- Một `Error` làm phương thức thất bại.
- Transaction manager/provider đánh dấu transaction rollback-only, ví dụ lỗi persistence.

**Checked exception không mặc định được cấu hình rollback giống RuntimeException** trong nhiều cấu hình Spring truyền thống.

Ví dụ:

~~~java
@Transactional
public void process() throws BusinessCheckedException {
    updateInventory();
    throw new BusinessCheckedException("Thất bại nghiệp vụ");
}
~~~

Nếu `BusinessCheckedException` là checked exception, không nên mặc định rằng Spring sẽ rollback theo chính sách chuẩn của mọi phiên bản/cấu hình. Có thể khai báo:

~~~java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void process() throws BusinessCheckedException {
    updateInventory();
    throw new BusinessCheckedException("Thất bại nghiệp vụ");
}
~~~

Hoặc dùng `rollbackFor = Exception.class` nếu đó là chủ đích của tầng service.

Đừng cấu hình rollback chung cho mọi exception mà không đánh giá: có những trường hợp lỗi đọc dữ liệu ngoài hoặc tín hiệu không nghiêm trọng vẫn cho phép công việc commit, nhưng cần thiết kế có chủ ý.

### 8.1. Nuốt exception có thể dẫn đến commit ngoài mong muốn

Ví dụ nguy hiểm:

~~~java
@Transactional
public void placeOrder(Command c) {
    reserveStock(c);

    try {
        persistOrder(c);
    } catch (RuntimeException ex) {
        log.warn("Không tạo được đơn", ex);
    }

    // Method kết thúc bình thường:
    // Spring có thể cố commit phần thay đổi trước đó.
}
~~~

Nếu exception bị bắt và không thoát ra, transaction interceptor có thể không nhận được tín hiệu rollback. Tuy nhiên một lỗi JPA có thể đã đánh dấu transaction rollback-only, dẫn tới `UnexpectedRollbackException` khi commit. **Không được dựa vào một trong hai hành vi như chính sách nhất quán.**

Khi lỗi làm toàn bộ use case không thể hợp lệ, nên:

- Ném exception để transaction rollback; hoặc
- Nếu cần bắt lỗi để bổ sung ngữ cảnh, rethrow một exception phù hợp; hoặc
- Đánh dấu rollback-only bằng transaction API khi có lý do rõ ràng và hiểu hệ quả.

Ví dụ bọc lỗi:

~~~java
@Transactional
public void placeOrder(Command c) {
    try {
        reserveStock(c);
        persistOrder(c);
    } catch (PersistenceException ex) {
        throw new OrderCreationException(
            "Không thể tạo đơn hàng", ex
        );
    }
}
~~~

`OrderCreationException` nên là RuntimeException nếu muốn tuân theo rollback mặc định. Không bắt lỗi DB rồi dùng cùng EntityManager đã hỏng để tiếp tục như thể không có lỗi.

### 8.2. Exception ở commit xảy ra sau dòng return

Method `@Transactional` có thể chạy đến `return orderId` mà không có exception trong thân method, nhưng flush/constraint failure phát sinh **lúc transaction interceptor commit sau đó**.

Vì vậy nếu controller đã gọi method qua proxy và nhận được kết quả bình thường, commit đã được xử lý theo lời gọi đó; còn nếu commit thất bại, exception sẽ được truyền qua lời gọi service.

Không phát thông báo thành công từ bên trong method chỉ vì đã tới dòng cuối. Với hành động ngoài DB, dùng outbox hoặc cơ chế sau commit thích hợp.

---

## 9. Propagation: REQUIRED, REQUIRES_NEW và nguy cơ tách transaction

Spring định nghĩa propagation để quyết định method nên tham gia transaction nào.

### 9.1. REQUIRED — thường là lựa chọn đúng

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void reserveInventory(...) {
    // ...
}
~~~

`REQUIRED` là mặc định của `@Transactional`. Nếu caller đã có transaction, method tham gia transaction đó; nếu chưa có, nó tạo transaction mới.

Use case:

~~~text
PlaceOrderService.placeOrder() [T1]
    |
    +-- reserveInventory() [tham gia T1]
    +-- saveOrder()        [tham gia T1]
    +-- appendOutbox()     [tham gia T1]
    |
    +-- COMMIT T1 hoặc ROLLBACK T1
~~~

Đây là cấu trúc giúp toàn bộ thay đổi DB của use case có một ranh giới commit.

### 9.2. REQUIRES_NEW — tách thành transaction độc lập

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordSomething(...) {
    // ...
}
~~~

Khi method thật sự được gọi qua transaction proxy, Spring tạm đình chỉ transaction hiện tại và bắt đầu một transaction mới (nếu transaction manager hỗ trợ).

~~~text
placeOrder [T1]
   |
   +-- recordSomething [T2 - REQUIRES_NEW]
   |      |
   |      +-- COMMIT T2
   |
   +-- lỗi xảy ra
   +-- ROLLBACK T1

Kết quả: T2 có thể đã commit dù T1 rollback.
~~~

Điều này **phá tính nguyên tử chung** nếu thao tác bên trong T2 là phần bắt buộc của Order. Ví dụ ghi Outbox bằng `REQUIRES_NEW` có thể khiến event đã commit nhưng Order lại rollback — người nhận sự kiện tìm không thấy Order.

REQUIRES_NEW hữu ích khi nghiệp vụ **cố tình cần một bản ghi độc lập**, chẳng hạn audit “đã cố gắng đăng nhập” phải được lưu dù giao dịch đăng nhập thất bại. Nhưng phải nhìn nhận rõ đó là **hai transaction với kết quả độc lập**.

### 9.3. NESTED và savepoint

`Propagation.NESTED` có thể ánh xạ tới savepoint của transaction hiện tại trong những transaction manager/resource phù hợp. Nhưng hỗ trợ NESTED không đồng nhất trên mọi JPA transaction manager và mọi phối hợp JDBC/JPA.

Không dùng NESTED như một cách mặc định chia một use case thành các bước có thể rollback riêng, nhất là khi phải đồng bộ persistence context JPA và JDBC savepoint. Nếu thật sự cần savepoint, phải xác minh transaction manager, driver, flush/clear và semantics của provider.

### 9.4. Self-invocation làm @Transactional không được áp dụng

Ví dụ:

~~~java
@Service
public class OrderService {

    public void endpointEntry(Command c) {
        createTransactionally(c); // Gọi trực tiếp cùng instance.
    }

    @Transactional
    public void createTransactionally(Command c) {
        // ...
    }
}
~~~

Trong cấu hình Spring AOP proxy thông thường, lời gọi từ một method đến method khác **cùng instance** không đi qua proxy. Vì vậy annotation của method bị gọi có thể không được áp dụng như dự kiến.

Đặt transaction ở public method được gọi từ bean khác qua Spring proxy, hoặc tổ chức service theo cấu trúc phù hợp với transaction manager. Đừng dựa vào `@Transactional` trên `private` method hoặc gọi nội bộ trong mô hình proxy mặc định.

---

## 10. Concurrency: một transaction không tự chống overselling

Giả sử Inventory chỉ còn 1 sản phẩm. Hai request đặt mỗi request 1 sản phẩm:

~~~text
Transaction A                      Transaction B
----------------------------------------------------------
Đọc available = 1
                                   Đọc available = 1
Kiểm tra đủ
                                   Kiểm tra đủ
Giảm về 0
                                   Giảm về 0
COMMIT
                                   COMMIT
~~~

Nếu thiếu locking/version/atomic update thích hợp, hai Order có thể cùng được tạo dù kho chỉ còn 1. Đây là nguy cơ **lost update hoặc overselling** tùy cách ORM thực hiện SQL và isolation.

**Atomicity** bảo đảm từng transaction commit trọn vẹn. **Isolation và concurrency control** cần được thiết kế để nhiều transaction không cùng phá business invariant.

### 10.1. Cách A: PESSIMISTIC_WRITE trong transaction

Đây là cách dùng ở service mẫu:

~~~java
Inventory inventory = em.find(
    Inventory.class,
    sku,
    LockModeType.PESSIMISTIC_WRITE
);

if (inventory == null) {
    throw new IllegalArgumentException("SKU không tồn tại");
}

inventory.reserve(quantity);
~~~

Một DBMS có hỗ trợ pessimistic row locking sẽ phối hợp khóa với transaction. Request thứ hai có thể phải chờ request thứ nhất commit/rollback rồi mới tiếp tục với trạng thái theo chính sách khóa và isolation của DB.

Những điểm cần chú ý:

- Thường cần transaction đang hoạt động.
- Lock có thể gây chờ, timeout hoặc deadlock.
- Không phải mọi dialect có cùng SQL/semantics.
- Khóa nhiều SKU theo thứ tự ổn định (ví dụ tăng dần theo SKU) có thể giảm nguy cơ deadlock nhưng không loại bỏ hoàn toàn.
- Giữ transaction ngắn; tránh chờ HTTP API ngoài hoặc thao tác nặng trong lúc đang giữ khóa.

### 10.2. Cách B: optimistic locking với @Version

Entity Inventory có:

~~~java
@Version
private long version;
~~~

Khi hai transaction cùng tải một version, cập nhật của transaction commit sau có thể gặp `OptimisticLockException` nếu phiên bản đã thay đổi.

Luồng:

~~~text
A đọc available=1, version=7
B đọc available=1, version=7

A cập nhật available=0, version=8 -> COMMIT
B cố cập nhật dựa trên version=7
    -> optimistic conflict -> ROLLBACK
~~~

Không nên chỉ thêm `@Version` rồi bỏ qua handling. Service cần xác định có retry hay thông báo hết hàng/đã thay đổi. Khi retry, phải **đọc lại tồn kho và kiểm tra toàn bộ điều kiện trong transaction mới**.

Optimistic locking hữu ích khi xung đột hiếm và không muốn giữ row lock lâu. Pessimistic locking có thể phù hợp khi contention cao và cần serialize thao tác trên từng SKU.

### 10.3. Cách C: UPDATE có điều kiện nguyên tử

Một cách khác là để database kiểm tra và giảm tồn trong **một câu SQL**:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE sku = :sku
  AND available >= :quantity;
~~~

Nếu affected row count bằng 1, thao tác giữ tồn thành công. Nếu bằng 0, SKU không tồn tại hoặc không đủ hàng (cần query/logic nếu muốn phân biệt).

Ưu điểm:

- Database thực hiện kiểm tra và giảm tồn như một thao tác nguyên tử.
- Có thể giảm nhu cầu load entity và khóa thủ công.
- Dễ tổ chức các thao tác nhỏ với điều kiện cạnh tranh rõ ràng.

Nhưng cần đặc biệt lưu ý:

- JPQL bulk UPDATE hoặc native SQL **không đồng bộ tự động trạng thái các entity Inventory đã managed trong persistence context**.
- Nếu có `@Version`, bulk DML không tự áp dụng cùng versioning semantics của một managed entity update, trừ khi câu lệnh được thiết kế để xử lý.
- Nên kiểm tra row count và thực hiện trong cùng transaction với Order/Outbox.
- Cần kiểm soát flush/clear/refresh nếu cùng context đã tải Inventory trước đó.
- Dù mỗi UPDATE là nguyên tử, giữ nhiều SKU vẫn cần một **transaction bao trùm** để rollback mọi SKU nếu một SKU thất bại.

### 10.4. UNIQUE constraint và idempotency cũng là concurrency control

Hai request có cùng `requestId` có thể cùng vượt qua một kiểm tra trước đó:

~~~java
if (!repository.existsByRequestId(requestId)) {
    // Cả hai request đều có thể đi đến đây.
}
~~~

Chỉ `UNIQUE(request_id)` ở database mới cưỡng chế tính duy nhất trong điều kiện cạnh tranh. Kiểm tra tồn tại trước INSERT chỉ là tối ưu hoặc bước trả thông báo, không thay thế constraint.

Khi gặp unique conflict, transaction cần rollback. Để trả kết quả cho request retry, tra cứu bản ghi đã commit trong transaction mới, xác minh cùng người dùng/payload và trả ID tương ứng.

---

## 11. Có nên mở transaction trước khi gọi cổng thanh toán?

Không nên mặc định mở một transaction JPA, khóa Inventory rồi gọi một HTTP payment API có thể chậm hàng giây hoặc timeout.

Tình huống xấu:

~~~text
BEGIN DB TRANSACTION
  -> khóa tồn kho
  -> tạo Order
  -> gọi payment provider qua HTTP
       ... chờ 10 giây / timeout ...
  -> COMMIT hoặc ROLLBACK
~~~

Vấn đề:

- Giữ connection, lock và tài nguyên DB trong thời gian chờ mạng.
- Timeout mạng không cho biết chắc payment provider **đã xử lý tiền hay chưa**.
- Database rollback không thể hoàn tác một giao dịch đã được cổng thanh toán thực thi.
- Có thể tăng deadlock/lock wait và làm giảm throughput.
- Retry mù quáng có thể tạo thanh toán trùng.

**Một transaction JPA chỉ bao trùm các tài nguyên được transaction manager điều phối.** Một HTTP request, email hay broker publish thông thường không tham gia cùng atomic DB commit.

### 11.1. Phân tách thành các bước nghiệp vụ

Một cách thiết kế:

~~~text
Bước 1 — DB transaction ngắn
  Tạo Order(PENDING_PAYMENT)
  Giữ tồn kho
  Ghi outbox PaymentRequested
  COMMIT

Bước 2 — Worker ngoài transaction đó
  Đọc event
  Gọi payment provider với idempotency key
  Nhận kết quả / webhook

Bước 3 — DB transaction mới
  Kiểm tra transition trạng thái hợp lệ
  Chuyển Order -> PAID hoặc PAYMENT_FAILED
  Phát event tiếp theo bằng outbox
  COMMIT

Bước 4 — Nếu thất bại/timeout theo quy tắc
  Hoàn tồn kho hoặc giữ chờ xử lý
  Ghi trạng thái/bồi hoàn thích hợp
~~~

Đây là một dạng **workflow/saga**, không phải một transaction database kéo dài xuyên toàn bộ thanh toán.

### 11.2. Compensation không phải database rollback

Nếu đã commit việc giữ tồn kho ở bước 1 rồi thanh toán thất bại ở bước 2, không thể rollback transaction đã commit. Cần một **transaction bù trừ**:

- Chuyển Order sang `PAYMENT_FAILED` hoặc `CANCELLED`.
- Hoàn lại số tồn đã giữ theo rule.
- Ghi sự kiện/audit liên quan.
- Chống bù trừ hai lần bằng trạng thái và idempotency.

Compensation là một hành động nghiệp vụ mới, có thể thất bại và cần retry. Nó **không hoàn toàn tương đương** với rollback ACID của transaction ban đầu.

---

## 12. Transactional outbox cho sự kiện cần phát sau commit

Giả sử muốn công bố sự kiện `OrderPlaced` tới message broker. Nếu làm:

~~~java
@Transactional
public UUID placeOrder(Command c) {
    PurchaseOrder order = createAndPersist(c);

    broker.publish(new OrderPlaced(order.getId()));

    return order.getId();
}
~~~

hai hệ thống không commit cùng nhau:

- Publish thành công nhưng database rollback: broker có event cho Order không tồn tại.
- Database commit thành công nhưng publish thất bại: Order có tồn tại mà hệ thống khác không nhận event.
- Publish timeout: không biết broker đã nhận hay chưa.

### 12.1. Outbox giải quyết phần nào?

Thay vì publish trực tiếp:

~~~java
@Transactional
public UUID placeOrder(Command c) {
    PurchaseOrder order = createAndPersist(c);

    em.persist(OutboxEvent.orderPlaced(
        order.getId(), Instant.now()
    ));

    return order.getId();
}
~~~

Order và OutboxEvent nằm **trong cùng database transaction**. Điều này đảm bảo:

- Nếu Order rollback, event outbox cũng rollback.
- Nếu commit thành công, cả Order và event outbox cùng tồn tại.
- Worker có thể đọc event sau commit và publish theo cơ chế retry.

Sơ đồ:

~~~text
Application transaction
   |
   +-- INSERT orders
   +-- UPDATE inventory
   +-- INSERT outbox_events
   |
   +-- COMMIT
        |
        v
Outbox poller / CDC
        |
        +-- publish event
        +-- ghi nhận đã publish
        +-- retry khi gặp lỗi
~~~

### 12.2. Outbox không mặc định bảo đảm exactly-once delivery

Một worker có thể:

1. Đọc event.
2. Publish tới broker thành công.
3. Bị crash trước khi đánh dấu `published_at`.

Lần chạy sau worker có thể publish lại event. Vì vậy:

- Consumer cần xử lý **idempotent** theo event ID hoặc key phù hợp.
- Worker có cơ chế retry/backoff và ghi trạng thái.
- Có cơ chế xử lý poison message/dead-letter và theo dõi backlog.
- Nếu nhiều worker poll, sử dụng claim/locking an toàn cho từng event, ví dụ phương án tương thích database với `FOR UPDATE SKIP LOCKED`.
- Thời điểm đánh dấu published cần được chọn rõ; không thể coi thao tác DB và broker luôn là một local JPA transaction.

Transactional outbox bảo đảm **ý định publish được lưu cùng business commit**. Nó không tự biến mạng/broker thành transaction của database.

### 12.3. Vì sao không publish trong @AfterCommit đơn giản là đủ?

Spring có cơ chế callback hoặc `@TransactionalEventListener(phase = AFTER_COMMIT)`. Nó giúp trì hoãn hành động đến sau commit, tránh thông báo sớm khi DB rollback.

Nhưng nếu process crash ngay sau commit trước khi callback chạy, sự kiện có thể mất. Nếu yêu cầu là **không làm mất event**, nên dùng outbox bền vững; callback sau commit có thể là cơ chế tối ưu bổ trợ, không thay thế outbox trong mọi mức độ tin cậy.

---

## 13. Ranh giới transaction và nhiều database/service

Cần phân biệt ba trường hợp:

### 13.1. Nhiều repository, cùng một database và transaction manager

Ví dụ:

~~~text
OrderRepository ----\
InventoryRepository -+---- same datasource / same DB transaction
OutboxRepository ----/
~~~

Một `@Transactional` ở service có thể bao trùm cả ba repository khi cấu hình JPA/transaction manager phù hợp.

### 13.2. Hai datasource hoặc hai EntityManagerFactory độc lập

~~~text
OrderRepository -> Database A / TransactionManager A

InventoryRepository -> Database B / TransactionManager B
~~~

Chỉ đặt `@Transactional` với manager A **không bảo đảm** thay đổi ở Database B rollback cùng A. Nếu cần atomicity xuyên nhiều transaction resources, có thể phải đánh giá XA/JTA/two-phase commit hoặc thiết kế lại dữ liệu/workflow.

Giao dịch phân tán có chi phí vận hành, availability và failure modes riêng. Không nên áp dụng chỉ vì muốn tái sử dụng `@Transactional` cho nhiều DB.

### 13.3. Microservices độc lập

~~~text
Order Service -> Order DB
Inventory Service -> Inventory DB
Payment Service -> Payment Provider
~~~

Một lời gọi service mạng không gia nhập local JPA transaction của Order Service chỉ vì method Java bên gọi có `@Transactional`.

Thường cần workflow/saga, outbox/inbox, idempotency, trạng thái rõ, timeout và compensation. Thiết kế “một giao dịch cho toàn bộ thay đổi” lúc này được hiểu là **một business workflow có tính nhất quán có kiểm soát**, không phải một database transaction duy nhất.

---

## 14. Không nên làm transaction quá dài

Transaction dài có thể:

- Giữ connection pool lâu.
- Giữ row/table locks làm request khác chờ.
- Tăng nguy cơ timeout, deadlock.
- Tạo nhiều entity managed trong persistence context gây tốn RAM.
- Làm transaction log/WAL lớn và rollback tốn tài nguyên.
- Giữ snapshot cũ, ảnh hưởng vacuum/garbage collection ở một số DBMS.
- Tăng khả năng conflict do nhiều dữ liệu thay đổi đồng thời.

Nhưng **không thể chỉ vì muốn transaction ngắn mà tách một hành động nguyên tử thành nhiều commit không có cơ chế phục hồi**.

Một cân bằng hợp lý:

1. Validate dữ liệu thuần Java sớm, ngoài transaction nếu không cần DB/lock.
2. Chỉ mở transaction khi bắt đầu các bước cần nhất quán.
3. Tải và khóa đúng dữ liệu cần thiết.
4. Thực hiện business logic ngắn gọn.
5. Persist thay đổi và outbox.
6. Commit sớm.
7. Xử lý email/HTTP/report nặng sau commit hoặc qua worker.

### 14.1. Đọc ngoài transaction có thể làm quyết định lỗi thời

Ví dụ:

~~~java
// Đọc số lượng bên ngoài transaction.
long available = inventoryService.getAvailable(sku);

// Nhiều thao tác chậm...

@Transactional
public void placeOrder(...) {
    if (available >= quantity) {
        // Lúc này dữ liệu có thể đã thay đổi.
    }
}
~~~

Business invariant phụ thuộc trạng thái cạnh tranh nên phải được **kiểm tra lại trong transaction** dưới cơ chế isolation/locking phù hợp, hoặc dùng atomic conditional SQL.

Có thể thực hiện validation cấu trúc ngoài transaction (chuỗi trống, số lượng âm, format request). Nhưng điều kiện về tồn kho, số dư và trạng thái đang bị các request khác thay đổi cần được bảo vệ trong transaction.

---

## 15. Isolation level và các bất thường thường gặp

Các mức isolation phổ biến:

- `READ_COMMITTED`.
- `REPEATABLE_READ`.
- `SERIALIZABLE`.
- Ngoài ra chuẩn SQL định nghĩa `READ_UNCOMMITTED`, nhưng ý nghĩa thực tế phụ thuộc DBMS.

Tên gọi isolation không đủ để suy ra mọi hành vi: các DBMS có cách triển khai MVCC, predicate locking, serialization failures và snapshot khác nhau.

### 15.1. Lost update

Hai transaction đọc cùng giá trị rồi đều ghi một giá trị mới, khiến cập nhật của transaction trước bị ghi đè. `@Version`, row lock hoặc atomic SQL có thể giải quyết tùy mô hình.

### 15.2. Write skew

Hai transaction đọc một điều kiện liên quan nhiều hàng và sửa **những hàng khác nhau**, khiến invariant tổng thể bị phá dù mỗi hàng riêng lẻ không bị lost update.

Ví dụ hai bác sĩ cùng trực, quy tắc “luôn có ít nhất một người trực”. Mỗi transaction thấy người kia đang trực rồi tự tắt trạng thái trực của mình. Ở một số isolation, cả hai commit khiến không còn ai trực.

Để bảo vệ invariant **liên hàng**, có thể cần SERIALIZABLE, locking theo một hàng điều phối, hoặc ràng buộc/thiết kế dữ liệu đảm bảo invariant.

### 15.3. Phantom/predicate condition

Một transaction kiểm tra “số đơn đang hoạt động dưới giới hạn”, transaction khác có thể thêm hàng mới trước khi transaction đầu commit. Không phải lúc nào `SELECT COUNT(*)` rồi INSERT cũng an toàn.

Nếu constraint không thể diễn đạt bằng UNIQUE đơn giản, cần có cơ chế locking/serialization hoặc một counter duy nhất được cập nhật nguyên tử.

### 15.4. SERIALIZABLE không có nghĩa không cần retry

Ở nhiều DBMS, SERIALIZABLE có thể từ chối một transaction bằng serialization failure để ngăn bất thường. Ứng dụng phải rollback và **retry toàn bộ unit of work** trong transaction mới nếu an toàn.

Không bắt lỗi serialization rồi chỉ chạy lại một câu INSERT cuối cùng trong transaction đang hỏng; tất cả điều kiện đã đọc trước đó cần được đánh giá lại.

---

## 16. Retry: lặp lại toàn bộ use case, không phải một phần tùy tiện

Các lỗi có thể cần retry:

- Deadlock được DB phát hiện.
- Serialization failure.
- Optimistic locking conflict.
- Lock timeout trong những trường hợp phù hợp.
- Sự cố mạng ngắn hạn mà kết quả transaction cần được xác minh.

Không phải lỗi nào cũng nên retry:

- Thiếu tồn kho hiện tại.
- Customer không tồn tại.
- Vi phạm nghiệp vụ cố định.
- Payload sai.
- Unique conflict vì request khác đã commit một yêu cầu không tương đương.

### 16.1. Một transaction thất bại phải được kết thúc

Nếu `flush()` lỗi constraint, persistence context/transaction có thể bị đánh dấu rollback-only. Không tiếp tục gọi `save()` và cố `commit()` ngay trong context đó.

Cách xử lý cơ bản:

~~~text
try attempt #1 trong T1
   |
   +-- conflict / deadlock
   +-- ROLLBACK T1
   |
   v
backoff có giới hạn
   |
   v
try attempt #2 trong T2 MỚI
   |
   +-- đọc lại dữ liệu
   +-- kiểm tra lại rule
   +-- commit hoặc rollback
~~~

Retry nên nằm **bên ngoài** method transaction để mỗi lần thử có transaction riêng. Nếu đặt retry quanh code bên trong một transaction dài, nó có thể chạy lại logic trên dữ liệu cũ hoặc trong transaction rollback-only.

### 16.2. Idempotency khi không biết commit đã xảy ra chưa

Giả sử server commit Order thành công nhưng kết nối HTTP mất trước khi client nhận response. Client gửi lại cùng `requestId`. Nếu không có idempotency, có thể tạo hai đơn và giảm tồn hai lần.

Một thiết kế:

- Client gửi `requestId` duy nhất cho hành động đặt hàng.
- Database có `UNIQUE(request_id)`.
- Khi yêu cầu trùng, service đọc Order đã commit theo requestId.
- So sánh chủ sở hữu, nội dung/yêu cầu tương ứng trước khi trả cùng kết quả.
- Ghi event/outbox một lần theo commit thành công; consumer xử lý idempotent.

Nếu request khác nội dung nhưng trùng key, không được âm thầm trả kết quả cũ như thể cùng hành động. Đây là lỗi contract idempotency.

### 16.3. Đặt retry ở tầng phù hợp với @Transactional

Trong Spring AOP, có thể dùng một wrapper khác gọi method `@Transactional` cho từng attempt. Cần chú ý thứ tự các interceptor `@Retryable`/`@Transactional` nếu dùng Spring Retry để bảo đảm mỗi retry mở transaction mới đúng như mong muốn. Không suy đoán thứ tự mặc định rồi triển khai vào production khi chưa kiểm chứng.

---

## 17. Validation và thứ tự thao tác trong transaction

Một transaction có thể viết nhiều thao tác theo thứ tự logic khác thứ tự SQL thực tế:

~~~java
em.persist(order);
inventory.reserve(qty);
em.persist(outbox);
~~~

Hibernate có thể trì hoãn và sắp thứ tự INSERT/UPDATE/DELETE trong action queue, miễn đáp ứng mapping/dependency. Do đó:

- Đừng dựa vào SQL xảy ra đúng theo thứ tự gọi method Java.
- Constraint có thể báo lỗi tại flush/commit thay vì khi đổi field.
- Khi logic cần dữ liệu đã được ghi để dùng trong native SQL/triggers, có thể cần `flush()` có chủ đích.
- Không dùng `flush()` như một cách tạo mini-commit.

### 17.1. Khi nào nên flush tường minh?

Có thể dùng `em.flush()` khi:

- Cần lỗi unique/FK xuất hiện trước khi tiến hành bước khác trong cùng transaction.
- Cần đảm bảo SQL pending được đồng bộ trước một thao tác native phụ thuộc.
- Cần quan sát database constraints trong một test.
- Cần chia lô xử lý có kiểm soát khi nhập dữ liệu lớn.

Không nên gọi `flush()` sau **mỗi entity** nếu điều đó phá lợi ích batching và tăng round-trip. Chỉ flush theo nhu cầu consistency của use case và cách ORM hoạt động.

### 17.2. Tránh gọi em.clear() giữa một unit of work nếu chưa hiểu

`em.clear()` detach toàn bộ managed entities. Nếu pending changes chưa được flush, chúng có thể bị bỏ không đồng bộ. Ngay cả sau flush, các Java object cũ không còn managed; thay đổi tiếp trên chúng có thể không được ghi.

Trong transaction nghiệp vụ nhỏ, thường không cần `clear()`. Với import hàng loạt, dùng flush/clear theo lô nhưng phải cân nhắc FK và các rule của từng batch.

---

## 18. Transaction trong Java SE với EntityTransaction

Không dùng Spring vẫn có thể thiết kế cùng nguyên tắc. Với persistence unit kiểu `RESOURCE_LOCAL`:

~~~java
import jakarta.persistence.*;

public class TransferService {

    private final EntityManagerFactory emf;

    public TransferService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public void transfer(
        Long fromId,
        Long toId,
        long amount
    ) {
        if (amount <= 0 || fromId.equals(toId)) {
            throw new IllegalArgumentException(
                "Giao dịch chuyển tiền không hợp lệ"
            );
        }

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            // Khóa các tài khoản theo thứ tự ID cố định.
            long firstId = Math.min(fromId, toId);
            long secondId = Math.max(fromId, toId);

            Account first = em.find(
                Account.class,
                firstId,
                LockModeType.PESSIMISTIC_WRITE
            );

            Account second = em.find(
                Account.class,
                secondId,
                LockModeType.PESSIMISTIC_WRITE
            );

            if (first == null || second == null) {
                throw new IllegalArgumentException(
                    "Tài khoản không tồn tại"
                );
            }

            Account source =
                first.getId().equals(fromId) ? first : second;

            Account target =
                first.getId().equals(toId) ? first : second;

            source.debit(amount);
            target.credit(amount);

            em.persist(TransferAudit.record(
                fromId, toId, amount
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
    }
}
~~~

Ví dụ giả định `Account` là entity cùng database, có `getId()`, `debit()`, `credit()` với kiểm tra số dư/tràn số, và `TransferAudit.record()` tạo một entity audit hợp lệ. Đây là cấu trúc minh họa transaction boundary; hệ thống tiền tệ thực tế cần mô hình số tiền, ledger, idempotency và chính sách kế toán nghiêm ngặt hơn.

Điểm đáng chú ý:

- `tx.begin()` trước khi đọc/khóa và thay đổi số dư.
- Hai Account và Audit nằm trong cùng transaction.
- Nếu `debit()` hoặc `credit()` thất bại, không có một nửa giao dịch được commit.
- Thứ tự khóa cố định giảm nguy cơ deadlock.
- `finally` luôn đóng EntityManager do ứng dụng tạo.
- Không chia chuyển tiền thành một transaction trừ người gửi và một transaction cộng người nhận.

### 18.1. EntityManagerFactory và EntityManager

`EntityManagerFactory` được thiết kế để dùng chung và tạo EntityManager. Một `EntityManager` không an toàn để chia sẻ tùy tiện giữa nhiều thread/request. Tạo hoặc nhận EntityManager theo đúng phạm vi unit of work, rồi đóng nếu thuộc quyền quản lý của ứng dụng.

Không dùng một EntityManager singleton cho nhiều chuyển tiền đồng thời; như thế vừa trộn persistence context, vừa làm ranh giới transaction không rõ.

---

## 19. Những lỗi thiết kế thường gặp

### Lỗi 1 — Mỗi repository.save() tự commit

Nếu nghiệp vụ cần ba thay đổi cùng thành công, không được để mỗi repository chạy một transaction độc lập rồi nghĩ outer method sẽ rollback được tất cả.

**Khắc phục:** đặt transaction ở application service, đảm bảo các repository tham gia cùng transaction resource.

### Lỗi 2 — Gọi thanh toán qua HTTP khi đang khóa database

HTTP timeout có thể kéo dài, khóa lâu và không thể rollback thanh toán đã được provider thực hiện.

**Khắc phục:** tách thành workflow nhiều bước, outbox/idempotency/compensation.

### Lỗi 3 — @Transactional trên private/self-invoked method

Trong cấu hình Spring proxy thông thường, annotation có thể không được interceptor thực thi.

**Khắc phục:** đặt boundary ở public method được gọi qua bean proxy, kiểm chứng propagation thật.

### Lỗi 4 — Dùng REQUIRES_NEW cho outbox bắt buộc

Nếu Outbox commit riêng còn Order rollback, có sự kiện về đơn không tồn tại.

**Khắc phục:** Outbox ghi trong **cùng transaction** của business change.

### Lỗi 5 — Bắt lỗi rồi return success

Nếu một bước bắt buộc thất bại nhưng bị nuốt exception, transaction có thể vẫn commit phần thay đổi, hoặc commit thất bại vì rollback-only.

**Khắc phục:** ném lỗi đúng loại, rollback rõ ràng, không tiếp tục context đã lỗi.

### Lỗi 6 — Nhầm flush với commit

`em.flush()` có thể phát SQL và gán ID, nhưng transaction vẫn có thể rollback.

**Khắc phục:** chỉ xem operation thành công bền vững sau commit, quản lý side effects riêng.

### Lỗi 7 — Chỉ kiểm tra số tồn mà không khóa/atomic update

Hai transaction cùng thấy available=1 và đều bán được một sản phẩm.

**Khắc phục:** pessimistic lock, optimistic version hoặc conditional UPDATE có affected row count.

### Lỗi 8 — Truy cập nhiều database nhưng tin một @Transactional

Một transaction manager không tự điều phối mọi datasource khác hay service HTTP.

**Khắc phục:** thiết kế rõ phạm vi transactional resources; đánh giá JTA/XA hoặc saga khi thật sự cần.

### Lỗi 9 — Transaction quá dài

Giữ khóa trong lúc tạo PDF, gửi email, gọi REST API hoặc xử lý toàn bộ file lớn.

**Khắc phục:** để transaction ngắn, defer tác vụ ngoài DB, chia batch/workflow có quy tắc nhất quán.

### Lỗi 10 — Retry trong transaction đang rollback-only

Sau một lỗi constraint/optimistic conflict, tiếp tục dùng cùng EntityManager và thử lại có thể thất bại hoặc phát sinh trạng thái không đáng tin.

**Khắc phục:** rollback toàn bộ và retry trong transaction mới, với số lần giới hạn.

### Lỗi 11 — Không có idempotency key

Client mất response rồi gửi lại có thể tạo thêm đơn và trừ tồn kho lần nữa.

**Khắc phục:** requestId/unique constraint, kiểm chứng nội dung request và trả kết quả của hành động đã commit.

### Lỗi 12 — Tin rằng @Version bảo vệ mọi invariant

`@Version` bảo vệ xung đột ghi trên entity có version phù hợp, nhưng không tự bảo đảm mọi quy tắc liên hàng hoặc xử lý bulk DML/ngoại hệ thống.

**Khắc phục:** xác định invariant và chọn đúng isolation/constraint/locking cho từng trường hợp.

### Lỗi 13 — Dùng test @Transactional nhưng không kiểm tra commit thật

Spring test gắn `@Transactional` thường rollback sau test theo cấu hình phổ biến. Test có thể thấy entity trong persistence context mà chưa bao giờ xác minh commit thành công.

**Khắc phục:** test những phần cần commit/rollback với transaction boundary riêng và EntityManager mới, đồng thời test các constraint ở database thật.

### Lỗi 14 — Dùng entity graph/collection mà không kiểm soát lazy loading

Một transaction quá rộng chỉ để tránh `LazyInitializationException` có thể che N+1 và lock lâu.

**Khắc phục:** thiết kế fetch plan, DTO và ranh giới truy cập phù hợp; không kéo transaction sang cả HTTP serialization.

---

## 20. Kiểm thử transaction boundary

Để tin rằng service thực hiện toàn bộ thay đổi trong một transaction, kiểm thử cần quan sát **trạng thái database sau commit hoặc rollback**, không chỉ kiểm tra mock được gọi đủ lần.

### 20.1. Test thành công

Chuẩn bị:

- Customer hợp lệ.
- JAVA-101 có 5.
- DB-201 có 3.

Gọi `placeOrder()` với 2 JAVA-101 và 1 DB-201. Sau khi transaction commit:

- Có một Order với hai OrderLine.
- Inventory tương ứng còn 3 và 2.
- Có một OutboxEvent liên kết đúng Order.
- requestId là duy nhất.
- Không có side effect gửi broker trực tiếp trong transaction.

Nên đọc kết quả bằng EntityManager/context mới hoặc truy vấn riêng sau commit, tránh phụ thuộc vào managed object còn giữ trong memory.

### 20.2. Test rollback khi sản phẩm thứ hai thiếu tồn

Chuẩn bị:

- JAVA-101 có 5.
- DB-201 có 0.

Gọi đặt hàng:

~~~java
assertThrows(
    InsufficientStockException.class,
    () -> placeOrderService.placeOrder(command)
);
~~~

Sau khi lời gọi đã kết thúc và rollback:

- JAVA-101 vẫn là 5.
- DB-201 vẫn là 0.
- Không có Order/OrderLine mới theo requestId.
- Không có OutboxEvent mới.
- Không phát thông báo thành công.

Test nên chạy với transaction thật, không chỉ mock InventoryRepository. Nếu test method tự được đánh dấu `@Transactional` và rollback tự động, cần chủ động kiểm chứng ranh giới của use case thay vì nhầm rollback của test với rollback do exception service.

### 20.3. Test lỗi unique requestId

Hai request cùng requestId được gửi gần nhau:

- Chỉ có tối đa một Order được commit cho key.
- Không có việc giữ tồn hai lần do cả hai request commit như hai đơn độc lập.
- Request lỗi unique được rollback và có thể đọc lại kết quả của request thành công trong transaction mới.
- Nếu payload khác cùng key, hệ thống trả lỗi conflict theo hợp đồng API.

### 20.4. Test concurrency trên cùng SKU

Dùng hai transaction thực và phối hợp thời điểm bắt đầu để mô phỏng hai người cùng đặt số lượng mà kho chỉ đủ cho một yêu cầu. Sau khi hai transaction kết thúc:

- Không có available âm.
- Tổng lượng đã giữ không vượt số lượng ban đầu.
- Một hoặc nhiều request có thể thất bại/timeout tùy chiến lược lock và lịch chạy.
- Không có Order thành công mà Inventory tương ứng chưa được giữ.

Test concurrency có thể cần latch/barrier và database thật; H2 in-memory không mặc nhiên tái hiện mọi đặc điểm locking của PostgreSQL/MySQL.

### 20.5. Test outbox và worker

- Khi Order transaction rollback, Outbox không có event.
- Khi commit, Outbox có event dù worker chưa chạy.
- Worker crash sau publish nhưng trước mark published: retry có thể phát lại; consumer không xử lý trùng tác động.
- Khi broker tạm lỗi, event không mất mà vẫn chờ retry.
- Khi event bị lỗi dữ liệu, có quy trình theo dõi và xử lý poison message.

---

## 21. Checklist thiết kế transaction cho một use case

Trước khi đánh dấu một method `@Transactional`, hãy làm rõ:

1. **Một hành động nghiệp vụ là gì?** Ví dụ “đặt một đơn hàng có N dòng”, không phải “lưu một entity”.
2. **Những thay đổi nào không được phép tồn tại riêng lẻ?** Order, Inventory, OrderLine, Outbox có cần commit cùng nhau không?
3. **Tất cả có cùng DB transaction resource không?** Nếu không, phải thiết kế workflow/distributed coordination khác.
4. **Boundary nằm ở application service nào?** Method được gọi qua transaction proxy chưa?
5. **Transaction cần ngắn đến đâu?** Có đang giữ khóa trong lúc gọi mạng/xử lý nặng không?
6. **Lỗi nào phải rollback?** Checked/un-checked exception, `rollbackFor`, rollback-only và exception ở commit.
7. **Propagation có phù hợp không?** Các bước bắt buộc nên tham gia transaction chung, tránh `REQUIRES_NEW` ngoài ý muốn.
8. **Các entity nào cần managed?** Dùng dirty checking, cascade hợp lý, không lạm dụng `merge()/save()`.
9. **Cần khóa hay constraint nào?** UNIQUE, CHECK, FK, `@Version`, row lock, atomic conditional SQL.
10. **Những điều kiện nào có thể đổi đồng thời?** Số dư, tồn kho, hạn mức, trạng thái, số lượng bản ghi.
11. **Khi nào phát tác động ngoài DB?** Outbox, idempotency và xử lý sau commit.
12. **Có thể retry an toàn không?** Retry toàn transaction, backoff có giới hạn, kiểm tra requestId.
13. **Cần compensation không?** Nếu nhiều bước đã commit độc lập hoặc liên hệ payment provider.
14. **Kiểm thử rollback thế nào?** Đọc DB sau transaction, test failure giữa các bước và conflict.
15. **Quan sát production thế nào?** Transaction duration, lock wait, rollback count, deadlock, outbox backlog, retry và latency.
16. **Dữ liệu audit/lịch sử có cần bất biến riêng?** Tránh hard delete hoặc thao tác bù không có dấu vết.
17. **Kết quả trả cho client có đúng sau commit không?** Không gửi thông báo thành công từ giữa transaction.
18. **Mọi writer đều tuân thủ constraint chứ?** Batch job, SQL native, admin tool và service khác đều có thể ghi DB.

### 21.1. Sơ đồ quyết định nhanh

~~~text
Use case cần nhiều thay đổi?
          |
          v
Các thay đổi có phải cùng thành công/thất bại?
       |                          |
      Không                       Có
       |                          |
       v                          v
Có thể chia thành        Có cùng DB transaction resource?
các bước độc lập               |               |
với quy tắc rõ               Có              Không
                              |               |
                              v               v
                    Một @Transactional    Saga/outbox/inbox,
                    tại service boundary  distributed coordination
                              |
                              v
                    Xác định concurrency:
                    locks / @Version / constraints
                              |
                              v
                    Ghi các thay đổi và outbox
                              |
                              v
                    Commit hoặc rollback trọn vẹn
~~~

Không phải mọi use case “thấy có nhiều entity” đều cần giữ một transaction lâu. Mấu chốt là **bất biến cần bảo vệ tại ranh giới commit** và **phạm vi tài nguyên thực sự có thể được transaction manager điều phối**.

---

## 22. Bài tập vận dụng

### Bài tập 1 — Nhiều save() nhưng một transaction

Một service tạo Order, cập nhật Inventory và thêm Audit bằng ba repository. Mỗi repository có phương thức `save()`.

Hỏi: có thể chỉ gọi ba `save()` liên tiếp mà chắc chắn tất cả rollback cùng nhau không? Thiết kế transaction boundary đặt ở đâu?

**Gợi ý:** một application service method đại diện cho use case nên có `@Transactional`; các repository phải tham gia cùng DB transaction.

### Bài tập 2 — Sản phẩm thứ hai hết tồn

Một khách đặt sản phẩm A và B. A còn 10, B còn 0. Code giảm tồn A trước rồi gặp exception khi xử lý B.

Hỏi: trạng thái A sau rollback phải là bao nhiêu? Tại sao không nên commit sau mỗi dòng hàng?

**Gợi ý:** A vẫn là 10, vì tất cả dòng hàng là một hành động đặt đơn nguyên tử.

### Bài tập 3 — REQUIRES_NEW làm outbox “mồ côi”

Tạo Order trong transaction T1, ghi Outbox bằng `REQUIRES_NEW` trong T2, sau đó T1 rollback.

Hỏi: điều gì còn trong database? Vì sao đó là sai với mục tiêu “chỉ phát event cho Order đã commit”?

**Gợi ý:** T2 có thể đã commit Outbox dù T1 rollback. Outbox phải tham gia cùng transaction nghiệp vụ.

### Bài tập 4 — Thanh toán ngoài database

Service mở transaction, giảm tồn và gọi cổng thanh toán. Cổng trả timeout. Có chắc payment chưa xử lý không? DB rollback có hoàn tiền không?

**Gợi ý:** không. Cần bước thanh toán riêng với idempotency key, webhook/trạng thái, outbox và compensation theo nghiệp vụ.

### Bài tập 5 — Hai người đặt món cuối cùng

Inventory available=1. Hai transaction cùng cố giảm 1. Thiết kế hai giải pháp:

- PESSIMISTIC_WRITE.
- Atomic conditional SQL update với affected row count.

Giải thích vì sao chỉ kiểm tra `available >= 1` trong bộ nhớ không đủ.

### Bài tập 6 — Checked exception

Một method `@Transactional` cập nhật Inventory rồi ném checked exception. Hãy giải thích rollback mặc định có thể khác RuntimeException thế nào và cách dùng `rollbackFor` khi thực sự muốn rollback.

### Bài tập 7 — Nuốt exception

Một method bắt `RuntimeException` từ `reserveStock()`, log lỗi và return một Order ID giả. Tại sao nguy hiểm? Nêu hai trường hợp có thể xảy ra ở commit: commit phần thay đổi hoặc lỗi rollback-only.

### Bài tập 8 — Idempotency khi mất response

Server commit Order thành công nhưng client không nhận được HTTP response. Client retry với cùng requestId. Thiết kế cách tránh trừ tồn hai lần và trả kết quả của Order đã tạo.

**Gợi ý:** unique requestId ở DB, lookup trong transaction mới khi key trùng, xác minh payload và chủ sở hữu.

### Bài tập 9 — Bulk UPDATE và persistence context

Trong transaction, service tải Inventory managed, sau đó dùng native SQL trừ tồn trực tiếp trong DB. Tại sao giá trị `inventory.getAvailable()` có thể stale? Làm sao tránh việc một flush sau đó ghi đè hoặc dùng dữ liệu sai?

### Bài tập 10 — Kiểm thử rollback thực tế

Thiết kế integration test:

- Bắt đầu với tồn kho A=5, B=0.
- Gọi placeOrder(A=1, B=1).
- Kiểm tra exception.
- Dùng transaction/context mới đọc Inventory, Order và Outbox.
- Khẳng định cả ba loại dữ liệu phản ánh rollback đầy đủ.

Vì sao chỉ `verify(mockRepository).save(...)` không đủ chứng minh tính nguyên tử?

---

## 23. Ghi nhớ

- **Transaction boundary nên theo một hành động nghiệp vụ**, không theo từng câu SQL hay từng repository.
- **Atomicity** nghĩa là các thay đổi bắt buộc trong cùng DB transaction commit cùng nhau hoặc rollback cùng nhau.
- **Persistence context** theo dõi entity; **transaction** quyết định ranh giới commit. `flush()` không phải `commit()`.
- Trong Spring/JPA, **application service method `@Transactional`** thường là nơi phù hợp để điều phối toàn bộ use case.
- `Propagation.REQUIRED` giúp các collaborator tham gia transaction hiện tại; `REQUIRES_NEW` tạo kết quả commit độc lập và có thể phá atomicity nếu dùng sai.
- **Rollback mặc định của Spring thường áp dụng cho RuntimeException/Error**; checked exception cần chính sách phù hợp. Đừng nuốt lỗi bắt buộc.
- **Một transaction không tự tránh overselling/lost update**; dùng constraint, optimistic/pessimistic locking hoặc conditional UPDATE theo invariant.
- **Khóa nhiều dòng theo thứ tự ổn định**, giữ transaction ngắn và có chính sách timeout/deadlock.
- **Đừng gọi HTTP payment, gửi email hoặc publish broker trực tiếp trong transaction dài** rồi trông đợi database rollback hoàn tác tác động ngoài.
- **Transactional outbox** ghi ý định phát event cùng business commit; worker publish sau commit và consumer phải xử lý trùng khi cần.
- **Nhiều DB/microservice** không tự tham gia một local JPA transaction; dùng saga/compensation hoặc distributed coordination phù hợp.
- **Retry phải bắt đầu transaction mới**, đánh giá lại điều kiện nghiệp vụ và bảo vệ idempotency bằng unique constraint.
- **Kiểm thử transaction bằng trạng thái database sau commit/rollback**, bao gồm thất bại ở giữa use case và cạnh tranh đồng thời.

**Kết luận:** Thiết kế giao dịch đúng bắt đầu bằng việc xác định **điều gì phải đúng sau khi một hành động nghiệp vụ kết thúc**. Trong phạm vi một database, nhóm tất cả các thay đổi liên quan dưới cùng transaction, kiểm soát concurrency và chỉ coi hành động thành công sau commit. Khi workflow vượt qua ranh giới database, không cố kéo một `@Transactional` bao trùm HTTP/broker; hãy dùng trạng thái nghiệp vụ, outbox, idempotency và compensation để duy trì tính nhất quán một cách minh bạch.
