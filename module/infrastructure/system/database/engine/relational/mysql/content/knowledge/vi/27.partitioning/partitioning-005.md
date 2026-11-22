# Partition pruning và điều kiện lọc có thể cắt vùng

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích partition pruning và lý do MySQL có thể bỏ qua những partition không chứa hàng phù hợp.
- Phân biệt partition pruning với index lookup, partition selection và full scan.
- Viết điều kiện `WHERE` phù hợp với biểu thức phân vùng để optimizer loại bỏ partition không cần thiết.
- Nhận biết cách pruning hoạt động với `RANGE`, `LIST`, `HASH` và `KEY`.
- Tránh các biểu thức, phép chuyển kiểu và điều kiện làm mất khả năng pruning.
- Kiểm tra partition được truy cập bằng `EXPLAIN FORMAT=JSON` và các định dạng EXPLAIN phù hợp với phiên bản.
- Kết hợp partition pruning với index trong từng partition.
- Hiểu các giới hạn của partitioned table trong InnoDB trước khi thiết kế schema.

Các ví dụ hướng tới MySQL 8.0/8.4 với InnoDB. Kế hoạch thực thi thực tế phụ thuộc phiên bản, kiểu partition, biểu thức phân vùng, dữ liệu, statistics và index.

## 1. Partition pruning là gì?

Partitioning chia một bảng logic thành nhiều partition. Mỗi partition lưu một phần dữ liệu theo quy tắc phân vùng đã khai báo, chẳng hạn theo khoảng ngày, danh sách giá trị hoặc kết quả của hàm băm.

Khi truy vấn có điều kiện cho phép xác định một số partition chắc chắn không thể chứa hàng cần tìm, optimizer có thể bỏ qua các partition đó. Quá trình này gọi là **partition pruning**.

Ví dụ bảng đơn hàng được phân vùng theo quý dựa trên `created_at`. Nếu truy vấn chỉ lấy đơn trong quý 1 năm 2026, MySQL có thể chỉ đọc partition của quý đó thay vì mở rộng việc tìm kiếm sang tất cả partition của bảng.

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

Nếu điều kiện khớp với cách chia partition, optimizer có thể xác định phạm vi ngày nằm trong partition `p2026q1` và loại các partition khác khỏi kế hoạch.

### 1.1. Pruning giảm số partition cần truy cập

Partition pruning giúp giảm phạm vi dữ liệu vật lý phải kiểm tra. Nó đặc biệt hữu ích với bảng lớn có dữ liệu được phân vùng theo thời gian hoặc một khóa nghiệp vụ có quy luật truy vấn rõ ràng.

Pruning không làm thay đổi kết quả logic của câu SQL. Nếu điều kiện yêu cầu dữ liệu ở ba partition, MySQL phải truy cập cả ba partition đó.

### 1.2. Pruning không đồng nghĩa với dùng index

Partition pruning và index access giải quyết hai lớp khác nhau:

- **Partition pruning:** xác định partition nào có thể chứa hàng phù hợp.
- **Index access:** tìm hàng phù hợp bên trong các partition được giữ lại.

Một truy vấn có thể prune còn một partition nhưng vẫn full scan partition đó. Ngược lại, truy vấn có thể dùng index trong từng partition nhưng phải truy cập tất cả partition nếu không có điều kiện trên partition key.

Vì vậy, khi phân tích hiệu năng, cần xem cả partition được chọn và access method/index được sử dụng trong partition đó.

### 1.3. Pruning khác với chỉ định partition bằng tay

Optimizer tự động pruning dựa trên điều kiện truy vấn. MySQL cũng cho phép chỉ định partition rõ ràng bằng cú pháp `PARTITION (...)`:

```sql
SELECT order_id, total_amount
FROM orders PARTITION (p2026q1)
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

Đây là partition selection do người viết SQL yêu cầu. Nếu chỉ định thiếu partition có thể chứa hàng phù hợp, kết quả sẽ thiếu dữ liệu. Trong truy vấn thông thường, nên để optimizer pruning tự động và dùng `EXPLAIN` để xác nhận.

## 2. Điều kiện để optimizer thực hiện pruning

Optimizer cần suy ra được tập partition có thể chứa hàng phù hợp từ điều kiện của truy vấn. Điều kiện càng trực tiếp và có thể đánh giá thành hằng số thì pruning càng dễ dự đoán.

Những dạng điều kiện thường hỗ trợ pruning gồm:

- So sánh partition key với hằng số bằng `=`, `<`, `<=`, `>`, `>=`.
- Điều kiện khoảng bằng `BETWEEN` hoặc cặp cận dưới/cận trên.
- `IN (...)` với tập giá trị xác định.
- Kết hợp các điều kiện bằng `AND` hoặc `OR` khi optimizer có thể xác định các nhánh.
- Điều kiện trên chính biểu thức phân vùng hoặc dạng mà optimizer có thể suy ra tương đương.

Không phải mọi biểu thức SQL đều được biến đổi thành điều kiện partition có thể pruning. Hãy ưu tiên predicate trực tiếp trên partition key và kiểm tra execution plan.

### 2.1. Điều kiện trực tiếp trên partition key

Với bảng phân vùng theo `RANGE COLUMNS(created_at)`, truy vấn sau là dạng thuận lợi:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01'
```

