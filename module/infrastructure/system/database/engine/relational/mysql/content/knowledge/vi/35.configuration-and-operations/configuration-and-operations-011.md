# Cấu hình và vận hành

## Event Scheduler, tác vụ bảo trì và lịch thực hiện ngoài database

MySQL có Event Scheduler để chạy các câu lệnh SQL theo lịch ngay trong máy chủ database. Đây là lựa chọn thuận tiện cho các công việc nhỏ, gắn chặt với dữ liệu và chỉ cần thao tác SQL, chẳng hạn xóa từng lô log hết hạn hoặc cập nhật bảng tổng hợp. Với các quy trình cần gọi API, chạy backup, xuất file, phối hợp nhiều dịch vụ, retry có kiểm soát hoặc điều phối trên nhiều máy chủ, nên dùng scheduler bên ngoài như cron, systemd timer, Windows Task Scheduler hoặc một nền tảng orchestration.

Chọn đúng nơi lập lịch là một quyết định vận hành. Event Scheduler giúp tác vụ nằm gần dữ liệu và giảm thành phần phải triển khai; scheduler bên ngoài giúp quản lý dependency, quan sát, phân phối công việc và phục hồi tốt hơn. Dù chọn cách nào, công việc vẫn cần idempotency, giới hạn thời gian, kiểm soát chạy trùng, ghi nhận kết quả và có phương án xử lý khi MySQL hoặc worker gián đoạn.

### 1. Hai nơi có thể điều phối công việc định kỳ

Event Scheduler là thành phần của MySQL Server. Một event chứa lịch chạy và câu lệnh SQL hoặc lời gọi stored procedure. Máy chủ kiểm tra lịch và thực thi event khi đến thời điểm.

Scheduler bên ngoài chạy độc lập với MySQL. Nó có thể gọi MySQL client, một chương trình ứng dụng, script, API hoặc một workflow nhiều bước. Ví dụ phổ biến là cron trên Linux, systemd timer, Windows Task Scheduler, Kubernetes CronJob hoặc nền tảng orchestration như Airflow.

| Tiêu chí | MySQL Event Scheduler | Scheduler bên ngoài database |
| --- | --- | --- |
| Nơi chạy | Bên trong mysqld | Một máy chủ, container hoặc dịch vụ điều phối riêng |
| Công việc phù hợp | SQL ngắn, bảo trì dữ liệu cục bộ, cập nhật bảng tổng hợp | Backup, ETL, xuất file, gọi API, nhiều hệ thống hoặc workflow dài |
| Phụ thuộc | MySQL đang chạy và `event_scheduler` được bật | Scheduler/worker và kết nối tới các hệ thống cần thiết |
| Giao dịch | Có thể dùng transaction trong stored procedure; phải chủ động thiết kế | Worker có thể quản lý nhiều transaction và nhiều dịch vụ |
| Retry và dependency | Phải tự thiết kế trong SQL hoặc bảng trạng thái | Thường có cơ chế retry, dependency, queue và alert tích hợp |
| Điều phối nhiều máy | Cần kiểm soát topology và chỉ định instance thực thi | Có thể dùng distributed scheduler, leader election hoặc lock dùng chung |
| Quan sát | Metadata event, error log và bảng audit do ứng dụng tự tạo | Lịch sử job, log, metric và cảnh báo của nền tảng |
| Thao tác ngoài SQL | Không trực tiếp chạy shell, gọi HTTP hay tạo file tùy ý | Có thể gọi chương trình, API, object storage và dịch vụ khác |

Không có lựa chọn tốt nhất cho mọi tác vụ. Hãy chọn theo phạm vi công việc, yêu cầu phục hồi và khả năng giám sát của hệ thống.

### 2. Khi nào nên dùng Event Scheduler?

Event Scheduler phù hợp khi công việc:

- Chủ yếu đọc hoặc ghi dữ liệu trong cùng MySQL instance.
- Có thời lượng ngắn và tài nguyên có thể giới hạn bằng batch.
- Có thể chạy lại an toàn nếu lần trước bị gián đoạn.
- Không cần chờ một workflow bên ngoài hoàn tất.
- Có thể quan sát qua bảng trạng thái hoặc log của máy chủ.

Ví dụ phù hợp gồm xóa một lô audit log quá hạn, cập nhật số liệu tổng hợp theo giờ, đánh dấu đơn hàng hết hạn hoặc tạo snapshot nghiệp vụ nhỏ trong database.

