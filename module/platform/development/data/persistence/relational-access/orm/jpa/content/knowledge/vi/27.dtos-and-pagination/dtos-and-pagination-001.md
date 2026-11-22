# Lựa chọn entity hoặc DTO theo mục đích đọc dữ liệu trong JPA

Trong Java Persistence API (JPA), truy vấn có thể trả về **entity được quản lý bởi persistence context** hoặc **DTO (Data Transfer Object)** chứa các giá trị mà một use case thực sự cần. Cả hai đều có thể biểu diễn mã đơn hàng, trạng thái và tổng tiền, nhưng khác nhau đáng kể về vòng đời, khả năng thay đổi dữ liệu, chi phí truy vấn, lazy loading, phân trang và bảo mật.

Xét hai yêu cầu:

- Màn hình danh sách cần hiển thị 20 đơn hàng: mã đơn, trạng thái, tổng tiền, tên khách hàng và ngày tạo.
- Một service xử lý thanh toán cần lấy một đơn hàng, xác nhận trạng thái hiện tại, cập nhật aggregate và bảo vệ optimistic locking.

Cùng một entity `PurchaseOrder` có thể tham gia cả hai use case. Tuy nhiên, **màn hình danh sách thường phù hợp với DTO projection**, còn **service thực hiện thay đổi nghiệp vụ thường phù hợp với managed entity**.

Một truy vấn Entity:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
~~~

Một truy vấn DTO projection:

