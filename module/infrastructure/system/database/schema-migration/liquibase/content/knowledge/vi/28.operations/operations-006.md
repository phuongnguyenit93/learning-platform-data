# Đánh giá hiệu năng changelog lớn và tiền điều kiện tốn kém

Khi một dự án Liquibase phát triển qua nhiều năm, changelog có thể chứa hàng trăm hoặc hàng nghìn changeset, nhiều tầng include, SQL script, dữ liệu seed và precondition để bảo vệ từng thay đổi. Một lệnh update từng hoàn tất trong vài giây có thể dần kéo dài, tiêu tốn connection, giữ lock lâu và làm chậm quá trình khởi động ứng dụng. Không phải lúc nào nguyên nhân cũng là câu DDL/DML chính: thời gian đọc changelog, kiểm tra checksum, tạo snapshot metadata, chạy precondition hoặc chờ khóa cũng có thể chiếm phần đáng kể.

Tối ưu đúng cần đo được **thời gian của từng pha**, tìm changeset hoặc precondition có chi phí cao, rồi thay đổi cách tổ chức và kiểm tra mà vẫn giữ nguyên tính an toàn. Bỏ precondition chỉ để chạy nhanh có thể khiến migration áp dụng lên sai schema hoặc bỏ qua dữ liệu chưa đạt điều kiện. Chia changelog thành nhiều file cũng không tự động làm update nhanh hơn nếu tổng số changeset và các truy vấn kiểm tra vẫn như cũ.

Bài thuộc chương **Vận hành** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Nội dung tập trung vào cách đánh giá hiệu năng changelog lớn, nhận diện precondition tốn kém, tối ưu việc đọc metadata và SQL kiểm tra, đồng thời bảo toàn tính đúng đắn của migration.

## 1. Phân rã thời gian một lần chạy Liquibase

Thời gian tổng của một lần update có thể gồm nhiều thành phần:

\[
T_{run} =
T_{startup} +
T_{resource} +
T_{validation} +
T_{lock} +
T_{precondition} +
T_{changes} +
T_{history}
\]

Đây là mô hình phân tích để đặt câu hỏi, không phải bộ đếm mà mọi phiên bản Liquibase đều xuất ra sẵn. Trong thực tế, một số pha có thể chồng lấn hoặc được thực hiện trong cùng một thao tác.

| Pha | Công việc | Dấu hiệu chậm |
|---|---|---|
| Startup | Khởi tạo JVM, Spring context, DataSource, driver | Ứng dụng khởi động chậm dù chưa có SQL migration |
| Resource loading | Tìm changelog gốc, include, SQL và CSV | Nhiều file, đường dẫn từ xa hoặc tài nguyên thiếu |
| Parse/validation | Đọc cấu trúc changelog, kiểm tra định dạng và định danh | Changelog lớn, include lồng sâu, nhiều changeset |
| Checksum/history | Đối chiếu changeset với DATABASECHANGELOG | Nhiều changeset, history lớn hoặc truy cập DB chậm |
| Lock wait | Chờ DATABASECHANGELOGLOCK | Có tiến trình Liquibase khác đang chạy |
| Preconditions | Kiểm tra DBMS, schema, metadata hoặc dữ liệu | Snapshot lớn, truy vấn SQL tốn kém, lặp lại cùng điều kiện |
| Changes | Thực thi DDL/DML | SQL chậm, lock DBMS, I/O, backfill lớn |
| History/finalization | Ghi nhận changeset và giải phóng lock | Transaction, kết nối hoặc DBMS đang quá tải |

Đừng bắt đầu tối ưu bằng cách thay đổi changelog khi chưa biết thời gian nằm ở pha nào. Nếu run chờ lock 90 giây và thực thi SQL 5 giây, việc viết lại precondition không giải quyết được nguyên nhân chính.

## 2. Đo baseline trước khi tối ưu

Baseline là số liệu tham chiếu để so sánh sau thay đổi. Nên ghi lại tối thiểu:

- Liquibase version, Java version, JDBC driver và DBMS version.
- Changelog root, số changeset được chọn và số changeset pending.
- Target database/schema và context/label/DBMS filter.
- Thời gian bắt đầu/kết thúc, tổng duration.
- Thời gian chờ lock nếu có thể quan sát.
- Changeset chậm nhất và thời gian thực thi.
- Precondition hoặc SQL check có chi phí đáng kể.
- Tải DBMS, số connection và các session đang block.
- Kết quả sau update: schema, dữ liệu và DATABASECHANGELOG.

So sánh các lần chạy trên cùng điều kiện: cùng loại máy, DBMS version, lượng dữ liệu, cấu hình connection, artifact và trạng thái history. Nếu một lần chạy trên database trống còn lần khác trên database production-like có hàng triệu dòng, chênh lệch thời gian không thể được quy cho thay đổi changelog một cách đáng tin cậy.

### 2.1. Dùng percentile thay vì chỉ nhìn một lần chạy

