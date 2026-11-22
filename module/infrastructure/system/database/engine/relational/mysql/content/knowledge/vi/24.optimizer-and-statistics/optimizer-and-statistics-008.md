# Join order, access path và lựa chọn thuật toán JOIN

Khi thực thi một truy vấn nối nhiều bảng, MySQL phải quyết định ba việc có liên quan nhưng khác nhau: **join order** xác định bảng nào được xử lý trước; **access path** xác định cách đọc hàng của từng bảng; **join algorithm** xác định cách kết hợp các tập hàng. Một truy vấn viết `customers JOIN orders JOIN order_items` không có nghĩa MySQL luôn đọc bảng theo đúng thứ tự văn bản đó.

MySQL dùng optimizer dựa trên chi phí để ước lượng số hàng, độ chọn lọc của điều kiện, chi phí đọc index/table và chi phí kết hợp các bảng. Với cùng câu SQL, kế hoạch có thể thay đổi khi dữ liệu, thống kê, index hoặc phiên bản thay đổi. Vì vậy, cần đọc `EXPLAIN` và đối chiếu bằng `EXPLAIN ANALYZE` thay vì đoán kế hoạch từ thứ tự các bảng trong câu lệnh.

Trong module `DATABASE_MYSQL`, hiểu ba quyết định này giúp giải thích vì sao một JOIN nhanh trên dữ liệu nhỏ lại chậm khi dữ liệu tăng, vì sao optimizer chọn sai bảng dẫn đầu, và khi nào index lookup hoặc hash join phù hợp. Bài học tập trung vào MySQL 8.0 trở lên với InnoDB.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt join order, access path và join algorithm.
- Giải thích cách optimizer ước lượng chi phí và chọn thứ tự nối bảng.
- Đọc thứ tự bảng trong `EXPLAIN` dạng tabular, JSON và TREE.
- Phân biệt table scan, index lookup, range scan và covering access trong JOIN.
- Giải thích nested-loop join, index nested-loop join, batched key access và hash join.
- Thiết kế index cho phía outer và inner của nested-loop join.
- Nhận diện nguyên nhân optimizer chọn join order không phù hợp.
- Cải thiện thống kê bằng `ANALYZE TABLE` và histogram khi thích hợp.
- Dùng `EXPLAIN ANALYZE` để so sánh số hàng ước lượng với số hàng thực tế.
- Hiểu giới hạn khi ép join order và tác động của outer join.

## 1. Ba quyết định khi thực thi JOIN

Giả sử truy vấn nối khách hàng với đơn hàng:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42;
```

Optimizer phải trả lời ba câu hỏi:

1. **Join order:** đọc `customers` trước rồi tìm `orders`, hay đọc `orders` trước rồi tìm `customers`?
2. **Access path:** đọc bảng bằng table scan, index range scan, ref lookup, eq_ref lookup hay một đường truy cập khác?
3. **Join algorithm:** lặp qua từng hàng outer và tìm hàng inner, gom khóa để lookup theo lô, hay xây hash table rồi probe?

Ba quyết định không thay thế nhau. Ví dụ, optimizer có thể chọn `customers` làm bảng đầu tiên, dùng index range trên `tenant_id`, rồi dùng nested loop với index lookup trên `orders.customer_id`. Một kế hoạch khác có thể đọc `orders` theo index lọc trạng thái/ngày, sau đó tra `customers` bằng primary key.

## 2. Bộ dữ liệu thực hành

Các ví dụ tiếp theo dùng bốn bảng: khách hàng, đơn hàng, dòng đơn hàng và sản phẩm. Tạo bảng trong schema lab riêng:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    customer_status VARCHAR(20) NOT NULL,
    external_customer_code VARCHAR(30) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_customers_tenant (tenant_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_status_time
        (customer_id, status, created_at),
    KEY idx_orders_status_time
        (status, created_at, order_id, customer_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(160) NOT NULL,
    category_id BIGINT UNSIGNED NOT NULL,
    is_active TINYINT(1) NOT NULL,
    PRIMARY KEY (product_id),
    KEY idx_products_category (category_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY idx_order_items_order (order_id),
    KEY idx_order_items_product (product_id, order_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Các index trên `orders` thể hiện hai hướng truy cập có thể hữu ích: bắt đầu từ khách hàng rồi lookup đơn, hoặc bắt đầu từ trạng thái/thời gian rồi lookup khách hàng. Không có nghĩa mọi hệ thống nên giữ cả hai index; chúng được tạo để so sánh kế hoạch và chi phí ghi trong lab. Các secondary index InnoDB tự mang primary key nếu khóa đó chưa có trong phần key đã khai báo, vì vậy index `(tenant_id)` có thể cung cấp cả `customer_id` cho bước join mà không cần khai báo lặp cột này.

Nạp dữ liệu đủ lớn và có phân phối khác nhau giữa tenant, trạng thái và ngày tạo đơn. Vài hàng mẫu không đủ để đánh giá optimizer vì table scan thường rẻ hơn khi bảng rất nhỏ.

## 3. Join order: bảng nào được đọc trước?

Join order là thứ tự optimizer đưa các bảng vào kế hoạch nối. Với inner join, optimizer thường có quyền hoán đổi thứ tự bảng vì phép nối có thể được biến đổi mà vẫn giữ kết quả logic. Thứ tự trong `FROM` là cách viết truy vấn, không phải chỉ thị bắt buộc.

### 3.1. Bắt đầu từ bảng lọc mạnh

Nếu điều kiện `tenant_id = 42` chỉ chọn một tỷ lệ nhỏ khách hàng, bắt đầu từ `customers` có thể hợp lý:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID'
  AND o.created_at >= '2026-01-01 00:00:00'
  AND o.created_at <  '2026-02-01 00:00:00';
```

