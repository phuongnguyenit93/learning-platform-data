# Khóa phân vùng, biên và phân vùng mặc định trong PostgreSQL

Khi bảng PostgreSQL tăng từ vài triệu lên hàng trăm triệu hàng, một cách tổ chức dữ liệu thường được cân nhắc là **phân vùng bảng** (*table partitioning*). Thay vì để tất cả hàng trong một quan hệ vật lý duy nhất, PostgreSQL có thể định tuyến hàng vào nhiều bảng con dựa trên **khóa phân vùng** (*partition key*) và các **biên phân vùng** (*partition bounds*).

Ví dụ, hệ thống lưu đơn hàng theo ngày tạo:

~~~text
orders (bảng cha khai báo PARTITION BY RANGE)
  |
  +-- orders_2026_01 : [2026-01-01, 2026-02-01)
  +-- orders_2026_02 : [2026-02-01, 2026-03-01)
  +-- orders_default : mọi giá trị chưa khớp các khoảng trên
~~~

Ngày `2026-01-31` thuộc tháng 1, nhưng ngày `2026-02-01` **không** còn thuộc phân vùng tháng 1. Khi ứng dụng gửi một hàng có ngày tháng 3 mà chưa có phân vùng tháng 3, PostgreSQL có thể đưa nó vào `orders_default` nếu bảng cha đã khai báo phân vùng mặc định. Nếu không có phân vùng phù hợp, câu `INSERT` thất bại.

Điều quan trọng hơn: khi đã có hàng tháng 3 trong `orders_default`, việc thêm phân vùng riêng cho tháng 3 **không đơn thuần là chạy một câu CREATE TABLE**. PostgreSQL phải bảo đảm không còn hàng thuộc khoảng tháng 3 ở phân vùng mặc định; nếu còn, thao tác có thể bị từ chối và cần kế hoạch di chuyển dữ liệu an toàn.

Bài học này giải thích:

- Cách chọn **khóa phân vùng**, phân biệt `RANGE`, `LIST` và `HASH`.
- Cách hiểu **biên dưới bao gồm, biên trên loại trừ**, `MINVALUE`, `MAXVALUE` và khoảng nhiều cột.
- Ý nghĩa và giới hạn của **phân vùng mặc định** (*DEFAULT partition*).
- Cách định tuyến `INSERT`, xử lý `UPDATE` làm đổi khóa, quan sát `tableoid`.
- Cách kiểm tra metadata, pruning, điều kiện khóa chính/`UNIQUE`, quy trình thêm phân vùng mới khi DEFAULT đã có dữ liệu.
- Những vấn đề vận hành: tạo trước partition, dữ liệu ngoài khoảng, khóa DDL, lưu trữ và lưu giữ dữ liệu.

**Lưu ý thuật ngữ:** “khóa phân vùng” ở đây là *partition key* — cột/biểu thức quyết định hàng nằm ở partition nào. Nó **không phải row lock/table lock** dùng để điều phối transaction đồng thời.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chọn partition key phản ánh truy vấn và cách quản lý vòng đời dữ liệu.
2. Giải thích quy tắc định tuyến của `RANGE`, `LIST`, `HASH`.
3. Viết partition bounds không chồng lấn, không bỏ sót đầu mút ngoài chủ ý.
4. Biết tại sao `FOR VALUES FROM (a) TO (b)` bao gồm `a` nhưng loại `b`.
5. Giải thích `DEFAULT` nhận những hàng nào và giá trị `NULL` được xử lý ra sao.
6. Nhận ra biên `RANGE` nhiều cột có so sánh theo bộ giá trị, không phải các hình chữ nhật điều kiện độc lập.
7. Tạo bảng cha, partition con, default partition và truy vấn kiểm tra `tableoid`.
8. Xử lý trường hợp dữ liệu đang ở DEFAULT cần chuyển sang phân vùng tháng mới.
9. Đọc `EXPLAIN` để xác định partition pruning có diễn ra không.
10. Thiết kế khóa chính/`UNIQUE` phù hợp giới hạn của partitioned table.
11. Nhận diện rủi ro concurrency, locking và phân vùng tương lai bị thiếu.

## 2. Phân vùng bảng thực chất là gì?

Với **declarative partitioning**, bạn tạo một bảng cha:

~~~sql
CREATE TABLE example_orders (
    order_id bigint NOT NULL,
    order_date date NOT NULL,
    amount numeric(12, 2) NOT NULL
) PARTITION BY RANGE (order_date);
~~~

Bảng cha khai báo lược đồ và quy tắc phân vùng. Các bảng partition riêng mới giữ hàng vật lý:

~~~sql
CREATE TABLE example_orders_jan
PARTITION OF example_orders
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
~~~

Khi thực thi:

~~~sql
INSERT INTO example_orders (order_id, order_date, amount)
VALUES (1, DATE '2026-01-15', 50000);
~~~

PostgreSQL định tuyến hàng vào `example_orders_jan` dựa trên khóa `order_date`.

### 2.1. Bảng cha không giữ các hàng riêng của nó

Với declarative partitioned table thông thường, **bảng cha là quan hệ phân vùng ảo**, còn hàng nằm ở các partitions (có thể có các tầng subpartition).

~~~sql
SELECT *
FROM example_orders;
~~~

Truy vấn qua bảng cha có thể thấy hàng từ các partitions phù hợp.

### 2.2. Không nhầm phân vùng với tạo nhiều bảng tùy ý

Nếu bạn tự tạo các bảng `orders_jan`, `orders_feb` không gắn qua `PARTITION OF`/`ATTACH PARTITION`, PostgreSQL **không tự biết** chúng là các partitions của `orders`. Truy vấn bảng cha cũng không tự `UNION ALL` các bảng độc lập ấy.

### 2.3. Khóa phân vùng quyết định định tuyến

~~~text
INSERT into parent
       |
       v
Tính partition key
       |
       v
So với các partition bounds
       |
       +--> tìm được partition -> lưu hàng vào partition đó
       |
       +--> không tìm được -> DEFAULT (nếu có)
       |
       +--> không có DEFAULT -> lỗi định tuyến
~~~

## 3. Ba chiến lược: RANGE, LIST, HASH

| Chiến lược | Định nghĩa khóa | Cách xác định partition | Khi thường phù hợp |
| --- | --- | --- | --- |
| `RANGE` | Một hoặc nhiều cột/biểu thức có thứ tự | Khoảng `FROM ... TO ...` | Ngày/tháng, ID theo dải, dữ liệu theo thời gian |
| `LIST` | Một cột hoặc biểu thức | Một tập giá trị liệt kê `FOR VALUES IN (...)` | Quốc gia, vùng, trạng thái có tập giá trị được quản lý |
| `HASH` | Một hoặc nhiều cột/biểu thức | Hash với `MODULUS` và `REMAINDER` | Phân tán dữ liệu theo khóa khi không có dải truy vấn tự nhiên |

### 3.1. RANGE: chia theo khoảng

~~~sql
PARTITION BY RANGE (order_date)
~~~

Rất hữu ích nếu ứng dụng thường hỏi:

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
~~~

và cần lưu trữ, lưu giữ hoặc xóa dữ liệu theo tháng.

### 3.2. LIST: chia theo danh sách

~~~sql
PARTITION BY LIST (region)
~~~

Vùng `'north'`, `'south'` có thể thuộc partition riêng, còn giá trị mới hoặc không biết trước được đưa về DEFAULT nếu có.

### 3.3. HASH: chia theo giá trị băm

~~~sql
PARTITION BY HASH (customer_id)
~~~

Phù hợp phân tán tương đối đều theo ID, không tự giúp query tìm “tháng 2” nếu khóa không phải thời gian.

### 3.4. Chọn chiến lược từ access pattern

Không chọn theo cảm giác “chia nhiều partition sẽ nhanh”. Trước tiên xác định:

- Predicate phổ biến của query là gì?
- Có cần xóa/lưu trữ theo mốc thời gian không?
- Dữ liệu có lệch mạnh theo vùng/khách không?
- Có bao nhiêu partition, và sẽ tăng thế nào?
- Khóa có ổn định khi `UPDATE` không?
- Những `PRIMARY KEY`/`UNIQUE`/`FOREIGN KEY` nào cần giữ?

## 4. Dựng schema thực hành

Các lệnh trong bài dành cho **database lab**. Không chạy lại các thao tác tạo, gắn hoặc di chuyển partition trên bảng production.

### 4.1. Tạo schema

~~~sql
CREATE SCHEMA part_lab;
~~~

### 4.2. Tạo bảng cha phân vùng theo ngày

~~~sql
CREATE TABLE part_lab.orders (
    order_id bigint NOT NULL,
    order_date date NOT NULL,
    customer_id integer NOT NULL,
    region text NOT NULL,
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    status text NOT NULL DEFAULT 'new',
    PRIMARY KEY (order_id, order_date)
) PARTITION BY RANGE (order_date);
~~~

Điểm cần quan sát:

- `order_date` là **partition key**.
- Khóa chính gồm cả `order_id` và `order_date` vì PostgreSQL yêu cầu các cột khóa phân vùng phù hợp có mặt trong khóa duy nhất/khóa chính trên bảng cha.
- `order_date NOT NULL` giúp ví dụ ngày tháng rõ ràng; trong phần RANGE với nullable key sẽ giải thích cách NULL được xử lý.
- `PRIMARY KEY (order_id, order_date)` **không bảo đảm riêng `order_id` là duy nhất trên mọi ngày**.

### 4.3. Tạo partition tháng 1, tháng 2

~~~sql
CREATE TABLE part_lab.orders_2026_01
PARTITION OF part_lab.orders
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE part_lab.orders_2026_02
PARTITION OF part_lab.orders
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
~~~

### 4.4. Tạo DEFAULT partition

~~~sql
CREATE TABLE part_lab.orders_default
PARTITION OF part_lab.orders
DEFAULT;
~~~

Lưu ý: từ `DEFAULT` ở đây thuộc **cú pháp khai báo partition**, hoàn toàn khác `DEFAULT 'new'` là giá trị mặc định của cột `status`.

## 5. RANGE: biên dưới bao gồm, biên trên loại trừ

Cú pháp:

~~~sql
FOR VALUES FROM (lower_bound) TO (upper_bound)
~~~

Trong phân vùng RANGE, quy tắc quan trọng là:

\[
\text{lower bound} \le \text{key} < \text{upper bound}
\]

Viết theo khoảng:

~~~text
[lower_bound, upper_bound)
 ^           ^
 gồm        không gồm
~~~

### 5.1. Kiểm tra các ngày biên

Partition tháng 1:

~~~sql
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
~~~

| order_date | Thuộc tháng 1? | Lý do |
| --- | --- | --- |
| `2025-12-31` | Không | Trước biên dưới |
| `2026-01-01` | Có | Biên dưới **được bao gồm** |
| `2026-01-15` | Có | Ở giữa khoảng |
| `2026-01-31` | Có | Nhỏ hơn 1/2 |
| `2026-02-01` | Không | Bằng biên trên, **bị loại** |

