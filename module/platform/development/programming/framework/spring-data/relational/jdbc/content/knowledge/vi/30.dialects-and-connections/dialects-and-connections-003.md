# Khác biệt quoting, limit/offset, generated keys và kiểu dữ liệu

Spring Data JDBC hỗ trợ nhiều hệ quản trị cơ sở dữ liệu thông qua abstraction gọi là **Dialect**. Dialect mô tả những khác biệt SQL và JDBC mà framework cần biết, chẳng hạn cách quote identifier, cách giới hạn số hàng, cách lấy giá trị ID được database sinh và một số khả năng kiểu dữ liệu.

Nhờ dialect, repository và JdbcAggregateTemplate có thể tạo SQL phù hợp với database đang cấu hình mà không buộc application code phải tự viết mọi cú pháp riêng. Tuy vậy, dialect không biến SQL tùy chỉnh thành SQL đa nền tảng. Khi viết câu lệnh trong @Query hoặc JdbcTemplate, lập trình viên vẫn phải dùng cú pháp identifier, pagination, generated key và kiểu dữ liệu phù hợp với DBMS/driver thực tế.

Bài này giải thích bốn khác biệt thường gây lỗi khi chuyển database hoặc thay JDBC driver: **quoting và quy tắc chữ hoa/thường của identifier; LIMIT/OFFSET; generated keys; và mapping kiểu dữ liệu**.

## 1. Dialect là gì?

Dialect là tập hợp quy tắc SQL/JDBC dành cho một hệ quản trị cụ thể. Spring Data Relational dùng dialect để tạo câu lệnh và ánh xạ các tính năng mà SQL giữa các database không hoàn toàn giống nhau.

Ví dụ, các database có thể khác nhau ở:

- Ký tự dùng để quote tên bảng/cột.
- Cách chuẩn hóa identifier không quote thành chữ hoa hoặc chữ thường.
- Cú pháp giới hạn số hàng và bỏ qua hàng.
- Cách trả về ID vừa được sinh sau INSERT.
- Hỗ trợ sequence, identity column, generated columns.
- Kiểu dữ liệu như UUID, JSON, array, enum, boolean và timestamp.
- Khả năng khóa hàng, trả về hàng sau INSERT/UPDATE hoặc các tính năng đặc thù khác.

Trong Spring Data JDBC, dialect được sử dụng bởi các thành phần tạo SQL và mapping. Repository CRUD và JdbcAggregateTemplate có thể dựa trên dialect để chọn cú pháp phù hợp.

~~~mermaid
flowchart TD
    A[Repository hoặc JdbcAggregateTemplate] --> B[Spring Data Relational mapping]
    B --> C[Dialect của database]
    C --> D[SQL identifier processing]
    C --> E[Pagination và generated key strategy]
    C --> F[JDBC type và converter support]
    D --> G[JDBC driver]
    E --> G
    F --> G
    G --> H[(Database)]
~~~

Dialect không phải là một cấu hình thay thế JDBC driver. Driver vẫn chịu trách nhiệm thực thi JDBC API, chuyển kiểu dữ liệu và giao tiếp với database. Dialect cung cấp cho Spring Data những quy tắc cần thiết để tạo SQL tương thích.

## 2. Dialect được chọn theo database như thế nào?

Trong ứng dụng Spring Boot, DataSource thường được cấu hình từ URL, driver class và thông tin kết nối. Spring Data JDBC dùng database metadata và các dialect được hỗ trợ để chọn cách xử lý phù hợp.

Ví dụ cấu hình kết nối PostgreSQL:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: app
    password: secret
~~~

Ví dụ cấu hình H2 cho môi trường thử nghiệm:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:shop;DB_CLOSE_DELAY=-1
    username: sa
    password:
~~~

Ứng dụng không nên hard-code giả định rằng SQL được tạo cho H2 sẽ luôn chạy giống hệt trên PostgreSQL, MySQL, SQL Server hoặc Oracle. Khi đổi URL/driver, dialect và một số hành vi JDBC cũng có thể thay đổi.

Spring Data Relational có các implementation dialect cho những database được hỗ trợ. Với database hoặc JDBC driver mới chưa được nhận diện, cần kiểm tra phiên bản Spring Data Relational, khả năng dialect hiện có và hướng mở rộng được hỗ trợ ở phiên bản đó. Không nên chỉ đổi driver rồi giả định mọi cú pháp đặc thù đã được xử lý.

### Kiểm tra database và driver đang chạy

JDBC DatabaseMetaData cho biết thông tin môi trường kết nối:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductName());
    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());
    System.out.println(metadata.getIdentifierQuoteString());
}
~~~

Thông tin này hữu ích khi debug môi trường khác nhau. Hãy lưu ý connection trong ví dụ được mở trực tiếp và phải được đóng; trong code đang chạy transaction, không lấy một connection độc lập để suy luận trạng thái của transaction hiện tại.

## 3. Identifier là gì và vì sao cần quoting?

Identifier là tên đối tượng trong SQL, ví dụ:

- Tên bảng: customers, purchase_orders.
- Tên cột: id, created_at, display_name.
- Tên schema, sequence, index hoặc alias.

Identifier khác với **value**. Value là dữ liệu được truyền vào điều kiện, ví dụ email, trạng thái hoặc ID.

Ví dụ:

~~~sql
SELECT id, display_name
FROM customers
WHERE email = ?;
~~~

Trong câu lệnh trên:

- customers, id, display_name và email là identifier.
- Giá trị email được truyền qua dấu hỏi là value.

