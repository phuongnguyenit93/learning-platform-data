# Quản lý named native query và SQL đặc thù của hệ quản trị trong JPA

**Jakarta Persistence (JPA)** khuyến khích truy vấn theo mô hình entity bằng JPQL hoặc Criteria API. Tuy nhiên, đôi khi nghiệp vụ cần những khả năng SQL mà JPQL không biểu diễn thuận tiện: *Common Table Expression* (CTE), window function, xử lý JSON, truy vấn báo cáo phức tạp, tính năng khóa của database hoặc các hàm riêng của PostgreSQL, MySQL, Oracle hay SQL Server.

JPA cho phép chạy **native SQL** trực tiếp. Khi một câu SQL đặc thù có cấu trúc ổn định, được tái sử dụng ở nhiều nơi, ta có thể **đặt tên** cho nó bằng `@NamedNativeQuery` rồi gọi qua `EntityManager.createNamedQuery(...)`.

Ví dụ:

~~~java
@NamedNativeQuery(
    name = "PurchaseOrder.findConfirmedNative",
    query = """
        SELECT o.id, o.order_code, o.customer_id,
               o.status, o.total_amount, o.created_at
        FROM purchase_orders o
        WHERE o.status = 'CONFIRMED'
        ORDER BY o.created_at DESC, o.id DESC
        """,
    resultClass = PurchaseOrder.class
)
~~~

Ở repository:

~~~java
List<PurchaseOrder> orders = em.createNamedQuery(
        "PurchaseOrder.findConfirmedNative",
        PurchaseOrder.class
    )
    .getResultList();
~~~

**Khác với `@NamedQuery`**, nội dung `query` ở trên là **SQL dùng tên bảng/cột vật lý**, không phải JPQL dùng tên entity/attribute Java.

Mục tiêu của bài học thuộc chương **Native SQL** là giúp bạn:

1. Khai báo và tái sử dụng **named native query** một cách có tổ chức.
2. Gọi truy vấn bằng API JPA, bind tham số và xử lý kết quả an toàn.
3. Phân biệt **entity mapping**, **scalar result**, **DTO projection** và `@SqlResultSetMapping`.
4. Quản lý SQL riêng cho từng hệ quản trị mà không rải phụ thuộc database khắp code nghiệp vụ.
5. Hiểu tác động của native SQL lên transaction, persistence context, cache và optimistic locking.
6. Kiểm chứng schema, kiểu dữ liệu, hiệu năng, quyền truy cập và tính khả chuyển bằng integration test.

Điểm cốt lõi: **`@NamedNativeQuery` làm cho SQL đặc thù dễ quản lý và tái sử dụng; nó không tự biến SQL đó thành một truy vấn portable giữa mọi database.**

---

## 1. Khi nào cần native SQL?

Với một truy vấn đơn giản, JPQL thường đã đủ:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.createdAt DESC
~~~

JPQL có ưu điểm:

- Tham chiếu `PurchaseOrder` và các thuộc tính Java.
- JPA provider chuyển thành SQL theo mapping và dialect.
- Có tính khả chuyển cao hơn cho những cấu trúc chuẩn.
- Dễ tích hợp với entity lifecycle, typed query và fetch plan.

Trong khi đó, SQL chuyên biệt có thể cần:

~~~sql
SELECT
    o.customer_id,
    DATE_TRUNC('month', o.created_at) AS month_start,
    SUM(o.total_amount) AS monthly_revenue
FROM purchase_orders o
WHERE o.status = 'CONFIRMED'
GROUP BY o.customer_id, DATE_TRUNC('month', o.created_at)
ORDER BY o.customer_id, month_start;
~~~

`DATE_TRUNC` là ví dụ hàm thường dùng trên PostgreSQL, nhưng không phải cú pháp giống nhau trên mọi hệ quản trị.

Một trường hợp khác là window function:

~~~sql
SELECT
    o.id,
    o.customer_id,
    o.total_amount,
    ROW_NUMBER() OVER (
        PARTITION BY o.customer_id
        ORDER BY o.created_at DESC, o.id DESC
    ) AS customer_row_number
FROM purchase_orders o;
~~~

Đây là loại truy vấn có thể dễ đọc và tối ưu hơn khi viết trực tiếp bằng SQL đặc thù, tùy phiên bản Jakarta Persistence và database đang sử dụng.

**Đừng dùng native SQL chỉ vì nó quen thuộc hơn.** Với CRUD và điều kiện lọc đơn giản, JPQL/Criteria thường làm code ít phụ thuộc schema vật lý hơn.

## 2. Phân biệt bốn cơ chế truy vấn

| Cơ chế | Ngôn ngữ | Cách gọi | Tình huống phù hợp |
| --- | --- | --- | --- |
| `EntityManager.createQuery(...)` | JPQL hoặc Criteria | Cung cấp truy vấn tại runtime | Truy vấn portable, đơn giản/động |
| `@NamedQuery` | JPQL | `createNamedQuery(name)` | JPQL tĩnh, tái sử dụng |
| `EntityManager.createNativeQuery(...)` | SQL native | Cung cấp SQL tại runtime | SQL đặc thù được tạo tại thời điểm chạy |
| `@NamedNativeQuery` | SQL native | `createNamedQuery(name)` | SQL đặc thù có cấu trúc ổn định, cần quản lý tập trung |

Ví dụ đối chiếu:

~~~java
// JPQL động:
em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.status = :status",
    PurchaseOrder.class
);

// Native SQL động:
em.createNativeQuery(
    "SELECT * FROM purchase_orders WHERE status = ?1",
    PurchaseOrder.class
);

// Named JPQL:
em.createNamedQuery(
    "PurchaseOrder.findByStatus",
    PurchaseOrder.class
);

// Named native SQL:
em.createNamedQuery(
    "PurchaseOrder.findByStatusNative",
    PurchaseOrder.class
);
~~~

`createNamedQuery` được dùng cho **cả named JPQL lẫn named native query**. API này tra cứu tên đã đăng ký; người gọi không phải truyền lại nội dung SQL.

### 2.1. Named native query không phải stored procedure

Một named native query là một **câu SQL được khai báo trong metadata** của JPA. Nó không phải:

- Stored procedure được cài vào database.
- Database view hay materialized view.
- Một bảng kết quả đã lưu.
- Một transaction độc lập.
- Một SQL prepared statement được giữ mãi từ lúc startup.

JPA có `StoredProcedureQuery` cho trường hợp gọi stored procedure. Việc chọn giữa chúng phụ thuộc chức năng database và hợp đồng tham số/kết quả.

## 3. Cấu trúc annotation @NamedNativeQuery

Các thành phần thường gặp:

~~~java
@NamedNativeQuery(
    name = "PurchaseOrder.findByStatusNative",
    query = """
        SELECT o.id, o.order_code, o.customer_id,
               o.status, o.total_amount, o.created_at
        FROM purchase_orders o
        WHERE o.status = ?1
        ORDER BY o.created_at DESC, o.id DESC
        """,
    resultClass = PurchaseOrder.class
)
~~~

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `name` | Tên định danh của truy vấn trong persistence unit |
| `query` | Câu SQL native, dùng tên bảng/cột database |
| `resultClass` | Class kết quả khi có mapping trực tiếp phù hợp, thường là entity |
| `resultSetMapping` | Tên `@SqlResultSetMapping` khi cần ánh xạ kết quả phức tạp |
| `hints` | Query hints, tùy khả năng provider |

**`resultClass` và `resultSetMapping` là hai hướng mô tả kết quả**; không nên đặt cả hai như hai chiến lược mapping mâu thuẫn cho cùng một query.

Tên truy vấn là **định danh metadata**, không phải tên table hay method Java. Quy ước thường dùng:

~~~text
PurchaseOrder.findByStatusNative
PurchaseOrder.overviewNative
PurchaseOrder.countByCustomerNative
PurchaseOrder.cancelDraftNative
Report.monthlyRevenuePostgres
Report.latestOrdersPerCustomerPostgres
~~~

Tên phải đủ rõ để người khác nhận biết một truy vấn là **native** và nếu có, **gắn với một dialect cụ thể**.

### 3.1. Phạm vi tên là persistence unit

Dù `@NamedNativeQuery` được đặt trên entity `PurchaseOrder`, tên truy vấn được đăng ký trong phạm vi **persistence unit**, chứ không thuộc riêng một Java object.

Vì vậy:

~~~java
em.createNamedQuery("PurchaseOrder.findByStatusNative");
~~~

không cần tạo instance `PurchaseOrder`.

Cần tránh xung đột giữa những định nghĩa tên truy vấn. Tên của named native query không nên trùng với named JPQL query trong cùng persistence unit; đừng giả định hai annotation có namespace tách biệt chỉ vì SQL khác nhau.

## 4. Mô hình ví dụ: Customer và PurchaseOrder

Bài học sử dụng Java 17+ và package `jakarta.persistence`. Với các dự án JPA 2.x sử dụng `javax.persistence`, cần áp dụng dependency, annotation và cấu hình theo phiên bản tương ứng.

### 4.1. Enum OrderStatus

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

