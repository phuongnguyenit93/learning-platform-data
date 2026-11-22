# Theo dõi thời gian chạy, trạng thái và changeset thất bại

Một migration Liquibase có thể mất vài giây khi thêm một cột nhỏ, nhưng cũng có thể kéo dài nhiều phút hoặc hàng giờ khi tạo index trên bảng lớn, chuyển đổi dữ liệu hoặc chờ khóa từ giao dịch khác. Nếu chỉ nhìn kết quả cuối cùng là thành công hay thất bại, đội vận hành sẽ khó biết migration đang tiến triển, bị chậm ở changeset nào, đang chờ database hay đã dừng bất thường.

Theo dõi migration cần kết hợp **thời gian chạy**, **trạng thái từng changeset**, **log của Liquibase**, **lịch sử trong DATABASECHANGELOG**, **trạng thái DATABASECHANGELOGLOCK** và hoạt động thực tế của DBMS. Những tín hiệu này trả lời các câu hỏi khác nhau: lệnh bắt đầu lúc nào, thay đổi nào đã hoàn tất, tiến trình có đang giữ khóa, câu SQL nào đang chạy, và database còn ở trạng thái an toàn để tiếp tục hay không.

Bài thuộc chương **Vận hành** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này hướng dẫn xây dựng cách theo dõi có thể điều tra được, phát hiện changeset chậm hoặc thất bại, phân loại nguyên nhân, quyết định retry/rollback/forward-fix và lưu bằng chứng sau mỗi lần triển khai.

## 1. Cần theo dõi những gì?

Một lần chạy Liquibase có nhiều lớp trạng thái. Không nên gom tất cả thành một nhãn SUCCESS/FAILED duy nhất.

| Lớp theo dõi | Câu hỏi cần trả lời | Nguồn tín hiệu |
|---|---|---|
| Run/deployment | Lần chạy nào, trên database nào, dùng artifact nào? | CI/CD job, application startup log, deployment metadata |
| Duration | Bắt đầu, kết thúc, tổng thời gian và thời gian từng changeset? | Log có timestamp, wrapper/CI step, instrumentation |
| Changeset progress | Changeset nào đã được ghi nhận? | DATABASECHANGELOG, log |
| Pending changes | Còn changeset nào chưa chạy? | Liquibase status |
| Lock | Có tiến trình Liquibase giữ khóa không? | DATABASECHANGELOGLOCK, list-locks |
| DBMS activity | SQL có đang chạy, chờ lock hay bị block? | Catalog/session view của DBMS |
| Outcome | Lần chạy hoàn tất, thất bại hay bị hủy? | Exit code, exception, pipeline result |
| Post-check | Schema và dữ liệu thực tế có đúng? | SQL assertions, application smoke test |

Một lần chạy có thể thất bại dù một số changeset trước đó đã hoàn tất. Ngược lại, lệnh có exit code thành công nhưng post-check phát hiện schema/data không đúng kỳ vọng. Vì vậy, phải ghi nhận cả **trạng thái tiến trình** và **trạng thái database sau tiến trình**.

## 2. Phân biệt trạng thái của run và trạng thái của changeset

Run là một lần gọi Liquibase, thường gắn với một deployment hoặc startup. Changeset là đơn vị thay đổi được khai báo trong changelog. Một run có thể chứa nhiều changeset.

Ví dụ:

~~~text
Run: release-2026.11 / target=staging
  001-create-customer       EXECUTED
  002-add-customer-email    EXECUTED
  003-create-email-index    đang thực thi
  004-add-customer-status   chưa chạy
~~~

Nếu changeset 003 thất bại:

- Run có kết quả FAILED.
- Changeset 001 và 002 vẫn có thể đã hoàn tất và được ghi trong DATABASECHANGELOG.
- Changeset 003 có thể không có bản ghi hoàn tất trong lịch sử, tùy thời điểm lỗi và hành vi DBMS.
- Changeset 004 chưa được chạy.
- Schema có thể ở trạng thái trước 003, hoặc có thay đổi một phần nếu thao tác không nguyên tử.

Không nên đánh dấu toàn bộ run là “chưa làm gì” chỉ vì lệnh cuối cùng thất bại. Cũng không nên xem mọi changeset trước đó là đã được áp dụng chỉ dựa vào thứ tự trong changelog; phải kiểm tra lịch sử và trạng thái database.

## 3. Định danh một lần chạy để có thể truy vết

Mỗi lần chạy nên có một bộ định danh nhất quán:

- Release hoặc build ID.
- Target ID và database identity không chứa secret.
- Artifact/changelog version hoặc digest.
- Liquibase version và DBMS/driver version.
- Changelog root.
- Context, label và DBMS filter.
- Thời điểm bắt đầu/kết thúc.
- Người hoặc pipeline khởi chạy.
- Kết quả cuối cùng và changeset lỗi nếu có.

Ví dụ bản ghi vận hành:

~~~text
run_id=release-2026.11.19-region-a-02
target_id=region-a
database=orders_prod
schema=app
artifact=orders-service:2026.11.19.2
liquibase_version=PINNED_VERSION
dbms=PostgreSQL
started_at=2026-11-19T10:02:14Z
finished_at=2026-11-19T10:04:51Z
result=FAILED
last_completed_changeset=20261119-014
failed_changeset=20261119-015
~~~

Các giá trị trên chỉ minh họa. Không đưa password, token, JDBC URL có credentials hoặc dữ liệu nghiệp vụ vào metadata/log. Nếu DBMS hoặc pipeline có ID deployment riêng, lưu ID đó để liên kết log và sự kiện.

Định danh target phải được xác minh trước khi chạy. Một log có tên region-a nhưng kết nối nhầm region-b sẽ làm hỏng toàn bộ quá trình điều tra.

## 4. Đo thời gian chạy ở cấp run

Thời gian tổng là tín hiệu cơ bản:

\[
T_{\text{run}} = T_{\text{finished}} - T_{\text{started}}
\]

Nhưng tổng thời gian không cho biết migration chậm ở bước nào. Nên ghi ít nhất:

- Thời điểm pipeline bắt đầu.
- Thời điểm khởi tạo kết nối DB.
- Thời điểm lấy được Liquibase lock.
- Thời điểm bắt đầu/kết thúc mỗi changeset nếu có instrumentation.
- Thời điểm giải phóng lock.
- Thời điểm post-check hoàn tất.

Có thể tách:

\[
T_{\text{run}} =
T_{\text{startup}} +
T_{\text{lock-wait}} +
T_{\text{migration}} +
T_{\text{post-check}}
\]

Đây là mô hình phân tích thời gian, không phải các bộ đếm Liquibase tự động luôn cung cấp. Pipeline hoặc lớp instrumentation cần ghi những mốc phù hợp.

Ví dụ:

| Giai đoạn | Thời gian |
|---|---:|
| Khởi tạo JVM/DataSource | 4 giây |
| Chờ Liquibase lock | 1 giây |
| Thực thi changeset | 118 giây |
| Kiểm tra sau migration | 3 giây |
| Tổng | 126 giây |

Nếu run tăng từ 30 giây lên 126 giây, chỉ nhìn tổng thời gian chưa đủ. Phải biết phần tăng nằm ở chờ lock, DDL, backfill hay startup.

## 5. Đo thời gian từng changeset

Với migration dài, cần biết changeset nào chiếm thời gian. Một log hữu ích nên gắn:

- ID.
- AUTHOR.
- FILENAME hoặc logical path.
- Thời điểm bắt đầu.
- Thời điểm hoàn tất.
- Duration.
- Change type hoặc mô tả ngắn.
- Kết quả.
- Target ID và run ID.

Ví dụ bảng theo dõi:

| Changeset | Bắt đầu | Duration | Kết quả |
|---|---|---:|---|
| 011-create-customer | 10:02:15 | 0,4 giây | EXECUTED |
| 012-add-email | 10:02:16 | 0,2 giây | EXECUTED |
| 013-backfill-email | 10:02:17 | 92 giây | EXECUTED |
| 014-create-index | 10:03:49 | 18 giây | EXECUTED |

Liquibase log có thể ghi thời điểm thực thi và thông tin changeset, nhưng định dạng và mức chi tiết phụ thuộc version, logging configuration và integration. Nếu cần duration chính xác cho từng changeset, có thể dùng log có timestamp, event listener/instrumentation phù hợp phiên bản, hoặc wrapper tách các nhóm migration. Không giả định mọi phiên bản đều phát ra một metric chuẩn tên changeset_duration.

### 5.1. Baseline thời gian

Sau một số lần triển khai, xây dựng baseline theo loại changeset:

- DDL nhỏ: thời gian thường ngắn.
- Tạo index: phụ thuộc kích thước bảng, tải và thuật toán.
- Backfill: phụ thuộc số dòng, batch size và index.
- Thêm constraint: phụ thuộc dữ liệu hiện tại và DBMS.
- DML hàng loạt: phụ thuộc transaction, WAL/redo, lock và I/O.

Không áp một ngưỡng 10 giây cho mọi changeset. Một index lớn có thể cần nhiều phút trong khi một addColumn có default phức tạp có thể có tác động bất ngờ theo DBMS/version. Ngưỡng cảnh báo phải dựa trên số liệu thực tế và ngân sách downtime/lock.

