# Sai tên bảng/cột, quoting và schema search path

Khi Spring Data JDBC đọc hoặc ghi aggregate, framework tạo SQL dựa trên metadata mapping, naming strategy, dialect và cấu hình database. Nếu tên bảng, tên cột hoặc schema trong mapping không khớp với database thực tế, câu SQL có thể thất bại dù entity Java vẫn biên dịch bình thường.

Những lỗi thường gặp gồm bảng không tồn tại, cột không tồn tại, identifier là từ khóa SQL, tên có chữ hoa/chữ thường khác nhau hoặc connection đang tìm bảng trong schema khác. Các lỗi này đôi khi có cùng biểu hiện như “table not found”, nhưng nguyên nhân có thể khác nhau.

Bài học này giải thích cách Spring Data JDBC suy ra tên relational, cách ghi đè bằng annotation, cách database xử lý identifier không quote và có quote, vai trò của schema/search path, cùng quy trình đối chiếu SQL được sinh ra với metadata database.

## 1. Spring Data JDBC lấy tên bảng và cột từ đâu?

Spring Data Relational dùng mapping metadata để xác định tên bảng, cột và các cột liên kết trong aggregate. Nếu không chỉ định tên tường minh, framework dùng naming strategy mặc định.

Ví dụ entity:

~~~java
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    private LocalDateTime createdAt;
}
~~~

Với naming strategy mặc định thường dùng trong Spring Data Relational, tên Java camelCase được chuyển sang dạng snake_case. Ví dụ:

| Java property/type | Tên relational thường được suy ra |
|---|---|
| PurchaseOrder | purchase_order |
| orderNumber | order_number |
| createdAt | created_at |

Tên thực tế còn chịu ảnh hưởng của custom NamingStrategy, annotation mapping và phiên bản Spring Data Relational. Khi database đã có schema do hệ thống khác tạo, không nên đoán tên bảng/cột từ tên class; hãy kiểm tra schema thực tế.

## 2. Ghi đè tên bảng bằng @Table

Nếu bảng có tên khác với tên mặc định, dùng @Table:

~~~java
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    // ...
}
~~~

Nếu bảng nằm trong schema cụ thể, có thể khai báo schema:

~~~java
@Table(value = "purchase_orders", schema = "sales")
public class PurchaseOrder {
    // ...
}
~~~

Tên thuộc tính annotation và khả năng hỗ trợ schema cần được đối chiếu với version Spring Data JDBC của dự án. Với database hoặc dialect có quy tắc schema riêng, hãy xác nhận SQL được sinh ra.

Khi có schema được chỉ định tường minh, ứng dụng không cần phụ thuộc hoàn toàn vào schema mặc định hoặc search path của connection để tìm bảng đó.

## 3. Ghi đè tên cột bằng @Column

Dùng @Column khi tên property Java không trùng tên cột:

~~~java
import org.springframework.data.relational.core.mapping.Column;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_no")
    private String orderNumber;

    @Column("created_on")
    private LocalDateTime createdAt;
}
~~~

Trong ví dụ, property Java vẫn có tên orderNumber và createdAt, nhưng Spring Data JDBC ánh xạ chúng vào order_no và created_on.

### 3.1. Column mapping không tự sửa schema

Annotation chỉ thay đổi metadata mapping của ứng dụng. Nó không tự tạo, đổi tên hoặc migrate cột trong database.

Nếu entity dùng:

~~~java
@Column("order_no")
private String orderNumber;
~~~

thì bảng phải thực sự có cột order_no. Nếu database chỉ có order_number, câu SQL vẫn có thể lỗi “column not found”.

Hãy đồng bộ entity mapping với migration/schema. Đừng sửa annotation để che một migration chưa chạy hoặc một schema drift giữa các môi trường.

## 4. Tên cột của collection và quan hệ aggregate

Spring Data JDBC lưu aggregate theo cấu trúc relational. Với collection con, cần chú ý cả bảng con, foreign key và key column nếu collection có thứ tự hoặc dùng Map.

Ví dụ:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_number"
    )
    private List<OrderLine> lines;
}
~~~

Các tên cần đối chiếu:

- Bảng của aggregate root: purchase_orders.
- Bảng lưu OrderLine theo mapping của kiểu con.
- Cột liên kết idColumn trong bảng con: order_id.
- keyColumn nếu collection cần lưu vị trí hoặc key: line_number.

