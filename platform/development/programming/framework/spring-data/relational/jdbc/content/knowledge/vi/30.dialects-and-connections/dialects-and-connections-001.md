# Vai trò của Dialect trong SQL sinh tự động và khả năng cơ sở dữ liệu

Spring Data JDBC hỗ trợ nhiều hệ quản trị quan hệ nhưng không thể giả định mọi database dùng cùng một cú pháp SQL hoặc có cùng khả năng. PostgreSQL, MySQL, Oracle, SQL Server và các database khác khác nhau ở cách giới hạn kết quả, khóa hàng, tạo ID, đặt dấu nháy cho tên bảng/cột, xử lý kiểu dữ liệu và nhiều chi tiết khác.

**Dialect** là lớp trừu tượng mô tả những khác biệt đó. Spring Data JDBC dùng dialect tương ứng với database để tạo SQL phù hợp khi chạy các thao tác mà framework quản lý, chẳng hạn lưu aggregate, truy vấn repository, phân trang, sắp xếp và khóa bi quan.

Dialect còn mô tả khả năng của database. Nếu một tính năng không được hỗ trợ, framework có thể chọn cách xử lý khác hoặc báo lỗi rõ ràng. Nhờ vậy, ứng dụng có thể dùng một mô hình lập trình nhất quán trong khi SQL cuối cùng vẫn phù hợp với database đang kết nối.

Bài học trình bày dialect làm gì, cách Spring Data JDBC phát hiện dialect, những điểm SQL generation chịu ảnh hưởng, danh sách database được hỗ trợ trực tiếp, và cách tích hợp một database chưa có dialect.

## 1. Dialect là gì?

Trong SQL, cùng một ý định có thể được biểu diễn bằng những cú pháp khác nhau. Ví dụ, ứng dụng muốn lấy 10 hàng bắt đầu từ vị trí 20:

~~~sql
-- PostgreSQL / MySQL: cú pháp minh họa
SELECT id, status
FROM orders
ORDER BY id
LIMIT 10 OFFSET 20;
~~~

Một database khác có thể dùng cú pháp:

~~~sql
-- SQL Server: cú pháp minh họa
SELECT id, status
FROM orders
ORDER BY id
OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY;
~~~

Ý nghĩa nghiệp vụ giống nhau: lấy một lát dữ liệu đã sắp xếp. Cú pháp SQL khác nhau.

Dialect cung cấp quy tắc để Spring Data render câu SQL phù hợp. Thay vì tự viết nhánh `if database == ...` trong mọi repository hoặc service, framework sử dụng dialect đã được chọn cho kết nối hiện tại.

Trong Spring Data JDBC, interface JDBC chuyên biệt là `JdbcDialect`, thuộc package:

~~~java
import org.springframework.data.jdbc.core.dialect.JdbcDialect;
~~~

`JdbcDialect` kế thừa interface chung `Dialect` của Spring Data Relational. Interface chung mô tả nhiều đặc điểm SQL có thể dùng cho cả Spring Data JDBC và Spring Data R2DBC; `JdbcDialect` bổ sung những phần riêng của JDBC driver, như hỗ trợ cột array và tạo SQL type.

### Dialect không phải là database driver

| Thành phần | Vai trò |
| --- | --- |
| Database server | Thực thi SQL, quản lý bảng, transaction, constraint và dữ liệu |
| JDBC driver | Kết nối Java với database, gửi SQL và chuyển kết quả thành kiểu Java |
| DataSource | Cung cấp JDBC Connection |
| JdbcDialect | Mô tả cú pháp và khả năng database để Spring Data tạo SQL phù hợp |
| Spring Data JDBC | Ánh xạ aggregate và điều phối câu SQL qua JDBC infrastructure |

Dialect không mở kết nối thay cho driver, không thay thế DataSource và không thực thi câu SQL. Nó cung cấp thông tin cho các thành phần SQL generation và mapping.

## 2. Vì sao Spring Data JDBC cần Dialect?

Spring Data JDBC tạo SQL từ metadata entity và thao tác repository. Những câu SQL này phải thích ứng với database.

Ví dụ một aggregate có thể cần:

- `INSERT` root và lấy ID do database sinh.
- `UPDATE` một hàng theo ID và version.
- `DELETE` các entity con trước khi xóa root theo quan hệ aggregate.
- `SELECT` với điều kiện `WHERE`, sắp xếp và phân trang.
- `SELECT` có lock clause cho pessimistic locking.
- Truy vấn `EXISTS` hoặc `COUNT`.
- Truy vấn lấy giá trị tiếp theo của sequence.
- Bind kiểu dữ liệu đặc thù như array hoặc kiểu vendor-specific.

Một phần các thao tác này có cú pháp SQL chuẩn. Một phần khác phụ thuộc database hoặc driver. Dialect gom các khác biệt vào một nơi để framework dùng nhất quán.

### 2.1. Một ý định, nhiều cách render

Ví dụ ứng dụng khai báo repository:

~~~java
public interface OrderRepository
        extends CrudRepository<Order, Long> {

    List<Order> findByStatusOrderByCreatedAtDesc(String status);
}
~~~

Spring Data phân tích tên method để xác định property, điều kiện và thứ tự. Framework tạo cấu trúc truy vấn rồi dùng dialect để render cú pháp SQL phù hợp.

SQL minh họa có thể có dạng:

~~~sql
SELECT ...
FROM orders
WHERE status = ?
ORDER BY created_at DESC;
~~~

Câu SQL thực tế còn phụ thuộc tên cột, identifier quoting, mapping, database và phiên bản framework.

### 2.2. Dialect không dịch mọi câu SQL của ứng dụng

Dialect chủ yếu phục vụ SQL do Spring Data JDBC sinh từ các abstraction mà framework quản lý, như repository query methods, `Query`/`Criteria`, thao tác aggregate và các tính năng SQL tương ứng.

Nếu ứng dụng tự viết SQL bằng `@Query`, `JdbcTemplate`, JDBC client hoặc MyBatis, SQL đó vẫn phải tuân theo cú pháp database mục tiêu. Không nên kỳ vọng dialect tự chuyển một câu SQL PostgreSQL thành cú pháp MySQL hay SQL Server.

Ví dụ, câu SQL có `RETURNING`, `ON CONFLICT`, hàm JSON riêng hoặc cú pháp hint của vendor vẫn là SQL do người viết chịu trách nhiệm tương thích.

## 3. Dialect nằm ở đâu trong quá trình sinh SQL?

Có thể hình dung pipeline đơn giản:

~~~mermaid
flowchart TD
    A["Repository method hoặc thao tác aggregate"] --> B["Spring Data phân tích metadata và ý định"]
    B --> C["Tạo cấu trúc SQL / câu lệnh"]
    D["JdbcDialect đã được chọn"] --> E["Quy tắc cú pháp và khả năng database"]
    C --> F["SQL rendering"]
    E --> F
    F --> G["SQL phù hợp với database"]
    G --> H["JDBC driver"]
    H --> I["Database thực thi"]
~~~

Repository method mô tả **muốn làm gì**. Mapping metadata mô tả **entity và property tương ứng với bảng/cột nào**. Dialect mô tả **cách database hiện tại yêu cầu câu SQL và kiểu dữ liệu**. JDBC driver gửi SQL tới server.

Điều này giải thích vì sao cùng một repository có thể chạy trên nhiều database được hỗ trợ mà không phải viết một repository riêng cho từng vendor, miễn là ứng dụng không phụ thuộc vào SQL riêng của một database.

## 4. Spring Data JDBC phát hiện Dialect như thế nào?

Trong cấu hình chuẩn, Spring Data JDBC dùng `AbstractJdbcConfiguration` để đăng ký các bean cần thiết. Bean `JdbcDialect` được tạo bằng cách gọi:

~~~java
jdbcDialect(NamedParameterJdbcOperations operations)
~~~

Cấu hình mặc định sử dụng `DialectResolver` để xác định database thông qua JDBC connection. Resolver thường kiểm tra metadata của connection, ví dụ thông tin do `Connection.getMetaData()` cung cấp.

Luồng khái niệm:

~~~text
DataSource
    ↓
JDBC Connection
    ↓
DatabaseMetaData
    ↓
DialectResolver
    ↓
JdbcDialect tương ứng
    ↓
SQL generation và JDBC mapping
~~~

Với Spring Boot, khi starter `spring-boot-starter-data-jdbc` và một `DataSource` hợp lệ đã được cấu hình, phần lớn hạ tầng còn lại được auto-configuration thiết lập. Ứng dụng thông thường không cần tự tạo dialect bean cho một database đã được hỗ trợ.

Nếu resolver không tìm thấy dialect phù hợp, quá trình khởi tạo Spring Data JDBC thất bại với lỗi không thể resolve dialect. Đây là lỗi cấu hình/tích hợp database, không phải lỗi SQL của một repository method cụ thể.

## 5. Các database được hỗ trợ trực tiếp

Theo tài liệu Spring Data Relational 4.1.2, Spring Data JDBC có dialect tích hợp cho các database sau:

| Database | Dialect JDBC tích hợp |
| --- | --- |
| IBM Db2 | Có |
| H2 | Có |
| HSQLDB | Có |
| MariaDB | Có |
| Microsoft SQL Server | Có |
| MySQL | Có |
| Oracle | Có |
| PostgreSQL | Có |

Danh sách này phụ thuộc phiên bản Spring Data Relational. Khi nâng cấp framework hoặc chọn database mới, hãy kiểm tra danh sách trong tài liệu đúng phiên bản đang dùng.

Có JDBC driver không đồng nghĩa Spring Data JDBC tự động có dialect cho database đó. Một database có driver JDBC tốt nhưng chưa có dialect vẫn có thể không khởi động được Spring Data JDBC.

### Phân biệt database, dialect và phiên bản driver

Một database có thể có nhiều phiên bản server và driver. Dialect được chọn dựa trên metadata kết nối và những khả năng mà implementation hỗ trợ. Việc database xuất hiện trong danh sách không có nghĩa mọi tính năng của nó đều được Spring Data JDBC khai thác.

Ví dụ, dialect có thể hỗ trợ truy vấn cơ bản nhưng không hỗ trợ một tính năng đặc thù như array column hoặc single-query loading. Khi một feature không được hỗ trợ, framework có thể dùng đường xử lý khác hoặc ném exception nếu không có fallback.

Không nên chỉ kiểm tra “database có trong danh sách” rồi kết luận toàn bộ tính năng đều tương thích. Cần kiểm tra từng capability mà ứng dụng thực sự sử dụng.

