# Ánh xạ kết quả thủ tục sang entity hoặc dữ liệu độc lập trong JPA

Trong **Jakarta Persistence (JPA)**, ứng dụng có thể truy vấn database bằng JPQL, Criteria API, native SQL hoặc gọi **stored procedure** (thủ tục lưu trữ). Khi gọi procedure, việc đăng ký tham số mới chỉ là một nửa công việc; nửa còn lại là **chọn cách ánh xạ kết quả trả về**.

Có hai nhóm kết quả cần phân biệt:

- **Entity**: một hàng kết quả đại diện cho một thực thể đã khai báo `@Entity`, có định danh `@Id`, được JPA quản lý trong persistence context khi được materialize đúng mapping.
- **Dữ liệu độc lập**: giá trị scalar, nhiều cột `Object[]`, DTO hoặc Java record. Chúng thích hợp cho báo cáo, màn hình danh sách, tổng hợp và API response; **không tham gia dirty checking như entity**.

Sơ đồ:

~~~text
                        STORED PROCEDURE
                               |
                   IN / OUT / result sets
                               |
                               v
                       StoredProcedureQuery
                               |
                   +-----------+-----------+
                   |                       |
                   v                       v
             Entity result           Independent result
             PurchaseOrder           OrderOverview / OrderStats
             - có @Id                - DTO, record, scalar
             - managed state         - không managed
             - lifecycle JPA         - không dirty checking
             - có thể LAZY           - dữ liệu cần thiết đã lấy
~~~

Bài này thuộc chương **Thủ tục lưu trữ** của chủ đề **Data Persistence Relational Access ORM JPA**. Các ví dụ dùng Java 17+, namespace `jakarta.persistence`, cùng một số stored procedures theo cú pháp **MySQL** để việc học có bối cảnh cụ thể. Với PostgreSQL, Oracle hoặc SQL Server, cần điều chỉnh SQL, cách trả result set/cursor và khả năng của driver/provider.

**Nguyên tắc thiết kế:** dùng entity mapping nếu kết quả thật sự là **entity đầy đủ với identity hợp lệ**. Nếu procedure trả projection, số liệu tổng hợp hoặc dữ liệu phục vụ một use case đọc, hãy chọn DTO/scalar.

---

## 1. Các hình thức kết quả của stored procedure

Một procedure có thể:

1. Nhận tham số `IN`.
2. Trả tham số `OUT` hoặc `INOUT`.
3. Phát một hoặc nhiều **result sets** bằng SELECT theo khả năng database.
4. Trả một **REF_CURSOR** thông qua OUT parameter trên những hệ quản trị hỗ trợ.
5. Thực hiện DML và trả thông tin **update count**.
6. Kết hợp nhiều loại kết quả theo một thứ tự phụ thuộc database/JDBC.

Ví dụ ba hợp đồng khác nhau:

~~~text
sp_find_orders(p_customer_id)
    IN:  customer id
    OUT: một result set gồm nhiều hàng đơn hàng

sp_customer_totals(p_customer_id, p_count, p_total)
    IN:  customer id
    OUT: số đơn, tổng tiền
    ResultSet: không bắt buộc

sp_customer_dashboard(p_customer_id)
    IN:  customer id
    ResultSet 1: thông tin khách hàng
    ResultSet 2: thống kê đơn hàng
~~~

Đây là điểm phân biệt **result-set column** với **output parameter**: một cột `total_count` trong SELECT không tự trở thành một tham số `OUT p_total_count`.

| Kết quả | API/cách đọc thường dùng |
| --- | --- |
| Một result set | `getResultList()` |
| Một giá trị từ result set | `getSingleResult()` nếu hợp đồng phù hợp |
| OUT/INOUT | `getOutputParameterValue(...)` |
| REF_CURSOR | `ParameterMode.REF_CURSOR` và cơ chế provider/DB |
| Nhiều result sets/update counts | `execute()`, `hasMoreResults()`, `getResultList()`, `getUpdateCount()` |
| Entity từ result set | `resultClasses` hoặc `@EntityResult` |
| DTO từ result set | `@ConstructorResult` hoặc chuyển đổi tại repository |

## 2. API chuẩn: StoredProcedureQuery

JPA cung cấp:

~~~java
import jakarta.persistence.StoredProcedureQuery;
import jakarta.persistence.ParameterMode;
~~~

Tạo query theo procedure name:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_orders_for_customer");
~~~

Cung cấp class kết quả entity:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery(
        "sp_orders_for_customer",
        PurchaseOrder.class
    );
~~~

Sử dụng mapping đã được đăng ký:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery(
        "sp_order_overview",
        "OrderOverviewMapping"
    );
~~~

Hoặc dùng metadata khai báo sẵn:

~~~java
StoredProcedureQuery sp =
    em.createNamedStoredProcedureQuery(
        "PurchaseOrder.byCustomerProc"
    );
~~~

`StoredProcedureQuery` kế thừa các chức năng của `Query` và bổ sung cách đăng ký/lấy tham số procedure:

| Phương thức | Mục đích |
| --- | --- |
| `registerStoredProcedureParameter` | Đăng ký vị trí/tên, kiểu, mode |
| `setParameter` | Gán đầu vào |
| `execute` | Bắt đầu lời gọi và xác định kết quả đầu có là result set |
| `getResultList` | Lấy result set hiện hành |
| `getSingleResult` | Lấy một kết quả khi truy vấn trả đúng một |
| `hasMoreResults` | Chuyển qua kết quả tiếp theo |
| `getUpdateCount` | Lấy update count hiện hành |
| `getOutputParameterValue` | Đọc giá trị OUT/INOUT |

**`execute()` không phải commit.** Nó gọi procedure và tạo các kết quả trong transaction/connection hiện tại theo quy tắc của database.

### 2.1. Bốn ParameterMode

~~~java
ParameterMode.IN
ParameterMode.OUT
ParameterMode.INOUT
ParameterMode.REF_CURSOR
~~~

Ví dụ đăng ký theo vị trí:

~~~java
sp.registerStoredProcedureParameter(
    1,
    Long.class,
    ParameterMode.IN
);
sp.setParameter(1, 42L);
~~~

Vị trí tham số bắt đầu từ **1** theo API JPA, và phải tương ứng với chữ ký procedure thực.

Không đăng ký tất cả tham số đều là `IN` nếu procedure dùng OUT/INOUT. Khi tham số cần map về JDBC type đặc thù, phải kiểm chứng với driver và provider.

## 3. Mô hình dữ liệu ví dụ

Entity `Customer`:

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;

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

Enum:

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    DRAFT, CONFIRMED, CANCELLED
}
~~~

Entity `PurchaseOrder`:

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "purchase_orders")
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
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", precision = 15, scale = 2, nullable = false)
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

    public Customer getCustomer() {
        return customer;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void changeStatus(OrderStatus next) {
        this.status = next;
    }
}
~~~

Schema MySQL tương ứng:

