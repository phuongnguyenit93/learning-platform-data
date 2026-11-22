
# Khóa điều phối của Liquibase và khóa đối tượng trong cơ sở dữ liệu

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi nhiều ứng dụng, pipeline hoặc tiến trình cùng kết nối một database, hai loại khóa rất dễ bị nhầm lẫn: **khóa điều phối của Liquibase**, giúp tránh nhiều tiến trình Liquibase cùng thực hiện migration thiếu kiểm soát; và **khóa đối tượng/giao dịch do DBMS quản lý**, bảo vệ tính nhất quán khi thực thi DDL hoặc DML trên bảng, hàng, metadata và các tài nguyên khác.

Bài thuộc chương **Giao dịch và khóa** này giải thích sự khác biệt, cách chúng tương tác, vì sao pipeline có thể chờ dù Liquibase đã lấy được khóa điều phối, và cách xử lý an toàn khi migration bị treo, lock chờ lâu hoặc thất bại giữa chừng. Nội dung áp dụng cho migration chạy từ CLI, Maven/Gradle plugin, Spring Boot hoặc CI/CD, với các ví dụ minh họa PostgreSQL, MySQL, SQL Server và các DBMS có cơ chế tương tự.

Sau bài học, người học cần có thể: đọc trạng thái DATABASECHANGELOGLOCK; phân biệt một Liquibase lock với database lock; chẩn đoán blocked session, deadlock và lock timeout; quyết định khi nào **không được** giải phóng lock; đồng thời thiết kế thay đổi schema/dữ liệu giảm thời gian chặn ứng dụng trong nhiều môi trường.

## 1. Hai lớp khóa giải quyết hai bài toán khác nhau

| Khía cạnh | Khóa điều phối Liquibase | Khóa đối tượng/giao dịch của DBMS |
|---|---|---|
| Mục tiêu | Điều phối các lệnh Liquibase cùng quản lý một lịch sử migration | Bảo vệ tính nhất quán khi transaction, DDL, DML truy cập tài nguyên database |
| Thành phần chịu trách nhiệm | Dịch vụ lock của Liquibase và bảng DATABASECHANGELOGLOCK mặc định | Lock manager của PostgreSQL, MySQL, SQL Server, Oracle... |
| Đối tượng | Quyền tiến hành migration Liquibase trên database/schema cấu hình tương ứng | Hàng, bảng, index, metadata/schema, page, key/range hoặc tài nguyên khác |
| Thời gian tồn tại | Thường trong khoảng Liquibase giữ quyền chạy tác vụ migration, được thả khi kết thúc bình thường | Tùy statement, transaction, DBMS và chế độ khóa |
| Phạm vi | Những tiến trình Liquibase trỏ đến cùng cơ chế/bảng lock | Các session truy cập đối tượng bị khóa, bao gồm ứng dụng không dùng Liquibase |
| Có bảo vệ dữ liệu ứng dụng trực tiếp? | Không; không thay thế transaction/isolation | Có, theo quy tắc DBMS |
| Có ngăn sửa schema thủ công ngoài Liquibase? | Không | Có thể xung đột/chờ bởi lock DBMS tương ứng, không phải bởi DATABASECHANGELOGLOCK |
| Khi sự cố | Có thể tồn tại trạng thái lock bị giữ lại sau job ngừng bất thường | Có thể có session chặn, deadlock, lock timeout hoặc transaction chưa kết thúc |

**Kết luận cốt lõi:** giữ được Liquibase lock không có nghĩa SQL đã có thể chạy ngay. Liquibase có thể đã được quyền migration nhưng đang **chờ lock bảng hoặc lock metadata** do ứng dụng khác giữ. Ngược lại, nếu một transaction ứng dụng giữ lock trên customer, điều đó không có nghĩa nó sở hữu DATABASECHANGELOGLOCK.

## 2. Trình tự điển hình khi Liquibase chạy update

Một luồng đơn giản:

~~~text
Pipeline / ứng dụng gọi Liquibase update
                |
                v
Đọc cấu hình kết nối, changelog, lịch sử
                |
                v
Đề nghị lấy quyền chạy migration
qua DATABASECHANGELOGLOCK
                |
          +-----+------+
          |            |
      Lấy được      Đang bị giữ
          |            |
          v            v
   Xác định pending  Chờ/thử lại hoặc lỗi
   changeset         theo cấu hình
          |
          v
   Đánh giá các điều kiện phù hợp
          |
          v
   Gửi DDL/DML tới DBMS
          |
          v
   DBMS quyết định khóa đối tượng,
   transaction, wait/deadlock/timeout
          |
          v
   Cập nhật DATABASECHANGELOG
   theo kết quả migration
          |
          v
   Giải phóng Liquibase lock
   khi lệnh kết thúc bình thường
~~~

Đây là mô hình để hiểu thứ tự trách nhiệm, không phải mô tả mọi lời gọi nội bộ của mọi phiên bản Liquibase. Một số bước kiểm tra, validation hoặc khởi tạo bảng lịch sử có thể diễn ra ở vị trí khác tùy cơ chế và lệnh. Điều cần giữ là: **Liquibase điều phối việc chạy migration**, còn DBMS quyết định **statement thật có được lock tài nguyên và thực thi hay không**.

Với rollback hay những lệnh thay đổi database có cơ chế khóa tương ứng, vẫn cần quan tâm cả hai lớp khóa. Không giả định mọi lệnh chỉ đọc như status hay validate đều nhất thiết lấy lock điều phối theo đúng cách update.

## 3. Bảng DATABASECHANGELOGLOCK và ý nghĩa các cột

Mặc định Liquibase tạo/sử dụng một bảng tên **DATABASECHANGELOGLOCK** để điều phối quá trình migration. Trong cấu hình thông thường, bảng chứa một bản ghi khóa điều phối với các cột chính:

| Cột | Ý nghĩa thường gặp |
|---|---|
| ID | Định danh hàng khóa; thiết lập mặc định thường dùng ID=1 |
| LOCKED | Cờ cho biết Liquibase lock đang được giữ theo trạng thái bảng |
| LOCKGRANTED | Thời điểm lock được ghi nhận cấp |
| LOCKEDBY | Thông tin mô tả host hoặc tiến trình được ghi nhận giữ lock |

