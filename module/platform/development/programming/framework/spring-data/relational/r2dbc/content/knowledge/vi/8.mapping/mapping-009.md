# Chiến lược đặt tên và xử lý định danh có dấu ngoặc

## 1. Vì sao tên bảng và tên cột cần được quản lý nhất quán?

Khi ánh xạ entity Java sang cơ sở dữ liệu quan hệ, ứng dụng phải chuyển tên class và thuộc tính thành tên bảng, tên cột. Trong Java, tên thường dùng camelCase như `createdAt`, `customerId`; trong database, nhóm phát triển có thể chọn snake_case như `created_at`, `customer_id`. Tên bảng cũng có thể theo tên class, tên nghiệp vụ hoặc một quy ước riêng.

Ngoài quy ước đặt tên, SQL còn có khái niệm **identifier** (định danh): tên database, schema, bảng, cột, alias hoặc sequence. Một số identifier trùng với từ khóa SQL, chứa chữ hoa, dấu cách hoặc ký tự đặc biệt. Khi đó, database có thể yêu cầu identifier được đặt trong dấu quote phù hợp.

Trong Spring Data Relational, bao gồm Spring Data R2DBC, hai vấn đề này được xử lý qua:

- **Naming strategy**: quy tắc suy ra tên bảng, cột và các cột liên kết từ mô hình Java.
- **Quoted identifier**: metadata cho biết một identifier cần được quote khi Spring Data tạo SQL.

Bài này tập trung vào cách chọn quy ước đặt tên, ghi đè tên bằng annotation, xử lý identifier có dấu quote và phối hợp giữa mapping metadata với SQL viết tay.

## 2. Identifier khác với giá trị dữ liệu

Cần phân biệt tên đối tượng SQL với giá trị được truyền vào câu lệnh.

~~~sql
SELECT customer_id, status
FROM orders
WHERE customer_id = 42;
~~~

Trong câu SQL trên:

- `orders` là tên bảng.
- `customer_id` và `status` là tên cột.
- `42` là giá trị dữ liệu dùng trong điều kiện.

Tên bảng và tên cột là **identifier**. Giá trị như ID, email, trạng thái hoặc ngày tháng là **data value**. Hai loại này có quy tắc xử lý khác nhau.

Với giá trị dữ liệu, nên dùng bind parameter:

~~~java
databaseClient.sql("""
        SELECT customer_id, status
        FROM orders
        WHERE customer_id = :customerId
        """)
    .bind("customerId", customerId)
    .map((row, metadata) -> row.get("status", String.class))
    .one();
~~~

Bind parameter giúp driver truyền giá trị đúng kiểu và tránh ghép dữ liệu người dùng trực tiếp vào chuỗi SQL. Không thể dùng bind parameter để thay tên bảng hoặc tên cột. Ví dụ `FROM :tableName` không có nghĩa driver sẽ thay parameter bằng một identifier SQL.

Nếu tên bảng hoặc cột thực sự phải thay đổi theo lựa chọn runtime, cần dùng một danh sách cho phép (allowlist) gồm những identifier đã được định nghĩa trước và xây dựng SQL theo quy tắc an toàn. Không ghép trực tiếp tên identifier tùy ý từ request người dùng.

## 3. NamingStrategy mặc định của Spring Data Relational

Spring Data Relational dùng **NamingStrategy** để suy ra tên relational từ class và property. Quy ước mặc định thường chuyển tên camelCase sang snake_case.

Ví dụ:

| Java model | Identifier mặc định thường gặp |
|---|---|
| Class `CustomerOrder` | Bảng `customer_order` |
| Property `createdAt` | Cột `created_at` |
| Property `customerId` | Cột `customer_id` |
| Property `postalCode` | Cột `postal_code` |

Mục đích của naming strategy là giúp mô hình Java giữ quy ước đặt tên phù hợp với ngôn ngữ lập trình, trong khi database dùng quy ước relational nhất quán. Nhờ đó, không cần viết annotation cho mọi property nếu tên đã tuân theo convention.

