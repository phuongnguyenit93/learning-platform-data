# Chuẩn hóa chuỗi kiểm tra trước và sau mỗi lần cập nhật bằng Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng **changelog**, **changeset**, **precondition**, **checksum** và lịch sử triển khai, đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Kiểm tra và cập nhật** này xây dựng một quy trình kiểm soát lặp lại được cho **mỗi lần chạy Liquibase update**: xác minh trước khi chạy, xem trước thay đổi, áp dụng có giám sát, đối chiếu kết quả và lưu bằng chứng triển khai.

Điều cần chuẩn hóa không chỉ là tập hợp vài lệnh. Một lần update đáng tin cậy phải trả lời được sáu câu hỏi: **Đang tác động đúng database nào?** **Changelog nào sắp được áp dụng?** **Schema và dữ liệu hiện có đáp ứng giả định chưa?** **SQL dự kiến có chấp nhận được không?** **Sau chạy, database có đạt trạng thái kỳ vọng không?** **Nếu lỗi, có thể phân biệt phần đã áp dụng và phần chưa áp dụng để phục hồi không?**

Mục tiêu là biến những câu hỏi đó thành các **cổng kiểm tra (gates)** có kết quả PASS/FAIL, người chịu trách nhiệm, tiêu chí dừng và chứng cứ. Các ví dụ sử dụng PostgreSQL và Liquibase CLI; có thể áp dụng ý tưởng cho DBMS khác nhưng phải điều chỉnh SQL, quyền, tính giao dịch của DDL và câu lệnh theo phiên bản Liquibase thực tế.

## 1. Phân biệt kiểm tra trước, trong và sau update

Một lần triển khai có thể chia thành năm pha:

~~~text
[1] Xác định đích + snapshot trạng thái
        |
        v
[2] Kiểm tra changelog + điều kiện dữ liệu + xem SQL
        |
        v
    GATE PRE: cho phép cập nhật?
        |
   PASS | FAIL ---> DỪNG, điều tra, không tự bỏ qua
        v
[3] Liquibase update (giám sát log/lock/error)
        |
        v
[4] Kiểm tra lịch sử + schema + dữ liệu + ứng dụng
        |
        v
    GATE POST: đạt trạng thái kỳ vọng?
        |
   PASS | FAIL ---> CÔ LẬP, RECONCILE, ROLLBACK/FORWARD-FIX
        v
[5] Lưu chứng cứ, cho phép phát hành bước tiếp theo
~~~

**Preflight** là các bước trước thay đổi, gồm nhận diện database, quyền, version công cụ, lịch sử Liquibase, dữ liệu hiện tại và SQL dự kiến. **Runtime monitoring** quan sát quá trình thực thi: log, thời gian, lock, timeout và lỗi. **Postflight** xác minh hậu điều kiện sau update, không chỉ nhìn exit code. Một pipeline chỉ dùng lệnh update rồi in chữ “SUCCESS” chưa có đủ bằng chứng schema/dữ liệu đã đúng.

Precondition trong changelog là một phần của preflight tại thời điểm Liquibase đánh giá changeset, nhưng không thay thế được toàn bộ kiểm tra trước và sau. Ví dụ, precondition **tableExists** không khẳng định bảng có đủ constraint, index hoặc dữ liệu mong muốn.

### Nguyên tắc nền tảng

- Một lần phát hành sử dụng **một bộ changelog đã được review**, có commit hoặc artifact ID xác định; không sửa changeset đã triển khai ở môi trường dùng chung.
- Các bước kiểm tra phải chạy trên **cùng database/schema đích**, với chính sách context, label và tham số tương ứng lần update thật.
- Mỗi kiểm tra phải có **kỳ vọng rõ ràng**: không phát hiện lỗi, số lượng đối tượng dự kiến, giá trị dữ liệu, ứng dụng khởi động và đọc/ghi được.
- Khi kiểm tra bắt buộc không đạt, **dừng** thay vì tự sửa bảng DATABASECHANGELOG, xóa checksum, MARK_RAN hoặc bỏ precondition cho pipeline xanh.
- Nếu thay đổi đã bắt đầu và thất bại, **đối chiếu trạng thái thực tế trước khi chạy lại**; không mặc định mọi DDL đã rollback nguyên tử.

## 2. Định nghĩa đầu vào chuẩn của một lần triển khai

Trước khi gọi Liquibase, nhóm cần mô tả bản triển khai bằng tập thông tin có thể truy vết:

| Thông tin | Ví dụ | Mục đích kiểm soát |
|---|---|---|
| Release/artifact ID | customer-service build 2026.11.19.1 | Biết mã nguồn, changelog nào được dùng |
| Commit changelog | Git SHA của bản đã review | Tránh thay đổi file giữa preview và update |
| DBMS/phiên bản | PostgreSQL 16 | Đánh giá cú pháp và transactional DDL |
| Database/schema đích | customer_db / public | Tránh chạy vào nhầm môi trường |
| Changelog root | db/changelog/db.changelog-master.yaml | Có một đầu vào migration rõ ràng |
| Contexts/labels | Tập giá trị của environment | Xác định changeset nào được chọn |
| Liquibase/JDBC version | Phiên bản đã cố định trong image CI | Giảm khác biệt behavior/checksum |
| Tài khoản migration | customer_migrator | Quyền DDL, không phải tài khoản ứng dụng |
| Backup/khả năng phục hồi | Snapshot hoặc PITR đã được xác minh | Có đường phục hồi khi thay đổi nguy hiểm |
| Người/điều kiện phê duyệt | Gate của CI/CD | Kiểm soát production và thay đổi rủi ro cao |

