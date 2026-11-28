# Script schema theo hệ quản trị cơ sở dữ liệu

Spring Session JDBC lưu `HttpSession` vào các bảng quan hệ dùng chung để nhiều instance của ứng dụng Spring có thể đọc và cập nhật cùng một phiên. Để repository hoạt động, database phải có schema tương thích với Spring Session. Schema gồm bảng metadata phiên, bảng thuộc tính phiên, khóa chính, khóa ngoại và các index phục vụ tìm phiên, dọn phiên hết hạn và tra cứu theo principal.

Spring Session cung cấp các script schema theo từng hệ quản trị cơ sở dữ liệu (DBMS). Khác biệt giữa các script chủ yếu nằm ở kiểu dữ liệu nhị phân, cú pháp DDL, engine và quy tắc đặt tên của từng database. Không nên lấy nguyên script của PostgreSQL chạy trên MySQL hoặc SQL Server; cần dùng script đúng dialect và đúng phiên bản Spring Session.

## 1. Hai bảng cốt lõi của Spring Session JDBC

Schema mặc định thường có hai bảng:

| Bảng | Vai trò | Dữ liệu chính |
|---|---|---|
| `SPRING_SESSION` | Lưu metadata và định danh phiên | ID nội bộ, session ID, thời điểm tạo, lần truy cập gần nhất, timeout, thời điểm hết hạn, principal name |
| `SPRING_SESSION_ATTRIBUTES` | Lưu từng thuộc tính của phiên | Khóa liên kết đến phiên, tên thuộc tính và dữ liệu đã tuần tự hóa |

Một số cột quan trọng trong `SPRING_SESSION`:

| Cột | Ý nghĩa |
|---|---|
| `PRIMARY_ID` | Khóa chính nội bộ của bản ghi session |
| `SESSION_ID` | Định danh phiên mà client mang trong cookie hoặc header |
| `CREATION_TIME` | Thời điểm tạo phiên, thường lưu dạng epoch milliseconds |
| `LAST_ACCESS_TIME` | Thời điểm truy cập gần nhất, thường lưu dạng epoch milliseconds |
| `MAX_INACTIVE_INTERVAL` | Khoảng không hoạt động tối đa, tính bằng giây |
| `EXPIRY_TIME` | Mốc hết hạn được tính từ metadata thời gian |
| `PRINCIPAL_NAME` | Tên principal để tra cứu phiên theo người dùng khi repository hỗ trợ index |

`PRIMARY_ID` và `SESSION_ID` có mục đích khác nhau. `PRIMARY_ID` liên kết bản ghi metadata với các thuộc tính trong bảng con. `SESSION_ID` là giá trị định danh phiên được dùng để tìm phiên từ request. Thông thường `SESSION_ID` có unique index, còn `PRIMARY_ID` là primary key.

Trong `SPRING_SESSION_ATTRIBUTES`, mỗi thuộc tính được lưu thành một hàng. Khóa chính ghép thường gồm `SESSION_PRIMARY_ID` và `ATTRIBUTE_NAME`. Khóa ngoại `SESSION_PRIMARY_ID` tham chiếu `SPRING_SESSION.PRIMARY_ID`; `ON DELETE CASCADE` giúp xóa các hàng thuộc tính khi bản ghi phiên bị xóa, nếu database và schema đang dùng hỗ trợ hành vi đó.

## 2. Vì sao cần script riêng theo DBMS?

Các hệ quản trị có kiểu dữ liệu nhị phân và cú pháp DDL khác nhau. Thuộc tính session sau khi serialize là dữ liệu byte, nên cột `ATTRIBUTE_BYTES` phải dùng kiểu nhị phân phù hợp với database.

| DBMS | Kiểu dữ liệu nhị phân thường thấy trong schema Spring Session |
|---|---|
| PostgreSQL | `BYTEA` |
| MySQL/MariaDB | `BLOB` theo script tương ứng; một số ứng dụng có thể cần kiểu dung lượng lớn hơn theo chính sách dữ liệu |
| Oracle | `BLOB` |
| Microsoft SQL Server | `VARBINARY(MAX)` |
| H2 | `BINARY LARGE OBJECT` hoặc kiểu tương ứng trong script của phiên bản |
| DB2 | `BLOB` |