Bind parameter dùng để truyền value, không dùng để thay thế identifier. Ví dụ sau không có nghĩa là chọn bảng theo giá trị tham số:

~~~sql
SELECT * FROM ?;
~~~

Nếu tên bảng hoặc cột cần lựa chọn động, phải ánh xạ lựa chọn đầu vào sang danh sách identifier được cho phép rồi tạo SQL phù hợp. Không nối trực tiếp identifier do người dùng gửi vào câu SQL.

### Identifier quoting

Quoting là đặt identifier trong ký tự phân cách để database hiểu tên đó là một identifier chính xác, đặc biệt khi tên chứa chữ hoa/thường có ý nghĩa, dấu cách hoặc trùng keyword.

Một số kiểu quoting thường gặp:

| Database / hệ SQL | Ký tự quote identifier thường dùng | Ví dụ |
|---|---|---|
| PostgreSQL | Dấu nháy kép | "Order" |
| H2 | Dấu nháy kép | "Order" |
| Oracle | Dấu nháy kép | "Order" |
| MySQL | Backtick | `order` |
| MariaDB | Backtick | `order` |
| SQL Server | Dấu ngoặc vuông; dấu nháy kép khi cấu hình phù hợp | [Order] |

Cú pháp chính xác phụ thuộc DBMS và cấu hình. Không nên lấy một câu SQL có backtick từ MySQL rồi dùng nguyên xi trên PostgreSQL.

## 4. Reserved word và tên bảng/cột dễ gây xung đột

Một số từ là keyword hoặc reserved word trong SQL. Ví dụ các tên như order, user, group, rank hoặc value có thể gây xung đột tùy database và phiên bản.

Ví dụ schema dùng tên bảng order:

~~~sql
CREATE TABLE order (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30)
);
~~~

Câu lệnh có thể bị parser từ chối vì ORDER là keyword. Có thể quote identifier theo cú pháp DBMS:

~~~sql
CREATE TABLE "order" (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30)
);
~~~

Nhưng câu lệnh trên chỉ là ví dụ theo hệ thống hỗ trợ dấu nháy kép. Với MySQL, cách quote thông dụng là:

~~~sql
CREATE TABLE `order` (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30)
);
~~~

Tên tránh keyword thường dễ bảo trì hơn. Chẳng hạn dùng purchase_orders thay cho order giúp giảm nhu cầu quote và làm schema dễ đọc hơn.

Nếu bảng/cột đã tồn tại với tên trùng keyword, cần thống nhất cách quote trong migration, SQL tùy chỉnh, view, trigger và code truy vấn.

## 5. Quy tắc chữ hoa/thường của identifier

Database không thống nhất cách xử lý identifier không quote.

Một số khác biệt thường gặp:

- PostgreSQL chuyển identifier không quote thành chữ thường.
- Oracle thường chuẩn hóa identifier không quote thành chữ hoa.
- SQL Server thường phân biệt tên theo collation và cấu hình.
- MySQL có các quy tắc riêng cho tên database/table, có thể chịu ảnh hưởng hệ điều hành và cấu hình lower_case_table_names; column name thường không phân biệt hoa/thường.

Ví dụ trên PostgreSQL:

~~~sql
CREATE TABLE Customer (
    id BIGINT PRIMARY KEY
);
~~~

Tên không quote được chuẩn hóa thành customer. Trong khi:

~~~sql
CREATE TABLE "Customer" (
    id BIGINT PRIMARY KEY
);
~~~

tạo identifier có chữ hoa C được giữ nguyên. Sau đó câu query phải dùng đúng cách quote và spelling tương ứng:

~~~sql
SELECT * FROM "Customer";
~~~

Nếu truy vấn viết SELECT * FROM Customer, PostgreSQL sẽ tìm customer viết thường và không nhất thiết tìm thấy bảng "Customer".

Quy tắc này có thể tạo lỗi khi chuyển schema từ database này sang database khác, nhất là khi migration tạo tên có mixed case hoặc có quote.

### Quy ước đặt tên dễ portable

Để giảm vấn đề quoting:

- Dùng tên bảng/cột chữ thường.
- Dùng snake_case cho identifier vật lý.
- Tránh keyword SQL.
- Không dùng dấu cách hoặc ký tự đặc biệt trong tên.
- Giữ naming strategy nhất quán giữa entity, migration và SQL tùy chỉnh.
- Chỉ dùng quoted mixed-case identifier khi có lý do rõ ràng và chấp nhận mọi nơi phải dùng đúng spelling.

## 6. Quoting trong mapping Spring Data JDBC

Entity có thể khai báo bảng và cột bằng metadata:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        @Column("order_number") String orderNumber,
        String status
) {}
~~~

Tên property Java là orderNumber, nhưng tên cột vật lý là order_number. Spring Data dùng mapping metadata và identifier processing của dialect khi tạo SQL.

Dialect có thể quote identifier trong SQL được framework sinh theo quy tắc database. Vì vậy, generated SQL không nhất thiết giống chính xác câu SQL viết tay mà bạn mong đợi, dù chúng có cùng ý nghĩa.

Nếu cần dùng tên bảng/cột trùng keyword, có thể cấu hình tên mapping theo khả năng hỗ trợ của phiên bản Spring Data Relational và dialect. Hãy xác nhận SQL được sinh trên database thực tế. Không nên giả định annotation @Table hoặc @Column sẽ tự sửa mọi câu SQL tùy chỉnh.

### SQL viết tay không được dialect tự viết lại

Ví dụ repository method:

~~~java
@Query("""
    SELECT id, order_number, status
    FROM purchase_orders
    WHERE status = :status
    """)
