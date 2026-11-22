# WITH CHECK OPTION và giới hạn dữ liệu được ghi qua VIEW

Một **view** trong SQL đặt tên cho một câu truy vấn để người dùng đọc dữ liệu theo một cách nhìn có chủ đích. Chẳng hạn, thay vì cho bộ phận chăm sóc khách hàng xem tất cả đơn hàng, hệ thống có thể tạo view chỉ hiển thị các đơn **đang là bản nháp** của một tổ chức.

```sql
CREATE VIEW v_draft_orders AS
SELECT order_id, tenant_id, customer_id, status, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'DRAFT';
```

Câu hỏi phát sinh khi view **cho phép ghi**: nếu người dùng `UPDATE` một hàng đang là `DRAFT` thành `PAID`, hoặc `INSERT` một đơn có `tenant_id = 20` qua view trên, điều gì sẽ xảy ra?

Trong các hệ quản trị hỗ trợ **updatable view**, việc ghi qua view có thể làm thay đổi **bảng gốc**. Nếu không có cơ chế ràng buộc bổ sung, một bản ghi được chèn/cập nhật qua view có thể **biến mất khỏi chính view đó** vì không còn thỏa điều kiện `WHERE`.

Mệnh đề **`WITH CHECK OPTION`** giải quyết vấn đề này bằng cách kiểm tra hàng sau khi ghi: thao tác `INSERT` hoặc `UPDATE` qua view chỉ được chấp nhận nếu hàng mới **thỏa điều kiện hiển thị của view theo phạm vi kiểm tra được yêu cầu**. Với những view lồng nhau, một số DBMS như PostgreSQL và MySQL phân biệt **`LOCAL`** và **`CASCADED`**.

Bài học thuộc chương **View và bảng trung gian** của module Database SQL. Nội dung tập trung vào:

- View có thể cập nhật được khác view chỉ đọc ở điểm nào.
- Vì sao `WHERE` khi đọc không đủ giới hạn việc **ghi**.
- Cách dùng `WITH CHECK OPTION` để chặn hàng được ghi nhưng không còn nằm trong view.
- Phân biệt `WITH LOCAL CHECK OPTION` và `WITH CASCADED CHECK OPTION` khi có nhiều tầng view.
- Tác động đối với `INSERT`, `UPDATE`, `DELETE`, `NULL` và ràng buộc của bảng gốc.
- Sự khác nhau giữa PostgreSQL, MySQL/MariaDB, SQL Server, Oracle và SQLite.
- Vì sao CHECK OPTION **không thay thế** phân quyền, Row-Level Security (RLS), khóa ngoại hay quy tắc nghiệp vụ.

> Phần thực hành chính sử dụng **PostgreSQL**, với các bảng và view tạm trong một phiên kết nối. Các câu lệnh làm thay đổi dữ liệu được trình bày như **những thử nghiệm riêng**. Để so sánh kết quả, có thể dùng transaction kèm `ROLLBACK` hoặc tạo lại dữ liệu mẫu. Các phần dành cho DBMS khác có ghi rõ phương ngữ.

## 1. View là kết quả truy vấn logic, không mặc nhiên là bảng lưu trữ

Xét câu lệnh:

```sql
CREATE VIEW v_active_customers AS
SELECT customer_id, customer_name
FROM customers
WHERE customer_status = 'ACTIVE';
```

Sau khi tạo, người dùng có thể đọc:

```sql
SELECT customer_id, customer_name
FROM v_active_customers
ORDER BY customer_id;
```

Một view thông thường thường **không tự lưu một bản sao riêng** của các hàng được chọn. Nó mô tả câu truy vấn dùng để lấy dữ liệu từ bảng nguồn. Các thay đổi ở bảng nguồn có thể làm tập hàng mà view hiển thị thay đổi khi truy vấn tiếp theo được đánh giá.

Điều này khác **temporary table** hoặc **materialized view**:

| Đối tượng | Dữ liệu nhìn thấy đến từ đâu? | Ghi qua đối tượng? |
|---|---|---|
| View thông thường | Truy vấn định nghĩa view trên bảng/view nguồn | Có thể nếu view và DBMS cho phép; không mặc nhiên |
| Temporary table | Dữ liệu thật được lưu trong bảng tạm theo phạm vi phiên/giao dịch | Thường ghi như bảng phù hợp |
| Materialized view | Kết quả truy vấn đã được lưu và làm mới theo cơ chế riêng | Phụ thuộc DBMS; không áp dụng CHECK OPTION như updatable view thông thường |
| Bảng gốc | Các hàng được lưu trong bảng | Theo quyền và ràng buộc của bảng |

**`WITH CHECK OPTION` dành cho việc ghi qua view có điều kiện**, không phải cơ chế “vật chất hóa” hoặc tạo bộ lọc tự động khi ghi trực tiếp vào bảng gốc.

## 2. Khi nào một view cho phép INSERT, UPDATE hoặc DELETE?

Một view đơn giản có thể được DBMS đánh giá là **automatically updatable**: có thể ánh xạ thao tác ghi trên view sang bảng bên dưới mà không cần lập trình thủ công.

Ví dụ ý tưởng:

```sql
CREATE VIEW v_orders_simple AS
SELECT order_id, tenant_id, customer_id, status
FROM orders
WHERE tenant_id = 10;
```

Vì view chọn các cột trực tiếp của **một bảng** và lọc bằng `WHERE`, nhiều DBMS có thể cho phép một số thao tác `INSERT`, `UPDATE` và `DELETE` thông qua view nếu quyền, schema và quy tắc engine cho phép.

Ngược lại, các view có phép tổng hợp hoặc một số phép toán phức tạp thường không tự cập nhật được:

```sql
CREATE VIEW v_order_totals AS
SELECT tenant_id, COUNT(*) AS number_of_orders
FROM orders
GROUP BY tenant_id;
```

Không có một quy tắc hiển nhiên để diễn giải:

```sql
UPDATE v_order_totals
SET number_of_orders = 100
WHERE tenant_id = 10;
```

thành các thay đổi cụ thể ở bảng `orders`. Vì vậy, các view có `GROUP BY`, aggregate, `DISTINCT`, set operations, hoặc JOIN phức tạp có thể không hỗ trợ DML tự động.

**CHECK OPTION không biến view chỉ đọc thành updatable view.** Muốn ghi qua view, cần đáp ứng **cả hai**: view có thể cập nhật theo cơ chế DBMS và thao tác ghi vượt qua các kiểm tra/ràng buộc áp dụng.

### 2.1. Các điều kiện updatable view thường gặp trong PostgreSQL

Với **view được PostgreSQL tự động cho phép cập nhật**, các điều kiện chính gồm:

- `FROM` ở cấp truy vấn view chứa đúng **một** quan hệ nguồn là bảng hoặc một view cũng có thể cập nhật.
- Không có các cấu trúc làm mất phép ánh xạ hàng đơn giản như `DISTINCT`, `GROUP BY`, `HAVING`, `LIMIT`, `OFFSET` hoặc các phép tập hợp ở cấp truy vấn.
- Danh sách chọn không có hàm tổng hợp, hàm cửa sổ hoặc set-returning functions gây mất tính updatable theo quy tắc engine.
- Cột được cập nhật phải ánh xạ được tới cột ghi của bảng nguồn; một biểu thức tính toán trong SELECT không mặc nhiên ghi được.

Đây là mô tả để nhận diện dạng view đơn giản, **không phải thuật toán hoàn chỉnh** áp dụng mọi phiên bản. Nếu view có `INSTEAD OF` trigger/rule, khả năng ghi và mức áp dụng CHECK OPTION có các quy tắc riêng cần kiểm tra.

## 3. Dữ liệu mẫu PostgreSQL

Tạo bảng đơn hàng có mã định danh rõ ràng, điều kiện trạng thái và một số ràng buộc cơ bản.

```sql
-- PostgreSQL. TEMP dùng để thử nghiệm trong phiên đang mở.
CREATE TEMP TABLE demo_view_orders (
    order_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(12,2) NOT NULL
        CHECK (total_amount >= 0),
    created_on DATE NOT NULL,
    internal_note TEXT NOT NULL DEFAULT 'none'
);

INSERT INTO demo_view_orders
    (order_id, tenant_id, customer_id, status,
     total_amount, created_on, internal_note)
VALUES
    (101, 10, 1001, 'DRAFT',     100.00, DATE '2026-11-01', 'call back'),
    (102, 10, 1002, 'PAID',      250.00, DATE '2026-11-02', 'paid'),
    (103, 20, 2001, 'DRAFT',     300.00, DATE '2026-11-03', 'other tenant'),
    (104, 10, 1003, 'CANCELLED',  90.00, DATE '2026-11-04', 'cancelled'),
    (105, 10, 1004, 'DRAFT',     450.00, DATE '2026-11-05', 'follow up'),
    (106, 20, 2002, 'PAID',      180.00, DATE '2026-11-06', 'other tenant');
```

| order_id | tenant_id | customer_id | status | total_amount |
|---:|---:|---:|---|---:|
| 101 | 10 | 1001 | DRAFT | 100.00 |
| 102 | 10 | 1002 | PAID | 250.00 |
| 103 | 20 | 2001 | DRAFT | 300.00 |
| 104 | 10 | 1003 | CANCELLED | 90.00 |
| 105 | 10 | 1004 | DRAFT | 450.00 |
| 106 | 20 | 2002 | PAID | 180.00 |

Ta muốn tạo một view chỉ chứa **đơn DRAFT của tenant 10**. Theo dữ liệu ban đầu, view này chỉ hiển thị **101** và **105**.

Các ví dụ dùng khóa `order_id` do người viết cung cấp. Không có cơ chế tự sinh ID ở bảng mẫu để việc quan sát tập hàng dễ dàng hơn.

## 4. Không có CHECK OPTION: ghi xong, hàng có thể biến mất

Tạo view **chưa bật kiểm tra**:

```sql
CREATE TEMP VIEW v_t10_drafts_unchecked AS
SELECT
    order_id, tenant_id, customer_id,
    status, total_amount, created_on
FROM demo_view_orders
WHERE tenant_id = 10
  AND status = 'DRAFT';
```

Đọc view:

```sql
SELECT order_id, tenant_id, status
FROM v_t10_drafts_unchecked
ORDER BY order_id;
-- 101 | 10 | DRAFT
-- 105 | 10 | DRAFT
```

### 4.1. UPDATE khiến hàng rời khỏi view

Thử trong transaction PostgreSQL:

```sql
BEGIN;

UPDATE v_t10_drafts_unchecked
SET status = 'PAID'
WHERE order_id = 101
RETURNING order_id, tenant_id, status;
-- 101 | 10 | PAID

SELECT order_id, tenant_id, status
FROM v_t10_drafts_unchecked
ORDER BY order_id;
-- Chỉ còn 105 trong view.

SELECT order_id, tenant_id, status
FROM demo_view_orders
WHERE order_id = 101;
-- 101 | 10 | PAID: hàng vẫn còn trong bảng gốc.

ROLLBACK;
-- Trạng thái của 101 trở lại DRAFT.
```

Vì sao điều này xảy ra?

1. Ở thời điểm tìm hàng, đơn 101 **đang hiển thị** qua view nên có thể được chọn để UPDATE.
2. Câu UPDATE thay đổi `status` ở bảng gốc từ `DRAFT` thành `PAID`.
3. Sau cập nhật, hàng **không còn thỏa** điều kiện `status = 'DRAFT'`.
4. View không còn trả hàng 101, dù bảng gốc vẫn chứa hàng ấy.

Đây là hành vi có thể hợp lệ nếu view không có CHECK OPTION. **`WHERE` trong định nghĩa view giới hạn những hàng được nhìn thấy để thao tác**, chứ không mặc nhiên buộc các giá trị **sau khi ghi** vẫn nằm trong view.

### 4.2. INSERT có thể tạo hàng không xuất hiện trong view

```sql
BEGIN;

INSERT INTO v_t10_drafts_unchecked
    (order_id, tenant_id, customer_id, status,
     total_amount, created_on)
VALUES
    (201, 20, 2003, 'DRAFT', 500.00, DATE '2026-11-07');

SELECT order_id
FROM v_t10_drafts_unchecked
WHERE order_id = 201;
-- Không có hàng.

SELECT order_id, tenant_id, status
FROM demo_view_orders
WHERE order_id = 201;
-- 201 | 20 | DRAFT

ROLLBACK;
```

Hàng 201 được chèn vào **bảng gốc**, nhưng tenant của nó là 20 nên không thỏa view tenant 10.

### 4.3. Đây có phải lỗi PostgreSQL?

Không. Khi người dùng được phép ghi qua một updatable view **không có CHECK OPTION**, việc hàng mới không còn nằm trong tập view có thể là hành vi được hệ quản trị cho phép.

Điều đáng lo là ứng dụng có thể hiểu sai: “Tôi tạo đơn qua màn hình DRAFT của tenant 10, lệnh INSERT báo thành công, nhưng mở lại màn hình không thấy đơn.” CHECK OPTION giúp biến những thao tác mâu thuẫn với tập view thành **lỗi rõ ràng** thay vì ghi xong rồi “biến mất”.

## 5. WITH CHECK OPTION: giữ hàng được ghi trong tập nhìn thấy

Định nghĩa view có CHECK OPTION:

```sql
CREATE TEMP VIEW v_t10_drafts_checked AS
SELECT
    order_id, tenant_id, customer_id,
    status, total_amount, created_on
FROM demo_view_orders
WHERE tenant_id = 10
  AND status = 'DRAFT'
WITH CHECK OPTION;
```

Trong PostgreSQL, `WITH CHECK OPTION` không ghi chế độ là dạng **`CASCADED` mặc định**. Nếu chỉ có một tầng view như trên, khác biệt giữa `LOCAL` và `CASCADED` chưa tạo ra kết quả khác.

### 5.1. INSERT hợp lệ

```sql
BEGIN;

INSERT INTO v_t10_drafts_checked
    (order_id, tenant_id, customer_id,
     status, total_amount, created_on)
VALUES
    (202, 10, 2004, 'DRAFT', 600.00, DATE '2026-11-08')
RETURNING order_id, tenant_id, status;
-- 202 | 10 | DRAFT

SELECT order_id
FROM v_t10_drafts_checked
WHERE order_id = 202;
-- Có hàng 202.

ROLLBACK;
```

Hàng 202 thỏa đồng thời:

```sql
tenant_id = 10
AND status = 'DRAFT'
```

nên CHECK OPTION cho phép ghi nếu các ràng buộc khác của bảng cũng được thỏa mãn.

### 5.2. INSERT không thỏa điều kiện view

```sql
-- Thử RIÊNG: PostgreSQL trả lỗi CHECK OPTION của view.
INSERT INTO v_t10_drafts_checked
    (order_id, tenant_id, customer_id,
     status, total_amount, created_on)
VALUES
    (203, 20, 2005, 'DRAFT', 700.00, DATE '2026-11-09');
```

Hàng có `tenant_id = 20` không thuộc view tenant 10 nên bị từ chối, dù `tenant_id = 20` không vi phạm `NOT NULL` hay `CHECK` của bảng gốc.

Tương tự:

```sql
-- Thử RIÊNG: status là PAID, không thuộc view DRAFT.
INSERT INTO v_t10_drafts_checked
    (order_id, tenant_id, customer_id,
     status, total_amount, created_on)
VALUES
    (204, 10, 2006, 'PAID', 800.00, DATE '2026-11-10');
```

Trường hợp thứ hai hợp lệ về giá trị trạng thái tại bảng gốc, nhưng **không hợp lệ khi được ghi qua view DRAFT**.

### 5.3. UPDATE làm hàng rời view bị chặn

```sql
-- Thử RIÊNG: đơn 101 đang là DRAFT.
UPDATE v_t10_drafts_checked
SET status = 'PAID'
WHERE order_id = 101;
```

PostgreSQL từ chối vì sau UPDATE, hàng không còn thỏa `status = 'DRAFT'`.

Điểm cần nhớ:

- `WHERE order_id = 101` xác định **hàng cũ** đang được chọn để cập nhật.
- `WITH CHECK OPTION` kiểm tra **hàng mới** sau cập nhật có còn thỏa predicate của view không.
- Vì trạng thái mới là `PAID`, CHECK OPTION chặn.
- Hàng 101 ở bảng gốc vẫn là `DRAFT` sau câu UPDATE bị lỗi, với giả định không có thao tác độc lập khác.

### 5.4. UPDATE cột không ảnh hưởng điều kiện view

```sql
BEGIN;

UPDATE v_t10_drafts_checked
SET total_amount = 125.00
WHERE order_id = 101
RETURNING order_id, status, total_amount;
-- 101 | DRAFT | 125.00

ROLLBACK;
```

Cập nhật giá trị `total_amount` không làm hàng rời tập DRAFT tenant 10, nên CHECK OPTION không chặn. Nhưng nếu đổi thành `total_amount = -10`, ràng buộc `CHECK(total_amount >= 0)` của **bảng gốc** vẫn chặn thao tác. Hai kiểm tra cùng tồn tại, phục vụ hai mục tiêu khác nhau.

## 6. CHECK OPTION áp dụng cho hàng **sau** INSERT/UPDATE

Có thể hiểu logic bằng hai bước:

```text
INSERT/UPDATE qua view
          |
          v
DBMS xác định hàng sẽ ghi vào bảng gốc
          |
          v
Kiểm tra điều kiện của view áp dụng (CHECK OPTION)
          |
       +--+--+
       |     |
      TRUE   FALSE hoặc UNKNOWN
       |     |
       v     v
  Có thể   Từ chối
  tiếp tục  thao tác
  ghi       ở hàng đó
       |
       v
Còn phải thỏa CHECK/NOT NULL/UNIQUE/FK/quyền/trigger...
```

Sơ đồ là cách hình dung **ngữ nghĩa**, không khẳng định thứ tự vật lý tuyệt đối của mọi bước thực thi/triggers trên tất cả DBMS.

Nếu điều kiện view là:

```sql
WHERE tenant_id = 10
  AND status = 'DRAFT'
```

hàng sau ghi phải **thực sự thỏa** các điều kiện đó; không đủ nếu chỉ trước khi ghi nó còn được nhìn thấy.

### 6.1. Điều kiện view không tự tạo giá trị khi INSERT

Giả sử muốn chèn một bản nháp mà **không truyền `tenant_id` và `status`**:

```sql
-- Không hợp lệ với schema mẫu vì thiếu các cột NOT NULL
-- và không có DEFAULT cung cấp tenant_id/status.
INSERT INTO v_t10_drafts_checked
    (order_id, customer_id, total_amount, created_on)
VALUES
    (205, 2007, 900.00, DATE '2026-11-11');
```

View có `WHERE tenant_id = 10 AND status = 'DRAFT'` **không có nghĩa** DBMS sẽ tự điền `tenant_id = 10` và `status = 'DRAFT'` khi INSERT. Các cột bị bỏ qua vẫn theo quy tắc **DEFAULT/NULL/ràng buộc của bảng gốc**.

Nếu muốn mặc định các giá trị, cần thiết kế default, câu INSERT nêu rõ giá trị hoặc cơ chế phù hợp. CHECK OPTION **kiểm tra**, không phải lệnh **điền/chỉnh** dữ liệu.

### 6.2. Không phải tất cả cột hiển thị đều sửa được

Ví dụ view:

```sql
CREATE TEMP VIEW v_t10_amounts AS
SELECT
    order_id,
    total_amount,
    total_amount * 0.10 AS calculated_fee
FROM demo_view_orders
WHERE tenant_id = 10;
```

`calculated_fee` là biểu thức tính, không tự ánh xạ thành cột ghi trong bảng. Trong PostgreSQL, các cột đơn giản như `total_amount` có thể cập nhật theo quy tắc view, nhưng `calculated_fee` không tự biến thành cột updatable chỉ vì view hiển thị nó.

`WITH CHECK OPTION` cũng không làm biểu thức `calculated_fee` trở thành một đích ghi hợp lệ.

## 7. Ghi nhiều hàng: chỉ một hàng vi phạm thì sao?

Với PostgreSQL, một câu `INSERT` thông thường là **một statement nguyên tử**. Nếu một hàng đầu vào vi phạm CHECK OPTION và làm statement lỗi, các hàng khác thuộc **cùng statement** không được commit riêng.

```sql
-- PostgreSQL: thử riêng ngoài transaction dài.
INSERT INTO v_t10_drafts_checked
    (order_id, tenant_id, customer_id, status,
     total_amount, created_on)
VALUES
    (211, 10, 2011, 'DRAFT', 100.00, DATE '2026-11-11'),
    (212, 10, 2012, 'PAID',  200.00, DATE '2026-11-12');
```

- 211 phù hợp với view.
- 212 có `status = 'PAID'`, vi phạm điều kiện view.
- **Cả câu INSERT thất bại**; không được xem 211 là đã chèn thành công riêng.

Đây không phải chính sách “bỏ qua hàng lỗi” giống một số công cụ nhập dữ liệu đặc biệt. Muốn xử lý từng hàng hợp lệ/lỗi của một file, thường cần **bảng staging** và quy trình kiểm tra, tách dữ liệu trước khi ghi qua view hoặc bảng đích.

### 7.1. PostgreSQL lỗi trong transaction và SAVEPOINT

