# RANGE, LIST, HASH, KEY và biến thể COLUMNS

MySQL cho phép chia một bảng lớn thành nhiều **partition** theo quy tắc xác định trước. Ứng dụng vẫn truy vấn một tên bảng duy nhất, còn MySQL xác định partition cần đọc hoặc ghi dựa trên giá trị của partition key. Bốn chiến lược chính là `RANGE`, `LIST`, `HASH` và `KEY`; `RANGE COLUMNS` và `LIST COLUMNS` là các biến thể cho phép dùng trực tiếp một hoặc nhiều cột làm khóa phân vùng.

Chọn đúng chiến lược phụ thuộc vào cách dữ liệu được chia: theo khoảng ngày/số, theo danh sách nhóm giá trị, phân phối theo hàm băm hay phân phối bằng thuật toán băm nội bộ của MySQL. Partitioning có thể giúp loại bỏ partition không liên quan khi truy vấn (partition pruning) và đơn giản hóa vòng đời dữ liệu. Nó không tự thay thế index, không tự phân phối dữ liệu sang nhiều server và không bảo đảm mọi truy vấn đều nhanh hơn.

Bài học thuộc module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Trong chương **Phân vùng**, bài này tập trung vào `RANGE`, `LIST`, `HASH`, `KEY` và các biến thể `COLUMNS`.

## 1. Partitioning là gì?

Partitioning chia dữ liệu của một bảng thành các phần do storage engine quản lý. Với người dùng SQL, bảng vẫn được tham chiếu bằng một tên duy nhất:

```sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE order_date >= '2026-01-01'
  AND order_date <  '2026-02-01';
```

Nếu bảng được partition theo ngày, optimizer có thể xác định chỉ một số partition chứa dữ liệu thuộc khoảng ngày này và bỏ qua các partition còn lại.

Các khái niệm cần phân biệt:

- **Partition key:** cột hoặc biểu thức xác định một hàng thuộc partition nào.
- **Partition:** một phần dữ liệu trong bảng partitioned.
- **Partition pruning:** tối ưu loại bỏ partition chắc chắn không chứa hàng thỏa điều kiện.
- **Partitioned table:** bảng được chia partition nhưng vẫn được truy vấn như một bảng.

Trong MySQL, partitioning là cơ chế chia dữ liệu trong cùng một instance/server. Nó không phải sharding và không tự chuyển partition sang các máy chủ khác. Với InnoDB, mỗi partition có cấu trúc index của riêng nó; MySQL không cung cấp global index chung xuyên tất cả partition.

## 2. Chọn chiến lược phân vùng

| Chiến lược | Cách xác định partition | Phù hợp khi |
|---|---|---|
| `RANGE` | Giá trị của biểu thức nằm trong một khoảng | Dữ liệu theo thời gian, số thứ tự hoặc các dải số. |
| `RANGE COLUMNS` | Giá trị của một hay nhiều cột nằm trong khoảng | Muốn phân vùng trực tiếp theo `DATE`, `DATETIME`, chuỗi hoặc nhiều cột. |
| `LIST` | Giá trị biểu thức thuộc một danh sách xác định | Nhóm mã khu vực, loại sản phẩm hoặc nhóm nghiệp vụ có mã số. |
| `LIST COLUMNS` | Một hay nhiều cột thuộc danh sách giá trị/tuple | Nhóm theo chuỗi, ngày hoặc nhiều cột mà không cần biểu thức số nguyên. |
| `HASH` | Kết quả biểu thức số nguyên được băm để phân phối | Muốn chia tương đối đều theo một giá trị, không có ranh giới nghiệp vụ tự nhiên. |
| `KEY` | MySQL áp dụng hàm băm nội bộ trên một hay nhiều cột | Muốn phân phối theo các cột có kiểu dữ liệu khác nhau mà không tự viết biểu thức hash. |

`RANGE`/`LIST` biểu diễn miền dữ liệu do người thiết kế định nghĩa. `HASH`/`KEY` phân phối hàng theo kết quả băm. Chọn chiến lược theo predicate truy vấn và quy trình lưu trữ dữ liệu, không chỉ theo số lượng hàng.

## 3. RANGE partitioning

`RANGE` chia dữ liệu thành các khoảng không chồng lấn. Mỗi partition khai báo một cận trên bằng `VALUES LESS THAN`. Giá trị bằng cận trên thuộc partition kế tiếp, không thuộc partition hiện tại.

Ví dụ chia đơn hàng theo năm:

```sql
CREATE TABLE orders_by_year (
    order_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, order_date),
    KEY idx_customer_date (customer_id, order_date)
) ENGINE = InnoDB
PARTITION BY RANGE (YEAR(order_date)) (
    PARTITION p_before_2024 VALUES LESS THAN (2024),
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

Ý nghĩa các partition:

- `p_before_2024`: `YEAR(order_date) < 2024`.
- `p2024`: `2024 <= YEAR(order_date) < 2025`.
- `p2025`: `2025 <= YEAR(order_date) < 2026`.
- `p_future`: mọi giá trị còn lại, nhờ cận `MAXVALUE`.

`VALUES LESS THAN (2025)` là cận loại trừ. Ngày thuộc năm 2025 được đưa vào `p2025`, không vào `p2024`.

### 3.1. Chèn và truy vấn dữ liệu

```sql
INSERT INTO orders_by_year
    (order_id, order_date, customer_id, total_amount)
VALUES
    (1001, '2024-12-31', 42, 150.00),
    (1002, '2025-01-01', 42, 250.00),
    (1003, '2025-08-15', 51, 300.00),
    (1004, '2026-02-10', 51, 450.00);
```

Truy vấn theo chính biểu thức phân vùng:

```sql
SELECT order_id, order_date, total_amount
FROM orders_by_year
WHERE YEAR(order_date) = 2025;
```

Điều kiện tương thích với biểu thức `YEAR(order_date)` giúp optimizer nhận diện partition cần đọc. Có thể xem partition được chọn bằng:

```sql
EXPLAIN
SELECT order_id, order_date, total_amount
FROM orders_by_year
WHERE YEAR(order_date) = 2025;
```

Trong kết quả `EXPLAIN`, cột `partitions` cho biết các partition mà kế hoạch dự kiến truy cập.

### 3.2. MAXVALUE và quản lý khoảng tương lai

`MAXVALUE` là cận lớn nhất, thường dùng để gom các giá trị chưa được chia partition riêng. Khi đã có partition `MAXVALUE`, không thể chỉ `ADD PARTITION` một partition có cận lớn hơn nó. Muốn tách một khoảng mới ra khỏi partition cuối, cần tổ chức lại partition chứa `MAXVALUE` bằng `REORGANIZE PARTITION`.

Ví dụ sau chỉ minh họa cấu trúc thao tác trên bảng lab:

```sql
ALTER TABLE orders_by_year
REORGANIZE PARTITION p_future INTO (
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

Sau thao tác, dữ liệu năm 2026 thuộc `p2026`, còn dữ liệu từ năm 2027 trở đi thuộc `p_future`. DDL partition có thể di chuyển hoặc tổ chức lại lượng dữ liệu lớn; hãy kiểm tra dung lượng, thời gian khóa và kế hoạch vận hành trước khi thực hiện trên bảng production.

## 4. RANGE COLUMNS

`RANGE COLUMNS` cho phép phân vùng trực tiếp theo giá trị của một hoặc nhiều cột. Không cần bọc cột ngày trong `YEAR()` hoặc `TO_DAYS()`. Nó hỗ trợ các kiểu cột như số nguyên, `DATE`, `DATETIME` và chuỗi; không dùng biểu thức tùy ý trong danh sách cột.

Ví dụ phân vùng trực tiếp theo ngày:

```sql
CREATE TABLE orders_by_date (
    order_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, order_date),
    KEY idx_customer_date (customer_id, order_date)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (order_date) (
    PARTITION p_before_2025 VALUES LESS THAN ('2025-01-01'),
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Truy vấn theo khoảng ngày:

```sql
SELECT order_id, order_date, total_amount
FROM orders_by_date
WHERE order_date >= '2025-04-01'
  AND order_date <  '2025-05-01';
```

Điều kiện range trực tiếp trên `order_date` phù hợp với ranh giới của `RANGE COLUMNS`, giúp optimizer có thể pruning các partition nằm ngoài khoảng truy vấn.

### 4.1. RANGE COLUMNS với nhiều cột

`RANGE COLUMNS` có thể nhận nhiều cột. MySQL so sánh các giá trị theo thứ tự từ trái sang phải như tuple:

```sql
CREATE TABLE shipment_events (
    event_id BIGINT NOT NULL,
    event_date DATE NOT NULL,
    region_id INT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    PRIMARY KEY (event_id, event_date, region_id)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date, region_id) (
    PARTITION p_early VALUES LESS THAN ('2025-01-01', 100),
    PARTITION p_late VALUES LESS THAN ('2026-01-01', 100),
    PARTITION p_future VALUES LESS THAN (MAXVALUE, MAXVALUE)
);
```

Với tuple `(event_date, region_id)`, `event_date` được so sánh trước. `region_id` chỉ quyết định thứ tự khi `event_date` bằng nhau. Vì vậy, đây không phải cách chia độc lập theo từng vùng rồi từng năm; hãy dùng nhiều cột chỉ khi thứ tự tuple đúng với ranh giới nghiệp vụ.

## 5. LIST partitioning

`LIST` đưa hàng vào partition dựa trên việc giá trị biểu thức có thuộc danh sách đã khai báo hay không. Biểu thức `LIST` truyền thống phải cho kết quả số nguyên.

Ví dụ chia theo mã vùng dạng số:

```sql
CREATE TABLE sales_by_region_id (
    sale_id BIGINT NOT NULL,
    region_id INT NOT NULL,
    sale_date DATE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (sale_id, region_id),
    KEY idx_region_date (region_id, sale_date)
) ENGINE = InnoDB
PARTITION BY LIST (region_id) (
    PARTITION p_north VALUES IN (1, 2),
    PARTITION p_central VALUES IN (3, 4),
    PARTITION p_south VALUES IN (5, 6)
);
```

Các giá trị:

- `region_id` 1 và 2 thuộc `p_north`.
- `region_id` 3 và 4 thuộc `p_central`.
- `region_id` 5 và 6 thuộc `p_south`.

Khác với `RANGE`, `LIST` không có cận `MAXVALUE` để nhận mọi giá trị còn lại. Nếu insert một `region_id` chưa xuất hiện trong danh sách partition, MySQL báo lỗi không tìm thấy partition phù hợp. Phải cập nhật cấu hình partition khi miền giá trị nghiệp vụ mở rộng.

### 5.1. Truy vấn và pruning

```sql
SELECT sale_id, sale_date, amount
FROM sales_by_region_id
WHERE region_id IN (1, 2);
```

Điều kiện trên partition key cho phép optimizer chỉ xét partition tương ứng nếu có thể xác định tập giá trị. Dùng `EXPLAIN` để kiểm tra cột `partitions`.

## 6. LIST COLUMNS

`LIST COLUMNS` cho phép dùng trực tiếp cột có kiểu dữ liệu không phải số nguyên, ví dụ `VARCHAR`, `DATE` hoặc kiểu số. Nó cũng cho phép phân vùng theo nhiều cột.

Ví dụ chia doanh số theo mã vùng dạng chuỗi:

```sql
CREATE TABLE sales_by_region (
    sale_id BIGINT NOT NULL,
    region_code VARCHAR(20) NOT NULL,
    sale_date DATE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (sale_id, region_code),
    KEY idx_region_date (region_code, sale_date)
) ENGINE = InnoDB
PARTITION BY LIST COLUMNS (region_code) (
    PARTITION p_north VALUES IN ('NORTH', 'NORTHEAST'),
    PARTITION p_central VALUES IN ('CENTRAL'),
    PARTITION p_south VALUES IN ('SOUTH', 'SOUTHWEST')
);
```

Truy vấn:

```sql
SELECT sale_id, region_code, amount
FROM sales_by_region
WHERE region_code = 'NORTH';
```

`LIST COLUMNS` giúp tránh việc phải chuyển mã chuỗi thành một biểu thức số nguyên chỉ để phân vùng. Tuy nhiên, danh sách vẫn phải bao phủ mọi giá trị có thể được ghi.

### 6.1. LIST COLUMNS với nhiều cột

Có thể khai báo partition theo tuple gồm nhiều cột:

```sql
CREATE TABLE regional_sales (
    sale_id BIGINT NOT NULL,
    country_code CHAR(2) NOT NULL,
    region_code VARCHAR(20) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (sale_id, country_code, region_code)
) ENGINE = InnoDB
PARTITION BY LIST COLUMNS (country_code, region_code) (
    PARTITION p_vn_north VALUES IN (('VN', 'NORTH')),
    PARTITION p_vn_south VALUES IN (('VN', 'SOUTH')),
    PARTITION p_us_north VALUES IN (('US', 'NORTH')),
    PARTITION p_us_south VALUES IN (('US', 'SOUTH'))
);
```

Mỗi tuple `(country_code, region_code)` phải khớp một danh sách đã khai báo. `LIST COLUMNS` nhiều cột hữu ích khi một tổ hợp giá trị là đơn vị phân vùng tự nhiên; số partition sẽ tăng nhanh nếu kết hợp quá nhiều chiều phân loại.

## 7. HASH partitioning

`HASH` dùng kết quả của một biểu thức số nguyên để phân phối hàng vào số lượng partition cố định. MySQL áp dụng phép băm/modulo nội bộ dựa trên biểu thức và số partition.

Ví dụ chia đơn hàng theo khách hàng thành tám partition:

```sql
CREATE TABLE orders_by_customer_hash (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, customer_id),
    KEY idx_customer_date (customer_id, order_date)
) ENGINE = InnoDB
PARTITION BY HASH (customer_id)
PARTITIONS 8;
```

MySQL tính partition từ `customer_id`; người dùng không cần chỉ định giá trị của từng partition. Với tám partition, mỗi hàng được phân phối vào một trong tám partition theo kết quả hash.

### 7.1. HASH theo biểu thức

Biểu thức `HASH` phải cho kết quả số nguyên. Ví dụ:

```sql
CREATE TABLE events_by_month_hash (
    event_id BIGINT NOT NULL,
    event_date DATE NOT NULL,
    payload_size INT NOT NULL,
    PRIMARY KEY (event_id, event_date)
) ENGINE = InnoDB
PARTITION BY HASH (MONTH(event_date))
PARTITIONS 4;
```

Ví dụ này minh họa cú pháp; nó không phải thiết kế tốt để phân chia dữ liệu theo thời gian vì tháng 1 của mọi năm sẽ cùng được hash từ giá trị tháng 1. Nếu cần quản lý dữ liệu theo năm/tháng và pruning theo khoảng ngày, `RANGE` hoặc `RANGE COLUMNS` thường phù hợp hơn.

### 7.2. HASH và phân phối dữ liệu

`HASH` không cho phép người thiết kế chỉ định hàng cụ thể vào partition nào. Phân phối phụ thuộc vào giá trị biểu thức và số partition. Nó có thể giúp trải đều dữ liệu nếu giá trị đầu vào có phân bố phù hợp, nhưng không bảo đảm mỗi partition có đúng cùng số hàng.

Nếu truy vấn thường lọc theo partition key, optimizer có thể xác định partition cần đọc. Nếu truy vấn không có điều kiện tương ứng, MySQL có thể phải xét nhiều hoặc toàn bộ partition.

## 8. KEY partitioning

`KEY` cũng phân phối hàng bằng hash, nhưng MySQL tự chọn hàm băm nội bộ thay vì yêu cầu người dùng viết biểu thức số nguyên. Có thể dùng một hoặc nhiều cột với các kiểu dữ liệu được hỗ trợ.

Ví dụ:

```sql
CREATE TABLE customers_by_key (
    customer_id BIGINT NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (customer_id, email),
    KEY idx_created_at (created_at)
) ENGINE = InnoDB
PARTITION BY KEY (customer_id)
PARTITIONS 8;
```

`KEY (customer_id)` dùng thuật toán hash của MySQL để chọn partition. Khác với `HASH`, người dùng không cung cấp biểu thức như `YEAR(created_at)` hoặc `customer_id + 1`.

### 8.1. KEY với nhiều cột

```sql
PARTITION BY KEY (customer_id, created_at)
PARTITIONS 8;
```

Danh sách cột tham gia hash ảnh hưởng cách dữ liệu được phân phối. Nếu bỏ danh sách cột, MySQL dùng primary key nếu có; nếu không có, có thể dùng unique key phù hợp theo quy tắc của KEY partitioning. Khi thiết kế production, nên khai báo cột tường minh để thể hiện rõ partition key.

`KEY` thường hữu ích khi muốn phân phối theo các cột có kiểu chuỗi hoặc kiểu dữ liệu mà không tiện chuyển thành một biểu thức số nguyên. Tuy nhiên, lựa chọn cột vẫn phải phù hợp với các truy vấn cần pruning và các ràng buộc khóa duy nhất.

## 9. LINEAR HASH và LINEAR KEY

MySQL hỗ trợ hai biến thể `LINEAR HASH` và `LINEAR KEY`:

```sql
PARTITION BY LINEAR HASH (customer_id)
PARTITIONS 8;
```

```sql
PARTITION BY LINEAR KEY (customer_id)
PARTITIONS 8;
```

Hai biến thể này sử dụng thuật toán linear hashing, khác với cách phân phối hash thông thường. Thuật toán được thiết kế để việc mở rộng hoặc thu hẹp số partition có thể cần ít công việc tái phân phối hơn trong một số trường hợp, nhưng phân phối dữ liệu có thể khác với `HASH`/`KEY` thông thường.

Không chọn `LINEAR` chỉ vì tên có vẻ tối ưu hơn. Hãy đánh giá số partition, độ phân bố khóa, thao tác thêm/bớt partition và kế hoạch truy vấn thực tế.

## 10. So sánh RANGE, LIST, HASH, KEY và COLUMNS

| Đặc điểm | RANGE | RANGE COLUMNS | LIST | LIST COLUMNS | HASH | KEY |
|---|---|---|---|---|---|---|
| Định nghĩa partition | Cận trên của khoảng | Cận trên theo cột/tuple | Danh sách giá trị | Danh sách giá trị/tuple | Số partition | Số partition |
| Partition key | Biểu thức | Một hoặc nhiều cột | Biểu thức | Một hoặc nhiều cột | Biểu thức số nguyên | Một hoặc nhiều cột |
| Dùng trực tiếp DATE/DATETIME | Thường cần biểu thức chuyển đổi | Có | Thường cần biểu thức số nguyên | Có | Biểu thức phải trả số nguyên | Có thể dùng cột kiểu được hỗ trợ |
| Có partition catch-all | Có thể dùng `MAXVALUE` | Có thể dùng `MAXVALUE` | Không có `MAXVALUE` | Không có `MAXVALUE` | Không áp dụng | Không áp dụng |
| Phân phối | Theo khoảng có thứ tự | Theo khoảng có thứ tự | Theo tập giá trị | Theo tập giá trị | Theo hash expression | Theo hash nội bộ MySQL |
| Mục tiêu thường gặp | Vòng đời dữ liệu theo khoảng | Phân vùng ngày/cột trực tiếp | Nhóm mã số hữu hạn | Nhóm chuỗi/tuple hữu hạn | Phân phối tương đối đều | Phân phối theo cột không cần tự viết hash |

Lưu ý: `COLUMNS` chỉ là biến thể của `RANGE` và `LIST`. Không có cú pháp `HASH COLUMNS` hoặc `KEY COLUMNS`.

## 11. Ràng buộc khóa chính và unique key

Đây là một trong những giới hạn thiết kế quan trọng nhất của MySQL partitioning: **mọi unique key của bảng, bao gồm primary key, phải chứa tất cả các cột được dùng trong partitioning expression**.

Ví dụ bảng phân vùng theo `order_date`:

```sql
CREATE TABLE orders_partitioned (
    order_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    PRIMARY KEY (order_id, order_date)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (order_date) (
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Primary key chứa `order_date`, vì đây là partition key. Nếu khai báo `PRIMARY KEY (order_id)` riêng, MySQL sẽ từ chối vì unique key không bao gồm `order_date`.

### 11.1. Ảnh hưởng đến tính duy nhất toàn bảng

Với primary key `(order_id, order_date)`, MySQL bảo đảm tính duy nhất của cặp giá trị, không bảo đảm `order_id` riêng lẻ duy nhất trên mọi partition. Hai hàng có cùng `order_id` nhưng khác `order_date` vẫn có thể thỏa khóa ghép.

Nếu nghiệp vụ yêu cầu `order_id` duy nhất toàn bảng, cần cân nhắc lại thiết kế partition key hoặc cơ chế bảo đảm uniqueness ở tầng ứng dụng/bảng tra cứu riêng. Không thể giả định một unique index chỉ trên `order_id` vẫn hoạt động khi partition theo `order_date`.

## 12. Các giới hạn quan trọng của InnoDB partitioning

Trước khi partition một bảng nghiệp vụ, cần kiểm tra các ràng buộc:

- Bảng partitioned InnoDB không hỗ trợ foreign key constraint; nó cũng không thể được một foreign key ở bảng khác tham chiếu theo cách thông thường.
- Mọi unique key phải bao gồm tất cả cột trong partitioning expression.
- Partitioning expression phải tuân theo tập cú pháp/hàm MySQL cho phép; không dùng subquery, stored function, UDF hoặc biến làm partition key.
- `RANGE` và `LIST` truyền thống dùng biểu thức trả về số nguyên; nếu muốn dùng trực tiếp `DATE`, `DATETIME` hoặc chuỗi, xem xét biến thể `COLUMNS`.
- `BLOB` và `TEXT` không thể được dùng làm partitioning columns.
- Tất cả partition của một bảng dùng cùng storage engine và cùng định nghĩa cột/index.
- Không có global index xuyên tất cả partition; index được tổ chức theo partition.

Đặc biệt, giới hạn foreign key có thể làm partitioning không phù hợp với schema quan hệ có nhiều quan hệ tham chiếu. Hãy đánh giá ràng buộc dữ liệu trước khi chọn partitioning chỉ vì bảng có nhiều hàng.

## 13. Partition pruning

Partition pruning là khả năng optimizer bỏ qua các partition chắc chắn không thể chứa hàng thỏa điều kiện. Đây thường là lợi ích truy vấn quan trọng nhất của partitioning.

Với bảng `orders_by_date` được phân vùng bằng `RANGE COLUMNS(order_date)`, truy vấn:

```sql
EXPLAIN
SELECT order_id, order_date, total_amount
FROM orders_by_date
WHERE order_date >= '2025-04-01'
  AND order_date <  '2025-05-01';
```

có thể chỉ truy cập partition `p2025`, vì các partition còn lại không chứa ngày trong khoảng này.

Trong `EXPLAIN`, kiểm tra:

- `partitions`: danh sách partition được truy cập.
- `type`, `key`, `rows`: cách truy cập index và số hàng ước lượng bên trong các partition được chọn.
- `Extra`: các điều kiện lọc hoặc bước xử lý bổ sung.

Partition pruning và index lookup là hai lớp tối ưu khác nhau. Pruning giảm số partition cần xét; index giúp tìm hàng bên trong partition được chọn. Một truy vấn có pruning tốt vẫn có thể quét nhiều hàng trong partition nếu thiếu index phù hợp.

### 13.1. Viết điều kiện tương thích với partition key

Nếu phân vùng theo:

```sql
PARTITION BY RANGE (YEAR(order_date))
```

thì truy vấn theo biểu thức:

```sql
WHERE YEAR(order_date) = 2025
```

là cách trực tiếp để thể hiện điều kiện trên partition expression.

Nếu phân vùng theo:

```sql
PARTITION BY RANGE COLUMNS (order_date)
```

thì truy vấn range trực tiếp:

```sql
WHERE order_date >= '2025-01-01'
  AND order_date <  '2026-01-01'
```

phù hợp với partition key. Không bọc cột trong hàm không cần thiết khi mục tiêu là giúp optimizer nhận diện ranh giới partition.

## 14. Quản lý và kiểm tra partition

Có thể xem định nghĩa bảng:

```sql
SHOW CREATE TABLE orders_by_date;
```

Xem thông tin partition qua metadata:

```sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders_by_date'
ORDER BY PARTITION_ORDINAL_POSITION;
```

`TABLE_ROWS` đối với InnoDB là số liệu ước lượng, không phải lúc nào cũng là số đếm chính xác. Nếu cần số lượng chính xác, hãy chạy `COUNT(*)` với điều kiện phù hợp và cân nhắc chi phí đọc.

Một số thao tác DDL thường gặp:

```sql
-- Thêm partition RANGE mới khi bảng chưa có MAXVALUE
ALTER TABLE some_range_table
ADD PARTITION (
    PARTITION p2027 VALUES LESS THAN (2028)
);
```

```sql
-- Tổ chức lại partition cuối có MAXVALUE
ALTER TABLE orders_by_year
REORGANIZE PARTITION p_future INTO (
    PARTITION p2027 VALUES LESS THAN (2028),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

```sql
-- Xem trước định nghĩa và danh sách partition
SHOW CREATE TABLE orders_by_year;
```

`DROP PARTITION` có thể xóa toàn bộ dữ liệu trong partition bị loại bỏ. Đây là thao tác có tính phá hủy dữ liệu; phải xác minh partition, backup/retention và phê duyệt vận hành trước khi thực hiện.

## 15. Khi nào nên dùng từng chiến lược?

### RANGE / RANGE COLUMNS

Chọn khi dữ liệu có ranh giới tự nhiên theo thời gian, số thứ tự hoặc khoảng giá trị. Ví dụ đơn hàng theo tháng/năm, log theo ngày hoặc dữ liệu theo dải ID. `RANGE COLUMNS` phù hợp khi muốn dùng trực tiếp `DATE`/`DATETIME` và predicate range.

### LIST / LIST COLUMNS

Chọn khi giá trị thuộc các nhóm hữu hạn được định nghĩa trước, ví dụ vùng địa lý, loại tenant hoặc mã nghiệp vụ. Cần có quy trình cập nhật partition khi danh mục giá trị mở rộng. Nếu dữ liệu mới thường xuyên xuất hiện mà không thể dự báo danh sách, LIST có thể gây lỗi insert vì thiếu partition.

### HASH

Chọn khi muốn phân phối theo một biểu thức số nguyên và không có ranh giới nghiệp vụ phù hợp với RANGE/LIST. Cần xem truy vấn có lọc theo cùng partition key không; nếu không, pruning có thể không giúp nhiều.

### KEY

Chọn khi muốn phân phối theo một hoặc nhiều cột mà không tự xây biểu thức hash số nguyên. KEY tiện khi cột có kiểu chuỗi hoặc kiểu dữ liệu mà HASH expression không dùng trực tiếp được.

## 16. Partitioning không thay thế index hoặc thiết kế truy vấn

Một bảng có 100 partition không đồng nghĩa một truy vấn sẽ nhanh gấp 100 lần. Nếu truy vấn không lọc theo partition key, MySQL có thể phải xét tất cả partition. Nếu mỗi partition thiếu index phù hợp, engine vẫn phải quét nhiều hàng bên trong từng partition.

Hãy phân biệt:

| Cơ chế | Giải quyết vấn đề |
|---|---|
| Partitioning | Chia dữ liệu và có thể loại partition không liên quan. |
| Index | Tìm hàng hiệu quả bên trong cấu trúc dữ liệu/partition. |
| Query tuning | Giảm số hàng cần đọc, giảm phép tính và cải thiện thứ tự thực thi. |
| Sharding | Phân phối dữ liệu qua nhiều node/server do kiến trúc ứng dụng hoặc middleware quản lý. |

Một bảng nhỏ thường không cần partition. Partitioning cũng làm schema, unique key, foreign key và quy trình DDL phức tạp hơn. Hãy đo bằng dữ liệu thực tế và xác định lợi ích rõ ràng trước khi áp dụng.

## 17. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `RANGE` nhưng bỏ sót khoảng giá trị | Insert ngoài mọi partition bị lỗi | Khai báo cận phù hợp hoặc `MAXVALUE` nếu chiến lược cần catch-all. |
| Dùng `LIST` nhưng quên giá trị mới | Insert giá trị chưa được liệt kê bị lỗi | Quản lý danh mục và partition cùng quy trình phát hành. |
| Dùng `RANGE` cho ngày nhưng không hiểu `YEAR()` | Truy vấn theo predicate khác biểu thức có thể không pruning như kỳ vọng | Dùng predicate tương thích hoặc `RANGE COLUMNS`. |
| Quên partition key trong unique key | DDL bị MySQL từ chối | Đưa mọi cột partition expression vào tất cả unique key, kể cả PK. |
| Nghĩ `PRIMARY KEY(order_id, order_date)` bảo đảm order_id duy nhất | Chỉ cặp `(order_id, order_date)` là duy nhất | Thiết kế cách bảo đảm uniqueness toàn bảng phù hợp nghiệp vụ. |
| Cần foreign key trên bảng InnoDB partitioned | Không tạo được ràng buộc FK | Đánh giá lại partitioning hoặc thiết kế quan hệ. |
| Tạo quá nhiều partition | Tăng chi phí metadata, optimizer và quản trị | Chọn số partition theo workload và vòng đời dữ liệu. |
| Nghĩ partitioning tự tăng tốc mọi truy vấn | Truy vấn không pruning vẫn có thể đọc nhiều partition | Kiểm tra `EXPLAIN` và index trong từng partition. |
| Nghĩ partitioning là sharding | Kỳ vọng dữ liệu tự chạy trên nhiều server | Dùng kiến trúc sharding riêng nếu cần phân phối đa node. |
| DROP PARTITION mà không kiểm tra dữ liệu | Mất toàn bộ hàng trong partition | Kiểm tra retention, backup và đúng tên partition trước DDL. |

## 18. Quy trình thiết kế partitioning

1. **Xác định vấn đề cần giải quyết.** Làm rõ truy vấn chậm, vòng đời dữ liệu, dung lượng hay thao tác xóa dữ liệu cũ.
2. **Đọc workload.** Thống kê predicate thường dùng, khoảng thời gian truy vấn, join và cách phân trang.
3. **Chọn partition key.** Chọn cột/biểu thức có quan hệ trực tiếp với điều kiện truy vấn và vòng đời dữ liệu.
4. **Chọn chiến lược.** RANGE cho khoảng, LIST cho tập giá trị, HASH/KEY cho phân phối.
5. **Kiểm tra ràng buộc.** Đảm bảo mọi unique key chứa partition key; đánh giá foreign key và kiểu dữ liệu.
6. **Thiết kế ranh giới.** Tránh khoảng trống, chồng lấn và thiếu giá trị; cân nhắc MAXVALUE với RANGE.
7. **Thiết kế index trong partition.** Tạo index phục vụ truy vấn sau khi pruning.
8. **Kiểm tra bằng dữ liệu đại diện.** Bao gồm giá trị tại ngay trước, bằng và sau ranh giới partition.
9. **Đọc EXPLAIN.** Xem `partitions`, `key`, `type`, `rows` và `Extra`.
10. **Lập kế hoạch vận hành.** Xác định lịch thêm/reorganize/drop partition, backup và retention.
11. **Đo toàn workload.** So sánh truy vấn đọc, ghi, DDL và chi phí quản trị trước/sau.

## 19. Bài tập thực hành

### Bài tập 1: RANGE theo năm

Tạo bảng đơn hàng partition theo `YEAR(order_date)` với các partition cho năm 2024, 2025 và một partition tương lai.

**Yêu cầu:** insert hàng ở ngày cuối năm và ngày đầu năm tiếp theo; xác định partition đích và giải thích cận `VALUES LESS THAN`.

### Bài tập 2: RANGE COLUMNS theo ngày

Tạo bảng partition trực tiếp theo `order_date` bằng `RANGE COLUMNS`.

**Yêu cầu:** truy vấn một tháng bằng điều kiện range; dùng `EXPLAIN` kiểm tra cột `partitions`.

### Bài tập 3: LIST theo mã vùng

Tạo bảng `LIST` cho các mã vùng số 1–6, sau đó thử insert mã 7.

**Yêu cầu:** ghi nhận lỗi khi không có partition phù hợp và đề xuất quy trình thêm giá trị mới.

### Bài tập 4: LIST COLUMNS theo chuỗi

Tạo bảng phân vùng theo `region_code VARCHAR`, dùng các nhóm `NORTH`, `CENTRAL`, `SOUTH`.

**Yêu cầu:** thử truy vấn một mã vùng và kiểm tra partition pruning.

### Bài tập 5: HASH và KEY

Tạo hai bảng lab: một bảng `HASH(customer_id)`, một bảng `KEY(customer_id)`, mỗi bảng có tám partition.

**Yêu cầu:** so sánh cách khai báo partition key và giải thích điểm khác nhau giữa biểu thức HASH do người dùng chỉ định với hash nội bộ của KEY.

### Bài tập 6: Nhiều cột trong COLUMNS

Tạo bảng `RANGE COLUMNS(event_date, region_id)` hoặc `LIST COLUMNS(country_code, region_code)`.

**Yêu cầu:** kiểm tra cách MySQL so sánh tuple và xác định partition của một số giá trị biên.

### Bài tập 7: Unique key và partition key

Tạo bảng partition theo `order_date` nhưng chỉ khai báo `PRIMARY KEY(order_id)`.

**Yêu cầu:** quan sát lỗi, sửa primary key để bao gồm `order_date`, rồi giải thích tác động đến tính duy nhất toàn bảng.

### Bài tập 8: Partition pruning

Chạy cùng một truy vấn có và không có điều kiện trên partition key.

**Yêu cầu:** so sánh `partitions`, `key`, `rows` trong `EXPLAIN`; giải thích vì sao partitioning không thay thế index.

## 20. Checklist review partitioning

- [ ] Đã xác định vấn đề thực tế cần partitioning giải quyết.
- [ ] Partition key phù hợp với predicate truy vấn và vòng đời dữ liệu.
- [ ] Đã chọn đúng RANGE, RANGE COLUMNS, LIST, LIST COLUMNS, HASH hoặc KEY.
- [ ] Các khoảng RANGE liên tục, không chồng lấn và có xử lý giá trị tương lai.
- [ ] LIST bao phủ mọi giá trị hợp lệ có thể insert.
- [ ] Đã hiểu cách so sánh tuple khi dùng nhiều cột COLUMNS.
- [ ] Mọi unique key và primary key đều chứa partition key.
- [ ] Đã đánh giá ảnh hưởng của primary key ghép đến uniqueness nghiệp vụ.
- [ ] Đã kiểm tra giới hạn foreign key của InnoDB partitioned table.
- [ ] Index trong partition hỗ trợ truy vấn sau pruning.
- [ ] EXPLAIN cho thấy partition được truy cập như mong đợi.
- [ ] Đã có quy trình thêm, reorganize và loại bỏ partition.
- [ ] Đã kiểm tra backup/retention trước thao tác DROP PARTITION.
- [ ] Đã đo cả chi phí đọc, ghi và vận hành sau khi partition.

## 21. Ghi nhớ

`RANGE` chia theo khoảng giá trị, `LIST` chia theo danh sách giá trị, `HASH` phân phối theo biểu thức số nguyên và `KEY` dùng thuật toán hash nội bộ của MySQL. `RANGE COLUMNS` và `LIST COLUMNS` cho phép dùng trực tiếp một hoặc nhiều cột, bao gồm kiểu ngày và chuỗi trong phạm vi được hỗ trợ.

Partitioning có ích khi partition key khớp với điều kiện truy vấn hoặc quy trình quản lý vòng đời dữ liệu. Hãy kiểm tra partition pruning bằng `EXPLAIN`, thiết kế index phù hợp bên trong partition và nhớ rằng mọi unique key phải bao gồm các cột partition key. Với InnoDB, cần đặc biệt cân nhắc giới hạn foreign key và tính duy nhất toàn bảng trước khi partition một bảng nghiệp vụ.