Các script cũng có thể khác về kiểu chuỗi, giới hạn độ dài, cú pháp index, engine lưu trữ và cách đặt tên constraint. Vì vậy, dùng script đi kèm đúng phiên bản thư viện là cách khởi đầu an toàn hơn tự viết một schema chung rồi hy vọng mọi DBMS chấp nhận.

## 3. Các script schema được đóng gói cùng Spring Session

Module `spring-session-jdbc` cung cấp các tài nguyên schema cho những database được hỗ trợ. Các script thường nằm trong package resource:

```text
org/springframework/session/jdbc/
```

Tên file thường theo mẫu `schema-<platform>.sql`, ví dụ:

```text
org/springframework/session/jdbc/schema-postgresql.sql
org/springframework/session/jdbc/schema-mysql.sql
org/springframework/session/jdbc/schema-oracle.sql
org/springframework/session/jdbc/schema-sqlserver.sql
```

Danh sách chính xác phụ thuộc phiên bản Spring Session đang dùng. Hãy kiểm tra nội dung JAR `spring-session-jdbc` trong dependency cache hoặc artifact được đóng gói của chính dự án. Không suy đoán tên file chỉ từ tên DBMS; cũng không sao chép script từ một phiên bản khác mà chưa đối chiếu.

Các script này tạo schema theo quy ước Spring Session, gồm bảng phiên, bảng thuộc tính và các index cần thiết. Khi nâng phiên bản Spring Session, so sánh script schema của phiên bản mới với schema đang triển khai để biết có thay đổi cần migration hay không.

## 4. Ví dụ schema cho PostgreSQL

Ví dụ dưới đây minh họa cấu trúc cốt lõi theo dialect PostgreSQL. Script chính thức được đóng gói trong đúng phiên bản Spring Session vẫn là nguồn tham chiếu cuối cùng:

```sql
CREATE TABLE SPRING_SESSION (
    PRIMARY_ID CHAR(36) NOT NULL,
    SESSION_ID CHAR(36) NOT NULL,
    CREATION_TIME BIGINT NOT NULL,
    LAST_ACCESS_TIME BIGINT NOT NULL,
    MAX_INACTIVE_INTERVAL INT NOT NULL,
    EXPIRY_TIME BIGINT NOT NULL,
    PRINCIPAL_NAME VARCHAR(100),
    CONSTRAINT SPRING_SESSION_PK PRIMARY KEY (PRIMARY_ID)
);

CREATE UNIQUE INDEX SPRING_SESSION_IX1
    ON SPRING_SESSION (SESSION_ID);
CREATE INDEX SPRING_SESSION_IX2
    ON SPRING_SESSION (EXPIRY_TIME);
CREATE INDEX SPRING_SESSION_IX3
    ON SPRING_SESSION (PRINCIPAL_NAME);

CREATE TABLE SPRING_SESSION_ATTRIBUTES (
    SESSION_PRIMARY_ID CHAR(36) NOT NULL,
    ATTRIBUTE_NAME VARCHAR(200) NOT NULL,
    ATTRIBUTE_BYTES BYTEA NOT NULL,
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_PK
        PRIMARY KEY (SESSION_PRIMARY_ID, ATTRIBUTE_NAME),
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_FK
        FOREIGN KEY (SESSION_PRIMARY_ID)
        REFERENCES SPRING_SESSION (PRIMARY_ID)
        ON DELETE CASCADE
);
```

`BYTEA` là kiểu dữ liệu nhị phân của PostgreSQL. Index trên `SESSION_ID` hỗ trợ tra cứu phiên theo ID; index `EXPIRY_TIME` hỗ trợ tìm bản ghi hết hạn để cleanup; index `PRINCIPAL_NAME` hỗ trợ truy vấn phiên theo principal khi tính năng đó được dùng.

Tên bảng và index ở ví dụ là tên mặc định phổ biến. Nếu ứng dụng cấu hình tên bảng khác hoặc dùng schema database riêng, phải bảo đảm mọi câu lệnh repository, script và migration cùng trỏ đến một cấu trúc nhất quán.

