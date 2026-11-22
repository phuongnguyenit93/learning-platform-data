# Chỉ mục, khóa và kế hoạch thực thi ở mức cần đọc hiểu

## Mục tiêu của bài học

Khi một ứng dụng Spring đọc đơn hàng bằng JDBC, JPA hoặc Spring Data, câu truy vấn cuối cùng vẫn phải được hệ quản trị cơ sở dữ liệu thực thi. Một lệnh `findByCustomerId(...)` trông ngắn gọn trong Java có thể chạy rất nhanh hoặc rất chậm tùy cấu trúc bảng, chỉ mục, số lượng bản ghi, điều kiện lọc và kế hoạch thực thi.

Sau bài học này, bạn cần:

1. Phân biệt **chỉ mục (index)** với **khóa chính (primary key)**, **khóa ngoại (foreign key)** và ràng buộc **UNIQUE**.
2. Hiểu tại sao có chỉ mục đôi khi truy vấn nhanh hơn, và tại sao **có index không đồng nghĩa database sẽ dùng index**.
3. Nhìn vào truy vấn `WHERE`, `JOIN`, `ORDER BY`, `LIMIT` để nhận ra một chỉ mục có thể hữu ích.
4. Đọc các phần thiết yếu của kế hoạch `EXPLAIN`: cách quét dữ liệu, điều kiện áp dụng tại index, bộ lọc còn lại, phép nối, sắp xếp, ước tính và số đo thực tế.
5. Biết quy trình tối thiểu để điều tra một truy vấn chậm trong tầng data access của ứng dụng Spring, thay vì thêm index theo cảm tính.

Các câu lệnh thực hành dùng **PostgreSQL** để có cú pháp và cách đọc kế hoạch cụ thể. Nguyên tắc tổng quát tương tự ở nhiều hệ quản trị quan hệ, nhưng tên phép toán, định dạng `EXPLAIN` và chi tiết tối ưu hóa khác nhau giữa PostgreSQL, MySQL, SQL Server, Oracle và các hệ khác. Đây là mức kiến thức dành cho lập trình viên ứng dụng, không phải giáo trình quản trị/tuning database chuyên sâu.

## 1. Ba khái niệm phải tách riêng

Giả sử ứng dụng có bảng `customers` và `orders`. Một customer có nhiều order.

- **Khóa (key)/ràng buộc (constraint)** trả lời câu hỏi về **tính đúng đắn của dữ liệu**: dòng nào là duy nhất, và quan hệ tham chiếu có hợp lệ không?
- **Chỉ mục (index)** là **cấu trúc truy cập dữ liệu** giúp database tìm, lọc hoặc đọc theo một thứ tự nhất định hiệu quả hơn trong một số truy vấn.
- **Kế hoạch thực thi (execution plan)** là **chiến lược được database chọn cho một câu SQL cụ thể**: đọc bảng theo cách nào, nối các bảng bằng thuật toán nào, có phải sắp xếp không và xử lý bao nhiêu dòng.

Ví dụ: ràng buộc khóa ngoại đảm bảo `orders.customer_id` tham chiếu đến customer có thật; index trên `orders.customer_id` có thể giúp tìm đơn hàng theo customer nhanh hơn; còn execution plan cho biết database **có thực sự chọn** index ấy khi chạy truy vấn hay không.

Cần tránh lẫn hai nghĩa của “khóa”: **primary/foreign key** là khóa nhận dạng/tham chiếu của mô hình dữ liệu; **row lock/table lock** là khóa đồng thời khi các transaction truy cập dữ liệu. Phần lớn bài này nói về *key*, không phải cơ chế *locking*; phần 8 phân biệt ngắn gọn.

## 2. Khóa chính, khóa duy nhất và khóa ngoại

### 2.1. Primary key (PK): định danh một dòng

