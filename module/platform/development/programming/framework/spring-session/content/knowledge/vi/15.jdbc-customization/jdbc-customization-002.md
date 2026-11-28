# Đổi tên bảng, schema và tên bảng thuộc tính liên quan

Spring Session JDBC lưu một phiên vào các bảng quan hệ. Với `JdbcIndexedSessionRepository`, cấu trúc mặc định thường gồm bảng `SPRING_SESSION` chứa metadata của phiên và bảng `SPRING_SESSION_ATTRIBUTES` chứa các thuộc tính được serialize. Khi ứng dụng cần đặt tên theo quy ước nội bộ, dùng schema riêng hoặc chia sẻ một database giữa nhiều ứng dụng, cần tùy chỉnh tên bảng và DDL đồng bộ với cấu hình repository.

Điểm cần phân biệt là tên bảng gốc, tên bảng thuộc tính đi kèm và schema/database namespace. Thuộc tính `spring.session.jdbc.table-name` điều khiển tên bảng phiên mà repository sử dụng; bảng thuộc tính thường được suy ra bằng cách thêm hậu tố `_ATTRIBUTES`. Thuộc tính `spring.session.jdbc.schema` lại chỉ vị trí script DDL dùng để khởi tạo schema của Spring Session, không phải tên schema namespace trong database. Nếu nhầm hai ý nghĩa này, ứng dụng có thể khởi động được nhưng truy vấn vào bảng sai hoặc gặp lỗi không tìm thấy bảng.

## 1. Hai bảng mặc định và quan hệ giữa chúng

`JdbcIndexedSessionRepository` lưu metadata và attributes tách biệt:

| Bảng mặc định | Vai trò | Dữ liệu điển hình |
| --- | --- | --- |
| `SPRING_SESSION` | Một hàng cho mỗi phiên | `PRIMARY_ID`, `SESSION_ID`, thời điểm tạo/truy cập, timeout, thời điểm hết hạn và principal name |
| `SPRING_SESSION_ATTRIBUTES` | Một hàng cho mỗi thuộc tính của phiên | `SESSION_PRIMARY_ID`, `ATTRIBUTE_NAME`, dữ liệu đã serialize trong `ATTRIBUTE_BYTES` |

`PRIMARY_ID` là khóa nội bộ của bản ghi phiên. `SESSION_ID` là định danh phiên được trao đổi với client. Bảng attributes tham chiếu tới bản ghi session bằng `SESSION_PRIMARY_ID`, thường thông qua khóa ngoại tới `SPRING_SESSION.PRIMARY_ID`. Vì một phiên có thể có nhiều attributes, quan hệ giữa hai bảng là một-nhiều.

Các cột và kiểu dữ liệu cụ thể phụ thuộc script schema của database và phiên bản Spring Session. Ví dụ, PostgreSQL thường dùng `BYTEA` cho dữ liệu thuộc tính; một hệ quản trị khác có thể dùng `BLOB` hoặc kiểu nhị phân tương ứng. Không sao chép nguyên kiểu dữ liệu của PostgreSQL sang Oracle, SQL Server hoặc MySQL mà không đối chiếu schema script dành cho nền tảng đó.

Khi đổi tên bảng phiên, bảng attributes liên quan cũng phải đổi theo quy ước mà repository đang sử dụng. Ví dụ, nếu tên bảng gốc là `APP_SESSION`, repository thường truy cập bảng thuộc tính `APP_SESSION_ATTRIBUTES`. Chỉ đổi tên bảng metadata trong database mà không tạo bảng attributes tương ứng sẽ khiến thao tác lưu hoặc đọc session attributes thất bại.

## 2. Đổi tên bảng bằng Spring Boot

Với Spring Boot, cấu hình tên bảng thường nằm ở `spring.session.jdbc.table-name`. Ví dụ:

```yaml
spring:
  session:
    jdbc:
      table-name: APP_SESSION
      initialize-schema: never
```

Trong ví dụ này, repository dùng `APP_SESSION` làm bảng metadata và tên bảng thuộc tính liên quan theo quy ước `APP_SESSION_ATTRIBUTES`. `initialize-schema: never` phù hợp khi schema đã được tạo và quản lý bằng migration của dự án. Khi mới thử nghiệm trên môi trường local hoặc database nhúng, có thể dùng tùy chọn khởi tạo schema phù hợp, nhưng không nên để ứng dụng production tự thay đổi DDL ngoài quy trình quản lý database.

