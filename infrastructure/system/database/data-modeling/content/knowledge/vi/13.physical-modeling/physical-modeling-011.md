# Đánh giá thiết kế bằng kế hoạch truy vấn và dữ liệu có quy mô phù hợp

Một lược đồ đã có khóa chính, khóa ngoại, kiểu dữ liệu và chỉ mục vẫn chưa thể được coi là **thiết kế vật lý tốt** chỉ vì mọi câu SQL chạy được trên vài trăm bản ghi. Trong thực tế, cùng một truy vấn có thể mất vài mili giây trên dữ liệu thử nhưng chậm hàng giây khi có hàng triệu dòng, một nhóm khách hàng có số đơn hàng bất thường, dữ liệu cũ tích lũy nhiều năm hoặc nhiều giao dịch ghi đang chạy đồng thời.

Đánh giá mô hình vật lý cần nối ba lớp bằng chứng:

1. **Yêu cầu nghiệp vụ và tải thực tế:** màn hình/API/báo cáo nào quan trọng; giới hạn độ trễ, thông lượng và dung lượng là gì?
2. **Kế hoạch truy vấn (query execution plan):** hệ quản trị dự kiến và thực sự đọc, lọc, JOIN, sắp xếp và tổng hợp dữ liệu theo cách nào?
3. **Dữ liệu có quy mô và phân bố đại diện:** số hàng, độ rộng, phân bố giá trị, độ lệch, tỷ lệ NULL, tương quan giữa cột, tỷ lệ ghi/xóa và khả năng cạnh tranh tài nguyên có gần điều kiện vận hành không?

Bài học này thuộc chương **Mô hình vật lý** của module **DATABASE_DATA_MODELING**. Mục tiêu không phải chọn một chỉ mục theo cảm tính, mà là biết cách **đặt giả thuyết, tạo phép thử có thể lặp lại, đọc bằng chứng, thay đổi một yếu tố, đo lại và ghi nhận đánh đổi**. Ví dụ sử dụng PostgreSQL; nguyên tắc về số lượng hàng, độ chọn lọc, kế hoạch truy vấn và benchmark cũng hữu ích khi đánh giá CSDL quan hệ, document, đồ thị và hệ thống phân tích.

> **Nguyên tắc:** Không thể kết luận “chỉ mục A nhanh hơn B” chỉ từ tên loại chỉ mục hoặc một bản EXPLAIN không có số liệu thực thi. Phải đối chiếu với **truy vấn đúng, dữ liệu đúng, trạng thái hệ thống đúng và phép đo đúng**.

## 1. Phân biệt thiết kế logic và thiết kế vật lý

Trong thiết kế logic, một hệ thống bán hàng có thể gồm Customer, Product, SalesOrder và OrderLine, với các quan hệ và ràng buộc rõ ràng:

~~~text
Customer (1) ── (N) SalesOrder (1) ── (N) OrderLine (N) ── (1) Product
~~~

Mô hình logic trả lời: ai là ai, đơn hàng thuộc khách nào, mỗi dòng tham chiếu sản phẩm nào, khóa nào phải duy nhất.

Thiết kế vật lý bổ sung những quyết định như:

- Kiểu dữ liệu cụ thể, độ dài trường và kích thước hàng.
- Cách lưu khóa chính và khóa ngoại, chỉ mục phục vụ các mẫu truy vấn.
- Có cần index nhiều cột, partial index, covering index, BRIN hoặc partition không.
- Truy vấn nên trả về bao nhiêu dòng, có phân trang bằng khóa hay dùng OFFSET.
- Những truy vấn tổng hợp nào được phép quét một lượng dữ liệu lớn.
- Cách quản lý thống kê bộ tối ưu, vacuum, dữ liệu cũ, lịch sử và lưu trữ.
- Có cần cấu trúc dẫn xuất, bảng tổng hợp hoặc bộ đệm cho một nhu cầu đọc cụ thể.
- Ảnh hưởng đến **ghi dữ liệu**, giao dịch, khóa, dung lượng, backup và thời gian triển khai thay đổi lược đồ.

Một lựa chọn vật lý chỉ hợp lý trong **ngữ cảnh tải**. Chỉ mục trên cột trạng thái có ít giá trị có thể rất ít lợi ích cho truy vấn đọc 70% bảng, nhưng một partial index lọc nhóm trạng thái hiếm kết hợp điều kiện ngày có thể rất hữu ích cho báo cáo ngắn.

## 2. Đầu vào của một phép đánh giá có trách nhiệm

Trước khi mở EXPLAIN, cần viết rõ những giả định có thể kiểm chứng.

| Yếu tố | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Quy mô hiện tại | Mỗi bảng có bao nhiêu hàng? | 250 nghìn Order, 1,25 triệu OrderLine |
| Quy mô dự kiến | Sau 12–24 tháng có bao nhiêu hàng? | Số đơn tăng 5 lần |
| Phân bố dữ liệu | Có giá trị phổ biến vượt trội? | 10% khách tạo ra phần lớn đơn mới |
| Độ sâu lịch sử | Dữ liệu cũ có được giữ nguyên? | Đơn thanh toán phải giữ nhiều năm |
| Truy vấn quan trọng | API nào có tần suất và độ nhạy cao? | Lấy 20 đơn gần nhất của khách |
| SLO | Yêu cầu chấp nhận được là gì? | Ví dụ mục tiêu p95 dưới 150 ms, **do sản phẩm tự đặt** |
| Tải ghi | Bao nhiêu INSERT/UPDATE/DELETE mỗi giây? | Tạo đơn, đổi trạng thái, nhập hàng |
| Cạnh tranh | Có bao nhiêu phiên cùng dùng tài nguyên? | 50 phiên đồng thời ở giờ cao điểm |
| Môi trường | CPU, RAM, ổ đĩa, cache, phiên bản DBMS? | PostgreSQL trên máy tương đương production |

**SLO (service level objective)** là mục tiêu vận hành do nhóm thống nhất, **không phải số mặc định của PostgreSQL**. Cần xác định rõ đang đo thời gian thực thi SQL tại server, thời gian của toàn request hay độ trễ từ thiết bị người dùng. Một truy vấn chạy 20 ms không có nghĩa API cũng trả trong 20 ms khi còn mạng, ứng dụng, pool connection và serialization.

### 2.1. Ba nhóm truy vấn mẫu

Trong ví dụ bán hàng, ta dùng ba truy vấn có tính chất khác nhau:

1. **OLTP tra cứu ngắn:** lấy 20 đơn mới nhất của một customer_id.
2. **Danh sách điều hành:** lấy 50 đơn PAID gần đây.
3. **Tổng hợp:** doanh số theo sản phẩm trong 30 ngày gần nhất.

Truy vấn (1) cần lọc rất chọn lọc và trả ít dòng; truy vấn (2) phụ thuộc độ chọn lọc của thời gian và trạng thái; truy vấn (3) có thể phải đọc và tổng hợp hàng trăm nghìn OrderLine.

**Không nên áp một mục tiêu thời gian giống nhau cho cả ba** nếu chức năng và nhu cầu khác nhau. Hãy đặt ngân sách hiệu năng cho từng nhóm, theo tần suất và tác động tới người dùng.

## 3. Tạo lược đồ thử nghiệm có khóa và ràng buộc thật

Một thử nghiệm đáng tin hơn khi có PK, FK, UNIQUE, CHECK và kiểu dữ liệu tương ứng với thiết kế dự kiến. Nếu bỏ hết ràng buộc để nạp dữ liệu cho nhanh rồi đánh giá khả năng ghi, kết quả sẽ không phản ánh chi phí kiểm tra tham chiếu và chỉ mục của hệ thống thật.

Ví dụ PostgreSQL, chỉ chạy trong **môi trường phát triển/benchmark riêng**:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    region_code TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    list_price_cents BIGINT NOT NULL CHECK (list_price_cents >= 0)
);