Một **primary key** xác định duy nhất từng dòng trong bảng. Giá trị của cột hoặc bộ cột PK phải **duy nhất và khác NULL**; một bảng có tối đa **một ràng buộc PRIMARY KEY** (khóa đó có thể gồm nhiều cột).

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);
```

Trong bảng này, `id` là PK. Hai customer không thể có cùng `id`, và `id` không thể NULL. PK có thể là khóa nghiệp vụ như mã quốc gia hoặc khóa thay thế (surrogate key) như ID số tự tăng/UUID. Chọn khóa ổn định, ít thay đổi; không mặc định lấy email hay số điện thoại làm PK vì những giá trị đó có thể thay đổi theo nghiệp vụ.

Với **PostgreSQL**, khai báo PK đồng thời tạo một **unique B-tree index** để thực thi tính duy nhất; tuy nhiên **PK là một ràng buộc mang ý nghĩa dữ liệu, không chỉ là index**. Nhiều hệ quản trị có cơ chế tạo chỉ mục hỗ trợ ràng buộc tương tự, nhưng chi tiết khác nhau.

### 2.2. UNIQUE: ngăn trùng theo quy tắc nghiệp vụ

`UNIQUE` ràng buộc tính duy nhất của một cột hoặc tổ hợp cột. Ví dụ `customers.email UNIQUE` ngăn hai dòng cùng email. Nó không biến email thành PK và không mặc định yêu cầu `NOT NULL`.

```sql
CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
```

Đây là ví dụ **khóa chính ghép**: `order_id` có thể trùng ở nhiều dòng, `line_no` cũng có thể trùng giữa các đơn, nhưng **cặp** `(order_id, line_no)` phải duy nhất. Có thể dùng `UNIQUE(order_id, product_id)` nếu quy tắc nghiệp vụ yêu cầu mỗi sản phẩm chỉ xuất hiện một lần trong một đơn; đây là một quyết định nghiệp vụ khác với PK.

**Lưu ý NULL:** trong PostgreSQL, `UNIQUE` mặc định cho phép nhiều dòng có NULL ở cột unique, vì NULL được coi là khác nhau trong kiểm tra duy nhất. PostgreSQL hỗ trợ `NULLS NOT DISTINCT` khi muốn coi NULL là trùng nhau. Không áp dụng máy móc quy tắc này cho mọi DBMS.

### 2.3. Foreign key (FK): bảo toàn quan hệ tham chiếu

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
);
```

`orders.customer_id` là **FK** trỏ đến `customers.id`. Nó ngăn đơn hàng chứa `customer_id` không tồn tại trong `customers`. `NOT NULL` ở đây còn ngăn đơn hàng không gắn customer. Nếu bỏ `NOT NULL`, SQL có thể cho phép FK NULL theo quy tắc tương ứng.

Khi xóa hoặc sửa PK của dòng được tham chiếu, database kiểm tra ràng buộc FK. Các chính sách như `ON DELETE RESTRICT`, `NO ACTION`, `CASCADE`, `SET NULL` phải phản ánh nghiệp vụ. Ví dụ `CASCADE` có thể phù hợp để xóa dòng chi tiết khi xóa đơn hàng, nhưng dễ gây xóa dữ liệu ngoài mong muốn nếu dùng với quan hệ “khách hàng — đơn hàng”.

**Điểm dễ nhầm:** ở PostgreSQL, khai báo FK **không tự tạo index trên cột phía tham chiếu** (`orders.customer_id`). Index phía customer được tham chiếu đã có do PK/unique; index bên orders có thể cần tạo riêng cho tra cứu theo customer và để hỗ trợ một số thao tác kiểm tra FK khi xóa/cập nhật customer. Không nhất thiết tạo chỉ mục đơn lẻ trên mọi FK: cần xét mẫu truy vấn, độ lớn bảng, chỉ mục ghép đã có và chi phí ghi.

| Cấu trúc | Mục đích chính | Có tự bảo đảm dòng duy nhất? | Có thể hỗ trợ tốc độ truy vấn? |
| --- | --- | --- | --- |
| `PRIMARY KEY` | Định danh duy nhất, không NULL | Có | Có, qua index hỗ trợ ở PostgreSQL |
| `UNIQUE` | Thực thi quy tắc không trùng | Có, theo quy tắc NULL của DBMS | Có, qua unique index hỗ trợ |
| `FOREIGN KEY` | Bảo đảm tham chiếu hợp lệ | Không | Phụ thuộc index trên cột tham chiếu, không tự được tạo ở PostgreSQL |
| `CREATE INDEX` thường | Hỗ trợ tìm kiếm, lọc, nối, sắp xếp | Không | Có thể, khi optimizer thấy có lợi |

**Tính toàn vẹn dữ liệu và hiệu năng là hai quyết định khác nhau.** Không bỏ FK để làm truy vấn “nhanh hơn” nếu tính toàn vẹn quan hệ vẫn là yêu cầu; cũng không thêm nhiều index chỉ vì cột đó đã có FK.

## 3. Chỉ mục hoạt động như thế nào?

Hình dung muốn tìm một tên trong cuốn danh bạ rất dày:

- Nếu duyệt từng trang từ đầu đến cuối, bạn đang làm gần giống **sequential scan**.
- Nếu mở phần tra cứu đã sắp xếp và đi nhanh đến nhóm tên cần tìm, bạn đang tận dụng ý tưởng của **B-tree index**.

