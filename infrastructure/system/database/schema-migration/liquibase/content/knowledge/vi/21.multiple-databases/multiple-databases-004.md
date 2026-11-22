# Kiểm thử cùng migration trên từng hệ quản trị được hỗ trợ

Trong chương **Nhiều cơ sở dữ liệu** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, một changelog có thể được thiết kế để triển khai trên nhiều hệ quản trị cơ sở dữ liệu (DBMS), nhưng việc cú pháp Liquibase được chấp nhận không đồng nghĩa migration có cùng hành vi trên mọi DBMS. Mỗi hệ quản trị có kiểu dữ liệu, quy tắc identifier, transaction DDL, khóa bảng, metadata, index, sequence, collation và cách thực thi SQL riêng. Vì vậy, phải kiểm thử **cùng một ý định migration trên từng DBMS và phiên bản nằm trong phạm vi hỗ trợ**.

Phạm vi kiến thức của dịch vụ **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài học áp dụng đầy đủ phạm vi đó vào việc kiểm thử cùng migration trên từng hệ quản trị được hỗ trợ.

Mục tiêu của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Với hệ thống đa DBMS, các nguyên tắc đó cần được áp dụng cho toàn bộ ma trận nền tảng: giữ changelog có thể tái lập, kiểm tra SQL được sinh ra, xác minh cấu trúc và dữ liệu thực tế, đồng thời phát hiện sớm những khác biệt về semantics giữa các engine.

Bài học hướng dẫn cách xây dựng ma trận kiểm thử, lựa chọn DBMS thật để chạy integration test, thiết kế changeset portable và nhánh đặc thù, kiểm tra upgrade/rollback, và đưa kết quả vào pipeline phát hành.

## 1. Cùng migration không có nghĩa SQL phải giống nhau

Liquibase cung cấp change type ở mức khái niệm như createTable, addColumn, addForeignKeyConstraint, createIndex và modifyDataType. Công cụ chuyển những khai báo này thành SQL phù hợp với DBMS đang kết nối.

Ví dụ, cùng một ý định:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-001-create-payment-status"
      author: "team-db"
      changes:
        - createTable:
            schemaName: app
            tableName: payment_status
            columns:
              - column:
                  name: code
                  type: VARCHAR(24)
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_payment_status
                    nullable: false
              - column:
                  name: display_name
                  type: VARCHAR(100)
                  constraints:
                    nullable: false
~~~

Liquibase có thể sinh DDL khác nhau cho PostgreSQL, MySQL, SQL Server hoặc Oracle. Khác biệt về dấu quote, kiểu dữ liệu vật lý và cú pháp tạo constraint không nhất thiết là lỗi. Điều cần giữ nhất quán là **ý nghĩa mong đợi**:

- Có bảng app.payment_status.
- code là khóa chính, không NULL và duy nhất.
- display_name không NULL.
- Độ dài và semantics của cột đáp ứng hợp đồng dữ liệu.
- Ứng dụng có thể đọc/ghi các giá trị theo cách đã thiết kế.

Không nên đặt mục tiêu mọi DBMS phải sinh ra cùng một chuỗi SQL. Nên đặt mục tiêu chúng tạo ra **schema và hành vi tương đương theo hợp đồng đã định nghĩa**, trừ những khác biệt vật lý được chấp nhận và ghi lại.

## 2. Xác định rõ DBMS nào thực sự được hỗ trợ

Trước khi viết test, lập danh sách chính thức các hệ quản trị và phiên bản mà sản phẩm cam kết hỗ trợ. Ví dụ một dự án có thể hỗ trợ một số phiên bản PostgreSQL, MySQL, SQL Server và Oracle; con số cụ thể phải lấy từ chính sách sản phẩm và phiên bản driver đang được chứng nhận.

Ma trận cần ghi nhận:

| Thành phần | Thông tin cần cố định |
|---|---|
| DBMS | PostgreSQL, MySQL, MariaDB, SQL Server, Oracle hoặc engine khác |
| Phiên bản server | Phiên bản tối thiểu, phiên bản đang triển khai, phiên bản dự kiến nâng cấp |
| Edition/compatibility | Edition, compatibility level hoặc feature flag ảnh hưởng DDL |
| JDBC driver | Tên và phiên bản driver được dùng trong test/production |
| Liquibase | Phiên bản CLI/library và các extension |
| Java/runtime | Phiên bản JDK và Spring Boot nếu migration chạy trong ứng dụng |
| Encoding/collation | Charset, collation, timezone và các thiết lập ảnh hưởng dữ liệu |
| Cấu hình schema | Catalog, schema mặc định, search path và tài khoản migration |

Không ghi “hỗ trợ MySQL” nếu chỉ mới thử một phiên bản MySQL trong môi trường local. Phải nêu rõ phiên bản nào đã được kiểm thử và phiên bản nào chưa nằm trong phạm vi cam kết.

### Ma trận ví dụ

| DBMS | Phiên bản được chứng nhận | Cách kiểm thử |
|---|---|---|
| PostgreSQL | Theo support policy của dự án | Container/database thật, driver đúng phiên bản |
| MySQL | Theo support policy của dự án | Engine thật với SQL mode/collation đã chọn |
| SQL Server | Theo support policy của dự án | Engine thật, compatibility level phù hợp |
| Oracle | Theo support policy của dự án | Engine thật, schema/user và quyền tương đương |
| DBMS khác | Chỉ khi có cam kết hỗ trợ | Bổ sung test suite và tiêu chí riêng |

Đây là mẫu ma trận, không phải tuyên bố dự án bắt buộc hỗ trợ tất cả các DBMS trên. Nếu một engine không còn được hỗ trợ, hãy loại khỏi ma trận chính thức theo quy trình phát hành; đừng để test suite ngầm quyết định phạm vi hỗ trợ.

## 3. Kiểm thử trên DBMS thật, không chỉ dựa vào H2

H2 hữu ích cho một số unit test hoặc kiểm tra nhanh, nhưng không phải bản thay thế đầy đủ cho PostgreSQL, MySQL, SQL Server hay Oracle. Ngay cả khi bật chế độ tương thích cú pháp, H2 không tái tạo toàn bộ hành vi của engine đích.

Các khác biệt thường gặp:

- Cách chuẩn hóa chữ hoa/thường và quote identifier.
- Kiểu dữ liệu, độ chính xác số, timestamp và timezone.
- Cách xử lý NULL, unique constraint và collation.
- Identity, sequence và auto-increment.
- Index biểu thức, partial index, included columns và index online.
- Transaction DDL, implicit commit và rollback.
- Lock, timeout và mức cô lập giao dịch.
- Catalog metadata, quyền truy cập system view và cách đặt schema.
- SQL function, JSON operator, generated column và stored procedure.

