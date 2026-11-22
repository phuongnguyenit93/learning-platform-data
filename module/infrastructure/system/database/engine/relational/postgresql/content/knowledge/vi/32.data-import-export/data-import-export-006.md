# Xuất dữ liệu từ bảng hoặc truy vấn trong PostgreSQL

Khi cần gửi dữ liệu PostgreSQL cho một hệ thống khác, phân tích bằng Excel, chuyển cho nhóm BI hoặc tạo một tập dữ liệu phục vụ kiểm toán, bạn cần **xuất dữ liệu** ra một định dạng và một nơi lưu trữ phù hợp. PostgreSQL cung cấp lệnh `COPY ... TO` để xuất dữ liệu trực tiếp từ bảng hoặc kết quả truy vấn. Trong công cụ `psql`, lệnh `\copy ... TO` chuyển dữ liệu qua kết nối rồi ghi file ở máy chạy client.

Hai lệnh có tên gần giống nhưng khác nơi truy cập file:

- **`COPY ... TO '/path/file.csv'`**: PostgreSQL server tự ghi file trên filesystem của máy chủ database. Quyền truy cập file là quyền của tiến trình PostgreSQL.
- **`\copy ... TO 'file.csv'`**: `psql` ghi file ở máy client đang chạy `psql`. Quyền truy cập file là quyền của người dùng máy client; không cần quyền superuser hoặc quyền đọc/ghi file server chỉ để ghi file client.

Phân biệt hai vị trí này đặc biệt quan trọng khi database chạy trên cloud, Docker, Kubernetes hoặc một máy chủ Linux từ xa: đường dẫn `/tmp/export.csv` trong `COPY` là đường dẫn **trên máy server**, còn trong `\copy` là đường dẫn **trên máy chạy psql**.

```text
                   ỨNG DỤNG / psql CLIENT
                            |
                     gửi COPY request
                            |
                            v
                  POSTGRESQL SERVER
                            |
              +-------------+-------------+
              |                           |
          COPY TO file                COPY TO STDOUT
              |                           |
              v                           v
       Filesystem SERVER          protocol qua connection
                                          |
                                          v
                                  psql / client application
                                          |
                                          v
                                   Filesystem CLIENT

        SQL: COPY ... TO '/server/path.csv'
        psql: \copy ... TO 'client/path.csv'
```

Bài thuộc chương **Nhập xuất dữ liệu** của module *Database Engine Relational PostgreSQL*. Nội dung tập trung vào xuất dữ liệu từ bảng hoặc truy vấn, lựa chọn CSV/text/binary, đường dẫn và quyền, cách dùng psql, tính nhất quán khi export nhiều file, bảo vệ dữ liệu nhạy cảm và các lỗi thường gặp.

Sau bài học, bạn có thể:

1. Viết `COPY table TO ...` và `COPY (SELECT ...) TO ...`.
2. Chọn `COPY` server-side hay `\copy` client-side theo vị trí file và quyền thực tế.
3. Xuất một số cột, lọc hàng, JOIN, aggregate, view hoặc partitioned table qua query.
4. Thiết lập CSV header, delimiter, quote, escape, NULL và encoding.
5. Phân biệt CSV, text và binary format.
6. Dùng `psql \copy`, `\o`, `\g filename` và output CSV của psql đúng mục đích.
7. Hiểu quyền `SELECT`, quyền file server và các predefined roles có liên quan.
8. Xuất dữ liệu có RLS theo đúng role/policy, không vô tình xuất vượt phạm vi.
9. Tổ chức snapshot và file staging khi cần xuất nhiều tập dữ liệu nhất quán.
10. Nhận diện rủi ro CSV formula injection, lộ dữ liệu, file dở dang và export quá lớn.

> **Môi trường thực hành:** Các ví dụ dùng schema thử nghiệm `export_lab`. Hãy chạy trong database phát triển/test và thay đường dẫn file bằng một thư mục tồn tại, có quyền ghi trên đúng máy. Những ví dụ server-side file và `PROGRAM` chỉ dùng để học cú pháp; không cấp quyền rộng hoặc chạy trên production khi chưa đánh giá.

---

## 1. Vì sao cần xuất dữ liệu?

### 1.1. Những tình huống phổ biến

- Xuất danh sách đơn hàng theo khoảng ngày để phân tích.
- Tạo CSV giao cho đối tác hoặc hệ thống kế toán.
- Xuất dữ liệu tổng hợp theo khách hàng, sản phẩm hoặc tháng.
- Chuyển kết quả query từ database server về laptop của analyst.
- Tạo file staging để chuyển sang data warehouse.
- Lưu một bản trích xuất có kiểm soát phục vụ kiểm toán.
- Xuất dữ liệu từ materialized view đã refresh.
- Lấy một tập rows từ partitioned table mà không cần dump toàn database.

### 1.2. Export khác backup

| Nhu cầu | Công cụ thường phù hợp |
|---|---|
| Xuất một bảng hoặc kết quả query thành CSV/text | `COPY` hoặc `\copy` |
| Xuất dữ liệu chọn lọc theo WHERE/JOIN | `COPY (SELECT ...) TO` |
| Backup logic một database/schema/object | `pg_dump` |
| Backup toàn cluster, roles và database objects | `pg_dumpall` hoặc giải pháp backup phù hợp |
| Xuất một tập JSON/JSONL | Query dùng `json_build_object`/`row_to_json` rồi `COPY` |
| Lấy file Excel XLSX | Xuất CSV rồi chuyển đổi bằng công cụ spreadsheet/ETL |

`COPY` không phải công cụ backup đầy đủ. Nó xuất giá trị của các cột trong tập kết quả, không tự lưu schema, indexes, constraints, grants, triggers hoặc toàn bộ metadata của bảng.

### 1.3. Export là một hợp đồng dữ liệu

Một file CSV không chỉ là “các cột được ngăn bởi dấu phẩy”. Người nhận cần biết:

- Tên và thứ tự cột.
- Kiểu dữ liệu và định dạng ngày/giờ.
- Quy tắc NULL và chuỗi rỗng.
- Encoding.
- Đơn vị tiền tệ, timezone và precision.
- Thứ tự rows nếu downstream phụ thuộc thứ tự.
- Phạm vi dữ liệu và thời điểm snapshot.
- Version/schema của file.

Với dữ liệu dùng giữa các hệ thống, hãy coi định dạng export là một **data contract** được phiên bản hóa.

---

## 2. Chuẩn bị schema và dữ liệu thực hành

### 2.1. Tạo schema

```sql
CREATE SCHEMA export_lab;
```

Nếu schema đã tồn tại, hãy dùng database test mới hoặc kiểm tra quyền sở hữu; không xóa schema của người khác để chạy lại bài.

### 2.2. Tạo bảng customers

```sql
CREATE TABLE export_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email TEXT,
    tenant_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
```

### 2.3. Tạo bảng orders

```sql
CREATE TABLE export_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES export_lab.customers(customer_id),
    tenant_id INTEGER NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'paid', 'cancelled')),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0),
    note TEXT
);

CREATE INDEX orders_tenant_ordered_at_idx
ON export_lab.orders (tenant_id, ordered_at);
```

### 2.4. Nạp dữ liệu mẫu

```sql
INSERT INTO export_lab.customers
    (customer_id, customer_name, email, tenant_id, created_at)
VALUES
    (1, 'Nguyen An', 'an@example.test', 10,
        TIMESTAMPTZ '2026-01-03 08:00:00+00'),
    (2, 'Tran Binh', NULL, 10,
        TIMESTAMPTZ '2026-01-05 09:30:00+00'),
    (3, 'Le Chi', 'chi@example.test', 20,
        TIMESTAMPTZ '2026-02-01 10:15:00+00');

INSERT INTO export_lab.orders
    (order_id, customer_id, tenant_id, ordered_at,
     status, amount, note)
VALUES
    (1001, 1, 10, TIMESTAMPTZ '2026-02-01 01:00:00+00',
     'paid', 120.50, 'First order'),
    (1002, 1, 10, TIMESTAMPTZ '2026-02-02 02:30:00+00',
     'draft', 80.00, 'Needs review, urgent'),
    (1003, 2, 10, TIMESTAMPTZ '2026-02-03 04:00:00+00',
     'paid', 250.00, 'Contains "special" item'),
    (2001, 3, 20, TIMESTAMPTZ '2026-02-04 06:00:00+00',
     'paid', 999.99, E'First line\nSecond line');
```

### 2.5. Kiểm tra dữ liệu

```sql
SELECT *
FROM export_lab.customers
ORDER BY customer_id;

SELECT *
FROM export_lab.orders
ORDER BY order_id;
```

Dữ liệu có email NULL, ghi chú chứa dấu phẩy, dấu nháy kép và newline để bạn thấy CSV cần quote/escape như thế nào.

---

## 3. Lệnh SQL COPY TO

### 3.1. Cú pháp cơ bản

```sql
COPY table_name
TO 'absolute_server_path'
WITH (FORMAT csv, HEADER true);
```

Hoặc xuất kết quả truy vấn:

```sql
COPY (
    SELECT ...
) TO 'absolute_server_path'
WITH (FORMAT csv, HEADER true);
```

Điểm quan trọng:

- `COPY table TO` xuất rows của một relation được hỗ trợ.
- `COPY (query) TO` xuất kết quả của query.
- Query phải đặt trong dấu ngoặc đơn sau `COPY`.
- `TO 'path'` ghi file trực tiếp trên server.
- `TO STDOUT` truyền dữ liệu qua connection tới client.
- `WITH (FORMAT csv, HEADER true)` chọn CSV và ghi header.

### 3.2. Xuất toàn bộ bảng

```sql
COPY export_lab.orders
TO '/var/lib/postgresql/exports/orders.csv'
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
```

Đường dẫn trên là **ví dụ server-side**. Thư mục `/var/lib/postgresql/exports` phải tồn tại trên máy chạy PostgreSQL và tiến trình PostgreSQL phải có quyền ghi.

### 3.3. COPY TO không tự bảo đảm thứ tự rows

Nếu cần thứ tự ổn định, dùng query:

```sql
COPY (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        status,
        amount
    FROM export_lab.orders
    ORDER BY order_id
) TO '/var/lib/postgresql/exports/orders_sorted.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
```

Không dựa vào thứ tự vật lý của heap, primary key hay index để kết luận output luôn được sắp xếp. **Chỉ `ORDER BY` trong query mới biểu diễn thứ tự mong muốn.**

### 3.4. Xuất một số cột

```sql
COPY export_lab.orders (
    order_id,
    customer_id,
    ordered_at,
    amount
)
TO '/var/lib/postgresql/exports/order_amounts.csv'
WITH (FORMAT csv, HEADER true);
```

Chỉ các cột liệt kê được xuất. Cột `note` và `tenant_id` không xuất trong file này.

### 3.5. Vì sao nên chọn cột tường minh?

```sql
COPY export_lab.orders TO ...;
```