Hai cận thời gian xác định một khoảng liên tục trên chính cột phân vùng. Optimizer có thể so sánh khoảng này với các ranh giới partition.

### 2.2. Dùng khoảng nửa mở cho ngày giờ

Với cột `DATETIME` hoặc `TIMESTAMP`, nên biểu diễn một ngày, tháng hoặc quý bằng khoảng nửa mở `[start, end)`:

```sql
WHERE created_at >= '2026-02-01 00:00:00'
  AND created_at <  '2026-03-01 00:00:00'
```

Cách viết này:

- Bao gồm mọi thời điểm từ đầu tháng 2.
- Không cần đoán giá trị thời gian cuối ngày như `23:59:59.999999`.
- Tránh chồng lấn giữa hai kỳ liền nhau.
- Thể hiện cận trên độc quyền rõ ràng.

Khi dùng `TIMESTAMP`, cần thống nhất múi giờ của session và cách ứng dụng gửi giá trị thời gian. Khi dùng `DATE`, literal nên cùng kiểu/ngữ nghĩa ngày.

### 2.3. Điều kiện trên cột không phải partition key

Giả sử bảng được phân vùng theo `created_at`, nhưng truy vấn chỉ có:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 9001;
```

Điều kiện không giới hạn `created_at`, nên optimizer thường phải xét tất cả partition. Index trên `customer_id` có thể giúp tìm khách hàng trong từng partition, nhưng không thay thế partition pruning.

Nếu nghiệp vụ có thể cung cấp khoảng thời gian, thêm điều kiện thời gian chính xác:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 9001
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
```

Truy vấn này vừa có thể prune theo `created_at`, vừa dùng index phù hợp trong partition còn lại.

## 3. Ví dụ RANGE COLUMNS theo ngày

`RANGE COLUMNS` phù hợp khi muốn phân vùng trực tiếp theo giá trị cột mà không phải viết hàm chuyển đổi trong biểu thức partition.

### 3.1. Tạo bảng orders phân vùng theo quý

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (order_id, created_at),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_status_created (status, created_at)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p_before_2026 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026q1      VALUES LESS THAN ('2026-04-01'),
    PARTITION p2026q2      VALUES LESS THAN ('2026-07-01'),
    PARTITION p2026q3      VALUES LESS THAN ('2026-10-01'),
    PARTITION p2026q4      VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future     VALUES LESS THAN (MAXVALUE)
);
```

Với `RANGE COLUMNS`, mỗi partition chứa các giá trị nhỏ hơn cận được khai báo và lớn hơn hoặc bằng cận của partition trước đó. Ví dụ:

- `p_before_2026`: ngày trước `2026-01-01`.
- `p2026q1`: từ `2026-01-01` đến trước `2026-04-01`.
- `p2026q2`: từ `2026-04-01` đến trước `2026-07-01`.
- `p_future`: từ `2027-01-01` trở đi.

### 3.2. Vì sao primary key gồm created_at?

Với bảng được partition theo một cột, MySQL yêu cầu mọi unique key của bảng, bao gồm primary key, phải chứa tất cả cột được dùng trong partitioning expression. Vì vậy, ví dụ dùng:

```sql
PRIMARY KEY (order_id, created_at)
```

thay vì chỉ `PRIMARY KEY (order_id)`.

Điều này có hệ quả thiết kế: unique constraint trên `(order_id, created_at)` không bảo đảm `order_id` đơn lẻ là duy nhất trên toàn bảng. Nếu nghiệp vụ cần mã đơn hàng duy nhất toàn cục, cần thiết kế cơ chế ID và tra cứu phù hợp, chẳng hạn ID được sinh duy nhất ở ứng dụng hoặc một bảng định danh riêng không phân vùng.

InnoDB partitioned table cũng không hỗ trợ foreign key theo các giới hạn partitioning của MySQL. Cần đánh giá ràng buộc tham chiếu trước khi quyết định partition một bảng có quan hệ khóa ngoại.

### 3.3. Truy vấn chỉ lấy quý 1 năm 2026

```sql
SELECT order_id, created_at, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

Khoảng này nằm hoàn toàn trong `p2026q1`. Optimizer có thể bỏ qua các partition còn lại.

