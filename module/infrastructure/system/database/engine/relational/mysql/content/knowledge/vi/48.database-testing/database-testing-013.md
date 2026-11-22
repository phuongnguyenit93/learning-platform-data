# Kiểm thử migration, backup/restore, replication và failover

Một hệ thống MySQL chỉ đáng tin khi đã chứng minh được rằng nó có thể thay đổi schema, khôi phục dữ liệu, đồng bộ replica và chuyển vai trò máy chủ trong các tình huống có kiểm soát. Việc câu lệnh migration chạy thành công, job backup báo hoàn tất hoặc replica hiển thị trạng thái Running chưa đủ để kết luận hệ thống an toàn.

Bài học này xây dựng cách kiểm thử bốn năng lực vận hành quan trọng: **migration schema**, **backup và restore**, **replication** và **failover**. Mỗi năng lực cần có điều kiện đầu vào, dữ liệu kiểm thử, tiêu chí thành công, cách đo thời gian và bằng chứng có thể xem lại. Các bài thực hành cần chạy trên môi trường cô lập hoặc staging tương đương production; không thử nghiệm phá hoại trực tiếp trên hệ thống đang phục vụ người dùng.

Trong phạm vi **DATABASE_MYSQL**, các bài kiểm thử kết nối với thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời. Chúng cũng kiểm tra khả năng đọc execution plan, tối ưu truy vấn, phân quyền, sao lưu và xử lý sự cố của cơ sở dữ liệu quan hệ.

## 1. Mục tiêu và mô hình kiểm thử

Sau bài học, bạn có thể:

- Thiết kế bộ kiểm thử migration cho các phiên bản schema được hỗ trợ.
- Kiểm tra tính đúng đắn của dữ liệu sau thay đổi DDL và backfill.
- Tạo backup, restore trên máy chủ độc lập và phục hồi đến một thời điểm bằng binary log.
- Xác minh replica nhận và áp dụng giao dịch đúng thứ tự, đo replication lag.
- Diễn tập switchover/failover, kiểm soát split-brain và kiểm tra ứng dụng kết nối lại.
- Đo RPO/RTO thực tế và lưu bằng chứng kiểm thử.
- Tạo pipeline CI/CD có thể lặp lại, an toàn và gần với môi trường production.

### 1.1. Bốn năng lực cần kiểm tra

~~~mermaid
flowchart TD
    PLAN[Kế hoạch thay đổi] --> MIG[Migration test]
    PLAN --> BACKUP[Backup / Restore test]
    PLAN --> REPL[Replication test]
    PLAN --> FAIL[Failover test]
    MIG --> DATA[Kiểm tra cấu trúc và dữ liệu]
    BACKUP --> PITR[Restore và PITR]
    REPL --> CONS[GTID, lag và tính nhất quán]
    FAIL --> PROMOTE[Promote và kết nối lại]
    DATA --> EVIDENCE[Bằng chứng và RPO/RTO]
    PITR --> EVIDENCE
    CONS --> EVIDENCE
    PROMOTE --> EVIDENCE
~~~

| Năng lực | Câu hỏi chính | Bằng chứng thành công |
|---|---|---|
| Migration | Có thể nâng schema từ các phiên bản được hỗ trợ mà không làm sai dữ liệu hoặc phá ứng dụng không? | Schema đúng, invariant dữ liệu đúng, ứng dụng cũ/mới hoạt động theo kế hoạch |
| Backup/restore | Có thể khôi phục dữ liệu và dịch vụ trong mục tiêu đã cam kết không? | Restore hoàn tất, đối soát đạt, RPO/RTO đo được |
| Replication | Replica có nhận và áp dụng đầy đủ giao dịch theo đúng thứ tự không? | GTID/position bắt kịp, dữ liệu khớp, không có lỗi applier |
| Failover | Khi primary mất, có thể chuyển sang máy chủ mới mà tránh hai primary cùng ghi không? | Primary cũ được fencing, primary mới nhận ghi, client phục hồi, RPO/RTO được ghi nhận |

### 1.2. Phân biệt test logic và test vận hành

Unit test phù hợp để kiểm tra logic chuyển đổi dữ liệu thuần túy, validation hoặc quy tắc nghiệp vụ. Integration test cần chạy với MySQL thật để kiểm tra DDL, constraint, transaction, SQL mode, collation, locking và hành vi JDBC.

Kiểm thử vận hành cần có môi trường nhiều máy chủ và các thành phần gần với production: primary, replica, binary log archive, proxy/router, connection pool, backup storage và công cụ giám sát. Mock một replica hoặc giả lập kết quả backup không thể chứng minh replication hay restore thực sự hoạt động.

## 2. Thiết kế môi trường kiểm thử

### 2.1. Môi trường cần tương đồng production

Trước khi kiểm thử, ghi lại các đặc điểm quan trọng:

- Phiên bản MySQL chính xác, bao gồm patch release.
- Storage engine, charset, collation, SQL mode và time zone.
- `server_id`, GTID, binary log và cấu hình replication.
- `max_connections`, cấu hình InnoDB và dung lượng storage.
- Phiên bản JDBC driver, Spring Boot, Hibernate và migration tool.
- Cấu hình backup, keyring, TLS, user/role và quyền.
- Proxy, MySQL Router, load balancer và timeout mạng.
- Kích thước dữ liệu, số lượng bảng, index và phân bố dữ liệu.

Một container MySQL nhỏ rất hữu ích cho CI, nhưng không đại diện đầy đủ cho production có hàng terabyte dữ liệu, I/O giới hạn, nhiều replica và proxy. Dùng container để kiểm tra logic schema và tích hợp; dùng staging hoặc bản sao có kích thước tương đương để đo DDL, backup/restore, replication throughput và failover.