Các giá trị nhạy cảm như password, token, URL chứa credential không được đưa vào commit hoặc log. Kết quả kiểm tra có thể cần ghi database/schema/host để nhận diện đích, nhưng không công bố thông tin kết nối bí mật trong artifact mở cho mọi người.

Một quy trình nhiều môi trường nên dùng **cùng changelog đã review** để promote từ test sang staging và production. Kết nối, secret và context/label có thể khác có chủ đích; sự khác biệt phải được khai báo và kiểm soát, không chỉnh sửa SQL của changeset cũ theo từng môi trường.

## 3. Gate đầu tiên: xác nhận đúng database và quyền truy cập

Lỗi nguy hiểm nhất là cập nhật đúng changelog trên **sai database**. Trước khi đọc trạng thái schema, cần xác nhận connection target bằng chính phiên kết nối hoặc cách truy vấn tương đương được pipeline sử dụng.

Ví dụ PostgreSQL:

~~~sql
SELECT
    current_database() AS db_name,
    current_schema() AS current_schema,
    current_user AS connected_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version;
~~~

Truy vấn này giúp nhận diện database, role, schema mặc định và thông tin server trong điều kiện kết nối phù hợp. Nếu kết nối qua proxy, Unix socket hoặc môi trường managed, một số trường có thể NULL hoặc không tương ứng trực tiếp hostname cấu hình; do đó nên so sánh với **danh tính môi trường đáng tin cậy** của hệ thống triển khai, không chỉ so sánh một giá trị.

Tài khoản migration cần đủ quyền cho change type sắp chạy và để Liquibase quản lý bảng metadata. Không dùng superuser thường xuyên chỉ để tránh lỗi quyền. Có thể tách tài khoản migration và tài khoản runtime ứng dụng: runtime không cần quyền tạo/xóa bảng nếu Liquibase quản lý toàn bộ schema.

**Điều kiện dừng:** database/schema/role không trùng mục tiêu đã được phê duyệt; không xác định được server; hoặc quyền chưa đủ cho thay đổi được review. Không “sửa nhanh” bằng cách đổi URL hay tăng quyền ngay giữa pipeline mà không xem lại phạm vi.

## 4. Gate preflight: kiểm tra trạng thái Liquibase và changelog

Trước update, cần đối chiếu ba nguồn sự thật:

1. **Changelog trong artifact**: tập changeset định thực hiện và định nghĩa được review.
2. **DATABASECHANGELOG**: lịch sử đã ghi nhận trong database đích.
3. **Schema/dữ liệu thực tế**: những đối tượng và dữ liệu đang tồn tại.

Chỉ một trong ba nguồn không đủ. Ví dụ: DATABASECHANGELOG có dòng changeset tạo index, nhưng index đã bị xóa bằng SQL thủ công; Liquibase vẫn có thể xem changeset là đã chạy. Ngược lại, bảng tồn tại nhưng changeset chưa được ghi nhận có thể là dấu hiệu một migration thủ công hoặc lần chạy dở.

### Những lệnh Liquibase thường dùng

Sau khi cấu hình changelog, JDBC driver, URL và credentials đúng, quy trình CLI mẫu là:

~~~shell
liquibase --version
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

- **liquibase --version**: xác nhận công cụ đang dùng, hữu ích khi nhiều máy có phiên bản khác nhau.
- **validate**: kiểm tra cấu trúc changelog, một số thuộc tính/tham chiếu và tính hợp lệ mà Liquibase có thể xác minh; có thể phát hiện những vấn đề liên quan lịch sử/checksum. **PASS không chứng minh SQL luôn chạy được trên database thật.**
- **status --verbose**: hỗ trợ nhìn changeset nào còn chưa được ghi nhận áp dụng; cách thể hiện có thể phụ thuộc version và loại changeset.
- **update-sql**: sinh SQL dự kiến cho update mà không áp dụng thay đổi. Đây là đầu vào review, nhưng không hoàn toàn mô phỏng mọi tác động runtime, lock, dữ liệu cạnh tranh hoặc precondition trong mọi chế độ.

**Tùy phiên bản Liquibase CLI, dạng viết/tùy chọn lệnh có thể khác**, chẳng hạn các tham số toàn cục, context filter hoặc vị trí options. Hãy cố định và kiểm tra cú pháp phiên bản tổ chức đang dùng. Điều quan trọng là cùng tham số đích và bộ lọc phải được sử dụng giữa validate, status, preview và update.

Trên database chưa chạy Liquibase bao giờ, **DATABASECHANGELOG** và **DATABASECHANGELOGLOCK** có thể chưa tồn tại. Việc thiếu bảng metadata lúc khởi tạo không tự động là sự cố. Ngược lại, với database đã được quản lý, sự biến mất bất thường của các bảng này là dấu hiệu cần điều tra thay vì tạo lại lịch sử từ đầu.

## 5. Gate preflight: kiểm tra dữ liệu và schema theo từng migration

