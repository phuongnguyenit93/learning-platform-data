# Thiết kế ranh giới tải dữ liệu trước khi chuyển sang DTO trong JPA

Trong các ứng dụng sử dụng **Jakarta Persistence (JPA)**, đọc một entity thành công **không đồng nghĩa** tất cả dữ liệu cần thiết đã được tải. Entity có thể chứa quan hệ `LAZY`; khi truy cập quan hệ đó, provider có thể thực hiện SQL bổ sung. Nếu truy cập sau khi persistence context đã đóng hoặc entity trở thành detached, ứng dụng có thể gặp lỗi không khởi tạo được dữ liệu.

Đây là lý do cần **thiết kế ranh giới tải dữ liệu trước khi chuyển sang DTO** (*data-loading boundary*). Ranh giới này xác định **phần dữ liệu nào cần đọc, cách đọc, thời điểm đọc và nơi hoàn tất việc chuyển entity thành đối tượng dữ liệu độc lập**.

Ví dụ, endpoint trả chi tiết đơn hàng cần:

~~~text
OrderDetailDto
  id, code, createdAt, totalAmount
  customer
    id, email
  lines[]
    id, productCode, quantity, unitPrice
~~~

Một lời gọi:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
~~~

không tự bảo đảm `order.getCustomer()` và `order.getLines()` đã được tải. Nếu DTO mapper được gọi sau khi đóng EntityManager, việc đọc các association chưa khởi tạo có thể thất bại.

Hướng thiết kế tốt:

~~~text
HTTP request
     |
     v
Application service [transaction / persistence context]
     |
     +-- Chọn hợp đồng DTO
     +-- Kiểm tra quyền truy cập
     +-- Thực thi truy vấn theo fetch plan
     +-- Hoàn tất ánh xạ thành DTO
     |
     v
DTO chỉ chứa dữ liệu độc lập
     |
     v
Serialization / caller [không cần EntityManager]
~~~

Bài thuộc chương **Kế hoạch tải**, chủ đề **Data Persistence Relational Access ORM JPA**. Nội dung giải thích quan hệ giữa persistence context, `LAZY`, `JOIN FETCH`, `EntityGraph`, DTO projection, N+1, phân trang collection, transaction, batch loading, bảo mật và kiểm thử SQL.

**Nguyên tắc trung tâm:** *DTO phải được hoàn thiện trước khi rời ranh giới persistence, nhưng chỉ tải những gì use case thật sự cần*.

---

## 1. Khái niệm ranh giới tải dữ liệu

Ranh giới tải dữ liệu là điểm trong kiến trúc nơi ứng dụng quyết định rõ:

1. **Dữ liệu đầu vào**: order ID, bộ lọc, user hiện hành, tenant, offset/limit.
2. **Dữ liệu đầu ra**: DTO có những trường scalar và association nào.
3. **Kế hoạch tải**: fetch join, entity graph, batch loading, DTO constructor projection hay nhiều query.
4. **Phạm vi quản lý**: transaction và persistence context nào được dùng.
5. **Thời điểm mapping**: entity → DTO phải hoàn tất trước khi rời phạm vi đã chọn.
6. **Tính độc lập**: sau khi trả DTO, controller và JSON serializer không cần JPA để đọc tiếp dữ liệu.

Ranh giới này **không đồng nghĩa** với việc chuyển mọi quan hệ sang `FetchType.EAGER`. EAGER là cấu hình chung trên mapping; mỗi endpoint lại có nhu cầu dữ liệu khác nhau.

### 1.1. Một entity, nhiều hợp đồng dữ liệu

| Nhu cầu | Dữ liệu cần | Chiến lược đáng cân nhắc |
| --- | --- | --- |
| Xem một đơn nhỏ | Order, Customer, Lines | Fetch join/EntityGraph, map trong transaction |
| Danh sách 20 đơn | ID, mã, trạng thái, ngày, email | Constructor DTO projection |
| Danh sách kèm số dòng | Order + COUNT(lines) | Aggregate/DTO projection |
| Trang đơn kèm toàn bộ lines | Parents theo trang, child theo tập ID | Hai giai đoạn và grouping |
| Report hàng trăm nghìn dòng | Một số scalar/aggregate | Projection, phân đoạn hoặc streaming có quản lý |
| Nghiệp vụ thay đổi entity | Managed entity và các quan hệ phục vụ invariant | Fetch plan theo domain operation |

Nếu màn hình danh sách không cần lines, tải lines cho mọi order là **over-fetch**. Nếu màn hình chi tiết cần lines nhưng mapper chỉ nhận entity chưa tải, đó là **under-fetch**.

Mục tiêu không phải số câu SQL nhỏ nhất bằng mọi giá: query join rất rộng có thể truyền hàng trăm nghìn rows dù chỉ có một câu SQL.

## 2. Entity loaded, entity managed và DTO là ba khái niệm khác nhau

- **Managed entity**: entity thuộc persistence context hiện tại; JPA quản lý identity và thay đổi theo quy tắc của context/transaction.
- **Loaded attribute**: trường hoặc association đã được provider tải đủ để ứng dụng truy cập mà không cần khởi tạo lazy thêm.
- **DTO**: object chứa dữ liệu phục vụ trao đổi; không có managed identity, không dirty checking nếu là record/class thông thường.

Ví dụ:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
boolean managed = em.contains(order);
~~~

`managed == true` không chứng minh `order.getLines()` đã initialized.

Ngược lại, một entity detached vẫn có thể đọc những trường/association **đã tải trước khi detach**, nhưng không nên truy cập quan hệ LAZY chưa khởi tạo sau khi context không còn hoạt động.

### 2.1. Những quan hệ cần nhớ

| Cấu trúc | Ý nghĩa |
| --- | --- |
| `@ManyToOne(fetch = LAZY)` | To-one có thể trì hoãn tải |
| `@OneToMany(fetch = LAZY)` | Collection thường được tải khi cần |
| `JOIN` | Join để chọn/lọc dữ liệu |
| `JOIN FETCH` | Yêu cầu tải association trong fetch plan |
| `@NamedEntityGraph` | Khai báo tập thuộc tính cần tải cho use case |
| `SELECT new ...Dto(...)` | Tạo dữ liệu DTO trực tiếp từ các biểu thức JPQL |
| `PersistenceUnitUtil.isLoaded(...)` | Kiểm tra load state; không tải dữ liệu |
| `em.close()` / `em.clear()` | Đóng context / detach managed entities |

**JOIN thông thường không tự thay cho JOIN FETCH.** Một query có thể join Customer để lọc theo email mà vẫn chưa khởi tạo đầy đủ `order.customer` trong entity kết quả.

---

## 3. Mô hình dùng trong bài

Các ví dụ dùng Java 17+, `jakarta.persistence.*` và một số ví dụ `@Transactional` của Spring. Khi dùng Jakarta EE/JTA hoặc resource-local, có thể thiết kế ranh giới tương đương với API transaction của môi trường.

### 3.1. Enum OrderStatus

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

### 3.2. Entity Customer

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false, unique = true)
    private String email;

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

### 3.3. Entity PurchaseOrder

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "total_amount",
            nullable = false, precision = 15, scale = 2)
    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    @OrderBy("id ASC")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
~~~

### 3.4. Entity OrderLine

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price",
            nullable = false, precision = 15, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {
    }

    public Long getId() {
        return id;
    }

    public String getProductCode() {
        return productCode;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
~~~

`@OrderBy("id ASC")` mô tả thứ tự tải các phần tử `lines`. Nó không phải `@OrderColumn` và không bổ sung cột vị trí vào bảng. Nếu thứ tự dòng hàng là dữ liệu nghiệp vụ bắt buộc, cần thiết kế thứ tự lưu trữ tương ứng trong model/schema.

### 3.5. Schema quan hệ minh họa

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(255) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(15, 2) NOT NULL,
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);

