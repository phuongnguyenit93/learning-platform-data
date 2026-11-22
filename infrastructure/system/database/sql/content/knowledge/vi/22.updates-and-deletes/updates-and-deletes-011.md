# Xóa mềm, khôi phục và điều kiện truy vấn dữ liệu còn hiệu lực

Trong SQL, câu lệnh `DELETE FROM ...` thường được hiểu là **xóa hàng khỏi bảng**. Nhưng trong nhiều hệ thống nghiệp vụ, khi người dùng bấm “Xóa khách hàng”, “Đưa sản phẩm vào thùng rác” hoặc “Ngừng sử dụng bản ghi”, doanh nghiệp vẫn cần giữ thông tin để điều tra sự cố, đối soát giao dịch, khôi phục thao tác nhầm hoặc phục vụ yêu cầu lưu trữ hợp pháp. Khi ấy, một thiết kế thường gặp là **xóa mềm** (*soft delete*): **không xóa vật lý hàng**, mà cập nhật một thuộc tính đánh dấu hàng **không còn hiệu lực trong những truy vấn thông thường**.

Ví dụ:

```sql
UPDATE customers
SET deleted_at = CURRENT_TIMESTAMP
WHERE customer_id = 42
  AND deleted_at IS NULL;
```

Hàng của khách 42 vẫn có trong bảng. Một truy vấn thông thường chỉ hiển thị khách còn hiệu lực bằng điều kiện:

```sql
SELECT *
FROM customers
WHERE deleted_at IS NULL;
```

Và có thể khôi phục bằng cách **bỏ dấu xóa mềm** nếu điều kiện nghiệp vụ cho phép:

```sql
UPDATE customers
SET deleted_at = NULL
WHERE customer_id = 42
  AND deleted_at IS NOT NULL;
```

Tuy nhiên, ba câu lệnh trên **chưa đủ để thiết kế một hệ thống an toàn**. Khi có nhiều tenant, khóa duy nhất, bảng con, JOIN, báo cáo, tìm kiếm, cache, phân quyền hoặc nhiều người cập nhật đồng thời, việc “giấu hàng có `deleted_at`” phải được thực hiện nhất quán. Khôi phục cũng không luôn thành công: một khách cũ có thể có email đã được khách mới sử dụng; một sản phẩm từng xóa có thể đã hết quyền bán; một bản ghi đã xóa theo yêu cầu pháp lý có thể **không được phép** khôi phục.

Bài học thuộc **Database SQL → Cập nhật và xóa**. Chúng ta sẽ xây dựng một ví dụ **PostgreSQL** tự chứa, giải thích các mẫu xóa mềm và khôi phục có điều kiện, ràng buộc tính duy nhất cho dữ liệu còn hiệu lực, tác động đến `SELECT`, `JOIN`, tổng hợp, khóa ngoại, giao dịch và bảo mật, rồi đối chiếu những lựa chọn trên SQL Server, MySQL, SQLite và Oracle.

> **Nguyên tắc cốt lõi:** “xóa mềm” là một **trạng thái nghiệp vụ** được lưu bằng `UPDATE`; còn “chỉ đọc dữ liệu còn hiệu lực” là một **hợp đồng truy vấn** phải được duy trì xuyên suốt hệ thống. Giữ hàng trong database không đồng nghĩa hàng đó vẫn được sử dụng như đang hoạt động.

## 1. Phân biệt xóa vật lý, xóa mềm và vô hiệu hóa

Trước hết, cần phân biệt những thao tác trông giống nhau trên giao diện.

| Thao tác | Dữ liệu còn trong bảng? | Ý nghĩa | Khả năng khôi phục |
| --- | --- | --- | --- |
| **Xóa vật lý** (*hard delete*) bằng `DELETE` | Không còn hàng trong bảng đó sau commit | Loại hàng khỏi quan hệ dữ liệu | Thường cần backup, audit hoặc nguồn khác để dựng lại |
| **Xóa mềm** (*soft delete*) bằng `UPDATE` | Có | Đánh dấu bản ghi không thuộc tập “còn hiệu lực” | Có thể đảo trạng thái nếu thỏa ràng buộc và chính sách |
| **Vô hiệu hóa** (`is_active = false`) | Có | Thực thể còn tồn tại nhưng tạm ngừng một chức năng | Có thể bật lại, nhưng không nhất thiết là khôi phục từ thùng rác |
| **Lưu trữ/đóng hồ sơ** (`archived_at`, `closed_at`) | Có | Kết thúc một chu kỳ nghiệp vụ hoặc chuyển trạng thái lưu trữ | Tùy workflow; không luôn tương đương xóa mềm |
| **Ẩn khỏi công khai** (`published = false`) | Có | Không hiển thị công khai nhưng người quản trị vẫn quản lý bình thường | Bật lại trạng thái công khai |
| **Xóa theo hạn lưu giữ** (*purge*) | Có thể bị xóa vật lý | Loại dữ liệu quá hạn theo chính sách | Có thể không còn khả năng khôi phục |

Chẳng hạn, một hóa đơn **đã phát hành** thường không nên được “xóa” chỉ bằng cập nhật `deleted_at`: quy trình nghiệp vụ có thể yêu cầu hủy/điều chỉnh bằng chứng từ riêng. Tương tự, cấm đăng nhập (`disabled_at`) không có nghĩa xóa hồ sơ người dùng (`deleted_at`).

**Không áp dụng soft delete máy móc cho mọi bảng.** Trước khi thiết kế, cần trả lời: bản ghi có thật sự được xem là không còn hiệu lực, hay chỉ chuyển sang một trạng thái khác?

### 1.1. Ví dụ minh họa

```text
customers

customer_id   name          deleted_at
----------    ----------    --------------------------
1             An            NULL
2             Bình          NULL
3             Chi           2026-10-09 13:00:00+07

SELECT * FROM customers;
  -> Thấy cả 3 hàng.

SELECT * FROM customers WHERE deleted_at IS NULL;
  -> Chỉ thấy An và Bình.
```

Hàng của Chi **chưa mất**, nhưng quy tắc truy vấn mặc định sẽ coi Chi là **không còn hiệu lực**.

## 2. Các cách biểu diễn trạng thái xóa mềm

Có nhiều schema thường gặp:

### 2.1. Cờ Boolean `is_deleted`

```sql
CREATE TABLE example_products (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
```

Truy vấn dữ liệu còn hiệu lực:

```sql
SELECT *
FROM example_products
WHERE is_deleted = FALSE;
```

Ưu điểm: dễ hiểu, bộ lọc đơn giản. Nhược điểm: **không biết xóa khi nào** nếu không có cột khác; cần audit bổ sung để tra cứu.

### 2.2. Mốc thời gian `deleted_at`

```sql
CREATE TABLE example_products (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ NULL
);
```

Quy ước:

- `deleted_at IS NULL`: bản ghi **còn hiệu lực**.
- `deleted_at IS NOT NULL`: bản ghi **đã xóa mềm**.
- `deleted_at` khác NULL ghi lại **thời điểm xóa mềm**, hữu ích cho audit và dọn dữ liệu sau thời gian lưu giữ.

Trong bài học này, ta dùng `deleted_at` làm **nguồn trạng thái chính**. Không dùng song song `is_deleted` và `deleted_at` nếu không có quy tắc cưỡng chế tính nhất quán; nếu một cột nói đã xóa còn cột kia nói đang hoạt động, truy vấn có thể trả kết quả mâu thuẫn.

### 2.3. Các cột bổ sung

Một hệ thống thực tế có thể cần:

```text
deleted_at        TIMESTAMPTZ NULL
deleted_by        TEXT NULL
delete_reason     TEXT NULL
updated_at        TIMESTAMPTZ NOT NULL
version           BIGINT NOT NULL
```

`deleted_by` là người/hệ thống thực hiện. `delete_reason` là lý do theo chính sách. `version` hỗ trợ kiểm soát cập nhật đồng thời. Các cột này **không thay thế audit log bất biến**: khi khôi phục và đặt `deleted_at = NULL`, nếu cũng xóa `deleted_by`/`delete_reason` thì thông tin hành động cũ biến mất khỏi chính hàng.

### 2.4. Timestamp hay thời điểm có hiệu lực?

`deleted_at` thường biểu diễn **thời điểm thao tác xóa**. Nếu nghiệp vụ là “sản phẩm sẽ hết hiệu lực từ 00:00 ngày mai”, đó có thể là một thuộc tính **effective_until** khác:

```sql
WHERE effective_from <= :as_of
  AND (effective_until IS NULL OR effective_until > :as_of)
```

Đừng tự thay “hết hạn hiệu lực theo lịch” bằng “đã xóa mềm” nếu hệ thống cần cả hai trạng thái. Bài này tập trung vào **xóa mềm và bộ lọc các hàng chưa bị xóa**; dữ liệu có thời gian hiệu lực riêng phải thêm điều kiện tương ứng.

## 3. Bộ dữ liệu PostgreSQL tự chứa

Ví dụ gồm **khách hàng** và **đơn hàng**, có nhiều tenant, một số khách đã xóa mềm, một số đơn đã xóa mềm. Điều này giúp làm rõ sự khác biệt giữa trạng thái hàng cha và trạng thái hàng con.

Trong một phiên PostgreSQL, chạy:

```sql
CREATE TEMP TABLE demo_soft_customers (
    customer_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by TEXT NULL,
    delete_reason TEXT NULL,
    CONSTRAINT uq_demo_soft_customer_tenant
        UNIQUE (tenant_id, customer_id)
);

CREATE UNIQUE INDEX uq_demo_soft_active_email
ON demo_soft_customers (
    tenant_id,
    lower(email)
)
WHERE deleted_at IS NULL;

CREATE TEMP TABLE demo_soft_orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PAID', 'PENDING', 'CANCELED')
    ),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    deleted_at TIMESTAMPTZ NULL,
    deleted_by TEXT NULL,
    CONSTRAINT fk_demo_soft_order_customer
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_soft_customers(tenant_id, customer_id)
);

INSERT INTO demo_soft_customers (
    customer_id, tenant_id, email, full_name,
    deleted_at, deleted_by, delete_reason
)
VALUES
    (1, 10, 'an@example.com',   'An',         NULL, NULL, NULL),
    (2, 10, 'binh@example.com', 'Bình',       NULL, NULL, NULL),
    (3, 10, 'chi@example.com',  'Chi',
        TIMESTAMPTZ '2026-10-09 13:00:00+07', 'ops-1', 'Yêu cầu ẩn hồ sơ'),
    (4, 10, 'an@example.com',   'An bản cũ',
        TIMESTAMPTZ '2026-10-02 09:00:00+07', 'ops-2', 'Bản ghi lưu trữ'),
    (5, 20, 'an@example.com',   'An tenant khác',
        NULL, NULL, NULL),
    (6, 10, 'dung@example.com', 'Dũng',      NULL, NULL, NULL),
    (7, 10, 'em@example.com',   'Em',
        TIMESTAMPTZ '2026-10-08 08:00:00+07', 'ops-1', 'Ngừng sử dụng'),
    (8, 10, 'hoa@example.com',  'Hoa',       NULL, NULL, NULL);

INSERT INTO demo_soft_orders (
    order_id, tenant_id, customer_id, status, amount,
    deleted_at, deleted_by
)
VALUES
    (1001, 10, 1, 'PAID',    120.00, NULL, NULL),
    (1002, 10, 1, 'PAID',     80.00,
        TIMESTAMPTZ '2026-10-10 09:00:00+07', 'ops-1'),
    (1003, 10, 2, 'PAID',    200.00, NULL, NULL),
    (1004, 10, 3, 'PAID',     90.00, NULL, NULL),
    (1005, 10, 4, 'PAID',     50.00, NULL, NULL),
    (1006, 20, 5, 'PAID',    300.00, NULL, NULL),
    (1007, 10, 6, 'PENDING',   0.00, NULL, NULL),
    (1008, 10, 7, 'PAID',     70.00,
        TIMESTAMPTZ '2026-10-09 08:00:00+07', 'ops-1'),
    (1009, 10, 6, 'PAID',    150.00, NULL, NULL),
    (1010, 10, 8, 'PAID',     60.00,
        TIMESTAMPTZ '2026-10-11 08:00:00+07', 'ops-2');
```