Nếu dùng cấu hình Java thay vì auto-configuration, `@EnableJdbcHttpSession` có thuộc tính `tableName` trong các phiên bản hỗ trợ:

```java
@Configuration
@EnableJdbcHttpSession(tableName = "APP_SESSION")
class JdbcSessionConfiguration {
}
```

Chỉ chọn một cách cấu hình repository nhất quán. Nếu Spring Boot đã auto-configure JDBC Session, không khai báo thêm một cấu hình `@EnableJdbcHttpSession` chỉ để đổi tên bảng mà chưa kiểm tra tác động tới auto-configuration. Hai cấu hình cùng tạo repository/filter có thể gây bean conflict hoặc làm ứng dụng dùng repository khác với dự kiến.

Tên bảng là cấu hình tĩnh do ứng dụng kiểm soát. Không lấy tên bảng trực tiếp từ request, header hoặc tham số người dùng. Repository đưa tên này vào câu SQL; chỉ dùng identifier đã được xác định trong cấu hình và phù hợp quy tắc đặt tên của database.

## 3. Đổi tên bảng thuộc tính liên quan

Trong cấu hình chuẩn của `JdbcIndexedSessionRepository`, tên bảng attributes được xây dựng từ tên bảng session với hậu tố `_ATTRIBUTES`. Vì vậy, khi đổi:

```yaml
spring:
  session:
    jdbc:
      table-name: PORTAL_SESSION
```

schema cần có cả:

- `PORTAL_SESSION`
- `PORTAL_SESSION_ATTRIBUTES`

Không có một property tiêu chuẩn độc lập trong cấu hình Boot thông thường để đặt tùy ý tên bảng attributes thành một tên hoàn toàn khác, chẳng hạn `PORTAL_SESSION_DATA`, trong khi bảng metadata là `PORTAL_SESSION`. Nếu cần quy ước tên độc lập, hãy kiểm tra API của phiên bản đang dùng. Có thể cần repository tùy chỉnh hoặc implementation mở rộng, đồng thời phải điều chỉnh các câu SQL, mapping và DDL cho nhất quán. Không đổi tên bảng attributes thủ công rồi hy vọng repository tự phát hiện.

Hậu tố `_ATTRIBUTES` là một phần của quy ước triển khai. Hãy chọn tên bảng gốc sao cho tên được ghép không vượt giới hạn identifier của database và không đụng tên bảng đã có. Ví dụ `APP_SESSION` tạo tên `APP_SESSION_ATTRIBUTES`, thường dễ quản lý hơn tên quá dài hoặc có dấu cách.

## 4. Schema namespace khác với schema initialization script

Từ “schema” có hai ý nghĩa thường gặp trong cấu hình JDBC:

1. **Database schema/namespace:** vùng chứa các bảng trong database, ví dụ `portal_data.APP_SESSION` trong PostgreSQL hoặc `APPDATA.APP_SESSION` trong Oracle.
2. **Schema SQL script:** file DDL tạo bảng và index, ví dụ file `schema-postgresql.sql` mà Spring Session chạy khi khởi tạo.

Property `spring.session.jdbc.schema` dùng để chỉ resource chứa script DDL cho Spring Session. Nó không tự chuyển các bảng vào namespace `portal_data` và cũng không đặt `search_path` của PostgreSQL. Ví dụ:

```yaml
spring:
  session:
    jdbc:
      schema: classpath:db/session-schema.sql
      initialize-schema: always
```

Ở đây `classpath:db/session-schema.sql` là vị trí file SQL trong ứng dụng. Script đó phải chứa câu lệnh tạo đúng các bảng và index trong namespace mong muốn. `initialize-schema: always` yêu cầu cơ chế khởi tạo chạy script theo cấu hình; lựa chọn này chủ yếu hữu ích trong môi trường kiểm thử hoặc môi trường được kiểm soát. Trong production, nên dùng migration tool và để Spring Session không tự chạy DDL.

## 5. Đặt bảng vào schema riêng của database

Cách đặt schema namespace phụ thuộc hệ quản trị và cấu hình `DataSource`. Một phương án thường dễ vận hành là cấu hình schema mặc định cho user/database connection, sau đó dùng `table-name` làm tên bảng không kèm namespace.

