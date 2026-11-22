# Mục tiêu phân vùng và giới hạn khác với chia dữ liệu giữa nhiều máy chủ

Partitioning (phân vùng bảng) trong MySQL chia các hàng của **một bảng logic** thành nhiều partition được quản lý bên trong cùng một MySQL instance. Ứng dụng vẫn truy vấn bảng bằng tên bảng thông thường; MySQL quyết định partition nào cần đọc hoặc ghi. Mục tiêu thường gặp là loại bỏ phần dữ liệu không liên quan bằng partition pruning, quản lý vòng đời dữ liệu theo khoảng thời gian và thực hiện một số thao tác bảo trì trên từng phần dữ liệu.

Partitioning không phải sharding. Nó không tự phân phối các hàng của một bảng sang nhiều MySQL server, không tạo thêm năng lực CPU/RAM/IOPS từ nhiều máy và không tự giải quyết giao dịch phân tán. Sharding chia dữ liệu giữa nhiều instance độc lập, cần cơ chế định tuyến và quản lý khóa ở cấp ứng dụng hoặc middleware. Replication lại sao chép dữ liệu sang server khác để phục vụ tính sẵn sàng hoặc đọc; nó cũng không đồng nghĩa với partitioning.

Chọn partitioning khi cấu trúc truy vấn và vòng đời dữ liệu thực sự phù hợp với ranh giới partition. Nếu truy vấn thường đọc toàn bộ bảng, điều kiện không thể pruning hoặc bảng chưa đủ lớn để cần quản lý theo partition, partitioning có thể không mang lại lợi ích và còn tăng độ phức tạp schema/vận hành.

## 1. Partitioning là gì?

Với partitioning theo chiều ngang (horizontal partitioning), các hàng của cùng một bảng được chia thành những nhóm riêng theo quy tắc partition. Mỗi partition chứa một phần hàng, nhưng từ góc nhìn SQL, chúng vẫn thuộc một bảng:

```sql
SELECT *
FROM sales_events
WHERE occurred_at >= '2026-01-01'
  AND occurred_at <  '2026-04-01';
```

Ứng dụng không cần tự ghép nhiều bảng con. MySQL có thể xác định điều kiện ngày chỉ liên quan đến một hoặc một số partition và chỉ truy cập các partition đó.

Một partitioned table có các đặc điểm chính:

- Một tên bảng logic và một định nghĩa schema.
- Các hàng được phân phối vào partition theo partitioning expression hoặc partitioning key.
- Mỗi partition là một phần lưu trữ bên trong bảng, không phải một MySQL server độc lập.
- Index của bảng partitioned được tổ chức trong từng partition; MySQL không cung cấp global index B-tree trải xuyên qua tất cả partition.
- Truy vấn không cần chỉ rõ tên partition; optimizer có thể pruning dựa trên điều kiện WHERE.

Partitioning thường được gọi là chia dữ liệu theo hàng. Nó khác vertical partitioning, vốn tách các nhóm cột thành những bảng khác nhau, thường nối lại bằng khóa chính.

## 2. Mục tiêu chính của partitioning

Partitioning có thể giải quyết một số vấn đề cụ thể:

1. **Partition pruning:** tránh đọc partition không thể chứa hàng thỏa điều kiện lọc.
2. **Quản lý vòng đời dữ liệu:** loại bỏ dữ liệu cũ theo partition, chẳng hạn bỏ một tháng hoặc một quý đã hết thời hạn lưu.
3. **Bảo trì theo phạm vi:** thao tác với một phần dữ liệu có ranh giới rõ ràng thay vì quét/xóa từng hàng trên toàn bảng.
4. **Tổ chức dữ liệu lớn:** nhóm dữ liệu theo thời gian, tenant, vùng hoặc khóa phân phối phù hợp với cách truy vấn.
5. **Vận hành có quy tắc:** dễ lập lịch tạo partition tương lai, kiểm tra partition thiếu và lưu trữ dữ liệu theo kỳ.

