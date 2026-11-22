# @SqlResultSetMapping, constructor result và giới hạn kiểu kết quả trong Hibernate ORM

## 1. Khi native SQL không thể tự biến mọi hàng kết quả thành DTO

Trong Hibernate ORM, HQL và Criteria API thường giúp truy vấn theo entity và các thuộc tính Java đã được ánh xạ. Tuy nhiên, đôi khi ứng dụng cần SQL gốc (native SQL) để tận dụng các tính năng của PostgreSQL, query phân tích, CTE, window function, hoặc một báo cáo cần tối ưu trực tiếp theo schema vật lý.

Ví dụ một màn hình quản trị muốn hiển thị:

| Mã khách | Số đơn đã thanh toán | Tổng doanh thu |
|---:|---:|---:|
| 10 | 5 | 1.450.000 |
| 20 | 3 | 860.000 |

SQL có thể là:

~~~sql
SELECT
    o.customer_id AS customer_id,
    COUNT(*) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_amount
FROM purchase_orders o
WHERE o.status = 'PAID'
GROUP BY o.customer_id
ORDER BY total_amount DESC;
~~~

Kết quả database không phải entity PurchaseOrder: mỗi hàng chứa customer_id, order_count và total_amount, trong đó hai cột là kết quả aggregate. Vì thế truy vấn:

~~~java
entityManager.createNativeQuery(sql, PurchaseOrder.class);
~~~

không phù hợp: SQL không trả đủ dữ liệu để dựng một PurchaseOrder có trạng thái hợp lệ. Còn truy vấn không chỉ định mapping:

~~~java
entityManager.createNativeQuery(sql).getResultList();
~~~

thường trả các giá trị scalar theo JDBC/Hibernate; khi có nhiều cột, mỗi hàng thường là Object[]. Ứng dụng phải hiểu vị trí cột và kiểu dữ liệu cụ thể mới sử dụng an toàn.

**@SqlResultSetMapping** là cách Jakarta Persistence khai báo một ánh xạ có tên để nói cho provider biết: hàng kết quả native SQL cần trở thành entity, một DTO qua constructor, các scalar hoặc sự kết hợp của chúng.

Bài này thuộc chương **SQL gốc**, tập trung vào ba vấn đề:

1. Khai báo và dùng **@SqlResultSetMapping**.
2. Dùng **@ConstructorResult** để tạo đối tượng từ các cột SQL.
3. Hiểu **giới hạn kiểu kết quả**, từ alias, JDBC numeric, nullable, enum, timestamp, UUID, JSON đến kết quả hỗn hợp và lifecycle của entity.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt native query trả entity, scalar, DTO và Object[].
- Khai báo @SqlResultSetMapping với @ColumnResult, @ConstructorResult và @EntityResult.
- Ánh xạ tên alias SQL sang constructor argument đúng thứ tự và kiểu.
- Biết khi nào @FieldResult cần ánh xạ alias của entity.
- Hiểu ý nghĩa entity managed khác với DTO được tạo bằng constructor.
- Nhận biết lỗi chuyển đổi BigInteger/Long, BigDecimal/Double, enum, JSON, UUID và thời gian.
- Dùng @NamedNativeQuery và EntityManager với mapping có tên.
- Viết native SQL có parameter an toàn, phân trang, count và giới hạn tenant.
- Kiểm thử ánh xạ trên database/dialect thực tế thay vì suy luận từ object Java.

Ví dụ dùng Java 17+, Jakarta Persistence, Hibernate ORM 6.x và PostgreSQL. Các tên class trong bài độc lập về mặt khái niệm; khi áp dụng vào một dự án cụ thể, đặt các public class/record vào file Java riêng và bổ sung import, migration, transaction, quyền truy cập phù hợp. Những ví dụ về conversion có thể thay đổi tùy JDBC driver, Hibernate version và SQL type; cần xác nhận trên runtime mục tiêu.

## 2. Mô hình dữ liệu cho các ví dụ

Giả sử hệ thống có khách hàng và đơn hàng:

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ PURCHASE_ORDERS : places
    PURCHASE_ORDERS ||--o{ ORDER_ITEMS : contains
    CUSTOMERS {
        bigint id PK
        varchar full_name
        varchar email
    }
    PURCHASE_ORDERS {
        bigint id PK
        bigint tenant_id
        bigint customer_id FK
        varchar status
        numeric total_amount
        timestamptz created_at
        timestamptz deleted_at
    }
    ORDER_ITEMS {
        bigint id PK
        bigint order_id FK
        integer quantity
    }
~~~

Một entity PurchaseOrder rút gọn:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Instant getCreatedAt() { return createdAt; }
}

enum OrderStatus { DRAFT, PAID, CANCELLED }
~~~

Customer:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @Column(nullable = false)
    private String email;

    protected Customer() {}

    public Long getId() { return id; }
    public String getFullName() { return fullName; }
    public String getEmail() { return email; }
}
~~~

Lưu ý phân biệt:

| Mô hình Java/HQL | SQL vật lý |
|---|---|
| PurchaseOrder | purchase_orders |
| PurchaseOrder.totalAmount | total_amount |
| PurchaseOrder.createdAt | created_at |
| PurchaseOrder.customer | customer_id |
| Customer.fullName | full_name |

Native SQL dùng **tên bảng và cột vật lý**, còn các annotation EntityResult/FieldResult dùng **entity class và thuộc tính Java được mapping**. Sự kết hợp của hai cách đặt tên chính là nguồn gốc của nhiều lỗi @SqlResultSetMapping.

## 3. Những cách trả kết quả từ native SQL

Có nhiều hướng, mỗi hướng phù hợp với một loại dữ liệu:

| Cách | Kết quả chính | Khi nào phù hợp |
|---|---|---|
| createNativeQuery(sql) | Scalar hoặc Object[] theo JDBC/provider | Query thử nghiệm, ít cột, mapping thủ công có kiểm soát |
| createNativeQuery(sql, Entity.class) | Entity được ORM dựng từ row | Query trả đủ cột cần cho một entity được mapping |
| @SqlResultSetMapping + @ColumnResult | Scalar có alias và kiểu mong muốn | Báo cáo ít cột, không cần DTO |
| @SqlResultSetMapping + @ConstructorResult | DTO/record do constructor tạo | Báo cáo nhiều cột, read model/API response |
| @SqlResultSetMapping + @EntityResult | Entity từ native query | Cần entity được Hibernate quản lý |
| Mapping kết hợp EntityResult/ConstructorResult/ColumnResult | Một hàng chứa nhiều phần kết quả | Query cần entity và số liệu đi kèm |
| Tuple transformer / RowMapper | Ánh xạ theo chương trình, thường provider/framework-specific | Mapping động/phức tạp hoặc cần xử lý linh hoạt |

Không có một cơ chế nào tự chuyển mọi kiểu SQL thành mọi kiểu Java. @SqlResultSetMapping khai báo **hình dạng tĩnh** cho hàng kết quả và vẫn phải phù hợp metadata/result type mà JDBC cung cấp.

### 3.1. Native query không có mapping

~~~java
String sql = """
    SELECT o.customer_id, COUNT(*), SUM(o.total_amount)
    FROM purchase_orders o
    WHERE o.status = 'PAID'
    GROUP BY o.customer_id
    """;

@SuppressWarnings("unchecked")
List<Object[]> rows = entityManager
    .createNativeQuery(sql)
    .getResultList();

for (Object[] row : rows) {
    Object customerId = row[0];
    Object orderCount = row[1];
    Object total = row[2];
}
~~~

Khi SQL trả nhiều cột và không có mapping, giá trị nằm ở vị trí 0, 1, 2. Kiểu runtime có thể là Long, Integer, BigInteger, BigDecimal hoặc kiểu driver khác tùy SQL type và provider.

Không viết:

~~~java
Long count = (Long) row[1];
~~~

chỉ vì COUNT “về mặt ý nghĩa” là số nguyên; cần xác nhận kiểu do runtime trả về hoặc khai báo conversion rõ ràng. Lỗi thường gặp là ClassCastException khi SQL/JDBC trả BigInteger nhưng code cast trực tiếp sang Long.

### 3.2. Result type không phải entity

Một native query select COUNT hoặc SUM không tự tạo PurchaseOrder. Việc truyền PurchaseOrder.class làm resultClass không biến một hàng aggregate thành entity hợp lệ. Đối tượng entity cần có khóa định danh và các cột cần thiết theo mapping của Hibernate.

Tương tự, không mặc định overload createNativeQuery(sql, MyDto.class) tự hoạt động portable với mọi DTO Java ở mọi JPA version/provider. Nếu project cần mapping DTO đáng tin cậy theo metadata JPA, @ConstructorResult là một lựa chọn rõ ràng.

## 4. @SqlResultSetMapping là một ánh xạ có tên

Ví dụ tối giản:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
@SqlResultSetMapping(
    name = "OrderCountScalars",
    columns = {
        @ColumnResult(name = "customer_id", type = Long.class),
        @ColumnResult(name = "order_count", type = Long.class)
    }
)
public class PurchaseOrder {
    @Id
    private Long id;
    // Các field được mapping khác.
}
~~~

Ở đây:

- **name:** định danh mapping, ví dụ OrderCountScalars.
- **columns:** danh sách các cột scalar cần trích từ ResultSet.
- **@ColumnResult.name:** label/alias trong kết quả SQL, không nhất thiết là tên cột bảng.
- **@ColumnResult.type:** kiểu Java muốn đọc ra, nếu phù hợp với JDBC value và Hibernate conversion.

SQL:

~~~sql
SELECT
    o.customer_id AS customer_id,
    COUNT(*) AS order_count
FROM purchase_orders o
WHERE o.tenant_id = ?
GROUP BY o.customer_id
ORDER BY customer_id;
~~~

Thực thi:

~~~java
@SuppressWarnings("unchecked")
List<Object[]> rows = entityManager
    .createNativeQuery(sql, "OrderCountScalars")
    .setParameter(1, authenticatedTenantId)
    .getResultList();
~~~

