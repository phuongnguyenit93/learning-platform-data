# Gán tham số theo tên và theo vị trí trong JPQL

Trong Jakarta Persistence (JPA), JPQL (*Jakarta Persistence Query Language*) cho phép truy vấn **entity và thuộc tính Java** thay vì viết trực tiếp tên bảng, cột như SQL. Khi truy vấn cần nhận dữ liệu thay đổi theo request — ID khách hàng, trạng thái đơn hàng, thời gian bắt đầu, giá tối thiểu — ta không nên nối giá trị người dùng trực tiếp vào chuỗi truy vấn. Cách chuẩn là **khai báo tham số trong JPQL và truyền giá trị qua `setParameter(...)`**.

Có hai hình thức chính:

```jpql
-- Tham số theo tên (named parameters)
SELECT o FROM PurchaseOrder o
WHERE o.status = :status
  AND o.totalAmount >= :minimumTotal
```

```jpql
-- Tham số theo vị trí (positional parameters)
SELECT o FROM PurchaseOrder o
WHERE o.status = ?1
  AND o.totalAmount >= ?2
```

Tương ứng trong Java:

```java
// Theo tên
query.setParameter("status", OrderStatus.PAID);
query.setParameter("minimumTotal", new BigDecimal("100000.00"));

// Theo vị trí: đánh số từ 1, không phải 0
query.setParameter(1, OrderStatus.PAID);
query.setParameter(2, new BigDecimal("100000.00"));
```

Hai cách đều giải quyết một bài toán: **tách cấu trúc truy vấn khỏi giá trị dữ liệu**. Khác biệt chủ yếu nằm ở cách định danh tham số và khả năng đọc/bảo trì code.

> **Quy tắc dễ nhớ:** Trong JPQL, `:status` được gán bằng `setParameter("status", value)`, còn `?1` được gán bằng `setParameter(1, value)`. Không đặt dấu `:` trong tên truyền vào `setParameter`, vị trí bắt đầu từ **1**, và không trộn hai kiểu tham số trong cùng một câu JPQL.

Bài học này thuộc chương **JPQL cơ bản** của module **Data Persistence Relational Access ORM JPA**. Nội dung đi từ cú pháp cơ bản đến kiểu dữ liệu, tham số lặp lại, `IN`, `LIKE`, `NULL`, truy vấn động, Spring Data JPA, Criteria API, kiểm soát SQL injection và các lỗi thường gặp.

## 1. JPQL là truy vấn trên entity, không phải bảng

Giả sử hệ thống có entity `PurchaseOrder` với các thuộc tính:

- `id`: ID đơn hàng.
- `orderCode`: mã đơn hàng.
- `status`: enum trạng thái.
- `totalAmount`: tổng tiền.
- `createdAt`: thời điểm tạo.
- `customer`: quan hệ `@ManyToOne` đến `Customer`.

Một khai báo rút gọn:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false)
    private String orderCode;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {}

    // Constructor, domain methods và getters được lược bớt.
}
```

Và:

```java
public enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Entity `Customer` có ID kiểu `Long`, được ánh xạ bằng `@Entity` và `@Id`:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Customer() {}
}
```

Khi viết JPQL:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.orderCode = :orderCode
```

ta dùng **tên entity `PurchaseOrder`** và **tên thuộc tính `orderCode`**, không viết `purchase_orders.order_code` theo tên SQL. JPA provider dịch JPQL thành SQL dựa trên mapping.

### Khác biệt giữa JPQL và SQL

| Trong JPQL | Trong SQL thông thường |
|---|---|
| `PurchaseOrder` | `purchase_orders` |
| `o.orderCode` | `o.order_code` |
| `o.customer.id` | Thường được hiện thực bằng `customer_id` hoặc JOIN tùy truy vấn/provider |
| `:orderCode` | Placeholder JDBC phù hợp với dialect/driver |
| `?1` | Positional JPQL parameter được provider dịch sang cơ chế bind thích hợp |

**Tham số chỉ thay thế giá trị.** Nó không đổi cách truy vấn entity theo mapping và không thay thế tên entity, thuộc tính hay toán tử JPQL.

## 2. Vì sao cần bind tham số?

Một cách không nên làm:

```java
String jpql =
    "select o from PurchaseOrder o " +
    "where o.orderCode = '" + requestedCode + "'";

List<PurchaseOrder> orders =
    entityManager.createQuery(jpql, PurchaseOrder.class)
                 .getResultList();
```

Đoạn này ghép trực tiếp đầu vào vào cú pháp truy vấn. Nó gây nhiều vấn đề:

1. **Injection:** dữ liệu đầu vào có thể trở thành một phần cú pháp truy vấn nếu bị ghép không an toàn.
2. **Ký tự đặc biệt:** mã đơn chứa dấu nháy đơn có thể phá cú pháp.
3. **Kiểu dữ liệu:** số, enum và thời gian có thể bị chuyển thành chuỗi sai quy cách.
4. **Dễ bảo trì:** khi thêm điều kiện, code phải tự quản lý dấu nháy, escape và định dạng.
5. **Tối ưu:** bind parameters có thể hỗ trợ database/provider tái sử dụng cấu trúc statement, tùy hệ thống.

Cách có tham số:

```java
String jpql =
    "select o from PurchaseOrder o " +
    "where o.orderCode = :orderCode";

List<PurchaseOrder> orders = entityManager
    .createQuery(jpql, PurchaseOrder.class)
    .setParameter("orderCode", requestedCode)
    .getResultList();
```

Ở đây `requestedCode` là **giá trị** của tham số, không bị coi là một đoạn JPQL mới.

Bind tham số không phải cơ chế bảo mật duy nhất: ứng dụng vẫn cần authentication, authorization, giới hạn dữ liệu theo tenant, validation, kiểm soát truy vấn động và quản lý transaction.

## 3. Gán tham số theo tên: `:parameterName`

**Named parameter** bắt đầu bằng dấu hai chấm `:` trong JPQL, theo sau là một tên hợp lệ.

Ví dụ:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :status
```

Java:

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = :status",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.PAID);

List<PurchaseOrder> result = query.getResultList();
```

Từng phần:

- `:status` trong chuỗi JPQL là **vị trí nhận giá trị**.
- `setParameter("status", ...)` tìm tham số **tên status**, không gồm dấu `:`.
- `OrderStatus.PAID` là giá trị Java được truyền vào.
- `getResultList()` thực hiện truy vấn để lấy danh sách kết quả.

### Hai điều kiện có hai tên

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = :status " +
    "and o.totalAmount >= :minimumTotal",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.PAID);
query.setParameter(
    "minimumTotal",
    new BigDecimal("100000.00")
);

List<PurchaseOrder> orders = query.getResultList();
```

Việc đặt tên tham số theo ý nghĩa nghiệp vụ khiến một query có nhiều điều kiện dễ đọc hơn so với các vị trí số.

### Đọc mã đúng cách

```text
JPQL: WHERE o.status = :status
                      └─────┐
Java: setParameter("status", OrderStatus.PAID)
                    └───────┘
```

Tên phải khớp với tham số được khai báo. `"status"` khác `"orderStatus"`.

### Không thêm dấu hai chấm vào lời gọi Java

Sai:

```java
query.setParameter(":status", OrderStatus.PAID);
```

Đúng:

```java
query.setParameter("status", OrderStatus.PAID);
```

Dấu `:` là **ký hiệu cú pháp trong JPQL**; API `setParameter(String name, ...)` nhận tên thuần.

## 4. Gán tham số theo vị trí: `?1`, `?2`, ...

**Positional parameter** dùng dấu hỏi và chỉ số nguyên dương trong JPQL:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = ?1
  AND o.totalAmount >= ?2
```

Java:

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = ?1 " +
    "and o.totalAmount >= ?2",
    PurchaseOrder.class
);

query.setParameter(1, OrderStatus.PAID);
query.setParameter(2, new BigDecimal("100000.00"));

