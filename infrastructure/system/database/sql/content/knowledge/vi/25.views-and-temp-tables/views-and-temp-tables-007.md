# Materialized view và khác biệt với view thông thường

Một truy vấn tổng hợp có thể phải quét hàng triệu giao dịch, kết nối nhiều bảng và tính lại doanh thu mỗi khi người dùng mở dashboard. Để câu SQL dễ tái sử dụng, ta có thể tạo **view**. Nhưng nếu truy vấn vẫn tốn nhiều thời gian, việc đặt tên cho nó bằng `CREATE VIEW` không nhất thiết làm nó chạy nhanh hơn: mỗi lần truy vấn view thông thường, hệ quản trị vẫn phải tạo ra kết quả từ dữ liệu nguồn theo kế hoạch thực thi phù hợp.

Một lựa chọn khác là **materialized view** (view vật hóa): hệ quản trị **lưu kết quả của truy vấn** dưới dạng dữ liệu vật lý để các lần đọc sau sử dụng kết quả đã tính sẵn. Đổi lại, kết quả đó có thể **không còn mới** khi bảng nguồn thay đổi; cần quy trình **làm mới** (*refresh*).

Bài học thuộc chương **View và bảng trung gian** của Database SQL. Các ví dụ chính dùng **PostgreSQL** và phân biệt rõ bốn khái niệm:

1. **View thông thường:** lưu **định nghĩa truy vấn**, không lưu bộ kết quả thành một bản sao bền vững riêng.
2. **Materialized view:** lưu **định nghĩa và dữ liệu kết quả** tại lần tạo/làm mới gần nhất.
3. **Bảng trung gian/bảng tổng hợp:** lưu dữ liệu như một bảng do ứng dụng hoặc pipeline chủ động cập nhật.
4. **Refresh:** tái tạo dữ liệu vật hóa theo nguồn; không đồng nghĩa tự động cập nhật ngay khi có `INSERT`/`UPDATE`/`DELETE` ở bảng nguồn.

Để thấy khác biệt một cách trực tiếp, ta sẽ tạo hai đối tượng trả cùng các cột, thay đổi bảng đơn hàng, rồi so sánh những gì mỗi đối tượng hiển thị **trước và sau `REFRESH`**.

## 1. View thông thường là gì?

Một view thông thường (*ordinary view*, đôi khi gọi là *virtual view*) là một **đối tượng cơ sở dữ liệu có tên**, được định nghĩa bởi câu `SELECT`.

Ví dụ:

```sql
CREATE VIEW v_paid_orders AS
SELECT order_id, shop_id, placed_on, amount
FROM orders
WHERE status = 'paid';
```

Sau đó có thể truy vấn:

```sql
SELECT *
FROM v_paid_orders
WHERE shop_id = 10;
```

Điểm quan trọng: trong PostgreSQL, view thông thường **không chứa một bản sao lưu sẵn của toàn bộ các hàng `SELECT`**. Khi truy vấn view, hệ quản trị xử lý định nghĩa view cùng truy vấn bên ngoài để lấy dữ liệu phù hợp từ các bảng/đối tượng nguồn.

### 1.1. View không đồng nghĩa với bảng mới

Một câu `CREATE VIEW` chủ yếu lưu **logic truy vấn** cùng metadata. Nó không giống:

```sql
CREATE TABLE paid_orders_copy AS
SELECT ...
```

Lệnh `CREATE TABLE ... AS SELECT` tạo bảng thật chứa dữ liệu tại lúc thực thi. View thông thường không phải một lần sao chép kết quả như vậy.

### 1.2. Bảng nguồn thay đổi, view thông thường thường thấy ngay

Giả sử view lấy các đơn có `status='paid'`. Sau khi một transaction cập nhật đơn từ `pending` thành `paid` và **commit**, các lần `SELECT` mới từ view có thể thấy đơn ấy theo quy tắc transaction isolation của người đọc.

Không có lệnh `REFRESH VIEW` riêng để “cập nhật dữ liệu” của view thông thường trong PostgreSQL; view luôn được đánh giá dựa trên dữ liệu nguồn nhìn thấy đối với câu truy vấn hiện tại.

**Lưu ý:** “thấy ngay” ở đây là theo **snapshot của transaction**. Một transaction `REPEATABLE READ` đã mở trước commit của writer có thể tiếp tục thấy snapshot cũ. Điều đó không có nghĩa view lưu kết quả lỗi thời; đó là quy tắc cô lập giao dịch.

### 1.3. Vì sao tạo view vẫn rất hữu ích?

View giúp:

- **Đặt tên cho một phép truy vấn** dùng nhiều lần.
- **Tập trung logic nghiệp vụ** như chỉ lấy đơn `paid`.
- **Ẩn độ phức tạp** của JOIN, biểu thức và bộ lọc.
- **Tạo giao diện dữ liệu ổn định** cho ứng dụng báo cáo.
- **Kiểm soát cột được trình bày** và kết hợp với quyền truy cập, nếu cấu hình bảo mật đúng.

Nhưng một view không tự động biến một truy vấn tổng hợp nặng thành truy vấn nhẹ. Tối ưu thường phụ thuộc index trên bảng nguồn, kế hoạch thực thi, kích thước dữ liệu và điều kiện lọc.

## 2. Materialized view là gì?

Materialized view cũng có một câu `SELECT` định nghĩa. Khác biệt lớn là **kết quả SELECT được lưu thành các hàng vật lý** trong chính materialized view.

Trong PostgreSQL:

```sql
CREATE MATERIALIZED VIEW mv_paid_daily AS
SELECT
    shop_id,
    placed_on,
    COUNT(*) AS paid_orders,
    SUM(amount) AS revenue
FROM orders
WHERE status = 'paid'
GROUP BY shop_id, placed_on
WITH DATA;
```

`WITH DATA` yêu cầu tạo dữ liệu kết quả ngay khi tạo đối tượng. Sau đó:

```sql
SELECT *
FROM mv_paid_daily
ORDER BY placed_on, shop_id;
```

đọc **những hàng đã được lưu**, không tự chạy lại toàn bộ câu tổng hợp nguồn trong mỗi lần `SELECT`.

Sơ đồ:

```text
ORDINARY VIEW
┌───────────────┐        ┌────────────────────────────┐
│ Bảng orders   │ ─────► │ v_paid_daily               │
│ luôn thay đổi │        │ Lưu logic SELECT           │
└───────────────┘        │ Query mới đọc nguồn theo   │
                         │ snapshot của query         │
                         └────────────────────────────┘

MATERIALIZED VIEW
┌───────────────┐  CREATE / REFRESH  ┌───────────────────┐
│ Bảng orders   │ ─────────────────► │ mv_paid_daily     │
│ luôn thay đổi │                    │ Lưu hàng kết quả  │
└───────────────┘                    └───────────────────┘
                                             │
                                      SELECT nhanh hơn
                                      trong một số tải,
                                      nhưng có thể cũ
```

Materialized view là sự đánh đổi giữa:

- **Chi phí tính trước** và chi phí lưu dữ liệu.
- **Tốc độ truy vấn lại** trên dữ liệu đã tổng hợp.
- **Độ mới của dữ liệu** giữa hai lần refresh.
- **Chi phí và độ phức tạp vận hành refresh**.

### 2.1. View vật hóa không phải cache có TTL tự động

Trong PostgreSQL cơ bản, `CREATE MATERIALIZED VIEW` không tự cài lịch refresh và cũng không tự làm mới khi bảng nguồn thay đổi. Bạn phải gọi `REFRESH MATERIALIZED VIEW` hoặc xây dựng công việc bên ngoài để làm việc đó.

Một số DBMS khác có cơ chế refresh tự động, theo lịch hoặc incremental; đó là **khả năng phụ thuộc từng hệ**, không phải thuộc tính mặc định của mọi materialized view.

### 2.2. Dữ liệu vật hóa có thể được đánh index

Vì PostgreSQL materialized view lưu các hàng thật, ta có thể tạo index trên các cột đầu ra của nó để hỗ trợ những truy vấn đọc phổ biến.

Ngược lại, không thể tạo index vật lý trực tiếp trên một **ordinary view** của PostgreSQL như thể nó có các hàng riêng; thường phải tạo index trên bảng nguồn hoặc dùng materialized view/bảng tổng hợp khi thích hợp.

## 3. Bảng so sánh cốt lõi

| Tiêu chí | View thông thường | Materialized view (PostgreSQL) |
| --- | --- | --- |
| Lưu định nghĩa `SELECT` | Có | Có |
| Lưu các hàng kết quả vật lý riêng | Không | Có |
| Thấy thay đổi nguồn ở truy vấn mới | Theo snapshot transaction, thường cập nhật | Chỉ sau lần refresh phù hợp |
| Cần `REFRESH` để cập nhật kết quả lưu sẵn | Không | Có |
| Dung lượng lưu hàng kết quả | Không có bộ hàng riêng | Có, có thể lớn |
| Có thể tạo index trực tiếp trên kết quả | Không như bảng vật lý | Có |
| Tốc độ query | Tùy truy vấn gốc và optimizer | Có thể nhanh nếu đọc kết quả tính sẵn |
| Chi phí cập nhật dữ liệu | Không có bước refresh riêng | Có bước tính lại và duy trì index |
| Truy vấn chứa JOIN/aggregate phức tạp | Có thể | Có thể |
| Tự tăng tốc mọi truy vấn hay không | Không | Không |
| Nạp dữ liệu mới bằng `INSERT` trực tiếp vào đối tượng | Một số view đơn giản có thể cập nhật được; view aggregate thường không | Không cập nhật trực tiếp materialized view bằng DML thông thường |
| Phù hợp | Logic dùng chung, cần kết quả nguồn hiện tại | Báo cáo nặng, cho phép dữ liệu trễ theo chính sách |

Không nên kết luận materialized view luôn tốt hơn view: nếu người dùng cần giá trị **mới nhất sau mỗi commit**, hoặc truy vấn nguồn đã rất nhanh nhờ index, một materialized view có thể chỉ tăng chi phí lưu trữ và vận hành.

## 4. Chuẩn bị database thử nghiệm PostgreSQL

Trong PostgreSQL, materialized view là đối tượng lưu dữ liệu tương tự quan hệ vật lý. Để các ví dụ truy cập và refresh ổn định qua nhiều câu lệnh hoặc phiên, ta dùng **bảng thường trong schema riêng** thay vì `TEMP TABLE`.

**Chỉ chạy trong cơ sở dữ liệu học tập/sandbox.** Các lệnh sau tạo mới schema `demo_mv_317`. Không chạy vào production nếu tên schema đã được sử dụng cho mục đích khác.

### 4.1. Tạo schema và hai bảng nguồn

```sql
CREATE SCHEMA demo_mv_317;

CREATE TABLE demo_mv_317.shops (
    shop_id INTEGER PRIMARY KEY,
    shop_name TEXT NOT NULL UNIQUE
);

CREATE TABLE demo_mv_317.orders (
    order_id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL
        REFERENCES demo_mv_317.shops (shop_id),
    placed_on DATE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0)
);
```

Một hàng `orders` đại diện cho **một đơn**, đã có tổng tiền `amount` của đơn đó. Nếu một hệ thống lưu nhiều dòng hàng trong bảng `order_items`, không được JOIN làm nhân bản `orders.amount` rồi cộng nhầm như doanh thu.

### 4.2. Thêm hai cửa hàng và mười đơn

```sql
INSERT INTO demo_mv_317.shops (shop_id, shop_name)
VALUES
    (10, 'Cửa hàng Bắc'),
    (20, 'Cửa hàng Nam');

INSERT INTO demo_mv_317.orders
    (order_id, shop_id, placed_on, status, amount)
VALUES
    ( 1, 10, DATE '2025-08-01', 'paid',      100),
    ( 2, 10, DATE '2025-08-01', 'paid',       50),
    ( 3, 20, DATE '2025-08-01', 'paid',       80),
    ( 4, 10, DATE '2025-08-02', 'paid',       70),
    ( 5, 20, DATE '2025-08-02', 'pending',   120),
    ( 6, 20, DATE '2025-08-03', 'paid',       40),
    ( 7, 10, DATE '2025-08-03', 'cancelled',  60),
    ( 8, 20, DATE '2025-08-03', 'paid',       90),
    ( 9, 10, DATE '2025-08-04', 'paid',       30),
    (10, 20, DATE '2025-08-04', 'paid',       45);
```

