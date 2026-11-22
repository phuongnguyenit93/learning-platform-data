# Khác biệt ký hiệu bind, dấu ngoặc định danh và từ khóa dành riêng

## 1. Vì sao SQL khác nhau giữa các hệ quản trị?

Spring Data R2DBC cung cấp repository, `R2dbcEntityTemplate` và `DatabaseClient` để làm việc với relational database. Tuy nhiên, R2DBC là abstraction truy cập dữ liệu; nó không biến PostgreSQL, MySQL, SQL Server và H2 thành một hệ quản trị có cùng cú pháp SQL.

Những khác biệt thường gặp gồm:

- Ký hiệu bind parameter mà driver chấp nhận.
- Cách quote tên bảng, cột, schema và identifier khác.
- Tập từ khóa dành riêng (reserved keywords).
- Quy tắc chuyển chữ hoa/chữ thường của identifier không được quote.
- Cú pháp phân trang, generated value, kiểu dữ liệu và hàm SQL.
- Cách driver bind giá trị null, collection và kiểu dữ liệu đặc thù.

Ví dụ, marker native có thể là `$1` trong PostgreSQL, `?` trong MySQL hoặc marker theo quy ước của driver SQL Server. Tên cột `order` có thể bị parser hiểu là từ khóa `ORDER BY`. Tên bảng `user` cũng có thể xung đột với từ khóa hoặc tên dựng sẵn.

Trong Spring Data R2DBC, cần phân biệt:

1. **SQL do Spring Data tạo:** dialect hỗ trợ chọn bind marker, quote identifier và một số cú pháp riêng.
2. **SQL do ứng dụng viết:** câu lệnh trong `@Query` hoặc `DatabaseClient.sql(...)` vẫn phải phù hợp với database mục tiêu. Không giả định framework tự dịch mọi native SQL sang hệ quản trị khác.

Hiểu rõ ranh giới này giúp tránh lỗi khi chuyển database hoặc xây dựng ứng dụng hỗ trợ nhiều môi trường.

## 2. Bind parameter là gì?

Bind parameter là vị trí trong câu SQL để driver gắn giá trị dữ liệu tại thời điểm thực thi. Ứng dụng viết câu lệnh có marker rồi bind giá trị riêng, thay vì nối dữ liệu đầu vào trực tiếp vào SQL.

Ví dụ ý tưởng:

```sql
SELECT id, email_address
FROM customer
WHERE email_address = <parameter>;
```

`<parameter>` chỉ là placeholder minh họa; marker thật phụ thuộc driver và dialect.

Bind parameter giúp:

- Tránh nối chuỗi dữ liệu đầu vào vào SQL.
- Giảm nguy cơ SQL injection đối với giá trị.
- Truyền kiểu dữ liệu riêng với câu SQL.
- Có thể hỗ trợ database tái sử dụng kế hoạch thực thi.
- Tách câu SQL khỏi dữ liệu.

Không làm như sau:

```java
// Không an toàn
String sql = "SELECT * FROM customer WHERE email_address = '"
        + email + "'";
```

Hãy bind giá trị:

```java
databaseClient.sql("SELECT id FROM customer WHERE email_address = :email")
        .bind("email", email)
        .fetch()
        .all();
```

Ví dụ dùng named parameter của Spring `DatabaseClient`. Lớp Spring chuyển marker theo dialect/driver khi thực thi.

## 3. Ký hiệu bind native

R2DBC SPI làm việc với `Statement` và các vị trí bind do driver cung cấp. Marker native không giống nhau giữa mọi driver.

| Hệ quản trị / driver | Marker native thường gặp | Ví dụ |
| --- | --- | --- |
| PostgreSQL R2DBC | `$1`, `$2`, ... | `WHERE id = $1` |
| MySQL R2DBC | `?` | `WHERE id = ?` |
| Microsoft SQL Server R2DBC | Marker theo tên/ordinal như `@P0` tùy driver | `WHERE id = @P0` |
| H2 R2DBC | Theo quy ước driver, thường positional | Kiểm tra tài liệu đúng phiên bản |

Đây là dạng thường gặp để nhận diện cú pháp, không phải cam kết mọi phiên bản driver đều giống nhau. Hãy kiểm tra tài liệu của driver đang dùng.

### 3.1. PostgreSQL

PostgreSQL thường dùng marker positional bắt đầu từ `$1`:

```sql
SELECT id, email_address
FROM customer
WHERE email_address = $1
  AND status = $2;
```

Trong R2DBC native API, vị trí bind ở Java thường bắt đầu từ 0, trong khi marker SQL bắt đầu từ `$1`:

```java
connection.createStatement("SELECT id FROM customer WHERE email_address = $1")
        .bind(0, email)
        .execute();
```

Với driver PostgreSQL phổ biến, `$1` tương ứng index `0` của `Statement.bind(0, value)`. Đừng nhầm chỉ số marker trong SQL với chỉ số API Java.

### 3.2. MySQL

MySQL R2DBC thường dùng dấu hỏi `?` làm positional marker:

```sql
SELECT id, email_address
FROM customer
WHERE email_address = ?
  AND status = ?;
```