CREATE INDEX idx_orders_status_created_id
    ON purchase_orders (status, created_at, id);

CREATE INDEX idx_lines_order_id
    ON order_lines (order_id, id);
~~~

DDL này chỉ minh họa, phải điều chỉnh cho database và migration thực tế.

---

## 4. Thiết kế DTO contract trước khi thiết kế fetch plan

Một API chi tiết cần trường đơn hàng, thông tin khách hàng và các lines. Định nghĩa:

~~~java
package com.example.shop.dto;

public record CustomerSummaryDto(
    Long id,
    String email
) {
}
~~~

~~~java
package com.example.shop.dto;

import java.math.BigDecimal;

public record OrderLineDto(
    Long id,
    String productCode,
    int quantity,
    BigDecimal unitPrice
) {
}
~~~

~~~java
package com.example.shop.dto;

import com.example.shop.domain.OrderStatus;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

public record OrderDetailDto(
    Long id,
    String orderCode,
    OrderStatus status,
    LocalDateTime createdAt,
    BigDecimal totalAmount,
    CustomerSummaryDto customer,
    List<OrderLineDto> lines
) {
    public OrderDetailDto {
        lines = List.copyOf(lines);
    }
}
~~~

Hợp đồng:

~~~text
PurchaseOrder.id/code/status/createdAt/totalAmount
       |
       +-- customer.id/email
       |
       +-- lines[*].id/productCode/quantity/unitPrice
       |
       v
OrderDetailDto không chứa proxy/entity JPA
~~~

Từ DTO có thể suy ra **những association mapper sẽ cần đọc**:

- Các thuộc tính scalar của order.
- `customer.id` và `customer.email`.
- Collection `lines` và các field của mỗi line.
- Không cần một quan hệ khác như payments/discount history nếu DTO không chứa chúng.

### 4.1. Không bọc entity bên trong DTO

Anti-pattern:

~~~java
public record OrderDetailDto(
    Long id,
    Customer customer,
    List<OrderLine> lines
) {
}
~~~

Record này vẫn mang object graph JPA ra tầng ngoài. Nếu serializer truy cập quan hệ LAZY chưa tải, ranh giới persistence lại bị xuyên qua.

Nested DTO nên chứa **scalar hoặc DTO độc lập**:

~~~java
new CustomerSummaryDto(
    customer.getId(),
    customer.getEmail()
);
~~~

Đừng xem việc đổi tên lớp thành DTO là đủ để tách biệt persistence.

### 4.2. Tối thiểu hóa dữ liệu

DTO cũng là ranh giới của **API response**. Khi màn hình chỉ cần tên/mã khách hàng, không nên tải và trả toàn bộ profile, địa chỉ, thông tin thanh toán, lịch sử giao dịch.

Tối thiểu hóa dữ liệu giúp giảm SQL, băng thông và nguy cơ để lộ thông tin, nhưng **không thay thế authorization**.

## 5. Mapper chuyển entity thành DTO

Một mapper thuần Java:

~~~java
package com.example.shop.mapper;

import com.example.shop.domain.OrderLine;
import com.example.shop.domain.PurchaseOrder;
import com.example.shop.dto.CustomerSummaryDto;
import com.example.shop.dto.OrderDetailDto;
import com.example.shop.dto.OrderLineDto;
import java.util.List;

public final class OrderDtoMapper {

    private OrderDtoMapper() {
    }

    public static OrderDetailDto toDetail(PurchaseOrder order) {
        CustomerSummaryDto customer =
            new CustomerSummaryDto(
                order.getCustomer().getId(),
                order.getCustomer().getEmail()
            );

        List<OrderLineDto> lineDtos = order.getLines()
            .stream()
            .map(OrderDtoMapper::toLine)
            .toList();

        return new OrderDetailDto(
            order.getId(),
            order.getOrderCode(),
            order.getStatus(),
            order.getCreatedAt(),
            order.getTotalAmount(),
            customer,
            lineDtos
        );
    }

    private static OrderLineDto toLine(OrderLine line) {
        return new OrderLineDto(
            line.getId(),
            line.getProductCode(),
            line.getQuantity(),
            line.getUnitPrice()
        );
    }
}
~~~

Mapper không gọi trực tiếp `EntityManager`, nhưng **vẫn có thể làm JPA phát SQL** qua `order.getCustomer().getEmail()` hoặc `order.getLines().stream()`.

Vì thế:

- Tầng repository/service chịu trách nhiệm **fetch plan**.
- Mapper chịu trách nhiệm **chuyển dữ liệu**.
- Mapping phải xảy ra khi các association được yêu cầu đã tải và context vẫn hợp lệ.
- DTO trả về phải dùng được ngoài transaction.

**Không tự động coi mapper là “không đụng database”** chỉ vì code mapper không gọi `createQuery`.

---

## 6. Lỗi thứ nhất: map sau khi đóng EntityManager

Ví dụ có vấn đề:

~~~java
public PurchaseOrder findOrder(Long id) {
    EntityManager em = emf.createEntityManager();
    try {
        return em.find(PurchaseOrder.class, id);
    } finally {
        em.close();
    }
}

// Bên ngoài:
PurchaseOrder order = findOrder(orderId);
OrderDetailDto dto = OrderDtoMapper.toDetail(order);
~~~

Sau `em.close()`, order detached. Nếu customer/lines chưa initialized, mapper có thể gặp lỗi lazy-loading do provider không còn context thích hợp.

Cách khắc phục đúng hướng là **tải dữ liệu và hoàn tất mapping trong unit of work**:

~~~java
public OrderDetailDto findDetail(Long id) {
    EntityManager em = emf.createEntityManager();
    try {
        PurchaseOrder order = loadWithFetchPlan(em, id);
        return OrderDtoMapper.toDetail(order);
    } finally {
        em.close();
    }
}
~~~

`loadWithFetchPlan` là phương thức placeholder cho query ở các phần tiếp theo. Nếu yêu cầu snapshot nhất quán hoặc thao tác nhiều query, caller cần transaction theo chính sách ứng dụng; việc có một EntityManager mở không đồng nghĩa tự động có transaction phù hợp.

## 7. Lỗi thứ hai: mapper chạy trong transaction nhưng N+1

Ví dụ:

~~~java
@Transactional(readOnly = true)
public List<OrderDetailDto> listDetails() {
    List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    ).getResultList();

    return orders.stream()
        .map(OrderDtoMapper::toDetail)
        .toList();
}
~~~

Đoạn này có thể tránh lỗi lazy do context còn mở, nhưng vẫn không kiểm soát hiệu quả truy vấn. Với 100 orders:

~~~text
SELECT orders
SELECT customer WHERE id = ...
SELECT lines WHERE order_id = ...
SELECT customer WHERE id = ...
SELECT lines WHERE order_id = ...
...
~~~

có thể phát sinh nhiều SQL. Số lượng chính xác phụ thuộc cache, số customer khác nhau, batch fetching và provider.

**Transaction giải quyết phạm vi truy cập, không tự loại bỏ N+1.** Phải có fetch plan theo use case và đo số SQL.

### 7.1. Không cố “sửa” bằng EAGER toàn cục

~~~java
@OneToMany(fetch = FetchType.EAGER)
private List<OrderLine> lines;
~~~

có thể làm mọi nơi tải order phải quan tâm đến lines, kể cả endpoint chỉ cần mã đơn. EAGER cũng không nhất thiết tương đương một JOIN; provider có thể phát SELECT phụ.

Giữ LAZY cho những association phù hợp rồi **chọn graph trong query** thường dễ tối ưu hơn.

