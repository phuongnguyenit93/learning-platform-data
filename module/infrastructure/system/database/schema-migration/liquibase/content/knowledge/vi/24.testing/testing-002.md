# Khởi tạo cơ sở dữ liệu mới từ toàn bộ changelog

Trong chương **Kiểm thử** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, khởi tạo một cơ sở dữ liệu mới từ toàn bộ changelog là phép kiểm chứng quan trọng nhất cho khả năng tái lập của hệ thống. Một database trống không có bảng nghiệp vụ, không có lịch sử Liquibase và chưa có dữ liệu tham chiếu phải có thể được đưa tới trạng thái schema và dữ liệu mong đợi chỉ bằng artifact changelog đã phát hành.

Phạm vi của dịch vụ **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Người học thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Vì vậy, bài học không dừng ở việc chạy một lệnh update; nó xây dựng quy trình từ chuẩn bị database, xác minh changelog, triển khai toàn bộ changeset, kiểm tra schema/dữ liệu, chạy lại để xác nhận tính ổn định, đến kiểm thử ứng dụng và ghi nhận kết quả.

Định hướng đầy đủ của dịch vụ: Nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

**Fresh install** khác với nâng cấp một database cũ. Với fresh install, không có lịch sử trước đó để Liquibase đối chiếu và không được giả định bảng hoặc dữ liệu đã tồn tại. Đây là cách kiểm tra xem changelog có mô tả đầy đủ các bước cần thiết để tạo một hệ thống mới hay không.

## 1. Fresh install là gì và vì sao cần kiểm thử?

Fresh install là quá trình đưa một database hoặc schema mới, chưa có cấu trúc nghiệp vụ và chưa có lịch sử migration của ứng dụng, đến trạng thái mà một phiên bản ứng dụng có thể sử dụng.

Một lần fresh install đạt yêu cầu cần chứng minh:

- Changelog gốc được tìm thấy và toàn bộ changelog con được nạp đúng.
- Tất cả changeset cần thiết được thực thi theo đúng thứ tự.
- Bảng, cột, khóa, constraint, index, sequence, view và các object trong phạm vi được tạo đúng.
- Dữ liệu tham chiếu hoặc dữ liệu khởi tạo bắt buộc được nạp đúng.
- Các precondition phản ánh đúng giả định của database mới.
- DATABASECHANGELOG ghi nhận đúng lịch sử và checksum.
- DATABASECHANGELOGLOCK không bị giữ bất thường sau khi hoàn tất.
- Ứng dụng có thể kết nối, validate mapping và chạy các chức năng cơ bản.
- Chạy update lần nữa không tạo trùng object hoặc nhân đôi dữ liệu.
- Có bằng chứng kiểm thử để lặp lại trên môi trường khác.

Fresh install không chứng minh đường nâng cấp từ mọi phiên bản cũ đều đúng. Nó cũng không chứng minh migration có hiệu năng phù hợp với dữ liệu production. Hai nhóm kiểm thử này phải được thực hiện riêng.

## 2. Phân biệt tạo database với tạo schema ứng dụng

Liquibase thường kết nối vào một database đã tồn tại để quản lý các thay đổi bên trong database đó. Việc tạo database vật lý, cấp quyền ở cấp server hoặc cấu hình instance thường thuộc bước provisioning của nền tảng, DBA, Terraform, Kubernetes operator hoặc công cụ hạ tầng.

Cần phân biệt các lớp:

| Lớp | Ví dụ | Ai hoặc công cụ nào thường quản lý |
|---|---|---|
| Database/server | Tạo database, instance, endpoint, backup policy | Hạ tầng/DBA/platform |
| User và quyền | Tạo migration user, runtime user, grant | DBA/secret & access management |
| Schema namespace | Schema app, schema lưu metadata Liquibase | DBA hoặc Liquibase tùy chính sách |
| Schema ứng dụng | Bảng, cột, khóa, index, view | Liquibase changelog |
| Dữ liệu khởi tạo | Reference data, seed được kiểm soát | Liquibase hoặc quy trình dữ liệu riêng |
| Cấu hình runtime | URL, password, pool, timeout | Spring Boot externalized configuration |

Một database mới có thể đã tồn tại nhưng chưa có schema app. Hoặc database và schema đã được provisioning nhưng chưa có bảng nghiệp vụ. Xác định rõ điểm bắt đầu để precondition và changelog phản ánh đúng trạng thái.

Không mặc định rằng Liquibase có quyền tạo database. Một số DBMS yêu cầu kết nối vào database quản trị để tạo database khác; quy trình đó thường cần quyền cao và nên được tách khỏi migration schema nghiệp vụ.

## 3. Điều kiện đầu vào cho một database sạch

Trước khi chạy migration, xác minh database đích thực sự là database mới dành cho bài kiểm thử.

Checklist đầu vào:

- DBMS và phiên bản nằm trong support matrix.
- Database/catalog đích đã được tạo và có thể kết nối.
- Tài khoản migration có quyền cần thiết để tạo object và bảng lịch sử.
- Tài khoản runtime có quyền tối thiểu cần thiết cho ứng dụng.
- Schema mặc định hoặc schema đích đã được xác định.
- Không có bảng nghiệp vụ cũ bị bỏ sót.
- Không có DATABASECHANGELOG cũ từ một ứng dụng khác hoặc lần thử trước.
- Không có DATABASECHANGELOGLOCK ở trạng thái bất thường.
- Encoding, collation, timezone và cấu hình DBMS phù hợp với môi trường dự kiến.
- Changelog artifact, Liquibase version, JDBC driver và extension được pin.
- Context, label và changelog parameters được xác định rõ.

