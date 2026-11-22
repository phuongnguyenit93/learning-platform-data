# Kết quả kiểm thử H2 khác cơ sở dữ liệu production

Một test Spring Data R2DBC có thể chạy thành công với H2 nhưng thất bại khi triển khai lên PostgreSQL, SQL Server, MySQL hoặc một hệ quản trị khác. Điều này không nhất thiết có nghĩa code test sai. H2 là một database riêng, có parser SQL, dialect, kiểu dữ liệu, quy tắc transaction, locking, collation và driver riêng. Chế độ tương thích của H2 chỉ mô phỏng một phần hành vi của hệ quản trị khác; nó không biến H2 thành PostgreSQL, SQL Server hay MySQL.

Khi kết quả test khác production, cần xác định khác biệt nằm ở đâu: SQL được tạo ra, kiểu dữ liệu được bind/map, schema migration, constraint, transaction, concurrency hay cấu hình database. Cách xử lý bền vững là dùng H2 cho các kiểm thử nhanh phù hợp, đồng thời chạy integration test trên đúng database engine và R2DBC driver mà ứng dụng triển khai.

## 1. Vì sao H2 không thể thay thế database production?

H2 là một hệ quản trị quan hệ gọn nhẹ, thường được dùng trong test vì dễ khởi tạo và có thể chạy embedded/in-memory. PostgreSQL, SQL Server và MySQL có hệ sinh thái riêng, gồm kiểu dữ liệu, cú pháp, optimizer, lock manager, extension, collation và driver khác nhau.

Ngay cả khi hai database cùng hỗ trợ SQL chuẩn, mỗi hệ quản trị vẫn có những khác biệt ở phần mở rộng và chi tiết thực thi. Một câu lệnh hợp lệ trên H2 có thể không hợp lệ trên database production; ngược lại, một câu SQL dùng tính năng riêng của production có thể không chạy trên H2.

Các khác biệt thường gặp:

- **SQL dialect:** cú pháp phân trang, upsert, generated value, hàm chuỗi/ngày giờ, CTE và câu lệnh DDL.
- **Data type:** UUID, JSON/JSONB, array, enum, binary, temporal type, decimal precision và kiểu vendor-specific.
- **Identifier:** quy tắc chữ hoa/thường, quote, schema mặc định và tên trùng từ khóa.
- **Constraint:** unique, foreign key, check, nullability, deferred constraint và cách báo lỗi.
- **Transaction:** isolation, transactional DDL, lock, deadlock, savepoint và rollback.
- **Concurrency:** cách khóa hàng, thứ tự lấy lock, phantom read, lost update và serialization failure.
- **Driver:** bind marker, codec, generated keys, cancellation và cách chuyển exception.
- **Migration:** công cụ migration có thể tạo schema khác nhau hoặc script chỉ chạy được trên một dialect.
- **Optimizer:** index, execution plan, statistics và chi phí query không giống nhau.

Vì vậy, “test xanh trên H2” chỉ chứng minh code chạy với phiên bản H2, driver H2 và cấu hình H2 đang dùng. Nó không chứng minh mọi SQL hoặc transaction behavior sẽ giống production.

## 2. Phân biệt ba lớp khi chẩn đoán

Khi một test H2 khác production, trước tiên hãy xác định lỗi thuộc lớp nào:

| Lớp | Thành phần | Ví dụ lỗi |
|---|---|---|
| Ứng dụng và Spring Data | Repository, `R2dbcEntityTemplate`, `DatabaseClient`, converter, transaction manager | Mapping sai cột, transaction manager không đúng, callback không chạy. |
| R2DBC driver | H2/PostgreSQL/SQL Server/MySQL driver, codec và bind marker | Không chuyển được `OffsetDateTime`, generated value không được trả về, kiểu bind không hợp lệ. |
| Database engine | Parser, schema, constraint, isolation, locking, collation, optimizer | SQL syntax error, unique violation, deadlock, precision khác nhau. |

Một lỗi mapping có thể xuất hiện như lỗi database, nhưng nguyên nhân là converter hoặc driver. Ngược lại, cùng một repository code có thể tạo SQL khác nhau vì Spring Data chọn dialect theo database. Không nên sửa entity hoặc query trước khi biết câu SQL thực tế và kiểu tham số đã được gửi.

## 3. H2 compatibility mode có giới hạn

H2 hỗ trợ các chế độ tương thích với một số hệ quản trị, thường được bật qua URL hoặc tùy chọn cấu hình. Chế độ này có thể thay đổi một số hành vi parser hoặc hàm để thuận tiện chuyển đổi/test.

Ví dụ một JDBC URL của H2 có thể dùng chế độ PostgreSQL:

```text
jdbc:h2:mem:testdb;MODE=PostgreSQL;DB_CLOSE_DELAY=-1
```

Đây là URL JDBC minh họa. Khi dùng R2DBC H2, URL và cách truyền option phụ thuộc phiên bản R2DBC H2 driver; không sao chép nguyên URL JDBC sang R2DBC.

Compatibility mode không tái tạo đầy đủ:

- PostgreSQL planner, MVCC, lock behavior và extension.
- SQL Server `IDENTITY`, `OUTPUT`, `rowversion`, collation và kiểu native.
- MySQL storage engine, SQL mode, collation, implicit conversion và DDL behavior.
- Driver codec, bind parameter và generated value của R2DBC driver production.
- Cấu hình server, timezone, encoding, isolation và phiên bản database thật.

Do đó, dùng compatibility mode để tăng khả năng chạy một số câu SQL, nhưng không coi nó là bằng chứng tương thích production. Nếu code phụ thuộc tính năng riêng của database, hãy test trực tiếp trên engine đó.

## 4. Dialect Spring Data R2DBC có thể khác nhau

Spring Data Relational dùng `R2dbcDialect` để xử lý khác biệt giữa các database trong những abstraction mà framework quản lý, chẳng hạn bind marker, kiểu dữ liệu và cách tạo một số câu SQL.

Khi kết nối H2, Spring Data dùng dialect tương ứng H2. Khi kết nối PostgreSQL hoặc SQL Server, dialect tương ứng sẽ được chọn. Vì vậy, `R2dbcEntityTemplate` có thể sinh SQL khác nhau cho cùng một thao tác entity.