Chỉ mục B-tree lưu các khóa theo thứ tự có tổ chức, cùng thông tin để định vị dòng dữ liệu. Với điều kiện như `id = 42`, `created_at >= ?` hoặc thứ tự phù hợp, database có thể dùng cây để thu hẹp vùng tìm kiếm thay vì đọc mọi dòng. Đây là hình dung cơ bản; triển khai thực tế liên quan trang dữ liệu, bộ đệm, tính hiển thị dòng và kỹ thuật truy cập vật lý.

**Không phải index nào cũng là B-tree.** PostgreSQL còn có Hash, GIN, GiST, BRIN… phục vụ những dạng toán tử/kiểu dữ liệu khác nhau; bài này chỉ cần hiểu B-tree vì nó phổ biến cho phép so sánh, tìm theo khoảng và sắp xếp. Đừng tự suy ra cú pháp hoặc tính năng của loại index khác nếu chưa đọc tài liệu của DBMS đang dùng.

### 3.1. Một truy vấn có thể hưởng lợi từ index

```sql
SELECT id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

Nếu có hàng triệu đơn hàng nhưng chỉ cần 20 đơn gần nhất của một customer, index sau là một ứng viên hợp lý:

```sql
CREATE INDEX orders_customer_created_at_idx
    ON orders (customer_id, created_at DESC);