Vì vậy, nếu production hỗ trợ PostgreSQL và SQL Server, phải chạy migration integration test trên **cả PostgreSQL và SQL Server**. Test trên H2 có thể bổ sung tốc độ cho unit test, nhưng không được tính là bằng chứng DBMS-specific integration test đã đạt.

### Lựa chọn môi trường kiểm thử

Có thể sử dụng:

1. **Container database:** tạo instance tạm thời theo từng job, phù hợp CI và test lặp lại.
2. **Database test được quản lý:** dùng dịch vụ database riêng nếu engine không thuận tiện chạy container hoặc cần cấu hình tương đương production.
3. **Database dùng chung có schema cô lập:** chỉ khi đã có quy trình reset, namespace và phân quyền đủ an toàn; tránh các test chạy song song ghi đè nhau.
4. **Database bản sao/restore:** cần cho kiểm thử nâng cấp từ dữ liệu cũ có cấu trúc và kích thước gần thực tế.

Mỗi job nên có database hoặc schema cô lập và lịch sử DATABASECHANGELOG riêng. Không cho nhiều job DBMS hoặc nhiều nhánh test cùng update một database dùng chung mà không có cơ chế điều phối.

## 4. Kiểm thử theo hai hướng: dựng mới và nâng cấp

Một migration có thể chạy thành công trên database trống nhưng thất bại trên database đã có dữ liệu. Ngược lại, database legacy có thể được chỉnh thủ công để migration chạy được, trong khi một database mới không thể dựng lại đầy đủ từ changelog.

Do đó, mỗi thay đổi quan trọng cần được kiểm tra ít nhất theo hai hướng:

**Fresh install (dựng mới):**
- Database/schema trống.
- Chạy master changelog từ đầu.
- Xác minh mọi bảng, cột, khóa, index, view, sequence và dữ liệu tham chiếu cần thiết.
- Khởi động ứng dụng và chạy integration test.

**Upgrade path (nâng cấp):**
- Tạo database ở một release cũ hoặc restore fixture đại diện.
- Nạp dữ liệu gần với tình huống thật, bao gồm giá trị NULL, dữ liệu biên và các quan hệ.
- Chạy các migration từ release cũ tới release mới theo đúng thứ tự.
- Xác minh dữ liệu được giữ, chuyển đổi đúng và constraint mới có thể được áp dụng.
- Kiểm tra ứng dụng phiên bản mới hoạt động với schema sau migration.

Nếu sản phẩm hỗ trợ nâng cấp từ nhiều phiên bản cũ, xác định những đường nâng cấp được cam kết. Không chỉ thử upgrade từ release ngay trước đó nếu khách hàng có thể nhảy từ một release LTS cũ hơn.

### Ví dụ ma trận đường nâng cấp

| DBMS | Fresh install | Upgrade từ release trước | Upgrade từ LTS cũ | Rollback/forward fix |
|---|---:|---:|---:|---:|
| PostgreSQL | Có | Có | Theo support policy | Có |
| MySQL | Có | Có | Theo support policy | Có |
| SQL Server | Có | Có | Theo support policy | Có |

Các ô “Có” cần tương ứng với job/test có kết quả lưu được, không chỉ là mục tiêu trên tài liệu.

## 5. Phân biệt test cú pháp changelog với test hành vi DBMS

Các lớp kiểm thử bổ sung cho nhau:

| Lớp kiểm thử | Xác minh điều gì | Không chứng minh điều gì |
|---|---|---|
| Parse/validate | Changelog hợp lệ theo Liquibase và cấu hình | SQL runtime chắc chắn thành công |
| Generated SQL | Câu lệnh được sinh cho DBMS cụ thể | Dữ liệu thực tế đáp ứng constraint |
| Integration migration | Liquibase thực thi được trên engine thật | Hiệu năng production chắc chắn đạt |
| Schema assertion | Bảng/cột/constraint/index có đúng cấu trúc | Mọi ứng dụng phụ thuộc đều tương thích |
| Data assertion | Backfill/seed và quan hệ dữ liệu đúng | Không có lock/ảnh hưởng hiệu năng |
| Application integration | ORM, repository, transaction và API hoạt động | Tải lớn hoặc failover luôn an toàn |
| Upgrade/rollback | Đường chuyển phiên bản và phục hồi đã thử | Mọi sự cố production đều đảo ngược được |

Một pipeline tốt không gộp tất cả thành một bước “Liquibase update thành công”. Cần lưu kết quả theo DBMS, phiên bản, đường nâng cấp và nhóm kiểm tra để biết phạm vi nào đã đạt.

## 6. Change type portable và thay đổi đặc thù DBMS

Ưu tiên change type Liquibase có hỗ trợ trên các DBMS mục tiêu khi semantics phù hợp. Ví dụ createTable, addColumn, addForeignKeyConstraint, addUniqueConstraint và createIndex có thể giúp changelog diễn đạt ý định độc lập với cú pháp SQL cụ thể.

Tuy nhiên, mức hỗ trợ và cách sinh SQL phải được kiểm tra theo phiên bản Liquibase/DBMS. Một change type có thể:
- Không hỗ trợ một thuộc tính trên một DBMS.
- Sinh kiểu dữ liệu vật lý khác nhau.
- Có giới hạn về expression hoặc index options.
- Cần thêm precondition hoặc SQL riêng.
- Được triển khai bằng cú pháp không tương đương hoàn toàn.

Khi một thay đổi không thể diễn đạt portable, có thể dùng changeset đặc thù DBMS qua thuộc tính dbms hoặc precondition dbms.

Ví dụ hai nhánh có ID riêng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-010-add-special-index-postgresql"
      author: "team-db"
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX CONCURRENTLY ix_customer_email_lower
              ON app.customer (lower(email))
      rollback:
        - sql:
            sql: |
              DROP INDEX CONCURRENTLY IF EXISTS app.ix_customer_email_lower

  - changeSet:
      id: "20261120-011-add-special-index-mysql"
      author: "team-db"
      dbms: mysql
      changes:
        - sql:
            sql: |
              CREATE INDEX ix_customer_email
              ON app.customer (email)
      rollback:
        - dropIndex:
            schemaName: app
            tableName: customer
            indexName: ix_customer_email
~~~

