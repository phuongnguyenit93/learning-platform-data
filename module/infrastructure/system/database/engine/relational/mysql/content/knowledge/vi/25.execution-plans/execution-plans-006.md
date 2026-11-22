# rows, filtered và lượng dữ liệu ước tính sau lọc

Khi đọc `EXPLAIN` của MySQL, hai cột `rows` và `filtered` giúp trả lời hai câu hỏi khác nhau: MySQL dự đoán phải đọc bao nhiêu hàng từ một bước truy cập bảng, và dự đoán bao nhiêu phần trăm trong số đó còn thỏa điều kiện lọc tại bước này. Kết hợp hai con số, ta ước tính được lượng hàng được chuyển sang bước tiếp theo của kế hoạch.

Đây là các ước lượng của optimizer, không phải số hàng thực tế đã đọc hoặc trả về. Nếu ước lượng sai nhiều, MySQL có thể chọn sai thứ tự JOIN, sai index hoặc sai phương thức truy cập. Vì vậy, cần hiểu cách đọc `rows` và `filtered`, cách chúng ảnh hưởng đến cardinality của JOIN, và cách so sánh với số liệu thực tế bằng `EXPLAIN ANALYZE`.

## 1. `rows` và `filtered` trả lời hai câu hỏi khác nhau

Trong output dạng bảng của `EXPLAIN`, các cột liên quan thường gồm:

| Cột | Ý nghĩa |
|---|---|
| `type` | Kiểu truy cập bảng/index, ví dụ `const`, `eq_ref`, `ref`, `range`, `index`, `ALL` |
| `key` | Index optimizer chọn |
| `rows` | Số hàng MySQL ước tính cần đọc/kiểm tra trong lần truy cập bảng |
| `filtered` | Tỷ lệ phần trăm hàng ước tính vượt qua điều kiện lọc gắn với bước truy cập bảng |
| `Extra` | Thông tin bổ sung về lọc, sort, covering index, ICP và các thao tác khác |

`rows` mô tả lượng dữ liệu mà access method dự kiến phải xem xét. Với `ALL`, nó thường gần với số hàng ước tính của toàn bảng. Với `range` hoặc `ref`, nó có thể chỉ là số hàng ước tính trong phạm vi index hoặc lần lookup tương ứng.

`filtered` là phần trăm hàng từ bước truy cập đó mà optimizer dự đoán sẽ còn lại sau điều kiện lọc liên quan. Ví dụ `filtered = 25` nghĩa là ước tính 25% còn lại và khoảng 75% bị loại bởi bộ lọc ở bước này. Nó không phải phần trăm tổng số hàng của database, cũng không phải tỷ lệ cache hit hay phần trăm CPU.

Ví dụ:

| `rows` | `filtered` | Hàng ước tính sau lọc |
|---:|---:|---:|
| 10.000 | 10% | 1.000 |
| 2.000 | 50% | 1.000 |
| 500 | 100% | 500 |
| 100.000 | 0,1% | 100 |

Ước lượng cơ bản:

```text
estimated_rows_after_filter
    = rows * filtered / 100
```

Ví dụ `rows = 10.000`, `filtered = 10`:

```text
10.000 * 10 / 100 = 1.000 hàng
```

Optimizer dự đoán bước truy cập xem xét khoảng 10.000 hàng và khoảng 1.000 hàng vượt qua bộ lọc để được chuyển tiếp.

## 2. `rows` không nhất thiết là tổng số hàng của bảng

Một hiểu lầm phổ biến là nhìn `rows = 500` rồi kết luận bảng chỉ có 500 hàng. Con số này là ước lượng gắn với access method của table trong kế hoạch hiện tại.

Ví dụ bảng `orders` có 5 triệu hàng:

```sql
SELECT id, total_amount
FROM orders
WHERE customer_id = 120;
```

Nếu optimizer chọn index `idx_orders_customer_id`, `rows` có thể là ước lượng số hàng có `customer_id = 120`, chẳng hạn 35. Nó không phải số hàng toàn bảng.

Nếu truy vấn không có điều kiện dùng index và optimizer chọn full table scan, `rows` có thể gần với tổng số hàng ước tính của bảng:

```sql
SELECT *
FROM orders;
```

Trong trường hợp này `rows` ở kế hoạch có thể gần 5 triệu, tùy thống kê. Con số vẫn là ước lượng; `EXPLAIN` không thực thi truy vấn chỉ để đếm chính xác toàn bộ dữ liệu.

