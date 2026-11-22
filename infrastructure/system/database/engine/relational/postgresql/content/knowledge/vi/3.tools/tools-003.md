# Thực thi tệp SQL, biến psql và xử lý lỗi trong script PostgreSQL

## 1. Vì sao cần thực thi SQL theo tệp?

Khi mới học PostgreSQL, ta thường mở `psql` rồi nhập từng câu SQL. Tuy nhiên, trong dự án thực tế, công việc tạo schema, nạp dữ liệu ban đầu, chạy báo cáo hoặc cập nhật cấu trúc bảng có thể gồm hàng chục hay hàng trăm câu lệnh. Lưu các lệnh này vào tệp `.sql` giúp quy trình **có thể tái lập, xem xét thay đổi và tự động hóa**.

Ví dụ một lần triển khai database cần:

1. Tạo schema nếu chưa có.
2. Tạo bảng và ràng buộc.
3. Nạp dữ liệu thử.
4. Kiểm tra một số điều kiện và xuất báo cáo.
5. Dừng toàn bộ quy trình nếu có lỗi SQL.
6. Trả mã thoát khác 0 để CI/CD biết việc triển khai thất bại.

`psql` là công cụ dòng lệnh của PostgreSQL có thể thực hiện tất cả các bước trên. Ngoài SQL, `psql` cung cấp **meta-command** (bắt đầu bằng `\`), **biến psql** và các tùy chọn kiểm soát lỗi.

```text
Terminal / CI
    |
    | psql -X -v ON_ERROR_STOP=1 -f main.sql
    v
+------------------------------------+
| psql (máy khách)                    |
| - Đọc tệp SQL                      |
| - Xử lý \i / \ir / \set / \if       |
| - Thay biến :name                  |
| - Gửi câu SQL đến PostgreSQL       |
| - In lỗi, trả exit code            |
+------------------+-----------------+
                   |
                   | PostgreSQL protocol
                   v
+------------------------------------+
| PostgreSQL Server                  |
| - Kiểm tra cú pháp và quyền        |
| - Thực thi SQL / giao dịch         |
| - Kiểm tra khóa và ràng buộc       |
+------------------------------------+
```

**Điểm cốt lõi:** `\set`, `\echo` và `\ir` là lệnh do **psql xử lý ở client**, không phải cú pháp SQL có thể gửi nguyên vẹn tới server qua JDBC.

## 2. Chuẩn bị PostgreSQL và psql

Kiểm tra phiên bản client ở terminal:

```bash
psql --version
```

Kết nối database thử nghiệm:

```bash
psql --host=localhost --port=5432 \
     --username=lab_user --dbname=lab_db
```

Các giá trị `localhost`, `lab_user` và `lab_db` là ví dụ. Chỉ thay bằng endpoint và tài khoản được phép dùng; không dùng tài khoản superuser cho những việc không cần quyền quản trị.

Trong dấu nhắc `psql`, có thể nhập:

```text
\conninfo
\dt
\?
\q
```

| Meta-command | Tác dụng |
| --- | --- |
| `\conninfo` | Hiển thị thông tin kết nối |
| `\dt` | Liệt kê bảng phù hợp search path |
| `\d ten_bang` | Mô tả cấu trúc bảng |
| `\?` | Trợ giúp lệnh psql |
| `\h CREATE TABLE` | Trợ giúp cú pháp SQL |
| `\q` | Thoát khỏi phiên psql |

Hai môi trường dễ bị nhầm:

- **Terminal:** chạy `psql -f setup.sql` hoặc `psql -c "SELECT 1"`.
- **Trong psql:** nhập `\i setup.sql` hoặc `SELECT 1;`.

Nếu thấy dấu nhắc như `lab_db=>`, bạn đang bên trong psql; nếu thấy dấu nhắc Bash/PowerShell, bạn đang ở shell của hệ điều hành.

## 3. Chạy file SQL bằng `-f` / `--file`

Tạo một file `setup.sql` UTF-8:

```sql
CREATE SCHEMA IF NOT EXISTS demo_psql;

CREATE TABLE IF NOT EXISTS demo_psql.products (
    product_id bigint PRIMARY KEY,
    product_name text NOT NULL,
    price numeric(12,2) NOT NULL CHECK (price >= 0)
);

INSERT INTO demo_psql.products
    (product_id, product_name, price)
VALUES
    (1, 'Sổ tay', 35000.00)
ON CONFLICT (product_id) DO NOTHING;
```

Thực thi trong terminal:

```bash
psql -h localhost -U lab_user -d lab_db -f setup.sql
```

Hoặc:

```bash
psql --host=localhost \
     --username=lab_user \
     --dbname=lab_db \
     --file=setup.sql
```

`psql` đọc file theo thứ tự, gửi các câu SQL đến PostgreSQL và xử lý meta-command nếu file chứa chúng. Sau khi chạy:

```sql
SELECT product_id, product_name, price
FROM demo_psql.products
ORDER BY product_id;
```

Kết quả mẫu:

| product_id | product_name | price |
| ---: | --- | ---: |
| 1 | Sổ tay | 35000.00 |

**Lưu ý:** `IF NOT EXISTS` giúp không báo lỗi khi đối tượng đã có, nhưng nó không xác minh cấu trúc hiện tại có đúng như mong muốn. `ON CONFLICT DO NOTHING` bỏ qua hàng trùng khóa trong ví dụ; đây không phải chiến lược áp dụng cho mọi loại dữ liệu.

### 3.1. Khi nào dùng `-c`?

Chạy một câu SQL ngắn:

```bash
psql -h localhost -U lab_user -d lab_db \
  -c "SELECT current_database(), current_user;"
```

Có thể dùng nhiều `-c` cho nhiều command:

```bash
psql -h localhost -U lab_user -d lab_db \
  -c "SELECT now();" \
  -c "SELECT current_database();"
```

Một tham số `-c` có thể biểu thị chuỗi SQL gửi trực tiếp cho server hoặc một meta-command psql phù hợp. Không nên trộn SQL và meta-command trong cùng một chuỗi `-c`; dùng `-f` nếu cần script nhiều bước. Đặc biệt, cơ chế thay biến psql trong chuỗi SQL của `-c` không giống khi chạy file; hãy dùng `-f` để khai thác `:name` trong SQL một cách rõ ràng.

### 3.2. Chạy qua standard input

```bash
psql -h localhost -U lab_user -d lab_db < setup.sql
```

Cách này cũng có thể thực thi SQL, nhưng `-f` thường thuận tiện hơn vì thông báo lỗi có thể ghi rõ **tên file và số dòng**, giúp xử lý script dài.

## 4. Chạy nhiều file: `\i` và `\ir`

Trong psql, bạn có thể include file:

```text
\i setup.sql
\ir steps/01_schema.sql
```

Hai lệnh có khác biệt quan trọng:

| Meta-command | Mục đích | Cách xử lý đường dẫn tương đối |
| --- | --- | --- |
| `\i` | Đọc và thực thi một file khác | Tương đối với **thư mục làm việc hiện tại của psql** |
| `\ir` | Include relative | Tương đối với **thư mục chứa script đang thực thi** |

Giả sử:

```text
project/
└── sql/
    ├── main.sql
    └── steps/
        ├── 01_schema.sql
        ├── 02_seed.sql
        └── 03_report.sql
```

File `sql/main.sql`:

```sql
\set ON_ERROR_STOP on

\echo Starting PostgreSQL setup

\ir steps/01_schema.sql
\ir steps/02_seed.sql
\ir steps/03_report.sql

\echo Setup completed
```

Khi gọi:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f project/sql/main.sql
```

`\ir` tìm các file trong thư mục `project/sql/steps/`, vì nó dựa vào vị trí file `main.sql`, không phụ thuộc nơi người dùng đang đứng trong terminal.

Nếu bạn dùng `\i steps/01_schema.sql`, psql sẽ diễn giải tương đối với working directory; cùng script có thể chạy được trên máy này nhưng lỗi đường dẫn trên máy khác.

**Thực hành tốt:** dùng `\ir` cho các file con thuộc cùng bộ script; dùng đường dẫn đầy đủ hoặc đảm bảo working directory khi cần `\i`.

## 5. Biến psql: tạo và sử dụng

Biến psql là giá trị được quản lý trong **phiên psql**, có thể được đưa vào SQL hay meta-command bằng cú pháp `:var`. Chúng cho phép cùng một file chạy với những tham số khác nhau.

### 5.1. Truyền biến từ command line với `-v`

```bash
psql -h localhost -U lab_user -d lab_db \
  -v target_schema=demo_lab \
  -v min_amount=100000 \
  -f report.sql
```

`-v` là viết tắt của `--set`. Các biến `target_schema` và `min_amount` được đặt trong phiên psql trước khi script được chạy.

### 5.2. Đặt biến trong psql với `\set`

```text
\set target_schema demo_lab
\set min_amount 100000
\echo Schema: :target_schema
```

Xóa một biến:

```text
\unset min_amount
```

Lệnh `\set` khi không có tham số liệt kê các biến hiện hành. Cần thận trọng nếu ai đó đã lưu thông tin nhạy cảm vào biến: đừng in danh sách biến ra log công khai.

### 5.3. Phân biệt biến psql với SQL parameter

| Khái niệm | Được xử lý tại đâu? | Ví dụ |
| --- | --- | --- |
| Biến psql | Ở client `psql` | `:target_schema`, `\set` |
| Tham số prepared statement | Ở cơ chế SQL/driver | `$1`, bind values |
| Cấu hình phiên server | PostgreSQL backend | `SET search_path TO ...` |

Biến psql **không phải bind parameter** của driver JDBC. Một file dùng `:name` cần được thực thi trong môi trường có xử lý biến psql; gửi nguyên văn qua API SQL khác có thể lỗi cú pháp.

## 6. Quote biến chính xác: `:var`, `:'var'`, `:"var"`

Đây là lỗi phổ biến nhất khi viết script có tham số.

| Cú pháp | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| `:name` | Chèn nội dung biến gần như nguyên dạng vào cú pháp SQL | Chỉ với SQL fragment/giá trị đã tin cậy |
| `:'name'` | Quote biến thành **SQL string literal** | Văn bản hoặc literal cần cast sang kiểu khác |
| `:"name"` | Quote biến thành **SQL identifier** | Tên schema, bảng, cột |

Ví dụ biến:

```text
\set target_schema demo_lab
\set customer_name 'Nguyễn An'
\set min_amount 150000
```

Giá trị văn bản:

```sql
SELECT :'customer_name' AS selected_customer;
```

Tên đối tượng:

```sql
CREATE SCHEMA IF NOT EXISTS :"target_schema";
```

Giá trị số được quote thành literal và cast:

```sql
SELECT order_id, amount
FROM demo_lab.orders
WHERE amount >= :'min_amount'::numeric;
```

**Không thêm dấu nháy sẵn xung quanh biến**:

```sql
-- Sai ý tưởng: nội dung bên trong nháy là văn bản cố định.
SELECT ':customer_name';

-- Đúng: psql tạo literal SQL được quote an toàn.
SELECT :'customer_name';
```

Tương tự, `:'target_schema'` tạo **chuỗi**, không phải identifier; tên schema phải dùng `:"target_schema"`.

### 6.1. Rủi ro của `:name` chèn thô

```sql
-- Không dùng với giá trị lấy trực tiếp từ input chưa được kiểm soát.
SELECT * FROM demo_lab.orders WHERE amount >= :min_amount;
```

`psql` chèn nội dung biến vào cú pháp SQL. Nếu biến chứa nội dung không phải số như mong đợi, truy vấn có thể lỗi hoặc bị biến đổi ngoài ý muốn. Cách an toàn và rõ kiểu hơn là:

```sql
SELECT *
FROM demo_lab.orders
WHERE amount >= :'min_amount'::numeric;
```

Quote thành literal không tự xác minh quy tắc nghiệp vụ. Nếu người dùng gửi giá trị không chuyển được sang `numeric`, server nên báo lỗi.

### 6.2. Kiểm tra biến có tồn tại chưa

`psql` hỗ trợ biểu thức kiểm tra sự tồn tại biến:

```text
\if :{?target_schema}
  \echo Target schema was supplied
\else
  \echo Target schema is missing
\endif
```

`:{?target_schema}` chỉ kiểm tra biến đã được định nghĩa, không đảm bảo giá trị thuộc danh sách schema được phép thao tác. Khi script chạy tự động, nên kiểm tra cấu hình bắt buộc ở shell gọi script và bật `ON_ERROR_STOP`.

## 7. Thực hành: dùng biến để chọn schema

File `01_schema.sql`:

```sql
CREATE SCHEMA IF NOT EXISTS :"target_schema";

CREATE TABLE IF NOT EXISTS :"target_schema".orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Lệnh chạy:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -v target_schema=demo_batch \
  -h localhost -U lab_user -d lab_db \
  -f 01_schema.sql
```

Khi `target_schema=demo_batch`, lệnh tạo `demo_batch.orders`. Cùng script có thể chạy với `target_schema=demo_test` để tạo schema thử nghiệm khác.

**Lưu ý:** không dùng biến tên schema để tự chọn đối tượng production khi người dùng có thể truyền bất kỳ giá trị nào. `:"name"` giúp quote identifier an toàn về cú pháp, nhưng lựa chọn *schema nào được phép sửa* vẫn là chính sách quyền và kiểm tra nghiệp vụ.

## 8. Nạp dữ liệu và truyền tham số lọc

File `02_seed.sql`:

```sql
INSERT INTO :"target_schema".orders
    (order_id, customer_name, amount)
VALUES
    (1, 'Nguyễn An', 120000.00),
    (2, 'Trần Bình', 250000.00),
    (3, 'Lê Chi', 80000.00)
ON CONFLICT (order_id) DO UPDATE
SET customer_name = EXCLUDED.customer_name,
    amount = EXCLUDED.amount;
```

Ví dụ dùng `ON CONFLICT` để file nạp dữ liệu mẫu có thể chạy lại mà không báo lỗi trùng khóa. Trong hệ thống thật, **việc ghi đè dữ liệu cũ khi xung đột là một quyết định nghiệp vụ**, không nên áp dụng tự động cho mọi migration.

File `03_report.sql`:

```sql
SELECT
    order_id,
    customer_name,
    amount
FROM :"target_schema".orders
WHERE amount >= :'min_amount'::numeric
ORDER BY amount DESC, order_id ASC;
```

Chạy với:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -v target_schema=demo_batch \
  -v min_amount=100000 \
  -h localhost -U lab_user -d lab_db \
  -f 03_report.sql
```

Kết quả trên dữ liệu mẫu:

| order_id | customer_name | amount |
| ---: | --- | ---: |
| 2 | Trần Bình | 250000.00 |
| 1 | Nguyễn An | 120000.00 |

Ở đây biến được chuyển thành SQL literal bằng `:'min_amount'`, rồi PostgreSQL ép sang kiểu `numeric`.

## 9. `\gset`: lấy một hàng SQL thành biến psql

Không phải biến nào cũng cần lấy từ tham số terminal. `psql` có meta-command `\gset` để nhận giá trị từ **một hàng kết quả** của một câu `SELECT` rồi đặt chúng thành biến psql.

```sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(amount), 0)::numeric AS total_amount
FROM :"target_schema".orders
\gset