### 2.2. Dùng MySQL Testcontainers cho integration test

Ví dụ với Spring Boot, JUnit và Testcontainers:

~~~java
@Testcontainers
@SpringBootTest
class OrderRepositoryIT {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("appdb")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
    }

    @Autowired
    OrderRepository orderRepository;

    @Test
    void persistsAndReadsOrder() {
        Order order = new Order("ORD-1001", new BigDecimal("125.50"));
        orderRepository.saveAndFlush(order);

        Order loaded = orderRepository.findByOrderCode("ORD-1001")
            .orElseThrow();

        assertEquals(new BigDecimal("125.50"), loaded.getTotalAmount());
    }
}
~~~

Đây là ví dụ minh họa. Cần thêm dependency Testcontainers MySQL/JUnit tương ứng với phiên bản dự án. Hãy pin image theo patch release được production sử dụng thay vì để tag trôi nổi khi cần kết quả có thể tái lập. Cấu hình container với charset, collation, SQL mode và time zone phù hợp.

Không dùng H2 thay cho MySQL để kết luận migration SQL tương thích. H2 có cú pháp, kiểu dữ liệu, transaction, index, locking và optimizer khác MySQL. H2 vẫn có thể hữu ích cho unit test logic không phụ thuộc database.

### 2.3. Dữ liệu kiểm thử

Tạo fixture có cả trường hợp thông thường và biên:

- Bảng rỗng và bảng có dữ liệu lớn.
- Khóa chính tăng dần, UUID hoặc khóa ghép nếu hệ thống sử dụng.
- Giá trị NULL, chuỗi rỗng, Unicode và chuỗi sát giới hạn độ dài.
- Số âm, số rất lớn, decimal có scale, ngày giờ và múi giờ.
- Bản ghi có quan hệ foreign key, dữ liệu tham chiếu và trường hợp bị từ chối.
- Giá trị trùng, duplicate key và dữ liệu lịch sử cũ.
- Dữ liệu có phân bố lệch, một số tenant/bảng rất lớn.
- Transaction đồng thời cập nhật cùng một bản ghi.

Lưu lại fixture hoặc seed script có version. Mỗi lần chạy test cần biết chính xác dữ liệu đầu vào, migration version và cấu hình máy chủ.

## 3. Kiểm thử migration schema

### 3.1. Kiểm tra mọi đường nâng cấp được hỗ trợ

Một bộ migration test cần kiểm tra nhiều trạng thái xuất phát:

1. Database rỗng: cài mới toàn bộ migration.
2. Phiên bản schema gần nhất: nâng lên phiên bản mới.
3. Các phiên bản cũ còn được hỗ trợ: nâng theo đúng chuỗi migration thực tế.
4. Database có dữ liệu lớn và dữ liệu biên: xác minh backfill và chuyển đổi.
5. Database có đối tượng phụ thuộc: view, trigger, routine, event, foreign key và index.

Không chỉ kiểm tra đường từ schema mới nhất trong môi trường developer. Người dùng production có thể bỏ qua nhiều lần release, vì vậy phải biết hệ thống có hỗ trợ nâng từ phiên bản cũ trực tiếp hay cần nâng tuần tự qua từng phiên bản.

Với Flyway hoặc Liquibase, kiểm tra migration history, version, checksum và trạng thái thực thi. Nếu migration thất bại giữa chừng, xác định những DDL nào đã hoàn tất và database đang ở trạng thái nào. Nhiều DDL MySQL có implicit commit; không giả định toàn bộ migration sẽ rollback nguyên tử chỉ vì migration tool quản lý transaction.

### 3.2. Ví dụ migration thêm cột và backfill

Giả sử bảng `orders` cần thêm `source_channel` để ghi nhận nguồn tạo đơn. Một cách triển khai tương thích là chia thành các giai đoạn:

**Expand:** thêm cột nullable:

~~~sql
ALTER TABLE appdb.orders
  ADD COLUMN source_channel VARCHAR(24) NULL;
~~~

**Migrate:** backfill dữ liệu cũ theo batch nhỏ, dựa trên khóa chính:

~~~sql
UPDATE appdb.orders
SET source_channel = 'legacy'
WHERE order_id > 0
  AND order_id <= 10000
  AND source_channel IS NULL;
~~~

Lặp lại với các khoảng khóa tiếp theo. Theo dõi thời gian mỗi batch, lock wait, redo/undo, CPU, I/O và replication lag. Nếu bảng có khóa không liên tục hoặc phân bố lệch, dùng chiến lược phân trang phù hợp thay vì giả định mọi khoảng có cùng số hàng.

**Validate:** kiểm tra số lượng chưa chuyển đổi và giá trị ngoài tập cho phép:

~~~sql
SELECT COUNT(*) AS missing_source
FROM appdb.orders
WHERE source_channel IS NULL;

SELECT source_channel, COUNT(*) AS row_count
FROM appdb.orders
GROUP BY source_channel;
~~~

**Contract:** sau khi mọi ứng dụng đã ghi cột mới và dữ liệu được kiểm chứng, mới quyết định đặt NOT NULL hoặc xóa cấu trúc cũ. Nếu cột mới cần NOT NULL, xác định default và quy tắc cho dữ liệu lịch sử trước khi áp constraint.

Không chạy migration thay đổi nullability hoặc drop cột trước khi xác nhận tất cả phiên bản ứng dụng tương thích.

### 3.3. Kiểm tra cấu trúc sau migration

Dùng `SHOW CREATE TABLE` để kiểm tra định nghĩa thực tế:

~~~sql
SHOW CREATE TABLE appdb.orders;
~~~

Đối chiếu các thuộc tính:

- Tên, thứ tự, kiểu dữ liệu và nullability của cột.
- Default, unsigned, generated expression và comment.
- Primary key, unique key, foreign key và index.
- Engine, charset, collation và partition.
- View, trigger, procedure, function và event.
- Quyền user/role được ứng dụng sử dụng.

Có thể truy vấn Information Schema để kiểm tra tự động:

~~~sql
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

Không chỉ so sánh tên cột. Ví dụ đổi `DECIMAL(12,2)` thành `DECIMAL(10,2)` có thể làm dữ liệu lớn không còn lưu được dù migration vẫn tạo schema thành công.

### 3.4. Kiểm tra invariant dữ liệu

Invariant là điều kiện nghiệp vụ phải luôn đúng trước và sau migration. Ví dụ:

- Mỗi đơn hàng có một mã đơn duy nhất.
- Tổng thanh toán không âm.
- Trạng thái đơn thuộc tập giá trị cho phép.
- Mỗi chi tiết đơn hàng tham chiếu đến một đơn tồn tại.
- Tổng số lượng và tổng tiền không thay đổi sau chuyển đổi.
- Giá trị cột mới được ánh xạ đúng từ cột cũ.

Kiểm tra khóa trùng:

~~~sql
SELECT order_code, COUNT(*) AS duplicate_count
FROM appdb.orders
GROUP BY order_code
HAVING COUNT(*) > 1;
~~~

Kiểm tra bản ghi mồ côi:

~~~sql
SELECT COUNT(*) AS orphan_items
FROM appdb.order_items i
LEFT JOIN appdb.orders o ON o.order_id = i.order_id
WHERE o.order_id IS NULL;
~~~

Kiểm tra tổng giá trị:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM appdb.orders;
~~~

So sánh kết quả trước và sau migration trên cùng tập dữ liệu. Nếu migration có chủ đích thay đổi giá trị, viết quy tắc đối chiếu rõ ràng thay vì yêu cầu hai tổng phải bằng nhau.

### 3.5. Kiểm tra tương thích ứng dụng cũ và mới

Với triển khai rolling, các phiên bản ứng dụng có thể cùng hoạt động trong một khoảng thời gian. Kiểm thử ma trận:

| Schema | Ứng dụng cũ | Ứng dụng mới |
|---|---|---|
| Schema trước expand | Phải hoạt động | Chưa được triển khai nếu cần cột mới |
| Schema sau expand | Vẫn hoạt động | Có thể hoạt động nếu code hỗ trợ cột mới |
| Schema sau migrate | Phải còn tương thích nếu chưa contract | Đọc/ghi theo cấu trúc mới |
| Schema sau contract | Không còn được hỗ trợ | Phải hoạt động |

Kiểm tra cả writer, reader, worker, batch, báo cáo, CDC consumer và script vận hành. Một API mới hoạt động không chứng minh worker cũ không còn ghi tên cột đã bỏ.

### 3.6. Kiểm tra DDL và hiệu năng

Chạy migration trên bản sao có dung lượng gần production. Đo:

- Thời gian chờ metadata lock và thời gian thực thi DDL.
- CPU, IOPS, dung lượng tạm, redo/undo và binary log.
- Replication lag trong lúc DDL/backfill.
- Khả năng phục vụ query đọc/ghi trong migration.
- Execution plan của các truy vấn quan trọng trước và sau.

Dùng `EXPLAIN` hoặc `EXPLAIN ANALYZE` để xác nhận truy vấn vẫn dùng index và có cardinality phù hợp. `EXPLAIN ANALYZE` thực thi câu truy vấn, vì vậy chỉ chạy với truy vấn an toàn trên môi trường phù hợp.

Nếu cần DDL không được phép fallback sang copy table, có thể chỉ định thuật toán mà phiên bản hỗ trợ để migration thất bại rõ ràng khi không đáp ứng. Không mặc định mọi thao tác đều hỗ trợ `ALGORITHM=INSTANT` hoặc `LOCK=NONE`; xác nhận tài liệu và thử trên đúng phiên bản, engine và cấu trúc bảng.

## 4. Kiểm thử backup và restore

### 4.1. Xác định mục tiêu và phạm vi

Trước khi chạy backup test, ghi nhận:

- RPO: mức mất dữ liệu tối đa được chấp nhận.
- RTO: thời gian tối đa để dịch vụ hoạt động lại.
- Phạm vi: toàn instance, schema, bảng hoặc dữ liệu nghiệp vụ.
- Phiên bản MySQL và công cụ backup/restore.
- Keyring, certificate, plugin, user/role và file cấu hình cần thiết.
- Nơi lưu bản backup và binary log archive.
- Chính sách retention và quyền truy cập.

Một job backup có exit code 0 mới chứng minh công cụ đã hoàn tất theo góc nhìn của nó. Cần kiểm tra file, manifest, checksum và thực hiện restore thật.

### 4.2. Kịch bản backup test

Một bài test backup đầy đủ:

1. Tạo fixture với các bảng InnoDB, view, trigger, routine và event cần thiết.
2. Ghi lại thời điểm, GTID set hoặc tọa độ binary log.
3. Chạy full backup bằng công cụ đã chọn.
4. Kiểm tra mã thoát, log, manifest, checksum và kích thước file.
5. Sao chép backup sang vùng lưu trữ độc lập.
6. Xác nhận file có thể đọc/giải mã bằng đúng khóa.
7. Kiểm tra binary log từ mốc backup được archive liên tục.
8. Lưu thông tin phiên bản server và công cụ đi kèm backup.

Ví dụ logical dump với MySQL:

~~~bash
mysqldump --login-path=backup \
  --single-transaction --quick \
  --source-data=2 \
  --routines --events --triggers --hex-blob \
  --databases appdb \
  > appdb-backup.sql