### 2.1. Ý nghĩa phụ thuộc access type

| Access type | Cách hiểu `rows` khái quát |
|---|---|
| `const`, `system` | Tối đa một hàng được đọc trong kiểu truy cập đặc biệt này |
| `eq_ref` | Thường tối đa một hàng khớp cho mỗi tổ hợp hàng từ các bảng trước |
| `ref` | Số hàng ước tính khớp với giá trị khóa cho một lần lookup |
| `range` | Số hàng ước tính nằm trong phạm vi index |
| `index` | Số entry/hàng ước tính phải duyệt khi quét index |
| `ALL` | Số hàng ước tính phải quét khi full table scan |

Đây là mô tả khái quát. Cần đọc cùng `key`, `key_len`, `ref`, `Extra`, điều kiện truy cập và cấu trúc JOIN. Đặc biệt với bảng ở phía trong của nested-loop join, access có thể được thực hiện nhiều lần.

## 3. `filtered` là tỷ lệ vượt qua bộ lọc

Giả sử MySQL truy cập được 20.000 hàng qua index, sau đó còn điều kiện:

```sql
WHERE status = 'PAID'
  AND total_amount > 1000000
```

Optimizer dự đoán 25% hàng truy cập được thỏa các điều kiện lọc. `filtered = 25` có nghĩa khoảng một phần tư số hàng trong ước lượng access còn lại:

```text
20.000 * 25 / 100 = 5.000 hàng
```

`filtered = 100` không có nghĩa toàn bộ bảng được trả về. Nó có nghĩa optimizer dự đoán 100% hàng trong tập mà bước truy cập xem xét vượt qua phần lọc được tính ở đây. Nếu `rows = 10`, kết quả ước tính sau lọc vẫn chỉ là 10.

Ngược lại, `filtered = 1` không nhất thiết có nghĩa truy vấn rất nhanh. Nếu `rows = 10.000.000`, vẫn có thể phải xem xét lượng lớn hàng để giữ lại khoảng 100.000 hàng.

## 4. Đọc `rows` và `filtered` cùng nhau

Không đánh giá riêng một cột. Hai truy vấn có thể có `filtered` rất khác nhau nhưng chi phí cũng khác nhau:

| Truy vấn | `rows` | `filtered` | Hàng sau lọc ước tính |
|---|---:|---:|---:|
| A | 100 | 100% | 100 |
| B | 100.000 | 0,1% | 100 |

Cả hai dự đoán cùng chuyển 100 hàng sang bước sau, nhưng B phải xem xét nhiều hàng hơn để đạt kết quả đó. Nếu B thường xuyên chạy và điều kiện lọc có thể được hỗ trợ tốt hơn bằng index, có thể cần tối ưu access path.

Một tình huống khác:

| Truy vấn | `rows` | `filtered` | Hàng sau lọc ước tính |
|---|---:|---:|---:|
| C | 10.000 | 80% | 8.000 |
| D | 1.000.000 | 1% | 10.000 |

D chỉ giữ 1% nhưng vẫn tạo ra khoảng 10.000 hàng sau lọc và phải xem xét một triệu hàng. Tỷ lệ lọc thấp không tự động là tốt; phải xét lượng dữ liệu đầu vào, lượng đầu ra và số lần bước truy cập được thực hiện.

## 5. Ví dụ thực tế với bảng customers

Tạo bảng:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    region_code CHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_customers_region (region_code)
) ENGINE=InnoDB;
```

Truy vấn:

```sql
EXPLAIN
SELECT id, full_name
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE';
```

Giả sử output minh họa:

| table | type | key | rows | filtered | Extra |
|---|---|---|---:|---:|---|
| customers | ref | idx_customers_region | 40.000 | 25,00 | Using where |

Optimizer dự đoán:

- Khoảng 40.000 hàng được truy cập qua index theo `region_code`.
- Khoảng 25% vượt qua điều kiện còn lại `status = 'ACTIVE'`.
- Khoảng 10.000 hàng được chuyển tiếp.

Đây chỉ là output giả định để minh họa cách tính, không phải kết quả cố định của schema trên. Nếu sau đó tạo thêm index ghép `(region_code, status)`, optimizer có thể chọn index đó và tạo ra số hàng ước tính cùng `filtered` khác.

Chạy lại `EXPLAIN` sau khi thêm hoặc thay đổi index có thể cho thấy access path và ước lượng mới. Không nên suy ra index ghép luôn tốt hơn chỉ từ số `rows`; cần xét chi phí ghi, kích thước index và workload thực tế.

## 6. `rows` và `filtered` trong JOIN

Với JOIN, mỗi dòng trong `EXPLAIN` mô tả một bước truy cập bảng theo thứ tự optimizer chọn. Trong nested-loop join, bảng phía trong thường được truy cập một lần cho mỗi hàng đầu vào từ các bảng phía ngoài.

Ví dụ:

```sql
SELECT
    c.id,
    o.id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID';