Trong PostgreSQL, nếu một statement lỗi khi đang ở trong `BEGIN`, transaction thường bị đánh dấu **aborted**. Không thể tiếp tục chạy `SELECT`/`UPDATE` như thường cho đến khi `ROLLBACK` hoặc rollback tới savepoint thích hợp.

Kịch bản thử với savepoint:

```sql
BEGIN;

SAVEPOINT before_bad_insert;

-- Chạy câu INSERT vi phạm CHECK OPTION ở đây;
-- PostgreSQL sẽ trả lỗi.

ROLLBACK TO SAVEPOINT before_bad_insert;

-- Sau đó mới tiếp tục những câu hợp lệ trong transaction.
ROLLBACK;
```

Cần hiểu đây là **khung thao tác cho SQL client**; nếu công cụ được cấu hình dừng script ngay khi gặp lỗi, các câu tiếp theo có thể không tự chạy. Để dễ thử từng lỗi, nên thực thi từng ví dụ vi phạm **riêng lẻ** trên bảng tạm.

## 8. LOCAL và CASCADED: vấn đề chỉ xuất hiện rõ ở view lồng nhau

Một view có thể chọn dữ liệu từ **một view khác**.

Ví dụ:

```text
demo_view_orders (bảng gốc)
        |
        v
v_tenant10        -- WHERE tenant_id = 10
        |
        v
v_tenant10_drafts -- WHERE status = 'DRAFT'
```

Ta muốn hiểu: nếu viết CHECK OPTION **ở view bên trên**, nó kiểm tra:

- Chỉ điều kiện riêng của **view hiện tại**?
- Hay cả điều kiện của **những view bên dưới**?

Hai chế độ thường gặp trong PostgreSQL/MySQL:

- **`LOCAL CHECK OPTION`:** kiểm tra điều kiện của view hiện tại; các CHECK OPTION đã được khai báo riêng ở view bên dưới **vẫn có hiệu lực**, nhưng một view dưới không có check option có thể không được kiểm tra chỉ do local ở tầng trên.
- **`CASCADED CHECK OPTION`:** kiểm tra điều kiện của view hiện tại và lan xuống các tầng view bên dưới trong phạm vi các view có thể cập nhật và theo quy tắc engine.

Nếu không ghi chế độ trong PostgreSQL, **`CASCADED` là mặc định**.

Cú pháp:

```sql
CREATE VIEW v_name AS
SELECT ...
FROM ...
WHERE ...
WITH LOCAL CHECK OPTION;
```

hoặc:

```sql
CREATE VIEW v_name AS
SELECT ...
FROM ...
WHERE ...
WITH CASCADED CHECK OPTION;
```

**Không nên đặt `LOCAL` và `CASCADED` thành hai cách viết đồng nghĩa.** Chúng xác định độ sâu của các điều kiện hiển thị được thực thi khi ghi qua view lồng nhau.

## 9. Thực hành PostgreSQL: LOCAL kiểm tra tầng hiện tại

Tạo view nền chỉ nhìn tenant 10 **nhưng không có CHECK OPTION**:

```sql
CREATE TEMP VIEW v_tenant10 AS
SELECT
    order_id, tenant_id, customer_id,
    status, total_amount, created_on
FROM demo_view_orders
WHERE tenant_id = 10;
```

Tạo view trên nó, chỉ nhìn DRAFT và có **LOCAL CHECK OPTION**:

```sql
CREATE TEMP VIEW v_t10_drafts_local AS
SELECT
    order_id, tenant_id, customer_id,
    status, total_amount, created_on
FROM v_tenant10
WHERE status = 'DRAFT'
WITH LOCAL CHECK OPTION;
```

Tập kết quả ban đầu:

```sql
SELECT order_id, tenant_id, status
FROM v_t10_drafts_local
ORDER BY order_id;
-- 101 | 10 | DRAFT
-- 105 | 10 | DRAFT
```

### 9.1. Đổi tenant qua LOCAL có thể được cho phép

```sql
BEGIN;

UPDATE v_t10_drafts_local
SET tenant_id = 20
WHERE order_id = 105
RETURNING order_id, tenant_id, status;
-- 105 | 20 | DRAFT

SELECT order_id, tenant_id, status
FROM v_t10_drafts_local
ORDER BY order_id;
-- Chỉ còn 101.

SELECT order_id, tenant_id, status
FROM demo_view_orders
WHERE order_id = 105;
-- 105 | 20 | DRAFT

ROLLBACK;
```

Tại sao cập nhật có thể thành công?

- View **hiện tại** `v_t10_drafts_local` có predicate trực tiếp `status = 'DRAFT'`.
- Câu UPDATE chỉ đổi `tenant_id` sang 20 và giữ `status = 'DRAFT'`.
- Vì vậy **điều kiện LOCAL của view hiện tại vẫn đúng**.
- View nền `v_tenant10` có predicate `tenant_id = 10`, nhưng **chưa khai báo CHECK OPTION**.
- Chế độ `LOCAL` của view trên **không tự buộc** phải kiểm tra mọi điều kiện từ những view nền chưa có check option.

Sau update, hàng không còn xuất hiện qua view nền tenant 10 nên cũng không còn thấy ở view con. Đây chính là điểm khác biệt giữa LOCAL và CASCADED.

### 9.2. LOCAL vẫn chặn đổi status

```sql
-- Thử RIÊNG: vi phạm predicate trực tiếp của view LOCAL.
UPDATE v_t10_drafts_local
SET status = 'PAID'
WHERE order_id = 105;
```

Vì điều kiện trực tiếp `status = 'DRAFT'` không còn đúng, LOCAL CHECK OPTION từ chối cập nhật.

**Kết luận phần này:** LOCAL có thể ngăn hàng rời tập **theo điều kiện trực tiếp của view đang ghi**, nhưng **không tự bảo đảm toàn bộ chuỗi view nguồn còn hiển thị hàng đó**.

## 10. Thực hành PostgreSQL: CASCADED kiểm tra cả view nền

Tạo một view khác trên cùng view nền, nhưng có **CASCADED CHECK OPTION**:

```sql
CREATE TEMP VIEW v_t10_drafts_cascaded AS
SELECT
    order_id, tenant_id, customer_id,
    status, total_amount, created_on
FROM v_tenant10
WHERE status = 'DRAFT'
WITH CASCADED CHECK OPTION;
```

Thử hai tình huống.

### 10.1. Đổi status làm sai điều kiện view hiện tại

```sql
-- Thử RIÊNG: bị từ chối.
UPDATE v_t10_drafts_cascaded
SET status = 'PAID'
WHERE order_id = 101;
```

Lý do: `status = 'DRAFT'` của view tầng trên không còn đúng.

### 10.2. Đổi tenant làm sai điều kiện view nền

```sql
-- Thử RIÊNG: bị từ chối với CASCADED CHECK OPTION.
UPDATE v_t10_drafts_cascaded
SET tenant_id = 20
WHERE order_id = 105;
```

Vì `v_tenant10` chỉ chứa `tenant_id = 10`, CASCADED yêu cầu hàng mới cũng vượt qua điều kiện này, dù view nền không tự có CHECK OPTION.

### 10.3. Bảng so sánh trên cùng dữ liệu

Giả sử hàng 105 đang có `tenant_id = 10`, `status = 'DRAFT'`:

| Thao tác qua view bên trên | `WITH LOCAL CHECK OPTION` | `WITH CASCADED CHECK OPTION` |
|---|---|---|
| `SET total_amount = 500` | Cho phép, nếu ràng buộc khác hợp lệ | Cho phép |
| `SET status = 'PAID'` | Từ chối | Từ chối |
| `SET tenant_id = 20` | Có thể cho phép nếu view nền không có CHECK OPTION | Từ chối |
| INSERT với tenant 10 và DRAFT | Cho phép | Cho phép |
| INSERT với tenant 20 và DRAFT | Có thể cho phép qua tầng LOCAL theo điều kiện của view hiện tại | Từ chối |
| INSERT với tenant 10 và PAID | Từ chối | Từ chối |

Những kết quả nêu ở đây áp dụng cho **chuỗi automatically updatable views trên PostgreSQL** đã tạo, không có trigger/rule đặc biệt. Với view do trigger/rule điều khiển hoặc phương ngữ khác, cần xem cơ chế riêng.

## 11. Nếu view nền đã có CHECK OPTION thì LOCAL không vượt qua được

Một điểm dễ hiểu sai:

> LOCAL chỉ kiểm tra tầng hiện tại, vậy có thể dùng view LOCAL bên trên để vượt qua CHECK OPTION của view nền?

**Không.** Nếu view nền đã khai báo CHECK OPTION riêng, việc ghi qua các tầng phía trên vẫn phải tôn trọng kiểm tra đã được áp dụng ở view nền theo quy tắc tương ứng.

Tạo view nền có bảo vệ:

```sql
CREATE TEMP VIEW v_tenant10_checked AS
SELECT
    order_id, tenant_id, customer_id,
    status, total_amount, created_on
FROM demo_view_orders
WHERE tenant_id = 10
WITH CHECK OPTION;
```

Tạo view tầng trên có LOCAL:

```sql
CREATE TEMP VIEW v_t10_drafts_local_on_checked AS
SELECT
    order_id, tenant_id, customer_id,
    status, total_amount, created_on
FROM v_tenant10_checked
WHERE status = 'DRAFT'
WITH LOCAL CHECK OPTION;
```

Thử:

```sql
-- Thử RIÊNG: bị từ chối do CHECK OPTION ở view nền.
UPDATE v_t10_drafts_local_on_checked
SET tenant_id = 20
WHERE order_id = 105;
```

`status` vẫn là `DRAFT`, nên điều kiện LOCAL tầng trên đúng. Nhưng view nền đã có CHECK OPTION `tenant_id = 10`, vì vậy vẫn chặn thay đổi tenant.

| Tầng | Predicate | CHECK OPTION | Tác động khi ghi qua view trên |
|---|---|---|---|
| View nền | `tenant_id = 10` | Có | Phải được thỏa |
| View trên | `status = 'DRAFT'` | LOCAL | Phải được thỏa |
| Hàng mới tenant 20, DRAFT | Thỏa tầng trên, không thỏa tầng nền | — | Bị từ chối |

Như vậy, câu chính xác là: **LOCAL không tự mở rộng kiểm tra tới mọi predicate bên dưới, nhưng không xóa bỏ các kiểm tra đã có ở những view bên dưới**.

## 12. View có nhiều tầng hơn và chế độ mặc định

Giả sử:

```text
base_orders
    |
    v
v_tenant10          WHERE tenant_id = 10
    |
    v
v_tenant10_drafts   WHERE status = 'DRAFT'
    |
    v
v_large_drafts      WHERE total_amount >= 1000
```