Không nên dùng Event Scheduler làm công cụ chính cho backup vật lý, nén/đẩy file ra object storage, gửi email hàng loạt, gọi API thanh toán, chạy migration nhiều dịch vụ hoặc xử lý một workflow kéo dài nhiều giờ. Event chỉ thực thi SQL trong MySQL; nó không phải một hệ thống chạy chương trình trên hệ điều hành.

### 3. Khi nào nên dùng scheduler bên ngoài?

Scheduler bên ngoài thường phù hợp hơn khi tác vụ cần một hoặc nhiều đặc điểm sau:

1. Chạy chương trình bên ngoài MySQL, như `mysqlsh`, công cụ backup, script kiểm tra hoặc worker ứng dụng.
2. Kết hợp nhiều nguồn dữ liệu hoặc nhiều dịch vụ theo thứ tự phụ thuộc.
3. Cần retry với exponential backoff, timeout, giới hạn số lần thử và dead-letter workflow.
4. Cần lịch sử lần chạy, log tập trung, metric, cảnh báo và giao diện vận hành.
5. Cần chạy trên nhiều worker, scale ngang hoặc phân phối theo partition/tenant.
6. Cần điều phối theo lịch nghiệp vụ phức tạp, lịch ngày nghỉ hoặc điều kiện từ hệ thống khác.

Ví dụ, quy trình backup có thể gồm kiểm tra dung lượng, tạo backup nhất quán, kiểm tra kết quả, mã hóa, tải lên object storage, xác minh checksum và gửi cảnh báo. Event Scheduler không phải nơi phù hợp để điều phối toàn bộ chuỗi này; một scheduler bên ngoài có thể gọi các công cụ chuyên dụng và ghi trạng thái từng bước.

### 4. Kiểm tra và bật Event Scheduler

Kiểm tra trạng thái hiện tại:

```sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';
```

Các trạng thái thường gặp:

| Giá trị | Ý nghĩa vận hành |
| --- | --- |
| `ON` | Event Scheduler đang hoạt động và có thể thực thi event được bật khi đến lịch |
| `OFF` | Scheduler đang tắt; có thể bật lại khi cấu hình máy chủ cho phép |
| `DISABLED` | Scheduler bị vô hiệu hóa khi khởi động; không thể chỉ dùng `SET GLOBAL` để bật trong runtime |

Trong môi trường được phép, có thể bật runtime:

```sql
SET GLOBAL event_scheduler = ON;
```

Để giữ cấu hình sau restart, cấu hình máy chủ trong file option phù hợp:

```ini
[mysqld]
event_scheduler = ON
```

Hoặc dùng tùy chọn khởi động tương ứng của MySQL. Việc bật scheduler là thay đổi ở cấp instance, cần phối hợp với quản trị viên và quy trình triển khai. Không bật đồng loạt trên mọi replica nếu chưa xác định instance nào được phép chạy tác vụ.

### 5. Event gọi stored procedure để giữ phần lịch đơn giản

Với tác vụ có nhiều bước SQL, nên đặt logic trong stored procedure và để event chỉ chịu trách nhiệm lập lịch. Cách này giúp có thể chạy thủ công để kiểm thử, tái sử dụng logic và quản lý quyền rõ ràng.

Ví dụ, bảng audit log:

```sql
CREATE TABLE audit_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL,
    actor_id BIGINT NULL,
    action_name VARCHAR(100) NOT NULL,
    details JSON NULL,
    PRIMARY KEY (id),
    KEY idx_audit_created_id (created_at, id)
) ENGINE = InnoDB;
```

Stored procedure xóa tối đa 5.000 hàng quá hạn trong một lần chạy:

```sql
DELIMITER //
CREATE PROCEDURE purge_old_audit_batch()
BEGIN
    DELETE FROM audit_log
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL 90 DAY
    ORDER BY created_at ASC, id ASC
    LIMIT 5000;
END//
DELIMITER ;
```

Tạo event chạy mỗi giờ:

```sql
CREATE EVENT ev_purge_old_audit
ON SCHEDULE EVERY 1 HOUR
STARTS CURRENT_TIMESTAMP + INTERVAL 1 HOUR
ON COMPLETION PRESERVE
ENABLE
DO CALL purge_old_audit_batch();
```