Ví dụ, truy vấn phân trang có thể được chuyển thành cú pháp `LIMIT/OFFSET`, `OFFSET/FETCH` hoặc một dạng khác tùy dialect và phiên bản framework/database. Một query do `DatabaseClient` viết tường minh không tự động được chuyển đổi toàn bộ cú pháp theo dialect. Nếu SQL tùy chỉnh chứa `ON CONFLICT`, `OUTPUT INSERTED`, JSON operator hoặc hàm riêng, nó vẫn phải phù hợp với database đích.

Khi điều tra, hãy ghi nhận:

- Spring Boot và Spring Data Relational version.
- R2DBC driver và version.
- Database engine/version.
- Dialect thực tế được dùng.
- SQL sau khi framework xử lý bind marker.
- Kiểu Java và kiểu database của từng bind parameter.

Đừng kết luận “Spring Data tự lo dialect” rồi cho rằng mọi câu SQL viết trong `@Query` hoặc `DatabaseClient` đều portable.

## 5. Khác biệt cú pháp SQL thường gặp

Một số câu lệnh nhìn tương tự nhưng không portable:

| Nhu cầu | PostgreSQL | SQL Server | MySQL | Ghi chú |
|---|---|---|---|---|
| Phân trang | `LIMIT ... OFFSET ...` hoặc `OFFSET ... FETCH` | `ORDER BY ... OFFSET ... FETCH NEXT ...` | `LIMIT ... OFFSET ...` | SQL Server yêu cầu `ORDER BY` với `OFFSET/FETCH`. |
| Upsert | `INSERT ... ON CONFLICT ...` | `MERGE` hoặc pattern `UPDATE`/`INSERT` phù hợp | `INSERT ... ON DUPLICATE KEY UPDATE` | Semantics concurrency và constraint khác nhau. |
| Giá trị insert sinh ra | `RETURNING` | `OUTPUT INSERTED...` | Generated keys hoặc cơ chế driver | Không thay thế cú pháp của nhau. |
| Boolean | `BOOLEAN` | `BIT` | `BOOLEAN` thường là alias của `TINYINT(1)` | Mapping/codec cần xác nhận. |
| UUID | `UUID` | `UNIQUEIDENTIFIER` | Thường `BINARY(16)` hoặc `CHAR(36)` | Kiểu lưu trữ và codec khác nhau. |
| JSON | `JSON`/`JSONB` | `NVARCHAR`/JSON functions tùy schema | `JSON` | Operator và index khác nhau. |

H2 có thể chấp nhận một phần cú pháp tương tự nhưng không bảo đảm tương thích với toàn bộ tính năng hoặc semantics của các engine này.

## 6. Ví dụ: upsert chạy trên H2 nhưng lỗi trên production

Một repository có thể dùng câu SQL:

```sql
INSERT INTO customer_setting (customer_id, setting_key, setting_value)
VALUES (:customerId, :key, :value)
ON CONFLICT (customer_id, setting_key)
DO UPDATE SET setting_value = EXCLUDED.setting_value;
```

Đây là cú pháp PostgreSQL. Nó phụ thuộc unique constraint/index trên `(customer_id, setting_key)`. SQL Server không hỗ trợ `ON CONFLICT`; MySQL dùng cú pháp khác. H2 compatibility mode có thể hỗ trợ một số phần nhưng không nên dùng làm căn cứ xác nhận production.

Các hướng xử lý:

1. Nếu ứng dụng chỉ hỗ trợ PostgreSQL, dùng PostgreSQL trong integration test.
2. Nếu hỗ trợ nhiều database, tách SQL adapter theo dialect hoặc dùng abstraction có semantics được hỗ trợ trên tất cả engine mục tiêu.
3. Nếu cần portable behavior, thiết kế transaction/constraint rõ ràng và kiểm thử race condition trên từng engine.

Không nên chỉ thay cú pháp để test H2 qua mà bỏ qua atomicity. Một pattern `SELECT` rồi `INSERT` không có unique constraint/locking vẫn có thể tạo duplicate khi hai request đồng thời.

## 7. Khác biệt kiểu dữ liệu

Một entity Java có thể map sang kiểu SQL khác nhau. Một số khác biệt đáng chú ý:

| Domain type | H2 | PostgreSQL | SQL Server | MySQL |
|---|---|---|---|---|
| UUID | Kiểu hỗ trợ tùy version/cấu hình | `UUID` | `UNIQUEIDENTIFIER` | Thường `BINARY(16)` hoặc `CHAR(36)` |
| Boolean | `BOOLEAN` | `BOOLEAN` | `BIT` | `BOOLEAN`/`TINYINT(1)` |
| JSON | Kiểu/tính năng phụ thuộc version | `JSON`/`JSONB` | Thường văn bản cùng JSON functions | `JSON` |
| Binary lớn | `BLOB`/binary type | `BYTEA` | `VARBINARY(MAX)` | `BLOB` |
| Ngày giờ có offset | Hỗ trợ temporal type theo version | `TIMESTAMP WITH TIME ZONE` | `DATETIMEOFFSET` | `TIMESTAMP`/`DATETIME` với semantics riêng |
| Số thập phân | `DECIMAL`/`NUMERIC` | `NUMERIC` | `DECIMAL`/`NUMERIC` | `DECIMAL` |

Bảng chỉ nêu các lựa chọn phổ biến; mapping thực tế phụ thuộc schema, phiên bản engine, driver và converter. Không chọn kiểu Java chỉ vì H2 test đọc/ghi được.

## 8. UUID và identifier

PostgreSQL có kiểu `UUID` native. SQL Server dùng `UNIQUEIDENTIFIER`. MySQL thường lưu UUID ở dạng `BINARY(16)` hoặc chuỗi `CHAR(36)`. H2 có kiểu UUID riêng tùy phiên bản.

Trong Java, `java.util.UUID` thường là domain representation hợp lý, nhưng driver phải có codec tương ứng. Nếu production dùng `BINARY(16)`, cần quy ước byte order/encoding thống nhất. Nếu dùng chuỗi, cần định dạng chuẩn hóa để không tạo nhiều biểu diễn cho cùng một UUID.