Hai nhánh này **chỉ minh họa cách tách SQL theo DBMS**, không khẳng định index của PostgreSQL trên lower(email) và index email thông thường của MySQL có semantics tương đương. Nếu nghiệp vụ yêu cầu so sánh không phân biệt hoa/thường, cần thiết kế giải pháp MySQL tương ứng (chẳng hạn collation hoặc cột chuẩn hóa) và test để xác minh cùng hợp đồng. Không dùng ví dụ trên như một migration portable hoàn chỉnh.

Với SQL riêng:
- Ghi rõ dbms và phiên bản được áp dụng.
- Dùng ID changeset riêng, không tạo định danh mơ hồ.
- Có rollback phù hợp với cùng DBMS.
- Kiểm tra transaction/lock của câu SQL.
- Test trên engine thật.
- Xác minh nhánh DBMS khác tạo ra kết quả nghiệp vụ tương đương.

## 7. Dùng dbms, precondition, context và label đúng mục đích

Thuộc tính dbms của changeset giúp giới hạn changeset vào một hệ quản trị:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-020-postgresql-extension"
      author: "team-db"
      dbms: postgresql
      changes:
        - sql:
            sql: CREATE EXTENSION IF NOT EXISTS pgcrypto
~~~

Precondition dbms cũng có thể kiểm tra engine trong điều kiện phù hợp:

~~~yaml
preConditions:
  - onFail: HALT
  - dbms:
      type: postgresql
~~~

Không nên dùng precondition như cách “làm cho SQL không portable trở nên portable”. Nếu changeset chứa cú pháp PostgreSQL nhưng không giới hạn DBMS, Liquibase có thể đưa câu SQL đó đến engine khác và thất bại. Dùng dbms ở cấp changeset khi toàn bộ change chỉ dành cho engine đó.

Context và label giải quyết nhóm triển khai hoặc phạm vi phát hành, không thay thế việc nhận diện DBMS. Ví dụ:
- dbms: loại engine.
- context: mục đích/môi trường chạy như test hoặc demo.
- label: nhóm release hoặc tính năng.
- precondition: điều kiện trạng thái database cần đạt trước khi thực thi.

Các filter phải được cấu hình giống nhau giữa validate/status/update-sql/update. Một changeset bị loại khỏi lần chạy PostgreSQL không có nghĩa nó đã được xử lý; nó có thể tiếp tục pending trên một database khác hoặc khi filter thay đổi.

## 8. Những khác biệt DBMS phải đưa vào test matrix

### 8.1. Kiểu dữ liệu và chuyển đổi kiểu

Các kiểu logic như số nguyên lớn, chuỗi, số thập phân, boolean, ngày giờ, UUID và JSON có thể được ánh xạ sang kiểu vật lý khác nhau.

Ví dụ:
- Boolean có thể được biểu diễn bằng kiểu BOOLEAN, BIT hoặc kiểu số tùy DBMS.
- UUID có thể là kiểu native hoặc chuỗi/binary.
- Timestamp có/không timezone có semantics khác nhau.
- JSON có thể là JSON text, JSON binary hoặc kiểu dữ liệu khác.
- NUMBER/DECIMAL có precision và scale phải được xác định rõ.
- VARCHAR length có thể được hiểu theo ký tự hoặc byte tùy DBMS/cấu hình.

Test cần xác minh:
- Dữ liệu biên có lưu và đọc lại chính xác không.
- Giá trị timezone không bị dịch ngoài ý muốn.
- Precision/scale có làm tròn hoặc overflow không.
- Unicode và collation có xử lý đúng không.
- JDBC driver trả về kiểu Java như mong đợi không.
- modifyDataType có bảo toàn dữ liệu hiện hữu không.

Không chỉ so sánh tên kiểu vật lý; hãy xác minh semantics mà ứng dụng dựa vào.

### 8.2. Identity, sequence và auto-increment

DBMS khác nhau về:
- Identity column.
- Sequence độc lập.
- Auto-increment.
- Cách lấy generated key qua JDBC.
- Cách đồng bộ sequence sau khi backfill ID.
- Hành vi cache và giá trị tiếp theo sau rollback.

Test insert không chỉ kiểm tra row được tạo mà còn kiểm tra ID được sinh, tính duy nhất, cách ứng dụng lấy ID và khả năng tiếp tục insert sau khi import dữ liệu cũ.

Nếu migration nạp ID tường minh, cần kiểm tra sequence/identity có được đồng bộ để lần insert sau không va chạm. Cách điều chỉnh sequence là DBMS-specific và phải có test riêng.

### 8.3. Identifier, schema và catalog

Tên bảng/cột có thể khác cách chuẩn hóa chữ hoa/thường và cách quote. Một tên hoạt động trên PostgreSQL có thể được hiểu khác trên Oracle hoặc SQL Server.

Kiểm tra:
- Tên reserved keyword.
- Identifier có quote hay không.
- Độ dài tối đa.
- Case folding.
- Schema/catalog mặc định.
- Search path/default schema.
- Quyền tạo object trong schema.
- Cách Liquibase ghi FILENAME và nơi đặt DATABASECHANGELOG.

Không dùng tên bảng/cột mơ hồ hoặc từ khóa SQL chỉ vì một DBMS chấp nhận.

### 8.4. NULL, UNIQUE, CHECK và collation

Cùng một unique constraint có thể xử lý nhiều giá trị NULL khác nhau tùy DBMS. So sánh chuỗi cũng phụ thuộc collation, accent sensitivity và case sensitivity.

Test cần có:
- Hai giá trị NULL trong cột unique.
- Chuỗi chỉ khác hoa/thường.
- Chuỗi có/không dấu hoặc ký tự Unicode.
- Giá trị trùng theo quy tắc chuẩn hóa nghiệp vụ.
- CHECK constraint với giá trị biên và NULL.
- FK tham chiếu dữ liệu đã có.

Đừng giả định unique constraint trên email bảo đảm duy nhất theo quy tắc lowercase nếu DBMS/collation không áp dụng quy tắc đó.

### 8.5. Index và truy vấn

Index có thể khác về:
- Partial/filtered index.
- Functional/expression index.
- Included columns.
- Clustered/nonclustered.
- Online/concurrent creation.
- Predicate và sort direction.
- Compression, partitioning hoặc storage options.

Test schema cần xác minh định nghĩa index và tính hợp lệ; test truy vấn cần xem execution plan với dữ liệu đại diện. Một index tạo thành công không chứng minh nó cải thiện workload hoặc không chặn ghi quá lâu.

### 8.6. Transaction và DDL

