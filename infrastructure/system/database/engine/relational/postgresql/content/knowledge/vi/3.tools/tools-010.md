# Tổ chức tệp SQL và nhật ký thí nghiệm để tái lập kết quả trong PostgreSQL

Một câu truy vấn trả đúng kết quả một lần chưa chứng minh được nó đáng tin cậy. Nếu thiếu thông tin về dữ liệu ban đầu, phiên bản PostgreSQL, thứ tự chạy lệnh hoặc điều kiện kiểm tra, người khác không thể tái lập và đánh giá kết luận.

Một thí nghiệm SQL nên là **bộ đầu vào có thể chạy lại** gồm schema, dữ liệu mẫu, truy vấn, tiêu chí thành công, script điều phối và nhật ký thực thi. Kết quả có thể được kiểm chứng độc lập thay vì phụ thuộc vào ảnh chụp terminal hay những thao tác thủ công chỉ người viết biết.

Bài này dùng `psql` và PostgreSQL để tổ chức một lab từ đầu đến cuối. Ví dụ có lệnh `DROP SCHEMA ... CASCADE`, **chỉ chạy trong database thực hành riêng**, tuyệt đối không áp dụng cho dữ liệu production.

## 1. Thí nghiệm “tái lập được” nghĩa là gì?

Một bộ thử nghiệm có thể bàn giao cần trả lời:

1. **Mục tiêu:** cần kiểm tra ngữ nghĩa SQL, ràng buộc hay hiệu năng gì?
2. **Điều kiện đầu vào:** server, database, schema, dữ liệu, cấu hình nào?
3. **Trình tự:** tệp nào chạy trước, tệp nào phụ thuộc tệp khác?
4. **Lệnh thực tế:** ai chạy, chạy bằng `psql` hay công cụ khác, với tham số nào?
5. **Kỳ vọng:** những số liệu, tập hàng hoặc hành vi nào được coi là đúng?
6. **Quan sát:** output, lỗi, cảnh báo, exit code thực tế ra sao?
7. **Tái lập:** có thể reset rồi chạy lại mà không cần thao tác chưa ghi lại hay không?

| Tiêu chí | Ý nghĩa |
| --- | --- |
| Repeatability | Cùng môi trường, cùng quy trình chạy lại và nhận kết luận tương đương |
| Reproducibility | Người khác dựng môi trường tương ứng và kiểm chứng cùng kết luận |
| Traceability | Từ log truy ngược tới tệp SQL, cấu hình và phiên bản mã đã chạy |
| Verification | Có phép kiểm tra tự động hoặc tiêu chí đối chiếu rõ ràng |

Kết quả không nhất thiết giống từng byte: `EXPLAIN ANALYZE` có thể báo thời gian khác nhau giữa hai lượt, và `SELECT` không có `ORDER BY` không bảo đảm thứ tự hàng. Với dữ liệu cố định, **kết quả nghiệp vụ** và các bất biến quan trọng mới là điều cần tái lập.

## 2. Phân chia trách nhiệm giữa các tệp

Thay vì đặt mọi lệnh vào một file dài, có thể tổ chức:

~~~text
postgresql-labs/
├── README.md
├── .gitignore
├── .env.example
├── sql/
│   ├── run.psql
│   ├── 00_recreate_schema.sql
│   ├── 10_seed_data.sql
│   ├── 20_queries.sql
│   ├── 30_explain.sql
│   └── 90_assertions.sql
├── scripts/
│   └── run-lab.sh
├── expected/
│   └── paid-orders.md
├── reports/
│   └── experiment-template.md
└── logs/
    └── .gitkeep
~~~