`2026-02-01` đi sang partition tháng 2, vì partition tháng 2 bắt đầu đúng ở ngày ấy.

### 5.2. Hai khoảng liên tiếp không chồng lấn

~~~text
Tháng 1: [2026-01-01, 2026-02-01)
Tháng 2: [2026-02-01, 2026-03-01)
~~~

Chúng **chạm nhau ở biên** nhưng không chứa cùng một giá trị ngày. Đây là thiết kế chuẩn để tránh chồng lấn hoặc bỏ sót.

### 5.3. Tại sao không ghi ngày cuối tháng?

Thay vì biên trên `2026-01-31`, nên dùng **ngày đầu tháng kế tiếp**. Nếu chọn:

~~~sql
FOR VALUES FROM ('2026-01-01') TO ('2026-01-31')
~~~

thì chính ngày `2026-01-31` bị **loại khỏi partition** vì biên trên không bao gồm.

### 5.4. Không phải mọi tháng đều có số ngày bằng nhau

~~~text
Tháng 2/2026: [2026-02-01, 2026-03-01)
Tháng 2/2028: [2028-02-01, 2028-03-01)
~~~

Năm 2028 có ngày nhuận; cách định nghĩa bằng **đầu tháng kế tiếp** vẫn đúng, không phải tự nhập “28 hoặc 29”.

## 6. Thực hành: xem hàng được định tuyến đi đâu

~~~sql
INSERT INTO part_lab.orders (
    order_id, order_date, customer_id,
    region, amount, status
) VALUES
    (101, '2026-01-01', 1, 'north', 100000, 'paid'),
    (102, '2026-01-31', 1, 'north', 150000, 'paid'),
    (103, '2026-02-01', 2, 'south', 200000, 'new'),
    (104, '2026-02-28', 3, 'central', 50000, 'paid'),
    (105, '2026-03-01', 4, 'north', 120000, 'new'),
    (106, '2025-12-31', 5, 'south', 80000, 'paid');
~~~

Trong ví dụ:

- `101` và `102` thuộc `orders_2026_01`.
- `103` và `104` thuộc `orders_2026_02`.
- `105` (tháng 3) và `106` (tháng 12 năm trước) thuộc `orders_default`.

### 6.1. Kiểm tra bằng tableoid

~~~sql
SELECT
    order_id,
    order_date,
    tableoid::regclass AS physical_partition
FROM part_lab.orders
ORDER BY order_date, order_id;
~~~

`tableoid` là system column chứa OID của quan hệ vật lý sở hữu tuple. Ép sang `regclass` giúp nhìn tên partition. Không nên dùng tên partition làm khóa nghiệp vụ bất biến — dữ liệu có thể được chuyển partition.

### 6.2. Đếm hàng theo partition

~~~sql
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS n_orders
FROM part_lab.orders
GROUP BY tableoid
ORDER BY physical_partition::text;
~~~

Dự kiến mỗi partition đang có **hai hàng** (tháng 1: 2; tháng 2: 2; DEFAULT: 2).

### 6.3. Đọc trực tiếp partition con

~~~sql
SELECT order_id, order_date
FROM part_lab.orders_2026_01
ORDER BY order_id;
~~~

Truy vấn partition con chỉ lấy các hàng **của chính quan hệ con đó**. Thông thường ứng dụng nên truy vấn bảng cha để PostgreSQL tự định tuyến/quét các partition cần thiết, thay vì tự ghép tên partition theo tháng trong từng câu SQL.

## 7. Nếu không có partition khớp và không có DEFAULT

Một bảng phân vùng có thể **không khai báo** DEFAULT:

~~~sql
CREATE TABLE part_lab.strict_events (
    event_id bigint NOT NULL,
    event_date date NOT NULL
) PARTITION BY RANGE (event_date);

CREATE TABLE part_lab.strict_events_jan
PARTITION OF part_lab.strict_events
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
~~~

Thử:

~~~sql
INSERT INTO part_lab.strict_events(event_id, event_date)
VALUES (1, '2026-02-15');
~~~

Vì chưa có partition cho tháng 2 và không có DEFAULT, PostgreSQL sẽ báo lỗi định tuyến kiểu:

~~~text
ERROR: no partition of relation "strict_events"
found for row
~~~

Không nên coi lỗi ấy là một “lỗi PostgreSQL lạ”. Nó cho thấy **giá trị khóa không nằm trong partition nào** mà bảng cha cho phép.

### 7.1. Lợi ích của việc không tạo DEFAULT

- Phát hiện sớm dữ liệu sai ngày/ngoài phạm vi.
- Buộc quy trình tạo partition tương lai hoạt động đúng.
- Không âm thầm gom hàng ngoài khoảng vào một nơi ngày càng lớn.

### 7.2. Đánh đổi

Nếu quên tạo partition cho ngày mới, `INSERT` có thể lỗi và gây sự cố nhận dữ liệu. Với hệ thống vận hành liên tục, cần **quy trình tạo partition trước thời điểm cần dùng**.

## 8. MINVALUE và MAXVALUE cho RANGE

PostgreSQL hỗ trợ các giá trị biên đặc biệt cho RANGE:

- `MINVALUE`: nhỏ hơn mọi giá trị thông thường của vị trí khóa tương ứng.
- `MAXVALUE`: lớn hơn mọi giá trị thông thường của vị trí khóa tương ứng.

Ví dụ trên một bảng khác để không đụng partitions đã tạo:

~~~sql
CREATE TABLE part_lab.measurements (
    measurement_id bigint NOT NULL,
    sample_date date NOT NULL,
    value numeric NOT NULL
) PARTITION BY RANGE (sample_date);

CREATE TABLE part_lab.measurements_before_2026
PARTITION OF part_lab.measurements
FOR VALUES FROM (MINVALUE) TO ('2026-01-01');

CREATE TABLE part_lab.measurements_2026
PARTITION OF part_lab.measurements
FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE part_lab.measurements_after_2026
PARTITION OF part_lab.measurements
FOR VALUES FROM ('2027-01-01') TO (MAXVALUE);
~~~

### 8.1. MINVALUE/MAXVALUE không phải ngày cụ thể

`MINVALUE` không có nghĩa `DATE '0001-01-01'`, và `MAXVALUE` không phải một giá trị ngày vô hạn để ứng dụng phải tự tạo. Chúng là **ký hiệu biên trong partition bound**.

### 8.2. Khóa NULL vẫn cần xem riêng

`MINVALUE`/`MAXVALUE` không làm cho `NULL` tự thuộc RANGE partition. `NULL` không phải một giá trị có thứ tự như date thông thường. Nếu partition key nullable và cần nhận NULL, xem phần DEFAULT/LIST bên dưới.

### 8.3. Khi nào dùng biên mở rộng?

Một partition `MINVALUE → 2026-01-01` hữu ích nếu cần giữ toàn bộ lịch sử cũ. Tuy nhiên, một partition “mọi dữ liệu trước 2026” có thể rất lớn, làm giảm lợi ích quản lý theo tháng; chọn granularity theo truy vấn/retention.

## 9. LIST partition: biên là các giá trị được liệt kê

Không phải mọi dữ liệu phù hợp khoảng liên tục. Với vùng địa lý hoặc loại nghiệp vụ, có thể dùng `LIST`.

~~~sql
CREATE TABLE part_lab.shipments (
    shipment_id bigint NOT NULL,
    region text,
    weight_kg numeric NOT NULL
) PARTITION BY LIST (region);

CREATE TABLE part_lab.shipments_north
PARTITION OF part_lab.shipments
FOR VALUES IN ('north', 'northeast');

CREATE TABLE part_lab.shipments_south
PARTITION OF part_lab.shipments
FOR VALUES IN ('south');

CREATE TABLE part_lab.shipments_default
PARTITION OF part_lab.shipments
DEFAULT;
~~~

### 9.1. Định tuyến LIST

~~~sql
INSERT INTO part_lab.shipments (
    shipment_id, region, weight_kg
) VALUES
    (1, 'north', 2.0),
    (2, 'northeast', 1.5),
    (3, 'south', 3.0),
    (4, 'central', 4.0),
    (5, NULL, 0.5);
~~~

| region | Partition |
| --- | --- |
| `north` | `shipments_north` |
| `northeast` | `shipments_north` |
| `south` | `shipments_south` |
| `central` | `shipments_default` |
| `NULL` | `shipments_default` trong cấu hình này |

### 9.2. Một giá trị không thể thuộc hai partition LIST

Không thể đồng thời khai báo `'north'` trong cả `shipments_north` và `shipments_south`. Các tập giá trị partition phải **không trùng nhau theo quy tắc so khớp của partitioning**.

### 9.3. LIST partition có thể nhận NULL tường minh

Ở một bảng LIST khác, PostgreSQL cho phép khai báo:

~~~sql
CREATE TABLE part_lab.labels (
    label_id bigint NOT NULL,
    label text
) PARTITION BY LIST (label);

CREATE TABLE part_lab.labels_missing
PARTITION OF part_lab.labels
FOR VALUES IN (NULL);

CREATE TABLE part_lab.labels_other
PARTITION OF part_lab.labels
DEFAULT;
~~~

Khi đó `label IS NULL` được định tuyến vào `labels_missing`, không vào DEFAULT.

### 9.4. LIST khác RANGE khi gặp NULL

LIST có thể **liệt kê NULL như một trường hợp đặc biệt**. RANGE không tạo khoảng thứ tự thông thường chứa NULL; nullable RANGE key cần xem đường DEFAULT hoặc bị từ chối nếu không có nơi chứa.

## 10. HASH partition: MODULUS và REMAINDER

Với khóa ID không có nhóm thời gian tự nhiên:

~~~sql
CREATE TABLE part_lab.activity (
    activity_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    event_kind text NOT NULL
) PARTITION BY HASH (customer_id);

CREATE TABLE part_lab.activity_p0
PARTITION OF part_lab.activity
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE part_lab.activity_p1
PARTITION OF part_lab.activity
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE part_lab.activity_p2
PARTITION OF part_lab.activity
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE part_lab.activity_p3
PARTITION OF part_lab.activity
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

### 10.1. Phân vùng HASH không dùng khoảng ngày

PostgreSQL tính hàm hash trên partition key và dùng quy tắc modulus/remainder để chọn partition. **Đừng tự cho rằng customer_id = 4 chắc chắn rơi vào p0** chỉ vì `4 % 4 = 0` — PostgreSQL dùng giá trị **hash của key**, không nhất thiết phần dư trực tiếp của ID.

### 10.2. Không có DEFAULT theo kiểu RANGE/LIST