Một lần chạy nhanh hoặc chậm bất thường chưa đủ để thay đổi ngưỡng. Với môi trường có nhiều lần triển khai, có thể theo dõi median, p90 và p95 của thời gian run hoặc changeset. Ghi riêng thời gian chờ lock và thời gian SQL để không trộn hai nguyên nhân.

Ví dụ:

| Chỉ số | Trước tối ưu | Sau tối ưu |
|---|---:|---:|
| Tổng duration median | 82 giây | 41 giây |
| Lock wait median | 2 giây | 2 giây |
| Preconditions median | 31 giây | 8 giây |
| Changes execution median | 38 giây | 27 giây |
| Post-check median | 11 giây | 4 giây |

Các con số chỉ minh họa cách phân tích. Khi thời gian precondition giảm mạnh còn lock wait không đổi, có bằng chứng rằng thay đổi đã tác động đúng pha.

## 3. Changelog lớn gây chi phí ở đâu?

Một changelog lớn có thể làm tăng chi phí theo nhiều cách:

- Nhiều file phải được tìm và đọc.
- Nhiều tầng include khiến việc truy vết cấu trúc khó hơn.
- IncludeAll quét thư mục chứa nhiều tài nguyên.
- Có nhiều changeset cần được phân tích và đối chiếu với lịch sử.
- Nhiều precondition phải đánh giá.
- Nhiều changeset có checksum hoặc filter riêng.
- Nhiều tài nguyên SQL/CSV cần được nạp.
- Một số changeset chạy lại theo cấu hình runAlways hoặc runOnChange.

Không phải tất cả chi phí đều tăng tuyến tính với số file. DBMS, resource accessor, cache, filesystem/JAR, kích thước metadata và loại precondition đều ảnh hưởng. Cần đo trên phiên bản Liquibase và kiến trúc thực tế.

### 3.1. Số file không đồng nghĩa số lần truy vấn database

Chia một changelog thành nhiều file giúp tổ chức và review, nhưng không nhất thiết giảm số changeset hoặc số lần Liquibase phải đọc history. Nếu 1.000 changeset vẫn được include và cần kiểm tra, chi phí phân tích và đối chiếu vẫn tồn tại.

Ngược lại, một file khổng lồ cũng không phải lúc nào nhanh hơn: nó khó review, dễ xung đột, khó chia ownership và dễ tạo một changeset quá lớn. Mục tiêu là cấu trúc dễ hiểu, ổn định và đo được, không phải tối thiểu số file bằng mọi giá.

## 4. Tổ chức include và includeAll có kiểm soát

Include tường minh:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-orders.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-indexes.yaml
      relativeToChangelogFile: true
~~~

IncludeAll:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: changes
      relativeToChangelogFile: true
~~~

Include tường minh giúp nhìn thấy thứ tự và danh sách file ngay trong master. IncludeAll giảm công sức cập nhật master khi thêm file, nhưng cần kiểm soát chặt thư mục được quét, quy tắc sắp xếp và loại file nằm trong đó.

Khuyến nghị:

- Giữ changelog root gọn, có cấu trúc theo domain hoặc giai đoạn phát hành.
- Không đặt file SQL không phải changelog trong thư mục mà includeAll quét nếu cấu hình có thể nhận nhầm.
- Không trộn tài liệu, backup, file tạm hoặc output generated vào thư mục includeAll.
- Dùng quy tắc tên file nhất quán và thứ tự xác định.
- Tránh cây include quá sâu khiến khó biết changeset nào được nạp.
- Giữ đường dẫn ổn định sau khi changeset đã triển khai.
- Đo thời gian parse/resource loading trước và sau khi tái cấu trúc.

Nếu thư mục có hàng nghìn file và nhiều file không liên quan, thu hẹp phạm vi includeAll có thể giảm việc quét tài nguyên. Tuy nhiên, thay đổi cách include có thể ảnh hưởng thứ tự và identity changeset; cần kiểm thử history trước khi triển khai.

## 5. Hiểu chi phí của precondition

Precondition là điều kiện được đánh giá trước khi Liquibase thực thi một changelog hoặc changeset. Chúng bảo vệ migration khỏi chạy trong trạng thái không phù hợp, nhưng bản thân việc kiểm tra cũng có chi phí.

Một số precondition thường dùng:

- dbms và runningAs.
- tableExists, columnExists, viewExists.
- sequenceExists, indexExists.
- primaryKeyExists, foreignKeyConstraintExists, uniqueConstraintExists.
- changeSetExecuted và changeLogPropertyDefined.
- sqlCheck.
- Custom precondition.

Chi phí phụ thuộc cách từng precondition được thực hiện, DBMS, driver, schema scope, số đối tượng và Liquibase version. Một số điều kiện có thể kiểm tra metadata đơn giản; một số điều kiện cần lấy snapshot hoặc truy vấn catalog rộng hơn. Không nên giả định mọi precondition đều chỉ là một câu SELECT nhỏ.

### 5.1. Snapshot metadata có thể đắt