\echo Total orders: :order_count
\echo Total amount: :total_amount
```

`SELECT` này trả một hàng tổng hợp, nên phù hợp với `\gset`.

Các quy tắc đáng nhớ:

- Query phải trả **đúng một hàng**. Nếu 0 hàng hoặc nhiều hơn 1 hàng, psql không thể gán theo cách này.
- Tên các cột kết quả trở thành tên biến.
- Nếu giá trị một cột là SQL `NULL`, biến tương ứng có thể bị unset.
- Có thể dùng tiền tố, ví dụ `\gset stats_` để đặt `stats_order_count`.
- Biến tạo bởi `\gset` vẫn chỉ sống ở phía client psql.

`\gset` không phải là `INSERT` và không tự ghi kết quả vào database.

## 10. `\if`, `\elif`, `\else` trong script

psql hỗ trợ điều kiện để quyết định có thực hiện một đoạn script hay không:

```text
\set run_report true

\if :run_report
  \echo Running report
\else
  \echo Report skipped
\endif
```

Các giá trị điều kiện nên là boolean dễ hiểu như `true/false`, `on/off`, `yes/no` hoặc `1/0`.

**Không xem `\if` như một trình thông dịch biểu thức SQL.** Ví dụ:

```text
-- Không phải cú pháp so sánh SQL để psql tự tính:
\if :order_count > 0
```

Nếu cần điều kiện dựa trên dữ liệu database, dùng `SELECT` để tính trước:

```sql
SELECT CASE
         WHEN COUNT(*) > 0 THEN 'true'
         ELSE 'false'
       END AS has_orders
