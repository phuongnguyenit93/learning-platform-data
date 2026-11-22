# Persistent statistics, lấy mẫu và tự động tính lại của InnoDB

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao MySQL cần thống kê dữ liệu để optimizer ước lượng số hàng và chọn execution plan.
- Phân biệt persistent statistics với non-persistent statistics của InnoDB.
- Xác định vai trò của `innodb_stats_persistent`, `innodb_stats_auto_recalc` và `innodb_stats_persistent_sample_pages`.
- Cấu hình thống kê ở cấp instance hoặc từng bảng bằng các tùy chọn `STATS_*`.
- Đọc dữ liệu thống kê trong `mysql.innodb_table_stats` và `mysql.innodb_index_stats`.
- Hiểu cách lấy mẫu page, cardinality và sự đánh đổi giữa độ chính xác với chi phí I/O.
- Chủ động cập nhật thống kê bằng `ANALYZE TABLE` sau khi nạp hoặc thay đổi dữ liệu lớn.
- Đánh giá việc tự động tính lại thống kê và xử lý trường hợp optimizer dùng ước lượng cũ.
- So sánh ước lượng với dữ liệu thực tế bằng `EXPLAIN` và `EXPLAIN ANALYZE`.

Các ví dụ hướng tới MySQL 8.0/8.4 với InnoDB. Giá trị mặc định và một số chi tiết có thể thay đổi theo phiên bản; hãy kiểm tra trên server mục tiêu trước khi áp dụng.

## 1. Vì sao optimizer cần statistics?

MySQL optimizer phải quyết định cách thực thi một câu SQL. Với một truy vấn JOIN nhiều bảng, nó cần ước lượng:

- Mỗi bảng có bao nhiêu hàng.
- Điều kiện `WHERE` sẽ giữ lại khoảng bao nhiêu hàng.
- Một giá trị trong index xuất hiện nhiều hay ít.
- Nên dùng index nào và nên đọc bảng theo thứ tự nào.
- Nên dùng nested-loop join hay một chiến lược thực thi khác phù hợp.
- Chi phí đọc index, đọc hàng và sắp xếp dự kiến là bao nhiêu.

Optimizer không thể đọc toàn bộ dữ liệu của mọi bảng chỉ để quyết định execution plan cho từng truy vấn. Nó dựa vào statistics (thống kê) để ước lượng cardinality và chi phí.

Ví dụ bảng `orders` có index trên `status`:

```sql
SELECT order_id, customer_id, created_at
FROM orders
WHERE status = 'PENDING';
```

Nếu optimizer ước lượng chỉ có 1% đơn hàng ở trạng thái `PENDING`, dùng index có thể hợp lý. Nếu thực tế có 90% hàng là `PENDING`, full table scan có thể rẻ hơn. Statistics sai lệch có thể khiến optimizer chọn kế hoạch không phù hợp.

### 1.1. Statistics là ước lượng, không phải kết quả truy vấn chính xác

Statistics của InnoDB được tạo từ việc lấy mẫu index page và ước lượng phân bố key. Các giá trị như số hàng của bảng hoặc cardinality của index không nhất thiết bằng số đếm chính xác tại thời điểm truy vấn.

Điều đó là chủ đích: statistics cần đủ tốt để hỗ trợ lựa chọn kế hoạch với chi phí thấp. Việc lấy mẫu giúp tránh phải quét toàn bộ index mỗi khi cần tính lại thống kê.

### 1.2. Statistics có thể ảnh hưởng trực tiếp đến execution plan

Giả sử một bảng có index `(status, created_at)`. Nếu optimizer đánh giá `status = 'PENDING'` rất chọn lọc, nó có thể dùng index để đọc một tập nhỏ. Nếu ước lượng sai và trạng thái này thực tế chiếm phần lớn bảng, kế hoạch đó có thể tốn nhiều lần truy cập index và clustered record hơn một lần quét tuần tự.

Statistics tốt không bảo đảm mọi kế hoạch đều tối ưu, nhưng statistics cũ hoặc kém chính xác làm optimizer khó đưa ra quyết định tốt.

## 2. Persistent statistics là gì?

Persistent optimizer statistics là thống kê index của InnoDB được lưu xuống đĩa, nhờ đó vẫn tồn tại sau khi MySQL restart. Trong MySQL 8.0/8.4, persistent statistics được bật mặc định bằng `innodb_stats_persistent=ON`.

Các bảng hệ thống lưu persistent statistics gồm:

- `mysql.innodb_table_stats`: thống kê ở cấp bảng.
- `mysql.innodb_index_stats`: thống kê ở cấp index và các prefix của index.

Nếu không lưu persistent statistics, InnoDB dùng non-persistent statistics trong bộ nhớ. Các thống kê này có thể bị mất khi server shutdown và được tính lại khi bảng được mở hoặc khi một số thao tác cần chúng. Vì quá trình lấy mẫu có thể tạo ước lượng khác nhau, execution plan có thể thay đổi sau restart.