List<PurchaseOrder> orders = query.getResultList();
```

**JPQL positional parameters đánh số bắt đầu từ 1.**

| Ký hiệu JPQL | Lời gọi tương ứng |
|---|---|
| `?1` | `setParameter(1, value)` |
| `?2` | `setParameter(2, value)` |
| `?3` | `setParameter(3, value)` |

Không viết `?0` cho tham số đầu tiên trong JPQL. Java collections có index bắt đầu từ 0, nhưng điều đó không áp dụng cho positional parameters của JPQL.

### Số vị trí có nghĩa, không phải thứ tự gọi setParameter

```java
query.setParameter(2, new BigDecimal("100000.00"));
query.setParameter(1, OrderStatus.PAID);
```

Đoạn này vẫn gán đúng nếu query sử dụng `?1` cho status và `?2` cho minimumTotal. Thứ tự *lời gọi Java* không cần giống thứ tự xuất hiện tham số trong chuỗi, miễn là giá trị gắn đúng ID tham số.

Nên đánh số tuần tự từ 1 theo thứ tự xuất hiện để dễ đọc và tránh lỗi. Không dựa vào cú pháp placeholder trần `?` thường gặp trong JDBC để viết JPQL chuẩn:

```java
// Không nên dùng dấu ? trần như JPQL positional parameter.
"select o from PurchaseOrder o where o.status = ?"
```

Ký hiệu chính xác cho tham số thứ nhất là `?1`.

## 5. So sánh named và positional parameters

| Tiêu chí | Theo tên | Theo vị trí |
|---|---|---|
| Cú pháp JPQL | `:status` | `?1` |
| Gán Java | `setParameter("status", value)` | `setParameter(1, value)` |
| Dễ đọc trong query dài | Thường tốt hơn | Phải nhớ mỗi số là gì |
| Thêm một điều kiện ở đầu | Ít ảnh hưởng tên tham số cũ | Dễ phải đánh số lại nếu muốn thứ tự liên tục |
| Dùng cùng tham số nhiều lần | Lặp tên `:keyword`, bind một lần | Lặp cùng vị trí `?1`, bind một lần |
| Nguy cơ lỗi phổ biến | Gõ sai tên, sai hoa/thường | Lệch thứ tự, nhầm vị trí bắt đầu từ 0 |
| Phù hợp | Query có nhiều điều kiện, code dài, maintain lâu | Query ngắn, repository method đơn giản |
| Bảo vệ injection cho giá trị | Có | Có |
| Tính portable trong JPQL | Có | Có, với số vị trí hợp lệ |

**Không có loại nào mặc định nhanh hơn loại kia chỉ vì cú pháp.** Provider xử lý binding và dịch truy vấn xuống SQL tương ứng; hiệu năng phụ thuộc query plan, index, dữ liệu, cách fetch, database và cache nhiều hơn cách viết `:status` hay `?1`.

Trong phần lớn code nghiệp vụ có nhiều điều kiện, nên ưu tiên **named parameters** vì tính rõ nghĩa.

## 6. Không trộn named và positional trong cùng một JPQL

Không nên viết:

```jpql
SELECT o FROM PurchaseOrder o
WHERE o.status = :status
  AND o.totalAmount >= ?1
```

Trong một câu JPQL, hãy chọn **một hệ thống tham số**. JPA quy định không được trộn named và positional parameters trong cùng query.

Hai phiên bản hợp lệ:

```jpql
SELECT o FROM PurchaseOrder o
WHERE o.status = :status
  AND o.totalAmount >= :minimumTotal
```

hoặc:

```jpql
SELECT o FROM PurchaseOrder o
WHERE o.status = ?1
  AND o.totalAmount >= ?2
```

Việc một provider cụ thể có thể chấp nhận một số cú pháp mở rộng không phải lý do để dựa vào hành vi không portable.

## 7. Tham số theo tên có thể xuất hiện nhiều lần

Giả sử cần tìm đơn hàng có code đúng từ khóa hoặc customer display name đúng từ khóa:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE o.orderCode = :keyword
   OR c.displayName = :keyword
```

Dù `:keyword` xuất hiện hai lần, code chỉ cần bind một giá trị:

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "join o.customer c " +
    "where o.orderCode = :keyword " +
    "or c.displayName = :keyword",
    PurchaseOrder.class
);

query.setParameter("keyword", keyword);
```

Mọi chỗ tham chiếu `:keyword` trong query nhận **cùng một giá trị**. Nếu hai điều kiện cần giá trị khác nhau, phải dùng hai tên:

```jpql
WHERE o.orderCode = :orderCode
   OR c.displayName = :customerName
```

Tương tự, positional parameter `?1` có thể xuất hiện nhiều lần để dùng chung giá trị. Đây là lý do mỗi tham số phải có ý nghĩa rõ ràng thay vì lặp số/tên tùy tiện.

## 8. Kiểu dữ liệu tham số được đối chiếu với mapping

Một tham số JPQL không đơn thuần là đoạn chuỗi thay thế văn bản. Provider dùng giá trị Java cùng metadata mapping và ngữ cảnh biểu thức để bind kiểu SQL phù hợp.

Ví dụ `o.totalAmount` có kiểu `BigDecimal`:

```java
query.setParameter(
    "minimumTotal",
    new BigDecimal("500000.00")
);
```

Không nên mặc định truyền một `String`:

```java
query.setParameter("minimumTotal", "500000.00"); // Dễ sai kiểu.
```

Một số database có ép kiểu ngầm, nhưng code portable nên truyền giá trị tương thích với kiểu property/parameter mong đợi.

Các ví dụ:

| Property JPA | Kiểu Java thường dùng để bind | Ví dụ |
|---|---|---|
| `Long id` | `Long` | `42L` |
| `String orderCode` | `String` | `"PO-1001"` |
| `BigDecimal totalAmount` | `BigDecimal` | `new BigDecimal("99000.00")` |
| `OrderStatus status` | `OrderStatus` | `OrderStatus.PAID` |
| `LocalDate date` | `LocalDate` | `LocalDate.of(2026, 1, 1)` |
| `LocalDateTime createdAt` | `LocalDateTime` | `LocalDateTime.of(2026, 1, 1, 0, 0)` |
| `Customer customer` | Entity tham chiếu `Customer` | `entityManager.getReference(Customer.class, id)` |

Một JPA provider có thể phát hiện sai kiểu khi gọi `setParameter`, khi thực thi truy vấn hoặc khi JDBC/database bind; exception và thời điểm khác nhau giữa cách triển khai.

## 9. Enum parameter: truyền enum, không phải chuỗi tùy ý

Entity:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false)
private OrderStatus status;
```

JPQL:

```jpql
SELECT o FROM PurchaseOrder o WHERE o.status = :status
```

Java:

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o where o.status = :status",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.PAID);
```

Không nên viết:

```java
query.setParameter("status", "PAID");
```

chỉ vì database lưu enum dưới dạng chuỗi. **Property của entity có kiểu `OrderStatus`**; mapping `EnumType.STRING` là cách JPA chuyển giá trị enum xuống cột SQL.

Nếu lấy giá trị request dạng chuỗi, nên parse/validate sang enum **trước khi bind**:

```java
OrderStatus status;

try {
    status = OrderStatus.valueOf(requestStatus);
} catch (IllegalArgumentException ex) {
    throw new IllegalArgumentException("Invalid order status", ex);
}

query.setParameter("status", status);
```

Cần xử lý input `null` và quy tắc phân biệt chữ hoa/chữ thường theo hợp đồng API; `valueOf` mặc định yêu cầu đúng tên enum.

## 10. Tham số ngày tháng và thời gian

Với thuộc tính:

```java
@Column(name = "created_at", nullable = false)
private LocalDateTime createdAt;
```

có thể truy vấn một khoảng thời gian:

```java
LocalDateTime from =
    LocalDateTime.of(2026, 1, 1, 0, 0);

LocalDateTime to =
    LocalDateTime.of(2026, 2, 1, 0, 0);

TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.createdAt >= :from " +
    "and o.createdAt < :to",
    PurchaseOrder.class
);

query.setParameter("from", from);
query.setParameter("to", to);
```

Sử dụng khoảng **[from, to)** (bao gồm bắt đầu, không bao gồm kết thúc) giúp chia các khoảng liền kề mà không cần đặt thời điểm cuối ngày kiểu `23:59:59.999` phụ thuộc độ chính xác.

### `java.time` và `@Temporal`

Trong các phiên bản JPA hỗ trợ Java Time (từ JPA 2.2 trở đi), `LocalDate`, `LocalDateTime`, `LocalTime` và các kiểu được hỗ trợ khác có thể bind trực tiếp phù hợp mapping. **Không dùng `@Temporal` trên `LocalDateTime`**.

Với legacy `java.util.Date` hoặc `Calendar`, JPA có overload `setParameter` nhận `TemporalType` để chỉ độ chính xác:

```java
java.util.Date legacyFrom = ...;