Không chỉ dựa vào tên database có chữ test hoặc new để kết luận nó sạch. Hãy truy vấn metadata hoặc tạo database dùng một lần để biết chắc trạng thái ban đầu.

Nếu database đã có dữ liệu hoặc lịch sử, đó là bài kiểm thử nâng cấp/tiếp nhận legacy, không còn là fresh install thuần túy.

## 4. Xác định điểm vào changelog gốc

Một dự án nên có một master changelog làm entry point cho toàn bộ schema và dữ liệu do module quản lý. Ví dụ cấu trúc:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      baseline/
        001-create-reference-tables.yaml
        002-create-core-tables.yaml
      changes/
        20261119-add-customer-status.yaml
        20261120-add-payment-index.yaml
      data/
        payment-status-v1.csv
~~~

Master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: baseline/001-create-reference-tables.yaml
      relativeToChangelogFile: true
  - include:
      file: baseline/002-create-core-tables.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/20261119-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/20261120-add-payment-index.yaml
      relativeToChangelogFile: true
~~~

Đường dẫn là ví dụ; phải phù hợp với vị trí thực tế của master changelog và cách đóng gói resource. Với relativeToChangelogFile: true, đường dẫn include được giải quyết tương đối theo changelog chứa khai báo include. Nếu không dùng thuộc tính này, cách phân giải phụ thuộc cấu hình và vị trí changelog.

Những điều cần kiểm tra:

1. Master changelog được chỉ định đúng trong CLI hoặc Spring Boot.
2. Mọi tệp include đều tồn tại trong artifact đã build.
3. Không include nhầm tệp test/demo vào release production.
4. Không include lặp một changelog theo hai đường dẫn logic khác nhau.
5. Thứ tự include phản ánh phụ thuộc thực tế.
6. Đường dẫn và định danh của changeset đã phát hành được giữ ổn định.
7. Các thư mục chứa dữ liệu ngoài như CSV cũng được đóng gói đúng.

Một tệp changelog nằm trong source tree nhưng không được include sẽ không tự chạy. Fresh install là cách tốt để phát hiện những thay đổi đã được thử thủ công nhưng bị quên đưa vào master.

## 5. Thứ tự changeset và phụ thuộc giữa các object

Liquibase thực thi changeset theo thứ tự changelog được nạp, bao gồm thứ tự include. ID có dạng ngày tháng không tự làm changeset chạy theo thứ tự số hoặc thời gian.

Ví dụ phụ thuộc:

~~~text
Schema app
   |
   v
Bảng reference
   |
   v
Bảng customer / payment
   |
   v
Foreign key và unique constraint
   |
   v
Index phục vụ truy vấn
   |
   v
Dữ liệu tham chiếu và dữ liệu khởi tạo
   |
   v
View / routine phụ thuộc bảng
~~~

Đây là sơ đồ minh họa; thứ tự thực tế phụ thuộc object và DBMS. Chẳng hạn dữ liệu tham chiếu có thể cần trước khi tạo FK hoặc trước khi chạy backfill. View có thể cần tạo sau bảng/cột mà nó sử dụng.

Quy tắc thiết kế:

- Tạo schema/namespace trước khi tạo bảng trong schema đó.
- Tạo bảng cha trước bảng con nếu FK phụ thuộc.
- Tạo cột trước index hoặc constraint sử dụng cột.
- Seed reference data trước khi ứng dụng hoặc migration dữ liệu tham chiếu tới nó.
- Thực hiện backfill trước khi siết NOT NULL/UNIQUE/FK nếu dữ liệu cũ cần được chuyển đổi.
- Tạo view/routine sau các object mà chúng phụ thuộc.
- Tách thao tác lớn hoặc đặc thù transaction thành changeset phù hợp.

Không gom tất cả DDL/DML vào một changeset lớn chỉ để giảm số dòng lịch sử. Changeset nhỏ, có ý nghĩa rõ ràng giúp review, chẩn đoán lỗi và rollback theo mốc dễ hơn.

## 6. Khai báo schema và tên object tường minh

Đối với dự án dùng nhiều schema, khai báo schemaName hoặc cấu hình default schema rõ ràng. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "team-db"
      changes:
        - createTable:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_customer
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
                  constraints:
                    nullable: false
~~~

Nếu schema app chưa tồn tại, cần một changeset hoặc bước provisioning tạo schema đó theo quyền và quy tắc của DBMS. Không giả định mọi database mới đều có schema app.

Đặt tên constraint/index ổn định:
- pk_customer
- fk_payment_customer
- uq_customer_email
- ck_payment_amount_positive
- ix_payment_customer_created

Tên rõ ràng giúp tìm object, đọc log, viết rollback và đối chiếu metadata. Chú ý giới hạn độ dài identifier của DBMS; cùng tên logic có thể cần tên vật lý rút gọn theo quy ước.

Không phụ thuộc vào tên constraint do DBMS tự sinh nếu migration sau cần drop hoặc tham chiếu constraint đó. Khai báo tên tường minh khi change type hỗ trợ.

## 7. Tạo cấu trúc bằng change type Liquibase