Câu truy vấn **chỉ đọc** tham khảo:

~~~sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

Câu SQL này chỉ đúng khi bảng lịch sử khóa dùng tên và schema mặc định hoặc đã được chọn đúng schema. Nếu Liquibase được cấu hình **databaseChangeLogLockTableName**, schema lịch sử riêng hoặc một cách đặt tên khác, cần truy vấn đúng vị trí tương ứng. Quyền truy cập và kiểu dữ liệu boolean cũng phụ thuộc DBMS.

Ví dụ kết quả minh họa:

~~~text
ID | LOCKED | LOCKGRANTED          | LOCKEDBY
1  | true   | 2026-11-19 14:05:10  | migration-job@runner-01
~~~

Điều này cho biết **bảng đang ghi nhận lock được giữ**. Nó không tự chứng minh job vẫn hoạt động, không cho biết transaction đang chặn bảng nào, và không chứng minh SQL migration đã thành công. Thời điểm và thông tin LOCKEDBY là manh mối để điều tra cùng với log CI/CD và session database.

## 4. DATABASECHANGELOG và DATABASECHANGELOGLOCK không giống nhau

Hai bảng có vai trò khác:

- **DATABASECHANGELOG** ghi nhận lịch sử changeset theo id, author, FILENAME, checksum, EXECTYPE, thời gian, v.v. Nó trả lời “changeset nào đã được xử lý tại database này?”.
- **DATABASECHANGELOGLOCK** điều phối quyền chạy migration. Nó trả lời “Liquibase có đang ghi nhận một tiến trình giữ quyền migration không?”.

Ví dụ một pipeline có thể đã lấy được lock, nhưng chưa thực hiện thành công changeset nào do đang chờ DDL lock. Khi đó:

1. DATABASECHANGELOGLOCK có thể cho biết LOCKED=true.
2. DATABASECHANGELOG chưa có bản ghi cho changeset mới.
3. DBMS có thể có session đang chờ trên bảng do một transaction ứng dụng giữ lock.

Việc nhìn thấy LOCKED=true rồi xóa bản ghi trong DATABASECHANGELOG hoặc sửa checksum là **sai vấn đề**. Ngược lại, chỉ vì DATABASECHANGELOG có đầy đủ changeset không có nghĩa hiện tại không có một tiến trình khác đang giữ lock để đánh giá cập nhật mới.

## 5. Phạm vi khóa điều phối: cùng database và cùng cấu hình lịch sử

Liquibase lock giúp điều phối những lệnh Liquibase **đang sử dụng cùng bảng khóa có hiệu lực**. Trong dự án nhiều schema, nhiều database, nhiều service, phạm vi này phải được xác định chính xác.

Một số tình huống:

- Hai pod Spring Boot cùng trỏ vào **một database và cùng DATABASECHANGELOGLOCK**: chúng có thể cạnh tranh cùng lock. Một pod được quyền chạy migration trước; pod khác thường phải chờ.
- Hai pipeline trỏ vào **hai database khác nhau**: mỗi database có lịch sử và lock riêng; chúng không tự điều phối với nhau.
- Hai Liquibase job trỏ cùng database nhưng được cấu hình **bảng lock khác tên hoặc khác schema**: chúng có thể không dùng cùng cơ chế điều phối, dù cùng tác động lên bảng ứng dụng. Đây là cấu hình nguy hiểm nếu migration phụ thuộc nhau.
- Một DBA chạy ALTER TABLE thủ công: thao tác này không phải tiến trình Liquibase tham gia lock điều phối; DBMS vẫn có thể gây xung đột tài nguyên khi hai bên chạy đồng thời.

Không coi DATABASECHANGELOGLOCK là **distributed lock tổng quát** cho toàn bộ ứng dụng hoặc mọi hệ thống. Nó phục vụ cơ chế quản lý migration Liquibase, không thay thế lock nghiệp vụ, leader election, job scheduler, hay thứ tự triển khai giữa nhiều service.

## 6. Hai tiến trình Liquibase đồng thời: điều gì thường xảy ra?

Giả sử hai pipeline A và B cùng muốn cập nhật một database:

~~~text
Thời điểm  Pipeline A                     Pipeline B
T0        Bắt đầu update                  Bắt đầu update
T1        Lấy được Liquibase lock         Chưa lấy được, chờ
T2        Chạy changeset pending          Tiếp tục chờ
T3        Ghi lịch sử và thả lock         Có thể lấy được lock
T4        Kết thúc                       Đọc trạng thái hiện thời
T5                                       Bỏ qua changeset đã được ghi nhận,
                                         hoặc xử lý changeset còn pending
~~~

Cơ chế này giảm nguy cơ **hai Liquibase job cùng áp dụng một changeset trên một database**. Tuy nhiên nó không bảo đảm các pipeline A và B có cùng revision changelog hoặc code tương thích.

Nếu A triển khai release 12 rồi B dùng một changelog cũ của release 11, lịch sử và cấu hình có thể gây vấn đề khi B kiểm tra checksum, changelog hoặc muốn rollback. Nếu B mang một revision mới hơn chưa được phê duyệt, việc lấy được lock sau A có thể dẫn đến migration không đúng thứ tự phát hành mà tổ chức dự kiến.

**Lock giải quyết sự đồng thời, không giải quyết quản trị phiên bản release.** Cần một cơ chế điều phối deploy bảo đảm artifact, schema version, thứ tự và approvals.

## 7. Khóa DBMS phát sinh từ DML

Trong khi Liquibase giữ quyền migration, các câu lệnh DML được DBMS thực thi theo cơ chế transaction và isolation của hệ quản trị đó.

Ví dụ:

~~~sql
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Trên DBMS hỗ trợ row-level locking, UPDATE thường lấy các khóa phù hợp trên những hàng cần sửa và có thể phải chờ transaction khác đang giữ tài nguyên xung đột. Ngoài row locks, DBMS có thể dùng những cơ chế khóa khác tùy access path, index, isolation level, foreign key, trigger hoặc cơ chế MVCC.