query.setParameter(
    "legacyFrom",
    legacyFrom,
    TemporalType.TIMESTAMP
);
```

Đoạn này chỉ minh họa overload cho tham số có property legacy date/time tương ứng. Không trộn tùy tiện `java.util.Date` với `LocalDateTime` mà bỏ qua kiểu mapping.

### Vấn đề timezone

`LocalDateTime` không mang timezone/offset. Nếu hệ thống nhận thời gian theo múi giờ người dùng rồi lưu UTC, ứng dụng cần có chính sách chuyển đổi rõ ràng trước khi bind tham số.

Việc bind đúng kiểu không tự sửa được lỗi “lọc sai ngày” do timezone, độ chính xác cột hoặc business rule. Cần nhất quán giữa API, domain, JDBC mapping và database.

## 11. Bind tham số cho quan hệ entity

JPQL cho phép so sánh association trực tiếp với entity có định danh:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.customer = :customer
```

Java:

```java
Customer customer = entityManager.getReference(
    Customer.class, customerId
);

List<PurchaseOrder> orders = entityManager
    .createQuery(
        "select o from PurchaseOrder o " +
        "where o.customer = :customer",
        PurchaseOrder.class
    )
    .setParameter("customer", customer)
    .getResultList();
```

Provider có thể dùng ID của entity reference để so sánh khóa ngoại mà không cần tải toàn bộ thuộc tính Customer, tùy mapping và cách hiện thực.

Nếu đã có ID và không cần object entity, một cách khác là so sánh đường dẫn ID:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.customer.id = :customerId
```

Java:

```java
query.setParameter("customerId", customerId);
```

Cả hai cách đều có ngữ nghĩa rõ ràng nhưng kiểu tham số khác nhau:

- `o.customer = :customer` → bind `Customer`.
- `o.customer.id = :customerId` → bind ID, ví dụ `Long`.

Đừng bind `Long` vào `:customer` nếu expression mong đợi một entity, hoặc truyền `Customer` vào `:customerId` nếu expression mong đợi Long.

### `getReference()` không phải kiểm tra tồn tại

Nếu dùng:

```java
Customer reference =
    entityManager.getReference(Customer.class, customerId);
```

thì reference không đảm bảo hàng Customer thật sự tồn tại. Với truy vấn chỉ lọc theo FK, nếu ID không có, kết quả thường rỗng; với thao tác tạo quan hệ, database FK vẫn cần bảo vệ tính toàn vẹn.

Khi nghiệp vụ cần kiểm tra customer tồn tại hoặc trạng thái ACTIVE, dùng `find` hoặc truy vấn thích hợp.

## 12. Tham số cho `IN`: truyền một tập giá trị

Một tình huống thường gặp là lấy nhiều đơn hàng theo danh sách ID:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.id IN :ids
```

Java:

```java
List<Long> ids = List.of(101L, 102L, 103L);

TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.id in :ids",
    PurchaseOrder.class
);

query.setParameter("ids", ids);

List<PurchaseOrder> result = query.getResultList();
```

Named parameter `:ids` nhận **collection** cho biểu thức `IN`. Provider sẽ xử lý danh sách giá trị theo cách hỗ trợ của nó, thường chuyển thành một tập bind markers trong SQL.

Với positional parameter:

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o where o.id in ?1",
    PurchaseOrder.class
);
query.setParameter(1, ids);
```

Cú pháp có/không có ngoặc quanh collection-valued parameter trong các biến thể JPQL/HQL và native SQL có thể khác nhau; dùng cú pháp JPA được provider mục tiêu hỗ trợ. Tránh nhầm cơ chế collection-valued binding của JPQL với một placeholder duy nhất trong native JDBC SQL.

### Không truyền danh sách ID thành một chuỗi

Sai:

```java
query.setParameter("ids", "101,102,103");
```

Nếu JPQL mong đợi collection giá trị Long, chuỗi này **không phải** một collection Long hợp lệ. Cách đúng là:

```java
query.setParameter("ids", List.of(101L, 102L, 103L));
```

### Danh sách rỗng là trường hợp đặc biệt

Một danh sách `ids` rỗng:

```java
List<Long> ids = List.of();
```

không được bảo đảm tạo ra cú pháp SQL hợp lệ khi bind vào `IN` trên mọi JPA provider/database. Một số provider chuyển đổi đặc biệt, một số có thể sinh cú pháp không tương thích hoặc ném lỗi.

Nếu ngữ nghĩa nghiệp vụ là “không có ID nào được yêu cầu”, xử lý ngay tại service:

```java
public List<PurchaseOrder> findByIds(List<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    return entityManager.createQuery(
        "select o from PurchaseOrder o where o.id in :ids",
        PurchaseOrder.class
    )
    .setParameter("ids", ids)
    .getResultList();
}
```

Đối với điều kiện `NOT IN`, danh sách rỗng lại có ngữ nghĩa khác (“không loại trừ ID nào”), nên giải pháp phù hợp thường là **bỏ điều kiện lọc** thay vì trả danh sách rỗng. Phải quyết định theo ý nghĩa nghiệp vụ.

### Danh sách rất lớn

Khi `ids` có hàng chục nghìn phần tử, câu SQL sau khi mở rộng bind markers có thể quá dài hoặc vượt giới hạn tham số/IN-list của database. Cân nhắc chia lô theo ràng buộc hệ quản trị, tạm lưu các ID trong bảng tạm, join với bảng dữ liệu, hoặc thay đổi API truy vấn. Một collection parameter không tự giải quyết bài toán hiệu năng của IN-list rất lớn.

## 13. Tham số `LIKE` và ký tự đại diện

JPQL hỗ trợ `LIKE` tương tự SQL cho chuỗi:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.orderCode LIKE :pattern
```

Java:

```java
String userInput = "PO-";

TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.orderCode like :pattern",
    PurchaseOrder.class
);

query.setParameter("pattern", userInput + "%");
```

Ở đây ký tự `%` nằm trong **giá trị được bind** và có nghĩa wildcard của LIKE. Cách này an toàn hơn ghép trực tiếp chuỗi người dùng vào JPQL.

| Ký tự LIKE | Ý nghĩa thường dùng |
|---|---|
| `%` | Không hoặc nhiều ký tự |
| `_` | Chính xác một ký tự |
| `\` hoặc ký tự escape được khai báo | Cách escape phụ thuộc cú pháp `ESCAPE` và dialect |

**Bind parameter giúp tránh injection vào cú pháp truy vấn nhưng không tự escape wildcard LIKE.**

### Khi muốn tìm literal chứa `%` hoặc `_`

Nếu người dùng tìm ký tự `%` theo nghĩa “dấu phần trăm thật”, cần escape nó. Ví dụ chọn dấu `!` làm escape character:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.orderCode LIKE :pattern ESCAPE '!'
```

Code hỗ trợ:

```java
private static String escapeLike(String raw) {
    return raw.replace("!", "!!")
              .replace("%", "!%")
              .replace("_", "!_");
}
```

Bind:

```java
String pattern = "%" + escapeLike(userInput.trim()) + "%";

TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.orderCode like :pattern escape '!'",
    PurchaseOrder.class
);

query.setParameter("pattern", pattern);
```

Cách escape trên có ý nghĩa vì query khai `ESCAPE '!'`. Nếu thay ký tự escape ở JPQL thì phải sửa hàm escape tương ứng.

### Tìm kiếm không phân biệt hoa/thường

