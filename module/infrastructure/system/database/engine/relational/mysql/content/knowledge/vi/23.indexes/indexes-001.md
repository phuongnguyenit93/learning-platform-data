# Cấu trúc B+tree và cơ chế tra cứu theo khóa

Trong InnoDB, các index thông thường được tổ chức bằng cấu trúc **B+tree**. Cây giữ các khóa theo thứ tự, chia dữ liệu thành nhiều page và cho phép MySQL đi từ root page qua các intermediate page tới leaf page cần thiết. Thay vì đọc tuần tự toàn bộ bảng, engine có thể định vị vùng chứa khóa cần tìm rồi chỉ đọc một số page liên quan.

Muốn hiểu vì sao một index giúp truy vấn nhanh, cần nắm ba điều: nội dung của từng tầng B+tree, khác biệt giữa clustered index và secondary index, và cách điều kiện truy vấn khớp với thứ tự khóa. Một index không tự động làm mọi truy vấn nhanh hơn; hiệu quả phụ thuộc vào khóa được tìm, phạm vi cần đọc, số hàng phù hợp và việc các page có sẵn trong buffer pool hay không.

Trong module `DATABASE_MYSQL`, kiến thức này là nền tảng để thiết kế index, đọc `EXPLAIN`, hiểu lookup theo primary/secondary key, chọn thứ tự cột của composite index và đánh giá chi phí đọc/ghi. Các ví dụ sử dụng InnoDB và cú pháp MySQL.

## 1. B+tree giải quyết vấn đề tra cứu như thế nào?

Nếu bảng có hàng triệu bản ghi mà không có index phù hợp, MySQL có thể phải quét nhiều hoặc toàn bộ dữ liệu để tìm hàng thỏa điều kiện. Đây là table scan. Với B+tree, các khóa được sắp xếp và phân cấp thành nhiều page; mỗi bước đi xuống cây thu hẹp vùng khóa cần tìm.

Hãy hình dung một index có các khóa số:

```text
                         [ 40 | 80 ]              root
                        /    |     \
                       /     |      \
             [10 | 20 | 30] [50 | 60 | 70] [90 | 100 | 110]
                  leaf          leaf          leaf
```

Root giữ các separator key để chỉ đường tới page con. Nếu tìm khóa 60, engine so sánh với 40 và 80, chọn nhánh giữa, rồi tìm trong leaf page chứa vùng khóa tương ứng.

Đây chỉ là sơ đồ logic. Trong InnoDB, mỗi node là một index page; một page có thể chứa nhiều khóa và nhiều con trỏ, không phải mỗi khóa là một node riêng. Cây có thể có nhiều tầng intermediate khi dữ liệu tăng.

### Vì sao gọi là B+tree?

Ở cấu trúc B+tree, các khóa dùng để điều hướng nằm ở các node trong và dữ liệu index ở tầng leaf. Tất cả leaf page nằm cùng độ sâu, giúp đường đi từ root tới leaf có số tầng ổn định. Các leaf page được liên kết theo thứ tự khóa để hỗ trợ duyệt range và index scan.

Với InnoDB:

- Root page và intermediate page chứa separator key cùng thông tin dẫn tới page con.
- Leaf page của clustered index chứa bản ghi đầy đủ của bảng.
- Leaf page của secondary index chứa secondary key cùng clustered key cần thiết để định vị hàng.
- Các leaf page được nối theo thứ tự khóa, giúp đọc các giá trị liên tiếp hiệu quả.

## 2. Page là đơn vị lưu trữ và I/O quan trọng

InnoDB không đọc từng giá trị index từ đĩa một cách độc lập. Dữ liệu index được lưu trong page. Page size mặc định thường là 16 KiB, nhưng có thể được cấu hình khi khởi tạo instance; kích thước được hỗ trợ phụ thuộc cấu hình và phiên bản.

Một page có thể chứa nhiều index record. Số record phụ thuộc vào độ rộng của khóa, dữ liệu lưu trong leaf, overhead quản lý page và mức độ lấp đầy. Vì vậy:

- Khóa càng rộng thì mỗi page thường chứa được càng ít entry.
- Entry càng nhỏ thì một page có thể phục vụ nhiều khóa hơn.
- Page chứa nhiều entry hơn thường giúp tăng fan-out của node trong.
- Fan-out cao giúp cây cần ít tầng hơn để quản lý cùng số lượng khóa.

Minh họa ý tưởng:

```text
Khóa hẹp:    [k1 k2 k3 k4 k5 k6 k7 k8 ...]
Khóa rộng:   [long-key-1] [long-key-2] [long-key-3] ...
             ít entry hơn trên cùng một page
```

Đây là mô hình khái niệm; không thể suy ra chính xác số entry/page chỉ từ kiểu dữ liệu. Cần tính cả độ dài thực tế, nullable flags, record header, page directory và các thành phần nội bộ khác.

### Buffer pool giữ page thường dùng trong bộ nhớ

InnoDB dùng buffer pool để cache data page và index page. Khi một page cần đọc đã nằm trong buffer pool, engine có thể truy cập trong bộ nhớ mà không cần đọc lại từ storage. Nếu page chưa có, InnoDB phải đọc page từ tablespace vào buffer pool.

Vì vậy, hiệu năng index không chỉ phụ thuộc số phép so sánh trong cây mà còn phụ thuộc:

- Root/intermediate/leaf page có nằm trong buffer pool không.
- Truy vấn phải đọc bao nhiêu leaf page.
- Secondary lookup có cần thêm clustered page không.
- Các page được truy cập có tính locality hay phân tán ngẫu nhiên.
- Buffer pool có đủ chỗ cho working set hay liên tục phải thay thế page.

## 3. Đường đi từ root tới leaf

Một lần tra cứu B+tree thường gồm các bước:

1. Bắt đầu tại root page của index.
2. So sánh khóa tìm kiếm với separator key trong page.
3. Chọn child pointer tương ứng với khoảng khóa.
4. Đọc intermediate page tiếp theo nếu cây có nhiều tầng.
5. Lặp lại đến leaf page chứa khóa hoặc vị trí khóa có thể nằm.
6. Tìm entry trong leaf page; nếu là range scan thì tiếp tục sang leaf page kế tiếp theo thứ tự khóa.

Sơ đồ:

```text
       Root page
           |
           v
   Intermediate page
           |
           v
       Leaf page  <---->  Leaf page  <---->  Leaf page
        keys 10-19          20-29              30-39
```

Trong mỗi page, InnoDB dùng cấu trúc nội bộ để tìm record theo thứ tự khóa. Khi một page chứa nhiều record, engine không cần đi qua từng hàng từ đầu như table scan; page directory và tổ chức record giúp định vị vùng phù hợp.

### Cây cân bằng và số lần truy cập page

B+tree giữ các leaf ở cùng độ sâu. Khi số khóa tăng, cây mở rộng bằng cách phân chia page và có thể tăng thêm tầng. Chiều cao cây thường tăng chậm so với số lượng khóa vì một page trong có thể trỏ tới nhiều page con.

Không nên diễn giải rằng mọi lookup luôn chỉ đọc đúng ba page. Số page thực tế phụ thuộc chiều cao cây, page có sẵn trong buffer pool hay không, loại index và việc truy vấn cần một hay nhiều leaf page.

## 4. Clustered index: leaf page chứa toàn bộ hàng

Trong InnoDB, clustered index xác định cách dữ liệu hàng được tổ chức. Nếu bảng có primary key, primary key là clustered index. Leaf page của clustered index chứa các cột của hàng.

Ví dụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    city VARCHAR(80) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

INSERT INTO customers (customer_id, email, full_name, city, created_at)
VALUES
    (105, 'linh@example.test', 'Linh Nguyen', 'Da Nang', '2026-01-10 09:00:00'),
    (106, 'minh@example.test', 'Minh Tran', 'Ho Chi Minh City', '2026-01-12 10:30:00'),
    (107, 'an@example.test', 'An Pham', 'Da Nang', '2026-01-15 14:15:00');
