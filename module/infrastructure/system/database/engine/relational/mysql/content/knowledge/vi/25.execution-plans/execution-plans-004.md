# Access type: const, eq_ref, ref, range, index và ALL

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Đọc cột `type` trong EXPLAIN và hiểu cách MySQL truy cập từng bảng trong kế hoạch thực thi.
- Phân biệt lookup bằng khóa duy nhất (`const`, `eq_ref`) với lookup có thể trả nhiều hàng (`ref`).
- Nhận diện truy cập theo khoảng khóa (`range`), quét toàn bộ index (`index`) và quét toàn bộ bảng (`ALL`).
- Liên hệ `type` với `possible_keys`, `key`, `key_len`, `ref`, `rows`, `filtered` và `Extra`.
- Giải thích vì sao `index` không luôn nhanh hơn `ALL`, và vì sao `ALL` đôi khi vẫn là lựa chọn hợp lý.
- Dùng dữ liệu thực hành và EXPLAIN để so sánh access type, sau đó kiểm tra giả thuyết bằng EXPLAIN ANALYZE.

Trong MySQL, EXPLAIN cho biết optimizer dự định đọc và kết hợp dữ liệu như thế nào. Cột `type` trong định dạng tabular mô tả cách MySQL truy cập một bảng trong kế hoạch join. Với định dạng JSON, thông tin tương ứng nằm ở thuộc tính `access_type`.

Sáu giá trị trong bài này thường được dùng để nhận biết mức độ chọn lọc của đường truy cập: `const`, `eq_ref`, `ref`, `range`, `index` và `ALL`. Chúng mô tả các cách đọc dữ liệu khác nhau, từ tìm tối đa một hàng bằng khóa duy nhất đến quét toàn bộ index hoặc toàn bộ bảng.

Không nên đọc `type` như một bảng xếp hạng hiệu năng tuyệt đối. Một access type tốt vẫn có thể chậm nếu phải thực hiện hàng triệu lần lookup; một lần quét `ALL` có thể hợp lý nếu bảng rất nhỏ hoặc truy vấn cần phần lớn hàng. Hãy đọc `type` cùng số hàng ước lượng, index được chọn, điều kiện lọc và kết quả đo thực tế.

## 1. Cột type nằm ở đâu trong EXPLAIN?

Bắt đầu bằng một câu truy vấn bất kỳ:

~~~sql
EXPLAIN
SELECT *
FROM sales_order
WHERE customer_id = 101;
~~~

EXPLAIN dạng tabular thường có các cột sau:

Nếu cấu hình server thay đổi định dạng EXPLAIN mặc định, hãy yêu cầu rõ định dạng tabular bằng `EXPLAIN FORMAT=TRADITIONAL`. Với JSON, tên thuộc tính tương ứng với cột `type` là `access_type`; TREE thể hiện các iterator bằng mô tả dạng cây.

| Cột | Ý nghĩa cần đọc |
|---|---|
| `id` | Thứ tự hoặc định danh query block trong kế hoạch |
| `select_type` | Loại query block, ví dụ SIMPLE hoặc PRIMARY |
| `table` | Bảng hoặc bí danh bảng đang được đọc |
| `partitions` | Partition được truy cập nếu bảng có partition |
| `type` | Access/join type được dùng để đọc bảng |
| `possible_keys` | Các index optimizer có thể cân nhắc |
| `key` | Index optimizer thực sự chọn |
| `key_len` | Độ dài phần khóa được sử dụng |
| `ref` | Giá trị hoặc cột được so sánh với index |
| `rows` | Số hàng optimizer ước tính phải đọc |
| `filtered` | Phần trăm hàng ước tính còn lại sau điều kiện lọc tại bảng |
| `Extra` | Thông tin bổ sung như Using index, Using where hoặc Using filesort |

Cột `type` trả lời câu hỏi: MySQL sẽ tìm hàng theo một khóa duy nhất, dò theo index, quét một khoảng hay quét toàn bộ cấu trúc?

Cột `key` trả lời câu hỏi: index nào được dùng? Hai cột phải được đọc cùng nhau. Ví dụ, `type = range` và `key = idx_order_date` có nghĩa MySQL dùng index ngày đặt hàng để đọc các khoảng khóa phù hợp.

MySQL còn có các access type khác như `system`, `fulltext`, `ref_or_null`, `index_merge`, `unique_subquery` và `index_subquery`. Bài này tập trung vào sáu giá trị thường gặp trong đề bài.

### 1.1. EXPLAIN không thực thi câu SELECT

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM sales_order
WHERE ordered_at >= '2026-02-01'
  AND ordered_at <  '2026-03-01';
~~~

EXPLAIN thông thường lấy kế hoạch do optimizer ước lượng; nó không chạy câu SELECT để trả về các hàng nghiệp vụ.

Để quan sát số liệu thực thi, MySQL 8.4 hỗ trợ:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, total_amount
FROM sales_order
WHERE ordered_at >= '2026-02-01'
  AND ordered_at <  '2026-03-01';
~~~

EXPLAIN ANALYZE thực sự chạy câu SELECT và bổ sung số hàng thực tế, số vòng lặp cùng thời gian của các iterator. Chỉ dùng nó với truy vấn có chi phí thực thi mà bạn chấp nhận được, đặc biệt trên production.

EXPLAIN ANALYZE luôn dùng định dạng TREE, vì vậy nó không hiển thị cột `type` dạng bảng. Hãy dùng EXPLAIN dạng tabular để đọc access type, rồi dùng EXPLAIN ANALYZE để đối chiếu số hàng và thời gian thực tế.

### 1.2. Access type phụ thuộc vị trí bảng trong join