Tên thực tế còn chịu ảnh hưởng của annotation mapping, schema, dialect và phiên bản Spring Data. Khi tích hợp với một schema có sẵn, nên kiểm tra metadata mapping và SQL thực tế thay vì chỉ suy đoán từ tên class.

### 3.1. Naming strategy áp dụng ở đâu?

NamingStrategy tham gia vào việc suy ra các identifier như:

- Tên bảng từ kiểu entity.
- Tên cột từ thuộc tính.
- Tên cột khóa dùng để liên kết đối tượng thành phần với aggregate root.
- Tên cột tham chiếu ngược trong những mapping collection có liên quan.

Các annotation mapping tường minh như `@Table` và `@Column` cho phép chỉ định tên cụ thể tại từng entity hoặc property. Đây là cách thích hợp khi một bảng legacy có quy ước khác với phần còn lại của ứng dụng.

### 3.2. Không nên giả định có tự động pluralize

Naming strategy mặc định không nên được hiểu là một bộ quy tắc tự động đổi tên class sang danh từ số nhiều theo ngôn ngữ. Ví dụ, class `CustomerOrder` thường được chuyển theo quy tắc camelCase thành `customer_order`; không nên mặc định framework sẽ tự đổi thành `customer_orders`.

Nếu schema đang dùng tên số nhiều, tên viết tắt hoặc tiền tố riêng, hãy khai báo bằng annotation hoặc cung cấp naming strategy phù hợp. Điều quan trọng là quy tắc phải nhất quán và khớp với schema đã triển khai.

## 4. Ghi đè tên bảng và cột bằng annotation

### 4.1. Dùng @Table để chỉ định tên bảng

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;
}
~~~

Ở đây, Spring Data dùng bảng `purchase_orders` cho entity PurchaseOrder. Việc đặt tên bảng rõ ràng giúp mô hình Java không bị buộc phải trùng với quy ước tên bảng trong database.

Có thể chỉ định schema nếu ứng dụng cần phân vùng đối tượng theo schema. Cú pháp annotation và cách dialect tạo SQL cần được xác nhận theo phiên bản đang dùng. Khi có nhiều schema hoặc database, nên ghi rõ schema trong metadata hoặc cấu hình connection phù hợp thay vì dựa vào search path ngầm định.

### 4.2. Dùng @Column để chỉ định tên cột

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_status")
    private String status;

    @Column("customer_id")
    private Long customerId;
}
~~~

Property Java vẫn có thể là `status` và `customerId`, trong khi database sử dụng `order_status` và `customer_id`. Điều này hữu ích khi kết nối với schema đã tồn tại hoặc khi tên cột cần phản ánh thuật ngữ database riêng.

Annotation tường minh cũng giúp người đọc thấy rõ mapping mà không phải tìm hiểu toàn bộ naming strategy. Tuy nhiên, không cần lặp lại annotation cho mọi thuộc tính nếu tên mặc định đã đúng quy ước.

### 4.3. Tên cột trong mapping thành phần

Với collection được ánh xạ bằng `@MappedCollection`, tên cột liên kết aggregate root và cột khóa collection cũng là identifier. Ví dụ:

~~~java
@MappedCollection(idColumn = "order_id", keyColumn = "line_no")
private List<OrderLine> lines;
~~~

- `idColumn` chỉ định cột ở bảng thành phần dùng để lưu ID của aggregate root.
- `keyColumn` chỉ định cột dùng làm khóa hoặc vị trí của phần tử collection theo mapping.

Các tên này phải khớp với schema. Nếu schema dùng tên legacy hoặc tên cần quote, có thể chỉ định theo cú pháp quoted identifier mà Spring Data Relational hỗ trợ. Cần kiểm tra SQL sinh ra và schema thực tế khi sử dụng collection mapping.

## 5. Quoted identifier là gì?

### 5.1. Vì sao SQL có dấu quote cho identifier?

Trong SQL, một identifier không quote thường được database xử lý theo quy tắc từ vựng và chuẩn hóa riêng. Một identifier có quote được hiểu như tên được chỉ định tường minh, nhờ đó có thể dùng tên trùng từ khóa, giữ chữ hoa/chữ thường hoặc chứa ký tự đặc biệt mà quy tắc không quote không cho phép.