Ví dụ này chỉ xóa một batch cho mỗi lần chạy. Lần tiếp theo tiếp tục xử lý những hàng còn thỏa điều kiện. Cách làm giới hạn lượng công việc mỗi lần, giảm transaction dài và tạo khoảng nghỉ cho workload ứng dụng. Nếu cần xử lý nhiều batch liên tiếp, hãy đặt giới hạn thời gian hoặc số batch tối đa trong procedure để event không chiếm tài nguyên quá lâu.

`DELIMITER` là lệnh của MySQL client để đổi ký tự kết thúc khi nhập routine có nhiều dấu chấm phẩy; nó không phải câu SQL gửi nguyên văn tới server. Trong migration tool, dùng cơ chế delimiter hoặc routine statement riêng mà công cụ hỗ trợ.

### 6. Thiết kế tác vụ bảo trì theo batch

Không nên xóa hàng triệu bản ghi trong một transaction duy nhất chỉ vì tác vụ được chạy lúc ít người dùng. Transaction lớn có thể giữ khóa lâu, tạo nhiều undo/redo, làm purge chậm, tăng replica lag và khiến rollback tốn thời gian.

Với bảng log lớn, nên:

1. Có index hỗ trợ điều kiện lọc và thứ tự xử lý, ví dụ `(created_at, id)`.
2. Xóa số hàng giới hạn mỗi lần, ví dụ `LIMIT 5000`.
3. Commit mỗi batch nếu procedure xử lý nhiều batch.
4. Giới hạn số batch hoặc thời gian chạy trong một lượt.
5. Ghi lại số hàng đã xử lý và mốc tiến độ để lần sau tiếp tục.
6. Theo dõi thời gian lock, deadlock, history list length, I/O và replica lag.

Không dùng `OFFSET` để bỏ qua các batch đã xử lý trong bảng đang thay đổi. Với tác vụ archive hoặc chuyển dữ liệu, nên dùng watermark/keyset theo khóa ổn định, ví dụ tiếp tục từ `id` cuối cùng đã hoàn thành. Điều kiện phải bảo đảm các hàng mới hoặc hàng bị cập nhật không bị bỏ sót.

Đối với bảng partition theo thời gian, có thể cân nhắc bỏ partition cũ thay vì xóa từng hàng. Đây là thay đổi DDL cần đánh giá ràng buộc, backup, replication và khả năng rollback vận hành; scheduler chỉ nên gọi quy trình đã được kiểm chứng.

### 7. Ngăn hai lần chạy cùng tác vụ chồng lấn

Một event chạy lâu có thể gặp lần đến lịch tiếp theo khi công việc trước chưa xong. Không nên dựa vào giả định scheduler sẽ tự bảo vệ mọi trường hợp chạy trùng, nhất là khi có nhiều instance, failover hoặc cùng một logic được gọi cả từ event lẫn scheduler bên ngoài.

Với tác vụ SQL trên một MySQL instance, có thể dùng named lock qua `GET_LOCK()`:

```sql
DELIMITER //
CREATE PROCEDURE run_purge_with_lock()
BEGIN
    DECLARE v_lock INT DEFAULT 0;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        IF v_lock = 1 THEN
            DO RELEASE_LOCK('maintenance.purge_old_audit');
        END IF;
        RESIGNAL;
    END;

    SELECT GET_LOCK('maintenance.purge_old_audit', 0)
    INTO v_lock;

    IF v_lock = 1 THEN
        CALL purge_old_audit_batch();
        DO RELEASE_LOCK('maintenance.purge_old_audit');
        SET v_lock = 0;
    END IF;
END//
DELIMITER ;
```

Nếu lock đang được phiên khác giữ, `GET_LOCK(..., 0)` trả về ngay và lượt chạy hiện tại bỏ qua công việc. Handler giải phóng lock khi routine gặp exception rồi phát lại lỗi. Với quy trình phức tạp hơn, cần ghi log cả trường hợp skip do đang chạy.

Named lock có phạm vi trên một MySQL server, không phải distributed lock giữa nhiều máy chủ độc lập. Nếu cùng job có thể chạy trên source và replica hoặc trên nhiều cluster node, cần cơ chế điều phối ở cấp hệ thống, một leader duy nhất hoặc bảng claim có khóa duy nhất được lưu ở nơi dùng chung.

### 8. Idempotency và khả năng chạy lại

Scheduler thường cung cấp cơ chế kích hoạt công việc; nó không tự bảo đảm công việc chỉ xảy ra đúng một lần. Sau timeout hoặc mất kết nối, worker có thể không biết transaction đã commit hay chưa. Khi retry, cùng một công việc có thể được chạy lại.