~~~java
List<OrderListItem> items = em.createQuery(
    """
    SELECT new com.example.shop.read.OrderListItem(
        o.id, o.orderNumber, o.status, o.totalAmount,
        c.displayName, o.createdAt
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.tenantId = :tenantId
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    OrderListItem.class
)
.setParameter("tenantId", tenantId)
.setMaxResults(20)
.getResultList();
~~~

Hai truy vấn có mục đích khác nhau. Câu đầu trả managed entity trong persistence context thích hợp; câu sau tạo những DTO chỉ mang các trường đã chọn. Với một danh sách đọc đơn thuần, DTO tránh phải materialize nhiều thuộc tính/associations không dùng. Với command thay đổi dữ liệu, managed entity lại có lợi vì kết hợp domain method, dirty checking và optimistic locking.

**Nguyên tắc xuyên suốt:** Không chọn entity hay DTO vì một công cụ được coi là “nhanh hơn” trong mọi tình huống. Hãy quyết định theo **dữ liệu sẽ được sử dụng thế nào sau khi đọc, số lượng bản ghi, các quan hệ cần tải, yêu cầu transaction và hợp đồng output**.

Bài học này đi từ mô hình entity đến các cách tạo DTO trong JPQL, Criteria API và Spring Data JPA; so sánh entity + mapper với projection trực tiếp; xử lý quan hệ một-nhiều, N+1, LazyInitializationException, Page/Slice, COUNT query, keyset pagination, read-only transaction, bảo mật và kiểm thử.

## 1. Entity là gì dưới góc nhìn đọc dữ liệu?

Entity JPA đại diện cho đối tượng có identity và mapping tới dữ liệu quan hệ:

~~~java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private long version;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    // Mapping khác...
}
~~~

Khi gọi:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);
~~~

trong persistence context phù hợp, `order` có thể là **managed entity**. Nó có những đặc tính:

- Identity map gắn identity với managed instance.
- Dirty checking phát hiện thay đổi field khi flush.
- `@Version` phục vụ optimistic locking khi JPA cập nhật managed entity.
- `@ManyToOne`, `@OneToMany` và association mappings khác.
- Các thuộc tính/association có thể chưa được tải do fetch strategy.
- Lifecycle callbacks, domain methods và cascade theo JPA.
- Trạng thái managed/detached tùy thời điểm.

Một entity được trả ra không nhất thiết chứa toàn bộ graph object trong bộ nhớ. Provider có thể sử dụng proxy/lazy collection, hoặc tải thêm association qua SQL khi code truy cập.

### 1.1. Managed entity và detached entity

~~~text
EntityManager.find(...)
          |
          v
       managed
          |
      +---+----------+
      |              |
   flush/query      close/clear/detach
      |              |
      v              v
  managed state   detached entity
                     |
                     +-- field đã tải: thường vẫn đọc được
                     +-- field LAZY chưa tải: có thể lỗi
~~~

Một entity detached vẫn là object Java. Các giá trị đã tải có thể tiếp tục được đọc, nhưng lazy association chưa khởi tạo có thể cần session/context không còn tồn tại.

### 1.2. Vì sao entity không đồng nghĩa “đọc toàn bộ database”?

Có nhiều fetch strategies và provider optimizations. Một entity result không mặc định tải tất cả relations. Nhưng một entity result thường mang state/metadata phục vụ persistence context, khác với DTO đơn thuần.

## 2. DTO là gì?

DTO là kiểu dữ liệu cho use case, không cần là JPA entity.

~~~java
package com.example.shop.read;

import com.example.shop.domain.OrderStatus;
import java.math.BigDecimal;
import java.time.Instant;

public record OrderListItem(
    Long id,
    String orderNumber,
    OrderStatus status,
    BigDecimal totalAmount,
    String customerName,
    Instant createdAt
) {}
~~~

Một record như `OrderListItem`:

- Không có `@Entity` và không được EntityManager quản lý.
- Không tự dirty check khi thay đổi hoặc được tạo lại.
- Không có proxy của JPA nếu chỉ chứa giá trị/DTO thuần.
- Có thể dùng ở controller, serialization, export và test mà không cần mở persistence context để truy cập dữ liệu đã có.
- Định nghĩa rõ những field mà API/use case được phép trả.
- Không được `em.merge` chỉ vì có trường `id`.

### 2.1. DTO không nhất thiết là record

DTO có thể là:

- Java `record`.
- Immutable class với constructor.
- POJO có getter/setter.
- Interface-based projection trong Spring Data JPA.
- Một kiểu response chứa các DTO con.

Record thường phù hợp với dữ liệu chỉ đọc, nhưng không phải yêu cầu bắt buộc.

### 2.2. DTO khác partial entity

Không nên tạo một entity chỉ có ID và hai field rồi coi như JPA sẽ quản lý đầy đủ:

~~~java
PurchaseOrder order = new PurchaseOrder();
// Chỉ đặt id, number và status rồi đưa vào merge.
~~~

Một object có mapping entity nhưng thiếu state không phải DTO an toàn để cập nhật. `merge` có thể sao chép field null/stale và gây mất dữ liệu nếu thiết kế không đúng.

Nếu cần đọc một phần, hãy tạo **read DTO** độc lập với persistence mapping.

## 3. So sánh entity và DTO

| Tiêu chí | Entity managed | DTO / projection |
|---|---|---|
| Mục tiêu | Domain/persistence identity | Truyền dữ liệu cho use case |
| Được EntityManager quản lý | Có khi managed | Không |
| Dirty checking | Có | Không |
| `@Version` tự được JPA quản lý khi cập nhật | Có theo JPA | Không |
| Lazy loading | Có thể | Không nếu DTO chứa value fields thuần |
| Entity callbacks | Theo lifecycle | Không |
| Chọn subset fields | Không phải mặc định của entity query | Trực tiếp qua projection |
| Identity map | Có | Không |
| Thích hợp cho domain command | Thường có | Không thay entity managed |
| Thích hợp cho REST list | Cần cân nhắc rủi ro | Thường tốt |
| Thích hợp cho báo cáo tổng hợp | Có thể quá nặng | Thường tốt |
| Phân trang | Có thể, nhưng fetch graph ảnh hưởng | Thuận tiện nếu chỉ có root rows |
| Dễ hạn chế field API | Có thể cần serializer rules | Rõ từ class DTO |
| Sửa database qua thay đổi object | Có thể khi managed | Không |
| Phụ thuộc mapping schema | Có | Query DTO vẫn dựa vào entity/SQL fields |

**DTO không tự động nhanh hơn entity.** Muốn hưởng lợi từ chỉ đọc những cột cần thiết, truy vấn cũng phải là scalar/constructor projection; map từ entity đã tải đủ sang DTO chỉ thay đổi kiểu object ở bước sau.

## 4. Các mục đích đọc dữ liệu trong ứng dụng

Trước khi viết repository, xác định nhiệm vụ:

1. **Đọc để thay đổi nghiệp vụ:** confirm payment, cancel order, cập nhật inventory reservation; thường cần managed entity.
2. **Đọc để hiển thị list:** order table, customer lookup, autocomplete; thường cần DTO projection và pagination.
3. **Đọc chi tiết:** một Order kèm Customer và Lines; có thể fetch entity rồi map DTO hoặc query nhiều DTO.
4. **Đọc để báo cáo:** SUM/COUNT/GROUP BY, dashboard; thường dùng scalar/aggregate DTO.
5. **Đọc để export:** hàng trăm nghìn dòng; dùng DTO projection theo batch/keyset.
6. **Đọc để kiểm tra tồn tại:** EXISTS hoặc COUNT/ID; không cần tạo toàn bộ entity.
7. **Đọc gửi async process:** truyền ID hoặc immutable snapshot DTO, không chuyển lazy entity qua thread.

### 4.1. Bảng lựa chọn theo mục đích

| Tình huống | Kiểu đọc thường phù hợp | Lý do |
|---|---|---|
| Thanh toán một Order | Entity managed | Domain method, version, transaction |
| Danh sách 20 Order | Page DTO | Chỉ lấy cột cần hiển thị |
| Chi tiết một Order có 5 Lines | Detail DTO | API contract, kiểm soát lazy |
| Báo cáo doanh thu theo ngày | Aggregate DTO | DB tính tổng |
| Chỉ lấy tên Customer | String/DTO scalar | Không cần entity |
| Kiểm tra Order tồn tại trong tenant | EXISTS/ID | Không cần entity graph |
| Đọc 1.000.000 Order để export | DTO theo chunk | Giảm managed state/memory |
| Xóa Order qua JPA lifecycle | Entity managed | `em.remove`, cascade theo mapping |
| Query một entity nội bộ đơn giản | Entity hoặc DTO | Dựa trên chi phí bảo trì |
| Danh sách parent kèm children | Page ID + DTO batch | Tránh phân trang trên JOIN rows |

Một service có thể dùng **entity cho command và DTO cho query** mà không cần triển khai CQRS đầy đủ.

## 5. Mô hình entity ví dụ

Giả sử hệ thống bán hàng có:

~~~text
Customer (1) -------- (N) PurchaseOrder
                             |
                             | (1)
                             |
                             +------ (N) OrderLine
~~~

### 5.1. OrderStatus

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED,
    EXPIRED
}
~~~

### 5.2. Customer

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    @Column(name = "email", nullable = false, length = 254)
    private String email;

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

### 5.3. PurchaseOrder

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_number", nullable = false,
            length = 40, unique = true)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public long getVersion() { return version; }
    public Long getTenantId() { return tenantId; }
    public String getOrderNumber() { return orderNumber; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Instant getCreatedAt() { return createdAt; }
    public Customer getCustomer() { return customer; }
    public List<OrderLine> getLines() { return lines; }

    public void confirmPayment() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                "Order is not pending"
            );
        }
        status = OrderStatus.PAID;
    }
}
~~~

### 5.4. OrderLine

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_sku", nullable = false)
    private String productSku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {}

    public Long getId() { return id; }
    public String getProductSku() { return productSku; }
    public int getQuantity() { return quantity; }
    public BigDecimal getUnitPrice() { return unitPrice; }
}
~~~

### 5.5. SQL schema ý tưởng

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    email VARCHAR(254) NOT NULL
);

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    product_sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(14,2) NOT NULL
);

CREATE INDEX idx_order_tenant_created
    ON purchase_order(tenant_id, created_at DESC, id DESC);

CREATE INDEX idx_orderline_order
    ON order_line(order_id);
~~~

Đây là mapping/DDL minh họa, không phải migration hoàn chỉnh. Chọn kiểu thời gian, precision, identity generation, indexes và domain constraints theo database thật.

## 6. Entity cho command: Thay đổi dữ liệu có quản lý

Một use case xác nhận thanh toán:

~~~java
@Service
public class PaymentApplicationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void confirmPayment(
            long orderId,
            long authenticatedTenantId) {

        PurchaseOrder order = em.createQuery(
            """
            SELECT o
            FROM PurchaseOrder o
            WHERE o.id = :id
              AND o.tenantId = :tenantId
            """,
            PurchaseOrder.class
        )
        .setParameter("id", orderId)
        .setParameter("tenantId", authenticatedTenantId)
        .getSingleResult();

        order.confirmPayment();
    }
}
~~~

Trong transaction phù hợp:

- Entity result có thể được managed.
- Domain method kiểm tra trạng thái `PENDING` trước khi chuyển `PAID`.
- Dirty checking phát sinh UPDATE khi flush/commit.
- `@Version` hỗ trợ optimistic locking.
- Không cần `em.merge(order)` chỉ để lưu một entity vẫn đang managed.

### 6.1. Nếu dùng DTO để đọc rồi update?

~~~java
public record OrderSnapshot(
    Long id,
    OrderStatus status,
    long version
) {}
~~~

Khi viết:

~~~java
OrderSnapshot snapshot = ...;

snapshot = new OrderSnapshot(
    snapshot.id(),
    OrderStatus.PAID,
    snapshot.version()
);
~~~

database không tự đổi. DTO không được dirty checked. Ứng dụng phải xây một command/update query riêng và tự thiết kế concurrency. Đó là lựa chọn có thể hợp lệ nhưng khác với cách JPA managed entity hoạt động.

### 6.2. Managed entity không giải quyết tự động mọi rủi ro

Backend vẫn cần xác nhận payment receipt, giới hạn tenant, xử lý double payment, idempotency, isolation và event/outbox khi có hệ thống ngoài DB. Lý do chọn entity là vì nó phù hợp với **hành vi cần thực hiện**, không phải vì ORM tự xử lý toàn bộ business rules.

## 7. DTO cho danh sách: Đọc chỉ những trường cần

Danh sách Order chỉ cần:

~~~text
ID | Mã đơn | Trạng thái | Tổng tiền | Khách hàng | Ngày tạo
~~~

DTO:

~~~java
package com.example.shop.read;

import com.example.shop.domain.OrderStatus;
import java.math.BigDecimal;
import java.time.Instant;

public record OrderListItem(
    Long id,
    String orderNumber,
    OrderStatus status,
    BigDecimal totalAmount,
    String customerName,
    Instant createdAt
) {}
~~~

JPQL constructor projection:

~~~java
List<OrderListItem> items = em.createQuery(
    """
    SELECT new com.example.shop.read.OrderListItem(
        o.id,
        o.orderNumber,
        o.status,
        o.totalAmount,
        c.displayName,
        o.createdAt
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.tenantId = :tenantId
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    OrderListItem.class
)
.setParameter("tenantId", tenantId)
.setMaxResults(20)
.getResultList();
~~~

Kết quả là DTOs, không phải PurchaseOrder entities.

### 7.1. Vì sao truy vấn có JOIN Customer?

Màn hình cần `customerName`. Query join to-one association để chọn `Customer.displayName` thay vì lazy load Customer cho từng Order ở Java.

### 7.2. JPQL dùng property Java, không dùng SQL column

`o.totalAmount` và `c.displayName` là thuộc tính entity. JPA provider dựa trên mapping để chọn những SQL columns phù hợp.

### 7.3. Constructor phải tương thích

`new com.example.shop.read.OrderListItem(...)` yêu cầu class/record có constructor tương ứng về số tham số, thứ tự và kiểu Java. Nếu thay `status` thành String trong DTO mà JPQL trả OrderStatus enum, phải thiết kế conversion phù hợp.

### 7.4. DTO projection không phải managed entity

Không thể gọi `entityManager.remove(orderListItem)` hay mong JPA tự ghi những thay đổi trên DTO. Read model tách khỏi persistence lifecycle.

## 8. Chuyển entity thành DTO sau khi đọc có giống direct projection không?

Hai cách:

**Cách A — Load entity, rồi map sang DTO:**

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

List<OrderListItem> items = orders.stream()
    .map(o -> new OrderListItem(
        o.getId(),
        o.getOrderNumber(),
        o.getStatus(),
        o.getTotalAmount(),
        o.getCustomer().getDisplayName(),
        o.getCreatedAt()
    ))
    .toList();
~~~

**Cách B — Query trực tiếp thành DTO:**

~~~java
List<OrderListItem> items = em.createQuery(
    """
    SELECT new com.example.shop.read.OrderListItem(
        o.id, o.orderNumber, o.status, o.totalAmount,
        c.displayName, o.createdAt
    )
    FROM PurchaseOrder o JOIN o.customer c
    """,
    OrderListItem.class
).getResultList();
~~~

Ở cách A:

- JPA đã materialize các entities.
- Persistence context quản lý identity/state phù hợp.
- Mỗi `getCustomer()` có thể kích hoạt lazy SELECT.
- Query ban đầu có thể chọn những field entity mà DTO không cần.

Ở cách B:

- Query chọn các trường cần dùng để tạo DTO.
- Không phải materialize PurchaseOrder hay Customer entity cho result này.
- Không có lazy Customer proxy trong DTO.
- Có thể giảm object graph và network payload.

### 8.1. Mapper sau entity vẫn có trường hợp phù hợp

Nếu entity đã được load vì domain command hoặc view detail có graph nhỏ, mapping sang DTO trong transaction có thể rất tự nhiên. Đừng tạo query DTO thứ hai chỉ vì một quy tắc máy móc.

### 8.2. MapStruct không tự sửa kế hoạch tải

Một mapper:

~~~java
@Mapping(target = "customerName",
         source = "customer.displayName")
OrderListItem toDto(PurchaseOrder order);
~~~

vẫn cần đọc `order.getCustomer().getDisplayName()`. Nếu Customer chưa tải và context không còn, mapper có thể lỗi; nếu context còn, có thể phát sinh N+1.

**Thay đổi kiểu output không thay thế việc xác định SQL cần đọc.**

## 9. Khi nào chỉ cần scalar hoặc Tuple?

Nếu use case chỉ cần đếm đơn:

~~~java
Long count = em.createQuery(
    """
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
    """,
    Long.class
)
.setParameter("tenantId", tenantId)
.getSingleResult();
~~~

Không cần entity hoặc DTO class riêng để trả một scalar.

Nếu cần nhiều cột dùng nội bộ:

~~~java
List<Tuple> rows = em.createQuery(
    """
    SELECT o.id AS orderId,
           o.orderNumber AS orderNumber,
           o.totalAmount AS total
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
    """,
    Tuple.class
)
.setParameter("tenantId", tenantId)
.getResultList();
~~~

Đọc:

~~~java
for (Tuple row : rows) {
    Long id = row.get("orderId", Long.class);
    String number = row.get("orderNumber", String.class);
    BigDecimal total = row.get("total", BigDecimal.class);
}
~~~

### 9.1. Scalar và Tuple có ưu điểm

- Không cần materialize entity graph.
- Thuận tiện cho aggregate/reporting.
- Có thể dùng trong query động trước khi định hình DTO.

### 9.2. Nhược điểm

- Tuple aliases là String.
- Đổi alias/type có thể lỗi runtime.
- Truyền Tuple/Object[] qua nhiều tầng làm code khó đọc.

Với một API sống lâu dài, DTO có tên thường rõ hơn kiểu dữ liệu tạm.

## 10. Criteria API: Chọn DTO với `cb.construct`

Khi nhiều filter tùy chọn, Criteria API có thể xây cả WHERE và projection.

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<OrderListItem> cq =
    cb.createQuery(OrderListItem.class);

Root<PurchaseOrder> order =
    cq.from(PurchaseOrder.class);

Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.INNER);