Các ảnh hưởng thực tế:

- Transaction ứng dụng giữ lock lâu khiến UPDATE migration phải chờ.
- UPDATE trên rất nhiều hàng có thể giữ khóa kéo dài và tạo lượng WAL/redo/undo lớn.
- Foreign key hoặc trigger có thể gây thêm truy cập và lock tới bảng khác.
- Thiếu index phù hợp với WHERE khiến nhiều hàng bị quét/đụng tới hơn dự kiến.
- Replication lag, deadlock hoặc timeout có thể xuất hiện dù Liquibase lock đã lấy thành công.

Không kết luận rằng “update chỉ sửa 100 hàng nên chắc chỉ có 100 khóa”. Quy tắc khóa phụ thuộc từng DBMS; ví dụ cơ chế lock escalation của SQL Server hoặc gap/next-key locks của MySQL InnoDB khác PostgreSQL.

## 8. Khóa DBMS phát sinh từ DDL

Các lệnh như CREATE INDEX, ALTER TABLE, ADD CONSTRAINT, DROP COLUMN có thể yêu cầu lock ở mức bảng, schema hoặc metadata. Độ mạnh và thời gian giữ lock phụ thuộc DBMS, tùy chọn DDL và phiên bản.

| Loại thao tác | Rủi ro thường gặp |
|---|---|
| ADD COLUMN | Cần lock metadata/schema; một số dạng thay đổi có thể phải rewrite dữ liệu |
| ALTER COLUMN TYPE | Có thể yêu cầu rewrite bảng, scan/validate dữ liệu và lock lâu |
| CREATE INDEX | Có thể đọc/quét bảng lớn và chặn một số hoạt động đồng thời |
| ADD FOREIGN KEY | Có thể cần truy cập/khóa cả bảng nguồn và bảng tham chiếu; validation tốn thời gian |
| DROP COLUMN / DROP TABLE | Có thể chặn truy vấn đang chạy và gây lỗi ứng dụng còn phụ thuộc đối tượng |
| RENAME TABLE / COLUMN | Có thể yêu cầu metadata lock và tạo rủi ro tương thích phiên bản ứng dụng |

Không phải mọi CREATE INDEX đều khóa độc quyền suốt quá trình. Một số DBMS cung cấp tùy chọn online/concurrent; nhưng chúng có ràng buộc riêng và vẫn cần lock metadata hoặc các pha chờ nhất định.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX CONCURRENTLY idx_customer_status
ON customer (status);
~~~

CREATE INDEX CONCURRENTLY giúp giảm một số tác động blocking so với cách tạo index thông thường, nhưng **không được chạy trong transaction block** và có các giai đoạn chờ riêng. Nếu sử dụng qua Liquibase, thường cần changeset dành riêng cho PostgreSQL cùng cấu hình transaction phù hợp, ví dụ runInTransaction: false, và kiểm chứng trên đúng phiên bản. Cách chạy không transaction cũng làm thay đổi kế hoạch khôi phục nếu câu lệnh thất bại.

## 9. Khóa Liquibase không thay thế transaction

Một changeset có thể có cấu hình **runInTransaction** để Liquibase dùng transaction khi DBMS hỗ trợ. Nhưng khóa điều phối và transaction phục vụ hai trách nhiệm tách biệt.

| Khái niệm | Câu hỏi nó giải quyết |
|---|---|
| DATABASECHANGELOGLOCK | Có một Liquibase process khác đang điều phối migration này không? |
| runInTransaction | Các thay đổi trong changeset có được cố gắng thực thi trong transaction không? |
| Transaction của DBMS | Khi nào lock đối tượng được lấy/thả, những thay đổi nào có thể rollback? |
| Database isolation | Transaction này quan sát và xung đột với transaction khác như thế nào? |
| Rollback Liquibase | Thực thi một chuỗi thay đổi để quay lui lịch sử theo kế hoạch nào? |

Ví dụ có một changeset gồm UPDATE rồi ALTER TABLE. Cho dù Liquibase có khóa điều phối suốt update, tính nguyên tử của hai statement vẫn phụ thuộc hỗ trợ DDL transaction của DBMS. Một số DBMS có implicit commit với nhiều thao tác DDL; khi câu thứ hai lỗi, câu đầu có thể đã có tác động không tự phục hồi theo cách mong đợi.

**runInTransaction: false không tắt DATABASECHANGELOGLOCK.** Ngược lại, lấy được DATABASECHANGELOGLOCK không bảo đảm mọi DDL/DML sẽ rollback cùng nhau. Không sử dụng một cơ chế để suy luận thay cơ chế còn lại.

## 10. Khóa được giữ trong bao lâu?

Có ba khoảng thời gian đáng quan sát:

1. **Chờ lock Liquibase:** trước khi tiến trình có quyền chạy migration; thường do một Liquibase job khác giữ bảng lock.
2. **Thực thi changeset:** sau khi lấy được lock Liquibase, SQL đang chạy hoặc chờ các lock DBMS.
3. **Hoàn tất và giải phóng:** cập nhật lịch sử, commit/rollback những phần phù hợp và thả quyền điều phối.

Một migration lâu chưa chắc là do **khóa Liquibase bị kẹt**. Nó có thể đang được tiến trình hợp lệ giữ khi thực hiện một index build, backfill lớn hoặc chờ lock bảng từ ứng dụng. Tăng thời gian chờ lấy khóa Liquibase chỉ giúp tiến trình thứ hai chờ lâu hơn; nó **không sửa được session DBMS đang chặn câu SQL**.

Trong vận hành, nên ghi riêng:

- Thời gian chờ lấy khóa Liquibase.
- Thời gian chờ lock do DBMS.
- Thời gian thực thi thực tế từng changeset.
- Thời gian toàn bộ migration và kết quả cuối.
- Phiên bản changelog, ứng dụng và DBMS.

Các thông số timeout, số lần retry và tên tùy chọn có thể thay đổi theo phiên bản Liquibase, JDBC hoặc DBMS; hãy đối chiếu cấu hình chính xác trước khi thay đổi ở production.