Một số DDL có thể chạy trong transaction ở DBMS này nhưng gây implicit commit hoặc không rollback được ở DBMS khác. Tác động lock và thời gian thực thi cũng khác.

Kiểm tra:
- runInTransaction.
- DDL có commit ngầm không.
- Câu lệnh có được phép trong transaction không.
- Lock loại nào và kéo dài bao lâu.
- Timeout và retry.
- Nếu changeset thất bại giữa chừng, đối tượng nào còn tồn tại.
- DATABASECHANGELOG có ghi nhận changeset hay chưa.

Đừng suy ra tính nguyên tử chỉ từ việc Liquibase chia thao tác thành changeset. Transaction semantics thuộc DBMS và loại SQL thực thi.

## 9. Thiết kế test cho một changeset cụ thể

Ví dụ changeset thêm trạng thái cho đơn hàng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-030-add-order-status"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: purchase_order
        - not:
            - columnExists:
                schemaName: app
                tableName: purchase_order
                columnName: status_code
      changes:
        - addColumn:
            schemaName: app
            tableName: purchase_order
            columns:
              - column:
                  name: status_code
                  type: VARCHAR(24)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: purchase_order
            columnName: status_code
~~~

Một test tốt trên từng DBMS không dừng ở việc update trả exit code 0. Cần xác minh:

1. Bảng app.purchase_order tồn tại trước migration.
2. Cột status_code được tạo đúng kiểu/độ dài logic.
3. Nullability/default đúng yêu cầu.
4. Các hàng cũ được xử lý theo chính sách đã định.
5. Precondition dừng khi bảng thiếu hoặc cột đã tồn tại.
6. DATABASECHANGELOG ghi nhận đúng ID/AUTHOR/FILENAME.
7. Ứng dụng đọc/ghi status_code được.
8. Rollback trong database thử nghiệm cho kết quả dự kiến.
9. Update lần hai không chạy lại changeset thông thường.
10. Kết quả tương đương trên mỗi DBMS hỗ trợ.

Nếu DBMS có giới hạn khác nhau, cần ghi rõ ngoại lệ thay vì bỏ qua test. Ví dụ kiểu VARCHAR có giới hạn length khác hoặc index trên cột dài cần chiến lược riêng.

## 10. Test database mới và test nâng cấp với dữ liệu đại diện

### Fresh database

- Tạo database hoặc schema rỗng cho từng DBMS.
- Chạy master changelog từ đầu.
- Kiểm tra mọi object cần có.
- Kiểm tra dữ liệu tham chiếu/seed.
- Khởi tạo ứng dụng.
- Chạy test repository, transaction, API và query quan trọng.

### Upgrade database

- Tạo schema ở release cũ bằng changelog lịch sử.
- Nạp fixture có dữ liệu cũ và edge case.
- Chạy migration của release mới.
- Kiểm tra backfill, constraint, index và các quan hệ.
- Chạy ứng dụng mới và test chức năng.
- Xác minh dữ liệu lịch sử không mất hoặc đổi nghĩa.

Fixture cần bao gồm:
- Bảng rỗng và bảng có nhiều hàng.
- NULL, chuỗi dài tối đa, Unicode và ký tự đặc biệt.
- Số ở biên precision/scale.
- Khóa ngoại hợp lệ và mồ côi.
- Dữ liệu trùng có thể ảnh hưởng UNIQUE.
- Ngày giờ ở nhiều timezone.
- Giá trị JSON hoặc dữ liệu lớn nếu ứng dụng sử dụng.
- Reference code cũ/deprecated.

Không dùng cùng một fixture SQL trên mọi DBMS nếu nó chứa cú pháp hoặc kiểu dữ liệu riêng. Có thể tạo fixture logic chung và có bộ nạp dữ liệu theo engine, nhưng kết quả nghiệp vụ phải tương đương.

## 11. Kiểm tra SQL được sinh cho từng DBMS

Trước khi thực thi, chạy các bước Liquibase trên từng database:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Sau review mới thực hiện:

~~~bash
liquibase update
liquibase history
~~~

Các lệnh trên cần được cấu hình với đúng changelog, JDBC URL, driver, schema và parameters cho từng DBMS. Không dùng một output update-sql từ PostgreSQL để phê duyệt thay cho SQL của SQL Server hoặc Oracle.

Khi review generated SQL, chú ý:
- Cú pháp DDL thực tế.
- Tên constraint/index.
- Kiểu dữ liệu vật lý.
- Default expression.
- Identifier quoting.
- Schema/catalog.
- Transaction wrapper và delimiter.
- SQL đặc thù do extension hoặc custom change sinh ra.
- Khả năng lock và thao tác trên bảng lớn.

Generated SQL là bằng chứng tốt cho **câu lệnh dự kiến**, nhưng không chứng minh quyền, dữ liệu, lock hoặc điều kiện runtime chắc chắn đạt. Vẫn phải chạy trên engine thật.

## 12. Tổ chức changelog cho nhiều DBMS

Có ba cách tổ chức phổ biến.

### Cách A: một changelog portable

Dùng change type chung khi Liquibase hỗ trợ đầy đủ và semantics tương đương:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-040-create-audit-log"
      author: "team-db"
      changes:
        - createTable:
            schemaName: app
            tableName: audit_log
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: event_code
                  type: VARCHAR(50)
                  constraints:
                    nullable: false
~~~

Ưu điểm:
- Ít nhánh.
- Dễ đọc và review.
- Lịch sử logic thống nhất.
- Ít nguy cơ một DBMS bị bỏ quên trong một nhánh riêng.

Điều kiện:
- Các kiểu dữ liệu và change type phải được hỗ trợ.
- SQL sinh ra phải được kiểm tra trên mọi engine.
- Các khác biệt về semantics phải được xử lý hoặc ghi nhận.

### Cách B: tách changeset theo DBMS

Dùng khi một DBMS cần câu SQL hoặc tính năng riêng. Mỗi changeset đặc thù có dbms filter và ID riêng. Những changeset portable sau đó phải dựa vào một trạng thái logic chung đã được từng nhánh tạo ra.

Ưu điểm:
- Có thể tận dụng tính năng đặc thù.
- Không ép SQL riêng vào một change type không phù hợp.

Rủi ro:
- Nhánh có thể tạo cấu trúc không tương đương.
- Một DBMS có thể thiếu migration nếu filter sai.
- Rollback và history phức tạp hơn.
- Cần test từng nhánh và kiểm tra kết quả chung.

### Cách C: changelog gốc include các nhánh theo nền tảng