## 6. Dùng log Liquibase để nhận biết tiến độ

Log thường là nguồn đầu tiên để biết Liquibase đã đọc changelog nào, chọn changeset nào và câu lệnh nào gây lỗi.

Một cấu hình logging của Spring Boot có thể bắt đầu từ:

~~~yaml
logging:
  level:
    liquibase: INFO
~~~

Khi điều tra chi tiết, có thể tăng mức log cho nhóm logger phù hợp với Liquibase version và integration đang dùng. Không bật DEBUG/TRACE toàn hệ thống trong production lâu dài nếu chưa đánh giá dung lượng log và thông tin nhạy cảm.

Một log vận hành cần trả lời:

1. Liquibase version nào đang chạy?
2. Database/target nào được kết nối?
3. Changelog root nào được nạp?
4. Context/label nào đang áp dụng?
5. Changeset nào bắt đầu và hoàn tất?
6. SQL hoặc change type nào gây lỗi?
7. Có lỗi kết nối, quyền, checksum, precondition hay lock?
8. Tiến trình có kết thúc bình thường và giải phóng lock không?

Log có thể chứa SQL hoặc giá trị literal. Trước khi chia sẻ log ra ngoài nhóm, loại bỏ credentials và dữ liệu nhạy cảm. Không ghi toàn bộ connection string có password.

## 7. Kiểm tra changeset còn chờ bằng status

Lệnh status cho biết changeset nào còn chờ được áp dụng theo cấu hình và lịch sử của database hiện tại.

~~~bash
liquibase status --verbose
~~~

Thông tin này hữu ích trước và sau update:

- Trước update: thấy những changeset còn pending.
- Sau update thành công: xác nhận các changeset thông thường đã được ghi nhận không còn nằm trong danh sách chờ.
- Sau thất bại: xem những changeset chưa được ghi nhận còn lại.

Status là phép kiểm tra trạng thái, không thực thi migration và không thay thế post-check. Kết quả phụ thuộc changelog root, context, label, DBMS filter, default schema và database đang kết nối.

Để tránh đọc nhầm, chạy status với đúng cấu hình target và artifact sẽ được dùng cho update. Nếu status được chạy trên staging nhưng update chạy trên production, hai kết quả không thể so sánh trực tiếp.

## 8. Xem lịch sử trong DATABASECHANGELOG

DATABASECHANGELOG là lịch sử changeset đã được Liquibase ghi nhận trên database đích. Các cột thường được dùng để điều tra:

| Cột | Ý nghĩa |
|---|---|
| ID | ID của changeset |
| AUTHOR | Author |
| FILENAME | Đường dẫn changelog |
| MD5SUM | Checksum theo cơ chế Liquibase |
| DATEEXECUTED | Thời điểm ghi nhận |
| ORDEREXECUTED | Thứ tự ghi nhận |
| EXECTYPE | Loại thực thi/ghi nhận |
| DEPLOYMENT_ID | Mã triển khai nếu phiên bản/cấu hình có lưu |

Ví dụ truy vấn PostgreSQL:

~~~sql
SELECT id, author, filename, md5sum,
       exectype, dateexecuted, orderexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Tìm một changeset cụ thể:

~~~sql
SELECT id, author, filename, md5sum,
       exectype, dateexecuted, orderexecuted
FROM databasechangelog
WHERE id = '20261119-015'
  AND author = 'database-team';
~~~

Tên bảng/schema và identifier phải điều chỉnh theo cấu hình thực tế. Có thể dùng bảng lịch sử trong schema metadata riêng.

**Không phải mọi changeset thất bại đều có một dòng FAILED trong DATABASECHANGELOG.** Nếu lỗi xảy ra trước khi Liquibase ghi nhận changeset hoàn tất, changeset có thể không xuất hiện. Vì vậy, kết luận thất bại phải dựa trên log, exit code, trạng thái database và lịch sử, không chỉ truy vấn EXECTYPE.

## 9. Hiểu EXECTYPE khi đọc lịch sử

Một số giá trị EXECTYPE thường gặp có ý nghĩa:

- EXECUTED: changeset đã được thực thi.
- RERAN: changeset được chạy lại trong trường hợp cấu hình như runOnChange/runAlways.
- MARK_RAN: changeset được ghi nhận là đã chạy nhưng change không được thực thi theo cơ chế đánh dấu.
- SKIPPED: có thể xuất hiện trong một số luồng xử lý/phiên bản.
- FAILED: không nên giả định là giá trị luôn được ghi lại cho mọi lần thất bại.