Trong truy vấn join, các bảng được đọc theo một thứ tự do optimizer chọn. Giá trị từ bảng đã đọc có thể trở thành đầu vào để tìm hàng ở bảng tiếp theo.

Ví dụ:

- Bảng đầu tiên có thể được lọc bằng một hằng số.
- Bảng tiếp theo có thể được dò theo khóa ngoại của bảng trước.
- Bảng thứ ba có thể được tìm bằng khóa chính dựa trên kết quả từ hai bảng đầu.

Vì thế, `eq_ref` và `ref` thường được hiểu trong ngữ cảnh mỗi tổ hợp hàng từ các bảng đứng trước. Đừng chỉ nhìn một hàng EXPLAIN mà bỏ qua thứ tự các hàng trong kết quả.

## 2. Chuẩn bị dữ liệu thực hành

Các ví dụ trong bài dùng database thử nghiệm với ba bảng: customer, sales_order và order_line. Mỗi bảng dùng InnoDB để các index B-tree hoạt động theo cách thường gặp trong ứng dụng.

### 2.1. Tạo bảng

~~~sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    email VARCHAR(190) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customer_email (email)
) ENGINE = InnoDB;

CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL,
    order_no VARCHAR(30) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    ordered_at DATETIME NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    note VARCHAR(200) NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_order_no (order_no),
    KEY idx_customer_status (customer_id, order_status),
    KEY idx_order_status (order_status),
    KEY idx_order_date (ordered_at),
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_line (
    order_line_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_line_id),
    KEY idx_line_order (order_id),
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES sales_order (order_id)
) ENGINE = InnoDB;
~~~

Các index quan trọng trong bài:

- `PRIMARY KEY` của customer và sales_order là khóa duy nhất, không NULL.
- `uq_order_no` là unique index trên order_no.
- `idx_customer_status` là composite index, có customer_id ở vị trí đầu tiên.
- `idx_order_status` và `idx_order_date` là index không duy nhất.
- `idx_line_order` cho phép tìm nhiều dòng chi tiết của một đơn hàng.

### 2.2. Nạp dữ liệu

~~~sql
INSERT INTO customer (
    customer_id, customer_name, email
)
VALUES
    (101, 'Nguyen An', 'an@example.test'),
    (102, 'Tran Binh', 'binh@example.test'),
    (103, 'Le Chi', 'chi@example.test'),
    (104, 'Pham Dung', 'dung@example.test');

INSERT INTO sales_order (
    order_id,
    order_no,
    customer_id,
    order_status,
    ordered_at,
    total_amount,
    note
)
VALUES
    (5001, 'SO-2026-0001', 101, 'PAID',
     '2026-02-01 09:15:00', 1250000.00, 'standard delivery'),
    (5002, 'SO-2026-0002', 101, 'PAID',
     '2026-02-03 11:30:00', 2400000.00, 'gift wrap'),
    (5003, 'SO-2026-0003', 102, 'PENDING',
     '2026-02-08 14:00:00',  890000.00, 'call before delivery'),
    (5004, 'SO-2026-0004', 103, 'PAID',
     '2026-02-15 16:45:00', 3400000.00, 'standard delivery'),
    (5005, 'SO-2026-0005', 101, 'CANCELLED',
     '2026-02-18 10:20:00',  450000.00, 'cancelled by customer'),
    (5006, 'SO-2026-0006', 104, 'PAID',
     '2026-03-02 08:10:00', 5100000.00, 'priority delivery'),
    (5007, 'SO-2026-0007', 102, 'PENDING',
     '2026-03-05 13:25:00',  760000.00, 'awaiting payment'),
    (5008, 'SO-2026-0008', 101, 'PAID',
     '2026-03-10 17:05:00', 1750000.00, 'standard delivery');

INSERT INTO order_line (
    order_line_id, order_id, product_code, quantity, unit_price
)
VALUES
    (9001, 5001, 'KB-01', 1, 1250000.00),
    (9002, 5001, 'MS-01', 2,  350000.00),
    (9003, 5002, 'KB-02', 1, 2400000.00),
    (9004, 5003, 'CB-01', 1,  890000.00),
    (9005, 5004, 'MN-01', 2, 1700000.00),
    (9006, 5005, 'HD-01', 1,  450000.00),
    (9007, 5006, 'SC-01', 1, 5100000.00),
    (9008, 5007, 'CB-02', 1,  760000.00),
    (9009, 5008, 'KB-01', 1, 1750000.00);
~~~

Đây là dữ liệu nhỏ để nhìn rõ quan hệ và kết quả truy vấn. Optimizer có thể chọn kế hoạch khác trên dữ liệu rất nhỏ vì chi phí quét bảng thấp. Khi cần quan sát một access type cụ thể, bài học dùng `FORCE INDEX` hoặc `STRAIGHT_JOIN` ở các ví dụ được ghi chú; đây là công cụ thực hành, không phải chỉ thị nên ép kế hoạch trong ứng dụng thật.

## 3. const: tìm tối đa một hàng bằng giá trị hằng

`const` được dùng khi MySQL có thể tìm tối đa một hàng bằng cách so sánh toàn bộ khóa chính hoặc toàn bộ unique index với các giá trị hằng.

Ví dụ với khóa chính:

~~~sql
EXPLAIN
SELECT *
FROM customer
WHERE customer_id = 101;
~~~

Ví dụ với unique index:

~~~sql
EXPLAIN
SELECT *
FROM sales_order
WHERE order_no = 'SO-2026-0001';
~~~

Với các truy vấn này:

- Điều kiện cung cấp giá trị khóa cụ thể ngay trong câu SQL.
- Tất cả phần của PRIMARY KEY hoặc UNIQUE index được sử dụng.
- Tối đa một hàng phù hợp.
- Optimizer có thể đọc hàng ngay từ đầu và xem giá trị các cột của hàng như hằng số trong phần còn lại của kế hoạch.

### 3.1. Khóa ghép phải dùng đủ các phần

Giả sử bảng có unique index ghép:

~~~sql
CREATE TABLE warehouse_bin (
    warehouse_id INT UNSIGNED NOT NULL,
    bin_code VARCHAR(30) NOT NULL,
    capacity INT UNSIGNED NOT NULL,
    PRIMARY KEY (warehouse_id, bin_code)
) ENGINE = InnoDB;
~~~

Truy vấn dùng đủ hai phần khóa:

~~~sql
EXPLAIN
SELECT capacity
FROM warehouse_bin
WHERE warehouse_id = 1
  AND bin_code = 'A-01';
~~~

Đây là trường hợp có thể dùng `const`, vì toàn bộ khóa chính ghép được so sánh với giá trị hằng.

Nếu chỉ lọc warehouse_id, điều kiện mới dùng một phần khóa chính ghép và có thể trả nhiều hàng. Khi đó không còn là lookup `const` theo toàn bộ khóa chính.

### 3.2. const khác ref như thế nào?

Nếu điều kiện tìm theo một khóa không duy nhất, một giá trị có thể khớp nhiều hàng. MySQL phải đọc tất cả hàng phù hợp, vì vậy access type thường là `ref`.

Nếu dùng khóa duy nhất đầy đủ với hằng số và có tối đa một hàng, `const` phù hợp hơn.

Không phải mọi câu WHERE có dấu bằng đều tạo `const`. Dấu bằng trên một cột không index hoặc trên index không duy nhất không đủ để đảm bảo chỉ có một hàng.

## 4. eq_ref: mỗi tổ hợp hàng trước đó khớp tối đa một hàng

`eq_ref` thường xuất hiện ở bảng được join sau một bảng khác. Với mỗi tổ hợp hàng từ các bảng đứng trước, MySQL tìm tối đa một hàng trong bảng hiện tại bằng toàn bộ PRIMARY KEY hoặc UNIQUE NOT NULL index.

Ví dụ: mỗi đơn hàng thuộc về đúng một khách hàng:

~~~sql
EXPLAIN
SELECT
    o.order_id,
    o.order_no,
    c.customer_name
FROM sales_order AS o
STRAIGHT_JOIN customer AS c
    ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
~~~

`STRAIGHT_JOIN` yêu cầu MySQL đọc sales_order trước rồi mới đọc customer. Với mỗi hàng đơn hàng, điều kiện join cung cấp một customer_id để tìm đúng một hàng theo PRIMARY KEY của customer.

Trong EXPLAIN, hàng của customer có thể có:

- `type = eq_ref`
- `key = PRIMARY`
- `ref` tham chiếu đến cột customer_id của sales_order

Giá trị `type` của sales_order phụ thuộc index và thống kê; điểm cần quan sát ở ví dụ này là access type của customer.

### 4.1. Điều kiện để có eq_ref

Các điều kiện cốt lõi:

1. Phép so sánh là equality, thường dùng toán tử `=`.
2. Toàn bộ phần của index được sử dụng.
3. Index là PRIMARY KEY hoặc UNIQUE NOT NULL.
4. Giá trị so sánh có thể là hằng số hoặc cột từ bảng đã được đọc trước.

Nếu join chỉ dùng một phần của composite unique index, hoặc index không duy nhất, MySQL có thể phải dùng `ref` vì một giá trị có thể khớp nhiều hàng.

### 4.2. Ví dụ eq_ref với khóa ghép

~~~sql
EXPLAIN
SELECT
    l.order_line_id,
    o.order_no
FROM order_line AS l
STRAIGHT_JOIN sales_order AS o
    ON o.order_id = l.order_id;
~~~

Với mỗi dòng chi tiết, order_id xác định tối đa một đơn hàng qua PRIMARY KEY của sales_order. Bảng sales_order có thể được truy cập bằng `eq_ref`.

`eq_ref` thường là một đường join rất chọn lọc. Tuy nhiên, nếu bảng đứng trước có hàng triệu dòng, MySQL vẫn có thể thực hiện hàng triệu lookup. Hãy xem số vòng lặp và thời gian thực tế thay vì chỉ dựa vào nhãn access type.

## 5. ref: tìm tất cả hàng có cùng giá trị index

`ref` dùng khi MySQL dò index bằng một giá trị nhưng không thể đảm bảo chỉ có một hàng khớp.

Ví dụ tìm tất cả đơn hàng của khách hàng 101:

~~~sql
EXPLAIN
SELECT
    order_id,
    order_no,
    order_status
FROM sales_order FORCE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

Index `idx_customer_status(customer_id, order_status)` có customer_id ở vị trí đầu tiên. Truy vấn dùng phần đầu của index để tìm các đơn của khách hàng. Vì một khách hàng có thể có nhiều đơn, access type phù hợp là `ref`.

### 5.1. ref có thể dùng leftmost prefix

Index ghép trong schema thực hành là `KEY idx_customer_status (customer_id, order_status)`.

Truy vấn chỉ lọc customer_id:

~~~sql
SELECT *
FROM sales_order
WHERE customer_id = 101;
~~~

có thể sử dụng phần đầu của index. Đây là quy tắc leftmost prefix: MySQL có thể khai thác các cột liên tiếp bắt đầu từ cột đầu tiên của composite index.

Nếu chỉ lọc order_status mà không có customer_id, index này thường không phải lựa chọn trực tiếp cho một lookup theo leftmost prefix. Index riêng `idx_order_status` trong schema thực hành phục vụ trường hợp đó.