xuất mọi cột phù hợp của bảng. Khi schema thêm cột mới như `internal_comment` hoặc `payment_token_reference`, lệnh không liệt kê cột có thể vô tình đưa thêm dữ liệu vào file.

Với export dùng lâu dài hoặc giao cho bên ngoài, nên dùng **column list hoặc SELECT list tường minh**.

---

## 4. Xuất dữ liệu từ truy vấn SELECT

### 4.1. Lọc theo trạng thái

```sql
COPY (
    SELECT
        order_id,
        ordered_at,
        status,
        amount
    FROM export_lab.orders
    WHERE status = 'paid'
    ORDER BY ordered_at, order_id
) TO '/var/lib/postgresql/exports/paid_orders.csv'
WITH (FORMAT csv, HEADER true);
```

`COPY (SELECT ...) TO` hữu ích khi export cần WHERE, ORDER BY, JOIN, aggregate, expression hoặc masking.

### 4.2. Lọc theo khoảng thời gian

```sql
COPY (
    SELECT
        order_id,
        tenant_id,
        ordered_at,
        amount
    FROM export_lab.orders
    WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
      AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
    ORDER BY ordered_at, order_id
) TO '/var/lib/postgresql/exports/february_orders.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
```

Dùng khoảng nửa mở `[start, end)` thường tránh phải tính “giây cuối cùng” của ngày và phù hợp với timestamp có độ chính xác cao.

### 4.3. JOIN nhiều bảng

```sql
COPY (
    SELECT
        o.order_id,
        c.customer_name,
        c.email,
        o.ordered_at,
        o.status,
        o.amount
    FROM export_lab.orders AS o
    JOIN export_lab.customers AS c
      ON c.customer_id = o.customer_id
     AND c.tenant_id = o.tenant_id
    WHERE o.tenant_id = 10
    ORDER BY o.order_id
) TO '/var/lib/postgresql/exports/tenant_10_orders.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
```

Header của query output lấy tên cột/alias trong SELECT. Dùng alias rõ ràng để data consumer có schema dễ hiểu.

### 4.4. Aggregate theo tenant

```sql
COPY (
    SELECT
        tenant_id,
        status,
        COUNT(*) AS order_count,
        SUM(amount) AS total_amount
    FROM export_lab.orders
    GROUP BY tenant_id, status
    ORDER BY tenant_id, status
) TO '/var/lib/postgresql/exports/order_summary.csv'
WITH (FORMAT csv, HEADER true);
```

### 4.5. Export expression và alias

```sql
COPY (
    SELECT
        order_id,
        amount,
        amount * 1.08 AS amount_with_tax,
        upper(status) AS status_code
    FROM export_lab.orders
    ORDER BY order_id
) TO '/var/lib/postgresql/exports/order_calculated.csv'
WITH (FORMAT csv, HEADER true);
```

Đây là output đã tính toán; không có cột vật lý `amount_with_tax` hoặc `status_code` trong bảng gốc.

### 4.6. Xuất view

```sql
CREATE VIEW export_lab.paid_order_report AS
SELECT
    o.order_id,
    c.customer_name,
    o.ordered_at,
    o.amount
FROM export_lab.orders AS o
JOIN export_lab.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'paid';

COPY (
    SELECT *
    FROM export_lab.paid_order_report
    ORDER BY order_id
) TO '/var/lib/postgresql/exports/paid_order_report.csv'
WITH (FORMAT csv, HEADER true);
```

`COPY table TO` trực tiếp không hỗ trợ mọi loại relation như view hoặc partitioned table; dùng `COPY (SELECT ...) TO` cho những trường hợp đó.

### 4.7. Partitioned table

Nếu bảng là partitioned table, query:

```sql
COPY (
    SELECT *
    FROM app.events
    WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
    ORDER BY event_time, event_id
) TO '/var/lib/postgresql/exports/events.csv'
WITH (FORMAT csv, HEADER true);
```

cho phép PostgreSQL truy vấn partitioned parent và các partitions phù hợp. Dùng trực tiếp `COPY app.events TO ...` không tương đương cách query tổng quát này.

### 4.8. COPY query từ materialized view

`COPY table TO` có thể xuất populated materialized view. Nếu cần lọc/sắp xếp, query form vẫn rõ ràng:

```sql
COPY (
    SELECT *
    FROM reporting.monthly_sales
    WHERE month_start >= DATE '2026-01-01'
    ORDER BY month_start, tenant_id
) TO '/var/lib/postgresql/exports/monthly_sales.csv'
WITH (FORMAT csv, HEADER true);
```

### 4.9. SELECT DISTINCT hoặc UNION

```sql
COPY (
    SELECT DISTINCT customer_id
    FROM export_lab.orders
    ORDER BY customer_id
) TO '/var/lib/postgresql/exports/order_customers.csv'
WITH (FORMAT csv, HEADER true);
```

`COPY (query) TO` xuất kết quả query như một tập rows; mọi semantics của query như DISTINCT, UNION, GROUP BY và JOIN vẫn do PostgreSQL xử lý.

---

## 5. COPY TO server file và quyền truy cập

### 5.1. Server và client là hai máy khác nhau

Giả sử:

```text
Laptop analyst:
    C:\Users\analyst\Downloads

Database server:
    /var/lib/postgresql/data
```

Lệnh:

```sql
COPY export_lab.orders
TO '/tmp/orders.csv'
WITH (FORMAT csv, HEADER true);
```

ghi `/tmp/orders.csv` trên **database server**, không phải laptop analyst.

### 5.2. OS user của PostgreSQL

Server-side COPY mở file dưới OS identity mà PostgreSQL server process đang chạy (thường là user hệ thống `postgres` trên Linux). User đăng nhập database không tự có quyền ghi mọi thư mục trên server.

Ngay cả khi SQL role có `SELECT` trên bảng, lệnh ghi server file vẫn cần:

- Đường dẫn server tồn tại/được truy cập.
- OS permissions cho PostgreSQL process.
- Quyền PostgreSQL phù hợp cho server-side file operation.

### 5.3. Predefined roles

Những quyền PostgreSQL có liên quan:

| Role | Khả năng chính |
|---|---|
| `pg_write_server_files` | Ghi file ở những vị trí server process có thể truy cập qua các chức năng file/COPY |
| `pg_read_server_files` | Đọc file server qua các chức năng file/COPY |
| `pg_execute_server_program` | Thực thi chương trình trên server qua những chức năng cho phép |

Các roles này có quyền mạnh, không nên grant cho role ứng dụng chỉ để tải một file CSV.

### 5.4. Quyền ghi file và quyền đọc bảng là hai lớp

Để chạy:

```sql
COPY export_lab.orders
TO '/server/path/orders.csv'
WITH (FORMAT csv, HEADER true);
```

cần quyền SELECT thích hợp trên cột/bảng **và** quyền server-file operation phù hợp khi đích là file server. `GRANT SELECT` không tự cấp quyền ghi filesystem; ngược lại, có `pg_write_server_files` không tự cấp SELECT trên mọi bảng.

### 5.5. Không grant pg_write_server_files tùy tiện

Role này có thể ghi file ở phạm vi filesystem mà PostgreSQL process được OS cho phép. Đây là một quyền rộng, có thể ảnh hưởng file cấu hình, dữ liệu ứng dụng hoặc những vị trí nhạy cảm nếu OS permissions không được khóa tốt.

Nếu chỉ muốn analyst xuất file về máy cá nhân, **`\copy` thường là lựa chọn phù hợp hơn**.

### 5.6. Đường dẫn phải tuyệt đối khi COPY TO file

PostgreSQL yêu cầu output filename của `COPY TO` là absolute path. Điều này tránh hiểu nhầm current directory của server process.

### 5.7. Ví dụ Windows server path

Nếu PostgreSQL server chạy trên Windows, một ví dụ dạng:

```sql
COPY export_lab.orders
TO E'C:\\postgres_exports\\orders.csv'
WITH (FORMAT csv, HEADER true);
```

được diễn giải từ filesystem của máy server Windows. Hãy kiểm tra escaping và quyền của service account PostgreSQL.

---

## 6. COPY TO STDOUT và psql \copy

### 6.1. COPY TO STDOUT

```sql
COPY (
    SELECT order_id, amount
    FROM export_lab.orders
    ORDER BY order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

`STDOUT` nghĩa là PostgreSQL gửi dữ liệu qua connection cho client. Server không tự chọn file đích.

### 6.2. psql \copy

Trong `psql`:

```text
\copy export_lab.orders TO 'orders.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

`\copy` dùng cơ chế frontend copy: psql nhận data từ server và ghi file trên **máy đang chạy psql**.

### 6.3. Xuất query result bằng \copy

```text
\copy (SELECT order_id, customer_id, ordered_at, status, amount FROM export_lab.orders WHERE status = 'paid' ORDER BY order_id) TO 'paid_orders.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

Phần query phải nằm trong ngoặc. Đây là cách thường dùng để xuất query tùy biến trực tiếp về máy analyst.

### 6.4. Đường dẫn tương đối

Với `\copy`, filename được truy cập từ phía client. Nếu bạn viết:

```text
\copy (SELECT order_id, amount FROM export_lab.orders) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
```

file được ghi vào working directory hiện tại của tiến trình psql. Có thể xem/thay thư mục bằng meta-command:

```text
\! pwd
\cd /path/to/export
```

`\! pwd` là lệnh shell thông qua psql và phụ thuộc OS. Trên Windows có thể dùng đường dẫn client Windows phù hợp.

### 6.5. Ví dụ đường dẫn client Windows

```text
\copy (SELECT order_id, amount FROM export_lab.orders ORDER BY order_id) TO 'C:/Users/analyst/Downloads/orders.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

File nằm trên máy chạy psql. Nếu psql đang chạy trong container, path phải tồn tại trong container và được mount nếu cần lấy file về host.

### 6.6. Không cần superuser chỉ để ghi file client

`\copy` chuyển data qua connection. Người dùng vẫn cần quyền SQL SELECT thích hợp trên query, và client process cần quyền ghi file ở local destination; nhưng không cần `pg_write_server_files` chỉ để tạo file local.

### 6.7. Quy tắc parser riêng của \copy

Khác nhiều psql meta-commands, toàn bộ phần còn lại của dòng sau `\copy` được coi là tham số. Vì thế:

- Viết lệnh `\copy` trên một dòng rõ ràng.
- Không trông đợi psql variable interpolation như `:myvar` trong phần arguments.
- Không trông đợi backquote expansion.
- Cẩn thận với dấu nháy trong query/path.

Nếu cần SQL động phức tạp, hãy tạo query/function đã kiểm soát hoặc dùng client API phù hợp, không cố ghép input không tin cậy vào một dòng `\copy`.

### 6.8. COPY count

SQL COPY thường trả command tag:

```text
COPY 4
```

Số 4 là số rows đã xuất. Với `COPY TO STDOUT` hoặc `\copy ... TO stdout`, psql có thể không in command tag để tránh trộn dòng trạng thái vào dữ liệu output.

---

## 7. COPY server file, \copy client file và PROGRAM