Một cách portable ở mức ngữ nghĩa JPQL:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE LOWER(o.orderCode) LIKE :pattern ESCAPE '!'
```

Java:

```java
String input = escapeLike(
    userInput.toLowerCase(Locale.ROOT)
);
query.setParameter("pattern", "%" + input + "%");
```

Điều này có thể giảm khả năng tận dụng index thông thường vì có hàm `LOWER` trên cột; các database có case-insensitive collation, functional index hoặc full-text search riêng. Chọn kỹ thuật phù hợp với yêu cầu tìm kiếm và dữ liệu thực tế.

**Tham số luôn biểu diễn giá trị chuỗi.** Không dùng `:pattern` thay cho một đoạn cú pháp SQL như `LIKE`, `LOWER` hoặc `ORDER BY`.

## 14. Tham số `NULL`: `= NULL` không giống `IS NULL`

Một lỗi logic phổ biến:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.orderCode = :code
```

và:

```java
query.setParameter("code", null);
```

Trong logic ba giá trị của SQL, so sánh thông thường với NULL không cho kết quả TRUE. Điều kiện kiểu `column = NULL` không chọn các hàng có NULL như `IS NULL`.

Nếu muốn lọc các hàng có thuộc tính nullable là NULL, viết:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.customer IS NULL
```

Trong ví dụ này `customer` đang bắt buộc nên truy vấn minh họa sẽ không trả dữ liệu hợp lệ; với một quan hệ nullable như `salesAgent` thì `o.salesAgent IS NULL` là tình huống thực tế.

### Điều kiện tùy chọn theo request

Giả sử filter status có thể vắng mặt. Có hai chiến lược.

**Chiến lược A: Chọn JPQL theo ngữ nghĩa**

```java
public List<PurchaseOrder> findOrders(OrderStatus status) {
    String jpql = "select o from PurchaseOrder o";

    if (status != null) {
        jpql += " where o.status = :status";
    }

    TypedQuery<PurchaseOrder> query =
        entityManager.createQuery(jpql, PurchaseOrder.class);

    if (status != null) {
        query.setParameter("status", status);
    }

    return query.getResultList();
}
```

Cách này giúp truy vấn không có điều kiện khi status null và không buộc database phải suy luận kiểu cho `NULL` placeholder.

**Chiến lược B: Điều kiện OR có tham số null**

```jpql
SELECT o
FROM PurchaseOrder o
WHERE (:status IS NULL OR o.status = :status)
```

và:

```java
query.setParameter("status", status);
```

Cách B đôi khi tiện, nhưng có thể gặp vấn đề suy luận kiểu NULL ở một số database/driver, ảnh hưởng query plan và khả năng dùng index. Với nhiều điều kiện tùy chọn, dựng JPQL có kiểm soát hoặc Criteria API thường dễ tối ưu hơn.

### Tham số lặp lại trong OR

Trong:

```jpql
WHERE (:status IS NULL OR o.status = :status)
```

`:status` chỉ là **một named parameter** dù xuất hiện hai lần. Chỉ cần một lời gọi `setParameter("status", status)`.

## 15. So sánh hai khoảng giá trị

Một điều kiện khoảng tổng tiền:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.totalAmount BETWEEN :fromAmount AND :toAmount
```

Java:

```java
BigDecimal from = new BigDecimal("100000.00");
BigDecimal to = new BigDecimal("500000.00");

if (from.compareTo(to) > 0) {
    throw new IllegalArgumentException("Invalid amount range");
}

List<PurchaseOrder> orders = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.totalAmount between :fromAmount and :toAmount",
    PurchaseOrder.class
)
.setParameter("fromAmount", from)
.setParameter("toAmount", to)
.getResultList();
```

`BETWEEN` bao gồm hai đầu mút. Đối với thời gian hoặc phân trang theo mốc, đôi khi `>= :from` và `< :to` tốt hơn để tránh trùng ở ranh giới; đối với số tiền, chọn theo quy tắc kinh doanh.

Đổi sang positional:

```jpql
WHERE o.totalAmount BETWEEN ?1 AND ?2
```

và:

```java
query.setParameter(1, from);
query.setParameter(2, to);
```

Nếu đảo thứ tự hai giá trị ở `setParameter`, query không có lỗi cú pháp nhưng có thể trả kết quả sai — một ví dụ điển hình về nhược điểm của positional parameters khi query dài.

## 16. `TypedQuery` và `Query`: cách gán giống nhau, kiểu kết quả khác nhau

API JPA có:

- `TypedQuery<T>`: biết kiểu kết quả, chẳng hạn `PurchaseOrder` hoặc `Long`.
- `Query`: kiểu truy vấn tổng quát, thường dùng cho bulk update/delete hoặc trường hợp kết quả động.

Ví dụ typed query:

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o where o.status = :status",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.NEW);
List<PurchaseOrder> result = query.getResultList();
```

Ví dụ COUNT:

```java
TypedQuery<Long> countQuery = entityManager.createQuery(
    "select count(o) from PurchaseOrder o " +
    "where o.status = :status",
    Long.class
);

Long count = countQuery
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();
```

Ví dụ bulk update:

```java
Query updateQuery = entityManager.createQuery(
    "update PurchaseOrder o " +
    "set o.status = :newStatus " +
    "where o.status = :oldStatus"
);

updateQuery.setParameter("newStatus", OrderStatus.CANCELLED);
updateQuery.setParameter("oldStatus", OrderStatus.NEW);

int affected = updateQuery.executeUpdate();
```

Đối với bulk JPQL update/delete, code cần transaction phù hợp. Bulk operations thường **bỏ qua việc đồng bộ từng managed entity qua dirty checking và lifecycle callbacks**, và có thể khiến persistence context đang giữ entity có state cũ. Không dùng chúng như một bản sao hoàn toàn của thao tác sửa managed entity.

Điểm chung: named/positional parameter vẫn được gán bằng `setParameter`.

## 17. `getResultList()`, `getSingleResult()` và tham số

Ví dụ tìm theo mã đơn duy nhất:

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.orderCode = :code",
    PurchaseOrder.class
);

query.setParameter("code", requestedCode);
```

Có thể gọi:

```java
List<PurchaseOrder> matches = query.getResultList();
```

hoặc:

```java
PurchaseOrder order = query.getSingleResult();
```

Sự khác nhau:

- `getResultList()` trả danh sách, có thể rỗng.
- `getSingleResult()` thường ném `NoResultException` nếu không có kết quả.
- `getSingleResult()` ném `NonUniqueResultException` nếu có nhiều hơn một kết quả theo hợp đồng.
- Không có kết quả **khác** với lỗi bind tham số hay lỗi database.
- Tùy phiên bản JPA có thêm API trả về single-result với semantics khác; cần xem framework đang dùng.

Nếu mục tiêu là “lấy tối đa một đơn hàng để hiển thị”, có thể:

```java
List<PurchaseOrder> matches = query
    .setMaxResults(1)
    .getResultList();

PurchaseOrder first = matches.isEmpty()
    ? null
    : matches.get(0);
```

Nhưng khi dữ liệu buộc phải unique theo nghiệp vụ, cần **UNIQUE constraint ở database** thay vì chỉ giới hạn một dòng truy vấn để che dữ liệu trùng.

## 18. Phân trang không phải là bind `LIMIT` trong JPQL

Ví dụ lấy các order đã thanh toán trong trang kết quả:

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = :status " +
    "order by o.createdAt desc, o.id desc",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.PAID);
query.setFirstResult(20);
query.setMaxResults(10);

List<PurchaseOrder> orders = query.getResultList();
```

Ý nghĩa: bỏ qua 20 kết quả đầu và lấy tối đa 10 kết quả tiếp theo.

JPA cung cấp `setFirstResult(...)` và `setMaxResults(...)` để phân trang portable thay vì giả định JPQL hỗ trợ cú pháp native SQL:

```sql
LIMIT :limit OFFSET :offset
```

Cú pháp SQL cụ thể do dialect/provider quyết định. Cần `ORDER BY` ổn định (ở ví dụ có thêm `id` làm tie-breaker) nếu muốn phân trang có kết quả dễ dự đoán.

### Kiểm tra dữ liệu phân trang

```java
if (page < 0 || pageSize <= 0 || pageSize > 100) {
    throw new IllegalArgumentException("Invalid page");
}