Với hai ColumnResult, một hàng thường là Object[] gồm hai phần theo thứ tự khai báo. Nếu chỉ một scalar result, kết quả mỗi hàng có thể là giá trị đơn, không cần Object[].

### 4.1. Annotation đặt ở đâu?

@SqlResultSetMapping thường được khai báo trên một **entity class được Jakarta Persistence quản lý**, ngay cả khi mapping đó tạo DTO không liên quan trực tiếp đến entity chứa annotation. Đây là metadata của persistence unit, không phải một phương thức chuyển đổi gắn với một SQL string cụ thể.

Ví dụ đặt OrderTotalsMapping trên PurchaseOrder chỉ là một nơi khai báo. Một query native ở repository khác vẫn có thể gọi mapping theo tên nếu metadata đó đã được provider đăng ký trong cùng persistence unit.

Không đặt @SqlResultSetMapping trên một record DTO thông thường rồi mặc định Hibernate sẽ quét record đó như managed entity. Nếu DTO không phải managed type, metadata của annotation có thể không được đăng ký. Có thể chọn entity thích hợp để đăng ký mapping hoặc dùng XML mapping được cấu hình nếu dự án sử dụng cách đó.

### 4.2. Một entity có nhiều mapping

~~~java
@Entity
@SqlResultSetMappings({
    @SqlResultSetMapping(
        name = "OrderCountScalars",
        columns = @ColumnResult(name = "order_count",
                                type = Long.class)
    ),
    @SqlResultSetMapping(
        name = "OrderAmountScalars",
        columns = @ColumnResult(name = "total_amount",
                                type = BigDecimal.class)
    )
})
public class PurchaseOrder {
    @Id
    private Long id;
}
~~~

Lưu ý tên mapping phải rõ ràng, không xung đột với mapping khác trong phạm vi metadata persistence unit. Khi dự án lớn, dùng tên có namespace như OrderAnalytics.CustomerTotals để tránh trùng tên.

### 4.3. Mapping là tĩnh, còn SQL có thể động

@SqlResultSetMapping không tự thay đổi cấu trúc khi SELECT thêm hoặc bỏ cột. Một mapping constructor với ba cột mong đợi ba alias tương ứng; nếu một nhánh SQL không trả total_amount, query có thể thất bại lúc trích ResultSet.

Các điều kiện WHERE có thể thay đổi động mà vẫn dùng mapping, nhưng **hình dạng cột/alias của SELECT phải ổn định**. Nếu report có các bộ trường thay đổi tùy input, cân nhắc nhiều DTO/mapping riêng hoặc RowMapper/transformer với kiểm soát rõ ràng.

## 5. @ConstructorResult: tạo DTO bằng constructor

Ta muốn trả:

~~~java
package com.example.shop.reporting;

import java.math.BigDecimal;

public record CustomerOrderTotals(
    Long customerId,
    Long orderCount,
    BigDecimal totalAmount
) {}
~~~

Record có canonical constructor nhận đúng ba tham số theo thứ tự khai báo.

### 5.1. Khai báo @ConstructorResult

Ví dụ annotation đặt trên PurchaseOrder:

~~~java
import com.example.shop.reporting.CustomerOrderTotals;
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
@SqlResultSetMapping(
    name = "CustomerOrderTotalsMapping",
    classes = @ConstructorResult(
        targetClass = CustomerOrderTotals.class,
        columns = {
            @ColumnResult(name = "customer_id",
                          type = Long.class),
            @ColumnResult(name = "order_count",
                          type = Long.class),
            @ColumnResult(name = "total_amount",
                          type = BigDecimal.class)
        }
    )
)
public class PurchaseOrder {
    @Id
    private Long id;
    // Các thuộc tính persistent khác.
}
~~~

Trong project thực, chỉ khai báo một class PurchaseOrder, thêm annotation mapping vào entity hiện có; các class PurchaseOrder rút gọn ở những đoạn code là các cách minh họa thay thế nhau, không phải các entity trùng tên để copy đồng thời.

### 5.2. SQL phải trả alias đúng

~~~java
String sql = """
    SELECT
        o.customer_id AS customer_id,
        COUNT(*) AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS total_amount
    FROM purchase_orders o
    WHERE o.tenant_id = :tenantId
      AND o.status = :status
      AND o.deleted_at IS NULL
    GROUP BY o.customer_id
    ORDER BY total_amount DESC, customer_id ASC
    """;
~~~

Các alias customer_id, order_count, total_amount khớp chính xác các @ColumnResult.name. Chúng không cần là tên field của record (customerId, orderCount, totalAmount); **constructor nhận theo vị trí khai báo trong columns**, không tự gán theo tên record component.

### 5.3. Thực thi native query bằng mapping name

~~~java
@Transactional(readOnly = true)
@SuppressWarnings("unchecked")
public List<CustomerOrderTotals> totals(
        Long authenticatedTenantId) {

    return entityManager.createNativeQuery("""
        SELECT
            o.customer_id AS customer_id,
            COUNT(*) AS order_count,
            COALESCE(SUM(o.total_amount), 0) AS total_amount
        FROM purchase_orders o
        WHERE o.tenant_id = :tenantId
          AND o.status = :status
          AND o.deleted_at IS NULL
        GROUP BY o.customer_id
        ORDER BY total_amount DESC, customer_id ASC
        """, "CustomerOrderTotalsMapping")
        .setParameter("tenantId", authenticatedTenantId)
        .setParameter("status", "PAID")
        .getResultList();
}
~~~

Trong Hibernate, native query thường hỗ trợ named parameter như :tenantId. Tuy nhiên, **khả năng portable của named parameter trong native SQL không giống JPQL**; khi cần đi qua nhiều provider, positional parameter được hỗ trợ rộng rãi hơn theo JPA contract. Giá trị status ở ví dụ là literal database VARCHAR ứng với enum được lưu dạng STRING; nếu schema lưu enum theo kiểu khác, parameter/SQL phải được điều chỉnh.

### 5.4. Điều gì xảy ra khi Hibernate xử lý một hàng?

~~~mermaid
flowchart TD
    A[Native SQL SELECT] --> B[JDBC ResultSet]
    B --> C[Đọc alias customer_id]
    B --> D[Đọc alias order_count]
    B --> E[Đọc alias total_amount]
    C --> F[Convert sang Long]
    D --> G[Convert sang Long]
    E --> H[Convert sang BigDecimal]
    F --> I[Constructor CustomerOrderTotals]
    G --> I
    H --> I
    I --> J[DTO record, không managed]
~~~

Provider nhận các scalar, chuyển thành kiểu tương thích theo mapping rồi gọi constructor thích hợp. Đây không phải quá trình dựng entity managed hoặc lazy-load association.

## 6. Thứ tự constructor quan trọng hơn tên field

Xét record:

~~~java
public record CustomerOrderTotals(
    Long customerId,
    Long orderCount,
    BigDecimal totalAmount
) {}
~~~

Mapping đúng:

~~~java
columns = {
    @ColumnResult(name = "customer_id", type = Long.class),
    @ColumnResult(name = "order_count", type = Long.class),
    @ColumnResult(name = "total_amount", type = BigDecimal.class)
}
~~~

Nếu đổi thứ tự hai cột đầu:

~~~java
columns = {
    @ColumnResult(name = "order_count", type = Long.class),
    @ColumnResult(name = "customer_id", type = Long.class),
    @ColumnResult(name = "total_amount", type = BigDecimal.class)
}
~~~

Hibernate có thể vẫn tìm được constructor (Long, Long, BigDecimal) và gọi được, nhưng **customerId và orderCount bị đảo ngữ nghĩa**. Đây là lỗi nguy hiểm hơn ClassCastException vì code có thể chạy mà báo cáo sai.

Vì vậy cần kiểm thử giá trị đầu ra, không chỉ test DTO khác null. Một test với customer ID = 10 và số đơn = 5 dễ phát hiện việc đảo vị trí này.

### 6.1. Constructor phải tồn tại và có thể truy cập

Nếu mapping khai báo (Long, Long, BigDecimal) nhưng class chỉ có:

~~~java
public CustomerOrderTotals(Long customerId, int count,
                           BigDecimal amount) { /* ... */ }
~~~

thì provider có thể không tìm được constructor tương thích hoặc phát sinh lỗi type conversion. Nên dùng một constructor/record canonical rõ ràng và khai báo @ColumnResult.type phù hợp.

Không dựa vào việc Hibernate tự đoán tên parameter của Java constructor bằng tên alias SQL. @ConstructorResult xác định đối số chủ yếu bằng **thứ tự** và kiểu khai báo.

### 6.2. Khi nào dùng class thay vì record?

~~~java
public final class CustomerOrderTotals {
    private final Long customerId;
    private final Long orderCount;
    private final BigDecimal totalAmount;

    public CustomerOrderTotals(
            Long customerId, Long orderCount,
            BigDecimal totalAmount) {
        this.customerId = customerId;
        this.orderCount = orderCount;
        this.totalAmount = totalAmount;
    }

    public Long getCustomerId() { return customerId; }
    public Long getOrderCount() { return orderCount; }
    public BigDecimal getTotalAmount() { return totalAmount; }
}
~~~

@ConstructorResult hoạt động với một class có constructor tương thích, không bắt buộc record. Record tiện cho immutable read model; class phù hợp khi cần logic/serialization riêng. DTO không cần @Entity, @Id, no-arg constructor hay setters.

## 7. @ColumnResult và kiểu dữ liệu JDBC

Khi truy vấn scalar, SQL type và cách JDBC driver materialize giá trị quyết định kiểu thực tế trước khi Hibernate áp dụng type mapping.

Một số kiểu thường gặp:

| SQL expression / PostgreSQL type | Giá trị Java thường gặp | Lưu ý |
|---|---|---|
| bigint | Long | Integer có thể không đủ miền giá trị |
| integer | Integer | Không tự cast Integer sang Long bằng ép object |
| numeric/decimal | BigDecimal | Dùng cho tiền, giữ precision |
| COUNT(*) | Long/bigint trên PostgreSQL, provider có thể convert khác | Nên khai báo type và test runtime |
| SUM(numeric) | BigDecimal | SUM của tập rỗng có thể là NULL |
| AVG(numeric) | BigDecimal hoặc kiểu số khác tùy dialect/expression | Kiểm tra scale/precision |
| real/double precision | Float/Double | Không dùng cho tiền nếu cần chính xác thập phân |
| varchar/text | String | Collation/encoding theo database |
| boolean | Boolean | NULL dùng Boolean, không dùng primitive |
| date | java.sql.Date/LocalDate tùy đường mapping | Test driver/provider |
| timestamp/timestamptz | Timestamp/Instant/OffsetDateTime tùy mapping | Cần chính sách timezone rõ |
| UUID | UUID/String/driver-specific | Kiểm tra JDBC type và cast |
| json/jsonb | String/PGobject/kiểu tùy Hibernate | Không có ánh xạ DTO nested tự động |
| SQL array | java.sql.Array hoặc kiểu provider-specific | Không mặc định thành List Java |

Đây là những kết quả thường gặp, **không phải một hợp đồng rằng mọi dialect trả cùng Java class**. Khác với thuộc tính entity đã có @JdbcTypeCode/@Convert/mapping rõ ràng, scalar expression từ native SQL có thể được provider suy luận qua ResultSetMetaData.

### 7.1. Tại sao type của @ColumnResult hữu ích?

~~~java
@ColumnResult(name = "order_count", type = Long.class)
~~~

Nó giúp nhà cung cấp JPA biết kiểu Java mong muốn. Tuy nhiên, type không phải một bộ chuyển đổi vạn năng. Nếu database trả JSONB kiểu đặc thù hoặc một giá trị vượt miền Long, việc chỉ ghi type = Long.class không bảo đảm truy vấn thành công.

### 7.2. Đừng cast Number sai kiểu

Nếu đang dùng mapping thủ công không khai báo type:

~~~java
Object raw = row[1];
Long count = (Long) raw; // Có thể ClassCastException.
~~~

Cách phòng thủ khi yêu cầu tổng quát là Number:

~~~java
Object raw = row[1];
if (!(raw instanceof Number n)) {
    throw new IllegalStateException(
        "Giá trị order_count không phải Number");
}
long count = n.longValue();
~~~

Nhưng longValue() có thể **cắt phần thập phân hoặc tràn số** nếu kiểu Number không phù hợp. Với dữ liệu quan trọng, xác định SQL type, kiểm tra miền giá trị và dùng chuyển đổi chính xác, ví dụ:

~~~java
long count;
if (raw instanceof java.math.BigInteger bi) {
    count = bi.longValueExact();
} else if (raw instanceof java.math.BigDecimal bd) {
    count = bd.longValueExact();
} else if (raw instanceof Long l) {
    count = l;
} else if (raw instanceof Integer i) {
    count = i.longValue();
} else {
    throw new IllegalArgumentException(
        "Kiểu count không được hỗ trợ: " + raw.getClass());
}
~~~

Ví dụ này dành cho giá trị non-null; trong code thật phải kiểm tra null trước khi gọi getClass(). Nếu đã dùng @ColumnResult(type=Long.class) và integration test xác nhận kiểu ổn định, không nhất thiết phải chuyển đổi thủ công nhiều nhánh như trên.

### 7.3. COUNT có thể lớn hơn Integer.MAX_VALUE

Không để DTO dùng Integer chỉ vì dữ liệu thử nghiệm có 10 hàng. PostgreSQL COUNT(*) trả bigint; số đếm trong production có thể vượt 2,1 tỷ. Long thường hợp lý hơn cho count. Nếu yêu cầu đếm vượt 64 bit (hiếm trong thực tế), chọn kiểu/thiết kế thích hợp thay vì ép kiểu mất dữ liệu.

## 8. SUM, AVG, NULL và BigDecimal

Giả sử báo cáo tổng tiền của một khách:

~~~sql
SELECT SUM(o.total_amount) AS total_amount
FROM purchase_orders o
WHERE o.customer_id = ?;
~~~

Nếu không có hàng phù hợp, SUM trả NULL theo ngữ nghĩa SQL, trong khi COUNT(*) trả 0. DTO có field BigDecimal có thể nhận null, nhưng nếu business muốn 0 thì SQL phải quy định:

~~~sql
SELECT COALESCE(
    SUM(o.total_amount), CAST(0 AS NUMERIC)
) AS total_amount
FROM purchase_orders o
WHERE o.customer_id = ?;
~~~

COALESCE không nên dùng vô điều kiện nếu NULL mang nghĩa “chưa có số liệu”. Hãy xác định policy business trước.

### 8.1. Không dùng double để lưu tiền

~~~java
public record OrderSummary(double totalAmount) {}
~~~

Nếu SQL dùng numeric/decimal thì BigDecimal thường thích hợp hơn:

~~~java
public record OrderSummary(BigDecimal totalAmount) {}
~~~

Double là số dấu phẩy động nhị phân, có thể không biểu diễn chính xác các giá trị tiền thập phân. Nếu tính phần trăm, tỷ lệ hoặc báo cáo khoa học cần Double thì chọn có chủ đích, không mặc định mọi aggregate là Double.

### 8.2. AVG và độ chính xác

~~~sql
SELECT AVG(o.total_amount) AS avg_amount
FROM purchase_orders o;
~~~

Kết quả của AVG có thể có nhiều chữ số thập phân hơn kiểu cột nguồn. Không tự đặt scale=2 trong DTO constructor nếu nghiệp vụ cần giữ độ chính xác trung gian. Nên phân biệt **giá trị tính toán** với **cách hiển thị**, và làm tròn theo policy khi cần.

### 8.3. Null và primitive constructor arguments

Nếu một cột của query có thể NULL, đừng dùng primitive:

~~~java
public record PaymentSummary(long lastPaymentId) {}
~~~

khi SQL trả NULL cho người chưa thanh toán. Dùng Long:

~~~java
public record PaymentSummary(Long lastPaymentId) {}
~~~

Một constructor cần unbox null thành long có thể gây exception. Thiết kế DTO phải phản ánh khả năng NULL của **expression SQL cuối cùng**, không chỉ DDL nguồn.

## 9. Alias SQL là một phần của hợp đồng mapping

Trong @SqlResultSetMapping:

~~~java
@ColumnResult(name = "order_count", type = Long.class)
~~~

name là **tên cột/label được trả về trong ResultSet**, thường là alias của SELECT. Nếu SQL đổi:

~~~sql
COUNT(*) AS total_orders
~~~

nhưng mapping vẫn tìm order_count, provider có thể báo không tìm thấy label hoặc lỗi trích cột.

### 9.1. Luôn đặt alias cho expression

Nên:

~~~sql
SELECT
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM purchase_orders;
~~~

Không nên để mapping phụ thuộc tên tự sinh:

~~~sql
SELECT COUNT(*), SUM(total_amount)
FROM purchase_orders;
~~~

Tên result column cho biểu thức có thể khác theo driver/database. Alias rõ ràng là hợp đồng giữa SQL và @ColumnResult.

### 9.2. Tránh alias trùng nhau trong JOIN

~~~sql
SELECT o.id, c.id
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id;
~~~

Hai cột cùng có label id. Mapping dựa trên label id có thể mơ hồ. Nên:

~~~sql
SELECT
    o.id AS order_id,
    c.id AS customer_id
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id;
~~~

Với EntityResult/FieldResult, alias duy nhất càng quan trọng khi SQL trả nhiều entity cùng lúc.

### 9.3. Viết hoa/thường và quoted identifiers

PostgreSQL thường fold identifier không quoted sang chữ thường. Một alias:

~~~sql
SELECT COUNT(*) AS "orderCount"
FROM purchase_orders;
~~~

khác với alias không quoted theo quy tắc tên cột SQL. Nếu mapping dùng name="orderCount", kết quả có thể phụ thuộc cách đặt quote và JDBC metadata. Để giảm rủi ro, thường dùng alias lowercase/snake_case nhất quán như order_count, rồi ánh xạ qua constructor orderCount.

### 9.4. SELECT * có ưu và nhược điểm

Khi native SQL trả **một entity** với cấu trúc phù hợp, SELECT o.* có thể giúp lấy đủ các cột của entity. Nhưng:

- JOIN thêm bảng khác dễ tạo label trùng.
- DDL thay đổi khiến danh sách cột thay đổi ngoài dự kiến.
- Query đọc nhiều cột không cần thiết.
- Projection/constructor mapping nên chọn alias tường minh, không dùng SELECT *.

Một DTO report tốt thường dùng SELECT danh sách cột/aggregate rõ ràng và mapping alias ổn định.

## 10. @EntityResult: native SQL trả entity được quản lý

Nếu SQL thật sự trả dữ liệu của một entity, có thể ánh xạ bằng @EntityResult:

~~~java
@Entity
@Table(name = "purchase_orders")
@SqlResultSetMapping(
    name = "PurchaseOrderEntityMapping",
    entities = @EntityResult(
        entityClass = PurchaseOrder.class
    )
)
public class PurchaseOrder {
    @Id
    private Long id;
    // Tất cả persistent attributes như mapping ở đầu bài.
}
~~~

Native SQL:

~~~java
@SuppressWarnings("unchecked")
List<PurchaseOrder> orders = entityManager
    .createNativeQuery("""
        SELECT o.*
        FROM purchase_orders o
        WHERE o.tenant_id = :tenantId
          AND o.deleted_at IS NULL
        ORDER BY o.id DESC
        """, "PurchaseOrderEntityMapping")
    .setParameter("tenantId", authenticatedTenantId)
    .getResultList();
~~~

Do chỉ chọn cột của purchase_orders, các cột có tên vật lý đúng như entity mapping, Hibernate có thể dựng PurchaseOrder theo mapping. Với native SQL trả entity, phải cung cấp khóa chính và **các cột cần thiết để hydrate entity theo mapping**. Nhiều trường hợp cần đầy đủ các cột non-lazy, version/discriminator và cột FK liên quan; không nên giả định chọn mỗi id và status là đủ để có một entity hợp lệ.

### 10.1. EntityResult khác ConstructorResult

