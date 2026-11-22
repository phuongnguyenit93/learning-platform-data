# Kiểm chứng SQL được sinh từ truy vấn Criteria trong JPA

**Criteria API** của Jakarta Persistence (JPA) cho phép xây dựng truy vấn bằng các đối tượng Java có kiểu như `CriteriaBuilder`, `CriteriaQuery`, `Root`, `Join` và `Predicate`. Tuy nhiên, chương trình **không gửi cây Criteria trực tiếp cho cơ sở dữ liệu**: JPA provider sẽ diễn giải cây truy vấn thành SQL phù hợp với mapping entity, dialect của database, fetch plan, phân trang và trạng thái persistence context.

Do đó, khi một truy vấn Criteria trả sai kết quả hoặc chạy chậm, chỉ đọc code Criteria là chưa đủ. Cần **kiểm chứng SQL thực tế được sinh và thực thi**, các giá trị tham số được bind, số lần truy cập database và kế hoạch thực thi của database.

Ví dụ, code:

~~~java
query.where(
    cb.equal(root.get("status"), OrderStatus.CONFIRMED)
);
~~~

có thể tạo ý tưởng SQL:

~~~sql
SELECT ...
FROM purchase_orders o
WHERE o.status = ?;
~~~

Nhưng câu SQL cuối cùng có thể thêm JOIN, ORDER BY, LIMIT/OFFSET, cột discriminator, điều kiện filter, cách biểu diễn enum và các truy vấn bổ sung tùy mapping/provider. Không nên coi bản dịch SQL viết tay là bằng chứng những gì đã thật sự chạy.

Bài học này thuộc chủ đề **Data Persistence Relational Access ORM JPA**, chương **Criteria API**, tập trung vào một quy trình có thể thực hiện được:

1. Xây dựng Criteria có mục tiêu và dữ liệu đầu vào rõ ràng.
2. Quan sát **SQL và JDBC bind parameters** ở đúng thời điểm thực thi.
3. Đối chiếu **ý nghĩa truy vấn, JOIN, WHERE, ORDER BY, pagination** với yêu cầu nghiệp vụ.
4. Phát hiện **SQL dư thừa, N+1, flush trước query, duplicate rows** và hành vi provider/dialect.
5. Kiểm tra với **database thực**, dùng `EXPLAIN` và integration tests khi cần.
6. Xác nhận những kết luận nào **portable theo JPA**, những kết luận nào chỉ đúng với **Hibernate, EclipseLink hoặc một phiên bản database**.

Mục tiêu không phải ép mọi provider sinh SQL giống hệt nhau. Mục tiêu là biết **đoạn Criteria đang tạo ra hành vi database nào** và hành vi đó có đúng, an toàn, hiệu quả hay không.

---

## 1. Đường đi từ Criteria đến SQL

Sơ đồ tổng quát:

~~~text
Ứng dụng Java
    |
    | CriteriaBuilder, CriteriaQuery, Root, Join, Predicate
    v
Cây truy vấn Criteria (mô hình JPA)
    |
    | EntityManager.createQuery(criteria)
    v
JPA provider / query engine
    |
    +-- Metadata @Entity, @Table, @Column, @ManyToOne...
    +-- Dialect PostgreSQL / MySQL / Oracle / ...
    +-- Mapping enum, ID, converter, inheritance, filters
    +-- Fetch plan và query hints
    +-- Pagination / locking / flush mode
    |
    v
SQL + JDBC PreparedStatement
    |
    +-- SQL có placeholder ?, $1... tùy tầng hiển thị
    +-- Giá trị/kiểu tham số được bind riêng
    |
    v
Database
    |
    +-- Parse / optimize / execute
    +-- Index scan, seq scan, join, sort, limit...
    |
    v
ResultSet
    |
    v
Entity, DTO, scalar hoặc Tuple
~~~

Có **ba tầng** cần kiểm tra riêng:

| Tầng | Điều cần xác nhận | Công cụ |
| --- | --- | --- |
| Criteria/JPA | Cây điều kiện đúng, chọn đúng entity/attribute, kết quả đúng kiểu | Đọc biểu thức Criteria, integration test kết quả |
| Provider/JDBC | SQL nào được phát, bind parameter ra sao, bao nhiêu statement | Logging Hibernate/EclipseLink, JDBC proxy, `StatementInspector` |
| Database | Execution plan, số hàng xử lý, index và thời gian thực tế | SQL logs, `EXPLAIN`, `EXPLAIN ANALYZE`, monitoring DB |

**SQL log và execution plan trả lời hai câu hỏi khác nhau.** Log cho thấy câu SQL nào được provider gửi; plan cho thấy database quyết định thực thi câu đó như thế nào.

### 1.1. Truy vấn được tạo không có nghĩa SQL đã chạy

Ba thao tác:

~~~java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

// Xây dựng Root, Predicate, Order...
TypedQuery<PurchaseOrder> q = em.createQuery(cq);

List<PurchaseOrder> rows = q.getResultList();
~~~

có những mốc khác nhau:

- `cb.createQuery(...)` tạo cấu trúc Criteria.
- `em.createQuery(cq)` tạo query object; provider có thể xác thực hoặc chuẩn bị kế hoạch truy vấn.
- `q.getResultList()` thường là nơi truy vấn SELECT được thực thi.
- Ngoài ra, `getSingleResult()` hoặc `executeUpdate()` cũng là điểm thực thi tương ứng với loại query.
- Provider có thể phát SQL **trước SELECT** nếu cần flush các thay đổi pending trong transaction.

Đừng bật SQL logging rồi kết luận Criteria “không tạo SQL” chỉ vì chưa gọi phương thức thực thi.

### 1.2. Không có API JPA chuẩn để lấy toàn bộ SQL đã render

`CriteriaQuery` là cấu trúc logic; JPA **không định nghĩa** một lời gọi portable như:

~~~java
String sql = criteriaQuery.toSql(); // Không tồn tại trong JPA chuẩn.
~~~

`criteriaQuery.toString()` không phải hợp đồng trả SQL thực thi. Một số provider có API nội bộ hoặc cơ chế unwrap/debug để xem query plan, nhưng tên lớp, định dạng và hành vi có thể thay đổi theo phiên bản.

Nếu muốn biết SQL thực chạy trong môi trường cụ thể, nên **quan sát đường JDBC/SQL logging** thay vì dựa vào `toString()`.

## 2. Mô hình ví dụ: khách hàng và đơn hàng

Để có tình huống cụ thể, giả sử ứng dụng muốn tìm các đơn **đã xác nhận**, tạo sau một thời điểm, thuộc khách hàng có email bắt đầu bằng một prefix; kết quả được sắp theo thời gian tạo giảm dần và phân trang.

### 2.1. Enum trạng thái

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

### 2.2. Entity Customer

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

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

### 2.3. Entity PurchaseOrder

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

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(
        name = "total_amount",
        nullable = false,
        precision = 15,
        scale = 2
    )
    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
~~~

### 2.4. Entity OrderLine

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

    protected OrderLine() {
    }
}
~~~

Entity `OrderLine` chỉ được dùng để minh họa về fetch và số lượng câu SQL ở phần sau.

### 2.5. Schema dự kiến

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    total_amount DECIMAL(15,2) NOT NULL,
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(255) NOT NULL,
    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
~~~

Đây là schema **minh họa**, không phải DDL tự động bắt buộc từ provider. DDL thật phụ thuộc database và migration. Khi kiểm chứng SQL, đối chiếu với **schema môi trường đang chạy**, không chỉ với annotation hoặc sơ đồ dự kiến.

## 3. Xây truy vấn Criteria có điều kiện rõ ràng

Một phương thức tìm kiếm:

~~~java
package com.example.shop.repository;

import com.example.shop.domain.Customer;
import com.example.shop.domain.OrderStatus;
import com.example.shop.domain.PurchaseOrder;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;
import jakarta.persistence.criteria.ParameterExpression;
import jakarta.persistence.criteria.Root;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Locale;

public class OrderSearchRepository {

    private final EntityManager em;

    public OrderSearchRepository(EntityManager em) {
        this.em = em;
    }

    public List<PurchaseOrder> findOrders(
            OrderStatus status,
            LocalDateTime fromTime,
            String customerEmailPrefix,
            int offset,
            int limit) {

        CriteriaBuilder cb = em.getCriteriaBuilder();
        CriteriaQuery<PurchaseOrder> cq =
            cb.createQuery(PurchaseOrder.class);

        Root<PurchaseOrder> order =
            cq.from(PurchaseOrder.class);

        Join<PurchaseOrder, Customer> customer =
            order.join("customer", JoinType.INNER);

        ParameterExpression<OrderStatus> statusParam =
            cb.parameter(OrderStatus.class, "status");

        ParameterExpression<LocalDateTime> fromParam =
            cb.parameter(LocalDateTime.class, "fromTime");

        ParameterExpression<String> prefixParam =
            cb.parameter(String.class, "prefix");

        cq.select(order)
          .where(
              cb.and(
                  cb.equal(order.get("status"), statusParam),
                  cb.greaterThanOrEqualTo(
                      order.get("createdAt"),
                      fromParam
                  ),
                  cb.like(
                      cb.lower(customer.get("email")),
                      prefixParam
                  )
              )
          )
          .orderBy(
              cb.desc(order.get("createdAt")),
              cb.desc(order.get("id"))
          );

        TypedQuery<PurchaseOrder> query = em.createQuery(cq);

        return query
            .setParameter("status", status)
            .setParameter("fromTime", fromTime)
            .setParameter(
                "prefix",
                customerEmailPrefix.toLowerCase(Locale.ROOT) + "%"
            )
            .setFirstResult(offset)
            .setMaxResults(limit)
            .getResultList();
    }
}
~~~

Gọi:

~~~java
List<PurchaseOrder> orders = repository.findOrders(
    OrderStatus.CONFIRMED,
    LocalDateTime.of(2026, 10, 1, 0, 0),
    "hana@",
    0,
    20
);
~~~

**Lưu ý:** ví dụ giả định input đã được kiểm tra, `offset >= 0` và `limit > 0`; prefix nếu nhập từ người dùng cần xử lý ký tự wildcard `%`, `_` khi yêu cầu tìm chuỗi literal. Đồng thời, quyền truy cập của caller vào dữ liệu khách hàng phải được kiểm tra riêng.

### 3.1. Đọc truy vấn ở cấp Criteria

Hãy diễn giải từng thành phần trước khi nhìn SQL:

| Cấu trúc Java | Ý nghĩa query |
| --- | --- |
| `cq.from(PurchaseOrder.class)` | Entity gốc là `PurchaseOrder` |
| `order.join("customer", INNER)` | Chỉ lấy order có quan hệ customer phù hợp với inner join |
| `cb.equal(order.get("status"), statusParam)` | Lọc trạng thái |
| `cb.greaterThanOrEqualTo(..., fromParam)` | Chỉ lấy order tạo từ mốc thời gian trở đi |
| `cb.lower(customer.get("email"))` | Chuyển email về chữ thường khi so khớp |
| `cb.like(..., prefixParam)` | Tìm email theo prefix |
| `orderBy(createdAt DESC, id DESC)` | Sắp xếp giảm dần, thêm ID để phân biệt thời gian bằng nhau |
| `setFirstResult(offset)` | Bỏ qua một số kết quả ban đầu |
| `setMaxResults(limit)` | Giới hạn số kết quả trả về |

Có thể viết một JPQL tương đương về **ý nghĩa logic**:

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE o.status = :status
  AND o.createdAt >= :fromTime
  AND LOWER(c.email) LIKE :prefix
ORDER BY o.createdAt DESC, o.id DESC
~~~

Nhưng **JPQL tương đương không đồng nghĩa SQL provider sẽ trùng hệt** với một bản dịch viết tay.

### 3.2. SQL minh họa, chưa phải kết quả quan sát

Một hệ quản trị có thể nhận SQL giống:

~~~sql
SELECT
    o.id,
    o.customer_id,
    o.status,
    o.created_at,
    o.total_amount
FROM purchase_orders o
INNER JOIN customers c
    ON c.id = o.customer_id
WHERE o.status = ?
  AND o.created_at >= ?
  AND LOWER(c.email) LIKE ?
ORDER BY o.created_at DESC, o.id DESC
OFFSET ? ROWS
FETCH NEXT ? ROWS ONLY;
~~~

Các placeholder `?` sẽ được bind, ví dụ:

~~~text
status    = CONFIRMED
fromTime  = 2026-10-01T00:00:00
prefix    = hana@%
offset    = 0
limit     = 20
~~~

**Đây là hình dung logic, không phải log đã được ghi nhận.** PostgreSQL, MySQL và các dialect khác có thể render phân trang bằng `LIMIT/OFFSET`, `FETCH FIRST`, truy vấn bao ngoài hoặc cách khác. Provider cũng có thể thêm alias, CAST, điều kiện phụ và đổi thứ tự tham số trong SQL.

Mục đích của bước kiểm chứng là xác nhận những giả định này bằng **SQL thực**.

## 4. Những gì cần ghi nhận từ SQL thực tế

Khi mở SQL log, đừng chỉ kiểm tra có chữ `SELECT`. Hãy xem:

1. **Bảng gốc** có đúng `purchase_orders` không?
2. **JOIN** tới `customers` là `INNER JOIN` hay loại khác, điều kiện `ON` đúng không?
3. **WHERE** có đủ `status`, mốc `created_at` và `LOWER(email) LIKE` không?
4. **Bind parameters** có đúng giá trị và kiểu không?
5. **ORDER BY** có đủ `created_at DESC, id DESC` không?
6. **Pagination** có được chuyển thành giới hạn ở database không?
7. **SELECT list** có lấy những cột cần thiết hay lấy quá nhiều không?
8. Có **SELECT phụ** để nạp EAGER/LAZY association không?
9. Có **INSERT/UPDATE/DELETE bất ngờ** do flush trước query không?
10. Có phát sinh nhiều statement cho một business operation không?
11. Cùng câu query được chạy bao nhiêu lần?
12. Database dùng index và plan như thế nào?

Một query trả kết quả đúng nhưng sinh 101 câu SQL cho 100 record vẫn là điều cần đánh giá. Tương tự, query sinh một SQL nhưng scan toàn bộ bảng lớn cũng có thể kém hiệu năng.

## 5. Bật logging SQL với Hibernate

**Hibernate** là một JPA provider phổ biến. Các ví dụ cấu hình sau tập trung vào **Hibernate 6.x** (thường dùng với Jakarta Persistence), đồng thời nêu điểm khác với Hibernate 5.

### 5.1. Cấu hình logging trong Spring Boot

Trong `application.properties` cho **môi trường development/test**:

~~~properties
# Không cần in SQL hai lần qua System.out.
spring.jpa.show-sql=false

# Hibernate 6.x: SQL được render.
logging.level.org.hibernate.SQL=DEBUG

# Hibernate 6.x: JDBC bind parameters.
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Ví dụ log có thể trông như:

~~~text
DEBUG org.hibernate.SQL -
    select o1_0.id, o1_0.customer_id, o1_0.status, ...
    from purchase_orders o1_0
    join customers c1_0 on c1_0.id = o1_0.customer_id
    where o1_0.status = ?
      and o1_0.created_at >= ?
      and lower(c1_0.email) like ?
    order by o1_0.created_at desc, o1_0.id desc
    offset ? rows fetch first ? rows only

TRACE org.hibernate.orm.jdbc.bind -
    binding parameter (1:VARCHAR) <- [CONFIRMED]
TRACE org.hibernate.orm.jdbc.bind -
    binding parameter (2:TIMESTAMP) <- [2026-10-01T00:00]
TRACE org.hibernate.orm.jdbc.bind -
    binding parameter (3:VARCHAR) <- [hana@%]
~~~

**Log ví dụ chỉ minh họa.** Tên alias, thứ tự parameter và cách format phụ thuộc Hibernate/dialect/version.

Với **Hibernate 5.x**, logger thường dùng để quan sát giá trị bind là:

~~~properties
logging.level.org.hibernate.type.descriptor.sql.BasicBinder=TRACE
~~~

Không nên áp cấu hình logger của Hibernate 5 cho Hibernate 6 rồi kết luận “Hibernate không bind tham số”; tên logger đã thay đổi theo thế hệ.

### 5.2. Khi không dùng Spring Boot

Với Logback, có thể đặt logger tương ứng trong `logback.xml`:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="org.hibernate.SQL" level="DEBUG"/>
    <logger name="org.hibernate.orm.jdbc.bind" level="TRACE"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đây là cấu hình ví dụ cho project sử dụng Logback/SLF4J. Nếu đang dùng Log4j2, JUL hoặc môi trường Jakarta EE, dùng cơ chế logging thực tế của hệ thống.

### 5.3. hibernate.show_sql có dùng được không?

Một số cấu hình Hibernate hỗ trợ:

~~~properties
hibernate.show_sql=true
hibernate.format_sql=true
hibernate.highlight_sql=true
~~~

Chúng có thể hữu ích cho thử nghiệm nhanh. Tuy nhiên, `show_sql` thường in SQL trực tiếp ra console, không luôn tích hợp tốt với định dạng, level và correlation ID của hệ thống logging. Trong dự án cần quan sát có kiểm soát, nên ưu tiên logger chuyên dụng.

`format_sql` giúp câu SQL dễ đọc nhưng **không làm thay đổi ngữ nghĩa SQL**. Không suy luận truy vấn chạy nhanh hơn vì SQL đã được format đẹp.

### 5.4. Cảnh báo: bind log có thể tiết lộ dữ liệu nhạy cảm

`TRACE` của JDBC bind có thể ghi:

- Email và số điện thoại.
- Mã khách hàng, token hoặc thông tin đăng nhập nếu vô tình dùng trong query.
- Dữ liệu tài chính, nội dung cá nhân.
- Giá trị tham số tìm kiếm do người dùng nhập.

Vì vậy:

- Chỉ bật bind logging trong môi trường được kiểm soát.
- Dùng **dữ liệu test giả lập** khi trình bày log.
- Không bật TRACE toàn bộ trong production mà không có chính sách bảo mật.
- Hạn chế thời gian lưu, quyền truy cập và mục đích sử dụng log.
- Nếu cần theo dõi production, ưu tiên metric/trace đã **ẩn dữ liệu** hoặc summary không chứa tham số nhạy cảm.

**Quan sát SQL phải đi cùng quản trị dữ liệu trong log.**

## 6. Bật logging SQL với EclipseLink

**EclipseLink** là một JPA provider khác. Cấu hình logging của EclipseLink **không giống Hibernate**.

Ví dụ trong `persistence.xml`:

~~~xml
<persistence-unit name="shopPU">
    <provider>
        org.eclipse.persistence.jpa.PersistenceProvider
    </provider>

    <class>com.example.shop.domain.Customer</class>
    <class>com.example.shop.domain.PurchaseOrder</class>
    <class>com.example.shop.domain.OrderLine</class>

    <properties>
        <property
            name="eclipselink.logging.level.sql"
            value="FINE"/>
        <property
            name="eclipselink.logging.parameters"
            value="true"/>
    </properties>
</persistence-unit>
~~~

Với cấu hình và logging adapter phù hợp, EclipseLink có thể ghi SQL và parameter values.

Lưu ý:

- Thuộc tính `eclipselink.logging.*` là **extension của EclipseLink**, không phải thuộc tính portable của JPA.
- Cơ chế format log, mức độ chi tiết và logger thực tế tùy phiên bản/cấu hình.
- `eclipselink.logging.parameters=true` có rủi ro tiết lộ dữ liệu tương tự bind logging của Hibernate.
- Không sao chép `logging.level.org.hibernate.SQL` vào ứng dụng chỉ dùng EclipseLink rồi kỳ vọng thấy SQL.

### 6.1. JPA chuẩn có tùy chọn logging chung không?

Không có một thuộc tính `jakarta.persistence.show_sql` chuẩn áp dụng giống nhau cho mọi provider. Nếu dự án cần logging đồng nhất giữa các provider, có thể quan sát ở tầng **JDBC DataSource proxy** hoặc database logging thay vì phụ thuộc logger riêng của ORM.

Tuy nhiên một JDBC proxy cũng cần cấu hình phù hợp để không lặp log và không lưu dữ liệu nhạy cảm.

## 7. Phân biệt SQL template và bind parameter

Câu SQL chuẩn bị thực thi thường có placeholders:

~~~sql
SELECT *
FROM purchase_orders
WHERE status = ?
  AND created_at >= ?;
~~~

JDBC PreparedStatement bind giá trị riêng:

~~~text
parameter 1: VARCHAR    -> "CONFIRMED"
parameter 2: TIMESTAMP  -> 2026-10-01T00:00:00
~~~

### 7.1. Vì sao chỉ xem SQL chưa đủ?

Nếu câu SQL là:

~~~sql
WHERE status = ?
~~~

nhưng API trả dữ liệu không đúng, nguyên nhân có thể không nằm ở cấu trúc SQL mà ở giá trị bind:

~~~text
Expected: CONFIRMED
Actual:   CANCELLED
~~~

Hoặc:

~~~text
Expected fromTime: 2026-10-01T00:00
Actual fromTime:   2026-11-01T00:00
~~~

Vì vậy cần đối chiếu **placeholder, vị trí, kiểu và giá trị tham số**.

### 7.2. Thứ tự tham số SQL không nhất thiết giống tên Criteria

Criteria:

~~~java
ParameterExpression<OrderStatus> statusParam =
    cb.parameter(OrderStatus.class, "status");
~~~

có tên `status` ở tầng JPA, nhưng JDBC có thể dùng tham số vị trí `1`, `2`, `3`. Provider có quyền tổ chức lại SQL/parameter bindings, ví dụ đưa điều kiện JOIN hoặc pagination vào vị trí khác.

**Không giả định parameter SQL thứ 1 luôn ứng với tham số Criteria xuất hiện đầu tiên trong code Java.** Hãy xem log cùng statement cụ thể và binding order thực tế.

### 7.3. Kiểu SQL có thể khác kiểu Java

Ví dụ:

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

Trong Java, tham số có kiểu `OrderStatus`. Nhưng DB có thể nhận một chuỗi `VARCHAR` hoặc một kiểu enum vendor-specific tùy mapping.

Ví dụ `LocalDateTime` có thể bind thành `TIMESTAMP`. Với `Instant` hoặc `OffsetDateTime`, xử lý time zone/JDBC type có thể khác tùy provider, driver và database.

Một lỗi sai kiểu bind đôi khi chỉ xuất hiện khi kiểm tra SQL-level log hoặc khi database báo type mismatch. Không suy luận từ generic `ParameterExpression<T>` rằng kiểu SQL cuối cùng đã đúng tuyệt đối.

## 8. Thời điểm chạy SQL: getResultList, auto flush và cache

Một integration test có thể chạy:

~~~java
PurchaseOrder managed = em.find(PurchaseOrder.class, orderId);

// Sửa managed entity.
managed.changeStatus(OrderStatus.CONFIRMED);

// Chạy Criteria SELECT.
List<PurchaseOrder> rows =
    em.createQuery(criteriaQuery).getResultList();
~~~

Nếu `FlushModeType.AUTO` được dùng, JPA provider có thể đồng bộ thay đổi pending trước SELECT để bảo đảm semantics truy vấn.

Log có thể là:

~~~text
UPDATE purchase_orders SET status = ? WHERE id = ?
SELECT ... FROM purchase_orders WHERE status = ?
~~~

Nếu chỉ hỏi “Criteria sinh ra SQL gì?”, cần phân biệt:

- `UPDATE` do **flush** của thay đổi managed trước query.
- `SELECT` do **Criteria query**.
- SELECT bổ sung do **fetching** association.
- SQL schema/sequence hoặc SQL khác từ cùng transaction.

### 8.1. Đừng đo truy vấn ngay sau bước ghi fixture mà không tách log

Nếu test:

~~~java
em.persist(customer);
em.persist(order);

// Đo SQL ở đây.
List<PurchaseOrder> rows = em.createQuery(cq).getResultList();
~~~

thì `SELECT` có thể đi kèm `INSERT` flush tự động. Khi cần đo riêng query SELECT:

~~~java
em.flush();
em.clear();

// Bắt đầu ghi nhận SQL ở đây.
List<PurchaseOrder> rows = em.createQuery(cq).getResultList();
~~~

`flush()` đồng bộ pending changes, `clear()` detach các managed entities trong context. Đây là thao tác phục vụ **phân tách phép đo trong môi trường test**; không có nghĩa production code nên luôn flush/clear trước mọi query.

### 8.2. Persistence context cache không đồng nghĩa query cache

Khi `em.find(Entity.class, id)` và entity đã managed, JPA có thể trả entity từ first-level cache mà không SELECT mới. Nhưng một Criteria query dạng SELECT thường vẫn được thực thi theo semantics truy vấn; việc trả về managed instance cho cùng ID không đồng nghĩa query SELECT không chạy.

Một số provider có query cache hoặc second-level cache, làm quan sát số SQL phụ thuộc cấu hình. Nếu cần phép đo lặp lại được, phải biết:

- Persistence context đã chứa những entity nào?
- Query cache có bật không?
- Second-level cache có bật không?
- Dữ liệu test đã flush/commit chưa?
- Có transaction khác đang ghi dữ liệu không?

Không quy đổi “không thấy SQL” thành “Criteria không hoạt động” khi chưa kiểm tra cache và thời điểm thực thi.

## 9. So sánh Criteria với JPQL tương đương

Một cách kiểm chứng hữu ích là viết một JPQL tương đương về mặt ngữ nghĩa:

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE o.status = :status
  AND o.createdAt >= :fromTime
  AND LOWER(c.email) LIKE :prefix
ORDER BY o.createdAt DESC, o.id DESC
~~~

Sau đó thực thi Criteria và JPQL với cùng tập tham số/dữ liệu, rồi so sánh **kết quả nghiệp vụ**.

Ví dụ JPQL:

~~~java
List<PurchaseOrder> jpqlRows = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.status = :status
      AND o.createdAt >= :fromTime
      AND LOWER(c.email) LIKE :prefix
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    PurchaseOrder.class
)
.setParameter("status", OrderStatus.CONFIRMED)
.setParameter("fromTime", fromTime)
.setParameter("prefix", "hana@%")
.setMaxResults(20)
.getResultList();
~~~

Đối chiếu:

| Tiêu chí | Criteria | JPQL |
| --- | --- | --- |
| Entity gốc | `Root<PurchaseOrder>` | `FROM PurchaseOrder o` |
| Join | `root.join("customer")` | `JOIN o.customer c` |
| Status | `cb.equal(...)` | `o.status = :status` |
| Time | `cb.greaterThanOrEqualTo(...)` | `o.createdAt >= :fromTime` |
| Email | `cb.like(cb.lower(...))` | `LOWER(c.email) LIKE :prefix` |
| Sort | `orderBy(...)` | `ORDER BY ...` |
| Pagination | `setMaxResults(...)` | `setMaxResults(...)` |

Mục tiêu là xác nhận Criteria không vô tình bỏ một predicate, đảo điều kiện hoặc join sai association.

**Không yêu cầu hai query phải render ra SQL byte-for-byte giống nhau.** Provider có thể thay alias, sắp lại biểu thức, chọn join strategy tương đương hoặc đưa filter vào vị trí khác. Kết quả giống nhau cũng chưa chứng minh hiệu năng giống nhau.

## 10. JOIN: điểm rất dễ sinh SQL ngoài dự kiến

### 10.1. INNER JOIN có thể loại các entity không có association

Criteria:

~~~java
Join<PurchaseOrder, Customer> customer =
    root.join("customer", JoinType.INNER);
~~~

Ý tưởng SQL:

~~~sql
FROM purchase_orders o
INNER JOIN customers c ON c.id = o.customer_id
~~~

Nếu quan hệ nullable, những order không có customer sẽ không xuất hiện trong kết quả.

Trong model ví dụ `@ManyToOne(optional=false)` và FK `NOT NULL`, inner join phản ánh thiết kế domain. Nhưng với association tùy chọn, cần cân nhắc `LEFT JOIN`.

### 10.2. LEFT JOIN để giữ bản ghi cha khi không có con

Ví dụ nếu muốn lấy mọi order và dữ liệu customer tùy chọn:

~~~java
Join<PurchaseOrder, Customer> customer =
    root.join("customer", JoinType.LEFT);
~~~

SQL logic:

~~~sql
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
~~~

Tuy nhiên, nếu đặt điều kiện bắt buộc trên cột customer trong `WHERE`:

~~~java
cb.equal(customer.get("email"), "a@example.com")
~~~

thì các row không có customer vẫn bị loại do biểu thức so sánh với `NULL` không thỏa điều kiện. SQL có thể **có LEFT JOIN nhưng kết quả tương đương INNER JOIN đối với filter đó**.

Vì vậy khi kiểm chứng SQL, không chỉ nhìn chữ `LEFT` mà phải đánh giá cả điều kiện ở `WHERE` và `ON`.

### 10.3. ON và WHERE không luôn tương đương với LEFT JOIN

Ví dụ ứng dụng muốn mọi order, nhưng chỉ join customer có email hợp một điều kiện nào đó.

Criteria có thể đặt điều kiện trên `Join.on(...)`:

~~~java
Join<PurchaseOrder, Customer> customer =
    root.join("customer", JoinType.LEFT);

customer.on(
    cb.like(
        cb.lower(customer.get("email")),
        cb.parameter(String.class, "prefix")
    )
);
~~~

Ý tưởng SQL:

~~~sql
LEFT JOIN customers c
    ON c.id = o.customer_id
   AND LOWER(c.email) LIKE ?
~~~

Khi đặt điều kiện vào `WHERE` thay vì `ON`, những order không khớp customer có thể biến mất. Đối với outer join, **vị trí đặt điều kiện là một phần của ngữ nghĩa**.

Kiểm chứng SQL phải xác nhận predicate nằm đúng chỗ nếu yêu cầu nghiệp vụ phụ thuộc vào việc giữ bản ghi gốc.

## 11. Join qua collection có thể nhân bản số dòng

Giả sử một order có ba order lines. Criteria:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

root.join("lines", JoinType.INNER);

cq.select(root);
~~~

SQL logic:

~~~sql
SELECT o.*
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id;
~~~

Nếu `Order#1` có ba line, SQL có thể trả ba row cùng `o.id = 1`. Tùy query và provider, danh sách entity từ JPA có thể có duplicate hoặc provider có thể xử lý deduplication theo phiên bản/ngữ nghĩa.

### 11.1. Dùng distinct khi yêu cầu root unique

~~~java
cq.select(root).distinct(true);
~~~

Có thể yêu cầu loại các kết quả root trùng lặp ở tầng JPA; SQL render có thể chứa `DISTINCT` hoặc provider thực hiện một phần ở bộ nhớ.

Nhưng cần hiểu:

- `distinct(true)` thay đổi semantics kết quả.
- SQL `DISTINCT` có thể tốn sort/hash.
- Khi fetch collection hoặc chọn nhiều cột, SQL `DISTINCT` không luôn xử lý đúng bài toán phân trang.
- Không dùng distinct để che giấu một join sai đang tạo cardinality ngoài ý muốn.

### 11.2. Test phải kiểm tra cả số phần tử lẫn identity

Ví dụ fixture:

~~~text
Order #101 -> Line #1, #2, #3
Order #102 -> Line #4
~~~

Câu SQL join có thể trả bốn dòng. Nhưng nghiệp vụ muốn **hai đơn hàng**.

Một phép kiểm chứng không nên chỉ viết:

~~~java
assertFalse(orders.isEmpty());
~~~