### 3.4. Truy vấn đi qua hai quý

```sql
SELECT order_id, created_at, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-03-15'
  AND created_at <  '2026-04-15';
```

Truy vấn giao với hai partition:

- Phần từ `2026-03-15` đến trước `2026-04-01` thuộc `p2026q1`.
- Phần từ `2026-04-01` đến trước `2026-04-15` thuộc `p2026q2`.

Optimizer cần truy cập cả hai partition và có thể bỏ các partition khác.

### 3.5. Truy vấn không có cận thời gian

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PAID';
```

Không có điều kiện trên `created_at`, vì vậy không thể loại partition dựa trên thời gian. Dù có index `idx_orders_status_created`, MySQL vẫn có thể phải kiểm tra index ở tất cả partition.

## 4. Dùng biểu thức phân vùng và điều kiện phải khớp biểu thức

Một kiểu thiết kế khác là phân vùng theo biểu thức, ví dụ `YEAR(created_at)`.

### 4.1. RANGE theo YEAR(created_at)

```sql
CREATE TABLE yearly_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (order_id, created_at)
) ENGINE = InnoDB
PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

Với bảng này, biểu thức phân vùng là `YEAR(created_at)`. Điều kiện trực tiếp trên biểu thức:

```sql
SELECT order_id, created_at, total_amount
FROM yearly_orders
WHERE YEAR(created_at) = 2026;
```

có thể cho phép optimizer xác định partition `p2026`.

### 4.2. Điều kiện trực tiếp trên cột có thể không tương đương với biểu thức partition

Nếu bảng phân vùng theo `YEAR(created_at)`, điều kiện sau dễ biểu đạt đúng mục tiêu:

```sql
WHERE YEAR(created_at) = 2026
```

Điều kiện theo khoảng trên cột gốc:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
```

có thể được optimizer biến đổi trong một số trường hợp, nhưng không nên giả định mọi biểu thức partition đều được suy ra từ mọi predicate tương đương. Hãy xác nhận bằng `EXPLAIN` trên phiên bản và schema thật. Nếu muốn pruning dễ dự đoán, viết điều kiện khớp biểu thức phân vùng hoặc cân nhắc `RANGE COLUMNS(created_at)` để phân vùng trực tiếp theo cột.

### 4.3. Tránh bọc partition column trong hàm không khớp

Với bảng `orders` phân vùng bằng `RANGE COLUMNS(created_at)`, truy vấn:

```sql
SELECT order_id, created_at
FROM orders
WHERE YEAR(created_at) = 2026;
```

có thể làm pruning kém rõ ràng hơn vì biểu thức lọc không còn là khoảng trực tiếp trên cột phân vùng. Viết lại thành:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01';
```

Predicate trên cột gốc giúp optimizer đối chiếu trực tiếp với ranh giới `RANGE COLUMNS`, đồng thời thường thuận lợi cho range access trên B-tree index.

### 4.4. Tránh ép kiểu lên partition column

Giả sử `created_at` có kiểu `DATE`. Hãy so sánh với literal ngày phù hợp:

```sql
WHERE created_at >= DATE '2026-01-01'
  AND created_at <  DATE '2027-01-01'
```

Tránh viết biểu thức kiểu:

```sql
WHERE CAST(created_at AS CHAR) LIKE '2026%'
```

Việc biến đổi partition column có thể khiến optimizer không suy ra được range partition cần giữ, đồng thời làm giảm khả năng dùng B-tree index trực tiếp. Nếu đầu vào ứng dụng là chuỗi, hãy parse/validate thành giá trị DATE/DATETIME trước khi bind tham số.

## 5. Pruning với RANGE và LIST

### 5.1. RANGE partitioning

RANGE chia dữ liệu theo các khoảng liên tiếp. Các predicate có cận dưới/cận trên phù hợp với partition key thường hỗ trợ pruning tốt.

Ví dụ:

```sql
SELECT *
FROM yearly_orders
WHERE YEAR(created_at) >= 2025
  AND YEAR(created_at) < 2027;
```

Nếu partitioning expression là `YEAR(created_at)`, optimizer có thể giữ các partition có miền năm giao với khoảng `[2025, 2027)`.

### 5.2. LIST partitioning

LIST chia dữ liệu theo các giá trị rời rạc. Ví dụ phân vùng theo vùng bán hàng:

```sql
CREATE TABLE regional_sales (
    sale_id BIGINT NOT NULL,
    region_code CHAR(3) NOT NULL,
    sold_at DATE NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    PRIMARY KEY (sale_id, region_code)
) ENGINE = InnoDB
PARTITION BY LIST COLUMNS (region_code) (
    PARTITION p_north VALUES IN ('HN', 'HP'),
    PARTITION p_south VALUES IN ('HCM', 'CT'),
    PARTITION p_central VALUES IN ('DN', 'HU')
);
```