cq.select(
    cb.construct(
        OrderListItem.class,
        order.get("id"),
        order.get("orderNumber"),
        order.get("status"),
        order.get("totalAmount"),
        customer.get("displayName"),
        order.get("createdAt")
    )
);

cq.where(
    cb.equal(order.get("tenantId"), tenantId),
    cb.greaterThanOrEqualTo(
        order.get("totalAmount"),
        minimumTotal
    )
);

cq.orderBy(
    cb.desc(order.get("createdAt")),
    cb.desc(order.get("id"))
);

List<OrderListItem> items =
    em.createQuery(cq)
      .setMaxResults(20)
      .getResultList();
~~~

Kết quả vẫn là DTO. `Root<PurchaseOrder>` dùng để mô tả query, không có nghĩa bản thân result phải là entity.

### 10.1. Khi Criteria phù hợp

- Có nhiều bộ lọc runtime.
- Cấu trúc JOIN/AND/OR thay đổi.
- Cần tái sử dụng logic filter cho data/count queries.
- Dự án có static metamodel để giảm lỗi String paths.

### 10.2. Khi JPQL constructor dễ đọc hơn

Truy vấn cố định với vài điều kiện thường ngắn gọn hơn khi viết JPQL trực tiếp. Không đổi tất cả SELECT sang Criteria chỉ vì muốn DTO.

## 11. Fetch plan khi thực sự cần entity

Một use case domain cần đọc Customer để kiểm tra quyền/điều kiện. Có thể yêu cầu tải Customer bằng JPQL:

~~~java
PurchaseOrder order = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    JOIN FETCH o.customer
    WHERE o.id = :id
      AND o.tenantId = :tenantId
    """,
    PurchaseOrder.class
)
.setParameter("id", orderId)
.setParameter("tenantId", tenantId)
.getSingleResult();
~~~

`JOIN FETCH` yêu cầu association được nạp cùng entity theo ngữ nghĩa JPQL, khác JOIN thông thường chỉ để lọc/chọn trường.

### 11.1. EntityGraph

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

TypedQuery<PurchaseOrder> query = em.createQuery(
    """
    SELECT o FROM PurchaseOrder o
    WHERE o.id = :id AND o.tenantId = :tenantId
    """,
    PurchaseOrder.class
);

query.setParameter("id", orderId);
query.setParameter("tenantId", tenantId);
query.setHint("jakarta.persistence.loadgraph", graph);

PurchaseOrder order = query.getSingleResult();
~~~

Có thể dùng `jakarta.persistence.fetchgraph` theo semantics fetch graph. Provider có thể triển khai bằng JOIN hoặc secondary SELECT, không nhất thiết một SQL.

### 11.2. Trả DTO sau khi fetch entity

Service có thể:

1. Query entity với JOIN FETCH/EntityGraph.
2. Map thành DTO trong transaction.
3. Trả DTO để controller serialize.

Do đó **đọc entity và trả DTO không loại trừ nhau**. Phải cân nhắc so với direct DTO projection để chọn chi phí phù hợp.

### 11.3. Đừng đổi mọi relation thành EAGER

EAGER toàn hệ thống có thể tải association không dùng, tăng SQL/row width và gây N+1 qua secondary SELECT. Nên chọn fetch plan theo use case.

## 12. N+1 khi đọc entity để tạo danh sách

Code:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getDisplayName()
    );
}
~~~

Nếu mỗi Customer chưa được tải, provider có thể thực hiện:

~~~text
1 SELECT cho Orders
N SELECT bổ sung cho Customers
----------------------------
1 + N SQL queries (kịch bản xấu)
~~~

Đây là **N+1 query problem**. Nếu nhiều Orders chung Customer hoặc cache đã có Customer, số SQL bổ sung có thể ít hơn, nhưng không nên dựa vào điều đó để thiết kế.

### 12.1. Cách khắc phục cho list

- JPQL constructor projection chọn `customer.displayName` qua JOIN.
- JOIN FETCH to-one khi thực sự cần entity.
- EntityGraph phù hợp.
- Batch fetching của provider nếu đã kiểm chứng.
- Query theo tập IDs và map trong Java.

### 12.2. DTO không tự sửa N+1 nếu mapper gọi lazy getter

Nếu bạn load `List<PurchaseOrder>` rồi mới đổi thành DTO, SQL vẫn có thể là 1+N. Lợi ích của direct DTO projection nằm ở **query selection và result shape**, không ở tên class.

## 13. LazyInitializationException và boundary API

Một flow thường gặp:

~~~text
Controller
    |
    v
Service @Transactional
    |
    +-- SELECT Order
    +-- lines còn LAZY
    +-- return PurchaseOrder
    |
    v
Transaction-scoped persistence context kết thúc
    |
    v
JSON serializer gọi getLines()
    |
    v
Hibernate LazyInitializationException
~~~

Hibernate dùng exception riêng `org.hibernate.LazyInitializationException` khi cố khởi tạo proxy/collection không còn session phục vụ. JPA provider khác có thể biểu hiện khác.

### 13.1. Vì sao entity list nguy hiểm khi trả trực tiếp?

Serializer có thể duyệt getters ngoài phạm vi service. Các association có thể:

- Chưa được tải.
- Gây query bổ sung khi OSIV giữ context mở.
- Chứa vòng tham chiếu hai chiều.
- Làm response phát triển ngoài dự kiến.
- Chứa field không được phép công bố.

### 13.2. DTO đã materialize giải quyết boundary

Nếu service trả `OrderListItem` record thuần, serializer không cần load `Order.lines` hoặc `Customer`. Output contract rõ ràng và độc lập hơn với persistence context.

### 13.3. Không dùng OSIV như giải pháp mặc định

Spring Open EntityManager in View có thể giữ EntityManager mở qua giai đoạn serialize, giúp lazy access đôi khi thành công. Nhưng N+1 có thể chuyển từ service sang controller/serializer; SQL có thể phát sinh sau transaction nghiệp vụ, làm latency khó đoán. Một số ứng dụng chủ đích sử dụng OSIV, song API có DTO/fetch boundary rõ thường dễ kiểm soát hơn.

### 13.4. Không trả List rỗng khi lazy fail

“Collection chưa tải” không đồng nghĩa “database không có rows”. Catch exception rồi trả `List.of()` sẽ làm sai semantics nghiệp vụ.

## 14. Chi tiết Order có Lines: Dựng DTO trong service

DTO:

~~~java
package com.example.shop.read;

public record OrderLineView(
    Long id,
    String productSku,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderDetailsView(
    Long id,
    String orderNumber,
    OrderStatus status,
    BigDecimal totalAmount,
    String customerName,
    List<OrderLineView> lines
) {}
~~~

Một service có thể fetch một Order với Customer và Lines:

~~~java
@Transactional(readOnly = true)
public OrderDetailsView getDetails(
        long tenantId, long orderId) {

    PurchaseOrder order = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        JOIN FETCH o.customer
        LEFT JOIN FETCH o.lines
        WHERE o.id = :id
          AND o.tenantId = :tenantId
        """,
        PurchaseOrder.class
    )
    .setParameter("id", orderId)
    .setParameter("tenantId", tenantId)
    .getSingleResult();

    List<OrderLineView> lines = order.getLines().stream()
        .map(line -> new OrderLineView(
            line.getId(),
            line.getProductSku(),
            line.getQuantity(),
            line.getUnitPrice()
        ))
        .toList();

    return new OrderDetailsView(
        order.getId(),
        order.getOrderNumber(),
        order.getStatus(),
        order.getTotalAmount(),
        order.getCustomer().getDisplayName(),
        List.copyOf(lines)
    );
}
~~~

