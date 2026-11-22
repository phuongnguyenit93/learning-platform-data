# DELETE USING và kiểm soát phạm vi xóa trong PostgreSQL

Khi vận hành một hệ thống có nhiều khách hàng, việc xóa dữ liệu ít khi chỉ là câu lệnh `DELETE FROM orders WHERE id = 1`. Những yêu cầu thực tế thường có dạng: “Xóa đơn hàng đã hủy trước ngày lưu trữ, nhưng **chỉ** của tổ chức đang xử lý và **chỉ** khi khách hàng đã đóng tài khoản”, “Dọn các hàng có khóa không còn tồn tại ở bảng đối chiếu”, hoặc “Xóa từng đợt 100 bản ghi đủ điều kiện mà không chặn các tiến trình khác”.

Trong PostgreSQL, cú pháp **`DELETE ... USING`** cho phép đưa **bảng khác, truy vấn con hoặc CTE** vào phép xác định những hàng của bảng đích phải xóa. Nó đặc biệt hữu ích khi điều kiện xóa phụ thuộc dữ liệu trong bảng liên quan.

Tuy nhiên, một câu lệnh đúng cú pháp vẫn có thể gây mất dữ liệu nếu:

- Thiếu điều kiện `WHERE` hoặc thiếu một điều kiện kết nối.
- Bỏ quên giới hạn `tenant_id` trong hệ thống nhiều tổ chức.
- Dùng nhầm `AND`/`OR` khiến phạm vi rộng hơn dự định.
- Nối bằng khóa chỉ duy nhất **trong từng tenant** nhưng quên so khớp tenant.
- Nhầm số hàng sau `JOIN` với số **hàng đích** sẽ bị xóa.
- Không kiểm tra ảnh hưởng của khóa ngoại `ON DELETE CASCADE`, trigger, partition hoặc các bảng liên quan.
- Chỉ chạy `SELECT` kiểm tra trước rồi mặc định tập hàng không thay đổi khi `DELETE` được thực hiện sau đó.
- Cố gắng viết `DELETE ... LIMIT` như ở một số hệ quản trị khác.

Bài học thuộc chương **Thay đổi dữ liệu** của module *Database Engine Relational PostgreSQL*. Mục tiêu là hiểu đúng ngữ nghĩa của `DELETE USING` và hình thành quy trình **xác định phạm vi – xem trước – kiểm tra phụ thuộc – xóa trong giao dịch – xác nhận – ghi nhận/khôi phục**.

> **Cảnh báo thực hành:** `DELETE` tác động trực tiếp lên dữ liệu. Mọi bảng trong bài sử dụng schema riêng `delete_lab`, giá trị giả định và các khối `BEGIN ... ROLLBACK` để dễ thử lại. Không chạy `DELETE` hoặc `DROP` trên dữ liệu thực trước khi kiểm tra quyền, phạm vi, bản sao lưu và quy trình phê duyệt của hệ thống.

## 1. DELETE cơ bản: xóa hàng nào của bảng nào?

### 1.1. Cú pháp tối thiểu

```sql
DELETE FROM some_table
WHERE some_condition;
```

PostgreSQL xóa các hàng **của bảng được chỉ định sau `DELETE FROM`** thỏa điều kiện. Nếu không có `WHERE`, lệnh không còn bộ lọc hàng đích:

```sql
-- Cực kỳ nguy hiểm khi bảng có dữ liệu thật:
-- DELETE FROM some_table;
```

Lệnh trên có thể xóa toàn bộ hàng được phép xóa trong bảng. **Không** xem việc thêm `USING` là một lớp bảo vệ mặc định; điều kiện nối và lọc mới quyết định phạm vi.

### 1.2. Xóa hàng khác với xóa bảng

| Lệnh | Tác dụng | Có WHERE theo hàng? |
|---|---|---|
| `DELETE FROM table WHERE ...` | Xóa những hàng phù hợp | Có |
| `DELETE FROM table` | Xóa mọi hàng phù hợp với quyền/chính sách hiện hành | Không |
| `TRUNCATE table` | Làm rỗng bảng theo cơ chế riêng | Không |
| `DROP TABLE table` | Xóa định nghĩa bảng cùng dữ liệu | Không |

`DELETE` không tự xóa cấu trúc bảng, chỉ mục hay schema. Trong PostgreSQL, các hàng bị xóa có thể vẫn chiếm dung lượng vật lý một thời gian do MVCC; `VACUUM`/autovacuum sẽ xử lý các phiên bản hàng chết theo điều kiện của hệ thống.

### 1.3. DELETE và UPDATE không có cùng ý nghĩa

Nếu nghiệp vụ muốn **giữ lịch sử** hoặc “ngừng hoạt động”, có thể phù hợp hơn với:

```sql
UPDATE some_table
SET deleted_at = CURRENT_TIMESTAMP
WHERE ...;
```

Đây là **soft delete**, không phải xóa vật lý. Nó mang hệ quả riêng về truy vấn, uniqueness, bảo mật và chính sách lưu trữ. Không mặc định soft delete luôn đáp ứng yêu cầu xóa dữ liệu thật theo chính sách.

## 2. DELETE USING: cú pháp PostgreSQL và ý nghĩa

Mẫu cơ bản:

```sql
DELETE FROM target_table AS t
USING related_table AS r
WHERE t.related_id = r.id
  AND r.some_flag = 'yes'
RETURNING t.id;
```

Các phần:

- **`DELETE FROM target_table AS t`**: chỉ ra **bảng đích** có hàng sẽ bị xóa.
- **`USING related_table AS r`**: thêm nguồn dữ liệu để xét điều kiện; **không có nghĩa xóa hàng của r**.
- **`WHERE t.related_id = r.id`**: nối hàng của bảng đích với nguồn liên quan.
- **`AND r.some_flag = 'yes'`**: chọn những hàng đáp ứng quy tắc nghiệp vụ.
- **`RETURNING t.id`**: trả về thông tin của những hàng đích vừa bị xóa.

Ngữ nghĩa đơn giản là:

> Xóa một hàng **t** nếu có một cách kết hợp nó với các nguồn trong `USING` khiến biểu thức `WHERE` đúng.

Nếu một hàng đích kết hợp được với **nhiều** hàng nguồn, bản thân hàng đích vẫn chỉ có thể bị xóa **một lần** trong statement đó. Nhưng một truy vấn `SELECT` dùng cùng join có thể sinh nhiều hàng; phải phân biệt hai loại số đếm.

### 2.1. So sánh với DELETE JOIN của MySQL

Không dùng cú pháp kiểu:

```sql
-- Đây không phải cú pháp DELETE JOIN PostgreSQL:
-- DELETE o
-- FROM orders AS o
-- JOIN customers AS c ON c.customer_id = o.customer_id
-- WHERE c.status = 'closed';
```

Trong PostgreSQL, viết:

```sql
-- Ví dụ cú pháp PostgreSQL:
-- DELETE FROM orders AS o
-- USING customers AS c
-- WHERE c.customer_id = o.customer_id
--   AND c.status = 'closed';
```

`USING` tham gia vào điều kiện xác định hàng cần xóa, không phải một `JOIN` đặt ngay sau tên bảng đích theo cú pháp MySQL.

### 2.2. Alias của bảng đích

Khi khai báo:

```sql
DELETE FROM delete_lab.orders AS o
...
```

trong phần còn lại của statement hãy dùng alias **`o`** để tham chiếu bảng đích. PostgreSQL coi alias là tên biểu diễn bảng đích trong phạm vi truy vấn; dùng lại tên bảng gốc để tham chiếu như không có alias có thể gây lỗi.

### 2.3. Bảng nào bị xóa?

Trong câu:

```sql
DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE ...
```

chỉ các hàng của **`delete_lab.orders`** là mục tiêu xóa trực tiếp. Bảng `customers` đóng vai trò nguồn điều kiện và không tự bị xóa bởi lệnh này.

**Ngoại lệ gián tiếp:** khóa ngoại với `ON DELETE CASCADE`, trigger hoặc cơ chế dữ liệu khác có thể làm **các bảng liên quan** thay đổi. Vì vậy “chỉ bảng đích được gọi tên” không đồng nghĩa “toàn database chỉ thay đổi bảng đó”.

## 3. Dựng môi trường thực hành hai tenant

Ta mô phỏng ứng dụng nhiều tổ chức. `customer_id` chỉ duy nhất **trong một tenant**; tên khách hoặc ID có thể được sử dụng lại ở tenant khác. Một yêu cầu xóa đúng phải phân biệt cả **`tenant_id`** và **`customer_id`**.

### 3.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS delete_lab;

CREATE TABLE delete_lab.customers (
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    customer_name TEXT NOT NULL,
    account_status TEXT NOT NULL
        CHECK (account_status IN ('active', 'closed')),
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE delete_lab.orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled', 'refunded')),
    created_at TIMESTAMPTZ NOT NULL,
    cancelled_at TIMESTAMPTZ,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    CONSTRAINT fk_order_customer
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES delete_lab.customers(tenant_id, customer_id),
    CONSTRAINT chk_cancel_date
        CHECK (status <> 'cancelled' OR cancelled_at IS NOT NULL)
);
```

**Lưu ý thiết kế:** `orders.order_id` là khóa chính toàn bảng; còn quan hệ khách hàng dùng **khóa ghép** `(tenant_id, customer_id)`. Điều này tránh việc một đơn tenant 10 tham chiếu nhầm khách tenant 20 có cùng `customer_id`.

### 3.2. Dữ liệu khách hàng

```sql
INSERT INTO delete_lab.customers
    (tenant_id, customer_id, customer_name, account_status)
VALUES
    (10, 101, 'An',       'active'),
    (10, 102, 'Bình',     'closed'),
    (10, 103, 'Chi',      'closed'),
    (10, 104, 'Dũng',     'active'),
    (20, 101, 'Hà',       'closed'),
    (20, 201, 'Khánh',    'closed'),
    (20, 202, 'Lan',      'active'),
    (20, 203, 'Minh',     'closed');
```

**Bẫy cố ý:** cả tenant 10 và tenant 20 đều có `customer_id=101`, nhưng tenant 10 đang **active**, tenant 20 đã **closed**. Một phép nối chỉ bằng `customer_id` có thể gắn nhầm trạng thái của khách khác tenant.

### 3.3. Dữ liệu đơn hàng

```sql
INSERT INTO delete_lab.orders
    (order_id, tenant_id, customer_id, status,
     created_at, cancelled_at, amount)
VALUES
    ( 1, 10, 101, 'paid',
      '2026-09-01 09:00+07', NULL, 300),
    ( 2, 10, 102, 'cancelled',
      '2026-09-01 10:00+07', '2026-09-05 12:00+07', 180),
    ( 3, 10, 103, 'cancelled',
      '2026-09-10 09:00+07', '2026-09-12 14:00+07', 250),
    ( 4, 10, 104, 'pending',
      '2026-10-04 08:00+07', NULL, 75),
    ( 5, 10, 101, 'cancelled',
      '2026-09-20 08:00+07', '2026-09-20 10:00+07', 95),
    ( 6, 20, 101, 'cancelled',
      '2026-08-01 07:00+07', '2026-08-11 09:00+07', 210),
    ( 7, 20, 202, 'paid',
      '2026-10-03 15:00+07', NULL, 140),
    ( 8, 20, 203, 'cancelled',
      '2026-09-03 10:00+07', '2026-09-12 11:00+07', 120),
    ( 9, 10, 101, 'refunded',
      '2026-10-07 10:00+07', NULL, 85),
    (10, 10, 102, 'cancelled',
      '2026-10-08 09:00+07', '2026-10-09 10:00+07', 155),
    (11, 20, 201, 'cancelled',
      '2026-09-28 13:00+07', '2026-09-29 12:00+07', 265),
    (12, 20, 203, 'paid',
      '2026-10-12 11:00+07', NULL, 190);
