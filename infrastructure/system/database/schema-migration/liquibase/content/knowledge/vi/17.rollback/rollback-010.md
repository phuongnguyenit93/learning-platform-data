# Kiểm thử cập nhật, hoàn tác và cập nhật lại trong Liquibase

Migration database không được xem là an toàn chỉ vì lệnh **update** chạy thành công một lần. Một changeset có thể áp dụng được nhưng không thể hoàn tác; một rollback có thể chạy không lỗi nhưng làm mất dữ liệu; hoặc sau rollback, chính changeset đó không thể cập nhật lại vì trạng thái schema và lịch sử Liquibase đã lệch nhau. Vì vậy, một quy trình kiểm chứng quan trọng là **cập nhật → hoàn tác → cập nhật lại** (*update → rollback → re-update*).

Bài học thuộc chương **Hoàn tác** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

**Trọng tâm** của bài là cách dựng phép thử ba giai đoạn, sử dụng lệnh **update-testing-rollback** khi được phiên bản/cấu hình Liquibase hỗ trợ, thiết kế phương án làm thủ công có kiểm soát, xác minh trạng thái ở mỗi giai đoạn và phát hiện những giới hạn mà một lệnh thành công không thể bảo đảm.

Sau bài học, bạn có thể:

1. Giải thích tại sao cần thử cả đường đi lên, đường đi xuống và đường đi lên lần nữa.
2. Chọn đúng cơ chế rollback theo tag, số changeset hoặc mốc phù hợp.
3. Phân biệt **rollback của Liquibase** với **rollback của transaction DBMS** và **khôi phục database từ backup**.
4. Viết changelog có rollback phù hợp, thiết kế kiểm tra trước/sau mỗi giai đoạn và truy vết qua DATABASECHANGELOG.
5. Nhận diện vấn đề về DDL tự commit, changeset không thể đảo ngược, tiền điều kiện, dữ liệu phát sinh và tính chạy lại.
6. Đưa kiểm thử migration vào CI/CD, tách biệt với các thao tác phá hủy trên production.

## 1. Vì sao kiểm thử chỉ một lần update là chưa đủ?

Xét một chuỗi thay đổi:

~~~text
A. Thêm cột customer.status
B. Chuyển dữ liệu trạng thái cũ sang cột mới
C. Tạo index trên customer.status
~~~

Nếu chạy **update** trên database trống và không gặp lỗi, ta chỉ biết một phần đường triển khai ban đầu đã hoạt động. Các câu hỏi chưa được trả lời:

- Khi cần rollback, index và cột có được gỡ theo thứ tự đúng không?
- Nếu backfill làm thay đổi dữ liệu thật, rollback có khôi phục giá trị ban đầu không?
- Nếu cột có default, constraint hoặc trigger phụ thuộc, rollback có làm hỏng chúng không?
- Sau rollback, Liquibase có xem những changeset đó là **pending** trở lại không?
- Chạy update lần thứ hai có tạo đúng schema mong đợi không?
- DBMS có thực sự hoàn tác được DDL, hay một phần DDL đã tự commit?
- Nếu lỗi xảy ra sau một bước đã commit, DATABASECHANGELOG còn phản ánh đúng trạng thái không?

Phép thử **up → down → up** giúp phát hiện một lớp lỗi mà chỉ kiểm thử cập nhật một chiều khó thấy.

### 1.1. Ba lớp kết quả phải được kiểm chứng

| Lớp | Điều cần xác nhận |
|---|---|
| **Công cụ Liquibase** | Lệnh trả về trạng thái phù hợp; có hoặc không có changeset pending như dự kiến |
| **Lịch sử** | DATABASECHANGELOG ghi nhận đúng ID, AUTHOR, FILENAME, EXECTYPE ở từng giai đoạn |
| **Database thật** | Bảng, cột, index, constraint, view và dữ liệu khớp kỳ vọng |

Không kết luận kiểm thử thành công chỉ vì CLI in ra thông báo thành công. Một changeset có thể được **MARK_RAN** mà không thực thi SQL, hoặc schema có thể bị thay đổi thủ công ngoài Liquibase.

## 2. Hiểu đúng ba giai đoạn của phép thử

Một kịch bản được thiết kế từ **baseline S0** tới trạng thái mục tiêu **S1**.

