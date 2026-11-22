# Chỉ mục biểu thức và yêu cầu đối với hàm trong PostgreSQL

Trong ứng dụng PostgreSQL, không phải truy vấn nào cũng lọc theo giá trị nguyên vẹn của một cột. Một hệ thống đăng nhập muốn tìm email **không phân biệt chữ hoa/thường**; hệ thống bán hàng muốn lọc các dòng có **thành tiền = đơn giá × số lượng**; hệ thống sự kiện muốn truy cập một trường nằm bên trong `jsonb`. Khi điều kiện lọc viết dưới dạng `lower(email)`, `unit_price * quantity` hay `payload ->> 'customer_id'`, index B-tree trên cột gốc không nhất thiết giúp PostgreSQL tìm dữ liệu theo đúng biểu thức ấy.

**Chỉ mục biểu thức** (*expression index* hay *functional index*) cho phép lưu giá trị được **tính từ cột** trong một index. Thay vì chỉ đánh chỉ mục cho `email`, ta có thể đánh chỉ mục cho **`lower(email)`**; thay vì chỉ đánh chỉ mục cho `unit_price` và `quantity` riêng rẽ, ta có thể đánh chỉ mục cho **`(unit_price * quantity)`**.

Nhưng PostgreSQL đặt một yêu cầu căn bản: **mọi hàm và toán tử được dùng để tính khóa chỉ mục phải có tính bất biến phù hợp (`IMMUTABLE`)**. Một biểu thức phụ thuộc thời gian hiện tại, timezone của session, dữ liệu bảng khác, cấu hình có thể thay đổi hay một hàm được đánh dấu `STABLE`/`VOLATILE` sẽ không phù hợp để lưu làm khóa index theo cách thông thường.

Bài học này giải thích cả **cách tạo**, **cách PostgreSQL dùng** và **cách bảo trì** chỉ mục biểu thức, đặc biệt tập trung vào tính đúng đắn của hàm, không chỉ tốc độ truy vấn.

## 1. Mục tiêu

Hoàn thành bài này, bạn có thể:

1. Phân biệt chỉ mục cột thông thường với chỉ mục trên **biểu thức tính từ một hay nhiều cột**.
2. Viết `CREATE INDEX ... ON table (lower(column))` và `CREATE INDEX ... ON table ((a * b))` đúng cú pháp.
3. Dùng chỉ mục biểu thức để tăng tốc tìm kiếm, sắp xếp và ràng buộc uniqueness theo giá trị chuẩn hóa.
4. Hiểu chính xác ba nhãn volatility của PostgreSQL: **`IMMUTABLE`, `STABLE` và `VOLATILE`**.
5. Nhận biết vì sao `now()`, `random()` hoặc một số phép chuyển `timestamptz` sang ngày không thể dùng trực tiếp làm khóa index.
6. Kiểm tra volatility thực tế từ `pg_proc` theo **chữ ký hàm**, không chỉ tên hàm.
7. Tạo hàm SQL tự viết có khai báo `IMMUTABLE` một cách có trách nhiệm; hiểu hậu quả nếu gắn nhãn sai hoặc thay đổi logic hàm.
8. Dùng **partial expression index**, **unique expression index**, chọn expression index hay generated column/column thường.
9. Đọc `EXPLAIN` và các catalog để biết index có hợp lệ, được sử dụng hay không.
10. Hiểu chi phí lúc `INSERT`/`UPDATE`, ảnh hưởng đến HOT update, collation/timezone, `REINDEX` và triển khai đồng thời.

## 2. Mô hình tư duy: index lưu “kết quả” của biểu thức

Chỉ mục B-tree thông thường:

~~~sql
CREATE INDEX idx_users_email ON users (email);
~~~

về mặt ý tưởng lưu các khóa dựa trên `email`:

~~~text
Index key                 Row reference
---------------------------------------
Anh@Example.com          → user 1
binh@example.com         → user 2
chi@example.org          → user 3
~~~

Chỉ mục biểu thức:

~~~sql
CREATE INDEX idx_users_lower_email
ON users (lower(email));
~~~

lưu kết quả đã được tính:

~~~text
Index key                 Row reference
---------------------------------------
anh@example.com          → user 1
binh@example.com         → user 2
chi@example.org          → user 3
~~~

Khi truy vấn:

~~~sql
SELECT *
FROM users
WHERE lower(email) = 'anh@example.com';
~~~

PostgreSQL có thể tìm khóa `anh@example.com` trong expression index thay vì tính `lower(email)` cho từng hàng trong một sequential scan.

~~~mermaid
flowchart TD
    A["INSERT / UPDATE row"] --> B["Đánh giá lower(email)"]
    B --> C["Ghi giá trị biểu thức vào index"]
    D["SELECT ... WHERE lower(email) = ?"] --> E["Planner xem biểu thức và thống kê"]
    E --> F{"Index có lợi không?"}
    F -->|Có| G["Index Scan / Bitmap Index Scan"]
    F -->|Không| H["Sequential Scan"]
    G --> I["Trả hàng thỏa điều kiện"]
    H --> I
~~~

**Điểm đánh đổi:** kết quả biểu thức được tính và duy trì **khi ghi**, nhờ đó có thể tránh tính lặp cho mọi hàng khi **đọc**. Index không miễn phí: nó chiếm đĩa, tăng công việc ghi và cần nhất quán với logic hàm.

### 2.1. Khi nào cần index biểu thức?

Những tình huống thường gặp:

| Điều kiện nghiệp vụ | Biểu thức có thể index |
| --- | --- |
| Email không phân biệt hoa/thường | `lower(email)` |
| Email loại khoảng trắng hai đầu và chuẩn hóa chữ | `lower(btrim(email))` |
| Tên tìm kiếm không phân biệt hoa/thường | `lower(display_name)` |
| Thành tiền một dòng đơn hàng | `(unit_price * quantity)` |
| Mã khách lấy từ JSONB | `(payload ->> 'customer_id')` |
| Giá trị âm/dương theo biến đổi | `abs(balance)` nếu đúng ngữ nghĩa |
| Ngày từ timestamp **không timezone** | `created_local::date` hoặc `date_trunc('day', created_local)` với overload phù hợp |

Không phải cứ có hàm trong `WHERE` thì phải tạo expression index. Cần xem số lượng hàng, tính chọn lọc, tần suất truy vấn, chi phí ghi và cách có thể viết lại truy vấn để dùng index cột gốc.

## 3. Bộ dữ liệu thực hành

Các ví dụ sẽ dùng schema `expr_idx_256` trong **database lab riêng**. Nếu schema đã tồn tại, dùng tên khác thay vì xóa dữ liệu cũ.

### 3.1. Bảng khách hàng

~~~sql
CREATE SCHEMA expr_idx_256;

CREATE TABLE expr_idx_256.customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO expr_idx_256.customers
    (customer_id, email, display_name, deleted_at)
VALUES
    (1, 'Anh@Example.com',     'Anh Nguyễn', NULL),
    (2, 'binh@example.com',    'Bình Lê',    NULL),
    (3, 'CHI@sample.org',      'Chi Phạm',   NULL),
    (4, 'duong@example.com',   'Dương Trần', NULL),
    (5, 'user@legacy.test',    'Tài khoản cũ',
        TIMESTAMPTZ '2026-01-01 00:00:00+07'),
    (6, 'old@EXAMPLE.com',     'Đã xóa',
        TIMESTAMPTZ '2026-02-01 00:00:00+07');
~~~

Ở đây `deleted_at IS NULL` nghĩa là tài khoản đang hoạt động; giá trị không NULL dùng cho soft-delete.

### 3.2. Bảng dòng hàng

