# Tham số hóa JPQL và native SQL để tránh ghép giá trị không tin cậy

Trong ứng dụng truy cập dữ liệu quan hệ qua **Jakarta Persistence (JPA)**, truy vấn thường phải nhận dữ liệu từ HTTP request, message queue, file import, CSV, cookie, header hoặc một hệ thống tích hợp. Những giá trị đó có thể là email, từ khóa tìm kiếm, mã đơn hàng, danh sách ID hay khoảng thời gian.

Một lỗi nguy hiểm là **đặt thẳng giá trị không tin cậy vào chuỗi JPQL hoặc SQL**:

```java
String jpql =
    "SELECT u FROM UserAccount u WHERE u.email = '"
    + emailFromRequest
    + "'";

List<UserAccount> users =
    em.createQuery(jpql, UserAccount.class)
      .getResultList();
```

Nếu input chứa dấu nháy hoặc cú pháp có ý nghĩa với ngôn ngữ truy vấn, dữ liệu có thể làm thay đổi cấu trúc câu lệnh thay vì được so sánh như một giá trị thông thường. Hậu quả có thể là đọc dữ liệu ngoài dự kiến, sửa/xóa nhầm dữ liệu, bỏ qua điều kiện lọc hoặc gây lỗi và lộ thông tin.

Cách viết đúng là dùng **tham số truy vấn (bind parameters)**:

```java
List<UserAccount> users = em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.email = :email
    """,
    UserAccount.class
)
.setParameter("email", emailFromRequest)
.getResultList();
```

Giá trị được truyền riêng khỏi cấu trúc truy vấn. Kể cả khi nó chứa dấu nháy, dấu chấm phẩy hay những từ giống từ khóa SQL, giá trị vẫn được xử lý như **dữ liệu**, không trở thành điều kiện JPQL bổ sung.

Bài học thuộc chủ đề **Data Persistence Relational Access ORM JPA**, chương **Bảo mật dữ liệu**, với đề mục trực tiếp **“Tham số hóa JPQL và native SQL để tránh ghép giá trị không tin cậy”**.

Sau bài, người học có thể:

1. Nhận diện lỗi ghép input vào JPQL/native SQL.
2. Sử dụng named và positional parameters đúng chỗ với `EntityManager`.
3. Phân biệt cú pháp JPQL (entity/attribute) và native SQL (table/column).
4. Dùng Criteria API để cấu trúc động không đi qua string concatenation tùy tiện.
5. Biết **tham số không thể thay tên bảng, tên cột, keyword hoặc hướng `ORDER BY`**.
6. Xây dựng allowlist cho sorting, filtering và dynamic SQL structure.
7. Escape wildcard `%`, `_` và escape character trong `LIKE`.
8. Xử lý `IN`, danh sách rỗng, `NULL`, kiểu dữ liệu và pagination.
9. Không nhầm query parameterization với authorization, tenant isolation hoặc validation.
10. Thiết kế kiểm thử an toàn cho input chứa ký tự đặc biệt và các đường truy vấn thực.
11. Hiểu tác động đến performance, statement reuse, logging và exception handling.

**Nguyên tắc trung tâm:** *Giữ cấu trúc truy vấn do ứng dụng kiểm soát; truyền mọi giá trị không tin cậy qua tham số có kiểu phù hợp. Những thành phần không thể bind phải được chọn từ allowlist đóng, không được lấy trực tiếp từ input.*

---

## 1. SQL injection và JPQL injection bắt đầu từ việc trộn mã với dữ liệu

Một câu truy vấn là một ngôn ngữ có cấu trúc:

```sql
SELECT *
FROM user_accounts
WHERE tenant_id = 10
  AND email = 'alice@example.com';
```

Các từ khóa `SELECT`, `FROM`, `WHERE`, tên cột, toán tử và các dấu phân cách có **ý nghĩa cú pháp**. `alice@example.com` là **giá trị dữ liệu**.

Khi lập trình viên ghép giá trị vào chuỗi SQL:

```java
String sql =
    "SELECT * FROM user_accounts WHERE email = '"
    + input
    + "'";
```

giá trị input trở thành một phần của **nguồn SQL** trước khi database parser phân tích.

Điều tương tự xảy ra với JPQL:

```java
String jpql =
    "SELECT u FROM UserAccount u "
    + "WHERE u.email = '" + input + "'";
```

JPA provider cần parse JPQL, chuyển nó thành SQL và gửi xuống database. Nếu input đã được ghép vào JPQL source, provider **không có cơ sở để phân biệt phần nào là template tin cậy và phần nào vốn là dữ liệu**.

### 1.1. Ranh giới tin cậy

Có thể hình dung:

```text
Untrusted user input
        |
        |   Cách SAI: nối vào JPQL/SQL text
        v
Query source text bị thay đổi
        |
        v
JPQL/SQL parser xử lý input như cú pháp
```

Cách đúng:

```text
Trusted query template ──────> JPQL/SQL parser
                                      |
Untrusted input ──────────────> Bind parameter
                                      |
                                      v
                          Execute với data value
```

**Không có nghĩa dùng tham số sẽ sửa mọi lỗ hổng bảo mật.** Nó tập trung bảo vệ ranh giới **dữ liệu–cú pháp** tại query API.

### 1.2. Mã từ upstream service cũng có thể không tin cậy

“Không tin cậy” không chỉ có input do người dùng cuối gõ:

- CSV upload.
- Header/request query string.
- Một message trong queue.
- Dữ liệu cũ đã lưu trong database.
- Response từ một service khác.
- Cấu hình do admin không chuyên kỹ thuật nhập.
- Tên file hoặc ID được chuyển qua nhiều tầng.
- Tham số truyền vào job/scheduler.

Một giá trị đã được lưu trong DB không tự trở thành trusted SQL fragment khi ứng dụng đọc lại và ghép vào câu query sau này. Đó có thể là **second-order injection**.

---

## 2. Mô hình ví dụ xuyên suốt

Dùng một entity tài khoản và một entity đơn hàng để minh họa.

### 2.1. UserAccount entity

```java
package com.example.security.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;

@Entity
@Table(
    name = "user_accounts",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_accounts_tenant_email",
        columnNames = {"tenant_id", "email"}
    )
)
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "email", nullable = false, length = 320)
    private String email;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected UserAccount() {
    }

    public UserAccount(
            Long tenantId,
            String email,
            String displayName,
            Instant createdAt) {
        this.tenantId = tenantId;
        this.email = email;
        this.displayName = displayName;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

### 2.2. PurchaseOrder entity

```java
package com.example.security.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_code", nullable = false)
    private String orderCode;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Các entity chỉ phục vụ bài học bảo mật truy vấn. Để chạy một ứng dụng hoàn chỉnh, cần constructor/domain methods, DDL/migrations, repositories và business rules tương ứng.

### 2.3. Bảng database tương ứng

Ví dụ DDL PostgreSQL:

```sql
CREATE TABLE user_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uk_accounts_tenant_email
        UNIQUE (tenant_id, email)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    order_code VARCHAR(255) NOT NULL,
    total_amount NUMERIC(19,2) NOT NULL
);
```

**Lưu ý quan trọng về multi-tenant:** hai bảng đều có `tenant_id`. Tham số hóa giúp không đổi cú pháp query, nhưng **không tự ngăn người dùng truy cập tenant khác**. Cần authorization/tenant scoping độc lập.

---

# Phần I — Tham số hóa JPQL

## 3. Lỗi ghép giá trị vào JPQL

Một phương thức dễ mắc lỗi:

```java
public List<UserAccount> findByEmailUnsafe(String input) {
    String jpql =
        "SELECT u FROM UserAccount u "
        + "WHERE u.email = '" + input + "'";

    return em.createQuery(jpql, UserAccount.class)
        .getResultList();
}
```

Với input bình thường, code có thể “chạy được” và khiến người viết chủ quan.

Nhưng các giá trị có dấu nháy đơn hoặc chuỗi giống toán tử truy vấn có thể làm JPQL:

- Bị lỗi cú pháp.
- Thay đổi nghĩa của biểu thức `WHERE`.
- Vô hiệu hóa một phần điều kiện.
- Trả nhiều bản ghi hơn mong đợi.
- Gây lộ dữ liệu nếu query thiếu các hàng rào authorization khác.

Không nên tự “sửa” bằng cách chặn một số từ khóa hoặc dấu nháy. Đó là chiến lược blacklist không đầy đủ.

### 3.1. Cách đúng với named parameter

```java
public List<UserAccount> findByEmailSafe(String input) {
    return em.createQuery(
        """
        SELECT u
        FROM UserAccount u
        WHERE u.email = :email
        """,
        UserAccount.class
    )
    .setParameter("email", input)
    .getResultList();
}
```

`input` được bind như một `String` value; JPA provider chịu trách nhiệm chuyển nó thành parameter value ở tầng truy vấn phù hợp.

### 3.2. Query structure là cố định

```text
JPQL template:
    SELECT u FROM UserAccount u WHERE u.email = :email

Parameter:
    email = <input>

Parser:
    Parse template, không parse input thành JPQL source
```

Tập dữ liệu trả về có thể thay đổi vì **giá trị được so sánh khác nhau**, nhưng input không được tự thêm `OR`, `JOIN`, `ORDER BY` hay `DELETE` vào cú pháp query.

### 3.3. Không cần tự escape dấu nháy cho equality

Khi dùng binding:

```java
.setParameter("email", "o'hara@example.test")
```

JPA/driver xử lý value; không cần tự biến dấu `'` thành `''` bằng string replacement.

Tự escape thủ công trước khi bind có thể làm thay đổi dữ liệu:

```text
o'hara@example.test
```

thành:

```text
o''hara@example.test
```

mà ứng dụng lại đi so sánh sai giá trị.