### 4.2. Entity Customer

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

    @Column(name = "email", nullable = false, unique = true, length = 180)
    private String email;

    @Column(name = "full_name", nullable = false, length = 160)
    private String fullName;

    protected Customer() {
    }

    public Customer(String email, String fullName) {
        this.email = email;
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

### 4.3. Entity PurchaseOrder với native queries

~~~java
package com.example.shop.domain;

import com.example.shop.dto.OrderOverview;
import jakarta.persistence.Column;
import jakarta.persistence.ConstructorResult;
import jakarta.persistence.ColumnResult;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.NamedNativeQueries;
import jakarta.persistence.NamedNativeQuery;
import jakarta.persistence.SqlResultSetMapping;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "purchase_orders")
@NamedNativeQueries({
    @NamedNativeQuery(
        name = "PurchaseOrder.findByCustomerAndStatusNative",
        query = """
            SELECT o.id, o.order_code, o.customer_id,
                   o.status, o.total_amount, o.created_at
            FROM purchase_orders o
            WHERE o.customer_id = ?1
              AND o.status = ?2
            ORDER BY o.created_at DESC, o.id DESC
            """,
        resultClass = PurchaseOrder.class
    ),
    @NamedNativeQuery(
        name = "PurchaseOrder.countByStatusNative",
        query = """
            SELECT COUNT(*)
            FROM purchase_orders o
            WHERE o.status = ?1
            """
    ),
    @NamedNativeQuery(
        name = "PurchaseOrder.overviewByCustomerNative",
        query = """
            SELECT
                o.id AS order_id,
                o.order_code AS order_code,
                c.email AS customer_email,
                o.total_amount AS total_amount
            FROM purchase_orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE o.customer_id = ?1
            ORDER BY o.id DESC
            """,
        resultSetMapping = "OrderOverviewMapping"
    )
})
@SqlResultSetMapping(
    name = "OrderOverviewMapping",
    classes = @ConstructorResult(
        targetClass = OrderOverview.class,
        columns = {
            @ColumnResult(name = "order_id", type = Long.class),
            @ColumnResult(name = "order_code", type = String.class),
            @ColumnResult(name = "customer_email", type = String.class),
            @ColumnResult(name = "total_amount", type = BigDecimal.class)
        }
    )
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(
        name = "total_amount",
        precision = 15,
        scale = 2,
        nullable = false
    )
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

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

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
~~~

Một số điểm cần lưu ý:

- Các định nghĩa `@NamedNativeQuery` là **metadata**; chưa thực thi SQL khi khai báo.
- `findByCustomerAndStatusNative` ánh xạ kết quả thành **entity**.
- `countByStatusNative` trả về giá trị **scalar**, không phải entity.
- `overviewByCustomerNative` dùng `@SqlResultSetMapping` để tạo **DTO**.
- `?1` và `?2` là tham số vị trí trong ví dụ. Cú pháp/khả năng native positional parameter phải được xác nhận với provider và phiên bản JPA đang dùng.
- `@Enumerated(EnumType.STRING)` mô tả mapping enum cho entity, nhưng **binding một enum trực tiếp vào native SQL không phải lúc nào cũng được chuyển đổi như JPQL**. Với cột `VARCHAR` như ví dụ, repository có thể bind giá trị `status.name()`.
- SQL dùng `purchase_orders`, `customer_id`, `total_amount` vì đây là **tên vật lý trong database**.

### 4.4. DTO cho constructor mapping

~~~java
package com.example.shop.dto;

import java.math.BigDecimal;

public record OrderOverview(
    Long orderId,
    String orderCode,
    String customerEmail,
    BigDecimal totalAmount
) {
}
~~~

Record Java có constructor với bốn argument theo thứ tự component. Trong `@ConstructorResult`, thứ tự cột phải khớp constructor tương ứng:

~~~text
order_id        -> Long
order_code      -> String
customer_email  -> String
total_amount    -> BigDecimal
~~~

Nếu driver trả một kiểu không tương thích, việc khai báo `@ColumnResult(type = ...)` có thể giúp xác định kiểu mong muốn, nhưng **không thay thế hoàn toàn khả năng chuyển đổi thực của provider/JDBC**.

### 4.5. Schema SQL minh họa

Ví dụ sử dụng hệ quản trị có cú pháp identity column phù hợp:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(180) NOT NULL UNIQUE,
    full_name VARCHAR(160) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(255) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

DDL chỉ nhằm minh họa cấu trúc bảng. Với native SQL, sự khác biệt giữa schema ở migration thực tế và tên bảng/cột đã hardcode trong query là vấn đề quan trọng: đổi `purchase_orders` thành `orders` trong database sẽ khiến named native query cũ không còn hợp lệ nếu chưa sửa/migrate tương ứng.

## 5. Gọi named native query có tham số

Repository:

~~~java
package com.example.shop.repository;

import com.example.shop.domain.OrderStatus;
import com.example.shop.domain.PurchaseOrder;
import jakarta.persistence.EntityManager;
import java.util.List;

public final class PurchaseOrderReader {

    private final EntityManager em;

    public PurchaseOrderReader(EntityManager em) {
        this.em = em;
    }

    public List<PurchaseOrder> findByCustomerAndStatus(
            long customerId,
            OrderStatus status) {

        return em.createNamedQuery(
                "PurchaseOrder.findByCustomerAndStatusNative",
                PurchaseOrder.class
            )
            .setParameter(1, customerId)
            .setParameter(2, status.name())
            .getResultList();
    }
}
~~~

Đây là một lần thực thi SQL cụ thể:

1. JPA tra cứu `PurchaseOrder.findByCustomerAndStatusNative` trong metadata.
2. Provider chuẩn bị native SQL tương ứng.
3. Repository binding hai giá trị vào query object.
4. `getResultList()` thực thi câu SELECT.
5. Provider ánh xạ các hàng phù hợp thành các entity `PurchaseOrder`.

**Tên named query không phải đường dẫn file hoặc tên method.** Sai một ký tự sẽ khiến JPA không tìm thấy metadata.

### 5.1. Tên tham số trong native SQL có portable không?

JPQL hỗ trợ tham số đặt tên:

~~~jpql
WHERE o.status = :status
~~~

Nhưng với **native SQL**, mức hỗ trợ tham số dạng `:status` khác nhau giữa các provider và các thế hệ JPA. Theo mô hình khả chuyển truyền thống của JPA, **tham số vị trí** là lựa chọn an toàn hơn.

Ví dụ native:

~~~sql
WHERE o.customer_id = ?1
  AND o.status = ?2
~~~

Binding:

~~~java
query.setParameter(1, customerId);
query.setParameter(2, status.name());
~~~

Cần phân biệt:

- `?1`, `?2` ở đây được provider diễn giải như **native query parameters**.
- SQL được gửi xuống JDBC có thể chứa placeholder `?` thay vì nguyên `?1`.
- Cú pháp native SQL và các extension có thể có cách parse tham số riêng; **phải thử trên provider/version thực tế**.
- Cú pháp tên tham số `:param` trong native SQL có thể là extension hữu ích nhưng không nên coi là hợp đồng portability cho mọi provider.

### 5.2. Không ghép input vào chuỗi SQL

Sai:

~~~java
String sql =
    "SELECT * FROM purchase_orders WHERE status = '" +
    userInput + "'";
~~~

Đúng hơn là dùng bind parameter:

~~~java
query.setParameter(1, allowedStatus);
~~~

Binding tránh việc input trở thành một phần cú pháp SQL, đồng thời giúp provider/JDBC xử lý giá trị và kiểu phù hợp.

Tuy nhiên parameter **không thay thế tên bảng, tên cột, ORDER BY field hay tên hàm SQL**. Nếu cần lựa chọn động các thành phần cấu trúc, phải dùng whitelist do ứng dụng kiểm soát.

## 6. getResultList, getSingleResult và executeUpdate

### 6.1. Truy vấn danh sách

~~~java
List<PurchaseOrder> orders = em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatusNative",
        PurchaseOrder.class
    )
    .setParameter(1, customerId)
    .setParameter(2, OrderStatus.CONFIRMED.name())
    .getResultList();
~~~

Nếu không có hàng khớp, `getResultList()` trả danh sách rỗng.

### 6.2. Truy vấn scalar COUNT

Named query:

~~~sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = ?1
~~~

Gọi:

~~~java
Object result = em.createNamedQuery(
        "PurchaseOrder.countByStatusNative"
    )
    .setParameter(1, "CONFIRMED")
    .getSingleResult();

long count = ((Number) result).longValue();
~~~

**Tại sao dùng `Number` thay vì ép thẳng `Long`?** Với native SQL, provider/driver có thể trả về những kiểu số Java khác nhau, chẳng hạn `Long` hoặc `BigInteger` tùy phiên bản và cơ chế mapping. Khi metadata mapping không cam kết cụ thể, chuyển qua `Number` phù hợp hơn.

Không làm:

~~~java
Long count = (Long) query.getSingleResult();
~~~

nếu chưa xác nhận chính xác result type. Với một query count có mapping riêng bằng `@ColumnResult(type = Long.class)`, có thể xây contract kiểu mạnh hơn, nhưng vẫn cần kiểm tra trên runtime thực tế.

### 6.3. Một bản ghi duy nhất

~~~java
PurchaseOrder order = em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatusNative",
        PurchaseOrder.class
    )
    .setParameter(1, customerId)
    .setParameter(2, "CONFIRMED")
    .getSingleResult();
~~~

Nếu query có thể trả nhiều order, `getSingleResult()` không phải lựa chọn đúng:

- Không có kết quả: có thể ném `NoResultException`.
- Nhiều kết quả: có thể ném `NonUniqueResultException`.

Hãy dùng một query thật sự có tính duy nhất, hoặc `getResultList()` với phân trang/giới hạn tùy nghiệp vụ.

### 6.4. Cập nhật hoặc xóa bằng native query

Native SQL không bắt buộc là SELECT. Một câu `UPDATE` hoặc `DELETE` cần:

~~~java
int affected = em.createNamedQuery(
        "PurchaseOrder.cancelDraftNative"
    )
    .setParameter(1, "CANCELLED")
    .setParameter(2, "DRAFT")
    .executeUpdate();
~~~

`executeUpdate()` trả số lượng được JPA báo là bị ảnh hưởng. Cần có **transaction ghi phù hợp**, và phải xử lý các hệ quả đối với persistence context (được giải thích ở phần sau).

## 7. Ánh xạ native result về entity

Cấu hình:

~~~java
@NamedNativeQuery(
    name = "PurchaseOrder.findByCustomerAndStatusNative",
    query = """
        SELECT o.id, o.order_code, o.customer_id,
               o.status, o.total_amount, o.created_at
        FROM purchase_orders o
        WHERE o.customer_id = ?1
          AND o.status = ?2
        """,
    resultClass = PurchaseOrder.class
)
~~~

cho biết kết quả SQL cần được dùng để tạo/định vị entity `PurchaseOrder` theo mapping JPA.

**Không chỉ cần cột ID.** Đối với native result mapping trực tiếp về entity, cần cung cấp đủ các cột mà provider cần để materialize entity đúng, bao gồm các cột mapped và FK thích hợp theo entity mapping. Nếu thiếu, kết quả có thể gây lỗi SQL/JDBC, mapping exception hoặc hành vi không portable.

### 7.1. SELECT * có tiện nhưng không phải luôn tốt nhất

Ví dụ:

~~~sql
SELECT o.*
FROM purchase_orders o
WHERE o.id = ?1;
~~~

Dạng này thường dễ dùng khi một bảng chứa đầy đủ field của một entity đơn giản. Nhưng:

- Schema thêm cột có thể làm result rộng hơn.
- JOIN nhiều bảng với `SELECT *` tạo tên cột trùng nhau.
- Entity inheritance hoặc secondary table mapping phức tạp hơn một bảng.
- Thay đổi schema có thể ảnh hưởng query ngoài dự kiến.

Nếu cần kết quả entity rõ ràng và schema ổn định, chọn đủ cột có alias phù hợp thường dễ kiểm soát hơn.

### 7.2. Native entity result vẫn tham gia persistence context

Khi `EntityManager` trả entity từ native query:

- JPA nhận diện entity theo identity/mapping của persistence unit.
- Entity có thể trở thành managed trong context hiện hành.
- Nếu một entity cùng ID đã managed, provider quản lý tính nhất quán identity trong context.
- Việc sửa managed entity có thể được dirty checking theo transaction.
- Những quan hệ LAZY chưa tải vẫn có thể phát sinh SQL khi truy cập.