`HASH` không hỗ trợ `DEFAULT partition`. Nếu tạo thiếu bucket, giá trị băm rơi vào bucket chưa khai báo có thể không có partition phù hợp và insert lỗi.

### 10.3. Các modulus phải tương thích

PostgreSQL cho phép một số cấu hình hash bounds với modulus khác nhau, nhưng có quy tắc về tính tương thích/chia hết để không tạo overlap. Trong lab đơn giản, dùng cùng `MODULUS 4` và đủ bốn remainder.

### 10.4. HASH không giúp truy vấn khoảng thời gian

~~~sql
WHERE event_time >= ...
~~~

nếu partition key chỉ là `customer_id`, PostgreSQL không thể tự loại hầu hết hash partitions dựa trên `event_time`. Chọn partition strategy theo **predicate thực tế**, không chỉ theo mong muốn phân phối tải.

## 11. Multi-column RANGE: so sánh theo bộ khóa

Một partitioned table có thể dùng nhiều khóa:

~~~sql
CREATE TABLE part_lab.coordinates (
    point_id integer NOT NULL,
    a integer NOT NULL,
    b integer NOT NULL
) PARTITION BY RANGE (a, b);

CREATE TABLE part_lab.coordinates_band
PARTITION OF part_lab.coordinates
FOR VALUES FROM (1, 10) TO (2, 20);

CREATE TABLE part_lab.coordinates_default
PARTITION OF part_lab.coordinates
DEFAULT;
~~~

**Không hiểu sai** biên này thành điều kiện:

~~~text
1 <= a < 2
AND
10 <= b < 20
~~~

PostgreSQL so sánh các **bộ giá trị theo thứ tự từ trái sang phải (lexicographic)**.

### 11.1. Minh họa

Khoảng `FROM (1,10) TO (2,20)` có nghĩa:

~~~text
(a,b) >= (1,10)
AND
(a,b) <  (2,20)
~~~

theo phép so sánh từ cột a rồi tới b.

| (a,b) | Thuộc partition? | Giải thích |
| --- | --- | --- |
| `(1,9)` | Không | Nhỏ hơn biên dưới |
| `(1,10)` | Có | Bằng biên dưới |
| `(1,999)` | Có | a=1 nhỏ hơn 2, dù b rất lớn |
| `(2,-100)` | Có | a=2, b=-100 nhỏ hơn 20 |
| `(2,19)` | Có | Nhỏ hơn biên trên |
| `(2,20)` | Không | Bằng biên trên |
| `(3,0)` | Không | Lớn hơn biên trên |

### 11.2. Thử định tuyến

~~~sql
INSERT INTO part_lab.coordinates(point_id, a, b)
VALUES
    (1, 1, 10),
    (2, 1, 999),
    (3, 2, -100),
    (4, 2, 20);

SELECT
    point_id,
    a,
    b,
    tableoid::regclass AS physical_partition
FROM part_lab.coordinates
ORDER BY point_id;
~~~

Ba hàng đầu thuộc `coordinates_band`; hàng thứ tư thuộc `coordinates_default`.

### 11.3. Vì sao composite range có thể gây bất ngờ?

Nếu ý định là “mỗi tenant có dải ngày riêng”, viết `PARTITION BY RANGE (tenant_id, order_date)` mà không hiểu lexicographic bounds có thể tạo các khoảng bao phủ nhiều tenant/ngày ngoài dự kiến.

Khi cần tách theo tenant **và sau đó theo tháng**, có thể cân nhắc **subpartitioning** hoặc một chiến lược cấu trúc khác, thay vì áp điều kiện hình chữ nhật lên RANGE nhiều cột.

## 12. Khóa phân vùng là cột hay biểu thức?

PostgreSQL hỗ trợ partition key là cột và, trong một số dạng phù hợp, **biểu thức**.

Ví dụ ý tưởng:

~~~sql
CREATE TABLE part_lab.telemetry (
    telemetry_id bigint NOT NULL,
    sensor_id text NOT NULL,
    reading numeric NOT NULL
) PARTITION BY LIST (lower(sensor_id));
~~~

Nếu dùng biểu thức làm khóa, cần quan tâm:

- Biểu thức có phù hợp yêu cầu của partition key hay không, gồm tính bất biến và kiểu trả về.
- Điều kiện query có thể dùng partition pruning hiệu quả hay không.
- Constraints `PRIMARY KEY`/`UNIQUE` trên bảng cha có thể bị giới hạn vì partition key chứa biểu thức.
- Mọi ứng dụng phải hiểu ngữ nghĩa chuẩn hóa khóa (ví dụ `lower`).

### 12.1. Không phải hàm nào cũng được dùng

Một biểu thức phụ thuộc thời gian hiện tại hoặc trạng thái phiên không phù hợp với cơ chế partitioning cần quy tắc định tuyến ổn định. Không thiết kế:

~~~sql
-- Sai hướng thiết kế: giá trị thay đổi theo thời gian hiện tại.
PARTITION BY RANGE (now())
~~~

### 12.2. Không nhất thiết dùng expression để chia theo tháng

Với cột `date` hoặc `timestamptz`, `PARTITION BY RANGE (created_at)` cùng các bound đầu tháng thường đơn giản hơn và có khả năng pruning tốt nếu query lọc bằng khoảng trực tiếp.

### 12.3. Quy tắc với PRIMARY KEY/UNIQUE

Với declarative partitioned table, constraint duy nhất ở bảng cha có những yêu cầu riêng về partition key. Nếu dùng expression key, không thể giả định mọi `PRIMARY KEY`/`UNIQUE` ở mức cha vẫn được hỗ trợ như khi khóa phân vùng là các cột đơn giản.

## 13. DEFAULT partition nhận những giá trị nào?

Một partition `DEFAULT` nhận các giá trị khóa **không thuộc bất kỳ partition được khai báo rõ nào khác**.

~~~sql
CREATE TABLE part_lab.orders_default
PARTITION OF part_lab.orders
DEFAULT;
~~~

Trong lab hiện tại, DEFAULT có thể nhận:

- Ngày trước `2026-01-01`.
- Ngày từ `2026-03-01` trở đi, vì mới tạo riêng tháng 1 và tháng 2.
- Không nhận `NULL` trong `orders`, vì cột `order_date` đã `NOT NULL`.

### 13.1. DEFAULT không phải “partition cho NULL” riêng

DEFAULT là **phần bù của mọi partition tường minh**, không chỉ nơi chứa null. Với nullable RANGE key, NULL có thể được định tuyến vào DEFAULT nếu không bị constraint ngăn; với LIST, NULL có thể đã được chỉ định cho partition `FOR VALUES IN (NULL)`.

### 13.2. Chỉ một DEFAULT cho mỗi cấp partitioned table

Không thể tạo hai DEFAULT partitions cùng làm “catch-all” ở cùng cấp cho một bảng cha. Nếu cần phân nhóm dữ liệu lỗi/không biết, hãy chủ động tổ chức schema và cơ chế vận hành thay vì chờ nhiều DEFAULT cùng cấp.

### 13.3. DEFAULT là cơ chế an toàn hay rủi ro?

**Ưu điểm:** ứng dụng có thể tiếp tục nhận dữ liệu khi một giá trị chưa được dự liệu (nếu mọi constraint khác đều hợp lệ).

**Rủi ro:** lỗi tạo partition theo lịch có thể không làm INSERT lỗi; dữ liệu âm thầm dồn vào DEFAULT, gây tăng dung lượng, chậm query và làm khó quá trình tách lại về đúng partition.

## 14. Kiểm tra dữ liệu nằm trong DEFAULT

~~~sql
SELECT
    COUNT(*) AS rows_in_default,
    MIN(order_date) AS earliest_date,
    MAX(order_date) AS latest_date
FROM part_lab.orders_default;
~~~

Với dữ liệu mẫu ban đầu: `rows_in_default=2`, min là `2025-12-31` và max là `2026-03-01`.

### 14.1. Nhóm theo tháng để biết khoảng nào thiếu

~~~sql
SELECT
    date_trunc('month', order_date::timestamp)::date
        AS month_start,
    COUNT(*) AS n_orders
FROM part_lab.orders_default
GROUP BY 1
ORDER BY 1;
~~~

Đây là truy vấn **quan sát dữ liệu DEFAULT**, không phải predicate dùng cho partition pruning trên bảng cha. Có thể thấy nhiều tháng bị bỏ quên trong quá trình provisioning.

### 14.2. Theo dõi tỷ trọng DEFAULT

~~~sql
WITH counts AS (
    SELECT
        (SELECT COUNT(*) FROM part_lab.orders) AS all_rows,
        (SELECT COUNT(*) FROM part_lab.orders_default)
            AS default_rows
)
SELECT
    all_rows,
    default_rows,
    ROUND(
        100.0 * default_rows / NULLIF(all_rows, 0), 2
    ) AS default_pct
FROM counts;
~~~

Trên hệ thống thật, việc chạy `COUNT(*)` quá thường xuyên có thể tốn tài nguyên. Có thể dùng monitoring/ước lượng theo chính sách vận hành; khi cần con số chính xác mới chạy count trên dữ liệu tương ứng.

### 14.3. Một hàng sai ngày vẫn có thể hợp lệ về kiểu

`DATE '2036-01-01'` là ngày hợp lệ, nhưng có thể là **lỗi dữ liệu nghiệp vụ**. DEFAULT không tự biết ngày đó là bất thường. Ứng dụng/constraint cần xác nhận giới hạn nghiệp vụ.

## 15. Điều gì xảy ra khi thêm partition mới có DEFAULT?

Trong lab, hàng:

~~~text
order_id=105, order_date=2026-03-01
~~~

đã nằm ở `orders_default`.

Bây giờ nếu thử:

~~~sql
CREATE TABLE part_lab.orders_2026_03
PARTITION OF part_lab.orders
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
~~~

PostgreSQL phải thay đổi phạm vi của DEFAULT để nó **không còn chứa các hàng tháng 3**. Nhưng hiện tại DEFAULT đang có hàng ngày `2026-03-01`. Thao tác có thể thất bại vì ràng buộc partition/default không còn thỏa.

### 15.1. Tại sao database không tự di chuyển hàng?

Định nghĩa partition mới là thao tác metadata/DDL kèm kiểm tra điều kiện, **không phải một lệnh tự động di chuyển toàn bộ dữ liệu từ DEFAULT sang partition mới**.

Nếu dữ liệu ngoài phạm vi đã bị gom vào DEFAULT, bạn phải lập kế hoạch di chuyển và kiểm soát concurrent writes.

### 15.2. Vì sao cần xử lý giao dịch đồng thời?

Giả sử bạn:

1. Copy hàng tháng 3 khỏi DEFAULT.
2. Xóa hàng tháng 3 khỏi DEFAULT.
3. Attach partition tháng 3.