~~~

`--single-transaction` cung cấp snapshot nhất quán cho bảng InnoDB. DDL đồng thời trên các bảng đang dump có thể làm snapshot không nhất quán hoặc gây lỗi; đóng băng thay đổi cấu trúc trong cửa sổ backup. Với bảng không transactional, cần phương án khóa hoặc backup phù hợp.

Đối với dữ liệu lớn, kiểm thử MySQL Shell dump/load hoặc physical backup tương thích. Đừng suy ra thời gian restore từ tốc độ dump; load/index build/prepare thường có đặc điểm tài nguyên khác.

### 4.3. Restore trên máy chủ cô lập

Dựng một instance phục hồi có:

- Phiên bản MySQL tương thích với loại backup.
- Dung lượng data, temporary tablespace và binary log đủ dùng.
- Keyring/plugin/certificate cần thiết.
- Endpoint riêng, không thể nhận traffic production.
- Tài khoản restore riêng.
- Mạng và DNS được cô lập để tránh ứng dụng kết nối nhầm.

Runbook restore tổng quát:

1. Cấp phát máy chủ phục hồi.
2. Cài phiên bản và công cụ đúng yêu cầu.
3. Khôi phục cấu hình, plugin và khóa cần thiết.
4. Restore full backup.
5. Với physical backup, thực hiện prepare/apply-log theo tài liệu công cụ.
6. Khởi động MySQL và kiểm tra error log, tablespace.
7. Xác minh schema, đối tượng và user cần thiết.
8. Chạy đối soát dữ liệu và smoke test ứng dụng.
9. Ghi lại thời gian từng bước và kết quả.

Nếu dùng logical dump, một file SQL có thể đã nạp được một phần trước khi gặp lỗi. Không chạy lại file trên database đã nạp dở nếu chưa xác định tính idempotent và trạng thái từng câu lệnh. Có thể dựng lại schema đích sạch rồi restore lại.

### 4.4. Kiểm thử point-in-time recovery

PITR kết hợp full backup với binary log từ mốc backup đến mốc cần phục hồi.

Một kịch bản kiểm thử có thể làm như sau:

1. Tạo full backup.
2. Ghi GTID set hoặc file/position của snapshot.
3. Tạo một giao dịch kiểm thử có marker duy nhất, ví dụ thêm bản ghi `TEST-BEFORE`.
4. Ghi nhận tọa độ hoặc thời điểm phục hồi ngay sau giao dịch này.
5. Tạo một giao dịch tiếp theo `TEST-AFTER`.
6. Thực hiện thao tác phá hủy có kiểm soát trong môi trường thử nghiệm, ví dụ xóa một bảng fixture.
7. Restore full backup vào máy chủ cô lập.
8. Phát lại binary log đến mốc đã ghi ở bước 4, trước giao dịch `TEST-AFTER` và thao tác phá hủy.
9. Xác minh `TEST-BEFORE` tồn tại, `TEST-AFTER` không tồn tại và bảng fixture được phục hồi.

Dùng `mysqlbinlog` để đọc và giới hạn log theo tọa độ hoặc thời điểm:

~~~bash
mysqlbinlog \
  --start-position=12345 \
  --stop-datetime="2026-11-19 14:34:59" \
  /backup/mysql-bin.000123 \
  /backup/mysql-bin.000124 \
  > /restore/replay.sql
~~~

Các giá trị trên chỉ là placeholder. Trong kiểm thử thực tế phải dùng tọa độ, timestamp, timezone và danh sách file log của backup. Để dừng chính xác trước một giao dịch, ưu tiên xác định event/transaction boundary và kiểm tra output; timestamp có thể không đủ chính xác nếu nhiều giao dịch gần nhau.

Đọc nội dung file replay trước khi áp dụng. Không phát lại binary log chưa kiểm tra lên production. DDL có implicit commit và không thể được hoàn tác bằng ROLLBACK thông thường.

### 4.5. Tiêu chí đạt của restore test

- MySQL khởi động thành công và mở được tablespace.
- Số schema/bảng/đối tượng cần thiết đúng.
- Checksum hoặc đối soát dữ liệu đạt tiêu chí.
- User, role, grant và kết nối TLS hoạt động.
- Có thể chạy truy vấn nghiệp vụ trọng yếu.
- PITR dừng đúng mốc; dữ liệu trước/sau mốc được phân biệt đúng.
- RTO và RPO thực tế được đo và nằm trong mục tiêu.
- Log, manifest, version và kết quả restore được lưu lại.

## 5. Kiểm thử replication

### 5.1. Kiểm tra cấu hình nền

Với replication dựa trên GTID, kiểm tra nguồn và đích có cấu hình tương thích. Nguồn cần binary log; `server_id` phải duy nhất trong topology. Dùng row-based binary logging nếu kiến trúc và công cụ yêu cầu.

Trên nguồn:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'enforce_gtid_consistency';
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW BINARY LOG STATUS;
~~~

Trên replica:

~~~sql
SHOW REPLICA STATUS\G
~~~

Kiểm tra receiver/applier, lỗi gần nhất, GTID đã nhận và đã thực thi, vị trí relay/source log và replication lag. Không chỉ nhìn một trường `Seconds_Behind_Source`; chỉ số này có thể là NULL hoặc không phản ánh đầy đủ độ trễ trong một số trạng thái.

### 5.2. Kiểm thử giao dịch đi từ source đến replica

Một test đơn giản:

1. Ghi một bản ghi có ID duy nhất trên source và commit.
2. Đọc `@@GLOBAL.gtid_executed` sau commit để ghi lại GTID set cần chờ.
3. Trên replica, chờ tập GTID đó được thực thi.
4. Đọc bản ghi trên replica và so sánh với source.