```

Với truy vấn:

```sql
SELECT customer_id, email, full_name, city, created_at
FROM customers
WHERE customer_id = 105;
```

MySQL có thể đi trực tiếp theo clustered B+tree của primary key tới leaf page chứa hàng `customer_id = 105`. Vì leaf page đã chứa toàn bộ hàng, không cần bước tra cứu thêm một index khác để lấy các cột còn lại.

### Clustered key được chọn thế nào?

Quy tắc InnoDB:

1. Dùng primary key nếu bảng có khai báo primary key.
2. Nếu không có primary key, chọn unique index đầu tiên có tất cả cột khóa `NOT NULL`.
3. Nếu không có khóa phù hợp, tạo hidden row ID 6 byte và clustered index ẩn.

Do đó, clustered index không phải lúc nào cũng là một cột tên `id`; nó có thể là primary key ghép hoặc unique key phù hợp. Khi thiết kế bảng mới, nên khai báo primary key rõ ràng để định danh hàng và kiểm soát clustered key.

## 5. Secondary index: tra cứu hai bước

Secondary index là B+tree độc lập với clustered index. Leaf page của secondary index lưu giá trị cột được index và clustered key dùng để định vị hàng trong clustered index.

Ví dụ tạo index trên email:

```sql
CREATE UNIQUE INDEX uq_customers_email
ON customers (email);
```

Truy vấn:

```sql
SELECT customer_id, full_name, city
FROM customers
WHERE email = 'linh@example.test';
```

Đường đi điển hình:

```text
1. Tìm email trong secondary B+tree
              |
              v
2. Lấy customer_id từ secondary leaf entry
              |
              v
3. Tìm customer_id trong clustered B+tree
              |
              v
4. Đọc hàng đầy đủ từ clustered leaf page
```

Đây thường được gọi là secondary-to-clustered lookup hoặc double lookup. Bước thứ hai có thể phát sinh thêm truy cập page nếu clustered page chưa nằm trong buffer pool.

Nếu primary key gồm nhiều cột, secondary index cần mang các thành phần clustered key cần thiết để định vị hàng. Nếu một thành phần khóa chính đã nằm trong secondary key, InnoDB không cần lưu lặp lại thành phần đó trong entry.

### Secondary index không phải con trỏ vật lý cố định

Secondary index lưu clustered key, không lưu địa chỉ vật lý cố định của hàng. Khi clustered record di chuyển do tổ chức page thay đổi, engine vẫn có thể định vị hàng thông qua clustered key. Điều này giúp index duy trì tính đúng đắn khi B+tree được cân bằng và page được tổ chức lại.

## 6. Covering index: khi không cần tra cứu clustered index

Một truy vấn có thể được phục vụ hoàn toàn từ secondary index nếu mọi cột cần lọc, sắp xếp và trả về đều có sẵn trong index entry. Trường hợp đó được gọi là covering index.

Ví dụ tạo index:

```sql
CREATE INDEX idx_customers_city_created
ON customers (city, created_at);
```

Truy vấn:

```sql
SELECT city, created_at, customer_id
FROM customers
WHERE city = 'Da Nang'
ORDER BY created_at, customer_id;
```

Các cột `city` và `created_at` được khai báo trực tiếp trong index; `customer_id` là primary key nên InnoDB tự mang nó vào secondary index entry để định vị hàng. Vì vậy truy vấn vẫn có thể được phục vụ hoàn toàn từ index mà không cần khai báo lặp `customer_id` trong danh sách cột index. Trong `EXPLAIN`, dấu hiệu thường gặp là `Using index` trong cột `Extra`.

So sánh với truy vấn:

```sql
SELECT city, created_at, customer_id, full_name
FROM customers
WHERE city = 'Da Nang'
ORDER BY created_at, customer_id;
```

`full_name` không nằm trong index. Nếu dùng secondary index, InnoDB cần tra cứu clustered record để lấy cột này. Optimizer vẫn có thể chọn table scan nếu cho rằng chi phí thấp hơn.

Không nên đưa mọi cột vào index chỉ để tạo covering index. Index quá rộng làm tăng dung lượng, giảm fan-out và tăng chi phí INSERT/UPDATE/DELETE. Hãy cân bằng số lần truy vấn tiết kiệm được với chi phí duy trì index.

## 7. Tra cứu equality và range scan

### Equality lookup

Điều kiện equality tìm một giá trị hoặc một nhóm hàng có cùng giá trị khóa:

```sql
SELECT customer_id, email
FROM customers
WHERE email = 'linh@example.test';
```

Với unique index trên `email`, optimizer có thể dùng unique lookup để tìm tối đa một hàng. Với nonunique index, cùng một giá trị có thể dẫn tới nhiều entry trong leaf page.

### Range scan

Điều kiện range xác định một khoảng khóa:

```sql
SELECT customer_id, email, created_at
FROM customers
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at;
```

Nếu có index phù hợp trên `created_at`, MySQL có thể định vị leaf page đầu tiên trong range rồi duyệt các entry liên tiếp cho tới khi vượt biên. Leaf page được liên kết theo thứ tự khóa nên range scan tránh phải tìm lại từ root cho từng entry.

Range scan vẫn có thể tốn kém nếu khoảng bao phủ phần lớn bảng hoặc cần đọc nhiều cột không có trong index. Có index không đồng nghĩa truy vấn luôn nhanh hơn table scan.

### Prefix search và điều kiện không sargable

Với index trên chuỗi, điều kiện prefix như:

```sql
SELECT customer_id, email
FROM customers
WHERE email LIKE 'linh%';
```

có thể được chuyển thành range trên các giá trị bắt đầu bằng `linh`, tùy collation và dạng pattern. Ngược lại, pattern có wildcard đầu chuỗi:

```sql
WHERE email LIKE '%@example.test'
```

không cung cấp điểm bắt đầu rõ ràng trên B+tree thông thường.

Điều kiện bọc hàm trên cột cũng thường làm giảm khả năng dùng range lookup thông thường:

```sql
-- Thường thân thiện với index hơn
WHERE created_at >= '2026-01-01'