## 5. Ví dụ schema cho MySQL và MariaDB

MySQL/MariaDB dùng kiểu `BLOB` cho cột dữ liệu nhị phân trong script tương ứng. Với khóa ngoại và `ON DELETE CASCADE`, bảng thường cần engine hỗ trợ foreign key như InnoDB.

Phần bảng thuộc tính có thể có dạng:

```sql
CREATE TABLE SPRING_SESSION_ATTRIBUTES (
    SESSION_PRIMARY_ID CHAR(36) NOT NULL,
    ATTRIBUTE_NAME VARCHAR(200) NOT NULL,
    ATTRIBUTE_BYTES BLOB NOT NULL,
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_PK
        PRIMARY KEY (SESSION_PRIMARY_ID, ATTRIBUTE_NAME),
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_FK
        FOREIGN KEY (SESSION_PRIMARY_ID)
        REFERENCES SPRING_SESSION (PRIMARY_ID)
        ON DELETE CASCADE
) ENGINE=InnoDB;
```

Nếu session attribute có thể lớn hơn giới hạn của kiểu `BLOB` mà script sử dụng, cần đánh giá dung lượng thực tế và cân nhắc kiểu dữ liệu lớn hơn theo khả năng DBMS. Không tự đổi sang `LONGTEXT` hoặc kiểu ký tự vì dữ liệu được lưu là byte đã serialize, không phải chuỗi văn bản tùy ý. Khi thay đổi kiểu cột, kiểm thử serializer, migration và backup/restore.

Với MySQL, cũng kiểm tra collation và charset của các cột chuỗi, quy tắc so sánh `SESSION_ID` và `PRINCIPAL_NAME`, engine của cả hai bảng, phiên bản database và giới hạn index. Dùng script của Spring Session cho đúng DBMS/version làm điểm bắt đầu, sau đó điều chỉnh bằng migration được kiểm soát nếu cần.

## 6. Khác biệt ở Oracle và SQL Server

Oracle thường dùng `BLOB` cho `ATTRIBUTE_BYTES`; kiểu chuỗi và quy tắc tên object có thể khác với các database dùng `VARCHAR`. SQL Server dùng `VARBINARY(MAX)` cho dữ liệu nhị phân lớn và có cú pháp DDL/index riêng. Ví dụ minh họa kiểu cột:

```sql
-- Oracle
ATTRIBUTE_BYTES BLOB NOT NULL
```

```sql
-- Microsoft SQL Server
ATTRIBUTE_BYTES VARBINARY(MAX) NOT NULL
```

Đây chỉ là phần kiểu cột, không phải script tạo schema hoàn chỉnh cho hai hệ quản trị. Dùng file `schema-oracle.sql` hoặc `schema-sqlserver.sql` được đóng gói cùng phiên bản Spring Session của dự án để có đúng cú pháp primary key, index, constraint và kiểu dữ liệu.

Với Oracle, lưu ý quy tắc viết hoa/thường và cách database xử lý identifier không đặt trong dấu quote. Với SQL Server, kiểm tra schema owner, collation, giới hạn tên object và quyền tạo index/constraint. Nếu triển khai trên database có schema riêng như `APP_SESSION`, migration cần tạo bảng trong đúng schema và tài khoản runtime cần quyền tương ứng.

## 7. Hiểu các index trong schema

Các index tiêu chuẩn phục vụ các truy vấn thường xuyên của repository:

| Index | Cột | Mục đích |
|---|---|---|
| Unique index trên `SESSION_ID` | `SESSION_ID` | Tìm một phiên theo ID và ngăn trùng định danh |
| Index hết hạn | `EXPIRY_TIME` | Tìm các phiên đã đến hạn để dọn |
| Index principal | `PRINCIPAL_NAME` | Tìm các phiên thuộc một principal |

Không xóa index chỉ vì ứng dụng hiện chưa có màn hình quản lý phiên. Repository hoặc tính năng tích hợp có thể cần index đó cho cleanup hay truy vấn khác. Nếu muốn bỏ index để giảm chi phí ghi, phải đo workload, kiểm tra SQL mà repository phát ra và xác nhận tính năng liên quan không còn phụ thuộc.

