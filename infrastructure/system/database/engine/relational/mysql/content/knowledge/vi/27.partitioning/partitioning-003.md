# Chọn partition key theo thời gian hoặc miền dữ liệu

Partitioning chia một bảng logic thành nhiều partition được quản lý trong cùng một MySQL table. Khi chọn đúng partition key, MySQL có thể bỏ qua những partition không liên quan đến truy vấn (partition pruning), đồng thời DBA có thể quản lý dữ liệu theo từng khoảng thời gian hoặc từng miền giá trị. Nhưng partitioning không tự động làm mọi truy vấn nhanh hơn, không thay thế index và cũng không phân tán dữ liệu sang nhiều máy chủ.

Với module DATABASE_MYSQL, quyết định partition key cần xuất phát từ cách ứng dụng lọc dữ liệu, vòng đời dữ liệu và các ràng buộc khóa. Bài này so sánh partition theo thời gian với partition theo miền dữ liệu, hướng dẫn chọn RANGE, LIST, HASH hoặc KEY, và chỉ ra các giới hạn quan trọng của MySQL cần tính đến trước khi thiết kế schema.

## 1. Partition key quyết định điều gì?

Partition key là cột hoặc biểu thức MySQL dùng để xác định một hàng thuộc partition nào. Ví dụ:

- created_at có thể đưa đơn hàng vào partition theo tháng.
- region_code có thể đưa dữ liệu vào partition theo khu vực.
- tenant_id có thể được băm để phân phối các tenant qua một số partition cố định.

Partition key ảnh hưởng trực tiếp đến:

1. Khả năng MySQL loại bỏ partition không cần đọc.
2. Số hàng mà truy vấn phải tìm trong các partition còn lại.
3. Cách lưu giữ, lưu trữ hoặc xóa dữ liệu cũ.
4. Các khóa PRIMARY KEY và UNIQUE mà bảng có thể khai báo.
5. Khả năng sử dụng foreign key và các đặc tính schema khác.
6. Chi phí bảo trì khi thêm, gộp, tách hoặc loại partition.

Một partition key tốt thường nằm trong điều kiện lọc phổ biến, có miền giá trị và vòng đời phù hợp với chiến lược quản lý dữ liệu. Chọn key chỉ vì cột đó có nhiều giá trị khác nhau hoặc vì muốn chia bảng thành nhiều phần đều nhau là chưa đủ.

## 2. Partitioning không phải sharding và không thay thế index

Partitioning là phân chia ngang một bảng trong cùng một MySQL instance. Các partition thuộc cùng một bảng logic, dùng chung tên bảng và được truy vấn bằng SQL thông thường.

Sharding phân phối dữ liệu qua nhiều máy chủ hoặc database instance, thường cần tầng định tuyến và quản lý phân tán. Partitioning không tự tăng dung lượng CPU, RAM hoặc khả năng ghi bằng cách chuyển dữ liệu sang máy khác.

Partitioning cũng không thay thế index:

- Partition pruning loại bỏ partition không liên quan dựa trên điều kiện partition key.
- Index tìm hàng bên trong partition được chọn.
- Một truy vấn có thể prune xuống một partition rồi vẫn cần full scan nếu partition đó không có index phù hợp.
- Một truy vấn có index tốt nhưng không có điều kiện partition key vẫn có thể phải tìm trên nhiều partition.

Trong MySQL, index của bảng partitioned được tổ chức theo từng partition; không có global index bao phủ tất cả partition như một cấu trúc duy nhất. Truy vấn không lọc theo partition key có thể phải truy cập index ở nhiều partition. Vì vậy, cần thiết kế cả partition key và index theo workload thực tế.

## 3. Bắt đầu từ mẫu truy vấn và vòng đời dữ liệu

Trước khi chọn key, hãy thu thập các truy vấn thường gặp:

| Câu hỏi | Ý nghĩa đối với partition key |
|---|---|
| Ứng dụng thường lọc theo ngày tạo, ngày giao dịch hay ngày hết hạn? | Có thể chọn cột thời gian |
| Người dùng thường truy vấn theo tenant, vùng, loại dữ liệu hay mã khách hàng? | Có thể chọn cột miền dữ liệu |
| Truy vấn có luôn truyền partition key không? | Quyết định khả năng pruning |
| Dữ liệu cũ được xóa theo tháng/quý/năm không? | RANGE theo thời gian có thể thuận lợi |
| Có cần giữ từng miền dữ liệu độc lập về vận hành không? | Có thể cân nhắc LIST hoặc KEY |
| Các truy vấn có cần đảm bảo UNIQUE trên một cột không chứa partition key? | Có thể xung đột với quy tắc unique key của MySQL |
| Có cần foreign key tới hoặc từ bảng này không? | Ảnh hưởng lớn đến khả năng dùng partitioning với InnoDB |

Đừng bắt đầu bằng câu hỏi “chia thành bao nhiêu partition?”. Trước hết hãy xác định truy vấn nào cần được prune, dữ liệu được giữ bao lâu và ràng buộc schema nào không thể bỏ.

## 4. Partition theo thời gian: lựa chọn phổ biến cho dữ liệu có vòng đời

Partition theo thời gian phù hợp với bảng có dữ liệu tăng liên tục và được truy vấn theo khoảng thời gian, ví dụ:

- Đơn hàng theo created_at.
- Sự kiện hệ thống theo event_time.
- Giao dịch tài chính theo transaction_date.
- Log ứng dụng theo logged_at.

Với dữ liệu cần giữ 13 tháng, DBA có thể tạo partition theo tháng và loại bỏ partition cũ sau khi hết thời hạn lưu giữ. Việc loại một partition có thể nhanh hơn xóa hàng triệu dòng bằng DELETE, nhưng đây là thao tác DDL có tác động phá hủy dữ liệu và cần quy trình backup/retention rõ ràng.

### Ví dụ RANGE COLUMNS theo tháng

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id, created_at),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_status_created (status, created_at)
) ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p_before_2026 VALUES LESS THAN ('2026-01-01 00:00:00'),
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01 00:00:00'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01 00:00:00'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01 00:00:00'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

RANGE COLUMNS(created_at) chia hàng theo giá trị DATETIME. Partition p_before_2026 nhận các giá trị trước đầu năm 2026; p2026_01 nhận từ đầu năm đến trước đầu tháng 2; các mốc tiếp theo tiếp tục bao phủ những khoảng không chồng lấn. p_future nhận tất cả giá trị từ đầu tháng 4 trở đi.

Điều kiện lọc nên viết theo khoảng nửa mở:

~~~sql
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE created_at >= '2026-02-01 00:00:00'
  AND created_at <  '2026-03-01 00:00:00';
~~~

MySQL có thể xác định chỉ partition p2026_02 liên quan đến truy vấn. Khoảng nửa mở tránh phải đoán giá trị thời gian cuối cùng của ngày/tháng và hoạt động tốt với DATETIME có hoặc không có phần microsecond.

### Chọn cột thời gian nào?

Không phải cột thời gian nào cũng phù hợp:

- created_at: phù hợp nếu truy vấn và retention dựa trên thời điểm tạo bản ghi.
- event_time: phù hợp với dữ liệu sự kiện nếu thời gian sự kiện là tiêu chí truy vấn chính.
- business_date: phù hợp khi nghiệp vụ phân kỳ theo ngày kế toán hoặc ngày giao dịch.
- updated_at: thường thay đổi; nếu dùng làm partition key, UPDATE có thể phải chuyển hàng giữa partition và làm phức tạp việc quản lý.

Hãy chọn cột có ý nghĩa ổn định đối với vòng đời bản ghi. Nếu dữ liệu đến muộn hoặc được ghi backfill, cần xác định partition của nó theo thời gian sự kiện hay thời gian tiếp nhận.

## 5. Chọn độ hạt partition: ngày, tháng hay năm?

Độ hạt (granularity) quyết định mỗi partition chứa khoảng thời gian dài bao lâu.