Bộ dữ liệu có **10 đơn**, trong đó:

- **8 đơn paid**.
- **1 đơn pending** (ID 5), chưa tính vào doanh thu paid.
- **1 đơn cancelled** (ID 7), không tính vào doanh thu paid.

### 4.3. Tính doanh thu nguồn trước khi tạo view

```sql
SELECT
    shop_id,
    placed_on,
    COUNT(*) AS paid_orders,
    SUM(amount) AS paid_revenue
FROM demo_mv_317.orders
WHERE status = 'paid'
GROUP BY shop_id, placed_on
ORDER BY placed_on, shop_id;
```

Kết quả:

| Ngày | Shop | Số đơn paid | Doanh thu paid |
| --- | ---: | ---: | ---: |
| 2025-08-01 | 10 | 2 | 150 |
| 2025-08-01 | 20 | 1 | 80 |
| 2025-08-02 | 10 | 1 | 70 |
| 2025-08-03 | 20 | 2 | 130 |
| 2025-08-04 | 10 | 1 | 30 |
| 2025-08-04 | 20 | 1 | 45 |

Tổng doanh thu paid là:

```text
150 + 80 + 70 + 130 + 30 + 45 = 505
```

Đối chiếu bằng câu khác:

```sql
SELECT
    COUNT(*) AS paid_order_count,
    SUM(amount) AS total_paid_revenue
FROM demo_mv_317.orders
WHERE status = 'paid';
```

Kết quả: `paid_order_count = 8` và `total_paid_revenue = 505.00`.

Trong ngày 02/08, shop 20 chỉ có đơn pending nên **không có hàng doanh thu paid**. Ngày 03/08, shop 10 chỉ có đơn cancelled nên cũng **không có hàng**. Đây là hành vi tự nhiên của `GROUP BY` trên tập đã lọc, không phải lỗi của view.

## 5. Tạo view thông thường cho báo cáo ngày–cửa hàng

```sql
CREATE VIEW demo_mv_317.v_daily_paid_sales AS
SELECT
    o.placed_on,
    o.shop_id,
    COUNT(*) AS paid_orders,
    SUM(o.amount) AS paid_revenue
FROM demo_mv_317.orders AS o
WHERE o.status = 'paid'
GROUP BY o.placed_on, o.shop_id;
```

View này đóng gói quy tắc:

> Mỗi hàng kết quả đại diện một **ngày–cửa hàng có ít nhất một đơn paid**; `paid_orders` là số đơn paid và `paid_revenue` là tổng amount của các đơn đó.

Dùng nó như một bảng trong `SELECT`:

```sql
SELECT
    placed_on,
    shop_id,
    paid_orders,
    paid_revenue
FROM demo_mv_317.v_daily_paid_sales
ORDER BY placed_on, shop_id;
```

Kết quả là sáu hàng như phần 4.3.

### 5.1. Lọc thêm khi dùng view

```sql
SELECT *
FROM demo_mv_317.v_daily_paid_sales
WHERE shop_id = 10
  AND placed_on >= DATE '2025-08-01'
  AND placed_on <  DATE '2025-08-05'
ORDER BY placed_on;
```

Kết quả:

| Ngày | Shop | Paid orders | Paid revenue |
| --- | ---: | ---: | ---: |
| 2025-08-01 | 10 | 2 | 150 |
| 2025-08-02 | 10 | 1 | 70 |
| 2025-08-04 | 10 | 1 | 30 |

Điều kiện `WHERE` ngoài view giúp người dùng chọn phạm vi báo cáo. PostgreSQL optimizer có thể đưa một số điều kiện xuống dưới truy vấn view, tùy phép biến đổi an toàn và kế hoạch thực tế. Không phải cứ có view là engine phải tính mọi cửa hàng/ngày trước rồi mới lọc.

### 5.2. View thường dùng khi nào?

Dùng ordinary view nếu:

- Cần một **nguồn logic chung** mà nhiều truy vấn tham chiếu.
- Các thay đổi nguồn cần xuất hiện ngay trong câu đọc mới theo isolation.
- Truy vấn đủ nhẹ hoặc có index thích hợp trên bảng nguồn.
- Muốn thay đổi logic SQL ở một vị trí nhưng không nhân bản dữ liệu.
- Cần cho phép lọc theo các trường nguồn mà không muốn lưu vô số biến thể của kết quả.

**Đừng đặt tên `v_...` rồi mặc định view đã có dữ liệu được cache.** Trong PostgreSQL, `CREATE VIEW` không lưu sẵn sáu hàng trong ví dụ.

## 6. Tạo materialized view từ cùng logic

Ta có thể định nghĩa lại câu SQL hoặc tham chiếu view vừa tạo:

```sql
CREATE MATERIALIZED VIEW demo_mv_317.mv_daily_paid_sales AS
SELECT
    placed_on,
    shop_id,
    paid_orders,
    paid_revenue
FROM demo_mv_317.v_daily_paid_sales
WITH DATA;
```

Ở đây, materialized view lấy kết quả từ ordinary view tại lúc tạo và lưu dữ liệu vật lý.

### 6.1. So sánh kết quả ở thời điểm đầu

```sql
SELECT *
FROM demo_mv_317.v_daily_paid_sales
ORDER BY placed_on, shop_id;

SELECT *
FROM demo_mv_317.mv_daily_paid_sales
ORDER BY placed_on, shop_id;
```

Ngay sau khi tạo `WITH DATA`, hai truy vấn cho **cùng sáu hàng**, vì nguồn chưa thay đổi giữa hai bước.

Nhưng hai đối tượng có cơ chế khác nhau:

- `v_daily_paid_sales` đọc qua truy vấn nguồn theo snapshot của câu lệnh.
- `mv_daily_paid_sales` đọc sáu hàng **đã vật hóa** vào thời điểm tạo.

### 6.2. Có thể tạo materialized view không thông qua view thường

```sql
CREATE MATERIALIZED VIEW demo_mv_317.mv_daily_paid_direct AS
SELECT
    placed_on,
    shop_id,
    COUNT(*) AS paid_orders,
    SUM(amount) AS paid_revenue
FROM demo_mv_317.orders
WHERE status = 'paid'
GROUP BY placed_on, shop_id
WITH DATA;
```

Đây là **materialized view thứ hai**, chỉ để minh họa cách viết trực tiếp, không cần thiết cho các bước so sánh tiếp theo. Có thể bỏ qua câu này nếu chỉ muốn duy trì một materialized view trong bài thực hành.

Dùng view thường làm nguồn giúp **chia sẻ logic**; định nghĩa trực tiếp có thể giảm tầng phụ thuộc. Cả hai đều không biến materialized view thành dữ liệu tự cập nhật.

## 7. Thí nghiệm quan trọng: bảng nguồn đổi, hai view khác nhau

Bây giờ thêm một đơn paid vào cùng ngày/cửa hàng đã có:

```sql
INSERT INTO demo_mv_317.orders
    (order_id, shop_id, placed_on, status, amount)
VALUES
    (11, 10, DATE '2025-08-01', 'paid', 25);
```

Sau khi INSERT commit (nếu dùng autocommit thông thường, statement đã được commit), tổng doanh thu ngày 01/08 shop 10 tăng từ **150** thành **175**, và số đơn paid tăng từ 2 lên 3.

### 7.1. View thông thường cho kết quả mới

```sql
SELECT placed_on, shop_id, paid_orders, paid_revenue
FROM demo_mv_317.v_daily_paid_sales
WHERE placed_on = DATE '2025-08-01'
  AND shop_id = 10;
```

Kết quả:

| Ngày | Shop | Paid orders | Paid revenue |
| --- | ---: | ---: | ---: |
| 2025-08-01 | 10 | 3 | 175 |

Vì ordinary view đọc dữ liệu nguồn đã commit theo snapshot hiện tại, nó thấy đơn mới.

### 7.2. Materialized view vẫn trả kết quả lưu cũ

```sql
SELECT placed_on, shop_id, paid_orders, paid_revenue
FROM demo_mv_317.mv_daily_paid_sales
WHERE placed_on = DATE '2025-08-01'
  AND shop_id = 10;
```

Kết quả:

| Ngày | Shop | Paid orders | Paid revenue |
| --- | ---: | ---: | ---: |
| 2025-08-01 | 10 | 2 | 150 |

**Đây không phải lỗi tổng hợp**: materialized view vẫn chứa kết quả của lần tạo gần nhất. Nó chưa được làm mới.

### 7.3. So sánh tổng trên toàn bộ ngày/cửa hàng

```sql
SELECT SUM(paid_revenue) AS live_revenue
FROM demo_mv_317.v_daily_paid_sales;

SELECT SUM(paid_revenue) AS stored_revenue
FROM demo_mv_317.mv_daily_paid_sales;
```

Ngay sau thay đổi:

```text
ordinary view     → 530
materialized view → 505
chênh lệch        → 25
```

Các phép tính:

```text
Nguồn ban đầu = 505
Đơn mới       =  25
Nguồn hiện tại = 530
Materialized view vẫn = 505 (chưa refresh)
```

Nếu chạy hai câu trong hai transaction khác nhau và có writer khác tiếp tục sửa dữ liệu, phép so sánh có thể bị ảnh hưởng bởi timing. Đối với thí nghiệm này, hãy giữ nguyên dữ liệu trong lúc đọc để quan sát chính xác.

## 8. Làm mới bằng REFRESH MATERIALIZED VIEW

Để đồng bộ kết quả vật hóa với truy vấn nguồn hiện tại:

```sql
REFRESH MATERIALIZED VIEW demo_mv_317.mv_daily_paid_sales;
```

Sau đó:

```sql
SELECT *
FROM demo_mv_317.mv_daily_paid_sales
WHERE placed_on = DATE '2025-08-01'
  AND shop_id = 10;
```

Bây giờ materialized view trả:

```text
paid_orders  = 3
paid_revenue = 175
```

Tổng doanh thu vật hóa là **530**, bằng ordinary view ở thời điểm nguồn không thay đổi thêm.

### 8.1. REFRESH làm gì?

Trong PostgreSQL, `REFRESH MATERIALIZED VIEW` thực thi lại truy vấn định nghĩa materialized view để thay thế tập kết quả lưu sẵn bằng kết quả mới.

`REFRESH`:

- **Không sửa** các hàng của bảng nguồn.
- **Không yêu cầu** ứng dụng viết lại `CREATE MATERIALIZED VIEW`.
- **Không chạy tự động** khi bảng nguồn được INSERT/UPDATE/DELETE.
- **Có thể tiêu tốn tài nguyên đáng kể** nếu câu tổng hợp nguồn rất lớn.
- Không nên được hiểu là một thuật toán incremental chung chỉ cập nhật vài nhóm thay đổi; PostgreSQL core thường phải đánh giá lại truy vấn định nghĩa.

### 8.2. Khi REFRESH bắt đầu, snapshot nào được đọc?

Truy vấn nguồn của một lần refresh chạy theo quy tắc transaction/snapshot của DBMS tại thời điểm phù hợp. Nếu một giao dịch khác commit **sau khi snapshot dùng cho refresh đã hình thành**, thay đổi đó có thể không nằm trong kết quả refresh vừa hoàn thành.

Vì vậy, trạng thái “refresh vừa xong” **không có nghĩa** không tồn tại cập nhật nguồn mới hơn. Độ mới phải được đo theo một quy ước rõ: mốc snapshot, thời điểm làm mới, watermark của nguồn hoặc chấp nhận độ trễ tối đa.

### 8.3. Refresh nhiều lần có làm tăng số đơn trong MV không?

Không. Một materialized view tổng hợp theo `(placed_on,shop_id)` không tự tích lũy thêm dữ liệu mỗi lần refresh. Nếu nguồn không thay đổi, chạy:

```sql
REFRESH MATERIALIZED VIEW demo_mv_317.mv_daily_paid_sales;
REFRESH MATERIALIZED VIEW demo_mv_317.mv_daily_paid_sales;
```

vẫn cho cùng sáu hàng ở thời điểm hiện tại. Đây là **tính tái tạo từ truy vấn nguồn**, không phải thao tác `INSERT` thêm vào kết quả cũ.

## 9. INSERT, UPDATE, DELETE ở nguồn đều ảnh hưởng kết quả khi refresh

Không chỉ INSERT. Từ trạng thái sau phần 8 (đã có đơn 11), thực hiện ba thay đổi:

```sql
-- Đơn paid đổi amount từ 70 lên 90:
UPDATE demo_mv_317.orders
SET amount = 90
WHERE order_id = 4;

-- Đơn pending được xác nhận paid:
UPDATE demo_mv_317.orders
SET status = 'paid'
WHERE order_id = 5;

-- Hủy bỏ hoàn toàn một bản ghi paid khỏi nguồn:
DELETE FROM demo_mv_317.orders
WHERE order_id = 8;
```

Đây là các thao tác minh họa trên database thử nghiệm, không phải chính sách xử lý hoàn tiền hoặc xóa lịch sử thật. Trong nghiệp vụ, xóa vật lý đơn có thể không hợp lệ; có thể cần trạng thái khác hoặc sự kiện điều chỉnh.

### 9.1. Kết quả live mới

```sql
SELECT *
FROM demo_mv_317.v_daily_paid_sales
ORDER BY placed_on, shop_id;
```

| Ngày | Shop | Số đơn paid | Doanh thu paid |
| --- | ---: | ---: | ---: |
| 2025-08-01 | 10 | 3 | 175 |
| 2025-08-01 | 20 | 1 | 80 |
| 2025-08-02 | 10 | 1 | 90 |
| 2025-08-02 | 20 | 1 | 120 |
| 2025-08-03 | 20 | 1 | 40 |
| 2025-08-04 | 10 | 1 | 30 |
| 2025-08-04 | 20 | 1 | 45 |

Tổng:

```text
175 + 80 + 90 + 120 + 40 + 30 + 45 = 580
```

Diễn giải chênh lệch:

```text
Trạng thái đã refresh sau đơn 11 = 530
Đổi amount đơn 4 từ 70 lên 90 = +20
Đơn 5 chuyển pending thành paid = +120
Xóa đơn paid số 8 (amount 90)    = -90
Nguồn sau thay đổi               = 580
```

### 9.2. Materialized view vẫn cũ trước refresh

Sau khi sửa nguồn nhưng **chưa** gọi `REFRESH` lần nữa, `mv_daily_paid_sales` vẫn tổng **530** và chỉ có sáu nhóm. Đặc biệt nó chưa có nhóm ngày 02/08 shop 20, vì nhóm đó trước đây chỉ có đơn pending.

### 9.3. Làm mới để nhận cả những nhóm phát sinh mới

```sql
REFRESH MATERIALIZED VIEW demo_mv_317.mv_daily_paid_sales;

SELECT *
FROM demo_mv_317.mv_daily_paid_sales
ORDER BY placed_on, shop_id;
```

Lúc này có **bảy nhóm**, tổng 580. Nhóm `(2025-08-02, shop 20)` xuất hiện với doanh thu 120; nhóm `(2025-08-03, shop 20)` giảm từ 130 xuống 40.

**Materialized view lưu kết quả của truy vấn**, nên khi nguồn thay đổi làm nhóm mới xuất hiện, nhóm cũ biến mất hoặc giá trị nhóm thay đổi, lần refresh có nhiệm vụ phản ánh cả ba trường hợp.

## 10. WITH DATA và WITH NO DATA

PostgreSQL cho phép tạo materialized view **có** hoặc **chưa có** dữ liệu được nạp.

### 10.1. WITH DATA — tạo và nạp ngay

```sql
CREATE MATERIALIZED VIEW demo_mv_317.mv_shop_totals AS
SELECT
    shop_id,
    COUNT(*) AS paid_orders,
    SUM(amount) AS paid_revenue
FROM demo_mv_317.orders
WHERE status = 'paid'
GROUP BY shop_id
WITH DATA;
```

Đối tượng sẵn sàng được `SELECT` sau khi tạo. Trong bộ dữ liệu sau phần 9:

| shop_id | paid_orders | paid_revenue |
| ---: | ---: | ---: |
| 10 | 5 | 295 |
| 20 | 4 | 285 |

Kiểm tra: `295 + 285 = 580`, số đơn paid `5 + 4 = 9`.

### 10.2. WITH NO DATA — tạo định nghĩa, chưa có dữ liệu đọc được

```sql
CREATE MATERIALIZED VIEW demo_mv_317.mv_shop_totals_later AS
SELECT
    shop_id,
    COUNT(*) AS paid_orders,
    SUM(amount) AS paid_revenue
FROM demo_mv_317.orders
WHERE status = 'paid'
GROUP BY shop_id
WITH NO DATA;
```

Một materialized view ở trạng thái **chưa populated** không tương đương một bảng rỗng hợp lệ. Trong PostgreSQL, `SELECT` trực tiếp từ materialized view chưa được nạp sẽ báo lỗi cho đến khi refresh có dữ liệu:

```sql
-- Nếu chạy ngay lúc này sẽ báo lỗi vì MV chưa populated:
SELECT * FROM demo_mv_317.mv_shop_totals_later;
```

Để nạp:

```sql
REFRESH MATERIALIZED VIEW demo_mv_317.mv_shop_totals_later;

SELECT *
FROM demo_mv_317.mv_shop_totals_later
ORDER BY shop_id;
```

Sau refresh, nó có hai hàng như `mv_shop_totals`.

### 10.3. Khi nào dùng WITH NO DATA?

- Muốn tạo cấu trúc trước, rồi nạp ở một bước triển khai riêng.
- Muốn kiểm soát thời điểm chạy tác vụ nạp đầu tiên.
- Tách bước triển khai DDL khỏi bước dựng dữ liệu lớn.

Nhưng không nên cấp cho dashboard một materialized view chưa populated rồi kỳ vọng nó tự hiển thị 0 hàng: PostgreSQL sẽ không cho đọc bình thường trước lần nạp đầu tiên.

### 10.4. REFRESH ... WITH NO DATA

PostgreSQL còn hỗ trợ:

```sql
REFRESH MATERIALIZED VIEW demo_mv_317.mv_shop_totals_later
WITH NO DATA;
```

Lệnh này bỏ trạng thái dữ liệu đã populated để đối tượng không còn sẵn sàng cho truy vấn cho đến khi `REFRESH ... WITH DATA` trở lại. Đây không phải cách “làm mới nhanh hơn”; cần hiểu hậu quả tạm thời không thể đọc dữ liệu.

## 11. Tạo index trên materialized view

Ví dụ báo cáo luôn truy vấn theo `placed_on` và `shop_id`:

```sql
SELECT paid_orders, paid_revenue
FROM demo_mv_317.mv_daily_paid_sales
WHERE placed_on = DATE '2025-08-02'
  AND shop_id = 20;
```

Ta có thể thêm index:

```sql
CREATE UNIQUE INDEX uq_mv_daily_paid_sales_317
ON demo_mv_317.mv_daily_paid_sales (placed_on, shop_id);
```

Vì truy vấn định nghĩa `GROUP BY placed_on, shop_id`, kết quả có **tối đa một hàng cho mỗi cặp khóa**. Unique index phản ánh đúng grain của dữ liệu vật hóa.

### 11.1. Unique index mang hai lợi ích

- Hỗ trợ truy vấn lọc theo khóa, tùy optimizer và phân bố dữ liệu.
- Trong PostgreSQL, tạo điều kiện quan trọng để có thể gọi `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

Nếu materialized view chứa nhiều hàng cùng `(placed_on, shop_id)` thì index unique sẽ không tạo được. Không được tùy tiện thêm cột kỹ thuật vào index chỉ để né trùng nếu truy vấn thực tế phải có một hàng trên mỗi cặp.

### 11.2. Index không bảo đảm luôn được sử dụng

Bảng mẫu chỉ vài hàng. PostgreSQL có thể chọn quét tuần tự dù có index, vì quét một quan hệ rất nhỏ rẻ hơn đọc index.

Khi quy mô thực tế lớn, index có thể rất hữu ích nếu các truy vấn thường lọc theo các cột đầu ra. Nhưng index cũng tăng dung lượng lưu trữ và có thể tăng chi phí xây dựng/duy trì khi refresh.

### 11.3. Ordinary view cần index ở đâu?

Không thể làm như sau trong PostgreSQL:

```sql
-- CỐ Ý KHÔNG HỢP LỆ: ordinary view không có dữ liệu vật lý riêng để index.
CREATE INDEX idx_v_paid_sales
ON demo_mv_317.v_daily_paid_sales (placed_on, shop_id);
```

Thay vào đó, xem xét index trên bảng nguồn:

```sql
CREATE INDEX idx_orders_paid_date_shop_317
ON demo_mv_317.orders (placed_on, shop_id)
WHERE status = 'paid';
```

Index trên nguồn cũng có thể hỗ trợ truy vấn định nghĩa materialized view **khi refresh**, dù lựa chọn thực tế tùy kế hoạch truy vấn. Trong PostgreSQL, `CREATE VIEW` chỉ thêm lớp logic, không tạo nơi lưu index của chính các hàng kết quả.

## 12. REFRESH thông thường và REFRESH CONCURRENTLY

Hai cách làm mới quan trọng nhất trong PostgreSQL:

```sql
REFRESH MATERIALIZED VIEW demo_mv_317.mv_daily_paid_sales;
```

và:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    demo_mv_317.mv_daily_paid_sales;
```

### 12.1. REFRESH thông thường

Lệnh refresh bình thường thay kết quả đã lưu. Trong lúc làm mới, nó có thể **chặn những truy vấn SELECT khác** muốn đọc chính materialized view đó do khóa mà PostgreSQL sử dụng.

Với materialized view ít hàng, thời gian rất ngắn; với báo cáo tổng hợp lớn, cần cân nhắc ảnh hưởng tới người đọc dashboard.

### 12.2. REFRESH CONCURRENTLY

`CONCURRENTLY` được thiết kế để quá trình refresh **không khóa chặn SELECT thông thường trên materialized view theo cách của refresh bình thường**. Người đọc có thể tiếp tục sử dụng bộ dữ liệu vật hóa đang khả dụng trong khi một bộ kết quả mới được xây dựng và áp dụng.

Đổi lại, đường làm mới này có yêu cầu và chi phí riêng. Không được hiểu `CONCURRENTLY` là “không có bất kỳ khóa nào, không tốn tài nguyên, mọi SELECT thấy dữ liệu nguồn ngay lập tức”.

### 12.3. Điều kiện tiên quyết cho CONCURRENTLY trong PostgreSQL

Đối với materialized view được làm mới đồng thời:

1. Materialized view phải **đã populated**.
2. Phải có **ít nhất một unique index** trên materialized view.
3. Unique index ấy phải dùng **chỉ tên cột đầu ra**, không phải expression index.
4. Index phải **bao phủ mọi hàng**, không phải partial index có `WHERE`.
5. Không thể đồng thời chạy nhiều thao tác refresh cùng một materialized view như các tác vụ độc lập không phối hợp.

Index từ phần 11 đáp ứng điều kiện trên:

```sql
CREATE UNIQUE INDEX uq_mv_daily_paid_sales_317
ON demo_mv_317.mv_daily_paid_sales (placed_on, shop_id);
```