Nếu bảng con đang dùng một tên foreign key khác, cần cấu hình mapping cho đúng. Sai idColumn thường làm thao tác tải hoặc lưu collection thất bại dù bảng root vẫn hoạt động.

Không nhầm @Column với @MappedCollection: @Column ánh xạ property scalar thành cột; @MappedCollection mô tả cách lưu collection con trong aggregate.

## 5. NamingStrategy và quy tắc đặt tên toàn cục

Khi nhiều entity cùng dùng một quy tắc khác mặc định, có thể cung cấp custom NamingStrategy thay vì lặp annotation ở mọi property.

NamingStrategy có thể quyết định tên:

- Bảng từ kiểu entity.
- Cột từ property.
- Cột foreign key của collection.
- Cột key của collection.

Ví dụ minh họa tùy biến tên bảng cho một entity:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.NamingStrategy;
import org.springframework.data.relational.core.sql.SqlIdentifier;

@Configuration
public class RelationalNamingConfiguration {

    @Bean
    NamingStrategy namingStrategy() {
        return new NamingStrategy() {

            @Override
            public SqlIdentifier getTableName(Class<?> type) {
                if (type == PurchaseOrder.class) {
                    return SqlIdentifier.unquoted("purchase_orders");
                }

                return NamingStrategy.INSTANCE.getTableName(type);
            }
        };
    }
}
~~~

Đoạn code minh họa API NamingStrategy hiện đại dựa trên SqlIdentifier. Hãy kiểm tra chữ ký và cách đăng ký NamingStrategy của đúng Spring Data Relational version trong dự án; các phiên bản cũ có thể có API khác.

Custom NamingStrategy là quy tắc mapping rộng. Thay đổi nó có thể ảnh hưởng nhiều entity, bao gồm bảng con và cột liên kết. Nếu chỉ một hoặc hai tên khác biệt, @Table và @Column thường thể hiện ý định rõ hơn.

## 6. Identifier là gì và vì sao cần quoting?

Database phân biệt tên identifier với giá trị dữ liệu. Tên bảng và tên cột là identifier; chuỗi được bind trong WHERE là value.

Ví dụ:

~~~sql
SELECT order_number
FROM purchase_orders
WHERE status = ?;
~~~

Ở đây purchase_orders, order_number và status là identifier. Giá trị truyền vào dấu ? là parameter.

Prepared statement bảo vệ value khỏi SQL injection, nhưng không thể bind tên bảng hoặc tên cột như một value parameter. Identifier cần được xác định từ mapping hoặc whitelist và được quote theo cú pháp của database khi cần.

### 6.1. Từ khóa SQL

Một số tên dễ xung đột với từ khóa hoặc cú pháp SQL:

- order
- user
- group
- key
- rank
- value

Ví dụ, bảng tên order có thể gây lỗi cú pháp vì ORDER là từ khóa trong ORDER BY. Cách đơn giản nhất thường là dùng tên không xung đột như purchase_orders.

Nếu phải tương thích với schema đã có tên đặc biệt, cần xác định cách quote identifier đúng với database và mapping infrastructure.

## 7. Identifier không quote và identifier có quote

Database có quy tắc riêng cho identifier không quote và identifier được quote. Quy tắc này ảnh hưởng chữ hoa/chữ thường và việc tên có được hiểu như từ khóa hay không.

### 7.1. PostgreSQL

Trong PostgreSQL:

- Identifier không quote được chuyển về chữ thường.
- Identifier được quote bằng dấu ngoặc kép giữ nguyên cách viết và có phân biệt hoa/thường.

Ví dụ:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY
);
~~~

Tên purchase_orders không quote được tra cứu như chữ thường.

Nếu tạo bảng:

~~~sql
CREATE TABLE "PurchaseOrders" (
    id BIGINT PRIMARY KEY
);
~~~

thì truy vấn phải dùng đúng identifier đã quote:

~~~sql
SELECT * FROM "PurchaseOrders";
~~~

Truy vấn không quote PurchaseOrders sẽ được PostgreSQL chuyển thành chữ thường và không trỏ đến bảng có tên quoted mixed-case.

### 7.2. Oracle

Oracle thường chuyển identifier không quote về chữ hoa. Identifier được quote giữ nguyên chữ hoa/chữ thường và cần được tham chiếu đúng cách.