### 5.2. ref không đồng nghĩa với một hàng

Giả sử một khách hàng có 3.000 đơn. Một lookup `ref` theo customer_id vẫn có thể trả về 3.000 hàng.

Vì vậy, hãy đọc thêm:

- `rows`: số hàng ước tính cần đọc cho mỗi lần truy cập.
- `filtered`: tỷ lệ hàng dự kiến còn lại sau điều kiện lọc.
- `Extra`: điều kiện còn phải kiểm tra sau khi lấy hàng.
- Số lần lặp trong EXPLAIN ANALYZE nếu truy vấn là join.

Một `ref` trả ít hàng thường hữu ích. Một `ref` trả rất nhiều hàng có thể tốn kém, nhất là khi được lặp lại cho nhiều hàng từ bảng trước.

## 6. range: đọc một hoặc nhiều khoảng khóa

`range` dùng index để lấy một tập con hàng nằm trong một hoặc nhiều khoảng giá trị. Các điều kiện phổ biến gồm:

- `>`, `>=`, `<`, `<=`
- `BETWEEN`
- `IN (...)`
- `IS NULL`, `IS NOT NULL`
- `LIKE 'prefix%'` trên B-tree khi chuỗi mẫu không bắt đầu bằng wildcard

Ví dụ tìm đơn trong tháng 2:

~~~sql
EXPLAIN
SELECT
    order_id,
    order_no,
    ordered_at,
    total_amount
FROM sales_order FORCE INDEX (idx_order_date)
WHERE ordered_at >= '2026-02-01 00:00:00'
  AND ordered_at <  '2026-03-01 00:00:00';
~~~

Index `idx_order_date(ordered_at)` có thể hỗ trợ truy cập theo khoảng thời gian. Khoảng nửa mở `[đầu tháng, đầu tháng kế tiếp)` thường thuận tiện cho DATETIME vì không phải đoán thời điểm cuối ngày có phần microsecond hay không.

### 6.1. BETWEEN và nhiều khoảng

~~~sql
EXPLAIN
SELECT order_id, ordered_at
FROM sales_order
WHERE ordered_at BETWEEN
      '2026-02-01 00:00:00'
      AND '2026-02-28 23:59:59';
~~~

Hoặc:

~~~sql
EXPLAIN
SELECT order_id, order_status
FROM sales_order
WHERE order_status IN ('PAID', 'PENDING');
~~~

Optimizer có thể dùng range access nếu index và chi phí phù hợp. Dù điều kiện là equality hoặc IN, `type` có thể được biểu diễn là `range` khi MySQL xây dựng một hoặc nhiều khoảng index.

### 6.2. Range trên composite index

Với index ghép, MySQL có thể tạo khoảng trên các phần khóa liên tiếp. Ví dụ:

~~~sql
CREATE INDEX idx_customer_date
ON sales_order (customer_id, ordered_at);
~~~

Truy vấn:

~~~sql
EXPLAIN
SELECT order_id, ordered_at
FROM sales_order
WHERE customer_id = 101
  AND ordered_at >= '2026-02-01 00:00:00'
  AND ordered_at <  '2026-03-01 00:00:00';
~~~

Optimizer có thể dùng customer_id làm phần bằng và ordered_at làm biên range trên index ghép.

Với B-tree composite index, sau khi gặp phần khóa dùng điều kiện range, các phần tiếp theo thường không tiếp tục thu hẹp cùng một khoảng theo cách đơn giản như các điều kiện equality đứng trước. Cần xem `key_len`, optimizer trace và kế hoạch thực tế để biết chính xác các phần khóa đã tham gia tạo range.

### 6.3. Range không có nghĩa là luôn đọc ít hàng

Nếu khoảng truy vấn bao phủ phần lớn bảng, quét index rồi truy xuất hàng có thể đắt hơn quét toàn bảng. Optimizer có thể chọn `ALL` thay vì `range` khi chi phí ước tính của range không có lợi.

Ngoài ra, điều kiện có hàm trên cột, ép kiểu không phù hợp hoặc wildcard ở đầu chuỗi có thể làm mất khả năng tạo range hiệu quả trên index thông thường.

Ví dụ thường khó khai thác index B-tree theo ordered_at:

~~~sql
SELECT order_id
FROM sales_order
WHERE DATE(ordered_at) = '2026-02-15';
~~~

Có thể viết lại thành điều kiện khoảng:

~~~sql
SELECT order_id
FROM sales_order
WHERE ordered_at >= '2026-02-15 00:00:00'
  AND ordered_at <  '2026-02-16 00:00:00';
~~~

Cách viết lại giúp optimizer có cơ hội dùng range access trực tiếp trên ordered_at.

## 7. index: quét toàn bộ cây index

`index` có nghĩa MySQL quét toàn bộ index tree của bảng. Nó tương tự `ALL` ở chỗ không giới hạn việc đọc vào một khoảng chọn lọc; khác biệt là cấu trúc được quét là index tree.

Ví dụ:

~~~sql
EXPLAIN
SELECT customer_id
FROM sales_order FORCE INDEX (idx_customer_status);
~~~

Index `idx_customer_status` chứa customer_id và order_status; các secondary index của InnoDB cũng mang khóa chính để định vị hàng. Truy vấn chỉ cần customer_id nên index có thể bao phủ dữ liệu cần trả về.

Kế hoạch có thể hiển thị:

- `type = index`
- `key = idx_customer_status`
- `Extra = Using index`

Điều đó có nghĩa MySQL có thể lấy dữ liệu cần thiết ngay từ index mà không phải đọc lại từng hàng trong clustered index.