| Độ hạt | Phù hợp khi | Đánh đổi |
|---|---|---|
| Theo ngày | Lượng dữ liệu mỗi ngày lớn, retention hoặc xử lý theo ngày | Nhiều partition và công việc tạo trước |
| Theo tháng | Workload báo cáo và retention theo tháng, lượng dữ liệu vừa/lớn | Xóa dữ liệu theo ngày cần xử lý trong partition |
| Theo quý | Dữ liệu tăng chậm, chu kỳ nghiệp vụ theo quý | Truy vấn theo tháng vẫn đọc partition của cả quý |
| Theo năm | Dữ liệu ít hoặc vòng đời theo năm | Partition lớn, bảo trì và loại bỏ một phần nhỏ khó hơn |

Không có một độ hạt đúng cho mọi bảng. Cần cân đối kích thước mỗi partition, số lượng partition, tần suất truy vấn và cách vận hành. Quá nhiều partition làm tăng metadata và chi phí lập kế hoạch; quá ít partition có thể không giúp pruning hoặc retention đủ linh hoạt.

Với bảng tăng rất nhanh, hãy ước lượng số hàng và dung lượng theo mỗi khoảng thời gian trước khi chọn độ hạt. Cũng cần tạo partition tương lai trước khi dữ liệu đi tới mốc mới.

## 6. Dùng RANGE cho miền số hoặc miền thời gian

RANGE phù hợp khi miền giá trị có thứ tự tự nhiên và có thể chia thành các khoảng không chồng lấn:

- ID tăng dần.
- Ngày/tháng/năm.
- Số tiền hoặc mức điểm.
- Khoảng nhiệt độ hoặc khoảng đo.

Ví dụ chia hoạt động khách hàng theo khoảng mã số:

~~~sql
CREATE TABLE customer_activity (
    customer_id BIGINT UNSIGNED NOT NULL,
    activity_id BIGINT UNSIGNED NOT NULL,
    activity_time DATETIME NOT NULL,
    PRIMARY KEY (customer_id, activity_id)
) ENGINE=InnoDB
PARTITION BY RANGE (customer_id) (
    PARTITION p_low VALUES LESS THAN (1000000),
    PARTITION p_mid VALUES LESS THAN (5000000),
    PARTITION p_high VALUES LESS THAN (10000000),
    PARTITION p_max VALUES LESS THAN (MAXVALUE)
);
~~~

Truy vấn theo customer_id trong một khoảng có thể prune partition tương ứng. Nhưng nếu truy vấn thường lọc theo activity_time mà không có customer_id, cách phân vùng theo customer_id có thể không hỗ trợ truy vấn đó.

Với kiểu DATE/DATETIME, RANGE COLUMNS thường rõ ràng hơn việc bọc cột trong hàm số. Với kiểu số, có thể dùng RANGE(column) hoặc RANGE COLUMNS(column) tùy yêu cầu và kiểu dữ liệu.

## 7. Dùng LIST khi miền dữ liệu có tập giá trị nhỏ, ổn định

LIST phù hợp khi giá trị partition key thuộc một tập miền đã biết, ví dụ vùng kinh doanh hoặc loại dữ liệu:

~~~sql
CREATE TABLE regional_sales (
    region_code VARCHAR(20) NOT NULL,
    sale_id BIGINT UNSIGNED NOT NULL,
    sale_date DATE NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (region_code, sale_id)
) ENGINE=InnoDB
PARTITION BY LIST COLUMNS (region_code) (
    PARTITION p_north VALUES IN ('NORTH', 'NORTHEAST'),
    PARTITION p_central VALUES IN ('CENTRAL'),
    PARTITION p_south VALUES IN ('SOUTH', 'SOUTHWEST')
);
~~~

Khi truy vấn có region_code = 'NORTH', MySQL có thể chỉ đọc partition p_north. LIST COLUMNS cho phép dùng trực tiếp các giá trị cột, bao gồm chuỗi.

LIST phù hợp với tập giá trị hữu hạn và được quản lý rõ. Nếu hệ thống thường xuyên thêm region/tenant mới, mỗi thay đổi có thể cần DDL để bổ sung partition. Hàng có giá trị không được liệt kê sẽ không thể được chèn vào bảng nếu không có partition phù hợp.

Không nên tạo một partition cho mỗi khách hàng nếu số khách hàng có thể tăng đến hàng chục nghìn hoặc hàng triệu. Trường hợp đó nên cân nhắc KEY/HASH với số partition cố định hoặc một mô hình khác.

## 8. Dùng HASH hoặc KEY để phân phối đều theo miền giá trị

