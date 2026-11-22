# EXCHANGE PARTITION và kiểm tra dữ liệu khi hoán đổi

`ALTER TABLE ... EXCHANGE PARTITION` cho phép hoán đổi dữ liệu giữa một partition của bảng đã phân vùng và một bảng thường (nonpartitioned table) có cấu trúc tương thích. Thao tác này thường được dùng để nạp dữ liệu đã chuẩn bị vào partition hoặc đưa một partition ra bảng staging/archive để xử lý tiếp.

Điểm quan trọng là đây là **hoán đổi**, không phải thao tác append: dữ liệu đang có trong partition được chuyển sang bảng thường, còn dữ liệu đang có trong bảng thường được đưa vào partition. Nếu một phía rỗng, phía đó nhận dữ liệu của phía còn lại. Với `WITH VALIDATION`, MySQL kiểm tra các hàng trong bảng thường có thuộc miền giá trị của partition đích hay không trước khi hoán đổi.

Trong module `DATABASE_MYSQL`, kỹ thuật này hữu ích cho nạp dữ liệu theo kỳ, archive partition và triển khai ETL. Tuy nhiên, phải kiểm tra cấu trúc hai bảng, partition bounds, khóa duy nhất, dữ liệu staging, metadata lock và hậu quả khi bỏ validation. Bài học tập trung vào MySQL 8.0 và InnoDB.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích semantics hoán đổi hai chiều của `EXCHANGE PARTITION`.
- Tạo bảng RANGE partition và bảng staging không phân vùng có cấu trúc tương thích.
- Hiểu vì sao cột partition phải nằm trong mọi unique key của bảng phân vùng.
- Kiểm tra schema, storage engine, index và partition bounds trước khi exchange.
- Dùng `WITH VALIDATION` để xác minh dữ liệu staging thuộc partition đích.
- Hiểu rủi ro khi dùng `WITHOUT VALIDATION` và nguy cơ hàng nằm sai partition.
- Xác minh số hàng và dữ liệu sau khi hoán đổi.
- Dùng exchange để nạp dữ liệu hoặc đưa partition ra staging/archive.
- Nhận biết implicit commit, metadata lock và giới hạn vận hành.

## 1. EXCHANGE PARTITION làm gì?

Cú pháp tổng quát:

```sql
ALTER TABLE partitioned_table
EXCHANGE PARTITION partition_name
WITH TABLE nonpartitioned_table
[WITH VALIDATION | WITHOUT VALIDATION];
```

Hai đối tượng tham gia:

- `partitioned_table`: bảng được phân vùng; lệnh chỉ định một partition cụ thể.
- `nonpartitioned_table`: bảng thường, không có partition, dùng để nhận hoặc cung cấp dữ liệu.

Sau khi exchange thành công:

- Các hàng trước đó nằm trong partition đích chuyển sang bảng thường.
- Các hàng trước đó nằm trong bảng thường chuyển sang partition đích.
- Định nghĩa partition và định nghĩa bảng vẫn giữ nguyên; chỉ dữ liệu được hoán đổi giữa hai đối tượng.

Do đó, nếu partition đích có 1 triệu hàng và staging có 100 nghìn hàng, sau exchange partition chứa 100 nghìn hàng, còn staging nhận 1 triệu hàng cũ. MySQL không nối 100 nghìn hàng vào 1 triệu hàng hiện có.

### 1.1. Hai tình huống sử dụng chính

**Nạp dữ liệu vào partition:** chuẩn bị dữ liệu trong bảng staging, kiểm tra dữ liệu, sau đó exchange staging vào partition tương ứng. Nếu partition đang rỗng, sau exchange staging thường rỗng.

**Đưa partition ra ngoài:** chuẩn bị một bảng staging rỗng, exchange partition vào bảng đó. Partition trở thành rỗng, còn bảng staging chứa dữ liệu của partition để export, archive hoặc xử lý tiếp.

### 1.2. Exchange không phải INSERT SELECT

`INSERT INTO partitioned_table SELECT ... FROM staging` sao chép từng hàng và thực hiện insert vào bảng đích. `EXCHANGE PARTITION` hoán đổi phần dữ liệu của hai đối tượng theo cơ chế metadata/storage engine, tránh phải insert lại từng hàng như cách sao chép thông thường.