Các điều kiện kiểm tra đối tượng schema có thể cần Liquibase thu thập metadata để xác định bảng, cột, index hoặc constraint. Trên database có nhiều schema và hàng chục nghìn đối tượng, snapshot có thể mất thời gian và sử dụng nhiều bộ nhớ.

Nếu nhiều changeset liên tục yêu cầu các điều kiện schema tương tự, chi phí snapshot/metadata có thể lặp lại hoặc trở thành phần đáng kể của update. Hành vi cụ thể phụ thuộc loại precondition và phiên bản; hãy dùng log, profiling hoặc truy vấn DBMS để xác minh thay vì suy đoán.

Không nên xóa tableExists hoặc columnExists chỉ vì chúng chậm. Hãy xác định chúng đang bảo vệ điều gì, có thể thay bằng kiểm tra hẹp hơn không, và liệu điều kiện đó có thực sự cần đánh giá ở từng changeset hay không.

## 6. Phân biệt precondition cấp changelog và cấp changeset

Precondition cấp changelog bảo vệ toàn bộ changelog. Nó phù hợp với điều kiện chung cho cả lần triển khai, ví dụ yêu cầu DBMS đúng hoặc môi trường đã được chuẩn bị.

Precondition cấp changeset bảo vệ một thay đổi cụ thể. Nó phù hợp khi chỉ một changeset cần bảng, cột hoặc trạng thái dữ liệu riêng.

Ví dụ điều kiện chung:

~~~yaml
databaseChangeLog:
  - preConditions:
      - onFail: HALT
      - dbms:
          type: postgresql

  - changeSet:
      id: 001-create-customer
      author: database-team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Ví dụ điều kiện riêng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-status
      author: database-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
~~~

Không chuyển mọi precondition lên cấp changelog chỉ để giảm số lần đánh giá. Điều kiện chung phải thật sự đúng cho toàn bộ changeset. Nếu một bảng chỉ cần cho một changeset, đặt điều kiện ở phạm vi phù hợp giúp thông báo lỗi và ý nghĩa an toàn rõ ràng hơn.

## 7. Tránh lặp lại cùng một kiểm tra tốn kém

Giả sử 40 changeset đều kiểm tra cùng một bảng staging hoặc cùng một trạng thái migration. Nếu mỗi changeset thực hiện một SQL check phức tạp, tổng chi phí có thể đáng kể.

Trước khi thay đổi, hãy hỏi:

1. Điều kiện này có cần được đánh giá lại trước từng changeset không?
2. Có thể kiểm tra một lần ở cấp changelog không?
3. Có thể biểu diễn bằng precondition metadata chuẩn thay vì truy vấn dữ liệu rộng không?
4. Có thể thiết kế một changeset chuẩn bị trạng thái rồi các changeset sau dựa vào thứ tự đó không?
5. Có cần kiểm tra lại vì trạng thái có thể thay đổi giữa các changeset không?

Nếu điều kiện là invariant của toàn bộ release và không thay đổi trong lúc migration, kiểm tra một lần ở cấp changelog có thể hợp lý. Nếu điều kiện bảo vệ một thao tác cụ thể trước rủi ro dữ liệu, giữ precondition tại changeset đó.

Không dựa vào giả định rằng Liquibase tự cache mọi precondition giữa các changeset. Hành vi cache/snapshot tùy implementation và version. Hãy đo số truy vấn thực tế và giữ thiết kế đúng ngay cả khi cache không tồn tại.

## 8. Thiết kế sqlCheck hiệu quả

sqlCheck hữu ích khi cần kiểm tra điều kiện nghiệp vụ hoặc dữ liệu mà precondition metadata chuẩn không biểu diễn được.

Ví dụ kiểm tra còn bản ghi có email NULL trước khi thêm NOT NULL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-require-customer-email
      author: database-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer
              WHERE email IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: email
            columnDataType: VARCHAR(255)
~~~

Truy vấn COUNT(*) có thể phải đọc nhiều dòng tùy DBMS, index và điều kiện. Trên bảng lớn, một truy vấn EXISTS thường có thể dừng khi tìm thấy bản ghi đầu tiên:

~~~sql
SELECT CASE
         WHEN EXISTS (
           SELECT 1
           FROM customer
           WHERE email IS NULL
         )
         THEN 1
         ELSE 0
       END;
~~~

Precondition có thể đặt expectedResult là 0 nếu không có dòng vi phạm. Cần xác minh kiểu kết quả và cách driver trả về giá trị trên DBMS thực tế.

Các nguyên tắc tối ưu:

- Chỉ chọn những cột cần thiết; tránh SELECT *.
- Tránh COUNT(*) nếu chỉ cần biết có ít nhất một dòng vi phạm.
- Dùng điều kiện lọc có thể tận dụng index khi phù hợp.
- Giới hạn phạm vi schema/table.
- Không chạy truy vấn quét toàn bộ bảng nhiều lần cho cùng một invariant.
- Xem execution plan trên dữ liệu đại diện.
- Đo cả thời gian và tác động I/O/lock.
- Không thêm LIMIT tùy tiện nếu nó làm sai ngữ nghĩa điều kiện.