-- Có thể không dùng range access trên index created_at
WHERE DATE(created_at) = '2026-01-01'
```

Nếu cần tìm theo biểu thức, cân nhắc generated column được index hoặc functional index phù hợp với phiên bản MySQL.

## 8. Composite index được sắp xếp theo thứ tự từ trái sang phải

Composite index là index gồm nhiều cột. Ví dụ:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);

INSERT INTO orders (order_id, tenant_id, status, created_at, total_amount)
VALUES
    (1001, 10, 'PAID', '2026-01-03 09:00:00', 250.00),
    (1002, 10, 'NEW',  '2026-01-05 10:00:00', 120.00),
    (1003, 10, 'PAID', '2026-01-08 11:00:00', 450.00),
    (1004, 20, 'PAID', '2026-01-09 12:00:00',  90.00);
```

Các entry được sắp xếp theo thứ tự từ điển:

1. So sánh `tenant_id` trước.
2. Nếu `tenant_id` bằng nhau, so sánh `status`.
3. Nếu hai cột đầu bằng nhau, so sánh `created_at`.

Minh họa:

```text
(tenant=1, status='NEW',     time=t1)
(tenant=1, status='NEW',     time=t2)
(tenant=1, status='PAID',    time=t1)
(tenant=2, status='NEW',     time=t1)
(tenant=2, status='SHIPPED', time=t3)
```

Vì cột đầu tiên là `tenant_id`, index này hỗ trợ tốt các truy vấn bắt đầu từ tenant, chẳng hạn:

```sql
WHERE tenant_id = 10
```

hoặc:

```sql
WHERE tenant_id = 10
  AND status = 'PAID'
```

và:

```sql
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
```

Theo quy tắc leftmost prefix, truy vấn chỉ lọc `status = 'PAID'` thường không thể dùng index này như một range lookup liên tục hiệu quả vì không chỉ rõ cột đầu `tenant_id`. MySQL có thể cân nhắc các chiến lược khác như index skip scan trong một số điều kiện và phiên bản, nhưng không nên thiết kế workload chính dựa vào ngoại lệ đó.

## 9. Equality prefix trước range key

Với composite index `(tenant_id, status, created_at)`, một mẫu truy vấn hiệu quả thường là equality trên các cột đầu, rồi range trên cột tiếp theo:

```sql
SELECT order_id, tenant_id, status, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
```

Engine có thể định vị vùng bắt đầu theo `(10, 'PAID', '2026-01-01')` rồi quét đến biên kết thúc. Các cột sau cột range có thể vẫn được kiểm tra bằng index condition hoặc filter, nhưng thường không tiếp tục thu hẹp cùng một khoảng liên tục theo cách equality prefix đã làm.