List<PurchaseOrder> findByStatus(@Param("status") String status);
~~~

Tên bảng/cột trong @Query là identifier do lập trình viên ghi. Framework bind tham số status, nhưng không thể tự động đổi một câu SQL tùy ý từ cú pháp quote của MySQL sang PostgreSQL hoặc sửa mọi reserved word.

Khi SQL tùy chỉnh phải chạy trên nhiều database, cần:

- Dùng tập con cú pháp SQL chung nếu có thể.
- Tránh identifier cần quote.
- Tách query theo dialect/database khi thật sự cần.
- Dùng custom repository abstraction để đóng gói khác biệt.
- Kiểm tra migration và query trên từng DBMS mục tiêu.

## 7. LIMIT và OFFSET dùng để phân trang

Phân trang offset-based có hai thành phần:

- **LIMIT**: số hàng tối đa muốn nhận.
- **OFFSET**: số hàng bỏ qua trước khi lấy kết quả.

Ví dụ:

~~~sql
SELECT id, order_number, status
FROM purchase_orders
ORDER BY created_at DESC, id ASC
LIMIT 20 OFFSET 40;
~~~

Câu lệnh lấy tối đa 20 hàng sau khi bỏ qua 40 hàng đầu tiên theo thứ tự đã sắp xếp.

Nếu page number bắt đầu từ 0, công thức:

~~~text
offset = pageNumber * pageSize
~~~

Ví dụ pageNumber = 2, pageSize = 20 thì offset = 40.

Không có ORDER BY thì database không bảo đảm thứ tự hàng. Phân trang không có thứ tự ổn định có thể khiến một bản ghi xuất hiện ở nhiều trang hoặc bị bỏ qua khi dữ liệu thay đổi.

## 8. Cú pháp pagination khác nhau giữa database

Không phải database nào cũng dùng LIMIT/OFFSET giống PostgreSQL/MySQL.

| Database | Một dạng cú pháp giới hạn kết quả |
|---|---|
| PostgreSQL | LIMIT n OFFSET m |
| MySQL / MariaDB | LIMIT n OFFSET m hoặc LIMIT m, n |
| H2 | LIMIT n OFFSET m; cũng hỗ trợ cú pháp chuẩn tùy phiên bản |
| SQL Server | ORDER BY ... OFFSET m ROWS FETCH NEXT n ROWS ONLY |
| Oracle hiện đại | OFFSET m ROWS FETCH NEXT n ROWS ONLY |
| Oracle phiên bản cũ | Có thể dùng ROWNUM hoặc truy vấn lồng |

Ví dụ SQL Server:

~~~sql
SELECT id, order_number, status
FROM purchase_orders
ORDER BY created_at DESC, id ASC
OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Ví dụ Oracle hiện đại:

~~~sql
SELECT id, order_number, status
FROM purchase_orders
ORDER BY created_at DESC, id ASC
OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Đây là khác biệt mà dialect có thể xử lý khi Spring Data sinh query. Nếu tự viết @Query chứa LIMIT 20 OFFSET 40, câu lệnh có thể không chạy trên SQL Server hoặc Oracle phiên bản không hỗ trợ cú pháp đó.

## 9. Dùng Pageable và Query để tránh tự viết cú pháp phân trang

Trong repository, method có thể nhận Pageable theo khả năng của Spring Data JDBC:

~~~java
Page<PurchaseOrder> findByStatus(String status, Pageable pageable);
~~~

Khi cần dùng JdbcAggregateTemplate, có thể áp dụng Pageable lên Query:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        )
);

Query baseQuery = Query.query(
        Criteria.where("status").is("OPEN")
);

Query pageQuery = baseQuery.with(pageable);

List<PurchaseOrder> content =
        template.findAll(pageQuery, PurchaseOrder.class);
~~~

Dialect tạo phần SQL giới hạn và độ lệch phù hợp. Code ứng dụng không cần tự quyết định có dùng LIMIT, OFFSET FETCH hay ROWNUM.

Nếu cần Page<T> có tổng số phần tử, đếm bằng query gốc chưa phân trang:

~~~java
long total = template.count(baseQuery, PurchaseOrder.class);
Page<PurchaseOrder> page = new PageImpl<>(content, pageable, total);
~~~

Phần lấy dữ liệu và phần đếm là hai truy vấn riêng. Khi dữ liệu thay đổi đồng thời, total và content có thể khác thời điểm quan sát; transaction/isolation cần được cân nhắc theo yêu cầu.

### Stable sort là bắt buộc về mặt thực tế

Một trang ổn định nên có thứ tự xác định, đặc biệt khi cột sort chính có thể trùng nhau:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);
~~~

Nếu chỉ sort theo createdAt, nhiều đơn hàng cùng timestamp có thể đổi thứ tự giữa các lần query. Thêm khóa duy nhất như id làm tiêu chí cuối giúp kết quả phân trang ổn định hơn.

## 10. Offset pagination có giới hạn hiệu năng

Offset lớn có thể tốn chi phí vì database phải xác định và bỏ qua nhiều hàng trước khi trả kết quả.

Ví dụ trang 1.000 với page size 50 có offset 49.950. Tùy execution plan và index, database có thể phải duyệt một lượng lớn dữ liệu.

Khi cần duyệt dữ liệu lớn hoặc trang sâu, cân nhắc **keyset/seek pagination**. Ví dụ sắp xếp created_at giảm dần và id giảm dần; trang tiếp theo dùng cặp giá trị cuối trang trước:

~~~sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
ORDER BY created_at DESC, id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Cú pháp giới hạn cuối cùng vẫn phụ thuộc dialect. Ý tưởng keyset là lọc từ khóa cuối trang trước thay vì bỏ qua hàng theo offset.

Keyset pagination phù hợp khi:

- Dataset lớn.
- Người dùng chủ yếu đi tới trang kế tiếp.
- Có cột sort ổn định và khóa duy nhất làm tie-breaker.
- Không cần nhảy tùy ý đến một số trang rất xa.

Không nên giả định Pageable tự động biến offset pagination thành keyset pagination. Đây là một chiến lược query khác và cần được thiết kế rõ.

## 11. Generated keys là gì?

Khi INSERT một hàng, database có thể tự sinh khóa chính. Ví dụ cột identity/auto-increment:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
~~~

Ứng dụng insert mà không truyền id:

~~~sql
INSERT INTO customers(name) VALUES ('Lan');
~~~

Database tạo ID, ví dụ 101. Ứng dụng thường cần lấy ID đó để:

- Trả object đã lưu cho caller.
- Gắn khóa ngoại cho các hàng child thuộc aggregate.
- Tạo URL hoặc response.
- Ghi audit hoặc outbox.
- Thực hiện bước tiếp theo trong cùng transaction.

Generated key là giá trị khóa do database cấp. Nó khác với update count, tức số hàng bị tác động bởi câu lệnh.

## 12. Spring Data JDBC lấy ID được sinh như thế nào?

Khi aggregate root có property @Id và giá trị ID biểu thị entity mới theo quy tắc newness, Spring Data JDBC dùng chiến lược phù hợp với dialect/driver để insert và lấy generated ID.

Ví dụ:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name
) {}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Lưu aggregate mới:

~~~java
Customer input = new Customer(null, "Lan");
Customer saved = repository.save(input);

Long generatedId = saved.id();
~~~

Với immutable record, hãy dùng object được trả về từ save. Không giả định object đầu vào đã bị mutate để nhận ID.

Spring Data JDBC có thể dùng khả năng generated keys của JDBC driver hoặc chiến lược đặc thù theo database. Chi tiết SQL/returning strategy phụ thuộc dialect và driver.

### ID do ứng dụng gán khác ID do database sinh

Nếu ứng dụng tự tạo ID, ví dụ UUID:

~~~java
Customer input = new Customer(UUID.randomUUID(), "Lan");
Customer saved = repository.save(input);
~~~

thì ID đã có trước khi INSERT và không cần lấy generated identity từ database. Tuy nhiên, chiến lược nhận diện entity mới phải phù hợp với cách ID được gán; không nên chỉ đổi kiểu ID rồi giả định mọi repository sẽ tự biết object là mới.

Với Spring Data JDBC, quy tắc nhận diện new entity có thể dựa trên ID null hoặc version null khi entity dùng @Version, và có thể được tùy chỉnh qua Persistable khi cần. Hãy chọn chiến lược rõ ràng để tránh entity có ID gán sẵn bị coi nhầm là entity đã tồn tại.

## 13. JDBC generated keys API

JDBC cung cấp khả năng yêu cầu generated keys khi tạo PreparedStatement và đọc kết quả qua getGeneratedKeys():

~~~java
PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO customers(name) VALUES (?)",
        Statement.RETURN_GENERATED_KEYS
);
~~~

Sau khi executeUpdate:

~~~java
int affected = statement.executeUpdate();

try (ResultSet keys = statement.getGeneratedKeys()) {
    if (keys.next()) {
        long id = keys.getLong(1);
    }
}
~~~

Đây là API JDBC tổng quát. Driver/database phải hỗ trợ việc trả generated keys theo cách đó và có thể có khác biệt về cột được trả, tên cột hoặc kiểu dữ liệu.

Có thể kiểm tra driver khai báo hỗ trợ:

~~~java
boolean supportsGeneratedKeys =
        connection.getMetaData().supportsGetGeneratedKeys();
~~~

Thông tin metadata không thay thế integration test. Hãy thử đúng câu INSERT và đúng driver đang dùng.

## 14. Lấy generated key với JdbcTemplate và KeyHolder

Khi viết custom JDBC code, Spring JDBC cung cấp KeyHolder và GeneratedKeyHolder:

~~~java
import java.sql.Statement;
import org.springframework.jdbc.core.PreparedStatementCreator;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

KeyHolder keyHolder = new GeneratedKeyHolder();

PreparedStatementCreator creator = connection -> {
    PreparedStatement statement = connection.prepareStatement(
            "INSERT INTO customers(name) VALUES (?)",
            Statement.RETURN_GENERATED_KEYS
    );
    statement.setString(1, "Lan");
    return statement;
};

int affected = jdbcTemplate.update(creator, keyHolder);

Number key = keyHolder.getKey();
Long generatedId = key == null ? null : key.longValue();
~~~

Ví dụ dùng API JDBC generated keys thông thường. Một số driver yêu cầu chỉ định cột generated key hoặc hỗ trợ cách lấy khác. Kiểm tra tài liệu driver và thử trên database mục tiêu.

Không nên viết logic lấy ID bằng cách chạy một câu SELECT riêng kiểu “ID lớn nhất hiện tại”:

~~~sql
SELECT MAX(id) FROM customers;
~~~

Cách này không an toàn khi có nhiều transaction insert đồng thời; giá trị lớn nhất có thể thuộc về transaction khác. Dùng generated key của chính câu INSERT hoặc cơ chế sequence/returning phù hợp.

## 15. PostgreSQL RETURNING và các cơ chế tương tự