FROM :"target_schema".orders
\gset

\if :has_orders
  \echo Orders were found
\else
  \echo No orders found
\endif
```

Khi điều kiện quyết định **một thao tác ghi quan trọng**, hãy cân nhắc tính nguyên tử của SQL/transaction thay vì “đọc kết quả qua psql rồi một lát sau cập nhật” trong nhiều bước không được bảo vệ.

## 11. Vấn đề: một SQL lỗi nhưng script vẫn chạy tiếp

Mặc định, nếu không bật `ON_ERROR_STOP`, psql có thể in lỗi rồi **tiếp tục chạy những câu SQL sau đó**. Điều này đặc biệt nguy hiểm với migration.

Ví dụ file `bad_setup.sql`:

```sql
CREATE TABLE demo_psql.example_one (
    id integer PRIMARY KEY
);

-- Cố tình lỗi: bảng không tồn tại.
INSERT INTO demo_psql.no_such_table(id)
VALUES (1);

CREATE TABLE demo_psql.example_two (
    id integer PRIMARY KEY
);
```

Trong chế độ autocommit thông thường, có thể xảy ra:

```text
Câu 1: CREATE example_one       → thành công, đã commit
Câu 2: INSERT no_such_table     → báo lỗi
Câu 3: CREATE example_two       → vẫn tiếp tục, đã commit
Kết quả: trạng thái triển khai không đầy đủ
```

Một công cụ CI không được báo thành công chỉ vì dòng cuối cùng trong script chạy xong.

## 12. `ON_ERROR_STOP`: dừng khi có lỗi

Nên truyền từ command line:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f bad_setup.sql
```