**Native query không có nghĩa kết quả entity luôn là DTO detached.** Kết quả phụ thuộc kiểu result mapping đã khai báo.

### 7.3. Native JOIN không luôn đồng nghĩa fetch association

Câu:

~~~sql
SELECT o.*
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.email = ?1
~~~

có JOIN để **lọc** đơn hàng, nhưng chỉ chọn các cột của `o`. Đừng mặc định entity `o.customer` đã được khởi tạo và tất cả trường Customer đều có sẵn.

Nếu ứng dụng sau đó duyệt:

~~~java
for (PurchaseOrder o : orders) {
    System.out.println(o.getCustomer().getEmail());
}
~~~

provider có thể phải chạy SQL bổ sung, tùy fetch strategy và cache. Native JOIN cho điều kiện lọc không phải cơ chế fetch join JPQL tương đương một cách tự động.

Với màn hình chỉ cần email, DTO projection thường rõ hơn việc yêu cầu ORM materialize toàn bộ object graph.

## 8. Khi cần @SqlResultSetMapping

Native query có thể trả:

- Entity đơn.
- Một scalar như COUNT.
- Nhiều cột scalar dưới dạng `Object[]`.
- DTO với constructor.
- Nhiều entity ở cùng một row.
- Tổ hợp entity và scalar.

`@SqlResultSetMapping` cho phép khai báo **cách chuyển SQL ResultSet thành kết quả Java** có tên riêng.

Ví dụ:

~~~java
@SqlResultSetMapping(
    name = "OrderOverviewMapping",
    classes = @ConstructorResult(
        targetClass = OrderOverview.class,
        columns = {
            @ColumnResult(name = "order_id", type = Long.class),
            @ColumnResult(name = "order_code", type = String.class),
            @ColumnResult(name = "customer_email", type = String.class),
            @ColumnResult(
                name = "total_amount",
                type = BigDecimal.class
            )
        }
    )
)
~~~

Câu SQL phải cung cấp các alias tương ứng:

~~~sql
SELECT
    o.id AS order_id,
    o.order_code AS order_code,
    c.email AS customer_email,
    o.total_amount AS total_amount
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id = ?1;
~~~

**Alias SQL là hợp đồng giữa query và mapping.** Nếu đổi `AS customer_email` thành `AS email_address` mà không cập nhật `@ColumnResult(name = "customer_email")`, mapper có thể không tìm thấy cột mong đợi.

### 8.1. @ConstructorResult với DTO/record

Record:

~~~java
public record OrderOverview(
    Long orderId,
    String orderCode,
    String customerEmail,
    BigDecimal totalAmount
) {
}
~~~

Khi provider hỗ trợ chuyển đổi kiểu như khai báo, mỗi row sẽ được truyền vào constructor:

~~~text
SQL row:
  order_id       = 101
  order_code     = PO-101
  customer_email = a@example.com
  total_amount   = 210.50

                |
                v

new OrderOverview(101L, "PO-101", "a@example.com", 210.50)
~~~

DTO này **không phải JPA entity managed**. Việc sửa component (nếu là mutable DTO) hoặc tạo record mới không được đồng bộ tới database bằng dirty checking.

### 8.2. Lấy kết quả DTO

~~~java
List<OrderOverview> result = em.createNamedQuery(
        "PurchaseOrder.overviewByCustomerNative",
        OrderOverview.class
    )
    .setParameter(1, customerId)
    .getResultList();
~~~

Khi dùng `createNamedQuery(name, ResultClass.class)`, runtime/provider cần nhận diện kết quả theo `resultSetMapping` đúng kiểu. Với provider/phiên bản không tương thích typed result cho một mapping phức tạp, có thể dùng overload không typed rồi chuyển kết quả một cách có kiểm soát.

Đừng mặc định một `@SqlResultSetMapping` bất kỳ trả entity chỉ vì annotation được đặt trên entity class.

### 8.3. @ColumnResult dùng cho scalar

Một result mapping chỉ chứa scalar có thể khai báo:

~~~java
@SqlResultSetMapping(
    name = "MonthlyRevenueScalars",
    columns = {
        @ColumnResult(name = "month_start"),
        @ColumnResult(name = "monthly_revenue", type = BigDecimal.class)
    }
)
~~~

SQL:

~~~sql
SELECT
    DATE_TRUNC('month', created_at) AS month_start,
    SUM(total_amount) AS monthly_revenue
FROM purchase_orders
WHERE status = 'CONFIRMED'
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month_start;
~~~

Nếu một row có nhiều scalar, JPA thường trả kết quả dạng `Object[]` theo quy tắc mapping; kiểu chính xác của `month_start` phụ thuộc driver/provider nếu không khai báo rõ.

Khi làm báo cáo, tốt hơn nên có một DTO conversion ở repository để tầng service không phải xử lý `Object[]` hoặc JDBC-specific types.

## 9. @EntityResult và @FieldResult khi alias phức tạp

Khi native SQL JOIN nhiều bảng và tên cột bị trùng, có thể cần `@EntityResult` và `@FieldResult`.

Ví dụ hai bảng cùng có cột `id`:

~~~sql
SELECT
    o.id AS order_pk,
    o.order_code AS order_code,
    o.customer_id AS customer_fk,
    o.status AS order_status,
    o.total_amount AS order_total,
    o.created_at AS order_created,
    c.id AS customer_pk,
    c.email AS customer_email,
    c.full_name AS customer_full_name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id;
~~~

Nếu muốn provider tạo entity từ alias `order_pk` và `order_status`, một mapping tường minh có thể trông như:

~~~java
@SqlResultSetMapping(
    name = "OrderEntityAliased",
    entities = @EntityResult(
        entityClass = PurchaseOrder.class,
        fields = {
            @FieldResult(name = "id", column = "order_pk"),
            @FieldResult(
                name = "orderCode",
                column = "order_code"
            ),
            @FieldResult(
                name = "customer",
                column = "customer_fk"
            ),
            @FieldResult(
                name = "status",
                column = "order_status"
            ),
            @FieldResult(
                name = "totalAmount",
                column = "order_total"
            ),
            @FieldResult(
                name = "createdAt",
                column = "order_created"
            )
        }
    )
)
~~~

Điểm cần nhớ:

- `name` trong `@FieldResult` là **thuộc tính JPA** của entity.
- `column` là **alias/cột trong SQL ResultSet**.
- Quan hệ `@ManyToOne` có thể cần ánh xạ cột FK hoặc quy tắc ánh xạ đặc thù theo provider.
- Khóa chính entity cần được xác định đầy đủ.
- Với entity inheritance, composite key, secondary table hoặc nhiều entity trong một result, cấu hình có thể phức tạp hơn rất nhiều.

**Ví dụ trên chỉ minh họa cách khai báo metadata alias**, không phải tuyên bố rằng mọi provider sẽ hỗ trợ mọi mô hình association/inheritance giống nhau trong native result mapping. Với entity đơn giản, `resultClass` thường dễ bảo trì hơn.

### 9.1. Mapping nhiều entity cùng một hàng

Một `@SqlResultSetMapping` có thể có nhiều `@EntityResult`. Khi query chọn cả `PurchaseOrder` và `Customer`, provider có thể trả mỗi hàng dưới dạng `Object[]` chứa các entity được ánh xạ.

Điều đó không biến SQL join thành một JPQL fetch join một cách tự động; application vẫn cần hiểu kiểu kết quả, quan hệ và identity của từng object. Nếu API chỉ cần vài cột từ cả hai bảng, **DTO mapping** thường đơn giản hơn nhiều.

## 10. Scalar result: vì sao không luôn cast được kiểu?

Native SQL:

~~~sql
SELECT COUNT(*) AS total_count
FROM purchase_orders;
~~~

Provider có thể trả `Long`, `BigInteger` hoặc một lớp `Number` khác tùy driver/ORM/version.

An toàn hơn:

~~~java
Number total = (Number) query.getSingleResult();

long count = total.longValue();
~~~

Nếu cần kiểu cố định, có thể xem xét mapping:

~~~java
@SqlResultSetMapping(
    name = "LongCountMapping",
    columns = @ColumnResult(
        name = "total_count",
        type = Long.class
    )
)
~~~

Nhưng vẫn cần xác nhận trên database/provider mà dự án hỗ trợ.

Tương tự:

- `DECIMAL/NUMERIC` thường phù hợp với `BigDecimal`.
- `DATE`, `TIMESTAMP` có thể trở thành các kiểu JDBC/Java time khác nhau.
- `UUID` có thể cần driver/provider mapping cụ thể.
- `JSON/JSONB` có thể trả đối tượng riêng của driver nếu chưa có mapper.
- Array và geometry có thể yêu cầu extension.

Đây là lý do native query đặc thù không chỉ là thay chuỗi JPQL bằng SQL; cần xem xét **hợp đồng kiểu dữ liệu ở ranh giới JDBC**.

## 11. Phân trang và sắp xếp native query

`Query` có các API chung:

~~~java
List<PurchaseOrder> page = em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatusNative",
        PurchaseOrder.class
    )
    .setParameter(1, customerId)
    .setParameter(2, "CONFIRMED")
    .setFirstResult(40)
    .setMaxResults(20)
    .getResultList();
~~~

Điểm cần kiểm tra:

- Provider có hỗ trợ phân trang cho loại native query đó theo dialect không?
- SQL được render thành `LIMIT/OFFSET`, `FETCH FIRST` hay cách khác?
- Có `ORDER BY` xác định để các trang ổn định không?
- Mapping result có khiến số hàng SQL khác số entity trả về không?
- Câu query đã tự viết `LIMIT` chưa, có gây áp giới hạn hai lần khi gọi `setMaxResults` không?

### 11.1. ORDER BY không ổn định gây lặp dữ liệu giữa các trang

Nếu chỉ viết:

~~~sql
ORDER BY o.created_at DESC
~~~

và nhiều đơn có cùng `created_at`, thứ tự giữa các row trùng giá trị không được bảo đảm.

Nên bổ sung khóa phân biệt:

~~~sql
ORDER BY o.created_at DESC, o.id DESC
~~~

Với dữ liệu thường xuyên thay đổi, offset pagination vẫn có thể lặp/bỏ bản ghi giữa các request. Khi cần độ ổn định và tốc độ cao, cân nhắc keyset pagination theo đúng tập khóa sort.

### 11.2. SQL native đặc thù có thể tự kiểm soát phân trang

Truy vấn báo cáo nâng cao có thể chủ động dùng window function hoặc CTE để phân trang theo nhóm. Khi đó, không nên áp `setMaxResults` như một “điều chỉnh vô hại” nếu query đã có logic giới hạn bên trong.