Các giá trị thực tế và cách ghi nhận phụ thuộc phiên bản, loại change và đường đi thực thi. Khi điều tra, kiểm tra schema bảng, log và tài liệu đúng runtime.

Đặc biệt, MARK_RAN không đồng nghĩa SQL đã chạy. Một bản ghi lịch sử không chứng minh schema/data có trạng thái mong đợi. Cần truy vấn đối tượng và dữ liệu thực tế.

## 10. Theo dõi DATABASECHANGELOGLOCK

DATABASECHANGELOGLOCK cho biết có tiến trình Liquibase đang giữ quyền chạy migration trong phạm vi bảng khóa đó hay không.

Ví dụ truy vấn PostgreSQL:

~~~sql
SELECT id, locked, lockgranted, lockedby
FROM databasechangeloglock
ORDER BY id;
~~~

Các trường hữu ích:

- LOCKED: trạng thái khóa.
- LOCKGRANTED: thời điểm cấp khóa.
- LOCKEDBY: thông tin tiến trình/host theo cách Liquibase ghi nhận.

Nếu một changeset chạy lâu, lock có thể vẫn được giữ hợp lệ. Không kết luận stale lock chỉ vì thời gian giữ khóa vượt dự kiến.

Có thể dùng lệnh CLI sau trong những phiên bản hỗ trợ:

~~~bash
liquibase list-locks
~~~

Nếu cần giải phóng khóa, chỉ thực hiện sau khi xác minh tiến trình holder đã dừng, không còn session đang chạy migration và trạng thái database đã được điều tra. Không sửa trực tiếp LOCKED bằng SQL như cách xử lý thông thường.

## 11. Phân biệt thời gian chạy với thời gian chờ lock

Một migration “chậm” có thể chưa thực thi SQL nào. Nó có thể đang chờ tiến trình Liquibase khác giữ DATABASECHANGELOGLOCK.

Dấu hiệu:

- Log cho biết không lấy được change log lock hoặc đang đợi lock.
- DATABASECHANGELOGLOCK cho thấy LOCKED=true.
- LOCKGRANTED cũ hơn thời điểm run hiện tại.
- Một tiến trình khác có log đang thực thi migration.

Trong tình huống này, thời gian run tăng nhưng thời gian thực thi changeset chưa bắt đầu. Nếu không tách lock-wait khỏi migration duration, dashboard có thể kết luận nhầm changeset bị chậm.

Quy trình điều tra:

1. Xác minh target/database identity.
2. Đọc trạng thái DATABASECHANGELOGLOCK của đúng target.
3. Xác định holder từ LOCKEDBY và log deployment.
4. Kiểm tra process/pod/job còn sống không.
5. Kiểm tra DBMS session có query đang chạy hoặc chờ lock.
6. Chờ nếu migration vẫn tiến triển; điều tra nếu bị block.
7. Chỉ xem xét release-locks khi đã chứng minh holder dừng và trạng thái DB an toàn.

## 12. Theo dõi SQL đang chạy và DBMS wait

Liquibase log cho biết changeset và lỗi ở mức công cụ; DBMS catalog giúp hiểu câu SQL đang chạy hoặc chờ.

Ví dụ PostgreSQL:

~~~sql
SELECT pid, usename, application_name, state,
       wait_event_type, wait_event,
       query_start, state_change,
       LEFT(query, 200) AS query_preview
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

Có thể kiểm tra các session đang bị block bằng các view/function lock của PostgreSQL, ví dụ pg_locks và pg_blocking_pids. Khi đó cần phân biệt:

- Liquibase đang chờ DATABASECHANGELOGLOCK.
- SQL của Liquibase đang chờ row/table lock trong DBMS.
- DBMS đang thực hiện DDL hoặc build index.
- Kết nối bị idle hoặc đã mất.
- Một giao dịch nghiệp vụ dài đang chặn DDL.

Query preview có thể chứa literal nhạy cảm. Hạn chế quyền xem và không đưa kết quả nguyên văn vào ticket công khai.

Các DBMS khác có catalog và câu truy vấn tương ứng, chẳng hạn performance views hoặc dynamic management views. Dùng công cụ quan sát đúng DBMS, không sao chép truy vấn PostgreSQL cho Oracle/MySQL/SQL Server.

## 13. Phân loại changeset thất bại

Một changeset có thể thất bại vì nhiều nguyên nhân khác nhau. Phân loại đúng giúp tránh retry sai cách.