Ví dụ với PostgreSQL:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30)
);
~~~

Tên `orders` và `status` không cần quote. PostgreSQL chuẩn hóa identifier không quote thành chữ thường.

Nếu tạo bảng với tên có chữ hoa được quote:

~~~sql
CREATE TABLE "PurchaseOrder" (
    "OrderId" BIGINT PRIMARY KEY,
    "orderStatus" VARCHAR(30)
);
~~~

Các identifier có quote được giữ đúng chữ hoa/chữ thường. Khi truy vấn, cần dùng chính xác tên đã tạo:

~~~sql
SELECT "OrderId", "orderStatus"
FROM "PurchaseOrder";
~~~

Truy vấn `SELECT OrderId FROM PurchaseOrder` không tương đương với truy vấn trên trong PostgreSQL, vì identifier không quote được chuẩn hóa thành chữ thường.

### 5.2. Từ khóa SQL và tên có ký tự đặc biệt

Một số từ như `order`, `group`, `user` hoặc `select` có thể xung đột với cú pháp SQL tùy database và vị trí sử dụng. Identifier có dấu cách hoặc ký tự đặc biệt cũng thường cần quote.

Ví dụ tên bảng `Order` hoặc tên cột `group` có thể làm câu SQL khó đọc hoặc gây lỗi cú pháp nếu dùng không đúng quy tắc. Có thể giải quyết theo hai hướng:

1. Đổi tên bảng/cột thành tên an toàn, chẳng hạn `purchase_orders`, `order_group`.
2. Giữ tên hiện tại nhưng đánh dấu identifier cần quote và dùng đúng cách viết trong SQL.

Nếu có quyền thiết kế schema mới, nên ưu tiên tên đơn giản, nhất quán và tránh từ khóa SQL. Quoted identifier hữu ích khi tích hợp schema legacy hoặc khi có yêu cầu bắt buộc giữ nguyên tên.

## 6. Đánh dấu quoted identifier trong Spring Data Relational

Spring Data Relational có cơ chế biểu diễn identifier có quote trong mapping metadata. Khi khai báo tên trong annotation, có thể dùng **backtick** bao quanh identifier để đánh dấu nó cần được quote.

Ví dụ:

~~~java
@Table("`Order`")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("`group`")
    private String group;
}
~~~

Trong metadata Spring Data, backtick là dấu đánh dấu quoted identifier. Khi tạo SQL, Spring Data sử dụng quy tắc quote phù hợp với dialect của database. Không nên hiểu rằng backtick sẽ luôn được gửi nguyên văn đến database.

Với PostgreSQL, identifier tương ứng có thể được render thành dấu ngoặc kép:

~~~sql
SELECT "id", "group"
FROM "Order";
~~~

Cú pháp quote ở tầng SQL phụ thuộc database. Ví dụ, PostgreSQL dùng dấu ngoặc kép cho quoted identifier; MySQL thường dùng backtick; SQL Server hỗ trợ dấu ngoặc vuông hoặc dấu ngoặc kép khi cấu hình quoted identifier phù hợp. Spring Data dựa trên dialect để xử lý identifier được đánh dấu quoted trong metadata.

### 6.1. Quoting giữ nguyên chữ hoa/chữ thường

Giả sử schema PostgreSQL có bảng được tạo như sau:

~~~sql
CREATE TABLE "PurchaseOrder" (
    "OrderId" BIGINT PRIMARY KEY,
    "orderStatus" VARCHAR(30)
);
~~~

Entity mapping cần giữ đúng cách viết của từng identifier:

~~~java
@Table("`PurchaseOrder`")
public class PurchaseOrder {

    @Id
    @Column("`OrderId`")
    private Long id;

    @Column("`orderStatus`")
    private String status;
}
~~~

Nếu chỉ quote tên bảng nhưng không quote các cột cần giữ nguyên chữ hoa/chữ thường, SQL có thể tìm sai cột. Ngược lại, nếu schema dùng tên chữ thường không quote, việc quote một tên viết hoa sẽ làm identifier trở thành một tên khác trong PostgreSQL.