Trên source:

~~~sql
INSERT INTO appdb.replication_probe(probe_id, payload)
VALUES ('replica-test-001', 'committed-on-source');

SELECT @@GLOBAL.gtid_executed;
~~~

Trên replica, dùng GTID set vừa ghi nhận:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('SOURCE_GTID_SET', 60);
~~~

Kết quả `0` nghĩa là tập GTID đã được thực thi trong thời gian chờ; `1` nghĩa là timeout. Sau đó kiểm tra dữ liệu:

~~~sql
SELECT probe_id, payload
FROM appdb.replication_probe
WHERE probe_id = 'replica-test-001';
~~~

Dùng bảng probe riêng hoặc fixture được kiểm soát. Không để bản ghi kiểm thử làm nhiễu dữ liệu nghiệp vụ.

### 5.3. Kiểm thử lag và khả năng bắt kịp

Tạo workload ghi có kiểm soát trên source, đo:

- Thời gian commit ở source.
- Thời điểm GTID được thực thi trên replica.
- `Seconds_Behind_Source` và trạng thái receiver/applier.
- Tốc độ nhận/applier transaction.
- CPU, I/O, relay log và dung lượng binary log.
- Thời gian replica bắt kịp sau khi workload giảm hoặc dừng.

Không cố tình tạo tải vượt khả năng production trên hệ thống thật. Dùng staging hoặc bản sao với giới hạn tài nguyên. Một test lag cần có ngưỡng chấp nhận, ví dụ replica phải bắt kịp trong một thời gian xác định sau khi dừng tải kiểm thử.

### 5.4. Kiểm thử lỗi replication

Trong staging, diễn tập các trường hợp:

- Replica mất kết nối mạng với source.
- Receiver dừng nhưng applier vẫn có relay log để xử lý.
- Applier gặp lỗi do schema hoặc dữ liệu không tương thích.
- Binary log cần thiết bị purge trước khi replica đọc.
- Replica restart và tiếp tục từ metadata đã lưu.
- DDL được áp dụng và consumer đọc schema mới.
- Transaction chạm nhiều schema trong topology có filter.

Với mỗi lỗi, xác nhận alert được phát, runbook chỉ đúng vị trí lỗi và replica có thể phục hồi bằng cách hợp lệ. Không dùng skip counter hoặc bỏ giao dịch tùy tiện để chuyển trạng thái về Running; điều đó có thể che giấu dữ liệu thiếu.

### 5.5. Kiểm tra tính nhất quán dữ liệu

So sánh checksum hoặc thống kê theo bảng/chunk tại cùng mốc dữ liệu. Có thể đối chiếu số hàng, tổng tiền, min/max, khóa trùng và quan hệ foreign key. Nếu source vẫn ghi trong lúc so sánh, hai kết quả có thể khác nhau do thời điểm đọc; cần chờ một GTID set chung hoặc dừng ghi trong cửa sổ kiểm tra.

Kiểm thử riêng hành vi ứng dụng đọc từ replica:

- Read-after-write có cần đọc lại từ primary không?
- Ứng dụng có chấp nhận eventual consistency không?
- Khi replica lag vượt ngưỡng, router có chuyển đọc về primary hoặc từ chối truy vấn không?
- Transaction có đọc dữ liệu vừa ghi trên một replica khác không?

Replication đang Running không đồng nghĩa replica luôn phù hợp cho read-after-write.

## 6. Kiểm thử switchover và failover

### 6.1. Phân biệt switchover và failover

**Switchover** là chuyển primary có kế hoạch, khi source vẫn hoạt động và có thể dừng ghi, chờ replica bắt kịp rồi chuyển vai trò.

**Failover** là chuyển vai trò khi primary bị lỗi hoặc không còn phục vụ được. Có thể không lấy được mốc cuối từ primary cũ; với asynchronous replication, một số giao dịch đã commit có thể chưa tới replica được promote.

Cả hai đều cần kiểm tra fencing, dữ liệu, kết nối ứng dụng và khả năng phục hồi của node cũ. Failover test phải có kịch bản tránh split-brain: hai máy chủ cùng nhận ghi độc lập.

### 6.2. Switchover có kiểm soát

Một runbook tổng quát cho topology primary/replica:

1. Bật maintenance hoặc chặn luồng ghi mới.
2. Drain request và chờ transaction đang mở hoàn tất.
3. Fence primary cũ bằng `super_read_only` và cơ chế hạ tầng ngăn ứng dụng ghi vào nó.
4. Ghi GTID set cuối cùng của primary.
5. Chờ replica thực thi hết GTID set đó.
6. Xác nhận receiver/applier không lỗi và dữ liệu cần thiết đã có.
7. Dừng replication channel trên replica được chọn làm primary mới.
8. Mở quyền ghi trên node mới theo runbook.
9. Chuyển Router/proxy/DNS/endpoint và kiểm tra kết nối mới.
10. Mở traffic theo từng bước, xác nhận ghi/đọc và theo dõi lỗi.
11. Giữ node cũ ở trạng thái fenced; chỉ tái gia nhập topology sau khi được đồng bộ đúng cách.

Ví dụ lệnh fencing và chờ mốc GTID:

~~~sql
-- Trên primary cũ sau khi dừng mọi writer
SET GLOBAL super_read_only = ON;

SELECT @@GLOBAL.gtid_executed;
~~~

Trên replica được chọn:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('FINAL_SOURCE_GTID_SET', 120);
~~~