## 6. Những khả năng mà Dialect mô tả

Interface `Dialect` không chỉ chứa một tên database. Nó cung cấp các strategy và capability mà SQL generator hoặc mapping layer cần dùng.

Một số method quan trọng trong Spring Data Relational 4.1.x:

| Thành phần | Vai trò |
| --- | --- |
| `getIdentifierProcessing()` | Quy tắc xử lý tên bảng, cột và identifier: quoting, chữ hoa/chữ thường |
| `getIdGeneration()` | Chiến lược lấy ID được database sinh, generated keys và sequence |
| `getInsertRenderContext()` | Quy tắc render câu INSERT phù hợp database |
| `getSelectContext()` | Quy tắc render SELECT |
| `limit()` | Cú pháp giới hạn số hàng và offset |
| `lock()` | Cú pháp lock clause cho SELECT |
| `orderByNullHandling()` | Cách biểu diễn thứ tự NULL trong ORDER BY |
| `getLikeEscaper()` | Quy tắc escape giá trị dùng với LIKE |
| `getExistsFunction()` | Biểu thức SQL thích hợp cho truy vấn EXISTS |
| `simpleTypes()` | Các kiểu dữ liệu database/driver có thể xử lý trực tiếp |
| `getConverters()` | Converter đặc thù do dialect cung cấp |
| `getArraySupport()` | Khả năng lưu và đọc cột array |
| `supportsSingleQueryLoading()` | Cho biết dialect hỗ trợ chiến lược load aggregate trong một query |
| `getUpsertRenderContext()` | Quy tắc render single-statement upsert, nếu dialect hỗ trợ |

Một số method có giá trị mặc định; một số method cung cấp object chuyên biệt để render SQL. Dialect implementation cũng có thể khai báo tính năng không hỗ trợ. Khi ứng dụng yêu cầu một tính năng không có, API tương ứng có thể ném `UnsupportedOperationException`.

## 7. Identifier processing: tên bảng và tên cột

Database khác nhau ở cách xử lý identifier:

- Có database dùng dấu nháy kép `"name"`.
- Một số database dùng dấu backtick bao quanh tên identifier.
- SQL Server thường dùng dấu ngoặc vuông `[name]` trong cú pháp T-SQL.
- Quy tắc chuyển chữ hoa/chữ thường của tên không đặt trong dấu quote cũng có thể khác nhau.

Dialect cung cấp `IdentifierProcessing` để render `SqlIdentifier` thành tên SQL phù hợp. Ví dụ, tên property Java `createdAt` có thể được mapping thành cột `created_at`; dialect xử lý cách đưa tên cột đó vào SQL và cách quote nếu cần.

Một số database phân biệt tên identifier đã quote với tên không quote. Vì vậy, việc tự tạo SQL với tên bảng/cột viết hoa, viết thường hoặc có từ khóa SQL có thể gây lỗi khi chạy trên database khác.

### Ví dụ identifier quoting

SQL minh họa:

~~~sql
-- Dùng identifier không quote
SELECT id, order_status
FROM purchase_orders;
~~~

~~~sql
-- Dùng dấu quote theo quy tắc database
SELECT "id", "order_status"
FROM "purchase_orders";
~~~

Đây chỉ là minh họa về quoting. Không nên tự thêm dấu quote vào mọi tên cột khi mapping đã do Spring Data quản lý.

Nếu schema dùng tên cột là từ khóa hoặc có chữ hoa/thường đặc biệt, hãy khai báo mapping rõ ràng và kiểm thử trên database thật. Không nên dựa vào hành vi tự chuẩn hóa identifier của một database rồi giả định database khác cũng giống vậy.

## 8. ID generation và sequence

Tạo ID là một trong những khác biệt quan trọng giữa database và JDBC driver.

Khi entity mới có ID tự sinh, Spring Data JDBC cần biết:

- Có thể lấy generated key sau câu INSERT hay không.
- Driver có yêu cầu chỉ rõ tên cột ID cần trả về không.
- Driver có hỗ trợ generated keys trong batch operation không.
- Database có hỗ trợ sequence hay không.
- Cú pháp SQL lấy giá trị tiếp theo của sequence là gì.

Các thông tin này nằm trong `IdGeneration` mà dialect cung cấp.

### 8.1. ID tự sinh từ cột identity

Entity:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;
}
~~~

Nếu database tự sinh ID khi insert, Spring Data JDBC bỏ cột ID khỏi INSERT khi entity mới có ID ở trạng thái ban đầu phù hợp. Sau khi insert, framework dùng JDBC generated keys để lấy giá trị và đưa vào entity được lưu.

Cách JDBC driver trả generated keys khác nhau. API `IdGeneration` có thuộc tính `driverRequiresKeyColumnNames()` để mô tả trường hợp driver cần tên cột ID. Oracle là ví dụ đáng chú ý cho yêu cầu này.

API cũng mô tả hỗ trợ generated keys trong batch operation. Tài liệu hiện hành nêu rằng khả năng này thường có ở các dialect, với DB2 và SQL Server là những ngoại lệ cần lưu ý. Khi dùng batch insert có ID tự sinh, hãy kiểm tra khả năng của dialect và driver.

### 8.2. Dùng sequence