Test H2 có thể thành công vì codec H2 chấp nhận UUID trực tiếp, trong khi production driver không hỗ trợ cách bind đó hoặc converter được cấu hình khác. Hãy kiểm tra cả insert, select, predicate `WHERE id = :id` và generated ID trên driver thực tế.

## 9. JSON và kiểu dữ liệu vendor-specific

Một ứng dụng có thể lưu JSON trong entity:

```java
@Table("customer_profile")
public class CustomerProfile {
    @Id
    private UUID id;

    private String displayName;

    @Column("preferences")
    private Json preferences;
}
```

Kiểu `Json` ở đây chỉ minh họa domain type; codec và converter phụ thuộc driver. PostgreSQL `JSONB` có operator và index riêng; MySQL JSON có functions riêng; SQL Server thường lưu JSON trong kiểu văn bản và dùng các hàm JSON để truy vấn. H2 có hỗ trợ JSON theo phiên bản nhưng không tái tạo toàn bộ operator, indexing và behavior của production.

Nếu query dùng `->`, `->>`, `@>`, `JSON_VALUE`, `JSON_QUERY` hoặc JSON path riêng, hãy chạy test trên đúng database. Nếu muốn giảm phụ thuộc dialect, có thể map JSON thành `String`/domain object và xử lý ở application khi payload nhỏ, nhưng phải cân nhắc validation, index và chi phí đọc/ghi.

## 10. Decimal precision và rounding

H2 và production có thể khác nhau ở precision/scale, cách chuyển đổi số và lỗi khi giá trị vượt giới hạn cột. Với tiền hoặc số liệu chính xác, dùng `BigDecimal` trong Java và `DECIMAL(p,s)`/`NUMERIC(p,s)` trong schema.

Ví dụ:

```sql
amount DECIMAL(19, 4) NOT NULL
```

Test trên H2 có thể cho phép một giá trị hoặc chuyển đổi mà production từ chối, hoặc cách rounding/truncation khác nhau. Không dựa vào việc insert thành công để khẳng định precision đúng.

Kiểm tra các trường hợp:

- Giá trị có đúng scale.
- Giá trị sát giới hạn precision.
- Giá trị vượt precision.
- Giá trị âm/dương theo constraint.
- `NULL` ở cột nullable.
- Phép `SUM` có thể trả kiểu rộng hơn kiểu cột.
- Chuyển đổi giữa `BigDecimal` và kiểu Java khi map từ driver.

Quy tắc rounding nên được định nghĩa trong domain bằng `RoundingMode` rõ ràng. Không để engine tự làm tròn theo một semantics mà ứng dụng không kiểm soát.

## 11. Ngày giờ và timezone

Các database khác nhau về kiểu temporal và cách lưu timezone. Ví dụ:

- PostgreSQL `TIMESTAMP WITH TIME ZONE` lưu một thời điểm theo semantics của `timestamptz`; nó không giữ nguyên tên vùng timezone ban đầu.
- SQL Server `DATETIMEOFFSET` lưu ngày giờ cùng offset.
- MySQL `TIMESTAMP` có chuyển đổi theo session time zone; `DATETIME` không lưu timezone.
- H2 hỗ trợ nhiều temporal type nhưng không nhất thiết có cùng precision hoặc codec với production.

Trong Java, phân biệt:

- `Instant`: một thời điểm trên timeline UTC.
- `OffsetDateTime`: ngày giờ kèm UTC offset.
- `LocalDateTime`: ngày giờ địa phương không có offset/timezone.
- `LocalDate`: ngày lịch.
- `LocalTime`: giờ trong ngày.

Không map `LocalDateTime` sang một cột timezone-aware rồi mặc định đó là UTC. Cần quy định timezone ở application và database session, đồng thời kiểm tra DST nếu nghiệp vụ dùng giờ địa phương.

Test nên chạy các giá trị sát ranh giới ngày, offset khác nhau, fractional seconds và giá trị quanh chuyển đổi DST nếu có. H2 test với timezone mặc định của máy developer có thể khác production container.

## 12. Boolean, enum và collation

SQL Server dùng `BIT` cho boolean; MySQL thường biểu diễn `BOOLEAN` bằng `TINYINT(1)`; PostgreSQL có `BOOLEAN`. Driver có thể map về `Boolean`, nhưng kiểu cột, nullability và codec vẫn cần kiểm tra.

Enum có thể được lưu bằng tên (`VARCHAR`) hoặc ordinal (`INTEGER`). Lưu ordinal dễ hỏng khi thứ tự enum thay đổi; thường nên lưu mã ổn định bằng converter. Nếu database có enum native, migration và driver support sẽ mang tính vendor-specific.

Collation ảnh hưởng so sánh và sắp xếp chuỗi. Ví dụ, database production có thể không phân biệt hoa/thường hoặc dấu theo collation, trong khi H2 dùng quy tắc khác. Một truy vấn tìm `An` có thể trả kết quả khác `an` hoặc `Án` tùy collation.

Không giả định `String.equals()` của Java có semantics giống phép so sánh SQL. Nếu nghiệp vụ yêu cầu chuẩn hóa email, mã sản phẩm hoặc username, hãy quy định normalization rõ ràng và có thể lưu thêm normalized column/index.

## 13. Identifier, schema và từ khóa

Database có quy tắc khác nhau về tên bảng/cột không quote:

- PostgreSQL chuyển identifier không quote về chữ thường; identifier được quote giữ nguyên case và trở nên phân biệt hoa/thường.
- H2 có quy tắc folding/case handling riêng và cấu hình có thể thay đổi behavior.
- SQL Server có collation và quy tắc identifier riêng; schema mặc định thường ảnh hưởng cách resolve tên.
- MySQL có thể phụ thuộc cấu hình hệ điều hành và `lower_case_table_names` đối với tên bảng.

Một entity có `@Table("Customer")` có thể được resolve khác nhau giữa môi trường. Nên chọn quy ước tên bảng/cột đơn giản, ổn định, tránh từ khóa và dùng `@Table`/`@Column` tường minh khi cần.

Ví dụ:

```java
@Table("customer_account")
public class CustomerAccount {
    @Id
    private UUID id;

    @Column("display_name")
    private String displayName;
}
```

Không sửa case của identifier chỉ để H2 test qua mà chưa xác nhận schema production. Migration và mapping annotation phải thống nhất trên database mục tiêu.

## 14. Generated ID và generated values