| Đường dẫn | Nhiệm vụ |
| --- | --- |
| `README.md` | Mục tiêu, điều kiện trước khi chạy, cách reset, kết quả mong đợi |
| `00_recreate_schema.sql` | Khởi tạo lại bảng, ràng buộc, index trong schema lab |
| `10_seed_data.sql` | Nạp dữ liệu cố định |
| `20_queries.sql` | Những câu SQL đang nghiên cứu |
| `30_explain.sql` | Phân tích kế hoạch khi cần |
| `90_assertions.sql` | Kiểm tra và báo lỗi nếu sai |
| `run.psql` | Điều phối thứ tự chạy trong `psql` |
| `scripts/run-lab.sh` | Gọi `psql`, lưu log và kiểm tra mã thoát |
| `expected/` | Tập kết quả hoặc diễn giải kỳ vọng |
| `reports/` | Báo cáo kết luận gắn với lần chạy |
| `logs/` | Bằng chứng thực thi, stdout/stderr và metadata |

Tiền tố `00`, `10`, `20`, `90` giúp đọc tên dễ hiểu, **không làm PostgreSQL tự chạy đúng thứ tự**. Tệp `run.psql` mới là nơi diễn đạt sự phụ thuộc.

~~~mermaid
flowchart TD
    A["README và môi trường"] --> B["00: Tạo schema"]
    B --> C["10: Seed dữ liệu"]
    C --> D["20: Query"]
    D --> E["90: Assertions"]
    E --> F{"Lượt chạy hợp lệ?"}
    F -->|"Có"| G["Log PASS + report"]
    F -->|"Không"| H["Log FAIL + điều tra"]
~~~

## 3. Tạo một database lab tách biệt

Ví dụ đặt tên database `lab_pg52`. Nếu tài khoản quản trị có quyền tạo database, có thể chạy:

~~~bash
createdb -h 127.0.0.1 -p 5432 -U postgres lab_pg52
~~~

Việc tạo database chỉ cần làm một lần. Hãy cấp một role `lab_user` có quyền phù hợp trong database lab; không dùng quyền quản trị toàn cluster cho mọi bài tập.

Kiểm tra kết nối trước khi reset:

~~~bash
psql -X -h 127.0.0.1 -p 5432 \
  -U lab_user -d lab_pg52 \
  -c "SELECT current_database(), current_user, version();"
~~~

Tên database và role có thể điều chỉnh theo môi trường. Bắt buộc xác nhận **đúng database thực hành** trước khi chạy lệnh xóa schema. Trong hệ thống nhiều người, mỗi người hoặc mỗi job CI nên có database/schema riêng để không dọn dữ liệu của nhau.

## 4. Tệp 00_recreate_schema.sql

Mục tiêu lab: đếm đơn đã thanh toán theo từng khách hàng và vẫn giữ khách hàng có số đơn bằng 0.

~~~sql
-- CHỈ CHẠY TRONG database lab_pg52.
BEGIN;

DROP SCHEMA IF EXISTS lab52 CASCADE;
CREATE SCHEMA lab52;

CREATE TABLE lab52.customers (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL,
    city text NOT NULL
);

CREATE TABLE lab52.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES lab52.customers (customer_id),
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    total numeric(12, 2) NOT NULL CHECK (total >= 0),
    created_at timestamptz NOT NULL
);

CREATE INDEX idx_lab52_orders_customer_status
    ON lab52.orders (customer_id, status);

COMMIT;
~~~

Giải thích:

- `DROP SCHEMA IF EXISTS lab52 CASCADE` xóa toàn bộ đối tượng thuộc schema lab52, kể cả dữ liệu cũ. Đây là **thao tác phá hủy**, chỉ phù hợp với schema thực hành sở hữu riêng.
- `BEGIN` và `COMMIT` nhóm DDL vào transaction. PostgreSQL cho phép rollback nhiều lệnh DDL phổ biến, nhưng không có nghĩa tất cả thao tác quản trị đều hợp lệ trong transaction.
- `lab52.customers` và `lab52.orders` dùng tên đầy đủ, giảm lệ thuộc vào `search_path`.
- `PRIMARY KEY`, `FOREIGN KEY`, `CHECK` ngăn seed sai âm thầm được chấp nhận.
- `numeric(12,2)` bảo toàn thập phân chính xác cho tổng tiền; `timestamptz` có ngữ nghĩa thời điểm tuyệt đối.

