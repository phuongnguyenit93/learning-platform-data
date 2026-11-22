# Lỗi bind tham số, cú pháp SQL và định danh có dấu ngoặc

Khi dùng Spring Data R2DBC, lỗi truy vấn thường xuất hiện ở ba khu vực có liên quan nhưng cần chẩn đoán riêng: **bind tham số**, **cú pháp SQL** và **định danh được quote** (tên bảng, schema, cột, alias có dấu phân cách). Một câu SQL nhìn có vẻ hợp lệ vẫn có thể thất bại vì placeholder không đúng driver, tham số null được bind sai kiểu, tên cột là từ khóa dành riêng hoặc cách viết hoa/thường không khớp với identifier trong database.

Cách xử lý hiệu quả là tách câu SQL khỏi giá trị đầu vào, xác định database/driver đang thực thi, kiểm tra marker và kiểu dữ liệu, rồi đối chiếu quy tắc identifier của dialect. Không sửa bằng cách nối chuỗi dữ liệu người dùng vào SQL. Giá trị phải được bind; tên bảng/cột động phải được chọn từ allowlist và quote theo database.

## 1. Ba nhóm lỗi cần phân biệt

| Nhóm | Biểu hiện thường gặp | Nguyên nhân có thể |
|---|---|---|
| Bind tham số | Thiếu parameter, index ngoài phạm vi, lỗi convert type | Marker sai, thứ tự bind sai, thiếu bindNull hoặc sai kiểu |
| Cú pháp SQL | Syntax error, unexpected token, missing keyword | SQL sai dialect, dấu ngoặc, alias, keyword, dấu phẩy hoặc clause |
| Identifier quoting | Table/column not found, lỗi tên reserved word, khác biệt chữ hoa/thường | Identifier chưa quote, quote sai kiểu, schema/case không khớp |

Một lỗi có thể thuộc nhiều nhóm. Ví dụ câu SQL dùng tên cột order không được quote có thể bị parser hiểu là keyword; sau khi sửa quote, câu lệnh vẫn có thể lỗi nếu placeholder đang dùng cú pháp của driver khác.

Hãy bắt đầu từ exception gốc, SQLState/vendor code và SQL đã được tạo. Đừng chỉ nhìn message cuối cùng của controller vì tầng service có thể đã bọc lỗi thành một exception chung.

## 2. Bind parameter có tác dụng gì?

Bind parameter tách cấu trúc câu SQL khỏi giá trị dữ liệu. Database nhận câu lệnh có placeholder và các giá trị được truyền riêng qua driver.

Ví dụ:

~~~sql
SELECT id, full_name
FROM customer
WHERE email = :email
~~~

Giá trị email được bind riêng:

~~~java
databaseClient.sql("""
        SELECT id, full_name
        FROM customer
        WHERE email = :email
        """)
    .bind("email", email)
    .fetch()
    .one();
~~~

Lợi ích:

- Tránh nối chuỗi giá trị vào SQL.
- Giảm nguy cơ SQL injection đối với dữ liệu được bind.
- Driver truyền giá trị theo kiểu phù hợp thay vì biến mọi thứ thành text.
- Tách SQL template khỏi dữ liệu request.
- Có thể giúp database/driver tái sử dụng execution plan tùy implementation.

Bind parameter chỉ áp dụng cho **giá trị**, ví dụ email, ID, ngày tháng, số lượng hoặc trạng thái. Nó không thay thế được tên bảng, tên cột, từ khóa SQL hay toàn bộ một đoạn SQL.

## 3. Named parameter trong Spring DatabaseClient

Spring DatabaseClient hỗ trợ named parameter để mã nguồn không phụ thuộc trực tiếp vào marker native của từng driver. Với named parameter, câu SQL dùng dạng :name; framework mở rộng và chuyển đổi sang marker mà driver cần.

Ví dụ:

~~~java
public Mono<Customer> findByEmail(String email) {
    return databaseClient.sql("""
            SELECT id, full_name, email
            FROM customer
            WHERE email = :email
            """)
        .bind("email", email)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("full_name", String.class),
            row.get("email", String.class)
        ))
        .one();
}
~~~

Ở đây:

- :email là named marker trong SQL template.
- bind("email", email) cung cấp giá trị tương ứng.
- DatabaseClient chuyển named marker sang marker phù hợp với dialect/driver.
- .one() diễn đạt kết quả tối đa một hàng.

Tên parameter trong SQL và tên truyền vào bind phải khớp. Không cần thêm dấu hai chấm vào tên truyền cho bind.

### 3.1. Tránh nhầm named marker với marker native

Driver R2DBC có thể dùng cú pháp marker khác nhau. Ví dụ, PostgreSQL thường dùng $1, $2; một số driver dùng ? hoặc marker riêng.

