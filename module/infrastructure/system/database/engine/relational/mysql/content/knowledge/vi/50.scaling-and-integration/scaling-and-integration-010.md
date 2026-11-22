# Lưu trữ dữ liệu cũ, tổng hợp báo cáo và tách tải phân tích

Khi hệ thống MySQL phát triển, bảng giao dịch thường tăng liên tục trong khi phần lớn truy vấn nghiệp vụ chỉ cần dữ liệu gần đây. Báo cáo theo tháng, quý hoặc nhiều năm lại phải quét và tổng hợp một lượng lớn bản ghi. Nếu chạy các truy vấn phân tích nặng trực tiếp trên primary đang phục vụ OLTP, chúng có thể tranh chấp CPU, I/O, buffer pool, connection và metadata lock với request của ứng dụng.

Một chiến lược mở rộng hợp lý kết hợp ba việc: xác định vòng đời dữ liệu và lưu trữ dữ liệu cũ theo chính sách; tạo bảng tổng hợp để báo cáo không phải tính lại mọi chi tiết; và tách tải phân tích sang read replica hoặc kho dữ liệu riêng. Bài học thuộc module **DATABASE_MYSQL**, tập trung vào khả năng mở rộng và tích hợp MySQL, từ thiết kế retention, archive, partition đến ETL/CDC và kiểm soát tải báo cáo.

## 1. Phân biệt OLTP và OLAP

Hai nhóm workload có đặc điểm khác nhau:

| Đặc điểm | OLTP — giao dịch | OLAP — phân tích |
|---|---|---|
| Mục tiêu | Phục vụ thao tác nghiệp vụ trực tuyến | Tổng hợp, so sánh và phân tích xu hướng |
| Truy vấn | Ngắn, có điều kiện chọn lọc, thường dùng index | Quét nhiều hàng, JOIN nhiều bảng, GROUP BY |
| Ghi dữ liệu | Nhiều INSERT/UPDATE/DELETE nhỏ | Thường nạp theo lô hoặc theo luồng |
| Transaction | Ngắn, cần độ trễ thấp và tính nhất quán | Có thể đọc snapshot lớn, xử lý dài |
| Tối ưu | Throughput giao dịch và latency p95/p99 | Throughput scan, thời gian hoàn thành báo cáo |
| Tài nguyên | Cần ổn định cho request người dùng | Có thể tiêu thụ CPU, I/O và bộ nhớ lớn |

Ví dụ OLTP: tạo đơn hàng, trừ tồn kho, cập nhật trạng thái thanh toán. Ví dụ OLAP: tổng doanh thu theo vùng trong 24 tháng, tỷ lệ khách hàng quay lại hoặc phân tích số đơn theo sản phẩm và kênh bán.

Một câu SQL có thể chạy nhanh trên dữ liệu nhỏ nhưng trở thành tải OLAP khi quét hàng chục triệu bản ghi. Không nên đánh giá một truy vấn chỉ theo cú pháp; hãy xét số hàng, phạm vi thời gian, cardinality, index, concurrency và tác động đến các workload đang chạy.

## 2. Kiến trúc tách tải dữ liệu

Một kiến trúc phổ biến có ba vùng:

~~~text
                   Ứng dụng nghiệp vụ
                           |
                           v
                    MySQL Primary
                     OLTP workload
                           |
                 Asynchronous replication
                           |
             +-------------+-------------+
             |                           |
             v                           v
      Read Replica                CDC / ETL pipeline
  truy vấn đọc chọn lọc                    |
  báo cáo vận hành                         v
                                    Analytics Store
                                  fact / dimension /
                                  aggregate tables
                                           |
                                           v
                                  Dashboard / BI / ML
~~~

Vai trò từng thành phần:

- **Primary:** nhận giao dịch ghi và các truy vấn nghiệp vụ cần dữ liệu mới nhất.
- **Read replica:** phục vụ truy vấn đọc có thể chấp nhận độ trễ replication; giảm một phần tải đọc trên primary.
- **CDC/ETL:** chuyển dữ liệu thay đổi hoặc dữ liệu theo lô sang hệ thống phân tích.
- **Analytics store:** lưu dữ liệu lịch sử, fact/dimension và bảng tổng hợp được thiết kế cho truy vấn phân tích.

Read replica vẫn là một MySQL server phải áp dụng relay log và thực thi thay đổi từ primary. Một báo cáo quá nặng có thể làm replica lag tăng, khiến dữ liệu đọc cũ và ảnh hưởng các consumer khác. Vì vậy, replica là một bước offload hữu ích nhưng không thay thế kho phân tích riêng khi workload OLAP lớn hoặc khó dự đoán.

### Chọn nơi chạy báo cáo

| Loại báo cáo | Nơi phù hợp để bắt đầu |
|---|---|
| Tra cứu chi tiết một đơn hàng gần đây | Primary hoặc replica tùy yêu cầu freshness |
| Dashboard vận hành với truy vấn nhẹ | Read replica |
| Tổng hợp doanh thu nhiều tháng trên hàng chục triệu dòng | Analytics store hoặc summary table |
| Phân tích ad hoc, JOIN nhiều fact table | Kho dữ liệu phân tích |
| Báo cáo cần read-after-write ngay sau giao dịch | Primary hoặc cơ chế chờ replica bắt kịp |

Không chuyển tất cả SELECT sang replica một cách máy móc. Các luồng đọc sau khi ghi, kiểm tra tồn kho, xác nhận thanh toán hoặc kiểm tra quyền có thể yêu cầu dữ liệu mới nhất và cần đọc từ primary hoặc dùng cơ chế consistency phù hợp.

## 3. Xây dựng chính sách vòng đời dữ liệu

Trước khi archive, cần xác định dữ liệu nào còn phục vụ giao dịch, dữ liệu nào cần tra cứu lịch sử và dữ liệu nào có thể xóa.

Một chính sách retention nên mô tả:

- **Phạm vi:** bảng, loại bản ghi và tenant/đơn vị nghiệp vụ áp dụng.
- **Mốc thời gian:** dựa trên created_at, closed_at, paid_at hoặc ngày kết thúc nghiệp vụ.
- **Điều kiện lưu trữ:** chỉ archive bản ghi đã hoàn tất, không còn transaction hoặc quy trình đang mở.
- **Thời gian lưu:** bao lâu ở bảng nóng, bao lâu ở archive và bao lâu ở backup.
- **Legal hold:** trường hợp phải giữ lại dù đã đến hạn xóa thông thường.
- **Khả năng truy xuất:** ai được đọc dữ liệu cũ, thời gian phục hồi mong muốn và cách kiểm soát truy cập.
- **Xóa cuối cùng:** cách xóa khỏi database, archive, bản sao và backup theo chính sách.