```

Tổng cộng có **12 đơn**. Mỗi timestamp kèm `+07` để các khoảng ngày trong ví dụ có ranh giới rõ ràng.

### 3.4. Dữ liệu chi tiết đơn và cờ xử lý

Để quan sát ảnh hưởng của việc xóa đơn hàng lên bảng con, tạo `order_items` với `ON DELETE CASCADE`:

```sql
CREATE TABLE delete_lab.order_items (
    item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES delete_lab.orders(order_id)
        ON DELETE CASCADE,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

INSERT INTO delete_lab.order_items
    (item_id, order_id, sku, quantity)
VALUES
    (1001, 2, 'SKU-A', 1),
    (1002, 2, 'SKU-B', 2),
    (1003, 3, 'SKU-A', 1),
    (1004, 5, 'SKU-C', 1),
    (1005, 6, 'SKU-D', 1),
    (1006, 7, 'SKU-B', 1),
    (1007, 8, 'SKU-A', 1),
    (1008, 9, 'SKU-D', 1),
    (1009, 10, 'SKU-B', 1);
```

Thêm bảng cờ, trong đó **một đơn có thể khớp nhiều cờ**:

```sql
CREATE TABLE delete_lab.order_flags (
    order_id BIGINT NOT NULL
        REFERENCES delete_lab.orders(order_id)
        ON DELETE CASCADE,
    flag TEXT NOT NULL,
    PRIMARY KEY (order_id, flag)
);

INSERT INTO delete_lab.order_flags(order_id, flag)
VALUES
    (2, 'expired'),
    (2, 'reviewed'),
    (3, 'expired'),
    (5, 'expired'),
    (6, 'expired');
```

Hệ thống đã có FK từ `order_items` và `order_flags` về `orders`. Khi xóa đơn 2, hai dòng item và hai cờ của đơn 2 cũng có thể bị xóa bởi cascade. **Số dòng `DELETE FROM orders ... RETURNING` chỉ phản ánh các đơn hàng đích**, không tự đếm các dòng con bị cascade.

## 4. Xác định yêu cầu xóa trước khi viết SQL

Giả sử có yêu cầu:

> “Xóa các đơn hàng của **tenant 10**, có trạng thái **`cancelled`**, thời điểm hủy **trước 00:00 ngày 01/10/2026 theo +07**, và chỉ khi **khách hàng trong cùng tenant** đã đóng tài khoản.”

Ta tách thành điều kiện kiểm chứng:

| Yêu cầu | Biểu thức SQL |
|---|---|
| Chỉ tenant 10 | `o.tenant_id = 10` |
| Chỉ đơn đã hủy | `o.status = 'cancelled'` |
| Hủy trước mốc | `o.cancelled_at < TIMESTAMPTZ '2026-10-01 00:00:00+07'` |
| Đối chiếu khách đúng tenant | `c.tenant_id = o.tenant_id` |
| Đối chiếu đúng customer | `c.customer_id = o.customer_id` |
| Khách đóng tài khoản | `c.account_status = 'closed'` |

**Tập mục tiêu dự kiến là hai đơn `order_id=2` và `order_id=3`**, không phải toàn bộ đơn cancelled cũ.

Vì sao các đơn khác không hợp lệ?

- Đơn 5: tenant 10, cancelled cũ nhưng khách 101 của tenant 10 **vẫn active**.
- Đơn 10: tenant 10, khách closed, nhưng `cancelled_at` **sau** mốc.
- Đơn 6, 8, 11: cancelled cũ, khách closed, nhưng thuộc **tenant 20**.
- Đơn 1, 4, 9: không phải cancelled.

Đây là bước quan trọng nhất của “kiểm soát phạm vi xóa”: phải có **danh sách và lý do loại trừ**, không chỉ một điều kiện `WHERE` nhìn có vẻ đúng.

## 5. Xem trước bằng SELECT trước khi DELETE

Đầu tiên, viết truy vấn `SELECT` phản ánh **chính xác cùng quan hệ nối và bộ lọc** sẽ dùng khi xóa:

```sql
SELECT
    o.order_id,
    o.tenant_id,
    o.customer_id,
    c.customer_name,
    c.account_status,
    o.status,
    o.cancelled_at,
    o.amount
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
ORDER BY o.order_id;
```

Kết quả chính:

| order_id | tenant_id | customer_id | customer_name | status | account_status |
|---:|---:|---:|---|---|---|
| 2 | 10 | 102 | Bình | cancelled | closed |
| 3 | 10 | 103 | Chi | cancelled | closed |

### 5.1. Đếm mục tiêu trước

```sql
SELECT COUNT(*) AS target_orders
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed';
```

Vì mỗi đơn khớp đúng một customer theo khóa ghép, kết quả là **2**. Nhưng khi nguồn `USING` có quan hệ một-nhiều, `COUNT(*)` của một `JOIN` tương tự có thể đếm **lặp cùng đơn**, nên cần xem thêm mục 8.

### 5.2. Có thể liệt kê chỉ ID để duyệt

```sql
SELECT o.order_id
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON (c.tenant_id, c.customer_id)
     = (o.tenant_id, o.customer_id)
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
ORDER BY o.order_id;
```

Điều kiện hàng row-comparison ở trên chỉ là cách viết ngắn của hai phép so sánh bằng. Với các cột khóa `NOT NULL` trong lab, hai cách tương đương về ý nghĩa. Để dễ review SQL production, nhiều nhóm vẫn chọn viết rõ **hai điều kiện nối**.

**Cảnh báo:** `SELECT` trước xóa chưa phải một “đảm bảo khóa chặt” rằng kết quả xóa sau đó luôn đúng chính hai ID. Nếu giao dịch khác thay đổi dữ liệu giữa hai câu lệnh, tập phù hợp có thể khác. Phần 13 giải thích cách giảm rủi ro này.

## 6. DELETE USING đúng yêu cầu

Câu lệnh PostgreSQL:

```sql
DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
RETURNING
    o.order_id,
    o.tenant_id,
    o.customer_id,
    o.status,
    o.cancelled_at;
```

Nếu chạy trên dữ liệu lab nguyên vẹn, statement xóa **đúng hai đơn 2 và 3**.

### 6.1. Vì sao điều kiện nối nằm trong WHERE?

Trong PostgreSQL, `USING` đưa các nguồn vào statement; các quan hệ nối với bảng đích thường được viết ở **`WHERE`**:

```sql
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
```

Nếu quên điều kiện `c.customer_id = o.customer_id` nhưng vẫn có một khách `closed` trong tenant 10, nhiều đơn của tenant đó có thể được ghép với khách đóng tài khoản **không liên quan**, khiến điều kiện theo trạng thái khách mất ý nghĩa.

Nếu quên `c.tenant_id = o.tenant_id`, việc trùng `customer_id` giữa hai tenant có thể gắn trạng thái khách sai. Bài lab cố ý có khách 101 ở cả tenant 10 và tenant 20 để thấy bẫy này.

### 6.2. Điều kiện tenant không nên chỉ xuất hiện bên USING

Đừng dựa vào:

```sql
-- Không đủ để bảo vệ phạm vi nếu thiếu join tenant đúng:
-- WHERE c.tenant_id = 10
--   AND c.account_status = 'closed'
--   AND o.customer_id = c.customer_id
```

Nếu `customer_id` chỉ duy nhất trong từng tenant, đơn của tenant khác có thể khớp khách tenant 10. Hãy kiểm soát cả:

```sql
o.tenant_id = 10
AND c.tenant_id = o.tenant_id
AND c.customer_id = o.customer_id
```

Ở hệ thống có RLS, tenant predicate còn phải phù hợp với chính sách quyền; xem mục 15.

### 6.3. RETURNING cho biết những hàng đích bị xóa

`RETURNING` rất có ích cho vận hành vì:

- Ghi nhận ID vừa xóa.
- Cho biết có thực sự xóa đúng tập dự định hay không.
- Có thể chuyển dữ liệu sang bảng lưu vết theo một statement dữ liệu sửa đổi.
- Tránh suy đoán từ thông báo “DELETE 2” mà không biết hai ID là gì.

Nó **không** tự tạo backup bền vững, không cho biết toàn bộ các dòng con bị cascade, và không đảm bảo bạn có thể khôi phục sau commit nếu không có kế hoạch lưu trữ/backup tương ứng.

## 7. Thử xóa trong giao dịch rồi ROLLBACK

Để học hoặc xem tác động trước khi commit, bọc thao tác trong transaction:

```sql
BEGIN;

SELECT
    o.order_id,
    o.tenant_id,
    o.customer_id,
    o.cancelled_at
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
ORDER BY o.order_id;

DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
RETURNING o.order_id, o.tenant_id, o.customer_id;

-- Xem trạng thái trong transaction hiện tại:
SELECT order_id
FROM delete_lab.orders
WHERE order_id IN (2, 3)
ORDER BY order_id;

-- Hủy thử nghiệm: khôi phục thay đổi của transaction này.
ROLLBACK;
```

Sau `ROLLBACK`, hai đơn và các dòng con bị cascade trong transaction được giữ lại như trước khi chạy statement (giả sử không có thay đổi khác ngoài transaction thử nghiệm).

### 7.1. ROLLBACK là công cụ kiểm tra, không phải backup lâu dài

Một khi đã `COMMIT` thao tác xóa, không thể chạy `ROLLBACK` sau đó để đảo ngược transaction đã hoàn tất. Cần có **backup, bản lưu trữ, audit, point-in-time recovery** hoặc quy trình khôi phục đã được chuẩn bị trước.

### 7.2. Xác nhận trước khi COMMIT

Ở môi trường thật, trước `COMMIT` nên đối chiếu:

- Số hàng đích được xóa.
- Danh sách khóa/tenant trong `RETURNING`.
- Ảnh hưởng lên bảng con và những thao tác do trigger sinh ra.
- Mọi trường hợp nằm ngoài tiêu chí phải còn nguyên.
- Kết quả log/audit và trạng thái transaction.

Nếu phát hiện số hàng khác dự kiến, **ROLLBACK** và điều tra; không cố gắng “sửa nhanh điều kiện” sau khi đã commit nhầm.

## 8. Một đơn khớp nhiều hàng USING vẫn chỉ bị xóa một lần

Với `order_flags`, đơn 2 có hai cờ `expired` và `reviewed`.

Xem kết quả JOIN:

```sql
SELECT
    o.order_id,
    f.flag
FROM delete_lab.orders AS o
JOIN delete_lab.order_flags AS f
    ON f.order_id = o.order_id
WHERE o.tenant_id = 10
  AND o.order_id IN (2, 3)
  AND f.flag IN ('expired', 'reviewed')
ORDER BY o.order_id, f.flag;
```

Kết quả có **ba hàng JOIN**:

| order_id | flag |
|---:|---|
| 2 | expired |
| 2 | reviewed |
| 3 | expired |

Nhưng tập **đơn đích duy nhất** chỉ có **2 ID**.

Thử trong giao dịch:

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
USING delete_lab.order_flags AS f
WHERE f.order_id = o.order_id
  AND o.tenant_id = 10
  AND o.order_id IN (2, 3)
  AND f.flag IN ('expired', 'reviewed')
RETURNING o.order_id;

ROLLBACK;
```

`DELETE RETURNING` trả mỗi đơn đích đã xóa **một lần**, không trả ID 2 hai lần chỉ vì có hai dòng `order_flags` khớp. Đây là khác biệt giữa **số hàng JOIN** và **số hàng bị xóa**.

### 8.1. Đếm chính xác đối tượng xóa trong SELECT

Nếu nguồn có fanout:

```sql
SELECT
    COUNT(*) AS join_rows,
    COUNT(DISTINCT o.order_id) AS target_orders
FROM delete_lab.orders AS o
JOIN delete_lab.order_flags AS f
    ON f.order_id = o.order_id
WHERE o.tenant_id = 10
  AND o.order_id IN (2, 3)
  AND f.flag IN ('expired', 'reviewed');
```

Kết quả: `join_rows=3`, `target_orders=2`.

Đừng dùng `COUNT(*)` của JOIN một-nhiều để báo “sẽ xóa 3 đơn”, vì điều đó có thể khiến kiểm tra phạm vi và giới hạn số hàng sai.

### 8.2. DISTINCT ở SELECT xem trước

Có thể xem một hàng cho mỗi đơn:

```sql
SELECT DISTINCT
    o.order_id,
    o.tenant_id
FROM delete_lab.orders AS o
JOIN delete_lab.order_flags AS f
    ON f.order_id = o.order_id
WHERE o.tenant_id = 10
  AND f.flag IN ('expired', 'reviewed')
ORDER BY o.order_id;
```

Nhưng nếu SELECT thêm `f.flag`, các hàng có cờ khác nhau không còn trùng toàn bộ cột, nên `DISTINCT` không co về một hàng mỗi đơn. Khi mục tiêu chỉ là **“có ít nhất một cờ phù hợp”**, `EXISTS` thường diễn đạt rõ hơn.

## 9. DELETE USING so với WHERE EXISTS

Một truy vấn `DELETE` phụ thuộc bảng khác có thể viết bằng `USING` hoặc `EXISTS`.

### 9.1. USING: nối tường minh

```sql
-- Ví dụ trong transaction thử nghiệm:
BEGIN;

DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
RETURNING o.order_id;

ROLLBACK;
```

### 9.2. EXISTS: điều kiện tồn tại

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND EXISTS (
      SELECT 1
      FROM delete_lab.customers AS c
      WHERE c.tenant_id = o.tenant_id
        AND c.customer_id = o.customer_id
        AND c.account_status = 'closed'
  )
RETURNING o.order_id;

ROLLBACK;
```

Với dữ liệu, khóa và điều kiện trong ví dụ, hai câu lệnh có cùng tập đơn mục tiêu: **2 và 3**.

### 9.3. Khi nào chọn cách nào?

| Tiêu chí | `DELETE USING` | `DELETE WHERE EXISTS` |
|---|---|---|
| Muốn viết điều kiện dựa vào nhiều bảng | Tự nhiên qua nguồn `USING` | Tự nhiên qua truy vấn con |
| Muốn diễn đạt “có ít nhất một hàng liên quan” | Có thể, nhưng join có thể tạo nhiều hàng | **Rất rõ nghĩa** |
| Nguồn một-nhiều | Có thể sinh fanout ở phép match | Không cần quan tâm số hàng match sau hàng đầu về mặt ngữ nghĩa |
| Tham chiếu cột bảng liên quan trong điều kiện | Thuận tiện | Thuận tiện trong subquery |
| Hiệu năng | Phụ thuộc kế hoạch | Phụ thuộc kế hoạch |

Không mặc định `USING` luôn nhanh hơn `EXISTS` hay ngược lại. PostgreSQL optimizer có thể chọn kế hoạch khác nhau theo thống kê, index, số hàng và điều kiện; cần `EXPLAIN` trên dữ liệu đại diện.

### 9.4. NOT EXISTS: xóa hàng không có đối chiếu

Một yêu cầu khác là “xóa đơn có mã xử lý cũ **không còn** tồn tại trong bảng đối chiếu”. Đây là anti-join, thường diễn đạt bằng `NOT EXISTS`.

Ví dụ một bảng staging:

```sql
CREATE TABLE delete_lab.import_candidates (
    tenant_id INTEGER NOT NULL,
    external_code TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, external_code)
);