Hoặc khai báo trong script:

```text
\set ON_ERROR_STOP on
```

`ON_ERROR_STOP` là **biến đặc biệt của psql**. Nó yêu cầu psql dừng khi gặp lỗi thích hợp thay vì tiếp tục xử lý những câu sau.

**Cảnh báo quan trọng:** dừng khi lỗi **không có nghĩa hoàn tác mọi lệnh trước đó**. Nếu một câu `CREATE TABLE` đã commit trước lỗi, nó vẫn tồn tại, trừ khi có transaction bao ngoài để rollback.

Có hai mục tiêu riêng:

- **Fail fast:** ngừng ngay khi script có lỗi.
- **Atomicity:** hoặc tất cả thay đổi thuộc transaction cùng commit, hoặc không có thay đổi nào thuộc transaction được commit.

`ON_ERROR_STOP` phục vụ mục tiêu thứ nhất; cần transaction để giải quyết mục tiêu thứ hai.

## 13. Exit code: để shell/CI nhận biết thất bại

`psql` trả exit code khi chương trình kết thúc. Các mã thường dùng:

| Exit code | Ý nghĩa |
| ---: | --- |
| **0** | psql hoàn thành bình thường |
| **1** | Lỗi nghiêm trọng ở phía psql (ví dụ không đọc được file) |
| **2** | Kết nối tới server bị hỏng trong chế độ không tương tác |
| **3** | Lỗi trong script khi `ON_ERROR_STOP` được bật |

Đừng suy luận rằng một script không bật `ON_ERROR_STOP` sẽ luôn trả nonzero chỉ vì có câu SQL lỗi ở giữa.

### 13.1. Bash: kiểm tra mã thoát

```bash
#!/usr/bin/env bash

psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f setup.sql

status=$?

if [ "$status" -ne 0 ]; then
  echo "Database script failed (psql exit=$status)" >&2
  exit "$status"
fi

echo "Database script completed"
```

Phải lấy `$?` **ngay sau** lệnh psql, vì lệnh tiếp theo có thể thay đổi exit status.

### 13.2. Bash: chạy có cơ chế dừng lỗi

```bash
#!/usr/bin/env bash
set -euo pipefail

psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f setup.sql

echo "Completed"
```

`set -e` có những ngoại lệ theo ngữ cảnh shell (như điều kiện `if`); `pipefail` giúp pipeline không che mã lỗi của lệnh đứng trước. Nhưng **`set -e` không thay thế `ON_ERROR_STOP`**: shell chỉ biết psql thất bại nếu psql báo exit code phù hợp.

### 13.3. Windows PowerShell 5.1

```powershell
& psql -X -v ON_ERROR_STOP=1 `
    -h localhost -U lab_user -d lab_db `
    -f .\setup.sql

$psqlExit = $LASTEXITCODE

if ($psqlExit -ne 0) {
    Write-Error "Database script failed: psql exit $psqlExit"
    exit $psqlExit
}

Write-Host "Database script completed"
```

Trong PowerShell, `$LASTEXITCODE` là exit code của chương trình native vừa chạy. Với Windows PowerShell 5.1, không nên chỉ dựa vào `$ErrorActionPreference = 'Stop'` để xử lý mọi exit code khác 0 của chương trình native. Hãy kiểm tra `$LASTEXITCODE` rõ ràng.

Ký tự tiếp dòng trong Bash là dấu gạch chéo ngược `\`; PowerShell thường dùng **backtick**. Đừng sao chép cú pháp tiếp dòng từ Bash sang PowerShell mà không điều chỉnh.

## 14. `--single-transaction` / `-1`: nguyên tử hóa một nhóm file

Nếu các câu lệnh đều hỗ trợ chạy trong transaction, có thể sử dụng:

```bash
psql -X -v ON_ERROR_STOP=1 -1 \
  -h localhost -U lab_user -d lab_db \
  -f setup.sql
```

`-1` viết tắt của `--single-transaction`. Khi sử dụng với các tùy chọn file/command phù hợp, psql bao các câu lệnh trong một transaction. Khi `ON_ERROR_STOP` bật và có lỗi, quá trình có thể rollback thay vì commit những thay đổi trong transaction đó.

```text
START TRANSACTION
      |
      +-- SQL A: thành công
      |
      +-- SQL B: thành công
      |
      +-- SQL C: lỗi
      |
      +-- ROLLBACK
      |
      +-- psql trả nonzero cho shell
```

### 14.1. Tại sao `-1` và `ON_ERROR_STOP` nên đi cùng nhau?

Vì chúng giải quyết hai vấn đề khác nhau:

| Tùy chọn | Chức năng |
| --- | --- |
| `-v ON_ERROR_STOP=1` | Dừng script và báo lỗi |
| `-1` | Nhóm nhiều lệnh tương thích vào một transaction |
| Kết hợp | Dừng ở lỗi và rollback các thay đổi chưa commit trong transaction |

Nếu chỉ bật `ON_ERROR_STOP`, những lệnh đã được autocommit trước đó **không tự bị rollback**.

### 14.2. Những câu lệnh không thể chạy trong transaction block

Không phải mọi câu lệnh PostgreSQL đều thích hợp với `-1`:

```sql
-- Không chạy được bên trong transaction block:
CREATE DATABASE another_db;