**validate** không thể đoán mọi giả định nghiệp vụ. Mỗi release phải bổ sung các kiểm tra liên quan đến thay đổi đang triển khai, lý tưởng dùng một bộ câu SQL có đầu ra rõ ràng.

Giả sử sắp chuyển cột **customer.status** từ nullable sang NOT NULL. Cần xác nhận bảng/cột tồn tại, không có dữ liệu NULL và các writer hiện tại sẽ không tiếp tục ghi NULL.

Trước migration, có thể kiểm tra cấu trúc PostgreSQL:

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customer'
  AND column_name = 'status';
~~~

Và kiểm tra dữ liệu:

~~~sql
SELECT COUNT(*) AS null_status_count
FROM public.customer
WHERE status IS NULL;
~~~

**Kỳ vọng:** truy vấn schema trả đúng một dòng cho cột cần thay đổi, và **null_status_count = 0** khi sắp thêm NOT NULL. Nếu vẫn có NULL, phải thực hiện bước backfill phù hợp trước. Cần kiểm tra ứng dụng phiên bản cũ có thể tiếp tục tạo NULL trong lúc triển khai hay không; đếm 0 tại một thời điểm **không** loại trừ dữ liệu mới xuất hiện sau đó.

Tương tự, trước khi:

- **Thêm UNIQUE**: truy vấn bản ghi trùng theo tập cột và cách xử lý NULL/collation của DBMS.
- **Thêm FOREIGN KEY**: tìm bản ghi con mồ côi không có parent hợp lệ.
- **Xóa cột/bảng**: kiểm tra code, view, job, trigger và các phiên bản ứng dụng đang phụ thuộc.
- **Thêm index lớn**: đánh giá dữ liệu, index cùng tên, lock, độ lớn bảng và tài nguyên.
- **Đổi kiểu dữ liệu**: kiểm tra giá trị không thể chuyển đổi, giới hạn độ dài, overflow hoặc tràn độ chính xác.
- **Backfill**: ước lượng số hàng, batch size, thời gian, idempotency và chiến lược retry.

Mỗi preflight nên ghi rõ **query + expectedResult + cách xử lý khi FAIL**, thay vì chỉ lưu câu truy vấn không có tiêu chí thành công.

## 6. Đưa điều kiện quan trọng vào changeset bằng precondition

Kiểm tra SQL bên ngoài giúp CI quyết định có cho phép update, còn **preConditions** trong changelog bảo vệ giả định **ngay trước khi Liquibase thực thi changeset**.

Ví dụ changeset PostgreSQL yêu cầu bảng customer và cột status đã có, đồng thời không còn NULL trước khi thêm ràng buộc:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 030-customer-status-not-null
      author: database-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - onFailMessage: "Con customer.status NULL hoac thieu schema yeu cau"
        - onErrorMessage: "Khong the kiem tra customer.status"
        - tableExists:
            schemaName: public
            tableName: customer
        - columnExists:
            schemaName: public
            tableName: customer
            columnName: status
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM public.customer
              WHERE status IS NULL
      changes:
        - addNotNullConstraint:
            schemaName: public
            tableName: customer
            columnName: status
            columnDataType: varchar(30)
      rollback:
        - dropNotNullConstraint:
            schemaName: public
            tableName: customer
            columnName: status
            columnDataType: varchar(30)
~~~

Giải thích hai nhánh lỗi:

- **onFail: HALT**: điều kiện đánh giá thành công nhưng false (ví dụ COUNT(*) khác 0); migration dừng thay vì áp đặt ràng buộc lên dữ liệu chưa hợp lệ.
- **onError: HALT**: chính bước đánh giá gặp lỗi (ví dụ SQL sai hoặc không đủ quyền truy vấn); migration cũng dừng vì không thể xác nhận an toàn.

Precondition không xử lý lỗi phát sinh trong phần **changes**. Dù COUNT(*) bằng 0 ở lúc kiểm tra, một writer có thể thêm hàng NULL trước lúc DDL chạy; database vẫn có thể từ chối ràng buộc. Kiểm soát thay đổi đồng thời, thứ tự phát hành ứng dụng và kiểm tra sau migration vẫn là bắt buộc.

Không mặc định dùng **MARK_RAN** hoặc **CONTINUE** chỉ để bỏ qua điều kiện chưa đạt. MARK_RAN ghi changeset là đã xử lý mà không thực thi changes; CONTINUE bỏ qua để xem xét lần sau. Chúng chỉ có ý nghĩa khi nghiệp vụ và kế hoạch triển khai đã xác định rõ việc bỏ qua là hợp lệ.

## 7. Gate plan: xem chính xác thay đổi dự kiến trước khi chạy

Bước **update-sql** nên được đặt sau khi validate và xác nhận danh tính môi trường. Đầu ra cần được review theo rủi ro, không chỉ tìm xem SQL có lỗi cú pháp.

Một checklist review SQL dự kiến:

| Câu hỏi review | Vì sao quan trọng |
|---|---|
| Chỉ có changeset dự kiến? | Tránh kéo theo migration chưa được phê duyệt |
| Đúng schema và tên đối tượng? | Tránh thay nhầm bảng ở schema khác |
| Có DROP/TRUNCATE/DELETE không? | Có thể mất dữ liệu hoặc phụ thuộc quan trọng |
| ALTER TABLE có khóa hoặc rewrite bảng không? | Có thể chặn request và kéo dài downtime |
| Có thao tác ngoài transaction không? | Cần runInTransaction phù hợp và runbook partial failure |
| Có backfill lớn không? | Cần batch, giám sát và giới hạn tải |
| Có thay đổi quyền/extension/procedure không? | Cần xác nhận privilege, an ninh và dependency |
| Rollback dự kiến có thực sự phục hồi được không? | DDL rollback không đồng nghĩa khôi phục dữ liệu đã thay đổi |
| Tham số context/label có đúng không? | Có thể chọn sai tập changeset |
| Thay đổi có tương thích ứng dụng cũ và mới không? | Bảo vệ rolling deployment |

**Không coi preview là hợp đồng tuyệt đối rằng SQL runtime sẽ giống từng dòng.** Dữ liệu, trạng thái lock, context, precondition, DBMS và cấu hình có thể làm kết quả khác đi. Giữa lúc preview và update, không được đổi artifact hoặc connection target mà không lặp lại gate phù hợp.

Đối với production, có thể cần người review hoặc policy phê duyệt dựa trên SQL dự kiến, mức độ nguy hiểm, thời gian bảo trì và khả năng phục hồi. Kết quả phê duyệt phải gắn với commit và môi trường cụ thể, không áp dụng vô hạn cho những bản build khác.

## 8. Chuẩn hóa một bản ghi preflight PASS/FAIL

Một mẫu bằng chứng trước update nên ngắn nhưng đủ kiểm chứng, ví dụ:

~~~text
RELEASE_ID: customer-service-2026.11.19.1
CHANGELOG_COMMIT: <reviewed-commit>
DBMS: PostgreSQL
TARGET_DATABASE: customer_db
TARGET_SCHEMA: public
TARGET_ROLE: customer_migrator

PREFLIGHT:
  connection_target: PASS
  liquibase_version_pinned: PASS
  changelog_validate: PASS
  checksum_conflict: NONE_DETECTED
  pending_changesets: REVIEWED
  business_preconditions: PASS
  backup_or_restore_plan: VERIFIED
  sql_preview: REVIEWED
  deployment_lock_conflict: NONE_DETECTED

DECISION: APPROVED_FOR_UPDATE
~~~

Đây là **mẫu báo cáo**, không phải một file bắt buộc phải tạo trong repository. Nếu pipeline sử dụng artifact log, lưu nó ở hệ thống CI/CD được phép và tránh thông tin bí mật.

Đối với một số hệ thống, gate có thể có **waiver** cho trường hợp đã được phê duyệt, ví dụ index cần được tạo trong cửa sổ bảo trì. Waiver cần người phê duyệt, lý do, thời hạn và bằng chứng; không được biến thành cơ chế tắt kiểm tra mặc định.

## 9. Pha thực thi: chạy update có giám sát

Sau khi preflight và review SQL đạt yêu cầu, mới gọi lệnh:

~~~shell
liquibase update
~~~

Trong CI/CD, cần lưu ít nhất: thời điểm bắt đầu/kết thúc, ID job, release ID, phiên bản Liquibase, database đích theo định danh an toàn, changeset đã thực thi, lỗi nếu có và trạng thái của job. Không đưa password hoặc secrets vào tham số/log có thể bị hiển thị công khai.

**DATABASECHANGELOGLOCK** giúp Liquibase điều phối các lần cập nhật schema, nhưng không khóa toàn bộ traffic ứng dụng hoặc ngăn mọi thao tác SQL đồng thời. Một job đang giữ lock có thể là migration hợp lệ đang chạy lâu; không được tự giải phóng lock chỉ vì pipeline chờ quá lâu.

Các điểm giám sát quan trọng gồm thời gian DDL, DB lock waits, long-running transactions, CPU/IO, replication lag, dung lượng transaction log, lỗi JDBC và timeout của job. Một update chậm cần được phân tích trên DBMS cụ thể, không mặc định tăng timeout vô hạn.

Khi **runInTransaction: false** hoặc DBMS có DDL implicit commit, lỗi có thể để lại thay đổi đã áp dụng một phần trong khi lịch sử Liquibase chưa ghi nhận đầy đủ. Vì thế, nếu update thất bại, **không retry mù**. Phải tiến hành quy trình reconcile trạng thái trước.

## 10. Gate postflight: kiểm tra lịch sử Liquibase

Thành công ở mức lệnh chỉ là một tín hiệu. Sau update, cần đọc **DATABASECHANGELOG** để xác minh changeset dự kiến đã được ghi nhận với định danh phù hợp:

~~~sql
SELECT
    id,
    author,
    filename,
    exectype,
    md5sum,
    dateexecuted,
    orderexecuted
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Ví dụ truy vấn cụ thể cho changeset ở mục 6:

~~~sql
SELECT
    id, author, filename, exectype, md5sum, dateexecuted
FROM public.databasechangelog
WHERE id = '030-customer-status-not-null'
  AND author = 'database-team';
~~~

**Kỳ vọng:** tìm thấy changeset ở đúng file/đường dẫn logical tương ứng và có trạng thái thực thi phù hợp. Không dựa vào id riêng lẻ nếu các changelog khác có thể dùng cùng id; định danh Liquibase gồm **id + author + đường dẫn changelog**.

Cần hiểu một số loại trạng thái:

- **EXECUTED**: Liquibase ghi nhận changeset đã thực thi.
- **RERAN**: có thể xuất hiện khi một changeset được thiết kế chạy lại, chẳng hạn runAlways/runOnChange.
- **MARK_RAN**: changeset được đánh dấu đã xử lý mà không thực hiện nội dung changes; không đồng nghĩa DDL/DML kỳ vọng đã chạy.

Các bảng metadata và tên schema thực tế có thể đã được tùy chỉnh thông qua cấu hình Liquibase. Truy vấn trên giả định metadata nằm trong **public**, đúng với nhiều cài đặt PostgreSQL nhưng không phải tất cả.

**Checksum** trong MD5SUM giúp nhận diện changeset đã chạy có bị thay đổi theo quy tắc Liquibase hay không. Nó không xác nhận schema thực tế khớp 100%. Không sửa trực tiếp DATABASECHANGELOG hay dùng **clear-checksums** để che khác biệt nếu chưa điều tra nguyên nhân.

Sau update có thể gọi lại **liquibase status --verbose**, nhưng điều kiện “không còn pending” cần được hiểu cùng contexts, labels và các changeset có cơ chế **runAlways**; không nên dùng một phép so sánh chuỗi đầu ra máy móc làm tiêu chí duy nhất.

## 11. Gate postflight: kiểm tra schema và dữ liệu thật

Cùng với kiểm tra lịch sử, phải xác minh **hậu điều kiện (postconditions)** theo đối tượng mà release thay đổi. Với ví dụ thêm NOT NULL:

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customer'
  AND column_name = 'status';
~~~

**Kỳ vọng:** một dòng cho **status**, kiểu dữ liệu đúng thiết kế và **is_nullable = NO**.

Tiếp theo:

~~~sql
SELECT COUNT(*) AS null_status_count
FROM public.customer
WHERE status IS NULL;
~~~

**Kỳ vọng:** **null_status_count = 0**. Điều này kiểm tra trạng thái dữ liệu thực tế, không chỉ metadata. Nếu thay đổi cần bảo đảm thêm giá trị hợp lệ, cần có truy vấn kiểm tra domain hoặc constraint tương ứng.

Các hậu điều kiện thường gặp:

| Loại thay đổi | Hậu điều kiện quan trọng |
|---|---|
| **createTable** | Bảng tồn tại đúng schema, cột/kiểu/constraint và quyền truy cập |
| **addColumn** | Cột đúng kiểu, nullability/default, ứng dụng cũ và mới cùng đọc/ghi được |
| **addUniqueConstraint** | Constraint tồn tại, không có dữ liệu trùng vi phạm quy tắc DBMS |
| **addForeignKeyConstraint** | FK tồn tại với đúng cột, action ON UPDATE/DELETE, không còn dữ liệu mồ côi |
| **createIndex** | Index đúng cột/biểu thức và trạng thái hợp lệ; hiệu năng được đo khi cần |
| **backfill** | Đếm bản ghi mục tiêu, đối chiếu số lượng chuyển đổi, không mất dữ liệu |
| **view/function/trigger** | Định nghĩa đã cập nhật và thử hành vi bằng dữ liệu mẫu |
| **phân quyền** | Vai trò runtime có quyền cần, không cấp quyền quá rộng |

Đối với PostgreSQL **CREATE INDEX CONCURRENTLY**, một index cùng tên có thể tồn tại nhưng **invalid** nếu tạo thất bại. Vì vậy, ngoài tên còn cần kiểm tra **pg_index.indisvalid** và định nghĩa index. Với các DBMS khác, phải dùng metadata phù hợp thay vì sao chép SQL PostgreSQL.

Không nên chỉ kiểm tra trên một kết nối có quyền admin. Hãy dùng role runtime của ứng dụng để xác nhận việc truy cập sau thay đổi; một schema đúng nhưng tài khoản ứng dụng không đọc/ghi được vẫn là phát hành lỗi.

## 12. Kiểm tra tương thích ứng dụng sau migration

Postflight phải xem **database + ứng dụng** là một hệ thống. Một cột được thêm thành công không có nghĩa ứng dụng khởi động đúng hoặc xử lý dữ liệu mới.

Sau thay đổi, nên xác minh:

1. **Ứng dụng khởi động:** Spring Boot không bị lỗi khi khởi tạo datasource, Hibernate mapping hoặc Liquibase.
2. **Hợp đồng dữ liệu:** các truy vấn chính trả đúng schema, dữ liệu và kiểu giá trị.
3. **Đường đọc/ghi trọng yếu:** tạo bản ghi, sửa bản ghi và đọc lại qua API/DAO, với dữ liệu thử nghiệm cô lập.
4. **Phiên bản chạy song song:** ứng dụng cũ và mới đều tương thích trong giai đoạn rolling deployment.
5. **Quan sát vận hành:** exception rate, latency, lock wait, lỗi unique/FK và replication lag không tăng bất thường.
6. **Cleanup:** dữ liệu kiểm thử hoặc transaction test được thu dọn an toàn, không xóa dữ liệu nghiệp vụ thật.

Ví dụ: sau khi đổi **customer.status** sang NOT NULL, ứng dụng cũ còn thực thi INSERT không cung cấp status sẽ bắt đầu lỗi nếu không có default hợp lệ. Đó là lý do phải thay đổi theo chiến lược **expand → backfill → verify → enforce → contract**, không luôn gộp tất cả trong một release.