Changelog gốc có thể include các tệp chung và tệp DBMS-specific. Cần kiểm tra đường dẫn, thứ tự include, định danh và các filter. Không tạo hai changeset có cùng ID/AUTHOR/FILENAME logic nhưng thay đổi nội dung tùy engine mà không có thiết kế rõ ràng.

Không chọn cách tổ chức chỉ theo sở thích thư mục. Hãy chọn dựa trên số lượng khác biệt vật lý, khả năng tái sử dụng và mức độ dễ review.

## 13. Kiểm tra nhánh DBMS không bị chạy nhầm

Ví dụ một changeset chỉ dành cho PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-050-postgresql-specific-change"
      author: "team-db"
      dbms: postgresql
      changes:
        - sql:
            sql: SELECT 1
~~~

Trong test matrix:
- PostgreSQL phải xác nhận changeset được chọn và xử lý theo thiết kế.
- MySQL, SQL Server và Oracle phải xác nhận changeset PostgreSQL không được thực thi.
- Những thay đổi portable tiếp theo phải hoạt động trên tất cả DBMS.
- DATABASECHANGELOG trên từng engine cần được đọc để hiểu changeset nào được ghi nhận, bị lọc hoặc còn pending.

Không kiểm tra chỉ bằng việc câu SQL không lỗi. Một nhánh DBMS bị bỏ qua có thể khiến database thiếu object mà các changeset sau vẫn cố tham chiếu.

Nếu một change logic có các implementation khác nhau, hãy xác định **điểm hội tụ**: sau tất cả nhánh DBMS, mỗi database phải có cùng hợp đồng object/data mà ứng dụng cần. Viết assertion chung để kiểm tra điểm hội tụ đó.

## 14. Test precondition và lỗi môi trường

Precondition có thể trả kết quả khác nhau giữa DBMS do schema, metadata, quyền hoặc dữ liệu khác nhau.

Ví dụ:

~~~yaml
preConditions:
  - onFail: HALT
  - and:
      - dbms:
          type: postgresql
      - tableExists:
          schemaName: app
          tableName: customer
~~~

Ví dụ này yêu cầu DBMS là PostgreSQL và bảng customer tồn tại. Nếu changeset dùng cho nhiều engine, không nên đặt dbms: postgresql trong precondition chung mà không có nhánh riêng.

Test nên bao gồm:
- Đối tượng tồn tại đúng schema.
- Đối tượng thiếu.
- Đối tượng cùng tên nhưng ở schema khác.
- Tài khoản thiếu quyền metadata.
- Tên có quote/case khác nhau.
- DBMS không hỗ trợ precondition hoặc truy vấn SQL riêng.
- onFail và onError hoạt động đúng chính sách.

Phân biệt **Fail** (điều kiện được đánh giá nhưng không đạt) với **Error** (lỗi trong khi đánh giá). Một pipeline chỉ thử trường hợp precondition đạt sẽ bỏ sót hành vi quan trọng khi triển khai database không đồng nhất.

Không dùng MARK_RAN để làm cho mọi DBMS có kết quả xanh. Nếu precondition fail do thiếu object hoặc sai schema, cần hiểu nguyên nhân và xử lý migration tương ứng.

## 15. Test rollback theo khả năng thực tế của từng DBMS

Rollback cần được kiểm tra riêng vì cùng một change type có thể có mức hỗ trợ khác nhau:

- Có change type tự sinh rollback.
- Có thay đổi cần rollback khai báo tường minh.
- Có thao tác không thể khôi phục dữ liệu đã xóa.
- DDL có thể không rollback được nguyên tử.
- Một số lệnh index online/concurrent có giới hạn transaction.
- Constraint có thể không drop được khi còn dependency.

Một bài test rollback:

1. Tạo database thử nghiệm và chạy changelog tới mốc cần kiểm tra.
2. Nạp dữ liệu đại diện.
3. Lưu số hàng và các giá trị quan trọng.
4. Xem rollback SQL được sinh ra nếu phiên bản hỗ trợ.
5. Chạy rollback trong môi trường thử nghiệm.
6. Kiểm tra schema và dữ liệu sau rollback.
7. Xác định thay đổi nào không thể khôi phục tự động.
8. Dựng lại database và kiểm tra update từ đầu sau đó.

Không mặc định rollback một changeset nghĩa là rollback toàn bộ lần update. Khi một release có nhiều changeset, phải xác định điểm rollback, thứ tự phụ thuộc và tác động lên ứng dụng.

### Kiểm tra rollback không phá dữ liệu

Ví dụ addColumn có rollback dropColumn. Nếu ứng dụng đã ghi dữ liệu vào cột mới, dropColumn sẽ xóa dữ liệu. Test rollback phải chứng minh hành vi này đã được chấp nhận hoặc chọn chiến lược forward fix/backup phù hợp.

Với các migration dữ liệu, kiểm tra số hàng, mapping và audit trước/sau. Nếu phép chuyển đổi không đảo ngược (ví dụ gộp hai trạng thái thành một), không hứa rollback hoàn toàn nếu không lưu dữ liệu nguồn.

## 16. Test checksum và DATABASECHANGELOG trên từng engine

Mỗi database có bảng DATABASECHANGELOG riêng. Cùng một changelog được triển khai trên các DBMS có thể ghi lịch sử tương ứng, nhưng thời điểm và tập changeset có thể khác do filter hoặc release path.

Cần xác minh:
- ID, AUTHOR, FILENAME của changeset.
- EXECTYPE và thứ tự ghi nhận.
- MD5SUM phù hợp với artifact/phiên bản Liquibase.
- Không có changeset cũ bị xem thành mới do đổi đường dẫn.
- Changeset DBMS-specific được chọn đúng engine.
- Changeset đã chạy không bị sửa nội dung giữa các môi trường.
- Không có thao tác baseline/sync nhầm changeset pending.

Truy vấn minh họa:

~~~sql
SELECT ID, AUTHOR, FILENAME, EXECTYPE, DATEEXECUTED, MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
~~~

Tên schema của DATABASECHANGELOG phụ thuộc cấu hình. Nếu mỗi DBMS lưu bảng lịch sử trong schema khác nhau, test harness phải truy vấn đúng vị trí.

Không yêu cầu MD5SUM phải giống tuyệt đối giữa mọi phiên bản Liquibase nếu thuật toán/format checksum thay đổi theo version. Điều cần kiểm tra là **cùng artifact và cùng phiên bản công cụ tạo lịch sử nhất quán trong phạm vi được hỗ trợ**, đồng thời mọi khác biệt version phải được giải thích.