CREATE TABLE delete_lab.valid_external_codes (
    tenant_id INTEGER NOT NULL,
    external_code TEXT NOT NULL,
    PRIMARY KEY (tenant_id, external_code)
);

INSERT INTO delete_lab.import_candidates
    (tenant_id, external_code, imported_at)
VALUES
    (10, 'A-01', '2026-09-01 00:00+07'),
    (10, 'X-99', '2026-09-01 00:00+07'),
    (20, 'X-99', '2026-09-01 00:00+07');

INSERT INTO delete_lab.valid_external_codes
    (tenant_id, external_code)
VALUES
    (10, 'A-01'),
    (20, 'X-99');
```

Xem trước hàng **không có mã hợp lệ trong cùng tenant**:

```sql
SELECT i.tenant_id, i.external_code
FROM delete_lab.import_candidates AS i
WHERE i.tenant_id = 10
  AND NOT EXISTS (
      SELECT 1
      FROM delete_lab.valid_external_codes AS v
      WHERE v.tenant_id = i.tenant_id
        AND v.external_code = i.external_code
  )
ORDER BY i.external_code;
```

Kết quả chỉ có `(10, 'X-99')`.

Thử xóa:

```sql
BEGIN;

DELETE FROM delete_lab.import_candidates AS i
WHERE i.tenant_id = 10
  AND NOT EXISTS (
      SELECT 1
      FROM delete_lab.valid_external_codes AS v
      WHERE v.tenant_id = i.tenant_id
        AND v.external_code = i.external_code
  )
RETURNING i.tenant_id, i.external_code;

ROLLBACK;
```

`DELETE USING` chỉ với inner-match thông thường **không tự diễn đạt** điều kiện “không tồn tại hàng đối chiếu”. Dùng `NOT EXISTS` giúp rõ ngữ nghĩa và tránh nhầm lẫn `LEFT JOIN ... IS NULL` trong truy vấn xóa.

## 10. Kiểm soát phạm vi bằng khóa và điều kiện nghiệp vụ

Trước thao tác xóa hàng loạt, nên liệt kê mọi chiều làm giảm phạm vi:

### 10.1. Tenant / tổ chức

```sql
WHERE o.tenant_id = 10
```

Nếu hệ thống chia dữ liệu theo tenant, đây thường là điều kiện **không thể bỏ**. Nhưng chỉ thêm ở một bảng khác không đủ; các điều kiện JOIN cũng phải đảm bảo không nối chéo.

### 10.2. Trạng thái

```sql
AND o.status = 'cancelled'
```

Không nên chỉ lọc theo `cancelled_at IS NOT NULL` nếu trạng thái có thể được phục hồi, hoặc logic hiện tại dùng `cancelled_at` như dấu vết lịch sử. Nguồn sự thật của trạng thái phải được định nghĩa rõ.

### 10.3. Mốc thời gian đúng

```sql
AND o.cancelled_at <
    TIMESTAMPTZ '2026-10-01 00:00:00+07'
```

Nếu yêu cầu là “hủy trước ngày 1/10”, phải lọc theo **thời điểm hủy** chứ không nhất thiết theo `created_at`. Một đơn tạo từ tháng 8 nhưng vừa hủy hôm qua **không nên bị coi là đơn đã hủy từ tháng 8** chỉ vì ngày tạo cũ.

### 10.4. Ranh giới nửa mở

`< TIMESTAMPTZ '2026-10-01 00:00+07'` loại thời điểm **đúng 00:00 ngày 1/10**. Tránh diễn đạt “trước ngày 1/10” bằng `<= '2026-09-30 23:59:59'` vì timestamp có phần thập phân của giây và dễ phát sinh lỗ hổng.

### 10.5. Điều kiện bảng đối chiếu

```sql
AND c.account_status = 'closed'
```

Cần xác minh cột đang phản ánh **trạng thái hiện tại** hay trạng thái tại thời điểm đơn được hủy. Nếu yêu cầu pháp lý/nghiệp vụ dựa vào trạng thái lịch sử, bảng customers hiện tại có thể không đủ; phải chọn fact/event thích hợp.

### 10.6. Phạm vi quyền người chạy

Ngay cả khi SQL có đủ bộ lọc, tài khoản database nên có quyền **tối thiểu cần thiết**. Với tác vụ xóa thường xuyên, cân nhắc role riêng, chính sách RLS, job/approval và audit.

**Bộ lọc nghiệp vụ và phân quyền là hai lớp khác nhau**: có `o.tenant_id=10` không có nghĩa một role mặc nhiên được cấp quyền xóa dữ liệu của tenant 10.

## 11. Bẫy AND, OR và dấu ngoặc

Một điều kiện xóa sai rất phổ biến:

```sql
-- Không chạy: có thể xóa đơn 'cancelled' của tenant khác!
-- DELETE FROM delete_lab.orders
-- WHERE tenant_id = 10 AND status = 'pending'
--    OR status = 'cancelled';
```

Do `AND` có độ ưu tiên cao hơn `OR`, điều kiện trên được hiểu như:

```sql
WHERE (tenant_id = 10 AND status = 'pending')
   OR (status = 'cancelled')
```

Vế thứ hai **không giới hạn tenant**, nên các đơn `cancelled` của tenant 20 cũng có thể bị xóa.

Nếu yêu cầu là “xóa pending hoặc cancelled **trong tenant 10**”, viết:

```sql
WHERE tenant_id = 10
  AND status IN ('pending', 'cancelled')
```

hoặc:

```sql
WHERE tenant_id = 10
  AND (status = 'pending' OR status = 'cancelled')
```

### 11.1. Hãy thử điều kiện bằng SELECT trước

```sql
SELECT order_id, tenant_id, status
FROM delete_lab.orders
WHERE tenant_id = 10
  AND status IN ('pending', 'cancelled')
ORDER BY order_id;
```

Nếu phạm vi rộng hơn dự kiến, sửa `SELECT` **trước** khi chuyển thành `DELETE`.

### 11.2. Chú ý WHERE với NULL

`status <> 'paid'` không bao gồm giá trị `NULL` nếu cột cho phép NULL, vì so sánh với NULL cho unknown. Trong bảng lab `status NOT NULL`, bẫy này không xảy ra; nhưng trong schema khác cần xét cả:

```sql
-- Ví dụ logic khi cột status nullable:
-- WHERE status IS DISTINCT FROM 'paid'
```

Toán tử `IS DISTINCT FROM` có ngữ nghĩa so sánh rõ ngay cả khi một phía là NULL. Đừng dùng nó thay `<>` mà không xem yêu cầu: mở rộng tập hàng được chọn để xóa có thể là sai nghiệp vụ.

## 12. RETURNING và ghi nhận số hàng đã xóa

### 12.1. DELETE ... RETURNING

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
WHERE o.tenant_id = 10
  AND o.order_id IN (2, 3)
RETURNING
    o.order_id,
    o.tenant_id,
    o.customer_id,
    o.status,
    o.amount;

ROLLBACK;
```

Trên dữ liệu nguyên vẹn, `RETURNING` trả đúng hai hàng. Nó hữu ích để đối chiếu với danh sách đã duyệt.

### 12.2. Đếm số hàng xóa trong cùng statement

Có thể dùng data-modifying CTE:

```sql
BEGIN;

WITH removed AS (
    DELETE FROM delete_lab.orders AS o
    USING delete_lab.customers AS c
    WHERE c.tenant_id = o.tenant_id
      AND c.customer_id = o.customer_id
      AND o.tenant_id = 10
      AND o.status = 'cancelled'
      AND o.cancelled_at <
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND c.account_status = 'closed'
    RETURNING o.order_id
)
SELECT COUNT(*) AS deleted_order_count
FROM removed;

ROLLBACK;
```

Kết quả **2** nếu dữ liệu lab còn nguyên.

Đây là **số hàng của bảng orders** được xóa và trả về qua CTE, không phải số item con hoặc hàng của bảng customers.

### 12.3. Data-modifying CTE cần hiểu đúng snapshot