### 14.1. Vì sao cách này phù hợp với một Order?

Query chỉ lấy một parent theo ID, không phải 20 hoặc 200 parents phải phân trang. Với collection nhỏ/vừa, fetch một Order và chuyển DTO trong transaction có thể dễ hiểu.

### 14.2. Khi nào không nên fetch hết Lines?

Nếu một Order có hàng chục nghìn Lines, một query collection fetch có thể rất tốn memory/traffic. Có thể phân trang Lines hoặc dùng hai query projection riêng.

### 14.3. Nested associations cần fetch riêng

Nếu `OrderLine` có `Product product` LAZY và DTO cần Product.name, chỉ fetch `o.lines` chưa chắc Product đã tải. Phải xác định tất cả paths mà mapper truy cập.

## 15. DTO chi tiết bằng hai query projection

Một cách khác là không materialize PurchaseOrder entity.

Header DTO:

~~~java
public record OrderHeaderView(
    Long id,
    String orderNumber,
    OrderStatus status,
    BigDecimal totalAmount,
    String customerName
) {}
~~~

Query header:

~~~java
OrderHeaderView header = em.createQuery(
    """
    SELECT new com.example.shop.read.OrderHeaderView(
        o.id, o.orderNumber, o.status,
        o.totalAmount, c.displayName
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.id = :id
      AND o.tenantId = :tenantId
    """,
    OrderHeaderView.class
)
.setParameter("id", orderId)
.setParameter("tenantId", tenantId)
.getSingleResult();
~~~

Query Lines:

~~~java
List<OrderLineView> lines = em.createQuery(
    """
    SELECT new com.example.shop.read.OrderLineView(
        l.id, l.productSku, l.quantity, l.unitPrice
    )
    FROM OrderLine l
    WHERE l.order.id = :orderId
      AND l.order.tenantId = :tenantId
    ORDER BY l.id
    """,
    OrderLineView.class
)
.setParameter("orderId", orderId)
.setParameter("tenantId", tenantId)
.getResultList();
~~~

Ghép:

~~~java
OrderDetailsView details = new OrderDetailsView(
    header.id(),
    header.orderNumber(),
    header.status(),
    header.totalAmount(),
    header.customerName(),
    List.copyOf(lines)
);
~~~

### 15.1. Ưu điểm

- Chỉ lấy các cột cần thiết.
- Không tạo managed entity cho một màn hình chỉ đọc.
- Không có lazy collection trong DTO.
- Không nhân các cột parent theo số Lines như flat JOIN.
- Có thể giới hạn hoặc phân trang Lines riêng nếu cần.

### 15.2. Nhược điểm

- Hai lần round trip DB thay vì một.
- Code phải ghép hai phần dữ liệu.
- Hai SELECT có thể thấy state khác nhau nếu có concurrent writes tùy isolation.
- Cần xử lý không tìm thấy header hoặc không có Line.

Không có bảo đảm “hai query luôn chậm hơn một query JOIN”; SQL join có thể chuyển nhiều dữ liệu lặp. Hãy đo theo workload.

## 16. Vì sao SELECT JOIN to-many không tự tạo nested DTO?

Giả sử một Order có ba Lines:

~~~text
Order 101 | Line 501
Order 101 | Line 502
Order 101 | Line 503
~~~

Một query:

~~~jpql
SELECT o.id, o.orderNumber, l.id, l.productSku
FROM PurchaseOrder o
LEFT JOIN o.lines l
WHERE o.id = :id
~~~

trả ba SQL/result rows. JPQL constructor expression tạo một result tương ứng mỗi row, **không tự group** thành một `OrderDetailsView` chứa `List<OrderLineView>`.

Có thể:

1. Fetch entity graph và map collection trong service.
2. Dùng header DTO + lines DTO query rồi ghép.
3. Lấy flat DTO rows rồi group theo orderId ở Java.

Nếu dùng cách 3, phải xử lý parent lặp lại, dòng NULL khi không có child, và ordering.

## 17. Phân trang: Không load all rồi cắt trong Java

Không nên dùng:

~~~java
List<PurchaseOrder> all = repository.findAll();

List<OrderListItem> pageItems = all.stream()
    .skip((long) page * size)
    .limit(size)
    .map(this::toDto)
    .toList();
~~~

với bảng lớn, vì:

- `findAll()` có thể tải toàn bộ Orders.
- Nhiều managed entities chiếm memory.
- Mapper có thể tạo N+1.
- Database không giới hạn rows; Java chỉ cắt sau khi data đã tải.
- Trật tự SQL có thể không ổn định.
- User có thể yêu cầu trang có offset rất lớn.

**Đưa limit/offset hoặc keyset vào truy vấn database thay vì paging toàn bộ List trong memory.**

## 18. JPA thuần: DTO projection có OFFSET pagination

~~~java
public List<OrderListItem> pageOrders(
        EntityManager em,
        long tenantId,
        int page,
        int size) {

    if (page < 0 || size < 1 || size > 100) {
        throw new IllegalArgumentException(
            "Invalid pagination"
        );
    }

    int offset = Math.multiplyExact(page, size);

    TypedQuery<OrderListItem> query = em.createQuery(
        """
        SELECT new com.example.shop.read.OrderListItem(
            o.id, o.orderNumber, o.status, o.totalAmount,
            c.displayName, o.createdAt
        )
        FROM PurchaseOrder o
        JOIN o.customer c
        WHERE o.tenantId = :tenantId
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        OrderListItem.class
    );

    return query
        .setParameter("tenantId", tenantId)
        .setFirstResult(offset)
        .setMaxResults(size)
        .getResultList();
}
~~~

### 18.1. Chú ý offset và size

- Page index trong ví dụ là 0-based.
- `setFirstResult` nhận số rows bỏ qua.
- `setMaxResults` giới hạn số rows.
- `Math.multiplyExact` phát hiện tràn `int` khi tính offset.
- Giới hạn page size để bảo vệ memory và DB.

### 18.2. ORDER BY ổn định

~~~jpql
ORDER BY o.createdAt DESC, o.id DESC
~~~

Nếu chỉ sort theo createdAt, nhiều Order có thể cùng timestamp và thứ tự giữa chúng không được xác định. Dùng ID làm tie-breaker giúp paging ổn định hơn với dữ liệu không thay đổi.

Concurrent insert/update vẫn có thể làm các trang offset dịch chuyển. Không nên hứa offset pagination bảo đảm snapshot đồng nhất qua nhiều request.

### 18.3. Whitelist sort field

Không nối tên field tùy ý do client gửi vào JPQL:

~~~java
"ORDER BY o." + requestedField
~~~

Nên map một enum phía server vào những thuộc tính được phép. `setParameter` không dùng để bind tên field hoặc keyword ASC/DESC.

## 19. COUNT query và tổng số trang

Nếu UI hiển thị:

~~~text
Trang 1/618
Tổng 12.345 đơn hàng
~~~

cần một query COUNT tương ứng bộ lọc.

~~~java
Long total = em.createQuery(
    """
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
    """,
    Long.class
)
.setParameter("tenantId", tenantId)
.getSingleResult();
~~~

**Data query và count query phải dùng cùng semantics filter và authorization scope.** Nếu data query chỉ đọc tenant 7 mà COUNT đếm toàn hệ thống, vừa sai UI vừa có thể lộ thông tin tenant khác.

### 19.1. COUNT với to-many JOIN

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.productSku = :sku
~~~

có thể đếm trùng một Order nếu có hai Lines cùng SKU. Nếu cần số Order duy nhất:

~~~jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.productSku = :sku
~~~

Hoặc dùng EXISTS:

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.productSku = :sku
)
~~~

### 19.2. COUNT query không nên fetch collection

Nếu query data có fetch join, count query không cần/có thể không được phép fetch association khi result là Long. Tách filter logic khỏi selection/fetch/pagination.

### 19.3. COUNT có thể tốn chi phí lớn

Trên bảng nhiều triệu rows, exact COUNT với filter phức tạp có thể chậm. Nếu UI chỉ cần biết còn trang tiếp không, có thể dùng Slice thay vì Page.

## 20. Page và Slice trong Spring Data

`Page<T>`, `Slice<T>` và `Pageable` thuộc **Spring Data**, không phải API JPA chuẩn.

| Kiểu | Nội dung | Khi dùng |
|---|---|---|
| `List<T>` | Các phần tử | Không cần metadata trang |
| `Page<T>` | Content + totalElements/totalPages + metadata | UI có số trang |
| `Slice<T>` | Content + có trang kế tiếp hay không | Infinite scroll |
| `Window<T>` | Window/scrolling abstraction tùy Spring Data version | Cursor/keyset |
| DTO chunk | Dữ liệu theo batch nhỏ | Export hoặc batch read |

### 20.1. Page cần tổng số

Spring Data có thể thực hiện COUNT hoặc tối ưu nó trong một số tình huống; không nên giả định mỗi Page luôn đúng hai SQL mà chưa xem implementation/query.

### 20.2. Slice có thể tránh COUNT

Một phương pháp thông thường để xác định `hasNext` là đọc `size + 1` phần tử, rồi trả tối đa `size`. Cách Spring Data thực thi có thể thay đổi theo repository/query method.

### 20.3. Chọn theo UI contract, không theo mặc định framework

Nếu ứng dụng chỉ có nút “Load more”, COUNT tổng có thể không cần. Nếu user cần đi thẳng tới trang 20 và xem tổng số, Page thường phù hợp.

## 21. Spring Data: Page DTO với JPQL @Query

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            SELECT new com.example.shop.read.OrderListItem(
                o.id,
                o.orderNumber,
                o.status,
                o.totalAmount,
                c.displayName,
                o.createdAt
            )
            FROM PurchaseOrder o
            JOIN o.customer c
            WHERE o.tenantId = :tenantId
            """,
        countQuery = """
            SELECT COUNT(o)
            FROM PurchaseOrder o
            WHERE o.tenantId = :tenantId
            """
    )
    Page<OrderListItem> findListPage(
        @Param("tenantId") Long tenantId,
        Pageable pageable
    );
}
~~~