~~~sql
CREATE TABLE customers (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(180) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_code VARCHAR(255) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_po_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Các câu SQL này chỉ là ví dụ một schema cụ thể. Trong dự án thật, schema do migration xác định; mapping procedure phải phù hợp với chính database đang chạy.

---

## 4. Hướng thứ nhất: ánh xạ result set thành entity

Nếu procedure trả **đủ các cột được ánh xạ của `PurchaseOrder`**, ta có thể dùng `resultClass = PurchaseOrder.class` khi tạo query.

MySQL procedure:

~~~sql
DELIMITER //

CREATE PROCEDURE sp_orders_for_customer(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT
        o.id,
        o.order_code,
        o.customer_id,
        o.status,
        o.total_amount,
        o.created_at
    FROM purchase_orders o
    WHERE o.customer_id = p_customer_id
    ORDER BY o.created_at DESC, o.id DESC;
END//

DELIMITER ;
~~~

Lệnh `DELIMITER` là chỉ thị của một số công cụ nhập lệnh MySQL, không phải SQL chuẩn phải gửi nguyên xi qua mọi JDBC/migration tool. Khi dùng Flyway hoặc Liquibase, hãy theo cơ chế delimiter của công cụ đó.

Procedure trả:

| ResultSet column | Entity property |
| --- | --- |
| `id` | `id`, primary key |
| `order_code` | `orderCode` |
| `customer_id` | `customer` thông qua FK |
| `status` | `status`, enum STRING |
| `total_amount` | `totalAmount` |
| `created_at` | `createdAt` |

### 4.1. Lời gọi Java

~~~java
public List<PurchaseOrder> findOrders(
        EntityManager em,
        long customerId) {

    StoredProcedureQuery sp =
        em.createStoredProcedureQuery(
            "sp_orders_for_customer",
            PurchaseOrder.class
        );

    sp.registerStoredProcedureParameter(
        1, Long.class, ParameterMode.IN
    );
    sp.setParameter(1, customerId);

    return sp.getResultList().stream()
        .map(PurchaseOrder.class::cast)
        .toList();
}
~~~

`StoredProcedureQuery` không phải một `TypedQuery<PurchaseOrder>` generic, nên việc chuyển kiểu ở ranh giới repository là điều thường gặp. Nhưng **cast không tự tạo mapping**: phải khai báo result class/entity mapping đúng từ trước.

### 4.2. Vì sao entity result cần đủ cột?

Nếu procedure chỉ trả:

~~~sql
SELECT id, order_code, total_amount
FROM purchase_orders;
~~~

thì thiếu `customer_id`, `status`, `created_at` của entity mẫu. Không nên cố gắng xem result set này là một `PurchaseOrder` hoàn chỉnh.

Provider có thể báo thiếu cột, lỗi mapping hoặc hành vi không portable. Nếu chỉ cần ba giá trị, **DTO projection** phù hợp hơn.

### 4.3. Entity trả về có tham gia persistence context?

Khi result class ánh xạ đúng entity, JPA quản lý result theo entity identity trong persistence context tương ứng.

~~~java
List<PurchaseOrder> orders = findOrders(em, 42L);

for (PurchaseOrder order : orders) {
    boolean managed = em.contains(order);
    System.out.println(managed);
}
~~~

Khi entity còn thuộc context mở, kết quả thường là `true`. Điều đó mang ý nghĩa:

- Entity có identity theo `@Id`.
- JPA quản lý các instance cùng identity theo quy tắc persistence context.
- Managed entity có thể được dirty checking trong transaction phù hợp.
- Quan hệ `customer` có thể vẫn LAZY; gọi getter có thể dẫn tới SQL bổ sung.
- Sau khi đóng EntityManager, kết quả entity có thể trở thành detached.

**Không dùng `em.persist(order)` chỉ vì object được trả từ stored procedure**. Nó đã là entity theo mapping; persist dành cho entity mới.

## 5. First-level cache và trạng thái cũ sau khi procedure chạy

Giả sử `PurchaseOrder#101` đã được tải bằng:

~~~java
PurchaseOrder managed =
    em.find(PurchaseOrder.class, 101L);
~~~

Sau đó một procedure khác cập nhật status trong database rồi trả hàng `#101`. Context có thể vẫn giữ managed instance với giá trị status cũ.

Vì vậy:

- Entity identity trong context không đồng nghĩa **mọi field đã được reload mới nhất**.
- Native procedure không mặc định chạy dirty checking/callbacks trên entity đang quản lý.
- Khi cần state mới nhất, có thể dùng `em.refresh(managed)` trong context/transaction hợp lệ.
- `em.clear()` detach toàn bộ context, và **không tự flush**, nên có thể bỏ những thay đổi chưa đồng bộ.

Ví dụ:

~~~java
sp.execute();         // Procedure đã cập nhật DB.
em.refresh(managed);  // Nạp lại state nếu cần và được phép.
~~~

Không dùng `refresh` bừa bãi nếu đang có các thay đổi Java chưa flush mà không muốn mất chúng.

---

## 6. Hướng thứ hai: ánh xạ thành dữ liệu độc lập

Dữ liệu độc lập là một **giá trị đọc được từ database**, không nhất thiết mang identity/lifecycle của entity.

Các loại phổ biến:

| Kết quả | Java representation |
| --- | --- |
| `COUNT(*)` | `Number` → `long` |
| `SUM(total_amount)` | `BigDecimal` hoặc loại numeric do driver trả |
| Hai scalar trong một hàng | `Object[]` |
| Một hàng báo cáo với các cột từ nhiều bảng | DTO/record |
| Tập nhiều hàng của báo cáo | `List<DTO>` |
| OUT parameter | Java value/DTO tổng hợp từ các OUT |
| Hàng JSON/array đặc thù | Kiểu JDBC rồi chuyển đổi trong adapter |

Một DTO không cần `@Entity` hoặc `@Id`. JPA sẽ **không dirty check** nó khi ứng dụng thay đổi giá trị.

### 6.1. Ví dụ record

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

Record này dùng cho một màn hình tổng quan đơn hàng. Nó không có cùng trách nhiệm với entity `PurchaseOrder`, dù cùng chứa `orderId`.

### 6.2. Lợi ích khi trả DTO

- Chỉ lấy những cột cần thiết.
- Không tạo managed entity graph không cần thiết.
- Không kích hoạt lazy loading khi serializer truy cập object.
- Có contract API ổn định hơn.
- Hạn chế lộ thông tin nội bộ từ entity.
- Thích hợp với dữ liệu tổng hợp không có primary key entity.

Đổi lại, DTO **không thể tự lưu** khi gọi `em.flush()`. Nếu user sửa DTO, service cần thực hiện lệnh cập nhật có transaction theo nghiệp vụ.

## 7. Scalar result từ SELECT trong procedure

Procedure đếm số đơn:

~~~sql
DELIMITER //

CREATE PROCEDURE sp_count_orders_by_status(
    IN p_status VARCHAR(20)
)
BEGIN
    SELECT COUNT(*) AS total_count
    FROM purchase_orders
    WHERE status = p_status;
END//

DELIMITER ;
~~~

Java:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery(
        "sp_count_orders_by_status"
    );

sp.registerStoredProcedureParameter(
    1, String.class, ParameterMode.IN
);

sp.setParameter(1, OrderStatus.CONFIRMED.name());

Object value = sp.getSingleResult();
long count = ((Number) value).longValue();
~~~

Đây là **scalar result**, không phải entity. `COUNT(*)` có thể được JDBC/provider đưa về các kiểu `Number` khác nhau. Ép thẳng về `Long` trong mọi môi trường là một giả định không cần thiết.

### 7.1. Vì sao không bind Java enum trực tiếp trong mọi native procedure?

JPQL hiểu type mapping của entity, nhưng tham số native procedure có thể được driver xử lý khác. Với cột `status VARCHAR(20)` và thủ tục nhận `VARCHAR`, truyền `OrderStatus.CONFIRMED.name()` giúp thể hiện rõ hợp đồng DB.

Nếu routine nhận kiểu enum vendor-specific, ứng dụng cần binding/mapping tương ứng; không tự cho rằng mọi database dùng chuỗi.

## 8. Nhiều scalar dưới dạng Object[]

Procedure:

~~~sql
DELIMITER //

CREATE PROCEDURE sp_order_stats(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT
        COUNT(*) AS order_count,
        COALESCE(SUM(total_amount), 0) AS total_amount
    FROM purchase_orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
~~~

Java:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_order_stats");

sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
sp.setParameter(1, 42L);

Object[] row = (Object[]) sp.getSingleResult();

long count = ((Number) row[0]).longValue();
BigDecimal amount = (BigDecimal) row[1];
~~~

Trong DB schema ví dụ, `SUM` của DECIMAL thường được map về `BigDecimal`. Tuy nhiên phải xác nhận trên JDBC/provider thực vì SQL expression/cast hoặc phiên bản driver có thể ảnh hưởng kiểu.

Nhược điểm của `Object[]`:

- Các chỉ số `row[0]` và `row[1]` không có tên.
- Đổi thứ tự SELECT dễ phá Java code.
- Kiểu runtime không được compiler bảo đảm.
- Logic mapping dễ lặp ở nhiều nơi.

Nên chuyển giá trị thành DTO ngay trong repository:

~~~java
public record OrderStats(
    long orderCount,
    BigDecimal totalAmount
) {
}
~~~

~~~java
OrderStats stats = new OrderStats(
    ((Number) row[0]).longValue(),
    (BigDecimal) row[1]
);
~~~

**Không mặc định result set của procedure tự trả `Tuple` chỉ vì Criteria API có `Tuple`.** Cần xác định shape/result mapping đã khai báo.

---

## 9. @SqlResultSetMapping: cơ chế ánh xạ kết quả SQL

JPA cung cấp metadata `@SqlResultSetMapping` để mô tả cách đọc một hàng ResultSet.

Ba cơ chế chính:

| Annotation con | Công dụng |
| --- | --- |
| `@EntityResult` | Ánh xạ hàng thành entity |
| `@ConstructorResult` | Tạo DTO/class qua constructor |
| `@ColumnResult` | Ánh xạ một giá trị scalar |

Ví dụ mapping hai scalar:

~~~java
@SqlResultSetMapping(
    name = "OrderStatsScalars",
    columns = {
        @ColumnResult(
            name = "order_count",
            type = Long.class
        ),
        @ColumnResult(
            name = "total_amount",
            type = BigDecimal.class
        )
    }
)
~~~

Mapping phải được đăng ký trong metadata JPA, thường trên entity hoặc trong `orm.xml`.

**`@ColumnResult.name` chỉ column label/alias trong SQL ResultSet**, không phải tên parameter procedure hay tên field Java.

Nếu SQL trả:

~~~sql
SELECT
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM purchase_orders;
~~~

thì `order_count` và `total_amount` là tên cột mà result mapping yêu cầu.

### 9.1. Dùng result-set mapping lúc tạo procedure query

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery(
        "sp_order_stats",
        "OrderStatsScalars"
    );

sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
sp.setParameter(1, customerId);

List<?> result = sp.getResultList();
~~~

Một hàng có nhiều scalar thường cần được đọc theo cấu trúc composite, chẳng hạn `Object[]`. Metadata này **chưa có nghĩa** JPA tự tạo `OrderStats`; muốn tạo DTO, dùng constructor mapping.

## 10. @ConstructorResult: tạo DTO từ result set

Procedure chọn một số cột từ hai bảng:

~~~sql
DELIMITER //

CREATE PROCEDURE sp_order_overview(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT
        o.id AS order_id,
        o.order_code AS order_code,
        c.email AS customer_email,
        o.total_amount AS total_amount
    FROM purchase_orders o
    JOIN customers c
        ON c.id = o.customer_id
    WHERE o.customer_id = p_customer_id
    ORDER BY o.id DESC;
END//

DELIMITER ;
~~~

Khai báo mapping (gắn lên entity đã quản lý, ví dụ `PurchaseOrder`):

~~~java
@SqlResultSetMapping(
    name = "OrderOverviewMapping",
    classes = @ConstructorResult(
        targetClass = OrderOverview.class,
        columns = {
            @ColumnResult(
                name = "order_id",
                type = Long.class
            ),
            @ColumnResult(
                name = "order_code",
                type = String.class
            ),
            @ColumnResult(
                name = "customer_email",
                type = String.class
            ),
            @ColumnResult(
                name = "total_amount",
                type = BigDecimal.class
            )
        }
    )
)
~~~

Record:

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

Gọi:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery(
        "sp_order_overview",
        "OrderOverviewMapping"
    );

sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
sp.setParameter(1, customerId);

List<OrderOverview> overviews = sp.getResultList()
    .stream()
    .map(OrderOverview.class::cast)
    .toList();
~~~

Constructor mapping cần:

1. ResultSet trả đúng aliases.
2. Thứ tự `@ColumnResult` khớp thứ tự constructor.
3. Kiểu Java tương thích giá trị JDBC/provider.
4. Nullability có thể chấp nhận ở constructor.
5. DTO class/record có constructor provider có thể gọi.

### 10.1. Thứ tự quan trọng hơn tên field Java

Giả sử constructor nhận:

~~~java
OrderOverview(
    Long orderId,
    String orderCode,
    String customerEmail,
    BigDecimal totalAmount
)
~~~

thì mapping theo thứ tự:

~~~text
order_id -> order_code -> customer_email -> total_amount
~~~

Nếu đảo `order_id` và `order_code` trong metadata, provider không tự biết constructor nào “gần giống tên trường” để sửa lỗi.

### 10.2. @ColumnResult.type không phải phép thuật chuyển kiểu

Khai báo `type = Long.class` thể hiện kiểu kết quả mong muốn. Tuy nhiên driver có thể trả một SQL type không thể chuyển tương thích nếu dữ liệu hoặc mapping sai.

Với `TIMESTAMP`, `JSONB`, UUID/array/spatial, cần xác nhận type mapping cụ thể thay vì tùy tiện ép mọi giá trị về String.

## 11. @NamedStoredProcedureQuery: khai báo procedure có tên

Với procedure được dùng ở nhiều repository/service, có thể đăng ký metadata:

~~~java
@NamedStoredProcedureQuery(
    name = "PurchaseOrder.byCustomerProc",
    procedureName = "sp_orders_for_customer",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            type = Long.class
        )
    },
    resultClasses = { PurchaseOrder.class }
)
~~~

Annotation được gắn vào một entity được JPA quản lý (hoặc khai báo qua XML metadata) để có hiệu lực trong persistence unit.

Cách gọi:

~~~java
StoredProcedureQuery sp =
    em.createNamedStoredProcedureQuery(
        "PurchaseOrder.byCustomerProc"
    );

sp.setParameter(1, customerId);

List<PurchaseOrder> orders = sp.getResultList()
    .stream()
    .map(PurchaseOrder.class::cast)
    .toList();
~~~

Ở đây có hai tên khác nhau:

~~~text
JPA query name:         PurchaseOrder.byCustomerProc
Database procedure:     sp_orders_for_customer
~~~

Tên JPA dùng để tìm metadata. Tên database là đối tượng mà driver/provider thực sự gọi.

### 11.1. Các thuộc tính quan trọng

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `name` | Tên truy vấn trong persistence unit |
| `procedureName` | Tên routine tại database |
| `parameters` | Mode, type và tên/vị trí các tham số |
| `resultClasses` | Các class cho result set |
| `resultSetMappings` | Tên các mapping đã đăng ký |
| `hints` | Query hints theo khả năng provider |

### 11.2. Named procedure query ánh xạ DTO

~~~java
@NamedStoredProcedureQuery(
    name = "PurchaseOrder.overviewProc",
    procedureName = "sp_order_overview",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            type = Long.class
        )
    },
    resultSetMappings = { "OrderOverviewMapping" }
)
~~~

