# Using temporary, filesort và ý nghĩa thao tác sắp xếp

Khi đọc `EXPLAIN` của MySQL, hai dấu hiệu thường khiến người mới lo lắng là `Using temporary` và `Using filesort`. Chúng mô tả hai công việc khác nhau trong execution plan:

- `Using temporary` cho biết MySQL dùng một internal temporary table để xử lý một phần truy vấn.
- `Using filesort` cho biết MySQL cần một bước sắp xếp bổ sung vì thứ tự kết quả không được cung cấp trực tiếp bởi access path đang dùng.

Hai dấu hiệu này không đồng nghĩa với lỗi hoặc chắc chắn truy vấn đang ghi dữ liệu tạm ra đĩa. Internal temporary table có thể nằm trong bộ nhớ hoặc chuyển sang lưu trữ trên đĩa tùy kích thước, kiểu dữ liệu, phiên bản và cấu hình. `filesort` là tên thuật toán sắp xếp của MySQL; nó có thể hoàn thành trong bộ nhớ hoặc cần các file tạm khi dữ liệu sort vượt khả năng xử lý trong sort buffer.

Để đánh giá đúng, hãy xác định node nào tạo dữ liệu tạm, bao nhiêu hàng đi vào sort, index có thể đáp ứng thứ tự hay không, và số liệu thực tế có cho thấy áp lực I/O hoặc bộ nhớ hay không. Bài học này tập trung vào cách đọc `Extra`, cây `TREE`, `EXPLAIN ANALYZE` và các status counter liên quan.

## 1. Hai thông báo `Extra` biểu thị điều gì?

Với `EXPLAIN` dạng bảng, MySQL có thể hiển thị các dấu hiệu sau trong cột `Extra`:

| Extra | Ý nghĩa |
|---|---|
| `Using temporary` | Truy vấn cần internal temporary table để xử lý một phần kết quả trung gian. |
| `Using filesort` | MySQL thực hiện bước sort riêng thay vì đọc kết quả theo đúng thứ tự từ access path hiện tại. |
| `Using index` | Truy vấn có thể lấy các cột cần thiết từ index, thường được gọi là covering index access. |
| `Using where` | Có điều kiện được đánh giá để lọc hàng sau hoặc trong quá trình đọc. |
| `Using index condition` | Index Condition Pushdown kiểm tra một phần điều kiện ngay ở storage engine trước khi đọc toàn bộ hàng. |

`Using temporary` và `Using filesort` trả lời hai câu hỏi khác nhau. Một truy vấn có thể chỉ cần sort, chỉ cần temporary table, cần cả hai, hoặc không cần cái nào. Không nên gom chúng thành một khái niệm chung là “truy vấn ghi ra đĩa”.

### Không đánh giá hiệu năng chỉ bằng chữ `Using`

`Using filesort` trên 40 hàng có thể rất rẻ. Một table scan tuần tự trên bảng nhỏ cũng có thể rẻ hơn index lookup nhiều lần. Ngược lại, một sort trên hàng triệu hàng hoặc một temporary table lớn phải spill ra đĩa có thể là điểm nghẽn đáng kể.

Hãy kết hợp `Extra` với:

- Số hàng ước lượng và số hàng thực tế.
- Số vòng lặp của iterator.
- Thời gian thực tế của node sort/materialize.
- Số lượng page và dữ liệu cần xử lý.
- Các status counter về temporary table và sort.
- Kế hoạch thực thi trước/sau khi thay index hoặc SQL.

## 2. Internal temporary table là gì?

Internal temporary table là cấu trúc MySQL tự tạo trong lúc thực hiện truy vấn để lưu hoặc tổ chức dữ liệu trung gian. Nó khác với bảng tạm do ứng dụng tự tạo bằng `CREATE TEMPORARY TABLE`.

Ví dụ ứng dụng tự tạo bảng tạm:

```sql
CREATE TEMPORARY TABLE selected_customer_ids (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
);
```

Bảng trên có tên và vòng đời do session SQL quản lý. Trong khi đó, internal temporary table là chi tiết thực thi do optimizer/executor tạo ra; ứng dụng không tham chiếu trực tiếp bằng tên SQL.

### Những thao tác có thể cần internal temporary table

Tùy cấu trúc truy vấn và khả năng tận dụng index, MySQL có thể cần temporary table cho:

- Một số dạng `GROUP BY` hoặc aggregate.
- `DISTINCT` khi cần loại trùng bằng cách lưu/tổ chức tập kết quả.
- Một số truy vấn `UNION` cần khử trùng hoặc kết hợp kết quả.
- Một số truy vấn có `ORDER BY` và `GROUP BY` không thể giải quyết trực tiếp bằng index.
- Một số derived table, CTE hoặc subquery được materialize.
- Một số window function cần lưu hoặc tổ chức partition/frame trung gian.