### 7.1. Full index scan khác index lookup

Có hai khái niệm dễ nhầm:

- Index lookup: tìm một giá trị hoặc một khoảng bằng index, thường thể hiện qua `const`, `eq_ref`, `ref` hoặc `range`.
- Full index scan: đi qua toàn bộ entry của một index, thể hiện bằng `type = index`.

Một truy vấn chỉ chọn cột có trong index vẫn có thể phải đọc mọi entry. Việc có index không tự động làm truy vấn trở thành lookup chọn lọc.

### 7.2. Using index không phải access type

`Using index` nằm trong cột `Extra`, không phải cột `type`.

- `type = index`: cách truy cập là quét toàn bộ index.
- `Extra = Using index`: truy vấn có thể được đáp ứng chỉ bằng dữ liệu trong index (covering/index-only scan).

Có thể có `type = range` cùng `Using index` nếu MySQL đọc một khoảng index và toàn bộ cột cần thiết đều nằm trong index. Ngược lại, `type = index` có thể không có `Using index` nếu phải đọc hàng đầy đủ từ clustered index.

### 7.3. Khi nào index scan hữu ích?

Full index scan có thể hợp lý khi:

- Index nhỏ hơn đáng kể so với dữ liệu hàng.
- Truy vấn chỉ cần các cột nằm trong index.
- Thứ tự index giúp đáp ứng ORDER BY.
- Truy vấn cần phần lớn entry nhưng index-only scan vẫn ít dữ liệu phải đọc hơn table scan.

Nếu index rộng, chứa nhiều cột hoặc truy vấn phải lookup từng hàng trong clustered index, quét toàn index có thể không đem lại lợi ích.

## 8. ALL: quét toàn bộ bảng

`ALL` có nghĩa MySQL thực hiện full table scan trên bảng. Với InnoDB, việc đọc dữ liệu hàng thường đi qua clustered index.

Ví dụ:

~~~sql
EXPLAIN
SELECT *
FROM sales_order
WHERE total_amount >= 0;
~~~

Trong schema thực hành không có index trên total_amount. Điều kiện còn khớp tất cả hàng mẫu, và truy vấn yêu cầu toàn bộ cột. Full table scan thường là lựa chọn tự nhiên.

### 8.1. ALL không phải lúc nào cũng là lỗi

`ALL` có thể hợp lý khi:

- Bảng chỉ có vài hàng.
- Truy vấn cần phần lớn hàng trong bảng.
- Không có index phù hợp.
- Index có độ chọn lọc thấp, khiến lookup nhiều hàng tốn kém hơn quét tuần tự.
- Optimizer ước tính full scan có chi phí thấp hơn các đường index.

Điều cần kiểm tra là số hàng được đọc, số hàng trả về và tần suất chạy truy vấn. Một full scan trên bảng cấu hình 20 hàng có thể không đáng lo; full scan trên bảng giao dịch hàng trăm triệu hàng ở mỗi request có thể là vấn đề lớn.

### 8.2. Khi nào cần điều tra ALL?

Hãy điều tra khi:

- Bảng lớn nhưng truy vấn chỉ cần một vài hàng.
- Có index phù hợp nhưng `possible_keys` hoặc `key` không như mong đợi.
- Điều kiện lọc không sargable, ví dụ bọc cột trong hàm.
- Kiểu dữ liệu so sánh khác nhau dẫn đến chuyển đổi kiểu.
- Thống kê index cũ hoặc phân bố dữ liệu lệch.
- Truy vấn join khiến một bảng lớn bị quét lặp lại nhiều lần.

Có thể cập nhật thống kê sau thay đổi dữ liệu lớn:

~~~sql
ANALYZE TABLE sales_order;
~~~

ANALYZE TABLE cập nhật thống kê cho optimizer; nó không tạo index và không bảo đảm kế hoạch sẽ thay đổi theo hướng mong muốn. Hãy chạy EXPLAIN lại sau đó.

## 9. So sánh sáu access type

| type | Mẫu truy cập | Số hàng mỗi lần tìm | Ví dụ thường gặp |
|---|---|---:|---|
| `const` | Đọc tối đa một hàng bằng toàn bộ khóa duy nhất với hằng số | 0 hoặc 1 | PRIMARY KEY = 101 |
| `eq_ref` | Lookup bằng toàn bộ PRIMARY KEY/UNIQUE NOT NULL cho mỗi tổ hợp hàng trước | Tối đa 1 | Join order.customer_id tới customer.PK |
| `ref` | Lookup equality trên index không duy nhất hoặc leftmost prefix | Có thể nhiều | customer_id = 101 |
| `range` | Đọc một hoặc nhiều khoảng index | Một tập con | ordered_at trong một khoảng |
| `index` | Quét toàn bộ index tree | Toàn bộ entry index | Đọc cột được bao phủ bởi index |
| `ALL` | Quét toàn bộ bảng | Toàn bộ hàng | Lọc cột không index, lấy nhiều cột |

Tài liệu MySQL liệt kê các join type theo thứ tự khái quát từ tốt đến xấu, nhưng thứ tự đó không thay thế việc đánh giá chi phí. Đặc biệt, `index` và `ALL` đều là scan toàn bộ một cấu trúc; index scan chỉ có lợi khi cấu trúc index nhỏ hơn hoặc bao phủ tốt hơn dữ liệu cần đọc.

### 9.1. Phân biệt bằng câu hỏi

Khi đọc một dòng EXPLAIN, hãy lần lượt hỏi:

1. Có khóa duy nhất đầy đủ và giá trị hằng không? Có thể là const.
2. Đây có phải bảng join được tìm bằng toàn bộ khóa duy nhất dựa trên hàng trước không? Có thể là eq_ref.
3. Lookup equality có thể trả nhiều hàng không? Có thể là ref.
4. Truy vấn cần một khoảng giá trị trên index không? Có thể là range.
5. Không có điều kiện chọn lọc nhưng chỉ cần quét một index không? Có thể là index.
6. Không có đường index có lợi hoặc cần nhiều hàng? Có thể là ALL.

Câu hỏi tiếp theo luôn là: MySQL ước tính phải đọc bao nhiêu hàng và thực tế đã đọc bao nhiêu?

## 10. Đọc các cột đi kèm type

### 10.1. possible_keys và key

- `possible_keys` liệt kê index có thể dùng để tìm hàng.
- `key` là index thực sự được chọn.
- `key = NULL` thường có nghĩa không dùng index để định vị hàng trong bảng đó.

Một index có trong possible_keys nhưng không được chọn không nhất thiết là lỗi. Optimizer có thể ước tính scan rẻ hơn lookup, hoặc index không đủ chọn lọc.

### 10.2. key_len

`key_len` cho biết độ dài phần khóa được sử dụng. Với index ghép, nó giúp nhận diện MySQL đã dùng bao nhiêu phần khóa.

Đừng diễn giải key_len bằng cách đếm ký tự hoặc cột một cách cảm tính. Độ dài còn phụ thuộc kiểu dữ liệu, nullable, độ dài byte, charset và phần khóa thực sự tham gia access condition.

### 10.3. ref

`ref` cho biết cột hoặc hằng số được so sánh với index. Trong join, giá trị này thường trỏ tới cột từ bảng đứng trước.

Ví dụ, ở dòng customer trong truy vấn join đơn hàng, ref có thể là cột customer_id của sales_order. Đây là manh mối cho thấy lookup được thực hiện theo từng customer_id lấy từ bảng trước.

### 10.4. rows và filtered

`rows` là ước lượng số hàng MySQL cần đọc cho mỗi lần truy cập bảng. `filtered` là phần trăm hàng ước tính còn lại sau các điều kiện lọc bổ sung.

Ví dụ minh họa:

| type | rows | filtered | Diễn giải |
|---|---:|---:|---|
| ref | 100 | 10.00 | Dự kiến đọc 100 hàng, khoảng 10% còn lại sau lọc |
| range | 500 | 80.00 | Dự kiến đọc 500 hàng trong khoảng, khoảng 80% còn lại |
| ALL | 100000 | 1.00 | Quét 100.000 hàng, chỉ khoảng 1% còn lại |

Đây là số minh họa, không phải kết quả đo của schema thực hành. Ước lượng sai lệch có thể khiến optimizer chọn join order hoặc access path chưa tốt.

### 10.5. Extra

Một số giá trị thường gặp:

- `Using index`: truy vấn có thể được đáp ứng bằng index, không cần đọc thêm hàng từ clustered index.
- `Using where`: còn điều kiện được kiểm tra sau khi lấy hàng.
- `Using index condition`: Index Condition Pushdown giúp storage engine kiểm tra một phần điều kiện ngay trên index entry.
- `Using filesort`: MySQL cần bước sắp xếp bổ sung cho ORDER BY.
- `Using temporary`: truy vấn cần bảng tạm cho một bước xử lý.

Không suy ra tất cả chi phí chỉ từ `type`. Một truy vấn `range` có thể vẫn phải filesort hoặc đọc thêm nhiều hàng; một truy vấn `ref` có thể bị lặp lại rất nhiều lần trong join.

## 11. Lab: quan sát từng access type

Các câu lệnh sau dùng schema ở phần 2. Chạy EXPLAIN trước mỗi SELECT và xác định dòng bảng tương ứng.

### Lab 1: const trên PRIMARY KEY

~~~sql
EXPLAIN
SELECT *
FROM customer
WHERE customer_id = 101;
~~~

Kỳ vọng: bảng customer có thể dùng `const`, key là PRIMARY. Hãy kiểm tra điều kiện sử dụng toàn bộ khóa chính.

### Lab 2: const trên UNIQUE NOT NULL

~~~sql
EXPLAIN
SELECT order_id, customer_id, total_amount
FROM sales_order
WHERE order_no = 'SO-2026-0001';
~~~

Kỳ vọng: lookup tối đa một hàng bằng `uq_order_no`. Xác nhận index được khai báo UNIQUE và cột order_no là NOT NULL.

### Lab 3: eq_ref trong join

~~~sql
EXPLAIN
SELECT
    o.order_id,
    o.order_no,
    c.customer_name
FROM sales_order AS o
STRAIGHT_JOIN customer AS c
    ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
~~~

Tìm dòng customer trong EXPLAIN. Nó được đọc sau sales_order và có thể dùng PRIMARY KEY để tìm tối đa một khách hàng cho mỗi đơn.

### Lab 4: ref trên index không duy nhất

~~~sql
EXPLAIN
SELECT
    order_id,
    order_no,
    order_status
FROM sales_order FORCE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

Kỳ vọng: index ghép idx_customer_status được dùng qua phần đầu customer_id. Một khách hàng có thể có nhiều đơn nên access type có thể là `ref`.

### Lab 5: range trên ngày đặt hàng

~~~sql
EXPLAIN
SELECT order_id, ordered_at, total_amount
FROM sales_order FORCE INDEX (idx_order_date)
WHERE ordered_at >= '2026-02-01 00:00:00'
  AND ordered_at <  '2026-03-01 00:00:00';
~~~

Kỳ vọng: optimizer có thể dùng `range` với idx_order_date. Nếu dữ liệu nhỏ khiến optimizer chọn ALL, hãy tăng dữ liệu thử nghiệm hoặc dùng FORCE INDEX trong một phép thử riêng để quan sát access path.