Sau khi đã tạo và nạp materialized view:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    demo_mv_317.mv_daily_paid_sales;
```

### 12.4. Những index KHÔNG phù hợp làm điều kiện CONCURRENTLY

Một partial unique index:

```sql
-- Không đủ điều kiện CONCURRENTLY nếu đây là unique index duy nhất:
CREATE UNIQUE INDEX uq_mv_recent_only_317
ON demo_mv_317.mv_daily_paid_sales (placed_on, shop_id)
WHERE placed_on >= DATE '2025-08-01';
```

Index này chỉ bảo vệ một tập con các hàng, không đáp ứng quy tắc unique bao phủ mọi hàng của `REFRESH ... CONCURRENTLY`.

Một expression unique index:

```sql
-- Cũng không đủ điều kiện nếu đây là unique index duy nhất:
CREATE UNIQUE INDEX uq_mv_derived_317
ON demo_mv_317.mv_daily_paid_sales (
    (placed_on + 0),
    shop_id
);
```

Nó dựa trên biểu thức, không chỉ các tên cột đơn giản. Ở đây chỉ minh họa **loại index không đủ điều kiện**, không yêu cầu tạo các index này trong bộ thử nghiệm.

Nếu materialized view có thêm một index unique hợp lệ như `uq_mv_daily_paid_sales_317`, sự tồn tại của các index khác không làm mất điều kiện đó.

### 12.5. Có thể dùng CONCURRENTLY với WITH NO DATA không?

Không. Một materialized view vừa tạo `WITH NO DATA` **chưa populated**, nên chưa thể refresh bằng `CONCURRENTLY`. Cần một lần refresh bình thường để nạp dữ liệu, sau đó mới dùng `CONCURRENTLY` khi đã có unique index hợp lệ.

Ngoài ra, `REFRESH ... CONCURRENTLY` không kết hợp với `WITH NO DATA`.

### 12.6. Lịch đọc trong lúc refresh đồng thời

```text
t0: materialized view chứa tổng 530
t1: bảng orders đã có tổng 580
t2: bắt đầu REFRESH CONCURRENTLY
t3: truy vấn đọc MV có thể tiếp tục đọc phiên bản đang có
t4: refresh hoàn tất, kết quả mới được công bố
t5: truy vấn mới đọc MV thấy tổng 580 (nếu nguồn không đổi thêm)
```

Ở những snapshot/transaction đã mở, khả năng quan sát cụ thể còn phụ thuộc isolation và thời điểm bắt đầu. Điểm cốt lõi là `CONCURRENTLY` ưu tiên **khả năng tiếp tục đọc** hơn việc bắt mọi truy vấn đợi kết quả refresh.

## 13. Refresh có tự động theo lịch không?

Trong PostgreSQL core, materialized view **không tự theo dõi mọi thay đổi của bảng nguồn để làm mới ngay lập tức**. Nếu cần làm mới định kỳ, phải xây dựng hoặc sử dụng một cơ chế điều phối ngoài câu `CREATE MATERIALIZED VIEW`:

- Job scheduler của hệ điều hành hoặc nền tảng.
- Công việc ETL/ELT sau khi nạp xong dữ liệu.
- Dịch vụ ứng dụng chạy tác vụ theo lịch.
- Công cụ lập lịch mở rộng phù hợp với hệ thống PostgreSQL nếu đã được cài đặt và quản trị.

Ví dụ một job có thể chạy:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    demo_mv_317.mv_daily_paid_sales;
```

định kỳ theo chính sách của ứng dụng. **Bản thân câu SQL trên không lập lịch**; nó chỉ làm mới **ngay tại lần được gọi**.

### 13.1. Chọn chu kỳ refresh theo yêu cầu dữ liệu

Giả sử dữ liệu đơn hàng cập nhật liên tục:

| Yêu cầu dashboard | Hướng xử lý có thể phù hợp |
| --- | --- |
| Doanh thu cập nhật sau mỗi commit | Ordinary view hoặc truy vấn bảng/summary được cập nhật đồng bộ |
| Chấp nhận chậm 5–15 phút | Materialized view refresh định kỳ, nếu chi phí cho phép |
| Báo cáo cuối ngày | Refresh sau khi hoàn tất nạp/đối soát cuối ngày |
| Số liệu tháng trước ít thay đổi | Materialized view/summary được làm mới khi dữ liệu điều chỉnh |
| Báo cáo phải đồng bộ nhiều bảng nguồn | Refresh sau pipeline xác nhận watermark nhất quán |

Không tự chọn chu kỳ chỉ dựa vào cảm giác. Một materialized view nặng có thể mất nhiều thời gian để refresh; nếu lịch chạy dày hơn thời gian làm mới, các tác vụ có thể tranh chấp hoặc chất đống. Nên giám sát thời lượng, hàng nguồn, trạng thái lỗi và tuổi dữ liệu.

### 13.2. Xử lý khi refresh thất bại

Một hệ thống cần biết:

- Lần refresh gần nhất **thành công** khi nào?
- Lần refresh hiện tại có đang chạy không?
- Nếu job lỗi, dashboard có được phép dùng **dữ liệu cũ** không?
- Khi dữ liệu vượt quá độ trễ cho phép, ứng dụng sẽ cảnh báo, từ chối hay chuyển sang truy vấn nguồn?

Trong PostgreSQL, một lần refresh thất bại không phải bằng chứng đã có bộ dữ liệu mới. Đừng cập nhật cột “last_successful_refresh” trong hệ thống giám sát **trước khi lệnh refresh thực sự hoàn tất và commit**.

### 13.3. REFRESH không đương nhiên là incremental

Một kỳ vọng sai:

> Đơn 11 mới thêm, vậy REFRESH chỉ tính đúng một đơn đó.

Trong PostgreSQL cơ bản, `REFRESH MATERIALIZED VIEW` đánh giá lại truy vấn định nghĩa để dựng dữ liệu vật hóa mới. Dù engine có nhiều tối ưu ở kế hoạch thực thi và `CONCURRENTLY` có cơ chế áp dụng khác biệt, không nên tuyên bố có hệ thống incremental maintenance đầy đủ chỉ vì dùng materialized view.

Nếu cần cập nhật nhóm doanh thu **ngay khi từng đơn thay đổi** mà không quét lại lịch sử, nên cân nhắc **bảng tổng hợp được pipeline duy trì** với các quy tắc xử lý thêm/sửa/xóa và transaction phù hợp. Một số hệ khác hỗ trợ incremental materialized views theo giới hạn riêng.

## 14. Độ mới dữ liệu: view vật hóa trả lời một câu hỏi khác

Một dashboard có thể hỏi: “Doanh thu shop 10 **tính tới hiện tại** là bao nhiêu?” hoặc “Doanh thu shop 10 **ở đợt tổng hợp đã chốt gần nhất** là bao nhiêu?” Hai câu hỏi không giống nhau.

Ordinary view thường phù hợp hơn với câu hỏi thứ nhất. Materialized view phù hợp với câu hỏi thứ hai khi hệ thống đã định nghĩa lịch refresh hoặc mốc chốt số.

### 14.1. Data freshness, as-of time và refresh time

Có ít nhất ba mốc cần phân biệt:

| Mốc | Ý nghĩa |
| --- | --- |
| `source_event_time` | Thời điểm sự kiện nghiệp vụ phát sinh |
| `source_committed_at` / source watermark | Mốc dữ liệu nguồn được xác nhận hoặc bao phủ |
| `last_successful_refresh_at` | Thời điểm tác vụ refresh hoàn tất thành công |

`last_successful_refresh_at` không tự chứng minh rằng mọi sự kiện trước thời điểm đó đều đã có trong nguồn. Ví dụ, một giao dịch phát sinh hôm qua nhưng được nhập vào hệ thống sau lần refresh sáng nay thì chưa thể xuất hiện trong kết quả vật hóa sáng nay.

Nếu nguồn dữ liệu có **độ trễ nạp** và nhiều luồng xử lý, nên kết hợp timestamp refresh với **watermark dữ liệu đã nạp và đối soát** thay vì hiển thị một nhãn “real-time” chỉ vì job vừa chạy.

### 14.2. Materialized view không phải ảnh chụp lịch sử bất biến

Nếu chạy refresh lại sau khi sửa các giao dịch tháng trước, doanh thu tháng trước trong materialized view cũng thay đổi.

Vì vậy, một materialized view không tự thay thế cho **báo cáo đã chốt và phải lưu lịch sử**. Nếu cần bảo toàn “số liệu từng được công bố lúc 18:00 ngày cuối tháng”, phải thiết kế lưu phiên bản/snapshot báo cáo có định danh và quy trình chốt số riêng.

### 14.3. So sánh nguồn và kết quả vật hóa

Sau thay đổi cuối ở phần 9 và refresh thành công:

```sql
SELECT
    (SELECT COUNT(*)
     FROM demo_mv_317.orders
     WHERE status = 'paid') AS source_paid_orders,
    (SELECT SUM(paid_orders)
     FROM demo_mv_317.mv_daily_paid_sales) AS mv_paid_orders,
    (SELECT SUM(amount)
     FROM demo_mv_317.orders
     WHERE status = 'paid') AS source_revenue,
    (SELECT SUM(paid_revenue)
     FROM demo_mv_317.mv_daily_paid_sales) AS mv_revenue;
```

Khi không có writer tiếp tục thay đổi bảng giữa các lần đọc, kết quả:

| `source_paid_orders` | `mv_paid_orders` | `source_revenue` | `mv_revenue` |
| ---: | ---: | ---: | ---: |
| 9 | 9 | 580 | 580 |

Đối chiếu này giúp xác nhận trạng thái đã lưu trong một bộ dữ liệu thử nghiệm. Trong hệ thống ghi đồng thời, nên chạy phép đối chiếu trong một transaction có snapshot phù hợp hoặc so với cùng một **watermark**, để không gọi một khác biệt do thời điểm đọc là lỗi của materialized view.

### 14.4. Cách diễn đạt độ trễ trên giao diện

Một thông báo như:

> Số liệu được tổng hợp đến lần cập nhật thành công lúc 08:00; những giao dịch đến muộn có thể xuất hiện ở lần kế tiếp.

thường chính xác hơn khẳng định “dữ liệu mới nhất” khi đang đọc materialized view định kỳ. Chú thích này nên dựa vào **thời điểm thành công thật** của job, không phải thời điểm dashboard được mở.

## 15. Chọn grain: vật hóa theo ngày–cửa hàng hay theo tháng?

Trong ví dụ, mỗi hàng của `mv_daily_paid_sales` là một cặp:

```text
(placed_on, shop_id) → paid_orders, paid_revenue
```

Đây là **grain** của materialized view. Nó quyết định:

- Số hàng phải lưu.
- Những truy vấn có thể trả lời từ MV.
- Khóa phù hợp để tạo unique index.
- Mức độ linh hoạt khi người dùng muốn phân tích thêm.

### 15.1. Từ ngày–cửa hàng lên tổng tháng

Ta có thể dùng materialized view hiện tại để tính doanh thu theo tháng:

```sql
SELECT
    DATE_TRUNC('month', placed_on::timestamp)::date AS month_start,
    shop_id,
    SUM(paid_orders) AS paid_orders,
    SUM(paid_revenue) AS paid_revenue
FROM demo_mv_317.mv_daily_paid_sales
GROUP BY
    DATE_TRUNC('month', placed_on::timestamp)::date,
    shop_id
ORDER BY month_start, shop_id;
```

Vì các nhóm ngày–cửa hàng không trùng và đều đại diện cho đơn paid, cộng doanh thu của các ngày cho tháng là hợp lệ.

Trong mẫu sau refresh:

| Tháng | Shop | Số đơn paid | Doanh thu paid |
| --- | ---: | ---: | ---: |
| 2025-08 | 10 | 5 | 295 |
| 2025-08 | 20 | 4 | 285 |

### 15.2. Nhưng từ tháng không thể tự khôi phục ngày

Nếu chỉ vật hóa một hàng **tháng–cửa hàng**, người dùng muốn xem doanh thu riêng ngày 02/08 sẽ không thể suy ra chính xác từ số tổng tháng đó.

Một materialized view quá thô có thể nhanh nhưng mất khả năng phân tích chi tiết. Một materialized view quá chi tiết có thể gần bằng kích thước bảng nguồn, làm giảm lợi ích lưu sẵn.

**Chọn grain theo bộ câu hỏi báo cáo cần trả lời**, không chỉ theo tốc độ một truy vấn demo.