Nếu cần đếm chính xác số dòng vi phạm để báo cáo, COUNT(*) có thể là lựa chọn đúng. Nhưng nếu mục tiêu chỉ là HALT khi có một dòng, EXISTS thường thể hiện ý định rõ hơn và có cơ hội dừng sớm.

## 9. Tránh kiểm tra toàn bộ dữ liệu nếu chỉ cần kiểm tra điều kiện cần thiết

Một precondition có thể vô tình làm migration chậm vì thực hiện kiểm tra trên toàn bộ bảng lớn.

Ví dụ không hiệu quả cho mục tiêu “có tồn tại dòng cần xử lý không”:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PENDING';
~~~

Nếu bảng có hàng trăm triệu dòng và không có index phù hợp, truy vấn có thể tốn nhiều I/O. Nếu chỉ cần biết có ít nhất một dòng, dùng EXISTS. Nếu cần kiểm tra dữ liệu trong một partition hoặc tenant, giới hạn phạm vi đó.

Tuy nhiên, tối ưu truy vấn không được làm yếu điều kiện. Ví dụ kiểm tra một sample 100 dòng không chứng minh toàn bộ bảng không có dữ liệu vi phạm. Dùng sample chỉ khi nghiệp vụ cho phép và có một cơ chế kiểm tra đầy đủ khác.

## 10. Chọn precondition chuẩn trước custom SQL

Nếu mục tiêu là kiểm tra một đối tượng schema, precondition chuẩn thường dễ đọc và ít phụ thuộc DBMS hơn SQL tùy chỉnh.

Ví dụ:

~~~yaml
preConditions:
  - onFail: HALT
  - columnExists:
      tableName: customer
      columnName: email
~~~

Điều này diễn đạt ý định trực tiếp hơn một SQL query vào catalog PostgreSQL. Nhưng nếu precondition chuẩn cần snapshot metadata rộng trên database rất lớn, SQL catalog query được giới hạn đúng schema có thể rẻ hơn. Quyết định cần đo trên DBMS và Liquibase version cụ thể.

Đừng thay mọi precondition chuẩn bằng SQL catalog riêng chỉ vì một lần benchmark nhanh hơn. SQL catalog phụ thuộc DBMS, quyền, phiên bản và cách đặt identifier; chi phí bảo trì và rủi ro sai ngữ nghĩa cũng cần tính vào.

## 11. Đặt thứ tự điều kiện có chủ đích

Trong một nhóm AND/OR, có thể sắp xếp điều kiện dễ đọc theo mức độ đơn giản, nhưng không nên dựa vào short-circuit evaluation như một tối ưu hiệu năng nếu hành vi đó chưa được xác minh cho phiên bản Liquibase đang dùng.

Ví dụ một changeset cần DBMS PostgreSQL và bảng customer tồn tại:

~~~yaml
preConditions:
  - onFail: HALT
  - dbms:
      type: postgresql
  - tableExists:
      tableName: customer
~~~

Điều kiện dbms có thể là điều kiện rẻ, nhưng hãy kiểm tra cách Liquibase đánh giá và log thực tế. Không dùng thứ tự điều kiện để che giấu lỗi ở điều kiện sau. Mỗi precondition phải độc lập đúng và thông báo lỗi phải giúp người vận hành hiểu vì sao changeset không được chạy.

## 12. onFail và onError: chọn hành vi thay vì né chi phí

Precondition có thể thất bại vì điều kiện không đạt hoặc vì quá trình đánh giá gặp lỗi. Đây là hai trường hợp khác nhau.

- onFail xác định cách xử lý khi precondition được đánh giá thành công nhưng kết quả điều kiện không đạt.
- onError xác định cách xử lý khi việc đánh giá precondition phát sinh lỗi.

Các chính sách thường gặp gồm HALT, WARN, CONTINUE và MARK_RAN tùy scope/phiên bản hỗ trợ. Hãy kiểm tra tài liệu Liquibase version đang dùng trước khi chọn giá trị.

| Chính sách | Ý nghĩa vận hành khái quát | Rủi ro |
|---|---|---|
| HALT | Dừng khi điều kiện không đạt/lỗi theo cấu hình | Triển khai bị dừng, cần xử lý nguyên nhân |
| WARN | Ghi cảnh báo và tiếp tục theo hành vi hỗ trợ | Có thể tiếp tục trong trạng thái không mong muốn |
| CONTINUE | Bỏ qua changeset hiện tại trong lần chạy và tiếp tục | Thay đổi cần thiết có thể chưa được áp dụng |
| MARK_RAN | Ghi nhận changeset là đã chạy mà không thực thi change | Lịch sử có thể nói đã chạy trong khi schema/data thiếu |

Không đổi HALT thành WARN hoặc MARK_RAN chỉ để giảm thời gian hay làm pipeline xanh. Một precondition tốn kém vẫn có thể đang bảo vệ dữ liệu quan trọng. Hãy tối ưu truy vấn hoặc thiết kế lại phạm vi kiểm tra, rồi giữ chính sách an toàn phù hợp.