### Lab 6: index full scan

~~~sql
EXPLAIN
SELECT customer_id
FROM sales_order FORCE INDEX (idx_customer_status);
~~~

Kỳ vọng: `type = index`, index được quét toàn bộ. Vì chỉ cần customer_id có trong index, Extra có thể hiển thị Using index.

### Lab 7: ALL full table scan

~~~sql
EXPLAIN
SELECT *
FROM sales_order
WHERE total_amount >= 0;
~~~

Kỳ vọng: điều kiện không có index riêng và truy vấn cần toàn bộ cột. Full table scan có thể được chọn.

### Lab 8: So sánh index scan và table scan

~~~sql
EXPLAIN
SELECT customer_id
FROM sales_order FORCE INDEX (idx_customer_status);

EXPLAIN
SELECT *
FROM sales_order;
~~~

So sánh số hàng ước tính, key, type và Extra. Truy vấn thứ nhất chỉ cần một cột trong index; truy vấn thứ hai yêu cầu toàn bộ hàng.

### Lab 9: Quan sát access type của nhiều bảng

~~~sql
EXPLAIN
SELECT
    c.customer_name,
    o.order_no,
    l.product_code,
    l.quantity
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id
JOIN order_line AS l
    ON l.order_id = o.order_id
WHERE c.customer_id = 101;
~~~

Theo dõi thứ tự bảng trong EXPLAIN. Bảng customer có thể được đọc bằng const; các bảng tiếp theo có thể dùng ref hoặc eq_ref tùy join order và index được chọn. Optimizer có quyền đổi thứ tự join nếu truy vấn không khóa thứ tự.

## 12. Vì sao kế hoạch thực tế có thể khác kỳ vọng?

### 12.1. Bảng quá nhỏ

Với bảng chỉ có vài hàng, full table scan có thể rẻ hơn việc đọc index rồi quay lại clustered index. Do đó, EXPLAIN có thể hiển thị `ALL` dù có index phù hợp.

Đây là quyết định chi phí, không nhất thiết là lỗi optimizer.

### 12.2. Điều kiện không chọn lọc

Nếu truy vấn trả về phần lớn hàng, index lookup có thể gây nhiều lần đọc rời rạc. Quét toàn bảng theo thứ tự vật lý có thể rẻ hơn.

Ví dụ, lọc order_status = 'PAID' có thể trả về phần lớn bảng nếu hầu hết đơn đều đã thanh toán. Index status không chắc giúp truy vấn nhanh hơn.

### 12.3. Thống kê chưa phản ánh dữ liệu

Optimizer dựa trên thống kê để ước lượng số hàng và độ chọn lọc. Sau khi nạp hoặc xóa lượng dữ liệu lớn, có thể chạy:

~~~sql
ANALYZE TABLE customer, sales_order, order_line;
~~~

Sau đó chạy EXPLAIN lại và so sánh. Không nên mặc định ANALYZE TABLE sẽ luôn thay đổi kế hoạch hoặc làm truy vấn nhanh hơn.

### 12.4. Kiểu dữ liệu và biểu thức làm giảm khả năng dùng index

Các vấn đề phổ biến:

- So sánh cột với giá trị khác kiểu dữ liệu gây chuyển đổi.
- Bọc cột index trong hàm như DATE(ordered_at).
- Dùng LIKE với wildcard ở đầu chuỗi như LIKE '%2026'.
- Chỉ lọc cột thứ hai của composite index mà không có điều kiện trên phần đầu.
- Dùng phép toán trên cột làm điều kiện không còn sargable.

Hãy viết điều kiện trên cột index theo dạng có thể tạo lookup hoặc range khi phù hợp với nghiệp vụ.

### 12.5. Hạn chế của index ghép

Index `(customer_id, order_status)` có thể phục vụ điều kiện customer_id hoặc customer_id kết hợp order_status. Nó không tự động phục vụ tốt truy vấn chỉ lọc order_status.

Trước khi tạo index mới, hãy đối chiếu thứ tự cột với các truy vấn thực tế và xem index hiện tại đã đủ chưa.

## 13. Quy trình đọc EXPLAIN trong công việc

Khi điều tra một truy vấn chậm, làm theo trình tự:

1. Chạy EXPLAIN và xác định query block cùng thứ tự bảng.
2. Đọc `type` cho từng bảng, bắt đầu từ bảng đầu tiên.
3. Đối chiếu `possible_keys`, `key`, `key_len` và `ref`.
4. Đọc `rows` và `filtered` để tìm bảng có lượng đọc lớn.
5. Kiểm tra `Extra` để phát hiện lọc bổ sung, sort, temporary table hoặc covering index.
6. Xem điều kiện WHERE và JOIN có phù hợp với thứ tự cột index không.
7. Chạy EXPLAIN ANALYZE trong môi trường phù hợp để so sánh ước lượng với hàng thực tế và thời gian.
8. Chỉ thay đổi index hoặc câu SQL sau khi xác định nút thắt.
9. Đo lại cùng dữ liệu, tham số và điều kiện tải để xác nhận cải thiện.

Sơ đồ ghi nhớ:

~~~mermaid
flowchart TD
    A[Chạy EXPLAIN] --> B[Đọc thứ tự bảng]
    B --> C[Đọc type và key]
    C --> D[Kiểm tra rows, filtered, Extra]
    D --> E{Có scan hoặc lookup quá rộng?}
    E -->|Có| F[Kiểm tra điều kiện và index]
    E -->|Không| G[Kiểm tra sort, temporary và join lặp]
    F --> H[Thử thay đổi trên dữ liệu đại diện]
    G --> H
    H --> I[EXPLAIN ANALYZE và đo lại]
    I --> J[So sánh kế hoạch, hàng thực tế và thời gian]
