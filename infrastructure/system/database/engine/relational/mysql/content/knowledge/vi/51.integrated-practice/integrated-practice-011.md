# Triển khai thay đổi schema trên bảng lớn có ứng dụng đang hoạt động

## Mục tiêu

Sau bài thực hành này, bạn có thể:

- Lập kế hoạch thay đổi schema MySQL trên bảng có hàng chục hoặc hàng trăm triệu hàng mà ứng dụng vẫn nhận traffic.
- Phân biệt online DDL, instant DDL và công cụ online schema change.
- Dùng expand/contract để giữ tương thích trong rolling deployment.
- Thiết kế backfill theo batch có checkpoint, idempotency và khả năng tiếp tục sau sự cố.
- Đánh giá metadata lock, transaction dài, replication lag, dung lượng đĩa và tác động đến workload.
- Xác định điều kiện dừng, rollback point, forward fix và bước contract.
- Xây dựng runbook có tiêu chí go/no-go, quan sát và đối soát sau triển khai.

## 1. Bối cảnh thực hành

Một hệ thống thương mại điện tử chạy MySQL InnoDB 8.4. Bảng `orders` có khoảng 120 triệu hàng, tăng thêm vài trăm nghìn hàng mỗi ngày. API, worker và báo cáo đang đọc/ghi bảng liên tục. Nhóm phát triển muốn đổi tên cột `status` thành `order_status`, đồng thời tăng độ dài từ `VARCHAR(24)` lên `VARCHAR(32)` để thống nhất quy ước trạng thái mới.

Trong giai đoạn hai cột cùng tồn tại, giả định các giá trị trạng thái vẫn nằm trong giới hạn 24 ký tự và thuộc domain mà phiên bản V1 hiểu được. Nếu cần ghi giá trị dài hơn hoặc thêm trạng thái mới, phải mở rộng cột cũ và cập nhật khả năng tương thích của mọi reader cũ trước khi phát giá trị đó; chỉ mở rộng kiểu cột ở database chưa đủ nếu code V1 vẫn validate enum/domain cũ.

Schema hiện tại:

~~~sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(24) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created (customer_id, created_at)
) ENGINE=InnoDB;
~~~

Các ràng buộc vận hành:

- API phải tiếp tục phục vụ request trong suốt quá trình.
- Có nhiều instance ứng dụng được cập nhật theo rolling deployment.
- Worker và cron job có thể chạy lâu hơn thời gian deploy API.
- Replica được dùng cho báo cáo và một số truy vấn đọc.
- Không được bỏ mất cập nhật đơn hàng trong lúc backfill.
- Có thể dừng migration nếu latency, lock wait hoặc replication lag vượt ngưỡng.

Thay đổi này có vẻ đơn giản nếu nhìn từ DDL: thêm cột mới rồi bỏ cột cũ. Nhưng trên bảng 120 triệu hàng, việc chọn thuật toán DDL, chuyển đổi dữ liệu, phối hợp nhiều phiên bản ứng dụng và xử lý lỗi mới là phần quyết định thành công.

## 2. Nguyên tắc thiết kế trước khi chạy DDL

Thay đổi schema trên bảng lớn cần được xem như một quy trình phát hành nhiều giai đoạn, không phải một câu ALTER TABLE đơn lẻ.

Một quy trình an toàn thường gồm:

1. **Discover:** kiểm kê ứng dụng, query, job và consumer phụ thuộc schema cũ.
2. **Prepare:** kiểm thử DDL, dung lượng, metadata lock, replication và phương án phục hồi.
3. **Expand:** bổ sung cột/index/đối tượng mới theo cách tương thích ngược.
4. **Deploy compatible code:** phát hành code có thể đọc/ghi cấu trúc cũ và mới.
5. **Backfill:** chuyển dữ liệu cũ sang cấu trúc mới theo batch.
6. **Validate:** đối soát dữ liệu và hành vi ứng dụng.
7. **Switch:** chuyển dần luồng đọc sang cấu trúc mới.
8. **Contract:** loại bỏ phụ thuộc và xóa cấu trúc cũ sau khi đã hết consumer cũ.

Không bỏ qua bước kiểm kê. Một cột có thể được dùng bởi API chính, nhưng cũng có thể xuất hiện trong cron job, export CSV, stored procedure, view, trigger, dashboard BI, ETL hoặc truy vấn ad hoc.

### 2.1. Lập danh sách phụ thuộc

Trước khi sửa schema, tìm tất cả nơi tham chiếu `orders.status`:

- Entity/ORM mapping và native SQL trong ứng dụng.
- API instance, worker, queue consumer, cron job và batch import.
- Stored procedure, function, trigger, view và event.
- Báo cáo, dashboard, ETL/CDC và data warehouse.
- Script vận hành, công cụ quản trị và truy vấn thủ công.
- Replica, delayed replica, backup/restore pipeline và CDC consumer.

Query log hoặc Performance Schema có thể hỗ trợ tìm truy vấn đang chạy, nhưng không chứng minh rằng một job định kỳ sẽ không chạy lại trong tương lai. Kết hợp source search, deployment inventory, lịch job, tracing và trao đổi với chủ sở hữu hệ thống.

### 2.2. Ma trận tương thích ứng dụng/schema

Thiết kế phiên bản theo hướng giữ cấu trúc cũ trong toàn bộ thời gian còn code phụ thuộc:

| Phiên bản | Đọc | Ghi | Điều kiện schema |
|---|---|---|---|
| V1 hiện tại | status | status | Schema cũ |
| V2 tương thích | status | Cả status và order_status | Đã expand |
| V3 chuyển đọc | order_status | Cả hai cột | Backfill đã được xác minh |
| V4 chỉ dùng mới | order_status | order_status | Có thể contract sau khi V2/V3 và mọi consumer cũ đã dừng |

V2 và V3 có thể cùng tồn tại sau khi cột mới đã được thêm: cả hai đều ghi hai cột, chỉ khác cột dùng để đọc. Khi V4 bắt đầu chỉ ghi cột mới, cột cũ có thể trở nên stale đối với những hàng được cập nhật bởi V4. Đây là điểm rollback sang code chỉ đọc status không còn an toàn. Hãy coi thời điểm chuyển sang write-new-only là một quyết định có chủ đích, sau giai đoạn quan sát và phê duyệt.

## 3. Đánh giá phương án thay đổi bảng lớn

Trước khi chọn cách chạy DDL, cần biết thao tác cụ thể có thể dùng thuật toán nào trên đúng phiên bản MySQL, engine và cấu trúc bảng.

### 3.1. Ba thuật toán InnoDB thường gặp