## 17. Test lock, transaction và chạy đồng thời

Liquibase dùng DATABASECHANGELOGLOCK để điều phối các tiến trình Liquibase trên cùng database. Trong CI matrix, mỗi job nên có database riêng. Nếu cố tình kiểm tra lock, hãy tạo test chuyên biệt:

1. Khởi động tiến trình Liquibase A trên database thử nghiệm.
2. Trong khi A giữ lock, thử khởi động tiến trình B.
3. Xác nhận B chờ hoặc thất bại theo cấu hình timeout.
4. Đợi A hoàn tất và xác nhận B có thể tiếp tục theo quy tắc.
5. Kiểm tra DATABASECHANGELOG không ghi trùng changeset.
6. Mô phỏng lỗi tiến trình trong môi trường thử nghiệm và điều tra lock state.

Không chạy test này trên database production. Không force release lock khi chưa xác minh tiến trình đang giữ lock đã dừng.

Transaction DDL cần test theo engine:
- Một changeset gồm nhiều change có rollback nguyên tử không?
- Nếu change thứ hai thất bại, change thứ nhất còn tồn tại không?
- DATABASECHANGELOG có ghi nhận changeset không?
- Cần runInTransaction=false hay không?
- SQL có implicit commit không?
- Lock có được giải phóng đúng không?

Kết quả có thể khác giữa DBMS và phải được ghi trong ma trận.

## 18. Kiểm thử dữ liệu và quy tắc tương đương

Schema giống nhau không đủ; cùng migration phải bảo toàn ý nghĩa dữ liệu.

Ví dụ chuyển cột amount từ INTEGER sang DECIMAL:
- PostgreSQL có thể xử lý conversion theo một cách.
- MySQL có thể có quy tắc làm tròn hoặc cast khác.
- SQL Server/Oracle có precision/scale và lỗi overflow riêng.

Test cần kiểm tra:
- Giá trị nhỏ nhất/lớn nhất.
- Số thập phân vượt scale.
- NULL và default.
- Dữ liệu có format không hợp lệ.
- Unicode, timezone, collation.
- Tính duy nhất và quan hệ FK.
- Số hàng bị cập nhật/bỏ qua.
- Kết quả sau rollback hoặc forward fix.

Đối với backfill, không chỉ kiểm tra query thành công. Phải kiểm tra:
- Số hàng dự kiến được chuyển.
- Không có row bị bỏ sót.
- Không có dữ liệu mới bị ghi đè.
- Job có thể tiếp tục sau gián đoạn nếu thiết kế yêu cầu.
- Các transaction và batch size không gây lock vượt ngưỡng.

Nếu mỗi DBMS có cách biểu diễn vật lý khác nhau, hãy so sánh kết quả theo **quy tắc nghiệp vụ chuẩn hóa**, không so sánh raw metadata một cách máy móc.

## 19. Kiểm thử hiệu năng và khả năng vận hành

Migration thành công về chức năng vẫn có thể không phù hợp production nếu mất quá nhiều thời gian hoặc gây lock.

Đối với bảng lớn, cần kiểm thử:
- Thời gian tạo index.
- Thời gian ALTER COLUMN.
- Lock mode và thời gian chờ.
- Dung lượng temporary/log/WAL.
- Replication lag.
- Tác động lên truy vấn đọc/ghi.
- Timeout và khả năng dừng an toàn.
- Hành vi trên dữ liệu gần kích thước production.

Không lấy thời gian chạy trên database rỗng làm dự báo cho bảng hàng trăm triệu dòng. Tạo dataset có phân bố gần thực tế hoặc dùng bản sao đã được phép.

Một số DBMS hỗ trợ online/concurrent DDL với cú pháp và giới hạn riêng. Cần kiểm thử riêng câu SQL đó, transaction behavior, trạng thái index nếu tiến trình bị ngắt và cách rollback. Không suy luận “online” nghĩa là không có lock hoặc không có ảnh hưởng hiệu năng.

## 20. Test ứng dụng Spring Boot sau migration

Khi migration được thực thi từ Spring Boot, test cần xác minh cả Liquibase lẫn ứng dụng:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Test theo từng DBMS:
1. Khởi động database đúng engine/version.
2. Khởi động ứng dụng với JDBC driver tương ứng.
3. Liquibase chạy update hoặc job migration đã được thiết kế.
4. Hibernate validate mapping.
5. Test repository/JPA/native SQL.
6. Test transaction và generated key.
7. Test API đọc/ghi dữ liệu sau migration.
8. Kiểm tra log, exception và thời gian khởi động.
9. Kiểm tra app version cũ/mới nếu migration cần rolling deployment.

Hibernate validate chỉ kiểm tra một phần mapping; nó không chứng minh view, trigger, index, stored procedure hoặc dữ liệu tham chiếu đều đúng. Integration test cần bao phủ các thành phần ứng dụng thật sự sử dụng.

Nếu hệ thống có nhiều instance, không để mọi instance cùng tự ý thực hiện migration nguy cơ cao mà thiếu kế hoạch rollout. DATABASECHANGELOGLOCK điều phối Liquibase, nhưng không thay thế khả năng tương thích giữa các phiên bản ứng dụng đang chạy.

## 21. Tổ chức CI matrix cho nhiều DBMS

Một pipeline có thể định nghĩa ma trận:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    database:
      - postgres
      - mysql
      - sqlserver
      - oracle
~~~

Đây là cấu trúc minh họa cho CI; cú pháp thực tế phụ thuộc nền tảng pipeline và cách cung cấp database service. Ma trận thực tế nên chứa **cả phiên bản DBMS**, không chỉ tên engine.

Mỗi job:
- Khởi động DBMS/phiên bản được chỉ định.
- Chờ database sẵn sàng và kiểm tra kết nối.
- Cấp JDBC driver và Liquibase version đã pin.
- Cấp changelog, contexts, labels và parameters giống release.
- Chạy validate, status, update-sql.
- Chạy migration integration test.
- Kiểm tra schema, dữ liệu và DATABASECHANGELOG.
- Chạy test ứng dụng.
- Lưu log/SQL/output để truy vết.
- Hủy database test sau khi hoàn tất.

Nếu một DBMS job fail, pipeline tổng phải fail hoặc đánh dấu rõ platform không đạt. Không chỉ xem kết quả PostgreSQL là đại diện cho cả matrix.

### PR và lịch chạy