Các giá trị được bind theo thứ tự xuất hiện:

```java
connection.createStatement(
        "SELECT id FROM customer WHERE email_address = ? AND status = ?")
        .bind(0, email)
        .bind(1, status)
        .execute();
```

Hai dấu hỏi không mang tên. Nếu đổi thứ tự marker hoặc bind nhầm index, giá trị có thể được gắn sai cột.

### 3.3. SQL Server

Driver SQL Server có quy ước marker riêng, thường biểu diễn tham số theo tên/ordinal như `@P0`. Cú pháp chính xác và cách gọi bind phụ thuộc phiên bản driver:

```sql
SELECT id, email_address
FROM customer
WHERE email_address = @P0;
```

Khi dùng Spring `DatabaseClient`, ưu tiên named parameter ở lớp ứng dụng và để dialect/driver xử lý marker native. Nếu dùng trực tiếp R2DBC `Statement`, theo đúng quy tắc marker mà driver SQL Server công bố.

### 3.4. Không tự chuyển marker bằng replace

Không tự thay `:name` thành `?`, `$1` hoặc `@P0` bằng `String.replace`. Câu SQL có thể chứa các ký tự này trong string literal, comment, cast hoặc biểu thức đặc thù. Thay chuỗi đơn giản dễ làm hỏng SQL hoặc bind sai thứ tự.

Hãy dùng `DatabaseClient`, Spring Data repository hoặc `BindMarkersFactory` để xử lý marker theo dialect.

## 4. Named parameter của Spring và marker native

Spring `DatabaseClient` cho phép viết named parameter:

```java
databaseClient.sql("""
        SELECT id, display_name
        FROM customer
        WHERE status = :status
          AND created_at >= :fromTime
        """)
        .bind("status", status)
        .bind("fromTime", fromTime)
        .fetch()
        .all();
```

`:status` và `:fromTime` là named parameter của Spring. `DatabaseClient` có thể mở rộng chúng thành marker phù hợp với dialect/driver rồi bind giá trị tương ứng.

Minh họa cùng một query ở các lớp:

```text
Spring SQL:       WHERE status = :status
PostgreSQL SQL:   WHERE status = $1
MySQL SQL:        WHERE status = ?
SQL Server SQL:  WHERE status = @P0 (theo driver)
```

Không phải mọi API R2DBC đều hiểu `:name`. `io.r2dbc.spi.Connection.createStatement(...)` nhận SQL theo native syntax của driver; nó không tự cung cấp toàn bộ chức năng named parameter của Spring `DatabaseClient`.

### 4.1. Bind theo tên

```java
databaseClient.sql("SELECT * FROM customer WHERE id = :id")
        .bind("id", 42L)
        .fetch()
        .one();
```

Tên truyền cho `.bind("id", ...)` phải khớp marker `:id`.

### 4.2. Bind theo vị trí

```java
databaseClient.sql("SELECT * FROM customer WHERE id = ?")
        .bind(0, 42L)
        .fetch()
        .one();
```

Khi dùng positional marker, phải tuân thủ marker mà driver/dialect chấp nhận và thứ tự bind. Named parameter thường dễ đọc hơn khi ứng dụng cần hỗ trợ nhiều dialect.

### 4.3. Named parameter expansion

`DatabaseClient` có cơ chế named parameter expansion trong các phiên bản Spring Framework hỗ trợ. Nếu ứng dụng tùy chỉnh builder hoặc tắt tính năng này, marker `:name` có thể không được chuyển đổi. Kiểm tra cấu hình `DatabaseClient.Builder` và phiên bản framework trước khi dựa vào named parameter.

Với Spring Data R2DBC `@Query`, tham số method cũng được xử lý theo cơ chế query mapping của Spring Data. Không lấy cú pháp native marker của một driver áp dụng máy móc vào mọi repository query.

## 5. Bind giá trị, không bind tên bảng hoặc tên cột

Bind parameter đại diện cho **giá trị dữ liệu**, không đại diện cho SQL identifier.

Ví dụ sau không có nghĩa `:column` được thay bằng tên cột:

```sql
SELECT :column
FROM customer;
```

Sau khi bind, marker được hiểu như giá trị scalar. Tương tự, không thể dùng marker để thay tên bảng:

```sql
SELECT * FROM :tableName;
```

Đây không phải cách bind identifier hợp lệ.

Nếu cần chọn cột sắp xếp động, ánh xạ input vào allowlist:

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
        "created", "created_at",
        "name", "display_name",
        "email", "email_address");