Thiết kế idempotent có nghĩa là chạy lại cùng một đơn vị công việc không tạo tác động sai hoặc lặp ngoài ý muốn. Một số cách thường dùng:

- Dùng điều kiện trạng thái rõ ràng, ví dụ chỉ xử lý hàng `status = 'pending'` rồi chuyển sang `processed` trong cùng transaction.
- Dùng khóa duy nhất cho `job_name` và `run_key` để chặn cùng một kỳ công việc được ghi nhận hai lần.
- Dùng `INSERT ... ON DUPLICATE KEY UPDATE` cho bảng tổng hợp khi phép cập nhật có thể tính lại an toàn.
- Lưu watermark hoặc checkpoint và chỉ tiến về phía trước sau khi batch đã commit.
- Tách thao tác claim và xử lý; có lease hết hạn để thu hồi công việc bị worker bỏ dở.

Ví dụ bảng ghi nhận một kỳ chạy:

```sql
CREATE TABLE maintenance_job_run (
    job_name VARCHAR(100) NOT NULL,
    run_key VARCHAR(100) NOT NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    status VARCHAR(20) NOT NULL,
    affected_rows BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (job_name, run_key)
) ENGINE = InnoDB;
```

Khóa chính ghép ngăn tạo hai bản ghi cho cùng một job và cùng kỳ. Worker có thể thử claim bằng `INSERT` và xử lý duplicate key như một lần chạy đã được claim. Cần định nghĩa thêm cách phục hồi trạng thái `running` cũ, timeout/lease và xác minh kết quả trước khi cho phép chạy lại.

### 9. Ghi log kết quả và quan sát Event Scheduler

Không nên chỉ dựa vào việc event tồn tại để kết luận công việc đã chạy thành công. Cần theo dõi lần chạy gần nhất, trạng thái event và kết quả nghiệp vụ.

Liệt kê event:

```sql
SHOW EVENTS FROM app_db;
```

Xem định nghĩa và lịch:

```sql
SHOW CREATE EVENT app_db.ev_purge_old_audit;
```

Xem metadata event:

```sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STARTS,
    ENDS,
    STATUS,
    LAST_EXECUTED,
    EVENT_DEFINITION
FROM information_schema.events
WHERE EVENT_SCHEMA = 'app_db';
```

`LAST_EXECUTED` giúp xác định lần chạy gần nhất theo metadata; nó không thay thế bảng log chi tiết từng batch. Nên để procedure ghi `started_at`, `finished_at`, số hàng xử lý, status và thông tin lỗi vào bảng vận hành riêng. Đồng thời giám sát error log của MySQL và cảnh báo khi event không chạy đúng lịch hoặc lần chạy kéo dài bất thường.

Với scheduler bên ngoài, lưu run ID, scheduled time, actual start/end, exit code, retry count và log. Đồng bộ thời gian máy chủ và dùng cùng múi giờ chuẩn để đối chiếu lịch giữa scheduler và database.

### 10. Quyền thực thi và tài khoản chạy job

Event chạy theo security context của `DEFINER`. Người tạo event cần quyền `EVENT` trên schema phù hợp; routine được gọi cần quyền `EXECUTE`; definer phải có các quyền tối thiểu để thực hiện câu SQL bên trong routine. Nếu definer bị xóa hoặc quyền bị thu hồi, event có thể tồn tại nhưng thất bại khi chạy.

Nên dùng tài khoản dịch vụ chuyên biệt, chỉ cấp quyền trên bảng và routine cần thiết. Không dùng tài khoản `root` cho event bảo trì hoặc scheduler bên ngoài. Khi thay đổi definer, chuyển môi trường hoặc restore database, cần xác minh tài khoản và quyền tồn tại ở máy chủ đích.

Scheduler bên ngoài cũng cần một tài khoản database riêng với quyền tối thiểu. Không đặt mật khẩu trực tiếp trong command line, script được commit vào Git hoặc log. Dùng login path, option file có quyền filesystem hạn chế, secret manager hoặc cơ chế credential của nền tảng; kết nối từ xa nên dùng TLS và xác minh chứng thư theo chính sách bảo mật.

### 11. Múi giờ và thời điểm chạy

Event có metadata múi giờ được gắn khi tạo; scheduler bên ngoài lại phụ thuộc múi giờ của máy chủ hoặc cấu hình workflow. Nếu không quy định rõ, lịch chạy có thể lệch khi triển khai giữa các môi trường hoặc khi chuyển vùng.