Index trên `PRINCIPAL_NAME` đặc biệt hữu ích khi dùng repository JDBC có khả năng tra cứu phiên theo principal hoặc tích hợp quản lý phiên đồng thời. Nếu hệ thống chỉ dùng tra cứu theo session ID, index vẫn có thể tồn tại trong schema mặc định; giữ schema chuẩn giúp tránh khác biệt khó bảo trì khi nâng cấp.

## 8. Tạo schema tự động bằng Spring Boot

Spring Boot có thể khởi tạo schema Spring Session JDBC từ script classpath. Cấu hình thường gặp:

```yaml
spring:
  session:
    store-type: jdbc
    jdbc:
      initialize-schema: embedded
```

`initialize-schema` điều khiển việc chạy script tạo schema. Các giá trị thường gặp gồm:

| Giá trị | Hành vi |
|---|---|
| `embedded` | Chỉ tự khởi tạo cho embedded database được nhận diện |
| `always` | Luôn chạy script khởi tạo theo cấu hình |
| `never` | Không tự chạy script khởi tạo |

Tên thuộc tính, giá trị mặc định và cách xác định platform phụ thuộc phiên bản Spring Boot. Một số cấu hình dùng resource mặc định có placeholder platform; có thể chỉ định script riêng bằng thuộc tính `spring.session.jdbc.schema` nếu phiên bản hỗ trợ. Kiểm tra metadata cấu hình của đúng phiên bản Boot trước khi áp dụng.

Trong môi trường local hoặc test dùng H2, `embedded` có thể thuận tiện để tạo bảng tự động. Với production, thường nên quản lý schema bằng Flyway hoặc Liquibase để kiểm soát phiên bản, thứ tự migration, audit và rollback. Khi công cụ migration đã quản lý bảng, đặt `initialize-schema: never` để tránh Boot chạy lại script tạo bảng khi khởi động.

Không để nhiều cơ chế cùng tạo một schema. Nếu Flyway đã tạo `SPRING_SESSION`, việc Boot chạy lại `CREATE TABLE` có thể làm ứng dụng khởi động thất bại vì bảng đã tồn tại.

## 9. Quản lý schema bằng Flyway hoặc Liquibase

Với production, nên đặt script schema vào migration của dự án, ví dụ:

```text
src/main/resources/db/migration/
  V001__create_spring_session_tables.sql
```

Migration phải dùng DDL đúng DBMS của môi trường triển khai. Nếu dự án hỗ trợ nhiều database, có thể duy trì migration theo từng vendor hoặc dùng cơ chế placeholder/changelog có điều kiện của công cụ migration. Không dùng cùng một file DDL nếu kiểu nhị phân hoặc cú pháp index không tương thích giữa các hệ quản trị.

Ví dụ cấu hình:

```yaml
spring:
  session:
    store-type: jdbc
    jdbc:
      initialize-schema: never
```

Flyway/Liquibase chạy trước khi ứng dụng cần truy cập repository. Tài khoản migration có thể cần quyền tạo bảng, index và constraint; tài khoản runtime nên chỉ có quyền đọc/ghi/xóa cần thiết. Tách hai tài khoản giúp giới hạn quyền của ứng dụng khi chạy thường xuyên.

Khi nâng Spring Session, so sánh schema script của phiên bản mới với schema đang dùng. Nếu có thay đổi, tạo migration tăng dần, thử trên bản sao database và kiểm tra cả phiên đang tồn tại. Không sửa trực tiếp migration đã chạy trên môi trường dùng chung; tạo migration mới để lịch sử schema có thể tái lập.

## 10. Cấu hình tên bảng hoặc schema riêng

Mặc định, Spring Session JDBC dùng tên bảng `SPRING_SESSION` và `SPRING_SESSION_ATTRIBUTES`. Nếu cần đổi tên để tránh xung đột hoặc đặt trong schema riêng, cấu hình table name và đảm bảo DDL tạo đúng các tên tương ứng.

Ví dụ với annotation:

```java
@Configuration
@EnableJdbcHttpSession(tableName = "APP_SESSION")
public class JdbcSessionConfiguration {
}
```