~~~sql
CREATE TABLE expr_idx_256.order_lines (
    line_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    quantity INTEGER NOT NULL
        CHECK (quantity > 0),
    created_local TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

INSERT INTO expr_idx_256.order_lines
    (line_id, order_id, sku, unit_price, quantity, created_local)
VALUES
    (1, 1001, 'BOOK-01', 100000, 1,
        TIMESTAMP '2026-11-12 09:10:00'),
    (2, 1001, 'PEN-01',   10000, 4,
        TIMESTAMP '2026-11-12 09:10:00'),
    (3, 1002, 'MOUSE-01', 250000, 2,
        TIMESTAMP '2026-11-13 16:20:00'),
    (4, 1003, 'BOOK-01', 100000, 3,
        TIMESTAMP '2026-11-14 08:00:00'),
    (5, 1004, 'BAG-01',  450000, 1,
        TIMESTAMP '2026-11-14 09:30:00'),
    (6, 1005, 'CABLE-01', 90000, 2,
        TIMESTAMP '2026-11-14 10:15:00');
~~~

`created_local` được đặt tên cụ thể để nhắc rằng đây là **timestamp không có timezone**. Không nên dùng loại này cho mọi thời điểm nghiệp vụ cần biểu diễn một instant toàn cầu; trong hệ thống phân tán, `timestamptz` thường phù hợp hơn cho những thời điểm có ý nghĩa tuyệt đối.

### 3.3. Bảng sự kiện JSONB

~~~sql
CREATE TABLE expr_idx_256.events (
    event_id BIGINT PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);

INSERT INTO expr_idx_256.events
    (event_id, event_type, payload, occurred_at)
VALUES
    (1, 'purchase',
        '{"customer_id":"1","channel":"web"}'::jsonb,
        TIMESTAMPTZ '2026-11-12 09:00:00+07'),
    (2, 'login',
        '{"customer_id":"2","channel":"mobile"}'::jsonb,
        TIMESTAMPTZ '2026-11-13 09:00:00+07'),
    (3, 'purchase',
        '{"customer_id":"1","channel":"mobile"}'::jsonb,
        TIMESTAMPTZ '2026-11-14 08:00:00+07'),
    (4, 'logout',
        '{"customer_id":"3","channel":"web"}'::jsonb,
        TIMESTAMPTZ '2026-11-14 08:30:00+07');
~~~

### 3.4. Lưu ý về kích thước bảng mẫu

Bảng lab chỉ vài hàng để người học dễ xác nhận kết quả. PostgreSQL có thể ưu tiên **Seq Scan** vì rẻ hơn đọc index + heap, ngay cả khi chỉ mục đúng và đủ điều kiện. **Việc `EXPLAIN` trả Seq Scan trên bảng nhỏ không có nghĩa chỉ mục biểu thức vô hiệu.**

## 4. Ví dụ cơ bản: index trên lower(email)

### 4.1. Truy vấn chưa có expression index

~~~sql
SELECT
    customer_id,
    email,
    display_name
FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';
~~~

Kết quả là khách hàng `customer_id=1`.

Nếu chỉ có index B-tree thông thường trên `email`, truy vấn chứa `lower(email)` **không nhất thiết** dùng được index đó để tra theo khóa đã lower. Giá trị của index cột gốc và giá trị trong predicate là hai biểu thức khác nhau.

### 4.2. Tạo chỉ mục biểu thức

~~~sql
CREATE INDEX idx_customers_lower_email_256
ON expr_idx_256.customers (lower(email));
~~~

Trong cú pháp PostgreSQL, biểu thức là một **lời gọi hàm** như `lower(email)` có thể dùng ngay giữa danh sách khóa index mà không cần thêm cặp ngoặc bao ngoài. Với biểu thức phức tạp hơn, thường phải bao nó trong ngoặc.

### 4.3. Truy vấn khớp biểu thức index

~~~sql
SELECT
    customer_id,
    email
FROM expr_idx_256.customers
WHERE lower(email) = lower('ANH@EXAMPLE.COM');
~~~

PostgreSQL có thể dùng `idx_customers_lower_email_256`. Giá trị ở vế phải được tính từ hằng số; biểu thức ở vế trái khớp với khóa được lưu trong index.

### 4.4. Dùng EXPLAIN

~~~sql
EXPLAIN
SELECT customer_id, email
FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';
~~~

Trên bảng nhỏ, plan có thể vẫn là `Seq Scan`. Để xem dạng index plan trong **môi trường lab** và hiểu khả năng truy cập, có thể tạm vô hiệu hóa planner chọn sequential scan cho session/transaction:

~~~sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN
SELECT customer_id, email
FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';

ROLLBACK;
~~~

**Đây chỉ là thao tác minh họa planner.** `enable_seqscan=off` không xóa hoàn toàn mọi khả năng Seq Scan và **không nên dùng làm “tối ưu production”**; nó làm lệch lựa chọn chi phí thông thường.

### 4.5. Query phải diễn đạt điều kiện tương thích

Chỉ mục:

~~~sql
ON expr_idx_256.customers (lower(email))
~~~

phù hợp với dạng:

~~~sql
WHERE lower(email) = 'anh@example.com'
~~~

nhưng không nên mặc định nó hỗ trợ như nhau cho:

~~~sql
WHERE email = 'anh@example.com'
~~~

hoặc:

~~~sql
WHERE email ILIKE 'anh@example.com'
~~~

Planner không có nghĩa vụ chứng minh **mọi phép biến đổi logic có vẻ tương đương** và tự ánh xạ chúng về `lower(email)`. Đặc biệt, `ILIKE` là toán tử pattern matching với những quy tắc riêng, không phải phép bằng `lower(email)`. Nếu API quy định tìm theo chuẩn hóa email, tốt nhất thống nhất **biểu thức trong query** và **biểu thức trong index**.

## 5. Biểu thức số học: index trên (unit_price * quantity)

### 5.1. Vì sao hai index riêng không thay biểu thức?

Giả sử truy vấn thường xuyên lọc dòng đơn hàng có thành tiền lớn:

~~~sql
SELECT
    line_id,
    order_id,
    sku,
    unit_price,
    quantity,
    unit_price * quantity AS line_total
FROM expr_idx_256.order_lines
WHERE unit_price * quantity >= 300000
ORDER BY line_id;
~~~

Kết quả dự kiến:

| line_id | SKU | Thành tiền |
| ---: | --- | ---: |
| 3 | MOUSE-01 | 500.000 |
| 4 | BOOK-01 | 300.000 |
| 5 | BAG-01 | 450.000 |

Index trên `unit_price` riêng và `quantity` riêng không tự lưu **tích của hai cột** để tra theo ngưỡng `300000`.

### 5.2. Tạo expression index với dấu ngoặc

~~~sql
CREATE INDEX idx_order_lines_total_256
ON expr_idx_256.order_lines ((unit_price * quantity));
~~~

**Dấu ngoặc kép bên ngoài `((...))`** đến từ hai lớp:

- Cặp ngoài thuộc cú pháp danh sách khóa `ON table (...)`.
- Cặp trong bao **biểu thức số học** `(unit_price * quantity)`.

~~~text
ON order_lines ( (unit_price * quantity) )
               ^ ^                   ^ ^
               | +--- expression ----+ |
               +----- index keys ------+
~~~

### 5.3. Điều kiện range và ORDER BY

~~~sql
SELECT line_id, unit_price * quantity AS line_total
FROM expr_idx_256.order_lines
WHERE unit_price * quantity >= 300000
ORDER BY unit_price * quantity, line_id;
~~~

Một B-tree expression index có thể hỗ trợ điều kiện range trên khóa biểu thức, và trong một số plan có thể cung cấp thứ tự theo chính biểu thức. Việc thêm `line_id` sau thứ tự biểu thức trong `ORDER BY` có thể còn cần sort/tie-break nếu index không có khóa đó.

**Đừng suy ra** index này hiệu quả cho mọi query chỉ lọc `unit_price > 100000`. Khóa index là **tích**, không phải giá gốc.

### 5.4. Những giới hạn

- Các cột `unit_price` và `quantity` phải có kiểu có toán tử nhân được phép cho expression index.
- Kiểu kết quả `numeric` giữ quy tắc chính xác của phép nhân numeric; nếu dùng `double precision`, phải cân nhắc sai số dấu phẩy động cho nghiệp vụ tiền.
- Số học trong expression index phải dựa trên dữ liệu của **hàng hiện tại** và các hàm/toán tử phù hợp, không phải một subquery đọc bảng khác.

## 6. Chỉ mục biểu thức có thể gồm nhiều khóa và INCLUDE

Ví dụ lọc theo loại sự kiện và customer ID được lấy từ JSON:

~~~sql
CREATE INDEX idx_events_type_customer_256
ON expr_idx_256.events (
    event_type,
    (payload ->> 'customer_id')
);
~~~

Biểu thức `payload ->> 'customer_id'` trả về `text`. Index có hai khóa theo thứ tự:

1. `event_type` (cột thường);
2. `payload ->> 'customer_id'` (biểu thức).

Truy vấn tương ứng:

~~~sql
SELECT event_id, occurred_at
FROM expr_idx_256.events
WHERE event_type = 'purchase'
  AND payload ->> 'customer_id' = '1';
~~~

Kết quả gồm event ID **1** và **3**.

### 6.1. Composite index cần chú ý thứ tự cột

Index B-tree trên `(event_type, expression)` thường hữu ích khi query lọc `event_type` trước hoặc lọc cả hai khóa. Nó không tự có độ hiệu quả giống một index riêng chỉ trên expression khi query **chỉ** lọc `payload ->> 'customer_id'`; PostgreSQL có thể cần dùng chiến lược khác hoặc scan tùy thống kê và phiên bản.

### 6.2. INCLUDE khác khóa index

Khi cần lấy `event_id` trong nhiều query:

~~~sql
CREATE INDEX idx_events_customer_cover_256
ON expr_idx_256.events (
    (payload ->> 'customer_id')
)
INCLUDE (event_id);
~~~

`event_id` là **cột được INCLUDE**, không tham gia thứ tự so sánh B-tree hay điều kiện unique của index. Một index có cột INCLUDE có thể giúp một số index-only scan khi điều kiện visibility map và planner phù hợp.

Không nên thêm tất cả các cột lớn vào `INCLUDE`: index phình to, tăng write cost và có giới hạn kích thước index tuple.

## 7. Yêu cầu cốt lõi: hàm trong biểu thức phải IMMUTABLE

PostgreSQL phân loại volatility của hàm thành ba nhóm:

| Volatility | Cách hiểu | Ví dụ thường gặp | Có thể dùng trực tiếp trong khóa expression index? |
| --- | --- | --- | --- |
| **`IMMUTABLE`** | Cùng đầu vào luôn cho cùng kết quả theo giả định của hệ thống; không phụ thuộc trạng thái có thể thay đổi | `lower(text)`, các toán tử số học phù hợp | **Có**, nếu toàn biểu thức hợp lệ |
| **`STABLE`** | Trong một câu lệnh, cùng đầu vào cho kết quả ổn định; có thể khác giữa các câu lệnh khi môi trường thay đổi | `now()` / `transaction_timestamp()`, một số overload có timezone | **Không** |
| **`VOLATILE`** | Có thể thay đổi ngay cả khi gọi lặp với cùng tham số, hoặc có side effect | `random()`, `clock_timestamp()` | **Không** |

Khi chỉ mục lưu kết quả của một hàm, PostgreSQL cần giả định rằng **kết quả không thay đổi nếu các cột hàng không đổi**. Nếu không, chỉ mục có thể chứa khóa đã lỗi thời.

### 7.1. Ví dụ vì sao STABLE không đủ

Giả sử muốn index “đơn hàng được tạo trong hôm nay”:

~~~sql
-- Ví dụ KHÔNG HỢP LỆ:
-- CREATE INDEX idx_today
-- ON orders ((created_at::date = current_date));
~~~

`current_date` thay đổi sau nửa đêm (và phụ thuộc timezone/session). Một hàng hôm nay có thể thành hàng hôm qua **mà không có UPDATE nào trên hàng**; PostgreSQL sẽ không biết phải cập nhật khóa index đã lưu lúc đêm qua.

Thay vào đó, dùng index trên cột thời điểm và một điều kiện có **giới hạn thời gian được tính lúc truy vấn**:

~~~sql
CREATE INDEX idx_events_occurred_at_256
ON expr_idx_256.events (occurred_at);

SELECT event_id
FROM expr_idx_256.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
~~~

Với ngày động, application hoặc SQL tính hai mốc `[start,end)` tương ứng timezone nghiệp vụ, rồi PostgreSQL có thể dùng B-tree trên `occurred_at`. **Không cần index trên “hôm nay”** — một khái niệm thay đổi theo thời gian.

### 7.2. IMMUTABLE là lời hứa tính đúng, không phải nhãn cho tốc độ

Việc tự khai báo một hàm là `IMMUTABLE` **không làm hàm thực sự bất biến**. PostgreSQL tin khai báo của người viết hàm để tối ưu và xây index. Nếu khai báo sai, kết quả index hoặc cached plan có thể không đúng; hệ thống không bắt buộc phát hiện mọi vi phạm từ bên trong hàm.

### 7.3. Toán tử cũng là hàm ở mức hệ thống

Biểu thức:

~~~sql
unit_price * quantity
~~~

có toán tử nhân. Về mặt catalog, các toán tử PostgreSQL trỏ tới hàm thực thi. **Không chỉ những lời gọi có tên `some_function(...)` mới phải thỏa điều kiện volatility**; các toán tử tham gia biểu thức cũng phải phù hợp.

### 7.4. Index predicate cũng phải bất biến

Không chỉ **khóa** expression index: một **partial index predicate** (mệnh đề `WHERE` trong `CREATE INDEX`) cũng phải chỉ dựa trên những hàm/toán tử đáp ứng yêu cầu bất biến.

Ví dụ:

~~~sql
-- KHÔNG HỢP LỆ vì now() không IMMUTABLE:
-- CREATE INDEX idx_recent_orders
-- ON orders (created_at)
-- WHERE created_at >= now() - INTERVAL '7 days';
~~~

Ngay cả khi index key `created_at` là cột thường, **predicate** đổi giá trị theo thời gian mà không có thao tác ghi vào hàng, nên không được lưu cố định vào partial index.

## 8. Xem thuộc tính volatility trong pg_proc

Không cần đoán chỉ từ tên hàm. PostgreSQL ghi volatility trong system catalog **`pg_proc.provolatile`**.

~~~sql
SELECT
    n.nspname AS function_schema,
    p.proname AS function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid)
        AS argument_types,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility,
    CASE p.proparallel
        WHEN 's' THEN 'PARALLEL SAFE'
        WHEN 'r' THEN 'PARALLEL RESTRICTED'
        WHEN 'u' THEN 'PARALLEL UNSAFE'
    END AS parallel_safety
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'pg_catalog'
  AND p.proname IN (
      'lower',
      'date_trunc',
      'now',
      'random',
      'clock_timestamp',
      'to_char'
  )
ORDER BY p.proname, argument_types;
~~~

### 8.1. Tại sao hiển thị argument_types?

**Hàm PostgreSQL có thể overload theo kiểu tham số.** Một tên như `date_trunc` có thể có các bản triển khai nhận `timestamp without time zone`, `timestamp with time zone` hoặc kiểu khác. Các overload này **không nhất thiết có volatility giống nhau**.

Không kết luận “`date_trunc` luôn bất biến” hoặc “`date_trunc` luôn stable” chỉ dựa trên tên. Phải xét **chữ ký thực sự được SQL chọn**.

### 8.2. Xem một hàm theo đúng chữ ký

~~~sql
SELECT
    p.oid::regprocedure AS function_signature,
    p.provolatile,
    p.proparallel
FROM pg_catalog.pg_proc AS p
WHERE p.oid = 'pg_catalog.lower(text)'::regprocedure;
~~~

`provolatile='i'` nghĩa là khai báo IMMUTABLE. `proparallel` có ý nghĩa riêng về an toàn thực thi song song; **PARALLEL SAFE không đồng nghĩa IMMUTABLE và ngược lại**.

### 8.3. Dùng regprocedure tránh nhầm overload

~~~sql
SELECT
    'pg_catalog.now()'::regprocedure AS now_signature,
    'pg_catalog.random()'::regprocedure AS random_signature;
~~~

Với hàm tự viết, nên luôn kiểm tra **schema và kiểu đối số**, nhất là khi có tên trùng với hàm trong `pg_catalog` hoặc function overload trong nhiều schema.

## 9. Hai overload date_trunc và bẫy timestamptz

Một lỗi điển hình là thử tạo index theo ngày từ cột `TIMESTAMPTZ`:

~~~sql
-- KHÔNG HỢP LỆ theo volatility của overload thường dùng:
-- CREATE INDEX idx_events_date_bad_256
-- ON expr_idx_256.events ((occurred_at::date));
~~~

Phép chuyển `timestamptz -> date` **phụ thuộc múi giờ session**: cùng một instant UTC có thể thuộc ngày 14 ở timezone này nhưng ngày 15 ở timezone khác. Vì vậy phép cast tương ứng không thể coi là IMMUTABLE trên đầu vào `timestamptz`.

Ví dụ:

~~~text
2026-11-14 23:30:00+00
    = 2026-11-15 06:30:00+07

UTC day             : 2026-11-14
Asia/Ho_Chi_Minh day: 2026-11-15
~~~

### 9.1. date_trunc(text,timestamptz)

~~~sql
-- Cũng thường bị từ chối:
-- CREATE INDEX idx_events_trunc_bad_256
-- ON expr_idx_256.events (
--     date_trunc('day', occurred_at)
-- );
~~~

Overload `date_trunc(text, timestamptz)` có ngữ nghĩa liên quan `TimeZone` session, nên không được phép index theo yêu cầu IMMUTABLE.

### 9.2. date_trunc(text,timestamp without time zone)

Trái lại, khi cột là **timestamp không timezone** và biểu thức dùng đúng overload phù hợp:

~~~sql
CREATE INDEX idx_lines_created_day_256
ON expr_idx_256.order_lines (
    date_trunc('day', created_local)
);
~~~

Khóa index là timestamp đã được làm tròn xuống đầu ngày theo dữ liệu timestamp không timezone.