Quy tắc quan trọng là **tên và trạng thái quoted/unquoted trong mapping phải khớp với schema đã tạo**. Không nên thêm quote tùy tiện với hy vọng database sẽ tự bỏ qua khác biệt chữ hoa/chữ thường.

### 6.2. Quoted identifier với @MappedCollection

Các cột liên kết collection cũng cần khớp schema. Ví dụ metadata:

~~~java
@MappedCollection(
        idColumn = "`order_id`",
        keyColumn = "`line_no`"
)
private List<OrderLine> lines;
~~~

Cách đánh dấu quoted cần được kiểm tra với phiên bản Spring Data Relational đang dùng và dialect tương ứng. Nếu schema sử dụng tên snake_case chữ thường không phải từ khóa, thường không cần quote các cột này.

### 6.3. Dùng SqlIdentifier trong API mapping

Ở tầng Spring Data Relational, identifier còn được biểu diễn bằng kiểu **SqlIdentifier**. Kiểu này lưu tên và trạng thái quoted/unquoted tách biệt, thay vì phải tự ghép ký tự quote vào mọi câu SQL.

Ví dụ về ý nghĩa API:

~~~java
SqlIdentifier.unquoted("customer_order");
SqlIdentifier.quoted("PurchaseOrder");
~~~

- `unquoted(...)` biểu diễn identifier không yêu cầu quote.
- `quoted(...)` biểu diễn identifier cần được quote khi render SQL.

Khi identifier được render, dialect chịu trách nhiệm dùng ký tự quote phù hợp. Không nên tự nhét dấu ngoặc kép hoặc backtick vào nội dung của SqlIdentifier rồi lại đánh dấu quoted, vì có thể tạo ra quote lặp hoặc tên không khớp schema.

## 7. Khi nào nên quote identifier?

Có thể cân nhắc quote trong những trường hợp sau:

| Trường hợp | Ví dụ | Cách xử lý |
|---|---|---|
| Trùng từ khóa SQL | `order`, `group` | Đổi tên nếu có thể; nếu phải giữ thì quote |
| Cần giữ chữ hoa/chữ thường | `PurchaseOrder` | Quote nhất quán ở schema và mapping |
| Tên chứa dấu cách | `Order Details` | Quote, nhưng nên cân nhắc đổi tên |
| Tên có ký tự đặc biệt | `customer-code` | Quote hoặc đổi sang tên đơn giản |
| Schema legacy | Bảng/cột đã được tạo với quy ước riêng | Mapping tường minh và quote đúng khi cần |
| Tên thông thường theo snake_case | `customer_order` | Thường không cần quote |

Quote không phải công cụ để sửa mọi vấn đề về naming. Nếu có thể đổi schema, tên đơn giản thường dễ làm việc hơn với SQL viết tay, migration, báo cáo, công cụ quản trị và nhiều hệ quản trị cơ sở dữ liệu.

## 8. NamingStrategy tùy chỉnh

### 8.1. Khi nào cần custom naming strategy?

Một dự án có thể phải tuân theo quy ước riêng, chẳng hạn:

- Tất cả bảng có tiền tố `app_`.
- Tên bảng và cột dùng một quy tắc snake_case riêng.
- Bảng được phân nhóm theo schema.
- Tên cột khóa ngoại theo một quy ước nhất quán.
- Hệ thống mới phải tương thích với database legacy có tên không theo quy tắc mặc định.

Khi số lượng override lớn, việc viết `@Table` và `@Column` ở mọi class có thể tạo ra nhiều metadata lặp lại. NamingStrategy tùy chỉnh giúp tập trung quy tắc ở một nơi.

### 8.2. Ý tưởng cấu hình NamingStrategy

Có thể cung cấp một bean **NamingStrategy** trong application context để Spring Data Relational sử dụng khi suy ra identifier.

Ví dụ minh họa chiến lược thêm tiền tố `tbl_` vào tên bảng và chuyển tên class sang snake_case:

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.NamingStrategy;
import org.springframework.data.relational.core.sql.SqlIdentifier;

@Configuration
class RelationalNamingConfiguration {