```

Giả sử kế hoạch ước lượng:

| table | access | rows | filtered | Sau lọc mỗi lần truy cập |
|---|---|---:|---:|---:|
| c | `ref` | 10.000 | 50% | 5.000 |
| o | `ref` | 4 | 25% | 1 |

Diễn giải:

1. Bước `customers` ước tính truy cập 10.000 hàng và giữ lại khoảng 5.000 khách hàng.
2. Với mỗi khách hàng được chuyển tiếp, bước `orders` ước tính lookup khoảng 4 hàng.
3. Trong 4 hàng đó, khoảng 25% có trạng thái PAID, tương đương trung bình 1 đơn hàng phù hợp cho mỗi khách hàng.
4. Ước lượng đầu ra cuối cùng xấp xỉ 5.000 hàng, nếu các giả định độc lập và ước lượng trên phù hợp.

Số 4 ở dòng `orders` thường là ước lượng cho một lần truy cập/lookup, không có nghĩa toàn bộ JOIN chỉ đọc 4 đơn hàng. Nếu lookup được lặp cho 5.000 hàng khách hàng, tổng số hàng mà bước trong có thể xem xét lớn hơn nhiều.

Trong thực tế, optimizer có mô hình cardinality và cost phức tạp hơn phép nhân đơn giản. Ví dụ này giúp hiểu ý nghĩa per-scan; không dùng nó thay cho việc đọc toàn bộ kế hoạch.

### 6.1. Vì sao thứ tự JOIN quan trọng?

Nếu bước đầu tạo ra 500.000 hàng thay vì 5.000 hàng, một lookup phía trong dù chỉ xem xét 4 hàng mỗi lần cũng có thể bị lặp nhiều hơn rất nhiều.

Ví dụ:

```text
5.000 outer rows * 4 inner rows per lookup
    = 20.000 inner rows examined (ước lượng đơn giản)

500.000 outer rows * 4 inner rows per lookup
    = 2.000.000 inner rows examined (ước lượng đơn giản)
```

Do đó, sai lệch ở bước đầu có thể lan truyền và làm thay đổi chi phí các bước sau. Khi đọc kế hoạch JOIN, theo dõi lượng hàng được chuyển từ từng bảng sang bảng tiếp theo, không chỉ tìm dòng có `rows` lớn nhất.

### 6.2. Nested loop và số lần lặp

Trong nested-loop join, bảng trong có thể được truy cập nhiều lần. Cột `rows` trong EXPLAIN truyền thống không phải tổng số hàng đã xử lý trên mọi vòng lặp. Cần kết hợp vị trí của bảng trong join order và, nếu cần số thực tế, dùng `EXPLAIN ANALYZE` để xem `loops`.

Nếu `rows = 4` và bước được lặp 5.000 lần, có thể hình dung lượng hàng được xem xét xấp xỉ 20.000 theo ước lượng đơn giản. Số thực tế phụ thuộc cách thực thi, điều kiện, caching và loại join.

## 7. Cardinality và selectivity liên quan thế nào?

Optimizer cần ước tính số hàng thỏa điều kiện để chọn kế hoạch. Hai khái niệm hữu ích:

- **Cardinality:** số giá trị phân biệt hoặc số lượng tổ hợp giá trị mà thống kê mô tả, tùy ngữ cảnh index/statistics.
- **Selectivity:** tỷ lệ hàng thỏa một điều kiện so với tập hàng đầu vào.

Ví dụ bảng có 1.000.000 khách hàng, trong đó 100.000 khách ở VN:

```text
selectivity(region_code = 'VN')
    = 100.000 / 1.000.000
    = 10%