Nếu dùng Spring DatabaseClient, nên chọn một phong cách nhất quán: viết named marker :name và để DatabaseClient chuyển đổi.

Nếu dùng trực tiếp R2DBC SPI Statement, phải dùng cú pháp marker mà driver hỗ trợ. Không mặc định mọi driver hiểu :name.

Ví dụ PostgreSQL native Statement:

~~~java
connection.createStatement("""
        SELECT id, full_name
        FROM customer
        WHERE email = $1
        """)
    .bind(0, email)
    .execute();
~~~

Trong ví dụ native này, $1 là placeholder thứ nhất của PostgreSQL, còn bind(0, email) dùng index zero-based của R2DBC SPI. Hai cách đánh số khác nhau không phải lỗi: placeholder SQL bắt đầu từ 1 trong cú pháp PostgreSQL, API bind index bắt đầu từ 0.

Không viết SQL dùng $1 nhưng lại gọi DatabaseClient.bind("email", ...) như thể hai cơ chế có thể tự kết hợp, trừ khi API/driver cụ thể đã được xác nhận hỗ trợ đúng cách.

### 3.2. Kiểm tra số lượng và tên parameter

Các lỗi phổ biến:

- SQL có :customerId nhưng code bind "id".
- SQL có hai placeholder nhưng chỉ bind một giá trị.
- SQL bị thay đổi trong một nhánh điều kiện nhưng danh sách bind không thay đổi tương ứng.
- Tên parameter bị viết sai chính tả hoặc khác chữ hoa/thường.
- Dùng positional index sai thứ tự khi tạo Statement thủ công.
- Dùng index 1 cho tham số đầu tiên trong API R2DBC SPI.

Với named parameter, tạo SQL và binding theo cùng một cấu trúc để tránh hai danh sách bị lệch nhau. Với native Statement, ghi rõ thứ tự parameter cạnh câu SQL và nhớ index bắt đầu từ 0 trong API bind của R2DBC SPI.

## 4. Bind null đúng cách

Reactive Streams không phát giá trị null, và R2DBC SPI cũng không cho phép dùng bind(index, null) hoặc bind(name, null) như một cách biểu diễn SQL NULL. Cần gọi bindNull và cung cấp Java type để driver biết kiểu của giá trị null.

Ví dụ với DatabaseClient:

~~~java
databaseClient.sql("""
        INSERT INTO customer (email, nickname)
        VALUES (:email, :nickname)
        """)
    .bind("email", email)
    .bindNull("nickname", String.class)
    .fetch()
    .rowsUpdated();
~~~

Ví dụ với R2DBC SPI:

~~~java
statement
    .bind(0, email)
    .bindNull(1, String.class);
~~~

Kiểu truyền vào bindNull quan trọng vì database cần biết SQL type phù hợp. Với UUID, LocalDate, LocalDateTime, OffsetDateTime, BigDecimal hoặc kiểu riêng của database, hãy chọn Java type mà driver hỗ trợ cho cột tương ứng.

### 4.1. Phân biệt null với không truyền parameter

Có ba trường hợp khác nhau:

1. Parameter có giá trị: bind giá trị đó.
2. Parameter có SQL NULL: bindNull với kiểu Java tương ứng.
3. Không có parameter trong câu SQL: không bind parameter đó.

Không truyền parameter không đồng nghĩa với bind SQL NULL. Nếu SQL có placeholder nhưng không được bind, statement thường lỗi khi execute.

### 4.2. Null trong điều kiện WHERE

Điều kiện:

~~~sql
WHERE nickname = :nickname
~~~

khi nickname được bind thành SQL NULL sẽ không trả về hàng có nickname NULL theo logic SQL ba giá trị. Biểu thức so sánh với NULL tạo UNKNOWN, không phải TRUE.

Nếu muốn tìm hàng có nickname null, hãy viết điều kiện riêng:

~~~sql
WHERE nickname IS NULL
~~~

Nếu request cho phép cả hai hành vi, xây dựng hai nhánh SQL có chủ đích hoặc dùng predicate phù hợp với dialect. Không kỳ vọng nickname = NULL hoạt động giống nickname IS NULL.

## 5. Bind kiểu dữ liệu đúng với cột

Driver cần chuyển Java value sang kiểu dữ liệu database. Một số lỗi phát sinh khi truyền kiểu không phù hợp:

- Truyền String cho cột UUID nhưng driver không hỗ trợ conversion đó.
- Truyền Integer cho cột BIGINT.
- Truyền LocalDateTime vào cột yêu cầu offset/time zone.
- Truyền JSON dưới dạng Java object nhưng chưa cấu hình codec/converter.
- Truyền null mà không khai báo type.
- Dùng BigDecimal có precision/scale vượt giới hạn cột.

