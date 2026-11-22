# Thực hành điều tra checksum, khóa và changeset lỗi

## 1. Mục tiêu và nguyên tắc an toàn

Trong module DATABASE_SCHEMA_MIGRATION_LIQUIBASE, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD, người vận hành cần xử lý được ba nhóm sự cố thường gặp: checksum không khớp, khóa Liquibase còn bị giữ và changeset thất bại khi thực thi.

Ba sự cố này có thể xuất hiện cùng lúc nhưng nguyên nhân và cách phục hồi khác nhau:

- **Checksum mismatch:** nội dung changeset hiện tại không còn khớp checksum được lưu khi changeset đã chạy, hoặc cách tính checksum thay đổi theo phiên bản Liquibase.
- **Liquibase lock:** một runner đang giữ quyền cập nhật changelog, hoặc runner trước kết thúc bất thường khiến trạng thái lock còn lại.
- **Changeset failure:** database từ chối SQL, precondition không đạt, thiếu quyền, timeout hoặc một phần thao tác đã được thực thi trước khi lỗi xảy ra.

Mục tiêu bài thực hành là biết thu thập bằng chứng, xác định trạng thái thực tế của database, chọn phương án phục hồi có thể giải thích và kiểm chứng sau xử lý. Không dùng database production để cố tình tạo lỗi. Hãy dùng database disposable riêng, có thể xóa và tạo lại, cùng tài khoản migration được giới hạn trong database đó.

**Quy tắc an toàn:** không xóa/sửa thủ công bản ghi DATABASECHANGELOG hoặc DATABASECHANGELOGLOCK, không chạy clear-checksums theo phản xạ, không giải phóng lock khi runner còn hoạt động và không retry mù một changeset có DDL. Các thao tác này có thể làm Liquibase chạy lại thay đổi đã thực hiện, che giấu schema drift hoặc gây hỏng dữ liệu.

Sau bài học, bạn có thể:

1. Phân biệt checksum mismatch với lỗi validate, lỗi SQL và lỗi lock.
2. Đọc lịch sử changeset và đối chiếu checksum với source đã phát hành.
3. Xác định runner nào đang giữ lock và khi nào được phép release lock.
4. Phân tích changeset thất bại có transaction rollback hay để lại DDL một phần.
5. Chọn restore source, tạo changeset mới, sửa dữ liệu, retry hoặc forward-fix theo bằng chứng.
6. Lập báo cáo sự cố và thêm kiểm tra phòng ngừa vào CI/CD.

## 2. Chuẩn bị môi trường lab

### 2.1. Tạo database dùng riêng

Tạo một database test có thể tái tạo, ví dụ `liquibase_incident_lab`. Dùng đúng DBMS mà nhóm đang hỗ trợ. Không dùng H2 để kết luận về transaction DDL, metadata hoặc lock của PostgreSQL, MySQL, SQL Server hay Oracle nếu production chạy một trong các engine đó.

Chuẩn bị:

- Một database rỗng cho kịch bản cài mới.
- Một database đã chạy một số changeset để có lịch sử.
- Một user migration có quyền tạo/sửa object và ghi metadata trong phạm vi lab.
- Một user runtime không có quyền DDL, nếu muốn kiểm tra thêm khác biệt quyền.
- Một master changelog cố định và các file include được đóng gói cùng artifact.
- Một bản sao source changelog trước khi cố tình sửa để có thể khôi phục.

Ghi lại DBMS product/version, Java, Liquibase core/CLI, JDBC driver và extension version. CLI và Liquibase library trong Spring Boot có thể khác nhau; hãy xác định tiến trình nào thực sự chạy migration.

### 2.2. Cấu hình kết nối mẫu

Ví dụ file properties dùng riêng cho lab:

~~~properties
changeLogFile=classpath:/db/changelog/db.changelog-master.yaml
url=jdbc:postgresql://localhost:5432/liquibase_incident_lab
username=liquibase_migrator
password=${LAB_DB_PASSWORD}
defaultSchemaName=app
liquibaseSchemaName=liquibase_meta
contexts=lab
~~~

Đây chỉ là ví dụ minh họa cho PostgreSQL CLI. Cách đặt tên property và truyền secret phụ thuộc Liquibase version, plugin hoặc Spring Boot. Không commit mật khẩu thật vào file. Với Spring Boot, các thuộc tính kết nối và schema có thể được truyền qua cấu hình ngoài; phải kiểm tra giá trị hiệu lực.

### 2.3. Tạo changelog ban đầu