```

Nếu thống kê phản ánh đúng phân bố, optimizer có thể ước tính predicate này giữ lại khoảng 10% hàng khi áp dụng trên toàn bảng.

Cardinality của index và thống kê cột là một phần đầu vào cho ước lượng. Tuy nhiên, phân bố lệch, tương quan giữa các cột và điều kiện phức tạp có thể khiến ước lượng không chính xác.

## 8. Ước lượng nhiều predicate có thể sai

Giả sử bảng `customers` có:

- 10% hàng thuộc `region_code = 'VN'`.
- 50% hàng có `status = 'ACTIVE'`.

Nếu optimizer giả định hai điều kiện độc lập, nó có thể ước lượng:

```text
10% * 50% = 5%
```

Nhưng nếu gần như mọi khách hàng VN đều ACTIVE, tỷ lệ thực có thể gần 10%. Nếu chỉ 10% khách hàng VN ACTIVE, tỷ lệ thực có thể gần 1%.

Đây là vấn đề tương quan giữa các cột. Thống kê đơn cột không phải lúc nào cũng mô tả đầy đủ quan hệ giữa nhiều predicate. Histograms giúp mô tả phân bố của một cột; chúng không tự động giải quyết mọi tương quan đa cột.

Khi `filtered` sai nhiều, kiểm tra:

- Thống kê index/cột có cũ không?
- Dữ liệu có phân bố lệch (skew) không?
- Các cột lọc có tương quan không?
- Predicate có dùng biểu thức, hàm hoặc chuyển đổi kiểu không?
- Tham số truy vấn có phân bố rất khác nhau không?
- Có điều kiện phụ thuộc bảng khác trong JOIN không?

## 9. Phân biệt rows ước tính với số hàng thực tế

`EXPLAIN` thông thường không chạy truy vấn. `rows` và `filtered` là ước lượng do optimizer đưa ra dựa trên thống kê và mô hình chi phí.

Để xem thực tế, MySQL 8.0.18 trở lên hỗ trợ `EXPLAIN ANALYZE` cho câu truy vấn SELECT:

```sql
EXPLAIN ANALYZE
SELECT id, full_name
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE';
```

Output dạng TREE có thể có thông tin như:

```text
-> Index lookup on customers using idx_customers_region (region_code='VN')
   (cost=... rows=40000)
   (actual time=... rows=10000 loops=1)
```

Các giá trị trên chỉ là ví dụ minh họa:

- `cost` và `rows` là ước lượng của optimizer.
- `actual time` là thời gian thực tế của iterator.
- `actual rows` là số hàng thực tế trung bình trả ra mỗi lần iterator chạy.
- `loops` là số lần iterator được thực thi.

Trong ví dụ, iterator trả 10.000 hàng thực tế với một lần chạy, trong khi ước lượng là 40.000. Điều này gợi ý cardinality estimate đang cao hơn thực tế khoảng bốn lần.

### 9.1. Tính tổng hàng qua loops

Với iterator có `actual rows = 3` và `loops = 1.000`, số hàng trung bình mỗi loop là 3; tổng số hàng qua tất cả loop có thể xấp xỉ:

```text
3 * 1.000 = 3.000 hàng
```

Đừng so sánh `rows` ở EXPLAIN truyền thống với tổng actual rows qua mọi loops mà không quy về cùng đơn vị. So sánh per-scan với per-loop, hoặc quy đổi cả hai về tổng số hàng của toàn iterator.

### 9.2. EXPLAIN ANALYZE có thực thi truy vấn

`EXPLAIN ANALYZE` chạy câu lệnh SELECT để thu thập số liệu thực tế. Không dùng tùy tiện cho truy vấn rất nặng trên production vì bản thân phép đo có thể tiêu thụ CPU, I/O và thời gian. Nó cũng không phải công cụ thay thế benchmark workload đồng thời.

## 10. Đánh giá mức sai lệch estimate/actual

Một cách đơn giản là tính tỷ lệ:

```text
estimate_ratio = estimated_rows / actual_rows
```

Ví dụ:

| Ước lượng | Thực tế | Nhận xét |
|---:|---:|---|
| 10.000 | 9.500 | Khá sát |
| 100.000 | 10.000 | Ước lượng cao hơn 10 lần |
| 1.000 | 50.000 | Ước lượng thấp hơn 50 lần |
| 0 hoặc gần 0 | Có nhiều hàng thực tế | Cần kiểm tra thống kê và predicate đặc biệt |

Không có một ngưỡng cố định áp dụng cho mọi query. Sai lệch 10 lần ở một bước chỉ trả 1 hàng có thể không đáng kể; sai lệch 10 lần ở outer table của nested-loop join có thể làm số lần lookup phía trong tăng rất lớn.

Ưu tiên điều tra các sai lệch:

- Ở bảng ngoài của nested-loop join.
- Khi số hàng ước tính nhỏ nhưng thực tế rất lớn.
- Khi access path được chọn dựa trên selectivity sai.
- Khi query chạy thường xuyên và chiếm nhiều tài nguyên.

## 11. Dùng EXPLAIN FORMAT=JSON để xem cardinality

JSON cung cấp thêm chi tiết về ước lượng:

```sql
EXPLAIN FORMAT=JSON
SELECT
    c.id,
    o.id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID';