Hãy dùng Java type phù hợp và kiểm tra mapping của driver. Không chuyển tất cả giá trị thành String chỉ để tránh lỗi bind; cách đó có thể làm mất type semantics, ảnh hưởng index hoặc khiến database phải cast ngầm.

### 5.1. UUID

Nếu database có cột UUID, ưu tiên dùng java.util.UUID khi driver hỗ trợ:

~~~java
.bind("id", UUID.fromString(idText))
~~~

Nếu bind String, việc chuyển sang UUID phụ thuộc driver và database. Hãy parse/validate ở tầng application và bind UUID typed.

### 5.2. Decimal và numeric

Dùng BigDecimal cho dữ liệu tiền hoặc số cần độ chính xác thập phân. Kiểm tra precision/scale của cột và quy tắc rounding nghiệp vụ.

Không dùng double để lưu giá trị tài chính chỉ vì driver chấp nhận kiểu đó. Một lỗi precision có thể không phát sinh SQL exception nhưng vẫn tạo dữ liệu sai.

### 5.3. Date/time

Chọn Java temporal type theo semantics của cột:

- LocalDate cho ngày không có thời gian.
- LocalTime cho giờ không có ngày.
- LocalDateTime cho timestamp không gắn offset.
- OffsetDateTime hoặc Instant cho thời điểm tuyệt đối khi driver/database mapping hỗ trợ phù hợp.

Đối chiếu timezone của database session, driver và ứng dụng. Lỗi lệch múi giờ không nhất thiết xuất hiện dưới dạng bind exception.

### 5.4. JSON và kiểu database riêng

JSON/JSONB, array, enum, geometry và các kiểu riêng có thể cần codec, converter hoặc driver-specific wrapper. Kiểm tra tài liệu driver trước khi bind.

Nếu cần SQL cast, viết cast theo dialect một cách tường minh:

~~~sql
INSERT INTO event_log (payload)
VALUES (CAST(:payload AS jsonb))
~~~

Ví dụ này dành cho PostgreSQL JSONB. Không dùng nguyên cú pháp cast của PostgreSQL cho mọi database.

## 6. Bind danh sách và điều kiện IN

Một truy vấn tìm nhiều ID thường có dạng:

~~~sql
SELECT id, full_name
FROM customer
WHERE id IN (:ids)
~~~

Với Spring DatabaseClient, named parameter expansion có thể mở rộng collection thành các marker phù hợp. Tuy nhiên, cách xử lý collection phụ thuộc API, dialect và driver; hãy kiểm thử trên database thật của ứng dụng.

Nếu dùng PostgreSQL array, có thể có lựa chọn dùng ANY với array parameter, nhưng cách tạo và bind array phụ thuộc driver:

~~~sql
WHERE id = ANY(:ids)
~~~

Không giả định List Java luôn được chuyển thành SQL array. IN expansion và array binding là hai cơ chế khác nhau.

### 6.1. Danh sách rỗng

IN với danh sách rỗng có thể tạo SQL không hợp lệ hoặc không được hỗ trợ tùy cơ chế expansion. Hãy xử lý trường hợp rỗng trước khi chạy query.

Ví dụ:

~~~java
public Flux<Customer> findByIds(Collection<Long> ids) {
    if (ids.isEmpty()) {
        return Flux.empty();
    }

    return databaseClient.sql("""
            SELECT id, full_name
            FROM customer
            WHERE id IN (:ids)
            """)
        .bind("ids", ids)
        .map(customerMapper)
        .all();
}
~~~

Đảm bảo mapper phù hợp với API DatabaseClient thực tế của dự án. Ý chính là không gửi IN () khi danh sách không có phần tử.

### 6.2. Giới hạn kích thước danh sách

Một danh sách hàng chục nghìn ID có thể tạo câu SQL rất lớn, vượt giới hạn số parameter hoặc làm tăng chi phí parse/plan.

Hãy giới hạn kích thước đầu vào, chia batch khi cần hoặc dùng cơ chế array/table-valued parameter phù hợp với database. Không cho client tùy ý gửi collection khổng lồ.

## 7. Lỗi bind do thứ tự parameter

Khi dùng R2DBC SPI trực tiếp, positional binding dựa trên thứ tự marker trong SQL.

Ví dụ:

~~~java
Statement statement = connection.createStatement("""
    UPDATE customer
    SET full_name = $1, active = $2
    WHERE id = $3
    """);

statement
    .bind(0, fullName)
    .bind(1, active)
    .bind(2, id);
~~~