Trước khi tạo event, nên đặt session time zone có chủ đích và kiểm tra `TIME_ZONE` trong `INFORMATION_SCHEMA.EVENTS`. Với công việc theo chu kỳ kỹ thuật, UTC thường dễ vận hành và đối chiếu log. Với nghiệp vụ cần giờ địa phương, phải xác định cách xử lý giờ mùa hè (DST), ngày nghỉ và thời điểm không tồn tại hoặc lặp lại khi đổi giờ.

Kiểm tra cấu hình thời gian:

```sql
SELECT
    @@GLOBAL.time_zone,
    @@SESSION.time_zone,
    @@system_time_zone,
    UTC_TIMESTAMP(),
    CURRENT_TIMESTAMP();
```

Không giả định scheduler ngoài và MySQL dùng cùng múi giờ chỉ vì cả hai đang chạy trên cùng máy. Hãy cấu hình tường minh và ghi thời gian chạy ở UTC trong log để so sánh giữa các hệ thống.

### 12. Event Scheduler trong replication và failover

Event là đối tượng database và định nghĩa event có thể được ghi vào binary log/replicate theo cấu hình. Điều đó không có nghĩa mọi replica đều nên thực thi cùng một tác vụ bảo trì. Nếu source và replica cùng chạy job xóa, archive hoặc cập nhật summary, có thể tạo tải trùng, sai lệch dữ liệu hoặc thực hiện thao tác ở node không phải writer.

Với hệ thống replication/failover:

1. Xác định node nào được phép chạy từng job; thường chỉ writer/primary hiện tại thực hiện tác vụ ghi.
2. Kiểm tra `event_scheduler`, `STATUS` và trạng thái event trên source lẫn replica.
3. Dùng cấu hình trạng thái phù hợp để event không chạy trên replica; xác minh lại sau khi promotion/failover.
4. Sau khi đổi primary, chỉ kích hoạt job ở node mới sau khi xác nhận node cũ đã dừng hoặc mất quyền thực thi.
5. Dùng idempotency và khóa/claim có phạm vi phù hợp để giảm nguy cơ hai node cùng nhận một kỳ công việc.
6. Theo dõi replica lag vì tác vụ bảo trì ghi nhiều có thể tạo lượng binlog lớn.

Trạng thái `DISABLE ON SLAVE` xuất hiện trong cú pháp/tài liệu ở một số phiên bản và trạng thái metadata có thể hiển thị là `SLAVESIDE_DISABLED`. Hãy kiểm tra cú pháp, tên thuật ngữ và hành vi đúng phiên bản MySQL đang vận hành. Không dựa vào một câu lệnh disable đơn lẻ thay cho quy trình failover có kiểm tra.

Scheduler bên ngoài cũng có thể chạy trùng sau failover nếu nhiều worker cùng nhìn thấy lịch. Cần leader election, distributed lock hoặc cơ chế claim có tính nguyên tử trên kho dữ liệu dùng chung; lock `GET_LOCK()` trên một server không bảo vệ các MySQL instance độc lập.

### 13. Ví dụ scheduler bên ngoài gọi MySQL

Với tác vụ cần chạy script, scheduler ngoài có thể gọi MySQL client hoặc worker ứng dụng. Ví dụ một cron job gọi script đã được kiểm thử:

```cron
15 2 * * * /usr/local/bin/run-db-maintenance.sh
```

Script có thể gọi MySQL client bằng login path đã cấu hình cho tài khoản dịch vụ:

```bash
mysql --login-path=maintenance app_db < /opt/db-jobs/rebuild_daily_summary.sql
```

Không đưa mật khẩu trực tiếp vào câu lệnh. Tệp SQL cần có transaction, điều kiện lọc và xử lý lỗi phù hợp; script phải kiểm tra exit code của client và trả trạng thái thất bại cho scheduler để kích hoạt cảnh báo hoặc retry.

Trên Windows, có thể tạo task trong Task Scheduler để gọi PowerShell script; trên Kubernetes, CronJob có thể tạo pod chạy worker. Dù dùng nền tảng nào, cần cấu hình concurrency policy, deadline, retry/backoff, secret và logging. Khóa cục bộ như `flock` chỉ ngăn hai tiến trình trên cùng host; nó không thay thế distributed lock nếu job có thể chạy trên nhiều host.