Ví dụ master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-seed-lab-customer.yaml
      relativeToChangelogFile: true
~~~

File `changes/001-create-customer.yaml`:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-customer
      author: lab
      context: lab
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
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
              - column:
                  name: display_name
                  type: VARCHAR(200)
~~~

File `changes/002-seed-lab-customer.yaml`:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: seed-lab-customer
      author: lab
      context: lab
      changes:
        - insert:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 1
              - column:
                  name: email
                  value: lab@example.invalid
              - column:
                  name: display_name
                  value: Lab Customer
~~~

Các changeset ví dụ chỉ phục vụ lab. Trong hệ thống thật, dữ liệu tham chiếu cần có quy tắc định danh, xử lý xung đột và phân biệt seed data với dữ liệu nghiệp vụ.

### 2.4. Chạy lần đầu và lưu bằng chứng

Trước khi update:

~~~bash
liquibase --defaults-file=liquibase-lab.properties validate
liquibase --defaults-file=liquibase-lab.properties status --verbose
liquibase --defaults-file=liquibase-lab.properties update-sql
~~~

Đọc SQL preview, xác nhận đúng database/schema và changeset. Sau đó mới chạy:

~~~bash
liquibase --defaults-file=liquibase-lab.properties update
liquibase --defaults-file=liquibase-lab.properties history
~~~

Lưu commit, version Liquibase, JDBC driver, SQL preview, log và kết quả history. Trạng thái mong đợi: hai changeset lab đã được thực thi, bảng customer tồn tại và có một hàng dữ liệu.

## 3. Hiểu ba trạng thái trước khi xử lý

### 3.1. DATABASECHANGELOG là lịch sử thực thi

Liquibase ghi nhận changeset đã xử lý trong bảng DATABASECHANGELOG. Các cột thường cần xem gồm:

| Cột | Ý nghĩa điều tra |
|---|---|
| ID | Định danh changeset |
| AUTHOR | Tác giả changeset |
| FILENAME | Đường dẫn file/logical path được nhận diện |
| MD5SUM | Checksum được lưu |
| DATEEXECUTED | Thời điểm Liquibase ghi nhận |
| ORDEREXECUTED | Thứ tự thực thi |
| EXECTYPE | Kiểu kết quả như EXECUTED, RERAN hoặc MARK_RAN |
| DEPLOYMENT_ID | Nhóm triển khai nếu version/cấu hình ghi nhận |

Tên cột và một số giá trị có thể thay đổi theo phiên bản hoặc DBMS. Hãy truy vấn bảng trong schema metadata được cấu hình, không mặc định nó nằm trong schema nghiệp vụ.

Một changeset có row trong DATABASECHANGELOG không chứng minh object vẫn đúng hiện trạng. Object có thể bị sửa thủ công sau migration. Ngược lại, một changeset không có row không chứng minh nó chưa tác động database: DDL có thể đã thực thi một phần trước khi tiến trình thất bại.

### 3.2. DATABASECHANGELOGLOCK điều phối runner

Liquibase dùng bảng DATABASECHANGELOGLOCK để tránh nhiều Liquibase runner cùng cập nhật một bộ lịch sử. Bản ghi lock thường chứa:

- ID của lock row.
- LOCKED cho biết trạng thái khóa.
- LOCKGRANTED là thời điểm khóa được cấp.
- LOCKEDBY là thông tin máy/tiến trình giữ khóa.

Lock row còn đánh dấu locked không tự chứng minh runner đã chết. Tiến trình có thể vẫn chạy, đang chờ database hoặc đang thực hiện một changeset lâu. Phải kiểm tra process/job và session database trước khi release lock.

### 3.3. Phân biệt bốn kết quả

| Kết quả | Bằng chứng thường thấy | Hướng điều tra |
|---|---|---|
| Checksum mismatch | Validation báo checksum của changeset đã chạy không khớp | Source đã phát hành, row history, Liquibase version |
| Lock timeout | Liquibase không lấy được lock | Runner đang chạy, session DB, lock row |
| Changeset execution failed | SQL/precondition/permission/timeout error | Log, SQL, transaction boundary, object thực tế |
| Update thành công nhưng schema sai | History đã ghi nhưng object/data không đúng kỳ vọng | Schema drift, MARK_RAN, SQL và hậu kiểm |

Không dùng một lệnh reset cho cả bốn trường hợp. Mỗi loại cần một quyết định riêng dựa trên trạng thái database.

## 4. Lab A — Điều tra checksum mismatch

### 4.1. Tạo trạng thái đã triển khai