Nếu trong khoảng giữa một transaction khác lại `INSERT` hàng tháng 3 vào DEFAULT, thao tác attach có thể thất bại hoặc dữ liệu cần di chuyển thay đổi. Vì vậy cần **transaction và khóa/chiến lược đồng bộ phù hợp**, không chạy thủ công từng bước ở autocommit rồi hy vọng không có người ghi mới.

## 16. Quy trình lab: di chuyển dữ liệu DEFAULT và ATTACH PARTITION

Đây là mẫu học tập với **khóa mạnh và transaction ngắn** để minh họa tính nguyên tử. Không sao chép nguyên xi lên bảng lớn đang phục vụ production, vì khóa bảng có thể chặn cả đọc/ghi trong thời gian đáng kể.

### 16.1. Mục tiêu

Sau khi hoàn thành:

~~~text
orders_2026_01  -> tháng 1
orders_2026_02  -> tháng 2
orders_2026_03  -> tháng 3
orders_default  -> trước tháng 1 và từ tháng 4 trở đi
~~~

Và hàng `order_id=105` sẽ ở `orders_2026_03`.

### 16.2. Thao tác trong một transaction

~~~sql
BEGIN;

-- Lab: khóa mạnh để tránh thay đổi concurrent trong lúc chuyển.
LOCK TABLE part_lab.orders
IN ACCESS EXCLUSIVE MODE;

-- Tạo bảng riêng chưa attach, có các cột/default/constraint cần thiết.
CREATE TABLE part_lab.orders_2026_03 (
    LIKE part_lab.orders INCLUDING DEFAULTS INCLUDING CONSTRAINTS
);

-- Xác nhận mọi hàng đưa vào bảng này đều thuộc tháng 3.
ALTER TABLE part_lab.orders_2026_03
ADD CONSTRAINT orders_2026_03_date_check
CHECK (
    order_date >= DATE '2026-03-01'
    AND order_date < DATE '2026-04-01'
);

-- Chuyển các hàng tháng 3 sang bảng tạm làm partition tương lai.
INSERT INTO part_lab.orders_2026_03 (
    order_id, order_date, customer_id,
    region, amount, status
)
SELECT
    order_id, order_date, customer_id,
    region, amount, status
FROM part_lab.orders_default
WHERE order_date >= DATE '2026-03-01'
  AND order_date < DATE '2026-04-01';

-- Xóa bản gốc khỏi DEFAULT trong cùng transaction.
DELETE FROM part_lab.orders_default
WHERE order_date >= DATE '2026-03-01'
  AND order_date < DATE '2026-04-01';

-- Gắn bảng đã chứa đúng tập hàng làm partition chính thức.
ALTER TABLE part_lab.orders
ATTACH PARTITION part_lab.orders_2026_03
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

COMMIT;
~~~

**Đây là quy trình lab**, cố ý khóa mạnh để dễ hiểu atomicity. Với bảng production rất lớn, quy trình thật cần nghiên cứu thời gian copy, locking, WAL, constraints, index, foreign keys, replication lag và kiểm soát ghi trước khi chọn chiến lược online/batch.

### 16.3. Vì sao dùng bảng standalone trước ATTACH?

`CREATE TABLE ... PARTITION OF` khi DEFAULT đã chứa giá trị trong bound mới có thể bị từ chối. Với bảng standalone, bạn có thể kiểm tra/di chuyển dữ liệu rồi **ATTACH** sau khi DEFAULT không còn hàng xung đột.

### 16.4. CHECK constraint của bảng mới

Ràng buộc:

~~~sql
CHECK (
    order_date >= DATE '2026-03-01'
    AND order_date < DATE '2026-04-01'
)
~~~

giúp chứng minh dữ liệu bảng mới thuộc khoảng dự kiến. Vì `order_date NOT NULL` có ở bảng này, không có trường hợp NULL làm điều kiện CHECK trở thành unknown.

Ở một số trường hợp, constraint phù hợp được PostgreSQL dùng để tránh phải scan bảng mới khi `ATTACH PARTITION`. Tuy nhiên, **việc kiểm tra DEFAULT và locking vẫn cần được xem xét riêng**.

### 16.5. Tại sao dùng khóa ACCESS EXCLUSIVE trong lab?

Chúng ta cần ngăn những transaction khác chèn/sửa hàng qua bảng cha hoặc partitions trong lúc chuyển. Cách khóa này đơn giản về mặt giảng dạy nhưng **rất xâm lấn**; nó có thể chặn cả `SELECT` thông thường trong thời gian transaction mở.

Ở production, cần lên lịch và chọn thiết kế ít khóa hơn hoặc maintenance window theo tình huống, không áp khóa mạnh mặc định.

### 16.6. Nếu một bước thất bại thì sao?

Vì DDL/DML liên quan nằm trong một transaction PostgreSQL phù hợp, `ROLLBACK` sẽ hủy những thay đổi transactional chưa commit của quy trình. Sau lỗi trong transaction, hãy rollback rõ ràng thay vì tiếp tục các câu SQL khi transaction đã ở trạng thái aborted.

### 16.7. Xác minh sau commit

~~~sql
SELECT
    order_id,
    order_date,
    tableoid::regclass AS physical_partition
FROM part_lab.orders
ORDER BY order_id;

SELECT COUNT(*) AS march_rows
FROM part_lab.orders_2026_03;

SELECT COUNT(*) AS remaining_march_in_default
FROM part_lab.orders_default
WHERE order_date >= DATE '2026-03-01'
  AND order_date < DATE '2026-04-01';
~~~

Mong đợi hàng `105` nằm trong `orders_2026_03`; DEFAULT không còn hàng tháng 3.

## 17. Những lưu ý khi ATTACH PARTITION

`ALTER TABLE ... ATTACH PARTITION` gắn một bảng đã tồn tại vào cây partition theo bound mới.

### 17.1. Schema phải tương thích

Bảng gắn vào phải có cấu trúc cột, kiểu, constraint và những đặc tính cần thiết phù hợp bảng cha. Không tự cho rằng bảng staging tùy ý có thể attach mà PostgreSQL sẽ âm thầm sửa mọi cột.

### 17.2. Mọi hàng phải đúng bound

Nếu bảng staging chứa `order_date='2026-04-01'` nhưng attach với `TO ('2026-04-01')`, nó **không thỏa** bound vì biên trên bị loại. PostgreSQL phải xác minh/đòi dữ liệu đúng, hoặc từ chối thao tác.

### 17.3. Bảng không có CHECK phù hợp có thể cần scan

Khi bảng tồn tại sẵn đã chứa dữ liệu, PostgreSQL có thể scan để kiểm tra không có hàng ngoài bound. Một `CHECK` đã validated với predicate tương ứng có thể giúp tránh scan theo điều kiện được PostgreSQL chứng minh.

### 17.4. DEFAULT cũng có thể phải scan

Khi mở một khoảng partition mới, DEFAULT cần được xác minh không chứa hàng khớp khoảng đó. Nếu DEFAULT rất lớn và không có constraint phù hợp để chứng minh, thao tác có thể scan DEFAULT và gây khóa/chờ đáng kể.

### 17.5. CREATE PARTITION và ATTACH có khóa khác nhau

`CREATE TABLE ... PARTITION OF` và `ALTER TABLE ... ATTACH PARTITION` có thể lấy các mode khóa khác nhau trên parent/child/default. `ATTACH` thường giúp giảm mức khóa parent trong một số trường hợp, nhưng vẫn cần kiểm tra và khóa các quan hệ liên quan. Không mô tả nó là **hoàn toàn online, không khóa**.

### 17.6. Index và constraints

Partitioned indexes/constraints của bảng cha cần được bảo đảm trên partition mới theo quy tắc PostgreSQL. Với bảng lớn, việc tạo/kiểm tra các index cần thiết có thể tốn tài nguyên; lên kế hoạch thay vì assume `ATTACH` luôn tức thì.

### 17.7. Quy trình production cần tính cả concurrent writes

Khi dữ liệu vẫn được ghi liên tục, hãy xác định:

- Có thể khóa các đường ghi trong cửa sổ chuyển không?
- Có thể chuyển dữ liệu từng lô rồi khóa trong khoảng rất ngắn để hoàn tất không?
- Có transaction đang mở lâu giữ snapshot/locks không?
- Có replication/CDC/trigger nào phụ thuộc vào việc thay partition không?
- Có cần rollback hoặc retry nếu attach gặp xung đột?

Đừng cố “migrate online” chỉ bằng ba statement độc lập rồi để mặc race condition.

## 18. Sau khi có tháng 3, định tuyến thay đổi

Thử:

~~~sql
INSERT INTO part_lab.orders (
    order_id, order_date, customer_id,
    region, amount, status
) VALUES
    (107, '2026-03-20', 6, 'central', 350000, 'paid'),
    (108, '2026-04-01', 7, 'north', 90000, 'new');
~~~

Kỳ vọng:

- `107` thuộc `orders_2026_03`.
- `108` thuộc `orders_default` vì tháng 4 chưa có partition riêng.

~~~sql
SELECT
    order_id,
    order_date,
    tableoid::regclass AS physical_partition
FROM part_lab.orders
WHERE order_id IN (107, 108)
ORDER BY order_id;
~~~

### 18.1. Hãy tạo partition tương lai trước khi dữ liệu xuất hiện

Trong vận hành, nếu bạn tạo partition tháng 4 **trước ngày 1/4**, hàng tháng 4 được định tuyến đúng ngay từ đầu, giảm nhu cầu di chuyển lại từ DEFAULT.

### 18.2. DEFAULT không phải hàng đợi tự dọn

PostgreSQL **không tự chuyển hàng từ DEFAULT sang partition mới trong nền** khi bạn tạo hoặc attach một partition. Phải có quy trình vận hành để nhận diện, di chuyển và xác minh dữ liệu.

## 19. Khóa phân vùng có thể là NULL không?

Điều này phụ thuộc chiến lược, schema và các constraints.

### 19.1. RANGE partition với nullable key

~~~sql
CREATE TABLE part_lab.optional_dates (
    item_id integer NOT NULL,
    event_date date
) PARTITION BY RANGE (event_date);

CREATE TABLE part_lab.optional_dates_2026
PARTITION OF part_lab.optional_dates
FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE part_lab.optional_dates_default
PARTITION OF part_lab.optional_dates
DEFAULT;
~~~

Với cấu hình này, một hàng `event_date IS NULL` không thuộc khoảng RANGE tường minh và có thể vào DEFAULT.

~~~sql
INSERT INTO part_lab.optional_dates(item_id, event_date)
VALUES (1, NULL);

SELECT
    item_id,
    tableoid::regclass AS physical_partition
FROM part_lab.optional_dates;
~~~

### 19.2. NOT NULL ngăn đưa NULL vào DEFAULT

Trong bảng `part_lab.orders`, `order_date NOT NULL` ngăn giá trị NULL. Có DEFAULT cũng không vượt qua được constraint `NOT NULL`.

### 19.3. LIST có thể dành riêng partition cho NULL

