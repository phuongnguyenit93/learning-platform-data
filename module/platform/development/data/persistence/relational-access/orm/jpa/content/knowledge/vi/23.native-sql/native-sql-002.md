# Tạo và thực thi native query với tham số trong JPA

Trong các ứng dụng Java Persistence API (JPA), JPQL là công cụ quen thuộc để truy vấn entity. Nhưng nhiều hệ thống còn cần **SQL trực tiếp**: truy vấn báo cáo trên các bảng vật lý, sử dụng CTE hoặc window function, khai thác hàm đặc thù của PostgreSQL/MySQL/Oracle, hoặc thực thi một câu lệnh SQL đã được tối ưu và đo lường.

JPA cung cấp **native query** thông qua `EntityManager.createNativeQuery(...)`. Khi truyền dữ liệu đầu vào, ứng dụng nên dùng **parameter binding**, thay vì ghép giá trị người dùng thành một phần của câu SQL. Đây là trọng tâm của bài.

Ví dụ tối thiểu:

~~~java
Query query = entityManager.createNativeQuery(
    "SELECT id, order_number " +
    "FROM purchase_order " +
    "WHERE status = ?"
);

query.setParameter(1, "PAID");

List<?> rows = query.getResultList();
~~~

Đoạn này có bốn ý quan trọng:

- `purchase_order` và `order_number` là **tên bảng và cột thật trong database**, không phải tên entity/property Java.
- Dấu `?` trong SQL đại diện một **giá trị được bind**.
- `setParameter(1, "PAID")` gắn giá trị cho placeholder đầu tiên; chỉ số vị trí tham số của JPA bắt đầu bằng **1**.
- `getResultList()` thực thi truy vấn và lấy kết quả, còn định dạng kết quả phụ thuộc vào SELECT và result mapping.

Bài học hướng dẫn đầy đủ cách tạo, bind và thực thi native SELECT/INSERT/UPDATE/DELETE, nhận kết quả scalar, `Object[]`, entity hoặc DTO; xử lý tham số động, danh sách `IN`, `LIKE`, thời gian, pagination, SQL injection, transaction, persistence context và những giới hạn portability.

## 1. Native SQL khác JPQL ở đâu?

JPQL làm việc với mô hình đối tượng:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.status = :status",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.PAID);
~~~

Native SQL làm việc với schema vật lý:

~~~java
Query query = em.createNativeQuery(
    "SELECT o.id, o.order_number " +
    "FROM purchase_order o " +
    "WHERE o.status = ?"
);

query.setParameter(1, "PAID");
~~~

Bảng so sánh:

| Đặc điểm | JPQL | Native SQL |
|---|---|---|
| Tên trong truy vấn | Entity và thuộc tính Java | Bảng, cột SQL, alias |
| Ví dụ | `PurchaseOrder` / `o.totalAmount` | `purchase_order` / `o.total_amount` |
| JOIN | Theo association mapped | Qua FK và biểu thức SQL |
| Chuyển đổi query | Provider dịch JPQL thành SQL | SQL được ứng dụng cung cấp |
| Named parameters | Chuẩn JPA | Có provider hỗ trợ nhưng **không portable** trong native query |
| Positional parameters | Chuẩn JPA | Cách bind portable |
| Kết quả entity | Tự nhiên khi select entity | Phải chỉ rõ entity result mapping khi cần |
| Khả năng dùng hàm DB-specific | Bị giới hạn bởi JPQL/provider | Cao |
| Phụ thuộc schema/database | Ít hơn | Cao hơn |

**Native query vẫn là một JPA Query.** Nó có thể tham gia transaction và persistence context, hỗ trợ binding, pagination, hint và mapping kết quả. Nhưng SQL do ứng dụng viết nên JPA không thể bảo đảm mọi câu SQL di động giữa các DB.

### 1.1. Khi nào dùng native query?

Các tình huống hợp lý:

1. Cần **CTE**, **window function**, JSON/array operation hoặc full-text search không tiện diễn đạt bằng JPQL chuẩn.
2. Có câu SQL tối ưu báo cáo, được kiểm chứng với execution plan thực tế.
3. Cần chọn projection phức tạp từ nhiều bảng, nhất là khi dữ liệu không khớp trực tiếp một entity.
4. Cần SQL có điều kiện cập nhật rất cụ thể, và chấp nhận phải quản lý persistence context/optimistic locking.
5. Tích hợp legacy schema mà JPQL mapping trở nên bất tiện.

Không nên mặc định native SQL luôn nhanh hơn JPQL. Hai truy vấn logic giống nhau có thể có execution plan tương đương; hiệu năng phụ thuộc index, số row, join, database và fetch plan.

## 2. Luồng xử lý native query

~~~text
Java application
      |
      +-- SQL string có dấu ?
      |
      +-- EntityManager.createNativeQuery(sql)
      |
      +-- Query.setParameter(1, value)
      |
      v
JPA provider
      |
      +-- Chuẩn bị statement và bind giá trị
      +-- Thực thi qua JDBC
      +-- Ánh xạ kết quả nếu được yêu cầu
      |
      v
JDBC driver / Database
      |
      +-- SELECT: hàng kết quả
      +-- DML: số row bị tác động
      |
      v
Query.getResultList()
Query.getSingleResult()
Query.executeUpdate()
~~~

**Dấu `?` là placeholder cho một giá trị**, không phải lời yêu cầu ghép giá trị vào câu SQL ở tầng Java. Provider/driver thực hiện cơ chế binding theo khả năng của nó. Không nên tự chuyển các giá trị đầu vào thành một mảnh SQL literal.

Một Query được tạo ra chưa có nghĩa SQL đã được thực thi:

~~~java
Query q = em.createNativeQuery(
    "SELECT id FROM purchase_order WHERE status = ?"
);

q.setParameter(1, "PAID");

// Đến đây mới yêu cầu thực thi SELECT:
List<?> ids = q.getResultList();
~~~

## 3. Schema và entity minh họa

Bài học sử dụng mô hình Customer và PurchaseOrder:

~~~text
customer
    id (PK)
    email (UNIQUE)
    display_name

purchase_order
    id (PK)
    customer_id (FK -> customer.id)
    order_number (UNIQUE)
    status
    total_amount
    created_at
    version
~~~

DDL minh họa theo PostgreSQL:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_positive_total CHECK (total_amount >= 0)
);

CREATE INDEX idx_order_status_created
ON purchase_order(status, created_at DESC, id DESC);
~~~

Dữ liệu thử:

~~~text
customer
id | email                 | display_name
---+-----------------------+-------------
 1 | an@example.test       | Nguyễn An
 2 | binh@example.test     | Trần Bình

purchase_order
id | customer_id | order_number | status | total_amount
---+-------------+--------------+--------+-------------
10 | 1           | ORD-0010     | PAID   | 500000.00
11 | 1           | ORD-0011     | NEW    | 200000.00
12 | 2           | ORD-0012     | PAID   | 900000.00
~~~

Entity Java rút gọn:

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
~~~

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 254)
    private String email;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    protected Customer() {
    }

    public Long getId() {
        return id;
    }
}
~~~

Các entity này minh họa mapping, chưa phải toàn bộ domain model. Dự án thật cần constructor nghiệp vụ, methods, validation, migration và kiểu timestamp tương thích provider/driver.

## 4. Ba overload quan trọng của `createNativeQuery`

JPA cung cấp các cách tạo query tiêu biểu:

~~~java
Query q1 = em.createNativeQuery(sql);

Query q2 = em.createNativeQuery(
    sql,
    PurchaseOrder.class
);

Query q3 = em.createNativeQuery(
    sql,
    "OrderSummaryMapping"
);
~~~

Ý nghĩa:

| API | Dùng khi |
|---|---|
| `createNativeQuery(sql)` | Kết quả scalar hoặc nhiều cột, không có entity mapping tường minh |
| `createNativeQuery(sql, resultClass)` | Kết quả ánh xạ thành một entity/result class được hỗ trợ |
| `createNativeQuery(sql, resultSetMappingName)` | Kết quả sử dụng mapping đã đăng ký bằng `@SqlResultSetMapping` |

Một số JPA provider/phiên bản cung cấp generic API bổ sung, nhưng trong JPA tiêu chuẩn, native query thường được xử lý qua `Query` chứ không tự trở thành `TypedQuery<PurchaseOrder>` chỉ vì có câu SELECT.

### 4.1. Khi chưa cung cấp mapping

SQL một cột thường trả danh sách scalar; SQL nhiều cột thường trả hàng `Object[]`. Với hàm aggregate, kiểu số thực tế có thể tùy provider/driver.

### 4.2. Khi cung cấp entity result

Provider cần những cột mapped cần thiết, đặc biệt ID, version và FK. Nếu SELECT thiếu cột, quá trình materialize entity có thể không đúng hoặc ném exception.

### 4.3. Khi cung cấp DTO mapping

Ứng dụng có thể định nghĩa alias, kiểu và thứ tự constructor. Điều này phù hợp với API/reporting chỉ cần một số trường.

## 5. Positional parameters: Cách làm portable

Với native SQL:

~~~sql
SELECT id, order_number
FROM purchase_order
WHERE status = ?
  AND customer_id = ?
  AND total_amount >= ?
~~~

Binding:

~~~java
Query q = em.createNativeQuery(sql);

q.setParameter(1, "PAID");
q.setParameter(2, 1L);
q.setParameter(3, new BigDecimal("500000.00"));
~~~

Chỉ số `1`, `2` và `3` tính theo thứ tự dấu hỏi trong câu SQL.

~~~text
SQL:     WHERE status = ? AND customer_id = ? AND total_amount >= ?
                           1                   2                    3