| Nhóm lỗi | Ví dụ | Dấu hiệu cần tìm |
|---|---|---|
| Kết nối | Timeout, TLS, authentication | Connection exception, không tới bước thực thi |
| Quyền | Không có quyền CREATE/ALTER | Permission denied |
| Cú pháp | SQL không hợp lệ trên DBMS | Syntax error, SQL state |
| Dữ liệu | Unique/FK/NOT NULL violation | Constraint violation, bản ghi xung đột |
| Precondition | Điều kiện không đạt | Precondition failed, onFail policy |
| Checksum | Nội dung changeset đã thay đổi | Validation/checksum error |
| Lock | Không lấy được Liquibase lock | Cannot acquire change log lock |
| DBMS lock | DDL bị transaction khác chặn | Wait event, lock timeout/deadlock |
| Resource | SQL/CSV/changelog không tìm thấy | Resource/path exception |
| Transaction | DDL không hỗ trợ transaction hoặc commit một phần | DBMS-specific error, trạng thái object sau lỗi |

Không gộp mọi trường hợp thành “Liquibase failed”. Mỗi loại cần người xử lý và cách khôi phục khác nhau.

## 14. Khi changeset thất bại, kiểm tra theo thứ tự nào?

Một quy trình điều tra có thể thực hiện như sau:

**Bước 1 — Xác nhận đúng run và target.** Đối chiếu run ID, database name, schema, artifact và Liquibase version.

**Bước 2 — Đọc lỗi gốc.** Tìm exception sâu nhất, SQL state, tên bảng/cột/index và changeset ID. Thông báo bọc bên ngoài thường chỉ nói migration failed.

**Bước 3 — Kiểm tra lock.** Xác định tiến trình có giữ lock hợp lệ hay lock đang tồn đọng.

**Bước 4 — Kiểm tra lịch sử.** Đối chiếu changeset gần nhất đã ghi nhận trong DATABASECHANGELOG.

**Bước 5 — Kiểm tra schema/data thực tế.** Xác định SQL đã tác động một phần hay chưa.

**Bước 6 — Kiểm tra transaction.** Xem DBMS có rollback DDL/DML trong transaction hay không, changeset có runInTransaction=false không.

**Bước 7 — Chọn phương án.** Sửa cấu hình/quyền/dữ liệu, retry, forward-fix, rollback hoặc restore tùy trạng thái thực tế.

Không chạy update lại ngay khi thấy một changeset không có trong DATABASECHANGELOG. Nó có thể đã tạo object hoặc ghi dữ liệu nhưng chưa kịp ghi lịch sử.

## 15. Vì sao changeset có thể để lại trạng thái một phần?

Liquibase thường chạy changeset trong transaction khi DBMS và loại thao tác hỗ trợ. Nhưng không thể giả định mọi DDL đều transactional.

Các trường hợp đáng chú ý:

- DBMS tự commit một số DDL.
- Changeset đặt runInTransaction=false.
- Một SQL script chứa nhiều statement, lỗi ở statement giữa.
- Kết nối mất sau khi database commit nhưng trước khi client nhận kết quả.
- Một lệnh DDL có trạng thái trung gian riêng, ví dụ index build thất bại.
- Changeset có nhiều thao tác phụ thuộc và DBMS không rollback tất cả như một đơn vị.

Sau thất bại, kiểm tra:

- Bảng/cột/index/constraint có tồn tại không.
- Index có trạng thái hợp lệ không.
- Dữ liệu đã được insert/update một phần chưa.
- Transaction còn mở hay đã kết thúc.
- DATABASECHANGELOG có ghi changeset không.
- Lock còn giữ hay đã giải phóng.

Đừng dựa vào một thông báo exception để suy ra database chắc chắn không thay đổi.

## 16. Retry: khi nào an toàn?

Retry chỉ phù hợp khi đã hiểu trạng thái hiện tại và thay đổi có thể tiếp tục an toàn.

Có thể retry sau khi sửa nguyên nhân đơn giản như:

- Credential hết hạn đã được thay đúng.
- Quyền DDL được cấp theo phê duyệt.
- Database tạm thời không truy cập được.
- Lock hợp lệ đã được tiến trình cũ giải phóng.
- Changelog resource bị thiếu trong artifact đã được sửa bằng release phù hợp.

Nhưng trước khi retry, cần kiểm tra:

1. Process cũ đã dừng hoàn toàn.
2. DATABASECHANGELOGLOCK không còn holder hợp lệ.
3. Changeset lỗi có được ghi nhận hay không.
4. Schema/data có thay đổi một phần không.
5. SQL có idempotent hoặc có precondition bảo vệ không.
6. Retry có tạo object trùng, dữ liệu trùng hoặc xung đột constraint không.