Ví dụ PostgreSQL có schema `portal_data`. Có thể cấu hình user database hoặc JDBC connection để dùng schema mặc định đó, rồi tạo `APP_SESSION` và `APP_SESSION_ATTRIBUTES` trong `portal_data`. Với PostgreSQL JDBC driver, tham số `currentSchema` trong JDBC URL có thể được dùng để thiết lập schema search path cho connection:

```properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/portal?currentSchema=portal_data
spring.datasource.username=portal_app
spring.datasource.password=${DB_PASSWORD}

spring.session.jdbc.table-name=APP_SESSION
spring.session.jdbc.initialize-schema=never
```

Đây là ví dụ theo PostgreSQL. Với SQL Server, Oracle, MySQL hoặc database khác, cách chọn schema mặc định và cách định danh bảng có thể khác. Một số hệ quản trị coi schema gần như user namespace; một số khác phân biệt database, catalog và schema. Hãy dùng cơ chế được JDBC driver/database hỗ trợ.

Nếu phiên bản Spring Session và database cho phép tên bảng có namespace, có thể cấu hình tên đầy đủ như `portal_data.APP_SESSION`; repository thường suy ra tên bảng thuộc tính từ cùng tên gốc. Tuy nhiên, cần xác minh cách implementation ghép hậu tố và cách database xử lý identifier. Đặc biệt, tên có dấu quote hoặc identifier phân biệt hoa/thường có thể làm câu SQL được tạo không hợp lệ nếu repository nối chuỗi tên bảng. Cấu hình schema mặc định của connection thường ít rủi ro hơn so với identifier có quoting phức tạp.

Không nhầm database/catalog với schema namespace. Nếu database có nhiều lớp định danh, hãy kiểm tra chính xác câu SQL cuối cùng đang trỏ tới đâu và quyền của user trên cả hai bảng.

## 6. DDL tùy chỉnh phải khớp với tên repository

Khi dùng tên bảng tùy chỉnh, script DDL phải tạo bảng metadata, bảng attributes, khóa chính, khóa ngoại và index mà repository cần. Ví dụ dưới đây minh họa cấu trúc PostgreSQL rút gọn cho tên `APP_SESSION`; cần đối chiếu script chính thức của đúng phiên bản Spring Session và điều chỉnh kiểu dữ liệu theo database thực tế:

```sql
CREATE TABLE portal_data.APP_SESSION (
    PRIMARY_ID CHAR(36) NOT NULL,
    SESSION_ID CHAR(36) NOT NULL,
    CREATION_TIME BIGINT NOT NULL,
    LAST_ACCESS_TIME BIGINT NOT NULL,
    MAX_INACTIVE_INTERVAL INT NOT NULL,
    EXPIRY_TIME BIGINT NOT NULL,
    PRINCIPAL_NAME VARCHAR(100),
    CONSTRAINT APP_SESSION_PK PRIMARY KEY (PRIMARY_ID)
);

CREATE UNIQUE INDEX APP_SESSION_IX1
    ON portal_data.APP_SESSION (SESSION_ID);

CREATE INDEX APP_SESSION_IX2
    ON portal_data.APP_SESSION (EXPIRY_TIME);

CREATE INDEX APP_SESSION_IX3
    ON portal_data.APP_SESSION (PRINCIPAL_NAME);

CREATE TABLE portal_data.APP_SESSION_ATTRIBUTES (
    SESSION_PRIMARY_ID CHAR(36) NOT NULL,
    ATTRIBUTE_NAME VARCHAR(200) NOT NULL,
    ATTRIBUTE_BYTES BYTEA NOT NULL,
    CONSTRAINT APP_SESSION_ATTRIBUTES_PK
        PRIMARY KEY (SESSION_PRIMARY_ID, ATTRIBUTE_NAME),
    CONSTRAINT APP_SESSION_ATTRIBUTES_FK
        FOREIGN KEY (SESSION_PRIMARY_ID)
        REFERENCES portal_data.APP_SESSION (PRIMARY_ID)
        ON DELETE CASCADE
);
```