### 2.1. Lợi ích của persistent statistics

- Statistics được giữ qua server restart.
- Giảm khả năng execution plan thay đổi chỉ vì server vừa khởi động lại và tính lại thống kê từ mẫu khác.
- Có thể xem thời điểm cập nhật qua `last_update`.
- Có thể cấu hình tự động tính lại khi dữ liệu thay đổi đáng kể.
- Có thể điều chỉnh số page lấy mẫu ở cấp instance hoặc bảng.
- Hỗ trợ điều tra nguyên nhân optimizer chọn index hoặc join order không phù hợp.

Persistent statistics cải thiện tính ổn định, nhưng không đóng băng execution plan. Kế hoạch vẫn có thể thay đổi khi statistics được cập nhật, dữ liệu thay đổi, index/schema thay đổi, optimizer setting hoặc phiên bản MySQL thay đổi.

### 2.2. Kiểm tra cấu hình persistent statistics

```sql
SHOW VARIABLES LIKE 'innodb_stats_persistent';
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
```

Trong MySQL 8.0/8.4, giá trị mặc định thường là:

| Biến | Giá trị mặc định | Ý nghĩa |
|---|---:|---|
| `innodb_stats_persistent` | `ON` | Lưu index statistics của InnoDB xuống đĩa |
| `innodb_stats_auto_recalc` | `ON` | Tự động tính lại persistent statistics khi bảng thay đổi đáng kể |
| `innodb_stats_persistent_sample_pages` | `20` | Số index page lấy mẫu khi tính persistent statistics |

Luôn kiểm tra giá trị thực tế bằng `SHOW VARIABLES`; cấu hình instance có thể đã được DBA thay đổi.

## 3. Cấu hình persistent statistics ở cấp instance

### 3.1. Bật hoặc tắt persistent statistics

`innodb_stats_persistent` là biến GLOBAL. Có thể thay đổi runtime:

```sql
SET GLOBAL innodb_stats_persistent = ON;
```

Biến này được lưu cùng từng bảng tại thời điểm bảng được tạo. Có thể ghi đè cho từng bảng bằng `STATS_PERSISTENT` trong `CREATE TABLE` hoặc `ALTER TABLE`.

Do đó, thay đổi GLOBAL không tự động chuyển tất cả bảng hiện có từ chế độ này sang chế độ kia. Nếu muốn thay đổi một bảng đã tồn tại, hãy dùng tùy chọn cấp bảng rồi tính lại statistics khi cần.

### 3.2. Bật tự động tính lại

```sql
SET GLOBAL innodb_stats_auto_recalc = ON;
```

Khi bật, InnoDB tự động tính lại persistent statistics nếu dữ liệu của bảng thay đổi đáng kể. Ngưỡng mặc định được mô tả là khoảng 10% số hàng của bảng đã thay đổi.

Việc tính lại diễn ra bất đồng bộ ở background. Vì vậy, sau khi một lệnh bulk UPDATE/DELETE/INSERT thay đổi hơn ngưỡng, statistics không nhất thiết được cập nhật ngay lập tức. Có thể có độ trễ vài giây hoặc lâu hơn tùy tải và trạng thái server.

Nếu cần statistics mới ngay để đánh giá hoặc chạy truy vấn quan trọng, hãy chủ động thực hiện:

```sql
ANALYZE TABLE orders;
```

### 3.3. Điều chỉnh số page lấy mẫu

```sql
SET GLOBAL innodb_stats_persistent_sample_pages = 64;
```

Tăng số page lấy mẫu có thể cải thiện độ chính xác của cardinality estimate, nhưng làm tăng I/O và thời gian tính statistics. Giảm số page có thể giúp `ANALYZE TABLE` nhanh hơn, nhưng ước lượng dễ nhiễu hơn.

Thay đổi GLOBAL áp dụng cho các bảng dùng giá trị mặc định ở cấp bảng khi statistics được tính lại. Với một bảng đặc biệt, nên cân nhắc `STATS_SAMPLE_PAGES` thay vì tăng chi phí cho mọi bảng.

### 3.4. Thay đổi biến không tự làm mới statistics

Sau khi đổi `innodb_stats_persistent_sample_pages`, không nên giả định statistics hiện có đã được lấy mẫu lại. Cần chạy `ANALYZE TABLE` trên các bảng cần áp dụng số page mới để tính lại thống kê.

Tương tự, bật `innodb_stats_persistent` không có nghĩa mọi bảng cũ lập tức có thống kê persistent mới. Kiểm tra tùy chọn của bảng và chủ động phân tích bảng khi cần.

## 4. Cấu hình riêng cho từng bảng bằng STATS_* options

InnoDB cho phép điều chỉnh persistent statistics theo từng bảng bằng các table option:

| Tùy chọn | Giá trị | Ý nghĩa |
|---|---|---|
| `STATS_PERSISTENT` | `DEFAULT`, `0`, `1` | Chọn persistent hoặc non-persistent statistics cho bảng |
| `STATS_AUTO_RECALC` | `DEFAULT`, `0`, `1` | Bật/tắt tự động tính lại persistent statistics của bảng |
| `STATS_SAMPLE_PAGES` | Số nguyên dương | Số index page lấy mẫu khi tính cardinality/statistics cho bảng |

### 4.1. Khai báo khi CREATE TABLE

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_status_created (status, created_at)
) ENGINE = InnoDB
  STATS_PERSISTENT = 1
  STATS_AUTO_RECALC = 1
  STATS_SAMPLE_PAGES = 64;
```

Trong ví dụ, bảng `orders` dùng persistent statistics, cho phép tự động tính lại khi dữ liệu thay đổi đáng kể và lấy mẫu 64 index page khi ước lượng thống kê.

### 4.2. Thay đổi tùy chọn của bảng hiện có

```sql
ALTER TABLE orders
    STATS_PERSISTENT = 1,
    STATS_AUTO_RECALC = 0,
    STATS_SAMPLE_PAGES = 64;
```

Ví dụ này giữ persistent statistics nhưng tắt tự động tính lại cho riêng bảng `orders`. DBA cần có quy trình chủ động chạy `ANALYZE TABLE` sau bulk load hoặc khi phân bố dữ liệu thay đổi đáng kể.

Thay đổi table option không thay thế bước tính lại statistics. Sau khi thay đổi số page lấy mẫu hoặc bật persistent statistics cho bảng, có thể chạy:

```sql
ANALYZE TABLE orders;
```

### 4.3. Ý nghĩa DEFAULT

`DEFAULT` cho phép bảng kế thừa giá trị cấu hình GLOBAL tương ứng:

```sql
ALTER TABLE orders
    STATS_PERSISTENT = DEFAULT,
    STATS_AUTO_RECALC = DEFAULT;
```

Điều này hữu ích khi muốn đưa bảng trở lại chính sách chung của instance. `STATS_SAMPLE_PAGES` có thể được đặt riêng để bảng quan trọng dùng mẫu lớn hơn, trong khi các bảng khác tiếp tục dùng giá trị global.

## 5. InnoDB lấy mẫu index page như thế nào?

InnoDB không cần quét mọi index record để ước lượng cardinality. Khi tính statistics, engine lấy mẫu các page của index và dùng phân bố key trong mẫu để ước lượng số giá trị khác nhau.

Phương pháp lấy mẫu này thường được mô tả là random dive: InnoDB đọc các page được chọn ngẫu nhiên trong index, quan sát key và ước lượng phân bố trên toàn bộ index.

### 5.1. Cardinality là gì?

Cardinality của index/prefix là ước lượng số giá trị khác nhau trong tập key đó. Ví dụ index trên `status` có thể có cardinality thấp nếu chỉ có các giá trị `NEW`, `PAID`, `CANCELLED`; index trên `order_id` có cardinality cao vì mỗi hàng có một ID khác nhau.

Cardinality giúp optimizer đánh giá độ chọn lọc. Một điều kiện trên index có nhiều giá trị khác nhau thường có khả năng lọc tập dữ liệu tốt hơn, nhưng độ chọn lọc thực tế còn phụ thuộc giá trị cụ thể và phân bố dữ liệu.

### 5.2. Số page lấy mẫu ảnh hưởng thế nào?

- Mẫu quá nhỏ: dễ bỏ sót vùng dữ liệu hiếm hoặc phân bố lệch, cardinality estimate dao động.
- Mẫu lớn hơn: có nhiều thông tin hơn để ước lượng, nhưng cần đọc thêm page và tăng thời gian `ANALYZE TABLE`.
- Index lớn hoặc phân bố không đồng đều: thường nhạy hơn với kích thước mẫu.
- Bảng có nhiều index và primary key rộng: chi phí tính statistics có thể tăng vì InnoDB phải phân tích nhiều cấu trúc index.

Không có con số mẫu tối ưu cho mọi bảng. Hãy điều chỉnh có kiểm soát và so sánh cả chất lượng execution plan lẫn thời gian phân tích.

### 5.3. innodb_stats_persistent_sample_pages

Biến này là GLOBAL, động và có giá trị mặc định 20 trong MySQL 8.0/8.4:

```sql
SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
```

Ví dụ tăng mẫu:

```sql
SET GLOBAL innodb_stats_persistent_sample_pages = 100;
ANALYZE TABLE orders;
```

Tăng mẫu lên 100 có thể làm estimate ổn định hơn, nhưng không phải lúc nào cũng tốt hơn. Nếu `ANALYZE TABLE` trở nên quá chậm, có thể giảm lại hoặc dùng giá trị riêng cho bảng bằng `STATS_SAMPLE_PAGES`.

### 5.4. STATS_SAMPLE_PAGES theo bảng

```sql
ALTER TABLE orders
    STATS_SAMPLE_PAGES = 100;