Không cấu hình retry vô hạn cho migration. Một vòng lặp retry có thể liên tục tạo connection, chờ lock hoặc lặp lại một DDL không an toàn.

## 17. Rollback hay forward-fix?

Sau một changeset thất bại, lựa chọn phục hồi phụ thuộc loại thay đổi và trạng thái database.

| Tình huống | Hướng có thể phù hợp |
|---|---|
| Lỗi trước khi có thay đổi và transaction đã rollback | Sửa nguyên nhân rồi retry |
| Đối tượng đã được tạo đầy đủ nhưng history chưa ghi | Reconcile trạng thái theo quy trình có kiểm chứng; không tự mark-ran |
| Dữ liệu đã chuyển đổi một phần | Phân tích dữ liệu, backup/restore hoặc forward-fix |
| Changeset đã hoàn tất nhưng ứng dụng gặp lỗi | Đánh giá rollback hoặc hotfix ứng dụng |
| Rollback có thể làm mất dữ liệu mới | Ưu tiên forward-fix hoặc restore có kế hoạch |
| DDL không thể đảo ngược chính xác | Dùng migration sửa chữa và backup/restore phù hợp |

Rollback không phải lúc nào cũng là cách an toàn nhất. Một câu DROP COLUMN có thể làm mất dữ liệu phát sinh sau deployment. Một changeset tạo constraint có thể được xử lý bằng cách sửa dữ liệu vi phạm rồi tiếp tục, thay vì xóa toàn bộ thay đổi trước đó.

Trước rollback, preview SQL, kiểm tra dependency, dữ liệu mới và phiên bản ứng dụng đang chạy. Với thay đổi lớn, thử trên bản sao database có trạng thái tương đương.

## 18. Cảnh báo thời gian chạy và lock

Cảnh báo nên dựa trên baseline, không chỉ một ngưỡng cố định.

Các loại cảnh báo hữu ích:

- Run vượt thời gian dự kiến.
- Lock-wait vượt ngưỡng.
- Một changeset chạy lâu hơn percentile/baseline của chính loại đó.
- Không có log tiến triển trong khoảng thời gian bất thường.
- DATABASECHANGELOGLOCK vẫn bị giữ sau khi job đã kết thúc.
- Changeset lỗi hoặc run exit code khác 0.
- Update thành công nhưng post-check thất bại.
- Một target chậm hoặc lỗi trong khi các target khác đã hoàn tất.

Ví dụ chính sách minh họa:

| Mức | Điều kiện | Hành động |
|---|---|---|
| INFO | Migration trong thời gian baseline | Ghi nhận run và changeset |
| WARNING | Duration vượt ngưỡng cảnh báo | Kiểm tra lock, query và tải |
| HIGH | Không có tiến triển hoặc DBMS lock kéo dài | Gọi người vận hành database điều tra |
| CRITICAL | Changeset thất bại, dữ liệu/schema không xác định | Dừng rollout phụ thuộc, bảo toàn log và trạng thái |
| RECOVERY | Retry/forward-fix đã xác minh | Chạy lại có kiểm soát, post-check |

Không tự động release lock chỉ vì cảnh báo CRITICAL. Cảnh báo phải kích hoạt điều tra, không thay thế quyết định vận hành.

## 19. Theo dõi migration trong Spring Boot

Khi Liquibase chạy lúc Spring Boot startup, thời gian migration có thể nằm trong thời gian khởi tạo ApplicationContext. Nếu startup probe hoặc orchestration timeout quá ngắn, pod có thể bị restart trong khi migration vẫn đang chạy.

Cần quan sát:

- Thời gian từ process start tới datasource ready.
- Thời gian Liquibase khởi tạo.
- Changeset cuối cùng trong log.
- Trạng thái readiness/liveness/startup probe.
- Số lần restart và nguyên nhân.
- DATABASECHANGELOGLOCK.
- Trạng thái DBMS session.

Ví dụ cấu hình log:

~~~yaml
logging:
  level:
    liquibase: INFO
    org.springframework.boot.autoconfigure.liquibase: INFO
~~~

Tên logger cụ thể có thể thay đổi theo phiên bản và tích hợp. Kiểm tra log thực tế để xác định category nào ghi thông tin Liquibase trong dự án.

Nếu nhiều replica cùng bật Liquibase, chỉ một tiến trình có thể giữ lock trong cùng phạm vi; các replica khác có thể chờ trong startup. Với migration dài hoặc DDL nặng, cân nhắc chạy migration bằng job riêng trước khi rollout ứng dụng và tắt auto-run ở runtime theo kiến trúc dự án.

Không coi pod chưa ready là migration thất bại ngay. Kiểm tra tiến trình và DBMS trước khi restart hoặc hủy job.