Đọc:

~~~java
List<OrderOverview> overviews =
    em.createNamedStoredProcedureQuery(
            "PurchaseOrder.overviewProc"
        )
        .setParameter(1, customerId)
        .getResultList()
        .stream()
        .map(OrderOverview.class::cast)
        .toList();
~~~

Chọn **`resultClasses`** khi result set tương ứng entity đã mapping hợp lệ. Chọn **`resultSetMappings`** khi muốn mapping bằng `@EntityResult`, `@ConstructorResult` hoặc `@ColumnResult`.

Đừng khai báo hai chiến lược mapping mâu thuẫn cho cùng một result set.

### 11.3. Khai báo nhiều procedure

~~~java
@NamedStoredProcedureQueries({
    @NamedStoredProcedureQuery(
        name = "PurchaseOrder.byCustomerProc",
        procedureName = "sp_orders_for_customer",
        parameters = @StoredProcedureParameter(
            mode = ParameterMode.IN,
            type = Long.class
        ),
        resultClasses = PurchaseOrder.class
    ),
    @NamedStoredProcedureQuery(
        name = "PurchaseOrder.overviewProc",
        procedureName = "sp_order_overview",
        parameters = @StoredProcedureParameter(
            mode = ParameterMode.IN,
            type = Long.class
        ),
        resultSetMappings = "OrderOverviewMapping"
    )
})
~~~