Chỉ tiếp tục khi replica đã thực thi hết tập GTID cuối và các kiểm tra khác đạt. Lệnh mở ghi trên node mới phải theo đúng topology và quy trình quản lý của tổ chức. Với MySQL thông thường, cần tắt `super_read_only` và `read_only` theo thứ tự thích hợp sau khi node đã được promote. Nếu dùng InnoDB Cluster/Group Replication, hãy dùng quy trình quản trị của topology đó thay vì thao tác thủ công như một replica độc lập.

### 6.3. Failover không có kế hoạch

Diễn tập primary bị mất kết nối hoặc bị cô lập trong môi trường staging:

- Xác nhận hệ thống phát hiện primary không còn khả dụng.
- Thực hiện fencing hoặc xác minh primary cũ không thể nhận ghi.
- Chọn replica đủ điều kiện dựa trên GTID đã nhận/thực thi và trạng thái dữ liệu.
- Xác định giao dịch có thể bị mất do replication bất đồng bộ.
- Promote replica theo runbook.
- Chuyển endpoint và xác nhận ứng dụng tạo connection mới.
- Kiểm tra ghi mới, đọc dữ liệu và trạng thái transaction.
- Ghi nhận GTID cuối cùng có thể bảo vệ và mốc dữ liệu bị thiếu nếu có.
- Khi primary cũ quay lại, giữ nó read-only và tái đồng bộ theo quy trình; không tự động cho nó nhận ghi.

Không promote replica chỉ dựa trên việc nó đang Running. Cần đánh giá độ mới của dữ liệu và rủi ro mất transaction. Với asynchronous replication, commit trên primary không nhất thiết đã được replica nhận trước khi primary mất. Semisynchronous replication có thể giảm cửa sổ mất dữ liệu nhưng không nên mặc định là bảo đảm zero data loss trong mọi tình huống; kiểm tra chế độ timeout/fallback và trạng thái xác nhận thực tế.

### 6.4. Kiểm tra client và connection pool sau failover

Database chuyển primary thành công nhưng ứng dụng vẫn có thể lỗi nếu connection pool giữ socket đến node cũ hoặc DNS cache chưa cập nhật.

Kiểm thử:

- JDBC driver có reconnect khi physical connection bị mất không?
- HikariCP có loại connection hỏng và tạo connection mới không?
- MySQL Router/proxy có route đến primary mới không?
- DNS TTL và connection string có khiến client tiếp tục gọi node cũ không?
- Transaction bị ngắt giữa chừng có được báo lỗi rõ ràng không?
- Retry có idempotent và có thể xác định kết quả commit không?
- Worker, scheduler, batch và consumer có kết nối lại đúng node không?

Không retry một giao dịch ghi mù quáng sau lỗi mạng. Client có thể mất kết nối sau khi server commit nhưng trước khi nhận phản hồi. Dùng idempotency key, mã giao dịch nghiệp vụ hoặc truy vấn xác minh trạng thái trước khi thử lại.

## 7. Đo RPO và RTO

### 7.1. RPO

RPO là khoảng dữ liệu tối đa có thể mất. Trong failover, xác định:

- GTID cuối đã commit trên primary cũ nếu lấy được.
- GTID cuối đã thực thi trên replica được promote.
- Transaction nào đã được xác nhận với client.
- Transaction nào chỉ có trên primary cũ và chưa được replica nhận.
- Các giao dịch bị mất hoặc cần đối soát sau chuyển đổi.

Không dùng `Seconds_Behind_Source` làm phép đo RPO duy nhất. So sánh GTID và dữ liệu tại mốc kiểm thử mới cho biết phạm vi giao dịch replica thực sự có.

### 7.2. RTO

RTO là thời gian từ khi dịch vụ mất khả năng phục vụ đến khi ứng dụng hoạt động trở lại. Ghi lại các mốc:

| Mốc | Nội dung |
|---|---|
| T0 | Phát hiện primary hoặc database không khả dụng |
| T1 | Quyết định switchover/failover và bắt đầu fencing |
| T2 | Chọn và promote node mới |
| T3 | Router/proxy/endpoint chuyển sang node mới |
| T4 | Ứng dụng tạo connection mới và smoke test đạt |
| T5 | Traffic được mở lại và lỗi trở về ngưỡng bình thường |

RTO thực tế là khoảng từ T0 đến thời điểm dịch vụ đạt tiêu chí hoạt động trở lại do tổ chức xác định. Không dừng đồng hồ ở lúc MySQL process khởi động hoặc lúc replica được promote.

### 7.3. Ví dụ ghi nhận kết quả

| Chỉ số | Mục tiêu giả định | Kết quả diễn tập |
|---|---:|---:|
| RPO | ≤ 30 giây | Ghi số đo thực tế |
| RTO | ≤ 5 phút | Ghi số đo thực tế |
| Replica catch-up sau tải test | ≤ 2 phút | Ghi số đo thực tế |
| Restore full backup | ≤ 45 phút | Ghi số đo thực tế |
| PITR đến trước transaction lỗi | Đúng mốc | PASS/FAIL và GTID/position |

Các con số trong bảng chỉ là ví dụ để minh họa cách đặt tiêu chí. Chọn mục tiêu theo yêu cầu nghiệp vụ, SLA và kiến trúc thực tế.

## 8. Tích hợp kiểm thử vào CI/CD

### 8.1. Các lớp pipeline

Một pipeline hợp lý có thể gồm:

1. **Static validation:** kiểm tra migration file, naming, version, checksum và secret.
2. **Unit test:** kiểm tra logic chuyển đổi/validation độc lập với database.
3. **MySQL integration test:** chạy migration trên MySQL đúng phiên bản, seed fixture và xác minh schema.
4. **Compatibility test:** chạy ứng dụng cũ/mới với schema expand/migrate theo ma trận hỗ trợ.
5. **Performance test:** chạy DDL/backfill và query quan trọng trên dataset đại diện.
6. **Backup/restore drill:** chạy định kỳ hoặc trước release lớn trên môi trường riêng.
7. **Replication/failover exercise:** chạy theo lịch trên staging hoặc môi trường diễn tập.
8. **Release gate:** chỉ cho phép triển khai khi các tiêu chí bắt buộc đạt và có bằng chứng.