### 3.1. Ý nghĩa của mẫu dữ liệu

| customer_id | tenant_id | email | Trạng thái |
| ---: | ---: | --- | --- |
| 1 | 10 | an@example.com | Còn hiệu lực |
| 2 | 10 | binh@example.com | Còn hiệu lực |
| 3 | 10 | chi@example.com | Đã xóa mềm |
| 4 | 10 | an@example.com | Đã xóa mềm, **trùng email với khách 1** |
| 5 | 20 | an@example.com | Còn hiệu lực ở **tenant khác** |
| 6 | 10 | dung@example.com | Còn hiệu lực |
| 7 | 10 | em@example.com | Đã xóa mềm |
| 8 | 10 | hoa@example.com | Còn hiệu lực, chỉ có đơn đã xóa mềm |

Trong tenant 10:

- Có **7 khách** trong bảng, gồm **4 còn hiệu lực** (1, 2, 6, 8) và **3 đã xóa mềm** (3, 4, 7).
- Có **9 đơn hàng** trong bảng đơn, trong đó **3 đơn đã xóa mềm** (1002, 1008, 1010).
- Có **6 đơn chưa xóa mềm** (1001, 1003, 1004, 1005, 1007, 1009), nhưng **2 đơn trong số đó thuộc khách đã xóa mềm** (1004 của khách 3 và 1005 của khách 4).
- Nếu báo cáo chỉ lấy **đơn chưa xóa mềm của khách còn hiệu lực**, có **4 đơn** (1001, 1003, 1007, 1009), trong đó **3 PAID** với tổng tiền **470.00**.

Khách 8 (Hoa) chỉ có đơn 1010 đã xóa mềm: đây là trường hợp quan trọng để minh họa **LEFT JOIN phải đặt điều kiện hàng con ở đâu**.

**Lưu ý về cách chạy:** các ví dụ sửa dữ liệu ở phần sau thường dùng `BEGIN ... ROLLBACK` để quan sát hành vi mà không làm thay đổi bảng demo gốc. Nếu tự `COMMIT` các ví dụ, số hàng của những truy vấn tiếp theo có thể thay đổi đúng theo thao tác vừa làm.

## 4. Truy vấn mặc định: chỉ lấy bản ghi còn hiệu lực

Quy tắc cơ bản khi dùng `deleted_at`:

```sql
SELECT
    customer_id,
    tenant_id,
    email,
    full_name
FROM demo_soft_customers
WHERE tenant_id = 10
  AND deleted_at IS NULL
ORDER BY customer_id;
```

Kết quả:

| customer_id | full_name |
| ---: | --- |
| 1 | An |
| 2 | Bình |
| 6 | Dũng |
| 8 | Hoa |

`IS NULL` là điều kiện SQL đúng để kiểm tra chưa bị xóa mềm. **Không viết**:

```sql
WHERE deleted_at = NULL
```

Trong SQL thông thường, so sánh bằng `=` với NULL cho **UNKNOWN**, không phải TRUE. Câu điều kiện ấy không chọn những hàng có deleted_at NULL như người mới học có thể mong đợi.

### 4.1. Ba phạm vi đọc thường cần thiết

**Danh sách còn hiệu lực** cho nghiệp vụ hằng ngày:

```sql
SELECT *
FROM demo_soft_customers
WHERE tenant_id = 10
  AND deleted_at IS NULL;
```

**Thùng rác** cho người có quyền khôi phục:

```sql
SELECT
    customer_id, full_name, deleted_at, deleted_by, delete_reason
FROM demo_soft_customers
WHERE tenant_id = 10
  AND deleted_at IS NOT NULL
ORDER BY deleted_at DESC, customer_id;
```

**Danh sách tất cả**, gồm cả còn hiệu lực và đã xóa mềm, chỉ dành cho nghiệp vụ kiểm toán/quản trị phù hợp:

```sql
SELECT
    customer_id, full_name, deleted_at
FROM demo_soft_customers
WHERE tenant_id = 10
ORDER BY customer_id;
```

Đừng gọi cả ba câu truy vấn là “lấy danh sách khách” trong mã nguồn mà không phân biệt. Tên và quyền gọi cần biểu thị rõ **mặc định active, chỉ deleted, hay all**.

### 4.2. Tenant và soft delete là hai bộ lọc độc lập

Điều kiện:

```sql
WHERE tenant_id = 10
  AND deleted_at IS NULL
```

có hai ý nghĩa khác nhau:

- `tenant_id = 10`: xác định **phạm vi dữ liệu mà người gọi được phép truy cập**.
- `deleted_at IS NULL`: chọn những bản ghi **còn hiệu lực trong phạm vi đó**.

Chỉ thêm `deleted_at IS NULL` mà quên tenant có thể làm lộ khách của tenant khác. Chỉ thêm tenant mà quên deleted_at có thể hiện lại dữ liệu đã bị ẩn. Với API nhiều tenant, tenant phải được xác định bằng **ngữ cảnh xác thực ở server**, không tin giá trị tenant mà client tự khai báo.

## 5. Xóa mềm bằng UPDATE có điều kiện

Mẫu thao tác:

```sql
UPDATE demo_soft_customers
SET deleted_at = CURRENT_TIMESTAMP,
    deleted_by = 'staff-42',
    delete_reason = 'Người dùng yêu cầu ẩn',
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = 10
  AND customer_id = 2
  AND deleted_at IS NULL
RETURNING
    customer_id, full_name, deleted_at, deleted_by;
```

Đây là `UPDATE`, không phải `DELETE`. Điều kiện `deleted_at IS NULL` có tác dụng **chỉ chuyển trạng thái của hàng đang còn hiệu lực**.

### 5.1. Thực hành mà không để lại thay đổi

```sql
BEGIN;

UPDATE demo_soft_customers
SET deleted_at = CURRENT_TIMESTAMP,
    deleted_by = 'staff-42',
    delete_reason = 'Thử nghiệm xóa mềm',
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = 10
  AND customer_id = 2
  AND deleted_at IS NULL
RETURNING customer_id, full_name, deleted_at;

SELECT customer_id, full_name
FROM demo_soft_customers
WHERE tenant_id = 10
  AND deleted_at IS NULL
ORDER BY customer_id;

ROLLBACK;
```

Trong transaction, sau UPDATE, khách 2 **không còn trong danh sách active** của chính transaction đó. `ROLLBACK` đưa hàng trở lại trạng thái ban đầu. Khi chạy nghiệp vụ thật, sau khi kiểm tra và ghi audit cần **COMMIT** thay vì ROLLBACK.

### 5.2. Vì sao cần điều kiện trạng thái trong WHERE?

Giả sử hai request xóa cùng khách:

```sql
UPDATE customers
SET deleted_at = CURRENT_TIMESTAMP
WHERE customer_id = :id;
```

Request thứ hai có thể **ghi đè thời điểm xóa trước đó**, làm sai thông tin audit. Nếu dùng:

```sql
WHERE customer_id = :id
  AND deleted_at IS NULL
```

request đầu chuyển hàng sang deleted, request sau thường cập nhật **0 hàng**. Ứng dụng có thể xem đây là “đã xóa từ trước” hoặc phản hồi một trạng thái cụ thể theo hợp đồng API; quan trọng là **không vô tình ghi đè metadata của lần xóa đầu**.

### 5.3. Chỉ định đúng phạm vi khi UPDATE

Một lệnh nguy hiểm:

```sql
-- KHÔNG chạy: thiếu WHERE, sẽ đánh dấu mọi khách!
UPDATE demo_soft_customers
SET deleted_at = CURRENT_TIMESTAMP;
```

Với soft delete, quên WHERE không xóa vật lý hàng nhưng vẫn có thể khiến **mọi khách biến mất khỏi giao diện hoạt động**, gây sự cố nghiêm trọng.

Trong production:

- Dùng khóa chính hoặc khóa nghiệp vụ **kèm tenant**.
- Kiểm tra số hàng tác động bằng `RETURNING` hoặc row count của driver.
- Có transaction và phân quyền UPDATE rõ.
- Với thao tác xóa nhiều hàng, dùng một bước SELECT/preview số lượng và chính sách xác nhận phù hợp.

## 6. Khôi phục bằng UPDATE: không phải cứ SET NULL là xong

Khôi phục cơ bản:

```sql
UPDATE demo_soft_customers
SET deleted_at = NULL,
    deleted_by = NULL,
    delete_reason = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = 10
  AND customer_id = 3
  AND deleted_at IS NOT NULL
RETURNING customer_id, full_name, deleted_at;
```

Trong dữ liệu mẫu, khách 3 (Chi) đang deleted và không có khách còn hiệu lực khác dùng `chi@example.com`, nên thao tác khôi phục có thể thành công.

Thực hành trong transaction:

```sql
BEGIN;

UPDATE demo_soft_customers
SET deleted_at = NULL,
    deleted_by = NULL,
    delete_reason = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = 10
  AND customer_id = 3
  AND deleted_at IS NOT NULL
RETURNING customer_id, full_name, deleted_at;

SELECT customer_id, full_name
FROM demo_soft_customers
WHERE tenant_id = 10
  AND deleted_at IS NULL
ORDER BY customer_id;

ROLLBACK;
```

Khi transaction chưa rollback, danh sách active tạm thời gồm **5 khách** ở tenant 10. Sau ROLLBACK trở về **4**. Nếu muốn khôi phục thật, phải thực hiện các kiểm tra nghiệp vụ và COMMIT.

### 6.1. Không nên làm mất lịch sử xóa

Đặt `deleted_by` và `delete_reason` về NULL có thể phù hợp nếu đây là metadata **chỉ của trạng thái xóa hiện tại**. Tuy nhiên, một audit trail nghiêm túc cần lưu sự kiện:

```text
customer_id=3, action=SOFT_DELETE, actor=ops-1, at=...
customer_id=3, action=RESTORE, actor=staff-42, at=...
```

ở bảng nhật ký riêng hoặc hệ audit bất biến theo chính sách. Nếu chỉ có `deleted_at` và lúc restore đặt NULL, lịch sử hành động trước đó **không còn truy được từ hàng hiện tại**.

### 6.2. Khôi phục phải có quyền