Sau khi chạy hai changeset ban đầu, xác nhận row của create-customer và seed-lab-customer có trong DATABASECHANGELOG. Lưu checksum hiện tại của create-customer và bản source đã phát hành.

Có thể xem lịch sử bằng:

~~~bash
liquibase --defaults-file=liquibase-lab.properties history
liquibase --defaults-file=liquibase-lab.properties status --verbose
~~~

Nếu cần truy vấn trực tiếp, dùng SELECT trên bảng DATABASECHANGELOG tại schema metadata đúng. Cú pháp quote identifier và tên schema tùy DBMS.

### 4.2. Cố tình sửa changeset đã chạy

Trong database lab, sửa file 001-create-customer.yaml sau khi đã chạy, ví dụ đổi độ dài display_name từ VARCHAR(200) thành VARCHAR(300). Không tạo changeset mới ở bước này. Chạy:

~~~bash
liquibase --defaults-file=liquibase-lab.properties validate
liquibase --defaults-file=liquibase-lab.properties status --verbose
~~~

Tùy version và lệnh, Liquibase có thể phát hiện checksum mismatch trong quá trình validate/update hoặc khi so sánh lịch sử. Ghi lại:

1. Changeset nào được báo.
2. ID, author và filename/logical path.
3. Checksum đang lưu trong DATABASECHANGELOG.
4. Nội dung source hiện tại và source đã phát hành.
5. Version Liquibase thực thi.

**Giải thích:** checksum bảo vệ tính bất biến của changeset đã triển khai. Khi source thay đổi, Liquibase có thể nhận ra nội dung hiện tại không giống nội dung từng được áp dụng. Thay đổi độ dài cột trong source cũ không tự tạo migration alter column; nó chỉ làm lịch sử không còn khớp.

### 4.3. Chọn cách phục hồi đúng

Có ba hướng thường gặp:

**Hướng 1 — Khôi phục nội dung changeset đã phát hành.** Nếu thay đổi là chỉnh sửa nhầm, trả file về đúng nội dung đã triển khai. Sau đó tạo một changeset mới với ID khác để đổi độ dài cột nếu yêu cầu nghiệp vụ vẫn còn.

**Hướng 2 — Tạo changeset mới.** Đây là hướng phù hợp khi cần thay đổi schema thật. Giữ nguyên changeset cũ và thêm changeSet mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: widen-customer-display-name
      author: lab
      context: lab
      changes:
        - modifyDataType:
            schemaName: app
            tableName: customer
            columnName: display_name
            newDataType: VARCHAR(300)
~~~

Đưa changeset mới vào master changelog, chạy validate và update-sql, rồi thử trên database có history. Change type modifyDataType và SQL được sinh ra cần được kiểm tra trên DBMS mục tiêu.

**Hướng 3 — Chấp nhận checksum khác trong trường hợp có kiểm soát.** Liquibase có cơ chế validCheckSum cho một số tình huống được phê duyệt. Nó chỉ nói rằng checksum cụ thể được chấp nhận; nó không tự sửa schema và không thực thi thay đổi đã bị bỏ sót. Phải có lý do, checksum được xác minh, bằng chứng schema thực tế và review rõ ràng.

Không dùng validCheckSum để che việc sửa changeset đã triển khai mà chưa biết database thực tế đang ở trạng thái nào.

### 4.4. Khi nào dùng clear-checksums?

clear-checksums xóa checksum đã lưu để Liquibase tính lại khi lần update tiếp theo diễn ra. Đây không phải công cụ sửa nội dung changeset và không làm schema trở lại trạng thái mong muốn.

Chỉ cân nhắc khi:

- Đã xác định nguyên nhân liên quan checksum/version và hiểu tác động của việc tính lại.
- Đã thử trên bản sao database có history.
- Đã so sánh source với phiên bản đã phát hành.
- Có phê duyệt và cửa sổ triển khai phù hợp.
- Có kế hoạch xác minh toàn bộ lịch sử sau lần update.

Không chạy clear-checksums để chữa mọi lỗi checksum mismatch, cũng không chạy trực tiếp trên production khi chưa biết changeset nào đã bị sửa. Nếu nguyên nhân là changeset cũ bị thay nội dung, ưu tiên khôi phục source hoặc tạo changeset mới.

### 4.5. Hậu kiểm Lab A

Sau khi khôi phục source hoặc thêm changeset mới:

- validate thành công.
- status --verbose chỉ liệt kê changeset thực sự pending.
- SQL preview có đúng câu ALTER/modify type dự kiến.
- Update chỉ thực thi changeset mới, không chạy lại changeset cũ.
- DATABASECHANGELOG giữ row cũ và có row mới sau update.
- Cột thực tế có kiểu dữ liệu mong đợi; dữ liệu cũ vẫn đọc được.

## 5. Lab B — Điều tra lock bị giữ

### 5.1. Tạo tình huống runner giữ lock

Trên database lab, bắt đầu một migration đủ lâu để quan sát. Có thể dùng changeset chạy một thao tác có thời gian thực thi được kiểm soát trong môi trường test, hoặc chạy hai Liquibase job gần như đồng thời. Không cố tình kill tiến trình trên database dùng chung.

Trong khi runner A đang hoạt động, khởi chạy runner B với cùng database và schema metadata. Runner B có thể chờ lock hoặc báo không lấy được lock sau thời gian chờ.

Ghi lại:

- Job/instance nào là runner A và runner B.
- Thời điểm runner A bắt đầu.
- Log runner B và thời gian chờ.
- Trạng thái row DATABASECHANGELOGLOCK.
- Session database đang chạy câu SQL nào, nếu DBMS cung cấp thông tin đó.

### 5.2. Kiểm tra lock và process owner

Dùng truy vấn đọc trên bảng lock trong schema metadata. Ví dụ dạng tổng quát:

~~~sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM liquibase_meta.DATABASECHANGELOGLOCK;
~~~

Tên schema, cách viết hoa/thường và quy tắc quote phụ thuộc DBMS. Không chạy câu UPDATE/DELETE trên bảng lock để tự mở khóa.

Đối chiếu LOCKEDBY và thời điểm LOCKGRANTED với:

- Pipeline đang chạy hoặc job bị treo.
- Process Java/CLI trong container/VM.
- Session database, transaction và câu SQL hiện tại.
- Log của runner, đặc biệt là changeset bắt đầu cuối cùng.
- Tình trạng network, connection pool và timeout.

### 5.3. Phân biệt lock hợp lệ và lock mồ côi

**Lock hợp lệ:** runner vẫn hoạt động, có session hoặc đang thực hiện migration lâu. Không release lock. Hãy chờ theo thời gian vận hành đã định, theo dõi tiến độ và xác định liệu câu SQL có bị block bởi transaction khác hay không.

**Lock có thể mồ côi:** job/process đã kết thúc bất thường, không còn session thực thi tương ứng, không còn runner nào có thể sở hữu lock và log cho thấy lần chạy đã dừng. Trước khi kết luận, kiểm tra cả process trong hệ thống điều phối và session database; chỉ nhìn LOCKEDBY cũ là chưa đủ.

### 5.4. Giải phóng lock theo quy trình

Chỉ sau khi xác nhận không còn runner hoạt động và đã đánh giá trạng thái changeset/object, dùng command release lock của Liquibase:

~~~bash
liquibase --defaults-file=liquibase-lab.properties release-locks
~~~

Tên command hoặc cách gọi có thể khác theo phiên bản/CLI. Chạy với đúng cấu hình kết nối và schema metadata của database đang điều tra. Sau đó:

~~~bash
liquibase --defaults-file=liquibase-lab.properties status --verbose
liquibase --defaults-file=liquibase-lab.properties update-sql
~~~

Không chạy update ngay chỉ vì lock đã được giải phóng. Trước hết xác định changeset cuối cùng đã thực thi hoàn toàn hay một phần, đối chiếu history và object thực tế. Nếu DDL đã tạo object nhưng changeset chưa được ghi nhận, retry có thể thất bại vì object tồn tại.

### 5.5. Hậu kiểm Lab B

- Runner A kết thúc hoặc được xác nhận đã chết.
- Không còn session/transaction đang thực thi migration cũ.
- Lock được giải phóng bằng command được hỗ trợ.
- Status cho thấy changeset nào còn pending.
- SQL preview phù hợp với trạng thái database hiện tại.
- Chỉ một runner được phép tiếp tục migration.
- DATABASECHANGELOG và schema thực tế nhất quán sau update.

## 6. Lab C — Điều tra changeset thất bại

### 6.1. Tạo lỗi có thể tái hiện

Một cách an toàn là tạo dữ liệu duplicate rồi thử thêm unique constraint. Trước hết thêm hai khách hàng có cùng email vào database lab:

~~~sql
INSERT INTO app.customer (id, email, display_name)
VALUES
  (2, 'duplicate@example.invalid', 'Customer A'),
  (3, 'duplicate@example.invalid', 'Customer B');