Không thay `lab52` bằng `public` rồi chạy trên database đang có dữ liệu của nhóm. Với hệ thống thật, dùng schema migration có kiểm soát, không dùng script reset học tập.

## 5. Tệp 10_seed_data.sql: dữ liệu xác định

~~~sql
BEGIN;

INSERT INTO lab52.customers
    (customer_id, customer_name, city)
VALUES
    (1, 'An',   'HCM'),
    (2, 'Binh', 'HAN'),
    (3, 'Chi',  'HCM'),
    (4, 'Dung', 'DNG');

INSERT INTO lab52.orders
    (order_id, customer_id, status, total, created_at)
VALUES
    (101, 1, 'paid',      120.00, '2026-11-01 08:00:00+00'),
    (102, 1, 'paid',       80.00, '2026-11-01 09:00:00+00'),
    (103, 2, 'paid',      150.00, '2026-11-02 10:00:00+00'),
    (104, 2, 'cancelled', 300.00, '2026-11-02 11:00:00+00'),
    (105, 3, 'paid',      220.00, '2026-11-03 12:00:00+00');

COMMIT;
~~~

Tập dữ liệu được chọn có chủ ý:

| Khách hàng | Số đơn paid | Doanh thu paid |
| --- | ---: | ---: |
| An | 2 | 200.00 |
| Binh | 1 | 150.00 |
| Chi | 1 | 220.00 |
| Dung | 0 | 0.00 |
| **Tổng** | **4** | **570.00** |

Dung chưa có đơn; Binh có một đơn bị hủy. Hai trường hợp này giúp xác minh bộ lọc và phép `LEFT JOIN`.

Tất cả ID và timestamp cố định, không dùng `now()` hoặc `random()`. Những hàm đó phù hợp ở lab khác, nhưng nếu đưa vào dataset cần so sánh nguyên văn, chúng tạo ra kết quả thay đổi theo đồng hồ hoặc random state.

## 6. Tệp 20_queries.sql: truy vấn cần kiểm chứng

~~~sql
SET TIME ZONE 'UTC';
SET DateStyle TO 'ISO, YMD';

-- Lấy cả khách hàng không có đơn paid.
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.total), 0)::numeric(12, 2) AS paid_revenue
FROM lab52.customers AS c
LEFT JOIN lab52.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;

-- Tổng hợp để đối chiếu.
SELECT
    COUNT(*) AS paid_orders,
    COALESCE(SUM(total), 0)::numeric(12, 2) AS paid_revenue
FROM lab52.orders
WHERE status = 'paid';
~~~

Kết quả truy vấn thứ nhất phải gồm bốn hàng như bảng seed. Truy vấn thứ hai phải trả count `4` và revenue `570.00`.

Các chi tiết quan trọng:

1. Điều kiện `status = 'paid'` ở `ON` giữ lại khách hàng không có đơn paid.
2. `COUNT(o.order_id)` không đếm hàng NULL của phía bảng đơn khi `LEFT JOIN` không ghép được.
3. `COALESCE` trả doanh thu 0 cho khách hàng không có đơn.
4. `ORDER BY c.customer_id` làm thứ tự dòng có thể đối chiếu.
5. `numeric` phù hợp hơn số gần đúng nếu mục tiêu là kiểm tra phép cộng số tiền.

Không nên dựa vào việc PostgreSQL “thường trả theo id” khi thiếu `ORDER BY`. Bộ tối ưu hóa có quyền thay đổi đường truy cập và thứ tự kết quả.

## 7. Tệp 90_assertions.sql: biến kỳ vọng thành lỗi khi sai