Service:

~~~java
public Page<OrderListItem> list(
        long authenticatedTenantId,
        int page,
        int size) {

    if (page < 0 || size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid page");
    }

    Pageable pageable = PageRequest.of(
        page,
        size,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        )
    );

    return repository.findListPage(
        authenticatedTenantId,
        pageable
    );
}
~~~

### 21.1. Vì sao khai báo countQuery?

Với custom JPQL constructor projection/JOIN, suy diễn count query của framework có thể gặp giới hạn. `countQuery` tường minh giúp giữ semantics rõ và dễ kiểm thử.

### 21.2. Sort của Pageable

Khi query custom kết hợp `Pageable.Sort`, cách framework bổ sung ORDER BY phụ thuộc Spring Data version/query syntax. Kiểm tra generated JPQL/SQL và whitelist fields.

Nếu query đã có ORDER BY cố định, có thể truyền PageRequest không có dynamic sort để tránh trùng hoặc xung đột.

### 21.3. Đừng dùng Page constructor DTO có JOIN to-many mà quên row multiplication

Spring Data không tự group các DTO rows thành parents có List children. Nếu query tạo một DTO cho mỗi Line, trang đo theo query rows. Đây là vấn đề cardinality, không được giải quyết chỉ bằng return type `Page<DTO>`.

## 22. Spring Data interface projection

Một interface projection:

~~~java
public interface OrderSummaryProjection {
    Long getId();
    String getOrderNumber();
    BigDecimal getTotalAmount();
    String getCustomerName();
}
~~~

Repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT
            o.id AS id,
            o.orderNumber AS orderNumber,
            o.totalAmount AS totalAmount,
            c.displayName AS customerName
        FROM PurchaseOrder o
        JOIN o.customer c
        WHERE o.tenantId = :tenantId
        ORDER BY o.createdAt DESC, o.id DESC
        """)
    List<OrderSummaryProjection> findSummaries(
        @Param("tenantId") Long tenantId
    );
}
~~~

Spring Data có thể tạo proxy implement projection interface theo alias/tuple data, tùy implementation.

### 22.1. Lợi ích

- Getter là contract đọc.
- Không cần constructor DTO cho tập scalar đơn giản.
- Có thể kết hợp Spring Data pagination khi phù hợp.
- Closed projection đôi khi giúp framework tối ưu fields.

### 22.2. Cần chú ý

- Alias phải tương ứng getter/property.
- Nested projection có thể khiến provider JOIN/load nhiều dữ liệu hơn dự kiến.
- Open projection dùng SpEL/computed getters có thể hạn chế column pruning.
- Dynamic projections và query rewriting phụ thuộc Spring Data version.
- Projection interface không tự biến mọi nested entity thành value DTO thuần.

Đừng mặc định interface projection luôn nhanh hơn record DTO. Xem SQL thực tế.

## 23. Nested projection và DTO có collection

Ví dụ:

~~~java
public interface OrderWithCustomerProjection {
    Long getId();
    CustomerNameProjection getCustomer();
}

public interface CustomerNameProjection {
    String getDisplayName();
}
~~~

Nested projection tiện nhưng query execution phụ thuộc provider/framework. Nếu cần tối ưu nghiêm ngặt, một DTO phẳng có `customerName` và JPQL rõ ràng dễ phân tích hơn.

Đặc biệt tránh:

~~~java
public interface OrderBadProjection {
    List<OrderLine> getLines();
}
~~~

vì có thể còn phụ thuộc entity/persistent collection. Chỉ đổi interface không bảo đảm tầng API đã tách hoàn toàn khỏi JPA.

## 24. Phân trang parent có to-many children

Giả sử UI cần 20 Orders, **mỗi Order có danh sách Lines**.

Một query:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.tenantId = :tenantId
ORDER BY o.createdAt DESC, o.id DESC
~~~

kết hợp `setMaxResults(20)` có rủi ro:

- SQL JOIN nhân bản parent row theo số Lines.
- Database limit SQL rows không đồng nghĩa limit 20 Order roots.
- Provider có thể cần pagination trong memory hoặc cảnh báo.
- JOIN collection rộng có thể truyền lượng dữ liệu rất lớn.
- DISTINCT không tự giải quyết mọi vấn đề paging.

### 24.1. Chiến lược Page IDs trước

Bước 1: chọn đúng root IDs trong trang.

~~~java
List<Long> ids = em.createQuery(
    """
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    Long.class
)
.setParameter("tenantId", tenantId)
.setFirstResult(Math.multiplyExact(page, size))
.setMaxResults(size)
.getResultList();
~~~

Nếu `ids` rỗng, có thể trả trang rỗng.

### 24.2. Bước 2: Header DTO theo tập IDs

~~~java
List<OrderListItem> headers = em.createQuery(
    """
    SELECT new com.example.shop.read.OrderListItem(
        o.id, o.orderNumber, o.status, o.totalAmount,
        c.displayName, o.createdAt
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.tenantId = :tenantId
      AND o.id IN :ids
    """,
    OrderListItem.class
)
.setParameter("tenantId", tenantId)
.setParameter("ids", ids)
.getResultList();
~~~

### 24.3. Bước 3: Lines của tất cả IDs trong một query

DTO:

~~~java
public record OrderLineRow(
    Long orderId,
    Long lineId,
    String productSku,
    int quantity
) {}
~~~

Query:

~~~java
List<OrderLineRow> lineRows = em.createQuery(
    """
    SELECT new com.example.shop.read.OrderLineRow(
        o.id, l.id, l.productSku, l.quantity
    )
    FROM OrderLine l
    JOIN l.order o
    WHERE o.tenantId = :tenantId
      AND o.id IN :ids
    ORDER BY o.id, l.id
    """,
    OrderLineRow.class
)
.setParameter("tenantId", tenantId)
.setParameter("ids", ids)
.getResultList();
~~~

### 24.4. Bước 4: Group và giữ thứ tự trang

~~~java
Map<Long, List<OrderLineRow>> linesByOrder =
    lineRows.stream().collect(
        Collectors.groupingBy(
            OrderLineRow::orderId
        )
    );

Map<Long, OrderListItem> headerById =
    headers.stream().collect(
        Collectors.toMap(
            OrderListItem::id,
            Function.identity()
        )
    );

List<OrderPageItem> items = ids.stream()
    .filter(headerById::containsKey)
    .map(id -> new OrderPageItem(
        headerById.get(id),
        List.copyOf(
            linesByOrder.getOrDefault(id, List.of())
        )
    ))
    .toList();
~~~

Wrapper:

~~~java
public record OrderPageItem(
    OrderListItem header,
    List<OrderLineRow> lines
) {}
~~~

### 24.5. Vì sao phải khôi phục thứ tự?

`WHERE o.id IN :ids` không bảo đảm database trả rows theo thứ tự trong list `ids`. Thứ tự page được xác định từ query IDs; code cần dùng nó để sắp lại headers/children.

### 24.6. Trường hợp concurrent delete/update

Một Order được chọn ở bước IDs có thể bị xóa hoặc thay đổi trước khi query headers. Cách `filter(headerById::containsKey)` minh họa policy bỏ Order biến mất; hệ thống có thể chọn retry hoặc snapshot transaction nếu cần consistency chặt.