## 11. Phân biệt chờ, lock timeout, statement timeout và deadlock

Bốn trạng thái thường bị gọi chung là “database bị khóa”, nhưng cần xử lý khác nhau.

**Chờ lock (blocking):** transaction/DDL đang chờ một tài nguyên do session khác nắm giữ. Chờ có thể kết thúc bình thường khi session giữ khóa commit.

**Lock timeout:** DBMS hoặc driver từ chối chờ lâu hơn ngưỡng thiết lập để lấy lock. Cần xem blocker và thiết kế lại thời điểm/thời gian thao tác.

**Statement/query timeout:** câu lệnh vượt thời gian cho phép tổng thể. Nó có thể tốn thời gian vì chạy chậm, vì bị block hoặc do kế hoạch thực thi không phù hợp; không mặc nhiên suy ra lock.

**Deadlock:** hai hay nhiều transaction giữ các tài nguyên mà bên kia cần, tạo vòng chờ. DBMS thường phát hiện và lựa chọn một transaction làm nạn nhân để phá vòng. Cách xử lý dài hạn là sửa thứ tự truy cập dữ liệu, rút ngắn transaction và kiểm soát concurrency; không chỉ tăng timeout.

Đối chiếu log lỗi, session DBMS, câu SQL hiện tại và thứ tự các changeset trước khi quyết định retry. Nếu migration không idempotent hoặc đã thực thi một phần, retry thiếu kiểm chứng có thể làm sai dữ liệu.

## 12. PostgreSQL: xem session chờ và tiến trình chặn

Trong PostgreSQL, có thể dùng các view hệ thống theo quyền được cấp để xác định session chờ và những tiến trình chặn. Ví dụ truy vấn **chỉ đọc**:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocker_pids
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.pid;
~~~

Nếu một session Liquibase có blocker_pids khác rỗng, cần tìm session gây blocking, statement, thời gian transaction và quyền sở hữu trước khi xử lý. Một session idle in transaction có thể giữ lock lâu dù không còn chạy câu SQL nào.

Có thể xem tổng quan các lock đang được yêu cầu/cấp:

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

Các truy vấn này là điểm bắt đầu chẩn đoán, không phải một phép phân tích deadlock đầy đủ. Một số thông tin câu SQL, session hoặc lock có thể bị giới hạn bởi quyền giám sát và cấu hình hệ thống. Không lưu log query chứa bí mật hay dữ liệu cá nhân vào báo cáo công khai.

**Đặc thù PostgreSQL:** DDL có thể có lock mode mạnh, chẳng hạn ACCESS EXCLUSIVE cho nhiều thao tác ALTER TABLE, nhưng loại lock cụ thể còn phụ thuộc câu lệnh và phiên bản. Không suy luận mọi ALTER TABLE đều có cùng lock mode hoặc thời gian giữ khóa.

## 13. MySQL/InnoDB: metadata lock và transaction

MySQL có cơ chế metadata locking (MDL) giúp giữ cấu trúc đối tượng ổn định trong khi session khác đang dùng. Một transaction đọc/ghi kéo dài trên bảng customer có thể khiến ALTER TABLE chờ metadata lock, kể cả khi query ứng dụng trông đơn giản.

Trên những bản MySQL có Performance Schema phù hợp, truy vấn tham khảo:

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

Quyền quan sát và cấu hình instrumentation phải được bật/phù hợp. Trạng thái PENDING là dấu hiệu cần điều tra nhưng không tự cho biết toàn bộ chuỗi blocking; có thể cần kết hợp thông tin session, transaction và công cụ DBA.

Nhiều thao tác DDL MySQL có tính chất commit khác nhau so với PostgreSQL; **không được giả định DDL rollback an toàn trong transaction**. Các tùy chọn online/in-place/instant DDL cũng phụ thuộc engine, loại ALTER và phiên bản. Một ALTER “online” vẫn có thể cần metadata lock ở các pha nhất định và có thể gây chờ.

Cũng không đồng nhất MariaDB với MySQL cho mọi cú pháp, timeout và cơ chế DDL. Khi cả hai đều nằm trong ma trận sản phẩm, kiểm tra riêng.

## 14. SQL Server và Oracle: khóa cấu trúc vẫn cần quan sát

Trong SQL Server, ngoài lock dữ liệu còn có khóa liên quan schema modification/schema stability. Một DDL có thể cần schema modification lock (Sch-M) và chờ các session đang sử dụng đối tượng. Lock escalation, độ cô lập và online index operation đều ảnh hưởng tình huống thực tế.

Truy vấn giám sát SQL Server tham khảo:

~~~sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status
FROM sys.dm_tran_locks
WHERE resource_database_id = DB_ID();
~~~

Cần quyền giám sát tương ứng và nên kết hợp với các DMV về session/request để biết blocker thực sự.

Với Oracle, các DDL lock và dictionary/object lock có cơ chế riêng; nhiều lệnh DDL có implicit commit và một số dạng thay đổi cần lock độc quyền hoặc chờ lock liên quan. Có thể cần các view giám sát session/locked object với quyền DBA. Không sử dụng kết luận về PostgreSQL hay MySQL làm quy tắc cho Oracle.

**Nguyên tắc chung:** Liquibase trình bày thay đổi theo changelog; **DBMS mới là bên quyết định loại lock, thứ tự chờ, timeout, hỗ trợ transaction và khả năng rollback của SQL cụ thể**.

## 15. Stale Liquibase lock: vì sao xảy ra?

Một job bình thường thường thả DATABASECHANGELOGLOCK khi hoàn thành, kể cả khi có lỗi được xử lý đúng cách. Tuy nhiên, một tiến trình có thể chết đột ngột, bị kill, mất kết nối hoặc bị hệ thống ngắt trước khi cơ chế giải phóng lock hoàn tất.

Khi đó:

- DATABASECHANGELOGLOCK có thể vẫn ghi LOCKED=true.
- Không còn tiến trình Liquibase thực sự tiếp tục migration.
- Những job chạy sau có thể chờ hoặc báo không lấy được lock điều phối.
- Cơ sở dữ liệu có thể đã thực hiện **một phần** migration trước khi job chết.

