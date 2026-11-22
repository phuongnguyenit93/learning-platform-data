
# Dùng list-locks và đánh giá tình trạng khóa

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi một lệnh update không thể tiếp tục, một thông báo thường gặp là database đang được Liquibase khóa. Người vận hành cần xác định tiến trình nào đang giữ khóa, khóa còn hợp lệ hay đã bị bỏ lại sau sự cố, và có session database nào đang thực thi hoặc chờ hay không.

Bài thuộc chương **Vận hành** này hướng dẫn dùng lệnh **list-locks** để quan sát trạng thái khóa điều phối của Liquibase, sau đó đánh giá bằng chứng từ pipeline, tiến trình ứng dụng và lock manager của DBMS. Trọng tâm là phân biệt khóa Liquibase với khóa hàng/bảng/metadata do database tạo, nhận diện trạng thái active, stale hoặc chưa đủ thông tin, và xử lý theo runbook có kiểm soát. Bài cũng trình bày cách theo dõi lock theo từng target, giới hạn quyền, ghi audit và tránh mở khóa khi migration vẫn còn hoạt động.

Phạm vi bài học được xác định bởi **SERVICE_NAME=DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Theo **SERVICE_NAME_DESCRIBE**, module hướng dẫn quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Khóa Liquibase giải quyết vấn đề gì?

Khi hai tiến trình Liquibase cùng cập nhật một database, chúng có thể cùng đọc danh sách changeset pending rồi cùng cố gắng thực thi một thay đổi. Điều này có thể gây tạo bảng trùng, duplicate key, thay đổi schema không theo thứ tự hoặc lịch sử không nhất quán.

Liquibase dùng cơ chế **database change log lock** để điều phối những tiến trình cùng sử dụng một bảng khóa. Trong cấu hình thông thường, bảng có tên **DATABASECHANGELOGLOCK** và được lưu trong database/schema mà Liquibase quản lý.

Mục đích của khóa là bảo đảm một tiến trình Liquibase có quyền thực hiện công việc migration tại một thời điểm trong phạm vi bảng khóa đó. Khi công việc kết thúc bình thường, Liquibase giải phóng khóa để tiến trình tiếp theo có thể tiếp tục.

Khóa này là **khóa điều phối migration**. Nó không phải khóa nghiệp vụ cho ứng dụng và không thay thế cơ chế transaction, row lock, table lock hoặc metadata lock của DBMS.

## 2. Phân biệt DATABASECHANGELOG và DATABASECHANGELOGLOCK

Hai bảng thường được nhắc cùng nhau nhưng phục vụ hai mục đích khác nhau:

| Bảng | Vai trò | Câu hỏi trả lời |
|---|---|---|
| **DATABASECHANGELOG** | Ghi lịch sử changeset đã được xử lý | Changeset nào đã được ghi nhận? |
| **DATABASECHANGELOGLOCK** | Điều phối quyền chạy migration | Có tiến trình Liquibase nào đang giữ quyền migration? |

DATABASECHANGELOG chứa thông tin như ID, AUTHOR, FILENAME, MD5SUM, DATEEXECUTED, ORDEREXECUTED và EXECTYPE. DATABASECHANGELOGLOCK lưu trạng thái khóa, thời điểm cấp và thông tin tiến trình được ghi nhận.

Nếu thấy LOCKED=true, điều đó không cho biết changeset cuối cùng đã thành công hay chưa. Muốn biết lịch sử, phải xem DATABASECHANGELOG và đối chiếu với schema/data thực tế. Muốn biết ai đang giữ khóa, phải kết hợp lock table với thông tin job và session database.

Không xóa hoặc sửa DATABASECHANGELOG để giải quyết một lock wait. Đó là hai vấn đề riêng.

## 3. Cấu trúc điển hình của DATABASECHANGELOGLOCK

Bảng khóa mặc định thường có một hàng được sử dụng làm khóa điều phối, với các cột chính:

| Cột | Ý nghĩa |
|---|---|
| ID | Định danh hàng khóa; cấu hình mặc định thường dùng ID=1 |
| LOCKED | Trạng thái đang giữ khóa |
| LOCKGRANTED | Thời điểm Liquibase ghi nhận cấp khóa |
| LOCKEDBY | Thông tin mô tả host hoặc tiến trình giữ khóa |

Ví dụ kết quả minh họa:

~~~text
ID | LOCKED | LOCKGRANTED          | LOCKEDBY
1  | true   | 2026-11-19 09:30:00  | runner-02 (10.0.0.12)
~~~

Giá trị cụ thể, kiểu dữ liệu và cách biểu diễn boolean có thể khác theo DBMS và phiên bản Liquibase. Bảng có thể được đổi tên hoặc đặt trong schema riêng qua cấu hình.