Đây là mẫu minh họa, không phải script dùng chung cho mọi database. Schema chính thức có thể thay đổi theo phiên bản, nền tảng, độ dài cột và cách tạo index. Hãy lấy schema script tương ứng với phiên bản Spring Session và dialect, sau đó chỉnh tên bảng/schema có kiểm soát. Không bỏ cột hoặc index chỉ vì ứng dụng hiện tại chưa dùng một chức năng; repository có thể cần chúng cho truy vấn tìm session, dọn phiên hết hạn hoặc principal lookup.

Các thành phần cần đồng bộ:

- Tên bảng metadata phải khớp `table-name`.
- Tên bảng attributes phải khớp quy ước hậu tố hoặc repository tùy chỉnh.
- Khóa ngoại phải tham chiếu đúng bảng metadata và cột `PRIMARY_ID`.
- Index trên session ID cần bảo đảm tra cứu ID đúng và hiệu quả.
- Index trên expiry time hỗ trợ tác vụ dọn phiên hết hạn.
- Index trên principal name hỗ trợ các truy vấn theo principal nếu repository sử dụng.
- Kiểu nhị phân của `ATTRIBUTE_BYTES` phải tương thích database và serializer.

## 7. Quyền database và schema riêng

Khi đặt bảng trong schema riêng, tài khoản ứng dụng cần quyền trên cả hai bảng. Tùy database, quyền có thể gồm `SELECT`, `INSERT`, `UPDATE`, `DELETE` trên bảng session và attributes; quyền sequence nếu schema sử dụng sequence; quyền sử dụng schema hoặc quyền tạo bảng nếu ứng dụng được phép tự khởi tạo.

Trong production, thường nên tách quyền migration và quyền runtime:

- Tài khoản migration được cấp quyền tạo/sửa bảng, index, constraint trong schema session.
- Tài khoản ứng dụng chỉ có quyền thao tác dữ liệu cần thiết trên các bảng đã tạo.
- Tài khoản runtime không cần quyền `CREATE TABLE` nếu DDL được quản lý bằng Flyway/Liquibase hoặc quy trình DBA.

Nếu ứng dụng kết nối thành công nhưng nhận lỗi `permission denied`, kiểm tra quyền schema và quyền bảng attributes, không chỉ quyền trên bảng session chính. Nếu nhận lỗi `relation does not exist` hoặc `table not found`, kiểm tra schema mặc định, tên bảng, chữ hoa/thường và search path của connection.

Không cấp quyền rộng trên toàn database chỉ để xử lý lỗi thiếu quyền ở schema session. Cấp quyền tối thiểu trên namespace và các bảng cần thiết.

## 8. Quản lý DDL bằng Flyway hoặc Liquibase

Trong production, nên quản lý thay đổi tên bảng bằng migration có version. Một quy trình thường dùng:

1. Tạo schema namespace nếu chưa có.
2. Tạo bảng metadata và bảng attributes với tên mới.
3. Tạo đầy đủ primary key, foreign key và index.
4. Cấp quyền runtime cho user ứng dụng.
5. Cấu hình `spring.session.jdbc.table-name` và schema mặc định/qualified name tương ứng.
6. Triển khai ứng dụng và xác minh CRUD session.
7. Chỉ xóa bảng cũ sau khi không còn instance nào truy cập và dữ liệu cần thiết đã được xử lý.

Ví dụ cấu hình production:

```yaml
spring:
  session:
    jdbc:
      table-name: APP_SESSION
      initialize-schema: never
```

Flyway hoặc Liquibase chịu trách nhiệm tạo schema. Không bật `initialize-schema: always` đồng thời với migration mà không có lý do rõ ràng; hai cơ chế có thể cùng tạo hoặc sửa cấu trúc, khiến startup thất bại hoặc schema drift.

Đổi tên bảng không tự động di chuyển dữ liệu. Nếu bảng cũ đang có session còn hiệu lực, việc tạo bảng mới rỗng rồi đổi cấu hình có thể làm mọi người dùng bị đăng xuất vì repository không tìm thấy phiên cũ. Nếu cần giữ phiên, migration phải chuyển dữ liệu metadata và attributes theo đúng quan hệ, serializer và cấu trúc schema. Cũng cần đánh giá việc các instance cũ đang chạy song song vẫn truy cập bảng cũ trong rolling deployment.

## 9. Chiến lược đổi tên bảng khi ứng dụng đang chạy

Đổi tên bảng trực tiếp trong production có thể ảnh hưởng mọi request đang sử dụng session. Không nên chỉ chạy `ALTER TABLE ... RENAME` rồi triển khai một phiên bản ứng dụng mới nếu vẫn còn instance cũ dùng tên cũ.