~~~sql
DO $$
DECLARE
    v_paid_count bigint;
    v_paid_revenue numeric;
    v_customer_count bigint;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(total), 0)
    INTO v_paid_count, v_paid_revenue
    FROM lab52.orders
    WHERE status = 'paid';

    SELECT COUNT(*)
    INTO v_customer_count
    FROM lab52.customers;

    IF v_paid_count <> 4 THEN
        RAISE EXCEPTION
            'Sai paid count: actual=%, expected=4',
            v_paid_count;
    END IF;

    IF v_paid_revenue <> 570.00 THEN
        RAISE EXCEPTION
            'Sai revenue: actual=%, expected=570.00',
            v_paid_revenue;
    END IF;

    IF v_customer_count <> 4 THEN
        RAISE EXCEPTION
            'Sai customer count: actual=%, expected=4',
            v_customer_count;
    END IF;

    RAISE NOTICE 'LAB52 assertions passed';
END
$$ LANGUAGE plpgsql;
~~~

Khối `DO` được PostgreSQL thực thi như một đoạn PL/pgSQL ẩn danh. Nếu điều kiện không đạt, `RAISE EXCEPTION` tạo lỗi để runner/CI đánh dấu thất bại. Khi đúng, `NOTICE` cho biết assertions chạy tới cuối.

Có thể mở rộng assertions cho:

- Danh sách ID trả về chính xác.
- Doanh thu từng khách hàng, kể cả khách hàng có 0 đơn.
- Không tồn tại hàng mồ côi hoặc giá trị âm.
- Một thao tác rollback không còn ảnh hưởng dữ liệu.
- Kết quả của truy vấn chỉ mục hoặc truy vấn đối chiếu đã xác định.

Không nên assertion “Execution Time phải đúng 0.123 ms”, vì thời gian phụ thuộc hạ tầng và tải của server.

## 8. Tệp run.psql: thứ tự chạy chuẩn

~~~text
\set ON_ERROR_STOP on
\pset pager off
\pset null '(null)'

\echo === Environment ===
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    current_setting('server_version') AS server_version,
    current_setting('TimeZone') AS timezone_name;

\echo === Recreate schema ===
\ir 00_recreate_schema.sql

\echo === Seed data ===
\ir 10_seed_data.sql

\echo === Queries ===
\ir 20_queries.sql

\echo === Assertions ===
\ir 90_assertions.sql

\echo === Finished ===
~~~

Trong `psql`:

- `\i file.sql` include một tệp theo đường dẫn được cung cấp.
- `\ir file.sql` include tương đối với **thư mục của chính tệp chứa lệnh include**, rất tiện khi `run.psql` và các tệp SQL cùng nằm trong `sql/`.
- `\set ON_ERROR_STOP on` dừng script khi gặp lỗi.
- `\pset pager off` ngăn trình phân trang giao diện làm phiền khi chạy tự động.
- `\pset null '(null)'` giúp phân biệt SQL NULL với chuỗi rỗng.
- `\echo` chèn mốc dễ tìm trong nhật ký.

Các lệnh bắt đầu bằng `\` là **meta-command của psql**, không phải SQL. Nếu chạy bằng JDBC hay SQL console không hỗ trợ psql, cần một cơ chế điều phối khác.

## 9. Gọi psql từ terminal

Ở thư mục gốc repository:

~~~bash
psql \
  -X \
  -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 \
  -p 5432 \
  -U lab_user \
  -d lab_pg52 \
  -f sql/run.psql
~~~

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-X` | Không đọc file cấu hình cá nhân `.psqlrc`, giảm ảnh hưởng môi trường |
| `-v ON_ERROR_STOP=1` | Dừng khi script SQL lỗi |
| `-h`, `-p` | Chọn rõ host và port |
| `-U`, `-d` | Chọn rõ role và database |
| `-f` | Chạy nội dung của script |

Với `ON_ERROR_STOP`, `psql -f` có thể trả mã thoát `3` khi một lỗi xảy ra trong script. Lỗi kết nối hoặc lỗi của chương trình có thể trả mã khác. Hãy xem **mọi exit code khác 0 là thất bại**, không chỉ tìm chuỗi ERROR trong output.

### Tùy chọn single transaction

`psql -1` có thể bao các lệnh từ `-f` và `-c` trong một transaction, nhưng ví dụ hiện tại đã có `BEGIN` / `COMMIT` bên trong các file setup. Không bật thêm `-1` mà không thiết kế lại transaction boundaries.