| Cú pháp | Nơi đọc/ghi file hoặc chạy command | Quyền liên quan |
|---|---|---|
| `COPY table TO '/path/file'` | Server filesystem | SQL SELECT + server-file permission/OS access |
| `COPY (query) TO STDOUT` | Data qua connection | SQL SELECT |
| `\copy table TO 'file'` | Client filesystem của psql | SQL SELECT + quyền ghi local |
| `COPY (query) TO PROGRAM 'cmd'` | Command chạy trên server | SQL SELECT + `pg_execute_server_program`/quyền phù hợp |
| `\copy (query) TO PROGRAM 'cmd'` | Command chạy trên client nơi psql chạy | SQL SELECT + quyền chạy local command |

### 7.1. COPY TO PROGRAM server-side

```sql
-- Chỉ minh họa, không chạy tùy tiện:
-- COPY (
--     SELECT order_id, amount
--     FROM export_lab.orders
-- ) TO PROGRAM 'gzip > /var/lib/postgresql/exports/orders.csv.gz'
-- WITH (FORMAT csv, HEADER true);
```

PostgreSQL gọi command qua shell trên máy server. Người có thể tác động command string có thể gây hậu quả lớn. Không ghép user input vào `PROGRAM`.

### 7.2. \copy PROGRAM client-side

```text
-- Ví dụ minh họa cho client Unix có gzip:
\copy (SELECT order_id, amount FROM export_lab.orders) TO PROGRAM 'gzip > orders.csv.gz' WITH (FORMAT csv, HEADER true)
```

Ở đây command được chạy bởi tiến trình psql trên client. Nó không phải command chạy dưới OS account của PostgreSQL server.

### 7.3. PROGRAM và shell injection

Không tạo command như:

```text
PROGRAM 'gzip > ' || user_supplied_path
```

để chạy với input không tin cậy. Shell có các ký tự điều khiển như `;`, `$()`, dấu nháy và pipe. Nếu cần file path động, dùng API file của client hoặc cơ chế process invocation với argument list đã tách/quote an toàn, kèm allowlist.

### 7.4. Nên ưu tiên đường đơn giản

Nếu chỉ cần một CSV local, thường:

```text
\copy (SELECT ...) TO 'file.csv' WITH (FORMAT csv, HEADER true)
```

là đủ. Không cần server-side PROGRAM hoặc cấp quyền OS rộng.

---

## 8. Chọn định dạng: CSV, text hay binary

| Format | Đặc điểm | Phù hợp |
|---|---|---|
| `text` | Mỗi row một dòng, delimiter mặc định tab, escape bằng backslash | Trao đổi PostgreSQL/text, file đơn giản |
| `csv` | Quy tắc quote/escape phổ biến, hỗ trợ spreadsheet/ETL | Trao đổi giữa nhiều công cụ |
| `binary` | Dạng nhị phân theo kiểu dữ liệu PostgreSQL | Một số pipeline PostgreSQL-to-PostgreSQL cần hiệu năng/kiểu chính xác |

### 8.1. CSV là lựa chọn phổ biến

```sql
COPY (
    SELECT order_id, customer_id, amount
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

CSV dễ đọc, hỗ trợ Excel/LibreOffice/ETL và có quy tắc quote cho dấu phẩy, newline, dấu nháy.

### 8.2. Text format

```sql
COPY (
    SELECT order_id, customer_id, amount
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT text, DELIMITER E'\t', NULL '\\N');
```

Text format mặc định dùng tab làm delimiter và `\N` biểu diễn NULL. Backslash, tab, newline và carriage return trong giá trị cần được escape theo quy tắc COPY text.

### 8.3. Binary format

```sql
COPY export_lab.orders
TO '/var/lib/postgresql/exports/orders.bin'
WITH (FORMAT binary);
```

Binary format có thể giữ representation dữ liệu hiệu quả, nhưng:

- Không thể mở trực tiếp bằng Excel như CSV.
- Không có header CSV.
- Không hỗ trợ delimiter, NULL string, quote/escape như text/CSV.
- Phụ thuộc type send/receive functions và format version.
- Kém portable giữa hệ thống/phiên bản/kiểu dữ liệu khác nhau.

Không chọn binary chỉ vì nghĩ file nhỏ hơn trong mọi trường hợp. Hãy benchmark và xác nhận consumer hỗ trợ đúng format.

### 8.4. CSV không phải XLSX

PostgreSQL không xuất trực tiếp file Excel workbook `.xlsx` bằng `COPY`. Nếu cần XLSX, xuất CSV rồi dùng thư viện/công cụ phía client tạo workbook. CSV không lưu nhiều sheet, styles, formulas hoặc cell types như XLSX.

---

## 9. Cấu hình CSV: delimiter, quote và escape

### 9.1. Mặc định

CSV mặc định:

- Delimiter: dấu phẩy `,`.
- Quote: dấu nháy kép `"`.
- Escape: cùng ký tự quote, tức quote bên trong giá trị được nhân đôi.

### 9.2. Giá trị có dấu phẩy

Dữ liệu:

```text
note = Needs review, urgent
```

CSV output:

```csv
"Needs review, urgent"
```

### 9.3. Giá trị có dấu nháy kép

Dữ liệu:

```text
Contains "special" item
```

CSV output:

```csv
"Contains ""special"" item"
```

### 9.4. Giá trị có newline

Một giá trị text có newline có thể được quote thành một field trải qua nhiều dòng vật lý:

```csv
"First line
Second line"
```

Vì vậy **không dùng đếm số dòng văn bản để đếm số records CSV**. Một record có thể chứa newline nằm trong field được quote.

### 9.5. Tùy chỉnh delimiter

```sql
COPY (
    SELECT order_id, customer_id, amount
    FROM export_lab.orders
) TO STDOUT
WITH (
    FORMAT csv,
    DELIMITER ';',
    HEADER true
);
```

Delimiter phải là một ký tự một byte. CSV dùng dấu chấm phẩy có thể phù hợp với một số locale spreadsheet, nhưng consumer phải biết delimiter.

### 9.6. Tùy chỉnh quote và escape

```sql
COPY (
    SELECT order_id, note
    FROM export_lab.orders
) TO STDOUT
WITH (
    FORMAT csv,
    QUOTE '"',
    ESCAPE '"',
    HEADER true
);
```

Chỉ thay quote/escape khi data contract yêu cầu. Mặc định thường tương thích hơn với các CSV consumers phổ biến.

### 9.7. FORCE_QUOTE

```sql
COPY (
    SELECT
        customer_id,
        customer_name,
        email
    FROM export_lab.customers
) TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    FORCE_QUOTE (email)
);
```

`FORCE_QUOTE` chỉ áp dụng cho `COPY TO` CSV. Nó bắt buộc quote các giá trị **không NULL** của cột chỉ định. NULL output không bao giờ được quote.

Có thể dùng `FORCE_QUOTE *` để quote mọi non-NULL values:

```sql
COPY (
    SELECT order_id, status, note
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT csv, HEADER true, FORCE_QUOTE *);
```

### 9.8. FORCE_NULL và FORCE_NOT_NULL không phải tùy chọn output

`FORCE_NULL` và `FORCE_NOT_NULL` dành cho **COPY FROM** CSV, tức nhập dữ liệu. Khi xuất, dùng `NULL` và `FORCE_QUOTE` nếu cần biểu diễn NULL/chuỗi.

---

## 10. NULL và chuỗi rỗng trong CSV

### 10.1. CSV cần phân biệt NULL và empty string

Hai giá trị:

```text
SQL NULL
empty string ''
```

không giống nhau. PostgreSQL CSV mặc định phân biệt:

```csv

""
```

Trong ví dụ này:

- Field trống không quote biểu diễn NULL.
- Field `""` biểu diễn chuỗi rỗng.

### 10.2. Ví dụ export