```

Các thuộc tính thường hữu ích:

| Thuộc tính | Ý nghĩa khái quát |
|---|---|
| `rows_examined_per_scan` | Số hàng ước tính được xem xét mỗi lần truy cập bảng |
| `rows_produced_per_join` | Số hàng ước tính được tạo ra sau bước join tương ứng |
| `filtered` | Tỷ lệ phần trăm ước tính còn lại sau lọc |
| `access_type` | Phương thức truy cập bảng |
| `key` | Index được chọn |
| `used_key_parts` | Các phần key được sử dụng |
| `attached_condition` | Điều kiện được gắn vào bước truy cập/đánh giá |
| `cost_info` | Thông tin chi phí ước lượng |

Tên trường và cách lồng JSON phụ thuộc loại kế hoạch và phiên bản. Đọc cấu trúc đầy đủ thay vì tìm một trường cố định ở mọi query.

`rows_examined_per_scan` giúp hiểu số hàng cho một lần scan; `rows_produced_per_join` thể hiện ước lượng đầu ra tích lũy sau bước join. Hai trường này không cùng đơn vị và không nên so sánh trực tiếp.

## 12. Khi rows lớn nhưng filtered nhỏ

Ví dụ:

| `rows` | `filtered` | Sau lọc |
|---:|---:|---:|
| 1.000.000 | 0,01% | 100 |

Optimizer dự đoán phải xem xét một triệu hàng để giữ lại khoảng 100. Đây có thể là dấu hiệu cần cải thiện access path.

Các hướng xem xét:

1. Có thể thêm composite index để predicate chọn lọc hơn tham gia vào range access không?
2. Thứ tự cột index có phù hợp với điều kiện equality/range không?
3. Có thể dùng index khác để giảm số entry phải duyệt không?
4. Thống kê có phản ánh phân bố dữ liệu hiện tại không?
5. Có thể tránh hàm hoặc implicit conversion trên cột lọc không?
6. Có thể giảm số hàng đầu vào trước khi JOIN không?

Tuy nhiên, không phải mọi `filtered` nhỏ đều cần index mới. Nếu truy vấn phải đọc phần lớn dữ liệu để trả về kết quả lớn hoặc tính toán tổng hợp, full scan có thể là kế hoạch hợp lý.

## 13. Khi rows nhỏ nhưng filtered thấp

Ví dụ:

| `rows` | `filtered` | Sau lọc |
|---:|---:|---:|
| 20 | 5% | 1 |

Optimizer dự đoán truy cập 20 hàng và giữ lại khoảng 1. Đây có thể là access path rất tốt dù `filtered` chỉ 5%.

Không nên cố làm `filtered` tăng lên 100% bằng cách thêm index bao phủ mọi cột nếu lượng hàng cần xem xét đã nhỏ. Index bổ sung có chi phí ghi, lưu trữ và bảo trì; tối ưu phải dựa trên tổng chi phí.

## 14. `filtered` và `Using where`

`Using where` trong cột `Extra` cho biết có điều kiện WHERE được áp dụng để lọc hàng. `filtered` là ước lượng tỷ lệ hàng còn lại sau bộ lọc được optimizer tính cho bước truy cập.

Hai thông tin có liên quan nhưng không đồng nhất:

- `Using where` là mô tả cách thực thi trong kế hoạch.
- `filtered` là tỷ lệ ước lượng.
- Có `Using where` không có nghĩa `filtered` chắc chắn thấp.
- `filtered = 100` không có nghĩa không có mệnh đề WHERE; điều kiện có thể đã được dùng để định vị access range hoặc optimizer ước tính tất cả hàng của tập truy cập đều vượt qua.

Nếu truy vấn có ICP, một phần điều kiện được kiểm tra trong storage engine. Đọc `Extra` như `Using index condition` cùng `Using where` và các trường JSON để xác định phần lọc nào được thực hiện ở đâu. Không giả định `filtered` là số đo trực tiếp số lần đọc full row đã tránh được nhờ ICP.

## 15. Thống kê ảnh hưởng đến rows và filtered

Optimizer dùng thống kê để ước lượng cardinality và selectivity. Với InnoDB, thống kê index được lưu và có thể được lấy mẫu; kết quả có thể thay đổi sau khi dữ liệu biến động hoặc thống kê được cập nhật.

Một số lệnh thường dùng:

```sql
SHOW INDEX FROM customers;
```

```sql
ANALYZE TABLE customers;
```

`SHOW INDEX` hiển thị thông tin index như `Cardinality` ước tính. `ANALYZE TABLE` yêu cầu MySQL cập nhật thống kê cho bảng. Trên InnoDB, thống kê có yếu tố lấy mẫu nên cardinality vẫn là ước lượng, không phải số đếm chính xác tuyệt đối.

Với phân bố dữ liệu lệch, histogram có thể giúp optimizer ước lượng predicate trên một cột tốt hơn:

```sql
ANALYZE TABLE customers
UPDATE HISTOGRAM ON region_code, status
WITH 100 BUCKETS;
```

Histogram mô tả phân bố của từng cột được chọn. Nó có thể cải thiện ước lượng cho điều kiện đơn cột, nhưng không tự mô hình hóa mọi tương quan giữa `region_code` và `status`.

Không chạy ANALYZE TABLE hoặc tạo histogram trên production chỉ để thử mà chưa đánh giá tác động, quyền cần thiết và hành vi workload. Sau khi cập nhật thống kê, so sánh kế hoạch và hiệu năng thực tế.

## 16. Các nguyên nhân khiến estimate sai

| Nguyên nhân | Tác động có thể thấy | Hướng điều tra |
|---|---|---|
| Thống kê cũ | `rows`/`filtered` không còn khớp dữ liệu | Kiểm tra thời điểm ANALYZE, cân nhắc cập nhật statistics |
| Data skew | Giá trị phổ biến và hiếm bị ước lượng gần giống nhau | Xem histogram và phân bố thực tế |
| Tương quan giữa cột | Tích selectivity đơn cột sai | Kiểm tra phân bố kết hợp, không chỉ từng cột |
| Predicate dùng function | Khó ước lượng hoặc không dùng index hiệu quả | Xem biểu thức, generated column/index phù hợp nếu có lý do |
| Implicit conversion/collation | Kế hoạch truy cập và selectivity khác kỳ vọng | Kiểm tra kiểu dữ liệu, charset/collation và EXPLAIN |
| Tham số có phân bố lệch | Một plan không phù hợp mọi giá trị | Đo nhiều giá trị đại diện |
| Join fan-out | Ước lượng hàng sau join sai lớn | Kiểm tra uniqueness, FK, index và cardinality quan hệ |
| Bảng tạm/derived table | Ước lượng phụ thuộc materialization và biến đổi query | Đọc JSON/TREE plan và actual rows |

## 17. Quy trình phân tích rows và filtered

Khi một query chậm:

1. Chạy `EXPLAIN` để lấy access type, key, rows, filtered và Extra.
2. Với từng bảng, xác định `rows` là per-scan estimate hay access path nào.
3. Tính `rows * filtered / 100` để ước lượng hàng qua bộ lọc ở bước đó.
4. Với JOIN, xem bảng ngoài và số lần bảng trong được truy cập.
5. Dùng `EXPLAIN FORMAT=JSON` để xem rows examined per scan và rows produced per join.
6. Dùng `EXPLAIN ANALYZE` để lấy actual rows, loops và timing.
7. So sánh estimate với actual theo cùng đơn vị.
8. Nếu sai lệch lớn, kiểm tra statistics, skew, correlation, predicate và join fan-out.
9. Chỉ thay index hoặc query sau khi hiểu bước nào tạo ra lượng dữ liệu lớn.
10. Chạy lại EXPLAIN/ANALYZE trên tham số đại diện để xác nhận cải thiện.

## 18. Ví dụ phân tích một JOIN có ước lượng sai

Truy vấn:

```sql
SELECT
    c.id,
    o.id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01';