Lưu ý quan trọng: **LOCKED=true không đủ chứng minh lock bị stale**. Một migration hợp lệ có thể chạy rất lâu, nhất là khi đang tạo index, backfill hoặc chờ transaction từ ứng dụng. Nếu thấy LOCKGRANTED đã lâu, cần kết hợp thông tin tiến trình, log, session DBMS và tình trạng schema.

Bảng LOCKEDBY là một manh mối về nơi lấy lock. Host có thể đã bị thay thế, runner có thể được tái sử dụng, hoặc thông tin đó không cung cấp danh tính job đầy đủ. Không dùng một mình LOCKEDBY để quyết định giải phóng.

## 16. Phân biệt stale Liquibase lock với database lock còn hoạt động

Hai tình huống có bề ngoài gần giống nhau:

### Tình huống A — Liquibase lock còn được job hợp lệ giữ

- Bảng khóa ghi LOCKED=true.
- CI/CD hiển thị migration job vẫn chạy.
- DBMS có session của migration.
- Session có thể đang thực thi hoặc chờ lock từ transaction ứng dụng.

**Không giải phóng lock điều phối.** Cần tìm blocker, thay đổi thời điểm triển khai hoặc phối hợp với chủ sở hữu transaction. Giải phóng bằng tay trong khi job đang chạy có thể cho phép một job Liquibase khác bắt đầu, tạo cạnh tranh migration thật.

### Tình huống B — Không còn job nào giữ lock nhưng bảng ghi LOCKED=true

- Đã đối chiếu tất cả runner, pod và tiến trình Liquibase đang dùng cùng database.
- Không có tiến trình migration còn sống.
- Đã kiểm tra session/transaction DBMS và trạng thái thực thi cuối cùng.
- Có bằng chứng job trước kết thúc bất thường.

Đây là **nghi vấn stale lock**. Sau khi xác nhận không còn owner, nhóm có thể dùng lệnh chính thức của Liquibase để release lock, rồi **điều tra trạng thái schema/dữ liệu trước khi update lại**. Việc thả lock không hoàn tác các thay đổi đã chạy.

Một session DBMS có thể vẫn đang chạy kể cả khi UI CI đánh dấu job “cancelled”, do đường kết nối hoặc hủy lệnh diễn ra không đồng bộ. Vì thế, không chỉ dựa vào trạng thái giao diện pipeline.

## 17. list-locks và release-locks: dùng đúng mục đích

Liquibase cung cấp cơ chế/lệnh kiểm tra và giải phóng khóa điều phối, thường có tên CLI:

~~~text
liquibase list-locks
liquibase release-locks
~~~

Cú pháp và cách đặt tham số kết nối, changelog, schema, tên bảng lock có thể khác theo phiên bản Liquibase hoặc Maven/Gradle plugin. Hãy dùng wrapper/tài liệu đúng phiên bản trong dự án, xác nhận target database trước khi thao tác.

**list-locks** phục vụ quan sát thông tin lock mà Liquibase biết. **release-locks** là thao tác quản trị có thể làm trống trạng thái khóa điều phối; nó **không** giải phóng transaction lock của DBMS theo cách sửa một câu SQL đang chờ, và **không** rollback migration đã thực thi một phần.

Không chạy release-locks chỉ vì:

- Một job chờ lâu hơn dự tính.
- LOCKGRANTED ghi thời điểm cũ.
- Spring Boot khởi động chậm.
- Dashboard báo pod unhealthy nhưng chưa chắc DB session đã kết thúc.

Chỉ dùng sau khi xác nhận không có owner hoạt động và đã có kế hoạch đối chiếu schema, dữ liệu, DATABASECHANGELOG. Hạn chế quyền chạy release-locks ở production, ghi lại người phê duyệt, database đích, bằng chứng và kết quả.

## 18. Runbook xử lý nghi vấn kẹt khóa điều phối

Một runbook an toàn nên theo thứ tự:

1. **Dừng việc nhân thêm runner.** Tạm ngăn pipeline hoặc auto-retry tạo thêm các job cập nhật cùng database.
2. **Xác nhận database/schema.** Kiểm tra endpoint, DBMS, schema lịch sử và tên bảng lock thực sự được cấu hình.
3. **Đọc lock Liquibase.** Kiểm tra LOCKED, LOCKGRANTED, LOCKEDBY hoặc dùng list-locks.
4. **Tra job gốc.** Tìm pipeline run, pod/container, host, artifact và commit đang có thể giữ lock.
5. **Quan sát session DBMS.** Tìm session migration, transaction, query đang chạy, blocker và wait event.
6. **Nếu job vẫn sống:** không dùng release-locks. Điều tra block, thông báo chủ sở hữu, quyết định chờ/hủy theo quy trình an toàn.
7. **Nếu job đã chết:** xác nhận không còn transaction hoặc SQL migration tiếp tục chạy ngầm trên database.
8. **Đối chiếu trạng thái thực.** Đọc DATABASECHANGELOG, schema, index, constraint và dữ liệu các changeset vừa chạy.
9. **Xác định migration dở dang.** Đặc biệt kiểm tra DDL không transaction, runInTransaction=false và backfill có thể đã thực hiện một phần.
10. **Chỉ khi lock stale được xác nhận:** thực thi cơ chế release-locks chính thức với quyền và phê duyệt phù hợp.
11. **Đánh giá trước retry:** nếu có drift, dùng changeset sửa tiếp hoặc runbook khôi phục; không xóa bản ghi lịch sử tùy tiện.
12. **Chạy lại có giám sát:** validate, status, preview SQL, update có kiểm soát, kiểm tra schema và ứng dụng.
13. **Lưu hậu kiểm:** ghi nguyên nhân, thời gian, changeset, DBMS lock, biện pháp khôi phục và thay đổi ngăn tái diễn.

Điểm rủi ro nhất là **thả lock khi migration vẫn đang chạy**. Có thể tạo ra hai chủ thể đồng thời thay đổi schema dù cơ chế Liquibase vốn được dùng để ngăn điều đó.