public Flux<Customer> findCustomers(String requestedSort) {
    String column = SORT_COLUMNS.get(requestedSort);
    if (column == null) {
        return Flux.error(new IllegalArgumentException("Unsupported sort field"));
    }

    String sql = "SELECT id, display_name, email_address FROM customer ORDER BY "
            + column;
    return databaseClient.sql(sql)
            .map(this::mapCustomer)
            .all();
}
```

Chỉ identifier được chọn từ danh sách cố định do ứng dụng kiểm soát mới được đưa vào SQL. Không nối trực tiếp tên cột do người dùng gửi.

Nếu cần quote identifier động, dùng `SqlIdentifier`/`IdentifierProcessing` của Spring Data Relational khi phù hợp, hoặc một hàm quote riêng theo dialect đã xác định. `bind()` không bảo vệ identifier như cách nó bảo vệ giá trị.

## 6. Dấu quote identifier

Identifier là tên các đối tượng SQL như schema, table, column, index, constraint và sequence. Database cung cấp dấu quote để parser hiểu phần bên trong là tên đối tượng, đặc biệt khi tên trùng từ khóa hoặc có ký tự đặc biệt.

| Hệ quản trị | Dấu quote identifier thường dùng | Ví dụ |
| --- | --- | --- |
| PostgreSQL | Dấu nháy kép `"` | `"order"`, `"CreatedAt"` |
| MySQL | Backtick (dấu huyền ngược) | Ví dụ: tên order được đặt trong cặp backtick |
| SQL Server | Ngoặc vuông `[]`; dấu nháy kép khi `QUOTED_IDENTIFIER` bật | `[order]`, `[user]` |
| H2 | Dấu nháy kép `"` | `"order"` |

Dấu nháy đơn `'` dành cho string literal, không phải cách quote tên bảng hoặc cột:

```sql
SELECT 'customer' AS label; -- string literal
SELECT "customer".id FROM "customer"; -- quoted identifier trong PostgreSQL/H2
```

## 7. Khác biệt chữ hoa/chữ thường của identifier

Identifier không được quote có thể bị database chuyển đổi chữ hoa/chữ thường theo quy tắc riêng.

### 7.1. PostgreSQL

PostgreSQL chuyển identifier không quote về chữ thường:

```sql
CREATE TABLE Customer (
    id BIGINT PRIMARY KEY
);
```

Tên bảng thực tế là `customer`. Các cách viết không quote `Customer`, `CUSTOMER` và `customer` được xử lý như cùng identifier chữ thường.

Nếu quote:

```sql
CREATE TABLE "Customer" (
    id BIGINT PRIMARY KEY
);

SELECT * FROM "Customer";
```

Tên lúc này có phân biệt chữ hoa/chữ thường; `SELECT * FROM customer` không trỏ tới `"Customer"`.

### 7.2. MySQL

MySQL dùng backtick để quote identifier. Quy tắc phân biệt hoa/thường của tên database và table có thể phụ thuộc hệ điều hành cùng cấu hình `lower_case_table_names`. Tên column trong MySQL thường không phân biệt hoa/thường.

Không nên dựa vào việc tên bảng viết hoa chạy được trên Windows để kết luận sẽ chạy giống hệt trên Linux. Dùng quy ước chữ thường và `snake_case` giúp tránh khác biệt môi trường.

### 7.3. SQL Server

SQL Server hỗ trợ identifier trong ngoặc vuông:

```sql
SELECT [Order], [User]
FROM [Sales].[OrderHeader];
```

Dấu nháy kép cũng có thể dùng cho identifier khi `QUOTED_IDENTIFIER` được bật. Khả năng phân biệt chữ hoa/chữ thường chịu ảnh hưởng collation của database/server.

### 7.4. Quy tắc an toàn

- Dùng tên bảng/cột chữ thường.
- Dùng `snake_case`.
- Tránh quote identifier nếu không cần.
- Tránh tên trùng từ khóa SQL.
- Nếu phải quote, quote nhất quán ở DDL, query, migration và mapping.
- Không trộn cùng một tên vật lý với nhiều cách viết hoa/thường.

## 8. Từ khóa dành riêng và tên identifier

SQL có các từ khóa được dùng trong cú pháp. Một số từ là reserved keywords, nghĩa là không thể dùng làm identifier không quote ở vị trí tương ứng.

Ví dụ những tên dễ gây xung đột:

- `order` — thường xung đột với `ORDER BY`.
- `group` — thường xung đột với `GROUP BY`.
- `select` — từ khóa truy vấn.
- `user` — có ý nghĩa đặc biệt hoặc là từ khóa ở một số hệ quản trị.
- `key` — có thể là từ khóa trong một số dialect.
- `limit`, `offset`, `rank`, `value` — có thể có ý nghĩa đặc thù tùy hệ quản trị/phiên bản.

Danh sách reserved keyword không hoàn toàn giống nhau giữa PostgreSQL, MySQL, SQL Server và H2. Một từ có thể là reserved ở hệ quản trị này nhưng chỉ là non-reserved hoặc contextual keyword ở hệ quản trị khác.

Không ghi nhớ một danh sách chung rồi cho rằng nó đúng với mọi phiên bản. Hãy kiểm tra tài liệu từ khóa của database mục tiêu và ưu tiên tên miền nghiệp vụ rõ ràng.

Thay vì:

```sql
CREATE TABLE order (
    id BIGINT PRIMARY KEY
);
```

nên dùng:

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY
);
```

Tên `purchase_order` rõ nghĩa và ít có khả năng xung đột hơn.

## 9. Quote identifier khi bắt buộc dùng tên trùng từ khóa

Nếu schema cũ hoặc hợp đồng tích hợp buộc phải giữ tên `order`, cần quote theo database.

PostgreSQL:

```sql
CREATE TABLE "order" (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);