Ví dụ một changeset tạo bảng payment:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002-create-payment"
      author: "team-db"
      changes:
        - createTable:
            schemaName: app
            tableName: payment
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_payment
                    nullable: false
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: amount
                  type: DECIMAL(19, 4)
                  constraints:
                    nullable: false
              - column:
                  name: status_code
                  type: VARCHAR(24)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            schemaName: app
            tableName: payment
~~~

Ví dụ này giả định bảng app.customer và bảng reference chứa status_code đã được tạo trước. Các kiểu dữ liệu cần được kiểm tra trên từng DBMS hỗ trợ; DECIMAL(19,4) hoặc BIGINT có thể có cách ánh xạ vật lý khác nhưng phải đáp ứng cùng hợp đồng.

Tạo FK trong changeset sau khi cả hai bảng đã tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-payment-customer-fk"
      author: "team-db"
      changes:
        - addForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: payment
            baseColumnNames: customer_id
            referencedTableSchemaName: app
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_payment_customer
      rollback:
        - dropForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: payment
            constraintName: fk_payment_customer
~~~

Fresh install không có dữ liệu giao dịch cũ, nhưng vẫn cần bảo đảm bảng cha tồn tại trước khi thêm FK. Trên database đã có dữ liệu, cùng changeset này cần thêm bước kiểm tra dữ liệu mồ côi trước khi triển khai.

## 8. Chọn change type portable và SQL đặc thù DBMS

Ưu tiên change type Liquibase khi nó diễn đạt được cùng semantics trên các DBMS mục tiêu. Ví dụ createTable, addColumn, addForeignKeyConstraint, addUniqueConstraint và createIndex.

Nhưng một changelog portable không có nghĩa mọi thuộc tính đều được hỗ trợ giống nhau. Cần kiểm tra:
- DBMS có hỗ trợ change type không.
- Kiểu dữ liệu được ánh xạ ra sao.
- Constraint và index có cùng semantics không.
- Có cần SQL riêng cho expression/partial/online index không.
- Transaction DDL và rollback khác nhau thế nào.

Nếu phải dùng SQL riêng, giới hạn changeset theo DBMS:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-010-create-index-postgresql"
      author: "team-db"
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX CONCURRENTLY ix_payment_created
              ON app.payment(created_at)
      rollback:
        - sql:
            sql: |
              DROP INDEX CONCURRENTLY IF EXISTS app.ix_payment_created
~~~

Đây chỉ là ví dụ PostgreSQL. CREATE INDEX CONCURRENTLY có yêu cầu transaction riêng; có thể cần runInTransaction=false và phải kiểm tra trạng thái index nếu lệnh bị gián đoạn. Không đưa nguyên SQL này sang DBMS khác.

Fresh install cần chạy trên từng DBMS hỗ trợ. Một change type được chấp nhận trong YAML không chứng minh SQL được sinh ra và thực thi thành công trên mọi engine.

## 9. Preconditions khi database mới phải có trạng thái dự kiến

Với database sạch, precondition có thể xác minh schema hoặc object prerequisite. Ví dụ changeset thêm cột chỉ chạy khi bảng customer tồn tại và cột chưa có:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-020-add-customer-phone"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: customer
        - not:
            - columnExists:
                schemaName: app
                tableName: customer
                columnName: phone
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: VARCHAR(30)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: customer
            columnName: phone
~~~

Trong fresh install, điều kiện thường đạt nếu các changeset trước chạy đúng. Nếu precondition không đạt, HALT giúp dừng và phát hiện lỗi thứ tự hoặc cấu hình.

Không dùng MARK_RAN chỉ để làm test xanh. MARK_RAN có thể ghi nhận changeset mà không thực thi changes; nếu database mới thiếu object, cách này che giấu lỗi và khiến trạng thái lịch sử không phản ánh cấu trúc thực tế.

Precondition không thay thế PK/FK/UNIQUE ở cấp database. Nó kiểm tra giả định tại thời điểm migration, trong khi constraint bảo vệ dữ liệu về sau.

## 10. Nạp dữ liệu tham chiếu và seed cần thiết

Một fresh install thường cần dữ liệu tham chiếu như trạng thái thanh toán, loại khách hàng hoặc đơn vị tiền tệ. Dữ liệu này cần được quản lý bằng changeset riêng, có mã ổn định.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010-seed-payment-status"
      author: "team-db"
      changes:
        - insert:
            schemaName: app
            tableName: payment_status
            columns:
              - column:
                  name: code
                  value: PENDING
              - column:
                  name: display_name
                  value: "Chờ xử lý"
              - column:
                  name: active
                  valueBoolean: true
        - insert:
            schemaName: app
            tableName: payment_status
            columns:
              - column:
                  name: code
                  value: SUCCEEDED
              - column:
                  name: display_name
                  value: "Thành công"
              - column:
                  name: active
                  valueBoolean: true
      rollback:
        - delete:
            schemaName: app
            tableName: payment_status
            where: "code IN ('PENDING', 'SUCCEEDED')"
~~~

Rollback DELETE chỉ phù hợp khi những code này chưa bị dữ liệu khác tham chiếu và chưa có thay đổi runtime cần giữ. Trong production, giữ lại code lịch sử và ngừng active thường an toàn hơn xóa.