Nếu database hỗ trợ sequence, có thể đánh dấu property ID bằng `@Sequence`:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    @Sequence(
        sequence = "purchase_order_seq",
        schema = "public"
    )
    private Long id;

    private String status;
}
~~~

Spring Data JDBC dùng dialect để xác định khả năng sequence và tạo câu SQL lấy giá trị tiếp theo. Với PostgreSQL, SQL minh họa có dạng:

~~~sql
SELECT nextval('public.purchase_order_seq');
~~~

Sau khi lấy ID, framework đưa giá trị đó vào INSERT.

Theo tài liệu Spring Data Relational, các dialect hỗ trợ sequence gồm H2, HSQLDB, PostgreSQL, DB2, Oracle và Microsoft SQL Server. MySQL không hỗ trợ sequence theo cơ chế này. Nếu dùng MySQL, hãy dùng chiến lược ID phù hợp như cột tự tăng hoặc ID do ứng dụng cấp.

Việc lấy sequence value và insert là hai thao tác riêng. Tài liệu Spring khuyến nghị thực hiện chúng trong transaction bao quanh để bảo đảm tính nguyên tử của use case.

## 9. Insert rendering và generated keys

Câu INSERT có thể cần cú pháp riêng để trả về ID hoặc giá trị sinh tự động. Dialect cung cấp `InsertRenderContext` để framework render câu insert theo khả năng của database.

Một câu insert khái niệm:

~~~sql
INSERT INTO purchase_orders (status)
VALUES (?);
~~~

Nhưng cách yêu cầu generated key có thể khác nhau theo driver/database. Một số database/driver sử dụng JDBC `Statement.RETURN_GENERATED_KEYS`; trường hợp khác cần chỉ định tên cột ID hoặc dùng cú pháp SQL riêng.

Vì vậy, không nên giả định câu INSERT do Spring Data tạo ra sẽ giống hệt giữa mọi dialect. Hãy để framework sử dụng dialect và JDBC driver đã cấu hình.

## 10. SELECT, phân trang và LIMIT

Repository có thể dùng `Pageable` để yêu cầu một phần kết quả:

~~~java
public interface PurchaseOrderRepository
        extends PagingAndSortingRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(
        String status,
        Pageable pageable
    );
}
~~~

Caller:

~~~java
Pageable pageRequest = PageRequest.of(
    2,
    10,
    Sort.by(Sort.Direction.DESC, "id")
);

Page<PurchaseOrder> page =
    repository.findByStatus("OPEN", pageRequest);
~~~

Ý định là lấy trang thứ ba, mỗi trang 10 hàng, sắp xếp ID giảm dần. SQL generator kết hợp điều kiện, sort và limit/offset theo dialect.

Ví dụ minh họa:

~~~sql
-- Một kiểu cú pháp LIMIT/OFFSET
SELECT ...
FROM purchase_orders
WHERE status = ?
ORDER BY id DESC
LIMIT ? OFFSET ?;
~~~

~~~sql
-- Một kiểu cú pháp OFFSET/FETCH
SELECT ...
FROM purchase_orders
WHERE status = ?
ORDER BY id DESC
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
~~~

Đây không phải cam kết về thứ tự tham số hoặc SQL chính xác cho mọi dialect. Mục đích là cho thấy cùng một yêu cầu phân trang có thể được render bằng cú pháp khác nhau.

Nếu database hoặc dialect không hỗ trợ một dạng giới hạn kết quả, framework có thể không tạo được câu SQL tương ứng. Hãy kiểm tra capability thay vì giả định mọi database đều hỗ trợ mọi overload phân trang giống nhau.

## 11. Lock clause

Khi repository method dùng `@Lock`, Spring Data JDBC cần thêm cú pháp khóa phù hợp vào SELECT. Dialect cung cấp `LockClause` để mô tả phần SQL này.

Ví dụ cú pháp khóa ghi thường gặp:

~~~sql
SELECT *
FROM stock_items
WHERE sku = ?
FOR UPDATE;
~~~

Một database khác có thể dùng cú pháp khóa chia sẻ khác hoặc ánh xạ yêu cầu khóa đọc thành khóa ghi. Do đó, cùng một `LockMode` không bảo đảm tạo cùng một đoạn SQL trên mọi database.

Dialect là nơi mô tả khả năng và cú pháp lock. Ứng dụng vẫn cần transaction bao quanh SELECT và thao tác cập nhật để giữ khóa tới khi commit/rollback.

Nếu dialect không hỗ trợ lock clause cần thiết, đừng giả định annotation `@Lock` có thể tạo ra khóa bằng cách tự động biến đổi câu SQL tùy ý. Hãy kiểm tra database và SQL thực tế.

## 12. LIKE escaping và EXISTS

### 12.1. LIKE escaping

Khi derived query dùng các keyword như `Containing` hoặc `StartingWith`, Spring Data có thể cần xử lý ký tự đặc biệt trong giá trị tìm kiếm. Dialect cung cấp `getLikeEscaper()` để áp dụng quy tắc escape phù hợp với database.

Ký tự escape và cách khai báo `ESCAPE` có thể khác theo SQL dialect. Vì vậy không nên tự viết một thuật toán escape dùng chung cho mọi database rồi cho rằng nó tương đương với cách Spring Data render.

Lưu ý: escape wildcard và bind parameter là hai việc khác nhau. Bind parameter bảo vệ cấu trúc SQL; escape wildcard xác định `%` hoặc `_` trong input có được hiểu là ký tự literal hay cú pháp pattern.