| Thuật toán | Hành vi | Tác động cần dự kiến |
|---|---|---|
| INSTANT | Thay đổi metadata cho thao tác được hỗ trợ, không rebuild toàn bộ bảng | Nhanh hơn nhiều nhưng vẫn cần metadata lock; có giới hạn theo phiên bản và cấu trúc |
| INPLACE | Storage engine thực hiện thay đổi; có thể scan hoặc rebuild nội bộ tùy thao tác | Có thể cho phép DML đồng thời nhưng vẫn tốn I/O, CPU và dung lượng |
| COPY | Tạo bản sao bảng, sao chép dữ liệu rồi thay thế | Có thể tốn nhiều dung lượng và gây hạn chế ghi đáng kể |

INPLACE không có nghĩa là không copy/rebuild dữ liệu. LOCK=NONE cũng không có nghĩa là không cần bất kỳ loại khóa nào. Khả năng hỗ trợ phụ thuộc loại DDL, phiên bản MySQL, InnoDB, row format, index, foreign key và các thuộc tính bảng.

### 3.2. Kiểm tra khả năng hỗ trợ trước

Nếu muốn thêm cột mới ở cuối bảng và phiên bản/điều kiện hỗ trợ instant add column, có thể yêu cầu MySQL dùng INSTANT:

~~~sql
SET SESSION lock_wait_timeout = 5;

ALTER TABLE orders
    ADD COLUMN order_status VARCHAR(32) NULL,
    ALGORITHM=INSTANT;
~~~

ALGORITHM=INSTANT giúp migration thất bại rõ ràng nếu thao tác không được hỗ trợ thay vì âm thầm chọn một phương án rebuild tốn kém hơn. Tuy nhiên, không được suy luận rằng mọi thao tác ADD COLUMN đều instant. Kiểm tra giới hạn của phiên bản, số row version instant, vị trí cột và cấu trúc thực tế; chạy thử trên bản sao gần production.

Nếu cần tạo index:

~~~sql
ALTER TABLE orders
    ADD INDEX idx_orders_order_status_created
        (order_status, created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
~~~

Với InnoDB và thao tác được hỗ trợ, LOCK=NONE cho phép DML đồng thời trong phần lớn thời gian tạo index. Nếu server không hỗ trợ tổ hợp này, câu lệnh có thể thất bại. Hãy để migration báo lỗi rõ ràng thay vì tự chuyển sang một kiểu khóa gây downtime ngoài dự kiến.

Tạo index trên 120 triệu hàng vẫn là công việc nặng: cần đọc dữ liệu, sắp xếp, ghi index, dùng I/O và có thể làm tăng replication lag. Online DDL giúp giảm thời gian chặn ghi; nó không biến công việc tạo index thành miễn phí.

### 3.3. Khi nào cân nhắc online schema change tool?

Nếu DDL trực tiếp cần rebuild bảng, thời gian khóa không đáp ứng yêu cầu hoặc cần kiểm soát tốc độ copy, có thể đánh giá công cụ online schema change:

| Công cụ | Cách hoạt động khái quát | Điểm cần đánh giá |
|---|---|---|
| gh-ost | Tạo ghost table, copy theo chunk và áp dụng thay đổi mới từ binlog trước khi cut-over | Cần binlog phù hợp và khóa duy nhất ổn định; không hỗ trợ foreign key theo cách tổng quát; cần kiểm tra trigger/topology |
| pt-online-schema-change | Tạo bảng shadow, copy theo chunk và dùng trigger để đồng bộ thay đổi | Cần đánh giá trigger hiện có, foreign key handling, quyền và tải trigger trên mỗi DML |
| MySQL online DDL | Dùng cơ chế của InnoDB cho thao tác được hỗ trợ | Đơn giản hơn khi hỗ trợ đúng yêu cầu, nhưng có thể vẫn scan/rebuild và cần MDL |

Không chạy công cụ copy bảng trên production chỉ bằng lệnh mặc định. Phải thử với schema có cùng primary key, foreign key, trigger, generated column, partitioning, replication topology và tốc độ ghi tương tự.

Với gh-ost, kiểm tra yêu cầu binlog, row image, unique key và topology. Với pt-online-schema-change, đánh giá cách xử lý foreign key và trigger hiện có; trigger đồng bộ làm tăng chi phí mỗi lần ghi. Cả hai đều cần dung lượng đĩa cho bảng shadow, index, binlog và khoảng trống vận hành.

## 4. Chuẩn bị trước cửa sổ triển khai

Không bắt đầu khi chưa có baseline và tiêu chí dừng. Ghi nhận trạng thái bình thường trước migration để phân biệt tác động của DDL với biến động sẵn có.

### 4.1. Thu thập baseline

Ghi nhận ít nhất:

- Số hàng và dung lượng bảng/index.
- Tốc độ INSERT/UPDATE/DELETE và query latency p50/p95/p99.
- CPU, IOPS, throughput đĩa và dung lượng trống.
- Buffer pool usage/hit rate.
- Active connections, thread running và transaction dài.
- Lock wait/deadlock.
- Replica lag và tốc độ apply binlog.
- Binlog generation rate và retention.
- Error rate, timeout và connection pool saturation của ứng dụng.

Không chỉ ghi một ảnh chụp tại một thời điểm. Lấy baseline trong khoảng thời gian có giờ cao điểm và batch job để biết giới hạn thực tế.

### 4.2. Kiểm tra transaction dài và metadata lock

Transaction dài có thể giữ metadata lock tương thích với thao tác đọc/ghi, khiến ALTER chờ. Khi DDL đang chờ metadata lock, truy vấn mới có thể bị xếp hàng phía sau và tạo nghẽn bất ngờ.

Kiểm tra transaction InnoDB:

~~~sql
SELECT
    trx_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_mysql_thread_id,
    trx_state,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Kiểm tra metadata lock trên bảng:

~~~sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'sales_app'
  AND OBJECT_NAME = 'orders';
~~~

Có thể kết hợp performance_schema.threads, SHOW PROCESSLIST hoặc view sys.schema_table_lock_waits để tìm session đang giữ/chờ lock. Trước khi chạy DDL, xác định ai chịu trách nhiệm xử lý transaction lâu và điều kiện nào cho phép kill session. Không kill session tùy tiện khi chưa hiểu transaction đang làm gì.

### 4.3. Kiểm tra dung lượng và log

Nếu dùng online schema change hoặc DDL rebuild, cần dự trù:

- Bảng gốc và bảng shadow/copy.
- Secondary index mới.
- Temporary files và sort buffer theo cách MySQL thực hiện DDL.
- Redo/undo và binary log phát sinh.
- Dung lượng replica và backup.
- Headroom để ứng dụng tiếp tục ghi trong thời gian copy.

Nếu bảng gốc 500 GB, không thể giả định thêm một bảng shadow 500 GB cùng index sẽ vừa trên volume còn trống 200 GB. Tính cả tốc độ tăng dữ liệu trong lúc migration.

### 4.4. Backup và phục hồi

Trước thay đổi có rủi ro cao:

- Xác nhận backup gần nhất thành công.
- Kiểm tra binary log/PITR còn đủ để phục hồi tới thời điểm cần.
- Kiểm tra backup có thể restore trên môi trường khác.
- Ghi rõ RPO/RTO và người chịu trách nhiệm phục hồi.
- Xác định dữ liệu mới phát sinh sau backup được bảo toàn bằng cách nào.

Backup là phương án phục hồi dữ liệu, không phải nút rollback nhanh cho một DDL đã chạy. Restore 500 GB có thể mất nhiều giờ và yêu cầu điều phối traffic; vì vậy, rollback ứng dụng và forward fix thường là phương án xử lý đầu tiên khi dữ liệu nguồn vẫn còn.

## 5. Giai đoạn Expand: mở rộng cột cũ và thêm cột mới

Nếu yêu cầu tăng độ dài từ 24 lên 32 ký tự, hãy mở rộng cột hiện tại trước để các phiên bản tương thích có thể tiếp tục ghi cùng dữ liệu trong giai đoạn dual-write:

~~~sql
SET SESSION lock_wait_timeout = 5;

ALTER TABLE orders
    MODIFY COLUMN status VARCHAR(32) NOT NULL,
    ALGORITHM=INPLACE,
    LOCK=NONE;
~~~

Chỉ chạy câu lệnh với ALGORITHM=INPLACE, LOCK=NONE nếu đã xác nhận thao tác này được hỗ trợ trên đúng phiên bản và cấu trúc bảng. Nếu server từ chối tổ hợp thuật toán/lock, dừng để đánh giá online DDL hoặc công cụ copy bảng; không bỏ các clause rồi chạy lại theo mặc định trên production. Việc nới VARCHAR có thể vẫn cần scan/rebuild tùy điều kiện.

Sau khi cột cũ đã được mở rộng và kiểm tra, thêm order_status nullable. V1 vẫn chỉ dùng status nên tiếp tục hoạt động:

~~~sql
SET SESSION lock_wait_timeout = 5;

ALTER TABLE orders
    ADD COLUMN order_status VARCHAR(32) NULL,
    ALGORITHM=INSTANT;
~~~

Nếu lệnh instant thất bại, dừng và xác định lý do. Không bỏ ALGORITHM=INSTANT rồi chạy lại ngay trên production; điều đó có thể khiến MySQL chọn thuật toán nặng hơn. Thử trên bản sao và lên kế hoạch online DDL hoặc công cụ chuyên dụng.

Sau expand, kiểm tra:

~~~sql
SHOW CREATE TABLE orders;

SELECT
    COUNT(*) AS total_rows,
    SUM(order_status IS NULL) AS rows_without_new_status
FROM orders;
~~~

Truy vấn COUNT/SUM trên 120 triệu hàng có thể quét bảng và tạo tải. Chỉ chạy khi có ngân sách I/O, hoặc thay bằng thống kê theo chunk/ước lượng đã được chấp thuận. Ngay sau khi thêm cột nullable, việc mọi hàng có order_status IS NULL là trạng thái dự kiến.

Không thêm NOT NULL ngay ở bước này nếu hàng cũ chưa có giá trị. Cần tách việc bổ sung cấu trúc khỏi việc chuyển đổi dữ liệu.

Trong thời gian V1 còn hoạt động, ứng dụng vẫn phải gửi các giá trị thuộc domain cũ. Sau khi mọi reader cũ đã được drain, nhóm mới được phép phát các giá trị dài hơn hoặc domain mới theo kế hoạch tương thích đã kiểm thử.

## 6. Deploy V2: dual-write tương thích

V2 tiếp tục đọc status nhưng ghi cả status và order_status trong cùng một câu SQL hoặc cùng transaction.

Ví dụ cập nhật:

~~~sql
UPDATE orders
SET status = 'SHIPPED',
    order_status = 'SHIPPED',
    updated_at = NOW(6)
WHERE id = 90001;
~~~

Ví dụ tạo đơn:

~~~sql
INSERT INTO orders (
    customer_id,
    status,
    order_status,
    total_amount,
    created_at,
    updated_at
)
VALUES (
    501,
    'PENDING',
    'PENDING',
    125.50,
    NOW(6),
    NOW(6)
);
~~~

Dual-write phải nguyên tử. Tránh hai thao tác ghi riêng biệt không có transaction, vì process có thể dừng sau khi cập nhật cột cũ nhưng trước khi cập nhật cột mới.

Trong thời gian rolling deployment, V1 vẫn có thể ghi riêng status. Vì vậy, chưa được xem dữ liệu mới đã ổn định và bắt đầu switch read. Hãy chờ toàn bộ writer V1 được drain:

- API instance cũ đã kết thúc.
- Worker và consumer cũ đã được restart/drain.
- Cron job cũ đã chạy xong hoặc được cập nhật.
- Script import/maintenance cũ đã được thay thế.
- Không còn process có thể phát SQL chỉ ghi status.

Deployment pipeline báo thành công chưa đủ để chứng minh tất cả writer cũ đã dừng. Dùng version heartbeat, instance inventory, job registry và log truy vấn để xác nhận.

### 6.1. Nếu không thể drain writer cũ

Nếu một hệ thống bên ngoài không thể nâng cấp ngay, phải có cơ chế đồng bộ rõ ràng trước khi backfill/switch. Có thể đánh giá trigger tạm thời hoặc adapter service, nhưng phải:

- Xác định một nguồn sự thật trong từng giai đoạn.
- Xử lý cả INSERT, UPDATE và DELETE nếu liên quan.
- Tránh vòng lặp dual-write giữa trigger và ứng dụng.
- Kiểm tra trigger hiện có và thứ tự thực thi.
- Đo overhead trên mọi DML.
- Có ngày kết thúc và kế hoạch xóa cơ chế tạm.

Không giả định một trigger đơn giản sẽ xử lý đúng mọi writer, bulk import, replication và schema evolution.

## 7. Backfill 120 triệu hàng theo batch

Sau khi mọi writer đã dual-write, các hàng cũ vẫn có order_status IS NULL. Backfill sẽ chép giá trị từ status sang cột mới.

### 7.1. Dùng keyset/range theo primary key

Không dùng LIMIT ... OFFSET lớn vì MySQL có thể phải đọc và bỏ qua ngày càng nhiều hàng. Dùng khoảng khóa chính:

~~~sql
UPDATE orders
SET order_status = status
WHERE id > 0
  AND id <= 10000
  AND order_status IS NULL;
~~~

Batch tiếp theo xử lý khoảng 10000 đến 20000, rồi tiếp tục. Trong job thực tế, low_id, high_id và checkpoint được lưu bền vững.

Điều kiện order_status IS NULL giúp job chạy lại an toàn và tránh ghi đè giá trị đã được ứng dụng dual-write. Vì cột status trong ví dụ là NOT NULL, NULL ở cột mới biểu thị hàng chưa được backfill. Nếu cột nguồn có thể NULL, cần một cờ migration riêng hoặc quy tắc phân biệt NULL hợp lệ với hàng chưa xử lý.

### 7.2. Transaction ngắn cho mỗi batch

Mỗi batch nên chạy trong transaction riêng:

~~~sql
START TRANSACTION;

UPDATE orders
SET order_status = status
WHERE id > 10000
  AND id <= 20000
  AND order_status IS NULL;

COMMIT;
~~~

Kích thước 10.000 hàng chỉ là điểm khởi đầu. Chọn batch size dựa trên thời gian thực thi, lock wait, undo/redo, I/O, CPU và replica lag. Có thể bắt đầu với 1.000–5.000 hàng, đo rồi điều chỉnh; không có một con số tối ưu cố định.

Transaction ngắn giúp giới hạn lượng công việc cần rollback và thời gian giữ row lock. Không chạy một UPDATE duy nhất cho toàn bộ 120 triệu hàng nếu hệ thống cần duy trì latency ổn định.

### 7.3. Checkpoint và khả năng chạy lại

Một bảng điều khiển migration có thể lưu tiến độ:

~~~sql
CREATE TABLE schema_backfill_progress (
    migration_name VARCHAR(100) NOT NULL PRIMARY KEY,
    last_id BIGINT UNSIGNED NOT NULL,
    max_id BIGINT UNSIGNED NOT NULL,
    rows_updated BIGINT UNSIGNED NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    updated_at TIMESTAMP(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;
~~~

Ví dụ bản ghi:

~~~sql
SET @orders_max_id = (
    SELECT COALESCE(MAX(id), 0)
    FROM orders
);

INSERT INTO schema_backfill_progress (
    migration_name, last_id, max_id, rows_updated, status
)
VALUES (
    'orders_order_status_v1', 0, @orders_max_id, 0, 'RUNNING'
);
~~~

Job thực hiện theo vòng lặp:

1. Sau khi mọi writer V1 đã drain, lấy một high-water mark bằng MAX(id) và lưu lại cho lần chạy này.
2. Đọc last_id.
3. Tính high_id tiếp theo theo chunk size, không vượt high-water mark.
4. Mở transaction.
5. Chạy UPDATE trong range.
6. Cập nhật checkpoint và số hàng cập nhật trong cùng transaction.
7. Commit.
8. Nghỉ hoặc điều chỉnh tốc độ theo metric.
9. Tiếp tục cho đến khi hết range.

Checkpoint phải được cập nhật cùng transaction với batch. Nếu cập nhật checkpoint trước khi UPDATE commit, job có thể bỏ qua dữ liệu khi restart. Nếu batch commit nhưng checkpoint không commit, job có thể chạy lại; điều kiện idempotent order_status IS NULL khiến việc chạy lại an toàn.

Các hàng mới được tạo sau high-water mark đã được V2 dual-write nên không cần kéo dài backfill để đuổi theo ID tăng liên tục. Không dùng rows_updated làm bằng chứng duy nhất rằng tất cả hàng đã được xử lý. Có thể có khoảng trống ID do delete hoặc auto increment. Sau khi đến high-water mark, vẫn cần truy vấn kiểm tra hàng còn NULL hoặc mismatch.

Lấy high-water mark bằng truy vấn trên primary key:

~~~sql
SELECT COALESCE(MAX(id), 0) AS max_id
FROM orders;
~~~

Lưu max_id cùng migration metadata để mọi lần resume dùng cùng một giới hạn. Nếu job cần xử lý thêm dữ liệu được tạo trong lúc chạy, hãy xác minh rằng mọi writer đều dual-write; sau đó có thể chạy một lượt đối soát bổ sung theo range thay vì thay đổi high-water mark tùy tiện.

### 7.4. Pseudocode cho worker backfill

~~~java
while (true) {
    Progress progress = progressRepository.load("orders_order_status_v1");
    long lowId = progress.lastId();
    long maxId = progress.maxId();
    long highId = Math.min(lowId + chunkSize, maxId);

    transactionTemplate.executeWithoutResult(status -> {
        int updated = jdbcTemplate.update("""
            UPDATE orders
               SET order_status = status
             WHERE id > ?
               AND id <= ?
               AND order_status IS NULL
            """, lowId, highId);

        progressRepository.advance(
            "orders_order_status_v1",
            highId,
            updated
        );
    });

    if (highId == maxId) {
        break;
    }

    throttleIfNeeded();
}
~~~

Đây là pseudocode để thể hiện thứ tự công việc, không phải implementation hoàn chỉnh. Cần xử lý checkpoint không khớp migration version/high-water mark, lỗi deadlock, lock wait timeout, retry có giới hạn, cancellation, checkpoint bị cập nhật bởi worker khác và việc khóa tiến độ để không chạy hai worker trùng range.

Nếu dùng nhiều worker, chia các range không chồng lấn và lưu lease/ownership cho từng range. Không để hai worker cùng tăng một checkpoint duy nhất mà không có cơ chế đồng bộ.

### 7.5. Tác động lên replica và workload

Backfill tạo UPDATE cho nhiều hàng nên sinh redo, undo và binary log. Replica phải apply các thay đổi này. Nếu tốc độ backfill cao hơn khả năng apply, replication lag sẽ tăng.

Điều chỉnh tốc độ dựa trên:

- Replica lag và tốc độ catch-up.
- CPU, I/O và disk queue.
- Row lock wait/deadlock.
- Latency p95/p99 của API.
- Số connection đang chờ.
- Dung lượng undo tablespace và binlog.

Khi vượt ngưỡng đã định trước, giảm chunk size, tăng thời gian nghỉ hoặc pause job. Không tiếp tục chỉ vì batch hiện tại vẫn thành công.

## 8. Validate dữ liệu sau backfill

Không chuyển đọc sang cột mới chỉ vì job báo COMPLETED. Phải đối soát dữ liệu theo các điều kiện đã xác định.

### 8.1. Kiểm tra hàng còn thiếu

~~~sql
SELECT COUNT(*) AS missing_rows
FROM orders
WHERE order_status IS NULL;
~~~

### 8.2. Kiểm tra mismatch

~~~sql
SELECT COUNT(*) AS mismatch_rows
FROM orders
WHERE NOT (order_status <=> status);
~~~

Toán tử <=> so sánh NULL-safe. Với ví dụ này hai cột phải có cùng giá trị. Nếu mapping mới thay đổi domain hoặc chuẩn hóa giá trị, hãy dùng biểu thức mapping đã định nghĩa thay vì so sánh trực tiếp.

Trên bảng lớn, hai truy vấn COUNT có thể quét phần lớn hoặc toàn bộ bảng. Chạy theo range khóa chính, giới hạn concurrency và quan sát I/O. Có thể lưu kết quả đối soát theo chunk để biết range nào chưa đạt.

### 8.3. Kiểm tra phân bố nghiệp vụ

So sánh số lượng theo trạng thái:

~~~sql
SELECT status, COUNT(*) AS row_count
FROM orders
GROUP BY status
ORDER BY status;

SELECT order_status, COUNT(*) AS row_count
FROM orders
GROUP BY order_status
ORDER BY order_status;
~~~

Kết quả phải tương đương theo mapping. Nếu bảng đang tiếp tục nhận ghi, hai truy vấn chạy ở hai thời điểm khác nhau có thể có chênh lệch hợp lệ. Hãy đối soát trong cùng consistent snapshot hoặc theo range/version và ghi rõ cách tính phần dữ liệu đang thay đổi.

### 8.4. Đối soát theo range

Ví dụ kiểm tra từng đoạn ID:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(order_status IS NULL) AS missing_rows,
    SUM(NOT (order_status <=> status)) AS mismatch_rows
FROM orders
WHERE id > 1000000
  AND id <= 1100000;
~~~

Lưu lại kết quả từng range, timestamp, max ID và migration version. Khi toàn bộ range đạt điều kiện, chạy một lượt xác nhận cuối theo phương pháp đã được phê duyệt.

### 8.5. Thêm constraint NOT NULL sau khi dữ liệu sạch

Nếu schema đích yêu cầu order_status bắt buộc, chỉ thêm NOT NULL sau khi mọi hàng đã được backfill và các writer đang dual-write luôn cung cấp giá trị:

~~~sql
ALTER TABLE orders
    MODIFY COLUMN order_status VARCHAR(32) NOT NULL,
    ALGORITHM=INPLACE,
    LOCK=NONE;
~~~

Đây là một DDL riêng, phải rehearsal trên đúng phiên bản và schema. Thêm NOT NULL có thể cần kiểm tra dữ liệu hoặc rebuild tùy điều kiện. Nếu không hỗ trợ LOCK=NONE, đánh giá phương án khác và cửa sổ triển khai trước khi chạy. Không thực hiện constraint change khi vẫn còn hàng NULL.

## 9. Tạo index cho truy vấn mới

Giả sử V3 sẽ lọc đơn hàng theo trạng thái và thời gian:

~~~sql
SELECT id, customer_id, total_amount, created_at
FROM orders
WHERE order_status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 100;
~~~

Index dự kiến:

~~~sql
ALTER TABLE orders
    ADD INDEX idx_orders_order_status_created
        (order_status, created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
~~~

Thứ tự cột index phải dựa trên workload và selectivity. Không thêm index chỉ vì một câu query có điều kiện WHERE; hãy xem EXPLAIN, cardinality, thứ tự sort, covering needs và các query khác dùng index.

Kiểm tra kế hoạch:

~~~sql
EXPLAIN
SELECT id, customer_id, total_amount, created_at
FROM orders
WHERE order_status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 100;
~~~

Sau khi tạo index, theo dõi dung lượng, buffer pool, tốc độ ghi và thời gian truy vấn. Mỗi secondary index làm tăng chi phí INSERT/UPDATE/DELETE và chiếm dung lượng. Có thể cần ANALYZE TABLE theo kế hoạch để cập nhật statistics; đánh giá tác động và thời điểm chạy trước khi thực hiện.

## 10. Switch: chuyển luồng đọc sang cột mới

Khi backfill và validation đạt, phát hành V3. V3 đọc order_status nhưng vẫn dual-write cả hai cột. Cách này cho phép:

- V2 cũ vẫn đọc status và ghi cả hai.
- V3 mới đọc order_status và ghi cả hai.
- Cả hai phiên bản cùng hoạt động trong rolling deployment.

### 10.1. Chuyển traffic bằng feature flag

Một cách rollout:

1. Deploy V3 với flag đọc mới mặc định OFF.
2. Bật cho một nhóm instance hoặc tenant nhỏ.
3. So sánh kết quả đọc cũ/mới trong chế độ shadow nếu phù hợp.
4. Theo dõi error rate, latency, số hàng NULL/mismatch và metric nghiệp vụ.
5. Tăng dần tỷ lệ traffic.
6. Bật toàn bộ sau khi đạt tiêu chí ổn định.
7. Giữ dual-write trong thời gian quan sát để có thể quay lại đọc cột cũ.

Không bật toàn bộ traffic cùng lúc nếu chưa có bằng chứng từ canary. Nếu truy vấn mới dùng index mới, kiểm tra cả plan và tải database khi traffic tăng.

### 10.2. Shadow read và đối chiếu

Trong một số hệ thống, có thể đọc cả hai cột trong cùng request hoặc chạy query so sánh ở tỷ lệ nhỏ:

~~~sql
SELECT
    id,
    status,
    order_status,
    (status <=> order_status) AS values_match
FROM orders
WHERE id = ?;
~~~

Không thực hiện shadow read cho mọi request nếu nó làm tăng gấp đôi tải lên bảng lớn. Chọn sampling rate, tenant hoặc một tập request kiểm thử và chỉ log mismatch đã được lọc dữ liệu nhạy cảm.

## 11. Contract: loại bỏ cột cũ

Chỉ contract khi:

- Tất cả reader đã dùng order_status.
- Tất cả writer đã được chuyển sang phiên bản tương thích.
- Worker, cron, report, stored object, CDC consumer và script cũ không còn tham chiếu status.
- Dual-write đã được dừng theo kế hoạch và nhóm chấp nhận điểm rollback.
- Dữ liệu mới đã ổn định đủ thời gian.
- Backup/PITR và forward recovery đã được kiểm tra.
- DDL drop đã được thử trên bản sao có kích thước tương tự.

Sau khi deploy phiên bản chỉ ghi cột mới, chờ toàn bộ phiên bản dual-write được drain. Lúc này cột status không còn được cập nhật bởi ứng dụng mới; không được rollback về code đọc cột cũ vì dữ liệu có thể stale.

### 11.1. Drop cột

~~~sql
SET SESSION lock_wait_timeout = 5;

ALTER TABLE orders
    DROP COLUMN status,
    ALGORITHM=INSTANT;
~~~

Ví dụ yêu cầu ALGORITHM=INSTANT để câu lệnh thất bại rõ ràng nếu thao tác drop không được hỗ trợ trên đúng bảng/phiên bản. Không bỏ clause rồi chạy lại theo mặc định nếu chưa đánh giá nguy cơ rebuild/copy. Khả năng instant phụ thuộc MySQL version, row format, giới hạn bảng và các dependency của cột; nếu không hỗ trợ, lập kế hoạch online DDL hoặc dùng tool phù hợp.

Drop column có thể yêu cầu metadata lock. Trước khi chạy, kiểm tra transaction dài, lock wait và cửa sổ vận hành. Sau khi drop, xác minh ứng dụng, view, routine và consumer không còn truy vấn cột cũ.

### 11.2. Xóa code tương thích cũ

Sau contract:

- Xóa dual-write code.
- Xóa feature flag migration.
- Xóa job backfill và bảng progress khi đã lưu bằng chứng migration.
- Xóa metric tạm thời sau thời gian quan sát.
- Cập nhật ORM mapping, schema documentation và runbook.
- Xác minh migration state trong công cụ quản lý schema.

Không xóa log/checkpoint ngay khi job hoàn tất nếu cần chúng để điều tra hoặc audit. Lưu bằng chứng theo chính sách vận hành.

## 12. Metadata lock và kiểm soát thời gian chờ

Ngay cả online DDL cũng cần metadata lock ở một số giai đoạn. Một transaction đọc bảng và chưa kết thúc có thể giữ MDL, làm ALTER chờ. Nếu ALTER đang chờ và có độ ưu tiên khóa cao, truy vấn mới có thể xếp hàng phía sau.

Trước DDL:

~~~sql
SET SESSION lock_wait_timeout = 5;
~~~

lock_wait_timeout điều khiển thời gian chờ metadata lock. Nó khác innodb_lock_wait_timeout, vốn điều khiển thời gian chờ row lock của InnoDB.

Không đặt timeout quá dài để migration nằm chờ vô thời hạn trong production. Nếu không lấy được MDL nhanh, nên thất bại, điều tra transaction giữ khóa và thử lại ở thời điểm phù hợp.

Khi DDL đang chạy, quan sát:

- Metadata lock pending/granted.
- Processlist và transaction tuổi dài.
- API latency và connection pool wait.
- Online DDL progress qua Performance Schema nếu thao tác/version cung cấp instrument phù hợp.
- CPU/I/O và replication lag.

Nếu phát hiện DDL đang chờ MDL và gây hàng đợi truy vấn, người vận hành phải xác định session nào đang chặn và cân nhắc hủy DDL đang chờ trước khi ảnh hưởng lan rộng. Không kill blocker nếu chưa đánh giá rollback và tác động nghiệp vụ.

## 13. Giám sát online DDL và online schema change

### 13.1. Online DDL trực tiếp

Theo dõi:

- Thời gian prepare, execution và commit/cut-over.
- CPU, I/O, temporary disk và dung lượng index.
- innodb_online_alter_log_max_size nếu DML đồng thời tạo online alter log.
- MDL wait ở đầu/cuối DDL.
- Replica lag và binlog volume.
- Error log và trạng thái statement.

Nếu online alter log vượt giới hạn trong lúc DML tiếp tục, ALTER có thể thất bại. Tăng giới hạn không phải cách duy nhất; cần xem tốc độ ghi, kích thước DDL, thời gian chạy và dung lượng sẵn có.

### 13.2. Công cụ copy bảng

Với gh-ost hoặc pt-online-schema-change, theo dõi:

- Tốc độ copy và số hàng còn lại.
- Throttle theo replica lag, load và giờ cao điểm.
- Dung lượng bảng shadow và index.
- Binlog growth và khả năng đọc binlog.
- Trigger overhead (đặc biệt với pt-online-schema-change).
- Cut-over lock và thời gian chờ metadata lock.
- Tình trạng bảng gốc, bảng shadow và artifact nếu tool dừng.

Không xóa bảng ghost/shadow thủ công khi chưa xác định tool đang ở trạng thái nào. Dùng lệnh cleanup/abort theo đúng tool version và runbook.

## 14. Điều kiện dừng và tiêu chí go/no-go

Đặt ngưỡng cụ thể trước khi chạy, dựa trên SLO thực tế của hệ thống.

Ví dụ bảng quyết định:

| Chỉ số | Go | Pause/No-go minh họa |
|---|---|---|
| API p95 latency | Gần baseline | Tăng trên 30% liên tục trong 5 phút |
| API error rate | Không tăng đáng kể | Vượt ngưỡng SLO hoặc tăng gấp đôi baseline |
| Replica lag | Ổn định trong giới hạn | Vượt 60 giây và tiếp tục tăng |
| Disk free | Đủ headroom | Dưới ngưỡng vận hành an toàn đã định |
| Lock wait | Không có hàng đợi bất thường | MDL/row lock wait tăng kéo dài |
| DB CPU/I/O | Còn năng lực | Saturation kéo dài hoặc ảnh hưởng workload chính |
| Backfill throughput | Ổn định | Giảm mạnh, deadlock hoặc timeout tăng |

Các ngưỡng trên chỉ là ví dụ để xây runbook. Hệ thống production phải chọn ngưỡng dựa trên baseline, SLO, khả năng replica và thời gian phục hồi.

### 14.1. Go/no-go trước mỗi giai đoạn

**Trước expand:**

- DDL đã thử trên bản sao.
- Thuật toán và lock mode được xác nhận.
- Dung lượng và MDL đã được kiểm tra.
- Backup/PITR được xác nhận.
- Người trực vận hành và tiêu chí dừng đã sẵn sàng.

**Trước backfill:**

- V2 đã được deploy đủ.
- Mọi writer V1 đã drain.
- Dual-write được xác minh bằng test và metric.
- Checkpoint, retry và throttle đã chạy thử.
- Replica và storage còn headroom.

**Trước switch:**

- Không còn hàng thiếu hoặc mismatch theo tiêu chí.
- Index mới đã sẵn sàng và execution plan phù hợp.
- Canary read mới không có lỗi.
- Có thể quay lại đọc cột cũ vì dual-write vẫn tiếp tục.

**Trước contract:**

- Không còn consumer cũ.
- Rollback về schema cũ không còn là phương án được hỗ trợ hoặc đã có phương án phục hồi khác.
- Dual-write đã dừng theo đúng thứ tự.
- DDL drop đã thử và có cửa sổ MDL phù hợp.

## 15. Rollback, pause và forward fix

Không phải giai đoạn nào cũng có cùng khả năng rollback.

| Giai đoạn | Cách xử lý khi có lỗi |
|---|---|
| Trước expand | Hủy kế hoạch, không cần thay đổi dữ liệu |
| Sau expand, chưa dùng cột mới | Có thể giữ cột mới để điều tra hoặc drop nếu đã xác nhận an toàn |
| Trong dual-write | Dừng rollout/backfill; ứng dụng có thể tiếp tục đọc cột cũ nếu dữ liệu cũ vẫn được ghi đúng |
| Sau backfill, trước switch | Có thể giữ cột mới, sửa mapping và chạy lại batch; chưa cần drop |
| Sau switch read, vẫn dual-write | Có thể quay lại đọc cột cũ nếu mismatch/lag đã được kiểm soát |
| Sau write-new-only | Cột cũ có thể stale; không rollback đơn giản về code cũ |
| Sau contract | Cần forward migration hoặc restore/repair có kiểm soát nếu muốn khôi phục cấu trúc cũ |

MySQL DDL như ALTER TABLE thường gây implicit commit. Không dựa vào ROLLBACK SQL để hoàn tác schema change. Với migration đã thay đổi cấu trúc hoặc copy bảng, phải dùng phương án cụ thể của tool hoặc tạo migration mới.

### 15.1. Khi backfill bị lỗi giữa chừng

Nếu một batch deadlock hoặc timeout:

1. Rollback batch hiện tại.
2. Không tiến checkpoint.
3. Ghi lại lỗi, range và thời điểm.
4. Giảm batch size hoặc xử lý nguyên nhân lock.
5. Retry có giới hạn với backoff.
6. Tiếp tục từ checkpoint đã commit.
7. Chạy validation theo range sau khi hoàn tất.

Không retry vô hạn vì có thể che giấu một vấn đề schema hoặc workload dai dẳng.

### 15.2. Khi online DDL bị hủy

Nếu DDL thất bại:

- Đọc lỗi MySQL và error log.
- Xác định thay đổi đã hoàn tất, bị rollback nội bộ hay còn artifact cần xử lý.
- Kiểm tra SHOW CREATE TABLE và metadata.
- Kiểm tra MDL, dung lượng và replica.
- Không chạy lại ngay nếu chưa biết nguyên nhân.

Nếu dùng gh-ost hoặc pt-online-schema-change, làm theo trạng thái và lệnh cleanup của đúng phiên bản tool. Không tự xóa ghost/shadow table dựa trên tên đoán.

## 16. Phân biệt rollback ứng dụng và rollback schema

Rollback ứng dụng thường là triển khai lại image/binary cũ. Rollback schema là đưa database trở về cấu trúc và dữ liệu trước thay đổi. Hai thao tác không tương đương.

Trong ví dụ:

- Khi chỉ thêm order_status, V1 vẫn chạy vì status chưa bị xóa.
- Khi V2 dual-write, có thể dừng V2 và giữ V1 nếu chưa có thay đổi phá vỡ tương thích.
- Khi V3 đọc cột mới nhưng vẫn dual-write, có thể chuyển flag về đọc cũ.
- Khi V4 chỉ ghi cột mới, cột status không còn được cập nhật đầy đủ; đưa V1 trở lại có thể đọc dữ liệu cũ sai.
- Sau khi drop status, rollback ứng dụng cũ sẽ lỗi Unknown column.

Vì vậy, cần định nghĩa rollback point trong kế hoạch triển khai. Sau điểm write-new-only, ưu tiên forward fix nếu dữ liệu mới còn đáng tin cậy. Nếu cần khôi phục schema cũ, phải tạo cột/bảng mới và backfill ngược theo nguồn dữ liệu được xác minh.

## 17. Tổ chức migration code và vận hành

Không gộp DDL, backfill 120 triệu hàng và contract vào một migration startup chạy đồng bộ khi ứng dụng khởi động.

Tách thành các đơn vị có thể quan sát:

1. Vxxx__expand_orders_order_status.sql: thêm cột mới.
2. Release V2: dual-write.
3. Backfill job: chạy độc lập, có checkpoint và throttle.
4. Validation job: đối soát dữ liệu và index.
5. Release V3: switch read.
6. Release V4: ngừng ghi cột cũ sau khi rollback window đóng.
7. Vyyy__contract_orders_status.sql: drop cột cũ.

Flyway hoặc Liquibase có thể quản lý version DDL. Backfill dài nên là job riêng, có trạng thái và quyền dừng/tiếp tục. Không để migration tool giữ một transaction khổng lồ hoặc timeout mặc định trong nhiều giờ.

Mỗi bước cần có:

- Owner và người phê duyệt.
- Precondition.
- Lệnh hoặc artifact cụ thể.
- Metric cần theo dõi.
- Điều kiện hoàn tất.
- Điều kiện dừng.
- Cách resume hoặc forward fix.
- Bằng chứng validation.

## 18. Runbook triển khai mẫu

### T-7 ngày: chuẩn bị

- [ ] Kiểm kê mọi consumer của orders.status.
- [ ] Chọn phương án DDL trực tiếp hoặc online schema change tool.
- [ ] Rehearse trên bản sao có kích thước và tốc độ ghi gần production.
- [ ] Đo thời gian DDL, I/O, disk, MDL và replica lag.
- [ ] Xác nhận backup/PITR và thử restore.
- [ ] Xác định batch size, chunk size, checkpoint và throttle.
- [ ] Viết dashboard và cảnh báo.
- [ ] Chuẩn bị feature flag và rollback point.

### T-1 ngày: kiểm tra sẵn sàng

- [ ] Xác nhận phiên bản MySQL/Connector/ORM đúng với rehearsal.
- [ ] Xác nhận dung lượng đĩa và binlog retention.
- [ ] Kiểm tra transaction dài và session giữ MDL.
- [ ] Xác nhận replica khỏe và không có lag nền bất thường.
- [ ] Xác nhận on-call, DBA và chủ sở hữu ứng dụng sẵn sàng.
- [ ] Đóng băng các DDL không liên quan trong cửa sổ thay đổi.

### Ngày triển khai: expand

- [ ] Đặt lock_wait_timeout cho migration session.
- [ ] Mở rộng cột status cũ nếu yêu cầu độ dài mới và thuật toán đã được rehearsal.
- [ ] Chạy ADD COLUMN order_status theo thuật toán đã kiểm thử.
- [ ] Kiểm tra SHOW CREATE TABLE và metadata.
- [ ] Theo dõi latency, error rate, MDL, CPU/I/O và replica.
- [ ] Nếu có bất thường, dừng trước khi triển khai V2.

### Ngày triển khai: application và backfill

- [ ] Deploy V2 theo rolling deployment.
- [ ] Xác nhận mọi writer V1 đã drain.
- [ ] Kiểm tra dual-write trên dữ liệu mới.
- [ ] Bắt đầu backfill ở tốc độ thấp.
- [ ] Theo dõi mỗi batch và điều chỉnh throttle.
- [ ] Pause nếu vượt ngưỡng SLO hoặc replica lag.
- [ ] Resume từ checkpoint sau khi điều kiện trở lại bình thường.

### Sau backfill: validate và switch

- [ ] Kiểm tra missing/mismatch theo từng range.
- [ ] Đối soát phân bố trạng thái và metric nghiệp vụ.
- [ ] Thêm NOT NULL cho order_status nếu đó là constraint của schema đích và DDL đã được rehearsal.
- [ ] Tạo/kiểm tra index mới và execution plan.
- [ ] Deploy V3 với feature flag.
- [ ] Canary, shadow compare và tăng traffic dần.
- [ ] Giữ dual-write trong thời gian quan sát.

### Contract

- [ ] Xác nhận không còn reader/writer cũ hoặc consumer ngoài ứng dụng.
- [ ] Xác nhận quyết định đóng rollback window.
- [ ] Deploy V4 chỉ dùng cột mới.
- [ ] Drain mọi phiên bản dual-write.
- [ ] Chạy DDL drop theo kế hoạch MDL/online.
- [ ] Kiểm tra ứng dụng, báo cáo, routine và CDC sau contract.
- [ ] Xóa code/flag/job cũ và cập nhật tài liệu.

## 19. Bài thực hành trong môi trường lab

Tạo bảng thử có khóa chính tăng dần và dữ liệu đủ lớn để thấy tác động. Không cần 120 triệu hàng ngay từ đầu; có thể bắt đầu vài triệu hàng rồi tăng quy mô theo tài nguyên lab.

### Bài 1: Đo DDL

1. Tạo bảng orders với schema cũ và secondary index.
2. Nạp dữ liệu giả lập theo batch.
3. Chạy ADD COLUMN ... ALGORITHM=INSTANT.
4. Đo thời gian và xác minh DML vẫn hoạt động.
5. Thử một DDL cần rebuild trên bản sao; ghi lại dung lượng và thời gian.
6. Chạy ADD INDEX ... ALGORITHM=INPLACE, LOCK=NONE.
7. Quan sát Performance Schema, I/O và replication nếu có replica.

### Bài 2: Rolling deployment và dual-write

1. Chạy phiên bản V1 chỉ dùng status.
2. Thêm order_status.
3. Deploy V2 đọc cũ, ghi cả hai.
4. Giữ một writer V1 để chứng minh vì sao chưa thể backfill/switch.
5. Drain writer V1.
6. Tạo một số update đồng thời và xác minh hai cột đồng nhất.

### Bài 3: Backfill có checkpoint

1. Tạo job cập nhật theo range primary key.
2. Lưu checkpoint cùng transaction với mỗi batch.
3. Dừng job giữa chừng và khởi động lại.
4. Tạo update đồng thời từ ứng dụng trong lúc backfill.
5. Xác minh job không ghi đè giá trị dual-write.
6. Mô phỏng deadlock/timeout và kiểm tra retry.
7. Đối soát NULL và mismatch theo range.

### Bài 4: Switch và contract

1. Tạo index phục vụ query trên order_status.
2. Chạy EXPLAIN và benchmark query.
3. Deploy V3 đọc mới, dual-write.
4. Bật feature flag theo canary và quan sát metric.
5. Deploy V4 chỉ dùng cột mới sau khi quyết định đóng rollback window.
6. Drain V3 và mọi consumer cũ.
7. Drop cột status trên bản sao và quan sát MDL.
8. Xác minh không còn truy vấn lỗi hoặc phụ thuộc schema cũ.

## 20. Tiêu chí hoàn thành

Migration chỉ được đánh dấu hoàn tất khi tất cả điều kiện phù hợp đều đạt:

- Schema mới tồn tại đúng định nghĩa và index.
- Dữ liệu cũ đã được backfill và đối soát.
- Mọi writer/reader đang dùng cấu trúc mới.
- Không còn consumer phụ thuộc cột cũ.
- Replica lag trở lại baseline.
- API latency, error rate và DB resource ổn định.
- Không còn job migration chạy dở hoặc checkpoint không rõ trạng thái.
- Backup/PITR và bằng chứng triển khai được lưu.
- Cột cũ đã được contract theo kế hoạch.
- Runbook, schema documentation và migration history được cập nhật.

## Câu hỏi tự kiểm tra

1. Vì sao không nên đổi tên cột trực tiếp trên bảng lớn khi V1 vẫn đang chạy?
2. ALGORITHM=INSTANT khác INPLACE như thế nào?
3. Vì sao LOCK=NONE vẫn có thể gặp metadata lock?
4. Khi nào nên chọn gh-ost hoặc pt-online-schema-change thay cho ALTER trực tiếp?
5. Vì sao phải drain writer cũ trước backfill?
6. Điều kiện order_status IS NULL giúp backfill idempotent ra sao?
7. Vì sao checkpoint phải commit cùng batch dữ liệu?
8. Batch size ảnh hưởng thế nào đến row lock, redo/undo và replica lag?
9. Khi nào có thể switch read sang cột mới?
10. Vì sao write-new-only là điểm rollback quan trọng?
11. Vì sao backup không phải cách rollback schema nhanh?
12. Những metric nào cần theo dõi trước, trong và sau DDL?

## Kết luận

Triển khai schema change trên bảng lớn khi ứng dụng vẫn hoạt động đòi hỏi phối hợp DDL, code, dữ liệu và vận hành theo từng giai đoạn. Hãy kiểm kê phụ thuộc, chọn thuật toán đã rehearsal, expand schema tương thích, triển khai dual-write, drain writer cũ, backfill theo batch có checkpoint, đối soát dữ liệu, switch read có canary rồi mới contract. Online DDL và công cụ copy bảng giúp giảm downtime nhưng vẫn tiêu thụ tài nguyên và cần metadata lock. Kế hoạch chỉ an toàn khi có tiêu chí dừng, rollback point, forward recovery và runbook rõ ràng.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — ALTER TABLE](https://dev.mysql.com/doc/refman/8.4/en/alter-table.html)
- [MySQL 8.4 Reference Manual — InnoDB Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl.html)
- [MySQL 8.4 Reference Manual — InnoDB Online DDL Operations](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html)
- [MySQL 8.4 Reference Manual — Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html)
- [MySQL 8.4 Reference Manual — Online DDL Space Requirements](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-space-requirements.html)
- [GitHub — gh-ost](https://github.com/github/gh-ost)
- [Percona Toolkit — pt-online-schema-change](https://docs.percona.com/percona-toolkit/pt-online-schema-change.html)
- [MySQL 8.4 Reference Manual — InnoDB System Variables](https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html)