SELECT id, status FROM "order";
```

MySQL dùng backtick (dấu huyền ngược) bao quanh tên bảng:

```sql
CREATE TABLE `order` (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);

SELECT id, status FROM `order`;
```

SQL Server:

```sql
CREATE TABLE [order] (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);

SELECT id, status FROM [order];
```

Không lấy nguyên câu DDL PostgreSQL có dấu nháy kép rồi chạy trực tiếp trên MySQL với cấu hình mặc định, hoặc lấy cú pháp MySQL rồi chạy trên PostgreSQL. Nếu phải hỗ trợ nhiều database, cần DDL riêng theo dialect hoặc migration được viết cho từng hệ quản trị.

## 10. IdentifierProcessing và SqlIdentifier trong Spring Data Relational

Spring Data Relational có abstraction cho identifier. `SqlIdentifier` biểu diễn tên SQL cùng trạng thái quoted/unquoted; `IdentifierProcessing` mô tả cách database quote và chuyển đổi identifier.

Ví dụ:

```java
SqlIdentifier table = SqlIdentifier.unquoted("customer");
SqlIdentifier column = SqlIdentifier.quoted("Order");
```

`SqlIdentifier.unquoted(...)` biểu diễn tên không quote. `SqlIdentifier.quoted(...)` biểu diễn identifier cần được quote theo quy tắc dialect khi Spring tạo SQL.

Các API lập SQL của Spring Data Relational có thể dùng dialect và `IdentifierProcessing` để render identifier đúng hệ quản trị. Điều này hữu ích khi framework tự tạo câu SQL từ mapping metadata.

Không nhầm `SqlIdentifier.quoted("Order")` với việc tự thêm dấu quote vào chuỗi SQL tùy ý. Nó là metadata để SQL generator xử lý identifier; native query vẫn phải tuân thủ cú pháp database đang chạy.

### 10.1. Entity mapping với @Table và @Column

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_status")
    private String status;
}
```

Tên trong annotation cần khớp tên vật lý của schema theo naming strategy và mapping configuration. Nếu dùng tên cần quote hoặc chữ hoa có phân biệt, hãy kiểm tra cách phiên bản Spring Data Relational diễn giải metadata và SQL generator render identifier.

Với tên mới, ưu tiên tên đơn giản, chữ thường, không cần quote. Nếu tích hợp schema cũ có identifier đặc biệt, viết integration test xác nhận câu SQL được sinh và chạy đúng trên database thật.

## 11. Dialect trong Spring Data R2DBC

Dialect mô tả khác biệt SQL của hệ quản trị mà Spring Data cần biết. Spring Data R2DBC có dialect tương ứng với database/driver như PostgreSQL, H2, MySQL hoặc SQL Server tùy phiên bản hỗ trợ.

Dialect có thể tham gia vào:

- Tạo bind marker phù hợp.
- Quote identifier.
- Sinh một số biểu thức SQL đặc thù.
- Xử lý generated ID hoặc pagination theo database.
- Chọn quy tắc mapping cần thiết cho hệ quản trị.

Khi dùng `ReactiveCrudRepository`, Spring Data tạo nhiều câu SQL từ metadata và dialect. Khi dùng `@Query` hoặc `DatabaseClient.sql(...)`, ứng dụng viết câu SQL cụ thể nên vẫn chịu trách nhiệm về cú pháp và tính portable của câu lệnh.

### 11.1. Dialect không phải bộ dịch SQL tổng quát

Không nên kỳ vọng Spring tự dịch mọi câu:

```sql
SELECT ...
LIMIT 10 OFFSET 20;
```

sang cú pháp phân trang khác của SQL Server, hoặc chuyển mọi hàm PostgreSQL thành hàm tương đương trên MySQL. Dialect giúp framework tạo SQL trong phạm vi nó hỗ trợ; native SQL tùy chỉnh vẫn có thể phụ thuộc hệ quản trị.

Nếu cần hỗ trợ nhiều database, hãy tách SQL đặc thù thành repository implementation hoặc query strategy theo dialect. Giữ thao tác CRUD portable ở repository khi có thể.

### 11.2. Một repository và nhiều dialect

Một repository/template thường được xây dựng với mapping context và dialect gắn với `ConnectionFactory` được cấu hình. Nếu một routing `ConnectionFactory` chuyển giữa nhiều database có dialect khác nhau, không nên giả định Spring Data tự đổi dialect cho từng connection ở mỗi request.

Mô hình routing đơn giản phù hợp nhất khi target database tương thích về dialect, schema và kiểu dữ liệu. Nếu cần định tuyến giữa PostgreSQL và MySQL, có thể phải dùng template/repository riêng cho từng dialect hoặc lớp adapter tách biệt, thay vì một repository duy nhất dùng một dialect cho mọi target.

## 12. Viết query portable với named parameter

Một câu query đơn giản dùng cú pháp SQL phổ biến và named parameter của Spring có thể dễ duy trì hơn:

```java
databaseClient.sql("""
        SELECT id, email_address
        FROM customer
        WHERE status = :status
        """)
        .bind("status", "ACTIVE")
        .map((row, metadata) -> new CustomerSummary(
                row.get("id", UUID.class),
                row.get("email_address", String.class)))
        .all();
```

Named parameter giúp không phải tự viết `$1` hay `?` trong code ứng dụng. Tuy vậy, query vẫn cần dùng cú pháp, tên bảng/cột và kiểu dữ liệu hợp lệ trên database mục tiêu.

Ví dụ, `LIMIT`, `RETURNING`, JSON operator, array operator, upsert và hàm ngày giờ có thể khác nhau giữa hệ quản trị. Named parameter không làm các phần đó portable.

## 13. Bind giá trị NULL đúng cách

R2DBC SPI không cho bind Java `null` như một giá trị thông thường bằng `.bind(index, null)`. Cần dùng API bind null có khai báo kiểu:

```java
databaseClient.sql("UPDATE customer SET display_name = :name WHERE id = :id")
        .bindNull("name", String.class)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
```

Kiểu Java truyền cho `bindNull` giúp driver xác định kiểu dữ liệu cần bind. Với positional parameter, dùng overload `bindNull(index, type)` nếu API phiên bản đang dùng cung cấp.

### 13.1. NULL không giống chuỗi rỗng

- SQL `NULL`: không có giá trị/unknown theo logic SQL.
- `''`: chuỗi rỗng.
- `'   '`: chuỗi có khoảng trắng.
- `0`: số không.

Điều kiện `column = NULL` không đúng cách để tìm NULL. Hãy dùng `IS NULL`:

```sql
SELECT id
FROM customer
WHERE display_name IS NULL;
```

Nếu query cần điều kiện tùy chọn, có thể viết:

```sql
WHERE (:name IS NULL OR display_name = :name)
```

Kiểu bind null và khả năng suy luận kiểu của database/driver cần được kiểm thử. Với query phức tạp, có thể xây dựng các nhánh SQL rõ ràng thay vì dùng một biểu thức optional cho mọi trường hợp.

## 14. Bind collection trong điều kiện IN

Một số API Spring hỗ trợ mở rộng collection parameter thành nhiều bind marker:

```java
databaseClient.sql("SELECT id, display_name FROM customer WHERE id IN (:ids)")
        .bind("ids", List.of(id1, id2, id3))
        .fetch()
        .all();
```

Spring có thể mở rộng danh sách thành các marker riêng phù hợp dialect. Đây là tính năng của lớp named-parameter expansion, không phải mọi R2DBC driver đều nhận một Java `List` như một scalar parameter trong `IN`.

### 14.1. Danh sách rỗng

`IN ()` không phải cú pháp portable và có thể không hợp lệ. Nếu collection rỗng, hãy quyết định ý nghĩa nghiệp vụ ở ứng dụng:

- Nếu không có ID nghĩa là không có kết quả, trả `Flux.empty()` mà không gửi SQL.
- Nếu collection rỗng có nghĩa là không lọc, dùng một nhánh query riêng.
- Không bỏ điều kiện `IN` vô tình vì điều đó có thể làm query trả toàn bộ bảng.

Ví dụ:

```java
public Flux<Customer> findByIds(Collection<UUID> ids) {
    if (ids.isEmpty()) {
        return Flux.empty();
    }

    return databaseClient.sql(
                    "SELECT id, display_name FROM customer WHERE id IN (:ids)")
            .bind("ids", ids)
            .map(this::mapCustomer)
            .all();
}
```

Hãy kiểm tra giới hạn số bind parameter của database/driver. Với danh sách rất lớn, dùng batch, temporary table, table-valued parameter hoặc cơ chế array phù hợp database thay vì tạo hàng nghìn marker trong một câu query.

## 15. Dấu quote trong string literal và identifier

Không nhầm các loại dấu:

| Cú pháp | Ý nghĩa thường gặp |
| --- | --- |
| `'text'` | String literal |
| `"column"` | Quoted identifier trong PostgreSQL/H2; SQL Server khi cấu hình phù hợp |
| Backtick bao quanh tên | Quoted identifier trong MySQL |
| `[column]` | Quoted identifier trong SQL Server |
| `:value` | Named parameter trong Spring API hỗ trợ named binding |
| `$1` | Positional marker PostgreSQL native |
| `?` | Positional marker trong nhiều driver, bao gồm MySQL |

Ví dụ:

```sql
SELECT "order" FROM "purchase_order" WHERE status = 'PENDING';
```

Ở đây `"order"` là identifier, còn `'PENDING'` là string literal.

Nếu dùng double quote cho string trên MySQL với chế độ mặc định, database có thể hiểu đó là identifier thay vì string. Hãy dùng nháy đơn cho giá trị chuỗi trong SQL.

## 16. Reserved keyword thay đổi theo phiên bản

Reserved keyword có thể thay đổi giữa các phiên bản database. Một từ từng là identifier hợp lệ ở phiên bản cũ có thể trở thành từ khóa ở phiên bản mới khi hệ quản trị bổ sung cú pháp.

Ví dụ, tên `rank`, `groups`, `system`, `window`, `json`, `key` hoặc `value` có thể có ý nghĩa đặc biệt trong một số dialect/phiên bản. Danh sách chính xác cần được kiểm tra theo phiên bản server.