| Đặc điểm | @EntityResult | @ConstructorResult DTO |
|---|---|---|
| Đích | Class entity đã mapping | Class/record có constructor phù hợp |
| Identity map | Entity kết quả được ORM quản lý trong persistence context khi tải theo lifecycle query | DTO không thuộc identity map |
| Dirty checking | Managed entity có thể dirty-check | DTO bình thường không được dirty-check |
| Lazy association | Dựa trên mapping/fetch plan | Không tự có lazy association ORM |
| Yêu cầu @Id | Entity phải có định danh | DTO không cần @Id |
| Dữ liệu cần lấy | Các cột cần cho entity mapping | Chỉ các scalar mà constructor yêu cầu |
| Báo cáo aggregate | Không hợp lý nếu không phải entity thật | Phù hợp |
| Rủi ro partial row | Entity thiếu cột có thể lỗi hoặc state sai | Constructor thiếu/mismatch cột sẽ lỗi rõ |

Không dùng @EntityResult chỉ để “trông giống một DTO” nếu SQL không trả đủ entity data.

### 10.2. Entity trả về có thể là object đã managed

Nếu EntityManager đã chứa PurchaseOrder #101, native query trả entity cùng ID thường sử dụng quy tắc identity của persistence context. Kết quả có thể là instance đang managed, không phải object mới độc lập. Vì vậy sự thay đổi trực tiếp trên entity có thể được flush trong transaction, khác hoàn toàn với DTO.

Đối với màn hình chỉ xem số liệu, DTO thường giúp tránh đưa nhiều entity vào first-level cache.

## 11. @FieldResult: khi cột được alias khác tên vật lý

Giả sử query trả Customer nhưng alias được prefix để tránh trùng với Order:

~~~sql
SELECT
    c.id AS customer_id,
    c.full_name AS customer_name,
    c.email AS customer_email
FROM customers c
WHERE c.id = ?;
~~~

Entity Customer có các thuộc tính id, fullName, email. Có thể ánh xạ alias sang field:

~~~java
@Entity
@Table(name = "customers")
@SqlResultSetMapping(
    name = "CustomerAliasEntityMapping",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id",
                         column = "customer_id"),
            @FieldResult(name = "fullName",
                         column = "customer_name"),
            @FieldResult(name = "email",
                         column = "customer_email")
        }
    )
)
public class Customer {
    @Id
    private Long id;

    @Column(name = "full_name")
    private String fullName;

    private String email;
}
~~~

Ở đây:

- **@FieldResult.name:** tên persistent attribute Java của entity: id, fullName, email.
- **@FieldResult.column:** alias ResultSet: customer_id, customer_name, customer_email.

Không viết name="full_name" trừ khi full_name thực sự là tên persistent attribute (không phải chỉ là cột).

### 11.1. Giới hạn của FieldResult

Nếu entity có thêm version, FK association, discriminator, embedded attributes hoặc các cột bắt buộc khác, mapping phải bảo đảm SQL trả đủ dữ liệu Hibernate cần để dựng entity. Ví dụ chỉ có ba field ở trên phù hợp với Customer tối giản trong đoạn code, **không phải mẫu an toàn để cắt bớt 20 thuộc tính của một Customer production**.

Với entity có composite identifier hoặc association phức tạp, @FieldResult có quy tắc tên field/nested path riêng. Cần xem mapping JPA của entity và kiểm thử SQL trên provider mục tiêu; không thể bỏ một phần composite key rồi mong Hibernate nhận diện đúng instance.

### 11.2. Discriminator khi dùng inheritance

@EntityResult có thuộc tính discriminatorColumn cho kết quả ánh xạ hierarchy cần discriminator alias. Khi truy vấn native SQL trên entity kế thừa SINGLE_TABLE/JOINED/TABLE_PER_CLASS, phải cân nhắc strategy và các cột subclass để Hibernate xác định concrete entity type. Không giả định một truy vấn SELECT id, amount đủ cho mọi subclass.

## 12. Kết quả hỗn hợp: entity và scalar trong cùng một hàng

Yêu cầu: lấy từng đơn hàng cùng số OrderItem của đơn đó. Ứng dụng có thể muốn **PurchaseOrder entity managed** và thêm **itemCount scalar**.

Mapping:

~~~java
@SqlResultSetMapping(
    name = "OrderAndItemCountMapping",
    entities = @EntityResult(
        entityClass = PurchaseOrder.class
    ),
    columns = @ColumnResult(
        name = "item_count",
        type = Long.class
    )
)
~~~

SQL:

~~~sql
SELECT
    o.*,
    (
        SELECT COUNT(*)
        FROM order_items i
        WHERE i.order_id = o.id
    ) AS item_count
FROM purchase_orders o
WHERE o.tenant_id = ?
  AND o.deleted_at IS NULL
ORDER BY o.created_at DESC, o.id DESC;
~~~

Java:

~~~java
@SuppressWarnings("unchecked")
List<Object[]> rows = entityManager
    .createNativeQuery(sql, "OrderAndItemCountMapping")
    .setParameter(1, authenticatedTenantId)
    .getResultList();

for (Object[] row : rows) {
    PurchaseOrder order = (PurchaseOrder) row[0];
    Long count = (Long) row[1];

    // order: entity ORM
    // count: scalar bổ sung
}
~~~

Khi mapping kết hợp nhiều loại kết quả, mỗi hàng thường là Object[]; các phần được trả theo thứ tự khai báo metadata (entity results, constructor results, scalar results theo quy tắc JPA provider). **Thứ tự và kiểu phần tử phải được xác nhận trên integration test**, nhất là khi mapping có nhiều EntityResult/ConstructorResult.

Trong ví dụ dùng scalar subquery COUNT thay vì JOIN order_items + GROUP BY để không nhân bản hàng entity và không buộc phải chọn/group mọi cột của PurchaseOrder.

### 12.1. Nếu chỉ cần DTO thì đừng tải entity

Nếu UI chỉ cần order ID, status, item count, có thể khai báo một @ConstructorResult riêng:

~~~java
public record OrderListRow(
    Long orderId,
    String status,
    Long itemCount
) {}
~~~

SQL chọn đúng ba scalar; không cần SELECT o.* hoặc hydrate entity graph. Đặc biệt khi trang danh sách có hàng nghìn bản ghi, DTO giúp giảm memory và tránh lazy loading không chủ ý.

### 12.2. Mapping hỗn hợp không phải multi-object graph tự động

Nếu SQL trả cả Order và Customer, việc đặt hai EntityResult không tự bảo đảm mọi association/collection Java được đồng bộ đầy đủ như một fetch join HQL. Entity identity, FK mapping, alias, loại JOIN và rows trùng vẫn có thể ảnh hưởng. Chỉ dùng kết quả hỗn hợp nhiều entity khi thật sự cần, và test rõ quan hệ sau khi tải.

## 13. @NamedNativeQuery kết hợp resultSetMapping

Thay vì truyền SQL string trong từng method, có thể khai báo một named native query:

~~~java
@Entity
@Table(name = "purchase_orders")
@NamedNativeQuery(
    name = "PurchaseOrder.customerTotals",
    query = """
        SELECT
            o.customer_id AS customer_id,
            COUNT(*) AS order_count,
            COALESCE(SUM(o.total_amount), 0) AS total_amount
        FROM purchase_orders o
        WHERE o.tenant_id = :tenantId
          AND o.status = 'PAID'
          AND o.deleted_at IS NULL
        GROUP BY o.customer_id
        """,
    resultSetMapping = "CustomerOrderTotalsMapping"
)
@SqlResultSetMapping(
    name = "CustomerOrderTotalsMapping",
    classes = @ConstructorResult(
        targetClass = CustomerOrderTotals.class,
        columns = {
            @ColumnResult(name = "customer_id",
                          type = Long.class),
            @ColumnResult(name = "order_count",
                          type = Long.class),
            @ColumnResult(name = "total_amount",
                          type = BigDecimal.class)
        }
    )
)
public class PurchaseOrder {
    @Id
    private Long id;
}
~~~

Thực thi:

~~~java
@SuppressWarnings("unchecked")
List<CustomerOrderTotals> totals = entityManager
    .createNamedQuery("PurchaseOrder.customerTotals")
    .setParameter("tenantId", authenticatedTenantId)
    .getResultList();
~~~

Đây là cách tổ chức một native query tĩnh có tên cùng mapping DTO. Tên @NamedNativeQuery và @SqlResultSetMapping là hai tên riêng: một tên xác định SQL, tên còn lại xác định cách chuyển ResultSet.

### 13.1. Ưu/nhược điểm của named native query

Ưu điểm:

- Câu query và result mapping được khai báo tường minh.
- Dễ tìm nơi sử dụng theo tên.
- Giảm lặp lại SQL string trong service.
- Có thể hỗ trợ kiểm tra metadata lúc khởi động tùy provider.

Nhược điểm:

- Sửa alias, thứ tự cột hoặc DTO constructor phải đồng bộ nhiều nơi.
- Tính năng SQL phụ thuộc schema/dialect, khó portable hơn HQL.
- Mapping lớn khiến entity class chứa nhiều annotation metadata.
- Query động với nhiều tổ hợp SELECT rất khó mô hình bằng một named query cố định.

Đặt tên có quy ước và có integration test là quan trọng hơn việc chọn một vị trí annotation “đẹp”.

## 14. ConstructorResult không phải entity lifecycle

@ConstructorResult tạo một Java object bằng constructor. Nếu targetClass là DTO thường:

- Đối tượng không được EntityManager quản lý.
- EntityManager.contains(dto) không áp dụng vì dto không phải managed entity.
- Hibernate không dirty-check các field của DTO.
- DTO không có lazy-loaded collection do Hibernate cung cấp.
- Sửa giá trị DTO không tạo UPDATE khi flush.

Điều này rất phù hợp với báo cáo read-only, API response và dashboard.

### 14.1. Không dùng entity class làm DTO constructor target theo thói quen

Jakarta Persistence có quy tắc riêng khi @ConstructorResult target là một entity class: đối tượng được xây có thể ở trạng thái new/detached tùy khóa định danh được truyền, **không giống lời bảo đảm managed entity của @EntityResult**.