~~~

Tạo changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: add-unique-customer-email
      author: lab
      context: lab
      preConditions:
        - onFail: HALT
        - onError: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM (
                SELECT email
                FROM app.customer
                GROUP BY email
                HAVING COUNT(*) > 1
              ) duplicates
      changes:
        - addUniqueConstraint:
            schemaName: app
            tableName: customer
            columnNames: email
            constraintName: uq_customer_email
~~~

Với dataset trên, precondition không đạt. Chạy validate, status và update trên database lab. Liquibase phải dừng theo onFail HALT; changeset chưa được áp dụng và không được xem là hoàn tất. Ghi lại log precondition và xác nhận không có unique constraint trong catalog.

Đây là lỗi điều kiện dữ liệu, không phải checksum mismatch và cũng không phải lock. Cách xử lý là giải quyết duplicate theo quy tắc nghiệp vụ rồi chạy lại sau khi kiểm tra precondition, không đổi thành MARK_RAN để pipeline xanh.

### 6.2. Sửa dữ liệu và chạy lại

Quyết định bản ghi nào được giữ phải dựa trên nghiệp vụ. Trong lab, có thể đổi email của một hàng để làm dữ liệu duy nhất:

~~~sql
UPDATE app.customer
SET email = 'customer-b@example.invalid'
WHERE id = 3;
~~~

Chạy lại query precondition để xác nhận kết quả bằng 0. Sau đó chạy:

~~~bash
liquibase --defaults-file=liquibase-lab.properties status --verbose
liquibase --defaults-file=liquibase-lab.properties update-sql
liquibase --defaults-file=liquibase-lab.properties update
~~~

Hậu kiểm: unique constraint tồn tại, dữ liệu hiện tại thỏa constraint và changeset có trạng thái thực thi thành công trong DATABASECHANGELOG.

### 6.3. Trường hợp DDL đã chạy một phần

Một changeset có thể gồm nhiều thao tác. Nếu DBMS không hỗ trợ transaction DDL cho một số lệnh, hoặc thay đổi có implicit commit, lệnh đầu có thể thành công trước khi lệnh sau thất bại. Khi đó:

- Changeset có thể chưa có row hoàn tất trong DATABASECHANGELOG.
- Một hoặc nhiều object đã xuất hiện trong schema.
- Retry có thể báo object đã tồn tại.
- Rollback tự động có thể không hoàn tác mọi thao tác.

Ví dụ trong lab, một changeset tạo bảng rồi tạo index với tên/cấu hình không hợp lệ. Kết quả cụ thể phụ thuộc DBMS và loại DDL; phải quan sát trạng thái thật, không suy luận chỉ từ exception.

Quy trình điều tra:

1. Ghi lại changeset ID/author/file path và SQL preview.
2. Đọc log để tìm câu lệnh cuối cùng bắt đầu và câu lệnh gây lỗi.
3. Kiểm tra DATABASECHANGELOG xem changeset đã được ghi nhận chưa.
4. Kiểm tra catalog để biết bảng/index/constraint nào đã tồn tại.
5. Kiểm tra dữ liệu có bị insert/update một phần không.
6. Xác định DBMS có transaction DDL cho thao tác đó hay không.
7. Chọn cleanup có kiểm soát trên lab hoặc forward-fix cho môi trường đã có dữ liệu.

Không xóa object theo tên đoán. Trước khi drop object, xác minh owner, definition, dependency và dữ liệu. Trên production, nếu object có giá trị hoặc được ứng dụng sử dụng, thường cần một changeset sửa chữa/forward-fix được review thay vì thao tác cleanup tùy tiện.

## 7. Cách phân biệt nguyên nhân từ log

| Dấu hiệu | Khả năng cao | Bằng chứng tiếp theo |
|---|---|---|
| Checksum stored và checksum calculated khác nhau | Changeset đã sửa hoặc checksum version thay đổi | So source đã phát hành, version Liquibase và row history |
| Waiting for changelog lock / could not acquire lock | Runner khác đang giữ lock | Job, process, session DB và lock row |
| Precondition failed | Dữ liệu/schema không đạt điều kiện | Query precondition và object/data thực tế |
| Permission denied | Principal thiếu quyền | Grants, owner và schema metadata |
| Table/index/constraint already exists | Drift hoặc DDL đã thực thi một phần | Catalog, history và log câu lệnh trước |
| Connection lost / timeout | Mất phản hồi khi SQL có thể đã chạy | Session, transaction, object và DATABASECHANGELOG |
| SQL syntax/type error | DBMS/version/driver hoặc SQL generator khác | SQL preview và DBMS version |
| Update thành công nhưng thay đổi không có | Context/label, MARK_RAN hoặc nhầm target | Filter, EXECTYPE, schema và database identity |