Không nhất thiết chạy full restore và failover cho mọi commit. Unit/integration test chạy thường xuyên; restore drill, performance test và failover exercise chạy theo lịch, trước thay đổi hạ tầng hoặc trước release có rủi ro.

### 8.2. Tiêu chí chặn release

Một số điều kiện có thể dùng làm release gate:

- Migration không nâng được từ mọi schema version còn hỗ trợ.
- Checksum migration sai hoặc lịch sử migration không nhất quán.
- Invariant dữ liệu thất bại.
- DDL vượt thời gian lock hoặc gây replication lag quá ngưỡng.
- Backup chưa có bằng chứng restore thành công trong thời hạn chính sách.
- Binary log archive thiếu đoạn cần thiết cho RPO.
- Replica có lỗi IO/SQL hoặc không bắt kịp theo tiêu chí.
- Failover không fencing được primary cũ hoặc client không reconnect.
- RPO/RTO đo được vượt mục tiêu.

Mỗi gate cần xác định chủ sở hữu, log bằng chứng và quy trình xử lý khi thất bại. Không đánh dấu PASS chỉ vì job không trả exit code lỗi nếu chưa kiểm tra hậu điều kiện.

## 9. Sự cố kiểm thử thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Migration chạy ở CI nhưng lỗi trên staging | Khác phiên bản, collation, SQL mode, dữ liệu hoặc quyền | Đồng bộ cấu hình test và bổ sung fixture đại diện |
| Migration thành công nhưng dữ liệu sai | Backfill bỏ sót, mapping sai hoặc xử lý NULL không đúng | Kiểm tra invariant, batch range và đối soát dữ liệu |
| DDL làm replica lag tăng mạnh | Table rebuild, index build hoặc batch quá lớn | Đo DDL trên bản sao, điều chỉnh batch và cửa sổ chạy |
| Restore có file nhưng MySQL không khởi động | Backup thiếu file, keyring, plugin hoặc prepare sai | Kiểm tra manifest, error log và tài liệu công cụ |
| PITR đi quá transaction lỗi | Mốc dừng theo timestamp không đủ chính xác | Xác định event/transaction boundary và kiểm tra file replay |
| Replica Running nhưng dữ liệu không khớp | Lọc replication, giao dịch thiếu, kiểm tra khác thời điểm | Đối chiếu GTID, filter và checksum tại cùng mốc |
| Failover tạo hai primary | Không fencing được node cũ hoặc endpoint chuyển không đồng nhất | Dừng ghi, cô lập node, xác định nguồn dữ liệu chuẩn và khôi phục topology |
| Ứng dụng không kết nối sau promote | Pool giữ socket cũ, DNS/proxy chưa cập nhật | Kiểm tra route, connection pool, DNS và reconnect |
| Retry tạo giao dịch trùng | Không có idempotency hoặc kết quả commit không xác định | Dùng idempotency key và đối soát trạng thái trước retry |
| RTO vượt mục tiêu | Restore, promote, DNS hoặc kiểm tra thủ công quá lâu | Đo từng bước, tự động hóa runbook và diễn tập lại |

Không sửa kết quả test bằng cách bỏ qua lỗi replication hoặc giảm mức kiểm tra dữ liệu. Hãy lưu lại trạng thái lỗi để tìm nguyên nhân gốc.

## 10. Runbook và bằng chứng kiểm thử

Mỗi lần diễn tập cần lưu một bộ hồ sơ:

- Mục tiêu, phạm vi, người chịu trách nhiệm và thời gian chạy.
- Phiên bản MySQL, công cụ backup, driver, migration tool và ứng dụng.
- Seed/fixture version và dữ liệu đầu vào.
- GTID set, binlog file/position và mốc PITR.
- Migration history, checksum và DDL thực tế.
- Backup manifest, checksum và log restore.
- `SHOW REPLICA STATUS` trước/sau test và kết quả đối soát.
- Mốc T0–T5, RPO/RTO và lỗi phát sinh.
- Quyết định PASS/FAIL, vấn đề tồn đọng và hành động tiếp theo.

Một báo cáo ngắn nên trả lời: test nào đã chạy, môi trường nào, dữ liệu nào, tiêu chí nào đạt/chưa đạt, kết quả đo là bao nhiêu và ai chấp nhận rủi ro còn lại.

## 11. Checklist tổng hợp

### Migration

- [ ] Test từ database rỗng và mọi schema version còn hỗ trợ.
- [ ] Test dữ liệu biên, NULL, Unicode, duplicate và dữ liệu lớn.
- [ ] Kiểm tra schema, index, constraint và dependency sau DDL.
- [ ] Đối soát invariant trước/sau backfill.
- [ ] Test tương thích ứng dụng cũ và mới.
- [ ] Đo metadata lock, DDL duration, I/O và replication lag.
- [ ] Kiểm tra failure recovery khi migration dừng giữa chừng.

### Backup/restore

- [ ] Kiểm tra full/logical/physical backup theo phạm vi.
- [ ] Xác minh checksum, manifest và binary log archive.
- [ ] Restore trên máy chủ cô lập.
- [ ] Phục hồi PITR đến mốc có transaction marker.
- [ ] Kiểm tra user, role, grant, keyring và TLS.
- [ ] Đối soát cấu trúc, dữ liệu và nghiệp vụ.
- [ ] Đo RPO/RTO thực tế.

### Replication