ANALYZE TABLE orders;
```

Đây là cách nhắm tới một bảng có index quan trọng hoặc phân bố khó ước lượng mà không làm tăng số page lấy mẫu cho tất cả bảng khác.

## 6. Persistent statistics được lưu ở đâu?

InnoDB lưu persistent statistics trong hai bảng hệ thống thuộc schema `mysql`.

### 6.1. mysql.innodb_table_stats

Bảng này lưu thống kê ở cấp bảng. Một số cột quan trọng:

| Cột | Ý nghĩa |
|---|---|
| `database_name` | Schema chứa bảng |
| `table_name` | Tên bảng |
| `last_update` | Thời điểm statistics được cập nhật |
| `n_rows` | Số hàng ước lượng của bảng |
| `clustered_index_size` | Số page của clustered index theo statistics |
| `sum_of_other_index_sizes` | Tổng số page ước lượng của các secondary index |

Đọc thống kê của một bảng:

```sql
SELECT
    database_name,
    table_name,
    last_update,
    n_rows,
    clustered_index_size,
    sum_of_other_index_sizes
FROM mysql.innodb_table_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders';
```

`n_rows` là ước lượng, không phải kết quả chính xác của `SELECT COUNT(*)`. Không dùng giá trị này cho nghiệp vụ cần đếm chính xác.

### 6.2. mysql.innodb_index_stats

Bảng này lưu thống kê cho từng index và prefix của index:

| Cột | Ý nghĩa |
|---|---|
| `database_name`, `table_name` | Xác định bảng |
| `index_name` | Tên index |
| `last_update` | Thời điểm cập nhật statistics |
| `stat_name` | Loại thống kê, ví dụ `n_diff_pfx01`, `n_leaf_pages`, `size` |
| `stat_value` | Giá trị ước lượng |
| `sample_size` | Số page được lấy mẫu cho ước lượng tương ứng, nếu có |
| `stat_description` | Mô tả prefix/cấu trúc được thống kê |

Xem thống kê index:

```sql
SELECT
    index_name,
    stat_name,
    stat_value,
    sample_size,
    stat_description,
    last_update
FROM mysql.innodb_index_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders'
ORDER BY index_name, stat_name;
```

### 6.3. Ý nghĩa các stat_name thường gặp

- `n_diff_pfx01`: ước lượng số giá trị khác nhau của prefix gồm cột index đầu tiên.
- `n_diff_pfx02`: ước lượng số giá trị khác nhau của prefix gồm hai cột index đầu tiên.
- `n_diff_pfxNN`: tiếp tục theo prefix gồm NN cột đầu tiên của index.
- `n_leaf_pages`: số leaf page được ước lượng cho index.
- `size`: tổng số page được ước lượng cho index.

Với index ghép `(customer_id, created_at)`, `n_diff_pfx01` phản ánh cardinality ước lượng của `customer_id`; `n_diff_pfx02` phản ánh số tổ hợp khác nhau của `(customer_id, created_at)`.

### 6.4. Không chỉnh trực tiếp bảng statistics như cách vận hành thông thường

Các bảng `mysql.innodb_table_stats` và `mysql.innodb_index_stats` là dữ liệu nội bộ của InnoDB. Việc sửa tay giá trị thống kê có thể khiến optimizer dùng ước lượng không phản ánh dữ liệu và gây khó khăn khi điều tra.

Trong vận hành bình thường, hãy dùng `ANALYZE TABLE`, table options và system variables được hỗ trợ. Nếu thử nghiệm thay đổi thống kê ở môi trường nghiên cứu, cần backup, ghi lại giá trị gốc và hiểu rõ cách InnoDB nạp/áp dụng chúng; không biến thao tác sửa trực tiếp thành quy trình production mặc định.

## 7. Automatic recalculation: tự động tính lại khi dữ liệu thay đổi

Persistent statistics có thể được InnoDB tự động tính lại khi bảng thay đổi đủ lớn. Biến điều khiển là `innodb_stats_auto_recalc`, mặc định ON trong MySQL 8.0/8.4.

### 7.1. Ngưỡng khoảng 10% số hàng

Khi lượng dữ liệu của bảng thay đổi đáng kể, thường được mô tả là hơn 10% số hàng, InnoDB đánh dấu statistics cần cập nhật và thực hiện tính lại ở background.

Ví dụ bảng có khoảng 1.000.000 hàng. Nếu số hàng thay đổi vượt ngưỡng theo dõi, InnoDB có thể kích hoạt automatic recalculation. Đây không phải cam kết rằng cứ đúng 100.000 thay đổi là việc phân tích hoàn tất ngay tại câu DML cuối cùng.

Ngưỡng 10% là cơ chế kích hoạt mặc định, không phải quy tắc nghiệp vụ và cũng không bảo đảm statistics phản ánh ngay mọi thay đổi phân bố.

### 7.2. Automatic recalculation là bất đồng bộ

Sau bulk load hoặc UPDATE lớn, có thể có một khoảng thời gian statistics chưa được tính lại. Trong thời gian đó, optimizer có thể tiếp tục dùng thống kê cũ.

Nếu cần đồng bộ trước khi chạy workload tiếp theo, hãy chạy:

```sql
ANALYZE TABLE orders;
```

`ANALYZE TABLE` khởi chạy việc tính lại ở foreground, nên client nhận kết quả sau khi thao tác hoàn tất hoặc thất bại. Với bảng lớn, lệnh này có thể tạo I/O và cần được đưa vào kế hoạch vận hành.

### 7.3. Tắt automatic recalculation cho một bảng

```sql
ALTER TABLE orders
    STATS_AUTO_RECALC = 0;