Nếu `v_large_drafts` dùng `LOCAL CHECK OPTION`, tự nó chỉ kiểm tra `total_amount >= 1000`; những điều kiện khác được áp dụng theo các CHECK OPTION có ở những tầng dưới, nếu có.

Nếu dùng `CASCADED CHECK OPTION` trên một chuỗi **automatically updatable** và không bị ngăn bởi cơ chế đặc thù, hàng sau ghi phải thỏa cả:

```sql
tenant_id = 10
AND status = 'DRAFT'
AND total_amount >= 1000
```

### 12.1. Ví dụ ba tầng

```sql
CREATE TEMP VIEW v_large_t10_drafts AS
SELECT
    order_id, tenant_id, customer_id,
    status, total_amount, created_on
FROM v_t10_drafts_local
WHERE total_amount >= 1000
WITH CASCADED CHECK OPTION;
```

Giả sử chèn hàng mới qua `v_large_t10_drafts`:

```sql
-- Thử riêng, hợp lệ nếu các ràng buộc khác thỏa.
INSERT INTO v_large_t10_drafts
    (order_id, tenant_id, customer_id,
     status, total_amount, created_on)
VALUES
    (301, 10, 3001, 'DRAFT', 1200, DATE '2026-11-20');
```

Một hàng có `total_amount = 500` không thỏa điều kiện view trên, nên bị từ chối. Một hàng có `tenant_id = 20` không thỏa view nền và bị từ chối theo phạm vi CASCADED.

### 12.2. LOCAL không có nghĩa chỉ kiểm tra tên cột được SELECT

CHECK OPTION kiểm tra **predicate của định nghĩa view**, kể cả predicate sử dụng cột không có trong danh sách SELECT của view trực tiếp, miễn engine có thể đánh giá điều kiện. Cụm “LOCAL” chỉ nói về **tầng định nghĩa view**, không nói về “chỉ các cột được hiển thị”.

### 12.3. Giới hạn khi có trigger/rule thay thế

Ở PostgreSQL, `WITH CHECK OPTION` được hỗ trợ rõ cho **automatically updatable views**. Các view được cập nhật thông qua **`INSTEAD OF` triggers hoặc rewrite rules** có thể thay đổi cách áp dụng điều kiện: một phần tùy chọn LOCAL có thể kiểm tra được ở tầng tự động, còn CASCADED không nhất thiết đi xuyên được qua tầng trigger-updatable; các `INSTEAD` rules có thể làm một số kiểm tra view bị bỏ qua theo quy tắc PostgreSQL.

Không diễn giải từ khóa CASCADED là “bất kể có bao nhiêu trigger/rule cũng kiểm tra được toàn bộ bảng gốc”. Nếu view phụ thuộc trigger/rule, cần thiết kế kiểm tra ở chính cơ chế ghi đó hoặc ràng buộc bảng và thử trên phiên bản đang dùng.

## 13. NULL và logic ba giá trị trong CHECK OPTION

SQL không chỉ có `TRUE` và `FALSE`; một điều kiện có giá trị `NULL` có thể cho kết quả **`UNKNOWN`**.

Ví dụ:

```sql
WHERE approved = TRUE
```

Nếu `approved` là `NULL`, biểu thức `approved = TRUE` trả `UNKNOWN`, không phải `TRUE`.

Với CHECK OPTION, **hàng được ghi phải thực sự thỏa điều kiện view**; `FALSE` hoặc `UNKNOWN` đều không được xem là thỏa.

### 13.1. Dữ liệu mẫu có cột nullable

```sql
CREATE TEMP TABLE demo_reviews (
    review_id INTEGER PRIMARY KEY,
    approved BOOLEAN
);

CREATE TEMP VIEW v_approved_reviews AS
SELECT review_id, approved
FROM demo_reviews
WHERE approved = TRUE
WITH CHECK OPTION;
```

Chèn hợp lệ:

```sql
INSERT INTO v_approved_reviews (review_id, approved)
VALUES (1, TRUE);
```

Hai thao tác bị chặn:

```sql
-- Thử RIÊNG: approved = FALSE không thỏa view.
INSERT INTO v_approved_reviews (review_id, approved)
VALUES (2, FALSE);
```

```sql
-- Thử RIÊNG: approved = NULL làm predicate UNKNOWN.
INSERT INTO v_approved_reviews (review_id, approved)
VALUES (3, NULL);
```

Dù bảng gốc cho phép `approved NULL`, view `v_approved_reviews` chỉ chấp nhận những hàng mà `approved = TRUE` đánh giá đúng.

### 13.2. Nếu muốn coi NULL như chưa duyệt

Trong nghiệp vụ, `NULL` có thể nghĩa là “chưa duyệt”. Với view chỉ chứa bản ghi đã duyệt, CHECK OPTION cần tiếp tục chặn `NULL`.

Với view hiển thị bản ghi **chưa được duyệt hoặc chưa rõ trạng thái**, có thể định nghĩa:

```sql
CREATE TEMP VIEW v_not_approved_reviews AS
SELECT review_id, approved
FROM demo_reviews
WHERE approved = FALSE OR approved IS NULL
WITH CHECK OPTION;
```

Khi đó, chèn `approved FALSE` hoặc `NULL` phù hợp điều kiện; `TRUE` không phù hợp.

**Không tự dùng `COALESCE(approved, FALSE)` trong mọi nơi** nếu cần phân biệt “đã xác nhận từ chối” và “chưa có kết quả”. Quy tắc xử lý `NULL` phải đúng với ý nghĩa nghiệp vụ.

### 13.3. CHECK OPTION khác CHECK constraint ở chỗ nào?

Bảng gốc có thể có:

```sql
CHECK (total_amount >= 0)
```

Trong PostgreSQL, một `CHECK` constraint của bảng thông thường coi **TRUE hoặc UNKNOWN** là không vi phạm; muốn cấm `NULL` phải có `NOT NULL` thích hợp. Ngược lại, để một hàng hiển thị qua view `WHERE total_amount >= 0`, biểu thức đó phải **TRUE**; `UNKNOWN` không hiển thị và CHECK OPTION không chấp nhận khi ghi qua view.

Đây là điểm tinh tế:

| Điều kiện | Giá trị TRUE | FALSE | UNKNOWN do NULL |
|---|---|---|---|
| `WHERE` của view: hàng có được hiển thị? | Có | Không | Không |
| `WITH CHECK OPTION` trên predicate đó: hàng ghi có hợp lệ qua view? | Có, nếu các ràng buộc khác cũng thỏa | Không | Không |
| `CHECK (predicate)` tại bảng PostgreSQL thông thường | Chấp nhận | Từ chối | Thường chấp nhận; dùng `NOT NULL` nếu cần cấm NULL |

Không xem CHECK OPTION là bản sao đơn thuần của một `CHECK` constraint: **phạm vi thao tác và cách xử lý UNKNOWN khác nhau**.

## 14. INSERT, UPDATE và DELETE qua view có CHECK OPTION

### 14.1. INSERT

Nếu INSERT qua view tạo ra một hàng không thỏa predicate thuộc phạm vi CHECK OPTION, câu lệnh bị từ chối. Không chỉ định các cột trong INSERT không làm cho DBMS tự thêm điều kiện WHERE dưới dạng giá trị mặc định.

### 14.2. UPDATE

Một hàng đã nằm trong view có thể được UPDATE, nhưng hàng **sau cập nhật** phải tiếp tục thỏa các predicate được kiểm tra. Do đó:

```sql
-- Hợp lệ nếu hàng 101 vẫn là DRAFT của tenant 10:
UPDATE v_t10_drafts_checked
SET total_amount = 200
WHERE order_id = 101;
```

```sql
-- Bị chặn vì hàng 101 sẽ rời khỏi tập DRAFT:
UPDATE v_t10_drafts_checked
SET status = 'PAID'
WHERE order_id = 101;
```

CHECK OPTION không có chức năng “chuyển PAID về DRAFT cho hợp lệ”; nó chặn thao tác vi phạm.

### 14.3. DELETE

`DELETE` **không tạo một trạng thái hàng mới cần hiển thị trong view**, vì hàng bị xóa. Do đó CHECK OPTION không được dùng để bắt mọi hàng bị xóa phải “tiếp tục nhìn thấy” sau DELETE.

```sql
BEGIN;

DELETE FROM v_t10_drafts_checked
WHERE order_id = 101
RETURNING order_id;
-- Có thể xóa hàng 101 nếu quyền, FK, trigger phù hợp.

ROLLBACK;
```

Hành vi:

- Chỉ những hàng đang nằm trong view (ví dụ 101, 105) có thể được chọn bởi DELETE qua view đơn giản.
- CHECK OPTION không tự cấm DELETE của một hàng DRAFT đang nhìn thấy.
- `DELETE` vẫn chịu quyền, FK, trigger, Row-Level Security và quy tắc updatable view của DBMS.

**Nếu yêu cầu là “không cho xóa bản nháp”, CHECK OPTION không giải quyết được.** Cần phân quyền, trigger/rule thích hợp, RLS hoặc chính sách API.

### 14.4. Hàng không hiển thị không được “kéo vào” bằng UPDATE

Giả sử đơn 102 đang là `PAID`. Câu sau:

```sql
UPDATE v_t10_drafts_checked
SET status = 'DRAFT'
WHERE order_id = 102;
```

thường tác động **0 hàng**, vì đơn 102 không nằm trong tập hàng ban đầu của view DRAFT. CHECK OPTION kiểm tra hàng được ghi qua view, không cho phép UPDATE tùy ý một hàng đã bị bộ lọc view ẩn đi chỉ vì giá trị cập nhật sẽ đưa nó vào view.

Muốn chuyển đơn PAID thành DRAFT phải thao tác qua một đường ghi có thẩm quyền nhìn thấy nó, sau đó vẫn áp các ràng buộc nghiệp vụ tương ứng.

## 15. Giới hạn của CHECK OPTION: nó không phải hệ thống phân quyền

Một nguy cơ lớn là xem view có điều kiện như **hàng rào bảo mật duy nhất**.

Ví dụ:

```sql
CREATE VIEW v_tenant10_orders AS
SELECT *
FROM orders
WHERE tenant_id = 10
WITH CHECK OPTION;
```

Nếu người dùng còn có quyền:

```sql
UPDATE orders
SET tenant_id = 20
WHERE order_id = 101;
```

trực tiếp trên bảng `orders`, họ có thể **bỏ qua đường ghi qua view**. CHECK OPTION chỉ ràng buộc những thao tác **được thực hiện qua view và theo cơ chế view tương ứng**, không tự áp toàn bộ bảng nguồn cho mọi role.

### 15.1. CHECK OPTION không tự giới hạn SELECT

CHECK OPTION nhằm ràng buộc **giá trị sau ghi**. Khả năng đọc hàng nào do **định nghĩa SELECT của view** và các quyền/RLS/đặc tính view quy định.