```

Giả sử `EXPLAIN` ước lượng:

| table | rows | filtered | Sau lọc ước tính |
|---|---:|---:|---:|
| c | 50.000 | 20% | 10.000 |
| o | 8 | 50% | 4 mỗi lần lookup |

Nếu actual của `customers` chỉ có 500 hàng, optimizer đã ước lượng cao hơn 20 lần. Nếu bảng `orders` được lookup 500 lần thay vì 10.000 lần, tổng số lần truy cập phía trong có thể thấp hơn nhiều so với dự đoán.

Nếu actual của `customers` là 200.000 hàng, optimizer lại ước lượng thấp hơn rất nhiều và bước lookup `orders` có thể chạy nhiều lần hơn dự kiến.

Hãy kiểm tra thống kê `region_code` và `status`, nhất là khi hai cột tương quan. Nếu cần, đánh giá histogram cho từng cột, index ghép `(region_code, status)` và kế hoạch JOIN mới. Sau đó đo lại actual rows/loops; không kết luận chỉ từ việc `rows` giảm trong EXPLAIN.

## 19. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| `rows` là số hàng chắc chắn được trả về | Đây là ước lượng số hàng cần xem xét theo access path |
| `rows` luôn bằng tổng số hàng trong bảng | Nó phụ thuộc access type và điều kiện truy cập |
| `filtered = 10` nghĩa là chỉ đọc 10 hàng | Nghĩa là ước tính 10% hàng truy cập được vượt qua bộ lọc |
| `filtered = 100` nghĩa là không có WHERE | Điều kiện có thể đã được dùng trong access path hoặc toàn bộ tập truy cập được ước tính vượt qua |
| `rows * filtered` là số hàng thực tế | Đây là ước lượng, không phải actual row count |
| `rows` của bảng JOIN phía trong là tổng toàn JOIN | Nó thường là ước lượng cho một lần scan/lookup, có thể lặp nhiều lần |
| `filtered` càng thấp càng tốt | Phải xét cả số hàng đầu vào và số hàng còn lại |
| `rows` nhỏ luôn đồng nghĩa query nhanh | Còn phụ thuộc loops, row width, I/O, sort, lock và các iterator khác |
| `EXPLAIN ANALYZE` chỉ hiển thị ước lượng | Nó thực thi SELECT và hiển thị số liệu thực tế cùng ước lượng |
| ANALYZE TABLE tạo thống kê chính xác tuyệt đối | Thống kê InnoDB vẫn có thể dựa trên sampling và là ước lượng |

## 20. Checklist đọc rows và filtered

- `rows` đang mô tả access path nào và số hàng mỗi lần truy cập là bao nhiêu?
- Access type là `range`, `ref`, `eq_ref`, `index` hay `ALL`?
- `filtered` là tỷ lệ phần trăm nào còn lại sau lọc?
- `rows * filtered / 100` cho ra bao nhiêu hàng ước tính?
- Bảng có nằm phía trong nested-loop join và bị lặp nhiều lần không?
- Hàng được chuyển tiếp từ bảng ngoài có quá lớn không?
- Estimate có lệch đáng kể so với actual rows/loops không?
- Thống kê index/cột có cũ hoặc thiếu không?
- Dữ liệu có skew hoặc tương quan giữa các cột không?
- Predicate có function, implicit conversion hoặc điều kiện khó ước lượng không?
- Index có thể giảm số hàng phải xem xét thay vì chỉ lọc sau khi đọc không?
- Đã đo lại bằng `EXPLAIN ANALYZE` trên tham số đại diện chưa?

## Kết luận

Trong `EXPLAIN`, `rows` là số hàng optimizer ước tính phải xem xét cho một lần truy cập bảng; `filtered` là phần trăm hàng được ước tính còn lại sau lọc. Nhân `rows * filtered / 100` cho biết lượng hàng ước tính được chuyển sang bước tiếp theo, nhưng đây không phải số đo thực tế. Với JOIN, phải chú ý số lần lookup của bảng phía trong và lượng hàng tích lũy từ các bước trước. Dùng `EXPLAIN FORMAT=JSON` để xem cardinality chi tiết, `EXPLAIN ANALYZE` để đối chiếu actual rows/loops/timing, rồi điều tra thống kê, skew, tương quan và index khi sai lệch lớn. Đọc đúng hai con số này giúp giải thích quyết định của optimizer và tìm đúng bước làm phình lượng dữ liệu trong kế hoạch thực thi.