mà nên kiểm tra số ID duy nhất và danh sách ID theo kết quả mong muốn. Dù database thực thi SQL hợp lệ, query Criteria vẫn có thể sai semantics nếu nhận số phần tử không như yêu cầu.

## 12. Join thông thường khác fetch join

Criteria:

~~~java
root.join("customer", JoinType.INNER);
~~~

dùng association để lọc/join. Nó **không tự bảo đảm `root.getCustomer()` đã được eager-load** sau khi query trả kết quả.

Nếu service cần đọc customer ngay sau query, có thể chọn:

~~~java
root.fetch("customer", JoinType.INNER);
~~~

Điều này thể hiện **fetch join**: provider được yêu cầu tải association trong quá trình truy vấn owner.

Một ví dụ truy vấn đơn:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order =
    cq.from(PurchaseOrder.class);

order.fetch("customer", JoinType.INNER);

cq.select(order)
  .where(cb.equal(order.get("id"), cb.parameter(Long.class, "id")));

PurchaseOrder result = em.createQuery(cq)
    .setParameter("id", orderId)
    .getSingleResult();
~~~

Về SQL, provider thường có thể sinh join tới bảng `customers` và chọn thêm cột customer, nhưng cách thực hiện cụ thể có thể khác theo provider/fetch plan.

### 12.1. N+1 khi chỉ dùng join để lọc

Giả sử tìm 100 đơn hàng bằng Criteria, sau đó:

~~~java
for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getEmail());
}
~~~

Nếu `customer` là lazy và chưa được nạp, provider có thể phát thêm SELECT khi truy cập customer. Số câu SQL phụ thuộc số customer khác nhau, first-/second-level cache và batching; không khẳng định luôn chính xác 101 câu.

Điều cần quan sát:

~~~text
SELECT orders...
SELECT customer WHERE id = ...
SELECT customer WHERE id = ...
SELECT customer WHERE id = ...
...
~~~

Nếu SQL log có chuỗi SELECT lặp theo customer ID, cần đánh giá fetch strategy:

- Fetch join customer khi màn hình cần dữ liệu customer.
- DTO projection chọn trực tiếp email.
- Entity graph.
- Batch fetching theo khả năng provider.
- Đổi cách truy vấn hoặc dữ liệu trả về.

### 12.2. Collection fetch join và pagination là vùng rủi ro

Ví dụ:

~~~java
root.fetch("lines", JoinType.LEFT);
query.setMaxResults(20);
~~~

Một order có nhiều lines sẽ tạo nhiều SQL rows. Phân trang 20 **dòng SQL** không tương đương phân trang 20 **entity Order**.

Một số provider có thể:

- Không áp dụng pagination tại SQL như bạn kỳ vọng.
- Phân trang ở bộ nhớ sau khi lấy nhiều hàng.
- Phát cảnh báo hoặc lỗi tùy cấu hình.
- Thực hiện các kỹ thuật khác để bảo toàn semantics.

Khi kiểm chứng SQL Criteria có fetch collection, cần xem **LIMIT/OFFSET có thực sự giới hạn rows ở database không**, lượng dữ liệu được đọc và số lượng root entity trả về.

Nếu cần phân trang parent có collection, thường dùng:

1. Query ID của parent theo filter/sort, có pagination.
2. Query parent cùng dữ liệu cần thiết theo tập ID đó.
3. Ghép lại thứ tự ở tầng ứng dụng nếu cần.
4. Hoặc dùng projection theo use case thay cho fetch toàn bộ collection.

Không nên sửa bằng `distinct(true)` và mặc nhiên kết luận đã giải quyết mọi vấn đề pagination.

## 13. ORDER BY và tính ổn định của phân trang

Nếu query chỉ sắp:

~~~java
cq.orderBy(cb.desc(root.get("createdAt")));
~~~

hai order có thể có cùng `createdAt`. Database có quyền trả chúng theo thứ tự bất kỳ nếu không có tiêu chí phân biệt.

Khi dùng `setFirstResult` / `setMaxResults`, sự bất định đó có thể khiến một entity xuất hiện ở hai trang hoặc bị bỏ qua giữa các lần truy vấn, ngay cả khi dữ liệu không đổi.

Nên bổ sung tiêu chí unique:

~~~java
cq.orderBy(
    cb.desc(root.get("createdAt")),
    cb.desc(root.get("id"))
);
~~~

SQL cần được kiểm chứng là có **đúng hai điều kiện ORDER BY**.

### 13.1. LIMIT/OFFSET được render theo dialect

JPQL/Criteria không bắt người viết dùng cú pháp phân trang cụ thể của SQL. Tầng JPA:

~~~java
query.setFirstResult(40);
query.setMaxResults(20);
~~~

có thể trở thành:

~~~sql
LIMIT ? OFFSET ?
~~~

hoặc:

~~~sql
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
~~~

hoặc một dạng khác. Điều cần xác nhận là **kết quả đúng trang** và **pagination được đẩy xuống DB khi phù hợp**, không phải câu SQL chứa đúng chữ `LIMIT`.

### 13.2. Phân trang offset vẫn có giới hạn

Ngay cả khi SQL đúng, nếu người dùng xem trang 1 rồi dữ liệu mới được chèn trước khi xem trang 2, offset pagination có thể trả item lặp/thiếu giữa các request.

Đó là vấn đề snapshot/transaction và chiến lược pagination, không phải lỗi cú pháp Criteria. Với luồng dữ liệu lớn và thường xuyên thay đổi, cân nhắc **keyset pagination** theo cặp khóa sort phù hợp.

## 14. Kiểm chứng Criteria COUNT

Một API phân trang thường có hai query:

1. Query dữ liệu theo filter, sort và limit.
2. Query COUNT theo **cùng điều kiện nghiệp vụ**, nhưng không nhất thiết join/fetch giống hệt.

Ví dụ:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.INNER);

cq.select(cb.count(order))
  .where(
      cb.and(
          cb.equal(
              order.get("status"),
              cb.parameter(OrderStatus.class, "status")
          ),
          cb.like(
              cb.lower(customer.get("email")),
              cb.parameter(String.class, "prefix")
          )
      )
  );

Long count = em.createQuery(cq)
    .setParameter("status", OrderStatus.CONFIRMED)
    .setParameter("prefix", "hana@%")
    .getSingleResult();
~~~

SQL thường có dạng:

~~~sql
SELECT COUNT(o.id)
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = ?
  AND LOWER(c.email) LIKE ?;
~~~

Đây là minh họa. Provider có thể dùng `COUNT(*)` hoặc hình thức khác có cùng semantics.

### 14.1. Khi count bị nhân lên bởi collection join

Nếu đếm orders nhưng join `order.lines`, mỗi order có nhiều lines có thể xuất hiện nhiều lần:

~~~java
cq.select(cb.count(order));
~~~

Khi nghiệp vụ cần đếm **số order duy nhất**, cân nhắc:

~~~java
cq.select(cb.countDistinct(order));
~~~

Hoặc thiết kế lại query để dùng `EXISTS` khi phù hợp, tránh join làm nhân row.

Ví dụ yêu cầu “đếm đơn có ít nhất một dòng sản phẩm X” thường có thể diễn đạt theo subquery `EXISTS` để không nhân số order.

### 14.2. Data query và count query phải cùng filter

Nếu data query có:

~~~text
status = CONFIRMED
createdAt >= fromTime
customer.email LIKE prefix
~~~

nhưng count query chỉ có:

~~~text
status = CONFIRMED
~~~

thì số trang trả về sẽ sai mặc dù **cả hai SQL đều hợp lệ**.

Đừng chỉ đối chiếu số query; hãy đối chiếu **tập predicate** và semantics count.

## 15. SELECT entity khác SELECT DTO/projection

Criteria:

~~~java
cq.select(root);
~~~

yêu cầu provider materialize entity `PurchaseOrder`. SQL có thể cần các cột được mapping để tạo entity và theo dõi managed state.

Nếu màn hình chỉ cần ID, ngày tạo và số tiền, có thể dùng DTO projection:

~~~java
public record OrderPreview(
    Long id,
    java.time.LocalDateTime createdAt,
    java.math.BigDecimal totalAmount
) {
}
~~~

Criteria:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<OrderPreview> cq =
    cb.createQuery(OrderPreview.class);

Root<PurchaseOrder> o = cq.from(PurchaseOrder.class);

cq.select(
    cb.construct(
        OrderPreview.class,
        o.get("id"),
        o.get("createdAt"),
        o.get("totalAmount")
    )
);
~~~

SQL có thể chỉ cần:

~~~sql
SELECT o.id, o.created_at, o.total_amount
FROM purchase_orders o;
~~~

Một query trả nhiều entity có thể bị chi phí materialization và fetch khác với query chỉ trả DTO, ngay cả khi số hàng giống nhau.

### 15.1. Đọc SQL để xác nhận projection hiệu quả

Khi dùng `cb.construct(...)`, xem SQL có chọn đúng số cột cần thiết hay không. Đừng dùng `SELECT entity` rồi map sang DTO trong Java nếu lượng dữ liệu thừa quá lớn và query có thể projection trực tiếp.

Tuy nhiên, DTO không được quản lý bởi JPA, không được dirty checking. Nó phù hợp cho đọc dữ liệu và trả API, không phải thay thế mọi managed entity khi cập nhật domain.

### 15.2. Tuple và Object[] cần chú ý kiểu dữ liệu

Một Criteria multi-select có thể trả `Tuple` hoặc `Object[]`:

~~~java
CriteriaQuery<jakarta.persistence.Tuple> cq =
    cb.createTupleQuery();

Root<PurchaseOrder> root = cq.from(PurchaseOrder.class);

cq.multiselect(
    root.get("id").alias("orderId"),
    root.get("totalAmount").alias("amount")
);

List<jakarta.persistence.Tuple> rows =
    em.createQuery(cq).getResultList();
~~~

Nếu SQL trả kết quả đúng mà Java ném lỗi cast, cần xem **projection type/result mapping**, không phải chỉ xem WHERE.

Các alias trong `Tuple` là alias logic của selection, không nhất thiết trùng tên SQL alias do provider sinh. Không dựa vào SQL alias nội bộ để đọc `Tuple` nếu đã dùng alias JPA rõ ràng.

## 16. Dùng SQL logging để phát hiện flush ngoài dự kiến

Một transaction thay đổi managed entity rồi chạy Criteria SELECT:

~~~java
em.getTransaction().begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

// Giả sử PurchaseOrder có setter/method cập nhật trạng thái.
order.confirm();

List<PurchaseOrder> matches =
    em.createQuery(criteriaQuery).getResultList();