Điều quan trọng là bảo đảm cùng một hợp đồng **offset, limit, sort và total count** được thực hiện nhất quán, bất kể syntax database.

## 12. Named native query chuyên biệt PostgreSQL: date_trunc

Giả sử cần tính doanh thu theo tháng:

~~~sql
SELECT
    DATE_TRUNC('month', o.created_at) AS month_start,
    SUM(o.total_amount) AS monthly_revenue
FROM purchase_orders o
WHERE o.status = ?1
GROUP BY DATE_TRUNC('month', o.created_at)
ORDER BY month_start;
~~~

Cú pháp `DATE_TRUNC('month', ...)` là ví dụ của PostgreSQL. Có thể khai báo:

~~~java
@NamedNativeQuery(
    name = "Report.monthlyRevenuePostgres",
    query = """
        SELECT
            DATE_TRUNC('month', o.created_at) AS month_start,
            SUM(o.total_amount) AS monthly_revenue
        FROM purchase_orders o
        WHERE o.status = ?1
        GROUP BY DATE_TRUNC('month', o.created_at)
        ORDER BY month_start
        """,
    resultSetMapping = "MonthlyRevenueMapping"
)
~~~

DTO:

~~~java
public record MonthlyRevenue(
    java.time.LocalDateTime monthStart,
    java.math.BigDecimal revenue
) {
}
~~~

Mapping mong muốn:

~~~java
@SqlResultSetMapping(
    name = "MonthlyRevenueMapping",
    classes = @ConstructorResult(
        targetClass = MonthlyRevenue.class,
        columns = {
            @ColumnResult(
                name = "month_start",
                type = java.time.LocalDateTime.class
            ),
            @ColumnResult(
                name = "monthly_revenue",
                type = java.math.BigDecimal.class
            )
        }
    )
)
~~~

**Cần kiểm tra kiểu dữ liệu thực** của `date_trunc` tùy kiểu cột `TIMESTAMP`, JDBC driver và JPA provider. Nếu provider không thể chuyển trực tiếp về `LocalDateTime`, repository có thể dùng scalar mapping trung gian rồi chuyển kiểu.

### 12.1. Một query tương tự trên MySQL không có cùng SQL

MySQL thường dùng hàm như:

~~~sql
SELECT
    DATE_FORMAT(o.created_at, '%Y-%m') AS month_key,
    SUM(o.total_amount) AS monthly_revenue
FROM purchase_orders o
WHERE o.status = ?
GROUP BY DATE_FORMAT(o.created_at, '%Y-%m')
ORDER BY month_key;
~~~

Khác biệt:

- Tên hàm khác nhau.
- `DATE_FORMAT` thường trả **chuỗi**, không phải timestamp.
- Quy tắc timezone, collation, date arithmetic có thể khác.
- Cú pháp/kiểu tham số native SQL còn phụ thuộc provider.

Do đó không thể giữ nguyên DTO `MonthlyRevenue(LocalDateTime, BigDecimal)` trên MySQL mà không có **lớp chuyển đổi** tương thích.

### 12.2. Dùng chung một API nghiệp vụ

Service chỉ nên biết hợp đồng:

~~~java
public interface RevenueReportRepository {
    List<MonthlyRevenue> monthlyRevenue(OrderStatus status);
}
~~~

Phần PostgreSQL và MySQL có thể dùng SQL khác nhau nhưng **trả cùng kiểu kết quả nghiệp vụ**, sau khi repository chuyển kiểu và chuẩn hóa ranh giới thời gian.

Không rải điều kiện `if postgres ... else mysql ...` khắp service/controller.

## 13. PostgreSQL JSONB và SQL đặc thù

Giả sử bảng `customers` có cột JSONB `preferences`:

~~~sql
ALTER TABLE customers
ADD COLUMN preferences JSONB;
~~~

Ví dụ dữ liệu:

~~~sql
UPDATE customers
SET preferences = '{"tier":"GOLD","locale":"vi-VN"}'::jsonb
WHERE id = 42;
~~~

PostgreSQL có hàm để lấy giá trị text của một key JSONB:

~~~sql
SELECT
    c.id,
    c.email
FROM customers c
WHERE jsonb_extract_path_text(c.preferences, 'tier') = 'GOLD';
~~~

Named native query:

~~~java
@NamedNativeQuery(
    name = "Customer.findByPreferenceTierPostgres",
    query = """
        SELECT c.id, c.email, c.full_name
        FROM customers c
        WHERE jsonb_extract_path_text(c.preferences, 'tier') = ?1
        """,
    resultClass = Customer.class
)
~~~

Ở ví dụ này, query trả entity `Customer` theo các cột mapped của entity. Cột `preferences` chưa được mapping thành field Java trong entity mẫu; nếu sau này thêm field mapping JSON, result class và SQL phải được xem lại để bảo đảm mapping đầy đủ.

Cách gọi:

~~~java
List<Customer> goldCustomers = em.createNamedQuery(
        "Customer.findByPreferenceTierPostgres",
        Customer.class
    )
    .setParameter(1, "GOLD")
    .getResultList();
~~~

### 13.1. Không nhầm JSON của PostgreSQL với MySQL

MySQL có các hàm như `JSON_EXTRACT` và `JSON_UNQUOTE`. SQL tương ứng có thể mang ý tưởng:

~~~sql
SELECT c.id, c.email, c.full_name
FROM customers c
WHERE JSON_UNQUOTE(
    JSON_EXTRACT(c.preferences, '$.tier')
) = ?;
~~~

Những điều cần so sánh trước khi dùng cùng contract:

- Cột JSONB hay JSON.
- Kiểu giá trị trả về.
- Quy tắc missing key và JSON null.
- Index hỗ trợ JSON path.
- Cách optimizer xử lý biểu thức.
- Quy tắc escape của path expression.
- Tính năng SQL có mặt từ phiên bản DB nào.

**`@NamedNativeQuery` không tự dịch một hàm PostgreSQL sang hàm MySQL.**

### 13.2. Chú ý toán tử riêng và parameter parser

PostgreSQL có toán tử và cú pháp cast đặc thù như `::jsonb`, `->` hoặc `->>`. Một số SQL parser phía ORM có thể nhầm ký tự `:` trong `::` với cú pháp named parameter của native query, tùy phiên bản/provider.

Nếu gặp lỗi liên quan tới parser, có thể cân nhắc dạng:

~~~sql
CAST(?1 AS jsonb)
~~~

khi phù hợp, hoặc SQL function/driver binding khác, thay vì giả định mọi cú pháp vendor-specific luôn đi qua JPA parser nguyên vẹn.

Cần kiểm tra cả cách bind JSON trong JDBC; một `String` không phải lúc nào cũng được database tự chuyển sang JSONB đúng mong muốn.

## 14. CTE và window function trong named native query

Một báo cáo muốn lấy **đơn hàng mới nhất của từng khách hàng**.

Với database hỗ trợ window function:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.id,
        o.customer_id,
        o.order_code,
        o.created_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.id DESC
        ) AS row_rank
    FROM purchase_orders o
    WHERE o.status = ?1
)
SELECT
    r.id,
    r.customer_id,
    r.order_code,
    r.created_at
FROM ranked_orders r
WHERE r.row_rank = 1
ORDER BY r.customer_id;
~~~

Điểm dễ mắc lỗi:

- Query chỉ chọn **bốn cột**, không đủ để ánh xạ toàn bộ `PurchaseOrder` mẫu (thiếu `status` và `total_amount`). Vì vậy **không nên khai báo `resultClass = PurchaseOrder.class`** cho SQL này nếu không bổ sung những cột cần thiết.
- Nên trả **DTO** phù hợp với bốn cột, hoặc chọn đầy đủ cột entity khi thực sự muốn managed entity.
- `ROW_NUMBER()` và CTE support/optimizer phụ thuộc database và phiên bản.
- Thứ tự phụ `id DESC` giúp chọn một đơn duy nhất khi thời gian trùng nhau.

DTO:

~~~java
public record LatestOrderRow(
    Long orderId,
    Long customerId,
    String orderCode,
    java.time.LocalDateTime createdAt
) {
}
~~~

Có thể dùng `@SqlResultSetMapping` với constructor và alias phù hợp, hoặc chuyển `Object[]` ở repository khi contract kiểu đã được kiểm chứng.

### 14.1. Vì sao không chỉ dùng SELECT MAX(created_at)?

Một query:

~~~sql
SELECT customer_id, MAX(created_at)
FROM purchase_orders
GROUP BY customer_id;
~~~

trả thời điểm tối đa, **không tự chỉ định được bản ghi order duy nhất** khi nhiều order cùng timestamp.

Window function với `ROW_NUMBER()` và tie-breaker ID giúp diễn đạt rõ quy tắc “mới nhất”, nhưng vẫn cần test ở database mục tiêu.

## 15. Cơ chế @NamedNativeQueries và quản lý nhiều truy vấn

Khi có nhiều query liên quan tới một entity:

~~~java
@NamedNativeQueries({
    @NamedNativeQuery(
        name = "PurchaseOrder.findRecentNative",
        query = """
            SELECT o.id, o.order_code, o.customer_id,
                   o.status, o.total_amount, o.created_at
            FROM purchase_orders o
            WHERE o.created_at >= ?1
            ORDER BY o.created_at DESC, o.id DESC
            """,
        resultClass = PurchaseOrder.class
    ),
    @NamedNativeQuery(
        name = "PurchaseOrder.countAllNative",
        query = "SELECT COUNT(*) FROM purchase_orders"
    )
})
~~~

Các query có tên khác nhau, đều thuộc phạm vi persistence unit.

Lợi ích:

- Tránh copy SQL ở nhiều repository/service.
- Có thể đặt convention tên.
- Metadata có thể được provider xử lý cùng quá trình khởi tạo persistence unit.
- Mọi caller dùng cùng cấu trúc SQL.

Nhược điểm:

- Entity class có thể phình to nếu chứa quá nhiều báo cáo SQL dài.
- SQL PostgreSQL có thể nằm trong entity dùng chung với build MySQL.
- Đổi schema khiến cả query native cần sửa đồng bộ.
- Refactor tên cột không được compiler Java tự phát hiện.

Vì vậy named native query nên có **chính sách tổ chức**, không phải chỉ là “đặt mọi SQL vào annotation”.

## 16. Khai báo named native query trong orm.xml

JPA hỗ trợ metadata XML để cấu hình truy vấn thay vì đặt tất cả annotation trên entity.

