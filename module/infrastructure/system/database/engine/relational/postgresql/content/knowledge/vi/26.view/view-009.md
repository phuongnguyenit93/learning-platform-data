# Lựa chọn view, materialized view hoặc bảng tổng hợp trong PostgreSQL

Giả sử ứng dụng quản lý đơn hàng cần cung cấp báo cáo **doanh thu đã thanh toán theo ngày và theo tenant**. Có ba hướng thiết kế phổ biến:

1. Tạo một **view** chứa câu SQL tổng hợp. Mỗi lần đọc báo cáo, PostgreSQL thực hiện truy vấn trên dữ liệu nguồn theo cơ chế lập kế hoạch và snapshot hiện tại.
2. Tạo một **materialized view** lưu sẵn kết quả. Truy vấn báo cáo đọc dữ liệu đã được tính trước, nhưng kết quả **không tự đổi** khi đơn hàng nguồn được thêm hoặc sửa; phải có `REFRESH MATERIALIZED VIEW`.
3. Tạo một **bảng tổng hợp** (*summary/aggregate table*) với khóa theo ngày và tenant. Một job, transaction, trigger hoặc pipeline sự kiện chủ động cập nhật từng nhóm tổng hợp; đổi lại hệ thống phải tự bảo đảm tính đúng đắn, đồng bộ và khả năng khôi phục.

Ba lựa chọn đều có thể trả về những cột giống nhau:

```text
tenant_id | sales_day  | paid_orders | gross_amount
----------+------------+-------------+-------------
        1 | 2026-11-01 |           2 |       200.00
        1 | 2026-11-02 |           1 |        50.00
        2 | 2026-11-01 |           1 |        90.00
```

Nhưng chúng **không có cùng hợp đồng vận hành**.

```text
                       orders (bảng nguồn)
                               |
                +--------------+--------------+
                |              |              |
                v              v              v
           SQL VIEW      MATERIALIZED VIEW  SUMMARY TABLE
                |              |              |
         Tính khi đọc    Tính khi REFRESH   Tính theo sự kiện/
                |              |            job/transaction
                v              v              v
         Kết quả theo   Snapshot đã lưu    Số liệu do pipeline
         snapshot query  có thể bị cũ       tự duy trì
                |              |              |
                +--------------+--------------+
                               |
                       API / Dashboard
```

Bài thuộc chương **View** trong module *Database Engine Relational PostgreSQL*. Mục tiêu không chỉ là nhớ cú pháp `CREATE VIEW` và `CREATE MATERIALIZED VIEW`, mà là **chọn kiến trúc phù hợp** với khối lượng dữ liệu, yêu cầu độ mới, chi phí vận hành và tính chính xác nghiệp vụ.

Sau bài học, bạn có thể:

- Phân biệt nơi thực thi và nơi lưu dữ liệu của view, materialized view, bảng tổng hợp.
- Thiết kế đúng **grain** (*mức hạt*) của một báo cáo theo tenant/ngày.
- Dùng cùng một dataset để tạo cả ba dạng và chứng minh sự khác biệt sau INSERT/UPDATE.
- Hiểu `REFRESH MATERIALIZED VIEW`, `CONCURRENTLY`, yêu cầu unique index và giới hạn của refresh toàn phần.
- Thiết kế bảng tổng hợp với `PRIMARY KEY`, `INSERT ... ON CONFLICT DO UPDATE` và cơ chế tránh cộng trùng.
- Xử lý dữ liệu đến muộn, hoàn tiền, sửa ngày/tenant, xóa và backfill.
- Đặt mục tiêu freshness có thể đo và biết khi nào cần chuyển đổi kiến trúc.
- Đánh giá query plan, index, storage, lock, write amplification, quyền/RLS và chi phí bảo trì.

> **An toàn:** Toàn bộ ví dụ thực hành dùng schema riêng `view_choice_lab` trong database thử nghiệm. Không tạo lại hoặc xóa schema đang chứa dữ liệu của người khác. Các lệnh `REFRESH` và `UPDATE` trong bài thực sự thay đổi dữ liệu/quan hệ; hãy thực hiện trong môi trường lab. `EXPLAIN (ANALYZE)` với DML cũng **thực thi DML thật**.

---

## 1. Hiểu đúng ba khái niệm

### 1.1. View thông thường: định nghĩa truy vấn, không lưu bản sao dữ liệu

```sql
CREATE VIEW reporting.v_daily_sales AS
SELECT ...
FROM orders
GROUP BY ...;
```

View thông thường lưu **định nghĩa SQL**. Khi người dùng SELECT từ view, PostgreSQL xử lý truy vấn có tham chiếu các bảng nguồn và đưa ra kế hoạch thực thi tương ứng.

Một view **không mặc nhiên cache kết quả**:

```sql
SELECT *
FROM reporting.v_daily_sales;
```

Nếu `orders` vừa có một giao dịch committed làm thay đổi dữ liệu, truy vấn mới với snapshot có thể nhìn thấy thay đổi đó.

**Điều cần nhớ:** View là một lớp trừu tượng logic, **không phải “bảng đã chạy sẵn SELECT”**.

### 1.2. Materialized view: kết quả truy vấn được lưu thành dữ liệu

```sql
CREATE MATERIALIZED VIEW reporting.mv_daily_sales AS
SELECT ...
FROM orders
GROUP BY ...;
```

PostgreSQL tạo một relation chứa kết quả tại thời điểm khởi tạo/refresh. Khi query materialized view, hệ thống đọc dữ liệu **đã materialize**, thay vì phải tính lại toàn bộ GROUP BY trên bảng nguồn cho mỗi SELECT.

Đổi lại:

```text
INSERT INTO orders ... COMMIT
           |
           +--> VIEW: truy vấn mới có thể thấy ngay
           |
           +--> MATERIALIZED VIEW: vẫn giữ kết quả cũ
                        |
                   REFRESH
                        |
                        v
                  kết quả mới
```

Materialized view **không tự refresh** khi bảng nguồn đổi. PostgreSQL lõi cũng không mặc định có cơ chế **incremental materialized view maintenance** tổng quát cho mọi SELECT định nghĩa.

### 1.3. Bảng tổng hợp: một bảng thật với quy trình tính số liệu riêng

```sql
CREATE TABLE reporting.daily_sales_summary (
    tenant_id INTEGER NOT NULL,
    sales_day DATE NOT NULL,
    paid_orders BIGINT NOT NULL,
    gross_amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (tenant_id, sales_day)
);
```

Đây là **bảng thông thường**. PostgreSQL không biết rằng các cột trong nó phải luôn bằng kết quả GROUP BY từ `orders`; ứng dụng hoặc pipeline phải thực hiện điều đó.

Lợi ích:

- Có thể áp dụng các delta nhỏ, không tính lại lịch sử mỗi lần.
- Có thể lưu thêm watermark, revision, trạng thái kiểm soát và metadata.
- Có thể cập nhật một số nhóm tổng hợp ngay trong cùng transaction với dữ liệu nguồn.
- Có thể phục vụ báo cáo độ trễ thấp với khóa chính/index rõ ràng.

Giá phải trả:

- Logic **tạo, sửa, bù trừ và chống cộng trùng** phải do hệ thống thiết kế.
- Pipeline lỗi có thể làm sai số liệu mà PostgreSQL không tự biết.
- Cần đối soát định kỳ với dữ liệu gốc.

### 1.4. Một bảng so sánh nhanh

| Tiêu chí | View | Materialized view | Bảng tổng hợp |
|---|---|---|---|
| Có lưu kết quả tổng hợp riêng? | Không | Có | Có |
| Tự thấy thay đổi nguồn ở query mới? | Theo snapshot/MVCC | Không, cần `REFRESH` | Chỉ khi pipeline cập nhật |
| Chi phí SELECT báo cáo | Có thể cao | Thường thấp sau refresh | Thường thấp nếu thiết kế đúng grain/index |
| Chi phí cập nhật dữ liệu báo cáo | Không cần bảo trì kết quả | Refresh định kỳ, thường tính lại toàn bộ | Theo từng delta/batch hoặc rebuild |
| Khả năng index kết quả tổng hợp | Không index trực tiếp trên view | Có thể tạo index | Có thể tạo index |
| Logic đồng bộ phải tự viết | Không | Lịch refresh, giám sát lỗi | Có, thường phức tạp nhất |
| Kiểm soát dữ liệu bị cũ | Theo snapshot, replica/cache | Theo lần refresh gần nhất | Theo pipeline/watermark |
| Hỗ trợ UPDATE trực tiếp | Một số view đơn giản | Không dùng như bảng DML thông thường | Có |
| Phù hợp | Dữ liệu vừa, truy vấn không quá đắt, cần mới | Đọc lặp lại nhiều, chấp nhận staleness | Báo cáo lớn, cập nhật liên tục, SLA freshness chặt |

Không có một phương án “nhanh nhất” cho mọi trường hợp. **Mức hạt báo cáo, số lần đọc, số lần ghi và độ mới chấp nhận được** mới quyết định lựa chọn.

---

## 2. Bài toán mẫu: doanh thu đã thanh toán theo ngày UTC

Chúng ta thống nhất định nghĩa nghiệp vụ trước khi viết SQL:

- Mỗi hàng nguồn là **một đơn hàng**.
- `status='paid'` được tính vào doanh thu; `cancelled` và `refunded` không được tính.
- `amount` là giá trị tiền **theo một đơn vị tiền tệ đã thống nhất** trong lab. Trong production nhiều currency, **không cộng trộn các currency**; thêm `currency` vào grain hoặc quy đổi theo quy tắc có kiểm soát.
- Một ngày báo cáo được tính theo **UTC**, không phụ thuộc `TimeZone` của session.
- Mỗi hàng kết quả biểu diễn **một tenant trong một ngày UTC**.
- `paid_orders` là số đơn paid; `gross_amount` là tổng `amount` của các đơn paid.

Nếu nghiệp vụ cho phép partial refund, nhiều lần thanh toán hoặc các dòng sản phẩm, mô hình mẫu này cần mở rộng. Không nên đồng nhất `status='paid'` với một mô hình doanh thu tài chính đầy đủ.

### 2.1. Grain là gì?

**Grain** trả lời: “Một hàng báo cáo là gì?”

```text
Grain của đơn hàng nguồn:
    1 hàng = 1 order_id

Grain của báo cáo:
    1 hàng = (tenant_id, sales_day UTC)
```

Grain quyết định khóa duy nhất của materialized view và bảng tổng hợp:

```sql
(tenant_id, sales_day)
```

Nếu bổ sung `currency`, `region` hoặc `product_category` vào báo cáo, phải xem lại grain và khóa tương ứng; không thêm cột vào GROUP BY mà quên thay unique index/PRIMARY KEY.

### 2.2. Vì sao dùng khoảng UTC rõ ràng?

`ordered_at` sẽ là `TIMESTAMPTZ`. Ta định nghĩa ngày UTC:

```sql
(ordered_at AT TIME ZONE 'UTC')::date
```

`AT TIME ZONE 'UTC'` tạo timestamp theo giờ UTC trước khi lấy `date`. Điều này khác với `ordered_at::date`, có thể phụ thuộc `TimeZone` của session.

Nếu yêu cầu là **ngày theo giờ Việt Nam**, phải thay quy tắc bằng `Asia/Ho_Chi_Minh` ở **tất cả** view, materialized view, summary table và pipeline delta. Đừng có view tính ngày UTC nhưng summary table lại dùng ngày theo session.

---

## 3. Tạo phòng thực hành

### 3.1. Kiểm tra database

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Không tạo dữ liệu mẫu trong schema production. Ví dụ này giả sử schema `view_choice_lab` chưa tồn tại.

### 3.2. Tạo bảng nguồn

```sql
CREATE SCHEMA view_choice_lab;

CREATE TABLE view_choice_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('paid', 'cancelled', 'refunded')),
    amount NUMERIC(12,2) NOT NULL
        CHECK (amount >= 0)
);
```

Giới hạn ví dụ:

- Không có bảng payment/refund riêng.
- Không có currency vì lab giả định một đồng tiền thống nhất.
- `order_id` là identity; ID được cấp khi INSERT, không nên coi nó là khóa thời gian.
- Các transaction trên đơn hàng phải tuân thủ constraint.

### 3.3. Nạp sáu đơn hàng xác định

```sql
INSERT INTO view_choice_lab.orders
    (tenant_id, ordered_at, status, amount)
VALUES
    (1, '2026-11-01 02:00:00+00', 'paid',      120.00),
    (1, '2026-11-01 03:00:00+00', 'paid',       80.00),
    (1, '2026-11-02 08:00:00+00', 'paid',       50.00),
    (1, '2026-11-01 10:00:00+00', 'cancelled',  20.00),
    (2, '2026-11-01 12:00:00+00', 'paid',       90.00),
    (2, '2026-11-02 15:00:00+00', 'refunded',   40.00);
```

### 3.4. Xác nhận dữ liệu

```sql
SELECT
    order_id,
    tenant_id,
    ordered_at,
    status,
    amount
FROM view_choice_lab.orders
ORDER BY order_id;
```

Với schema mới và một lần INSERT theo thứ tự trên, identity thường cấp `order_id` từ 1 đến 6. Không dựa vào ID cụ thể khi tái chạy lab đã có dữ liệu.

### 3.5. Kết quả báo cáo mong đợi