Một số database hỗ trợ trả về dữ liệu từ câu INSERT/UPDATE/DELETE. PostgreSQL có RETURNING:

~~~sql
INSERT INTO customers(name)
VALUES ('Lan')
RETURNING id;
~~~

SQL Server có OUTPUT inserted:

~~~sql
INSERT INTO customers(name)
OUTPUT inserted.id
VALUES ('Lan');
~~~

Đây là cú pháp database-specific. JDBC driver và Spring Data dialect có thể dùng chiến lược phù hợp cho thao tác framework quản lý, nhưng SQL tự viết phải dùng đúng cú pháp của DBMS.

Nếu custom query cần trả về ID hoặc cả row sau INSERT, hãy xác định API JDBC phù hợp với result set trả về. Không giả định mọi câu INSERT có RETURNING đều có thể gọi qua JdbcTemplate.update(...) và nhận ID như update count; tùy API, có thể cần query/PreparedStatement hoặc RowMapper để đọc ResultSet.

## 16. Sequence và identity không giống nhau

Hai chiến lược sinh ID thường gặp:

- **Identity/auto-increment**: database sinh giá trị khi insert hàng.
- **Sequence**: database cung cấp một đối tượng sequence để cấp giá trị trước hoặc trong lúc insert.

Ví dụ sequence SQL:

~~~sql
CREATE SEQUENCE customer_id_seq START WITH 1 INCREMENT BY 1;
~~~

Một database có thể dùng:

~~~sql
INSERT INTO customers(id, name)
VALUES (NEXT VALUE FOR customer_id_seq, 'Lan');
~~~

Database khác có thể dùng cú pháp nextval hoặc sequence expression khác. Việc lấy giá trị sequence cũng có semantics riêng.

Spring Data JDBC hỗ trợ ID generation theo khả năng mapping/dialect của phiên bản và database. Nếu schema dùng sequence đặc thù hoặc ID strategy không được tự động hỗ trợ, hãy cấu hình theo API Spring Data Relational hiện hành hoặc triển khai custom persistence có kiểm soát. Không copy cú pháp sequence từ Oracle sang PostgreSQL hoặc ngược lại mà không kiểm tra.

## 17. JDBC type và Java type không phải lúc nào cũng tương ứng một-một

JDBC định nghĩa các kiểu dữ liệu chuẩn qua java.sql.Types/JDBCType, nhưng mỗi DBMS có tập kiểu vật lý và driver mapping riêng.

Ví dụ:

| Kiểu database thường gặp | Java type thường dùng | Lưu ý |
|---|---|---|
| BIGINT | Long / long | Dùng Long nếu có thể null |
| INTEGER | Integer / int | Kiểm tra overflow và nullability |
| VARCHAR | String | Encoding, collation và độ dài |
| BOOLEAN / BIT | Boolean / boolean | Hành vi phụ thuộc database/driver |
| DECIMAL / NUMERIC | BigDecimal | Giữ precision và scale |
| DATE | LocalDate | Chỉ biểu diễn ngày |
| TIMESTAMP | LocalDateTime hoặc kiểu thời gian phù hợp | Phân biệt local time và instant |
| TIMESTAMP WITH TIME ZONE | OffsetDateTime / Instant tùy mapping | Semantics timezone khác nhau theo DBMS |
| BINARY / VARBINARY / BLOB | byte[] | Kích thước và streaming |
| UUID | UUID hoặc String | Hỗ trợ kiểu vật lý phụ thuộc database |
| JSON / JSONB | String hoặc domain type qua converter | Không phải JDBC type portable giống nhau |
| ARRAY | SQL Array hoặc collection qua converter | Driver support rất khác nhau |

Đừng giả định mọi database có cùng kiểu BOOLEAN, UUID hoặc JSON. Có DB dùng kiểu native, có DB dùng CHAR/VARCHAR, BINARY hoặc kiểu mở rộng.

## 18. Boolean, enum và kiểu số

### Boolean

Một số database có kiểu BOOLEAN thực sự; một số hệ thống dùng BIT, NUMBER(1) hoặc biểu diễn số/chuỗi. Driver có thể chuyển đổi theo cách riêng.

Nếu schema cũ lưu active bằng CHAR(1) với Y/N, property Java Boolean cần converter để ánh xạ rõ:

~~~java
@WritingConverter
public class BooleanWritingConverter
        implements Converter<Boolean, String> {

    @Override
    public String convert(Boolean source) {
        return Boolean.TRUE.equals(source) ? "Y" : "N";
    }
}
~~~

Converter đọc cần ánh xạ ngược Y/N về Boolean. Không dùng converter này nếu database đã có kiểu boolean native và driver mapping phù hợp.

### Enum

Nếu enum được lưu bằng tên, giá trị trong database phụ thuộc tên enum Java. Đổi tên enum có thể cần migration dữ liệu.

~~~java
enum OrderStatus {
    NEW, PAID, SHIPPED
}
~~~

Với hệ thống lâu dài, có thể dùng converter lưu mã ổn định như N/P/S thay vì phụ thuộc tên enum. Cần có cả converter ghi và đọc để bảo đảm hai chiều nhất quán.

### Số và tiền tệ

Dùng BigDecimal cho DECIMAL/NUMERIC. Tránh chuyển qua double nếu giá trị cần chính xác như tiền tệ.

~~~java
BigDecimal total = new BigDecimal("1250.50");
~~~

Đối chiếu precision/scale giữa Java, schema và dữ liệu. Nếu database dùng DECIMAL(12,2), giá trị có quá nhiều chữ số hoặc scale có thể bị từ chối, làm tròn hoặc cắt theo hành vi DBMS.