## 20. Theo dõi nhiều database và nhiều môi trường

Một artifact có thể được triển khai tới staging, region A, region B hoặc nhiều tenant. Mỗi target có lịch sử, lock, thời gian và kết quả riêng.

Báo cáo theo target nên có:

| Trường | Ví dụ |
|---|---|
| target_id | region-a |
| database | orders_prod |
| release | release-2026.11.19 |
| started_at | thời điểm bắt đầu |
| duration | tổng thời gian |
| last_completed_changeset | changeset cuối đã ghi nhận |
| failed_changeset | changeset lỗi, nếu có |
| lock_state | unlocked/locked |
| outcome | completed/failed/pending |
| post_check | pass/fail/pending |

Nếu region A thất bại nhưng region B thành công, không ghi đè trạng thái region B bằng kết quả tổng của pipeline. Retry chỉ target lỗi sau khi kiểm tra history/schema. Không dùng một bảng tổng hợp ngoài database thay thế DATABASECHANGELOG của từng đích.

## 21. Tạo báo cáo sau mỗi lần triển khai

Một báo cáo vận hành ngắn nên cho phép người khác tiếp tục điều tra mà không cần đọc toàn bộ log.

Ví dụ:

~~~text
Release: orders-2026.11.19.2
Target: region-a / orders_prod
Artifact: changelog-digest=...
Liquibase: pinned-version
DBMS: PostgreSQL / major-version

Run:
  started: 10:02:14Z
  finished: 10:04:51Z
  duration: 157s
  outcome: FAILED

Progress:
  completed: 014 changesets
  failed: 015-add-order-status-index
  pending: 016-backfill-order-status

Lock:
  state: verify-required
  holder: ...

Failure:
  category: DBMS_LOCK_TIMEOUT
  sql_state: ...
  summary: DDL bị chặn bởi transaction dài

Next action:
  xác minh session chặn, dữ liệu và trạng thái index;
  chỉ retry sau khi database đã được kiểm tra.
~~~

Không điền thông tin chưa xác minh. Nếu chưa biết changeset có thay đổi một phần hay không, ghi UNKNOWN/NEEDS_INVESTIGATION thay vì suy đoán ROLLED_BACK.

## 22. Tổ chức log và metric an toàn

Log/metric nên có nhãn có giới hạn cardinality hợp lý:

- target_id.
- environment.
- release_id hoặc artifact version.
- outcome.
- DBMS family/version.
- changeset_id khi hệ thống metrics hỗ trợ và số lượng changeset được kiểm soát.

Không đưa các giá trị có thể tăng vô hạn hoặc chứa dữ liệu nhạy cảm làm label. Ví dụ JDBC URL đầy đủ, SQL literal, customer ID hoặc mỗi lần chạy UUID không nên trở thành metric label trong hệ thống metrics có cardinality cao.

Có thể lưu run ID đầy đủ trong log/tracing, còn metric tổng hợp theo target, environment, outcome và nhóm migration. Nếu muốn metric duration theo changeset, thiết kế instrumentation có kiểm soát và thống nhất định danh.

Các metric vận hành hữu ích:

- liquibase_run_duration_seconds.
- liquibase_run_total theo outcome.
- liquibase_lock_wait_seconds.
- liquibase_changeset_duration_seconds nếu có instrumentation.
- liquibase_pending_changesets.
- liquibase_migration_failures_total.
- liquibase_post_check_failures_total.

Đây là **tên metric gợi ý do dự án tự định nghĩa**, không phải cam kết rằng Liquibase cung cấp sẵn các metric đó. Cần xây exporter/listener/wrapper hoặc thu thập từ CI log theo cách đã kiểm thử.

## 23. Runbook khi changeset thất bại

Khi pipeline hoặc Spring Boot báo migration failed:

1. Dừng rollout các thành phần phụ thuộc nếu schema chưa rõ trạng thái.
2. Ghi nhận run ID, target ID, release, artifact và thời điểm.
3. Đọc exception gốc và xác định changeset lỗi.
4. Kiểm tra DATABASECHANGELOG và DATABASECHANGELOGLOCK của đúng target.
5. Xác minh process/connection cũ còn chạy không.
6. Kiểm tra DBMS session, lock và câu SQL liên quan.
7. Kiểm tra schema/data để phát hiện thay đổi một phần.
8. Xác định transaction và khả năng rollback thực tế.
9. Chọn retry, rollback, forward-fix hoặc restore.
10. Thử phương án trên database clone có trạng thái tương đương khi cần.
11. Chạy lại có kiểm soát và xác minh post-check.
12. Lưu báo cáo kết quả cùng nguyên nhân gốc.