Đã minh họa `FOR VALUES IN (NULL)`. Khi có partition như vậy, NULL vào partition tường minh đó, còn DEFAULT chứa những giá trị khác chưa được liệt kê.

### 19.4. HASH với nullable key

Nếu cột HASH key cho phép NULL, PostgreSQL vẫn có ngữ nghĩa hash/routing cho khóa ấy và không dựa trên một DEFAULT partition. Nhưng cân nhắc tính đúng nghiệp vụ, tính phân bố dữ liệu và constraints trước khi cho phép khóa null.

## 20. Trùng lặp biên và khoảng bị bỏ trống

PostgreSQL không cho các partitions cùng cấp có bounds chồng lấn.

### 20.1. Trùng khoảng là lỗi

Khi đã có:

~~~sql
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
~~~

thì không thể thêm một partition khác cùng cha:

~~~sql
-- Ví dụ cố ý có overlap, không chạy như migration.
FOR VALUES FROM ('2026-01-15') TO ('2026-02-15')
~~~

vì khoảng giao nhau từ ngày 15/1 tới trước 1/2.

### 20.2. Chạm biên đúng là hợp lệ

~~~text
[2026-01-01, 2026-02-01)
[2026-02-01, 2026-03-01)
~~~

Hai khoảng **không overlap**.

### 20.3. Khoảng trống vẫn có thể tồn tại

~~~text
[2026-01-01, 2026-02-01)
[2026-03-01, 2026-04-01)
~~~

Tháng 2 là **gap**. Nếu có DEFAULT, hàng tháng 2 vào DEFAULT; nếu không, chèn tháng 2 lỗi.

### 20.4. Không chỉ kiểm tra tính hợp lệ cú pháp

PostgreSQL sẽ ngăn các partition bounds không hợp lệ, nhưng không thể biết mục tiêu vận hành của bạn là “mỗi tháng có đúng một partition”. Cần công cụ/lịch tạo partition và kiểm tra **coverage** theo lịch nghiệp vụ.

## 21. Khóa chính và UNIQUE trên partitioned table

Đây là chủ đề dễ bỏ sót khi chọn partition key.

### 21.1. Vì sao PRIMARY KEY cần partition key?

Với bảng:

~~~sql
CREATE TABLE part_lab.orders (
    order_id bigint NOT NULL,
    order_date date NOT NULL,
    ...
    PRIMARY KEY (order_id, order_date)
) PARTITION BY RANGE (order_date);
~~~

Mỗi partition có thể có index riêng để enforce uniqueness trên phần dữ liệu của nó. PostgreSQL không sử dụng một **global unique index độc lập bao trùm mọi partitions** như một số hệ thống khác.

Để một constraint UNIQUE/PRIMARY KEY cấp cha có thể đảm bảo tính duy nhất trên toàn bảng qua các partition, key phải chứa tất cả cột của partition key theo quy tắc PostgreSQL.

### 21.2. Tại sao PRIMARY KEY(order_id) không được chấp nhận ở bảng này?

Một `order_id=100` ở tháng 1 và `order_id=100` ở tháng 2 có thể nằm trên hai partition riêng. Index cục bộ theo `order_id` sẽ không tự phát hiện giá trị trùng ở partition kia.

Vì vậy:

~~~sql
-- Không hợp lệ như PRIMARY KEY cấp cha
-- đối với PARTITION BY RANGE(order_date):
PRIMARY KEY (order_id)
~~~

### 21.3. Composite PK không đồng nghĩa order_id duy nhất

~~~sql
INSERT INTO part_lab.orders (
    order_id, order_date, customer_id,
    region, amount, status
) VALUES
    (999, '2026-01-10', 1, 'north', 10000, 'paid'),
    (999, '2026-02-10', 1, 'north', 10000, 'paid');
~~~

Hai hàng này có **cặp (order_id, order_date) khác nhau** nên không vi phạm composite PK. Tuy nhiên, nếu ứng dụng xác định đơn **chỉ bằng order_id**, đây có thể là thiết kế sai nghiệp vụ.

### 21.4. Lựa chọn khi cần order_id duy nhất toàn cục

Tùy yêu cầu:

1. Thiết kế khóa nghiệp vụ gồm partition key, ví dụ mỗi đơn được nhận diện bởi cặp ID+ngày.
2. Dùng cơ chế cấp ID có tính duy nhất trên toàn hệ thống (sequence/UUID) cùng các quy tắc ứng dụng phù hợp — nhưng **bản thân sequence không phải một UNIQUE constraint toàn cục**, và ID tự sinh không ngăn mọi insert thủ công/trùng do lỗi.
3. Duy trì một bảng định danh không phân vùng có `UNIQUE(order_id)` và tham chiếu/thiết kế transaction phù hợp khi cần enforcement ở DB.
4. Cân nhắc lại partition key hoặc cả việc phân vùng nếu global uniqueness là bất biến quan trọng.

Không tuyên bố composite PK đã giải quyết đầy đủ nhu cầu `order_id` duy nhất nếu điều đó không nằm trong constraint.

### 21.5. Partition key chứa expression

PostgreSQL có giới hạn bổ sung với UNIQUE/PRIMARY KEY cấp cha khi partition key chứa biểu thức hoặc function call. Hãy kiểm tra thiết kế PK trước khi chọn một expression partition key.

## 22. Indexes trên bảng phân vùng

Index định nghĩa ở bảng cha là dạng **partitioned index**, còn mỗi partition cần cấu trúc index vật lý tương ứng.

~~~sql
CREATE INDEX idx_orders_customer_date
ON part_lab.orders (customer_id, order_date DESC);
~~~

PostgreSQL tạo/quản lý các index tương ứng trên partitions theo cơ chế hỗ trợ.

### 22.1. Pruning khác index scan

Một truy vấn:

~~~sql
SELECT order_id, amount
FROM part_lab.orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01'
  AND customer_id = 2;
~~~

được hưởng lợi từ **hai quyết định riêng**:

1. Partition pruning có thể loại tháng 1, tháng 3 và DEFAULT không liên quan.
2. Trong partition tháng 2, PostgreSQL chọn `Seq Scan` hoặc `Index Scan` dựa trên dữ liệu và index.

Partition pruning **không đảm bảo luôn Index Scan**.

### 22.2. Không tạo index thừa trên mọi cột

Số partition nhiều khiến một index mới trên parent có thể kéo theo nhiều child indexes, thêm dung lượng và chi phí DML. Thiết kế từ query pattern và tính chọn lọc thật.

### 22.3. Index không tự giải quyết thiếu bound

Một index trên `order_date` không thể giúp INSERT ngày tháng 4 thành công nếu không có partition phù hợp và cũng không có DEFAULT. Đó là **lỗi định tuyến**, không phải lỗi tìm kiếm.

## 23. Partition pruning dựa trên khóa và biên

**Partition pruning** là khả năng PostgreSQL bỏ qua các partition không thể chứa hàng phù hợp với điều kiện query.

~~~sql
EXPLAIN
SELECT order_id, amount
FROM part_lab.orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01';
~~~

Từ các bounds:

~~~text
Jan: [2026-01-01, 2026-02-01)
Feb: [2026-02-01, 2026-03-01)
Mar: [2026-03-01, 2026-04-01)
Default: phần còn lại
~~~

planner có thể thấy rằng **chỉ partition tháng 2** thỏa điều kiện ngày trong ví dụ.

### 23.1. EXPLAIN có thể không hiện Append

Nếu pruning ở planning time loại hết chỉ trừ một partition, plan có thể chỉ hiện một scan trên `orders_2026_02` mà **không có Append nhiều con**.

### 23.2. Pruning không phải lọc toàn bộ rồi chọn tháng

Khi partition có bound loại trừ được từ trước, PostgreSQL có thể **không scan** những partition đó, khác với việc scan tất cả rồi Filter ở cuối.

### 23.3. Tham số và runtime pruning

~~~sql
PREPARE find_by_date(date, date) AS
SELECT order_id, amount
FROM part_lab.orders
WHERE order_date >= $1
  AND order_date < $2;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_by_date('2026-02-01', '2026-03-01');
~~~

Tùy plan và giá trị được biết khi lập kế hoạch, PostgreSQL có thể prune ở **planning time**, **executor initialization** hoặc trong những pha thực thi phù hợp. Một số plan thể hiện `Subplans Removed` hay node `never executed`. Không bắt mọi output phải có một dòng cố định giống nhau.

### 23.4. Hiểu tình huống DEFAULT

DEFAULT có ràng buộc ngầm là **không thuộc các bounds đã khai báo**. Khi query chỉ tìm trong tháng 2 đã có partition, PostgreSQL có thể loại DEFAULT khỏi đường scan nhờ thông tin bound.

Nhưng nếu query tìm **tháng 4** chưa có partition riêng, DEFAULT có thể là nơi duy nhất chứa hàng phù hợp và có thể phải scan/index tại đó.

## 24. Viết predicate để pruning hiệu quả

Điều kiện trực tiếp trên partition key thường dễ suy luận:

~~~sql
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01'
~~~

### 24.1. Tránh biến đổi làm khó chứng minh khoảng

~~~sql
WHERE EXTRACT(YEAR FROM order_date) = 2026
~~~

Không có cùng dạng điều kiện trực tiếp trên partition key như khoảng ngày. Planner có thể không suy ra chính xác tập partition cần xem theo biểu thức này.

Với nhu cầu cả năm 2026, cách rõ ràng hơn:

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date < DATE '2027-01-01'
~~~

### 24.2. Không thay đổi ngữ nghĩa timezone

Nếu khóa là `timestamptz`, các biên đầu tháng phụ thuộc mốc thời gian cụ thể (ví dụ UTC). Một tháng theo múi giờ địa phương có thể có ranh giới UTC khác; khi vùng có DST, độ dài ngày cũng có thể thay đổi.

### 24.3. Pruning dựa trên kiểu và toán tử phù hợp

Ép kiểu, collation, function trên partition key hoặc các predicate phức tạp có thể khiến pruning khó hơn. Xem `EXPLAIN` với truy vấn thực, không suy từ tên cột.

### 24.4. Query không lọc partition key có thể đọc mọi partition

~~~sql
SELECT order_id, amount
FROM part_lab.orders
WHERE customer_id = 42;
~~~

Vì parent partition theo ngày, nếu query không có thông tin đủ để suy bound ngày thì PostgreSQL có thể cần xem **nhiều partitions**. Chỉ mục `customer_id` trên từng partition vẫn có thể hữu ích, nhưng không biến nó thành một global index có thể nhảy tới đúng partition theo customer ID mà không biết ngày.

## 25. Cập nhật khóa phân vùng: row movement

PostgreSQL có thể xử lý `UPDATE` làm đổi partition key bằng cách **chuyển hàng sang partition phù hợp** trong các điều kiện được hỗ trợ:

~~~sql
BEGIN;

UPDATE part_lab.orders
SET order_date = DATE '2026-02-15'
WHERE order_id = 101
  AND order_date = DATE '2026-01-01';

SELECT
    order_id,
    order_date,
    tableoid::regclass AS physical_partition
FROM part_lab.orders
WHERE order_id = 101;

ROLLBACK;
~~~

Trong transaction, hàng `101` có thể xuất hiện ở `orders_2026_02`. Sau `ROLLBACK`, nó vẫn thuộc partition tháng 1 như ban đầu.

### 25.1. UPDATE làm đổi khóa không đơn giản như sửa cột bình thường

Row movement liên quan thao tác di chuyển giữa partitions, các constraints, triggers và cạnh tranh transaction. Ứng dụng không nên cập nhật khóa ngày thường xuyên nếu nó được dùng để định tuyến/retention.

### 25.2. Đích không tồn tại

Nếu đổi `order_date` sang một giá trị không khớp partition nào và không có DEFAULT, câu `UPDATE` có thể thất bại vì không có nơi đặt hàng.

### 25.3. Khóa chính ghép thay đổi

Trong lab, `PRIMARY KEY (order_id, order_date)` bao gồm ngày. Việc đổi ngày cũng đổi giá trị khóa chính logic; mọi foreign key tham chiếu tới composite key hoặc quy tắc nghiệp vụ liên quan cần được xem xét cẩn thận.

### 25.4. Không dựa vào tableoid làm ID lâu dài

`tableoid` chỉ cho biết hàng hiện ở quan hệ vật lý nào. Sau row movement, DETACH/ATTACH hoặc migration, thông tin ấy có thể thay đổi dù ứng dụng coi đó vẫn là đơn hàng cũ.

## 26. Dữ liệu cũ và chính sách retention

Một ưu điểm thường gặp của partition theo thời gian là quản lý vòng đời dữ liệu theo dải.

Ví dụ, khi chính sách cho phép xóa dữ liệu tháng 1/2026, bạn có thể quản lý riêng partition `orders_2026_01` thay vì chạy một `DELETE` rất lớn trên toàn bộ bảng.

### 26.1. DETACH PARTITION

~~~sql
-- Minh họa cú pháp; không chạy nếu lab còn cần tháng 1.
ALTER TABLE part_lab.orders
DETACH PARTITION part_lab.orders_2026_01;
~~~

Sau khi detach, bảng con vẫn có thể tồn tại như bảng độc lập, nhưng không còn thuộc đường truy vấn của parent.

### 26.2. DROP partition

~~~sql
-- Minh họa thao tác phá hủy dữ liệu; KHÔNG thực thi tùy tiện.
DROP TABLE part_lab.orders_2026_01;
~~~

Việc drop một partition chứa dữ liệu có thể xóa toàn bộ dữ liệu trong partition ấy. Cần backup/retention approvals, kiểm tra foreign keys và yêu cầu lưu trữ trước khi làm.

### 26.3. DEFAULT không thay retention windows

Nếu hàng cũ nằm trong DEFAULT cùng với hàng mới chưa có partition, không thể đơn giản drop DEFAULT để chỉ xóa dữ liệu cũ. DEFAULT có thể chứa nhiều tháng và loại giá trị khác nhau.

Đây là một lý do vận hành **không để DEFAULT tăng không kiểm soát**.

### 26.4. DETACH CONCURRENTLY có điều kiện riêng

PostgreSQL hiện đại hỗ trợ một số biến thể detach concurrent với hạn chế về transaction block, DEFAULT và trạng thái hệ thống. Không đưa lệnh concurrent vào migration được bọc transaction nếu chưa kiểm tra đầy đủ các điều kiện của phiên bản đang dùng.

## 27. Phân vùng con: subpartitioning

Một partition có thể tiếp tục là partitioned table, ví dụ chia trước theo năm rồi dưới mỗi năm theo tháng:

~~~text
parent: RANGE(order_date)
  |
  +-- year_2026: RANGE(order_date)
  |     +-- jan_2026
  |     +-- feb_2026
  |     +-- ...
  |
  +-- year_2027: RANGE(order_date)
        +-- jan_2027
        +-- ...
~~~

### 27.1. Mỗi cấp có bounds riêng

Một hàng phải thỏa **bound của mọi cấp tổ tiên** trong đường định tuyến. Việc tạo subpartition với khoảng vượt bound partition cha có thể dẫn đến lỗi/giới hạn hoặc không có dữ liệu nào hợp lệ ở phần vượt.

### 27.2. DEFAULT theo từng cấp

DEFAULT của một cấp là phần bù của các bounds **ở cấp đó**, không phải một “kho toàn cục” vượt mọi cấp phân vùng.

### 27.3. Không phân nhiều cấp chỉ để phức tạp

Thêm tầng partition làm tăng metadata, số đối tượng, planning/maintenance overhead và độ phức tạp migration. Chọn khi workload/retention và khối lượng dữ liệu có lý do rõ ràng.

## 28. Quan sát cấu trúc partition bằng catalog

PostgreSQL có các hàm/catalog để xem partition tree.

### 28.1. pg_partition_tree

~~~sql
SELECT
    relid::regclass AS partition,
    parentrelid::regclass AS parent,
    isleaf,
    level
FROM pg_partition_tree('part_lab.orders'::regclass)
ORDER BY level, relid::regclass::text;
~~~

`level=0` là parent gốc; `isleaf=true` cho biết leaf partition.

### 28.2. Xem biểu thức bound của partition con

~~~sql
SELECT
    c.oid::regclass AS partition_name,
    pg_get_expr(c.relpartbound, c.oid) AS partition_bound
FROM pg_class AS c
JOIN pg_inherits AS i
    ON i.inhrelid = c.oid
WHERE i.inhparent = 'part_lab.orders'::regclass
ORDER BY c.oid::regclass::text;
~~~

Kết quả `partition_bound` có thể cho thấy:

~~~text
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01')
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01')
DEFAULT
~~~

### 28.3. Xem partition key

~~~sql
SELECT
    c.oid::regclass AS parent_table,
    pg_get_partkeydef(c.oid) AS partition_key
FROM pg_class AS c
WHERE c.oid = 'part_lab.orders'::regclass;
~~~

Kỳ vọng: `RANGE (order_date)`.

### 28.4. pg_inherits và declarative partitions

`pg_inherits` lưu mối quan hệ cha/con dùng cho partition hierarchy và những dạng inheritance khác. Đừng chỉ thấy một hàng trong `pg_inherits` rồi giả định mọi bảng con đều là declarative partition có bound; dùng kết hợp `pg_class.relpartbound` và `pg_partition_tree` khi phù hợp.

### 28.5. tableoid để xem nơi lưu hàng

~~~sql
SELECT
    tableoid::regclass AS partition,
    COUNT(*) AS rows_count
FROM part_lab.orders
GROUP BY tableoid
ORDER BY partition::text;
~~~

Catalog mô tả **cấu trúc**; `tableoid` của các hàng cho biết **định tuyến dữ liệu hiện tại**.

## 29. EXPLAIN và chi phí khi có nhiều partitions

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, order_date, amount
FROM part_lab.orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01';
~~~

Các câu hỏi cần quan sát:

1. Plan có những partition nào?
2. Có scan `orders_default` không?
3. Có `Append` hay chỉ một scan?
4. Node nào dùng `Seq Scan` và node nào có `Index Cond`?
5. `Buffers: shared hit/read` thuộc các quan hệ đã truy cập là bao nhiêu?

### 29.1. EXPLAIN không phải EXPLAIN ANALYZE

~~~sql
EXPLAIN SELECT ...;
~~~

chỉ lập plan.

~~~sql
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;
~~~

thực thi truy vấn để đo rows, time và buffers. Với các lệnh sửa dữ liệu, `EXPLAIN ANALYZE` thực thi thật; không dùng trên production DML nếu không kiểm soát ảnh hưởng.

### 29.2. Pruning hiệu quả không có nghĩa latency luôn tốt

Một partition tháng có thể còn hàng chục triệu hàng. Dù pruning chỉ để lại một partition, query vẫn có thể rất chậm nếu thiếu index phù hợp hoặc phải sort nhiều.

### 29.3. Quá nhiều partitions có chi phí

Hàng nghìn partitions có thể tăng chi phí metadata, planning, autovacuum, catalog và quản lý migration. Pruning giúp loại partition không liên quan, nhưng không làm số partition lớn trở thành miễn phí.

## 30. Quản lý partition theo lịch

Với bảng RANGE theo tháng, quy trình vận hành thường có một lịch **tạo partition trước**.

### 30.1. Ví dụ khung vận hành

~~~text
Ngày 20 hằng tháng:
  1. Xác định các tháng sắp tới chưa có partition.
  2. Tạo trước partition của tháng kế tiếp/vài tháng tới.
  3. Kiểm tra metadata bounds và overlap.
  4. Kiểm tra DEFAULT có dữ liệu tương ứng không.
  5. Nếu có, lên kế hoạch chuyển dữ liệu an toàn.
  6. Kiểm tra EXPLAIN pruning và quyền/index.
  7. Ghi nhận kết quả và cảnh báo.
~~~

### 30.2. Chọn biên theo một timezone thống nhất

Với cột `date`, lựa chọn ngày thường rõ ràng. Với `timestamptz`, phải xác định tháng theo **UTC hay một timezone nghiệp vụ cụ thể**, và dùng ranh giới timestamp có offset/kiểu đúng để tránh DST/implicit conversion không mong muốn.

### 30.3. Không chỉ tin tên partition

Một bảng có tên `orders_2026_04` nhưng được attach sai khoảng vẫn sai về nghĩa. Phải kiểm tra `pg_get_expr(relpartbound, ...)`, không dựa riêng vào convention.

### 30.4. Monitoring DEFAULT

Nên phát hiện:

- Có hàng mới vào DEFAULT không?
- Hàng mới thuộc tháng sắp có partition chưa?
- DEFAULT có tăng bất thường không?
- Có ngày quá xa trong tương lai/quá cũ không?

Nếu DEFAULT bắt đầu nhận dữ liệu ngoài dự kiến, đó là tín hiệu cần sửa **quy trình provisioning hoặc validation nguồn dữ liệu**.

## 31. Các lỗi thiết kế thường gặp

### Lỗi 1. Hiểu partition key như một table lock

`PARTITION BY RANGE(order_date)` không khóa transaction theo ngày. Nó định nghĩa quy tắc **định tuyến và pruning**.

### Lỗi 2. Viết TO là biên bao gồm

`TO ('2026-02-01')` **không nhận** ngày 1/2; nó nhận giá trị **nhỏ hơn** 1/2.

### Lỗi 3. Dùng ngày cuối tháng làm TO

`TO ('2026-01-31')` bỏ mất 31/1. Hãy dùng ngày đầu tháng sau.