Một **smoke test** đọc/ghi thành công là bằng chứng hữu ích nhưng không chứng minh mọi nghiệp vụ đúng. Với ràng buộc quan trọng, cần kiểm thử cả trường hợp lỗi như chèn NULL bị từ chối và việc xử lý lỗi ở ứng dụng đúng như thiết kế.

## 13. Một pipeline chuẩn có thể trông như thế nào?

Sơ đồ tổng quát:

~~~text
PR: lint/validate changelog
  -> database test: update + postflight
  -> build artifact bất biến
  -> staging: preflight + SQL review + update + postflight
  -> approval cho production
  -> production: target check + preflight
  -> review SQL tương ứng chính target
  -> Liquibase update
  -> DATABASECHANGELOG + schema/data checks
  -> application smoke tests + metrics
  -> lưu release evidence / hoàn tất
~~~

Các bước chính cần được triển khai thành **job có exit status rõ ràng**, tránh chỉ in log mà vẫn trả code 0 khi kiểm tra thất bại. Ví dụ, một truy vấn COUNT(*) trả **17** là thực thi SQL thành công ở mức kỹ thuật, nhưng phải được đánh dấu **FAIL** nếu điều kiện kỳ vọng là 0.

Ví dụ mô tả gate theo dạng giả mã (không phải pipeline thực thi nguyên vẹn):

~~~text
assert target_database == approved_target
assert pinned_liquibase_version == expected_version
assert validate_changelog() == PASS
assert history_and_checksum_policy() == PASS
assert required_preflight_queries() == PASS
preview_sql = generate_update_sql()
assert review(preview_sql, release_id) == APPROVED

result = run_liquibase_update()
if result != SUCCESS:
    stop_deployment()
    reconcile_real_db_state_with_liquibase_history()
    select_recovery_or_forward_fix()
else:
    assert expected_changesets_recorded() == PASS
    assert schema_postconditions() == PASS
    assert data_postconditions() == PASS
    assert runtime_permissions_and_smoke_tests() == PASS
    record_release_evidence()
~~~

Điểm mấu chốt: **preflight hoặc postflight FAIL phải có tác động lên quyết định phát hành**. Nếu một bước kiểm tra chỉ ghi cảnh báo mà hệ thống vẫn tiếp tục triển khai bất chấp vi phạm ràng buộc bắt buộc, gate đó không thực hiện chức năng kiểm soát.

## 14. Spring Boot: ai sở hữu bước chạy Liquibase?

Spring Boot có thể chạy Liquibase trong quá trình khởi động ứng dụng khi dependency và cấu hình phù hợp:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

**Ưu điểm:** changelog gắn với artifact ứng dụng, dễ đồng bộ migration và code trong môi trường đơn giản. **Giới hạn:** khi migration chạy lâu hoặc cần review/approval production, việc chạy ngay khi nhiều replica khởi động khiến rollout, timeout và quan sát trạng thái phức tạp hơn.

Trong môi trường triển khai nhiều instance hoặc cần bảo vệ dữ liệu nghiêm ngặt, có thể dùng **job migration riêng trong CI/CD**: job lấy đúng artifact, chạy các gate trước/sau, rồi mới cho ứng dụng khởi động phiên bản mới. Khi đó ứng dụng runtime cần được cấu hình để không tự thực thi migration ngoài kế hoạch, chẳng hạn đặt **spring.liquibase.enabled=false** trong profile phù hợp.

Đừng để pipeline chạy update còn mọi replica cũng chủ động chạy update cùng bộ changelog mà không xác định vai trò. **DATABASECHANGELOGLOCK** phối hợp các tiến trình Liquibase, nhưng không thay thế được bước phê duyệt và kiểm chứng hậu điều kiện.

Nếu chọn mô hình Spring Boot tự migration, vẫn cần cách thực hiện các gate pre/post ngoài tiến trình ứng dụng, cùng log và cách chặn phát hành khi postflight chưa đạt. Không được coi việc ứng dụng khởi động thành công là bằng chứng đủ cho mọi biến đổi dữ liệu.

## 15. Kiểm tra trên nhiều môi trường và phát hiện drift

Khác biệt môi trường thường đến từ các nguồn:

- Changelog bị sửa sau khi một môi trường đã chạy changeset.
- Một DBA tạo index/cột bằng SQL thủ công.
- Contexts/labels khác nhau khiến tập changeset áp dụng khác.
- Schema/search path hoặc quyền của tài khoản migration không giống nhau.
- Dữ liệu lịch sử khác nhau, làm precondition/backfill có kết quả khác.
- DBMS version hoặc extension khác nhau, làm SQL có ngữ nghĩa khác.
- Một release triển khai dở ở staging rồi vẫn được promote.

Không thể giải quyết toàn bộ drift chỉ bằng một truy vấn DATABASECHANGELOG. Cần kết hợp **đối chiếu lịch sử**, **metadata schema**, **truy vấn dữ liệu**, **smoke test** và khi phù hợp là công cụ **diff/snapshot**. Liquibase có các khả năng so sánh database ở những phiên bản/sản phẩm phù hợp, nhưng kết quả diff cần được review; không tự động coi mọi khác biệt là lỗi hoặc tự sửa production mà không hiểu nguyên nhân.