    @Bean
    NamingStrategy namingStrategy() {
        return new NamingStrategy() {
            @Override
            public SqlIdentifier getTableName(Class<?> type) {
                String snakeCase = type.getSimpleName()
                        .replaceAll("([a-z0-9])([A-Z])", "$1_$2")
                        .toLowerCase(Locale.ROOT);

                return SqlIdentifier.unquoted("tbl_" + snakeCase);
            }
        };
    }
}
~~~

Với class `CustomerOrder`, tên bảng được suy ra là `tbl_customer_order`. Những phương thức không được override tiếp tục dùng hành vi mặc định của NamingStrategy nếu phiên bản Spring Data cung cấp default implementation tương ứng.

Đây là ví dụ về một quy tắc đơn giản. Khi triển khai thật, cần kiểm tra API NamingStrategy của đúng phiên bản Spring Data Relational đang sử dụng, đặc biệt nếu muốn tùy chỉnh schema, column, key column hoặc reverse column name. Cũng cần xác nhận Spring Boot auto-configuration đang sử dụng bean tùy chỉnh đó.

### 8.3. Tùy chỉnh tên cột

Nếu dự án muốn quy tắc riêng cho property, có thể override phương thức lấy tên cột. Ví dụ về ý tưởng:

~~~java
@Override
public SqlIdentifier getColumnName(RelationalPersistentProperty property) {
    return SqlIdentifier.unquoted(
            property.getName().replaceAll("([a-z0-9])([A-Z])", "$1_$2")
                    .toLowerCase(Locale.ROOT));
}
~~~

Phần triển khai này giả định đã import `RelationalPersistentProperty` từ Spring Data Relational. Cần giữ nhất quán với quy tắc đặt tên khóa ngoại và các cột collection; nếu chỉ override tên cột thông thường mà bỏ qua key/reverse column, schema có thể không khớp với SQL mà mapping tạo ra.

### 8.4. Khi nào nên dùng annotation thay cho strategy?

Dùng annotation khi một entity hoặc một property là ngoại lệ riêng:

~~~java
@Table("legacy_customer")
class Customer {
    @Id
    private Long id;

    @Column("CUST_EMAIL")
    private String email;
}
~~~

Dùng NamingStrategy khi quy tắc lặp lại trên nhiều entity và cần được quản lý tập trung. Có thể kết hợp cả hai: strategy cung cấp mặc định cho phần lớn mô hình, annotation ghi đè những trường hợp đặc biệt.

Tránh tạo naming strategy quá phức tạp với nhiều ngoại lệ khó đoán. Một quy tắc dễ hiểu và có integration test sẽ giúp schema ổn định hơn.

## 9. Quoted identifier trong SQL viết tay

Mapping metadata và SQL viết tay là hai ngữ cảnh khác nhau.

Khi dùng repository hoặc template mapping entity, Spring Data có metadata về table, column và trạng thái quote. Nhưng khi viết câu SQL trực tiếp bằng `@Query` hoặc `DatabaseClient`, người phát triển chịu trách nhiệm viết identifier theo cú pháp của database.

Ví dụ PostgreSQL với tên bảng và cột có quote:

~~~java
return databaseClient.sql("""
        SELECT "OrderId", "orderStatus"
        FROM "PurchaseOrder"
        WHERE "orderStatus" = :status
        """)
    .bind("status", status)
    .map((row, metadata) ->
            row.get("OrderId", Long.class))
    .all();
~~~

Ở đây:

- `"PurchaseOrder"`, `"OrderId"` và `"orderStatus"` là identifier được quote theo cú pháp PostgreSQL.
- `:status` là bind parameter cho giá trị dữ liệu.
- DatabaseClient không thể thay thế identifier bằng bind parameter.

Nếu chuyển câu SQL này sang MySQL hoặc SQL Server, cần kiểm tra và điều chỉnh cú pháp quote theo dialect tương ứng. Không nên sao chép nguyên dấu quote của PostgreSQL sang mọi database.

### 9.1. Identifier trong @Query