em.getTransaction().commit();
~~~

Với `FlushModeType.AUTO`, provider có thể phải làm thay đổi pending xuất hiện phù hợp trong kết quả SELECT. Vì thế log có thể là:

~~~text
SELECT ... FROM purchase_orders WHERE id = ?
UPDATE purchase_orders SET status = ? WHERE id = ?
SELECT ... FROM purchase_orders WHERE status = ?
COMMIT
~~~

Trong một bài đo, nếu bạn đếm ba SQL và kết luận “một Criteria tạo ba SELECT”, bạn đã trộn tác vụ:

- `find` ban đầu có thể tạo SELECT.
- Flush trước query có thể tạo UPDATE.
- Criteria cuối cùng tạo SELECT.

Hãy **tách phạm vi đo**, dùng fixture được chuẩn bị trước và giữ trạng thái context biết trước.

### 16.1. FlushModeType.COMMIT không phải công cụ bỏ qua tính nhất quán

Có thể cấu hình:

~~~java
em.setFlushMode(jakarta.persistence.FlushModeType.COMMIT);
~~~

Nhưng ngữ nghĩa kết quả query khi có pending changes trước commit có thể không được xác định đồng nhất như chế độ AUTO. Không đặt `COMMIT` chỉ để làm log “ít SQL hơn” nếu nghiệp vụ cần query nhìn thấy những thay đổi đang chờ.

### 16.2. Native query và Criteria có thể cùng dùng transaction

Một transaction có thể chạy Criteria SELECT, native SQL và thao tác entity. Khi theo dõi SQL, cần phân biệt nguồn nào sinh statement nào; nếu có mã gọi native query ở giữa, đừng gán SQL của nó cho Criteria.

Dùng correlation ID/span theo request và đặt marker trước/sau đoạn thực thi có thể giúp tách luồng trong log.

## 17. Kiểm chứng ở tầng JDBC bằng DataSource proxy

Nếu cần log SQL của cả Hibernate/EclipseLink/JDBC trực tiếp, có thể dùng một **DataSource proxy** hoặc driver wrapper thích hợp.

Ý tưởng:

~~~text
Application
    |
EntityManager / ORM
    |
JDBC DataSource proxy
    |     +-- Ghi statement count
    |     +-- Thời gian thực thi
    |     +-- SQL template
    |     +-- Bind parameters nếu được phép
    v
JDBC driver
    |
Database
~~~

Ví dụ các thư viện trong hệ sinh thái Java có thể làm việc này là P6Spy hoặc datasource-proxy (phụ thuộc phiên bản và cấu hình). Đây là công cụ **ngoài JPA chuẩn**, không nên giả định ứng dụng nào cũng đã có.

Ưu điểm:

- Quan sát ở ranh giới JDBC nên không phụ thuộc tên logger của provider.
- Có thể ghi cả SQL do code JDBC khác phát sinh.
- Có thể lấy thời gian/statement count hoặc kiểm tra truy vấn trong test.

Giới hạn:

- Không phải lúc nào cũng hiển thị **server-side execution plan**.
- Một số SQL từ stored procedures hoặc driver-level batching có biểu diễn khác.
- Cấu hình logging có thể tác động latency, memory và volume.
- Parameter logging có thể làm lộ dữ liệu nhạy cảm.
- Không thay thế database profiling khi cần hiểu index và IO.

Nếu chỉ cần xác nhận một câu Criteria sinh SQL đúng trong development, logging provider thường đủ. Nếu cần theo dõi **mọi câu SQL trong test** hoặc metric cross-provider, DataSource proxy có thể phù hợp hơn.

## 18. Hibernate StatementInspector: chặn điểm phát SQL để kiểm chứng

Hibernate hỗ trợ interface **`org.hibernate.resource.jdbc.spi.StatementInspector`**. Đây là API **riêng của Hibernate**, không thuộc Jakarta Persistence.

Một inspector đơn giản:

~~~java
package com.example.shop.testutil;

import org.hibernate.resource.jdbc.spi.StatementInspector;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

public final class RecordingSqlInspector implements StatementInspector {

    private static final Queue<String> SQL =
        new ConcurrentLinkedQueue<>();

    @Override
    public String inspect(String sql) {
        SQL.add(sql);
        return sql;
    }

    public static void clear() {
        SQL.clear();
    }

    public static List<String> snapshot() {
        return List.copyOf(SQL);
    }
}
~~~

Quan trọng:

- `inspect(String sql)` được Hibernate gọi khi chuẩn bị statement trong cơ chế phù hợp.
- Giá trị trả về có thể dùng để thay SQL; trong ví dụ **trả nguyên `sql`** để tránh biến đổi hành vi.
- Queue lưu SQL template; **không lưu bind values**.
- Queue tĩnh chỉ được dùng ở đây cho **test chạy tuần tự hoặc có cách cô lập rõ ràng**. Test song song có thể trộn SQL của nhiều request/transaction.
- Không lưu vô hạn mọi SQL trong production bằng một static queue.

### 18.1. Đăng ký Inspector

Với Hibernate, có thể cấu hình:

~~~properties
hibernate.session_factory.statement_inspector=com.example.shop.testutil.RecordingSqlInspector
~~~

Ví dụ Spring Boot khi property được chuyển xuống Hibernate:

~~~properties
spring.jpa.properties.hibernate.session_factory.statement_inspector=com.example.shop.testutil.RecordingSqlInspector
~~~

Cơ chế cấu hình có thể thay đổi theo cách khởi tạo `SessionFactory` và phiên bản Hibernate; kiểm tra môi trường thực tế. Một ứng dụng có thể đăng ký inspector instance thay vì class name trong cấu hình programmatic.

### 18.2. Dùng inspector để quan sát SQL phát ra

Trong test đã có fixture:

~~~java
em.flush();
em.clear();

RecordingSqlInspector.clear();

// Thực thi Criteria query được quan tâm.
List<PurchaseOrder> rows =
    em.createQuery(criteriaQuery).getResultList();

List<String> sqlStatements =
    RecordingSqlInspector.snapshot();
~~~

Cần đọc các câu SQL đã capture, xác định câu nào thuộc Criteria và câu nào là secondary fetch. `StatementInspector` không tự gắn nhãn “SQL này từ Criteria X” nếu nhiều query chạy cùng lúc.

### 18.3. Không kiểm chứng bằng so khớp nguyên chuỗi SQL

Một assertion kiểu:

~~~java
assertEquals(
    "select purchase0_.id as id1_0_ from purchase_orders purchase0_ ...",
    capturedSql
);
~~~

rất dễ hỏng khi:

- Nâng cấp Hibernate.
- Chuyển PostgreSQL sang MySQL.
- Đổi naming strategy.
- Provider đổi alias hoặc whitespace.
- Dialect thay cú pháp phân trang.
- Thêm column mapping hoặc điều kiện đa tenant.

Nếu mục tiêu test là **kết quả nghiệp vụ**, assert trên kết quả. Nếu mục tiêu test là **hình dạng SQL**, assert thuộc tính bền vững hơn như **có một JOIN cần thiết**, **không xuất hiện truy vấn N+1**, hoặc **không SELECT toàn bộ bảng con** khi không cần.

Ví dụ assertion định hướng trong test đơn luồng:

~~~java
boolean hasOrderQuery = RecordingSqlInspector.snapshot()
    .stream()
    .map(s -> s.toLowerCase(java.util.Locale.ROOT))
    .anyMatch(s -> s.contains("purchase_orders"));

org.junit.jupiter.api.Assertions.assertTrue(
    hasOrderQuery,
    "Expected at least one statement touching purchase_orders"
);
~~~

Test này **chưa đủ** để chứng minh filter, pagination và bind đúng. Nó chỉ minh họa cách quan sát SQL bằng inspector. Kết luận có độ tin cậy cao cần kết hợp SQL shape, bind values và **assertion dữ liệu đầu ra**.

## 19. Hibernate Statistics: đo số statement và truy vấn

Hibernate còn có API statistics:

~~~java
org.hibernate.SessionFactory sessionFactory =
    emf.unwrap(org.hibernate.SessionFactory.class);

org.hibernate.stat.Statistics statistics =
    sessionFactory.getStatistics();

statistics.setStatisticsEnabled(true);
statistics.clear();

List<PurchaseOrder> rows =
    em.createQuery(criteriaQuery).getResultList();

long preparedStatements =
    statistics.getPrepareStatementCount();
~~~

Một số ý nghĩa:

- `getPrepareStatementCount()` cung cấp số lượng prepared statements được ghi nhận theo thống kê của Hibernate.
- Statistics có thể đếm theo **SessionFactory**, không tự động cô lập theo request.
- Query cache, batch, fetch strategy và các thao tác cùng thời điểm có thể ảnh hưởng số liệu.
- `statistics.clear()` đặt lại số đếm thống kê, không xóa database hay persistence context.
- Cần bật thống kê đúng cách; tắt/bật trong production phải cân nhắc overhead.

**Đây là Hibernate-specific API**, không chạy nguyên xi trên EclipseLink. Với test yêu cầu di chuyển giữa provider, nên dùng một công cụ thống kê ở tầng JDBC hoặc abstraction riêng.

### 19.1. Kiểm tra N+1 bằng số statement

Ví dụ một test kiểm tra việc tải 20 orders cùng customer:

~~~text
Trường hợp A: Criteria lấy order, lặp getCustomer()
    SELECT orders
    SELECT customer #1
    SELECT customer #2
    ...
Trường hợp B: Criteria fetch join customer
    SELECT orders JOIN customer
~~~

Một test có thể ghi nhận statement count sau mỗi phương án và so sánh, nhưng **không áp đặt số đúng tuyệt đối** nếu first-level cache, batch fetching hoặc cùng customer được tái sử dụng.

Mục tiêu test là ràng buộc đặc tính hiệu năng quan trọng: truy vấn không tăng gần tuyến tính số SQL theo số entity. Nếu muốn giới hạn cứng, cần fixture và cấu hình cache/fetch được kiểm soát.

## 20. Một kịch bản integration test có thể tái hiện

Để kiểm chứng Criteria có độ tin cậy, cần **dữ liệu đầu vào được xác định** và **kết quả mong đợi**.

Giả sử fixture:

| ID logic | Email khách hàng | Status | createdAt | Mong muốn |
| --- | --- | --- | --- | --- |
| A | `hana@example.com` | CONFIRMED | 2026-10-03 09:00 | Có |
| B | `hana@example.com` | DRAFT | 2026-10-04 10:00 | Không |
| C | `huy@example.com` | CONFIRMED | 2026-10-05 11:00 | Không |
| D | `hana@example.com` | CONFIRMED | 2026-09-30 23:59 | Không |
| E | `hana@example.com` | CONFIRMED | 2026-10-06 08:00 | Có |