Kế hoạch có thể đọc khách hàng của tenant 42 bằng `idx_customers_tenant`, rồi với từng khách hàng tìm các đơn phù hợp qua `idx_orders_customer_status_time`. Hướng này hiệu quả nếu tenant có ít khách hàng hoặc số đơn tương ứng nhỏ.

### 3.2. Bắt đầu từ bảng có điều kiện chọn lọc hơn

Nếu chỉ có rất ít đơn `PAID` trong khoảng thời gian, bắt đầu từ `orders` có thể rẻ hơn:

```sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= '2026-01-01 00:00:00'
  AND o.created_at <  '2026-02-01 00:00:00'
  AND c.tenant_id = 42;
```

Optimizer có thể đọc vùng index `idx_orders_status_time` trước, sau đó tra mỗi khách hàng bằng primary key. Điều kiện tenant được kiểm tra khi lấy khách hàng. Hướng này phù hợp khi bộ lọc trạng thái/thời gian thu hẹp mạnh số đơn trước khi join.

### 3.3. Join order phụ thuộc phân phối dữ liệu

Giả sử `tenant_id = 42` chọn 100 khách hàng nhưng trạng thái/ngày chọn 2 triệu đơn trên toàn hệ thống; hướng khách hàng trước có thể ít công việc hơn. Nếu tenant có 500.000 khách hàng nhưng trạng thái/ngày chỉ chọn 300 đơn, hướng đơn hàng trước có thể tốt hơn.

Đừng chỉ so sánh số hàng trong từng bảng. Hãy ước lượng số hàng sau từng điều kiện và số lần lookup ở các bước tiếp theo. Một bảng lớn vẫn có thể là bảng dẫn đầu tốt nếu index lọc nó xuống một tập rất nhỏ.

## 4. Access path: cách đọc hàng của từng bảng

Access path mô tả cách MySQL lấy hàng từ một bảng trong kế hoạch JOIN. Một số access type thường gặp trong `EXPLAIN` dạng tabular:

| `type` | Ý nghĩa khái quát | Tình huống thường gặp |
|---|---|---|
| `system` | Bảng có đúng một hàng | Bảng hệ thống/derived result chỉ có một hàng |
| `const` | Tối đa một hàng được xác định bằng unique/primary key và hằng số | Lookup bằng toàn bộ unique key với giá trị cố định |
| `eq_ref` | Với mỗi tổ hợp hàng trước đó, lookup tối đa một hàng bằng unique index/primary key đầy đủ | Join `orders.customer_id` sang `customers.customer_id` |
| `ref` | Lookup một hoặc nhiều hàng bằng index không unique hoặc tiền tố unique phù hợp | Tìm đơn theo `customer_id` |
| `range` | Đọc một vùng index | Lọc theo thời gian, ID hoặc khoảng giá trị |
| `index` | Quét toàn bộ index | Có thể hữu ích nếu index nhỏ/covering nhưng vẫn là full index scan |
| `ALL` | Quét toàn bộ bảng | Bảng nhỏ, thiếu index phù hợp hoặc điều kiện ít chọn lọc |

Các nhãn này là access type, không phải thuật toán JOIN. Ví dụ, một kế hoạch nested loop có thể dùng `range` cho bảng đầu và `ref` cho bảng bên trong. `type=index` cũng không đồng nghĩa với covering index; covering thường được phản ánh bằng `Extra: Using index`.

### 4.1. eq_ref và ref trong join