CREATE TABLE orders (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    line_no SMALLINT NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Các điều quan trọng:

- Khóa chính OrderLine là **(order_id, line_no)**, phù hợp với định danh dòng trong một đơn.
- OrderLine tham chiếu Product, nhưng **unit_price_cents** là giá chốt tại thời điểm mua; nó không bắt buộc bằng giá Product hiện tại.
- Số tiền dùng số nguyên theo đơn vị nhỏ nhất của đồng tiền trong ví dụ, tránh sai số số thực khi tổng hợp. Hệ thống nhiều tiền tệ còn cần currency và chính sách làm tròn.
- FK từ bảng con không tự tạo chỉ mục trên **mọi cột FK** trong PostgreSQL; cách chọn chỉ mục được xem xét dựa trên truy vấn bên dưới.

### 3.1. Nạp dữ liệu có phân bố và độ lệch chủ đích

Dùng generate_series tạo 50.000 khách hàng, 3.000 sản phẩm, 250.000 đơn và 5 dòng mỗi đơn (1.250.000 dòng). Dữ liệu này đủ lớn để một số kiểu kế hoạch thể hiện khác biệt, nhưng **chưa phải một benchmark production**.

~~~sql
-- Chạy một lần trên database thử nghiệm trống.
INSERT INTO customers (customer_id, region_code, created_at)
SELECT n,
       CASE
           WHEN n % 10 < 7 THEN 'HCM'
           WHEN n % 10 < 9 THEN 'HN'
           ELSE 'OTHER'
       END,
       CURRENT_TIMESTAMP - ((n % 365) * INTERVAL '1 day')
FROM generate_series(1, 50000) AS g(n);

INSERT INTO products (product_id, title, list_price_cents)
SELECT n,
       'Product ' || n,
       10000 + (n % 101) * 500
FROM generate_series(1, 3000) AS g(n);

INSERT INTO orders (order_id, customer_id, status, created_at)
SELECT n,
       CASE
           -- Nhóm ít khách có nhiều đơn hơn mức bình thường.
           WHEN n % 11 = 0 THEN (n % 100) + 1
           ELSE ((n * 37) % 49900) + 101
       END,
       CASE
           WHEN n % 10 < 7 THEN 'PAID'
           WHEN n % 10 < 9 THEN 'PENDING'
           ELSE 'CANCELLED'
       END,
       CURRENT_TIMESTAMP
           - ((n % 365) * INTERVAL '1 day')
           - ((n % 86400) * INTERVAL '1 second')
FROM generate_series(1, 250000) AS g(n);

INSERT INTO order_lines
    (order_id, line_no, product_id, quantity, unit_price_cents)
SELECT o.order_id,
       s.line_no,
       p.product_id,
       1 + ((o.order_id + s.line_no) % 3)::INTEGER,
       p.list_price_cents
FROM orders AS o
CROSS JOIN generate_series(1, 5) AS s(line_no)
JOIN products AS p
  ON p.product_id = CASE
      -- Khoảng 70% các dòng tập trung vào 80 sản phẩm phổ biến.
      WHEN (o.order_id + s.line_no) % 10 < 7
        THEN ((o.order_id * 37 + s.line_no) % 80) + 1
      ELSE ((o.order_id * 17 + s.line_no * 13) % 2920) + 81
  END;
~~~

Những hằng số trong generator chỉ tạo ra **phân bố thử có chủ đích**, không phải mô hình xác suất đại diện cho một sàn bán hàng thực tế. Ta chủ động tạo **skew**: nhóm khách đặt nhiều đơn và nhóm sản phẩm phổ biến. Điều này giúp thử trường hợp mà dữ liệu đồng đều thường che khuất.

**Chú ý khả năng lặp lại:** CURRENT_TIMESTAMP khiến mốc ngày tương đối thay đổi mỗi lần nạp; phép nhân/chia lấy dư tạo phân bố có quy luật. Nếu cần so sánh qua nhiều phiên thử nghiệm, hãy lưu **mốc thời gian cố định** và **phiên bản bộ dữ liệu**, hoặc ghi lại thời điểm nạp cùng các truy vấn kiểm kê. Không suy ra từ dữ liệu tạo bằng công thức rằng nó có độ tương quan giống dữ liệu thật.

Sau khi nạp:

~~~sql
ANALYZE customers;
ANALYZE products;
ANALYZE orders;
ANALYZE order_lines;
~~~

PostgreSQL cần **thống kê cập nhật** để ước lượng số hàng, phân bố giá trị và chi phí các phương án. Nếu benchmark ngay sau khi nạp hàng triệu dòng mà không ANALYZE, có thể đánh giá sai một lược đồ tốt chỉ vì optimizer đang dùng thống kê cũ hoặc thiếu.

### 3.2. Kiểm tra bộ dữ liệu trước khi benchmark

~~~sql
SELECT 'customers' AS object, COUNT(*) AS rows FROM customers
UNION ALL
SELECT 'products', COUNT(*) FROM products
UNION ALL
SELECT 'orders', COUNT(*) FROM orders
UNION ALL
SELECT 'order_lines', COUNT(*) FROM order_lines;

SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status
ORDER BY status;

SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
ORDER BY order_count DESC
LIMIT 10;

SELECT product_id, COUNT(*) AS line_count
FROM order_lines
GROUP BY product_id
ORDER BY line_count DESC
LIMIT 10;
~~~

**Số lượng mục tiêu** theo generator là 50.000, 3.000, 250.000 và 1.250.000 hàng, nếu mọi INSERT thành công và chỉ chạy một lần trên bảng trống. Khi thử thật, cần quan sát kết quả trả về và ghi **số lượng thực tế**; không coi con số mục tiêu là kết quả đo.

Nếu môi trường không đủ tài nguyên, có thể thu nhỏ số hàng, nhưng phải ghi rõ tỷ lệ thu nhỏ. Benchmark trên 2.500 đơn không đại diện cho truy vấn xử lý 250 triệu đơn chỉ vì cùng schema.

## 4. EXPLAIN khác EXPLAIN ANALYZE như thế nào?

PostgreSQL cung cấp hai cấp thông tin chính:

~~~sql
-- Chỉ hiển thị kế hoạch dự kiến, không thực thi SELECT.
EXPLAIN
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

-- Thực thi SELECT, thu thập số liệu thực tế.
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

| Khía cạnh | EXPLAIN | EXPLAIN ANALYZE |
| --- | --- | --- |
| Có chạy truy vấn không? | Không thực thi SELECT bên dưới | **Có**, thực thi truy vấn bên dưới |
| Có hiển thị chi phí ước lượng? | Có | Có |
| Có số hàng thực tế và số lần lặp? | Không | Có |
| Có thời gian thực tế của từng nút? | Không | Có, trừ tùy chọn tắt timing |
| Có thống kê buffer khi yêu cầu? | Dữ liệu chi phí, không phải số buffer thực chạy | Có với BUFFERS |
| Dùng khi nào? | Khảo sát kế hoạch, đặc biệt với câu lệnh có tác động | Đo truy vấn trên môi trường được phép thực thi |

**Cảnh báo bắt buộc:** EXPLAIN ANALYZE **thực sự thực thi** cả INSERT, UPDATE, DELETE nếu câu lệnh bên dưới là thao tác ghi. Không chạy thử câu lệnh ghi có ANALYZE trên dữ liệu thật chỉ vì muốn xem kế hoạch.

Trên môi trường thử, có thể dùng giao dịch rồi ROLLBACK để khảo sát một số câu lệnh DML:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = 12345;

ROLLBACK;
~~~

ROLLBACK hủy các thay đổi dữ liệu thông thường **trong giao dịch**, nhưng không hoàn lại mọi tác động như mức tăng sequence, lời gọi dịch vụ ngoài trong trigger hoặc các tác động ngoài giao dịch. Vì vậy vẫn phải **cô lập môi trường thử và kiểm soát side effect**; không dùng ví dụ này như sự bảo đảm an toàn tuyệt đối ở production.

### 4.1. Các tùy chọn hữu ích

~~~sql
-- Thêm thông tin cấu hình có liên quan và định dạng cấu trúc.
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)
SELECT order_id
FROM orders
WHERE customer_id = 42;

-- Khi muốn giảm overhead đo thời gian từng nút:
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM order_lines;
~~~

FORMAT JSON thuận tiện khi cần lưu, phân tích hoặc so sánh cấu trúc kế hoạch tự động. Kế hoạch vẫn phụ thuộc phiên bản PostgreSQL, trạng thái dữ liệu, thống kê và cấu hình, nên không nên chỉ so sánh nguyên văn một đoạn text rồi kết luận có hồi quy.

## 5. Đọc một kế hoạch truy vấn từ dưới lên