Để giảm rủi ro:

- Dùng tên domain rõ nghĩa như `customer_order`, `user_account`, `group_membership`.
- Tránh tên quá chung như `value`, `key`, `user`, `order`, `group`.
- Nếu dùng tên có khả năng xung đột do schema cũ, quote nhất quán.
- Chạy migration và integration test trên phiên bản database thực tế.
- Khi nâng cấp server, kiểm tra release notes về keyword mới hoặc thay đổi parser.

## 17. Native query và khả năng chuyển đổi giữa database

Một repository có thể dùng query derivation:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, UUID> {

    Flux<Customer> findByStatusOrderByCreatedAtAscIdAsc(String status);
}
```

Query derivation cho phép Spring Data tạo SQL dựa trên mapping metadata và dialect. Đây thường là cách dễ chuyển database hơn nếu biểu thức được Spring Data hỗ trợ.

Với native query:

```java
@Query("SELECT * FROM customer WHERE status = :status ORDER BY created_at")
Flux<Customer> findActive(@Param("status") String status);
```

Tên bảng/cột, marker và biểu thức SQL phải phù hợp dialect. Named parameter được Spring Data xử lý, nhưng `SELECT *`, `ORDER BY`, hàm SQL hoặc cú pháp riêng vẫn có thể phụ thuộc database.

### 17.1. Tách query theo dialect khi cần

Nếu PostgreSQL cần `RETURNING` còn SQL Server cần `OUTPUT INSERTED...`, không ép hai cú pháp vào một native query dùng chung. Có thể:

- Dùng repository interface chung cho thao tác portable.
- Tạo custom repository implementation riêng cho từng database.
- Dùng adapter/strategy theo dialect để chọn câu SQL đã được kiểm soát.
- Viết migration và integration test riêng theo database.

Không xây dựng hệ thống dịch SQL tổng quát bằng replace chuỗi. Hãy giới hạn khác biệt ở lớp persistence adapter có test cụ thể.

## 18. Identifier quote và SQL injection

Bind parameter giúp bảo vệ **giá trị**. Nó không tự bảo vệ identifier được nối vào SQL.

Ví dụ nguy hiểm:

```java
String sql = "SELECT * FROM customer ORDER BY " + request.sortField();
```

Nếu `sortField` chứa biểu thức SQL ngoài ý muốn, câu query có thể bị thay đổi.

Hãy map input vào allowlist:

```java
enum CustomerSort {
    CREATED("created_at"),
    NAME("display_name"),
    EMAIL("email_address");

    private final String column;

    CustomerSort(String column) {
        this.column = column;
    }

    public String column() {
        return column;
    }
}
```

Sau đó chỉ dùng giá trị từ enum/allowlist trong identifier SQL. Nếu cần chọn chiều sort, dùng enum riêng cho `ASC`/`DESC`, không nối chuỗi tùy ý.

Quote identifier không thay thế allowlist. Một chuỗi độc hại được quote vẫn có thể trỏ tới identifier không được phép. Authorization và allowlist phải được áp dụng trước khi xây dựng query.

## 19. Khác biệt phân trang

Ngoài bind marker và quote identifier, cú pháp phân trang cũng có thể khác nhau.

PostgreSQL và MySQL thường hỗ trợ:

```sql
SELECT id, display_name
FROM customer
ORDER BY id
LIMIT :limit OFFSET :offset;
```

SQL Server thường dùng:

```sql
SELECT id, display_name
FROM customer
ORDER BY id
OFFSET @P0 ROWS FETCH NEXT @P1 ROWS ONLY;
```

Đây là ví dụ native SQL; marker cụ thể còn phụ thuộc driver. Khi dùng `Pageable`, `Sort` hoặc query derivation được Spring Data hỗ trợ, framework/dialect có thể sinh cú pháp phân trang phù hợp. Với native query viết tay, cần tự chọn cú pháp database mục tiêu.

Phân trang cần `ORDER BY` ổn định. Nếu không có thứ tự xác định, các trang có thể trùng hoặc thiếu hàng khi execution plan hoặc dữ liệu thay đổi.

## 20. Kiểu dữ liệu cũng ảnh hưởng tới bind

Bind marker chỉ là vị trí; giá trị Java vẫn phải được chuyển sang kiểu SQL mà driver/database hiểu.

| Ý nghĩa | PostgreSQL | MySQL | SQL Server |
| --- | --- | --- | --- |
| UUID | `UUID` | Thường lưu `BINARY(16)` hoặc `CHAR(36)` tùy thiết kế | `UNIQUEIDENTIFIER` |
| Tiền | `NUMERIC(p,s)` | `DECIMAL(p,s)` | `DECIMAL(p,s)` |
| Ngày giờ có offset | `TIMESTAMPTZ` | Thường dùng `TIMESTAMP`/`DATETIME` và quy ước UTC rõ ràng | `DATETIMEOFFSET` |
| Boolean | `BOOLEAN` | `BOOLEAN` là alias của `TINYINT(1)` trong nhiều cấu hình | `BIT` |
| JSON | `JSON`/`JSONB` | `JSON` | Có thể lưu `NVARCHAR` và dùng hàm JSON |

Bảng chỉ là định hướng. Mapping cụ thể phụ thuộc driver và converter của Spring Data.

### 20.1. UUID

PostgreSQL có kiểu UUID native. MySQL thường lưu UUID dưới dạng chuỗi hoặc binary; SQL Server có `UNIQUEIDENTIFIER`. Nếu cần chuyển database, xác định định dạng lưu trữ và converter rõ ràng.

### 20.2. Boolean

Một driver có thể encode Java `Boolean` sang kiểu boolean native, trong khi database khác biểu diễn bằng bit hoặc số. Hãy dùng kiểu SQL và converter được driver hỗ trợ.

### 20.3. Timestamp

`Instant`, `OffsetDateTime` và `LocalDateTime` mang ý nghĩa khác nhau. Đừng chỉ đổi tên kiểu SQL mà không xác định timezone semantics. Nếu lưu thời điểm tuyệt đối, chọn quy ước UTC nhất quán và test round-trip trên database mục tiêu.

## 21. Cấu hình dialect và ConnectionFactory

Spring Data R2DBC cần biết loại database để chọn dialect phù hợp. Thông thường dialect được xác định từ metadata của `ConnectionFactory`/driver.

Nếu tạo `ConnectionFactory` thủ công, hãy bảo đảm driver tương ứng có trong runtime dependency và URL dùng đúng scheme:

```text
r2dbc:postgresql://localhost:5432/app_db
r2dbc:mysql://localhost:3306/app_db
r2dbc:mssql://localhost:1433/app_db
```

Scheme cụ thể phải theo driver đang dùng. Không dùng JDBC URL như `jdbc:postgresql://...` để cấu hình R2DBC connection.