Đọc stack trace từ nguyên nhân gốc, không chỉ dòng “Migration failed”. Ghi changeset đang chạy, câu SQL gây lỗi, SQLState/vendor code, DBMS version và transaction boundary.

## 8. Cây quyết định phục hồi

~~~mermaid
flowchart TD
    A[Liquibase update thất bại] --> B{Có runner đang hoạt động?}
    B -->|Có| C[Không release lock; theo dõi runner và DB session]
    B -->|Không| D{Lock còn bị giữ?}
    D -->|Có| E[Đối chiếu process, session, log và changeset]
    E --> F[Chỉ release-locks khi xác nhận lock mồ côi]
    D -->|Không| G{Checksum mismatch?}
    F --> G
    G -->|Có| H[Đối chiếu source đã phát hành và DATABASECHANGELOG]
    H --> I[Khôi phục source hoặc thêm changeset mới]
    G -->|Không| J{Changeset có lỗi khi thực thi?}
    J -->|Có| K[Kiểm tra SQL, precondition, quyền và object thực tế]
    K --> L{DDL/data đã thực thi một phần?}
    L -->|Có| M[Chọn cleanup lab hoặc forward-fix có review]
    L -->|Không| N[Sửa nguyên nhân và retry có kiểm soát]
    J -->|Không| O[Kiểm tra target, filter, driver và cấu hình]
    I --> P[Validate, status, update-sql và hậu kiểm]
    M --> P
    N --> P
    O --> P
~~~

Cây quyết định giúp sắp xếp thứ tự điều tra. Trong sự cố thật, một lỗi có thể đồng thời liên quan lock và changeset đã thực thi một phần; khi đó phải hoàn tất kiểm tra process/lock và trạng thái object trước khi quyết định retry.

## 9. Những lệnh cần biết và giới hạn của chúng

| Lệnh | Mục đích | Không chứng minh được |
|---|---|---|
| validate | Kiểm tra cấu trúc changelog và tham chiếu có thể xác minh | Không chứng minh DDL chạy thành công trên DBMS |
| status --verbose | Liệt kê changeset pending theo cấu hình hiện tại | Không chứng minh schema thực tế không drift |
| update-sql | Sinh SQL dự kiến để review | Không chứng minh quyền, lock hoặc transaction runtime |
| history | Xem lịch sử changeset đã ghi nhận | Không chứng minh object vẫn đúng hiện trạng |
| release-locks | Giải phóng lock theo cơ chế Liquibase | Không sửa DDL đã thực thi một phần |
| clear-checksums | Xóa checksum lưu để tính lại ở lần update tiếp theo | Không sửa source hoặc schema |
| update | Thực thi changeset pending | Không bảo đảm một DDL đã rollback nếu DBMS không hỗ trợ |

Command và option có thể khác theo Liquibase version. Luôn dùng cùng defaults file, JDBC driver, changelog, context, label, parameter và schema của target đang điều tra. Không chạy các lệnh thay đổi trạng thái trên production chỉ để thử.

### 9.1. Truy vấn metadata phải phù hợp DBMS

SQL truy vấn DATABASECHANGELOG và DATABASECHANGELOGLOCK có thể khác về quote identifier, schema/catalog và kiểu dữ liệu giữa các DBMS. Bắt đầu bằng truy vấn SELECT đọc-only trên đúng schema metadata. Nếu bảng dùng prefix hoặc tên tùy chỉnh, dùng cấu hình Liquibase thực tế để xác định đúng tên.

Không dùng UPDATE/DELETE trực tiếp trên hai bảng này để tự sửa checksum, execution type hoặc lock. Nếu phải phục hồi metadata sau sự cố đặc biệt, cần runbook đã được DBA và nhóm sở hữu migration phê duyệt.

## 10. Hậu kiểm sau phục hồi

Sau mọi thao tác khôi phục, không chỉ kiểm tra command trả exit code 0. Xác nhận từng lớp:

### 10.1. Lịch sử

- Changeset đã chạy có row đúng trong DATABASECHANGELOG.
- ID, author và filename/logical path không bị nhân đôi.
- Checksum phù hợp với source đã phát hành hoặc ngoại lệ đã được phê duyệt.
- EXECTYPE phản ánh kết quả mong đợi.
- Không còn lock ngoài dự kiến.