## 19. Vì sao không nên UPDATE trực tiếp DATABASECHANGELOGLOCK?

Một cách xử lý truyền miệng là sửa thẳng:

~~~sql
-- Không thực thi tùy tiện trên môi trường thật:
UPDATE DATABASECHANGELOGLOCK
SET LOCKED = FALSE;
~~~

Câu lệnh trên **chỉ là ví dụ minh họa thao tác nguy hiểm**, không phải hướng dẫn vận hành. Nó bỏ qua cơ chế và kiểm tra của Liquibase, có thể không phù hợp kiểu boolean/DBMS, và không xác định ai đang giữ lock. Nếu job thực vẫn sống, nó có thể khiến hai tiến trình cùng thao tác migration.

Tương tự, không tự xóa hàng ID=1, drop bảng DATABASECHANGELOGLOCK hay sửa DATABASECHANGELOG để “cho ứng dụng khởi động được”. Những thao tác này phá vỡ khả năng truy vết và có thể làm trạng thái migration khó kiểm chứng hơn.

Giải pháp được ưu tiên là công cụ chính thức, đúng phiên bản và quyền truy cập, **sau bước xác minh owner không còn hoạt động**. Trường hợp đặc biệt cần DBA can thiệp trực tiếp phải có runbook, backup, bằng chứng và phê duyệt; không làm theo mẹo chung.

## 20. Spring Boot nhiều replica và tranh chấp khóa

Trong Spring Boot, nếu có Liquibase Core và auto-configuration phù hợp, ứng dụng có thể chạy migration lúc khởi động:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Giả sử một deployment scale 5 replica và cả 5 cùng bắt đầu:

- Các replica có thể cùng khởi tạo Liquibase và truy cập cùng bảng DATABASECHANGELOGLOCK.
- Một replica lấy quyền chạy migration, những replica khác chờ.
- Migration lâu có thể kéo dài thời gian startup, gây lỗi readiness/liveness hoặc hết hạn chờ theo cấu hình.
- Nếu orchestration tự khởi động lại các pod đang chờ, tải và nhiễu log có thể tăng.
- Lock giúp giảm cạnh tranh chạy changeset, nhưng không bảo đảm **ứng dụng cũ** đang chạy là tương thích với schema mới.

Hai chiến lược vận hành:

**A. Migration lúc ứng dụng khởi động:** phù hợp khi có điều phối chặt, thời lượng migration ngắn và pod lifecycle được thiết kế chịu được thời gian chờ. Cần kiểm soát số lượng replica khởi động đồng thời và readiness.

**B. Migration job riêng trước rollout:** pipeline hoặc một job độc lập dùng Liquibase để update database một lần, sau khi xác minh mới triển khai ứng dụng. Ở runtime cấu hình **spring.liquibase.enabled=false** nếu đây là chủ thể migration duy nhất. Cách này giúp phân tách sự cố migration khỏi sự cố startup.

Không chọn hai chiến lược cùng bật trên production mà không có chủ đích. Cơ chế lock không thay thế quyết định ai được phép migration và khi nào.

## 21. CI/CD: một chủ thể migration cho mỗi đích triển khai

Pipeline phát hành có thể tổ chức:

~~~text
Build + kiểm thử changelog
            |
            v
Xác định artifact/revision bất biến
            |
            v
Migration job duy nhất theo database đích
            |
            v
validate -> status -> review update SQL
            |
            v
Phê duyệt update production
            |
            v
Liquibase update + kiểm tra lock / schema / lịch sử
            |
            v
Triển khai ứng dụng tương thích
            |
            v
Hậu kiểm và theo dõi
~~~

Một vài guard hữu ích:

- **Serialize job theo database đích**, không chỉ theo tên branch Git.
- Không cho hai release pipeline của cùng ứng dụng tự phát chạy migration cùng lúc.
- Ghim Liquibase version, JDBC driver và changelog revision.
- Dùng tài khoản migration có quyền cần thiết, không cấp DDL cho mọi replica runtime.
- Đặt thời gian timeout/alert dựa trên công việc thực tế, không dùng timeout vô hạn.
- Log thời gian chờ Liquibase lock và lock DBMS theo khả năng công cụ.
- Quan sát DEADLOCK, lock timeout và long-running transaction qua hệ thống database.
- Không tự động release-locks mỗi khi job thất bại; điều đó có thể mở đường cho một migration thứ hai khi SQL của job trước chưa kết thúc.

Một retry thông minh cần biết **trạng thái cuối**: changeset đã ghi nhận, còn pending hay đã thực thi một phần. Không chỉ dựa vào exit code của job.

## 22. Giảm khóa đối tượng bằng expand–migrate–contract

Trong một hệ thống luôn có lưu lượng ghi/đọc, không thể chỉ trông chờ vào thời gian nghỉ để chạy ALTER TABLE lớn. Có thể chia kế hoạch thay đổi thành các giai đoạn.

Ví dụ thêm cột customer.status rồi chuyển dần ứng dụng:

**Expand:**

1. Thêm cột mới theo cách tương thích ứng dụng cũ, tránh constraint phá vỡ ngay.
2. Triển khai code đọc được cả trạng thái cũ và mới.
3. Nếu phù hợp, đặt default hoặc logic ứng dụng cho dữ liệu mới.

**Migrate:**

4. Backfill các hàng cũ theo batch có checkpoint và điều kiện rõ ràng.
5. Theo dõi lock, log, replication và tiến độ.
6. Kiểm chứng dữ liệu không còn trạng thái vi phạm.

**Contract:**

7. Chuyển ứng dụng sang sử dụng hoàn toàn schema mới.
8. Chỉ khi không còn writer cũ, thêm NOT NULL hoặc constraint và loại bỏ cấu trúc không dùng.
9. Kiểm tra các thay đổi DDL có khóa mạnh trên bảng lớn và chọn thời điểm/phương pháp phù hợp.

Chiến lược này giảm việc một thay đổi lớn chặn mọi phiên bản ứng dụng cùng lúc. Tuy nhiên không phải tất cả ALTER đều có lựa chọn online; SQL và khả năng khóa phải được kiểm chứng theo DBMS, kích thước bảng và phiên bản cụ thể.