Nói cách khác:

- `WHERE tenant_id = 10` của view giới hạn tập hàng view trả về.
- `WITH CHECK OPTION` bổ sung kiểm tra với thao tác ghi qua view.
- `GRANT/REVOKE`, quyền trên bảng nguồn, chính sách RLS và cấu hình security mode quy định ai có thể đi qua những đường đọc/ghi nào.

View có CHECK OPTION không tự kiểm soát SQL injection, quyền gọi API, danh tính tenant hay quyền truy cập bảng nguồn.

### 15.2. PostgreSQL view security definer/invoker và RLS

Theo cách vận hành phổ biến, view PostgreSQL có các quy tắc về quyền của **chủ view** so với **người gọi** đối với bảng nguồn. PostgreSQL 15+ có tùy chọn `security_invoker` cho view ở những trường hợp thích hợp; RLS và quyền bảng nền còn có quy tắc tương tác riêng.

CHECK OPTION **không quyết định những chính sách đó**. Khi dùng view cho multi-tenant:

1. Quy định chính xác role được phép `SELECT/INSERT/UPDATE/DELETE` qua view.
2. Hạn chế đường ghi trực tiếp vào bảng nguồn nếu cần.
3. Xác định tenant từ ngữ cảnh đã được xác thực phía server, không tin vào tenant ID do client tự chọn.
4. Cân nhắc **RLS** ở bảng gốc cho cơ chế bảo vệ hàng trên nhiều đường truy cập.
5. Kiểm tra SECURITY DEFINER/INVOKER, quyền chủ view, search_path và các hàm/trigger được gọi.

**CHECK OPTION hỗ trợ tính nhất quán của tập view; nó không thay thế thiết kế bảo mật đa lớp.**

### 15.3. Giới hạn tenant bằng view không tự sửa ID từ client

Với view tenant 10:

```sql
WHERE tenant_id = 10
WITH CHECK OPTION
```

một INSERT có `tenant_id = 20` sẽ bị chặn, nhưng điều này chỉ bảo vệ **khi câu INSERT thực sự đi qua view**. Trong hệ đa tenant thật, nên thiết kế API/role để không ai có thể tự thay tenant id và chèn qua một đường khác không ràng buộc.

Ngoài ra, `WHERE tenant_id = 10` là hard-code chỉ thích hợp minh họa hoặc phân vùng quyền cố định. Một dịch vụ có hàng nghìn tenant có thể chọn RLS và cấu hình tenant từ session/role có kiểm soát thay vì tạo hàng nghìn view thủ công.

## 16. CHECK OPTION và các ràng buộc của bảng gốc

CHECK OPTION chỉ giải quyết **một loại giới hạn**: hàng được chèn/cập nhật qua view phải nằm trong tập kết quả mà view được thiết kế đại diện.

Những ràng buộc khác không mất hiệu lực:

| Cơ chế | Điều bảo vệ chính | CHECK OPTION có thay thế được? |
|---|---|---|
| `PRIMARY KEY` | Khóa định danh duy nhất, không NULL | Không |
| `UNIQUE` | Tính duy nhất theo cột/biểu thức được ràng buộc | Không |
| `NOT NULL` | Bắt buộc có giá trị | Không |
| `CHECK` ở bảng | Quy tắc miền giá trị của cột/hàng | Không |
| `FOREIGN KEY` | Tính hợp lệ của quan hệ tham chiếu | Không |
| `WITH CHECK OPTION` | Giá trị sau INSERT/UPDATE thỏa điều kiện view | Đúng phạm vi của nó |
| `GRANT/REVOKE` | Quyền được gọi thao tác | Không |
| RLS | Quyền truy cập/ghi theo chính sách hàng | Không |
| Trigger | Logic tùy biến, audit, kiểm tra nghiệp vụ | Không |
| Transaction/khóa | Tính nguyên tử, cô lập và đồng thời | Không |

### 16.1. Hàng thỏa view vẫn có thể vi phạm CHECK

```sql
-- Status và tenant đều thỏa CHECK OPTION của view,
-- nhưng số tiền âm vi phạm CHECK ở bảng gốc.
INSERT INTO v_t10_drafts_checked
    (order_id, tenant_id, customer_id,
     status, total_amount, created_on)
VALUES
    (220, 10, 2220, 'DRAFT', -50, DATE '2026-11-20');
```

PostgreSQL vẫn báo lỗi vì `total_amount >= 0` là ràng buộc của bảng gốc.

### 16.2. Hàng thỏa view vẫn có thể trùng PK

```sql
-- order_id=101 đã tồn tại trong bảng gốc.
INSERT INTO v_t10_drafts_checked
    (order_id, tenant_id, customer_id,
     status, total_amount, created_on)
VALUES
    (101, 10, 2221, 'DRAFT', 100, DATE '2026-11-20');
```

Predicate view hợp lệ nhưng `PRIMARY KEY(order_id)` bị vi phạm. CHECK OPTION không có cơ chế tự tạo khóa mới hoặc bỏ qua unique violation.

### 16.3. View thiếu cột bắt buộc không tự chèn được

Nếu bảng gốc yêu cầu `tenant_id NOT NULL` nhưng view không xuất cột tenant và không có default/triggers để cung cấp nó, lệnh INSERT qua view có thể thất bại. CHECK OPTION không điền `tenant_id = 10` chỉ vì view dùng điều kiện đó.

Ví dụ:

```sql
CREATE TEMP VIEW v_tenant10_slim AS
SELECT order_id, customer_id, total_amount, created_on
FROM demo_view_orders
WHERE tenant_id = 10
WITH CHECK OPTION;
```

`v_tenant10_slim` có thể cho đọc và có thể cập nhật các cột ghi được, nhưng khi chèn hàng mới mà không cung cấp `tenant_id`/`status` bắt buộc, PostgreSQL còn phải áp default và `NOT NULL` của bảng nguồn. Với schema mẫu, những cột bị thiếu khiến câu INSERT không hợp lệ.

## 17. View có JOIN, GROUP BY hay biểu thức: CHECK OPTION không tự sửa khả năng ghi

Một view nhóm theo tenant:

```sql
CREATE TEMP VIEW v_tenant_revenue AS
SELECT tenant_id, SUM(total_amount) AS total_revenue
FROM demo_view_orders
WHERE status = 'PAID'
GROUP BY tenant_id;
```

Không thể mặc nhiên:

```sql
INSERT INTO v_tenant_revenue (tenant_id, total_revenue)
VALUES (10, 5000);
```

và mong PostgreSQL biết phải tạo bao nhiêu đơn hàng, thuộc khách nào, có trạng thái gì. View tổng hợp không thuộc nhóm automatically updatable thông thường. Thêm CHECK OPTION không làm xuất hiện quy tắc phân bổ dữ liệu.

### 17.1. JOIN có thể khó xác định bảng nào ghi

```sql
CREATE TEMP VIEW v_order_details AS
SELECT o.order_id, o.customer_id, o.total_amount
FROM demo_view_orders AS o
JOIN some_customers AS c
  ON c.customer_id = o.customer_id;
```

Ví dụ này giả định `some_customers` tồn tại, nhằm minh họa cấu trúc JOIN; **không chạy trên bộ dữ liệu mẫu nếu chưa tạo bảng**.

Với nhiều bảng, chỉ một thao tác UPDATE có thể mơ hồ về việc nên thay đổi hàng ở bảng nào hoặc tác động ra sao tới tính duy nhất/các hàng JOIN. Từng DBMS có quy tắc về view có thể cập nhật qua JOIN. PostgreSQL không tự động updatable đối với mọi view JOIN như một view chọn từ đúng một bảng.

Nếu cần DML qua view phức tạp, có thể sử dụng `INSTEAD OF` triggers theo khả năng DBMS. Nhưng lúc đó phải kiểm tra **ngữ nghĩa CHECK OPTION** và tự bảo vệ dữ liệu ở tầng ghi; không giả định CHECK OPTION mặc nhiên có đầy đủ hiệu lực như với view đơn giản.

### 17.2. Cột tính toán có thể chỉ đọc

```sql
CREATE TEMP VIEW v_order_with_tax AS
SELECT
    order_id,
    total_amount,
    total_amount * 1.08 AS display_amount
FROM demo_view_orders;
```

Cột `display_amount` là biểu thức, không có một cột bảng gốc đồng tên để UPDATE trực tiếp. Có thể cập nhật `total_amount` qua view tự động phù hợp, nhưng không đơn giản sửa `display_amount` rồi mong PostgreSQL tự đảo công thức và ghi lại `total_amount`.

CHECK OPTION cũng không tự biến cột tính toán thành cột ghi được.

## 18. PostgreSQL: ví dụ kiểm tra DELETE và UPDATE bằng transaction

Một quy trình thử có kiểm soát:

```sql
BEGIN;

-- Thử UPDATE không làm rời view.
UPDATE v_t10_drafts_checked
SET total_amount = total_amount + 25
WHERE order_id = 101
RETURNING order_id, total_amount;

-- Thử DELETE trên hàng đang thấy.
DELETE FROM v_t10_drafts_checked
WHERE order_id = 105
RETURNING order_id;

-- Kiểm tra bảng gốc trong chính transaction.
SELECT order_id, tenant_id, status, total_amount
FROM demo_view_orders
WHERE order_id IN (101, 105)
ORDER BY order_id;

-- Khôi phục dữ liệu thực hành.
ROLLBACK;
```

Kết quả về mặt ngữ nghĩa:

- UPDATE 101 có thể thành công nếu tổng tiền mới vẫn không âm và hàng vẫn là DRAFT tenant 10.
- DELETE 105 có thể xóa hàng 105 qua view, tùy quyền và FK/trigger.
- Sau `ROLLBACK`, bảng gốc quay lại trạng thái trước transaction.

**Lưu ý khác biệt:** transaction `ROLLBACK` phục hồi DML ở PostgreSQL khi chưa commit, không phải cơ chế để CHECK OPTION “quay lại” hàng không thỏa điều kiện. CHECK OPTION **ngăn thao tác bất hợp lệ ngay khi ghi**, còn transaction kiểm soát việc commit/rollback các thao tác hợp lệ hoặc lỗi.

## 19. MySQL: WITH LOCAL/CASCADED CHECK OPTION

MySQL hỗ trợ khai báo:

```sql
-- MySQL: giả sử bảng orders có cột tương ứng.
CREATE VIEW v_tenant10_orders AS
SELECT order_id, tenant_id, customer_id, status, total_amount
FROM orders
WHERE tenant_id = 10
WITH CASCADED CHECK OPTION;
```

và:

```sql
CREATE VIEW v_tenant10_drafts AS
SELECT order_id, tenant_id, customer_id, status, total_amount
FROM v_tenant10_orders
WHERE status = 'DRAFT'
WITH LOCAL CHECK OPTION;
```