```sql
COPY (
    SELECT
        customer_id,
        email
    FROM export_lab.customers
    ORDER BY customer_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

Customer 2 có email NULL; file sẽ thể hiện NULL theo quy tắc CSV mặc định.

### 10.3. Đặt NULL string riêng

```sql
COPY (
    SELECT customer_id, email
    FROM export_lab.customers
) TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    NULL 'NULL'
);
```

Lúc này SQL NULL được xuất thành token NULL không quote. Một giá trị text thực sự bằng chuỗi `NULL` sẽ được quote để phân biệt.

### 10.4. Consumer phải dùng cùng data contract

Nếu một pipeline import lại CSV, cần chọn đúng NULL string. Không tự coi chuỗi `NULL` là SQL NULL nếu export đã dùng default empty unquoted hoặc một quy ước khác.

### 10.5. Đừng xóa NULL thành chuỗi rỗng vô tình

Query:

```sql
SELECT COALESCE(email, '') AS email
FROM export_lab.customers;
```

đã biến SQL NULL thành empty string **trong kết quả query**. Điều này thay đổi ngữ nghĩa file. Chỉ làm khi data contract muốn như vậy.

---

## 11. Header, tên cột và thứ tự cột

### 11.1. HEADER true

```sql
COPY (
    SELECT
        order_id AS id,
        ordered_at AS order_time,
        amount AS total_amount
    FROM export_lab.orders
    ORDER BY order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

Dòng đầu sẽ chứa alias:

```csv
id,order_time,total_amount
```

### 11.2. Không có HEADER

```sql
COPY (
    SELECT order_id, amount
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT csv, HEADER false);
```

Dùng khi consumer đã có schema theo vị trí hoặc format yêu cầu không header. Không bỏ header chỉ vì file ngắn.

### 11.3. Tên cột là một phần của API

Thay alias `total_amount` thành `amount` có thể làm downstream mapping thất bại. Hãy coi tên và thứ tự header là contract; version hóa khi thay đổi.

### 11.4. Header không ghi kiểu dữ liệu

CSV header chỉ có tên cột, không chứa type, nullability, precision, timezone hay units. Nếu cần schema machine-readable, xuất thêm metadata/schema file hoặc dùng định dạng có schema như Parquet qua công cụ ETL phù hợp.

---

## 12. Encoding và định dạng ngày giờ

### 12.1. UTF-8

Với tiếng Việt và dữ liệu đa ngôn ngữ, thường chọn UTF-8:

```sql
COPY (
    SELECT customer_id, customer_name, email
    FROM export_lab.customers
) TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
```

### 12.2. Client encoding

Nếu bỏ `ENCODING`, COPY dùng client encoding hiện tại. Trong psql có thể xem/đặt:

```text
\encoding
\encoding UTF8
```

`ENCODING` của COPY mô tả encoding dữ liệu file; việc chuyển đổi được thực hiện theo cấu hình server/client và encoding đã chỉ định.

### 12.3. Không nhầm server encoding và file encoding

`SHOW server_encoding;` cho biết encoding database. File export có thể dùng encoding khác nếu PostgreSQL hỗ trợ chuyển đổi. Nếu ký tự không biểu diễn được trong encoding đích, COPY có thể báo lỗi.

### 12.4. DateStyle

COPY text/CSV xuất các giá trị qua output functions của kiểu dữ liệu. Định dạng date/time có thể chịu ảnh hưởng GUC như `DateStyle` và `TimeZone`.

Để export portable, có thể đặt:

```sql
BEGIN;

SET LOCAL DateStyle = 'ISO, YMD';
SET LOCAL TimeZone = 'UTC';

COPY (
    SELECT
        order_id,
        ordered_at,
        amount
    FROM export_lab.orders
    ORDER BY order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COMMIT;
```

Đây là mẫu SQL server-side COPY TO STDOUT; client phải nhận stream và lưu file. Nếu dùng `\copy`, có thể đặt các SET LOCAL trong transaction trước `\copy`.

### 12.5. TIMESTAMPTZ

`TIMESTAMPTZ` biểu diễn một thời điểm. Giá trị hiển thị theo `TimeZone` hiện hành. Cùng một instant có thể xuất thành chuỗi giờ khác nhau theo timezone:

```sql
BEGIN;
SET LOCAL TimeZone = 'UTC';
SELECT ordered_at FROM export_lab.orders;
SET LOCAL TimeZone = 'Asia/Ho_Chi_Minh';
SELECT ordered_at FROM export_lab.orders;
ROLLBACK;
```

Nếu consumer cần timestamp nhất quán, quy định timezone trong data contract, thường là UTC.

### 12.6. INTERVAL

PostgreSQL khuyến nghị chú ý `IntervalStyle` khi xuất dữ liệu cần portable; một số định dạng interval có thể bị diễn giải khác nếu server nhận có cấu hình khác. Nếu export interval cho hệ thống khác, hãy chuẩn hóa sang một representation rõ ràng hoặc quy định style.

### 12.7. BOM cho spreadsheet

`COPY ENCODING 'UTF8'` xuất UTF-8, nhưng không nên mặc định rằng mọi consumer Excel cần hoặc sẽ nhận BOM. Hãy kiểm tra consumer mục tiêu. Nếu cần BOM để tương thích một công cụ cũ, thêm BOM ở bước xử lý file phía client theo data contract; đừng chèn ký tự BOM vào từng field.

---

## 13. Xuất JSON/JSONL từ query

COPY hỗ trợ các format text, CSV và binary. Để tạo JSON, có thể tạo **một cột text/json expression** rồi dùng text output.

### 13.1. Một JSON object mỗi dòng (JSONL)

```sql
COPY (
    SELECT row_to_json(q)
    FROM (
        SELECT
            order_id,
            customer_id,
            ordered_at,
            status,
            amount
        FROM export_lab.orders
        ORDER BY order_id
    ) AS q
) TO STDOUT;
```

Mỗi row tạo một JSON object trên một dòng. Đây là dạng JSON Lines/NDJSON ở mức cấu trúc; consumer cần biết một dòng là một object.

### 13.2. Một JSON array duy nhất

```sql
COPY (
    SELECT COALESCE(
        json_agg(
            json_build_object(
                'order_id', order_id,
                'customer_id', customer_id,
                'amount', amount
            )
            ORDER BY order_id
        ),
        '[]'::json
    )
    FROM export_lab.orders
) TO STDOUT;
```

Kết quả là một row chứa một JSON array. Với dataset rất lớn, một array duy nhất có thể cần bộ nhớ/aggregation lớn; JSONL streaming thường phù hợp hơn.

### 13.3. JSON không phải CSV

Nếu consumer cần nested objects/arrays, JSON có thể biểu diễn cấu trúc tốt hơn CSV. Nhưng cần thống nhất:

- JSON vs JSONB textual representation.
- Quy tắc NULL.
- Kiểu số và precision.
- Tên keys.
- Một object/line hay một array/file.
- Version của schema.

### 13.4. JSON export có thể lộ cột ngoài ý muốn

`row_to_json(t)` với cả row có thể xuất tất cả cột trong composite row. Với dữ liệu nhạy cảm, tạo SELECT object tường minh thay vì serialize nguyên row.

---

## 14. Xuất dữ liệu có RLS và phân quyền

### 14.1. Quyền SELECT vẫn được áp dụng

Để xuất dữ liệu, role cần quyền đọc bảng/cột tương ứng. Với query export, các quyền của query như SELECT, EXECUTE trên function được gọi, và các chính sách bảo mật liên quan vẫn cần được đáp ứng.

### 14.2. COPY table TO và Row-Level Security

Nếu RLS bật trên bảng, PostgreSQL áp dụng các SELECT policies phù hợp cho `COPY table TO`. Tuy nhiên, hãy xác minh role đang chạy và policy cụ thể; không dùng một kết quả export của owner/superuser để suy ra dữ liệu mà runtime role sẽ thấy.

### 14.3. Query export cũng phải được kiểm tra

```sql
COPY (
    SELECT
        order_id,
        tenant_id,
        amount
    FROM export_lab.orders
    WHERE tenant_id = 10
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

Điều kiện `WHERE tenant_id = 10` là filter trong query, không tự thay authorization. Nếu caller có thể sửa query hoặc đổi tenant parameter, cần policy/grants bảo vệ ở database/app.

### 14.4. Superuser và BYPASSRLS

Superuser hoặc role có thuộc tính/khả năng bypass RLS có thể nhìn dữ liệu vượt policy thông thường. Export chạy bằng role đặc quyền có thể chứa nhiều dữ liệu hơn export chạy bởi role ứng dụng.

### 14.5. Nguyên tắc least privilege

- Export bằng role chỉ có SELECT trên dữ liệu cần thiết.
- Chỉ cấp quyền trên cột cần xuất khi phù hợp.
- Dùng query list cột tường minh.
- Không chạy export production bằng superuser chỉ vì tiện.
- Lưu audit ai export, thời điểm, query/report và nơi lưu file khi dữ liệu nhạy cảm.
- Kiểm soát download link, file ACL, encryption, retention và xóa file.

### 14.6. COPY FROM và RLS

Lưu ý phân biệt chiều dữ liệu: PostgreSQL hiện không hỗ trợ `COPY FROM` cho bảng có RLS; tài liệu khuyến nghị dùng các câu INSERT tương đương. Đây là vấn đề nhập dữ liệu, không phải lý do kết luận COPY TO cũng không dùng được với RLS.

---

## 15. psql output: \copy, \o, \g và --csv

### 15.1. \copy là frontend COPY

```text
\copy (SELECT order_id, amount FROM export_lab.orders ORDER BY order_id) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
```

Đây là lựa chọn chính khi cần file CSV đúng quy tắc COPY ở máy client.

### 15.2. \o chuyển output query của psql

```text
\pset format csv
\o 'orders.csv'

SELECT order_id, amount
FROM export_lab.orders
ORDER BY order_id;

\o
```

`\o` chuyển output của các lệnh query psql sang file; `\o` không có filename đóng việc redirect và trả output về nơi mặc định.

Khác biệt: `\o` ghi **output đã được psql format**, còn `\copy` dùng COPY protocol để nhận dữ liệu thô theo format được chỉ định.

### 15.3. \g filename cho một query

```text
\pset format csv
SELECT order_id, amount
FROM export_lab.orders
ORDER BY order_id
\g 'orders.csv'
```

`\g filename` gửi query hiện tại và ghi kết quả query vào file một lần. Nó là lựa chọn one-shot thay cho `\o`.

### 15.4. \pset format csv

```text
\pset format csv
```

psql dùng CSV formatting cho output của query. Nếu muốn output CSV có header, kiểm tra cấu hình tuples-only và các tùy chọn psql đang dùng.

### 15.5. psql --csv

Trong shell, psql có option:

```text
psql --csv -d appdb -c "SELECT order_id, amount FROM export_lab.orders ORDER BY order_id"
```

Output của psql được format CSV. Có thể kết hợp output redirection của shell, nhưng nhớ phân biệt stdout dữ liệu với stderr thông báo lỗi. Dùng `-X` nếu muốn bỏ qua psqlrc cá nhân và `-q` nếu muốn quiet khi script cần output sạch.

### 15.6. Vì sao không tự nối dấu phẩy?

Không nên làm:

```sql
SELECT order_id || ',' || customer_name || ',' || note
FROM ...;
```

vì dữ liệu có thể chứa delimiter, quote, newline, NULL và encoding cần xử lý. COPY CSV đã có serializer đúng chuẩn.

### 15.7. Vì sao không dùng aligned output làm CSV?

Output mặc định của psql có padding, separator và row-count footer. Nó dành cho con người đọc, không phải data interchange. Hãy dùng `\copy` hoặc `\pset format csv`.

---

## 16. Xuất kết quả truy vấn qua ứng dụng Java/JDBC

### 16.1. ResultSet thông thường

Một cách phổ biến là query bằng JDBC rồi tự serialize:

```java
String sql =
    "SELECT order_id, amount " +
    "FROM export_lab.orders " +
    "WHERE tenant_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setInt(1, 10);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            BigDecimal amount = resultSet.getBigDecimal("amount");
            // Serialize values using a CSV library.
        }
    }
}
```

Nếu tự ghi CSV, dùng thư viện CSV chuyên dụng để quote delimiter, quote character, newline và NULL. Không nối chuỗi bằng dấu phẩy.

### 16.2. Dùng PostgreSQL CopyManager

pgJDBC cung cấp API COPY riêng. Ví dụ minh họa:

```java
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

import javax.sql.DataSource;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;

public long exportPaidOrders(DataSource dataSource, Path target)
        throws Exception {

    String copySql =
        "COPY (" +
        "  SELECT order_id, customer_id, ordered_at, amount " +
        "  FROM export_lab.orders " +
        "  WHERE status = 'paid' " +
        "  ORDER BY order_id" +
        ") TO STDOUT WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')";

    try (Connection connection = dataSource.getConnection();
         OutputStream output = Files.newOutputStream(target)) {

        PGConnection pgConnection =
            connection.unwrap(PGConnection.class);

        CopyManager copyManager = pgConnection.getCopyAPI();

        return copyManager.copyOut(copySql, output);
    }
}
```

Đây là ví dụ theo API pgJDBC; cần dùng phiên bản driver có `PGConnection` và `CopyManager` tương ứng. SQL trong ví dụ là cố định. Nếu query có điều kiện động, không nối trực tiếp input không tin cậy vào SQL string.

### 16.3. CopyManager và standard JDBC khác nhau

- `PreparedStatement` thực thi query và đọc ResultSet qua JDBC.
- `CopyManager.copyOut` sử dụng PostgreSQL COPY protocol để stream dữ liệu ra OutputStream.
- COPY thường phù hợp với export lớn vì tránh việc application phải xử lý từng row/column ở mức ResultSet.
- Tự serialize ResultSet phù hợp khi cần biến đổi phức tạp ở Java, nhưng cần kiểm soát memory, fetch size và CSV escaping.

### 16.4. Ghi file staging

Trong Java, nên ghi vào file tạm trong cùng filesystem rồi chỉ đổi tên khi COPY hoàn tất:

```java
Path temporary = target.resolveSibling(
    target.getFileName().toString() + ".part"
);