- [ ] Xác nhận GTID, binlog, server_id và tài khoản replication.
- [ ] Test transaction từ source đến replica.
- [ ] Test catch-up và đo lag dưới tải.
- [ ] Test network interruption, restart và applier error.
- [ ] Kiểm tra DDL/filter và giao dịch nhiều schema.
- [ ] Đối soát checksum tại cùng mốc dữ liệu.
- [ ] Xác nhận ứng dụng xử lý replica lag đúng yêu cầu.

### Failover

- [ ] Test switchover có kế hoạch.
- [ ] Test mất primary trong staging.
- [ ] Fencing primary cũ trước khi mở ghi trên node mới.
- [ ] Chọn replica dựa trên GTID/dữ liệu thực tế.
- [ ] Chuyển Router/proxy/DNS và kiểm tra client reconnect.
- [ ] Kiểm tra retry/idempotency và giao dịch không rõ kết quả commit.
- [ ] Tái đồng bộ node cũ trước khi đưa lại vào topology.
- [ ] Đo RPO/RTO và lưu bằng chứng.

## 12. Tự kiểm tra

**Tình huống 1:** Migration thêm cột và backfill chạy thành công trên database rỗng, nhưng production upgrade từ schema cũ có dữ liệu lịch sử. Vì sao test hiện tại chưa đủ?

**Gợi ý:** Database rỗng không có dữ liệu NULL, giá trị biên, duplicate, phân bố lệch hoặc số lượng lớn. Cần test upgrade từ các version được hỗ trợ với fixture và dữ liệu đại diện, rồi đối soát invariant.

**Tình huống 2:** Job backup trả exit code 0 và file có kích thước lớn. Có thể đánh dấu backup đã được xác minh không?

**Gợi ý:** Chưa. Cần kiểm tra manifest/checksum, restore trên môi trường cô lập, mở tablespace, kiểm tra dữ liệu, quyền và ứng dụng.

**Tình huống 3:** Replica báo `Replica_IO_Running=Yes` nhưng `Replica_SQL_Running=No`. Có thể dùng replica này làm primary mới không?

**Gợi ý:** Chưa. Receiver có thể nhận log nhưng applier không áp dụng được. Phải kiểm tra lỗi SQL, GTID và dữ liệu thiếu trước khi quyết định promote.

**Tình huống 4:** Primary bị mất và replica có GTID set cũ hơn. Failover có thể mất giao dịch không?

**Gợi ý:** Có. Với asynchronous replication, một số giao dịch đã commit trên primary có thể chưa được replica nhận. Cần xác định RPO thực tế và đối soát các giao dịch có thể mất.

**Tình huống 5:** Sau promote, ứng dụng vẫn ghi vào primary cũ vì một số connection pool chưa reconnect. Rủi ro là gì?

**Gợi ý:** Có thể hình thành split-brain với hai node cùng nhận ghi. Cần fencing primary cũ ở tầng database và mạng, chuyển endpoint, loại connection cũ và chỉ mở traffic sau khi xác nhận một primary duy nhất.

**Tình huống 6:** Ứng dụng mất kết nối ngay sau khi gửi COMMIT. Có thể retry INSERT ngay không?

**Gợi ý:** Không nên retry mù quáng vì server có thể đã commit nhưng client chưa nhận phản hồi. Dùng idempotency key hoặc truy vấn xác minh trạng thái trước khi gửi lại.

## 13. Điểm cần ghi nhớ

- Kiểm thử migration phải bao phủ database rỗng, mọi schema version còn hỗ trợ, dữ liệu biên và dữ liệu lớn.
- MySQL thật cần được dùng cho integration test về DDL, transaction, constraint, locking và optimizer.
- DDL có implicit commit; không giả định migration có thể rollback nguyên tử.
- Backup chỉ được xác minh sau khi restore và kiểm tra dữ liệu, quyền, ứng dụng.
- PITR cần full backup cùng chuỗi binary log liên tục và mốc dừng chính xác.
- Replication Running không chứng minh dữ liệu đã khớp; kiểm tra GTID, applier, lag và invariant.
- Switchover/failover phải fencing primary cũ trước khi mở ghi trên primary mới để tránh split-brain.
- Asynchronous replication có thể mất giao dịch chưa đến replica; đo RPO thay vì giả định zero data loss.
- Ứng dụng cần reconnect và retry an toàn sau failover; giao dịch có kết quả commit không xác định phải được đối soát.
- Ghi nhận RPO/RTO, log, checksum, GTID, migration version và kết quả test để runbook có thể được diễn tập lại.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: Testing](https://dev.mysql.com/doc/refman/8.4/en/testing.html) — thông tin về kiểm thử MySQL.
- [MySQL 8.4 Reference Manual: Replication](https://dev.mysql.com/doc/refman/8.4/en/replication.html) — cấu hình, giám sát và xử lý replication.
- [MySQL 8.4 Reference Manual: GTID Auto-Positioning](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids-auto-positioning.html) — đồng bộ giao dịch theo GTID.
- [MySQL 8.4 Reference Manual: Point-in-Time Recovery](https://dev.mysql.com/doc/refman/8.4/en/point-in-time-recovery.html) — phục hồi đến một mốc bằng binary log.
- [MySQL 8.4 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html) — logical backup và snapshot.
- [MySQL 8.4 Reference Manual: Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html) — thuật toán DDL và mức khóa.
- [Testcontainers for Java: MySQL Module](https://java.testcontainers.org/modules/databases/mysql/) — chạy MySQL thật trong integration test.
- [Flyway Documentation: Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations) — quản lý version và lịch sử migration.
- [Liquibase Documentation: Change Types](https://docs.liquibase.com/change-types/home.html) — mô hình hóa thay đổi schema.