```

Khi tắt, DBA chịu trách nhiệm làm mới statistics sau những thay đổi đáng kể. Điều này có thể hữu ích nếu cần kiểm soát thời điểm cập nhật statistics để tránh thay đổi plan bất ngờ trong giờ cao điểm.

Nhưng nếu quên chạy `ANALYZE TABLE`, optimizer có thể dùng thống kê cũ trong thời gian dài. Chỉ tắt khi đã có lịch hoặc sự kiện vận hành rõ ràng để cập nhật.

### 7.4. Bật lại theo mặc định

```sql
ALTER TABLE orders
    STATS_AUTO_RECALC = DEFAULT;
```

Hoặc đặt rõ `1` nếu muốn bật cho bảng đó:

```sql
ALTER TABLE orders
    STATS_AUTO_RECALC = 1;
```

### 7.5. Thêm index hoặc thay đổi cột

Khi thêm index vào bảng hiện có, hoặc thêm/xóa cột, InnoDB tính toán và thêm index statistics vào `mysql.innodb_index_stats` bất kể `innodb_stats_auto_recalc` đang bật hay tắt. Tuy vậy, sau khi nạp lượng lớn dữ liệu vào bảng hoặc thay đổi mạnh phân bố key, vẫn nên đánh giá và chủ động `ANALYZE TABLE`.

## 8. ANALYZE TABLE: cập nhật statistics chủ động

`ANALYZE TABLE` yêu cầu storage engine phân tích bảng và cập nhật optimizer statistics. Với InnoDB persistent statistics, lệnh này tính lại các thống kê được lưu trong các bảng `mysql.innodb_*_stats`.

### 8.1. Cú pháp cơ bản

```sql
ANALYZE TABLE orders;
```

Có thể phân tích nhiều bảng:

```sql
ANALYZE TABLE orders, order_items, customers;
```

### 8.2. Khi nào nên chạy ANALYZE TABLE?

- Sau khi nạp lượng dữ liệu lớn bằng bulk load.
- Sau khi xóa hoặc cập nhật một tỷ lệ lớn dữ liệu.
- Sau khi phân bố giá trị của cột được index thay đổi mạnh.
- Khi `EXPLAIN` cho thấy estimated rows lệch đáng kể so với số hàng thực tế.
- Khi optimizer chọn index hoặc join order kém sau một đợt thay đổi dữ liệu.
- Sau khi thay đổi `STATS_SAMPLE_PAGES` và cần tính lại theo kích thước mẫu mới.
- Trong script chuẩn bị dữ liệu test/benchmark để bảo đảm statistics đã được tính.

### 8.3. ANALYZE TABLE không sửa dữ liệu nghiệp vụ

Lệnh này cập nhật metadata/statistics phục vụ optimizer; nó không thay đổi giá trị hàng như UPDATE hay DELETE. Tuy nhiên, nó vẫn đọc index page và có thể tạo tải I/O, nên không nên chạy lặp lại liên tục mà không có lý do.

### 8.4. Phân biệt ANALYZE TABLE với OPTIMIZE TABLE

| Lệnh | Mục đích |
|---|---|
| `ANALYZE TABLE` | Tính/cập nhật statistics để optimizer ước lượng tốt hơn |
| `OPTIMIZE TABLE` | Tổ chức lại/rebuild bảng InnoDB trong các trường hợp phù hợp, có thể thu hồi không gian và tái cấu trúc dữ liệu/index |

Nếu execution plan kém do statistics cũ, bắt đầu bằng `ANALYZE TABLE`. Không chạy `OPTIMIZE TABLE` chỉ để làm mới cardinality vì nó có chi phí DDL/rebuild lớn hơn nhiều.

## 9. Persistent và non-persistent statistics

Nếu persistent statistics bị tắt ở cấp instance hoặc một bảng đặt `STATS_PERSISTENT=0`, InnoDB dùng non-persistent statistics.

### 9.1. Non-persistent statistics hoạt động ra sao?

- Statistics được lưu trong bộ nhớ thay vì lưu bền vững trong các bảng `mysql.innodb_*_stats`.
- Chúng có thể mất khi server shutdown.
- InnoDB tính lại khi bảng được mở hoặc trong một số thao tác/điều kiện cập nhật.
- Ước lượng sau restart có thể khác lần trước do lấy mẫu khác nhau.

Điều này có thể làm execution plan thay đổi sau restart, kể cả khi dữ liệu nghiệp vụ không thay đổi đáng kể.

### 9.2. innodb_stats_transient_sample_pages

Khi bảng dùng non-persistent statistics, biến lấy mẫu liên quan là:

```sql
SHOW VARIABLES LIKE 'innodb_stats_transient_sample_pages';
```

Trong MySQL 8.0/8.4, giá trị mặc định là 8. Tăng số page có thể cải thiện ước lượng nhưng làm tăng I/O khi mở bảng hoặc tính lại statistics. Biến này chỉ áp dụng khi persistent statistics bị tắt cho bảng; nếu persistent bật, `innodb_stats_persistent_sample_pages` được sử dụng.

### 9.3. Không nhầm biến lấy mẫu

| Trạng thái bảng | Biến lấy mẫu |
|---|---|
| `STATS_PERSISTENT=1` hoặc persistent được bật theo DEFAULT | `innodb_stats_persistent_sample_pages` |
| `STATS_PERSISTENT=0` | `innodb_stats_transient_sample_pages` |

MySQL 8.0 đã loại bỏ biến cũ `innodb_stats_sample_pages`; hãy dùng biến persistent hoặc transient tương ứng thay vì cấu hình tên cũ.

## 10. Đọc statistics và kiểm tra chất lượng ước lượng

Statistics chỉ hữu ích khi được đối chiếu với hành vi truy vấn. Có thể kết hợp bảng thống kê, `EXPLAIN` và dữ liệu thực tế.

### 10.1. Kiểm tra thời điểm cập nhật

```sql
SELECT
    database_name,
    table_name,
    last_update,
    n_rows