Với primary key `customers.customer_id`, mỗi `orders.customer_id` chỉ có thể khớp tối đa một hàng khách hàng:

```sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id;
```

Nếu optimizer dùng primary key của `customers`, bảng khách hàng có thể có access type `eq_ref`. Nếu lookup đơn theo index không unique `orders.customer_id`, access type thường là `ref` vì một khách hàng có thể có nhiều đơn.

### 4.2. Table scan không phải lúc nào cũng sai

Nếu bảng chỉ có vài chục hàng, hoặc điều kiện trả về phần lớn bảng, đọc tuần tự có thể rẻ hơn đi qua index rồi lookup nhiều hàng trong clustered index. `ALL` không tự động chứng minh truy vấn có vấn đề; cần xem số hàng thực tế, số hàng trả về, tần suất truy vấn và latency.

### 4.3. Điều kiện JOIN phải tương thích kiểu dữ liệu

Để index join được sử dụng hiệu quả, hai cột nối nên có kiểu dữ liệu tương thích, gồm kích thước và signed/unsigned của kiểu số, charset/collation của kiểu chuỗi. Ép kiểu hoặc áp hàm lên cột được index có thể làm điều kiện kém sargable:

```sql
-- Tốt: hai cột cùng kiểu BIGINT UNSIGNED
ON o.customer_id = c.customer_id

-- Cần xem xét: ép kiểu trên cột index
ON CAST(o.customer_id AS CHAR) = c.external_customer_code
```

Nếu cần nối khóa khác kiểu, ưu tiên chuẩn hóa schema hoặc chuyển đổi giá trị ở phía tham số/nguồn phù hợp để không làm mất khả năng dùng index trên cột quan trọng.

## 5. Nested-loop join

Nested-loop join (NLJ) xử lý một tập hàng outer; với mỗi hàng outer, nó tìm hàng phù hợp trong tập inner. Với hai bảng, mô hình khái niệm:

```text
for each row in outer input:
    find matching rows in inner input
    emit joined rows
```

Nếu outer có `M` hàng và mỗi lần tìm inner phải quét `N` hàng, chi phí có thể gần `M × N`. Nếu inner có index phù hợp và mỗi lần lookup chỉ đọc một số ít hàng, chi phí giảm đáng kể.

### 5.1. Index nested-loop join

Đây là dạng thường gặp và hiệu quả khi bảng outer đã được thu hẹp, còn bảng inner có index trên cột join:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42;
```

Với `idx_customers_tenant(tenant_id)` (secondary entry tự mang `customer_id`) và `idx_orders_customer_status_time(customer_id, status, created_at)` (entry tự mang `order_id`), MySQL có thể:

1. Range scan khách hàng theo `tenant_id = 42`.
2. Với mỗi `customer_id`, lookup vùng index tương ứng trong `orders`.
3. Đọc các hàng đơn khớp và trả kết quả.

Nếu outer có 200 khách hàng và mỗi khách hàng trung bình có 20 đơn phù hợp, số lookup inner khoảng 200 lần và số hàng kết quả khoảng 4.000. Nếu outer tăng lên hàng triệu hàng, cùng kiểu lookup lặp có thể trở nên đắt.

### 5.2. Khi nào nested loop phù hợp?

- Outer input nhỏ sau khi lọc.
- Inner có index phù hợp với điều kiện join.
- Lookup thường trả một hoặc vài hàng (`eq_ref`, `ref`).
- Kết quả cần dừng sớm với `LIMIT` và thứ tự truy cập hỗ trợ được yêu cầu.

Nested loop có thể kém hiệu quả khi outer rất lớn, inner phải quét nhiều lần hoặc index lookup gây nhiều random I/O.

## 6. Batched Key Access (BKA) và Multi-Range Read

Batched Key Access là biến thể nested-loop gom các giá trị khóa join từ nhiều hàng outer thành một batch rồi thực hiện lookup ở inner theo lô. Multi-Range Read (MRR) có thể sắp xếp/nhóm các lần đọc theo thứ tự phù hợp hơn với storage để giảm I/O ngẫu nhiên.

BKA vẫn dựa trên index của bảng inner; nó không thay thế index. Khác biệt chính là gom nhiều lookup thay vì thực hiện từng lookup rời rạc.

Trong MySQL, BKA được điều khiển qua optimizer switch và thường không bật mặc định. Có thể thử trong session lab:

```sql
SELECT @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'mrr=on,batched_key_access=on';