Vì vậy, schema được tạo bằng quoted mixed-case identifiers có thể gây khó khăn khi dùng SQL sinh tự động hoặc khi nhiều công cụ dùng quy ước khác nhau.

### 7.3. MySQL

MySQL dùng backtick để quote identifier. Quy tắc phân biệt chữ hoa/chữ thường của tên bảng còn phụ thuộc hệ điều hành và cấu hình lower_case_table_names. Không nên dựa vào việc một máy Windows chạy được tên bảng khác chữ hoa/chữ thường để kết luận Linux production cũng hoạt động như vậy.

### 7.4. Không dùng dấu quote của database này cho database khác

Các kiểu quote thường gặp:

| Database | Identifier quote thường dùng |
|---|---|
| PostgreSQL | Dấu ngoặc kép: "name" |
| Oracle | Dấu ngoặc kép: "name" |
| MySQL | Backtick: name |
| SQL Server | Ngoặc vuông: [name], hoặc dấu ngoặc kép khi cấu hình phù hợp |

Dialect và identifier processing của Spring Data JDBC giúp tạo SQL theo database. Không tự nối dấu quote thủ công vào mọi annotation hoặc tên bảng mà không xác nhận cách framework xử lý.

## 8. Quoting trong Spring Data Relational

Spring Data Relational biểu diễn tên relational bằng SqlIdentifier. Identifier có thể mang thông tin quoted hoặc unquoted; dialect cung cấp quy tắc xử lý identifier phù hợp với database.

Nếu cần quote tên do mapping tạo ra, custom NamingStrategy có thể trả về SqlIdentifier được đánh dấu quoted:

~~~java
SqlIdentifier quotedName = SqlIdentifier.quoted("Order");
~~~

Ví dụ này minh họa việc tạo identifier quoted. Cách đưa identifier vào mapping phải thực hiện qua extension point phù hợp của phiên bản Spring Data Relational đang dùng, chẳng hạn NamingStrategy. Không giả định rằng thêm dấu quote vào chuỗi trong @Table hoặc @Column luôn tạo ra quoted identifier; annotation có thể coi toàn bộ chuỗi là tên literal tùy cách mapping xử lý.

Trước khi chọn quoting cho một schema hiện hữu, xác nhận:

1. Database tạo tên object bằng quy tắc quote nào.
2. Mapping đang tạo SqlIdentifier quoted hay unquoted.
3. Dialect dùng ký tự quote nào.
4. SQL thực tế có dùng đúng tên và đúng case không.

Nếu có thể, ưu tiên tên lowercase/snake_case không phải từ khóa và không cần quote. Quy ước đơn giản giảm lỗi giữa môi trường và công cụ migration.

## 9. Schema và search path

Schema là namespace chứa bảng và các object database. Một database có thể có nhiều schema với các bảng cùng tên:

~~~text
database
├── public
│   └── purchase_orders
├── sales
│   └── purchase_orders
└── archive
    └── purchase_orders
~~~

Nếu câu SQL chỉ dùng:

~~~sql
SELECT * FROM purchase_orders;
~~~

database cần xác định schema nào được tìm trước. Quy tắc đó phụ thuộc hệ quản trị và session configuration.

### 9.1. PostgreSQL search_path

PostgreSQL dùng search_path để tìm object không có schema prefix. Có thể kiểm tra:

~~~sql
SHOW search_path;
SELECT current_schema();
~~~

Nếu search_path không chứa schema sales hoặc schema khác được ưu tiên, câu query không qualify có thể tìm nhầm bảng hoặc báo relation does not exist.

Có thể chỉ định schema rõ trong mapping:

~~~java
@Table(value = "purchase_orders", schema = "sales")
public class PurchaseOrder {
    // ...
}
~~~

Hoặc cấu hình search_path cho connection/session theo chiến lược của ứng dụng. Với connection pool, session state có thể được giữ lại trên connection và tái sử dụng cho request sau. Nếu thay đổi search_path theo request, phải đảm bảo reset trạng thái trước khi trả connection về pool.

### 9.2. MySQL và database/catalog

Trong MySQL, schema thường tương đương database. Kết nối có thể chọn database mặc định trong JDBC URL hoặc qualify tên bảng bằng database/schema.

Kiểm tra database hiện tại:

~~~sql
SELECT DATABASE();
~~~