Nếu không có khoảng giá trị hoặc tập danh mục cố định, có thể dùng HASH hoặc KEY để phân phối hàng vào số partition cố định.

### HASH

~~~sql
CREATE TABLE tenant_events (
    tenant_id BIGINT UNSIGNED NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    event_time DATETIME NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
) ENGINE=InnoDB
PARTITION BY HASH (tenant_id)
PARTITIONS 16;
~~~

MySQL áp dụng biểu thức hash để xác định partition. HASH thường dùng cho biểu thức số nguyên. Với 16 partition, dữ liệu được phân phối theo kết quả hash, không có nghĩa mỗi partition luôn chứa chính xác 1/16 số hàng.

### KEY

~~~sql
CREATE TABLE tenant_events_by_key (
    tenant_id VARCHAR(64) NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    event_time DATETIME NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
) ENGINE=InnoDB
PARTITION BY KEY (tenant_id)
PARTITIONS 16;
~~~

KEY dùng hàm hash nội bộ của MySQL trên các cột được chỉ định và phù hợp với nhiều kiểu dữ liệu hơn HASH. Không cần tự viết biểu thức băm.

HASH/KEY có thể phân phối dữ liệu trên nhiều partition nhưng thường không giúp retention theo thời gian. Nếu cần xóa dữ liệu cũ theo tháng, partition theo thời gian thường phù hợp hơn. Nếu truy vấn theo tenant_id, HASH/KEY có thể prune theo tenant khi optimizer xác định được partition.

## 9. So sánh RANGE, LIST, HASH và KEY

| Kiểu partitioning | Khi nên cân nhắc | Ví dụ partition key | Hạn chế cần tính |
|---|---|---|---|
| RANGE / RANGE COLUMNS | Dữ liệu có thứ tự và khoảng giá trị rõ | created_at, transaction_date, numeric ID | Cần quản lý mốc; giá trị vượt partition cuối sẽ lỗi nếu không có MAXVALUE |
| LIST / LIST COLUMNS | Miền giá trị nhỏ, hữu hạn, ổn định | region_code, event_type | Giá trị mới cần được ánh xạ hoặc thêm partition |
| HASH | Phân phối theo biểu thức số nguyên | tenant_id, customer_id | Khó loại bỏ dữ liệu theo thời gian; không bảo đảm phân phối hoàn toàn đều |
| KEY | Phân phối theo hash nội bộ trên một hay nhiều cột | tenant_id dạng chuỗi hoặc khóa ghép | Ít kiểm soát cách băm; không thay thế sharding |

Chọn loại partitioning theo câu hỏi cần giải quyết. Nếu retention theo tháng là mục tiêu chính, HASH không phải lựa chọn tương đương RANGE. Nếu cần chia theo một số khu vực cố định, LIST thường thể hiện ý định rõ hơn HASH.

## 10. Partition pruning: điều kiện quan trọng để partition có ích

Partition pruning là khả năng MySQL loại bỏ các partition không thể chứa hàng thỏa mãn điều kiện truy vấn. Nó giảm số partition cần truy cập, nhưng không tự bảo đảm số hàng đọc bên trong partition là nhỏ.

Ví dụ bảng orders được partition theo created_at:

~~~sql
-- Điều kiện trực tiếp trên partition key: thuận lợi cho pruning
SELECT order_id, total_amount
FROM orders
WHERE created_at >= '2026-02-01'
  AND created_at < '2026-03-01';

-- Không có điều kiện partition key: có thể phải kiểm tra nhiều partition
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 42;
~~~

Truy vấn thứ hai vẫn có thể dùng index customer_id bên trong từng partition, nhưng không có điều kiện thời gian để loại các partition khác. Tùy phiên bản và kế hoạch, MySQL có thể phải truy cập index của nhiều partition.

Giữ điều kiện có thể suy luận trực tiếp từ partition key. Ví dụ thay vì:

~~~sql
WHERE YEAR(created_at) = 2026
~~~

hãy dùng khoảng:

~~~sql
WHERE created_at >= '2026-01-01'
  AND created_at < '2027-01-01'
~~~