Đối với danh mục lớn, có thể dùng loadData hoặc loadUpdateData theo khóa ổn định. Tệp CSV phải được đóng gói cùng artifact, có encoding và schema rõ ràng. Không chỉnh file seed đã được phát hành để âm thầm thay đổi dữ liệu lịch sử; tạo version changeset mới.

Phân biệt:
- Reference data do ứng dụng quản lý.
- Dữ liệu demo/test chỉ dành cho context tương ứng.
- Dữ liệu giao dịch phát sinh sau khi ứng dụng hoạt động.
- Cấu hình runtime theo môi trường.

Không đưa dữ liệu cá nhân hoặc dữ liệu production vào seed changelog.

## 11. Dùng context và label có chủ đích

Một master changelog có thể chứa dữ liệu demo chỉ dùng trong development:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-030-seed-demo-customer"
      author: "team-db"
      contextFilter: dev
      changes:
        - insert:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 9001
              - column:
                  name: email
                  value: demo@example.invalid
~~~

Khi chạy fresh install, cần chọn filter đúng cho môi trường. Cú pháp filter và hành vi khi không truyền context có thể phụ thuộc phiên bản Liquibase; hãy kiểm tra tài liệu/CLI của phiên bản thực tế.

Không coi context là ranh giới bảo mật. Nếu production không được phép có demo data, cần kiểm tra cấu hình effective, tách changelog demo hoặc dùng cổng kiểm soát rõ ràng. Chạy update-sql với cùng filter trước khi thực thi để xác nhận changeset nào được chọn.

Label có thể dùng cho release hoặc nhóm tính năng; dbms giới hạn engine; context thường dùng cho môi trường/mục đích. Ba cơ chế này có ý nghĩa khác nhau và không nên dùng thay thế tùy tiện.

## 12. Cấu hình Liquibase CLI cho database mới

Liquibase CLI cần changelog, JDBC URL, driver và credentials. Ví dụ liquibase.properties không chứa password:

~~~properties
changeLogFile=db/changelog/db.changelog-master.yaml
url=jdbc:postgresql://localhost:5432/customer_service_test
username=migration_user
driver=org.postgresql.Driver
defaultSchemaName=app
liquibaseSchemaName=migration_meta
~~~

Tên thuộc tính cấu hình có thể khác theo cách sử dụng CLI và phiên bản; xác minh bằng help/tài liệu Liquibase đang dùng. Cấu hình giả định database customer_service_test đã tồn tại, schema app và migration_meta đã được provisioning hoặc được tạo bởi bước riêng.

Password nên được inject qua biến môi trường hoặc secret store theo cơ chế được hỗ trợ, không commit vào file properties. Nếu URL có chứa credentials hoặc token, không in nó ra log.

Trước khi update, xác nhận:
- URL trỏ đúng database mới.
- Username là migration user.
- Driver đúng DBMS.
- Default schema và Liquibase schema đúng.
- Changelog path đúng với artifact.
- Context/label/parameters được chỉ định.
- Không có lịch sử cũ ngoài dự kiến.

## 13. Chu trình validate, status, update-sql và update

Một fresh install có kiểm soát nên tách kiểm tra và thực thi:

### Bước 1: validate

~~~bash
liquibase validate
~~~

Kiểm tra cấu trúc changelog, include, định danh và những vấn đề validation mà phiên bản Liquibase hỗ trợ. Validate thành công không chứng minh quyền DDL, dữ liệu hay SQL runtime chắc chắn đạt.

### Bước 2: status

~~~bash
liquibase status --verbose
~~~

Với database mới, thông thường tất cả changeset được chọn sẽ pending. Nếu không thấy một changeset mong đợi, kiểm tra master include, context/label/dbms filter và database URL.

### Bước 3: update-sql

~~~bash
liquibase update-sql
~~~

Đọc SQL dự kiến:
- Có đúng schema/catalog không?
- Có tạo tất cả bảng theo thứ tự không?
- Có constraint/index không?
- Có seed dữ liệu không?
- Có câu SQL đặc thù DBMS bị chạy nhầm không?
- Có thao tác drop/alter không mong muốn không?
- Có dùng đúng changelog parameters không?

Update-sql tạo SQL để review, không thực thi thay đổi. Kết quả có thể khác khi trạng thái database thay đổi hoặc filter/config khác.

### Bước 4: update

~~~bash
liquibase update
~~~

Chỉ chạy trên database test cô lập sau khi đã review. Liquibase sẽ thực thi các changeset đủ điều kiện và ghi lịch sử.

### Bước 5: kiểm tra history

~~~bash
liquibase history
liquibase status --verbose
~~~

Các changeset thông thường vừa chạy sẽ không còn pending. Đọc cả output và database metadata; không chỉ dựa vào exit code.

## 14. Kiểm tra DATABASECHANGELOG và DATABASECHANGELOGLOCK

Liquibase lưu lịch sử trong DATABASECHANGELOG. Những cột thường được quan tâm gồm ID, AUTHOR, FILENAME, DATEEXECUTED, ORDEREXECUTED, EXECTYPE và MD5SUM.

Truy vấn minh họa:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
~~~

Nếu liquibase-schema được cấu hình, cần truy vấn đúng schema chứa bảng history.

Kiểm tra lock:

~~~sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

Cấu trúc/cột và schema phụ thuộc phiên bản/cấu hình; câu truy vấn cần điều chỉnh theo DBMS thực tế. Sau khi update hoàn tất bình thường, không nên còn một lock đang được giữ bởi tiến trình đã dừng.