### 12.2. EXISTS

Một số database chấp nhận biểu thức EXISTS/count theo cách khác nhau. Dialect cung cấp `getExistsFunction()` để chọn biểu thức phù hợp cho truy vấn kiểm tra tồn tại.

Mặc định API có thể dùng `COUNT(1)`. Tài liệu API cũng nêu một số database cần biểu thức dạng `LEAST(COUNT(1), 1)`, trong khi biểu thức đó không được database khác chấp nhận.

Ứng dụng không cần tự viết nhánh SQL cho từng vendor nếu sử dụng abstraction do Spring Data cung cấp.

## 13. Array type, simple type và converter của dialect

Database không chỉ khác nhau về câu lệnh. Chúng còn khác nhau ở các kiểu dữ liệu mà JDBC driver có thể đọc/ghi trực tiếp.

### 13.1. Simple types

`simpleTypes()` trả về tập hợp kiểu được xem là kiểu native của store và có thể được driver xử lý. Điều này giúp Spring Data biết những kiểu nào có thể được chuyển trực tiếp qua JDBC mapping mà không cần ánh xạ thành cấu trúc khác.

Không nên nhầm simple type với mọi kiểu Java có thể serialize. Một kiểu Java tùy chỉnh vẫn có thể cần converter riêng. Việc database hỗ trợ kiểu native như JSON, UUID, array hoặc binary cũng không bảo đảm mọi driver trả về cùng một kiểu Java.

### 13.2. Converter do dialect cung cấp

`getConverters()` cho phép dialect cung cấp các converter đặc thù cho database hoặc JDBC driver. Ví dụ, một database có thể trả về kiểu vendor-specific mà Spring Data cần chuyển thành kiểu Java phù hợp.

Các converter này được kết hợp với hệ thống custom conversions của Spring Data JDBC. Khi ứng dụng đăng ký converter riêng, cần hiểu thứ tự và phạm vi đăng ký để tránh xung đột với converter mặc định hoặc converter do dialect cung cấp.

### 13.3. Array columns

`getArraySupport()` trả về mô tả hỗ trợ array column của dialect. Một số database có kiểu array native và JDBC driver có thể làm việc với chúng; một số database không hỗ trợ hoặc cần cách xử lý khác.

Vì vậy, nếu entity có property kiểu array hoặc collection được lưu trực tiếp trong một cột native array, cần kiểm tra:

- Database có kiểu array tương ứng không.
- Dialect có khai báo hỗ trợ array không.
- JDBC driver có thể tạo và đọc JDBC Array đúng cách không.
- Kiểu phần tử có được hỗ trợ và có mapping phù hợp không.

Nếu database không hỗ trợ array native, có thể cần mô hình hóa collection thành bảng con hoặc dùng kiểu lưu trữ khác như JSON với converter riêng. Không nên giả định một property kiểu `List<String>` tự động có thể lưu thành array trên mọi database.

## 14. ORDER BY và thứ tự của NULL

Khi sắp xếp một cột nullable, database có thể khác nhau về vị trí mặc định của giá trị NULL. Một số cú pháp cho phép chỉ định rõ:

~~~sql
ORDER BY created_at DESC NULLS LAST;
~~~

Database khác có thể dùng cách biểu diễn khác hoặc cần biểu thức bổ sung.

Dialect cung cấp `orderByNullHandling()` để mô tả cách xử lý thứ tự NULL. Nhờ đó, SQL generation có thể biểu diễn yêu cầu sort phù hợp với database thay vì giả định mọi server có cùng mặc định.

Nếu thứ tự NULL là một phần của nghiệp vụ, hãy chỉ định rõ yêu cầu sort và kiểm thử trên database thực tế. Đừng dựa vào thứ tự mặc định, vì khi chuyển database kết quả có thể thay đổi dù repository code không đổi.

## 15. Single-query loading và khả năng upsert

### 15.1. Single-query loading

`supportsSingleQueryLoading()` cho biết dialect có hỗ trợ khả năng load dữ liệu theo một query hay không. Đây là capability mà Spring Data Relational có thể sử dụng khi lựa chọn chiến lược đọc dữ liệu.

Không nên hiểu cờ này là mọi aggregate đều luôn được load bằng một câu SELECT. Kết quả còn phụ thuộc mapping, quan hệ aggregate, query và khả năng cụ thể của database. Hãy kiểm tra SQL thực tế khi hiệu năng đọc phụ thuộc số lượng round trip.

### 15.2. Single-statement upsert

Trong Spring Data Relational 4.1, `getUpsertRenderContext()` cung cấp quy tắc render cho thao tác upsert bằng một câu SQL. Mặc định API có thể dùng cú pháp `MERGE`; dialect không hỗ trợ có thể ném `UnsupportedOperationException`.

Các database có cú pháp upsert riêng. Ví dụ, PostgreSQL có `INSERT ... ON CONFLICT`, trong khi các database khác có thể dùng `MERGE` hoặc không hỗ trợ dạng thao tác tương ứng.

Một ứng dụng chỉ nên gọi API upsert khi dialect và database mục tiêu hỗ trợ. Không tự viết SQL của một vendor rồi kỳ vọng nó chạy trên database khác.