## 19. Temporal type và timezone

Ngày giờ là một nguồn lỗi phổ biến khi chuyển database hoặc driver.

Cần phân biệt:

- LocalDate: ngày lịch, không có giờ.
- LocalTime: giờ trong ngày, không có ngày.
- LocalDateTime: ngày giờ địa phương, không mang offset/timezone.
- OffsetDateTime: ngày giờ kèm UTC offset.
- Instant: một thời điểm trên timeline UTC.

TIMESTAMP và TIMESTAMP WITH TIME ZONE không có semantics giống nhau trên mọi DBMS. Một số database lưu local timestamp; một số chuẩn hóa về UTC; một số lưu offset hoặc diễn giải theo session timezone.

Ví dụ domain lưu Instant:

~~~java
public record AuditEntry(
        Long id,
        Instant createdAt
) {}
~~~

Khi lưu/đọc, hãy thống nhất timezone policy, thường là UTC ở biên persistence và chuyển sang timezone hiển thị ở tầng presentation. Kiểm tra JDBC driver có hỗ trợ chuyển kiểu mong muốn và precision timestamp của database.

Đừng giả định LocalDateTime có thể thay thế Instant nếu nghiệp vụ cần xác định thời điểm tuyệt đối. LocalDateTime không cho biết offset nên không thể xác định duy nhất một instant nếu không có timezone bổ sung.

## 20. UUID, JSON và kiểu dữ liệu đặc thù

UUID có thể được lưu dưới dạng kiểu UUID native, CHAR(36), VARCHAR(36) hoặc BINARY(16). Kiểu vật lý ảnh hưởng kích thước, index và cách driver bind/read.

JSON có thể được lưu trong cột JSON/JSONB hoặc text. JDBC driver có thể yêu cầu object đặc thù, PGobject hoặc converter tùy DBMS. Không nên giả định String luôn bind trực tiếp được vào mọi cột JSON native mà không cần cast hoặc type mapping.

Ví dụ domain value object:

~~~java
public record ShippingAddress(String street, String city) {}
~~~

Có thể dùng converter để lưu object thành JSON string, nhưng cần thống nhất serialization format, version schema và cách đọc dữ liệu cũ. Nếu JSON được query theo key thường xuyên, cần xem xét khả năng JSON operator/index của database và tránh làm mất portability mà không có lý do.

Với ARRAY, XML, spatial hoặc vendor-specific type, hãy kiểm tra JDBC driver và converter. Các kiểu này thường cần code mapping riêng.

## 21. Custom converters trong Spring Data JDBC

Spring Data JDBC cho phép đăng ký custom conversions để chuyển kiểu domain sang kiểu store và ngược lại. Có thể dùng @WritingConverter và @ReadingConverter để phân biệt hướng chuyển đổi.

Ví dụ value object Money được lưu thành BigDecimal:

~~~java
public record Money(BigDecimal amount) {}
~~~

Converter ghi:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyWritingConverter implements Converter<Money, BigDecimal> {
    @Override
    public BigDecimal convert(Money source) {
        return source.amount();
    }
}
~~~

Converter đọc:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class MoneyReadingConverter implements Converter<BigDecimal, Money> {
    @Override
    public Money convert(BigDecimal source) {
        return new Money(source);
    }
}
~~~

Đăng ký trong cấu hình JDBC:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new MoneyWritingConverter(),
                new MoneyReadingConverter()
        );
    }
}
~~~

Chữ ký cấu hình cụ thể có thể thay đổi theo phiên bản Spring Data Relational; đối chiếu API của dependency dự án. Nếu ứng dụng dùng Spring Boot auto-configuration, hãy tránh khai báo thêm cấu hình làm thay thế hoặc vô hiệu hóa các bean JDBC mặc định ngoài ý muốn.

Custom converter của Spring Data JDBC được dùng trong mapping do Spring Data quản lý. Không nên giả định JdbcTemplate tự động gọi cùng conversion service cho mọi tham số và ResultSet. Với custom JDBC code, hãy gọi converter rõ ràng hoặc dùng RowMapper/parameter mapping riêng.

## 22. Null và JDBC type

Một cột nullable cần kiểu Java có thể biểu diễn null. Ví dụ:

- BIGINT nullable nên map sang Long thay vì long.
- BOOLEAN nullable nên map sang Boolean thay vì boolean.
- DECIMAL nullable nên map sang BigDecimal có thể null.

Khi dùng PreparedStatement, việc bind null đôi khi cần chỉ định JDBC type để driver/database biết kiểu mong muốn:

~~~java
statement.setNull(1, Types.VARCHAR);
~~~

NamedParameterJdbcTemplate cũng cho phép khai báo SQL type cho parameter khi cần, đặc biệt với null hoặc kiểu đặc thù:

~~~java
new MapSqlParameterSource()
        .addValue("status", null, Types.VARCHAR);
~~~

Không nên thay null bằng chuỗi rỗng, 0 hoặc false nếu domain phân biệt rõ các trạng thái đó. SQL NULL có semantics riêng và điều kiện so sánh phải dùng IS NULL/IS NOT NULL thay vì = NULL.

## 23. Kiểu dữ liệu trong @Query và JdbcTemplate

Derived query và repository CRUD sử dụng mapping metadata để bind giá trị. Với @Query, Spring Data JDBC vẫn xử lý parameter binding theo repository infrastructure và mapping được hỗ trợ, nhưng câu SQL/identifier là do người viết.