```

Trong B-tree ghép `(customer_id, created_at DESC)`, các mục có cùng `customer_id` được nhóm theo thứ tự; database *có thể* đi đến nhóm customer cần tìm và đọc 20 kết quả theo thời gian, tránh quét/sắp xếp cả bảng. `LIMIT` đặc biệt có ích khi kết hợp đường truy cập phù hợp với `ORDER BY`.

**Tuy nhiên**, optimizer có thể chọn cách khác khi bảng còn rất nhỏ, truy vấn trả phần lớn dữ liệu, có thống kê khác hoặc chi phí ước tính nghiêng về quét tuần tự. **Tồn tại index không có nghĩa chắc chắn xuất hiện `Index Scan`.**

### 3.2. Thứ tự cột trong chỉ mục ghép rất quan trọng

So sánh:

```sql
CREATE INDEX idx_a ON orders (customer_id, created_at);
CREATE INDEX idx_b ON orders (created_at, customer_id);
```

Hai index này **không tương đương** cho truy vấn `WHERE customer_id = 42 AND created_at >= ...`. Với B-tree trong PostgreSQL, điều kiện bằng trên **cột đứng đầu** và điều kiện khoảng trên **cột kế tiếp** thường giúp giới hạn phần index phải quét hiệu quả. `idx_a` thường thích hợp hơn cho mẫu truy vấn vừa nêu.

Quy tắc thực hành:

- Bắt đầu từ các điều kiện lọc thực tế, đặc biệt cột equality trong `WHERE` hoặc `JOIN`; sau đó xét range, `ORDER BY` và số dòng cần trả.
- Với `(customer_id, created_at)`, truy vấn theo riêng `customer_id` có cơ hội tận dụng prefix của index; truy vấn chỉ theo `created_at` chưa chắc hiệu quả bằng index bắt đầu bằng `created_at`.
- B-tree PostgreSQL có thể dùng một số điều kiện trên cột không đứng đầu hoặc các chiến lược bổ sung, nhưng không nên hiểu quy tắc cột đầu theo nghĩa “tuyệt đối không bao giờ dùng”.
- `ORDER BY created_at DESC` cùng `WHERE customer_id = ?` phù hợp với index ghép bắt đầu bằng `customer_id` và có thứ tự thời gian thích hợp; cách quét tiến/lùi và quy tắc NULL còn phụ thuộc định nghĩa index.
- Một index ghép có thể thay nhu cầu một số index đơn, nhưng không mặc nhiên thay tất cả; phải xét query thực.

### 3.3. Selectivity, chi phí và các trường hợp index không giúp nhiều

**Selectivity** mô tả mức độ điều kiện phân biệt được bản ghi. `WHERE id = 42` trên cột duy nhất thường chỉ chọn một dòng; `WHERE status = 'NEW'` có thể chọn phần rất lớn bảng. Khi phải trả phần lớn số dòng, quét tuần tự có thể rẻ hơn tra index rồi đọc nhiều trang của bảng.

Một index cũng có **chi phí**:

- Tốn dung lượng đĩa và bộ nhớ đệm.
- Làm `INSERT`, `UPDATE` (đặc biệt cập nhật cột được index), `DELETE` có thêm công việc duy trì chỉ mục.
- Khi số lượng index tăng, thời gian ghi và chi phí vận hành có thể tăng.
- Có thể không hữu ích nếu query áp dụng hàm/ép kiểu lên cột theo cách index thông thường không hỗ trợ, ví dụ `WHERE DATE(created_at) = DATE '2025-01-15'`.

Truy vấn thời gian thường có thể viết theo **khoảng nửa mở** để tận dụng index B-tree thông thường:

```sql
-- Thay vì biến đổi created_at trên từng dòng:
SELECT id
FROM orders
WHERE created_at >= TIMESTAMPTZ '2025-01-15 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2025-01-16 00:00:00+00';
```

Ví dụ lọc theo ngày UTC, không mặc định là ngày theo múi giờ người dùng. Khi làm việc với thời gian, phải xác định timezone và ranh giới lịch đúng nghiệp vụ.

## 4. Execution plan: database thực sự dự định làm gì?

SQL là ngôn ngữ **khai báo kết quả**: bạn mô tả dữ liệu cần lấy, không ra lệnh phải dùng B-tree hay thuật toán join nào. **Query planner/optimizer** phân tích SQL và thống kê bảng để chọn một **cây phép toán** được cho là có chi phí thấp.

Ví dụ cùng một query có thể có các hướng:

```text
Hướng A: Seq Scan toàn bộ orders → Filter theo customer → Sort thời gian → Limit 20
Hướng B: Index Scan theo (customer_id, created_at DESC) → Limit 20
```

Nếu query nối `orders` với `customers`, plan còn có phép `Nested Loop`, `Hash Join` hoặc `Merge Join`. Các nhánh gần đáy cây lấy dòng từ bảng/index; các node phía trên kết hợp, lọc, nhóm, sắp xếp hoặc giới hạn kết quả.

### 4.1. Những node đủ dùng để đọc hiểu

| Node PostgreSQL | Đọc hiểu ở mức ứng dụng |
| --- | --- |
| `Seq Scan` | Đọc tuần tự bảng, thường hợp lý với bảng nhỏ hoặc lấy phần lớn dòng. Không tự kết luận đây là lỗi. |
| `Index Scan` | Dùng index tìm vị trí; thông thường vẫn có thể cần đọc row từ bảng. |
| `Index Only Scan` | Dùng dữ liệu có trong index, nhưng PostgreSQL vẫn có thể phải kiểm tra heap visibility; không phải lúc nào cũng “không đọc bảng”. |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Gom vị trí dòng từ index rồi đọc các trang bảng hiệu quả hơn cho một số số lượng kết quả. |
| `Filter` | Điều kiện áp dụng sau khi lấy dòng từ node; xem `Rows Removed by Filter` khi có. |
| `Index Cond` | Điều kiện được đẩy vào thao tác quét index, giúp thu hẹp phần cần tìm. |
| `Sort` | Sắp xếp kết quả, có thể tiêu thụ bộ nhớ hoặc spill ra đĩa. |
| `Limit` | Chỉ lấy số dòng được yêu cầu; có thể dừng node bên dưới sớm. |
| `Nested Loop` | Với mỗi dòng ở nhánh ngoài, truy cập nhánh trong; thường tốt khi tập ngoài nhỏ và nhánh trong có lookup hiệu quả. |
| `Hash Join` | Tạo bảng băm từ một phía rồi dò phía kia; thường hữu ích cho join bằng nhau trên tập đáng kể. |
| `Merge Join` | Ghép hai nguồn đã được sắp thứ tự theo khóa join hoặc có bước sắp xếp tương ứng. |
| `Aggregate` / `HashAggregate` | Thực hiện tính tổng, đếm, nhóm dữ liệu theo chiến lược phù hợp. |

**Tên node không phải điểm số tốt/xấu.** `Nested Loop` không mặc nhiên chậm; `Seq Scan` không mặc nhiên sai; `Index Scan` cũng không mặc nhiên nhanh. Phải đặt chúng trong số dòng, kích thước bảng, điều kiện và chi phí I/O cụ thể.

### 4.2. Đọc các con số quan trọng

Một node PostgreSQL có thể trông như sau (các số dưới đây **chỉ để giải thích cách đọc**, không phải kết quả của bài thực hành):

```text
Index Scan using orders_customer_created_at_idx on orders
  (cost=0.42..42.10 rows=20 width=36)
  (actual time=0.030..0.080 rows=20 loops=1)