Người dùng được phép **đọc** bản ghi đã xóa không nhất thiết được phép **khôi phục**. Một người quản lý có thể xem hồ sơ archive để đối soát nhưng không được chuyển hồ sơ đó về danh sách active. Quyền restore phải được kiểm tra tại tầng ứng dụng và/hoặc database, cùng kiểm tra tenant, trạng thái và ràng buộc nghiệp vụ.

## 7. Ràng buộc UNIQUE khi có dữ liệu đã xóa mềm

Đây là một vấn đề phổ biến nhất của soft delete.

Giả sử ứng dụng quy định: **trong cùng tenant, không có hai khách còn hiệu lực dùng cùng email**. Sau khi một khách bị xóa mềm, email đó có thể được một khách mới sử dụng. Nhưng nếu viết:

```sql
UNIQUE (tenant_id, email)
```

trên toàn bảng, cả hàng deleted vẫn tham gia constraint, nên **ngăn email được sử dụng lại**.

Trong PostgreSQL, ta đã tạo **unique partial index**:

```sql
CREATE UNIQUE INDEX uq_demo_soft_active_email
ON demo_soft_customers (
    tenant_id,
    lower(email)
)
WHERE deleted_at IS NULL;
```

Ý nghĩa:

- Chỉ những hàng `deleted_at IS NULL` tham gia ràng buộc duy nhất.
- Phạm vi unique là `(tenant_id, lower(email))`.
- Cùng email có thể có một hàng **active** và nhiều hàng **deleted** trong cùng tenant.
- Cùng email có thể active ở **hai tenant khác nhau**.

Trong dữ liệu mẫu:

```text
tenant 10, customer 1, an@example.com, ACTIVE
tenant 10, customer 4, an@example.com, DELETED
tenant 20, customer 5, an@example.com, ACTIVE
```

Ba hàng này không vi phạm partial index.

### 7.1. Khôi phục có thể thất bại do UNIQUE

Nếu khôi phục khách 4:

```sql
-- Ví dụ dự kiến gây lỗi unique_violation trong PostgreSQL:
UPDATE demo_soft_customers
SET deleted_at = NULL
WHERE tenant_id = 10
  AND customer_id = 4;
```

thì khách 4 sẽ trở thành **active trong tenant 10** và cùng email với khách 1, vi phạm `uq_demo_soft_active_email`. PostgreSQL **từ chối UPDATE**, không tự chọn một khách để ghi đè.

**Không thực thi ví dụ cố ý gây lỗi này trong cùng transaction chứa những thao tác tiếp theo** nếu chưa có xử lý lỗi/savepoint: một lỗi SQL có thể đưa transaction PostgreSQL vào trạng thái aborted đến khi ROLLBACK.

### 7.2. Phương án xử lý xung đột khi restore

Tùy nghiệp vụ, có thể:

1. **Từ chối restore**, báo rằng email hiện được một bản ghi active sử dụng.
2. **Yêu cầu đổi email** trước khi khôi phục, nếu định danh đăng nhập cho phép và đã xác minh quyền sở hữu.
3. **Hợp nhất hồ sơ** theo workflow riêng, với đối soát dữ liệu liên quan; không tự xóa hồ sơ active.
4. **Chuyển quyền sở hữu email** theo chính sách có kiểm soát, có audit và tránh ảnh hưởng bảo mật.

Không giải quyết bằng cách tắt UNIQUE để thao tác chạy, vì sẽ tạo hai bản ghi active có cùng khóa mà mọi truy vấn đăng nhập/tra cứu email có thể không xử lý đúng.

### 7.3. Vì sao UNIQUE gồm `deleted_at` không giải quyết đơn giản?

Một cách tưởng hợp lý:

```sql
UNIQUE (tenant_id, email, deleted_at)
```

không tương đương với “chỉ một email active”, vì ở nhiều DBMS (trong đó có cấu hình thông thường của PostgreSQL), các giá trị NULL trong UNIQUE có ngữ nghĩa riêng và **nhiều hàng có deleted_at NULL vẫn có thể cùng tồn tại**. Ngược lại, khi khác thời điểm xóa, hai hàng deleted cũng có các khóa khác nhau.

Hãy dùng cơ chế thực sự phù hợp với DBMS và quy tắc trạng thái, thay vì đưa `deleted_at` vào UNIQUE mà không kiểm tra semantics NULL.

## 8. Đếm dữ liệu: COUNT(*) không tự bỏ hàng deleted

Tổng số khách tenant 10:

```sql
SELECT COUNT(*) AS all_customer_rows
FROM demo_soft_customers
WHERE tenant_id = 10;
-- 7
```

Số khách **còn hiệu lực**:

```sql
SELECT COUNT(*) AS active_customers
FROM demo_soft_customers
WHERE tenant_id = 10
  AND deleted_at IS NULL;
-- 4
```

Số khách đã xóa mềm:

```sql
SELECT COUNT(*) AS deleted_customers
FROM demo_soft_customers
WHERE tenant_id = 10
  AND deleted_at IS NOT NULL;
-- 3
```

Các phép COUNT đều đúng theo **phạm vi hàng đã chọn**. Lỗi không nằm ở COUNT, mà ở việc người viết báo cáo quên định nghĩa đang đếm:

- Tất cả hàng còn lưu trong database?
- Những khách active?
- Những khách deleted trong thùng rác?
- Những khách từng active ở một thời điểm lịch sử?

Đừng gọi chung các đại lượng ấy là “tổng khách hàng” mà không giải thích.

### 8.1. GROUP BY trạng thái

PostgreSQL:

```sql
SELECT
    CASE
        WHEN deleted_at IS NULL THEN 'ACTIVE'
        ELSE 'SOFT_DELETED'
    END AS record_state,
    COUNT(*) AS customer_count
FROM demo_soft_customers
WHERE tenant_id = 10
GROUP BY
    CASE
        WHEN deleted_at IS NULL THEN 'ACTIVE'
        ELSE 'SOFT_DELETED'
    END
ORDER BY record_state;
```

Kết quả `ACTIVE = 4`, `SOFT_DELETED = 3`. Đây là báo cáo **quản trị trạng thái**, trong đó cố ý xem cả deleted và active. Nó khác danh sách hoạt động mặc định, vốn chỉ lấy active.

## 9. JOIN: phải quyết định trạng thái của cả bảng cha và bảng con

Soft delete dễ tạo lỗi khi dữ liệu được kết nối bằng JOIN. Bản thân `JOIN` không tự biết `deleted_at` của bảng nào cần lọc.

### 9.1. JOIN lấy đơn của khách active nhưng chưa lọc đơn active

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.amount,
    o.deleted_at AS order_deleted_at
FROM demo_soft_customers AS c
JOIN demo_soft_orders AS o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.customer_id
WHERE c.tenant_id = 10
  AND c.deleted_at IS NULL
ORDER BY c.customer_id, o.order_id;
```

Truy vấn có thể đưa ra cả đơn **1002** của khách 1 và đơn **1010** của khách 8, dù hai đơn này đã xóa mềm. Vì chỉ có điều kiện trên **c**, không có điều kiện active của **o**.

Nếu yêu cầu là “chỉ những đơn còn hiệu lực của khách còn hiệu lực”, thêm:

```sql
AND o.deleted_at IS NULL
```

Ở đây JOIN trong là `INNER JOIN`, nên điều kiện trong `WHERE` hoặc `ON` thường tương đương về tập hàng với bộ lọc thuần `o.deleted_at IS NULL`. Nhưng với **LEFT JOIN**, vị trí điều kiện có thể thay đổi kết quả.

### 9.2. LEFT JOIN: đặt điều kiện đơn active ở ON

Muốn danh sách **mọi khách active**, kể cả khách không còn đơn active, kèm số đơn hiện còn hiệu lực:

```sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS active_order_count,
    COALESCE(
        SUM(o.amount) FILTER (WHERE o.status = 'PAID'),
        0
    ) AS active_paid_amount
FROM demo_soft_customers AS c
LEFT JOIN demo_soft_orders AS o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.customer_id
   AND o.deleted_at IS NULL
WHERE c.tenant_id = 10
  AND c.deleted_at IS NULL
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | Khách | active_order_count | active_paid_amount |
| ---: | --- | ---: | ---: |
| 1 | An | 1 | 120.00 |
| 2 | Bình | 1 | 200.00 |
| 6 | Dũng | 2 | 150.00 |
| 8 | Hoa | 0 | 0.00 |

**Vì sao Hoa vẫn xuất hiện?** Điều kiện `o.deleted_at IS NULL` trong `ON` khiến đơn đã xóa mềm 1010 không được xem là hàng khớp, nhưng `LEFT JOIN` vẫn giữ **một hàng khách Hoa với các cột o là NULL**. `COUNT(o.order_id)` đúng bằng 0, không phải 1.

### 9.3. Cạm bẫy: lọc ở WHERE sau LEFT JOIN

Xem truy vấn:

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id
FROM demo_soft_customers AS c
LEFT JOIN demo_soft_orders AS o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.customer_id
WHERE c.tenant_id = 10
  AND c.deleted_at IS NULL
  AND o.deleted_at IS NULL;
```

Ở khách Hoa, phép JOIN **đã tìm thấy đơn 1010** (vì ON chỉ kiểm tra khóa), nhưng dòng này có `o.deleted_at IS NOT NULL`, nên WHERE loại đi. SQL **không tạo lại hàng bù NULL** sau khi WHERE đã lọc. Kết quả: **khách Hoa biến mất**, trái yêu cầu giữ mọi khách active.

Ngược lại, nếu khách **không có đơn nào trong bảng**, LEFT JOIN tạo hàng NULL và `o.deleted_at IS NULL` trong WHERE lại là TRUE; khách ấy có thể vẫn xuất hiện. Vì vậy lỗi này **khó nhận thấy** nếu tập kiểm thử không chứa trường hợp “chỉ có con đã xóa mềm”.

**Mẫu an toàn cho yêu cầu giữ bảng cha:** đặt điều kiện hiệu lực của hàng con vào `ON`, còn điều kiện hiệu lực của hàng cha trong `WHERE` của truy vấn ngoài.

### 9.4. COUNT(*) hay COUNT(o.order_id)?

Sau LEFT JOIN, một khách không có đơn active vẫn có **một hàng khách** kèm cột đơn NULL. `COUNT(*)` sẽ đếm 1. `COUNT(o.order_id)` chỉ đếm những hàng có order_id không NULL, phù hợp để đếm **số đơn thực**.

```sql
COUNT(o.order_id)
```

khác:

```sql
COUNT(*)
```

trong ngữ cảnh này. Đừng đổi thành COUNT(*) chỉ vì muốn câu SQL ngắn hơn.

## 10. Báo cáo đơn active và khách active: định nghĩa không luôn giống nhau

Trong mẫu tenant 10:

```sql
-- A. Đơn chưa xóa mềm, bất kể khách đã xóa mềm hay chưa.
SELECT COUNT(*) AS active_order_rows
FROM demo_soft_orders
WHERE tenant_id = 10
  AND deleted_at IS NULL;
-- 6
```

Nhưng một yêu cầu khác:

```sql
-- B. Chỉ đơn chưa xóa mềm của khách còn hiệu lực.
SELECT COUNT(*) AS active_orders_of_active_customers
FROM demo_soft_orders AS o
JOIN demo_soft_customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.deleted_at IS NULL
  AND c.deleted_at IS NULL;