// Copy hoàn tất và stream đóng thành công:
Files.move(
    temporary,
    target,
    java.nio.file.StandardCopyOption.REPLACE_EXISTING,
    java.nio.file.StandardCopyOption.ATOMIC_MOVE
);
```

`ATOMIC_MOVE` phụ thuộc filesystem/provider. Nếu không hỗ trợ, cần xử lý fallback có chủ đích. Không công bố file .part như một export hoàn chỉnh.

### 16.5. Không log nội dung file nhạy cảm

Log số rows, duration, query/report identifier và correlation ID khi phù hợp. Tránh log toàn bộ CSV hoặc token/email/PII chỉ để debug.

---

## 17. Snapshot và tính nhất quán khi export

### 17.1. Một COPY query là một statement

Một câu:

```sql
COPY (
    SELECT ...
) TO STDOUT WITH (FORMAT csv, HEADER true);
```

được thực thi như một statement và dùng snapshot theo isolation level/transaction hiện hành. Những thay đổi đã commit sau snapshot không nhất thiết xuất hiện trong kết quả đó.

### 17.2. Nhiều file có thể thấy các snapshot khác nhau

Nếu application export:

```text
orders.csv
customers.csv
payments.csv
```

bằng ba statements ở `READ COMMITTED`, mỗi statement có thể nhận snapshot mới. Một transaction khác có thể commit giữa các lần export, khiến các file không phản ánh cùng một thời điểm logic.

### 17.3. Dùng REPEATABLE READ cho snapshot nhất quán

Nếu cần các query exports thấy cùng một snapshot:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

-- psql có thể thực hiện các lệnh \copy trong transaction này.
-- \copy (SELECT ... FROM export_lab.orders) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
-- \copy (SELECT ... FROM export_lab.customers) TO 'customers.csv' WITH (FORMAT csv, HEADER true)

COMMIT;
```

Trong `REPEATABLE READ`, các SELECT trong transaction dùng snapshot nhất quán theo semantics isolation. Nếu dữ liệu có nhiều nguồn hoặc có side effects ngoài transaction, cần hợp đồng snapshot rộng hơn.

### 17.4. Read-only transaction

`READ ONLY` biểu thị transaction chỉ đọc, giảm nguy cơ vô tình sửa dữ liệu trong một quy trình export. Nó không thay quyền SELECT hoặc kiểm soát RLS.

### 17.5. Snapshot lâu có chi phí

Một export kéo dài có thể giữ snapshot lâu, làm PostgreSQL phải giữ lại tuple versions mà vacuum chưa thể dọn vì transaction còn cần nhìn thấy chúng.

Điều này có thể tăng bloat/áp lực storage. Với export lớn:

- Chạy ngoài peak khi có thể.
- Đo thời gian và dung lượng.
- Không giữ transaction mở trong lúc application xử lý file chậm ngoài database nếu không cần.
- Cân nhắc snapshot/export staging hoặc logical replication/data warehouse cho workload lặp lại.

### 17.6. File không nằm trong transaction database

Ngay cả khi query export chạy trong transaction:

- File đã ghi trên filesystem không tự rollback khi SQL transaction rollback.
- Nếu export thứ hai thất bại, file thứ nhất có thể đã tồn tại.
- Một lỗi network/client có thể để lại file không hoàn chỉnh.

Đây là điểm khác giữa atomic database commit và file I/O.

### 17.7. Staging file và publish

Một workflow đáng tin:

```text
1. Ghi orders.csv.part
2. Ghi customers.csv.part
3. Kiểm tra COPY hoàn tất, số rows và metadata
4. Commit/đóng transaction thành công
5. Đổi tên file staging sang tên công bố
6. Ghi manifest/checksum/version
```

Chỉ công bố file khi toàn bộ export thành công. Rename atomic chỉ bảo đảm từng file theo filesystem phù hợp; nếu nhiều file phải công bố cùng lúc, dùng manifest/version directory hoặc một marker hoàn tất.

---

## 18. Export lớn: streaming, chia lô và tiến độ

### 18.1. COPY stream dữ liệu

COPY không cần application gom toàn bộ rows vào một danh sách trong memory trước khi ghi file. Client có thể nhận stream và ghi dần.

### 18.2. Không OFFSET pagination lớn một cách mặc định

Một chiến lược:

```sql
SELECT *
FROM export_lab.orders
ORDER BY order_id
LIMIT 10000 OFFSET 1000000;
```

có thể tốn kém vì database vẫn phải đi qua nhiều rows để bỏ qua OFFSET. Nếu phải chia lô, cân nhắc keyset/range theo khóa có index:

```sql
SELECT *
FROM export_lab.orders
WHERE order_id > 1000000
ORDER BY order_id
LIMIT 10000;
```

Nhưng nhiều batches riêng có thể có snapshot khác nhau ở READ COMMITTED. Nếu cần snapshot nhất quán, phải thiết kế transaction/streaming hoặc snapshot protocol phù hợp.

### 18.3. Chia file theo partition hoặc range

Ví dụ xuất theo tháng:

```sql
COPY (
    SELECT event_id, event_time, payload
    FROM app.events
    WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00+00'
      AND event_time <  TIMESTAMPTZ '2026-02-01 00:00+00'
    ORDER BY event_time, event_id
) TO STDOUT WITH (FORMAT csv, HEADER true);
```

Chọn ranh giới không chồng lấn và không bỏ sót. Tên file nên thể hiện thời gian, tenant/scope và version schema nếu cần.

### 18.4. pg_stat_progress_copy

PostgreSQL cung cấp view `pg_stat_progress_copy` để theo dõi tiến độ COPY đang chạy:

```sql
SELECT
    pid,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed,
    tuples_excluded
FROM pg_stat_progress_copy;
```

Một số trường có thể NULL hoặc chưa có giá trị tùy loại COPY/đích/nguồn và giai đoạn thực thi. Cần quyền monitoring phù hợp để quan sát các sessions khác.

### 18.5. COPY TO STDOUT và client backpressure

Khi client ghi file chậm, việc đọc/ghi qua socket có thể bị giới hạn bởi network và filesystem. Đảm bảo client stream tiêu thụ dữ liệu, không giữ toàn bộ bytes trong RAM nếu export rất lớn.

### 18.6. Compression

Có thể nén file ở client hoặc dùng `PROGRAM` nếu phù hợp. Compression giảm storage/network nhưng dùng CPU và có thể làm khó resume. Đánh giá bottleneck trước khi thêm compression.

---

## 19. CSV formula injection khi mở bằng spreadsheet

### 19.1. CSV escaping không phải spreadsheet safety

CSV serializer bảo vệ dấu phẩy, quote và newline theo format. Nhưng một spreadsheet có thể diễn giải giá trị bắt đầu bằng các ký tự như:

```text
=
+
-
@
```

như công thức hoặc biểu thức tùy ứng dụng và cách mở file.

Ví dụ dữ liệu người dùng nhập:

```text
=HYPERLINK("https://example.invalid","Open")
```

có thể bị spreadsheet diễn giải như công thức. Quote CSV đúng chuẩn **không tự loại bỏ nguy cơ formula injection**.

### 19.2. Phân biệt số âm với formula

Không thể đơn giản prefix mọi giá trị bắt đầu bằng `-` mà không xét kiểu dữ liệu; `-100` có thể là số âm hợp lệ. Cần áp dụng chính sách dựa trên loại cột và consumer.

### 19.3. Mitigation theo consumer

Nếu file sẽ được mở trực tiếp bằng spreadsheet:

- Xác định các cột chứa text không tin cậy.
- Kiểm tra giá trị bắt đầu bằng dấu điều khiển/formula sau khi xử lý whitespace/control characters theo threat model.
- Có thể tạo một **export presentation** đã neutralize cho spreadsheet, chẳng hạn prefix apostrophe theo quy tắc đã test với Excel/LibreOffice.
- Giữ một export machine-to-machine riêng nếu cần bảo toàn dữ liệu gốc.
- Ghi rõ việc neutralization làm thay đổi representation.

Không áp dụng một biểu thức SQL chung cho mọi hệ thống rồi tuyên bố CSV đã an toàn tuyệt đối.

### 19.4. Ví dụ minh họa tạo presentation field

```sql
SELECT
    order_id,
    CASE
        WHEN customer_supplied_text ~ '^[[:space:]]*[=+@-]'
        THEN '''' || customer_supplied_text
        ELSE customer_supplied_text
    END AS spreadsheet_safe_text
FROM some_table;
```

Đây chỉ là minh họa ý tưởng, không phải sanitizer hoàn chỉnh cho mọi spreadsheet/locale. Không áp dụng quy tắc này lên cột số mà không xét kiểu và consumer. Cần kiểm thử các ký tự tab/CR/LF, leading whitespace và behavior của ứng dụng đích.

### 19.5. Không biến dữ liệu gốc thành dữ liệu presentation

Nếu consumer là API/ETL, đừng prefix apostrophe rồi coi đó là giá trị gốc. Hãy tách:

- Raw export bảo toàn dữ liệu.
- Spreadsheet export áp dụng neutralization theo hợp đồng.

---

## 20. Bảo vệ dữ liệu và file export

### 20.1. Export là một điểm rời khỏi database security boundary

Sau khi file được ghi ra:

- RLS không còn kiểm soát ai mở file.
- GRANT SELECT không còn bảo vệ bản copy đã xuất.
- Database audit không tự kiểm soát việc file được gửi qua email/cloud drive.
- Backup endpoint không tự xóa các bản export cũ.

Vì vậy export cần policy dữ liệu riêng.

### 20.2. Data minimization

Chỉ xuất:

- Những cột downstream thực sự cần.
- Những rows thuộc phạm vi nghiệp vụ.
- Khoảng thời gian được phê duyệt.
- Những identifiers đã được phép chia sẻ.

Tránh `SELECT *` trong export gửi ra ngoài.

### 20.3. Kiểm soát file

- Ghi file vào thư mục có ACL phù hợp.
- Tránh public web root và shared folder không hạn chế.
- Mã hóa khi lưu/truyền nếu dữ liệu nhạy cảm.
- Đặt retention/expiration.
- Ghi nhận người tạo, mục đích, thời điểm và phạm vi export.
- Không đưa credentials hoặc secret vào CSV.
- Xóa file staging thất bại theo chính sách.

### 20.4. Export qua server file

Nếu COPY ghi server file, quyền OS của PostgreSQL process quyết định file có thể bị ghi ở đâu. Dùng một thư mục export riêng, giới hạn quyền, không cho PostgreSQL ghi vào thư mục chứa cấu hình/keys.

### 20.5. Export qua client file

Với `\copy`, file nằm trên máy chạy psql. Nếu psql chạy trong container, CI runner hoặc jump host, đó là filesystem của môi trường đó, không phải máy người dùng đang xem terminal từ xa.

### 20.6. Không dùng COPY PROGRAM để gửi file tùy ý