Điều đó không có nghĩa exchange hoàn toàn miễn phí: validation có thể phải kiểm tra dữ liệu staging; thao tác DDL cần metadata lock; hệ thống vẫn cần tài nguyên cho metadata, index và hoạt động tiếp theo.

## 2. Tạo bảng phân vùng theo ngày

Ví dụ bảng lưu sự kiện bán hàng theo ngày. Bảng dùng `RANGE COLUMNS(event_date)` với partition theo tháng:

```sql
CREATE TABLE sales_event (
    event_id BIGINT UNSIGNED NOT NULL,
    event_date DATE NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    event_note VARCHAR(200) NULL,
    PRIMARY KEY (event_id, event_date),
    KEY idx_sales_tenant_date (tenant_id, event_date)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p202601 VALUES LESS THAN ('2026-02-01'),
    PARTITION p202602 VALUES LESS THAN ('2026-03-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Các miền partition:

| Partition | Miền giá trị `event_date` |
|---|---|
| `p202601` | Nhỏ hơn `2026-02-01` và lớn hơn/ bằng cận dưới của partition trước đó |
| `p202602` | Từ `2026-02-01` tới trước `2026-03-01` |
| `pmax` | Từ `2026-03-01` trở đi |

Trong ví dụ không khai báo partition tháng trước `p202601`, nên partition đầu tiên nhận mọi ngày nhỏ hơn `2026-02-01`. Trong hệ thống thật, nên định nghĩa đầy đủ các kỳ lưu trữ và quy tắc xử lý dữ liệu đến muộn.

### 2.1. Partition column phải nằm trong mọi unique key

MySQL yêu cầu mọi cột được dùng trong partitioning expression phải là một phần của mọi unique key trên bảng phân vùng, bao gồm primary key. Vì vậy primary key ở ví dụ là `(event_id, event_date)`, không phải chỉ `(event_id)`.

Nếu thử khai báo `PRIMARY KEY (event_id)` trong khi phân vùng theo `event_date`, MySQL sẽ từ chối định nghĩa. Điều này có hệ quả nghiệp vụ: khóa chính không còn bảo đảm `event_id` duy nhất toàn bảng nếu cùng một ID có thể xuất hiện ở hai ngày khác nhau. Ứng dụng phải bảo đảm định danh phù hợp hoặc thiết kế khóa khác.

Không được thêm `UNIQUE KEY uq_event_id (event_id)` nếu `event_date` không nằm trong unique key. Nếu cần bảo đảm ID duy nhất toàn cục, cần thiết kế lại mô hình định danh và partitioning để đáp ứng đồng thời ràng buộc đó.

## 3. Tạo bảng staging không phân vùng

Bảng staging phải là bảng thường, không có partition. Cấu trúc cột và index cần tương thích với bảng phân vùng. Để tránh nhầm lẫn về partitioning được sao chép khi tạo bảng từ một bảng khác, ví dụ khai báo staging tường minh:

```sql
CREATE TABLE sales_event_stage (
    event_id BIGINT UNSIGNED NOT NULL,
    event_date DATE NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    event_note VARCHAR(200) NULL,
    PRIMARY KEY (event_id, event_date),
    KEY idx_sales_tenant_date (tenant_id, event_date)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

`sales_event_stage` không có mệnh đề `PARTITION BY`, vì vậy đây là bảng không phân vùng. Hai bảng có cùng:

- Số lượng cột, tên cột, thứ tự cột và kiểu dữ liệu.
- Thuộc tính `NULL`/`NOT NULL`, độ chính xác và thuộc tính liên quan của cột.
- Primary key và các secondary index cần thiết.
- Storage engine InnoDB.

Trong vận hành, hãy đối chiếu `SHOW CREATE TABLE` của hai bảng trước khi exchange. Nếu có thay đổi schema ở bảng chính, phải cập nhật quy trình tạo staging để không còn lệch định nghĩa.

### 3.1. Những điều kiện cấu trúc cần nhớ

- Bảng nhận phải là bảng thường, không được partition.
- Hai phía phải có cấu trúc tương thích theo yêu cầu của MySQL cho exchange.
- Cả hai phía phải dùng cùng storage engine; ví dụ này dùng InnoDB.
- Không sử dụng foreign key constraint trên các bảng tham gia; InnoDB partitioned table không hỗ trợ foreign key.
- Partition được chỉ định phải tồn tại trong bảng phân vùng.
- Bảng staging không được là temporary table.

Không nên dựa vào việc hai bảng có cùng số cột là đủ. Khác thứ tự, kiểu dữ liệu, thuộc tính hoặc index có thể khiến exchange thất bại hoặc không đáp ứng yêu cầu cấu trúc. Dùng cùng một nguồn DDL/version hóa schema để tạo bảng chính và staging.

## 4. Nạp dữ liệu vào staging

Giả sử cần nạp dữ liệu tháng 1/2026 vào `p202601`. Nạp dữ liệu vào bảng staging trước:

```sql
INSERT INTO sales_event_stage
    (event_id, event_date, tenant_id, amount, event_note)
VALUES
    (1001, '2026-01-05', 10, 125.00, 'Web order'),
    (1002, '2026-01-12', 10,  80.00, 'Mobile order'),
    (1003, '2026-01-29', 20, 210.00, 'Partner order');
```

Staging có thể được nạp bằng `INSERT`, bulk load hoặc ETL. Giai đoạn này nên hoàn tất trước khi exchange để giảm thời gian giữ metadata lock trên bảng partitioned.

### 4.1. Kiểm tra miền dữ liệu trước exchange

Partition `p202601` nhận mọi `event_date` nhỏ hơn `2026-02-01` trong ví dụ. Kiểm tra staging:

```sql
SELECT COUNT(*) AS out_of_range_rows
FROM sales_event_stage
WHERE event_date >= '2026-02-01';
```

Vì `event_date` là `NOT NULL` và partition đầu tiên không có cận dưới khác, truy vấn này kiểm tra điều kiện trên của `p202601`. Trong hệ thống có cận dưới rõ ràng, cần kiểm tra cả hai phía:

```sql
SELECT COUNT(*) AS out_of_range_rows
FROM sales_event_stage
WHERE event_date <  '2026-01-01'
   OR event_date >= '2026-02-01';
```

Kết quả phải bằng 0 trước khi exchange. Với `RANGE COLUMNS`, cận `VALUES LESS THAN` là cận trên không bao gồm: ngày `2026-02-01` không thuộc `p202601`.

### 4.2. Kiểm tra dữ liệu theo nghiệp vụ

Ngoài partition bounds, cần kiểm tra các quy tắc khác:

```sql
SELECT COUNT(*) AS invalid_amount_rows
FROM sales_event_stage
WHERE amount < 0;

SELECT COUNT(*) AS missing_tenant_rows
FROM sales_event_stage
WHERE tenant_id IS NULL;

SELECT COUNT(*) AS duplicate_event_keys
FROM (
    SELECT event_id, event_date
    FROM sales_event_stage
    GROUP BY event_id, event_date
    HAVING COUNT(*) > 1
) AS duplicates;
```

Primary key đã ngăn duplicate `(event_id, event_date)` trong staging, nhưng kiểm tra bổ sung có thể hữu ích trong quy trình ETL và đối soát nguồn. Các kiểm tra nghiệp vụ phải phản ánh đúng schema thực tế; không giả định mọi hệ thống đều cấm amount âm.

### 4.3. Đối chiếu schema và engine

```sql
SHOW CREATE TABLE sales_event\G
SHOW CREATE TABLE sales_event_stage\G

SELECT TABLE_NAME, ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('sales_event', 'sales_event_stage');
```

Xác nhận `sales_event` có partition definition, `sales_event_stage` không có partition definition và cả hai dùng InnoDB. Kiểm tra đầy đủ column/index definition trước khi chạy DDL exchange.

## 5. EXCHANGE PARTITION WITH VALIDATION

Sau khi staging đã nạp và kiểm tra, thực hiện:

```sql
ALTER TABLE sales_event
EXCHANGE PARTITION p202601
WITH TABLE sales_event_stage
WITH VALIDATION;
```

`WITH VALIDATION` yêu cầu MySQL xác minh các hàng trong bảng staging phù hợp với partition đích. Đây là chế độ mặc định nếu không chỉ rõ `WITHOUT VALIDATION`; nên ghi rõ trong script vận hành để ý định kiểm tra dễ review.

Nếu staging có hàng ngày `2026-02-01`, exchange vào `p202601` sẽ thất bại vì hàng đó nằm ngoài miền partition. Sửa dữ liệu hoặc chọn đúng partition rồi mới thử lại.

### 5.1. Kết quả sau exchange

Nếu `p202601` ban đầu rỗng:

- `sales_event` partition `p202601` nhận ba hàng staging.
- `sales_event_stage` trở thành rỗng.
- Các partition khác không bị hoán đổi.

Kiểm tra:

```sql
SELECT COUNT(*) AS rows_in_partition
FROM sales_event PARTITION (p202601);

SELECT COUNT(*) AS rows_left_in_stage
FROM sales_event_stage;

SELECT event_id, event_date, tenant_id, amount
FROM sales_event PARTITION (p202601)
ORDER BY event_date, event_id;
```

Kết quả dự kiến là 3 hàng trong `p202601` và 0 hàng trong staging.

### 5.2. Nếu partition đã có dữ liệu

Giả sử partition đang có 1.000 hàng và staging có 100 hàng. Sau exchange, partition có 100 hàng staging; bảng staging nhận 1.000 hàng trước đó của partition. Không có bước append tự động.

Nếu mục tiêu là bổ sung dữ liệu mới vào partition mà vẫn giữ dữ liệu cũ, hãy thiết kế staging chứa cả tập dữ liệu hoàn chỉnh cần thay thế, hoặc dùng `INSERT`/ETL theo chiến lược phù hợp. Không exchange một staging chỉ chứa phần delta khi partition đang có dữ liệu rồi kỳ vọng hai tập được cộng lại.

## 6. WITHOUT VALIDATION và rủi ro dữ liệu sai partition

Có thể bỏ bước xác thực:

```sql
ALTER TABLE sales_event
EXCHANGE PARTITION p202601
WITH TABLE sales_event_stage
WITHOUT VALIDATION;
```

`WITHOUT VALIDATION` cho phép MySQL bỏ qua việc kiểm tra mọi hàng staging có thuộc partition đích hay không. Nó có thể giảm thời gian exchange với tập dữ liệu lớn, nhưng chỉ an toàn khi một quy trình khác đã chứng minh dữ liệu phù hợp với partition bounds.

### 6.1. Điều gì xảy ra nếu có hàng sai miền?

Nếu staging chứa `event_date = '2026-02-10'` nhưng được exchange vào `p202601`, hàng đó sẽ nằm vật lý trong partition có miền không phù hợp. Optimizer dựa vào partition bounds để pruning; một truy vấn tìm ngày `2026-02-10` có thể chỉ đọc `p202602` và bỏ qua `p202601`, dẫn tới kết quả thiếu hàng.

Đây là rủi ro tính đúng đắn dữ liệu, không chỉ là vấn đề hiệu năng. `WITHOUT VALIDATION` không biến partition thành nơi chứa mọi giá trị tùy ý một cách an toàn.

### 6.2. Khi nào cân nhắc WITHOUT VALIDATION?

Chỉ cân nhắc khi:

- Pipeline ETL đã kiểm tra toàn bộ dữ liệu theo cùng partition expression và bounds.
- Dữ liệu staging được khóa/đóng băng trong suốt giai đoạn kiểm tra và exchange.
- Có đối soát số hàng, min/max partition key và checksum phù hợp.
- Có quy trình xử lý ngay nếu kiểm tra hậu kỳ phát hiện dữ liệu sai.
- Đã thử nghiệm trên đúng phiên bản MySQL và cấu trúc production.

Nếu không chứng minh được các điều kiện này, dùng `WITH VALIDATION`. Đừng bỏ validation chỉ để giảm vài giây DDL mà đánh đổi tính đúng đắn truy vấn.

### 6.3. Kiểm tra bounds bằng MIN/MAX

Với partition tháng 1/2026:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(event_date) AS min_event_date,
    MAX(event_date) AS max_event_date
FROM sales_event_stage;
```

`MIN`/`MAX` giúp kiểm tra nhanh nhưng không thay thế kiểm tra mọi hàng nếu dữ liệu có kiểu hoặc biểu thức partition phức tạp. Với `RANGE COLUMNS(event_date)` và cột `DATE NOT NULL`, điều kiện lọc ngoài miền ở phần trước là cách kiểm tra trực tiếp. Với partition key nhiều cột hoặc expression, phải tái tạo đúng logic phân vùng trong validation.

## 7. EXCHANGE để archive một partition

Hoán đổi cũng dùng được theo chiều đưa partition ra ngoài. Tạo một bảng thường rỗng có schema/index tương thích, ví dụ `sales_event_archive_stage`:

```sql
CREATE TABLE sales_event_archive_stage (
    event_id BIGINT UNSIGNED NOT NULL,
    event_date DATE NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    event_note VARCHAR(200) NULL,
    PRIMARY KEY (event_id, event_date),
    KEY idx_sales_tenant_date (tenant_id, event_date)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Đảm bảo staging archive rỗng rồi exchange:

```sql
SELECT COUNT(*) AS archive_stage_rows
FROM sales_event_archive_stage;

ALTER TABLE sales_event
EXCHANGE PARTITION p202601
WITH TABLE sales_event_archive_stage
WITH VALIDATION;
```

Sau khi exchange:

- `sales_event_archive_stage` chứa các hàng trước đó của `p202601`.
- `p202601` trở thành rỗng.
- Bảng archive staging vẫn là bảng thường, có thể được export, backup, di chuyển hoặc đổi tên theo quy trình lưu trữ.

Không truncate hoặc drop bảng archive stage trước khi export/đối soát dữ liệu. Nếu staging archive không rỗng từ đầu, dữ liệu đó sẽ được đưa vào partition và dữ liệu partition sẽ chuyển sang staging; đây vẫn là hoán đổi hai chiều.

## 8. Xác minh trước và sau exchange

Một quy trình an toàn không dừng ở việc DDL trả về thành công. Hãy đối chiếu các lớp dữ liệu.

### 8.1. Kiểm tra định nghĩa partition

```sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'sales_event'
ORDER BY PARTITION_ORDINAL_POSITION;
```

`TABLE_ROWS` với InnoDB là ước lượng, không dùng làm số đối soát chính xác. Dùng `COUNT(*)` trên partition hoặc phép kiểm tra dữ liệu cụ thể khi cần số chính xác.

### 8.2. Đếm hàng trước/sau

Trước exchange, ghi nhận:

```sql
SELECT COUNT(*) AS stage_count
FROM sales_event_stage;

SELECT COUNT(*) AS partition_count_before
FROM sales_event PARTITION (p202601);
```

Sau exchange, ghi nhận lại cả hai. Nếu partition ban đầu rỗng, kỳ vọng `partition_count_after = stage_count_before` và `stage_count_after = 0`.

Nếu partition có dữ liệu trước đó, hai tập count sẽ đổi chỗ. Để đối soát, ghi nhận cả count, min/max, tổng amount hoặc checksum theo nghiệp vụ trước khi thao tác.

### 8.3. Kiểm tra dữ liệu sau exchange

```sql
SELECT COUNT(*) AS rows_outside_expected_range
FROM sales_event PARTITION (p202601)
WHERE event_date >= '2026-02-01';
```

Kết quả phải bằng 0. Có thể kiểm tra phân phối theo ngày:

```sql
SELECT event_date, COUNT(*) AS row_count, SUM(amount) AS daily_amount
FROM sales_event PARTITION (p202601)
GROUP BY event_date
ORDER BY event_date;
```

Đối chiếu với manifest của batch ETL hoặc số liệu nguồn. Không chỉ kiểm tra tổng số hàng: dữ liệu có thể đủ số lượng nhưng sai tenant, sai ngày hoặc sai giá trị nghiệp vụ.

### 8.4. Kiểm tra partition pruning

```sql
EXPLAIN
SELECT event_id, event_date, amount
FROM sales_event
WHERE event_date >= '2026-01-01'
  AND event_date <  '2026-02-01';
```

Trong output, xem cột `partitions` để xác nhận MySQL chỉ cần đọc partition phù hợp như `p202601`. Nếu hàng nằm sai partition do exchange không validation, pruning có thể bỏ qua chúng.

## 9. Điều kiện và giới hạn cần kiểm tra

| Điều kiện | Vì sao quan trọng |
|---|---|
| Bảng nguồn đã partition, staging không partition | Exchange chỉ hoán đổi một partition với bảng thường |
| Partition name chính xác | Sai tên hoặc partition không tồn tại khiến DDL thất bại |
| Cột và thứ tự cột tương thích | MySQL cần hai cấu trúc hàng tương ứng |
| Index tương thích | B-tree và định nghĩa index phải phù hợp để exchange |
| Cùng storage engine | Tránh hoán đổi giữa hai engine có layout/semantics khác nhau |
| Không có foreign key constraint | Partitioned InnoDB table không hỗ trợ foreign key |
| Staging không phải temporary table | Temporary table không phù hợp với thao tác exchange |
| Unique key chứa partition columns | Bắt buộc theo quy tắc partitioning của MySQL |
| Dữ liệu nằm trong partition bounds | Validation sẽ kiểm tra; dữ liệu sai có thể phá tính đúng đắn pruning nếu bỏ validation |
| Staging đã đóng băng | Tránh dữ liệu thay đổi giữa lúc kiểm tra và exchange |

Trước khi triển khai, đối chiếu yêu cầu của đúng phiên bản MySQL đang chạy. Các hạn chế của partitioning, loại cột và DDL có thể thay đổi giữa các phiên bản.

## 10. Metadata lock, implicit commit và vận hành

`EXCHANGE PARTITION` được thực hiện bằng `ALTER TABLE`, nên cần xem nó như một thao tác DDL. DDL có thể cần metadata lock trên bảng partitioned và bảng staging; nếu có transaction khác đang sử dụng bảng, thao tác có thể phải chờ. Ngược lại, DDL đang chờ metadata lock cũng có thể khiến truy vấn mới xếp hàng phía sau.

Trước khi chạy trên production:

- Kiểm tra transaction dài và metadata lock đang tồn tại.
- Chạy exchange trong thời gian tải phù hợp.
- Đảm bảo staging không bị ứng dụng khác ghi trong lúc kiểm tra/exchange.
- Theo dõi thời gian chờ lock, replication lag và lỗi DDL.
- Có kế hoạch xử lý nếu validation thất bại hoặc staging chứa dữ liệu sai.

### 10.1. Không kỳ vọng rollback DDL bằng transaction

Các câu lệnh `ALTER TABLE` gây implicit commit theo quy tắc MySQL. Không bọc `EXCHANGE PARTITION` trong transaction rồi kỳ vọng `ROLLBACK` có thể đảo ngược thao tác exchange như một câu `UPDATE` InnoDB thông thường.

Hãy coi exchange là ranh giới DDL riêng. Atomic DDL của MySQL 8.0 với InnoDB giúp bảo đảm tính nguyên tử của thao tác DDL được hỗ trợ khi có sự cố, nhưng không biến nó thành một thao tác có thể rollback tùy ý trong transaction ứng dụng. Cần thử nghiệm trên đúng bản MySQL và có kế hoạch phục hồi dữ liệu.

### 10.2. Validation và thời gian lock

`WITH VALIDATION` cần kiểm tra dữ liệu staging để bảo đảm các hàng thuộc partition đích. Với staging rất lớn, bước này có thể làm tăng thời gian thao tác. Hãy nạp dữ liệu, kiểm tra bounds và đối soát trước để phát hiện lỗi sớm; validation của MySQL vẫn là lớp bảo vệ cuối cùng khi exchange.

Nếu dùng `WITHOUT VALIDATION`, việc kiểm tra ngoài database phải đủ tin cậy và dữ liệu staging phải không bị thay đổi giữa validation riêng và exchange. Một lần `MIN/MAX` không đủ trong mọi mô hình partition, nhất là khi partition expression có nhiều cột.

## 11. Quy trình chuẩn nạp partition

Một quy trình ETL có thể tổ chức như sau:

1. Xác định partition đích và bounds chính xác từ schema/metadata.
2. Tạo hoặc truncate staging theo chính sách dữ liệu đã duyệt; xác nhận staging rỗng trước khi load nếu mục tiêu là nạp vào partition rỗng.
3. Nạp batch vào staging.
4. Kiểm tra schema, engine, index và trạng thái không partition của staging.
5. Kiểm tra dữ liệu ngoài bounds, duplicate key, NULL và quy tắc nghiệp vụ.
6. Đóng băng staging, ngăn writer khác thay đổi dữ liệu.
7. Ghi lại count, min/max, tổng kiểm soát hoặc checksum của batch.
8. Chạy `ALTER TABLE ... EXCHANGE PARTITION ... WITH VALIDATION`.
9. Đếm lại partition và staging; đối chiếu manifest.
10. Kiểm tra partition pruning bằng truy vấn đại diện.
11. Ghi log kết quả exchange và giải phóng staging theo chính sách.
12. Theo dõi metadata lock, replication và hiệu năng sau triển khai.

Nếu exchange thất bại, dữ liệu vẫn nằm trong staging để điều tra. Không xóa staging hoặc nạp lại đè lên dữ liệu trước khi xác định nguyên nhân.

## 12. Quy trình chuẩn archive partition

Để đưa một partition cũ ra ngoài:

1. Xác nhận kỳ dữ liệu đã đóng và không còn late-arriving events cần nạp.
2. Xác nhận partition bounds và dữ liệu trong partition.
3. Tạo bảng archive staging không partition, có cấu trúc/index tương thích.
4. Đảm bảo archive staging rỗng.
5. Ghi nhận count và số liệu đối soát trong partition.
6. Exchange partition với staging bằng `WITH VALIDATION`.
7. Đối chiếu số hàng và số liệu trong archive staging.
8. Export/backup/di chuyển archive staging theo quy trình lưu trữ.
9. Chỉ truncate/drop staging sau khi archive đã được xác minh và chính sách retention cho phép.
10. Nếu cần tái sử dụng partition rỗng, cập nhật quy trình nạp dữ liệu kỳ tiếp theo.

EXCHANGE không tự xóa dữ liệu cũ và cũng không tự nén/backup dữ liệu archive. Nó chỉ chuyển dữ liệu giữa partition và bảng thường.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Exchange báo schema không tương thích | Khác cột, kiểu, thứ tự hoặc index | So sánh `SHOW CREATE TABLE`; tạo staging từ cùng schema version |
| Staging bị từ chối vì partitioned | Bảng nhận cũng có partition | Dùng bảng thường không có `PARTITION BY` |
| Validation thất bại | Có hàng nằm ngoài bounds partition đích | Truy vấn tìm hàng sai miền, sửa dữ liệu hoặc chọn đúng partition |
| Sau exchange partition có số hàng không như dự kiến | Exchange là swap, partition có dữ liệu cũ được chuyển sang staging | Ghi nhận count cả hai phía và hiểu semantics hai chiều |
| Truy vấn không tìm thấy một số hàng | Dữ liệu đã exchange bằng WITHOUT VALIDATION và nằm sai partition | Kiểm tra partition key/bounds, exchange sửa lại theo quy trình có validation |
| DDL bị chờ lâu | Metadata lock hoặc validation trên staging lớn | Kiểm tra transaction/MDL, giảm staging, chọn thời điểm phù hợp |
| Dùng ROLLBACK nhưng exchange không quay lại | ALTER TABLE có implicit commit | Lập quy trình DDL và exchange ngược nếu cần phục hồi |
| Không tạo được unique key | Unique key thiếu cột partition | Đưa partition columns vào mọi unique key hoặc đổi partition design |
| Archive stage vẫn có dữ liệu cũ | Stage không rỗng trước khi exchange | Đối soát và làm rỗng staging theo chính sách trước thao tác |
| Dữ liệu staging thay đổi sau kiểm tra | Writer khác vẫn ghi vào staging | Đóng băng/quản lý quyền ghi trong giai đoạn preflight và exchange |

## 14. Bài thực hành

Thực hiện trong schema lab riêng với hai bảng `sales_event` và `sales_event_stage`:

1. Tạo bảng `sales_event` phân vùng `RANGE COLUMNS(event_date)` theo tháng.
2. Thử khai báo `PRIMARY KEY(event_id)` rồi quan sát quy tắc partition column trong unique key; sửa thành `(event_id, event_date)`.
3. Tạo staging không partition với cùng cột, thứ tự cột, kiểu dữ liệu, primary key, secondary index và InnoDB.
4. Dùng `SHOW CREATE TABLE` để đối chiếu hai định nghĩa và xác nhận chỉ bảng chính có partition clause.
5. Nạp dữ liệu tháng 1/2026 vào staging; kiểm tra count, min/max và dữ liệu ngoài bounds.
6. Thử thêm một hàng ngày `2026-02-01`; chạy exchange với `WITH VALIDATION` và quan sát lỗi.
7. Xóa hoặc chuyển hàng sai miền, chạy lại exchange; xác nhận partition nhận dữ liệu và staging rỗng nếu partition ban đầu rỗng.
8. Nạp dữ liệu vào staging trong khi partition đã có dữ liệu; exchange và xác nhận hai tập dữ liệu bị hoán đổi, không append.
9. Tạo staging archive rỗng và exchange partition ra ngoài; xác nhận partition rỗng và staging chứa dữ liệu cũ.
10. Trong lab riêng, thử `WITHOUT VALIDATION` với hàng ngoài bounds; kiểm tra rủi ro partition pruning và khôi phục trạng thái đúng.
11. Dùng `INFORMATION_SCHEMA.PARTITIONS` kiểm tra partition metadata và dùng `EXPLAIN` xác nhận pruning cho truy vấn theo ngày.
12. Thử giữ transaction đọc bảng ở session khác rồi chạy exchange; quan sát metadata lock wait và kết thúc transaction để thao tác tiếp tục.
13. Xây dựng manifest gồm row count, min/max ngày, tổng amount và checksum; đối chiếu trước/sau exchange.
14. Viết runbook nạp và archive partition, gồm preflight, exchange, verify, xử lý lỗi và điều kiện dọn staging.

Bạn hoàn thành bài khi giải thích được exchange là swap hai chiều, chứng minh staging thuộc đúng partition bounds và xác minh dữ liệu sau thao tác bằng cả metadata lẫn truy vấn nghiệp vụ.

## 15. Nguyên tắc cần ghi nhớ

- `EXCHANGE PARTITION` hoán đổi dữ liệu giữa một partition và một bảng thường; không append.
- Sau exchange, partition nhận dữ liệu cũ của staging và staging nhận dữ liệu cũ của partition.
- Dùng `WITH VALIDATION` để MySQL kiểm tra dữ liệu staging thuộc partition đích; đây là mặc định nếu không ghi `WITHOUT VALIDATION`.
- `WITHOUT VALIDATION` bỏ kiểm tra bounds và có thể đặt hàng sai partition, làm partition pruning trả kết quả thiếu.
- Bảng staging phải không partition và có cấu trúc/index tương thích; hai phía dùng cùng storage engine.
- InnoDB partitioned table không hỗ trợ foreign key; không thiết kế exchange với bảng có foreign key constraint.
- Mọi cột partition expression phải nằm trong mọi unique key, gồm primary key.
- Kiểm tra bounds, schema, engine, index, row count và quy tắc nghiệp vụ trước exchange.
- Dùng `INFORMATION_SCHEMA.PARTITIONS`, `SHOW CREATE TABLE`, `COUNT(*)`, `MIN/MAX` và `EXPLAIN` để xác minh.
- Exchange là DDL (`ALTER TABLE`), có implicit commit và có thể cần metadata lock.
- Validation có thể tốn thời gian theo số hàng staging; chuẩn bị dữ liệu trước để rút ngắn thời gian thao tác.
- Muốn archive partition, staging phải rỗng nếu mục tiêu là nhận toàn bộ dữ liệu partition.
- Không truncate/drop staging trước khi dữ liệu archive được đối soát và lưu trữ an toàn.
- Luôn thử nghiệm trên đúng phiên bản MySQL và có runbook phục hồi trước khi thao tác production.