-- Ví dụ các thao tác có hạn chế giao dịch:
VACUUM;
CREATE INDEX CONCURRENTLY idx_sample ON sample_table(id);
```

Các câu lệnh trên chỉ minh họa tính không phù hợp với transaction chung; `sample_table` là bảng giả định. Cần tách chúng thành bước triển khai riêng với quy trình kiểm soát phù hợp.

### 14.3. Không trộn `-1` với transaction control trong file tùy tiện

Nếu file tự có `BEGIN`, `COMMIT` hoặc `ROLLBACK`, chúng có thể làm hỏng ý định “toàn bộ file trong một transaction” do `-1` đặt ra. Nên chọn một nơi chịu trách nhiệm:

- Script tự quản lý transaction tường minh, **hoặc**
- Lệnh gọi `psql -1` quản lý transaction cho các file tương thích.

Một `COMMIT` ở giữa script có thể kết thúc transaction sớm, khiến bạn không còn bảo đảm rollback toàn bộ chuỗi.

### 14.4. Nhiều file trong một transaction

```bash
psql -X -v ON_ERROR_STOP=1 -1 \
  -h localhost -U lab_user -d lab_db \
  -f steps/01_schema.sql \
  -f steps/02_seed.sql \
  -f steps/03_report.sql
```

Hoặc dùng một `main.sql` có `\ir` các file con. Cả hai đều phù hợp khi muốn một phiên psql thực thi các bước theo thứ tự.

## 15. Lỗi trong transaction và `ON_ERROR_ROLLBACK`

PostgreSQL thường chuyển transaction sang trạng thái **aborted** sau một lỗi SQL, khiến các câu tiếp theo trong transaction bị từ chối cho đến khi rollback hoặc dùng savepoint đúng cách.

```sql
BEGIN;

CREATE TABLE demo_psql.error_demo (
    id integer PRIMARY KEY
);

-- Lỗi cố tình: cột không tồn tại.
INSERT INTO demo_psql.error_demo (missing_column)
VALUES (1);

-- Bị từ chối vì transaction đã lỗi.
INSERT INTO demo_psql.error_demo (id)
VALUES (2);

ROLLBACK;
```

Thông báo thường gặp:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

Cần tìm **lỗi gốc đầu tiên**, không chỉ sửa những lỗi tiếp theo do transaction đã aborted.

### 15.1. `ON_ERROR_ROLLBACK` là gì?

`psql` có biến đặc biệt:

```text
\set ON_ERROR_ROLLBACK on
```

Khi bật phù hợp, psql dùng savepoint để hỗ trợ hoàn tác **câu lệnh vừa lỗi** mà vẫn có thể tiếp tục transaction. Điều này có thể tiện khi thực hành tương tác, nhưng không nên bật để che lỗi trong migration cần all-or-nothing.

| Cơ chế | Mục đích |
| --- | --- |
| `ON_ERROR_STOP` | Dừng script khi lỗi |
| `-1` | Bao các lệnh hỗ trợ trong transaction |
| `ON_ERROR_ROLLBACK` | Dùng savepoint để tiếp tục sau một số lỗi |
| `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` | Điều khiển rollback từng phần của transaction |

Ví dụ savepoint tường minh:

```sql
BEGIN;

SAVEPOINT before_optional_step;

-- Thực hiện bước tùy chọn.
-- Nếu bước đó lỗi: ROLLBACK TO SAVEPOINT before_optional_step;

COMMIT;
```

Các comment trên là **mô tả quyết định**, không phải xử lý lỗi tự động. Khi cần rẽ nhánh theo lỗi, hãy dùng điều phối ứng dụng, SQL/PLpgSQL hoặc workflow có xử lý lỗi cụ thể.

## 16. Bộ script hoàn chỉnh: schema + seed + report

Cấu trúc đề xuất:

```text
sql/
├── main.sql
└── steps/
    ├── 01_schema.sql
    ├── 02_seed.sql
    └── 03_report.sql
```

### 16.1. `sql/main.sql`

```sql
\set ON_ERROR_STOP on

\echo ---------------------------------
\echo Starting PostgreSQL lab
\echo Schema: :target_schema
\echo ---------------------------------

\ir steps/01_schema.sql
\ir steps/02_seed.sql
\ir steps/03_report.sql

\echo Finished successfully
```

### 16.2. `sql/steps/01_schema.sql`

```sql
CREATE SCHEMA IF NOT EXISTS :"target_schema";

CREATE TABLE IF NOT EXISTS :"target_schema".orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

### 16.3. `sql/steps/02_seed.sql`

```sql
INSERT INTO :"target_schema".orders
    (order_id, customer_name, amount)
VALUES
    (1, 'Nguyễn An', 120000.00),
    (2, 'Trần Bình', 250000.00),
    (3, 'Lê Chi', 80000.00)
ON CONFLICT (order_id) DO UPDATE
SET customer_name = EXCLUDED.customer_name,
    amount = EXCLUDED.amount;
```

### 16.4. `sql/steps/03_report.sql`

```sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(amount), 0)::numeric AS total_amount
FROM :"target_schema".orders
\gset

\echo Orders: :order_count
\echo Total amount: :total_amount

SELECT order_id, customer_name, amount
FROM :"target_schema".orders
WHERE amount >= :'min_amount'::numeric
ORDER BY amount DESC, order_id;
```

### 16.5. Chạy toàn bộ bằng một lệnh

```bash
psql -X -v ON_ERROR_STOP=1 -1 \
  -v target_schema=lab_row45 \
  -v min_amount=100000 \
  -h localhost -U lab_user -d lab_db \
  -f sql/main.sql
```

Kết quả minh họa:

```text
Schema: lab_row45
Orders: 3
Total amount: 450000.00
```

Báo cáo sẽ chứa hai đơn với số tiền từ 100000 trở lên.

Từ ví dụ có thể thấy:

1. `-v` truyền tham số cho mọi file trong cùng phiên.
2. `\ir` tổ chức file con không phụ thuộc working directory.
3. `:"target_schema"` quote tên schema đúng cách.
4. `:'min_amount'::numeric` đưa giá trị thành literal được ép kiểu.
5. `\gset` chuyển kết quả SQL thành biến psql.
6. `ON_ERROR_STOP` dừng nếu lỗi; `-1` quản lý transaction chung khi các lệnh tương thích.

### 16.6. Thử lỗi có chủ đích

Trong **môi trường thực hành**, thêm tạm lệnh sau vào cuối `02_seed.sql`:

```sql
INSERT INTO :"target_schema".orders
    (order_id, customer_name, amount)
VALUES (999, 'Invalid', -10.00);
```

Ràng buộc `CHECK (amount >= 0)` làm lệnh thất bại. Khi chạy với `-v ON_ERROR_STOP=1 -1`, psql dừng, trả lỗi và rollback các thay đổi thuộc transaction của lượt chạy đó.

Không thử trên schema có dữ liệu thật, và không để lại câu lỗi chủ đích trong một script triển khai production.

## 17. In output và chẩn đoán lỗi

### 17.1. `\echo` và `\timing`

In thông báo:

```text
\echo Starting script
\echo Target schema: :target_schema
```

Đo thời gian các câu lệnh trong psql:

```text
\timing on
```

`\timing` tiện khi thử nghiệm nhưng không tự thay thế một phép benchmark có kiểm soát cache, tải và nhiều lần đo.

### 17.2. Hiển thị SQL khi lỗi

Ví dụ:

```bash
psql -X -v ON_ERROR_STOP=1 --echo-errors \
  -h localhost -U lab_user -d lab_db \
  -f sql/main.sql
```

`--echo-errors` giúp hiển thị câu lệnh liên quan tới thông báo lỗi. `-e` hoặc `--echo-queries` có thể in những câu SQL được gửi cho server.

**Cảnh báo:** SQL text có thể chứa literal nhạy cảm; không tự bật echo mọi SQL trong log production nếu chúng chứa dữ liệu bí mật.

### 17.3. Tắt pager trong automation

```bash
psql -X -P pager=off -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f sql/main.sql
```

`-P pager=off` giúp giảm khả năng output cần tương tác với pager trong môi trường script. Nó không thay đổi SQL hay dữ liệu trong database.

### 17.4. Redirect output, giữ exit code

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f sql/main.sql \
  > sql-out.log 2> sql-err.log

status=$?
if [ "$status" -ne 0 ]; then
  echo "Failed: $status" >&2
  exit "$status"
fi
```

Với pipeline như `psql ... | tee sql.log`, Bash thông thường có thể trả exit code của `tee` thay vì `psql`. Dùng `set -o pipefail` hoặc kiểm tra `PIPESTATUS[0]` ngay sau pipeline. Không để một lệnh in log thành công che mất lỗi thật của psql.

## 18. Credentials, kết nối và bảo mật trong script

### 18.1. Không nhúng password thật vào file SQL hay lệnh

Đừng lưu mật khẩu database trong repository, file script, URL log hoặc tham số dòng lệnh. Khi automation cần xác thực, dùng cơ chế secret management của nền tảng hoặc password file được cấp phát có kiểm soát.

Trên Unix, libpq thường tìm password file:

```text
~/.pgpass
```

Một dòng có cấu trúc:

```text
hostname:port:database:username:password
```

Ví dụ chỉ minh họa định dạng, **không phải credential thật**:

```text
db.example.internal:5432:lab_db:lab_user:REPLACE_WITH_SECRET
```

File phải có quyền truy cập hạn chế; trên Unix thường yêu cầu quyền tương đương `0600`. Trên Windows, password file mặc định thường ở `%APPDATA%\postgresql\pgpass.conf`. Có thể dùng `PGPASSFILE` để trỏ đến file được cấp bởi secret manager.

### 18.2. Tránh prompt chặn CI

Dùng `-w` / `--no-password`:

```bash
psql -X -w -v ON_ERROR_STOP=1 \
  -h db.example.internal -U lab_user -d lab_db \
  -f sql/main.sql
```

`-w` **không bỏ qua xác thực**. Nó chỉ yêu cầu không hỏi password tương tác; nếu server cần password mà client không tìm được từ nguồn phù hợp, kết nối thất bại thay vì làm pipeline đứng chờ.

### 18.3. TLS khi kết nối từ xa

Ví dụ libpq connection string có kiểm tra certificate và hostname:

```bash
psql -X -w -v ON_ERROR_STOP=1 \
  "host=db.example.internal port=5432 dbname=lab_db user=lab_user sslmode=verify-full sslrootcert=/etc/postgresql/root.crt" \
  -f sql/main.sql
```

`sslmode=verify-full` yêu cầu TLS và kiểm tra danh tính server theo chuỗi tin cậy/hostname. File CA và endpoint phải phù hợp môi trường thực. Đối với các hệ thống có proxy, cần xác định TLS được thiết lập ở chặng nào.

### 18.4. `-X` để giảm khác biệt giữa máy cá nhân và CI

`psql` có thể nạp cấu hình cá nhân `psqlrc` lúc khởi động. Điều đó tiện khi thao tác tương tác, nhưng có thể khiến script batch chạy khác nhau trên các máy. `-X` / `--no-psqlrc` bỏ qua cấu hình cá nhân, góp phần làm kết quả dễ tái lập.

## 19. Phân loại lỗi để xử lý đúng nguyên nhân

| Loại lỗi | Ví dụ | Cách tiếp cận |
| --- | --- | --- |
| File/working directory | Không tìm thấy `main.sql` hoặc file con | Kiểm tra đường dẫn `-f`, `\i`, `\ir` |
| Kết nối | Sai host, port, credential hoặc TLS | Kiểm tra libpq settings, mạng và quyền |
| Cú pháp SQL | Sai tên cột, thiếu ngoặc | Xem dòng gây lỗi, sửa SQL |
| Biến psql | Thiếu biến hoặc dùng literal thay vì identifier | Dùng `-v`, `:'var'`, `:"var"` |
| Quyền | Không được tạo schema/bảng | Dùng đúng tài khoản và cấp quyền tối thiểu |
| Ràng buộc | Trùng PK, sai FK, CHECK bị vi phạm | Sửa dữ liệu hoặc logic nhập |
| Giao dịch | Transaction aborted, lệnh không cho phép trong transaction | Kiểm tra lỗi gốc, rollback, phân tách file |
| Logic nghiệp vụ | Script chạy được nhưng chọn nhầm schema | Kiểm tra đích và yêu cầu triển khai |

### 19.1. File không tồn tại

Ví dụ thông báo:

```text
psql: error: setup.sql: No such file or directory
```

Kiểm tra:

- File thực sự tồn tại.
- Thư mục làm việc khi gọi `-f`.
- `\ir` được dùng khi cần đường dẫn tương đối với script.
- Đường dẫn có khoảng trắng cần quote đúng cú pháp shell.

### 19.2. Biến chưa quote đúng

```sql
-- Không phù hợp với tên schema có ký tự đặc biệt.
CREATE SCHEMA :target_schema;