Với `@Query`, câu SQL được viết tường minh. Nếu schema dùng identifier cần quote, hãy dùng cách quote mà database mục tiêu yêu cầu. Annotation mapping `@Table` không tự viết lại mọi identifier nằm trong chuỗi SQL tùy chỉnh.

~~~java
@Query("""
    SELECT "OrderId", "orderStatus"
    FROM "PurchaseOrder"
    WHERE "orderStatus" = :status
    """)
Flux<OrderSummary> findByStatus(String status);
~~~

Tên bind parameter phải tương ứng với cách Spring Data bind tham số của phương thức theo phiên bản đang dùng. Với query phức tạp, có thể khai báo `@Param` để tên parameter rõ ràng.

### 9.2. Không nối identifier từ input không tin cậy

Không viết:

~~~java
String sql = "SELECT * FROM " + request.getParameter("table");
~~~

Cách làm này cho phép input ảnh hưởng trực tiếp đến cấu trúc SQL. Bind parameter không áp dụng cho table name, vì vậy phải dùng allowlist nếu thực sự cần lựa chọn bảng động:

~~~java
Map<String, String> allowedTables = Map.of(
        "orders", "orders",
        "customers", "customers"
);

String table = allowedTables.get(requestedResource);
if (table == null) {
    return Mono.error(new IllegalArgumentException("Unsupported resource"));
}

String sql = "SELECT id FROM " + table + " WHERE status = :status";

return databaseClient.sql(sql)
        .bind("status", status)
        .map((row, metadata) -> row.get("id", Long.class))
        .all();
~~~

Ví dụ chỉ minh họa nguyên tắc allowlist. Trong hệ thống thực tế, nên tránh dynamic table nếu không có nhu cầu rõ ràng; nếu có, giá trị lấy từ allowlist phải là identifier do ứng dụng kiểm soát, không phải chuỗi tùy ý từ request.

## 10. Khác biệt về quote và chữ hoa/chữ thường giữa các database

Cú pháp và quy tắc chuẩn hóa identifier không hoàn toàn giống nhau giữa các hệ quản trị.

| Database | Cách quote identifier thường gặp | Quy tắc đáng chú ý |
|---|---|---|
| PostgreSQL | Dấu ngoặc kép: `"name"` | Identifier không quote được chuẩn hóa thành chữ thường; identifier quote giữ nguyên cách viết |
| MySQL | Backtick, ví dụ `name` | Backtick thường dùng để quote; hành vi phân biệt chữ hoa/chữ thường của tên bảng còn phụ thuộc hệ điều hành và cấu hình |
| SQL Server | Dấu ngoặc vuông: `[name]` hoặc dấu ngoặc kép trong chế độ phù hợp | Cần xét cấu hình QUOTED_IDENTIFIER và collation |
| Oracle | Dấu ngoặc kép: `"name"` | Identifier không quote thường được chuẩn hóa thành chữ hoa; quoted identifier giữ nguyên cách viết |

Spring Data Relational sử dụng dialect để render identifier có trạng thái quoted. Tuy nhiên, raw SQL viết tay vẫn cần theo cú pháp của database mà ứng dụng đang kết nối.

### 10.1. Ví dụ PostgreSQL

Tên không quote:

~~~sql
CREATE TABLE customer_order (
    customer_id BIGINT,
    created_at TIMESTAMP
);
~~~

Có thể truy vấn bằng chữ thường hoặc chữ hoa không quote vì PostgreSQL chuẩn hóa identifier không quote:

~~~sql
SELECT CUSTOMER_ID, CREATED_AT
FROM CUSTOMER_ORDER;
~~~

Tên có quote và chữ hoa:

~~~sql
CREATE TABLE "CustomerOrder" (
    "CustomerId" BIGINT,
    "CreatedAt" TIMESTAMP
);
~~~

Khi đó cần dùng chính xác cách viết:

~~~sql
SELECT "CustomerId", "CreatedAt"
FROM "CustomerOrder";
~~~

### 10.2. Tránh trộn lẫn hai quy ước

Một schema có cả `customer_order`, `CustomerOrder`, `CUSTOMER_ORDER` và những identifier được quote theo cách khác nhau sẽ khó bảo trì. Cần thống nhất quy tắc khi tạo schema mới và ghi rõ ngoại lệ của schema legacy.