Đây là các trường hợp thường gặp, không phải quy tắc rằng cứ viết `GROUP BY`, `DISTINCT`, `UNION`, CTE hay window function là chắc chắn có `Using temporary`. Optimizer có thể dùng index, merge query block hoặc chọn chiến lược khác để tránh temporary table.

### Temporary table có thể ở RAM hoặc trên đĩa

Internal temporary table có thể được giữ trong bộ nhớ khi kích thước và kiểu dữ liệu cho phép. Khi vượt giới hạn hoặc gặp điều kiện không thể xử lý bằng cấu trúc trong bộ nhớ, MySQL có thể chuyển sang internal on-disk temporary table.

Từ MySQL 8.0.16, `TempTable` là storage engine mặc định cho internal in-memory temporary table. Internal temporary table trên đĩa sử dụng InnoDB. Chi tiết ngưỡng và cách chuyển đổi phụ thuộc phiên bản/cấu hình; không nên giả định một biến duy nhất điều khiển toàn bộ hành vi.

Điều cần nhớ:

- `Using temporary` không có nghĩa chắc chắn temporary table nằm trên đĩa.
- Temporary table trong RAM vẫn tiêu thụ bộ nhớ và CPU.
- Temporary table trên đĩa có thể phát sinh I/O và tăng độ trễ.
- Một số materialization có thể xuất hiện trong plan mà không nhất thiết biểu diễn bằng đúng chuỗi `Using temporary` trong mọi định dạng EXPLAIN.

## 3. Filesort là gì?

`filesort` là tên thuật toán MySQL sử dụng khi cần sắp xếp hàng theo `ORDER BY`, hoặc trong một số thao tác khác cần thứ tự, mà access path không cung cấp thứ tự phù hợp.

Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
ORDER BY total_amount DESC;
```

Nếu MySQL đọc hàng theo một index không có thứ tự `total_amount` phù hợp, nó cần một bước sort riêng. `EXPLAIN` truyền thống có thể hiển thị `Using filesort`; `EXPLAIN FORMAT=TREE` thường biểu diễn bước này bằng iterator `Sort`.

### Filesort không nhất thiết tạo file trên đĩa

Tên `filesort` có từ lịch sử của MySQL và không khẳng định mỗi lần sort đều ghi file. Nếu dữ liệu sort vừa với vùng bộ nhớ được cấp phát, MySQL có thể hoàn tất sort trong RAM. Nếu dữ liệu lớn hơn khả năng xử lý trong sort buffer, thuật toán có thể tạo các run đã sắp xếp ở file tạm rồi merge chúng.

Một quy trình khái niệm:

```text
Các hàng thỏa WHERE
        |
        v
Tạo sort key và thông tin hàng cần truy xuất
        |
        v
Đưa dữ liệu vào sort buffer
        |
        +---- đủ chỗ ----> sắp xếp trong bộ nhớ
        |
        +---- thiếu chỗ --> tạo các run tạm đã sắp xếp
                               |
                               v
                         merge các run
        |
        v
Trả hàng theo ORDER BY
```

Đây là sơ đồ khái niệm; thuật toán cụ thể và dữ liệu được giữ trong sort record phụ thuộc phiên bản, query shape và lựa chọn của MySQL.

### Filesort có thể sort key trước rồi mới lấy hàng

Tùy trường hợp, MySQL có thể lưu sort key cùng row ID/định danh hàng rồi truy xuất các cột cần thiết sau khi sắp xếp, hoặc lưu thêm dữ liệu cần thiết trong sort record. Điều này ảnh hưởng kích thước bộ nhớ và số lần truy cập hàng. Không nên giả định filesort luôn copy toàn bộ row hoặc luôn chỉ giữ row ID.

### LIMIT có thể giảm công việc sort nhưng không đảm bảo bỏ qua sort

Với `ORDER BY ... LIMIT N`, MySQL có thể sử dụng chiến lược top-N/priority queue trong trường hợp phù hợp để giữ các hàng tốt nhất thay vì lưu toàn bộ thứ tự hoàn chỉnh. Tuy vậy, engine vẫn có thể phải đọc và đánh giá toàn bộ candidate rows để xác định N hàng đứng đầu.

Nếu index cung cấp đúng thứ tự, MySQL có thể đọc theo index và dừng sớm khi đã lấy đủ N hàng. Đây thường là lợi ích lớn hơn so với chỉ tối ưu thuật toán filesort.

## 4. Temporary table và filesort có thể cùng xuất hiện

Hai công việc này độc lập:

```text
Input rows
    |
    v