Đây là ví dụ annotation bổ sung cho `PurchaseOrder`, không phải khai báo một class thứ hai.

Tên named stored procedure query được đăng ký trong phạm vi persistence unit, cần tránh collision và giữ convention rõ. Không mặc định prefix theo class được JPA tự thêm vào tên.

---

## 12. @EntityResult và @FieldResult khi aliases đặc thù

Nếu procedure trả SQL với aliases khác tên cột mapped:

~~~sql
SELECT
    o.id AS order_pk,
    o.order_code AS order_label,
    o.customer_id AS customer_fk,
    o.status AS order_status,
    o.total_amount AS amount_value,
    o.created_at AS created_value
FROM purchase_orders o;
~~~

có thể khai báo mapping tường minh:

~~~java
@SqlResultSetMapping(
    name = "OrderEntityAliased",
    entities = @EntityResult(
        entityClass = PurchaseOrder.class,
        fields = {
            @FieldResult(
                name = "id",
                column = "order_pk"
            ),
            @FieldResult(
                name = "orderCode",
                column = "order_label"
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
                column = "amount_value"
            ),
            @FieldResult(
                name = "createdAt",
                column = "created_value"
            )
        }
    )
)
~~~

Trong đó:

- `FieldResult.name` là tên property JPA.
- `FieldResult.column` là tên column alias từ SQL.
- `EntityResult.entityClass` xác định loại entity.
- `@Id` phải được ánh xạ đủ để xác định identity.

Với `@ManyToOne`, composite key, inheritance hoặc secondary tables, quy tắc field mapping có thể phức tạp hơn. Cần kiểm tra provider/đặc tả theo model cụ thể.

**`@EntityResult` không phải giải pháp để biến một result set thiếu cột bắt buộc thành entity hợp lệ.** Khi chỉ cần vài trường, dùng DTO.

## 13. Nhiều entity hoặc entity kèm scalar

Một procedure có thể trả row chứa cả order/customer và một số đếm. `@SqlResultSetMapping` hỗ trợ mô tả tập hợp entity results và scalar columns trong một mapping.

Ví dụ logic:

~~~sql
SELECT
    o.id AS order_id,
    o.order_code,
    o.customer_id,
    o.status,
    o.total_amount,
    o.created_at,
    c.id AS customer_pk,
    c.email AS customer_email,
    COUNT(*) OVER (
        PARTITION BY o.customer_id
    ) AS customer_order_count
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id;
~~~

Nhưng kết quả kết hợp có thể là `Object[]` và yêu cầu mapping nhiều aliases. Đối với màn hình báo cáo, DTO chứa một tập giá trị xác định thường dễ bảo trì hơn:

~~~java
public record OrderCustomerSummary(
    Long orderId,
    String orderCode,
    String customerEmail,
    long customerOrderCount
) {
}
~~~

Nếu stored procedure JOIN to-many, một entity root có thể lặp trên nhiều SQL rows. Không mặc định danh sách entity kết quả luôn unique chỉ vì `@Id` unique trong database; cần xem SQL cardinality và yêu cầu business.

---

## 14. OUT parameter khác result-set column

Procedure không trả SELECT mà tính tổng qua OUT:

~~~sql
DELIMITER //

CREATE PROCEDURE sp_customer_totals(
    IN p_customer_id BIGINT,
    OUT p_order_count BIGINT,
    OUT p_total_amount DECIMAL(15, 2)
)
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(total_amount), 0)
    INTO p_order_count, p_total_amount
    FROM purchase_orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
~~~

Java:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_customer_totals");

sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
sp.registerStoredProcedureParameter(
    2, Long.class, ParameterMode.OUT
);
sp.registerStoredProcedureParameter(
    3, BigDecimal.class, ParameterMode.OUT
);

sp.setParameter(1, customerId);
sp.execute();

Number countValue =
    (Number) sp.getOutputParameterValue(2);

BigDecimal totalValue =
    (BigDecimal) sp.getOutputParameterValue(3);

OrderStats stats = new OrderStats(
    countValue.longValue(),
    totalValue
);
~~~

**OUT parameters không dùng `@SqlResultSetMapping`** nếu procedure không có ResultSet tương ứng. Hãy đăng ký đúng mode/type và đọc `getOutputParameterValue`.

Nếu procedure có cả result sets và OUT, một số provider/driver yêu cầu xử lý result sets/update counts theo thứ tự trước khi lấy OUT. Không khẳng định mọi tổ hợp output đều được đọc theo bất kỳ thứ tự nào.

### 14.1. Tên tham số và vị trí tham số

Một JPA provider/driver có thể hỗ trợ đăng ký theo tên:

~~~java
sp.registerStoredProcedureParameter(
    "p_customer_id",
    Long.class,
    ParameterMode.IN
);
~~~

Nhưng **không phải mọi database/JDBC driver đều hỗ trợ named parameters giống nhau**. Đăng ký theo vị trí với chữ ký rõ ràng thường giúp ví dụ ít phụ thuộc hơn.

### 14.2. INOUT

Procedure có thể nhận một giá trị rồi trả lại giá trị điều chỉnh:

~~~sql
DELIMITER //

CREATE PROCEDURE sp_clamp_limit(
    INOUT p_limit_value INT
)
BEGIN
    SET p_limit_value =
        LEAST(GREATEST(p_limit_value, 1), 500);
END//

DELIMITER ;
~~~

Java:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_clamp_limit");

sp.registerStoredProcedureParameter(
    1, Integer.class, ParameterMode.INOUT
);
sp.setParameter(1, 1000);

sp.execute();

int adjusted =
    ((Number) sp.getOutputParameterValue(1)).intValue();
~~~

`adjusted` theo logic procedure là 500. Đây là **dữ liệu độc lập**, không có identity JPA.

## 15. REF_CURSOR trên database có hỗ trợ

Một số database dùng output cursor để trả tập hàng. Ví dụ minh họa Oracle PL/SQL:

~~~sql
CREATE OR REPLACE PROCEDURE sp_orders_cursor (
    p_customer_id IN NUMBER,
    p_rows OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_rows FOR
        SELECT
            id, order_code, customer_id,
            status, total_amount, created_at
        FROM purchase_orders
        WHERE customer_id = p_customer_id
        ORDER BY created_at DESC, id DESC;
END;
/
~~~

JPA có `ParameterMode.REF_CURSOR`:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery(
        "sp_orders_cursor",
        PurchaseOrder.class
    );

sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
sp.registerStoredProcedureParameter(
    2, void.class, ParameterMode.REF_CURSOR
);

sp.setParameter(1, customerId);

List<?> rows = sp.getResultList();
~~~

**Đây là ví dụ định hướng, không phải lời hứa về khả năng chạy nguyên xi trên mọi JPA provider/Oracle driver.** Việc dùng `void.class` và cách lấy cursor có thể khác theo implementation.

Những điều phải kiểm chứng:

- Provider có hỗ trợ REF_CURSOR không?
- Driver có nhận đúng mode/SQL type?
- Procedure trả đúng cursor/result mapping không?
- Cursor cần transaction/connection còn sống bao lâu?
- Có nhiều REF_CURSOR không? Thứ tự đọc thế nào?
- Ánh xạ về entity có đủ cột và FK không?

### 15.1. PostgreSQL có function và procedure khác nhau

PostgreSQL phân biệt `CREATE FUNCTION` và `CREATE PROCEDURE`. Các cách trả set of rows, `refcursor` hoặc gọi bằng `SELECT`/`CALL` có khác biệt so với Oracle/MySQL.

Nếu PostgreSQL function trả bảng bằng `RETURNS TABLE`, một native query:

~~~sql
SELECT * FROM fn_orders_for_customer(?1);
~~~

có thể dễ kiểm soát hơn một lời gọi `StoredProcedureQuery` trong một số môi trường.

Đừng chuyển cơ học cú pháp `CALL sp...` của MySQL sang PostgreSQL mà không xác định routine thực sự là function hay procedure.

### 15.2. Không trả raw cursor ra khỏi repository

Cursor có vòng đời gắn với database connection/transaction. Không giữ nó trong controller sau khi persistence context và connection đã đóng.

Hãy đọc result thành entity/DTO trong phạm vi tài nguyên hợp lệ, hoặc thiết kế streaming API có cơ chế quản lý connection và transaction rõ ràng.

---

## 16. Một procedure trả nhiều result sets

Ví dụ MySQL:

~~~sql
DELIMITER //

CREATE PROCEDURE sp_customer_dashboard(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT c.id, c.email
    FROM customers c
    WHERE c.id = p_customer_id;

    SELECT
        COUNT(*) AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS total_amount
    FROM purchase_orders o
    WHERE o.customer_id = p_customer_id;
END//

DELIMITER ;
~~~

Result set thứ nhất có shape:

~~~text
id | email
42 | a@example.com
~~~

Result set thứ hai:

~~~text
order_count | total_amount
3           | 950.00
~~~

Hai result sets **không thể cùng được map thành `Customer` theo một resultClass duy nhất**.

### 16.1. Duyệt kết quả theo thứ tự

Một luồng JPA minh họa:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_customer_dashboard");

sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
sp.setParameter(1, customerId);

boolean resultSet = sp.execute();

while (true) {
    if (resultSet) {
        List<?> rows = sp.getResultList();
        // Xử lý result set hiện hành theo thứ tự hợp đồng.
    } else {
        int updateCount = sp.getUpdateCount();

        if (updateCount == -1) {
            break;
        }

        // Xử lý update count hiện hành nếu có.
    }

    resultSet = sp.hasMoreResults();
}
~~~

Các điểm cần nhớ:

- `execute()` trả true nếu **kết quả đầu tiên** là result set.
- `hasMoreResults()` đi tới kết quả tiếp theo; false có thể là update count hoặc hết kết quả.
- `getUpdateCount() == -1` nghĩa không có update count hiện hành.
- Nhiều result sets có thể yêu cầu nhiều result mappings, theo thứ tự kết quả.
- Trình tự result sets/update counts có thể khác do driver hoặc routine.

Đoạn trên minh họa cơ chế duyệt; trong code thực tế, hãy viết các nhánh xử lý cho từng shape kết quả và test bằng DB mục tiêu.

### 16.2. DTO gộp nhiều kết quả

Repository có thể trả:

~~~java
public record CustomerDashboard(
    Long customerId,
    String email,
    long orderCount,
    BigDecimal totalAmount
) {
}
~~~

Service không cần biết database đã trả hai result sets. Đây là ưu điểm của **mapping dữ liệu độc lập ở tầng repository**.

### 16.3. Update counts xen kẽ

Đặc biệt trên SQL Server, procedure có thể phát thông tin update counts xen giữa các result sets tùy T-SQL/driver và cấu hình như `SET NOCOUNT ON`.

Không dùng:

~~~java
sp.execute();
List<?> result = sp.getResultList();
~~~

mà giả định result đầu tiên luôn là result set muốn lấy, nếu contract của procedure chưa được kiểm soát.

## 17. Dữ liệu NULL và kiểu Java

Trong SQL:

~~~sql
SELECT
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM purchase_orders
WHERE customer_id = ?;
~~~

khi không có hàng khớp, `COUNT(*)` trả 0 còn `SUM(...)` thường trả `NULL`.

Nếu DTO:

~~~java
public record OrderStats(
    long orderCount,
    BigDecimal totalAmount
) {
}
~~~

mong `totalAmount` không null, nên quyết định rõ:

~~~sql
COALESCE(SUM(total_amount), 0) AS total_amount
~~~

hoặc cho phép giá trị null ở DTO và xử lý tại ứng dụng.

### 17.1. Primitive không chứa được NULL

`long` không thể nhận SQL NULL theo cách thông thường. Nếu cột có thể null, dùng `Long` hoặc xử lý default rõ ràng.

### 17.2. Numeric conversion

`COUNT` có thể trả `Long` hoặc kiểu `Number` khác. `SUM(DECIMAL)` thường map `BigDecimal`, nhưng thực tế phụ thuộc database/driver/SQL CAST.

Không ép kiểu theo một ví dụ chạy trên máy khác rồi coi là hợp đồng portable.

### 17.3. Thời gian và timezone

Procedure có thể trả `DATE`, `DATETIME`, `TIMESTAMP`, hoặc kết quả của các hàm ngày giờ. Chuyển sang `LocalDateTime`, `Instant`, `OffsetDateTime` cần xét:

- Timezone của dữ liệu gốc.
- Kiểu cột có lưu thông tin timezone không.
- Quy tắc session timezone.
- JDBC type của driver.
- Cách repository muốn biểu diễn ngày giờ nghiệp vụ.

Một MySQL `DATE_FORMAT` trả string có thể không tương đương PostgreSQL `date_trunc` trả timestamp. Nếu cần DTO portable, hãy chuẩn hóa về một kiểu như `YearMonth` tại adapter.

---

## 18. Stored procedure có DML: không tự đồng bộ managed entities

Giả sử procedure:

~~~sql
DELIMITER //

CREATE PROCEDURE sp_confirm_order(
    IN p_order_id BIGINT
)
BEGIN
    UPDATE purchase_orders
    SET status = 'CONFIRMED'
    WHERE id = p_order_id
      AND status = 'DRAFT';
END//

DELIMITER ;
~~~

Trước đó JPA đã tải:

~~~java
PurchaseOrder managed =
    em.find(PurchaseOrder.class, orderId);
~~~

Sau đó:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_confirm_order");

sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
sp.setParameter(1, orderId);
sp.execute();
~~~

**DB đã có thể đổi status nhưng `managed.getStatus()` vẫn là giá trị cũ.** Procedure thực thi SQL bên ngoài dirty checking của managed entity.

Vì vậy:

- Không mặc định `@PreUpdate` được gọi.
- Không mặc định `@Version` được tăng/kiểm tra.
- Không mặc định cascade/orphanRemoval diễn ra như `em.remove`/entity mutation.
- First-level và second-level cache có thể cần invalidation/refresh.
- Kết quả entity cùng ID có thể liên quan đến managed instance đang stale.

### 18.1. Flush trước, refresh/clear sau

Khi nghiệp vụ cần đảm bảo pending entity changes được ghi trước lúc procedure đọc DB:

~~~java
em.flush();
sp.execute();
em.refresh(managed);
~~~

`flush` không commit; `refresh` tải lại state. Với procedure sửa nhiều hàng, có thể cần `clear()` hoặc một context mới tùy use case, nhưng **clear không tự flush** và có thể làm mất pending changes.

### 18.2. Optimistic locking

Giả sử entity có `@Version`. Procedure UPDATE trực tiếp:

~~~sql
UPDATE purchase_orders
SET status = 'CONFIRMED'
WHERE id = p_order_id;
~~~

không tự bảo đảm phiên bản được tăng. Nếu cần optimistic concurrency, procedure phải kiểm tra/tăng version theo thiết kế rõ:

~~~sql
UPDATE purchase_orders
SET
    status = 'CONFIRMED',
    version = version + 1
WHERE id = p_order_id
  AND version = p_expected_version;
~~~

Kết quả 0 hàng ảnh hưởng có thể là xung đột version hoặc không có row; service cần xử lý theo nghiệp vụ.

## 19. Transaction: execute không phải commit

Resource-local transaction:

~~~java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    StoredProcedureQuery sp =
        em.createStoredProcedureQuery("sp_confirm_order");

    sp.registerStoredProcedureParameter(
        1, Long.class, ParameterMode.IN
    );
    sp.setParameter(1, orderId);
    sp.execute();

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Với Spring:

~~~java
@Service
public class OrderProcedureService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void confirm(Long orderId) {
        StoredProcedureQuery sp =
            em.createStoredProcedureQuery("sp_confirm_order");

        sp.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN
        );
        sp.setParameter(1, orderId);
        sp.execute();

        // Spring transaction manager xử lý commit/rollback.
    }
}
~~~