Các lựa chọn thường gặp:

| Cách làm | Khi phù hợp | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Giữ nguyên bảng, chỉ đổi schema trong môi trường mới | Tách namespace cho lần triển khai mới | Cần cấu hình datasource và quyền đúng |
| Tạo bảng mới rồi copy dữ liệu | Cần giữ phiên đang hoạt động | Phải chuyển cả metadata, attributes, index và dữ liệu serialize |
| Đổi tên bảng tại chỗ trong maintenance window | Có thể chấp nhận gián đoạn và đăng xuất người dùng | Instance cũ/mới có thể không tương thích trong thời gian chuyển đổi |
| Dùng migration nhiều giai đoạn | Rolling deployment cần hạn chế downtime | Cần xác định rõ giai đoạn đọc/ghi và thời điểm loại bỏ bảng cũ |

Nếu không cần giữ phiên cũ, có thể chủ động vô hiệu hóa session theo kế hoạch, thông báo người dùng đăng nhập lại và tạo bảng mới. Nếu cần giữ phiên, kiểm tra schema migration bằng bản sao dữ liệu production, bao gồm dữ liệu attributes đã serialize. Không dùng thao tác copy đơn giản nếu schema, primary key hoặc serializer đã thay đổi.

## 10. Identifier, chữ hoa/thường và từ khóa SQL

Tên bảng và schema là SQL identifier, không phải giá trị dữ liệu. Quy tắc của database có thể khác nhau:

- PostgreSQL chuyển identifier không quote về chữ thường; identifier được quote có thể phân biệt hoa/thường.
- Oracle thường lưu identifier không quote ở dạng chữ hoa.
- SQL Server có thể phụ thuộc collation và quy tắc identifier của database.
- MySQL có thể có khác biệt về chữ hoa/thường theo hệ điều hành và cấu hình.

Để giảm khác biệt, ưu tiên tên đơn giản như `APP_SESSION` và `APP_SESSION_ATTRIBUTES`, không có dấu cách, dấu gạch nối hoặc từ khóa SQL. Tránh dùng tên cần quoting phức tạp. Nếu dùng schema-qualified identifier, xác nhận cách repository tạo câu SQL với tên đó và kiểm thử trên đúng database production.

Không ghép tên schema/bảng từ dữ liệu người dùng. Cấu hình tên bảng cần được cố định khi khởi động và chỉ thay đổi qua release/migration đã kiểm soát. Nếu database yêu cầu quote identifier, cần xác minh repository có hỗ trợ đúng cú pháp; không tự thêm quote một cách phỏng đoán vì hậu tố `_ATTRIBUTES` có thể được nối vào sai vị trí.

## 11. Kiểm thử cấu hình bảng và schema

Kiểm thử phải chứng minh repository thực sự sử dụng bảng đã tùy chỉnh, không chỉ chứng minh DDL tồn tại. Một bộ kiểm tra hữu ích:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Ứng dụng khởi động với `table-name` mới | Repository tạo và truy vấn đúng bảng metadata |
| Tạo session | Bản ghi xuất hiện trong bảng metadata mới |
| Lưu session attribute | Bản ghi xuất hiện trong bảng attributes tương ứng |
| Đọc lại session | Metadata và attributes được khôi phục đầy đủ |
| Cập nhật attribute | Dữ liệu được ghi đúng bảng và đúng schema |
| Xóa/invalidate session | Bảng attributes được dọn theo FK hoặc logic repository |
| Session hết hạn | Tác vụ cleanup dùng đúng bảng và index expiry |
| Nhiều instance | Tất cả instance dùng cùng table name và schema namespace |
| User thiếu quyền | Lỗi quyền được phát hiện và phân biệt với lỗi không tìm thấy bảng |
| Migration dữ liệu cũ | Session còn hiệu lực được đọc đúng hoặc bị vô hiệu hóa theo kế hoạch |

Nên chạy integration test với cùng loại database và dialect production, ví dụ Testcontainers cho PostgreSQL hoặc database tương ứng. H2 có thể hữu ích cho kiểm thử nhanh nhưng không chứng minh cú pháp DDL, schema qualification, kiểu BLOB/BYTEA, identifier quoting và index behavior trên database production.

