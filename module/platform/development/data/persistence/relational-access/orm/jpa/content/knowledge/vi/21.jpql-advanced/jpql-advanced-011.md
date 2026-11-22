# Gọi hàm cơ sở dữ liệu qua FUNCTION và đánh giá tính khả chuyển trong JPQL

Trong **Jakarta Persistence (JPA)**, JPQL (*Jakarta Persistence Query Language*) cho phép truy vấn theo **entity và thuộc tính Java**, thay vì viết trực tiếp tên bảng, cột và cú pháp SQL của một hệ quản trị cơ sở dữ liệu. Tuy nhiên, khi xây dựng ứng dụng thực tế, đôi khi ta cần một hàm mà bộ hàm JPQL chuẩn không trực tiếp biểu diễn: bỏ dấu tiếng Việt khi tìm kiếm, gom thời gian theo ngày, xử lý JSON, chuẩn hóa chuỗi theo quy tắc của database hoặc dùng một phép tính chuyên biệt.

JPQL có biểu thức **`FUNCTION`** để gọi những hàm do database hoặc provider hỗ trợ:

~~~jpql
SELECT c
FROM Customer c
WHERE FUNCTION('unaccent', c.fullName) = :normalizedName
~~~

Đây là cơ chế mở rộng quan trọng, nhưng cần hiểu đúng: **cú pháp `FUNCTION` là một phần của JPQL; tên hàm, kiểu đối số, kiểu trả về và hành vi thực tế của hàm có thể không khả chuyển giữa các database**.

Bài học thuộc chương **JPQL nâng cao** của chủ đề **Data Persistence Relational Access ORM JPA**, tập trung vào bốn câu hỏi:

1. Cách viết, truyền tham số và gọi **hàm SQL từ JPQL** bằng `FUNCTION('name', ...)`.
2. Cách tạo biểu thức tương đương trong **Criteria API** với `CriteriaBuilder.function(...)`.
3. Cách xác định những phần nào **portable** và những phần nào phụ thuộc **provider, dialect hoặc database**.
4. Cách tổ chức code, thiết kế kiểm thử và tối ưu truy vấn để việc sử dụng hàm đặc thù không trở thành một phụ thuộc khó bảo trì.

## 1. Phân biệt ba loại hàm trong truy vấn

Trước khi sử dụng `FUNCTION`, cần phân biệt:

| Nhóm | Ví dụ | Cách gọi | Mức độ khả chuyển |
| --- | --- | --- | --- |
| Hàm/biểu thức chuẩn trong JPQL | `LOWER`, `UPPER`, `LENGTH`, `CONCAT`, `ABS`, `CURRENT_TIMESTAMP` | `LOWER(c.email)` | Cao hơn nếu tuân thủ đặc tả và mapping chuẩn |
| Hàm database qua JPQL `FUNCTION` | PostgreSQL `unaccent`, `date_trunc`; MySQL `date_format` | `FUNCTION('date_trunc', 'day', o.createdAt)` | Phụ thuộc database, driver, provider và cấu hình |
| Hàm SQL trong native query | CTE, hàm JSON/array, toán tử vendor-specific | `SELECT date_trunc('day', created_at) ...` | Phụ thuộc trực tiếp SQL dialect |

**Quy tắc đầu tiên:** khi JPQL chuẩn đã cung cấp đúng ngữ nghĩa, nên ưu tiên hàm chuẩn hơn là viết cùng hàm qua `FUNCTION`.

Ví dụ tìm email không phân biệt chữ hoa/chữ thường theo cách đơn giản:

~~~jpql
SELECT c
FROM Customer c
WHERE LOWER(c.email) = LOWER(:email)
~~~

Đây là JPQL chuẩn. Không cần:

~~~jpql
SELECT c
FROM Customer c
WHERE FUNCTION('lower', c.email) = FUNCTION('lower', :email)
~~~

Cách thứ hai khiến truy vấn phụ thuộc vào khả năng xử lý `FUNCTION` và nhận diện kiểu hơn mức cần thiết, dù nhiều database có hàm SQL `lower`.

### 1.1. “Portable” không có nghĩa cùng kết quả tuyệt đối trên mọi database

Cú pháp JPQL chuẩn mang lại một lớp trừu tượng, nhưng kết quả vẫn có thể chịu ảnh hưởng:

- Collation và cách so sánh chuỗi.
- Độ chính xác số học, kiểu decimal/floating point.
- Quy tắc làm tròn của database.
- Time zone, precision và mapping ngày giờ.
- Cách xử lý `NULL` hoặc khả năng tối ưu hóa truy vấn.

Vì vậy tính khả chuyển cần đánh giá ở **cú pháp, kiểu dữ liệu, ngữ nghĩa và hiệu năng**, chứ không chỉ ở câu hỏi “có chạy được trên hai database hay không?”.

## 2. Cú pháp FUNCTION trong JPQL

Cú pháp tổng quát:

~~~text
FUNCTION('ten_ham_sql', bieu_thuc_1, bieu_thuc_2, ...)
~~~

Hình thức đơn giản nhất không có đối số:

~~~jpql
SELECT FUNCTION('some_database_function')
FROM Customer c
~~~

Cách viết phổ biến hơn:

~~~jpql
SELECT FUNCTION('unaccent', c.fullName)
FROM Customer c
~~~

Hoặc hàm có nhiều đối số:

~~~jpql
SELECT FUNCTION('date_trunc', 'day', o.createdAt)
FROM PurchaseOrder o
~~~

Các thành phần:

- `FUNCTION` là từ khóa JPQL.
- `'unaccent'` hoặc `'date_trunc'` là **tên hàm**, viết dưới dạng chuỗi literal trong cú pháp JPQL.
- Các đối số sau tên hàm là biểu thức JPQL: field entity, parameter, literal hoặc biểu thức khác.
- Provider dịch biểu thức này thành SQL phù hợp với cách nó hỗ trợ hàm được gọi.
- Database phải **thực sự có hàm tương thích**, hoặc provider phải được cấu hình một cách hỗ trợ phù hợp.

### 2.1. Chuỗi tên hàm không phải tham số dữ liệu

Trong JPQL:

~~~jpql
FUNCTION('unaccent', c.fullName)
~~~

`'unaccent'` là tên hàm xác định ngay trong cấu trúc query. Không được giả định có thể thay nó bằng một parameter:

~~~jpql
-- Không phải cách portable để chọn tên hàm động:
FUNCTION(:functionName, c.fullName)
~~~

Tham số `:functionName` trong JPQL là **giá trị**, không phải một thành phần cú pháp có thể được thay thành tên hàm SQL tùy ý.

Nếu ứng dụng hỗ trợ một số chiến lược tìm kiếm, hãy chọn giữa **các truy vấn được định nghĩa sẵn** hoặc xây query từ danh sách hàm được phép ở tầng ứng dụng. Không đưa một tên hàm do client tự gửi trực tiếp vào JPQL hoặc SQL.

### 2.2. FUNCTION không phải stored procedure

`FUNCTION('name', ...)` là cách sử dụng **biểu thức hàm trong câu truy vấn**. Nó không tương đương với lời gọi stored procedure độc lập.

JPA có `StoredProcedureQuery` khi muốn gọi stored procedure thông qua API riêng. Database cũng có thể có stored function trả giá trị, nhưng khả năng gọi nó trong câu SELECT và việc xử lý OUT parameter không giống stored procedure.

Đừng lạm dụng `FUNCTION` để gọi các routine có **side effect** (cập nhật bảng, gửi thông báo, thao tác trạng thái ngoài DB) từ SELECT thông thường. Việc SQL optimizer thực thi hàm bao nhiêu lần và ở thời điểm nào không phải hợp đồng nghiệp vụ phù hợp cho các tác dụng phụ.

## 3. Mô hình ví dụ tự chứa

Dùng Java 17+, namespace **`jakarta.persistence`**. Với các dự án JPA 2.x cũ, đổi sang namespace `javax.persistence` tương ứng với dependency phiên bản đó.