Trong PostgreSQL, statement dữ liệu sửa đổi trong `WITH` được thực thi và dữ liệu `RETURNING` là kênh rõ ràng để truyền kết quả sang truy vấn chính. Các phần trong cùng statement dùng quy tắc snapshot riêng của data-modifying CTE; **không** nên thay `RETURNING` bằng cách mong một `SELECT` bên ngoài đọc lại bảng đích trong cùng statement và nhìn thấy ngay toàn bộ thay đổi theo thứ tự tưởng tượng.

**Quy tắc thực hành:** khi muốn biết hàng nào vừa được xóa trong statement đó, **dùng `RETURNING`**. Khi muốn xác minh trạng thái bảng sau xóa, thực hiện `SELECT` **ở statement kế tiếp trong cùng transaction**.

### 12.4. Lưu audit trong cùng transaction

Một bản ghi xóa có thể được lưu vào bảng audit **trước khi commit**. Ví dụ:

```sql
CREATE TABLE delete_lab.deleted_order_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    old_status TEXT NOT NULL,
    old_amount NUMERIC(12, 2) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Thao tác thử:

```sql
BEGIN;

WITH removed AS (
    DELETE FROM delete_lab.orders AS o
    WHERE o.tenant_id = 10
      AND o.order_id IN (2, 3)
    RETURNING
        o.order_id,
        o.tenant_id,
        o.customer_id,
        o.status,
        o.amount
)
INSERT INTO delete_lab.deleted_order_audit
    (order_id, tenant_id, customer_id, old_status, old_amount)
SELECT
    order_id, tenant_id, customer_id, status, amount
FROM removed;

SELECT order_id, tenant_id, old_status, old_amount
FROM delete_lab.deleted_order_audit
ORDER BY audit_id;

ROLLBACK;
```

Nếu transaction commit, thao tác xóa và chèn audit diễn ra cùng ranh giới giao dịch; nếu rollback, cả hai cùng được hoàn tác theo quy tắc transaction. Nhưng bảng audit này chỉ lưu **một số cột orders**, **không** sao lưu `order_items` hoặc mọi quan hệ phụ thuộc. Vì vậy audit không tự thay thế backup/archival hoàn chỉnh.

### 12.5. Lưu trước khi xóa và trách nhiệm khôi phục

Với dữ liệu quan trọng, có thể cần lưu trữ **đầy đủ** trước xóa: snapshot, bản ghi child, metadata, thời gian/actor, version schema, checksum hoặc bản sao lưu có kiểm tra khôi phục.

Không cho rằng chỉ cần `RETURNING id` là đủ để dựng lại đơn hàng, các dòng chi tiết và lịch sử xử lý. **Mức độ lưu trữ phải theo yêu cầu khôi phục thực tế**.

## 13. SELECT xem trước và DELETE có thể thấy dữ liệu khác nhau

Ở isolation mặc định **`READ COMMITTED`**, mỗi statement thường quan sát snapshot riêng. Một `SELECT` xem trước rồi `DELETE` chạy sau có thể thấy tập dữ liệu khác nếu transaction khác đã commit thay đổi.

Ví dụ:

```text
Thời điểm T1: SELECT thấy order_id 2 và 3 đủ điều kiện
Thời điểm T2: giao dịch khác đổi trạng thái order 3
Thời điểm T3: DELETE chạy với snapshot/kiểm tra mới

Kết quả xóa không nhất thiết còn đúng 2 và 3.
```

Ngoài ra, một hàng mới có thể trở thành đủ điều kiện giữa hai statement, nên `DELETE` theo **điều kiện động** có thể xóa thêm hàng không nằm trong danh sách xem trước ban đầu.

### 13.1. Khóa các hàng dự kiến bằng SELECT FOR UPDATE

Nếu muốn review những **hàng hiện có** và giữ lock trên chúng trước khi xóa trong cùng transaction:

```sql
BEGIN;

SELECT
    o.order_id,
    o.tenant_id,
    o.status,
    o.cancelled_at
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
ORDER BY o.order_id
FOR UPDATE OF o;

-- Bước tiếp theo có thể DELETE theo tập ID đã được phê duyệt.
-- Nếu chỉ thử trong lab, kết thúc:
ROLLBACK;
```

`FOR UPDATE OF o` khóa các hàng **orders** được chọn, giúp các thao tác cập nhật/xóa cạnh tranh trên những hàng đó phải phối hợp với transaction hiện tại. Nhưng:

- Nó **không tự khóa mọi hàng customers** vì `OF o` chỉ chỉ định bảng o.
- Nó **không chặn một hàng mới được chèn** vào tập phù hợp sau khi đã xem trước, trừ khi còn có cơ chế nhất quán/phạm vi khác.
- Giữ transaction/row lock lâu gây blocking và chi phí vận hành.
- Các câu xem trước và DELETE muốn ổn định theo quan hệ với customers cần tính cả thay đổi **trạng thái khách**.

Không khẳng định chỉ thêm `FOR UPDATE` là đủ cho mọi yêu cầu “xóa đúng toàn bộ snapshot và không ai thay đổi gì”.

### 13.2. Xóa theo danh sách ID đã chốt

Khi yêu cầu là **chỉ xóa những ID đã duyệt**, chuyển sang xóa theo bộ khóa cụ thể, vẫn giữ các guard quan trọng:

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE o.order_id IN (2, 3)
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND c.account_status = 'closed'
RETURNING o.order_id, o.tenant_id;

ROLLBACK;
```

Ưu điểm: không thể vô tình xóa **ID mới** ngoài danh sách 2,3 chỉ vì nó vừa trở thành đủ điều kiện. Đồng thời các guard vẫn bảo vệ trường hợp trạng thái nghiệp vụ đã đổi trước khi xóa.

Tuy nhiên nếu ID rất lớn hoặc được cung cấp từ client, cần bind parameter/bảng staging có kiểm soát và xác thực tenant. Không nối chuỗi `IN (...)` trực tiếp từ đầu vào chưa tin cậy.

### 13.3. Repeatable Read và Serializable không phải thay thế cho logic xóa

Ở `REPEATABLE READ`, các statement trong cùng transaction có snapshot nhất quán theo quy tắc PostgreSQL; cập nhật đồng thời có thể dẫn tới lỗi cần retry. `SERIALIZABLE` tăng khả năng kiểm soát tính nhất quán của kết quả giao dịch nhưng có thể trả lỗi serialization failure cần chạy lại toàn bộ transaction.

Ví dụ minh họa một transaction đọc rồi xóa theo danh sách:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT order_id
FROM delete_lab.orders
WHERE tenant_id = 10
  AND order_id IN (2, 3)
ORDER BY order_id;

DELETE FROM delete_lab.orders
WHERE tenant_id = 10
  AND order_id IN (2, 3)
RETURNING order_id;

ROLLBACK;
```

Không dùng isolation level như phép màu sửa mọi `WHERE` sai. Nó không biết mục tiêu nghiệp vụ là “xóa đơn cancelled của khách closed” nếu truy vấn không diễn đạt điều đó.

### 13.4. Mẫu xóa theo khóa đã chọn trong cùng statement

Một biến thể dùng CTE chọn ID:

```sql
BEGIN;

WITH candidates AS MATERIALIZED (
    SELECT o.order_id
    FROM delete_lab.orders AS o
    JOIN delete_lab.customers AS c
        ON c.tenant_id = o.tenant_id
       AND c.customer_id = o.customer_id
    WHERE o.tenant_id = 10
      AND o.status = 'cancelled'
      AND o.cancelled_at <
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND c.account_status = 'closed'
)
DELETE FROM delete_lab.orders AS o
USING candidates AS d
WHERE o.order_id = d.order_id
  AND o.tenant_id = 10
RETURNING o.order_id, o.tenant_id;

ROLLBACK;
```

`MATERIALIZED` ở đây nói rõ CTE được tính riêng theo khả năng hỗ trợ của PostgreSQL hiện đại; nó **không phải cơ chế phê duyệt** và cũng không tự khóa hoặc bảo đảm những điều kiện ở bảng customers không thay đổi ngoài transaction. Quan trọng hơn là tập candidate rõ và `DELETE` nối đúng khóa đích.

## 14. PostgreSQL DELETE không có LIMIT trực tiếp

Trong một số hệ SQL có thể gặp `DELETE ... LIMIT 100`, nhưng **PostgreSQL không hỗ trợ `LIMIT` trực tiếp ở cuối lệnh `DELETE`** theo cách đó.

```sql
-- Không phải cú pháp PostgreSQL:
-- DELETE FROM delete_lab.orders
-- WHERE status = 'cancelled'
-- LIMIT 100;
```

Nếu cần xóa theo đợt, hãy chọn **tập khóa** trong CTE/subquery rồi `DELETE` theo khóa đó.

### 14.1. Xóa tối đa hai đơn bằng CTE

```sql
BEGIN;

WITH batch AS MATERIALIZED (
    SELECT o.order_id
    FROM delete_lab.orders AS o
    WHERE o.tenant_id = 10
      AND o.status = 'cancelled'
    ORDER BY o.order_id
    LIMIT 2
)
DELETE FROM delete_lab.orders AS o
USING batch AS b
WHERE o.order_id = b.order_id
  AND o.tenant_id = 10
RETURNING o.order_id, o.tenant_id;

ROLLBACK;
```

Ở đây CTE chọn **tối đa hai ID**, rồi `DELETE` xóa những hàng orders có ID tương ứng. `ORDER BY` làm tập ứng viên có thể dự đoán trên dữ liệu ổn định. Nó không phải một `ORDER BY` của DELETE (PostgreSQL không hứa thứ tự trả hàng từ `DELETE RETURNING` nếu không được sắp ở truy vấn bao ngoài thích hợp).

### 14.2. Mẫu batch cho nhiều worker: FOR UPDATE SKIP LOCKED

Một tác vụ dọn dữ liệu lớn có thể chạy đồng thời ở nhiều worker. Để hạn chế tranh nhau cùng hàng:

```sql
BEGIN;

WITH batch AS MATERIALIZED (
    SELECT o.order_id
    FROM delete_lab.orders AS o
    JOIN delete_lab.customers AS c
        ON c.tenant_id = o.tenant_id
       AND c.customer_id = o.customer_id
    WHERE o.tenant_id = 10
      AND o.status = 'cancelled'
      AND o.cancelled_at <
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND c.account_status = 'closed'
    ORDER BY o.order_id
    LIMIT 100
    FOR UPDATE OF o SKIP LOCKED
)
DELETE FROM delete_lab.orders AS o
USING batch AS b
WHERE o.order_id = b.order_id
  AND o.tenant_id = 10
RETURNING o.order_id, o.tenant_id;