```

- `cost=0.42..42.10`: **startup cost** và **total cost ước tính** trong đơn vị chi phí của planner, **không phải mili-giây**.
- `rows=20` bên phần ước tính: số **dòng đầu ra được dự đoán** từ node, không mặc nhiên là số dòng đã kiểm tra.
- `width=36`: kích thước trung bình ước tính của một dòng đầu ra, tính theo byte.
- `actual time=0.030..0.080`: thời gian thực tế tính theo mili-giây cho node khi chạy với `ANALYZE`.
- `actual ... rows=20 loops=1`: số dòng trung bình đầu ra trên mỗi lần chạy node và số lần node chạy. Nếu `loops=100`, phải xét hiệu ứng lặp; ví dụ một inner scan trong nested loop có thể chạy rất nhiều lần.
- `Buffers` (khi yêu cầu): cho biết trang dữ liệu liên quan được truy cập/đọc theo loại, giúp nhận diện I/O; số đo chịu ảnh hưởng cache và lần chạy.

Đừng so trực tiếp `cost=42.10` với `actual time=0.080` vì đó là **hai đơn vị khác nhau**. Thay vào đó, so `estimated rows` với `actual rows` (lưu ý `loops`), kiểm tra nơi thực hiện lượng công việc lớn, node có sort/đọc nhiều trang và các điều kiện lọc.

### 4.3. `EXPLAIN` khác `EXPLAIN ANALYZE`

```sql
EXPLAIN
SELECT id FROM orders WHERE customer_id = 42;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM orders WHERE customer_id = 42;
```

- `EXPLAIN` không có `ANALYZE`: cho xem **kế hoạch và ước tính**, không thực thi truy vấn `SELECT` để đo thời gian/dòng thực tế.
- `EXPLAIN (ANALYZE, BUFFERS)`: **thực thi thật** rồi ghi lại thời gian, số dòng và thông tin buffer. Kết quả query thông thường không được trả về dưới dạng tập dữ liệu, nhưng công việc của SQL vẫn diễn ra.
- **Không chạy tùy tiện `EXPLAIN ANALYZE` trên `INSERT`, `UPDATE`, `DELETE`, `MERGE` của môi trường thật:** vì câu lệnh sẽ thực thi và có tác động dữ liệu. Khi cần phân tích lệnh ghi, dùng môi trường thử nghiệm phù hợp; transaction với `ROLLBACK` có thể hoàn tác thay đổi DB trong nhiều tình huống, nhưng không đảm bảo hoàn tác mọi tác dụng bên ngoài như gửi sự kiện.
- Với truy vấn đọc lớn, `ANALYZE` vẫn tạo tải thật; chọn thời điểm và môi trường phù hợp.

Kế hoạch thực thi phụ thuộc **database version, dữ liệu, thống kê, tham số truy vấn, index hiện có và cấu hình**. Không ghi nhớ một hình plan như kết quả “chuẩn” duy nhất cho mọi môi trường.

## 5. Thực hành: trước và sau khi tạo index

Ví dụ này dùng **PostgreSQL 17+**, thao tác trong **một phiên kết nối** bằng `psql` hoặc trình chạy SQL. Các bảng là `TEMP`, tự mất khi phiên kết thúc. Có thể lưu đoạn sau vào `index_plan_demo.sql` rồi chạy `psql -d ten_co_so_du_lieu_thu_nghiem -f index_plan_demo.sql`; cần cơ sở dữ liệu PostgreSQL và quyền tạo bảng tạm. **Chạy một lần mỗi phiên**, vì tên bảng tạm sẽ trùng nếu lặp lại trong cùng phiên.

```sql
-- 1. Tạo bảng và ràng buộc toàn vẹn.
CREATE TEMP TABLE demo_customers (
    id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);

CREATE TEMP TABLE demo_orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES demo_customers(id),
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('NEW', 'PAID'))
);

-- 2. Tạo dữ liệu mẫu (100 customers, 30.000 orders).
INSERT INTO demo_customers (id, email)
SELECT n, 'user' || n || '@example.test'
FROM generate_series(1, 100) AS g(n);

INSERT INTO demo_orders (customer_id, created_at, status)
SELECT ((n - 1) % 100) + 1,
       TIMESTAMPTZ '2025-01-01 00:00:00+00'
           + n * INTERVAL '1 minute',
       CASE WHEN n % 7 = 0 THEN 'PAID' ELSE 'NEW' END
FROM generate_series(1, 30000) AS g(n);

-- 3. Thu thập thống kê để planner có dữ liệu ước lượng.
ANALYZE demo_customers;
ANALYZE demo_orders;

-- 4. Kế hoạch TRƯỚC khi có index phục vụ riêng truy vấn này.
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, customer_id, created_at, status
FROM demo_orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2025-01-10 00:00:00+00'
ORDER BY created_at DESC
LIMIT 20;

-- 5. Tạo index ghép theo bộ lọc + thứ tự.
CREATE INDEX demo_orders_customer_created_at_idx
    ON demo_orders (customer_id, created_at DESC);

ANALYZE demo_orders;

-- 6. Chạy lại CHÍNH XÁC câu truy vấn để đối chiếu kế hoạch.
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, customer_id, created_at, status
FROM demo_orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2025-01-10 00:00:00+00'
ORDER BY created_at DESC
LIMIT 20;