### 15.3. COUNT và SUM có thể cộng từ các nhóm con, AVG thì không đơn giản như vậy

Ví dụ nếu một materialized view lưu theo ngày:

```sql
COUNT(*) AS paid_orders,
SUM(amount) AS paid_revenue,
AVG(amount) AS avg_order_amount
```

thì **trung bình của các AVG theo ngày** không nhất thiết bằng trung bình của mọi đơn, vì mỗi ngày có thể có số đơn khác nhau.

Để tính trung bình toàn tháng, nên lấy:

\[
AVG_{\text{tháng}}
=
\frac{\sum_{\text{ngày}} paid\_revenue}
     {\sum_{\text{ngày}} paid\_orders}
\]

khi số đơn ở mẫu đều có amount hợp lệ và mẫu số khác 0.

Nếu cột `amount` có thể `NULL`, mẫu số đúng cho `AVG(amount)` là **`COUNT(amount)`**, không phải `COUNT(*)`. Vì vậy, materialized view dùng cho báo cáo trung bình nên lưu cả **tổng** và **số giá trị không NULL** nếu cần tổng hợp tiếp.

### 15.4. Mất chiều lọc nếu không lưu trong grain

Nếu người dùng muốn lọc doanh thu theo `payment_method` nhưng materialized view chỉ lưu `(placed_on, shop_id)`, không thể khôi phục chính xác doanh thu từng phương thức từ tổng ngày–cửa hàng.

Có thể:

- Bổ sung `payment_method` vào `GROUP BY` và cột đầu ra.
- Tạo một materialized view khác cho nhu cầu báo cáo khác.
- Truy vấn bảng nguồn cho những bộ lọc chi tiết ít dùng.
- Duy trì bảng tổng hợp linh hoạt nếu yêu cầu cập nhật phức tạp.

Không nên thêm hàng chục chiều vào một materialized view chỉ để “có mọi bộ lọc”, vì số tổ hợp và kích thước lưu trữ có thể tăng nhanh.

## 16. Ghép materialized view với dữ liệu danh mục đang sống

Materialized view ở ví dụ chỉ lưu `shop_id`, không lưu `shop_name`. Ta có thể lấy tên mới nhất của cửa hàng bằng một JOIN lúc đọc:

```sql
SELECT
    m.placed_on,
    s.shop_name,
    m.paid_orders,
    m.paid_revenue
FROM demo_mv_317.mv_daily_paid_sales AS m
JOIN demo_mv_317.shops AS s
  ON s.shop_id = m.shop_id
ORDER BY m.placed_on, s.shop_name;
```

Giả sử đổi tên:

```sql
UPDATE demo_mv_317.shops
SET shop_name = 'Chi nhánh miền Bắc'
WHERE shop_id = 10;
```

Một câu `SELECT` mới từ truy vấn JOIN trên sẽ thấy **tên cửa hàng mới** theo snapshot giao dịch, dù không refresh materialized view, bởi tên được đọc **từ bảng `shops` tại thời điểm truy vấn**.

Nhưng số `paid_revenue` vẫn có thể cũ nếu `orders` đã thay đổi mà materialized view chưa được refresh.

### 16.1. Nếu đưa shop_name vào materialized view thì sao?

Ví dụ:

```sql
CREATE MATERIALIZED VIEW demo_mv_317.mv_daily_paid_with_name AS
SELECT
    v.placed_on,
    v.shop_id,
    s.shop_name,
    v.paid_orders,
    v.paid_revenue
FROM demo_mv_317.v_daily_paid_sales AS v
JOIN demo_mv_317.shops AS s
  ON s.shop_id = v.shop_id
WITH DATA;
```

Giờ cả doanh thu lẫn tên đều được lưu. Nếu đổi tên `shops.shop_name` lần nữa, tên đã vật hóa **không tự đổi** cho đến `REFRESH`.

Điều này cho thấy: **mỗi cột vật hóa đều có chính sách độ mới của chính materialized view**, trừ khi người đọc lấy cột đó từ bảng khác trong truy vấn ngoài.

### 16.2. Join ở bên ngoài có thể nhân hàng không?

Có. Nếu nối materialized view với một bảng dimension chứa **nhiều hàng trên cùng khóa**, mỗi hàng vật hóa có thể bị nhân lên.

Trong ví dụ, `shops.shop_id` là khóa chính, nên JOIN theo nó có tối đa một hàng khớp. Nếu bảng danh mục có nhiều phiên bản tên theo thời gian, cần nối theo điều kiện khoảng hiệu lực và đảm bảo **một bản ghi phù hợp mỗi khóa và thời điểm**, thay vì cộng tổng doanh thu đã bị nhân bản.

## 17. Materialized view và ngày không có giao dịch

Materialized view `mv_daily_paid_sales` chỉ chứa những cặp ngày–cửa hàng có ít nhất một đơn paid. Nó không tự tạo hàng cho:

- Ngày 02/08, shop 20 trước khi đơn 5 trở thành paid.
- Ngày 03/08, shop 10 chỉ có đơn cancelled.
- Những ngày hoàn toàn không có đơn.

Nếu dashboard yêu cầu **mọi ngày và mọi shop**, phải tạo **date spine** và tập shop, sau đó `LEFT JOIN` với kết quả đã tổng hợp.

### 17.1. Bù ngày khi truy vấn materialized view

```sql
WITH calendar AS (
    SELECT g.day_ts::date AS placed_on
    FROM generate_series(
        TIMESTAMP '2025-08-01',
        TIMESTAMP '2025-08-04',
        INTERVAL '1 day'
    ) AS g(day_ts)
)
SELECT
    c.placed_on,
    s.shop_id,
    s.shop_name,
    COALESCE(m.paid_orders, 0) AS paid_orders,
    COALESCE(m.paid_revenue, 0) AS paid_revenue
FROM calendar AS c
CROSS JOIN demo_mv_317.shops AS s
LEFT JOIN demo_mv_317.mv_daily_paid_sales AS m
    ON m.placed_on = c.placed_on
   AND m.shop_id = s.shop_id
ORDER BY c.placed_on, s.shop_id;
```

Trong mẫu này, `amount` của đơn được khai báo `NOT NULL` và chỉ cộng các đơn paid, nên `COALESCE` về 0 khi **không có nhóm paid** là một quy tắc hợp lý. Với dữ liệu có tiền chưa biết (`amount=NULL`), phải phân biệt **không có giao dịch** với **có giao dịch nhưng mọi amount đều NULL**; `COALESCE` không được dùng tùy tiện.

Vì có 4 ngày và 2 shop, truy vấn trả **8 hàng**. Với dữ liệu sau refresh của phần 9, ngày 03/08 shop 10 được điền 0 do chỉ có đơn cancelled.

### 17.2. Có nên vật hóa luôn toàn bộ các ngày trống?

Có thể vật hóa cả lưới ngày–shop, nhưng cần suy nghĩ về kích thước:

```text
365 ngày × 10.000 cửa hàng = 3.650.000 hàng/năm
```

Nếu dashboard chỉ hiển thị một shop trong một tuần, việc vật hóa sẵn mọi tổ hợp có thể lãng phí lưu trữ và tăng thời gian refresh.

Một hướng thường hợp lý là **vật hóa aggregate thưa** (chỉ những nhóm có dữ liệu), rồi dựng lịch và điền ngày trống ở lớp truy vấn/BI. Khi hệ thống yêu cầu số 0 cố định cho mọi đối tượng, lưới vật hóa phải giới hạn đúng phạm vi hoạt động của từng cửa hàng.

### 17.3. Bẫy lịch cố định trong định nghĩa materialized view

Nếu định nghĩa materialized view với `generate_series` chỉ tới `DATE '2025-08-04'`, dù refresh vào tháng 9, nó **không tự sinh ngày 05/08 trở đi**. Định nghĩa SQL cố định quyết định phạm vi dữ liệu mỗi lần refresh.

Có thể dùng bảng lịch đầy đủ được bảo trì hoặc xây dựng một phạm vi ngày tương ứng với yêu cầu nghiệp vụ. Tuy nhiên, ngay cả khi dùng `CURRENT_DATE` trong định nghĩa, materialized view chỉ nhận kết quả mới của biểu thức đó **khi refresh**, không phải mỗi lần `SELECT`.

## 18. View, materialized view, CTE, bảng tạm và bảng tổng hợp

Các cấu trúc này dễ bị gọi chung là “bảng trung gian”, nhưng thời gian sống và ngữ nghĩa khác nhau.

| Cấu trúc | Lưu dữ liệu riêng? | Sống qua nhiều query? | Nguồn thay đổi sẽ thế nào? | Khi phù hợp |
| --- | --- | --- | --- | --- |
| Ordinary view | Không lưu bộ kết quả vật lý | Có, lưu định nghĩa | Query mới xử lý từ nguồn | Tái sử dụng logic, dữ liệu mới |
| Materialized view | Có | Có | Dữ liệu đã lưu cũ tới khi refresh | Báo cáo nặng và chấp nhận trễ |
| CTE `WITH` | Chủ yếu phạm vi một statement | Không | Mỗi statement xử lý lại theo ngữ nghĩa optimizer | Chia nhỏ logic một truy vấn |
| Temporary table | Có, trong session hoặc transaction tùy quy tắc | Có trong phạm vi đời sống bảng tạm | Không tự theo nguồn | Pipeline nhiều bước trong một session |
| Permanent summary table | Có | Có | Cập nhật theo code/ETL/trigger riêng | Kiểm soát cập nhật incremental hoặc trạng thái đặc biệt |
| Application cache | Ngoài database hoặc trong tầng ứng dụng | Tùy TTL/chiến lược | Theo invalidate/refresh cache | Giảm tải, truy cập thường xuyên |

### 18.1. CTE MATERIALIZED không phải CREATE MATERIALIZED VIEW

PostgreSQL cho phép cấu trúc:

```sql
WITH paid AS MATERIALIZED (
    SELECT *
    FROM demo_mv_317.orders
    WHERE status = 'paid'
)
SELECT shop_id, SUM(amount)
FROM paid
GROUP BY shop_id;
```

Từ khóa `MATERIALIZED` ở đây là chỉ dẫn về cách xử lý một **CTE trong phạm vi một statement**. Nó **không tạo ra** một materialized view bền vững có thể truy vấn từ câu SQL khác và refresh sau này.

Đừng nhầm:

```sql
WITH paid AS MATERIALIZED (...)
```

với:

```sql
CREATE MATERIALIZED VIEW ... AS SELECT ...;
```

### 18.2. Temporary table không tự đồng bộ nguồn

```sql
CREATE TEMP TABLE tmp_daily_paid AS
SELECT
    placed_on,
    shop_id,
    SUM(amount) AS revenue
FROM demo_mv_317.orders
WHERE status = 'paid'
GROUP BY placed_on, shop_id;
```

Bảng tạm lưu kết quả tại lúc chạy. Nguồn đổi sau đó cũng **không tự cập nhật `tmp_daily_paid`**.

Khác biệt so với materialized view là cơ chế quản lý: bảng tạm thường chỉ hiện trong session và ứng dụng có thể trực tiếp `INSERT`/`UPDATE` nó. Materialized view là đối tượng có định nghĩa SELECT và lệnh refresh riêng.

### 18.3. Bảng summary tự duy trì

Giả sử pipeline quản lý bảng:

```sql
CREATE TABLE demo_mv_317.daily_paid_summary (
    placed_on DATE NOT NULL,
    shop_id INTEGER NOT NULL,
    paid_orders BIGINT NOT NULL,
    paid_revenue NUMERIC(14, 2) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (placed_on, shop_id)
);
```

Một pipeline có thể cập nhật bảng này sau khi chèn/sửa/hủy đơn, nhưng phải giải quyết đầy đủ:

- Thêm đơn paid vào nhóm ngày–shop.
- Sửa amount của một đơn paid.
- Đổi status từ paid sang pending hoặc ngược lại.
- Xóa/migrate một đơn sang ngày/shop khác.
- Retry và dữ liệu đến muộn.
- Nhiều writer cùng điều chỉnh một nhóm.
- Đối soát tổng với bảng nguồn.