Nếu ứng dụng kết nối nhầm database mặc định, bảng có thể tồn tại nhưng query vẫn báo không tìm thấy.

### 9.3. SQL Server và default schema

SQL Server có default schema gắn với database user. Một tên bảng không qualify có thể được tìm trong schema mặc định của user kết nối.

Kiểm tra schema hiện tại hoặc metadata theo user đang dùng. Đừng chỉ kiểm tra bằng tài khoản DBA nếu ứng dụng kết nối bằng tài khoản có default schema khác.

## 10. Phân biệt lỗi tên bảng với lỗi search path

Thông báo lỗi có thể giúp định hướng:

| Triệu chứng | Nguyên nhân có thể |
|---|---|
| Table/relation does not exist | Sai tên bảng, sai case hoặc sai schema/search path |
| Invalid identifier | Sai tên cột, case hoặc quote |
| Column not found | @Column không khớp schema hoặc migration chưa chạy |
| Syntax error near tên bảng | Identifier là từ khóa hoặc quoting sai |
| Permission denied | Bảng tồn tại nhưng user không có quyền |
| Ambiguous column | Query JOIN nhiều bảng có cột trùng tên nhưng không qualify |
| Works locally, fails in production | Khác database, OS, search_path, schema hoặc naming configuration |

Không sửa tên bảng ngay khi thấy “not found”. Trước tiên xác định object có tồn tại trong database/schema mà ứng dụng đang kết nối hay không.

## 11. Kiểm tra metadata database

JDBC cung cấp DatabaseMetaData để kiểm tra bảng và cột mà connection hiện tại nhìn thấy:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    try (ResultSet tables = metadata.getTables(
            connection.getCatalog(),
            "sales",
            "purchase_orders",
            new String[] {"TABLE"})) {

        while (tables.next()) {
            System.out.println(tables.getString("TABLE_SCHEM"));
            System.out.println(tables.getString("TABLE_NAME"));
        }
    }
}
~~~

Các tham số catalog, schema pattern và table pattern có semantics khác nhau theo driver. Nếu không tìm thấy kết quả, thử kiểm tra catalog/schema hiện tại và cách driver xử lý chữ hoa/chữ thường.

Có thể truy vấn information schema hoặc catalog view của database:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name = 'purchase_orders';
~~~

Kiểm tra cột:

~~~sql
SELECT table_schema, table_name, column_name
FROM information_schema.columns
WHERE table_name = 'purchase_orders'
ORDER BY ordinal_position;
~~~

Hãy chạy truy vấn bằng đúng database user và connection settings mà ứng dụng sử dụng. Một DBA nhìn thấy bảng không có nghĩa user của ứng dụng có quyền truy cập hoặc search path phù hợp.

## 12. Đối chiếu SQL được Spring Data JDBC sinh ra

Khi mapping trông đúng nhưng query vẫn lỗi, cần xem SQL thực tế.

Các bước:

1. Xác định repository method hoặc aggregate operation gây lỗi.
2. Bật logging JDBC phù hợp với Spring version hoặc dùng công cụ quan sát SQL.
3. Ghi nhận SQL sau khi framework tạo query.
4. Xác định table, column, schema và identifier case.
5. Đối chiếu từng identifier với metadata database.
6. Kiểm tra parameter values riêng biệt với tên identifier.

Các công cụ như datasource-proxy hoặc P6Spy có thể giúp quan sát SQL và thời gian thực thi. Cẩn thận với dữ liệu nhạy cảm trong parameter logging; không bật log chứa thông tin cá nhân hoặc bí mật ở production nếu chưa có biện pháp bảo vệ.

### 12.1. SQL trong @Query là SQL do người viết cung cấp

Với query tùy chỉnh:

~~~java
@Query("""
    SELECT id, order_no
    FROM sales.purchase_orders
    WHERE status = :status
    """)
List<OrderSummary> findSummaries(@Param("status") String status);
~~~

Tên bảng và cột trong chuỗi SQL phải khớp database. Không giả định @Table hoặc @Column sẽ tự viết lại identifier bên trong một câu SQL literal.

Nếu đổi tên bảng bằng migration, hãy cập nhật cả query tùy chỉnh, view, stored procedure và các SQL script liên quan.

## 13. Migration và schema drift

Một mapping có thể đúng trong môi trường development nhưng sai ở production vì migration không đồng bộ.