Ý tưởng LOCAL/CASCADED tương tự quy tắc đã học:

- LOCAL tập trung vào điều kiện của view hiện tại, đồng thời **không bỏ các check option đã tồn tại** ở view nền.
- CASCADED kiểm tra điều kiện view hiện tại và những view nguồn liên quan theo cơ chế MySQL.
- Mặc định của MySQL khi ghi `WITH CHECK OPTION` mà không nêu mức là `CASCADED`.

### 19.1. Không phải view nào của MySQL cũng updatable

MySQL có quy tắc riêng về **updatability**; những view sử dụng `ALGORITHM = TEMPTABLE` không updatable như những view có thể merge và ánh xạ trực tiếp về bảng nguồn.

Ví dụ:

```sql
-- MySQL: TEMPTABLE view thường không cho DML qua view.
CREATE ALGORITHM = TEMPTABLE VIEW v_paid_totals AS
SELECT tenant_id, SUM(total_amount) AS total_amount
FROM orders
WHERE status = 'PAID'
GROUP BY tenant_id;
```

Lý do view không updatable không chỉ là CHECK OPTION: phép nhóm và chế độ materialization qua TEMPTABLE làm mất ánh xạ ghi trực tiếp. Không kỳ vọng thêm `WITH CHECK OPTION` sẽ biến nó thành view có thể INSERT/UPDATE.

### 19.2. SQL SECURITY và CHECK OPTION phục vụ hai mục tiêu

MySQL cho phép cấu hình SQL SECURITY DEFINER/INVOKER cho view. Chế độ đó kiểm soát bối cảnh kiểm tra quyền, trong khi CHECK OPTION kiểm tra **hàng sau ghi có thỏa điều kiện view** hay không.

Không xem `SQL SECURITY DEFINER` là đồng nghĩa với `WITH CHECK OPTION`, và cũng không dùng CHECK OPTION thay cho quyền DB.

### 19.3. MySQL/MariaDB khác nhau theo phiên bản

MariaDB có cú pháp view và `WITH [CASCADED | LOCAL] CHECK OPTION` tương tự ở nhiều phiên bản, nhưng MySQL và MariaDB không phải cùng một sản phẩm. Khi triển khai, kiểm tra đúng phiên bản về view updatability, thuật toán view, quyền, trigger và cách báo lỗi.

## 20. SQL Server: WITH CHECK OPTION nhưng không dùng LOCAL/CASCADED kiểu PostgreSQL

SQL Server (T-SQL) cũng hỗ trợ `WITH CHECK OPTION` trong `CREATE VIEW`:

```sql
-- SQL Server Database Engine. Giả sử dbo.orders tồn tại.
CREATE VIEW dbo.v_draft_orders
AS
SELECT
    order_id, tenant_id, customer_id, status, total_amount
FROM dbo.orders
WHERE tenant_id = 10
  AND status = 'DRAFT'
WITH CHECK OPTION;
```

Nếu view có thể cập nhật, SQL Server dùng CHECK OPTION để ngăn các thay đổi qua view khiến hàng không còn thỏa điều kiện hiển thị theo quy tắc của view. Ví dụ cập nhật `status` của đơn đang là DRAFT sang PAID sẽ bị từ chối khi thao tác qua view có CHECK OPTION.

### 20.1. Đừng sao chép LOCAL/CASCADED vào T-SQL

Không coi cú pháp:

```sql
-- Không phải cú pháp T-SQL được dùng như PostgreSQL/MySQL:
WITH LOCAL CHECK OPTION
```

là tùy chọn tiêu chuẩn của SQL Server. SQL Server có `WITH CHECK OPTION`, nhưng không có cùng cặp từ khóa `LOCAL`/`CASCADED` trong định nghĩa view như PostgreSQL/MySQL.

### 20.2. SQL Server cũng có giới hạn updatable view

SQL Server có thể cho cập nhật một số view kết nối bảng nếu quy tắc về cột và nguồn ghi được đáp ứng, hoặc dùng `INSTEAD OF` trigger cho hành vi đặc biệt. Nhưng view có aggregate, DISTINCT, GROUP BY hoặc biểu thức không updatable không tự ghi được chỉ nhờ CHECK OPTION.

### 20.3. CREATE VIEW là một lệnh DDL riêng trong batch

Trong SQL Server, `CREATE VIEW` thường phải là **câu lệnh đầu của một batch**. Trong SQL Server Management Studio, người viết thường đặt `GO` trước/sau câu tạo view khi có những câu DDL khác cùng script.

`GO` là dấu phân tách batch của công cụ SQL Server, **không phải cú pháp SQL được gửi trực tiếp qua mọi API JDBC**. Ví dụ ở trên là một câu CREATE VIEW độc lập; khi chạy qua JDBC, không tự thêm `GO` vào chuỗi SQL nếu driver không hỗ trợ cú pháp công cụ.

## 21. Oracle Database: WITH CHECK OPTION, với cú pháp constraint riêng

Oracle Database cho phép view có `WITH CHECK OPTION`. Ví dụ:

```sql
-- Oracle Database: giả sử ORDERS có cột tương ứng.
CREATE VIEW v_draft_orders AS
SELECT
    order_id, tenant_id, customer_id, status, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'DRAFT'
WITH CHECK OPTION;
```

Oracle còn cho đặt **tên constraint của CHECK OPTION** theo cú pháp phù hợp:

```sql
CREATE VIEW v_draft_orders_named AS
SELECT
    order_id, tenant_id, customer_id, status, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'DRAFT'
WITH CHECK OPTION CONSTRAINT ck_v_draft_orders;
```

Tên constraint giúp nhận diện điều kiện view trong schema/thông báo lỗi theo cơ chế Oracle. Đây **không phải** cùng cú pháp với PostgreSQL `ON CONFLICT ON CONSTRAINT` hoặc `CHECK` tại bảng.

### 21.1. READ ONLY khác CHECK OPTION

Oracle cũng hỗ trợ view dạng:

```sql
-- Oracle
CREATE VIEW v_read_only_orders AS
SELECT order_id, tenant_id, status
FROM orders
WHERE tenant_id = 10
WITH READ ONLY;
```

- `WITH CHECK OPTION`: cho DML hợp lệ qua view có thể cập nhật, nhưng chặn hàng rời tập view.
- `WITH READ ONLY`: **không cho DML qua view** theo ý định của tùy chọn này.

Hai chính sách khác nhau: “được ghi nhưng phải giữ thuộc tập” và “không được ghi”.

### 21.2. Không dùng cú pháp LOCAL/CASCADED từ PostgreSQL nguyên xi

Oracle có ngữ nghĩa về view lồng nhau, updatable join views, trigger và check option riêng, nhưng `WITH LOCAL CHECK OPTION`/`WITH CASCADED CHECK OPTION` không phải cặp từ khóa thông dụng được viết trong Oracle `CREATE VIEW` giống PostgreSQL/MySQL.

Với view có JOIN, Oracle còn có những quy tắc về **key-preserved tables** và cột updatable. Khi dùng `INSTEAD OF` trigger, phải đọc đúng tài liệu Oracle về view/check option và kiểm tra các ràng buộc trong đường ghi.

## 22. SQLite: view thường chỉ đọc, không có WITH CHECK OPTION nguyên bản

SQLite hỗ trợ `CREATE VIEW` nhưng **view thông thường là read-only** đối với `INSERT`, `UPDATE` và `DELETE`. SQLite không hỗ trợ mệnh đề `WITH CHECK OPTION` theo cùng cú pháp PostgreSQL/MySQL/SQL Server/Oracle.

```sql
-- SQLite: view đọc dữ liệu.
CREATE VIEW v_draft_orders AS
SELECT order_id, tenant_id, customer_id, status, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'DRAFT';
```

Muốn thực hiện DML qua view, SQLite có cơ chế **`INSTEAD OF` trigger** để định nghĩa thao tác thực sự trên bảng nguồn. Khi đó, chính trigger phải thực thi quy tắc hạn chế dữ liệu.

### 22.1. Minh họa INSERT qua view có kiểm tra trong trigger

Giả sử SQLite có bảng:

```sql
-- SQLite: chạy trong database thử.
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    total_amount NUMERIC NOT NULL
);
```

Tạo view:

```sql
CREATE VIEW v_draft_t10 AS
SELECT order_id, tenant_id, customer_id, status, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'DRAFT';
```

Tạo trigger kiểm tra rồi chèn bảng gốc:

```sql
-- SQLite
CREATE TRIGGER tr_v_draft_t10_insert
INSTEAD OF INSERT ON v_draft_t10
BEGIN
    SELECT CASE
        WHEN NEW.tenant_id IS NULL
          OR NEW.tenant_id <> 10
          OR NEW.status IS NULL
          OR NEW.status <> 'DRAFT'
        THEN RAISE(ABORT, 'Row is outside v_draft_t10')
    END;

    INSERT INTO orders (
        order_id, tenant_id, customer_id,
        status, total_amount
    )
    VALUES (
        NEW.order_id, NEW.tenant_id, NEW.customer_id,
        NEW.status, NEW.total_amount
    );
END;
```

Sau đó:

```sql
-- Được phép.
INSERT INTO v_draft_t10
    (order_id, tenant_id, customer_id, status, total_amount)
VALUES
    (1, 10, 100, 'DRAFT', 100);

-- Bị trigger từ chối.
INSERT INTO v_draft_t10
    (order_id, tenant_id, customer_id, status, total_amount)
VALUES
    (2, 20, 200, 'DRAFT', 200);
```

Đây là **cách lập trình tương đương một phần về mục tiêu kiểm tra dữ liệu**, không phải SQLite đã có native `WITH CHECK OPTION`. Ví dụ chỉ định nghĩa **INSTEAD OF INSERT**; muốn cho UPDATE/DELETE qua view còn phải tạo trigger riêng, xác định cột nào được thay đổi, xử lý lỗi và đảm bảo FK/quyền theo ứng dụng.

**Lưu ý:** SQLite `CHECK`, `NOT NULL`, FK enforcement và các trigger khác của bảng gốc vẫn cần được cấu hình phù hợp. Trigger view đơn giản không thay thế schema chính xác hoặc kiểm soát tenant ở ứng dụng.

## 23. So sánh nhanh cú pháp theo hệ quản trị