~~~mermaid
flowchart LR
    A[S0: Baseline] -->|Update| B[S1: Schema sau migration]
    B -->|Rollback| C[S0': Trạng thái sau hoàn tác]
    C -->|Update lại| D[S1': Trạng thái sau áp dụng lần hai]
~~~

Tiêu chí mong đợi:

- Sau **update đầu**, trạng thái **S1** đạt những invariant đã chỉ định.
- Sau **rollback**, trạng thái **S0'** tương đương **S0** theo những tiêu chí cần bảo toàn.
- Sau **update lại**, trạng thái **S1'** tương đương **S1** theo hợp đồng schema/dữ liệu.

**Tương đương không nhất thiết bằng nhau từng byte.** Một số metadata như thời điểm thực thi, deployment ID, sequence value hoặc audit log có thể khác qua các lần chạy. Điều quan trọng là quy định trước những gì phải giống nhau: cấu trúc bảng, constraints, dữ liệu nghiệp vụ, khả năng truy vấn và lịch sử changeset phù hợp.

### 2.1. Đừng nhầm update lần hai với update lại sau rollback

Hai kịch bản khác nhau:

- **Update rồi update ngay lần nữa:** kiểm tra rằng những changeset đã ghi nhận thường không bị chạy lại ngoài ý muốn.
- **Update → rollback → update:** kiểm tra rollback thực sự đưa trạng thái về mức cho phép áp dụng lại changeset.

Cả hai đều hữu ích, nhưng không thay thế nhau. Lệnh **update-testing-rollback** tập trung vào chu trình thứ hai.

## 3. Ba cơ chế hoàn nguyên khác nhau

| Cơ chế | Ai thực hiện? | Ý nghĩa |
|---|---|---|
| **Transaction ROLLBACK** | DBMS | Hoàn nguyên những thay đổi chưa commit trong một transaction được hỗ trợ |
| **Liquibase rollback** | Liquibase chạy thay đổi đảo ngược | Hoàn tác các changeset đã triển khai theo kế hoạch và phạm vi được chọn |
| **Backup/restore** | Cơ chế sao lưu/khôi phục dữ liệu | Khôi phục trạng thái database từ bản sao/snapshot theo quy trình vận hành |

Ví dụ trên PostgreSQL:

~~~sql
BEGIN;
CREATE TABLE tx_demo (id BIGINT PRIMARY KEY);
ROLLBACK;
~~~

DDL thường được hoàn nguyên trong transaction PostgreSQL hợp lệ. Nhưng với nhiều DDL MySQL hoặc Oracle, thao tác tạo/sửa bảng có thể **implicit commit**, nên lệnh ROLLBACK của transaction không đảo được DDL đã chạy.

Trong Liquibase, một changeset tạo bảng có thể khai báo rollback là **dropTable**; đây là **một DDL mới**, không phải transaction rollback của lệnh CREATE TABLE trước đó.

**Backup/restore** lại là một quy trình khác, thường cần khi dữ liệu đã bị xóa hoặc thay đổi không thể đảo ngược an toàn.

## 4. Lệnh update-testing-rollback của Liquibase

Liquibase có lệnh **update-testing-rollback**, được thiết kế cho việc thử chuỗi thao tác: áp dụng các changeset đang chờ, hoàn tác những changeset vừa được áp dụng theo cơ chế lệnh, rồi áp dụng lại.

Ví dụ cú pháp thường gặp:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml \
  update-testing-rollback
~~~

Với môi trường dùng cấu hình kết nối qua CLI properties hoặc secret manager, không cần viết password thật trong câu lệnh minh họa.

**Lưu ý phiên bản:** tên lệnh, tùy chọn, phạm vi rollback, điều kiện cấp phép và cách hiển thị đầu ra phải được kiểm tra bằng tài liệu/CLI **đúng phiên bản** mà dự án dùng. Không suy luận rằng mọi phiên bản Liquibase đều cung cấp cùng tính năng hoặc syntax.

### 4.1. Lệnh nhằm phát hiện điều gì?

Đây là công cụ sớm để tìm lỗi như:

- Changeset chưa có rollback và Liquibase không thể tự tạo rollback.
- SQL rollback sai cú pháp hoặc sai thứ tự phụ thuộc.
- Một đối tượng vẫn tồn tại sau rollback khiến re-update báo duplicate.
- Một đối tượng bị mất sau rollback khiến re-update thiếu tiền đề.
- Tiền điều kiện hoặc filter khiến những changeset được chọn không như dự định.
- Đặc tính DBMS làm xuất hiện trạng thái chưa được dọn sạch sau khi thất bại.

Nhưng lệnh **không chứng minh** mọi thứ có thể khôi phục được trong production. Những thay đổi dữ liệu có tác dụng phụ hoặc thao tác ngoài database vẫn phải được kiểm tra riêng.

### 4.2. Không dùng thử nghiệm này trực tiếp trên production

Dù đích cuối cùng là trạng thái sau update, **giai đoạn rollback ở giữa là thao tác thật**. Nếu rollback bao gồm DROP COLUMN, DROP TABLE, DELETE hoặc thay đổi view/index, nó có thể gây mất dữ liệu, gián đoạn dịch vụ hoặc tác động phiên làm việc đang dùng schema.

**Chỉ chạy chu trình ba giai đoạn trên database thử nghiệm cách ly hoặc bản sao có chủ đích, với quyền và kế hoạch phục hồi phù hợp.** Không dùng nó để “kiểm tra nhanh” trên production khi database đang có dữ liệu nghiệp vụ và lưu lượng người dùng.

## 5. Điều kiện tiên quyết trước khi thử up → down → up

Một bài thử có giá trị cần **baseline được kiểm soát**.

Danh sách chuẩn bị:

1. Xác nhận database được dùng chỉ dành cho thử nghiệm hoặc là bản sao được phép thao tác.
2. Xác nhận JDBC URL, database/service, schema, user và driver thực tế.
3. Ghi Liquibase version, DBMS/version và loại executor.
4. Chọn artifact changelog đã được review.
5. Xác định changeset **đang pending** từ baseline.
6. Chọn chiến lược rollback, phạm vi rollback và cách xác minh trạng thái.
7. Chuẩn bị dữ liệu thử đại diện cho những quan hệ và constraints được thay đổi.
8. Có bản sao/backup cho phép khôi phục môi trường thử nghiệm nếu một lần rollback thất bại.

Đối với bài thực hành, dễ nhất là bắt đầu từ một database disposable, không chứa dữ liệu cần giữ, chạy changelog baseline trước rồi đưa migration mới vào phạm vi kiểm thử.

### 5.1. Cẩn thận với dữ liệu sẵn có

Nếu dùng bản sao production, trước tiên phải xử lý quyền truy cập, bảo vệ dữ liệu nhạy cảm và chính sách ẩn danh hóa. Bản sao đó vẫn chứa dữ liệu thật theo nghĩa nghiệp vụ, nên rollback DROP/DELETE vẫn có thể phá hủy nội dung bản sao; tuyệt đối không được hiểu test là không có rủi ro.

Nếu DBMS hoặc hệ thống backup sử dụng snapshot, việc phục hồi snapshot phải được kiểm chứng trên môi trường thử nghiệm thay vì chỉ dựa vào sự tồn tại của file backup.

## 6. Quan sát trạng thái trước khi chạy

Trước update, chạy kiểm tra **read-only** để xây baseline.

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate

liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose

liquibase history
~~~

Ý nghĩa:

- **validate** kiểm tra changelog theo quy tắc được Liquibase hỗ trợ.
- **status --verbose** giúp thấy changeset chưa được ghi nhận trong database với cấu hình hiện tại.
- **history** xem những thay đổi Liquibase đã ghi nhận trên database đang kết nối.

Cần ghi nhận những changeset pending **theo bộ ID + AUTHOR + FILENAME/logicalFilePath**, không chỉ đếm số lượng.

### 6.1. Truy vấn DATABASECHANGELOG

Một truy vấn chỉ đọc:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    EXECTYPE,
    DATEEXECUTED,
    MD5SUM,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Nếu bảng Liquibase nằm trong schema riêng hoặc có tên tùy chỉnh, phải dùng tên metadata thực tế.

Đừng mặc định rằng **history** trống có nghĩa database hoàn toàn trống: có thể DBMS đã được quản trị thủ công, hoặc Liquibase đang sử dụng schema metadata khác.

## 7. Kiểm tra SQL sẽ chạy trước khi update

Lệnh preview:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

Khi xem SQL, kiểm tra:

- Đúng tên schema, bảng, cột, index và constraint.
- Đúng thứ tự phụ thuộc giữa các changeset.
- Không có DROP, TRUNCATE hoặc UPDATE dữ liệu ngoài phạm vi dự kiến.
- DDL đặc thù DBMS đã được kiểm thử đúng phiên bản.
- Context, label filter và precondition chọn tập thay đổi mong đợi.
- Nếu có SQL function/procedure, delimiter và **splitStatements** phù hợp.
- Changeset có **runInTransaction:false** hoặc DDL tự commit đã có chiến lược xử lý khi lỗi.

**update-sql không chạy thử transaction**, cũng không chứng minh rollback sẽ thành công. Nó chỉ là bước review trước khi chuyển sang thao tác thực thi thật.

## 8. Phải kiểm tra SQL rollback trước khi thử rollback

Với một phạm vi rollback được xác định, các lệnh như **rollback-sql** theo tag hoặc **rollback-count-sql** theo số lượng changeset có thể được dùng để xem trước các lệnh đảo ngược.

Ví dụ hiện đại thường gặp:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-count-sql --count=2
~~~

Hoặc một quy trình sử dụng tag phù hợp:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-sql --tag=before_test_release
~~~

Các ví dụ minh họa **hai phương thức chọn phạm vi khác nhau**, không có nghĩa tag **before_test_release** tự tồn tại. Phải tạo và xác minh mốc tag theo quy trình trước đó. Tên lệnh, vị trí tùy chọn, chế độ output và yêu cầu phiên bản cần được xác minh từ Liquibase đang dùng.

### 8.1. Vì sao review rollback-sql quan trọng?

Giả sử changelog tạo index rồi thêm cột. Nếu rollback xóa cột trước khi xóa index phụ thuộc, DBMS có thể từ chối hoặc gây ảnh hưởng ngoài ý muốn.

Cần xem:

- Thứ tự rollback có phù hợp quan hệ phụ thuộc không.
- SQL có làm mất dữ liệu thật không.
- Có thể khôi phục comment, default, index, constraint và quyền trước đó không.
- Cú pháp rollback có đúng DBMS không.
- Có câu rollback cho SQL tùy ý, stored procedure hoặc data migration không.
- Có change type nào không được hỗ trợ auto rollback không.

**SQL preview là cần thiết nhưng chưa đủ:** cú pháp có thể hợp lệ nhưng vẫn thất bại vì dữ liệu, khóa, quyền hoặc DBMS đang trong trạng thái khác.

## 9. Chọn cách chạy phép thử: tự động hay thủ công

Có hai con đường chính.

| Tiêu chí | update-testing-rollback | Quy trình thủ công |
|---|---|---|
| Mục đích | Thử nhanh chu trình ba giai đoạn theo cơ chế lệnh | Kiểm soát từng bước và điểm dừng |
| Ranh giới | Theo tập changeset được lệnh xét và cơ chế hiện hành | Theo tag, số changeset hoặc mốc được chọn |
| Quan sát giữa các bước | Phụ thuộc log/đầu ra của lệnh | Có thể truy vấn schema/dữ liệu sau từng bước |
| Tùy biến dữ liệu và assertion | Thường cần công cụ kiểm thử bổ sung | Linh hoạt hơn |
| Rủi ro | Vẫn thực thi rollback thật | Vẫn thực thi rollback thật |
| Phù hợp | Kiểm thử nhanh trước phát hành | Kiểm chứng sâu, thay đổi dữ liệu, case đặc biệt |

**Một lệnh tự động thành công không thay thế các assertion nghiệp vụ.** Với thay đổi có dữ liệu hoặc dependencies phức tạp, nên có bài thử thủ công hoặc automation tùy chỉnh để quan sát từng trạng thái S0, S1, S0', S1'.

## 10. Cách làm thủ công theo một mốc tag

Một phương pháp thuận tiện trong **database kiểm thử** là ghi nhận mốc trước khi áp dụng changeset mới.

Dòng thời gian:

~~~text
1. Baseline S0
2. Tạo/xác nhận tag phù hợp trước thử nghiệm
3. Update các changeset mới -> S1
4. Xác minh S1
5. Rollback đến tag -> S0'
6. Xác minh S0'
7. Update lại -> S1'
8. Xác minh S1'
~~~

Ví dụ lệnh theo dạng CLI hiện đại:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml \
  tag before_test_release

liquibase --changelog-file=db/changelog/db.changelog-master.yaml \
  update

liquibase --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback --tag=before_test_release

liquibase --changelog-file=db/changelog/db.changelog-master.yaml \
  update
~~~

**Ràng buộc:** phải xác minh tag được gắn đúng trạng thái baseline và cách version Liquibase xử lý tag/rollback. Nếu database đã có tag trùng tên, mốc không rõ hoặc có changeset khác chạy xen vào, không tiếp tục như thể phạm vi rollback chắc chắn đúng.

### 10.1. Tại sao không tùy tiện dùng rollback-count?

**rollback-count** chọn số changeset gần nhất theo quy tắc Liquibase. Nếu database đã có changeset khác của một pipeline đồng thời, hoặc tập changeset được chọn thay đổi do filter, con số **2** có thể không còn nghĩa “hai thay đổi của bài thực hành”.

Trong thử nghiệm cách ly và khi đã xác minh history, rollback-count có thể hữu ích. Trong hệ thống dùng chung, mốc tag hoặc phương thức xác định phạm vi rõ hơn thường dễ kiểm soát hơn.

## 11. Thử theo số changeset khi phạm vi hoàn toàn được kiểm soát

Với một database disposable và changelog đơn giản chỉ có đúng hai changeset mới, có thể áp dụng:

~~~bash
liquibase --changelog-file=db/changelog/training.yaml update

liquibase --changelog-file=db/changelog/training.yaml \
  rollback-count-sql --count=2

liquibase --changelog-file=db/changelog/training.yaml \
  rollback-count --count=2

liquibase --changelog-file=db/changelog/training.yaml update
~~~

Trình tự dự kiến:

1. **update** chạy hai changeset.
2. **rollback-count-sql** hiển thị câu đảo ngược để review.
3. **rollback-count** thực hiện hoàn tác hai changeset.
4. **update** áp dụng lại.

Các lệnh thay đổi DB chỉ được chạy trên môi trường thử nghiệm đã xác minh; CLI option có thể khác theo phiên bản. **Không chạy rollback-count với số đoán mò trên database nhiều nhóm cùng sử dụng.**

### 11.1. Dừng khi có thay đổi bất ngờ

Nếu sau lần update đầu, **history** cho thấy số changeset mới hoặc thứ tự khác dự kiến, đừng tiếp tục rollback theo số lượng ban đầu. Phải cập nhật phạm vi dựa trên thực tế hoặc dựng lại baseline thử nghiệm.

## 12. Ví dụ changelog tự chứa cho bài thực hành

Giả sử PostgreSQL có schema **public** và database thực hành chưa có bảng **lab_order_note**. Tạo một changelog YAML minh họa gồm hai changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "lab-001-create-order-note"
      author: "training-team"
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - not:
            - tableExists:
                schemaName: public
                tableName: lab_order_note
      changes:
        - createTable:
            schemaName: public
            tableName: lab_order_note
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: order_id
                  type: bigint
                  constraints:
                    nullable: false
              - column:
                  name: note_text
                  type: varchar(500)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            schemaName: public
            tableName: lab_order_note

  - changeSet:
      id: "lab-002-order-note-index"
      author: "training-team"
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: lab_order_note
      changes:
        - createIndex:
            schemaName: public
            tableName: lab_order_note
            indexName: idx_lab_order_note_order_id
            columns:
              - column:
                  name: order_id
      rollback:
        - dropIndex:
            schemaName: public
            tableName: lab_order_note
            indexName: idx_lab_order_note_order_id
~~~

### 12.1. Vì sao tách hai changeset?

- **lab-001** tạo bảng.
- **lab-002** tạo index phụ thuộc bảng.
- Mỗi changeset có ID, tiền điều kiện và rollback riêng.
- Nếu index lỗi, bảng có thể đã được tạo và ghi nhận từ changeset trước; việc điều tra/khôi phục rõ ràng hơn.
- Khi rollback cả hai, index được gỡ trước rồi bảng được gỡ theo thứ tự phù hợp.

Không nên áp dụng changelog này lên database đã có đối tượng cùng tên. Các tiền điều kiện dùng **HALT** để làm lộ xung đột, không âm thầm đánh dấu như đã chạy.

### 12.2. Lưu ý về rollback dữ liệu

**dropTable** sẽ xóa dữ liệu của **lab_order_note** nếu bảng đã được ứng dụng ghi dữ liệu sau update. Vì thế ví dụ chỉ dành cho database thực hành disposable. Trong production, việc bổ sung rollback không đồng nghĩa đã có kế hoạch khôi phục dữ liệu đủ an toàn.

## 13. Tập assertion SQL cho từng giai đoạn

Trong PostgreSQL, có thể kiểm tra sự tồn tại của bảng và index bằng hàm **to_regclass**:

~~~sql
SELECT
    to_regclass('public.lab_order_note') IS NOT NULL
        AS table_exists,
    to_regclass('public.idx_lab_order_note_order_id') IS NOT NULL
        AS index_exists;
~~~

Kỳ vọng:

| Giai đoạn | table_exists | index_exists |
|---|---|---|
| **S0**: trước update | false | false |
| **S1**: sau update | true | true |
| **S0'**: sau rollback | false | false |
| **S1'**: sau update lại | true | true |

Điều kiện này kiểm tra hai đối tượng cần thiết nhưng chưa đủ để chứng minh toàn bộ schema. Nếu quan trọng, kiểm tra thêm cột, kiểu dữ liệu, nullability và ràng buộc.

Ví dụ truy vấn metadata cột:

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'lab_order_note'
ORDER BY ordinal_position;
~~~

Sau update và update lại, kỳ vọng có các cột id, order_id và note_text đúng kiểu/constraint như changelog.

## 14. Assertion lịch sử DATABASECHANGELOG

Lịch sử cần được kiểm tra song song với schema.

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    EXECTYPE,
    DATEEXECUTED,
    ORDEREXECUTED,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
WHERE AUTHOR = 'training-team'
  AND ID IN (
      'lab-001-create-order-note',
      'lab-002-order-note-index'
  )
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Giả định database không có các bản ghi trùng từ những bài thử trước.

| Giai đoạn | Bản ghi thực hành dự kiến |
|---|---|
| Trước update | Không có |
| Sau update | Hai changeset được ghi nhận theo quy tắc Liquibase |
| Sau rollback thành công | Các bản ghi tương ứng thường được gỡ khỏi trạng thái DATABASECHANGELOG |
| Sau update lại | Hai changeset lại được ghi nhận |

Các giá trị **DATEEXECUTED** và **DEPLOYMENT_ID** có thể khác giữa hai lượt update; đừng lấy việc chúng khác nhau làm lỗi kiểm thử.

**Quan trọng:** DATABASECHANGELOG không phải nhật ký append-only giữ mọi sự kiện; một rollback thành công có thể làm dòng lịch sử của changeset bị gỡ. Muốn kiểm toán mọi lượt up/down/up, hãy lưu thêm log và sự kiện trong CI/CD.

## 15. Kiểm thử đúng nghĩa là so sánh invariant, không chỉ so sánh số dòng

Một bộ assertion nên mô tả **hợp đồng trạng thái** thay vì chỉ tìm “hai dòng mới” trong history.

Ví dụ hợp đồng sau update:

~~~text
- Bảng public.lab_order_note tồn tại.
- Có cột id BIGINT PRIMARY KEY, NOT NULL.
- Có cột order_id BIGINT NOT NULL.
- Có cột note_text VARCHAR(500) NOT NULL.
- Có index idx_lab_order_note_order_id trên order_id.
- Hai changeset được Liquibase ghi nhận với identity dự kiến.
~~~

Sau rollback:

~~~text
- Bảng public.lab_order_note không còn.
- Index phụ thuộc không còn.
- Những bản ghi changeset vừa rollback không còn là trạng thái đã áp dụng.
- Các đối tượng baseline không bị thay đổi hoặc xóa ngoài dự kiến.
~~~

Sau re-update:

~~~text
- Hợp đồng schema sau update được thỏa trở lại.
- Không có đối tượng trùng, index trùng hoặc thay đổi ngoài mong đợi.
- Những changeset được ghi nhận theo cơ chế Liquibase.
~~~

Các tiêu chí phải được điều chỉnh theo tính chất migration. Với data migration, cần thêm invariant về **số hàng, giá trị nghiệp vụ, khóa tham chiếu và tính bảo toàn dữ liệu**.

## 16. Chạy update hai lần mà không rollback: kiểm tra phát hiện duplicate

Ngoài ba giai đoạn chính, có thể bổ sung một bước:

~~~bash
liquibase --changelog-file=db/changelog/training.yaml update
liquibase --changelog-file=db/changelog/training.yaml status --verbose
liquibase --changelog-file=db/changelog/training.yaml update
~~~

Với changeset thông thường đã ghi nhận, lần update thứ hai không nên cố CREATE TABLE hoặc CREATE INDEX một lần nữa. Nếu xảy ra duplicate, điều tra:

- ID/AUTHOR/FILENAME có thay đổi không.
- Changelog có được include qua đường dẫn khác không.
- Có **runAlways** hoặc **runOnChange** không.
- DATABASECHANGELOG có ở schema khác không.
- Có ai xóa/sửa lịch sử hoặc rollback trước đó không.

Đây là kiểm thử **không chạy lại ngoài ý muốn**. Nó khác phép thử re-update sau rollback, khi changeset đã được hoàn tác có thể trở lại trạng thái pending.

## 17. Tiền điều kiện có thể ảnh hưởng mạnh đến phép thử

Precondition kiểm tra trạng thái database trước khi changeset thực thi. Ví dụ:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - not:
      - tableExists:
          tableName: lab_order_note
          schemaName: public
~~~

Trước update: bảng chưa tồn tại, điều kiện đúng.

Sau update: bảng tồn tại, nhưng changeset đã được ghi nhận nên thường không được xét chạy lại.

Sau rollback: bảng đã được gỡ, thay đổi có thể được xét lại và điều kiện lại đúng.

Đây là hành vi mong đợi của local precondition trong chu trình up/down/up.

### 17.1. Sai phạm vi precondition có thể phá chu trình

Nếu đặt **NOT tableExists** ở **cấp changelog**, lần update thứ hai có thể bị chặn vì bảng đã được tạo thành công; điều kiện “bảng chưa tồn tại” chỉ phù hợp với thời điểm chạy changeset tạo bảng.

Với migration có phụ thuộc, hãy đặt precondition ở cấp phù hợp, thay vì áp điều kiện trạng thái tạm thời cho toàn bộ changelog.

### 17.2. MARK_RAN có thể tạo kết quả giả

Nếu dùng **onFail:MARK_RAN**, changeset có thể được ghi nhận mà không chạy SQL. Sau update, CLI có thể không báo lỗi nhưng bảng/cột cần tạo vẫn chưa tồn tại.

Khi kiểm thử, phải phân biệt **EXECTYPE=MARK_RAN** với **EXECUTED** và kiểm tra metadata thật; không chỉ nhìn số changeset được ghi nhận.

## 18. runAlways và runOnChange ảnh hưởng tới việc kiểm thử

Hai thuộc tính này làm thay đổi hành vi chạy lại của changeset:

- **runAlways:true**: cho phép thực thi changeset mỗi lần update đủ điều kiện.
- **runOnChange:true**: cho phép chạy lại theo thay đổi checksum theo quy tắc Liquibase, thường dùng với một số view/procedure.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "refresh-summary-view"
      author: "reporting-team"
      runOnChange: true
      changes:
        - createView:
            viewName: customer_summary
            replaceIfExists: true
            selectQuery: "SELECT id, email FROM customer"
~~~

Phép thử **update hai lần** hoặc **up/down/up** phải tính tới cơ chế chạy lại này. Không tự suy ra rằng một bản ghi changeset luôn tương ứng với đúng một lần SQL được thực thi.

### 18.1. Dữ liệu không idempotent gây nguy hiểm

Xét changeset:

~~~sql
UPDATE account_balance
SET amount = amount + 100;
~~~

Nếu chạy lại, giá trị có thể tăng thêm 100 mỗi lần. Việc Liquibase có thể chạy lại changeset không khiến SQL trở nên **idempotent**.

Với migration dữ liệu, đặc biệt khi runAlways/runOnChange hoặc sửa chữa sau rollback, phải kiểm tra tính chạy lại an toàn, phạm vi hàng bị ảnh hưởng và cách khôi phục.

## 19. Rollback DML cần chiến lược bảo toàn dữ liệu

Giả sử migration cập nhật giá trị NULL:

~~~sql
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Một rollback ngây thơ:

~~~sql
UPDATE customer
SET status = NULL
WHERE status = 'ACTIVE';
~~~

không đúng nếu trước migration đã có những dòng ACTIVE hợp lệ. Nó sẽ xóa thông tin của cả những dòng không được migration tác động.

Để rollback có nghĩa, cần thiết kế từ trước một trong các phương án:

- Ghi lại khóa và giá trị gốc của những dòng thay đổi trong bảng backup/audit được quản lý.
- Dùng marker hoặc transaction ID đủ tin cậy để nhận diện đúng tập dòng.
- Chuyển đổi dữ liệu qua trạng thái trung gian có thể đảo ngược rõ ràng.
- Dùng bản sao/snapshot để khôi phục khi tính toàn vẹn yêu cầu.
- Chọn **forward fix** có kiểm soát nếu đảo ngược dữ liệu không an toàn.

Phép thử up/down/up phải kiểm tra **nội dung dữ liệu**, không chỉ xem UPDATE đã chạy và rollback không ném exception.

## 20. Rollback đối tượng SQL: view, function và procedure

Changeset có thể tạo hoặc thay thế view/function:

~~~sql
CREATE OR REPLACE VIEW customer_summary AS
SELECT id, email
FROM customer;
~~~

Nếu view **đã tồn tại trước migration**, rollback bằng:

~~~sql
DROP VIEW customer_summary;
~~~

có thể làm mất view cũ, không phải khôi phục định nghĩa trước đó.

Đối với một đối tượng đã tồn tại, cần lưu **định nghĩa baseline** và thiết kế rollback khôi phục định nghĩa cũ. Nếu changeset tạo mới hoàn toàn, DROP có thể là rollback phù hợp nếu không có đối tượng phụ thuộc.

Với SQL phức tạp:

- Kiểm tra **splitStatements**, **endDelimiter** và dialect DBMS.
- Xem SQL rollback dự kiến.
- Thử quy trình trên DBMS/driver thật.
- Xác minh đối tượng sau cả ba giai đoạn, ví dụ gọi function hoặc truy vấn view.
- Đừng xem việc CREATE OR REPLACE chạy lại được là bằng chứng rollback đúng.

## 21. DDL tự commit và chu trình không hoàn nguyên hoàn toàn

Hành vi DDL khác nhau theo DBMS:

| DBMS | Rủi ro đặc biệt khi up/down/up |
|---|---|
| **PostgreSQL** | Nhiều DDL có transaction; một số lệnh như CREATE INDEX CONCURRENTLY yêu cầu ngoài transaction |
| **MySQL/MariaDB** | Nhiều DDL implicit commit; lỗi giữa changeset có thể để lại schema đã thay đổi |
| **Oracle** | DDL thường implicit commit; DML trước DDL có thể bị commit trước |
| **SQL Server** | Nhiều DDL transactional nhưng có ngoại lệ theo lệnh/chế độ |
| **SQLite** | DDL thông thường transactional, nhưng đổi schema và lock có đặc điểm riêng |

**Một rollback Liquibase thành công không chứng minh toàn bộ thao tác ban đầu đã chạy trong cùng transaction.** Nó có thể chỉ là một loạt SQL đảo ngược trên schema đã commit.

### 21.1. Trường hợp CREATE INDEX CONCURRENTLY ở PostgreSQL

SQL:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON public.orders (created_at);
~~~

Câu lệnh không được chạy trong transaction block. Changeset có thể cần **runInTransaction:false**, và sau khi bị gián đoạn có thể còn index invalid.

Khi thử rollback và chạy lại:

1. Kiểm tra index có tồn tại không.
2. Kiểm tra index có hợp lệ không.
3. Kiểm tra SQL rollback có phù hợp giao dịch hay không.
4. Không retry mù nếu index đã được tạo một phần.
5. Xem lịch sử Liquibase sau mỗi bước.

### 21.2. Trường hợp DDL MySQL đã implicit commit

Nếu changeset thêm cột rồi UPDATE thất bại, cột có thể vẫn tồn tại dù changeset chưa ghi EXECUTED. Trong trường hợp đó, **update-testing-rollback không tự đảm bảo trạng thái sẽ được sửa chữa chính xác**.

Đầu tiên phải điều tra schema/data thật, xác định đoạn nào đã thành công và lập kế hoạch reconciliation. Không dùng việc sửa tay DATABASECHANGELOG như giải pháp mặc định.

## 22. Phép thử thành công nhưng vẫn có nguy cơ phá hủy dữ liệu

Một script có thể:

1. CREATE TABLE mới.
2. ROLLBACK bằng DROP TABLE.
3. CREATE TABLE lần nữa.

Và mọi lệnh đều thành công.

Tuy nhiên, nếu giữa update và rollback có người dùng hoặc test fixture ghi dữ liệu vào bảng, DROP TABLE có thể xóa dữ liệu đó. Sau re-update, schema đúng nhưng dữ liệu biến mất.

Do đó, cần phân biệt:

- **Khả năng đảo ngược schema:** các đối tượng được tạo/gỡ đúng.
- **Khả năng bảo toàn dữ liệu:** dữ liệu đã có hoặc phát sinh sau migration có được giữ không.
- **Khả năng duy trì tương thích ứng dụng:** ứng dụng cũ/mới có hoạt động ở các trạng thái tạm thời không.
- **Khả năng khôi phục vận hành:** có plan nếu một bước dừng giữa chừng không.

Phép thử tự động là một điều kiện hữu ích, nhưng không phải giấy chứng nhận rollback production an toàn.

## 23. Điều tra khi rollback thất bại ở giữa chừng

Một kịch bản nguy hiểm:

~~~text
S1: create table + add column + add index
Rollback:
  1. Drop index thành công
  2. Drop column thất bại vì constraint phụ thuộc
  3. Drop table chưa chạy
~~~

Database hiện ở trạng thái **trung gian**, có thể không khớp S0 hoặc S1.

Quy trình xử lý:

1. Dừng thao tác tiếp theo và tránh auto retry.
2. Ghi nhận changeset/statement lỗi và SQL đã chạy.
3. Kiểm tra lịch sử và trạng thái của từng đối tượng.
4. Xác định DBMS, transaction boundary và DDL implicit commit.
5. Kiểm tra xem rollback đã gỡ những dòng nào trong DATABASECHANGELOG.
6. Chọn kế hoạch phục hồi dựa trên trạng thái thật: hoàn tất rollback, forward fix hoặc restore.
7. Thử kế hoạch trên database bản sao, rồi mới áp dụng.
8. Ghi lại sự kiện và cập nhật bộ kiểm thử.

**Không cố thực hiện update lại ngay khi rollback mới hoàn tất một phần.** Khi baseline chưa khớp, re-update có thể chạm đối tượng còn sót hoặc nhân đôi dữ liệu.

## 24. Thử khả năng retry sau khi update gặp lỗi

Chu trình up/down/up nên được bổ sung một kịch bản **update lỗi trước rollback** trên môi trường thử nghiệm, đặc biệt đối với DBMS có implicit commit.

Ví dụ một changeset cố:

~~~sql
CREATE TABLE retry_probe (id BIGINT PRIMARY KEY);
CREATE TABLE retry_probe (id BIGINT PRIMARY KEY);
~~~

Lệnh thứ hai cố tạo bảng cùng tên và dự kiến lỗi. Đây chỉ là bài thử gây lỗi có chủ đích trên database disposable.

### Trên PostgreSQL

Nếu cả hai DDL được chạy trong một transaction hợp lệ, CREATE TABLE đầu có thể được hoàn nguyên khi changeset lỗi.

### Trên MySQL

CREATE TABLE thường implicit commit; sau khi lệnh thứ hai lỗi, bảng có thể còn tồn tại dù changeset chưa ghi nhận hoàn tất.

### Điều cần học

- Không suy luận trạng thái schema chỉ từ exit code.
- Không dùng retry vô điều kiện.
- Không tự đánh dấu **MARK_RAN** chỉ vì bảng đã tồn tại.
- Kiểm tra cả schema thật lẫn DATABASECHANGELOG trước khi quyết định sửa chữa.

Đây là kiểm thử **phục hồi lỗi**, không phải cùng một việc với kiểm thử rollback của changeset đã chạy thành công.

## 25. Quản lý database lock khi thử rollback

Liquibase thường dùng **DATABASECHANGELOGLOCK** để điều phối hoạt động migration. Trong test CI, nếu nhiều job trỏ vào cùng database, chúng có thể tranh chấp lock hoặc làm baseline thay đổi bất ngờ.

Nguyên tắc:

- Mỗi job migration integration test nên có database/schema cách ly hoặc cơ chế điều phối rõ ràng.
- Không chạy update/rollback song song trên cùng một database bằng nhiều pipeline độc lập.
- Nếu lock tồn tại sau khi job lỗi, xác minh có tiến trình Liquibase nào đang chạy trước khi xử lý.
- Không tự giải phóng lock khi một migration khác còn hoạt động.
- Liquibase lock không thay thế transaction hoặc khóa DDL của DBMS.

Một pipeline “sạch” cần bảo đảm **không có tác nhân khác ghi vào database** trong lúc đang xác minh S0 → S1 → S0' → S1'.

## 26. Thiết kế automation trong CI/CD

Phép thử có thể là một bước bắt buộc trước khi phát hành changelog.

Ví dụ pipeline ở mức khái niệm:

~~~text
Stage 1 — Prepare
  - Tạo database thử nghiệm cách ly
  - Nạp schema/data baseline phù hợp
  - Cấu hình Liquibase/driver/DBMS đúng phiên bản

Stage 2 — Preflight
  - Validate changelog
  - Kiểm tra JDBC URL/schema và lịch sử ban đầu
  - Kiểm tra tập changeset pending
  - Sinh SQL update và rollback để review

Stage 3 — Execute
  - Update -> kiểm tra S1
  - Rollback -> kiểm tra S0'
  - Update lại -> kiểm tra S1'

Stage 4 — Report
  - Đối chiếu DATABASECHANGELOG
  - Xuất kết quả assertion
  - Lưu log, version, artifact hash, deployment ID
  - Dọn database thử nghiệm theo chính sách
~~~

Có thể dùng **update-testing-rollback** ở Stage 3 nếu khả năng quan sát và kiểm soát phù hợp; khi cần assertion ở mỗi giai đoạn, pipeline có thể tách thành các lệnh riêng.

### 26.1. Tại sao không chỉ dựa vào exit code?

Exit code chỉ cho biết công cụ đánh giá lệnh theo cách nào. Một rollback có thể:

- Được thực thi nhưng mất dữ liệu.
- Dùng MARK_RAN hoặc filter khiến tập changeset khác mong đợi.
- Cập nhật lịch sử nhưng còn drift trong schema.
- Thành công trên DBMS nhỏ trong test nhưng gây lock kéo dài trên production.

Do đó, gate CI/CD cần kết hợp **exit code + assertion schema/data + history + review phạm vi rollback**.

### 26.2. Không lộ secret

Không ghi mật khẩu database trong script chia sẻ hoặc log. Dùng secret manager hoặc biến môi trường được bảo vệ. Đảm bảo logs chứa dữ liệu thử, không in dữ liệu cá nhân của bản sao production đã được ẩn danh hóa.

## 27. Ma trận kiểm thử đa DBMS

Với sản phẩm hỗ trợ nhiều DBMS, một bài thử trên PostgreSQL không chứng minh changelog chạy tốt trên MySQL hoặc SQL Server.

Bảng ma trận gợi ý:

| Kiểm thử | PostgreSQL | MySQL | SQL Server | Oracle |
|---|---|---|---|---|
| Validate changelog | Có | Có | Có | Có |
| SQL update đúng dialect | Xác minh | Xác minh | Xác minh | Xác minh |
| SQL rollback đúng dialect | Xác minh | Xác minh | Xác minh | Xác minh |
| Transaction và DDL behavior | Xác minh | Xác minh implicit commit | Xác minh ngoại lệ | Xác minh implicit commit |
| Up/down/up trên database cách ly | Có | Có | Có | Có |
| Assertion schema/data | Có | Có | Có | Có |
| Khả năng phục hồi khi lỗi giữa chừng | Thử theo rủi ro | Thử theo rủi ro | Thử theo rủi ro | Thử theo rủi ro |

Không nhất thiết chạy mọi DBMS nếu hệ thống chỉ hỗ trợ một DBMS. Nhưng nếu cùng changelog được chia sẻ giữa nhiều hệ, cần xác minh trên từng mục tiêu chính thức.

### 27.1. Phân biệt cú pháp rollback theo DBMS

Một rollback SQL như:

~~~sql
DROP INDEX idx_lab_order_note_order_id;
~~~

có thể chạy trên PostgreSQL nhưng có DBMS yêu cầu tên bảng/schema hoặc một cú pháp khác. Dùng change type Liquibase **dropIndex** khi được hỗ trợ để giảm lỗi dialect, rồi vẫn phải kiểm tra SQL generator đích.

## 28. Chỉ số và log cần lưu sau bài thử

Một báo cáo thử nghiệm đầy đủ nên chứa:

| Trường | Ví dụ nội dung |
|---|---|
| **Artifact changelog** | Commit hash hoặc build ID |
| **Liquibase version** | Phiên bản chạy thực tế |
| **DBMS/version** | PostgreSQL phiên bản được test |
| **JDBC driver/executor** | Driver và phương thức thực thi |
| **Database/schema đích** | Định danh môi trường thử nghiệm không chứa secret |
| **Danh sách pending ban đầu** | ID + AUTHOR + FILENAME |
| **S1 result** | Assertion schema/data sau update |
| **S0' result** | Assertion sau rollback |
| **S1' result** | Assertion sau update lại |
| **Rollback SQL reviewed** | Có/không, artifact hoặc log tương ứng |
| **EXECTYPE** | EXECUTED/MARK_RAN/RERAN nếu liên quan |
| **DEPLOYMENT_ID** | ID nhóm thao tác được ghi nhận, nếu có |
| **Tình huống lỗi** | Statement và nguyên nhân nếu thất bại |
| **Kết luận** | Pass/Fail theo các invariant cụ thể |

Không nên coi **DATEEXECUTED** hoặc **DEPLOYMENT_ID** sau re-update phải trùng lượt update đầu. Chúng là metadata của quá trình xử lý, không phải một phần bất biến của schema nghiệp vụ.

## 29. Case study: rollback thành công về mặt SQL nhưng dữ liệu bị mất

**Bối cảnh:** một changeset tạo bảng lưu phản hồi đơn hàng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-020-create-feedback"
      author: "orders-team"
      changes:
        - createTable:
            tableName: order_feedback
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
              - column:
                  name: feedback_text
                  type: varchar(1000)
      rollback:
        - dropTable:
            tableName: order_feedback
~~~

Trong kiểm thử disposable:

1. Update tạo bảng.
2. Rollback xóa bảng.
3. Re-update tạo lại bảng.

Kết quả kỹ thuật có thể PASS.

Nhưng trong production, sau update đã có khách hàng gửi phản hồi. Rollback bằng DROP TABLE xóa dữ liệu mới. Re-update tạo bảng rỗng **không khôi phục phản hồi**.

### 29.1. Kết luận từ case study

Phép thử up/down/up có thể xác nhận **khả năng tái tạo schema**, nhưng vẫn không đủ chứng minh **khôi phục nghiệp vụ**. Để rollback production an toàn, có thể cần:

- Giữ lại bảng cũ và chỉ thay đổi luồng đọc/ghi trong giai đoạn chuyển tiếp.
- Thêm cơ chế sao lưu hoặc xuất dữ liệu trước thay đổi phá hủy.
- Áp dụng expand–migrate–contract với khoảng thời gian tương thích.
- Chuẩn bị forward fix thay vì rollback phá hủy.
- Xác minh retention, backup/restore và yêu cầu tuân thủ dữ liệu.

## 30. Case study: precondition MARK_RAN che giấu migration thiếu

**Bối cảnh:** một changeset thêm cột **orders.status** có local precondition:

~~~yaml
preConditions:
  - onFail: MARK_RAN
  - onError: HALT
  - not:
      - columnExists:
          tableName: orders
          columnName: status
~~~

Nếu cột status đã tồn tại với **kiểu dữ liệu sai**, precondition fail và Liquibase có thể đánh dấu MARK_RAN mà không chạy thay đổi.

Một bài thử chỉ kiểm tra history hoặc exit code có thể PASS giả. Nhưng database không đạt hợp đồng kiểu cột yêu cầu.

**Cách thiết kế bài thử đúng:**

1. Kiểm tra định nghĩa thật của orders.status trong catalog.
2. Phân biệt EXECTYPE trong DATABASECHANGELOG.
3. Xác minh precondition phản ánh đủ giả định nghiệp vụ.
4. Chọn HALT khi trạng thái khác mong đợi cần được điều tra.
5. Chỉ dùng MARK_RAN khi trạng thái tương đương đã được xác minh bằng tiêu chí rõ.

## 31. Những lỗi thường gặp khi kiểm thử up/down/up

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| update-testing-rollback không được CLI nhận diện | Phiên bản/chế độ hỗ trợ khác | Kiểm tra help/tài liệu đúng bản; dùng quy trình thủ công nếu phù hợp |
| Update thành công, rollback không có SQL | Change type không hỗ trợ auto rollback hoặc thiếu custom rollback | Viết rollback có kiểm chứng; preview rollback |
| Rollback DROP TABLE làm mất dữ liệu | Rollback có tính phá hủy | Chỉ thử trên DB cách ly; thiết kế backup/forward fix |
| Sau rollback, re-update báo table exists | DDL còn sót do rollback fail/implicit commit | Kiểm tra catalog và history; reconciliation trước retry |
| Sau rollback, changeset không còn trong history | Liquibase đã gỡ bản ghi khi hoàn tác | Dùng log pipeline để kiểm toán sự kiện |
| Re-update không chọn changeset | Context/labels/dbms hoặc lịch sử không như dự kiến | Xem status và cấu hình runtime |
| SQL rollback sai thứ tự | Chưa xét phụ thuộc index/constraint/view | Sắp xếp rollback theo quan hệ phụ thuộc |
| EXECTYPE=MARK_RAN nhưng schema thiếu | Precondition đánh dấu mà không thực thi | Kiểm tra invariant, không chỉ đọc history |
| SQL DML chạy lại làm nhân đôi tác động | Thao tác không idempotent, runAlways/runOnChange | Thiết kế xử lý tập dữ liệu và marker an toàn |
| MySQL/Oracle không hoàn nguyên DDL như mong đợi | Implicit commit | Thiết kế rollback chủ động, tách changeset |
| PostgreSQL concurrent index còn invalid | Thao tác bị gián đoạn ngoài transaction | Kiểm tra catalog và xử lý index trước retry |
| Rollback-count chọn nhầm changeset | Có thay đổi khác được ghi nhận hoặc sai count | Dùng baseline cách ly và phạm vi xác minh rõ |
| CI thành công nhưng schema khác mong đợi | Không có assertion schema/data | So sánh invariant từng giai đoạn |
| Test pass trên H2 nhưng fail production | DBMS/dialect/transaction khác | Thử trên DBMS đích |
| Test bị lock do job khác | Nhiều pipeline dùng chung database | Cách ly database hoặc điều phối |
| Checksum mismatch sau khi sửa changeset cũ | Thay đổi nội dung đã triển khai | Dùng changeset mới, đối chiếu artifact cũ |

## 32. Bài thực hành tổng hợp: kiểm thử đầy đủ ba giai đoạn

**Mục tiêu:** dùng changelog **lab_order_note** ở phần trước để kiểm chứng cập nhật, hoàn tác và cập nhật lại trên PostgreSQL.

### Bước 1: chuẩn bị

- Tạo database PostgreSQL disposable, không chứa bảng/index thực hành.
- Đặt đúng connection properties và Liquibase version.
- Lưu changelog bài thực hành, bảo đảm đúng path được nạp.
- Chạy validate, status, history.
- Ghi nhận kết quả query **to_regclass**: bảng/index đều chưa có.

### Bước 2: xem SQL

- Chạy update-sql.
- Xem SQL rollback theo phạm vi mốc hoặc số changeset được kiểm soát.
- Xác nhận không có DDL lạ và thứ tự phụ thuộc hợp lệ.

### Bước 3: update đầu

~~~bash
liquibase --changelog-file=db/changelog/training.yaml update
~~~

Sau đó kiểm tra:

- Bảng và index tồn tại.
- Các cột và ràng buộc đạt hợp đồng.
- Hai changeset được DATABASECHANGELOG ghi nhận.
- Không có changeset không mong đợi trong log update.

### Bước 4: rollback

Dùng phương thức rollback đã được xác minh và đã xem SQL, ví dụ rollback theo số changeset trên môi trường thử nghiệm độc lập:

~~~bash
liquibase --changelog-file=db/changelog/training.yaml \
  rollback-count --count=2
~~~

Sau đó kiểm tra:

- Bảng và index không còn.
- Hai changeset không còn được ghi là đã áp dụng trong trạng thái DATABASECHANGELOG.
- Các đối tượng baseline khác vẫn nguyên vẹn.

### Bước 5: update lại

~~~bash
liquibase --changelog-file=db/changelog/training.yaml update
~~~

Kiểm tra lại toàn bộ hợp đồng schema của bước 3. Đối chiếu lịch sử, nhưng không yêu cầu timestamp/deployment ID giống lần trước.

### Bước 6: so sánh

Lập bảng:

| Assertion | Trước update | Sau update | Sau rollback | Sau re-update |
|---|---|---|---|---|
| Table tồn tại | false | true | false | true |
| Index tồn tại | false | true | false | true |
| Kiểu/cột đúng | Không áp dụng | PASS | Không áp dụng | PASS |
| Changeset recorded | 0 | 2 | 0 | 2 |
| Đối tượng baseline không đổi | PASS | PASS | PASS | PASS |

Nếu bất kỳ assertion nào fail, bài thử phải fail dù các lệnh Liquibase trước đó có exit code 0.

### Bước 7: thử lệnh tổng hợp

Nếu phiên bản Liquibase hỗ trợ, reset database thực hành về baseline rồi chạy:

~~~bash
liquibase --changelog-file=db/changelog/training.yaml \
  update-testing-rollback
~~~

Đối chiếu kết quả với chu trình thủ công. Lưu ý việc reset phải thực hiện bằng quy trình được phép, chỉ trên database disposable. Đừng dùng cách xóa hàng DATABASECHANGELOG thủ công để giả vờ trở về baseline.

## 33. Câu hỏi tự kiểm tra

**1. Vì sao cần update → rollback → update lại?**

Để xác minh cả đường áp dụng, đường đảo ngược và khả năng áp dụng lại thay đổi sau khi khôi phục baseline.

**2. Chu trình này có chứng minh dữ liệu production được bảo toàn không?**

Không. Một rollback có thể làm mất dữ liệu phát sinh sau update. Cần assertion dữ liệu và kế hoạch phục hồi riêng.

**3. update-testing-rollback có dùng an toàn trên production không?**

Không nên. Nó thực hiện các thao tác rollback thật; có thể gây gián đoạn hoặc phá hủy dữ liệu. Dùng trên database thử nghiệm cách ly.

**4. update-sql có thay thế chạy thử rollback không?**

Không. Nó chỉ sinh SQL dự kiến; không kiểm chứng transaction, quyền, lock và trạng thái dữ liệu thực tế.

**5. Rollback transaction và Liquibase rollback khác nhau thế nào?**

Transaction rollback hoàn nguyên những thay đổi chưa commit trong transaction được DBMS hỗ trợ. Liquibase rollback thực thi những thay đổi đảo ngược theo kế hoạch migration.

**6. Nếu sau rollback không còn bản ghi changeset trong DATABASECHANGELOG, có nghĩa changeset chưa từng chạy?**

Không. Rollback có thể gỡ bản ghi lịch sử, nên cần log CI/CD để kiểm toán mọi sự kiện.

**7. Vì sao re-update thất bại trên MySQL sau khi một update lỗi?**

Có thể vì DDL đã implicit commit, để lại đối tượng dù changeset chưa được ghi hoàn tất.

**8. Vì sao không nên dùng onFail:MARK_RAN để cho bài thử dễ PASS?**

Vì nó có thể đánh dấu đã xử lý mà không chạy SQL, làm lịch sử có vẻ đúng trong khi schema sai.

**9. Vì sao rollback-count cần được dùng cẩn thận?**

Vì số changeset gần nhất có thể khác dự đoán nếu database có hoạt động khác hoặc filter thay đổi.

**10. Sau re-update, DATEEXECUTED có phải khớp lần đầu không?**

Không. Timestamp và deployment ID là metadata của lần xử lý, không phải invariant schema.

**11. Một view CREATE OR REPLACE có thể rollback bằng DROP VIEW trong mọi trường hợp không?**

Không. Nếu view đã tồn tại trước migration, DROP VIEW sẽ xóa nó thay vì khôi phục định nghĩa trước đó.

**12. CI nên kiểm tra gì ngoài exit code?**

Schema và dữ liệu thực tế, lịch sử changeset, phạm vi rollback, SQL dự kiến, tính lặp lại và các invariant đã được xác định.

## 34. Checklist hoàn chỉnh trước khi phê duyệt rollback

- [ ] Đã xác định database thử nghiệm hoặc bản sao được phép dùng cho thao tác phá hủy.
- [ ] Đã xác nhận JDBC URL, schema metadata, user, Liquibase/driver/DBMS version.
- [ ] Changelog artifact và tập changeset pending đã được cố định.
- [ ] Đã ghi baseline S0 và các invariant cần giữ.
- [ ] Đã chạy validate và review update-sql.
- [ ] Đã review rollback SQL theo phạm vi được xác minh.
- [ ] Không chọn rollback-count bằng số lượng phỏng đoán trên database dùng chung.
- [ ] Đã phân biệt rollback của Liquibase với transaction rollback và backup/restore.
- [ ] Đã xét DDL implicit commit và các thao tác yêu cầu runInTransaction:false.
- [ ] Có custom rollback cho những SQL/change types không hỗ trợ auto rollback.
- [ ] Đã đánh giá mất dữ liệu, phụ thuộc và side effect ngoài database.
- [ ] Có assertion schema/data sau S1, S0' và S1'.
- [ ] Đã kiểm tra ID/AUTHOR/FILENAME và EXECTYPE trong DATABASECHANGELOG.
- [ ] Đã chú ý MARK_RAN, runAlways, runOnChange và thay đổi filter.
- [ ] Đã thử update lần hai khi không rollback nếu kịch bản yêu cầu.
- [ ] Có phương án khi rollback thất bại giữa chừng, không retry mù.
- [ ] CI chạy trên database cách ly, không có job migration cạnh tranh.
- [ ] Có log CI/CD để theo dõi cả những changeset đã rollback và không còn trong history.
- [ ] Đã thử trên DBMS thực tế được hỗ trợ, không chỉ H2 hoặc mock.
- [ ] Không sửa changeset cũ hay DATABASECHANGELOG để che checksum/identity.
- [ ] Có backup/restore hoặc forward fix đã được kiểm chứng cho thay đổi rủi ro cao.
- [ ] Không dùng phép thử up/down/up để tác động production đang phục vụ người dùng.

**Kết luận:** Kiểm thử **cập nhật → hoàn tác → cập nhật lại** giúp xác minh hai chiều của migration và khả năng tái áp dụng changeset sau khi trở về baseline. Lệnh **update-testing-rollback** là phương tiện thuận tiện khi được Liquibase phiên bản dự án hỗ trợ; quy trình thủ công cho phép quan sát và kiểm tra sâu ở từng giai đoạn. Dù dùng cách nào, tiêu chí thành công phải dựa trên **SQL đã được review, trạng thái schema/dữ liệu, lịch sử DATABASECHANGELOG và những invariant nghiệp vụ** — không chỉ dựa vào exit code. Cách tiếp cận này làm tăng khả năng phát hiện lỗi rollback trước production và xây dựng quy trình phục hồi migration có kiểm chứng qua nhiều môi trường.