Server-side PROGRAM có thể chạy command dưới quyền OS của PostgreSQL. Không cấp `pg_execute_server_program` cho analyst/application chỉ để nén hoặc chuyển file. Dùng client-side compression hoặc một export service có quyền giới hạn.

---

## 21. Xuất dữ liệu với RLS: test đúng role

### 21.1. Tạo bảng minh họa có RLS

Đây là thí nghiệm tùy chọn trong schema lab:

```sql
CREATE TABLE export_lab.tenant_notes (
    note_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    note_text TEXT NOT NULL
);

INSERT INTO export_lab.tenant_notes
VALUES
    (1, 10, 'Tenant 10 note'),
    (2, 20, 'Tenant 20 note');

ALTER TABLE export_lab.tenant_notes ENABLE ROW LEVEL SECURITY;
```

### 21.2. Policy minh họa

Một policy production cần gắn với identity/context tin cậy. Ví dụ đơn giản theo database role hoặc GUC phải được thiết kế theo hệ thống thực; không sao chép một policy tin GUC caller tùy ý.

```sql
-- Mẫu cú pháp cho môi trường đã có role và context tin cậy:
-- CREATE POLICY tenant_export_policy
-- ON export_lab.tenant_notes
-- FOR SELECT
-- USING (tenant_id = current_setting('app.tenant_id')::integer);
```

### 21.3. COPY TO áp dụng SELECT policies

Khi `COPY table TO` chạy trên bảng RLS-enabled, các SELECT policies phù hợp được áp dụng theo role thực thi. Query export cũng chịu các quyền và chính sách của query.

### 21.4. Test dưới role runtime

Không test bằng superuser rồi kết luận dữ liệu xuất ra là đúng với user ứng dụng. Test bằng role có quyền thực tế và policy thực tế.

### 21.5. Không export bằng role bypass RLS nếu không cần

Một role có BYPASSRLS hoặc superuser có thể xuất rows vượt policy thông thường. Với export tenant, dùng role least-privilege và audit scope.

---

## 22. psql script và automation

### 22.1. Dùng file script

Một file `export.sql` có thể chứa:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET LOCAL DateStyle = 'ISO, YMD';
SET LOCAL TimeZone = 'UTC';

-- psql meta-command: file được ghi trên client.
-- \copy (SELECT order_id, amount FROM export_lab.orders ORDER BY order_id) TO 'orders.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

COMMIT;
```

Chạy bằng:

```bash
psql -X -v ON_ERROR_STOP=1 -d appdb -f export.sql
```

`-X` bỏ qua psqlrc; `ON_ERROR_STOP` làm psql dừng khi script gặp lỗi. Đối với automation, hãy kiểm tra exit status và file output.

### 22.2. Đặt thư mục client trước

Trong script psql có thể dùng `\cd` để đổi working directory client:

```text
\cd /var/tmp/exports
\copy (SELECT order_id, amount FROM export_lab.orders) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
```

Trên Windows, dùng đường dẫn phù hợp với máy psql.

### 22.3. Không dùng shell redirection sai tầng

```bash
psql -d appdb -c "COPY export_lab.orders TO '/tmp/orders.csv' WITH (FORMAT csv, HEADER true)"
```

ghi file ở máy server.

Trong khi:

```bash
psql -d appdb -c "\copy export_lab.orders TO 'orders.csv' WITH (FORMAT csv, HEADER true)"
```

ghi file ở máy chạy psql.

### 22.4. stdout và stderr

Khi tự động hóa:

- Dữ liệu CSV nên đi vào file/stdout riêng.
- Error messages nên được giữ ở stderr/log.
- Không trộn banner, timing, SQL echo hoặc row count vào CSV.
- Dùng `-q`/`-X` phù hợp.
- Dùng `ON_ERROR_STOP` để pipeline nhận lỗi thay vì coi script chạy xong là thành công.

### 22.5. Shell quoting

Một query có dấu nháy đơn, dấu ngoặc, dollar quoting và dấu cách dễ bị shell parse sai nếu ghép thành một chuỗi. Với query dài, dùng file script và `psql -f` thay vì tạo command string phức tạp từ input người dùng.

---

## 23. Xuất kết quả truy vấn qua \g và \o

### 23.1. \g filename

```text
SELECT order_id, amount
FROM export_lab.orders
ORDER BY order_id
\g 'orders.csv'
```

psql ghi output query hiện tại vào file. Format phụ thuộc `\pset` options.

### 23.2. \o filename

```text
\pset format csv
\o 'orders.csv'

SELECT order_id, amount
FROM export_lab.orders
ORDER BY order_id;

SELECT COUNT(*) AS order_count
FROM export_lab.orders;