| tenant_id | sales_day | paid_orders | gross_amount |
|---:|---|---:|---:|
| 1 | 2026-11-01 | 2 | 200.00 |
| 1 | 2026-11-02 | 1 | 50.00 |
| 2 | 2026-11-01 | 1 | 90.00 |

Đơn cancelled 20.00 và refunded 40.00 không được tính. Nhóm tenant 2 ngày 2026-11-02 không có đơn paid, nên **không sinh hàng** trong kết quả GROUP BY này. Đây là quy ước quan trọng khi so sánh với bảng tổng hợp có thể giữ hàng 0.

---

## 4. Phương án A — VIEW: luôn tính từ nguồn khi truy vấn

### 4.1. Tạo view báo cáo

```sql
CREATE VIEW view_choice_lab.v_daily_sales AS
SELECT
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date AS sales_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS gross_amount
FROM view_choice_lab.orders
WHERE status = 'paid'
GROUP BY
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date;
```

Ta không cần tạo bảng dữ liệu kết quả: chỉ tạo một định nghĩa SQL.

### 4.2. Truy vấn view

```sql
SELECT
    tenant_id,
    sales_day,
    paid_orders,
    gross_amount
FROM view_choice_lab.v_daily_sales
ORDER BY tenant_id, sales_day;
```

Kết quả tương ứng bảng ở mục 3.

### 4.3. PostgreSQL làm gì khi đọc?

View được mở rộng thông qua cơ chế xử lý truy vấn của PostgreSQL. Planner có thể:

- Quét bảng `orders`.
- Dùng index thích hợp nếu predicate và thống kê cho phép.
- Áp `WHERE status='paid'`.
- Tính ngày UTC từ `ordered_at`.
- Gom nhóm bằng `HashAggregate` hoặc `GroupAggregate`.
- Áp những điều kiện/order ở truy vấn ngoài theo kế hoạch tương ứng.

Không có một table riêng tên `v_daily_sales` chứa ba rows vật lý cần được duy trì.

### 4.4. Đọc view và tính “mới nhất” theo MVCC

Một SELECT mới ở isolation `READ COMMITTED` thường dùng snapshot của statement mới nhất, thấy những giao dịch nguồn đã commit trước snapshot đó. Nhưng:

- Transaction `REPEATABLE READ` có thể tiếp tục thấy snapshot cũ trong cùng giao dịch.
- Đọc từ read replica có thể trễ replication.
- Ứng dụng có thể cache response.
- Một ghi đang chưa commit không xuất hiện.

Vì vậy nói “VIEW luôn realtime tuyệt đối” là không chính xác. Đúng hơn: **view không giữ riêng bản tổng hợp cũ; dữ liệu đọc chịu quy tắc snapshot của database**.

### 4.5. View thường thích hợp khi nào?

- Bảng nguồn chưa quá lớn hoặc truy vấn GROUP BY đã đủ nhanh.
- Báo cáo có nhiều tham số lọc linh hoạt khó materialize mọi tổ hợp.
- Cần phản ánh trạng thái nguồn theo snapshot mới.
- Muốn tập trung logic SQL tại database.
- Không muốn vận hành refresh scheduler hoặc delta pipeline.
- Tần suất đọc thấp hơn hoặc vừa phải so với lượng dữ liệu.

### 4.6. View không tự làm query rẻ đi

Nếu báo cáo mỗi 2 giây phải scan 300 triệu đơn hàng và GROUP BY, tạo view **không loại bỏ công việc GROUP BY**. Nó chỉ giúp tái sử dụng SQL và đơn giản hóa quyền/interface.

Đừng dùng view như một “cache miễn phí”.

---

## 5. Phương án B — MATERIALIZED VIEW: lưu snapshot của kết quả

### 5.1. Tạo materialized view

```sql
CREATE MATERIALIZED VIEW view_choice_lab.mv_daily_sales AS
SELECT
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date AS sales_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS gross_amount
FROM view_choice_lab.orders
WHERE status = 'paid'
GROUP BY
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date
WITH DATA;
```

`WITH DATA` yêu cầu thực hiện truy vấn và lưu kết quả ban đầu. Đây cũng là hành vi mặc định trong những cú pháp tạo materialized view tương ứng, nhưng ghi tường minh giúp người học thấy điểm khác với `WITH NO DATA`.

### 5.2. Đọc kết quả đã được lưu

```sql
SELECT
    tenant_id,
    sales_day,
    paid_orders,
    gross_amount
FROM view_choice_lab.mv_daily_sales
ORDER BY tenant_id, sales_day;
```

Lúc này materialized view có cùng ba hàng như view thông thường, nhưng **những hàng ấy đã được lưu vật lý**.

### 5.3. Materialized view có thể có index

```sql
CREATE UNIQUE INDEX mv_daily_sales_tenant_day_uidx
ON view_choice_lab.mv_daily_sales (tenant_id, sales_day);
```

Unique index này phù hợp vì kết quả đã GROUP BY đúng `tenant_id, sales_day`, mỗi cặp chỉ một hàng.

Lợi ích:

- Query `WHERE tenant_id=... AND sales_day=...` có thể tra cứu hẹp.
- Index bao phủ **tất cả rows** và chỉ dùng **tên cột thông thường**.
- Đáp ứng yêu cầu then chốt của `REFRESH MATERIALIZED VIEW CONCURRENTLY` (khi vật thể đã populated).

Không cần cùng một index trên source `orders` để query matview nhanh; nguồn và matview là **hai quan hệ** có storage/index riêng.

### 5.4. Materialized view không được cập nhật như bảng tổng hợp

Không dùng:

```sql
-- Không phải thao tác DML thông thường được hỗ trợ trên matview:
-- UPDATE view_choice_lab.mv_daily_sales
-- SET gross_amount = 100
-- WHERE tenant_id = 1;
```

Muốn thay kết quả, cập nhật **bảng nguồn** rồi `REFRESH MATERIALIZED VIEW`. Materialized view không phải bảng tự do để UPSERT từng row theo cách summary table.

### 5.5. Vòng đời của một matview

```text
CREATE MATERIALIZED VIEW ... WITH DATA
       |
       v
Kết quả được lưu ở thời điểm tạo
       |
       v
Nguồn thay đổi, matview vẫn giữ giá trị cũ
       |
       v
REFRESH MATERIALIZED VIEW
       |
       v
Kết quả được tính lại theo snapshot của refresh
       |
       v
Các SELECT tiếp theo thấy dữ liệu mới khi refresh hoàn tất
```

---

## 6. Phương án C — Bảng tổng hợp: tự duy trì theo grain

### 6.1. Tạo bảng tổng hợp

```sql
CREATE TABLE view_choice_lab.daily_sales_summary (
    tenant_id INTEGER NOT NULL,
    sales_day DATE NOT NULL,
    paid_orders BIGINT NOT NULL DEFAULT 0
        CHECK (paid_orders >= 0),
    gross_amount NUMERIC(18,2) NOT NULL DEFAULT 0
        CHECK (gross_amount >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, sales_day)
);
```

Cột `updated_at` ở đây biểu thị **lần cập nhật gần nhất của một nhóm**, không mặc nhiên là watermark chứng minh toàn bộ nguồn đã đồng bộ đến một thời điểm.

### 6.2. Bootstrap từ query chuẩn

```sql
INSERT INTO view_choice_lab.daily_sales_summary
    (tenant_id, sales_day, paid_orders, gross_amount)
SELECT
    tenant_id,
    sales_day,
    paid_orders,
    gross_amount
FROM view_choice_lab.v_daily_sales;
```

Giờ view, materialized view và summary table đều có cùng ba hàng.

### 6.3. Đọc bảng tổng hợp

```sql
SELECT
    tenant_id,
    sales_day,
    paid_orders,
    gross_amount
FROM view_choice_lab.daily_sales_summary
ORDER BY tenant_id, sales_day;
```

Truy vấn đọc một bảng đã có số liệu; không cần GROUP BY qua `orders` tại thời điểm SELECT.

### 6.4. Không có tự động đồng bộ

Việc tạo bảng trên không thông báo PostgreSQL rằng:

```text
orders INSERT/UPDATE/DELETE
   -> phải UPDATE daily_sales_summary
```

Nếu không có job/trigger/pipeline, bảng tổng hợp sẽ **cũ** ngay khi nguồn đổi. Khác với materialized view có `REFRESH` định nghĩa sẵn, summary table cần **logic bảo trì do bạn thiết kế**.

### 6.5. Bảng tổng hợp cần constraint

`PRIMARY KEY (tenant_id,sales_day)` ngăn hai hàng cho cùng một nhóm. `CHECK` ngăn paid_orders hoặc gross_amount âm trong mô hình doanh thu giản lược.

Nhưng constraint **không bảo đảm** các giá trị cộng dồn thực sự bằng bảng `orders`. Một số sai lệch (chẳng hạn 220 thay vì 230) vẫn có thể thỏa mọi constraint.

---

## 7. Thí nghiệm khác biệt sau khi bảng nguồn thay đổi

Tại thời điểm này, ba phương án đã được tạo từ cùng dữ liệu sáu đơn hàng.

### 7.1. Thêm một đơn paid

```sql
INSERT INTO view_choice_lab.orders
    (tenant_id, ordered_at, status, amount)
VALUES
    (1, '2026-11-01 17:00:00+00', 'paid', 30.00);
```

Đây là đơn thứ bảy nếu chỉ nạp một lần. Nó tăng số đơn paid của tenant 1 ngày 01/11 từ **2 lên 3**, và doanh thu từ **200.00 lên 230.00**.

### 7.2. Đọc VIEW ngay sau INSERT đã commit

```sql
SELECT paid_orders, gross_amount
FROM view_choice_lab.v_daily_sales
WHERE tenant_id = 1
  AND sales_day = DATE '2026-11-01';
```

Trong một statement mới thấy commit, kết quả là:

```text
paid_orders | gross_amount
------------+-------------
          3 |      230.00
```

### 7.3. Đọc MATERIALIZED VIEW trước REFRESH

```sql
SELECT paid_orders, gross_amount
FROM view_choice_lab.mv_daily_sales
WHERE tenant_id = 1
  AND sales_day = DATE '2026-11-01';
```

Vẫn là:

```text
paid_orders | gross_amount
------------+-------------
          2 |      200.00
```

Không có trigger tự động refresh materialized view khi `orders` thêm một hàng.

### 7.4. Đọc bảng tổng hợp trước pipeline

```sql
SELECT paid_orders, gross_amount
FROM view_choice_lab.daily_sales_summary
WHERE tenant_id = 1
  AND sales_day = DATE '2026-11-01';
```

Vẫn là **2 / 200.00** vì chưa có code cập nhật summary. Đây không phải lỗi của PostgreSQL; đó là đặc tính của một bảng thông thường không tự liên hệ với nguồn.

### 7.5. Trạng thái sau một INSERT

| Nguồn đọc | paid_orders | gross_amount | Lý do |
|---|---:|---:|---|
| `v_daily_sales` | 3 | 230.00 | Tính theo source snapshot mới |
| `mv_daily_sales` | 2 | 200.00 | Chưa refresh |
| `daily_sales_summary` | 2 | 200.00 | Chưa xử lý delta |

Đây là thí nghiệm quan trọng nhất để hiểu vì sao **không thể chọn kiến trúc chỉ nhìn vào tốc độ SELECT**.

---

## 8. REFRESH MATERIALIZED VIEW và độ mới dữ liệu

### 8.1. REFRESH thông thường

```sql
REFRESH MATERIALIZED VIEW
    view_choice_lab.mv_daily_sales;
```

PostgreSQL chạy lại truy vấn định nghĩa materialized view và cập nhật nội dung được materialize. Sau khi refresh hoàn tất và commit, SELECT mới có thể thấy:

```text
tenant 1 / 2026-11-01 -> 3 orders, 230.00
```

### 8.2. REFRESH thường không phải incremental

Kể cả khi chỉ thêm một đơn mới, PostgreSQL lõi thông thường **không tự nhận ra cần cập nhật đúng một nhóm tenant/ngày** theo delta +30. Nó sẽ thực hiện lại truy vấn định nghĩa matview để xây kết quả mới.

Ví dụ:

```text
Nguồn: 250 triệu order
Biến động: 1 order mới
REFRESH: vẫn có thể phải đọc/tổng hợp lượng rất lớn dữ liệu nguồn
```

Chi phí phụ thuộc SQL, index, scan, join, aggregate và bộ dữ liệu; không mặc định refresh là một phép cập nhật metadata nhanh.

### 8.3. REFRESH thông thường ảnh hưởng người đọc

`REFRESH MATERIALIZED VIEW` không có `CONCURRENTLY` có thể cần khóa mạnh đối với matview, làm các SELECT khác bị chặn trong thời gian thực hiện. Trên dashboard nhiều người đọc, hãy đo thời gian refresh và lock contention trước khi lập lịch.

### 8.4. REFRESH CONCURRENTLY