Nếu cần thực thể có identity map và dirty checking, dùng EntityResult/native entity query. Nếu chỉ cần dữ liệu hiển thị, dùng DTO riêng. Dùng cùng class entity cho hai mục đích dễ làm nhầm trạng thái persistence và dẫn tới lỗi update/merge.

### 14.2. DTO không phải cách cập nhật lại entity

~~~java
CustomerOrderTotals row = totals.get(0);
~~~

Nếu record immutable, muốn thay đổi nội dung phải tạo record mới. Kể cả DTO mutable, thay đổi DTO chỉ là thay đổi object Java. Muốn cập nhật database phải viết workflow update riêng qua entity managed, HQL/native DML hoặc repository; không trông đợi flush tự tìm một DTO đã sửa.

## 15. Enum: column type và Java type khác nhau

Giả sử entity có:

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

Trong native SQL:

~~~sql
SELECT o.status AS status
FROM purchase_orders o;
~~~

ResultSet scalar thường thấy VARCHAR/String, không mặc định thành OrderStatus chỉ vì một entity khác có @Enumerated. Nếu DTO constructor yêu cầu enum:

~~~java
public record OrderStatusRow(OrderStatus status, Long count) {}
~~~

thì việc khai báo:

~~~java
@ColumnResult(name = "status", type = OrderStatus.class)
~~~

không nên được xem là conversion portable từ VARCHAR sang enum cho mọi JPA provider/dialect. Với mapping constructor native, cách rõ ràng là DTO raw:

~~~java
public record OrderStatusRawRow(String status, Long count) {}
~~~

Sau đó chuyển đổi có kiểm soát:

~~~java
OrderStatus parsed;
try {
    parsed = OrderStatus.valueOf(rawRow.status());
} catch (IllegalArgumentException ex) {
    throw new IllegalStateException(
        "Status database không hợp lệ: " + rawRow.status(), ex);
}
~~~

Nếu ứng dụng lưu enum bằng ordinal hoặc PostgreSQL native enum, SQL type và conversion lại khác; cần mapping/test phù hợp.

### 15.1. Không bỏ qua trạng thái lạ

Nếu SQL trả "ARCHIVED" nhưng enum Java chưa có, đó là tín hiệu schema/application version chưa tương thích. Không biến giá trị lạ thành null hoặc DRAFT mặc định nếu business không quy định; có thể làm sai báo cáo hoặc an toàn nghiệp vụ.

## 16. Timestamp, Instant và timezone

Native query:

~~~sql
SELECT
    o.id AS order_id,
    o.created_at AS created_at
FROM purchase_orders o;
~~~

Mapping:

~~~java
@ColumnResult(name = "order_id", type = Long.class),
@ColumnResult(name = "created_at", type = Instant.class)
~~~

Kiểu Instant có thể được Hibernate hỗ trợ trong nhiều trường hợp, nhưng conversion từ JDBC TIMESTAMP/TIMESTAMPTZ sang Instant phụ thuộc dialect, version và cấu hình timezone. Không tự kết luận rằng cột SQL TIMESTAMP WITHOUT TIME ZONE có cùng semantics với Instant UTC.

### 16.1. Nếu provider trả Timestamp hoặc OffsetDateTime

Có thể chọn một DTO raw phù hợp, sau đó chuyển đổi rõ theo timezone đã định nghĩa:

~~~java
java.sql.Timestamp ts = /* đọc từ ResultSet theo API phù hợp */;
Instant instant = ts.toInstant();
~~~

Nhưng nếu cột trong database vốn là local timestamp không có timezone, chuyển sang Instant cần **xác định timezone nguồn**, không đơn giản gắn UTC tùy ý.

### 16.2. Dùng khoảng thời gian nửa mở

~~~sql
WHERE o.created_at >= :fromTime
  AND o.created_at < :toTime
~~~

Truy vấn khoảng [fromTime, toTime) thường dễ quản lý hơn việc tạo giá trị 23:59:59.999..., vốn phụ thuộc precision. Thời gian được truyền vào phải là kiểu được Hibernate/JDBC bind phù hợp; chỉ dùng input string từ client sau khi parse và validate timezone.

## 17. UUID, JSONB, ARRAY và các SQL type không có DTO mapping chuẩn

@ConstructorResult không phải JSON serializer. Nó gọi Java constructor với một tập giá trị scalar đã được provider chuyển đổi.

### 17.1. UUID

PostgreSQL hỗ trợ uuid type. JDBC có thể trả java.util.UUID; một số query expression/cast có thể trả String. Để API ổn định:

- Chọn SQL type/cast rõ ràng.
- Kiểm tra @ColumnResult(type=UUID.class) trên dialect.
- Nếu DTO cần String, cast UUID sang text trong PostgreSQL khi phù hợp.
- Không cast Object trực tiếp sang UUID chỉ vì cột mang tên request_id.

Ví dụ:

~~~sql
SELECT e.request_id::text AS request_id
FROM outbox_events e;
~~~

DTO có String requestId dễ nhận; nếu ứng dụng cần UUID, parse bằng UUID.fromString và xử lý dữ liệu không hợp lệ.

### 17.2. JSONB

Nếu SQL trả một cột jsonb, PostgreSQL JDBC có thể trả PGobject hoặc kiểu khác tùy đường thực thi. Khai báo:

~~~java
@ColumnResult(name = "payload", type = Map.class)
~~~

không bảo đảm Hibernate tự parse JSON thành Map cho constructor DTO.

Cách minh họa đơn giản:

~~~sql
SELECT e.id, e.payload::text AS payload_json
FROM outbox_events e;
~~~

DTO:

~~~java
public record OutboxPayloadRow(
    Long id,
    String payloadJson
) {}
~~~

Sau đó dùng Jackson/ObjectMapper hoặc thư viện JSON đã kiểm soát để parse theo schema. Nếu entity dùng @JdbcTypeCode(SqlTypes.JSON), mapping đó áp dụng theo cấu hình thuộc tính entity; không mặc định mọi scalar native SQL expression được chuyển cùng cách.

### 17.3. SQL ARRAY và custom types

Một cột PostgreSQL ARRAY có thể xuất hiện ở JDBC dưới dạng java.sql.Array hoặc driver-specific representation. Không mặc định:

~~~java
@ColumnResult(name = "tags", type = List.class)
~~~

sẽ biến nó thành List<String>. Cần chọn custom type/transformer thích hợp hoặc map ở tầng JDBC/Java sau khi đọc. SQL struct/composite, range, geometry, hstore và các custom types khác cũng cần xử lý theo dialect/provider.

### 17.4. Đừng dùng Object làm hợp đồng API

Một DTO như:

~~~java
public record AnalyticsRow(Object value1, Object value2) {}
~~~

có thể chạy trong thử nghiệm nhưng khiến code sử dụng khó biết kiểu thật. Ở ranh giới service/API, nên có read model với kiểu chính xác và xử lý conversion tường minh, đặc biệt với tiền, ID, thời gian và kiểu nullable.

## 18. Mapping kết quả của JOIN và nguy cơ duplicate rows

Giả sử muốn lấy đơn và OrderItem:

~~~sql
SELECT
    o.id AS order_id,
    i.id AS item_id
FROM purchase_orders o
JOIN order_items i ON i.order_id = o.id;
~~~

Một PurchaseOrder có ba OrderItem sẽ xuất hiện **ba hàng SQL**. @SqlResultSetMapping không tự tổng hợp ba hàng đó thành một DTO chứa List<OrderItem>:

~~~java
public record OrderWithItems(Long id, List<Long> itemIds) {}
~~~

ConstructorResult đọc **một hàng ResultSet** và gọi constructor từ các scalar của hàng đó. Nó không tự xây nested collection hay gom nhóm tất cả rows theo order ID.

### 18.1. Ba chiến lược khi cần parent và child

1. **DTO phẳng:** mỗi hàng là (orderId, itemId), sau đó group ở Java nếu tập dữ liệu đã được giới hạn.
2. **Hai query:** lấy danh sách Order ID/page trước, rồi query items của các Order đó và ghép DTO theo ID.
3. **SQL aggregation:** dùng json_agg/array_agg có alias và giải mã kết quả theo kiểu thích hợp; chấp nhận dependency PostgreSQL.

Chọn theo cardinality và nhu cầu UI. Nếu mỗi đơn có hàng chục nghìn items, DTO gom cả collection vào một trang danh sách là lựa chọn tốn bộ nhớ dù không có entity managed.

### 18.2. Pagination sau JOIN

Nếu query join items rồi LIMIT 20, database giới hạn **20 joined rows** chứ không phải 20 PurchaseOrder hoàn chỉnh. Điều này có thể cắt mất child của đơn cuối. Khi phân trang parent, hãy page Order ID trước rồi fetch child bằng query thứ hai; đừng dùng ConstructorResult như cách né row multiplication.

### 18.3. Count query phải đúng đơn vị đếm

~~~sql
SELECT COUNT(*)
FROM purchase_orders o
JOIN order_items i ON i.order_id = o.id;
~~~

đếm số hàng join, không phải số đơn. Nếu cần số đơn có ít nhất một item:

~~~sql
SELECT COUNT(*)
FROM purchase_orders o
WHERE EXISTS (
    SELECT 1
    FROM order_items i
    WHERE i.order_id = o.id
);
~~~

Nếu group theo customer và phân trang các **nhóm khách**, totalElements phải là số nhóm khách phù hợp, không phải COUNT(*) của purchase_orders. Có thể dùng COUNT(DISTINCT customer_id) hoặc một subquery group tương ứng.

## 19. Phân trang native SQL và mapping DTO

Ví dụ một báo cáo khách hàng có tổng tiền, phân trang:

~~~java
String sql = """
    SELECT
        o.customer_id AS customer_id,
        COUNT(*) AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS total_amount
    FROM purchase_orders o
    WHERE o.tenant_id = :tenantId
      AND o.status = 'PAID'
      AND o.deleted_at IS NULL
    GROUP BY o.customer_id
    ORDER BY total_amount DESC, customer_id ASC
    """;