**Binding là giải pháp, không phải tự sanitize cú pháp SQL rồi ghép chuỗi.**

---

## 4. Named parameters của JPQL

Named parameter có dạng:

```jpql
:parameterName
```

Ví dụ:

```java
TypedQuery<UserAccount> query = em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.tenantId = :tenant
      AND u.email = :email
    """,
    UserAccount.class
);

query.setParameter("tenant", tenantId);
query.setParameter("email", email);

List<UserAccount> result = query.getResultList();
```

### 4.1. Ưu điểm

- Tên rõ nghĩa.
- Tránh phụ thuộc thứ tự các vị trí.
- Có thể sử dụng một parameter nhiều lần.
- Dễ mở rộng truy vấn và đọc review.
- Tách input khỏi query structure.

### 4.2. Lặp lại cùng parameter

```java
em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.email = :keyword
       OR u.displayName = :keyword
    """,
    UserAccount.class
)
.setParameter("keyword", keyword)
.getResultList();
```

Đây là equality comparison trên hai fields. Nếu cần `LIKE`, phải xử lý wildcard semantics riêng ở phần sau.

### 4.3. Lỗi thường gặp

**Quên bind:**

```java
var query = em.createQuery(
    "SELECT u FROM UserAccount u WHERE u.email = :email",
    UserAccount.class
);

query.getResultList(); // Chưa setParameter("email", ...).
```

**Bind sai tên:**

```java
query.setParameter("userEmail", email);
```

Trong khi template khai báo `:email`.

**Thêm dấu hai chấm vào tên khi bind:**

```java
query.setParameter(":email", email); // Không dùng dạng này.
```

Thông thường tên truyền vào API là `"email"`, không có dấu `:`.

Lỗi bind parameter là lỗi application, không nên bị dịch thành “không tìm thấy account”.

---

## 5. Positional parameters của JPQL

JPQL cũng hỗ trợ positional parameters:

```java
List<UserAccount> users = em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.tenantId = ?1
      AND u.email = ?2
    """,
    UserAccount.class
)
.setParameter(1, tenantId)
.setParameter(2, email)
.getResultList();
```

Ở đây `?1` là tham số vị trí số 1 và `?2` là vị trí số 2.

### 5.1. Chỉ số bắt đầu từ 1

Không dùng `setParameter(0, ...)` cho vị trí đầu trong JPA.

### 5.2. Không tự tạo positional marker từ input

Sai:

```java
String jpql = "SELECT u FROM UserAccount u WHERE u.id = ?"
    + requestParameterIndex;
```

Đây là việc biến input thành **query source**. Marker và cấu trúc query phải do code quyết định.

### 5.3. Chọn named hay positional?

| Trường hợp | Gợi ý |
| --- | --- |
| JPQL nhiều tham số | Named parameters dễ đọc |
| JPQL truy vấn ngắn | Cả hai đều hợp lệ |
| Native SQL cần khả chuyển | Kiểm tra positional marker theo JPA provider |
| Query do Criteria API xây dựng | Dùng `ParameterExpression`/typed expressions |
| Truy vấn động nhiều nhánh | Criteria API hoặc query builder giữ structure trusted |

Không trộn named và positional parameters bừa bãi trong cùng một query; giữ quy ước rõ để tránh lỗi/provider portability.

---

## 6. Kiểu dữ liệu là một phần của an toàn và tính đúng

Bind parameter không có nghĩa ứng dụng bỏ qua **kiểu dữ liệu**.

### 6.1. Long ID

```java
Long accountId = 42L;

UserAccount account = em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.id = :id
    """,
    UserAccount.class
)
.setParameter("id", accountId)
.getSingleResult();
```

Đừng lấy chuỗi ID rồi ghép vào JPQL:

```java
"... WHERE u.id = " + rawIdFromRequest
```

### 6.2. BigDecimal

```java
BigDecimal minTotal = new BigDecimal("100.00");

List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.totalAmount >= :minimum
    """,
    PurchaseOrder.class
)
.setParameter("minimum", minTotal)
.getResultList();
```

Không dùng `double` cho tiền khi domain dùng `BigDecimal`, và không ghép chuỗi thập phân tùy locale vào SQL source.

### 6.3. Enum

Nếu entity có:

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

JPQL nên nhận enum value:

```java
query.setParameter("status", OrderStatus.CONFIRMED);
```

Không tự ghép tên enum vào source query.

### 6.4. Instant/LocalDateTime/LocalDate

```java
Instant from = ...;
Instant to = ...;

em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.createdAt >= :fromTime
      AND u.createdAt < :toTime
    """,
    UserAccount.class
)
.setParameter("fromTime", from)
.setParameter("toTime", to)
.getResultList();
```

Ưu tiên một khoảng **half-open** `[from, to)` để xử lý ranh giới thời gian rõ ràng.

Dù đã bind an toàn, vẫn cần thống nhất timezone/type mapping, kiểm tra `from < to` và không cho query range vô hạn gây quá tải.

---

## 7. Tránh biến validation thành “chống injection giả”

Validation vẫn quan trọng:

- Email đúng format.
- ID có kiểu số và thuộc range hợp lệ.
- Từ khóa không vượt độ dài giới hạn.
- Thời gian bắt đầu trước thời gian kết thúc.
- Danh sách ID không vượt số lượng cho phép.
- Kiểu enum thuộc tập được hỗ trợ.

Nhưng **validation không phải thay thế cho parameter binding**.

Sai về tư duy:

> “Tôi đã kiểm tra input không có dấu nháy đơn nên có thể nối vào SQL.”

Một blacklist ký tự không hiểu hết các biến thể của ngôn ngữ truy vấn, encoding, comment, functions hoặc driver behavior.

Đúng:

> “Tôi bind value để ngăn input trở thành syntax; tôi validation value để bảo đảm nghiệp vụ, tài nguyên và error messages.”

### 7.1. Không yêu cầu email loại bỏ ký tự hợp lệ chỉ để tránh SQL injection

Có những ký tự như dấu nháy đơn có thể xuất hiện trong dữ liệu hợp lệ tùy domain. Không ép dữ liệu trở nên khác chỉ để phù hợp với string concatenation nguy hiểm.

---

# Phần II — Native SQL

## 8. Native query khác JPQL ở ngôn ngữ và portability

JPQL:

```java
em.createQuery(
    "SELECT u FROM UserAccount u WHERE u.email = :email",
    UserAccount.class
)
.setParameter("email", email)
.getResultList();
```

Native SQL:

```java
em.createNativeQuery(
    "SELECT * FROM user_accounts WHERE email = ?",
    UserAccount.class
)
.setParameter(1, email)
.getResultList();
```

Ở native SQL:

- `user_accounts` là tên bảng DB.
- `email` là cột SQL.
- SQL được database/dialect hiểu trực tiếp.
- JPA provider vẫn cung cấp parameter binding, nhưng cú pháp chi tiết có thể khác theo provider.

**Không trộn tên entity JPQL với table SQL.**

### 8.1. Native SQL cũng cần binding

Sai:

```java
String sql =
    "SELECT * FROM user_accounts WHERE email = '"
    + email
    + "'";

em.createNativeQuery(sql, UserAccount.class)
    .getResultList();
```

Đúng:

```java
em.createNativeQuery(
    "SELECT * FROM user_accounts WHERE email = ?",
    UserAccount.class
)
.setParameter(1, email)
.getResultList();
```

Đây là positional parameter minh họa. Với native SQL, hãy kiểm tra placeholder syntax và positional binding được provider/driver thực tế hỗ trợ.

### 8.2. Named params trong native SQL là câu chuyện portability

Nhiều Hibernate projects viết:

```java
em.createNativeQuery(
    """
    SELECT *
    FROM user_accounts
    WHERE tenant_id = :tenant
      AND email = :email
    """,
    UserAccount.class
)
.setParameter("tenant", tenantId)
.setParameter("email", email)
.getResultList();
```

Cú pháp này thường được Hibernate hỗ trợ, nhưng **không được giả định mọi JPA provider/Jakarta Persistence version hỗ trợ native named parameters theo cùng cách**.

Khi portability là ưu tiên, dùng phương án positional parameter được provider/JPA version mục tiêu hỗ trợ và có integration test.

### 8.3. Positional marker giữa JDBC và JPA

JDBC `PreparedStatement` thường dùng `?`. JPQL positional parameters là `?1`, `?2`. Native queries đi qua một provider có thể dùng `?`, `?1` hoặc những quy tắc riêng.

**Đừng copy thẳng cú pháp `?1` từ JPQL vào mọi native query mà không kiểm tra provider.** Binding trên JPA API vẫn dùng vị trí 1-based khi gọi `setParameter(int, value)`.

### 8.4. Những ký tự SQL đặc biệt của DB có thể tương tác với parser provider

Ví dụ một số dialect dùng `?` như JSON operators hoặc dùng `::` cho casts, `:name` làm named marker. Provider parser có thể nhầm với parameter marker.

Trong các trường hợp này, cân nhắc:

- Chuyển sang cú pháp toán tử/function tương đương được provider xử lý rõ.
- Dùng `CAST(...)` thay vì cú pháp vendor gây mơ hồ nếu phù hợp.
- Sử dụng JDBC PreparedStatement trực tiếp trong một adapter có kiểm soát.
- Kiểm thử integration với đúng dialect/provider.

**Không xử lý mơ hồ bằng cách ghép input vào SQL text.**

---

## 9. Native SQL cho INSERT/UPDATE/DELETE phải bind mọi dữ liệu

Ví dụ UPDATE:

```java
int updated = em.createNativeQuery(
    """
    UPDATE user_accounts
    SET display_name = ?
    WHERE tenant_id = ?
      AND id = ?
    """
)
.setParameter(1, displayName)
.setParameter(2, tenantId)
.setParameter(3, accountId)
.executeUpdate();
```