Vì đã tạo unique index trên `(tenant_id,sales_day)` và materialized view hiện đã có dữ liệu, có thể thử:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    view_choice_lab.mv_daily_sales;
```

`CONCURRENTLY` được thiết kế để hạn chế việc chặn các SELECT đồng thời trên matview trong lúc refresh, nhưng **không có nghĩa refresh miễn phí** hoặc không cần lock.

### 8.5. Điều kiện bắt buộc của CONCURRENTLY

Theo quy tắc PostgreSQL, materialized view phải:

- **Đã populated**: không ở trạng thái chưa có dữ liệu do `WITH NO DATA`.
- Có ít nhất **một UNIQUE index** trên matview.
- Unique index đó phải dùng **chỉ tên cột**, không phải expression index.
- Unique index đó phải **bao phủ tất cả rows**, không có predicate `WHERE` (không phải partial unique index).

Ví dụ hợp lệ trong lab:

```sql
CREATE UNIQUE INDEX mv_daily_sales_tenant_day_uidx
ON view_choice_lab.mv_daily_sales
    (tenant_id, sales_day);
```

Index đã được tạo ở mục 5, nên đây là **định nghĩa để minh họa**, không phải lệnh cần chạy lại cùng tên.

Ví dụ không đáp ứng yêu cầu:

```sql
-- Partial UNIQUE: không đủ điều kiện cho REFRESH CONCURRENTLY.
-- CREATE UNIQUE INDEX bad_partial_uidx
-- ON view_choice_lab.mv_daily_sales (tenant_id, sales_day)
-- WHERE paid_orders > 0;

-- UNIQUE expression index: không đáp ứng yêu cầu tương ứng.
-- CREATE UNIQUE INDEX bad_expression_uidx
-- ON view_choice_lab.mv_daily_sales
--     ((tenant_id::text), sales_day);
```

### 8.6. CONCURRENTLY không có nghĩa tính delta từ source

Đây là hiểu lầm thường gặp:

```text
REFRESH MATERIALIZED VIEW CONCURRENTLY
             ≠
Chỉ refresh hàng vừa thay đổi trong orders
```

`CONCURRENTLY` chủ yếu điều chỉnh **cách thay nội dung materialized view và tương tác với người đọc**. Truy vấn định nghĩa vẫn cần được thực hiện lại; PostgreSQL lõi không mặc định có incremental refresh cho GROUP BY.

Trong một số workload, `CONCURRENTLY` còn **tốn tài nguyên hoặc chạy lâu hơn** REFRESH thông thường vì phải so sánh/áp dụng thay đổi.

### 8.7. Mỗi matview chỉ một refresh tại một thời điểm

PostgreSQL không cho phép nhiều refresh cùng lúc tùy ý lên cùng một materialized view. Scheduler cần **điều phối một job refresh cho mỗi matview** và xử lý job chạy trễ.

Không tạo cron mỗi phút nhưng cho mỗi lần refresh chạy mười phút rồi khởi phát chồng hàng loạt job thiếu kiểm soát.

### 8.8. Người đọc có thể thấy bản trước khi refresh commit

Khi refresh concurrent đang chạy, người đọc thường có thể tiếp tục SELECT từ matview và thấy **bản dữ liệu đã committed** trước đó; sau khi refresh commit, những statement với snapshot mới thấy kết quả mới.

Điều đó là tốt cho availability, nhưng không xóa bỏ yêu cầu **freshness SLA**.

---

## 9. WITH NO DATA và lần refresh đầu tiên

### 9.1. Tạo matview nhưng chưa populated

```sql
-- Mẫu độc lập, không cần chạy lại trên mv_daily_sales có sẵn.
CREATE MATERIALIZED VIEW view_choice_lab.mv_daily_sales_empty AS
SELECT
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date AS sales_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS gross_amount
FROM view_choice_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, (ordered_at AT TIME ZONE 'UTC')::date
WITH NO DATA;
```

`WITH NO DATA` tạo định nghĩa relation mà **chưa materialize kết quả**. Đừng nhầm với một bảng có kết quả rỗng hợp lệ nhưng đã populated.

### 9.2. Không SELECT như một matview đã nạp

Một matview chưa populated được đánh dấu **unscannable**; SELECT nó có thể báo lỗi yêu cầu populate trước. Không lấy `COUNT(*) = 0` làm giả định.

### 9.3. REFRESH đầu tiên

```sql
REFRESH MATERIALIZED VIEW
    view_choice_lab.mv_daily_sales_empty;
```

Sau khi chạy thành công, matview được populated và có thể SELECT.

`REFRESH ... CONCURRENTLY` **không phải lựa chọn cho lần nạp đầu tiên khi matview chưa populated**. Muốn refresh concurrent về sau cần tạo unique index đủ điều kiện trước.

### 9.4. Không kết hợp CONCURRENTLY với WITH NO DATA

Không viết:

```sql
-- Không hợp lệ:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY
--     view_choice_lab.mv_daily_sales_empty
-- WITH NO DATA;
```

Hai tùy chọn không được kết hợp. `WITH NO DATA` còn làm trạng thái materialized view không sẵn sàng để đọc dữ liệu bình thường cho tới khi refresh có data.

---

## 10. Khi nào materialized view thật sự có lợi?

### 10.1. Báo cáo đắt, được đọc nhiều lần, nguồn thay đổi ít

Ví dụ:

```text
Bảng nguồn: 40 triệu transactions
Truy vấn báo cáo: GROUP BY ngày/tenant, JOIN nhiều bảng
Số lần đọc: 300 lần/phút
SLA freshness: tối đa 15 phút
Tốc độ thay đổi: vài nghìn giao dịch mỗi phút
```

Nếu một REFRESH hoàn tất trong khoảng hợp lý và không gây ảnh hưởng tải quá mức, matview có thể giảm công việc lặp lại của hàng trăm SELECT.

### 10.2. Kết quả được nhóm có số hàng nhỏ

Nguồn 40 triệu orders nhưng materialized view chỉ có vài nghìn nhóm (tenant,day). Index trên kết quả nhóm giúp dashboard đọc hẹp.

### 10.3. Không có nhu cầu tính delta từng sự kiện

Khi đã chấp nhận kết quả cũ tới 15 phút, vận hành một lịch refresh có thể đơn giản hơn phát triển event pipeline có exactly-once effect và bù trừ lịch sử.

### 10.4. Nhưng nếu refresh mất 45 phút?

Một lịch refresh mỗi 15 phút **không thể bảo đảm SLA** nếu mỗi lần refresh mất 45 phút và còn chờ locks/CPU. Cần:

- Giảm chi phí truy vấn nguồn, thêm index/partition pruning nếu phù hợp.
- Điều chỉnh grain/khối lượng dữ liệu được materialize.
- Tách một vài báo cáo nặng.
- Chuyển sang aggregate table cập nhật theo lô/delta.
- Đưa báo cáo chuyên sâu sang hệ thống analytics nếu hợp lý.

### 10.5. Materialized view là snapshot, không phải hằng số đúng theo mọi lúc

Định nghĩa **“số liệu đúng”** cần thêm nhãn thời điểm:

```text
Doanh thu ngày 01/11
    đúng theo nguồn tại snapshot refresh lúc 09:00
```

Nếu source có hoàn tiền lúc 09:03, matview vừa refresh lúc 09:00 chưa thể phản ánh giao dịch đó. Đó là staleness dự kiến, không phải dữ liệu hỏng, **nếu SLA và metadata rõ ràng**.

---

## 11. Bảng tổng hợp cập nhật theo delta

Sau thí nghiệm INSERT thêm 30.00 ở mục 7, materialized view đã được refresh ở mục 8, còn `daily_sales_summary` vẫn giữ 200.00 cho tenant 1 ngày 01/11. Ta thử cập nhật phần chênh lệch thay vì GROUP BY toàn bộ nguồn.

### 11.1. UPSERT tăng giá trị

```sql
INSERT INTO view_choice_lab.daily_sales_summary AS s
    (tenant_id, sales_day, paid_orders, gross_amount, updated_at)
VALUES
    (1, DATE '2026-11-01', 1, 30.00, clock_timestamp())
ON CONFLICT (tenant_id, sales_day)
DO UPDATE SET
    paid_orders = s.paid_orders + EXCLUDED.paid_orders,
    gross_amount = s.gross_amount + EXCLUDED.gross_amount,
    updated_at = clock_timestamp();
```

Sau một lần thực thi duy nhất, nhóm này đạt **3 paid orders / 230.00**, trùng view.

### 11.2. Vì sao dùng ON CONFLICT?

Khi một tenant/ngày chưa có hàng:

- `INSERT` tạo nhóm mới.

Khi nhóm đã tồn tại:

- `ON CONFLICT (tenant_id,sales_day)` tìm đúng khóa.
- `DO UPDATE` cộng delta vào số hiện tại.

Việc xử lý xung đột và cập nhật row được PostgreSQL thực hiện theo cơ chế atomic của statement; nhiều writers cùng cập nhật cùng khóa sẽ phải phối hợp row locks.

### 11.3. Rủi ro: chạy UPSERT hai lần sẽ cộng hai lần

Nếu chạy lại câu UPSERT trên:

```text
Lần 1: +1 order, +30.00
Lần 2: +1 order, +30.00

Nguồn thực: chỉ có một order mới
Summary: tăng thành +2 orders, +60.00
```

`ON CONFLICT DO UPDATE` **không tự bảo đảm exactly-once business effect** khi cùng một sự kiện được giao lại. Nó chỉ bảo đảm tính nguyên tử của thao tác trên khóa.

**Không chạy lại câu UPSERT +30 trong lab nếu vẫn muốn so sánh đúng dữ liệu nguồn.** Phần tiếp theo thiết kế cơ chế chống xử lý trùng.

### 11.4. Upsert dạng snapshot khác upsert delta

Hai hình thức:

```sql
-- Gán kết quả đã tính lại cho nhóm:
-- gross_amount = EXCLUDED.gross_amount