Để tránh drift tái diễn, nên buộc mọi thay đổi schema được review qua changelog, hạn chế DDL thủ công, lưu commit ID của bản đã chạy và dùng cùng artifact qua các môi trường.

**Chú ý với runAlways/runOnChange:** một changeset được cấu hình chạy lại có thể không mang hành vi “chạy đúng một lần”. Tiêu chí postflight phải xét logic của từng loại changeset, không mặc định số lần chạy hay số dòng lịch sử bằng số lần gọi update.

## 16. Khi preflight hoặc update thất bại: dừng và phân loại

| Tình huống | Biểu hiện | Cách xử lý phù hợp |
|---|---|---|
| **Sai database/schema** | Danh tính đích khác approved target | Dừng ngay, không chạy SQL; sửa cấu hình qua review |
| **Changelog validate lỗi** | Cú pháp, include, định danh, checksum bất thường | Sửa nguyên nhân ở mã nguồn/migration mới; không làm yếu kiểm soát |
| **Precondition fail** | Database không đạt điều kiện đã đánh giá | Kiểm tra dữ liệu/schema và kế hoạch chuyển tiếp |
| **Precondition error** | Không thể đánh giá điều kiện do lỗi | Kiểm tra SQL, quyền, connection; không coi là PASS |
| **Lock Liquibase đang giữ** | Update chờ hoặc không lấy được lock | Xác minh tiến trình còn chạy trước khi xử lý lock |
| **SQL DDL/DML lỗi** | Vi phạm constraint, timeout, quyền, unsupported SQL | Xác định thay đổi thực tế đã commit tới đâu |
| **runInTransaction=false bị ngắt** | Một phần đối tượng có thể đã tạo | So sánh metadata và DATABASECHANGELOG, không retry mù |
| **Update PASS, schema postflight FAIL** | Lịch sử có changeset nhưng đối tượng thiếu/sai | Chặn phát hành, kiểm tra drift hoặc logic migration |
| **Postflight dữ liệu FAIL** | Dữ liệu sai số lượng/constraint dù DDL thành công | Cô lập tác động, phân tích và triển khai bước sửa có kiểm soát |
| **Ứng dụng smoke test FAIL** | Migration đúng nhưng phiên bản app không tương thích | Dừng rollout; quyết định rollback app, forward-fix schema hoặc phục hồi |

Đặc biệt, nếu một changeset sử dụng SQL ngoài transaction như **CREATE INDEX CONCURRENTLY** thất bại, PostgreSQL có thể để lại index invalid. Không dùng **MARK_RAN** chỉ vì tên index xuất hiện; cần kiểm tra **indisvalid** và định nghĩa trước khi quyết định xử lý.

## 17. Rollback, restore và forward-fix là ba quyết định khác nhau

**Rollback Liquibase** chạy các bước đảo ngược theo thiết kế của changeset hoặc change type khi được hỗ trợ. Nó không bảo đảm phục hồi dữ liệu đã bị xóa, trạng thái sequence hay tác động bên ngoài database. Với những thay đổi không thể đảo ngược, cần mô tả rõ rủi ro và phương án khác.

**Restore** là khôi phục database từ backup/snapshot hoặc Point-in-Time Recovery (PITR) nếu hạ tầng hỗ trợ. Nó có thể gây mất những giao dịch hợp lệ phát sinh sau mốc backup; vì vậy cần xác định RPO/RTO, phạm vi database, ứng dụng và cách bảo toàn dữ liệu mới.

**Forward-fix** là tạo migration mới để đưa hệ thống tiến đến trạng thái đúng, ví dụ bổ sung constraint hoặc sửa dữ liệu mà không cố quay lại schema cũ. Đây thường là lựa chọn phù hợp khi ứng dụng đã chạy với schema mới hoặc rollback làm mất dữ liệu.

Trong cả ba trường hợp, cần ghi rõ:

1. Trạng thái thực tế **trước khi quyết định**.
2. Changeset nào đã được ghi nhận và change nào có thể đã thực thi một phần.
3. Dữ liệu nào cần giữ, có writer đang hoạt động không.
4. Hành vi của DBMS về transaction/DDL và dependency.
5. Kế hoạch kiểm tra lại schema, dữ liệu và ứng dụng sau khôi phục.

Không sửa trực tiếp bảng DATABASECHANGELOG để làm “đồng bộ” sau sự cố. Nếu cần reconcile lịch sử, sử dụng quy trình chính thức được review, dựa trên chứng cứ rằng schema thật sự tương đương; không dùng **clear-checksums**, **changelog-sync** hoặc **MARK_RAN** như bước chữa mọi lỗi.

## 18. Mẫu báo cáo postflight cho mỗi release

Một mẫu log có thể được CI/CD hoặc đội triển khai ghi lại:

~~~text
RELEASE_ID: customer-service-2026.11.19.1
CHANGELOG_COMMIT: <reviewed-commit>
TARGET_DATABASE: customer_db
TARGET_SCHEMA: public
LIQUIBASE_UPDATE: SUCCESS

POSTFLIGHT:
  expected_changesets: VERIFIED
  unexpected_history_or_checksum: NONE_DETECTED
  schema_constraints: PASS
  data_assertions: PASS
  index_or_object_health: PASS
  runtime_permissions: PASS
  application_smoke_test: PASS
  monitoring_observation: PASS