Không nên chỉ viết `paid_revenue = paid_revenue + EXCLUDED.paid_revenue` trên mỗi lần nạp nếu sự kiện có thể gửi lại; như vậy cùng đơn sẽ được cộng nhiều lần. **Bảng summary tự duy trì đòi hỏi logic idempotency và giao dịch đúng**, không phải một phiên bản “materialized view nhưng nhanh hơn” miễn phí.

## 19. CREATE OR REPLACE VIEW và thay đổi định nghĩa vật hóa

### 19.1. Thay đổi ordinary view

Trong PostgreSQL, có thể dùng:

```sql
CREATE OR REPLACE VIEW demo_mv_317.v_daily_paid_sales AS
SELECT
    o.placed_on,
    o.shop_id,
    COUNT(*) AS paid_orders,
    SUM(o.amount) AS paid_revenue
FROM demo_mv_317.orders AS o
WHERE o.status = 'paid'
GROUP BY o.placed_on, o.shop_id;
```

Đây là cùng định nghĩa, chỉ minh họa `CREATE OR REPLACE VIEW`. Nếu muốn thay đổi danh sách cột, kiểu cột hoặc thứ tự cột, PostgreSQL có **các giới hạn tương thích** khi dùng `CREATE OR REPLACE VIEW`; không được tự giả định có thể thay đổi tự do như tạo mới.

Một view đang được ứng dụng sử dụng như giao diện SQL nên được quản lý qua migration có kiểm tra các đối tượng phụ thuộc.

### 19.2. REFRESH không đổi định nghĩa SQL

Nếu cần đổi từ “chỉ paid” sang “cả paid và pending”, câu:

```sql
REFRESH MATERIALIZED VIEW demo_mv_317.mv_daily_paid_sales;
```

**không tự đổi** định nghĩa từ điều kiện `WHERE status = 'paid'` sang một điều kiện khác. Nó chỉ chạy lại **định nghĩa hiện có**.

Khi `mv_daily_paid_sales` được tạo từ ordinary view, sửa định nghĩa ordinary view **có thể ảnh hưởng đến kết quả của lần refresh tiếp theo** nếu thay đổi được PostgreSQL cho phép và đối tượng phụ thuộc vẫn hợp lệ. Nhưng điều đó vẫn **không** thay đổi trực tiếp dữ liệu đã vật hóa cho tới refresh.

### 19.3. Không dùng CREATE OR REPLACE MATERIALIZED VIEW như view thường

PostgreSQL không cung cấp cú pháp `CREATE OR REPLACE MATERIALIZED VIEW` tương đương `CREATE OR REPLACE VIEW`. Khi cần thay cấu trúc định nghĩa MV, quy trình triển khai thường phải **tạo lại đối tượng** hoặc tạo materialized view mới rồi chuyển các truy vấn sang đối tượng mới có kiểm soát.

Cần tính tới:

- Phụ thuộc của view khác vào materialized view cũ.
- Index/unique index phải tạo lại trên đối tượng mới.
- Quyền truy cập được cấu hình lại.
- Thời gian nạp dữ liệu mới.
- Tác động đến dashboard đang đọc.
- Cơ chế chuyển đổi tên/phiên bản và rollback.

Không nên dùng `DROP MATERIALIZED VIEW ... CASCADE` tùy tiện trong production vì nó có thể xóa cả các đối tượng phụ thuộc.

## 20. Bảo mật và phân quyền

Ordinary view có thể giúp hạn chế những cột được hiển thị. Materialized view còn có thêm vấn đề: **dữ liệu đã được sao chép vật lý vào một đối tượng khác**.

### 20.1. Quyền đọc materialized view không nhất thiết giống quyền đọc nguồn

Nếu một vai trò được cấp `SELECT` trên materialized view, nó có thể đọc những hàng đã lưu trong materialized view dù người đó không được cấp trực tiếp quyền `SELECT` trên mọi bảng nguồn theo cùng cách.

Do đó, nếu bảng nguồn có dữ liệu nhạy cảm, hãy xem materialized view như **một bản sao dữ liệu cần phân quyền và kiểm toán riêng**. Không mặc định chính sách lọc hàng ở bảng nguồn sẽ được đánh giá lại cho mỗi hàng đã vật hóa mỗi khi có người đọc.

Ví dụ grant cho vai trò báo cáo **đã được tạo và quản lý bởi hệ thống**:

```sql
-- Vai trò reporting_reader cần tồn tại trước.
GRANT USAGE ON SCHEMA demo_mv_317 TO reporting_reader;

GRANT SELECT
ON demo_mv_317.mv_daily_paid_sales
TO reporting_reader;
```

Đây là ví dụ về cấu trúc quyền, **không phải bước bắt buộc** của bộ demo vì vai trò `reporting_reader` chưa được tạo. Một quyền `SELECT` trên MV không có nghĩa quyền xem bảng nguồn cũng được cấp.

### 20.2. View thông thường cũng cần cấu hình bảo mật đúng

PostgreSQL có nhiều đặc điểm về quyền, ownership, security barrier, cách kiểm tra quyền bảng nền và tùy chọn `security_invoker` ở các phiên bản hỗ trợ.

Ví dụ PostgreSQL 15+ có thể tạo view theo quyền của người gọi ở những tình huống phù hợp:

```sql
CREATE VIEW demo_mv_317.v_paid_orders_invoker
WITH (security_invoker = true) AS
SELECT order_id, shop_id, placed_on, amount
FROM demo_mv_317.orders
WHERE status = 'paid';
```

Khi sử dụng tùy chọn này, cần xác minh vai trò thực thi có quyền thích hợp trên bảng nền. Không coi view là hàng rào bảo mật tuyệt đối chỉ vì nó ẩn một cột khỏi danh sách SELECT.

Với yêu cầu row-level security, tenant isolation hoặc dữ liệu nhạy cảm, hãy thiết kế và thử quyền trên chính phiên bản PostgreSQL/DBMS đang vận hành.

### 20.3. Ai được refresh?

`REFRESH MATERIALIZED VIEW` là thao tác quản trị/cập nhật dữ liệu vật hóa. Quyền thực hiện phụ thuộc phiên bản PostgreSQL, ownership và những quyền cụ thể (ví dụ quyền `MAINTAIN` trong các phiên bản PostgreSQL hỗ trợ).

Không nên cấp khả năng refresh cho mọi tài khoản báo cáo chỉ vì họ cần `SELECT`. Một vai trò dịch vụ thực hiện job refresh có thể được quản trị riêng, với ghi log và cảnh báo.

### 20.4. Refresh không tự xóa dấu vết nhạy cảm ở nơi khác

Nếu dữ liệu cá nhân bị xóa ở bảng nguồn theo một yêu cầu hợp lệ, một materialized view chưa refresh có thể **tiếp tục giữ dữ liệu cũ**. Ngoài ra còn có backup, log, replica hoặc cache ứng dụng.

Khi dữ liệu cần xóa hoặc che giấu theo chính sách, phải tính cả **bản sao vật hóa** và quy trình refresh/invalidation, không chỉ đổi ở bảng nguồn.

## 21. Hiệu năng: đo đúng trước khi quyết định vật hóa

### 21.1. Đo truy vấn thường

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    placed_on,
    shop_id,
    paid_orders,
    paid_revenue
FROM demo_mv_317.v_daily_paid_sales
WHERE shop_id = 10
ORDER BY placed_on;
```

Trên PostgreSQL, có thể thấy các bước quét, lọc, aggregate hoặc sort được dùng để trả kết quả. Optimizer có thể gộp logic của view vào kế hoạch truy vấn bên ngoài.

### 21.2. Đo truy vấn materialized view

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    placed_on,
    shop_id,
    paid_orders,
    paid_revenue
FROM demo_mv_317.mv_daily_paid_sales
WHERE shop_id = 10
ORDER BY placed_on;
```

Truy vấn này thường có kế hoạch đọc **các hàng của MV**, không phải quét lại toàn bộ `orders` để tổng hợp ở mỗi lần đọc. Với bảng mẫu chỉ vài hàng, lợi thế có thể không rõ hoặc thậm chí không đáng kể.

`EXPLAIN ANALYZE` thực sự chạy câu truy vấn để đo. Hai ví dụ `SELECT` chỉ đọc, nhưng khi dùng trên production vẫn có tải CPU/I/O và thời gian giữ snapshot; cần cân nhắc.

### 21.3. Tổng chi phí không chỉ là độ trễ SELECT

Để đánh giá lựa chọn, xem ít nhất:

\[
C_{\text{ordinary}}
\approx
Q \times C_{\text{query nguồn}}
\]

\[
C_{\text{materialized}}
\approx
Q \times C_{\text{query MV}}
+
R \times C_{\text{refresh}}
+
C_{\text{lưu trữ/quản trị}}
\]

trong đó:

- `Q` là số lần người dùng truy vấn trong một khoảng.
- `R` là số lần refresh trong cùng khoảng.
- `C` là chi phí tương ứng (CPU, I/O, thời gian, tài nguyên).

Đây là mô hình trực giác, **không phải công thức chi phí chính xác của optimizer**. Nếu Q lớn và truy vấn nguồn tốn kém, vật hóa có thể đáng giá. Nếu dữ liệu đổi rất nhanh và R phải lớn, chi phí refresh có thể xóa lợi thế.

### 21.4. Tỷ lệ dữ liệu thay đổi và kích thước MV

Một báo cáo tổng hợp 100 triệu đơn thành 365 × 100 nhóm ngày–shop có thể tạo materialized view nhỏ hơn nhiều so với nguồn. Một materialized view lưu gần như toàn bộ chi tiết của 100 triệu đơn có thể vẫn rất lớn, dù có index.

Index, refresh và vacuum/maintenance phụ thuộc DBMS và cấu trúc. Chọn materialized view vì **đã xác định được các truy vấn nặng lặp lại**, không chỉ vì số hàng nguồn nghe lớn.

### 21.5. Một materialized view không tự được optimizer chọn để thay truy vấn nguồn

Trong PostgreSQL core, nếu ứng dụng vẫn viết:

```sql
SELECT SUM(amount)
FROM demo_mv_317.orders
WHERE status = 'paid';
```

hệ quản trị **không tự động bắt buộc chuyển** truy vấn này sang `mv_daily_paid_sales` chỉ vì đã tồn tại vật hóa tương đương. Muốn hưởng lợi của MV, ứng dụng thường phải **truy vấn trực tiếp materialized view** hoặc có một lớp truy cập định tuyến thích hợp.

Một số DBMS/kho dữ liệu có khả năng *query rewrite* dựa trên materialized view; không suy rộng cơ chế đó sang PostgreSQL mà chưa xác minh.

## 22. Triển khai và bảo trì trong production

Một thiết kế dùng materialized view cần nhiều hơn một lệnh `CREATE`.

### 22.1. Quy trình triển khai gợi ý

1. Xác định các truy vấn báo cáo lặp lại và **grain** cần lưu.
2. Xác nhận mức độ dữ liệu trễ tối đa được chấp nhận.
3. Thiết kế view hoặc truy vấn nguồn và kiểm soát `WHERE`/`JOIN`.
4. Tạo materialized view, nạp dữ liệu đầu tiên.
5. Tạo index theo mẫu truy vấn; nếu cần `CONCURRENTLY`, bảo đảm unique index hợp lệ.
6. Thiết lập quyền đọc và quyền refresh.
7. Triển khai job refresh theo lịch hoặc sau pipeline nạp nguồn.
8. Theo dõi thời gian refresh, thất bại, độ trễ và dung lượng.
9. Chỉ chuyển dashboard sang nguồn MV khi kết quả đối soát phù hợp và độ trễ chấp nhận được.
10. Chuẩn bị quy trình thay đổi schema, rebuild và rollback.

### 22.2. Job refresh nên có kiểm soát trùng lịch

Một job chạy theo phút có thể vẫn đang thực hiện thì lần kế tiếp tới hạn. Không nên để nhiều worker liên tục gửi refresh cùng MV rồi chờ tranh chấp không cần thiết.

