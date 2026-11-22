# Luân chuyển dữ liệu cũ và lập kế hoạch bảo trì partition

Partitioning giúp chia một bảng lớn thành các phần dữ liệu có thể quản lý theo phạm vi khóa phân vùng. Với bảng giao dịch lưu theo ngày, partition theo thời gian cho phép đưa dữ liệu cũ ra khỏi bảng đang phục vụ ứng dụng bằng thao tác trên cả partition, thay vì xóa hàng triệu bản ghi theo từng dòng. Tuy nhiên, partition chỉ hữu ích khi có chính sách vòng đời dữ liệu, lịch tạo partition mới, quy trình archive và kế hoạch bảo trì rõ ràng.

Trong MySQL, các thao tác như `EXCHANGE PARTITION`, `DROP PARTITION`, `TRUNCATE PARTITION` và `REORGANIZE PARTITION` có tác động khác nhau đến dữ liệu và cấu trúc phân vùng. Một thao tác DDL sai có thể làm mất dữ liệu hoặc khiến partition nhận dữ liệu đến muộn không còn đúng như dự kiến. Bài học này tập trung vào cách lập kế hoạch luân chuyển dữ liệu cũ an toàn và vận hành partition theo lịch.

## Mục tiêu

Sau bài học, bạn có thể:

- Thiết kế partition theo thời gian để hỗ trợ chính sách retention.
- Tạo trước partition tương lai và tránh để dữ liệu mới rơi vào tình huống không có partition phù hợp.
- Dùng `EXCHANGE PARTITION` để chuyển dữ liệu của một partition sang bảng độc lập phục vụ archive.
- Phân biệt `DROP PARTITION`, `TRUNCATE PARTITION` và `REORGANIZE PARTITION`.
- Xác minh dữ liệu trước/sau luân chuyển và lập kế hoạch rollback, backup, metadata lock.
- Xây dựng lịch bảo trì định kỳ, theo dõi partition và xử lý dữ liệu đến muộn.

Các ví dụ giả định MySQL 8.0, InnoDB và bảng được partition theo `RANGE COLUMNS` trên cột `DATE`. Hãy kiểm tra khả năng hỗ trợ và giới hạn của đúng phiên bản MySQL đang triển khai trước khi áp dụng DDL trên production.

## 1. Bắt đầu từ chính sách vòng đời dữ liệu

Trước khi tạo partition, cần trả lời những câu hỏi nghiệp vụ:

- Dữ liệu nóng cần phục vụ truy vấn thường xuyên trong bao lâu: 30 ngày, 12 tháng hay vài năm?
- Dữ liệu cũ phải được giữ online, chuyển sang bảng archive, xuất ra object storage hay xóa sau thời hạn pháp lý?
- Dữ liệu đến muộn có thể xuất hiện sau bao lâu? Có cho phép nạp lại giao dịch của kỳ đã archive không?
- Truy vấn chủ yếu lọc theo ngày, theo khách hàng hay theo mã giao dịch?
- Ai phê duyệt việc xóa dữ liệu và làm thế nào chứng minh dữ liệu archive đầy đủ?

Một chính sách mẫu:

| Nhóm dữ liệu | Cách lưu | Thời gian giữ | Hành động khi hết hạn |
|---|---|---|---|
| Giao dịch gần đây | Bảng partition chính | 24 tháng | Chuyển partition cũ sang bảng archive |
| Giao dịch đã archive | Bảng độc lập hoặc kho lưu trữ | Theo yêu cầu nghiệp vụ/pháp lý | Backup, kiểm tra và xóa theo chính sách riêng |
| Dữ liệu quá hạn archive | Không còn trong bảng online | Theo thời hạn đã phê duyệt | Xóa partition hoặc bản archive sau khi xác minh |

Partitioning không tự quyết định dữ liệu nào được giữ hoặc xóa. Nó chỉ cung cấp ranh giới vật lý để thao tác theo nhóm. Chính sách retention, điều kiện truy vấn và lịch vận hành phải được xác định trước.

## 2. Thiết kế bảng partition theo thời gian

Ví dụ bảng giao dịch bán hàng:

```sql
CREATE TABLE sales (
    sale_id BIGINT UNSIGNED NOT NULL,
    sold_at DATE NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(16) NOT NULL,
    PRIMARY KEY (sale_id, sold_at),
    KEY ix_sales_customer_date (customer_id, sold_at),
    KEY ix_sales_status_date (status, sold_at)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (sold_at) (
    PARTITION p_before_2026 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

`RANGE COLUMNS(sold_at)` phân chia dữ liệu theo ranh giới ngày. `p_before_2026` chứa mọi ngày nhỏ hơn ngày 1/1/2026; `p2026` chứa các ngày từ 1/1/2026 đến trước 1/1/2027; `p_future` nhận các giá trị từ 1/1/2027 trở đi.

Tên partition chỉ là quy ước. Với `RANGE`, partition đầu tiên không có cận dưới tường minh; vì vậy `p_before_2026` có thể chứa dữ liệu rất cũ nếu ứng dụng cho phép nạp lại. Sau khi bỏ partition đầu tiên, partition kế tiếp sẽ trở thành partition đầu tiên và phạm vi của nó mở rộng xuống phía dưới. Nếu không muốn dữ liệu quá cũ lọt vào partition mới, ứng dụng cần kiểm tra retention floor trước khi insert hoặc phải duy trì một partition dành riêng cho dữ liệu cũ.

### Chú ý khóa duy nhất và khóa ngoại

Với bảng partitioned trong MySQL, mọi unique key, bao gồm primary key, phải chứa tất cả cột được dùng trong biểu thức partitioning. Trong ví dụ, `sold_at` nằm trong primary key `(sale_id, sold_at)`.

InnoDB không hỗ trợ foreign key trên bảng được partition bởi người dùng; bảng partitioned cũng không thể được bảng khác tham chiếu bằng foreign key. Nếu mô hình dữ liệu cần ràng buộc tham chiếu, phải thiết kế lại ranh giới bảng hoặc kiểm tra quan hệ ở tầng ứng dụng/transaction theo cách phù hợp.

Index trên bảng partitioned được tổ chức theo từng partition (local index). Partition pruning giúp bỏ qua partition không liên quan; index trong partition giúp tìm hàng bên trong partition được chọn. Partitioning không thay thế thiết kế index và không tự động làm mọi truy vấn nhanh hơn.

## 3. Lập kế hoạch partition tương lai

Không nên chờ đến khi dữ liệu của ngày/tháng mới đến mới phát hiện bảng chưa có partition. Nếu không có partition phù hợp, thao tác insert có thể thất bại. `p_future` dùng `MAXVALUE` làm vùng đệm để tránh lỗi này, nhưng dữ liệu mới sẽ tiếp tục rơi vào cùng một partition cho đến khi partition được tách.

### Tách partition MAXVALUE bằng REORGANIZE

Trước năm 2027, có thể tách `p_future` thành partition riêng cho năm 2027 và một `p_future` mới:

```sql
ALTER TABLE sales
REORGANIZE PARTITION p_future INTO (
    PARTITION p2027 VALUES LESS THAN ('2028-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

`REORGANIZE PARTITION` phân phối lại các hàng trong partition cũ theo các ranh giới mới. Nếu `p_future` đã chứa nhiều dữ liệu, thao tác có thể phải di chuyển và ghi lại lượng dữ liệu đáng kể. Vì vậy, tạo partition tương lai trước thời điểm cần dùng sẽ giúp giảm áp lực bảo trì khẩn cấp.

### ADD PARTITION khi không có MAXVALUE

Nếu thiết kế không có partition `MAXVALUE`, có thể thêm partition mới ở cuối phạm vi:

```sql
ALTER TABLE sales_no_future
ADD PARTITION (
    PARTITION p2027 VALUES LESS THAN ('2028-01-01')
);
```

Không thể thêm một partition có ranh giới cao hơn sau partition `MAXVALUE` bằng `ADD PARTITION`; phải `REORGANIZE` partition chứa `MAXVALUE` để tách vùng mới. Chọn một chiến lược nhất quán và ghi rõ trong runbook.

### Lịch tạo partition

Một lịch vận hành thường tạo partition trước 1-3 kỳ, tùy tần suất partition và thời gian phê duyệt thay đổi. Ví dụ:

| Thời điểm | Công việc |
|---|---|
| Đầu mỗi tháng | Kiểm tra partition hiện có và kỳ tiếp theo |
| Trước kỳ mới 2-4 tuần | Tạo partition cho tháng/quý tiếp theo |
| Hàng tuần | Cảnh báo nếu dữ liệu đã bắt đầu rơi vào `p_future` |
| Hàng ngày | Theo dõi insert lỗi do thiếu partition và dữ liệu đến muộn |
| Trước kỳ archive | Kiểm tra backup, số hàng, ranh giới ngày và phê duyệt retention |

Nếu dùng `p_future`, cần giám sát số hàng trong partition này. Khi partition nhận dữ liệu thường xuyên, đó là tín hiệu lịch tạo partition đang chậm hoặc ranh giới đã lỗi thời.

## 4. EXCHANGE PARTITION để archive dữ liệu cũ

`ALTER TABLE ... EXCHANGE PARTITION` hoán đổi dữ liệu của một partition với một bảng không partition. Đây là cách hữu ích để tách dữ liệu cũ ra khỏi bảng online mà không phải `DELETE` từng hàng.

Giả sử `p_before_2026` đã hết thời gian phục vụ online và cần archive. Tạo bảng độc lập có cấu trúc tương thích:

```sql
CREATE TABLE sales_archive_before_2026 LIKE sales;
ALTER TABLE sales_archive_before_2026 REMOVE PARTITIONING;
```

`CREATE TABLE ... LIKE` tạo bảng rỗng dựa trên cấu trúc nguồn; `REMOVE PARTITIONING` biến bảng archive thành bảng không partition. Kiểm tra `SHOW CREATE TABLE` để xác nhận các cột, kiểu dữ liệu, index và thuộc tính bảng tương thích. Bảng archive đích phải rỗng trước khi exchange, nếu không dữ liệu đang có trong bảng đó sẽ được chuyển ngược vào partition.

Thực hiện exchange với validation:

```sql
ALTER TABLE sales
EXCHANGE PARTITION p_before_2026
WITH TABLE sales_archive_before_2026
WITH VALIDATION;
```

Sau thao tác:

- `sales_archive_before_2026` chứa các hàng trước đây thuộc `p_before_2026`.
- `p_before_2026` vẫn tồn tại nhưng trở thành partition rỗng.
- Các partition khác của `sales` không bị chuyển dữ liệu.

`WITH VALIDATION` là lựa chọn mặc định và yêu cầu MySQL kiểm tra hàng trong bảng không partition có thuộc phạm vi của partition đích hay không. Validation có thể tốn thời gian khi bảng archive rất lớn, nhưng giúp ngăn dữ liệu nằm sai partition. `WITHOUT VALIDATION` bỏ qua bước kiểm tra; chỉ dùng khi quy trình đã chứng minh toàn bộ hàng phù hợp với ranh giới partition. Nếu đưa hàng sai phạm vi vào partition, truy vấn dựa trên partition pruning có thể không tìm thấy hàng ở nơi ứng dụng kỳ vọng.

### Xác minh trước và sau exchange

Trước exchange, ghi nhận số hàng và khoảng ngày:

```sql
SELECT COUNT(*) AS row_count,
       MIN(sold_at) AS min_sold_at,
       MAX(sold_at) AS max_sold_at
FROM sales PARTITION (p_before_2026);
```

Sau exchange, kiểm tra bảng archive:

```sql
SELECT COUNT(*) AS row_count,
       MIN(sold_at) AS min_sold_at,
       MAX(sold_at) AS max_sold_at
FROM sales_archive_before_2026;

SELECT COUNT(*) AS remaining_rows
FROM sales PARTITION (p_before_2026);
```

Số hàng archive phải khớp số hàng đã ghi nhận trước exchange; partition nguồn phải rỗng. Đối chiếu thêm tổng tiền, số lượng theo ngày hoặc checksum nghiệp vụ nếu yêu cầu kiểm toán cần mức xác minh cao hơn.

### Sau exchange: giữ lại hay xóa partition rỗng?

Có hai lựa chọn:

- Giữ partition rỗng nếu cần dùng lại ranh giới hiện tại hoặc muốn thực hiện bước archive theo đợt.
- `DROP PARTITION` để loại bỏ định nghĩa partition cũ sau khi đã xác minh archive.

Ví dụ:

```sql
ALTER TABLE sales DROP PARTITION p_before_2026;
```

Chỉ drop sau khi bảng archive đã được kiểm tra, backup theo chính sách và có phê duyệt. Khi drop partition đầu tiên của bảng `RANGE`, partition kế tiếp trở thành partition đầu tiên và phạm vi của nó mở rộng xuống dưới. Nếu cần ngăn dữ liệu quá cũ xuất hiện trong partition mới, phải có kiểm tra ở tầng ứng dụng hoặc tổ chức lại partition phù hợp.

## 5. DROP, TRUNCATE và REORGANIZE khác nhau thế nào?

| Thao tác | Tác động đến dữ liệu | Tác động đến định nghĩa partition | Khi dùng |
|---|---|---|---|
| `DROP PARTITION` | Xóa toàn bộ dữ liệu trong partition bị drop | Xóa partition khỏi bảng | Loại bỏ kỳ dữ liệu đã hết retention sau khi archive hoặc phê duyệt xóa |
| `TRUNCATE PARTITION` | Xóa toàn bộ hàng trong partition | Giữ partition và ranh giới của nó | Làm rỗng một partition để tái sử dụng |
| `REORGANIZE PARTITION` | Phân phối lại dữ liệu giữa các partition được chỉ định | Thay đổi ranh giới/số partition trong vùng đó | Tách `MAXVALUE`, gộp partition nhỏ hoặc điều chỉnh ranh giới |
| `EXCHANGE PARTITION` | Hoán đổi dữ liệu giữa partition và bảng không partition | Giữ partition; bảng độc lập nhận dữ liệu | Archive hoặc nạp dữ liệu theo lô bằng bảng staging |

Ví dụ làm rỗng partition mà vẫn giữ định nghĩa:

```sql
ALTER TABLE sales TRUNCATE PARTITION p_future;
```

Lệnh này xóa dữ liệu trong `p_future`, không xóa partition. Đây là thao tác phá hủy dữ liệu; chỉ dùng khi chắc chắn dữ liệu trong partition không cần giữ.

Ví dụ gộp hai partition liền kề:

```sql
ALTER TABLE sales
REORGANIZE PARTITION p2026, p2027 INTO (
    PARTITION p2026_2027 VALUES LESS THAN ('2028-01-01')
);
```

Ranh giới mới phải bao phủ đúng phạm vi dữ liệu của các partition được reorganize. Với partition có nhiều hàng, thao tác có thể cần di chuyển dữ liệu và tạo lại cấu trúc index liên quan; cần ước lượng dung lượng, thời gian và tải I/O trước khi chạy.

## 6. Vì sao không nên archive bằng DELETE hàng loạt?

Có thể xóa dữ liệu cũ bằng:

```sql
DELETE FROM sales
WHERE sold_at < '2026-01-01';
```

Nhưng với hàng triệu hoặc hàng tỷ hàng, cách này có thể tạo lượng undo/redo lớn, làm tăng binary log, khiến purge phải làm việc nhiều và giữ khóa lâu. Transaction lớn còn có thể làm replica chậm hoặc ảnh hưởng truy vấn đang chạy.

Nếu ranh giới retention trùng với ranh giới partition, `EXCHANGE PARTITION` rồi `DROP PARTITION` thường phù hợp hơn vì thao tác theo đơn vị partition. Tuy nhiên, DDL vẫn cần metadata lock, có thể phải chờ transaction đang sử dụng bảng và có thể tạo tải I/O tùy thao tác. Không nên xem partition DDL là thao tác không có chi phí.

Nếu retention cutoff nằm giữa một partition, không thể drop một phần partition bằng `DROP PARTITION`. Có thể:

1. Dùng `REORGANIZE PARTITION` để tách vùng cũ và vùng cần giữ theo ranh giới mới, rồi archive/drop phần cũ.
2. Xóa theo lô bằng khóa chính nếu lượng dữ liệu nhỏ hoặc ranh giới không phù hợp để thay đổi partition.
3. Điều chỉnh lịch partition trong thiết kế tiếp theo để ranh giới trùng với chu kỳ retention.

Lựa chọn phụ thuộc khối lượng dữ liệu, thời gian cho phép, yêu cầu lưu trữ và chi phí rebuild.

## 7. Partition pruning và truy vấn sau khi luân chuyển

Partition pruning giúp optimizer chỉ đọc các partition có thể chứa hàng phù hợp. Điều kiện nên thể hiện trực tiếp phạm vi của partition key:

```sql
SELECT sale_id, customer_id, amount
FROM sales
WHERE sold_at >= '2026-06-01'
  AND sold_at <  '2026-07-01'
  AND customer_id = 42;
```

Tránh bọc partition key trong hàm nếu có thể viết thành khoảng tương đương:

```sql
-- Khó hỗ trợ pruning hơn trong nhiều trường hợp:
WHERE YEAR(sold_at) = 2026

-- Viết thành khoảng rõ ràng:
WHERE sold_at >= '2026-01-01'
  AND sold_at <  '2027-01-01'
```

Kiểm tra partition được chọn:

```sql
EXPLAIN PARTITIONS
SELECT sale_id, amount
FROM sales
WHERE sold_at >= '2026-06-01'
  AND sold_at <  '2026-07-01';
```

Cột `partitions` trong kết quả cho biết các partition được xét. Sau khi archive và drop partition cũ, truy vấn lịch sử phải chuyển sang bảng archive hoặc hệ thống lưu trữ tương ứng. Nếu ứng dụng vẫn truy vấn duy nhất bảng `sales`, dữ liệu đã chuyển ra sẽ không còn xuất hiện trong kết quả.

## 8. Lập kế hoạch và thực hiện một đợt archive

Một đợt archive nên có các bước kiểm soát rõ ràng:

1. **Xác định phạm vi:** chọn partition đã đóng, xác nhận ngày bắt đầu/kết thúc và chính sách retention.
2. **Kiểm tra schema:** xác nhận bảng archive không partition có cấu trúc và index tương thích; bảng đích đang rỗng.
3. **Kiểm tra dữ liệu:** đếm hàng, min/max ngày, tổng tiền và các số liệu nghiệp vụ trước exchange.
4. **Kiểm tra khả năng phục hồi:** xác nhận backup gần nhất và quy trình khôi phục bảng archive đã được kiểm thử.
5. **Kiểm tra tải và khóa:** tìm transaction dài, chọn thời gian ít tải, dự trù metadata lock và thời gian validation.
6. **Exchange:** chạy `EXCHANGE PARTITION ... WITH VALIDATION`.
7. **Đối chiếu:** so sánh số hàng và số liệu nghiệp vụ ở bảng archive, xác nhận partition nguồn rỗng.
8. **Backup archive:** tạo bản sao độc lập theo chính sách backup và retention.
9. **Drop partition:** chỉ thực hiện sau khi dữ liệu archive đã được xác minh và có phê duyệt.
10. **Ghi nhận:** lưu thời điểm, người thực hiện, partition, số hàng, checksum/tổng đối chiếu, thời gian DDL và kết quả.

DDL như `ALTER TABLE` có thể gây implicit commit và không thể được hoàn tác bằng `ROLLBACK` như DML thông thường. Không bọc toàn bộ quy trình exchange/drop trong một transaction rồi kỳ vọng có thể rollback mọi bước. Hãy dùng checkpoint, backup và quy trình khôi phục rõ ràng.

## 9. Metadata lock và cửa sổ bảo trì

Các lệnh `ALTER TABLE` cần metadata lock (MDL). Nếu một transaction đang giữ metadata lock trên bảng, thao tác partition có thể phải chờ. Ngược lại, khi DDL đang chờ lấy MDL, các truy vấn mới cũng có thể bị xếp hàng phía sau tùy tình huống.

Trước cửa sổ bảo trì:

- Kiểm tra transaction dài và session idle trong transaction.
- Tránh chạy archive cùng thời điểm với migration hoặc DDL khác trên bảng.
- Đặt thời gian chờ hợp lý và theo dõi trạng thái lệnh trong `performance_schema`/process list.
- Chuẩn bị kế hoạch hủy thao tác nếu đang chờ lock quá lâu; việc hủy DDL đang chạy có thể cần thời gian rollback/cleanup.
- Thông báo cho ứng dụng nếu thao tác có thể làm tăng độ trễ hoặc gây gián đoạn.

Không mặc định `EXCHANGE PARTITION`, `DROP PARTITION` hay `REORGANIZE PARTITION` đều là instant. Mức độ khóa, thuật toán và chi phí phụ thuộc loại thao tác, engine, phiên bản và cấu trúc bảng. Kiểm tra tài liệu MySQL cho đúng phiên bản, thử trên bản sao dữ liệu và đo thời gian trước khi đưa vào lịch production.

## 10. Theo dõi partition và phát hiện lỗi vận hành

Liệt kê partition hiện có:

```sql
SELECT PARTITION_NAME,
       PARTITION_METHOD,
       PARTITION_EXPRESSION,
       PARTITION_DESCRIPTION,
       TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'sales'
ORDER BY PARTITION_ORDINAL_POSITION;
```

Với InnoDB, `TABLE_ROWS` trong `INFORMATION_SCHEMA.PARTITIONS` là ước lượng; không dùng nó làm số đối soát chính xác. Dùng `COUNT(*)` theo partition hoặc số liệu archive đã chụp trước/sau để kiểm chứng:

```sql
SELECT COUNT(*)
FROM sales PARTITION (p_future);
```

Các cảnh báo nên theo dõi:

| Dấu hiệu | Ý nghĩa có thể | Hành động |
|---|---|---|
| `p_future` tăng hàng liên tục | Partition kỳ mới chưa được tạo hoặc boundary cũ | Tạo partition kỳ tiếp theo và xác minh dữ liệu đã vào đúng vùng |
| Insert báo không có partition phù hợp | Không có partition chứa giá trị partition key | Tạo partition mới; kiểm tra dữ liệu vượt phạm vi và thời điểm chạy job |
| Archive table không khớp số hàng trước exchange | Quy trình exchange hoặc đối soát có vấn đề | Dừng bước drop, giữ nguyên dữ liệu và điều tra |
| DDL chờ lâu | Transaction hoặc truy vấn khác giữ MDL | Xác định blocker, xử lý transaction và dời cửa sổ bảo trì nếu cần |
| Query lịch sử không còn dữ liệu | Partition đã được exchange/drop khỏi bảng online | Chuyển truy vấn sang archive hoặc tầng lưu trữ phù hợp |
| Reorganize kéo dài | Partition nguồn lớn hoặc phải di chuyển nhiều page | Đo trước, chia nhỏ công việc nếu thiết kế cho phép và chọn giờ ít tải |

## 11. Xử lý dữ liệu đến muộn

Dữ liệu đến muộn là một trong những rủi ro lớn nhất của partition theo thời gian. Ví dụ, partition trước năm 2026 đã được archive và drop nhưng một giao dịch có `sold_at = '2025-12-31'` lại được gửi đến sau đó.

Hãy chọn một chính sách tường minh:

- **Từ chối dữ liệu quá hạn:** kiểm tra retention floor trước khi insert và chuyển bản ghi đến luồng xử lý ngoại lệ.
- **Nạp qua staging:** đưa dữ liệu cũ vào bảng staging, xác minh rồi archive trực tiếp hoặc exchange vào một partition được thiết kế cho late-arriving data.
- **Mở lại vùng lịch sử có kiểm soát:** tạo/reorganize partition để tiếp nhận dữ liệu cũ, nạp xong rồi chạy lại quy trình archive. Cách này có thể tốn chi phí và cần phê duyệt.

Không tự động nạp dữ liệu cũ vào partition đầu tiên chỉ vì câu lệnh insert không lỗi. Sau khi drop partition đầu tiên, phạm vi của partition tiếp theo có thể mở rộng xuống dưới; dữ liệu cũ có thể được nhận vào một partition mang tên kỳ mới. Kiểm tra ranh giới bằng `INFORMATION_SCHEMA.PARTITIONS` và áp dụng retention floor ở tầng ứng dụng.

## 12. Checklist vận hành định kỳ

Trước mỗi kỳ bảo trì, xác nhận:

- [ ] Partition kỳ tiếp theo đã tồn tại hoặc có lịch tạo rõ ràng.
- [ ] Partition được archive đã đóng, không còn ghi mới theo quy tắc nghiệp vụ.
- [ ] Bảng archive không partition có schema và index tương thích.
- [ ] Bảng archive đích đang rỗng.
- [ ] Đã ghi nhận số hàng, min/max partition key và số liệu đối chiếu.
- [ ] Backup gần nhất hợp lệ và quy trình restore đã được kiểm thử.
- [ ] Không có transaction dài gây chờ metadata lock.
- [ ] Đã chọn `WITH VALIDATION` hoặc có bằng chứng đủ mạnh nếu dùng `WITHOUT VALIDATION`.
- [ ] Sau exchange, số hàng archive khớp và partition nguồn rỗng.
- [ ] Chỉ drop partition sau khi archive và backup được xác minh.
- [ ] Lịch sử thao tác và người phê duyệt được lưu lại.
- [ ] Chính sách dữ liệu đến muộn và retention floor vẫn được thực thi.

## 13. Bài thực hành

Trên một MySQL instance thử nghiệm, tạo bảng `sales` partition theo `RANGE COLUMNS(sold_at)` như phần 2 và nạp dữ liệu giả cho các kỳ khác nhau.

1. Chạy `EXPLAIN PARTITIONS` cho truy vấn một tháng và xác định partition được chọn.
2. Tạo bảng `sales_archive_before_2026` bằng `CREATE TABLE ... LIKE`, sau đó `REMOVE PARTITIONING`. Dùng `SHOW CREATE TABLE` để so sánh schema.
3. Ghi nhận `COUNT(*)`, `MIN(sold_at)` và `MAX(sold_at)` trong `p_before_2026`. Thực hiện `EXCHANGE PARTITION ... WITH VALIDATION`.
4. Xác nhận bảng archive có đúng số hàng và partition nguồn rỗng. Chưa drop partition ở bước này.
5. Trên bản thử nghiệm riêng, thực hiện `DROP PARTITION` và quan sát cách ranh giới của partition đầu tiên thay đổi.
6. Tạo partition 2027 bằng cách `REORGANIZE` `p_future`. Quan sát dữ liệu được phân phối theo ranh giới mới.
7. Thử insert một hàng có `sold_at` cũ hơn retention floor. Thiết kế kiểm tra ở ứng dụng để từ chối hoặc đưa hàng vào luồng staging.
8. Mô tả cách khôi phục nếu bảng archive thiếu dữ liệu sau exchange; nêu rõ vì sao không thể chỉ dùng `ROLLBACK` để đảo một lệnh DDL đã commit.

## Ghi nhớ

- Lập chính sách retention và dữ liệu đến muộn trước khi chọn partition key và ranh giới partition.
- Tạo partition tương lai trước thời điểm cần dùng; theo dõi `p_future` nếu có `MAXVALUE`.
- `EXCHANGE PARTITION` hoán đổi dữ liệu với bảng không partition; dùng validation và đối soát trước/sau.
- `DROP PARTITION` xóa dữ liệu và định nghĩa partition; `TRUNCATE PARTITION` chỉ làm rỗng; `REORGANIZE PARTITION` thay đổi ranh giới và có thể di chuyển dữ liệu.
- Chỉ archive/drop partition sau khi backup và số liệu đối chiếu đã được xác minh.
- Partition DDL cần metadata lock và có thể tạo tải; phải thử nghiệm, lập cửa sổ bảo trì và chuẩn bị phục hồi.
- Sau khi drop partition đầu tiên, phạm vi partition kế tiếp mở rộng xuống dưới; cần retention floor hoặc thiết kế tiếp nhận dữ liệu cũ rõ ràng.