-- Cộng thay đổi mới:
-- gross_amount = s.gross_amount + EXCLUDED.gross_amount
```

Không trộn hai loại payload:

- Snapshot `gross_amount=230` không được cộng vào 200.
- Delta `+30` không được gán thay cho 200.

Một contract pipeline nên nêu rõ **sự kiện mang số tuyệt đối hay số thay đổi**.

---

## 12. Chống xử lý trùng: ledger và idempotency

Các hệ thống queue/outbox thường có cơ chế giao sự kiện **at least once**. Khi worker crash sau commit nhưng trước lúc xác nhận message, cùng một event có thể được xử lý lại.

### 12.1. Tạo ledger các thay đổi đã áp dụng

```sql
CREATE TABLE view_choice_lab.applied_sales_changes (
    change_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    sales_day DATE NOT NULL,
    delta_paid_orders BIGINT NOT NULL,
    delta_gross_amount NUMERIC(18,2) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

`change_id` là **ID duy nhất của một business change event**, không nhất thiết bằng `order_id`. Một order có thể phát sinh nhiều event hợp lệ (paid, refunded, corrected), nên không dùng order_id làm event ID cho mọi thay đổi nếu cần theo dõi nhiều phiên bản.

### 12.2. Chỉ áp dụng delta nếu event chưa được ghi vào ledger

Trong lab, delta của đơn +30 đã được cộng ở mục 11. Vì vậy **không chạy lại delta đó** ở ví dụ sau. Câu dưới minh họa một sự kiện mới độc lập có ID 91001 và delta đã được hệ thống nguồn bảo đảm; chỉ thực thi khi delta thực sự có nguồn tương ứng.

```sql
WITH accepted AS (
    INSERT INTO view_choice_lab.applied_sales_changes
        (change_id, tenant_id, sales_day,
         delta_paid_orders, delta_gross_amount)
    VALUES
        (91001, 1, DATE '2026-11-02', 1, 25.00)
    ON CONFLICT (change_id) DO NOTHING
    RETURNING
        tenant_id, sales_day,
        delta_paid_orders, delta_gross_amount
)
INSERT INTO view_choice_lab.daily_sales_summary AS s
    (tenant_id, sales_day, paid_orders, gross_amount, updated_at)
SELECT
    tenant_id,
    sales_day,
    delta_paid_orders,
    delta_gross_amount,
    clock_timestamp()
FROM accepted
ON CONFLICT (tenant_id, sales_day)
DO UPDATE SET
    paid_orders = s.paid_orders + EXCLUDED.paid_orders,
    gross_amount = s.gross_amount + EXCLUDED.gross_amount,
    updated_at = clock_timestamp();
```

**Cảnh báo phạm vi:** Đây là cú pháp mẫu cho một event hợp lệ; nếu chạy nguyên vẹn sau lab mà chưa thêm business event nguồn tương ứng, summary sẽ **cố ý lệch** bảng `orders`. Để thực hành đầy đủ, trước hết phải tạo sự kiện nguồn chính xác hoặc dùng một database riêng cho mô phỏng event ingestion.

### 12.3. Tại sao cùng statement giúp tránh “ledger có nhưng summary chưa cộng”?

Hai thao tác được kết nối bằng `WITH ... RETURNING` trong **một SQL statement**:

1. Chỉ event mới được INSERT vào `applied_sales_changes`.
2. `accepted` chỉ trả các row thực sự được insert.
3. Summary chỉ nhận delta từ những row ấy.

Nếu statement lỗi, transaction không commit phần ledger/summary riêng lẻ theo kiểu một nửa thành công.

### 12.4. Retry cùng change_id

Khi cùng event 91001 đến lại:

- `ON CONFLICT (change_id) DO NOTHING` không tạo ledger row mới.
- CTE `accepted` không trả row.
- Statement không cộng thêm delta vào summary.

Đây là **exactly-once effect theo khóa event** trong điều kiện schema/hợp đồng đúng, không phải bảo đảm mạng sẽ chỉ gửi đúng một message.

### 12.5. ID trùng nhưng payload khác

`ON CONFLICT DO NOTHING` có thể âm thầm bỏ một payload khác dùng lại `change_id`. Trong production cần:

- ID event không bị tái sử dụng cho nội dung khác.
- Lưu hash/version hoặc dữ liệu cần đối chiếu.
- Phát hiện conflict payload thay vì im lặng coi như retry.
- Có đường xử lý poison messages và dead-letter.

### 12.6. Chưa giải quyết nguồn và summary cùng transaction

Ledger + summary được cập nhật atomic **ở phía consumer**. Nếu đơn hàng được ghi ở một database khác hoặc queue khác, còn có vấn đề giao event chắc chắn từ source sang consumer. Thường dùng:

- Transactional outbox trong cùng database với business write.
- CDC đọc transaction log với cơ chế kiểm soát độ trễ.
- Event streaming có sequence/version và deduplication.
- Chốt watermark và đối soát.

Không gọi một pipeline là “end-to-end exactly once” chỉ vì có `ON CONFLICT DO NOTHING` ở consumer.

---

## 13. Hoàn tiền, sửa đơn và delta âm

Chỉ tính các lệnh INSERT mới là chưa đủ. Số liệu có thể thay đổi khi:

- `paid → refunded`.
- `paid → cancelled` khi quy tắc nghiệp vụ cho phép.
- Sửa `amount` sau khi paid.
- Đổi `tenant_id` hoặc `ordered_at` khiến một order chuyển sang **nhóm báo cáo khác**.
- Xóa hàng, nhập liệu trùng hoặc sửa lịch sử.

### 13.1. Phép bù trừ khi paid → refunded

Nếu một order paid 80.00 ở tenant 1 ngày 01/11 đổi thành refunded, nhóm tương ứng cần:

```text
delta_paid_orders = -1
delta_gross_amount = -80.00
```

Đây là **reversal** của đóng góp cũ. Không chỉ trừ 80 mà quên trừ một paid order.

### 13.2. Cập nhật nguồn và summary trong cùng transaction

Với hệ thống đơn giản ở **cùng database**, có thể phối hợp transaction giữa bảng nguồn và summary:

```sql
-- Ví dụ mô phỏng refund order_id=2 trong một database lab mới,
-- không lặp lại nếu order đã refunded.
BEGIN;

WITH changed AS (
    UPDATE view_choice_lab.orders
    SET status = 'refunded'
    WHERE order_id = 2
      AND status = 'paid'
    RETURNING
        tenant_id,
        (ordered_at AT TIME ZONE 'UTC')::date AS sales_day,
        amount
),
adjusted AS (
    UPDATE view_choice_lab.daily_sales_summary AS s
    SET
        paid_orders = s.paid_orders - 1,
        gross_amount = s.gross_amount - c.amount,
        updated_at = clock_timestamp()
    FROM changed AS c
    WHERE s.tenant_id = c.tenant_id
      AND s.sales_day = c.sales_day
      AND s.paid_orders >= 1
      AND s.gross_amount >= c.amount
    RETURNING s.tenant_id, s.sales_day
)
SELECT
    (SELECT COUNT(*) FROM changed) AS changed_orders,
    (SELECT COUNT(*) FROM adjusted) AS adjusted_groups;

-- Trong code vận hành, CHỈ COMMIT khi kết quả đối chiếu hợp lệ.
-- Nếu changed_orders=1 mà adjusted_groups<>1, ROLLBACK và điều tra.
COMMIT;
```

**Lưu ý:** Dòng `COMMIT` ở đây là minh họa luồng transaction và dành cho dữ liệu lab trong trạng thái dự kiến. Ứng dụng production phải **kiểm tra số hàng được cập nhật và chủ động ROLLBACK khi bất biến sai**, hoặc dùng function/logic có `RAISE EXCEPTION` để không cho commit lệch. Không đưa nguyên đoạn vào cron và tin rằng có `SELECT` kiểm tra là đủ.

### 13.3. Vì sao điều kiện status='paid' quan trọng?

Nếu cùng lệnh refund bị retry, lần sau `status='paid'` không còn đúng, nên `UPDATE orders` không trả row trong CTE; không có contribution nào được trừ lần nữa.

Tuy nhiên, hệ thống nhiều loại trạng thái cần **state machine** và event version đúng, không chỉ một điều kiện trạng thái.

### 13.4. Materialized view xử lý refund thế nào?

Đối với matview:

```sql
REFRESH MATERIALIZED VIEW
    view_choice_lab.mv_daily_sales;
```

Kết quả mới được tái tính từ nguồn, nên tự loại đóng góp của order refunded. Không cần tự viết delta -80 cho matview, nhưng phải chịu chi phí refresh lại.

### 13.5. View xử lý refund thế nào?

View chạy GROUP BY trên các row `status='paid'` theo snapshot query, nên khi source status đã committed là refunded, báo cáo mới tự loại order đó.

### 13.6. Đổi grain cần hai phía

Nếu một đơn từ tenant 1/ngày 01/11 được sửa thành tenant 2/ngày 02/11:

```text
Grain cũ (tenant 1, Nov 01): trừ đóng góp cũ
Grain mới (tenant 2, Nov 02): cộng đóng góp mới
```

Pipeline delta phải biết **old row** và **new row**. Chỉ nhìn NEW không đủ để trừ nhóm cũ. Trong trigger PostgreSQL, có thể dùng `OLD`/`NEW`; trong CDC dùng before/after hoặc sự kiện bù trừ; trong ứng dụng dùng transaction và record cũ được khóa/đọc đúng.

### 13.7. Nhóm rỗng và giá trị 0

Nếu nhóm trước có một order paid rồi bị refund:

- View/matview từ `GROUP BY WHERE status='paid'` sẽ **không còn hàng** cho nhóm ấy.
- Summary table trừ delta có thể giữ một hàng `paid_orders=0, gross_amount=0`.

Hai biểu diễn khác nhau. Khi đối chiếu, hãy chọn quy tắc:

- Xóa nhóm summary khi cả số đơn và doanh thu về 0, hoặc
- Giữ nhóm 0 và dùng calendar/COALESCE để đồng nhất output.

Không kết luận có data corruption chỉ vì một bên không có row còn bên kia có row 0, khi hợp đồng báo cáo cho phép điều đó.

---

## 14. Backfill và reconciliation: không thể bỏ qua

Với bảng tổng hợp tự duy trì, pipeline có thể mất event, cộng trùng, dùng sai timezone hoặc đổi logic tính doanh thu sau một thời gian. Cần khả năng xây lại từ **source of truth**.

### 14.1. Query chuẩn để đối chiếu

`v_daily_sales` trong lab được dùng như một định nghĩa tập trung của doanh thu từ nguồn. Với production, query chuẩn phải được review độc lập và có version, không mặc định view cũng luôn không có bug.

### 14.2. Đối chiếu toàn bộ grain với FULL OUTER JOIN

```sql
SELECT
    COALESCE(v.tenant_id, s.tenant_id) AS tenant_id,
    COALESCE(v.sales_day, s.sales_day) AS sales_day,
    COALESCE(v.paid_orders, 0) AS actual_paid_orders,
    COALESCE(s.paid_orders, 0) AS summary_paid_orders,
    COALESCE(v.gross_amount, 0) AS actual_gross_amount,
    COALESCE(s.gross_amount, 0) AS summary_gross_amount
FROM view_choice_lab.v_daily_sales AS v
FULL OUTER JOIN view_choice_lab.daily_sales_summary AS s
    ON s.tenant_id = v.tenant_id
   AND s.sales_day = v.sales_day
WHERE
    COALESCE(v.paid_orders, 0)
        <> COALESCE(s.paid_orders, 0)
    OR
    COALESCE(v.gross_amount, 0)
        <> COALESCE(s.gross_amount, 0)
ORDER BY tenant_id, sales_day;
```

Đây là query phát hiện sai lệch theo nhóm, tính cả nhóm bị thiếu ở một phía. Nó tốn công đọc/tổng hợp bảng nguồn; trên dữ liệu lớn có thể đối chiếu theo kỳ, tenant hoặc sample trước.

### 14.3. Rebuild đơn giản trong cửa sổ bảo trì

Đối với bảng demo nhỏ và có thể **tạm chặn writers**, quy trình minh họa:

```sql
BEGIN;

-- SHARE lock trên orders ngăn các transaction sửa orders
-- trong khoảng rebuild; phải đánh giá contention.
LOCK TABLE view_choice_lab.orders IN SHARE MODE;

DELETE FROM view_choice_lab.daily_sales_summary;

INSERT INTO view_choice_lab.daily_sales_summary
    (tenant_id, sales_day, paid_orders, gross_amount)
SELECT tenant_id, sales_day, paid_orders, gross_amount
FROM view_choice_lab.v_daily_sales;

COMMIT;
```

Sau rebuild, bảng summary thể hiện đúng kết quả GROUP BY theo dữ liệu nguồn tại transaction/locking context đó, giả định không có pipeline khác đồng thời áp delta độc lập vào summary.

**Không coi đoạn này là phương án online cho bảng hàng trăm triệu rows**:

- `LOCK ... IN SHARE MODE` có thể chặn writers của `orders`.
- `DELETE` toàn bảng ghi WAL, tạo dead tuples và giữ row locks.
- Reader có snapshot cũ có thể thấy dữ liệu khác do MVCC.
- Consumer delta đang chạy có thể bị khóa/tranh chấp hoặc cộng lại event đã thuộc snapshot.

### 14.4. Rebuild production phải có mốc và điều phối

Một quy trình lớn thường cần:

1. Xác định source snapshot/watermark.
2. Tính lại tập tổng hợp trong staging table hoặc các batch đã checkpoint.
3. Kiểm tra row counts, sums, các nhóm trọng yếu.
4. Tạm dừng/điều phối consumer delta khi chuyển đổi.
5. Áp các thay đổi sau watermark vào bản mới hoặc chuyển atomic theo cơ chế phù hợp.
6. Chuyển readers sang bản đã đối soát.
7. Giữ đường rollback và quan sát sau chuyển đổi.

Không rebuild vào một bảng rồi để event consumer cộng thêm **cùng các order đã nằm trong bản rebuild**.

### 14.5. Watermark phải có ý nghĩa

Một timestamp `updated_at` trên summary row không đủ chứng minh worker đã xử lý **tất cả** events trước một mốc. Watermark tốt thường dựa trên:

- Offset/sequence có thứ tự được xác nhận.
- Transaction log position trong CDC.
- Batch/job ID có phạm vi dữ liệu xác định.
- Snapshot/revision được lưu bền vững.

Mục tiêu là trả lời được: “Bảng này đã áp tất cả thay đổi của nguồn **đến đâu**?”

### 14.6. Đối chiếu count và sum chưa phải tất cả

Hai sai sót có thể vô tình bù trừ cùng số tiền, khiến tổng khớp nhưng hàng nguồn sai. Với dữ liệu nhạy cảm, nên bổ sung:

- Đếm theo status/currency/category.
- Tìm sự kiện chưa xử lý theo ID.
- Tổng số transaction/amount theo checkpoint.
- Audit log, hash/checksum có phạm vi xác định.
- Test nghiệp vụ với hoàn tiền/sửa ngày/tenant.

---

## 15. Yêu cầu độ mới: thiết kế freshness SLA

### 15.1. Freshness khác query latency

- **Query latency:** thời gian một SELECT trả kết quả (ví dụ 40 ms).
- **Data freshness:** độ chậm giữa thay đổi source và sự xuất hiện của nó trong báo cáo.

Một materialized view có thể trả trong 5 ms nhưng phản ánh số liệu của 30 phút trước. Một view đọc trực tiếp có thể cần 1.500 ms nhưng theo snapshot nguồn mới.

### 15.2. Định nghĩa SLA bằng câu có thể đo

Ví dụ:

```text
99% sự kiện paid được thể hiện trong báo cáo
trong vòng 60 giây sau khi giao dịch source commit.
```

Đây là một tiêu chí cụ thể hơn “báo cáo gần realtime”.

### 15.3. Gợi ý lựa chọn theo SLA

| Mục tiêu | Hướng thường cân nhắc | Điều kiện |
|---|---|---|
| Query hiện trạng ở snapshot mới | View | GROUP BY/JOIN nguồn đủ nhanh |
| Chấp nhận trễ vài phút/giờ | Materialized view + lịch refresh | Refresh hoàn tất ổn định trước deadline |
| Cần cập nhật từng giây, workload lớn | Summary table transactional/event-driven | Có delta, idempotency, watermark và reconciliation |
| Báo cáo truy vấn tùy biến ít đọc | View hoặc query trực tiếp | Không materialize vô số biến thể |
| Báo cáo nặng ít thay đổi | Materialized view | Dữ liệu đã tổng hợp nhỏ hơn nhiều nguồn |
| Nhiều báo cáo realtime phức tạp | Hệ tổng hợp chuyên dụng hoặc kiến trúc analytics | Cần đánh giá chi phí/kỹ thuật của hệ thống khác |

Không chỉ dựa vào từ “realtime” trong yêu cầu. Hỏi về **thời điểm commit của nguồn**, phần trăm sự kiện phải bắt kịp, trường hợp lỗi và cách hiển thị dữ liệu cũ.

### 15.4. Scheduling REFRESH không tạo SLA nếu job chậm

Giả sử:

```text
Refresh bắt đầu lúc 09:00
Refresh xong lúc 09:12
Lần tiếp theo bắt đầu lúc 09:15
```

Query lúc 09:14 có thể thấy snapshot được tính theo trạng thái nguồn ở một thời điểm gần lúc bắt đầu refresh, không phải số liệu 09:14. Chỉ dựa vào “refresh mỗi 15 phút” không chứng minh **staleness tối đa 15 phút** trong mọi tình huống.

Nên theo dõi:

- Thời điểm refresh **bắt đầu** và **hoàn tất**.
- Thời điểm/snapshot dữ liệu nguồn được đọc theo semantics transaction.
- Thời gian chờ lock.
- Thời gian query tính lại.
- Trạng thái success/failure.
- Tuổi của snapshot/offset dữ liệu được phục vụ.

### 15.5. Nếu refresh thất bại thì sao?

Matview có thể vẫn phục vụ snapshot cũ. Dashboard nên biết:

- Lần refresh thành công gần nhất.
- Số lần job fail.
- Độ tuổi dữ liệu vượt SLA hay chưa.
- Có cần cảnh báo hoặc gắn nhãn “dữ liệu tới thời điểm ...” không.

Không coi SELECT thành công từ matview là bằng chứng refresh scheduler còn hoạt động.

---

## 16. View không phải vật liệu lưu trữ và không có index riêng

### 16.1. Index nên nằm trên bảng nguồn

Với view dựa vào orders:

```sql
CREATE INDEX orders_paid_tenant_time_idx
ON view_choice_lab.orders (tenant_id, ordered_at)
WHERE status = 'paid';
```

Đây là **partial B-tree index trên bảng nguồn**. Nó có thể giúp những truy vấn đã giới hạn tenant và khoảng thời gian, vì chỉ chứa rows paid.

Không viết:

```sql
-- Không thể tạo B-tree vật lý trực tiếp trên một VIEW thông thường:
-- CREATE INDEX ... ON view_choice_lab.v_daily_sales (...);
```

### 16.2. Biến đổi thời gian có thể ảnh hưởng khả năng dùng index

View nhóm theo:

```sql
(ordered_at AT TIME ZONE 'UTC')::date
```

Một query ngoài:

```sql
SELECT *
FROM view_choice_lab.v_daily_sales
WHERE sales_day = DATE '2026-11-01';
```

có thể không được planner đổi thành một range đơn giản trên `orders.ordered_at` trong mọi trường hợp. Nếu đây là hotspot, cân nhắc:

- SQL trực tiếp có `ordered_at >= lower` và `ordered_at < upper`.
- Tạo expression index phù hợp khi hợp lệ và có workload thực.
- Materialize báo cáo ngày vào MV/table.
- Xem `EXPLAIN` để xác định khả năng pushdown/pruning thực tế.

**Không giả định view luôn tự biến mọi điều kiện trên cột tổng hợp thành điều kiện indexable trên bảng gốc.**

### 16.3. Predicate pushdown có giới hạn

Trong nhiều truy vấn đơn giản, PostgreSQL có thể tối ưu view bằng cách đưa điều kiện xuống dưới. Nhưng:

- Aggregate, window functions, DISTINCT và LIMIT có thể hạn chế một số phép biến đổi.
- `security_barrier` có thể thay thứ tự đánh giá để bảo vệ thông tin.
- Volatile functions và các phép JOIN phức tạp có semantics riêng.

Do đó, một view là lớp abstraction hữu ích nhưng không bảo đảm mọi query ngoài sẽ có plan giống SQL tự tay viết ở một mức khác.

### 16.4. ORDER BY trong view

Không dựa vào thứ tự vật lý hoặc thứ tự xuất hiện tình cờ của rows từ view/MV/summary. Khi API cần deterministic pagination:

```sql
SELECT *
FROM view_choice_lab.v_daily_sales
ORDER BY tenant_id, sales_day;
```

View chỉ được đọc qua SELECT ngoài; **ORDER BY ở truy vấn tiêu thụ** là hợp đồng thứ tự cần thể hiện rõ.

---

## 17. Index cho materialized view và bảng tổng hợp

### 17.1. Index trên materialized view

```sql
CREATE UNIQUE INDEX mv_daily_sales_tenant_day_uidx
ON view_choice_lab.mv_daily_sales
    (tenant_id, sales_day);
```

Index đã được tạo ở mục 5; câu trên chỉ nhắc lại định nghĩa, không chạy hai lần.

Query:

```sql
EXPLAIN
SELECT paid_orders, gross_amount
FROM view_choice_lab.mv_daily_sales
WHERE tenant_id = 1
  AND sales_day = DATE '2026-11-01';
```

có thể dùng index tùy cost/cardinality. Với chỉ vài hàng trong lab, Seq Scan thường hợp lý.

### 17.2. Bảng tổng hợp có primary key

```sql
PRIMARY KEY (tenant_id, sales_day)
```

PostgreSQL tạo unique B-tree index để phục vụ constraint. Nó có thể dùng cho:

```sql
WHERE tenant_id = 1
  AND sales_day >= DATE '2026-11-01'
  AND sales_day <  DATE '2026-12-01'
```

Nếu workload thường truy vấn **tất cả tenant của một ngày**, có thể cần index khác bắt đầu bằng `sales_day`, nhưng chỉ tạo sau khi đo.

### 17.3. Không có “global index” cho báo cáo chỉ vì nguồn có index

Index trên `orders(tenant_id,ordered_at)` giúp quét nguồn. Index trên `mv_daily_sales(tenant_id,sales_day)` giúp đọc **kết quả đã lưu**. Hai index phục vụ các giai đoạn và quan hệ khác nhau.

### 17.4. Covering index và INCLUDE

Trong một số workload:

```sql
-- Mẫu cân nhắc, không cần tạo thêm trên lab:
-- CREATE INDEX ... ON daily_sales_summary
--   (tenant_id, sales_day)
--   INCLUDE (paid_orders, gross_amount);
```

`INCLUDE` có thể giúp index-only scan khi điều kiện MVCC visibility phù hợp. Nhưng nếu summary table bị UPDATE liên tục, visibility map có thể chưa hỗ trợ index-only nhiều như kỳ vọng, và index rộng tăng chi phí ghi.

Đừng thêm INCLUDE theo thói quen nếu primary key đã đủ cho vài trăm/thousand nhóm.

### 17.5. ANALYZE sau bulk load/REFRESH

```sql
ANALYZE view_choice_lab.mv_daily_sales;
ANALYZE view_choice_lab.daily_sales_summary;
```

Thống kê giúp planner dự đoán rows/selectivity tốt hơn. Với dữ liệu báo cáo lớn được refresh/rebuild, nên có chiến lược quản lý thống kê phù hợp; không nên dựa vào plan trước khi populate.

---

## 18. Đọc EXPLAIN: lúc nào chi phí chuyển từ READ sang WRITE?

### 18.1. Truy vấn VIEW

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM view_choice_lab.v_daily_sales
WHERE tenant_id = 1
ORDER BY sales_day;
```

Quan sát những node bên dưới aggregate: scan nguồn, filter paid, hash/sort/group và buffers. PostgreSQL vẫn cần làm công việc tổng hợp khi đọc.

### 18.2. Truy vấn MATERIALIZED VIEW

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM view_choice_lab.mv_daily_sales
WHERE tenant_id = 1
ORDER BY sales_day;
```

Plan chỉ truy cập relation matview đã lưu; không phải lập lại GROUP BY trên orders cho mỗi SELECT.

### 18.3. Truy vấn SUMMARY TABLE

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM view_choice_lab.daily_sales_summary
WHERE tenant_id = 1
ORDER BY sales_day;
```

Tương tự về chi phí đọc kết quả nhỏ, nhưng phải cộng thêm chi phí tổng thể của pipeline/UPSERT/ledger/backfill để so phương án công bằng.

### 18.4. Không chỉ so một SELECT latency

Một so sánh đầy đủ cần ít nhất:

| Chỉ số | View | Materialized view | Summary table |
|---|---|---|---|
| SELECT p50/p95/p99 | Có | Có | Có |
| CPU/I/O query nguồn | Mỗi SELECT | Mỗi REFRESH | Theo job/delta |
| Tổng số lần scan nguồn | Theo traffic | Theo lịch refresh | Theo backfill/reconciliation |
| Ghi WAL | Chủ yếu nguồn | Source + refresh storage/index | Source + summary/ledger |
| Lock contention | Theo query nguồn | Theo refresh và SELECT | Theo update nhóm/source |
| Storage | Định nghĩa view | Kết quả + indexes | Kết quả + indexes + ledger |
| Độ trễ dữ liệu | Snapshot query | Lần refresh | Watermark pipeline |
| Recovery phức tạp | Thường thấp | Refresh lại | Rebuild/replay/đối soát |

### 18.5. Thận trọng với dữ liệu lab nhỏ

Trên sáu/bảy orders, view có thể nhanh hơn matview vì overhead rất nhỏ. Không dùng một test trên vài hàng để kết luận kiến trúc production cho hàng trăm triệu orders.

### 18.6. Đo đúng cost của refresh

Không chỉ đo thời gian đọc matview. Hãy đo:

- Thời gian REFRESH thông thường và CONCURRENTLY.
- I/O/CPU khi tính lại query nguồn.
- Thời gian giữ/chờ lock.
- Độ trễ replicas và WAL.
- Kích thước matview/index.
- Thời điểm dữ liệu mới xuất hiện sau commit refresh.

Nếu refresh gây spike vài phút làm ứng dụng chậm, matview có thể cần thay thế dù SELECT riêng rất nhanh.

---

## 19. Thiết kế đúng phép tổng hợp

### 19.1. SUM và COUNT là đại lượng có thể bù trừ theo grain

Với mô hình paid orders đơn giản, hai thước đo:

```text
paid_orders = SUM(1 cho mỗi order paid)
gross_amount = SUM(amount cho mỗi order paid)
```

có tính **additive** theo các nhóm disjoint, cho phép cộng delta và bù trừ khi status đổi.

### 19.2. AVG không phải tổng của các AVG

Ví dụ hai ngày:

```text
Ngày A: 1 order, amount 100
Ngày B: 9 orders, tổng amount 90

AVG toàn kỳ = (100 + 90) / (1 + 9) = 19
AVG hai AVG ngày = (100 + 10) / 2 = 55  <- sai
```

Nếu cần average amount theo tháng từ daily summary, lưu **SUM(amount)** và **COUNT(*)**; tính:

```sql
SELECT
    tenant_id,
    SUM(gross_amount)
        / NULLIF(SUM(paid_orders), 0) AS avg_paid_order_amount
FROM view_choice_lab.daily_sales_summary
GROUP BY tenant_id;
```

### 19.3. COUNT(DISTINCT ...) không additive đơn giản

Nếu cùng customer mua hàng ở hai ngày, cộng số customer distinct từng ngày sẽ đếm khách đó hai lần ở tổng tháng.

**Không** thiết kế một daily distinct count rồi cộng lên năm nếu nghiệp vụ yêu cầu distinct toàn năm. Có thể cần:

- Summary theo customer/grain sâu hơn.
- Tính lại trên raw data cho khoảng được hỏi.
- Sketch/approximate distinct với hợp đồng sai số rõ.
- Thiết kế bảng membership để xác định số khách distinct.

### 19.4. Join fanout làm sai cả ba phương án

Nếu một order có ba order items và report:

```sql
SELECT SUM(o.amount)
FROM orders o
JOIN order_items i ON i.order_id = o.order_id;
```

thì `o.amount` có thể bị cộng ba lần. View, matview và summary table đều có thể **lưu/đọc cùng một phép tính sai**.

Giải pháp: xác định grain của bảng trước/sau JOIN; aggregate items theo order hoặc tách measures đúng grain. `SUM(DISTINCT o.amount)` không phải giải pháp tổng quát vì hai orders khác nhau có thể cùng amount.

### 19.5. Nhiều loại tiền tệ

Không cộng:

```text
100 USD + 100 VND = 200 "tiền"
```

Trong production:

- Thêm `currency` vào grain và khóa nếu báo cáo từng đồng tiền.
- Nếu báo cáo một đơn vị quy đổi, xác định tỷ giá tại mốc nào.
- Lưu source currency, exchange rate/version, đơn vị quy đổi.
- Có chính sách làm lại summary khi tỷ giá hoặc giao dịch bị điều chỉnh.

### 19.6. Phân biệt gross, net, refund và recognized revenue

Định nghĩa `status='paid'` trong lab là giản lược. Các hệ thống thực thường cần các bảng payment, invoice, refund và ledger; doanh thu kế toán có thể được công nhận khác thời điểm order paid.

Không đặt tên `gross_amount` rồi dùng nó làm số báo cáo tài chính chính thức khi chưa được nghiệp vụ xác nhận.

---

## 20. Chọn phương án khi báo cáo có nhiều chiều lọc

Một dashboard có thể lọc:

```text
tenant
date range
region
sales channel
product category
campaign
payment method
currency
```

### 20.1. View linh hoạt khi tổ hợp điều kiện đa dạng

Một view trên dữ liệu nguồn có thể phục vụ nhiều điều kiện WHERE và JOIN khác nhau. Nhưng độ linh hoạt không xóa chi phí quét nguồn khi dữ liệu lớn.

### 20.2. Materialize quá nhiều chiều có thể bùng nổ cardinality

Giả sử:

```text
100 tenants × 365 ngày × 20 regions × 10 channels × 50 categories
      = 365 triệu tổ hợp lý thuyết
```

Thực tế chỉ những tổ hợp có dữ liệu mới sinh row GROUP BY, nhưng cardinality vẫn có thể rất lớn.

Một materialized view quá chi tiết sẽ:

- Chiếm nhiều disk.
- Tốn nhiều thời gian refresh.
- Tạo index lớn.
- Có thể mất lợi ích “kết quả nhỏ so với nguồn”.

### 20.3. Chọn grain đủ linh hoạt nhưng không quá mịn

Grain:

```text
(tenant_id, sales_day)
```

phù hợp cho báo cáo ngày/tenant, nhưng **không** phục hồi được report theo từng sản phẩm vì dữ liệu product đã bị mất khỏi tổng hợp.

Nếu cần product-level:

```text
(tenant_id, sales_day, product_id)
```

thì có thể roll up lên ngày/tenant bằng SUM, nhưng chi phí lưu và cập nhật cao hơn. Phải xác định measures có additive theo product không.

### 20.4. Hybrid: nhiều tầng dữ liệu

Một kiến trúc thực tế có thể kết hợp:

```text
orders source
  |
  +--> v_order_details          (lớp SQL logic)
  |
  +--> daily_sales_summary      (API realtime)
  |
  +--> mv_monthly_kpis          (dashboard định kỳ)
  |
  +--> analytics warehouse      (báo cáo lịch sử chuyên sâu)
```

Không cần ép **một phương án duy nhất** phục vụ mọi nhu cầu. Tuy vậy, phải tránh nhiều định nghĩa doanh thu khác nhau âm thầm cho cùng một metric.

---

## 21. View và quyền truy cập dữ liệu

### 21.1. View có thể là một API SQL ổn định

Một view:

```sql
CREATE VIEW view_choice_lab.v_paid_order_public AS
SELECT
    order_id,
    tenant_id,
    ordered_at,
    amount
FROM view_choice_lab.orders
WHERE status = 'paid';
```

có thể công bố các cột đã chọn, ẩn các trường không muốn cung cấp cho một vai trò đọc nhất định.

Nhưng **không coi view tự động là hàng rào bảo mật tenant** nếu không thiết kế quyền và RLS đúng.

### 21.2. Quyền trên view và bảng nguồn

Theo mặc định, view trong PostgreSQL dùng những quy tắc quyền liên quan **view owner** đối với các bảng cơ sở theo hành vi PostgreSQL. Vì vậy một role có quyền SELECT trên view có thể đọc qua view ngay cả khi không được cấp SELECT trực tiếp trên base table trong những tình huống thông thường.

Điều này hữu ích để xuất một interface hạn chế, nhưng phải quản lý owner, grants, function privileges và những vấn đề liên quan.

### 21.3. security_invoker

PostgreSQL 15+ hỗ trợ tùy chọn `security_invoker` cho view:

```sql
-- Ví dụ trên PostgreSQL hỗ trợ security_invoker:
-- CREATE VIEW view_choice_lab.v_order_invoker
-- WITH (security_invoker = true)
-- AS SELECT order_id, tenant_id
--    FROM view_choice_lab.orders;
```

Với `security_invoker=true`, quyền của người gọi được dùng cho các quan hệ cơ sở theo semantics của tùy chọn này; RLS cũng cần được xét tương ứng. Không sao chép cú pháp vào phiên bản PostgreSQL cũ mà không kiểm tra hỗ trợ.

### 21.4. security_barrier

`security_barrier` cho view giúp giới hạn một số kiểu biến đổi kế hoạch có thể làm lộ dữ liệu thông qua function/predicate được đánh giá không đúng thứ tự bảo mật.

```sql
-- Tùy mục tiêu bảo mật:
-- CREATE VIEW some_view WITH (security_barrier = true) AS ...;
```

Nhưng security barrier có thể ảnh hưởng predicate pushdown và hiệu năng. Nó **không thay thế toàn bộ mô hình authorization**.

### 21.5. RLS và tenant scope

Với hệ thống nhiều tenant:

- Đặt quy tắc phân quyền tại vị trí có thể kiểm chứng.
- Xác định view owner/invoker và RLS behavior.
- Không cấp quyền SELECT trên matview toàn tenant nếu cần ngăn tenant khác đọc.
- Không nghĩ một điều kiện `WHERE tenant_id=$1` do client truyền là đủ bảo mật nếu client có thể bỏ nó.

### 21.6. Materialized view là dữ liệu đã sao chép

Vì matview chứa dữ liệu vật lý, một cơ chế RLS hoặc quyền được áp dụng trên bảng nguồn **không mặc nhiên thực thi lại như truy vấn nguồn mỗi khi ai đó SELECT matview**. Kiểm tra riêng grants, owner và khả năng truy cập relation chứa dữ liệu materialize.

Một matview tổng hợp toàn tenant có thể làm lộ số liệu tenant khác nếu cấp quyền đọc quá rộng.

### 21.7. Summary table cũng phải được bảo vệ

Một summary table có thể lưu PII, metrics tài chính và dữ liệu theo tenant. Phân quyền cho consumer/worker ghi và role đọc phải được thiết kế riêng; worker ghi không nên có quyền tùy tiện trên toàn schema nếu không cần.

---

## 22. Cập nhật được hay không? Một số giới hạn quan trọng

### 22.1. Một số view đơn giản có thể tự cập nhật

Ví dụ view một bảng không có GROUP BY:

```sql
CREATE VIEW view_choice_lab.v_paid_order_public AS
SELECT order_id, tenant_id, ordered_at, amount
FROM view_choice_lab.orders
WHERE status = 'paid';
```

Định nghĩa này đã được tạo ở mục 21; đây là lời nhắc, **không chạy lại CREATE VIEW cùng tên**.

PostgreSQL hỗ trợ một số **automatically updatable views** khi định nghĩa đáp ứng quy tắc. Tuy nhiên, việc update qua view phải tuân theo cột có thể thay đổi, constraint và quy tắc `CHECK OPTION` khi áp dụng.

### 22.2. GROUP BY view không tự update như bảng

```sql
CREATE VIEW view_choice_lab.v_daily_sales AS
SELECT tenant_id, ..., COUNT(*), SUM(amount)
FROM ...
GROUP BY ...;
```

Đây là dạng minh họa định nghĩa đã tạo ở mục 4. Một row tổng hợp không ánh xạ một-một tới một order, nên không có thao tác UPDATE tự động đơn giản để chuyển `gross_amount=200` thành 250 và biết phải sửa order nào.

Có thể viết `INSTEAD OF` triggers/rules cho những interface nhất định, nhưng không mặc định PostgreSQL có thể sửa dữ liệu nguồn từ aggregate view.

### 22.3. Materialized view không là bảng DML tùy ý

Matview được làm mới từ định nghĩa truy vấn. Không dùng `INSERT/UPDATE/DELETE` trực tiếp như summary table thông thường.

### 22.4. Summary table hỗ trợ UPDATE/UPSERT thông thường

Đây chính là lý do summary table phù hợp với pipeline cập nhật delta. Đổi lại, **tính đúng đắn** không tự đến từ việc bảng có thể UPDATE.

### 22.5. Không nhầm “updatable view” với “live aggregate”

Một view có thể phản ánh dữ liệu mới mà **không cho phép cập nhật thông qua view**. “Live” nói về **đọc**, còn “updatable” nói về **ghi qua interface**.

---

## 23. Đồng bộ dưới concurrency và transaction

### 23.1. View đọc một snapshot nhất quán theo statement

Một SELECT aggregate sử dụng snapshot của database theo isolation level. Nó không lấy nửa trạng thái trước commit và nửa trạng thái sau commit của cùng một transaction theo cách làm mất atomicity của commit.

### 23.2. Materialized view có snapshot refresh

REFRESH thực thi truy vấn theo snapshot của transaction/câu lệnh refresh, rồi công bố kết quả sau commit. Trong lúc refresh, writers có thể tiếp tục thay đổi bảng nguồn; những thay đổi xảy ra sau snapshot mà refresh sử dụng **không nhất thiết được tính** vào kết quả refresh này.

Không gắn nhãn matview “dữ liệu đúng tới lúc job kết thúc” nếu job sử dụng một snapshot trước đó.

### 23.3. Summary đồng bộ trong cùng transaction

Nếu một API ghi order rồi cập nhật daily summary **trong cùng transaction** và rollback nếu một bước lỗi, hệ thống có thể đạt consistency mạnh giữa hai relation cho workflow đó.

Tuy nhiên, điều này có thể tăng:

- Lock contention trên một nhóm summary nóng.
- Thời gian transaction.
- Deadlock risk nếu các code paths cập nhật bảng theo thứ tự khác nhau.
- Write amplification.

### 23.4. Hot-row contention

Mọi order của một tenant trong cùng ngày cập nhật:

```sql
PRIMARY KEY (tenant_id, sales_day)
```

thì hàng summary đó có thể trở thành **hot row** khi hàng nghìn writers cùng cộng delta.

Giải pháp có thể cân nhắc:

- Gom event theo batch thay vì UPDATE từng order.
- Shard counter theo bucket rồi roll up.
- Dùng event stream/queue theo tenant để tuần tự hóa có chủ đích.
- Tách workload analytics khỏi online transactions.
- Sử dụng matview nếu freshness cho phép.

Không biến mọi order write thành transaction chờ một row khóa nóng mà chưa đo.

### 23.5. Isolation level không chữa thiếu event

`SERIALIZABLE` hoặc locking chặt có thể giúp ngăn một số anomalies, nhưng không tự giao lại event thất lạc giữa hệ thống nguồn và consumer. Cần thiết kế giao nhận, idempotency và reconciliation độc lập.

### 23.6. Eventual consistency cần hiển thị rõ

Nếu summary được cập nhật asynchronous, có thể có khoảng:

```text
Đơn paid đã commit tại source
            |
            v
Event đang chờ trong queue
            |
            v
Summary chưa đổi
            |
            v
Consumer xử lý và commit summary
```

Khoảng chậm này phải nằm trong freshness SLA hoặc được biểu thị trên UI. Không gọi summary là “đã commit tức thời” khi pipeline asynchronous.

---

## 24. Partitioning và vòng đời dữ liệu

Một bảng `orders` lớn có thể được partition theo tháng. Lúc đó lựa chọn báo cáo có thêm những cân nhắc:

### 24.1. View trên partitioned table

View có thể hưởng lợi từ **partition pruning** nếu predicate phù hợp với partition key và planner chứng minh được những partition không liên quan.

Nếu query tính tất cả dữ liệu lịch sử mỗi lần, view vẫn phải đọc nhiều partition.

### 24.2. Materialized view không tự thay đổi khi detach nguồn

Nếu một partition tháng cũ bị DETACH hoặc DROP, matview **không tự cập nhật nội dung đã materialize**. Chỉ sau refresh, kết quả mới phản ánh tình trạng nguồn hiện tại.

Điều đó có thể là:

- Lợi ích nếu cần giữ báo cáo lịch sử khi raw data rời online, **nhưng phải có policy và kiểm soát**.
- Rủi ro nếu dữ liệu nguồn bị xóa theo quyền riêng tư nhưng matview còn giữ số liệu/cá nhân không được phép lưu.

### 24.3. Bảng tổng hợp có thể lưu lâu hơn raw data

Ví dụ:

```text
Raw orders: giữ 90 ngày
Daily summary không chứa PII: giữ 3 năm
```

Thiết kế đó có thể tiết kiệm dữ liệu, nhưng chỉ hợp lệ khi chính sách lưu trữ/tuân thủ cho phép. Một khi raw data đã bị xóa, việc **rebuild chính xác** các kỳ lịch sử từ source có thể không còn khả thi; cần lưu bằng chứng/backup cần thiết theo quy định.

### 24.4. Không hiểu retention là xóa hết mọi bản sao tự động

DROP source partition không tự xóa dữ liệu khỏi:

- Materialized view.
- Summary table.
- Backup/archive.
- Data warehouse.
- Log và cache.

Thực hiện retention với **bản đồ tất cả nơi dữ liệu được sao chép**, không chỉ bảng nguồn.

---

## 25. Chọn dựa trên số liệu tải

Trước khi quyết định, thu thập ít nhất:

| Câu hỏi | Thông tin cần có |
|---|---|
| Bảng nguồn lớn bao nhiêu? | Rows, bytes, partitions, tốc độ tăng |
| Query hiện tại tốn bao lâu? | p50/p95/p99, buffers, CPU, temp spill |
| Query được gọi bao nhiêu lần? | Requests/phút, concurrency |
| Nguồn thay đổi bao nhiêu? | INSERT/UPDATE/DELETE và tần suất |
| Bao nhiêu nhóm tổng hợp? | Cardinality theo grain |
| Chấp nhận trễ tối đa? | SLA, cách đo theo commit time/watermark |
| Có late events/refunds không? | Thời gian và tần suất correction |
| Có nhiều tenant/currency không? | Quy tắc phân quyền và khóa nhóm |
| Có thể khóa nguồn khi rebuild không? | Maintenance window, tải ghi |
| Mức vận hành cho phép? | Scheduler, queue/CDC, alert, on-call |

### 25.1. Một ví dụ quyết định

Giả sử:

```text
orders: 2 triệu rows, tăng 3.000/ngày
dashboard: 5 requests/phút
view query: 80 ms p95
SLA: dữ liệu mới theo snapshot
```

View có thể đã đáp ứng tốt. Thêm matview hoặc event pipeline là tăng độ phức tạp không cần thiết nếu hệ thống không có yêu cầu khác.

### 25.2. Trường hợp nên thử matview

```text
orders: 100 triệu rows
report query: 12 giây
dashboard: 200 requests/phút
SLA: trễ tối đa 30 phút
REFRESH thử nghiệm: 4 phút, tải chấp nhận được
```

Matview có thể giảm mạnh chi phí SELECT lặp lại; cần kiểm tra refresh job, concurrency/locks và freshness.

### 25.3. Trường hợp nên thử summary table

```text
orders: 400 triệu rows
report query: 20 giây
dashboard: 1.000 requests/phút
SLA: phần lớn sự kiện dưới 15 giây
REFRESH toàn phần: 25 phút
Event stream/outbox đã có, có cơ chế đối soát
```

Một summary table cập nhật theo delta/batch có thể phù hợp hơn refresh toàn bộ. Nhưng nếu cập nhật cùng một hot key gây contention, thiết kế delta vẫn cần tối ưu.

### 25.4. Đừng dùng những con số minh họa như benchmark chính thức

Các thời gian/tốc độ nêu trên **chỉ là tình huống giả định** để diễn giải quyết định. Không phải cam kết hiệu năng PostgreSQL. Kết quả thực tế phụ thuộc hardware, cache, query, index, data distribution, concurrency và phiên bản.

---

## 26. Runbook vận hành MATERIALIZED VIEW

### 26.1. Trước triển khai

1. Xác định grain và semantics nghiệp vụ.
2. Benchmark truy vấn định nghĩa trên dữ liệu đại diện.
3. Tính số hàng/dung lượng kết quả.
4. Tạo matview `WITH DATA` hoặc nạp lần đầu nếu `WITH NO DATA`.
5. Tạo indexes cần cho query.
6. Nếu muốn `CONCURRENTLY`, tạo ít nhất một **UNIQUE index không partial, không expression, phủ mọi rows**.
7. Kiểm tra quyền truy cập và dữ liệu tenant.

### 26.2. Khi chạy refresh

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    view_choice_lab.mv_daily_sales;
```

Chỉ dùng câu trên khi matview đã populated và index hợp lệ; nếu không đáp ứng, dùng refresh thông thường theo quy trình.

### 26.3. Giám sát job

Theo dõi:

- Started/finished.
- Success/failure.
- Thời gian lock wait.
- Thời gian refresh.
- Rows result và index size.
- Nguồn có nhiều cập nhật trong lúc refresh không.
- Data freshness theo snapshot/watermark.
- Replica lag/WAL.

### 26.4. Xử lý khi refresh fail

Không xóa matview ngay khi job fail. Cần:

1. Kiểm tra lỗi (unique index, quyền, SQL định nghĩa, disk, timeout).
2. Kiểm tra matview có còn populated và readable không.
3. Giữ snapshot cũ nếu hợp đồng cho phép; cảnh báo staleness.
4. Sửa nguyên nhân rồi retry có điều phối.
5. Nếu cần rebuild, dùng kế hoạch không làm dashboard mất dữ liệu đột ngột.

### 26.5. Thay đổi định nghĩa SQL

Không coi `REFRESH` là lệnh thay đổi tùy ý query định nghĩa. Khi logic báo cáo thay đổi (thêm currency, sửa timezone, thêm chiều nhóm), cần migration materialized view phù hợp, thay unique index và kiểm chứng output.

Một cách an toàn cho hệ lớn là xây **matview phiên bản mới**, populate/index/compare rồi chuyển readers theo kế hoạch, thay vì chỉnh sửa/phá bản đang phục vụ tùy tiện.

---

## 27. Runbook vận hành bảng tổng hợp

### 27.1. Hợp đồng dữ liệu nguồn

Định nghĩa:

- Nguồn sự kiện nào tạo contribution +?
- Sự kiện nào tạo contribution -?
- Khi nào order coi là paid?
- Có partial refund, tax, discount và currency không?
- Sửa một order phải đảo contribution nào?

Không cho consumer tự suy từ status chưa được định nghĩa.

### 27.2. Hợp đồng grain

```text
PRIMARY KEY:
  (tenant_id, sales_day)

METRICS:
  paid_orders
  gross_amount
```

Nếu muốn currency/product, chỉnh cả khóa và logic delta.

### 27.3. Hợp đồng delivery

- Mỗi change event có ID/version duy nhất.
- Ledger hoặc offset bảo đảm deduplication.
- Source write và event publication không có khoảng mất dữ liệu.
- Có handling retry và out-of-order events.
- Có dead-letter và khả năng replay.

### 27.4. Hợp đồng freshness

- Theo dõi source position/watermark.
- Đo lag của consumer.
- Cảnh báo khi vượt ngưỡng.
- UI/API hiển thị data-as-of khi cần.

### 27.5. Hợp đồng reconciliation

- Đối chiếu theo tenant/ngày và currency nếu có.
- Phát hiện nhóm thiếu/thừa.
- Đối chiếu COUNT/SUM và nhóm đặc biệt.
- Có thủ tục sửa từ source-of-truth.
- Lưu bằng chứng sửa/khôi phục, phân biệt correction event với replay.

### 27.6. Hợp đồng backup/rebuild

- Biết có thể xây lại từ raw data đến mốc nào.
- Nếu raw source bị archive/drop, giữ quyền truy cập hợp lệ cho rebuild.
- Có phương án chuyển đổi không cộng trùng delta.
- Đánh giá thời gian rebuild trong RTO.

### 27.7. Bảo vệ dữ liệu nhạy cảm

Phân quyền writer/reader; không cho application role tùy tiện UPDATE số liệu tổng hợp nếu nghiệp vụ yêu cầu dữ liệu đã kiểm toán. Log thay đổi, giới hạn tenant và kiểm tra các bản sao.

---

## 28. Những sai lầm thường gặp

**1. “View là cache của SELECT.”** Sai. View thông thường lưu định nghĩa truy vấn, không lưu bản sao kết quả.

**2. “View luôn nhanh hơn truy vấn gốc.”** Không. Nó thường dùng chính công việc nguồn cần thiết, chỉ đổi interface SQL.

**3. “View luôn realtime tuyệt đối.”** Không. Đọc theo snapshot/MVCC, có thể chịu replica/cache lag.

**4. “Materialized view tự cập nhật khi base table đổi.”** Không. Cần REFRESH.

**5. “REFRESH CONCURRENTLY là incremental refresh.”** Không. Định nghĩa nguồn vẫn được thực thi lại.

**6. “CONCURRENTLY luôn nhanh hơn REFRESH thường.”** Không. Có thể tốn tài nguyên/chi phí cao hơn.

**7. “REFRESH CONCURRENTLY không cần unique index.”** Sai. Cần unique index đủ điều kiện.

**8. “Partial unique index đủ cho REFRESH CONCURRENTLY.”** Sai.

**9. “Unique expression index cũng đủ.”** Sai. Unique index yêu cầu dùng tên cột, không biểu thức, và bao phủ mọi rows.

**10. “Có thể REFRESH CONCURRENTLY một matview WITH NO DATA chưa populated.”** Không.

**11. “WITH NO DATA nghĩa là SELECT trả 0 rows bình thường.”** Sai; matview chưa populated có trạng thái unscannable.

**12. “Refresh chạy xong lúc 09:10 nghĩa snapshot chắc chắn là 09:10.”** Không. Dữ liệu phụ thuộc snapshot được dùng lúc thực thi.

**13. “Matview luôn cũ đúng bằng chu kỳ cron.”** Không. Duration/failure/lock wait làm staleness thay đổi.

**14. “Matview có thể UPDATE từng row như summary table.”** Không phải cơ chế DML bình thường.

**15. “Bảng tổng hợp tự biết nguồn của nó.”** Không. Nó là bảng thông thường.

**16. “ON CONFLICT cộng delta là exactly once.”** Không. Retry cùng event có thể cộng trùng nếu thiếu deduplication.

**17. “change_id=order_id đủ cho mọi refund/correction.”** Không nếu một order có nhiều business events.

**18. “Không cần backfill vì từ nay job sẽ chạy đúng.”** Sai. Dữ liệu lịch sử có thể thiếu hoặc bị lệch.

**19. “Bảng summary có PRIMARY KEY thì số liệu chắc đúng.”** Không. Constraint không so kết quả với source.

**20. “REFRESH matview chỉ cập nhật những group đã thay đổi.”** Không mặc định trong PostgreSQL lõi.

**21. “Sửa một order đổi ngày chỉ cần cộng vào nhóm mới.”** Sai. Phải trừ nhóm cũ.

**22. “Hoàn tiền chỉ cần giảm amount, không giảm count.”** Không đúng theo metric paid_orders của lab.

**23. “UPDATE status lại lần nữa vẫn cần áp delta -1.”** Không nếu chuyển trạng thái đã được xử lý; cần idempotence/state machine.

**24. “Một summary row bằng 0 luôn giống view không có row.”** Không về cấu trúc; API phải thống nhất.

**25. “AVG của daily AVG bằng AVG toàn kỳ.”** Sai nếu ngày có số lượng đơn khác nhau.

**26. “Distinct counts cộng được giữa các ngày.”** Không với các nhóm có thực thể trùng.

**27. “SUM(DISTINCT amount) sửa được JOIN fanout.”** Không, vì các orders khác nhau có thể cùng amount.

**28. “Cộng nhiều currency trong cùng một SUM là bình thường.”** Không nếu chưa có quy tắc quy đổi.

**29. “SUM gross_amount từ trạng thái paid luôn là revenue kế toán chính thức.”** Không. Cần xác nhận định nghĩa nghiệp vụ.

**30. “Một view có GROUP BY tự update được như view SELECT một bảng.”** Không.

**31. “Index trên view thông thường tạo giống index trên table.”** Không. Tạo index trên bảng nguồn hoặc materialize.

**32. “Index trên orders cũng là index của materialized view.”** Không. Hai relation có index riêng.

**33. “View luôn pushdown mọi predicate qua GROUP BY/LIMIT/security barrier.”** Không bảo đảm.

**34. “SELECT trên matview tự dùng RLS source ở thời điểm đọc.”** Không được giả định. Phải kiểm soát quyền trên dữ liệu đã materialize.

**35. “Thêm summary table làm write latency bằng 0.”** Không. UPSERT/ledger có WAL, locks và contention.

**36. “Lưu updated_at ở từng group chứng minh mọi event trước mốc đã xử lý.”** Không. Cần watermark có semantics rõ.

**37. “Rebuild bằng DELETE + INSERT là online và miễn phí.”** Không. Có WAL, locks và rủi ro xung đột với consumer.

**38. “Báo cáo theo ngày UTC giống ngày local của mọi tenant.”** Sai. Cần timezone policy.

**39. “DROP raw partitions tự xóa dữ liệu trong matview/summary.”** Không.

**40. “Chỉ đo SELECT nhanh nhất là đủ chọn kiến trúc.”** Không. Cần cost refresh/write, storage, freshness và recovery.

---

## 29. Bài tập thực hành có đáp án

### Bài 1 — Chọn phương án đơn giản nhất

**Tình huống:** 200 nghìn orders, 10 người dùng xem báo cáo mỗi giờ, query GROUP BY mất 40 ms, cần dữ liệu sau commit.

**Đáp án:** Bắt đầu với **view** hoặc truy vấn trực tiếp; chưa có lý do rõ để materialize hay xây event pipeline.

### Bài 2 — Chọn materialized view

**Tình huống:** 70 triệu orders, báo cáo được đọc 300 lần/phút, chấp nhận dữ liệu trễ 20 phút, refresh mất 3 phút.

**Đáp án:** Materialized view đáng đánh giá. Cần đo end-to-end freshness, locks và tải refresh thực tế.

### Bài 3 — Chọn summary table

**Tình huống:** 500 triệu orders, report cần phản ánh thay đổi trong vài giây, full REFRESH mất 20 phút.

**Đáp án:** Xem xét summary table theo delta/batch với idempotency, watermark và reconciliation; đánh giá hot-row contention.

### Bài 4 — Grain của báo cáo

**Yêu cầu:** doanh thu paid theo tenant, ngày và currency.

**Đáp án:** Grain là `(tenant_id,sales_day,currency)`; khóa nhóm, unique index hoặc PK phải bao gồm cả ba nếu một hàng là một nhóm.

### Bài 5 — VIEW có lưu ba hàng kết quả?

**Đáp án:** Không. `v_daily_sales` chỉ lưu định nghĩa SELECT; GROUP BY được thực hiện theo truy vấn trên source.

### Bài 6 — Tạo VIEW

**Đáp án:**

```sql
CREATE VIEW view_choice_lab.v_daily_sales AS
SELECT
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date AS sales_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS gross_amount
FROM view_choice_lab.orders
WHERE status='paid'
GROUP BY tenant_id,
         (ordered_at AT TIME ZONE 'UTC')::date;
```

Trong lab đã có view cùng tên; đây là cú pháp minh họa, không chạy lại.

### Bài 7 — INSERT mới ảnh hưởng thế nào?

**Tình huống:** Thêm order paid 30.00 vào tenant 1 ngày 01/11 sau khi ba phương án đã được bootstrap.

**Đáp án:** View truy vấn nguồn mới có **3/230.00**. MV vẫn **2/200.00** trước REFRESH. Summary vẫn **2/200.00** trước khi áp delta.

### Bài 8 — Materialized view cần làm gì?

**Đáp án:**

```sql
REFRESH MATERIALIZED VIEW
    view_choice_lab.mv_daily_sales;
```

Sau refresh, kết quả phản ánh snapshot nguồn được dùng trong quá trình refresh.

### Bài 9 — Khác biệt của CONCURRENTLY

**Câu hỏi:** `REFRESH ... CONCURRENTLY` có nghĩa chỉ scan orders vừa thay đổi không?

**Đáp án:** Không. Nó điều chỉnh cách thay kết quả để hỗ trợ readers đồng thời tốt hơn trong những trường hợp hợp lệ; query định nghĩa vẫn được thực hiện lại.

### Bài 10 — Unique index cho CONCURRENTLY

**Đáp án:**

```sql
CREATE UNIQUE INDEX mv_daily_sales_tenant_day_uidx
ON view_choice_lab.mv_daily_sales (tenant_id, sales_day);
```

Index đã tồn tại trong lab; không tạo trùng. Unique index phải phủ mọi rows và dùng các tên cột, không phải expression/partial.

### Bài 11 — WITH NO DATA

**Câu hỏi:** Matview `WITH NO DATA` chưa refresh có thể SELECT bình thường như bảng rỗng không?

**Đáp án:** Không. Nó chưa populated và được đánh dấu unscannable. Cần REFRESH thường để populate trước.

### Bài 12 — REFRESH đầu tiên

**Câu hỏi:** Có thể dùng `REFRESH CONCURRENTLY` ngay cho matview chưa populated không?

**Đáp án:** Không. Populate lần đầu bằng REFRESH không CONCURRENTLY.

### Bài 13 — Summary table có tự đồng bộ?

**Đáp án:** Không. Nó là một bảng thường, cần job/transaction/trigger/event pipeline.

### Bài 14 — Upsert delta

**Đáp án:**

```sql
INSERT INTO view_choice_lab.daily_sales_summary AS s
    (tenant_id,sales_day,paid_orders,gross_amount)
VALUES (1,DATE '2026-11-01',1,30.00)
ON CONFLICT (tenant_id,sales_day)
DO UPDATE SET
    paid_orders=s.paid_orders+EXCLUDED.paid_orders,
    gross_amount=s.gross_amount+EXCLUDED.gross_amount;
```

**Chỉ minh họa cú pháp**; không chạy lại cùng delta nếu đã áp ở mục 11.

### Bài 15 — Retry của delta

**Câu hỏi:** Nếu thực hiện câu UPSERT `+30` hai lần cho cùng một order, số liệu có đúng không?

**Đáp án:** Không. Nó cộng 60. Cần ID change event và ledger/deduplication hoặc cơ chế bảo đảm effect đúng một lần.

### Bài 16 — Vì sao change_id không chỉ là order_id?

**Đáp án:** Một order có thể có sự kiện paid, refunded và corrected. Mỗi **change event** cần ID/version độc lập để vừa chống trùng vừa cho phép những thay đổi hợp lệ kế tiếp.

### Bài 17 — Delta refund

**Yêu cầu:** Order paid 80 trở thành refunded; metric chỉ tính paid.

**Đáp án:** Delta `paid_orders=-1`, `gross_amount=-80` ở grain cũ, theo transaction/state machine được kiểm soát.

### Bài 18 — Đổi ngày/tenant

**Đáp án:** Bù trừ contribution của grain cũ và cộng lại grain mới theo dữ liệu sau thay đổi; không chỉ cộng một phía.

### Bài 19 — Nhóm không còn đơn paid

**Câu hỏi:** View không có hàng, summary có hàng 0. Có thể coi chúng luôn giống nhau không?

**Đáp án:** Không về cấu trúc SQL. Phải thống nhất quy tắc hiển thị/đối chiếu và có thể dùng COALESCE hoặc xóa group 0.

### Bài 20 — Đối chiếu missing groups

**Đáp án:** Dùng `FULL OUTER JOIN` trên `(tenant_id,sales_day)` giữa view chuẩn và summary, so `COUNT/SUM` với `COALESCE` theo quy ước 0/missing.

### Bài 21 — AVG theo tháng

**Câu hỏi:** Có nên lấy AVG của AVG theo ngày?

**Đáp án:** Không nếu số orders/ngày khác nhau. Tính `SUM(gross_amount)/NULLIF(SUM(paid_orders),0)`.

### Bài 22 — Distinct customer

**Câu hỏi:** Tổng khách unique từng ngày có bằng khách unique cả tháng không?

**Đáp án:** Không nếu khách xuất hiện ở nhiều ngày. Metric COUNT DISTINCT là non-additive trong tình huống ấy.

### Bài 23 — JOIN fanout

**Câu hỏi:** Một order có 3 items; `SUM(order.amount)` sau JOIN raw items sai bao nhiêu?

**Đáp án:** Nếu amount bị lặp lại ba lần, SUM cộng gấp ba contribution của order đó. Phải aggregate đúng grain trước/sau JOIN.

### Bài 24 — Index của view

**Câu hỏi:** Có thể `CREATE INDEX ON v_daily_sales` như bảng thường không?

**Đáp án:** Không. View thường không lưu rows. Tạo index trên source phù hợp hoặc dùng matview/bảng tổng hợp.

### Bài 25 — Index của matview

**Câu hỏi:** Index trên `orders(tenant_id,ordered_at)` có tự là index của matview không?

**Đáp án:** Không. Tạo index riêng trên materialized view nếu muốn truy vấn kết quả đã materialize nhanh.

### Bài 26 — MVCC

**Câu hỏi:** View có luôn thấy mọi COMMIT mới trong một transaction `REPEATABLE READ` đang mở?

**Đáp án:** Không. Transaction lặp lại snapshot theo isolation; việc view không cache không bỏ qua MVCC.

### Bài 27 — Refresh lâu

**Tình huống:** job chạy mỗi 10 phút nhưng mỗi refresh mất 25 phút.

**Đáp án:** Không thể coi lịch 10 phút là bảo đảm freshness 10 phút. Cần đo duration/wait và thiết kế lại.

### Bài 28 — Tenant isolation

**Câu hỏi:** Có thể cấp SELECT toàn bộ matview đa tenant cho role tenant rồi chỉ dựa vào client WHERE tenant_id không?

**Đáp án:** Không nên. Thiết kế permissions/RLS/interface truy cập riêng để không lộ dữ liệu tenant khác.

### Bài 29 — Currency

**Câu hỏi:** Có thể cộng 100 USD và 100 VND thành 200 đơn vị tiền để làm daily summary không?

**Đáp án:** Không. Thêm currency vào grain hoặc có quy tắc tỷ giá/quy đổi được kiểm soát.

### Bài 30 — Partition source đã DROP

**Câu hỏi:** DROP một partition source có tự xóa dữ liệu lịch sử từ materialized view hoặc summary không?

**Đáp án:** Không. Những dữ liệu đã materialize hoặc copy riêng phải được quản lý theo retention của chúng.

### Bài 31 — Source snapshot và updated_at

**Câu hỏi:** `summary.updated_at=09:00` có chứng minh tất cả changes trước 09:00 đã áp dụng không?

**Đáp án:** Không. Nó chỉ cho biết row summary được ghi lúc đó, không chứng minh offset/watermark của source.

### Bài 32 — Tăng độ chính xác của quyết định

**Yêu cầu:** liệt kê ba phép đo tối thiểu trước khi chuyển từ view sang matview.

**Đáp án:** (1) latency/tần suất query view, (2) thời gian và tải REFRESH trên dữ liệu thực, (3) freshness SLA cùng số liệu staleness quan sát được. Nên đo thêm locks, index/storage, replica lag và failure handling.

---

## 30. Checklist quyết định kiến trúc

### Định nghĩa nghiệp vụ

1. **Một hàng report đại diện điều gì?** Grain đã được chốt chưa?
2. **Measure có đúng không?** Paid/refunded/gross/net, VAT, discounts và currency?
3. **Ngày theo timezone nào?** UTC hay từng tenant?
4. **Group nào cần xuất hiện khi count=0?** Không có row hay row 0?
5. **Có yêu cầu aggregate lên tháng/năm?** AVG/distinct có additive không?

### Phân tích truy vấn

6. **Chi phí query nguồn hiện tại?** `EXPLAIN (ANALYZE, BUFFERS)` trên SELECT an toàn.
7. **Bao nhiêu lần đọc?** API/QPS, concurrency, peak traffic.
8. **Bao nhiêu lần ghi/correction?** INSERT/UPDATE/DELETE/source events.
9. **Độ lớn kết quả GROUP BY?** Rows và storage.
10. **Query có lọc nhiều chiều tùy ý?** Có đủ tổ hợp để materialize không?
11. **Index nguồn và kết quả phù hợp?** Key order, partial indexes, stats.

### Freshness và consistency

12. **Độ mới chấp nhận được?** Xác định SLA theo commit/watermark.
13. **View có đủ nhanh nếu đọc snapshot mới?**
14. **Matview refresh có đủ nhanh và ổn định?**
15. **Summary có nguồn event đáng tin?** Outbox/CDC/transaction.
16. **Có idempotency?** Event ID/version + deduplication.
17. **Có xử lý refund, sửa ngày, xóa và late events?**
18. **Có reconciliation và rebuild?**
19. **Có watermark đáng tin và báo động vượt SLA?**

### Vận hành và bảo mật

20. **Matview đã populated?** Nếu refresh concurrent có unique index đúng quy tắc?
21. **Refresh có tạo lock contention?** Có backlog/failure policy?
22. **Summary có hot-row contention?** Có cần batching?
23. **Index, WAL, disk, replication lag có phù hợp?**
24. **Bảo mật tenant?** Owner/invoker/RLS, grants trên copied data?
25. **Retention?** Các bản sao trong MV/summary/cache/backup được quản lý?
26. **Rollback khi migration thất bại?** Có versioned report và fallback?
27. **Có kiểm tra kết quả nghiệp vụ trước/sau chuyển đổi?**
28. **Đã tính tổng chi phí vận hành?** Không chỉ latency của SELECT.

---

## 31. Kết luận: chọn phương án theo hợp đồng, không theo tên công nghệ

**View** là lựa chọn hợp lý khi cần một giao diện SQL rõ ràng, muốn nhìn thấy dữ liệu theo snapshot nguồn mới và query nền đủ nhanh. View không lưu kết quả tổng hợp, không tự xóa chi phí scan/join/aggregate.

**Materialized view** hợp lý khi kết quả tổng hợp được đọc rất nhiều lần, phép tính nguồn đắt nhưng có thể chấp nhận dữ liệu cũ tới một giới hạn rõ ràng. Nó có thể được index và phục vụ SELECT rất nhanh; đổi lại phải lên lịch `REFRESH`, đo lock/chi phí, theo dõi staleness và hiểu rằng `CONCURRENTLY` **không phải incremental refresh**.

**Bảng tổng hợp** hợp lý khi báo cáo lớn phải cập nhật nhanh theo sự kiện hoặc cần quy tắc bảo trì riêng. Nó cho phép `UPSERT` theo delta và thiết kế watermark/ledger, nhưng phải tự giải quyết **idempotency, correction, old/new grain, failure recovery và reconciliation**. Tốc độ SELECT tốt không biện minh cho số liệu sai.

### Một nguyên tắc quyết định thực dụng

```text
                  Cần báo cáo tổng hợp?
                           |
                           v
        Query trực tiếp từ nguồn đủ nhanh?
                  /                  \
                Có                  Không
                |                     |
                v                     v
             Dùng VIEW      Chấp nhận refresh theo kỳ
                                  và có SLA trễ?
                                  /          \
                                Có           Không
                                |              |
                                v              v
                         MATERIALIZED     SUMMARY TABLE
                             VIEW          / pipeline
                                |              |
                          Đo refresh     Thiết kế delta,
                          và staleness   idempotency, reconcile
```

Sơ đồ này là **điểm khởi đầu**, không phải thuật toán bắt buộc. Khi workloads đa dạng, có thể kết hợp view, matview, summary table và hệ analytics chuyên biệt với định nghĩa metric thống nhất.

**Câu hỏi quan trọng nhất trước khi quyết định:** “Báo cáo này phải đúng **tới thời điểm nào**, với **mức độ chính xác nghiệp vụ nào**, và hệ thống sẵn sàng trả chi phí tính toán **lúc đọc, lúc refresh hay lúc cập nhật nguồn**?”

### Tài liệu PostgreSQL chính thức

- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html).
- [Rules and Views](https://www.postgresql.org/docs/current/rules-views.html).
- [Updatable Views](https://www.postgresql.org/docs/current/rules-views.html#RULES-VIEWS-UPDATE).
- [CREATE MATERIALIZED VIEW](https://www.postgresql.org/docs/current/sql-creatematerializedview.html).
- [REFRESH MATERIALIZED VIEW](https://www.postgresql.org/docs/current/sql-refreshmaterializedview.html).
- [Materialized Views](https://www.postgresql.org/docs/current/rules-materializedviews.html).
- [CREATE UNIQUE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html).
- [INSERT ... ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html).
- [CREATE TABLE / Constraints](https://www.postgresql.org/docs/current/sql-createtable.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
- [Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html).