### 19.1. Không mặc định mọi procedure rollback hoàn toàn

Một số procedure có thể chạy DDL tạo implicit commit (tùy DB), tự quản lý transaction theo quy tắc database hoặc gây side effects ngoài giao dịch.

Vì vậy phải đọc hợp đồng và body procedure trước khi hứa rằng `@Transactional` sẽ rollback mọi thay đổi của nó.

Với transaction thông thường và DML nằm trong giao dịch, rollback có thể hủy thay đổi SQL chưa commit. Nhưng email/HTTP/file viết từ routine/ứng dụng ngoài transaction không tự được hoàn tác.

## 20. Dùng named stored procedure trong repository

Một repository tốt che giấu API cụ thể khỏi tầng service:

~~~java
public interface OrderReportRepository {

    List<OrderOverview> findOverviews(Long customerId);

    OrderStats getStats(Long customerId);
}
~~~

Một implementation:

~~~java
public final class MySqlOrderReportRepository
        implements OrderReportRepository {

    private final EntityManager em;

    public MySqlOrderReportRepository(EntityManager em) {
        this.em = em;
    }

    @Override
    public List<OrderOverview> findOverviews(
            Long customerId) {

        StoredProcedureQuery sp =
            em.createNamedStoredProcedureQuery(
                "PurchaseOrder.overviewProc"
            );

        sp.setParameter(1, customerId);

        return sp.getResultList()
            .stream()
            .map(OrderOverview.class::cast)
            .toList();
    }

    @Override
    public OrderStats getStats(Long customerId) {

        StoredProcedureQuery sp =
            em.createStoredProcedureQuery("sp_order_stats");

        sp.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN
        );
        sp.setParameter(1, customerId);

        Object[] row = (Object[]) sp.getSingleResult();

        return new OrderStats(
            ((Number) row[0]).longValue(),
            (BigDecimal) row[1]
        );
    }
}
~~~

EntityManager phải được cung cấp theo scope của ứng dụng/container; **không giữ một application-managed EntityManager dùng chung đồng thời giữa nhiều thread**.

### 20.1. Vì sao repository trả DTO thay vì StoredProcedureQuery?

Tầng service không nên cần biết:

- Procedure nào trả OUT, procedure nào trả cursor.
- Result column alias là gì.
- COUNT do JDBC trả `BigInteger` hay `Long`.
- Một routine trả bao nhiêu result sets.
- Oracle/PostgreSQL/MySQL cần cú pháp gì.

Repository chuyển các kết quả kỹ thuật thành **hợp đồng nghiệp vụ ổn định**.

---

## 21. Khả chuyển giữa các hệ quản trị

`StoredProcedureQuery` là một API JPA chuẩn, nhưng bản thân procedure vẫn phụ thuộc database.

| Khía cạnh | MySQL | PostgreSQL | Oracle | SQL Server |
| --- | --- | --- | --- | --- |
| Khai báo routine | `CREATE PROCEDURE` | Function và procedure tách biệt | PL/SQL procedure/package | T-SQL procedure |
| Trả tập hàng | SELECT bên trong procedure | Function trả set, cursor hoặc cơ chế khác | REF_CURSOR phổ biến | Result sets từ procedure |
| OUT parameters | Có | Có | Có | Có |
| Cursor | Cơ chế khác Oracle | `refcursor` theo transaction | `SYS_REFCURSOR` | Cơ chế khác |
| Result type JSON | JSON functions | JSON/JSONB | Khả năng theo version | JSON qua type/functions |
| Time function | `DATE_FORMAT` | `date_trunc` | Hàm Oracle | Hàm T-SQL |
| Transaction behavior | Quy tắc MySQL | Quy tắc PostgreSQL | Quy tắc Oracle | Quy tắc SQL Server |

Không lấy SQL MySQL:

~~~sql
BEGIN
    SELECT ...
END
~~~

rồi mong đổi nguyên xi sang PostgreSQL. Trước tiên phải quyết định function hay procedure, loại output, transaction và driver support.

### 21.1. Adapter cho nhiều DB

~~~text
OrderReportService
        |
        v
OrderReportRepository
        |
        +--------------------------+
        |                          |
        v                          v
MySqlOrderReportRepository   OracleOrderReportRepository
        |                          |
SELECT result set            SYS_REFCURSOR
        |                          |
        +-------------+------------+
                      |
                      v
                 OrderOverview
~~~

Nếu DB thay đổi, service và DTO không nhất thiết phải đổi. Khác biệt nằm trong adapter.

## 22. Phân trang và khối lượng dữ liệu

Vì `StoredProcedureQuery` thừa hưởng `Query`, nhiều lập trình viên thử:

~~~java
sp.setFirstResult(40);
sp.setMaxResults(20);
~~~

Nhưng **không nên mặc định provider có thể đẩy offset/limit vào SELECT bên trong một stored procedure**. Khả năng hỗ trợ khác giữa DB và provider.

Nếu procedure trả hàng trăm nghìn rows, nên cân nhắc thêm IN parameters để phân trang trong chính SQL của procedure:

~~~sql
DELIMITER //