-- Đúng: quote biến thành identifier.
CREATE SCHEMA :"target_schema";
```

Với string literal:

```sql
-- Sai ý tưởng:
SELECT ':customer_name';

-- Đúng:
SELECT :'customer_name';
```

### 19.3. Lỗi bảng không tồn tại

```text
ERROR: relation "demo_batch.orders" does not exist
```

Kiểm tra database/schema đang kết nối:

```sql
SELECT current_database(), current_user, current_schema();

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name = 'orders'
ORDER BY table_schema;
```

Có thể script tạo schema chưa chạy, target_schema truyền sai hoặc người dùng chọn nhầm database.

### 19.4. Lỗi transaction aborted

Thông báo:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

Lỗi này thường xuất hiện **sau** một câu SQL đã lỗi trước đó. Hãy tìm lỗi đầu tiên, không chỉ chăm chăm sửa câu bị từ chối tiếp theo.

### 19.5. Phân biệt “script chạy xong” với “đúng nghiệp vụ”

Một script có thể trả exit 0 nhưng xóa nhầm hàng do thiếu `WHERE`, hoặc tạo đối tượng ở schema khác. `ON_ERROR_STOP` không nhận biết các sai lầm về ý định nghiệp vụ khi SQL vẫn hợp lệ.

Với thao tác quan trọng, cần đối chiếu host, database, schema, số hàng dự kiến, quyền truy cập và có kế hoạch backup/rollback phù hợp.

## 20. Mẫu automation bằng Bash

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:?PGHOST is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGUSER:?PGUSER is required}"
: "${TARGET_SCHEMA:?TARGET_SCHEMA is required}"

psql \
  -X \
  -w \
  -v ON_ERROR_STOP=1 \
  -1 \
  -v target_schema="$TARGET_SCHEMA" \
  -v min_amount=100000 \
  -h "$PGHOST" \
  -U "$PGUSER" \
  -d "$PGDATABASE" \
  -f sql/main.sql

echo "SQL script completed successfully"
```

Đây là mẫu chạy qua shell; nó yêu cầu bốn biến cấu hình không được rỗng. Password phải được cung cấp qua secret manager/password file phù hợp, không in ra output.

Với automation production:

- Giữ SQL trong version control, nhưng không commit secrets.
- Không chọn tên schema/database chỉ từ một input không được kiểm soát.
- Kiểm tra môi trường mục tiêu trước khi triển khai.
- Dùng `ON_ERROR_STOP` và kiểm tra exit code.
- Dùng transaction chung **chỉ khi mọi câu lệnh tương thích**.
- Có kế hoạch chạy lại hoặc hoàn nguyên sau lỗi.
- Không bỏ qua quyền và cấu hình TLS chỉ để vượt qua lỗi kết nối.

### Idempotency cần được hiểu đúng

`CREATE TABLE IF NOT EXISTS` không xác minh bảng đã có đúng cấu trúc. `ON CONFLICT DO UPDATE` có thể ghi đè dữ liệu hợp lệ nếu dùng sai. Vì vậy:

- “Chạy lại không lỗi” không đồng nghĩa với “kết quả chính xác”.
- “Chạy trong transaction” không đồng nghĩa với “không thể tác động nhầm schema”.
- Với migration production, nên có hệ thống theo dõi **phiên bản migration**, trạng thái áp dụng và quy trình kiểm tra riêng.

## 21. Một số lệnh psql nâng cao cần cẩn trọng

### 21.1. `\gexec`

`\gexec` có thể thực thi các câu SQL được **sinh ra từ kết quả một truy vấn**. Điều này hữu ích cho những tác vụ quản trị có kiểm soát, nhưng rất nguy hiểm nếu truy vấn sinh lệnh từ dữ liệu người dùng hoặc ghép tên đối tượng không quote đúng.

Không dùng `\gexec` để chạy hàng loạt `DROP` hoặc thay đổi quyền trên production mà thiếu quy trình phê duyệt và kiểm tra tập đối tượng.

### 21.2. `\copy` và `COPY`

`\copy` là meta-command client-side của psql, thường dùng để đọc/ghi CSV trên máy chạy client. `COPY` là lệnh SQL của PostgreSQL server; những biến thể đọc/ghi file ở server có yêu cầu quyền và đường dẫn khác.

Không mặc định rằng `\copy './file.csv'` và `COPY ... FROM '/path/file.csv'` truy cập cùng hệ thống file.

### 21.3. File backup plain SQL và định dạng khác

Một bản backup dạng **plain SQL** từ `pg_dump` có thể được phục hồi bằng `psql` theo quy trình phù hợp. Nhưng bản backup định dạng custom/tar/directory cần công cụ như `pg_restore`. Không gửi file backup nhị phân vào `psql -f` như một script SQL văn bản.