### Lỗi 4. Tạo ranges chồng lấn

PostgreSQL sẽ từ chối partitions cùng cấp có bound giao nhau; không thể “ưu tiên partition khai báo trước”.

### Lỗi 5. Bỏ trống tháng nhưng có DEFAULT nên không ai biết

INSERT vẫn thành công; dữ liệu có thể gom vào DEFAULT, khiến lỗi provision partition bị che đi.

### Lỗi 6. Nghĩ DEFAULT chỉ nhận NULL

DEFAULT nhận mọi giá trị **không khớp partitions khác**; NULL chỉ là một trường hợp tùy chiến lược và constraint.

### Lỗi 7. Nghĩ MINVALUE/MAXVALUE bao gồm NULL

Đó là các ký hiệu biên RANGE, **không biến NULL thành giá trị nằm giữa các bound**.

### Lỗi 8. Áp toán tử % trực tiếp lên ID để đoán HASH partition

PostgreSQL hash key rồi dùng modulus/remainder; không đơn giản là `customer_id % modulus` theo cách ứng dụng tự tính.

### Lỗi 9. Cố tạo DEFAULT cho HASH

HASH partitioning không dùng DEFAULT giống RANGE/LIST.

### Lỗi 10. Hiểu composite RANGE như các khoảng trên từng cột

`FROM (1,10) TO (2,20)` là khoảng **lexicographic**, không phải `1<=a<2 AND 10<=b<20`.

### Lỗi 11. Thêm tháng mới khi DEFAULT đang chứa hàng tháng ấy

Constraint DEFAULT sẽ không còn hợp lệ; cần di chuyển/xóa dữ liệu liên quan và attach trong quy trình có kiểm soát.

### Lỗi 12. Chỉ copy dữ liệu mà chưa xóa khỏi DEFAULT

Khi attach, DEFAULT vẫn có hàng xung đột với bound mới. Không được coi việc copy xong là đã hoàn tất migration.

### Lỗi 13. Copy/delete/attach bằng các transaction rời

Concurrent writes có thể rơi lại vào DEFAULT ở giữa các bước. Phải có transaction/locking hoặc cơ chế đồng bộ phù hợp.

### Lỗi 14. Tin ATTACH không bao giờ scan hoặc giữ khóa

Đối tượng mới và DEFAULT có thể cần validation; khóa DDL và chi phí scan có thể rất đáng kể.

### Lỗi 15. Tạo PRIMARY KEY(order_id) khi partition theo order_date

Constraint UNIQUE/PRIMARY KEY cấp cha bị giới hạn bởi partition key; không có global unique index tự động ngoài các child indexes.

### Lỗi 16. Cho rằng composite PK làm order_id duy nhất

`(order_id, order_date)` chỉ bảo đảm **cặp** là duy nhất; cùng ID ở hai ngày khác nhau có thể hợp lệ.

### Lỗi 17. Nghĩ partition pruning = index scan

Pruning loại partitions; scan bên trong partition vẫn có thể là Seq Scan. Hai tối ưu khác nhau.

### Lỗi 18. Truy vấn không lọc partition key nhưng mong pruning

Nếu chia theo ngày nhưng chỉ lọc customer ID, PostgreSQL có thể phải xem nhiều partitions.

### Lỗi 19. UPDATE khóa ngày thường xuyên

Đổi partition key có thể làm row movement, tốn công hơn sửa cột thông thường và ảnh hưởng constraints/triggers/concurrency.

### Lỗi 20. Tên partition là ranh giới đúng

Tên bảng không enforce biên. Metadata bound thực tế mới quyết định định tuyến.

### Lỗi 21. Drop DEFAULT để “xóa dữ liệu lỗi”

DEFAULT có thể chứa cả dữ liệu hợp lệ chưa có partition, dữ liệu cũ và dữ liệu tương lai. Xóa cả partition có thể làm mất nhiều loại dữ liệu.

### Lỗi 22. Tạo vô hạn partition nhỏ

Quá nhiều partitions làm tăng quản lý metadata, planning, lock và catalog overhead. Granularity phải có cơ sở.

### Lỗi 23. Dùng timestamp không rõ múi giờ

Nếu ranh giới tháng theo UTC nhưng ứng dụng kỳ vọng tháng theo timezone khác, hàng gần nửa đêm có thể thuộc partition khác trực giác.

### Lỗi 24. Nghĩ DEFAULT sẽ tự dọn khi có partition mới

Không có cơ chế tự chuyển hàng đã nằm trong DEFAULT sang partition mới một cách âm thầm. Phải migration.

## 32. Bài tập thực hành

Làm trên schema `part_lab`. Những bài tạo bảng mới có thể dùng tên bảng riêng trong database lab. Với thao tác phá hủy, chỉ viết SQL minh họa thay vì chạy trên dữ liệu thật.

### Bài 1. Định nghĩa

Partition key là gì? Nó khác row lock/table lock ra sao?

### Bài 2. Biên tháng

Partition `FROM ('2026-01-01') TO ('2026-02-01')` chứa ngày `2026-02-01` không? Vì sao?

### Bài 3. Ngày cuối tháng

Vì sao `TO ('2026-01-31')` không đúng nếu mục tiêu chứa toàn bộ tháng 1?

### Bài 4. Ngày nhuận

Viết bounds của tháng 2/2028 bằng hai mốc đầu tháng.

### Bài 5. Routing

Với lab đã tạo, hàng `order_date='2025-12-31'` vào partition nào? Hàng `'2026-02-01'` vào partition nào?

### Bài 6. tableoid

Viết query hiện `order_id`, `order_date` và tên partition thực lưu hàng.

### Bài 7. Không có DEFAULT

Một hàng không khớp partition nào và không có DEFAULT sẽ có kết quả gì khi INSERT?

### Bài 8. MINVALUE và MAXVALUE

Viết partition chứa mọi ngày trước `2026-01-01` và một partition chứa mọi ngày từ `2027-01-01` trở đi.

### Bài 9. LIST

Viết một LIST partition chứa hai vùng `north` và `northeast`.

### Bài 10. NULL trong LIST

Viết partition riêng chứa giá trị LIST key `NULL`. Khi đó NULL còn đi về DEFAULT không?

### Bài 11. NULL trong RANGE

Với nullable RANGE key có DEFAULT, hàng null đi đâu? Nếu cột có `NOT NULL` thì sao?

### Bài 12. HASH

Tạo 4 hash partitions cho khóa `customer_id`. Vì sao không suy địa chỉ partition chỉ từ `customer_id % 4`?

### Bài 13. Composite RANGE

Khoảng `FROM (1,10) TO (2,20)` có chứa `(1,999)` và `(2,-100)` không? Giải thích.

### Bài 14. DEFAULT

Nêu ba lý do không nên để DEFAULT tăng không kiểm soát.

### Bài 15. Chuyển dữ liệu DEFAULT

DEFAULT có hàng tháng 4, bạn muốn attach partition tháng 4. Vì sao không thể đơn giản attach mà không kiểm tra dữ liệu?

### Bài 16. Quy trình an toàn

Mô tả thứ tự create staging, copy, delete, attach và commit để tách tháng mới từ DEFAULT trong lab; vấn đề concurrency là gì?

### Bài 17. CHECK validation

Tại sao CHECK đã validated và chứng minh khoảng bound có thể giảm scan khi attach?

### Bài 18. Tạo mới partition

Viết SQL tạo partition tháng 4/2026 **sau khi** DEFAULT không còn dữ liệu tháng 4.

### Bài 19. PK

Vì sao partitioned parent theo `order_date` không thể mặc định có `PRIMARY KEY(order_id)` cấp cha?

### Bài 20. Composite key

`PRIMARY KEY(order_id,order_date)` có đảm bảo `order_id` duy nhất toàn cục không?

### Bài 21. Pruning

Viết query tháng 2/2026 trên `part_lab.orders` để PostgreSQL có cơ hội prune partitions khác.

### Bài 22. EXPLAIN

Viết `EXPLAIN (ANALYZE, BUFFERS)` cho query tháng 2, nêu hai dấu hiệu về pruning và scan.

### Bài 23. Không lọc partition key

Vì sao `WHERE customer_id=42` có thể quét nhiều partitions dù có index theo customer_id ở từng child?

### Bài 24. UPDATE khóa phân vùng

Khi đổi `order_date` của một hàng tháng 1 sang tháng 2, PostgreSQL có thể phải làm gì?

### Bài 25. Catalog

Viết query xem `pg_get_partkeydef`, `pg_partition_tree` và `pg_get_expr(relpartbound,...)`.

### Bài 26. Retention

Vì sao detach/drop một partition cũ thường dễ quản lý hơn xóa từng hàng, và cần thận trọng điều gì?

### Bài 27. Query không sargable

`EXTRACT(YEAR FROM order_date)=2026` có thể bất lợi gì cho pruning? Viết predicate khoảng tương đương.

### Bài 28. Tạo trước partition

Mô tả một quy trình định kỳ giúp không bao giờ phụ thuộc vào DEFAULT để tiếp nhận dữ liệu tháng mới.

## 33. Gợi ý đáp án

### Bài 1

Partition key là cột/biểu thức dùng để quyết định partition vật lý chứa hàng, không phải khóa đồng thời của transaction.

### Bài 2–3

`TO` là biên trên **loại trừ**, nên ngày 1/2 không thuộc tháng 1. `TO('2026-01-31')` cũng loại đúng ngày 31/1; dùng `TO('2026-02-01')`.

### Bài 4

~~~sql
FOR VALUES FROM ('2028-02-01') TO ('2028-03-01')
~~~

### Bài 5–6

`2025-12-31` thuộc DEFAULT; `2026-02-01` thuộc `orders_2026_02`.

~~~sql
SELECT
    order_id,
    order_date,
    tableoid::regclass AS partition_name
FROM part_lab.orders
ORDER BY order_id;
~~~

### Bài 7

`INSERT` thất bại do không có partition tương ứng; PostgreSQL không tự tạo partition mới.

### Bài 8

~~~sql
FOR VALUES FROM (MINVALUE) TO ('2026-01-01')
-- và:
FOR VALUES FROM ('2027-01-01') TO (MAXVALUE)
~~~

Các biên này không tự nhận `NULL`.

### Bài 9–10

~~~sql
CREATE TABLE part_lab.shipments_north_answer
PARTITION OF part_lab.shipments
FOR VALUES IN ('north', 'northeast');
~~~

*Câu trên chỉ là minh họa cú pháp:* trong lab đã tồn tại `shipments_north` với cùng tập giá trị, nên **không chạy thêm** vì overlap. Với một bảng LIST mới:

~~~sql
CREATE TABLE labels_null
PARTITION OF part_lab.labels
FOR VALUES IN (NULL);
~~~

Nếu partition NULL đã được khai báo (như `labels_missing` trong lab), không thể tạo lại một partition NULL trùng. Trong cấu hình có partition NULL, giá trị NULL đi vào partition tường minh, không về DEFAULT.