CREATE PROCEDURE sp_orders_page(
    IN p_customer_id BIGINT,
    IN p_limit INT,
    IN p_offset INT
)
BEGIN
    SELECT
        id, order_code, customer_id,
        status, total_amount, created_at
    FROM purchase_orders
    WHERE customer_id = p_customer_id
    ORDER BY created_at DESC, id DESC
    LIMIT p_limit OFFSET p_offset;
END//

DELIMITER ;
~~~

Phải validate `limit > 0`, `offset >= 0`, số lượng tối đa và quyền truy cập trước khi gọi.

Nếu chỉ cần report 20 dòng, trả 500.000 managed entities rồi cắt List trong Java vừa tốn bộ nhớ vừa gây áp lực lên persistence context.

### 22.1. N+1 vẫn có thể xuất hiện

Procedure trả entity `PurchaseOrder` không tự bảo đảm `customer` đã được fetch. Nếu service lặp `getCustomer().getEmail()`, JPA có thể phát SELECT bổ sung cho các lazy associations chưa tải.

DTO projection trực tiếp lấy `customer_email` có thể phù hợp hơn cho danh sách chỉ đọc.

## 23. Kiểm thử kết quả procedure

Một test chỉ mock repository không thể chứng minh JDBC driver và database đã trả đúng shape.

Cần integration test để xác nhận:

1. Procedure tồn tại trong schema đúng.
2. Tham số đúng mode, vị trí và kiểu.
3. Result sets có đúng số cột/alias.
4. `resultClasses` map đủ identity/FK.
5. `@ConstructorResult` tìm đúng constructor.
6. Null/BigDecimal/timestamp được chuyển đúng.
7. OUT/INOUT/REF_CURSOR hoạt động trên driver thực.
8. Nhiều result sets trả đúng thứ tự.
9. DML có transaction/rollback đúng.
10. Persistence context không dùng state stale không kiểm soát.
11. Query có performance phù hợp.
12. User/tenant authorization được áp dụng.

### 23.1. Fixture có ca phân biệt

| Mã đơn | Customer | Status | Total |
| --- | ---: | --- | ---: |
| PO-001 | 42 | DRAFT | 100.00 |
| PO-002 | 42 | CONFIRMED | 200.00 |
| PO-003 | 42 | CONFIRMED | 300.00 |
| PO-004 | 43 | CONFIRMED | 400.00 |

Ví dụ mong đợi:

- `sp_orders_for_customer(42)`: ba đơn PO-001, PO-002, PO-003 theo ORDER BY thực.
- `sp_count_orders_by_status('CONFIRMED')`: ba đơn trên toàn bảng.
- `sp_order_stats(42)`: count 3 và total 600.00.
- `sp_order_overview(42)`: ba record có đúng customer email và total.

Cần assert đúng ID/thứ tự/cột, không chỉ assert danh sách không rỗng.

### 23.2. Test entity result

Sau khi lấy entity trong context mở:

~~~java
List<PurchaseOrder> rows = findOrders(em, 42L);

assertEquals(3, rows.size());
assertTrue(em.contains(rows.get(0)));
~~~

Các dòng `assertEquals`, `assertTrue` là minh họa JUnit 5; muốn chạy cần import và chuẩn bị fixture/cấu hình phù hợp.

### 23.3. Test DTO result

~~~java
OrderOverview first = overviews.get(0);

assertEquals("PO-003", first.orderCode());
assertEquals(
    new BigDecimal("300.00"),
    first.totalAmount()
);
~~~

Kiểm tra alias, thứ tự và decimal scale. Với string/temporal/JSON đặc thù, thêm test mapping tại driver thực.

### 23.4. H2 không thay thế database đích

Test H2 có thể giúp xác nhận một phần JPA API, nhưng không chứng minh MySQL stored procedure, Oracle REF_CURSOR hoặc PostgreSQL function/cursor chạy tương đương trên production.

Nếu workflow dựa vào routine đặc thù, hãy chạy test trên database/version được hỗ trợ, có thể bằng test containers hoặc môi trường tích hợp riêng.

## 24. Logging và hiệu năng

Với Hibernate 6 trong development/test:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Với EclipseLink, logging thuộc tính provider-specific:

~~~xml
<property
    name="eclipselink.logging.level.sql"
    value="FINE"/>
<property
    name="eclipselink.logging.parameters"
    value="true"/>
~~~

Không phải mọi provider hiển thị các CALL/OUT/cursor giống nhau; đôi khi cần JDBC logging hoặc profiling tại database.

**Không bật bind logging chứa dữ liệu cá nhân/tài chính trong production mà không có quy tắc bảo mật.**

Đối với performance:

- Xem SQL/plan bên trong procedure.
- Đánh giá index, JOIN, sort, scan.
- Giới hạn result-set size.
- Xem số lần procedure được gọi mỗi request.
- Cân nhắc memory của managed entity graph.
- Cân nhắc query/report trả DTO thay entity nếu chỉ đọc.
- Theo dõi thời gian giữ connection/transaction/cursor.

Stored procedure không mặc định nhanh hơn một câu JPQL tạo SQL tương đương.

## 25. Bảo mật: bind parameter chưa đủ

Ví dụ:

~~~java
sp.setParameter(1, customerIdFromRequest);
~~~

Binding tránh việc dữ liệu bị ghép vào SQL text ở Java, nhưng **không xác nhận người dùng có quyền xem customer đó**.

Service cần kiểm tra authorization/tenant context. Với procedure có quyền definer/invoker đặc thù, cần chú ý:

- Chỉ cấp quyền EXECUTE cho đúng account.
- Procedure không tự ghép dynamic SQL từ input không kiểm soát.
- ResultSet/OUT không tiết lộ dữ liệu vượt quyền.
- Thông tin nhạy cảm không bị đưa ra log.
- Không cho client chọn tên procedure tùy ý.

Nếu procedure tự tạo dynamic SQL bằng phép nối string, nguy cơ injection vẫn tồn tại **bên trong database**, dù Java dùng `setParameter`.

## 26. Lỗi thường gặp và nguyên nhân

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy named procedure query | Sai tên metadata hoặc entity chưa đăng ký | Kiểm tra `name` và persistence unit |
| Database báo procedure không tồn tại | Sai schema/name hoặc chưa migration | Kiểm tra catalog và quyền |
| Không gọi được procedure | Sai kiểu/mode/thứ tự tham số | Đối chiếu signature DB |
| OUT không có giá trị | Chưa đăng ký OUT hoặc đọc không đúng trình tự | Kiểm tra `ParameterMode` và kết quả trước OUT |
| REF_CURSOR lỗi | Driver/provider/version/transaction không hỗ trợ | Integration test trên DB thật |
| Entity mapping thiếu field | ResultSet trả partial columns | Chọn đủ cột hoặc DTO |
| DTO constructor mismatch | Sai alias, thứ tự hoặc kiểu | Sửa `@ColumnResult` và constructor |
| COUNT cast lỗi | JDBC trả Number subtype khác | Dùng `Number` rồi convert |
| Có hai result sets nhưng chỉ đọc một | Không dùng cơ chế result traversal | Dùng `hasMoreResults`/`getUpdateCount` |
| Update count xuất hiện trước SELECT | Procedure có DML hoặc driver protocol | Kiểm tra result sequence |
| Entity không đổi sau procedure DML | Context giữ managed state cũ | Refresh/clear có kiểm soát |
| @Version không tăng | SQL procedure không có version logic | Thiết kế optimistic concurrency trong routine |
| SQL chạy ở MySQL nhưng lỗi PostgreSQL | Khác cơ chế routine/result | Tách adapter theo DB |
| DTO API có lazy loading exception | Đang trả entity không đủ fetch | Dùng DTO/explicit fetch |
| N+1 khi duyệt Customer | Association LAZY chưa tải | Projection hoặc fetch strategy |
| Transaction rollback không như mong đợi | Implicit commit/side effect | Kiểm tra body procedure và DB semantics |
| Runtime chậm/bộ nhớ tăng | Result sets quá lớn hoặc entity graph | Paging/aggregation/DTO và profiling |
| SQL injection qua procedure | SQL động trong routine ghép input | Parameterization và whitelist bên trong DB |
| Lộ dữ liệu xuyên tenant | Thiếu authorization filter | Kiểm tra tenant/user theo nguồn tin cậy |