int firstResult = Math.multiplyExact(page, pageSize);
query.setFirstResult(firstResult);
query.setMaxResults(pageSize);
```

Đây là validation của API, độc lập với named/positional parameters. Không dựa vào việc bind parameter để chặn toàn bộ việc request truy vấn dữ liệu quá lớn.

## 19. Không thể bind tên cột, tên entity hoặc đoạn JPQL

Một nhầm lẫn quan trọng:

```jpql
SELECT o
FROM PurchaseOrder o
ORDER BY :sortColumn
```

và:

```java
query.setParameter("sortColumn", "createdAt");
```

không biến `:sortColumn` thành tên thuộc tính `o.createdAt`. **Tham số biểu diễn giá trị, không phải cú pháp định danh**. Tùy provider, query này có thể bị từ chối hoặc được diễn giải thành order by một biểu thức/giá trị, nhưng không đạt mục tiêu sắp xếp động theo tên field.

Tương tự, không thể viết:

```jpql
SELECT o FROM :entityName o
```

rồi bind một tên entity. Tên entity, property, join và toán tử phải là một phần của cú pháp JPQL đã xác định.

### Sắp xếp động bằng whitelist

Nếu người dùng được phép sắp theo mã hoặc thời điểm tạo:

```java
String orderBy = switch (sortField) {
    case "code" -> "o.orderCode";
    case "createdAt" -> "o.createdAt";
    case "amount" -> "o.totalAmount";
    default -> throw new IllegalArgumentException(
        "Unsupported sort field"
    );
};

String direction = descending ? "desc" : "asc";

String jpql =
    "select o from PurchaseOrder o " +
    "where o.status = :status " +
    "order by " + orderBy + " " + direction + ", o.id asc";

TypedQuery<PurchaseOrder> query =
    entityManager.createQuery(jpql, PurchaseOrder.class);

query.setParameter("status", status);
```

Cách này chỉ ghép những **đoạn cú pháp hardcoded đã qua whitelist**, không đưa chuỗi tên field không kiểm soát từ request vào JPQL.

Với truy vấn động phức tạp, dùng Criteria API hoặc Spring Data `Sort` với các ràng buộc property phù hợp có thể dễ bảo trì hơn.

## 20. Named query: tên truy vấn khác tên tham số

JPA cho phép khai báo `@NamedQuery`:

```java
@Entity
@NamedQuery(
    name = "PurchaseOrder.byStatus",
    query = "select o from PurchaseOrder o " +
            "where o.status = :status"
)
public class PurchaseOrder {
    // Các field và mapping như ví dụ trước.
}
```

Ở đây có **hai loại tên**:

- `PurchaseOrder.byStatus`: tên của **câu truy vấn được đặt sẵn**.
- `status` trong `:status`: tên của **tham số dữ liệu**.

Sử dụng:

```java
TypedQuery<PurchaseOrder> query =
    entityManager.createNamedQuery(
        "PurchaseOrder.byStatus",
        PurchaseOrder.class
    );

query.setParameter("status", OrderStatus.NEW);

List<PurchaseOrder> result = query.getResultList();
```

Không viết:

```java
query.setParameter("PurchaseOrder.byStatus", OrderStatus.NEW);
```

vì tên của named query không phải tên parameter.

Named query có thể được phân tích/kiểm tra bởi provider vào thời điểm khởi tạo tùy phiên bản và cấu hình; điều đó không thay đổi quy tắc gán tham số ở runtime.

## 21. Spring Data JPA: `@Query` với named parameters

Khi dùng Spring Data JPA:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.math.BigDecimal;
import java.util.List;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where o.status = :status
          and o.totalAmount >= :minimumTotal
        """)
    List<PurchaseOrder> findOrders(
        @Param("status") OrderStatus status,
        @Param("minimumTotal") BigDecimal minimumTotal
    );
}
```

Trong ví dụ:

- `:status` trong JPQL liên kết với method argument được đánh dấu `@Param("status")`.
- `:minimumTotal` tương tự liên kết với `@Param("minimumTotal")`.
- `@Param` là annotation của **Spring Data**, không phải `jakarta.persistence.Parameter`.
- Spring Data thực hiện binding vào JPA query khi repository method được gọi.

Gọi:

```java
List<PurchaseOrder> orders = repository.findOrders(
    OrderStatus.PAID,
    new BigDecimal("100000.00")
);
```

### Có thể bỏ `@Param` không?

Một số phiên bản/cấu hình Spring Data JPA hỗ trợ lấy tên tham số của method từ metadata Java khi compile với `-parameters`. Tuy nhiên, để ví dụ không phụ thuộc vào compiler metadata, **ghi rõ `@Param` là lựa chọn dễ hiểu**.

Tên trong `@Param` phải khớp với placeholder trong JPQL, không kèm dấu `:`.

## 22. Spring Data JPA: `@Query` với positional parameters

Cùng truy vấn có thể dùng vị trí:

```java
@Query("""
    select o from PurchaseOrder o
    where o.status = ?1
      and o.totalAmount >= ?2
    """)
List<PurchaseOrder> findOrders(
    OrderStatus status,
    BigDecimal minimumTotal
);
```

`?1` liên kết với **đối số thứ nhất của repository method**, `?2` với **đối số thứ hai**.

Đây là lựa chọn ngắn gọn cho query đơn giản. Nhưng khi method có nhiều argument cùng kiểu hoặc thứ tự thay đổi, rất dễ bind nhầm.

Ví dụ:

```java
@Query("""
    select o from PurchaseOrder o
    where o.totalAmount between ?1 and ?2
    """)
List<PurchaseOrder> betweenAmounts(
    BigDecimal minimum,
    BigDecimal maximum
);
```

Nếu đổi thứ tự arguments mà quên cập nhật JPQL, code vẫn có thể compile nhưng kết quả sai. Named parameters làm quan hệ giữa tham số và ngữ nghĩa rõ hơn.

### Native query khác JPQL

Trong Spring Data:

```java
@Query(
    value = "select * from purchase_orders where order_code = :code",
    nativeQuery = true
)
List<PurchaseOrder> findNativeByCode(@Param("code") String code);
```

Đây là **native SQL** vì `nativeQuery = true`, nên dùng tên bảng/cột SQL. Cú pháp parameter có thể được Spring Data/provider hỗ trợ, nhưng khả năng bind collection, kiểu database-specific và các biểu thức native không hoàn toàn giống JPQL portable.

Đừng đổi `nativeQuery = true` chỉ để “sửa” một câu JPQL viết sai tên entity/property.

## 23. `@Query` cập nhật dữ liệu với `@Modifying`

Spring Data JPA cần đánh dấu truy vấn thay đổi dữ liệu:

```java
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Modifying
@Query("""
    update PurchaseOrder o
    set o.status = :newStatus
    where o.status = :oldStatus
    """)
int replaceStatus(
    @Param("oldStatus") OrderStatus oldStatus,
    @Param("newStatus") OrderStatus newStatus
);
```

Lời gọi cần nằm trong transaction phù hợp, thường do service cung cấp:

```java
@Transactional
public int cancelNewOrders() {
    return repository.replaceStatus(
        OrderStatus.NEW,
        OrderStatus.CANCELLED
    );
}
```

Hãy nhớ:

- Parameter binding trong `UPDATE` giống query `SELECT`.
- `executeUpdate()`/return value thể hiện số hàng bị ảnh hưởng theo cách provider báo.
- Bulk update có thể bỏ qua cơ chế dirty checking đối với từng managed entity và không tự cập nhật những instance đã có trong persistence context.
- Nếu entity có `@Version`, bulk JPQL không mặc nhiên thực hiện cùng version management như cập nhật từng entity thông thường.
- Nếu cần cập nhật state hiện đang managed, cân nhắc thao tác trên entity rồi flush thay vì bulk update.

Phần quan trọng của bài vẫn là **bind đúng dữ liệu**; lựa chọn bulk update phụ thuộc vòng đời entity và tính nhất quán.

## 24. Criteria API: tham số khai báo bằng đối tượng `ParameterExpression`

Khi JPQL phải có nhiều điều kiện động, Criteria API có thể diễn tả truy vấn bằng Java types thay vì nối chuỗi.

Ví dụ lọc theo status:

```java
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.ParameterExpression;
import jakarta.persistence.criteria.Root;

CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

ParameterExpression<OrderStatus> statusParam =
    cb.parameter(OrderStatus.class, "status");

cq.select(order)
  .where(cb.equal(order.get("status"), statusParam));

TypedQuery<PurchaseOrder> query =
    entityManager.createQuery(cq);

query.setParameter("status", OrderStatus.PAID);

List<PurchaseOrder> results = query.getResultList();
```