Ví dụ tách riêng vào `META-INF/orm.xml` theo schema Jakarta Persistence phù hợp:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.1">

    <named-native-query name="PurchaseOrder.findAllNative">
        <query><![CDATA[
            SELECT o.id, o.order_code, o.customer_id,
                   o.status, o.total_amount, o.created_at
            FROM purchase_orders o
            ORDER BY o.id DESC
        ]]></query>
        <result-class>com.example.shop.domain.PurchaseOrder</result-class>
    </named-native-query>

</entity-mappings>
~~~

Đây là ví dụ metadata cho môi trường Jakarta Persistence 3.1; đường dẫn, namespace/schema và cách đăng ký XML cần khớp phiên bản JPA đang dùng.

Đặc biệt, **đừng đăng ký hai truy vấn khác nội dung với cùng tên** trong annotation và XML nếu chưa hiểu quy tắc precedence/override. Cách tổ chức dễ quản lý là chọn **một nguồn định nghĩa rõ ràng** cho mỗi tên query trong một persistence unit.

### 16.1. Khi nào nên chọn XML?

Có thể hữu ích khi:

- SQL dài, không muốn đưa vào entity class.
- Cần nhiều cấu hình persistence unit riêng cho từng DB.
- Muốn nhóm query metadata cạnh các mapping khác.
- Dự án đã có quy trình phát hành cấu hình XML kiểm soát được.

Không có nghĩa XML luôn tốt hơn annotation. Với dự án nhỏ và một database, annotation có thể rất rõ ràng. Điều quan trọng là tên, phạm vi, versioning và kiểm thử được quản lý nhất quán.

## 17. Không có cơ chế tự động chuyển named native query giữa dialect

Một named native query có:

~~~sql
SELECT DATE_TRUNC('month', created_at)
FROM purchase_orders;
~~~

**không trở nên portable** chỉ vì PostgreSQL/MySQL đều được Hibernate hỗ trợ dưới dạng dialect.

JPA provider có thể:

- Bind parameters.
- Ánh xạ result.
- Áp dụng một số cơ chế pagination/hints theo khả năng.
- Thực thi native SQL qua JDBC.

Nhưng nó không có trách nhiệm chung phải **viết lại toàn bộ SQL PostgreSQL** thành SQL tương đương cho Oracle/MySQL/SQL Server. Trình dịch JPQL/Criteria khác với cách provider xử lý native SQL.

### 17.1. Các dạng phụ thuộc DB

| Tính năng | Phụ thuộc |
| --- | --- |
| Hàm `DATE_TRUNC` | PostgreSQL và DB có hỗ trợ tương thích |
| `JSONB`, `->>` | Kiểu JSON/toán tử của PostgreSQL |
| `DATE_FORMAT`, `JSON_EXTRACT` | MySQL và DB có các hàm tương ứng |
| `TOP`, `OFFSET FETCH`, `LIMIT` | Cú pháp phân trang theo dialect/version |
| `MERGE` hoặc vendor UPSERT | Ngữ nghĩa conflict handling |
| `RETURNING` | DML kết quả và khả năng JPA/provider nhận kết quả |
| `FOR UPDATE SKIP LOCKED` | Tính năng khóa và isolation từng DB |
| Window function/CTE | Phiên bản DB và cách optimizer xử lý |
| Quoted identifiers | Quy tắc chữ hoa/thường, dấu quote |
| Boolean/UUID/JSON/array | JDBC type và mapping |

Ngay cả SQL chạy trên hai DB cũng cần xem **kiểu kết quả, null handling, collation và transaction semantics**.

## 18. Thiết kế repository theo database adapter

Thay vì đặt SQL PostgreSQL và MySQL cùng trong một entity dùng chung không phân biệt môi trường, có thể tạo một interface:

~~~java
package com.example.shop.repository;

import com.example.shop.dto.MonthlyRevenue;
import java.util.List;

public interface RevenueReportRepository {
    List<MonthlyRevenue> findMonthlyRevenue(String status);
}
~~~

Hai implementation:

~~~text
                         RevenueReportRepository
                                  |
                     +------------+------------+
                     |                         |
                     v                         v
          PostgresRevenueRepository   MySqlRevenueRepository
                     |                         |
              DATE_TRUNC(...)            DATE_FORMAT(...)
                     |                         |
                 PostgreSQL                  MySQL
                     \                         /
                      +-----------+-----------+
                                  |
                           MonthlyRevenue DTO
~~~

Có thể quản lý query bằng hai cách:

**Cách A — named native query theo từng môi trường:** cung cấp metadata XML/persistence unit riêng, mỗi môi trường đăng ký những tên và SQL phù hợp. Nếu dùng cùng tên nghiệp vụ cho các SQL khác nhau, phải bảo đảm tại runtime **chỉ một định nghĩa** được đăng ký cho persistence unit đó.

**Cách B — native SQL tại repository adapter:** mỗi implementation dùng `createNativeQuery(...)` hoặc một lớp query builder riêng với SQL được đóng gói, tránh đăng ký một named query không tương thích DB ngay từ startup.

Không có quy tắc “named native query luôn tốt hơn createNativeQuery”. Nếu hai môi trường cần SQL rất khác nhau, repository adapter có thể rõ ràng hơn và tránh vấn đề metadata không hợp lệ trong môi trường không tương thích.

### 18.1. Ranh giới API nên trả dữ liệu nghiệp vụ

Ví dụ `MonthlyRevenue`:

~~~java
package com.example.shop.dto;

import java.math.BigDecimal;
import java.time.YearMonth;

public record MonthlyRevenue(
    YearMonth month,
    BigDecimal revenue
) {
}
~~~

Ở PostgreSQL, kết quả raw có thể là một timestamp tháng đầu. Ở MySQL, có thể là chuỗi `"2026-11"`. Repository adapter chịu trách nhiệm chuyển về **`YearMonth`**, và thống nhất quy tắc timezone.

Service chỉ nhận:

~~~java
List<MonthlyRevenue> monthlyRevenue =
    repository.findMonthlyRevenue("CONFIRMED");
~~~

Nó không cần biết `PGobject`, `DATE_FORMAT`, loại JDBC timestamp hay tên hàm cụ thể của database.

## 19. SQL native và transaction: SELECT khác DML

### 19.1. SELECT không tự commit

~~~java
List<PurchaseOrder> orders =
    em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatusNative",
        PurchaseOrder.class
    )
    .setParameter(1, customerId)
    .setParameter(2, "CONFIRMED")
    .getResultList();
~~~

Câu SELECT lấy dữ liệu theo transaction/persistence context của lần gọi. Việc thực thi SELECT **không tự tạo một commit**.

Trong một transaction, SQL SELECT có thể bị ảnh hưởng bởi isolation và những thay đổi managed chưa flush.

### 19.2. UPDATE/DELETE cần transaction phù hợp

Named native DML:

~~~java
@NamedNativeQuery(
    name = "PurchaseOrder.cancelDraftNative",
    query = """
        UPDATE purchase_orders
        SET status = ?1
        WHERE status = ?2
        """
)
~~~

Thực thi resource-local:

~~~java
em.getTransaction().begin();

try {
    int affected = em.createNamedQuery(
            "PurchaseOrder.cancelDraftNative"
        )
        .setParameter(1, "CANCELLED")
        .setParameter(2, "DRAFT")
        .executeUpdate();

    em.getTransaction().commit();

    System.out.println("Affected rows: " + affected);
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
}
~~~

Đây là ví dụ `RESOURCE_LOCAL`. Với JTA/Spring, transaction manager/container điều phối commit/rollback; không dùng `em.getTransaction()` trực tiếp trên JTA-managed `EntityManager`.

### 19.3. executeUpdate không đồng nghĩa transaction đã commit

`executeUpdate()` có thể thực thi SQL UPDATE trong transaction và trả số bản ghi ảnh hưởng. Transaction vẫn có thể rollback về sau.

Nếu service cần phát thông báo bên ngoài database, đừng xem số `affected > 0` là bằng chứng dữ liệu đã commit bền vững. Cần thiết kế after-commit event hoặc transactional outbox tùy yêu cầu độ tin cậy.

## 20. Native bulk DML có thể làm persistence context bị stale

Đây là điểm dễ gây lỗi nhất.

Giả sử:

~~~java
PurchaseOrder managed =
    em.find(PurchaseOrder.class, orderId);

System.out.println(managed.getStatus()); // DRAFT
~~~

Sau đó ứng dụng chạy native UPDATE:

~~~java
em.createNativeQuery(
    "UPDATE purchase_orders SET status = 'CONFIRMED' WHERE id = ?1"
)
.setParameter(1, orderId)
.executeUpdate();
~~~

Trong persistence context, object `managed` có thể vẫn giữ `status = DRAFT`. Database đã được cập nhật trong transaction, nhưng native SQL **không đồng nghĩa gọi setter trên managed entity**.

~~~text
Persistence context                 Database
-------------------                 -------------------
PurchaseOrder#101
  status = DRAFT                    row #101 status = DRAFT
         |                                    |
         | native SQL UPDATE                  |
         +----------------------------------->|
                                              v
                                     row #101 status = CONFIRMED

Managed object vẫn có thể là DRAFT nếu chưa refresh/clear.
~~~

Các hệ quả:

- Query/`find` về cùng entity có thể gặp trạng thái managed cũ.
- `@PreUpdate` và các lifecycle callbacks có thể không được gọi như một thay đổi entity bình thường.
- Những quan hệ cascade và orphan removal không tự chạy như khi sửa object graph managed.
- Nếu entity có `@Version`, native SQL không tự bảo đảm optimistic locking được tôn trọng.
- Second-level cache có thể cần provider-specific invalidation/synchronization.

### 20.1. Đồng bộ trước và sau native DML

Một workflow kiểm soát:

~~~java
em.flush(); // Đồng bộ pending changes trước DML khi phù hợp.

int changed = em.createNamedQuery(
        "PurchaseOrder.cancelDraftNative"
    )
    .setParameter(1, "CANCELLED")
    .setParameter(2, "DRAFT")
    .executeUpdate();

em.clear(); // Detach managed entities để tránh dùng trạng thái cũ.
~~~

**Không gọi `clear()` bừa bãi.** Nếu context còn thay đổi chưa flush, clear có thể bỏ những thay đổi đó. `flush()` không phải commit, và việc xóa/đặt lại context có thể ảnh hưởng những entity khác.

Khi chỉ cập nhật một entity và muốn giữ phần còn lại của context, `refresh(entity)` hoặc nạp lại có chọn lọc có thể phù hợp hơn, tùy trạng thái transaction và nghiệp vụ.

### 20.2. Native SQL và optimistic locking

Entity có:

~~~java
@Version
private long version;
~~~

Nếu chạy native SQL:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE id = ?;
~~~

thì câu SQL đó không tự phát sinh điều kiện `AND version = ?` hoặc tăng `version` như dirty checking của JPA.