Truy vấn:

```sql
SELECT sale_id, region_code, amount
FROM regional_sales
WHERE region_code IN ('HCM', 'CT');
```

Optimizer có thể chỉ giữ partition `p_south`. Với LIST, điều kiện bằng hoặc `IN` trên partition key là dạng dễ pruning.

Điều kiện trên `sold_at` đơn lẻ không giới hạn `region_code`, nên không thể prune partition theo vùng.

## 6. Pruning với HASH và KEY

HASH và KEY thường dùng để phân phối hàng vào một số partition theo kết quả hàm băm. Chúng không tạo các khoảng thời gian hoặc danh sách giá trị dễ đọc như RANGE/LIST.

### 6.1. HASH partitioning

Ví dụ:

```sql
CREATE TABLE customer_activity (
    activity_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    occurred_at DATETIME NOT NULL,
    PRIMARY KEY (activity_id, customer_id)
) ENGINE = InnoDB
PARTITION BY HASH (customer_id)
PARTITIONS 8;
```

Với điều kiện bằng trên partition expression:

```sql
SELECT activity_id, customer_id, occurred_at
FROM customer_activity
WHERE customer_id = 9001;
```

optimizer có thể tính partition chứa giá trị `customer_id = 9001` và chỉ truy cập partition đó.

Điều kiện `customer_id BETWEEN 9000 AND 9100` không tương đương một khoảng partition liên tục vì hash phân phối giá trị qua các partition. Optimizer thường không thể bỏ các partition chỉ dựa trên range này; cần kiểm tra plan thực tế.

### 6.2. KEY partitioning

KEY dùng hàm băm do MySQL cung cấp dựa trên một hoặc nhiều cột:

```sql
CREATE TABLE session_events (
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_time DATETIME NOT NULL,
    PRIMARY KEY (event_id, tenant_id)
) ENGINE = InnoDB
PARTITION BY KEY (tenant_id)
PARTITIONS 8;
```

Điều kiện bằng hoặc tập giá trị xác định trên key có thể giúp pruning:

```sql
SELECT event_id, tenant_id, event_time
FROM session_events
WHERE tenant_id = 42;
```

Một truy vấn chỉ lọc theo `event_time` không cung cấp thông tin để xác định partition theo `tenant_id`; vì vậy có thể phải xét tất cả partition.

### 6.3. Không dùng HASH chỉ để mong range pruning

Nếu workload thường truy vấn theo tháng hoặc quý, RANGE theo ngày thường phù hợp hơn HASH theo ngày. HASH phân tán các giá trị, không giữ các giá trị thời gian gần nhau trong một partition liên tiếp.

Nếu workload thường truy vấn theo một tenant cụ thể, HASH/KEY theo tenant có thể giúp phân phối dữ liệu và prune theo tenant equality. Tuy nhiên, một tenant lớn có thể tạo skew; cần đánh giá phân bố dữ liệu và khả năng mở rộng.

## 7. AND, OR và IN trong điều kiện pruning

### 7.1. Kết hợp partition key với điều kiện khác bằng AND

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01'
  AND status = 'PAID';
```

Điều kiện thời gian có thể prune partition trước; điều kiện `status` tiếp tục lọc hàng trong partition còn lại. Một index như `(status, created_at)` hoặc `(created_at, status)` có phù hợp hay không phụ thuộc thứ tự truy vấn, độ chọn lọc và workload tổng thể.

### 7.2. OR trên các khoảng rời nhau

```sql
SELECT order_id, created_at
FROM orders
WHERE (created_at >= '2026-01-01' AND created_at < '2026-04-01')
   OR (created_at >= '2026-07-01' AND created_at < '2026-10-01');
```

Optimizer có thể xác định hai khoảng thời gian và chỉ giữ partition giao với chúng, ví dụ `p2026q1` và `p2026q3`. Khả năng pruning cụ thể phụ thuộc cách biểu thức được phân tích; kiểm tra `partitions` trong EXPLAIN.

### 7.3. IN với tập giá trị

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at IN ('2026-01-10', '2026-04-15', '2026-08-20');
```

Với RANGE COLUMNS theo `created_at`, các giá trị thuộc những partition khác nhau có thể khiến optimizer giữ đúng tập partition tương ứng. Nếu nhiều giá trị cùng nằm trong một partition, partition đó chỉ cần được truy cập một lần.

### 7.4. Điều kiện OR không liên quan partition key

```sql
SELECT order_id, created_at, customer_id
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-04-01'
   OR customer_id = 9001;
```

Do `AND` có độ ưu tiên cao hơn `OR`, biểu thức tương đương:

```sql
WHERE (created_at >= '2026-01-01' AND created_at < '2026-04-01')
   OR customer_id = 9001
```

Nhánh `customer_id = 9001` có thể khớp hàng ở bất kỳ partition thời gian nào. Vì vậy, optimizer không thể loại toàn bộ partition ngoài quý 1 chỉ dựa trên nhánh thời gian. Nếu ý định nghiệp vụ là cả hai điều kiện phải cùng đúng, hãy dùng `AND`; nếu thực sự cần `OR`, hãy hiểu rằng pruning có thể bị giới hạn.

Luôn dùng dấu ngoặc để thể hiện rõ logic Boolean và tránh vô tình làm mất khả năng pruning.

## 8. Pruning và index bên trong partition

Partitioning không thay thế index. Khi pruning giữ lại một hoặc nhiều partition, MySQL vẫn cần tìm hàng bên trong mỗi partition được chọn.

### 8.1. Index được tổ chức trong từng partition

Với InnoDB partitioned table, index được tổ chức cục bộ trong từng partition (local indexes). MySQL không cung cấp global index chung cho toàn bộ partition như một số hệ quản trị khác.

Ví dụ index:

```sql
KEY idx_orders_customer_created (customer_id, created_at)
```

được duy trì trong các partition của bảng. Khi truy vấn prune còn `p2026q1`, access path sử dụng index trong partition đó. Khi truy vấn phải đọc 8 partition, index lookup có thể diễn ra ở cả 8 partition.

### 8.2. Kết hợp pruning và index

Ví dụ:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01'
  AND customer_id = 9001;
```

Các bước logic:

1. Dùng điều kiện `created_at` để loại các partition ngoài quý 1.
2. Trong partition còn lại, dùng index phù hợp để tìm các hàng của `customer_id = 9001`.
3. Đọc các cột cần thiết và trả kết quả.

Nếu index không phù hợp, MySQL có thể full scan partition quý 1. Pruning đã giảm số vùng cần đọc nhưng chưa chắc giảm đủ chi phí bên trong vùng đó.

### 8.3. Không có điều kiện partition key nhưng có index tốt

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 9001;
```

Index customer có thể giúp tìm hàng nhanh trong mỗi partition, nhưng MySQL vẫn cần kiểm tra nhiều partition vì không biết khách hàng có đơn ở quý nào. Nếu truy vấn theo customer là workload chủ đạo và không có giới hạn thời gian, partition theo thời gian có thể không đem lại lợi ích cho truy vấn đó.

Đây là lý do phải chọn partition key theo workload thực tế, không chỉ theo cách dữ liệu được lưu.

## 9. Xác nhận partition pruning bằng EXPLAIN

Không suy luận rằng truy vấn đã prune chỉ vì `WHERE` có nhắc tới partition key. Hãy xem execution plan.

### 9.1. EXPLAIN FORMAT=JSON

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

Trong JSON plan, tìm thuộc tính `partitions` ở node tương ứng với bảng `orders`. Nó liệt kê các partition được optimizer chọn để truy cập. Với ví dụ quý 1, kỳ vọng danh sách chỉ gồm `p2026q1` nếu schema và ranh giới đúng như đã khai báo.

### 9.2. EXPLAIN PARTITIONS ở phiên bản hỗ trợ

Có thể gặp cú pháp truyền thống:

```sql
EXPLAIN PARTITIONS
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

Output dạng bảng có cột `partitions`, liệt kê partition được truy cập. Trong các bản MySQL mới, cú pháp `EXPLAIN PARTITIONS` được đánh dấu deprecated; ưu tiên `EXPLAIN FORMAT=JSON` cho công cụ và tài liệu mới.

### 9.3. Đọc cùng key, type và rows

Ngoài `partitions`, kiểm tra:

- `type`: cách truy cập trong partition, ví dụ `range`, `ref` hoặc `ALL`.
- `key`: index được chọn.
- `key_len`: phần index được dùng.
- `rows`: số hàng ước lượng phải đọc trong access path.
- `filtered`: tỷ lệ hàng ước lượng còn lại sau filter.
- `Extra`: điều kiện lọc, covering index, ICP hoặc sort.

Một plan chỉ truy cập một partition nhưng `type = ALL` có thể vẫn quét toàn bộ partition đó. Một plan truy cập nhiều partition với `type = ref` có thể dùng index hiệu quả bên trong mỗi partition.

### 9.4. EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01'
  AND customer_id = 9001;
```

`EXPLAIN ANALYZE` thực sự thực thi truy vấn và hiển thị số hàng/thời gian thực tế của các iterator. Dùng nó để xem chi phí còn lại sau khi partition pruning và index access.

