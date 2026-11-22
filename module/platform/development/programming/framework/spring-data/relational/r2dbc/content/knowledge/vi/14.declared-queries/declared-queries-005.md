# Ánh xạ tên cột, bí danh và thuộc tính kết quả

Khi dùng Spring Data Relational R2DBC, câu SQL trả về một tập hàng với các cột có tên hoặc bí danh. Spring Data cần chuyển từng giá trị trong hàng thành thuộc tính của entity hoặc DTO Java. Quá trình đó phụ thuộc vào mapping metadata, naming strategy và nhãn cột mà database trả về.

Tên cột trong database có thể khác tên property Java. Ví dụ, entity dùng `customerName`, schema dùng `customer_name`, còn một truy vấn join có thể cần đặt bí danh `customer_name` để tránh trùng tên với cột của bảng khác. Nếu tên cột hoặc bí danh không khớp với mapping mà Spring Data mong đợi, thuộc tính có thể không được gán đúng hoặc quá trình ánh xạ có thể thất bại tùy kiểu entity và constructor.

Bài học này trình bày cách Spring Data R2DBC ánh xạ kết quả truy vấn, sự khác nhau giữa tên cột và bí danh, cách dùng `@Column`, cách đặt alias cho entity và projection, cách xử lý biểu thức SQL, join, giá trị null và cách ánh xạ tường minh bằng `DatabaseClient`.

## 1. Từ kết quả SQL đến thuộc tính Java

Một truy vấn SQL trả về một result set. Mỗi hàng có các giá trị; mỗi cột có một nhãn mà driver R2DBC cung cấp qua metadata. Nhãn đó thường là tên cột được chọn hoặc bí danh khai báo bằng `AS`.

Ví dụ schema:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(200)
);
~~~

Entity Java:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("customer_name")
    private String name;

    @Column("email_address")
    private String email;
}
~~~

Khi đọc hàng từ bảng `customer`, Spring Data dùng mapping metadata của entity để xác định cột nào tương ứng với property nào:

| Property Java | Tên cột được mapping |
|---|---|
| `id` | `id` |
| `name` | `customer_name` |
| `email` | `email_address` |

Ví dụ truy vấn:

~~~sql
SELECT id, customer_name, email_address
FROM customer
WHERE id = :id;
~~~

Các nhãn cột trong kết quả khớp với mapping của entity. Spring Data có thể chuyển hàng thành một `Customer` mà không cần tự viết mapper cho từng cột.

Luồng tổng quát:

~~~text
SQL query
   |
   v
Database result set
   |
   v
R2DBC Row + RowMetadata
   |
   v
Spring Data mapping metadata
   |
   v
Entity / DTO
~~~

Đối với repository method, Spring Data thường thực hiện bước chuyển đổi này dựa trên kiểu trả về. Khi dùng `DatabaseClient`, ứng dụng có thể yêu cầu Spring mapping hoặc tự đọc từng cột từ `Row`.

## 2. Phân biệt tên cột, tên property và bí danh

Ba tên sau có vai trò khác nhau:

- **Tên property Java:** tên thuộc tính trong entity hoặc DTO, ví dụ `customerName`.
- **Tên cột vật lý:** tên được khai báo trong schema, ví dụ `customer_name`.
- **Bí danh SQL (alias):** nhãn thay thế của một cột trong result set, ví dụ `customer_name AS display_name`.

Bảng ví dụ:

| Thành phần | Ví dụ | Dùng ở đâu |
|---|---|---|
| Property Java | `customerName` | Mã nguồn entity/DTO |
| Column trong schema | `customer_name` | DDL và SQL |
| Alias trong SELECT | `customer_name AS display_name` | Nhãn của kết quả truy vấn |
| Mapping annotation | `@Column("display_name")` | Metadata property của entity |

Alias không đổi tên cột trong database. Nó chỉ đổi nhãn cột được trả về bởi câu truy vấn hiện tại.

Ví dụ:

~~~sql
SELECT customer_name AS display_name
FROM customer;
~~~