### 24.7. Không tải collection vô hạn

Nếu mỗi Order có hàng chục nghìn Lines, kể cả query batch có thể rất lớn. UI có thể chỉ cần số Lines hoặc 5 Lines gần nhất; hãy thiết kế contract và pagination children riêng.

## 25. Khi chỉ cần số lượng children: Đừng tải collection

Màn hình danh sách chỉ hiển thị:

~~~text
Order | Tổng tiền | Số Lines
~~~

Có thể query aggregate:

~~~java
public record OrderLineCountView(
    Long id,
    String orderNumber,
    Long lineCount
) {}
~~~

~~~java
List<OrderLineCountView> rows = em.createQuery(
    """
    SELECT new com.example.shop.read.OrderLineCountView(
        o.id, o.orderNumber, COUNT(l)
    )
    FROM PurchaseOrder o
    LEFT JOIN o.lines l
    WHERE o.tenantId = :tenantId
    GROUP BY o.id, o.orderNumber
    ORDER BY o.id DESC
    """,
    OrderLineCountView.class
)
.setParameter("tenantId", tenantId)
.setMaxResults(20)
.getResultList();
~~~

`COUNT(l)` tính trên database và trả Long. Không cần load từng OrderLine chỉ để gọi `lines.size()`.

### 25.1. JOIN nhiều collections có thể làm count sai

Nếu JOIN thêm Payments, mỗi Line có thể bị nhân bởi số Payments. Khi đó `COUNT(l)` có thể đếm trùng; cân nhắc COUNT DISTINCT, subquery hoặc aggregate query riêng.

### 25.2. GROUP BY và phân trang

Một page query GROUP BY cần COUNT phù hợp để tính tổng số **nhóm Order**, không phải tổng số rows sau JOIN. Đừng dùng `COUNT(*)` ở query khác rồi suy ra totalGroups nếu semantics không khớp.

## 26. OFFSET và keyset pagination

DTO projection không bắt buộc phải đi với OFFSET. Có thể dùng keyset/cursor nếu truy vấn cần duyệt sâu.

### 26.1. OFFSET

SQL minh họa:

~~~sql
SELECT ...
FROM purchase_order
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
~~~

Database có thể cần bỏ qua rất nhiều row để lấy 20 row cuối, tùy index/plan.

### 26.2. Keyset với sort giảm dần

Giả sử cursor cuối trang trước:

~~~text
createdAt = 2026-11-01T10:00:00Z
id = 500
~~~

JPQL trang tiếp:

~~~jpql
SELECT new com.example.shop.read.OrderListItem(
    o.id, o.orderNumber, o.status, o.totalAmount,
    c.displayName, o.createdAt
)
FROM PurchaseOrder o
JOIN o.customer c
WHERE o.tenantId = :tenantId
  AND (
      o.createdAt < :cursorTime
      OR (
          o.createdAt = :cursorTime
          AND o.id < :cursorId
      )
  )
ORDER BY o.createdAt DESC, o.id DESC
~~~

Binding:

~~~java
query.setParameter("tenantId", tenantId);
query.setParameter("cursorTime", cursorTime);
query.setParameter("cursorId", cursorId);
query.setMaxResults(size);
~~~

### 26.3. Lợi ích và giới hạn

- Có thể tránh OFFSET sâu.
- Yêu cầu sort deterministic với khóa tie-breaker duy nhất.
- Cursor phải chứa đủ sort keys.
- Nếu sort theo nhiều field/NULL/ASC-DESC hỗn hợp, điều kiện cursor phức tạp hơn.
- Concurrent updates của sort fields có thể khiến item chuyển vị trí.
- Không thuận tiện để “nhảy ngay tới trang 250” nếu không có anchor tương ứng.
- Index phải hỗ trợ filter/order.
- Cursor không được thay quyền truy cập server-side.

Keyset và DTO là hai chiều thiết kế khác nhau: keyset chọn **nhóm rows**, DTO chọn **hình dạng kết quả**.

## 27. Read-only transaction và DTO

Trong Spring:

~~~java
@Transactional(readOnly = true)
public List<OrderListItem> listOrders(...) {
    // Query projection
}
~~~

`readOnly = true` là gợi ý/cấu hình transaction của framework, với tác dụng tối ưu tùy provider. Nó không tự biến entity thành DTO và không phải rào bảo mật thay thế quyền ghi của database.

### 27.1. Entity trong transaction read-only vẫn là entity

Nếu query trả PurchaseOrder, nó vẫn có mapping, identity và lazy associations; tùy provider, read-only có thể giảm dirty-checking overhead nhưng không biến nó thành value object.

### 27.2. DTO sau khi materialize thường không cần context

Nếu service trả record chỉ chứa String, BigDecimal, Instant và List DTO đã khởi tạo, controller có thể serialize sau transaction mà không cần tải thêm dữ liệu.

### 27.3. Transaction và consistency của nhiều SELECT

Nếu detail DTO được dựng từ hai SQL, chúng có thể nhìn thấy dữ liệu ở hai thời điểm khác nhau dưới một số isolation levels. DTO không bảo đảm snapshot consistency. Với nghiệp vụ yêu cầu snapshot chặt, phải thiết kế transaction/isolation thích hợp.

## 28. First-level cache, second-level cache và memory

Managed entity thường được persistence context theo dõi để hỗ trợ identity map, dirty checking và lazy associations. Nếu giữ hàng trăm nghìn entity trong một transaction, memory có thể tăng đáng kể.

DTO projection thường không cần persistence-context metadata cho từng entity result. Nhưng một `List` chứa hàng triệu DTO vẫn tiêu tốn nhiều RAM.

### 28.1. Khi cache làm entity có lợi

Nếu entity đã managed trong current context, `em.find` lại cùng ID có thể không tạo SELECT mới. Với command logic cần cùng identity, đây là lợi ích quan trọng.

### 28.2. Không so sánh hiệu năng chỉ trên cache warm

Một benchmark entity query khi cache warm với DTO query khi cache cold là không công bằng. Cần đo nhiều tình huống và xem SQL/objects thật.

### 28.3. Second-level cache khác query cache

Second-level entity cache có thể hỗ trợ entity reads nếu provider được cấu hình. DTO result có thể được cache qua các cơ chế query cache riêng hoặc application cache, nhưng không tự là entity entry trong persistence cache. Hành vi cụ thể phụ thuộc provider.

## 29. Bảo mật khi thiết kế DTO và entity output

Customer có thể chứa email, số điện thoại, địa chỉ, ghi chú nội bộ hoặc thông tin compliance. Màn hình danh sách Order chỉ cần tên.

Nếu trả nguyên Customer entity và JSON serializer duyệt toàn bộ getter, API có thể vô tình trả dữ liệu ngoài contract khi mapping thay đổi.

Một DTO:

~~~java
public record CustomerDisplayView(
    Long id,
    String displayName
) {}
~~~

giới hạn field được gửi.

### 29.1. Projection không tự thay authorization

Query DTO vẫn phải lọc:

~~~jpql
WHERE o.tenantId = :authenticatedTenantId
~~~

Tenant ID phải đến từ security context server-side, không phải một ID do client tự tuyên bố.

### 29.2. COUNT cũng là thông tin nhạy cảm

Nếu data query trả Orders của tenant hiện tại nhưng COUNT query đếm toàn hệ thống, totalElements có thể làm lộ thống kê của tenant khác. Áp dụng cùng permission scope cho data/count/child queries.

### 29.3. API DTO cần versioning có chủ đích

Thay đổi entity field không nên tự động làm đổi JSON. DTO tạo ranh giới giúp kiểm soát compatibility khi API có nhiều client.

## 30. DTO snapshot không phải trạng thái authoritative để cập nhật

Một DTO đọc từ database là **ảnh chụp tại thời điểm truy vấn**.

~~~java
public record InventoryView(
    Long productId,
    int availableQuantity,
    Instant observedAt
) {}
~~~

Nếu user nhìn thấy availableQuantity=5, điều đó không bảo đảm 5 sản phẩm còn tồn khi user đặt hàng sau 10 giây.

Command service phải tái kiểm tra invariant dưới transaction/locking phù hợp.

### 30.1. Read model và write model có thể khác

Một ứng dụng có thể dùng:

~~~text
GET /orders      -> DTO projection/page
GET /orders/{id} -> OrderDetailsView
POST /orders/{id}/pay -> load managed PurchaseOrder
~~~

Đây là một cách tách read/write responsibilities. Không nhất thiết phải triển khai event sourcing hay CQRS phức tạp để dùng DTO cho queries.

### 30.2. Không map ngược DTO một cách mù quáng

Nếu client gửi DTO chỉ có ID và status, copy mọi field còn thiếu thành null lên entity managed có thể làm mất dữ liệu. Command DTO nên mô tả **ý định** (`ConfirmPaymentCommand`, `ChangeShippingAddressCommand`), không phải snapshot entity thiếu field.