EXPLAIN FORMAT=TREE
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42;
```

Khả năng chọn BKA còn phụ thuộc cấu trúc truy vấn, index, optimizer và phiên bản. Nếu kế hoạch không đổi, không có nghĩa câu lệnh SET lỗi; điều kiện hiện tại có thể không phù hợp hoặc chi phí ước lượng không ủng hộ BKA. Hãy so sánh `EXPLAIN ANALYZE` trước/sau trên cùng dữ liệu và workload. Không bật BKA toàn hệ thống chỉ dựa trên một truy vấn lab.

## 7. Hash join

Hash join xây một hash table từ một input (build side), sau đó đọc input còn lại (probe side) và tìm các hàng có khóa khớp. Với equi-join, thuật toán có thể hiệu quả khi không có index join phù hợp hoặc khi lượng hàng cần kết hợp lớn khiến nested loop phải thực hiện quá nhiều lookup.

Mô hình khái niệm:

```text
build hash table from one input using join key
for each row in the other input:
    calculate hash(join key)
    find candidate matches in hash table
    verify join condition
    emit matching rows
```

Hash join không yêu cầu inner index lookup cho điều kiện equi-join, nhưng vẫn cần đọc các input và cấp bộ nhớ cho hash table. Nếu dữ liệu lớn, chi phí bộ nhớ và I/O tạm có thể đáng kể.

### 7.1. Hash join trong MySQL 8.0

MySQL 8.0.18 giới thiệu hash join. Từ MySQL 8.0.20, hash join thay thế thuật toán block nested-loop cũ trong các trường hợp liên quan; do đó, tài liệu hoặc plan từ phiên bản cũ có thể hiển thị `Using join buffer (Block Nested Loop)` trong khi bản mới hiển thị `Hash join`.

Trong `EXPLAIN FORMAT=TREE`, một kế hoạch đủ điều kiện có thể hiển thị nút `Inner hash join` hoặc dạng hash join tương ứng. Hình thức cụ thể phụ thuộc phiên bản và loại JOIN.

### 7.2. Build side và probe side

Về nguyên tắc, input nhỏ hơn thường là ứng viên tốt cho build side vì hash table cần ít bộ nhớ hơn. Optimizer lựa chọn dựa trên ước lượng cardinality và chi phí; đừng giả định bảng viết bên trái luôn là build side.

### 7.3. Khi nào hash join phù hợp?

- Hai input cần đọc một lượng hàng tương đối lớn.
- Điều kiện nối là phép so sánh bằng phù hợp với hash join.
- Không có index lookup hiệu quả cho inner side hoặc lookup lặp quá đắt.
- Bộ nhớ và I/O tạm đủ để xử lý hash table.

Nếu một input chỉ còn vài hàng và input kia có unique/index lookup rất tốt, nested loop thường có lợi thế. Hash join cũng không tự sửa được việc phải quét quá nhiều dữ liệu do thiếu bộ lọc hoặc thống kê sai.

## 8. So sánh các cách kết hợp

| Thuật toán | Cách hoạt động | Thường phù hợp khi | Điểm cần chú ý |
|---|---|---|---|
| Nested loop | Với mỗi hàng outer, tìm hàng inner | Outer nhỏ và inner có access path tốt | Outer lớn có thể tạo rất nhiều lookup |
| Index nested loop | Nested loop dùng index ở inner | Join key có index, lookup trả ít hàng | Phụ thuộc selectivity và locality của lookup |
| Batched Key Access | Gom khóa outer rồi lookup inner theo batch; có thể kết hợp MRR | Nhiều index lookup và batch giúp giảm I/O | Phụ thuộc optimizer switch, workload và phiên bản |
| Hash join | Build hash table, probe input còn lại | Equi-join lớn, index lookup không phù hợp | Tốn bộ nhớ; có thể phát sinh I/O tạm |
| Block Nested Loop (cũ) | Gom block hàng outer trong join buffer rồi so với inner | Plan ở các phiên bản cũ | Từ MySQL 8.0.20, hash join thay thế BNL trong các trường hợp liên quan |

Không có thuật toán tốt nhất cho mọi JOIN. Lựa chọn phụ thuộc kích thước input sau filter, index, phân phối dữ liệu, thứ tự join, giới hạn bộ nhớ và chi phí I/O.

## 9. Đọc join plan bằng EXPLAIN

### 9.1. EXPLAIN dạng tabular

```sql
EXPLAIN
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID';
```

Trong output truyền thống, mỗi hàng thường mô tả một bảng hoặc query block. Với JOIN đơn giản, thứ tự hàng trong output thường phản ánh thứ tự truy cập bảng trong kế hoạch. Các cột cần chú ý:

- `table`: bảng/alias được truy cập.
- `type`: access type như `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`.
- `possible_keys`: index optimizer cân nhắc.
- `key`: index được chọn.
- `key_len`: độ dài phần key dùng trong access path.
- `ref`: giá trị/cột được so sánh với key.
- `rows`: số hàng ước lượng phải đọc.
- `filtered`: tỷ lệ hàng ước lượng còn lại sau điều kiện lọc.
- `Extra`: thông tin bổ sung như `Using where`, `Using index`, `Using join buffer`.

Với JOIN phức tạp, derived table, subquery hoặc query block lồng nhau, đừng chỉ nhìn thứ tự dòng; dùng JSON hoặc TREE để hiểu cấu trúc đầy đủ.

### 9.2. EXPLAIN FORMAT=JSON

```sql
EXPLAIN FORMAT=JSON
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID';
```

JSON trình bày thông tin sâu hơn về `nested_loop`, `table`, `access_type`, `rows_examined_per_scan`, `rows_produced_per_join`, `attached_condition` và chi phí ước lượng. Đây là dạng hữu ích khi cần xác định điều kiện được áp ở đâu và số hàng tăng qua từng bước join.

### 9.3. EXPLAIN FORMAT=TREE

```sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID';
```

TREE cho thấy cấu trúc thực thi theo dạng cây, thường dễ nhận ra:

- `Nested loop inner join`: outer input và inner lookup.
- `Index lookup`: lookup qua index.
- `Index range scan`: đọc một vùng index.
- `Table scan`: quét bảng.
- `Hash join`: build/probe hash join.
- `Filter`: điều kiện lọc được áp tại một nút.

Hãy đọc từ các nút lá lên nút cha để biết dữ liệu đi từ đâu, được lọc ở bước nào và kết hợp ra sao.

## 10. EXPLAIN ANALYZE: kiểm tra ước lượng với thực tế

`EXPLAIN` thông thường chủ yếu cho biết ước lượng trước khi chạy. `EXPLAIN ANALYZE` thực thi truy vấn và bổ sung số hàng, số vòng lặp cùng thời gian thực tế của iterator. MySQL hỗ trợ lệnh này từ 8.0.18.

```sql
EXPLAIN ANALYZE
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID'
  AND o.created_at >= '2026-01-01 00:00:00'
  AND o.created_at <  '2026-02-01 00:00:00';