Temporary table (lưu/tổ chức dữ liệu trung gian)
    |
    v
Sort (sắp xếp theo thứ tự yêu cầu)
    |
    v
Final result
```

Ví dụ một truy vấn nhóm dữ liệu rồi sắp theo kết quả tổng hợp:

```sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;
```

MySQL cần tính aggregate theo `status`, sau đó sắp xếp các nhóm theo `revenue` vừa tính. Một execution plan có thể cần cấu trúc trung gian để tạo nhóm và một bước sort để sắp các nhóm theo tổng doanh thu. Tùy index, dữ liệu và optimizer, `EXPLAIN` có thể hiển thị cả `Using temporary` lẫn `Using filesort`.

Không phải mọi truy vấn aggregate đều cần cả hai. Nếu nhóm được đọc theo thứ tự index phù hợp, MySQL có thể tránh một số temporary operation. Nhưng `ORDER BY` theo giá trị aggregate thường vẫn cần sort vì thứ tự tổng doanh thu chỉ biết sau khi tính từng nhóm.

## 5. Chuẩn bị dữ liệu thực hành

Tạo bảng đơn hàng với hai index có mục đích khác nhau:

```sql
CREATE TABLE orders_sort_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_status_created_order (
        tenant_id,
        status,
        created_at,
        order_id
    ),
    KEY idx_orders_tenant_total (
        tenant_id,
        total_amount
    ),
    KEY idx_orders_tenant_created_order (
        tenant_id,
        created_at,
        order_id
    )
) ENGINE=InnoDB;
```

Nạp một ít dữ liệu minh họa:

```sql
INSERT INTO orders_sort_demo (
    order_id,
    tenant_id,
    customer_id,
    status,
    created_at,
    total_amount
)
VALUES
    (1001, 10, 1, 'PAID', '2026-01-03 09:00:00', 250.00),
    (1002, 10, 2, 'NEW',  '2026-01-05 10:00:00', 120.00),
    (1003, 10, 1, 'PAID', '2026-01-08 11:00:00', 450.00),
    (1004, 10, 3, 'PAID', '2026-01-10 12:00:00',  90.00),
    (1005, 20, 2, 'PAID', '2026-01-11 13:00:00', 180.00),
    (1006, 10, 2, 'CANCELLED', '2026-01-12 14:00:00', 75.00);