Các engine có cách sinh ID khác nhau:

- PostgreSQL thường dùng identity/sequence và hỗ trợ `RETURNING`.
- SQL Server dùng `IDENTITY`, `SEQUENCE` và `OUTPUT INSERTED`.
- MySQL dùng `AUTO_INCREMENT` và generated keys qua driver.
- H2 có identity/sequence nhưng API và SQL không đại diện đầy đủ cho mọi production engine.

Spring Data R2DBC có thể lấy generated ID qua dialect/driver trong các đường entity persistence được hỗ trợ. Nếu ứng dụng dùng SQL tường minh, cần hiểu API generated values của driver hoặc viết câu SQL phù hợp database.

Không viết test H2 chỉ kiểm tra ID khác null rồi kết luận production generated-value behavior chắc chắn giống. Hãy test trên driver production và kiểm tra entity trả về sau `save`, đặc biệt với entity immutable.

## 15. Constraint và cách báo lỗi

Các database có thể khác nhau về:

- Tên/định dạng constraint violation.
- SQL state và vendor error code.
- Thời điểm kiểm tra constraint.
- Hỗ trợ deferred constraint.
- Unique constraint với cột nullable.
- Foreign key cascade và update/delete behavior.
- Check constraint và conversion trước khi kiểm tra.

Ví dụ unique constraint:

```sql
ALTER TABLE customer
ADD CONSTRAINT uq_customer_email UNIQUE (email);
```

Test H2 có thể xác nhận duplicate email bị từ chối, nhưng không đảm bảo exception type, SQL state hoặc tên constraint giống production. Nếu service phân loại lỗi theo constraint name/vendor code, phải kiểm tra trên driver thật.

Không bắt mọi `DataIntegrityViolationException` rồi chuyển thành “email đã tồn tại”. Lỗi có thể đến từ foreign key, check constraint, not-null hoặc một unique constraint khác. Phân loại theo constraint cụ thể và giữ nguyên lỗi không nhận diện.

## 16. NULL và unique constraint

Các database có thể có semantics khác nhau khi unique index chứa `NULL`. Ví dụ PostgreSQL mặc định cho phép nhiều hàng có `NULL` ở cột unique vì `NULL` không bằng `NULL` theo semantics so sánh thông thường; các phiên bản mới có tùy chọn `NULLS NOT DISTINCT`. SQL Server và các hệ quản trị khác có quy tắc riêng về unique index với null.

Nếu nghiệp vụ yêu cầu mỗi customer chỉ có một external reference khi giá trị được cung cấp, hãy thiết kế constraint/filter phù hợp database và test trên production engine. Không dựa vào H2 để xác nhận mọi biến thể unique-null behavior.

Nếu cột bắt buộc phải có giá trị, khai báo `NOT NULL` thay vì dựa vào unique constraint để xử lý null.

## 17. Foreign key, cascade và thứ tự ghi

Test H2 có thể không phản ánh đúng schema production nếu migration test bỏ qua foreign key hoặc tạo bảng bằng schema đơn giản hơn. Kiểm tra:

- Foreign key thực sự được tạo trong database.
- Cột tham chiếu có kiểu và collation phù hợp.
- `ON DELETE`/`ON UPDATE` action đúng.
- Thứ tự insert parent/child đúng.
- Transaction rollback khi insert child vi phạm foreign key.
- Cascade có thể xóa bao nhiêu hàng và có phù hợp nghiệp vụ không.

Không tắt constraint trong test chỉ để fixture dễ tạo rồi kết luận persistence logic an toàn. Nếu test cần seed dữ liệu phức tạp, hãy tạo theo đúng thứ tự quan hệ hoặc dùng fixture SQL phù hợp.

## 18. Transactional DDL và migration khác nhau

Một nguyên nhân phổ biến khiến migration chạy trên H2 nhưng production thất bại là semantics DDL khác nhau. Một số engine hỗ trợ transactional DDL cho nhiều thao tác; một số DDL có implicit commit hoặc không thể rollback theo cách ứng dụng mong đợi.

Ví dụ:

- PostgreSQL hỗ trợ transactional behavior cho nhiều lệnh DDL, dù vẫn có ngoại lệ và lock behavior cần hiểu.
- MySQL có nhiều DDL statement gây implicit commit.
- SQL Server hỗ trợ transaction cho nhiều DDL operation nhưng có giới hạn và semantics riêng theo statement.
- H2 có hành vi DDL và transaction riêng.

Không giả định migration thất bại sẽ để schema nguyên trạng trên mọi database. Nếu migration có nhiều bước, hãy kiểm tra trạng thái sau lỗi và thiết kế recovery. Migration tool có thể quản lý lịch sử nhưng không làm mọi DDL trở nên rollback được.

## 19. Isolation và locking có thể khác nhau

Một test H2 chạy tuần tự thường không bộc lộ race condition. Production có nhiều request đồng thời, nhiều instance và lock contention. Các database khác nhau về MVCC, row lock, gap/next-key lock, predicate lock và deadlock detection.

Những tình huống cần chú ý:

- Hai request cùng cập nhật một account.
- Hai transaction insert cùng unique key.
- Đọc rồi cập nhật theo giá trị cũ (lost update).
- Đọc danh sách rồi insert hàng mới (phantom).
- Hai transaction lấy lock theo thứ tự khác nhau (deadlock).
- Transaction giữ lock lâu vì pipeline reactive có network call hoặc xử lý CPU dài.

Nếu nghiệp vụ cần điều kiện như “chỉ trừ tiền khi balance đủ”, đặt điều kiện vào câu `UPDATE` và kiểm tra `rowsUpdated`, hoặc dùng locking/version strategy phù hợp. Không chỉ dựa vào read-then-save trong Java.

## 20. Isolation level mặc định không giống nhau

Không nên dựa vào mặc định của H2 để suy luận production. Hãy xác định isolation level thực tế từ database, transaction manager và cấu hình ứng dụng.

Một số khái niệm:

| Isolation | Mục tiêu khái quát | Điều cần kiểm tra |
|---|---|---|
| READ UNCOMMITTED | Có thể đọc dữ liệu chưa commit ở engine hỗ trợ | Dirty read và semantics cụ thể. |
| READ COMMITTED | Chỉ đọc dữ liệu đã commit theo semantics engine | Non-repeatable read và snapshot từng statement. |
| REPEATABLE READ | Giữ tính lặp lại cho các hàng đã đọc theo semantics engine | Phantom behavior khác nhau giữa database. |
| SERIALIZABLE | Tạo kết quả tương đương thực thi tuần tự | Có thể phát serialization failure và cần retry. |

Tên isolation giống nhau không bảo đảm implementation giống nhau. Ví dụ PostgreSQL `REPEATABLE READ` dùng snapshot isolation với behavior khác một số engine; SQL Server có thể dùng locking hoặc row-versioning tùy cấu hình `READ_COMMITTED_SNAPSHOT`/snapshot isolation.

Test concurrency phải chạy trên database production hoặc engine tương ứng, với isolation configuration giống môi trường triển khai.

## 21. Test reactive transaction có thể khác test imperative

Spring Data R2DBC dùng reactive transaction context được truyền qua Reactor Context. Một test sử dụng `block()` ở giữa reactive chain, tự `subscribe()` hoặc dùng transaction test imperative có thể không kiểm tra đúng transaction context.

Các nguyên tắc:

- Giữ toàn bộ thao tác database trong cùng `Mono`/`Flux` chain.
- Dùng đúng `ReactiveTransactionManager` gắn với `ConnectionFactory` của repository/client.
- Với test cần transaction, dùng reactive transaction support phù hợp và xác nhận publisher thực sự chạy trong context đó.
- Không giả định `@Transactional` trên test method JUnit luôn bao bọc reactive publisher theo cách mong đợi.
- Nếu cần xác nhận rollback, chủ động tạo transaction trong service/test và query lại trạng thái sau khi transaction kết thúc.

Một test dùng H2 có thể pass dù hai thao tác vô tình dùng connection khác nhau hoặc transaction không bao trùm đúng pipeline; production concurrency có thể làm lỗi lộ rõ hơn.

## 22. R2DBC driver behavior cũng là một phần của khác biệt

Không chỉ database engine thay đổi. Driver R2DBC quyết định cách Java type được bind/đọc, cách statement được thực thi và cách cancellation/error được chuyển thành Reactive Streams signal.

Ví dụ khác biệt có thể nằm ở:

- `UUID`, JSON, array, enum, binary và temporal codec.
- Bind null và yêu cầu cung cấp Java type cho null parameter.
- Generated values và `returnGeneratedValues`.
- Batch statement và `Statement.add()`.
- Mapping `Clob`/`Blob` hoặc kiểu dữ liệu lớn.
- Cancellation và query timeout.
- Exception type, SQL state và vendor code.
- Connection acquisition, validation và pool behavior.

Một unit test có thể mock `DatabaseClient` và pass, nhưng không kiểm tra driver codec. H2 R2DBC driver cũng không đại diện cho PostgreSQL/SQL Server/MySQL driver. Hãy có test chạy qua đúng driver production.

## 23. Cấu hình H2 cho test R2DBC

Nếu dùng H2 R2DBC, hãy khai báo driver test và URL đúng theo tài liệu phiên bản driver:

```groovy
testImplementation 'io.r2dbc:r2dbc-h2'
```

Ví dụ cấu hình minh họa:

```yaml
spring:
  r2dbc:
    url: r2dbc:h2:mem:///r2dbc-test
```

URL và option giữ database sống qua các connection, cách khởi tạo schema và lifecycle database phụ thuộc R2DBC H2 driver. Không sao chép tùy chọn JDBC như `DB_CLOSE_DELAY` sang R2DBC URL mà chưa kiểm tra driver. Với in-memory database, cần bảo đảm database chưa bị đóng giữa lúc setup schema và lúc repository mở connection.

H2 phù hợp cho test nhanh khi query và schema nằm trong phần SQL mà H2 hỗ trợ, và test không nhằm xác nhận dialect/locking production.

## 24. Chạy migration thật trong test

Một test chỉ tạo bảng bằng `schema.sql` giản lược có thể bỏ sót constraint, index, default và conversion có trong migration production. Khi mục tiêu là kiểm tra persistence integration, nên chạy đúng migration scripts lên database test.

Nếu migration có cú pháp riêng cho PostgreSQL/SQL Server/MySQL, H2 có thể không chạy được. Không nên duy trì một schema H2 giả định khác schema production mà không ghi rõ phạm vi test. Tốt hơn là chạy migration trên Testcontainers của engine thực tế.

Các test migration nên kiểm tra:

- Database mới hoàn toàn có thể chạy tất cả migration.
- Database ở phiên bản schema trước có thể nâng cấp lên phiên bản hiện tại.
- Migration tạo đúng constraint, index, default và sequence.
- Migration thất bại có trạng thái được hiểu và có cách recovery.
- Backfill dữ liệu giữ nguyên invariant.
- Code mới tương thích với schema trong giai đoạn rolling deployment nếu yêu cầu.

## 25. Dùng Testcontainers với database production

Testcontainers khởi tạo database engine trong container để integration test chạy trên cùng loại database với production. Ví dụ PostgreSQL:

```groovy
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
testImplementation 'io.r2dbc:r2dbc-postgresql'
```

Phiên bản dependency nên được quản lý bằng BOM phù hợp. Ví dụ test:

```java
@SpringBootTest
@Testcontainers
class TransferRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
            "r2dbc:postgresql://" + postgres.getHost() + ":"
                + postgres.getMappedPort(5432) + "/"
                + postgres.getDatabaseName());
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);

        registry.add("spring.flyway.url", postgres::getJdbcUrl);
        registry.add("spring.flyway.user", postgres::getUsername);
        registry.add("spring.flyway.password", postgres::getPassword);
    }
}
```

Ví dụ dùng Spring Boot test context, Testcontainers và Flyway qua JDBC; project cần có PostgreSQL R2DBC driver, PostgreSQL JDBC driver và migration tool tương ứng. Nếu ứng dụng không dùng Flyway, bỏ các property Flyway và khởi tạo schema theo cơ chế migration thực tế.

Container image nên pin version phù hợp production, ví dụ cùng major/minor nếu cần kiểm chứng tính năng/version-specific. Không dùng `latest` vì test có thể thay đổi hành vi khi image được cập nhật.

## 26. Dùng đúng engine cho từng môi trường production