Nếu bind nhầm thứ tự, câu SQL vẫn có thể execute nhưng cập nhật sai cột hoặc phát lỗi type conversion.

Đặt tên biến có ý nghĩa và bind theo thứ tự được ghi rõ. Nếu câu SQL được xây dựng động, hãy tạo danh sách parameter cùng lúc với SQL thay vì tự duy trì hai mảng độc lập.

### 7.1. Không dùng cùng index cho nhiều giá trị khác nhau

Mỗi vị trí marker phải được bind với giá trị phù hợp. Nếu Statement có ba marker mà code chỉ bind hai vị trí, execute sẽ thất bại. Nếu bind lại một vị trí, giá trị cuối cùng có thể thay thế giá trị trước tùy API/driver.

Hãy xác nhận số marker, index và type trước khi execute.

## 8. Cú pháp SQL phụ thuộc database dialect

Spring Data R2DBC không làm cho SQL trở thành hoàn toàn portable. Cú pháp cụ thể vẫn phụ thuộc database.

Các khác biệt thường gặp:

- Identifier quote: dấu nháy kép, backtick hoặc ngoặc vuông.
- Pagination: LIMIT/OFFSET, OFFSET/FETCH hoặc cú pháp riêng.
- Upsert: ON CONFLICT, ON DUPLICATE KEY hoặc MERGE.
- Generated key/returning: RETURNING hoặc cơ chế khác.
- JSON operator và cast.
- Boolean literal.
- Date/time function.
- Sequence/identity.
- Locking syntax như FOR UPDATE.
- CTE, window function và recursive query.

Một query chạy trên PostgreSQL có thể không chạy trên MySQL hoặc SQL Server dù cả hai đều được truy cập qua R2DBC.

### 8.1. Kiểm tra dialect đang được dùng

Spring Data Relational/R2DBC có dialect abstraction để hỗ trợ việc tạo SQL cho database cụ thể. Nếu dùng repository derivation hoặc R2dbcEntityTemplate, framework có thể tạo một phần SQL dựa trên dialect.

Khi viết SQL native qua @Query hoặc DatabaseClient, phần SQL do ứng dụng viết vẫn phải tuân theo dialect của database. Không giả định dialect sẽ sửa mọi câu SQL thủ công.

Nếu dùng custom ConnectionFactory hoặc nhiều database, xác nhận repository/template được gắn đúng dialect và ConnectionFactory.

### 8.2. Không trộn cú pháp từ nhiều database

Ví dụ các cú pháp pagination:

~~~sql
-- PostgreSQL / MySQL
SELECT id, name
FROM customer
ORDER BY id
LIMIT :size OFFSET :offset
~~~

~~~sql
-- SQL Server (một dạng phổ biến)
SELECT id, name
FROM customer
ORDER BY id
OFFSET :offset ROWS
FETCH NEXT :size ROWS ONLY
~~~

Đây là ví dụ theo dialect, không phải cú pháp dùng chung. Cần kiểm tra version server và driver cụ thể.

## 9. Identifier là gì và vì sao phải quote?

Identifier là tên đối tượng SQL: database, schema, table, column, index, sequence, alias hoặc function. Identifier không phải giá trị dữ liệu.

Ví dụ:

~~~sql
SELECT customer_id
FROM sales.customer
WHERE customer_id = :id
~~~

Trong đó sales là schema, customer là table, customer_id là column, còn :id là value parameter.

Database có quy tắc riêng cho identifier:

- Từ khóa dành riêng có thể không được dùng làm tên table/column nếu không quote.
- Chữ hoa/thường có thể được chuẩn hóa khác nhau.
- Tên có dấu cách hoặc ký tự đặc biệt thường cần quote.
- Quote sai loại có thể khiến parser hiểu sai hoặc tìm object khác.

### 9.1. Từ khóa dành riêng

Tên như order, user, group, select hoặc key có thể là reserved word hoặc từ khóa đặc biệt trong một số database/version.

Ví dụ:

~~~sql
SELECT id, status
FROM order
~~~

Có thể lỗi vì order là từ khóa trong database cụ thể. Cách tốt nhất là chọn tên tránh reserved word, ví dụ orders hoặc purchase_order.

Nếu schema hiện tại không thể đổi, hãy quote identifier đúng theo database.

### 9.2. Dấu quote không giống nhau giữa các database