## 23. Data migration lớn: giới hạn tác động lên transaction/lock

Giả sử cần đổi trạng thái hàng triệu bản ghi:

~~~sql
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Một UPDATE toàn tập có thể giữ nhiều khóa, sinh log lớn và cản trở transaction ứng dụng. Trước khi đưa vào changeset:

1. Đo số hàng cần sửa và tốc độ dự kiến trên bản dữ liệu đại diện.
2. Kiểm tra index phục vụ điều kiện WHERE.
3. Xác định lượng log/undo, replication lag và chi phí rollback.
4. Chọn batch theo khóa ổn định khi có thể.
5. Tạo checkpoint hoặc cơ chế biết lô nào đã thành công.
6. Đảm bảo thao tác có thể tiếp tục an toàn sau khi job bị hủy.
7. Theo dõi latency/lock wait của ứng dụng trong lúc thử nghiệm.
8. Quy định ngưỡng tạm dừng hoặc rollback/forward fix.

Liquibase phù hợp quản lý **mốc thay đổi và lịch sử**, nhưng một backfill cực lớn có thể hợp lý hơn khi thực hiện qua job batch/ETL riêng có điều phối, còn changelog chứa schema và invariant liên quan.

**Không coi việc đặt runInTransaction=false và splitStatements=false là kỹ thuật giảm lock phổ quát.** Các tham số đó thay đổi cách thực thi/transaction, không tự biến một UPDATE lớn thành những lô nhỏ an toàn.

## 24. Preconditions, checksum và rollback có liên quan tới lock thế nào?

Khóa không tự xác nhận dữ liệu/schema có đúng. Cần kết hợp các cơ chế khác:

- **Precondition:** kiểm tra điều kiện trước khi chạy, ví dụ bảng/cột tồn tại hoặc dữ liệu đạt yêu cầu. Nếu kiểm tra chạy SQL nặng, chính nó cũng có thể tạo tải hoặc chờ; không nên viết precondition truy vấn toàn bảng tùy tiện.
- **Checksum:** phát hiện thay đổi nội dung changeset đã ghi nhận. Khóa Liquibase không cho phép sửa changeset cũ một cách an toàn; cần giữ lịch sử bất biến.
- **DATABASECHANGELOG:** biết changeset nào đã được ghi nhận; đối chiếu trước khi retry sau crash.
- **Rollback:** có thể phải lấy khóa điều phối và các lock DBMS tương tự update; rollback không nhất thiết nhanh hơn hoặc ít rủi ro hơn migration tiến.
- **runInTransaction:** ảnh hưởng khả năng phục hồi thay đổi trong một changeset, không bảo vệ việc chạy song song ở các job.
- **Context, label và dbms:** quyết định changeset nào được chọn; không thay thế lock điều phối hay concurrency control của DBMS.

Ví dụ một changeset bị **MARK_RAN** theo precondition có thể xuất hiện trong lịch sử dù DDL/DML không chạy. Nếu phát hiện schema thiếu đối tượng sau đó, thả lock hay retry update thường **không** khiến changeset tự thực thi lại. Phải chẩn đoán nguyên nhân dựa trên EXECTYPE và trạng thái thật, sau đó thiết kế changeset sửa có kiểm chứng.

## 25. Những lỗi thường gặp và cách phân biệt

| Triệu chứng | Nguyên nhân có thể | Bước điều tra phù hợp |
|---|---|---|
| Liquibase báo đang chờ lấy lock | Một Liquibase job khác giữ DATABASECHANGELOGLOCK | list-locks, truy vấn bảng lock, đối chiếu runner đang hoạt động |
| LOCKED=true lâu hơn dự kiến | Migration dài hoặc lock stale sau job chết | Kiểm tra job, DB session, current SQL và log trước khi quyết định |
| Update đã lấy lock nhưng rất chậm | DBMS blocking, index build hoặc backfill lớn | Quan sát wait event, blocker, lock metadata/row/table |
| ALTER TABLE chờ dù ứng dụng chỉ SELECT | DDL cần lock schema/metadata không tương thích với session khác | Tìm transaction dài, read query và lock mode theo DBMS |
| Deadlock trong update dữ liệu | Các transaction giữ lock theo thứ tự xung đột | Xem deadlock graph/log, thứ tự truy cập, transaction scope |
| SQL Server báo lock timeout | Statement không lấy được lock trong hạn mức | Tìm blocker, kiểm tra isolation/index và thời gian chạy |
| MySQL ALTER chờ metadata lock | Session đang giữ metadata lock trên bảng | Dùng Performance Schema và thông tin transaction |
| PostgreSQL lock wait kéo dài | Một phiên làm việc giữ lock cần thiết | pg_stat_activity, pg_blocking_pids, pg_locks |
| Hai job vẫn đồng thời sửa cùng bảng | Chúng dùng bảng/schema lock Liquibase khác nhau hoặc một bên không dùng Liquibase | So sánh cấu hình và session DBMS |
| Pod Spring Boot khởi động rồi restart lặp | Migration hoặc lock wait lâu hơn thời gian health check | Kiểm tra logs, probe, kiến trúc migration job |
| release-locks xong nhưng update lại lỗi | Schema đã thực thi một phần hoặc transaction còn ảnh hưởng | Đối chiếu DATABASECHANGELOG với schema/data và log cũ |
| Changelog có EXECUTED nhưng đối tượng thiếu | Drift ngoài Liquibase, thao tác khác đã thay đổi hoặc lịch sử bất nhất | Kiểm tra schema thực, SQL đã chạy, changeset/rollback |
| Rollback không hoàn toàn khôi phục dữ liệu | DDL autocommit hoặc backfill không có snapshot | Phương án forward fix/backup, test rollback trước production |

Đọc chính xác thông báo lỗi là bước đầu, nhưng không đủ. Một số timeout có thể phát sinh từ kết nối, transaction hoặc statement chứ không phải Liquibase lock. Cần phân loại sự cố theo **lớp khóa** trước khi chọn giải pháp.