### 21.4. Encoding của script

Nên lưu file SQL bằng **UTF-8**, nhất là khi có tiếng Việt. Kiểm tra:

```sql
SHOW client_encoding;
```

Trong psql:

```text
\encoding UTF8
```

Nếu file có encoding khác hoặc được tạo bởi công cụ dùng BOM không mong muốn, quá trình thực thi có thể phát sinh lỗi. Nên thống nhất quy ước UTF-8 giữa repository và pipeline.

## 22. Bài tập tự kiểm tra

### Bài 1: Chạy `setup.sql`, dừng ngay khi lỗi

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f setup.sql
```

**Giải thích:** `ON_ERROR_STOP` giúp báo thất bại khi script có lỗi. Nếu muốn atomicity và tất cả câu lệnh hỗ trợ transaction, có thể cân nhắc `-1`.

### Bài 2: Phân biệt `\i` và `\ir`

File `project/sql/main.sql` chứa `\ir steps/01.sql`. Chạy từ một thư mục terminal khác thì file nào được include?

**Đáp án:** `project/sql/steps/01.sql`. `\ir` dựa vào vị trí file đang chạy, còn `\i` dựa vào thư mục làm việc của psql.

### Bài 3: Truyền tên bảng qua biến psql

```sql
CREATE TABLE :"target_schema".events (
    event_id bigint PRIMARY KEY,
    description text NOT NULL
);
```

**Giải thích:** `:"target_schema"` quote biến như identifier. Biến cần được đặt bằng `-v target_schema=...` hoặc `\set`.

### Bài 4: Truyền giá trị text trong WHERE

```sql
SELECT *
FROM demo_batch.orders
WHERE customer_name = :'customer_name';
```

**Giải thích:** `:'customer_name'` tạo string literal. Không viết `WHERE customer_name = ':customer_name'`.

### Bài 5: Script lỗi ở câu thứ hai nhưng câu thứ ba vẫn chạy

**Hỏi:** nguyên nhân và cách sửa?

**Đáp án:** `ON_ERROR_STOP` chưa bật, hoặc script không được xử lý theo ý định. Dùng `-v ON_ERROR_STOP=1` và kiểm tra mã thoát từ `psql`; nếu cần tất cả bước cùng thành công hoặc cùng rollback, dùng transaction phù hợp.

### Bài 6: `ON_ERROR_STOP` có tự rollback lệnh trước đó không?

**Đáp án:** không. Nó chỉ yêu cầu dừng. Các lệnh đã autocommit trước đó vẫn tồn tại. Cần transaction bao ngoài như `-1` cho nhóm lệnh được hỗ trợ.

### Bài 7: Dùng `-1` với `CREATE DATABASE` được không?

**Đáp án:** không, vì `CREATE DATABASE` không được phép chạy trong transaction block. Phải chạy nó ở bước riêng ngoài transaction.

### Bài 8: Cách kiểm tra exit code trong PowerShell

**Đáp án:** lấy `$LASTEXITCODE` ngay sau khi gọi `psql` và báo lỗi/`exit` nếu khác 0. Không chỉ dựa vào việc PowerShell không in lỗi đỏ.

### Bài 9: Lấy số hàng từ SELECT sang biến psql

```sql
SELECT COUNT(*) AS order_count
FROM demo_batch.orders
\gset

\echo Orders: :order_count
```

**Giải thích:** `\gset` gán giá trị từ đúng một hàng kết quả vào biến `order_count`.

### Bài 10: Dùng `\if` với kết quả SQL

```sql
SELECT CASE WHEN COUNT(*) > 0 THEN 'true' ELSE 'false' END AS has_rows
FROM demo_batch.orders
\gset

\if :has_rows
  \echo Data exists
\else
  \echo No data
\endif
```

**Giải thích:** SQL tính biểu thức, psql dùng biến boolean để chọn nhánh; `\if` không tự phân tích toán tử so sánh SQL tùy ý.

## 23. Ghi nhớ

- **`psql -f file.sql`** là cách chuẩn để thực thi file SQL từ terminal; **`\i`** và **`\ir`** giúp include file bên trong psql. Dùng `\ir` cho các file con trong bộ script nhiều thư mục.
- **`-v name=value`** và **`\set`** định nghĩa biến ở phía psql, không phải tham số SQL bind của server.
- **`:'name'`** quote thành literal, **`:"name"`** quote thành identifier, còn **`:name`** chèn nội dung thô. Quote sai có thể gây lỗi hoặc tạo SQL ngoài ý muốn.
- **`\gset`** chuyển một hàng kết quả SQL thành biến; **`\if`** giúp rẽ nhánh theo boolean được psql hiểu.
- Với automation, dùng **`-X -v ON_ERROR_STOP=1`**, kiểm tra **exit code** và không để pipeline che lỗi SQL.
- **`ON_ERROR_STOP` không đồng nghĩa với transaction.** Dùng **`-1`** khi cần all-or-nothing và mọi lệnh được phép chạy trong transaction block.
- **Không phải mọi câu SQL đều chạy được với `-1`**, ví dụ `CREATE DATABASE` hoặc `CREATE INDEX CONCURRENTLY`.
- Tránh lưu mật khẩu trong script/dòng lệnh/log. Dùng secret manager hoặc password file, tắt password prompt với `-w` khi automation yêu cầu.
- Trước thay đổi quan trọng, kiểm tra đúng host, database, schema, dữ liệu và quyền, đồng thời chuẩn bị phương án rollback.
- Một script đáng tin cậy phải **chạy đúng việc, báo lỗi rõ, dừng đúng lúc và không để lại trạng thái ngoài ý muốn**.

Khi sử dụng `psql` cho PostgreSQL, hãy coi việc thực thi tệp SQL, thay thế biến và quản lý lỗi là **một quy trình có hợp đồng rõ ràng với hệ thống gọi**: thành công phải có exit code thành công; thất bại phải có tín hiệu thất bại; và những thay đổi cần đi cùng chính sách giao dịch phù hợp.