Có thể dùng scheduler có cơ chế **không chạy chồng job**, hàng đợi hoặc khóa logic ở tầng điều phối. Nếu refresh lỗi, cần ghi nhận thất bại và retry với giới hạn phù hợp, tránh bão retry.

### 22.3. Chọn lúc refresh theo mốc dữ liệu đã nạp

Nếu pipeline nạp dữ liệu cửa hàng lúc 02:00 và hoàn tất lúc 02:20, refresh cố định lúc 02:05 có thể lấy dữ liệu chưa đủ. Trong trường hợp này, tốt hơn là kích hoạt refresh **sau khi pipeline đã xác nhận dữ liệu nạp thành công**, hoặc dựa vào một watermark nguồn đã đủ điều kiện.

Một materialized view có thể hoàn toàn nhất quán theo snapshot database lúc 02:05 nhưng vẫn thiếu phần dữ liệu nghiệp vụ chưa nạp xong. **Nhất quán transaction và đầy đủ dữ liệu nguồn không phải một khái niệm.**

### 22.4. Thời gian refresh không thay thế tuổi dữ liệu

Job refresh hoàn tất lúc 03:00 chưa đủ để kết luận dữ liệu nguồn bao phủ tới 03:00. Cần hiển thị và giám sát ít nhất:

- Mốc hoàn tất refresh.
- Watermark dữ liệu nguồn được bao phủ.
- Mức trễ hiện tại so với mục tiêu.
- Số lần refresh thất bại liên tiếp.
- Chi phí/thời lượng refresh.

Nếu độ trễ vượt ngưỡng, ứng dụng có thể gắn nhãn **dữ liệu cũ**, ẩn chỉ số nhạy thời gian hoặc chuyển sang truy vấn nguồn theo khả năng hệ thống.

## 23. Khác biệt giữa các DBMS

Không phải DBMS nào cũng có cùng câu `CREATE MATERIALIZED VIEW` hoặc chính sách refresh.

| Hệ quản trị | Khả năng liên quan | Điều cần nhớ |
| --- | --- | --- |
| **PostgreSQL** | `CREATE MATERIALIZED VIEW`; `REFRESH`; `REFRESH ... CONCURRENTLY` | Refresh không được lập lịch tự động trong core; `CONCURRENTLY` cần unique index thích hợp và MV đã populated |
| **Oracle Database** | Materialized views với nhiều chính sách refresh tùy định nghĩa và điều kiện | Có thể có complete/fast refresh, lịch làm mới hoặc query rewrite trong các tình huống được hỗ trợ |
| **SQL Server** | Indexed views (*view có index vật lý*) theo các điều kiện cụ thể | Cơ chế, giới hạn định nghĩa và chi phí duy trì index khác PostgreSQL materialized view |
| **MySQL** | Không có cơ chế `CREATE MATERIALIZED VIEW` gốc tương đương PostgreSQL trong MySQL thông dụng | Thường dùng summary table, scheduler/ETL hoặc cache |
| **SQLite** | Không có materialized view gốc theo cùng cú pháp | Dùng bảng tổng hợp hoặc snapshot do ứng dụng cập nhật |
| **Kho phân tích đám mây** | Một số có managed materialized views hoặc dynamic tables | Refresh, giới hạn truy vấn, tự động rewrite và phí tính toán phụ thuộc dịch vụ/phiên bản |

### 23.1. Oracle có thể quản lý refresh khác PostgreSQL

Oracle có các khả năng vật hóa chuyên dụng. Những khái niệm như *fast refresh* hoặc *on commit refresh* có điều kiện và giới hạn riêng; không thể sao chép nguyên cú pháp PostgreSQL sang Oracle, hoặc giả định mọi truy vấn Oracle đều hỗ trợ fast refresh.

### 23.2. SQL Server indexed view không giống một bản sao PostgreSQL REFRESH

SQL Server có thể vật hóa kết quả view bằng cách tạo unique clustered index nếu định nghĩa thỏa điều kiện của indexed view. Việc duy trì index có thể gắn với thay đổi dữ liệu nền, tạo ra khác biệt về **chi phí ghi** và **độ mới kết quả** so với chu kỳ `REFRESH MATERIALIZED VIEW` của PostgreSQL.

Cần kiểm tra các hạn chế SQL Server về `SCHEMABINDING`, aggregate, thuộc tính xác định và SET options, không mặc định view nào cũng có thể indexed.

### 23.3. Đừng chọn theo tên tính năng

Hai hệ có thể cùng gọi “materialized view” nhưng khác nhau ở:

- Tập cú pháp `SELECT` được cho phép.
- Có thể refresh incremental hay chỉ toàn bộ.
- Có lịch tự động hoặc refresh on commit không.
- Cách cập nhật đồng thời, lock và transaction.
- Hỗ trợ index và phân vùng.
- Cơ chế query rewrite, optimizer và chi phí vận hành.

Khi port hệ thống, hãy xác minh **hợp đồng ngữ nghĩa** trước khi dịch cú pháp.

## 24. Các lỗi thường gặp

| Lỗi hoặc suy luận sai | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Tạo VIEW là dữ liệu được cache” | Ordinary view lưu truy vấn, không lưu bộ kết quả riêng | Dùng materialized view/summary nếu cần tính sẵn |
| “Materialized view luôn hiện số liệu mới nhất” | Bảng nguồn thay đổi không tự kích hoạt refresh PostgreSQL | Thiết kế lịch và giám sát độ trễ |
| Quên `REFRESH` sau nạp dữ liệu | Dashboard đọc kết quả đã lưu cũ | Kích hoạt refresh sau pipeline hoặc theo lịch |
| Gọi `REFRESH CONCURRENTLY` khi chưa có unique index | PostgreSQL không cho chạy | Tạo unique index toàn phần trên cột đầu ra |
| Dùng partial/expression unique index làm điều kiện duy nhất cho CONCURRENTLY | Không đáp ứng yêu cầu unique index thích hợp | Dùng chỉ cột, không predicate, bao phủ mọi hàng |
| Dùng CONCURRENTLY trên MV `WITH NO DATA` | MV chưa populated | Refresh bình thường trước |
| Coi CONCURRENTLY là không tốn khóa/tài nguyên | Vẫn có chi phí và đồng bộ nội bộ | Đo và quản lý lịch refresh |
| Dựa vào thứ tự trả hàng sau CREATE/REFRESH | Không bảo đảm `SELECT` có thứ tự cố định | `ORDER BY` tại câu SELECT ngoài |
| Cộng doanh thu sau JOIN nhân hàng | Tổng bị tính lặp | Chọn grain và khóa nối phù hợp |
| Vật hóa theo tháng nhưng cần lọc theo từng ngày | Đã mất độ chi tiết cần thiết | Chọn grain theo nhu cầu |
| Lấy trung bình của các AVG ngày | Thiếu trọng số theo số quan sát | Lưu SUM và COUNT, tính ratio |
| `COALESCE(SUM(amount),0)` với tiền chưa biết | Nhầm NULL với 0 thật | Phân biệt nhóm rỗng và số liệu thiếu |
| Tin refresh đã xong nghĩa mọi nguồn hoàn tất | Dữ liệu có thể nhập trễ hoặc thiếu batch | Kiểm tra watermark nguồn và đối soát |
| Materialized view coi như snapshot lịch sử bất biến | Refresh có thể thay số cũ | Lưu snapshot/chốt báo cáo có version nếu cần |
| Sửa định nghĩa view rồi nghĩ MV đã đổi ngay | Dữ liệu MV chưa tự tái tính | Refresh và kiểm chứng dependency |
| Dùng `CREATE OR REPLACE MATERIALIZED VIEW` như ordinary view | PostgreSQL không có cú pháp tương đương | Migration/rebuild có kiểm soát |
| Grant SELECT trên MV mà quên dữ liệu nhạy cảm | MV lưu bản sao có quyền riêng | Quản trị grant, tenant/RLS và chính sách dữ liệu |
| Giữ lịch refresh dày hơn thời gian chạy | Refresh job tranh chấp, dồn lịch | Scheduler không chạy chồng, giám sát |
| Tạo index trên ordinary view PostgreSQL | View không lưu hàng vật lý riêng | Index trên bảng nguồn hoặc dùng MV |
| Truy vấn source rồi mong PG tự dùng MV | PG core không tự rewrite như giả định | Truy vấn MV trực tiếp |
| So sánh view với MV giữa các transaction đang ghi | Hai câu có thể thấy hai mốc khác nhau | Cùng snapshot/watermark và nguồn ổn định khi đối soát |

## 25. Bài tập thực hành kèm đáp án

Các bài bên dưới dùng schema `demo_mv_317` và trạng thái nguồn **sau phần 9**, trừ khi câu hỏi nêu mốc khác. Với bài yêu cầu quan sát dữ liệu trước refresh, hãy theo đúng thứ tự thao tác của phần liên quan.

### Bài 1 — Tên của hai loại view

Đối tượng `v_daily_paid_sales` và `mv_daily_paid_sales` khác nhau căn bản ở đâu?

**Đáp án:** Ordinary view lưu định nghĩa SELECT và truy vấn lại dữ liệu nguồn phù hợp; materialized view lưu cả tập hàng kết quả của lần tạo/refresh, nên có thể stale.

### Bài 2 — Số doanh thu ban đầu

Trước khi thêm đơn 11 và các thay đổi ở phần 9, tổng doanh thu paid là bao nhiêu?

**Đáp án:** **505** với 8 đơn paid, theo các nhóm 150, 80, 70, 130, 30 và 45.

### Bài 3 — Cùng SELECT, khác kết quả trước refresh

Sau khi chèn đơn 11 paid 25 vào shop 10 ngày 01/08 nhưng chưa refresh, ordinary view và MV cho doanh thu ngày đó bao nhiêu?

**Đáp án:** Ordinary view **175**, materialized view **150**. Mức chênh lệch 25 đúng bằng amount của đơn mới.

### Bài 4 — REFRESH làm thay đổi bảng nguồn không?

```sql
REFRESH MATERIALIZED VIEW demo_mv_317.mv_daily_paid_sales;
```

có tạo đơn mới hoặc cập nhật `orders` không?

**Đáp án:** Không. Nó thực thi lại truy vấn định nghĩa và cập nhật dữ liệu **lưu trong MV**, không chủ động sửa các hàng nguồn.

### Bài 5 — Kết quả sau bốn loại biến động

Sau `INSERT` đơn 11 (+25), tăng amount đơn 4 (+20), chuyển đơn 5 thành paid (+120) và xóa đơn 8 (−90), tổng doanh thu paid bằng bao nhiêu?

**Đáp án:** `505 + 25 + 20 + 120 - 90 = 580`. Có 9 đơn paid ở nguồn.

### Bài 6 — Nhóm mới xuất hiện ở đâu?

Trước khi đơn 5 được chuyển thành paid, có hàng ngày 02/08 shop 20 trong `v_daily_paid_sales` không?

**Đáp án:** Không, vì nhóm chỉ có đơn pending. Sau chuyển thành paid, có một hàng mới với `paid_orders=1`, `paid_revenue=120`; MV chỉ nhận hàng này sau refresh.

### Bài 7 — Tạo index để refresh concurrent

Viết index cho grain `(placed_on,shop_id)`:

```sql
CREATE UNIQUE INDEX uq_mv_daily_paid_sales_317
ON demo_mv_317.mv_daily_paid_sales (placed_on, shop_id);
```

**Đáp án:** Đây là unique index trên các cột đầu ra, không predicate, phù hợp với nhóm duy nhất theo ngày–shop và là điều kiện quan trọng cho `REFRESH ... CONCURRENTLY`.

### Bài 8 — REFRESH CONCURRENTLY trên MV mới tạo WITH NO DATA

Có được chạy ngay không?

**Đáp án:** Không. Cần nạp dữ liệu lần đầu bằng refresh không concurrent, rồi dùng `CONCURRENTLY` khi MV đã populated và có unique index hợp lệ.