Java:    setParameter(1, "PAID")
         setParameter(2, 1L)
         setParameter(3, BigDecimal)
~~~

### 5.1. JPA dùng vị trí bắt đầu từ 1

Sai:

~~~java
q.setParameter(0, "PAID");
~~~

Đúng:

~~~java
q.setParameter(1, "PAID");
~~~

### 5.2. Hai placeholder với cùng một giá trị vẫn phải bind hai lần

~~~java
Query q = em.createNativeQuery(
    "SELECT id FROM purchase_order " +
    "WHERE customer_id = ? OR approved_by_customer_id = ?"
);

q.setParameter(1, customerId);
q.setParameter(2, customerId);
~~~

Ví dụ giả định schema có thêm `approved_by_customer_id`. Cùng một giá trị logic không biến hai placeholder thành một placeholder chung.

### 5.3. Cú pháp `?1` khác với dấu `?`

JPQL có positional parameter đánh số như `?1`. Một số provider/framework cũng nhận `?1` trong native SQL, nhưng nếu muốn một mẫu JPA native binding portable, hãy dùng placeholder JDBC-style `?` và bind các vị trí JPA từ 1.

Nếu framework của bạn hỗ trợ `?1` cho native SQL, đó là hành vi cần kiểm chứng theo provider/phiên bản, không nên suy rộng thành mọi implementation.

### 5.4. Thứ tự đặt tham số

Việc gọi `setParameter(2, ...)` trước `setParameter(1, ...)` không phải là lỗi nếu cả hai vị trí cuối cùng đều đúng và được bind trước khi thực thi. Tuy nhiên, code bind tuần tự 1, 2, 3 thường dễ bảo trì hơn.

## 6. Named parameters trong native query

Với JPQL, named parameters là chuẩn:

~~~java
em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.status = :status"
).setParameter("status", OrderStatus.PAID);
~~~

Với native SQL, nhiều provider như Hibernate hỗ trợ:

~~~java
Query q = em.createNativeQuery(
    "SELECT id FROM purchase_order WHERE status = :status"
);

q.setParameter("status", "PAID");
~~~

**Nhưng JPA không bảo đảm named parameter binding portable đối với native queries.** Chỉ positional parameter binding là lựa chọn portable theo hợp đồng cơ bản của chuẩn.

Do đó:

- Nếu dự án phải chạy với nhiều JPA provider, ưu tiên `WHERE status = ?`.
- Nếu dự án cố định Hibernate/provider hỗ trợ, named parameters có thể giúp SQL dài dễ đọc hơn.
- Phải kiểm thử lại nếu nâng cấp provider/đổi DB.
- Không dùng việc named parameter “chạy ở máy tôi” làm bằng chứng cho tính di động của code.

### 6.1. Dấu hai chấm có thể xung đột cú pháp DB

PostgreSQL có toán tử ép kiểu:

~~~sql
SELECT some_value::integer
~~~

Một parser named parameter có thể nhầm dấu `:` thành điểm mở đầu tham số. Nếu xảy ra vấn đề, có thể dùng cú pháp như:

~~~sql
SELECT CAST(some_value AS INTEGER)
~~~

Tùy database, `CAST` có thể cần điều chỉnh. Đừng “khắc phục” bằng cách ghép trực tiếp giá trị người dùng vào SQL.

## 7. Bind tham số để tránh SQL injection

Không nên:

~~~java
String sql =
    "SELECT id FROM purchase_order " +
    "WHERE order_number = '" + userInput + "'";

Query q = em.createNativeQuery(sql);
~~~

`userInput` có thể chứa dấu nháy đơn hoặc nội dung phá cấu trúc câu lệnh.

Nên:

~~~java
Query q = em.createNativeQuery(
    "SELECT id FROM purchase_order WHERE order_number = ?"
);

q.setParameter(1, userInput);
~~~

Giá trị được chuyển như **data**, không phải ghép vào cú pháp SQL.

### 7.1. Tại sao tự escape dấu nháy không đủ?

Cố tự thay `'` thành `''` không phải giải pháp tổng quát cho mọi kiểu SQL, dialect, encoding và loại literal. Parameter binding giúp tránh phải quản lý phần lớn các chi tiết đó bằng tay.

### 7.2. Parameter không thay tên bảng hay tên cột

Câu sau không phải cách portable để chọn bảng:

~~~sql
SELECT * FROM ?
~~~

Tương tự:

~~~sql
ORDER BY ?
~~~

không có nghĩa giá trị bind sẽ trở thành tên cột SQL động. Placeholder dành cho **giá trị biểu thức**, không dùng như một mảnh cú pháp/identifier.

Muốn sắp xếp động, chỉ dùng whitelist:

~~~java
public enum OrderSort {
    CREATED_AT,
    TOTAL_AMOUNT,
    ORDER_NUMBER
}
~~~

~~~java
String column = switch (sort) {
    case CREATED_AT -> "created_at";
    case TOTAL_AMOUNT -> "total_amount";
    case ORDER_NUMBER -> "order_number";
};

String direction = descending ? "DESC" : "ASC";

String sql =
    "SELECT id, order_number FROM purchase_order " +
    "WHERE status = ? " +
    "ORDER BY " + column + " " + direction + ", id DESC";
~~~

`column` và `direction` đều được sinh từ tập giá trị cố định server-side, không lấy một đoạn SQL bất kỳ do client gửi.

### 7.3. Injection protection khác authorization

Dù mọi tham số đã bind an toàn, query vẫn có thể làm lộ dữ liệu nếu thiếu điều kiện quyền truy cập.

~~~java
Query q = em.createNativeQuery(
    "SELECT id, order_number " +
    "FROM purchase_order " +
    "WHERE id = ? AND customer_id = ?"
);

q.setParameter(1, orderId);
q.setParameter(2, authenticatedCustomerId);
~~~

`authenticatedCustomerId` phải đến từ identity/security context đã được server xác minh. Không tin một ID do người dùng nhập như một bằng chứng sở hữu.

## 8. Bind các kiểu dữ liệu phổ biến

Ví dụ một query với ba điều kiện:

~~~java
Query q = em.createNativeQuery(
    "SELECT id FROM purchase_order " +
    "WHERE status = ? " +
    "AND customer_id = ? " +
    "AND total_amount >= ?"
);

q.setParameter(1, "PAID");
q.setParameter(2, 42L);
q.setParameter(3, new BigDecimal("500000.00"));
~~~

### 8.1. String và enum

Với entity dùng:

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

và schema lưu chuỗi `NEW`, `PAID`, `CANCELLED`, native query có thể bind:

~~~java
q.setParameter(1, OrderStatus.PAID.name());
~~~

Không mặc định rằng native SQL tự biết một dấu `?` tương ứng field có `@Enumerated` hay `AttributeConverter`. Nếu database dùng enum native hoặc giá trị số/chuỗi chuyển đổi riêng, cách bind phải tương thích encoding thực tế.

### 8.2. Long và kiểu số

~~~java
q.setParameter(2, Long.valueOf(42));
~~~

Dùng kiểu Java tương ứng cột BIGINT. Khi DB trả kết quả numeric scalar, kiểu Java có thể không chính xác là Long dù parameter được bind bằng Long.

### 8.3. BigDecimal

~~~java
q.setParameter(
    3,
    new BigDecimal("500000.00")
);
~~~

Với số tiền, tránh dùng `double` khi cần độ chính xác decimal. Kiểm tra precision/scale của cột theo migration.

### 8.4. Boolean

~~~java
q.setParameter(1, true);
~~~

phù hợp trong nhiều trường hợp cột BOOLEAN. Với schema legacy dùng `Y/N` hoặc `0/1`, phải bind đúng biểu diễn trong DB.

### 8.5. Ngày giờ

Ví dụ cần lọc trong khoảng:

~~~text
created_at >= 2026-01-01T00:00:00Z
created_at <  2026-02-01T00:00:00Z
~~~

Java:

~~~java
Instant from = Instant.parse(
    "2026-01-01T00:00:00Z"
);

Instant untilExclusive = Instant.parse(
    "2026-02-01T00:00:00Z"
);
~~~

Query:

~~~java
Query q = em.createNativeQuery(
    "SELECT id, order_number FROM purchase_order " +
    "WHERE created_at >= ? AND created_at < ?"
);

q.setParameter(1, Timestamp.from(from));
q.setParameter(2, Timestamp.from(untilExclusive));
~~~

`Timestamp` là một cách bind thường dùng với JDBC, nhưng xử lý `TIMESTAMP WITH TIME ZONE` phụ thuộc mapping, provider và driver. Khi sử dụng `Instant`, `OffsetDateTime` hoặc kiểu JDBC 4.2, hãy kiểm tra độ chính xác/timezone trên stack thực tế.

**Khoảng nửa mở** `[from, untilExclusive)` thường tránh lỗi cuối ngày so với tự tạo `23:59:59.999...`.

### 8.6. Chuyển ngày local sang thời điểm chính xác

Nếu giao diện dùng ngày theo múi giờ Việt Nam:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant start = LocalDate.of(2026, 1, 1)
    .atStartOfDay(zone)
    .toInstant();

Instant end = LocalDate.of(2026, 2, 1)
    .atStartOfDay(zone)
    .toInstant();
~~~

Chuyển đổi phải thuộc hợp đồng nghiệp vụ, không để repository tự đoán LocalDate là UTC.

## 9. Null không được xử lý như phép bằng thông thường

SQL:

~~~sql
WHERE some_column = ?
~~~

với parameter null **không tương đương**:

~~~sql
WHERE some_column IS NULL
~~~

Theo SQL three-valued logic, so sánh bằng với NULL không trả TRUE.