Không xóa bảng lịch sử để “làm database mới” nếu mục tiêu là kiểm tra migration. Tạo database/schema cô lập mới sẽ an toàn và có thể tái lập hơn. Không giải phóng lock cưỡng bức khi chưa xác minh không còn migration đang chạy.

## 15. Xác minh schema thực tế sau update

DATABASECHANGELOG chỉ ghi nhận lịch sử Liquibase; nó không phải bản sao đầy đủ của schema hiện tại. Để xác minh fresh install, cần kiểm tra object thật.

Ví dụ PostgreSQL kiểm tra bảng/cột:

~~~sql
SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'app'
ORDER BY table_name, ordinal_position;
~~~

Kiểm tra constraint bằng catalog hoặc information_schema phù hợp với DBMS. Kiểm tra index bằng catalog của engine. Kiểm tra sequence/identity, view, routine, trigger và quyền nếu thuộc phạm vi.

Một bộ assertion nên so sánh:
- Danh sách bảng bắt buộc.
- Tên và kiểu cột.
- Nullability/default.
- PK/FK/UNIQUE/CHECK.
- Index và thứ tự cột.
- Sequence/identity.
- View/routine/trigger.
- Schema owner và grants.
- Dữ liệu tham chiếu.

Không so sánh raw metadata mà bỏ qua khác biệt DBMS đã được chấp nhận. Ví dụ một kiểu logic có thể được biểu diễn vật lý khác nhau nhưng phải có cùng semantics với ứng dụng.

## 16. Xác minh dữ liệu sau fresh install

Kiểm tra số lượng và giá trị dữ liệu tham chiếu:

~~~sql
SELECT code, display_name, active
FROM app.payment_status
ORDER BY code;
~~~

Kiểm tra dữ liệu bắt buộc không bị thiếu:

~~~sql
SELECT COUNT(*) AS missing_required_status
FROM app.payment_status
WHERE code IN ('PENDING', 'SUCCEEDED')
  AND active = false;
~~~

Truy vấn trên chỉ là ví dụ; tiêu chí thực tế phải phù hợp nghiệp vụ. Không nên chỉ kiểm tra COUNT(*) = 2 vì hai dòng sai code vẫn có thể làm test qua nếu không kiểm tra nội dung.

Fresh install thường không có giao dịch nghiệp vụ, nhưng phải có những reference data tối thiểu mà ứng dụng cần. Nếu danh mục được quản trị ngoài Liquibase, test cần seed fixture hoặc gọi API quản trị phù hợp và xác minh rõ nguồn dữ liệu.

Cũng nên kiểm tra:
- Unique code không trùng.
- FK không có tham chiếu mồ côi.
- Giá trị default đúng.
- Sequence tiếp tục sinh ID hợp lệ sau khi insert.
- Dữ liệu UTF-8 hiển thị đúng.
- Timestamp theo timezone mong đợi.

## 17. Chạy update lần thứ hai để kiểm tra tính ổn định

Sau khi fresh install thành công, gọi lại:

~~~bash
liquibase status --verbose
liquibase update
liquibase history
~~~

Mục tiêu:
- Changeset thông thường đã chạy không bị chạy lại.
- Không có bảng/cột/constraint được tạo trùng.
- Seed không nhân đôi.
- Không xuất hiện thay đổi ngoài dự kiến.
- DATABASECHANGELOG không ghi nhận một lần chạy lại bất thường.

Có ngoại lệ:
- runAlways được thiết kế để chạy ở mỗi lần update phù hợp.
- runOnChange có thể chạy lại khi nội dung liên quan thay đổi.
- Một số change type/SQL được cấu hình đặc biệt.

Vì vậy, test lần hai cần hiểu changelog hiện tại. Không kết luận mọi changeset luôn không chạy lại. Đối với seed thông thường, nên dùng changeset bất biến và khóa duy nhất để bảo vệ dữ liệu.

Nếu lần chạy thứ hai tạo thêm object hoặc row, điều tra định danh ID/AUTHOR/FILENAME, runAlways/runOnChange, filter, file include và SQL có được chạy ngoài Liquibase hay không.

## 18. Fresh install trên nhiều DBMS

Nếu module hỗ trợ nhiều DBMS, mỗi engine cần database mới riêng. Không chạy chung một database target giữa các job.

Ma trận ví dụ:

| DBMS | Fresh install | Schema assertion | Data assertion | Application test |
|---|---:|---:|---:|---:|
| PostgreSQL | Có | Có | Có | Có |
| MySQL | Có | Có | Có | Có |
| SQL Server | Có | Có | Có | Có |
| Oracle | Có | Có | Có | Có |

Đây là mẫu; chỉ đưa các DBMS và phiên bản nằm trong support policy thực tế.

Các khác biệt phải kiểm tra:
- Mapping kiểu dữ liệu.
- Identifier và schema mặc định.
- Identity/sequence.
- NULL và UNIQUE.
- Collation và Unicode.
- Index/constraint.
- Transaction DDL và lock.
- SQL đặc thù DBMS.
- JDBC driver và generated key.

H2 có thể hữu ích cho một số test nhanh, nhưng không thay thế integration test trên engine thật. Fresh install là thời điểm tốt để phát hiện change type hoặc SQL chỉ chạy trên DBMS mà người phát triển đang dùng.

## 19. Kiểm tra changelog có thể tái lập từ artifact