## 13. Dùng context, label và dbms filter đúng mục tiêu

Context và label giúp chọn tập changeset phù hợp cho một môi trường hoặc đợt triển khai. Thuộc tính dbms giới hạn changeset cho hệ quản trị tương ứng.

Các bộ lọc này có thể giảm số changeset cần thực thi hoặc kiểm tra trong một lần chạy. Tuy nhiên, chúng không phải cách che giấu thay đổi chưa hoàn tất và không thay thế precondition.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-seed-demo-data
      author: database-team
      context: dev
      changes:
        - insert:
            tableName: demo_category
            columns:
              - column:
                  name: name
                  value: Example
~~~

Trước khi tối ưu bằng context/label, xác minh pipeline production truyền đúng filter. Một changeset quan trọng bị loại khỏi context có thể không chạy mà không phải là lỗi hiệu năng.

## 14. Chia nhỏ data migration thay vì một truy vấn quá lớn

Một changeset backfill hàng triệu dòng có thể chiếm phần lớn thời gian, giữ transaction lâu và tạo tải lớn. Đây là vấn đề thực thi SQL chứ không phải parse changelog.

Các chiến lược:

- Chia backfill thành batch có giới hạn.
- Xử lý theo khóa hoặc khoảng ID ổn định.
- Ghi nhận tiến độ để có thể tiếp tục an toàn.
- Tránh cập nhật lại những dòng đã hoàn tất.
- Kiểm tra index phục vụ điều kiện lọc.
- Giới hạn lock và thời gian transaction theo DBMS.
- Tách bước thêm cột, backfill, xác minh và thêm constraint.
- Theo dõi WAL/redo, replication lag và dung lượng log.

Ví dụ truy vấn theo batch PostgreSQL chỉ mang tính minh họa:

~~~sql
WITH batch AS (
    SELECT id
    FROM customer
    WHERE email_normalized IS NULL
    ORDER BY id
    LIMIT 5000
)
UPDATE customer c
SET email_normalized = lower(c.email)
FROM batch
WHERE c.id = batch.id;
~~~

Đây mới là một batch; cần cơ chế lặp có kiểm soát và điều kiện dừng. Không giả định một changeset SQL tự lặp đến khi hết dữ liệu. Có thể dùng job migration chuyên biệt, stored procedure hoặc nhiều changeset theo giai đoạn, tùy yêu cầu audit và khả năng resume.

Precondition nên kiểm tra trạng thái cần thiết trước batch hoặc trước giai đoạn, không chạy một truy vấn toàn bảng nặng trước từng batch nếu điều kiện đó không thay đổi.

## 15. Tối ưu thứ tự changeset và phụ thuộc

Changelog nên đặt những thay đổi nhỏ, độc lập và có thể kiểm chứng trước những thao tác nặng khi dependency cho phép. Nhưng không được đảo thứ tự chỉ vì benchmark cho thấy một trình tự nhanh hơn.

Ví dụ expand–migrate–contract:

1. Thêm cột mới nullable.
2. Triển khai ứng dụng có thể đọc/ghi cả cột cũ và mới.
3. Backfill dữ liệu theo batch.
4. Kiểm tra không còn giá trị thiếu.
5. Thêm constraint hoặc index phù hợp.
6. Chuyển ứng dụng sang cột mới.
7. Xóa cột cũ trong một release sau khi đã xác nhận không còn consumer.

Cách chia giai đoạn giúp tránh một changeset dài giữ lock quá lâu và cho phép kiểm soát từng bước. Tuy nhiên, mỗi giai đoạn phải có history và tiêu chí hoàn tất rõ; không để ứng dụng đọc dữ liệu chưa được backfill.

## 16. Kiểm tra index và execution plan của precondition

Một sqlCheck có điều kiện WHERE có thể rất chậm nếu cột lọc không có index hoặc thống kê DBMS đã cũ.

Trên PostgreSQL, có thể dùng EXPLAIN để xem kế hoạch:

~~~sql
EXPLAIN
SELECT 1
FROM customer
WHERE email IS NULL;
~~~

EXPLAIN không thực thi truy vấn theo cách EXPLAIN ANALYZE thực thi; nó cho biết kế hoạch dự kiến dựa trên thống kê. Không dùng EXPLAIN ANALYZE một cách tùy tiện trên truy vấn thay đổi dữ liệu hoặc bảng production có tải cao.

Cần cân nhắc:

- Index có hỗ trợ điều kiện lọc không?
- Predicate có thể dùng index không?
- Có implicit cast làm mất khả năng index seek không?
- Thống kê có đủ mới không?
- Truy vấn có scan quá nhiều partition không?
- Kết quả có khác khi dữ liệu lớn hơn nhiều không?

Đừng tạo index chỉ để làm một precondition nhanh hơn nếu index đó không có giá trị vận hành hoặc tạo thêm chi phí migration lớn. Có thể thay đổi cách kiểm tra hoặc dùng một trạng thái đã được kiểm chứng.