Nếu cần tìm row có giá trị null, dùng `IS NULL`. Nếu filter không được cung cấp, thường **bỏ điều kiện** khỏi câu SQL. Nếu muốn bind null có kiểu rõ ràng, một số provider/driver cần thêm thông tin kiểu SQL hoặc cast tương thích.

Ví dụ filter tùy chọn:

~~~java
StringBuilder sql = new StringBuilder(
    "SELECT id FROM purchase_order WHERE status = ?"
);

List<Object> args = new ArrayList<>();
args.add("PAID");

if (customerId != null) {
    sql.append(" AND customer_id = ?");
    args.add(customerId);
}
~~~

Khi bind:

~~~java
Query q = em.createNativeQuery(sql.toString());

for (int i = 0; i < args.size(); i++) {
    q.setParameter(i + 1, args.get(i));
}
~~~

Nhờ đó, một filter null không bị biến thành điều kiện `customer_id = NULL` gây sai kết quả.

## 10. SELECT một cột: Scalar result

~~~java
Query q = em.createNativeQuery(
    "SELECT order_number " +
    "FROM purchase_order WHERE id = ?"
);

q.setParameter(1, 10L);

String number = (String) q.getSingleResult();
~~~

Vì chọn một cột dạng text, kết quả thường là một String scalar, không phải `Object[]`.

### 10.1. `getSingleResult()` không có row

Nếu không có kết quả, JPA thường ném `NoResultException`. Nếu có hơn một hàng, có thể ném `NonUniqueResultException`.

Ví dụ:

~~~java
public Optional<String> findOrderNumber(
        EntityManager em, long orderId) {

    Query q = em.createNativeQuery(
        "SELECT order_number " +
        "FROM purchase_order WHERE id = ?"
    );

    q.setParameter(1, orderId);

    try {
        return Optional.of(
            (String) q.getSingleResult()
        );
    } catch (NoResultException ex) {
        return Optional.empty();
    }
}
~~~

Ví dụ giả định `order_number` là NOT NULL. Với cột nullable, cần phân biệt “không có row” và “có row chứa NULL”.

### 10.2. `getResultList()` khi không có row

`getResultList()` trả danh sách rỗng, không phải ném `NoResultException` chỉ vì không tìm thấy kết quả.

## 11. SELECT COUNT và kiểu số trả về

~~~java
Query q = em.createNativeQuery(
    "SELECT COUNT(*) " +
    "FROM purchase_order WHERE status = ?"
);

q.setParameter(1, "PAID");

Number raw = (Number) q.getSingleResult();
long count = raw.longValue();
~~~

Native `COUNT(*)` có thể được driver/provider trả dưới dạng `Long`, `BigInteger` hoặc kiểu `Number` khác. Vì thế:

~~~java
Long count = (Long) q.getSingleResult();
~~~

không phải giả định an toàn cho mọi môi trường khi không có result mapping cụ thể.

Ngoài ra, `COUNT(*)` trả về một scalar aggregate; đừng cast kết quả thành `PurchaseOrder`.

## 12. SELECT nhiều cột: Object[]

~~~java
Query q = em.createNativeQuery(
    "SELECT id, order_number, total_amount " +
    "FROM purchase_order " +
    "WHERE status = ? " +
    "ORDER BY id"
);

q.setParameter(1, "PAID");

List<?> rows = q.getResultList();
~~~

Mỗi hàng thông thường là `Object[]`:

~~~java
for (Object value : rows) {
    Object[] columns = (Object[]) value;

    long id = ((Number) columns[0]).longValue();
    String number = (String) columns[1];
    BigDecimal amount = (BigDecimal) columns[2];

    System.out.println(id + " " + number + " " + amount);
}
~~~

`BigDecimal` phù hợp với cột NUMERIC(14,2) trong nhiều provider/driver, nhưng vẫn nên kiểm tra kiểu thực tế.

### 12.1. Thứ tự cột là hợp đồng

~~~text
SELECT id, order_number, total_amount

columns[0] = id
columns[1] = order_number
columns[2] = total_amount
~~~

Nếu đổi thứ tự trong SQL mà không sửa Java, mapping theo index có thể lỗi. Với query nhiều cột hoặc tái sử dụng lâu dài, nên tạo DTO rõ ràng hoặc dùng `@SqlResultSetMapping`.

### 12.2. Scalar projection không phải entity managed

Nếu chỉ SELECT ba scalar columns, JPA không tự tạo một entity PurchaseOrder đầy đủ có dirty checking. Đây là dữ liệu projection. Nếu muốn entity lifecycle, cần ánh xạ entity.

## 13. Materialize native result thành entity

JPA có overload:

~~~java
Query q = em.createNativeQuery(
    "SELECT o.* " +
    "FROM purchase_order o " +
    "WHERE o.status = ?",
    PurchaseOrder.class
);

q.setParameter(1, "PAID");

List<?> results = q.getResultList();

for (Object item : results) {
    PurchaseOrder order = (PurchaseOrder) item;
    System.out.println(order.getOrderNumber());
}
~~~

`resultClass = PurchaseOrder.class` yêu cầu provider ánh xạ result set về entity.

### 13.1. Cần đủ cột mapped

PurchaseOrder gồm:

- `id`.
- `customer_id` cho association Customer.
- `order_number`.
- `status`.
- `total_amount`.
- `created_at`.
- `version`.

Câu:

~~~sql
SELECT id, order_number
FROM purchase_order
~~~

có thể **không đủ** để materialize PurchaseOrder đầy đủ. Provider có thể báo thiếu cột hoặc có hành vi không phù hợp khi hydrate entity. Dùng SELECT đầy đủ các cột cần thiết hoặc chuyển sang projection DTO nếu chỉ cần một phần.

### 13.2. Cẩn trọng với SELECT * khi JOIN

~~~sql
SELECT *
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id
~~~

có thể trả hai cột tên `id`, gây nhập nhằng mapping. Khi kết quả là entity từ một bảng, hãy chọn rõ các cột của entity hoặc dùng alias/result mapping.

### 13.3. Entity nhận từ native query có thể đang managed

Nếu query ánh xạ thành entity, JPA có thể trả object đã tồn tại trong identity map của persistence context. Vì vậy:

- Không suy ra native SELECT luôn tạo instance Java mới.
- Không suy ra entity managed cũ được refresh mọi field chỉ vì SQL đã chạy.
- Muốn làm mới state từ DB có thể cần `em.refresh(...)` hoặc `clear()/reload` đúng ngữ cảnh.
- Những thay đổi chưa flush cần được xử lý trước khi clear/refresh để tránh mất dữ liệu.

## 14. Ánh xạ native result thành DTO

Ví dụ DTO Java record:

~~~java
package com.example.shop.dto;

import java.math.BigDecimal;

public record OrderSummary(
    Long id,
    String orderNumber,
    BigDecimal totalAmount
) {}
~~~

Có thể map thủ công từ `Object[]`, hoặc dùng `@SqlResultSetMapping` với `@ConstructorResult` để giảm phụ thuộc vào index ở nhiều nơi.

### 14.1. Đăng ký SqlResultSetMapping

Đặt annotation trên entity được JPA nhận diện:

~~~java
@Entity
@Table(name = "purchase_order")
@SqlResultSetMapping(
    name = "OrderSummaryMapping",
    classes = @ConstructorResult(
        targetClass = OrderSummary.class,
        columns = {
            @ColumnResult(name = "order_id", type = Long.class),
            @ColumnResult(name = "number", type = String.class),
            @ColumnResult(name = "amount", type = BigDecimal.class)
        }
    )
)
public class PurchaseOrder {
    // Các field và mapping entity đầy đủ.
}
~~~

Ví dụ chỉ trình bày những annotation liên quan; `PurchaseOrder` cần mapping entity như phần trên.

### 14.2. Query với alias khớp mapping

~~~java
Query q = em.createNativeQuery(
    "SELECT o.id AS order_id, " +
    "       o.order_number AS number, " +
    "       o.total_amount AS amount " +
    "FROM purchase_order o " +
    "WHERE o.status = ?",
    "OrderSummaryMapping"
);

q.setParameter(1, "PAID");

List<?> rows = q.getResultList();

for (Object value : rows) {
    OrderSummary summary = (OrderSummary) value;
    System.out.println(summary);
}
~~~

Các tên alias và thứ tự cột trong `@ConstructorResult` phải tương thích constructor DTO. `@ColumnResult.type` giúp khai báo kiểu kết quả mong muốn; khả năng chuyển đổi vẫn phụ thuộc vào DB/provider.

### 14.3. Lợi ích của DTO

- Không cần load toàn bộ cột của entity.
- Không tạo nhiều managed objects không cần thiết.
- Hợp đồng response API rõ ràng.
- Giảm rủi ro lazy loading khi JSON serialization.
- Có thể kết hợp dữ liệu từ nhiều bảng hoặc aggregate.
- Dễ kiểm thử alias/types sau khi SQL thay đổi.

### 14.4. EntityResult và FieldResult

Với mapping phức tạp hơn, JPA còn có `@EntityResult` và `@FieldResult` để xác định alias cột cho entity. Điều này có ích khi query JOIN nhiều bảng hoặc alias không khớp tên mapping gốc.

Không mặc định `SELECT a.*, b.*` sẽ tự tạo hai entity chuẩn nếu không khai báo rõ ý nghĩa từng cột.

## 15. Named native query

Một SQL dùng nhiều lần có thể được khai báo bằng `@NamedNativeQuery`:

~~~java
@Entity
@Table(name = "purchase_order")
@NamedNativeQuery(
    name = "PurchaseOrder.findPaidNative",
    query = "SELECT o.* " +
            "FROM purchase_order o " +
            "WHERE o.status = ? " +
            "ORDER BY o.created_at DESC",
    resultClass = PurchaseOrder.class
)
public class PurchaseOrder {
    // Entity mapping.
}
~~~