Lợi ích không tự động xuất hiện chỉ vì bảng có nhiều partition. Nếu truy vấn không lọc theo partition key hoặc cần đọc mọi partition, MySQL vẫn phải xử lý nhiều phần dữ liệu. Partitioning cũng không thay thế index: sau khi pruning, optimizer vẫn cần access path phù hợp bên trong từng partition.

## 3. Partitioning không phải sharding

Đây là khác biệt quan trọng nhất khi thiết kế hệ thống lớn:

| Tiêu chí | MySQL partitioning | Sharding |
| --- | --- | --- |
| Phạm vi chia dữ liệu | Nhiều partition trong một bảng trên một MySQL instance | Dữ liệu được chia giữa nhiều instance/server độc lập |
| Định tuyến | MySQL optimizer/storage engine chọn partition | Ứng dụng, proxy hoặc middleware định tuyến đến shard |
| Tên bảng | Một bảng logic | Thường có schema/bảng tương ứng trên nhiều shard |
| Năng lực máy chủ | Vẫn dùng tài nguyên của instance chứa bảng | Có thể phân tải CPU, RAM, I/O và dung lượng qua nhiều máy |
| JOIN giữa hai phần dữ liệu | Có thể thực hiện trong cùng instance theo SQL bình thường | Có thể cần scatter-gather hoặc xử lý ở ứng dụng |
| Giao dịch | Transaction InnoDB trong cùng instance | Giao dịch xuyên shard phức tạp; có thể cần saga hoặc distributed transaction |
| Unique key | Chịu các quy tắc khóa duy nhất của partitioned table | Cần chiến lược ID/unique toàn cụm ở cấp hệ thống |
| Vận hành | Quản lý partition, index và tablespace trong instance | Quản lý shard placement, routing, rebalance, failover và backup từng shard |

Ví dụ: chia bảng `orders` thành partition theo tháng trên một server vẫn là partitioning. Đặt dữ liệu khách hàng 1–100000 trên server A, khách hàng 100001–200000 trên server B là sharding nếu ứng dụng định tuyến truy vấn đến server tương ứng.

Partitioning không phải cách scale-out nhiều máy. Nếu nút thắt là CPU, RAM hoặc I/O của một server, chia bảng thành partition trên chính server đó không tạo thêm tài nguyên phần cứng. Khi cần phân tải ngang qua nhiều máy, phải thiết kế sharding hoặc kiến trúc phân tán phù hợp.

## 4. Phân biệt partitioning, replication và backup

Ba khái niệm thường bị nhầm lẫn:

| Cơ chế | Mục tiêu | Dữ liệu ở server khác? |
| --- | --- | --- |
| Partitioning | Chia một bảng thành các phần quản lý và truy cập trong cùng instance | Không tự tạo server khác |
| Replication | Sao chép thay đổi/dữ liệu từ source sang replica để tăng khả năng sẵn sàng hoặc phục vụ đọc | Có, nhưng thường là bản sao của cùng tập dữ liệu logic |
| Backup | Tạo bản sao có thể dùng để phục hồi sau mất dữ liệu hoặc sự cố | Có thể được lưu ở nơi khác; không phải cơ chế phân vùng truy vấn |
| Sharding | Chia tập dữ liệu giữa các instance để mở rộng dung lượng và tải | Có, mỗi shard sở hữu một phần dữ liệu |

Một MySQL replica có thể chứa bảng đã partition giống source. Điều đó không biến các partition trên source thành các shard nằm ở replica. Replication sao chép thay đổi; sharding định tuyến các phần dữ liệu khác nhau đến các instance khác nhau.

Partitioning cũng không phải backup. `DROP PARTITION` có thể loại bỏ dữ liệu khỏi bảng; muốn khôi phục cần backup, archive hoặc bản sao phù hợp. Không dùng partition maintenance thay cho chính sách backup/restore.

## 5. Các kiểu partitioning trong MySQL

MySQL hỗ trợ các phương pháp partitioning phổ biến:

| Phương pháp | Cách phân phối hàng | Trường hợp thường gặp |
| --- | --- | --- |
| `RANGE` / `RANGE COLUMNS` | Chọn partition theo khoảng giá trị | Dữ liệu theo ngày, tháng, năm hoặc khoảng ID |
| `LIST` / `LIST COLUMNS` | Chọn partition theo danh sách giá trị | Khu vực, loại nghiệp vụ hoặc nhóm tenant hữu hạn |
| `HASH` | Dùng biểu thức số nguyên để phân phối hàng theo hash | Chia tương đối đều theo khóa, không cần ranh giới nghiệp vụ rõ |
| `KEY` | MySQL dùng hàm hash nội bộ trên một hoặc nhiều cột | Phân phối theo khóa mà không tự viết biểu thức hash |

`RANGE` và `LIST` có thể dùng partition pruning hiệu quả khi điều kiện truy vấn phù hợp với ranh giới. `HASH` và `KEY` thường chia đều theo giá trị khóa hơn là tạo các khoảng có ý nghĩa cho việc xóa dữ liệu cũ.

MySQL cũng hỗ trợ subpartitioning trong một số kết hợp, chẳng hạn `RANGE` kết hợp `HASH`. Subpartitioning tăng số phần quản lý và độ phức tạp; chỉ dùng khi có yêu cầu rõ ràng và đã đo lợi ích.

## 6. RANGE COLUMNS: ví dụ phân vùng dữ liệu theo thời gian

Giả sử hệ thống lưu sự kiện bán hàng và thường truy vấn theo quý. Có thể dùng `RANGE COLUMNS` với cột `DATE`:

```sql
CREATE TABLE sales_events (
    event_id BIGINT UNSIGNED NOT NULL,
    occurred_at DATE NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (event_id, occurred_at),
    KEY idx_sales_tenant_date (tenant_id, occurred_at)
) ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (occurred_at) (
    PARTITION p_before_2026 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026q1 VALUES LESS THAN ('2026-04-01'),
    PARTITION p2026q2 VALUES LESS THAN ('2026-07-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Các partition `RANGE` có ranh giới tăng dần. `p2026q1` chứa ngày từ `2026-01-01` đến trước `2026-04-01`; `p2026q2` chứa ngày từ `2026-04-01` đến trước `2026-07-01`. `p_before_2026` chứa các ngày trước năm 2026 và `p_future` nhận các ngày từ `2026-07-01` trở đi.

### 6.1. Lưu ý về khóa chính và unique key

Trong MySQL, mọi cột được dùng trong partitioning expression phải xuất hiện trong mọi unique key của bảng, bao gồm primary key. Vì partition key ở ví dụ là `occurred_at`, khóa chính được định nghĩa là `(event_id, occurred_at)`.

Điều này có hệ quả thiết kế: bảng trên không thể khai báo `UNIQUE(event_id)` nếu `occurred_at` không nằm trong unique key đó. Database chỉ có thể bảo đảm duy nhất theo cặp `(event_id, occurred_at)`, không tự bảo đảm `event_id` duy nhất toàn bảng.

Nếu nghiệp vụ bắt buộc `event_id` duy nhất toàn cục, cần thiết kế ID sao cho không trùng qua mọi partition, hoặc dùng một bảng registry/định danh riêng có unique key không bị giới hạn bởi partitioning. Không được giả định mỗi partition có một unique index riêng sẽ tự tạo ra unique constraint toàn bảng.

## 7. Partition pruning: lợi ích hiệu năng quan trọng nhất

Partition pruning là khả năng optimizer loại bỏ các partition chắc chắn không thể chứa hàng thỏa điều kiện. Với bảng theo ngày ở ví dụ trên:

```sql
SELECT event_id, tenant_id, amount
FROM sales_events
WHERE occurred_at >= '2026-01-01'
  AND occurred_at <  '2026-04-01';