Lệnh này tạo tải thực tế; hãy dùng trên truy vấn và môi trường phù hợp, không chạy tùy tiện với truy vấn nặng trên production.

## 10. Điều kiện làm pruning kém hiệu quả

### 10.1. Không lọc partition key

Truy vấn không có điều kiện trên partition key thường phải xét mọi partition:

```sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
```

Nếu bảng phân vùng theo `created_at`, điều kiện status không giúp xác định partition thời gian.

### 10.2. Bọc partition column trong hàm không khớp

Với `RANGE COLUMNS(created_at)`, dạng:

```sql
WHERE YEAR(created_at) = 2026
```

không trực tiếp mô tả range trên partition key. Viết thành khoảng ngày nếu có thể:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
```

### 10.3. So sánh sai kiểu dữ liệu hoặc ép kiểu cột

Đầu vào nên được bind đúng kiểu với partition key. Việc cast cột hoặc dùng biểu thức không tương thích có thể làm điều kiện khó phân tích và làm giảm pruning/index access.

### 10.4. OR mở rộng sang vùng dữ liệu không giới hạn

Một nhánh OR không ràng buộc partition key có thể buộc optimizer giữ nhiều partition hơn. Dùng ngoặc và kiểm tra logic điều kiện trước khi tối ưu.

### 10.5. Điều kiện phụ thuộc dữ liệu runtime khó suy ra

Predicate dựa trên giá trị từ bảng khác, biểu thức phức tạp hoặc subquery có thể khó cho optimizer xác định tập partition trước khi thực thi. Những trường hợp này cần kiểm tra plan thực tế; không giả định điều kiện tương đương với hằng số sẽ luôn được pruning như nhau.

## 11. Prepared statement và tham số thời gian

Ứng dụng thường gửi truy vấn có tham số:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= ?
  AND created_at < ?;
```

Với prepared statement, MySQL có thể sử dụng giá trị tham số khi thực thi để xác định partition cần truy cập trong các trường hợp hỗ trợ pruning. Hãy bind tham số đúng kiểu DATE/DATETIME/TIMESTAMP và xác minh bằng plan phù hợp với cách ứng dụng thực thi.

Không nối chuỗi ngày giờ trực tiếp vào SQL để tạo điều kiện partition. Prepared statement giúp tránh SQL injection và giảm lỗi định dạng/kiểu dữ liệu.

Nếu framework hoặc driver chuẩn bị câu lệnh theo cơ chế client-side thay vì server-side, cách quan sát plan có thể khác. Kiểm tra SQL thực tế và hành vi của connector đang sử dụng.

## 12. Theo dõi partition và kiểm tra định nghĩa

### 12.1. Xem DDL của bảng

```sql
SHOW CREATE TABLE orders;
```

Kiểm tra phần `PARTITION BY`, biểu thức phân vùng, ranh giới và tên partition. Đây là cách nhanh để xác nhận schema thật khác gì so với tài liệu thiết kế.

### 12.2. Xem danh sách partition qua INFORMATION_SCHEMA

```sql
SELECT
    PARTITION_NAME,
    PARTITION_ORDINAL_POSITION,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY PARTITION_ORDINAL_POSITION;
```

Với InnoDB, `TABLE_ROWS` là ước lượng, không phải số hàng chính xác. `DATA_LENGTH` và `INDEX_LENGTH` cung cấp số liệu dung lượng theo metadata; dùng công cụ giám sát hệ thống để đối chiếu dung lượng file và filesystem.

### 12.3. Kiểm tra partition nào được truy cập

Kết hợp:

1. `SHOW CREATE TABLE` để hiểu ranh giới partition.
2. `EXPLAIN FORMAT=JSON` để xem partition optimizer chọn.
3. `EXPLAIN ANALYZE` để đo số hàng/thời gian thực tế.
4. `INFORMATION_SCHEMA.PARTITIONS` để theo dõi kích thước và phân bố dữ liệu.

Không chỉ nhìn số partition được prune. Một partition rất lớn vẫn có thể là bottleneck; cần đánh giá số hàng, index và phân bố dữ liệu bên trong nó.

## 13. Những giới hạn thiết kế cần nhớ

Partitioning là quyết định thiết kế schema, không chỉ là một tùy chọn hiệu năng.

### 13.1. Mọi unique key phải chứa partitioning columns

Với partitioned table, mọi unique key phải bao gồm tất cả cột được dùng trong partitioning expression. Điều này ảnh hưởng primary key và các unique constraint khác.

Ví dụ partition theo `created_at` thì:

```sql
PRIMARY KEY (order_id, created_at)
```

có thể phù hợp, nhưng:

```sql
UNIQUE KEY uq_order_id (order_id)
```

không đáp ứng quy tắc nếu `created_at` không nằm trong unique key.