Thực thi:

~~~java
Query q = em.createNamedQuery(
    "PurchaseOrder.findPaidNative"
);

q.setParameter(1, "PAID");

List<?> orders = q.getResultList();
~~~

Phân biệt:

- `@NamedQuery`: nội dung là **JPQL**.
- `@NamedNativeQuery`: nội dung là **native SQL**.

Đưa SQL vào named native query không làm nó portable giữa mọi DB; nó chỉ làm rõ tên, metadata và nơi đăng ký query.

### 15.1. Query hint trong named native query

Có thể khai báo `@QueryHint` cho timeout hoặc option provider-specific, nhưng phải xem phiên bản JPA/provider/driver. Một hint được chấp nhận không có nghĩa DB chắc chắn áp dụng đúng theo mong đợi.

## 16. Thêm điều kiện động và bind positional parameters

Một API tìm kiếm có các filter tùy chọn: status, customerId và minTotal.

~~~java
public List<?> searchOrders(
        EntityManager em,
        String status,
        Long customerId,
        BigDecimal minTotal) {

    StringBuilder sql = new StringBuilder(
        "SELECT id, order_number, total_amount " +
        "FROM purchase_order WHERE 1 = 1"
    );

    List<Object> params = new ArrayList<>();

    if (status != null) {
        sql.append(" AND status = ?");
        params.add(status);
    }

    if (customerId != null) {
        sql.append(" AND customer_id = ?");
        params.add(customerId);
    }

    if (minTotal != null) {
        sql.append(" AND total_amount >= ?");
        params.add(minTotal);
    }

    sql.append(" ORDER BY id DESC");

    Query q = em.createNativeQuery(sql.toString());

    for (int i = 0; i < params.size(); i++) {
        q.setParameter(i + 1, params.get(i));
    }

    return q.getResultList();
}
~~~

Ở đây, phần SQL được ghép là **fragment cố định do server định nghĩa**. Giá trị động luôn được đưa vào qua `setParameter`.

### 16.1. Tại sao cách này không giống nối input vào SQL?

Có khác biệt lớn giữa:

~~~java
sql.append(" AND status = ?");
params.add(status);
~~~

và:

~~~java
sql.append(" AND status = '" + status + "'");
~~~

Cách đầu bind giá trị, còn cách sau ghép literal trực tiếp và có rủi ro SQL injection.

### 16.2. Luôn phân biệt null với giá trị thực

- `status == null`: không thêm điều kiện.
- `minTotal == BigDecimal.ZERO`: có thể là một điều kiện hợp lệ.
- `customerId == 0`: có thể là input sai, không tự bỏ qua.
- Danh sách filter rỗng: semantics phải được định nghĩa.
- Nếu tenant restriction là bắt buộc, **không** để client được bỏ điều kiện tenant.

### 16.3. Khi query động quá phức tạp

Nếu có nhiều nhóm AND/OR, JOIN, EXISTS và COUNT dùng cùng bộ filter, Criteria API hoặc một SQL query builder chuyên dụng có thể dễ duy trì hơn nối chuỗi thủ công. Native SQL vẫn phù hợp nếu cần tính năng DB đặc thù, nhưng phải thiết kế bộ lọc và tham số rõ ràng.

## 17. Native IN với danh sách tham số

Giả sử cần tìm Order có ID trong danh sách:

~~~java
List<Long> ids = List.of(10L, 11L, 12L);
~~~

SQL:

~~~sql
SELECT id, order_number
FROM purchase_order
WHERE id IN (?, ?, ?)
~~~

Không được mặc định rằng:

~~~java
Query q = em.createNativeQuery(
    "SELECT id FROM purchase_order WHERE id IN (?)"
);

q.setParameter(1, ids);
~~~

sẽ được mọi JPA provider tự mở rộng thành ba parameter. **Native collection/list parameter expansion không được bảo đảm portable.**

### 17.1. Tạo placeholder theo số phần tử

~~~java
public List<?> findByIds(
        EntityManager em,
        List<Long> ids) {

    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    if (ids.size() > 500) {
        throw new IllegalArgumentException(
            "Too many IDs"
        );
    }

    String placeholders = String.join(
        ", ",
        Collections.nCopies(ids.size(), "?")
    );

    Query q = em.createNativeQuery(
        "SELECT id, order_number " +
        "FROM purchase_order " +
        "WHERE id IN (" + placeholders + ") " +
        "ORDER BY id"
    );

    for (int i = 0; i < ids.size(); i++) {
        q.setParameter(i + 1, ids.get(i));
    }

    return q.getResultList();
}
~~~

Chỉ **số lượng dấu ?** được tạo từ kích thước list; giá trị ID luôn được bind.

### 17.2. List rỗng cần quy ước

`IN ()` là SQL không hợp lệ ở nhiều DB. Cần xác định:

- List rỗng nghĩa “không ID nào” → trả List rỗng.
- List rỗng nghĩa “không lọc” → bỏ mệnh đề IN.
- List rỗng không hợp lệ → validation error.

Không vô tình đổi list rỗng thành truy vấn trả tất cả bản ghi.

### 17.3. List quá lớn

Một danh sách hàng chục nghìn ID có thể vượt giới hạn bind parameters, gây SQL dài hoặc plan kém. Có thể cần batch, bảng tạm/staging, join bảng tham chiếu, array/table-valued parameters hoặc extension của provider/DB đã được kiểm chứng.

## 18. LIKE với tham số và ký tự wildcard

Tìm mã đơn có chứa từ khóa:

~~~java
Query q = em.createNativeQuery(
    "SELECT id, order_number " +
    "FROM purchase_order " +
    "WHERE LOWER(order_number) LIKE ? " +
    "ORDER BY id"
);

String keyword = "ord";

q.setParameter(
    1,
    "%" + keyword.toLowerCase(Locale.ROOT) + "%"
);
~~~

Parameter binding an toàn cho SQL structure. Nhưng `%` và `_` trong chính keyword vẫn được hiểu là wildcard của LIKE.

### 18.1. Tìm chuỗi literal có dấu `%`

Nếu người dùng gõ `50%` và muốn khớp dấu `%` thật, dùng escape rule:

~~~java
private static String escapeLike(String input) {
    return input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
~~~

SQL:

~~~sql
SELECT id, order_number
FROM purchase_order
WHERE LOWER(order_number) LIKE ? ESCAPE '!'
~~~

Bind:

~~~java
String pattern =
    "%" + escapeLike(keyword.toLowerCase(Locale.ROOT)) + "%";

q.setParameter(1, pattern);
~~~

Cú pháp `ESCAPE '!'` cần được kiểm tra trên database mục tiêu. Đây là vấn đề **ngữ nghĩa LIKE**, không phải thay thế cho parameter binding.

### 18.2. LIKE không nhất thiết nhanh

Mẫu `'%abc%'` có wildcard đầu chuỗi có thể khó dùng B-tree index thông thường. Với lượng dữ liệu lớn, cân nhắc full-text/trigram index hoặc search engine theo yêu cầu.

## 19. Phân trang native query

Native `Query` hỗ trợ các API JPA:

~~~java
q.setFirstResult(offset);
q.setMaxResults(pageSize);
~~~

Ví dụ:

~~~java
Query q = em.createNativeQuery(
    "SELECT id, order_number, total_amount " +
    "FROM purchase_order " +
    "WHERE status = ? " +
    "ORDER BY created_at DESC, id DESC"
);

q.setParameter(1, "PAID");

int page = 0;
int pageSize = 20;

q.setFirstResult(page * pageSize);
q.setMaxResults(pageSize);

List<?> rows = q.getResultList();
~~~

Provider/dialect có thể chuyển pagination thành LIMIT/OFFSET, FETCH FIRST hoặc kỹ thuật khác.

### 19.1. Phải có ORDER BY ổn định

Không có ORDER BY, database không cam kết thứ tự hàng. Khi phân trang, người dùng có thể nhận những hàng khác nhau giữa các lần đọc.

Nên dùng:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

`id` là tie-breaker khi nhiều đơn có cùng `created_at`. Ngay cả khi có sort ổn định, dữ liệu insert/update đồng thời vẫn có thể làm trang offset dịch chuyển; keyset pagination có thể phù hợp với feed lớn.

### 19.2. Validate và tránh overflow

~~~java
if (page < 0 || pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException("Invalid pagination");
}

int offset = Math.multiplyExact(page, pageSize);

q.setFirstResult(offset);
q.setMaxResults(pageSize);
~~~

Giới hạn số row bảo vệ memory/latency. Mốc 100 chỉ là ví dụ, cần điều chỉnh theo use case.

### 19.3. Tự viết LIMIT/OFFSET có thể phụ thuộc DB

~~~sql
LIMIT ? OFFSET ?
~~~

phổ biến ở một số database nhưng không có syntax giống nhau ở mọi DB. Nếu muốn giữ logic pagination trong API JPA, ưu tiên `setFirstResult`/`setMaxResults` khi provider hỗ trợ native query đúng trên dialect đang dùng.

## 20. COUNT riêng cho phân trang

Data query:

~~~java
Query data = em.createNativeQuery(
    "SELECT id, order_number FROM purchase_order " +
    "WHERE status = ? " +
    "ORDER BY created_at DESC, id DESC"
);

data.setParameter(1, "PAID");
data.setFirstResult(0);
data.setMaxResults(20);
~~~

Count query:

~~~java
Query countQuery = em.createNativeQuery(
    "SELECT COUNT(*) FROM purchase_order " +
    "WHERE status = ?"
);

countQuery.setParameter(1, "PAID");

long total =
    ((Number) countQuery.getSingleResult()).longValue();
~~~

Nếu data query có thêm filter customerId, date range hoặc tenant, count query phải áp dụng cùng logic. Đừng để UI hiển thị 1.000 trang nhưng danh sách thực tế chỉ có vài row vì count bị thiếu điều kiện.

### 20.1. JOIN to-many có thể đếm trùng

~~~sql
SELECT COUNT(*)
FROM purchase_order o
JOIN order_line l ON l.order_id = o.id
WHERE l.product_id = ?
~~~

Nếu một Order có nhiều line khớp, COUNT(*) đếm nhiều row JOIN. Nếu muốn số Order duy nhất, cần `COUNT(DISTINCT o.id)` hoặc cấu trúc EXISTS phù hợp.

~~~sql
SELECT COUNT(*)
FROM purchase_order o
WHERE EXISTS (
    SELECT 1
    FROM order_line l
    WHERE l.order_id = o.id
      AND l.product_id = ?
)
~~~

## 21. JOIN và kết quả báo cáo

Ví dụ lấy thông tin đơn kèm tên khách hàng:

~~~java
Query q = em.createNativeQuery(
    "SELECT o.order_number, " +
    "       c.display_name, " +
    "       o.total_amount " +
    "FROM purchase_order o " +
    "JOIN customer c ON c.id = o.customer_id " +
    "WHERE o.status = ? " +
    "ORDER BY o.created_at DESC"
);

q.setParameter(1, "PAID");
~~~

Mapping thủ công:

~~~java
for (Object value : q.getResultList()) {
    Object[] row = (Object[]) value;

    String orderNumber = (String) row[0];
    String customerName = (String) row[1];
    BigDecimal total = (BigDecimal) row[2];

    // Tạo DTO hoặc tính toán báo cáo.
}
~~~

Có thể định nghĩa:

~~~java
public record OrderReportRow(
    String orderNumber,
    String customerName,
    BigDecimal total
) {}
~~~

và chuyển mỗi hàng thành record. Với báo cáo lớn, nên dùng result mapping hoặc lớp converter nhất quán, không để controller phụ thuộc trực tiếp vào `Object[]`.

## 22. CTE và window function với parameter binding

Một lợi ích nổi bật của native SQL là tận dụng khả năng database.

Ví dụ PostgreSQL: chọn top N đơn PAID theo giá trị của từng khách hàng.

~~~sql
WITH ranked_orders AS (
    SELECT
        o.id,
        o.order_number,
        o.customer_id,
        o.total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.total_amount DESC, o.id DESC
        ) AS amount_rank
    FROM purchase_order o
    WHERE o.status = ?
)
SELECT
    id,
    order_number,
    customer_id,
    total_amount,
    amount_rank