### 3.1. Entity Customer

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDateTime;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 160)
    private String fullName;

    @Column(name = "email", nullable = false, unique = true, length = 180)
    private String email;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected Customer() {
    }

    public Customer(String fullName, String email, LocalDateTime createdAt) {
        this.fullName = fullName;
        this.email = email;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
~~~

### 3.2. Entity PurchaseOrder

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
import java.time.LocalDateTime;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(name = "total_amount", precision = 15, scale = 2, nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
~~~

### 3.3. Schema minh họa

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(160) NOT NULL,
    email VARCHAR(180) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE INDEX idx_orders_created_at
    ON purchase_orders (created_at);
~~~

Các câu `CREATE TABLE` chỉ minh họa mô hình quan hệ và giả định database hỗ trợ cú pháp tương ứng. Không phải JPA provider nào cũng dùng chính xác một DDL này; các ví dụ `FUNCTION` phía dưới nêu rõ database mục tiêu khi cần.

## 4. Ví dụ: gọi unaccent của PostgreSQL qua FUNCTION

Một ứng dụng cần tìm khách hàng theo tên, cho phép người dùng gõ `Nguyen` và tìm thấy `Nguyễn`. PostgreSQL có extension **`unaccent`** giúp loại bỏ dấu/biến thể accent trong những tình huống phù hợp.

### 4.1. Điều kiện tiên quyết trên PostgreSQL

Trên PostgreSQL có hỗ trợ extension và tài khoản được cấp quyền thích hợp:

~~~sql
CREATE EXTENSION IF NOT EXISTS unaccent;
~~~

Hàm `unaccent` không nên được xem là hàm SQL/JPA chuẩn có mặt sẵn trong mọi database. Việc triển khai extension, schema, quyền truy cập và search path có thể khác nhau giữa môi trường.

Ví dụ minh họa trực tiếp trong PostgreSQL:

~~~sql
SELECT unaccent('Nguyễn Văn A');
-- Một kết quả kỳ vọng với dictionary thông thường:
-- Nguyen Van A
~~~

Kết quả phụ thuộc quy tắc chuyển đổi của extension/dictionary đang dùng. Không coi thao tác bỏ dấu là phép so sánh Unicode chuẩn tuyệt đối trong mọi ngôn ngữ.

### 4.2. JPQL qua FUNCTION

~~~java
String jpql =
    """
    SELECT c
    FROM Customer c
    WHERE LOWER(FUNCTION('unaccent', c.fullName)) LIKE :pattern
    ORDER BY c.id
    """;

List<Customer> customers = em.createQuery(jpql, Customer.class)
    .setParameter("pattern", "%nguyen%")
    .getResultList();
~~~

Trong truy vấn:

1. `c.fullName` là attribute JPA của `Customer`.
2. `FUNCTION('unaccent', c.fullName)` yêu cầu dùng hàm `unaccent` khi SQL được thực thi.
3. `LOWER(...)` là hàm JPQL chuẩn, dùng để đưa kết quả về chữ thường.
4. `LIKE :pattern` so khớp với một mẫu chuỗi.
5. Tham số được binding thay vì ghép input trực tiếp vào JPQL.

SQL mục tiêu có thể có ý tưởng tương đương:

~~~sql
SELECT c.*
FROM customers c
WHERE LOWER(unaccent(c.full_name)) LIKE ?
ORDER BY c.id;
~~~

**Đây chỉ là SQL minh họa.** Provider phải hỗ trợ cách diễn giải kiểu trả về của `unaccent` trong biểu thức `LOWER`. Một số phiên bản/provider cần đăng ký hàm với kiểu trả về `String` hoặc có hạn chế về kiểm tra kiểu truy vấn; không thể chỉ nhìn cú pháp JPQL rồi bảo đảm query chạy trên mọi môi trường.

### 4.3. Vì sao không dùng LOWER là đủ?

~~~jpql
LOWER(c.fullName) LIKE :pattern
~~~

giúp giảm khác biệt chữ hoa/chữ thường theo khả năng database, nhưng **không phải phép loại bỏ dấu tiếng Việt**. Chuỗi `Nguyễn` không trở thành `Nguyen` chỉ nhờ LOWER trong mọi collation.

Bài toán bỏ dấu có thể được giải theo nhiều hướng:

- Hàm `unaccent` của PostgreSQL.
- Một collation có đặc tính accent-insensitive được DB hỗ trợ.
- Một cột tìm kiếm đã chuẩn hóa do ứng dụng duy trì.
- Công cụ full-text search hoặc search engine chuyên dụng nếu cần search phong phú.

`FUNCTION` giúp gọi một lựa chọn database-specific; nó **không giải quyết tự động tất cả ngữ nghĩa tìm kiếm**.

## 5. Truyền tham số an toàn khi dùng FUNCTION

Hàm có thể nhận tham số dữ liệu:

~~~jpql
SELECT c
FROM Customer c
WHERE FUNCTION('unaccent', c.fullName)
      = FUNCTION('unaccent', :inputName)
~~~

Về nguyên tắc, `:inputName` là parameter dữ liệu được binding:

~~~java
query.setParameter("inputName", userInput);
~~~

Điều này tốt hơn ghép input vào chuỗi JPQL:

~~~java
// Không làm như sau:
String jpql =
    "SELECT c FROM Customer c " +
    "WHERE FUNCTION('unaccent', c.fullName) = '" +
    userInput + "'";
~~~

Ghép chuỗi trực tiếp làm tăng nguy cơ lỗi escaping và JPQL injection.

### 5.1. Parameter binding không vô hiệu hóa wildcard của LIKE

Giả sử code:

~~~java
String pattern = "%" + userInput + "%";
query.setParameter("pattern", pattern);
~~~

Việc bind parameter giúp giữ **cấu trúc truy vấn** ổn định, nhưng ký tự `%` và `_` trong input vẫn có **ngữ nghĩa wildcard của LIKE**. Nếu nghiệp vụ muốn tìm **đúng chuỗi người dùng nhập**, cần escape các ký tự đặc biệt theo quy tắc LIKE.

Ví dụ dùng ký tự escape `!`:

~~~java
public static String escapeLike(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
~~~

JPQL:

~~~jpql
SELECT c
FROM Customer c
WHERE LOWER(c.fullName) LIKE :pattern ESCAPE '!'
~~~

Binding:

~~~java
String pattern =
    "%" + escapeLike(userInput.toLowerCase(java.util.Locale.ROOT)) + "%";

query.setParameter("pattern", pattern);
~~~

Ví dụ này giải quyết **literal LIKE matching**, chưa tự giải quyết việc bỏ dấu; nếu áp dụng thêm `unaccent`, cần chuẩn hóa input theo cùng quy tắc được chọn và chú ý khả năng support của provider.

### 5.2. Không nhận tên hàm trực tiếp từ request

Một API kiểu:

~~~text
GET /customers?dbFunction=some_name
~~~

không nên trực tiếp biến `some_name` thành một literal hàm SQL được nối vào câu truy vấn. Tên hàm có ảnh hưởng tới **cấu trúc SQL** và khả năng gọi routine không mong muốn.

Tốt hơn, ứng dụng có một whitelist rõ:

~~~java
public enum SearchMode {
    EXACT,
    CASE_INSENSITIVE,
    ACCENT_INSENSITIVE
}
~~~

Dựa vào `SearchMode`, repository chọn một truy vấn chuẩn hoặc một truy vấn đặc thù đã định nghĩa sẵn. Không cho client đặt tên hàm tùy ý.

## 6. FUNCTION trong SELECT: nhận kiểu kết quả như thế nào?

`FUNCTION` có thể xuất hiện trong projection:

~~~jpql
SELECT FUNCTION('unaccent', c.fullName)
FROM Customer c
ORDER BY c.id
~~~

Hoặc lấy cả ID và chuỗi chuẩn hóa:

~~~jpql
SELECT c.id, FUNCTION('unaccent', c.fullName)
FROM Customer c
ORDER BY c.id
~~~

Trong JPQL, việc provider suy luận kiểu trả về cho **hàm không chuẩn** có thể phụ thuộc cơ chế đăng ký hàm, dialect và hỗ trợ biểu thức. Không nên mặc định tất cả provider sẽ biết rằng `unaccent` trả `String` nếu nó chưa được khai báo trong metadata của provider.

Một cách truy xuất tương đối ít giả định về generic result type là lấy `Object[]`:

~~~java
List<Object[]> rows = em.createQuery(
    """
    SELECT c.id, FUNCTION('unaccent', c.fullName)
    FROM Customer c
    ORDER BY c.id
    """,
    Object[].class
).getResultList();

for (Object[] row : rows) {
    Long id = (Long) row[0];

    Object normalizedValue = row[1];
    String normalizedName =
        normalizedValue == null ? null : normalizedValue.toString();

    System.out.println(id + ": " + normalizedName);
}
~~~

Ví dụ này vẫn giả định provider/DB cho phép thực thi `unaccent`. Cách chuyển `toString()` chỉ thích hợp khi ta **biết rõ ngữ nghĩa hàm trả dữ liệu dạng text**; không dùng tương tự cho hàm trả ngày giờ, số hoặc JSON binary mà không kiểm tra kiểu.

### 6.1. Typed query không ép database chuyển kiểu

Không nên suy luận:

~~~java
em.createQuery(
    "SELECT FUNCTION('some_date_function', o.createdAt) " +
    "FROM PurchaseOrder o",
    java.time.LocalDateTime.class
);
~~~

sẽ ép hàm SQL bất kỳ trả đúng `LocalDateTime`. Class truyền vào `createQuery` diễn đạt kiểu kết quả mong muốn ở JPA, nhưng **không thay thế kiểu trả về thực của hàm SQL hoặc khả năng mapping của provider**.

Với một số hàm chưa đăng ký, provider có thể không suy luận được kiểu để dùng trong `SELECT new ...`, `WHERE`, `GROUP BY` hoặc phép so sánh. Khi đó cần:

- Dùng hàm JPQL chuẩn nếu có.
- Đăng ký function descriptor/return type theo provider khi hỗ trợ.
- Dùng native SQL và mapping result rõ ràng.
- Hoặc chọn một thiết kế query khác tránh hàm đặc thù.

### 6.2. FUNCTION trong DTO constructor expression

Ví dụ ý tưởng:

~~~jpql
SELECT new com.example.shop.dto.CustomerSearchRow(
    c.id,
    FUNCTION('unaccent', c.fullName)
)
FROM Customer c
~~~

Để chạy được, DTO cần constructor tương thích:

~~~java
package com.example.shop.dto;

public record CustomerSearchRow(
    Long customerId,
    String normalizedName
) {
}
~~~

**Điểm cần kiểm tra:** provider có nhận diện kết quả `unaccent` là `String` và hỗ trợ truyền nó vào constructor hay không. Nếu không, việc compile/validate query có thể lỗi ngay từ startup hoặc lúc thực thi.

Không nên dùng DTO constructor expression với một hàm tùy ý rồi khẳng định type checking của mọi JPA provider đều suy ra đúng chỉ từ record Java.

## 7. FUNCTION trong WHERE: giữ kiểu so sánh nhất quán

Đây là tình huống điển hình:

~~~jpql
SELECT c
FROM Customer c
WHERE FUNCTION('unaccent', c.fullName)
      = FUNCTION('unaccent', :name)
~~~

Hai phía dùng cùng kiểu hàm có thể cho kết quả nhất quán hơn so với chuẩn hóa một phía, nhưng không tự bảo đảm tương đương về:

- Collation.
- Unicode normalization.
- Dấu câu và khoảng trắng.
- Quy tắc chữ hoa/thường.
- Mapping kiểu SQL.
- `NULL`.

Nếu cần tìm không phân biệt dấu **và** hoa/thường, có thể chuẩn hóa cả hai phía:

~~~jpql
SELECT c
FROM Customer c
WHERE LOWER(FUNCTION('unaccent', c.fullName))
      = LOWER(FUNCTION('unaccent', :name))
~~~

Vẫn cần lưu ý tương thích kiểu/trình biên dịch JPQL. Nếu provider không hỗ trợ lồng hàm chưa đăng ký bên trong `LOWER`, có thể phải đăng ký return type của `unaccent`.

### 7.1. Chú ý NULL

Trong SQL, đa số hàm xử lý input `NULL` theo quy tắc riêng của hàm. Với những hàm strict kiểu thông thường, input null thường trả null. So sánh:

~~~jpql
FUNCTION('unaccent', c.fullName) = :name
~~~

với `:name = null` **không tương đương** truy vấn `IS NULL` trong SQL logic ba giá trị.

Nếu nghiệp vụ cần truy vấn giá trị null, dùng điều kiện rõ:

~~~jpql
SELECT c
FROM Customer c
WHERE c.fullName IS NULL
~~~

Trong entity mẫu `fullName` được khai báo NOT NULL, ví dụ này chỉ minh họa cú pháp cho model có thuộc tính nullable.

**Không giả định mọi custom database function là null-propagating.** Một số hàm trả giá trị mặc định, một số báo lỗi và một số nhận nhiều đối số với logic null khác nhau. Kiểm tra semantics của hàm trên database mục tiêu.

## 8. FUNCTION trong ORDER BY

Đôi khi thứ tự sắp xếp không thể biểu diễn đúng chỉ bằng một thuộc tính Java, ví dụ muốn sắp xếp tên bỏ dấu:

~~~jpql
SELECT c
FROM Customer c
ORDER BY FUNCTION('unaccent', c.fullName) ASC, c.id ASC
~~~

Khi chạy trên PostgreSQL với hàm phù hợp, provider có thể tạo SQL:

~~~sql
SELECT c.*
FROM customers c
ORDER BY unaccent(c.full_name) ASC, c.id ASC;
~~~

Các lưu ý quan trọng:

1. **Tên hàm phụ thuộc DB**: `unaccent` không sẵn có trong mọi hệ thống.
2. **Collation vẫn ảnh hưởng thứ tự**: bỏ dấu không tự quy định mọi luật so sánh chuỗi.
3. **Trùng giá trị sau chuẩn hóa**: nhiều tên có thể cùng chuỗi không dấu; thêm `c.id` giúp thứ tự ổn định hơn.
4. **Hiệu năng sort**: database có thể phải tính hàm cho nhiều hàng và thực hiện sort.
5. **Phân trang**: muốn kết quả trang ổn định cần thứ tự đủ phân biệt; offset pagination còn chịu ảnh hưởng khi dữ liệu thay đổi đồng thời.

Không nên ép database tính function cho hàng triệu record khi chỉ muốn vài kết quả mà chưa đánh giá query plan và chỉ mục.

## 9. FUNCTION trong GROUP BY và thống kê theo ngày

Một ví dụ nâng cao rất thường gặp là **gom đơn hàng theo ngày**.

Giả sử `PurchaseOrder.createdAt` là `LocalDateTime`, ánh xạ vào cột `TIMESTAMP`. PostgreSQL có hàm `date_trunc`:

~~~sql
SELECT date_trunc('day', created_at) AS day_bucket,
       COUNT(*) AS total
FROM purchase_orders
GROUP BY date_trunc('day', created_at)
ORDER BY day_bucket;
~~~

JPQL có thể biểu diễn ý tưởng:

~~~jpql
SELECT FUNCTION('date_trunc', 'day', o.createdAt),
       COUNT(o)
FROM PurchaseOrder o
GROUP BY FUNCTION('date_trunc', 'day', o.createdAt)
ORDER BY FUNCTION('date_trunc', 'day', o.createdAt)
~~~

Đây là truy vấn mang tính **database-specific**. Nó chỉ chạy khi:

- Database cung cấp hàm `date_trunc` với signature thích hợp.
- Provider hỗ trợ truyền hai đối số tới hàm.
- Provider suy luận/xử lý được kiểu trả về khi dùng hàm trong `SELECT`, `GROUP BY` và `ORDER BY`.
- Kiểu timestamp của field `createdAt` phù hợp với signature của hàm.

Một ví dụ Java:

~~~java
List<Object[]> dailyCounts = em.createQuery(
    """
    SELECT FUNCTION('date_trunc', 'day', o.createdAt),
           COUNT(o)
    FROM PurchaseOrder o
    GROUP BY FUNCTION('date_trunc', 'day', o.createdAt)
    ORDER BY FUNCTION('date_trunc', 'day', o.createdAt)
    """,
    Object[].class
).getResultList();

for (Object[] row : dailyCounts) {
    Object bucket = row[0];
    Long count = (Long) row[1];

    System.out.println(bucket + " -> " + count);
}
~~~

Trong ví dụ, phần tử `bucket` có thể được map thành kiểu ngày giờ Java khác nhau tùy provider/driver và cách đăng ký hàm; vì vậy không ép cứng về `LocalDateTime` khi chưa xác định hợp đồng kiểu kết quả.

### 9.1. MySQL không có cùng API date_trunc

MySQL có những hàm xử lý ngày giờ khác, chẳng hạn `DATE_FORMAT`:

~~~sql
SELECT DATE_FORMAT(created_at, '%Y-%m-%d') AS day_bucket,
       COUNT(*) AS total
FROM purchase_orders
GROUP BY DATE_FORMAT(created_at, '%Y-%m-%d')
ORDER BY day_bucket;
~~~

`DATE_FORMAT` thường trả chuỗi. Trong khi đó, `date_trunc` trên PostgreSQL trả kiểu timestamp phù hợp với overload được gọi.

Hai câu query có thể cùng thể hiện nhóm theo ngày, nhưng **không có cùng tên hàm, chữ ký hoặc kiểu kết quả**.

Không chỉ đổi:

~~~jpql
FUNCTION('date_trunc', ...)
~~~

thành:

~~~jpql
FUNCTION('date_format', ...)
~~~

và mong mọi DTO, sorting và grouping tiếp tục có chính xác cùng semantics.

### 9.2. Time zone và ranh giới ngày

Với cột `TIMESTAMP WITHOUT TIME ZONE`, giá trị được lưu không tự chứa time zone. Với `TIMESTAMP WITH TIME ZONE`, database có thể xử lý thời điểm và chuyển đổi theo session time zone hoặc cú pháp hàm cụ thể.

Để nhóm “theo ngày của Việt Nam” từ các instant toàn cầu, phải xác định:

- Timestamp lưu dạng UTC instant hay giờ địa phương?
- “Ngày” được tính theo time zone của ai?
- Database session time zone được cấu hình ra sao?
- Các transaction/báo cáo có cùng quy tắc dùng giờ không?

**`FUNCTION` không tự giải quyết timezone.** Cùng một instant có thể thuộc hai ngày khác nhau ở hai time zone.

## 10. Khi nào không cần FUNCTION để xử lý ngày?

Giả sử yêu cầu chỉ là lấy những đơn hàng được tạo trong một ngày `LocalDate` đã biết. Một cách portable hơn thường là **tính khoảng thời gian ở Java rồi truy vấn range**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;

LocalDate day = LocalDate.of(2026, 11, 15);

LocalDateTime start = day.atStartOfDay();
LocalDateTime end = day.plusDays(1).atStartOfDay();

List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.createdAt >= :start
      AND o.createdAt < :end
    ORDER BY o.createdAt, o.id
    """,
    PurchaseOrder.class
)
.setParameter("start", start)
.setParameter("end", end)
.getResultList();
~~~

Ưu điểm:

- Không gọi hàm database đặc thù.
- Dùng so sánh `>=` và `<` của JPQL.
- Có cơ hội sử dụng B-tree index trên cột `created_at` tốt hơn so với bọc cột trong function, tùy query plan.
- Ranh giới nửa mở `[start, end)` tránh lỗi precision khi cố gán `23:59:59.999...`.
- Dễ kiểm thử điều kiện đầu/cuối ngày.

**Đây là ví dụ dành cho timestamp lưu theo cùng quy tắc local time như input.** Nếu dữ liệu lưu dạng instant UTC và nghiệp vụ chọn ngày theo một timezone, hãy chuyển **đầu ngày và đầu ngày kế tiếp** từ timezone nghiệp vụ thành instant tương ứng; không giả định mỗi ngày có đúng 24 giờ ở mọi múi giờ do DST.

### 10.1. So sánh hai thiết kế

| Yêu cầu | Giải pháp thường nên cân nhắc |
| --- | --- |
| Lấy bản ghi trong một ngày | Range query `createdAt >= start AND createdAt < end` |
| Sắp theo thời gian tạo | `ORDER BY o.createdAt` chuẩn |
| Lấy năm/tháng bằng logic Java khi đã có dữ liệu nhỏ | Xử lý ở Java nếu phù hợp |
| Báo cáo tổng hợp hàng triệu bản ghi theo ngày ngay trong DB | `date_trunc`/hàm tương ứng, với chiến lược DB cụ thể |
| Một API phải hoạt động trên nhiều DB | Ưu tiên JPQL chuẩn hoặc abstraction tách dialect |
| Tìm kiếm dấu tiếng Việt trên PostgreSQL | `unaccent` hoặc search/index chuyên dụng, có kiểm thử |
| Xử lý JSONB/array/spatial đặc thù | Native SQL hoặc `FUNCTION` khi provider hỗ trợ tốt |

Không nên dùng `FUNCTION` chỉ vì bài toán “nghe có vẻ cần hàm”. Trước hết kiểm tra có cách diễn đạt bằng JPQL chuẩn và chỉ mục tốt hơn không.

## 11. Gọi hàm trong Criteria API

JPQL dạng chuỗi thích hợp cho câu query ổn định. Nếu điều kiện tìm kiếm được xây động, **Criteria API** có phương thức:

~~~java
<T> Expression<T> function(
    String name,
    Class<T> type,
    Expression<?>... args
);
~~~

Ý nghĩa:

- `name`: tên hàm SQL.
- `type`: kiểu kết quả Java mà ứng dụng/Criteria model mong đợi.
- `args`: các biểu thức Criteria truyền vào hàm.

### 11.1. Ví dụ CriteriaBuilder.function với unaccent

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Expression;
import jakarta.persistence.criteria.Root;
import java.util.List;

public List<Customer> searchByNormalizedName(
        EntityManager em,
        String pattern) {

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Customer> cq =
        cb.createQuery(Customer.class);

    Root<Customer> customer = cq.from(Customer.class);

    Expression<String> unaccentedName =
        cb.function(
            "unaccent",
            String.class,
            customer.get("fullName")
        );

    Expression<String> lowerName =
        cb.lower(unaccentedName);

    cq.select(customer)
      .where(cb.like(lowerName, cb.parameter(String.class, "pattern")))
      .orderBy(cb.asc(customer.get("id")));

    TypedQuery<Customer> query = em.createQuery(cq);

    return query
        .setParameter("pattern", pattern)
        .getResultList();
}
~~~

Câu Criteria biểu diễn ý tưởng tương tự:

~~~jpql
SELECT c
FROM Customer c
WHERE LOWER(FUNCTION('unaccent', c.fullName)) LIKE :pattern
ORDER BY c.id
~~~

Phương thức trên giả định ứng dụng đã truyền pattern hợp lệ, chẳng hạn `"%nguyen%"`. Nếu input từ user, tầng gọi cần thực hiện quy tắc escape/normalization tương ứng.

### 11.2. Class<T> là khai báo kiểu, không phải SQL CAST

Trong:

~~~java
cb.function(
    "unaccent",
    String.class,
    customer.get("fullName")
);
~~~

`String.class` giúp Criteria API tạo một `Expression<String>`. Nó **không có nghĩa database được ép phải trả String** và không bảo đảm provider hỗ trợ function chưa đăng ký trong mọi vị trí của query.

Nếu function thực trả `timestamp` nhưng code khai báo `String.class`, bạn có thể gặp lỗi:

- SQL type mismatch.
- Validation của provider.
- JDBC mapping/conversion sai.
- ClassCastException khi lấy kết quả.
- Kết quả phụ thuộc dialect.

Chọn kiểu Java phù hợp với signature đã được xác định trên DB/provider, và thiết kế kiểm thử tích hợp cho trường hợp đó.

### 11.3. Nhiều đối số và literal

Ví dụ cho PostgreSQL `date_trunc`:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Object[]> cq = cb.createQuery(Object[].class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Expression<java.time.LocalDateTime> bucket =
    cb.function(
        "date_trunc",
        java.time.LocalDateTime.class,
        cb.literal("day"),
        order.get("createdAt")
    );

cq.multiselect(bucket, cb.count(order))
  .groupBy(bucket)
  .orderBy(cb.asc(bucket));

List<Object[]> rows = em.createQuery(cq).getResultList();
~~~

Đây là **ví dụ phụ thuộc PostgreSQL và khả năng mapping temporal result của provider**. Khai báo `LocalDateTime.class` thể hiện kỳ vọng của application, không phải sự bảo đảm database/proxy luôn trả kiểu đó. Trong hệ thống thực tế có thể cần đăng ký hàm và điều chỉnh kiểu temporal tương ứng.

## 12. Dùng FUNCTION trong NamedQuery

Nếu truy vấn sử dụng hàm cố định và được gọi ở nhiều nơi, có thể khai báo named query:

~~~java
@Entity
@Table(name = "customers")
@NamedQuery(
    name = "Customer.searchAccentInsensitive",
    query =
        "SELECT c FROM Customer c " +
        "WHERE LOWER(FUNCTION('unaccent', c.fullName)) " +
        "LIKE :pattern " +
        "ORDER BY c.id"
)
public class Customer {
    // Các field như ví dụ ở trên.
}
~~~

Gọi:

~~~java
List<Customer> results = em.createNamedQuery(
        "Customer.searchAccentInsensitive",
        Customer.class
    )
    .setParameter("pattern", "%nguyen%")
    .getResultList();
~~~

Cần chú ý:

- Tên named query là metadata của persistence unit.
- Query chứa `FUNCTION('unaccent', ...)` vẫn **không portable** sang DB không có `unaccent`.
- Một provider có thể validate named query khi khởi động; nếu không hiểu kiểu hàm, **application startup có thể thất bại** ngay cả khi chức năng tìm kiếm chưa được gọi.
- Tùy khả năng hỗ trợ, cần đăng ký function hoặc tách named query theo môi trường.

Named query giúp quản lý cấu trúc query, **không tự biến hàm SQL đặc thù thành hàm đa database**.

## 13. Tính khả chuyển gồm nhiều lớp

Khi đánh giá câu:

~~~jpql
FUNCTION('date_trunc', 'day', o.createdAt)
~~~

hãy xét các lớp sau.

### 13.1. Lớp 1: cú pháp JPQL

`FUNCTION('name', ...)` là cú pháp JPA chuẩn để gọi database function. Ở lớp này, ý tưởng có tính portable hơn việc chèn cú pháp SQL trực tiếp vào câu JPQL.

Nhưng cú pháp chuẩn chỉ cung cấp **cửa gọi hàm**, không định nghĩa mọi hàm có tên tùy ý.

### 13.2. Lớp 2: database có hàm hay không

PostgreSQL có `date_trunc`; MySQL phổ biến dùng các hàm ngày giờ khác, như `DATE_FORMAT`. Một database khác có thể có một hàm tên giống nhưng khác signature hoặc kiểu kết quả.

Câu JPQL hợp lệ vẫn có thể tạo SQL mà DB báo:

~~~text
function date_trunc(...) does not exist
~~~

hoặc lỗi tương ứng của hệ quản trị.

### 13.3. Lớp 3: provider biết hàm và kiểu trả về không

Hibernate, EclipseLink và các JPA provider khác có cơ chế diễn giải expression, suy luận kiểu và dịch SQL khác nhau.

Có trường hợp database đã có hàm nhưng provider vẫn báo lỗi ở bước parse/validation JPQL vì nó không biết kiểu trả về phù hợp để thực hiện phép so sánh, gọi hàm lồng nhau hoặc xây DTO projection.

Có thể cần **function registration/descriptor** theo provider, chứ không chỉ tạo hàm trong database.

### 13.4. Lớp 4: kiểu JDBC và mapping Java

Database có thể trả:

- `text/varchar` → `String`.
- `numeric/decimal` → `BigDecimal`.
- `timestamp` → kiểu ngày giờ qua JDBC/provider.
- `jsonb` → type/driver object hoặc giá trị được mapping riêng.
- `uuid` → `UUID` hoặc đại diện khác tùy driver/provider.
- Array/spatial → kiểu dữ liệu riêng.

Không đủ khi chỉ biết tên hàm; phải biết **kiểu trả về** và cách JPA đọc nó.

### 13.5. Lớp 5: ngữ nghĩa và kết quả

Ngay cả khi cả hai DB có `lower` hoặc `round`, chúng có thể khác về collation, Unicode, precision và quy tắc làm tròn trong một số tình huống. Hàm tên giống không tự bảo đảm hoàn toàn giống nhau.

### 13.6. Lớp 6: hiệu năng

Một database có thể dùng expression index hoặc computed column để tăng tốc; database khác không có tính năng tương tự, hoặc optimizer chọn plan khác.

Một câu query chạy đúng trên cả hai nơi vẫn có thể chênh lệch hiệu năng lớn.

| Lớp khả chuyển | Câu hỏi |
| --- | --- |
| Cú pháp JPQL | `FUNCTION`/Criteria expression có hợp lệ không? |
| Database function | DB mục tiêu có tên hàm và số đối số phù hợp không? |
| Provider | ORM nhận diện/dịch kiểu và cú pháp đúng không? |
| JDBC/Java type | Kết quả map về type cần dùng được không? |
| Semantics | Kết quả với NULL, Unicode, timezone, rounding có tương đương không? |
| Performance | Index và query plan có phù hợp với workload không? |
| Operations | Extension, permission và migration có được triển khai không? |

## 14. Bảng so sánh một số hàm đặc thù

Bảng dưới chỉ đưa ra **ví dụ định hướng**, không phải bản đồ thay thế cú pháp tự động. Đối với mỗi DB/version, phải xác định signature và kết quả thực tế.

| Mục đích | PostgreSQL (ví dụ) | MySQL (ví dụ) | Lựa chọn thường portable hơn |
| --- | --- | --- | --- |
| Đổi thành chữ thường | `lower(text)` | `lower(str)` | JPQL `LOWER(...)` |
| Ghép chuỗi | `concat(...)` | `concat(...)` | JPQL `CONCAT(...)` |
| Bỏ dấu khi tìm kiếm | `unaccent(text)` với extension | Collation hoặc cách chuẩn hóa riêng | Cột search text được chuẩn hóa, hoặc engine tìm kiếm |
| Gom timestamp theo ngày | `date_trunc('day', ts)` | `DATE_FORMAT(ts, '%Y-%m-%d')` hoặc biểu thức tương đương | Range query nếu chỉ lọc một ngày |
| Phân tách/chuẩn hóa bằng regex | `regexp_replace(...)` | `REGEXP_REPLACE(...)` ở phiên bản hỗ trợ | Chuẩn hóa tại ứng dụng nếu đủ nhu cầu |
| Xử lý dữ liệu JSON | `jsonb_extract_path_text(...)` và các toán tử JSONB | `JSON_EXTRACT(...)` | Mapping JSON có abstraction riêng, hoặc native SQL |
| Sinh/biến đổi text chuyên biệt | Extension hoặc user-defined function | Hàm/plugin tương ứng | Tách chức năng theo DB adapter |

Ví dụ PostgreSQL:

~~~jpql
FUNCTION('date_trunc', 'month', o.createdAt)
~~~

Ví dụ ý tưởng trên MySQL:

~~~jpql
FUNCTION('date_format', o.createdAt, '%Y-%m')
~~~

Hai biểu thức **không tương đương về type**: cái đầu thường trả timestamp đã cắt, cái sau trả chuỗi. Nếu dùng chúng chung cho DTO nhận `LocalDateTime` thì phiên bản MySQL có thể không tương thích.

## 15. Provider-specific registration: khi nào cần?

Có những tình huống provider không hiểu hàm chưa khai báo, dù database hiểu:

~~~jpql
SELECT FUNCTION('unaccent', c.fullName)
FROM Customer c
~~~

Đối với một số JPA provider hoặc phiên bản, có thể:

- Cho phép chuyển tiếp hàm ngay khi biết syntax.
- Cần đăng ký tên hàm và kiểu kết quả để dùng trong expression phức tạp.
- Cần đăng ký cách render đặc biệt nếu cú pháp SQL không phải `name(arg1, arg2, ...)`.
- Chỉ hỗ trợ một số vị trí sử dụng `FUNCTION`, tùy khả năng type resolution.

### 15.1. Vì sao register function không phải JPA portable API chung?

JPA chuẩn cung cấp cú pháp gọi hàm và Criteria API, **không đặt ra một API thống nhất cho mọi provider để đăng ký mọi SQL function với return type, argument validator và custom rendering template**.

Ví dụ, các phiên bản Hibernate hiện đại có cơ chế đăng ký function descriptor ở hạ tầng query engine/dialect, nhưng tên class và API callback có thể thay đổi giữa phiên bản Hibernate. EclipseLink có các extension khác.

Điều đó nghĩa là:

- Cấu hình function registry gắn chặt với **provider và phiên bản**.
- Chuyển provider có thể phải viết lại phần đăng ký.
- Đăng ký hàm không làm database bỗng có routine chưa được cài đặt.
- Không nên xem các annotation/API extension như một phần của JPA chuẩn nếu chúng không thuộc `jakarta.persistence`.

### 15.2. Định hướng thiết kế adapter

Thay vì rải function name khắp nghiệp vụ:

~~~text
Application service
        |
        v
CustomerSearchRepository (interface)
        |
        +--- PostgreSqlCustomerSearchRepository
        |           |
        |           +-- FUNCTION('unaccent', ...)
        |
        +--- PortableCustomerSearchRepository
                    |
                    +-- LOWER(...)
                        hoặc normalized search column
~~~

Cách này làm rõ **ranh giới phụ thuộc DB**. Khi đổi database, ta có một lớp cần thay thế/kiểm thử thay vì tìm chuỗi `FUNCTION('unaccent'` ở mọi service.

Nếu chỉ hỗ trợ một database duy nhất và đội ngũ chấp nhận phụ thuộc đó, việc dùng `FUNCTION` trực tiếp vẫn có thể hợp lý. Điểm quan trọng là **ghi nhận dependency như một quyết định thiết kế**, không coi nó là ngẫu nhiên portable.

## 16. Một số hàm JPQL chuẩn nên biết trước khi chọn FUNCTION

### 16.1. Xử lý chuỗi

JPQL thường hỗ trợ các hàm chuẩn:

~~~jpql
LOWER(c.fullName)
UPPER(c.fullName)
LENGTH(c.fullName)
TRIM(c.fullName)
SUBSTRING(c.fullName, 1, 3)
CONCAT(c.fullName, ' - customer')
LOCATE('a', c.fullName)
~~~

Chúng sử dụng **thuộc tính entity** và tham số JPQL thông thường.

Ví dụ:

~~~java
List<Customer> rows = em.createQuery(
    """
    SELECT c
    FROM Customer c
    WHERE LENGTH(TRIM(c.fullName)) >= :minLength
    ORDER BY LOWER(c.fullName), c.id
    """,
    Customer.class
)
.setParameter("minLength", 3)
.getResultList();
~~~

Trước khi chuyển sang một SQL function đặc thù như `ltrim`, `rtrim` hay `char_length`, hãy xem biểu thức chuẩn `TRIM`/`LENGTH` đã giải quyết yêu cầu hay chưa.

### 16.2. Số học

Một số hàm/biểu thức chuẩn:

~~~jpql
ABS(o.totalAmount)
SQRT(:someNumber)
MOD(:someInteger, 3)
~~~

Tập hàm JPQL chuẩn được mở rộng theo các phiên bản Jakarta Persistence. Khi dự án dùng phiên bản mới, có thể có thêm hàm toán học và ngày giờ chuẩn mà bản cũ chưa có. Vì vậy cần biết **đúng phiên bản Jakarta Persistence** trước khi khẳng định một function chỉ có thể gọi bằng `FUNCTION`.

### 16.3. Ngày giờ

JPQL có các biểu thức như:

~~~jpql
CURRENT_DATE
CURRENT_TIME
CURRENT_TIMESTAMP
~~~

Chúng mang semantics ngày giờ theo đặc tả và database, nhưng không phải giải pháp cho mọi phép gom ngày/tháng, chuyển múi giờ hoặc trừ khoảng thời gian.

Nếu chỉ lọc từ một thời điểm đến trước thời điểm khác, so sánh tham số Java thường rõ hơn:

~~~jpql
WHERE o.createdAt >= :fromTime AND o.createdAt < :toTime
~~~

**Đừng thay thế phép so sánh đơn giản bằng hàm trên cột khi không cần thiết**, vì có thể làm mất cơ hội tận dụng index.

## 17. SARGability và hiệu năng khi bọc cột bằng hàm

Một truy vấn thông thường:

~~~sql
SELECT *
FROM customers
WHERE email = 'user@example.com';
~~~

có thể tận dụng B-tree index trên `email` nếu schema và query plan phù hợp.

Nhưng:

~~~sql
SELECT *
FROM customers
WHERE LOWER(email) = 'user@example.com';
~~~

hoặc:

~~~sql
SELECT *
FROM customers
WHERE unaccent(full_name) = 'nguyen van a';
~~~

có thể khiến database phải tính hàm trên nhiều bản ghi, và **index thông thường trên cột gốc không nhất thiết hữu ích** cho biểu thức đó.

Các chiến lược cải thiện:

1. **Expression/function-based index** nếu database hỗ trợ và hàm đáp ứng điều kiện chỉ mục.
2. **Generated/computed column** chứa giá trị chuẩn hóa, kèm index.
3. **Cột chuẩn hóa do ứng dụng cập nhật** theo quy tắc nhất quán, có index.
4. **Full-text index/search extension** phù hợp cho tìm kiếm nhiều từ.
5. **Truy vấn range** thay vì bọc cột thời gian bằng hàm khi chỉ lọc trong khoảng.
6. **Đo EXPLAIN/ANALYZE** trên database thật thay vì suy luận từ cú pháp JPQL.

### 17.1. Chú ý expression index với unaccent của PostgreSQL

Không nên tự mặc định có thể tạo:

~~~sql
CREATE INDEX ... ON customers (unaccent(full_name));
~~~

bởi PostgreSQL có những yêu cầu về **tính bất biến (immutability)** đối với expression index, trong khi việc xử lý `unaccent` phụ thuộc dictionary/extension và có thể không đáp ứng yêu cầu này theo cách mặc định.

Nếu chọn index chuẩn hóa tên, cần nghiên cứu thiết kế **stored normalized value**, generated column hay wrapper function theo ràng buộc cụ thể của PostgreSQL, cùng chiến lược đồng bộ dictionary. Không tự gắn nhãn `IMMUTABLE` cho một hàm có semantics thay đổi chỉ để ép database cho tạo index, vì điều đó có thể khiến chỉ mục sai dữ liệu.

### 17.2. Query plan thực tế quan trọng hơn việc viết “một câu JPQL đẹp”

Một câu JPQL ngắn:

~~~jpql
WHERE FUNCTION('unaccent', c.fullName) LIKE :pattern
~~~

có thể chậm khi:

- Bảng chứa hàng triệu customer.
- Pattern bắt đầu bằng `%`.
- Không có index phù hợp.
- Hàm được tính trên từng dòng.
- Database phải sort thêm theo một expression khác.
- Kết quả trả nhiều entity kèm các lazy association.

Nếu yêu cầu search quan trọng, cần mô hình chỉ mục và kiểm thử tải tương xứng. `FUNCTION` chỉ mở khả năng gọi hàm, **không phải cơ chế tối ưu SQL tự động**.

## 18. JSON, array và các kiểu dữ liệu chuyên biệt

Nhiều database có hệ hàm JSON khác nhau. PostgreSQL có các hàm và toán tử JSONB, MySQL có nhóm JSON functions riêng. Khi gọi từ JPQL, cần xem xét cả mapping của trường JSON.

Ví dụ ý tưởng với PostgreSQL:

~~~jpql
SELECT p
FROM Product p
WHERE FUNCTION(
    'jsonb_extract_path_text',
    p.attributesJson,
    'color'
) = :color
~~~

Đây là **ví dụ định hướng**, giả định `Product.attributesJson` được ánh xạ đúng vào kiểu JSONB của PostgreSQL bằng mapping/provider hỗ trợ. Nếu chỉ khai báo `String` với cột SQL là `jsonb` nhưng driver/provider gửi tham số dạng `varchar` không phù hợp, truy vấn có thể báo lỗi kiểu. Ngoài ra, provider phải nhận diện kiểu trả về của `jsonb_extract_path_text`.

Không đưa ví dụ này vào ứng dụng rồi kỳ vọng nó chạy được trên MySQL chỉ vì JPQL có từ khóa `FUNCTION`.

Khi thao tác nhiều với JSON/spatial/array:

- Xem xét native SQL nếu biểu thức chứa toán tử DB đặc thù và cú pháp phức tạp.
- Dùng cơ chế mapping JSON hoặc type system của provider khi rõ ràng.
- Thiết kế repository adapter chịu trách nhiệm chuyển result.
- Định nghĩa integration tests cho schema/mapping thật.
- Đánh giá JSON index hoặc functional index phù hợp với DB mục tiêu.

## 19. Khi nào chọn FUNCTION, Criteria API hoặc native SQL?

| Nhu cầu | Hướng tiếp cận |
| --- | --- |
| Hàm chuẩn JPQL đủ diễn đạt | Dùng trực tiếp `LOWER`, `TRIM`, `ABS`... |
| Chỉ cần một SQL function đơn giản trong truy vấn entity | `FUNCTION('name', ...)` |
| Điều kiện lọc thay đổi động và có một hàm SQL cần dùng | `CriteriaBuilder.function(...)` |
| SQL gồm CTE, window function, toán tử đặc thù, cú pháp không biểu diễn tốt bằng JPQL | Native SQL |
| Cần gọi stored procedure | `StoredProcedureQuery` |
| Cần tìm kiếm phức tạp/khối lượng lớn | Search abstraction, full-text hoặc search engine phù hợp |
| Ứng dụng phải chạy trên nhiều database | Ưu tiên JPQL chuẩn hoặc tách implementation theo dialect |
| Cần mapping function result khó đoán | Đăng ký type/function theo provider hoặc dùng native mapping rõ ràng |

Một sơ đồ lựa chọn:

~~~text
                 Cần xử lý đặc biệt trong query
                               |
                               v
                    JPQL chuẩn có đủ không?
                         /            \
                       Có              Không
                        |                |
                        v                v
                   Dùng hàm        Database có hàm
                   JPQL chuẩn      phù hợp không?
                                       /     \
                                     Có      Không
                                      |        |
                                      v        v
                           Provider hỗ trợ?  Thiết kế lại:
                              /       \       Java/search/
                            Có        Không   schema/function
                             |          |
                             v          v
                    FUNCTION hoặc    Provider registration
                    CriteriaBuilder  hoặc native SQL
                             |
                             v
                     Xác định type,
                     semantics, index,
                     kiểm thử đa môi trường
~~~

**Không dùng `FUNCTION` như biện pháp dự phòng đầu tiên cho tất cả những gì JPQL chưa quen thuộc.** Một cấu trúc portable có thể đơn giản hơn và dễ tối ưu hơn.

## 20. Tổ chức repository để hạn chế phụ thuộc database

Giả sử ứng dụng chủ yếu chạy PostgreSQL nhưng muốn không rải `unaccent` ra khắp service.

Định nghĩa abstraction nghiệp vụ:

~~~java
package com.example.shop.repository;

import com.example.shop.domain.Customer;
import java.util.List;

public interface CustomerNameSearch {
    List<Customer> findByNameContains(String text);
}
~~~

Triển khai PostgreSQL:

~~~java
package com.example.shop.repository;

import com.example.shop.domain.Customer;
import jakarta.persistence.EntityManager;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public final class PostgresCustomerNameSearch
        implements CustomerNameSearch {

    private final EntityManager em;

    public PostgresCustomerNameSearch(EntityManager em) {
        this.em = em;
    }

    @Override
    public List<Customer> findByNameContains(String text) {
        Objects.requireNonNull(text, "text");

        String normalizedPattern =
            "%" + escapeLike(text.toLowerCase(Locale.ROOT)) + "%";

        return em.createQuery(
            """
            SELECT c
            FROM Customer c
            WHERE LOWER(FUNCTION('unaccent', c.fullName))
                  LIKE :pattern ESCAPE '!'
            ORDER BY c.id
            """,
            Customer.class
        )
        .setParameter("pattern", normalizedPattern)
        .getResultList();
    }

    private static String escapeLike(String text) {
        return text
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
    }
}
~~~

**Giới hạn ví dụ:** hàm trên cột được bỏ dấu nhưng input mới chuyển chữ thường, **chưa áp dụng cùng cơ chế bỏ dấu cho input có dấu**. Nếu client nhập `Nguyễn` thay vì `Nguyen`, kết quả có thể khác kỳ vọng. Đối với chức năng accent-insensitive hoàn chỉnh, cần chuẩn hóa cả input theo cùng policy (ví dụ gọi `unaccent` trên parameter trong DB hoặc dùng cột/normalizer tương thích).

Một biến thể database-side đồng bộ hai phía:

~~~jpql
SELECT c
FROM Customer c
WHERE LOWER(FUNCTION('unaccent', c.fullName))
      LIKE LOWER(FUNCTION('unaccent', :pattern)) ESCAPE '!'
ORDER BY c.id
~~~

Nếu provider xử lý kiểu của `unaccent` đúng, biến thể này dùng cùng quy tắc bỏ dấu cho field và parameter; vẫn cần lưu ý wildcard và collation.

### 20.1. Triển khai portable hơn với cột chuẩn hóa

Thay vì gọi hàm `unaccent` tại query time, có thể thêm một cột:

~~~sql
-- Minh họa ý tưởng, DDL/migration chi tiết tùy DB:
ALTER TABLE customers
ADD COLUMN normalized_full_name VARCHAR(160);

CREATE INDEX idx_customers_normalized_name
    ON customers (normalized_full_name);
~~~

Ứng dụng cập nhật `normalized_full_name` khi tên thay đổi, theo một thuật toán normalization được định nghĩa rõ. JPQL:

~~~jpql
SELECT c
FROM Customer c
WHERE c.normalizedFullName LIKE :pattern
ORDER BY c.id
~~~

Điểm được lợi:

- Query không phụ thuộc `FUNCTION('unaccent', ...)`.
- Có thể dùng index thông thường nếu kiểu pattern và database optimizer phù hợp.
- Dễ tạo API có ngữ nghĩa nhất quán giữa nhiều môi trường.

Đánh đổi:

- Phải duy trì đồng bộ giữa tên gốc và tên chuẩn hóa.
- Phải thống nhất Unicode normalization và case folding.
- Phải migration dữ liệu hiện có.
- `LIKE '%term%'` vẫn có thể không tận dụng B-tree index tốt; cần xem xét trigram/full-text index nếu search contains quan trọng.

Khi quyết định giữa hai cách, tính portable **không chỉ là di chuyển query** mà còn là dữ liệu phải giữ một **policy chuẩn hóa nhất quán**.

## 21. Thiết kế chiến lược đa database

Giả sử sản phẩm phải hỗ trợ PostgreSQL và MySQL. Đừng để service viết:

~~~java
if (databaseName.equals("PostgreSQL")) {
    // query A
} else {
    // query B
}
~~~

ở nhiều nơi khác nhau. Tốt hơn có một contract rõ:

~~~text
OrderStatistics
    |
    +-- PostgreSqlOrderStatistics
    |      date_trunc(...)
    |
    +-- MySqlOrderStatistics
    |      date_format(...) hoặc biểu thức tương ứng
    |
    +-- PortableOrderStatistics
           query theo khoảng/aggregation ở Java khi phù hợp
~~~

Mỗi implementation cần trả về **cùng một DTO hợp đồng**, ví dụ:

~~~java
package com.example.shop.dto;

import java.time.LocalDate;

public record DailyOrderCount(
    LocalDate day,
    long count
) {
}
~~~

Nếu PostgreSQL query trả timestamp và MySQL query trả chuỗi, **đừng để DTO nhận các kiểu bất định rồi bắt caller tự đoán**. Repository adapter chịu trách nhiệm chuyển giá trị về `LocalDate` có semantics rõ, cùng quy tắc timezone.

### 21.1. Phân lớp portable vs provider-specific

Có thể phân vùng code:

| Phần | Có nên phụ thuộc function SQL? |
| --- | --- |
| Service nghiệp vụ | Hạn chế; gọi interface repository |
| Repository interface | Không cần biết tên hàm DB |
| Repository implementation cho PostgreSQL | Có thể biết `unaccent`, `date_trunc` |
| Repository implementation cho MySQL | Có thể biết `DATE_FORMAT`, SQL riêng |
| DTO/API contract | Cố gắng không để lộ `PGobject` hay kiểu JDBC vendor-specific |
| Schema migration | Có thể phải dùng DDL/extension riêng theo DB |
| Integration tests | Bắt buộc chạy với database mục tiêu khi hành vi quan trọng |

Nếu dự án **chỉ hỗ trợ một database**, thiết kế có thể đơn giản hơn. Tuy nhiên vẫn nên cô lập phụ thuộc để nâng cấp database/provider trong tương lai không đòi hỏi tìm và sửa toàn bộ service.

## 22. Kiểm thử FUNCTION một cách thực tế

Với query chứa hàm database-specific, unit test mock repository không đủ để xác nhận tính đúng đắn. Cần **integration test** với DB và provider phù hợp.

### 22.1. Các lớp kiểm thử

1. **Unit test**: service có chọn đúng repository/search mode và chuyển tham số đúng không?
2. **Query integration test**: provider có parse JPQL, suy luận type và render hàm không?
3. **Database integration test**: database có function/extension, signature và permission đúng không?
4. **Semantic test**: input Unicode/NULL/timezone/rounding có trả kết quả đúng không?
5. **Performance test**: query plan và index có đáp ứng dữ liệu thực tế không?
6. **Cross-database test** (nếu yêu cầu): cùng contract DTO đạt kết quả tương đương trên các DB được hỗ trợ không?

### 22.2. Ma trận kiểm thử mẫu

| Trường hợp | Dữ liệu | Điều cần xác nhận |
| --- | --- | --- |
| Bỏ dấu | `Nguyễn`, tìm `nguyen` | Kết quả theo policy normalization |
| Chữ hoa | `NgUyỄn`, tìm `NGUYEN` | Quy tắc case-insensitive |
| Trùng sau chuẩn hóa | `Nguyễn` và `Nguyen` | Thứ tự phụ ổn định bằng ID |
| NULL | Một thuộc tính nullable | Hàm và filter xử lý đúng `NULL` |
| Chuỗi đặc biệt | `%`, `_`, dấu nháy, ký tự Unicode | Parameter binding và LIKE escaping |
| Không có kết quả | Tên không tồn tại | Trả list rỗng, không lỗi |
| Ngày ranh giới | Gần 00:00:00 | Không mất/nhân đôi record |
| Timestamp khác timezone | Instant trước/sau mốc ngày địa phương | Nhóm đúng ngày nghiệp vụ |
| Kiểu kết quả | `date_trunc`, `DATE_FORMAT` | Mapping DTO đúng kiểu đã cam kết |
| Database không có extension | PostgreSQL chưa cài `unaccent` | Lỗi được phát hiện và hướng triển khai rõ |
| Provider khác | Hibernate/EclipseLink nếu hỗ trợ | Parse và return type tương thích hoặc lỗi được ghi nhận |
| Bảng lớn | Nhiều customer/order | Query plan, index, latency phù hợp |

### 22.3. Vì sao H2 unit/integration test chưa đủ?

H2 thường được dùng cho kiểm thử nhẹ, có thể hỗ trợ một số hàm tương tự database production hoặc cung cấp compatibility modes. Nhưng **không phải bản sao chính xác của PostgreSQL/MySQL**, đặc biệt với extension, JSONB, collation, time zone và type resolution.

Ví dụ: query dùng `date_trunc` chạy trên H2 không chứng minh `unaccent` của PostgreSQL đã được cấu hình, hay việc map `LocalDateTime` giống nhau trên hai driver.

Đối với phụ thuộc quan trọng, nên dùng PostgreSQL/MySQL thật trong môi trường test (ví dụ container integration test) cùng phiên bản sát production.

### 22.4. Ví dụ kiểm thử JPA về bỏ dấu

Pseudocode tích hợp (giả định dữ liệu và PostgreSQL extension đã được thiết lập):

~~~java
@Test
void findsNameWithoutAccents() {
    // Arrange:
    // persist Customer("Nguyễn Văn A", ...)
    // commit để DB chứa dữ liệu.

    List<Customer> matches = em.createQuery(
        """
        SELECT c
        FROM Customer c
        WHERE LOWER(FUNCTION('unaccent', c.fullName))
              = LOWER(FUNCTION('unaccent', :name))
        """,
        Customer.class
    )
    .setParameter("name", "Nguyen Van A")
    .getResultList();

    assertThat(matches)
        .extracting(Customer::getFullName)
        .contains("Nguyễn Văn A");
}
~~~

Đoạn này là **minh họa JUnit 5 + AssertJ** (cần import/phụ thuộc tương ứng), không phải một bài test đã được chạy. Trên provider không hỗ trợ return-type inference của `unaccent`, cần đăng ký function hoặc dùng mapping/query khác trước khi chạy.

## 23. Chẩn đoán lỗi thường gặp

### 23.1. Lỗi “function does not exist”

Ví dụ:

~~~text
ERROR: function unaccent(character varying) does not exist
~~~

Nguyên nhân khả dĩ:

- PostgreSQL chưa cài extension `unaccent`.
- Hàm được cài ở schema không nằm trong `search_path` phù hợp.
- Tên hàm/signature đối số khác.
- Column mapping tạo kiểu SQL không tương thích.
- Ứng dụng đang kết nối một database khác với dự kiến.

Cách xử lý: kiểm tra schema/extension, signature hàm và môi trường thật. Không sửa bằng cách thêm `FUNCTION` nhiều lần hoặc đổi thứ tự `persist`.

### 23.2. Lỗi provider không suy luận được kiểu hàm

Ví dụ lỗi query parse hoặc semantic validation khi dùng:

~~~jpql
LOWER(FUNCTION('unaccent', c.fullName))
~~~

Nguyên nhân có thể là provider không nhận biết `unaccent` trả một kiểu chuỗi. Cân nhắc:

- Register function với return type phù hợp theo API provider/version.
- Dùng SQL native được mapping rõ.
- Tránh lồng hàm ở JPQL nếu DB abstraction chưa hỗ trợ.
- Đổi chiến lược search sang cột normalized value.

### 23.3. ClassCastException hoặc DTO constructor mismatch

Ví dụ `FUNCTION('date_trunc', ...)` trả một kiểu không trùng với constructor DTO. Hãy xem:

- SQL function return type thật.
- JDBC type từ driver.
- JPA provider xử lý result conversion thế nào.
- Kiểu khai báo ở DTO/Criteria expression.
- Khả năng cần result set mapping/casting/adapter.

Không sửa bằng ép kiểu Java tùy tiện nếu đối tượng thực tế khác.

### 23.4. JPQL chạy nhưng kết quả sai dấu/case

Nguyên nhân có thể là:

- Chỉ `LOWER` mà chưa bỏ dấu.
- Bỏ dấu cột nhưng không bỏ dấu input.
- Collation khác giữa test và production.
- Unicode normalization không nhất quán.
- Pattern `LIKE` chứa wildcard không được escape.

Cần xác định policy tìm kiếm và kiểm thử với dữ liệu tiếng Việt thực tế.

### 23.5. Query chậm khi dùng FUNCTION trên cột

Nguyên nhân thường gặp:

- Index cột gốc không dùng hiệu quả với expression.
- Pattern có wildcard đầu.
- Hàm được tính cho quá nhiều dòng.
- Sort theo expression không có kế hoạch index phù hợp.

Dùng `EXPLAIN` hoặc `EXPLAIN ANALYZE` trên DB mục tiêu, xem cardinality và index; không suy đoán từ log JPQL.

### 23.6. “Chạy trên PostgreSQL nhưng lỗi trên MySQL”

Đó có thể là **giới hạn đã biết của tính khả chuyển** chứ không phải bug của `EntityManager`. `FUNCTION` không ánh xạ tự động tên `date_trunc` sang `DATE_FORMAT` hay một biểu thức tương đương của database khác.

Nếu multi-DB là yêu cầu, phải có adapter hoặc query portable từ thiết kế ban đầu.

## 24. Những ngộ nhận cần tránh

| Nhận định | Thực tế |
| --- | --- |
| “FUNCTION là JPQL chuẩn nên mọi hàm qua nó đều portable.” | Chỉ cú pháp gọi hàm là chuẩn; hàm thực phụ thuộc DB/provider. |
| “Hàm tồn tại trên DB thì provider chắc chắn hiểu kiểu.” | Provider có thể cần registration/return-type metadata. |
| “CriteriaBuilder.function với String.class ép DB trả String.” | `String.class` là kỳ vọng kiểu ở Criteria; không phải SQL CAST. |
| “LOWER đủ để tìm tên tiếng Việt không dấu.” | LOWER xử lý case, không tự bỏ dấu. |
| “Tên hàm có thể truyền qua setParameter.” | Parameter đại diện giá trị, không phải tên function/cú pháp SQL. |
| “Dùng parameter là wildcard LIKE được xử lý tự động.” | Binding an toàn cho cú pháp, nhưng `%`/`_` vẫn là wildcard nếu không escape. |
| “date_trunc của PostgreSQL và date_format của MySQL có cùng result type.” | Thường khác: timestamp vs string theo signature ví dụ. |
| “Có @NamedQuery thì SQL function được kiểm tra và portable.” | Named query tập trung metadata, không tạo tính portable cho hàm SQL. |
| “FUNCTION có thể thay mọi native SQL.” | Có cú pháp SQL/kiểu đặc thù khó hoặc không biểu diễn tốt bằng JPQL. |
| “FUNCTION luôn nhanh vì DB tính toán.” | Function trên cột có thể cản trở index và tăng CPU. |
| “Bọc cột bằng date_trunc để lọc một ngày luôn tốt hơn range.” | Range query thường rõ hơn và có cơ hội tận dụng index tốt hơn. |
| “Có thể dùng H2 làm bằng chứng PostgreSQL extension hoạt động.” | H2 không thay thế kiểm thử trên DB production-compatible. |
| “Đổi provider không ảnh hưởng FUNCTION.” | Type resolution, registration và rendering có thể khác. |
| “Dùng FUNCTION trong SELECT new chắc chắn tự cast đúng DTO.” | Return type và constructor phải tương thích thực sự. |
| “Một SQL function có side effect có thể gọi từ SELECT như service method.” | SQL execution/optimizer không cung cấp hợp đồng side effect phù hợp. |

## 25. Bài tập thực hành có lời giải

### Bài 1. Có cần FUNCTION để dùng LOWER?

Cho JPQL:

~~~jpql
SELECT c FROM Customer c WHERE LOWER(c.email) = LOWER(:email)
~~~

**Hỏi:** Có nên chuyển sang `FUNCTION('lower', ...)` để query portable hơn?

**Giải thích:** Không. `LOWER` đã là hàm JPQL chuẩn. Dùng dạng chuẩn thường rõ nghĩa và portable hơn. `FUNCTION` không tạo thêm lợi ích nếu không có yêu cầu SQL đặc thù.

### Bài 2. Tìm tên có dấu

Dữ liệu có `Nguyễn Văn A`. Người dùng nhập `Nguyen Van A`.

**Hỏi:** `LOWER(c.fullName)` đã đủ chưa?

**Giải thích:** Chưa, vì lowercase không tự xóa dấu. Nếu ứng dụng dùng PostgreSQL và đã cài extension `unaccent`, có thể cân nhắc `FUNCTION('unaccent', ...)`, rồi kiểm tra case/collation và normalizing cả input.

### Bài 3. Parameter cho tên hàm

~~~jpql
SELECT FUNCTION(:name, c.fullName) FROM Customer c
~~~

**Hỏi:** Có portable không?

**Giải thích:** Không nên dùng. Tên hàm trong cú pháp `FUNCTION` là literal xác định trong query, còn `setParameter` dùng để truyền giá trị dữ liệu. Nếu cần chọn giữa một số hàm, dùng whitelist/query riêng.

### Bài 4. FUNCTION trong Criteria API

Viết biểu thức gọi `unaccent` với kết quả mong muốn là String.

**Đáp án:**

~~~java
Expression<String> normalized =
    cb.function(
        "unaccent",
        String.class,
        root.get("fullName")
    );
~~~

Lưu ý: `String.class` không làm mọi provider tự biết hàm; cần DB/registration hỗ trợ.

### Bài 5. Chuyển truy vấn date_trunc sang MySQL

~~~jpql
FUNCTION('date_trunc', 'month', o.createdAt)
~~~

**Hỏi:** Có chạy nguyên xi trên MySQL không?

**Giải thích:** Không nên kỳ vọng. MySQL thường dùng các hàm format/extract khác; cần thay query và xác định result type/semantics, hoặc thiết kế query portable hơn nếu mục tiêu chỉ là lọc một khoảng.

### Bài 6. Lọc một ngày mà không gọi hàm DB

Yêu cầu tìm đơn ngày 15/11/2026, field `createdAt` là `LocalDateTime` lưu cùng timezone nghiệp vụ.

**Đáp án:**

~~~java
LocalDate day = LocalDate.of(2026, 11, 15);
LocalDateTime from = day.atStartOfDay();
LocalDateTime to = day.plusDays(1).atStartOfDay();
~~~

~~~jpql
SELECT o FROM PurchaseOrder o
WHERE o.createdAt >= :from
  AND o.createdAt < :to
~~~

Hướng này giảm phụ thuộc function DB và có thể tận dụng index `created_at` tốt hơn.

### Bài 7. Vì sao native query đôi khi cần thiết?

Query yêu cầu CTE phức tạp, toán tử JSONB đặc biệt và nhiều phép xử lý kết quả riêng của PostgreSQL.

**Giải thích:** `FUNCTION` thích hợp khi đưa một hàm SQL vào biểu thức JPQL; nó không diễn đạt tùy ý toàn bộ ngôn ngữ SQL của vendor. Native SQL có thể rõ ràng và đầy đủ hơn, nhưng đánh đổi bằng phụ thuộc database và mapping kết quả.

### Bài 8. Vì sao LEFT/RIGHT collation ảnh hưởng kết quả?

Một query dùng `FUNCTION('unaccent', name)` nhưng sort không giống giữa hai database.

**Giải thích:** Bỏ dấu chỉ là một phép biến đổi text. Collation, locale, quy tắc so sánh và Unicode vẫn có thể khác; cần định nghĩa chính xác yêu cầu nghiệp vụ và so sánh kết quả trên từng DB.

### Bài 9. DTO constructor bị lỗi khi dùng date_trunc

Record nhận `LocalDate`, nhưng function trả timestamp.

**Giải thích:** Sai kiểu kết quả. Có thể map về timestamp rồi chuyển thành `LocalDate` ở repository adapter, đăng ký/conversion phù hợp hoặc viết query native với mapping rõ ràng. Không giả định provider tự chuyển mọi result type.

### Bài 10. Hàm trong WHERE làm query chậm

~~~jpql
WHERE FUNCTION('unaccent', c.fullName) LIKE :pattern
~~~

Bảng có hàng triệu khách hàng. Truy vấn chậm.

**Giải thích:** Hàm trên cột và pattern dạng `%term%` có thể làm index thường không hiệu quả. Cần xem query plan, cân nhắc indexed normalized column, trigram/full-text search hoặc kiến trúc search riêng.

### Bài 11. Provider không nhận diện unaccent

PostgreSQL đã cài extension nhưng JPQL chứa:

~~~jpql
LOWER(FUNCTION('unaccent', c.fullName))
~~~

bị báo lỗi kiểu.

**Giải thích:** Database hiểu hàm nhưng provider có thể không suy luận được kiểu trả về để đưa vào `LOWER`. Cần provider-specific registration, thay query/mapping hoặc thiết kế search khác.

### Bài 12. GROUP BY theo ngày và time zone

Ứng dụng lưu timestamp UTC; báo cáo yêu cầu ngày theo `Asia/Ho_Chi_Minh`.

**Giải thích:** Phải chuyển instant theo zone phù hợp trước khi xác định bucket ngày hoặc sử dụng biểu thức database timezone đúng. Chỉ gọi `date_trunc('day', timestamp)` mà không xét timezone có thể phân nhóm sai ở ranh giới ngày.

### Bài 13. Sử dụng NamedQuery có đảm bảo đa DB?

~~~java
@NamedQuery(
    name = "Customer.search",
    query =
        "SELECT c FROM Customer c " +
        "WHERE FUNCTION('unaccent', c.fullName) = :name"
)
~~~

**Giải thích:** Không. Named query chỉ giúp khai báo tập trung và tái sử dụng; phụ thuộc PostgreSQL/unaccent vẫn nguyên vẹn.

### Bài 14. Kiểm thử trên H2

Query `FUNCTION('date_trunc', ...)` hoạt động trên H2.

**Hỏi:** Đã đủ chứng minh tương thích với PostgreSQL/MySQL production chưa?

**Giải thích:** Chưa. Cần integration test trên database/proxy driver gần môi trường thật, xác nhận signature, mapping type, timezone, index và những extension liên quan.

### Bài 15. Dùng hàm từ người dùng

Một endpoint cho phép user nhập tên SQL function để áp dụng lên cột `email`.

**Giải thích:** Không nên ghép tên hàm tùy ý vào query. Chọn tập hàm đã được phép, giới hạn use case ở service, binding dữ liệu bằng parameter và kiểm soát quyền truy cập. Parameterization không phải cơ chế bảo vệ khi cấu trúc function name bị nối trực tiếp từ input.

## 26. Checklist thiết kế trước khi dùng FUNCTION

Khi quyết định đưa một custom database function vào JPQL, hãy tự hỏi:

1. **Có hàm JPQL chuẩn tương đương không?** Ưu tiên giải pháp chuẩn nếu đáp ứng đúng nghĩa.
2. **Hàm SQL tồn tại trên DB nào và phiên bản nào?** Có extension/migration bắt buộc không?
3. **Signature chính xác là gì?** Bao nhiêu đối số, nhận kiểu gì, có overload không?
4. **Kiểu trả về là gì?** Provider có suy luận/mapping vào Java type đúng không?
5. **NULL, locale, Unicode, timezone và precision** được xử lý ra sao?
6. **Provider/dialect hiện tại có hỗ trợ không?** Có cần function registration riêng?
7. **FUNCTION được đặt ở đâu?** SELECT, WHERE, ORDER BY, GROUP BY, HAVING?
8. **Có giải pháp JPQL chuẩn/range query/column chuẩn hóa** dễ portable hơn không?
9. **Truy vấn có tận dụng index không?** Có cần expression index hoặc cột chuẩn hóa?
10. **Nếu chuyển database thì phần nào phải viết lại?** Nên có repository adapter không?
11. **Có kiểm thử tích hợp trên DB thật không?** H2 có đủ cho function đang dùng không?
12. **Có kiểm soát input không?** Không cho user đặt tên hàm tùy ý; binding dữ liệu.
13. **Kết quả có đưa trực tiếp vào DTO không?** Đảm bảo constructor/return type đúng.
14. **Hàm có side effect không?** Tránh dùng hàm mang side effect trong SELECT nghiệp vụ thông thường.

## 27. Kết luận

`FUNCTION` là một **cầu nối có chủ đích** từ JPQL sang khả năng của database:

~~~text
Entity / JPQL attribute
          |
          v
FUNCTION('sql_function_name', arguments)
          |
          v
JPA provider + SQL dialect
          |
          v
Database function
          |
          v
JDBC type / Java result
~~~

Để sử dụng đúng, cần nhớ:

- **Cú pháp `FUNCTION` là chuẩn JPA, nhưng hàm được gọi không mặc nhiên portable.**
- Với truy vấn động, `CriteriaBuilder.function(name, returnType, args...)` là API tương ứng; `returnType` không phải SQL CAST.
- Hàm chuẩn JPQL nên được ưu tiên khi có thể diễn đạt yêu cầu.
- Hàm đặc thù cần xác định rõ database, kiểu trả về, extension, provider registration và ngữ nghĩa.
- Việc bọc cột bằng function có thể làm truy vấn khó tận dụng index; range query hoặc normalized column đôi khi phù hợp hơn.
- Nếu ứng dụng hỗ trợ nhiều database, nên **cô lập hàm đặc thù trong repository adapter** và dùng DTO có hợp đồng kiểu dữ liệu thống nhất.
- Integration test với database mục tiêu là cần thiết để xác nhận cả cú pháp, type mapping, semantics và hiệu năng.

**Giá trị thực sự của `FUNCTION` không nằm ở việc biến JPQL thành SQL tùy ý, mà ở khả năng mở rộng JPQL khi một tính năng database thực sự cần thiết — đồng thời chủ động kiểm soát giới hạn tính khả chuyển do tính năng đó mang lại.**