Với JdbcTemplate, ứng dụng kiểm soát bind type và mapping kết quả nhiều hơn. Ví dụ:

~~~java
jdbcTemplate.query(
        "SELECT id, total FROM purchase_orders WHERE status = ?",
        (rs, rowNum) -> new PurchaseOrderSummary(
                rs.getLong("id"),
                rs.getBigDecimal("total")
        ),
        "OPEN"
);
~~~

Nếu ResultSet có null ở cột số, getLong trả 0 cho cả SQL NULL; phải gọi wasNull() hoặc dùng getObject với kiểu wrapper để phân biệt:

~~~java
long value = rs.getLong("optional_count");
Long count = rs.wasNull() ? null : value;
~~~

Hoặc:

~~~java
Long count = rs.getObject("optional_count", Long.class);
~~~

Cách hỗ trợ getObject(column, Class) phụ thuộc driver/JDBC version; kiểm tra driver khi dùng kiểu đặc thù.

## 24. Tính portable của SQL tự viết

Khi ứng dụng hỗ trợ nhiều DBMS, cần phân biệt hai phần:

- **SQL do Spring Data sinh**: dialect có thể xử lý nhiều khác biệt đã được framework mô hình hóa.
- **SQL do ứng dụng viết**: cú pháp cụ thể phải được người viết bảo đảm tương thích.

Ví dụ các câu lệnh sau không portable tuyệt đối:

~~~sql
SELECT * FROM customers LIMIT 10 OFFSET 20;
~~~

~~~sql
INSERT INTO customers(name) VALUES ('Lan') RETURNING id;
~~~

~~~sql
SELECT nextval('customer_id_seq');
~~~

Chúng có thể phù hợp với một database nhưng không chạy trên database khác. Nếu cần hỗ trợ nhiều dialect, có thể:

1. Dùng repository/Query API để framework sinh SQL.
2. Dùng cú pháp SQL chuẩn khi DBMS mục tiêu hỗ trợ.
3. Tách câu lệnh theo database vào strategy riêng.
4. Dùng custom repository fragment để đóng gói khác biệt.
5. Viết integration test trên mọi DBMS được công bố hỗ trợ.

Không nên tạo một câu SQL dài với nhiều nhánh DBMS nếu việc tách strategy rõ ràng hơn.

## 25. Migration schema phải đồng bộ với mapping

Dialect không tự sửa schema hiện có. Khi đổi database, cần chuyển đổi migration:

- Kiểu identity/auto-increment hoặc sequence.
- Kiểu UUID, boolean, JSON và temporal.
- Độ dài VARCHAR, precision/scale DECIMAL.
- Quoting và case của tên bảng/cột.
- Reserved word.
- Index và constraint.
- Default value, generated column và trigger.