Bảng vẫn có cột `customer_name`. Kết quả của truy vấn có nhãn `display_name`. Nếu muốn ánh xạ nhãn này vào entity có property `name`, mapping metadata phải xác định `name` tương ứng với `display_name`, chẳng hạn:

~~~java
@Column("display_name")
private String name;
~~~

Nếu entity vẫn khai báo `@Column("customer_name")`, alias `display_name` không còn khớp với tên cột mà metadata mong đợi. Hãy chọn alias tương ứng với mapping đích hoặc điều chỉnh metadata cho đúng.

## 3. Naming strategy và @Column quyết định tên mapping

Khi property không khai báo `@Column`, Spring Data Relational dùng naming strategy để suy ra tên cột từ property. Quy tắc mặc định thường chuyển camelCase thành snake_case:

| Property Java | Tên cột theo naming strategy |
|---|---|
| `firstName` | `first_name` |
| `createdAt` | `created_at` |
| `orderNumber` | `order_number` |
| `totalAmount` | `total_amount` |

Ví dụ:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    private LocalDateTime createdAt;
}
~~~

Mapping mặc định tương ứng với `order_number` và `created_at`, nếu dự án dùng naming strategy mặc định.

Khi tên cột khác quy tắc, dùng `@Column` của Spring Data Relational:

~~~java
@Column("ORDER_NO")
private String orderNumber;
~~~

Trong truy vấn tùy chỉnh, SELECT cần trả về nhãn cột phù hợp với mapping metadata đang dùng. Với property ở ví dụ trên, nhãn cột cần tương ứng với `ORDER_NO` theo quy tắc định danh của database và driver.

`@Column` là metadata ánh xạ property với cột. Nó không tự sửa nội dung của SQL viết tay và không tự tạo alias trong result set.

### 3.1. Dùng đúng annotation package

Với Spring Data Relational R2DBC, import:

~~~java
import org.springframework.data.relational.core.mapping.Column;
~~~

Không nhầm với `jakarta.persistence.Column` của JPA. Hai annotation thuộc hai cơ chế persistence khác nhau.

Khi một dự án có cả JPA và R2DBC, hãy kiểm tra import thực tế của entity. Annotation JPA không thay thế mapping metadata mà Spring Data Relational sử dụng.

## 4. Ánh xạ kết quả @Query về entity

Khi repository method trả về entity, các cột trong SELECT cần cung cấp dữ liệu tương ứng với các property mà entity cần ánh xạ.