Ngoài ra, những lệnh như `CREATE DATABASE` không được chạy trong transaction block. Do đó database lab được tạo trước, không đặt trong `run.psql`.

## 10. Script chạy và lưu nhật ký

Nội dung `scripts/run-lab.sh` cho Bash:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
log_file="logs/$stamp-lab52.log"
meta_file="logs/$stamp-lab52.meta.txt"

{
  printf 'experiment=lab52-paid-orders\n'
  printf 'started_at_utc=%s\n' "$stamp"
  printf 'host=127.0.0.1\n'
  printf 'port=5432\n'
  printf 'database=lab_pg52\n'
  printf 'role=lab_user\n'
  printf 'script=sql/run.psql\n'
  psql --version
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'git_commit=%s\n' "$(git rev-parse HEAD)"
  fi
} > "$meta_file"

if psql -X -a -v ON_ERROR_STOP=1 \
    -h 127.0.0.1 -p 5432 -U lab_user -d lab_pg52 \
    -f sql/run.psql > "$log_file" 2>&1; then
  printf 'exit_code=0\n' >> "$meta_file"
  printf 'PASS: %s\n' "$log_file"
else
  result=$?
  printf 'exit_code=%s\n' "$result" >> "$meta_file"
  printf 'FAIL (exit %s): %s\n' "$result" "$log_file" >&2
  exit "$result"
fi
~~~

Script giữ lại:

- Thời gian bắt đầu theo UTC để truy vết.
- Tên database, role, host, port và script được chạy.
- Phiên bản `psql` và Git commit nếu có.
- Nội dung `psql` thực thi qua `-a` (echo các dòng input), kết quả và lỗi.
- Exit code trong metadata và trạng thái PASS/FAIL của runner.

Dòng `> "$log_file" 2>&1` gộp stdout/stderr của `psql` vào cùng một tệp. Nếu cần phân tích tự động có thể lưu riêng `.out.log` và `.err.log`. Với hai job chạy cùng một giây, tên `stamp` có thể bị trùng; trong CI nên thêm run ID/job ID duy nhất.

**Bảo mật:** không hard-code password vào script. Có thể dùng credential store của môi trường hoặc `.pgpass` với quyền truy cập thích hợp. Trên Unix, tệp `.pgpass` thường cần quyền chỉ dành cho chủ sở hữu (ví dụ `chmod 600`); không commit credential thật.

## 11. Mẫu README để đồng nghiệp tự chạy

README cần có thông tin tối thiểu:

~~~markdown
# Lab 52 - Paid orders

## Mục tiêu
Kiểm tra LEFT JOIN giữ mọi khách hàng và tính đúng số đơn paid.

## Yêu cầu
- PostgreSQL server và psql client
- Database lab_pg52 riêng cho thực hành
- Role lab_user có quyền tạo schema trong database lab
- Bash nếu chạy scripts/run-lab.sh

## Chạy
Từ thư mục gốc:

    psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 5432 \
      -U lab_user -d lab_pg52 -f sql/run.psql

Hoặc:

    bash scripts/run-lab.sh

## Kết quả mong đợi
- 4 khách hàng
- 4 đơn paid, tổng 570.00
- Dung vẫn xuất hiện với count 0
- Assertions pass và psql exit code 0

## Cảnh báo
Script 00_recreate_schema.sql xóa schema lab52.
Không chạy vào database sản xuất.
~~~

Người khác không nên phải hỏi lại “bảng nào tạo trước?”, “đăng nhập role nào?”, “cần dữ liệu mẫu nào?” hoặc “làm sao biết kết quả đúng?”. Những điều đó thuộc tài liệu tái lập.

## 12. Nhật ký thí nghiệm có cấu trúc

Một report cho mỗi lượt chạy có thể ghi:

~~~markdown
# Experiment - lab52-paid-orders