### 10.2. Schema và dữ liệu

- Bảng, cột, kiểu dữ liệu, default, index và constraint tồn tại đúng.
- Object không bị tạo trùng hoặc tạo nhầm schema.
- Dữ liệu backfill/seed đúng số lượng và quy tắc nghiệp vụ.
- Không còn duplicate, NULL hoặc orphan row vi phạm điều kiện.
- Quyền migration/runtime vẫn đúng sau thay đổi.

### 10.3. Ứng dụng và pipeline

- validate, status --verbose và update-sql có kết quả phù hợp.
- Ứng dụng khởi động và truy vấn các object mới được.
- Smoke test và health check đạt.
- Log liên kết được release, commit, runner và database target.
- CI có test tái hiện sự cố hoặc kiểm tra ngăn tái diễn.

## 11. Phòng ngừa sự cố trong changelog và pipeline

### 11.1. Giữ changeset đã triển khai bất biến

Khi changeset đã chạy ở bất kỳ môi trường dùng chung nào, không sửa nội dung để thay đổi schema. Tạo changeset mới với ID/author phù hợp. Nếu cần di chuyển file, giữ định danh logical path có chủ đích và thử trên database có history.

Với view/procedure có thể thay thế toàn bộ định nghĩa, cân nhắc runOnChange khi phù hợp với semantics và version Liquibase. Không dùng runOnChange cho mọi DDL hoặc data migration; mỗi lần nội dung đổi có thể thực thi lại changeset và gây tác động ngoài dự kiến.

### 11.2. Dùng precondition để phát hiện điều kiện trước khi thay đổi

Precondition nên kiểm tra điều kiện thật sự cần cho changeset, ví dụ bảng/cột tồn tại, DBMS phù hợp hoặc dữ liệu không còn duplicate. Chọn HALT, WARN, CONTINUE hay MARK_RAN theo ý nghĩa nghiệp vụ. Đặc biệt, MARK_RAN có thể ghi nhận changeset mà không chạy change; chỉ dùng khi trạng thái object đã được xác minh và hậu kiểm chứng minh kết quả tương đương.

### 11.3. Kiểm tra SQL và dữ liệu trước production

Pipeline nên:

1. Dùng artifact bất biến và version Liquibase/extension/driver đã pin.
2. Chạy validate và status với đúng context/label/parameters.
3. Sinh update-sql cho DBMS mục tiêu.
4. Test database trống và database có history/dataset đại diện.
5. Kiểm tra changeset có DDL không transactional, lock dài hoặc thao tác phá hủy.
6. Chạy migration bằng đúng principal và quyền production-like.
7. Chỉ cho một migration job cập nhật một target trong mỗi đợt deploy.
8. Lưu log, SQL preview và bằng chứng hậu kiểm.

### 11.4. Thiết lập cảnh báo và runbook

Theo dõi thời gian giữ lock, thời gian chạy changeset, số changeset pending, lỗi checksum, precondition failure, SQL exception và migration timeout. Runbook phải nêu rõ ai xác minh runner, ai kiểm tra database session, ai có quyền release lock và ai phê duyệt forward-fix.

## 12. Bài tập tổng hợp

Thực hiện trên database lab mới hoặc khôi phục lại snapshot ban đầu. Ghi bằng chứng cho từng bước:

### Bài tập 1 — Checksum

1. Chạy changelog ban đầu thành công.
2. Lưu checksum của changeset create-customer.
3. Thay đổi một thuộc tính của changeset đã chạy.
4. Chạy validate/status và ghi nhận lỗi.
5. Khôi phục source hoặc thêm changeset mới để thể hiện thay đổi.
6. Chạy update-sql, update và đối chiếu history.

**Đạt khi:** giải thích được checksum mismatch; changeset cũ không bị chạy lại; thay đổi schema được biểu diễn bằng changeset mới nếu cần.

### Bài tập 2 — Lock

1. Chạy runner A trên database lab.
2. Trong khi A còn hoạt động, chạy runner B.
3. Ghi log chờ lock và trạng thái lock row.
4. Xác minh process/session của A.
5. Để A kết thúc bình thường rồi xác nhận B có thể tiếp tục theo cấu hình.
6. Trong một lần thử riêng, mô phỏng job lab kết thúc bất thường và kiểm tra quy trình xác nhận lock mồ côi trước release-locks.

**Đạt khi:** không release lock của runner còn hoạt động; chỉ dùng release-locks sau khi có bằng chứng runner đã kết thúc; không sửa trực tiếp lock row.