Upsert cũng không thay thế mọi quy tắc nghiệp vụ của insert/update. Hãy kiểm tra ID, unique constraint, optimistic locking và tác động tới entity con trước khi dùng.

## 16. Khả năng hỗ trợ không giống nhau giữa các database

Dialect có thể cung cấp một capability mặc định hoặc khai báo không hỗ trợ một tính năng. Không nên xây dựng một bảng “mọi database đều hỗ trợ” nếu chưa kiểm tra đúng phiên bản dialect và JDBC driver.

Những câu hỏi nên xác minh khi chọn database:

| Tính năng ứng dụng cần | Cần kiểm tra |
| --- | --- |
| ID tự sinh | Generated keys có hoạt động với driver không? |
| Batch insert | Generated keys có hỗ trợ trong batch không? |
| Sequence | Dialect có báo sequence support và tạo đúng sequence query không? |
| Phân trang | Limit/offset có cú pháp được hỗ trợ không? |
| Pessimistic locking | Lock clause có được dialect hỗ trợ và database có semantics phù hợp không? |
| LIKE search | Wildcard escaping có đúng với database không? |
| Array property | Dialect và JDBC driver có hỗ trợ array type không? |
| Upsert | Dialect có render single-statement upsert không? |
| Sort với NULL | Thứ tự NULL có giống yêu cầu nghiệp vụ không? |
| Single-query loading | Dialect có khai báo capability và mapping có phù hợp không? |

Nếu một method của dialect hoặc capability object báo không hỗ trợ, ứng dụng cần chọn thiết kế khác, dùng SQL riêng cho database đó hoặc cung cấp dialect tùy chỉnh.

## 17. Tích hợp database chưa được hỗ trợ

Nếu database chưa có dialect tích hợp, Spring Data JDBC không thể tự suy luận toàn bộ cú pháp từ JDBC driver. Cần cung cấp một implementation phù hợp.

Có hai hướng chính:

1. Tạo bean dialect bằng cách override `jdbcDialect(NamedParameterJdbcOperations)` trong cấu hình kế thừa `AbstractJdbcConfiguration`.
2. Viết `JdbcDialectProvider` và đăng ký qua `SpringFactoriesLoader` để resolver tự phát hiện.

Trước khi viết dialect mới, hãy kiểm tra database có tương thích với một dialect hiện có hay không. Chỉ tái sử dụng dialect khác nếu cú pháp và semantics thực sự tương thích, không chỉ vì hai database cùng hỗ trợ một phần SQL chuẩn.

### 17.1. Chọn dialect trực tiếp trong cấu hình

Ví dụ cấu hình ứng dụng tự cung cấp dialect:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.core.dialect.JdbcDialect;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;

@Configuration
public class CustomJdbcConfiguration
        extends AbstractJdbcConfiguration {

    @Override
    public JdbcDialect jdbcDialect(
            NamedParameterJdbcOperations operations) {
        return new AcmeJdbcDialect();
    }
}
~~~

`AcmeJdbcDialect` ở đây là implementation do ứng dụng hoặc vendor cung cấp. Ví dụ giả định ứng dụng chỉ có một database/dialect cần sử dụng.

Nếu có nhiều DataSource, việc chọn dialect phải tương ứng đúng với `NamedParameterJdbcOperations`/DataSource mà repository sử dụng. Không trả về dialect của database A cho kết nối database B.

### 17.2. Tự động phát hiện qua JdbcDialectProvider

Nếu muốn Spring tự phát hiện dialect, triển khai SPI `DialectResolver.JdbcDialectProvider`. Provider nhận `JdbcOperations`, kiểm tra metadata database và trả về dialect nếu nhận diện được.

Ví dụ khung:

~~~java
import java.util.Optional;

import org.springframework.data.jdbc.core.dialect.DialectResolver;
import org.springframework.data.relational.core.dialect.Dialect;
import org.springframework.jdbc.core.JdbcOperations;

public class AcmeJdbcDialectProvider
        implements DialectResolver.JdbcDialectProvider {

    @Override
    public Optional<Dialect> getDialect(JdbcOperations operations) {
        return operations.execute(connection -> {
            String productName = connection.getMetaData()
                .getDatabaseProductName();

            if ("AcmeDB".equals(productName)) {
                return Optional.of(new AcmeJdbcDialect());
            }

            return Optional.empty();
        });
    }
}
~~~

Đây là skeleton minh họa. Tên database, cách nhận diện version và implementation `AcmeJdbcDialect` cần được thay bằng thông tin thực tế của vendor. Nếu provider không nhận diện database, nó nên trả `Optional.empty()` để resolver tiếp tục thử provider khác.

Đăng ký provider trong resource:

~~~text
META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.data.jdbc.core.dialect.DialectResolver$JdbcDialectProvider=com.example.AcmeJdbcDialectProvider
~~~

Resolver dùng `SpringFactoriesLoader` để tìm provider đã đăng ký. Khi provider nhận diện đúng database, nó trả về dialect tương ứng.

### 17.3. Phạm vi cần triển khai trong custom dialect

Một custom dialect không chỉ cần trả về tên database. Nó phải cung cấp những phần mà ứng dụng sử dụng, có thể gồm:

- Identifier processing và quy tắc quote tên bảng/cột.
- Cách tạo ID, generated keys và sequence.
- Insert/select render context.
- Limit/offset và lock clause.
- Sort NULL và LIKE escaping.
- Exists expression.
- Kiểu dữ liệu native, converter và array support.
- Upsert render context nếu ứng dụng cần upsert.
- Các capability khác mà framework yêu cầu.

Bắt đầu từ những tính năng cần thiết, nhưng đừng khai báo hỗ trợ một capability nếu implementation chưa thực sự render hoặc xử lý đúng. Một dialect không chính xác có thể làm SQL sai ở runtime hoặc khiến framework chọn một đường xử lý không tương thích.

## 18. SQL viết tay và migration vẫn thuộc trách nhiệm ứng dụng

Dialect không tự chuyển mọi câu SQL do ứng dụng viết. Những phần sau thường vẫn cần được thiết kế theo database mục tiêu:

- Câu SQL trong `@Query`.
- Câu SQL gọi qua `JdbcTemplate` hoặc JDBC client.
- Migration Flyway/Liquibase.
- DDL tạo bảng, index, constraint, trigger và sequence.
- Hàm JSON, full-text search, stored procedure và vendor extension.
- SQL hint hoặc cú pháp tối ưu riêng của database.

Nếu mục tiêu là hỗ trợ nhiều database, hãy giữ SQL viết tay ở mức tối thiểu hoặc cô lập nó trong repository/adapter riêng. Migration có thể cần nhiều biến thể theo database. Không nên coi dialect là một công cụ dịch DDL tổng quát.

## 19. Quan sát SQL do Spring Data JDBC tạo

Khi SQL không chạy như mong đợi, bước đầu tiên là xem câu lệnh thực tế được gửi xuống JDBC.

Tài liệu Spring Data JDBC khuyến nghị bật logging của Spring JDBC, ví dụ trong `application.properties`:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

Có thể cần bật mức log phù hợp cho package cụ thể tùy phiên bản và cấu hình logging. Cấu hình trên giúp quan sát các thao tác JDBC do `NamedParameterJdbcTemplate` thực hiện.

Khi đọc log, hãy kiểm tra:

1. Tên bảng và cột có đúng mapping không.
2. Identifier có được quote theo database không.
3. Câu SELECT có limit/offset và ORDER BY như dự kiến không.
4. Câu INSERT có lấy generated key đúng cách không.
5. Lock clause có được thêm không.
6. Placeholder và kiểu bind có phù hợp với JDBC driver không.
7. SQL có phải câu lệnh framework sinh hay là SQL viết tay trong ứng dụng.

Không nên bật logging SQL có giá trị bind nhạy cảm ở production nếu chính sách bảo mật không cho phép. Khi debug, dùng dữ liệu thử nghiệm và môi trường phù hợp.

## 20. Kiểm thử khả năng tương thích database

Một repository chạy được trên H2 chưa chứng minh nó chạy đúng trên PostgreSQL, MySQL, Oracle hoặc SQL Server. H2 có dialect, parser, kiểu dữ liệu và transaction semantics riêng.

Nếu ứng dụng production dùng một database cụ thể, integration test quan trọng nên chạy với đúng loại database đó. Có thể dùng Testcontainers để khởi chạy database tương ứng trong pipeline kiểm thử.

Các nhóm kiểm thử nên có:

- Tạo schema bằng migration và khởi động Spring context để xác nhận dialect được resolve.
- Insert entity có ID tự sinh và xác nhận generated key.
- Insert bằng sequence nếu ứng dụng dùng `@Sequence`.
- Đọc, cập nhật và xóa aggregate.
- Derived query, sort, limit/offset và count/exists.
- LIKE với wildcard và ký tự cần escape.
- Pessimistic locking trong hai transaction đồng thời.
- Kiểu dữ liệu đặc thù như array, JSON, UUID hoặc binary nếu có.
- Upsert nếu ứng dụng sử dụng API này.
- Tên bảng/cột có chữ hoa, từ khóa hoặc identifier cần quote.

Không cần kiểm thử tất cả capability của dialect nếu ứng dụng không dùng chúng. Hãy ưu tiên các feature ảnh hưởng trực tiếp tới schema và workload của hệ thống.

## 21. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| ApplicationContext không khởi động, không resolve được dialect | Database chưa có dialect được đăng ký hoặc metadata không nhận diện được | Kiểm tra driver, connection metadata và dialect provider |
| Có JDBC driver nhưng Spring Data JDBC không chạy | Driver không thay thế dialect | Cung cấp dialect tương thích hoặc dùng database được hỗ trợ |
| SQL phân trang lỗi trên database khác | Cú pháp limit/offset không giống nhau | Kiểm tra dialect và SQL được render |
| Tên bảng/cột không tìm thấy | Identifier quoting hoặc letter casing khác | Kiểm tra mapping và identifier processing |
| Insert không lấy được ID | Driver/dialect khác nhau về generated keys | Kiểm tra `IdGeneration` và driver |
| Dùng @Sequence trên MySQL không hoạt động | MySQL không hỗ trợ sequence theo cơ chế này | Dùng identity/auto increment hoặc ID do ứng dụng cấp |
| Batch insert không lấy đủ generated keys | Driver không hỗ trợ generated keys trong batch | Kiểm tra capability và chọn chiến lược ghi phù hợp |
| Lock query lỗi cú pháp | Lock clause không phù hợp database hoặc dialect | Kiểm tra dialect lock support và SQL thực tế |
| Array property không map được | Database/driver/dialect không hỗ trợ array tương ứng | Dùng kiểu lưu trữ khác hoặc custom mapping |
| Upsert báo không hỗ trợ | Dialect không cung cấp upsert render context | Dùng insert/update hoặc SQL riêng cho database |
| SQL trong @Query lỗi khi đổi database | SQL viết tay không được dialect tự dịch | Viết query theo vendor hoặc tách implementation |
| H2 test pass nhưng production fail | Hành vi database khác nhau | Chạy integration test với database production |