Một kế hoạch là **cây toán tử thực thi**. Những nút thường gặp:

| Nút trong kế hoạch | Công việc chính | Dấu hiệu cần xem |
| --- | --- | --- |
| **Seq Scan** | Đọc lần lượt các hàng của bảng | Tỷ lệ bảng phải đọc; filter; buffers |
| **Index Scan** | Tìm hàng qua index rồi đọc heap khi cần | Index Cond, số heap page, tính chọn lọc |
| **Index Only Scan** | Đọc cột có trong index khi điều kiện visibility cho phép | Heap Fetches; index coverage và visibility map |
| **Bitmap Index/Heap Scan** | Gom vị trí từ index rồi đọc nhiều heap page | Recheck Cond, lossy pages và số page |
| **Nested Loop** | Với mỗi hàng phía ngoài, tìm hàng phù hợp phía trong | loops, cardinality, index phía trong |
| **Hash Join** | Dựng hash từ một phía rồi dò phía kia | Kích thước hash, batches và memory |
| **Merge Join** | Ghép hai nguồn theo khóa có thứ tự | Nguồn có sẵn sort order hay phải Sort |
| **Sort** | Sắp xếp dữ liệu | Sort Method, Memory/Disk, số dòng |
| **HashAggregate/GroupAggregate** | Gom nhóm/tổng hợp | Số nhóm, bộ nhớ, disk spill |
| **Limit** | Ngừng trả kết quả sau ngưỡng | Có thể tránh scan hết hay vẫn phải sort/aggregate? |
| **Gather/Gather Merge** | Phối hợp worker song song | Workers Planned/Launched, phân bố công việc |

**Không nên coi Seq Scan luôn xấu, Index Scan luôn tốt.** Khi đọc hầu hết một bảng nhỏ, quét tuần tự có thể rẻ hơn đọc qua index rồi nhảy ngẫu nhiên nhiều trang dữ liệu. Ngược lại, truy vấn trả 20 hàng trong bảng lớn có thể rất hưởng lợi từ index đúng thứ tự.

### 5.1. Cost không phải mili giây

Một dòng kế hoạch có thể trông như:

~~~text
Index Scan using idx_orders_customer_recent on orders
  (cost=0.42..15.30 rows=20 width=24)
~~~

Đây **chỉ là ví dụ hình dạng đầu ra**, không phải kết quả đã chạy trên bộ dữ liệu ở phần 3. Các số trong cost là **đơn vị chi phí tương đối của planner**, không phải 0,42 ms hay 15,30 ms. Planner dùng các ước lượng để chọn phương án có chi phí dự kiến thấp trong các phương án đã xét.

Khi có EXPLAIN ANALYZE, một nút còn có:

~~~text
(actual time=0.050..0.180 rows=20 loops=1)
~~~

Các số actual time là số đo của lần thực thi, phụ thuộc môi trường và có overhead đo. **Không được trích các giá trị minh họa trên làm số liệu benchmark**.

### 5.2. Estimated rows, actual rows và loops

Đây là một trong những so sánh quan trọng nhất:

- **rows ước lượng:** optimizer dự đoán nút trả bao nhiêu hàng **mỗi lần thực thi**.
- **actual rows:** số hàng trung bình/thực tế nút trả mỗi lần thực thi theo hiển thị.
- **loops:** số lần nút được gọi, đặc biệt quan trọng bên trong Nested Loop.
- **Tổng công việc xấp xỉ** có thể liên hệ với actual rows × loops, nhưng còn phải xét số hàng bị lọc, heap page và các nút con.

Nếu ước lượng 10 hàng nhưng thực tế 100.000 hàng, optimizer có thể đã chọn kiểu JOIN hoặc thứ tự JOIN không phù hợp. Khi đó nguyên nhân gốc có thể là **thống kê thiếu/cũ, tương quan cột, skew, biểu thức lọc hoặc tham số truy vấn**, không đơn thuần là “thiếu index”.

### 5.3. Filter khác Index Cond

Trong kế hoạch:

- **Index Cond** mô tả điều kiện được sử dụng để giới hạn phần truy xuất qua index.
- **Filter** là điều kiện được kiểm tra sau khi đã lấy hàng tới nút xử lý.
- **Rows Removed by Filter** cho biết có bao nhiêu hàng không đạt điều kiện tại nút đó.

Một index trên status chỉ giúp định vị status, nhưng nếu truy vấn còn lọc customer_id và created_at mà index không hỗ trợ tốt, PostgreSQL vẫn có thể phải đọc nhiều hàng rồi mới lọc. Hãy xem **tỷ lệ hàng được đọc so với hàng trả về**, thay vì chỉ thấy từ “Index Scan”.

### 5.4. Buffers và giới hạn của việc đọc số liệu

Với BUFFERS, có thể thấy các chỉ số như:

- **shared hit:** buffer page được tìm thấy trong PostgreSQL shared buffer cache.
- **shared read:** buffer page phải được đọc vào shared buffers; không nhất thiết tương đương một lần đọc vật lý từ ổ đĩa vì còn cache của hệ điều hành.
- **shared dirtied/written:** trang bị làm bẩn/ghi ra ở quá trình thực thi.
- **temp read/written:** I/O với dữ liệu tạm, thường liên quan sort/hash không đủ bộ nhớ.

Tổng buffer hit lớn **không tự động là lỗi**, và shared read không đo đầy đủ thời gian I/O của thiết bị. Cần đọc cùng thời gian thực thi, số lần lặp, dữ liệu đã cache và cấu hình máy.

## 6. Ca thực hành A: truy vấn 20 đơn mới nhất của một khách

Truy vấn phục vụ màn hình “Lịch sử đơn hàng”:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

### 6.1. Đánh giá thiết kế trước khi thêm index

Bảng orders mới có PK trên order_id, nên **PK không hỗ trợ trực tiếp** điều kiện customer_id + thứ tự thời gian. Planner có thể chọn Seq Scan và Sort, hoặc một kế hoạch khác tùy quy mô. Chỉ nhìn tên khóa chính sẽ không phát hiện vấn đề.

Đo kế hoạch ban đầu:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Ghi lại: thời gian, số hàng đúng, kế hoạch, estimated/actual rows, buffers, có Sort hay không.

### 6.2. Thêm chỉ mục phù hợp điều kiện và thứ tự

~~~sql
CREATE INDEX idx_orders_customer_recent
ON orders (customer_id, created_at DESC, order_id DESC)
INCLUDE (status);

ANALYZE orders;
~~~

Động cơ:

1. **customer_id** đầu tiên hỗ trợ điều kiện bằng nhau.
2. **created_at DESC, order_id DESC** giúp đi theo thứ tự hiển thị, nhất là khi hai đơn có cùng created_at.
3. **LIMIT 20** cho phép dừng sau khi có đủ 20 hàng nếu kế hoạch có thể đi theo index đúng hướng.
4. **INCLUDE(status)** làm status có mặt trong index để có cơ hội dùng Index Only Scan cho truy vấn này.

Tuy nhiên, **Index Only Scan không chắc xuất hiện**, và kể cả khi xuất hiện vẫn có thể có **Heap Fetches** do trang dữ liệu chưa được đánh dấu all-visible. Khi bảng được cập nhật liên tục, visibility map, VACUUM và độ rộng index ảnh hưởng đáng kể. INCLUDE không có nghĩa “truy vấn chắc chắn chỉ đọc index”.

Chạy lại **cùng câu SQL**, với cùng dữ liệu và cấu hình; so sánh trước/sau. Index mới cũng làm tăng dung lượng và chi phí INSERT/UPDATE/DELETE trên orders, nên phải đo cả tác động ghi.

### 6.3. Thử cả khách hàng phổ biến và thông thường

Ví dụ benchmark với customer_id thuộc nhóm “hot” và nhóm thường:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 10007
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Hai giá trị chỉ là **ví dụ thử**, không bảo đảm có cùng số hàng. Hãy kiểm tra phân bố trước khi phân loại khách thật sự là hot/cold. Một index tốt có thể giúp cả hai, nhưng thời gian trả kết quả và số trang phải đọc vẫn khác nhau vì lượng hàng, vị trí dữ liệu và trạng thái cache.

**Bài học:** benchmark chỉ với một customer_id không đại diện cho những khách có lịch sử hàng chục nghìn đơn hoặc những khách chỉ có một đơn.