### Bài tập 3 — Changeset lỗi do dữ liệu

1. Chèn hai hàng có email trùng.
2. Chạy changeset tạo unique constraint với precondition HALT.
3. Xác nhận migration dừng và constraint chưa được tạo.
4. Sửa dữ liệu theo quy tắc lab.
5. Xác nhận precondition đạt rồi chạy lại.
6. Kiểm tra constraint, dữ liệu và DATABASECHANGELOG.

**Đạt khi:** phân biệt được precondition failure với SQL execution failure và không dùng MARK_RAN để che dữ liệu vi phạm.

### Bài tập 4 — DDL thực thi một phần

1. Trên database lab dùng riêng, thiết kế changeset có hai thao tác DDL mà thao tác sau cố tình lỗi.
2. Chạy migration và lưu log đầy đủ.
3. Kiểm tra history, catalog và object sau lỗi.
4. Ghi rõ DBMS có rollback DDL trong tình huống đó hay không.
5. Lập phương án cleanup chỉ cho lab hoặc forward-fix có review.
6. Tạo database lab mới và chạy lại quy trình sau khi sửa.

**Đạt khi:** không giả định row history vắng mặt nghĩa là database chưa thay đổi; phương án phục hồi dựa trên object thực tế và transaction semantics.

## 13. Mẫu biên bản điều tra sự cố

Có thể dùng mẫu sau cho mỗi lần migration lỗi:

| Trường | Nội dung |
|---|---|
| Incident ID | Mã sự cố |
| Environment/target | Môi trường, DBMS, database/catalog, schema |
| Release | Commit, artifact digest, build/job ID |
| Toolchain | Java, Spring Boot, Liquibase, extension, JDBC driver |
| Changelog | Master file, changeset ID/author/path |
| Error category | Checksum / lock / precondition / SQL / permission / timeout |
| Evidence | Log, SQL preview, history, lock row, catalog và data checks |
| Actual state | Changeset đã ghi nhận chưa; object/data đã thay đổi chưa |
| Root cause | Nguyên nhân được chứng minh |
| Recovery | Restore source / new changeset / release lock / data fix / forward-fix |
| Verification | History, schema, data, permission, application health |
| Prevention | CI test, alert, runbook hoặc review rule |
| Approval | Người chịu trách nhiệm và phê duyệt |

Không ghi credential hoặc dữ liệu cá nhân không cần thiết vào biên bản. Nếu đính kèm SQL/log, mask secret và giới hạn quyền truy cập.

## 14. Checklist trước khi kết thúc xử lý

- [ ] Đã xác định chính xác database, schema metadata và migration runner.
- [ ] Đã lưu commit/artifact, Liquibase version, driver và log.
- [ ] Đã phân loại lỗi là checksum, lock, precondition, SQL, quyền hay timeout.
- [ ] Đã đối chiếu changeset ID/author/filename và row DATABASECHANGELOG.
- [ ] Đã kiểm tra lock owner/process/session trước khi release.
- [ ] Đã kiểm tra object và dữ liệu thực tế, kể cả DDL có thể đã chạy một phần.
- [ ] Không sửa/xóa history row hoặc lock row bằng SQL tùy tiện.
- [ ] Không dùng clear-checksums hoặc MARK_RAN nếu chưa có căn cứ và phê duyệt.
- [ ] Changeset đã triển khai được giữ nguyên; thay đổi mới có changeset mới.
- [ ] Đã chạy validate, status và update-sql với đúng cấu hình.
- [ ] Đã kiểm tra schema, dữ liệu, constraint, quyền và ứng dụng sau phục hồi.
- [ ] Đã ghi lại nguyên nhân, quyết định, bằng chứng và biện pháp phòng ngừa.

**Kết luận:** điều tra checksum, lock và changeset lỗi bắt đầu bằng việc xác định lịch sử Liquibase, runner đang hoạt động và trạng thái schema/data thực tế. Checksum mismatch cần đối chiếu source đã phát hành; lock chỉ được giải phóng sau khi xác nhận không còn runner sở hữu; changeset thất bại phải được kiểm tra transaction boundary và DDL đã thực thi một phần trước khi retry. Khi dùng database lab để tái hiện, lưu bằng chứng, kiểm tra hậu phục hồi và bổ sung regression check vào CI/CD, DATABASE_SCHEMA_MIGRATION_LIQUIBASE có thể xử lý sự cố có kiểm soát mà vẫn bảo toàn lịch sử migration.