Một lỗi thường gặp là local chạy được vì máy phát triển có file CSV, SQL hoặc resource không được đóng gói vào artifact.

Hãy kiểm tra:
- Master changelog có nằm trong classpath/package không.
- Các tệp include có được copy vào artifact không.
- File CSV được loadData có tồn tại ở đường dẫn đã khai báo không.
- Relative path có đúng khi chạy từ CLI và Spring Boot không.
- Extension được khai báo có mặt trong runtime classpath không.
- Encoding file là UTF-8 hoặc đúng encoding được cấu hình.
- Không phụ thuộc file tuyệt đối trên máy dev.
- Không dùng biến môi trường chỉ có ở máy một người mà không được khai báo trong pipeline.

Một phép kiểm tra tốt là chạy migration từ **artifact đã build**, trong một môi trường sạch hoặc container, thay vì chỉ chạy từ IDE với source tree đầy đủ.

Cùng artifact nên được promote qua development, staging và production. Nếu build lại mỗi môi trường, có nguy cơ changelog/resource khác nhau dù source branch giống nhau.

## 20. Fresh install bằng Spring Boot

Có thể để Spring Boot chạy Liquibase khi khởi động ứng dụng:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Trong fresh install:
1. Database đã được provisioning.
2. Spring Boot tạo datasource.
3. Liquibase auto-configuration đọc master changelog.
4. Liquibase tạo/đọc bảng history và thực thi changeset.
5. Hibernate validate mapping sau khi schema đã được chuẩn bị theo thứ tự tích hợp.
6. Ứng dụng hoàn tất startup nếu các điều kiện khác đạt.

Kiểm tra log startup và xác minh DB trực tiếp. Không bật ddl-auto: update cùng Liquibase trong production để Hibernate âm thầm tạo object mà không có lịch sử changeset.

Nếu dùng datasource riêng cho Liquibase, khai báo spring.liquibase.url/user/password và kiểm tra URL đó trỏ cùng database/schema mà ứng dụng sẽ sử dụng hoặc tới đúng mục tiêu migration được thiết kế.

## 21. Fresh install bằng CI/CD migration job

Trong production, có thể tách migration khỏi startup ứng dụng:

~~~text
Provision database
       |
Create schema/users/grants
       |
Build and publish application artifact
       |
Run Liquibase validate/status/update-sql
       |
Review and approve
       |
Run Liquibase update
       |
Verify history/schema/data
       |
Deploy Spring Boot application
       |
Smoke test
~~~

Job migration phải:
- Dùng cùng changelog artifact với application release.
- Dùng tài khoản migration riêng.
- Xác minh database đích.
- Chạy validate/status/update-sql trước update.
- Kiểm soát context/label/parameters.
- Lưu log và SQL review.
- Không để nhiều job cùng cập nhật database.
- Xác minh DATABASECHANGELOG và schema thật.
- Chỉ cho ứng dụng nhận traffic khi schema đạt trạng thái tương thích.

Nếu fresh install là bước đầu tiên cho một khách hàng mới, provisioning và migration nên được ghi log riêng. Điều đó giúp phân biệt lỗi tạo database, lỗi quyền và lỗi changelog.

## 22. Kiểm tra ứng dụng sau khi schema được tạo

Fresh install chỉ thành công về database khi schema và dữ liệu đủ cho ứng dụng. Tiếp theo cần test ứng dụng:

- Kết nối datasource.
- Hibernate validate hoặc mapping validation phù hợp.
- Repository CRUD.
- Generated ID/sequence.
- Transaction commit/rollback.
- Query native và JPQL.
- API hoặc service sử dụng reference data.
- View, trigger hoặc routine mà ứng dụng phụ thuộc.
- Health check và readiness.
- Các job nền cần bảng hoặc index mới.

Một database có đủ bảng vẫn có thể không dùng được nếu thiếu grant, reference data hoặc sequence. Test ứng dụng giúp phát hiện những phụ thuộc không được thể hiện đầy đủ trong schema.

Nếu có nhiều DBMS, chạy cùng bộ test logic trên mỗi engine. Có thể dùng assertion chung và adapter riêng cho metadata theo DBMS.

## 23. Rollback sau fresh install

Fresh install thường dùng database test có thể xóa và tạo lại, nhưng vẫn nên hiểu rollback của changeset.

Các loại thao tác:
- CREATE TABLE: rollback DROP TABLE có thể xóa dữ liệu phát sinh.
- ADD COLUMN: rollback DROP COLUMN xóa giá trị đã ghi.
- INSERT seed: rollback DELETE có thể vi phạm FK hoặc xóa dữ liệu được ứng dụng dùng.
- ADD FK/UNIQUE: rollback drop constraint không khôi phục dữ liệu sai đã bị loại trước đó.
- Backfill: rollback chỉ chính xác nếu dữ liệu gốc được lưu hoặc phép biến đổi đảo ngược được.

Test rollback trên database có thể khôi phục:
1. Chạy tới changeset cần kiểm tra.
2. Nạp dữ liệu đại diện nếu rollback có thể xóa dữ liệu.
3. Sinh SQL rollback nếu công cụ/phiên bản hỗ trợ.
4. Chạy rollback theo điểm đích đã chọn.
5. Xác minh object và dữ liệu sau rollback.
6. Ghi nhận thao tác nào không thể đảo ngược hoàn toàn.
7. Dựng lại database và chạy update từ đầu để kiểm tra khả năng tái lập.