## 17. Changelog lớn và checksum/history

Liquibase phải đối chiếu changeset với lịch sử trong DATABASECHANGELOG. Khi changelog lớn, số lượng changeset và cách tổ chức file có thể làm tăng thời gian validation/history lookup.

Các nguyên tắc:

- Dùng ID, author và path ổn định.
- Không sửa changeset đã triển khai để “tối ưu” nội dung cũ.
- Thêm changeset mới cho thay đổi tiếp theo.
- Tránh runAlways/runOnChange nếu không thực sự cần.
- Đảm bảo index/primary key phù hợp trên bảng history theo schema do Liquibase quản lý; không tự ý sửa cấu trúc bảng nội bộ.
- Theo dõi thời gian validate/history riêng nếu có instrumentation.
- Không chạy clear-checksums như một biện pháp tăng tốc.

Clear-checksums không làm giảm số changeset cần xử lý theo cách có ý nghĩa và có thể làm thay đổi trạng thái checksum cần được điều tra. Không dùng nó để che checksum mismatch hoặc sửa nội dung changeset cũ.

## 18. Không chạy nhiều Liquibase update song song trên cùng history/lock

DATABASECHANGELOGLOCK điều phối các tiến trình Liquibase cùng phạm vi lock. Chạy nhiều update song song trên cùng database và cùng bảng lock thường không làm migration nhanh hơn; tiến trình sau có thể chỉ chờ.

Nếu pipeline chạy đồng thời trên nhiều database độc lập, có thể song song theo target khi tài nguyên cho phép. Nhưng trong một database, phải tính tới lock, DBMS workload và dependency.

Khi thấy run chậm, phân biệt:

- Chờ DATABASECHANGELOGLOCK.
- Chờ lock nội bộ DBMS.
- Chờ connection pool.
- Đang thực thi SQL.
- Đang tạo snapshot metadata.
- Đang ghi history.

Không giải phóng lock để “tăng tốc”. Chỉ xử lý stale lock sau khi xác minh tiến trình holder đã dừng và database ở trạng thái an toàn.

## 19. Tối ưu startup Spring Boot khi Liquibase chạy lúc khởi động

Nếu Spring Boot tự chạy Liquibase lúc startup, thời gian migration nằm trong thời gian ứng dụng sẵn sàng nhận traffic. Một changelog lớn hoặc precondition chậm có thể khiến readiness kéo dài và orchestration restart pod.

Cần đo riêng:

- JVM startup.
- Datasource initialization.
- Liquibase initialization.
- Lock wait.
- Preconditions và SQL changes.
- ApplicationContext completion.
- Readiness transition.

Với migration dài, cân nhắc chạy Liquibase bằng job triển khai độc lập trước khi rollout application. Khi đó ứng dụng không phải tự chạy migration trong từng replica. Nếu chọn mô hình này, pipeline phải bảo đảm migration job thành công trước khi ứng dụng mới nhận traffic.

Không tắt Liquibase auto-run mà không có bước migration thay thế. Cần xác định rõ ai sở hữu migration, quyền DDL nằm ở đâu và cách ứng dụng biết schema đã sẵn sàng.

## 20. Theo dõi hiệu năng trên nhiều môi trường

Cùng changelog có thể chạy nhanh ở dev nhưng chậm ở production vì lượng dữ liệu, số schema, tải, index, lock và quyền khác nhau.

Mỗi lần benchmark cần lưu:

| Trường | Mục đích |
|---|---|
| target/environment | Biết database nào được đo |
| DBMS/version | Giải thích khác biệt engine |
| Liquibase/driver version | Đảm bảo runtime so sánh được |
| changelog artifact | Biết nội dung migration |
| context/label/DBMS filter | Biết changeset nào được chọn |
| row count/data volume | Đặt kết quả trong bối cảnh dữ liệu |
| run duration | Đo tổng |
| lock wait | Phân biệt chờ khóa |
| precondition duration | Tìm điều kiện tốn kém |
| changeset duration | Tìm SQL chậm |
| post-check duration | Biết chi phí xác minh |

Không dùng số liệu production có dữ liệu nhạy cảm trong dashboard công khai. Chỉ thu thập metadata vận hành cần thiết và kiểm soát quyền truy cập.

## 21. Những tối ưu nguy hiểm cần tránh