## 31. Native SQL báo cáo vẫn nên trả DTO

Một báo cáo có thể cần SQL đặc thù:

~~~sql
SELECT
    o.status AS status,
    COUNT(*) AS order_count,
    SUM(o.total_amount) AS total_amount
FROM purchase_order o
WHERE o.tenant_id = ?
GROUP BY o.status
ORDER BY o.status;
~~~

DTO:

~~~java
public record OrderStatusReport(
    String status,
    long orderCount,
    BigDecimal totalAmount
) {}
~~~

Có thể map từ `Object[]`, `Tuple`/provider mapping hoặc `@SqlResultSetMapping` với `@ConstructorResult`.

~~~java
List<OrderStatusReport> reports = new ArrayList<>();

for (Object result : nativeQuery.getResultList()) {
    Object[] row = (Object[]) result;

    reports.add(new OrderStatusReport(
        (String) row[0],
        ((Number) row[1]).longValue(),
        (BigDecimal) row[2]
    ));
}
~~~

Kiểu numeric do native SQL/JDBC trả có thể phụ thuộc driver/provider, nên cần xác minh trước khi cast cứng.

**Không tạo một entity giả cho kết quả GROUP BY chỉ để có một class return type.** DTO/aggregate result phù hợp hơn.

## 32. Export lớn: DTO theo chunk, không giữ mọi entity

Giả sử cần xuất một triệu Orders ra CSV. Load mọi entity trong một `List` rồi render là cách dễ tăng memory.

Thiết kế thường phù hợp:

1. Chọn đúng cột export bằng projection.
2. Đọc theo batch nhỏ.
3. Ghi từng batch ra output.
4. Không giữ toàn bộ batch cũ trong RAM.
5. Sử dụng keyset theo ID hoặc cursor phù hợp.
6. Quản lý transaction/connection/stream lifecycle.
7. Chọn consistency policy cho dữ liệu thay đổi đồng thời.

DTO:

~~~java
public record OrderExportRow(
    Long id,
    String orderNumber,
    BigDecimal totalAmount
) {}
~~~

Đọc theo keyset:

~~~java
Long lastId = 0L;
int batchSize = 500;

while (true) {

    List<OrderExportRow> batch = em.createQuery(
        """
        SELECT new com.example.shop.read.OrderExportRow(
            o.id, o.orderNumber, o.totalAmount
        )
        FROM PurchaseOrder o
        WHERE o.tenantId = :tenantId
          AND o.id > :lastId
        ORDER BY o.id ASC
        """,
        OrderExportRow.class
    )
    .setParameter("tenantId", tenantId)
    .setParameter("lastId", lastId)
    .setMaxResults(batchSize)
    .getResultList();

    if (batch.isEmpty()) {
        break;
    }

    for (OrderExportRow row : batch) {
        csvWriter.write(row);
    }

    lastId = batch.get(batch.size() - 1).id();
}
~~~

Đây là pseudocode cho workflow; application phải xác định transaction boundary và checkpoint. Nếu dữ liệu được insert/delete trong lúc export, tập kết quả có thể biến động; snapshot consistency phải được thiết kế khi cần.

### 32.1. Stream chưa chắc là cursor thật

`getResultStream()` có thể được provider triển khai theo nhiều cách. Không mặc định mọi stream đều không giữ toàn bộ dữ liệu hoặc tự đóng ResultSet đúng lúc. Tránh trả stream phụ thuộc EntityManager ra khỏi scope transaction.

### 32.2. DTO không giải quyết memory nếu vẫn tích lũy mọi DTO

Projection giảm độ rộng/result management overhead; **chunking** mới giúp tránh giữ một triệu result objects trong RAM.

## 33. Kiểm thử việc chọn entity hoặc DTO

Test nên xác minh cả semantics lẫn query behavior.

### 33.1. Fixture

~~~text
Tenant 7:
  Order 101: Customer A, 2 Lines, total 200000
  Order 102: Customer B, 0 Lines, total 300000
  Order 103: Customer A, 4 Lines, total 500000

Tenant 8:
  Order 201: Customer C, 1 Line, total 900000
~~~

### 33.2. Test danh sách DTO

- Có đúng fields và types không?
- Có lọc tenant 8 ra khỏi list tenant 7 không?
- Thứ tự theo createdAt DESC, id DESC có đúng không?
- Page size 2 trả không quá 2 root Orders?
- COUNT chỉ tính tenant 7?
- Có lộ Customer.email không?

### 33.3. Test chi tiết

- Order 101 có đúng 2 Lines?
- Order 102 có List Lines rỗng?
- Header/child joins không làm mất parent không có Lines?
- Sai tenant/ID được xử lý theo security contract?
- DTO sau khi service trả về có thể đọc mà không cần persistence context?

### 33.4. Test ngoài transaction service

Nếu test method tự có `@Transactional` bao trùm cả bước serialize, nó có thể che lỗi lazy xuất hiện ở production. Test HTTP hoặc service boundary với transaction thật sự kết thúc và OSIV theo cấu hình production.

### 33.5. Test N+1

Với Hibernate có thể dùng statistics/log SQL trong integration test. Đọc 1, 20 và 100 Orders để xem số SQL tăng như thế nào. Đừng chỉ assert JSON đúng trên fixture 1 Order.

### 33.6. Test count duplicate

Một Order có hai Lines cùng SKU. Nếu lọc theo SKU, totalElements phải là 1 Order chứ không phải 2 SQL JOIN rows.

### 33.7. Test entity command và version

Sau khi gọi `confirmPayment`, commit rồi đọc bằng EntityManager mới. Test rằng status đúng và optimistic locking phát hiện phiên bản stale theo contract provider.

### 33.8. Test database mục tiêu

H2 có thể khác PostgreSQL/MySQL/Oracle về kiểu thời gian, SQL pagination, NULL ordering, collation, plan và constraint. Query quan trọng nên được kiểm tra trên DB/dialect thực hoặc gần tương đương.

## 34. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| API trả entity rồi lỗi LazyInitializationException | Serializer đọc LAZY sau context | Dựng DTO trong service và fetch đúng |
| Đổi response sang DTO nhưng query vẫn chậm | Vẫn query entity graph lớn rồi map | Projection trực tiếp |
| 100 Orders phát sinh 101 SELECT | N+1 lazy Customer | JOIN/projection/fetch to-one |
| Page<Entity> JSON quá lớn | Serializer duyệt relations | Page DTO |
| Page to-many mất/thừa Order | JOIN FETCH collection với OFFSET | Page IDs rồi fetch/group children |
| COUNT lớn hơn số Order | JOIN to-many nhân root | DISTINCT/EXISTS |
| DTO constructor lỗi | FQN/constructor arg type/order sai | Đồng bộ SELECT và DTO |
| Interface projection field null | Alias/getter mismatch | Kiểm tra aliases/framework |
| DTO chứa entity | Chưa tách lazy context | Chỉ chứa value/DTO con |
| Thay đổi DTO không cập nhật database | DTO không managed | Command + entity managed |
| `@Transactional` service vẫn lazy error | Mapping/serialization chạy sau return | Map trong boundary |
| Spring test pass nhưng production lỗi | Test giữ transaction hoặc OSIV mở | Test ngoài boundary |
| OFFSET sâu chậm | DB bỏ qua nhiều rows | Keyset/cursor |
| Sort page không ổn định | Không có unique tie-breaker | ORDER BY field, id |
| DTO lộ dữ liệu tenant khác | Query thiếu permission predicate | Scope data/count/children |
| Export dùng quá nhiều heap | Load tất cả rows một lúc | DTO chunk/keyset |
| Aggregate DTO đọc sai COUNT | JOIN lặp hoặc type mapping | COUNT DISTINCT và kiểm tra result types |
| EntityGraph vẫn nhiều SELECT | Provider fetch strategy khác kỳ vọng | Quan sát SQL |
| Read-only transaction vẫn trả entity | Read-only không biến thành DTO | Tách output contract |
| UI cần số Lines nhưng query tải Lines | Dùng collection thay COUNT | Aggregate DTO |
| Client gửi DTO cũ rồi ghi đè dữ liệu | Không check version/invariant | Managed command và concurrency |

## 35. Bài tập thực hành

### Bài 1. Danh sách Customer

Cần trả 50 Customer, mỗi người chỉ có ID và displayName.

**Câu hỏi:** Entity hay DTO?

**Đáp án:** DTO projection thường hợp lý; không cần tải email hoặc managed state.

### Bài 2. Thanh toán Order

Service phải đổi status từ PENDING sang PAID và dùng `@Version`.

**Đáp án:** Managed entity với transaction và domain method thường phù hợp; DTO read không tự dirty check.

### Bài 3. Entity sang DTO sau findAll

~~~java
repository.findAll().stream()
    .map(this::toDto)
    .toList();
~~~

**Câu hỏi:** Có chắc ít SQL và memory không?