## 7. Ca thực hành B: lọc trạng thái và ngày

Truy vấn điều hành:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders
WHERE status = 'PAID'
  AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Trong dữ liệu mẫu, PAID chiếm phần lớn đơn, vì vậy index **chỉ trên status** có thể có tính chọn lọc thấp. Thay vì thêm index một cột theo thói quen, đánh giá một **partial index**:

~~~sql
CREATE INDEX idx_orders_paid_recent
ON orders (created_at DESC, order_id DESC)
WHERE status = 'PAID';
~~~

Điểm mạnh có thể có:

- Chỉ chứa các hàng thuộc nhóm PAID.
- Dùng ngày tạo để giới hạn miền thời gian và phục vụ ORDER BY.
- Có thể trả sớm khi đủ 50 hàng ở thời điểm gần nhất.

Nhưng nếu phần lớn bảng đều PAID, partial index vẫn có thể **rất lớn**. Mức lợi ích phụ thuộc độ chọn lọc theo thời gian, kích thước index, cập nhật trạng thái và số hàng phải lấy từ heap.

### 7.1. Partial index phụ thuộc tính suy ra của điều kiện

Planner phải biết điều kiện WHERE của truy vấn **hàm ý** predicate của partial index. Truy vấn với **status = 'PAID'** là trường hợp rõ. Nhưng một câu lệnh chuẩn bị với **status = $1** có thể không sử dụng partial index trong **generic plan** vì giá trị tham số không cố định khi lập kế hoạch.

Không nên kết luận partial index “không hoạt động” chỉ vì thử một câu SQL hằng rồi ứng dụng dùng câu SQL tham số. Phải benchmark **đúng dạng truy vấn ứng dụng phát ra**, kể cả tình huống custom plan/generic plan và phân bố giá trị của tham số.

### 7.2. Dữ liệu theo thời gian phải phản ánh vận hành

Khi đơn hàng cũ chiếm 95% bảng, chỉ 5% là dữ liệu mới, index theo created_at có thể rất hữu ích cho màn hình thời gian gần đây. Nhưng trên một bảng thử chỉ chứa 7 ngày dữ liệu, cùng truy vấn có thể đọc gần như toàn bảng.

Vì vậy cần tạo cả:

- Dữ liệu **mới và cũ** theo phân bố tuổi thực tế.
- Các giai đoạn cao điểm nếu nghiệp vụ có mùa vụ.
- Các trạng thái có tỷ lệ hợp lý và có thể tương quan với tuổi đơn.
- Các bản ghi được sửa/xóa thường xuyên để đánh giá MVCC, VACUUM và index bloat nếu đó là đặc điểm production.

## 8. Ca thực hành C: tổng hợp doanh số theo sản phẩm

Yêu cầu báo cáo: với những đơn PAID trong 30 ngày gần đây, lấy 20 sản phẩm có số lượng bán cao nhất.

~~~sql
SELECT l.product_id,
       SUM(l.quantity)::BIGINT AS units_sold
FROM orders AS o
JOIN order_lines AS l ON l.order_id = o.order_id
WHERE o.status = 'PAID'
  AND o.created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
GROUP BY l.product_id
ORDER BY units_sold DESC, l.product_id
LIMIT 20;
~~~

Câu SQL này đo **số lượng đơn vị hàng bán**, không đo **doanh thu**. Nếu cần doanh thu, phải cộng lượng × đơn giá giao dịch, có quy tắc hoàn tiền/điều chỉnh, tiền tệ và thời điểm ghi nhận. Không thay đơn giá đã mua bằng list_price_cents hiện tại của Product.

### 8.1. Cần xem gì trong kế hoạch?

- **Orders có được lọc sớm không?** Số đơn PAID trong 30 ngày là bao nhiêu so với toàn bộ bảng?
- **Kiểu JOIN là gì?** Hash Join, Nested Loop hay Merge Join; vì sao optimizer chọn kiểu đó?
- **OrderLine được truy cập như thế nào?** Qua PK(order_id, line_no) cho từng Order hay quét phần lớn OrderLine?
- **Ước lượng trước GROUP BY:** số hàng đầu vào là bao nhiêu?
- **Bước GROUP BY/SORT có spill ra disk không?** Có temp read/written hoặc Sort Method external không?
- **LIMIT 20 có giúp tránh phần tổng hợp không?** Thường **không**: để biết top 20 sản phẩm, vẫn phải tổng hợp những hàng đủ điều kiện trước khi sắp xếp/chọn top.

Đừng kỳ vọng chỉ thêm index trên product_id là đủ để tăng tốc mọi truy vấn top sản phẩm. Đây là truy vấn **tổng hợp theo điều kiện của Order**, có thể bị chi phối bởi số dòng phải đọc, kiểu JOIN và chi phí tổng hợp.

### 8.2. Kiểm tra khả năng tăng tốc theo truy vấn nguồn

Nếu chương trình thường lọc Order trước rồi tra các OrderLine của từng đơn, PK **(order_id, line_no)** đã hỗ trợ truy vấn OrderLine theo order_id.

Nếu ứng dụng còn thường dùng mẫu:

~~~sql
SELECT order_id, line_no, quantity
FROM order_lines
WHERE product_id = 52
ORDER BY order_id DESC
LIMIT 100;
~~~

thì có thể cân nhắc một chỉ mục khác:

~~~sql
CREATE INDEX idx_order_lines_product_order
ON order_lines (product_id, order_id DESC);
~~~

Chỉ mục này phục vụ một **mẫu truy vấn khác**, không được giả định là cách tối ưu chắc chắn cho GROUP BY toàn bộ sản phẩm. Mọi index bổ sung phải được so sánh với chi phí tăng dung lượng và tốc độ nhập OrderLine.

### 8.3. Khi nào cần bảng tổng hợp?

Nếu báo cáo tương tự được gọi liên tục và phải quét dữ liệu rất lớn, có thể cân nhắc bảng tổng hợp theo ngày:

~~~text
product_daily_sales(
    sales_date,
    product_id,
    units_sold,
    gross_amount_cents,
    currency,
    ...
)
~~~

Cấu trúc dẫn xuất có thể giảm lượng dữ liệu đọc cho báo cáo, nhưng tạo thêm nghĩa vụ:

- Xác định **grain**: một hàng là một ngày–sản phẩm–tiền tệ.
- Xử lý đơn CANCELLED, hoàn hàng và điều chỉnh sau ngày ghi nhận.
- Cập nhật đồng bộ hay bất đồng bộ? Chấp nhận trễ bao lâu?
- Bảo đảm **idempotency**, tránh cộng doanh số hai lần khi job chạy lại.
- Có cách so sánh tổng hợp với **nguồn giao dịch gốc** để phát hiện sai lệch.

Không nên phi chuẩn hóa thành một bảng cộng dồn ngay khi chưa có bằng chứng rằng kế hoạch đọc dữ liệu nguồn thật sự không đạt yêu cầu.

## 9. Vì sao planner ước lượng sai số hàng?

Ngay cả một bộ index hợp lý cũng có thể không được sử dụng nếu planner đánh giá sai số hàng. PostgreSQL dựa trên thống kê và giả định có giới hạn; một số nguồn sai lệch phổ biến:

| Nguyên nhân | Dấu hiệu | Hướng kiểm tra |
| --- | --- | --- |
| **Thống kê cũ** | estimated rows lệch nhiều sau nạp/xóa dữ liệu lớn | ANALYZE, autovacuum/autoanalyze |
| **Skew** | Giá trị “hot” có kết quả khác hẳn giá trị trung bình | Đo top values, most common values |
| **Tương quan giữa cột** | Điều kiện kết hợp ước lượng sai dù từng cột có thống kê | Extended statistics khi phù hợp |
| **Dữ liệu thời gian tích lũy** | Dữ liệu gần hiện tại khác hẳn dữ liệu cũ | Histogram, partition/bộ thống kê cập nhật |
| **Biểu thức/function trong WHERE** | Số hàng ước lượng kém hoặc khó dùng index | Xem biểu thức có thể tối ưu thành range không |
| **Tham số truy vấn** | Cùng câu SQL nhưng hiệu năng khác giữa giá trị | Custom/generic plan và phân bố tham số |
| **JOIN nhiều–nhiều** | Kết quả lớn hơn dự kiến | Kiểm tra bội số, khóa, FK, grain và điều kiện JOIN |