Ví dụ index:

```sql
-- Index idx_orders_tenant_status_created đã được tạo ở phần trước.
-- Dùng lại index đó để thử equality prefix và range scan.
SHOW INDEX FROM orders;
```

Khi chọn thứ tự cột, hãy xem:

- Cột nào thường được lọc bằng equality?
- Cột nào thường dùng range?
- Truy vấn có cần `ORDER BY` theo các cột kế tiếp không?
- Các cột có được lọc cùng nhau thường xuyên không?
- Số giá trị khác nhau và độ chọn lọc của từng cột ra sao?

Không áp dụng máy móc quy tắc “cột có cardinality cao luôn đứng trước”. Với composite index, leftmost prefix và mẫu truy vấn thực tế thường quan trọng hơn một quy tắc chọn cột đơn lẻ.

## 10. Index hỗ trợ ORDER BY và GROUP BY

Index có thứ tự phù hợp có thể giúp MySQL đọc dữ liệu theo thứ tự cần thiết mà không phải thực hiện một bước filesort riêng.

Ví dụ:

```sql
CREATE INDEX idx_orders_tenant_created
ON orders (tenant_id, created_at);

SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
ORDER BY created_at, order_id;
```

Sau khi cố định `tenant_id`, các entry còn lại được sắp theo `created_at`; `order_id` là primary key và được InnoDB tự bổ sung vào secondary index entry. Optimizer có thể tận dụng thứ tự đó để trả kết quả theo `created_at, order_id`.

Nếu yêu cầu thứ tự đảo chiều, MySQL có thể dùng backward index scan khi thứ tự cột và hướng sắp xếp phù hợp; index descending cũng được hỗ trợ trong MySQL 8.0. Tuy nhiên, thứ tự ASC/DESC trộn lẫn giữa nhiều cột có thể cần index được định nghĩa đúng chiều để tránh sort.

Với `GROUP BY`, index phù hợp có thể hỗ trợ đọc các giá trị cùng nhóm liền nhau. Nhưng việc có index không bảo đảm luôn loại bỏ temporary table hoặc sort; hãy kiểm tra kế hoạch và `Extra` trong EXPLAIN.

## 11. Unique index và nonunique index trong leaf page

Unique index bảo đảm không có hai entry có cùng giá trị khóa theo quy tắc so sánh của index, có xét NULL theo semantics MySQL. Nonunique index cho phép nhiều hàng có cùng giá trị khóa.

Ví dụ:

```sql
CREATE INDEX idx_customers_city
ON customers (city);
```

`uq_customers_email` đã được tạo ở phần secondary index và có thể hỗ trợ unique lookup. `idx_customers_city` có thể trả về nhiều khách hàng trong cùng thành phố; engine duyệt toàn bộ các entry tương ứng trong leaf page range.

Khi giá trị trùng nhiều, secondary index cần clustered key để phân biệt từng hàng. Vì vậy, hai hàng có cùng `city` vẫn có entry riêng nhờ clustered key đi kèm.

## 12. B+tree thay đổi khi INSERT, UPDATE và DELETE

Index không phải cấu trúc chỉ đọc. Mọi INSERT, DELETE và UPDATE làm thay đổi cột index đều cần bảo trì B+tree.

### INSERT

Khi chèn khóa mới, InnoDB tìm leaf page đúng vị trí rồi thêm index record. Nếu page còn chỗ, record được chèn vào page đó. Nếu page đầy, engine có thể phải chia page (page split), phân phối record sang page mới và cập nhật các tầng cha nếu cần.

Chèn khóa tăng dần thường có xu hướng tập trung ở vùng cuối index; chèn khóa phân tán ngẫu nhiên có thể chạm nhiều leaf page khác nhau và làm tăng page split hoặc page utilization không đồng đều.

### UPDATE

Nếu UPDATE thay đổi cột không được index hóa, InnoDB chủ yếu cập nhật clustered record. Nếu thay đổi cột index, entry liên quan trong index phải được cập nhật; về mặt cấu trúc có thể tương đương xóa entry cũ và thêm entry mới.

### DELETE