```

Đối chiếu:

- Số hàng ước lượng với số hàng thực tế ở từng iterator.
- Số vòng lặp của inner lookup.
- Thời gian mỗi iterator và thời gian tổng.
- Nút nào đọc nhiều hàng nhưng chỉ trả lại rất ít hàng.
- Nút nào có thời gian lớn nhất và có phải do sort/hash/temp I/O không.

`EXPLAIN ANALYZE` thực sự chạy SELECT. Không chạy tùy tiện trên truy vấn rất nặng hoặc production khi chưa đánh giá phạm vi và tác động.

## 11. Thống kê và cardinality ảnh hưởng join order

Optimizer không biết trước toàn bộ kết quả truy vấn; nó dựa vào thống kê để ước lượng số hàng và selectivity. Nếu thống kê sai hoặc dữ liệu lệch mạnh, optimizer có thể chọn sai bảng dẫn đầu hoặc đánh giá thấp số vòng lookup.

### 11.1. Cập nhật thống kê bảng

```sql
ANALYZE TABLE customers, orders, order_items, products;
```

Lệnh này yêu cầu MySQL cập nhật thống kê key distribution cho các bảng. Sau khi nạp dữ liệu lớn, xóa nhiều hàng hoặc thay đổi phân phối dữ liệu đáng kể, thống kê mới có thể giúp optimizer đưa ra kế hoạch phù hợp hơn.

`ANALYZE TABLE` không tạo index và không thay đổi dữ liệu nghiệp vụ. Nó có thể cần tài nguyên và có hành vi lock/đồng thời phụ thuộc engine/phiên bản; thực hiện theo quy trình vận hành phù hợp.

### 11.2. Histogram cho cột có phân phối lệch

Nếu một cột có phân phối lệch và không có index phù hợp, histogram có thể cải thiện ước lượng selectivity của điều kiện lọc:

```sql
ANALYZE TABLE customers
UPDATE HISTOGRAM ON customer_status WITH 32 BUCKETS;
```

Kiểm tra histogram:

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'customers'
  AND COLUMN_NAME = 'customer_status';
```

Xóa histogram khi cần:

```sql
ANALYZE TABLE customers
DROP HISTOGRAM ON customer_status;
```

Histogram không tạo access path và không thay thế index. Nó giúp ước lượng predicate tốt hơn; histogram đơn cột cũng không mô tả hoàn hảo tương quan giữa nhiều cột như `(tenant_id, customer_status)`.