Nếu database đã tồn tại, hãy kiểm tra metadata thực tế trong database trước khi thay annotation. Đổi cách quote có thể làm ứng dụng tìm đến một identifier khác dù tên hiển thị trông gần giống nhau.

## 11. Những lỗi thường gặp khi đặt tên và quote identifier

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Table hoặc column không tồn tại | NamingStrategy suy ra tên khác schema | Dùng @Table/@Column hoặc chỉnh strategy cho khớp |
| Lỗi cú pháp gần từ khóa SQL | Identifier trùng reserved word nhưng không được quote | Đổi tên hoặc đánh dấu quoted identifier |
| PostgreSQL báo relation/column không tồn tại dù tên nhìn giống | Khác biệt chữ hoa/chữ thường do quoted và unquoted identifier | Kiểm tra tên chính xác trong catalog và dùng cùng cách viết |
| SQL chạy qua repository nhưng @Query thất bại | Mapping metadata không tự sửa identifier trong raw SQL | Viết quote đúng dialect trong câu query |
| SQL hoạt động ở PostgreSQL nhưng lỗi ở MySQL | Dùng cú pháp quote hoặc tính năng riêng của database khác | Dùng dialect và SQL tương ứng |
| Collection mapping không tìm thấy cột liên kết | idColumn/keyColumn không khớp schema | Kiểm tra @MappedCollection và DDL |
| Tên bảng có tiền tố sai | Custom NamingStrategy không được áp dụng hoặc bị override | Kiểm tra bean, auto-configuration và annotation |
| Tên bảng bị quote hai lần hoặc có ký tự quote trong tên | Trộn dấu quote SQL vào identifier đã được đánh dấu quoted | Dùng SqlIdentifier.quoted hoặc cú pháp annotation phù hợp, không tự ghép quote |

### 11.1. Lỗi tên bảng hoặc cột không tồn tại

Ví dụ Spring Data mặc định suy ra `purchase_order`, nhưng schema thật là `purchase_orders`. Khi đó, database báo không tìm thấy relation/table. Hãy kiểm tra tên được mapping, naming strategy và annotation tường minh.

Với PostgreSQL, cũng cần kiểm tra schema đang được dùng và search_path. Một bảng tồn tại trong schema khác vẫn có thể không được tìm thấy nếu connection đang dùng schema mặc định khác.

### 11.2. Lỗi do reserved word

Nếu tên cột là `group`, SQL viết tay có thể bị hiểu là từ khóa. Có thể đổi thành `customer_group`, hoặc quote đúng theo database. Nếu dùng mapping metadata, đánh dấu quoted identifier trong annotation thay vì tự nhúng ký tự quote SQL vào mọi nơi.

### 11.3. Lỗi do chữ hoa/chữ thường

Với PostgreSQL, `OrderId` không quote và `"OrderId"` không cùng cách xử lý. Identifier không quote được chuyển thành chữ thường, trong khi identifier quote giữ nguyên chữ hoa/chữ thường. Kiểm tra DDL gốc và catalog để xác định chính xác tên.

### 11.4. Lỗi do SQL viết tay không cùng quy tắc mapping

Entity mapping có thể đã chỉ định `@Table("`PurchaseOrder`")`, nhưng câu `@Query` vẫn dùng `FROM purchase_order`. Hai câu lệnh đang tham chiếu hai identifier khác nhau. Cần dùng đúng tên và quote trong SQL viết tay.

## 12. Quy trình lựa chọn naming strategy cho dự án

Có thể áp dụng trình tự sau khi thiết kế schema hoặc tích hợp database hiện có:

1. **Xác định quy ước database:** snake_case, chữ thường, tiền tố bảng, schema và cách đặt tên khóa ngoại.
2. **Kiểm tra identifier hiện hữu:** đọc DDL hoặc metadata database để biết chính xác tên và trạng thái quote.
3. **Chọn NamingStrategy:** dùng mặc định nếu phù hợp; custom strategy nếu có quy tắc chung khác.
4. **Ghi đè ngoại lệ:** dùng @Table, @Column và các annotation mapping liên quan cho tên đặc biệt.
5. **Chỉ quote khi cần:** ưu tiên đổi tên tránh reserved word; nếu phải giữ thì quote nhất quán.
6. **Đồng bộ raw SQL:** rà soát @Query, DatabaseClient và migration để chúng dùng đúng identifier theo dialect.
7. **Kiểm thử tích hợp:** xác nhận insert, select, update, delete, collection mapping và migration với database thực tế.
8. **Quan sát SQL:** bật logging có kiểm soát ở môi trường phát triển để xác nhận tên được render đúng.
9. **Giữ schema ổn định:** thay đổi tên bảng/cột qua migration có version thay vì sửa database thủ công trên từng môi trường.

Sơ đồ quyết định đơn giản:

~~~text
Tên Java có theo quy ước mặc định?
             |
        +----+----+
        |         |
       Có        Không
        |         |
        v         v
 Dùng naming   Dùng @Table /
 strategy      @Column hoặc
 mặc định      NamingStrategy riêng
        |         |
        +----+----+
             |
             v
 Identifier có reserved word,
 chữ hoa cần giữ hoặc ký tự đặc biệt?
             |
        +----+----+
        |         |
       Không      Có
        |         |
        v         v
 Không cần     Đánh dấu quoted
 quote         trong mapping metadata
        |         |
        +----+----+
             |
             v
 Kiểm thử mapping và raw SQL
 trên database mục tiêu
~~~

## 13. Kiểm thử mapping và quoted identifier

Unit test có thể kiểm tra domain logic, nhưng không đủ để xác nhận database hiểu tên bảng/cột như mong đợi. Cần integration test với database cùng loại và phiên bản tương thích với môi trường triển khai.

Một số trường hợp nên kiểm tra:

- Entity dùng tên mặc định camelCase được ánh xạ đúng sang snake_case.
- @Table và @Column ghi đè đúng tên schema.
- Identifier reserved word được quote và truy vấn thành công.
- Identifier có chữ hoa được truy cập đúng theo quy tắc database.
- @MappedCollection sử dụng đúng idColumn và keyColumn.
- @Query và DatabaseClient dùng cú pháp quote đúng dialect.
- Migration tạo đúng tên identifier mà mapping mong đợi.
- Insert, update, select và delete đều hoạt động trên schema thực tế.

Có thể dùng Testcontainers để chạy database cô lập cho mỗi lượt kiểm thử. Điều này giúp tránh tình trạng test chạy được trên H2 nhưng thất bại trên PostgreSQL hoặc MySQL do khác biệt về identifier, kiểu dữ liệu và SQL dialect.

Không nên chỉ kiểm tra rằng Spring ApplicationContext khởi động thành công. Nên thực hiện truy vấn thật hoặc lưu/đọc một entity để xác nhận mapping đã hoạt động.

## 14. Kết luận

NamingStrategy giúp Spring Data Relational suy ra tên bảng, cột và identifier liên kết từ mô hình Java theo một quy ước nhất quán. Khi cần khớp schema legacy hoặc ngoại lệ, có thể ghi đè bằng @Table, @Column, @MappedCollection hoặc cung cấp NamingStrategy tùy chỉnh.

Quoted identifier dùng để xử lý tên trùng từ khóa SQL, cần giữ chữ hoa/chữ thường hoặc chứa ký tự đặc biệt. Spring Data Relational cho phép đánh dấu quoted identifier trong mapping metadata và dùng dialect để render ký tự quote phù hợp. Với SQL viết tay trong @Query hoặc DatabaseClient, người phát triển vẫn phải dùng đúng cú pháp của database mục tiêu.

Cần luôn phân biệt identifier với giá trị dữ liệu: tên bảng/cột không thể thay bằng bind parameter, còn giá trị đầu vào phải được bind thay vì ghép chuỗi. Một quy ước tên đơn giản, metadata mapping rõ ràng và integration test trên database thật sẽ giúp tránh lỗi không tìm thấy bảng/cột và giảm khác biệt giữa các môi trường.