Ví dụ:

- Entity đã đổi @Column từ order_number sang order_no.
- Migration đổi tên cột chưa chạy ở production.
- Một môi trường có bảng sales.purchase_orders, môi trường khác chỉ có public.purchase_orders.
- Database được tạo thủ công với tên quoted mixed-case.
- Migration tool chạy bằng schema user khác với ứng dụng.

Quy trình kiểm tra:

1. Xem version migration đã áp dụng trên từng môi trường.
2. Kiểm tra DDL thực tế, không chỉ file migration trong repository.
3. Kiểm tra schema/user mà ứng dụng kết nối.
4. So sánh tên bảng, cột, kiểu dữ liệu và constraint.
5. Chạy migration đúng database và schema.
6. Thực hiện integration test với cùng dialect/driver mục tiêu.

Không sửa entity mapping để thích ứng tạm thời với một môi trường bị thiếu migration mà không xác định nguồn schema chuẩn.

## 14. Quy tắc đặt tên để giảm lỗi

Một quy ước dễ vận hành thường có các đặc điểm:

- Dùng lowercase snake_case cho bảng và cột.
- Tránh từ khóa SQL làm tên bảng/cột.
- Tránh tên quoted mixed-case nếu không có lý do tương thích.
- Dùng @Table và @Column khi tên database khác tên Java.
- Chỉ định schema rõ nếu ứng dụng không nên phụ thuộc search path.
- Dùng cùng naming convention trong migration, query tùy chỉnh và entity mapping.
- Không đổi naming strategy toàn cục chỉ để sửa một bảng riêng lẻ.

Ví dụ:

~~~sql
CREATE TABLE sales.purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

~~~java
@Table(value = "purchase_orders", schema = "sales")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    @Column("created_at")
    private LocalDateTime createdAt;
}
~~~

Tên Java camelCase, tên relational lowercase snake_case và schema tường minh giúp mapping dễ đọc và ít phụ thuộc cấu hình session.

## 15. Kiểm thử mapping với database mục tiêu

H2 có thể dùng cho test nhanh, nhưng không chứng minh mọi quy tắc identifier của PostgreSQL, MySQL, Oracle hoặc SQL Server.

Các khác biệt có thể ảnh hưởng:

- Quy tắc case folding.
- Ký tự quote identifier.
- Từ khóa dành riêng.
- Schema/catalog/search path.
- Độ nhạy chữ hoa/chữ thường của tên bảng.
- Cách driver trả metadata.
- Cú pháp DDL và generated SQL.

Nếu production dùng PostgreSQL, integration test quan trọng về tên bảng/cột nên chạy với PostgreSQL cùng driver tương thích, chẳng hạn thông qua Testcontainers. Làm tương tự cho database mục tiêu khác.

Test nên bao gồm:

1. Insert aggregate.
2. Read aggregate.
3. Update aggregate.
4. Lưu và tải collection con.
5. Chạy custom @Query.
6. Kiểm tra schema được chỉ định và quyền của application user.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Spring tìm purchase_order nhưng DB có purchase_orders | Tên mặc định khác tên bảng thực tế | Dùng @Table với tên chính xác |
| Query báo không tìm thấy order_number | Property mapping suy ra tên khác hoặc cột DB có tên order_no | Dùng @Column và đồng bộ migration |
| Bảng tồn tại nhưng relation does not exist | Search path hoặc schema mặc định sai | Qualify schema hoặc cấu hình session đúng |
| Chạy được trên Windows nhưng lỗi Linux | Quy tắc case của tên bảng khác nhau | Dùng lowercase convention và test trên OS/database mục tiêu |
| Tên Order gây syntax error | Identifier xung đột từ khóa SQL | Đổi tên hoặc quote đúng dialect |
| Quote rồi lại không tìm thấy bảng | Quoted identifier phân biệt case | Dùng đúng spelling và quote convention khi tạo/truy vấn |
| Collection con không tải được | Sai bảng con hoặc idColumn/keyColumn | Kiểm tra @MappedCollection và foreign key |
| Repository chạy nhưng @Query lỗi | SQL literal dùng tên bảng/cột cũ | Cập nhật custom SQL theo schema |
| DBA thấy bảng nhưng app không thấy | User ứng dụng thiếu quyền hoặc dùng schema khác | Kiểm tra bằng đúng credentials và metadata |
| Một môi trường lỗi sau deploy | Migration chưa áp dụng hoặc schema drift | Kiểm tra migration history và DDL thực tế |
| Custom NamingStrategy làm nhiều entity đổi tên | Quy tắc toàn cục áp dụng rộng | Giới hạn thay đổi và kiểm thử toàn bộ mapping |
| Thêm dấu quote vào @Table nhưng SQL vẫn sai | Annotation không được diễn giải thành quoted identifier như dự đoán | Kiểm tra SqlIdentifier và dialect thực tế |