Một hàng LOCKED=true là bằng chứng rằng bảng đang ghi nhận khóa được giữ. Nó **không tự chứng minh** tiến trình còn sống, đã chết, đang chạy SQL hay đang chờ DBMS lock.

## 4. list-locks dùng để làm gì?

Lệnh CLI **list-locks** cho phép xem thông tin khóa Liquibase trên database mà cấu hình kết nối hiện tại trỏ tới.

Lệnh thường dùng:

~~~text
liquibase list-locks
~~~

Kết quả giúp người vận hành biết Liquibase có ghi nhận lock đang được giữ hay không và các thông tin liên quan mà phiên bản công cụ cung cấp. Định dạng output có thể khác giữa các phiên bản hoặc wrapper.

Lệnh này hữu ích khi:

- Một update khác báo không lấy được lock.
- Pipeline đã chờ lâu hơn dự kiến.
- Job migration bị hủy hoặc runner mất kết nối.
- Nhiều pod Spring Boot cùng khởi động.
- DBA cần kiểm tra trạng thái trước khi quyết định bước phục hồi.
- Một lần deploy trước kết thúc bất thường và lần deploy mới không thể tiếp tục.

**list-locks là bước quan sát, không phải lệnh giải phóng khóa.** Nó không rollback SQL, không kết thúc process, không kill session DBMS và không sửa dữ liệu ứng dụng.

## 5. Chạy list-locks trên đúng database

Một lệnh list-locks chỉ có ý nghĩa khi kết nối tới đúng database/schema và đúng bảng lock mà migration sử dụng.

Trước khi chạy, xác minh:

1. Target ID và environment.
2. Host/endpoint hoặc database alias.
3. Database/catalog hiện tại.
4. Schema chứa bảng history và lock.
5. Tên bảng DATABASECHANGELOGLOCK nếu đã tùy chỉnh.
6. Liquibase version và connection profile.
7. Context/label không làm thay đổi target ngoài dự kiến.

Ví dụ CLI minh họa:

~~~text
liquibase \
  --url=jdbc:postgresql://db-host:5432/customer_db \
  --username=customer_migrator \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  list-locks
~~~

Cú pháp xuống dòng và cách truyền tham số phụ thuộc shell/CLI. Không ghi password trực tiếp trong command line, nơi có thể xuất hiện trong process list hoặc log. Dùng secret manager hoặc cơ chế cấp credential an toàn của môi trường.

Nếu chạy list-locks trên database khác, kết quả có thể báo không có lock dù database thật vẫn đang bị khóa. Luôn ghi target ID trong báo cáo vận hành.

## 6. Bảng lock được tùy chỉnh ở đâu?

Một số dự án thay đổi tên hoặc schema của bảng lịch sử và bảng lock. Những thuộc tính thường gặp trong cấu hình Liquibase gồm:

- \`databaseChangeLogTableName\`
- \`databaseChangeLogLockTableName\`
- \`liquibaseSchemaName\`
- \`defaultSchemaName\`
- Catalog/schema tương ứng theo DBMS.

Tên thuộc tính, vị trí cấu hình và cách truyền có thể khác giữa CLI, Maven/Gradle plugin và Spring Boot. Cần đối chiếu đúng phiên bản Liquibase và DBMS đang chạy.

Nếu dự án dùng bảng lock tùy chỉnh, list-locks phải được thực hiện với cùng cấu hình. Nếu một job dùng bảng lock mặc định còn job khác dùng bảng lock riêng nhưng cùng sửa object, hai job có thể không được điều phối với nhau.

Không đổi tên bảng lock chỉ để làm sạch trạng thái. Nếu Liquibase bắt đầu nhìn vào một bảng mới, lịch sử/khóa cũ có thể vẫn tồn tại ở vị trí trước đó.

## 7. Quy trình đọc kết quả list-locks

Sau khi chạy lệnh, ghi lại:

- Target ID, environment và database/schema.
- LOCKED hoặc trạng thái mà CLI hiển thị.
- LOCKGRANTED nếu có.
- LOCKEDBY nếu có.
- Liquibase version và thời điểm kiểm tra.
- Job/runner có khả năng sở hữu khóa.
- Lệnh gần nhất đã chạy và kết quả.

Đừng kết luận chỉ dựa vào một trường. Ví dụ LOCKED=true và LOCKGRANTED cách đây vài giờ có thể là stale lock, nhưng cũng có thể migration đang chạy một index build lâu hoặc bị chờ một transaction ứng dụng.

Kết quả list-locks cần được đối chiếu với:

1. Trạng thái pipeline/job.
2. Tiến trình hoặc container/Pod.
3. Session đang kết nối database.
4. SQL đang thực thi hoặc wait event.
5. Lịch sử changeset và trạng thái schema/data.

Nếu không tìm được bằng chứng đủ chắc, phân loại là **UNKNOWN/NEEDS_INVESTIGATION**, không tự động coi là stale.

## 8. Ba trạng thái vận hành: active, stale và unknown

Có thể phân loại bằng chứng theo ba nhóm:

| Trạng thái | Dấu hiệu | Quyết định |
|---|---|---|
| **ACTIVE** | Job/runner còn chạy hoặc DB session migration còn hoạt động | Không giải phóng khóa; theo dõi và chẩn đoán tiến độ |
| **STALE** | Job đã kết thúc bất thường, không còn owner/session thực thi, trạng thái schema đã được kiểm tra | Có thể xem xét release lock theo quy trình được duyệt |
| **UNKNOWN** | Thiếu log, không xác định được owner, session khó quan sát hoặc trạng thái DB chưa rõ | Dừng retry và tiếp tục điều tra |

Một lock không được phân loại chỉ bằng tuổi của LOCKGRANTED. Thời gian là manh mối để ưu tiên điều tra, không phải tiêu chí đủ để xóa khóa.

Khi chưa chắc chắn, giữ trạng thái UNKNOWN và yêu cầu DBA/on-call cùng owner pipeline xác minh. Một lần chờ lâu vẫn có thể là migration hợp lệ.

## 9. Đối chiếu LOCKEDBY với pipeline và runner

LOCKEDBY có thể chứa host, địa chỉ hoặc thông tin tiến trình do Liquibase ghi nhận. Nó hữu ích để tìm runner nhưng không nhất thiết là một định danh job duy nhất.

Đối chiếu:

- Pipeline run ID và job name.
- Commit SHA/artifact revision.
- Host hoặc runner name.
- Kubernetes namespace, Job và Pod.
- Container/process start time.
- Thời gian job bắt đầu và lần log cuối.
- Trạng thái cancel/timeout/retry.
- Người đã trigger hoặc phê duyệt release.

Một runner có thể được tái sử dụng cho job khác; một Pod có thể đã bị thay thế; tên host có thể không đủ để tìm chính xác process. Không kết luận owner chỉ từ chuỗi LOCKEDBY nếu không có bằng chứng liên kết.

Nếu pipeline đã báo canceled nhưng session database còn tồn tại, SQL có thể vẫn chạy hoặc connection chưa được đóng hoàn toàn. Hãy kiểm tra DBMS trước khi release.

## 10. Đối chiếu với DATABASECHANGELOG

DATABASECHANGELOG giúp xác định những changeset đã được ghi nhận trước hoặc trong lần chạy.

Truy vấn tham khảo:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    MD5SUM,
    EXECTYPE,
    DATEEXECUTED,
    ORDEREXECUTED
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Có thể lọc theo changeset đang điều tra, nhưng cần giữ đủ định danh ID, AUTHOR và FILENAME. Không chỉ lọc theo ID nếu cùng ID được dùng ở nhiều file.

Khi job thất bại, đối chiếu:

- Changeset cuối cùng đã ghi nhận.
- EXECTYPE như EXECUTED, MARK_RAN hoặc RERAN.
- Changeset đang được log cho biết là đang chạy.
- SQL/object thực tế đã xuất hiện hay chưa.
- Dữ liệu đã thay đổi một phần hay chưa.

Nếu SQL đã tác động nhưng row lịch sử chưa được ghi nhận, có thể xảy ra khi DBMS DDL autocommit, transaction không bao trọn thao tác hoặc kết nối bị mất ở thời điểm không rõ. Không retry trước khi xác minh trạng thái thật.

## 11. Liquibase lock khác DBMS lock như thế nào?

| Đặc điểm | Liquibase coordination lock | DBMS object/transaction lock |
|---|---|---|
| Mục tiêu | Điều phối tiến trình Liquibase | Bảo vệ tính nhất quán khi truy cập database |
| Nơi quan sát | DATABASECHANGELOGLOCK/list-locks | Lock manager và system views của DBMS |
| Chủ thể | Liquibase process | Bất kỳ database session nào |
| Phạm vi | Cùng bảng khóa Liquibase | Hàng, bảng, metadata, page, key/range hoặc tài nguyên DBMS |
| Nguyên nhân chờ | Liquibase process khác giữ quyền migration | Transaction/DDL/session khác giữ lock xung đột |
| Công cụ xử lý | Xác minh owner, Liquibase release-locks khi stale | Xử lý blocker/transaction theo quy tắc DBMS |

Có thể gặp tình huống Liquibase đã giữ coordination lock nhưng SQL đang chờ DBMS table/metadata lock. list-locks vẫn hiển thị khóa Liquibase đang được giữ. Giải phóng khóa Liquibase không làm transaction ứng dụng nhả DBMS lock; nếu migration process còn sống, release thủ công có thể tạo thêm một Liquibase process khác cùng chạy.

Vì vậy phải xác định **lớp khóa đang gây chờ** trước khi chọn hành động.

## 12. PostgreSQL: tìm session chờ và session chặn

PostgreSQL cung cấp \`pg_stat_activity\` và hàm \`pg_blocking_pids\` để hỗ trợ điều tra.

Truy vấn chỉ đọc tham khảo:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_start,
    pg_blocking_pids(a.pid) AS blocker_pids
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.query_start;
~~~

Các điểm cần xem:

- Session Liquibase có còn kết nối không?
- State là active hay idle in transaction?
- Wait event có liên quan lock không?
- Có blocker PID nào không?
- Query bắt đầu lúc nào?
- Application name/user có trùng migration job không?

Có thể xem lock đang được cấp/chờ:

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation
FROM pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, locktype, mode;
~~~

Các view và thông tin hiển thị phụ thuộc quyền. Không kết luận mọi session idle đều vô hại: idle in transaction có thể giữ lock. Không kill PID chỉ vì query chạy lâu; cần owner, tác động và quy trình DBA.

## 13. MySQL/InnoDB: kiểm tra metadata lock và transaction

MySQL có metadata lock (MDL) bảo vệ định nghĩa object trong khi session sử dụng. Một transaction kéo dài có thể khiến ALTER TABLE chờ metadata lock, dù Liquibase đã lấy coordination lock.

Truy vấn tham khảo trên các phiên bản MySQL có Performance Schema phù hợp:

~~~sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = DATABASE();
~~~

Có thể cần kết hợp với \`performance_schema.data_locks\`, \`data_lock_waits\`, thông tin processlist hoặc transaction views tùy phiên bản. Instrumentation và quyền quan sát cần được cấu hình.

Trạng thái PENDING là dấu hiệu có yêu cầu lock chưa được cấp, nhưng chưa đủ để hiểu toàn bộ blocker chain. Xác định session đang giữ metadata/data lock và thời gian transaction trước khi can thiệp.

Không giả định MySQL và MariaDB có cùng view, cột hoặc hành vi DDL ở mọi phiên bản.

## 14. SQL Server: xem lock request và blocking session

SQL Server cung cấp DMV \`sys.dm_tran_locks\` để xem lock request và \`sys.dm_exec_requests\` để quan sát request đang chạy.

Ví dụ truy vấn chỉ đọc:

~~~sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status,
    resource_database_id
FROM sys.dm_tran_locks
WHERE resource_database_id = DB_ID();
~~~

Kết hợp thông tin request:

~~~sql
SELECT
    session_id,
    status,
    command,
    wait_type,
    wait_time,
    blocking_session_id
FROM sys.dm_exec_requests
WHERE database_id = DB_ID();
~~~

Cần quyền xem DMV tương ứng. Một Sch-M (schema modification) lock hoặc lock request khác có thể chờ session đang sử dụng object. Hãy xem blocking_session_id, wait_type và request thực tế.

Không kết thúc session SQL Server khi chưa xác định transaction, owner và khả năng rollback. KILL session có thể kích hoạt rollback transaction dài và kéo dài thời gian phục hồi.

## 15. Đánh giá thời gian lock: dài không đồng nghĩa stale

LOCKGRANTED cho biết thời điểm Liquibase ghi nhận cấp lock. Khoảng thời gian từ lúc đó đến hiện tại cần được so sánh với:

- Thời lượng migration dự kiến.
- Loại changeset (DDL, index build, data backfill).
- Kích thước bảng và số hàng.
- DBMS lock wait/statement duration.
- Log tiến độ mới nhất.
- Tình trạng pipeline và process.
- Thời gian deploy của các release trước.

Một migration tạo index trên bảng lớn có thể kéo dài hơn migration add column. Một backfill theo batch có thể chạy lâu nhưng vẫn có tiến độ. Một session bị block có thể không phát log mới trong thời gian dài dù process còn hoạt động.

Thiết lập alert theo ngưỡng dựa trên workload và baseline lịch sử. Alert nên tạo yêu cầu điều tra, không tự gọi release-locks.

## 16. Các nguyên nhân phổ biến khiến lock tồn tại

| Nguyên nhân | Dấu hiệu | Hướng kiểm tra |
|---|---|---|
| Migration đang chạy bình thường | Job running, DB session active | Theo dõi tiến độ và thời lượng |
| Migration chờ DBMS lock | Job running, session wait event/blocker | Tìm transaction chặn |
| Hai Liquibase job cùng target | Một job giữ lock, job khác chờ | Pipeline run list và list-locks |
| Process bị kill đột ngột | Job chết, bảng vẫn LOCKED=true | Kiểm tra session và schema một phần |
| Runner/Pod mất kết nối | Pipeline timeout, session có thể còn | Kiểm tra DB connection/process |
| DDL autocommit thất bại sau một phần | Schema đã đổi, history có thể thiếu | So sánh object và changeset |
| Cấu hình history table khác nhau | Job nhìn thấy lock khác hoặc không thấy lịch sử | Kiểm tra tên/schema bảng theo target |
| Job cũ chưa kết thúc nhưng retry đã tạo job mới | Nhiều session cùng target | Dừng tạo runner mới và xác minh owner |

Một lock tồn tại lâu có thể là hệ quả của nhiều nguyên nhân. Phải kết hợp dữ liệu từ cả Liquibase và DBMS.

## 17. Quy trình điều tra theo từng bước

Khi nhận cảnh báo lock:

1. **Dừng tạo thêm migration job** cho cùng target để tránh tăng cạnh tranh.
2. **Xác minh target**: environment, database, schema và bảng lock.
3. Chạy **list-locks** bằng đúng connection profile.
4. Ghi LOCKED, LOCKGRANTED, LOCKEDBY và thời điểm kiểm tra.
5. Tìm pipeline/job/Pod/runner có khả năng sở hữu lock.
6. Kiểm tra process và log cuối cùng.
7. Quan sát DBMS session, transaction, blocker và wait event.
8. Đối chiếu DATABASECHANGELOG và changeset đang xử lý.
9. Kiểm tra schema/data để xác định SQL đã thực thi toàn bộ, một phần hay chưa.
10. Phân loại ACTIVE, STALE hoặc UNKNOWN.
11. Chọn hành động theo runbook và quyền phê duyệt.
12. Hậu kiểm history, schema, data và trạng thái lock.

Không bỏ qua bước xác minh target. Một list-locks chạy nhầm database có thể tạo cảm giác an toàn giả.

## 18. ACTIVE: migration vẫn còn tiến trình hợp lệ

Dấu hiệu ACTIVE có thể gồm:

- Pipeline đang running.
- Pod/container còn tồn tại và process Liquibase còn hoạt động.
- Database session migration còn kết nối.
- Query đang thực thi hoặc chờ một DBMS lock có blocker xác định.
- Log cho thấy tiến độ hoặc statement hiện hành.

Trong tình huống này:

- Không chạy release-locks.
- Không xóa hoặc cập nhật trực tiếp DATABASECHANGELOGLOCK.
- Không khởi chạy một migration job khác trên cùng target.
- Xác định migration đang chạy hay đang bị block.
- Phối hợp với owner session/blocker để chọn chờ, dời lịch hoặc hủy theo quy trình.
- Theo dõi trạng thái sau khi owner kết thúc.

Nếu cần dừng job, hãy dùng cơ chế cancel/stop của pipeline và hiểu cách driver/DBMS xử lý query đang chạy. Sau khi cancel, vẫn phải kiểm tra session và trạng thái schema trước khi đánh giá lock.

## 19. STALE: khi nào có thể nghi ngờ khóa bị bỏ lại?

Stale lock là trạng thái bảng khóa còn ghi nhận LOCKED=true nhưng tiến trình đã giữ khóa không còn hoạt động và không còn công việc migration hợp lệ tiếp tục.

Bằng chứng cần có:

- Pipeline run đã kết thúc bất thường hoặc được xác nhận không còn chạy.
- Không còn process/Pod/runner sở hữu job đó.
- Không còn DB session migration đang thực thi hoặc chờ tiếp tục công việc.
- Không còn query bị hủy nhưng session chưa đóng.
- Owner và DBA đã kiểm tra trạng thái database.
- Schema/data/history đã được đối chiếu để xác định thay đổi một phần.
- Không có release khác đang sử dụng cùng bảng lock.

Không chỉ dựa vào LOCKGRANTED cũ hoặc LOCKEDBY trỏ tới host không còn thấy. Nếu thiếu bằng chứng về session hoặc process, giữ trạng thái UNKNOWN.

## 20. UNKNOWN: xử lý khi bằng chứng chưa đủ

Có thể không xác định được owner vì log đã hết hạn, runner bị xóa, quyền DMV hạn chế hoặc session database không hiển thị đầy đủ.

Khi đó:

- Không giải phóng lock.
- Không xóa bảng hoặc row lock.
- Không chạy update/retry.
- Giữ target ở trạng thái blocked.
- Yêu cầu owner database/DBA cấp bằng chứng còn thiếu.
- Kiểm tra audit log, job history, connection audit và monitoring.
- Đánh giá schema/data bằng quyền chỉ đọc.
- Ghi rõ điều gì đã biết và điều gì chưa thể xác minh.

Một lần dừng có kiểm soát thường ít rủi ro hơn việc giải phóng nhầm khóa khi migration còn chạy.

## 21. release-locks: thao tác quản trị sau khi xác nhận stale

Liquibase cung cấp lệnh **release-locks** để giải phóng trạng thái khóa điều phối trong bảng DATABASECHANGELOGLOCK.

Lệnh thường dùng:

~~~text
liquibase release-locks
~~~

Cú pháp và cách gọi cần theo đúng Liquibase version/CLI/plugin. Chạy bằng đúng connection profile, schema history và target đã được xác minh.

Chỉ cân nhắc sau khi:

1. Owner xác nhận job cũ đã kết thúc.
2. Không còn process Liquibase hoạt động.
3. Không còn DB session migration tiếp tục thực thi hoặc chờ.
4. Trạng thái schema/data và DATABASECHANGELOG đã được kiểm tra.
5. Xác định không có job mới cạnh tranh.
6. Có người có quyền phê duyệt theo quy trình vận hành.
7. Ghi lại target, bằng chứng, operator và thời điểm.

**release-locks không rollback changeset và không phục hồi dữ liệu.** Nó chỉ giải phóng coordination lock mà Liquibase đang ghi nhận. Nếu migration đã thực hiện một phần, việc thả khóa không tự đưa database về trạng thái trước đó.

## 22. Vì sao không sửa trực tiếp DATABASECHANGELOGLOCK?

Một số hướng dẫn không chính thức khuyên chạy SQL để đặt LOCKED=false hoặc xóa hàng khóa. Đây không phải cách xử lý mặc định an toàn.

Ví dụ dưới đây chỉ minh họa một thao tác không nên thực hiện tùy tiện:

~~~sql
-- Không chạy tùy tiện trên môi trường thật:
UPDATE DATABASECHANGELOGLOCK
SET LOCKED = FALSE
WHERE ID = 1;
~~~

Thao tác trực tiếp có thể bỏ qua cơ chế kiểm tra của Liquibase và làm cho một job khác lấy khóa trong khi owner cũ vẫn còn hoạt động. Nếu DBMS/driver hoặc cấu hình dùng kiểu dữ liệu khác, câu lệnh còn có thể không phù hợp.

Không xóa row ID=1, drop bảng lock hoặc sửa DATABASECHANGELOG để che lỗi. Ưu tiên lệnh Liquibase được hỗ trợ sau khi stale lock đã được xác minh. Can thiệp trực tiếp chỉ thuộc quy trình DBA đặc biệt có phê duyệt, backup, bằng chứng và kế hoạch phục hồi cụ thể.

## 23. Sau khi release-locks, chưa được retry ngay một cách mù quáng

Trước lần update tiếp theo:

1. Chạy list-locks lại để xác nhận trạng thái khóa.
2. Kiểm tra không có process/job cũ hoặc mới đang giữ lock.
3. Đọc DATABASECHANGELOG của target.
4. Xác định changeset cuối cùng đã được ghi nhận.
5. Đối chiếu schema object và dữ liệu liên quan.
6. Kiểm tra DDL có implicit commit hay changeset dùng runInTransaction=false.
7. Xác định SQL nào có thể đã chạy nhưng chưa được ghi history.
8. Chọn retry cùng revision, forward fix hoặc restore theo bằng chứng.
9. Chạy validate/status/updateSQL khi phù hợp.
10. Thực thi có giám sát và hậu kiểm.

Nếu changeset tạo bảng đã chạy nhưng lịch sử chưa ghi, retry có thể lỗi table exists. Nếu changeset update dữ liệu đã chạy một phần, retry có thể tác động thêm hàng. Hãy sửa trạng thái theo một changeset mới hoặc recovery plan được review, không xóa row lịch sử để ép chạy lại.

## 24. Retry policy và timeout không thay thế chẩn đoán

Một pipeline có thể chờ lấy Liquibase lock trong một khoảng thời gian được cấu hình. Các thuộc tính về lock wait/polling có thể khác theo phiên bản. Tăng timeout có thể hữu ích khi migration hợp lệ nhưng lâu; nó không giải quyết stale lock, blocker hoặc target mismatch.

Phân biệt các timeout:

| Loại | Ý nghĩa |
|---|---|
| Connection timeout | Không thiết lập được kết nối |
| Liquibase lock wait | Chờ tiến trình Liquibase khác nhả coordination lock |
| DBMS lock timeout | Chờ khóa object/transaction |
| Statement timeout | Câu SQL chạy hoặc chờ vượt thời gian |
| Job timeout | Tổng thời gian pipeline cho phép |

Retry nên có giới hạn và backoff. Không tự động release-locks khi timeout; cũng không retry checksum mismatch, permission hoặc target mismatch như lỗi mạng tạm thời.

## 25. Spring Boot nhiều replica và list-locks

Nếu Spring Boot bật Liquibase startup migration, nhiều replica có thể cùng khởi động. Các process cùng sử dụng DATABASECHANGELOGLOCK sẽ cạnh tranh khóa:

- Một process lấy lock và thực hiện migration.
- Những process khác chờ hoặc báo không lấy được lock theo cấu hình.
- Khi process đầu hoàn tất, process tiếp theo có thể tiếp tục kiểm tra lịch sử.
- Startup latency có thể tăng và readiness probe có thể hết thời gian.

Khi có cảnh báo, dùng list-locks để quan sát target, sau đó đối chiếu Pod/Deployment và DB sessions. Không chỉ xem số replica; cần biết Pod nào thực sự chạy Liquibase và revision nào.

Trong production nhiều replica, có thể chuyển sang migration Job riêng và tắt auto-run ở application runtime. Khi đó job là owner rõ ràng, còn ứng dụng chỉ khởi động sau readiness gate. Dù chọn mô hình nào, không để pipeline và Spring Boot cùng chạy migration ngoài chính sách single-writer.

## 26. Nhiều database: list-locks phải theo từng target

Mỗi database thường có DATABASECHANGELOGLOCK riêng. Khóa ở customer_db không khóa order_db hoặc billing_db.

Khi điều tra release nhiều database:

- Chạy list-locks riêng trên từng target.
- Ghi database/schema và history table được dùng.
- Không suy ra target khác đang unlocked từ kết quả một target.
- Đối chiếu release/job ID theo từng database.
- Giữ trạng thái thành công/thất bại riêng cho từng đích.
- Chặn consumer phụ thuộc nếu provider còn migration hoặc chưa readiness.
- Không release lock ở database A để giải quyết lỗi database B.

Nếu nhiều logical schema cùng nằm trong một physical database, phải xác định chúng dùng chung hay tách bảng lock/history. Tách bảng lock không tự giải quyết xung đột khi hai job cùng sửa object phụ thuộc.

## 27. Quyền và bảo mật khi kiểm tra khóa

list-locks cần connection tới database và quyền đọc bảng lock cùng metadata liên quan. Việc xem DBMS sessions/lock manager có thể cần quyền giám sát riêng.

Nên tách:

- Tài khoản migration có quyền thực thi DDL/DML theo phạm vi.
- Tài khoản giám sát chỉ đọc history/lock và metadata cần thiết.
- Quyền DBA/kill session chỉ cấp cho nhóm được ủy quyền.
- Secret được lấy từ secret manager, không lưu trong command log.
- Log không chứa password, token, private key hoặc PII.
- Báo cáo sự cố chỉ lưu database alias/target ID, không công khai full JDBC URL có credential.

Không cấp superuser cho mọi người chỉ để chạy list-locks. Nếu cần xem DBMS lock views, dùng quyền giám sát phù hợp và lưu audit.

## 28. Ghi nhận sự cố lock để có thể truy vết

Một lock incident record nên có:

| Trường | Nội dung |
|---|---|
| Incident/release ID | Liên kết sự cố và release |
| Target ID | Database đích |
| Environment/DBMS | Môi trường và hệ quản trị |
| History/lock table | Schema và tên bảng được kiểm tra |
| Liquibase version | Phiên bản công cụ |
| list-locks result | LOCKED, LOCKGRANTED, LOCKEDBY |
| Pipeline/process owner | Job, runner, Pod hoặc host |
| DBMS session | Session ID, state, wait/blocker nếu có |
| Last changeset | ID/author/filename và EXECTYPE liên quan |
| Classification | ACTIVE, STALE hoặc UNKNOWN |
| Decision | Wait, cancel, release-locks, retry hoặc forward fix |
| Approval/operator | Người phê duyệt và thực hiện |
| Post-check | Lock/history/schema/data sau xử lý |

Ghi thời gian theo timezone rõ ràng. Nếu các hệ thống dùng clock khác nhau, đối chiếu timestamp cần tính đến lệch đồng hồ.

Không đưa dữ liệu nhạy cảm vào incident record. Cần đủ bằng chứng để người trực sau hiểu vì sao lock được giữ hoặc giải phóng.

## 29. Runbook mẫu: xử lý cảnh báo Liquibase đang bị khóa

**Pha A — Khoanh vùng**

1. Nhận target ID và release ID.
2. Dừng tạo thêm job cho cùng target.
3. Xác minh database/schema và bảng lock.
4. Chạy list-locks bằng đúng connection profile.
5. Ghi kết quả và timestamp.

**Pha B — Xác minh owner**

6. Tra pipeline run và runner.
7. Kiểm tra process/Pod/container.
8. Kiểm tra DBMS session, query, wait event và blocker.
9. Đối chiếu DATABASECHANGELOG và changeset đang chạy.
10. Kiểm tra schema/data nếu job đã lỗi hoặc bị cancel.

**Pha C — Quyết định**

- Nếu ACTIVE: không release; theo dõi hoặc phối hợp owner/blocker.
- Nếu STALE đã được xác minh: xin phê duyệt, dùng release-locks đúng target.
- Nếu UNKNOWN: giữ blocked và yêu cầu thêm bằng chứng.

**Pha D — Hậu kiểm**

11. Chạy list-locks lại.
12. Đối chiếu DATABASECHANGELOG và schema/data.
13. Chạy status/updateSQL để xác định pending changeset.
14. Chỉ retry khi trạng thái một phần đã được hiểu và kế hoạch phục hồi rõ.
15. Lưu incident record và nguyên nhân gốc.

Runbook này là quy trình điều tra; quyền release và kill session phải tuân theo chính sách vận hành của tổ chức.

## 30. Bài thực hành: đánh giá ba tình huống khóa

Thực hành trên database disposable, không dùng production.

### Tình huống A — Migration đang hoạt động

1. Khởi chạy một Liquibase update đủ lâu trên database thử nghiệm.
2. Từ terminal/job khác, chạy list-locks cùng target.
3. Đối chiếu LOCKED/LOCKGRANTED/LOCKEDBY với pipeline và DBMS session.
4. Xác nhận process còn sống và SQL đang chạy hoặc chờ.
5. Phân loại ACTIVE; không chạy release-locks.
6. Chờ job kết thúc và chạy list-locks lại.

### Tình huống B — Liquibase lock và DBMS lock cùng tồn tại

1. Session ứng dụng A mở transaction và giữ lock trên bảng thử nghiệm.
2. Liquibase job B chạy changeset muốn ALTER/UPDATE bảng đó.
3. Chạy list-locks: Liquibase có thể đang giữ coordination lock.
4. Quan sát DBMS session B đang chờ blocker A.
5. Kết thúc transaction A theo cách có kiểm soát trên môi trường lab.
6. Xác nhận migration B tiếp tục, ghi history và thả Liquibase lock.

Bài học: list-locks không cho biết đầy đủ blocker của DBMS.

### Tình huống C — Mô phỏng stale lock có kiểm soát

1. Dùng database disposable và ghi lại trạng thái ban đầu.
2. Thực hiện kịch bản dừng bất thường của migration process theo công cụ lab.
3. Kiểm tra job/process/session còn hoạt động không.
4. Đọc list-locks và đối chiếu schema/history.
5. Chỉ khi xác nhận không còn owner/session và lock thực sự stale, dùng release-locks trên database lab.
6. Kiểm tra lock đã được giải phóng, schema/data có thể ở trạng thái nào.
7. Chạy status/updateSQL và quyết định cách tiếp tục.

Không cố tình sửa DATABASECHANGELOGLOCK bằng SQL để mô phỏng; hãy dùng kịch bản thử nghiệm được kiểm soát và công cụ Liquibase phù hợp.

## 31. Checklist vận hành list-locks

- [ ] Đã xác định đúng target, environment, database và schema.
- [ ] Đã xác nhận tên/schema của DATABASECHANGELOGLOCK.
- [ ] Đã dùng đúng Liquibase version và connection profile.
- [ ] Đã chạy list-locks và lưu kết quả cùng timestamp.
- [ ] Đã ghi LOCKED, LOCKGRANTED, LOCKEDBY nếu output cung cấp.
- [ ] Không kết luận stale chỉ dựa vào thời gian lock cũ.
- [ ] Đã đối chiếu pipeline, runner, Pod/process và job owner.
- [ ] Đã kiểm tra DBMS session, transaction, wait event và blocker.
- [ ] Đã phân biệt Liquibase coordination lock với DBMS object lock.
- [ ] Đã đối chiếu DATABASECHANGELOG, EXECTYPE và changeset cuối.
- [ ] Đã kiểm tra schema/data để phát hiện thay đổi một phần.
- [ ] ACTIVE thì không release-locks hoặc mở thêm migration job.
- [ ] UNKNOWN thì giữ blocked và tiếp tục điều tra.
- [ ] STALE chỉ được xác nhận khi không còn owner/process/session liên quan.
- [ ] release-locks chỉ chạy sau phê duyệt và bằng đúng target.
- [ ] Không UPDATE/DELETE trực tiếp bảng lock để xử lý thông thường.
- [ ] Sau release đã chạy list-locks và hậu kiểm history/schema/data.
- [ ] Retry có giới hạn và dựa trên trạng thái thực tế.
- [ ] Quyền giám sát, quyền migration và quyền DBA được tách phù hợp.
- [ ] Incident record có bằng chứng, operator, approval và kết quả hậu kiểm.
- [ ] Đã kiểm thử runbook trên database disposable.

**Ghi nhớ:** \`list-locks\` cho biết Liquibase đang ghi nhận trạng thái khóa điều phối trên database đích. Nó không chứng minh process còn sống hay đã chết, cũng không hiển thị đầy đủ blocker của DBMS. Hãy xác minh target, pipeline owner, process/Pod, DBMS sessions và DATABASECHANGELOG trước khi phân loại ACTIVE, STALE hoặc UNKNOWN. Chỉ dùng \`release-locks\` khi stale lock đã được chứng minh và có phê duyệt; sau đó vẫn phải đối chiếu schema/data và history trước khi retry. Đánh giá khóa dựa trên bằng chứng giúp tránh hai migration chạy đồng thời và giữ lịch sử triển khai Liquibase nhất quán.