Nếu nghiệp vụ cần optimistic concurrency, native query cần thiết kế rõ cơ chế kiểm tra/tăng version phù hợp:

~~~sql
UPDATE purchase_orders
SET status = ?1,
    version = version + 1
WHERE id = ?2
  AND version = ?3;
~~~

Khi số hàng cập nhật bằng 0, application cần phân biệt entity không tồn tại hoặc xung đột phiên bản, xử lý lỗi và transaction theo yêu cầu.

**Đừng mặc định một native named UPDATE có cùng ngữ nghĩa optimistic locking với việc sửa managed entity có `@Version`.**

## 21. Flush trước native query: cần hiểu thời điểm

Trong transaction có thay đổi pending:

~~~java
PurchaseOrder managed = em.find(PurchaseOrder.class, id);
managed.confirm();

List<?> rows = em.createNamedQuery(
    "PurchaseOrder.overviewByCustomerNative"
).setParameter(1, customerId)
 .getResultList();
~~~

JPA provider có thể cần flush trước query theo flush mode, provider và cách nó đánh giá ảnh hưởng tới kết quả. Với native SQL, khả năng ORM nhận biết **bảng nào query chạm tới** có thể hạn chế hoặc phụ thuộc API riêng.

Không nên suy luận:

- “Native SELECT luôn flush tất cả trước khi chạy”.
- “Native SELECT không bao giờ flush”.
- “Nếu có câu SQL SELECT thì managed changes đã commit”.

Khi tính đúng đắn yêu cầu native query nhìn thấy thay đổi pending trong cùng transaction, dùng ranh giới transaction/`flush()` có chủ đích và xác nhận hành vi trên provider thực tế. Nhớ rằng flush **chỉ đồng bộ SQL chưa commit**.

## 22. SQL injection: bảo vệ cả dữ liệu và cấu trúc query

### 22.1. Bind giá trị, không nối chuỗi

Sai:

~~~java
String sql =
    "SELECT * FROM customers WHERE email = '" +
    emailFromRequest + "'";
~~~

Đúng hơn:

~~~java
Query query = em.createNativeQuery(
    "SELECT id, email, full_name FROM customers WHERE email = ?1",
    Customer.class
);

query.setParameter(1, emailFromRequest);
~~~

Với `@NamedNativeQuery`, cú pháp SQL cố định đã loại bỏ nhu cầu ghép input vào query ở mỗi lần gọi.

### 22.2. Không thể bind tên bảng hoặc cột như một giá trị

Không làm:

~~~sql
SELECT * FROM ?1 ORDER BY ?2;
~~~

và kỳ vọng `?1` trở thành tên table còn `?2` trở thành tên column.

Identifier SQL là một phần của **cấu trúc câu truy vấn**. Nếu cần lựa chọn sort, dùng whitelist:

~~~java
public enum OrderSort {
    CREATED_DESC,
    AMOUNT_DESC
}
~~~

Repository map enum sang một trong các truy vấn được định nghĩa sẵn, hoặc xây SQL từ **các identifier đã được hardcode và kiểm soát** trong ứng dụng.

Không đưa raw `sortColumn`, `tableName`, `functionName` do client cung cấp thẳng vào chuỗi native SQL.

### 22.3. LIKE wildcard vẫn có ngữ nghĩa

Binding `"%a%"` an toàn về cấu trúc, nhưng ký tự `%` và `_` vẫn là wildcard trong SQL `LIKE`.

Nếu API muốn tìm **literal text**, cần escape pattern theo dialect và có quy tắc `ESCAPE` phù hợp. Không coi parameterization là giải pháp tự động cho mọi quy tắc tìm kiếm.

### 22.4. Cần kiểm tra quyền truy cập dữ liệu

Ví dụ:

~~~sql
SELECT o.*
FROM purchase_orders o
WHERE o.customer_id = ?1;
~~~

Nếu `customerId` lấy từ URL do client gửi, kẻ gọi có thể thử ID của khách hàng khác. Bind parameter không tự bảo vệ data authorization.

Cần xác thực caller có quyền đọc customer đó, hoặc giới hạn query bằng tenant/user ID lấy từ security context đáng tin cậy:

~~~sql
WHERE o.tenant_id = ?1
  AND o.customer_id = ?2
~~~

Điều kiện bảo mật cần nhất quán ở mọi query, kể cả SQL native viết riêng, vì nó không tự thừa hưởng mọi rule ở tầng repository/service.

## 23. Native query và các tính năng Hibernate riêng

Hibernate có thể cung cấp API native query mở rộng, ví dụ `unwrap` về interface Hibernate:

~~~java
org.hibernate.query.NativeQuery<?> hibernateQuery =
    em.createNativeQuery("SELECT ...")
      .unwrap(org.hibernate.query.NativeQuery.class);
~~~

Tùy phiên bản Hibernate, có thể đăng ký scalar types, đồng bộ query spaces hoặc cấu hình result transformers và nhiều tính năng khác.

Nhưng:

- `NativeQuery` của Hibernate **không phải Jakarta Persistence API portable**.
- API có thể thay đổi giữa Hibernate 5 và Hibernate 6.
- Cách unwrap query được tạo từ named native query có thể phụ thuộc provider.
- Khi chuyển sang EclipseLink, code Hibernate-specific cần thay thế.

Nếu dùng extension để giải quyết một vấn đề thật (kiểu JSON, synchronization, native result mapping phức tạp), hãy **cô lập nó trong repository adapter** và ghi rõ phiên bản/provider cần hỗ trợ.

## 24. Logging SQL và bind parameters

Để xác minh named native query thực sự chạy SQL gì, nên bật logging trong development/test.

Ví dụ Spring Boot với Hibernate 6:

~~~properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Với Hibernate 5, logger binding thường khác:

~~~properties
logging.level.org.hibernate.type.descriptor.sql.BasicBinder=TRACE
~~~

Log dự kiến có thể gần như:

~~~text
DEBUG org.hibernate.SQL -
    SELECT o.id, o.order_code, o.customer_id, o.status,
           o.total_amount, o.created_at
    FROM purchase_orders o
    WHERE o.customer_id = ?
      AND o.status = ?
    ORDER BY o.created_at DESC, o.id DESC

TRACE org.hibernate.orm.jdbc.bind -
    binding parameter (1:BIGINT) <- [42]
TRACE org.hibernate.orm.jdbc.bind -
    binding parameter (2:VARCHAR) <- [CONFIRMED]
~~~

**Đây là ví dụ log minh họa, không phải output của một lần chạy trong bài.**

Với EclipseLink, có các cấu hình riêng như:

~~~xml
<property
    name="eclipselink.logging.level.sql"
    value="FINE"/>
<property
    name="eclipselink.logging.parameters"
    value="true"/>
~~~

Không dùng một cấu hình logging của provider này rồi mặc định nó áp dụng cho provider khác.

### 24.1. Cần quan sát gì?

- Có đúng tên bảng/cột theo migration không?
- Parameter được bind đúng vị trí, kiểu và giá trị không?
- Câu query đang chạy bao nhiêu lần?
- Result mapping có phát SQL bổ sung để tải association không?
- Pagination có được đẩy xuống DB không?
- Có flush SQL trước query không?
- Có lỗi cast/JSON/enum/timestamp khi JDBC đọc kết quả không?

### 24.2. Không bật bind logging thiếu kiểm soát trên production

Bind log có thể chứa email, số điện thoại, mã nghiệp vụ, dữ liệu cá nhân hoặc thông tin nhạy cảm. Chỉ bật trong môi trường phù hợp, dùng fixture giả lập và kiểm soát retention/quyền xem log.

Một SQL log có thể rất hữu ích cho debug nhưng cũng tạo rủi ro bảo mật nếu lưu raw values quá rộng.

## 25. Named native query và hiệu năng

Một câu SQL viết trực tiếp không mặc định nhanh hơn JPQL. Về bản chất, **database tối ưu SQL cuối cùng**, không biết câu lệnh đến từ Criteria, JPQL hay `@NamedNativeQuery`.

Điểm có thể khác:

- Bạn chọn được CTE/window function/hint đặc thù.
- Bạn kiểm soát danh sách cột và JOIN rõ hơn.
- Provider giảm bớt bước dịch JPQL nhưng vẫn có JDBC/database execution.
- Có thể phải tự chịu trách nhiệm nhiều hơn về mapping và tối ưu SQL.

### 25.1. Xem EXPLAIN thay vì đoán

Với PostgreSQL:

~~~sql
EXPLAIN
SELECT o.id, o.order_code, o.customer_id,
       o.status, o.total_amount, o.created_at
FROM purchase_orders o
WHERE o.customer_id = 42
  AND o.status = 'CONFIRMED'
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20;
~~~

Một index có thể cân nhắc:

~~~sql
CREATE INDEX idx_orders_customer_status_time_id
ON purchase_orders (
    customer_id,
    status,
    created_at DESC,
    id DESC
);
~~~

Nhưng không nên áp dụng index này theo thói quen:

- Cardinality `customer_id`/`status` có thể khác giữa môi trường.
- Query còn nhiều loại filter khác.
- Index có chi phí ghi và lưu trữ.
- Database có thể chọn plan tốt hơn với index khác.
- Sort/limit và phân phối dữ liệu ảnh hưởng lựa chọn.