DECISION: READY_FOR_NEXT_DEPLOYMENT_STAGE
EVIDENCE: CI job ID, logs, SQL query results, approval ID
~~~

Giá trị **PASS** phải xuất phát từ kiểm tra thật, không được điền trước theo mẫu. Khi một phần không áp dụng, ghi **NOT_APPLICABLE** cùng lý do; khi chưa đo được, ghi **UNKNOWN** và không tự coi là PASS cho điều kiện bắt buộc.

Báo cáo nên được lưu với quyền truy cập thích hợp vì có thể chứa tên database, schema, migration và số liệu nghiệp vụ. Không ghi credentials hoặc dữ liệu nhạy cảm không cần thiết.

## 19. Thực hành: một lần update chuyển customer.status sang NOT NULL

Giả sử database có bảng customer với cột status nullable. Mục tiêu phát hành là áp ràng buộc NOT NULL sau khi dữ liệu đã được backfill.

**Trước update:**

1. Kiểm tra artifact/changelog commit, environment và tài khoản migration.
2. Chạy validate; xem status và danh sách changeset pending. Đối chiếu lịch sử không có checksum bất thường.
3. Truy vấn information_schema để chắc chắn status là cột được yêu cầu.
4. Truy vấn **COUNT(*) WHERE status IS NULL**. Nếu còn NULL, dừng và triển khai bước backfill có kiểm chứng trước.
5. Review update-sql để xác định chỉ có addNotNullConstraint và các changeset dự kiến.
6. Xác nhận ứng dụng hiện tại hoặc cơ chế default sẽ không tiếp tục INSERT status=NULL.

**Trong update:** chạy Liquibase một lần qua tiến trình đã được chỉ định; theo dõi log, lock và thời gian ALTER TABLE. Nếu thất bại, ngừng phát hành phụ thuộc và xác định trạng thái trước khi retry.

**Sau update:**

1. Đọc DATABASECHANGELOG và xác minh changeset **030-customer-status-not-null** được ghi nhận đúng.
2. Kiểm tra **is_nullable = NO** trong information_schema.
3. Kiểm tra **COUNT(*) WHERE status IS NULL = 0**.
4. Chạy smoke test ghi status hợp lệ; xác minh việc ghi NULL bị từ chối theo hành vi kỳ vọng của DBMS.
5. Xác nhận ứng dụng phiên bản hiện tại và sắp triển khai đều tương thích; theo dõi lỗi DML sau release.
6. Lưu SQL/check results, log job và quyết định postflight PASS/FAIL.

Ví dụ này cho thấy **update thành công là điều kiện cần nhưng chưa đủ**. Nếu update báo success nhưng ứng dụng cũ vẫn chèn NULL, hệ thống có thể phát sinh lỗi nghiệp vụ ngay sau khi ràng buộc có hiệu lực. Đó là vấn đề trình tự triển khai, không phải lỗi cú pháp Liquibase.

## 20. Checklist vận hành lặp lại được

Trước khi update:

- [ ] Xác nhận đúng database, schema, role, DBMS/version và release artifact.
- [ ] Changelog và Liquibase/JDBC version đã được cố định, có commit nhận diện.
- [ ] Chạy validate và kiểm tra bất thường lịch sử/checksum.
- [ ] Kiểm tra những changeset sắp được chọn theo contexts/labels/DBMS.
- [ ] Kiểm tra điều kiện dữ liệu và schema, có ngưỡng PASS/FAIL rõ.
- [ ] Review SQL dự kiến và đánh giá lock, thời gian, mất dữ liệu, rollback.
- [ ] Xác nhận backup/phương án phục hồi cho thay đổi quan trọng.
- [ ] Có approval và xác định một tiến trình chịu trách nhiệm chạy update.

Trong và sau update:

- [ ] Theo dõi log, lock, timeout và tài nguyên; không retry khi chưa xác minh trạng thái lỗi.
- [ ] Đối chiếu changeset, checksum và lịch sử DATABASECHANGELOG sau chạy.
- [ ] Xác minh schema/constraint/index/object bằng metadata DBMS.
- [ ] Xác minh hậu điều kiện dữ liệu bằng truy vấn có expectedResult.
- [ ] Kiểm tra quyền runtime, đường đọc/ghi và tương thích phiên bản ứng dụng.
- [ ] Đánh dấu FAIL và chặn phát hành khi hậu điều kiện bắt buộc không đạt.
- [ ] Lưu bằng chứng, người phê duyệt, quyết định cuối và phương án phục hồi khi cần.

Trong **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chuỗi chuẩn hóa cần được thực hiện nhất quán cho **mỗi lần cập nhật**: **nhận diện đúng đích → validate và đối chiếu lịch sử → kiểm tra điều kiện dữ liệu → xem trước SQL → update có giám sát → xác minh schema/dữ liệu/ứng dụng → lưu bằng chứng**. Kết hợp các gate đó với changelog bất biến, precondition, checksum, DATABASECHANGELOGLOCK, rollback hoặc forward-fix và CI/CD sẽ biến migration từ thao tác kỹ thuật đơn lẻ thành quy trình phát hành có thể kiểm chứng, lặp lại và truy vết qua nhiều môi trường.