FROM mysql.innodb_table_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders';
```

Nếu `last_update` quá cũ so với lần bulk load hoặc thay đổi dữ liệu lớn gần nhất, cần kiểm tra `STATS_AUTO_RECALC` và cân nhắc `ANALYZE TABLE`.

### 10.2. Kiểm tra cardinality của index

```sql
SELECT
    index_name,
    stat_name,
    stat_value,
    sample_size,
    last_update
FROM mysql.innodb_index_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders'
  AND stat_name LIKE 'n_diff_pfx%'
ORDER BY index_name, stat_name;
```

Với index ghép, các prefix statistics cho biết số giá trị khác nhau ước lượng ở từng độ dài prefix. Nếu prefix đầu có cardinality thấp, điều kiện chỉ lọc trên cột đầu có thể không chọn lọc tốt.

### 10.3. So sánh với số giá trị khác nhau thực tế

Để kiểm tra một index nhỏ hoặc bảng thử nghiệm, có thể đếm distinct:

```sql
SELECT
    COUNT(DISTINCT status) AS distinct_statuses
FROM orders;
```

Với index ghép `(customer_id, created_at)`, có thể kiểm tra:

```sql
SELECT COUNT(*) AS distinct_customer_created_pairs
FROM (
    SELECT customer_id, created_at
    FROM orders
    GROUP BY customer_id, created_at
) AS distinct_pairs;
```

Đây là phép quét/tổng hợp trên dữ liệu thật và có thể tốn kém ở bảng lớn. Chỉ chạy trong môi trường phù hợp hoặc trên tập dữ liệu đã giới hạn; không biến truy vấn kiểm chứng này thành monitoring định kỳ tốn kém.

### 10.4. Đối chiếu EXPLAIN

```sql
EXPLAIN
SELECT order_id, customer_id, created_at
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
```

Quan sát:

- `key`: index optimizer chọn.
- `rows`: số hàng ước lượng phải đọc.
- `filtered`: tỷ lệ phần trăm hàng còn lại sau điều kiện lọc mà optimizer ước lượng.
- `type`: access method như `range`, `ref` hoặc `ALL`.
- `possible_keys`: index optimizer xem là ứng viên.

Nếu `rows`/`filtered` ước lượng lệch nhiều so với thực tế, statistics có thể là một nguyên nhân. Cũng cần kiểm tra predicate, kiểu dữ liệu, collation, index design và histogram.

### 10.5. Dùng EXPLAIN ANALYZE để xem số hàng thực tế

MySQL 8.0.18 trở lên hỗ trợ `EXPLAIN ANALYZE` cho các câu SELECT phù hợp:

```sql
EXPLAIN ANALYZE
SELECT order_id, customer_id, created_at
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
```

`EXPLAIN ANALYZE` thực sự thực thi truy vấn và hiển thị số hàng cùng thời gian thực tế ở các iterator. So sánh actual rows với estimated rows giúp xác định mức độ sai lệch của optimizer.

Không chạy `EXPLAIN ANALYZE` một cách tùy tiện trên truy vấn nặng trong production vì nó tạo tải thực. Chọn thời điểm và phạm vi dữ liệu phù hợp.

## 11. Statistics, histogram và index design

Persistent index statistics và histogram có liên quan nhưng không phải cùng một cơ chế.

- Persistent InnoDB statistics chủ yếu cung cấp ước lượng cardinality và kích thước index dựa trên việc lấy mẫu index page.
- Histogram cung cấp thông tin phân bố giá trị của một cột, hữu ích khi optimizer cần ước lượng điều kiện lọc trên cột không được hỗ trợ tốt bởi index statistics.
- Index design quyết định các đường truy cập mà optimizer có thể chọn; statistics chỉ giúp ước lượng chi phí của những đường đó.

Ví dụ cập nhật histogram cho cột `status`:

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status WITH 32 BUCKETS;
```