```

MySQL có thể chỉ truy cập partition `p2026q1`, thay vì đọc tất cả partition. Đây là lợi ích thực tế nhất của partitioning đối với truy vấn lọc theo partition key.

Kiểm tra partition được chọn:

```sql
EXPLAIN
SELECT event_id, tenant_id, amount
FROM sales_events
WHERE occurred_at >= '2026-01-01'
  AND occurred_at <  '2026-04-01';
```

Trong output `EXPLAIN` dạng bảng, cột `partitions` cho biết partition mà kế hoạch dự kiến truy cập. Nếu chỉ thấy `p2026q1`, pruning đã loại các partition khác cho truy vấn đó.

### 7.1. Điều kiện truy vấn cần phù hợp với partition key

Để pruning hiệu quả, viết điều kiện trực tiếp trên cột partition theo khoảng rõ ràng:

```sql
WHERE occurred_at >= '2026-01-01'
  AND occurred_at <  '2026-04-01'
```

Tránh biến đổi cột partition trong biểu thức nếu không cần:

```sql
-- Không ưu tiên: áp dụng hàm lên cột partition
WHERE YEAR(occurred_at) = 2026
```

Điều kiện dùng hàm hoặc phép biến đổi có thể khiến optimizer khó suy ra partition cần truy cập, tùy biểu thức partition và khả năng tối ưu của phiên bản. Hãy viết predicate tương đương theo khoảng ngày và xác nhận bằng `EXPLAIN`.

Không có partition pruning nếu truy vấn không giới hạn partition key hoặc nếu điều kiện buộc đọc mọi partition. Một truy vấn lọc theo `tenant_id` nhưng không lọc `occurred_at` có thể cần xem xét tất cả partition theo ngày, dù có index tenant ở từng partition.

## 8. LIST COLUMNS: phân vùng theo danh mục hữu hạn

`LIST COLUMNS` phù hợp khi cột phân vùng có tập giá trị nghiệp vụ hữu hạn và các giá trị có thể được gán vào từng partition:

```sql
CREATE TABLE regional_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    region_code CHAR(2) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_id, region_code),
    KEY idx_regional_orders_created (created_at)
) ENGINE=InnoDB
PARTITION BY LIST COLUMNS (region_code) (
    PARTITION p_asia VALUES IN ('VN', 'SG', 'TH'),
    PARTITION p_europe VALUES IN ('DE', 'FR', 'GB'),
    PARTITION p_america VALUES IN ('US', 'CA'),
    PARTITION p_other VALUES IN ('AU', 'NZ')
);
```

Truy vấn lọc theo `region_code` có thể pruning đến partition tương ứng. Nếu thêm một mã vùng chưa nằm trong danh sách, insert sẽ thất bại vì không có partition nhận giá trị đó. Cần có quy trình thêm partition hoặc thiết kế partition dự phòng phù hợp.

`LIST` hữu ích khi miền giá trị được quản lý ổn định. Nếu danh sách tenant hoặc vùng thay đổi liên tục và có hàng nghìn giá trị, cần đánh giá chi phí quản lý partition và cân nhắc cách phân phối khác.

## 9. HASH và KEY: phân phối hàng theo khóa

`HASH` dùng biểu thức số nguyên để tính partition. Ví dụ:

```sql
CREATE TABLE user_activity (
    activity_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    occurred_at DATETIME NOT NULL,
    PRIMARY KEY (activity_id, user_id)
) ENGINE=InnoDB
PARTITION BY HASH (user_id)
PARTITIONS 8;
```

MySQL tính giá trị hash theo biểu thức và chọn một trong tám partition. Cách này có thể phân phối hàng theo `user_id`, nhưng không tạo ranh giới thời gian để drop dữ liệu cũ theo tháng. Nếu cần tìm theo thời gian mà không lọc `user_id`, truy vấn có thể phải xét nhiều partition.

`KEY` để MySQL thực hiện hash trên một hoặc nhiều cột:

```sql
CREATE TABLE tenant_events (
    event_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    occurred_at DATETIME NOT NULL,
    PRIMARY KEY (event_id, tenant_id)
) ENGINE=InnoDB
PARTITION BY KEY (tenant_id)
PARTITIONS 16;
```

`HASH` và `KEY` chia dữ liệu giữa các partition trong cùng bảng/instance. Chúng không phân phối tenant sang các MySQL server khác nhau và không phải sharding.

## 10. Index của partitioned table

Trong MySQL, index của bảng partitioned được chia theo partition. Mỗi partition có các index tương ứng trên phần dữ liệu của nó; không có global index duy nhất bao phủ tất cả partition như một số hệ quản trị khác.

Khi truy vấn lọc theo partition key và một cột khác, MySQL có thể:

1. Prune các partition không liên quan.
2. Dùng index cục bộ trong partition còn lại để tìm hàng.

Ví dụ:

```sql
SELECT event_id, amount
FROM sales_events
WHERE occurred_at >= '2026-01-01'
  AND occurred_at <  '2026-04-01'
  AND tenant_id = 42;