Hoặc bind qua chính đối tượng `ParameterExpression`:

```java
query.setParameter(statusParam, OrderStatus.PAID);
```

Đây vẫn là **parameter binding**: phần truy vấn mô tả expression, dữ liệu được truyền riêng.

Với metamodel tĩnh được sinh phù hợp, có thể thay `order.get("status")` bằng thuộc tính kiểu an toàn hơn, giảm lỗi khi đổi tên field.

### Khi nào Criteria có lợi?

- Nhiều điều kiện tùy chọn.
- Chỉ thêm predicate khi parameter tương ứng có giá trị.
- Tạo query theo filter object.
- Dùng CriteriaBuilder thay vì nối chuỗi JPQL phức tạp.
- Tích hợp Specifications trong Spring Data JPA.

Criteria không loại bỏ nhu cầu validation, authorization, index, fetch plan hay kiểm soát query quá lớn.

## 25. Truy vấn động: chỉ tạo placeholder cho điều kiện tồn tại

Giả sử form tìm kiếm cho phép lọc:

- `status`: có thể null.
- `minimumTotal`: có thể null.
- `customerId`: có thể null.

Có thể xây query theo điều kiện đã cung cấp:

```java
public List<PurchaseOrder> search(
        OrderStatus status,
        BigDecimal minimumTotal,
        Long customerId) {

    StringBuilder jpql = new StringBuilder(
        "select o from PurchaseOrder o where 1 = 1"
    );

    if (status != null) {
        jpql.append(" and o.status = :status");
    }
    if (minimumTotal != null) {
        jpql.append(" and o.totalAmount >= :minimumTotal");
    }
    if (customerId != null) {
        jpql.append(" and o.customer.id = :customerId");
    }

    jpql.append(" order by o.createdAt desc, o.id desc");

    TypedQuery<PurchaseOrder> query =
        entityManager.createQuery(
            jpql.toString(), PurchaseOrder.class
        );

    if (status != null) {
        query.setParameter("status", status);
    }
    if (minimumTotal != null) {
        query.setParameter("minimumTotal", minimumTotal);
    }
    if (customerId != null) {
        query.setParameter("customerId", customerId);
    }

    query.setMaxResults(100);
    return query.getResultList();
}
```

Đoạn này **chỉ nối những đoạn JPQL cố định, được kiểm soát trong code**. Nó không nối giá trị `status`, `customerId` hay `minimumTotal` vào chuỗi.

Ưu điểm: không cố bind null cho điều kiện không dùng; query plan có thể dễ tối ưu hơn so với một chuỗi gồm nhiều OR-NULL predicate.

Nhược điểm: khi có nhiều nhóm AND/OR và JOIN, nối chuỗi thủ công dễ sai ngoặc hoặc alias. Khi độ phức tạp tăng, Criteria API hoặc một query builder có ràng buộc thường đáng cân nhắc.

## 26. Tham số với phép đếm, HAVING và subquery

Parameter binding không chỉ áp dụng trong `WHERE` đơn giản.

### Trong `HAVING`

Tìm Customer có ít nhất một số lượng đơn hàng:

```jpql
SELECT c.id, COUNT(o)
FROM PurchaseOrder o
JOIN o.customer c
GROUP BY c.id
HAVING COUNT(o) >= :minimumOrders
```

Java:

```java
List<Object[]> rows = entityManager.createQuery(
    "select c.id, count(o) " +
    "from PurchaseOrder o join o.customer c " +
    "group by c.id having count(o) >= :minimumOrders",
    Object[].class
)
.setParameter("minimumOrders", 5L)
.getResultList();
```

`COUNT` trong JPQL trả giá trị kiểu `Long`; truyền `5L` biểu diễn rõ ngữ nghĩa số lượng.

### Trong subquery

Ví dụ tìm đơn có tổng tiền cao hơn tổng trung bình của những đơn ở một trạng thái nhất định:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.totalAmount > (
    SELECT AVG(x.totalAmount)
    FROM PurchaseOrder x
    WHERE x.status = :referenceStatus
)
```

Bind:

```java
query.setParameter("referenceStatus", OrderStatus.PAID);
```

Tham số bên trong subquery được bind như tham số ở query ngoài; nếu cùng tên được tham chiếu nhiều nơi trong cùng query, nó là cùng một named parameter.

### Trong phép `DELETE`

```jpql
DELETE FROM PurchaseOrder o
WHERE o.status = :status
  AND o.createdAt < :beforeTime
```

Code cần transaction, `executeUpdate()` và hiểu các ảnh hưởng bulk delete đối với managed entities và foreign keys. Tên/vị trí tham số hoạt động giống các ví dụ khác.

## 27. Có thể truy xuất metadata của tham số

JPA cung cấp API để đọc metadata của parameters mà query nhận:

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = :status",
    PurchaseOrder.class
);

Set<Parameter<?>> parameters = query.getParameters();
```

Với query có named parameter, metadata có thể chứa `getName()`. Với positional parameter, có thể có `getPosition()`.

Ví dụ:

```java
for (Parameter<?> parameter : query.getParameters()) {
    System.out.println("Name: " + parameter.getName());
    System.out.println("Position: " + parameter.getPosition());
}
```

Ý nghĩa:

- Named parameter thường có name và không có position.
- Positional parameter thường có position và không có name.
- Provider có thể suy luận type theo ngữ cảnh hoặc báo type không xác định trong vài trường hợp.

Đây là API hữu ích cho framework/debugging, nhưng trong code nghiệp vụ thường chỉ cần bind bằng tên/vị trí đã biết.

### Tránh dùng introspection để che vấn đề thiết kế

Nếu một query được xây dựng bằng code của ứng dụng, không cần lấy tất cả parameter names từ metadata rồi gán một map giá trị mơ hồ. Với truy vấn cố định, các lời gọi `setParameter` tường minh có ý nghĩa nghiệp vụ rõ ràng hơn.

## 28. Không nên dùng lại `Query` giữa các luồng

Một `EntityManager` không được coi là thread-safe theo hợp đồng JPA. Query được tạo từ EntityManager có trạng thái bind parameters, pagination, hints... và không nên chia sẻ tùy tiện giữa các request hoặc luồng.

Anti-pattern:

```java
// Không nên giữ instance query có trạng thái bind toàn cục:
private static TypedQuery<PurchaseOrder> sharedQuery;
```

Rồi mỗi request:

```java
sharedQuery.setParameter("status", requestStatus);
return sharedQuery.getResultList();
```

Hai request có thể ghi đè parameter của nhau và EntityManager gắn với query cũng có vấn đề concurrency.

Cách đúng: **tạo query object cho mỗi đơn vị công việc** từ EntityManager thích hợp. Nếu muốn tái sử dụng cấu trúc truy vấn, dùng hằng số JPQL, `@NamedQuery` hoặc repository method, không dùng một `TypedQuery` instance mutable chung cho mọi request.

## 29. Cú pháp tham số dễ bị nhầm với chuỗi literal

Ví dụ:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.orderCode = ':code'
```

Ở đây `':code'` nằm **trong dấu nháy chuỗi JPQL**, nên được hiểu là một chuỗi literal gồm các ký tự `:code`, không phải một named parameter.

Đúng:

```jpql
WHERE o.orderCode = :code
```

Tương tự:

```jpql
WHERE o.orderCode LIKE '%:keyword%'
```

không bind `:keyword` theo ý định. Cần viết:

```jpql
WHERE o.orderCode LIKE :pattern
```

và bind giá trị có wildcard:

```java
query.setParameter("pattern", "%" + keyword + "%");
```

Nếu muốn tìm literal `%` hoặc `_`, dùng cơ chế `ESCAPE` như phần trước.

## 30. Tên tham số phân biệt chữ hoa/chữ thường

Ví dụ JPQL:

```jpql
WHERE o.status = :orderStatus
```

Bind đúng:

```java
query.setParameter("orderStatus", OrderStatus.PAID);
```

Có thể sai:

```java
query.setParameter("orderstatus", OrderStatus.PAID);
query.setParameter("OrderStatus", OrderStatus.PAID);
```

Named parameters là định danh, thường được phân biệt hoa/thường. Hãy dùng quy ước nhất quán như `camelCase` và tránh những tên quá gần nhau về cách viết.

Cần giữ chính xác **tên field trong JPQL** và **tên parameter**. Chúng là hai loại tên khác nhau:

```jpql
WHERE o.orderCode = :code
```

- `o.orderCode`: property Java, phải tồn tại trên entity.
- `code`: tên parameter do người viết query chọn; có thể khác property.

## 31. Gán thiếu tham số hoặc gán sai tên

Giả sử query:

```jpql
WHERE o.status = :status
  AND o.totalAmount >= :minimumTotal
