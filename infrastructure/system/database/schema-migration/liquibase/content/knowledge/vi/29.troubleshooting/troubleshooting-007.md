# Khóa còn tồn tại sau tiến trình bị dừng

Liquibase dùng bảng **DATABASECHANGELOGLOCK** để điều phối các tiến trình migration cùng làm việc trên một database. Khi một tiến trình bị kill, máy chạy job mất kết nối hoặc agent CI bị dừng đột ngột, hàng khóa có thể vẫn ghi nhận trạng thái đang khóa dù tiến trình ban đầu không còn hoạt động. Những lần chạy Liquibase tiếp theo khi đó có thể chờ hoặc báo không lấy được lock.

Xử lý tình huống này cần xác định khóa còn được một tiến trình thật giữ hay chỉ là trạng thái cũ chưa được giải phóng. Giải phóng khóa quá sớm có thể cho phép hai tiến trình update chạy đồng thời và làm schema/history khó kiểm soát. Ngược lại, chờ vô thời hạn một khóa đã mồ côi làm pipeline và hoạt động phát hành bị đình trệ.

Bài học thuộc chương **Xử lý sự cố** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài này hướng dẫn điều tra khóa Liquibase còn tồn tại sau khi tiến trình bị dừng, phân biệt Liquibase lock với lock của DBMS, xác minh process/session, quyết định khi nào được dùng lệnh **release-locks**, kiểm tra partial state sau sự cố và thiết lập phòng ngừa để tránh tái diễn.

Sau bài học, bạn có thể:

1. Giải thích vai trò và phạm vi của DATABASECHANGELOGLOCK.
2. Đọc LOCKED, LOCKGRANTED và LOCKEDBY để xác định thông tin khóa.
3. Phân biệt khóa Liquibase còn tồn tại với transaction hoặc metadata lock của DBMS.
4. Điều tra pipeline, process, host và database session trước khi can thiệp.
5. Giải phóng stale lock bằng lệnh Liquibase phù hợp sau khi xác minh an toàn.
6. Kiểm tra schema, dữ liệu và DATABASECHANGELOG khi tiến trình bị dừng giữa changeset.
7. Khôi phục quy trình update có kiểm soát và phòng ngừa sự cố trong CI/CD.

## 1. DATABASECHANGELOGLOCK hoạt động như thế nào?

Liquibase sử dụng bảng **DATABASECHANGELOGLOCK** để ngăn nhiều tiến trình Liquibase cùng thực thi thay đổi trên cùng một lock table tại một thời điểm. Khi một tiến trình chuẩn bị chạy các lệnh cần điều phối như update, Liquibase lấy khóa; khi hoàn tất bình thường, tiến trình giải phóng khóa.

Bảng mặc định thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| ID | Định danh hàng khóa; cấu hình mặc định thường có một hàng với ID = 1 |
| LOCKED | Trạng thái khóa, true khi lock đang được giữ |
| LOCKGRANTED | Thời điểm khóa được cấp |
| LOCKEDBY | Thông tin máy/host hoặc tiến trình giữ khóa, tùy phiên bản và cách triển khai |

Tên bảng và schema chứa bảng có thể được cấu hình. Nếu dự án đổi tên hoặc đặt metadata trong schema riêng, hãy xác định đúng bảng mà kết nối Liquibase đang dùng.

### 1.1. Lock bảo vệ điều gì?

Lock giúp các tiến trình Liquibase dùng chung metadata lock table tránh chạy migration chồng lấn. Ví dụ hai pipeline cùng gọi update trên một database và cùng dùng DATABASECHANGELOGLOCK, tiến trình thứ hai sẽ không được phép thực thi song song với tiến trình đã lấy lock.

Lock này không:

- Hợp nhất changelog hoặc giải quyết Git conflict.
- Ngăn DBA chạy DDL trực tiếp ngoài Liquibase.
- Ngăn ứng dụng ghi dữ liệu trong lúc migration.
- Thay thế table lock, row lock hay metadata lock của DBMS.
- Bảo đảm một changeset không để lại partial state sau crash.
- Xác minh người chạy có quyền phê duyệt production.
- Bảo đảm hai tiến trình dùng hai lock table khác nhau sẽ phối hợp với nhau.

**Phạm vi bảo vệ phụ thuộc vào việc các tiến trình có thực sự dùng chung lock table hay không.** Nếu hai pipeline trỏ tới cùng database nhưng cấu hình metadata schema khác nhau, chúng có thể dùng hai bảng lock riêng và không điều phối lẫn nhau.

### 1.2. Vì sao lock có thể còn sau khi process đã dừng?

Liquibase thường giải phóng lock trong luồng kết thúc bình thường. Nếu JVM bị kill -9, container bị xóa cưỡng bức, runner mất điện hoặc tiến trình bị dừng trước khi chạy cleanup, hàng lock có thể vẫn mang LOCKED = true.

Database không tự suy luận rằng process trên máy client đã chết chỉ từ hàng metadata đó. Vì vậy, stale lock cần được xác minh và giải phóng có chủ đích.

## 2. Nhận diện triệu chứng

Các dấu hiệu thường gặp:

- Pipeline Liquibase mới chờ lấy lock quá lâu.
- Log báo không lấy được changelog lock.
- Thông báo cho biết lock được giữ bởi host hoặc process không còn hoạt động.
- DATABASECHANGELOGLOCK có LOCKED = true trong thời gian dài.
- Job trước bị cancelled, timeout hoặc runner mất kết nối.
- Lần update trước kết thúc bất thường và không có log giải phóng lock.
- Nhiều môi trường cùng báo lock dù người vận hành nghĩ chỉ có một job.

Thông báo cụ thể thay đổi theo phiên bản Liquibase. Không chỉ dựa vào một dòng log; cần kiểm tra metadata table và trạng thái process/database.

### 2.1. Phân biệt ba trạng thái thường bị nhầm