| Cách làm | Vì sao nguy hiểm | Cách thay thế |
|---|---|---|
| Xóa precondition vì chậm | Migration có thể chạy trên schema sai | Tối ưu truy vấn hoặc phạm vi điều kiện |
| Đổi HALT thành WARN | Pipeline tiếp tục khi invariant không đạt | Giữ chính sách an toàn, sửa nguyên nhân |
| Dùng MARK_RAN để bỏ qua changeset | History ghi đã chạy dù change không được thực thi | Baseline có bằng chứng hoặc changeset sửa chữa |
| Thay COUNT bằng sample | Có thể bỏ sót dữ liệu vi phạm | EXISTS hoặc kiểm tra đầy đủ đúng predicate |
| Bỏ kiểm tra checksum | Che giấu thay đổi changeset đã triển khai | Điều tra checksum và phát hành changeset mới |
| Chạy update song song cùng DB | Tranh lock, tăng tải, không tăng throughput | Điều phối một runner theo database |
| Gộp mọi migration vào một changeset | Transaction/lock dài, khó phục hồi | Chia theo bước có thể kiểm chứng |
| Thay include bằng includeAll tùy tiện | Có thể đổi thứ tự hoặc nạp file ngoài ý muốn | Quy định thư mục, comparator và test |
| Tạo index để phục vụ một precondition duy nhất | Tốn chi phí ghi và dung lượng | Xem lại predicate hoặc kiểm tra metadata |
| Tăng timeout vô hạn | Che dấu tiến trình bị block | Đặt ngưỡng, cảnh báo và runbook |

Tối ưu phải bảo toàn invariant dữ liệu. Một migration nhanh nhưng bỏ qua điều kiện cần thiết là migration không an toàn.

## 22. Quy trình benchmark và tối ưu có kiểm chứng

Một vòng tối ưu nên có thể tái tạo:

1. Chọn database test có kích thước và phân bố dữ liệu đại diện.
2. Pin Liquibase, JDBC driver và DBMS version.
3. Ghi nhận changelog artifact, filter và target identity.
4. Chạy baseline nhiều lần, thu thập tổng duration, lock wait và từng pha có thể đo.
5. Xác định một bottleneck cụ thể: parse, snapshot, sqlCheck, DDL, backfill hay lock.
6. Thay đổi một yếu tố tại một thời điểm.
7. Chạy lại cùng kịch bản và so sánh.
8. Xác minh schema, dữ liệu, history và rollback không bị suy giảm.
9. Kiểm tra trên database mới và database upgrade có lịch sử.
10. Ghi lại kết quả, rủi ro và quyết định đưa tối ưu vào release.

Không thay nhiều thứ cùng lúc như chuyển includeAll, xóa precondition, đổi context và gộp changeset; nếu kết quả nhanh hơn sẽ khó biết nguyên nhân và khó chứng minh tính an toàn.

## 23. Công cụ và câu lệnh hỗ trợ chẩn đoán

Các lệnh Liquibase thường dùng trong quá trình phân tích:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase list-locks
~~~

Ý nghĩa:

- validate kiểm tra một số lỗi cấu trúc/configuration của changelog.
- status cho biết changeset còn chờ theo cấu hình hiện tại.
- update-sql hiển thị SQL dự kiến cho update để review.
- update thực thi changeset được chọn.
- list-locks hỗ trợ xem trạng thái lock trong các phiên bản có lệnh này.

Cú pháp và hành vi phụ thuộc Liquibase version. Các lệnh trên không tự cung cấp một báo cáo duration chi tiết cho mọi precondition. Để đo sâu, kết hợp log timestamp, pipeline timing, DBMS session/statement statistics và instrumentation phù hợp.

Trên PostgreSQL, có thể quan sát query đang chạy:

~~~sql
SELECT pid, application_name, state,
       wait_event_type, wait_event,
       query_start, LEFT(query, 200) AS query_preview
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

Có thể xem execution plan của truy vấn kiểm tra bằng EXPLAIN. Với DBMS khác, dùng catalog và công cụ performance tương ứng. Không chia sẻ query preview nếu có literal hoặc thông tin nhạy cảm.

## 24. Lỗi thường gặp khi tối ưu changelog lớn

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Update chậm dù không có SQL pending | Startup, resource loading, validation/history hoặc precondition | Đo từng pha, kiểm tra status và log |
| Một precondition mất nhiều giây | Snapshot metadata rộng hoặc SQL check quét bảng | Giới hạn schema/predicate, dùng execution plan |
| Nhiều changeset lặp cùng SQL check | Điều kiện chung đặt ở từng changeset | Đánh giá có thể chuyển lên changelog-level không |
| IncludeAll quét quá nhiều file | Thư mục có nhiều tài nguyên ngoài changelog | Thu hẹp thư mục, tách nhóm, cân nhắc include tường minh |
| Thời gian run tăng thất thường | Lock wait hoặc tải DBMS thay đổi | Kiểm tra DATABASECHANGELOGLOCK và session |
| Chạy nhanh trên dev, chậm production | Dữ liệu và metadata lớn hơn | Benchmark trên dữ liệu đại diện |
| SQL check COUNT(*) quá chậm | Quét bảng lớn dù chỉ cần biết có dòng vi phạm | Dùng EXISTS nếu đúng ngữ nghĩa |
| Tăng tốc bằng WARN gây lỗi dữ liệu | Điều kiện an toàn bị bỏ qua | Khôi phục HALT và sửa predicate |
| Changeset cũ bị chạy lại | runAlways/runOnChange hoặc history/path thay đổi | Kiểm tra identity và cấu hình |
| Retry sau timeout tạo object trùng | SQL đã commit một phần | Kiểm tra schema/history trước retry |
| Spring Boot startup timeout | Migration dài trong ApplicationContext | Đo riêng migration, cân nhắc job độc lập |
| Parallel update không nhanh hơn | Cùng DATABASECHANGELOGLOCK hoặc DBMS contention | Tuần tự theo database, giới hạn concurrency |