Kiểm tra histogram:

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM information_schema.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
```

Histogram không thay thế `mysql.innodb_index_stats`; nó bổ sung thông tin phân bố ở cấp cột. Việc tạo histogram, số bucket và chính sách cập nhật cần được đánh giá theo workload. Một histogram không phù hợp hoặc cũ cũng có thể làm estimate lệch.

## 12. Quy trình sau bulk load hoặc thay đổi dữ liệu lớn

Một quy trình vận hành có thể gồm:

1. Nạp dữ liệu hoặc thực hiện batch DML.
2. Xác nhận dữ liệu đã hoàn tất và không còn batch đang thay đổi cùng bảng.
3. Kiểm tra cấu hình `STATS_PERSISTENT`, `STATS_AUTO_RECALC` và `STATS_SAMPLE_PAGES`.
4. Nếu cần statistics ngay, chạy `ANALYZE TABLE`.
5. Kiểm tra `last_update`, `n_rows` và các prefix cardinality trong `mysql.innodb_*_stats`.
6. Chạy `EXPLAIN` cho các truy vấn quan trọng.
7. Với truy vấn đại diện và môi trường phù hợp, chạy `EXPLAIN ANALYZE` để so sánh estimated rows với actual rows.
8. Nếu estimate vẫn sai, xem xét tăng sample pages cho đúng bảng, kiểm tra histogram, index và phân bố dữ liệu.
9. Ghi lại execution plan và latency để phát hiện thay đổi sau các lần cập nhật statistics tiếp theo.

Không nên chạy `ANALYZE TABLE` sau mọi câu INSERT/UPDATE nhỏ. Tần suất cần cân bằng giữa độ mới của statistics và chi phí I/O/CPU.

## 13. Ví dụ cấu hình theo từng loại bảng

### 13.1. Bảng OLTP thay đổi thường xuyên

```sql
ALTER TABLE orders
    STATS_PERSISTENT = 1,
    STATS_AUTO_RECALC = 1,
    STATS_SAMPLE_PAGES = 20;
```

Giữ persistent statistics và automatic recalculation. Giá trị sample 20 là mức mặc định phổ biến; theo dõi execution plan để xác định có cần tăng hay không.

### 13.2. Bảng lớn, index phân bố lệch

```sql
ALTER TABLE event_logs
    STATS_PERSISTENT = 1,
    STATS_AUTO_RECALC = 1,
    STATS_SAMPLE_PAGES = 100;

ANALYZE TABLE event_logs;
```

Mẫu lớn hơn có thể cải thiện estimate nhưng tăng thời gian phân tích. Chỉ giữ cấu hình nếu đo được lợi ích thực tế.

### 13.3. Bảng archive cập nhật theo batch có lịch

```sql
ALTER TABLE monthly_archive
    STATS_PERSISTENT = 1,
    STATS_AUTO_RECALC = 0,
    STATS_SAMPLE_PAGES = 64;