| Trạng thái | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Liquibase lock còn được giữ | LOCKED = true | Xác minh job/process/session đang sở hữu |
| DBMS session/transaction đang giữ lock | Query bị chặn, DBMS báo lock wait | Điều tra session và transaction trên DBMS |
| Job đã chết nhưng metadata chưa giải phóng | LOCKED = true, không tìm thấy process/session tương ứng | Xác minh toàn bộ runner/host rồi mới release-locks |

Có thể xảy ra nhiều trạng thái cùng lúc. Ví dụ Liquibase lock còn true trong khi một transaction DBMS cũng đang giữ metadata lock. Không nên xử lý một lớp rồi giả định lớp kia đã hết.

## 3. Thu thập thông tin trước khi can thiệp

Trước tiên ghi nhận sự cố và xác định đúng database:

- Tên môi trường: dev, integration, staging hay production.
- Database/catalog và schema nghiệp vụ.
- Schema/catalog chứa DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- Liquibase version và JDBC driver.
- Root changelog và các tham số context/labels.
- Pipeline run ID, job ID và thời điểm bắt đầu.
- Host/runner/container đã chạy Liquibase.
- Lệnh cuối cùng và log cuối cùng trước khi process dừng.
- Changeset đang thực thi nếu log xác định được.
- Thời điểm bắt đầu lock và giá trị LOCKEDBY.

Không đưa password, token hoặc connection string chứa secret vào incident log.

### 3.1. Xác định cấu hình metadata

Kiểm tra cấu hình được dùng bởi job đã thất bại:

- URL database.
- liquibaseSchemaName hoặc cấu hình schema metadata tương ứng.
- liquibaseCatalogName nếu DBMS hỗ trợ catalog.
- Tên bảng lock nếu dự án tùy chỉnh.
- Datasource riêng cho Liquibase trong Spring Boot.
- Profile, environment và context/labels.
- Root changelog và defaults file.

Nếu job mới dùng metadata schema khác job cũ, việc xem nhầm bảng lock có thể dẫn đến kết luận sai. Luôn truy vấn đúng metadata database mà tiến trình thực tế đã sử dụng.

## 4. Đọc trạng thái DATABASECHANGELOGLOCK

Có thể dùng truy vấn chỉ đọc để xem hàng khóa:

~~~sql
SELECT
    ID,
    LOCKED,
    LOCKGRANTED,
    LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

Nếu metadata nằm trong schema riêng, chỉ rõ schema theo cú pháp DBMS, ví dụ:

~~~sql
SELECT
    ID,
    LOCKED,
    LOCKGRANTED,
    LOCKEDBY
FROM liquibase_meta.DATABASECHANGELOGLOCK;
~~~

Ví dụ thứ hai minh họa cách chỉ định schema, tên thực tế phụ thuộc cấu hình. Với identifier được quote hoặc tên bảng viết hoa/thường đặc biệt, sử dụng cú pháp đúng DBMS.

### 4.1. Diễn giải kết quả

| LOCKED | LOCKGRANTED | LOCKEDBY | Cách hiểu ban đầu |
|---|---|---|---|
| false | NULL hoặc rỗng | NULL hoặc rỗng | Không có Liquibase lock đang được ghi nhận |
| true | Có thời điểm gần đây | Host/job nhận diện được | Có thể tiến trình vẫn hoạt động |
| true | Thời điểm cũ | Host không còn tồn tại | Có thể là stale lock, cần điều tra thêm |
| true | Thời điểm cũ | Host còn tồn tại | Có thể job bị treo hoặc session còn sống |
| Giá trị bất thường | Thiếu/không nhất quán | Không rõ | Kiểm tra metadata, schema và lịch sử thao tác |

Không dùng riêng tuổi của LOCKGRANTED làm tiêu chí giải phóng. Một migration lớn có thể chạy hàng giờ; một tiến trình vẫn hoạt động không trở thành stale chỉ vì vượt một ngưỡng thời gian tùy ý.

### 4.2. LOCKEDBY không phải bằng chứng đầy đủ

LOCKEDBY có thể chỉ cho biết hostname/IP hoặc thông tin môi trường, không nhất thiết là PID có thể tra cứu trực tiếp. Container có thể đã bị thay thế, hostname có thể tái sử dụng và runner có thể đã mất log.

Đối chiếu LOCKEDBY với CI job, container runtime, host inventory và database session. Không kết thúc process chỉ dựa vào một chuỗi hostname cũ.

## 5. Kiểm tra pipeline và process sở hữu lock

Tìm job đã gọi Liquibase:

1. Tra pipeline run theo thời điểm LOCKGRANTED.
2. Xác định job đang running, cancelled, failed hay timed out.
3. Kiểm tra job có bước cleanup/finally hay không.
4. Xác định runner hoặc container đã chạy lệnh.
5. Kiểm tra có job retry hoặc deployment khác đang dùng cùng database.
6. Xem log cuối cùng để biết process dừng trước, trong hay sau changeset.
7. Nếu runner bị mất, kiểm tra trạng thái host/container qua hệ thống vận hành.

Một pipeline hiển thị Failed không nhất thiết chứng minh process con đã kết thúc. Có trường hợp job điều khiển đã timeout nhưng process Liquibase vẫn chạy ở runner hoặc container nền.

### 5.1. Kiểm tra process tại host

Nếu có quyền quản trị host/runner, xác minh process Java/Liquibase và command line liên quan. Dùng định danh process cùng thời gian khởi chạy, working directory và job ID để tránh nhầm process khác.

Trên container orchestration, kiểm tra pod/container có còn tồn tại, trạng thái termination và log. Không xóa pod hoặc kill process đang chạy chỉ để giải phóng lock nếu chưa xác minh tác động migration.

### 5.2. Khi process không còn nhưng database session còn

Mất kết nối client không luôn đồng nghĩa DBMS đã kết thúc session ngay. Network partition, TCP timeout hoặc connection pool có thể khiến session/transaction còn tồn tại trong database.