### 9.1. Kiểm tra thống kê cơ bản

~~~sql
SELECT schemaname, tablename, attname,
       null_frac, n_distinct,
       most_common_vals, most_common_freqs
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename IN ('orders', 'order_lines')
  AND attname IN ('customer_id', 'status', 'product_id')
ORDER BY tablename, attname;
~~~

Bảng hệ thống **pg_stats** có thể cho thấy phân bố được lấy mẫu, bao gồm các giá trị phổ biến và tỷ lệ của chúng. Đây là thống kê **ước lượng**, không phải bản kiểm kê chính xác của mọi hàng. Đọc cùng các truy vấn COUNT/GROUP BY nếu cần xác minh nhóm hot.

Khi thống kê của cột không đủ chi tiết, có thể cân nhắc điều chỉnh **statistics target** và ANALYZE lại, nhưng điều này làm tăng chi phí phân tích và kích thước thống kê.

~~~sql
-- Ví dụ: chỉ dùng khi đã xác định sai lệch ước lượng đáng kể.
ALTER TABLE orders
ALTER COLUMN customer_id SET STATISTICS 500;

ANALYZE orders;
~~~

Không tăng statistics target cho mọi cột theo thói quen. Hãy đo ảnh hưởng lên kế hoạch sau thay đổi và cân nhắc bảo trì.

### 9.2. Extended statistics: cột tương quan nhau

Nếu trạng thái PAID gần như chỉ xuất hiện ở nhóm đơn cũ hoặc một vùng khách hàng, giả định độc lập giữa các cột có thể khiến ước lượng tổ hợp sai.

PostgreSQL hỗ trợ extended statistics cho một số quan hệ giữa cột trong **cùng bảng**, chẳng hạn:

~~~sql
CREATE STATISTICS st_orders_status_customer
    (mcv, dependencies)
ON status, customer_id
FROM orders;

ANALYZE orders;
~~~

Nó có thể giúp planner nhận diện **tổ hợp giá trị phổ biến** hoặc phụ thuộc giữa các cột. Tuy nhiên, extended statistics **không phải thuốc chữa mọi lỗi ước lượng**, nhất là ước lượng liên bảng hoặc một số điều kiện range/phức tạp; khả năng sử dụng tùy kiểu thống kê, truy vấn và phiên bản PostgreSQL.

### 9.3. Truy vấn viết theo cách cản trở index

Ví dụ muốn lọc đơn trong ngày cụ thể:

~~~sql
-- Có thể làm việc dùng index thường trên created_at kém thuận lợi:
SELECT order_id
FROM orders
WHERE created_at::date = DATE '2026-11-20';
~~~

Với TIMESTAMPTZ, phép chuyển sang DATE còn phụ thuộc múi giờ của session. Nếu yêu cầu là **ngày theo múi giờ nghiệp vụ**, nên xác định ranh giới thời gian rõ và dùng range nửa mở:

~~~sql
-- Ví dụ ngày 20/11/2026 theo UTC.
SELECT order_id
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-11-20 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-21 00:00:00+00';
~~~

Cách viết range thường dễ sử dụng B-tree trên created_at. Nhưng nếu yêu cầu ngày theo múi giờ Việt Nam, phải chuyển **hai ranh giới địa phương** sang instant tương ứng; không được ngầm thay bằng UTC vì kết quả nghiệp vụ sẽ khác.

## 10. Phân trang, ORDER BY và LIMIT

Một quyết định tưởng là ở tầng API có thể thay đổi hoàn toàn kế hoạch truy vấn.

### 10.1. OFFSET sâu

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 10000;
~~~

Dù có index hỗ trợ thứ tự, DBMS có thể vẫn cần **đi qua hơn 10.000 hàng** trước khi bỏ chúng để trả 20 hàng. OFFSET phù hợp cho một số giao diện phân trang nông, nhưng có thể tốn chi phí với trang rất sâu.

### 10.2. Keyset pagination