### Bài 9 — Unique index một phần có đủ không?

```sql
CREATE UNIQUE INDEX uq_recent
ON demo_mv_317.mv_daily_paid_sales (placed_on, shop_id)
WHERE placed_on >= DATE '2025-08-01';
```

Nếu đây là unique index duy nhất, nó có đủ điều kiện cho CONCURRENTLY không?

**Đáp án:** Không. PostgreSQL đòi unique index bao phủ **mọi hàng**, không phải partial index.

### Bài 10 — WITH NO DATA có giống bảng rỗng không?

```sql
CREATE MATERIALIZED VIEW demo_mv_317.mv_empty_start AS
SELECT * FROM demo_mv_317.v_daily_paid_sales
WITH NO DATA;
```

Nếu SELECT ngay từ `mv_empty_start`, kết quả thế nào?

**Đáp án:** PostgreSQL báo materialized view **chưa populated**, thay vì trả một tập 0 hàng bình thường. Chạy `REFRESH MATERIALIZED VIEW demo_mv_317.mv_empty_start` rồi mới đọc.

### Bài 11 — Tính tổng tháng từ MV ngày

Dùng `SUM(paid_revenue)` theo `shop_id` trên `mv_daily_paid_sales` sau refresh cuối cùng. Hai giá trị là gì?

**Đáp án:** Shop 10 **295**, shop 20 **285**; tổng 580.

### Bài 12 — Có thể lấy doanh thu từng phương thức thanh toán không?

MV chỉ có `(placed_on,shop_id,paid_orders,paid_revenue)`. Người dùng muốn lọc theo `payment_method` không có trong nguồn kết quả. Có tính chính xác được từ MV hiện tại không?

**Đáp án:** Không. Phải lấy từ bảng nguồn hoặc thiết kế MV lưu thêm chiều phương thức thanh toán phù hợp.

### Bài 13 — Vì sao AVG(AVG(...)) thường sai?

Hai ngày có lần lượt 2 đơn tổng 150 và 1 đơn tổng 90. Trung bình đơn của từng ngày là 75 và 90. Lấy `(75+90)/2 = 82.5` có đúng AVG của cả ba đơn không?

**Đáp án:** Không. AVG chung = `(150+90)/(2+1)=80`. Phải dùng tổng tiền chia tổng số giá trị hợp lệ, không lấy trung bình đơn giản của trung bình ngày.

### Bài 14 — Bù ngày không có giao dịch

Nếu ngày 03/08 shop 10 chỉ có đơn cancelled, tại sao MV ngày–shop không có hàng? Muốn biểu đồ hiển thị 0 thì làm gì?

**Đáp án:** Truy vấn định nghĩa chỉ `WHERE status='paid'`, nên không có nhóm cho shop đó. Tạo date spine × shops, rồi `LEFT JOIN` với MV; `COALESCE` thành 0 nếu có quy tắc xác nhận không có paid nghĩa là doanh thu 0.

### Bài 15 — Đổi tên shop có cần refresh MV không?

MV lưu `shop_id`, còn tên lấy bằng JOIN trực tiếp bảng `shops` khi SELECT. Đổi tên shop thì cần refresh để thấy tên mới không?

**Đáp án:** Không, vì tên không được vật hóa trong MV này. Nhưng nếu `shop_name` nằm trong các cột của MV, cần refresh để bản lưu nhận tên mới.

### Bài 16 — Dữ liệu nguồn mới nhưng snapshot của reader cũ

Một transaction `REPEATABLE READ` đã đọc trước khi writer commit. Truy vấn ordinary view tiếp theo có chắc thấy dữ liệu mới không?

**Đáp án:** Không. Snapshot transaction có thể cố định ở thời điểm trước. “Ordinary view đọc dữ liệu hiện tại” phải hiểu theo **snapshot và isolation của query**, không có nghĩa vượt qua quy tắc MVCC.

### Bài 17 — Materialized view có tự dùng thay query nguồn không?

Ứng dụng tiếp tục `SELECT SUM(amount) FROM demo_mv_317.orders WHERE status='paid'`. Chỉ vì có MV, PostgreSQL core có bắt buộc tự chuyển truy vấn này sang MV không?

**Đáp án:** Không. Ứng dụng thường phải truy vấn MV trực tiếp hoặc dùng một lớp định tuyến/viết lại riêng.

### Bài 18 — Materialized view là bản lưu vĩnh viễn của số liệu cuối tháng?

**Đáp án:** Không. `REFRESH` có thể thay đổi số của tháng trước nếu giao dịch nguồn bị điều chỉnh. Muốn dữ liệu chốt bất biến phải thiết kế snapshot có version hoặc quy trình đóng sổ.

### Bài 19 — READ quyền nguồn khác quyền MV

Một user không được quyền đọc bảng `orders` nhưng được cấp `SELECT` trên MV có chứa doanh thu từ orders. Có thể user đọc MV không?

**Đáp án:** Có thể, tùy quyền trên MV và các đối tượng liên quan. Không mặc định chính sách quyền/RLS của bảng nguồn được kiểm tra lại y hệt cho từng hàng vật hóa. Phải bảo vệ MV như một tập dữ liệu riêng.

### Bài 20 — Khi nào nên chọn ordinary view?

Một API cần trả giá trị tồn kho ngay sau mỗi commit và truy vấn từ bảng nguồn đã nhanh. Materialized view refresh mỗi 15 phút có phù hợp không?

**Đáp án:** Thường không phù hợp nếu yêu cầu thật là ngay sau commit. Ordinary view hoặc truy vấn trực tiếp nguồn tốt hơn vì materialized view có thể trễ 15 phút hoặc hơn khi job thất bại.

### Bài 21 — Nếu refresh job chậm hơn lịch chạy?

Job được gọi mỗi 1 phút nhưng refresh mất 4 phút. Rủi ro là gì?

**Đáp án:** Các lượt làm mới có thể tranh chấp/chờ, gây tải hoặc backlog. Cần điều phối không chồng job, theo dõi thời lượng và chọn lịch phù hợp.

### Bài 22 — Tạo index trên ordinary view

`CREATE INDEX ... ON demo_mv_317.v_daily_paid_sales (...)` có hợp lệ trong PostgreSQL không?

**Đáp án:** Không. Index thông thường phải nằm trên quan hệ có dữ liệu vật lý phù hợp; có thể index bảng `orders` hoặc tạo index trên materialized view.

### Bài 23 — CTE MATERIALIZED có bằng materialized view không?

```sql
WITH s AS MATERIALIZED (
    SELECT * FROM demo_mv_317.orders WHERE status = 'paid'
)
SELECT COUNT(*) FROM s;
```

sau khi statement kết thúc có thể gọi `REFRESH MATERIALIZED VIEW s` không?

**Đáp án:** Không. `MATERIALIZED` của CTE là cách xử lý trong một statement; nó không tạo materialized view có tên `s` được lưu qua các query.

### Bài 24 — Chọn giải pháp cho báo cáo cuối ngày

Báo cáo chạy nhiều lần trong ngày, nguồn có hàng triệu đơn và hệ thống chấp nhận chỉ cập nhật sau pipeline chốt ngày. Nên cân nhắc cấu trúc nào?

**Đáp án gợi ý:** Materialized view doanh thu theo ngày/khu vực với index thích hợp, refresh sau khi pipeline hoàn thành và kiểm tra watermark. Nếu cần incremental rất sát thời gian thực, cân nhắc bảng summary được duy trì có kiểm soát.

## 26. Checklist lựa chọn materialized view

1. **Câu hỏi nghiệp vụ là gì?** Cần dữ liệu mới sau mỗi commit hay chấp nhận một bản kết quả đã chốt?
2. **Truy vấn gốc có thật sự nặng không?** Đo trên dữ liệu đại diện, không đo bằng cảm giác.
3. **Ordinary view có đủ chưa?** View có thể đóng gói logic mà không tăng chi phí vật hóa.
4. **Grain vật hóa là gì?** Ngày–shop, tháng–shop hay thêm chiều khác?
5. **Đã bảo vệ các phép JOIN và tổng hợp khỏi nhân hàng chưa?**
6. **Những bộ lọc người dùng cần có thể suy ra từ các cột MV không?**
7. **SUM/COUNT/AVG được tổng hợp tiếp đúng ngữ nghĩa không?** Đặc biệt là `NULL` và trung bình có trọng số.
8. **Materialized view đã populated chưa?** `WITH NO DATA` chưa sẵn sàng SELECT.
9. **Có cần truy vấn liên tục trong lúc refresh không?** Nếu có, cân nhắc `CONCURRENTLY` và điều kiện unique index.
10. **Index trên MV có hỗ trợ đường đọc phổ biến không?**
11. **Nguồn thay đổi theo lịch nào?** Refresh sau batch hay theo thời gian?
12. **Độ trễ tối đa được phép bao nhiêu?** Có hiển thị as-of/watermark không?
13. **Refresh thất bại thì xử lý thế nào?** Cảnh báo, retry, dùng bản cũ hay chuyển truy vấn nguồn?
14. **Có nhiều công việc refresh chạy chồng không?** Cần điều phối và giám sát.
15. **Quyền xem và refresh được phân tách chưa?** MV chứa bản sao dữ liệu cần bảo vệ.
16. **Dữ liệu phải xóa/ẩn theo chính sách có được xử lý ở bản vật hóa không?**
17. **Có kế hoạch đổi schema và rebuild không?** Index, quyền và dependency có thể cần dựng lại.
18. **Có đối soát giữa nguồn và MV trên một watermark/snapshot phù hợp không?**
19. **Kích thước dữ liệu đã lưu và chi phí refresh có hợp lý không?**
20. **DBMS có cùng ngữ nghĩa materialized view như ví dụ không?** Cần kiểm tra theo engine/phiên bản.

## 27. Dọn dẹp dữ liệu thử nghiệm

Khi không còn cần bộ ví dụ, trên **đúng database sandbox** đã dùng để tạo schema:

```sql
DROP SCHEMA demo_mv_317 CASCADE;
```

**Cảnh báo:** `CASCADE` xóa toàn bộ đối tượng phụ thuộc trong schema thử nghiệm, bao gồm bảng, ordinary view, materialized view và index. Chỉ chạy khi chắc chắn schema `demo_mv_317` được tạo riêng cho bài học, không chứa dữ liệu hay đối tượng của người khác.

Nếu muốn giữ dữ liệu để chạy lại bài sau, không cần xóa. Khi chạy lại từ đầu, nên dùng database/schema sandbox mới hoặc chủ động dọn đúng đối tượng mẫu thay vì áp dụng `DROP ... CASCADE` cho một schema đang được dùng chung.

## 28. Tổng kết

**View thông thường lưu logic của một truy vấn; materialized view lưu bộ kết quả đã tính từ logic đó.** Sự khác biệt này dẫn tới hai mô hình dùng dữ liệu:

- Với ordinary view, câu truy vấn mới xử lý dữ liệu nguồn theo snapshot hiện hành, thích hợp khi cần dữ liệu mới và muốn tái sử dụng logic.
- Với materialized view, câu truy vấn mới đọc kết quả đã lưu, có thể giảm chi phí đọc lặp lại nhưng phải chấp nhận quản lý độ mới, lịch refresh, index, quyền, dung lượng và tác động khi dữ liệu nguồn thay đổi.

Trong PostgreSQL, `REFRESH MATERIALIZED VIEW` là thao tác cập nhật kết quả lưu sẵn; `REFRESH MATERIALIZED VIEW CONCURRENTLY` giúp tiếp tục phục vụ truy vấn đọc trong lúc làm mới nhưng đòi hỏi materialized view đã populated và một unique index hợp lệ trên các cột đầu ra.

Chọn materialized view khi **lợi ích tính trước được chứng minh, grain phục vụ đúng báo cáo và độ trễ được quản trị rõ ràng**. Nếu dữ liệu phải luôn mới hoặc phép đo cần cập nhật theo sự kiện với quy tắc phức tạp, ordinary view hoặc bảng tổng hợp do pipeline duy trì có thể phù hợp hơn.