FROM ranked_orders
WHERE amount_rank <= ?
ORDER BY customer_id, amount_rank
~~~

JPA:

~~~java
Query q = em.createNativeQuery(sql);

q.setParameter(1, "PAID");
q.setParameter(2, topN);

List<?> rows = q.getResultList();
~~~

Ở đây `ROW_NUMBER() OVER (...)` là SQL analytics, còn `topN` được bind như giá trị. Đây không phải ví dụ portable cho mọi database; phải kiểm tra hỗ trợ cú pháp và result types trên DB mục tiêu.

## 23. Native UPDATE có điều kiện

Ví dụ hủy một đơn NEW:

~~~java
Query q = em.createNativeQuery(
    "UPDATE purchase_order " +
    "SET status = ? " +
    "WHERE id = ? AND status = ?"
);

q.setParameter(1, OrderStatus.CANCELLED.name());
q.setParameter(2, orderId);
q.setParameter(3, OrderStatus.NEW.name());

int updated = q.executeUpdate();
~~~

Một số ý nghĩa:

- `updated = 1`: một row khớp điều kiện đã được update.
- `updated = 0`: có thể không tồn tại ID hoặc trạng thái không còn NEW.
- Cần transaction phù hợp để thực hiện DML.
- `executeUpdate()` không đồng nghĩa transaction đã commit.
- Native UPDATE không tự chạy các entity setter/callback như cập nhật entity managed.
- Managed entity đã load trước đó có thể giữ state cũ.

### 23.1. Resource-local transaction

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Query q = em.createNativeQuery(
        "UPDATE purchase_order " +
        "SET status = ? WHERE id = ? AND status = ?"
    );

    q.setParameter(1, "CANCELLED");
    q.setParameter(2, orderId);
    q.setParameter(3, "NEW");

    int updated = q.executeUpdate();

    tx.commit();

    System.out.println("Updated: " + updated);
} catch (RuntimeException original) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackError) {
            original.addSuppressed(rollbackError);
        }
    }
    throw original;
} finally {
    em.close();
}
~~~

Trong Spring/JTA container-managed transaction, dùng transaction manager/interceptor thay vì tự gọi `em.getTransaction().begin()` trên JTA EntityManager.

### 23.2. Affected rows không chứng minh commit

Có thể:

~~~text
BEGIN
  UPDATE ...          -- 1 row
  executeUpdate() = 1
ROLLBACK
~~~

Sau rollback, DB có thể trở lại trạng thái ban đầu. Commit thuộc về transaction owner.

## 24. Native UPDATE và optimistic locking

Giả sử PurchaseOrder dùng:

~~~java
@Version
private long version;
~~~

Một native SQL thông thường:

~~~sql
UPDATE purchase_order
SET status = 'CANCELLED'
WHERE id = 10
~~~

**không tự động** làm JPA tăng `version`. Nếu cần optimistic concurrency, native SQL phải thể hiện điều kiện version.

~~~java
Query q = em.createNativeQuery(
    "UPDATE purchase_order " +
    "SET status = ?, version = version + 1 " +
    "WHERE id = ? AND version = ? AND status = ?"
);

q.setParameter(1, "CANCELLED");
q.setParameter(2, orderId);
q.setParameter(3, expectedVersion);
q.setParameter(4, "NEW");

int affected = q.executeUpdate();

if (affected != 1) {
    throw new IllegalStateException(
        "Order changed, missing, or not cancellable"
    );
}
~~~

Đây là optimistic concurrency **do SQL tự thiết kế**, không phải do JPA tự thêm vào native UPDATE.

Nếu `affected = 0`, nguyên nhân có thể do ID không tồn tại, version đã đổi hoặc trạng thái không khớp. Nếu nghiệp vụ cần phân biệt, cần truy vấn/logic bổ sung và kiểm soát concurrency phù hợp.

### 24.1. Entity trong persistence context có thể stale

Ngay cả khi SQL tăng version, object PurchaseOrder đã managed có thể vẫn giữ version cũ. Không tiếp tục dùng object đó để ghi mà không có chiến lược refresh/clear hoặc tách transaction.

## 25. Native INSERT với tham số

Giả sử có bảng audit:

~~~sql
CREATE TABLE audit_event (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    reference_id BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Có thể dùng:

~~~java
Query q = em.createNativeQuery(
    "INSERT INTO audit_event " +
    "(event_type, reference_id, created_at) " +
    "VALUES (?, ?, ?)"
);

q.setParameter(1, "ORDER_CANCELLED");
q.setParameter(2, orderId);
q.setParameter(3, Timestamp.from(Instant.now()));

int inserted = q.executeUpdate();
~~~

Native INSERT không tự:

- Tạo một managed AuditEvent entity.
- Gọi `@PrePersist` của entity nếu thao tác đi thẳng qua SQL.
- Áp dụng `@GeneratedValue` ở tầng JPA.
- Cascade sang những entity khác theo graph.
- Trả generated key một cách portable qua `executeUpdate()`.

Nếu cần entity lifecycle và generated ID qua JPA, `em.persist(auditEvent)` có thể đơn giản hơn.

### 25.1. RETURNING là vấn đề DB-specific

PostgreSQL hỗ trợ cú pháp `INSERT ... RETURNING id`, nhưng cách nhận kết quả từ một DML native query qua JPA có thể phụ thuộc provider và database. Không suy ra mọi DB JPA đều có API nhận generated key giống nhau cho native INSERT.

## 26. Native DELETE với tham số

Ví dụ xóa đơn nháp của đúng khách hàng:

~~~java
Query q = em.createNativeQuery(
    "DELETE FROM purchase_order " +
    "WHERE id = ? AND customer_id = ? AND status = ?"
);

q.setParameter(1, orderId);
q.setParameter(2, authenticatedCustomerId);
q.setParameter(3, "NEW");

int deleted = q.executeUpdate();
~~~

Đây là DML trực tiếp:

- Cần transaction phù hợp.
- Bị ràng buộc bởi FK, UNIQUE/CHECK và trigger DB.
- Không tự thực thi tất cả JPA entity callbacks.
- Không tự lan cascade/orphanRemoval theo entity graph như `em.remove(order)`.
- Có thể khiến context chứa entity cũ.
- Nếu DB có `ON DELETE CASCADE`, DB xử lý xóa con theo quy tắc DB, khác cơ chế JPA cascade.

Nếu hệ thống phải giữ lịch sử đơn hàng, nên cân nhắc soft delete/trạng thái nghiệp vụ thay vì xóa vật lý.

### 26.1. Không dùng native DELETE để né business rules

Một service có thể có quy tắc “chỉ xóa đơn NEW chưa phát sinh thanh toán”. Nếu SQL chỉ:

~~~sql
DELETE FROM purchase_order WHERE id = ?
~~~

nó có thể vi phạm nghiệp vụ, dù không gây SQL injection. Hãy đưa điều kiện nghiệp vụ cần bảo vệ vào SQL/transaction, và bổ sung constraint/locking khi có concurrency.

## 27. Native DML và persistence context không tự đồng bộ

Đây là điểm dễ gây lỗi nhất khi kết hợp native SQL với ORM.

Giả sử:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);
~~~