Nếu màn hình đã biết **created_at và order_id của dòng cuối trang trước**, dùng con trỏ:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
  AND (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-20 10:15:00+00', 123456)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Với thứ tự giảm dần ở cả hai cột và khóa phân biệt order_id, điều kiện so sánh tuple giúp tiếp tục từ một điểm trong thứ tự thay vì bỏ qua một lượng lớn hàng. Mẫu truy vấn phải dùng **đúng cặp khóa sắp xếp**, có tie-breaker ổn định và tính đến việc dữ liệu có thể được chèn/cập nhật giữa các lần gọi.

**Không dùng giá trị cursor ví dụ như dữ liệu thực.** Ứng dụng phải trả cursor từ hàng cuối cùng đã lấy. Nếu sort order có nhiều chiều khác hướng, biểu thức so sánh cần được viết lại tương ứng.

### 10.3. Kiểm tra tính xác định của thứ tự

ORDER BY created_at DESC đơn độc có thể không xác định thứ tự khi nhiều đơn cùng thời điểm. Dùng **order_id DESC** làm tie-breaker giúp phân trang ổn định hơn, nhất là khi so sánh query plan giữa những lần benchmark. Khi cơ sở dữ liệu cập nhật đồng thời, kết quả giữa các trang vẫn có thể thay đổi; tính ổn định đầy đủ cần chính sách snapshot hoặc cách phục vụ feed phù hợp.

## 11. Chỉ mục là một đánh đổi, không phải số điểm thành tích

Một index có lợi khi giúp query tránh đọc/sort quá nhiều dữ liệu, nhưng nó cũng:

- Chiếm không gian lưu trữ và ảnh hưởng đến backup/replication.
- Làm INSERT, UPDATE, DELETE có thêm việc bảo trì.
- Có thể tăng WAL và tình trạng index bloat.
- Làm thay đổi kế hoạch của các truy vấn khác, đôi khi không như kỳ vọng.
- Cần xét mức chọn lọc và phân bố dữ liệu, không chỉ tên cột.

### 11.1. Thứ tự cột trong index ghép

Index:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
~~~

hữu ích cho truy vấn tìm đơn của **một khách** rồi sắp theo created_at. Nhưng truy vấn chỉ lọc created_at trên **mọi khách hàng** có thể không được phục vụ tối ưu giống một index bắt đầu bằng created_at.

Trước khi tạo index mới, kiểm tra index đã có, phần tiền tố chung, ORDER BY, điều kiện bằng/range và các thay đổi trạng thái. Nhiều index gần giống nhau có thể làm tải ghi nặng hơn mà lợi ích đọc không tương xứng.

### 11.2. BRIN khi dữ liệu rất lớn và có thứ tự vật lý phù hợp

BRIN lưu tóm tắt theo vùng trang, có thể hữu ích cho cột thời gian trên bảng lớn nếu **giá trị created_at có tương quan với vị trí vật lý của dữ liệu**. Nó nhỏ hơn nhiều B-tree trong một số trường hợp, nhưng có thể phải đọc và kiểm tra thêm hàng do hoạt động theo vùng.

~~~sql
-- Minh họa một phương án để benchmark trên bảng đơn rất lớn:
CREATE INDEX idx_orders_created_brin
ON orders USING brin (created_at);
~~~

Không mặc định BRIN thắng B-tree. Trên bộ dữ liệu nạp với created_at xoay vòng theo n, thứ tự vật lý có thể **không tương quan tốt** với ngày tạo, nên BRIN có thể kém hiệu quả. Muốn đánh giá BRIN phải tạo dữ liệu theo thứ tự và cách nạp **gần vận hành thực**.

### 11.3. Partitioning không tự động tăng tốc

Partition theo thời gian thường được đề xuất khi Order có hàng trăm triệu dòng. Nó có thể giúp:

- Giới hạn số partition được truy cập nếu WHERE cho phép **partition pruning**.
- Quản lý dữ liệu cũ theo kỳ, ví dụ lưu trữ hoặc loại bỏ cả partition đúng chính sách.
- Phân tách một số thao tác bảo trì trên tập dữ liệu lớn.

Nhưng partition còn gây chi phí quản lý, thay đổi cách thiết kế khóa/unique, index, FK, kế hoạch và thao tác ghi. Nếu truy vấn không lọc partition key hoặc phải JOIN qua rất nhiều partition, lợi ích có thể ít hoặc âm.

**Không partition một bảng 250 nghìn dòng chỉ vì có cột created_at.** Hãy xác định vấn đề cụ thể: thời gian truy vấn, quản lý dữ liệu lịch sử, chỉ mục quá lớn hay bảo trì. Sau đó đo thử với một số partition và lượng dữ liệu đại diện.

## 12. Benchmark đúng: không chỉ chạy một truy vấn một lần

Một lần EXPLAIN ANALYZE là **bằng chứng chẩn đoán**, chưa phải benchmark đủ tin cậy.

### 12.1. Thiết lập môi trường

Ghi lại ít nhất:

- Phiên bản PostgreSQL, extension liên quan, CPU/RAM/ổ đĩa.
- Các cấu hình liên quan: shared_buffers, work_mem, effective_cache_size, random_page_cost, max_parallel_workers_per_gather, cùng giá trị thực tế nếu đã điều chỉnh.
- Quy mô từng bảng, kích thước dữ liệu và index, độ phân bố, mức độ phân mảnh.
- Trạng thái ANALYZE/VACUUM, tỷ lệ bảng đang nằm trong cache.
- Có người dùng/job khác đang tạo tải đồng thời không.
- Dạng SQL đúng với ứng dụng: JOIN, tham số, LIMIT, thứ tự, SELECT list và isolation level.

Không cần sao chép toàn bộ cấu hình hệ thống vào bài kết quả, nhưng mọi yếu tố có thể thay đổi kết luận nên được ghi. Đừng đem số ms đo trên laptop so trực tiếp với production rồi gọi đó là tốc độ dự đoán.

### 12.2. Phân biệt warm cache và cold cache

- **Warm cache:** dữ liệu/index thường xuyên dùng đã nằm trong cache, truy vấn có thể ít phải đọc từ lưu trữ.
- **Cold cache:** dữ liệu chưa sẵn trong cache, phải nạp nhiều hơn qua tầng bộ đệm/hệ điều hành.

Một truy vấn có thời gian đầu tiên cao hơn nhiều lần sau chưa chắc là lỗi. Ngược lại, luôn benchmark trên warm cache có thể che khuất vấn đề với tập dữ liệu lớn hơn RAM.

Không nên vô tư xóa cache của máy dùng chung để tạo cold cache. Thay vào đó dùng môi trường riêng, quy trình đo thống nhất và ghi rõ điều kiện bộ đệm. Lặp nhiều lần, bỏ qua hoặc tách riêng giai đoạn khởi động nếu phù hợp.

### 12.3. Số lần đo và cách tổng hợp

Một quy trình có thể áp dụng:

1. Nạp dữ liệu thử và ANALYZE.
2. Ghi kế hoạch/độ trễ trước khi sửa.
3. Chạy nhiều lần trên các loại tham số: khách hot, khách ít đơn, khoảng ngày rộng/hẹp.
4. Ghi median, p95, max, số hàng trả về, buffers và biến động thời gian.
5. Thay **một yếu tố** (ví dụ chỉ thêm idx_orders_customer_recent).
6. Lặp đúng bộ tham số và tải tương đương.
7. Đo lại **tốc độ ghi**, dung lượng index và các truy vấn quan trọng khác.
8. Kết luận dựa trên tiêu chí chấp nhận đã đặt trước, không chỉ một kết quả nhanh nhất.

Ví dụ bảng ghi kết quả **để điền sau khi chạy**, không phải số liệu đã đo:

| Truy vấn | Tập tham số | Kế hoạch | p50 (ms) | p95 (ms) | Buffers/read | Hàng trả về |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Lịch sử đơn | Khách phổ biến | Trước index | — | — | — | — |
| Lịch sử đơn | Khách phổ biến | Sau index | — | — | — | — |
| Lịch sử đơn | Khách ít đơn | Trước index | — | — | — | — |
| Lịch sử đơn | Khách ít đơn | Sau index | — | — | — | — |
| Top sản phẩm | 30 ngày | Trước thay đổi | — | — | — | — |
| Top sản phẩm | 30 ngày | Sau thay đổi | — | — | — | — |

Một giá trị p95 từ 5 lần chạy là rất kém ổn định. Để đánh giá phân vị, cần đủ số quan sát, thứ tự thử giảm thiên lệch do cache và mô tả chính xác cách chọn tham số. Khi tính p95 của **API**, cần đo tại cấp request dưới tải đại diện; không coi thời gian nội bộ EXPLAIN là p95 toàn hệ thống.

### 12.4. Phép đo một phiên và nhiều phiên

**EXPLAIN ANALYZE** của một truy vấn đơn lẻ cho biết cách nó chạy trong điều kiện lúc đó. Nó **không** đo được đầy đủ thông lượng, thời gian chờ pool connection, lock contention, transaction throughput và tải I/O của hàng chục phiên.

Benchmark tải đồng thời cần công cụ điều phối request/giao dịch phù hợp trong môi trường cho phép, định nghĩa rõ tỉ lệ đọc–ghi, tốc độ đến của request và thời gian kiểm thử. Không ép nhiều phiên “càng nhiều càng tốt” rồi gán mức tắc nghẽn gây ra cho một index cụ thể khi chưa phân tích giới hạn CPU, I/O, khóa và pool.

## 13. Tốc độ đọc tốt nhưng ghi có còn đúng và đủ nhanh?

Thêm chỉ mục để tăng tốc lịch sử đơn có thể làm giảm tốc độ tạo đơn, cập nhật trạng thái hoặc xóa dữ liệu cũ. Một đánh giá thiết kế vật lý phải tính hai chiều.

### 13.1. Đo đường ghi chính

Đặt các phép thử riêng cho:

- INSERT Order và 5 OrderLine trong một giao dịch.
- UPDATE Order từ PENDING sang PAID.
- UPDATE trạng thái hoặc địa chỉ giao hàng.
- Thao tác hủy/hoàn hàng (nếu được mô hình hóa).
- Lưu trữ dữ liệu cũ hoặc chuyển phân vùng.

Khi một index chứa **status** là cột được INCLUDE, việc thay đổi status vẫn có thể yêu cầu bảo trì index. Một thay đổi index giúp SELECT không nhất thiết miễn phí ở đường ghi.

### 13.2. Không bỏ qua FK và tính nguyên tử

Ví dụ benchmark có đơn và dòng đơn, cần duy trì **OrderLine trỏ tới Order tồn tại**. Nếu bỏ FK để nạp nhanh rồi không bật lại trong sản phẩm cuối, ta đang đo một thiết kế **khác** với thiết kế nghiệp vụ đã yêu cầu.

Tương tự, nếu tạo đơn gồm 5 dòng cần được ghi nguyên tử, phải benchmark một transaction có cả Order và OrderLine. So sánh với việc nạp từng dòng bằng autocommit hoặc COPY batch chỉ có giá trị nếu đó là đường ghi thật hoặc là một phép thử riêng được ghi nhãn rõ.

### 13.3. Trường hợp chỉ số đẹp nhưng sai chức năng

Một truy vấn trả 20 dòng rất nhanh nhưng:

- sắp xếp sai khi hai dòng cùng timestamp;
- bỏ qua điều kiện tenant_id;
- JOIN Product với trạng thái hiện tại để tính giá lịch sử;
- nhân bản OrderLine vì JOIN quan hệ nhiều–nhiều;
- hoặc chỉ đọc một phần dữ liệu do phân trang không ổn định;

thì không đạt yêu cầu. **Tính đúng đắn là điều kiện tiên quyết**, không phải chỉ số có thể đánh đổi lấy độ trễ thấp.

## 14. Kiểm thử ở quy mô phù hợp: nhiều kích thước và tình huống biên

Một tập dữ liệu đại diện thường cần **nhiều chiều và nhiều mức tải**, không chỉ một giá trị N.

| Kịch bản | Điều cần thử | Dấu hiệu có thể lộ ra |
| --- | --- | --- |
| Nhỏ (1–10 nghìn dòng) | Tính đúng, kiểm tra SQL/constraint | Index đôi khi không được chọn do bảng nhỏ |
| Trung bình (vài trăm nghìn) | Truy vấn tra cứu, JOIN, sort | Nút thắt kế hoạch đầu tiên |
| Lớn (hàng triệu–chục triệu) | Cardinality, I/O, index size | Sort/hash spill, scan quá rộng |
| Rất lớn (theo dự báo thực tế) | Partition/retention, bảo trì | Chi phí vacuum, index bloat, backup |
| Dữ liệu hot/cold | Giá trị phổ biến/hiếm | Kế hoạch phụ thuộc tham số |
| Dữ liệu lệch | 70% vào một nhóm, nhiều NULL | Sai lệch estimated vs actual |
| Dữ liệu lịch sử | Cũ nhiều, mới ít | Index theo thời gian, BRIN/partition |
| Ghi đồng thời | Nhiều giao dịch trên cùng khóa | Lock, retry, deadlock |
| Gần giới hạn nghiệp vụ | Khách cực nhiều đơn, bảng con cực lớn | Pagination sâu, nested-loop lặp lớn |

**Không phải bảng nào cũng cần hàng chục triệu dòng để benchmark.** Tỷ lệ dữ liệu và dạng truy vấn phải tương xứng với nhu cầu. Chẳng hạn bảng mã tiền tệ có vài trăm hàng; cố nhân lên hàng triệu sẽ tạo một tình huống không liên quan đến vận hành.

Đồng thời, nếu đơn hàng dự báo tăng từ 250 nghìn lên 50 triệu sau vài năm, phải thử ít nhất một mức đủ lớn để lộ chi phí **lưu trữ, index, JOIN và bảo trì**; không chỉ nhân tuyến tính thời gian đo ở 250 nghìn rồi cho rằng kết luận luôn đúng.

## 15. Vị trí của document, graph và mô hình phân tích

Cùng một quy trình “đề xuất → đo → đọc kế hoạch → kiểm chứng” có thể áp dụng với công nghệ khác, nhưng công cụ và số liệu cụ thể thay đổi.

| Kiểu lưu trữ | Cần kiểm tra | Dữ liệu đại diện quan trọng |
| --- | --- | --- |
| **Quan hệ (PostgreSQL)** | EXPLAIN/ANALYZE, scan, JOIN, sort/hash, buffers, index | Số hàng, độ chọn lọc, skew, tương quan, NULL, độ rộng hàng |
| **Document** | Explain của query/aggregation, index và số document examined, sort/lookup | Kích thước document, độ dài mảng, cấu trúc lồng, tỷ lệ field vắng |
| **Graph** | Traversal depth, branching factor, số cạnh đi qua, đường đi trả về | Bậc nút, đỉnh hub, số đường đi, chu trình, loại quan hệ |
| **Warehouse/OLAP** | Partition pruning, scan bytes, shuffle, spill, join/aggregation | Số fact, grain, độ rộng, cardinality dimension, skew phân vùng |

### 15.1. Document: đừng chỉ đếm document

Một hệ thống document có 100 nghìn Customer, mỗi Customer chứa mảng Orders, không tương đương về chi phí với 100 nghìn Customer mà mỗi người có 2 Order. Cần đo:

- Kích thước trung bình và **p95/p99** của document.
- Số phần tử mảng trung bình/tối đa.
- Truy vấn lọc theo phần tử lồng, index đa khóa và chi phí cập nhật document lớn.
- Việc nhúng và tham chiếu có làm nhân bản dữ liệu hay tạo update nhiều document không.

“Ít JOIN hơn” chưa chứng minh document nhanh hơn; cần kiểm tra chi phí đọc/ghi trên mẫu thực tế.

### 15.2. Graph: số nút không đủ

Một đồ thị có một triệu nút nhưng mỗi nút chỉ có hai cạnh khác với một đồ thị có một số **hub nối hàng trăm nghìn cạnh**. Truy vấn đường đi độ dài 2–4 bước có thể mở rộng rất lớn tại hub.

Đánh giá graph cần số cạnh đã duyệt, độ sâu, bậc nút, tỉ lệ trùng đường, giới hạn traversal và chính sách chu trình. Nếu dùng dữ liệu đồ thị sinh ngẫu nhiên đồng đều, có thể bỏ sót vấn đề chủ yếu của dữ liệu thật.

### 15.3. Warehouse: đừng nhầm độ trễ truy vấn với chi phí xử lý

Một kho phân tích thường tối ưu scan theo cột, phân vùng và tổng hợp trên tập rất lớn. Cần đánh giá **số byte quét**, số hàng shuffle, spill, độ lệch khóa JOIN và cách xử lý dimension nhiều–nhiều.

Nếu JOIN fact với bridge tạo nhiều dòng cho một sự kiện, kết quả tính tiền có thể sai. Phải xác định **grain** và quy tắc phân bổ trước khi kết luận kế hoạch “nhanh và đúng”.

## 16. Hồ sơ thí nghiệm và tiêu chí chấp nhận

Một thay đổi chỉ mục hoặc cấu trúc vật lý nên đi kèm hồ sơ ngắn nhưng đủ để người khác tái hiện:

~~~text
Đề xuất:
  Thêm index (customer_id, created_at DESC, order_id DESC)
  INCLUDE(status) trên orders.

Giả thuyết:
  Giảm số hàng cần đọc/sort để lấy 20 đơn mới nhất của một khách.
  Chấp nhận tăng dung lượng index và chi phí ghi ở mức đã đo.

Môi trường:
  PostgreSQL version, cấu hình quan trọng, CPU/RAM/storage.
  Dataset version, ngày tạo, row counts, phân bố khách hot/cold.
  Trạng thái ANALYZE/VACUUM, cache và tải nền.

Truy vấn:
  SQL nguyên vẹn, loại tham số, giới hạn thời gian, LIMIT.
  Nhóm tham số: hot, thông thường, không có đơn.

Kết quả trước/sau:
  EXPLAIN (ANALYZE, BUFFERS) lưu lại.
  Rows estimated/actual, node scan/join/sort.
  p50/p95 qua nhiều lần chạy với cùng điều kiện.
  Độ lớn index, INSERT/UPDATE latency và tác động khác.

Quyết định:
  ACCEPT / REJECT / NEEDS MORE DATA.
  Lý do dựa trên tiêu chí đã thống nhất, không chỉ một số ms.
~~~

Nếu dữ liệu thử khác production đáng kể, phải ghi rõ **giới hạn hiệu lực của kết luận**. Ví dụ: “Kết quả đáng tin cho truy vấn theo một customer và 250 nghìn Order, chưa chứng minh hiệu năng khi đạt 50 triệu Order hoặc 200 phiên đồng thời”.

## 17. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đo trên vài chục bản ghi | Kế hoạch nhỏ không đại diện quy mô thật | Tạo nhiều mức dữ liệu và phân bố phù hợp |
| Chỉ dùng dữ liệu ngẫu nhiên đồng đều | Bỏ sót hot key, skew và tương quan | Tạo/ẩn danh dữ liệu có phân bố đại diện |
| Đọc cost như mili giây | Kết luận sai từ ước lượng của planner | Phân biệt cost và actual time |
| Chỉ nhìn tên Scan | Bỏ qua số hàng bị lọc, loops, buffers | Đọc cả cây kế hoạch |
| Cho rằng Seq Scan luôn tệ | Tạo index không hữu ích, tăng chi phí ghi | So sánh lượng dữ liệu đọc và tổng chi phí |
| Chỉ thử một customer_id | Kế hoạch tốt cho nhóm thường, tệ cho nhóm hot | Thử nhiều nhóm tham số |
| Không ANALYZE sau nạp hàng loạt | Planner dùng thống kê thiếu/cũ | Cập nhật thống kê có kiểm soát |
| Thêm index theo mọi cột WHERE | Index trùng, khó bảo trì, ghi chậm | Thiết kế theo predicate, order, selectivity |
| Kỳ vọng LIMIT làm GROUP BY rẻ | Vẫn phải đọc/tổng hợp dữ liệu nguồn | Kiểm tra plan; cân nhắc tổng hợp khi cần |
| Dùng EXPLAIN ANALYZE với DELETE trên DB thật | Thực thi thao tác xóa | Chỉ thử trên môi trường an toàn |
| Coi một lần chạy là p95 | Số liệu không có ý nghĩa thống kê | Lặp đủ lần, đo dưới tải đại diện |
| Benchmark chỉ đọc | Không biết index làm ghi chậm | Đo tỉ lệ đọc/ghi và transaction thực |
| Đổi nhiều thứ cùng lúc | Không biết nguyên nhân thay đổi kết quả | Thay một yếu tố hoặc thiết kế A/B rõ |
| Chỉ quan tâm thời gian | Có thể bỏ qua kết quả sai, trùng, mồ côi | Kiểm tra đúng dữ liệu và bất biến trước |
| Đánh giá partition theo số bảng | Phức tạp tăng mà không giải quyết nút thắt | Xác định vấn đề và đo partition pruning |

## 18. Bài tập tự kiểm tra có gợi ý giải

### Bài 1. Vì sao một chỉ mục không được chọn?

**Đề bài:** Bảng có 10 nghìn dòng. Truy vấn chọn 80% bảng và có index trên cột lọc. EXPLAIN vẫn cho Seq Scan. Đây có chắc là lỗi không?

**Gợi ý:** Không. Khi phải đọc phần lớn bảng, quét tuần tự có thể rẻ hơn truy cập qua index và nhiều heap page. Cần xem estimated/actual rows, buffers, độ rộng hàng và thời gian thực, không chỉ tên nút.

### Bài 2. Index cho lịch sử đơn hàng

**Đề bài:** Truy vấn WHERE customer_id = ? ORDER BY created_at DESC, order_id DESC LIMIT 20 trên bảng hàng triệu Order. Đề xuất index nào và phải đo gì?

**Gợi ý:** Cân nhắc index **(customer_id, created_at DESC, order_id DESC)**; nếu chỉ SELECT thêm status, có thể thử INCLUDE(status). Đo plan, Sort, số hàng, buffer, p50/p95 với khách hot/cold; đo cả dung lượng và tốc độ INSERT/UPDATE vì index thêm chi phí ghi.

### Bài 3. Ước lượng sai nghiêm trọng

**Đề bài:** Một Nested Loop ước lượng 20 hàng ngoài nhưng thực tế nhận 80.000 hàng; nút trong chạy hàng chục nghìn lần. Có nên lập tức buộc Hash Join?

**Gợi ý:** Chưa. Kiểm tra nguyên nhân estimated/actual rows lệch: thống kê cũ, skew, tương quan, tham số, điều kiện JOIN. Cập nhật ANALYZE/thống kê hoặc thiết kế index/truy vấn; sau đó đo lại. Bắt planner dùng một kiểu JOIN có thể che vấn đề thay vì giải quyết gốc.

### Bài 4. LIMIT trên tổng hợp

**Đề bài:** SELECT product_id, SUM(quantity) FROM order_lines GROUP BY product_id ORDER BY SUM(quantity) DESC LIMIT 10. Vì sao LIMIT 10 không bảo đảm chỉ đọc 10 hàng?

**Gợi ý:** Để biết top 10 sản phẩm phải tổng hợp những dòng đầu vào phù hợp, thường là nhiều hay toàn bộ OrderLine. LIMIT hạn chế kết quả cuối, không tự loại bỏ công việc nhóm. Index hoặc bảng tổng hợp cần được đánh giá theo mẫu truy vấn cụ thể.

### Bài 5. Dữ liệu benchmark có đúng phân bố?

**Đề bài:** Dữ liệu production có một số khách với hàng trăm nghìn đơn, nhưng generator chia đều đơn cho mọi khách. Có thể rút ra kết luận hiệu năng theo khách hot không?

**Gợi ý:** Không đáng tin. Cần mô phỏng skew phù hợp và thử nhiều nhóm tham số. Nên ghi phân bố, độ sâu lịch sử, tỷ lệ trạng thái/NULL và kích thước các bảng để biết kết luận áp dụng trong phạm vi nào.

### Bài 6. EXPLAIN ANALYZE có vô hại?

**Đề bài:** Một người chạy EXPLAIN ANALYZE DELETE FROM orders WHERE created_at < ... trên production chỉ để xem thời gian xóa.

**Gợi ý:** Đây là thao tác nguy hiểm vì EXPLAIN ANALYZE **thực thi DELETE**. Chỉ dùng EXPLAIN không ANALYZE để xem kế hoạch dự kiến hoặc chạy phép thử có kiểm soát trên môi trường tách biệt. ROLLBACK trong một transaction thử không bảo đảm hoàn nguyên mọi side effect ngoài giao dịch.

### Bài 7. BRIN hay B-tree?

**Đề bài:** Bảng sự kiện rất lớn, created_at tăng gần theo thứ tự ghi, phần lớn truy vấn lọc một tuần. Nên đánh giá gì?

**Gợi ý:** Cân nhắc B-tree và BRIN theo dữ liệu và thứ tự vật lý. BRIN có thể nhỏ, hữu ích khi tương quan vật lý tốt nhưng phải đọc/recheck nhiều trang; B-tree thường chọn lọc chính xác hơn nhưng lớn và tốn bảo trì hơn. Đo kế hoạch và I/O trên quy mô thích hợp.

### Bài 8. Nhiều index nhưng API vẫn chậm

**Đề bài:** SQL tại server p50 thấp nhưng API p95 cao. Có thể kết luận thiếu index không?

**Gợi ý:** Không. Phải đo end-to-end, phân biệt thời gian connection pool, lock, mạng, serialization, logic ứng dụng, hàng đợi và tải đồng thời. Chỉ mục là một giả thuyết, không phải câu trả lời mặc định.

### Bài 9. JOIN làm sai tổng doanh số

**Đề bài:** Báo cáo doanh thu JOIN OrderLine với hai bảng đa trị độc lập rồi SUM(amount), làm mỗi dòng hóa đơn xuất hiện nhiều lần. Nếu EXPLAIN chạy nhanh, có thể chấp nhận không?

**Gợi ý:** Không. Kết quả **sai** do grain của phép JOIN. Cần tổng hợp trước, chọn quan hệ đúng hoặc phân bổ có quy tắc. Tính đúng nghiệp vụ luôn phải kiểm chứng trước tốc độ.

### Bài 10. Partition có giải quyết mọi truy vấn?

**Đề bài:** Orders chia partition theo created_at. Truy vấn chỉ lọc customer_id và không lọc created_at. Có thể chắc chắn chỉ đọc một partition không?

**Gợi ý:** Không. Không có điều kiện partition key phù hợp, planner có thể phải xét nhiều hoặc tất cả partition. Cần kiểm tra partition pruning và kế hoạch thực tế; partition làm tăng chi phí quản trị, không phải phép tối ưu chung cho mọi query.

## 19. Ghi nhớ

- **Kế hoạch truy vấn là bằng chứng về cách DBMS thực thi hoặc dự định thực thi**, không phải mục tiêu tự thân. Đọc cây toán tử, estimated/actual rows, loops, filter, sort/hash, buffer và thời gian trong ngữ cảnh.
- **EXPLAIN** không chạy SELECT; **EXPLAIN ANALYZE** thực thi câu lệnh bên dưới. Không thử DML có tác động trên dữ liệu thật.
- **Quy mô đúng chưa đủ; phân bố cũng phải đúng.** Hot key, dữ liệu lệch, tỷ lệ NULL, lịch sử và tương quan giữa cột có thể quyết định kế hoạch.
- **Một index tốt phụ thuộc query và tải.** Đo lợi ích đọc cùng chi phí ghi, dung lượng, bảo trì và tác động lên truy vấn khác.
- **Giữ đúng nghiệp vụ trước khi tối ưu.** JOIN tạo hàng trùng, phân trang sai thứ tự hay giá lịch sử bị thay đổi đều là thiết kế không đạt dù phản hồi nhanh.
- **Benchmark phải lặp lại, có đối chứng và ghi giới hạn kết luận.** Một lần chạy nhanh trên laptop không chứng minh hệ thống đạt p95 trong production.
- **Quan hệ, document, graph và warehouse đều cần phép đo tương ứng cấu trúc dữ liệu thực.** Không có công nghệ nào tự thay thế việc kiểm tra kế hoạch, dữ liệu và quy tắc nghiệp vụ.

Một quyết định mô hình vật lý đáng tin phải trả lời được: **Với dữ liệu và tải nào, truy vấn nào được cải thiện, cải thiện bao nhiêu theo số đo, đánh đổi điều gì, và có giữ nguyên tính đúng đắn hay không?** Đó là cách biến thiết kế dữ liệu từ giả định thành lựa chọn kỹ thuật có thể kiểm chứng và tiến hóa.