Không xem rollback thành công là bằng chứng fresh install ban đầu đúng; hai bài kiểm tra trả lời câu hỏi khác nhau.

## 24. Kiểm tra lỗi và khả năng khôi phục

Fresh install nên có các test âm tính có chủ đích trên database dùng một lần:

- Sai changelog path: ứng dụng/CLI phải báo lỗi rõ ràng.
- Thiếu JDBC driver: kết nối không thể khởi tạo.
- Thiếu quyền tạo bảng: migration dừng với lỗi quyền.
- Precondition không đạt: hành vi HALT/WARN/CONTINUE/MARK_RAN đúng chính sách.
- Changeset SQL sai: xác định changeset nào đã ghi nhận và trạng thái schema thực tế.
- Seed trùng khóa: database constraint bảo vệ tính duy nhất.
- Tệp CSV thiếu: migration thất bại và log chỉ rõ resource.
- DBMS không hỗ trợ change type: pipeline phát hiện trên engine đó.
- Migration bị dừng: kiểm tra transaction, lock và object được tạo một phần.

Khi lỗi:
1. Dừng retry tự động nếu trạng thái chưa rõ.
2. Đọc log để xác định changeset đầu tiên thất bại.
3. Đọc DATABASECHANGELOG và DATABASECHANGELOGLOCK.
4. Kiểm tra schema vật lý và dữ liệu.
5. Xác định transaction có rollback được không.
6. Sửa nguyên nhân bằng thay đổi có kiểm soát.
7. Chạy validate/status/update-sql lại.
8. Chỉ retry trên database có trạng thái đã hiểu.

Không xóa DATABASECHANGELOG để “reset” một fresh install thất bại. Nếu database test dùng một lần, có thể hủy và tạo database mới theo quy trình test; nếu database cần giữ lại để điều tra, bảo toàn history và bằng chứng.

## 25. Các lỗi thường gặp khi khởi tạo database mới

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Không tìm thấy changelog master | Sai classpath hoặc đường dẫn | Kiểm tra change-log và artifact |
| Không tìm thấy tệp include | Đường dẫn tương đối sai hoặc file không được đóng gói | Kiểm tra relativeToChangelogFile và resource |
| Table already exists | Database không sạch hoặc changeset bị nhận diện như mới | Kiểm tra object và ID/AUTHOR/FILENAME |
| Schema does not exist | Chưa provisioning hoặc chưa tạo schema | Tạo schema đúng thứ tự và quyền |
| Permission denied | Migration user thiếu quyền DDL/DML/history | Kiểm tra grants |
| Checksum validation failed | Changeset đã chạy bị sửa hoặc version khác | So sánh artifact và history; tạo changeset mới nếu cần |
| Foreign key creation failed | Bảng cha/cột chưa có hoặc dữ liệu không hợp lệ | Kiểm tra thứ tự và dữ liệu |
| Unique constraint failed | Seed hoặc fixture trùng khóa | Kiểm tra dữ liệu trước constraint |
| Sequence tạo ID trùng | Sequence chưa đồng bộ sau insert ID tường minh | Điều chỉnh sequence theo DBMS |
| Không có dữ liệu reference | Seed không được include hoặc bị filter | Kiểm tra master, context và label |
| Update chạy nhưng app lỗi | Thiếu grant, mapping hoặc dữ liệu | Chạy smoke/integration test |
| Update lần hai nhân đôi seed | runAlways, runOnChange hoặc seed không được thiết kế an toàn | Kiểm tra changeset và unique key |
| Một DBMS chạy, engine khác fail | SQL/type/transaction đặc thù | Chạy integration test trên DBMS thật |
| DATABASECHANGELOGLOCK bị giữ | Job dừng hoặc tiến trình khác còn chạy | Điều tra owner trước khi release lock |

## 26. Bài thực hành: dựng mới một database từ toàn bộ changelog

**Bối cảnh:** ứng dụng quản lý khách hàng và thanh toán dùng Liquibase. Cần tạo database test mới từ changelog master, bao gồm bảng khách hàng, trạng thái thanh toán, payment, khóa ngoại, index và dữ liệu tham chiếu.

### Phần A — Chuẩn bị

1. Chọn DBMS và phiên bản trong support matrix.
2. Provision một database trống.
3. Tạo migration user và runtime user theo quyền tối thiểu.
4. Xác nhận schema app và schema metadata.
5. Kiểm tra master changelog và toàn bộ include trong artifact.
6. Pin Liquibase, JDBC driver và extension.
7. Xác định context/label/parameters cần dùng.

### Phần B — Kiểm tra trước migration

1. Chạy validate.
2. Chạy status --verbose.
3. Xác nhận các changeset cần thiết đang pending.
4. Chạy update-sql.
5. Review thứ tự tạo bảng, khóa, index và seed.
6. Xác nhận không có dữ liệu demo ngoài ý muốn.
7. Xác nhận đúng database URL và schema.

### Phần C — Thực thi

1. Chạy update trên database mới.
2. Lưu output và thời gian.
3. Truy vấn DATABASECHANGELOG.
4. Kiểm tra DATABASECHANGELOGLOCK.
5. Kiểm tra metadata bảng/cột/constraint/index.
6. Kiểm tra reference data.
7. Kiểm tra sequence/identity bằng một thao tác insert thử.
8. Khởi động ứng dụng với Hibernate validate.