- Pull request thay đổi changelog: chạy test trên tất cả DBMS nằm trong support matrix nếu thay đổi ảnh hưởng migration.
- Nightly: có thể chạy thêm phiên bản DBMS cũ/mới, upgrade path dài và test hiệu năng.
- Release candidate: chạy đầy đủ ma trận hỗ trợ, bao gồm upgrade từ phiên bản được cam kết.
- Nâng cấp Liquibase/driver: chạy lại ma trận tương ứng để phát hiện khác biệt SQL/checksum.

Không bỏ qua một job fail chỉ vì engine đó ít được dùng. Nếu muốn giảm ma trận, phải thay đổi chính sách hỗ trợ một cách chính thức.

## 22. Ví dụ pipeline test theo từng DBMS

Pseudocode sau mô tả logic một job, không gắn với một nhà cung cấp CI cụ thể:

~~~bash
set -e

# DB_URL, DB_USERNAME, DB_PASSWORD và driver đã được cấp an toàn.
liquibase validate
liquibase status --verbose
liquibase update-sql

# Chỉ chạy trên database test cô lập.
liquibase update

# Sau migration, chạy test ứng dụng và assertion schema/data.
./run-migration-integration-tests

liquibase history
~~~

Trong mỗi job, DB_URL phải trỏ tới engine/version tương ứng. Không dùng chung database target giữa các job trong matrix.

Cần lưu:
- DBMS và server version.
- JDBC driver version.
- Liquibase version/extension.
- Commit hoặc artifact changelog.
- Context/label và parameters.
- Generated SQL.
- Kết quả update.
- Kết quả schema/data assertion.
- Log integration test.

Không lưu password, token hoặc JDBC URL có chứa credentials trong artifact/log.

## 23. Kiểm tra thứ tự release và tương thích ứng dụng

Cùng migration có thể chạy trên nhiều DBMS nhưng ứng dụng vẫn có thể lỗi do rollout.

Ví dụ migration thêm cột NOT NULL:
- DBMS A có thể cho phép thêm cột với default theo cách ít tốn chi phí.
- DBMS B có thể rewrite bảng hoặc lock lâu.
- Ứng dụng cũ không biết cột mới.
- Ứng dụng mới yêu cầu cột mới nhưng migration chưa chạy.

Với thay đổi phá tương thích, dùng expand–migrate–contract:
1. Thêm cấu trúc mới theo cách tương thích ngược.
2. Triển khai ứng dụng đọc/ghi được cả trạng thái cũ và mới.
3. Backfill dữ liệu.
4. Chuyển traffic/reader/writer.
5. Kiểm chứng không còn phụ thuộc cũ.
6. Xóa cấu trúc cũ bằng migration riêng.

Test matrix cần chạy các giai đoạn này trên mỗi DBMS hỗ trợ. Nếu một engine có lock hoặc transaction behavior khác, thứ tự deploy và thời gian bảo trì có thể phải điều chỉnh theo engine.

## 24. Quản lý phiên bản Liquibase và driver

Kết quả migration phụ thuộc không chỉ DBMS mà còn Liquibase, extension và JDBC driver.

Một thay đổi nâng cấp công cụ có thể ảnh hưởng:
- Cách sinh SQL cho một change type.
- Mapping kiểu dữ liệu.
- Parser SQL, delimiter hoặc splitStatements.
- Metadata snapshot/diff.
- Checksum version hoặc validation.
- Cách driver xử lý generated keys, timestamp và metadata.
- Transaction/DDL behavior được quan sát.

Vì vậy, ma trận kiểm thử nên khóa phiên bản công cụ. Khi nâng Liquibase hoặc JDBC driver:
1. Ghi nhận phiên bản cũ/mới.
2. Chạy lại changelog đã triển khai trên database có history.
3. Kiểm tra validate và checksum.
4. So sánh update-sql.
5. Chạy fresh install và upgrade path.
6. Chạy integration test ứng dụng.
7. Chỉ nâng production sau khi giải thích mọi khác biệt.

Không đổi đồng thời DBMS, driver, Liquibase và changelog trong một lần nếu không có lý do; thay đổi nhiều biến khiến khó xác định nguồn lỗi.

## 25. Chẩn đoán lỗi theo DBMS

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| PostgreSQL chạy, MySQL lỗi syntax | SQL đặc thù hoặc change type không hỗ trợ cùng thuộc tính | Đọc update-sql MySQL, tách nhánh dbms khi cần |
| SQL Server không thấy bảng | Schema mặc định hoặc tên owner khác | Xác minh schema/catalog, quyền và identifier |
| Oracle lỗi độ dài tên | Identifier vượt giới hạn theo phiên bản | Rút gọn tên ổn định và kiểm tra namespace |
| Một engine tạo cột boolean khác | Mapping kiểu vật lý khác | Kiểm tra semantics/JDBC mapping thay vì chỉ tên kiểu |
| UNIQUE chấp nhận nhiều NULL ở engine này nhưng không ở engine khác | Quy tắc NULL/unique khác nhau | Định nghĩa rõ nghiệp vụ và bổ sung chiến lược tương thích |
| Timestamp lệch giờ | Timezone, kiểu cột hoặc driver khác nhau | Kiểm tra UTC, session timezone và kiểu có/không timezone |
| Rollback DDL thất bại | DDL transaction behavior khác | Xác định thay đổi đã áp dụng, dùng recovery/forward fix |
| Index tạo rất lâu trên một engine | DDL lock, table size hoặc phương pháp tạo index | Đo trên dữ liệu đại diện và cân nhắc online/concurrent |
| Test pass trên H2 nhưng fail production | H2 không mô phỏng đủ semantics DBMS thật | Chạy integration test trên engine mục tiêu |
| Changelog DBMS-specific bị chạy sai | dbms filter/precondition hoặc cấu hình connection sai | Kiểm tra DBMS nhận diện, generated SQL và history |
| Metadata không đọc được | Tài khoản thiếu quyền catalog/system view | Cấp quyền tối thiểu phù hợp hoặc dùng kiểm tra chuyên biệt |
| Changeset pending ở một engine | Nhánh DBMS bị filter, history khác hoặc release path khác | Đọc DATABASECHANGELOG và bộ lọc trên chính engine đó |
| Một engine fail giữa changeset | Transaction/DDL không nguyên tử | Kiểm tra schema vật lý và history trước retry |
| Checksum khác sau nâng cấp tool | Version/normalization hoặc source changeset khác | So sánh phiên bản, artifact và history; không sửa checksum thủ công |