## 8. Đặt ranh giới ở service và transaction

Ví dụ với Spring:

~~~java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderQueryService {

    private final EntityManager em;

    public OrderQueryService(EntityManager em) {
        this.em = em;
    }

    @Transactional(readOnly = true)
    public OrderDetailDto detail(Long orderId) {
        PurchaseOrder order = loadDetailEntity(orderId);
        return OrderDtoMapper.toDetail(order);
    }

    private PurchaseOrder loadDetailEntity(Long orderId) {
        // Sử dụng JOIN FETCH hoặc EntityGraph.
        throw new UnsupportedOperationException();
    }
}
~~~

`@Transactional` là annotation **Spring**, không thuộc Jakarta Persistence. Với Spring proxy-based transaction, method public thường cần được gọi từ bên ngoài proxy do Spring quản lý để advice được áp dụng.

`readOnly=true` thường là **hint/cấu hình transaction**, không phải cơ chế bảo mật chặn tuyệt đối mọi thao tác ghi.

Ranh giới đúng:

~~~text
Controller
    |
    v
@Transactional service
    |
    +-- kiểm tra quyền
    +-- load query / graph
    +-- map DTO
    |
    v
Return OrderDetailDto
    |
    +-- transaction kết thúc
    +-- serializer chỉ dùng scalar/nested DTO
~~~

Khi dùng JTA/Jakarta EE hoặc application-managed EntityManager, ranh giới cần được tạo bằng cơ chế tương đương.

---

## 9. Phương án A: JOIN FETCH khi xem một đơn hàng

Nếu biết một đơn hàng có ít dòng và cần chi tiết đầy đủ, JPQL fetch join có thể hợp lý:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN FETCH o.customer
LEFT JOIN FETCH o.lines
WHERE o.id = :id
~~~

Giải thích:

- `JOIN FETCH o.customer`: tải quan hệ customer bắt buộc.
- `LEFT JOIN FETCH o.lines`: tải lines **nhưng vẫn giữ order không có line**.
- `WHERE o.id = :id`: giới hạn một root.
- `DISTINCT`: thể hiện mục đích root không lặp; cách render/deduplicate còn phụ thuộc provider.

Ví dụ:

~~~java
public PurchaseOrder findDetailEntity(
        EntityManager em,
        Long orderId) {

    List<PurchaseOrder> rows = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        JOIN FETCH o.customer
        LEFT JOIN FETCH o.lines
        WHERE o.id = :id
        """,
        PurchaseOrder.class
    )
    .setParameter("id", orderId)
    .getResultList();

    if (rows.isEmpty()) {
        throw new jakarta.persistence.EntityNotFoundException(
            "Order not found: " + orderId
        );
    }

    return rows.get(0);
}
~~~

Service:

~~~java
@Transactional(readOnly = true)
public OrderDetailDto detail(Long id) {
    PurchaseOrder order = repository.findDetailEntity(em, id);
    return OrderDtoMapper.toDetail(order);
}
~~~

Ví dụ SQL được sinh có thể tương tự:

~~~sql
SELECT
    o.id, o.order_code, o.status,
    o.created_at, o.total_amount, o.customer_id,
    c.id, c.email,
    l.id, l.product_code, l.quantity, l.unit_price
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines l ON l.order_id = o.id
WHERE o.id = ?;
~~~

Đây là **SQL minh họa**, không phải log thực tế. Dialect và provider có thể chọn aliases, columns hoặc query shape khác.

### 9.1. Vì sao LEFT JOIN FETCH?

Nếu một đơn không có lines:

~~~jpql
JOIN FETCH o.lines
~~~

là inner join và có thể làm mất order khỏi kết quả. `LEFT JOIN FETCH` giữ parent ngay cả khi collection rỗng.

### 9.2. Row multiplication

Một order có 40 lines có thể tạo gần 40 SQL rows vì các cột order/customer bị lặp trên từng dòng join. ORM hợp nhất về một entity root cùng collection, nhưng băng thông và memory xử lý vẫn có chi phí.

Với một order có hàng chục nghìn lines, fetch toàn bộ collection chỉ để hiển thị một vài dòng là thiết kế không phù hợp. Hãy dùng line pagination hoặc projection/aggregate.

### 9.3. Fetch nhiều collection có thể gây tích Descartes

Giả sử:

~~~text
Order.lines:    20
Order.payments: 4
Order.notes:    10
~~~

Một query fetch join cả ba collection độc lập có thể tạo hàng trăm SQL rows cho cùng root:

\[
20 \times 4 \times 10 = 800
\]

Một số provider còn có hạn chế riêng với nhiều bag collections.

Không dùng “một SELECT” làm mục tiêu tuyệt đối. Nhiều SELECT nhỏ hoặc DTO projection có thể giảm đáng kể row multiplication.

## 10. Phương án B: EntityGraph theo use case

JPA hỗ trợ `EntityGraph` để yêu cầu tải các thuộc tính cụ thể mà không sửa global `FetchType`.

### 10.1. Named entity graph

Gắn lên entity:

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.detail",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode("lines")
    }
)
@Entity
public class PurchaseOrder {
    // Mapping như mô hình đã trình bày.
}
~~~

Đây là đoạn metadata bổ sung; không tạo một class entity thứ hai trong project.

Khi truy vấn:

~~~java
EntityGraph<?> graph =
    em.getEntityGraph("PurchaseOrder.detail");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    java.util.Map.of(
        "jakarta.persistence.fetchgraph",
        graph
    )
);

if (order == null) {
    throw new jakarta.persistence.EntityNotFoundException();
}

OrderDetailDto dto = OrderDtoMapper.toDetail(order);
~~~

Map DTO khi context còn hợp lệ. Các attribute trong graph được yêu cầu theo semantics graph; provider có thể thực hiện join hoặc secondary selects.

### 10.2. Graph động

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");
graph.addAttributeNodes("lines");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    java.util.Map.of(
        "jakarta.persistence.fetchgraph",
        graph
    )
);
~~~

Graph động hữu ích khi fetch plan thuộc một repository method riêng, không cần gắn tên metadata chung.

### 10.3. fetchgraph và loadgraph

| Hint | Ý nghĩa |
| --- | --- |
| `jakarta.persistence.fetchgraph` | Attributes trong graph được yêu cầu tải; attribute khác được xem như LAZY theo graph semantics, provider có thể tải thêm state |
| `jakarta.persistence.loadgraph` | Attributes trong graph được tải; phần không khai báo theo mapping fetch semantics thông thường |

Ví dụ:

~~~java
query.setHint(
    "jakarta.persistence.loadgraph",
    graph
);
~~~

**EntityGraph không đảm bảo đúng một câu SQL** và không tự làm cho collection fetch + pagination an toàn trong mọi provider.

### 10.4. Subgraph nếu DTO có tầng quan hệ sâu

Giả sử DTO cần `order.customer.address.city`. Một entity graph có thể khai báo subgraph:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

Subgraph<Customer> customerGraph =
    graph.addSubgraph("customer", Customer.class);

customerGraph.addAttributeNodes("address");
~~~

Đây là ví dụ **ý tưởng**, giả sử `Customer` có association `address` tương ứng. Không dùng subgraph này với entity mẫu ở trên khi chưa có mapping `address`.

Với graph sâu, phải đo cardinality, tránh fetch nhiều to-many cùng lúc.

---

## 11. Phương án C: query DTO projection trực tiếp

Đối với màn hình chỉ đọc các scalar, cách đơn giản nhất có thể là không materialize entity graph.

Định nghĩa:

~~~java
package com.example.shop.dto;

import com.example.shop.domain.OrderStatus;
import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderListItemDto(
    Long id,
    String orderCode,
    OrderStatus status,
    LocalDateTime createdAt,
    BigDecimal totalAmount,
    String customerEmail
) {
}
~~~

JPQL:

~~~jpql
SELECT new com.example.shop.dto.OrderListItemDto(
    o.id,
    o.orderCode,
    o.status,
    o.createdAt,
    o.totalAmount,
    c.email
)
FROM PurchaseOrder o
JOIN o.customer c
WHERE o.status = :status
ORDER BY o.createdAt DESC, o.id DESC
~~~

Java:

~~~java
List<OrderListItemDto> page = em.createQuery(
    """
    SELECT new com.example.shop.dto.OrderListItemDto(
        o.id,
        o.orderCode,
        o.status,
        o.createdAt,
        o.totalAmount,
        c.email
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.status = :status
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    OrderListItemDto.class
)
.setParameter("status", OrderStatus.CONFIRMED)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
~~~

Trong projection chỉ gồm scalar, provider không cần materialize managed `PurchaseOrder` và `Customer` để map từng DTO theo cách tải entity thông thường.

Đây là **read model**, không phải managed entity. Thay đổi field của DTO không được dirty checking để cập nhật database.

### 11.1. JOIN khác JOIN FETCH

Trong projection trên:

~~~jpql
JOIN o.customer c
~~~

chỉ giúp lấy `c.email`. Chúng ta **không cần `JOIN FETCH`**, vì không trả entity `PurchaseOrder` và không cần tải `order.customer` proxy.

### 11.2. Constructor type phải đúng

Thứ tự argument trong `SELECT new ...` phải tương thích constructor của record. Nếu thêm field vào record hoặc thay type nhưng không sửa JPQL, provider có thể báo lỗi parsing/constructor mapping.

Đặt integration test cho những DTO projections quan trọng.

### 11.3. Không cần tải collection chỉ để đếm

Nếu list chỉ cần số lines, có thể dùng aggregation phù hợp:

~~~jpql
SELECT o.id, COUNT(l)
FROM PurchaseOrder o
LEFT JOIN o.lines l
GROUP BY o.id
~~~

Đối với một DTO chứa thêm các field order, cần thiết kế `GROUP BY` phù hợp với JPQL và database, hoặc dùng subquery/aggregate query riêng. Đừng tải toàn bộ `lines` rồi đếm trong Java nếu database chỉ cần trả một số.

## 12. DTO lồng collection: một constructor projection không tự gom list

Nếu một `OrderDetailDto` có `List<OrderLineDto>`, JOIN to-many sẽ tạo nhiều hàng:

~~~text
order_id | line_id | product_code
101      | 1       | AA
101      | 2       | BB
101      | 3       | CC
~~~

JPQL `SELECT new OrderDetailDto(...)` **không tự hiểu** cần gom ba row trên thành một List<OrderLineDto> của cùng order theo cách constructor projection chuẩn thông thường.

Có ba hướng:

1. Fetch managed entity + lines rồi map.
2. Query header DTO và lines DTO riêng, sau đó ghép.
3. Query flat projection và group theo order ID trong repository.

Việc ánh xạ nested DTO cần là một bước thiết kế rõ, không dựa vào serializer duyệt LAZY graph sau đó.

## 13. Tạo detail DTO bằng hai query projection

Header projection:

~~~java
public record OrderHeaderRow(
    Long id,
    String orderCode,
    OrderStatus status,
    LocalDateTime createdAt,
    BigDecimal totalAmount,
    Long customerId,
    String customerEmail
) {
}
~~~

Line projection:

~~~java
public record OrderLineRow(
    Long id,
    String productCode,
    int quantity,
    BigDecimal unitPrice
) {
}
~~~

Query header:

~~~java
OrderHeaderRow header = em.createQuery(
    """
    SELECT new com.example.shop.dto.OrderHeaderRow(
        o.id, o.orderCode, o.status,
        o.createdAt, o.totalAmount,
        c.id, c.email
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.id = :id
    """,
    OrderHeaderRow.class
)
.setParameter("id", orderId)
.getSingleResult();
~~~

Query lines:

~~~java
List<OrderLineRow> lines = em.createQuery(
    """
    SELECT new com.example.shop.dto.OrderLineRow(
        l.id, l.productCode,
        l.quantity, l.unitPrice
    )
    FROM OrderLine l
    WHERE l.order.id = :id
    ORDER BY l.id ASC
    """,
    OrderLineRow.class
)
.setParameter("id", orderId)
.getResultList();
~~~

Tạo DTO:

~~~java
List<OrderLineDto> lineDtos = lines.stream()
    .map(l -> new OrderLineDto(
        l.id(), l.productCode(),
        l.quantity(), l.unitPrice()
    ))
    .toList();

OrderDetailDto dto = new OrderDetailDto(
    header.id(),
    header.orderCode(),
    header.status(),
    header.createdAt(),
    header.totalAmount(),
    new CustomerSummaryDto(
        header.customerId(),
        header.customerEmail()
    ),
    lineDtos
);
~~~

Ưu điểm:

- Chỉ lấy những cột cần.
- Không materialize managed graph.
- Không phụ thuộc LAZY loading để tạo nested DTO.
- Dễ giới hạn số lines bằng query riêng khi cần.

Đánh đổi:

- Hai round trips.
- Phải xác định ngữ nghĩa snapshot của hai SELECT.
- Nếu nghiệp vụ cần managed entity để gọi domain methods, projection không thay thế entity.

### 13.1. Khi nào hai query nhanh hơn một fetch join?

Nếu một order có nhiều lines và parent rộng hàng chục cột, một fetch join sẽ lặp lại các cột parent trên mọi SQL row.

Hai query chọn header một lần và child rows riêng có thể truyền ít dữ liệu hơn. Nhưng round-trip overhead cũng là chi phí, vì vậy phải đo với dữ liệu thật thay vì mặc định hai query luôn tốt hơn.

---

## 14. Phân trang: tránh fetch join collection trên query root có limit

Ví dụ rủi ro:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    WHERE o.status = :status
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    PurchaseOrder.class
)
.setParameter("status", status)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
~~~

Một order có 10 lines tạo nhiều SQL rows. Giới hạn 20 rows từ database **không tương đương** 20 root orders với collections đầy đủ.

Provider có thể phân trang trong bộ nhớ, phát cảnh báo hoặc lỗi tùy phiên bản/cấu hình; không thể coi hành vi luôn giống nhau.

**Đừng kết hợp root pagination với collection fetch join mà không xác minh query plan và semantics.**

### 14.1. DISTINCT không sửa hết vấn đề

`DISTINCT` có thể loại root trùng ở tầng JPA, nhưng SQL vẫn chứa rows có child khác nhau. Nó không tự đảm bảo database áp limit lên **số parent** như ứng dụng mong muốn.

## 15. Phân trang hai giai đoạn: ID trước, graph sau

Một chiến lược thông dụng:

~~~text
Query A: IDs thuộc trang
    [105, 102, 99]
         |
         v
Query B: tải những order với ID IN (...)
         |
         v
Map by ID, phục hồi thứ tự [105, 102, 99]
         |
         v
List<OrderDetailDto>
~~~

### 15.1. Query A: chọn root IDs

~~~java
List<Long> ids = em.createQuery(
    """
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.status = :status
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    Long.class
)
.setParameter("status", status)
.setFirstResult(offset)
.setMaxResults(limit)
.getResultList();
~~~

Dùng thêm `o.id DESC` làm tie-breaker khi nhiều order có cùng `createdAt`.

Nếu `ids.isEmpty()` thì trả list rỗng; không gửi `IN ()` rỗng và kỳ vọng mọi DB xử lý giống nhau.

### 15.2. Query B: fetch graph cho tập IDs

~~~java
List<PurchaseOrder> fetched = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    JOIN FETCH o.customer
    LEFT JOIN FETCH o.lines
    WHERE o.id IN :ids
    """,
    PurchaseOrder.class
)
.setParameter("ids", ids)
.getResultList();
~~~