Ví dụ DDL cho PostgreSQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    total NUMERIC(18, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

DDL cho MySQL có thể dùng AUTO_INCREMENT và kiểu khác:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    total DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Hai schema có ý nghĩa gần nhau nhưng không hoàn toàn giống nhau về timezone và generated identity semantics. Migration cần được thiết kế theo DBMS mục tiêu thay vì chỉ thay tên kiểu.

## 26. Kiểm thử portability giữa các database

Nếu ứng dụng tuyên bố hỗ trợ nhiều database, test chỉ với H2 là chưa đủ. Hãy kiểm tra các tình huống phụ thuộc dialect:

| Khu vực | Kiểm thử nên có |
|---|---|
| Identifier | Tên bảng/cột có reserved word hoặc mixed case nếu ứng dụng thực sự dùng |
| Pagination | Page đầu, page giữa, page rỗng, sort nhiều cột |
| Generated keys | Insert root mới, lấy ID, insert aggregate có child |
| Type mapping | Boolean, enum, decimal, temporal, UUID và null |
| Custom converters | Đọc/ghi hai chiều và dữ liệu cũ |
| SQL tùy chỉnh | @Query, JdbcTemplate, quote và pagination syntax |
| Transaction | Commit/rollback, optimistic locking và isolation cần thiết |
| Migration | Tạo schema mới và nâng cấp schema từ phiên bản trước |

Testcontainers có thể chạy container của database mục tiêu để integration test trên driver thật. Hãy chọn image/version gần với môi trường triển khai và dùng đúng JDBC driver dependency. Với database thương mại hoặc không có image phù hợp, dùng môi trường test được nhà cung cấp hỗ trợ.

## 27. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| SQL lỗi gần tên bảng/cột | Identifier là reserved word hoặc quote sai | Đổi tên hoặc quote theo dialect |
| PostgreSQL không tìm thấy bảng mixed-case | Identifier được tạo có quote và phân biệt hoa/thường | Dùng đúng quoted spelling hoặc chuẩn hóa schema |
| Query chạy trên H2 nhưng lỗi trên SQL Server | @Query dùng LIMIT/OFFSET không được hỗ trợ | Dùng Pageable/Query hoặc SQL riêng cho dialect |
| ID sau save vẫn null | Đọc object đầu vào thay vì object trả về hoặc driver/generated strategy không phù hợp | Dùng object trả về và kiểm tra generated-key support |
| ID lấy bằng MAX(id) bị sai | Có transaction insert đồng thời | Dùng generated keys/RETURNING/sequence phù hợp |
| UUID bind thất bại | Database/driver dùng kiểu UUID đặc thù | Dùng converter hoặc JDBC type phù hợp |
| Enum không đọc lại được | Giá trị lưu trong DB không khớp converter | Chuẩn hóa mã lưu và converter hai chiều |
| Boolean sai trên DB khác | Kiểu BOOLEAN/BIT/NUMBER mapping khác nhau | Dùng converter hoặc kiểu vật lý thống nhất |
| Timestamp lệch giờ | LocalDateTime/Instant/timezone semantics bị nhầm | Chọn temporal type và UTC policy rõ ràng |
| BigDecimal mất độ chính xác | Chuyển qua double hoặc schema precision/scale không đủ | Dùng BigDecimal và đồng bộ DECIMAL |
| Cột nullable thành 0/false | Dùng primitive hoặc ResultSet getter không kiểm tra wasNull | Dùng wrapper và xử lý SQL NULL |
| JdbcTemplate không dùng custom converter | Converter Spring Data không tự áp dụng cho JDBC template | Bind/map thủ công hoặc dùng mapper chung |
| Câu INSERT tùy chỉnh không trả ID | Dùng update count thay cho generated key | Dùng KeyHolder hoặc result-set API phù hợp |

## 28. Quy trình khi chuyển database hoặc driver

Khi chuyển ứng dụng sang DBMS khác hoặc nâng cấp JDBC driver, nên thực hiện theo trình tự:

1. Xác định DBMS, version và JDBC driver version mục tiêu.
2. Kiểm tra dialect mà phiên bản Spring Data Relational hỗ trợ.
3. Đối chiếu identifier, reserved words, quote và case normalization.
4. Kiểm tra cú pháp LIMIT/OFFSET và ORDER BY.
5. Kiểm tra identity/sequence và generated-key retrieval.
6. So sánh kiểu SQL với Java type, nullability và converter.
7. Chuyển đổi migration/schema, index và constraint.
8. Chạy integration test bằng driver/database mục tiêu.
9. Kiểm tra SQL được sinh và bind parameter trong môi trường phát triển.
10. Đo execution plan và hiệu năng phân trang/truy vấn trên dữ liệu đại diện.

## 29. Bài thực hành: quan sát bốn khác biệt

Dùng một bảng đơn hàng:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    total DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Thực hiện các bài tập:

1. Lưu một PurchaseOrder có id null bằng repository.save và đọc ID từ object trả về.
2. Tạo repository query nhận Pageable, xem SQL pagination được tạo trên database đang dùng.
3. Thêm Sort theo createdAt và id để bảo đảm thứ tự ổn định.
4. Viết một câu @Query dùng identifier có tên dễ gây xung đột, sau đó đổi tên hoặc quote theo DBMS.
5. Dùng JdbcTemplate và GeneratedKeyHolder để insert một customer và lấy ID.
6. Kiểm tra DatabaseMetaData.supportsGetGeneratedKeys và identifierQuoteString.
7. Thêm một property BigDecimal, Instant và UUID; chạy đọc/ghi trên driver mục tiêu.
8. Thử giá trị null với wrapper type và kiểm tra kết quả ResultSet.
9. Thử một custom converter cho enum hoặc value object.
10. Chạy integration test trên H2 và database production-like, ghi lại các khác biệt quan sát được.

Mục tiêu là phân biệt phần framework/dialect đã xử lý với phần SQL, schema và converter mà ứng dụng cần tự quản lý.

## 30. Nguyên tắc ghi nhớ

- Dialect mô tả khác biệt SQL/JDBC để Spring Data JDBC sinh câu lệnh phù hợp với database.
- Identifier là tên bảng/cột; value là dữ liệu được bind. Không dùng bind parameter để thay tên identifier.
- Quoting và case normalization khác nhau giữa DBMS; tránh reserved word và mixed-case identifier nếu không cần.
- SQL trong @Query/JdbcTemplate không tự được dialect viết lại thành cú pháp portable.
- LIMIT/OFFSET có cú pháp khác nhau; dùng Pageable/Query để framework tạo phần phân trang phù hợp khi có thể.
- Phân trang cần ORDER BY ổn định, thường thêm ID làm tie-breaker.
- Generated key là ID database sinh, khác update count; dùng object trả về từ repository.save.
- JdbcTemplate có thể dùng KeyHolder/GeneratedKeyHolder hoặc cơ chế RETURNING/OUTPUT riêng của database.
- Không lấy ID bằng MAX(id) sau INSERT vì không an toàn khi có concurrent insert.
- JDBC type và Java type không luôn tương ứng một-một; chú ý UUID, JSON, enum, boolean và temporal type.
- Dùng BigDecimal cho DECIMAL/NUMERIC và wrapper type cho cột nullable.
- Custom converter của Spring Data JDBC không tự động áp dụng cho mọi thao tác JdbcTemplate.
- Migration, schema, driver và integration test phải cùng phản ánh DBMS được hỗ trợ.

Dialect giúp Spring Data JDBC xử lý nhiều khác biệt phổ biến giữa các database, nhưng không xóa bỏ sự khác nhau của SQL và JDBC driver. Hãy để framework quản lý phần generated SQL mà nó hỗ trợ; với SQL tự viết, identifier, pagination, generated key và type conversion phải được thiết kế theo database mục tiêu. Khi kiểm thử trên đúng driver và DBMS, ứng dụng sẽ tránh được những lỗi chỉ xuất hiện sau khi triển khai hoặc khi chuyển môi trường.

## Tài liệu tham khảo

- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html)
- [Spring Data Relational — API](https://docs.spring.io/spring-data/relational/docs/current/api/)
- [Spring Data JDBC — JdbcAggregateTemplate API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html)
- [JDBC DatabaseMetaData API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/DatabaseMetaData.html)
- [JDBC Connection API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html)
- [Spring JDBC Reference](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)