Khi lỗi, phân loại trước:
- Lỗi **changelog/định danh**.
- Lỗi **SQL/DBMS capability**.
- Lỗi **kiểu dữ liệu/semantics**.
- Lỗi **quyền và metadata**.
- Lỗi **transaction/lock**.
- Lỗi **dữ liệu và constraint**.
- Lỗi **mapping/ứng dụng**.

Không giải quyết lỗi DBMS bằng cách bỏ test của engine đó nếu engine vẫn nằm trong support policy.

## 26. Bài thực hành: kiểm thử cùng changelog trên hai DBMS

**Bối cảnh:** một ứng dụng Spring Boot hỗ trợ hai DBMS được nhóm xác định trong support matrix. Changelog tạo bảng customer, thêm email, tạo unique constraint và index phục vụ truy vấn.

### Phần A — Chuẩn bị

1. Chọn phiên bản server và JDBC driver được hỗ trợ của từng DBMS.
2. Tạo hai database test cô lập.
3. Cấu hình cùng changelog master và cùng commit.
4. Xác nhận schemaName, context/label và parameters.
5. Chuẩn bị fixture có email trùng, NULL, Unicode và chuỗi dài.

### Phần B — Fresh install

1. Chạy validate trên DBMS A và B.
2. Chạy status --verbose và update-sql trên từng engine.
3. Review SQL sinh ra riêng cho A và B.
4. Chạy update.
5. Kiểm tra bảng, cột, PK, UNIQUE và index.
6. Chạy truy vấn đọc/ghi qua JDBC và ORM.
7. Kiểm tra DATABASECHANGELOG của từng database.

### Phần C — Upgrade path

1. Dựng schema từ release cũ trên cả hai engine.
2. Nạp fixture giống nhau về mặt nghiệp vụ.
3. Chạy migration mới.
4. Kiểm tra backfill, constraint và dữ liệu biên.
5. Chạy ứng dụng mới với Hibernate validate.
6. Kiểm tra truy vấn, transaction và generated key.
7. So sánh kết quả theo hợp đồng logic.

### Phần D — Rollback và lỗi

1. Trên database có thể khôi phục, thử rollback changeset tạo index/constraint.
2. Xác minh object và dữ liệu sau rollback.
3. Mô phỏng một precondition fail.
4. Mô phỏng lỗi DDL ở giữa một changeset trên môi trường thử nghiệm.
5. Đọc DATABASECHANGELOG và schema thực tế trước khi quyết định retry.
6. Ghi nhận khác biệt transaction/lock giữa hai DBMS.

### Câu hỏi tự kiểm tra

- Nếu validate thành công trên PostgreSQL, có thể kết luận changelog chạy trên SQL Server không? **Không.**
- Nếu generated SQL khác nhau, có phải migration sai không? **Không nhất thiết.** Cần so sánh semantics và kết quả.
- H2 chạy thành công có thay integration test trên DBMS thật không? **Không.**
- Khi một DBMS cần SQL riêng, nên dùng cách nào? **Tách changeset theo dbms, có ID và rollback riêng, rồi kiểm tra điểm hội tụ logic.**
- Vì sao phải test upgrade từ dữ liệu cũ? **Vì constraint, conversion và backfill có thể thất bại khi dữ liệu thật tồn tại.**
- DATABASECHANGELOG giống nhau có chứng minh schema giống nhau không? **Không.** Phải kiểm tra metadata và dữ liệu thực tế.
- Nếu rollback DDL được trên một engine, có thể giả định engine khác cũng rollback được không? **Không.** Transaction DDL khác nhau.
- Test matrix có thể bỏ qua một DBMS ít dùng không? **Chỉ khi chính sách hỗ trợ đã thay đổi chính thức.**

## 27. Checklist review migration đa DBMS

**Phạm vi hỗ trợ**
- [ ] Đã liệt kê DBMS, phiên bản server, edition và driver được hỗ trợ.
- [ ] Đã pin phiên bản Liquibase/extension và Java runtime.
- [ ] Đã xác định schema/catalog, charset, collation và timezone.
- [ ] Không coi H2 hoặc chế độ tương thích là thay thế DBMS thật.

**Thiết kế changelog**
- [ ] Ưu tiên change type portable khi semantics tương đương.
- [ ] SQL đặc thù có dbms filter, ID riêng và rollback riêng.
- [ ] Các nhánh DBMS hội tụ về cùng hợp đồng schema/data.
- [ ] Precondition, context, label và parameters có mục đích rõ ràng.
- [ ] ID/AUTHOR/FILENAME và checksum ổn định qua các môi trường.
- [ ] Không sửa changeset đã chạy để né khác biệt DBMS.

**Kiểm thử**
- [ ] Có fresh install test trên từng DBMS/version hỗ trợ.
- [ ] Có upgrade test từ release cũ được cam kết.
- [ ] Đã review update-sql riêng cho từng engine.
- [ ] Có schema assertion và data assertion.
- [ ] Đã test kiểu dữ liệu, NULL, UNIQUE, collation, identity/sequence.
- [ ] Đã test identifier, schema/catalog và quyền metadata.
- [ ] Đã test transaction DDL, lock, timeout và failure recovery.
- [ ] Đã test rollback/forward fix theo từng DBMS.
- [ ] Có integration test Spring Boot/JDBC/ORM trên engine thật.
- [ ] Dữ liệu fixture có giá trị biên và kích thước phù hợp.

**CI/CD và vận hành**
- [ ] Matrix job cô lập database và DATABASECHANGELOG.
- [ ] Cùng artifact/changelog được dùng cho mọi job.
- [ ] Mỗi job lưu DBMS/version, driver, Liquibase và generated SQL.
- [ ] Một engine fail làm pipeline báo rõ platform chưa đạt.
- [ ] Production dùng cùng quy trình review và cổng phê duyệt.
- [ ] Có kế hoạch tương thích ứng dụng và expand–migrate–contract khi cần.
- [ ] Không retry hoặc release lock khi chưa xác định trạng thái migration.
- [ ] Sau update đã kiểm tra schema, dữ liệu, history và smoke test.

**Kết luận:** kiểm thử migration đa DBMS phải xác nhận **cùng ý định, cùng hợp đồng dữ liệu và hành vi ứng dụng** trên từng engine/phiên bản được hỗ trợ. Liquibase giúp diễn đạt changeset và sinh SQL phù hợp, nhưng không loại bỏ khác biệt về kiểu dữ liệu, transaction DDL, lock, index, identifier và metadata. Kết hợp ma trận DBMS thật, fresh install, upgrade path, generated SQL review, schema/data assertion, rollback test và CI/CD matrix sẽ giúp phát hiện sai lệch trước khi migration đến production.