~~~

## 14. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| const và eq_ref giống nhau | const đọc tối đa một hàng từ giá trị hằng; eq_ref lookup một hàng cho mỗi tổ hợp bảng trước | Xem bảng có phải join input hay không |
| Mọi điều kiện bằng đều là const | Index có thể không duy nhất hoặc chỉ dùng một phần khóa | Kiểm tra định nghĩa index và key_len |
| ref luôn chỉ trả một hàng | Index không duy nhất có thể trả rất nhiều hàng | Đọc rows và filtered |
| range chỉ áp dụng cho toán tử lớn hơn/nhỏ hơn | IN, BETWEEN và một số equality range cũng có thể tạo range access | Xem access path trong EXPLAIN |
| index có nghĩa truy vấn đọc ít hàng | type=index là full index scan | Phân biệt index scan với index lookup |
| Using index là một type | Đây là thông tin trong Extra về covering/index-only access | Đọc cả type và Extra |
| ALL luôn là kế hoạch tệ | Bảng nhỏ hoặc truy vấn lấy phần lớn dữ liệu có thể phù hợp với full scan | Đánh giá chi phí và hàng thực tế |
| Có index thì optimizer luôn dùng | Optimizer so sánh chi phí và độ chọn lọc | Xem key và possible_keys |
| rows là số hàng thực tế | Đây là ước lượng của optimizer | Dùng EXPLAIN ANALYZE để đo |
| key_len cho biết số cột index đơn giản | Độ dài phụ thuộc kiểu dữ liệu, nullable và phần khóa sử dụng | Đối chiếu định nghĩa index và charset |
| FORCE INDEX luôn làm truy vấn nhanh hơn | Ép index có thể khiến kế hoạch đắt hơn | Chỉ dùng để thử nghiệm hoặc sau khi đo kỹ |

## 15. Bài tập thực hành

### Bài 1: Nhận diện const

Viết hai truy vấn tìm customer bằng PRIMARY KEY và email bằng UNIQUE index. Chạy EXPLAIN và giải thích vì sao mỗi truy vấn có thể dùng const.

### Bài 2: Phân biệt const và eq_ref

Dùng truy vấn đơn hàng join khách hàng. Giải thích vì sao customer được đọc theo từng order thay vì được xem như một bảng const.

### Bài 3: Quan sát ref

Tìm tất cả đơn của customer_id = 101. Thay đổi dữ liệu để một khách hàng có hàng trăm đơn rồi so sánh rows ước tính.

### Bài 4: Leftmost prefix

Dùng index (customer_id, order_status). So sánh EXPLAIN cho điều kiện chỉ có customer_id, chỉ có order_status và có cả hai điều kiện.

### Bài 5: Range theo thời gian

Viết truy vấn tháng 2 bằng BETWEEN và bằng khoảng nửa mở. So sánh kế hoạch và giải thích khác biệt về biên DATETIME.

### Bài 6: Full index scan

Dùng FORCE INDEX để quét idx_customer_status. Thay đổi SELECT để lấy thêm note không nằm trong index và quan sát Extra.

### Bài 7: Full table scan

Truy vấn theo total_amount. Thêm một index phù hợp trong môi trường thử nghiệm rồi chạy EXPLAIN lại. So sánh kế hoạch trước và sau.

### Bài 8: Dữ liệu nhỏ và dữ liệu lớn

Chạy cùng truy vấn trên bảng có ít hàng và bảng có nhiều hàng. Quan sát khi nào optimizer chuyển giữa ALL và access type dùng index.

### Bài 9: Kiểm tra ước lượng

Chạy EXPLAIN và EXPLAIN ANALYZE cho truy vấn join. So sánh rows ước tính với actual rows, số loops và thời gian.

### Bài 10: Chẩn đoán truy vấn chậm

Chọn một truy vấn có ALL hoặc index scan trên bảng lớn. Phân tích index hiện tại, đề xuất thay đổi và chứng minh bằng kế hoạch cùng số liệu đo.

## Kết luận

`const` và `eq_ref` là các đường lookup có tối đa một hàng; `ref` dùng equality lookup nhưng có thể trả nhiều hàng; `range` đọc một hoặc nhiều khoảng index; `index` quét toàn bộ index tree; `ALL` quét toàn bộ bảng.

Hãy đọc cột `type` cùng `key`, `key_len`, `ref`, `rows`, `filtered` và `Extra`. Sau đó kiểm tra kế hoạch thực tế bằng EXPLAIN ANALYZE khi phù hợp. Một access type tốt không đảm bảo truy vấn nhanh nếu số hàng hoặc số lần lặp quá lớn; một full scan cũng không phải lỗi nếu nó có chi phí thấp nhất cho dữ liệu và kết quả cần đọc.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — EXPLAIN Output Format: https://dev.mysql.com/doc/refman/8.4/en/explain-output.html
- MySQL 8.4 Reference Manual — Range Optimization: https://dev.mysql.com/doc/refman/8.4/en/range-optimization.html
- MySQL 8.4 Reference Manual — EXPLAIN Statement: https://dev.mysql.com/doc/refman/8.4/en/explain.html
- MySQL 8.4 Reference Manual — How MySQL Uses Indexes: https://dev.mysql.com/doc/refman/8.4/en/mysql-indexes.html
- MySQL 8.4 Reference Manual — Multiple-Column Indexes: https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html
- MySQL 8.4 Reference Manual — Verifying Index Usage: https://dev.mysql.com/doc/refman/8.4/en/verifying-index-usage.html