### Bài 11

Nullable RANGE key với DEFAULT có thể định tuyến NULL vào DEFAULT; `NOT NULL` khiến INSERT/UPDATE NULL thất bại trước khi có thể lưu hàng hợp lệ.

### Bài 12

~~~sql
FOR VALUES WITH (MODULUS 4, REMAINDER 0)
FOR VALUES WITH (MODULUS 4, REMAINDER 1)
FOR VALUES WITH (MODULUS 4, REMAINDER 2)
FOR VALUES WITH (MODULUS 4, REMAINDER 3)
~~~

Định tuyến dựa trên hàm hash của PostgreSQL rồi mới lấy modulus/remainder; không đơn giản là ID chia 4.

### Bài 13

Cả `(1,999)` và `(2,-100)` đều thuộc khoảng: so sánh theo bộ từ trái sang phải, không áp hai khoảng riêng trên hai cột.

### Bài 14

DEFAULT có thể che giấu thiếu partitions, trở nên rất lớn/khó tối ưu, và khiến attach partition mới phải kiểm tra/di chuyển dữ liệu có thể gây khóa lâu.

### Bài 15–16

Vì DEFAULT đang chứa hàng thuộc khoảng mới, nó sẽ vi phạm bound bị thu hẹp. Trong một transaction/chiến lược đồng bộ phù hợp: khóa ngăn concurrent writes, tạo bảng staging có CHECK tháng mới, copy dữ liệu, delete dữ liệu tương ứng khỏi DEFAULT, attach bảng staging và commit. Production cần kế hoạch riêng để tránh khóa dài.

### Bài 17

CHECK đã validated và chứng minh mọi hàng trong staging thuộc bound có thể cho PostgreSQL tránh phải scan toàn bộ staging để kiểm tra, tùy điều kiện. DEFAULT vẫn có thể cần scan/validation.

### Bài 18

~~~sql
CREATE TABLE part_lab.orders_2026_04
PARTITION OF part_lab.orders
FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
~~~

**Chỉ chạy khi** DEFAULT không còn hàng ngày trong khoảng tháng 4 và chưa có partition trùng bound.

### Bài 19–20

Không có global unique index tự động. `PRIMARY KEY(order_id)` không thể enforce toàn cục nếu một giá trị ID nằm ở hai partition ngày khác nhau. `PRIMARY KEY(order_id,order_date)` chỉ đảm bảo **cặp**, không phải `order_id` đơn lẻ.

### Bài 21–22

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM part_lab.orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01';
~~~

Xem plan có bỏ partitions Jan/Mar/DEFAULT không; trong Feb scan là Seq Scan hay Index Scan, buffer/time bao nhiêu.

### Bài 23

Khóa phân vùng là ngày, nên customer ID không tự suy ra partition chứa hàng. Index trên customer ID trong từng child có thể giúp tìm bên trong từng partition nhưng không nhất thiết giảm số partitions cần xem.

### Bài 24

PostgreSQL có thể thực hiện row movement giữa partition tháng 1 và tháng 2, với constraints, triggers và concurrency semantics liên quan; nếu đích không tồn tại và không có DEFAULT, có thể lỗi.

### Bài 25

~~~sql
SELECT pg_get_partkeydef('part_lab.orders'::regclass);

SELECT
    relid::regclass AS partition,
    parentrelid::regclass AS parent,
    level
FROM pg_partition_tree('part_lab.orders'::regclass);

SELECT
    c.oid::regclass AS child,
    pg_get_expr(c.relpartbound, c.oid) AS bound
FROM pg_class AS c
JOIN pg_inherits AS i
  ON i.inhrelid = c.oid
WHERE i.inhparent = 'part_lab.orders'::regclass;
~~~

### Bài 26

Quản lý một partition vật lý cho phép tổ chức retention theo tháng thay vì xóa từng hàng, nhưng detach/drop có rủi ro dữ liệu, locks, FK, backup, policy và các dependency. Không thực hiện tùy tiện.

### Bài 27

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date < DATE '2027-01-01'
~~~

Điều kiện trực tiếp trên partition key dễ prune hơn trong nhiều tình huống; còn `EXTRACT` có thể ngăn planner suy bounds tương ứng.

### Bài 28

Theo lịch, tạo partitions cho vài tháng tương lai trước khi dữ liệu xuất hiện; đối chiếu metadata bounds, kiểm tra DEFAULT và cảnh báo nếu xuất hiện hàng thuộc tháng không dự kiến; giám sát kết quả thực thi và lên phương án di chuyển nếu đã có dữ liệu rơi vào DEFAULT.

## 34. Bảng tra cứu nhanh

| Yêu cầu | Cú pháp / ý nghĩa |
| --- | --- |
| Partition key theo thời gian | `PARTITION BY RANGE (order_date)` |
| Khoảng tháng 1 | `FROM ('2026-01-01') TO ('2026-02-01')` |
| Biên RANGE | `[lower, upper)` — dưới gồm, trên loại |
| Khoảng trước mọi ngày khác | `FROM (MINVALUE) TO ('2026-01-01')` |
| Khoảng về sau | `FROM ('2027-01-01') TO (MAXVALUE)` |
| Partition theo vùng | `PARTITION BY LIST (region)` |
| Giá trị LIST | `FOR VALUES IN ('north','south')` |
| NULL ở LIST | `FOR VALUES IN (NULL)` |
| Partition HASH | `PARTITION BY HASH (customer_id)` |
| HASH bucket | `FOR VALUES WITH (MODULUS 4, REMAINDER 0)` |
| Catch-all RANGE/LIST | `CREATE TABLE ... PARTITION OF ... DEFAULT` |
| Xem partition thực lưu | `tableoid::regclass` |
| Xem partition tree | `pg_partition_tree(parent::regclass)` |
| Xem partition key | `pg_get_partkeydef(parent_oid)` |
| Xem bounds | `pg_get_expr(relpartbound, oid)` |
| Gắn bảng sẵn có | `ALTER TABLE parent ATTACH PARTITION child FOR VALUES ...` |
| Tháo partition | `ALTER TABLE parent DETACH PARTITION child` |
| Pruning | Planner/executor loại partition không khớp predicate key |
| Kiểm tra pruning | `EXPLAIN (ANALYZE, BUFFERS)` |
| Theo dõi DEFAULT | `SELECT ... FROM parent_default` |
| PK/UNIQUE cấp cha | Phải thỏa yêu cầu chứa toàn bộ partition key columns |
| Đổi partition key | Có thể gây row movement |

## 35. Checklist trước khi vận hành

1. **Khóa phân vùng có hợp với query thật?** Có filter theo ngày/vùng/ID tương ứng không?
2. **Biên RANGE đúng [lower,upper)?** Có bỏ sót ngày cuối tháng hoặc dùng sai timezone không?
3. **Partitions có liên tiếp đúng kế hoạch?** Có gap ngoài chủ ý hay overlap không?
4. **DEFAULT có thật cần?** Nếu không có, ứng dụng xử lý lỗi ngày ngoài khoảng thế nào?
5. **DEFAULT đang chứa những ngày/vùng gì?** Có cảnh báo khi tăng không?
6. **Giá trị NULL được định tuyến ra sao?** Có NOT NULL, LIST NULL partition hay DEFAULT?
7. **Composite range có được hiểu theo lexicographic?** Có vô tình tạo phạm vi quá rộng?
8. **HASH có đủ bucket và modulus/remainder đúng?** Có nhầm với ID modulo trực tiếp?
9. **PK/UNIQUE có bao gồm partition key theo yêu cầu?** Global identity có được bảo vệ thực sự?
10. **Tạo partitions tương lai trước thời hạn?** Có tự động hóa và giám sát?
11. **Nếu DEFAULT đã có hàng thuộc bound mới, quy trình chuyển dữ liệu là gì?**
12. **CREATE/ATTACH có thể scan/giữ khóa bao lâu?** Đã đo trên dữ liệu gần production?
13. **Có concurrent writers hoặc transaction lâu?** Cần cửa sổ bảo trì hay cơ chế online?
14. **Các partition mới có constraints/index/quyền đúng không?**
15. **UPDATE partition key có thường xảy ra?** Row movement ảnh hưởng nghiệp vụ gì?
16. **EXPLAIN có prune partition không liên quan?** Có Seq Scan lớn trong partition còn lại không?
17. **Retention có cần detach/drop partition?** Đã kiểm tra backup/FK/dependency?
18. **Có quá nhiều partitions làm tăng overhead?** Granularity có cơ sở?
19. **Có kiểm tra metadata thay vì dựa tên partition?**
20. **Hàng đang nằm đúng partition dự kiến?** Đã dùng `tableoid` và giám sát DEFAULT?

## 36. Tổng kết

Ba khái niệm trọng tâm của declarative partitioning trong PostgreSQL:

1. **Khóa phân vùng** (*partition key*) quyết định **cách định tuyến** mỗi hàng vào partition. Với `RANGE` nó biểu thị một vị trí trong dải có thứ tự; với `LIST` là giá trị thuộc danh sách; với `HASH` là kết quả phân loại theo hàm hash. Partition key **không phải transaction lock**.
2. **Biên phân vùng** (*partition bounds*) xác định phạm vi không trùng của từng partition. Với RANGE, đầu dưới **bao gồm** và đầu trên **loại trừ**: `[2026-01-01, 2026-02-01)` chứa cả ngày 31/1 nhưng không chứa ngày 1/2. Với RANGE nhiều cột, so sánh là **lexicographic** chứ không phải nhiều điều kiện khoảng độc lập.
3. **Phân vùng mặc định** (*DEFAULT*) là nơi nhận những giá trị không thuộc partition tường minh trong RANGE/LIST, nếu constraints cho phép. Nó giúp giảm lỗi định tuyến trong ngắn hạn nhưng có thể che giấu việc thiếu partition. Khi tạo partition mới, dữ liệu đã nằm trong DEFAULT thuộc bound mới **phải được xử lý trước**, nếu không thao tác có thể bị từ chối.

Một hệ thống phân vùng tốt cần **đúng ngữ nghĩa và dễ vận hành**: chọn key theo truy vấn/retention, định nghĩa bounds nhất quán, tạo partition tương lai chủ động, theo dõi DEFAULT, giữ các ràng buộc uniqueness phù hợp và dùng `EXPLAIN` để xác nhận pruning thật sự diễn ra.

Khi chuẩn bị thêm một partition mới, hãy hỏi: **“Bound này bao gồm chính xác những giá trị nào, DEFAULT hiện có hàng nào thuộc bound đó, và thao tác attach sẽ khóa/kiểm tra dữ liệu ra sao?”**. Trả lời được ba câu ấy giúp tránh lỗi thường gặp nhất của việc mở rộng bảng phân vùng theo thời gian.