@SuppressWarnings("unchecked")
List<CustomerOrderTotals> page = entityManager
    .createNativeQuery(sql, "CustomerOrderTotalsMapping")
    .setParameter("tenantId", authenticatedTenantId)
    .setFirstResult(pageIndex * pageSize)
    .setMaxResults(pageSize)
    .getResultList();
~~~

setFirstResult/setMaxResults được Hibernate chuyển thành pagination phù hợp native query/dialect trong những trường hợp hỗ trợ. Tuy nhiên **sắp xếp phải ổn định**; khi nhiều khách có total_amount bằng nhau, thêm customer_id để tránh thứ tự không xác định.

### 19.1. Chặn pageIndex và pageSize không hợp lệ

~~~java
if (pageIndex < 0 || pageSize < 1 || pageSize > 100
        || (long) pageIndex * pageSize > Integer.MAX_VALUE) {
    throw new IllegalArgumentException(
        "Trang hoặc kích thước trang không hợp lệ");
}
~~~

Tránh phép nhân int trước khi kiểm tra vì có thể overflow. Query với OFFSET rất sâu có thể chậm dù page size nhỏ; cân nhắc keyset/cursor pagination nếu phải duyệt dữ liệu rất lớn.

### 19.2. Count theo nhóm

Nếu báo cáo có một hàng cho mỗi customerId, số phần tử tổng cần đếm số customer có đơn PAID:

~~~sql
SELECT COUNT(*)
FROM (
    SELECT o.customer_id
    FROM purchase_orders o
    WHERE o.tenant_id = :tenantId
      AND o.status = 'PAID'
      AND o.deleted_at IS NULL
    GROUP BY o.customer_id
) grouped;
~~~

Không đếm COUNT(*) trực tiếp trên purchase_orders vì đó là số đơn. Nếu GROUP BY có HAVING hoặc filter phức tạp, count query cũng phải phản ánh cùng ngữ nghĩa group/having.

### 19.3. Content và count có thể khác nhau khi có ghi đồng thời

Ở isolation READ COMMITTED của PostgreSQL, hai statement SELECT trong một transaction có thể thấy snapshot khác nhau nếu dữ liệu được commit giữa hai lần đọc. DTO mapping không tạo snapshot isolation. Với dashboard thông thường chênh lệch nhỏ có thể chấp nhận; với báo cáo tài chính cần nhất quán, hãy định nghĩa isolation/snapshot hoặc precomputed read model phù hợp.

## 20. Parameter binding, tenant và bảo mật trong native SQL

Native SQL không được bảo vệ tự động chỉ vì câu query chạy qua Hibernate. Nguyên tắc:

- Bind mọi **giá trị** qua query parameter.
- Validate input và giới hạn số lượng records trả về.
- Không ghép thẳng chuỗi user input vào WHERE.
- Không cho client tự sửa tenantId để xem dữ liệu người khác.
- Dùng whitelist khi dynamic ORDER BY hoặc tên cột/bảng vì identifier không bind như value.

Sai:

~~~java
String sql = "SELECT * FROM purchase_orders WHERE status = '"
    + rawStatus + "'";
~~~

Đúng hơn:

~~~java
String sql = """
    SELECT o.*
    FROM purchase_orders o
    WHERE o.tenant_id = :tenantId
      AND o.status = :status
      AND o.deleted_at IS NULL
    """;

Query query = entityManager.createNativeQuery(
    sql, "PurchaseOrderEntityMapping");
query.setParameter("tenantId", authenticatedTenantId);
query.setParameter("status", validatedStatus);
~~~

Trong ví dụ, validatedStatus là giá trị database phù hợp (chẳng hạn "PAID" nếu schema dùng VARCHAR và enum string mapping). Hãy lấy authenticatedTenantId từ ngữ cảnh bảo mật tin cậy, không nhận trực tiếp từ request như một quyền tự khai báo.

### 20.1. Dynamic ORDER BY

Không thể bind :columnName để thay một identifier SQL. Có thể:

~~~java
String orderBy = switch (sortKey) {
    case "amountHigh" -> "total_amount DESC, customer_id ASC";
    case "amountLow" -> "total_amount ASC, customer_id ASC";
    case "customerId" -> "customer_id ASC";
    default -> throw new IllegalArgumentException(
        "Sort không hợp lệ");
};
~~~

Sau đó ghép **chỉ** đoạn SQL được tạo từ whitelist cố định, không ghép raw user input.

### 20.2. SQL ResultSet mapping không bảo vệ quyền truy cập

Một DTO chỉ trả customerId, totalAmount vẫn có thể làm lộ doanh thu khách hàng nếu WHERE quên tenant/authorization. @SqlResultSetMapping chỉ biến dữ liệu đã đọc thành object, không phải cơ chế lọc row-level security. Mọi native query phải tuân thủ tenant policy và phân quyền giống HQL/Criteria.

## 21. Native bulk DML và persistence context

Mục tiêu của @SqlResultSetMapping chủ yếu là ánh xạ **kết quả SELECT** hoặc result set trả về trong bối cảnh được provider hỗ trợ. Không nhầm nó với cơ chế đồng bộ entity sau native UPDATE/DELETE.

Ví dụ:

~~~java
entityManager.createNativeQuery("""
    UPDATE purchase_orders
    SET status = 'CANCELLED'
    WHERE id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();
~~~

Nếu PurchaseOrder cùng ID đang managed trong EntityManager, object Java có thể còn status cũ sau native DML. Native bulk update không đi qua dirty checking, @PreUpdate callback và version handling thông thường của từng managed entity.

Một pattern có kiểm soát:

~~~java
entityManager.flush();
entityManager.createNativeQuery("""
    UPDATE purchase_orders
    SET status = :status
    WHERE id = :id
    """)
    .setParameter("status", "CANCELLED")
    .setParameter("id", id)
    .executeUpdate();
entityManager.clear();
~~~

flush đồng bộ thay đổi pending trước DML; clear detach **toàn bộ** entities managed trong persistence context. Đừng gọi clear máy móc khi service còn entity khác cần chỉnh sửa. Có thể chọn refresh hoặc transaction ranh giới riêng theo use case. Không bắt lỗi SQL khiến transaction thất bại rồi tiếp tục làm việc trên EntityManager như chưa xảy ra gì.

### 21.1. @SqlResultSetMapping không biến native UPDATE thành entity update

Một câu SQL có RETURNING trên PostgreSQL có thể trả rows, nhưng cách gọi API/ánh xạ response của DML RETURNING phụ thuộc provider/driver/version. Không mặc định mọi native UPDATE ... RETURNING đều hoạt động như một SELECT + ConstructorResult trên mọi JPA implementation. Nếu dự án cần RETURNING, phải kiểm thử rõ Hibernate version và API thích hợp, hoặc dùng JDBC chuyên dụng.

### 21.2. Automatic flush và query synchronization

Hibernate/JPA có quy tắc flush trước query tùy FlushMode, bootstrap API và query spaces. Native SQL có thể khó phân tích để tự nhận biết bảng liên quan; Hibernate có API provider-specific cho việc khai báo synchronized query spaces trong các trường hợp cần thiết. Khi trộn native SQL với entity changes pending:

- Xác định transaction/FlushMode.
- Flush đúng thời điểm nếu query phải thấy dữ liệu chưa được ghi từ persistence context.
- Không tin rằng native query luôn tự đồng bộ cache/lifecycle cho mọi SQL phức tạp.
- Với query caching hoặc second-level cache, test invalidation/synchronization theo Hibernate version.

## 22. Mapping tĩnh và kết quả động: giới hạn thiết kế

Một API báo cáo có thể cho phép người dùng chọn:

~~~text
includeRevenue = true/false
includeAverage = true/false
groupBy = CUSTOMER / MONTH / STATUS
~~~

Nếu mỗi tổ hợp tạo ra danh sách SELECT và alias khác nhau, một @ConstructorResult cố định rất khó bao phủ mọi hình dạng row.

Các chiến lược:

1. **Cố định schema DTO:** luôn trả cùng các alias, cột không dùng thì trả NULL/0 theo contract.
2. **Nhiều DTO/mapping rõ ràng:** mỗi loại báo cáo có result shape cố định.
3. **Tuple/Object[]/map có validator:** khi người dùng thật sự tự chọn nhiều cột động.
4. **Hibernate TupleTransformer hoặc JDBC RowMapper:** provider/framework-specific, linh hoạt nhưng cần quản lý alias, null và conversion thủ công.
5. **Read model chuyên dụng:** với dashboard lớn, pre-aggregate dữ liệu hoặc dùng view/materialized view có schema ổn định.

@SqlResultSetMapping phát huy tác dụng tốt nhất khi schema kết quả được coi là một **hợp đồng ổn định** giữa SQL và Java.

### 22.1. Một mapping không thể tự tạo nested DTO tùy ý

Ví dụ:

~~~java
public record CustomerWithOrders(
    Long customerId,
    List<OrderSummary> orders
) {}
~~~

Một @ConstructorResult trên SELECT JOIN thông thường không tự gom nhiều rows thành List<OrderSummary>. Nếu mỗi row có cột customer_id/order_id/amount, provider chỉ có thông tin của từng row khi gọi constructor. Cần tự group, query riêng hoặc JSON aggregation/parsing theo thiết kế.

### 22.2. Alias không phải type system hoàn chỉnh

Có alias "total_amount" không có nghĩa SQL expression luôn là numeric. SQL có thể vô tình đổi thành:

~~~sql
TO_CHAR(SUM(o.total_amount), 'FM999999.00') AS total_amount
~~~

Kết quả mới là text, dù alias vẫn total_amount. Mapping BigDecimal có thể lỗi hoặc convert ngoài dự kiến. Vì vậy cần kiểm thử cả **alias lẫn SQL type** sau khi sửa expression.

## 23. Spring Data JPA native queries và projection

Spring Data JPA hỗ trợ các repository method với native SQL:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            SELECT o.id, o.total_amount
            FROM purchase_orders o
            WHERE o.tenant_id = :tenantId
            ORDER BY o.id DESC
            """,
        nativeQuery = true
    )
    List<Object[]> findAmounts(
        @Param("tenantId") Long tenantId
    );
}
~~~