| Hệ quản trị | Hỗ trợ native `WITH CHECK OPTION` trong view? | `LOCAL` / `CASCADED` | Ghi chú |
|---|---|---|---|
| **PostgreSQL** | Có, với automatically updatable views phù hợp | Có; mặc định `CASCADED` | View lồng nhau, trigger/rule có ngoại lệ |
| **MySQL** | Có, với updatable views | Có; mặc định `CASCADED` | Quy tắc updatability và `ALGORITHM` riêng |
| **MariaDB** | Có, trong các phiên bản hỗ trợ updatable views | Có theo cú pháp tương ứng | Cần kiểm tra phiên bản |
| **SQL Server** | Có | Không theo cặp cú pháp PG/MySQL | Dùng `WITH CHECK OPTION` |
| **Oracle** | Có | Không theo cặp cú pháp PG/MySQL | Có `WITH CHECK OPTION CONSTRAINT name` và `WITH READ ONLY` |
| **SQLite** | Không có native CHECK OPTION | Không áp dụng | View read-only trừ khi có `INSTEAD OF` trigger |

Sự giống nhau của từ khóa `WITH CHECK OPTION` không có nghĩa khả năng **INSERT/UPDATE qua view JOIN**, cách áp dụng trigger, privilege hay các ngoại lệ đều giống nhau.

## 24. CHECK OPTION không kiểm soát được mọi cách thay đổi dữ liệu

Xét view đã kiểm tra:

```sql
CREATE TEMP VIEW v_t10_drafts_checked2 AS
SELECT order_id, tenant_id, customer_id, status, total_amount, created_on
FROM demo_view_orders
WHERE tenant_id = 10 AND status = 'DRAFT'
WITH CHECK OPTION;
```

Một ứng dụng có thể thực hiện:

```sql
-- Ghi trực tiếp bảng gốc, không đi qua view:
UPDATE demo_view_orders
SET status = 'PAID'
WHERE order_id = 101;
```

Nếu ứng dụng có quyền UPDATE bảng gốc và không có ràng buộc nghiệp vụ khác, câu này có thể chạy. Dữ liệu từ view nhìn thấy sau đó thay đổi, dù bản thân view có CHECK OPTION. Không có gì mâu thuẫn: CHECK OPTION bảo vệ **đường ghi qua view**, không phải mọi câu SQL tác động tới bảng gốc.

Điều này ảnh hưởng kiến trúc API:

- Nếu chỉ muốn người dùng chỉ thao tác bản nháp qua view, **không cấp** một đường UPDATE bảng gốc không kiểm soát.
- Nếu trạng thái `PAID` là chuyển trạng thái hợp lệ thông qua service riêng, service đó có thể dùng một đường ghi khác với quyền và validation riêng.
- Nếu muốn mọi hàng ở bảng gốc không thể có một số trạng thái/giá trị, định nghĩa **CHECK constraint/trigger/RLS** ở lớp thích hợp, không chỉ dựa vào view.
- Nếu dữ liệu được ghi bởi migration, batch job hoặc trigger, cần kiểm tra những đường đó có đi qua view hay không.

## 25. CHECK OPTION và câu lệnh ON CONFLICT / upsert

Trên PostgreSQL, `INSERT ... ON CONFLICT` là cơ chế xử lý vi phạm unique key để chèn hoặc cập nhật. Khi liên quan đến view có CHECK OPTION, cần phân biệt hai mục tiêu:

1. **Unique conflict:** hai hàng có cùng khóa, cần DO NOTHING/DO UPDATE theo arbiter.
2. **View check:** một hàng được ghi qua view có còn thuộc tập được phép hiển thị không?

Hai việc **không thay thế nhau**. CHECK OPTION không biến thành `ON CONFLICT`, và việc upsert xử lý khóa trùng không tự chứng minh hàng sau ghi thỏa predicate của view.

Đặc biệt, khả năng và cách hỗ trợ `ON CONFLICT` khi **đích INSERT là view** phụ thuộc PostgreSQL, cơ chế tự cập nhật/trigger và phiên bản; không mặc định mọi updatable view cho phép toàn bộ biến thể `ON CONFLICT DO UPDATE` như bảng gốc.

Một thiết kế thực tế thường là:

- Dùng **upsert trên bảng đích với unique constraint chuẩn** để bảo vệ tính duy nhất.
- Dùng **CHECK/NOT NULL/FK, RLS và transaction** để bảo vệ dữ liệu và quyền tại lớp bảng.
- Khi có nhu cầu API thông qua view, dùng **WITH CHECK OPTION** để ràng buộc tập hàng được ghi qua view và kiểm tra cách các cơ chế tương tác.

Không dùng upsert với `DO NOTHING` như cách âm thầm bỏ qua một hàng vi phạm predicate view; một hàng không thuộc view là vấn đề **phạm vi dữ liệu**, không đơn thuần là khóa trùng.

## 26. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách hiểu đúng |
|---|---|---|
| “WHERE của view đã chặn INSERT sai” | Có thể chèn hàng không nhìn thấy qua view | Dùng `WITH CHECK OPTION` khi view updatable và cần kiểm tra sau ghi |
| “CHECK OPTION cho phép sửa bản ghi bất kỳ thành hàng hợp lệ” | UPDATE 0 hàng vì bản ghi ban đầu bị ẩn | Chỉ hàng hiện nhìn thấy qua view mới là đối tượng UPDATE thông thường |
| “CHECK OPTION tự điền tenant_id/status từ WHERE” | INSERT thiếu cột bắt buộc và bị lỗi | Dùng DEFAULT, cột đầu vào rõ ràng hoặc cơ chế viết đúng |
| “CHECK OPTION là ràng buộc duy nhất của bảng” | Vẫn có duplicate/giá âm/FK sai | Giữ PK/UNIQUE/CHECK/FK tại bảng |
| “CHECK OPTION sẽ chặn DELETE” | DELETE hàng đang nhìn thấy vẫn có thể được phép | Dùng quyền/RLS/trigger để kiểm soát DELETE |
| “LOCAL luôn kiểm tra mọi tầng view” | Thay đổi thoát predicate view nền chưa được kiểm tra | Dùng CASCADED khi muốn kiểm tra các tầng tự động phù hợp |
| “LOCAL cho phép vượt mọi CHECK OPTION bên dưới” | Vi phạm check ở view nền có bảo vệ vẫn bị chặn | CHECK OPTION đã khai báo ở view nền vẫn áp dụng |
| “CASCADED chắc chắn xuyên mọi INSTEAD OF trigger/rule” | View do trigger điều khiển có ngữ nghĩa đặc thù | Kiểm tra điều kiện tại chính đường ghi và docs engine |
| “CHECK OPTION chấp nhận UNKNOWN do NULL” | Hàng bị từ chối vì không thỏa WHERE | Phải TRUE; xử lý NULL rõ ràng |
| “CHECK constraint và CHECK OPTION xử lý NULL giống hệt” | Suy sai hành vi dữ liệu thiếu | PostgreSQL CHECK thường chấp nhận UNKNOWN, view check thì không |
| “CHECK OPTION làm view GROUP BY updatable” | INSERT/UPDATE vẫn không ánh xạ được | Updatability là điều kiện độc lập |
| “Có CHECK OPTION thì không cần kiểm soát quyền” | Ghi trực tiếp bảng nguồn vẫn có thể bỏ qua view | Thiết kế privilege/RLS/API |
| “VIEW là materialized view” | Hiểu sai chỗ dữ liệu được lưu | View thông thường định nghĩa truy vấn; materialized view là loại khác |
| “SQLite cũng có WITH CHECK OPTION” | Sai cú pháp | SQLite dùng INSTEAD OF triggers để mô phỏng khi cần |
| “SQL Server/Oracle cũng có WITH LOCAL CHECK OPTION” | Sai phương ngữ | Chọn cú pháp theo engine |
| “Một hàng lỗi trong multi-row INSERT sẽ tự bỏ qua” | Cả statement PostgreSQL thất bại | Staging, validation, transaction |
| “Tên tenant là khóa duy nhất trên toàn hệ” | Rủi ro trộn tenant khi ghi qua nhiều đường | Dùng khóa ghép/phân quyền và điều kiện tenant đúng |
| “Chạy qua view lúc nào cũng nhanh hoặc chậm hơn” | Không có cơ sở về execution plan | Đo trên DBMS, index và workload thực tế |

## 27. Bài tập thực hành có đáp án

### Bài 1. Phát hiện hàng biến mất

Một view có định nghĩa:

```sql
CREATE VIEW v_drafts AS
SELECT order_id, status
FROM orders
WHERE status = 'DRAFT';
```

Chạy:

```sql
UPDATE v_drafts
SET status = 'PAID'
WHERE order_id = 1;
```

**Hỏi:** nếu view updatable và không có CHECK OPTION, chuyện gì có thể xảy ra?

**Đáp án:** cập nhật ở bảng gốc có thể thành công, sau đó hàng 1 **không còn hiển thị** qua `v_drafts` vì nó không còn là DRAFT. Định nghĩa `WHERE` không mặc nhiên ngăn hàng sau ghi rời view.

### Bài 2. Thêm CHECK OPTION

**Yêu cầu:** tạo view chỉ cho ghi đơn DRAFT của tenant 10 và kiểm tra điều kiện sau ghi.

**Đáp án PostgreSQL:**

```sql
CREATE VIEW v_t10_drafts AS
SELECT order_id, tenant_id, customer_id, status, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'DRAFT'
WITH CHECK OPTION;
```

View phải là dạng updatable phù hợp và người gọi có quyền tương ứng. Với PostgreSQL, mặc định là CASCADED nếu không nêu tùy chọn.

### Bài 3. Dự đoán INSERT sai tenant

```sql
INSERT INTO v_t10_drafts
    (order_id, tenant_id, customer_id, status, total_amount)
VALUES (500, 20, 2500, 'DRAFT', 300);
```

**Đáp án:** bị CHECK OPTION từ chối vì `tenant_id = 20` không thỏa predicate `tenant_id = 10`. Dữ liệu giá/trạng thái dù hợp lệ với bảng gốc cũng không hợp lệ khi ghi qua view này.

### Bài 4. Dự đoán UPDATE hợp lệ

```sql
UPDATE v_t10_drafts
SET total_amount = 350
WHERE order_id = 101;
```

**Đáp án:** nếu hàng 101 đang là DRAFT tenant 10 và tổng tiền 350 thỏa ràng buộc bảng, cập nhật qua view được chấp nhận, vì không làm sai điều kiện view.

### Bài 5. LOCAL trên view lồng nhau

Giả sử:

```sql
CREATE VIEW v_tenant10 AS
SELECT * FROM orders WHERE tenant_id = 10;

CREATE VIEW v_local_drafts AS
SELECT * FROM v_tenant10 WHERE status = 'DRAFT'
WITH LOCAL CHECK OPTION;
```

**Hỏi:** đổi `tenant_id` từ 10 sang 20 nhưng giữ `status = 'DRAFT'` qua `v_local_drafts` có thể xảy ra gì trên PostgreSQL?