- Run ID: <mã lượt chạy>
- Mục tiêu: kiểm tra thống kê đơn paid bằng LEFT JOIN
- SQL version: <Git commit và trạng thái working tree>
- PostgreSQL server: <phiên bản>
- psql client: <phiên bản>
- Database/schema: lab_pg52 / lab52
- Host/port/role: <giá trị lab>
- Timezone: UTC
- Started at: <thời điểm UTC>
- Script: sql/run.psql
- Kết quả mong đợi: count 4, revenue 570.00
- Kết quả quan sát: <giá trị từ log>
- Exit code: <số>
- Sai khác/cảnh báo: <nếu có>
- Log: logs/<run-id>-lab52.log
- Kết luận: PASS/FAIL, nguyên nhân và hành động tiếp theo
~~~

Mỗi trường trả lời một vấn đề: **khi nào, ở đâu, dùng mã nào, chạy gì, kết quả gì**.

Kết quả mong đợi đặt ở `expected/` hoặc assertions; kết quả quan sát đặt trong log. Không chỉnh log gốc sau khi chạy cho khớp kỳ vọng. Viết phần giải thích tại `reports/`.

## 13. Kiểm soát những nguồn gây kết quả khác nhau

### 13.1. Thứ tự của SELECT

~~~sql
-- Không bảo đảm thứ tự.
SELECT customer_id FROM lab52.customers;

-- Thứ tự xác định.
SELECT customer_id
FROM lab52.customers
ORDER BY customer_id;
~~~

Kết quả của `LIMIT` cũng có thể thay đổi nếu thiếu `ORDER BY`:

~~~sql
SELECT customer_id
FROM lab52.customers
ORDER BY customer_id
LIMIT 3;
~~~

Khi cột sort có thể trùng, dùng thêm khóa tie-breaker để thứ tự hoàn toàn xác định.

### 13.2. Ngày giờ, locale và định dạng

`now()`, `clock_timestamp()` và `CURRENT_DATE` phụ thuộc thời điểm chạy. `timestamptz` được hiển thị theo `TimeZone` của session. Vì thế ví dụ dùng timestamp có `+00` và `SET TIME ZONE 'UTC'`.

Sắp xếp văn bản có thể phụ thuộc collation của database. Nếu cần so sánh đầu ra Unicode giữa nhiều hệ thống, phải kiểm soát hoặc ghi nhận quy tắc sắp xếp.

### 13.3. Random và sequence

`random()` gây dữ liệu biến động khi không kiểm soát seed. `nextval()` của sequence không có cùng hành vi rollback như dữ liệu bảng và có thể tạo khoảng trống ID. Khi viết seed dùng để kiểm chứng nguyên văn, nên chọn ID cố định hoặc reset sequence đúng cách.

### 13.4. Cấu hình cá nhân

`.psqlrc`, `PGHOST`, `PGDATABASE`, `search_path`, `DateStyle`, `TimeZone` và những thiết lập của role có thể làm kết quả khác giữa máy. Dùng `-X`, chỉ định rõ kết nối và ghi lại cấu hình có ảnh hưởng.

## 14. Ghi EXPLAIN và đo hiệu năng

Một tệp `sql/30_explain.sql` có thể chứa:

~~~sql
EXPLAIN (VERBOSE, COSTS, FORMAT TEXT)
SELECT c.customer_id, COUNT(o.order_id)
FROM lab52.customers AS c
LEFT JOIN lab52.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

`EXPLAIN` thường chỉ hiển thị kế hoạch ước lượng. Nếu muốn đo số liệu chạy thật:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT c.customer_id, COUNT(o.order_id)
FROM lab52.customers AS c
LEFT JOIN lab52.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

`EXPLAIN ANALYZE` **thực sự thực thi câu SQL**. Đối với `UPDATE` hoặc `DELETE`, điều đó có thể thay đổi dữ liệu; chỉ thử trong lab và transaction/rollback phù hợp.