Ví dụ:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, customer_name, email_address
        FROM customer
        WHERE id = :id
        """)
    Mono<Customer> findCustomerById(Long id);
}
~~~

Entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("customer_name")
    private String name;

    @Column("email_address")
    private String email;
}
~~~

Ở đây tên cột trong SELECT khớp với mapping của entity. Spring Data chuyển giá trị `customer_name` vào property `name` và `email_address` vào property `email`.

Nếu truy vấn đọc dữ liệu từ một bảng legacy có tên cột khác, có thể đặt alias để result set có nhãn phù hợp với entity:

~~~sql
SELECT
    legacy_cust_nm AS customer_name,
    email_addr AS email_address
FROM legacy_customer
WHERE customer_id = :id;
~~~

Entity vẫn dùng `@Column("customer_name")` và `@Column("email_address")`. Alias làm cho nhãn kết quả khớp với metadata đích.

Không giả định alias bất kỳ sẽ tự động được chuyển sang tên property Java. Hãy dựa vào naming strategy hoặc giá trị `@Column` của property, rồi kiểm tra kết quả bằng integration test trên driver và database thực tế.

## 5. Dùng alias cho DTO và projection

Không phải truy vấn nào cũng cần trả về toàn bộ entity. Với báo cáo, màn hình tổng hợp hoặc danh sách chỉ hiển thị vài trường, DTO projection thường phù hợp hơn.

Ví dụ DTO:

~~~java
public record CustomerOrderSummary(
        Long customerId,
        String customerName,
        Long orderCount) {
}
~~~

Truy vấn:

~~~java
@Query("""
    SELECT
        c.id AS customer_id,
        c.customer_name AS customer_name,
        COUNT(o.id) AS order_count
    FROM customer c
    LEFT JOIN purchase_order o
        ON o.customer_id = c.id
    GROUP BY c.id, c.customer_name
    ORDER BY c.customer_name
    """)
Flux<CustomerOrderSummary> findOrderSummary();
~~~

Các alias được đặt theo naming convention tương ứng với tên component DTO: `customer_id`, `customer_name` và `order_count`. Khi dùng class-based projection, hãy bảo đảm constructor/component của DTO và các nhãn kết quả có thể được mapping tương ứng trong cấu hình Spring Data của dự án.

DTO chỉ chứa dữ liệu mà truy vấn cần trả về. Cách này tránh tạo một entity có nhiều property không được SELECT và làm rõ rằng kết quả là dữ liệu đọc phục vụ một use case.

### 5.1. Interface projection

Nếu dùng interface projection, tên accessor biểu diễn property mà projection cần:

~~~java
public interface CustomerNameView {
    Long getId();
    String getCustomerName();
}
~~~

Truy vấn cần cung cấp nhãn phù hợp với mapping của projection:

~~~java
@Query("""
    SELECT
        c.id AS id,
        c.customer_name AS customer_name
    FROM customer c
    WHERE c.active = TRUE
    """)
Flux<CustomerNameView> findActiveCustomerNames();
~~~

Với projection, alias càng rõ ràng càng dễ hiểu và tránh phụ thuộc vào tên cột không ổn định. Kiểm tra mapping với phiên bản Spring Data R2DBC đang dùng, nhất là khi projection có nested property hoặc tên property khác hẳn schema.

### 5.2. Khi nào dùng entity, khi nào dùng DTO?

| Trường hợp | Kiểu kết quả phù hợp |
|---|---|
| Đọc một aggregate để xử lý nghiệp vụ hoặc cập nhật | Entity |
| Đọc đầy đủ trạng thái một đối tượng | Entity |
| Màn hình chỉ cần vài cột | DTO hoặc projection |
| Báo cáo có `COUNT`, `SUM`, `AVG` | DTO hoặc projection |
| Kết quả join nhiều bảng với tên cột trùng | DTO với alias rõ ràng |
| Kết quả tính toán không tương ứng một entity lưu trữ | DTO hoặc kiểu kết quả chuyên biệt |

Tránh ánh xạ một phần result set vào entity đầy đủ nếu các property không được chọn có thể bị hiểu nhầm là null hoặc trạng thái mặc định. Dùng DTO cho kết quả chỉ đọc một phần thường làm hợp đồng rõ hơn.

## 6. Alias cho biểu thức và hàm tổng hợp

Một biểu thức SQL thường không có nhãn phù hợp với property Java. Hãy đặt alias có ý nghĩa.

Ví dụ:

~~~sql
SELECT
    c.id AS customer_id,
    COALESCE(c.nickname, c.customer_name) AS display_name,
    COUNT(o.id) AS order_count,
    SUM(o.total_amount) AS total_spent
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
GROUP BY c.id, c.nickname, c.customer_name;
~~~

DTO:

~~~java
public record CustomerStatistics(
        Long customerId,
        String displayName,
        Long orderCount,
        BigDecimal totalSpent) {
}
~~~

Các alias mô tả rõ kết quả của biểu thức. Không dựa vào tên mặc định mà database tự gán cho `COUNT(...)` hoặc `COALESCE(...)`; tên đó có thể khó đọc, thay đổi theo database hoặc không khớp với property.

Lưu ý về kiểu dữ liệu:

- `COUNT` thường trả về kiểu số nguyên rộng, nhưng kiểu Java cụ thể cần tương thích với driver và database.
- `SUM` có kiểu kết quả phụ thuộc kiểu cột đầu vào và hệ quản trị.
- `AVG` có thể trả về kiểu số thập phân khác với kiểu cột ban đầu.
- `COALESCE` phải có các đối số tương thích kiểu dữ liệu.
- Giá trị có thể null nếu biểu thức hoặc phép tổng hợp cho phép điều đó.

Hãy kiểm tra kiểu trả về thực tế và dùng kiểu Java phù hợp, ví dụ `Long` cho số đếm và `BigDecimal` cho số tiền.

## 7. Alias khi JOIN nhiều bảng

Một truy vấn join có thể trả về nhiều cột cùng tên. Ví dụ cả `customer` và `purchase_order` đều có cột `id`, `created_at` hoặc `status`.

Không nên dựa vào `SELECT *`:

~~~sql
SELECT *
FROM customer c
JOIN purchase_order o ON o.customer_id = c.id;
~~~

Result set có thể có các nhãn trùng nhau. Khi mapper đọc theo tên, việc xác định cột nào thuộc entity có thể mơ hồ hoặc phụ thuộc hành vi của driver.

Hãy chọn cột tường minh và alias rõ ràng:

~~~sql
SELECT
    c.id AS customer_id,
    c.customer_name AS customer_name,
    o.id AS order_id,
    o.status AS order_status,
    o.created_at AS order_created_at
FROM customer c
JOIN purchase_order o
    ON o.customer_id = c.id;
~~~

DTO tương ứng:

~~~java
public record CustomerOrderRow(
        Long customerId,
        String customerName,
        Long orderId,
        String orderStatus,
        LocalDateTime orderCreatedAt) {
}
~~~

Cách đặt alias này tránh xung đột giữa `customer.id` và `purchase_order.id`, đồng thời làm rõ nguồn gốc dữ liệu.

Nếu mục tiêu là trả về một `Customer` có danh sách `Order`, đừng giả định một câu join bất kỳ sẽ tự dựng aggregate graph như ORM JPA. Spring Data Relational có mô hình aggregate riêng. Hãy xác định cách tải và ghép các dữ liệu liên quan bằng repository, truy vấn tùy chỉnh hoặc DTO, phù hợp với ranh giới aggregate.

## 8. Phân biệt alias cột với tên bảng và tên property trong derived query

Alias chỉ tồn tại trong result set của câu SELECT. Nó không đổi tên bảng, không đổi schema và không đổi tên property trong domain model.

Ví dụ:

~~~sql
SELECT customer_name AS display_name
FROM customer;
~~~

Câu truy vấn này không tạo cột `display_name` trong bảng `customer`. Nếu muốn đổi tên cột vật lý, phải dùng migration schema.

Tương tự, derived query method dùng property Java của entity:

~~~java
Flux<Customer> findByName(String name);
~~~

Nếu entity có property `name` và `@Column("customer_name")`, Spring Data dùng metadata để tạo điều kiện trên cột `customer_name`. Không đổi method thành `findByCustomerName` chỉ vì tên cột vật lý là `customer_name`, trừ khi property Java thực sự tên `customerName`.

Với SQL viết tay trong `@Query`, dùng tên bảng và cột vật lý hoặc alias đúng theo câu truy vấn. Mapping metadata không tự sửa tên trong chuỗi SQL.

## 9. Ánh xạ tường minh bằng DatabaseClient

Khi cần kiểm soát hoàn toàn việc đọc kết quả, `DatabaseClient` cho phép lấy giá trị từ `Row` theo nhãn cột.

Ví dụ:

~~~java
Flux<CustomerOrderRow> findCustomerOrders() {
    return databaseClient.sql("""
            SELECT
                c.id AS customer_id,
                c.customer_name AS customer_name,
                o.id AS order_id,
                o.status AS order_status
            FROM customer c
            JOIN purchase_order o
                ON o.customer_id = c.id
            """)
            .map((row, metadata) -> new CustomerOrderRow(
                    row.get("customer_id", Long.class),
                    row.get("customer_name", String.class),
                    row.get("order_id", Long.class),
                    row.get("order_status", String.class)))
            .all();
}
~~~

Ở đây, các chuỗi truyền vào `row.get(...)` phải khớp với nhãn cột mà driver cung cấp. Vì thế, alias trong SQL và tên dùng trong mapper phải thống nhất.

Có thể dùng `RowMetadata` để xem thông tin cột do driver cung cấp:

~~~java
.map((row, metadata) -> {
    ColumnMetadata idColumn =
            metadata.getColumnMetadata("customer_id");

    Long id = row.get("customer_id", Long.class);

    return new CustomerIdView(id);
})
~~~

API metadata và khả năng tra cứu theo tên phụ thuộc R2DBC SPI và driver. Nếu gặp khác biệt về chữ hoa/chữ thường, hãy kiểm tra label thực tế được trả về và dùng tên ổn định trong SQL.

### 9.1. Đọc cột nullable

Một cột nullable có thể trả về Java `null` khi đọc bằng `Row.get`:

~~~java
String phoneNumber =
        row.get("phone_number", String.class);
~~~

Nếu `phone_number` là SQL NULL, biến `phoneNumber` có thể là `null`. Dùng kiểu wrapper như `Long`, `Integer` hoặc `Boolean` khi cột có thể null; kiểu primitive Java như `long` hoặc `int` không thể chứa null.

Không nhầm hai trường hợp:

- Không có hàng: publisher không phát row.
- Có hàng nhưng cột nullable là SQL NULL: publisher phát row và giá trị cột là null.

### 9.2. Tự chuyển đổi kiểu dữ liệu

`Row.get(label, type)` yêu cầu kiểu Java tương thích với giá trị mà driver có thể cung cấp. Với kiểu số, ngày giờ, UUID hoặc kiểu đặc thù database, hãy kiểm tra mapping của driver.

Nếu phép chuyển đổi không được hỗ trợ trực tiếp, có thể dùng Spring Data conversion khi mapping entity/DTO, hoặc chuyển đổi tường minh trong mapper. Không ép kiểu tùy tiện bằng cast vì có thể gây `ClassCastException` khi runtime.

## 10. Tên alias và chữ hoa/chữ thường của identifier

Quy tắc chữ hoa/chữ thường của tên cột và alias phụ thuộc hệ quản trị cơ sở dữ liệu.

Ví dụ, PostgreSQL chuyển identifier không quote về chữ thường. Một số hệ quản trị khác có thể chuyển về chữ hoa hoặc áp dụng quy tắc riêng. Identifier có quote thường giữ nguyên cách viết theo quy tắc của dialect.

Ví dụ PostgreSQL:

~~~sql
SELECT customer_name AS display_name
FROM customer;
~~~

Alias không quote được chuẩn hóa thành `display_name`.

Nếu viết:

~~~sql
SELECT customer_name AS "displayName"
FROM customer;
~~~

PostgreSQL giữ nguyên chữ hoa/chữ thường trong alias đã quote. Khi đó mapper cần tra cứu nhãn đúng theo tên mà driver công bố.

Để giảm khác biệt giữa các database:

- Ưu tiên alias chữ thường dạng `snake_case`.
- Tránh alias chứa dấu cách hoặc ký tự đặc biệt nếu không cần.
- Tránh dùng từ khóa SQL làm alias.
- Nếu bắt buộc quote identifier, dùng cú pháp quote theo dialect và kiểm tra trên database mục tiêu.
- Không dựa vào việc driver tự chuẩn hóa tên theo cùng một cách trên mọi hệ quản trị.

## 11. Thiếu cột, cột dư và ánh xạ entity một phần

Một entity có thể chứa nhiều property persistent hơn số cột được chọn trong câu SQL. Ví dụ entity có `id`, `name`, `email`, `phoneNumber`, nhưng query chỉ chọn `id` và `name`.

~~~sql
SELECT id, customer_name
FROM customer;
~~~

Đây là result set một phần. Property không có trong result set không thể được lấy từ hàng. Cách xử lý cụ thể phụ thuộc kiểu entity, constructor và mapping converter; không nên dựa vào việc property thiếu sẽ luôn tự động nhận null hoặc giá trị mặc định.

Nếu use case chỉ cần hai trường, nên tạo projection/DTO riêng:

~~~java
public record CustomerNameView(
        Long id,
        String customerName) {
}
~~~

Nếu truy vấn cần trả về entity đầy đủ, hãy chọn đủ các cột persistent cần thiết:

~~~sql
SELECT
    id,
    customer_name,
    email_address,
    phone_number
FROM customer;
~~~

Cột dư trong result set không tự trở thành property của entity. Nếu truy vấn có thêm `COUNT`, biểu thức hoặc dữ liệu từ bảng join, hãy ánh xạ phần đó vào DTO phù hợp thay vì mong entity tự lưu giữ các cột không thuộc mapping.

## 12. Alias cho nested projection và value object

Khi kết quả cần biểu diễn dữ liệu lồng nhau, hãy xem xét kiểu DTO phù hợp với cách mapping được hỗ trợ trong phiên bản Spring Data. Không nên giả định rằng dấu chấm trong alias như `address.city` tự động dựng một object lồng nhau.

Một cách an toàn là dùng alias phẳng:

~~~sql
SELECT
    c.id AS customer_id,
    c.customer_name AS customer_name,
    a.city AS address_city,
    a.postal_code AS address_postal_code
FROM customer c
LEFT JOIN customer_address a
    ON a.customer_id = c.id;
~~~

DTO phẳng:

~~~java
public record CustomerAddressRow(
        Long customerId,
        String customerName,
        String addressCity,
        String addressPostalCode) {
}
~~~

Tầng service có thể chuyển DTO phẳng thành response có cấu trúc lồng nhau. Cách này làm rõ trường hợp địa chỉ không tồn tại, tránh phụ thuộc vào quy tắc ánh xạ nested alias không được hỗ trợ.

Nếu entity sử dụng `@Embedded` hoặc một value object, hãy chọn alias theo column mapping của embedded property và prefix đã cấu hình. Kiểm tra mapping metadata của Spring Data Relational để xác nhận tên cột hiệu lực.

## 13. Lỗi thường gặp khi ánh xạ tên cột và alias

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Alias khác tên cột mà entity mapping mong đợi | Nhãn result set không khớp mapping metadata | Dùng alias phù hợp với naming strategy hoặc `@Column` |
| Dùng tên property Java thay cho cột vật lý trong SQL | SQL viết tay không được mapping metadata tự sửa | Viết đúng tên cột hoặc alias trong câu SELECT |
| Dùng `SELECT *` cho join | Nhiều bảng có cột trùng tên | Chọn cột tường minh và đặt alias riêng |
| Bỏ alias cho `COUNT`, `SUM` hoặc biểu thức | Nhãn kết quả khó dự đoán, không khớp DTO | Đặt alias ổn định, có ý nghĩa |
| Chọn thiếu cột khi trả entity đầy đủ | Entity thiếu dữ liệu cần ánh xạ | Chọn đủ cột hoặc dùng projection/DTO |
| Dùng alias camelCase nhưng naming strategy kỳ vọng snake_case | Nhãn không theo mapping convention | Dùng alias snake_case hoặc mapping rõ ràng |
| Nhầm `@Column` của JPA với Spring Data | Annotation thuộc framework khác | Import `org.springframework.data.relational.core.mapping.Column` |
| Alias trùng nhau trong join | Mapper không xác định được cột đích | Đặt alias phân biệt như `customer_id`, `order_id` |
| Sai chữ hoa/chữ thường của alias đã quote | Database giữ nguyên identifier đã quote | Kiểm tra label thực tế từ driver |
| Ép kiểu giá trị `COUNT` hoặc `SUM` sai | Kiểu SQL/driver khác kiểu Java giả định | Chọn kiểu tương thích hoặc chuyển đổi tường minh |
| Dùng alias như thể đã đổi schema | Alias chỉ đổi nhãn kết quả | Dùng migration nếu cần đổi tên cột vật lý |

## 14. Quy trình thiết kế SELECT và mapping kết quả

Khi viết một truy vấn khai báo, hãy thực hiện theo trình tự:

1. Xác định kiểu kết quả là entity, DTO hay projection.
2. Liệt kê các property cần có trong kiểu kết quả.
3. Xác định tên cột mapping hiệu lực từ naming strategy và `@Column`.
4. Viết SELECT tường minh, tránh `SELECT *` khi join hoặc projection.
5. Đặt alias cho biểu thức, aggregate và các cột trùng tên.
6. Bảo đảm alias khớp với mapping metadata hoặc mapper tường minh.
7. Kiểm tra chữ hoa/chữ thường và quy tắc quote của database.
8. Kiểm tra kiểu Java tương ứng với kiểu dữ liệu mà driver trả về.
9. Xác định rõ cột nullable và các property có thể không xuất hiện.
10. Chạy integration test trên đúng database/driver để xác nhận entity hoặc DTO được dựng như mong đợi.

Một bảng mapping trước khi viết SQL giúp giảm lỗi:

| Nhãn kết quả | Property đích | Ghi chú |
|---|---|---|
| `id` | `id` | Khóa chính |
| `customer_name` | `name` | Entity dùng `@Column("customer_name")` |
| `email_address` | `email` | Entity dùng `@Column("email_address")` |
| `order_count` | `orderCount` | Alias của biểu thức `COUNT` |
| `order_id` | `orderId` | Alias phân biệt với `customer_id` |

## 15. Kiểm thử ánh xạ kết quả

Một truy vấn có thể chạy thành công nhưng vẫn ánh xạ sai property hoặc kiểu dữ liệu. Vì vậy, integration test nên kiểm tra giá trị thực tế của từng property quan trọng.

Ví dụ với repository:

~~~java
StepVerifier.create(customerRepository.findCustomerById(existingId))
        .assertNext(customer -> {
            assertThat(customer.getId()).isEqualTo(existingId);
            assertThat(customer.getName()).isEqualTo("Nguyen An");
            assertThat(customer.getEmail()).isEqualTo("an@example.com");
        })
        .verifyComplete();
~~~

Với projection:

~~~java
StepVerifier.create(customerRepository.findOrderSummary())
        .assertNext(summary -> {
            assertThat(summary.customerId()).isEqualTo(10L);
            assertThat(summary.customerName()).isEqualTo("Nguyen An");
            assertThat(summary.orderCount()).isEqualTo(2L);
        })
        .verifyComplete();
~~~

Với `DatabaseClient`, kiểm tra mapper trả đúng giá trị theo alias. Tạo dữ liệu test có:

- Tên cột khác tên property Java.
- Alias của biểu thức tính toán.
- Hai bảng có cột cùng tên.
- Cột nullable.
- Không có hàng phù hợp.
- Giá trị số lớn hoặc kiểu dữ liệu đặc thù nếu truy vấn có aggregate.

Unit test cho mapper có thể kiểm tra logic chuyển đổi thuần Java, nhưng integration test trên database mục tiêu mới xác nhận được alias, metadata, driver và mapping cùng hoạt động.

## 16. Ghi nhớ

- Spring Data R2DBC ánh xạ result set dựa trên mapping metadata và nhãn cột do driver cung cấp.
- Tên property Java, tên cột vật lý và alias SQL là ba khái niệm khác nhau.
- Naming strategy thường chuyển camelCase thành snake_case; `@Column` ghi đè tên cột cho property cụ thể.
- Alias trong SELECT chỉ đổi nhãn kết quả; nó không đổi schema hoặc tên property Java.
- Với entity, nhãn kết quả cần phù hợp với tên cột hiệu lực trong mapping metadata.
- Với DTO/projection, đặt alias rõ ràng theo property và naming convention mà mapping sử dụng.
- Đặt alias cho biểu thức, aggregate và các cột trùng tên trong JOIN.
- Tránh `SELECT *` khi join nhiều bảng hoặc khi chỉ cần một projection nhỏ.
- `DatabaseClient` cho phép đọc theo alias tường minh qua `Row.get`; tên phải khớp label mà driver cung cấp.
- Phân biệt không có hàng với một hàng có cột SQL NULL.
- Nếu SELECT chỉ lấy một phần dữ liệu, dùng DTO/projection thay vì giả định entity đầy đủ sẽ được dựng đúng.
- Xác nhận alias, kiểu dữ liệu và quy tắc chữ hoa/chữ thường bằng integration test trên database thực tế.