Có thể xem truy vấn chịu ảnh hưởng của histogram:

```sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE customer_status = 'ACTIVE';
```

### 11.3. Skew và tương quan giữa cột

Giả sử 90% khách hàng có trạng thái `ACTIVE`, nhưng tỷ lệ này khác biệt lớn giữa các tenant. Nếu optimizer không nắm được phân phối hoặc tương quan giữa `tenant_id` và `customer_status`, số hàng sau filter có thể bị ước lượng sai.

Hãy xem phân phối thực tế trong lab:

```sql
SELECT customer_status, COUNT(*) AS customer_count
FROM customers
GROUP BY customer_status
ORDER BY customer_count DESC;

SELECT tenant_id, customer_status, COUNT(*) AS customer_count
FROM customers
GROUP BY tenant_id, customer_status
ORDER BY customer_count DESC;
```

Nếu estimate lệch, cân nhắc `ANALYZE TABLE`, histogram cho predicate phù hợp, index composite phản ánh truy vấn và cập nhật thống kê sau khi dữ liệu thay đổi. Đừng tạo histogram hoặc index chỉ để ép một plan cụ thể mà chưa đo.

## 12. Thiết kế index cho hai hướng join

Với truy vấn lọc tenant ở khách hàng rồi tìm đơn của họ:

```sql
WHERE c.tenant_id = 42
  AND o.status = 'PAID'
  AND o.created_at >= ...
```

Index `idx_customers_tenant(tenant_id)` phía khách hàng hỗ trợ lọc tenant; InnoDB tự mang primary key `customer_id` trong secondary entry để cung cấp khóa join. Index `idx_orders_customer_status_time(customer_id, status, created_at)` phía đơn hỗ trợ lookup các đơn theo từng khách hàng, trạng thái và khoảng thời gian; primary key `order_id` cũng được mang theo.

Nếu truy vấn thường bắt đầu từ đơn hàng có trạng thái/ngày rất chọn lọc, index `(status, created_at, order_id, customer_id)` có thể hỗ trợ range scan đơn trước và mang `customer_id` để lookup khách hàng. Hai index thể hiện hai access pattern khác nhau.

### 12.1. Index trên cột join không phải lúc nào cũng đủ

Index chỉ trên `orders.customer_id` hỗ trợ lookup theo khách hàng, nhưng nếu mỗi khách hàng có hàng chục nghìn đơn và truy vấn chỉ cần đơn `PAID` trong một tuần, index composite có thể giảm lượng hàng cần đọc:

```sql
KEY idx_orders_customer_status_time
    (customer_id, status, created_at)
```

Ngược lại, nếu bắt đầu từ trạng thái/ngày trên toàn hệ thống, thứ tự cột phù hợp có thể là:

```sql
KEY idx_orders_status_time
    (status, created_at, order_id, customer_id)
```

Không tạo cả hai chỉ vì chúng có thể hỗ trợ hai hướng. Đánh giá tần suất truy vấn, selectivity, dung lượng và chi phí ghi; index phụ làm tăng chi phí mọi INSERT/UPDATE/DELETE.

### 12.2. Join nhiều bảng

Với `customers -> orders -> order_items -> products`, optimizer có thể nối theo nhiều thứ tự hợp lệ. Một hướng có thể là lọc khách hàng, tìm đơn, lấy dòng đơn rồi tra sản phẩm. Hướng khác có thể lọc sản phẩm theo category, tìm dòng đơn liên quan rồi đi ngược lên đơn hàng/khách hàng.

Index ở từng cạnh join có thể cần khác nhau:

- `customers`: `idx_customers_tenant(tenant_id)`; secondary entry tự mang `customer_id`.
- `orders(customer_id, status, created_at)` cho đơn theo khách hàng.
- `order_items`: `idx_order_items_order(order_id)`; secondary entry tự mang `order_item_id`.
- `products`: `idx_products_category(category_id)`; secondary entry tự mang `product_id`.

Nếu query lọc category rất mạnh, bắt đầu từ `products` có thể hợp lý. Nếu lọc tenant và thời gian mạnh hơn, bắt đầu từ `customers` hoặc `orders` có thể tốt hơn. Hãy dựa trên số hàng sau filter, không dựa vào thứ tự bảng được viết.

## 13. INNER JOIN và OUTER JOIN ảnh hưởng khả năng đổi thứ tự

Với `INNER JOIN`, optimizer thường có nhiều tự do hoán đổi thứ tự bảng khi phép biến đổi vẫn giữ kết quả. `LEFT JOIN` có semantics bảo toàn hàng phía trái; việc đổi thứ tự có thể làm thay đổi kết quả nên bị giới hạn bởi quan hệ outer join.

