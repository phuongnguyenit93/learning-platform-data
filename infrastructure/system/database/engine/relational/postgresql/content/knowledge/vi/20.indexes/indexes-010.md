# INCLUDE, covering index và index-only scan trong PostgreSQL

Giả sử một hệ thống bán hàng thường xuyên hiển thị **20 đơn hàng mới nhất của một khách**, gồm mã đơn, ngày tạo, trạng thái và tổng tiền:

```sql
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Nếu PostgreSQL có một B-tree index trên `customer_id`, cơ sở dữ liệu có thể tìm các đơn của khách nhanh hơn quét cả bảng. Nhưng để lấy `ordered_at`, `status` và `total_amount`, executor có thể vẫn phải tìm về **bảng heap** cho từng hàng. Khi truy vấn chạy rất thường xuyên và heap lớn, các lần truy cập heap có thể tiêu tốn đáng kể I/O.

Một cách thiết kế là:

```sql
CREATE INDEX idx_orders_customer_recent_cover
ON orders (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

Trong đó:

- `customer_id`, `ordered_at` và `order_id` là **key columns** của index: dùng để tổ chức thứ tự B-tree, tìm kiếm hoặc đáp ứng `ORDER BY` khi điều kiện phù hợp.
- `status` và `total_amount` là **included columns** hay **payload/non-key columns**: được lưu trong bản ghi index để có thể đọc cùng index, nhưng **không tham gia thứ tự B-tree và không là phần khóa tìm kiếm của index**.
- Vì index có thông tin mà query cần, nó là một **covering index đối với truy vấn này**.
- Khi điều kiện về MVCC/visibility cho phép, PostgreSQL có thể chọn **Index Only Scan** để trả kết quả mà không cần truy cập heap cho phần lớn hoặc toàn bộ hàng.

Tuy nhiên, **`INCLUDE` không tự bảo đảm `Index Only Scan`**, và **`Index Only Scan` không tự bảo đảm `Heap Fetches = 0`**. Bài học này tập trung vào cả hai điểm đó để tránh tối ưu chỉ mục theo cảm tính.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **index key** với **included (non-key) column**.
2. Hiểu covering index là một khái niệm **phụ thuộc truy vấn**, không phải một loại index luôn “phủ” mọi truy vấn.
3. Viết cú pháp `CREATE INDEX ... INCLUDE (...)` của PostgreSQL.
4. Giải thích cơ chế **Index Scan**, **Bitmap Heap Scan**, **Index Only Scan** và cách chọn của planner.
5. Hiểu vai trò của **visibility map**, bit **all-visible**, MVCC và `VACUUM` trong việc giảm heap fetch.
6. Phân tích `EXPLAIN (ANALYZE, BUFFERS)`, nhất là `Index Cond`, `Filter`, `Heap Fetches`.
7. Biết cột nào nên là key, cột nào nên là INCLUDE, và khi nào không nên thêm INCLUDE.
8. Hiểu các đánh đổi về **dung lượng index, tốc độ INSERT/UPDATE, HOT update, bloat, WAL** và bảo trì.
9. Kết hợp `INCLUDE` với chỉ mục unique, partial index, chỉ mục nhiều cột và các truy vấn `LIMIT`.
10. Xây dựng thí nghiệm an toàn để **đo** lợi ích thay vì khẳng định chắc chắn từ cú pháp.

## 2. Tư duy về bảng heap và chỉ mục B-tree

Trong một bảng PostgreSQL thông thường, các bản ghi được lưu trong **heap**. Một B-tree index lưu các index entries với các **key** và thông tin định vị tuple tương ứng. Khi truy vấn cần một hàng, PostgreSQL có thể dùng index để thu hẹp vị trí phải tìm.

Một hình dung đơn giản:

```text
INDEX B-TREE                              HEAP TABLE
customer_id / ordered_at / order_id      Toàn bộ các cột của đơn
            |
            +-- tìm entry ----------------> đọc tuple trên heap
                                               |
                                               +-- status
                                               +-- total_amount
                                               +-- note
                                               +-- ...
```

Index thường giúp **không phải đọc mọi hàng của bảng**. Nhưng sau khi xác định vị trí, executor vẫn có thể phải đọc heap để lấy các cột không được index lưu trữ hoặc xác minh tính hiển thị của tuple.

### 2.1. Index Scan truyền thống

Khi query lấy `total_amount` mà index chỉ có `customer_id`, executor có thể:

1. Duyệt B-tree để tìm entry có `customer_id = 42`.
2. Lấy thông tin định vị hàng tương ứng.
3. Truy cập heap để đọc tuple và lấy `total_amount`.
4. Áp dụng những điều kiện bổ sung nếu chưa được xử lý ở index.
5. Trả kết quả.

Nếu trả ít hàng và heap sẵn trong cache, cách này có thể rất tốt. Nếu trả nhiều hàng nằm rải rác trên nhiều heap pages, các truy cập heap có thể tạo chi phí đáng kể.

### 2.2. Index Only Scan

Với index lưu **đủ thông tin mà truy vấn cần**, PostgreSQL có thể tìm và trả dữ liệu qua index. Tuy nhiên, index entry bản thân nó **không chứa đầy đủ thông tin MVCC để chứng minh tuple hiện có được nhìn thấy bởi snapshot của query hay không**. PostgreSQL cần dựa vào **visibility map** hoặc kiểm tra heap.

Ý nghĩa của Index Only Scan là: **có khả năng tránh heap vì cột dữ liệu nằm trong index**, không phải hứa chắc “không bao giờ đọc heap”.

### 2.3. Covering index giải quyết vấn đề gì?

Nếu truy vấn cần chỉ `customer_id`, `ordered_at`, `order_id`, `status` và `total_amount`, ta có thể lưu các cột ít được dùng làm tiêu chí tìm kiếm vào phần INCLUDE, để executor **có sẵn giá trị trong index**.

Đây là tối ưu kiểu **đổi dung lượng và chi phí ghi lấy khả năng giảm đọc heap**, chứ không phải một tính năng miễn phí.

## 3. Cú pháp INCLUDE

Ví dụ B-tree:

```sql
CREATE INDEX index_name
ON table_name (key_column_1, key_column_2)
INCLUDE (payload_column_1, payload_column_2);
```

Với unique index:

```sql
CREATE UNIQUE INDEX index_name
ON table_name (unique_key_1, unique_key_2)
INCLUDE (payload_column);
```

PostgreSQL cũng hỗ trợ `INCLUDE` trong các dạng định nghĩa constraint/index phù hợp. Mức hỗ trợ tùy **index access method**: **B-tree** là ví dụ trung tâm vì có thể trả giá trị cột từ index một cách trực tiếp. Một số access method khác hỗ trợ INCLUDE theo đặc tính riêng; không suy luận rằng mọi phương thức, nhất là **GIN**, đều có hành vi giống B-tree hoặc đều có thể Index Only Scan.

### 3.1. Ba nhóm cột cần phân biệt

| Nhóm | Nằm ở đâu? | Tác dụng |
| --- | --- | --- |
| **Key column** | Trong cấu trúc key của index | Tìm kiếm, so sánh, sắp xếp, tính uniqueness đối với unique index |
| **INCLUDE column** | Payload của index entry ở nơi phù hợp | Có thể trả thêm giá trị cho truy vấn; không tạo thứ tự hoặc key search mới |
| **Cột chỉ có trong heap** | Không được index đang xét lưu | Truy vấn cần giá trị cột đó thường phải tìm về heap |

Ví dụ:

```sql
CREATE INDEX idx_demo_cover
ON some_table (tenant_id, created_at DESC)
INCLUDE (amount, status);
```

Đây là đoạn DDL minh họa, giả định bảng tồn tại. `tenant_id` và `created_at` là key, còn `amount` và `status` là payload.

### 3.2. INCLUDE không tạo “key thứ ba”

Đừng đánh đồng:

```sql
CREATE INDEX idx_key_amount
ON some_table (tenant_id, created_at, amount);
```

với:

```sql
CREATE INDEX idx_include_amount
ON some_table (tenant_id, created_at)
INCLUDE (amount);
```

Ở index thứ nhất, `amount` thuộc **key**, có thể ảnh hưởng thứ tự B-tree và các cơ hội dùng điều kiện tìm kiếm. Ở index thứ hai, `amount` là **payload**, chỉ được lưu thêm để trả dữ liệu.

Việc đặt `amount` vào INCLUDE không tự biến:

```sql
WHERE amount > 100000
```

thành một **Index Cond** B-tree hiệu quả như khi `amount` là key phù hợp với thứ tự các cột trước đó.

## 4. Covering index là khái niệm theo truy vấn

Xét index:

```sql
CREATE INDEX idx_orders_cover
ON orders (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

Truy vấn A:

```sql
SELECT order_id, ordered_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Các cột đầu ra và điều kiện đều có trong index. Nó **có khả năng cover truy vấn A**.

Truy vấn B:

```sql
SELECT
    order_id,
    ordered_at,
    status,
    total_amount,
    customer_note
FROM orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Nếu `customer_note` không có trong index, B **không được index này cover**, dù chỉ thêm một cột so với A.

Truy vấn C:

```sql
SELECT COUNT(*)
FROM orders
WHERE customer_id = 42;
```

Chỉ mục có thể đủ thông tin để hỗ trợ C, mặc dù C không lấy bất kỳ payload INCLUDE nào. Thực tế, một index chỉ có key `customer_id` cũng có thể có khả năng Index Only Scan cho C nếu các điều kiện khác thỏa.

**Kết luận:** `INCLUDE` không bắt buộc để có Index Only Scan. Nó là công cụ **mở rộng tập cột có thể lấy từ một index** mà không phải biến các cột đó thành key.

### 4.1. Điều kiện “cover” không chỉ là SELECT list

Khi quyết định index có đủ cho truy vấn, hãy xét:

- Cột ở `SELECT`.
- Cột dùng trong `WHERE` / join conditions hoặc biểu thức cần đánh giá.
- Cột ở `ORDER BY`, `GROUP BY` và các biểu thức liên quan.
- Cột mà một operator/function cần đọc để tính kết quả.
- Những cột trên bảng hiện tại mà executor phải truy cập ở giai đoạn thích hợp.

Chỉ nhìn danh sách `SELECT` rồi thêm INCLUDE là chưa đủ. Ví dụ SELECT chỉ `total_amount` nhưng điều kiện `WHERE status = 'PAID'` thì query vẫn cần giá trị `status` để lọc, trừ khi các đặc tính của index/predicate cho phép planner chứng minh điều kiện theo cách khác.

## 5. INCLUDE không tham gia thứ tự và tìm kiếm B-tree

Giả sử có index:

```sql
CREATE INDEX idx_customer_time
ON orders (customer_id, ordered_at DESC)
INCLUDE (status, total_amount);
```

### 5.1. Trường hợp tìm kiếm thuận lợi

```sql
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
```

Với B-tree nhiều cột có key đầu `customer_id` và key tiếp `ordered_at`, PostgreSQL có cơ hội dùng những điều kiện đó để xác định vùng index cần quét.

### 5.2. Trường hợp status chỉ là INCLUDE

```sql
WHERE status = 'PAID'
```

Nếu `status` chỉ là INCLUDE, nó **không tạo cấu trúc khóa B-tree theo status**. PostgreSQL có thể đọc `status` từ index entry rồi lọc ngay trong một Index Only Scan nếu kế hoạch cho phép, nhưng không thể dùng status như key dẫn đường để nhảy tới một đoạn B-tree riêng theo giá trị PAID.

Đừng nhầm:

- **Giá trị có trong index** ⇒ có thể tránh phải lấy giá trị đó từ heap.
- **Giá trị là index key phù hợp** ⇒ có thể dùng để giới hạn phạm vi quét hoặc đáp ứng thứ tự index.

Hai lợi ích này khác nhau.

### 5.3. ORDER BY trên cột INCLUDE

Một index:

```sql
ON orders (customer_id, ordered_at)
INCLUDE (total_amount)
```

không tự bảo đảm dữ liệu được sắp theo `total_amount`. Truy vấn:

```sql
WHERE customer_id = 42
ORDER BY total_amount DESC
```

có thể vẫn cần `Sort` hoặc cách xử lý khác. Muốn đáp ứng thứ tự tổng tiền trực tiếp từ B-tree, cần xem index có **total_amount là key ở vị trí phù hợp** hay không.

## 6. Bài lab PostgreSQL: tạo bảng và dữ liệu

Những ví dụ sau dùng schema độc lập `index_include_lab`, chỉ dành cho database thử nghiệm. Việc `CREATE TABLE` và nạp vài chục nghìn dòng có thể dùng dung lượng và thời gian; không chạy tùy tiện trên production.

### 6.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS index_include_lab;
```

### 6.2. Tạo bảng đơn hàng

```sql
CREATE TABLE index_include_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    region_code TEXT NOT NULL,
    customer_note TEXT
);
```

Ở đây:

- `order_id` là định danh hàng.
- `customer_id` dùng lọc các đơn của một khách.
- `ordered_at` dùng hiển thị/sắp xếp theo thời gian.
- `status` và `total_amount` thường được lấy trên màn hình nhưng không nhất thiết dùng để tìm kiếm.
- `region_code` là một chiều lọc bổ sung.
- `customer_note` mô phỏng thông tin text dài hơn, **không nên INCLUDE chỉ vì bảng có cột đó**.

### 6.3. Nạp dữ liệu tổng hợp

```sql
INSERT INTO index_include_lab.orders (
    customer_id,
    ordered_at,
    status,
    total_amount,
    region_code,
    customer_note
)
SELECT
    (g.n % 400) + 1,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + make_interval(mins => g.n),
    CASE
        WHEN (g.n / 13) % 10 < 7 THEN 'PAID'
        WHEN (g.n / 13) % 10 < 9 THEN 'PENDING'
        ELSE 'CANCELLED'
    END,
    (1000 + g.n % 9999)::numeric(12, 2),
    CASE WHEN g.n % 3 = 0 THEN 'S'
         WHEN g.n % 3 = 1 THEN 'N'
         ELSE 'C'
    END,
    repeat('Sample note. ', 10)
FROM generate_series(1, 80000) AS g(n);
```

Lệnh tạo **80.000 hàng** có 400 mã khách giả định. Dùng dữ liệu giả giúp bạn có thể tự kiểm chứng plan mà không liên quan tới thông tin cá nhân thật.

Thời điểm `ordered_at` chạy từ đầu tháng 1 tới cuối tháng 2 năm 2026 (mỗi hàng tăng một phút). Phân bố trạng thái chỉ dùng để mô phỏng dữ liệu đọc/ghi; không phản ánh doanh nghiệp thực.

### 6.4. Thống kê ban đầu

```sql
ANALYZE index_include_lab.orders;

SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT customer_id) AS customers,
    MIN(ordered_at) AS first_order,
    MAX(ordered_at) AS last_order
FROM index_include_lab.orders;
```

Với script nạp thành công một lần, số hàng là 80.000 và số khách là 400. Nếu bảng đã chứa dữ liệu từ lượt trước, số liệu thực tế có thể khác; bài giả định schema ban đầu trống.

## 7. Truy vấn trọng tâm: 20 đơn hàng gần nhất

Truy vấn chính:

```sql
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Truy vấn có hai yêu cầu hiệu năng:

1. **Lọc nhanh:** lấy các đơn của khách 42 sau một mốc thời gian.
2. **Trả kết quả sớm:** ưu tiên đơn mới nhất, chỉ cần 20 hàng.

Một index hợp lý có key theo thứ tự điều kiện và sort:

```sql
CREATE INDEX idx_lab_orders_customer_recent_cover
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

### 7.1. Vì sao customer_id ở đầu?

`customer_id = 42` là điều kiện bằng trên một cột xác định partition logic của kết quả. Với B-tree nhiều cột, key đầu này giúp planner thu hẹp vùng index theo khách.

### 7.2. Vì sao ordered_at DESC tiếp theo?

Các hàng cùng khách được sắp theo thời gian giảm dần trong index. Truy vấn lọc mốc thời gian và lấy những đơn mới nhất có thể tận dụng thứ tự đó; đây là lựa chọn hợp lý cho kiểu `ORDER BY ordered_at DESC LIMIT 20`.

### 7.3. Vì sao order_id DESC là key?

Hai đơn có thể trùng `ordered_at`. Thêm `order_id DESC` làm kết quả **có thứ tự ổn định** và phù hợp `ORDER BY ordered_at DESC, order_id DESC`.

Ở bảng mẫu, order_id là unique. Nếu chỉ đưa order_id vào INCLUDE thay vì key, index không được sắp theo order_id trong những hàng trùng timestamp, nên query có thể cần thêm xử lý sắp xếp.

### 7.4. Vì sao status và total_amount là INCLUDE?

Hai cột xuất hiện ở `SELECT` nhưng không cần tham gia điều kiện tìm kiếm hoặc thứ tự hiển thị của query này. Đưa vào INCLUDE giúp index chứa dữ liệu đầu ra, **không làm key B-tree dài thêm một cách không cần thiết**.

## 8. Index Scan và Index Only Scan trên EXPLAIN

Sau khi tạo index, xem kế hoạch:

```sql
EXPLAIN
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Một dạng plan **có thể** gặp (chỉ mang tính minh họa, không phải output bắt buộc):

```text
Limit
  -> Index Only Scan using idx_lab_orders_customer_recent_cover
       on index_include_lab.orders
       Index Cond: (customer_id = 42 AND ordered_at >= ...)
```

Một plan khác vẫn có thể là `Index Scan`, `Bitmap Heap Scan` hoặc `Seq Scan + Sort`. Planner cân nhắc:

- Thống kê của bảng và cột.
- Số hàng dự kiến trả và độ chọn lọc.
- Có `LIMIT` hay không.
- Chi phí page access, cache, random I/O.
- Tỷ lệ heap pages được đánh dấu all-visible.
- Độ rộng index, chi phí duyệt B-tree.
- Cấu hình planner và phiên bản PostgreSQL.

**Không xem việc có CREATE INDEX là bằng chứng planner bắt buộc dùng index đó.**

### 8.1. Đo thực tế

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

`ANALYZE` ở đây nghĩa là **thực sự thực thi câu SELECT để đo**, khác với chỉ `EXPLAIN` không ANALYZE. `BUFFERS` bổ sung thống kê page hits/reads/writes liên quan tới query.

Khi thấy:

```text
Index Only Scan ...
  Index Cond: (...)
  Heap Fetches: 0
```

thì tại lần chạy đó, executor không cần fetch heap tuple cho những index entries đã đọc do kiểm tra visibility. Đây là dấu hiệu rất tốt, **không phải hợp đồng vĩnh viễn**: sau INSERT/UPDATE/DELETE hoặc với snapshot/VM khác, heap fetches có thể tăng.

### 8.2. Index Only Scan mà Heap Fetches khác 0

Ví dụ một plan minh họa khác:

```text
Index Only Scan using idx_lab_orders_customer_recent_cover ...
  Index Cond: (customer_id = 42)
  Heap Fetches: 19
```

Điều đó **không mâu thuẫn với tên Index Only Scan**. Index chứa các giá trị cột query cần, nhưng PostgreSQL vẫn cần đọc heap để xác minh tuple visibility cho một số entry do heap pages chưa được đánh dấu all-visible.

### 8.3. Index Cond và Filter

Trong EXPLAIN, phân biệt:

- **`Index Cond`:** điều kiện được dùng qua index access method để giới hạn hoặc kiểm tra trong index scan.
- **`Filter`:** điều kiện lọc được đánh giá tại node sau khi có tuple/giá trị tương ứng; có thể khiến nhiều index entries được đọc nhưng không trả kết quả.

Khi một cột chỉ thuộc INCLUDE, nó có thể được đọc từ payload trong Index Only Scan để lọc, nhưng **không trở thành search key của B-tree chỉ vì có trong index**.

## 9. Visibility map: yếu tố quyết định heap fetch

Để hiểu sâu Index Only Scan, phải hiểu **visibility map (VM)**.

PostgreSQL sử dụng MVCC. Một heap page có thể chứa:

- Một phiên bản hàng còn hiển thị.
- Các phiên bản cũ của UPDATE/DELETE.
- Tuple chưa được commit, đang chờ transaction.
- Dữ liệu mà một snapshot cụ thể có thể hoặc không thể nhìn thấy.

Một index entry không đủ thông tin để chứng minh mọi transaction đều được phép thấy tuple đó. PostgreSQL phải kiểm tra tính hiển thị.

### 9.1. Bit all-visible

Visibility map ghi nhận thông tin theo **heap page**. Khi một page có bit **all-visible**, PostgreSQL biết các tuple trên page đó **được nhìn thấy bởi mọi transaction liên quan** theo nghĩa MVCC mà Index Only Scan có thể dùng.

Khi index entry trỏ tới page all-visible:

```text
Index entry -> xem visibility map -> all-visible
            -> có thể trả giá trị từ index
            -> không cần đọc heap page cho kiểm tra visibility
```

Nếu page **chưa all-visible**:

```text
Index entry -> xem visibility map -> chưa all-visible
            -> truy cập heap để kiểm tra tuple visibility
            -> có thể trả hoặc loại theo snapshot
```

Visibility map có kích thước rất nhỏ so với heap và thường có khả năng lưu trong bộ nhớ đệm. Điều đó giúp giảm I/O đáng kể khi tỷ lệ all-visible cao.

### 9.2. VM all-visible khác all-frozen

PostgreSQL còn theo dõi trạng thái liên quan tới freezing để quản lý transaction ID. Đối với bài này, trọng tâm là **all-visible** vì nó quyết định việc Index Only Scan có thể bỏ qua kiểm tra heap cho page đó.

Không đánh đồng:

- Bit **all-visible** dùng làm căn cứ bỏ qua heap visibility fetch.
- Thông tin **all-frozen** liên quan quá trình freeze/tuổi transaction ID.

Một page có thể đủ điều kiện all-visible mà không nhất thiết được hiểu là đã hoàn tất mọi mục tiêu freezing trong mọi ngữ cảnh.

## 10. VACUUM và chỉ mục phủ: tại sao dữ liệu ít thay đổi thường lợi hơn?

Visibility map thường được cập nhật bởi **VACUUM** khi PostgreSQL xác định page đáp ứng điều kiện all-visible. Sau một đợt INSERT/UPDATE, nhiều page mới hoặc đã thay đổi có thể chưa có bit all-visible.

Đó là lý do một covering index trên bảng **chỉ đọc hoặc chủ yếu thêm dữ liệu cũ đã được VACUUM** thường đem lại nhiều heap avoidance hơn một bảng mà mọi hàng bị UPDATE liên tục.

### 10.1. Thí nghiệm trước/sau VACUUM

Sau bulk INSERT và CREATE INDEX ở phần trước, chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Ghi nhận `Heap Fetches` nếu plan là Index Only Scan.

Tiếp đó, thực hiện **bên ngoài transaction block**:

```sql
VACUUM (ANALYZE) index_include_lab.orders;
```

Sau đó chạy lại `EXPLAIN (ANALYZE, BUFFERS)` trên cùng câu SELECT.

Nếu những heap pages chứa tuple liên quan nay được đánh dấu all-visible và planner chọn Index Only Scan, `Heap Fetches` có thể giảm mạnh, đôi khi về 0.

### 10.2. VACUUM không bảo đảm Heap Fetches = 0

Kết quả phụ thuộc:

- Có transaction/snapshot cũ khiến page chưa đủ điều kiện all-visible không.
- Có INSERT/UPDATE/DELETE mới xen vào không.
- Trạng thái tuple và thời gian VACUUM.
- Kiểu bảng, workload và kế hoạch thực thi.

Không khẳng định chạy `VACUUM` một lần sẽ biến mọi truy vấn thành Index Only Scan hoặc làm mọi page all-visible.

### 10.3. Không VACUUM sau mọi query

PostgreSQL có **autovacuum** để dọn tuple cũ và duy trì cơ chế MVCC/visibility theo chính sách cấu hình. Không nên đặt `VACUUM` trước mỗi lần SELECT để “ép index-only”; chi phí bảo trì có thể lớn hơn lợi ích.

Trong ứng dụng thật, phải đo autovacuum, thời gian transaction, tốc độ ghi và tỷ lệ all-visible trước khi điều chỉnh lịch bảo trì.

## 11. Sau UPDATE, index-only scan có thể đọc heap nhiều hơn

Ta thử cập nhật một số đơn:

```sql
UPDATE index_include_lab.orders
SET customer_note = 'Changed after initial load'
WHERE customer_id = 42;
```

Ngay sau UPDATE, các heap pages bị thay đổi có thể mất trạng thái all-visible. Một truy vấn dùng covering index cho khách 42 có thể thấy **Heap Fetches tăng**, dù các cột mà truy vấn SELECT cần vẫn đều nằm trong index.

### 11.1. Chỉ sửa cột không có trong index

`customer_note` không nằm trong covering index. Một UPDATE chỉ sửa cột này **có thể đủ điều kiện HOT update** nếu các điều kiện khác thỏa, ví dụ page còn chỗ và không có index nào yêu cầu cập nhật do giá trị thay đổi.

**HOT (Heap-Only Tuple)** giúp tránh cập nhật index entries trong những điều kiện phù hợp. Nhưng HOT **không đồng nghĩa page vẫn all-visible**: thay đổi tuple vẫn liên quan tới MVCC và visibility map.

### 11.2. Sửa cột INCLUDE có thể phá HOT

Ví dụ:

```sql
UPDATE index_include_lab.orders
SET total_amount = total_amount + 1
WHERE order_id = 100;
```

Vì `total_amount` được lưu trong payload của index `idx_lab_orders_customer_recent_cover`, thay đổi cột đó khiến PostgreSQL phải duy trì index tương ứng; nó **không đủ điều kiện HOT theo trường hợp cột indexed đã thay đổi**.

Đây là **chi phí quan trọng của INCLUDE**. Một cột không dùng làm search key vẫn có thể khiến mỗi lần cập nhật giá trị phải cập nhật index.

### 11.3. Đánh đổi thực tế

| Kiểu workload | Lợi ích tiềm năng của INCLUDE | Rủi ro |
| --- | --- | --- |
| Bảng chủ yếu đọc, ít UPDATE | Cao, page dễ all-visible | Index tốn thêm dung lượng |
| Bảng append-only sau khi dữ liệu ổn định | Tốt cho truy vấn lịch sử | Dữ liệu mới chưa chắc all-visible |
| Bảng trạng thái cập nhật liên tục | Có thể hạn chế | Visibility map bị reset, index maintenance |
| Cột INCLUDE thay đổi thường xuyên | Tránh heap khi đọc một số query | HOT giảm, WAL/bloat tăng |
| Cột payload rất dài | Ít chắc chắn có lợi | Index tuple lớn hoặc không thể lưu |

Vì vậy, **INCLUDE thường phù hợp hơn với cột đầu ra hẹp, đọc thường xuyên và cập nhật ít**, không phải một cách mặc định đưa mọi cột SELECT vào index.

## 12. So sánh ba thiết kế index

Xét một truy vấn:

```sql
SELECT ordered_at, total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC
LIMIT 20;
```

Ba lựa chọn:

**A. Index chỉ trên customer_id:**

```sql
CREATE INDEX idx_choice_a
ON index_include_lab.orders (customer_id);
```

Có thể lọc khách tốt, nhưng `ordered_at` và `total_amount` không có trong index. Query có thể phải đọc heap và sort.

**B. Composite key đầy đủ:**

```sql
CREATE INDEX idx_choice_b
ON index_include_lab.orders
    (customer_id, ordered_at DESC, total_amount);
```

Các cột đều là key, nên `total_amount` tham gia cấu trúc B-tree dù query không tìm hay sắp xếp theo tổng tiền.

**C. Composite key + INCLUDE:**

```sql
CREATE INDEX idx_choice_c
ON index_include_lab.orders
    (customer_id, ordered_at DESC)
INCLUDE (total_amount);
```

`total_amount` được lưu như payload, đáp ứng nhu cầu lấy kết quả mà không phải key search.

### 12.1. Bảng so sánh ý nghĩa

| Thiết kế | Lọc customer_id | Thứ tự ordered_at | Giá trị total_amount có trong index | total_amount là key |
| --- | --- | --- | --- | --- |
| A | Có | Không theo key thứ hai | Không | Không |
| B | Có | Có | Có | Có |
| C | Có | Có | Có | **Không** |

**Lưu ý vận hành:** ba ví dụ CREATE INDEX trên được dùng để so sánh thiết kế. Không nên giữ cả ba trên cùng bảng production nếu chúng trùng chức năng mà không có lợi ích bổ sung; mỗi index tăng dung lượng và chi phí ghi.

### 12.2. Key rộng ảnh hưởng cấu trúc B-tree

Payload INCLUDE không phải phần key dùng để phân chia thứ tự B-tree. PostgreSQL có thể lược bớt những cột không cần ở các cấp trên của B-tree theo cơ chế phù hợp, giúp một số cấu trúc cấp trên gọn hơn so với biến mọi cột thành key.

Nhưng **leaf entries vẫn phải lưu payload INCLUDE**, nên tổng kích thước index vẫn tăng. Đó là lý do không thể suy luận index với INCLUDE “gần như miễn phí”.

## 13. UNIQUE INDEX ... INCLUDE: uniqueness chỉ áp dụng cho key

Đây là một điểm rất dễ nhầm:

```sql
CREATE UNIQUE INDEX idx_unique_demo
ON some_table (tenant_id, external_order_id)
INCLUDE (total_amount);
```

Index trên có ý nghĩa:

> Trong cùng `tenant_id`, mỗi `external_order_id` chỉ được xuất hiện một lần theo quy tắc unique.

Nó **không** bắt các `total_amount` phải khác nhau.

### 13.1. Ví dụ có thể chạy

```sql
CREATE TABLE index_include_lab.external_orders (
    tenant_id INTEGER NOT NULL,
    external_order_id TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    source TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_lab_external_orders_unique_cover
ON index_include_lab.external_orders
    (tenant_id, external_order_id)
INCLUDE (total_amount);

INSERT INTO index_include_lab.external_orders
    (tenant_id, external_order_id, total_amount, source)
VALUES
    (1, 'A-001', 100000, 'web'),
    (1, 'A-002', 100000, 'app'),
    (2, 'A-001', 100000, 'web');
```

Ba dòng trên hợp lệ:

- Tenant 1 có hai order IDs khác nhau cùng total_amount.
- Tenant 2 có thể dùng `A-001` vì tenant_id khác.

Nhưng câu sau **sẽ vi phạm unique key**, bất kể included amount có khác:

```sql
-- Chỉ minh họa lỗi, không cần thực thi:
-- INSERT INTO index_include_lab.external_orders
--     (tenant_id, external_order_id, total_amount, source)
-- VALUES (1, 'A-001', 999999, 'other');
```

### 13.2. Vì sao INCLUDE trong unique index hữu ích?

Ứng dụng thường tìm order theo `(tenant_id, external_order_id)` rồi cần ngay `total_amount`:

```sql
SELECT total_amount
FROM index_include_lab.external_orders
WHERE tenant_id = 1
  AND external_order_id = 'A-001';
```

Unique key giúp tìm đúng một dòng, còn included total_amount có thể giúp đọc trực tiếp qua index nếu visibility cho phép.

Nhưng nếu bạn cần trả cả `source` mà index không chứa, query không còn được index này cover.

### 13.3. INCLUDE không mở rộng unique constraint

Đây là hai ý nghĩa khác nhau:

```sql
UNIQUE (tenant_id, external_order_id)
INCLUDE (total_amount)
```

và:

```sql
UNIQUE (tenant_id, external_order_id, total_amount)
```

Ở dạng đầu, total_amount chỉ là payload. Ở dạng sau, nó thuộc bộ key dùng xét uniqueness. Không dùng INCLUDE nếu business rule thực sự yêu cầu **tổ hợp ba cột** là duy nhất.

## 14. Partial covering index: chỉ lưu một phần bảng

Giả sử dashboard chỉ hiển thị **đơn đã thanh toán**. Một partial index có thể giới hạn số entry:

```sql
CREATE INDEX idx_lab_paid_orders_cover
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (total_amount)
WHERE status = 'PAID';
```

Với query:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

planner có thể tận dụng:

- **Predicate** `status = 'PAID'` xác định chỉ những hàng PAID được lưu trong partial index.
- **Keys** xác định khách và thứ tự.
- **INCLUDE total_amount** trả giá trị tiền.

Vì `status` ở đây là điều kiện định nghĩa partial index chứ không được query lấy ra làm cột đầu ra, index có thể cover các giá trị cần trả mà không cần lưu status dưới dạng INCLUDE trong ví dụ.

### 14.1. Partial index chỉ được dùng khi planner chứng minh được predicate

Truy vấn:

```sql
WHERE customer_id = 42
  AND status = 'PAID'
```

có điều kiện khớp rõ predicate.

Nhưng nếu query là:

```sql
WHERE customer_id = 42
  AND status = $1
```

trong một prepared statement/generic plan, PostgreSQL **không nhất thiết có thể chứng minh** tham số `$1` luôn bằng `'PAID'`, nên không thể giả định partial index chắc chắn được chọn. Việc dùng index phụ thuộc cách lập plan và các điều kiện được biết tại planning time.

Đó là lý do cần benchmark đúng hình thức truy vấn ứng dụng gửi, kể cả parameter binding.

### 14.2. Không phải mọi status đều cần một partial index

Tạo một index riêng cho PAID, PENDING và CANCELLED có thể tăng chi phí ghi/bảo trì nhiều lần. Chỉ nên tạo khi workload thực sự cần và độ chọn lọc/predicate phù hợp.

## 15. INCLUDE với điều kiện lọc trên payload

Xét index chính:

```sql
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount)
```

Và query:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

`status` có trong payload nên có thể được dùng để **lọc kết quả trong quá trình Index Only Scan**, nhưng không nằm trong cấu trúc key B-tree để giảm trực tiếp phạm vi duyệt theo status.

Nếu phần lớn đơn của khách không PAID, executor có thể phải xét nhiều index entries để tìm đủ 20 đơn PAID. Khi đó, các thiết kế khác cần cân nhắc:

**Phương án A – đưa status vào key:**

```sql
CREATE INDEX idx_lab_customer_status_time
ON index_include_lab.orders
    (customer_id, status, ordered_at DESC, order_id DESC)
INCLUDE (total_amount);
```

Phù hợp nếu query thường xuyên lọc `customer_id = ? AND status = ?` rồi ORDER BY thời gian.

**Phương án B – partial index cho PAID:**

```sql
CREATE INDEX idx_lab_paid_customer_time
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (total_amount)
WHERE status = 'PAID';
```

Phù hợp nếu workload chủ yếu truy cập trạng thái PAID và predicate được planner nhận ra.

**Phương án C – giữ status là INCLUDE:**

Phù hợp khi cần lấy status ra hiển thị nhưng phần lớn query **không lọc theo status**, hoặc điều kiện status không đủ chọn lọc để đáng đổi thứ tự key/index.

### 15.1. Không có thứ tự key đúng cho mọi query

Một index trên:

```sql
(customer_id, status, ordered_at)
```

không nhất thiết đáp ứng `ORDER BY ordered_at` cho **mọi status của một khách** mà không cần xử lý bổ sung, vì dữ liệu trong index được nhóm theo status trước ordered_at.

Ngược lại, index:

```sql
(customer_id, ordered_at)
INCLUDE (status)
```

thuận lợi cho tất cả đơn của khách theo thời gian, nhưng không thu hẹp tìm kiếm trực tiếp theo status.

Thiết kế phải xuất phát từ **truy vấn quan trọng và phân bố dữ liệu thật**, không chỉ danh sách cột xuất hiện trong SQL.

## 16. Index Only Scan không phải Bitmap Heap Scan

PostgreSQL có nhiều cách truy xuất index:

| Plan node | Đường đọc chính | Khi nào có thể hợp lý? |
| --- | --- | --- |
| `Seq Scan` | Quét heap theo thứ tự vật lý | Nhiều hàng phù hợp, bảng nhỏ, index không có lợi |
| `Index Scan` | Duyệt index, đọc heap cho hàng cần | Lọc chọn lọc, `ORDER BY/LIMIT` |
| `Bitmap Index Scan + Bitmap Heap Scan` | Gom vị trí từ index thành bitmap, đọc heap theo block | Cần nhiều hàng, kết hợp nhiều điều kiện/index |
| `Index Only Scan` | Duyệt index, có thể bỏ heap khi VM cho phép | Giá trị cần đọc đều có trong index; nhiều page all-visible |

`Bitmap Heap Scan` có chữ “Heap” vì nó đọc heap theo bitmap các block/hàng phù hợp. Nó không trở thành Index Only Scan chỉ vì index có INCLUDE.

Một query có covering index vẫn có thể chọn `Bitmap Heap Scan` nếu planner đánh giá chi phí có lợi, hoặc có điều kiện truy cập khác.

### 16.1. Bitmap có thể kết hợp index

PostgreSQL có thể sử dụng `BitmapAnd` hoặc `BitmapOr` để kết hợp điều kiện từ nhiều index. Đây là một kỹ thuật **khác** với việc lưu payload để đọc index-only.

Nếu query cần số lượng lớn hàng và nhiều điều kiện độc lập, một thiết kế dựa vào bitmap scans có thể hợp lý hơn cố tạo một covering index rất rộng.

### 16.2. Không xem Index Only Scan luôn nhanh nhất

Một index-only plan có thể chậm hơn index scan trong một số trường hợp vì:

- Index có INCLUDE quá rộng nên duyệt nhiều page.
- Visibility map chưa all-visible, phải fetch heap nhiều.
- Planner ước lượng số hàng khác thực tế.
- Cache và hệ lưu trữ làm chi phí khác kỳ vọng.
- Query cần scan rất nhiều index entries để lọc payload.

Điều cần tối ưu là **latency, throughput và tài nguyên tổng thể của workload**, không phải cố làm EXPLAIN xuất hiện một tên node nhất định.

## 17. Đọc kỹ EXPLAIN (ANALYZE, BUFFERS)

Một output minh họa:

```text
Limit  (actual time=... rows=20 loops=1)
  Buffers: shared hit=...
  ->  Index Only Scan using idx_lab_orders_customer_recent_cover
        on orders
        Index Cond: (customer_id = 42)
        Heap Fetches: 0
        Buffers: shared hit=...
Planning Time: ...
Execution Time: ...
```

Đọc lần lượt:

### 17.1. actual rows và loops

- `rows=20` ở Limit cho biết truy vấn thực trả 20 hàng.
- `loops=1` là số lần node được chạy trong plan minh họa.
- Nếu node bên trong nested loop chạy nhiều lần, tổng chi phí có thể cao dù mỗi lần trả ít hàng.

### 17.2. Index Cond

`Index Cond` cho biết điều kiện được index scan sử dụng. Không nên suy luận một điều kiện trên included column là search key chỉ vì cột đó có trong index.

### 17.3. Heap Fetches

Chỉ số này cho biết số lượt fetch heap mà Index Only Scan vẫn phải thực hiện để kiểm tra visibility. **0** là lý tưởng cho workload đọc; **khác 0** cần xét MVCC/VM và tần suất cập nhật.

### 17.4. Buffers

`Buffers: shared hit` cho biết truy cập các block đã có trong shared buffers; `shared read` cho biết cần đọc block từ lớp lưu trữ vào shared buffers theo nghĩa thống kê PostgreSQL.

Không đồng nhất mỗi `shared read` với đúng một lần đọc đĩa vật lý chậm, vì hệ điều hành còn có page cache. Tuy nhiên các chỉ số này vẫn hữu ích để so sánh xu hướng I/O giữa các kế hoạch.

### 17.5. Planning Time và Execution Time

Một index phức tạp có thể làm thay đổi cả thời gian lập kế hoạch và thời gian thực thi. Trong benchmark, cần đo nhiều lần, thử cache nóng/lạnh, và so các phân bố tham số.

Đừng kết luận chỉ dựa vào một lượt chạy trên bảng 80.000 hàng với dữ liệu tổng hợp.

## 18. Có thể ép planner để quan sát Index Only Scan không?

Trong môi trường **lab**, bạn có thể tạm hạn chế một số chiến lược scan để quan sát khả năng của index. Ví dụ:

```sql
BEGIN;

SET LOCAL enable_seqscan = off;
SET LOCAL enable_bitmapscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;

ROLLBACK;
```

Mục đích **chỉ là thí nghiệm**: xem các phương án khác khi planner bị hạn chế. Không dùng `enable_seqscan=off` lâu dài như một “bản sửa hiệu năng”.

**Hai lưu ý:**

1. Ngay cả khi tắt seq/bitmap scan, PostgreSQL vẫn chọn dựa trên những con đường hợp lệ và chi phí; `enable_*` không biến một index không cover thành index cover.
2. Một plan bị ép có thể chậm hơn kế hoạch mặc định. Hãy khôi phục cấu hình sau phép đo và dùng số liệu thật để quyết định thiết kế index.

## 19. Kiểm tra kích thước index

Một index có INCLUDE thường lớn hơn index chỉ chứa key khi số hàng và độ rộng payload giống nhau.

### 19.1. Xem tổng kích thước bảng và index

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('index_include_lab.orders')
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('index_include_lab.orders')
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('index_include_lab.orders')
    ) AS total_size;
```

`pg_relation_size` với tên bảng như trên thường phản ánh fork chính của heap; `pg_indexes_size` là tổng kích thước index của bảng; `pg_total_relation_size` bao gồm bảng và các cấu trúc liên quan như index/TOAST.

### 19.2. Xem từng index

```sql
SELECT
    indexname,
    pg_size_pretty(
        pg_relation_size(
            (format('%I.%I', schemaname, indexname))::regclass
        )
    ) AS index_size
FROM pg_indexes
WHERE schemaname = 'index_include_lab'
  AND tablename = 'orders'
ORDER BY indexname;
```

Khi thử nhiều index của lab, ghi lại số byte và số row/độ rộng để thấy INCLUDE ảnh hưởng tới storage.

### 19.3. So sánh trước/sau không nên giữ nhiều index trùng lâu dài

Để benchmark:

1. Đo query khi chỉ có index key cơ bản.
2. Tạo hoặc thay bằng index có INCLUDE.
3. Chạy VACUUM/ANALYZE, đo nhiều lần với workload tương tự.
4. Ghi kết quả thời gian, buffers, heap fetches và index size.
5. Tính chi phí ghi/UPDATE và disk space tăng thêm.
6. Chỉ giữ index có lợi ích thực tế.

Không mặc định “thêm INCLUDE” là miễn phí vì một query SELECT đã tăng tốc.

## 20. Payload INCLUDE quá rộng: nguy cơ lỗi kích thước index tuple

Index B-tree có giới hạn kích thước entry theo kích thước page và cách lưu trữ. Nếu INCLUDE một cột TEXT/JSONB rất lớn:

```sql
-- KHÔNG nên áp dụng máy móc nếu customer_note có thể rất dài.
-- CREATE INDEX idx_bad_cover
-- ON index_include_lab.orders (customer_id, ordered_at)
-- INCLUDE (customer_note);
```

thì có thể xảy ra:

- Index phình to đáng kể.
- Nhiều page được đọc hơn cho cùng số hàng.
- INSERT/UPDATE tốn thêm WAL, I/O và CPU.
- Tạo index hoặc ghi hàng mới **thất bại vì một index tuple quá lớn**.

**TOAST không làm INCLUDE text lớn trở thành miễn phí.** Các index entries vẫn phải tuân thủ giới hạn của access method. Một giá trị rất dài không nên được lưu payload chỉ để tránh một heap fetch hiếm hoi.

### 20.1. Cách chọn payload

Những cột thường đáng cân nhắc:

- Mã trạng thái ngắn.
- Số tiền `NUMERIC` vừa phải.
- Khóa ngoại ID.
- Timestamps hoặc flags được trả thường xuyên.

Những cột thường cần cân nhắc kỹ:

- Text mô tả dài.
- JSON payload lớn.
- Binary/blob lớn.
- Cột thay đổi rất thường xuyên.
- Cột chỉ xuất hiện trong một báo cáo hiếm khi chạy.

## 21. B-tree deduplication và INCLUDE

PostgreSQL B-tree có tối ưu **deduplication** trong những trường hợp có nhiều giá trị key trùng nhau: các tuple cùng key có thể được tổ chức thành posting list để giảm kích thước index.

Với **B-tree index có INCLUDE non-key columns**, PostgreSQL **không áp dụng B-tree deduplication** cho index đó. Đây là một đánh đổi ít được chú ý.

Ví dụ:

```sql
CREATE INDEX idx_status_only
ON index_include_lab.orders (status);
```

và:

```sql
CREATE INDEX idx_status_with_payload
ON index_include_lab.orders (status)
INCLUDE (total_amount);
```

Khi có rất nhiều hàng cùng status, index đầu có thể hưởng lợi từ các tối ưu dành cho key trùng (nếu điều kiện/phiên bản cho phép); index có INCLUDE không được dùng B-tree deduplication theo cách đó.

Đừng suy luận index với INCLUDE sẽ luôn lớn hơn chính xác một tỷ lệ cố định, nhưng **khả năng nén dedup mất đi** là một lý do để kiểm tra kỹ nếu key có độ phân biệt thấp.

## 22. INCLUDE và HOT UPDATE

HOT update là một tối ưu quan trọng của PostgreSQL khi UPDATE một hàng mà **không cần thay đổi index entry** theo các điều kiện áp dụng và còn chỗ thích hợp trên heap page.

### 22.1. Trước khi INCLUDE một cột cập nhật thường xuyên

Giả sử `status` thay đổi thường xuyên:

```sql
UPDATE index_include_lab.orders
SET status = 'PAID'
WHERE order_id = 100
  AND status = 'PENDING';
```

Nếu `status` có trong một index với vai trò **key hoặc INCLUDE**, thay đổi giá trị nó có thể làm UPDATE **không đủ điều kiện HOT**. PostgreSQL phải cập nhật index để lưu giá trị payload mới.

Tác động có thể gồm:

- Tăng số entry/index pages được viết.
- Tăng WAL.
- Giảm tỷ lệ HOT updates.
- Tăng dead tuples và công việc VACUUM.
- Tăng contention trên page/index dưới tải ghi cao.

### 22.2. Đo HOT updates

Có thể quan sát thống kê:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'index_include_lab'
  AND relname = 'orders';
```

Đây là các bộ đếm/thống kê tích lũy và có độ trễ cập nhật; không dùng chúng như bằng chứng tuyệt đối cho đúng một statement vừa chạy mà không xét lần reset stats và workload đồng thời.

### 22.3. HOT và Index Only Scan có thể kéo theo đánh đổi

Một index rộng giúp một số SELECT đọc ít heap hơn, nhưng việc đặt cột update thường xuyên vào INCLUDE có thể làm UPDATE đắt hơn. Ngoài ra, UPDATE làm mất bit all-visible ở các heap pages liên quan, khiến index-only queries sau đó phải heap fetch thêm.

**Cần đo cả đọc lẫn ghi**, không chỉ SELECT đang được tối ưu.

## 23. INCLUDE trong nhiều index làm tăng chi phí ghi

Giả sử một bảng có:

```text
PRIMARY KEY(order_id)
INDEX(customer_id, ordered_at) INCLUDE(status, total_amount)
INDEX(status, ordered_at) INCLUDE(total_amount)
INDEX(region_code, ordered_at) INCLUDE(total_amount)
```

Một lần UPDATE `total_amount` có thể phải duy trì **nhiều index** chứa nó. Nếu bảng có tốc độ ghi cao, tổng chi phí rất đáng kể.

Vì vậy trước khi thêm một covering index mới:

1. Liệt kê các index hiện có.
2. Xác định query nào thực sự chậm và tần suất của nó.
3. Xác định index hiện tại đã gần cover chưa.
4. Chỉ thêm payload cần thiết, không đưa toàn bộ SELECT list một cách vô điều kiện.
5. Đo index size, UPDATE latency, WAL và autovacuum.
6. Xem có thể thay thế một index cũ bằng thiết kế mới không.

### 23.1. Kiểm tra index hiện có

```sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'index_include_lab'
  AND tablename = 'orders'
ORDER BY indexname;
```

Trong production, không xóa index chỉ vì thấy tên trùng: nó có thể phục vụ unique/constraint, FK workload, ORDER BY khác, hoặc một query ít xuất hiện trong log.

## 24. INCLUDE không phải phép thay thế cho projection đúng

Ngay cả khi có covering index, ứng dụng vẫn nên chỉ lấy những cột cần thiết:

```sql
-- Tốt hơn cho danh sách đơn:
SELECT order_id, ordered_at, status, total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

thay vì:

```sql
-- Có thể buộc lấy thêm dữ liệu rộng từ heap:
SELECT *
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

`SELECT *` lấy thêm `customer_note` và `region_code` không nằm trong index chính, nên index đó không còn cover toàn bộ output.

Không nên INCLUDE tất cả cột bảng chỉ để “chữa SELECT *”; việc đó có thể tạo index gần rộng bằng hoặc rộng hơn các phần dữ liệu chính, với chi phí bảo trì không hợp lý.

## 25. Tính chỉ mục theo tenant và phạm vi dữ liệu

Trong hệ thống multi-tenant, một query phải lọc đúng tenant:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM tenant_orders
WHERE tenant_id = 8
  AND customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Index phù hợp có thể là:

```sql
CREATE INDEX idx_tenant_orders_recent_cover
ON tenant_orders
    (tenant_id, customer_id, ordered_at DESC, order_id DESC)
INCLUDE (total_amount);
```

Đây là **DDL minh họa**, giả định bảng `tenant_orders` tồn tại.

### 25.1. Tại sao tenant_id là key?

Điều kiện `tenant_id = 8` xác định phạm vi dữ liệu được phép xét. Khi query luôn lọc tenant, đặt tenant_id là một trong các key đầu thường giúp hạn chế vùng index.

**Nhưng:** index không phải cơ chế phân quyền. Nếu ứng dụng bỏ điều kiện tenant hoặc role có SELECT rộng, việc có `tenant_id` ở index không tự ngăn rò rỉ dữ liệu. Cần authorization và Row-Level Security khi phù hợp.

### 25.2. Không dùng INCLUDE để che lỗi thiết kế khóa

Nếu query phải tìm theo:

```sql
WHERE tenant_id = ?
  AND customer_id = ?
```

nhưng index chỉ:

```sql
ON tenant_orders (customer_id)
INCLUDE (tenant_id, total_amount)
```

thì tenant_id chỉ là payload, không giúp index tìm trực tiếp theo tenant. Trong hệ thống nhiều tenant có customer_id trùng nhau, đây có thể là thiết kế kém hơn index ghép theo cả hai key.

## 26. INCLUDE và phân trang ổn định

Một danh sách đơn mới nhất thường dùng:

```sql
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20
```

Việc đưa `order_id` vào key không chỉ giúp planner dùng thứ tự index, mà còn làm **thứ tự kết quả rõ ràng khi các đơn cùng timestamp**.

### 26.1. OFFSET có thể tốn chi phí

```sql
SELECT order_id, ordered_at, total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
OFFSET 10000
LIMIT 20;
```

Dù có covering index, PostgreSQL vẫn phải đi qua các mục phù hợp bị bỏ qua trước khi đến trang sâu. INCLUDE không loại bỏ chi phí của offset lớn.

### 26.2. Keyset pagination

Khi có “last seen” với cả timestamp và ID:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND (ordered_at, order_id)
        < (TIMESTAMPTZ '2026-02-20 10:00:00+00', 78000)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Đây là ví dụ seek tới các hàng đứng sau mốc đã thấy theo thứ tự giảm dần (với các giá trị khóa không NULL và cặp thứ tự phù hợp). Index key gồm `customer_id, ordered_at DESC, order_id DESC` có thể giúp truy vấn đi tiếp hiệu quả hơn offset sâu.

**INCLUDE vẫn chỉ phục vụ payload**: `total_amount` có thể lấy từ index, còn hai cột phân trang cần là key để hỗ trợ thứ tự/điều kiện.

### 26.3. Phân trang không tự tạo snapshot cố định

Nếu đơn mới được chèn giữa hai lượt fetch, trang tiếp theo có thể thay đổi theo dữ liệu đã commit. Keyset pagination giúp thứ tự ổn định hơn đối với khóa sắp xếp, nhưng không tự bảo đảm một snapshot bất biến qua nhiều request.

Nếu nghiệp vụ yêu cầu chốt một báo cáo chính xác ở một mốc thời gian, cần định nghĩa snapshot/transaction và lịch sử dữ liệu riêng.

## 27. Index-only scan trên dữ liệu mới và dữ liệu lịch sử

Hãy phân biệt hai vùng:

```text
Đơn hàng lịch sử đã ổn định
    ít UPDATE, đã được VACUUM
    -> nhiều heap pages all-visible
    -> Index Only Scan có cơ hội Heap Fetches thấp

Đơn hàng vừa tạo/đang đổi trạng thái
    INSERT/UPDATE liên tục
    -> nhiều heap pages chưa all-visible
    -> Index Only Scan có thể vẫn fetch heap
```

### 27.1. Nếu dashboard luôn truy vấn 20 đơn mới nhất?

Những đơn mới nhất thường nằm ở phần dữ liệu vừa được INSERT/UPDATE. Vì vậy, ngay cả với covering index đầy đủ, `Heap Fetches` có thể đáng kể.

Điều này không có nghĩa index vô ích:

- Key vẫn giúp tìm và trả 20 đơn mới nhất nhanh.
- INCLUDE vẫn cung cấp các cột output từ index.
- Nhưng **heap visibility check** có thể vẫn cần.

Lợi ích của INCLUDE phụ thuộc vào chi phí heap fetch thực sự có tránh được và độ rộng payload.

### 27.2. Nếu báo cáo quét dữ liệu tháng trước?

Một bảng lịch sử ít cập nhật, đã trải qua VACUUM, có thể có nhiều page all-visible và hưởng lợi rõ rệt hơn từ Index Only Scan khi query chọn đúng cột được cover.

Vì thế nên benchmark **cả truy vấn dữ liệu mới lẫn dữ liệu cũ**, không chỉ một customer_id.

## 28. Index-only không có nghĩa không đọc dữ liệu từ đĩa

Một hiểu nhầm:

> “Index Only Scan nghĩa là không đọc đĩa, vì chỉ đọc index.”

Sai. Index cũng được lưu trên đĩa và trong cache như các quan hệ khác. `Index Only Scan` có thể đọc **index pages** từ storage, và visibility map pages cũng phải có mặt khi cần.

Điểm tối ưu là **tránh hoặc giảm heap tuple fetch** đối với những giá trị đã nằm trong index.

Nếu index quá rộng hoặc không nằm trong cache, nó có thể gây nhiều I/O. Vì vậy:

- Đo `BUFFERS shared hit/read`.
- Xem kích thước index.
- Xem `Heap Fetches`.
- Xem actual rows/loops.
- So latency dưới tải đồng thời.

Đừng coi `Heap Fetches = 0` là toàn bộ câu chuyện hiệu năng.

## 29. Index-only và MVCC isolation

PostgreSQL phải trả các hàng **đúng với snapshot** của statement/transaction. Visibility map là một tối ưu để không cần đọc heap trong tình huống an toàn; nó không bỏ qua nguyên tắc MVCC.

### 29.1. READ COMMITTED

Mỗi statement thường lấy snapshot phù hợp với trạng thái commit tại thời điểm bắt đầu statement. Nếu một page chưa all-visible, Index Only Scan có thể cần đọc heap để kiểm tra tuple hợp lệ với snapshot đó.

### 29.2. REPEATABLE READ

Một transaction có snapshot ổn định qua nhiều statement, nhưng điều đó không tự biến tất cả heap pages thành all-visible. Các phiên bản chưa phù hợp với mọi snapshot không thể bị bỏ qua một cách tùy tiện.

### 29.3. Transaction dài và VACUUM

Transaction/snapshot cũ tồn tại lâu có thể khiến VACUUM không thể dọn một số phiên bản và đánh dấu all-visible ở những page thích hợp. Điều đó làm lợi ích Index Only Scan kém hơn.

Đừng “tối ưu index-only” bằng cách tắt hoặc bỏ qua kiểm tra MVCC: PostgreSQL phải giữ đúng dữ liệu trước khi nhanh.

## 30. Access methods khác nhau không có cùng khả năng index-only

B-tree là access method thông dụng nhất cho ví dụ `INCLUDE + Index Only Scan` vì nó lưu key và có khả năng trả giá trị cột từ index.

Không nên tổng quát hóa:

> “Bất kỳ index nào trong PostgreSQL cũng dùng Index Only Scan nếu SELECT có đúng cột.”

Một access method phải hỗ trợ khả năng trả dữ liệu có nghĩa từ index:

- **B-tree:** hỗ trợ index-only scans cho các kiểu/cột phù hợp.
- **GiST / SP-GiST:** khả năng index-only phụ thuộc support của access method và operator class, vì một số biểu diễn index là dạng mất thông tin (*lossy*) hoặc không thể tái tạo giá trị gốc.
- **GIN:** nhìn chung không hỗ trợ index-only scans kiểu B-tree vì index entry lưu các phần tử/key tách ra từ dữ liệu thay vì lưu toàn bộ giá trị gốc có thể trả lại.
- **BRIN:** index tóm tắt block ranges, không thay thế việc lấy tuple đầy đủ từ heap theo cách này.

Ngoài ra, mức hỗ trợ cú pháp `INCLUDE` không đồng nghĩa mọi method/operator class đều đem lại cùng lợi ích. Khi dùng index method khác B-tree, phải xác nhận **phiên bản PostgreSQL, operator class, giá trị được lưu và EXPLAIN thực tế**.

## 31. Index expression và INCLUDE

Một truy vấn thường gặp:

```sql
SELECT
    customer_id,
    lower(region_code) AS normalized_region
FROM index_include_lab.orders
WHERE lower(region_code) = 'n';
```

Nếu query thường tìm theo **biểu thức `lower(region_code)`**, một index expression có thể phù hợp:

```sql
CREATE INDEX idx_lab_region_lower
ON index_include_lab.orders
    ((lower(region_code)), customer_id);
```

Đây là index trên **giá trị tính toán**. PostgreSQL có một số giới hạn/khả năng nhận diện expression index cho Index Only Scan tùy cách query và planner kiểm tra cột cần lấy.

Một thiết kế có INCLUDE trên các cột cơ sở có thể phục vụ query khác:

```sql
CREATE INDEX idx_lab_region_lower_cover
ON index_include_lab.orders
    ((lower(region_code)), customer_id)
INCLUDE (region_code);
```

Nhưng không nên giả định hai chỉ mục trên luôn có hiệu năng bằng nhau hoặc luôn dẫn tới index-only. **Dùng EXPLAIN trên câu truy vấn thật** để xác nhận.

### 31.1. Biểu thức không nhất thiết được chấp nhận trong INCLUDE

`INCLUDE` dành cho **cột** làm payload, không phải nơi viết một biểu thức tùy ý giống phần key expression:

```sql
-- KHÔNG PHẢI cách đặt expression ở INCLUDE:
-- INCLUDE (lower(region_code))
```

Nếu cần một biểu thức làm search key, hãy định nghĩa expression index với cú pháp phù hợp.

## 32. Thiết kế covering index từ workload thực tế

Không bắt đầu bằng câu hỏi “bảng có những cột nào?”, mà bắt đầu từ **truy vấn nào cần tối ưu**.

Ví dụ có ba nhóm query:

**A. Danh sách 20 đơn mới nhất của khách:**

```sql
SELECT order_id, ordered_at, status, total_amount
FROM index_include_lab.orders
WHERE customer_id = $1
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

**B. Đếm đơn đã thanh toán theo khách:**

```sql
SELECT COUNT(*)
FROM index_include_lab.orders
WHERE customer_id = $1
  AND status = 'PAID';
```

**C. Báo cáo tổng tiền theo vùng:**

```sql
SELECT region_code, SUM(total_amount)
FROM index_include_lab.orders
WHERE ordered_at >= $1
  AND ordered_at < $2
GROUP BY region_code;
```

Một index key `(customer_id, ordered_at DESC, order_id DESC) INCLUDE(status, total_amount)` rất hợp ý tưởng A, nhưng không nhất thiết tối ưu cho B hoặc C:

- B lọc thêm status và tính COUNT; có thể hưởng lợi từ `(customer_id, status)` hoặc partial index theo tần suất.
- C quét theo khoảng thời gian và nhóm vùng; key customer_id ở đầu có thể không phục vụ tốt mục tiêu đó.

**Một index không cần phục vụ tối ưu mọi truy vấn**. Đôi khi hai index hẹp có tổng hiệu quả tốt hơn một index cực rộng, nhưng phải cân nhắc chi phí ghi và storage.

### 32.1. Phân tích workload

Ghi nhận:

1. Tần suất query.
2. P50/P95/P99 latency và mục tiêu SLO.
3. Số hàng trả và số hàng phải quét.
4. Điều kiện equality/range/joins.
5. ORDER BY và LIMIT.
6. Những cột thật sự cần trả.
7. Tỷ lệ all-visible của heap.
8. INSERT/UPDATE/DELETE rate.
9. Cột payload có được cập nhật thường xuyên không.
10. Index hiện tại và ngân sách storage/WAL.

Chỉ sau đó mới quyết định **key order và INCLUDE columns**.

## 33. Đo SELECT trước và sau khi tạo covering index

Một quy trình lab:

### Bước 1: Có bảng và dữ liệu

Tạo và nạp 80.000 hàng như mục 6, chạy `ANALYZE`.

### Bước 2: Tạo index chỉ có key

```sql
CREATE INDEX idx_lab_customer_recent_key_only
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC);
```

Chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at, status, total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Ghi node plan, buffers, thời gian.

### Bước 3: So với index có INCLUDE

```sql
CREATE INDEX idx_lab_customer_recent_with_payload
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

Vì lab có thể đang giữ một index cover từ mục 7, cần hiểu **planner có thể chọn bất kỳ index nào phù hợp** trong các index còn tồn tại. Muốn so sánh đáng tin, hãy thực hiện trong những trạng thái index được kiểm soát (ví dụ khôi phục test database hoặc chỉ giữ một thiết kế tại một thời điểm), không tự ép kết luận từ tên index vừa tạo.

### Bước 4: VACUUM rồi đo lại

```sql
VACUUM (ANALYZE) index_include_lab.orders;
```

Sau đó chạy lại câu SELECT và so:

- `Index Scan` hay `Index Only Scan`?
- Có bao nhiêu `Heap Fetches`?
- Bao nhiêu `shared hit/read`?
- Chi phí sort có thay đổi không?
- Tổng thời gian có giảm đáng kể không?

### Bước 5: Thử UPDATE và đo lại

```sql
UPDATE index_include_lab.orders
SET total_amount = total_amount + 1
WHERE customer_id = 42;
```

Đo lại plan và `Heap Fetches`. Đồng thời chú ý UPDATE vào included column có thể ảnh hưởng HOT và index maintenance.

### Bước 6: Ghi nhận tổng chi phí

Đọc index size và thống kê update. Lợi ích chỉ có ý nghĩa vận hành khi cải thiện query quan trọng **đủ bù chi phí storage và write**.

Không dùng `VACUUM FULL` hoặc thay tham số planner toàn hệ thống chỉ để chứng minh một ví dụ.

## 34. Ước lượng visibility map bằng catalog: đọc thận trọng

PostgreSQL duy trì các số liệu thống kê trong `pg_class` để hỗ trợ planner. Có thể quan sát ước lượng:

```sql
SELECT
    relname,
    relpages,
    relallvisible,
    CASE
        WHEN relpages > 0
        THEN ROUND(relallvisible::numeric / relpages * 100, 2)
        ELSE NULL
    END AS estimated_all_visible_pct
FROM pg_class
WHERE oid = 'index_include_lab.orders'::regclass;
```

Ý nghĩa:

- `relpages`: thống kê/ước lượng số page của quan hệ cho planner.
- `relallvisible`: thống kê/ước lượng số heap pages được đánh dấu all-visible.
- Tỷ lệ có thể cung cấp **gợi ý** về cơ hội index-only.

**Không xem các con số này là ảnh chụp trực tiếp tuyệt đối từng bit VM ở đúng thời điểm query**. Chúng có thể không được cập nhật tức thời sau mọi thay đổi và cần đọc theo bối cảnh thống kê.

Nếu cần chẩn đoán sâu, có các công cụ/extension phù hợp nhưng phải được quản trị viên chấp thuận; bài học không giả định những extension đó đã cài.

## 35. Index INCLUDE trong PRIMARY KEY và UNIQUE constraint

Một số phiên bản PostgreSQL hiện đại hỗ trợ included columns cho index phục vụ **PRIMARY KEY/UNIQUE constraint** theo cú pháp phù hợp:

```sql
CREATE TABLE index_include_lab.customer_preferences (
    customer_id INTEGER PRIMARY KEY,
    language_code TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Đây là bảng ví dụ bổ sung, chưa dùng INCLUDE trong primary key.

Một thiết kế constraint minh họa:

```sql
CREATE TABLE index_include_lab.api_keys (
    tenant_id INTEGER NOT NULL,
    key_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    last_used_at TIMESTAMPTZ,
    CONSTRAINT uq_api_key_name
        UNIQUE (tenant_id, key_name)
        INCLUDE (enabled, last_used_at)
);
```

Khóa duy nhất là `(tenant_id, key_name)`. Hai included columns **không tham gia uniqueness**, nhưng có thể phục vụ câu SELECT tra key rồi lấy trạng thái.

### 35.1. Khi nào không nên INCLUDE vào constraint index?

Nếu cột `last_used_at` được cập nhật sau **mọi request** của API, INCLUDE nó khiến unique index liên quan cần cập nhật thường xuyên. Điều đó có thể gây write amplification mạnh hơn nhiều so với lợi ích tránh một heap fetch khi tra key.

Đây là ví dụ chủ đích để thấy **cú pháp hợp lệ không đồng nghĩa thiết kế nên dùng**.

## 36. CREATE INDEX CONCURRENTLY và tác động triển khai

Trên bảng production đang có traffic, tạo B-tree index lớn theo cách thường có thể ảnh hưởng các tác vụ ghi. PostgreSQL hỗ trợ:

```sql
CREATE INDEX CONCURRENTLY idx_orders_recent_online
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

Mục đích của `CONCURRENTLY` là giảm việc chặn INSERT/UPDATE/DELETE trong lúc xây index so với cách xây index thường. Tuy nhiên:

- Thao tác có thể kéo dài và dùng nhiều I/O/CPU/WAL.
- Nó vẫn có giai đoạn chờ các transaction khác.
- Không được thực thi `CREATE INDEX CONCURRENTLY` trong transaction block tường minh.
- Nếu thất bại, có thể còn index ở trạng thái invalid, cần kiểm tra catalog và xử lý theo runbook.
- Không tạo nhiều index trùng chức năng trong cùng một đợt migration mà không có kế hoạch.

### 36.1. Tạo index xong chưa chắc planner dùng ngay

Sau khi tạo, có thể cập nhật thống kê bằng `ANALYZE` nếu cần và đo truy vấn thực tế. Chú ý query plan phụ thuộc cả tỷ lệ all-visible và số liệu dữ liệu, không chỉ việc index đã xuất hiện trong catalog.

### 36.2. Xóa index không còn cần

```sql
-- Ví dụ trên lab, chỉ chạy khi đã quyết định không cần index:
-- DROP INDEX CONCURRENTLY index_include_lab.idx_orders_recent_online;
```

`DROP INDEX CONCURRENTLY` cũng có hạn chế transaction và điều kiện áp dụng. Với production, phải kiểm tra index có hỗ trợ constraint hoặc workload khác không, và cần phối hợp rollout khi ứng dụng còn dùng nhiều plan.

## 37. Khi nào không nên dùng INCLUDE?

Một checklist quyết định:

**Không nên thêm INCLUDE chỉ vì:**

- Query có một cột trong SELECT, nhưng chạy rất hiếm.
- Bảng chỉ có vài trăm hàng và Seq Scan đã rất nhanh.
- Query đã có Index Scan hiệu quả, heap fetch ít và trong cache.
- Cột payload lớn đến mức index phình to hoặc có nguy cơ lỗi kích thước tuple.
- Cột thay đổi liên tục, làm giảm HOT và tăng write cost.
- Bảng đang cập nhật dày đặc khiến nhiều page chưa all-visible.
- Query còn cần các cột khác không có trong index, nên vẫn phải đọc heap.
- Điều kiện tìm kiếm đang thiếu key phù hợp: INCLUDE không thay key.
- `ORDER BY` trên included column nhưng kỳ vọng dùng thứ tự B-tree.
- Chỉ muốn làm cho EXPLAIN xuất hiện dòng “Index Only Scan” mà không có cải thiện latency.

### 37.1. Khi nào INCLUDE đáng thử?

INCLUDE thường đáng xem xét nếu:

1. Có một hoặc vài query **đọc nhiều lần, latency quan trọng**.
2. Đã có key index phù hợp với lọc/sort.
3. Query còn phải đọc heap **chủ yếu để lấy vài cột đầu ra nhỏ**.
4. Các cột cần thêm ít thay đổi.
5. Heap pages của phần dữ liệu được hỏi có tỷ lệ all-visible đáng kể.
6. Storage và chi phí ghi tăng thêm chấp nhận được.
7. Benchmark cho thấy thời gian/buffers/heap fetches cải thiện thực sự.

Đây là **giả thuyết tối ưu cần đo**, không phải quy tắc luôn đúng.

## 38. Bảng so sánh các đặc tính dễ nhầm

| Câu hỏi | Câu trả lời đúng |
| --- | --- |
| Index có INCLUDE có phải covering index cho mọi query không? | Không; chỉ cover khi có đủ dữ liệu query cần |
| Index chỉ có key có thể Index Only Scan không? | Có, nếu query chỉ cần dữ liệu index cung cấp và visibility phù hợp |
| Included column có dùng để sắp thứ tự B-tree không? | Không |
| Included column có tham gia unique key không? | Không |
| Filter trên included column có thể tránh heap không? | Có thể, khi plan/visibility cho phép |
| Filter trên included column có là B-tree search key không? | Không |
| Index Only Scan có luôn Heap Fetches = 0 không? | Không |
| Heap Fetches khác 0 nghĩa index không cover output? | Không nhất thiết; có thể do VM/MVCC |
| VACUUM có thể giúp heap fetch giảm không? | Có, khi giúp page đạt all-visible |
| VACUUM luôn bảo đảm tất cả page all-visible không? | Không |
| UPDATE cột INCLUDE có ảnh hưởng HOT không? | Có thể làm UPDATE không HOT do giá trị index thay đổi |
| INCLUDE cột lớn có miễn phí nhờ TOAST không? | Không |
| B-tree deduplication có áp dụng cho index có INCLUDE không? | Không, với B-tree non-key INCLUDE |
| Có INCLUDE thì planner bắt buộc chọn Index Only Scan không? | Không |
| INCLUDE có làm index hoàn toàn không cần heap trong mọi truy vấn không? | Không |
| Có cần theo dõi write overhead khi thêm INCLUDE không? | Có, đặc biệt với bảng ghi nhiều |

## 39. Một số lỗi thiết kế cụ thể

### 39.1. Đưa tất cả cột vào INCLUDE

```sql
-- Ý tưởng tệ nếu các cột rộng và cập nhật thường xuyên:
-- CREATE INDEX idx_everything
-- ON orders(customer_id)
-- INCLUDE(status, total_amount, region_code, customer_note, ...);
```

Hậu quả: index rộng, mất nhiều storage, có nguy cơ lỗi kích thước index tuple, tăng WAL và giảm HOT. Hãy tối ưu **đúng projection thực tế**.

### 39.2. Dùng INCLUDE thay key cho ORDER BY

```sql
ON orders(customer_id)
INCLUDE(ordered_at)
```

không có cùng khả năng hỗ trợ `ORDER BY ordered_at DESC` như index key:

```sql
ON orders(customer_id, ordered_at DESC)
```

### 39.3. Dùng INCLUDE thay key cho WHERE lọc mạnh

```sql
ON orders(customer_id)
INCLUDE(status)
```

không tự tạo khả năng tìm một dải key `status='PAID'` giống index:

```sql
ON orders(customer_id, status)
```

### 39.4. Coi HEAP FETCHES là số row của bảng

`Heap Fetches` trong plan Index Only Scan là thống kê các lần fetch heap cho node đó, **không phải số hàng tồn tại trong bảng, không phải COUNT(*)**, và cũng không tự nói bao nhiêu byte đã được đọc từ đĩa vật lý.

### 39.5. Dùng VACUUM FULL để “kích hoạt index-only”

`VACUUM FULL` viết lại bảng và có khóa mạnh, không phải lựa chọn mặc định để tăng tỷ lệ all-visible. Bắt đầu từ vận hành autovacuum, workload UPDATE và `VACUUM (ANALYZE)` phù hợp; chỉ xét VACUUM FULL cho mục tiêu bảo trì storage cụ thể.

## 40. Bài tập thực hành PostgreSQL

Các bài sau dựa trên schema `index_include_lab`. Với những bài đo hiệu năng, hãy dùng **database thử nghiệm** và chạy nhiều lần trước khi kết luận.

1. **Khái niệm:** giải thích khác nhau giữa index key, INCLUDE column và cột chỉ có trong heap.
2. **Covering index:** với truy vấn lấy `order_id, ordered_at, status, total_amount` theo `customer_id`, thiết kế B-tree key và INCLUDE hợp lý.
3. **ORDER BY:** tại sao `order_id` nên nằm trong key khi query sắp `ordered_at DESC, order_id DESC`?
4. **Payload:** nếu query không tìm/sort theo `total_amount`, vì sao INCLUDE có thể phù hợp hơn đưa nó vào cuối key?
5. **Không cover:** thêm `customer_note` vào SELECT; vì sao index chính không còn cover hoàn toàn?
6. **Index-only không cần INCLUDE:** viết `SELECT COUNT(*) WHERE customer_id=42` và giải thích vì sao index chỉ có key cũng có khả năng Index Only Scan.
7. **Index Cond:** tạo index chính, chạy EXPLAIN với `customer_id=42` và khoảng `ordered_at`; ghi điều kiện Index Cond khi xuất hiện.
8. **Filter:** thêm `status='PAID'` khi status chỉ là INCLUDE. Giải thích khác biệt giữa lọc payload và tìm kiếm B-tree theo key.
9. **Key status:** tạo index `(customer_id,status,ordered_at DESC) INCLUDE(total_amount)`; so hiệu quả cho query lọc status.
10. **Sort:** query `ORDER BY total_amount DESC` khi total_amount chỉ là INCLUDE. Vì sao có thể cần Sort?
11. **VACUUM:** so `EXPLAIN (ANALYZE, BUFFERS)` trước/sau `VACUUM (ANALYZE)` trên bảng lab. Heap Fetches thay đổi ra sao?
12. **Visibility map:** giải thích vai trò bit all-visible và vì sao Index Only Scan vẫn có thể đọc heap.
13. **MVCC:** tại sao index entry không thể tự chứng minh mọi tuple đều hiển thị với snapshot hiện tại?
14. **Dữ liệu vừa INSERT:** vì sao trang mới chưa chắc all-visible dù mọi cột output đã nằm trong index?
15. **UPDATE cột không index:** UPDATE customer_note của khách 42, rồi đo heap fetch; vì sao page có thể mất all-visible?
16. **UPDATE payload:** UPDATE total_amount, giải thích tác động đến HOT update và index maintenance.
17. **Theo dõi HOT:** dùng `pg_stat_user_tables` xem n_tup_upd và n_tup_hot_upd; vì sao đây là bộ đếm tích lũy?
18. **Kích thước:** dùng `pg_relation_size` và `pg_indexes_size` để ghi size trước/sau thêm payload INCLUDE.
19. **Unique key:** tạo unique index `(tenant_id,external_order_id) INCLUDE(total_amount)`. Trường nào quyết định uniqueness?
20. **Trùng amount:** thêm hai đơn khác external ID nhưng cùng amount. Vì sao không vi phạm unique index có INCLUDE?
21. **Partial index:** tạo index chỉ chứa status PAID, có keys customer_id/ordered_at và include total_amount. Viết query phù hợp.
22. **Prepared statement:** giải thích vì sao query `status=$1` có thể không chứng minh được predicate partial index trong generic plan.
23. **Index keys order:** so `(customer_id, status, ordered_at)` và `(customer_id, ordered_at) INCLUDE(status)` với query không lọc status.
24. **B-tree dedup:** vì sao index có INCLUDE không được dùng B-tree deduplication như index chỉ có key trong các trường hợp phù hợp?
25. **Cột lớn:** đề xuất cách đo và quyết định có nên INCLUDE customer_note hay không.
26. **Index tuple limit:** nếu một cột JSONB payload rất lớn, điều gì có thể xảy ra khi tạo index hoặc INSERT?
27. **Select star:** so `SELECT *` với SELECT projection hẹp và giải thích tác động tới covering index.
28. **Bitmap:** phân biệt Bitmap Heap Scan và Index Only Scan về đọc heap.
29. **Planner:** tại sao có covering index nhưng PostgreSQL vẫn có thể dùng Seq Scan trên bảng nhỏ?
30. **Buffers:** giải thích `shared hit` và `shared read` trong EXPLAIN, và vì sao chúng không đồng nghĩa trực tiếp số lần disk I/O vật lý.
31. **LIMIT:** thêm LIMIT 20 vào query lấy đơn mới nhất; vì sao index key phù hợp có thể giảm số hàng cần xét?
32. **Pagination:** so OFFSET sâu với keyset pagination theo `(ordered_at,order_id)`; INCLUDE giúp phần nào và không giúp phần nào?
33. **Multi-tenant:** viết index có `tenant_id, customer_id, ordered_at` làm keys; vì sao tenant_id không nên chỉ nằm ở INCLUDE nếu luôn lọc tenant?
34. **RLS:** giải thích vì sao index có tenant_id không thay thế authorization/RLS.
35. **Workload đọc:** nếu bảng lịch sử gần như không UPDATE và được VACUUM thường xuyên, INCLUDE có thể có lợi thế nào?
36. **Workload ghi:** nếu status thay đổi liên tục, vì sao INCLUDE status có thể làm UPDATE đắt hơn?
37. **Benchmark:** thiết kế phép đo trước/sau index với số liệu actual rows, Heap Fetches, Buffers, index size và UPDATE latency.
38. **EXPLAIN thực thi:** tại sao phải thận trọng với `EXPLAIN (ANALYZE, BUFFERS)` trên query thay đổi dữ liệu hoặc query rất nặng?
39. **CONCURRENTLY:** khi tạo index trên production, vì sao cần hiểu giới hạn của `CREATE INDEX CONCURRENTLY` và trạng thái index invalid khi lỗi?
40. **Không tối ưu mù:** một query đã chạy 2 ms, heap fetch ít nhưng INCLUDE làm index tăng 4 GB; những số liệu nào cần để quyết định giữ hay bỏ?
41. **Thiết kế 3 query:** phân tích ba query A/B/C ở mục 32 và đề xuất index riêng cho query quan trọng nhất, tránh tạo index trùng chức năng.
42. **Tiêu chuẩn hoàn tất:** lập checklist xác minh một thiết kế INCLUDE được chấp nhận: key đúng, cover đủ, heap fetch thấp khi phù hợp, storage và write overhead chấp nhận được, benchmark đáng tin.

## 41. Quy trình review một đề xuất INCLUDE

Khi đồng nghiệp đề xuất:

```sql
CREATE INDEX idx_fast
ON big_table (customer_id)
INCLUDE (col_a, col_b, col_c);
```

hãy hỏi:

1. **Truy vấn nào** sẽ dùng index này? Có SQL và bind parameters thực tế không?
2. **Key order** có phù hợp các điều kiện equality/range và `ORDER BY` không?
3. **Các payload** có thật sự cần để cover query đó không?
4. Nếu query lọc/sort theo payload, có cần chuyển cột đó thành key không?
5. Có `SELECT *` hoặc cột khác làm index không cover không?
6. Planner có thực sự chọn Index Only Scan không? Nếu không, vì sao?
7. `Heap Fetches` có thấp không, và workload có đủ all-visible pages không?
8. Các cột INCLUDE có cập nhật thường xuyên, gây mất HOT không?
9. Payload có text/JSONB lớn hoặc nguy cơ vượt giới hạn index tuple không?
10. Index tăng bao nhiêu dung lượng, WAL và chi phí ghi?
11. Có index khác trùng chức năng có thể thay thế/loại bỏ không?
12. Nếu là partial index, query có chứng minh predicate được không?
13. Nếu là unique index, mọi người có hiểu uniqueness chỉ xét key không?
14. Có benchmark nhiều lần trên dữ liệu và tần suất workload đại diện không?
15. Triển khai production có tính đến concurrent build, thời gian chạy, quyền và rollback plan không?

Chỉ nên kết luận “index mới đáng triển khai” sau khi lợi ích đọc đủ rõ so với chi phí tổng thể.

## 42. Tổng kết

`INCLUDE`, covering index và Index Only Scan liên quan nhau nhưng **không đồng nghĩa**:

```text
1. INDEX KEY
   (customer_id, ordered_at DESC, order_id DESC)
   -> Giúp tìm vùng B-tree và cung cấp thứ tự phù hợp

2. INCLUDE PAYLOAD
   (status, total_amount)
   -> Lưu thêm giá trị đầu ra
   -> Không tham gia thứ tự key hay UNIQUE key

3. COVERING INDEX
   -> Index có đủ dữ liệu mà truy vấn cần
   -> Khả năng cover phụ thuộc câu SQL cụ thể

4. INDEX ONLY SCAN
   -> Planner chọn kế hoạch lấy dữ liệu từ index
   -> Kiểm tra visibility map
   -> Heap pages all-visible: có thể bỏ heap fetch
   -> Pages chưa all-visible: vẫn phải đọc heap
```

Những nguyên tắc quan trọng:

- **Chọn key theo `WHERE` và `ORDER BY`; chọn INCLUDE theo những cột đầu ra nhỏ cần đọc thường xuyên.** Không dùng INCLUDE để thay search key hoặc sort key.
- **Một index cover truy vấn không có nghĩa executor luôn chọn Index Only Scan.** Planner lựa chọn theo thống kê, độ chọn lọc và chi phí.
- **Index Only Scan không bảo đảm Heap Fetches bằng 0.** MVCC vẫn phải được bảo vệ, và visibility map quyết định có cần đọc heap cho page liên quan hay không.
- **VACUUM và workload cập nhật ảnh hưởng mạnh đến hiệu quả.** Bảng ít thay đổi thường có cơ hội all-visible cao hơn; bảng ghi liên tục có thể vẫn heap-fetch đáng kể.
- **Cột INCLUDE không miễn phí.** Nó tăng index size, chi phí ghi, có thể làm giảm HOT updates, mất B-tree deduplication và gặp giới hạn tuple size khi payload quá lớn.
- **UNIQUE INDEX ... INCLUDE chỉ unique theo các key columns.** Payload được lưu để đọc, không mở rộng uniqueness.
- **Đo cả đọc lẫn ghi bằng EXPLAIN, Buffers, Heap Fetches, index size và số liệu workload** thay vì tối ưu chỉ để có một tên node đẹp trong plan.

Khi hiểu đúng **key để tìm kiếm, payload để bao phủ dữ liệu và visibility map để bảo đảm MVCC**, bạn có thể thiết kế covering index PostgreSQL thực sự hữu ích: giảm truy cập heap cho những truy vấn quan trọng, nhưng không đánh đổi quá mức dung lượng và thông lượng ghi của hệ thống.