Khi ghi hiệu năng, lưu phiên bản server, kích thước bảng/chỉ mục, statistics, execution plan, actual rows, buffers, thời gian, tải hệ thống và số lần đo. Không yêu cầu từng lượt có cùng thời gian thực thi. Với bảng chỉ vài dòng, PostgreSQL có thể chọn `Seq Scan` dù có index; điều này không chứng minh chỉ mục sai.

## 15. Xuất kết quả dạng CSV khi cần diff tự động

Log có SQL và thông báo hữu ích để chẩn đoán nhưng khó so sánh bằng máy. Có thể xuất kết quả riêng:

~~~bash
psql -X -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 -p 5432 -U lab_user -d lab_pg52 \
  --csv \
  -c "
    SELECT customer_id, customer_name
    FROM lab52.customers
    ORDER BY customer_id;
  " > customers.csv
~~~

Tùy phiên bản `psql`, có thể dùng `\copy (SELECT ...) TO STDOUT WITH (FORMAT csv, HEADER true)` thay cho `--csv`. Phân biệt `COPY` phía server và `\copy` phía client để tránh nhầm quyền ghi file.

Nên tách **log thực thi**, **artifact kết quả** và **report kết luận**. Nếu muốn diff CSV, phải chuẩn hóa thứ tự dòng, null representation, encoding, timezone và định dạng dữ liệu.

## 16. Thí nghiệm đồng thời cần hai phiên riêng

Các bài về MVCC, lock wait và deadlock không thể mô phỏng đầy đủ bằng một luồng `run.psql` tuần tự. Cần timeline nhiều session:

| Bước | Phiên A | Phiên B | Trạng thái |
| --- | --- | --- | --- |
| 1 | `BEGIN` | — | A mở transaction |
| 2 | `UPDATE ... WHERE id=1` | — | A giữ khóa |
| 3 | — | `BEGIN` | B mở transaction |
| 4 | — | `UPDATE ... WHERE id=1` | B chờ A |
| 5 | `COMMIT` | Câu UPDATE tiếp tục | A giải phóng khóa |
| 6 | — | `COMMIT` | B kết thúc |

Cần ghi `pg_backend_pid()` của từng phiên, bước đồng bộ, timeout, kết quả và cách rollback/commit. Không chỉ dùng `sleep 1` để hy vọng các thao tác luôn chạy đúng thứ tự trên mọi máy.

## 17. Gắn với Git và giữ dữ liệu an toàn

**Nên commit:** các tệp SQL, runner, README, assertions, dữ liệu mẫu giả, expected results nhỏ và template report.

**Tránh commit:** mật khẩu, token, log chứa dữ liệu nhạy cảm, dump production, artifact lớn có thể tái tạo.