Cần kiểm tra session DBMS trước khi release lock. Nếu session còn chạy, xử lý qua quy trình DBMS/DBA được phê duyệt; không giả định lệnh release-locks sẽ kết thúc transaction đó.

## 6. Phân biệt Liquibase lock với lock của DBMS

Đây là bước quan trọng nhất trước khi can thiệp.

**DATABASECHANGELOGLOCK** là metadata lock do Liquibase quản lý. DBMS còn có các loại lock riêng:

- Row lock và table lock.
- Metadata lock.
- DDL lock.
- Transaction lock.
- Advisory lock hoặc application lock tùy DBMS.

Ví dụ pipeline mới có thể không lấy được Liquibase lock vì LOCKED = true. Trong trường hợp khác, Liquibase lock đã false nhưng một transaction DDL cũ vẫn khiến ALTER TABLE bị chặn. Hai lỗi có biểu hiện khác nhau và cách xử lý khác nhau.

### 6.1. PostgreSQL: kiểm tra session và hoạt động chờ

Ví dụ truy vấn đọc thông tin session:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start;
~~~

Kiểm tra lock và quan hệ chờ có thể dùng pg_locks cùng pg_stat_activity. Truy vấn cần điều chỉnh theo quyền quan sát và phiên bản PostgreSQL.

Không hiển thị hoặc chia sẻ query có chứa dữ liệu nhạy cảm trong incident report.

### 6.2. MySQL/MariaDB

Có thể kiểm tra process/session bằng SHOW PROCESSLIST hoặc các view trong performance_schema. Tập view và quyền quan sát phụ thuộc phiên bản và cấu hình.

Cần chú ý metadata lock, transaction đang mở và DDL implicit commit. Việc Liquibase lock được giải phóng không tự giải phóng một session database vẫn tồn tại.

### 6.3. SQL Server

Có thể xem session, request và lock qua các dynamic management views như sys.dm_exec_sessions, sys.dm_exec_requests và sys.dm_tran_locks. Cần quyền quan sát phù hợp và lọc đúng database/session.

### 6.4. Oracle

Có thể điều tra session, transaction và lock qua các view quản trị như V$SESSION, V$TRANSACTION và V$LOCK, tùy quyền được cấp và phiên bản.

Các truy vấn ở trên chỉ là điểm bắt đầu. Dùng tài liệu DBMS đúng phiên bản và phối hợp DBA khi cần quyền quản trị.

## 7. Xác minh có tiến trình Liquibase khác đang chạy không

Trước khi release lock, cần chứng minh không còn tiến trình migration hợp lệ đang sử dụng cùng lock table.

Kiểm tra:

- Pipeline đang chạy ở mọi project/repository liên quan.
- Scheduled job hoặc deployment tự động.
- Job retry sau timeout.
- Developer chạy Liquibase từ máy cá nhân.
- Spring Boot instance tự chạy Liquibase lúc startup.
- Một service khác dùng chung database/metadata.
- Process thủ công trong container hoặc host quản trị.
- Tiến trình chạy với datasource/config khác nhưng trỏ tới cùng lock table.

Không chỉ kiểm tra pipeline của một repository. Hai ứng dụng có thể cùng dùng một database và một metadata table.

### 7.1. Spring Boot có thể là nguồn tiến trình thứ hai

Nếu nhiều instance Spring Boot cùng bật Liquibase auto-configuration, mỗi instance có thể khởi tạo Liquibase khi startup. Lock table giúp điều phối nếu chúng dùng cùng metadata table, nhưng startup và timeout có thể khiến log khó nhận diện.

Xác minh:

- spring.liquibase.enabled.
- Datasource mà Liquibase sử dụng.
- Các instance/pod đang restart.
- Deployment rollout và autoscaling.
- Liquibase schema/table metadata.
- Job migration độc lập nếu dự án có sử dụng.

Nếu tổ chức đã chuyển sang migration job riêng, bảo đảm các ứng dụng không còn tự chạy migration ngoài ý muốn.

## 8. Ma trận quyết định trước khi giải phóng khóa

Không dùng một thao tác giống nhau cho mọi tình huống.

| Bằng chứng | Quyết định |
|---|---|
| Job/process Liquibase vẫn hoạt động | Không release; theo dõi và xử lý tiến trình theo quy trình vận hành |
| Job đã timeout nhưng process con còn sống | Xác minh process; dừng có kiểm soát nếu được phê duyệt, rồi kiểm tra DB session |
| Process không còn, DB session vẫn hoạt động | Điều tra session/transaction trước; xử lý DBMS theo quy trình DBA |
| Không còn job, process hoặc session tương ứng; LOCKED vẫn true | Stale lock có khả năng cao; có thể dùng release-locks sau khi xác minh target |
| LOCKED = false nhưng migration vẫn chờ | Điều tra DBMS lock, connection, network hoặc nguyên nhân khác |
| Có partial DDL/data sau crash | Reconcile schema/data trước khi chạy lại |
| Không xác định được owner hoặc target metadata | Dừng can thiệp, thu thập thêm bằng chứng |

**Điều kiện cần trước release:** tất cả tiến trình Liquibase có thể dùng cùng lock table đã kết thúc hoặc đã được xác minh dừng; không còn session/transaction cần bảo toàn; đúng database và metadata schema đã được xác nhận; trạng thái changeset sau sự cố đã được điều tra đủ để lập kế hoạch tiếp theo.

## 9. Dùng lệnh release-locks

Liquibase cung cấp lệnh **release-locks** để giải phóng changelog lock còn tồn tại. Tên lệnh và cách gọi có thể khác ở phiên bản cũ; hãy kiểm tra help/tài liệu của đúng Liquibase version đang cài.

Ví dụ minh họa:

~~~bash
liquibase \
  --defaults-file=liquibase.properties \
  release-locks
~~~

Hoặc truyền cấu hình kết nối theo cơ chế bảo mật của môi trường:

~~~bash
liquibase \
  --url=JDBC_URL \
  --username=MIGRATION_USER \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  release-locks
~~~

Các chuỗi viết hoa là placeholder, không phải giá trị kết nối. Không đặt password thật trong command line, shell history hoặc log. Dùng secret manager/protected variables và cấu hình an toàn của pipeline.

### 9.1. Vì sao phải dùng đúng cấu hình metadata?

Lệnh release-locks cần trỏ tới đúng database và lock table đang bị khóa. Nếu chạy với URL hoặc liquibaseSchemaName khác, nó có thể không giải phóng hàng khóa mà job cũ đã tạo.

Trước khi chạy, đối chiếu:

- JDBC URL và database/catalog.
- liquibaseSchemaName/catalogName.
- Tên metadata table nếu được tùy chỉnh.
- Credential và profile.
- Môi trường đích.
- Liquibase version.

Không dựa vào tên file properties giống nhau để kết luận cấu hình giống nhau; nội dung và biến môi trường có thể khác.

### 9.2. Lệnh release-locks làm gì và không làm gì?

Lệnh này giải phóng trạng thái Liquibase lock trong metadata table theo cơ chế của Liquibase.

Nó không:

- Rollback changeset đang chạy.
- Hoàn tác DDL đã commit.
- Khôi phục dữ liệu bị xóa hoặc chuyển đổi.
- Sửa DATABASECHANGELOG checksum.
- Chấm dứt mọi session DBMS.
- Chứng minh database đã ở trạng thái nhất quán.
- Xác nhận người vận hành có production approval.

Do đó, giải phóng khóa chỉ là một bước trong quy trình phục hồi, không phải hoàn tất phục hồi.

## 10. Không cập nhật DATABASECHANGELOGLOCK thủ công một cách tùy tiện

Có thể tìm thấy hướng dẫn SQL dạng:

~~~sql
UPDATE DATABASECHANGELOGLOCK
SET LOCKED = FALSE,
    LOCKGRANTED = NULL,
    LOCKEDBY = NULL
WHERE ID = 1;
~~~

Đây là ví dụ minh họa cấu trúc metadata, **không phải lệnh mặc định để chạy trong production**.

Sửa trực tiếp có rủi ro:

- Ghi đè lock của một tiến trình vẫn đang hoạt động.
- Không sử dụng đầy đủ cơ chế/kiểm tra của Liquibase.
- Cập nhật nhầm metadata schema hoặc database.
- Tạo race condition với tiến trình đang chờ.
- Làm mất thông tin phục vụ điều tra.
- Không giải quyết transaction/session đang tồn tại ở DBMS.

Ưu tiên lệnh release-locks đúng phiên bản và đúng cấu hình. Nếu vì sự cố đặc biệt phải thao tác metadata trực tiếp, cần quy trình DBA được phê duyệt, xác minh không còn tiến trình, ghi lại giá trị trước/sau và kiểm tra lại schema/history. Không dùng SQL này như thao tác tự động khi pipeline timeout.

## 11. Kiểm tra trạng thái ngay sau khi release

Sau khi lệnh release-locks hoàn tất, truy vấn lại metadata:

~~~sql
SELECT
    ID,
    LOCKED,
    LOCKGRANTED,
    LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

Kỳ vọng thông thường:

- LOCKED = false.
- LOCKGRANTED được xóa hoặc không còn giá trị.
- LOCKEDBY được xóa hoặc không còn giá trị.

Nếu vẫn true, không chạy update lặp lại ngay. Kiểm tra:

- Có tiến trình khác vừa lấy lock.
- Lệnh release-locks dùng nhầm cấu hình.
- Metadata table khác với bảng đang quan sát.
- Lệnh thất bại hoặc credential không đủ quyền.
- Có một job mới tự động retry.

### 11.1. Kiểm tra list-locks nếu phiên bản hỗ trợ

Một số phiên bản Liquibase cung cấp lệnh list-locks để xem thông tin lock. Hãy xác nhận lệnh trong help của phiên bản đang dùng. Truy vấn trực tiếp bảng metadata vẫn hữu ích để đối chiếu.

## 12. Điều tra changeset bị gián đoạn trước khi retry

Đây là phần thường bị bỏ qua. Khi process chết, cần biết nó dừng ở đâu:

- Trước khi lấy lock.
- Sau khi lấy lock nhưng trước changeset đầu tiên.
- Trong khi thực thi SQL/DDL.
- Sau khi DDL hoàn tất nhưng trước khi ghi history.
- Sau khi ghi history nhưng trước khi giải phóng lock.
- Sau khi hoàn tất migration nhưng client mất kết nối trước khi nhận kết quả.

Các tình huống có trạng thái database khác nhau.

### 12.1. Kiểm tra log của Liquibase

Tìm:

- Changeset ID, author và filename cuối cùng.
- SQL/command cuối cùng được ghi log.
- Thời điểm bắt đầu/kết thúc changeset.
- Lỗi JDBC/DBMS.
- Transaction rollback hoặc commit.
- Thông báo ghi DATABASECHANGELOG.
- Thông báo giải phóng lock.

Log có thể không đủ nếu process bị kill cứng. Khi thiếu bằng chứng, phải kiểm tra catalog và dữ liệu thật.

### 12.2. Kiểm tra DATABASECHANGELOG

Ví dụ truy vấn:

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
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Đối chiếu changeset cuối cùng với log. Không có hàng history cho một changeset không chứng minh changeset chưa tạo ra tác động trên database; DDL có thể đã commit trước khi Liquibase ghi history tùy DBMS và transaction behavior.

## 13. Partial state và implicit commit

Một changeset có thể thực hiện nhiều câu lệnh. Nếu tiến trình bị dừng giữa chừng, kết quả phụ thuộc DBMS, loại DDL và cấu hình transaction.