Không dùng một mốc thời gian chung cho mọi bảng. Ví dụ, bảng session có thể chỉ cần lưu vài ngày, dữ liệu log vận hành có thể lưu theo tuần hoặc tháng, trong khi đơn hàng đã hoàn tất có thể cần tra cứu trong nhiều năm tùy yêu cầu nghiệp vụ.

### Phân loại dữ liệu

| Nhóm | Đặc điểm | Cách xử lý |
|---|---|---|
| Dữ liệu nóng | Được đọc/ghi thường xuyên | Giữ trong bảng OLTP có index phù hợp |
| Dữ liệu ấm | Ít cập nhật nhưng vẫn cần tra cứu | Có thể chuyển sang schema/bảng lịch sử hoặc replica |
| Dữ liệu lạnh | Hiếm khi truy cập, chủ yếu phục vụ kiểm toán/lịch sử | Archive sang storage rẻ hơn hoặc kho dữ liệu |
| Dữ liệu hết hạn | Không còn mục đích lưu trữ hợp lệ | Xóa hoặc ẩn danh theo retention đã phê duyệt |

Archive không đồng nghĩa với xóa. Nếu bản ghi cũ vẫn phải truy xuất, cần xác định ứng dụng tìm kiếm dữ liệu đó qua bảng archive, service lịch sử hay kho dữ liệu.

## 4. Thiết kế bảng archive

Có nhiều cách tổ chức archive. Lựa chọn phụ thuộc vào kích thước dữ liệu, tần suất tra cứu, ràng buộc và khả năng vận hành.

### Bảng archive cùng schema

Ví dụ bảng đơn hàng đang hoạt động:

~~~sql
CREATE TABLE app.orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(15,2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_created_at (created_at),
    KEY idx_orders_customer_created (customer_id, created_at)
) ENGINE=InnoDB;
~~~

Có thể tạo bảng archive với cấu trúc tương thích:

~~~sql
CREATE TABLE archive.orders_archive LIKE app.orders;
~~~

Lệnh CREATE TABLE ... LIKE sao chép cấu trúc cột và index nhưng không sao chép dữ liệu. Cần kiểm tra lại các thuộc tính không được sao chép đầy đủ theo nhu cầu, đặc biệt foreign key, trigger, partition, quyền và các đối tượng phụ thuộc.

Ưu điểm:

- Dễ chuyển dữ liệu giữa hai bảng trên cùng MySQL instance.
- Có thể giữ kiểu dữ liệu và khóa tương tự bảng nguồn.
- Ứng dụng có thể tra cứu lịch sử bằng truy vấn riêng.

Hạn chế:

- Dữ liệu vẫn tiêu thụ storage và backup của cùng instance.
- Bảng archive vẫn tạo index và chi phí bảo trì.
- Truy vấn UNION giữa bảng nóng và archive có thể phức tạp.
- Cần quản lý FK, trigger, quyền và chính sách xóa riêng.

Nếu mục tiêu là giảm dung lượng trên primary, chỉ chuyển sang schema khác trên cùng instance thường chưa đủ. Cần archive sang instance hoặc object storage/kho dữ liệu riêng.

### Archive theo database hoặc instance riêng

Có thể tạo database lịch sử trên cùng instance hoặc server khác. Tách instance giúp cô lập I/O, backup và quyền truy cập tốt hơn. Tuy nhiên, nếu chuyển sang server khác, giao dịch chuyển dữ liệu không còn nằm trong cùng một transaction MySQL; cần quy trình đồng bộ, xác minh và checkpoint riêng.

### Archive sang object storage hoặc data lake

Với dữ liệu rất cũ, có thể xuất theo định dạng CSV, Parquet hoặc định dạng được nền tảng phân tích hỗ trợ rồi lưu trong object storage. Quy trình cần:

- Manifest mô tả schema, partition thời gian, số hàng và checksum.
- Mã hóa khi lưu và truyền.
- Kiểm soát quyền truy cập và retention.
- Phiên bản schema để đọc lại dữ liệu cũ.
- Quy trình kiểm tra file và khả năng khôi phục.

MySQL không tự biến object storage thành một bảng có thể JOIN trực tiếp. Ứng dụng hoặc nền tảng phân tích cần một lớp đọc/ETL để truy xuất dữ liệu đã archive.

## 5. Chuyển dữ liệu cũ theo batch an toàn

Không nên xóa hàng triệu bản ghi trong một transaction duy nhất. Một transaction quá lớn có thể giữ row lock lâu, tạo undo/redo log lớn, làm replica lag tăng, gây áp lực purge và khiến rollback rất tốn thời gian.

Chuyển theo batch nhỏ giúp giới hạn tác động và có thể tiếp tục từ checkpoint. Mỗi batch cần xác định rõ:

- Điều kiện đủ tuổi và đủ trạng thái để archive.
- Phạm vi khóa chính của batch.
- Số hàng đã copy và số hàng đã xóa.
- Checkpoint cuối cùng đã hoàn thành.
- Cách xử lý khi batch lỗi hoặc chạy lại.

### Điều kiện archive

Ví dụ chỉ archive đơn hàng đã thanh toán hoặc đã hủy, đã đóng và cũ hơn cutoff:

~~~sql
SELECT order_id, status, created_at
FROM app.orders
WHERE created_at < '2025-01-01 00:00:00'
  AND status IN ('PAID', 'CANCELLED')
ORDER BY order_id
LIMIT 100;
~~~

Cutoff nên được tính theo UTC hoặc một timezone thống nhất. Không dùng thời điểm hiện tại ở mỗi batch theo cách khiến điều kiện thay đổi giữa chừng; ghi lại cutoff của cả lần chạy để job có thể tiếp tục nhất quán.

### Di chuyển trong cùng MySQL instance

Nếu bảng nguồn và archive đều là InnoDB trên cùng instance, có thể copy và xóa trong một transaction theo từng khoảng khóa chính. Ví dụ:

~~~sql
START TRANSACTION;