Spring Data có nhiều cơ chế projection và có thể hỗ trợ interface-based projection dựa trên alias, DTO class/record projection hoặc annotation native mapping chuyên biệt ở những phiên bản nhất định. Tuy nhiên, **không giả định một class DTO bất kỳ sẽ được tự động ánh xạ constructor từ native SQL giống HQL constructor expression**.

Nếu muốn dùng @SqlResultSetMapping theo cách JPA rõ ràng và ít phụ thuộc Spring Data version, hãy thực thi bằng EntityManager.createNativeQuery(sql, mappingName) trong custom repository/service.

### 23.1. HQL constructor expression khác @ConstructorResult

HQL:

~~~hql
select new com.example.shop.reporting.CustomerOrderTotals(
    o.customer.id,
    count(o),
    sum(o.totalAmount)
)
from PurchaseOrder o
group by o.customer.id
~~~

Ở đây Hibernate biết kiểu entity attribute từ mapping HQL và thực hiện constructor expression.

Native SQL:

~~~sql
SELECT customer_id, COUNT(*), SUM(total_amount)
FROM purchase_orders
GROUP BY customer_id;
~~~

SQL này không có thông tin về CustomerOrderTotals. @SqlResultSetMapping/@ConstructorResult chính là phần metadata nói cách tạo DTO từ các cột ResultSet native.

### 23.2. Query result mapping là vấn đề độc lập với cách repository được gọi

Dù gọi qua EntityManager hay Spring Data, những nguyên tắc sau vẫn áp dụng:

- Alias phải khớp.
- Constructor argument order/type phải đúng.
- SQL phải trả đủ cột entity nếu dùng EntityResult.
- COUNT, SUM, null và JSON cần conversion phù hợp.
- Tenant và authorization phải nằm trong SQL/DB policy.
- Paging/count phải đếm đúng đơn vị kết quả.

## 24. Khi nào không cần @SqlResultSetMapping?

Không phải mọi native SQL đều cần annotation này.

### 24.1. Một scalar đơn giản

~~~java
Number count = (Number) entityManager
    .createNativeQuery("""
        SELECT COUNT(*)
        FROM purchase_orders
        WHERE tenant_id = :tenantId
        """)
    .setParameter("tenantId", authenticatedTenantId)
    .getSingleResult();

long countValue = count.longValue();
~~~

Với một scalar và kiểu số nằm trong miền Long, cách này có thể đủ. Nếu yêu cầu chính xác và database có kiểu đặc biệt, kiểm tra conversion thay vì longValue mù quáng.

### 24.2. Truy vấn entity đầy đủ

~~~java
@SuppressWarnings("unchecked")
List<PurchaseOrder> orders = entityManager
    .createNativeQuery("""
        SELECT o.*
        FROM purchase_orders o
        WHERE o.id = :id
        """, PurchaseOrder.class)
    .setParameter("id", id)
    .getResultList();
~~~

Nếu SQL trả đúng shape entity và không cần alias custom/multiple results, overload entity class thường đơn giản hơn việc khai báo @EntityResult riêng.

### 24.3. Dynamic report đặc thù

Nếu danh sách cột không cố định hoặc cần streaming triệu rows với transformation phức tạp, có thể cân nhắc JDBC/JdbcTemplate, Hibernate transformer hoặc công cụ reporting chuyên biệt. Mỗi cơ chế có trade-off, không có yêu cầu mọi native SQL trong ứng dụng phải đi qua @SqlResultSetMapping.

### 24.4. Khi HQL/Criteria làm được tốt hơn

Nếu chỉ cần entity filtering, joins theo association và DTO đơn giản, HQL/Criteria API thường dễ bảo trì vì dùng entity property thay cho table/column. Chỉ dùng native SQL khi có lợi thế rõ: chức năng database, query shape, hiệu năng đã đo hoặc tích hợp SQL sẵn có.

## 25. Kiểm thử @SqlResultSetMapping trên database thật

Lỗi mapping thường chỉ lộ lúc query được thực thi. Một ứng dụng khởi động thành công chưa chứng minh mọi alias, type và constructor đều đúng.

### 25.1. Bộ dữ liệu kiểm thử gợi ý

Tạo dữ liệu:

| Khách | Đơn PAID | Amount | Ghi chú |
|---:|---:|---:|---|
| 10 | #1 | 100.00 | Numeric scale 2 |
| 10 | #2 | 200.50 | Hai đơn để test COUNT |
| 20 | #3 | 0.00 | Test zero |
| 30 | Không có | — | Test GROUP BY không trả row |
| 10 | #4 CANCELLED | 999.00 | Không được cộng vào tổng PAID |
| 40 | Đơn tenant khác | 500.00 | Không rò rỉ cross-tenant |

Kết quả kỳ vọng khi report chỉ lấy PAID trong tenant hiện tại:

- Customer 10: orderCount=2, totalAmount=300.50.
- Customer 20: orderCount=1, totalAmount=0.00.
- Customer 30: không có row nếu query bắt đầu từ purchase_orders và GROUP BY các đơn.
- Customer 40: không có row.

Đừng chỉ assert DTO list không rỗng. Cần kiểm tra đúng từng field, kiểu và giá trị, nhất là hai field Long dễ bị đảo vị trí.

### 25.2. Skeleton integration test

~~~java
@SpringBootTest
class CustomerOrderTotalsMappingTest {
    @Autowired CustomerTotalsRepository reporting;

    @Test
    void mapsNativeAggregateIntoDto() {
        // Arrange:
        // - Tạo Customer 10 với PAID 100.00, PAID 200.50.
        // - Tạo CANCELLED 999.00 để chứng minh filter.
        // - Tạo Customer 20 với PAID 0.00.
        // - Tạo dữ liệu tenant khác.
        // - Flush/commit fixture rồi mở context mới.

        List<CustomerOrderTotals> result =
            reporting.findTotalsForCurrentTenant();

        // Assert:
        // - Đúng customerId, orderCount, totalAmount.
        // - Giá trị BigDecimal giữ precision.
        // - Không có đơn CANCELLED hoặc tenant khác.
        // - Type đúng constructor, không ClassCastException.
    }
}
~~~

Đây là skeleton, cần fixture, repository, annotation và method thực tế. Trong test nên dùng PostgreSQL Testcontainers hoặc database thật tương ứng production; H2 có thể có kiểu aggregate, UUID/JSON, timestamp và alias behavior khác PostgreSQL.

### 25.3. Test scalar type

Những test hữu ích:

1. COUNT(*) khi có 0, 1, nhiều rows và giá trị count vượt miền Integer nếu có thể mô phỏng.
2. SUM(numeric) của nhiều hàng chứa số lẻ thập phân.
3. SUM trên tập rỗng trả NULL hay 0 theo SQL.
4. AVG với nhiều chữ số thập phân.
5. ColumnResult(type=Long.class) và BigDecimal.class khớp constructor.
6. Timestamp/Instant với timezone khác UTC.
7. UUID raw và UUID cast sang text.
8. JSONB raw PGobject hoặc JSON text.
9. Nullable field với wrapper type và primitive constructor.

### 25.4. Test alias và thứ tự constructor

Chủ động tạo dữ liệu mà customerId khác orderCount; ví dụ id=10, count=2. Nếu hai giá trị tình cờ cùng là 1, đảo cột trong constructor mapping vẫn có thể vượt qua một test quá đơn giản.

Thử đổi alias order_count thành total_orders trong SQL trên một branch test để quan sát lỗi provider. Mục tiêu là xác nhận alias là một phần của hợp đồng, không phải chỉ kiểm tra code compile.

### 25.5. Test entity mapping

Khi dùng EntityResult:

- Query có ID và tất cả columns cần cho entity không?
- Entity có cùng identity với entity đã managed trong cùng context không?
- FK/lazy association hoạt động đúng khi truy cập không?
- Nếu đã có entity managed với state cũ, native query có trả stale state không?
- Có duplicate rows từ JOIN làm sai page hoặc số entity kỳ vọng không?

Không dùng test DTO ConstructorResult để suy ra hành vi EntityResult; chúng thuộc hai loại lifecycle khác nhau.

## 26. Quan sát SQL, bind values và execution plan

Trong development/test, có thể bật:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Logger bind parameter có thể ghi email, ID cá nhân hoặc dữ liệu thanh toán; không bật TRACE ở production mặc định. Dùng logging đủ để quan sát SQL shape/alias và giới hạn dữ liệu nhạy cảm trong log.

### 26.1. EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.customer_id AS customer_id,
    COUNT(*) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_amount
FROM purchase_orders o
WHERE o.tenant_id = 7
  AND o.status = 'PAID'
  AND o.deleted_at IS NULL
GROUP BY o.customer_id
ORDER BY total_amount DESC;
~~~

Hãy xem:

- Actual rows và estimated rows.
- Seq Scan/Index Scan, số lượng rows bị filter.
- HashAggregate hay GroupAggregate.
- Sort, memory và spill ra disk.
- Buffers hit/read và execution time.

Native SQL không tự nhanh hơn HQL chỉ vì được viết bằng tay. Ưu điểm của native SQL là quyền kiểm soát cú pháp/plan và các tính năng DB-specific; chất lượng vẫn phụ thuộc index, cardinality và cách filter.

### 26.2. Index ứng viên

Với báo cáo tenant + status + customer:

~~~sql
CREATE INDEX idx_orders_tenant_status_customer
ON purchase_orders(tenant_id, status, customer_id);
~~~

Index có thể giúp filter và group, nhưng không phải bảo đảm optimizer luôn dùng. Nếu báo cáo cũng lọc theo created_at hoặc chỉ đọc dữ liệu active, có thể cần thiết kế index khác/partial index. Mọi index tăng chi phí ghi và storage; chọn dựa trên workload thực tế.

### 26.3. Mapping đúng không đồng nghĩa query nhanh