DELETE đánh dấu/xóa hàng theo cơ chế InnoDB và cập nhật các index liên quan. Việc thu hồi và tái sử dụng không gian có thể diễn ra theo cơ chế purge và quản lý page; không phải mọi byte được trả ngay cho hệ điều hành sau một câu DELETE.

Vì vậy, thêm index có lợi cho SELECT nhưng tăng chi phí ghi, dung lượng và công việc bảo trì. Chỉ tạo index khi workload có truy vấn cần nó.

## 13. Đọc EXPLAIN để biết B+tree có được dùng không

`EXPLAIN` cho biết optimizer dự kiến truy cập bảng như thế nào. Ví dụ:

```sql
EXPLAIN
SELECT customer_id, full_name, city
FROM customers
WHERE email = 'linh@example.test';
```

Với fixture chỉ có vài hàng, optimizer có thể chọn table scan vì chi phí quét bảng nhỏ thấp hơn việc đi qua index. Khi đánh giá index, hãy dùng dữ liệu có quy mô và phân bố gần workload thật; không ép kết luận rằng index phải được chọn chỉ vì truy vấn có điều kiện equality.

Các cột thường cần xem:

| Cột | Ý nghĩa |
|---|---|
| `type` | Kiểu access, ví dụ `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`. |
| `possible_keys` | Các index optimizer xem là ứng viên. |
| `key` | Index thực tế được chọn; NULL nghĩa là không chọn index. |
| `key_len` | Độ dài phần key được dùng trong access path. |
| `rows` | Số hàng ước lượng cần đọc. |
| `filtered` | Tỷ lệ hàng ước tính còn lại sau điều kiện lọc. |
| `Extra` | Thông tin bổ sung như `Using index`, `Using where`, `Using filesort`. |

Một số kiểu access phổ biến:

- `const`: lookup unique/primary key với hằng số, tối đa một hàng.
- `eq_ref`: unique lookup cho mỗi tổ hợp hàng từ bảng trước trong JOIN.
- `ref`: lookup theo giá trị index không nhất thiết unique.
- `range`: đọc một hoặc nhiều khoảng khóa.
- `index`: quét toàn bộ index tree.
- `ALL`: table scan.

Đừng chỉ nhìn `type` rồi kết luận. `range` trên vài trăm entry có thể rất tốt; `index` scan toàn bộ index vẫn có thể tốn kém; `ALL` trên bảng nhỏ đôi khi rẻ hơn nhiều random lookups.

### EXPLAIN ANALYZE