Tên bảng thuộc tính thường được tạo dựa trên quy ước của repository và table name cấu hình; hãy xác minh chính xác trong phiên bản đang dùng. Không chỉ đổi tên bảng metadata mà quên bảng attributes, foreign key hoặc index.

Với schema database riêng, ví dụ `APP_DATA`, có thể cần qualify tên bảng trong DDL hoặc cấu hình search path/default schema của tài khoản database. Kiểm tra cách JDBC repository tạo SQL; một số cấu hình dùng tên bảng không qualify và phụ thuộc default schema của connection. Tên bảng và schema phải giống nhau giữa migration, tài khoản runtime và repository.

Tránh dùng tên trùng từ khóa SQL hoặc tên chứa ký tự cần quote. Nếu phải quote identifier, xác minh quy tắc quote của DBMS và cách repository tạo SQL động. Tên đơn giản gồm chữ và dấu gạch dưới thường dễ vận hành hơn.

## 11. Quyền database và thứ tự khởi tạo

Tài khoản chạy ứng dụng cần quyền cần thiết trên cả hai bảng: đọc, chèn, cập nhật, xóa và truy cập index theo cách DBMS yêu cầu. Tài khoản migration cần quyền tạo bảng, index, khóa chính, khóa ngoại và thay đổi schema. Không nên cấp quyền DBA hoặc quyền quản trị toàn database cho ứng dụng chỉ để Spring Session hoạt động.

Trong triển khai, bảo đảm thứ tự:

1. Database server sẵn sàng và database/schema đích tồn tại.
2. Migration tạo bảng, index và constraint thành công.
3. Tài khoản runtime có quyền trên schema.
4. Ứng dụng khởi động và tạo `DataSource`/`JdbcIndexedSessionRepository`.
5. Health check xác nhận kết nối và thao tác repository cơ bản.

Nếu ứng dụng khởi động trước migration, request đầu tiên có thể lỗi với thông báo thiếu bảng hoặc cột. Trong cụm nhiều instance, migration nên chạy như một bước triển khai có điều phối, không để mọi node đồng thời chạy DDL không kiểm soát.

## 12. Kiểm tra schema sau khi tạo

Sau khi chạy script, kiểm tra tối thiểu:

- Có đủ hai bảng `SPRING_SESSION` và `SPRING_SESSION_ATTRIBUTES`.
- Kiểu dữ liệu của các cột khớp dialect và script của phiên bản Spring Session.
- `PRIMARY_ID` là khóa chính; `SESSION_ID` có unique index.
- Có index trên `EXPIRY_TIME` và `PRINCIPAL_NAME` theo schema được chọn.
- Khóa ngoại attributes tham chiếu đúng `SPRING_SESSION.PRIMARY_ID`.
- `ON DELETE CASCADE` hoạt động đúng nếu script định nghĩa.
- Tài khoản runtime có quyền đọc/ghi/xóa.
- Các cột thời gian và timeout có độ rộng/kiểu phù hợp, không bị chuyển thành chuỗi.

Có thể dùng metadata của database (`information_schema`, catalog của Oracle hoặc SQL Server) để xác nhận bảng và index. Cú pháp truy vấn metadata khác nhau theo DBMS; nên viết script kiểm tra riêng cho từng vendor nếu quy trình triển khai hỗ trợ nhiều database.

## 13. Kiểm thử repository với database thật

Một schema được tạo thành công chưa đủ chứng minh Spring Session có thể lưu và khôi phục phiên. Hãy chạy integration test dùng DBMS giống production hoặc container test cùng loại:

1. Khởi động ứng dụng với `DataSource` và schema đã migration.
2. Gửi request tạo session và đặt một thuộc tính.
3. Xác nhận response phát session ID theo cookie/header resolver.
4. Gửi request tiếp theo với định danh đó và đọc lại thuộc tính.
5. Gọi logout và xác nhận phiên không còn được khôi phục.
6. Kiểm tra bản ghi trong hai bảng và hành vi xóa cascade.
7. Chờ phiên hết hạn hoặc dùng timeout ngắn trong test để xác nhận cleanup.
8. Nếu có nhiều instance, tạo phiên qua instance A và khôi phục qua instance B.