Ở đây **không phân trang trên collection fetch join**; tập root IDs đã giới hạn từ Query A.

Vẫn cần chú ý: nếu một order có 20.000 lines, Query B sẽ lớn. Chiến lược này giải quyết đúng số root thuộc trang, không giới hạn tuyệt đối số SQL rows.

### 15.3. Phục hồi thứ tự

SQL `IN :ids` không đảm bảo giữ thứ tự của list ID. Sắp bằng Java:

~~~java
Map<Long, PurchaseOrder> byId = fetched.stream()
    .collect(java.util.stream.Collectors.toMap(
        PurchaseOrder::getId,
        java.util.function.Function.identity()
    ));

List<OrderDetailDto> page = ids.stream()
    .map(byId::get)
    .filter(java.util.Objects::nonNull)
    .map(OrderDtoMapper::toDetail)
    .toList();
~~~

Lọc null trong ví dụ tránh NPE nếu một record biến mất giữa hai query. Nhưng **production cần định nghĩa contract rõ ràng**: retry, báo conflict, trả trang thiếu phần tử hay dùng isolation/snapshot phù hợp.

### 15.4. Giới hạn

- `IN` có thể gặp giới hạn số bind parameters; trang quá lớn cần giới hạn/chia batch.
- Tải collection vẫn có thể tạo row multiplication.
- Hai query có thể thấy dữ liệu khác nhau tùy transaction isolation.
- Thứ tự phải phục hồi theo Query A.
- Nếu chỉ cần scalar, projection theo trang có thể đơn giản hơn.

## 16. Phân trang hai giai đoạn bằng DTO projection

Nếu cần read-only DTO, thay vì Query B fetch entity graph, có thể dùng:

1. Query parent DTO theo page.
2. Query child DTO theo IDs của page.
3. Group child theo parent ID.
4. Tạo nested DTO.

Parent query:

~~~java
List<OrderHeaderRow> headers = em.createQuery(
    """
    SELECT new com.example.shop.dto.OrderHeaderRow(
        o.id, o.orderCode, o.status,
        o.createdAt, o.totalAmount,
        c.id, c.email
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.status = :status
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    OrderHeaderRow.class
)
.setParameter("status", status)
.setFirstResult(offset)
.setMaxResults(limit)
.getResultList();
~~~

Lấy IDs:

~~~java
List<Long> ids = headers.stream()
    .map(OrderHeaderRow::id)
    .toList();
~~~

Với list IDs không rỗng, query child:

~~~java
public record OrderLineWithParentRow(
    Long orderId,
    Long lineId,
    String productCode,
    int quantity,
    BigDecimal unitPrice
) {
}
~~~

~~~java
List<OrderLineWithParentRow> childRows = em.createQuery(
    """
    SELECT new com.example.shop.dto.OrderLineWithParentRow(
        l.order.id,
        l.id,
        l.productCode,
        l.quantity,
        l.unitPrice
    )
    FROM OrderLine l
    WHERE l.order.id IN :ids
    ORDER BY l.order.id, l.id
    """,
    OrderLineWithParentRow.class
)
.setParameter("ids", ids)
.getResultList();
~~~

Gom theo parent:

~~~java
Map<Long, List<OrderLineDto>> byOrder =
    new java.util.HashMap<>();

for (OrderLineWithParentRow line : childRows) {
    byOrder.computeIfAbsent(
        line.orderId(),
        ignored -> new java.util.ArrayList<>()
    ).add(new OrderLineDto(
        line.lineId(),
        line.productCode(),
        line.quantity(),
        line.unitPrice()
    ));
}
~~~

Tạo DTO theo thứ tự headers:

~~~java
List<OrderDetailDto> result = headers.stream()
    .map(h -> new OrderDetailDto(
        h.id(),
        h.orderCode(),
        h.status(),
        h.createdAt(),
        h.totalAmount(),
        new CustomerSummaryDto(
            h.customerId(),
            h.customerEmail()
        ),
        byOrder.getOrDefault(
            h.id(),
            java.util.List.of()
        )
    ))
    .toList();
~~~

Ưu điểm:

- Parent được phân trang ở SQL.
- Query child chọn chính xác các trường cần.
- Không cần materialize managed entity graph.
- Không tạo N+1 theo từng order.
- Parent không có child nhận list rỗng.
- Trật tự parent và child được điều khiển.

**Nhược điểm:** cần code grouping và quyết định semantics nhất quán giữa hai SELECT. Không nên dùng cách này cho nghiệp vụ cần thay đổi entity managed sau khi đọc.

---

## 17. Batch loading khi dùng managed entities

Nếu query đã lấy một trang order entities và mapper cần lazy associations, một số provider hỗ trợ **batch fetching**.

Với Hibernate:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@org.hibernate.annotations.BatchSize(size = 32)
private List<OrderLine> lines;
~~~

Hoặc:

~~~properties
hibernate.default_batch_fetch_size=32
~~~

Ý tưởng:

~~~text
Không batch:
  SELECT orders
  SELECT lines WHERE order_id = 1
  SELECT lines WHERE order_id = 2
  SELECT lines WHERE order_id = 3
  ...

Có batch:
  SELECT orders
  SELECT lines WHERE order_id IN (1, 2, 3, ...)
  ...
~~~

Tùy cache/context/provider, số query có thể giảm. Nhưng **BatchSize là extension Hibernate**, không phải annotation JPA portable.

### 17.1. Batch không thay thế ranh giới tải

Nếu mapper chạy sau khi context đã đóng, một collection chưa initialized vẫn có thể gây lỗi. Batch fetching chỉ giúp hiệu quả khi association **thực sự được tải** trong context hợp lệ.

Một use case quan trọng có thể kết hợp:

- Query root rõ ràng.
- Batch fetching phù hợp workload.
- Mapper chạy trong transaction.
- Đo SQL và số rows.

Provider-specific `SUBSELECT` fetching có thể hữu ích trong một số mô hình, nhưng không nên coi mọi provider hỗ trợ giống nhau.

## 18. Kiểm tra load state bằng PersistenceUnitUtil

JPA cung cấp:

~~~java
jakarta.persistence.PersistenceUnitUtil util =
    em.getEntityManagerFactory().getPersistenceUnitUtil();

boolean customerLoaded =
    util.isLoaded(order, "customer");

boolean linesLoaded =
    util.isLoaded(order, "lines");
~~~

`isLoaded` quan sát trạng thái tải theo provider; nó **không tự fetch** association.

Ví dụ mapper có guard:

~~~java
if (!util.isLoaded(order, "lines")) {
    throw new IllegalStateException(
        "Fetch plan does not load order lines"
    );
}
~~~

Guard này hữu ích khi team muốn ngăn mapper tự kích hoạt SQL không chủ đích.

Tuy nhiên:

- `isLoaded` không đếm SQL.
- Nó không chứng minh graph nhiều cấp đã tải đủ.
- Dữ liệu có thể loaded từ cache chứ không phải SELECT mới.
- Với detached entity, nó không mở lại context.
- Nó không thay thế integration test.

Một lỗi thường gặp là gọi `order.getLines().size()` trong vòng lặp chỉ để “ép load”. Cách này dễ biến thành N+1 và làm fetch plan khó nhìn thấy ở repository.

---

## 19. N+1: phải đo toàn bộ service method

Query root:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
~~~

Sau đó mapper:

~~~java
return orders.stream()
    .map(OrderDtoMapper::toDetail)
    .toList();
~~~

Các SELECT bổ sung có thể chỉ xuất hiện **trong mapper**. Nếu log chỉ quan sát phần `createQuery`, team dễ bỏ sót N+1.

Cần đo từ đầu use case đến khi DTO đã được tạo:

~~~text
START service method
  SELECT orders
  [SELECT customers/lines do lazy]
  Map DTO
END service method
~~~

Số SQL không luôn bằng `1 + 2N` vì nhiều order có thể cùng customer, context/cache đã có dữ liệu hoặc provider dùng batch.

Một phép đo tốt tăng kích thước tập order từ 10 đến 100 và xem SQL/latency/rows tăng theo tỷ lệ nào.

### 19.1. JOIN để lọc chưa phải fetch

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.email LIKE :pattern
~~~

được phép JOIN Customer để lọc, nhưng không tự yêu cầu `o.customer` initialized để mapper đọc email.

Với DTO list chỉ cần email, projection trực tiếp `c.email` thường hợp lý hơn.

## 20. Open Session in View không phải giải pháp fetch plan

Một số framework có tính năng **Open Session in View (OSIV)**, giữ Session/persistence context mở tới giai đoạn render/serialize.

Nếu controller trả entity:

~~~java
@GetMapping("/orders/{id}")
public PurchaseOrder detail(@PathVariable Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

serializer có thể đụng `customer` hoặc `lines` và kích hoạt SQL sau khi service transaction kết thúc.

Hệ quả:

- Query phát sinh ở tầng không chủ động chọn fetch plan.
- Dễ giấu N+1.
- Tăng thời gian giữ session/resources.
- Payload vô tình thay đổi theo entity mapping.
- Có thể xuất hiện vòng tham chiếu hoặc dữ liệu nhạy cảm.
- Khó kiểm soát latency endpoint.

Một cấu hình thường dùng trong Spring Boot:

~~~properties
spring.jpa.open-in-view=false
~~~

Đây là lựa chọn kiến trúc cần áp dụng có kiểm thử; tắt OSIV không tự sửa query thiếu fetch plan. Khi đã trả DTO hoàn chỉnh từ service, serializer không cần dựa vào OSIV.

## 21. Không chuyển entity hoặc JPA stream qua thread khác

Không nên:

~~~java
CompletableFuture.supplyAsync(
    () -> OrderDtoMapper.toDetail(entity)
);
~~~

mà mặc định thread background có thể lazy-load từ persistence context của request trước đó. `EntityManager` không phải đối tượng thread-safe để truyền dùng tùy ý.

Một phương án là:

- Mapping DTO trong transaction hiện tại.
- Chỉ truyền DTO/IDs qua async boundary.
- Nếu async task cần truy vấn thêm, mở unit of work riêng trong task.

Với `getResultStream()`, đừng trả raw stream từ repository khi transaction/connection có thể đã đóng. Streaming JPA/JDBC cần xử lý **resource lifetime** riêng và đóng stream đúng.

---

## 22. Tính nhất quán khi query nhiều bước

Trong một endpoint detail bằng hai query:

~~~text
Query 1: header, totalAmount = 1200
Query 2: lines, có thể đã thay đổi do transaction khác
~~~

Nếu database dùng READ COMMITTED, tùy DB, mỗi SELECT có thể quan sát snapshot khác nhau.

Một transaction chỉ đọc **không tự bảo đảm** tất cả SELECT nhìn cùng dữ liệu trong mọi isolation mode.

Đối với yêu cầu strict consistency, cân nhắc:

- Snapshot/transaction isolation phù hợp.
- Optimistic version hoặc kiểm tra version ở các bước.
- Thiết kế aggregate được duy trì như một invariant nghiệp vụ.
- Query/snapshot riêng cho báo cáo chính xác.
- Khả năng retry khi dữ liệu thay đổi đồng thời.

Không nhất thiết áp isolation cao nhất cho mọi endpoint. Hãy lựa chọn theo chi phí và tính đúng đắn.

### 22.1. Offset pagination cũng chịu ảnh hưởng insert/delete

Dù dùng `ORDER BY createdAt DESC, id DESC`, một order mới chèn trước trang 2 có thể khiến offset pagination lặp/bỏ phần tử giữa các request. Với feed liên tục, keyset pagination hoặc snapshot phù hợp có thể tốt hơn.

## 23. Bảo mật và ranh giới DTO

Hợp đồng DTO xác định **những field nào được trả**, còn query/service phải xác định **ai được xem**.

Ví dụ query chi tiết có điều kiện sở hữu:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN FETCH o.customer
LEFT JOIN FETCH o.lines
WHERE o.id = :orderId
  AND o.customer.id = :authorizedCustomerId
~~~

`authorizedCustomerId` phải lấy từ **security context tin cậy**, không chỉ từ tham số do client gửi.

Với multi-tenant system, bảo đảm tenant filter áp dụng cho:

- Query parent IDs.
- Query fetch graph chi tiết.
- Query lines theo ID batch.
- Count query và report query.
- Các lối đi khác như native SQL.

DTO không tự kiểm tra ownership. Nó chỉ giúp hạn chế field khi đã chọn đúng records.

### 23.1. Không lấy thừa dữ liệu nhạy cảm

Nếu API chỉ cần mã khách hàng, không đưa địa chỉ/email/transaction history vào DTO. Điều này giúp giảm payload và vùng dữ liệu nhạy cảm, nhưng quyền truy cập vẫn cần được kiểm soát.

## 24. EntityGraph trong Spring Data JPA

Spring Data JPA hỗ trợ annotation riêng:

~~~java
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.Optional;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer", "lines"})
    @Query(
        """
        SELECT o
        FROM PurchaseOrder o
        WHERE o.id = :id
        """
    )
    Optional<PurchaseOrder> findDetailById(
        @Param("id") Long id
    );
}
~~~

Ở service:

~~~java
@Transactional(readOnly = true)
public OrderDetailDto detail(Long id) {
    PurchaseOrder order = repository.findDetailById(id)
        .orElseThrow(
            () -> new jakarta.persistence.EntityNotFoundException()
        );

    return OrderDtoMapper.toDetail(order);
}
~~~

`@EntityGraph` của Spring Data và `@NamedEntityGraph` của Jakarta Persistence có vai trò khác nhau; Spring Data cấu hình query method, còn Jakarta annotation đăng ký graph metadata.

Không gắn graph to-many mặc định vào mọi repository method có `Pageable` mà không đánh giá pagination semantics.

### 24.1. Interface projection cũng cần quan sát SQL

Spring Data hỗ trợ interface projection, nhưng nested projection đôi khi vẫn tạo JOIN/fetch tùy framework/provider. Không xem tên “projection” là bằng chứng mọi query chỉ lấy cột tối thiểu; cần kiểm tra SQL thực tế.

---

## 25. Kiểm chứng SQL, round trips và row count

Khi chọn fetch plan, cần đo:

| Tiêu chí | Câu hỏi |
| --- | --- |
| Số SQL statements | Có N+1 không? |
| Số rows DB trả | Có row multiplication do to-many join không? |
| Độ rộng mỗi row | Có lặp quá nhiều parent columns không? |
| Kích thước graph | Có materialize hàng nghìn objects không cần không? |
| Round trips | Một query rộng hay vài query nhỏ có lợi hơn? |
| Pagination | Giới hạn đúng parent hay chỉ SQL join rows? |
| Index/query plan | JOIN/WHERE/ORDER BY có tối ưu không? |
| Transaction duration | Có giữ connection quá lâu khi map không? |
| Serializer | Có SQL phát sau khi service trả không? |
| Security | Có query nào bỏ tenant filter không? |

Ví dụ Hibernate 6 trong development/test:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Hibernate 5 thường dùng logger bind khác:

~~~properties
logging.level.org.hibernate.type.descriptor.sql.BasicBinder=TRACE
~~~

Không bật bind logging rộng ở production khi chưa có quy trình ẩn dữ liệu: email, ID, số tiền và thông tin cá nhân có thể xuất hiện trong log.

### 25.1. Hibernate Statistics

Khi dùng Hibernate:

~~~java
org.hibernate.SessionFactory sf =
    emf.unwrap(org.hibernate.SessionFactory.class);

org.hibernate.stat.Statistics stats =
    sf.getStatistics();

stats.setStatisticsEnabled(true);
stats.clear();

// Gọi service/query trong test.

long prepared = stats.getPrepareStatementCount();
~~~

Đây là API Hibernate-specific, có thể đếm trên toàn `SessionFactory` và bị nhiễu bởi test/request khác. Cần cô lập phép đo.

### 25.2. SQL ít không đồng nghĩa performance tốt

Một SQL join ba collections có thể tạo hàng nghìn rows, trong khi hai query DTO chỉ truyền vài trăm rows với ít cột hơn. Cần quan sát cả query plan, memory và latency.

`EXPLAIN`/`EXPLAIN ANALYZE` trên database thật có thể cho biết scans, joins, sort, estimated vs actual rows. Không chạy query phân tích nặng hoặc DML analysis thiếu kiểm soát trong production.

## 26. Xây integration tests cho fetch boundary

Dữ liệu mẫu:

| Order | Customer | Status | Số lines |
| --- | --- | --- | ---: |
| PO-101 | a@example.com | CONFIRMED | 2 |
| PO-102 | b@example.com | CONFIRMED | 0 |
| PO-103 | a@example.com | DRAFT | 3 |
| PO-104 | c@example.com | CONFIRMED | 10 |
| PO-105 | d@example.com | CONFIRMED | 1 |

Test nên xác nhận:

1. DTO có đúng order ID, code, status, amount.
2. Email customer đúng.
3. Order không có lines vẫn trả với list rỗng.
4. Dòng hàng đủ và đúng thứ tự nếu contract yêu cầu.
5. Trang chỉ chứa order đúng status, đủ số root.
6. Các orders cùng timestamp có thứ tự xác định bằng ID.
7. Tăng số order không làm SQL tăng gần tuyến tính khi không mong muốn.
8. Không có SQL khi serialize DTO sau khi service trả.
9. Không trả dữ liệu vượt quyền/tenant.
10. Collection nhiều lines không làm memory/latency vượt mục tiêu.

### 26.1. Test sau transaction

~~~java
OrderDetailDto dto = service.detail(orderId);

// Đã rời ranh giới method service.
assertEquals(orderId, dto.id());
assertEquals("a@example.com", dto.customer().email());
assertEquals(2, dto.lines().size());
~~~

Đây là đoạn assertion JUnit minh họa, giả định fixture phù hợp. DTO hoàn chỉnh được đọc ngoài transaction mà không cần JPA lazy loading.

### 26.2. Test với persistence context sạch

Nếu test vừa persist fixture và vẫn giữ entities/associations trong context, cache có thể che khuất SELECT bổ sung.

Trong test có transaction hợp lệ:

~~~java
em.flush();
em.clear();

// Reset vùng đo SQL rồi thực thi use case.
~~~

Hoặc chuẩn bị fixture trong transaction riêng, dùng EntityManager/persistence context mới cho act. Không đưa flush/clear vào production một cách máy móc.

### 26.3. Test không phụ thuộc OSIV

Nếu ứng dụng bật OSIV, một đoạn trả entity sai kiến trúc có thể vẫn hoạt động trong test HTTP do session chưa đóng. Có thể dùng nhóm integration tests với OSIV tắt để xác nhận response không dựa vào lazy loading trong serializer.

## 27. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| LazyInitializationException trong mapper | Map sau khi context đóng | Map trong ranh giới; fetch đúng dữ liệu |
| Map được nhưng SQL tăng theo số order | N+1 trong lazy associations | Fetch join/EntityGraph/batch/projection |
| EntityGraph vẫn phát nhiều SELECT | Graph không ràng buộc số SQL | Đo SQL và chọn plan hợp lý |
| Pagination trên collection trả sai số parent | Join rows khác root entities | Page IDs/headers trước rồi load child |
| Một order bị lặp | Join to-many nhân rows | Xem cardinality, distinct/group phù hợp |
| Đơn không có lines biến mất | Inner fetch join to-many | LEFT JOIN FETCH |
| DTO vẫn gây lazy loading | DTO chứa entity/proxy | Chỉ chứa nested DTO/scalars |
| Query projection không tạo được record | Sai type/thứ tự constructor | Đồng bộ query với record |
| Query B trả sai thứ tự | IN không giữ thứ tự danh sách | Reorder theo Query A IDs |
| Query B bỏ mất vài ID | Concurrent change giữa hai SELECT | Quy định consistency/retry/isolation |
| Trang có ít root do child join | LIMIT áp lên SQL rows | Tránh pagination trên fetch collection |
| EAGER khiến endpoint chậm | Over-fetch toàn cục | LAZY + fetch plan use case |
| Fetch nhiều collections rất chậm | Cartesian row explosion | Tách query, chỉ fetch cần thiết |
| Nhiều SQL sau service | Serializer truy cập lazy entity | Trả DTO, không OSIV phụ thuộc |
| Mapping ở async thread lỗi | Context không truyền qua thread | Truyền ID/DTO, task có scope riêng |
| COUNT sai | Join to-many làm nhân rows | Count DISTINCT/EXISTS |
| DTO header/lines lệch nhau | Snapshot khác giữa hai query | Isolation/consistency strategy |
| Lộ dữ liệu khách hàng khác | Thiếu authorization/tenant predicate | Kiểm tra quyền ngay trong service/query |
| Test không thấy N+1 | Cache/fixture cùng persistence context | Clear/new context và đo toàn use case |
| Collection 20.000 lines dùng quá nhiều RAM | Fetch toàn bộ thay vì paging | Child pagination hoặc aggregate |
| readOnly vẫn có DML | Read-only không là security boundary | Transaction policy và DB permissions |

---

## 28. Các ngộ nhận cần tránh

**“Có @Transactional thì không còn N+1.”** Sai. Transaction giúp association có thể load trong scope, nhưng không quy định SQL tối ưu.

**“Chuyển mọi quan hệ thành EAGER là giải pháp.”** Sai. EAGER có thể gây over-fetch ở các use case khác và không bảo đảm một SQL.

**“JOIN thông thường đã fetch association.”** Sai. JOIN để lọc/chọn dữ liệu, JOIN FETCH yêu cầu fetch association trong entity result.

**“EntityGraph luôn chạy một SQL.”** Sai. Graph biểu diễn attribute cần tải; provider được chọn execution strategy.

**“Một SELECT luôn tốt hơn hai SELECT.”** Không đúng nếu JOIN làm nhân hàng hoặc lặp nhiều cột.

**“DISTINCT giải quyết mọi vấn đề phân trang collection.”** Không. Nó không thay đổi cơ bản cardinality của rows trước khi materialize.

**“DTO record chứa entity cũng hoàn toàn độc lập.”** Không. Entity/proxy bên trong DTO vẫn mang semantics persistence.

**“OSIV giúp không cần quan tâm ranh giới tải.”** OSIV thường che giấu SQL phát sinh ngoài service và làm latency khó dự đoán.

**“DTO projection có thể tự gom nhiều child thành nested List.”** JPQL constructor projection thông thường không có cơ chế gom list tự động; cần grouping hoặc fetch graph có chủ đích.

**“DTO bảo đảm an toàn dữ liệu.”** DTO chỉ giúp kiểm soát field; authorization phải được thực hiện riêng.

## 29. Bài tập thực hành và lời giải

### Bài 1. Lazy sau khi EntityManager đóng

Repository trả `PurchaseOrder` có `lines` LAZY; controller gọi `getLines().size()`.

**Giải thích:** Đang truy cập association ngoài ranh giới context. Tải và map DTO trong service/repository trước khi đóng context.

### Bài 2. JOIN thay JOIN FETCH

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.email LIKE :pattern
~~~

**Giải thích:** JOIN chỉ giúp lọc; không bắt buộc customer initialized. Khi DTO chỉ cần email, dùng projection; khi entity cần customer, fetch join hoặc graph phù hợp.

### Bài 3. Order không có lines

~~~jpql
SELECT o FROM PurchaseOrder o JOIN FETCH o.lines
WHERE o.id = :id
~~~

**Giải thích:** Inner join có thể làm mất order rỗng. Dùng `LEFT JOIN FETCH` khi cần giữ parent.

### Bài 4. Phân trang 20 parent và to-many

**Giải thích:** Không áp `setMaxResults(20)` trực tiếp trên collection fetch join rồi mặc định có 20 parent đầy đủ. Query IDs/headers theo trang trước, tải collection sau.

### Bài 5. DTO trả entity Customer

**Giải thích:** Đó không phải DTO độc lập hoàn toàn. Map thành `CustomerSummaryDto` gồm field cần thiết.

### Bài 6. N+1 trong mapper

100 orders, mapper truy cập `getCustomer().getEmail()` và `getLines()`.

**Giải thích:** Có thể phát nhiều SELECT khi association LAZY. Dùng fetch plan phù hợp hoặc DTO projection, đo số SQL.

### Bài 7. LIMIT 20 nhưng chỉ còn 8 orders

**Giải thích:** Có thể có pagination trên SQL rows sau join collection; số root entities khác số join rows. Kiểm chứng SQL, chuyển sang paging roots.

### Bài 8. Query IN không giữ thứ tự IDs

Query A trả `[21, 18, 14]`, Query B trả `[14, 21, 18]`.

**Giải thích:** Dùng Map theo ID rồi xuất theo thứ tự Query A.

### Bài 9. Collection rất lớn

Một order có 80.000 lines, màn hình chỉ hiển thị 25 lines.

**Giải thích:** Dùng child pagination hoặc aggregate, không fetch toàn bộ collection chỉ vì detail endpoint.

### Bài 10. EntityGraph tạo hai SQL

**Giải thích:** Đây có thể là kế hoạch hợp lệ. Graph yêu cầu tải attribute, không cam kết số statement. Đo tổng rows và latency.

### Bài 11. Map trong @Async

**Giải thích:** Không chia sẻ managed EntityManager giữa threads. Truyền DTO hoặc ID; mở scope riêng trong task nếu cần DB.

### Bài 12. BatchSize tránh lazy lỗi?

**Giải thích:** Không. Batch fetching tối ưu số SQL khi lazy được tải trong context hợp lệ, không mở lại context đã đóng.

### Bài 13. DTO header/lines không khớp

**Giải thích:** Hai query có thể đọc dữ liệu tại hai snapshot khác nhau theo isolation. Quyết định snapshot/version/transaction theo yêu cầu.

### Bài 14. Query COUNT có JOIN FETCH

**Giải thích:** Không dùng fetch join để đếm entity. Query COUNT chỉ nên có filter/joins phục vụ predicate, dùng DISTINCT/EXISTS khi cần tránh row multiplication.

### Bài 15. EAGER có chắc một JOIN?

**Giải thích:** Không. Provider có thể dùng secondary SELECT. Xem SQL thực, không suy luận từ annotation.

### Bài 16. OSIV đang bật và API trả entity

**Giải thích:** Serializer có thể phát SQL ngoài service. Tốt hơn trả DTO hoàn chỉnh, test với OSIV tắt.

### Bài 17. Dữ liệu tenant khác lọt vào Query B

**Giải thích:** Filter quyền chỉ ở Query A không cho phép bổ sung ID từ client vào Query B. Giữ trusted IDs và tenant filters thích hợp.

### Bài 18. isLoaded trả false

**Giải thích:** Attribute chưa được xem là loaded; `isLoaded` không tự fetch. Cần thay fetch plan hoặc map trong context đã tải đúng association.

### Bài 19. DTO projection có dirty checking?

**Giải thích:** Không. DTO được tạo từ constructor projection không phải managed entity. Muốn cập nhật domain phải dùng entity/command có transaction.

### Bài 20. Hai query DTO có luôn nhanh hơn fetch join?

**Giải thích:** Không. Phải đo round trips, số rows, row width, cache, index và memory ở workload thực tế.

## 30. Checklist ra quyết định

Trước khi hoàn tất một endpoint:

1. DTO cần những field/association nào?
2. Có trường nào tải thừa không?
3. Mapper sẽ gọi getter nào?
4. Tất cả association cần đọc đã được fetch đúng phạm vi chưa?
5. Mapping có hoàn tất khi context còn hợp lệ không?
6. DTO có chứa entity/proxy/collection JPA không?
7. Có nên dùng projection thay vì managed entity không?
8. Với collection, số rows join có thể lớn bao nhiêu?
9. Có phân trang root đồng thời fetch collection không?
10. Có chiến lược IDs/headers trước, children sau nếu cần không?
11. Trật tự child/parent có xác định không?
12. `IN` list có rỗng hoặc vượt giới hạn DB không?
13. Hai SELECT có cần cùng snapshot không?
14. Có quyền user/tenant hợp lệ cho mọi query không?
15. Đã đo số SELECT và SQL rows tới khi DTO tạo xong chưa?
16. Có test sau khi service transaction kết thúc không?
17. Cache test có đang che giấu N+1 không?
18. OSIV có đang che giấu lỗi boundary không?
19. Có collection quá lớn làm tăng memory không?
20. Transaction có giữ resource lâu không cần thiết không?

## 31. Tổng kết

Ranh giới tải dữ liệu trước DTO là sự kết hợp của **hợp đồng output**, **fetch plan** và **vòng đời persistence**.

~~~text
Request + access policy
          |
          v
  Xác định DTO contract
          |
   +------+----------------+
   |                       |
   v                       v
Cần managed graph?     Chỉ cần dữ liệu đọc?
   |                       |
   v                       v
JOIN FETCH / Graph      DTO projection
hoặc batch               hoặc header + children
   |                       |
   +-----------+-----------+
               |
               v
        Quan sát SQL,
        row count, pagination
               |
               v
        Hoàn tất DTO trong
        ranh giới hợp lệ
               |
               v
        DTO độc lập cho API
~~~

Những nguyên tắc quan trọng:

- Không để lazy loading bị quyết định tình cờ trong serializer hoặc controller.
- Không đổi mọi association sang EAGER; dùng fetch plan theo use case.
- `JOIN FETCH` và `EntityGraph` hữu ích cho entity graph nhưng không tự đảm bảo hiệu năng hoặc pagination collection.
- DTO projection phù hợp với read model; nested collection có thể cần nhiều query và grouping.
- Transaction cho phép mapping trong scope hợp lệ nhưng **không tự sửa N+1**.
- Với nhiều query, cần giữ đúng thứ tự, quyền truy cập và yêu cầu nhất quán dữ liệu.
- Đo SQL và kiểm thử sau khi rời transaction để xác minh ranh giới thực sự hoạt động.

**Thiết kế tốt là tải đủ để DTO hoàn chỉnh trước khi rời persistence context, đồng thời tránh tải những dữ liệu không được hợp đồng DTO hoặc nghiệp vụ yêu cầu.**