@SqlResultSetMapping chỉ thay đổi cách Hibernate dựng kết quả Java. Nếu database phải đọc 10 triệu rows để SUM, việc dùng DTO không làm phép tổng hợp ở database tự rẻ hơn. Nó có thể giảm số entity hydrate và data transfer, nhưng chi phí scan/sort/aggregate vẫn phải được tối ưu riêng.

## 27. Bảng xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Unknown SqlResultSetMapping | Tên mapping sai hoặc metadata không được đăng ký | Kiểm tra annotation trên managed entity và persistence unit |
| Không tìm thấy column alias | SQL alias khác @ColumnResult.name | Đặt alias tường minh, đồng bộ SQL/mapping |
| Constructor not found | Thứ tự/kiểu @ColumnResult không khớp constructor | Kiểm tra record canonical constructor và type |
| DTO chạy nhưng customerId/orderCount bị đảo | Hai tham số cùng kiểu Long bị khai báo sai thứ tự | Test giá trị cụ thể khác nhau |
| ClassCastException BigInteger to Long | Kiểu JDBC khác kiểu code cast | @ColumnResult(type), conversion chính xác, integration test |
| SUM trả NULL gây NPE | Tập rỗng hoặc cột nullable, constructor primitive | Dùng wrapper và/hoặc COALESCE có chủ đích |
| BigDecimal thành Double mất precision | DTO/mapping chọn kiểu float | Dùng numeric/BigDecimal cho tiền |
| Enum constructor không nhận String | Scalar native không tự áp @Enumerated | DTO String và convert có kiểm soát |
| Instant/timezone sai | SQL timestamp/dialect/zone không thống nhất | Xác định timezone và kiểm tra driver |
| JSONB không thành Map | ColumnResult không phải JSON parser | Cast JSONB sang text rồi parse hoặc custom type |
| UUID cast sai | JDBC/SQL trả UUID hoặc text khác dự kiến | Khai báo/cast SQL và test kiểu |
| EntityResult lỗi column not found | SQL thiếu cột/alias entity cần | Trả đủ cột; dùng FieldResult khi alias khác |
| Hai entity cùng alias id | JOIN trả label trùng | Prefix alias và mapping tường minh |
| EntityResult trả state cũ | Persistence context đã có entity cùng ID | Flush/refresh/clear theo transaction semantics |
| DTO sửa mà DB không update | ConstructorResult không managed | Viết workflow cập nhật entity riêng |
| Không thể ánh xạ List child trong constructor | Mỗi row chỉ chứa scalar của một record | Group nhiều rows hoặc query riêng |
| Page report total sai | Count đơn thay vì count group, hoặc JOIN nhân hàng | Count theo đơn vị kết quả, group/EXISTS đúng |
| Query trả dữ liệu tenant khác | SQL thiếu tenant/security predicate | Bind tenant từ auth context, kiểm thử cross-tenant |
| Native SQL chạy trên PostgreSQL nhưng lỗi H2 | SQL type/dialect/cast không tương thích | Test PostgreSQL bằng Testcontainers |
| Native DML rồi entity managed vẫn cũ | SQL không đồng bộ identity map | Flush trước, clear/refresh đúng scope |
| SQL thay tên expression mà DTO vỡ | Hợp đồng alias/type bị thay đổi | Version hóa query/mapping và integration test |

## 28. Bài thực hành tổng hợp

### Bài A — Làm quen với native scalar result

1. Tạo purchase_orders và customers trên PostgreSQL.
2. Viết native SQL COUNT và SUM không có mapping.
3. In ra các Java class thực tế của row elements trong môi trường test.
4. Thử cast count trực tiếp sang Long, quan sát tính phụ thuộc JDBC/provider.
5. Dùng Number/conversion chính xác hoặc @ColumnResult(type).

### Bài B — Constructor DTO

1. Tạo CustomerOrderTotals record gồm Long, Long, BigDecimal.
2. Khai báo @SqlResultSetMapping với @ConstructorResult.
3. Dùng SQL GROUP BY customer_id, alias đủ ba cột.
4. Gọi createNativeQuery(sql, "CustomerOrderTotalsMapping").
5. Assert kiểu và giá trị, không chỉ số rows.
6. Đảo thử thứ tự hai @ColumnResult kiểu Long trong test để phát hiện lỗi nghiệp vụ.

### Bài C — EntityResult và FieldResult

1. Viết query SELECT o.* để ánh xạ PurchaseOrder entity.
2. Truy vấn entity cùng ID hai lần trong một persistence context, quan sát identity.
3. Tạo SQL SELECT Customer với alias customer_id, customer_name và customer_email.
4. Khai báo @FieldResult(name=JavaAttribute,column=SQLAlias).
5. Thử bỏ một cột cần thiết và quan sát lỗi trích entity.

### Bài D — Kết quả hỗn hợp

1. Khai báo OrderAndItemCountMapping có EntityResult và ColumnResult.
2. Query PurchaseOrder cùng COUNT(OrderItem) bằng scalar subquery.
3. Đọc mỗi Object[] và xác định phần entity/phần scalar.
4. So sánh memory với phương án chỉ trả DTO (orderId, itemCount).
5. Tránh JOIN to-many làm nhân bản parent.

### Bài E — NamedNativeQuery và bảo mật

1. Chuyển SQL báo cáo vào @NamedNativeQuery.
2. Liên kết resultSetMapping theo tên.
3. Bind tenantId từ auth context và status hợp lệ.
4. Thử input status bất thường và dynamic ORDER BY, dùng whitelist.
5. Viết test bảo đảm tenant khác không xuất hiện.

### Bài F — Các kiểu khó

1. Thêm cột enum/string status vào DTO.
2. Thêm created_at vào DTO dưới dạng Instant hoặc kiểu có conversion phù hợp.
3. Test SUM trên tập rỗng và COALESCE.
4. Tạo cột uuid và jsonb, thử mapping scalar thực tế trên PostgreSQL.
5. Chọn cast JSONB sang text rồi parse, so sánh với entity JSON mapping.

### Bài G — Phân trang và SQL plan

1. Phân trang report theo tổng tiền DESC, customer ID làm tie-breaker.
2. Viết count query đúng số nhóm customer.
3. Chạy EXPLAIN ANALYZE với và không có index ứng viên.
4. Tạo một customer có rất nhiều OrderItem, bảo đảm không join gây nhân rows.
5. So sánh hiệu năng native DTO với HQL projection cho cùng use case trước khi kết luận.

## 29. Checklist trước khi đưa mapping vào production

1. Query trả **entity hay DTO**? Không dùng EntityResult cho aggregate row.
2. Mọi SQL expression đều có **alias ổn định** chưa?
3. @ColumnResult.name có khớp label ResultSet, kể cả quote/case không?
4. **Thứ tự @ConstructorResult.columns** khớp constructor chính xác chưa?
5. Các type Long, BigDecimal, Instant, UUID và JSON có được kiểm thử với JDBC driver mục tiêu không?
6. Giá trị NULL có thể đi vào primitive constructor argument không?
7. Nếu dùng EntityResult, đã trả đủ PK/FK/version/discriminator/required columns chưa?
8. Query JOIN có tạo alias trùng hoặc duplicate parent rows không?
9. Query có tenant/security/soft delete predicates bắt buộc chưa?
10. Các giá trị được bind qua parameter, còn sort identifier dùng whitelist chưa?
11. Pagination/count đếm đúng đơn vị báo cáo chưa?
12. Có trộn native DML với managed entities trong cùng persistence context không?
13. Có cần NamedNativeQuery cố định hay query builder động?
14. Có integration test trên PostgreSQL/dialect thực tế không?
15. Đã kiểm tra execution plan, dữ liệu truyền và chi phí tạo result objects chưa?

## 30. Tóm tắt các lựa chọn và nguyên tắc ghi nhớ

Khi dùng native SQL trong Hibernate ORM, hãy nhớ ba lớp khác nhau:

~~~mermaid
flowchart LR
    A[Native SQL: bảng, cột, expression] --> B[JDBC ResultSet: alias và SQL type]
    B --> C{@SqlResultSetMapping}
    C --> D[@EntityResult: managed entity]
    C --> E[@ConstructorResult: DTO]
    C --> F[@ColumnResult: scalar]
    C --> G[Mixed mapping: Object[]]
~~~

- **@SqlResultSetMapping** định nghĩa một ánh xạ có tên để giải mã ResultSet native SQL.
- **@ColumnResult** đọc cột scalar theo alias và kiểu mong muốn, không phải bộ chuyển đổi mọi SQL type.
- **@ConstructorResult** gọi constructor DTO theo thứ tự cột đã khai báo; tên field DTO không tự được so khớp với alias.
- **@EntityResult** ánh xạ hàng thành entity được ORM quản lý và cần đủ dữ liệu của mapping.
- **@FieldResult** liên kết persistent attribute name của entity với alias SQL khi tên trong ResultSet khác tên cột thường dùng.
- **Một hàng ResultSet thường tạo một DTO constructor result**; mapping không tự gom nhiều child rows thành List.
- **Native scalar types phụ thuộc JDBC/dialect**: COUNT, SUM, NULL, timestamp, enum, JSON, UUID và ARRAY đều cần hợp đồng rõ.
- **DTO không managed**; sửa DTO không phát sinh UPDATE qua dirty checking.
- **SQL, alias, type và constructor là một hợp đồng**: đổi một phần phải kiểm tra các phần còn lại.
- **Native SQL không bỏ qua trách nhiệm bảo mật hoặc hiệu năng**: tenant, parameter binding, paging/count và execution plan vẫn cần được thiết kế, kiểm thử.

Điểm cốt lõi là phân biệt **giá trị mà database trả về** với **đối tượng Java mà ứng dụng muốn nhận**. Native SQL quyết định các cột, alias và kiểu JDBC; @SqlResultSetMapping chỉ rõ cách Hibernate chuyển từng hàng đó thành entity, DTO hoặc scalar. Khi coi alias, thứ tự constructor và kiểu dữ liệu là một hợp đồng được kiểm thử, các báo cáo native SQL sẽ rõ ràng, an toàn và dễ duy trì hơn nhiều so với việc cast Object[] theo phỏng đoán.