- Một số DBMS hỗ trợ transaction cho nhiều DDL.
- Một số DDL có implicit commit.
- Một số thao tác không được chạy trong transaction block.
- runInTransaction=false làm thay đổi ranh giới transaction.
- SQL tùy chỉnh có thể gọi procedure hoặc thao tác ngoài transaction.

Ví dụ một changeset:

~~~yaml
- changeSet:
    id: "ORD-901-expand-order-schema"
    author: "orders-team"
    changes:
      - createTable:
          schemaName: app
          tableName: order_archive
          columns:
            - column:
                name: id
                type: bigint
      - createIndex:
          schemaName: app
          tableName: order_archive
          indexName: idx_order_archive_id
          columns:
            - column:
                name: id
~~~

Nếu tiến trình dừng sau khi bảng được tạo nhưng trước khi index hoàn tất, lần chạy lại có thể gặp table already exists. Không giải quyết bằng cách đánh dấu changeset đã chạy nếu index vẫn thiếu.

### 13.1. Kiểm tra schema thực tế

Dùng catalog DBMS để xác minh từng object trong changeset:

- Bảng/cột có tồn tại không?
- Kiểu dữ liệu và nullability có đúng không?
- Index có tồn tại và ở trạng thái hợp lệ không?
- Constraint đã được tạo/validate chưa?
- View/function có đúng định nghĩa không?
- Dữ liệu đã được backfill đến đâu?

Không chỉ kiểm tra object name. Một object có thể tồn tại nhưng cấu hình chưa đúng.

### 13.2. Kiểm tra dữ liệu

Với changeset DML, xác minh:

- Số hàng đã cập nhật.
- Phạm vi khóa bị tác động.
- Giá trị trước/sau nếu có snapshot.
- Có hàng bị cập nhật một phần không.
- Có job hoặc ứng dụng khác tiếp tục ghi trong lúc sự cố không.
- Có thể tiếp tục bằng điều kiện idempotent hay cần reconciliation.

## 14. Chọn phương án phục hồi sau khi release lock

Sau khi xác minh lock đã được giải phóng, không mặc định chạy update ngay. Chọn phương án dựa trên trạng thái database:

| Trạng thái sau sự cố | Phương án |
|---|---|
| Chưa có thay đổi nào của changeset | Có thể chạy lại sau khi xác minh target/history |
| Changeset hoàn tất và history đã ghi | Kiểm tra các changeset còn pending rồi tiếp tục |
| DDL partial, history chưa ghi | Reconcile object theo DBMS; sửa/khôi phục trạng thái rồi mới retry |
| DML partial, history chưa ghi | Đối chiếu dữ liệu, thiết kế tiếp tục hoặc phục hồi dữ liệu |
| Changeset không thể đảo ngược an toàn | Lập forward fix hoặc restore theo kế hoạch |
| History và schema không khớp | Dừng update, lập kế hoạch reconciliation có review |
| Không xác định được trạng thái | Giữ nguyên database, thu thập thêm bằng chứng và escalate DBA |

### 14.1. Khi có thể retry

Chỉ retry khi:

- Không còn process/session cũ.
- Lock đã được giải phóng.
- Target database và metadata schema đúng.
- Schema/data ở trạng thái phù hợp với changeset.
- DATABASECHANGELOG không mâu thuẫn.
- Kế hoạch xử lý partial state đã được xác nhận.
- Không có pipeline khác chuẩn bị update đồng thời.

Sau đó có thể chạy status, validate và update-sql theo quy trình trước khi update thật.

### 14.2. Khi nên tạo forward fix

Nếu changeset đã tạo ra một phần trạng thái và việc đảo ngược không an toàn, có thể cần một changeset mới để đưa database từ trạng thái thực tế sang trạng thái mong muốn. Forward fix phải mô tả trạng thái đầu vào, precondition và kết quả; không sửa changeset đã phát hành để che lịch sử.

## 15. Vì sao không nên dùng MARK_RAN để bỏ qua partial state?

MARK_RAN có thể đánh dấu changeset như đã xử lý mà không thực thi changes. Nó không tự xác nhận tất cả object hoặc dữ liệu của changeset đã tồn tại đúng.

Ví dụ changeset cần tạo bảng và index. Sau crash chỉ có bảng tồn tại. Nếu precondition đánh giá điều kiện quá rộng và chọn MARK_RAN, Liquibase có thể ghi nhận changeset dù index còn thiếu.

Chỉ dùng MARK_RAN khi trạng thái database đã được chứng minh tương đương kết quả changeset và hành vi đó được review. Nếu còn object thiếu hoặc sai thuộc tính, cần reconciliation hoặc forward fix.

## 16. Không clear-checksums để xử lý stale lock

Lệnh clear-checksums phục vụ quản lý checksum, không giải phóng DATABASECHANGELOGLOCK và không sửa partial DDL.

Nếu gặp đồng thời stale lock và checksum mismatch:

1. Xử lý lock theo quy trình riêng.
2. Điều tra checksum và changeset identity.
3. So sánh artifact đã phát hành.
4. Kiểm tra schema/data.
5. Tạo changeset mới nếu cần.
6. Chỉ dùng thao tác checksum đặc biệt khi có quyết định được phê duyệt.

Không chạy một chuỗi lệnh “release-locks, clear-checksums, update” theo thói quen. Mỗi bước có tác động khác nhau và cần bằng chứng riêng.

## 17. Runbook xử lý stale lock từng bước

Có thể áp dụng trình tự sau cho incident:

### Bước 1 — Dừng tạo thêm migration job

Tạm ngăn pipeline retry hoặc deployment khác tự động chạy vào cùng database. Ghi nhận các job đang chờ.

### Bước 2 — Xác định đúng database và metadata table

Đối chiếu JDBC URL, catalog/database, Liquibase schema và tên lock table. Không thao tác khi chưa chắc target.

### Bước 3 — Đọc trạng thái lock