Khi có nhiều `ConnectionFactory`, repository/template cần được cấu hình với factory tương ứng. Nếu ứng dụng định tuyến giữa database có dialect khác nhau, lưu ý dialect gắn với template/repository configuration; routing connection ở runtime không tự bảo đảm query generator thay dialect theo từng target.

## 22. Kiểm tra query được tạo và lỗi bind

Khi gặp lỗi cú pháp hoặc bind, hãy xác định lỗi thuộc lớp nào:

1. SQL parser không chấp nhận marker.
2. Số marker và số giá trị bind không khớp.
3. Tên named parameter không khớp tên `.bind(...)` hoặc `@Param`.
4. Kiểu Java không encode được thành kiểu SQL.
5. Identifier cần quote nhưng query chưa quote đúng.
6. Tên bảng/cột không tồn tại hoặc sai chữ hoa/chữ thường.
7. Câu SQL dùng cú pháp riêng của database khác.
8. Parameter null chưa được bind với kiểu rõ ràng.

Một số lỗi điển hình:

| Lỗi | Nguyên nhân có thể có |
| --- | --- |
| Syntax error near `?` | Driver không chấp nhận marker của database khác |
| Parameter index out of range | Bind index không khớp số marker |
| No value specified for parameter | Thiếu bind cho marker trong SQL |
| Unknown column / invalid column | Sai identifier hoặc sai cách quote/case |
| Syntax error near `order` | Identifier trùng reserved keyword |
| Cannot bind null | Dùng `.bind(name, null)` thay vì `.bindNull(...)` |
| Type mismatch | Java type không tương thích SQL type/driver codec |

Trong phát triển, có thể bật log SQL phù hợp của Spring/driver để xem câu lệnh và thông tin lỗi. Tránh ghi password, token hoặc dữ liệu cá nhân vào log.

## 23. Kiểm thử trên từng hệ quản trị

Một query chạy với H2 không chứng minh query chạy đúng trên PostgreSQL hoặc MySQL. H2 có thể khác về reserved keywords, quoting, kiểu dữ liệu, generated key và cú pháp SQL.

Nếu production dùng PostgreSQL, integration test quan trọng nên chạy PostgreSQL thật, thường qua Testcontainers. Nếu sản phẩm hỗ trợ nhiều database, cần test riêng cho từng dialect/driver được hỗ trợ.

Ví dụ cấu trúc test:

```java
@Testcontainers
@SpringBootTest
class CustomerRepositoryPostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://" + postgres.getHost() + ":"
                        + postgres.getFirstMappedPort() + "/"
                        + postgres.getDatabaseName());
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }
}
```

Đây là khung cấu hình minh họa; test project cần dependency Testcontainers PostgreSQL và R2DBC PostgreSQL driver, đồng thời khởi tạo schema trước khi test.

Các test nên bao gồm:

- Named parameter được chuyển và bind đúng.
- Null parameter dùng `bindNull` đúng kiểu.
- Collection parameter trong `IN` được mở rộng đúng và xử lý danh sách rỗng.
- Identifier có tên bình thường và identifier cần quote hoạt động.
- Tên cột có chữ hoa/chữ thường được xử lý theo schema.
- Query không dùng reserved keyword ngoài ý muốn.
- `Sort`, `Pageable` hoặc pagination native hoạt động đúng.
- UUID, decimal, boolean và timestamp round-trip chính xác.
- Migration tạo đúng bảng, cột, index và constraint.