ROLLBACK;
```

Ở ví dụ:

- `ORDER BY o.order_id` chọn thứ tự dự kiến.
- `LIMIT 100` giới hạn số ứng viên.
- `FOR UPDATE OF o` lấy row locks trên những đơn được chọn.
- `SKIP LOCKED` bỏ qua các hàng đang bị transaction khác khóa thay vì chờ chúng.
- `DELETE ... USING batch` chỉ xóa những khóa đã chọn.

**Giới hạn của SKIP LOCKED:**

- Nó cố tình cho **góc nhìn không đầy đủ/không nhất quán** về những hàng đang bị khóa, thích hợp với job/queue chứ không phải mọi báo cáo tài chính.
- “Không còn hàng trong đợt này” chưa chứng minh **không còn hàng đủ điều kiện** nếu có hàng bị khóa hoặc giao dịch khác đang thay đổi dữ liệu.
- Các worker cần cơ chế retry, lịch quét lại, kiểm soát stop condition và giám sát tiến độ.
- Khi giữ `FOR UPDATE OF o`, khách hàng trong bảng `c` không tự bị khóa; nếu trạng thái khách có thể đổi, cần cân nhắc thêm guard/quy trình phù hợp.
- Bản thân việc chọn và xóa theo lô có thể gây deadlock trong workload phức tạp; thứ tự khóa, FK và trigger vẫn quan trọng.

### 14.3. Batch không phải lúc nào cũng cần

Xóa 50 hàng trong bảng nhỏ có thể đơn giản hơn bằng một statement. Chia batch hữu ích khi:

- Khối lượng xóa rất lớn.
- Muốn giới hạn thời gian giữ lock mỗi transaction.
- Muốn chia hoạt động thành các đợt có khả năng dừng/tiếp tục.
- Cần giảm áp lực WAL, autovacuum, replica lag hoặc transaction log.

Nhưng nhiều batch vẫn tạo tổng tải I/O và có thể làm việc lâu hơn, đồng thời dữ liệu có thể thay đổi giữa các batch. Chọn kích thước sau khi đo tải thực và hiểu yêu cầu nhất quán.

## 15. Row-Level Security và quyền DELETE

Một ứng dụng multi-tenant nên có chính sách phân quyền ở nhiều tầng.

### 15.1. DELETE cần quyền tương ứng

Để thực hiện `DELETE`, role cần quyền `DELETE` trên bảng đích. Các cột được đọc trong điều kiện `WHERE`/`USING` và `RETURNING` có thể yêu cầu quyền `SELECT` tương ứng theo quy tắc PostgreSQL.

Không nên cấp `DELETE` không giới hạn cho mọi tài khoản ứng dụng rồi trông chờ developer luôn nhớ điều kiện tenant. Cân nhắc role tách biệt cho nghiệp vụ dọn dữ liệu.

### 15.2. Row-Level Security (RLS)

PostgreSQL có **RLS** cho phép giới hạn hàng một role được phép thao tác. Với `DELETE`, policy phù hợp có thể hạn chế những hàng được xóa theo biểu thức `USING` của policy.

Ý tưởng ở mức cấu trúc:

```sql
-- Cú pháp minh họa cho mô hình phân quyền được thiết kế đầy đủ:
-- ALTER TABLE delete_lab.orders ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY orders_delete_policy
-- ON delete_lab.orders
-- FOR DELETE
-- TO application_role
-- USING (tenant_id = current_setting('app.tenant_id')::integer);
```

**Không chạy nguyên ví dụ này trong lab:** role `application_role` và cơ chế thiết lập `app.tenant_id` cần được định nghĩa, bảo vệ và kiểm thử riêng. Một custom GUC tùy ý đặt được bởi client **không tự trở thành cơ chế xác thực tin cậy**; cần một đường gán tenant được ủy quyền thích hợp.

RLS có sắc thái về table owner, role `BYPASSRLS`, policies và quyền đọc. Không khẳng định tất cả người dùng bị RLS theo cách giống nhau nếu chưa kiểm tra cấu hình và role.

### 15.3. RLS không thay bộ lọc nghiệp vụ

RLS có thể hạn chế hàng **được phép xóa**, nhưng không tự biết “chỉ xóa đơn đã hủy trước cutoff của khách đã đóng tài khoản”. Các điều kiện nghiệp vụ vẫn phải nằm trong `WHERE`/`USING` phù hợp.

Ngược lại, bộ lọc tenant ở application không thay một mô hình phân quyền có trách nhiệm. Đây là **hai hàng rào bổ sung**, không phải thay thế nhau.

## 16. Khóa ngoại, ON DELETE CASCADE và trigger

### 16.1. Các kiểu hành vi FK khi xóa hàng cha

Giả sử một bảng `orders` có bảng `order_items` tham chiếu:

| Cấu hình FK từ bảng con | Hành vi khái quát khi xóa hàng cha |
|---|---|
| `ON DELETE CASCADE` | Các hàng con tham chiếu bị xóa theo |
| `ON DELETE RESTRICT` | Cấm xóa cha nếu còn hàng con tham chiếu |
| `ON DELETE NO ACTION` (mặc định) | Vi phạm FK nếu kết quả không còn hợp lệ ở thời điểm kiểm tra; có thể liên quan deferred constraint |
| `ON DELETE SET NULL` | Cột FK của hàng con được đặt NULL nếu cho phép và cấu hình phù hợp |
| `ON DELETE SET DEFAULT` | Cột FK của hàng con được đặt giá trị mặc định; vẫn phải thỏa FK |

Không thể chỉ nhìn `DELETE ... RETURNING` của bảng cha để khẳng định toàn bộ số hàng bị thay đổi trong database.

### 16.2. Ảnh hưởng cascade trong lab

Hai đơn 2 và 3 có các dòng item:

```sql
SELECT
    order_id,
    COUNT(*) AS item_rows
FROM delete_lab.order_items
WHERE order_id IN (2, 3)
GROUP BY order_id
ORDER BY order_id;
```

Kết quả:

| order_id | item_rows |
|---:|---:|
| 2 | 2 |
| 3 | 1 |

Nếu xóa đơn 2,3 và commit, **ba hàng item** cũng bị xóa do `ON DELETE CASCADE`. Bảng `order_flags` có các hàng thuộc hai đơn đó cũng bị cascade.

Vì vậy, không nên báo tác động là “xóa 2 hàng toàn hệ thống”; phải phân biệt **2 hàng orders trực tiếp** và các hàng con bị tác động.

### 16.3. Trigger có thể tác động đến quy trình xóa

Trigger `BEFORE DELETE`, `AFTER DELETE` hoặc cơ chế ứng dụng có thể:

- Ghi log.
- Từ chối thao tác trong một số điều kiện.
- Đồng bộ trạng thái hoặc ghi bản ghi liên quan.
- Ảnh hưởng kết quả tác động nếu trigger chặn việc xóa một hàng.

Trước một job xóa lớn, cần kiểm tra schema và dependency đang triển khai; không đánh giá ảnh hưởng chỉ từ câu SQL `DELETE`.

### 16.4. Quyền xóa và ngữ nghĩa audit

Nếu audit được viết bởi trigger, hãy xác định nó chạy **trong transaction nào**, có dùng external side effect không và dữ liệu audit có tồn tại nếu statement rollback hay không. Hoạt động ngoài database (ví dụ thông báo gửi qua hệ thống khác) **không nhất thiết rollback** cùng database; không phát sự kiện “đã xóa thành công” trước khi commit theo cách có thể tạo sự kiện giả.

Với hệ thống tích hợp, có thể cần pattern **transactional outbox** để bảo đảm sự kiện và thao tác xóa có quan hệ nhất quán.

## 17. EXPLAIN, chỉ mục và chi phí xóa

### 17.1. Những cột có thể cần index

Đối với truy vấn ví dụ:

```sql
DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed';
```

có thể xem xét một index phục vụ lọc theo tenant, trạng thái và thời gian:

```sql
CREATE INDEX orders_purge_candidate_idx
ON delete_lab.orders
    (tenant_id, status, cancelled_at, customer_id);
```

Khóa chính của `customers` trên `(tenant_id, customer_id)` đã cung cấp index phục vụ lookup theo khóa ghép. Tuy nhiên, index tối ưu còn phụ thuộc cardinality, tính chọn lọc của `account_status` và cách planner quyết định thứ tự JOIN.

### 17.2. Partial index nếu chỉ dọn cancelled

Nếu khối lượng bảng lớn và job chỉ xử lý `status='cancelled'`:

```sql
CREATE INDEX orders_cancelled_purge_idx
ON delete_lab.orders (tenant_id, cancelled_at, customer_id)
WHERE status = 'cancelled';
```

Index này chỉ lưu những hàng thỏa predicate tại thời điểm cập nhật index; có thể tiết kiệm dung lượng so với index tất cả trạng thái. Nhưng nó cũng tăng chi phí ghi và **không tự bảo đảm** planner sẽ dùng cho mọi truy vấn.

Hai index ở ví dụ phục vụ mục đích gần nhau; trên production không tạo cả hai chỉ vì tài liệu liệt kê, mà cần đo workload và tránh index dư.

### 17.3. Chỉ mục trên khóa ngoại của bảng con

`order_items.order_id` và `order_flags.order_id` được dùng khi thực hiện cascade. `order_flags` có primary key `(order_id, flag)` nên index bắt đầu bằng `order_id`. Còn `order_items` chỉ có PK trên `item_id`, nên có thể xem xét:

```sql
CREATE INDEX order_items_order_id_idx
ON delete_lab.order_items (order_id);
```

PostgreSQL không tự tạo index trên **mọi cột tham chiếu FK** ở bảng con. Khi xóa hoặc cập nhật khóa của nhiều hàng cha, việc tìm hàng con có thể tốn chi phí nếu thiếu index phù hợp.

### 17.4. EXPLAIN SELECT trước DELETE

```sql
EXPLAIN
SELECT o.order_id
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed';
```

Đây là cách ít rủi ro để tìm hiểu **mẫu truy vấn chọn ứng viên**, nhưng không cho thấy toàn bộ chi phí xóa vật lý, kiểm tra FK, cascade, trigger và WAL.

### 17.5. EXPLAIN trên DELETE không có ANALYZE

```sql
EXPLAIN
DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed';
```

`EXPLAIN` **không có `ANALYZE`** mô tả kế hoạch ước lượng mà không thực thi lệnh xóa. Nó có thể hiển thị node `Delete on ...` và cách xác định hàng mục tiêu.

**Không chạy `EXPLAIN (ANALYZE, BUFFERS) DELETE ...` một cách vô ý trên production**: `ANALYZE` thực thi lệnh, có thể xóa dữ liệu thật. Trong một lab hoặc môi trường có kiểm soát, nếu phải đo thật, có thể dùng transaction và rollback, đồng thời hiểu các side effect ngoài database có thể không được hoàn tác cùng rollback.

### 17.6. Xóa nhiều không đồng nghĩa giải phóng dung lượng tức thì

PostgreSQL sử dụng MVCC. Sau `DELETE`, dữ liệu cũ có thể còn nằm trong các trang bảng để những snapshot cũ truy cập; autovacuum/VACUUM sẽ tái sử dụng không gian khi có thể.

Không mong file bảng giảm ngay sau khi xóa. Một số thao tác thu hồi dung lượng như `VACUUM FULL` có chi phí và yêu cầu khóa mạnh; đừng chạy tùy tiện chỉ vì vừa thực hiện một job purge.

### 17.7. WAL, replica và batch

Một lệnh xóa lớn có thể tạo nhiều WAL, ảnh hưởng replication lag, autovacuum, index maintenance và giao dịch khác. Chia batch có thể giúp kiểm soát thời gian giữ lock và khả năng tiến hành theo tiến độ, nhưng không làm tổng chi phí biến mất.

Với hệ thống có replica, cần giám sát tốc độ áp dụng WAL và trạng thái đọc sau xóa; không coi việc query trên replica trễ là bằng chứng primary chưa xóa.

## 18. Partitioning và phạm vi xóa

Trong bảng partitioned, `DELETE FROM partitioned_parent WHERE ...` có thể tác động tới những partition chứa hàng phù hợp theo điều kiện và khả năng partition pruning.

Nếu dữ liệu được phân vùng theo ngày/tháng, một bộ lọc đúng theo partition key có thể giảm lượng partition phải quét. Nhưng:

- `DELETE` vẫn là thao tác theo hàng, khác với việc tháo/dọn cả partition.
- Cascade, trigger, FK và quyền vẫn phải xét.
- `TRUNCATE`/`DETACH PARTITION` không thay cho `DELETE USING` khi yêu cầu xóa chỉ một phần hàng trong partition hoặc cần audit từng hàng.
- Một partition có thể chứa dữ liệu của nhiều tenant; xóa cả partition chỉ vì một tenant hết hạn là sai.

Khi nhu cầu là xóa **toàn bộ dữ liệu của một khoảng thời gian** theo partition, quản lý vòng đời partition có thể là chiến lược khác phù hợp hơn, nhưng phải đánh giá ranh giới dữ liệu và dependency trước.

## 19. DELETE hay TRUNCATE?

### 19.1. TRUNCATE khác về cơ chế

`TRUNCATE` có thể làm rỗng bảng hiệu quả trong tình huống dọn toàn bộ, nhưng:

- Không có `WHERE` để xóa một tenant hoặc một trạng thái.
- Có quy tắc khóa mạnh và xử lý FK/`CASCADE` khác `DELETE`.
- Không kích hoạt các **row-level DELETE triggers** như `DELETE`; có cơ chế trigger dành riêng cho `TRUNCATE`.
- Có ngữ nghĩa MVCC khác biệt; cần kiểm tra phù hợp nếu có transaction đồng thời và snapshot cũ.

Trong PostgreSQL, `TRUNCATE` có thể được rollback khi thực hiện trong transaction theo quy tắc của hệ, nhưng **không vì thế mà an toàn hơn `DELETE`** cho yêu cầu xóa chọn lọc.

### 19.2. Quy tắc chọn

| Yêu cầu | Lựa chọn thường phù hợp |
|---|---|
| Xóa đơn theo tenant + trạng thái + cutoff | `DELETE WHERE` hoặc `DELETE USING` |
| Xóa nếu có/không có bản ghi đối chiếu | `DELETE USING`, `EXISTS`, `NOT EXISTS` |
| Dọn hàng loạt theo batch và ID | CTE candidate + `DELETE USING` |
| Làm rỗng toàn bộ bảng staging dùng riêng | Cân nhắc `TRUNCATE` với khóa/FK/trigger phù hợp |
| Giữ hàng nhưng ẩn khỏi người dùng | `UPDATE deleted_at` / soft delete |
| Loại bỏ dữ liệu theo partition trọn vẹn | Xem vòng đời partition, không dùng thay cho xóa chọn lọc |

Không áp một công cụ cho mọi loại yêu cầu.

## 20. Tự xóa dựa vào các hàng khác trong cùng bảng

Đôi khi muốn xóa những bản ghi bị coi là trùng phiên bản hoặc bản ghi cũ hơn theo một khóa.

### 20.1. Self-join trong USING cần alias riêng

Ví dụ với một bảng giả định `dedupe_events`:

```sql
-- Minh họa cấu trúc; các bảng thực hành ở dưới sẽ được tạo riêng.
-- DELETE FROM dedupe_events AS old
-- USING dedupe_events AS newer
-- WHERE old.tenant_id = newer.tenant_id
--   AND old.business_key = newer.business_key
--   AND old.version_no < newer.version_no;
```

Một bảng được đưa vào statement ở **hai vai trò**: hàng `old` là **đích xóa**, còn `newer` là **hàng để đối chiếu**. Hai alias phải khác nhau.

### 20.2. Dữ liệu minh họa

```sql
CREATE TABLE delete_lab.event_versions (
    event_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    business_key TEXT NOT NULL,
    version_no INTEGER NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE (tenant_id, business_key, version_no)
);