Điểm quan trọng:

- `displayName` là dữ liệu.
- `tenantId` là dữ liệu lọc scope.
- `accountId` là dữ liệu xác định row.
- Cấu trúc `UPDATE`, table và columns do ứng dụng quyết định.

### 9.1. DML query cần transaction

`executeUpdate()` với UPDATE/DELETE thường yêu cầu transaction đang active/joined theo JPA semantics. Native query có parameterization không thay ranh giới transaction.

### 9.2. Query an toàn cú pháp vẫn có thể sai quyền

Ví dụ:

```sql
UPDATE user_accounts
SET display_name = ?
WHERE id = ?
```

đã bind input an toàn nhưng nếu API đa tenant không thêm `tenant_id` hoặc không kiểm tra ownership, một user có thể sửa row thuộc tổ chức khác.

**Injection prevention và authorization là hai hàng rào khác nhau.**

### 9.3. Bulk native DML có ảnh hưởng persistence context

Native UPDATE có thể bỏ qua dirty checking và JPA entity lifecycle callbacks thông thường. Managed entities đã được load có thể stale.

Nếu dùng native DML, cần chiến lược rõ về `flush`, `clear`, entity versioning và cache coherence. Không lấy parameterization làm bảo đảm consistency.

---

## 10. Native SQL mapping kết quả

JPA native query:

```java
@SuppressWarnings("unchecked")
List<UserAccount> users =
    em.createNativeQuery(
        """
        SELECT
            id, tenant_id, email,
            display_name, created_at
        FROM user_accounts
        WHERE tenant_id = ?
        """,
        UserAccount.class
    )
    .setParameter(1, tenantId)
    .getResultList();
```

Native entity mapping phải cung cấp những cột mà provider cần để materialize entity phù hợp; ánh xạ thiếu hoặc alias khác có thể gây lỗi runtime.

Nếu chọn scalar projection:

```java
@SuppressWarnings("unchecked")
List<Object[]> rows = em.createNativeQuery(
    """
    SELECT id, email
    FROM user_accounts
    WHERE tenant_id = ?
    """
)
.setParameter(1, tenantId)
.getResultList();
```

Cần map kiểu JDBC về Java types cẩn thận. Không có mối liên hệ trực tiếp giữa SQL injection safety và việc kết quả là `Object[]`, entity hay DTO; đều phải bind input đúng.

### 10.1. Không lấy lỗi mapping để bỏ parameterization

Một native query fail vì thiếu column/alias cần được sửa mapping. Không “đơn giản hóa” bằng cách ghép raw request string vào SQL chỉ để truy vấn chạy.

---

# Phần III — Những thứ parameterization KHÔNG xử lý

## 11. Không thể bind tên bảng, cột và keywords như values

Đây là một ranh giới quan trọng.

Giả sử client chọn sắp xếp theo `createdAt`.

Sai:

```java
String jpql =
    "SELECT u FROM UserAccount u ORDER BY "
    + sortFieldFromRequest;
```

Nếu người dùng kiểm soát `sortFieldFromRequest`, họ đang kiểm soát **cấu trúc** truy vấn chứ không chỉ một value.

Không thể “sửa” bằng:

```java
String jpql =
    "SELECT u FROM UserAccount u ORDER BY :sortField";

query.setParameter("sortField", "createdAt");
```

Một bind parameter biểu diễn **giá trị**, không phải identifier/property path. Thậm chí nếu query được provider chấp nhận, nó thường không có nghĩa “sort theo cột createdAt”; có thể là một expression constant hoặc bị từ chối.

### 11.1. Những phần không nên lấy thẳng từ input

- Tên entity trong JPQL.
- Tên table, view, schema trong native SQL.
- Tên column/property.
- Alias SQL.
- `ASC`/`DESC`.
- Phần `NULLS FIRST`/`NULLS LAST`.
- Toán tử so sánh `=`, `<`, `>`, `LIKE`.
- Tên database function.
- Raw `JOIN`, `WHERE`, `GROUP BY` hoặc `HAVING` fragments.
- Cấu trúc JSON path có semantics riêng nếu bị ghép thành SQL source.
- Câu lệnh DDL, database identifiers và partition names.

Chúng là **query structure**, không phải giá trị được truyền vào predicate.

---

## 12. Allowlist đóng cho ORDER BY

Thiết kế một tập cột được phép:

```java
public enum AccountSortField {
    CREATED_AT,
    EMAIL,
    DISPLAY_NAME
}
```

Sau đó chọn JPQL fragment từ constants do application kiểm soát:

```java
private static String toJpqlOrderPath(
        AccountSortField field) {

    return switch (field) {
        case CREATED_AT -> "u.createdAt";
        case EMAIL -> "u.email";
        case DISPLAY_NAME -> "u.displayName";
    };
}
```

Hướng sắp xếp cũng phải được parse/giới hạn:

```java
public enum Direction {
    ASC,
    DESC
}
```

Xây query:

```java
public List<UserAccount> searchAccounts(
        Long tenantId,
        AccountSortField field,
        Direction direction) {

    String orderPath = toJpqlOrderPath(field);

    String directionSql = switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };

    String jpql = """
        SELECT u
        FROM UserAccount u
        WHERE u.tenantId = :tenant
        ORDER BY
        """
        + orderPath
        + " " + directionSql
        + ", u.id ASC";

    return em.createQuery(jpql, UserAccount.class)
        .setParameter("tenant", tenantId)
        .getResultList();
}
```

**Vì sao nối chuỗi ở đây chấp nhận được?** Các fragments có thể được nối đều là **constants do application sở hữu**, chỉ được lựa chọn qua enum đóng. Input không được chèn nguyên văn vào source.

### 12.1. Chuyển string đầu vào thành enum đúng cách

Ở controller:

```java
private static AccountSortField parseSortField(
        String requested) {

    if (requested == null) {
        return AccountSortField.CREATED_AT;
    }

    return switch (requested) {
        case "createdAt" -> AccountSortField.CREATED_AT;
        case "email" -> AccountSortField.EMAIL;
        case "displayName" -> AccountSortField.DISPLAY_NAME;
        default -> throw new IllegalArgumentException(
            "Unsupported sort field"
        );
    };
}
```

Nếu client gửi tên property lạ, trả validation error; **không fallback sang ghép nguyên chuỗi không tin cậy**.

### 12.2. Stable ordering

Thêm tie-breaker `u.id ASC` giúp phân trang khi nhiều rows cùng `createdAt` hoặc `displayName`.

Nhưng pagination còn cần xử lý concurrent inserts/updates và có thể dùng keyset pagination nếu use case yêu cầu snapshot/stability mạnh hơn.

### 12.3. Không dùng regex mở quá rộng

Sai về bảo mật thiết kế:

```java
if (field.matches("[a-zA-Z0-9_.]+")) {
    jpql += " ORDER BY " + field;
}
```

Regex chỉ kiểm tra **hình dạng**, không giới hạn field/path/ngữ nghĩa. Dù không có ký tự SQL đặc biệt, một property hợp lệ ngoài allowlist có thể lộ thông tin hoặc gây query cost lớn.

---

## 13. Criteria API cho truy vấn động có cấu trúc

Khi search API có filters hoặc sorting động, **Criteria API** giúp biểu diễn query thành một cây biểu thức thay vì tự lắp string source.

Ví dụ:

```java
public List<UserAccount> searchByTenantAndEmail(
        EntityManager em,
        Long tenantId,
        String email) {

    CriteriaBuilder cb = em.getCriteriaBuilder();

    CriteriaQuery<UserAccount> cq =
        cb.createQuery(UserAccount.class);

    Root<UserAccount> u = cq.from(UserAccount.class);

    Predicate inTenant =
        cb.equal(u.get("tenantId"), tenantId);

    Predicate emailMatches =
        cb.equal(u.get("email"), email);

    cq.select(u).where(
        cb.and(inTenant, emailMatches)
    );

    return em.createQuery(cq).getResultList();
}
```

Ở đây `tenantId` và `email` được đưa vào typed expression tree, không được ghép làm cú pháp JPQL do user kiểm soát.

### 13.1. Criteria API không tự thay allowlist

Sai về chính sách:

```java
Path<?> sort = u.get(userSuppliedPropertyName);
```

Dù Criteria API tránh string injection vào JPQL source, người dùng vẫn có thể chọn property/path **không được phép về quyền hoặc performance**.

Hãy dùng enum-to-path mapping:

```java
private static Path<?> sortPath(
        Root<UserAccount> u,
        AccountSortField field) {

    return switch (field) {
        case CREATED_AT -> u.get("createdAt");
        case EMAIL -> u.get("email");
        case DISPLAY_NAME -> u.get("displayName");
    };
}
```

Và:

```java
Path<?> path = sortPath(u, field);

cq.orderBy(
    direction == Direction.ASC
        ? cb.asc(path)
        : cb.desc(path),
    cb.asc(u.get("id"))
);
```

### 13.2. ParameterExpression rõ ràng

Có thể khai báo:

```java
ParameterExpression<String> emailParam =
    cb.parameter(String.class, "email");

cq.where(cb.equal(u.get("email"), emailParam));

TypedQuery<UserAccount> query = em.createQuery(cq);

query.setParameter("email", email);

return query.getResultList();
```

Mẫu này thể hiện rõ ranh giới giữa cấu trúc và value, hữu ích khi kết hợp nhiều optional predicates.

### 13.3. Static metamodel tăng type safety

Nếu project dùng JPA static metamodel:

```java
u.get(UserAccount_.email)
```

có thể giảm typo so với `"email"`, nhưng cấu hình annotation processing/metamodel generation phụ thuộc build setup.

Static metamodel vẫn không tự quyết định user nào được phép filter/sort theo field nào. Security policy vẫn phải được thiết kế.