```

Partition pruning giới hạn phạm vi vào quý 1; index `(tenant_id, occurred_at)` có thể hỗ trợ tìm theo tenant trong partition đó. Thứ tự cột index vẫn cần được chọn theo workload và điều kiện truy vấn thực tế.

Nếu truy vấn chỉ lọc theo `tenant_id` mà không có điều kiện ngày, MySQL có thể phải dò index tương ứng trên nhiều partition. Nhiều partition không đồng nghĩa mỗi truy vấn sẽ đọc ít dữ liệu hơn.

## 11. Những ràng buộc quan trọng của partitioned table

Trước khi chọn partitioning, cần kiểm tra các giới hạn thiết kế của MySQL:

- Mọi cột trong partitioning expression phải xuất hiện trong mọi unique key, bao gồm primary key.
- InnoDB không hỗ trợ foreign key trên các bảng dùng user-defined partitioning; bảng partitioned cũng không thể tham gia quan hệ foreign key theo cách thông thường.
- Index được phân vùng cục bộ; không có global unique index độc lập với partition key.
- Partitioning expression phải tuân thủ các quy tắc về kiểu dữ liệu, hàm và biểu thức được phép; không thể tùy ý dùng subquery hoặc hàm không xác định.
- Số partition và các kết hợp partition/subpartition chịu giới hạn theo phiên bản và storage engine; quá nhiều partition làm tăng chi phí metadata, mở bảng và bảo trì.
- Một số tính năng/index hoặc loại bảng có giới hạn riêng với partitioning; cần xác minh đúng phiên bản MySQL trước khi triển khai.

Ràng buộc foreign key và unique key có thể ảnh hưởng sâu đến mô hình dữ liệu. Nếu schema phụ thuộc nhiều vào foreign key hoặc cần unique key toàn cục không chứa partition key, partitioning có thể không phù hợp.

## 12. Partition maintenance: quản lý vòng đời dữ liệu

Một lợi ích quan trọng của `RANGE` là có thể loại bỏ một khoảng dữ liệu cũ bằng thao tác partition thay vì xóa từng hàng.

Ví dụ loại bỏ partition chứa dữ liệu trước năm 2026:

```sql
ALTER TABLE sales_events
DROP PARTITION p_before_2026;
```

Lệnh này loại bỏ toàn bộ hàng trong partition đó khỏi bảng. Đây là thao tác phá hủy dữ liệu; phải archive hoặc backup trước nếu còn nghĩa vụ lưu trữ. Không nhầm `DROP PARTITION` với thao tác xóa có thể rollback từng hàng.

Làm rỗng một partition nhưng giữ partition:

```sql
ALTER TABLE sales_events
TRUNCATE PARTITION p2026q1;
```

`TRUNCATE PARTITION` cũng loại bỏ dữ liệu trong partition được chỉ định. Hãy xác minh tên partition, điều kiện lưu giữ và kế hoạch khôi phục trước khi chạy.

### 12.1. Thêm partition tương lai

Nếu bảng không có partition `MAXVALUE`, có thể thêm partition RANGE mới với ranh giới lớn hơn các partition hiện tại. Nếu đã có partition `MAXVALUE`, không thể đơn giản thêm partition mới phía sau nó; cần chia lại partition cuối bằng `REORGANIZE PARTITION`.

Ví dụ bảng đang có `p_future` nhận mọi ngày từ `2026-07-01` trở đi:

```sql
ALTER TABLE sales_events
REORGANIZE PARTITION p_future INTO (
    PARTITION p2026q3 VALUES LESS THAN ('2026-10-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Việc này tách dữ liệu thuộc quý 3/2026 khỏi partition tương lai. Cần lập lịch tạo partition trước khi nạp dữ liệu cho kỳ mới và kiểm tra dữ liệu đã rơi vào partition nào.

### 12.2. Exchange partition

MySQL hỗ trợ `EXCHANGE PARTITION` để hoán đổi dữ liệu của một partition với một bảng không partition có cấu trúc phù hợp:

```sql
ALTER TABLE sales_events
EXCHANGE PARTITION p2026q1
WITH TABLE sales_events_stage
WITH VALIDATION;
```

Thao tác này có thể hữu ích cho quy trình nạp/archiving dữ liệu theo kỳ. Bảng trao đổi phải đáp ứng các yêu cầu cấu trúc, engine và ràng buộc của MySQL. `WITH VALIDATION` yêu cầu kiểm tra các hàng trong bảng staging thuộc đúng partition; `WITHOUT VALIDATION` bỏ bước kiểm tra và chỉ nên dùng khi ứng dụng đã bảo đảm dữ liệu nằm đúng phạm vi.

## 13. Partitioning không tự làm mọi truy vấn nhanh hơn

Partitioning có thể cải thiện truy vấn nếu optimizer pruning được phần lớn partition. Nhưng nó cũng có thể không đem lại lợi ích hoặc khiến truy vấn phức tạp hơn:

- Truy vấn không lọc partition key phải xét nhiều partition.
- Mỗi partition có index riêng, nên truy vấn cần tìm theo khóa không phải partition key có thể dò nhiều index.
- Quá nhiều partition làm tăng metadata và chi phí lập kế hoạch/vận hành.
- Partitioning không thay thế index phù hợp, thống kê optimizer hay query tuning.
- Nếu bảng nhỏ, full scan một bảng có thể rẻ hơn quản lý nhiều partition.
- Truy vấn JOIN hoặc aggregate trên nhiều partition vẫn phải xử lý lượng dữ liệu tương ứng.

Không nên partition chỉ vì bảng có hàng trăm triệu hàng. Hãy xem workload: tỷ lệ truy vấn lọc theo partition key, dữ liệu cũ có được xóa/archive theo kỳ không, index có phù hợp không và có giới hạn schema nào cản trở không.

## 14. Khi nào partitioning phù hợp?

Partitioning thường đáng đánh giá khi:

- Bảng rất lớn và phần lớn truy vấn có điều kiện trên một cột partition rõ ràng.
- Dữ liệu có vòng đời tự nhiên theo tháng/quý/năm và cần loại bỏ/archive theo kỳ.
- Các truy vấn thường đọc một hoặc một vài khoảng thời gian thay vì toàn bộ lịch sử.
- Schema không bị cản bởi yêu cầu foreign key hoặc unique key toàn cục.
- Đội vận hành có quy trình tạo partition tương lai, kiểm tra partition thiếu và backup/archive trước khi xóa.

Không nên chọn partitioning chỉ vì:

- Muốn chia tải qua nhiều server.
- Muốn mọi truy vấn tự nhanh hơn.
- Muốn thay thế index hoặc query tuning.
- Muốn tăng dung lượng lưu trữ của một server vượt giới hạn phần cứng.
- Muốn tách bảng theo nhiều cột nhưng chưa xác định query pattern và lifecycle.

## 15. Khi nào cần sharding thay vì partitioning?

Nếu một MySQL instance đã chạm giới hạn CPU, RAM, I/O hoặc dung lượng và cần mở rộng ngang, sharding có thể là lựa chọn. Dữ liệu được chia theo shard key, chẳng hạn `tenant_id`, `customer_id` hoặc vùng địa lý; ứng dụng/middleware xác định shard chứa bản ghi.

Sharding mang lại khả năng phân tải qua nhiều server nhưng tăng độ phức tạp:

- Mỗi request phải định tuyến đúng shard.
- Truy vấn cần dữ liệu từ nhiều shard có thể phải scatter-gather.
- Unique ID và unique constraint toàn cụm cần thiết kế riêng.
- JOIN và transaction xuyên shard khó hơn.
- Rebalancing, di chuyển tenant, backup, restore và failover phải quản lý theo shard.
- Một shard quá nóng có thể trở thành bottleneck dù các shard khác còn rảnh.

Có thể kết hợp partitioning bên trong từng shard nếu có lý do quản lý dữ liệu theo thời gian, nhưng hai tầng giải quyết hai vấn đề khác nhau: sharding phân phối qua máy chủ; partitioning chia bảng bên trong một instance.

## 16. Quy trình quyết định có nên partition

Trước khi thay đổi schema, hãy trả lời:

1. Bảng lớn đến mức nào và tốc độ tăng dữ liệu ra sao?
2. Các truy vấn quan trọng thường lọc theo cột nào?
3. Có thể chọn partition key trùng với điều kiện truy vấn và vòng đời dữ liệu không?
4. Tỷ lệ truy vấn có thể pruning một hoặc vài partition là bao nhiêu?
5. Có yêu cầu unique key không chứa partition key không?
6. Bảng có quan hệ foreign key cần giữ không?
7. Có cần truy vấn theo các cột khác partition key và phải dò nhiều partition không?
8. Có kế hoạch tạo partition tương lai và xử lý dữ liệu ngoài phạm vi không?
9. Có quy trình archive/backup trước `DROP PARTITION` hoặc `TRUNCATE PARTITION` không?
10. Bottleneck hiện tại là query scan trong một server hay đã cần scale-out nhiều server?
11. Đã thử trên dữ liệu đại diện và so sánh `EXPLAIN`, thời gian, I/O trước/sau chưa?

Nếu mục tiêu là scale-out, đánh giá sharding. Nếu mục tiêu là vòng đời dữ liệu và pruning theo thời gian, partitioning có thể phù hợp. Nếu truy vấn chậm do thiếu index hoặc query plan sai, hãy giải quyết nguyên nhân đó trước.

## 17. Kiểm tra partition và kế hoạch truy vấn

Xem cấu trúc bảng:

```sql
SHOW CREATE TABLE sales_events\G
```

Xem thông tin partition:

```sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'sales_events'
ORDER BY PARTITION_ORDINAL_POSITION;
```

`TABLE_ROWS` với InnoDB thường là ước lượng, không phải số đếm chính xác. Nếu cần số hàng chính xác theo partition, có thể truy vấn `COUNT(*)` với partition selection trong môi trường phù hợp, nhưng cần cân nhắc chi phí đọc.

Ví dụ kiểm tra partition pruning:

```sql
EXPLAIN
SELECT event_id, amount
FROM sales_events
WHERE occurred_at >= '2026-01-01'
  AND occurred_at <  '2026-04-01';
```

Đối chiếu cột `partitions` trong output với số partition dự kiến. Dùng `EXPLAIN ANALYZE` trên SELECT đại diện để đo số hàng và thời gian thực tế khi cần; không kết luận hiệu năng chỉ từ việc bảng có partition.

## 18. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| Partitioning chia dữ liệu ra nhiều MySQL server | Nó chia bảng trong một instance | Dùng sharding nếu cần phân phối qua nhiều server |
| Partitioning tự tăng CPU/RAM/IOPS | Tài nguyên vẫn thuộc cùng instance | Xác định bottleneck phần cứng và kiến trúc scale-out |
| Có partition thì truy vấn nào cũng nhanh | Lợi ích phụ thuộc partition pruning và index | Kiểm tra `EXPLAIN` và workload |
| Chỉ cần partition key là đủ, không cần index | Sau pruning, truy vấn vẫn cần access path phù hợp | Thiết kế index cho điều kiện lọc và join |
| Có thể tạo UNIQUE(event_id) dù partition theo ngày | Mọi unique key phải chứa partition key | Thiết kế composite key hoặc registry cho ID toàn cục |
| InnoDB partitioned table dùng foreign key bình thường | User-defined partitioning không hỗ trợ foreign key với InnoDB | Xem xét lại mô hình quan hệ hoặc partitioning |
| Replication là một dạng sharding | Replication sao chép dữ liệu; sharding chia quyền sở hữu dữ liệu | Chọn cơ chế theo mục tiêu |
| DROP PARTITION giống DELETE có thể rollback | Nó là DDL loại bỏ dữ liệu của partition | Archive/backup và xác nhận trước khi chạy |
| HASH partition theo tenant sẽ đưa tenant lên server riêng | Hash chỉ chọn partition trong cùng instance | Cần router/shard map cho sharding |
| Partition càng nhiều càng tốt | Quá nhiều partition tăng chi phí metadata và quản lý | Chọn số partition theo workload và giới hạn phiên bản |

## 19. Bài tập thực hành

1. Tạo bảng `sales_events` với `PARTITION BY RANGE COLUMNS (occurred_at)` theo ví dụ.
2. Chèn hàng thuộc các quý khác nhau và truy vấn theo từng khoảng ngày.
3. Dùng `EXPLAIN` kiểm tra cột `partitions`; thử bỏ điều kiện ngày và quan sát số partition được truy cập.
4. Thử viết điều kiện `YEAR(occurred_at) = 2026`, sau đó đổi sang khoảng ngày; so sánh pruning.
5. Thử tạo `UNIQUE(event_id)` trên bảng partition theo `occurred_at`; đọc lỗi và giải thích quy tắc unique key.
6. Tạo bảng `LIST COLUMNS` theo `region_code`; thử insert mã vùng không được khai báo.
7. Tạo bảng `HASH` hoặc `KEY` với nhiều partition; kiểm tra hàng được phân phối nhưng vẫn nằm trong cùng MySQL instance.
8. Dùng `INFORMATION_SCHEMA.PARTITIONS` để xem partition name, method và kích thước ước lượng.
9. Trong môi trường lab, thử `REORGANIZE PARTITION` để tách partition `MAXVALUE` thành kỳ mới và partition tương lai.
10. Tạo bảng staging có cấu trúc phù hợp và thử `EXCHANGE PARTITION ... WITH VALIDATION`.
11. Lập kế hoạch retention: archive dữ liệu, xác nhận backup, rồi mới `DROP PARTITION` cho kỳ đã hết hạn.
12. Viết một bản so sánh kiến trúc: partitioning theo tháng trên một server so với sharding theo tenant trên nhiều server.

## 20. Ghi nhớ

MySQL partitioning chia hàng của một bảng logic thành nhiều partition bên trong cùng một MySQL instance. Mục tiêu chính là partition pruning và quản lý vòng đời dữ liệu; nó không tự phân phối dữ liệu qua nhiều server, không tạo thêm tài nguyên phần cứng và không thay thế sharding, replication hay backup.

MySQL hỗ trợ `RANGE`, `RANGE COLUMNS`, `LIST`, `LIST COLUMNS`, `HASH` và `KEY`. Partition pruning hiệu quả khi điều kiện truy vấn phù hợp với partition key; sau pruning, index trong partition vẫn quan trọng. Mọi unique key phải chứa các cột partitioning expression; InnoDB user-partitioned tables không hỗ trợ foreign key. `DROP PARTITION`/`TRUNCATE PARTITION` có thể loại bỏ lượng dữ liệu lớn nên cần archive/backup và kiểm soát vận hành. Hãy quyết định partitioning theo query pattern, lifecycle, ràng buộc schema và kết quả đo; nếu mục tiêu là scale-out qua nhiều máy, thiết kế sharding riêng.