**Đáp án:** có thể được cho phép vì LOCAL của tầng trên chỉ kiểm tra predicate trực tiếp `status = 'DRAFT'`; view nền chưa có CHECK OPTION để chặn `tenant_id = 20`. Hàng sau đó biến mất khỏi cả hai view vì không còn thuộc tenant 10.

### Bài 6. CASCADED chặn điều kiện tầng nền

Thay định nghĩa tầng trên bằng:

```sql
CREATE VIEW v_cascaded_drafts AS
SELECT * FROM v_tenant10 WHERE status = 'DRAFT'
WITH CASCADED CHECK OPTION;
```

**Đáp án:** cập nhật `tenant_id = 20` bị từ chối, vì CASCADED còn kiểm tra predicate `tenant_id = 10` ở view nền.

### Bài 7. LOCAL trên view nền đã được bảo vệ

`v_tenant10` có `WITH CHECK OPTION`; `v_local_drafts` có `WITH LOCAL CHECK OPTION`.

**Hỏi:** có thể đổi tenant từ 10 sang 20 qua view trên không?

**Đáp án:** không. CHECK OPTION ở tầng nền vẫn có hiệu lực; LOCAL tầng trên không vô hiệu hóa các CHECK OPTION đã được khai báo bên dưới.

### Bài 8. NULL trong view predicate

```sql
CREATE VIEW v_approved AS
SELECT review_id, approved
FROM reviews
WHERE approved = TRUE
WITH CHECK OPTION;
```

**Hỏi:** INSERT với `approved = NULL` có hợp lệ qua view không, dù bảng gốc cho phép NULL?

**Đáp án:** không. `approved = TRUE` là `UNKNOWN` khi approved NULL; hàng không thỏa predicate view, nên bị CHECK OPTION từ chối.

### Bài 9. DELETE có bị chặn bởi CHECK OPTION?

**Hỏi:** xóa một đơn đang nằm trong view `v_t10_drafts_checked` thì sao?

**Đáp án:** CHECK OPTION không phải chính sách cấm DELETE. DELETE có thể được phép nếu view updatable, role có quyền và các ràng buộc/triggers liên quan không ngăn. Không có “hàng sau DELETE” để yêu cầu còn thỏa predicate.

### Bài 10. View có GROUP BY

**Hỏi:** thêm `WITH CHECK OPTION` vào view `SELECT tenant_id, COUNT(*) FROM orders GROUP BY tenant_id` có làm INSERT vào view được không?

**Đáp án:** không. Các view tổng hợp như vậy không có ánh xạ DML tự động về từng hàng nguồn, nên CHECK OPTION không giải quyết được vấn đề updatable view.

### Bài 11. Đường ghi trực tiếp vào bảng gốc

**Hỏi:** tài khoản có quyền UPDATE bảng `orders` trực tiếp có thể thay `status` sang PAID dù có view DRAFT với CHECK OPTION không?

**Đáp án:** có thể, nếu không có ràng buộc/quyền/RLS/trigger khác chặn. CHECK OPTION bảo vệ thao tác qua view, không tự ràng buộc mọi đường ghi vào bảng gốc.

### Bài 12. MySQL và LOCAL/CASCADED

**Hỏi:** MySQL có hỗ trợ hai chế độ LOCAL/CASCADED và mặc định của `WITH CHECK OPTION` không nêu chế độ là gì?

**Đáp án:** MySQL có hỗ trợ **`LOCAL`** và **`CASCADED`**; mặc định là **CASCADED** đối với câu tạo view phù hợp. Vẫn phải đáp ứng quy tắc updatable view của MySQL.

### Bài 13. SQL Server

**Yêu cầu:** nêu cú pháp CHECK OPTION cho SQL Server.

**Đáp án:**

```sql
CREATE VIEW dbo.v_active_orders
AS
SELECT order_id, status
FROM dbo.orders
WHERE status = 'DRAFT'
WITH CHECK OPTION;
```

Không dùng cặp `WITH LOCAL/CASCADED CHECK OPTION` giống PostgreSQL/MySQL trong T-SQL.

### Bài 14. Oracle READ ONLY khác CHECK OPTION

**Hỏi:** `WITH READ ONLY` và `WITH CHECK OPTION` có cùng ý nghĩa không?

**Đáp án:** không. READ ONLY chủ đích **cấm DML qua view**; CHECK OPTION cho phép ghi qua view nếu view updatable và hàng sau ghi vẫn thỏa các điều kiện thuộc phạm vi kiểm tra.

### Bài 15. SQLite

**Hỏi:** tại sao không thể sao chép một câu PostgreSQL `CREATE VIEW ... WITH CHECK OPTION` vào SQLite?

**Đáp án:** SQLite không hỗ trợ native CHECK OPTION cho view. View SQLite thường chỉ đọc; để xử lý DML qua view phải dùng `INSTEAD OF` trigger và tự kiểm tra điều kiện dữ liệu tại đường ghi.

### Bài 16. Multi-row INSERT có một hàng sai

**Tình huống:** PostgreSQL INSERT qua view có CHECK OPTION với hai hàng, hàng 1 đúng tenant/status, hàng 2 sai status.

**Đáp án:** cả statement INSERT thông thường bị lỗi theo tính nguyên tử của PostgreSQL; không nên suy hàng 1 đã được commit riêng. Muốn tách hàng tốt/xấu của file nhập, dùng staging và validation trước.

### Bài 17. Cột bắt buộc bị ẩn

**Tình huống:** view chỉ chọn `order_id` và `total_amount` từ bảng có `tenant_id NOT NULL`, không có default. View có `WHERE tenant_id = 10 WITH CHECK OPTION`.

**Hỏi:** INSERT chỉ cung cấp ID và amount có tự điền tenant 10 không?

**Đáp án:** không. Predicate view không là default. Câu INSERT thiếu giá trị bắt buộc của bảng gốc sẽ lỗi trừ khi một cơ chế hợp lệ khác cung cấp giá trị.

### Bài 18. Thiết kế tenant an toàn

**Tình huống:** mỗi tenant có view lọc theo tenant_id, nhưng tài khoản ứng dụng vẫn có quyền trực tiếp UPDATE bảng nguồn.

**Đáp án:** CHECK OPTION trên view là chưa đủ. Cần giới hạn quyền trực tiếp, kiểm soát tenant từ server, cân nhắc RLS và ràng buộc khóa đúng phạm vi. View có điều kiện chỉ là **một lớp của thiết kế bảo vệ dữ liệu**.

## 28. Bảng ghi nhớ cuối bài

| Câu hỏi | Câu trả lời ngắn |
|---|---|
| View có WHERE là đủ chặn ghi ra ngoài tập? | **Không**, nếu view updatable mà không có CHECK OPTION |
| CHECK OPTION kiểm tra lúc nào? | Khi INSERT/UPDATE qua view, xét hàng sau ghi theo predicate áp dụng |
| Hàng sai điều kiện view có được chấp nhận? | **Không**, phải thỏa predicate TRUE |
| NULL khiến predicate UNKNOWN có được chấp nhận? | **Không** |
| CHECK OPTION tự sinh DEFAULT cho cột ẩn? | **Không** |
| CHECK OPTION cấm DELETE? | **Không**, DELETE có quy tắc quyền/FK/trigger riêng |
| LOCAL và CASCADED khác gì? | Phạm vi điều kiện view được kiểm tra theo tầng |
| View nền có CHECK OPTION thì LOCAL tầng trên có bỏ qua được? | **Không** |
| CASCADED luôn kiểm tra qua mọi trigger/rule? | **Không được giả định** |
| View GROUP BY tự updatable nếu thêm CHECK OPTION? | **Không** |
| CHECK OPTION có thay UNIQUE/FK/CHECK/NOT NULL? | **Không** |
| CHECK OPTION có thay phân quyền/RLS? | **Không** |
| PostgreSQL/MySQL có LOCAL/CASCADED? | **Có**, trong phạm vi tính năng tương ứng |
| SQL Server/Oracle dùng cùng cú pháp LOCAL/CASCADED? | **Không** |
| SQLite có native CHECK OPTION? | **Không**; thường cần INSTEAD OF trigger |

## 29. Nguyên tắc áp dụng vào thiết kế hệ thống

Khi cần cho phép ghi qua view, một quy trình suy nghĩ hữu ích gồm:

1. **Định nghĩa ý nghĩa của tập view:** ví dụ “đơn DRAFT của tenant 10” hay “bản ghi đã được duyệt”.
2. **Xác nhận view thực sự updatable** theo DBMS và cấu trúc SQL. View có GROUP BY/JOIN/biểu thức phức tạp không tự trở nên updatable khi có CHECK OPTION.
3. **Xác định giá trị nào người dùng được phép thay:** đổi số tiền? đổi trạng thái? chuyển tenant? xóa hàng?
4. **Bật CHECK OPTION nếu muốn dữ liệu sau ghi còn thuộc tập view.** Với view lồng nhau, chọn LOCAL hay CASCADED theo phạm vi cần bảo vệ.
5. **Đảm bảo ràng buộc bảng gốc vẫn đúng:** PK/UNIQUE, NOT NULL, CHECK, FK và default độc lập với CHECK OPTION.
6. **Thử cả INSERT và UPDATE:** hàng hợp lệ, sai tenant, sai trạng thái, NULL, hàng có khóa trùng, thiếu cột bắt buộc và thao tác DELETE.
7. **Kiểm tra đường ghi thực tế:** nếu view dùng INSTEAD OF trigger/rule, hiểu nơi điều kiện sẽ được thực thi; đừng suy từ cú pháp alone.
8. **Kiểm soát quyền:** view CHECK OPTION không đủ nếu role có đường UPDATE bảng nguồn không hạn chế; xem xét RLS và tenant authorization.
9. **Đối soát sau thao tác:** xem số hàng bị tác động, trạng thái ở bảng nguồn và view; dùng transaction/rollback khi thử nghiệm.
10. **Tôn trọng phương ngữ:** PostgreSQL/MySQL/MariaDB có LOCAL/CASCADED; SQL Server/Oracle có cú pháp khác; SQLite thường cần trigger thay thế.

**Kết luận:** `WITH CHECK OPTION` là một ràng buộc quan trọng khi **ghi qua view có điều kiện**: nó ngăn một thao tác `INSERT`/`UPDATE` tạo ra hàng không còn đáp ứng tiêu chí mà view đại diện. Với view lồng nhau, `LOCAL` và `CASCADED` xác định **độ sâu kiểm tra** nhưng không tự thay thế kiểm tra ở tầng nền đã có. CHECK OPTION không sinh giá trị mặc định, không làm view phức tạp tự cập nhật được, không cấm DELETE và không thay thế các ràng buộc hay quyền trên bảng gốc. Sử dụng đúng cần kết hợp **ngữ nghĩa view, schema, transaction, kiểm soát truy cập và tính năng của đúng DBMS**.