## 22. Quy trình chọn database và Dialect

Khi đánh giá một database cho ứng dụng Spring Data JDBC, hãy thực hiện theo thứ tự:

1. Xác nhận database có dialect tích hợp trong đúng phiên bản Spring Data Relational.
2. Xác nhận JDBC driver và phiên bản driver tương thích với database server.
3. Xác định các capability ứng dụng cần: generated ID, sequence, array, upsert, lock, paging, LIKE, sort NULL.
4. Kiểm tra dialect có hỗ trợ từng capability hay không.
5. Xác định phần SQL viết tay và migration nào phụ thuộc vendor.
6. Viết integration test trên database mục tiêu.
7. Nếu chưa có dialect, đánh giá chi phí triển khai và duy trì custom dialect.
8. Quan sát SQL được sinh trong môi trường test và kiểm tra query plan khi cần.

Nếu ứng dụng chỉ cần CRUD cơ bản, dialect tích hợp thường giảm đáng kể công việc tương thích. Nếu ứng dụng phụ thuộc nhiều vào SQL vendor-specific, việc chuyển database vẫn cần thay đổi query, migration và test dù đã có dialect.

## 23. Bài tập tự thực hành

### Bài 1 — Quan sát dialect được chọn

Khởi chạy ứng dụng Spring Data JDBC với một database được hỗ trợ. Quan sát quá trình khởi động và xác định dialect tương ứng với connection metadata.

### Bài 2 — So sánh SQL phân trang

Tạo một repository method nhận `Pageable`. Chạy cùng method trên PostgreSQL và SQL Server, bật JDBC logging và so sánh cú pháp limit/offset.

### Bài 3 — Identifier processing

Tạo bảng có tên cột cần quote hoặc có chữ hoa/thường đặc biệt. Khai báo mapping tường minh và quan sát SQL được sinh.

### Bài 4 — Generated key

Tạo entity có ID tự sinh. Lưu entity và kiểm tra ID trả về. Chạy trên một database/driver khác để quan sát khác biệt generated key.

### Bài 5 — Sequence support

Dùng `@Sequence` trên database hỗ trợ sequence. Quan sát câu SELECT lấy next value và câu INSERT tiếp theo. Thử trên MySQL và giải thích vì sao chiến lược sequence không áp dụng.

### Bài 6 — LIKE và lock

Tạo derived query dùng LIKE và một query method dùng `@Lock`. Quan sát SQL do dialect tạo trên database đang sử dụng.

### Bài 7 — Capability array/upsert

Kiểm tra `getArraySupport()` và `getUpsertRenderContext()` của dialect. Xác định ứng dụng có thực sự cần hai capability đó hay không.

### Bài 8 — Custom dialect provider

Tạo một provider cho database giả định chưa được hỗ trợ. Kiểm tra product name qua JDBC metadata, trả dialect cho đúng database và đăng ký provider qua `META-INF/spring.factories`.

### Bài 9 — Kiểm thử production-like

Chuyển integration test từ H2 sang database giống production bằng Testcontainers. So sánh migration, generated keys, paging, locking và kiểu dữ liệu.

## 24. Tài liệu tham khảo chính thức

- [Spring Data Relational — Getting Started / Dialects](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html): danh sách database được hỗ trợ, cách Spring Data phát hiện dialect và đăng ký dialect tùy chỉnh.
- [Spring Data Relational — Dialect API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/dialect/Dialect.html): các capability chung như identifier processing, ID generation, limit, lock, upsert, array, converter và simple types.
- [Spring Data Relational — JdbcDialect API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/dialect/JdbcDialect.html): phần mở rộng dialect dành riêng cho JDBC.
- [Spring Data Relational — DialectResolver API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/dialect/DialectResolver.html): cách resolver xác định dialect từ JDBC connection.
- [Spring Data Relational — IdGeneration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/dialect/IdGeneration.html): generated key, sequence và khả năng ID generation theo driver.
- [Spring Data Relational — Sequence Support](https://docs.spring.io/spring-data/relational/reference/jdbc/sequences.html): sử dụng `@Sequence` và danh sách dialect hỗ trợ sequence.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): ID generation và cách Spring Data JDBC lưu entity.

Dialect là lớp mô tả cú pháp SQL và khả năng của database để Spring Data JDBC có thể sinh câu lệnh phù hợp từ repository và aggregate mapping. Cấu hình chuẩn tự resolve dialect từ JDBC connection; với database chưa được hỗ trợ, ứng dụng cần cung cấp implementation tương thích. Khi triển khai đa database, hãy kiểm tra từng capability mà ứng dụng sử dụng và kiểm thử bằng đúng database mục tiêu, vì dialect giúp trừu tượng hóa SQL được framework sinh chứ không tự chuyển mọi SQL viết tay hoặc migration giữa các vendor.