-- 7. Kiểm tra số bản ghi đã tạo.
SELECT (SELECT COUNT(*) FROM demo_customers) AS customer_count,
       (SELECT COUNT(*) FROM demo_orders) AS order_count;
```

Kết quả đếm có ý nghĩa cố định: `customer_count = 100` và `order_count = 30000`. **Không có một bản stdout `EXPLAIN` cố định**: plan và số đo thời gian/buffer có thể khác giữa các lần chạy, máy và phiên bản; đặc biệt hai lần đo có thể chịu ảnh hưởng dữ liệu đã nằm trong cache.

Hướng quan sát:

1. Trước khi tạo index ghép, hãy xem có `Seq Scan` và `Sort` hay không, đọc `Filter` và số dòng được trả. Index PK trên `id` không nhất thiết giúp truy vấn lọc theo `customer_id`.
2. Sau khi tạo `(customer_id, created_at DESC)`, xem planner có chọn `Index Scan`, `Index Cond` và có bỏ được `Sort` hay không. Một plan khả dĩ được **lược đồ hóa**, không phải output bắt buộc:

   ```text
   Limit
     -> Index Scan using demo_orders_customer_created_at_idx on demo_orders
          Index Cond: (customer_id = 42 AND created_at >= ...)
   ```

3. Đọc `actual rows` và `Buffers` ở những node đáng chú ý; xem liệu DB có phải xử lý quá nhiều dòng trước khi lấy được 20 dòng.
4. Nếu vẫn có `Seq Scan`, **đừng ép index ngay**. Cần xét bảng nhỏ hay lớn, thống kê, tỷ lệ dòng lọc, chi phí truy cập và có thực sự tiết kiệm tổng công việc hay không.
5. Nếu thêm `AND status = 'PAID'` mà index không chứa status, plan có thể dùng `Index Cond` cho customer/time và `Filter` thêm cho status; điều này không tự động là lỗi. Cân nhắc index khác chỉ khi truy vấn và tần suất truy cập thực tế chứng minh cần thiết.

**Vì sao dùng TEMP?** Dữ liệu mẫu không làm thay đổi bảng nghiệp vụ sẵn có; ràng buộc PK/FK/UNIQUE vẫn hoạt động; PostgreSQL có thể lấy kế hoạch cho các bảng tạm như bảng thường. `ANALYZE` ở đây quan trọng vì bảng tạm không được tiến trình autovacuum của phiên khác tự phân tích như bảng thường.

### 5.1. Kiểm tra ý nghĩa khóa ngay trên dữ liệu mẫu

Ví dụ độc lập sau thể hiện các quy tắc, **đừng gộp các INSERT cố ý gây lỗi vào script thực hành phía trên**:

```sql
-- Bị từ chối: customer 999 không tồn tại (vi phạm FK).
INSERT INTO demo_orders (customer_id, created_at, status)
VALUES (999, NOW(), 'NEW');