## 26. Thực hành: ba kịch bản chờ khóa

Thực hành trên database disposable, dùng các tài khoản được phép và không can thiệp session production.

### Kịch bản A — Hai Liquibase process cùng một database

Chuẩn bị một master changelog với một changeset đơn giản và một database mới.

1. Tạo hai tiến trình/test runner dùng **cùng URL, schema và bảng DATABASECHANGELOGLOCK**.
2. Bố trí để runner A chạy một migration đủ lâu cho runner B có thể bắt đầu cùng lúc.
3. Quan sát runner B phải chờ hoặc nhận thông báo liên quan lock theo phiên bản/cấu hình.
4. Sau khi A kết thúc, kiểm tra runner B đối chiếu DATABASECHANGELOG trước khi quyết định còn changeset pending.
5. Xác minh bảng lock được trả về trạng thái không bị giữ khi cả hai kết thúc bình thường.

Không giả định các runner sẽ luôn in cùng một thông báo hay cùng thời gian retry. Mục tiêu là quan sát **không có hai chủ thể Liquibase hợp lệ cùng áp dụng một changeset** trong phạm vi một cơ chế khóa thống nhất.

### Kịch bản B — Liquibase có lock nhưng chờ database transaction

Trên một database thử nghiệm, session A của ứng dụng bắt đầu transaction và thực hiện thao tác giữ lock trên bảng customer. Session B chạy Liquibase với changeset muốn ALTER hoặc UPDATE bảng đó.

1. Quan sát DATABASECHANGELOGLOCK có thể được Liquibase giữ.
2. Quan sát DBMS session B đang chờ lock đối tượng hoặc metadata.
3. Kết thúc transaction của session A bằng một thao tác có chủ đích trên database thử nghiệm.
4. Xem session B tiếp tục và kết quả migration.
5. Đối chiếu DATABASECHANGELOG, schema và dữ liệu sau khi cả hai hoàn thành.

Bài học: **Liquibase lock và database lock có thể cùng tồn tại**, và nguồn chờ thực sự nằm ở DBMS chứ không phải ở cơ chế điều phối.

### Kịch bản C — Mô phỏng lock stale mà không phá database

Không nên cố tình sửa DATABASECHANGELOGLOCK bằng tay trong môi trường chia sẻ. Với môi trường thử nghiệm có thể reset hoàn toàn, hãy nghiên cứu kịch bản một Liquibase job bị dừng bất thường.

1. Lưu kết quả preflight và thông tin changeset.
2. Cho job migration bắt đầu theo kịch bản có kiểm soát.
3. Quan sát trạng thái khi job bị dừng bất thường theo công cụ thử nghiệm.
4. Xác định lock thực sự còn bị giữ hay không; không giả định job nào chết cũng để lại stale lock.
5. Kiểm tra không còn process/session migration và trạng thái thay đổi đã thực hiện.
6. Nếu còn stale lock đã xác nhận, áp dụng quy trình release-locks được duyệt trên database disposable.
7. Chỉ retry sau khi đối chiếu lịch sử, schema và dữ liệu.

Kết quả có thể khác theo DBMS, thời điểm dừng và cơ chế xử lý lỗi. Mục đích là hình thành **thói quen xác minh trước khi giải phóng**, không phải luyện thao tác phá/hủy lock.

## 27. Checklist triển khai và xử lý lock

- [ ] Đã phân biệt Liquibase coordination lock với DBMS row/table/metadata lock.
- [ ] Đã xác định đúng database, schema và DATABASECHANGELOGLOCK được cấu hình.
- [ ] Chỉ có một migration owner/job chính cho database đích trong mỗi lần phát hành.
- [ ] Đã ghim revision changelog, Liquibase version và JDBC driver.
- [ ] Đã thử migration trên DBMS thật, dữ liệu và quy mô đại diện.
- [ ] Đã phân tích khóa/DDL và transaction đối với ALTER TABLE, CREATE INDEX, backfill.
- [ ] Đã cân nhắc online/concurrent DDL theo khả năng DBMS, không suy diễn từ hệ quản trị khác.
- [ ] Đã xác định timeout, thời lượng dự kiến và chỉ số giám sát phù hợp.
- [ ] Có cách phát hiện blocker/long-running transaction trong DBMS.
- [ ] Đã kiểm tra status, SQL dự kiến và phạm vi changeset pending.
- [ ] Thay đổi schema lớn có lộ trình expand–migrate–contract khi cần.
- [ ] Backfill lớn có chiến lược batch, checkpoint và phục hồi.
- [ ] Pipeline không tự chạy release-locks khi nhận timeout hoặc lỗi.
- [ ] Trước khi giải phóng nghi vấn stale lock đã chứng minh không có owner còn hoạt động.
- [ ] Trước retry đã đối chiếu DATABASECHANGELOG với schema/dữ liệu thật.
- [ ] Không sửa trực tiếp DATABASECHANGELOGLOCK hoặc DATABASECHANGELOG để che sự cố.
- [ ] Rollback/forward fix đã được kiểm chứng, có backup khi dữ liệu quan trọng.
- [ ] Spring Boot runtime và migration job có trách nhiệm rõ ràng, không khởi động cạnh tranh không kiểm soát.
- [ ] Có log CI/CD, audit, phê duyệt thao tác trên production và hậu kiểm sau triển khai.

**Ghi nhớ:** **DATABASECHANGELOGLOCK** giúp Liquibase điều phối các tiến trình migration dùng chung lịch sử; nó **không thay thế** khóa hàng, bảng hoặc metadata do DBMS tạo khi thực thi SQL. Một migration có thể giữ Liquibase lock hợp lệ nhưng vẫn chờ transaction ứng dụng. Khi nghi lock bị kẹt, phải xác minh chủ sở hữu, session DBMS, lịch sử và schema thật trước khi giải phóng. Giữ một migration owner rõ ràng, giảm thời gian giữ DBMS lock, chọn chiến lược rollback có kiểm chứng và theo dõi cả hai lớp khóa là nền tảng cho schema migration an toàn qua Spring Boot hoặc CI/CD.