---

## 14. Dynamic table/partition/schema names

Đôi khi native SQL cần chọn bảng theo một tập partitions hoặc một trong vài reports.

Không được làm:

```java
String sql =
    "SELECT COUNT(*) FROM " + tableFromRequest;
```

Không thể bind table name như một value:

```sql
SELECT COUNT(*) FROM ?
```

không có ý nghĩa identifier binding portable trong SQL.

### 14.1. Chọn từ danh sách constants

```java
public enum ReportTable {
    CURRENT_ORDERS,
    ARCHIVED_ORDERS
}
```

```java
private static String trustedTable(
        ReportTable table) {

    return switch (table) {
        case CURRENT_ORDERS -> "purchase_orders";
        case ARCHIVED_ORDERS -> "archived_purchase_orders";
    };
}
```

```java
String sql =
    "SELECT COUNT(*) FROM " + trustedTable(table)
    + " WHERE tenant_id = ?";

Object result = em.createNativeQuery(sql)
    .setParameter(1, tenantId)
    .getSingleResult();
```

Đây là controlled structure selection. `tenantId` vẫn là bind parameter.

### 14.2. Còn phải kiểm soát quyền

Ngay cả khi hai bảng đều thuộc allowlist, một user không nhất thiết có quyền đọc archived orders. Allowlist **chống query-structure injection**, không thay authorization.

### 14.3. Identifier quoting không phải lựa chọn mặc định

Việc thêm dấu quotes quanh một arbitrary identifier có thể tránh một số parsing issues nhưng vẫn cho phép truy cập bảng/cột ngoài chính sách nếu không có allowlist.

Đối với dynamic schema và table names, ưu tiên **thiết kế không cho user chọn identifiers tùy ý**.

---

# Phần IV — LIKE và các ký tự wildcard

## 15. `LIKE` có hai lớp xử lý khác nhau

Một query có thể đã chống SQL injection:

```java
em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.displayName LIKE :pattern
    """,
    UserAccount.class
)
.setParameter("pattern", input)
.getResultList();
```

`input` là data value, không thể tự thay cấu trúc JPQL.

Nhưng `LIKE` có semantics riêng:

- `%` đại diện cho chuỗi ký tự có độ dài bất kỳ.
- `_` đại diện cho một ký tự.
- Một escape character có thể dùng để tìm `%` hoặc `_` theo nghĩa literal.

Nếu search UI yêu cầu **tìm chính xác chuỗi người dùng nhập như text**, việc bind trực tiếp `%` có thể biến thành search rất rộng. Đây không phải SQL injection, mà là **wildcard injection/search semantics error**.

### 15.1. Định nghĩa rõ search API

Có hai contract khác nhau:

**Contract A — User nhập pattern:** user cố ý có quyền dùng `%` và `_` làm wildcard.

**Contract B — User nhập plain text:** `%` và `_` phải được tìm như các ký tự bình thường.

Trong phần lớn ô tìm kiếm phổ thông, Contract B thường dễ hiểu hơn.

---

## 16. Escape LIKE wildcard với ký tự `!`

Để tránh các khác biệt phức tạp của dấu `\` trong Java string/SQL dialect, ví dụ dùng dấu `!` làm escape character.

JPQL:

```jpql
SELECT u
FROM UserAccount u
WHERE LOWER(u.displayName)
      LIKE :pattern ESCAPE '!'
```

Java helper:

```java
private static String escapeLikeLiteral(String input) {
    return input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
```

Chú ý **thứ tự**: escape chính escape character (`!`) trước khi escape các wildcard.

Tìm chứa chuỗi:

```java
String normalized =
    input.toLowerCase(Locale.ROOT);

String pattern =
    "%" + escapeLikeLiteral(normalized) + "%";

List<UserAccount> users = em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.tenantId = :tenant
      AND LOWER(u.displayName)
          LIKE :pattern ESCAPE '!'
    """,
    UserAccount.class
)
.setParameter("tenant", tenantId)
.setParameter("pattern", pattern)
.getResultList();
```

### 16.1. Ví dụ input và pattern

| Input người dùng | Sau escape | Pattern chứa |
| --- | --- | --- |
| `Lan` | `Lan` | `%Lan%` |
| `100%` | `100!%` | `%100!%%` |
| `A_B` | `A!_B` | `%A!_B%` |
| `Hello!` | `Hello!!` | `%Hello!!%` |
| `!%_` | `!!!%!_` | `%!!!%!_%` |

Ví dụ trên giải thích thuật toán; pattern còn được bind như **một parameter** để chống query injection.

### 16.2. Lỗi thường gặp: escape sau khi thêm wildcard chủ động

Sai:

```java
String pattern =
    escapeLikeLiteral("%" + input + "%");
```

Cách này escape luôn hai dấu `%` do **ứng dụng chủ động thêm**, khiến truy vấn không còn là tìm chứa chuỗi.

Đúng:

```java
String pattern =
    "%" + escapeLikeLiteral(input) + "%";
```

### 16.3. `LOWER` và collation cần kiểm tra riêng

`LOWER(u.displayName)` và `toLowerCase(Locale.ROOT)` có thể có differences với Unicode/collation/DB locale. Đây là vấn đề search semantics và index design, không phải lý do bỏ binding.

### 16.4. Hiệu năng của `%keyword%`

Một pattern bắt đầu bằng `%` thường khó dùng B-tree index theo cách prefix search thông thường. Nếu data lớn, cân nhắc full-text/trigram indexes hoặc search engine phù hợp, với query parameterization tương ứng.

Không giảm bảo mật để “giúp index hoạt động”.

---

## 17. Native SQL LIKE cũng cần binding và escape

Ví dụ SQL với cùng ý nghĩa:

```java
String pattern =
    "%" + escapeLikeLiteral(input) + "%";

@SuppressWarnings("unchecked")
List<UserAccount> users = em.createNativeQuery(
    """
    SELECT *
    FROM user_accounts
    WHERE tenant_id = ?
      AND display_name LIKE ? ESCAPE '!'
    """,
    UserAccount.class
)
.setParameter(1, tenantId)
.setParameter(2, pattern)
.getResultList();
```

**DB portability:** syntax/collation/escape semantics của `LIKE` cần được kiểm thử trên database mục tiêu. JPQL `ESCAPE` và SQL dialect implementation không nên bị coi là có behavior giống hệt trên mọi engine nếu có Unicode/collation/escape quirks.

### 17.1. Không chỉ chặn `%` và `_`

Nếu business muốn giới hạn query cost, có thể validate độ dài keyword, số filters, number of results. Nhưng escaping wildcard để diễn đạt literal match và binding để chống injection vẫn là hai yêu cầu riêng.

### 17.2. Truy vấn `ILIKE`/full-text đặc thù DB

PostgreSQL `ILIKE` là một tính năng SQL riêng; có thể dùng bound parameters trong native SQL. Đừng ghép input chỉ vì đã chuyển khỏi JPQL.

---

# Phần V — Danh sách IN, NULL và filters động

## 18. `IN` với tập giá trị: không tạo danh sách bằng nối chuỗi

Sai:

```java
String idsCsv = ids.stream()
    .map(Object::toString)
    .collect(Collectors.joining(","));

String jpql =
    "SELECT u FROM UserAccount u WHERE u.id IN ("
    + idsCsv + ")";
```

Với `List<Long>` được parse nghiêm ngặt, rủi ro injection trực tiếp có thể thấp hơn dữ liệu chuỗi; nhưng pattern vẫn có vấn đề:

- Không tái sử dụng query structure.
- Dễ lặp sai khi đổi sang String identifiers.
- Dễ gặp danh sách rỗng.
- Có giới hạn số bind values/SQL size.
- Không có kiểm soát số phần tử/truy vấn lớn.
- Tạo tiền lệ ghép input vào source.

### 18.1. Spring Data derived query

Ví dụ repository:

```java
public interface UserAccountRepository
        extends JpaRepository<UserAccount, Long> {

    List<UserAccount> findByTenantIdAndIdIn(
        Long tenantId,
        Collection<Long> ids
    );
}
```

Spring Data/provider xử lý parameterization tương ứng. Cần xác nhận behavior với collection rỗng trên version đang dùng.

### 18.2. JPQL collection parameter

Trong nhiều JPA/Hibernate setups, có thể dùng:

```java
List<UserAccount> users = em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.tenantId = :tenant
      AND u.id IN :ids
    """,
    UserAccount.class
)
.setParameter("tenant", tenantId)
.setParameter("ids", ids)
.getResultList();
```

**Portability:** collection-valued parameter expansion và behavior cụ thể cần được xác nhận với Jakarta Persistence/provider version mục tiêu, nhất là khi dùng native SQL. Đừng suy luận `IN (?)` của JDBC sẽ tự mở rộng một Java `List` ở mọi driver.

### 18.3. Xử lý empty list có chủ đích

Nếu `ids` rỗng và contract là “không chọn bản ghi nào”:

```java
if (ids.isEmpty()) {
    return List.of();
}
```

Không xây:

```sql
WHERE id IN ()
```

rồi mặc định mọi database chấp nhận. Cũng không bỏ điều kiện `IN` khi list rỗng vì như vậy có thể **trả toàn bộ records**.

### 18.4. Giới hạn kích thước danh sách

Ví dụ:

```java
if (ids.size() > 500) {
    throw new IllegalArgumentException(
        "Too many identifiers"
    );
}
```

Con số 500 chỉ là giới hạn sản phẩm minh họa, không phải mức chuẩn của JPA. Hãy chọn theo workload, DB parameter limits, API contract và SLO.

---

## 19. Native SQL `IN`: sự khác nhau với JPQL

Một sai lầm:

```java
em.createNativeQuery(
    "SELECT * FROM user_accounts WHERE id IN (?)",
    UserAccount.class
)
.setParameter(1, ids);
```

Không có bảo đảm JDBC placeholder `?` **tự chuyển** `List<Long>` thành nhiều placeholders SQL.

### 19.1. Phương án explicit positional placeholders

Nếu có danh sách IDs được parse thành `List<Long>` với kích thước hợp lệ:

```java
public List<?> findAccountsByIdsNative(
        List<Long> ids,
        Long tenantId) {

    if (ids.isEmpty()) {
        return List.of();
    }

    if (ids.size() > 500) {
        throw new IllegalArgumentException(
            "Too many IDs"
        );
    }

    String placeholders = String.join(
        ", ",
        java.util.Collections.nCopies(ids.size(), "?")
    );

    String sql = """
        SELECT *
        FROM user_accounts
        WHERE tenant_id = ?
          AND id IN (
        """
        + placeholders
        + ")";

    Query query = em.createNativeQuery(
        sql,
        UserAccount.class
    );

    query.setParameter(1, tenantId);

    for (int i = 0; i < ids.size(); i++) {
        query.setParameter(i + 2, ids.get(i));
    }

    return query.getResultList();
}
```

Ở đây code chỉ tạo một dãy **constant `?` markers theo số lượng**, không chèn values vào SQL. SQL structure thay đổi theo số lượng markers, nhưng từng giá trị vẫn bind tách biệt.

**Cần test với native placeholder syntax của provider.** Một số stack hỗ trợ named/list expansion hoặc array parameters theo extension/database dialect, nhưng không nên coi một cách là portable cho tất cả.

### 19.2. Chú ý số lượng queries/plan cache

Danh sách có độ dài khác nhau tạo query text khác nhau. Với tải lớn, có thể cân nhắc temporary table, table-valued parameters, native array binding hoặc join to staging table theo DB, nhưng đó là database-specific design.

### 19.3. Không chèn dữ liệu sau khi join

Sai:

```java
String sql = "WHERE email IN ('"
    + String.join("','", emailsFromRequest)
    + "')";