Ví dụ:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
WHERE c.tenant_id = 42;
```

Điều kiện `o.status = 'PAID'` trong `ON` giữ lại khách hàng không có đơn PAID; các cột `o` của họ sẽ là `NULL`.

Nếu chuyển điều kiện sang `WHERE`:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID';
```

Các hàng không có đơn có `o.status IS NULL` và bị `WHERE` loại bỏ. Truy vấn khi đó có semantics gần với inner join đối với điều kiện này. Không di chuyển điều kiện giữa `ON` và `WHERE` chỉ để mong đổi plan; trước hết phải giữ đúng ý nghĩa kết quả.

## 14. Ép join order và optimizer hint

MySQL thường tự chọn join order dựa trên chi phí. Trong trường hợp đã đo và xác định optimizer liên tục chọn sai thứ tự, có thể thử `STRAIGHT_JOIN` trong lab:

```sql
SELECT STRAIGHT_JOIN
    c.customer_id,
    o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID';
```

`STRAIGHT_JOIN` yêu cầu MySQL đọc các bảng theo thứ tự xuất hiện ở phần `FROM`. Nó có thể giúp kiểm chứng giả thuyết về join order nhưng cũng có thể khóa optimizer vào kế hoạch kém khi phân phối dữ liệu thay đổi.

MySQL 8.0 còn có optimizer hints cho join order như `JOIN_ORDER`, `JOIN_PREFIX`, `JOIN_SUFFIX` và `JOIN_FIXED_ORDER` ở các phiên bản hỗ trợ. Cú pháp hint phải đúng query block và phiên bản; hãy xác minh trong tài liệu đúng bản MySQL trước khi dùng.

Ưu tiên sửa nguyên nhân gốc:

- Cập nhật thống kê.
- Bổ sung hoặc điều chỉnh index phù hợp workload.
- Làm điều kiện join sargable và kiểu dữ liệu tương thích.
- Giảm số hàng sớm bằng predicate đúng ngữ nghĩa.
- Tránh ép join order cố định nếu dữ liệu thay đổi thường xuyên.

## 15. Những dấu hiệu join plan có vấn đề

| Dấu hiệu | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Bảng lớn được đọc trước dù filter rất rộng | Estimate sai hoặc thiếu index phù hợp | So sánh rows estimate/actual, kiểm tra stats và histogram |
| Inner table có `ALL` và loops rất lớn | Thiếu index trên join/filter hoặc optimizer chọn access path kém | Kiểm tra index inner, số vòng lặp và điều kiện join |
| `rows` estimate khác xa actual | Thống kê cũ, skew hoặc tương quan cột | `ANALYZE TABLE`, histogram và xem phân phối thật |
| Hash join tốn nhiều thời gian/bộ nhớ | Hai input lớn hoặc build side quá lớn | Giảm input hợp lệ, cải thiện filter/index và đo lại |
| Nested loop có hàng triệu lần lookup | Outer input quá lớn hoặc join order không phù hợp | Kiểm tra outer cardinality, index inner và hướng join thay thế |
| `Using temporary` hoặc sort lớn | GROUP BY/ORDER BY không được hỗ trợ bởi access path | Kiểm tra index, thứ tự join và lượng dữ liệu trung gian |
| Query chậm sau khi dữ liệu tăng | Plan từng phù hợp với dữ liệu nhỏ, nay selectivity khác | Chạy `EXPLAIN ANALYZE` với dữ liệu gần production |
| LEFT JOIN mất hàng không khớp | Predicate phía phải đặt trong WHERE | Xem lại semantics và vị trí điều kiện ON/WHERE |

## 16. Quy trình tối ưu một truy vấn JOIN

1. Ghi rõ kết quả nghiệp vụ cần trả về; xác định inner/outer join có bảo toàn hàng hay không.
2. Xác định điều kiện lọc mạnh nhất và ước lượng số hàng còn lại sau mỗi điều kiện.
3. Kiểm tra kiểu dữ liệu và collation của các cột join; loại bỏ cast/hàm không cần thiết trên cột index.
4. Liệt kê index hiện có ở từng bảng và xác định access path khả thi.
5. Chạy `EXPLAIN FORMAT=TREE` và `EXPLAIN FORMAT=JSON` để đọc join order, access path và thuật toán.
6. Chạy `EXPLAIN ANALYZE` trong lab/staging để so sánh estimate với actual.
7. Nếu estimate sai, cập nhật thống kê và xem histogram cho predicate lệch phân phối.
8. Thiết kế index composite theo hướng join thực tế; không thêm index chỉ dựa vào một cột riêng lẻ.
9. So sánh nested loop/index lookup, BKA hoặc hash join nếu optimizer có thể chọn và workload phù hợp.
10. Đo latency, số hàng đọc, loops, I/O và chi phí ghi sau khi thêm index.
11. Chỉ dùng `STRAIGHT_JOIN`/optimizer hint khi có bằng chứng rõ và kế hoạch theo dõi sau triển khai.
12. Kiểm tra lại khi dữ liệu và phân phối thay đổi; plan tốt hôm nay không đảm bảo tốt mãi mãi.