Ví dụ `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
.pgpass
*.pgpass
logs/*.log
logs/*.meta.txt
artifacts/*.csv
~~~

`.gitignore` không xóa những secret đã commit trước đó khỏi lịch sử Git. Cần quản lý credential và xử lý dữ liệu nhạy cảm ở nguồn.

SHA từ `git rev-parse HEAD` chỉ xác định commit, không bao gồm sửa đổi chưa commit. Với thí nghiệm cần truy vết nghiêm ngặt, ghi cả trạng thái working tree hoặc checksum tệp thực sự đã chạy.

## 18. Tích hợp vào CI

Khi `run.psql` có assertions và exit code rõ ràng, pipeline có thể:

~~~text
Checkout mã nguồn
   ↓
Khởi động PostgreSQL test
   ↓
Tạo database/role lab riêng
   ↓
Chạy psql -X -v ON_ERROR_STOP=1 -f sql/run.psql
   ↓
Lưu log, metadata, artifacts
   ↓
Đánh dấu PASS hoặc FAIL
~~~

Điều kiện bắt buộc:

- Tuyệt đối không trỏ script reset tới production.
- Mỗi job có database hoặc schema độc lập.
- Ghi hoặc cố định PostgreSQL server version.
- Credential lấy từ secret store của CI.
- Lưu log cả khi job thất bại.
- Exit code khác 0 phải làm job thất bại.

Nếu dùng Docker, cần ghi rõ image tag, hostname, port và nơi chạy client. `127.0.0.1` trong container không đương nhiên trỏ tới PostgreSQL ở container khác.

## 19. Lỗi thường gặp khi lưu và chạy thí nghiệm

### Chỉ lưu query.sql

Thiếu schema và dữ liệu đầu vào, kết quả khó tái lập. Hãy lưu cả setup, seed và thứ tự thực thi.

### Không bật ON_ERROR_STOP

SQL có thể lỗi mà script vẫn chạy tiếp. Luôn bật biến và kiểm tra exit code trong automation.

### Dùng đường dẫn include phụ thuộc cwd

Script chạy đúng khi ở thư mục `sql/` nhưng sai từ repo root. Dùng `\ir` và runner xác định thư mục.

### Dùng DROP CASCADE quá rộng

Có thể xóa dữ liệu người khác. Giới hạn phạm vi trong database/schema lab và xác nhận kết nối trước.

### So sánh SELECT thiếu ORDER BY

Tập hàng giống nhau nhưng thứ tự có thể khác. Thêm `ORDER BY` và tie-breaker ổn định.

### Không phân biệt expected và actual

Đừng sửa log cho khớp kỳ vọng. Viết expected trước, actual trong log, kết luận trong report.

### Dùng EXPLAIN ANALYZE tưởng là “chỉ xem”

Với DML, truy vấn được thực thi và có thể ghi dữ liệu. Chỉ đo trong môi trường thử an toàn.

### Đặt password và dữ liệu thật trong log

`psql -a` có thể in literal SQL. Dùng dữ liệu giả, secret store và chính sách lưu trữ đúng.

### Đánh giá performance bằng một con số

Thời gian bị ảnh hưởng bởi cache và tải. Đo nhiều lượt, ghi điều kiện và xem phân bố.

### Chỉ ghi Git commit nhưng đang có sửa đổi chưa commit

Khi đó commit không phản ánh chính xác các tệp đã chạy. Ghi trạng thái dirty hoặc checksum khi cần.

## 20. Quy trình tạo một lab PostgreSQL mới

1. Xác định giả thuyết có thể kiểm chứng.
2. Chuẩn bị database/schema thực hành tách biệt.
3. Viết tệp dựng lược đồ và ràng buộc.
4. Viết seed dữ liệu cố định, gồm các trường hợp biên.
5. Viết truy vấn với điều kiện và thứ tự kết quả rõ ràng.
6. Viết assertions biểu diễn kỳ vọng.
7. Dùng `run.psql` điều phối tệp qua `\ir`.
8. Gọi `psql -X` với `ON_ERROR_STOP` và kết nối tường minh.
9. Ghi log, exit code, thời gian, phiên bản, commit/checksum.
10. So sánh expected và actual, điều tra lỗi trong log gốc.
11. Chạy lại từ trạng thái sạch sau khi sửa.
12. Commit tệp nguồn và README an toàn để người khác tái lập.

Một dấu hiệu tốt là đồng nghiệp hoặc job CI có thể dựng database mới chỉ từ repository và README, không phải hỏi lại tác giả đã thực hiện thao tác thủ công nào trước đó.

## 21. Kết luận

**Thí nghiệm PostgreSQL có thể tái lập không chỉ là câu SQL đúng, mà là một quy trình có đầu vào, thứ tự, kiểm tra và bằng chứng đầy đủ.** Tách tệp theo chuỗi **reset schema → seed → queries → assertions**, dùng `psql` với `\ir` và `ON_ERROR_STOP`, lưu log kèm metadata và gắn kết quả với phiên bản mã giúp người khác kiểm chứng kết luận một cách độc lập.

Khi các điều kiện đầu vào được kiểm soát và mọi sai khác đều có log để truy vết, quá trình học truy vấn, chỉ mục và giao dịch trở nên đáng tin cậy, dễ duy trì và thuận tiện mở rộng thành kiểm thử tự động trong dự án PostgreSQL.