### Phần D — Chạy lại và kiểm thử ứng dụng

1. Chạy status lần nữa.
2. Chạy update lần hai.
3. Xác nhận không có object hoặc seed bị nhân đôi.
4. Chạy repository/API integration test.
5. Kiểm tra transaction và generated ID.
6. Kiểm tra log/health check.
7. Chạy test rollback trên database có thể khôi phục.

### Phần E — Lặp lại trên môi trường sạch khác

1. Tạo database mới thứ hai hoặc engine khác trong support matrix.
2. Dùng cùng artifact/changelog.
3. Chạy cùng quy trình.
4. So sánh kết quả logic về schema và dữ liệu.
5. Ghi nhận khác biệt vật lý được chấp nhận.
6. Xác nhận pipeline fail nếu một DBMS không đạt.

### Câu hỏi tự kiểm tra

- Vì sao database phải thật sự sạch? **Để xác minh toàn bộ changelog có thể tạo schema từ đầu và không phụ thuộc thay đổi thủ công.**
- Chỉ chạy update có đủ chứng minh thành công không? **Không.** Cần kiểm tra history, schema, dữ liệu và ứng dụng.
- Vì sao chạy update lần hai? **Để phát hiện changeset/seed không được thiết kế đúng cho lịch sử và khả năng chạy lặp.**
- Có nên tạo database bằng Liquibase luôn không? **Thông thường provisioning database/server được tách khỏi migration schema nghiệp vụ; phụ thuộc quyền và chính sách nền tảng.**
- Nếu một changeset bị filter thì nó đã được chạy chưa? **Không nhất thiết.** Kiểm tra status và history với filter thực tế.
- H2 có thay thế test fresh install trên DBMS production không? **Không.**
- Nếu update thất bại, có nên xóa DATABASECHANGELOG rồi chạy lại? **Không.** Cần xác định trạng thái vật lý và lịch sử trước.
- Vì sao cần test từ artifact đóng gói? **Để phát hiện resource include/CSV/SQL thiếu trong package dù local source chạy được.**

## 27. Checklist nghiệm thu fresh install

**Database và cấu hình**
- [ ] Database/catalog đích đã được provisioning và xác minh.
- [ ] DBMS/version, JDBC driver và Liquibase version thuộc support matrix.
- [ ] Migration user có quyền đúng phạm vi; runtime user có quyền tối thiểu.
- [ ] Schema ứng dụng và schema metadata được xác định.
- [ ] Database không chứa history/object cũ ngoài dự kiến.
- [ ] URL, profile, context, label và parameters được kiểm tra.

**Changelog**
- [ ] Master changelog là entry point duy nhất được chọn.
- [ ] Tất cả include/resource/CSV/SQL được đóng gói trong artifact.
- [ ] Thứ tự changeset đáp ứng dependency.
- [ ] ID/AUTHOR/FILENAME ổn định.
- [ ] Change type được hỗ trợ trên DBMS mục tiêu.
- [ ] Precondition phản ánh trạng thái mong đợi.
- [ ] Reference data và demo data được tách đúng phạm vi.
- [ ] Rollback được khai báo hoặc giới hạn không thể đảo ngược được ghi nhận.

**Thực thi và xác minh**
- [ ] Validate PASS.
- [ ] Status hiển thị đúng tập changeset pending.
- [ ] Update-sql được review trên đúng DBMS/configuration.
- [ ] Update hoàn tất.
- [ ] DATABASECHANGELOG có đủ changeset và checksum phù hợp.
- [ ] DATABASECHANGELOGLOCK không bị giữ bất thường.
- [ ] Schema assertion đạt: bảng, cột, khóa, index, sequence, view.
- [ ] Data assertion đạt: seed, reference code, quan hệ và giá trị mặc định.
- [ ] Chạy update lần hai không tạo thay đổi ngoài dự kiến.
- [ ] Hibernate validate và ứng dụng khởi động thành công.
- [ ] Repository/API/transaction smoke test đạt.
- [ ] Rollback hoặc forward fix đã được đánh giá.
- [ ] Log và artifact bằng chứng được lưu an toàn.

**CI/CD và nhiều môi trường**
- [ ] Fresh install test chạy trên từng DBMS/version được hỗ trợ.
- [ ] Dùng cùng artifact/changelog khi promote.
- [ ] Không dùng H2 làm bằng chứng duy nhất.
- [ ] Job migration có ownership và quyền rõ ràng.
- [ ] Có review SQL, approval và kiểm soát secret.
- [ ] Pipeline báo lỗi rõ nếu một engine không đạt.
- [ ] Có kế hoạch xử lý khi migration thành công nhưng app deploy thất bại.

**Kết luận:** khởi tạo database mới từ toàn bộ changelog là phép thử chứng minh hệ thống có thể tái lập schema và dữ liệu từ một điểm bắt đầu sạch. Liquibase cung cấp changelog, changeset, precondition, checksum và DATABASECHANGELOG để quản lý quá trình đó; nhưng chỉ kiểm tra bằng cả generated SQL, object thực tế, dữ liệu, lần update lặp và ứng dụng mới xác nhận được kết quả. Khi fresh install được chạy trên đúng DBMS/version, từ artifact hoàn chỉnh và trong pipeline có kiểm soát, nhóm có nền tảng đáng tin cậy để triển khai database mới và tiếp tục nâng cấp qua nhiều môi trường.