-- 4
```

Hai số **6** và **4** đều chính xác theo phạm vi tương ứng. Chúng khác nhau vì hai đơn **1004 và 1005** chưa bị xóa mềm, nhưng khách sở hữu **đã xóa mềm**.

### 10.1. Đừng ẩn đơn lịch sử khỏi báo cáo tài chính theo mặc định

Một đơn đã thanh toán vẫn có thể cần được tính vào báo cáo kế toán, **dù hồ sơ khách đã bị ẩn khỏi CRM**. Nếu một báo cáo doanh thu đột nhiên cộng thêm `c.deleted_at IS NULL` do tái sử dụng một “default scope” của ORM, số tiền có thể giảm mà không hề có nghiệp vụ hoàn tiền.

Hãy phân biệt:

- **Giao diện quản lý khách còn hiệu lực**: cần lọc customer active.
- **Danh sách đơn còn hiệu lực**: cần lọc order active theo quy ước.
- **Doanh thu lịch sử đã ghi nhận**: cần dựa vào trạng thái giao dịch/kế toán và chính sách chỉnh sửa, không được tự động bỏ mọi đơn của khách archived.

**Trạng thái xóa mềm là thuộc tính của một thực thể**, không tự động quyết định trạng thái pháp lý/tài chính của mọi thực thể liên quan.

### 10.2. Phạm vi doanh thu phụ thuộc yêu cầu

Trong tenant 10, với **đơn chưa xóa mềm của khách active**, tổng tiền đơn `PAID` là:

```sql
SELECT COALESCE(SUM(o.amount), 0) AS paid_amount
FROM demo_soft_orders AS o
JOIN demo_soft_customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.deleted_at IS NULL
  AND c.deleted_at IS NULL
  AND o.status = 'PAID';
-- 470.00
```

Nếu **không lọc khách active**, tổng các đơn PAID chưa xóa mềm của tenant 10 là **610.00**, vì cộng thêm 90.00 và 50.00 từ hai khách archived. Chọn số nào đúng phải xuất phát từ **định nghĩa chỉ số**, không phải từ việc biến mọi bảng thành active-only.

## 11. Khóa ngoại và soft delete: FK không tự quan tâm deleted_at

Khóa ngoại:

```sql
FOREIGN KEY (tenant_id, customer_id)
REFERENCES demo_soft_customers(tenant_id, customer_id)
```

bảo đảm hàng order tham chiếu tới **một hàng customer đang tồn tại vật lý** với cặp khóa tương ứng. Khi customer bị soft delete:

```sql
UPDATE demo_soft_customers
SET deleted_at = CURRENT_TIMESTAMP
WHERE customer_id = 3;
```

hàng customer **vẫn tồn tại** nên khóa ngoại của các order trỏ tới customer ấy vẫn hợp lệ.

### 11.1. `ON DELETE CASCADE` không chạy khi soft delete

Một FK có `ON DELETE CASCADE` sẽ hoạt động khi hàng cha bị **DELETE vật lý** theo điều kiện hỗ trợ của DBMS. Nhưng soft delete chỉ là `UPDATE deleted_at`, nên **không kích hoạt cơ chế ON DELETE CASCADE của FK**.

Nếu nghiệp vụ muốn “xóa mềm khách thì xóa mềm các bản ghi con”, bạn phải thiết kế riêng:

- Transaction cập nhật cha và con.
- Trigger hoặc service layer áp dụng policy.
- Truy vấn mặc định ẩn con nếu cha không active, **không thực sự thay đổi trạng thái của con**.
- Một cấu trúc quản lý quan hệ/retention riêng.

Không có một lựa chọn phù hợp cho mọi bảng. Ví dụ, **không tự động xóa mềm giao dịch thanh toán** chỉ vì khách yêu cầu ẩn hồ sơ; giao dịch có thể phải tiếp tục lưu theo chính sách kế toán.

### 11.2. Kiểu cascade có kiểm soát

Giả sử sản phẩm có bảng `customer_drafts` chỉ là dữ liệu nháp, chính sách cho phép xóa mềm toàn bộ nháp cùng customer. Một transaction có thể:

```sql
BEGIN;

UPDATE customer_drafts
SET deleted_at = CURRENT_TIMESTAMP,
    deleted_by = :actor_id
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id
  AND deleted_at IS NULL;

UPDATE customers
SET deleted_at = CURRENT_TIMESTAMP,
    deleted_by = :actor_id
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id
  AND deleted_at IS NULL;

COMMIT;
```

Đây là **mẫu bảng/placeholder giả định**, không phải đoạn chạy nguyên trạng trên bảng demo (bảng `customer_drafts` chưa được tạo). Transaction giúp các cập nhật cùng commit hoặc rollback theo cơ chế DBMS.

Nếu ứng dụng cho phép tạo nháp mới đồng thời, chỉ gom hai UPDATE trong transaction **chưa chắc ngăn một request khác chèn nháp mới vào đúng thời điểm xóa**. Cần phối hợp khóa hàng cha, kiểm tra trạng thái trong transaction ghi con và cơ chế đồng bộ phù hợp.

### 11.3. Không khôi phục tất cả hàng con một cách mù quáng

Một đơn/hàng con có thể đã bị xóa mềm **trước đó vì lý do độc lập**. Khi khôi phục cha, không nên:

```sql
-- Nguy hiểm về logic: khôi phục mọi con đã xóa!
UPDATE child_records
SET deleted_at = NULL
WHERE parent_id = :id;
```

Nếu cần khôi phục các con đã bị xóa **do cùng một thao tác cascade**, nên lưu **mã nhóm xóa** hoặc metadata nguồn xóa để chỉ phục hồi đúng các hàng bị ảnh hưởng bởi thao tác ấy, và kiểm tra từng quy tắc nghiệp vụ. Khôi phục cha có thể cần giữ nguyên các con đã bị xóa vì lý do riêng.

## 12. Chọn cách lọc hàng con: ON, WHERE, EXISTS và NOT EXISTS

Không phải bài toán nào cũng cần JOIN để trả dữ liệu con.

### 12.1. Khách active có ít nhất một đơn active

```sql
SELECT
    c.customer_id, c.full_name
FROM demo_soft_customers AS c
WHERE c.tenant_id = 10
  AND c.deleted_at IS NULL
  AND EXISTS (
      SELECT 1
      FROM demo_soft_orders AS o
      WHERE o.tenant_id = c.tenant_id
        AND o.customer_id = c.customer_id
        AND o.deleted_at IS NULL
  )
ORDER BY c.customer_id;
```

Trong bộ mẫu, kết quả là khách **1, 2 và 6**; khách 8 chỉ có đơn deleted nên không thỏa EXISTS. `EXISTS` kiểm tra **có ít nhất một** hàng phù hợp, không nhân bản khách nếu họ có nhiều đơn.

### 12.2. Khách active không có bất kỳ đơn active nào

```sql
SELECT
    c.customer_id, c.full_name
FROM demo_soft_customers AS c
WHERE c.tenant_id = 10
  AND c.deleted_at IS NULL
  AND NOT EXISTS (
      SELECT 1
      FROM demo_soft_orders AS o
      WHERE o.tenant_id = c.tenant_id
        AND o.customer_id = c.customer_id
        AND o.deleted_at IS NULL
  )
ORDER BY c.customer_id;
-- Hoa (customer_id = 8).
```

Điều kiện `o.deleted_at IS NULL` phải nằm **bên trong EXISTS/NOT EXISTS** nếu yêu cầu chỉ xét đơn active. Nếu quên, khách 8 bị coi là “đã có đơn” vì đơn 1010 còn trong bảng dù đã xóa mềm.

### 12.3. Không tùy tiện dùng `NOT IN` với NULL

Nếu subquery dùng `NOT IN` và có thể trả NULL, ngữ nghĩa ba giá trị của SQL có thể khiến kết quả bất ngờ. Với yêu cầu “không tồn tại đơn active”, `NOT EXISTS` kèm khóa quan hệ rõ thường dễ kiểm soát hơn.

## 13. View để gom quy tắc đọc còn hiệu lực

Khi nhiều truy vấn phải viết:

```sql
WHERE tenant_id = :tenant_id
  AND deleted_at IS NULL
```

người lập trình có thể quên một điều kiện. Một giải pháp là tạo **view chỉ hiển thị active**, ví dụ PostgreSQL:

```sql
CREATE TEMP VIEW demo_active_customers AS
SELECT
    customer_id,
    tenant_id,
    email,
    full_name,
    created_at,
    updated_at
FROM demo_soft_customers
WHERE deleted_at IS NULL;
```

Truy vấn ứng dụng:

```sql
SELECT customer_id, full_name
FROM demo_active_customers
WHERE tenant_id = 10
ORDER BY customer_id;
```

View giúp tên đối tượng phản ánh **phạm vi dữ liệu**. Nhưng view **không tự áp dụng phân quyền tenant** nếu người dùng truy vấn mà thiếu tenant. Và nếu ứng dụng còn có quyền SELECT trực tiếp trên bảng gốc, nó vẫn có thể vô tình đọc bản ghi deleted.

### 13.1. View active không phải lịch sử bất biến

View là định nghĩa truy vấn đọc dữ liệu hiện tại. Khi hàng được xóa mềm hoặc khôi phục, kết quả view thay đổi. Nó không tự lưu **ai đã xóa** hoặc **một hàng từng active ở thời điểm trước**. Với các yêu cầu lịch sử, cần audit/event log hoặc temporal data được thiết kế riêng.

### 13.2. Tên view và các trường hợp quản trị

Có thể thiết kế rõ:

```text
active_customers   -> chỉ hàng active
deleted_customers  -> chỉ hàng đã xóa mềm, hạn chế quyền
customers           -> bảng gốc, không dùng trực tiếp cho nghiệp vụ thường ngày
```

Quyết định đặt quyền SELECT lên view, bảng, schema và vai trò cần dựa trên DBMS. Tránh tạo một view `all_customers` rồi cấp quyền rộng không cần thiết.

## 14. ORM và “default scope” không đủ làm rào chắn duy nhất

Nhiều ORM có cơ chế soft delete tích hợp, ví dụ tự thêm điều kiện active vào các truy vấn thông thường. Điều này tiện lợi nhưng có rủi ro:

- Raw SQL hoặc stored procedure có thể **bỏ qua scope**.
- JOIN/CTE phức tạp có thể chỉ lọc một số bảng, không lọc tất cả.
- Các thao tác quản trị cần **bao gồm deleted** có thể phải dùng chế độ đặc biệt.
- Truy vấn báo cáo tài chính có thể cần giữ lịch sử, không được tự ẩn mọi bản ghi deleted.
- Cache, search index và warehouse có thể không nhận được cập nhật trạng thái nếu thiếu đồng bộ.
- Bulk UPDATE có thể không chạy đầy đủ callbacks/hook mà ORM thường gọi theo từng entity.

Vì vậy:

1. Định nghĩa **chính sách read scope** ở một lớp dễ tái sử dụng.
2. Kiểm tra các truy vấn raw SQL, báo cáo, job nền, tìm kiếm.
3. Phân biệt đường truy cập **active**, **deleted** và **all with permission**.
4. Áp dụng **ràng buộc ở database** cho các bất biến quan trọng như uniqueness.
5. Không xem default scope là một cơ chế thay thế xác thực/ủy quyền.

Tên API của ORM thay đổi theo framework và phiên bản; nguyên lý SQL vẫn là **bộ lọc trạng thái phải nằm ở đúng tầng truy vấn**.

## 15. Tối ưu truy vấn active bằng partial/filtered index

Trong một hệ thống có hàng triệu bản ghi deleted nhưng phần lớn truy vấn chỉ lấy active, index có thể được thiết kế theo điều kiện.

PostgreSQL:

```sql
CREATE INDEX idx_demo_soft_active_customers_tenant
ON demo_soft_customers (tenant_id, customer_id)
WHERE deleted_at IS NULL;
```

Index này chỉ chứa những hàng thỏa predicate active. Nó có thể phục vụ:

```sql
SELECT customer_id, full_name
FROM demo_soft_customers
WHERE tenant_id = 10
  AND deleted_at IS NULL