INSERT INTO delete_lab.event_versions
    (event_id, tenant_id, business_key, version_no, payload)
VALUES
    (100, 10, 'A', 1, 'A v1'),
    (101, 10, 'A', 2, 'A v2'),
    (102, 10, 'A', 3, 'A v3'),
    (103, 10, 'B', 1, 'B v1'),
    (104, 20, 'A', 1, 'Tenant 20 A v1'),
    (105, 20, 'A', 2, 'Tenant 20 A v2');
```

Yêu cầu: **tenant 10**, với mỗi `business_key` chỉ giữ phiên bản `version_no` lớn nhất.

Xem trước:

```sql
SELECT DISTINCT
    old.event_id,
    old.business_key,
    old.version_no
FROM delete_lab.event_versions AS old
JOIN delete_lab.event_versions AS newer
    ON newer.tenant_id = old.tenant_id
   AND newer.business_key = old.business_key
   AND newer.version_no > old.version_no
WHERE old.tenant_id = 10
ORDER BY old.business_key, old.version_no;
```

Kết quả là event 100 và 101; event 102 là phiên bản mới nhất, còn event 103 không có phiên bản mới hơn.

Thử xóa:

```sql
BEGIN;

DELETE FROM delete_lab.event_versions AS old
USING delete_lab.event_versions AS newer
WHERE old.tenant_id = 10
  AND newer.tenant_id = old.tenant_id
  AND newer.business_key = old.business_key
  AND newer.version_no > old.version_no
RETURNING old.event_id, old.tenant_id,
          old.business_key, old.version_no;

ROLLBACK;
```

**Quan trọng:** Một hàng old có thể khớp nhiều newer; nó vẫn chỉ bị xóa một lần. Để không xóa hàng sai, cần hiểu **version_no** có thực sự xác định “mới nhất” theo nghiệp vụ hay không. Nếu nhiều bản ghi cùng version nhưng khác nội dung được phép, cần quy tắc tie-breaker/khóa rõ ràng.

### 20.3. Dùng ROW_NUMBER cho dedup theo quy tắc khác

Khi cần giữ “một hàng mới nhất theo timestamp và event_id”:

```sql
-- Cấu trúc minh họa, có thể áp dụng nếu bảng thực có event_time.
-- WITH ranked AS (
--   SELECT event_id,
--          ROW_NUMBER() OVER (
--            PARTITION BY tenant_id, business_key
--            ORDER BY event_time DESC, event_id DESC
--          ) AS rn
--   FROM event_table
--   WHERE tenant_id = 10
-- )
-- DELETE FROM event_table AS e
-- USING ranked AS r
-- WHERE e.event_id = r.event_id
--   AND e.tenant_id = 10
--   AND r.rn > 1;
```

Nên dùng khóa phân định duy nhất trong `ORDER BY` của `ROW_NUMBER` để việc chọn hàng giữ lại không tùy thuộc thứ tự bất định giữa những timestamp bằng nhau.

Không xóa trùng trên production nếu chưa xét các FK, event history và ý nghĩa của bản ghi.

## 21. Xóa theo quan hệ nhiều bảng

`USING` có thể đưa nhiều nguồn vào, nhưng mỗi nguồn bổ sung đều tăng rủi ro thiếu điều kiện nối.

Ví dụ mục tiêu: xóa đơn của tenant 10 nếu khách đã đóng và đơn có cờ `expired`:

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
USING
    delete_lab.customers AS c,
    delete_lab.order_flags AS f
WHERE o.tenant_id = 10
  AND c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND c.account_status = 'closed'
  AND f.order_id = o.order_id
  AND f.flag = 'expired'
  AND o.status = 'cancelled'
RETURNING o.order_id;

ROLLBACK;
```

Điều kiện nối gồm **cặp tenant/customer** và **order_id/flag**. Nếu bỏ `f.order_id = o.order_id`, chỉ cần tồn tại một cờ expired ở đâu đó là các đơn khác có thể khớp theo Cartesian product.

### 21.1. Đối chiếu nhiều bảng không đồng nghĩa xóa nhiều bảng

Statement trên chỉ chỉ định bảng **orders** làm target. Các bảng `customers` và `order_flags` là nguồn tra điều kiện; `order_flags` còn bị cascade khi hàng orders cha bị xóa.

Nếu nghiệp vụ muốn xóa trực tiếp dữ liệu ở hai bảng khác nhau **không có FK CASCADE**, thường cần các statement riêng trong một transaction theo thứ tự phụ thuộc, hoặc một thiết kế lưu trữ khác. Không suy ra `USING a,b` sẽ xóa cả a lẫn b.

### 21.2. Subquery trong USING

`USING` cũng có thể nhận một derived table để rút gọn logic:

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
USING (
    SELECT tenant_id, customer_id
    FROM delete_lab.customers
    WHERE tenant_id = 10
      AND account_status = 'closed'
) AS closed_customers
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND closed_customers.tenant_id = o.tenant_id
  AND closed_customers.customer_id = o.customer_id
RETURNING o.order_id;

ROLLBACK;
```

Derived table giúp đọc rõ tập đối chiếu, nhưng **không** có nghĩa PostgreSQL bắt buộc chạy subquery trước rồi mới chạy DELETE theo thứ tự vật lý như một chương trình thủ tục. Hãy dựa trên ngữ nghĩa kết quả và kế hoạch thực thi thực tế, không trên cảm giác về thứ tự viết SQL.

## 22. Xử lý lỗi và kết quả trong Java/JDBC

Trong ứng dụng Java, tránh nối thẳng các tham số tenant, status và cutoff vào SQL. Dùng `PreparedStatement` để bind giá trị.

### 22.1. Ví dụ DELETE USING có RETURNING

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public final class OrderCleanupRepository {
    public List<Long> deleteEligibleOrders(
            Connection connection,
            int tenantId,
            OffsetDateTime cutoff
    ) throws SQLException {
        if (cutoff == null) {
            throw new IllegalArgumentException("cutoff is required");
        }

        String sql = """
            DELETE FROM delete_lab.orders AS o
            USING delete_lab.customers AS c
            WHERE c.tenant_id = o.tenant_id
              AND c.customer_id = o.customer_id
              AND o.tenant_id = ?
              AND o.status = 'cancelled'
              AND o.cancelled_at < CAST(? AS timestamptz)
              AND c.account_status = 'closed'
            RETURNING o.order_id
            """;

        List<Long> ids = new ArrayList<>();
        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setInt(1, tenantId);
            ps.setObject(2, cutoff);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    ids.add(rs.getLong("order_id"));
                }
            }
        }
        return ids;
    }
}
```

Ví dụ sử dụng Java text block (Java 15+) và driver JDBC hỗ trợ `OffsetDateTime`. Phương thức này **thực sự xóa** dữ liệu; nó không có chế độ “xem trước” chỉ vì kết quả được trả trong một danh sách ID. Ứng dụng production cần đặt thao tác này trong luồng phê duyệt, transaction và logging phù hợp.

### 22.2. Commit, rollback và ngoại lệ

Ví dụ khung transaction ở phía service:

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;

public final class OrderCleanupService {
    private final OrderCleanupRepository repository =
        new OrderCleanupRepository();