Sau khi triển khai, kiểm tra metadata database để xác nhận bảng nằm đúng schema, index/foreign key tồn tại và user runtime có quyền cần thiết. Có thể bật log SQL ở môi trường test để xác minh tên bảng được repository sử dụng; tránh bật log có chứa dữ liệu session nhạy cảm trong production.

## 12. Lỗi thường gặp và cách chẩn đoán

**Bảng metadata được tìm thấy nhưng lưu attributes thất bại.** Kiểm tra bảng `<table-name>_ATTRIBUTES` đã được tạo trong cùng schema chưa, tên có đúng quy ước không, kiểu `ATTRIBUTE_BYTES` có phù hợp không và user runtime có quyền ghi không.

**Ứng dụng vẫn truy vấn `SPRING_SESSION` sau khi đã đổi tên.** Kiểm tra property `spring.session.jdbc.table-name`, profile đang active và repository bean thực tế. Nếu dùng `@EnableJdbcHttpSession`, kiểm tra `tableName` của annotation. Xác nhận không có cấu hình auto/manual chồng chéo.

**Đặt `spring.session.jdbc.schema=portal_data` nhưng bảng không nằm trong schema đó.** Property này chỉ định script DDL, không phải database namespace. Cấu hình schema mặc định/qualified table name qua datasource hoặc cơ chế database tương ứng, đồng thời sửa DDL để tạo bảng đúng namespace.

**Lỗi relation/table not found.** Kiểm tra database user, default schema/search path, schema-qualified identifier, chữ hoa/thường và tên bảng attributes. Xác minh DDL đã chạy trên đúng database mà ứng dụng đang kết nối.

**Lỗi permission denied.** Kiểm tra quyền trên schema và cả hai bảng, cùng quyền sequence nếu database cần. Tách quyền migration khỏi quyền runtime thay vì cấp quyền quản trị toàn database.

**Đăng nhập bị mất sau khi đổi tên bảng.** Repository mới có thể đang đọc bảng rỗng trong khi dữ liệu cũ vẫn ở bảng trước. Nếu cần giữ phiên, phải migrate cả bảng session và attributes; nếu không, chủ động vô hiệu hóa phiên cũ và thông báo đăng nhập lại.

**Migration chạy thành công nhưng Spring Session không lưu được.** Kiểm tra DDL có khớp phiên bản Spring Session không, đặc biệt cột, kiểu dữ liệu nhị phân, khóa chính, khóa ngoại và index. Không tự lược bỏ cột/index dựa trên một truy vấn test đơn giản.

## 13. Quy trình triển khai đề xuất

1. Xác định database/dialect, phiên bản Spring Session và repository JDBC thực tế.
2. Chọn tên bảng gốc ngắn, ổn định; xác định tên bảng attributes theo hậu tố repository sử dụng.
3. Chọn schema namespace bằng default schema của datasource hoặc qualified identifier đã được kiểm thử.
4. Tạo DDL từ schema script chính thức của đúng phiên bản/dialect rồi chỉnh tên bảng/schema.
5. Quản lý DDL bằng Flyway/Liquibase; đặt `initialize-schema: never` trong production.
6. Cấu hình `spring.session.jdbc.table-name` hoặc `@EnableJdbcHttpSession(tableName = ...)` theo một cơ chế duy nhất.
7. Cấp quyền tối thiểu cho runtime user trên cả hai bảng và các đối tượng database liên quan.
8. Kiểm thử tạo, đọc, cập nhật, xóa, timeout, attributes và nhiều instance trên đúng loại database.
9. Nếu đổi tên trên hệ thống đã có dữ liệu, lập kế hoạch migration/gián đoạn và xác minh phiên cũ trước khi loại bỏ bảng cũ.

Đổi tên bảng và schema trong Spring Session JDBC là thay đổi đồng bộ giữa cấu hình repository, DDL, database namespace và quyền truy cập. Bảng metadata và bảng attributes phải cùng tuân theo quy ước mà repository sử dụng; script `spring.session.jdbc.schema` chỉ cung cấp DDL để khởi tạo. Khi quản lý thay đổi bằng migration và kiểm thử trên đúng database, ứng dụng có thể đặt session tables trong namespace riêng mà vẫn duy trì việc lưu, khôi phục và dọn phiên nhất quán giữa nhiều instance.