ORDER BY customer_id;
```

Nhưng không được khẳng định bộ tối ưu **luôn sử dụng** index: với bảng nhỏ, sequential scan có thể rẻ hơn; với truy vấn không thể chứng minh predicate tương thích, index cũng có thể không được chọn.

### 15.1. Index cho order active

```sql
CREATE INDEX idx_demo_soft_active_orders_customer
ON demo_soft_orders (tenant_id, customer_id, order_id)
WHERE deleted_at IS NULL;
```

Index này phù hợp về mặt cấu trúc với truy vấn tìm đơn active theo tenant và customer. Tuy nhiên, lượng dữ liệu, tính chọn lọc, ORDER BY và thống kê quyết định kế hoạch thực sự.

### 15.2. Vì sao không đặt `deleted_at` ở mọi index một cách máy móc?

Một index thông thường:

```sql
CREATE INDEX idx_example ON customers (deleted_at, tenant_id);
```

không luôn tối ưu hơn partial index cho truy vấn active, và có thể làm tăng chi phí ghi/khối lượng lưu trữ. Phải xét các mẫu truy vấn chính: đọc active, đọc thùng rác, purge theo tuổi, lookup khóa, sort theo thời gian, tìm kiếm theo email.

### 15.3. EXPLAIN cho truy vấn active

```sql
EXPLAIN
SELECT customer_id, email
FROM demo_soft_customers
WHERE tenant_id = 10
  AND deleted_at IS NULL
ORDER BY customer_id;
```

Trong PostgreSQL, `EXPLAIN` cho **kế hoạch dự kiến**. Với môi trường kiểm thử phù hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, email
FROM demo_soft_customers
WHERE tenant_id = 10
  AND deleted_at IS NULL
ORDER BY customer_id;
```

`EXPLAIN ANALYZE` thực sự chạy truy vấn SELECT và báo số hàng/thời gian/buffer. Bảng demo chỉ có vài hàng, nên không đủ để đánh giá index trên hệ thống nhiều triệu bản ghi.

## 16. So sánh ràng buộc active-unique theo DBMS

**Yêu cầu chung:** không có hai khách **còn hiệu lực** với cùng email trong cùng tenant; khách deleted không chặn email mới, nhưng restore phải kiểm tra xung đột.

### 16.1. PostgreSQL: unique partial index