Sau đó thực thi:

~~~java
em.createNativeQuery(
    "UPDATE purchase_order SET status = ? WHERE id = ?"
)
.setParameter(1, "PAID")
.setParameter(2, orderId)
.executeUpdate();
~~~

Có thể xảy ra:

~~~text
Managed Java object: order.status = NEW
Database row:        purchase_order.status = PAID
~~~

Native UPDATE không tương đương gọi `order.markPaid()` trên managed entity, và JPA không nhất thiết tự thay đổi các field của object đã được tải.

### 27.1. Refresh entity

Khi cần tải lại state:

~~~java
em.refresh(order);
~~~

Nhưng `refresh` có thể ghi đè các thay đổi chưa flush trên managed object. Cần đặt nó trong quy trình nghiệp vụ rõ ràng.

### 27.2. Clear và reload

~~~java
em.flush(); // Nếu có thay đổi pending cần giữ.
em.clear(); // Detach các managed entities.

PurchaseOrder reloaded =
    em.find(PurchaseOrder.class, orderId);
~~~

`clear()` có thể làm mất pending changes chưa flush, vì vậy không gọi như một cách “đồng bộ tất cả” khi chưa hiểu trạng thái hiện tại.

### 27.3. Tránh native DML và dirty checking xung đột

Nếu một entity managed còn state cũ nhưng được update bằng native SQL, một lần flush dirty state sau đó có thể ghi đè dữ liệu hoặc gây version conflict. Khi kết hợp hai đường ghi trên cùng row, cần chọn rõ thứ tự và ownership của state.

## 28. Flush trước native SELECT khi cần thấy pending changes

Ví dụ service sửa entity managed:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

order.markPaid();
~~~

Sau đó dùng native COUNT:

~~~java
Query q = em.createNativeQuery(
    "SELECT COUNT(*) FROM purchase_order WHERE status = ?"
);

q.setParameter(1, "PAID");
long paidCount =
    ((Number) q.getSingleResult()).longValue();
~~~

Nếu SQL UPDATE chưa flush, database có thể chưa phản ánh thay đổi của object managed.

### 28.1. AUTO và COMMIT

`FlushModeType.AUTO` quy định JPA provider phải bảo đảm những thay đổi pending có thể ảnh hưởng kết quả query được phản ánh trong ngữ cảnh transaction phù hợp, bằng flush hoặc cơ chế tương đương.

Với `FlushModeType.COMMIT`, tác động của pending changes chưa flush tới query trước commit không được chuẩn bảo đảm.

Native query có thể khiến provider khó phân tích chính xác những bảng liên quan so với JPQL. Hành vi thực tế khác nhau theo provider và API.

### 28.2. Explicit flush khi cần ranh giới chắc chắn

~~~java
em.flush();

Query q = em.createNativeQuery(
    "SELECT COUNT(*) FROM purchase_order WHERE status = ?"
);

q.setParameter(1, "PAID");

long count =
    ((Number) q.getSingleResult()).longValue();
~~~

`flush()` đồng bộ SQL trong transaction hiện tại, **không commit**. Transaction khác vẫn chịu quy tắc isolation, và rollback có thể hủy những tác động đã flush.

### 28.3. Bulk DML và clear không tự thay thế flush

Nếu gọi `em.clear()` trước khi flush, những thay đổi managed chưa đồng bộ có thể bị mất. Nếu gọi bulk SQL mà không xử lý state cũ, entity managed có thể stale. Cần có quy trình cụ thể tùy use case, không áp dụng một công thức mù quáng.

## 29. Native query trong Spring Data JPA

Nếu ứng dụng dùng Spring Data, có thể khai báo query native trên repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = "SELECT o.* " +
                "FROM purchase_order o " +
                "WHERE o.status = ?1",
        nativeQuery = true
    )
    List<PurchaseOrder> findByStatusNative(String status);
}
~~~

`@Query(nativeQuery = true)` là khả năng của Spring Data JPA. Cách Spring Data xử lý các tham số `?1` và mapping có thể phụ thuộc framework/provider; không nên đồng nhất hoàn toàn với hợp đồng portable của `EntityManager.createNativeQuery` thuần JPA.

### 29.1. DML trong Spring Data

Với UPDATE/DELETE qua repository annotation, thường dùng `@Modifying` và transaction:

~~~java
@Modifying
@Transactional
@Query(
    value = "UPDATE purchase_order " +
            "SET status = ?1 " +
            "WHERE id = ?2 AND status = ?3",
    nativeQuery = true
)
int changeStatus(
    String nextStatus,
    Long orderId,
    String expectedStatus
);
~~~

`@Modifying` là API **Spring Data**, không phải JPA chuẩn. Nếu dùng trực tiếp EntityManager và `executeUpdate()`, không cần annotation này.

### 29.2. @Transactional không phải commit bên trong repository

Một repository có thể tham gia transaction của application service. `executeUpdate()` hoặc return từ repository **không chứng minh transaction ngoài cùng đã commit**. Transaction manager quyết định ranh giới commit/rollback.

### 29.3. ReadOnly không biến SQL thành không thể ghi

`@Transactional(readOnly = true)` của Spring là cấu hình transaction/framework; không dùng nó thay security rule hoặc database permission. Các hành vi tối ưu read-only phụ thuộc transaction manager/provider.

## 30. Query hint, timeout và native SQL

Một native query có thể đặt timeout:

~~~java
Query q = em.createNativeQuery(
    "SELECT id FROM purchase_order WHERE status = ?"
);

q.setParameter(1, "PAID");
q.setHint(
    "jakarta.persistence.query.timeout",
    3000
);
~~~

`3000` là yêu cầu 3.000 ms theo hint JPA. Nhưng timeout có thể không dừng chính xác ở mili-giây thứ 3.000; provider, JDBC driver và DB quyết định khả năng áp dụng.

Không kết luận hint đã có tác dụng chỉ vì `setHint` không ném exception. Một provider có thể bỏ qua hint không nhận diện. Nếu timeout là yêu cầu quan trọng, test bằng query chậm có kiểm soát trên stack thực.

### 30.1. Query timeout khác lock timeout

`jakarta.persistence.query.timeout` liên quan thời gian thực thi query; `jakarta.persistence.lock.timeout` liên quan yêu cầu chờ lock trong tình huống pessimistic locking.

Một native SQL chứa `FOR UPDATE` hoặc locking clause có thể có cách xử lý lock timeout riêng của DB. Không gộp hai khái niệm này thành một.

## 31. Locking bằng native SQL

Ví dụ PostgreSQL:

~~~sql
SELECT id, status
FROM purchase_order
WHERE id = ?
FOR UPDATE
~~~

JPA:

~~~java
Query q = em.createNativeQuery(
    "SELECT id, status " +
    "FROM purchase_order " +
    "WHERE id = ? FOR UPDATE"
);

q.setParameter(1, orderId);

Object[] row = (Object[]) q.getSingleResult();
~~~

`FOR UPDATE` là cú pháp SQL; chi tiết NOWAIT, SKIP LOCKED, lock timeout và phạm vi lock phụ thuộc database. Query cần transaction phù hợp và không nên giữ lock trong khi chờ API ngoài DB.

Nếu ứng dụng chỉ cần cập nhật trạng thái với điều kiện, một native UPDATE có WHERE state/version có thể đơn giản và ít round trip hơn SELECT FOR UPDATE rồi UPDATE, nhưng cần chọn theo concurrency semantics cụ thể.

## 32. Những điểm cần kiểm tra khi query lỗi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SQL grammar error | Sai tên bảng/cột hoặc cú pháp DB | Kiểm tra schema/dialect thật |
| Bind index 0 lỗi | JPA dùng 1-based positional index | Bắt đầu từ 1 |
| Thiếu tham số | Có placeholder chưa bind | Đếm dấu `?` và binding |
| Bind enum không đúng | Cột SQL lưu string/number/native enum khác kiểu | Dùng encoding phù hợp |
| Query returns no result | WHERE không khớp | Dùng list hoặc xử lý NoResultException |
| NonUniqueResultException | getSingleResult trên query có nhiều hàng | Thêm unique condition hoặc dùng list |
| ClassCastException | Scalar returned type khác giả định | Kiểm tra Number/JDBC result type |
| Entity hydration lỗi | SELECT thiếu mapped column | Chọn đủ cột hoặc dùng DTO |
| JOIN trả nhiều ID trùng | To-many join nhân row | DISTINCT/EXISTS |
| Query IN list lỗi | Không tự mở rộng collection | Tạo placeholders hoặc dùng extension |
| LIKE tìm sai | Wildcard không được escape | Dùng ESCAPE nếu tìm literal |
| DML ngoài transaction | Thiếu transaction hợp lệ | Đặt boundary đúng |
| SQL UPDATE rồi getter vẫn cũ | Managed entity stale | Refresh/clear-reload có kiểm soát |
| UPDATE bị optimistic conflict | Version/where không khớp | Kiểm tra expected version/affected rows |
| FK violation khi DELETE | Bảng con còn tham chiếu | Thiết kế chính sách xóa đúng |
| SQL chạy H2 nhưng fail production | Dialect/type khác nhau | Test DB mục tiêu |
| Query quá chậm | Thiếu index, lọc quá rộng, load quá nhiều cột | EXPLAIN/pagination/projection |
| SQL bind data log lộ PII | Logging thiếu mask | Không log tham số nhạy cảm |

### 32.1. Transaction lỗi có thể không tiếp tục dùng được

Nếu DB ném exception khi thực thi native query, transaction có thể bị đánh dấu rollback-only hoặc ở trạng thái lỗi. Không bắt exception rồi tiếp tục commit mà không kiểm tra trạng thái transaction.