Query:

~~~text
status = CONFIRMED
fromTime = 2026-10-01T00:00
prefix = hana@%
sort = createdAt DESC, id DESC
offset = 0
limit = 10
~~~

Kết quả đúng theo business:

~~~text
E
A
~~~

### 20.1. Tách arrange và act

Trong integration test:

~~~java
// Arrange: chuẩn bị fixture theo transaction hợp lệ.
// Persist Customer và PurchaseOrder có dữ liệu kiểm chứng.
// Commit hoặc flush dữ liệu, theo test fixture strategy.

// Tách context của bước chuẩn bị khỏi bước đo.
em.flush();
em.clear();

// Act: bắt đầu vùng quan sát SQL ở đây.
RecordingSqlInspector.clear();

List<PurchaseOrder> result =
    repository.findOrders(
        OrderStatus.CONFIRMED,
        LocalDateTime.of(2026, 10, 1, 0, 0),
        "hana@",
        0,
        10
    );

// Assert: business result, sau đó đối chiếu SQL.
~~~

Nếu test đã dùng transaction fixture riêng được commit và query bằng EntityManager khác, không gọi `em.flush()` ngoài transaction phù hợp. Quy trình cụ thể phụ thuộc test framework và mô hình persistence unit.

### 20.2. Assertion dữ liệu đầu ra là nền tảng

Ví dụ JUnit 5:

~~~java
List<String> codes = result.stream()
    .map(PurchaseOrder::getOrderCode)
    .toList();

org.junit.jupiter.api.Assertions.assertEquals(
    List.of("E", "A"),
    codes
);
~~~

Để ví dụ compile, entity thực tế phải có `orderCode` và getter như trong fixture. Nếu model đang dùng ID/field khác, assert theo identifier đã định nghĩa trong domain. **Đây là minh họa cách kiểm chứng result**, không phải code test đã được chạy trong bài.

Không nên chỉ assert `result.size() == 2` nếu kết quả có thể chứa nhầm hai bản ghi khác.

### 20.3. Assertion SQL riêng biệt

Có thể kiểm tra các dấu hiệu như:

- Statement SELECT chính chạm bảng `purchase_orders`.
- Có JOIN tới `customers` do filter email.
- Có điều kiện tương ứng `status` và `created_at`.
- Không có SELECT lặp không cần thiết khi đọc customer.
- Có phương thức phân trang tương thích dialect.

Đừng để assertion dạng “contains string” quá lỏng trở thành chứng cứ duy nhất. Một query thiếu điều kiện vẫn có thể chứa tên bảng và từ `JOIN`, nhưng trả dữ liệu sai.

### 20.4. Tránh test chạy đồng thời làm nhiễu SQL capture

Nếu dùng `RecordingSqlInspector` với queue tĩnh, SQL từ test khác có thể xuất hiện giữa các phép đo. Với suite lớn, cần thiết kế cô lập bằng:

- Chạy test liên quan đến inspector tuần tự.
- Gắn correlation ID hoặc session/request context theo cơ chế kiểm soát được.
- Dùng DataSource proxy với listener theo scope phù hợp.
- Không dùng shared mutable SQL queue làm nguồn khẳng định tuyệt đối khi chạy song song.

Tính lặp lại của phép đo quan trọng hơn việc “bắt được rất nhiều log”.

## 21. Đánh giá SQL bằng EXPLAIN

Khi đã biết SQL và bind parameters, bước tiếp theo là xem database thực thi như thế nào.

Với PostgreSQL, một truy vấn tương đương có thể được phân tích:

~~~sql
EXPLAIN
SELECT o.id, o.created_at, o.status
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'CONFIRMED'
  AND o.created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND LOWER(c.email) LIKE 'hana@%'
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20 OFFSET 0;
~~~

`EXPLAIN` hiển thị execution plan mà optimizer dự kiến, như:

~~~text
Limit
  -> Sort
       -> Hash Join
            -> Seq Scan on purchase_orders
            -> Seq Scan on customers
~~~

Đây là một **sơ đồ plan minh họa**, không phải kết quả EXPLAIN thực tế. Database có thể chọn index scan, nested loop, hash join hoặc phương án khác tùy thống kê, index, dữ liệu và tham số.

### 21.1. EXPLAIN ANALYZE đo thực thi

Với PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM ...
WHERE ...;
~~~

`ANALYZE` **thực thi câu truy vấn** để ghi thời gian và hàng thực tế. Với một SELECT chỉ đọc trong môi trường kiểm thử phù hợp, nó hữu ích để xác nhận:

- Estimated rows vs actual rows.
- Time của từng node.
- Số lần loop trong nested loop.
- Shared buffer hits/reads.
- Sort strategy và memory.
- Index scan hay sequential scan.

**Không chạy `EXPLAIN ANALYZE` tùy tiện trên DML trong production** vì nó có thể thực thi tác dụng ghi của câu lệnh. Ngay cả SELECT cũng có thể gây tải đáng kể nếu quét nhiều dữ liệu, nên cần môi trường và quyền phù hợp.

### 21.2. Không copy SQL chứa bí mật vào công cụ ngoài

Khi chuyển SQL từ log sang công cụ query plan:

- Dùng giá trị đại diện/fixture không nhạy cảm.
- Kiểm tra kiểu tham số thực tế, đặc biệt timestamp và enum.
- Không đẩy email/token/ID riêng tư tới dịch vụ công khai.
- Giữ điều kiện, sort và giới hạn đủ giống query cần phân tích.
- Chú ý query plan có thể khác nhau theo giá trị bind thực tế.

### 21.3. Những chỉ số nên đọc

| Chỉ số/hiện tượng | Ý nghĩa cần đánh giá |
| --- | --- |
| Seq Scan trên bảng rất lớn | Có đang lọc quá nhiều hàng, thiếu index hoặc optimizer chọn hợp lý không? |
| Index Scan / Bitmap Scan | Có index phù hợp với filter không? |
| Nested Loop rất nhiều vòng | Join có đang làm tăng số lượt truy cập không? |
| Hash Join / Merge Join | Có phù hợp với số hàng và bộ nhớ không? |
| Sort lớn, có spill | ORDER BY có tốn memory/disk không? |
| Estimated rows lệch actual rows | Thống kê hoặc selectivity estimate có vấn đề không? |
| LIMIT nằm trên truy vấn lớn | Có thật sự giới hạn sớm hay vẫn phải sort/lấy rất nhiều rows? |
| Buffers read cao | Có nhiều I/O vật lý hoặc cache miss không? |

Không nên quy mọi `Seq Scan` là xấu: với bảng nhỏ hoặc điều kiện trả phần lớn dữ liệu, sequential scan có thể là lựa chọn đúng.

## 22. Index liên quan trực tiếp tới Criteria query

Truy vấn ví dụ lọc:

~~~text
status = ?
created_at >= ?
customer.email LIKE prefix
ORDER BY created_at DESC, id DESC
~~~

Có thể cân nhắc các index tùy workload:

~~~sql
CREATE INDEX idx_orders_status_created_id
ON purchase_orders (status, created_at, id);
~~~

Hoặc:

~~~sql
CREATE INDEX idx_orders_customer_status_created_id
ON purchase_orders (
    customer_id,
    status,
    created_at,
    id
);
~~~

**Không áp dụng cả hai index theo thói quen.** Mỗi index có chi phí disk, write amplification và maintenance. Lựa chọn dựa trên query plan, phân phối dữ liệu và cách join thực tế.

### 22.1. Hàm LOWER có thể ảnh hưởng index

Điều kiện:

~~~sql
LOWER(c.email) LIKE 'hana@%'
~~~

không nhất thiết tận dụng hiệu quả unique index thông thường trên `email`. Với PostgreSQL hoặc database khác, có thể cần:

- Expression index thích hợp nếu DB cho phép.
- Collation/citext hoặc column normalized theo schema.
- Prefix-search index/operator class phù hợp.
- Truy vấn đơn giản hơn nếu email đã được chuẩn hóa khi lưu.

Kiểm chứng SQL cần đi kèm kiểm chứng **khả năng dùng index**. Một truy vấn đúng về kết quả có thể vẫn chậm do biểu thức hàm.

### 22.2. Index theo FK

Join:

~~~sql
o.customer_id = c.id
~~~

có thể hưởng lợi từ index trên `purchase_orders.customer_id` trong nhiều workload. Nhưng việc chọn composite index hay FK index riêng cần dựa vào truy vấn thực tế.

Không mặc định rằng database tự tạo index ở mọi cột FK; hành vi phụ thuộc hệ quản trị và schema migration.

## 23. Kiểm chứng SQL sinh ra từ CriteriaUpdate và CriteriaDelete

Criteria API không chỉ tạo SELECT. Nó còn có:

~~~java
CriteriaUpdate<PurchaseOrder> update =
    cb.createCriteriaUpdate(PurchaseOrder.class);
~~~

và:

~~~java
CriteriaDelete<PurchaseOrder> delete =
    cb.createCriteriaDelete(PurchaseOrder.class);
~~~

### 23.1. CriteriaUpdate

Ví dụ cập nhật trạng thái tất cả order DRAFT:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<PurchaseOrder> update =
    cb.createCriteriaUpdate(PurchaseOrder.class);

Root<PurchaseOrder> root = update.from(PurchaseOrder.class);

update.set(root.get("status"), OrderStatus.CANCELLED)
      .where(
          cb.equal(root.get("status"), OrderStatus.DRAFT)
      );

int affected = em.createQuery(update).executeUpdate();
~~~

SQL minh họa:

~~~sql
UPDATE purchase_orders
SET status = ?
WHERE status = ?;
~~~

Cần **transaction hợp lệ** cho bulk DML. `executeUpdate()` là mốc thực thi, khác với `getResultList()`.

### 23.2. CriteriaDelete

Ví dụ xóa order DRAFT trước một mốc:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaDelete<PurchaseOrder> delete =
    cb.createCriteriaDelete(PurchaseOrder.class);

Root<PurchaseOrder> root = delete.from(PurchaseOrder.class);

delete.where(
    cb.and(
        cb.equal(root.get("status"), OrderStatus.DRAFT),
        cb.lessThan(
            root.get("createdAt"),
            cb.parameter(LocalDateTime.class, "cutoff")
        )
    )
);

int affected = em.createQuery(delete)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
~~~

SQL minh họa:

~~~sql
DELETE FROM purchase_orders
WHERE status = ?
  AND created_at < ?;
~~~

### 23.3. Bulk DML khác dirty checking

CriteriaUpdate/Delete vận hành theo semantics **bulk DML** của JPA:

- Không tương đương với việc tải từng managed entity rồi gọi setter hoặc `em.remove(...)`.
- Có thể bỏ qua entity lifecycle callback/cascade và cách quản lý version của entity thông thường.
- Managed entities đã tải trước bulk update/delete có thể **stale** trong persistence context.
- Cần kiểm tra FK, transaction isolation và rollback.
- Không kết luận “UPDATE thành công” chỉ từ SQL text; phải kiểm tra số hàng ảnh hưởng và state sau transaction.

Nếu test query CriteriaUpdate trên managed entity đã có trong context, cần chú ý `clear()`/refresh **sau khi đã xử lý pending changes hợp lệ** để tránh đọc lại một object Java cũ rồi tưởng DB chưa cập nhật.

## 24. Ràng buộc về SQL dialect và phiên bản provider

JPA định nghĩa ngữ nghĩa Criteria, nhưng SQL cuối cùng phụ thuộc:

| Yếu tố | Ảnh hưởng có thể thấy |
| --- | --- |
| PostgreSQL/MySQL/Oracle/SQL Server | Phân trang, hàm, kiểu boolean, quoting, locking |
| Hibernate/EclipseLink | Alias, join rendering, fetch, predicate handling, result mapping |
| Phiên bản provider | Query engine, tối ưu hóa join, cách xử lý distinct |
| Naming strategy | Tên bảng/cột, chữ hoa/thường, underscore |
| Inheritance strategy | Discriminator, JOINED tables, UNION |
| AttributeConverter | Kiểu/giá trị tham số SQL được bind |
| Entity graph / fetch mode | JOIN hoặc secondary SELECT |
| Filters/multi-tenancy | WHERE/ON bổ sung điều kiện |
| Cache | Một số lần tải không phát SELECT mới |
| JDBC driver | Cách binding/hiển thị kiểu, batching |
| Database schema | Index, constraints, triggers, generated columns |

Ví dụ `setMaxResults(10)` không có nghĩa SQL trên mọi DB chứa từ `LIMIT 10`. Câu SQL có thể hợp lệ về semantics nhưng có hình thức khác.

### 24.1. Đừng khẳng định “JPA luôn sinh JOIN này”

Provider có thể:

- Dùng FK trực tiếp khi chỉ cần ID của association.
- Bỏ JOIN không cần thiết nhờ metadata.
- Thêm JOIN do fetch plan.
- Dùng subquery tương đương.
- Render predicate theo một cách SQL khác mà vẫn cho cùng kết quả.

Nếu nghiệp vụ phụ thuộc vào hiệu năng hoặc một loại JOIN nhất định, quan sát **provider và phiên bản đang chạy**. Không sử dụng một ảnh chụp SQL từ tutorial khác như bằng chứng cho hệ thống của mình.

### 24.2. Chuyển database cần chạy lại phép đo

H2 có thể hỗ trợ một phần cú pháp giống PostgreSQL hoặc MySQL, nhưng **không phải bản sao hoàn chỉnh** về optimizer, collation, locking, function và index.

Một test chạy đúng ở H2 chỉ chứng minh hành vi trên cấu hình H2 đó. Nếu production dùng PostgreSQL, nên có integration test trên PostgreSQL (có thể qua container) cho các query quan trọng.

## 25. Hibernate-specific API không thay thế JPA portable contract

Ví dụ:

~~~java
org.hibernate.Session session =
    em.unwrap(org.hibernate.Session.class);
~~~

hoặc:

~~~java
org.hibernate.SessionFactory sessionFactory =
    emf.unwrap(org.hibernate.SessionFactory.class);
~~~

cho phép truy cập khả năng riêng của Hibernate, nhưng code sẽ phụ thuộc provider.

Khi cần tính portable:

- Viết Criteria theo `jakarta.persistence.criteria.*`.
- Xác minh kết quả bằng integration test.
- Quan sát SQL qua JDBC proxy nếu muốn tránh phụ thuộc logger ORM.
- Cô lập Hibernate statistics/inspector trong module test hoặc diagnostic adapter.
- Không để service nghiệp vụ phụ thuộc sâu vào SQL alias, internals hoặc classes của Hibernate.

**Kết quả JPA là hợp đồng chính; SQL text là bằng chứng thực thi của môi trường cụ thể.** Hai việc đều quan trọng nhưng không nên nhầm tầng abstraction.

## 26. Quy trình kiểm chứng có thể áp dụng trong dự án

Một quy trình thực tế cho một query Criteria:

### Bước 1: Xác định hợp đồng nghiệp vụ

Ví dụ:

~~~text
Input:
  status = CONFIRMED
  fromTime = 2026-10-01T00:00
  prefix = hana@%
  offset = 0
  limit = 20

Output:
  Danh sách PurchaseOrder phù hợp
  Sắp createdAt DESC, id DESC
  Không chứa order ngoài điều kiện
~~~

Nêu rõ cách xử lý null, thứ tự và phân trang để tránh “SQL hợp lệ nhưng sai ý định”.

### Bước 2: Chuẩn bị dữ liệu có ca phân biệt

Tạo ít nhất:

- Một bản ghi khớp mọi điều kiện.
- Một bản ghi sai status.
- Một bản ghi trước mốc thời gian.
- Một bản ghi thuộc customer không khớp prefix.
- Hai bản ghi có cùng thời gian để kiểm tra tie-breaker ID.
- Một parent có nhiều child nếu query có to-many join.

### Bước 3: Cô lập transaction và persistence context

Hoàn tất fixture trong transaction phù hợp, flush/commit, hoặc clear/new context tùy test. Không để SQL fixture làm nhiễu phép đo query.

### Bước 4: Bật công cụ quan sát

Chọn một:

- Hibernate SQL + bind logger.
- EclipseLink SQL logger.
- JDBC DataSource proxy.
- Hibernate StatementInspector và Statistics nếu test đã dùng Hibernate.
- Database statement log/monitoring theo quyền và môi trường.

Không bật tất cả công cụ nếu gây log lặp mà không thêm thông tin.

### Bước 5: Thực thi Criteria

Gọi `getResultList()`, `getSingleResult()` hoặc `executeUpdate()` theo loại query. Đặt tham số, offset, limit và transaction rõ ràng.

### Bước 6: Assert kết quả nghiệp vụ

Đối chiếu ID, thứ tự, số lượng, giá trị projection và xử lý null theo fixture. Không dừng ở việc “không ném exception”.

### Bước 7: Kiểm tra SQL/JDBC

Ghi nhận:

- SQL statement chính.
- Các statement phụ.
- Bind values/types.
- JOIN, WHERE, GROUP BY, ORDER BY, pagination.
- Số lần statement lặp lại.
- SQL bất ngờ do flush.

### Bước 8: Phân tích execution plan khi cần

Dùng `EXPLAIN` với dữ liệu tương đương trên DB mục tiêu. Đọc row estimates, index, join, sort và IO.

### Bước 9: Tối ưu đúng tầng

Nếu sai kết quả: sửa Criteria/predicate/join.

Nếu quá nhiều SELECT: sửa fetch plan, projection hoặc batch strategy.

Nếu một SELECT rất chậm: xem index, thống kê, filter, order, plan.

Nếu bind sai: sửa type, converter, parameter handling.

Nếu SQL khác giữa DB: đánh giá dialect/provider và portability.

### Bước 10: Ghi lại giả định cần bảo vệ

Với query quan trọng, nên có integration test thể hiện **hợp đồng nghiệp vụ**, kèm phép đo SQL shape/statement count cho những đặc tính hiệu năng được coi là thiết yếu. Tránh snapshot nguyên SQL dài không ổn định qua mỗi phiên bản.

## 27. Những lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm chứng |
| --- | --- | --- |
| Không thấy SQL dù đã xây Criteria | Chưa gọi phương thức thực thi; logger sai | Kiểm tra `getResultList()` và cấu hình provider |
| Có SQL nhưng không thấy giá trị `?` | Chưa bật bind logger hoặc proxy | Bật logger bind đúng phiên bản ở môi trường an toàn |
| `WHERE` thiếu điều kiện | Predicate chưa được đưa vào `cq.where(...)` | Xem cây Criteria và SQL thực |
| Trả thiếu parent | INNER JOIN hoặc điều kiện trên LEFT JOIN ở WHERE | Xem JOIN/ON/WHERE và fixture nullable |
| Parent bị lặp | Join collection to-many nhân row | Đối chiếu SQL rows, `distinct`, countDistinct, EXISTS |
| Pagination trả ít root hơn dự kiến | To-many fetch join hoặc duplicate rows | Kiểm tra LIMIT/OFFSET ở SQL và số root sau materialize |
| N+1 | Truy cập lazy association sau query | Ghi log toàn business operation, xem SELECT lặp |
| SQL nhiều UPDATE trước SELECT | AUTO flush pending changes | Tách fixture/dirty context khỏi query measurement |
| Không thấy SELECT lần thứ hai | First-level/second-level cache hoặc query cache | Kiểm tra cache/context và loại thao tác |
| SQL đúng nhưng kết quả sai | Bind values/type hoặc dữ liệu fixture khác | Kiểm tra parameter log và schema |
| COUNT lớn hơn số entity | Join to-many và COUNT không distinct | Dùng countDistinct/EXISTS phù hợp |
| DTO nhận sai type | Projection/type mapping không khớp | Xem SELECT columns và constructor/generic type |
| SQL quá khác tutorial | Dialect, provider version, naming strategy | Đối chiếu môi trường thật |
| Hibernate logger không in bind | Dùng logger Hibernate 5 trên Hibernate 6 | Xem namespace logger theo phiên bản |
| Test flakey khi capture SQL | Queue dùng chung, test song song, cache | Cô lập capture và fixture |
| Query chậm dù SQL hợp lệ | Index/query plan/sort | Chạy `EXPLAIN` trên DB mục tiêu |
| SQL có dữ liệu nhạy cảm trong log | Bật TRACE bind không kiểm soát | Tắt/redact và dùng dữ liệu test |
| DML cập nhật DB nhưng entity cũ không đổi | Bulk CriteriaUpdate/Delete bỏ qua managed state | Clear/refresh đúng transaction sau bulk |
| Query khác nhau giữa PostgreSQL và MySQL | Dialect và SQL-specific capabilities | Integration test trên cả hai DB |

## 28. Bài tập thực hành có lời giải

### Bài 1. Khi nào Criteria thực sự chạy SELECT?

~~~java
CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> root = cq.from(Customer.class);

cq.select(root);

TypedQuery<Customer> query = em.createQuery(cq);
~~~

**Hỏi:** Vì sao chưa thấy SELECT trong SQL log?