-- Bị từ chối: email đã tồn tại (vi phạm UNIQUE).
INSERT INTO demo_customers (id, email)
VALUES (101, 'user1@example.test');
```

Hai thao tác sẽ gây lỗi ràng buộc khi chạy trong phiên còn bảng tạm, như mong đợi; trong transaction có thể cần xử lý/rollback sau lỗi trước khi chạy lệnh khác. Những lỗi này liên quan **tính toàn vẹn dữ liệu**, không cho biết truy vấn đọc hiện tại có dùng index tốt hay không.

## 6. Đọc plan trong thực tế: một quy trình sáu câu hỏi

Khi một endpoint Spring trả về chậm và đã xác định thời gian nằm ở câu SQL, hãy lần lượt hỏi:

**1. SQL thực tế là gì, và tham số đại diện là gì?** Trong JPA, ORM có thể tạo SQL khác với thứ bạn hình dung từ `findBy...` hoặc JPQL. Xem SQL có join nào, truy vấn bao nhiêu lần, `WHERE` thực sự có điều kiện gì và kiểu dữ liệu nào được bind. Không ghi log dữ liệu cá nhân/secret tùy tiện.

**2. Câu truy vấn cần trả bao nhiêu dòng?** Một truy vấn pagination 20 dòng khác hoàn toàn báo cáo phải đọc hàng triệu dòng. Nếu không có `LIMIT` hoặc phân trang, index đơn thuần có thể không giải quyết lượng dữ liệu trả về quá lớn.

**3. Database đọc dữ liệu thế nào?** Xem `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`; xác định đang quét bảng nào và có index hỗ trợ điều kiện quan trọng hay không.

**4. Điều kiện được thực thi ở đâu?** Phân biệt `Index Cond` với `Filter`; đọc `Rows Removed by Filter` khi có. Một bộ lọc rất tốn công sau khi đọc nhiều dòng gợi ý phải xem lại cách viết truy vấn hoặc thiết kế index.

**5. Ước tính có sát thực tế không?** Khi `estimated rows` thấp nhưng `actual rows` lớn gấp nhiều lần, planner có thể chọn thuật toán join/scan chưa phù hợp do thống kê không đại diện hoặc do phân bố dữ liệu khó ước lượng. Xem lại thống kê, tham số, điều kiện có tương quan; đừng chỉ thêm index.

**6. Tổng chi phí đến từ đâu?** Nhìn `loops` của nested loop, I/O `BUFFERS`, `Sort`/sort spill, số lần chạy truy vấn từ ứng dụng, network round trip và lượng dữ liệu ánh xạ sang Java. Một truy vấn nhanh nhưng gọi 1.000 lần vẫn tạo endpoint chậm.

Đo lường trên dữ liệu đủ đại diện, so sánh cùng điều kiện và nhớ sự khác biệt giữa môi trường local, staging và production. Thời gian chạy một lần rất dễ dao động do cache, tải CPU, concurrent workload và thống kê.

## 7. Gắn với JDBC, JPA và Spring Data

Trong Spring, các lớp `JdbcTemplate`, JPA `EntityManager` hoặc Spring Data Repository quyết định **cách Java gửi yêu cầu**, còn DBMS vẫn chọn kế hoạch thực thi SQL cho dữ liệu của mình.

Một repository đọc 20 đơn hàng gần nhất bằng Spring JDBC có thể viết như sau. Đây là **lớp minh họa trong ứng dụng đã cấu hình `JdbcTemplate` và có bảng thật `orders`**, không phải chương trình Java độc lập; bảng `orders` ở đây không phải bảng tạm `demo_orders` của bài thực hành.

```java
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReadRepository {
    private final JdbcTemplate jdbc;

    public OrderReadRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderView> latestForCustomer(long customerId, Instant since) {
        return jdbc.query(
                """
                SELECT id, created_at, status
                FROM orders
                WHERE customer_id = ?
                  AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (rs, rowNum) -> new OrderView(
                        rs.getLong("id"),
                        rs.getTimestamp("created_at").toInstant(),
                        rs.getString("status")
                ),
                customerId,
                Timestamp.from(since)
        );
    }

    public record OrderView(long id, Instant createdAt, String status) {}
}
```

Code này sử dụng parameter binding cho hai **giá trị** truy vấn; `?` tránh ghép đầu vào vào SQL. Với môi trường PostgreSQL phù hợp, index `(customer_id, created_at DESC)` là một ứng viên kiểm tra qua `EXPLAIN`. Không có annotation `@Repository`, `@Transactional` hay tên phương thức nào **ép** database chọn `Index Scan`.

Với **Spring Data JPA**, phương thức như `findTop20ByCustomerIdOrderByCreatedAtDesc(...)` có thể giúp tạo truy vấn, nhưng:

- Kiểm tra SQL thực tế và tham số, vì mapping, fetch, pagination và quan hệ entity có thể ảnh hưởng câu SQL.
- Đừng suy luận “đã có PK trong entity thì mọi truy vấn theo FK đều nhanh”. PK của `orders.id` khác đường truy cập theo `orders.customer_id`.
- Phát hiện **N+1 query** ở tầng ORM: một SQL nhanh nhưng được gọi lặp khi lười tải quan hệ có thể gây tổng thời gian lớn. Fetch join, projection hoặc batch fetching đôi khi phù hợp hơn một index mới.
- Nếu thêm index, nên quản lý DDL trong migration (Flyway/Liquibase hoặc quy trình schema của hệ thống); không dựa vào Hibernate auto-DDL ở môi trường production để tạo chỉ mục tùy ý.
- Khi kiểm tra `EXPLAIN`, dùng SQL **tương đương** với SQL mà ứng dụng gửi và tham số đại diện; lưu ý việc DB dùng generic/custom plan với prepared statement có thể ảnh hưởng lựa chọn.

Về trách nhiệm kiến trúc: repository/DAO chịu trách nhiệm truy vấn; service giữ quy tắc nghiệp vụ và điều phối transaction; cơ sở dữ liệu thực thi ràng buộc PK/FK/UNIQUE và chọn plan. **Không thay các ràng buộc database bằng kiểm tra tồn tại đơn thuần trong Java**, vì request đồng thời có thể vượt qua kiểm tra ứng dụng trước khi ghi.

## 8. “Key” không phải “lock”: phân biệt ngắn gọn

Cùng từ “khóa” nhưng không cùng cơ chế:

- **Primary key/foreign key:** quy tắc định danh và quan hệ dữ liệu, tồn tại trong schema và được database cưỡng chế.
- **Row lock/table lock:** cơ chế phối hợp các transaction đọc/ghi đồng thời, tùy câu lệnh, DBMS và isolation level.
- **Index:** cấu trúc tăng hiệu quả một số đường truy cập; index không tự thay thế transaction hoặc locking.

Ví dụ, `SELECT ... FOR UPDATE` trong PostgreSQL có thể khóa những dòng được chọn trong transaction để phối hợp cập nhật cạnh tranh. Việc tìm dòng theo index có thể giúp định vị nhanh, nhưng **index và row lock là hai khái niệm khác nhau**. Đừng nghĩ chỉ mục loại bỏ hoàn toàn blocking, deadlock hay tranh chấp ghi. Các vấn đề locking/isolation cần được học riêng ở chủ đề transaction và concurrency.

## 9. Các lỗi tư duy phổ biến

| Nhận định dễ sai | Cách đọc/áp dụng đúng |
| --- | --- |
| “Có `PRIMARY KEY` thì mọi `WHERE` đều nhanh.” | PK hỗ trợ lookup trên cột/bộ cột PK; truy vấn theo cột khác phải xét index và plan của nó. |
| “Có `FOREIGN KEY` thì cột FK đã được index.” | Trong PostgreSQL, FK không tự tạo index phía tham chiếu; cần kiểm tra thực tế. |
| “Index càng nhiều càng tốt.” | Mỗi index tiêu tốn lưu trữ và làm thao tác ghi phải cập nhật thêm; tránh index trùng/không dùng. |
| “Thấy `Seq Scan` tức là query lỗi.” | Đọc toàn bảng có thể là lựa chọn tốt nhất cho bảng nhỏ hoặc truy vấn ít chọn lọc. |
| “Có `Index Scan` thì query chắc chắn nhanh.” | Có thể vẫn đọc nhiều dòng/buffer, join lặp nhiều lần hoặc truyền quá nhiều dữ liệu về Java. |
| “`cost` là số mili-giây.” | `cost` là đơn vị ước tính nội bộ; `actual time` mới là thời gian đo khi dùng `ANALYZE`. |
| “`EXPLAIN ANALYZE` chỉ mô phỏng.” | Nó thực sự chạy SQL, kể cả tác dụng ghi dữ liệu nếu câu lệnh có ghi. |
| “Cứ thêm index lên từng cột trong `WHERE`.” | Thứ tự cột của index ghép, selectivity, loại toán tử và mẫu truy vấn quyết định lợi ích. |
| “Tốc độ query trên H2/local chứng minh production sẽ nhanh.” | Engine, dữ liệu, thống kê, cache, version, khóa và tải thực tế có thể khác. |

## 10. Câu hỏi tự kiểm tra

1. Tại sao `PRIMARY KEY`, `UNIQUE` và `FOREIGN KEY` không thể thay bằng một index thông thường?
2. Nếu truy vấn lọc theo `customer_id` và lấy 20 dòng mới nhất theo `created_at`, vì sao `(customer_id, created_at DESC)` có thể hợp lý hơn `(created_at, customer_id)`?
3. Khi plan có `Seq Scan`, bạn cần thêm thông tin gì trước khi kết luận thiếu index?
4. Trong `EXPLAIN ANALYZE`, sự khác biệt giữa `rows=100` ở phần estimated và `actual rows=10000 loops=5` nói lên điều gì?
5. Nếu JPA phát 100 truy vấn nhỏ vì N+1, index mới có giải quyết hoàn toàn vấn đề không? Nên kiểm tra những gì?
6. Vì sao không chạy `EXPLAIN ANALYZE DELETE ...` tùy tiện trên dữ liệu thật?

**Ghi nhớ:** *Key* bảo vệ quy tắc dữ liệu, *index* hỗ trợ đường truy cập, còn *execution plan* cho thấy database chọn cách thực thi nào. Trong ứng dụng Spring, hãy bắt đầu từ SQL và dữ liệu thực tế, đọc `EXPLAIN`, kiểm tra số dòng/công việc, rồi mới quyết định thay đổi truy vấn hoặc chỉ mục.

### Tài liệu tra cứu thêm

- PostgreSQL 17 — [Indexes](https://www.postgresql.org/docs/17/indexes.html), đặc biệt [Multicolumn Indexes](https://www.postgresql.org/docs/17/indexes-multicolumn.html).
- PostgreSQL 17 — [Constraints](https://www.postgresql.org/docs/17/ddl-constraints.html).
- PostgreSQL 17 — [Using EXPLAIN](https://www.postgresql.org/docs/17/using-explain.html).
- PostgreSQL 17 — [ANALYZE](https://www.postgresql.org/docs/17/sql-analyze.html).