Với resource-local, rollback trong catch và đóng EntityManager do ứng dụng tạo. Với Spring/JTA, để transaction owner xử lý theo chính sách exception/rollback.

### 32.2. Log SQL không có nghĩa SQL đã commit

Bản ghi SQL `INSERT`/`UPDATE`/`DELETE` có thể xuất hiện trước khi transaction commit; rollback vẫn có thể hủy thay đổi.

## 33. Kiểm thử tích hợp native query có tham số

Vì native SQL phụ thuộc schema và DB, integration test có giá trị rất lớn.

### 33.1. Fixture phân biệt được thứ tự binding

Tạo:

~~~text
Order #10: customer=1, status=PAID
Order #11: customer=1, status=NEW
Order #12: customer=2, status=PAID
~~~

Query:

~~~sql
SELECT id FROM purchase_order
WHERE status = ? AND customer_id = ?
~~~

Bind `PAID` ở vị trí 1, `1L` ở vị trí 2. Kết quả phải chỉ có ID 10. Nếu dữ liệu test quá đồng nhất, lỗi bind nhầm thứ tự có thể không bị phát hiện.

### 33.2. Test SQL injection

Cho parameter chứa dấu nháy, dấu backslash, Unicode và một chuỗi giống cú pháp SQL. Truy vấn phải đối xử với chúng như data, không thực thi cú pháp ngoài ý định.

### 33.3. Test scalar numeric

`COUNT(*)` nên được đọc qua `Number` nếu không có mapping type rõ ràng. Kiểm tra kiểu và phạm vi giá trị trên DB/driver đang dùng.

### 33.4. Test entity result mapping

Chạy `createNativeQuery(sql, PurchaseOrder.class)` với tất cả cột cần thiết; kiểm tra ID, status, totalAmount, customer FK và version. Cố tình thay alias trong một test có thể giúp phát hiện việc mapping phụ thuộc tên cột.

### 33.5. Test DTO mapping

Với `@ConstructorResult`, kiểm tra đúng alias, thứ tự và kiểu. Dùng số tiền khác nhau để nhận diện mapping bị tráo cột.

### 33.6. Test DML và rollback

~~~text
Transaction A:
    BEGIN
    Native UPDATE Order #10
    executeUpdate() = 1
    ROLLBACK

Transaction B/context mới:
    Order #10 giữ trạng thái trước UPDATE.
~~~

Đọc qua persistence context mới để tránh managed entity stale che kết quả.

### 33.7. Test persistence context stale

1. `em.find` Order để tạo managed entity.
2. Native UPDATE cùng row.
3. Xem object managed có thể chưa phản ánh thay đổi.
4. Làm mới bằng `refresh` hoặc context mới.
5. Xác minh DB đã được cập nhật sau commit.

### 33.8. Test database mục tiêu

H2 hoặc một DB in-memory có thể khác PostgreSQL/MySQL/Oracle về timestamp, enum, JSON operators, locking, pagination, result numeric types và constraint. Với query dùng cú pháp DB-specific, test trên chính DB mục tiêu hoặc môi trường tương đương chặt chẽ.

### 33.9. Không ghi log dữ liệu nhạy cảm trong test/production

Query parameter có thể chứa email, token, mã khách hàng hoặc dữ liệu tài chính. SQL bind logging nên được giới hạn/ẩn dữ liệu theo chính sách bảo mật, nhất là trên production.

## 34. Đóng gói native SQL trong repository

Không nên để controller hay mọi service tự viết native SQL rải rác. Một repository chuyên trách giúp quản lý query template, binding và mapping.

Ví dụ interface:

~~~java
public interface OrderReportRepository {

    List<OrderSummary> findPaidOrders(
        long customerId,
        int page,
        int size
    );

    long countPaidOrders(long customerId);
}
~~~

Implementation:

~~~java
public final class JpaNativeOrderReportRepository
        implements OrderReportRepository {

    private final EntityManager em;

    public JpaNativeOrderReportRepository(EntityManager em) {
        this.em = em;
    }

    @Override
    public List<OrderSummary> findPaidOrders(
            long customerId,
            int page,
            int size) {

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                "Invalid paging"
            );
        }

        Query q = em.createNativeQuery(
            "SELECT id, order_number, total_amount " +
            "FROM purchase_order " +
            "WHERE customer_id = ? AND status = ? " +
            "ORDER BY created_at DESC, id DESC"
        );

        q.setParameter(1, customerId);
        q.setParameter(2, "PAID");
        q.setFirstResult(Math.multiplyExact(page, size));
        q.setMaxResults(size);

        List<OrderSummary> result = new ArrayList<>();

        for (Object item : q.getResultList()) {
            Object[] row = (Object[]) item;

            result.add(new OrderSummary(
                ((Number) row[0]).longValue(),
                (String) row[1],
                (BigDecimal) row[2]
            ));
        }

        return result;
    }

    @Override
    public long countPaidOrders(long customerId) {
        Query q = em.createNativeQuery(
            "SELECT COUNT(*) FROM purchase_order " +
            "WHERE customer_id = ? AND status = ?"
        );

        q.setParameter(1, customerId);
        q.setParameter(2, "PAID");

        return ((Number) q.getSingleResult()).longValue();
    }
}
~~~

Ví dụ dùng `OrderSummary` đã khai báo ở phần DTO, và giả định EntityManager được cấp theo transaction/scope phù hợp.

### 34.1. Repository không phải nhất thiết là transaction owner

Nếu use case cần sửa Order và Inventory trong cùng transaction, ranh giới nên bao trùm cả hai thao tác. Repository native query chỉ tham gia, không tự commit độc lập nếu nghiệp vụ đòi tính nguyên tử.

### 34.2. SQL phải sống cùng schema migration

Nếu migration đổi `total_amount` thành `gross_amount`, native query dùng `total_amount` không tự được provider sửa lại chỉ vì entity đổi `@Column`. Hãy tìm và cập nhật mọi query có tên cột cũ, cùng integration tests liên quan.

## 35. Portability, hiệu năng và lựa chọn công cụ

Phân biệt **portability của JPA API** với **portability của SQL**.

JPA API:

~~~java
em.createNativeQuery(sql);
query.setParameter(1, value);
query.getResultList();
query.executeUpdate();
~~~

có thể portable, nhưng SQL như:

~~~sql
INSERT ... RETURNING id
~~~

hay:

~~~sql
SELECT ... FOR UPDATE SKIP LOCKED
~~~

phụ thuộc khả năng DB. Những tính năng như JSONB, UPSERT, array parameters, function, window syntax và kiểu timestamp có thể khác.

### 35.1. Chọn native query khi lợi ích rõ ràng

- JPQL đơn giản hơn cho CRUD query theo entity.
- Criteria tốt cho nhiều điều kiện động theo entity model.
- Native SQL phù hợp với SQL chuyên biệt/báo cáo phức tạp.
- Các thư viện query DSL có thể hữu ích khi viết nhiều SQL động có cấu trúc.

Không nhất thiết dùng một công cụ cho toàn hệ thống.

### 35.2. Native SQL không tự động nhanh hơn

Một câu JPQL và một câu native SQL có thể sinh ra cùng execution plan. Khi tối ưu, xem:

- Index và độ chọn lọc các điều kiện.
- Projection so với `SELECT *`.
- Số row trả về.
- SQL JOIN to-many và duplicate.
- Phân trang OFFSET sâu.
- Các function trên cột index như `LOWER(...)`.
- Query plan/EXPLAIN của database.
- Round trip JDBC và cấu hình batch/fetch.

### 35.3. Parameter binding và plan cache

Bind parameter giúp tách dữ liệu khỏi cấu trúc SQL và có thể hỗ trợ tận dụng statement/plan caching theo driver/DB. Nhưng hiệu quả cache không được bảo đảm chỉ vì dùng `?`: DB có thể chọn plan khác theo dữ liệu, thống kê và cơ chế chuẩn bị statement.

## 36. Bài tập thực hành

### Bài 1. Phân biệt JPQL với native SQL

JPQL:

~~~java
"SELECT o FROM PurchaseOrder o WHERE o.status = :status"
~~~

Native SQL:

~~~sql
SELECT id, order_number FROM purchase_order WHERE status = ?
~~~

**Câu hỏi:** Tên nào là entity/property, tên nào là bảng/cột?

**Đáp án:** `PurchaseOrder` và `o.status` trong JPQL là entity và property. `purchase_order` và `order_number` trong SQL là schema names.

### Bài 2. Positional index

~~~sql
SELECT id FROM purchase_order
WHERE status = ? AND customer_id = ?
~~~

**Câu hỏi:** Bind đúng thế nào?

**Đáp án:**

~~~java
q.setParameter(1, "PAID");
q.setParameter(2, customerId);
~~~

Chỉ số bắt đầu từ 1.

### Bài 3. SQL injection

Developer viết:

~~~java
String sql =
    "SELECT id FROM purchase_order " +
    "WHERE order_number = '" + userInput + "'";
~~~

**Câu hỏi:** Sửa thế nào?

**Đáp án:** Dùng `WHERE order_number = ?` và `q.setParameter(1, userInput)`. Không nối input thành SQL literal.

### Bài 4. Named native parameter

~~~java
em.createNativeQuery(
    "SELECT id FROM purchase_order WHERE status = :status"
);
~~~

**Câu hỏi:** Có portable tuyệt đối theo JPA không?

**Đáp án:** Không. Có provider hỗ trợ named parameters trong native SQL nhưng JPA chỉ bảo đảm positional binding portable.

### Bài 5. Một cột và nhiều cột