Nếu production chạy SQL Server, hãy dùng SQL Server Testcontainers/image và R2DBC SQL Server driver tương ứng. Nếu production chạy MySQL, dùng MySQL tương ứng. PostgreSQL test không chứng minh SQL Server query đúng, dù cả hai đều là relational database.

Ngoài engine, hãy cố gắng đồng bộ:

- Major/minor version database.
- Collation và character set.
- Time zone/session settings.
- SQL mode hoặc compatibility level.
- Extension và module được dùng trong production.
- Isolation/row-versioning settings.
- Schema và migration version.
- R2DBC driver version.

Testcontainers không tự tái tạo mọi cấu hình managed database production. Nếu production dùng extension, collation hoặc setting đặc biệt, cấu hình container/test database tương ứng hoặc có test riêng xác nhận sự khác biệt.

## 27. Phân chia test theo mục tiêu

Không cần chạy mọi test trên container database thật. Có thể chia tầng:

| Loại test | Database | Mục tiêu | Ví dụ |
|---|---|---|---|
| Unit test domain/service | Không cần database hoặc dùng mock/fake | Quy tắc nghiệp vụ, validation, mapping logic thuần | Amount dương, currency, authorization policy. |
| Reactive pipeline test | Publisher giả, `StepVerifier`/`TestPublisher` | Signal, retry, fallback, cancellation | Empty vs error, retry count. |
| Fast persistence test | H2 R2DBC | Mapping và CRUD cơ bản trong phạm vi H2 | Insert/select đơn giản, repository query portable. |
| Database integration test | Testcontainers production engine | Dialect, codec, migration, constraint, transaction | Generated values, JSON, locking. |
| Concurrency test | Production engine và driver | Race condition, deadlock, isolation | Hai transfer đồng thời, unique conflict. |
| Performance test | Môi trường gần production | Query plan, index, latency và throughput | Pagination, batch, pool saturation. |

Phân tầng giúp test nhanh vẫn có giá trị, đồng thời không để H2 chịu trách nhiệm xác minh những hành vi nó không thể đại diện.

## 28. `@DataR2dbcTest` và `@SpringBootTest`

`@DataR2dbcTest` của Spring Boot là test slice tập trung vào R2DBC components, phù hợp cho một số kiểm thử repository/mapping. `@SpringBootTest` tạo application context rộng hơn và phù hợp khi cần xác nhận cấu hình service, transaction manager, migration và bean wiring gần production.

Tùy phiên bản Spring Boot và cấu hình dự án, test slice có thể thay đổi auto-configuration được nạp. Không giả định `@DataR2dbcTest` tự chạy Flyway hoặc nạp mọi service/transaction bean. Nếu test cần migration thật hoặc nhiều bean ứng dụng, cấu hình import rõ hoặc dùng `@SpringBootTest`.

Khi dùng Testcontainers, có thể cấu hình container properties qua `@DynamicPropertySource` hoặc cơ chế service connection được phiên bản Spring Boot hỗ trợ. Đảm bảo property R2DBC trỏ đến container thật; nếu chỉ thay JDBC URL nhưng repository dùng R2DBC, test vẫn có thể kết nối nhầm database khác.

## 29. Kiểm tra SQL được tạo và SQL tùy chỉnh

Khi query chạy H2 nhưng production lỗi, cần tách query do framework sinh và SQL viết tay:

- Repository derived query: Spring Data tạo SQL theo metadata và dialect.
- `R2dbcEntityTemplate`: framework tạo SQL từ `Query`, `Criteria`, sort và mapping metadata.
- `@Query`: câu SQL do developer viết, dù vẫn có binding/mapping từ Spring Data.
- `DatabaseClient`: SQL do developer điều khiển trực tiếp.
- R2DBC SPI: statement và marker theo driver cụ thể.

Với hai nhóm đầu, kiểm tra dialect và mapping metadata. Với `@Query`/`DatabaseClient`, kiểm tra cú pháp SQL cụ thể trên production engine. Không giả định `@Query` tự rewrite `LIMIT` thành `OFFSET/FETCH` hoặc chuyển `ON CONFLICT` thành `MERGE`.

Trong môi trường test, có thể bật SQL logging có kiểm soát hoặc dùng proxy/listener để quan sát query. Không ghi bind values nhạy cảm. So sánh SQL thực tế giữa H2 và production test để tìm phần cú pháp hoặc alias khác nhau.

## 30. Mapping entity và tên cột

Một entity có thể chạy với H2 vì database resolve tên cột không nghiêm ngặt, nhưng production báo column not found do case/quote/schema khác.

Ví dụ:

```java
@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private UUID id;

    @Column("created_at")
    private Instant createdAt;
}
```

Đảm bảo migration tạo đúng `purchase_order.created_at`, schema đúng và dialect quote identifier theo yêu cầu. Tránh dùng tên cột có chữ hoa/thường hỗn hợp hoặc tên trùng từ khóa nếu không cần.

Nếu production có schema riêng như `orders.purchase_order`, xác định rõ schema mapping/search path/default schema. H2 test chỉ có schema mặc định có thể không phát hiện thiếu schema qualification.

## 31. Kiểm tra constraint và migration thay vì tạo schema giả

Một số test H2 tạo schema bằng `schema.sql` hoặc `@Sql` đơn giản, trong khi production dùng Flyway/Liquibase. Schema test có thể thiếu:

- Unique constraint.
- Foreign key.
- Check constraint.
- Not-null.
- Default expression.
- Trigger.
- Sequence/identity.
- Partial/filtered index.
- Collation hoặc generated column.

Khi đó test xanh vì database test không có ràng buộc cần bảo vệ dữ liệu. Đối với persistence integration test, nên dùng migration thật trên database đích. Nếu một test chỉ cần bảng tối giản để kiểm tra logic đơn lẻ, ghi rõ phạm vi của nó và không dùng nó để kết luận schema production đúng.

## 32. Test transaction rollback trên engine thật

Một test chuyển tiền có thể pass trên H2 nhưng fail production do transaction manager, driver, connection binding hoặc lock behavior khác. Test rollback nên:

1. Seed account A và B.
2. Bắt đầu reactive transaction.
3. Debit A.
4. Làm credit B thất bại có chủ đích.
5. Xác nhận publisher phát lỗi.
6. Sau khi transaction kết thúc, query lại bằng một transaction/query độc lập.
7. Xác nhận số dư A và B không đổi, không có ledger/outbox record một phía.

Không chỉ assert `expectError` rồi kết luận rollback thành công. Cần đọc lại dữ liệu đã commit. Cũng không dựa vào transaction test của JUnit nếu không chắc nó bao bọc reactive chain.

## 33. Kiểm thử concurrency phải chạy trên database production

H2 có thể xử lý locking và concurrency khác database thật. Các test quan trọng gồm:

- Hai request cùng debit một tài khoản.
- Hai request insert cùng idempotency key.
- Hai transaction cập nhật hai account theo thứ tự ngược nhau.
- Optimistic version conflict.
- Deadlock/serialization failure và retry.
- Unique/foreign-key conflict đồng thời.
- Query dưới isolation level thực tế.

Test cần thực sự chạy đồng thời, dùng barrier/latch hoặc reactive coordination phù hợp, và đọc lại trạng thái cuối. Chạy hai request tuần tự không kiểm tra race condition.

Không dùng H2 làm bằng chứng duy nhất cho việc không thể debit quá số dư hoặc không thể tạo duplicate transfer. Hãy chạy test trên engine và isolation configuration production.

## 34. Execution plan và performance không thể suy ra từ H2

H2 có optimizer và storage engine riêng. Một query chạy nhanh trên H2 không có nghĩa query đó dùng index đúng hoặc có latency tương đương trên PostgreSQL/SQL Server/MySQL.

Các khác biệt gồm:

- Statistics và cardinality estimation.
- Index access path.
- Join algorithm.
- Sort/hash memory và spill behavior.
- Lock contention.
- Buffer/cache và storage I/O.
- Parallel query.
- Network round-trip và result decoding.

Không dùng benchmark H2 để quyết định index production. Hãy dùng execution plan và metrics của engine thật với dữ liệu có phân bố gần production. H2 vẫn hữu ích cho kiểm tra logic query nhỏ, nhưng không thay thế performance test.

## 35. Timezone, locale và environment drift

Test local có thể chạy timezone UTC hoặc timezone của máy developer, còn container production dùng UTC hoặc một vùng khác. Locale, collation và encoding cũng có thể khác.

Hãy cố định cấu hình thời gian và locale trong test, nhưng vẫn kiểm tra database session thực tế:

- Time zone của database/server/session.
- Time zone của JVM/container.
- Encoding và collation.
- Locale của application.
- Precision timestamp và rounding.

Đối với timestamp đại diện thời điểm, ưu tiên quy ước UTC/`Instant` rõ ràng. Đối với ngày nghiệp vụ, dùng `LocalDate` thay vì chuyển qua timestamp tùy tiện. Test boundary values và daylight saving nếu hệ thống xử lý giờ địa phương.

## 36. Chẩn đoán lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xác nhận |
|---|---|---|
| H2 pass, production báo syntax error | SQL dialect hoặc function khác | Lấy raw SQL và chạy trên production engine/version. |
| Column/table not found | Schema, case, quote hoặc migration khác | Kiểm tra metadata schema và migration history. |
| Bind parameter type error | Driver codec hoặc Java type không tương thích | Kiểm tra kiểu bind, `bindNull` và driver version. |
| Generated ID null | Dialect/driver generated-value behavior khác | Test insert trên driver thật, kiểm tra returned entity/`OUTPUT`/`RETURNING`. |
| Unique constraint error khác loại | Exception translation/vendor code khác | Ghi nhận SQL state, vendor code và constraint cụ thể. |
| Test rollback pass nhưng production có dữ liệu dở dang | Transaction manager/connection factory/context khác | Kiểm tra transaction boundary và query lại sau lỗi. |
| Deadlock chỉ xảy ra production | Concurrency, lock order, index hoặc isolation | Chạy concurrency test và đọc deadlock report. |
| Tìm kiếm chuỗi khác kết quả | Collation/case/accent sensitivity | Kiểm tra collation và normalization. |
| Timestamp lệch | Timezone/precision/codec khác | Kiểm tra session timezone và kiểu SQL/Java. |
| Query nhanh trên H2 nhưng chậm production | Optimizer/index/data volume khác | Xem execution plan và metrics engine thật. |
| Migration H2 pass, production fail | DDL syntax/transaction/lock semantics khác | Chạy migration thật trên engine/version production. |

Không sửa bằng cách thêm một nhánh H2-specific trong production code nếu nguyên nhân thực sự là test đang dùng sai database cho hành vi cần xác minh. Chỉ thêm abstraction đa dialect khi ứng dụng thực sự hỗ trợ nhiều engine.

## 37. Quy trình chẩn đoán từng bước

Khi một test pass H2 nhưng fail production, làm theo trình tự:

1. Ghi lại database engine/version, R2DBC driver/version, Spring Data version và cấu hình session.
2. Thu thập exception type, SQL state, vendor code và cause chain mà không ghi bind values nhạy cảm.
3. Xác định SQL đến từ repository derivation, template, `@Query` hay `DatabaseClient`.
4. Lấy SQL thực tế và kiểm tra trên đúng engine/version.
5. Kiểm tra kiểu bind Java, nullability và codec của driver.
6. So sánh schema/migration history, constraint, index và default giữa H2 và production.
7. Nếu lỗi chỉ xuất hiện đồng thời, kiểm tra isolation, lock order, transaction context và pool.
8. Nếu lỗi liên quan thời gian/chuỗi, kiểm tra timezone, precision, collation và normalization.
9. Tạo integration test tái hiện trên Testcontainers hoặc môi trường production-equivalent.
10. Giữ H2 test nếu nó vẫn hữu ích cho mục tiêu nhanh; chuyển hành vi phụ thuộc dialect/engine sang test database thật.

Không nên thay đổi code nhiều lớp cùng lúc. Một biến số được kiểm tra rõ giúp tìm nguyên nhân nhanh hơn.

## 38. Ma trận test đề xuất

Một dự án có thể tổ chức ma trận như sau:

| Test suite | H2 R2DBC | Production engine qua Testcontainers |
|---|---|---|
| Domain validation | Không cần | Không cần |
| Reactive operator/retry/fallback | Có thể dùng publisher giả | Không cần trừ khi có persistence interaction |
| CRUD mapping cơ bản | Có thể | Nên có test đại diện |
| Derived repository query | Có thể cho query portable | Có, để xác nhận dialect production |
| Native SQL/`@Query` vendor-specific | Không đủ | Bắt buộc |
| JSON/UUID/array/temporal codec | Không đủ | Bắt buộc nếu dùng trong production |
| Generated values | Kiểm tra cơ bản | Bắt buộc trên driver production |
| Constraint và exception translation | Không đủ để xác nhận chi tiết | Bắt buộc cho mapping lỗi quan trọng |
| Transaction rollback | Có thể test cơ bản | Bắt buộc cho use case quan trọng |
| Concurrency/deadlock/isolation | Không đủ | Bắt buộc cho invariant đồng thời |
| Migration | Chỉ nếu script portable | Bắt buộc trên engine production |
| Performance/index/execution plan | Không dùng làm căn cứ | Dùng môi trường gần production |

Ma trận không có nghĩa mọi test phải chạy hai lần. Chọn suite theo mục tiêu và mức rủi ro của tính năng.

## 39. Giữ H2 test nhanh nhưng giới hạn kết luận

H2 vẫn có giá trị:

- Test mapping entity cơ bản với schema portable.
- Test repository CRUD đơn giản.
- Test service reactive với database test nhỏ.
- Test validation/constraint SQL chuẩn được cả engine hỗ trợ.
- Tạo fixture nhanh cho logic không phụ thuộc dialect.

Nhưng mỗi test nên có mục đích rõ. Nếu test dùng H2, tránh dùng nó làm bằng chứng cho:

- SQL vendor-specific.
- Native JSON/array/spatial type.
- Generated value đặc thù.
- Locking, deadlock hoặc isolation production.
- DDL migration production.
- Collation hoặc timezone production.
- Query plan và performance.

Nếu H2 test thường xuyên cần thêm `MODE`, `NON_KEYWORDS`, function alias hoặc schema giả để bắt chước production, đó có thể là dấu hiệu nên chuyển test đó sang database thật.

## 40. Những lỗi thiết kế test thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ dùng H2 cho toàn bộ persistence test | Bỏ sót khác biệt dialect, driver và concurrency | Thêm Testcontainers cho production engine. |
| Dùng compatibility mode rồi coi là tương đương | Có false confidence | Xem mode là hỗ trợ cú pháp một phần. |
| Tạo schema test khác migration thật | Constraint/index/default bị thiếu | Chạy migration thật trên test database. |
| Chỉ mock `DatabaseClient` | Không kiểm tra SQL/codec/transaction | Có integration test driver thật. |
| Test query không có `ORDER BY` nhưng assert thứ tự | Test chập chờn theo engine | Thêm thứ tự ổn định hoặc assert theo tập. |
| Dùng H2 để benchmark | Kết luận sai về optimizer/index | Đo trên engine và dữ liệu gần production. |
| Chỉ assert lỗi mà không đọc lại dữ liệu | Không chứng minh rollback | Query trạng thái sau transaction kết thúc. |
| Test transaction bằng `block()`/`subscribe()` tùy tiện | Có thể bỏ qua reactive context | Compose publisher và dùng StepVerifier. |
| Chạy Testcontainers với `latest` | Kết quả thay đổi theo thời điểm | Pin version image và driver. |
| Không kiểm tra database settings | Test/prod lệch collation/timezone/isolation | Đồng bộ cấu hình quan trọng. |

## 41. Checklist trước khi kết luận một lỗi là do code

Khi so sánh H2 và production, xác định:

1. Test và production có dùng đúng engine/major version mong muốn không?
2. R2DBC driver và Spring Data versions có tương thích không?
3. Câu SQL thực tế là gì và được sinh bởi abstraction nào?
4. Bind marker, Java type và null binding có đúng driver không?
5. Schema được tạo từ cùng migration scripts không?
6. Table/column/schema case và quoting có thống nhất không?
7. Data type, precision, timezone và collation có giống không?
8. Constraint, trigger, sequence, default và index có hiện diện không?
9. Transaction manager có dùng đúng `ConnectionFactory` không?
10. Isolation và locking configuration có giống production không?
11. Test có thực sự chạy đồng thời khi cần kiểm tra race condition không?
12. Có thể tái hiện trên Testcontainers của engine production không?

## 42. Quy trình áp dụng trong dự án Spring Data R2DBC

Một chiến lược thực tế:

1. Giữ unit test và reactive pipeline test độc lập với database ở mức có thể.
2. Dùng H2 cho CRUD/mapping đơn giản và SQL portable nếu thời gian chạy là ưu tiên.
3. Dùng đúng R2DBC driver và database engine trong Testcontainers cho query vendor-specific, migration, generated values, type mapping và constraint.
4. Chạy concurrency test cho các invariant quan trọng như số dư, idempotency và unique key trên engine production.
5. Dùng migration thật để tạo schema test; không tự viết schema giản lược cho integration suite chính.
6. Pin database image, driver và framework versions để test có thể tái lập.
7. Đồng bộ timezone, collation, isolation và extension quan trọng với production.
8. Khi test fail, phân loại lỗi thuộc application, driver hay engine trước khi sửa code.
9. Chỉ giữ compatibility mode cho các test mà nó thực sự giúp ích; không mở rộng kết luận vượt quá phạm vi hỗ trợ.
10. Chạy suite production-equivalent trong CI trước khi phát hành các thay đổi persistence quan trọng.

H2 là công cụ hữu ích để chạy nhanh các kiểm thử R2DBC cơ bản, nhưng nó không phải bản sao của database production. Kết quả khác nhau thường xuất phát từ dialect SQL, kiểu dữ liệu, driver codec, schema migration, constraint, collation, transaction hoặc concurrency. Hãy dùng H2 trong phạm vi phù hợp và chạy integration test bằng đúng engine/driver production cho những hành vi phụ thuộc database. Khi chẩn đoán, so sánh SQL thực tế, kiểu bind, schema và transaction configuration; Testcontainers giúp tái hiện môi trường gần production trong CI. Cách phân tầng này giữ được tốc độ test mà vẫn phát hiện các lỗi chỉ xuất hiện khi ứng dụng chạy trên database thật.