    public List<Long> run(
            Connection connection,
            int tenantId,
            OffsetDateTime cutoff
    ) throws SQLException {
        boolean oldAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);
        try {
            List<Long> ids =
                repository.deleteEligibleOrders(
                    connection, tenantId, cutoff
                );

            // Ở production: kiểm tra giới hạn số hàng,
            // ghi audit/outbox và các guard bổ sung trước commit.
            if (ids.size() > 1000) {
                throw new IllegalStateException(
                    "Số hàng vượt ngưỡng cho phép"
                );
            }

            connection.commit();
            return ids;
        } catch (SQLException | RuntimeException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }
            throw e;
        } finally {
            connection.setAutoCommit(oldAutoCommit);
        }
    }
}
```

**Giới hạn mẫu code:** Đối với connection lấy từ pool/framework, thông thường transaction do tầng quản lý giao dịch sở hữu. Không tự điều khiển `autoCommit`/`commit` nếu framework đã có transaction manager. Mẫu trên chỉ minh họa nguyên tắc rollback và kiểm tra kết quả **trước commit**; việc đổi trạng thái connection trong `finally` cũng cần chính sách trả pool/xử lý lỗi phù hợp ở hệ thống thật.

### 22.3. Phân biệt lỗi khóa ngoại và lỗi exclusion

Một lệnh xóa có thể thất bại do:

- `23503` — `foreign_key_violation`: bảng con có FK hạn chế xóa.
- `42501` — `insufficient_privilege`: role không đủ quyền.
- `40001` — `serialization_failure`: giao dịch tại isolation phù hợp cần retry.
- `40P01` — `deadlock_detected`: deadlock, thường cần retry cả transaction theo chính sách an toàn.

Đừng xử lý mọi lỗi bằng “không tìm thấy đơn” hoặc “không có hàng để xóa”. `DELETE 0` có thể là không có ứng viên hợp lệ; exception là một trạng thái khác.

## 23. Giám sát một job xóa định kỳ

Một tác vụ dọn dữ liệu tin cậy thường có ít nhất những thông tin:

| Trường | Ý nghĩa |
|---|---|
| `job_id` | Định danh lượt xử lý |
| `tenant_id` | Phạm vi tenant |
| `cutoff` | Ranh giới thời gian cố định cho lượt |
| `filter_version` | Phiên bản quy tắc xóa |
| `candidate_count` | Số ứng viên trước khi xóa |
| `deleted_count` | Số hàng target thực sự đã xóa |
| `deleted_ids` hoặc checksum/bản audit | Bằng chứng đối chiếu |
| `started_at` / `finished_at` | Thời điểm chạy |
| `transaction_status` | Commit, rollback, failed |
| `dependent_changes` | Ảnh hưởng phụ thuộc được đo/ghi nhận nếu cần |

### 23.1. Đặt ngưỡng an toàn

Ví dụ:

- Mỗi batch không quá 100 hoặc 1000 bản ghi tùy workload.
- Không xóa nếu `candidate_count` vượt ngưỡng dự kiến.
- Chỉ xử lý tenant đã được cho phép.
- Không chạy khi hệ thống ở trạng thái incident/backup chưa sẵn sàng.
- Dừng và cảnh báo nếu số hàng xóa tăng đột biến.

Đây là **biện pháp vận hành**, không phải tính năng tự có của `DELETE USING`. Cần đưa vào application job, transaction orchestration và giám sát thực tế.

### 23.2. Xóa từ nhiều worker cần idempotency của job

Nếu một batch đã commit nhưng worker mất kết nối trước khi nhận kết quả, retry có thể thấy **0 hàng** vì các hàng đã bị xóa. Điều đó không nhất thiết là lỗi nếu job được thiết kế **có thể thực thi lại an toàn**.

Tuy nhiên, retry không được dùng một cutoff động hoặc bộ lọc mới ngoài ý muốn rồi xóa thêm dữ liệu khác. Có thể lưu **cutoff và job scope cố định**, đánh dấu batch hoàn thành, và đối chiếu audit theo cơ chế phù hợp.

### 23.3. Backup cần được thử khôi phục

Việc “có file backup” không tự đảm bảo có thể khôi phục:

- Backup có bao phủ các bảng và thời điểm cần không?
- Có WAL/point-in-time recovery nếu yêu cầu không?
- Có đủ khóa mã hóa và quyền?
- Đã thử restore với schema/extension/version tương ứng chưa?
- Có yêu cầu không được phục hồi dữ liệu đã yêu cầu xóa vĩnh viễn không?

Không xử lý những câu hỏi này ở câu SQL `DELETE`, nhưng chúng là một phần không thể bỏ qua của quy trình xóa dữ liệu nhạy cảm hoặc quan trọng.

## 24. Những sai lầm thường gặp

**1. “USING có nghĩa xóa cả hai bảng.”** Sai. Chỉ bảng sau `DELETE FROM` là target trực tiếp; tác động phụ thuộc có thể xảy ra qua FK/trigger.

**2. “DELETE USING mà không có WHERE vẫn an toàn vì đã có bảng đối chiếu.”** Sai. Thiếu điều kiện nối/lọc có thể làm phạm vi thành Cartesian product và xóa nhiều hàng.

**3. “Có tenant_id ở bảng customers là đủ.”** Sai nếu JOIN không ràng buộc tenant của orders hoặc không có giới hạn tenant đúng.

**4. “Customer_id luôn là khóa toàn cục.”** Không nếu schema định nghĩa khóa ghép `(tenant_id, customer_id)`.

**5. “Nếu SELECT JOIN ra 3 dòng thì DELETE phải xóa 3 hàng.”** Sai khi một hàng target khớp nhiều dòng USING.

**6. “RETURNING trả một dòng cho mỗi dòng USING khớp.”** Sai. Nó phản ánh mỗi hàng target đã bị xóa.

**7. “COUNT(DISTINCT order_id) trong SELECT cũng đếm các hàng con bị CASCADE.”** Sai. Đó là số order ID khác nhau.

**8. “Chỉ chạy SELECT rồi DELETE là đủ chống thay đổi đồng thời.”** Không. Snapshot có thể đổi giữa statement.

**9. “BEGIN giúp tự đóng băng toàn bộ dữ liệu ngay cả ở READ COMMITTED.”** Không. Mỗi statement vẫn có thể có snapshot mới.

**10. “FOR UPDATE OF orders khóa luôn mọi bảng USING.”** Không. `OF` giới hạn những bảng được khóa theo cấu trúc statement.

**11. “SKIP LOCKED đảm bảo đợt này đã xem hết mọi ứng viên.”** Không. Nó có thể bỏ qua hàng đang bị khóa.

**12. “DELETE ... LIMIT 100 là cú pháp PostgreSQL.”** Không. Chọn candidate keys bằng CTE rồi xóa theo khóa.

**13. “Có ORDER BY trong CTE thì DELETE RETURNING tự có thứ tự.”** Không được bảo đảm. Nếu muốn trình bày có thứ tự, sắp kết quả ở tầng trả dữ liệu thích hợp.

**14. “ON DELETE CASCADE không làm thay đổi phạm vi tác động.”** Sai. Nó có thể xóa các hàng tham chiếu trong bảng con.

**15. “TRUNCATE giống DELETE không WHERE.”** Không. Khóa, trigger, FK, MVCC và cơ chế thao tác khác.

**16. “DELETE giải phóng ngay dung lượng file bảng.”** Không. PostgreSQL MVCC cần VACUUM/duy trì phù hợp.

**17. “EXPLAIN ANALYZE DELETE không xóa thật.”** Sai. `ANALYZE` thực thi statement.

**18. “Dùng SELECT DISTINCT sau JOIN có thể cứu mọi phép tính tác động.”** Không. Nó chỉ đổi tập hàng SELECT, không sửa bộ lọc xóa sai.

**19. “Lệnh DELETE trả 0 hàng nghĩa là chắc chắn không có dữ liệu phù hợp.”** Không nếu RLS/role, lock/batch, điều kiện hay snapshot đã thay đổi; cần biết bối cảnh.

**20. “Cứ dùng OR mà không cần ngoặc vì tenant đã ở đầu WHERE.”** Sai. `AND` và `OR` có ưu tiên khác nhau.

**21. “WHERE status <> 'paid' tự bao gồm NULL.”** Không; so sánh với NULL có unknown nếu cột nullable.

**22. “Có thể rollback sau COMMIT để phục hồi.”** Không. Phải dùng kế hoạch khôi phục trước đó.

**23. “Audit vài cột là backup đầy đủ.”** Không nếu bảng con, metadata hoặc dữ liệu lịch sử cũng cần khôi phục.

**24. “Xóa theo created_at tương đương xóa theo cancelled_at.”** Không. Hai sự kiện có thể cách nhau rất xa.

**25. “RLS tự làm đúng mọi quy tắc nghiệp vụ.”** Không. Quy tắc eligibility và policy quyền là hai lớp riêng.

**26. “Thêm nhiều index sẽ luôn giúp DELETE nhanh hơn.”** Không. Index tăng chi phí duy trì khi ghi và có thể dư.

**27. “Xóa từ bảng cha không ảnh hưởng tốc độ nếu bảng con lớn.”** Không. Truy vấn FK/cascade có thể cần index ở phía bảng con.

**28. “Dùng WHERE IN (2,3) là đủ dù API còn phải giới hạn tenant.”** Không. Vẫn cần tenant/authorization guards.

**29. “DELETE USING là cách viết duy nhất cho điều kiện tồn tại.”** Không. `EXISTS` thường rõ và phù hợp.

**30. “NOT EXISTS có thể viết tương đương bằng USING inner join với bảng không có hàng.”** Không. Anti-existence cần logic phủ định phù hợp.

## 25. Bài tập thực hành có hướng dẫn đáp án

### Bài 1 — Đọc yêu cầu thành điều kiện

**Yêu cầu:** xóa các đơn thuộc tenant 10, đã hủy trước ngày 01/10/2026 (+07), khách trong cùng tenant đã đóng tài khoản.

**Đáp án:** các điều kiện chính gồm:

```sql
o.tenant_id = 10
AND o.status = 'cancelled'
AND o.cancelled_at <
    TIMESTAMPTZ '2026-10-01 00:00:00+07'
AND c.tenant_id = o.tenant_id
AND c.customer_id = o.customer_id
AND c.account_status = 'closed'
```

Với dữ liệu ban đầu, chỉ đơn **2 và 3** đủ điều kiện.

### Bài 2 — Xem trước danh sách

**Yêu cầu:** chọn ID và customer name trước khi xóa.

**Đáp án:**

```sql
SELECT o.order_id, c.customer_name
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
ORDER BY o.order_id;
```

### Bài 3 — Viết DELETE USING

**Yêu cầu:** xóa đúng phạm vi của bài 2 và trả ID.

**Đáp án (chỉ chạy trong transaction lab):**

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
RETURNING o.order_id;

ROLLBACK;
```

### Bài 4 — Phát hiện thiếu khóa tenant

**Tình huống:** bảng customers có khách 101 ở tenant 10 (active) và tenant 20 (closed). JOIN chỉ bằng customer_id.

**Đáp án:** đơn tenant 10 của khách 101 có thể khớp trạng thái closed từ tenant 20. Phải nối thêm:

```sql
AND c.tenant_id = o.tenant_id
```

và đảm bảo phạm vi đích bằng `o.tenant_id=10`.

### Bài 5 — Fanout

**Câu hỏi:** đơn 2 có hai cờ `expired` và `reviewed`. Khi `USING order_flags` lọc cả hai cờ, `RETURNING order_id` cho đơn 2 mấy lần?

**Đáp án:** **Một lần**, vì hàng đích chỉ bị xóa một lần, dù join có hai hàng.

### Bài 6 — COUNT(*) có đúng số đơn dự kiến không?

**Đáp án:** Không nếu bảng USING có nhiều hàng khớp một đơn. Dùng:

```sql
SELECT COUNT(DISTINCT o.order_id)
FROM delete_lab.orders AS o
JOIN delete_lab.order_flags AS f
    ON f.order_id = o.order_id
WHERE o.tenant_id = 10
  AND f.flag IN ('expired', 'reviewed');
```

### Bài 7 — Viết WHERE EXISTS

**Yêu cầu:** xóa đơn cancelled cũ của tenant 10 nếu có customer closed cùng tenant.

**Đáp án:**

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND EXISTS (
      SELECT 1
      FROM delete_lab.customers AS c
      WHERE c.tenant_id = o.tenant_id
        AND c.customer_id = o.customer_id
        AND c.account_status = 'closed'
  )
RETURNING o.order_id;

ROLLBACK;
```

### Bài 8 — Anti-join NOT EXISTS

**Yêu cầu:** xóa hàng staging tenant 10 không có mã trong bảng valid codes tương ứng tenant.

**Đáp án:**

```sql
BEGIN;

DELETE FROM delete_lab.import_candidates AS i
WHERE i.tenant_id = 10
  AND NOT EXISTS (
      SELECT 1
      FROM delete_lab.valid_external_codes AS v
      WHERE v.tenant_id = i.tenant_id
        AND v.external_code = i.external_code
  )
RETURNING i.external_code;

ROLLBACK;
```

Kết quả chỉ `X-99`.

### Bài 9 — Nhìn lỗi AND/OR

**Câu hỏi:** điều kiện `tenant_id = 10 AND status = 'pending' OR status = 'cancelled'` có xóa cancelled của tenant 20 không?

**Đáp án:** **Có thể có**, vì vế `OR status = 'cancelled'` không bị ràng buộc tenant. Sửa thành:

```sql
tenant_id = 10
AND status IN ('pending', 'cancelled')
```

### Bài 10 — Dọn 100 hàng

**Yêu cầu:** PostgreSQL không có `DELETE LIMIT`. Hãy dùng CTE để chọn tối đa 100 hàng.

**Đáp án:**

```sql
BEGIN;