INSERT INTO archive.orders_archive (
    order_id, customer_id, status, total_amount, created_at
)
SELECT
    order_id, customer_id, status, total_amount, created_at
FROM app.orders
WHERE created_at < '2025-01-01 00:00:00'
  AND status IN ('PAID', 'CANCELLED')
  AND order_id > 100000
  AND order_id <= 101000;

DELETE FROM app.orders
WHERE created_at < '2025-01-01 00:00:00'
  AND status IN ('PAID', 'CANCELLED')
  AND order_id > 100000
  AND order_id <= 101000;

COMMIT;
~~~

Đây là ví dụ theo khoảng ID; kích thước khoảng phải được điều chỉnh theo mật độ dữ liệu và thời gian transaction. Nếu INSERT hoặc DELETE lỗi, rollback cả transaction để tránh trạng thái chỉ copy mà chưa xóa hoặc đã xóa mà chưa archive. Archive table nên có unique key phù hợp để phát hiện bản ghi trùng.

Điều kiện ở câu INSERT và DELETE phải tương ứng chính xác. Nếu các hàng có thể bị cập nhật đồng thời, cần khóa hoặc kiểm tra lại trạng thái hàng trong transaction; tốt hơn là chỉ archive dữ liệu đã đóng và bất biến theo nghiệp vụ. Không xóa hàng chỉ dựa trên một danh sách ID cũ nếu trạng thái hoặc điều kiện retention có thể đã thay đổi.

Sau mỗi batch, ghi checkpoint và số hàng. Có thể dùng ROW_COUNT() ngay sau INSERT và DELETE để lấy số hàng ảnh hưởng; ứng dụng điều phối nên so sánh hai con số và chỉ đánh dấu batch hoàn tất khi transaction commit thành công.

### Di chuyển sang server archive riêng

Không thể dùng một transaction InnoDB thông thường để atomic commit giữa hai MySQL server độc lập. Dùng quy trình có checkpoint:

1. Chụp phạm vi ID và cutoff cố định.
2. Export hoặc đọc dữ liệu nguồn theo batch.
3. Nạp vào staging/archive đích bằng khóa duy nhất để phát hiện bản ghi trùng.
4. So sánh số hàng, checksum theo chunk và các trường nghiệp vụ quan trọng.
5. Ghi manifest/checkpoint đã xác minh ở hệ thống đích.
6. Chỉ sau khi xác nhận dữ liệu đích đầy đủ mới xóa nguồn theo đúng phạm vi đã kiểm tra.
7. Nếu job chạy lại, bỏ qua hoặc đối chiếu bản ghi đã có; không tạo bản sao mới.

Nếu dữ liệu vẫn có thể thay đổi trong lúc export, cần chốt snapshot hoặc dùng CDC để bắt các thay đổi sau snapshot. Nếu không, bản archive có thể bỏ sót cập nhật hoặc chứa trạng thái cũ.

### Quan hệ cha-con và ràng buộc

Khi archive bảng cha, hãy kiểm tra các bảng con tham chiếu đến nó. Có thể cần archive bảng con trước, giữ bản ghi cha trong bảng nóng đến khi hết phụ thuộc, hoặc lưu dữ liệu lịch sử theo mô hình không còn FK nhưng vẫn có định danh nghiệp vụ rõ ràng.

Không xóa bảng cha trước khi xử lý quan hệ con. Bảng archive ở schema/database khác cũng không nên được giả định có thể giữ nguyên mọi foreign key của bảng nguồn; kiểm tra giới hạn FK và thiết kế truy xuất trước khi chuyển.

## 6. Xóa dữ liệu hết hạn theo batch

Nếu dữ liệu đã được archive và xác minh, xóa khỏi bảng nóng theo batch:

~~~sql
DELETE FROM app.orders
WHERE created_at < '2025-01-01 00:00:00'
  AND status IN ('PAID', 'CANCELLED')
ORDER BY order_id
LIMIT 1000;
~~~

Lặp lại cho đến khi không còn hàng phù hợp. Nghỉ giữa các batch nếu cần để giảm áp lực I/O và replication. Dùng index hỗ trợ điều kiện lọc, ví dụ index bắt đầu bằng created_at hoặc một index kết hợp phù hợp với status và created_at.

Không chạy DELETE lớn trong giờ cao điểm mà không theo dõi:

- Thời gian thực hiện và số hàng mỗi batch.
- Row lock wait và deadlock.
- Undo/redo, history list length và purge lag.
- Binary log, relay log và replica lag.
- Dung lượng đĩa và tốc độ tăng của file log.
- Latency và error rate của ứng dụng OLTP.

Nếu DELETE kích hoạt cascade, trigger hoặc ghi audit, chi phí có thể lớn hơn số hàng trực tiếp bị xóa. Đo tác động trên bản sao dữ liệu gần production.

### Idempotency và checkpoint

Job archive phải có thể chạy lại sau khi process chết hoặc mạng gián đoạn. Mỗi batch nên có:

- run_id duy nhất.
- cutoff cố định.
- khóa bắt đầu/kết thúc hoặc cursor cuối cùng.
- trạng thái PENDING/RUNNING/VERIFIED/COMPLETED/FAILED.
- số hàng nguồn, đích và checksum.
- thời điểm bắt đầu/kết thúc và thông tin lỗi.

Không cập nhật checkpoint trước khi dữ liệu đích đã commit và xác minh. Nếu checkpoint được ghi ở hệ thống khác với archive database, cần thiết kế thứ tự ghi và cơ chế đối soát để xử lý trường hợp một bên commit còn bên kia mất kết nối.

## 7. Dùng partition để quản lý dữ liệu theo thời gian

Partitioning chia một bảng logic thành các phần vật lý theo quy tắc. Với bảng lịch sử có cột thời gian, RANGE partition có thể giúp loại bỏ nhanh một vùng dữ liệu cũ bằng thao tác DDL thay vì DELETE từng hàng.

Ví dụ bảng sự kiện partition theo tháng:

~~~sql
CREATE TABLE app.order_events (
    event_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    order_id BIGINT NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    payload JSON NULL,
    PRIMARY KEY (event_id, created_at),
    KEY idx_order_created (order_id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p_before_2026_11
        VALUES LESS THAN ('2026-11-01 00:00:00'),
    PARTITION p202611
        VALUES LESS THAN ('2026-12-01 00:00:00'),
    PARTITION p202612
        VALUES LESS THAN ('2027-01-01 00:00:00'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

Ví dụ trên minh họa cấu trúc; cần tạo partition tương lai trước khi dữ liệu chạm MAXVALUE và có quy trình quản lý tên partition theo lịch. Primary key chứa created_at vì với MySQL partitioned table, mọi unique key phải bao gồm tất cả cột được dùng trong biểu thức partition. Điều này có nghĩa event_id không còn được bảo đảm duy nhất toàn bảng bởi primary key trên.

### Loại bỏ partition cũ

Khi partition đã hết retention và dữ liệu đã được archive hoặc không còn cần giữ:

~~~sql
ALTER TABLE app.order_events
  DROP PARTITION p202611;
~~~

DROP PARTITION loại bỏ toàn bộ dữ liệu trong partition đó. Đây là thao tác phá hủy dữ liệu, cần xác nhận cutoff, backup, manifest archive và tên partition trước khi chạy. Nó không tự xuất dữ liệu sang archive.

### Giới hạn cần biết

- Mọi UNIQUE key trên bảng partitioned phải chứa các cột partition.
- InnoDB partitioned tables không hỗ trợ foreign key theo các giới hạn của MySQL.
- Một số loại index, engine, kiểu dữ liệu và thao tác DDL có giới hạn riêng.
- Partition pruning chỉ hữu ích khi truy vấn lọc theo partition key phù hợp.
- Quá nhiều partition làm tăng metadata và chi phí quản lý.
- Partitioning không thay thế index; mỗi partition vẫn cần index phù hợp.

Không partition mọi bảng chỉ vì bảng lớn. Chọn partition khi có quy tắc truy vấn/retention rõ, dữ liệu phân bố hợp lý và đội vận hành có quy trình tạo, archive, drop và giám sát partition.

### Partitioning không đồng nghĩa với archive

Partitioning giúp quản lý và loại bỏ vùng dữ liệu trong cùng một bảng/instance. Archive là chuyển dữ liệu sang nơi lưu trữ khác với chính sách truy xuất và retention riêng. Nếu cần giữ lịch sử sau khi drop partition, phải export/verify hoặc dùng một quy trình chuyển partition sang bảng lưu trữ trước khi loại bỏ.

## 8. Thiết kế bảng tổng hợp cho báo cáo

Một báo cáo lặp lại mỗi ngày không nhất thiết phải quét toàn bộ bảng giao dịch mỗi lần. Có thể tạo bảng tổng hợp theo ngày, cửa hàng, sản phẩm hoặc vùng để dashboard đọc một lượng dữ liệu nhỏ hơn.

Ví dụ bảng fact đơn hàng có nhiều triệu dòng; dashboard chỉ cần doanh thu và số đơn theo ngày/cửa hàng. Tạo bảng summary:

~~~sql
CREATE TABLE analytics.daily_sales (
    sales_date DATE NOT NULL,
    store_id BIGINT NOT NULL,
    order_count BIGINT NOT NULL,
    gross_amount DECIMAL(18,2) NOT NULL,
    updated_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (sales_date, store_id),
    KEY idx_daily_sales_store_date (store_id, sales_date)
) ENGINE=InnoDB;
~~~

Job tổng hợp trên analytics store có thể tính lại một ngày hoặc một khoảng ngày:

~~~sql
START TRANSACTION;

DELETE FROM analytics.daily_sales
WHERE sales_date = '2026-11-18';

INSERT INTO analytics.daily_sales (
    sales_date, store_id, order_count, gross_amount
)
SELECT
    DATE(created_at) AS sales_date,
    store_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS gross_amount
FROM analytics.fact_orders
WHERE created_at >= '2026-11-18 00:00:00'
  AND created_at <  '2026-11-19 00:00:00'
  AND status = 'PAID'
GROUP BY DATE(created_at), store_id;

COMMIT;
~~~

Xóa và tính lại một khoảng thời gian hữu hạn giúp job có thể chạy lại mà không cộng dồn doanh thu lần thứ hai. Ví dụ trên giả định fact_orders là dữ liệu đã được nạp vào analytics store và chỉ refresh một ngày tại một thời điểm. Với nhiều job đồng thời, cần khóa điều phối hoặc cơ chế version để hai job không xóa/ghi đè cùng khoảng ngày.

Không chạy ví dụ này trực tiếp trên primary nếu phép tổng hợp quét bảng OLTP lớn. Nên lấy dữ liệu từ replica/CDC hoặc analytics store, rồi ghi summary ở nơi phục vụ báo cáo.

### Tổng hợp theo nhiều cấp

Có thể xây các bảng summary theo các chiều khác nhau:

| Bảng tổng hợp | Grain — mức chi tiết | Ví dụ truy vấn |
|---|---|---|
| daily_sales | Ngày × cửa hàng | Doanh thu theo ngày |
| monthly_sales | Tháng × vùng | So sánh tăng trưởng vùng |
| product_sales | Ngày × sản phẩm | Sản phẩm bán chạy |
| customer_activity | Khách hàng × tháng | Tần suất quay lại |

Grain phải được xác định rõ. Nếu một bảng summary có grain ngày × cửa hàng, không thể suy ra doanh thu theo từng sản phẩm nếu không có chiều sản phẩm hoặc một bảng summary khác.

### Dùng GROUP BY và ROLLUP

Với dữ liệu nhỏ hoặc báo cáo ad hoc, MySQL có thể tổng hợp trực tiếp:

~~~sql
SELECT
    YEAR(created_at) AS sales_year,
    MONTH(created_at) AS sales_month,
    store_id,
    SUM(total_amount) AS gross_amount
FROM analytics.fact_orders
WHERE created_at >= '2025-01-01'
  AND created_at <  '2026-01-01'
  AND status = 'PAID'
GROUP BY
    YEAR(created_at),
    MONTH(created_at),
    store_id
WITH ROLLUP;
~~~

ROLLUP tạo các dòng subtotal và grand total. Ứng dụng cần nhận diện các giá trị NULL do subtotal sinh ra, không nhầm chúng với dữ liệu gốc có NULL. Với báo cáo lặp lại hoặc dữ liệu lớn, bảng summary thường dễ kiểm soát chi phí hơn việc tính lại mỗi lần.

### Không có materialized view tự động trong MySQL

MySQL không cung cấp materialized view được tự động refresh như một số hệ quản trị khác. Một bảng summary thường được duy trì bằng scheduled event, ứng dụng batch, scheduler bên ngoài hoặc pipeline ETL/CDC. Cần tự quản lý thời điểm refresh, tính idempotent, checkpoint và đối soát.

## 9. Chọn chiến lược cập nhật summary

Có ba cách phổ biến:

| Chiến lược | Cách hoạt động | Phù hợp |
|---|---|---|
| Full refresh | Tính lại toàn bộ summary rồi thay thế phiên bản cũ | Dữ liệu nhỏ hoặc cửa sổ refresh dài |
| Incremental batch | Chỉ xử lý khoảng thời gian hoặc ID mới | Bảng lớn, có checkpoint và dữ liệu gần append-only |
| CDC-based | Áp dụng sự kiện INSERT/UPDATE/DELETE vào mô hình phân tích | Cần độ trễ thấp và xử lý thay đổi liên tục |

### Full refresh

Ưu điểm là logic đơn giản và dễ đối soát. Nhược điểm là đọc lại toàn bộ dữ liệu, tốn I/O và có thể tạo khoảng thời gian summary không sẵn sàng nếu thay thế không nguyên tử.

Một mẫu an toàn hơn là tính vào bảng staging, kiểm tra xong rồi đổi phiên bản hoặc thay dữ liệu trong transaction phù hợp. Không truncate bảng đang được dashboard đọc nếu không chấp nhận khoảng trống.

### Incremental batch

Lưu watermark như thời gian cập nhật hoặc khóa tăng dần:

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    updated_at
FROM app.orders
WHERE updated_at > '2026-11-18 10:00:00'
  AND updated_at <= '2026-11-18 10:05:00'
ORDER BY updated_at, order_id;
~~~

Watermark phải có thứ tự ổn định. Nếu nhiều bản ghi có cùng updated_at, dùng thêm khóa duy nhất để tạo cursor kép, ví dụ (updated_at, order_id). Nên dùng khoảng chồng lấn nhỏ rồi upsert theo primary key ở đích để tránh bỏ sót do timestamp có độ phân giải thấp, clock skew hoặc transaction commit trễ.

Nếu bản ghi cũ có thể được UPDATE hoặc DELETE, incremental scan chỉ theo created_at sẽ không đủ. Cần updated_at đáng tin cậy, tombstone, audit table hoặc CDC để ghi nhận thay đổi.

### CDC từ binary log

Change Data Capture đọc các sự kiện thay đổi từ MySQL binary log và chuyển chúng sang hệ thống khác. Một pipeline CDC thường:

1. Chụp snapshot ban đầu hoặc xác định vị trí bắt đầu.
2. Đọc binlog theo thứ tự commit.
3. Chuyển row event thành thay đổi ở đích.
4. Ghi checkpoint/offset đã áp dụng.
5. Tiếp tục đọc sau khi restart.

CDC phù hợp khi cần đồng bộ thay đổi liên tục, nhưng cần quản lý binlog retention, schema evolution, transaction lớn, ordering, duplicate delivery và khả năng replay. Consumer nên idempotent vì một số pipeline có thể phát lại sự kiện khi khởi động lại hoặc phục hồi checkpoint.

## 10. Đồng bộ dữ liệu qua replica và CDC

MySQL replication thường là bất đồng bộ. Primary có thể commit trước khi replica áp dụng transaction. Vì vậy, báo cáo đọc từ replica có thể trễ so với giao dịch vừa xảy ra.

### Theo dõi replica lag

Trên replica, kiểm tra trạng thái replication theo phiên bản:

~~~sql
SHOW REPLICA STATUS\G
~~~

Các trường hữu ích gồm:

- Replica_IO_Running và Replica_SQL_Running.
- Seconds_Behind_Source.
- Last_IO_Error và Last_SQL_Error.
- Source_Log_File, Read_Source_Log_Pos.
- Relay_Source_Log_File, Exec_Source_Log_Pos.
- Retrieved_Gtid_Set và Executed_Gtid_Set khi dùng GTID.

Tên trường có thể khác ở phiên bản cũ, ví dụ các tên dùng Master thay cho Source. Seconds_Behind_Source không phải thước đo hoàn hảo trong mọi tình huống; NULL có thể biểu thị trạng thái không xác định. Nên theo dõi thêm hàng đợi applier, GTID đã thực thi, thời gian transaction và độ trễ quan sát từ ứng dụng.

### Báo cáo cần dữ liệu mới nhất

Nếu user vừa tạo đơn hàng rồi ngay lập tức mở trang xác nhận, đọc từ replica có thể chưa thấy đơn hàng. Các lựa chọn:

- Đọc từ primary trong khoảng thời gian read-after-write.
- Chờ replica thực thi đến GTID đã commit rồi mới đọc.
- Gắn consistency token/version vào request và định tuyến đọc phù hợp.
- Thiết kế UI thể hiện trạng thái đang đồng bộ nếu nghiệp vụ chấp nhận eventual consistency.

Không giả định mọi replica đều có dữ liệu giống primary tại cùng thời điểm.

### Binlog retention cho CDC

Consumer CDC có thể bị gián đoạn lâu hơn dự kiến. Nếu MySQL purge binlog trước khi consumer đọc đến vị trí cần thiết, pipeline không thể tiếp tục từ offset cũ và có thể phải snapshot lại.

Đặt retention đủ dài dựa trên:

- Thời gian gián đoạn tối đa có thể xảy ra.
- Tốc độ sinh binlog cao điểm.
- Thời gian khôi phục consumer và replay backlog.
- Dung lượng disk dành cho binlog.
- Chính sách backup và point-in-time recovery.

Không purge binary log chỉ để giải phóng đĩa khi replica hoặc CDC consumer còn cần các file đó.

## 11. Thiết kế mô hình dữ liệu phân tích

Kho dữ liệu phân tích thường tổ chức dữ liệu theo fact và dimension:

- **Fact table:** lưu sự kiện hoặc số đo có thể tổng hợp, ví dụ đơn hàng, dòng đơn hàng, thanh toán.
- **Dimension table:** mô tả các chiều phân tích như khách hàng, sản phẩm, cửa hàng, ngày và kênh bán.

Ví dụ:

~~~text
                 dim_customer
                       |
dim_date ---- fact_order_line ---- dim_product
                       |
                  dim_store
                       |
                  dim_channel
~~~

Fact table cần grain rõ ràng. Ví dụ một hàng là một dòng sản phẩm trong đơn hàng, không phải một đơn hàng. Nếu SUM(total_amount) trên bảng dòng đơn hàng mà total_amount là tổng cấp đơn, doanh thu có thể bị nhân lên theo số dòng. Định nghĩa grain và measure trước khi viết báo cáo.

### Dimension thay đổi theo thời gian

Tên sản phẩm, phân loại, khu vực hoặc phân khúc khách hàng có thể thay đổi. Nếu báo cáo lịch sử phải phản ánh thuộc tính tại thời điểm giao dịch, cần lưu lịch sử dimension, ví dụ Slowly Changing Dimension Type 2 với effective_from, effective_to và cờ current_record.

Nếu chỉ ghi đè thuộc tính hiện tại, báo cáo quá khứ có thể bị thay đổi theo thông tin mới. Chọn cách lưu lịch sử theo yêu cầu nghiệp vụ, không mặc định dimension luôn bất biến.

### Chuẩn hóa đơn vị và timezone

Trước khi tổng hợp, thống nhất:

- Tiền tệ và quy tắc quy đổi tỷ giá.
- Múi giờ dùng để xác định ngày báo cáo.
- Quy tắc hoàn tiền, hủy đơn và điều chỉnh doanh thu.
- Định nghĩa đơn hàng hợp lệ và thời điểm ghi nhận doanh thu.
- Cách xử lý dữ liệu đến muộn hoặc được sửa sau khi đã tổng hợp.

Ví dụ, một đơn hàng tạo lúc 23:30 UTC có thể thuộc ngày khác nếu báo cáo theo giờ Việt Nam. Không dùng DATE(timestamp) mà chưa xác định timezone nghiệp vụ.

## 12. Xử lý dữ liệu đến muộn và thay đổi lịch sử

Incremental pipeline thường giả định dữ liệu mới chỉ được thêm vào. Thực tế, một đơn hàng cũ có thể được hoàn tiền, điều chỉnh trạng thái, cập nhật thông tin cửa hàng hoặc bị xóa theo yêu cầu nghiệp vụ. Nếu summary chỉ cộng thêm sự kiện mới mà không xử lý thay đổi cũ, báo cáo sẽ sai dần theo thời gian.

Các tình huống cần có quy tắc:

- **Late-arriving data:** giao dịch có event time thuộc ngày cũ nhưng chỉ đến pipeline sau vài giờ hoặc vài ngày.
- **Correction:** số tiền hoặc trạng thái của bản ghi lịch sử được sửa.
- **Delete/tombstone:** bản ghi nguồn bị xóa nhưng summary phải trừ hoặc loại bỏ phần đóng góp trước đó.
- **Duplicate event:** CDC hoặc batch phát lại cùng sự kiện.
- **Out-of-order event:** sự kiện đến không đúng thứ tự nghiệp vụ.

### Recompute cửa sổ gần đây

Một cách đơn giản là tính lại một cửa sổ ngày gần nhất mỗi lần chạy, ví dụ 3–7 ngày, tùy độ trễ dữ liệu thực tế. Dùng DELETE theo ngày rồi INSERT lại kết quả tính toán trong một transaction ở analytics store. Cách này xử lý được late-arriving data trong cửa sổ đó.

Các điều chỉnh cũ hơn cửa sổ cần một luồng correction/backfill riêng. Không giả định mọi dữ liệu đến muộn đều nằm trong vài ngày gần nhất.

### CDC phải có khóa và thứ tự áp dụng

Đối với CDC, lưu event ID hoặc khóa nguồn và checkpoint đã áp dụng. Nếu event được gửi lại, consumer nhận biết và không áp dụng lần thứ hai. Với UPDATE, cần biết giá trị trước/sau hoặc đủ dữ liệu để tái tính measure. Với DELETE, cần tombstone hoặc sự kiện xóa để loại bản ghi khỏi fact/summary.

Không chỉ dùng timestamp làm khóa sự kiện nếu nhiều thay đổi có thể có cùng timestamp. Dùng khóa định danh ổn định và offset/binlog position hoặc GTID để duy trì thứ tự và checkpoint.

## 13. Tối ưu truy vấn báo cáo

Tách tải phân tích không có nghĩa có thể bỏ qua tối ưu SQL. Một báo cáo đọc hàng tỷ dòng vẫn có thể làm nghẽn analytics store, tăng chi phí và kéo dài thời gian cập nhật dữ liệu.

### Lọc theo khoảng thời gian có thể dùng index

Tránh bọc cột thời gian trong hàm ở điều kiện lọc nếu cần range scan:

~~~sql
-- Thường khó tận dụng index trên created_at
SELECT COUNT(*)
FROM analytics.fact_orders
WHERE DATE(created_at) = '2026-11-18';

-- Dạng range thường thân thiện với index hơn
SELECT COUNT(*)
FROM analytics.fact_orders
WHERE created_at >= '2026-11-18 00:00:00'
  AND created_at <  '2026-11-19 00:00:00';
~~~

Khoảng nửa mở [start, end) tránh lỗi ở phần microsecond và thuận tiện ghép các khoảng ngày liên tiếp. Mốc thời gian phải được tính theo timezone báo cáo rồi chuyển sang timezone lưu trữ nhất quán.

### Chỉ lấy cột cần thiết

Tránh SELECT * trên fact table lớn. Chỉ đọc dimension key và measure cần tổng hợp. Việc giảm dữ liệu đọc giúp giảm I/O và bộ nhớ cho sort/hash/grouping.

### Đọc execution plan

~~~sql
EXPLAIN
SELECT
    store_id,
    SUM(total_amount)
FROM analytics.fact_orders
WHERE created_at >= '2026-11-01'
  AND created_at <  '2026-12-01'
  AND status = 'PAID'
GROUP BY store_id;
~~~

Kiểm tra:

- Access type và partition pruning nếu bảng có partition.
- Key được chọn và thứ tự cột index.
- Estimated rows so với số hàng thực tế.
- Temporary table, filesort và chi phí GROUP BY.
- Join order và cardinality của dimension.

Nếu phiên bản MySQL hỗ trợ, dùng EXPLAIN ANALYZE trong môi trường phù hợp để xem số hàng và thời gian thực tế. EXPLAIN ANALYZE thực thi truy vấn; không chạy tùy tiện một báo cáo nặng trên primary production.

### Index cho workload báo cáo

Index composite phải phù hợp với bộ lọc và thứ tự truy cập. Ví dụ, báo cáo lọc theo status và created_at có thể cần index khác với báo cáo lọc theo store_id và created_at. Đừng thêm index theo từng báo cáo mà không đo chi phí ghi và dung lượng.

Trên fact table lớn, index phụ làm tăng storage, thời gian nạp và chi phí bảo trì. Kho phân tích có thể chọn ít index hơn OLTP, tận dụng partition theo thời gian hoặc định dạng columnar ở nền tảng khác.

### Giới hạn truy vấn ad hoc

Đặt timeout, giới hạn khoảng thời gian mặc định và giới hạn concurrency cho dashboard hoặc người dùng ad hoc. Báo cáo không có bộ lọc ngày có thể quét toàn bộ lịch sử; yêu cầu người dùng chọn khoảng thời gian hoặc chạy qua pipeline batch.

## 14. Tính nhất quán của báo cáo

Một báo cáo có thể đọc nhiều bảng hoặc nhiều batch nạp. Nếu mỗi phần được đọc ở thời điểm khác nhau, kết quả tổng có thể không nhất quán.

Các cách xử lý:

- Chạy truy vấn trong một consistent snapshot khi cần các bảng cùng thời điểm trên một MySQL instance.
- Ghi batch_id hoặc data_version vào các bảng analytics và chỉ công bố batch sau khi tất cả bảng liên quan đã nạp xong.
- Dùng staging schema/table rồi chuyển sang phiên bản đã xác minh.
- Hiển thị thời điểm dữ liệu được cập nhật cuối cùng trên dashboard.
- Với dữ liệu CDC, công bố checkpoint/GTID đã áp dụng để người dùng hiểu freshness.

Trong MySQL InnoDB, transaction với isolation REPEATABLE READ có thể dùng consistent read snapshot. Tuy nhiên, transaction đọc quá lâu có thể giữ snapshot cũ và làm tăng áp lực undo/purge. Báo cáo rất dài nên chạy trên analytics store hoặc snapshot riêng thay vì giữ transaction nhiều giờ trên primary.

### Freshness và correctness là hai chỉ số khác nhau

- **Freshness:** dữ liệu mới nhất đã được nạp đến thời điểm nào.
- **Correctness:** dữ liệu đã nạp có đầy đủ, không trùng, không thiếu và đúng quy tắc nghiệp vụ hay không.

Pipeline có thể rất mới nhưng sai do duplicate event; hoặc dữ liệu chính xác nhưng trễ một giờ. Theo dõi cả hai, không dùng riêng replica lag để khẳng định báo cáo đúng.

## 15. Backup, phục hồi và retention của dữ liệu archive

Archive vẫn là dữ liệu cần bảo vệ. Việc chuyển dữ liệu khỏi bảng nóng không có nghĩa có thể bỏ backup.

Chính sách backup cần xét:

- Backup database OLTP và archive theo lịch phù hợp.
- Backup analytics store hoặc tái tạo được từ nguồn/CDC nếu đó là lựa chọn có chủ đích.
- Binary log đủ dài để point-in-time recovery và phục hồi CDC.
- Manifest/checksum của file archive.
- Mã hóa, quyền truy cập và vị trí lưu backup.
- Thử restore định kỳ và đo RPO/RTO.
- Retention của backup phải nhất quán với chính sách xóa dữ liệu, kể cả thời gian backup cũ còn chứa bản ghi đã hết hạn.

Nếu yêu cầu xóa dữ liệu áp dụng cả bản sao lưu, cần có chính sách hết hạn backup hoặc quy trình xử lý theo nền tảng. Xóa một hàng khỏi primary không có nghĩa hàng đó biến mất ngay khỏi backup bất biến.

### Đối soát archive

Một manifest cho mỗi batch có thể lưu:

| Trường | Mục đích |
|---|---|
| run_id | Định danh lần chạy |
| source_table | Bảng nguồn |
| cutoff | Mốc retention cố định |
| min_key / max_key | Phạm vi khóa của batch |
| row_count | Số hàng đã xuất/nạp |
| checksum | Giá trị đối soát theo chunk |
| schema_version | Phiên bản schema dữ liệu |
| completed_at | Thời điểm xác minh |
| status | Trạng thái batch |

Checksum nên được tính theo chunk hoặc theo manifest có thứ tự ổn định. Không chỉ so sánh tổng SUM của một cột số vì hai tập dữ liệu khác nhau vẫn có thể cho cùng tổng.

## 16. Điều khiển tải và lịch chạy

Archive, ETL và báo cáo nên chạy theo lịch hoặc theo giới hạn tài nguyên. Tránh chạy đồng thời các job đều đọc toàn bảng hoặc rebuild index.

### Throttle job

- Giới hạn số hàng mỗi batch.
- Nghỉ giữa các batch khi CPU, I/O hoặc replica lag vượt ngưỡng.
- Giảm concurrency của ETL khi primary đang cao tải.
- Tách lịch archive, backup và báo cáo nặng nếu cùng dùng storage.
- Dừng an toàn khi dung lượng đĩa hoặc binlog vượt ngưỡng cảnh báo.
- Cho phép resume từ checkpoint đã xác minh.

### Theo dõi chỉ số

| Chỉ số | Vì sao quan trọng |
|---|---|
| OLTP p95/p99 latency | Phát hiện ảnh hưởng đến request người dùng |
| CPU và storage latency/IOPS | Đo cạnh tranh tài nguyên |
| Replica lag và applier queue | Đảm bảo dữ liệu đọc/CDC không tụt quá xa |
| Binlog volume và disk free | Tránh hết đĩa hoặc mất log cần cho CDC |
| Batch throughput và error rate | Phát hiện job chậm hoặc lỗi lặp |
| Summary freshness | Biết báo cáo đang phản ánh dữ liệu đến đâu |
| Archive row count/checksum | Đảm bảo dữ liệu được chuyển đủ |
| Long transaction và lock wait | Phát hiện job giữ snapshot/lock quá lâu |

Thiết lập ngưỡng theo baseline thực tế. Một giá trị replica lag 5 giây có thể chấp nhận được với dashboard nội bộ nhưng không phù hợp với màn hình xác nhận thanh toán.

## 17. Quy trình triển khai từ OLTP sang analytics

**Giai đoạn 1 — Khảo sát**

1. Xác định bảng tăng nhanh nhất và tỷ lệ dữ liệu nóng/lạnh.
2. Phân tích truy vấn báo cáo đang chạy trên primary.
3. Xác định SLA freshness, retention và thời gian truy xuất lịch sử.
4. Đo CPU, I/O, buffer pool, binlog và replica lag.
5. Xác định ràng buộc, FK, trigger và phụ thuộc ứng dụng.

**Giai đoạn 2 — Thiết kế**

1. Chọn archive table, archive instance hay object storage.
2. Chọn read replica, CDC hoặc ETL batch cho từng loại dữ liệu.
3. Định nghĩa grain, fact, dimension và summary table.
4. Chọn watermark/checkpoint, khóa idempotency và quy tắc late-arriving data.
5. Thiết kế backup, restore và retention cho bản gốc lẫn archive.

**Giai đoạn 3 — Diễn tập**

1. Dùng bản sao dữ liệu có kích thước gần production.
2. Chạy archive theo batch và thử resume sau lỗi.
3. So sánh row count, checksum và dữ liệu mẫu.
4. Mô phỏng replica lag, binlog retention và CDC restart.
5. Đối chiếu kết quả báo cáo với truy vấn nguồn đã kiểm chứng.
6. Đo ảnh hưởng lên OLTP và điều chỉnh throttle.

**Giai đoạn 4 — Triển khai**

1. Bắt đầu với một bảng hoặc một khoảng thời gian nhỏ.
2. Theo dõi latency, I/O, disk, replication và lỗi ứng dụng.
3. Xác minh archive/analytics trước khi xóa dữ liệu nóng.
4. Mở rộng dần số bảng và khoảng dữ liệu.
5. Chuyển dashboard sang analytics khi kết quả đã đối soát.

**Giai đoạn 5 — Vận hành**

1. Lập lịch archive, CDC, summary refresh và backup.
2. Theo dõi freshness, correctness và backlog.
3. Kiểm tra retention, legal hold và quy trình xóa.
4. Diễn tập restore dữ liệu archive và backfill báo cáo.
5. Cập nhật schema contract khi ứng dụng thay đổi bảng nguồn.

## 18. Những lỗi thiết kế thường gặp

- **Archive trước khi xác minh:** dữ liệu nguồn đã xóa nhưng archive thiếu hàng hoặc sai byte.
- **Dùng timestamp đơn làm watermark:** bỏ sót nhiều bản ghi có cùng thời điểm hoặc transaction commit trễ.
- **Cộng dồn summary khi job retry:** doanh thu hoặc số đơn bị nhân đôi.
- **Chỉ đọc từ replica:** báo cáo không thấy giao dịch mới và người dùng hiểu nhầm là mất dữ liệu.
- **Chạy báo cáo nặng trên replica duy nhất:** replication lag tăng và các luồng đọc khác bị ảnh hưởng.
- **Drop partition mà chưa archive:** mất toàn bộ dữ liệu trong partition.
- **Không xử lý FK/bảng con:** archive bản ghi cha làm mất tính toàn vẹn hoặc khiến ứng dụng không tra cứu được.
- **Không lưu schema version:** dữ liệu cũ không còn giải mã đúng sau khi schema thay đổi.
- **Không giữ binlog đủ lâu:** CDC không thể tiếp tục sau outage.
- **Xóa backup quá muộn hoặc không có retention:** dữ liệu đã xóa khỏi primary vẫn tồn tại trong bản sao lưu lâu hơn chính sách cho phép.

## 19. Checklist vận hành

**Retention và archive**

- [ ] Có chính sách retention theo từng nhóm dữ liệu.
- [ ] Chỉ archive bản ghi đã hoàn tất và đủ điều kiện.
- [ ] Cutoff và phạm vi batch được cố định.
- [ ] Copy và delete trong cùng transaction khi cùng instance.
- [ ] Khi khác server, có staging, manifest, checksum và xác minh trước purge.
- [ ] Đã kiểm tra FK, trigger, index và phụ thuộc ứng dụng.
- [ ] Job có checkpoint và chạy lại an toàn.

**Báo cáo và summary**

- [ ] Đã xác định grain của fact và summary table.
- [ ] Job refresh có tính idempotent.
- [ ] Có xử lý late-arriving update/delete và duplicate event.
- [ ] Query báo cáo có filter thời gian và index phù hợp.
- [ ] Đã kiểm tra EXPLAIN/EXPLAIN ANALYZE trong môi trường phù hợp.
- [ ] Dashboard hiển thị freshness/data version.

**Tách tải và phục hồi**

- [ ] Đã chọn primary, replica hoặc analytics store theo SLA freshness.
- [ ] Theo dõi replication lag và binlog retention.
- [ ] Có backup/restore và đối soát archive.
- [ ] Có giới hạn tải, batch size và cơ chế pause/resume.
- [ ] Đã diễn tập lỗi CDC, backfill và khôi phục dữ liệu lịch sử.

## Tài liệu tham khảo

- [MySQL Reference Manual — Replication](https://dev.mysql.com/doc/refman/8.0/en/replication.html)
- [MySQL Reference Manual — Binary Log](https://dev.mysql.com/doc/refman/8.0/en/binary-log.html)
- [MySQL Reference Manual — Partitioning](https://dev.mysql.com/doc/refman/8.0/en/partitioning.html)
- [MySQL Reference Manual — InnoDB Consistent Read](https://dev.mysql.com/doc/refman/8.0/en/innodb-consistent-read.html)
- [MySQL Reference Manual — EXPLAIN](https://dev.mysql.com/doc/refman/8.0/en/explain.html)
- [MySQL Reference Manual — LOAD DATA](https://dev.mysql.com/doc/refman/8.0/en/load-data.html)

## Kết luận

Mở rộng MySQL cho dữ liệu lịch sử và báo cáo đòi hỏi tách vòng đời dữ liệu khỏi tải giao dịch. Hãy định nghĩa retention trước, archive theo batch có checkpoint và chỉ purge sau khi xác minh; dùng partition khi có quy tắc thời gian và hiểu rõ giới hạn unique key/foreign key; tạo summary theo grain rõ ràng và refresh idempotent; chuyển tải phân tích sang replica hoặc analytics store theo yêu cầu freshness. Kết hợp CDC/ETL, backup, checksum, throttle và giám sát để dữ liệu cũ vẫn truy xuất được trong khi primary tiếp tục phục vụ OLTP ổn định.