Truy vấn:

~~~sql
SELECT line_id, created_local
FROM expr_idx_256.order_lines
WHERE date_trunc('day', created_local)
      = TIMESTAMP '2026-11-14 00:00:00'
ORDER BY line_id;
~~~

Kết quả là `line_id=4,5,6` trong dataset.

### 9.3. Đừng ép kiểu để “qua” kiểm tra IMMUTABLE

Không tự chuyển `timestamptz` sang `timestamp` mà không xác định múi giờ:

~~~sql
-- Có yếu tố phụ thuộc session timezone; đừng mặc định immutable:
-- occurred_at::timestamp
~~~

Nếu nghiệp vụ cần nhóm theo ngày địa phương, hãy **định nghĩa timezone thật rõ** và kiểm tra volatility của mọi hàm trong biểu thức. Trong nhiều hệ thống, giải pháp đơn giản, đúng và dễ bảo trì nhất là **B-tree index trên `occurred_at`** kết hợp điều kiện range trên hai mốc timestamp có timezone.

### 9.4. Range predicate thường tốt hơn ép timestamp vào ngày

~~~sql
SELECT
    event_id,
    occurred_at
FROM expr_idx_256.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
~~~

Dạng **nửa mở `[start, end)`** tránh những mẹo như “23:59:59.999999”, không bỏ sót độ chính xác microsecond và tận dụng index trên cột gốc. Với timezone có DST, **không mặc định một ngày địa phương luôn 24 giờ**; tính hai mốc midnight theo đúng vùng timezone rồi chuyển sang instant.

## 10. Những biểu thức dùng thời gian hiện tại không thể làm khóa index

Những câu sau là **ví dụ cố ý sai**, chỉ đọc để hiểu lỗi, không áp dụng:

~~~sql
-- now() là STABLE, không IMMUTABLE:
-- CREATE INDEX idx_bad_1
-- ON expr_idx_256.events ((now() - occurred_at));

-- clock_timestamp() là VOLATILE:
-- CREATE INDEX idx_bad_2
-- ON expr_idx_256.events ((clock_timestamp()));

-- random() là VOLATILE:
-- CREATE INDEX idx_bad_3
-- ON expr_idx_256.events ((random()));
~~~

Lỗi PostgreSQL thường là:

~~~text
ERROR: functions in index expression must be marked IMMUTABLE
~~~

Với partial index predicate:

~~~text
ERROR: functions in index predicate must be marked IMMUTABLE
~~~

### 10.1. “Bảy ngày gần nhất” là điều kiện **động**

Yêu cầu:

> Lấy những sự kiện xảy ra trong bảy ngày gần nhất.

Giải pháp thực tế:

~~~sql
SELECT event_id, event_type
FROM expr_idx_256.events
WHERE occurred_at >= now() - INTERVAL '7 days'
ORDER BY occurred_at DESC;
~~~

Index `(occurred_at)` đã tạo ở mục 7 vẫn có thể hỗ trợ **range scan** dù vế phải dùng `now()`. Ràng buộc IMMUTABLE áp dụng cho **biểu thức được lưu làm khóa hoặc predicate index**, không có nghĩa mọi giá trị runtime ở điều kiện query cũng phải immutable.

### 10.2. Vì sao SQL trên query được phép có now?

Trong query, `now() - INTERVAL '7 days'` được đánh giá ở thời điểm thực thi phù hợp với tính STABLE và transaction timestamp. Nó không phải một khóa index đã được lưu lâu dài khi dữ liệu chưa thay đổi.

### 10.3. “Đang còn hiệu lực” và partial index

Không nên viết:

~~~sql
-- KHÔNG HỢP LỆ:
-- CREATE INDEX idx_active_promotions
-- ON promotions (promotion_id)
-- WHERE expires_at > now();
~~~

Một promotion hợp lệ hôm nay có thể hết hạn ngày mai mà **không cần UPDATE**. Index partial chỉ tự duy trì khi hàng thay đổi, nên không thể tự chuyển hàng ra khỏi index khi đồng hồ trôi.

Giải pháp có thể là:

- Index trên `expires_at` và lọc `expires_at > now()` lúc đọc.
- Duy trì một cột trạng thái **materialized** thông qua job/transaction cập nhật có kiểm soát, nếu business cho phép độ trễ.
- Thiết kế index partial theo điều kiện **ổn định trên cột** như `cancelled_at IS NULL`, không dựa vào đồng hồ.

## 11. Hàm tự viết: đánh dấu IMMUTABLE đúng cách

Một hệ thống có thể quy định email được so khớp bằng cách **bỏ whitespace ở hai đầu và lower-case**. Ta có thể tạo một hàm SQL:

~~~sql
CREATE FUNCTION expr_idx_256.normalize_email(input_email TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT pg_catalog.lower(
        pg_catalog.btrim(input_email)
    );
$$;
~~~

Các thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `LANGUAGE sql` | Hàm dùng biểu thức SQL |
| `IMMUTABLE` | Khai báo cùng đầu vào cho cùng kết quả theo ngữ nghĩa hàm |
| `STRICT` | Trả NULL khi bất kỳ tham số nào NULL; không cần chạy thân hàm với đầu vào NULL |
| `PARALLEL SAFE` | Hàm được khai báo an toàn để chạy trong parallel worker |

Với hàm chỉ gọi `btrim(text)` và `lower(text)` phù hợp, khai báo IMMUTABLE là một lựa chọn có cơ sở trong ngữ cảnh collation được giữ ổn định. Tuy nhiên, **quy tắc chữ hoa/thường có thể phụ thuộc collation/locale**; nâng cấp thư viện collation hay thay đổi quy tắc chuẩn hóa là một tình huống cần bảo trì index.

### 11.1. Dùng hàm trong index

~~~sql
CREATE INDEX idx_customers_normalized_email_256
ON expr_idx_256.customers (
    expr_idx_256.normalize_email(email)
);
~~~

~~~sql
SELECT
    customer_id,
    email
FROM expr_idx_256.customers
WHERE expr_idx_256.normalize_email(email)
      = expr_idx_256.normalize_email('  ANH@EXAMPLE.COM  ');
~~~

Kết quả gồm khách hàng 1.

### 11.2. Query phải dùng cùng quy tắc chuẩn hóa

Một index trên:

~~~sql
expr_idx_256.normalize_email(email)
~~~

không nhất thiết được planner dùng cho truy vấn chỉ viết:

~~~sql
WHERE lower(email) = 'anh@example.com'
~~~

Mặc dù hàm hiện tại có thể tương đương `lower(btrim(email))`, planner không nên bị giả định là sẽ suy diễn và mở rộng mọi UDF rồi khớp index. Hãy thống nhất expression trong các đường truy vấn hoặc thiết kế một normalized column rõ ràng.

### 11.3. Vì sao phải ghi rõ pg_catalog?

Hàm SQL có thể phụ thuộc cách tên hàm/đối tượng được phân giải theo `search_path`. Trong ví dụ, dùng `pg_catalog.lower` và `pg_catalog.btrim` giúp làm rõ hàm hệ thống được gọi và giảm nhầm lẫn khi có hàm trùng tên ở schema khác.

Đây là phần của **định nghĩa ngữ nghĩa ổn định**; nó không tự thay yêu cầu kiểm tra collation, dữ liệu hay quyền thực thi.

## 12. Không “nói dối” PostgreSQL về tính bất biến

Giả sử tác giả viết một hàm đọc tỷ giá từ bảng khác:

~~~sql
-- PSEUDOCODE KHÔNG ĐƯỢC ĐƯA VÀO PRODUCTION:
-- CREATE FUNCTION calc_vnd_price(usd numeric)
-- RETURNS numeric
-- LANGUAGE sql
-- IMMUTABLE
-- AS $$
--     SELECT usd * rate
--     FROM exchange_rates
--     WHERE currency = 'USD';
-- $$;
~~~

Tỷ giá có thể thay đổi mà **`usd` ở dòng sản phẩm không đổi**. Dù tác giả khai báo `IMMUTABLE`, hàm thực tế phụ thuộc bảng `exchange_rates`. Nếu dùng nó làm khóa index, giá trị index đã lưu **không được tự tính lại** khi bảng tỷ giá thay đổi.

Hậu quả:

- Query qua index có thể nhìn giá trị cũ.
- Query dùng Seq Scan có thể tính giá trị mới.
- Kết quả nghiệp vụ có thể **khác nhau tùy query plan**.
- Unique expression index có thể kiểm soát uniqueness theo một quy tắc đã lỗi thời.
- Các kế hoạch SQL đã cache có thể tối ưu lời gọi hàm IMMUTABLE theo cách không phù hợp nếu hàm thực sự có trạng thái thay đổi.

### 12.1. Những yếu tố thường khiến hàm không immutable

- Đọc một bảng khác hoặc phụ thuộc giá trị có thể cập nhật.
- Gọi đồng hồ thời gian (`now`, `current_timestamp`, `clock_timestamp`).
- Dùng ngẫu nhiên (`random`).
- Phụ thuộc cấu hình session như `TimeZone`, `DateStyle`, `lc_time` hoặc `search_path` mà kết quả có thể thay đổi.
- Gọi API/HTTP, đọc file có thể đổi, trạng thái bên ngoài.
- Phụ thuộc dữ liệu extension/dictionary có thể thay đổi mà không có cơ chế rebuild.
- Hàm có side effect, ghi dữ liệu hoặc thay đổi trạng thái.

Không phải mọi hàm có yếu tố locale đều bị catalog đánh dấu STABLE: nhiều hàm như `lower` được khai báo IMMUTABLE theo ngữ nghĩa collation và giả định collation được bảo trì. **Điều cần phân biệt** là volatility do PostgreSQL khai báo và những thay đổi ngoài bối cảnh bình thường như upgrade collation, vốn có thể yêu cầu REINDEX.

### 12.2. Có thể ép hàm STABLE thành IMMUTABLE bằng wrapper không?

Bạn có thể viết một wrapper và **tự khai báo** IMMUTABLE, nhưng PostgreSQL thường chỉ tin metadata của wrapper thay vì chứng minh toàn bộ hành vi của nó qua mọi cách gọi. Điều đó **không biến phép tính phụ thuộc session thành đúng**.

Ví dụ với `unaccent`: cấu hình dictionary/rules có thể thay đổi. Một số hướng dẫn dùng wrapper IMMUTABLE để tạo index. Chỉ nên làm nếu bạn thực sự **kiểm soát và khóa chặt quy tắc chuyển đổi**, hiểu khi nào cần rebuild, và chấp nhận bảo trì thủ công. Nếu quy tắc có thể thay đổi, dùng **cột chuẩn hóa được lưu và cập nhật có kiểm soát** thường minh bạch hơn.

### 12.3. IMMUTABLE không có nghĩa “không được sửa source code”

Một hàm có thể thực sự immutable **với định nghĩa hiện tại**, nhưng nếu bạn thay logic từ:

~~~text
normalize_email = lower(trim(email))
~~~

sang:

~~~text
normalize_email = lower(trim(email)) + một quy tắc mới
~~~

thì dữ liệu khóa đã lưu trong index có thể không còn hợp lệ theo logic mới. Thay đổi body của hàm được index tham chiếu **không nhất thiết tự rebuild index**. Cần kế hoạch migration, kiểm tra uniqueness, backfill/reindex và rollout an toàn.

## 13. STABLE và VOLATILE có mục đích hợp lệ ngoài expression index

Không nên suy ra hàm STABLE/VOLATILE “xấu”. Chúng có vai trò cần thiết:

### 13.1. STABLE

Ví dụ:

~~~sql
SELECT now();
~~~

`now()` đại diện transaction start time; kết quả giữ ổn định trong cùng transaction theo ngữ nghĩa PostgreSQL. Nó thích hợp để:

~~~sql
SELECT event_id
FROM expr_idx_256.events
WHERE occurred_at >= now() - INTERVAL '24 hours';
~~~

nhưng không thích hợp để **đưa vào index key** vì một transaction vào ngày mai sẽ có timestamp khác cho cùng tham số rỗng.

### 13.2. VOLATILE

~~~sql
SELECT random(), clock_timestamp();
~~~

Hàm có thể cho kết quả khác nhau giữa các lần gọi. Chúng hữu ích cho một số bài toán nhưng không thể làm cơ sở khóa index ổn định.

### 13.3. Khác biệt với parallel safety

Một hàm có thể được khai báo:

~~~sql
STABLE PARALLEL SAFE
~~~

nhưng **vẫn không được dùng** trong expression index vì không IMMUTABLE. Ngược lại, một hàm IMMUTABLE nhưng đánh dấu `PARALLEL UNSAFE` có thể bị hạn chế trong parallel query, song đó là **một thuộc tính khác**, không phải lý do trực tiếp của yêu cầu volatility đối với index.

## 14. Unique expression index: ràng buộc email không phân biệt hoa/thường

Expression index còn làm được việc quan trọng hơn tăng tốc: tạo **ràng buộc uniqueness theo kết quả biểu thức**.

### 14.1. Unique trên email gốc chưa đủ

~~~sql
CREATE UNIQUE INDEX idx_customers_email_raw_256
ON expr_idx_256.customers (email);
~~~

Index này coi `'Anh@Example.com'` và `'anh@example.com'` là **hai chuỗi khác nhau** dưới các quy tắc so sánh thông thường của cột/text collation được dùng. Nếu business muốn email case-insensitive, ràng buộc trên email gốc có thể chưa đủ.

### 14.2. Unique theo lower(email)

~~~sql
CREATE UNIQUE INDEX uq_customers_lower_email_256
ON expr_idx_256.customers (lower(email));
~~~

Giờ một khách hàng mới dùng email `'ANH@example.COM'` có cùng `lower(email)` với `customer_id=1` nên sẽ vi phạm uniqueness.

~~~sql
-- Chỉ thử trên dữ liệu lab:
BEGIN;
SAVEPOINT before_duplicate;

INSERT INTO expr_idx_256.customers
    (customer_id, email, display_name)
VALUES
    (100, 'ANH@example.COM', 'Email trùng chuẩn hóa');
-- Dự kiến: ERROR duplicate key value violates unique constraint.
-- SQLSTATE 23505.

ROLLBACK TO SAVEPOINT before_duplicate;
ROLLBACK;
~~~

Sau lỗi trong transaction, dùng `ROLLBACK TO SAVEPOINT`/`ROLLBACK` phù hợp trước khi tiếp tục.

### 14.3. Unique expression index không tự làm cột NOT NULL

Nếu `email` nullable, `lower(NULL)` là NULL. Theo quy tắc uniqueness mặc định của PostgreSQL, **nhiều khóa NULL** có thể cùng tồn tại trong unique index. Trong lab đã khai báo `email TEXT NOT NULL`, nên không có lỗ hổng đó.

Nếu muốn NULL được coi không khác nhau, PostgreSQL hiện đại có cơ chế unique `NULLS NOT DISTINCT` trong những ngữ cảnh phù hợp, nhưng chỉ dùng khi tương ứng hợp đồng dữ liệu và phiên bản server.

### 14.4. Lưu ý về Unicode/collation

`lower(text)` có quy tắc phụ thuộc collation, không nhất thiết tương đương **Unicode full case folding** hoặc mọi quy tắc chuẩn hóa địa chỉ email. Email còn có domain, local-part và những quy ước nghiệp vụ riêng. **Đừng tuyên bố unique lower(email) giải quyết mọi trường hợp Unicode/email identity** nếu hệ thống cần một định nghĩa chính xác hơn.

### 14.5. Không giống UNIQUE constraint trên cột

Unique expression index được PostgreSQL dùng để kiểm soát trùng biểu thức, nhưng không phải một khóa unique cột thường để mọi tính năng tham chiếu hoạt động hệt:

- Một `FOREIGN KEY` không thể tham chiếu trực tiếp “giá trị `lower(email)`” như một cột target không tồn tại.
- Không thể tự coi expression index là `UNIQUE(email)` thông thường trong schema.
- `ON CONFLICT` có cơ chế suy luận index phù hợp theo biểu thức/predicate, nhưng phải dùng đúng cú pháp và đặc tính index; không nên cho rằng mọi expression index có thể đặt tên như một unique constraint cột.

Khi cần FK/ORM/schema portability, hãy cân nhắc **cột normalized_email có ràng buộc** hoặc giải pháp dữ liệu tương ứng.

## 15. Partial expression index: chỉ index những hàng đang hoạt động

Trong nhiều hệ thống, tài khoản đã soft-delete vẫn cần giữ lịch sử nhưng không nên chặn email cho tài khoản hoạt động mới.

Ví dụ:

~~~sql
CREATE UNIQUE INDEX uq_customers_active_email_256
ON expr_idx_256.customers (
    expr_idx_256.normalize_email(email)
)
WHERE deleted_at IS NULL;
~~~

Trong phạm vi **hàng đang hoạt động**, email sau chuẩn hóa không được trùng. Hàng đã soft-delete không tham gia index partial này.

**Ghi chú quan trọng cho lab:** ở mục 14.2 đã tạo `uq_customers_lower_email_256` **áp dụng cho tất cả hàng**. Khi thử logic “soft-deleted được dùng lại email”, hãy xóa **index unique toàn bảng** hoặc chạy trên một bảng khác; nếu giữ cả hai, index toàn bảng vẫn cấm việc trùng `lower(email)` dù hàng cũ đã soft-delete.

### 15.1. Truy vấn phù hợp predicate

~~~sql
SELECT
    customer_id,
    email
FROM expr_idx_256.customers
WHERE deleted_at IS NULL
  AND expr_idx_256.normalize_email(email)
      = expr_idx_256.normalize_email('ANH@EXAMPLE.COM');
~~~

Điều kiện `deleted_at IS NULL` giúp planner thấy truy vấn chỉ cần những hàng được partial index bao phủ.

### 15.2. Tại sao query bỏ deleted_at có thể không dùng partial index?

~~~sql
SELECT customer_id
FROM expr_idx_256.customers
WHERE expr_idx_256.normalize_email(email)
      = 'anh@example.com';
~~~

Query này cần cả **hàng đã xóa**, trong khi partial index chỉ có **hàng chưa xóa**. PostgreSQL không thể dùng partial index làm nguồn đầy đủ cho một điều kiện không đảm bảo predicate của index.

### 15.3. Predicate implication và prepared statements

Planner cần chứng minh điều kiện `WHERE` của truy vấn **hàm ý predicate** của partial index, thường tại thời điểm lập kế hoạch. Các điều kiện diễn đạt tương đương bằng logic phức tạp, hoặc điều kiện phụ thuộc tham số không biết giá trị khi lập generic plan, có thể **không được nhận ra**.

Ví dụ một partial index theo:

~~~sql
WHERE deleted_at IS NULL
~~~

phù hợp rõ ràng với query có chính điều kiện này. Tránh giả định PostgreSQL có một bộ chứng minh logic tổng quát cho mọi cấu trúc `CASE`, `COALESCE`, điều kiện OR hoặc placeholder.

### 15.4. Dùng unique partial index cho quy tắc “chỉ active mới unique”

Đây là ví dụ cho thấy index có thể thực thi **quy tắc nghiệp vụ** chứ không chỉ tiết kiệm thời gian đọc. Nhưng phải thống nhất:

- Khi soft-delete, email cũ được phép tái sử dụng hay không?
- Khi khôi phục tài khoản đã xóa, nếu email bị chiếm thì làm gì?
- Có cần quản lý email trùng trước khi tạo unique index không?
- Hệ thống login/query có luôn lọc `deleted_at IS NULL` không?

Nếu một rule thay đổi sau khi index đã triển khai, cần migration có kiểm soát và xem tác động dữ liệu trùng đang tồn tại.

## 16. Toàn bộ biểu thức phải hợp lệ, không chỉ hàm ngoài cùng

Ví dụ:

~~~sql
CREATE INDEX idx_customers_cleanup_256
ON expr_idx_256.customers (
    lower(btrim(email))
);
~~~

Để expression index này hợp lệ, không đủ nếu chỉ `lower` là IMMUTABLE. Các phép toán/hàm thành phần **`btrim`**, phép ép kiểu ngầm định, thao tác collation và biểu thức liên quan đều phải thỏa yêu cầu.

### 16.1. COALESCE và CASE

Những cấu trúc SQL như `COALESCE` hoặc `CASE` không tự khiến expression index bất hợp lệ:

~~~sql
CREATE INDEX idx_customer_deleted_marker_256
ON expr_idx_256.customers (
    (CASE WHEN deleted_at IS NULL THEN 1 ELSE 0 END)
);
~~~

Điều kiện kiểm tra `deleted_at IS NULL` ổn định theo dữ liệu hàng; kết quả `1`/`0` không phụ thuộc session. Tuy vậy, index trên biểu thức chỉ có hai giá trị thường có **độ chọn lọc thấp** và có thể không có lợi bằng một partial index phù hợp với truy vấn thực tế.

Ví dụ khác:

~~~sql
CREATE INDEX idx_customers_name_fallback_256
ON expr_idx_256.customers (
    lower(COALESCE(display_name, ''))
);
~~~

Trong schema lab, `display_name NOT NULL`, nên `COALESCE` hơi thừa. Ở bảng khác có cột nullable, expression có thể hữu ích, nhưng phải thống nhất **NULL được diễn giải thành chuỗi rỗng** có đúng nghiệp vụ không.

### 16.2. Không đặt aggregate/window/subquery trong index expression

Chỉ mục biểu thức tính từ **các cột của một hàng trong bảng được index**, không phải một truy vấn tùy ý trên toàn database.

Những ý tưởng sau không phù hợp làm khóa expression index trực tiếp:

~~~sql
-- Không hợp lệ / không phải thiết kế đúng:
--
-- CREATE INDEX idx_sum
-- ON order_lines ((SUM(unit_price * quantity)));
--
-- CREATE INDEX idx_rank
-- ON orders ((ROW_NUMBER() OVER (ORDER BY created_at)));
--
-- CREATE INDEX idx_latest_rate
-- ON products ((price * (
--     SELECT rate FROM exchange_rates ORDER BY changed_at DESC LIMIT 1
-- )));
~~~

Các giá trị như **tổng theo nhiều hàng**, **xếp hạng cửa sổ**, **tỷ giá hiện hành của bảng khác** cần thiết kế khác:

- Truy vấn aggregate trên dữ liệu đã có index phù hợp;
- Materialized view có quy trình `REFRESH`;
- Bảng summary được duy trì có kiểm soát;
- Cột vật hóa giá trị tại thời điểm ghi;
- Quy tắc nghiệp vụ tách riêng khỏi index expression.

### 16.3. Không phụ thuộc giá trị từ hàng khác

Một hàm `IMMUTABLE` thực sự không thể cho kết quả khác chỉ vì một hàng ở bảng lookup được sửa. Nếu muốn lưu kết quả tra cứu, hãy materialize dữ liệu nguồn vào chính hàng đích, quản lý việc cập nhật đồng bộ và định nghĩa index trên cột được lưu. **Index không tự thiết lập dependency dữ liệu lên từng hàng của bảng khác.**

## 17. Thay hàm đã được index tham chiếu: vì sao cần REINDEX?

Giả sử hệ thống đã có:

~~~sql
CREATE INDEX idx_customers_normalized_email_256
ON expr_idx_256.customers (
    expr_idx_256.normalize_email(email)
);
~~~

Và function version 1 thực hiện:

~~~text
normalize_email(email) = lower(trim(email))
~~~

Sau này nhóm phát triển thay logic function để xóa thêm một ký tự, chuyển đổi Unicode hay chuẩn hóa theo chính sách mới. **PostgreSQL không tự tính lại mọi index key chỉ vì body của function thay đổi**.

### 17.1. Kịch bản index stale

~~~text
Ngày 1:
    email = "A.B@example.com"
    f_v1(email) = "a.b@example.com"
    → key index = "a.b@example.com"

Ngày 20:
    f_v2(email) = "ab@example.com"
    → SELECT bằng hàm mới tính "ab@example.com"
    → index vẫn có thể đang giữ key cũ "a.b@example.com"
~~~

Nếu query planner dùng expression index, kết quả có thể không khớp với tính toán lại bằng logic mới. Đặc biệt với **UNIQUE** expression index, thay đổi chuẩn hóa có thể khiến **hai hàng trước đây không trùng trở nên trùng**, cần giải quyết dữ liệu trước khi xây lại.

### 17.2. Mẫu kế hoạch migration

1. Thống nhất quy tắc mới và phiên bản ứng dụng.
2. Tính thử kết quả expression mới trên dữ liệu hiện có.
3. Tìm những collision/duplicate dưới quy tắc mới.
4. Có phương án xử lý collision và rollback nghiệp vụ.
5. Triển khai hàm mới theo chiến lược tương thích (đôi khi dùng tên version mới như `normalize_email_v2`).
6. Tạo index mới tương ứng, hoặc `REINDEX` đúng index sau khi hàm được cập nhật.
7. Đo query plan, kiểm tra ràng buộc uniqueness và chuyển ứng dụng sang truy vấn mới.
8. Chỉ xóa index/hàm cũ khi đã xác nhận không còn dependency và có thể khôi phục.

**Không sửa body của hàm IMMUTABLE trong production như một thay đổi “không ảnh hưởng dữ liệu” khi hàm đang được index, generated column hoặc plan khác tham chiếu.**

### 17.3. Ví dụ REINDEX trong môi trường phù hợp

~~~sql
-- Tái tính index key từ định nghĩa hiện tại của hàm.
-- Dùng khi đã lập kế hoạch và được phép vận hành.
REINDEX INDEX expr_idx_256.idx_customers_normalized_email_256;
~~~

Lệnh này có thể ảnh hưởng truy cập đồng thời tùy cách thực thi. Trên PostgreSQL hỗ trợ và trong hoàn cảnh phù hợp, có thể cân nhắc:

~~~sql
REINDEX INDEX CONCURRENTLY
    expr_idx_256.idx_customers_normalized_email_256;
~~~

`REINDEX ... CONCURRENTLY` có điều kiện hỗ trợ/giới hạn riêng, không chạy trong explicit transaction block thông thường và có thể không thích hợp với mọi loại index hoặc tình huống sự cố. Cần xem tài liệu đúng phiên bản và đánh giá downtime/IO.

### 17.4. Đổi nhãn volatility không làm dữ liệu index đúng

Nếu một function đã được index dùng và bạn đổi từ `IMMUTABLE` sang `STABLE`, PostgreSQL sẽ không tự “sửa” index cũ thành một loại index hợp lệ khác. **Quy tắc tính index vốn yêu cầu IMMUTABLE**, nên cách xử lý đúng có thể là loại bỏ index và thiết kế lại dữ liệu/query, không phải chỉ đổi metadata.

## 18. Collation và ICU/libc: một dạng thay đổi logic âm thầm

Với text, nhiều phép so sánh và chuyển chữ phụ thuộc **collation**. PostgreSQL có thể sử dụng collation từ `libc` hoặc `ICU` tùy cách cài đặt và phiên bản.

Ví dụ:

~~~sql
CREATE INDEX idx_customers_lower_name_256
ON expr_idx_256.customers (lower(display_name));
~~~

Index này giả định quy tắc `lower` và trật tự so sánh text của collation đủ ổn định. Nếu hệ điều hành/ICU hoặc định nghĩa collation thay đổi, một khóa đã lưu theo phiên bản cũ có thể **không còn có thứ tự/giá trị phù hợp với phiên bản mới**.

### 18.1. Xem thông tin collation

~~~sql
SELECT
    oid::regcollation AS collation_name,
    collprovider,
    collversion,
    pg_catalog.pg_collation_actual_version(oid) AS actual_version
FROM pg_catalog.pg_collation
WHERE collversion IS NOT NULL
ORDER BY 1
LIMIT 30;
~~~

### 18.2. Tìm chênh lệch version collation

~~~sql
SELECT
    oid::regcollation AS collation_name,
    collversion,
    pg_catalog.pg_collation_actual_version(oid) AS actual_version
FROM pg_catalog.pg_collation
WHERE collversion IS NOT NULL
  AND collversion IS DISTINCT FROM
      pg_catalog.pg_collation_actual_version(oid)
ORDER BY 1;
~~~

Kết quả chênh lệch là một dấu hiệu cần xem tài liệu và kế hoạch bảo trì. **Không khẳng định mọi index bị hỏng chỉ từ một hàng khác version**, nhưng phải đánh giá các đối tượng phụ thuộc collation.

### 18.3. Khi nâng cấp collation

Kế hoạch thường cần:

- Xác định những index, constraint, materialized objects phụ thuộc collation;
- Rebuild index/đối tượng cần thiết theo quy tắc mới;
- Kiểm tra collision hoặc thay đổi thứ tự trong unique index;
- Chỉ cập nhật metadata collation version bằng lệnh thích hợp khi đã xử lý phụ thuộc.

**Chỉ chạy `ALTER COLLATION ... REFRESH VERSION` để làm hết warning mà chưa rebuild các index cần thiết không giải quyết nội dung khóa cũ.**

### 18.4. COLLATE "C" khi yêu cầu byte/ASCII rõ ràng

Với một số mã kỹ thuật chỉ dùng ASCII và cần quy tắc nhất quán, có thể chọn collation rõ ràng:

~~~sql
CREATE INDEX idx_customers_email_c_256
ON expr_idx_256.customers (
    lower(email COLLATE "C")
);
~~~

Truy vấn muốn dùng logic index này phải dùng **cùng collation** và dạng biểu thức phù hợp:

~~~sql
SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(email COLLATE "C") = 'anh@example.com';
~~~

Tuy nhiên, collation `"C"` có quy tắc chữ hoa/thường không giống mọi ngôn ngữ Unicode. **Không đổi collation chỉ để index nhanh hơn** khi ứng dụng cần so khớp tên người/địa chỉ quốc tế theo quy tắc khác.

## 19. Query biểu thức có tương thích index không?

Xét index:

~~~sql
CREATE INDEX idx_customers_lower_email_256
ON expr_idx_256.customers (lower(email));
~~~

Các truy vấn:

~~~sql
-- A: phù hợp trực tiếp
SELECT customer_id FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';

-- B: cũng có thể dùng nếu planner suy luận được vế phải
SELECT customer_id FROM expr_idx_256.customers
WHERE lower(email) = lower('ANH@EXAMPLE.COM');

-- C: khác biểu thức ở vế trái
SELECT customer_id FROM expr_idx_256.customers
WHERE lower(btrim(email)) = 'anh@example.com';

-- D: khác toán tử/cách tìm
SELECT customer_id FROM expr_idx_256.customers
WHERE email ILIKE '%example.com';
~~~

**A/B** gần với khóa index. **C** dùng một biểu thức khác (`lower(btrim(email))`) nên không nên mặc định index `lower(email)` hỗ trợ. **D** là pattern search trên cột raw, có thể cần một index khác và operator class/extension phù hợp.

### 19.1. PostgreSQL có thể chuẩn hóa một số biểu thức

Planner có thể biến đổi, rút gọn hằng số hoặc suy luận một số điều kiện để sử dụng index. Vì vậy **không cần mọi byte trong SQL phải giống hệt định nghĩa index**. Nhưng cũng không được giả định planner sẽ chứng minh mọi đồng nhất thức toán học hay biến đổi qua UDF.

**Nguyên tắc thực tế:** viết predicate đúng theo định nghĩa dữ liệu, xem `EXPLAIN` và đo trên workload thật thay vì đoán.

### 19.2. Kiểu dữ liệu và implicit cast

Index trên:

~~~sql
(payload ->> 'customer_id')
~~~

trả kiểu `text`. Query:

~~~sql
WHERE payload ->> 'customer_id' = '1'
~~~

phù hợp với khóa text. Nhưng nếu viết:

~~~sql
WHERE (payload ->> 'customer_id')::bigint = 1
~~~

đó là biểu thức **kiểu bigint** khác. Index text không tự trở thành index bigint. Nếu truy vấn số học thật sự chiếm ưu thế và mọi dữ liệu JSONB có thể ép kiểu hợp lệ, có thể thiết kế index riêng cho phép cast.

### 19.3. Cẩn thận dữ liệu lỗi khi cast vào expression index

Ví dụ:

~~~sql
-- Chỉ hợp lệ nếu mọi payload cần index đều chứa
-- chuỗi customer_id có thể ép sang BIGINT.
--
-- CREATE INDEX idx_events_customer_numeric
-- ON expr_idx_256.events (
--     ((payload ->> 'customer_id')::bigint)
-- );
~~~

Nếu có một payload chứa `"customer_id":"ABC"`, việc **build index** có thể thất bại vì cast text sang bigint không hợp lệ. Sau khi index được tạo, một insert/update dữ liệu không đúng định dạng cũng có thể thất bại khi PostgreSQL cần tính khóa index.

Đây là một lợi ích gián tiếp về phát hiện dữ liệu nhưng **không thay** quy tắc schema validation rõ ràng như `CHECK`/JSON schema validation ở application.

## 20. Expression index B-tree so với GIN/GiST/trigram

Expression index không phải **một index method độc lập**. Nó là cách xác định **index key**; phương thức index vẫn có thể là B-tree, GIN, GiST hoặc phương thức khác nếu dữ liệu/toán tử được hỗ trợ.

### 20.1. B-tree cho equality và range trên biểu thức

~~~sql
CREATE INDEX idx_lines_amount_btree_256
ON expr_idx_256.order_lines
USING btree ((unit_price * quantity));
~~~

Phù hợp với những truy vấn `=`, `<`, `>=`, `ORDER BY` trên cùng biểu thức, tùy planner và thống kê.

### 20.2. GIN trên JSONB thô

Nếu muốn hỏi về cấu trúc JSONB:

~~~sql
CREATE INDEX idx_events_payload_gin_256
ON expr_idx_256.events
USING gin (payload);
~~~

Truy vấn:

~~~sql
SELECT event_id
FROM expr_idx_256.events
WHERE payload @> '{"customer_id":"1"}'::jsonb;
~~~

GIN trên `payload` có thể hỗ trợ toán tử containment `@>` phù hợp với operator class của JSONB. Đây là chiến lược khác với B-tree trên `payload ->> 'customer_id'`.

### 20.3. B-tree trên trường JSONB đã trích xuất

~~~sql
CREATE INDEX idx_events_customer_text_256
ON expr_idx_256.events (
    (payload ->> 'customer_id')
);
~~~

Nó lưu text đã trích xuất, phù hợp với `WHERE payload ->> 'customer_id' = '1'`. Nếu chỉ lọc equality một đường JSON cố định, phương án này có thể nhỏ và hiệu quả hơn GIN toàn payload. Nếu cần nhiều đường JSON/predicate phức tạp, GIN có thể phù hợp hơn.

### 20.4. Trigram cho substring search

Nếu hệ thống đã cài extension `pg_trgm` và quyền cho phép, có thể tạo:

~~~sql
-- Chỉ chạy khi extension có sẵn và được phép:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- CREATE INDEX idx_customer_name_trgm_256
-- ON expr_idx_256.customers
-- USING gin (lower(display_name) gin_trgm_ops);
~~~

Sau đó truy vấn:

~~~sql
SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(display_name) LIKE '%anh%';
~~~

Một B-tree expression index `lower(display_name)` thông thường không tự có khả năng tối ưu mọi truy vấn `LIKE '%substring%'`. Trigram GIN/GiST là một lựa chọn cho tìm chuỗi con và similarity, đi kèm chi phí index và độ dài pattern.

**Không gán mọi truy vấn “tìm theo tên” cho B-tree `lower(name)`**, cần phân biệt equality, prefix search và substring/fuzzy search.

### 20.5. Prefix LIKE và text_pattern_ops

Trong nhiều collation không phải `C`, một B-tree thông thường có thể không được planner sử dụng cho tất cả prefix `LIKE 'abc%'`. Một lựa chọn là operator class pattern:

~~~sql
CREATE INDEX idx_customers_name_prefix_256
ON expr_idx_256.customers (
    lower(display_name) text_pattern_ops
);
~~~

Truy vấn:

~~~sql
SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(display_name) LIKE 'anh%';
~~~

Việc dùng index còn tùy collation, pattern, khả năng planner biến điều kiện thành range và kích thước dữ liệu. **`text_pattern_ops` không phải index cho substring ở giữa chuỗi**.

## 21. Expression index và generated column: lựa chọn thiết kế

PostgreSQL hỗ trợ **generated column** trong các phiên bản hiện đại. Một cách thay cho index trực tiếp trên `lower(btrim(email))` là lưu một cột được sinh ra tự động:

~~~sql
ALTER TABLE expr_idx_256.customers
ADD COLUMN normalized_email TEXT
GENERATED ALWAYS AS (
    lower(btrim(email))
) STORED;

CREATE INDEX idx_customers_normalized_column_256
ON expr_idx_256.customers (normalized_email);
~~~

### 21.1. So sánh

| Khía cạnh | Expression index | Stored generated column + index |
| --- | --- | --- |
| Dữ liệu chuẩn hóa lưu ở đâu? | Trong index | Trong hàng và có thể trong index |
| SELECT có thể gọi bằng tên cột đơn giản? | Không trực tiếp; query dùng expression | Có: `normalized_email` |
| Có thể cho nhiều query/ORM dùng chung? | Cần thống nhất expression | Dễ tham chiếu bằng tên cột |
| Có chi phí lưu trữ? | Index | Cột dữ liệu + index |
| Có yêu cầu IMMUTABLE với generated expression? | Có cho index | **Có** với generated expression |
| Dùng làm FK target với unique column phù hợp? | Không trực tiếp theo biểu thức | Có thể thiết kế khóa/unique phù hợp trên cột |
| Đổi quy tắc chuẩn hóa | Cần rebuild index | Cần migration/backfill/recompute theo cách PostgreSQL hỗ trợ |

**Generated column không phải cách lách volatility.** PostgreSQL cũng yêu cầu biểu thức generation hợp lệ, dùng hàm bất biến thích hợp và không tùy ý đọc dữ liệu bảng khác.

### 21.2. Khi nào chọn expression index?

Thường thích hợp nếu:

- Chỉ một vài query cần expression và không cần giá trị như cột riêng;
- Quy tắc biến đổi đơn giản, thực sự immutable;
- Không cần FK/ORM tham chiếu tên normalized field;
- Index trên biểu thức có chọn lọc tốt.

### 21.3. Khi nào chọn generated column?

Có thể hữu ích nếu:

- Nhiều loại query, báo cáo, API cần giá trị đã biến đổi;
- Muốn dễ query/đặt constraint trên cột có tên;
- Cần định nghĩa schema rõ ràng thay vì lặp cùng biểu thức ở nhiều nơi;
- Chấp nhận lưu thêm giá trị và migration cho cột.

### 21.4. Cột được application duy trì

Nếu phép biến đổi phụ thuộc quy tắc thay đổi theo thời gian/dictionary/configuration, một **cột được ghi có kiểm soát** qua application/trigger/job có thể phù hợp hơn generated column hoặc expression index. Khi quy tắc đổi, migration phải **cập nhật lại các giá trị lưu** và xây lại index nếu cần.

Không có một lựa chọn tốt nhất cho mọi trường hợp; tính đúng và khả năng vận hành lâu dài quan trọng hơn chỉ giảm vài dòng SQL.

## 22. Thống kê biểu thức và vai trò ANALYZE

Planner quyết định dùng index dựa trên thống kê:

- Ước lượng số hàng thỏa predicate (selectivity);
- Độ đa dạng giá trị expression;
- Chi phí scan index rồi đọc heap;
- Kích thước bảng/index, số trang, correlation;
- Điều kiện lọc khác, join, sort, LIMIT.

Sau khi tạo index hoặc nạp dữ liệu lớn, chạy:

~~~sql
ANALYZE expr_idx_256.customers;
ANALYZE expr_idx_256.order_lines;
ANALYZE expr_idx_256.events;
~~~

`ANALYZE` thu thập thống kê phục vụ planner, trong đó PostgreSQL có thể thu thập thống kê cho các khóa biểu thức của expression index. Nó **không thay đổi nội dung nghiệp vụ** như một câu UPDATE.

### 22.1. EXPLAIN trên lab

~~~sql
EXPLAIN
SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';
~~~

Đọc các yếu tố:

~~~text
Seq Scan / Index Scan / Bitmap Heap Scan
Index Cond / Filter
estimated rows
estimated cost
~~~

Với bảng có sáu hàng, Seq Scan rất có thể rẻ hơn Index Scan.

### 22.2. EXPLAIN ANALYZE thực thi query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';
~~~

Với `SELECT` thuần lab, lệnh thường an toàn để đo. Nhưng **`EXPLAIN ANALYZE` thực thi câu SQL thật**: dùng nó trên `UPDATE`/`DELETE` trong production khi chưa có kế hoạch là nguy hiểm. Các hàm volatile có side effect trong `SELECT` cũng cần được xem xét trước khi chạy.

### 22.3. Kiểm tra index thực sự đang phục vụ workload không

~~~sql
SELECT
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch
FROM pg_catalog.pg_stat_user_indexes AS s
WHERE s.schemaname = 'expr_idx_256'
ORDER BY s.idx_scan DESC, s.indexrelname;
~~~

`idx_scan=0` không chứng minh index vô ích sau khi chỉ chạy vài câu test: statistics có thể được reset, query plan thay đổi, hoặc chưa có workload đại diện. Cũng không nên xóa index unique chỉ vì số scan thấp: nó còn thực thi **ràng buộc dữ liệu khi ghi**.

## 23. Chi phí INSERT/UPDATE và HOT update

Một expression index có giá trị khi đọc nhanh hơn, nhưng phải tính chi phí khi ghi.

### 23.1. INSERT phải tính khóa index

Với:

~~~sql
CREATE INDEX idx_customers_lower_email_256
ON expr_idx_256.customers (lower(email));
~~~

mỗi hàng mới cần tính `lower(email)` và thêm khóa tương ứng vào index. Nếu có nhiều index biểu thức phức tạp, CPU và I/O ghi có thể tăng đáng kể.

### 23.2. UPDATE làm index maintenance phức tạp

Khi `email` thay đổi, khóa `lower(email)` có thể thay đổi, nên PostgreSQL phải duy trì index đúng với phiên bản hàng mới.

Ví dụ:

~~~sql
BEGIN;

UPDATE expr_idx_256.customers
SET email = 'ANH.NEW@EXAMPLE.COM'
WHERE customer_id = 1;

SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(email) = 'anh.new@example.com';
-- Customer 1 trong transaction.

ROLLBACK;
~~~

### 23.3. HOT (Heap-Only Tuple) update

PostgreSQL có cơ chế **HOT update** giúp tránh tạo index entries mới trong một số trường hợp cập nhật không làm thay đổi những cột mà index phụ thuộc và còn đủ chỗ trong heap page.

Expression index có tham chiếu tới cột `email`. Khi `email` được cập nhật, cơ hội HOT thường bị hạn chế ngay cả khi biểu thức kết quả không đổi theo một quy tắc chuẩn hóa nào đó. Vì vậy **index càng nhiều cột/biểu thức phụ thuộc, càng khó đạt HOT cho workload ghi những cột ấy**.

Không suy ra “thêm expression index chỉ tác động SELECT”. Với bảng nhiều UPDATE/s, chi phí write amplification/HOT là yếu tố thiết kế quan trọng.

### 23.4. Quan sát HOT ở bảng

~~~sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'expr_idx_256'
ORDER BY relname;
~~~

Các thống kê là counter tích lũy từ lúc reset và có thể chịu độ trễ cập nhật. Chúng giúp quan sát workload, không phải chứng minh riêng một expression index là nguyên nhân của mọi thay đổi HOT ratio.

### 23.5. Expression phức tạp có thể tốn CPU build/index maintenance

Hàm chuẩn hóa Unicode phức tạp, xử lý JSON dài hoặc tính hash lớn có thể làm `CREATE INDEX`, `INSERT` và `UPDATE` tốn CPU. Chỉ tạo khi truy vấn cần; tránh đánh chỉ mục biểu thức hiếm dùng hoặc luôn thay đổi.

## 24. CREATE INDEX CONCURRENTLY và vận hành production

Trên bảng production lớn, `CREATE INDEX` thông thường có thể chặn một số hoạt động ghi trong thời gian build. PostgreSQL có:

~~~sql
CREATE INDEX CONCURRENTLY idx_customers_lower_email_conc_256
ON expr_idx_256.customers (lower(email));
~~~

### 24.1. Khác biệt quan trọng

`CREATE INDEX CONCURRENTLY` được thiết kế để giảm việc **chặn ghi kéo dài** khi build index, đổi lại có thể:

- Mất nhiều thời gian hơn;
- Cần nhiều pha/scan và chờ các transaction phù hợp;
- Tăng I/O/CPU trong khi đang hoạt động;
- Để lại **invalid index** nếu quá trình thất bại hoặc bị hủy;
- Có những giới hạn đặc thù, đặc biệt với partitioned tables và transaction block.

**Không chạy trong explicit transaction block**:

~~~sql
-- KHÔNG HỢP LỆ:
-- BEGIN;
-- CREATE INDEX CONCURRENTLY idx_x ON table_x (lower(col));
-- COMMIT;
~~~

### 24.2. Kiểm tra index có valid không

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisvalid AS is_valid,
    i.indisready AS is_ready,
    i.indisunique AS is_unique
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS t
    ON t.oid = i.indrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'expr_idx_256'
ORDER BY index_name;
~~~

- `indisvalid` cho biết index có được xem là hợp lệ cho query/constraints theo trạng thái catalog không.
- `indisready` liên quan index có sẵn sàng cho việc insert/update maintenance không.

Không tự xóa một index invalid khi chưa kiểm tra nó thuộc quy trình build nào và có ảnh hưởng đến uniqueness/locking hay không.

### 24.3. Nếu CONCURRENTLY thất bại

Một runbook thường:

1. Xem log/SQLSTATE nguyên nhân (duplicate với unique, lỗi cast, hủy bởi lock, disk).
2. Xem `pg_index.indisvalid`/`indisready`.
3. Kiểm tra dữ liệu lỗi/khác biểu thức.
4. Chọn phương án **drop invalid index** theo cách/phiên bản phù hợp và tạo lại, hoặc áp dụng công cụ PostgreSQL hỗ trợ rebuild.
5. Xác minh trạng thái valid và plan/constraint sau xây lại.

**Không coi statement tạo index trả lỗi là “không có gì xảy ra”.** Concurrent index build có thể để lại metadata và ảnh hưởng write path cần xử lý.

### 24.4. UNIQUE CONCURRENTLY cần rà soát duplicate trước

Nếu tạo unique index trên `lower(email)` mà dữ liệu đã có hai email khác hoa/thường, build sẽ không thành công. Với concurrent unique build, có những giai đoạn PostgreSQL đã bắt đầu kiểm tra uniqueness ngay cả khi index cuối cùng không valid. Vì vậy triển khai online index **phải** có preflight và kế hoạch xử lý duplicate.

## 25. Kiểm tra định nghĩa expression index trong catalog

### 25.1. pg_indexes: bắt đầu nhanh

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'expr_idx_256'
ORDER BY tablename, indexname;
~~~

`indexdef` hiển thị DDL mô tả index, bao gồm biểu thức, phương thức index, tùy chọn `UNIQUE` và `WHERE` nếu có.

### 25.2. pg_get_indexdef

~~~sql
SELECT
    c.oid::regclass AS index_name,
    pg_catalog.pg_get_indexdef(c.oid) AS create_index_sql
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('i', 'I')
  AND n.nspname = 'expr_idx_256'
ORDER BY index_name;
~~~

### 25.3. Tách biểu thức và partial predicate

~~~sql
SELECT
    idx.indexrelid::regclass AS index_name,
    idx.indrelid::regclass AS table_name,
    pg_catalog.pg_get_expr(
        idx.indexprs,
        idx.indrelid
    ) AS indexed_expressions,
    pg_catalog.pg_get_expr(
        idx.indpred,
        idx.indrelid
    ) AS partial_index_predicate,
    idx.indisunique,
    idx.indisvalid
FROM pg_catalog.pg_index AS idx
JOIN pg_catalog.pg_class AS c
    ON c.oid = idx.indexrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'expr_idx_256'
ORDER BY index_name;
~~~

Ý nghĩa:

- `indexprs`: representation của các **index expressions**, NULL nếu index chỉ trên cột thường.
- `indpred`: predicate của **partial index**, NULL nếu index toàn bảng.
- `indisunique`: unique index hay không.
- `indisvalid`: trạng thái hợp lệ.

Đây là cách tốt để **đọc định nghĩa đã được PostgreSQL lưu**, đặc biệt khi DDL tạo index nằm trong nhiều migration hoặc được ORM sinh tự động.

## 26. Preflight trước khi tạo UNIQUE expression index

Muốn enforce uniqueness theo chuẩn hóa, phải tìm các nhóm trùng trước:

~~~sql
SELECT
    lower(btrim(email)) AS normalized_email,
    COUNT(*) AS row_count,
    ARRAY_AGG(customer_id ORDER BY customer_id)
        AS customer_ids
FROM expr_idx_256.customers
WHERE deleted_at IS NULL
GROUP BY lower(btrim(email))
HAVING COUNT(*) > 1
ORDER BY row_count DESC, normalized_email;
~~~

Với dataset gốc, query không có kết quả. Trên dữ liệu thật, các nhóm có `COUNT(*) > 1` cần được xử lý theo chính sách trước khi tạo unique index.

### 26.1. Chạy thử dữ liệu trùng trong transaction lab

~~~sql
BEGIN;

-- Nếu unique index toàn bảng từ mục 14 vẫn còn,
-- INSERT sau sẽ lỗi ngay. Trên lab hãy chỉ đọc
-- logic preflight thay vì cố làm hỏng constraint.

-- Ví dụ giả lập nếu đang kiểm tra bảng staging không unique:
-- INSERT INTO stage_customers(email)
-- VALUES ('Anh@Example.com'), ('ANH@example.COM');

ROLLBACK;
~~~

**Một index unique đúng phải từ chối dữ liệu trùng mới**, còn preflight là biện pháp giúp migration tránh thất bại bất ngờ khi dữ liệu cũ đã trùng.

### 26.2. Unique dựa trên expression chỉ kiểm tra expression

Nếu index là `UNIQUE(lower(btrim(email)))`, sự bằng nhau được định nghĩa bởi **kết quả biểu thức và collation**. Hai hàng có email gốc khác nhau có thể bị coi trùng. Ngược lại, hai địa chỉ mà người dùng coi “giống nhau” có thể không trùng dưới biểu thức này nếu quy tắc chuẩn hóa chưa bao phủ trường hợp tương ứng.

Vì vậy, việc **định nghĩa canonicalization** là một quyết định nghiệp vụ trước khi tạo index, không thể phó mặc cho `lower` một cách vô điều kiện.

## 27. Khi nào không nên tạo expression index?

### 27.1. Bảng quá nhỏ

Nếu bảng có vài chục hàng, Seq Scan có thể nhanh hơn Index Scan. Tạo thêm index tăng chi phí ghi và bảo trì không cần thiết.

### 27.2. Biểu thức có độ chọn lọc rất thấp

~~~sql
CREATE INDEX idx_customers_is_active_256
ON expr_idx_256.customers (
    (deleted_at IS NULL)
);
~~~

Index này chỉ có hai loại khóa `TRUE` và `FALSE`. Nếu phần lớn khách hàng đều active, query lọc active có thể vẫn phải đọc phần lớn bảng, nên index không mang lại lợi ích nhiều. **Partial index** trên một khóa chọn lọc của tập active thường có ích hơn.

### 27.3. Biểu thức thay đổi logic thường xuyên

Nếu quy tắc tính giá, tỷ giá, quy trình chuẩn hóa tên liên tục thay đổi, index trên hàm đòi hỏi migration/rebuild liên tục. Đôi khi nên giữ các trường dữ liệu gốc và **lưu các giá trị versioned** đã tính, hoặc dùng bảng summary/lookup phù hợp.

### 27.4. Query không dùng biểu thức đó

Nếu API luôn lọc `email = ?` và không bao giờ gọi `lower(email)`, index lower có thể không giúp đường đọc chính. Cần thống kê workload trước khi tạo.

### 27.5. Chi phí ghi lớn hơn lợi ích đọc

Bảng log được insert với tốc độ cao có thể chịu ảnh hưởng đáng kể nếu mỗi dòng phải tính nhiều expression index. Cân nhắc tần suất truy vấn và khả năng dùng BRIN trên cột thời gian, partitioning hoặc xử lý trong hệ thống phân tích thay vì nhiều index B-tree phức tạp.

### 27.6. Không có cơ chế quản trị hàm/collation

Nếu nhiều nhóm có thể sửa UDF “immutable” mà không kiểm soát migration, expression index dựa trên hàm ấy dễ trở thành nguồn lỗi khó tìm. Cần ownership, versioning và runbook REINDEX trước khi đưa vào production.

## 28. Thiết kế kiểm thử expression index

Một bộ kiểm thử tốt không chỉ kiểm tra query trả đúng trên vài hàng:

1. **Đúng biểu thức:** query dùng đúng ngữ nghĩa normalizer/điều kiện.
2. **Đúng NULL:** NULL, chuỗi rỗng, khoảng trắng, giá trị thiếu.
3. **Đúng collation:** Unicode/casefold theo hợp đồng dữ liệu.
4. **Đúng uniqueness:** dữ liệu trùng cần bị từ chối; dữ liệu khác hợp lệ.
5. **Đúng sau UPDATE:** sửa cột nguồn làm khóa index cập nhật.
6. **Đúng sau migration hàm:** rebuild/index mới theo logic version mới.
7. **Đúng sau timezone/collation upgrade:** xác định nhu cầu REINDEX.
8. **Đúng trên số liệu lớn:** planner, latency, buffer/I/O.
9. **Đúng đồng thời:** tạo index online, unique violations và rollback.
10. **Đúng vận hành:** có monitoring invalid index/size/usage.

### 28.1. Test so sánh query Seq Scan và Index Scan

Để học planner, trong lab có thể lấy kết quả query như bình thường, sau đó dùng `EXPLAIN` dưới `SET LOCAL enable_seqscan = off` để xem index path.

**Không ép một plan trên production rồi lấy kết quả nhanh/chậm ở bảng vài hàng làm bằng chứng hiệu năng.** Phân tích đúng cần dữ liệu đại diện và thống kê đầy đủ.

### 28.2. Test hàm volatility bằng catalog

Trước khi đưa UDF vào index, kiểm tra:

~~~sql
SELECT
    p.oid::regprocedure AS signature,
    p.provolatile
FROM pg_catalog.pg_proc AS p
WHERE p.oid =
    'expr_idx_256.normalize_email(text)'::regprocedure;
~~~

Kỳ vọng metadata `provolatile='i'`. Nhưng **kiểm tra metadata không chứng minh hàm thực sự immutable**; code review function vẫn bắt buộc về mặt thiết kế.

## 29. Những lỗi thường gặp

| Hiện tượng / cách hiểu sai | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Có index `email` nên `lower(email)=?` chắc chắn dùng index | Khóa index và expression khác nhau | Index `lower(email)` hoặc query theo email gốc |
| `CREATE INDEX ON t (a+b)` | Biểu thức không phải function call thường cần cặp ngoặc | `ON t ((a+b))` |
| Có `ORDER BY lower(name)` là index cột `name` đủ | Sắp xếp theo expression khác cột gốc | Xem index `lower(name)` và plan |
| `IMMUTABLE` chỉ là cách “hứa” cho planner tối ưu | Nó là hợp đồng ngữ nghĩa mà index phụ thuộc | Đảm bảo thật sự bất biến |
| Hàm `STABLE` “gần như immutable” nên index được | Hôm sau/session khác có thể cho kết quả khác | Không dùng làm khóa/predicate |
| Hàm được khai báo IMMUTABLE thì chắc chắn đúng | PostgreSQL tin khai báo, không phân tích mọi side effect | Review code/dependencies |
| `now()` dùng được trong index vì ổn định trong transaction | Không ổn định qua transaction | Index cột thời gian, query range |
| `random()` dùng được cho index phân bổ ngẫu nhiên | Giá trị thay đổi giữa các lần gọi | Không dùng volatile index expression |
| `timestamptz::date` là immutable | Phụ thuộc session `TimeZone` | Range `timestamptz` hoặc thiết kế ngày có timezone rõ |
| Mọi overload `date_trunc` giống nhau | Overload timestamp và timestamptz khác volatility | Xem `pg_proc` theo chữ ký |
| `PARALLEL SAFE` nghĩa là IMMUTABLE | Hai nhãn khác mục đích | Xem `provolatile` và `proparallel` riêng |
| Dùng `WHERE expires_at > now()` làm partial predicate | Membership của index thay đổi theo thời gian | Index `expires_at` thường |
| `DISTINCT`/`LOWER` giải quyết mọi Unicode/email identity | Canonicalization còn tùy quy tắc và collation | Định nghĩa hợp đồng chuẩn hóa |
| Tạo unique lower(email) và bỏ `NOT NULL` | Nhiều NULL có thể không bị cấm | Ràng buộc NULL đúng yêu cầu |
| Soft-delete unique toàn bảng vẫn cho reuse email | Index toàn bảng vẫn cấm duplicate | Partial unique index theo active |
| Index partial sẽ dùng cho query không lọc active | Thiếu hàng deleted trong index | Query phải hàm ý predicate |
| Planner luôn hiểu hai biểu thức tương đương | Không có bộ chứng minh tổng quát | Dùng expression thống nhất, `EXPLAIN` |
| Tạo index trên text JSON, query cast bigint vẫn như nhau | Kết quả biểu thức có kiểu khác | Index expression theo kiểu truy vấn thực |
| Có GIN JSONB là mọi `->>` equality đều tối ưu | Operator/query form khác nhau | Chọn B-tree expression hoặc GIN đúng mục đích |
| B-tree lower(name) tối ưu `LIKE '%abc%'` | Substring cần phương án khác | Xem pg_trgm/GIN hoặc full-text phù hợp |
| Thay body IMMUTABLE UDF index tự cập nhật | Khóa index cũ có thể stale | Migration + REINDEX hoặc index mới |
| REFRESH VERSION collation là đủ | Metadata đổi nhưng khóa có thể vẫn cũ | Rebuild index phụ thuộc rồi refresh theo runbook |
| Expression index chỉ tăng chi phí đọc | Nó tăng công việc ghi và có thể giảm HOT | Đo write/read trade-off |
| `CREATE INDEX CONCURRENTLY` thất bại không để lại gì | Có thể còn invalid index | Kiểm tra `pg_index` và xử lý |
| `EXPLAIN ANALYZE` luôn chỉ “xem” | Nó thực thi statement | Chỉ đo an toàn trên workload phù hợp |
| Seq Scan trên bảng nhỏ nghĩa index sai | Cost planner có thể đúng khi scan bảng nhỏ | Đo với dữ liệu thực |
| `idx_scan=0` nghĩa có thể xóa unique index | Index còn thực thi ràng buộc | Xem usage lẫn integrity |
| Generated column cho phép hàm STABLE | Generated expression cũng có giới hạn immutability | Chọn thiết kế khác khi logic thay đổi |

## 30. Bài tập thực hành

Các bài tập dùng schema `expr_idx_256` đã tạo. Có bài yêu cầu **dự đoán lỗi thay vì chạy một DDL cố ý sai**. Khi muốn thực hành phá tính unique hoặc thay body hàm, chỉ làm trên database lab và có rollback/migration plan.

### Bài 1 — Định nghĩa expression index

Giải thích sự khác nhau giữa:

~~~sql
CREATE INDEX i1 ON expr_idx_256.customers (email);
CREATE INDEX i2 ON expr_idx_256.customers (lower(email));
~~~

**Gợi ý:** i1 lưu giá trị cột gốc; i2 lưu `lower(email)`. Query dùng `lower(email)` phù hợp với i2 hơn.

### Bài 2 — Tìm email không phân biệt hoa/thường

Viết truy vấn tìm `'ANH@EXAMPLE.COM'` theo biểu thức lower và chỉ mục đã tạo.

**Đáp án mong đợi:** khách hàng ID 1.

### Bài 3 — Dấu ngoặc expression

Điền cú pháp:

~~~sql
CREATE INDEX idx_example
ON expr_idx_256.order_lines (___);
~~~

để index `unit_price * quantity`.

**Đáp án:** `(unit_price * quantity)` nằm trong dấu ngoặc danh sách index, tức `((unit_price * quantity))` ở câu đầy đủ.

### Bài 4 — Query theo thành tiền

Viết query lấy dòng hàng có thành tiền lớn hơn hoặc bằng 300.000.

**Đáp án:** `line_id=3,4,5`.

### Bài 5 — Trích xuất JSONB

Viết expression index trên `(payload ->> 'customer_id')` và query tìm event của customer `'1'`.

**Đáp án:** `event_id=1,3`.

### Bài 6 — Multi-column expression index

Thiết kế index có khóa thứ nhất `event_type`, thứ hai `payload ->> 'customer_id'`. Truy vấn nào nhiều khả năng phù hợp hơn?

1. `WHERE event_type='purchase' AND payload->>'customer_id'='1'`.
2. `WHERE occurred_at > ...`.

**Gợi ý:** index được tạo trên cặp `(event_type, customer_id_extracted)`, không phải trên `occurred_at`.

### Bài 7 — EXPLAIN ở bảng nhỏ

Vì sao `EXPLAIN` có thể chọn `Seq Scan` dù `idx_customers_lower_email_256` đã có?

**Đáp án:** bảng quá nhỏ, scan toàn bảng có chi phí thấp; planner không bắt buộc dùng index.

### Bài 8 — Kiểm tra volatility

Chạy query catalog ở mục 8 và đối chiếu:

- `lower(text)`;
- `now()`;
- `random()`;
- các overload `date_trunc`.

Ghi rõ `provolatile='i'/'s'/'v'` và giải thích ý nghĩa.

### Bài 9 — Vì sao now() bị từ chối?

Hãy giải thích tại sao không thể index:

~~~sql
-- CREATE INDEX i_bad ON events ((now() - occurred_at));
~~~

**Đáp án:** cùng hàng và cùng `occurred_at` nhưng kết quả thay đổi theo thời gian. Hàm `now()` không IMMUTABLE.

### Bài 10 — Đúng điều kiện bảy ngày gần nhất

Viết query chọn sự kiện trong 7 ngày gần nhất với index cột `occurred_at`.

**Gợi ý:** `WHERE occurred_at >= now() - INTERVAL '7 days'`; index lưu cột thời gian, không lưu `now()`.

### Bài 11 — Partial index “chưa hết hạn”

Tại sao:

~~~sql
-- CREATE INDEX ON promotions(id)
-- WHERE expires_at > now();
~~~

không hợp lệ? Đề xuất index cột `expires_at` thay thế.

### Bài 12 — Date từ TIMESTAMPTZ

Cho `occurred_at = TIMESTAMPTZ '2026-11-14 23:30:00+00'`.

**Câu hỏi:** UTC day và ngày ở `Asia/Ho_Chi_Minh` khác nhau thế nào? Vì sao `occurred_at::date` phụ thuộc session timezone?

**Đáp án:** UTC ngày 14, HCMC ngày 15.

### Bài 13 — date_trunc overload

So sánh:

~~~sql
date_trunc('day', TIMESTAMP '2026-11-14 10:15:00')
date_trunc('day', TIMESTAMPTZ '2026-11-14 10:15:00+07')
~~~

Kiểm tra `pg_proc` để thấy volatility của overload tương ứng. Vì sao overload `timestamptz` không phù hợp làm expression index trực tiếp?

### Bài 14 — UDF chuẩn hóa email

Tạo `expr_idx_256.normalize_email(text)` bằng `lower(btrim(input_email))`, khai báo `IMMUTABLE STRICT PARALLEL SAFE`. Viết query tìm email ID 1 với đầu vào có whitespace/chữ hoa.

### Bài 15 — Khai báo sai IMMUTABLE

Một UDF tính `price * exchange_rate` bằng cách đọc tỷ giá trong bảng `exchange_rates` được tác giả đánh dấu IMMUTABLE.

**Câu hỏi:** nếu tỷ giá thay đổi nhưng hàng product không update, vì sao index trên UDF có thể sai? Cần mô hình nào khác?

### Bài 16 — Unique expression index

Tạo unique index `lower(email)` trong lab, thử insert `'ANH@example.COM'` trong savepoint và quan sát `23505`.

**Gợi ý:** nếu migration thực tế, cần preflight duplicate cũ trước khi build unique.

### Bài 17 — NULL và unique

Giả sử cột `email` nullable. Nhiều hàng `email=NULL` có thể tồn tại dưới unique index `lower(email)` mặc định không? Nếu nghiệp vụ cấm email thiếu, ràng buộc nào nên có?

**Đáp án:** nhiều NULL có thể tồn tại; dùng `NOT NULL` nếu phải có email.

### Bài 18 — Partial unique cho active customer

Viết:

~~~sql
CREATE UNIQUE INDEX ...
ON expr_idx_256.customers (
    expr_idx_256.normalize_email(email)
)
WHERE deleted_at IS NULL;
~~~

**Câu hỏi:** tại sao phải gỡ index unique toàn bảng nếu muốn tài khoản soft-deleted được reuse email? Tại sao khôi phục tài khoản cũ có thể bị chặn?

### Bài 19 — Predicate implication

Hai query:

~~~sql
WHERE deleted_at IS NULL
  AND expr_idx_256.normalize_email(email) = 'abc@example.com'
~~~

và:

~~~sql
WHERE expr_idx_256.normalize_email(email) = 'abc@example.com'
~~~

Query nào có thể sử dụng partial index chỉ chứa `deleted_at IS NULL` làm nguồn đầy đủ? Giải thích.

### Bài 20 — Thay đổi UDF

Nhóm phát triển thay cách normalize email. Hãy lập kế hoạch migration gồm preflight collision, index v2/reindex, kiểm tra unique, rollout ứng dụng và rollback.

**Không chỉ `CREATE OR REPLACE FUNCTION` rồi coi index đã được cập nhật.**

### Bài 21 — Collation upgrade

Chạy `pg_collation_actual_version` và so với `collversion` trên database lab.

**Câu hỏi:** khi version khác, tại sao `REFRESH VERSION` không tự sửa khóa B-tree cũ? Cần đánh giá dependency và REINDEX ra sao?

### Bài 22 — Text pattern search

Phân biệt ba query:

~~~sql
WHERE lower(display_name) = 'anh'
WHERE lower(display_name) LIKE 'anh%'
WHERE lower(display_name) LIKE '%anh%'
~~~

Chọn index ứng viên B-tree, B-tree `text_pattern_ops` và GIN trigram khi extension phù hợp. Vì sao B-tree bình thường không tự giải quyết substring giữa chuỗi?

### Bài 23 — Generated column

Thêm cột `normalized_email GENERATED ALWAYS AS (lower(btrim(email))) STORED` trong database lab.

**Câu hỏi:** ưu/nhược so với index `lower(btrim(email))` trực tiếp? Có thể dùng một UDF phụ thuộc `now()` trong generated expression không?

### Bài 24 — HOT update

Một bảng có expression index `lower(email)`. Hai kiểu update:

1. Đổi `display_name`, không đổi `email`.
2. Đổi `email`.

Kiểu nào có cơ hội HOT tốt hơn nếu không có index khác tham chiếu cột đang đổi và đủ chỗ trong trang? Vì sao expression index vẫn ảnh hưởng workload ghi?

### Bài 25 — CONCURRENTLY và invalid index

Nêu lý do `CREATE INDEX CONCURRENTLY` không chạy trong explicit transaction block, khi nào hữu ích và cách kiểm tra `pg_index.indisvalid`/`indisready` sau thất bại.

### Bài 26 — Catalog index expressions

Từ `pg_index`, dùng `pg_get_expr(indexprs, indrelid)` và `pg_get_expr(indpred, indrelid)` để tách khóa biểu thức và partial predicate của các index trong schema lab.

**Câu hỏi:** chỉ mục toàn bảng có `indpred` NULL không? Chỉ mục toàn cột thường có `indexprs` NULL không?

### Bài 27 — Chi phí ghi và index-only scan

Một bảng có 50 triệu hàng và 15 expression indexes, chủ yếu INSERT/UPDATE. Nhóm phát triển muốn thêm 5 expression indexes nữa vì “đọc đôi khi nhanh hơn”.

**Bài tập:** đề xuất các số đo: tần suất query, selectivity, query latency, index size, TPS/commit latency, HOT ratio, VACUUM, WAL, `pg_stat_user_indexes`, kế hoạch rollback.

### Bài 28 — Phân biệt function volatility và parallel safety

Trong `pg_proc`, một hàm có `provolatile='s'` và `proparallel='s'`.

**Câu hỏi:** nó có được dùng trong expression index không? Vì sao “Parallel Safe” không đồng nghĩa “Immutable”?

**Đáp án:** không; index key yêu cầu IMMUTABLE, không phải chỉ an toàn khi chạy trong parallel worker.

### Bài 29 — JSONB cast và dữ liệu lỗi

Hãy thử lập kế hoạch tạo index `((payload ->> 'customer_id')::bigint)`. Điều gì sẽ xảy ra nếu một hàng JSON chứa `"customer_id":"not-a-number"`? Vì sao cần validation trước khi build index và trước lúc insert?

### Bài 30 — Code review tổng hợp

Một lập trình viên đề xuất:

~~~sql
CREATE FUNCTION app.discounted_price(p numeric)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p * (1 - current_setting('app.discount')::numeric)
$$;

CREATE INDEX idx_discounted
ON products (app.discounted_price(price));
~~~

Hãy giải thích:

1. Hàm này có thực sự bất biến nếu cấu hình `app.discount` thay đổi không?
2. Vì sao việc gắn `IMMUTABLE` có thể khiến index chứa khóa cũ?
3. Nên tính giá đã giảm ở thời điểm nào và lưu thế nào?
4. Có nên dùng giá giảm từ một bảng chính sách versioned không?
5. Nếu cần thay quy tắc tính giá, kế hoạch migration/reindex hoặc model mới là gì?
6. Query nào thực sự cần index giá giảm, hay index trên `price` đã đủ sau khi biến đổi ngưỡng lọc?

**Đáp án định hướng:** hàm phụ thuộc session configuration nên không thực sự IMMUTABLE; cần chuyển sang mô hình không thay đổi theo tham số ẩn, hoặc tính/lưu giá đã giảm có version hợp lệ, rồi index một giá trị ổn định.

## 31. Quy trình chọn chỉ mục biểu thức cho sản phẩm thật

Một checklist đề xuất trước khi tạo index production:

1. **Xác định câu query chậm** và truy vấn thực tế dùng biểu thức gì.
2. **Xác định kiểu dữ liệu** của đầu vào/kết quả, implicit casts và collation.
3. **Đánh giá volatility** của mọi hàm/toán tử, kể cả overload và UDF.
4. **Xác định ngữ nghĩa NULL**, dấu cách, Unicode, timezone, JSON malformed.
5. **Kiểm tra index cột thường có thể đủ** bằng cách rewrite thành range predicate hay không.
6. **Chọn index method/operator class** phù hợp: B-tree equality/range, GIN containment/trigram, BRIN cho dữ liệu vật lý có correlation.
7. **Chọn full/partial/unique** dựa trên business rules và query predicate.
8. **Preflight duplicate và dữ liệu cast lỗi** trước unique/index build.
9. **Ước lượng write cost**, bloat, WAL và khả năng HOT update.
10. **Đo EXPLAIN/EXPLAIN ANALYZE trên dữ liệu đại diện**, không chỉ vài hàng lab.
11. **Thiết kế triển khai online**: lock, `CONCURRENTLY`, invalid index, rollback.
12. **Ghi dependency vào migration docs**: UDF version, collation, extension, timezone giả định.
13. **Theo dõi usage và hiệu năng sau triển khai**, không chỉ lúc tạo index.
14. **Có runbook REINDEX/migration** nếu function hoặc collation thay đổi.

### 31.1. Mẫu quyết định nhanh

| Mục tiêu | Lựa chọn khởi đầu |
| --- | --- |
| Đăng nhập email không phân biệt hoa/thường | Unique expression index theo canonicalization được định nghĩa, hoặc cột normalized |
| Lọc đơn theo thời điểm trong 7 ngày gần nhất | B-tree index trên cột `timestamptz` + range query |
| Tìm một thuộc tính text từ JSONB | B-tree expression trên `payload ->> 'field'` |
| Tìm các cấu trúc JSONB chứa object | GIN trên JSONB/operator class phù hợp |
| Lọc thành tiền `unit_price * quantity` | B-tree expression index nếu workload đủ lớn/chọn lọc |
| Chuẩn hóa phụ thuộc tỷ giá/hàm động | Materialized/versioned value hoặc schema nghiệp vụ, không ép IMMUTABLE |
| Tìm chuỗi con `%keyword%` | Cân nhắc `pg_trgm` và GIN/GiST |
| Unique chỉ trong tập chưa soft-delete | Unique partial expression index nếu predicate đúng business rule |

## 32. Tài liệu PostgreSQL chính thức

Khi vận hành, hãy đối chiếu phiên bản PostgreSQL đang dùng:

- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): cơ chế và ví dụ `lower(col)`, `(col1 + col2)`, unique expression index.
- [Function Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html): ý nghĩa `VOLATILE`, `STABLE` và `IMMUTABLE`, tác động tới optimizer/cached plans.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): cú pháp biểu thức, index method, `WHERE`, `INCLUDE`, `CONCURRENTLY` và giới hạn.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): tính hàm ý predicate, uniqueness theo tập con và những giới hạn planner.
- [Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html): vai trò thứ tự khóa B-tree.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, Hash, GiST, SP-GiST, GIN, BRIN và các toán tử hỗ trợ.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html): điều kiện của generated expressions và giới hạn.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html): tái xây index, các biến thể concurrent.
- [The System Catalog pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html): `provolatile`, `proparallel` và metadata hàm.
- [The System Catalog pg_index](https://www.postgresql.org/docs/current/catalog-pg-index.html): `indexprs`, `indpred`, `indisvalid`, `indisready`.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html): quy tắc collation và rủi ro khi version thay đổi.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): cách đọc plan và tác dụng chạy thật của `EXPLAIN ANALYZE`.
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html): các operator class trigram GIN/GiST khi có extension.