### 13.2. InnoDB partitioned table không hỗ trợ foreign key

Không thể tạo foreign key trên partitioned InnoDB table theo giới hạn partitioning của MySQL. Cũng không thể để bảng khác tham chiếu tới partitioned InnoDB table bằng foreign key.

Nếu schema phụ thuộc nhiều quan hệ FK, cần cân nhắc kỹ trước khi partition. Không nên bỏ constraint chỉ để có partition pruning mà chưa thay thế bằng cách bảo vệ toàn vẹn dữ liệu tương đương.

### 13.3. Partition không tự làm mọi truy vấn nhanh hơn

- Truy vấn không lọc partition key có thể phải truy cập mọi partition.
- Nhiều partition làm tăng metadata và chi phí lập kế hoạch/quản trị.
- Index vẫn cần được thiết kế cho truy vấn bên trong partition.
- Partition key có thể không phù hợp với các truy vấn quan trọng nhất.
- Phân bố dữ liệu lệch có thể làm một partition lớn hơn hẳn các partition khác.

### 13.4. Chọn partition key theo workload

Trước khi partition, hãy thống kê các truy vấn thực tế:

- Có bao nhiêu truy vấn lọc theo ngày/tháng/tenant?
- Truy vấn có luôn cung cấp partition key không?
- Dữ liệu cũ có được archive/drop theo kỳ không?
- Một partition có thể tăng đến kích thước nào?
- Unique key và foreign key hiện tại có tương thích không?
- Có cần truy vấn xuyên suốt toàn bộ lịch sử không?

Nếu phần lớn truy vấn không có điều kiện trên partition key, partitioning có thể không đem lại pruning như mong muốn.

## 14. Bài thực hành: xác minh pruning cho các dạng predicate

Dùng bảng `orders` đã tạo ở phần 3. Chèn dữ liệu thử nghiệm ở các ngày thuộc những partition khác nhau.

### Bài 1: Một partition

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

Kiểm tra JSON có chỉ liệt kê `p2026q1` trong `partitions` hay không.

### Bài 2: Hai partition

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at >= '2026-03-15'
  AND created_at <  '2026-04-15';
```

Kỳ vọng các partition giao với khoảng là `p2026q1` và `p2026q2`.

### Bài 3: Không có partition key

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PAID';
```

Quan sát optimizer phải xét những partition nào. Vì không có điều kiện trên `created_at`, thường không thể prune theo thời gian.

### Bài 4: So sánh predicate trực tiếp và hàm

```sql
-- Dạng trực tiếp trên partition key
EXPLAIN FORMAT=JSON
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01';

-- Dạng bọc cột trong hàm
EXPLAIN FORMAT=JSON
SELECT order_id
FROM orders
WHERE YEAR(created_at) = 2026;
```

So sánh danh sách partition. Bảng dùng `RANGE COLUMNS(created_at)`, vì vậy predicate trực tiếp thường thể hiện pruning rõ ràng hơn. Ghi lại kết quả thực tế của server thay vì giả định hai plan giống nhau.

### Bài 5: Pruning kết hợp index

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01'
  AND customer_id = 9001;
```

Kiểm tra đồng thời:

- Danh sách partition được giữ.
- Index được chọn trong partition.
- Số hàng ước lượng.
- Điều kiện còn lại được áp dụng.

### Bài 6: OR với một nhánh không giới hạn partition key

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, customer_id
FROM orders
WHERE (created_at >= '2026-01-01' AND created_at < '2026-04-01')
   OR customer_id = 9001;
```

Giải thích vì sao nhánh `customer_id = 9001` có thể yêu cầu giữ các partition ngoài quý 1.

## 15. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Query vẫn đọc mọi partition | Không có predicate trên partition key hoặc predicate không thể suy ra | Thêm điều kiện đúng nghiệp vụ trên partition key |
| `YEAR(date_col) = ...` không prune như mong đợi | Partition theo cột gốc hoặc biểu thức không khớp | Dùng range trực tiếp hoặc khớp partition expression |
| Prune còn một partition nhưng truy vấn vẫn chậm | Full scan hoặc index kém trong partition đó | Kiểm tra `type`, `key`, `rows`, `EXPLAIN ANALYZE` và thiết kế index |
| Có index tốt nhưng vẫn nhiều partition | Index không thay thế partition pruning | Thêm điều kiện partition key nếu nghiệp vụ có giới hạn |
| Partition key không có trong unique key | Vi phạm quy tắc unique key của partitioned table | Thiết kế lại primary/unique key và định danh toàn cục |
| Không tạo được foreign key | InnoDB partitioned table không hỗ trợ FK | Cân nhắc không partition hoặc thay thế bằng cơ chế toàn vẹn được thiết kế rõ ràng |
| OR làm mất pruning | Một nhánh có thể khớp mọi partition | Dùng ngoặc, xem lại logic và kiểm tra plan |
| Partition theo HASH nhưng range query không prune | Hash không bảo toàn thứ tự giá trị | Chọn RANGE nếu workload cần lọc theo khoảng |
| Dùng `PARTITION (...)` và thiếu dữ liệu | Người viết SQL đã loại partition cần thiết | Ưu tiên pruning tự động hoặc xác minh đầy đủ partition được chọn |
| Tin `TABLE_ROWS` là số hàng chính xác | Metadata InnoDB là ước lượng | Dùng COUNT khi cần số đếm chính xác và chấp nhận chi phí |