Không xóa DATABASECHANGELOG, không sửa EXECTYPE và không release lock bằng SQL để che lỗi. Những thao tác đó có thể làm mất bằng chứng hoặc khiến Liquibase chạy lại thay đổi nguy hiểm.

## 24. Bài thực hành: theo dõi một changeset chậm và một changeset thất bại

Dùng PostgreSQL Testcontainers hoặc database lab riêng. Không thử trên production.

### Phần A — Theo dõi thời gian

1. Tạo changelog có một changeset tạo bảng và một changeset tạo index.
2. Chạy Liquibase update với log có timestamp.
3. Ghi thời gian run và thời gian từng changeset nếu instrumentation hỗ trợ.
4. Truy vấn DATABASECHANGELOG để xác nhận thứ tự và thời điểm ghi nhận.
5. Truy vấn DATABASECHANGELOGLOCK sau khi run kết thúc.
6. So sánh thời gian giữa lần đầu và lần chạy không còn changeset pending.

### Phần B — Mô phỏng changeset thất bại do dữ liệu

1. Tạo bảng có dữ liệu trùng.
2. Viết changeset thêm unique constraint.
3. Chạy update và quan sát lỗi.
4. Kiểm tra changeset có được ghi nhận trong DATABASECHANGELOG hay không.
5. Kiểm tra constraint có tồn tại một phần không.
6. Truy vấn các nhóm dữ liệu vi phạm.
7. Sửa fixture hoặc thiết kế bước làm sạch dữ liệu.
8. Retry sau khi xác minh trạng thái database.

### Phần C — Mô phỏng lock wait

1. Mở một transaction lab giữ lock trên bảng cần thay đổi.
2. Khởi chạy changeset DDL từ Liquibase.
3. Quan sát log, DATABASECHANGELOGLOCK và DBMS session.
4. Phân biệt thời gian chờ Liquibase lock với thời gian chờ DBMS lock.
5. Kết thúc transaction lab theo kế hoạch.
6. Xác nhận migration tiếp tục hoặc thất bại theo timeout đã cấu hình.
7. Kiểm tra lock và lịch sử sau khi kết thúc.

### Phần D — Tạo báo cáo vận hành

Tổng hợp target, release, duration, changeset cuối, changeset lỗi, lock state, DBMS error và kết quả post-check. Chỉ ghi những gì đã quan sát được.

Điều kiện hoàn thành: người học có thể phân biệt run failure với changeset history, xác định migration đang chờ ở lớp nào, kiểm tra trạng thái một phần và chọn cách phục hồi dựa trên bằng chứng.

## 25. Checklist theo dõi migration trong production

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Run có ID và target identity rõ ràng? | Log/pipeline metadata |
| Artifact và Liquibase/DBMS version được ghi lại? | Release manifest |
| Có thời gian bắt đầu/kết thúc và duration? | Timestamp và pipeline result |
| Có phân biệt lock-wait với SQL execution? | Log và DATABASECHANGELOGLOCK/DBMS session |
| Có thể xác định changeset cuối đã hoàn tất? | DATABASECHANGELOG và log |
| Changeset lỗi có ID/author/path rõ? | Exception và changelog |
| Có lưu SQL state/root cause? | Log đã lọc thông tin nhạy cảm |
| Có kiểm tra trạng thái schema/data sau lỗi? | SQL assertions/catalog |
| Có kiểm tra transaction và partial commit? | DBMS behavior, runInTransaction, session |
| Có chính sách retry hữu hạn? | Pipeline policy và runbook |
| Có phương án rollback/forward-fix/restore? | Kế hoạch được review |
| Có post-check sau update? | Schema/data/application assertions |
| Có báo cáo riêng cho từng target? | Result artifact không bị ghi đè |
| Có cảnh báo duration/lock/failure? | Threshold dựa trên baseline |
| Log/metric có bảo vệ secrets và PII? | Quy tắc redaction và access control |

**Nguyên tắc cuối cùng:** theo dõi Liquibase hiệu quả cần ghép thời gian của run, tiến độ changeset, lịch sử DATABASECHANGELOG, trạng thái DATABASECHANGELOGLOCK, log và hoạt động của DBMS. Khi một changeset thất bại, hãy xác định đúng target và nguyên nhân gốc, kiểm tra thay đổi đã commit một phần hay chưa rồi mới quyết định retry, rollback hoặc forward-fix. Một báo cáo có run ID, duration, changeset cuối, lỗi gốc và post-check giúp đội vận hành khôi phục có kiểm soát và cải thiện độ tin cậy của các lần triển khai tiếp theo.