**Đáp án:** Chưa gọi phương thức thực thi. Với SELECT, thường cần `query.getResultList()` hoặc `getSingleResult()` để provider thực hiện truy vấn.

### Bài 2. Sai vị trí điều kiện với LEFT JOIN

Criteria dùng `LEFT JOIN` tới association tùy chọn nhưng đặt:

~~~java
cq.where(cb.equal(join.get("status"), "ACTIVE"));
~~~

**Hỏi:** Vì sao bản ghi cha không có association biến mất?

**Đáp án:** Điều kiện trên cột phía joined ở `WHERE` loại các row có giá trị NULL. Nếu muốn giữ parent và chỉ hạn chế dữ liệu ở joined side, cần đánh giá dùng `join.on(...)` hoặc cách viết predicate phù hợp.

### Bài 3. COUNT bị nhân đôi

Có 2 order, mỗi order có 3 lines. Criteria join lines rồi `cb.count(root)`.

**Hỏi:** Kết quả COUNT có thể là bao nhiêu và vì sao?

**Đáp án:** Có thể là 6 do SQL có 6 hàng join, dù chỉ có 2 order. Muốn đếm order duy nhất, dùng `cb.countDistinct(root)` hoặc truy vấn EXISTS phù hợp.

### Bài 4. Không thấy parameter trong SQL log

SQL:

~~~sql
WHERE status = ?
~~~

**Hỏi:** Có phải Criteria không binding `status`?

**Đáp án:** Không. JDBC dùng placeholder. Cần xem bind logger hoặc JDBC proxy để xác nhận giá trị và kiểu.

### Bài 5. Kiểm chứng enum

Entity dùng:

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

Criteria binding `OrderStatus.CONFIRMED`.

**Đáp án:** Kiểm tra SQL-level binding có giá trị tương ứng và kiểu SQL phù hợp. Không mong giá trị Java enum xuất hiện nguyên văn trong SQL template.

### Bài 6. Tại sao có UPDATE trước SELECT?

Một managed entity bị sửa, rồi Criteria SELECT chạy trong transaction với flush mode AUTO.

**Đáp án:** Provider có thể flush pending UPDATE trước SELECT. Tách SQL của flush khỏi SQL chính của Criteria khi phân tích.

### Bài 7. N+1 với Customer

Criteria trả 100 orders, service gọi `order.getCustomer().getEmail()` với relation LAZY.

**Đáp án:** Có thể phát sinh nhiều SELECT để nạp customers chưa có trong persistence context. Kiểm tra statement count và SQL log của toàn vòng lặp; dùng fetch join, DTO hoặc batch fetching khi phù hợp.

### Bài 8. Vì sao JOIN FETCH collection không tốt cho pagination?

Query fetch `order.lines` và gọi `setMaxResults(20)`.

**Đáp án:** Một order có thể tạo nhiều SQL rows. Provider không thể đơn giản áp giới hạn 20 hàng join để bảo đảm 20 parent đầy đủ. Cần đánh giá SQL thực, thường dùng phân trang ID parent trước rồi tải collection riêng.

### Bài 9. Sắp theo createdAt nhưng trang không ổn định

Nhiều orders có cùng createdAt.

**Đáp án:** Thêm ID unique vào ORDER BY, ví dụ `createdAt DESC, id DESC`. Offset vẫn có giới hạn khi dữ liệu thay đổi giữa các lần đọc.

### Bài 10. SQL text khác sau nâng cấp Hibernate

Một test snapshot toàn bộ SQL thất bại vì alias `purchase0_` đổi thành `p1_0`.

**Đáp án:** Nếu ngữ nghĩa và kết quả không đổi, đây có thể chỉ là thay đổi renderer. Test nên tập trung kết quả, số SQL và đặc tính SQL quan trọng thay vì alias nội bộ.

### Bài 11. H2 chạy nhanh nhưng PostgreSQL chậm

**Đáp án:** Hai DB có optimizer, thống kê, kích thước dữ liệu và index khác nhau. Test kết quả trên H2 không thay thế `EXPLAIN ANALYZE` trên PostgreSQL có dữ liệu gần production.

### Bài 12. StatementInspector thấy SQL nhưng không có bind values

**Đáp án:** `StatementInspector` nhận SQL template tại bước chuẩn bị statement; không tự cung cấp mọi giá trị JDBC bind. Dùng logger bind hoặc công cụ JDBC phù hợp nếu cần kiểm tra tham số.

### Bài 13. Dùng isLoaded thay việc đếm SELECT

Sau query:

~~~java
util.isLoaded(order, "customer")
~~~

**Hỏi:** Có xác định được số SELECT đã phát không?

**Đáp án:** Không. `isLoaded` quan sát load state của attribute, không đo số SQL hay nguồn dữ liệu cache. Dùng statement logging/statistics để kiểm chứng query count.

### Bài 14. Bulk CriteriaUpdate không làm object managed đổi trạng thái

Ứng dụng gọi `executeUpdate()`, database đã đổi status, nhưng một managed entity trong context vẫn có giá trị cũ.

**Đáp án:** Bulk DML bỏ qua cơ chế cập nhật managed instance thông thường. Cần quản lý persistence context (refresh/clear theo tình huống) và transaction phù hợp.

### Bài 15. SELECT entity hoặc DTO?

Màn hình chỉ cần ID và số tiền của 100.000 orders.

**Đáp án:** Cân nhắc Criteria projection `cb.construct(...)` hoặc tuple chọn đúng cột, thay vì materialize toàn bộ entity graph. Kiểm tra SQL SELECT list để xác nhận chỉ lấy dữ liệu cần thiết.

### Bài 16. EXPLAIN có phải kết quả SQL logging không?

**Đáp án:** Không. Logging cho biết SQL/JDBC operation được gửi; EXPLAIN cho biết optimizer dự kiến thực thi (và EXPLAIN ANALYZE đo thực thi). Cần cả hai khi điều tra vấn đề hiệu năng.

### Bài 17. Kiểm tra query filter ở test

Fixture có một order CONFIRMED trước mốc `fromTime`, và một DRAFT sau mốc.

**Đáp án:** Cả hai phải bị loại. Test chỉ chứa dữ liệu khớp điều kiện sẽ không phát hiện Criteria bị thiếu predicate hoặc dùng phép so sánh sai.

### Bài 18. Test SQL đang đếm statement của fixture

Test persist 100 orders rồi chạy Criteria, statistics báo nhiều INSERT cùng SELECT.

**Đáp án:** Cần flush/commit fixture rồi reset vùng quan sát SQL trước khi thực thi Criteria, dùng context rõ ràng. Không gán số INSERT của phần chuẩn bị cho query.

### Bài 19. SQL JOIN tồn tại nhưng service vẫn N+1

Criteria có join dùng để lọc email, không có fetch join. Service truy cập customer ở vòng lặp.

**Đáp án:** JOIN thông thường không tự bảo đảm association đã initialized. Cần xem SQL/fetch semantics, dùng `fetch` hoặc DTO khi nghiệp vụ cần customer.

### Bài 20. Tại sao không nên bật bind log trong production?

**Đáp án:** Bind values có thể bao gồm email, token, dữ liệu cá nhân/tài chính. Chỉ bật trong phạm vi cho phép, cần redaction, quyền truy cập, retention và giới hạn chi phí logging.

## 29. Mẫu ghi chép một lần kiểm chứng SQL

Khi phân tích một query Criteria quan trọng, có thể ghi lại các thông tin sau trong ticket hoặc tài liệu kỹ thuật:

~~~text
Use case:
  Tìm đơn CONFIRMED theo email prefix và mốc thời gian

JPA provider:
  Hibernate [phiên bản cụ thể]

Database:
  PostgreSQL [phiên bản cụ thể]

Criteria:
  PurchaseOrder root
  INNER JOIN customer
  status = :status
  createdAt >= :fromTime
  LOWER(email) LIKE :prefix
  ORDER BY createdAt DESC, id DESC
  offset + limit

Fixture:
  5 orders bao phủ điều kiện đúng/sai

Expected result:
  [E, A]

Observed result:
  [E, A]

Observed SQL:
  (Trích SQL template đã ẩn dữ liệu nhạy cảm)

Bind parameters:
  (Giá trị test và JDBC types)

Additional statements:
  (Số SELECT/UPDATE/DELETE ngoài query chính)

EXPLAIN summary:
  (Plan, index/scan, actual rows nếu có)

Conclusion:
  Đúng semantics / vấn đề cần sửa / rủi ro hiệu năng

Environment notes:
  Cache, flush mode, transaction, fetch plan, test isolation
~~~

Cách ghi chép này giúp người khác có thể **tái hiện phép kiểm chứng** khi nâng cấp Hibernate, đổi dialect hoặc thay đổi mapping. Nó hữu ích hơn việc lưu một ảnh chụp console không có tham số, dữ liệu đầu vào và phiên bản môi trường.

## 30. Tổng kết

Có ba nguyên tắc lớn:

**Thứ nhất, Criteria API mô tả truy vấn ở cấp entity, không phải SQL cuối cùng.** Provider chuyển nó thành SQL dựa trên metadata JPA, database dialect, fetch plan, parameter types và transaction state. Không có lời gọi `CriteriaQuery.toSql()` portable trong JPA.

**Thứ hai, kiểm chứng SQL phải kết hợp nhiều loại bằng chứng.** SQL log cho biết statement nào được phát; bind log cho biết tham số; assertion trên dữ liệu cho biết semantics; statement count giúp phát hiện N+1; `EXPLAIN` giúp hiểu index và execution plan. Chỉ nhìn một câu SQL chưa đủ để kết luận query đúng và hiệu quả.

**Thứ ba, hãy kiểm thử đặc tính ổn định thay vì hình thức SQL không ổn định.** Alias, whitespace và cú pháp phân trang có thể thay đổi theo provider/dialect, trong khi hợp đồng nghiệp vụ vẫn giống nhau. Với những điểm phụ thuộc thật sự vào SQL (fetch join, số statement, index, FK, bulk DML), cần đo trong môi trường tích hợp phù hợp.

Quy trình khuyến nghị là:

~~~text
Criteria -> thực thi query -> capture SQL + binds
         -> assert kết quả -> đánh giá JOIN/sort/pagination
         -> đếm SQL phụ -> EXPLAIN khi cần
         -> sửa đúng tầng -> ghi lại điều kiện tái hiện
~~~

**Kiểm chứng SQL được sinh từ truy vấn Criteria không nhằm thay thế abstraction của JPA, mà nhằm bảo đảm abstraction đó thực sự tạo ra hành vi database đúng với yêu cầu nghiệp vụ và hiệu năng của ứng dụng.**