## 16. Quy trình tối ưu partition pruning

1. **Xác nhận partition expression:** đọc `SHOW CREATE TABLE` và xác định chính xác cột/hàm dùng để phân vùng.
2. **Chọn predicate phù hợp:** dùng equality, IN hoặc range trực tiếp trên partition key khi có thể.
3. **Dùng khoảng nửa mở cho thời gian:** `>= start AND < end`.
4. **Tránh biến đổi partition column:** không bọc cột trong hàm/cast không cần thiết.
5. **Kiểm tra logic AND/OR:** bảo đảm nhánh OR không vô tình mở rộng sang mọi partition.
6. **Chạy EXPLAIN:** xem `partitions` trong JSON hoặc định dạng tương thích.
7. **Kiểm tra index trong partition:** đánh giá `key`, `type`, `rows`, `filtered` và Extra.
8. **Đo thực tế:** dùng `EXPLAIN ANALYZE` phù hợp để so sánh estimated/actual rows và thời gian.
9. **Đối chiếu workload:** kiểm tra các truy vấn quan trọng có thực sự cung cấp partition key không.
10. **Xác minh giới hạn schema:** unique key, primary key và foreign key có tương thích với partitioning không.

## 17. Checklist trước khi triển khai production

- [ ] Partition key và partition expression được xác định rõ.
- [ ] Điều kiện truy vấn khớp partition expression hoặc là range trực tiếp có thể pruning.
- [ ] Predicate thời gian dùng cận dưới bao gồm và cận trên loại trừ.
- [ ] Tham số được bind đúng kiểu DATE/DATETIME/TIMESTAMP.
- [ ] Đã kiểm tra `partitions` trong `EXPLAIN FORMAT=JSON`.
- [ ] Đã phân biệt số partition được truy cập với số hàng phải đọc trong partition.
- [ ] Index trong từng partition hỗ trợ điều kiện lọc/JOIN còn lại.
- [ ] Đã kiểm tra các nhánh OR và biểu thức hàm/cast trên partition key.
- [ ] Đã xem xét workload không có điều kiện partition key.
- [ ] Mọi unique key bao gồm các cột dùng trong partitioning expression.
- [ ] Đã đánh giá giới hạn foreign key của InnoDB partitioned table.
- [ ] Đã kiểm tra skew dữ liệu, số lượng partition và chi phí quản trị.
- [ ] Đã đo truy vấn đại diện bằng EXPLAIN ANALYZE trong môi trường phù hợp.

## 18. Kết luận

Partition pruning cho phép optimizer bỏ qua partition chắc chắn không chứa hàng phù hợp. Để pruning hiệu quả, điều kiện truy vấn cần thể hiện trực tiếp partition key hoặc biểu thức phân vùng, thường bằng equality, `IN` hoặc range. Với dữ liệu thời gian, khoảng nửa mở `>= start AND < end` thường rõ ràng, tránh lỗi cận cuối và hỗ trợ range access.

RANGE/LIST phù hợp với điều kiện theo khoảng hoặc tập giá trị; HASH/KEY thường pruning tốt hơn với equality hoặc tập giá trị xác định, không giữ thứ tự để xử lý range. Pruning chỉ giảm số partition cần xét; index vẫn quyết định cách tìm hàng bên trong từng partition. Hãy kiểm tra `partitions`, `key`, `type`, `rows` và actual execution, đồng thời tính đến giới hạn unique key và foreign key của partitioned InnoDB table trước khi đưa thiết kế vào production.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: Partition Pruning](https://dev.mysql.com/doc/refman/8.4/en/partitioning-pruning.html)
- [MySQL 8.4 Reference Manual: Partitioning Types](https://dev.mysql.com/doc/refman/8.4/en/partitioning-types.html)
- [MySQL 8.4 Reference Manual: Partitioning Limitations](https://dev.mysql.com/doc/refman/8.4/en/partitioning-limitations.html)
- [MySQL 8.4 Reference Manual: EXPLAIN Output Format](https://dev.mysql.com/doc/refman/8.4/en/explain-output.html)