Test dùng H2 có thể phát hiện lỗi cơ bản nhưng không thay thế test trên PostgreSQL, MySQL, Oracle hoặc SQL Server nếu production dùng DBMS đó. Các khác biệt về BLOB, index, collation, transaction isolation, identifier và DDL có thể chỉ xuất hiện trên database đích.

Không nên dùng `MockHttpSession` để xác minh schema JDBC; mock không truy cập bảng. Test tích hợp phải đi qua `SessionRepositoryFilter` hoặc repository JDBC thật.

## 14. Lỗi thường gặp khi áp dụng script

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra và xử lý |
|---|---|---|
| `Table SPRING_SESSION not found` | Script chưa chạy, chạy sai schema hoặc ứng dụng dùng datasource khác | Kiểm tra migration history, default schema và `DataSource` hiệu lực |
| Lỗi kiểu dữ liệu `BLOB`/binary | Dùng script của DBMS khác hoặc driver không tương thích | Dùng schema script đúng platform và driver phù hợp |
| Lỗi cú pháp khi tạo index | Cú pháp DDL khác vendor hoặc identifier cần quote | Đối chiếu script đi kèm đúng phiên bản và DBMS |
| Không xóa được session do foreign key | Bảng attributes không có cascade hoặc constraint tạo sai | Kiểm tra FK tham chiếu `PRIMARY_ID` và hành vi cascade |
| Tra cứu session chậm | Thiếu index trên `SESSION_ID`, `EXPIRY_TIME` hoặc `PRINCIPAL_NAME` | Kiểm tra execution plan và index theo schema chuẩn |
| Ứng dụng lỗi khi khởi động do bảng đã tồn tại | Boot initialization và Flyway/Liquibase cùng chạy | Chọn một cơ chế sở hữu schema; thường tắt initialize-schema khi dùng migration |
| Có bảng nhưng insert/update bị từ chối | Tài khoản runtime thiếu quyền hoặc schema owner không đúng | Cấp quyền tối thiểu trên đúng schema |
| Test H2 chạy nhưng production lỗi | DDL/kiểu dữ liệu khác DBMS | Chạy integration test với cùng loại database production |
| Nâng Spring Session rồi repository lỗi SQL | Schema hiện tại không còn tương thích hoặc script phiên bản mới có thay đổi | So sánh schema và tạo migration có kiểm soát |

Không sửa lỗi bằng cách tự thêm cột hoặc xóa index ngay trên production khi chưa hiểu truy vấn repository và phiên bản thư viện. Tạo migration có review, thử trên bản sao dữ liệu và xác minh rollback/backup trước khi áp dụng.

## 15. Checklist triển khai

- [ ] Xác định DBMS và phiên bản database thực tế.
- [ ] Dùng schema script đi kèm đúng phiên bản `spring-session-jdbc`.
- [ ] Kiểm tra kiểu cột nhị phân của `ATTRIBUTE_BYTES`.
- [ ] Có đủ primary key, unique index, index expiry/principal và foreign key.
- [ ] Dùng Flyway/Liquibase hoặc cơ chế schema initialization có chủ sở hữu rõ ràng.
- [ ] Không để Boot và công cụ migration cùng tạo schema.
- [ ] Cấu hình đúng tên bảng/schema nếu dùng quy ước riêng.
- [ ] Tách quyền migration và quyền runtime theo nguyên tắc tối thiểu.
- [ ] Kiểm thử tạo, đọc, cập nhật, hết hạn và xóa session trên DBMS đích.
- [ ] Kiểm thử khôi phục phiên giữa các instance cùng dùng database.
- [ ] So sánh schema khi nâng phiên bản Spring Session và không sửa migration đã chạy.

Script schema theo DBMS là nền tảng để Spring Session JDBC lưu metadata và thuộc tính phiên đúng cách. Chọn script theo database và phiên bản thư viện, giữ nguyên các khóa/index cần thiết, quản lý thay đổi bằng migration và kiểm thử trên đúng hệ quản trị production. Khi schema, repository và cấu hình `DataSource` thống nhất, các instance có thể dùng chung phiên Servlet qua JDBC với vòng đời và cleanup có thể dự đoán.