## 25. Bài thực hành: tìm precondition tốn kém

Dùng database lab hoặc Testcontainers với dữ liệu mô phỏng đủ lớn. Không thử benchmark destructive trên production.

### Phần A — Tạo baseline

1. Tạo bảng customer có số dòng đại diện.
2. Tạo changelog có nhiều changeset và một số precondition.
3. Chạy update trên database sạch và database đã có history.
4. Ghi tổng duration, lock wait và log.
5. Xác định precondition hoặc changeset tốn thời gian nhất.

### Phần B — So sánh COUNT và EXISTS

1. Tạo dữ liệu có và không có dòng vi phạm.
2. Chạy truy vấn COUNT(*) theo predicate.
3. Chạy truy vấn EXISTS với cùng predicate.
4. Dùng EXPLAIN để so sánh kế hoạch.
5. Xác minh cả hai biểu diễn cùng một điều kiện logic trong mọi trường hợp.
6. Chọn cách phù hợp và kiểm tra lại precondition.

### Phần C — So sánh precondition cấp changelog và changeset

1. Tạo nhiều changeset cần cùng một điều kiện chung.
2. Đo cấu hình kiểm tra lặp ở từng changeset.
3. Chuyển điều kiện thực sự chung lên cấp changelog.
4. Chạy lại và so sánh thời gian.
5. Kiểm tra trường hợp điều kiện không đạt và xác nhận toàn bộ changelog dừng đúng chính sách.

Không chuyển điều kiện riêng của một changeset lên cấp changelog chỉ để giảm số lần chạy.

### Phần D — Kiểm tra include và history

1. Tổ chức cùng tập changeset bằng include tường minh và includeAll trong hai fixture riêng.
2. So sánh resource loading, thời gian parse và độ rõ thứ tự.
3. Kiểm tra ID/author/path và DATABASECHANGELOG.
4. Xác nhận không có changeset bị thiếu hoặc nạp hai lần.

### Phần E — Đánh giá an toàn

1. Tạo dữ liệu vi phạm constraint.
2. Xác minh precondition HALT dừng migration.
3. Thử thay đổi predicate để tối ưu nhưng giữ nguyên ngữ nghĩa.
4. Chạy trên cả dữ liệu hợp lệ và dữ liệu vi phạm.
5. Đối chiếu schema/data/history sau từng lần chạy.

Điều kiện hoàn thành: người học chỉ ra được bottleneck bằng số liệu, giải thích chi phí của precondition, chứng minh tối ưu không làm yếu điều kiện và xác nhận history/schema vẫn đúng.

## 26. Checklist trước khi đưa tối ưu hiệu năng vào production

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Đã đo baseline cùng DBMS và dữ liệu đại diện? | Số liệu trước tối ưu |
| Đã tách startup, lock wait, precondition và SQL execution? | Timing/log/DBMS session |
| Đã xác định precondition đắt cụ thể? | Predicate, snapshot hoặc truy vấn liên quan |
| Có thể thu hẹp schema/object scope? | Phạm vi kiểm tra được xác minh |
| SQL check có đúng ngữ nghĩa và execution plan phù hợp? | Test dữ liệu hợp lệ/vi phạm |
| Có điều kiện lặp lại không cần thiết? | Phân tích cấp changelog/changeset |
| Include/includeAll có thứ tự xác định? | Cấu trúc và test history |
| Context/label/DBMS filter không bỏ sót migration? | Effective filter và status |
| Chính sách onFail/onError còn an toàn? | Kiểm thử nhánh fail/error |
| Changeset đã phát hành được giữ bất biến? | History/checksum review |
| Backfill và DDL có giới hạn lock/transaction? | Test trên dữ liệu lớn |
| Có kiểm tra rollback/forward-fix? | Kết quả thử nghiệm |
| Fresh install và upgrade đều đạt? | Hai bộ test độc lập |
| Có post-check schema/data/history? | Assertion sau migration |
| Có cảnh báo khi duration vượt baseline? | Ngưỡng và runbook |

**Nguyên tắc cuối cùng:** tối ưu changelog lớn phải bắt đầu bằng đo đạc, sau đó xử lý đúng bottleneck: resource loading, history/checksum, lock wait, snapshot metadata, SQL precondition hay DDL/DML. Hãy giữ precondition bảo vệ invariant dữ liệu, thu hẹp phạm vi và chi phí truy vấn, tránh lặp kiểm tra không cần thiết và thử lại trên database có dữ liệu đại diện. Một migration chỉ được xem là tối ưu khi thời gian cải thiện mà schema, dữ liệu, lịch sử và khả năng phục hồi vẫn đúng.