## 24. Những lỗi thường gặp khi chuyển hệ quản trị

| Triệu chứng | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| Query PostgreSQL dùng được nhưng MySQL lỗi | Dùng `$1` native marker hoặc cú pháp PostgreSQL | Dùng named parameter Spring hoặc viết query riêng cho MySQL |
| Query MySQL dùng `?` nhưng SQL Server lỗi | Marker native khác driver | Dùng `DatabaseClient` named parameter hoặc marker SQL Server đúng chuẩn |
| Tên bảng `order` không truy vấn được | Reserved keyword | Đổi tên thành `purchase_order` hoặc quote theo dialect |
| Bảng `"Customer"` không tìm thấy | PostgreSQL phân biệt identifier quoted case | Dùng đúng chữ hoa/chữ thường và quote nhất quán |
| Backtick lỗi trên PostgreSQL | Backtick là cú pháp MySQL | Dùng double quote theo PostgreSQL hoặc tên không cần quote |
| `"name"` thành identifier sai trên MySQL | Double quote có semantics khác theo SQL mode | Dùng backtick hoặc tên đơn giản không cần quote |
| Bind table name không hoạt động | Parameter marker chỉ bind giá trị | Dùng allowlist và identifier processing |
| `IN (:ids)` lỗi với list rỗng | SQL expansion tạo danh sách rỗng không hợp lệ | Xử lý collection rỗng trước khi gửi query |
| H2 test pass nhưng production fail | Khác dialect, keyword, type hoặc SQL syntax | Test với database production bằng Testcontainers |
| `bind(null)` lỗi | R2DBC cần khai báo kiểu null | Dùng `.bindNull(name, type)` |
| Chuyển MySQL sang PostgreSQL mất case | Quy tắc identifier folding khác nhau | Chuẩn hóa tên vật lý và migration schema |
| Routing giữa PostgreSQL và MySQL tạo SQL sai | Một repository/template không tự đổi dialect theo target | Tách template/repository adapter theo dialect |

## 25. Quy tắc thiết kế để giảm phụ thuộc dialect

Khi viết ứng dụng Spring Data R2DBC có khả năng chạy trên nhiều hệ quản trị:

1. Dùng query derivation hoặc API Spring Data cho thao tác CRUD phổ biến.
2. Dùng named parameter của `DatabaseClient` hoặc `@Query` thay vì tự viết marker native khi API hỗ trợ.
3. Không bind identifier; dùng tên cố định, allowlist và identifier processing phù hợp.
4. Đặt tên bảng/cột chữ thường, `snake_case`, tránh reserved keyword.
5. Nếu buộc phải dùng từ khóa làm identifier, quote theo đúng database và giữ nhất quán trong migration/query/mapping.
6. Dùng kiểu Java và SQL có quy ước rõ ràng cho UUID, decimal, timestamp, boolean và JSON.
7. Xử lý null bằng API bind null có kiểu.
8. Xử lý collection rỗng trước khi tạo điều kiện `IN`.
9. Tách native query đặc thù thành custom repository/adapter theo dialect.
10. Không coi H2 compatibility mode là bằng chứng tương thích hoàn toàn với database production.
11. Kiểm thử trên đúng R2DBC driver và phiên bản database được hỗ trợ.
12. Khi nâng cấp database, kiểm tra reserved keyword, identifier behavior và thay đổi driver.

## 26. Quy trình chẩn đoán query không portable

Khi query chạy trên database A nhưng lỗi trên database B, hãy lần lượt xác định:

1. Câu SQL do repository sinh hay do ứng dụng viết trực tiếp?
2. Marker là named parameter của Spring hay native marker của driver?
3. Driver đang dùng chấp nhận marker và kiểu bind nào?
4. Các tham số đã được bind đủ, đúng tên/index và đúng kiểu chưa?
5. Có tham số null cần `.bindNull(...)` không?
6. Có tên bảng/cột trùng reserved keyword không?
7. Identifier có được quote theo đúng dialect không?
8. Quy tắc case folding có khiến tên vật lý khác với tên query không?
9. Query có dùng hàm, toán tử, phân trang hoặc kiểu dữ liệu đặc thù không?
10. Cùng một template/repository có đang được dùng với nhiều dialect khác nhau không?
11. Test đã chạy trên database và driver thực tế chưa?

Phân loại đúng vấn đề giúp sửa ở đúng tầng: marker thuộc binding, quote thuộc identifier, keyword thuộc naming/schema, còn cú pháp native thuộc dialect của query.

Khác biệt ký hiệu bind, dấu quote identifier và reserved keyword là những nguyên nhân phổ biến khiến native SQL không portable giữa các hệ quản trị. Spring Data R2DBC và `DatabaseClient` giúp trừu tượng hóa một phần thông qua dialect và named parameter, nhưng không phải bộ dịch mọi SQL. Hãy dùng bind parameter cho giá trị, chọn identifier an toàn, quote theo đúng database khi cần và kiểm thử trên đúng driver/server để giữ mapping cùng query nhất quán.