### 14. So sánh cách triển khai cho các tác vụ bảo trì thường gặp

| Tác vụ | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Xóa một batch log hết hạn mỗi giờ | Event Scheduler hoặc worker ngoài | SQL ngắn, chạy gần dữ liệu; cần batch và log |
| Cập nhật bảng tổng hợp nhỏ sau mỗi giờ | Event Scheduler | Phép tính SQL cục bộ, dễ chạy lại |
| Backup vật lý và upload object storage | Scheduler bên ngoài | Cần công cụ backup, file, mã hóa, upload và xác minh |
| Export CSV rồi gửi tới đối tác | Scheduler bên ngoài | Cần filesystem/network/API và credential riêng |
| Chạy ETL qua nhiều database | Scheduler bên ngoài | Cần dependency, checkpoint và retry nhiều bước |
| Gửi email nhắc việc | Scheduler bên ngoài hoặc hàng đợi ứng dụng | MySQL không phải dịch vụ gửi email; cần kiểm soát gửi trùng và retry |
| Rebuild index/bảo trì DDL bảng lớn | Quy trình vận hành bên ngoài | Cần cửa sổ bảo trì, kiểm tra dung lượng, lock, replication và giám sát |
| Tác vụ cần chỉ chạy trên primary sau failover | Scheduler có điều phối topology | Phải bảo đảm một nơi thực thi và phục hồi trạng thái sau promotion |

### 15. Quy trình triển khai một job định kỳ

1. **Xác định yêu cầu:** lịch, múi giờ, SLA, khối lượng, thời gian tối đa và hành vi khi bỏ lỡ một kỳ.
2. **Chọn nơi chạy:** Event Scheduler cho SQL cục bộ; scheduler ngoài cho workflow nhiều bước hoặc cần hệ thống khác.
3. **Thiết kế dữ liệu:** index, batch size, watermark, trạng thái job, khóa chống chạy trùng và bảng audit.
4. **Thiết kế lỗi:** timeout, retry, idempotency, xử lý deadlock, phục hồi lease và cảnh báo.
5. **Thiết kế quyền:** definer/service account riêng, quyền tối thiểu, secret được quản lý an toàn.
6. **Kiểm thử thủ công:** chạy routine/script với dữ liệu thử, xác minh kết quả và khả năng chạy lại.
7. **Bật lịch:** triển khai một instance trước, xác minh múi giờ, trạng thái scheduler và lần chạy đầu.
8. **Theo dõi:** thời gian chạy, số hàng, lỗi, lock wait, I/O, replica lag và độ trễ so với lịch.
9. **Kiểm thử phục hồi:** mô phỏng worker dừng, MySQL restart, lần chạy trễ và failover trong môi trường thử nghiệm.
10. **Vận hành vòng đời:** có quy trình disable, sửa lịch, chuyển definer, rotate secret và gỡ job không còn dùng.

### 16. Checklist trước khi chọn Event Scheduler hay scheduler ngoài

1. Công việc chỉ gồm SQL trong một MySQL instance hay cần gọi hệ thống bên ngoài?
2. Thời lượng và số lượng hàng có được giới hạn bằng batch không?
3. Có thể chạy lại an toàn sau timeout hoặc mất kết nối không?
4. Có cơ chế chống hai lần chạy cùng lúc và chống hai node cùng thực thi không?
5. Có ghi log thời điểm, kết quả, số hàng, lỗi và checkpoint không?
6. Múi giờ, DST và hành vi khi MySQL/scheduler ngừng hoạt động đã rõ chưa?
7. Definer hoặc service account có quyền tối thiểu và credential được bảo vệ không?
8. Đã kiểm tra replication, failover, replica lag và vị trí writer chưa?
9. Có timeout, retry/backoff, alert và runbook xử lý thất bại không?
10. Có người chịu trách nhiệm disable hoặc thay đổi job khi nghiệp vụ kết thúc không?

Event Scheduler là lựa chọn gọn cho các tác vụ SQL ngắn, cục bộ và có thể chạy lại. Scheduler bên ngoài phù hợp với backup, ETL, API và workflow cần quan sát hoặc điều phối nhiều thành phần. Trong cả hai trường hợp, một job đáng tin cậy phải có batch giới hạn, idempotency, cơ chế chống chạy trùng, quyền tối thiểu, log vận hành và quy trình phục hồi khi lịch không được thực hiện như dự kiến.