```

Dù mỗi phần tử trông như email, đó vẫn là cách ghép values vào SQL source.

---

## 20. `NULL` không dùng toán tử equality như giá trị thông thường

SQL ba giá trị logic có semantics riêng:

```sql
email = NULL
```

không tương đương:

```sql
email IS NULL
```

JPQL cũng phân biệt:

```jpql
WHERE u.email IS NULL
```

và:

```jpql
WHERE u.email = :email
```

với `:email` được bind `null`.

### 20.1. Optional filter rõ ràng

Nếu null có nghĩa “không lọc”:

```java
String jpql = """
    SELECT u
    FROM UserAccount u
    WHERE u.tenantId = :tenant
    """;

if (email != null) {
    jpql += " AND u.email = :email";
}
```

Sau đó bind chỉ khi có predicate:

```java
TypedQuery<UserAccount> q =
    em.createQuery(jpql, UserAccount.class)
      .setParameter("tenant", tenantId);

if (email != null) {
    q.setParameter("email", email);
}
```

Đây là **concatenation của constant query fragment**, không chèn raw value. Tuy nhiên với nhiều filters, Criteria API hoặc query builder typed thường giúp tránh lỗi hơn.

### 20.2. Không dùng `${input}` để thay đổi predicate

Một parameter binding cho `null` không thể được coi như sự thay thế portable cho việc xây đúng `IS NULL` hoặc quyết định bỏ filter. Phải định nghĩa input semantics.

### 20.3. SQL NULL semantics không phải injection vulnerability

Một truy vấn `email = :email` trả zero rows khi `email` null có thể là logic bug, nhưng không phải bằng chứng injection. Phân biệt lỗi an toàn cú pháp với lỗi nghiệp vụ.

---

## 21. Optional filters bằng Criteria API

Một phương thức tìm kiếm có tenant bắt buộc và email/displayName tùy chọn:

```java
public List<UserAccount> search(
        Long tenantId,
        String email,
        String displayName) {

    CriteriaBuilder cb = em.getCriteriaBuilder();

    CriteriaQuery<UserAccount> cq =
        cb.createQuery(UserAccount.class);

    Root<UserAccount> root =
        cq.from(UserAccount.class);

    List<Predicate> where = new ArrayList<>();

    where.add(
        cb.equal(root.get("tenantId"), tenantId)
    );

    if (email != null && !email.isBlank()) {
        where.add(
            cb.equal(root.get("email"), email)
        );
    }

    if (displayName != null &&
            !displayName.isBlank()) {

        String pattern = "%" +
            escapeLikeLiteral(
                displayName.toLowerCase(Locale.ROOT)
            )
            + "%";

        where.add(
            cb.like(
                cb.lower(root.get("displayName")),
                pattern,
                '!'
            )
        );
    }

    cq.select(root)
      .where(where.toArray(new Predicate[0]))
      .orderBy(cb.asc(root.get("id")));

    return em.createQuery(cq).getResultList();
}
```

Imports:

```java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
```

### 21.1. Tenant predicate không được tùy chọn theo input

Ví dụ trên luôn thêm `tenantId` vào conditions. Không thiết kế kiểu:

```java
if (tenantId != null) {
    where.add(...);
}
```

nếu business yêu cầu tất cả queries bị scope theo tenant. Tenant nên được lấy từ authenticated context đã xác minh, không nhận tùy ý từ client.

### 21.2. Criteria API không bỏ qua authorization

Một Criteria query được xây an toàn khỏi SQL syntax injection vẫn có thể trả dữ liệu không được phép nếu repository quên tenant/ownership filter.

---

# Phần VI — Phân trang, sắp xếp và hiệu năng

## 22. Dùng `setFirstResult` và `setMaxResults` thay vì ghép LIMIT/OFFSET

Với JPQL:

```java
List<UserAccount> users = em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.tenantId = :tenant
    ORDER BY u.createdAt DESC, u.id DESC
    """,
    UserAccount.class
)
.setParameter("tenant", tenantId)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
```

### 22.1. Validate pageSize và offset

```java
if (offset < 0) {
    throw new IllegalArgumentException(
        "Offset must be non-negative"
    );
}

if (pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException(
        "Page size must be between 1 and 100"
    );
}
```

Các giới hạn là ví dụ sản phẩm. Đặt ceiling phù hợp SLA và database.

### 22.2. Không để client tự kiểm soát SQL LIMIT fragment

Sai:

```java
String sql = "SELECT * FROM user_accounts LIMIT "
    + limitFromRequest;
```

Dù có thể parse số trước khi ghép để giảm injection risk, JPA API pagination là lựa chọn rõ hơn khi dùng JPA. Với native SQL đặc thù, bind LIMIT/OFFSET khi provider/DB hỗ trợ hoặc dùng API tương ứng.

### 22.3. Native query pagination cần test

`setFirstResult`/`setMaxResults` trên native query có mức độ hỗ trợ và translation tùy provider/version/dialect, nhất là với stored procedures hoặc result set mappings. Test behavior trên DB mục tiêu.

### 22.4. Parameterization có thể hỗ trợ plan reuse

Một query cố định với parameters giúp provider/driver/database có cơ hội tái sử dụng parse/plan. Nhưng:

- DB optimizer có thể chọn plan theo parameter values.
- `IN` list expansion thay đổi query text.
- Query caching và plan caching có rules riêng.
- Parameterization không tự làm query nhanh.
- Parameter sniffing có thể tạo plan-quality tradeoffs tùy database.

**Bảo mật là lý do bắt buộc; hiệu năng là lợi ích tiềm năng, không phải lời hứa tuyệt đối.**

---

## 23. `LIKE` input dài và query resource exhaustion

Bind đúng nhưng một người dùng vẫn có thể gửi search rất tốn tài nguyên:

```text
keyword dài hàng chục nghìn ký tự
pattern %...%
sort trên cột không index
pageSize rất lớn
nhiều OR predicates
```

Parameterization chống injection, **không tự chống denial-of-service qua query cost**.

Nên thiết kế:

- Maximum keyword length.
- Pagination cap.
- Query timeout phù hợp.
- Allowed sorts/filters.
- Index/plan tốt.
- Rate limiting.
- Auditing suspicious query patterns.
- Tenant scoping.
- Circuit breaker hoặc workload isolation nếu cần.

Không vì performance mà nối input không tin cậy vào query string.

---

# Phần VII — An toàn trong Spring Data JPA

## 24. Derived query methods tự tránh cách nối JPQL nguy hiểm

Ví dụ:

```java
public interface UserAccountRepository
        extends JpaRepository<UserAccount, Long> {

    Optional<UserAccount> findByTenantIdAndEmail(
        Long tenantId,
        String email
    );
}
```

Spring Data xây query theo property names do developer định nghĩa và bind values theo repository parameters. Khi dùng đúng, đây là một cách giảm lỗi ghép chuỗi.

### 24.1. Derived query không bảo đảm quyền

Nếu method là:

```java
findByEmail(email)
```

nhưng hệ thống multi-tenant yêu cầu tenant scope, truy vấn vẫn có thể trả account từ tenant khác.

Security review cần xem **phạm vi dữ liệu được phép**, không chỉ có injection hay không.

### 24.2. Spring Data @Query dùng parameters

```java
public interface UserAccountRepository
        extends JpaRepository<UserAccount, Long> {

    @Query(
        """
        SELECT u
        FROM UserAccount u
        WHERE u.tenantId = :tenant
          AND u.email = :email
        """
    )
    Optional<UserAccount> findExact(
        @Param("tenant") Long tenantId,
        @Param("email") String email
    );
}
```

Đây là JPQL `@Query` với named parameters.

### 24.3. Native query trong Spring Data

```java
@Query(
    value = """
        SELECT *
        FROM user_accounts
        WHERE tenant_id = :tenant
          AND email = :email
        """,
    nativeQuery = true
)
Optional<UserAccount> findExactNative(
    @Param("tenant") Long tenantId,
    @Param("email") String email
);
```

Spring Data JPA với một provider như Hibernate có thể hỗ trợ native named params theo cấu hình đang dùng. Không coi cú pháp này là bằng chứng **portable cho mọi provider/JPA version**, và phải integration test.

### 24.4. Sort/Pageable từ client

Spring Data có mechanisms cho `Sort` và `Pageable`, nhưng ứng dụng vẫn nên giới hạn allowed properties:

```java
private static final Set<String> ALLOWED_SORTS =
    Set.of("createdAt", "email", "displayName");
```

Không mặc định mọi property path do client nhập là field được phép sort/filter. Một đường sort native SQL hoặc function expression có thể cần kiểm soát chặt hơn nữa.

### 24.5. Đừng chuyển Spring Expression Language thành raw SQL template

Một số Spring Data features cho phép expressions trong annotations. Không biến input người dùng thành **query fragment** bằng string interpolation. Giữ phân biệt giữa **expression tính ra bound value** và **expression tạo structure SQL**.

---

# Phần VIII — Tenant isolation và authorization

## 25. Parameter binding không thay kiểm tra quyền

Hãy xét hai truy vấn đều được bind an toàn:

```java
em.createQuery(
    "SELECT u FROM UserAccount u WHERE u.id = :id",
    UserAccount.class
)
.setParameter("id", userId)
.getSingleResult();
```

và:

```java
em.createQuery(
    """
    SELECT u
    FROM UserAccount u
    WHERE u.id = :id
      AND u.tenantId = :tenant
    """,
    UserAccount.class
)
.setParameter("id", userId)
.setParameter("tenant", authenticatedTenantId)
.getSingleResult();
```

Cả hai đều chống syntax injection. Nhưng trong ứng dụng multi-tenant, truy vấn đầu có thể là **IDOR/BOLA** nếu caller không được phép truy cập entity có ID đó.

### 25.1. Không lấy tenant ID tùy ý từ request

Sai về authorization:

```java
Long tenantId = request.getParameter("tenantId");
```

rồi dùng trực tiếp như căn cứ cho quyền đọc.

Đúng về thiết kế là xác định authenticated principal, memberships, scope và tenant từ security context/authorization service đã xác minh.

### 25.2. Mọi đường truy vấn phải được scope

Bao gồm:

- Normal SELECT.
- Native SQL.
- Batch UPDATE/DELETE.
- JPQL bulk DML.
- Report/export.
- Count/exists endpoints.
- Background jobs.
- Search endpoints có dynamic filters.

Một repository method mới không thể tự thừa hưởng tenant protection nếu không có thiết kế rõ.

### 25.3. Database row-level security là lớp bổ sung

Một số DB như PostgreSQL hỗ trợ row-level security (RLS) để áp chính sách ở tầng DB. RLS có thể bổ sung defense-in-depth, nhưng cần cấu hình role/session context và test rất kỹ.

Query parameterization vẫn phải được dùng; RLS **không thay bind parameters**.

### 25.4. Không nhầm “đã bind ID” với “được phép xem ID”

Đây là một trong những nhầm lẫn quan trọng nhất về bảo mật data access.

---

## 26. Cấu trúc câu truy vấn và quyền của database user

Ngay cả khi toàn bộ giá trị được bind, tài khoản database cấp cho ứng dụng không nên có quyền không cần thiết:

- Không dùng superuser credentials để phục vụ HTTP requests.
- Hạn chế DDL/administrative permissions.
- Chỉ cấp SELECT/INSERT/UPDATE/DELETE trên objects cần thiết.
- Tách read-only/reporting role nếu hợp lý.
- Quản lý secrets an toàn.
- Kiểm soát stored procedures có quyền cao.
- Audit quyền của batch jobs và service accounts.

Đây là **least privilege** — một lớp phòng vệ nếu lỗi logic hoặc injection vẫn xuất hiện ở đường code khác.

### 26.1. Parameterization không bảo vệ raw SQL nguy hiểm được gọi cố ý

Nếu code có endpoint thực hiện native `DELETE` tất cả records do business logic sai, dù values đều bind, dữ liệu vẫn có thể bị xóa nhầm.

Không đánh đồng chống SQL injection với đúng nghiệp vụ/quyền.

---

# Phần IX — Kiểm thử và giám sát

## 27. Unit test cho phương thức tham số hóa

Ta có thể kiểm tra rằng logic query builder dùng template cố định và bind giá trị.

Một cách thiết kế dễ test là tách input parsing:

```java
record AccountSearchRequest(
    String email,
    AccountSortField sortField,
    Direction direction
) {
}
```

Với `parseSortField`:

```java
@Test
void rejectsUnknownSortField() {
    assertThrows(
        IllegalArgumentException.class,
        () -> parseSortField(
            "someUnexpectedDatabaseColumn"
        )
    );
}
```

Test này chứng minh allowlist hoạt động, nhưng **không tự chứng minh JPQL thực tế được parameterize**. Cần test DAO/repository với JPA provider.

### 27.1. Test với dấu nháy đơn

```java
@Test
void emailWithSingleQuoteIsUsedAsLiteralValue() {
    String email = "o'hara@example.test";

    // Fixture: một account hợp lệ có email như trên.
    createAccountFixture(
        100L, email, "O'Hara"
    );

    List<UserAccount> rows =
        service.findByEmail(100L, email);

    assertEquals(1, rows.size());
    assertEquals(email, rows.get(0).getEmail());
}
```

Các helpers minh họa (`createAccountFixture`, `service.findByEmail`) phải được triển khai trong test project.

Mục đích là dữ liệu chứa ký tự đặc biệt phải **được so khớp nguyên văn**, không gây lỗi query hoặc làm thay đổi predicate.

### 27.2. Test strings giống SQL syntax

Có thể dùng input test không gây hại:

```text
O'Reilly
name;with:semicolon
text -- comment-looking
a'b
```

Test kỳ vọng những chuỗi này được xử lý **như dữ liệu** khi bind.

Không cần biến test thành công cụ khai thác; chỉ cần xác minh query không tự thay cấu trúc hoặc trả các rows khác.

---

## 28. Integration test với database thực

Test toàn bộ đường truy vấn:

1. Tạo schema từ migrations.
2. Insert fixture cho hai tenants.
3. Chạy DAO methods với input bình thường và ký tự đặc biệt.
4. Kiểm tra SQL bind behavior qua result đúng.
5. Kiểm tra tenant scoping.
6. Kiểm tra sorting allowlist.
7. Kiểm tra `LIKE` wildcard literal.
8. Kiểm tra empty `IN` list.
9. Kiểm tra native SQL placeholder compatibility.
10. Kiểm tra pagination limits.
11. Kiểm tra native UPDATE/DELETE không ảnh hưởng rows ngoài scope.
12. Chạy trên provider/driver/database mục tiêu.

### 28.1. Không chỉ test return count

Nếu một truy vấn thiếu tenant predicate, nó vẫn có thể trả đúng một row trong fixture đơn giản. Test cần có **rows từ tenant khác với values giống nhau** để phát hiện dữ liệu bị lộ.

### 28.2. Test query mới sau khi sửa code

Bảo mật là một thuộc tính của **mọi code path**. Có thể phương thức tìm kiếm đã parameterize nhưng endpoint export vẫn dùng string concatenation. Nên review/test repository layer theo route và business operation.

---

## 29. Integration test LIKE literal `%` và `_`

Giả sử fixture:

```text
Tenant 100:
  displayName = "100% Complete"
  displayName = "1000 Complete"
  displayName = "A_B"
  displayName = "AXB"
```

Nếu người dùng tìm literal `100%`, expected chỉ chứa `"100% Complete"` khi match theo nghĩa contains.

Nếu tìm literal `A_B`, expected bao gồm `"A_B"` nhưng không tự bao gồm `"AXB"` chỉ vì `_` wildcard.

### 29.1. Test pseudo-code

```java
@Test
void percentIsEscapedAsLiteralForPlainTextSearch() {
    List<UserAccount> rows =
        searchService.searchByName(100L, "100%");

    assertTrue(
        rows.stream().anyMatch(
            u -> u.getDisplayName().equals("100% Complete")
        )
    );

    assertFalse(
        rows.stream().anyMatch(
            u -> u.getDisplayName().equals("1000 Complete")
        )
    );
}
```

Cần fixture được commit trước test và `searchByName` dùng `escapeLikeLiteral` + `ESCAPE '!'` như phần 16.

### 29.2. Test escape character

Fixture tên `"Hello!"`, input `"Hello!"` phải được tìm đúng. Nếu quên `.replace("!", "!!")`, pattern có thể bị hiểu sai.

### 29.3. Kiểm tra trên DB đích

Một test trên H2 có thể khác PostgreSQL/MySQL về collation và escape behavior. Với search semantics quan trọng, test engine/version giống production.

---

## 30. Kiểm thử ORDER BY allowlist

Thử các input:

| User input | Mong đợi |
| --- | --- |
| `createdAt` | Map thành trusted `u.createdAt` |
| `email` | Map thành trusted `u.email` |
| `displayName` | Map thành trusted `u.displayName` |
| `unknownField` | Bị từ chối |
| Input có khoảng trắng/ký tự cấu trúc | Bị từ chối |
| `null` | Dùng default đã định nghĩa |
| `direction=ASC` | Enum ASC |
| `direction=DESC` | Enum DESC |
| Direction khác | Bị từ chối |

### 30.1. Test structure, không chỉ test exceptions

Một field không thuộc allowlist phải bị từ chối **trước khi tạo query text**, không phải chỉ chờ provider báo invalid path ở runtime.

### 30.2. Không cho client truyền JPQL snippets

Tránh API kiểu:

```text
sort = "u.createdAt DESC, u.email ASC"
```

nếu nó nhận raw JPQL fragments. Nên cho client chọn discrete allowed fields/directions.

---

## 31. Security regression test cho native UPDATE

Fixture:

```text
Tenant 100: user id=1, displayName=Alice
Tenant 200: user id=2, displayName=Bob
```

Khi caller thuộc tenant 100, một operation cập nhật id=2 phải không ảnh hưởng tenant 200.

Ví dụ native SQL đã scope:

```java
int affected = em.createNativeQuery(
    """
    UPDATE user_accounts
    SET display_name = ?
    WHERE tenant_id = ?
      AND id = ?
    """
)
.setParameter(1, "New Name")
.setParameter(2, authenticatedTenantId)
.setParameter(3, targetId)
.executeUpdate();
```

Nếu `authenticatedTenantId=100` và `targetId=2`, affected rows phải bằng 0.

Đây là test **authorization/tenant scoping**. Mọi values vẫn parameterized.

### 31.1. Không chỉ xem số affected rows

Sau transaction commit, dùng EntityManager mới để đọc tenant 200 row và xác nhận `"Bob"` không thay đổi.

### 31.2. Lỗi native bulk UPDATE có thể làm L1 stale

Test mở context mới để verify persisted data, không dựa trên managed entity của context đã thực hiện bulk SQL.

---

## 32. Logging parameter values có thể làm lộ dữ liệu

Khi debug query, nhiều người bật SQL/bind logs. Với Hibernate 6 trong dev/test:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Khi TRACE, parameter values có thể được ghi log:

```text
binding parameter [1] as [VARCHAR] - [alice@example.test]
```

**Dù binding đã chống injection**, log vẫn có thể tiết lộ dữ liệu cá nhân.

### 32.1. Quy tắc logging

- Không bật bind TRACE mặc định ở production.
- Redact emails/tokens/PII khi cần.
- Chỉ log metadata/correlation ID phù hợp.
- Giới hạn retention và quyền truy cập logs.
- Không trả raw SQL/bind values trong HTTP 500.
- Không log mật khẩu, API keys, secrets.
- Cân nhắc hash tokenized identifiers khi theo dõi sự cố.

### 32.2. Không dùng log có placeholder như bằng chứng chắc chắn

Một Hibernate SQL log có `?` là tín hiệu query có parameters, nhưng vẫn cần xem các **fragments được nối trước đó**. Một phần query structure có thể đã bị input kiểm soát, trong khi predicates khác được bind an toàn.

---

## 33. Code review checklist cho data access

Khi review một method JPA/native SQL, hãy hỏi:

1. Có input nào đến từ request, file, queue hoặc DB record không?
2. Input có được nối vào JPQL/SQL source không?
3. Mọi values có đi qua `setParameter` hoặc API binding tương đương không?
4. Có tên bảng/cột/sort từ client không?
5. Structural choices có được map qua allowlist đóng không?
6. Có raw JPQL/SQL fragment parameter nào được public API nhận không?
7. Có dùng `CriteriaBuilder` nhưng `root.get(userInput)` không qua allowlist không?
8. Native named parameters có được provider hỗ trợ và test không?
9. Positional markers native/JPQL có dùng đúng cú pháp cho stack mục tiêu không?
10. Có `LIKE` không, người dùng nhập plain text hay pattern?
11. Có escape `%`, `_` và escape character đúng contract không?
12. Có validate maximum keyword length không?
13. Có xử lý danh sách `IN` rỗng không?
14. Có giới hạn số IDs/bind parameters không?
15. Có xử lý `NULL` semantics đúng không?
16. Có bind đúng Java types (ID/enum/date/BigDecimal) không?
17. Có tenant/ownership predicate bắt buộc không?
18. Tenant ID có được lấy từ authenticated context đáng tin không?
19. Có query nào bỏ qua filter vì một optional input rỗng không?
20. Có native UPDATE/DELETE chạm nhiều rows không?
21. Có giới hạn pageSize/sorting không?
22. Có dùng SQL vendor extensions làm giảm portability không?
23. Có plan/index phù hợp để tránh expensive searches không?
24. DB application role có least privilege không?
25. Có test input chứa dấu nháy và ký tự đặc biệt không?
26. Có test wildcard `%`/`_` như literal text không?
27. Có test user khác tenant không nhìn thấy hoặc sửa được row không?
28. Có test native query với DB/provider thực không?
29. Có tránh bật bind logs nhạy cảm trên production không?
30. Có phân biệt injection risk với authorization, validation, query cost và consistency không?

---

# Phần X — Những ngộ nhận phổ biến

## 34. “JPA tự chống mọi SQL injection”

Không đúng. JPA cung cấp parameter binding và Criteria API, nhưng developer vẫn có thể:

```java
em.createQuery(
    "SELECT u FROM UserAccount u WHERE u.email = '"
    + input + "'"
);
```

ORM không thể cứu query template đã bị input thay đổi trước khi parse.

## 35. “Chỉ cần replace dấu nháy đơn là đủ”

Không đúng. Manual escaping có thể sai với driver, dialect, encoding và ngữ cảnh. Dùng bound parameters thay vì cố đoán mọi biến thể syntax.

## 36. “@Query tự động parameterize dù nối giá trị vào chuỗi”

Không đúng. Một annotation `@Query` với named parameters và binding đúng là an toàn cho values. Nếu application hay framework expression tạo ra raw query fragments từ input thì rủi ro vẫn tồn tại.

## 37. “Có thể bind tên cột như một String”

Không đúng. `ORDER BY :field` không mang nghĩa chọn identifier được chỉ định bởi string parameter. Dùng enum/allowlist hoặc Criteria AST.

## 38. “Regex chỉ cho chữ và số là đủ cho dynamic identifier”

Không đủ. Regex không quyết định property đó có nằm trong policy được phép hay không. Dùng allowlist cụ thể.

## 39. “Bind LIKE pattern là đủ để tìm literal text”

Không đúng khi `%`, `_` có wildcard semantics. Cần escape theo contract để tránh semantic overmatching, đồng thời bind pattern để chống injection.

## 40. “Một placeholder JDBC tự mở rộng List”

Không portable. JPQL/ORM extensions và native JDBC có list binding rules khác nhau. Phải dùng collection support đã kiểm chứng hoặc tạo placeholder count và bind từng phần tử.

## 41. “Danh sách IN rỗng thì bỏ WHERE là hợp lý”

Rất nguy hiểm. `IN []` thường có ý nghĩa **không bản ghi nào**, không phải tất cả bản ghi. Bỏ filter có thể gây lộ dữ liệu hàng loạt.

## 42. “Bind tenantId nghĩa là caller được phép đọc tenant đó”

Không đúng. Bind bảo vệ syntax; tenant scope phải lấy từ security context/authorization đã xác minh.

## 43. “SQL log chứa dấu ? nghĩa là query không có rủi ro injection”

Không nhất thiết. Một phần query structure khác vẫn có thể nối từ input. Phải review toàn bộ query builder.

## 44. “Tham số hóa giúp mọi query nhanh hơn”

Không có lời hứa đó. Plan quality, index, cardinality, SQL shape và DB optimizer vẫn quyết định performance.

## 45. “Native SQL không thể tham số hóa”

Sai. `EntityManager.createNativeQuery(...).setParameter(...)` và JDBC `PreparedStatement` đều có cơ chế bind values. Chỉ cần biết provider/dialect limitations.

## 46. “Validation email thay thế parameter binding”

Sai. Validation bảo vệ business shape; binding bảo vệ ranh giới syntax/data.

## 47. “Chỉ dữ liệu nhập trực tiếp từ HTTP mới không tin cậy”

Sai. Dữ liệu lấy từ queue, CSV, external API hoặc database record cũ cũng có thể không đáng tin. Không tạo second-order injection.

---

# Phần XI — Bài tập thực hành

## 48. Tình huống có lời giải

### Bài 1. Ghép email vào JPQL

```java
String jpql =
    "SELECT u FROM UserAccount u WHERE u.email = '"
    + email + "'";
```

**Lời giải:** Dùng `WHERE u.email = :email` và `.setParameter("email", email)`.

### Bài 2. Ghép account ID vào SQL

```java
String sql =
    "SELECT * FROM user_accounts WHERE id = " + rawId;
```

**Lời giải:** Parse/validate ID thành `Long`; dùng positional parameter và `setParameter`. Không ghép raw input.

### Bài 3. JPQL có `:email` nhưng bind tên `userEmail`

**Lời giải:** Tên binding phải trùng `email`, không có dấu hai chấm. Đây là lỗi programming, không phải row vắng mặt.

### Bài 4. JPQL positional parameters bắt đầu từ đâu?

**Lời giải:** Chỉ số bắt đầu từ 1: `?1` tương ứng `setParameter(1, ...)`.

### Bài 5. Native query dùng named params với Hibernate

**Lời giải:** Có thể được Hibernate hỗ trợ, nhưng khi portability quan trọng phải kiểm tra JPA/provider/version mục tiêu. Không suy rộng cho mọi provider.

### Bài 6. ORDER BY do user gửi

**Lời giải:** Không ghép trực tiếp và không bind như value. Chuyển field/direction qua enum/allowlist thành trusted fragments hoặc Criteria order expressions.

### Bài 7. Sort field hợp regex `[A-Za-z0-9_.]+`

**Lời giải:** Vẫn cần allowlist vì ký tự hợp lệ không chứng minh người dùng được phép sort theo field đó.

### Bài 8. Tìm literal `100%`

**Lời giải:** Escape `%` thành `!%` và dùng `ESCAPE '!'`, bind pattern. Nếu tự thêm surrounding `%`, escape input trước.

### Bài 9. Tìm literal `A_B`

**Lời giải:** Escape `_` thành `!_`, không coi `_` là wildcard.

### Bài 10. Input có dấu `!`

**Lời giải:** Escape `!` thành `!!` trước `%` và `_` để bảo đảm pattern có nghĩa literal đúng.

### Bài 11. `IN` list rỗng

**Lời giải:** Trả empty result hoặc xử lý theo contract. Không bỏ filter rồi trả toàn bảng.

### Bài 12. Native `IN (?)` với Java `List<Long>`

**Lời giải:** Không portable. Dùng list binding provider-supported hoặc tạo số placeholder cố định theo list length rồi bind từng value.

### Bài 13. User gửi 100.000 IDs

**Lời giải:** Binding không ngăn query/resource exhaustion. Áp input limit và cân nhắc staging/table-valued strategy.

### Bài 14. Filter `email = :email` với `email=null`

**Lời giải:** Dùng `IS NULL` nếu ý muốn tìm rows null, hoặc bỏ predicate nếu null nghĩa là “không lọc”. Quy tắc phải explicit.

### Bài 15. User thuộc tenant 100 gửi `tenantId=200`

**Lời giải:** Không tin input làm authorization. Lấy tenant từ authenticated context và kiểm tra membership/ownership.

### Bài 16. Native UPDATE đã bind tên và ID

**Lời giải:** Vẫn phải thêm `tenant_id`/ownership predicate và kiểm tra affected rows; binding không thay authorization.

### Bài 17. @BatchSize trong Hibernate

**Lời giải:** Không liên quan trực tiếp injection; cũng không tự cải thiện sự an toàn của dynamic queries.

### Bài 18. SQL logs chứa bind values

**Lời giải:** Có thể lộ PII/secrets. Giới hạn TRACE, redact và không gửi raw SQL error ra client.

### Bài 19. Native PostgreSQL JSON operator `?`

**Lời giải:** Có thể xung đột parameter parsing của provider. Sử dụng syntax tương thích hoặc JDBC adapter, integration test. Không ghép raw input để tránh parser.

### Bài 20. Query có `LIMIT` lấy từ request

**Lời giải:** Validate page size và ưu tiên `setMaxResults`/`setFirstResult` khi phù hợp. Không nối raw limit.

### Bài 21. Dynamic table name của báo cáo

**Lời giải:** Chọn từ enum/allowlist constants; không bind table name như value hoặc nhận arbitrary table name.

### Bài 22. Input đã được lưu trong database, sau đó ghép vào SQL

**Lời giải:** Vẫn là untrusted data, có thể là second-order injection. Bind dù value đến từ DB.

### Bài 23. Tìm kiếm có `%keyword%` và index không được dùng

**Lời giải:** Đó là query performance. Xem full-text/trigram/index strategy; không bỏ parameterization.

### Bài 24. `CriteriaBuilder` dùng `root.get(requestedField)`

**Lời giải:** Không tự bảo đảm quyền/sort policy. Map input qua enum field allowlist.

### Bài 25. Spring Data `findByTenantIdAndEmail`

**Lời giải:** Derived query parameterize values; phải bảo đảm tenant ID thuộc authenticated context và phương thức được dùng đúng.

### Bài 26. Test chỉ dùng email `alice@example.com`

**Lời giải:** Chưa đủ để phát hiện nối chuỗi nguy hiểm. Thêm ký tự đặc biệt như dấu nháy và test native/JPQL paths.

### Bài 27. Client gửi `sort=createdAt DESC`

**Lời giải:** API nên nhận field/direction tách riêng hoặc parse từ allowlist; không chấp nhận raw JPQL fragment.

### Bài 28. Native DELETE tác động tất cả tenants

**Lời giải:** Đó là lỗi authorization/tenant scoping, dù values đều parameterized. Thêm policy và test cross-tenant writes.

### Bài 29. Dùng SQL string escaping rồi vẫn gọi `setParameter`

**Lời giải:** Có thể biến đổi input sai. Đối với equality, bind nguyên giá trị; với LIKE wildcard có helper escape riêng cho pattern semantics.

### Bài 30. Dùng `List<String>` email vào native SQL IN

**Lời giải:** Không join với dấu nháy. Dùng placeholders/typed binding, hoặc provider-specific list parameter đã kiểm chứng.

### Bài 31. Một câu JPQL có tên property lấy từ cấu hình không tin cậy

**Lời giải:** Config cũng có thể là untrusted input. Chỉ chấp nhận allowed paths hoặc query templates do application sở hữu.

### Bài 32. Query không injection nhưng vẫn trả 10 triệu rows

**Lời giải:** Cần pagination, authorization, rate limits, query timeout và index. Parameterization không giải quyết resource exhaustion.

### Bài 33. Một database user có quyền tạo/xóa schema

**Lời giải:** Áp least privilege để giảm thiệt hại nếu xuất hiện lỗi ở SQL path khác.

### Bài 34. Query `u.email = :email` đã bind an toàn, nhưng request cho ID tùy ý

**Lời giải:** Injection safety không thay object-level access checks. Bổ sung ownership/tenant authorization.

### Bài 35. Integration test trên H2 pass nhưng PostgreSQL LIKE khác

**Lời giải:** Test collation, escape semantics và SQL placeholder behavior trên provider/database production tương ứng.

---

## 49. Checklist quyết định giải pháp

Khi xây bất kỳ JPQL/native SQL query nào nhận dữ liệu ngoài application, hãy theo trình tự:

1. **Xác định structure**: phần nào do code chọn và phần nào là user value?
2. **Giữ template tin cậy**: không nối raw input vào JPQL/SQL source.
3. **Bind values**: dùng named/positional parameters đúng provider/version.
4. **Allowlist structural choices**: field, direction, operator, table, function.
5. **Validation nghiệp vụ**: format, type, size, value ranges.
6. **LIKE semantics**: plain text cần escape wildcard, pattern search cần contract rõ.
7. **Collection semantics**: `IN` rỗng, limit sizes, native expansion portability.
8. **Authorization**: tenant, owner, role và object scope.
9. **Resource safety**: pagination, timeout, rate limit, index/plan.
10. **Database correctness**: constraints, schema, transaction boundaries.
11. **Test thực**: JPQL, native, sorting, LIKE và cross-tenant access.
12. **Log an toàn**: không lộ SQL/bind values chứa dữ liệu nhạy cảm.

---

## 50. Sơ đồ ra quyết định

```text
                 Dữ liệu đi vào query
                           |
                           v
             Có phải giá trị dữ liệu?
                  /                 \
                Có                  Không
                |                     |
                v                     v
         Dùng bind parameter     Có phải cấu trúc query:
         + đúng Java type        identifier/keyword/operator?
                |                     |
                |                     v
                |                Chỉ lấy từ allowlist
                |                hoặc trusted templates
                |                     |
                +----------+----------+
                           |
                           v
                Có LIKE/IN/NULL không?
                           |
               +-----------+------------+
               |           |            |
               v           v            v
          Escape LIKE   Handle list   Define null
           wildcards    empty/limit   semantics
               |           |            |
               +-----------+------------+
                           |
                           v
               Apply tenant/authorization
                           |
                           v
              Apply resource limits
                           |
                           v
              Execute via JPA/JDBC binding
                           |
                           v
              Verify results + audit safely
```

**Một truy vấn an toàn không chỉ tránh injection mà còn bảo vệ đúng phạm vi dữ liệu và tài nguyên.**

---

## 51. Tổng kết

Có thể cô đọng nội dung bài vào ba quy tắc không được đánh đổi:

**Quy tắc 1 — Giá trị luôn được bind:**

```java
String jpql =
    "SELECT u FROM UserAccount u WHERE u.email = :email";

em.createQuery(jpql, UserAccount.class)
  .setParameter("email", input)
  .getResultList();
```

**Quy tắc 2 — Cấu trúc động phải được chọn từ tập cho phép:**

```java
String orderBy = switch (sortField) {
    case CREATED_AT -> "u.createdAt";
    case EMAIL -> "u.email";
    case DISPLAY_NAME -> "u.displayName";
};
```

**Quy tắc 3 — An toàn query source không thay policy dữ liệu:**

```jpql
WHERE u.id = :id
  AND u.tenantId = :authenticatedTenant
```

với `authenticatedTenant` lấy từ security context đã xác minh và business authorization logic phù hợp.

Những điểm quan trọng cuối:

- **JPQL vẫn có injection risk nếu nối input thành JPQL text**; ORM không tự sửa lỗi này.
- **Native SQL có parameter binding**; khi portability quan trọng, kiểm tra marker/named parameter support theo provider/version.
- **Named và positional params chỉ đại diện cho dữ liệu**, không đại diện cho table/column names hoặc SQL keywords.
- **`ORDER BY` dynamic phải có allowlist**, ngay cả khi dùng Criteria API.
- **`LIKE` cần escape `%`, `_` và escape character** nếu input được hiểu là plain text.
- **`IN` list rỗng phải xử lý rõ**, không bỏ filter và vô tình đọc toàn bộ bảng.
- **Binding không thay validation, authorization hoặc tenant isolation**.
- **DML native/bulk được parameterize vẫn có thể làm stale JPA persistence context** và phải xử lý transaction semantics.
- **Không đánh giá an toàn chỉ từ SQL logs có `?`**, vì một phần khác của query có thể đã bị ghép raw input.
- **Bảo mật truy vấn cần kiểm thử trên database/provider thật**, bao gồm đặc thù `LIKE`, native parameter syntax và các request cross-tenant.

**Tham số hóa là hàng rào bắt buộc giữa giá trị không tin cậy và cú pháp JPQL/SQL. Hãy để ứng dụng kiểm soát cấu trúc truy vấn, để JPA/JDBC bind dữ liệu, và để authorization quyết định người dùng được phép thao tác trên những bản ghi nào.**