```sql
CREATE UNIQUE INDEX uq_customers_active_email
ON customers (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Đây là mẫu PostgreSQL phổ biến. Với email, `lower(email)` chỉ là ví dụ về quy tắc so sánh; các hệ có thể cần normalization/collation riêng và có những yêu cầu nghiệp vụ với domain email khác nhau.

### 16.2. SQL Server: unique filtered index

```sql
CREATE UNIQUE INDEX uq_customers_active_email
ON dbo.customers (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
```

SQL Server có **filtered index**; cú pháp trên giả định `normalized_email` được lưu hoặc tính hợp lệ theo schema của ứng dụng. Tính không phân biệt hoa/thường còn phụ thuộc collation hoặc cách chuẩn hóa. Không sao chép cú pháp `lower(email)` của expression index PostgreSQL sang SQL Server mà không xét yêu cầu indexed/computed columns.

### 16.3. SQLite: partial index

SQLite có partial indexes trong những phiên bản hỗ trợ:

```sql
CREATE UNIQUE INDEX uq_customers_active_email
ON customers (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

SQLite thường lưu timestamp theo biểu diễn chuỗi/số tùy schema; đảm bảo deleted_at thực sự có **NULL SQL** khi active, không phải chuỗi `'NULL'` hay `''`.

### 16.4. MySQL: generated column và UNIQUE

MySQL không hỗ trợ unique filtered index theo cùng cú pháp PostgreSQL. Một cách thường dùng là **generated column** trả NULL cho hàng deleted, cộng với UNIQUE index (vì UNIQUE của MySQL cho phép nhiều giá trị NULL phù hợp với mục đích):

```sql
-- MySQL 8.x, mẫu trên bảng và cột đã tồn tại.
ALTER TABLE customers
ADD COLUMN active_email VARCHAR(255)
    GENERATED ALWAYS AS (
        CASE
            WHEN deleted_at IS NULL THEN LOWER(email)
            ELSE NULL
        END
    ) STORED,
ADD UNIQUE KEY uq_customers_active_email (
    tenant_id, active_email
);
```

Khi active, `active_email` chứa email được chuẩn hóa. Khi deleted, nó là NULL và không chặn một email active khác. Mẫu này giả định `tenant_id NOT NULL` và email phù hợp độ dài/charset/collation của cột generated. Cần thử khi email dài, Unicode, charset, collation và phiên bản MySQL/MariaDB cụ thể.

### 16.5. Oracle: function-based unique index

Trên những phiên bản Oracle hỗ trợ kiểu biểu thức tương ứng, có thể dùng index trên biểu thức trả NULL cho hàng deleted:

```sql
CREATE UNIQUE INDEX uq_customers_active_email
ON customers (
    CASE WHEN deleted_at IS NULL THEN tenant_id END,
    CASE WHEN deleted_at IS NULL THEN LOWER(email) END
);
```

Mục đích là chỉ các hàng active tạo cặp khóa không NULL. Oracle có quy tắc riêng về chuỗi rỗng/NULL, collation và expression index; phải kiểm tra schema và phiên bản thực tế. Nếu một thành phần khóa có thể NULL, cần xác định semantics UNIQUE thay vì suy diễn từ PostgreSQL.

**Điểm không đổi giữa các hệ:** trạng thái active được biểu diễn bằng một điều kiện, còn ràng buộc **chỉ một khóa active** phải được thực thi ở database bằng cơ chế mà DBMS thực sự hỗ trợ.

## 17. Tranh chấp đồng thời: hai thao tác cùng một hàng

Giả sử hai request chạy gần nhau:

```text
Request A: DELETE mềm customer 2
Request B: RESTORE customer 2
```

Hoặc:

```text
Request A: RESTORE customer 4 (email an@example.com)
Request B: CREATE customer mới cùng email
```

Nếu logic chỉ là:

```text
SELECT kiểm tra không trùng
UPDATE/INSERT
```

thì **giữa SELECT và UPDATE/INSERT**, một transaction khác có thể thay đổi dữ liệu. Đây là lỗi *check-then-act race*.

### 17.1. Atomic UPDATE có điều kiện

PostgreSQL:

```sql
UPDATE demo_soft_customers
SET deleted_at = CURRENT_TIMESTAMP,
    deleted_by = 'staff-42',
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = 10
  AND customer_id = 2
  AND deleted_at IS NULL
RETURNING customer_id, deleted_at;
```

Câu UPDATE là một thao tác nguyên tử theo cơ chế transaction của database. Nếu hàng đã bị xóa mềm trước khi điều kiện được kiểm tra và câu lệnh thực thi, nó sẽ không bị cập nhật như một hàng active nữa. Ứng dụng phải kiểm tra **số hàng bị tác động**.

### 17.2. UNIQUE index là lớp bảo vệ cuối cùng

Hai request có thể cùng cho rằng email còn trống dựa trên các lần SELECT trước đó. **Unique index** mới là lớp database bảo vệ bất biến “không hai active cùng email” dưới concurrency thích hợp. Ứng dụng phải xử lý **unique-violation** thành phản hồi nghiệp vụ, không xem mọi lỗi là lỗi hệ thống không thể giải thích.

Với PostgreSQL, lỗi vi phạm unique thường có SQLSTATE **23505**. Khi bắt lỗi ở application, cần phân biệt chính xác index/constraint liên quan, không coi mọi lỗi 23505 là “email đã dùng”.

### 17.3. Optimistic locking bằng version

Một bảng thật có thể thêm:

```sql
version BIGINT NOT NULL DEFAULT 0
```

Khi cập nhật:

```sql
-- Mẫu dùng cột version trên bảng nghiệp vụ giả định.
UPDATE customers
SET deleted_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id
  AND deleted_at IS NULL
  AND version = :expected_version;
```

Nếu có 0 hàng cập nhật, ứng dụng kiểm tra liệu bản ghi đã bị xóa, version đã đổi, ID không tồn tại hay không được phép truy cập. Cơ chế version hữu ích khi người dùng mở form sửa, người khác xóa mềm trong lúc đó, và request sửa cũ không được phép ghi đè trạng thái mới.

### 17.4. Tránh update nhầm hàng archived

Một lệnh chỉnh tên:

```sql
UPDATE demo_soft_customers
SET full_name = 'Tên mới'
WHERE tenant_id = 10
  AND customer_id = 3;
```

có thể thay đổi **hàng đã xóa mềm**. Nếu nghiệp vụ chỉ cho sửa active, điều kiện cần có:

```sql
AND deleted_at IS NULL
```

Không chỉ SELECT cần lọc trạng thái; **UPDATE thông thường** cũng cần điều kiện active để tránh làm thay đổi dữ liệu archived ngoài ý muốn.

## 18. Khôi phục có điều kiện nghiệp vụ

Ngoài không trùng email, trước khi restore có thể cần kiểm tra:

- Bản ghi chưa vượt thời hạn cho phép khôi phục.
- Tenant và người thao tác còn quyền khôi phục.
- Tài khoản tổ chức/cha còn hiệu lực.
- Mã định danh, số điện thoại, username hoặc slug chưa được dùng lại.
- Trạng thái pháp lý không cấm khôi phục.
- Bản ghi có đủ tham chiếu cần thiết để sử dụng sau khi active.
- Không có sự kiện purge/ẩn danh hóa làm mất dữ liệu cần thiết.

Mẫu pseudo-workflow:

```text
BEGIN
  Lock hoặc cập nhật điều kiện trên bản ghi cần restore
  Kiểm tra tenant + quyền + thời hạn + trạng thái cha
  Kiểm tra các ràng buộc nghiệp vụ
  UPDATE deleted_at = NULL
  Để unique/FK/check constraint bảo vệ tính nhất quán
  Ghi audit trong transaction thích hợp
COMMIT

Nếu conflict: ROLLBACK và thông báo lý do phù hợp
```

### 18.1. Ràng buộc về thời gian khôi phục

Nếu chính sách cho khôi phục trong **30 ngày** từ lúc xóa:

```sql
UPDATE demo_soft_customers
SET deleted_at = NULL,
    deleted_by = NULL,
    delete_reason = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = 10
  AND customer_id = 3
  AND deleted_at IS NOT NULL
  AND deleted_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
RETURNING customer_id;
```

Đây là **mẫu điều kiện**. Dữ liệu mẫu ghi deleted_at tại tháng 10/2026, nên vào một ngày hiện tại khác kết quả phụ thuộc thời gian chạy. Nếu bài toán có khoảng chính xác theo UTC, cần xác định đơn vị “30 ngày” và timezone theo chính sách.

Không dùng `CURRENT_DATE - deleted_at` một cách tùy tiện khi nghiệp vụ nói **30 × 24 giờ**; ngày lịch và thời lượng thực có thể khác trong vùng có DST.

### 18.2. Không dùng điều kiện NULL theo cách sai

```sql
WHERE deleted_at != NULL
```

không có nghĩa “đang deleted”. Phải viết:

```sql
WHERE deleted_at IS NOT NULL
```

Với soft delete dựa trên timestamp, hai toán tử `IS NULL` và `IS NOT NULL` xuất hiện xuyên suốt các truy vấn đọc, xóa mềm và restore.

## 19. API và ngữ nghĩa trạng thái

Một dịch vụ có thể ánh xạ:

```text
GET    /customers          -> danh sách active
GET    /customers/{id}     -> một khách active
DELETE /customers/{id}     -> soft delete nếu được phép
POST   /customers/{id}/restore -> restore có điều kiện
GET    /customers/trash    -> danh sách deleted cho vai trò có quyền
```

Đây chỉ là mô hình minh họa, không phải giao thức bắt buộc.

### 19.1. GET một bản ghi đã xóa

Một query:

```sql
SELECT customer_id, full_name
FROM demo_soft_customers
WHERE tenant_id = 10
  AND customer_id = 3
  AND deleted_at IS NULL;
```

trả **0 hàng** vì khách 3 archived, dù hàng vẫn nằm trong database. API có thể trả **404** để không tiết lộ sự tồn tại của bản ghi đã ẩn, hoặc dùng **410 Gone** nếu hợp đồng và quyền truy cập cho phép công khai trạng thái deleted. Không nên tự suy luận rằng mọi API soft-delete bắt buộc phải trả cùng một HTTP status.

### 19.2. DELETE lặp lại

Nếu DELETE mềm lần thứ nhất thành công, request thứ hai có thể cập nhật 0 hàng do điều kiện active. Có API chọn phản hồi 204 theo nghĩa “đích đã không còn active”, có API phản hồi trạng thái khác. Quan trọng là **thao tác lặp không đổi thời điểm/actor của lần xóa đầu** và hành vi đã được tài liệu hóa.

### 19.3. Restore phải được xác thực riêng

Không biến endpoint restore thành “UPDATE deleted_at NULL với id bất kỳ” do người dùng cung cấp. Cần kiểm tra quyền, tenant, lifecycle, UNIQUE, audit và chính sách khôi phục dữ liệu nhạy cảm. Nếu không, một người dùng có thể khôi phục dữ liệu từng bị ẩn vì lý do quản trị.

## 20. Ghi nhật ký thay đổi và bảo toàn lịch sử

Soft delete giữ hàng hiện tại, nhưng **không tự lưu toàn bộ các lần đổi trạng thái**.

Giả sử hành trình:

```text
2026-10-01: CREATE customer 3
2026-10-09: SOFT_DELETE customer 3
2026-10-12: RESTORE customer 3
2026-11-02: SOFT_DELETE customer 3
```

Nếu chỉ lưu `deleted_at`, tại cuối kỳ bảng chỉ cho biết **lần xóa hiện tại** ngày 02/11. Hai lần chuyển trạng thái trước đó không còn ở hàng hiện tại.

### 20.1. Mô hình audit event

Một bảng riêng có thể ghi:

```text
customer_audit_events
  event_id
  tenant_id
  customer_id
  action           -- CREATED, SOFT_DELETED, RESTORED, UPDATED
  actor_id
  occurred_at
  request_id
  old_state
  new_state
  reason
```

Khi xóa mềm và ghi audit trong cùng transaction, có thể tránh trường hợp trạng thái đã đổi nhưng log nghiệp vụ không được ghi. Cần cân nhắc retention, bảo mật dữ liệu audit và quyền sửa/xóa log phù hợp; audit có thể chứa dữ liệu nhạy cảm và không được công khai cho mọi người đọc.

### 20.2. Audit và event sourcing khác nhau

Audit lưu **lịch sử thao tác** để truy nguyên; event sourcing dùng sự kiện làm nguồn xây dựng trạng thái theo một mô hình cụ thể. Một bảng `deleted_at` kết hợp audit không tự biến hệ thống thành event-sourced. Cũng không nên hứa có thể dựng trạng thái quá khứ chính xác nếu audit không ghi đủ mọi thay đổi có ảnh hưởng.

### 20.3. Không dùng deleted_at để tái tạo trạng thái mọi thời điểm

Một truy vấn “as of” như:

```sql
WHERE created_at <= :as_of
  AND (deleted_at IS NULL OR deleted_at > :as_of)
```

chỉ có thể gần đúng trong mô hình **không restore, không sửa lịch sử và cột created_at/deleted_at có ngữ nghĩa thích hợp**. Nếu một hàng đã deleted, được restore rồi deleted lại, một cột deleted_at duy nhất không chứa đủ lịch sử để biết hàng có hiệu lực vào mọi thời điểm trước đó.

Khi cần **historical as-of query** chính xác, hãy dùng versioned/temporal tables, nhật ký thay đổi đầy đủ hoặc mô hình `valid_from`/`valid_to` được thiết kế rõ, thay vì suy diễn từ trạng thái xóa mềm hiện tại.

## 21. Chỉ số báo cáo theo thời gian: đếm sai khi xem trạng thái hiện tại

Giả sử báo cáo hỏi:

> “Ngày 01/10 có bao nhiêu khách đang hoạt động?”

Nếu chạy hôm nay:

```sql
SELECT COUNT(*)
FROM customers
WHERE created_at <= TIMESTAMPTZ '2026-10-02 00:00:00+07'
  AND deleted_at IS NULL;
```

đó là “khách tạo trước mốc **và vẫn active tại thời điểm chạy truy vấn**”, không phải chắc chắn số khách active **tại 01/10**. Một khách active trong tháng 10 nhưng bị xóa vào tháng 11 sẽ bị loại khỏi query này.

Để báo cáo lịch sử đúng, hệ thống có thể cần:

- Snapshot số lượng active theo ngày;
- Bảng versioned lifecycle;
- Event log `CREATE/DELETE/RESTORE` đủ để dựng trạng thái;
- Temporal tables nếu DBMS hỗ trợ và cấu hình phù hợp.

Đừng để filter `deleted_at IS NULL` của **danh sách hiện tại** tự động áp vào mọi **báo cáo lịch sử**. Đây là một lỗi nghiệp vụ phổ biến khi tái sử dụng chung repository/ORM scope.

## 22. Tác động đến tìm kiếm, cache và hệ thống đồng bộ

Trong một hệ thống hiện đại, dữ liệu khách có thể tồn tại ngoài bảng SQL:

```text
Database (nguồn sự thật)
    |
    +--> Cache / Redis
    +--> Search index
    +--> Data warehouse
    +--> Event consumers / CRM / email service
```

Khi `deleted_at` đổi từ NULL sang timestamp, một SELECT mới tại DB có thể ẩn hàng đúng. Nhưng nếu cache chưa bị invalidated hoặc search index chưa cập nhật, người dùng vẫn có thể nhìn thấy thông tin cũ.

### 22.1. Phát sự kiện thay đổi trạng thái

Một kiến trúc có thể phát:

```text
CustomerSoftDeleted {
  tenant_id,
  customer_id,
  deleted_at,
  version
}

CustomerRestored {
  tenant_id,
  customer_id,
  restored_at,
  version
}
```

Consumer dùng version/idempotency để cập nhật search/cache đúng thứ tự. Nếu một sự kiện RESTORE đến sau DELETE nhưng do mạng lại được xử lý trước, không có version/checkpoint có thể khiến search index hiển thị trạng thái sai.

### 22.2. Soft delete và CDC tombstone

Trong change data capture (CDC), *tombstone* đôi khi biểu thị **xóa khóa khỏi một luồng/compact log**. Còn soft delete là **UPDATE cột** trong bảng SQL. Hai khái niệm không tự tương đương: một pipeline CDC có thể nhận UPDATE `deleted_at` chứ không nhận sự kiện DELETE vật lý. Cần quy tắc biến đổi CDC rõ nếu downstream muốn ẩn bản ghi theo soft delete.

### 22.3. Thông báo lỗi và dữ liệu nhạy cảm

Không gửi toàn bộ row archived, email hoặc lý do xóa trong message mà downstream không cần. Event nên có khóa và metadata cần thiết, được phân quyền và bảo vệ. “Giữ để khôi phục” không phải lý do cấp quyền đọc rộng rãi đối với dữ liệu nhạy cảm đã xóa mềm.

## 23. Hard delete, retention và xóa theo yêu cầu pháp lý

**Soft delete không phải xóa dữ liệu khỏi hệ thống.** Nếu một người yêu cầu xóa dữ liệu cá nhân theo chính sách hoặc nghĩa vụ pháp lý, việc chỉ đặt `deleted_at` vẫn để dữ liệu trong database, backup, cache, log hoặc warehouse. Soft delete **không tự đáp ứng** yêu cầu xóa/ẩn danh hóa thực sự.

Một hệ thống có thể phân biệt:

1. **Soft delete ngay:** người dùng không còn thấy/sử dụng hàng.
2. **Thời gian cho restore:** ví dụ thùng rác 30 ngày, nếu được phép.
3. **Purge/ẩn danh hóa:** sau thời hạn hoặc khi có căn cứ phù hợp, xóa vật lý hoặc thay đổi dữ liệu định danh theo chính sách.
4. **Xử lý bản sao:** cache, search, analytics, archive và backup theo lịch/khả năng khôi phục và nghĩa vụ lưu giữ.

### 23.1. Không xóa vật lý bừa bãi khi còn FK

Trong bộ dữ liệu mẫu, customer 3 có order 1004 trỏ đến. Vì FK còn hiệu lực, `DELETE FROM demo_soft_customers WHERE customer_id=3` có thể bị **ngăn** do có hàng con tham chiếu. Đây là hành vi bảo vệ tính toàn vẹn, không phải lỗi cần “tắt FK” ngay.

Khi purge, phải xác định:

- Có nên giữ giao dịch nhưng **ẩn danh hóa danh tính khách** không?
- Có được xóa các hàng con không?
- Có yêu cầu lưu chứng từ theo quy định không?
- Khóa nào cần giữ cho đối soát?
- Việc xóa có tác động tới bản sao dữ liệu và lịch sử audit không?

Không dùng `ON DELETE CASCADE` tràn lan để “dọn sạch” khi chưa hiểu ràng buộc nghiệp vụ.

### 23.2. Chọn hàng đủ hạn trước khi purge

PostgreSQL:

```sql
SELECT
    tenant_id,
    customer_id,
    deleted_at
FROM demo_soft_customers
WHERE deleted_at IS NOT NULL
  AND deleted_at < CURRENT_TIMESTAMP - INTERVAL '90 days'
ORDER BY deleted_at, customer_id;
```

Đây là bước **xem trước** danh sách đủ tuổi theo một chính sách giả định 90 ngày. Không nên tiếp tục DELETE vật lý trực tiếp chỉ dựa vào thời gian: cần kiểm tra legal hold, FK, backup, quyền và luồng phê duyệt. Những bước purge phải có audit và khả năng đối soát riêng.

### 23.3. Retention khác thời gian khôi phục

“Có thể restore trong 30 ngày” không nhất thiết là “dữ liệu sẽ bị xóa vật lý sau đúng 30 ngày”. Dữ liệu giao dịch có thể cần được lưu lâu hơn vì nghĩa vụ kế toán; ngược lại, một yêu cầu xóa hợp lệ có thể yêu cầu xử lý nhanh hơn theo quy định áp dụng. Hai thời hạn phải được xác định bởi chính sách và pháp luật liên quan, không suy diễn từ giao diện thùng rác.

## 24. Migration: thêm soft delete cho bảng đã tồn tại

Giả sử một ứng dụng trước đây chỉ có bảng:

```text
customers(customer_id, tenant_id, email, full_name)
```

Giờ muốn thêm soft delete. Một migration cần xét:

### 24.1. Thêm cột nullable

PostgreSQL:

```sql
ALTER TABLE customers
ADD COLUMN deleted_at TIMESTAMPTZ NULL;
```

Những hàng cũ nhận deleted_at NULL, theo quy ước đều còn hiệu lực. Đây là lựa chọn thường tự nhiên khi dữ liệu lịch sử trước đây được xem là active.

### 24.2. Chuyển đổi uniqueness

Nếu bảng có unique `(tenant_id,email)` trên **toàn bộ hàng**, thêm partial index **không tự bỏ unique cũ**. Khi vẫn giữ constraint cũ, email đã dùng bởi hàng deleted tiếp tục không thể tái sử dụng.

Cần một migration có kiểm soát:

1. Đánh giá dữ liệu và quy tắc email chuẩn hóa hiện tại.
2. Tạo unique index mới cho active theo cách phù hợp, kiểm tra xung đột.
3. Chuyển đổi/loại constraint toàn bảng **chỉ khi** không còn cần thiết theo nghiệp vụ.
4. Xem tác động với các FK, UPSERT/ON CONFLICT và câu SQL phụ thuộc constraint.
5. Có kế hoạch rollback và tránh khoảng thời gian không được database bảo vệ uniqueness.

Không drop unique cũ trước khi có bảo vệ thay thế nếu hệ thống đang ghi đồng thời. Cách rollout online còn tùy dung lượng, phiên bản và khả năng khóa của DBMS.

### 24.3. Cập nhật mọi đường đọc/ghi

Kiểm kê:

- SELECT danh sách/chi tiết/tìm kiếm.
- JOIN, báo cáo và dashboard.
- UPDATE và DELETE thường ngày.
- API quyền quản trị và restore.
- Cache, search, warehouse, export.
- Các job đồng bộ, email, gửi thông báo.
- Bản ghi con và quy tắc FK/cascade.

Một migration chỉ thêm `deleted_at` nhưng không cập nhật những truy vấn mặc định có thể khiến người dùng **vẫn nhìn thấy hàng đã xóa mềm**.

### 24.4. Quy trình rollout theo giai đoạn

Có thể triển khai:

```text
Schema mới (deleted_at)
       |
       v
Đường đọc active-aware
       |
       v
Đường ghi soft delete/restore
       |
       v
Ràng buộc uniqueness và quyền
       |
       v
Đồng bộ cache/index/report
       |
       v
Theo dõi số hàng và lỗi
```

Trình tự cụ thể phụ thuộc kiến trúc, yêu cầu zero downtime và khả năng deploy đồng thời các dịch vụ. Khi nhiều phiên bản ứng dụng chạy song song, cần tránh phiên bản cũ viết hard DELETE trong lúc phiên bản mới kỳ vọng soft delete.

## 25. Khả năng hỗ trợ và cú pháp theo hệ quản trị

Các nguyên tắc `UPDATE`, `IS NULL`, `IS NOT NULL`, transaction và JOIN xuất hiện rộng rãi trong SQL, nhưng tính năng tối ưu/ràng buộc khác nhau.

| DBMS | Kiểu thời gian thường dùng | Unique cho active | Ghi chú |
| --- | --- | --- | --- |
| **PostgreSQL** | `TIMESTAMPTZ` | Unique partial index `WHERE deleted_at IS NULL` | `UPDATE ... RETURNING`; partial index; `FILTER` trong aggregate |
| **SQL Server** | `datetime2`/`datetimeoffset` | Unique filtered index | `UPDATE ... OUTPUT` thay cho RETURNING; cú pháp ngày/giờ khác |
| **MySQL 8.x** | `DATETIME`/`TIMESTAMP` | Thường dùng generated column + UNIQUE | Không có filtered index theo đúng cú pháp PostgreSQL; `CURRENT_TIMESTAMP` và timezone cần lưu ý |
| **SQLite** | TEXT/REAL/INTEGER theo quy ước | Partial index ở phiên bản hỗ trợ | `RETURNING` ở các phiên bản mới; cách lưu ngày/giờ do schema quy định |
| **Oracle Database** | `TIMESTAMP WITH TIME ZONE` hoặc các kiểu liên quan | Có thể dùng function-based unique index | Kiểu chuỗi rỗng/NULL và thao tác trả hàng cập nhật có cú pháp riêng |

### 25.1. SQL Server soft delete và restore

Ví dụ T-SQL trên bảng `dbo.customers` giả định:

```sql
UPDATE dbo.customers
SET deleted_at = SYSUTCDATETIME(),
    deleted_by = @actor_id
OUTPUT INSERTED.customer_id, INSERTED.deleted_at
WHERE tenant_id = @tenant_id
  AND customer_id = @customer_id
  AND deleted_at IS NULL;
```

`OUTPUT INSERTED` là cơ chế lấy các giá trị sau UPDATE trong T-SQL. Không sao chép nguyên `RETURNING` của PostgreSQL sang SQL Server.

Khôi phục:

```sql
UPDATE dbo.customers
SET deleted_at = NULL,
    deleted_by = NULL
WHERE tenant_id = @tenant_id
  AND customer_id = @customer_id
  AND deleted_at IS NOT NULL;
```

Việc thành công vẫn phụ thuộc unique filtered index và các điều kiện nghiệp vụ.

### 25.2. MySQL soft delete

Trên MySQL 8.x:

```sql
UPDATE customers
SET deleted_at = CURRENT_TIMESTAMP,
    deleted_by = ?
WHERE tenant_id = ?
  AND customer_id = ?
  AND deleted_at IS NULL;
```

Placeholder `?` chỉ là dạng thường dùng trong prepared statements qua driver; ứng dụng không nên nối chuỗi ID trực tiếp vào SQL. Với cột `TIMESTAMP`/`DATETIME`, cần thống nhất lưu UTC và cách diễn giải timezone. Đừng giả định MySQL hỗ trợ `UPDATE ... RETURNING` giống PostgreSQL.

### 25.3. SQLite soft delete

Nếu deleted_at được lưu theo chuỗi thời gian ISO 8601:

```sql
UPDATE customers
SET deleted_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE customer_id = ?
  AND deleted_at IS NULL;
```

Đây là mẫu SQLite, không phải kiểu `TIMESTAMPTZ` của PostgreSQL. Phải dùng một quy ước biểu diễn nhất quán để so sánh thời gian và tránh coi chuỗi `'NULL'` là SQL NULL.

### 25.4. Oracle và các hệ hỗ trợ temporal/history

Oracle có cơ chế timestamp/flashback và các lựa chọn lịch sử tùy phiên bản; SQL Server có system-versioned temporal tables trong môi trường hỗ trợ. Chúng có thể phục vụ yêu cầu **truy vấn trạng thái quá khứ**, nhưng **không tự thay thế soft delete mặc định** và cũng không làm mất nhu cầu định nghĩa active filter. Nếu dùng cả temporal và soft delete, phải hiểu trạng thái hiện tại khác với trạng thái tại `AS OF` và cấu hình retention/history.

## 26. Những lỗi thường gặp khi thiết kế soft delete

| Lỗi hoặc ngộ nhận | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| `WHERE deleted_at = NULL` | So sánh với NULL bằng `=` không ra TRUE | Dùng `IS NULL` |
| `WHERE deleted_at != NULL` để lấy thùng rác | Không phải phép thử khác NULL | Dùng `IS NOT NULL` |
| Quên WHERE khi UPDATE soft delete | Đánh dấu toàn bộ bảng | Khóa + tenant + trạng thái trong WHERE, kiểm tra row count |
| Chỉ lọc customer active nhưng không lọc order active | Hiển thị đơn đã xóa mềm | Định nghĩa trạng thái của từng bảng |
| Đặt `o.deleted_at IS NULL` trong WHERE sau LEFT JOIN | Khách chỉ có đơn deleted có thể biến mất | Đặt predicate của hàng con vào ON |
| Dùng COUNT(*) sau LEFT JOIN để đếm đơn | Hàng bù NULL vẫn được đếm | COUNT(o.order_id) |
| Dùng UNIQUE(tenant,email,deleted_at) để bảo vệ một email active | NULL trong UNIQUE có semantics đặc thù | Dùng partial/filtered/generated index đúng |
| Khôi phục chắc chắn thành công vì hàng còn trong bảng | Có thể xung đột email, mã hoặc workflow | Kiểm tra constraint và xử lý conflict |
| Khôi phục mọi hàng con khi restore cha | Có thể phục hồi dữ liệu bị xóa độc lập | Dùng metadata/cascade batch và chính sách |
| FK ON DELETE CASCADE sẽ soft delete con | Soft delete là UPDATE, không phải DELETE | Thiết kế cascade riêng nếu cần |
| Soft delete tự ngăn tạo con cho cha archived | FK chỉ kiểm tra hàng cha tồn tại | Kiểm tra active trong luồng tạo con |
| Ràng buộc active chỉ cần kiểm tra SELECT trước INSERT | Race condition giữa nhiều transaction | Unique index bảo vệ invariant |
| ORM default scope là cơ chế phân quyền đầy đủ | Raw SQL/job khác có thể bỏ scope | Quyền server/DB, tenant filtering, audit |
| Báo cáo tài chính phải bỏ đơn của khách deleted | Trạng thái CRM khác trạng thái ghi nhận doanh thu | Định nghĩa KPI và retention riêng |
| `deleted_at` cho biết toàn bộ lịch sử trạng thái | Restore ghi đè trạng thái trước | Audit/temporal model |
| Soft delete nghĩa là dữ liệu đã bị xóa theo luật | Bytes vẫn trong DB và bản sao | Quy trình purge/ẩn danh hóa phù hợp |
| Chỉ cập nhật DB là đủ | Cache/search/warehouse có thể còn dữ liệu cũ | Đồng bộ sự kiện và invalidation |
| Tạo index deleted_at luôn tốt nhất | Phụ thuộc truy vấn, phân bố và engine | Đo plan bằng EXPLAIN |
| Mọi bản ghi có deleted_at NULL đều “hợp lệ” | Có thể có trạng thái đình chỉ/hết hạn khác | Kết hợp điều kiện nghiệp vụ cần thiết |
| Khôi phục nghĩa là làm phát sinh lại mọi tác vụ cũ | Có thể dẫn đến gửi lại email/đơn/giao dịch | Định nghĩa side effects của restore |
| “Thùng rác 30 ngày” đồng nghĩa “purge sau 30 ngày” | Retention và restore có thể khác | Quy định chính sách rõ |

## 27. Bài tập thực hành

Các bài sử dụng hai bảng `demo_soft_customers` và `demo_soft_orders` đã tạo ở mục 3. Các thao tác sửa trạng thái nên được thử trong **transaction kết thúc bằng ROLLBACK** để giữ bộ dữ liệu phục vụ những bài tiếp theo.

### Bài 1 — Lọc khách còn hiệu lực

Viết truy vấn lấy `customer_id`, `full_name`, `email` của tenant 10 với `deleted_at IS NULL`. Vì sao có **4 hàng**? Sau đó viết truy vấn thùng rác (`IS NOT NULL`) và xác nhận có **3 hàng**.

### Bài 2 — Vì sao `= NULL` sai?

So sánh:

```sql
WHERE deleted_at = NULL
```

với:

```sql
WHERE deleted_at IS NULL
```

Hãy giải thích SQL ba giá trị TRUE/FALSE/UNKNOWN làm hai điều kiện khác nhau thế nào.

### Bài 3 — Xóa mềm có kiểm soát

Trong transaction, xóa mềm khách 2 bằng UPDATE với các cột `deleted_at`, `deleted_by`, `delete_reason`, `updated_at`, điều kiện tenant và trạng thái active. Dùng `RETURNING` kiểm tra hàng cập nhật. Sau đó chạy lại cùng UPDATE: vì sao lần hai thường tác động **0 hàng**?

### Bài 4 — Khôi phục khách Chi

Trong transaction, restore khách 3 bằng `deleted_at = NULL`, chỉ khi đang deleted. Số khách active ở tenant 10 đổi từ **4 thành 5** trong transaction. Dùng `ROLLBACK` để trở về 4.

### Bài 5 — Khôi phục xung đột email

Vì sao restore khách 4 sẽ xung đột unique partial index, dù khách 4 vẫn tồn tại vật lý? Nêu hai phương án xử lý hợp lệ và giải thích vì sao không nên tắt UNIQUE để “chạy được”.

### Bài 6 — Đếm khách active/deleted

Viết một truy vấn dùng conditional aggregation hoặc `FILTER` (PostgreSQL) trả `all_customers = 7`, `active_customers = 4`, `deleted_customers = 3` cho tenant 10. Phân biệt tổng hàng vật lý và tổng active.

### Bài 7 — LEFT JOIN với khách chỉ có đơn deleted

LEFT JOIN customer với order, lọc customer active trong WHERE và order active **trong ON**, GROUP BY khách rồi `COUNT(o.order_id)`. Vì sao khách Hoa vẫn xuất hiện với **0 đơn active**?

### Bài 8 — Đặt predicate sai vị trí

Chuyển `o.deleted_at IS NULL` từ ON xuống WHERE của truy vấn bài 7. Khách Hoa còn xuất hiện không? Vì sao SQL không tự tạo lại một hàng con NULL sau WHERE?

### Bài 9 — Doanh thu nào được tính?

Viết hai truy vấn:

1. Tổng PAID của **đơn chưa soft-delete** trong tenant 10, không yêu cầu customer active.
2. Tổng PAID của **đơn chưa soft-delete thuộc khách active** trong tenant 10.

Kết quả tương ứng **610.00** và **470.00**. Giải thích hai con số trả lời những yêu cầu nghiệp vụ khác nhau.

### Bài 10 — EXISTS và NOT EXISTS

Liệt kê khách active có ít nhất một đơn active bằng EXISTS. Sau đó liệt kê khách active **không có đơn active** bằng NOT EXISTS. Khách Hoa thuộc tập nào? Nếu quên lọc trạng thái order trong subquery, kết quả thay đổi ra sao?

### Bài 11 — FK và cascade

Khách 3 đang soft deleted nhưng order 1004 còn active. FK có vi phạm không? Nếu FK được khai báo `ON DELETE CASCADE`, soft delete khách 3 có tự soft delete order 1004 không? Hãy giải thích vì sao.

### Bài 12 — Restore con theo batch

Một khách có hai ghi chú: ghi chú A bị xóa riêng hôm trước, ghi chú B bị soft delete khi xóa khách. Khi restore khách, nên restore cả A và B hay chỉ B? Thiết kế metadata để nhận diện ghi chú nào thuộc thao tác cascade.

### Bài 13 — Partial index và filtered index

Viết index unique `(tenant_id, lower(email)) WHERE deleted_at IS NULL` trong PostgreSQL. Nêu công cụ tương tự ở SQL Server, giải pháp generated column cho MySQL, và vì sao UNIQUE có cột `deleted_at` nullable không đủ.

### Bài 14 — Quy tắc nhiều tenant

Khách 1 ở tenant 10 và khách 5 ở tenant 20 cùng email `an@example.com`. Có cần chặn không nếu unique chỉ trong tenant? Nếu request restore/soft delete gửi customer_id nhưng quên điều kiện tenant, có rủi ro gì?

### Bài 15 — UPDATE khách active

Viết lệnh đổi tên khách 2 với điều kiện `tenant_id`, `customer_id` và `deleted_at IS NULL`. Nếu người khác vừa soft delete khách này, vì sao request sửa không nên tiếp tục cập nhật một hàng đã archived?

### Bài 16 — Khôi phục theo hạn

Thiết kế câu UPDATE chỉ restore khách đã xóa mềm trong **30 ngày gần nhất**. Nêu lý do cần timestamp phù hợp timezone và điều kiện `deleted_at IS NOT NULL`. Nếu unique email xung đột thì sao?

### Bài 17 — Báo cáo tại thời điểm lịch sử

Một khách active ngày 01/10 nhưng bị soft delete ngày 01/11, và sau đó được restore ngày 10/11. Dùng cột deleted_at hiện tại có đủ để biết họ active vào ngày 05/11 không? Đề xuất audit event/temporal model để trả lời.

### Bài 18 — Cache và search index

DB đã đặt deleted_at nhưng search engine vẫn trả hồ sơ cũ. Những bước đồng bộ/invalidation nào cần có? Nếu sự kiện restore và delete đến consumer sai thứ tự, dùng version để xử lý thế nào?

### Bài 19 — Retention và hard delete

Một hồ sơ đã soft deleted hơn 90 ngày nhưng vẫn có đơn hàng liên quan. Hãy lập danh sách điều kiện kiểm tra trước khi purge: legal hold, FK, lưu trữ, ẩn danh hóa, backup và audit. Vì sao không thể luôn chạy `DELETE FROM customers WHERE deleted_at < ...`?

### Bài 20 — Thiết kế hệ thống hoàn chỉnh

Một ứng dụng nhiều tenant có khách hàng, đơn hàng và danh mục sản phẩm. Khách có thể bị ẩn và restore, đơn PAID cần đối soát lịch sử, sản phẩm archived không được đặt mua mới. Hãy thiết kế:

1. Các cột trạng thái nào phù hợp từng bảng?
2. Điều kiện active trong `SELECT`, `JOIN`, `UPDATE`, `INSERT` và API?
3. Unique key nào chỉ áp dụng cho hàng active?
4. Dữ liệu con nào bị soft delete theo cha, dữ liệu nào phải giữ?
5. Chính sách restore, audit, concurrency và purge?

Giải thích vì sao không thể xử lý toàn bộ nghiệp vụ chỉ bằng một câu `WHERE deleted_at IS NULL` đặt ở cuối mọi truy vấn.

## 28. Mẫu tư duy khi triển khai

```text
                  BẢN GHI HIỆN TẠI
                         |
                         v
                  Người dùng yêu cầu
                    "Xóa" hoặc "Ẩn"
                         |
                         v
              Xác thực + quyền + tenant
                         |
                         v
                UPDATE có điều kiện
              WHERE deleted_at IS NULL
                         |
                         v
                 deleted_at khác NULL
                         |
             +-----------+-----------+
             |                       |
             v                       v
     READ thường ngày          READ quản trị/thùng rác
     deleted_at IS NULL        deleted_at IS NOT NULL
             |                       |
             v                       v
      Không thấy bản ghi       Được xem nếu có quyền
                                     |
                                     v
                           Yêu cầu khôi phục?
                                     |
                                     v
                         Kiểm tra trạng thái, quyền,
                         unique, FK và policy
                                     |
                         +-----------+-----------+
                         |                       |
                       Hợp lệ                 Xung đột
                         |                       |
                         v                       v
                  UPDATE deleted_at=NULL    Từ chối/giải quyết
                         |
                         v
                      Audit + sync

        Đến kỳ retention/purge:
        đánh giá policy + dữ liệu con + bản sao,
        không nhầm soft delete với hard delete.
```

### 28.1. Ba câu hỏi trước mỗi truy vấn

Khi viết SQL liên quan soft delete, nên tự hỏi:

1. **Một hàng của bảng này còn hiệu lực nghĩa là gì?** Chỉ `deleted_at IS NULL`, hay còn cần status, effective dates, tenant, quyền?
2. **Các bảng được JOIN có phải cùng chịu quy tắc ấy không?** Đơn lịch sử có được giữ khi customer archived không? Nếu LEFT JOIN, điều kiện hàng con nằm ở ON hay WHERE?
3. **Mục tiêu là hiện tại hay lịch sử?** Danh sách active hôm nay, báo cáo giao dịch đã ghi nhận, hay trạng thái tại một ngày quá khứ?

Ba câu hỏi này giúp tránh lỗi “lọc quá ít” làm lộ dữ liệu deleted và “lọc quá nhiều” làm sai báo cáo.

## 29. Kết luận

**Xóa mềm** dùng `UPDATE` đánh dấu bản ghi không còn hiệu lực, phổ biến nhất qua `deleted_at`. **Khôi phục** chuyển hàng về active bằng `deleted_at = NULL`, nhưng chỉ khi quyền, trạng thái, unique key và các ràng buộc nghiệp vụ còn cho phép. Việc hàng vẫn tồn tại trong bảng không chứng minh nó hợp lệ để được hiển thị, chỉnh sửa hoặc tái sử dụng.

Truy vấn active cần **`deleted_at IS NULL` đúng vị trí và đúng bảng**; thùng rác cần `IS NOT NULL`. Với `LEFT JOIN`, đặt bộ lọc hàng con trong `ON` nếu phải giữ mọi hàng cha. Khóa ngoại không tự cascade soft delete; unique key cho dữ liệu active thường cần partial/filtered index hoặc cơ chế tương đương theo hệ quản trị. Transaction, update có điều kiện, kiểm soát concurrency và audit giúp thao tác có thể dự đoán được.

Cuối cùng, **soft delete không thay thế xóa vật lý, lưu lịch sử, phân quyền hay nghĩa vụ bảo vệ dữ liệu**. Một thiết kế SQL đáng tin phải nói rõ bản ghi nào **còn hiệu lực**, khi nào được **khôi phục**, dữ liệu liên quan nào **tiếp tục được sử dụng**, và dữ liệu nào cuối cùng cần **ẩn danh hóa hoặc loại bỏ theo chính sách**. Khi những quy tắc ấy nhất quán từ bảng, truy vấn, API đến hệ thống đồng bộ, soft delete mới thực sự trở thành một cơ chế vận hành an toàn thay vì chỉ là một cột timestamp.