| Database | Identifier delimiter thường gặp | Ghi chú |
|---|---|---|
| PostgreSQL | "name" | Quoted identifier giữ nguyên chữ hoa/thường |
| MySQL | \`name\` | Backtick là cách thông dụng; double quote phụ thuộc SQL mode |
| SQL Server | [name] hoặc "name" | Double quote phụ thuộc QUOTED_IDENTIFIER |
| H2 | "name" | Hành vi gần SQL chuẩn nhưng vẫn cần kiểm tra mode |

Không sao chép dấu quote của database này sang database khác. MySQL dùng backtick phổ biến; PostgreSQL dùng double quote; SQL Server hỗ trợ ngoặc vuông và có chế độ xử lý double quote riêng.

### 9.3. Identifier được quote có thể phân biệt chữ hoa/thường

PostgreSQL chuyển identifier không quote về chữ thường. Ví dụ:

~~~sql
SELECT id FROM Customer
~~~

identifier Customer không quote được chuẩn hóa thành customer.

Trong khi:

~~~sql
SELECT id FROM "Customer"
~~~

đòi hỏi object có đúng tên phân biệt hoa/thường là Customer.

Nếu table được tạo bằng quoted mixed-case identifier, query dùng chữ thường không quote có thể báo relation/table not found. Đây là lỗi tên object, không phải lỗi bind parameter.

Quy tắc của MySQL và SQL Server khác PostgreSQL, đặc biệt với table name case sensitivity, filesystem và collation. Luôn đối chiếu database đang dùng.

## 10. Quote identifier trong Spring Data Relational

Spring Data Relational sử dụng metadata về table và column để tạo SQL cho repository/template. Mapping annotation và NamingStrategy quyết định identifier nào được dùng.

Ví dụ:

~~~java
@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    @Column("order_status") String status
) {}
~~~

Dùng tên table/column rõ ràng giúp tránh phụ thuộc vào naming convention ngầm. Nếu tên object là reserved word hoặc cần giữ nguyên case, cần xác định cách Spring Data và dialect render identifier cho phiên bản đang dùng.

Spring Data Relational có abstraction SqlIdentifier để biểu diễn identifier có thông tin quote. Trong custom mapping/naming strategy, có thể dùng identifier quoted/unquoted theo API của phiên bản Spring Data. Hãy kiểm tra package/API đúng version; không giả định một string annotation tự động được quote giống nhau trên mọi database.

### 10.1. Tránh đặt tên object là reserved word

Nếu có quyền thiết kế schema, ưu tiên tên không cần quote:

- order → purchase_order
- user → app_user
- group → customer_group
- key → external_key

Tên đơn giản, nhất quán, snake_case thường giảm lỗi khi chuyển dialect, viết migration và đọc query.

### 10.2. Khi phải dùng tên có dấu cách hoặc ký tự đặc biệt

Nếu schema legacy có tên như Order Detail hoặc tên chứa dấu gạch ngang, cần quote chính xác và test trên database thật.

Không tự nối dấu quote bằng string thủ công nếu có abstraction identifier của Spring Data/dialect. Việc escape dấu quote bên trong identifier cũng khác nhau theo database.

## 11. Không thể bind tên table hoặc column bằng value parameter

Đoạn sau không chọn cột động:

~~~sql
SELECT id, name
FROM customer
ORDER BY :sortColumn
~~~

:sortColumn là một value parameter. Database hiểu nó như một giá trị literal, không phải tên column. Tương tự, không thể dùng bind parameter cho table name, schema name, column name, ASC/DESC, operator, một đoạn WHERE/ORDER BY tùy ý, tên function hoặc keyword.

### 11.1. Dùng allowlist cho identifier động

Nếu API cho phép sort theo nhiều trường, ánh xạ input thành các lựa chọn cố định:

~~~java
String orderBy = switch (sortField) {
    case "name" -> "full_name";
    case "createdAt" -> "created_at";
    case "price" -> "price";
    default -> throw new IllegalArgumentException(
        "Unsupported sort field"
    );
};

String direction = descending ? "DESC" : "ASC";

String sql = """
    SELECT id, full_name, created_at, price
    FROM product
    ORDER BY
    """ + orderBy + " " + direction;
~~~

Ví dụ này chỉ nối các fragment đến từ allowlist cố định do ứng dụng kiểm soát. Không nối trực tiếp sortField hoặc direction nguyên bản từ request.

Giá trị filter vẫn bind riêng:

~~~java
databaseClient.sql(sql + " WHERE category = :category")
    .bind("category", category);
~~~

Tốt hơn nữa, dùng enum hoặc cấu trúc query builder để không truyền chuỗi tùy ý qua nhiều tầng.

### 11.2. Quote không thay thế allowlist

Quote một identifier do user cung cấp không đủ để bảo vệ mọi tình huống. Cần kiểm tra identifier có nằm trong danh sách cột/table được phép hay không, sau đó quote theo dialect.

Không cho client gửi một đoạn SQL như sortExpression hoặc filterExpression rồi nối vào query.

## 12. SQL injection và nối chuỗi

Lỗi nguy hiểm là ghép trực tiếp giá trị request vào SQL:

~~~java
String sql = "SELECT * FROM customer WHERE email = '"
    + email
    + "'";
~~~

Nếu email chứa ký tự SQL đặc biệt, cấu trúc câu lệnh có thể bị thay đổi. Dùng bind parameter:

~~~java
databaseClient.sql("""
        SELECT *
        FROM customer
        WHERE email = :email
        """)
    .bind("email", email)
    .fetch()
    .all();
~~~

Bind parameter giúp database xem email là dữ liệu, không phải SQL syntax.

Tuy nhiên, bind parameter không bảo vệ phần SQL được nối từ identifier hoặc fragment động. Những phần đó cần allowlist và quote đúng dialect.

## 13. Lỗi cú pháp do dấu ngoặc và cấu trúc query

Dấu ngoặc đơn, dấu ngoặc kép và dấu quote identifier có ý nghĩa khác nhau:

- Parentheses () nhóm biểu thức, function argument, subquery hoặc IN list.
- Single quote '...' tạo string literal.
- Double quote "..." thường quote identifier trong PostgreSQL và SQL chuẩn.
- Backtick quote identifier trong MySQL.
- Square bracket thường quote identifier trong SQL Server.

Một số lỗi thường gặp:

- Thiếu dấu đóng ngoặc trong nested query.
- Dùng double quote cho string thay vì single quote.
- Dùng single quote quanh tên column, khiến database hiểu thành string literal.
- Dùng dấu quote của dialect khác.
- Quote alias nhưng tham chiếu alias với case khác.
- Đặt dấu phẩy thừa trước FROM hoặc sau SELECT.
- Đặt WHERE sau ORDER BY.
- Dùng LIMIT ở database không hỗ trợ cú pháp đó.
- Thiếu schema qualification hoặc dùng sai schema.

Ví dụ sai:

~~~sql
SELECT "full_name"
FROM customer
WHERE email = "alice@example.com"
~~~

Trên PostgreSQL, "alice@example.com" là quoted identifier, không phải string. Viết đúng:

~~~sql
SELECT "full_name"
FROM customer
WHERE email = 'alice@example.com'
~~~

Nếu tên column thực tế là full_name lowercase không quote, có thể viết full_name không dấu quote. Dùng quote nhất quán theo schema và dialect.

## 14. Schema qualification và alias

Khi nhiều schema có table trùng tên, cần chỉ rõ schema:

~~~sql
SELECT c.id, c.full_name
FROM sales.customer AS c
WHERE c.id = :id
~~~

Lỗi có thể xảy ra khi search path/schema mặc định khác giữa local và production, table tồn tại trong schema khác, migration tạo object ở schema khác với query, alias được khai báo nhưng tham chiếu sai, hoặc column trùng tên giữa nhiều table nhưng không được qualify.

Dùng alias ngắn và qualify column khi query join nhiều bảng:

~~~sql
SELECT c.id, o.id AS order_id
FROM customer AS c
JOIN purchase_order AS o
  ON o.customer_id = c.id
WHERE c.id = :customerId
~~~

Nếu identifier cần quote, quote từng thành phần theo dialect. Không quote cả chuỗi sales.customer như một identifier đơn nếu ý định là schema sales và table customer; cách đó có thể tìm một table literal có dấu chấm trong tên.

## 15. Cú pháp PostgreSQL đặc thù và named parameter

PostgreSQL có một số cú pháp dễ gây nhầm khi viết query qua abstraction named parameter:

- Native bind marker $1, $2.
- Cast bằng ::type hoặc CAST(value AS type).
- JSON operators như ->, ->>, @> và ? tùy operator.
- Array và ANY.
- Quoted identifier bằng double quote.

Khi dùng Spring DatabaseClient named parameters, dùng :name cho value parameter và kiểm tra parser/driver với các toán tử chứa ký tự đặc biệt. Nếu câu SQL có dấu hai chấm thuộc cú pháp khác hoặc chuỗi literal, hãy xem cách NamedParameterExpander của phiên bản framework xử lý; có thể dùng dạng CAST(:value AS type) để rõ ràng hơn thay vì viết cast shorthand gây nhầm parser.

Không tự thay :name bằng $1 nếu DatabaseClient đang quản lý named parameter expansion. Nếu dùng raw R2DBC Statement thì viết marker native của driver.

## 16. Chẩn đoán exception và SQLState

Khi query lỗi, giữ lại nguyên nhân gốc. Các lớp exception của Spring/driver có thể cho biết lỗi thuộc cú pháp, binding, data integrity, connection hay resource.

Thông tin nên thu thập:

- SQL template đã loại bỏ dữ liệu nhạy cảm.
- Tên và kiểu Java của các parameter.
- Database engine/version.
- Driver và R2DBC SPI version.
- SQLState hoặc vendor error code.
- Exception gốc và cause chain.
- Repository/service method gọi query.
- Có transaction đang mở hay không.
- Query chạy trực tiếp trên database client có lỗi tương tự không.

Không log password, token, email cá nhân hoặc payload nhạy cảm chỉ để debug bind. Có thể log tên parameter và Java type, ví dụ customerId: Long, createdAt: OffsetDateTime, mà không log value.

### 16.1. SQLState

SQLState là mã phân loại lỗi theo chuẩn/driver. Nhiều lỗi syntax hoặc access rule thuộc nhóm class 42, nhưng mã cụ thể phụ thuộc database.

Ví dụ PostgreSQL:

| SQLState | Ý nghĩa thường gặp |
|---|---|
| 42601 | Syntax error |
| 42703 | Undefined column |
| 42P01 | Undefined table/relation |
| 42804 | Datatype mismatch |

Không áp dụng các mã PostgreSQL cho mọi database. Lấy mã từ exception driver và đối chiếu tài liệu vendor.

### 16.2. Phân biệt lỗi SQL với lỗi kết nối

Nếu connection pool không cấp được connection, query có thể chưa hề tới database. Không nên xử lý connection timeout như syntax error.

Một số dấu hiệu:

- SQLState/vendor syntax code: database đã nhận và từ chối câu SQL.
- Authentication failure: kết nối không được xác thực.
- Acquire timeout: pool không cấp connection trong thời gian quy định.
- Network reset: connection bị ngắt giữa chừng.
- Bind/type error: statement không thể bind hoặc database từ chối kiểu dữ liệu.

Phân loại đúng giúp tránh sửa SQL khi nguyên nhân thật là pool hoặc network.

## 17. Quy trình cô lập lỗi

Khi một repository method thất bại, thực hiện theo trình tự:

1. Lấy exception gốc và SQLState/vendor code.
2. Xác định database, server version, driver và SPI đang chạy.
3. Tách SQL template khỏi parameter values.
4. Kiểm tra marker style và số lượng parameter.
5. Kiểm tra tên bind và thứ tự positional index.
6. Kiểm tra null được bind bằng bindNull và đúng Java type.
7. Kiểm tra kiểu Java so với kiểu cột.
8. Thay giá trị thật bằng dữ liệu test an toàn và chạy SQL trực tiếp trên cùng database.
9. Quote reserved identifier theo đúng dialect, kiểm tra case và schema.
10. Kiểm tra SQL fragment động có đến từ allowlist không.
11. Tạo integration test tái hiện lỗi qua R2DBC driver.
12. Chỉ sửa phần gây lỗi và giữ test regression cho case đó.

Khi chạy SQL thủ công, nhớ rằng marker native có thể khác named marker trong DatabaseClient. Nếu copy SQL template :name vào công cụ database, cần thay marker bằng literal test hoặc marker native theo đúng cách, không coi đó là cùng một cú pháp.

## 18. Kiểm thử binding và identifier trên database thật

Unit test với mock có thể xác nhận service gọi repository, nhưng không kiểm tra SQL parser, driver marker, quoting hay type mapping.

Nên có integration test trên database/driver tương ứng production, ví dụ dùng Testcontainers.

Các trường hợp nên kiểm tra:

- String, numeric, UUID, date/time và boolean binding.
- SQL NULL bằng bindNull.
- Null trong điều kiện WHERE.
- Danh sách rỗng và danh sách nhiều phần tử cho IN.
- Reserved word trong table/column.
- Identifier có mixed case.
- Schema qualification và alias trong JOIN.
- Tên có dấu cách hoặc ký tự đặc biệt nếu schema legacy có.
- Sort field được chọn từ allowlist.
- SQL injection payload được xử lý như value.
- Query native và query do Spring Data sinh ra.
- Mapping của kết quả về Java type.

### 18.1. Ví dụ StepVerifier

~~~java
StepVerifier.create(repository.findByEmail("alice@example.com"))
    .expectNextMatches(customer ->
        customer.email().equals("alice@example.com")
    )
    .verifyComplete();
~~~

Với trường hợp không tìm thấy:

~~~java
StepVerifier.create(repository.findByEmail("missing@example.com"))
    .verifyComplete();
~~~

Với SQL NULL, hãy tạo fixture có cột nullable và xác nhận truy vấn IS NULL trả đúng hàng. Đừng dùng email thật trong log hoặc test report.

### 18.2. Kiểm thử identifier quote

Nếu schema có reserved word hoặc mixed-case name, tạo migration test tạo đúng identifier đó rồi thực hiện query qua R2DBC. Test phải chạy bằng cùng database engine và mode như production; H2 compatibility mode không luôn tái hiện quy tắc quoting của PostgreSQL/MySQL/SQL Server.

## 19. Dùng log SQL một cách có kiểm soát

Trong môi trường development/test, có thể bật logging phù hợp để xem SQL template hoặc thông tin driver. Tên logger và mức log phụ thuộc phiên bản Spring Framework, Spring Data và driver.

Không bật verbose SQL/bind logging trong production một cách tùy tiện vì giá trị bind có thể chứa thông tin cá nhân, token hoặc dữ liệu nghiệp vụ nhạy cảm.

Một log chẩn đoán hữu ích thường ghi query name hoặc repository method, datasource alias, SQL template đã làm sạch, parameter names và Java types, duration, số rows updated và SQLState/vendor code khi lỗi.

Không cần ghi mọi parameter value. Nếu cần tái hiện, dùng dữ liệu synthetic trong test.

## 20. Những lỗi thường gặp

**Dùng marker của driver khác.** DatabaseClient có thể dịch named marker; raw Statement cần marker native. Chọn một cơ chế nhất quán.

**Nhầm index bind.** R2DBC SPI dùng index zero-based trong bind(int, value). Đừng bắt đầu từ 1 chỉ vì PostgreSQL placeholder hiển thị $1.

**Bind null bằng bind.** Dùng bindNull(index/name, JavaType).

**Dùng = NULL.** SQL cần IS NULL để kiểm tra giá trị null.

**Bind tên cột bằng parameter.** Parameter là value, không phải identifier. Dùng allowlist cho tên cột động.

**Nối input vào SQL.** Dễ tạo SQL injection. Bind mọi value và allowlist mọi identifier/fragment động.

**Dùng quote sai dialect.** Double quote, backtick và square bracket không thay thế cho nhau trong mọi database.

**Không để ý case của quoted identifier.** PostgreSQL phân biệt quoted mixed-case với unquoted lowercase. Kiểm tra tên object thật trong schema.

**Dùng reserved word làm tên object.** Ưu tiên đổi tên; nếu không thể, quote đúng dialect và test mapping.

**Truy vấn sai schema.** Qualify schema/table hoặc cấu hình search path rõ ràng.

**Dùng IN với danh sách rỗng.** Xử lý trước khi chạy query và giới hạn kích thước danh sách.

**Chỉ test bằng mock/H2.** Driver và database production có thể xử lý marker, type và quote khác. Dùng integration test đúng engine.

## 21. Nguyên tắc thiết kế

- Dùng named parameters qua Spring DatabaseClient khi phù hợp và để framework chuyển marker theo dialect.
- Với raw R2DBC Statement, dùng marker native của driver.
- Nhớ bind index trong R2DBC SPI bắt đầu từ 0.
- Không bind null bằng bind; dùng bindNull với Java type rõ ràng.
- Phân biệt SQL NULL với parameter không được bind và với predicate IS NULL.
- Bind mọi giá trị đầu vào; không nối giá trị user vào SQL.
- Không dùng value parameter để thay tên table, schema, column hoặc SQL keyword.
- Chọn identifier động từ allowlist và quote theo dialect.
- Tránh reserved word, mixed-case và tên có ký tự đặc biệt nếu có thể thiết kế schema.
- Kiểm tra schema qualification, alias, case và naming strategy.
- Xác nhận SQL syntax theo database server/version thực tế.
- Đối chiếu Java type với database column type và driver mapping.
- Xử lý collection rỗng, giới hạn batch và test IN expansion.
- Giữ SQLState, vendor code và cause chain để chẩn đoán.
- Không log bind values hoặc credentials nhạy cảm.
- Dùng integration test với đúng R2DBC driver và database engine.

## 22. Ghi nhớ

Lỗi bind tham số thường bắt nguồn từ marker không đúng driver, tên/index bị lệch, null không được bind bằng bindNull hoặc Java type không tương thích với cột. Lỗi cú pháp SQL cần được đối chiếu với dialect và phiên bản database. Lỗi identifier thường liên quan đến reserved word, dấu quote, chữ hoa/thường hoặc schema không đúng.

Với Spring DatabaseClient, named parameter giúp tách value khỏi SQL và chuyển marker theo driver. Với R2DBC SPI trực tiếp, phải dùng marker native và nhớ index zero-based. Identifier không thể bind như value; tên động phải được allowlist và quote theo database. Hãy chẩn đoán bằng exception gốc, SQLState, kiểu parameter và integration test trên database thật để sửa đúng nguyên nhân mà không tạo lỗ hổng SQL injection.