WITH batch AS (
    SELECT order_id
    FROM delete_lab.orders
    WHERE tenant_id = 10
      AND status = 'cancelled'
    ORDER BY order_id
    LIMIT 100
)
DELETE FROM delete_lab.orders AS o
USING batch AS b
WHERE o.order_id = b.order_id
  AND o.tenant_id = 10
RETURNING o.order_id;

ROLLBACK;
```

Khi nhiều worker chạy đồng thời, cân nhắc `FOR UPDATE SKIP LOCKED` và cơ chế retry.

### Bài 11 — Cascade tác động bao nhiêu hàng?

**Câu hỏi:** xóa đơn 2 và 3 trong lab có `ON DELETE CASCADE` ở `order_items`. Nếu hai đơn có lần lượt 2 và 1 dòng item, `DELETE orders RETURNING` trả bao nhiêu dòng? Bao nhiêu dòng item có thể bị xóa theo cascade?

**Đáp án:** **2** dòng orders trong `RETURNING`; **3** dòng item bị xóa theo cascade. Bảng order_flags còn có các dòng phụ thuộc có thể bị cascade tương ứng.

### Bài 12 — DELETE RETURNING và audit

**Yêu cầu:** lấy số hàng xóa và danh sách ID theo cùng statement.

**Đáp án:**

```sql
BEGIN;

WITH removed AS (
    DELETE FROM delete_lab.orders AS o
    WHERE o.tenant_id = 10
      AND o.order_id IN (2, 3)
    RETURNING o.order_id
)
SELECT
    COUNT(*) AS deleted_count,
    ARRAY_AGG(order_id ORDER BY order_id) AS deleted_ids
FROM removed;

ROLLBACK;
```

Kết quả `deleted_count=2` và `deleted_ids={2,3}` khi dữ liệu còn nguyên. Nếu không có hàng, `COUNT(*)=0` và `ARRAY_AGG` sẽ là NULL trừ khi được `COALESCE`.

### Bài 13 — SELECT trước DELETE có tuyệt đối an toàn không?

**Đáp án:** Không. Có thể có transaction khác commit giữa hai statement. Cân nhắc khóa hàng mục tiêu, chốt danh sách ID, giữ guard trong DELETE, isolation phù hợp và transaction có kiểm soát. Việc chỉ bọc `BEGIN` trong `READ COMMITTED` không tự đóng băng snapshot.

### Bài 14 — EXPLAIN ANALYZE

**Câu hỏi:** Lệnh `EXPLAIN (ANALYZE) DELETE FROM orders ...` có xóa dữ liệu thật không?

**Đáp án:** **Có**, vì `ANALYZE` thực thi câu lệnh. Để chỉ xem kế hoạch dự kiến, dùng `EXPLAIN DELETE ...` không kèm `ANALYZE`. Nếu cần đo thật trong lab, dùng transaction/rollback và hiểu các side effect ngoài transaction.

### Bài 15 — Xóa bản ghi phiên bản cũ bằng self-join

**Yêu cầu:** tenant 10 chỉ giữ event version lớn nhất mỗi `business_key`.

**Đáp án:**

```sql
BEGIN;

DELETE FROM delete_lab.event_versions AS old
USING delete_lab.event_versions AS newer
WHERE old.tenant_id = 10
  AND newer.tenant_id = old.tenant_id
  AND newer.business_key = old.business_key
  AND newer.version_no > old.version_no
RETURNING old.event_id, old.business_key, old.version_no;

ROLLBACK;
```

Kết quả xóa thử event **100,101**. Không ảnh hưởng event tenant 20.

### Bài 16 — Trạng thái xóa và soft delete

**Câu hỏi:** Một bảng cần lưu lịch sử 5 năm nhưng ẩn đơn khỏi giao diện ngay. Nên mặc định dùng DELETE vật lý không?

**Đáp án:** Không thể quyết định chỉ từ SQL. Nếu yêu cầu giữ lịch sử, có thể dùng cột `deleted_at`/`archived_at` và chính sách lọc/retention phù hợp. Nếu cần xóa hẳn theo chính sách dữ liệu, phải có kế hoạch purge về sau. Việc giữ thông tin cá nhân dưới dạng “ẩn” không tự đáp ứng mọi yêu cầu pháp lý về xóa.

### Bài 17 — Scope theo timestamp nào?

**Yêu cầu:** xóa những đơn **đã bị hủy trước 01/10**, không phải những đơn **được tạo trước 01/10**.

**Đáp án:** Bộ lọc chính phải dựa vào `cancelled_at` cùng trạng thái/điều kiện nghiệp vụ, không thay bằng `created_at`.

### Bài 18 — Trả về 0 hàng

**Câu hỏi:** `DELETE ... RETURNING` trả tập rỗng. Có thể kết luận hệ thống không có đơn cancelled cũ không?

**Đáp án:** Không đủ dữ liệu để kết luận. Có thể không có hàng phù hợp **với toàn bộ điều kiện và quyền hiện tại**, bị giới hạn tenant, có khác biệt snapshot, hoặc các hàng đã được xóa trước đó. Nếu dùng `SKIP LOCKED`, còn có khả năng bỏ qua hàng đang bị khóa.

### Bài 19 — Khi nào xóa bảng con trước?

Nếu FK từ `order_items` về `orders` khai báo `ON DELETE NO ACTION` thay vì `CASCADE` và đang có item, xóa order có thể vi phạm FK.

**Đáp án:** Cần quyết định chính sách nghiệp vụ: cấm xóa đơn có item, xóa child trước parent trong cùng transaction, hoặc chọn `ON DELETE CASCADE` có chủ đích khi phù hợp. Không sửa FK thành CASCADE chỉ để làm lỗi biến mất nếu cần bảo toàn lịch sử chi tiết đơn.

### Bài 20 — Vì sao cần tenant predicate dù ID là PK toàn cục?

**Đáp án:** `order_id` là PK toàn cục có thể giúp tìm một hàng chính xác, nhưng `tenant_id = :authorizedTenant` vẫn là một **guard phạm vi quyền/nghiệp vụ** quan trọng. Một người dùng không nên có thể xóa đơn tenant khác chỉ bằng cách đoán hoặc gửi `order_id` của đơn đó.

## 26. Checklist trước khi COMMIT một thao tác DELETE USING

Trước mỗi job xóa dữ liệu quan trọng, kiểm tra theo thứ tự:

1. **Đúng đối tượng:** bảng sau `DELETE FROM` có phải bảng cần xóa không?
2. **Đúng tenant:** có bộ lọc phạm vi tường minh và quan hệ JOIN đúng tenant không?
3. **Đúng trạng thái:** trạng thái nào được phép xóa, có luật giữ lịch sử/khôi phục nào không?
4. **Đúng mốc thời gian:** dựa vào `created_at`, `cancelled_at`, `paid_at` hay timestamp khác? Dùng timezone/cận phù hợp?
5. **Đúng khóa JOIN:** mọi bảng `USING` đều có điều kiện nối đầy đủ; tránh Cartesian product?
6. **Đúng AND/OR:** đã đặt ngoặc hoặc dùng `IN` để giới hạn tenant cho mọi nhánh chưa?
7. **Đã xem trước:** `SELECT` liệt kê đầy đủ ID và số lượng dự kiến chưa?
8. **Có fanout:** `COUNT(*)` của JOIN có đang đếm lặp một ID target không?
9. **Có thay đổi đồng thời:** snapshot, row locks, batch ID và các guard đã đáp ứng yêu cầu nhất quán chưa?
10. **Có FK/trigger:** dữ liệu con nào bị xóa/cập nhật, bảng nào có thể chặn thao tác?
11. **Có audit và backup:** đã xác định cách ghi nhận và khôi phục nếu thao tác sai chưa?
12. **Có ngưỡng:** số hàng quá cao hoặc khác dự kiến thì phải rollback?
13. **Có batch phù hợp:** nếu dữ liệu lớn, đã chọn khóa/`ORDER BY`, kích thước và xử lý `SKIP LOCKED` đúng chưa?
14. **Có quyền tối thiểu:** role, RLS và phê duyệt có phù hợp?
15. **Có đo hiệu năng:** index trên khóa JOIN/FK, `EXPLAIN`, WAL, lock, autovacuum và replica lag có được cân nhắc?
16. **Có kiểm tra trong transaction:** `RETURNING` có đúng tập mục tiêu trước khi commit?
17. **Có kế hoạch hậu kiểm:** số hàng còn lại, audit, metric job, log lỗi và phương án khôi phục?
18. **Không nhầm ROLLBACK sau COMMIT:** người vận hành hiểu ranh giới transaction?

## 27. Tổng kết

**`DELETE ... USING` là cú pháp PostgreSQL cho phép xóa hàng của một bảng dựa trên điều kiện kết hợp với những nguồn dữ liệu khác.** Nó không có nghĩa xóa tất cả bảng trong `USING`, và cũng không tự đảm bảo giới hạn tenant hoặc trạng thái.

Các nguyên tắc quan trọng:

- **Bảng đích nằm sau `DELETE FROM`; bảng `USING` chỉ hỗ trợ chọn hàng cần xóa.**
- **Điều kiện JOIN phải đầy đủ**, đặc biệt khi khóa nghiệp vụ chỉ duy nhất trong tenant. Không để dữ liệu tenant này khớp nhầm bản ghi tenant khác.
- **Xem trước bằng `SELECT`**, nhưng nhớ JOIN một-nhiều có thể trả nhiều hàng cho một mục tiêu; khi đếm đơn đích, dùng `COUNT(DISTINCT target_pk)` hoặc `EXISTS` phù hợp.
- **Dùng `RETURNING`** để biết hàng đích nào thực sự bị xóa, và **transaction + ROLLBACK** để thử nghiệm trước commit.
- **Đừng quên các tác động gián tiếp:** `ON DELETE CASCADE`, trigger, khóa ngoại, RLS, WAL và MVCC.
- **`SELECT` xem trước không tự đóng băng tập dữ liệu.** Với thao tác cần chính xác hoặc concurrent job, cân nhắc chốt khóa, row locks, isolation và guard ngay trong DELETE.
- **PostgreSQL không có `DELETE ... LIMIT` trực tiếp**; dùng CTE chọn một tập khóa rồi `DELETE ... USING` theo tập đó, có thể kết hợp `FOR UPDATE SKIP LOCKED` trong tình huống phù hợp.
- **`EXPLAIN ANALYZE DELETE` thực sự xóa**, nên chỉ thực hiện có kiểm soát; `EXPLAIN` không `ANALYZE` dùng để xem kế hoạch ước lượng.

**Nguyên tắc cuối cùng:** trước khi xóa, phải trả lời được **“xóa hàng nào, vì sao hàng đó đủ điều kiện, hàng nào chắc chắn không được xóa, và những bản ghi nào khác bị ảnh hưởng?”**. SQL chỉ nên được thực thi sau khi các câu trả lời này được thể hiện thành điều kiện, được xem trước, có ranh giới giao dịch và có khả năng đối chiếu kết quả.

### Tài liệu PostgreSQL chính thức

- [DELETE — cú pháp USING, WHERE và RETURNING](https://www.postgresql.org/docs/current/sql-delete.html).
- [WITH Queries và Data-Modifying Statements in WITH](https://www.postgresql.org/docs/current/queries-with.html).
- [Explicit Locking và FOR UPDATE / SKIP LOCKED](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Foreign Keys và ON DELETE](https://www.postgresql.org/docs/current/ddl-constraints.html).
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html).