Truy vấn LOCKED, LOCKGRANTED và LOCKEDBY. Lưu kết quả cùng thời điểm truy vấn.

### Bước 4 — Tìm process/job sở hữu

Tra pipeline run, runner, container, host và log. Xác định process còn hoạt động hay không.

### Bước 5 — Kiểm tra DBMS session/transaction

Xem session, request, transaction và lock của DBMS. Phân biệt session của Liquibase với session khác.

### Bước 6 — Xác nhận không còn migration đang chạy

Phải có bằng chứng rằng process/job cũ đã kết thúc và không còn session/transaction cần bảo toàn. Nếu không xác minh được, dừng và chuyển DBA/on-call.

### Bước 7 — Đánh giá partial state

Đối chiếu log, DATABASECHANGELOG, catalog và dữ liệu để biết changeset cuối đã tác động tới đâu.

### Bước 8 — Release lock

Dùng release-locks với đúng kết nối và metadata configuration của database bị khóa. Ghi lại người thực hiện, thời điểm và kết quả.

### Bước 9 — Xác minh lock đã mở

Truy vấn lại lock table hoặc dùng list-locks nếu phiên bản hỗ trợ. Xác nhận LOCKED = false.

### Bước 10 — Reconcile rồi mới update

Nếu schema/history/data không khớp, xử lý theo kế hoạch được review. Nếu trạng thái nhất quán và retry an toàn, chạy status, validate, update-sql rồi update.

### Bước 11 — Kiểm tra sau phục hồi

Xác minh changeset history, schema, dữ liệu, ứng dụng và không còn process/lock bất thường. Lưu incident record.

~~~mermaid
flowchart TD
    A[Liquibase lock còn tồn tại] --> B[Dừng retry/deployment mới]
    B --> C[Xác nhận database và metadata table]
    C --> D[Kiểm tra job/process/host]
    D --> E[Kiểm tra DBMS session và transaction]
    E --> F{Còn tiến trình hoặc session hoạt động?}
    F -->|Có| G[Không release; xử lý tiến trình/session]
    G --> D
    F -->|Không| H[Kiểm tra history và partial schema/data]
    H --> I[Release lock bằng Liquibase]
    I --> J{LOCKED đã false?}
    J -->|Không| K[Kiểm tra cấu hình, quyền và lock mới]
    J -->|Có| L{Schema/history nhất quán?}
    L -->|Không| M[Reconciliation hoặc forward fix]
    L -->|Có| N[Validate, status, update-sql]
    M --> N
    N --> O[Retry update có kiểm soát]
    O --> P[Verify và lưu audit]
~~~

## 18. Ví dụ tình huống: runner CI bị kill

**Bối cảnh:** pipeline staging chạy Liquibase update. Runner bị kill do timeout hạ tầng. Pipeline mới báo không lấy được lock.

Thông tin quan sát:

~~~text
LOCKED       = true
LOCKGRANTED  = 2026-11-19 14:20:00
LOCKEDBY     = ci-runner-42
Previous job = cancelled
Current job  = waiting for changelog lock
~~~

Các bước điều tra:

1. Tra runner ci-runner-42 và job run tương ứng.
2. Xác nhận container/process Liquibase đã dừng.
3. Kiểm tra có job retry hoặc Spring Boot instance đang chạy migration không.
4. Kiểm tra session DBMS từ runner cũ.
5. Xem log changeset cuối cùng.
6. Truy vấn DATABASECHANGELOG.
7. Kiểm tra schema object mà changeset cuối tạo hoặc sửa.
8. Nếu không còn process/session và trạng thái metadata xác nhận stale lock, dùng release-locks.
9. Kiểm tra LOCKED = false.
10. Nếu changeset cuối để lại partial state, reconcile trước khi retry.

Không chỉ thấy job Cancelled rồi chạy release-locks ngay. Process con hoặc DBMS session có thể vẫn tồn tại.

## 19. Ví dụ tình huống: lock đã mở nhưng update vẫn bị treo

**Bối cảnh:** DBA xác nhận LOCKED = false. Liquibase update vẫn chờ khi ALTER TABLE.

Khả năng:

- Transaction của ứng dụng đang giữ lock bảng.
- Một DDL khác đang chạy.
- Metadata lock của DBMS đang chặn.
- Session cũ còn tồn tại dù Liquibase lock đã được giải phóng.
- Kết nối tới database khác với database đã kiểm tra.

Cách điều tra:

1. Xác nhận JDBC URL và database identity của job.
2. Kiểm tra session đang chờ trong DBMS.
3. Xác định blocker và blocked session.
4. Kiểm tra transaction age và query.
5. Phối hợp owner của session trước khi terminate.
6. Đánh giá tác động tới ứng dụng và dữ liệu.
7. Sau khi blocker được xử lý, chạy lại theo quy trình.

Không dùng release-locks lần nữa nếu LOCKED đã false. Lệnh đó không giải phóng DBMS table/row/metadata lock.

## 20. Ví dụ tình huống: nhiều lock table cho cùng database

Một dự án có hai ứng dụng cùng sửa schema app. Ứng dụng A lưu DATABASECHANGELOGLOCK trong schema liquibase_a, ứng dụng B lưu lock table trong liquibase_b. Cả hai cùng chạy update trên schema app.

Vì chúng không dùng chung lock table, cơ chế Liquibase lock có thể không tuần tự hóa hai tiến trình. Kết quả có thể là DDL cạnh tranh hoặc changeset chạy trên trạng thái không dự đoán được.

Cách xử lý dài hạn:

- Xác định ownership migration của database/schema.
- Thống nhất metadata schema/table hoặc cơ chế điều phối chung.
- Nếu tách metadata là chủ ý, phải có deployment mutex bên ngoài bảo vệ cùng target.
- Không cho hai pipeline tự do chạy DDL đồng thời.
- Ghi rõ service nào là migration owner.

Một lock table không tự bảo vệ database trước mọi tiến trình Liquibase; nó chỉ điều phối những tiến trình cùng sử dụng nó.