```

Để chạy ví dụ JOIN ở phần 10, tạo thêm bảng khách hàng:

```sql
CREATE TABLE customers_sort_demo (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

INSERT INTO customers_sort_demo (customer_id, customer_name)
VALUES
    (1, 'An Nguyen'),
    (2, 'Binh Tran'),
    (3, 'Chi Le');
```

Fixture nhỏ giúp minh họa SQL. Optimizer có thể chọn table scan thay index vì bảng quá nhỏ; muốn đánh giá kế hoạch và hiệu năng thực tế, hãy dùng tập dữ liệu đủ lớn và có phân bố gần production.

## 6. Đọc `Using filesort` trong EXPLAIN

Thử sắp xếp theo `total_amount` trong tenant 10:

```sql
EXPLAIN
SELECT order_id, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
ORDER BY total_amount DESC;
```

Index `idx_orders_tenant_total` có thể hỗ trợ lọc tenant và đọc theo `total_amount`. Nếu optimizer chọn index đó và hướng scan phù hợp, nó có thể tránh filesort. Tuy nhiên, trên fixture nhỏ optimizer có thể chọn table scan rồi sort vì chi phí thấp hơn.

Để quan sát trường hợp sort cần thiết, thử sắp theo cột không nằm trong thứ tự index phù hợp:

```sql
EXPLAIN
SELECT order_id, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
ORDER BY created_at DESC, total_amount DESC;
```

Index hiện có không có thứ tự liên tiếp `(tenant_id, created_at, total_amount)`; MySQL có thể phải dùng filesort sau khi lọc. Xác nhận bằng `Extra`, `FORMAT=TREE` hoặc `FORMAT=JSON` thay vì đoán chỉ từ DDL.

### Filesort trong TREE

```sql
EXPLAIN FORMAT=TREE
SELECT order_id, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
ORDER BY created_at DESC, total_amount DESC;
```

Nếu kế hoạch cần sort, cây có thể có hình dạng:

```text
-> Sort: created_at DESC, total_amount DESC
    -> Index lookup/range scan on orders_sort_demo
       using an index for tenant_id
```

Node `Sort` nhận các hàng từ access iterator bên dưới và phát ra theo thứ tự yêu cầu. Số hàng của child cho biết sort phải xem xét bao nhiêu candidate rows; số hàng của parent có thể ít hơn nếu có `LIMIT`.

## 7. Dùng index để tránh filesort

Index B+tree có thể cung cấp thứ tự nếu các cột đầu được cố định bằng equality và các cột tiếp theo khớp thứ tự `ORDER BY`.

Truy vấn:

```sql
SELECT order_id, created_at, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Index phù hợp:

```sql
KEY idx_orders_tenant_status_created_order (
    tenant_id,
    status,
    created_at,
    order_id
)
```

Sau khi cố định `tenant_id` và `status`, các entry tiếp theo được sắp theo `created_at`, rồi `order_id`. MySQL có thể scan ngược để đáp ứng thứ tự DESC trên cả hai cột khi access path phù hợp. Khi index cung cấp thứ tự, nó có thể tránh một bước filesort và dừng đọc khi đã tìm đủ 20 hàng.

### Điều kiện để index hỗ trợ ORDER BY

- Các cột đầu của index phải được ràng buộc phù hợp, thường là equality predicate.
- Các cột `ORDER BY` phải khớp thứ tự tiếp theo của index.
- Hướng ASC/DESC phải tương thích với cách scan index. MySQL 8.0 hỗ trợ descending index; mixed directions có thể cần index khai báo chiều tương ứng.
- Biểu thức trong `ORDER BY` có thể ngăn sử dụng index thông thường nếu không có functional index/generated column tương ứng.
- Collation của biểu thức sắp xếp phải phù hợp với collation/index.
- Prefix index trên chuỗi không chứa toàn bộ giá trị nên không thể cung cấp mọi thứ tự yêu cầu trên toàn chuỗi.
- Khi `ORDER BY` dùng cột từ nhiều bảng, join order và cách truy cập có thể khiến index của một bảng không đủ để đáp ứng thứ tự toàn kết quả.

Không thêm index chỉ vì thấy `Using filesort`. Hãy kiểm tra số hàng phải sort, tần suất truy vấn và chi phí ghi/dung lượng của index mới.

## 8. GROUP BY và Using temporary

Ví dụ nhóm số đơn theo trạng thái:

```sql
EXPLAIN
SELECT status, COUNT(*) AS order_count
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status;
```

Index có prefix `(tenant_id, status)` có thể giúp MySQL đọc các hàng của tenant theo nhóm status. Trong một số trường hợp, engine có thể aggregate theo thứ tự index và tránh temporary table; trong trường hợp khác, optimizer có thể dùng temporary table hoặc chiến lược khác.

Thêm thứ tự theo aggregate:

```sql
EXPLAIN
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;
```

`revenue` là kết quả tính từ các hàng trong mỗi nhóm, không phải cột index có thứ tự sẵn. MySQL thường cần tạo kết quả nhóm rồi sắp xếp các nhóm theo revenue. Đây là tình huống dễ xuất hiện `Using temporary` và `Using filesort` cùng lúc.

### GROUP BY không tự đảm bảo thứ tự kết quả

Đừng dựa vào việc các hàng được nhóm để giả định kết quả luôn được sắp xếp. Nếu ứng dụng cần thứ tự, hãy khai báo `ORDER BY` rõ ràng. Đặc biệt trên MySQL 8.0, không nên dựa vào hành vi sắp xếp ngầm của GROUP BY từ các phiên bản cũ.

## 9. DISTINCT, UNION và các thao tác trung gian

`DISTINCT` cần bảo đảm các hàng đầu ra không trùng theo danh sách biểu thức được chọn. Tùy index và kế hoạch, MySQL có thể phát hiện giá trị trùng khi duyệt index hoặc cần temporary structure để lưu/khử trùng.

Ví dụ:

```sql
EXPLAIN
SELECT DISTINCT status
FROM orders_sort_demo
WHERE tenant_id = 10;
```

Với index phù hợp theo `(tenant_id, status)`, MySQL có thể tận dụng thứ tự index để loại trùng hiệu quả. Không có index phù hợp, có thể cần xử lý tập kết quả trung gian.

`UNION DISTINCT` cũng cần khử các hàng trùng giữa các nhánh:

```sql
EXPLAIN
SELECT customer_id
FROM orders_sort_demo
WHERE tenant_id = 10
UNION
SELECT customer_id
FROM orders_sort_demo
WHERE tenant_id = 20;
```

`UNION` mặc định loại trùng; `UNION ALL` giữ nguyên hàng trùng và thường tránh được công việc khử trùng. Chỉ đổi sang `UNION ALL` khi ngữ nghĩa nghiệp vụ cho phép giữ duplicate.

## 10. Sort trong JOIN và nhiều nhánh dữ liệu

Một truy vấn JOIN có thể cần sort sau khi các nhánh đã được nối:

```sql
EXPLAIN FORMAT=TREE
SELECT
    o.order_id,
    c.customer_name,
    o.created_at
FROM orders_sort_demo AS o
JOIN customers_sort_demo AS c
  ON c.customer_id = o.customer_id
WHERE o.tenant_id = 10
ORDER BY c.customer_name, o.created_at DESC;
```

Ở ví dụ này, thứ tự yêu cầu dùng cột từ cả hai bảng. Một index trên orders không nhất thiết có thể cung cấp toàn bộ thứ tự sau JOIN. Optimizer có thể thực hiện join rồi sort kết quả.

Nếu sort node nhận hàng sau JOIN, hãy xem:

1. Bao nhiêu hàng được tạo ra sau mỗi join iterator?
2. Có fan-out khiến tập kết quả tăng mạnh không?
3. Có thể lọc sớm ở một nhánh mà không đổi semantics không?
4. Có thể đổi join order hoặc index để giảm tập dữ liệu trước sort không?
5. Có thực sự cần sắp xếp toàn bộ cột hay chỉ một tập hẹp trước LIMIT?

Không cố ép index trên một bảng để thay thế sort khi thứ tự cuối cùng phụ thuộc cột từ nhiều bảng.

## 11. LIMIT, OFFSET và top-N sorting

`LIMIT` giới hạn số hàng trả về, nhưng không tự động giới hạn số hàng phải đọc hoặc sắp xếp.

Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
ORDER BY total_amount DESC
LIMIT 20;
```

Nếu không có index đáp ứng thứ tự `total_amount`, MySQL có thể phải xét toàn bộ hàng phù hợp rồi mới xác định 20 hàng lớn nhất. Một số trường hợp có thể dùng top-N/priority queue để giảm bộ nhớ và công việc sort, nhưng vẫn phải kiểm tra candidate rows.

`LIMIT 20 OFFSET 100000` còn phải bỏ qua nhiều hàng trước khi trả trang cần thiết. Với phân trang sâu trên bảng lớn, keyset pagination thường hiệu quả hơn nếu có khóa sắp xếp ổn định:

```sql
SELECT order_id, created_at, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
  AND (created_at, order_id) < ('2026-01-10 12:00:00', 1004)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Ví dụ này có thể tận dụng index `idx_orders_tenant_created_order (tenant_id, created_at, order_id)` đã khai báo trong schema. Điều kiện tuple dùng cho thứ tự giảm dần và cần index tương ứng; hãy kiểm tra semantics với NULL và tie-breaker. Keyset pagination tránh phải đọc rồi bỏ qua số lượng lớn hàng như OFFSET cao.

## 12. Đọc `Using temporary` và `Using filesort` trong các định dạng EXPLAIN

### Traditional EXPLAIN

```sql
EXPLAIN
SELECT
    status,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;
```

Xem cột `Extra` để biết có `Using temporary`, `Using filesort`, hoặc cả hai. Cột này cho biết loại thao tác, nhưng không mô tả đầy đủ kích thước dữ liệu tạm hay thời gian thực tế.

### EXPLAIN FORMAT=JSON

```sql
EXPLAIN FORMAT=JSON
SELECT
    status,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;
```

JSON plan có thể biểu diễn thuộc tính như `using_temporary_table` và `using_filesort` trong query block hoặc node liên quan. Cấu trúc JSON lồng nhau giúp liên hệ thao tác với query block/table cụ thể.

`EXPLAIN FORMAT=TREE` được hỗ trợ từ MySQL 8.0.16; `EXPLAIN ANALYZE` được hỗ trợ từ MySQL 8.0.18. Nếu server cũ hơn, dùng định dạng EXPLAIN được phiên bản đó hỗ trợ.

### EXPLAIN FORMAT=TREE và EXPLAIN ANALYZE

```sql
EXPLAIN FORMAT=TREE
SELECT
    status,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;

EXPLAIN ANALYZE
SELECT
    status,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;
```

Trong TREE, tìm node `Sort`, `Aggregate`, `Group aggregate`, `Temporary table` hoặc node materialization tương ứng. `EXPLAIN ANALYZE` cho biết số hàng thực tế và thời gian iterator, giúp xác định sort đang xử lý bao nhiêu hàng và chiếm bao nhiêu thời gian.

`EXPLAIN ANALYZE` thực thi SELECT. Không chạy tùy tiện trên truy vấn lớn hoặc đang gây tải cao; chọn môi trường và thời điểm phù hợp.

## 13. Theo dõi temporary table bằng status variables

Các status counter giúp quan sát số internal temporary table được tạo trong một session hoặc trên toàn server.

Kiểm tra session:

```sql
SHOW SESSION STATUS LIKE 'Created_tmp%';
```

Kiểm tra các biến toàn cục:

```sql
SHOW GLOBAL STATUS LIKE 'Created_tmp%';
```

Hai counter thường quan tâm:

- `Created_tmp_tables`: số internal temporary table được tạo.
- `Created_tmp_disk_tables`: số internal on-disk temporary table được tạo.

Các counter là số tích lũy trong phạm vi session/server kể từ lần khởi tạo hoặc reset phù hợp; chúng không tự gắn với một câu SQL duy nhất. Để đánh giá một truy vấn, ghi giá trị trước và sau khi chạy trong session thử nghiệm riêng rồi lấy phần chênh lệch.

Không diễn giải `Created_tmp_disk_tables` như số lần filesort ghi file. Filesort có thể tạo file tạm để merge mà không tương đương một internal temporary table được đếm bằng counter này.

Trên các phiên bản dùng `TempTable`, internal temporary table có thể sử dụng memory-mapped files trước khi chuyển sang InnoDB. `Created_tmp_disk_tables` không đếm các internal temporary table được lưu trong memory-mapped files; vì vậy counter này có thể thấp hơn tổng số trường hợp TempTable đã dùng vùng lưu trữ ngoài RAM. Hãy đọc counter cùng biến cấu hình và phiên bản server.

### Biến cấu hình liên quan

Một số biến có thể giúp hiểu giới hạn temporary table, tùy phiên bản:

```sql
SHOW VARIABLES LIKE 'internal_tmp_mem_storage_engine';
SHOW VARIABLES LIKE 'tmp_table_size';
SHOW VARIABLES LIKE 'temptable_max_ram';
SHOW VARIABLES LIKE 'temptable_max_mmap';
```

`tmp_table_size` giới hạn kích thước của một số internal in-memory temporary table trước khi cần chuyển sang lưu trữ trên đĩa; với TempTable còn có giới hạn tổng như `temptable_max_ram` và vùng memory-mapped như `temptable_max_mmap` trên các phiên bản hỗ trợ. Không phải biến nào cũng tồn tại hoặc có cùng semantics trên mọi bản MySQL. Đọc giá trị thực tế của phiên bản đang chạy trước khi điều chỉnh. Tăng giới hạn bộ nhớ quá cao có thể làm nhiều session đồng thời tiêu thụ RAM lớn.

## 14. Theo dõi filesort bằng status variables

Các counter liên quan tới sort:

```sql
SHOW SESSION STATUS LIKE 'Sort%';
SHOW GLOBAL STATUS LIKE 'Sort%';
```

Các biến thường gặp:

| Counter | Ý nghĩa khái quát |
|---|---|
| `Sort_scan` | Số lần sort gắn với scan. |
| `Sort_range` | Số lần sort gắn với range access. |
| `Sort_rows` | Số hàng đã được sort. |
| `Sort_merge_passes` | Số merge pass khi sort cần hợp nhất các run đã sắp xếp. |

`Sort_merge_passes` tăng có thể là dấu hiệu sort phải tạo và merge nhiều run do dữ liệu vượt sort buffer. Nhưng hãy xem cùng workload, số hàng sort và thời gian; một vài merge pass không tự động chứng minh hệ thống có vấn đề.

`sort_buffer_size` là vùng bộ nhớ sort cho connection/operation cần sort. Tăng biến này có thể giúp một số sort lớn giảm merge pass, nhưng bộ nhớ có thể được cấp phát cho nhiều session đồng thời. Đừng tăng global value một cách máy móc; trước hết giảm số hàng cần sort hoặc thiết kế index hỗ trợ thứ tự.

## 15. Nguyên nhân thường gặp của Using temporary và filesort

### ORDER BY không khớp index

Ví dụ index `(tenant_id, status, created_at)` nhưng truy vấn lọc `tenant_id` rồi sắp theo `total_amount`. Index không cung cấp thứ tự cần thiết nên MySQL phải sort.

### GROUP BY và ORDER BY theo hai tiêu chí khác nhau

MySQL có thể đọc và gom theo khóa nhóm, sau đó sort các nhóm theo aggregate hoặc biểu thức khác. Temporary table và filesort có thể cùng xuất hiện.

### DISTINCT hoặc UNION cần khử trùng

Khi không thể tận dụng thứ tự index để nhận biết giá trị trùng, MySQL có thể cần cấu trúc trung gian để loại duplicate.

### ORDER BY dùng biểu thức

Ví dụ:

```sql
ORDER BY DATE(created_at)
```

Index thông thường trên `created_at` không nhất thiết đáp ứng thứ tự của biểu thức `DATE(created_at)`. Cân nhắc range predicate trên cột gốc hoặc functional index/generated column nếu workload thực sự cần.

### ORDER BY kết hợp nhiều bảng

Nếu thứ tự phụ thuộc các cột từ nhiều bảng sau JOIN, một index đơn trên một bảng thường không đủ cung cấp thứ tự toàn kết quả.

### Số hàng trung gian quá lớn

Join fan-out hoặc filter đặt quá muộn có thể khiến hàng trăm nghìn hàng đi vào sort/temporary table dù cuối cùng chỉ trả một số nhỏ hàng.

## 16. Quy trình xử lý truy vấn có Using temporary/filesort

1. Chạy `EXPLAIN` và xác nhận `Using temporary`, `Using filesort` nằm ở query block/table nào.
2. Chạy `EXPLAIN FORMAT=TREE` để xác định node Sort, Aggregate, Materialize hoặc Temporary table.
3. Chạy `EXPLAIN ANALYZE` có kiểm soát để biết số hàng thực tế đi vào node và thời gian xử lý.
4. Xác định `ORDER BY`/`GROUP BY` có khớp thứ tự leftmost prefix của index hiện tại không.
5. Kiểm tra cột equality, range, sort và biểu thức/collation.
6. Tìm cách giảm candidate rows trước sort bằng predicate sargable và join order phù hợp.
7. Cân nhắc composite index hỗ trợ cả filter lẫn thứ tự; tính cả dung lượng và write amplification.
8. Với GROUP BY/aggregate, kiểm tra có thể tận dụng thứ tự index để gom nhóm hay không; nếu sort theo aggregate thì chấp nhận có thể cần sort kết quả nhóm.
9. Ghi nhận `Created_tmp%`, `Sort%` trước/sau trong session thử nghiệm riêng.
10. Chỉ điều chỉnh `sort_buffer_size` hoặc giới hạn TempTable sau khi đã hiểu nguyên nhân và ước lượng tải đồng thời.
11. Đo lại kết quả và thời gian; bảo đảm kết quả nghiệp vụ không thay đổi.

Ưu tiên giảm số hàng phải sort và để index cung cấp thứ tự khi phù hợp. Tăng buffer có thể giúp một trường hợp cụ thể nhưng không sửa được một kế hoạch đọc quá nhiều dữ liệu.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách hiểu/xử lý đúng |
|---|---|---|
| Nghĩ `Using filesort` luôn ghi file ra đĩa | Đánh giá sai mức độ tốn I/O | Filesort có thể hoàn tất trong RAM; kiểm tra merge passes và workload. |
| Nghĩ `Using temporary` luôn là disk table | Lo lắng không cần thiết hoặc tăng cấu hình sai | Internal temporary table có thể ở RAM hoặc trên đĩa. |
| Nghĩ temporary table và filesort là một | Không xác định được bước gây chi phí | Temporary lưu/tổ chức dữ liệu trung gian; filesort sắp xếp. |
| Thấy `Using filesort` là thêm index ngay | Index thừa làm chậm DML và tăng dung lượng | Kiểm tra số hàng sort, tần suất query và thứ tự index cần thiết. |
| Tăng `sort_buffer_size` rất lớn trên server | Nhiều connection có thể tiêu thụ RAM đồng thời | Đo trước, thay đổi thận trọng và ưu tiên giảm đầu vào sort. |
| Tăng `tmp_table_size` rồi nghĩ mọi temporary table đều được xử lý | Bỏ qua TempTable và các giới hạn khác theo version | Kiểm tra engine/biến thực tế của phiên bản MySQL. |
| Nghĩ LIMIT 20 nghĩa là chỉ đọc 20 hàng | Sort có thể cần xét toàn bộ candidate rows | Dùng index cung cấp thứ tự hoặc xem top-N strategy và actual rows. |
| Nghĩ GROUP BY tự bảo đảm thứ tự output | Ứng dụng phụ thuộc thứ tự không cam kết | Dùng ORDER BY rõ ràng. |
| Dùng UNION ALL thay UNION mà không kiểm tra duplicate | Thay đổi kết quả nghiệp vụ | Chỉ bỏ khử trùng khi semantics cho phép. |
| Đánh giá counter toàn server như số của một query | Không biết query nào tạo temporary/sort | Dùng session riêng và so sánh delta trước/sau. |

## 18. Bài tập thực hành

### Bài tập A — Đọc filesort

1. Tạo bảng `orders_sort_demo` và nạp fixture.
2. Chạy truy vấn lọc tenant và `ORDER BY created_at, total_amount`.
3. Chạy `EXPLAIN`, `FORMAT=TREE` và quan sát node Sort/`Using filesort`.
4. Ghi số hàng candidate và số hàng kết quả.
5. Giải thích vì sao index hiện có không đáp ứng toàn bộ thứ tự.

### Bài tập B — Tránh filesort bằng composite index

1. Chạy truy vấn equality trên `tenant_id`, `status` và ORDER BY `created_at`, `order_id`.
2. Quan sát index `idx_orders_tenant_status_created_order`.
3. Kiểm tra plan có còn Sort hay không.
4. Đổi một cột ORDER BY hoặc hướng ASC/DESC.
5. Đánh giá index có còn cung cấp thứ tự được yêu cầu không.

### Bài tập C — Temporary table và aggregate

1. Chạy GROUP BY `status` cho một tenant.
2. Chạy lại với ORDER BY `SUM(total_amount) DESC`.
3. So sánh `Using temporary`, `Using filesort` và TREE iterator.
4. Giải thích vì sao thứ tự theo aggregate chỉ xác định sau khi tính nhóm.

### Bài tập D — DISTINCT và UNION

1. Chạy DISTINCT status theo tenant.
2. Thử tạo index `(tenant_id, status)` và chạy lại EXPLAIN.
3. Chạy UNION và UNION ALL trên hai tập dữ liệu có giao nhau.
4. So sánh số hàng và công việc khử duplicate.
5. Giải thích vì sao không thể đổi UNION thành UNION ALL nếu cần loại trùng.

### Bài tập E — Theo dõi counter

1. Mở session riêng và ghi `Created_tmp%` cùng `Sort%`.
2. Chạy một truy vấn aggregate/sort đủ lớn.
3. Đọc lại counter và tính delta.
4. Chạy truy vấn có index cung cấp thứ tự.
5. So sánh Sort_rows, Sort_merge_passes và số temporary table.

### Bài tập F — LIMIT và phân trang

1. Chạy ORDER BY không có index với LIMIT 20.
2. Chạy lại với LIMIT 20 OFFSET 100000 trên tập dữ liệu lớn.
3. Tạo index đáp ứng filter/order và thử keyset pagination.
4. Dùng EXPLAIN ANALYZE so sánh actual rows và thời gian.
5. Giải thích khi nào LIMIT giúp dừng sớm và khi nào sort vẫn phải đọc nhiều hàng.

Bạn hoàn thành bài khi phân biệt được internal temporary table với filesort, giải thích được vì sao filesort không nhất thiết ghi file, xác định được node tạo temporary/sort và biết cách dùng index hoặc giảm đầu vào để hạ chi phí.

## 19. Nguyên tắc cần ghi nhớ

- `Using temporary` biểu thị internal temporary table; nó không khẳng định bảng tạm nằm trên đĩa.
- `Using filesort` biểu thị một bước sắp xếp bổ sung; filesort có thể chạy trong RAM hoặc dùng file tạm để merge.
- Temporary table và filesort là hai thao tác khác nhau, có thể xuất hiện riêng hoặc cùng lúc.
- `EXPLAIN FORMAT=TREE` thường thể hiện sort bằng iterator `Sort`; JSON plan có thể có `using_temporary_table` và `using_filesort`.
- Index có thể tránh filesort khi equality prefix và thứ tự cột khớp `ORDER BY`.
- `GROUP BY` có thể tận dụng index để gom nhóm, nhưng `ORDER BY` theo aggregate thường cần sort kết quả nhóm.
- `DISTINCT`/`UNION` có thể cần cấu trúc trung gian để khử trùng; `UNION ALL` chỉ dùng khi chấp nhận duplicate.
- `LIMIT` không bảo đảm chỉ đọc N hàng; sort có thể phải xét toàn bộ candidate rows.
- `Created_tmp_tables`/`Created_tmp_disk_tables` theo dõi internal temporary table; `Sort_merge_passes` theo dõi merge pass của sort.
- Status counter là tích lũy; dùng session riêng và delta trước/sau để gắn với truy vấn.
- Không tăng `sort_buffer_size` hoặc giới hạn TempTable một cách máy móc; cân nhắc RAM theo số connection đồng thời.
- Ưu tiên giảm số hàng đi vào sort, tận dụng index đúng thứ tự và đo lại bằng EXPLAIN ANALYZE.

Khi hiểu đúng `Using temporary` và `Using filesort`, bạn có thể phân biệt việc lưu dữ liệu trung gian với việc sắp xếp, nhận ra khi nào sort thực sự tạo áp lực tài nguyên và chọn cách tối ưu phù hợp. Hãy dựa trên node thực thi, số hàng thực tế, vòng lặp và status counter thay vì kết luận chỉ từ một dòng `Extra`.