Biểu thức hàm trên cột có thể làm pruning khó hơn hoặc không thực hiện được như mong đợi. Dùng khoảng trực tiếp là cách viết rõ ràng và thường thuận lợi cho cả partition pruning lẫn index range access.

## 11. Kiểm tra partition nào được sử dụng

Dùng EXPLAIN để xem partition được chọn:

~~~sql
EXPLAIN
SELECT order_id, customer_id, created_at
FROM orders
WHERE created_at >= '2026-02-01'
  AND created_at < '2026-03-01';
~~~

Trong EXPLAIN dạng bảng, cột partitions liệt kê partition được optimizer xem xét cho truy vấn. Nếu điều kiện chỉ thuộc một tháng nhưng danh sách vẫn có nhiều partition, hãy kiểm tra kiểu dữ liệu, biểu thức partition và cách viết điều kiện.

Có thể xem cấu trúc partition trong metadata:

~~~sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY PARTITION_ORDINAL_POSITION;
~~~

TABLE_ROWS của InnoDB là ước lượng, không phải số đếm chính xác. Dùng COUNT(*) với điều kiện phù hợp nếu cần số liệu chính xác, và cân nhắc chi phí khi bảng lớn.

## 12. Quy tắc quan trọng: mọi unique key phải chứa partition key

MySQL yêu cầu tất cả cột được dùng trong partitioning expression phải nằm trong mọi unique key của bảng, bao gồm PRIMARY KEY. Điều này có nghĩa partition key ảnh hưởng đến khả năng đảm bảo tính duy nhất toàn bảng.

Ví dụ bảng orders partition theo created_at không thể dùng:

~~~sql
-- Không hợp lệ nếu bảng partition theo created_at
PRIMARY KEY (order_id)
~~~

Thay vào đó, ví dụ dùng:

~~~sql
PRIMARY KEY (order_id, created_at)
~~~

Nhưng composite key này chỉ bảo đảm cặp (order_id, created_at) là duy nhất; nó không bảo đảm order_id đơn lẻ duy nhất trên toàn bảng. Nếu nghiệp vụ cần order_id duy nhất toàn cục, phải thiết kế cơ chế khác, ví dụ bảng registry không partition có UNIQUE(order_id), hoặc cấp ID toàn cục từ ứng dụng/dịch vụ ID. Cơ chế registry cần được cập nhật cùng transaction để tránh lệch dữ liệu.

Quy tắc này cần được kiểm tra trước khi triển khai partitioning. Nếu schema hiện tại có nhiều unique key không chứa partition key, việc partition hóa có thể buộc thay đổi mô hình khóa và cách các bảng khác tham chiếu dữ liệu.

## 13. Foreign key và các giới hạn schema của InnoDB partitioning

Trong MySQL, bảng InnoDB được partition do người dùng định nghĩa không thể chứa foreign key và cũng không thể được bảng khác tham chiếu bằng foreign key. Đây là giới hạn kiến trúc cần xem xét sớm.

Nếu bảng orders hiện có:

- PRIMARY KEY(order_id)
- FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
- UNIQUE(order_ref)

thì việc partition theo created_at không chỉ là thêm PARTITION BY. Phải giải quyết:

1. PRIMARY KEY và mọi unique key có chứa created_at hay không.
2. Ứng dụng có thể mất ràng buộc foreign key ở database hay không.
3. Kiểm tra tham chiếu sẽ được chuyển sang tầng ứng dụng, transaction hoặc mô hình dữ liệu nào.
4. Các truy vấn JOIN và thao tác xóa/cập nhật có giữ được tính toàn vẹn không.

Nếu foreign key là yêu cầu bắt buộc, bảng InnoDB partitioned có thể không phù hợp. Không nên bỏ foreign key chỉ để đạt partition pruning nếu rủi ro toàn vẹn dữ liệu lớn hơn lợi ích.

## 14. Bảo trì partition theo thời gian

Một lợi ích vận hành của RANGE partitioning là có thể thêm khoảng mới hoặc loại bỏ khoảng dữ liệu cũ bằng thao tác partition DDL.

### Tách partition tương lai để tạo tháng mới

Với bảng orders có p_future = MAXVALUE, trước khi bước sang tháng 4/2026 có thể tách partition tương lai:

~~~sql
ALTER TABLE orders
REORGANIZE PARTITION p_future INTO (
    PARTITION p2026_04 VALUES LESS THAN ('2026-05-01 00:00:00'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

Các hàng đã nằm trong p_future được phân phối lại vào partition mới hoặc p_future theo giá trị created_at. Thao tác này có thể tốn thời gian và tài nguyên tùy lượng dữ liệu cần di chuyển; hãy thử trên môi trường gần production và lên kế hoạch dung lượng.

### Loại partition cũ

~~~sql
ALTER TABLE orders DROP PARTITION p2026_01;
~~~

DROP PARTITION loại bỏ toàn bộ dữ liệu nằm trong partition đó. Đây là thao tác phá hủy dữ liệu, không tương đương DELETE có thể rollback bằng ROLLBACK trong transaction. Cần xác minh retention, backup, yêu cầu audit và trạng thái replication trước khi chạy.

Partition DDL là DDL; không dựa vào transaction ứng dụng để rollback thao tác này. Hãy kiểm tra tài liệu phiên bản MySQL, hành vi atomic DDL và tác động replication/backup trước khi thay đổi partition trên bảng lớn.

## 15. Chọn partition theo miền dữ liệu: các tình huống thường gặp

### Theo khu vực

LIST COLUMNS(region_code) phù hợp khi số khu vực ít và ít thay đổi. Truy vấn theo region có thể prune partition. Nếu cần báo cáo toàn quốc, truy vấn vẫn phải đọc các partition liên quan đến toàn bộ khu vực.

### Theo tenant

Nếu có hàng triệu tenant, không tạo một partition cho mỗi tenant. Có thể dùng KEY/HASH(tenant_id) với số partition cố định, nhưng chỉ có ích nếu truy vấn thường truyền tenant_id và phân phối đủ cân bằng. Cần nhớ cách này vẫn nằm trong một MySQL instance, không phải cách cô lập tenant như sharding.

### Theo loại sự kiện

LIST(event_type) phù hợp khi tập loại sự kiện nhỏ và ổn định. Nếu loại sự kiện mới thường xuyên xuất hiện, quy trình thêm partition hoặc mapping cần được quản lý; nếu không, insert có thể thất bại.

### Theo ID tăng dần

RANGE(id) có thể phù hợp khi truy vấn theo khoảng ID và cần quản lý dữ liệu cũ theo khoảng. Nhưng nếu truy vấn chủ yếu theo thời gian, partition theo ID có thể không giúp pruning theo ngày.

## 16. Các tiêu chí không nên bỏ qua khi chọn partition key

Đánh giá từng ứng viên theo các tiêu chí:

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| Query alignment | Điều kiện WHERE phổ biến có lọc theo partition key không? |
| Pruning | MySQL có thể xác định partition cần đọc từ literal/parameter không? |
| Retention | Có thể xóa hoặc lưu trữ dữ liệu theo partition mà không ảnh hưởng dữ liệu cần giữ không? |
| Cardinality | Số giá trị và phân bố có phù hợp với RANGE/LIST/HASH/KEY không? |
| Skew | Một partition có nguy cơ lớn hơn nhiều partition khác không? |
| Unique constraints | Mọi PRIMARY KEY/UNIQUE có thể chứa partition key không? |
| Foreign keys | Bảng có cần khai báo hoặc được tham chiếu bằng FK không? |
| Joins | Các bảng liên quan có cùng cách truy cập hay truy vấn sẽ phải quét nhiều partition? |
| Maintenance | Ai tạo partition mới, khi nào, và xử lý giá trị vượt miền ra sao? |
| Operations | Backup, restore, replication, monitoring và migration có hỗ trợ quy trình mới không? |

Không chọn partition key chỉ dựa trên cardinality. Một cột có hàng triệu giá trị nhưng không xuất hiện trong điều kiện lọc và không liên quan retention có thể không đem lại lợi ích.

## 17. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Chia nhiều partition thì truy vấn nào cũng nhanh | Chỉ truy vấn prune được partition mới giảm phạm vi đọc; truy vấn khác có thể phải truy cập nhiều partition |
| Partitioning tự phân tán tải sang nhiều máy | Partitioning của MySQL nằm trong một instance; sharding là bài toán khác |
| Có partition là không cần index | Index vẫn cần để tìm hàng bên trong partition |
| HASH luôn chia đều dữ liệu | Phân bố phụ thuộc giá trị và hàm hash; không bảo đảm mỗi partition có số hàng bằng nhau |
| Có thể giữ UNIQUE(order_id) khi partition theo created_at | MySQL yêu cầu partition key nằm trong mọi unique key |
| InnoDB partitioned table vẫn dùng foreign key bình thường | Bảng InnoDB partitioned do người dùng định nghĩa không hỗ trợ FK theo các chiều này |
| DROP PARTITION giống DELETE | DROP PARTITION loại bỏ toàn bộ dữ liệu partition bằng DDL và không rollback như DML transaction |
| Nên tạo một partition cho mỗi tenant | Số tenant lớn làm metadata và vận hành phức tạp; cân nhắc KEY/HASH hoặc sharding |

## 18. Quy trình thiết kế và kiểm chứng partition key

1. Thu thập truy vấn đại diện, điều kiện WHERE, JOIN, ORDER BY và yêu cầu retention.
2. Liệt kê các cột ứng viên: thời gian, ID, tenant, vùng hoặc loại dữ liệu.
3. Chọn RANGE/LIST/HASH/KEY theo miền giá trị và vòng đời.
4. Kiểm tra mọi PRIMARY KEY/UNIQUE có thể chứa partition key.
5. Kiểm tra giới hạn foreign key và các tính năng schema cần thiết.
6. Ước lượng số hàng/dung lượng mỗi partition và số partition trong nhiều năm.
7. Thiết kế index bên trong partition theo truy vấn thực tế.
8. Tạo dữ liệu thử đại diện, bao gồm dữ liệu lệch và giá trị biên.
9. Dùng EXPLAIN xem cột partitions có loại bỏ partition không cần thiết không.
10. Dùng EXPLAIN ANALYZE trên môi trường phù hợp để đo số hàng và thời gian thực tế.
11. Thử thêm partition, reorganize và drop partition trên bản sao dữ liệu.
12. Xây dựng job tạo partition tương lai, cảnh báo thiếu partition và quy trình phục hồi.

## 19. Bài tập thực hành

1. Tạo bảng orders partition theo RANGE COLUMNS(created_at) với các partition trước 2026, ba partition tháng và một partition tương lai.
2. Nạp dữ liệu thuộc các tháng khác nhau; chạy EXPLAIN cho truy vấn một tháng và kiểm tra danh sách partitions.
3. Chạy truy vấn chỉ lọc customer_id, không lọc created_at; quan sát vì sao pruning theo tháng không giúp loại partition.
4. Thử viết YEAR(created_at) = ... rồi viết lại thành khoảng nửa mở; so sánh kế hoạch.
5. Tạo bảng regional_sales với LIST COLUMNS(region_code); thử insert một region chưa được khai báo và quan sát kết quả.
6. Tạo bảng tenant_events với KEY(tenant_id) PARTITIONS 16; kiểm tra cách truy vấn theo tenant_id và truy vấn không có tenant_id.
7. Thử khai báo PRIMARY KEY(order_id) trên bảng partition theo created_at; giải thích vì sao không hợp lệ, sau đó đổi thành khóa ghép.
8. Thử thiết kế foreign key cho bảng InnoDB partitioned; ghi nhận giới hạn và đánh giá phương án mô hình dữ liệu thay thế.
9. Dùng REORGANIZE PARTITION để tách p_future thành partition tháng mới trên dữ liệu thử.
10. Dùng DROP PARTITION trên bản sao dữ liệu; đối chiếu số hàng trước và sau, đồng thời mô tả bước backup/approval cần có.

Bạn hoàn thành bài khi chọn được partition key dựa trên truy vấn và vòng đời dữ liệu, giải thích được trade-off giữa partition theo thời gian và miền dữ liệu, kiểm tra được pruning bằng EXPLAIN, và nhận diện được giới hạn unique key/foreign key trước khi triển khai. Partitioning chỉ nên được áp dụng khi lợi ích truy cập hoặc vận hành đã được đo và lớn hơn chi phí thay đổi schema.