\o
```

Cả hai query được redirect vào file, nên output CSV có thể gồm hai result sets liên tiếp. Nếu file cần một schema duy nhất, chỉ redirect query thích hợp hoặc dùng `\copy` riêng cho từng file.

### 23.3. \copy so với \g

| Đặc điểm | `\copy ... TO` | `\g filename` |
|---|---|---|
| Nền tảng | PostgreSQL COPY protocol | psql query output formatting |
| CSV serializer | COPY CSV | psql CSV output nếu chọn format CSV |
| Export table/query | Có | Query result |
| Ghi file phía client | Có | Có |
| COPY options như NULL/QUOTE/FORCE_QUOTE | Có | Không dùng nguyên bộ COPY options |
| Phù hợp bulk data export | Rất phù hợp | Phù hợp query output thông thường |

---

## 24. COPY TO trên partitioned table, view và inheritance

### 24.1. Direct COPY có giới hạn loại relation

`COPY table TO` trực tiếp áp dụng cho plain tables và populated materialized views. Nó không trực tiếp hỗ trợ một số relation như partitioned tables, inheritance child tables hoặc views.

### 24.2. Dùng COPY query

```sql
COPY (
    SELECT *
    FROM app.partitioned_events
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

Query form tận dụng SELECT semantics, bao gồm view và partitioned parent.

### 24.3. Inheritance và ONLY

Với bảng có inheritance, `SELECT * FROM parent` có thể bao gồm rows từ descendants theo semantics inheritance. `SELECT * FROM ONLY parent` chỉ chọn rows ở parent. Khi export, xác định rõ muốn lấy:

```sql
COPY (
    SELECT *
    FROM ONLY app.parent_table
    ORDER BY id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

hay toàn bộ hierarchy.

### 24.4. Materialized view phải được populated

Materialized view chưa được populate không có tập dữ liệu để xuất; cần refresh theo workflow trước. Nếu dùng `WITH NO DATA` lúc tạo materialized view, cần `REFRESH MATERIALIZED VIEW` trước export.

---

## 25. Các định dạng và kiểu dữ liệu đặc biệt

### 25.1. Numeric và tiền

`NUMERIC` xuất dạng text theo output function. Với dữ liệu tiền, quy định:

- Đơn vị tiền tệ.
- Scale/rounding.
- Dấu thập phân.
- Không phụ thuộc locale spreadsheet.
- Currency code nếu nhiều loại tiền.

Đừng xuất một cột `amount` mà không nói nó là VND, USD hay một currency khác.

### 25.2. Boolean

Boolean được xuất dạng textual representation của PostgreSQL, thường là `t`/`f` ở text format và các representation tương ứng ở CSV. Nếu consumer muốn `true/false`, có thể chuẩn hóa:

```sql
SELECT
    CASE WHEN is_active THEN 'true' ELSE 'false' END AS is_active
FROM app.users;
```

### 25.3. Arrays

PostgreSQL array có textual representation riêng; một consumer CSV không tự hiểu array đó thành cột nhiều phần tử. Nếu cần cấu trúc portable, có thể chuyển sang JSON:

```sql
SELECT to_json(tags) AS tags_json
FROM app.products;
```

### 25.4. JSON/JSONB

`json`/`jsonb` được xuất qua textual output. Nếu consumer cần parse JSON, kiểm tra escaping và encoding, không split field bằng dấu phẩy.

### 25.5. Bytea

`bytea` có thể được xuất ở representation text (ví dụ hex format tùy setting) hoặc binary COPY. Đừng coi CSV là định dạng nhị phân gốc; file lớn chứa bytea có thể tăng kích thước đáng kể.

### 25.6. Large Objects

PostgreSQL Large Objects được quản lý qua OID/large-object APIs; export một cột OID không tự xuất nội dung blob. Nếu cần nội dung large object, dùng các hàm/API large-object phù hợp hoặc xử lý riêng ở client.

### 25.7. Generated columns

Khi `COPY table TO` không có column list, các generated columns có quy tắc riêng và không được xử lý giống một cột ordinary ghi trực tiếp. Nếu contract cần generated value, dùng SELECT query tường minh để lấy giá trị cần xuất.

---

## 26. Đảm bảo thứ tự, schema và khả năng tái lập

### 26.1. ORDER BY phải có tie-breaker

```sql
ORDER BY ordered_at
```

có thể không xác định thứ tự ổn định giữa những rows có cùng timestamp. Nếu downstream cần reproducible file:

```sql
ORDER BY ordered_at, order_id
```

### 26.2. Không dùng SELECT *

Schema evolution có thể thêm cột, đổi thứ tự cột hoặc thêm dữ liệu nhạy cảm. Dùng:

```sql
SELECT order_id, ordered_at, status, amount
```

thay vì `SELECT *` trong data contract bên ngoài.

### 26.3. Version hóa export

Có thể đưa version vào:

- Tên file: `orders_v2_2026-02.csv`.
- Manifest JSON chứa schema version, thời điểm, row count và checksum.
- Metadata trong hệ thống catalog/data pipeline.

Không nên thêm một dòng metadata tùy ý vào CSV nếu consumer mong header là dòng đầu tiên; dùng sidecar manifest.

### 26.4. Checksum

Sau khi ghi file, client có thể tính SHA-256 để kiểm tra integrity khi chuyển file. Checksum không chứng minh nội dung đúng nghiệp vụ, nhưng giúp phát hiện file bị thay đổi/truyền lỗi.

### 26.5. Row count

COPY command tag có row count. Có thể đối chiếu với:

```sql
SELECT COUNT(*)
FROM export_lab.orders
WHERE status = 'paid';
```

Nhưng nếu count chạy ở snapshot khác, dữ liệu đồng thời có thể đổi. Với export nhất quán, đếm trong cùng transaction/snapshot hoặc lấy count từ output operation phù hợp.

---

## 27. Lỗi thường gặp khi xuất dữ liệu

### 27.1. could not open file: Permission denied

Nếu dùng SQL `COPY TO '/server/path'`:

- Kiểm tra path trên server.
- Kiểm tra OS user của PostgreSQL.
- Kiểm tra quyền directory/file.
- Kiểm tra role có quyền server-file operation.

Nếu muốn file trên laptop, chuyển sang `\copy`.

### 27.2. must be superuser or a member of pg_write_server_files

Đây là lỗi quyền server-side file. Không giải quyết bằng cách grant superuser cho application. Nếu mục tiêu chỉ là local export, dùng `\copy`; nếu server file là yêu cầu thật, DBA đánh giá grant tối thiểu.

### 27.3. relation does not exist

Có thể do:

- Tên bảng chưa schema-qualified.
- `search_path` không chứa schema đúng.
- Sai database.
- Bảng ở schema khác.
- Dùng direct COPY trên loại relation không được hỗ trợ.

Dùng tên đầy đủ:

```sql
COPY app.orders TO STDOUT;
```

hoặc query form.

### 27.4. permission denied for table

Role có thể kết nối database nhưng chưa có SELECT trên bảng/cột. Kiểm tra:

```sql
SELECT has_table_privilege(
    current_user,
    'export_lab.orders',
    'SELECT'
);
```

Với column-level grants, xem đúng danh sách cột được đọc.

### 27.5. invalid byte sequence / character conversion

Có thể encoding file không thể biểu diễn ký tự nguồn. Kiểm tra `server_encoding`, `client_encoding` và option `ENCODING`. UTF-8 thường là lựa chọn an toàn cho trao đổi đa ngôn ngữ.

### 27.6. CSV có thêm dòng hoặc cột bị lệch

Kiểm tra consumer có hiểu:

- Quoted newline.
- Delimiter tùy chỉnh.
- Escape quote.
- NULL string.
- Encoding.

Không split CSV bằng cách đọc từng dòng và tách dấu phẩy thủ công.

### 27.7. File rỗng

Một file chỉ có header có thể là kết quả hợp lệ khi query không trả rows. Kiểm tra `COPY 0` hoặc query filter; không tự kết luận export thất bại chỉ vì file ít bytes.

### 27.8. File dở dang

Nếu COPY bị lỗi giữa chừng hoặc client mất kết nối, file đích có thể chứa dữ liệu một phần. Ghi vào staging filename, chỉ rename/publish sau khi command thành công.

### 27.9. Không tìm thấy file sau \copy

Kiểm tra working directory của **psql process**, không phải working directory của database server. Nếu psql chạy trong Docker/CI, file nằm trong container/runner filesystem.

### 27.10. \copy không thay psql variables

Vì parser đặc biệt, đừng kỳ vọng `\copy ... TO :'filename'` sẽ thay biến như một SQL query. Dùng path literal phù hợp hoặc điều khiển từ script/client đã thiết kế rõ.

---

## 28. Kiểm tra tiến độ và hoạt động export

### 28.1. COPY command tag

Khi thành công, PostgreSQL trả:

```text
COPY n
```

Trong đó `n` là số rows được copy.

### 28.2. pg_stat_progress_copy

```sql
SELECT
    pid,
    relid::regclass AS relation,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed,
    tuples_excluded
FROM pg_stat_progress_copy;
```

Không phải mọi cột đều có ý nghĩa cho mọi kiểu source/destination. Với `COPY (query) TO STDOUT`, relation có thể không phản ánh toàn bộ query sources.

### 28.3. pg_stat_activity

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    query_start,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE query ILIKE 'COPY %'
ORDER BY query_start;
```

Để xem query của sessions khác, role cần quyền monitoring phù hợp. Không log/export toàn query nếu nó có literals nhạy cảm.

### 28.4. Theo dõi phía client

Ngoài database metrics, ghi:

- Thời gian bắt đầu/kết thúc.
- Số rows.
- Bytes/file size.
- Checksum.
- Tỷ lệ lỗi/retry.
- Target path/object storage key.
- Data contract version.

---

## 29. Những sai lầm phổ biến

**1. “COPY TO '/path' ghi file ở laptop.”** Sai. Nó ghi trên filesystem của PostgreSQL server.

**2. “\copy và COPY là cùng một lệnh SQL.”** Không. `\copy` là psql meta-command thực hiện frontend copy.

**3. “\copy cần pg_write_server_files.”** Không chỉ để ghi file client; nó cần quyền SELECT và quyền filesystem của client.

**4. “COPY server-side chỉ cần SELECT.”** Với file/PROGRAM server-side còn cần quyền server-file/program phù hợp và OS access.

**5. “Có pg_write_server_files là tự có quyền SELECT mọi bảng.”** Không. Đó là quyền filesystem server, tách với table privileges.

**6. “Có thể cấp pg_execute_server_program cho app để nén file.”** Rất rủi ro; đây là quyền thực thi command dưới OS identity của server.

**7. “COPY table TO luôn hỗ trợ view/partitioned table.”** Không. Dùng `COPY (SELECT ...) TO`.

**8. “COPY table TO tự sắp xếp theo primary key.”** Không. Dùng ORDER BY trong query.

**9. “COPY table TO xuất mọi cột theo thứ tự mình muốn.”** Không. Liệt kê column list hoặc SELECT list.

**10. “SELECT * an toàn cho export lâu dài.”** Schema thêm cột có thể thay đổi file contract và lộ dữ liệu.

**11. “CSV chỉ cần nối chuỗi bằng dấu phẩy.”** Sai. Cần quote/escape, newline và NULL semantics.

**12. “Một dòng CSV luôn là một record vật lý.”** Sai. Field có thể chứa newline bên trong quote.

**13. “NULL và chuỗi rỗng giống nhau trong CSV.”** Không. PostgreSQL dùng quoting để phân biệt theo NULL string.

**14. “FORCE_NOT_NULL là option COPY TO.”** Không. Đây là option COPY FROM CSV.

**15. “FORCE_QUOTE có thể quote NULL.”** Không. NULL output không bao giờ được FORCE_QUOTE.

**16. “HEADER MATCH là option export.”** Không. HEADER MATCH chỉ dành cho COPY FROM.

**17. “ENCODING UTF8 bảo đảm mọi consumer hiển thị tiếng Việt.”** Không nếu consumer mở sai encoding hoặc dữ liệu/metadata bị xử lý sai.

**18. “UTF-8 luôn tự thêm BOM.”** Không. COPY encoding không có nghĩa tự thêm BOM.

**19. “TIMESTAMPTZ luôn xuất UTC bất kể session.”** Không. Text output chịu TimeZone.

**20. “DateStyle không ảnh hưởng file.”** Có thể ảnh hưởng representation ngày tháng; quy định ISO khi cần portable.

**21. “Binary COPY là file interchange portable.”** Không. Binary format phụ thuộc types/version và không dành cho spreadsheet.

**22. “COPY TO trực tiếp ghi file nên không cần client connection ổn định.”** Vẫn cần kết nối điều khiển; với STDOUT client còn phải nhận stream.

**23. “COPY query export sẽ tự filter tenant theo tham số app.”** Không nếu query/policy không thiết kế đúng.

**24. “RLS không áp dụng cho COPY TO.”** Sai; SELECT policies liên quan được áp dụng cho COPY table TO.

**25. “Superuser export giống runtime role.”** Không. Superuser/BYPASSRLS có thể thấy nhiều rows hơn.

**26. “File đã xuất vẫn được RLS bảo vệ.”** Không. File nằm ngoài database security boundary.

**27. “Một transaction bao nhiều COPY làm các file tự atomic.”** Không. Filesystem writes không rollback cùng database transaction.

**28. “READ COMMITTED nhiều file export cùng snapshot.”** Không đảm bảo; mỗi statement có thể thấy snapshot mới.

**29. “REPEATABLE READ không có chi phí.”** Snapshot lâu có thể giữ dead tuples và ảnh hưởng vacuum.

**30. “File chỉ cần ghi trực tiếp tên cuối.”** Lỗi giữa chừng có thể để lại file không hoàn chỉnh; dùng staging/publish.

**31. “CSV quoting ngăn spreadsheet formula injection.”** Không. CSV parser và spreadsheet formula interpreter là hai lớp khác nhau.

**32. “Tất cả cột text bắt đầu dấu trừ đều là formula.”** Không. Cần xét kiểu dữ liệu/consumer, không phá số âm hợp lệ.

**33. “\o và \copy giống nhau.”** Không. Một cái redirect psql output, một cái dùng COPY protocol.

**34. “psql aligned output là CSV.”** Không.

**35. “Có thể dùng psql variable interpolation trong phần arguments của \copy.”** Không theo parser đặc biệt của meta-command.

**36. “COPY PROGRAM chạy trên client.”** Không. SQL COPY PROGRAM chạy trên server; \copy PROGRAM chạy bởi psql client.

**37. “Chỉ cần row count là đủ chứng minh export đúng.”** Không. Cần schema, scope, snapshot, checksum và kiểm tra downstream.

**38. “COPY count không hiện nghĩa export thất bại.”** Không. Với STDOUT psql có thể ẩn command tag để không trộn với dữ liệu.

**39. “Large Object OID là nội dung blob.”** Không. Cần export nội dung Large Object riêng.

**40. “Tạo CSV là đã có file Excel.”** Không. CSV không phải XLSX.

---

## 30. Bài tập thực hành và đáp án

### Bài 1 — Xuất toàn bộ bảng CSV

**Yêu cầu:** xuất bảng orders với header.

```sql
COPY export_lab.orders
TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Bài 2 — Xuất query

**Yêu cầu:** chỉ lấy paid orders.

```sql
COPY (
    SELECT order_id, ordered_at, amount
    FROM export_lab.orders
    WHERE status = 'paid'
    ORDER BY order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Bài 3 — Xuất một số cột

**Yêu cầu:** chỉ export order_id và amount.

```sql
COPY export_lab.orders (order_id, amount)
TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Bài 4 — ORDER BY

**Câu hỏi:** COPY table TO có bảo đảm order_id tăng dần không?

**Đáp án:** Không. Dùng query form với `ORDER BY order_id`.

### Bài 5 — Xuất dữ liệu tenant

```sql
COPY (
    SELECT order_id, amount
    FROM export_lab.orders
    WHERE tenant_id = 10
    ORDER BY order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Bài 6 — JOIN customer

```sql
COPY (
    SELECT o.order_id, c.customer_name, o.amount
    FROM export_lab.orders o
    JOIN export_lab.customers c
      ON c.customer_id = o.customer_id
    ORDER BY o.order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Bài 7 — Tổng hợp

```sql
COPY (
    SELECT tenant_id, COUNT(*) AS order_count, SUM(amount) AS total
    FROM export_lab.orders
    GROUP BY tenant_id
    ORDER BY tenant_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Bài 8 — Xuất view

**Câu hỏi:** Có thể dùng direct `COPY view_name TO ...` không?

**Đáp án:** Direct COPY TO không hỗ trợ view như plain table. Dùng `COPY (SELECT ... FROM view_name) TO ...`.

### Bài 9 — Partitioned table

**Câu hỏi:** Xuất partitioned parent bằng cách nào?

**Đáp án:** Dùng `COPY (SELECT ... FROM partitioned_parent) TO ...`.

### Bài 10 — Server path hay client path

**Câu hỏi:** `COPY ... TO '/tmp/a.csv'` ghi ở đâu?

**Đáp án:** Filesystem của database server.

### Bài 11 — psql \copy

**Yêu cầu:** ghi CSV ở máy psql.

```text
\copy (SELECT order_id, amount FROM export_lab.orders ORDER BY order_id) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
```

### Bài 12 — Server file permission

**Câu hỏi:** Role chỉ có SELECT nhưng không có pg_write_server_files có ghi server file bằng COPY TO filename được không?

**Đáp án:** Không nếu thiếu quyền server-file operation phù hợp; có thể dùng COPY TO STDOUT/\copy client file.

### Bài 13 — Client permission

**Câu hỏi:** \copy không cần pg_write_server_files thì có thể ghi vào bất kỳ folder trên laptop không?

**Đáp án:** Không. Tiến trình psql vẫn cần quyền filesystem local.

### Bài 14 — NULL

**Câu hỏi:** CSV mặc định biểu diễn NULL và empty string thế nào?

**Đáp án:** NULL là empty field không quote; empty string là `""`.

### Bài 15 — Header

**Yêu cầu:** header theo alias.

```sql
COPY (
    SELECT order_id AS id, amount AS total
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Bài 16 — Quote all

```sql
COPY (
    SELECT order_id, status
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT csv, HEADER true, FORCE_QUOTE *);
```

**Đáp án:** Quote mọi non-NULL values; NULL không quote.

### Bài 17 — Encoding

**Yêu cầu:** export UTF-8.

```sql
COPY (
    SELECT customer_name
    FROM export_lab.customers
) TO STDOUT
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
```

### Bài 18 — TimeZone

**Câu hỏi:** Vì sao cùng TIMESTAMPTZ có thể có chuỗi giờ khác khi export?

**Đáp án:** Text output chịu TimeZone session; đặt timezone theo contract, ví dụ UTC.

### Bài 19 — CSV newline

**Câu hỏi:** Một field có newline có tạo hai CSV records không?

**Đáp án:** Không nếu được quote đúng; newline nằm bên trong field của cùng record.

### Bài 20 — CSV formula injection

**Câu hỏi:** CSV quote đúng có ngăn Excel diễn giải `=...` như công thức không?

**Đáp án:** Không. Cần neutralize các text fields theo consumer và threat model.

### Bài 21 — RLS

**Câu hỏi:** COPY table TO có áp dụng SELECT policies khi RLS bật không?

**Đáp án:** Có, các SELECT policies phù hợp được áp dụng. Test bằng đúng role runtime.

### Bài 22 — COPY FROM RLS

**Câu hỏi:** COPY FROM trên table có RLS có được hỗ trợ không?

**Đáp án:** Hiện không; dùng INSERT tương đương theo tài liệu PostgreSQL.

### Bài 23 — Binary

**Câu hỏi:** Binary COPY có phù hợp để mở trực tiếp bằng Excel không?

**Đáp án:** Không. Dùng CSV cho spreadsheet.

### Bài 24 — JSONL

**Yêu cầu:** mỗi order một JSON object.

```sql
COPY (
    SELECT row_to_json(q)
    FROM (
        SELECT order_id, status, amount
        FROM export_lab.orders
        ORDER BY order_id
    ) q
) TO STDOUT;
```

### Bài 25 — psql \o

**Câu hỏi:** \o và \copy khác nhau thế nào?

**Đáp án:** \o redirect output đã được psql format; \copy dùng COPY protocol với options COPY.

### Bài 26 — \copy variables

**Câu hỏi:** Phần arguments của \copy có psql variable interpolation như query bình thường không?

**Đáp án:** Không; parser của \copy lấy toàn bộ phần còn lại của dòng như arguments và không thực hiện variable interpolation/backquote expansion.

### Bài 27 — PROGRAM

**Câu hỏi:** SQL COPY TO PROGRAM chạy ở đâu?

**Đáp án:** Trên server. \copy TO PROGRAM chạy command ở client nơi psql chạy.

### Bài 28 — Snapshot

**Câu hỏi:** Ba file export bằng ba statements READ COMMITTED có chắc cùng snapshot?

**Đáp án:** Không. Dùng transaction REPEATABLE READ READ ONLY nếu cần cùng snapshot cho các query trong cùng transaction.

### Bài 29 — File atomicity

**Câu hỏi:** Rollback transaction có xóa file CSV đã được ghi bởi client không?

**Đáp án:** Không. Filesystem không tham gia database transaction; dùng staging và publish sau thành công.

### Bài 30 — pg_stat_progress_copy

**Yêu cầu:** xem tiến độ COPY.

```sql
SELECT pid, command, type, bytes_processed, tuples_processed
FROM pg_stat_progress_copy;
```

### Bài 31 — COPY table TO thứ tự

**Câu hỏi:** Muốn thứ tự ổn định thì viết gì?

**Đáp án:** `COPY (SELECT ... ORDER BY ...) TO ...`.

### Bài 32 — Xuất chỉ cột public

**Câu hỏi:** Có nên dùng SELECT * để gửi dữ liệu cho đối tác?

**Đáp án:** Không. Chọn cột tường minh để giảm nguy cơ lộ cột mới/nhạy cảm.

### Bài 33 — XLSX

**Câu hỏi:** COPY có tạo workbook nhiều sheet .xlsx không?

**Đáp án:** Không. COPY tạo text/CSV/binary; dùng công cụ client tạo XLSX nếu cần.

### Bài 34 — Large Object

**Câu hỏi:** Export OID của Large Object có xuất nội dung blob không?

**Đáp án:** Không. Cần dùng Large Object API/hàm riêng để xuất nội dung.

### Bài 35 — Export server path

**Câu hỏi:** Vì sao không cấp pg_write_server_files cho mọi analyst?

**Đáp án:** Quyền này cho phép ghi file ở nhiều vị trí server mà PostgreSQL process có thể truy cập, vượt nhu cầu export local thông thường.

### Bài 36 — Automation

**Yêu cầu:** script psql dừng khi export lỗi.

**Đáp án gợi ý:**

```bash
psql -X -v ON_ERROR_STOP=1 -d appdb -f export.sql
```

Kiểm tra exit code và file output trước khi publish.

---

## 31. Checklist trước khi công bố file export

### Nội dung và schema

1. Đã xác định rõ nguồn bảng/query?
2. Dùng schema-qualified table names khi cần?
3. Có chọn cột tường minh, tránh SELECT *?
4. Header/alias và thứ tự cột đã được chốt?
5. Có WHERE/tenant scope đúng?
6. Có ORDER BY và tie-breaker nếu cần thứ tự?
7. Kiểu dữ liệu, timezone, đơn vị tiền và precision có contract?

### Đích và quyền

8. File nằm trên server hay client?
9. Đường dẫn là của đúng máy/container?
10. Role có SELECT trên đúng bảng/cột?
11. COPY server-file có quyền và OS access cần thiết?
12. Tránh cấp pg_write_server_files/pg_execute_server_program rộng?
13. Local client có quyền ghi file?
14. Không dùng PROGRAM với command chứa input không tin cậy?

### Định dạng

15. Chọn CSV/text/binary đúng consumer?
16. Header true/false đúng contract?
17. Delimiter/quote/escape được quy định?
18. NULL khác empty string đúng mong đợi?
19. Encoding UTF-8 hoặc encoding mục tiêu?
20. DateStyle/TimeZone/IntervalStyle portable?
21. Consumer hiểu embedded newlines và quoted fields?
22. CSV formula injection đã được đánh giá nếu mở bằng spreadsheet?

### Security và vận hành

23. Export chạy bằng role least-privilege?
24. RLS đã được test bằng role thực tế?
25. Không có cột PII/secret ngoài phạm vi?
26. File có ACL/encryption/retention phù hợp?
27. Snapshot nhất quán nếu nhiều file?
28. Export lớn có ảnh hưởng vacuum/locks/storage?
29. File ghi staging và chỉ publish khi thành công?
30. Có row count, file size và checksum?
31. Log không chứa dữ liệu nhạy cảm?
32. Có runbook retry/cleanup khi COPY lỗi giữa chừng?

---

## 32. Tổng kết

PostgreSQL cung cấp `COPY ... TO` để xuất rows từ bảng hoặc kết quả truy vấn. Đây là công cụ hiệu quả cho data export, nhưng phải hiểu rõ **đích file, quyền, format và snapshot**.

Những điểm cốt lõi:

- **`COPY ... TO '/server/path'`** ghi trên filesystem của PostgreSQL server; cần quyền server-file và OS access thích hợp.
- **`COPY ... TO STDOUT`** truyền dữ liệu qua connection. **`psql \copy ... TO 'client/path'`** nhận stream và ghi trên máy chạy psql, không cần quyền ghi file server.
- Dùng **`COPY (SELECT ...) TO`** cho lọc, JOIN, aggregate, view, partitioned table, biểu thức và thứ tự ổn định.
- Direct `COPY table TO` không hỗ trợ mọi loại relation; query form là lựa chọn tổng quát.
- CSV có quy tắc quote/escape cho delimiter, quote và newline; NULL và empty string được phân biệt bằng cách quote.
- UTF-8, DateStyle, TimeZone và IntervalStyle cần được thống nhất để file portable.
- RLS SELECT policies có áp dụng cho COPY TO table; hãy test dưới đúng runtime role.
- `COPY PROGRAM` server-side là quyền mạnh; không ghép input không tin cậy vào shell command.
- Nhiều file export có thể cần cùng snapshot; dùng transaction/isolation phù hợp, nhưng nhớ snapshot lâu có chi phí.
- Database transaction không rollback file client; hãy ghi staging, kiểm tra và publish sau khi hoàn tất.
- CSV escaping không đồng nghĩa spreadsheet formula safety; dữ liệu text không tin cậy cần được xử lý theo consumer.

**Câu hỏi tự kiểm tra:** Khi chạy `COPY (SELECT ...) TO '/tmp/report.csv'` từ laptop kết nối database cloud, file sẽ nằm ở đâu và ai cần quyền ghi? Nếu muốn file nằm trên laptop, lệnh nào phù hợp? Và nếu query export chứa tenant data, quyền/policy nào bảo đảm đúng phạm vi rows? Trả lời được ba câu này là bạn đã nắm những quyết định quan trọng nhất trước khi export dữ liệu từ PostgreSQL.

### Tài liệu PostgreSQL chính thức

- [COPY — copy data between a file and a table](https://www.postgresql.org/docs/current/sql-copy.html).
- [psql — \copy, frontend copy](https://www.postgresql.org/docs/current/app-psql.html).
- [psql — output formatting, \o, \g, --csv](https://www.postgresql.org/docs/current/app-psql.html).
- [Predefined Roles — pg_read_server_files, pg_write_server_files, pg_execute_server_program](https://www.postgresql.org/docs/current/predefined-roles.html).
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
- [COPY Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Date/Time Types and TimeZone](https://www.postgresql.org/docs/current/datatype-datetime.html).
- [Client Connection Defaults — client_encoding](https://www.postgresql.org/docs/current/runtime-config-client.html).
- [pgJDBC — Copy API](https://jdbc.postgresql.org/documentation/publicapi/org/postgresql/copy/CopyManager.html).