Trên MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` thực thi truy vấn và cung cấp số liệu thực tế của iterator:

```sql
EXPLAIN ANALYZE
SELECT customer_id, full_name, city
FROM customers
WHERE email = 'linh@example.test';
```

Lệnh này có thể tiêu tốn tài nguyên như truy vấn thật. Hãy chạy trên dữ liệu phù hợp và môi trường an toàn khi truy vấn có thể quét nhiều hàng.

## 14. Khi nào optimizer không chọn index?

Optimizer chọn access path dựa trên ước lượng chi phí. Nó có thể không dùng index khi:

- Bảng nhỏ và table scan rẻ hơn.
- Điều kiện trả về phần lớn hàng, khiến lookup từng hàng qua index tốn kém.
- Cột có độ chọn lọc thấp và index không giảm được nhiều dữ liệu cần đọc.
- Điều kiện không phù hợp với leftmost prefix hoặc không tạo được range hữu ích.
- Kiểu dữ liệu, collation hoặc phép chuyển đổi làm index khó sử dụng.
- Thống kê index không phản ánh tốt phân bố dữ liệu hiện tại.

Ví dụ cột `status` chỉ có hai giá trị `ACTIVE` và `INACTIVE`. Nếu 95% hàng là `ACTIVE`, index đơn trên `status` có thể không giúp nhiều cho truy vấn lấy tất cả hàng ACTIVE. Một composite index theo tenant hoặc thời gian có thể hữu ích hơn nếu phù hợp workload.

Không nên ép optimizer dùng index chỉ vì index tồn tại. Trước tiên kiểm tra cardinality, thống kê, số hàng thực tế và chi phí đọc dữ liệu.

## 15. Thống kê index và cardinality

Optimizer cần ước lượng số hàng có thể khớp với một giá trị hoặc range. Thống kê index giúp ước lượng cardinality (số giá trị phân biệt) và phân bố dữ liệu.

Kiểm tra:

```sql
SHOW INDEX FROM customers;
```

Cột `Cardinality` là ước lượng số giá trị phân biệt trong index prefix, không nhất thiết là con số chính xác tuyệt đối. Với composite index, cardinality được thể hiện theo từng key part/prefix.

Có thể yêu cầu cập nhật thống kê:

```sql
ANALYZE TABLE customers;
```

Sau khi dữ liệu thay đổi lớn hoặc phân bố lệch đáng kể, thống kê cũ có thể khiến optimizer chọn kế hoạch không tốt. `ANALYZE TABLE` cập nhật thống kê; hãy xem tác động trên hệ thống đang tải và theo chính sách vận hành.

## 16. Thiết kế index từ mẫu truy vấn

Một quy trình thiết kế index thực tế:

1. Thu thập truy vấn thường chạy và truy vấn có thời gian/đọc hàng cao.
2. Xác định cột dùng trong `WHERE`, `JOIN`, `ORDER BY` và `GROUP BY`.
3. Xác định truy vấn cần equality, range hay prefix search.
4. Nhóm các điều kiện thường xuất hiện cùng nhau.
5. Thiết kế composite index theo equality prefix, range và thứ tự cần trả về.
6. Kiểm tra khả năng covering nếu có lợi ích rõ ràng.
7. Chạy `EXPLAIN` trước và sau khi tạo index.
8. Đo thời gian và số hàng thực tế bằng `EXPLAIN ANALYZE` hoặc công cụ đo workload.
9. Đánh giá thêm dung lượng index và chi phí INSERT/UPDATE/DELETE.
10. Xóa index dư thừa chỉ sau khi xác minh không có truy vấn hoặc constraint nào phụ thuộc.

Ví dụ workload thường gặp:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Một index ứng viên có thể là:

```sql
CREATE INDEX idx_orders_tenant_status_created_order
ON orders (tenant_id, status, created_at);
```

Index này đặt equality columns trước, sau đó là cột range/sort. `order_id` là primary key và được tự động mang trong secondary index entry, nên không cần khai báo lại. Nhưng có nên đưa `total_amount` vào cuối index để covering hay không cần dựa trên tần suất truy vấn, độ rộng index và chi phí ghi. Không tạo covering index rộng chỉ để loại bỏ một lần lookup nếu lợi ích không bù được chi phí.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ mỗi index entry là một node | Hiểu sai B+tree và số lần đọc page | Một page chứa nhiều entry và con trỏ con. |
| Nghĩ clustered index chỉ lưu khóa | Bỏ qua việc leaf page chứa toàn bộ hàng | Clustered leaf chứa dữ liệu hàng. |
| Nghĩ secondary index trỏ tới địa chỉ vật lý cố định | Hiểu sai cách InnoDB định vị hàng | Secondary leaf mang clustered key để lookup clustered tree. |
| Nghĩ có index thì truy vấn chắc chắn nhanh | Bỏ qua selectivity, range size và random I/O | Đo bằng EXPLAIN và dữ liệu thực tế. |
| Bỏ qua leftmost prefix | Composite index không phục vụ truy vấn dự kiến | Đặt thứ tự cột theo mẫu equality/range/order. |
| Đặt cột range quá sớm trong composite index | Các cột sau có thể không thu hẹp range hiệu quả | Cân nhắc equality prefix trước range. |
| Dùng hàm trên cột index mà không xem access path | Index range lookup có thể không được dùng | Viết điều kiện sargable hoặc tạo functional/generated-column index. |
| SELECT thêm nhiều cột ngoài covering index | Phát sinh clustered lookup | Chỉ thêm cột cần thiết hoặc đánh giá covering index. |
| Tạo quá nhiều index | INSERT/UPDATE/DELETE chậm và tốn dung lượng | Chỉ giữ index phục vụ workload/constraint thực tế. |
| Tin cardinality là số chính xác | Dự đoán sai selectivity | Xem là ước lượng và cập nhật thống kê khi cần. |
| Cho rằng thứ tự leaf page là thứ tự SELECT | Ứng dụng phụ thuộc thứ tự không được bảo đảm | Luôn dùng `ORDER BY` ở query block ngoài. |

## 18. Bài tập thực hành

### Bài tập A — Quan sát clustered và secondary index

1. Tạo bảng `customers` có primary key `customer_id`.
2. Tạo secondary index unique trên `email`.
3. Chạy SELECT theo primary key và theo email.
4. Vẽ đường đi B+tree cho từng truy vấn.
5. Giải thích vì sao lookup theo email có thể cần thêm clustered lookup.

### Bài tập B — Composite index và leftmost prefix

1. Tạo index `(tenant_id, status, created_at)`.
2. Chạy truy vấn chỉ theo `tenant_id`.
3. Chạy truy vấn theo `tenant_id` và `status`.
4. Chạy truy vấn chỉ theo `status`.
5. Dùng EXPLAIN so sánh access path và giải thích leftmost prefix.

### Bài tập C — Equality và range

1. Tạo index `(tenant_id, status, created_at)`.
2. Chạy equality trên hai cột đầu và range trên `created_at`.
3. Thay điều kiện range bằng hàm `DATE(created_at)`.
4. So sánh EXPLAIN và xác định khi nào index range lookup bị ảnh hưởng.

### Bài tập D — Covering index

1. Tạo index `(city, created_at)`.
2. SELECT chỉ các cột nằm trong index.
3. SELECT thêm `full_name`.
4. Quan sát `Extra`; giải thích vì sao `customer_id` đã có sẵn nhờ primary key suffix nhưng `full_name` vẫn cần clustered lookup.
5. Đánh giá có nên thêm `full_name` vào index hay không.

### Bài tập E — Đo tác động của index

1. Nạp dữ liệu thử đủ lớn và có phân bố khác nhau.
2. Chạy query trước khi tạo index và ghi nhận thời gian/kế hoạch.
3. Tạo index ứng viên và chạy lại.
4. Chạy `ANALYZE TABLE` rồi kiểm tra thống kê.
5. Đo thêm chi phí INSERT/UPDATE để đánh giá trade-off.

Bạn hoàn thành bài khi có thể giải thích đường đi root-to-leaf, phân biệt clustered/secondary lookup, dự đoán composite index có phù hợp với điều kiện truy vấn hay không và xác minh lựa chọn của optimizer bằng EXPLAIN.

## 19. Nguyên tắc cần ghi nhớ

- InnoDB tổ chức các index thông thường bằng B+tree gồm root, intermediate và leaf page.
- Tất cả leaf page ở cùng độ sâu; leaf page được liên kết theo thứ tự khóa để hỗ trợ range scan.
- Page là đơn vị lưu trữ và cache; page size mặc định thường là 16 KiB nhưng có thể cấu hình.
- Clustered index leaf chứa toàn bộ dữ liệu hàng; secondary index leaf chứa secondary key và clustered key để định vị hàng.
- Lookup qua secondary index có thể cần thêm bước tra clustered index; covering index có thể bỏ bước này.
- Composite index được sắp theo thứ tự cột từ trái sang phải và tuân theo leftmost prefix.
- Equality prefix trước range thường là mẫu hữu ích cho composite index.
- Index có thể hỗ trợ ORDER BY/GROUP BY nhưng phải kiểm tra execution plan.
- INSERT/UPDATE/DELETE phải duy trì index; nhiều index làm tăng chi phí ghi và dung lượng.
- Optimizer chọn index dựa trên ước lượng chi phí; có index không có nghĩa luôn được dùng.
- `EXPLAIN`, `EXPLAIN ANALYZE`, `SHOW INDEX` và `ANALYZE TABLE` giúp đánh giá access path và thống kê.
- Không suy ra thứ tự kết quả từ B+tree; dùng `ORDER BY` khi cần thứ tự xác định.

Khi hiểu cấu trúc B+tree và đường đi của từng loại lookup, bạn có thể thiết kế index theo cách dữ liệu được lưu và truy vấn được thực thi. Kết hợp leftmost prefix, covering index, thống kê và EXPLAIN sẽ giúp cân bằng tốc độ đọc với chi phí lưu trữ và ghi dữ liệu trong MySQL.