## 21. Những điều không nên làm khi gặp stale lock

- Không release lock chỉ vì LOCKGRANTED đã cũ.
- Không release khi job/process/session vẫn có thể chạy.
- Không kill process hoặc terminate DB session mà chưa hiểu transaction.
- Không cập nhật LOCKED bằng SQL thủ công theo thói quen.
- Không xóa DATABASECHANGELOGLOCK hoặc DATABASECHANGELOG.
- Không chạy clear-checksums để xử lý lock.
- Không dùng MARK_RAN để che partial changeset.
- Không retry update khi chưa kiểm tra schema và history.
- Không chạy đồng thời nhiều job để “thử xem job nào vào được”.
- Không giả định lock false nghĩa là DBMS không còn lock.
- Không ghi credential hoặc dữ liệu nhạy cảm vào incident log.

## 22. Phòng ngừa khóa bị bỏ lại

### 22.1. Thiết kế pipeline có single-flight

Với một database target, chỉ nên có một migration job được phép chạy tại một thời điểm. Có thể dùng:

- Environment concurrency group.
- Deployment mutex.
- Queue theo database.
- Một migration job riêng thay vì mọi application instance tự update.
- Quy tắc không cho retry song song.

Cơ chế bên ngoài hữu ích khi nhiều service dùng các lock table khác nhau nhưng cùng thay đổi một database.

### 22.2. Quản lý timeout và cancellation

Cần phân biệt:

- Pipeline timeout.
- Liquibase lock wait timeout.
- JDBC socket/network timeout.
- DBMS statement timeout.
- Transaction timeout.
- Runner/container termination.

Các timeout nên được phối hợp để pipeline không báo thất bại trong khi process Liquibase vẫn chạy nền. Khi hủy job, bước cleanup cần có cơ hội chạy; nhưng không nên dựa hoàn toàn vào cleanup vì process có thể bị kill cưỡng bức.

### 22.3. Ghi nhận thông tin process

Log deployment nên ghi:

- Pipeline run ID.
- Job ID.
- Host/runner/container ID.
- Database/environment đã chuẩn hóa định danh.
- Liquibase version.
- Root changelog.
- Thời điểm bắt đầu/kết thúc.
- Changeset đang chạy nếu có.
- Kết quả update và cleanup.

Thông tin này giúp đối chiếu LOCKEDBY và LOCKGRANTED khi sự cố xảy ra.

### 22.4. Theo dõi lock lâu bất thường

Có thể giám sát LOCKED = true vượt thời gian vận hành dự kiến và phát cảnh báo. Ngưỡng phải dựa trên thời gian migration thực tế của hệ thống, không dùng một con số chung cho mọi database.

Cảnh báo chỉ nên tạo incident và kích hoạt điều tra. Không tự động release lock theo TTL khi chưa xác minh process/session; migration dài vẫn có thể đang chạy hợp lệ.

## 23. Tích hợp Spring Boot an toàn

Nếu Spring Boot bật Liquibase auto-configuration:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Cần xác định:

- Instance nào được phép chạy migration.
- Có bao nhiêu instance khởi động đồng thời.
- Datasource Liquibase có dùng chung metadata table không.
- Startup timeout và shutdown grace period.
- Pod bị evict/restart xử lý thế nào.
- Có migration job riêng hay migration khi ứng dụng startup.
- Log có nhận diện được instance và deployment ID không.

Với hệ thống rolling deployment, một job migration riêng thường giúp tách trách nhiệm schema khỏi số lượng application instance. Nếu vẫn chạy lúc startup, phải kiểm tra các instance dùng cùng metadata lock và có chính sách timeout phù hợp.

## 24. Kiểm tra sau khi phục hồi

Sau khi release lock và update được tiếp tục, xác minh nhiều lớp:

### 24.1. Liquibase metadata

- DATABASECHANGELOG có changeset dự kiến.
- ID, AUTHOR, FILENAME/logicalFilePath đúng.
- EXECTYPE phù hợp.
- Checksum không có mismatch chưa giải quyết.
- Không có changeset ngoài filter bị chạy.

### 24.2. Schema thực tế

- Bảng/cột/index/constraint đạt trạng thái mong muốn.
- Object không bị tạo trùng.
- Index ở trạng thái hợp lệ theo DBMS.
- View/function có định nghĩa đúng.
- Default, nullability và datatype chính xác.

### 24.3. Dữ liệu và ứng dụng

- Backfill đủ phạm vi.
- Không mất hoặc nhân đôi dữ liệu ngoài dự kiến.
- Invariant nghiệp vụ đạt.
- Ứng dụng đọc/ghi được.
- Không còn query bị chặn hoặc replication lag bất thường.
- Pipeline kết thúc và lock được giải phóng bình thường.

### 24.4. Audit

Lưu:

- Incident ID.
- Job cũ và job retry.
- Bằng chứng process/session đã dừng.
- Giá trị lock trước và sau.
- Người chạy release-locks.
- Thời điểm và cấu hình target.
- Kết quả reconciliation.
- Changeset và artifact cuối cùng.
- Kết quả xác minh sau update.

Không lưu secret trong bằng chứng.