Các URL `/docs/current/` trỏ tài liệu của major version hiện hành. Nếu hệ thống cố định PostgreSQL 14, 15, 16, 17, 18 hoặc phiên bản khác, dùng **đúng URL phiên bản** để xác nhận tính năng, cú pháp và giới hạn liên quan.

## 33. Tổng kết

**Chỉ mục biểu thức** cho phép PostgreSQL lưu khóa tính từ một hay nhiều cột, chẳng hạn `lower(email)`, `unit_price * quantity` và `payload ->> 'customer_id'`. Nó có thể giúp lọc, so sánh range, sắp xếp và thực thi **UNIQUE theo giá trị chuẩn hóa**; kết hợp với partial predicate còn có thể định nghĩa uniqueness chỉ cho những hàng hoạt động.

**Điều kiện trọng tâm là tính bất biến:** hàm/toán tử tham gia index key hoặc predicate phải có ngữ nghĩa **`IMMUTABLE`**. `STABLE` chỉ ổn định trong một phạm vi câu lệnh/transaction phù hợp; `VOLATILE` có thể thay đổi giữa các lần gọi. Không được ép hàm phụ thuộc đồng hồ, session timezone, bảng lookup, dictionary thay đổi hoặc cấu hình runtime thành IMMUTABLE chỉ để PostgreSQL cho phép tạo index.

Một expression index **đúng logic hôm nay** cũng cần được bảo trì khi định nghĩa UDF hoặc collation thay đổi. Dữ liệu khóa đã lưu không được tự động tính lại chỉ vì hàm được sửa; đôi khi cần **REINDEX, migration, preflight duplicate và rollout đồng bộ**. Đồng thời, index tăng chi phí ghi, có thể hạn chế HOT update và không được planner chọn nếu bảng nhỏ hoặc predicate không tương thích.

**Nguyên tắc áp dụng:** trước hết hãy xác định **biểu thức nghiệp vụ thực sự ổn định**, sau đó chọn index method, unique/partial predicate và kiểu dữ liệu phù hợp; kiểm tra volatility qua `pg_proc`, định nghĩa qua `pg_index`/`pg_indexes`, đo bằng `EXPLAIN` và quản lý vòng đời function/collation. Hiểu đúng yêu cầu với hàm quan trọng hơn việc tạo ra một chỉ mục có vẻ hoạt động: **index phải luôn giữ cùng ý nghĩa với dữ liệu mà query muốn tìm**.