**Đáp án:** Không; đã load toàn bộ entities, mapper có thể phát sinh N+1 và không có DB pagination.

### Bài 4. Constructor expression

~~~jpql
SELECT new com.example.shop.read.OrderListItem(...)
FROM PurchaseOrder o
~~~

**Câu hỏi:** Result có managed PurchaseOrder không?

**Đáp án:** Không; result là DTO constructor instances, không được JPA dirty check.

### Bài 5. COUNT sai tenant

Data query lọc `tenantId=7` nhưng COUNT không lọc tenant.

**Đáp án:** Sai số trang và có nguy cơ lộ thống kê tenant khác. Count phải áp dụng cùng authorization scope.

### Bài 6. N+1

100 Order entities đọc Customer.name trong vòng lặp.

**Đáp án:** Có thể tạo 1+N SQL. Dùng projection JOIN hoặc fetch to-one phù hợp.

### Bài 7. Lazy ở controller

Service trả Order entity, serializer đọc `getLines()` sau khi context đóng.

**Đáp án:** Có thể ném Hibernate LazyInitializationException. Dựng DTO trong service, tải dữ liệu trước boundary.

### Bài 8. To-many projection

JOIN OrderLine tạo 5 rows cho một Order. Có tự tạo DTO chứa List 5 Lines không?

**Đáp án:** Không. Cần group results hoặc query header/lines riêng, hoặc entity fetch + mapper.

### Bài 9. Fetch join + Page

Dùng `LEFT JOIN FETCH o.lines` cùng `setMaxResults(20)`.

**Đáp án:** Có rủi ro pagination trên rows thay vì Order roots. Page IDs rồi load children là một hướng.

### Bài 10. Page và Slice

Infinite scroll chỉ cần biết có trang kế.

**Đáp án:** Slice hoặc lấy `size+1` rows có thể tránh COUNT chính xác; Page nếu cần total.

### Bài 11. Tie-breaker

Hai Order cùng createdAt.

**Đáp án:** Sort thêm ID để có thứ tự deterministic: `ORDER BY createdAt DESC, id DESC`.

### Bài 12. Keyset

Cần duyệt một triệu Orders nhưng OFFSET quá sâu.

**Đáp án:** Cursor gồm createdAt và ID, WHERE đứng sau cursor theo order phù hợp, index tương ứng.

### Bài 13. Interface projection

`getCustomerName()` luôn null.

**Đáp án:** Kiểm tra SQL/JPQL alias `customerName`, getter và Spring Data version.

### Bài 14. DTO bọc entity

~~~java
public record OrderDto(PurchaseOrder order) {}
~~~

**Đáp án:** Chưa tách JPA; entity/proxy vẫn bị serializer truy cập. Dùng value/child DTO fields.

### Bài 15. Export 2 triệu Orders

**Đáp án:** DTO projection theo chunk/keyset và ghi tuần tự, không load toàn bộ entities/DTOs vào List.

### Bài 16. Optimistic version

Client đọc version=4, DB đã lên version=5.

**Đáp án:** Command phải kiểm tra state/version trong transaction và để JPA optimistic locking hoặc conditional update bảo vệ, không tin DTO snapshot cũ.

### Bài 17. Security

DTO chỉ có vài field nhưng query thiếu tenant filter.

**Đáp án:** DTO không phải authorization. Scope từ server phải có ở mọi data/count/child query.

### Bài 18. Aggregate

UI chỉ cần số Lines.

**Đáp án:** COUNT/aggregate projection có thể tốt hơn tải `List<OrderLine>`.

### Bài 19. Read-only

`@Transactional(readOnly=true)` có biến entity thành DTO không?

**Đáp án:** Không. Nó cấu hình transaction/framework, không loại bỏ mapping và lazy associations.

### Bài 20. Hai SELECT detail

Header và Lines đọc bằng hai query.

**Đáp án:** Có thể thêm round trip và thấy snapshot khác nhau dưới một số isolation levels; cần chọn consistency contract phù hợp.

## 36. Quy trình ra quyết định

### Bước 1. Xác định hành động sau khi đọc

Có cần sửa database bằng domain method? Nếu có, managed entity thường phù hợp. Nếu chỉ trình bày, bắt đầu từ projection DTO.

### Bước 2. Viết output contract

Liệt kê chính xác các field mà UI/API/report cần. Không chọn toàn bộ graph theo thói quen.

### Bước 3. Xác định cardinality

- Một root hay nhiều roots?
- Có to-one associations?
- Có to-many collections?
- Có nhiều collections đồng thời?
- Query GROUP BY/aggregate?
- Có bao nhiêu rows trong trường hợp xấu?

### Bước 4. Chọn hình dạng truy vấn

- Managed entity + fetch plan cho command.
- JPQL/Criteria DTO constructor cho danh sách.
- Detail DTO từ entity graph hoặc hai projection queries.
- Aggregate DTO/COUNT/SUM cho báo cáo.
- Chunk/keyset DTO cho export.

### Bước 5. Chọn pagination

- OFFSET + stable sort khi phù hợp.
- Page nếu cần COUNT.
- Slice nếu chỉ cần next page.
- Keyset/cursor cho scrolling sâu/khối lượng lớn.
- Page IDs trước khi tải children to-many.

### Bước 6. Đặt transaction boundary

Mapping từ entity thực hiện trong service khi context còn thích hợp; đừng để controller/serializer tự lazy load.

### Bước 7. Áp dụng security

Tenant và authorization phải nằm trong query hoặc cơ chế được kiểm chứng tương đương, bao gồm COUNT và queries phụ.

### Bước 8. Kiểm thử correctness và performance

Đo SQL count, row width, latency, memory, N+1, COUNT duplicates, sort/paging boundary, và test DTO sau khi context đóng.

### Bước 9. Điều chỉnh khi yêu cầu thay đổi

Nếu UI cần thêm Customer.region hoặc số Lines, cập nhật DTO và query có chủ đích. Không bật EAGER toàn bộ chỉ để một màn hình mới chạy được.

## 37. Tổng kết

~~~text
                   YÊU CẦU ĐỌC DỮ LIỆU
                             |
                             v
             Sau khi đọc có sửa domain state?
                     /              \
                   Có              Không
                   |                 |
                   v                 v
              Managed entity      DTO / projection
              + domain method         |
              + @Version              |
              + transaction           v
                   |           Một root hay nhiều?
                   |              /         \
                   |         Một root        List
                   |            |             |
                   |            v             v
                   |        Detail DTO     Page/Slice DTO
                   |        + children     + stable sort
                   |        khi cần        + COUNT nếu cần
                   |            |             |
                   +------------+-------------+
                                |
                                v
                   Fetch/selection theo use case
                                |
                                v
                  Kiểm tra N+1, JOIN to-many,
                  boundary, tenant và pagination
                                |
                                v
                      Test SQL + dữ liệu thật
~~~

Những điểm cần ghi nhớ:

1. **Entity phù hợp khi cần managed state, domain methods, dirty checking và optimistic locking.**
2. **DTO projection phù hợp cho danh sách, API chỉ đọc và báo cáo chỉ cần một số cột.**
3. **Entity rồi map DTO không tương đương direct projection** về lượng dữ liệu được tải và N+1.
4. **Một DTO chỉ an toàn khỏi lazy access khi chứa dữ liệu thuần đã materialize**, không phải entity/proxy bọc bên trong.
5. **JOIN FETCH/EntityGraph phục vụ use case cần entity và association**, nhưng không phải lý do fetch tất cả.
6. **JOIN to-many có thể nhân SQL rows**; phân trang root cần chiến lược thích hợp, thường là page IDs rồi fetch/group children.
7. **COUNT phải theo cùng filter/authorization và đếm đúng root**, không nhầm JOIN rows.
8. **Page, Slice và keyset trả lời những yêu cầu UI khác nhau**; đừng tính COUNT đắt tiền nếu không cần.
9. **Sort ổn định cần tie-breaker duy nhất**, nhưng vẫn phải xét dữ liệu thay đổi đồng thời.
10. **Entity trực tiếp trong JSON API có rủi ro lazy, recursion và lộ field**, nên dùng DTO contract có chủ đích.
11. **Read-only transaction không biến entity thành DTO** và không thay thế authorization.
12. **Query read DTO và command managed entity có thể cùng tồn tại** trong một ứng dụng JPA.
13. **Đo SQL, number of rows, memory và latency thực tế**, không kết luận chỉ từ độ dài source code.
14. **Kiểm thử ngoài transaction/context của service**, đặc biệt với serializer và lazy associations.
15. **Thiết kế DTO theo nhu cầu đọc thật**, thay vì tạo một DTO khổng lồ có hàng chục field tùy chọn.

Kết luận: lựa chọn tốt nhất không phải “entity luôn tốt hơn DTO” hay ngược lại. **Hãy dùng entity cho hành vi và vòng đời JPA; dùng DTO/projection cho dữ liệu cần truyền/hiển thị; rồi kết hợp fetch plan, transaction và phân trang đúng với từng use case**.