## 27. Bài tập thực hành

### Bài 1. Entity hay DTO?

Procedure trả `id`, `order_code`, `total_amount` nhưng entity còn `customer_id`, `status`, `created_at`.

**Đáp án:** Dùng DTO projection vì result set thiếu những cột quan trọng cho entity mapping. Không dựa vào `@Id` duy nhất để nhận một entity hoàn chỉnh.

### Bài 2. COUNT(*) trả Long?

`getSingleResult()` trả một loại `Number` khác `Long`.

**Đáp án:** Với scalar native chưa có mapping kiểu cố định, dùng `((Number) value).longValue()`. Đừng ép `(Long)` mà không kiểm chứng provider.

### Bài 3. OUT p_count

Procedure trả `OUT p_count` thay vì `SELECT COUNT(*)`.

**Đáp án:** Đăng ký `ParameterMode.OUT`, gọi `execute()` rồi `getOutputParameterValue(...)`. Không dùng result-set mapping để đọc một OUT parameter không thuộc ResultSet.

### Bài 4. ConstructorResult

Record nhận `(Long, String, BigDecimal)` nhưng metadata khai báo `(String, Long, BigDecimal)`.

**Đáp án:** Phải sửa thứ tự `@ColumnResult` cho khớp constructor; tên field của record không tự tái sắp xếp đối số.

### Bài 5. Entity cũ sau procedure UPDATE

Một entity đã managed có status DRAFT; procedure đổi DB thành CONFIRMED.

**Đáp án:** JPA không tự bảo đảm managed state cập nhật sau SQL bên trong procedure. Cân nhắc `refresh` hoặc context mới, và đảm bảo transaction/pending changes phù hợp.

### Bài 6. Nhiều result sets

Procedure trả danh sách khách hàng và số liệu tổng hợp.

**Đáp án:** Đọc các result sets theo đúng thứ tự, kiểm tra update counts xen giữa. Không map cả hai result sets về cùng entity class nếu shape khác nhau.

### Bài 7. Oracle REF_CURSOR

Procedure trả `SYS_REFCURSOR`.

**Đáp án:** Dùng cơ chế REF_CURSOR theo JPA/provider hỗ trợ, kiểm chứng transaction, driver và result mapping trên Oracle thực tế. Không áp dụng máy móc ví dụ MySQL.

### Bài 8. DTO có được merge không?

Service nhận `OrderOverview` record và gọi `em.merge(overview)`.

**Đáp án:** Không. `merge` dành cho entity; DTO không có managed identity. Muốn cập nhật phải dùng use case ghi và entity/procedure có transaction.

### Bài 9. PostgreSQL function

Hệ thống dùng PostgreSQL `RETURNS TABLE` function.

**Đáp án:** Có thể cân nhắc `SELECT * FROM function(...)` qua native query nếu phù hợp, thay vì mặc định dùng `StoredProcedureQuery` theo cú pháp MySQL CALL.

### Bài 10. Version conflict

Procedure UPDATE không kiểm tra `version` nhưng entity dùng `@Version`.

**Đáp án:** Native DML không tự tôn trọng optimistic locking của managed entity. Thiết kế điều kiện so phiên bản và tăng version trong procedure khi business yêu cầu.

### Bài 11. Test H2

Stored procedure chạy trên H2 nhưng production dùng Oracle REF_CURSOR.

**Đáp án:** Chưa đủ. Phải integration test với database/driver/provider được hỗ trợ.

### Bài 12. Procedure trả 100.000 entities

Ứng dụng chỉ cần tổng doanh thu và số đơn.

**Đáp án:** Nên để database aggregate, trả scalar/DTO nhỏ gọn thay vì tạo nhiều managed entities không cần thiết.

## 28. Checklist trước khi chọn mapping

1. **Routine có thật là procedure không?** Với PostgreSQL, có thể là function trả bảng.
2. **Result là OUT, REF_CURSOR hay result set?** Đọc bằng API thích hợp.
3. **Có bao nhiêu result sets/update counts?** Hợp đồng thứ tự là gì?
4. **Có đầy đủ cột entity và PK/FK không?** Nếu không, chọn DTO.
5. **Result cần managed identity/dirty checking không?** Nếu không, DTO/scalar thường đủ.
6. **Alias SQL có khớp `@ColumnResult`/`@FieldResult` không?**
7. **Constructor và thứ tự dữ liệu có tương thích không?**
8. **Numeric/temporal/JSON/NULL được map ra sao?**
9. **Transaction nào quản lý lời gọi?** Có implicit commit hoặc side effect không?
10. **Procedure DML có làm managed context stale không?**
11. **Optimistic versioning, callback, cascade cần bảo đảm ở tầng nào?**
12. **Có rủi ro N+1 hoặc materialize quá nhiều entity không?**
13. **Quyền EXECUTE và tenant/user authorization đã đúng chưa?**
14. **Có test với DB thật và schema migration mới nhất không?**
15. **Có adapter để cách gọi procedure không lan sang service/controller không?**

## 29. Tổng kết

Cơ chế tổng quát:

~~~text
Procedure trong database
           |
           +--- OUT / INOUT ------> Java value / DTO
           |
           +--- ResultSet đủ cột -> EntityResult / resultClasses
           |                        -> JPA managed entity
           |
           +--- ResultSet projection
           |                        -> ColumnResult / ConstructorResult
           |                        -> scalar / Object[] / DTO / record
           |
           +--- REF_CURSOR / nhiều result sets
                                    |
                                    v
                              DB + JDBC + provider
                              + thứ tự kết quả
                              + resource lifecycle
~~~

Những điều cần ghi nhớ:

- **Entity mapping** có ý nghĩa identity và persistence context; phải nhận đủ dữ liệu cần thiết để materialize entity.
- **Dữ liệu độc lập** nên được biểu diễn bằng scalar hoặc DTO/record khi procedure trả projection/tổng hợp; không có dirty checking.
- **`@SqlResultSetMapping`** cung cấp `@EntityResult`, `@ConstructorResult` và `@ColumnResult`.
- **`@NamedStoredProcedureQuery`** giúp đăng ký procedure, parameter modes và result mappings để tái sử dụng.
- **OUT/INOUT** không đồng nghĩa một ResultSet, và **REF_CURSOR/multiple results** phải được thử với DB/driver/provider cụ thể.
- **Procedure DML** có thể làm persistence context stale và không tự xử lý JPA callbacks, cascade hay version.
- **Tính khả chuyển của API JPA không đồng nghĩa procedure portable giữa DB**; nên cô lập khác biệt trong repository adapter.
- **Integration test** trên database mục tiêu là bằng chứng cần thiết cho mapping, transaction, output và hiệu năng.

**Chỉ chọn entity khi kết quả của stored procedure thực sự mang identity và trạng thái đầy đủ của entity. Với các dữ liệu tổng hợp, projection hoặc giá trị độc lập, DTO/scalar có hợp đồng rõ ràng là lựa chọn dễ hiểu và dễ bảo trì hơn.**