## 25. Bảng lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| LOCKED = true sau khi runner bị kill | Cleanup không chạy | Xác minh process/session rồi release-locks |
| LOCKEDBY trỏ host không còn | Runner/container đã bị hủy | Tra pipeline và host inventory, không dựa riêng hostname |
| Job mới chờ lock dù job cũ failed | Process con vẫn sống hoặc stale lock | Kiểm tra process và DB session |
| Release-locks chạy nhưng lock vẫn true | Sai URL/schema/table hoặc có tiến trình lấy lock lại | Đối chiếu cấu hình và truy vấn lại |
| LOCKED = false nhưng DDL bị chặn | DBMS lock/transaction khác | Điều tra session/blocker DBMS |
| Retry báo table already exists | DDL partial commit | Kiểm tra catalog và reconcile |
| History không có changeset nhưng object tồn tại | DDL đã commit trước history hoặc thay đổi thủ công | Điều tra artifact/log/schema, không MARK_RAN mù |
| Changeset đã ghi history nhưng pipeline báo timeout | Client mất kết nối sau khi DB hoàn tất | Kiểm tra history/schema trước retry |
| Nhiều job cùng lấy lock khác nhau | Metadata lock table bị tách | Chuẩn hóa lock table hoặc dùng mutex ngoài |
| Spring Boot restart liên tục chờ lock | Nhiều instance hoặc process migration treo | Xác định migration owner và startup behavior |
| Lock xuất hiện lại ngay sau release | Job khác tự động retry/startup | Tạm dừng trigger và tìm process mới |
| Xóa lock nhưng vẫn có session treo | Lock Liquibase khác DBMS session | Xử lý session/transaction riêng theo DBA |
| Checksum mismatch sau crash | Changeset bị sửa hoặc artifact khác | Đối chiếu release artifact và identity |
| MARK_RAN khiến schema thiếu object | Precondition quá rộng | Reconcile và tạo forward fix nếu cần |
| Lock table không có hàng mong đợi | Sai metadata schema hoặc cấu hình custom | Xác định đúng metadata location |

## 26. Checklist xử lý incident stale lock

- [ ] Đã dừng hoặc kiểm soát pipeline retry mới.
- [ ] Đã xác nhận đúng database/catalog/environment.
- [ ] Đã xác nhận đúng Liquibase metadata schema và lock table.
- [ ] Đã lưu LOCKED, LOCKGRANTED và LOCKEDBY trước can thiệp.
- [ ] Đã xác định pipeline run/job đã tạo lock.
- [ ] Đã xác minh process/runner/container cũ đã kết thúc.
- [ ] Đã kiểm tra các job Liquibase khác và Spring Boot instances.
- [ ] Đã kiểm tra DBMS session, transaction và blocker.
- [ ] Không còn tiến trình/session cần bảo toàn trước khi release.
- [ ] Đã đọc log và xác định changeset cuối cùng nếu có thể.
- [ ] Đã kiểm tra DATABASECHANGELOG.
- [ ] Đã kiểm tra schema/data để phát hiện partial state.
- [ ] Đã dùng release-locks đúng version và đúng metadata configuration.
- [ ] Đã xác minh LOCKED = false sau thao tác.
- [ ] Đã reconciliation partial DDL/DML nếu cần.
- [ ] Đã chạy validate/status/update-sql trước retry theo quy trình.
- [ ] Đã update có kiểm soát và xác minh schema/history/data.
- [ ] Đã lưu incident evidence và người thực hiện.
- [ ] Đã xác định nguyên nhân gốc và hành động phòng ngừa.

## 27. Câu hỏi tự kiểm tra

**1. DATABASECHANGELOGLOCK có vai trò gì?**

Điều phối các tiến trình Liquibase cùng sử dụng lock table để tránh thực thi migration chồng lấn.

**2. Vì sao process chết nhưng LOCKED vẫn true?**

Luồng cleanup giải phóng lock có thể không chạy khi process bị kill, runner mất điện hoặc kết nối bị ngắt đột ngột.

**3. LOCKGRANTED cũ có đủ để kết luận stale lock không?**

Không. Migration có thể chạy lâu; phải xác minh job, process và DBMS session.

**4. LOCKEDBY có phải PID chính xác không?**

Không nhất thiết. Nó có thể là hostname/IP hoặc thông tin môi trường; cần đối chiếu CI và host/container.

**5. release-locks có rollback changeset không?**

Không. Nó giải phóng Liquibase metadata lock, không hoàn tác DDL/DML.

**6. LOCKED = false nhưng ALTER TABLE vẫn chờ có thể do đâu?**

Có thể do table/metadata/transaction lock của DBMS hoặc session khác.

**7. Vì sao phải kiểm tra DATABASECHANGELOG sau crash?**

Để biết changeset nào đã được ghi nhận; tuy nhiên vẫn cần kiểm tra schema vì DDL có thể đã partial commit trước history.

**8. Có nên cập nhật LOCKED = false trực tiếp bằng SQL không?**

Không nên dùng tùy tiện. Ưu tiên release-locks; thao tác trực tiếp chỉ thuộc quy trình DBA ngoại lệ đã được phê duyệt và kiểm chứng.

**9. Vì sao hai ứng dụng có thể không chặn nhau dù cùng database?**

Nếu chúng dùng các metadata lock table khác nhau, Liquibase không có một lock chung để điều phối.

**10. Có nên tự động release lock khi vượt TTL?**

Không. TTL không chứng minh process đã chết; tự động release có thể tạo hai migration chạy đồng thời.

**11. Khi nào được retry update?**

Sau khi xác minh không còn process/session cũ, lock đã mở, target đúng, schema/history/data đã được reconciliation và retry an toàn.

**12. Bằng chứng nào cần lưu sau incident?**

Job/process identity, lock metadata trước/sau, DBMS session, changeset cuối, artifact, hành động release, reconciliation và kết quả verify.

**Kết luận:** Khóa Liquibase còn tồn tại sau khi tiến trình bị dừng cần được xử lý như một incident có trạng thái, không phải một lỗi chỉ cần xóa cờ LOCKED. Hãy xác nhận đúng metadata table, điều tra pipeline/process/DBMS session, đánh giá changeset cuối và partial state, rồi mới dùng release-locks. Sau khi mở khóa, kiểm tra lại schema, dữ liệu và DATABASECHANGELOG trước khi retry. Tách Liquibase lock khỏi DBMS lock, dùng một cơ chế single-flight cho mỗi database target và lưu audit evidence sẽ giúp phục hồi an toàn, đồng thời giảm nguy cơ migration chạy chồng lấn trong các lần phát hành sau.