```

Sau mỗi batch archive hoàn tất, job vận hành chạy:

```sql
ANALYZE TABLE monthly_archive;
```

Với cách này, DBA chủ động thời điểm làm mới statistics. Cần giám sát để job không bị bỏ sót, nếu không optimizer có thể dùng ước lượng cũ.

### 13.4. Bảng nhỏ, workload đơn giản

Không cần tăng sample pages chỉ vì có thể. Với bảng nhỏ và index đơn giản, mặc định thường đủ. Tăng mẫu không tạo thêm giá trị nếu estimate hiện tại đã phù hợp và truy vấn không có vấn đề.

## 14. Những lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Execution plan đổi sau restart | Bảng dùng non-persistent statistics hoặc statistics được tính lại từ mẫu khác | Bật persistent statistics phù hợp và phân tích lại bảng |
| Bulk load xong optimizer vẫn chọn index cũ | Automatic recalculation chạy nền và chưa hoàn tất, hoặc bị tắt | Chạy `ANALYZE TABLE` khi cần cập nhật ngay |
| `ANALYZE TABLE` quá chậm | Sample pages quá lớn, nhiều index/partition hoặc bảng rất lớn | Giảm mẫu có kiểm soát, phân tích theo lịch, đánh giá cấu trúc index |
| Cardinality estimate thiếu chính xác | Mẫu quá nhỏ hoặc phân bố dữ liệu lệch | Tăng `STATS_SAMPLE_PAGES` cho bảng liên quan và chạy ANALYZE |
| Tăng sample pages nhưng plan không đổi | Statistics không phải nguyên nhân chính hoặc optimizer vẫn đánh giá index khác rẻ hơn | Kiểm tra actual rows, histogram, predicate và index design |
| Tắt auto recalc nhưng quên cập nhật thủ công | Statistics bị cũ sau batch DML | Tạo lịch/job ANALYZE và giám sát `last_update` |
| Nghĩ `n_rows` là COUNT chính xác | Đây là giá trị ước lượng | Dùng `COUNT(*)` khi cần số đếm chính xác |
| Nhầm persistent index stats với histogram | Hai nguồn statistics có mục đích và cách cập nhật khác nhau | Kiểm tra `innodb_index_stats` và `COLUMN_STATISTICS` riêng |
| Sửa trực tiếp bảng mysql.innodb_*_stats | Can thiệp dữ liệu nội bộ và làm sai estimate | Dùng `ANALYZE TABLE` và table options được hỗ trợ |

## 15. Checklist trước khi đưa vào production

- [ ] Đã kiểm tra `innodb_stats_persistent` và tùy chọn của từng bảng.
- [ ] Đã hiểu persistent statistics tồn tại qua restart nhưng không cố định execution plan.
- [ ] Đã kiểm tra `innodb_stats_auto_recalc` và chính sách cập nhật tự động.
- [ ] Đã biết automatic recalculation là bất đồng bộ và có ngưỡng thay đổi khoảng 10% số hàng.
- [ ] Đã có quy trình `ANALYZE TABLE` sau bulk load hoặc thay đổi phân bố dữ liệu đáng kể.
- [ ] Đã chọn `innodb_stats_persistent_sample_pages`/`STATS_SAMPLE_PAGES` theo độ chính xác và chi phí I/O.
- [ ] Đã phân biệt persistent sample pages với transient sample pages.
- [ ] Đã đọc `last_update`, `n_rows` và cardinality trong các bảng `mysql.innodb_*_stats`.
- [ ] Đã so sánh estimated rows với actual rows bằng công cụ phù hợp.
- [ ] Đã xem xét histogram riêng khi index statistics chưa mô tả đủ phân bố cột.
- [ ] Không dùng `n_rows` thay cho COUNT chính xác.
- [ ] Không sửa trực tiếp bảng thống kê nội bộ như quy trình vận hành thường ngày.
- [ ] Đã đánh giá tải I/O và thời gian khi chạy ANALYZE trên bảng lớn.

## 16. Kết luận

Persistent statistics giúp InnoDB lưu index statistics xuống đĩa để giữ ước lượng ổn định hơn qua server restart. `innodb_stats_persistent` điều khiển chế độ này; `innodb_stats_auto_recalc` cho phép tính lại ở background khi bảng thay đổi đáng kể; `innodb_stats_persistent_sample_pages` và `STATS_SAMPLE_PAGES` điều khiển số index page được lấy mẫu.

Statistics vẫn là ước lượng. Mẫu quá nhỏ có thể làm cardinality sai lệch, còn mẫu quá lớn khiến `ANALYZE TABLE` tốn I/O và thời gian. Automatic recalculation không cập nhật tức thì, vì vậy sau bulk load hoặc thay đổi phân bố lớn, hãy chủ động phân tích bảng nếu cần plan mới ngay. Đọc `mysql.innodb_table_stats` và `mysql.innodb_index_stats`, so sánh estimate với actual rows và điều chỉnh theo từng bảng giúp optimizer có thông tin tốt hơn mà không tạo chi phí thống kê không cần thiết.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: Configuring Persistent Optimizer Statistics Parameters](https://dev.mysql.com/doc/refman/8.4/en/innodb-persistent-stats.html)
- [MySQL 8.4 Reference Manual: Configuring Optimizer Statistics for InnoDB](https://dev.mysql.com/doc/refman/8.4/en/innodb-performance-optimizer-statistics.html)
- [MySQL 8.4 Reference Manual: InnoDB Startup Options and System Variables](https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html)
- [MySQL 8.4 Reference Manual: CREATE TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/create-table.html)