## 17. Bài thực hành

Thực hiện trong database lab riêng với bốn bảng ở phần 2 và lượng dữ liệu đủ lớn:

1. Viết JOIN `customers` với `orders` theo `customer_id`, lọc một tenant; đọc thứ tự bảng trong `EXPLAIN`.
2. Thêm điều kiện `status` và khoảng `created_at`; so sánh index `(customer_id, status, created_at)` với index `(status, created_at, customer_id)`.
3. Tạo phân phối trong đó một tenant có ít khách hàng; đo kế hoạch bắt đầu từ `customers`.
4. Tạo phân phối trong đó một trạng thái/ngày chỉ chọn rất ít đơn; đo kế hoạch bắt đầu từ `orders`.
5. Dùng `EXPLAIN FORMAT=TREE` để nhận diện nested loop và index lookup.
6. Kiểm tra access type `eq_ref` khi tra khách hàng qua primary key và `ref` khi tìm nhiều đơn theo customer.
7. Thử truy vấn thiếu index inner trong schema lab riêng; quan sát số vòng quét và thời gian.
8. Thử BKA với `optimizer_switch` ở session; so sánh actual time, không chỉ nhìn tên thuật toán.
9. Tạo một equi-join lớn không có index join phù hợp để quan sát hash join trên MySQL 8.0.18 trở lên.
10. Thay đổi số hàng và phân phối dữ liệu; so sánh build/probe input và actual rows của hash join.
11. Chạy `ANALYZE TABLE`, tạo histogram cho `customers.customer_status`, rồi so sánh estimate trước/sau.
12. Viết `LEFT JOIN` với predicate phía bảng phải trong `ON`, sau đó chuyển sang `WHERE`; giải thích hàng nào biến mất.
13. Dùng `STRAIGHT_JOIN` để ép thứ tự trong lab, so sánh với kế hoạch optimizer tự chọn và bỏ hint sau khi đo.
14. Tối ưu một JOIN ba hoặc bốn bảng; nộp lại query, index đề xuất, `EXPLAIN TREE`, `EXPLAIN ANALYZE` và giải thích trade-off.

Bạn hoàn thành bài khi có thể giải thích tại sao optimizer chọn một bảng làm đầu vào, phân biệt được access type với join algorithm và dùng số liệu thực tế để quyết định thay đổi index hoặc join order.

## 18. Nguyên tắc cần ghi nhớ

- Join order, access path và join algorithm là ba quyết định khác nhau.
- Thứ tự bảng viết trong `FROM` không mặc định là thứ tự MySQL thực thi inner join.
- Optimizer chọn join order dựa trên ước lượng cardinality, selectivity và chi phí.
- `eq_ref`, `ref`, `range`, `index`, `ALL` là access type, không phải thuật toán JOIN.
- Nested loop hiệu quả khi outer nhỏ và inner có index lookup tốt.
- Index nested loop dùng index phía inner cho mỗi hàng outer; outer quá lớn có thể tạo nhiều lookup.
- BKA gom lookup theo batch và có thể dùng MRR; cần đo trước khi bật.
- Hash join build hash table rồi probe input còn lại; phù hợp với equi-join lớn khi index lookup không thuận lợi.
- MySQL 8.0.18 giới thiệu hash join; từ 8.0.20 hash join thay thế BNL cũ trong các trường hợp liên quan.
- Index nên hỗ trợ cả filter lẫn cột join theo access pattern thực tế.
- Thống kê sai hoặc dữ liệu skew có thể khiến optimizer chọn sai join order.
- `ANALYZE TABLE` cập nhật thống kê; histogram hỗ trợ ước lượng predicate nhưng không tạo index.
- `EXPLAIN FORMAT=TREE` giúp nhìn cấu trúc thực thi; `EXPLAIN ANALYZE` cung cấp số hàng và thời gian thực tế.
- LEFT JOIN bảo toàn hàng phía trái; đặt predicate ở ON hay WHERE có thể thay đổi kết quả.
- Chỉ ép join order sau khi có bằng chứng; ưu tiên sửa thống kê, index và predicate trước.