```

Nhưng chỉ bind:

```java
query.setParameter("status", OrderStatus.PAID);
query.getResultList();
```

Tham số `minimumTotal` chưa được gán. Provider sẽ không tự biến nó thành `NULL` chỉ vì ứng dụng quên bind; thường báo lỗi query parameter chưa được cung cấp trước hoặc khi thực thi.

Một lỗi khác:

```java
query.setParameter("minTotal", new BigDecimal("100000.00"));
```

trong khi JPQL khai `:minimumTotal`. Đây là tham số **không tồn tại theo tên đó**.

Các exception có thể là `IllegalArgumentException` hoặc exception provider-specific như `QueryParameterException`, tùy tình huống và phiên bản. Không nên viết logic chỉ bắt một tên exception rồi cho rằng mọi bind error đều thuộc nhóm đó.

### Hướng xử lý

- Giữ tên parameter gần code khai báo hoặc dùng constants/abstraction khi cần.
- Với query có điều kiện, chỉ bind tham số khi điều kiện tương ứng được thêm vào query.
- Dùng named parameters cho query nhiều điều kiện để tránh nhầm index.
- Dùng API repository có `@Param` rõ ràng khi làm việc với Spring Data JPA.

## 32. Sai kiểu dữ liệu và sai ngữ nghĩa tham số

JPQL:

```jpql
WHERE o.totalAmount >= :minAmount
```

nhưng code:

```java
query.setParameter("minAmount", OrderStatus.PAID);
```

có giá trị không tương thích với property số tiền. Provider có thể báo lỗi type binding/parameter mismatch.

Những sai lầm tương tự:

- Bind `String "2026-01-01"` vào `LocalDateTime` mà không parse.
- Bind `String "PAID"` vào enum property thay vì `OrderStatus.PAID`.
- Bind entity `Customer` vào predicate `o.customer.id = :id`.
- Bind `Long` vào predicate `o.customer = :customer`.
- Bind một chuỗi có dấu phẩy vào `IN :ids` thay vì collection đúng kiểu.
- Bind `null` rồi dùng toán tử `=` thay vì thiết kế điều kiện NULL.

JPA không bảo đảm tất cả sai kiểu đều được phát hiện đúng tại `setParameter()`; lỗi có thể xuất hiện khi query được biên dịch, thực thi hoặc khi database kiểm tra giá trị.

## 33. Kiểm tra kết quả thực tế khi câu query có nhiều tham số

Ví dụ truy vấn gồm bốn điều kiện:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :status
  AND o.totalAmount >= :minimumTotal
  AND o.createdAt >= :fromTime
  AND o.createdAt < :toTime
ORDER BY o.createdAt DESC
```

Nếu kết quả rỗng, đừng lập tức kết luận query syntax hoặc JPA lỗi. Có thể:

1. Enum status bind không đúng giá trị.
2. `minimumTotal` cao hơn dữ liệu.
3. Khoảng ngày không giao với dữ liệu thực.
4. `fromTime >= toTime`.
5. Timezone của API khác timezone lưu dữ liệu.
6. Truy vấn bị lọc thêm bởi tenant/security/provider filters.
7. Dữ liệu đang được sửa trong transaction và flush mode ảnh hưởng kết quả.
8. Database chưa có những hàng đã được mong đợi.

Khi chẩn đoán, kiểm tra **giá trị và kiểu từng parameter** (trong môi trường an toàn), predicate semantics và SQL được sinh ra. Không vô hiệu hóa parameter binding để nối chuỗi cho “dễ debug” vì sẽ tạo nguy cơ injection và lỗi định dạng.

## 34. SQL logging và dữ liệu nhạy cảm

Với Hibernate 6 trong Spring Boot, ở môi trường phát triển có thể dùng:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

- `org.hibernate.SQL` giúp quan sát SQL đã được sinh.
- Logging bind parameter có thể cho thấy giá trị và kiểu JDBC mà provider dùng.
- Các giá trị bind có thể chứa thông tin khách hàng, email, mã định danh, token hoặc dữ liệu tài chính.
- Không bật TRACE bind logging bừa bãi trong production hoặc log chia sẻ không có kiểm soát.

Log query không chứng minh transaction đã commit. Query có thể phát sinh trong transaction rollback, hoặc ORM có thể flush trước khi SELECT tùy flush mode.

### Tham số trong log SQL

Một query JPQL:

```jpql
WHERE o.status = :status
```

có thể biến thành SQL dạng:

```sql
WHERE o.status = ?
```

vì Hibernate/JDBC dùng bind marker riêng. Việc không thấy `:status` trong SQL log **không có nghĩa query mất tham số**: tên tham số ở tầng JPQL được ánh xạ thành vị trí bind của câu SQL JDBC.

## 35. Tác động hiệu năng: named vs positional không phải điểm chính

Điều thường tác động mạnh hơn đến hiệu năng:

- Index trên các cột được lọc hoặc sắp xếp.
- Tính chọn lọc của `status`, `customer_id`, `created_at`.
- JOIN và fetch plan.
- Việc sử dụng `LOWER()`, `LIKE '%keyword%'`, `OR :param IS NULL`.
- Kích thước danh sách `IN`.
- Pagination và số hàng trả về.
- Query plan và thống kê database.
- Cache của JPA/provider.
- Phân vùng dữ liệu theo tenant, permission và workload.

Một query có named parameters:

```jpql
WHERE o.customer.id = :customerId
  AND o.createdAt >= :from
```

và positional tương đương:

```jpql
WHERE o.customer.id = ?1
  AND o.createdAt >= ?2
```

thường có thể được dịch thành SQL với cùng điều kiện. Không nên đổi sang positional chỉ vì hy vọng database chạy nhanh hơn.

## 36. Bảo mật: bind values là cần thiết nhưng chưa đủ

Parameter binding giúp dữ liệu không bị ghép trực tiếp vào **cú pháp** JPQL ở các vị trí giá trị. Tuy nhiên, nó không tự:

- Xác thực người dùng.
- Kiểm tra quyền đọc đơn hàng của người khác.
- Áp tenant isolation.
- Giới hạn dữ liệu quá lớn.
- Chặn việc lạm dụng wildcard LIKE tạo truy vấn tốn tài nguyên.
- Bảo đảm tên field sort do client yêu cầu là an toàn.
- Bảo vệ các truy vấn được ghép động không kiểm soát ở phần cú pháp.

Ví dụ ứng dụng đa tenant:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.customer.id = :customerId
  AND o.tenantId = :tenantId
```

Ở đây `tenantId` là property **giả định có tồn tại** trong một phiên bản entity đa tenant; nó không nằm trong class PurchaseOrder tối giản đầu bài.

Khi triển khai thực tế, giá trị `tenantId` cần lấy từ **ngữ cảnh xác thực đáng tin cậy**, không chỉ dựa vào field tenantId mà client tự gửi. Binding ngăn thay cú pháp nhưng không ngăn người dùng cố truy vấn tenant khác bằng một ID tùy ý.

Với dynamic `ORDER BY`, whitelist các property và hướng sắp; không ghép request string thô thành cú pháp JPQL.

## 37. Ví dụ repository service hoàn chỉnh dùng named parameters

Một chức năng lọc đơn hàng theo trạng thái và tổng tiền:

```java
public record OrderSearchRequest(
    OrderStatus status,
    BigDecimal minimumTotal
) {}
```

Repository:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where o.status = :status
          and o.totalAmount >= :minimumTotal
        order by o.createdAt desc, o.id desc
        """)
    List<PurchaseOrder> findByStatusAndAmount(
        @Param("status") OrderStatus status,
        @Param("minimumTotal") BigDecimal minimumTotal
    );
}
```

Service:

```java
@Service
public class OrderSearchService {

    private final PurchaseOrderRepository orders;

    public OrderSearchService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public List<PurchaseOrder> search(OrderSearchRequest request) {
        if (request.status() == null) {
            throw new IllegalArgumentException("Status required");
        }

        BigDecimal minimum = request.minimumTotal();
        if (minimum == null || minimum.signum() < 0) {
            throw new IllegalArgumentException(
                "Minimum total must be nonnegative"
            );
        }

        return orders.findByStatusAndAmount(
            request.status(), minimum
        );
    }
}
```

Trong REST API, thường nên trả DTO thay vì entity trực tiếp để tránh lazy loading ngoài transaction và tiết lộ các trường không cần thiết. Ví dụ service này tập trung vào parameter binding, nên để nguyên kiểu trả entity của repository.

### Phiên bản positional tương đương

```java
@Query("""
    select o from PurchaseOrder o
    where o.status = ?1
      and o.totalAmount >= ?2
    order by o.createdAt desc, o.id desc
    """)
List<PurchaseOrder> findByStatusAndAmount(
    OrderStatus status,
    BigDecimal minimumTotal
);
```

Nhận xét: cả hai được gọi bằng cùng hai argument Java. Nếu method có nhiều tham số, named parameters có xu hướng giảm nhầm lẫn trong bảo trì.

## 38. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách khắc phục |
|---|---|---|
| `Could not locate named parameter ...` | Tên ở `setParameter` không giống `:name` trong JPQL | Dùng đúng tên, không có dấu `:`. |
| `Named parameter not bound` | Query được thực thi trước khi gán một parameter | Bind đầy đủ các parameter thực sự xuất hiện. |
| Positional parameter `?0` lỗi | JPQL bắt đầu đánh số từ 1 | Dùng `?1`, `?2`... |
| Dùng `setParameter(0, ...)` | Nhầm với index Java bắt đầu từ 0 | Dùng vị trí 1 cho `?1`. |
| Trộn `:status` và `?1` | Trộn hai hệ thống parameter | Chọn một cách trong mỗi query. |
| Query cho kết quả sai khi thay method arguments | Positional index không khớp ý nghĩa | Rà mapping `?1`/argument thứ nhất, cân nhắc named parameters. |
| `:status` trong dấu nháy không được bind | Nó là string literal | Bỏ dấu nháy: `= :status`. |
| `LIKE '%:term%'` không hoạt động | Parameter bị đặt trong string literal | Dùng `LIKE :pattern` rồi bind wildcard. |
| Input `%` cho LIKE trả quá nhiều hàng | Wildcard không được escape theo nghĩa literal | Dùng `ESCAPE` và escape user text khi cần literal search. |
| `= :value` với value null không tìm hàng null | SQL NULL cần `IS NULL` | Dựng predicate đúng semantics. |
| `IN :ids` với ids rỗng bị lỗi | SQL/provider xử lý danh sách rỗng khác nhau | Xử lý trường hợp rỗng trước. |
| Bind enum bằng String gặp lỗi type | Property là enum Java | Bind enum constant đúng kiểu. |
| Bind ID vào association parameter gặp type mismatch | `o.customer = :customer` mong entity | Dùng entity reference hoặc đổi predicate sang `o.customer.id`. |
| `ORDER BY :field` không sắp theo field | Parameter không thay tên property | Whitelist field rồi tạo cú pháp có kiểm soát. |
| `@Query` named parameter không tìm thấy | `@Param` không khớp, hoặc compiler metadata thiếu | Khai `@Param("...")` tường minh. |
| `@Query` JPQL báo table/column không hợp lệ | Dùng tên SQL thay entity/property | Dùng `PurchaseOrder` và `o.orderCode`, không dùng tên bảng/cột. |
| Native query không bind collection như JPQL | Cơ chế provider/native SQL khác | Xem khả năng bind collection theo dialect/provider. |
| SQL log chỉ thấy `?` mà không có `:status` | Provider dịch named JPQL parameter sang JDBC marker | Đây thường là hành vi bình thường. |
| Hai request ảnh hưởng parameter của nhau | Dùng chung mutable Query/EntityManager giữa luồng | Tạo query theo transaction/request; không share Query object. |
| Không thấy hàng vừa ghi trong kết quả | Flush mode/transaction hoặc logic filter | Xem thời điểm flush, query và transaction. |

## 39. Các câu hỏi tự kiểm tra

**Câu 1.** Trong query `WHERE o.status = :status`, lời gọi nào đúng?

```java
// Đúng:
query.setParameter("status", OrderStatus.PAID);

// Sai vì đặt dấu : trong tên:
query.setParameter(":status", OrderStatus.PAID);
```

**Câu 2.** `?1` tương ứng với index nào của `setParameter`?

```java
query.setParameter(1, value);
```

Không phải 0.

**Câu 3.** Nếu `:keyword` xuất hiện hai lần trong cùng query thì bind mấy lần?

Một lần bằng `setParameter("keyword", value)` là đủ, vì cả hai chỗ dùng cùng named parameter.

**Câu 4.** Có thể bind tên property cho `ORDER BY :field` không?

Không theo mục tiêu đổi cột sắp xếp. Parameter đại diện giá trị; tên field phải được lựa chọn trong cú pháp JPQL có kiểm soát, ví dụ whitelist hoặc Criteria.

**Câu 5.** Có thể dùng `setParameter("status", null)` với `o.status = :status` để tìm hàng có status NULL không?

Không. So sánh với SQL NULL qua `=` không có cùng ngữ nghĩa với `IS NULL`. Chọn predicate phù hợp.

**Câu 6.** Nếu `o.status` là enum `OrderStatus` nhưng cột database lưu VARCHAR, nên truyền gì?

Truyền `OrderStatus.PAID`, vì parameter tương ứng property enum của JPA. Provider xử lý mapping enum xuống SQL.

**Câu 7.** Khi `ids` rỗng, có nên luôn gọi query `IN :ids` không?

Không nên phụ thuộc vào hành vi provider/database với empty collection. Xử lý ngữ nghĩa empty list ở application.

**Câu 8.** Named parameters có tự ngăn người dùng truy cập đơn của tenant khác không?

Không. Binding chỉ tách giá trị khỏi cú pháp; authorization và tenant isolation phải được thiết kế riêng.

## 40. Tổng kết: chọn cách bind rõ nghĩa và an toàn

Cùng một yêu cầu “lấy các đơn PAID có tổng tiền tối thiểu 100.000” có hai phiên bản.

**Named parameters:**

```java
List<PurchaseOrder> orders = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = :status " +
    "and o.totalAmount >= :minimumTotal",
    PurchaseOrder.class
)
.setParameter("status", OrderStatus.PAID)
.setParameter("minimumTotal", new BigDecimal("100000.00"))
.getResultList();
```

**Positional parameters:**

```java
List<PurchaseOrder> orders = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = ?1 " +
    "and o.totalAmount >= ?2",
    PurchaseOrder.class
)
.setParameter(1, OrderStatus.PAID)
.setParameter(2, new BigDecimal("100000.00"))
.getResultList();
```

Cần giữ riêng năm nguyên tắc:

1. **Tham số theo tên dùng `:name` trong JPQL và `setParameter("name", value)` trong Java.**
2. **Tham số theo vị trí dùng `?1`, `?2`... và `setParameter(1, value)`, `setParameter(2, value)`...; vị trí bắt đầu từ 1.**
3. **Không trộn named và positional parameters trong cùng query.** Named thường dễ bảo trì hơn khi nhiều điều kiện.
4. **Bind đúng kiểu và đúng ngữ nghĩa:** enum, số tiền, thời gian, association, `IN`, `LIKE`, `NULL` đều có quy tắc riêng.
5. **Bind chỉ thay thế giá trị, không thay cú pháp.** Với identifier/sort động, dùng whitelist hoặc Criteria API; với dữ liệu người dùng, luôn giữ authorization và validation.

Khi hiểu rõ sự khác nhau giữa `:status` và `?1`, bạn có thể viết JPQL dễ đọc, tránh nhầm parameter, giảm nguy cơ injection, hỗ trợ truy vấn linh hoạt và kiểm soát tốt hơn hoạt động truy cập dữ liệu trong ứng dụng ORM/JPA.