## 17. Quy trình chẩn đoán lỗi tên bảng/cột

Khi gặp lỗi mapping, thực hiện theo trình tự:

1. **Xác định database:** kiểm tra JDBC URL, catalog và database user.
2. **Xác định schema:** kiểm tra schema hiện tại và search path.
3. **Kiểm tra object:** truy vấn metadata để xác nhận bảng và cột tồn tại.
4. **Kiểm tra mapping:** xem @Table, @Column, @MappedCollection và NamingStrategy.
5. **Kiểm tra identifier:** xác định tên có quoted, reserved word hoặc mixed-case không.
6. **Xem SQL thực tế:** xác nhận Spring Data JDBC đang phát ra identifier nào.
7. **Kiểm tra migration:** so sánh schema thực tế với migration đã áp dụng.
8. **Kiểm tra quyền:** xác nhận application user có quyền trên đúng schema.
9. **Chạy integration test:** dùng cùng database/driver và cấu hình connection.
10. **Sửa nguồn gốc:** cập nhật mapping, migration hoặc schema/search path theo quy ước chuẩn.

## 18. Bài tập thực hành

### Bài 1 — Tên mặc định và tên tường minh

1. Tạo PurchaseOrder với property orderNumber.
2. Quan sát tên bảng/cột được suy ra.
3. Tạo schema dùng purchase_orders và order_no.
4. Dùng @Table và @Column để ánh xạ.
5. Kiểm tra insert và read.

### Bài 2 — Schema search path

1. Tạo hai schema có bảng cùng tên.
2. Chạy query không qualify schema.
3. Thay đổi search_path hoặc default schema.
4. Quan sát bảng được chọn.
5. Dùng schema tường minh trong mapping và so sánh.

### Bài 3 — Quoted identifier

1. Tạo bảng có tên mixed-case được quote.
2. Thử truy vấn không quote.
3. Thử truy vấn đúng quote và case.
4. Kiểm tra metadata qua JDBC.
5. Ghi nhận vì sao lowercase unquoted naming dễ vận hành hơn.

### Bài 4 — NamingStrategy

1. Cấu hình custom NamingStrategy cho một entity.
2. Kiểm tra tên bảng được sinh.
3. Xác nhận entity khác vẫn dùng quy tắc mặc định.
4. Kiểm tra cả collection mapping.
5. Chạy integration test với database mục tiêu.

### Bài 5 — Chẩn đoán lỗi migration

1. Thay đổi tên một cột trong entity.
2. Bỏ qua migration ở test database.
3. Quan sát lỗi column not found.
4. Áp dụng migration.
5. Chạy lại test và xác nhận mapping.

## 19. Kết luận

Lỗi tên bảng và cột trong Spring Data JDBC thường bắt nguồn từ khác biệt giữa mapping metadata, schema thực tế và quy tắc identifier của database. Hãy xác định tên do naming strategy suy ra, dùng @Table và @Column cho các tên khác biệt, và kiểm tra cả cột liên kết của collection qua @MappedCollection.

Quoting và chữ hoa/chữ thường phụ thuộc database. Identifier không quote có thể bị chuyển case hoặc xung đột từ khóa; identifier quoted thường giữ nguyên spelling và phải được tham chiếu đúng cách. Schema search path quyết định nơi database tìm bảng không qualify, vì vậy một bảng có thể tồn tại nhưng connection của ứng dụng vẫn không tìm thấy.

Khi chẩn đoán, kiểm tra bằng đúng application user, schema và JDBC driver; đối chiếu SQL được sinh ra với metadata database và migration đã áp dụng. Dùng quy ước lowercase snake_case, tránh reserved words và chỉ định schema rõ khi cần sẽ giảm đáng kể lỗi mapping giữa các môi trường.