Dùng `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường được phép để quan sát execution thực. Với DML, nhớ rằng `EXPLAIN ANALYZE` có thể **thực thi thao tác ghi**, không chạy tùy tiện trên production.

### 25.2. JSON expression cần index thích hợp

PostgreSQL query:

~~~sql
WHERE jsonb_extract_path_text(preferences, 'tier') = 'GOLD'
~~~

có thể không tận dụng index thông thường trên một cột text khác. Có thể cân nhắc JSONB index, expression index hoặc cột chuẩn hóa tùy loại truy vấn và đặc tính expression.

Không mặc định `GIN` luôn là giải pháp cho mọi phép so sánh JSON; lựa chọn operator/index cần dựa trên truy vấn và query plan cụ thể.

### 25.3. N+1 vẫn có thể xảy ra

Một native query trả danh sách entity `PurchaseOrder`, rồi service gọi `getCustomer()` của mỗi order có thể vẫn phát nhiều SELECT. Native query không tự triệt tiêu lazy loading.

Nếu chỉ cần `customer.email`, hãy dùng DTO result mapping chọn email trực tiếp hoặc thiết kế fetch plan/association phù hợp.

## 26. Quản lý vòng đời query theo schema migration

Named native SQL dùng tên vật lý:

~~~sql
FROM purchase_orders
WHERE order_code = ?1
~~~

Nếu migration đổi:

~~~text
purchase_orders.order_code
            |
            v
purchase_orders.external_code
~~~

thì provider không thể tự biết đó là cùng thuộc tính `PurchaseOrder.orderCode`. Query native cần cập nhật tên cột.

Một quy trình triển khai đáng tin cậy:

1. Ghi nhận named native queries nào phụ thuộc bảng/cột cần đổi.
2. Chuẩn bị database migration tương thích với ứng dụng đang chạy.
3. Cập nhật SQL trong annotation hoặc XML.
4. Cập nhật `@SqlResultSetMapping` và DTO nếu đổi aliases/kiểu.
5. Chạy integration tests trên schema đã migration.
6. Triển khai theo thứ tự phù hợp với hệ thống có rolling deploy.
7. Chỉ xóa schema cũ khi không còn phiên bản ứng dụng phụ thuộc.

**Rename field Java** chưa chắc đã ảnh hưởng native SQL nếu tên cột vật lý giữ nguyên. Ngược lại, **rename cột database** có thể phá native SQL dù class Java vẫn compile bình thường.

### 26.1. Named native query có thể lỗi khi khởi động hoặc chỉ khi chạy

Provider có thể đăng ký metadata `@NamedNativeQuery` lúc boot, nhưng database chưa nhất thiết được yêu cầu parse SQL tại thời điểm đó.

Một truy vấn SQL chứa hàm không tồn tại có thể chỉ lỗi **khi được thực thi lần đầu**. Đừng coi “ứng dụng khởi động thành công” là bằng chứng mọi named native query hợp lệ trên database production.

Cần integration test thực thi các query quan trọng trong quá trình build/deploy phù hợp.

## 27. Quản lý tên và ownership trong codebase

Một cấu trúc dự án có thể như:

~~~text
com.example.shop
    domain/
        Customer.java
        PurchaseOrder.java
    dto/
        OrderOverview.java
        MonthlyRevenue.java
    repository/
        PurchaseOrderReader.java
        RevenueReportRepository.java
        PostgresRevenueRepository.java
        MySqlRevenueRepository.java
    service/
        OrderApplicationService.java
        RevenueReportService.java
    persistence/
        NativeQueryNames.java
    resources/
        META-INF/orm.xml
        db/migration/...
~~~

Tùy project, các named queries có thể được khai báo ở annotation hoặc XML, nhưng **chỉ một nguồn chính thức cho mỗi tên**.

Một lớp hằng số:

~~~java
public final class NativeQueryNames {

    private NativeQueryNames() {
    }

    public static final String ORDERS_BY_CUSTOMER_STATUS =
        "PurchaseOrder.findByCustomerAndStatusNative";

    public static final String ORDER_OVERVIEW =
        "PurchaseOrder.overviewByCustomerNative";

    public static final String COUNT_BY_STATUS =
        "PurchaseOrder.countByStatusNative";
}
~~~

Repository gọi:

~~~java
em.createNamedQuery(
    NativeQueryNames.ORDERS_BY_CUSTOMER_STATUS,
    PurchaseOrder.class
);
~~~

Nếu dùng compile-time constant trong annotation và code, có thể giảm nguy cơ lệch tên:

~~~java
@NamedNativeQuery(
    name = NativeQueryNames.COUNT_BY_STATUS,
    query = "SELECT COUNT(*) FROM purchase_orders WHERE status = ?1"
)
~~~

Giá trị annotation phải là constant expression phù hợp. Ví dụ `public static final String` gán literal đáp ứng yêu cầu này.

**Tuy nhiên, hằng số tên query chỉ giải quyết lỗi gõ tên; nó không kiểm tra tính hợp lệ của SQL, schema và result mapping.**

## 28. Kiểm thử native query theo nhiều tầng

### 28.1. Kiểm thử metadata

Xác nhận tên query được đăng ký trong persistence unit và có thể tạo `Query`:

~~~java
Query query = em.createNamedQuery(
    "PurchaseOrder.countByStatusNative"
);
~~~

Nếu sai tên, có thể nhận `IllegalArgumentException`. Nhưng tạo Query thành công chưa chứng minh SQL sẽ chạy đúng.

### 28.2. Kiểm thử SQL thực thi

Với dữ liệu test đã chuẩn bị:

~~~java
Number count = (Number) em.createNamedQuery(
        "PurchaseOrder.countByStatusNative"
    )
    .setParameter(1, "CONFIRMED")
    .getSingleResult();
~~~

Assert số lượng đúng theo fixture, không chỉ assert không có exception.

### 28.3. Kiểm thử mapping entity

Một query `resultClass = PurchaseOrder.class` cần đủ cột mapped. Kiểm tra:

- Entity có ID đúng.
- `orderCode`, `status`, `totalAmount` khớp dữ liệu.
- Quan hệ `customer` được nhận diện đúng FK.
- Không có lỗi missing column/alias.
- Khác biệt type/enum/date được xử lý đúng.

### 28.4. Kiểm thử DTO constructor mapping

Với `OrderOverviewMapping`, xác nhận:

- Alias `order_id`, `order_code`, `customer_email`, `total_amount` có mặt.
- Thứ tự/kiểu constructor đúng.
- Trường numeric được chuyển đúng `BigDecimal`.
- Trường nullable có contract rõ.
- Nếu SQL JOIN một-nhiều, không nhân đôi DTO ngoài ý muốn.

### 28.5. Kiểm thử transaction và stale state

Dùng một managed entity và một native UPDATE trong transaction kiểm soát; xác nhận các quy tắc về refresh/clear, kết quả sau commit và rollback.

Không nên dùng một entity vừa persist nhưng chưa flush làm fixture cho native SQL mà không hiểu flush mode của provider.

### 28.6. Kiểm thử trên database thực

Một H2 test không thể chứng minh PostgreSQL JSONB, `date_trunc`, CTE hoặc collation chạy đúng như production.

Nếu ứng dụng hỗ trợ PostgreSQL và MySQL, test suite nên thực thi từng adapter trên DB/version thực được hỗ trợ. Một ma trận:

| Trường hợp | PostgreSQL | MySQL |
| --- | --- | --- |
| Named query được đăng ký | Kiểm tra | Kiểm tra |
| Positional parameters | Kiểm tra | Kiểm tra |
| Entity result mapping | Kiểm tra | Kiểm tra |
| DTO mapping/timestamp | Kiểm tra | Kiểm tra |
| Thống kê theo tháng | `DATE_TRUNC` | `DATE_FORMAT`/biểu thức tương ứng |
| JSON tier filter | `jsonb_extract_path_text` | `JSON_EXTRACT`/`JSON_UNQUOTE` |
| NULL/timezone | Kiểm tra semantics | Kiểm tra semantics |
| Pagination | Query plan và result | Query plan và result |
| Bulk DML + transaction | Commit/rollback | Commit/rollback |
| Security/tenant filter | Kiểm tra | Kiểm tra |

## 29. Test fixture cần có các trường hợp phân biệt

Giả sử cần test named native query:

~~~sql
SELECT o.*
FROM purchase_orders o
WHERE o.customer_id = ?1
  AND o.status = ?2
ORDER BY o.created_at DESC, o.id DESC;
~~~

Tạo dữ liệu:

| Order | Customer ID | Status | createdAt | Kết quả với customer=42, CONFIRMED |
| --- | ---: | --- | --- | --- |
| A | 42 | CONFIRMED | 2026-10-01 09:00 | Có |
| B | 42 | DRAFT | 2026-10-02 09:00 | Không |
| C | 43 | CONFIRMED | 2026-10-03 09:00 | Không |
| D | 42 | CONFIRMED | 2026-10-04 09:00 | Có |
| E | 42 | CONFIRMED | 2026-10-04 09:00 | Có |

Kết quả mong muốn sắp theo `created_at DESC, id DESC`: D và E đứng trước A, thứ tự D/E dựa trên giá trị ID thực.

Tình huống test phải xác minh:

- Filter **customer_id** đúng.
- Filter **status** đúng.
- Hai đơn cùng timestamp được phân biệt bằng ID.
- Native enum được bind đúng dạng cột database.
- Result mapping trả entity đúng loại.
- Pagination không cắt kết quả bất thường.

Nếu chỉ tạo toàn bản ghi khớp điều kiện, test không thể phát hiện query bị bỏ mất WHERE.

## 30. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `createNamedQuery(...)` không tìm thấy tên | Query chưa đăng ký hoặc sai tên | Kiểm tra metadata, persistence unit, annotation/XML |
| Query có tên trùng | Trùng giữa named JPQL/native hoặc nhiều entity | Áp dụng quy ước tên duy nhất |
| Lỗi "relation/table does not exist" | Native SQL dùng sai tên schema/table | Đối chiếu migration và search path/schema |
| Lỗi "column does not exist" | Đổi cột nhưng chưa sửa SQL/alias | Cập nhật query và result mapping |
| `resultClass` báo missing column | SQL SELECT thiếu cột mapped | Chọn đầy đủ cột cần cho entity |
| `@ConstructorResult` không gọi được DTO constructor | Sai alias, thứ tự hoặc kiểu | Đối chiếu SQL aliases và constructor |
| `ClassCastException` với COUNT | Native scalar không trả đúng `Long` mong đợi | Dùng `Number` hoặc result mapping rõ |
| Native enum parameter không match | Bind Java enum nhưng DB cần VARCHAR | Bind giá trị phù hợp mapping, ví dụ `status.name()` |
| Query chạy PostgreSQL nhưng lỗi MySQL | Dùng `DATE_TRUNC`/JSONB/toán tử vendor | Tách dialect adapter hoặc dùng query portable |
| SQL chứa `::` bị lỗi parameter parser | Parser native của provider hiểu sai dấu `:` | Dùng CAST/SQL khác theo provider |
| Không thấy native UPDATE trên entity managed | Persistence context stale sau bulk DML | Flush/refresh/clear theo chiến lược phù hợp |
| `@Version` không tăng | Native DML không tự xử lý version | Thiết kế điều kiện/tăng version tường minh |
| Xóa nhiều row không chạy cascade ORM | SQL bulk bypass entity lifecycle | Hiểu FK/cascade và thao tác nghiệp vụ |
| Kết quả thiếu sau JOIN | INNER JOIN loại bản ghi không có association | Xem JOIN/ON/WHERE |
| Kết quả bị lặp | JOIN to-many nhân row | Thiết kế DISTINCT/EXISTS hoặc DTO đúng |
| N+1 sau native SELECT | Association LAZY chưa được fetch | Projection/fetch plan phù hợp |
| Pagination khác giữa DB | Dialect SQL và provider hỗ trợ khác | Test offset/limit trên DB mục tiêu |
| SQL nhanh ở H2 nhưng chậm ở production | Data distribution/index/optimizer khác | EXPLAIN và load test trên DB tương ứng |
| Không thấy lỗi lúc startup | Native SQL chưa được database parse | Integration test thực thi query |
| Input tên cột gây injection | Ghép raw identifier từ client | Whitelist và query được kiểm soát |
| Lộ dữ liệu qua SQL bind logging | TRACE parameter trên production | Tắt/redact và kiểm soát quyền log |

## 31. Bài tập có lời giải

### Bài 1. Phân biệt @NamedQuery và @NamedNativeQuery

Cho:

~~~java
@NamedQuery(
    name = "Order.jpql",
    query = "SELECT o FROM PurchaseOrder o"
)
~~~

và:

~~~java
@NamedNativeQuery(
    name = "Order.native",
    query = "SELECT * FROM purchase_orders",
    resultClass = PurchaseOrder.class
)
~~~

**Đáp án:** Query đầu dùng JPQL theo tên entity, query sau dùng SQL theo bảng vật lý. Cả hai có thể được gọi qua `createNamedQuery(name)` khi đăng ký trong persistence unit.

### Bài 2. Vì sao phải có resultClass hoặc resultSetMapping?

SQL:

~~~sql
SELECT *
FROM purchase_orders
WHERE id = ?1;
~~~

**Đáp án:** Nếu muốn nhận managed entity `PurchaseOrder`, cần mô tả mapping result thích hợp, ví dụ `resultClass = PurchaseOrder.class`. Không khai báo mapping, kết quả native thường là scalar hoặc `Object[]` theo số cột, không tự đảm bảo được kết quả entity như ý.

### Bài 3. Câu native COUNT nên ép kiểu gì?

~~~java
Object value = query.getSingleResult();
~~~

**Đáp án:** Với query chưa khai báo scalar mapping kiểu cố định, dùng `Number` rồi gọi `longValue()` hợp lý hơn giả định luôn nhận `Long`.

### Bài 4. Vì sao named native query có thể vỡ khi đổi tên cột?

**Đáp án:** SQL chứa tên cột vật lý, không được JPQL provider tự map lại theo tên thuộc tính Java. Schema migration và named native SQL phải được đổi đồng bộ.

### Bài 5. Native query có tự port DATE_TRUNC sang DATE_FORMAT không?

**Đáp án:** Không. `DATE_TRUNC`/`DATE_FORMAT` là hàm database-specific và có thể khác kiểu kết quả. Cần SQL riêng theo DB hoặc giải pháp portable khác.

### Bài 6. Alias trong DTO mapping

Mapping yêu cầu:

~~~java
@ColumnResult(name = "customer_email")
~~~

SQL trả:

~~~sql
SELECT c.email AS email_address ...
~~~

**Đáp án:** Sai alias so với mapping. Đổi SQL thành `AS customer_email` hoặc cập nhật `@ColumnResult` để khớp.

### Bài 7. Native SELECT có JOIN customer, tại sao vẫn lazy-load?

**Đáp án:** JOIN có thể chỉ dùng để lọc; nếu SELECT chỉ trả cột của order, JPA không bắt buộc materialize customer. Muốn dữ liệu customer cho màn hình, cân nhắc DTO projection hoặc fetch mapping phù hợp.

### Bài 8. Dùng @NamedNativeQuery để UPDATE được không?

**Đáp án:** Được, nếu câu SQL là UPDATE/DELETE phù hợp và gọi `executeUpdate()` trong transaction. Nhưng nó là bulk DML, không đồng nghĩa thay đổi từng managed entity và callbacks.

### Bài 9. Tại sao @Version không được cập nhật?

**Đáp án:** Native UPDATE không tự thêm điều kiện/tăng version theo cơ chế optimistic locking của dirty checking. Phải tự thiết kế version logic khi cần.

### Bài 10. Query chạy nhưng entity status trong memory vẫn cũ

**Đáp án:** Persistence context có thể stale sau native DML. Dùng `refresh` hoặc `clear` đúng cách sau khi bảo đảm pending changes đã được xử lý, và cân nhắc cache.

### Bài 11. Có nên dùng resultClass = PurchaseOrder cho query SELECT id, order_code?

**Đáp án:** Không nên. Kết quả không chứa đủ cột cần materialize entity như mapping. Dùng DTO projection/scalar hoặc chọn đủ cột mapped cho entity.

### Bài 12. Vì sao không đặt tên hàm SQL bằng parameter?

~~~sql
SELECT ?1(created_at) FROM purchase_orders
~~~

**Đáp án:** Bind parameter đại diện giá trị, không đại diện identifier/function syntax. Dùng SQL đã được chọn từ whitelist hoặc repository adapter.

### Bài 13. Query bị trùng name với @NamedQuery

**Đáp án:** Không nên có hai định nghĩa tên giống nhau trong cùng persistence unit. Đặt namespace rõ như `PurchaseOrder.findByStatus` và `PurchaseOrder.findByStatusNative`.

### Bài 14. Cần hỗ trợ cả PostgreSQL và MySQL

**Đáp án:** Tách query/database adapter, hoặc metadata XML theo profile bảo đảm một phiên bản truy vấn được đăng ký trên mỗi môi trường. Cùng contract DTO nhưng SQL/convert logic có thể khác.

### Bài 15. @NamedNativeQueries có tự chạy tất cả query không?

**Đáp án:** Không. Annotation đăng ký metadata. SQL thực thi khi ứng dụng gọi query object và phương thức như `getResultList()` hoặc `executeUpdate()`.

### Bài 16. Tại sao LIMIT 20 chưa chắc có đúng 20 entity?

**Đáp án:** Có thể không đủ dữ liệu khớp, hoặc mapping JOIN nhiều bảng tạo các dòng lặp, hoặc provider xử lý pagination theo cơ chế riêng. Kiểm tra SQL, ResultSet và entity mapping.

### Bài 17. Có thể dùng H2 để kiểm tra JSONB của PostgreSQL không?

**Đáp án:** H2 có thể phù hợp cho một số test cơ bản nhưng không chứng minh JSONB/hàm/operator/driver mapping của PostgreSQL. Cần integration test với DB tương ứng.

### Bài 18. Native query có tránh SQL injection hoàn toàn không?

**Đáp án:** Không. Phải bind dữ liệu, không ghép tên identifier do client cung cấp, kiểm tra quyền và giới hạn loại SQL được phép thực thi.

### Bài 19. COUNT đúng nhưng report sai timezone

**Đáp án:** SQL nhóm theo tháng/ngày có thể dựa vào timezone của DB/session hoặc kiểu timestamp. Repository phải quy định timezone nghiệp vụ và chuyển đổi kết quả nhất quán.

### Bài 20. Native query có luôn hiệu năng cao hơn JPQL không?

**Đáp án:** Không. SQL cuối cùng và query plan quyết định hiệu năng. Native SQL cho quyền dùng tính năng riêng nhưng cũng khiến ứng dụng phải chịu trách nhiệm hơn với index và portability.

## 32. Checklist khi thêm một named native query mới

Trước khi chấp nhận một truy vấn native được dùng ở nhiều nơi, hãy đặt ra những câu hỏi sau:

1. **Có thực sự cần native SQL không**, hay JPQL/Criteria đã đủ?
2. **Query có cấu trúc ổn định và cần tái sử dụng không?** Nếu có, named native query có thể phù hợp.
3. **Tên query đã duy nhất trong persistence unit chưa?** Có đụng named JPQL không?
4. **SQL đang nhắm tới DB/version nào?** Có hàm/operator/CTE đặc thù không?
5. **Bảng/cột/alias có khớp migration schema không?**
6. **Kết quả là entity, scalar, DTO hay nhiều entity?** Mapping đã tường minh chưa?
7. **Đủ cột để materialize entity chưa?** Có khóa/FK/discriminator/secondary table liên quan không?
8. **Kiểu JDBC và Java có tương thích không?** Numeric, timestamp, JSON, UUID, enum?
9. **Tham số có được bind an toàn không?** Có phần cấu trúc SQL nào phụ thuộc input client?
10. **Nếu DML, transaction và versioning xử lý thế nào?** Persistence context có stale không?
11. **Kết quả có bị nhân khi JOIN to-many không?**
12. **Pagination có đúng theo dialect và thứ tự ổn định không?**
13. **Đã kiểm tra N+1 hoặc secondary SELECT chưa?**
14. **Index và EXPLAIN đã được đánh giá khi query quan trọng hoặc dữ liệu lớn chưa?**
15. **Có filter bảo mật và tenant phù hợp không?**
16. **Nếu chạy trên database khác, implementation thay thế ở đâu?**
17. **Có integration test thực thi trên database thật không?**
18. **Có thể thay đổi schema mà không làm ứng dụng cũ ngừng chạy không?**

## 33. Tổng kết

Nhìn chung, luồng của một named native query là:

~~~text
@NamedNativeQuery / orm.xml
          |
          | Đăng ký trong persistence unit
          v
EntityManager.createNamedQuery(name)
          |
          | setParameter(), setFirstResult(), setMaxResults()...
          v
JPA provider + JDBC
          |
          | Thực thi SQL native trên database mục tiêu
          v
ResultSet
          |
          +---- resultClass -> managed entity nếu mapping phù hợp
          |
          +---- @SqlResultSetMapping -> DTO/entity/scalar mapping
          |
          +---- scalar/Object[] -> chuyển đổi có kiểm soát
          |
          v
Repository / service contract
~~~

Những nguyên tắc cần ghi nhớ:

- **`@NamedNativeQuery` định danh và tái sử dụng SQL native**, còn `@NamedQuery` dùng JPQL.
- **Tên truy vấn có phạm vi persistence unit** và cần tránh trùng lặp.
- **Native SQL dùng bảng/cột thật**, nên phụ thuộc schema và dialect database.
- **`resultClass` và `@SqlResultSetMapping`** quyết định cách ánh xạ ResultSet; entity cần đủ cột, DTO cần alias/constructor/kiểu nhất quán.
- **Binding tham số an toàn** là bắt buộc; không cho input thay thế tên bảng/cột/hàm tùy ý.
- **Native DML không tự bảo đảm dirty checking, cascade, callbacks và optimistic locking như thao tác managed entity**.
- **Portability cần được thiết kế rõ** bằng adapter hoặc metadata riêng cho từng hệ quản trị, không chỉ nhờ JPA provider.
- **Hiệu năng phải được đo bằng SQL log và EXPLAIN**, không giả định native query luôn nhanh.
- **Integration tests trên database đích** là cách phát hiện sớm lỗi parser, alias, result type, schema, timezone và SQL đặc thù.

**Giá trị của named native query không phải ở việc làm mất đi sự phụ thuộc database, mà ở việc đặt sự phụ thuộc đó vào một vị trí rõ ràng, kiểm soát được, có hợp đồng kết quả ổn định và có thể kiểm thử khi hệ thống thay đổi.**