**Câu hỏi:** `SELECT order_number ...` và `SELECT id, order_number ...` trả kết quả giống nhau không?

**Đáp án:** Không. Một scalar column thường trả scalar như String. Nhiều cột thường trả một `Object[]` cho mỗi row, khi không có mapping khác.

### Bài 6. Count

~~~java
Long count = (Long) q.getSingleResult();
~~~

**Câu hỏi:** Vì sao có thể ClassCastException?

**Đáp án:** Native COUNT(*) có thể trả BigInteger/Long hoặc Number khác tùy provider/driver. Dùng `((Number) q.getSingleResult()).longValue()` khi phù hợp.

### Bài 7. IN rỗng

**Câu hỏi:** Có nên sinh `WHERE id IN ()` khi danh sách IDs rỗng?

**Đáp án:** Không. Xác định semantics: có thể trả danh sách rỗng hoặc bỏ filter, không mặc định một cách làm cho mọi API.

### Bài 8. IN với List

~~~java
q.setParameter(1, List.of(10L, 11L));
~~~

cho SQL `WHERE id IN (?)`.

**Câu hỏi:** Có portable không?

**Đáp án:** Không. Native collection expansion tùy provider. Dùng `IN (?, ?)` và bind từng vị trí hoặc extension đã kiểm thử.

### Bài 9. LIKE

**Câu hỏi:** Người dùng nhập `50%` muốn khớp dấu phần trăm literal, có cần xử lý không?

**Đáp án:** Có. LIKE coi % là wildcard; cần escape theo cú pháp ESCAPE nếu muốn literal search, ngoài việc bind parameter.

### Bài 10. Kết quả entity

~~~java
em.createNativeQuery(
    "SELECT id, order_number FROM purchase_order",
    PurchaseOrder.class
);
~~~

**Câu hỏi:** Rủi ro?

**Đáp án:** Entity mapping yêu cầu thêm các cột khác như version, status, total, FK, timestamp. SELECT thiếu cột có thể lỗi; dùng full entity result hoặc DTO projection.

### Bài 11. DTO

**Câu hỏi:** SQL trả alias `order_id`, `number` và `amount`, muốn tạo `OrderSummary(Long,String,BigDecimal)`.

**Đáp án:** Có thể dùng `@SqlResultSetMapping` với `@ConstructorResult`/`@ColumnResult`, khai báo alias, kiểu và thứ tự phù hợp.

### Bài 12. Pagination

**Câu hỏi:** Dùng `setFirstResult(40)`/`setMaxResults(20)` nhưng không ORDER BY, vấn đề gì?

**Đáp án:** Thứ tự SQL không được bảo đảm; page có thể không ổn định. Thêm ORDER BY ổn định với ID tie-breaker.

### Bài 13. executeUpdate

~~~java
tx.begin();
int count = q.executeUpdate();
tx.rollback();
~~~

**Câu hỏi:** `count = 1` có chứng minh update đã commit không?

**Đáp án:** Không. ExecuteUpdate chạy DML trong transaction; rollback có thể hủy thay đổi.

### Bài 14. Native UPDATE và @Version

**Câu hỏi:** Native UPDATE status có tự tăng `@Version` không?

**Đáp án:** Không. Nếu cần optimistic locking, SQL phải cập nhật version và điều kiện WHERE đúng; hoặc cập nhật qua entity managed.

### Bài 15. Persistence context stale

Managed Order đã tải có status NEW. Native SQL đổi DB thành PAID.

**Câu hỏi:** `order.getStatus()` chắc chắn là PAID chưa?

**Đáp án:** Không. Native DML không tự đồng bộ object managed; cần refresh/clear-reload phù hợp sau khi xử lý pending changes.

### Bài 16. Transaction

**Câu hỏi:** Flush, executeUpdate và commit có giống nhau không?

**Đáp án:** Không. Flush đồng bộ pending JPA changes vào transaction; executeUpdate thực thi DML cụ thể; commit xác nhận transaction.

### Bài 17. DELETE và JPA cascade

**Câu hỏi:** Native DELETE Order có tự gọi cascade REMOVE/orphanRemoval trên từng OrderLine entity không?

**Đáp án:** Không. Native DML không đi qua remove entity lifecycle thông thường; DB FK có thể từ chối hoặc DB-level cascade được áp dụng nếu schema có cấu hình đó.

### Bài 18. Sort từ client

**Câu hỏi:** Có thể bind `ORDER BY ?` với chuỗi `"total_amount DESC"` để chọn cột không?

**Đáp án:** Không. Parameter dành cho giá trị; tên cột và hướng sort phải chọn từ whitelist ở server.

### Bài 19. Query đặc thù DB

**Câu hỏi:** Một native query PostgreSQL dùng `RETURNING` hoặc `JSONB`, có chắc chạy trên DB khác nhờ JPA không?

**Đáp án:** Không. API JPA portable không làm cú pháp SQL đặc thù DB portable.

### Bài 20. Test

**Câu hỏi:** Vì sao cần test native query trên PostgreSQL thực nếu production chạy PostgreSQL?

**Đáp án:** Result numeric types, timestamp, enum, JSON operators, lock behavior, constraints và SQL dialect có thể khác H2 hoặc DB khác.

## 37. Checklist trước khi đưa native query vào production

1. **Có cần native SQL không**, hay JPQL/Criteria đơn giản hơn?
2. SQL có dùng đúng **tên bảng/cột theo migration hiện tại** không?
3. Mọi **giá trị động đã bind qua parameter** chưa?
4. Positional parameters đã được đánh số **từ 1** đúng thứ tự chưa?
5. Có dùng native named parameter/list expansion phụ thuộc provider không?
6. Java types có khớp column types và enum encoding không?
7. Đã xử lý **null, list rỗng, LIKE wildcard và timezone** chưa?
8. SQL identifier/sort động đã whitelist chưa?
9. Có điều kiện tenant/authorization bắt buộc không?
10. Query trả **scalar, Object[], entity hay DTO**? Mapping có rõ không?
11. Entity result có đủ mapped columns, ID, FK và version không?
12. Có pagination và sort ổn định không?
13. Count query có cùng filter và không đếm trùng JOIN không?
14. Native DML có transaction boundary rõ không?
15. Có nguy cơ persistence context stale hoặc bỏ qua lifecycle callback không?
16. Native UPDATE có cần tự kiểm soát optimistic version không?
17. Có cần `flush()` trước SELECT hoặc `refresh()` sau DML không?
18. SQL có phụ thuộc dialect/function riêng DB không?
19. Đã xem execution plan/index trên workload thật chưa?
20. Đã test lỗi, rollback, concurrency, input đặc biệt trên DB mục tiêu chưa?

## 38. Tổng kết

~~~text
                 YÊU CẦU TRUY VẤN
                         |
                 Cần SQL trực tiếp?
                    /          \
                  Không        Có
                   |           |
                 JPQL /        v
                 Criteria  createNativeQuery(sql)
                               |
                               v
                       setParameter(1,...)
                       setParameter(2,...)
                               |
                      +--------+---------+
                      |                  |
                    SELECT              DML
                      |                  |
           getResultList() /       executeUpdate()
           getSingleResult()            |
                      |                  |
                 Mapping result      Transaction
                      |              commit/rollback
           +----------+--------+
           |          |        |
         Scalar     Object[]  Entity/DTO
                               |
                               v
                    Kiểm tra managed state
                    khi native DML tác động
                    cùng dữ liệu trong context
~~~

Các nguyên tắc cần ghi nhớ:

1. **`EntityManager.createNativeQuery(...)`** tạo query với SQL dựa trên tên bảng/cột thật.
2. **`Query.setParameter(int,Object)`** bind giá trị an toàn; positional index bắt đầu từ **1**.
3. **Positional binding portable hơn named parameters trong native SQL**; các extension theo provider phải được kiểm chứng.
4. **Không ghép input của người dùng vào SQL.** Parameter binding bảo vệ cấu trúc câu lệnh và giảm lỗi literal.
5. **Không dùng placeholder cho tên bảng, tên cột hoặc hướng ORDER BY.** Chọn fragment SQL từ whitelist của server.
6. **Chọn đúng result mapping**: scalar, `Object[]`, entity result hoặc DTO với `@SqlResultSetMapping`.
7. **`COUNT(*)` có thể trả kiểu Number khác Long**; kiểm tra result types trên provider thực tế.
8. **Native IN-list expansion không portable**; tạo placeholder có kiểm soát hoặc dùng extension được kiểm thử.
9. **Phân trang cần ORDER BY ổn định** và giới hạn page size; COUNT query phải phản ánh cùng filter.
10. **Native DML dùng `executeUpdate()` trong transaction**, nhưng `executeUpdate` không đồng nghĩa commit.
11. **Native UPDATE/DELETE bỏ qua một số entity lifecycle semantics** và có thể khiến persistence context stale.
12. **`@Version` không tự được cập nhật bởi native SQL**; cần thiết kế version condition nếu muốn optimistic locking.
13. **Flush khác commit; clear có thể làm mất pending changes**, nên quản lý ranh giới đồng bộ rõ ràng.
14. **Native SQL phụ thuộc DB/dialect**; khả năng di động của JPA API không bảo đảm cú pháp SQL di động.
15. **Kiểm thử bằng DB thực, SQL logging được bảo vệ và performance profiling** trước khi dựa vào hành vi provider.

Native query là cầu nối hữu ích giữa ORM và sức mạnh của SQL. Khi quản lý đúng **parameter binding, kiểu kết quả, transaction và persistence context**, ứng dụng có thể tận dụng những truy vấn SQL chuyên biệt mà vẫn giữ được tính an toàn, rõ ràng và khả năng bảo trì của lớp truy cập dữ liệu Java.
