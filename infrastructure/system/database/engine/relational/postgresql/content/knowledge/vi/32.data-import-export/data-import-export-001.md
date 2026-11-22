# COPY phía máy chủ và \copy phía máy khách trong PostgreSQL

Khi cần nhập vài trăm nghìn bản ghi sản phẩm từ CSV hoặc xuất hàng triệu dòng báo cáo, chạy từng câu `INSERT` hay `SELECT` rồi tự ghi file thường vừa chậm vừa khó kiểm soát. PostgreSQL cung cấp lệnh SQL **`COPY`** để truyền dữ liệu theo lô giữa bảng/truy vấn và file hoặc luồng dữ liệu. Công cụ dòng lệnh **`psql`** cung cấp meta-command **`\copy`** để việc đọc/ghi file diễn ra ở **máy đang chạy psql**, không nhất thiết là máy chạy PostgreSQL.

Hai cách nhìn giống nhau về cú pháp, nhưng khác nhau rất lớn về **nơi mở file, quyền cần có, bảo mật và cách triển khai**.

~~~text
                A. COPY FROM '/server/path/products.csv'

Máy chạy psql / Java                      Máy PostgreSQL
┌─────────────────┐                      ┌──────────────────────┐
│ Client          │   SQL COPY --------> │ PostgreSQL backend   │
│                 │                      │    │                 │
└─────────────────┘                      │    v                 │
                                       │ /server/path/...     │
                                       │ (FILE Ở SERVER)      │
                                       └──────────────────────┘


                B. \copy FROM '/client/path/products.csv'

Máy chạy psql                             Máy PostgreSQL
┌──────────────────────┐                  ┌─────────────────────┐
│ psql                 │                  │ PostgreSQL backend  │
│    │                 │    COPY FROM     │                     │
│    v                 │    STDIN         │                     │
│ /client/path/...     │ ===============> │ bảng đích           │
│ (FILE Ở CLIENT)      │   qua kết nối    │                     │
└──────────────────────┘                  └─────────────────────┘
~~~

Ví dụ minh họa:

~~~sql
-- Đây là SQL chạy trên PostgreSQL server.
COPY public.products (sku, name, price)
FROM '/var/lib/postgresql/import/products.csv'
WITH (FORMAT csv, HEADER true);
~~~

~~~text
-- Đây là meta-command của psql, không phải SQL chuẩn.
\copy public.products (sku, name, price) FROM '/home/dev/import/products.csv' WITH (FORMAT csv, HEADER true)
~~~

**Nguyên tắc cốt lõi:** `COPY ... FROM '/path'` yêu cầu **PostgreSQL server mở file**, còn `\copy ... FROM '/path'` yêu cầu **psql client mở file** và truyền nội dung cho server qua `COPY FROM STDIN`. Chọn sai cách có thể gây lỗi “file not found” dù file tồn tại, hoặc khiến ứng dụng bị đòi quyền server file nguy hiểm.

Bài này là một tài liệu tự chứa thuộc chương **Nhập xuất dữ liệu** của module *Database Engine Relational PostgreSQL*, bao gồm vị trí dữ liệu, quyền, cú pháp nhập/xuất, CSV/TEXT/BINARY, `STDIN/STDOUT`, xử lý `NULL`, bảng staging, giao dịch, ứng dụng JDBC, bảo mật và bài tập có đáp án.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác **`COPY` là SQL server-side** và **`\copy` là lệnh riêng của psql client**.
2. Dự đoán máy nào sẽ đọc/ghi file trong từng ví dụ, kể cả khi client chạy trên container hoặc máy từ xa.
3. Dùng `COPY FROM` và `COPY TO` đúng với bảng, danh sách cột và truy vấn `SELECT`.
4. Dùng `COPY FROM STDIN`/`TO STDOUT` để truyền qua một kết nối mà không yêu cầu server truy cập path ngoài.
5. Dùng `\copy ... FROM/TO 'file.csv' WITH (FORMAT csv, HEADER true)` cho file ở máy khách.
6. Phân biệt quyền `SELECT/INSERT` trên bảng với các quyền đọc/ghi/chạy chương trình trên server.
7. Biết khi nào cần `pg_read_server_files`, `pg_write_server_files`, `pg_execute_server_program` hoặc superuser, và vì sao chúng nhạy cảm.
8. Nhận biết sự khác nhau giữa `FORMAT text`, `FORMAT csv` và `FORMAT binary`.
9. Kiểm soát `DELIMITER`, `HEADER`, `QUOTE`, `ESCAPE`, `NULL` và danh sách cột.
10. Hiểu khác biệt **SQL NULL**, chuỗi rỗng và literal `NULL` khi làm việc với CSV.
11. Thiết kế import pipeline **file → staging → validation → bảng đích** mà không âm thầm bỏ hàng lỗi.
12. Dùng transaction và rollback để tránh kết quả nhập một phần ngoài ý muốn.
13. Hiểu tác động của `COPY` tới trigger, constraint, identity, index, WAL, autovacuum và locking.
14. Biết cách nhập/xuất qua PGJDBC `CopyManager` mà không chạy `\copy` như SQL.
15. Chẩn đoán lỗi đường dẫn, permission, encoding, CSV malformed, sai kiểu dữ liệu và khóa.
16. Theo dõi tiến độ bằng `pg_stat_progress_copy` khi phiên bản PostgreSQL hỗ trợ.
17. Chọn `COPY`, `\copy`, JDBC batch, ETL hoặc `pg_dump/pg_restore` theo mục tiêu.

## 2. COPY và \copy: cùng mục tiêu, khác nơi chạy

### 2.1. COPY là lệnh SQL PostgreSQL

~~~sql
COPY schema.table_name
FROM '/absolute/path/on/database/server/file.csv'
WITH (FORMAT csv, HEADER true);
~~~

SQL được gửi tới PostgreSQL. Khi nguồn là **tên file**, tiến trình PostgreSQL ở server tìm file trên **hệ thống file mà backend có thể thấy** và mở file bằng quyền hệ điều hành của tài khoản dịch vụ.

### 2.2. \copy là psql meta-command

~~~text
\copy schema.table_name FROM '/path/on/psql/client/file.csv' WITH (FORMAT csv, HEADER true)
~~~

Dấu `\` là ký hiệu lệnh meta của `psql`. PostgreSQL server không hiểu cú pháp `\copy` nếu gửi nó qua JDBC hoặc công cụ chỉ gửi SQL.

### 2.3. Psql làm gì phía sau?

Với `\copy ... FROM '/path'`, psql mở file phía client và trao nội dung với server qua cơ chế **`COPY ... FROM STDIN`**. Với `\copy ... TO '/path'`, nó đọc luồng **`COPY ... TO STDOUT`** rồi ghi vào file phía client.

### 2.4. Vai trò của kết nối

Với `\copy`, dữ liệu đi qua kết nối client–server. Nếu kết nối dùng TLS, luồng COPY được bảo vệ bởi TLS trên hop tương ứng; tuy nhiên file trên client vẫn cần chính sách bảo vệ riêng.

### 2.5. Không có “\copy bên trong PostgreSQL”

`\copy` chỉ tồn tại trong những client triển khai meta-command tương ứng, phổ biến là `psql`. Không viết `\copy` vào SQL function, view, trigger hoặc `PreparedStatement` của JDBC.

## 3. Bảng so sánh nhanh

| Tiêu chí | SQL `COPY` với file path | `psql \copy` với file path |
| --- | --- | --- |
| Ai mở file? | PostgreSQL backend trên server | Tiến trình psql trên client |
| Path nằm ở đâu? | File system của server/container chạy DB | File system của host/container chạy psql |
| Quyền hệ điều hành | Tài khoản dịch vụ PostgreSQL | Tài khoản chạy psql |
| Quyền đọc file đặc biệt ở DB | Có, khi dùng server file/PROGRAM | Không cần chỉ vì mở file client |
| Quyền bảng vẫn cần? | Có | Có |
| Dữ liệu đi qua client–server? | Lệnh SQL; file được DB mở trực tiếp | Có, qua STDIN/STDOUT |
| Có chạy trong JDBC như SQL? | Có với server-file COPY nếu đủ quyền; STDIN/STDOUT cần protocol API | Không |
| Hữu ích khi file nằm laptop | Thường không | Rất phù hợp |
| Hữu ích khi file nằm server DB | Phù hợp nếu được cho phép | Chỉ nếu psql cũng thấy file đó |
| Khả năng vận hành cloud DB | Thường hạn chế quyền server file | Thường dễ dùng hơn |
| Rủi ro quyền file | Quyền trên DB server rất nhạy cảm | Rủi ro file/command nằm phía client |
| Hướng import phổ biến | `COPY FROM file` | `\copy FROM file` |
| Hướng export phổ biến | `COPY TO file` | `\copy TO file` |

**Lưu ý:** SQL `COPY ... FROM STDIN`/**`TO STDOUT`** không mở server file, vì vậy không cần các quyền server-file tương ứng chỉ để dùng luồng. Đây là cơ chế cốt lõi để client libraries như PGJDBC stream dữ liệu.

## 4. Một ví dụ vị trí file dễ nhầm

Giả sử:

~~~text
Laptop cá nhân:
  /home/an/data/products.csv

Máy PostgreSQL:
  /var/lib/postgresql/data/
  không có /home/an/data/products.csv
~~~

Bạn kết nối từ laptop:

~~~bash
psql "host=db.example.internal dbname=shop user=importer sslmode=verify-full"
~~~

và chạy:

~~~sql
COPY public.products
FROM '/home/an/data/products.csv'
WITH (FORMAT csv, HEADER true);
~~~

Server sẽ thử mở `/home/an/data/products.csv` **trên máy database**, không phải laptop. Lỗi “could not open file” không chứng minh file laptop mất; đơn giản là **đường dẫn được nhìn từ máy khác**.

Sửa bằng:

~~~text
\copy public.products FROM '/home/an/data/products.csv' WITH (FORMAT csv, HEADER true)
~~~

nếu tài khoản chạy psql có quyền đọc file và database role có quyền `INSERT` vào bảng.

## 5. Quy trình học với một file CSV

Ta sẽ tạo schema lab và nhập file:

~~~csv
sku,product_name,unit_price_text,stock_text
KB-01,"Bàn phím, cơ",850000.00,8
MS-02,"Chuột ""siêu nhẹ""",299000.00,15
HM-03,Tai nghe,620000.50,3
~~~

Trong đó:

- Cột `product_name` của hàng đầu chứa **dấu phẩy** nên cần bao trong dấu nháy kép.
- Tên chuột chứa ký tự nháy kép; theo CSV mặc định, ký tự `"` nằm trong giá trị được thể hiện bằng `""`.
- Dữ liệu có tiếng Việt nên phải thống nhất mã hóa.
- Ta nhập các cột số ban đầu vào **text columns** để có thể kiểm tra lỗi dữ liệu trước khi ép kiểu.

### 5.1. Mục tiêu sau xử lý

| SKU | Tên sản phẩm | Giá | Tồn kho |
| --- | --- | ---: | ---: |
| KB-01 | Bàn phím, cơ | 850000.00 | 8 |
| MS-02 | Chuột "siêu nhẹ" | 299000.00 | 15 |
| HM-03 | Tai nghe | 620000.50 | 3 |

### 5.2. Dùng staging thay vì chèn thẳng

~~~text
products.csv
     |
     v
\copy FROM local file
     |
     v
import_lab.product_stage (text thô)
     |
     +--- kiểm tra cột thiếu/rỗng
     +--- kiểm tra định dạng và miền giá trị
     +--- phát hiện SKU trùng
     +--- chuẩn hóa
     |
     v
INSERT ... SELECT ... ON CONFLICT
     |
     v
import_lab.products (dữ liệu chuẩn)
~~~

Với file có chất lượng chưa chắc chắn, staging cho phép báo cáo **lỗi đầu vào cụ thể** thay vì chỉ nhận một exception kiểu “invalid input syntax” ở dòng nào đó của một lệnh import dài.

## 6. Tạo schema và bảng lab

Thực thi trên database thử nghiệm:

~~~sql
CREATE SCHEMA import_lab;

CREATE TABLE import_lab.product_stage (
    stage_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text,
    product_name text,
    unit_price_text text,
    stock_text text,
    imported_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE import_lab.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    product_name text NOT NULL,
    unit_price numeric(14,2) NOT NULL
        CHECK (unit_price >= 0),
    stock integer NOT NULL
        CHECK (stock >= 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 6.1. Vì sao staging dùng text?

Nếu file có `unit_price_text='not-a-number'` hoặc `stock_text='five'`, nhập vào cột text không lập tức bị từ chối bởi cast numeric/integer. Ta có thể chạy truy vấn kiểm tra và báo hàng lỗi.

### 6.2. Vì sao stage_id tự sinh?

`stage_id` định danh hàng staging để dễ điều tra lỗi. Ta **không** đưa `stage_id` vào CSV hay danh sách cột của COPY, để identity được tạo tự động.

### 6.3. Vì sao bảng đích có CHECK và UNIQUE?

`COPY` không thay thế constraints. Dữ liệu cuối cần được database bảo vệ ngay cả khi có một ứng dụng khác viết trực tiếp vào bảng.

### 6.4. Môi trường lab cần tách biệt

Các thao tác như `TRUNCATE` hoặc import lại bên dưới chỉ dành cho schema thử nghiệm. Đừng dùng tên `products` production hoặc `DROP ... CASCADE` chỉ để chạy ví dụ.

## 7. Tạo CSV trên máy chạy psql

Lưu nội dung sau vào một tệp, ví dụ `/home/dev/import/products.csv` trên máy Linux/macOS đang chạy `psql`:

~~~csv
sku,product_name,unit_price_text,stock_text
KB-01,"Bàn phím, cơ",850000.00,8
MS-02,"Chuột ""siêu nhẹ""",299000.00,15
HM-03,Tai nghe,620000.50,3
~~~

### 7.1. File cần là UTF-8

Đặt file dưới UTF-8, thống nhất với `client_encoding` khi kết nối. Không chỉ nhìn “có dấu tiếng Việt” trên editor rồi khẳng định byte encoding đúng.

### 7.2. Chú ý vị trí file trong container

Nếu chạy:

~~~bash
docker exec -it postgres psql -U postgres -d labdb
~~~

thì `psql` **chạy bên trong container**. `\copy FROM '/home/dev/import/products.csv'` lúc đó tìm file trong filesystem container, không phải laptop host.

### 7.3. Nếu psql chạy trực tiếp trên laptop

~~~bash
psql "host=localhost port=5432 dbname=labdb user=lab_user"
~~~

thì `\copy` nhìn thấy file laptop, dù PostgreSQL server nằm trong container.

### 7.4. Windows

Với psql chạy trên Windows, dùng đường dẫn client phù hợp, ví dụ `C:/Data/products.csv`. Không dùng path Unix trong ví dụ Linux rồi kỳ vọng Windows nhìn thấy. Với PowerShell/cmd, quoting của **shell** và parsing của **psql meta-command** là hai lớp khác nhau.

## 8. Nhập CSV bằng \copy phía máy khách

Trong phiên `psql` kết nối đúng database:

~~~text
\copy import_lab.product_stage (sku, product_name, unit_price_text, stock_text) FROM '/home/dev/import/products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
~~~

### 8.1. Đây là một dòng lệnh psql

`\copy` là meta-command của `psql` và có quy tắc parsing riêng. Với lệnh cơ bản, nên viết cả câu `\copy` trên **một dòng** trong script psql để tránh lỗi ghép nhiều dòng không giống SQL thông thường.

### 8.2. Điều kiện để thành công

- File tồn tại **trên máy chạy psql**.
- User hệ điều hành chạy psql được phép đọc file.
- PostgreSQL role có quyền `INSERT` trên bảng/cột tương ứng.
- File thực sự là CSV và các cột khớp danh sách.
- Mã hóa và dữ liệu phù hợp thiết lập.

### 8.3. Điều kiện quyền table vẫn giữ nguyên

`\copy` không “vượt” phân quyền SQL. Nếu database role thiếu `INSERT`, import thất bại dù file local đọc được.

### 8.4. Vì sao chỉ định danh sách cột?

Bảng staging có `stage_id` và `imported_at`, nhưng file chỉ chứa bốn cột. Danh sách:

~~~sql
(sku, product_name, unit_price_text, stock_text)
~~~

đảm bảo `COPY` không cố đẩy `sku` vào cột `stage_id` do vị trí cột bảng khác file.

### 8.5. Kiểm tra hàng đã nhập

~~~sql
SELECT stage_id, sku, product_name,
       unit_price_text, stock_text
FROM import_lab.product_stage
ORDER BY stage_id;
~~~

Kỳ vọng có ba hàng với nội dung được giải mã đúng, không còn dấu quote bao CSV trong các giá trị.

## 9. Nhập bằng COPY phía server

Nếu file thực sự đã được đặt **trên database server** tại `/var/lib/postgresql/import/products.csv`:

~~~sql
COPY import_lab.product_stage (
    sku,
    product_name,
    unit_price_text,
    stock_text
)
FROM '/var/lib/postgresql/import/products.csv'
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
~~~

### 9.1. Server phải nhìn được file

File có thể nằm trên volume mount của PostgreSQL container, thư mục server host hoặc network filesystem mà backend nhìn thấy. Tệp chỉ nằm ở laptop client thì câu SQL này không đọc được.

### 9.2. User hệ điều hành khác database role

PostgreSQL backend mở file bằng quyền tài khoản dịch vụ của tiến trình database. `chmod`/ACL trên hệ điều hành khác với `GRANT INSERT` trong PostgreSQL.

### 9.3. Cần quyền server-file phù hợp

SQL `COPY FROM '/server/file'` chỉ được phép với superuser hoặc những role có quyền như `pg_read_server_files` theo phiên bản/quy tắc PostgreSQL. Những quyền này rất nhạy cảm, không nên cấp cho tài khoản ứng dụng thông thường.

### 9.4. Đường dẫn tuyệt đối

Với `COPY FROM` server file, PostgreSQL đòi đường dẫn tuyệt đối cho filename. Đừng dùng đường tương đối như `'products.csv'` và hy vọng file được tìm trong thư mục làm việc hiện tại của laptop.

### 9.5. Cách chọn thực tế

Trong nhiều môi trường managed PostgreSQL, không có quyền đọc file tùy ý trên server. `\copy` hoặc ứng dụng dùng `COPY FROM STDIN` thường là giải pháp phù hợp hơn.

## 10. COPY TO: xuất file phía server

~~~sql
COPY import_lab.products (
    sku, product_name, unit_price, stock
)
TO '/var/lib/postgresql/export/products.csv'
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
~~~

### 10.1. File xuất nằm trên server

File được tạo bởi PostgreSQL backend tại path server; nó **không tự xuất hiện trên laptop** đang gửi SQL.

### 10.2. Quyền ghi server file

Server-file `COPY TO` đòi đặc quyền như `pg_write_server_files` hoặc superuser theo cơ chế PostgreSQL, đồng thời thư mục đích phải cho tiến trình database ghi.

### 10.3. Không nên ghi bừa vào data directory

Không dùng thư mục dữ liệu PostgreSQL làm nơi tùy ý đặt các file CSV xuất báo cáo. Tách đường dẫn export được quản trị, quota, retention và permissions để tránh ảnh hưởng lưu trữ dữ liệu database.

### 10.4. COPY TO file có hành vi không ghi đè

Khi server-side `COPY TO 'filename'` tạo file, PostgreSQL thường từ chối nếu file đích đã tồn tại, để tránh ghi đè dữ liệu quan trọng. Quản lý tên tệp phiên bản mới, dọn tệp cũ có kiểm soát; đừng thiết kế script phụ thuộc vào overwrite ngầm.

### 10.5. File nằm trên máy khác cần bước lấy file

Nếu người dùng cần tải export về laptop, một phương án đơn giản hơn là dùng `\copy ... TO local-file` ngay từ psql ở laptop.

## 11. \copy TO: xuất file ngay tại máy khách

Trong psql:

~~~text
\copy import_lab.products (sku, product_name, unit_price, stock) TO '/home/dev/export/products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
~~~

### 11.1. Psql mở file kết quả

Đường dẫn `/home/dev/export/products.csv` thuộc **máy chạy psql**, không phải server PostgreSQL. User OS chạy psql cần quyền ghi thư mục `/home/dev/export`.

### 11.2. Database role cần SELECT

Client chỉ được xuất những cột/rows mà SQL permissions và các chính sách dữ liệu phù hợp cho phép. `\copy` không nâng quyền đọc bảng.

### 11.3. Dữ liệu truyền qua mạng

PostgreSQL gửi dữ liệu theo giao thức COPY đến psql, psql ghi file. Với file lớn, đánh giá network bandwidth, thời gian và disk space của client.

### 11.4. File xuất cần bảo vệ

Nếu có email, số điện thoại hoặc thông tin nhạy cảm, file CSV sau xuất không được PostgreSQL tự áp RLS/GRANT khi nằm trên ổ đĩa người dùng. Cần kiểm soát quyền file, retention, encryption-at-rest và nơi lưu trữ.

## 12. Xuất kết quả một truy vấn thay vì toàn bảng

`COPY TO` hỗ trợ truy vấn được bọc trong dấu ngoặc:

~~~sql
COPY (
    SELECT
        sku,
        product_name,
        unit_price,
        stock
    FROM import_lab.products
    WHERE stock > 0
    ORDER BY sku
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

Đây là SQL `COPY (query) TO STDOUT`. Client có hỗ trợ COPY protocol có thể nhận dòng dữ liệu trực tiếp từ connection.

### 12.1. Với \copy trên psql

~~~text
\copy (SELECT sku, product_name, unit_price, stock FROM import_lab.products WHERE stock > 0 ORDER BY sku) TO '/home/dev/export/in_stock.csv' WITH (FORMAT csv, HEADER true)
~~~

### 12.2. Vì sao dùng query?

Nó cho phép:

- Chọn một số cột.
- Lọc `WHERE`.
- Ghép bảng `JOIN`.
- Tính biểu thức và đặt alias.
- Sắp xếp output khi cần thứ tự ổn định.
- Che/mask cột không được phép xuất.

### 12.3. Không phụ thuộc thứ tự vật lý của bảng

Muốn export có thứ tự rõ ràng để so sánh file hoặc test snapshot, dùng `ORDER BY` trong query. `COPY table TO` không hứa thứ tự nghiệp vụ cố định của các hàng.

### 12.4. Tên cột trên CSV header

Khi dùng `HEADER true` với query, tên cột/alias truy vấn được sử dụng để tạo header theo cơ chế PostgreSQL.

## 13. COPY FROM STDIN và TO STDOUT

PostgreSQL không buộc dữ liệu phải nằm ở file trên server. Hai lựa chọn rất quan trọng:

~~~sql
COPY import_lab.product_stage (
    sku, product_name, unit_price_text, stock_text
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

~~~sql
COPY (
    SELECT sku, product_name, unit_price, stock
    FROM import_lab.products
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

### 13.1. STDIN không nhất thiết là stdin của database OS

Trong giao thức PostgreSQL, `COPY FROM STDIN` nhận luồng dữ liệu **từ client qua connection**. PostgreSQL backend không trực tiếp đọc bàn phím của máy server.

### 13.2. STDOUT là luồng đến client

`COPY TO STDOUT` gửi dữ liệu qua giao thức COPY. Client quyết định ghi thành file, truyền qua pipeline hoặc xử lý trong bộ nhớ theo khả năng.

### 13.3. Vì sao \copy dựa trên STDIN/STDOUT?

Psql mở local file, sau đó dùng COPY protocol. Nhờ vậy nó không cần cấp quyền đọc/ghi file hệ điều hành server cho application role.

### 13.4. Trong JDBC cần COPY API

`PreparedStatement.executeQuery("COPY ... TO STDOUT")` thông thường không phải giao diện streaming COPY thích hợp. PGJDBC có `CopyManager`/COPY API cho việc đó.

## 14. COPY FROM STDIN trong psql tương tác

Psql có thể nhận dữ liệu trực tiếp sau lệnh SQL:

~~~text
COPY import_lab.product_stage (sku, product_name, unit_price_text, stock_text) FROM STDIN WITH (FORMAT csv, HEADER true);
sku,product_name,unit_price_text,stock_text
KB-01,"Bàn phím, cơ",850000.00,8
MS-02,"Chuột ""siêu nhẹ""",299000.00,15
\.
~~~

### 14.1. \. là dấu kết thúc dữ liệu trong psql

Khi psql đang nhập dữ liệu cho `COPY FROM STDIN`, dòng chỉ có `\.` biểu thị kết thúc luồng dữ liệu theo cơ chế script/psql.

### 14.2. Không gõ thêm dấu SQL

Dòng CSV là **dữ liệu**, không phải câu SQL có dấu `;`. Psql phân biệt phase COPY data và phase gửi câu SQL tiếp theo.

### 14.3. Lệnh có HEADER true

Đầu luồng dữ liệu ở ví dụ có header; PostgreSQL bỏ qua dòng header theo cấu hình này. Nếu bạn bỏ header nhưng vẫn `HEADER true`, dòng dữ liệu đầu tiên sẽ bị coi là header và không được nhập.

### 14.4. Không phù hợp nhập dữ liệu lớn bằng tay

Cách này minh họa cơ chế. Đối với file lớn, dùng `\copy FROM 'filename'` hoặc PGJDBC COPY API thay vì paste hàng triệu dòng vào terminal.

## 15. \copy FROM STDIN và piping

Meta-command `\copy` cũng có thể dùng nguồn stdin của client:

~~~text
\copy import_lab.product_stage (sku, product_name, unit_price_text, stock_text) FROM stdin WITH (FORMAT csv, HEADER true)
~~~

Với `\copy ... FROM stdin` trong môi trường psql phù hợp, dữ liệu được đọc từ nguồn input của psql. Khi xây pipeline shell, cần phân biệt:

- Chuẩn input của **shell/process psql**.
- Input do psql dùng để đọc lệnh SQL/meta-command.
- Luồng COPY data từ stdin/pstdin được psql cung cấp.

### 15.1. Cấu trúc pipeline cần được kiểm thử riêng

Shell quoting và psql parsing có thể làm một lệnh nhiều ký tự `\` chạy khác trên Bash, PowerShell và cmd. Khi script automation cần nhập từ pipe, chọn một cú pháp tương thích phiên bản psql và kiểm thử thực tế, thay vì giả định command string trong một shell được chuyển nguyên vẹn.

### 15.2. Không dùng file path khi muốn streaming

Đối với service Java tải file từ object storage, có thể stream InputStream vào PostgreSQL bằng `CopyManager` mà không ghi tệp xuống database server.

### 15.3. Kiểm soát dữ liệu đầu vào

Luồng STDIN vẫn phải có format, encoding và cấu trúc cột đúng. Server không tự phân tích một file JSON/Excel thành CSV nếu bạn chỉ viết `FORMAT csv`.

## 16. FORMAT text, csv và binary

`COPY` hỗ trợ nhiều format, không nên nhầm chúng với nhau.

| Format | Dạng dữ liệu | Ưu điểm | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| `text` | Văn bản phân tách, escape riêng của PostgreSQL | Đơn giản, nhiều trường hợp dùng tốt | Không giống CSV quoting |
| `csv` | CSV với delimiter, quote, escape, header | Tương thích nhiều công cụ dữ liệu | Cần xử lý dấu phân tách, NULL, quote và newline |
| `binary` | Định dạng nhị phân PostgreSQL COPY | Nhanh/không mất định dạng text trong trường hợp phù hợp | Không phải file CSV, kém portable giữa schema/version/kiểu |

### 16.1. FORMAT text

~~~sql
COPY import_lab.products TO STDOUT
WITH (FORMAT text);
~~~

Format text mặc định thường dùng TAB làm delimiter và ký hiệu `\N` cho NULL; có quy tắc escaping riêng cho ký tự tab, newline và backslash.

### 16.2. FORMAT csv

~~~sql
COPY import_lab.products TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

CSV mặc định thường dùng dấu phẩy, ký tự quote là dấu nháy kép và biểu diễn escape cho dấu quote theo quy tắc CSV.

### 16.3. FORMAT binary

~~~sql
COPY import_lab.products TO STDOUT
WITH (FORMAT binary);
~~~

Binary không phù hợp để mở bằng spreadsheet/text editor. Nội dung phụ thuộc mô tả các kiểu PostgreSQL, và định dạng binary không phải giao thức trao đổi trung lập cho mọi hệ quản trị.

### 16.4. Đừng ghép format sai

Một file CSV có header không thể tùy tiện nhập bằng `FORMAT text` và mong PostgreSQL tự nhận dấu phẩy/quote.

## 17. HEADER: dòng tiêu đề

Khi nhập:

~~~sql
COPY import_lab.product_stage (
    sku, product_name, unit_price_text, stock_text
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

`HEADER true` nói rằng dữ liệu đầu vào có dòng tiêu đề để bỏ qua khi nhập. Nó **không tự lập một ánh xạ tùy ý từ tên header sang tên cột** trong mọi chế độ/phiên bản.

### 17.1. Danh sách cột quyết định thứ tự

Nếu file có:

~~~csv
sku,product_name,unit_price_text,stock_text
~~~

thì danh sách cột phải khớp **thứ tự dữ liệu thực tế**, trừ khi bạn chủ động biến đổi file hoặc dùng cơ chế đặc biệt được hỗ trợ.

### 17.2. Header sai cũng có thể bị bỏ qua

Với `HEADER true` cơ bản, PostgreSQL không nhất thiết xác minh header text khớp chính xác tên cột. Những phiên bản có tùy chọn `HEADER MATCH` có hành vi kiểm tra nghiêm hơn; phải xác nhận khả năng của phiên bản server.

### 17.3. HEADER false

Nếu file không có dòng tiêu đề, đặt:

~~~sql
WITH (FORMAT csv, HEADER false)
~~~

hoặc bỏ tùy chọn HEADER khi đúng format. Nếu vô tình đặt true, hàng dữ liệu đầu sẽ bị loại vì bị hiểu là header.

### 17.4. Xuất file

`HEADER true` khi `COPY TO` sẽ thêm dòng tên cột, giúp file tự mô tả. Không bắt buộc nếu hệ thống tiêu thụ yêu cầu dữ liệu thuần không header.

## 18. DELIMITER, QUOTE, ESCAPE

CSV phổ biến dùng:

~~~sql
WITH (
    FORMAT csv,
    DELIMITER ',',
    QUOTE '"',
    ESCAPE '"',
    HEADER true
)
~~~

### 18.1. DELIMITER

Phân cách trường, thường là comma. Có thể dùng dấu khác, ví dụ:

~~~sql
WITH (FORMAT csv, DELIMITER ';', HEADER true)
~~~

nếu file thực sự là CSV dùng semicolon.

### 18.2. QUOTE

Ký tự bao trường có delimiter hoặc ký tự điều khiển cần quote, thường là `"`.

### 18.3. ESCAPE

Ký tự dùng để escape quote; mặc định trong CSV thường cùng với QUOTE. Hai dấu nháy kép liên tiếp thể hiện một dấu nháy kép trong giá trị.

### 18.4. Ví dụ dấu phẩy trong tên

~~~csv
KB-01,"Bàn phím, cơ",850000.00,8
~~~

Giá trị tên vẫn là `Bàn phím, cơ`, không bị tách thành hai trường.

### 18.5. Ví dụ dấu quote trong tên

~~~csv
MS-02,"Chuột ""siêu nhẹ""",299000.00,15
~~~

Giá trị đọc được là `Chuột "siêu nhẹ"`.

### 18.6. Trường chứa xuống dòng

Một ô CSV có thể chứa newline nếu được quote đúng. Đừng dùng bộ xử lý tự viết chỉ `split("\n")` rồi `split(",")` để giả lập parser CSV cho dữ liệu phức tạp.

## 19. SQL NULL và chuỗi rỗng trong CSV

Đây là một trong những nguyên nhân nhập sai dữ liệu âm thầm.

### 19.1. CSV mặc định

Với `FORMAT csv` và cấu hình mặc định, một trường **rỗng không được quote** thường biểu diễn SQL `NULL`, còn một trường **rỗng được quote** (`""`) biểu diễn chuỗi text rỗng.

Ví dụ:

~~~csv
sku,product_name,unit_price_text,stock_text
AA-01,,100.00,5
BB-02,"",100.00,5
~~~

Nếu đọc vào cột text, `AA-01` có `product_name IS NULL`, còn `BB-02` có `product_name = ''` theo cấu hình CSV mặc định.

### 19.2. NULL 'NULL'

Bạn có thể chọn một token riêng:

~~~sql
WITH (
    FORMAT csv,
    NULL 'NULL',
    HEADER true
)
~~~

Khi đó literal unquoted `NULL` được dùng như ký hiệu NULL. Nhưng nếu dữ liệu hợp lệ chứa chính chuỗi `NULL`, cần hiểu cách quote để phân biệt.

### 19.3. Text format khác CSV

Với `FORMAT text`, ký hiệu NULL mặc định là `\N`. Không kết luận `\N` luôn là ký hiệu NULL của mọi file CSV; format và `NULL` option quyết định.

### 19.4. FORCE_NULL

Trong những trường hợp import CSV cần coi cả giá trị **được quote** bằng null-string là SQL NULL, tùy chọn `FORCE_NULL` trên cột phù hợp có thể hỗ trợ.

### 19.5. FORCE_NOT_NULL

`FORCE_NOT_NULL` hỗ trợ tránh diễn giải unquoted null-string thành SQL NULL cho các cột CSV được chỉ định. Nó hữu ích khi một hệ thống xuất file rỗng nhưng nghiệp vụ muốn chuỗi rỗng.

### 19.6. Không đoán ý nghĩa dữ liệu từ file

Trước khi import production, phải xác định hợp đồng dữ liệu: trường rỗng có nghĩa *không có giá trị*, *chuỗi rỗng*, *0*, hay *giá trị mặc định*? Đừng chọn `NULL ''` tùy tiện rồi làm mất phân biệt.

## 20. Danh sách cột và DEFAULT

Một bảng có:

~~~sql
CREATE TABLE import_lab.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    product_name text NOT NULL,
    unit_price numeric(14,2) NOT NULL,
    stock integer NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

Khi import, nên chỉ định:

~~~sql
COPY import_lab.products (
    sku, product_name, unit_price, stock
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

Các cột không có trong danh sách dùng cơ chế mặc định hoặc null/constraint theo quy tắc PostgreSQL. Ở đây `product_id` sinh identity và `updated_at` lấy default.

### 20.1. Không tự tin thứ tự cột bảng không đổi

Thêm một cột bằng migration có thể làm file cũ không còn khớp nếu dùng `COPY table FROM ...` không có danh sách cột.

### 20.2. Explicit NULL khác omitted column

Nếu CSV có cột `updated_at` và giá trị được hiểu là SQL NULL, PostgreSQL không tự dùng `DEFAULT clock_timestamp()` chỉ vì ô rỗng. **Cột bị lược khỏi danh sách COPY** và **cột được đưa vào với NULL** là hai tình huống khác nhau.

### 20.3. GENERATED/IDENTITY

Với identity columns, hãy hiểu quy tắc `COPY` trong phiên bản PostgreSQL: nếu file cung cấp giá trị cho identity column, PostgreSQL có thể dùng giá trị được cung cấp thay vì tự sinh như trường hợp cột bị lược. Khi muốn tạo ID mới, **không nhập cột identity** trong danh sách.

### 20.4. Generated columns

Stored/generated columns có ràng buộc riêng về việc nhập giá trị trực tiếp. Không xuất rồi nhập lại tất cả cột mà không xem metadata của generated columns.

## 21. ENCODING và tiếng Việt

File chứa:

~~~csv
sku,product_name,unit_price_text,stock_text
TV-01,Bộ gõ tiếng Việt,99000.00,12
~~~

### 21.1. Client encoding

`COPY`/`\copy` xử lý text theo encoding được chỉ định hoặc `client_encoding` theo quy tắc phiên bản. Nếu file UTF-8 nhưng client chọn encoding khác, có thể lỗi chuyển mã hoặc dữ liệu bị lỗi ký tự.

### 21.2. Chỉ định ENCODING khi hỗ trợ

~~~sql
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
~~~

Tùy chọn encoding cho COPY được hỗ trợ ở các phiên bản PostgreSQL hiện đại; khi làm việc với server cũ, kiểm tra cú pháp/phương án đặt `client_encoding` thích hợp.

### 21.3. UTF-8 BOM

Một số ứng dụng lưu CSV kiểu UTF-8 có **byte-order mark (BOM)** đầu file. Nếu công cụ import không loại BOM theo cách bạn dự tính, ký tự BOM có thể dính vào tên cột/header hoặc giá trị đầu. Xác nhận với file thực tế và chuẩn hóa ở bước tiền xử lý khi cần.

### 21.4. Không đoán encoding bằng mắt

Một tệp Windows-1258, UTF-8 hoặc UTF-16 có thể nhìn ổn trong editor nhưng byte representation khác. PostgreSQL không tự “chữa” file UTF-16 thành UTF-8 chỉ nhờ `FORMAT csv`.

### 21.5. Chuẩn hóa đầu vào

Thiết kế pipeline nên kiểm tra byte encoding/định dạng tệp ở boundary, không đợi tới khi hàng thứ 50.000 báo lỗi “invalid byte sequence”.

## 22. Ngày giờ, số thập phân và locale

CSV là định dạng văn bản; PostgreSQL phải ép kiểu sang type của cột đích.

### 22.1. Số tiền

~~~csv
sku,unit_price
AA-01,1234.50
~~~

`numeric` thường chấp nhận dạng dấu chấm thập phân trong cú pháp SQL. Nếu file dùng `1.234,50` do locale, phải chuẩn hóa theo hợp đồng rõ; không chỉ thay mọi dấu phẩy vì CSV delimiter cũng dùng dấu phẩy.

### 22.2. Ngày giờ

Nên dùng ISO 8601 và timezone/offset rõ khi cần:

~~~text
2026-11-14T09:30:00+07:00
~~~

### 22.3. DateStyle

Cách PostgreSQL diễn giải một số chuỗi ngày mơ hồ có thể phụ thuộc `DateStyle`. Với import liên hệ thống, tránh chuỗi như `01/02/26` không rõ là tháng/ngày hay ngày/tháng.

### 22.4. Time zone

Nếu cột là `timestamptz` mà file không có timezone, cách diễn giải có thể phụ thuộc session time zone. Nên chuẩn hóa UTC hoặc offset rõ theo hợp đồng.

### 22.5. Staging và kiểm tra trước cast

Với file ngoài, nhập ngày/số vào text staging rồi dùng truy vấn kiểm tra hoặc chuyển đổi có kiểm soát cho phép ghi thông báo lỗi theo từng hàng.

## 23. Kiểm tra dữ liệu staging

Sau khi chạy `\copy`, trước khi đưa dữ liệu vào bảng đích, hãy khảo sát các hàng không hợp lệ.

### 23.1. Tìm SKU sai format

~~~sql
SELECT stage_id, sku
FROM import_lab.product_stage
WHERE sku IS NULL
   OR upper(btrim(sku)) !~ '^[A-Z0-9-]{3,24}$';
~~~

### 23.2. Tìm tên rỗng

~~~sql
SELECT stage_id, product_name
FROM import_lab.product_stage
WHERE product_name IS NULL
   OR btrim(product_name) = '';
~~~

### 23.3. Tìm giá không hợp lệ

~~~sql
SELECT stage_id, unit_price_text
FROM import_lab.product_stage
WHERE unit_price_text IS NULL
   OR unit_price_text
      !~ '^[0-9]{1,12}([.][0-9]{1,2})?$';
~~~

Regex này chỉ chấp nhận số không âm tối đa 12 chữ số nguyên và tối đa 2 chữ số thập phân; nó là **quy tắc cho lab**, không phải parser tiền tệ quốc tế.

### 23.4. Tìm tồn kho sai định dạng

~~~sql
SELECT stage_id, stock_text
FROM import_lab.product_stage
WHERE stock_text IS NULL
   OR stock_text !~ '^[0-9]{1,9}$';
~~~

Ví dụ cho phép tối đa 9 chữ số không âm để đảm bảo cast sang PostgreSQL `integer` không vượt phạm vi chỉ vì số quá lớn.

### 23.5. Phát hiện SKU trùng trong cùng file

~~~sql
SELECT
    upper(btrim(sku)) AS normalized_sku,
    count(*) AS occurrences
FROM import_lab.product_stage
GROUP BY upper(btrim(sku))
HAVING count(*) > 1;
~~~

Hai SKU `kb-01` và `KB-01` có thể bị coi là trùng sau normalize, tùy nghiệp vụ.

### 23.6. Không bỏ hàng lỗi im lặng

Một `INSERT SELECT` chỉ lọc các dòng hợp lệ mà không lưu report lỗi có thể khiến import “thành công” nhưng thiếu dữ liệu. Quy trình phải có chính sách fail-all, quarantine hoặc partial acceptance minh bạch.

## 24. Promote staging → bảng chính theo giao dịch

Giả sử file của một đợt import đã được kiểm tra; ta có thể dùng transaction để đảm bảo **không merge khi staging còn hàng không hợp lệ**.

~~~sql
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM import_lab.product_stage
        WHERE sku IS NULL
           OR upper(btrim(sku)) !~ '^[A-Z0-9-]{3,24}$'
           OR product_name IS NULL
           OR btrim(product_name) = ''
           OR unit_price_text IS NULL
           OR unit_price_text
               !~ '^[0-9]{1,12}([.][0-9]{1,2})?$'
           OR stock_text IS NULL
           OR stock_text !~ '^[0-9]{1,9}$'
    ) THEN
        RAISE EXCEPTION 'Product stage contains invalid rows';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM import_lab.product_stage
        GROUP BY upper(btrim(sku))
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate SKU inside import batch';
    END IF;
END;
$$;

INSERT INTO import_lab.products (
    sku,
    product_name,
    unit_price,
    stock
)
SELECT
    upper(btrim(sku)),
    btrim(product_name),
    unit_price_text::numeric(14,2),
    stock_text::integer
FROM import_lab.product_stage
ON CONFLICT (sku)
DO UPDATE SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    stock = EXCLUDED.stock,
    updated_at = clock_timestamp()
WHERE (import_lab.products.product_name,
       import_lab.products.unit_price,
       import_lab.products.stock)
   IS DISTINCT FROM
      (EXCLUDED.product_name,
       EXCLUDED.unit_price,
       EXCLUDED.stock);

COMMIT;
~~~

### 24.1. Nếu DO block ném lỗi

Transaction chuyển sang trạng thái lỗi. Trong script tự động nên bật `psql -v ON_ERROR_STOP=1` hoặc cơ chế equivalent để **ngừng ngay**, sau đó rollback theo chủ sở hữu transaction; không tiếp tục các bước và báo thành công.

### 24.2. Vì sao kiểm tra duplicate trước ON CONFLICT?

Nếu một `INSERT ... ON CONFLICT DO UPDATE` nhận nhiều hàng cùng khóa target trong **một statement**, nó có thể thất bại vì không thể tác động cùng target row nhiều lần như ý định. Nên chuẩn hóa và loại trùng trong batch trước khi merge.

### 24.3. Vì sao dùng WHERE ... IS DISTINCT FROM?

Tránh UPDATE ghi lại hàng không có thay đổi thực sự; giảm WAL, index churn và trigger side effects. Đặc biệt quan trọng khi chạy import lặp với cùng dữ liệu.

### 24.4. Không copy thẳng mọi thứ vào production

Nếu file chứa các đối tượng cần xác thực quan hệ, mã tiền tệ, danh mục, tenant hoặc điều kiện business khác, thêm validation tương ứng trước khi promotion.

### 24.5. Lab chưa phân biệt nhiều batch staging

Trong production, staging cần thêm batch ID/import job ID, unique constraints, trạng thái, source checksum và retention; không dùng toàn bộ bảng staging của nhiều file để promote chung không có phạm vi.

## 25. Import và promote trong cùng transaction

Khi muốn dữ liệu staging và bảng đích cùng rollback nếu gặp lỗi, psql có thể chạy:

~~~text
BEGIN;
TRUNCATE import_lab.product_stage;
\copy import_lab.product_stage (sku, product_name, unit_price_text, stock_text) FROM '/home/dev/import/products.csv' WITH (FORMAT csv, HEADER true)
-- Chạy phần kiểm tra và INSERT ... SELECT ở trên, không BEGIN lồng.
COMMIT;
~~~

Đây là **sơ đồ workflow**, không phải script chạy nguyên dạng với dòng chú thích thay cho validation. Muốn tự động hóa, hãy đặt những câu validation/merge đầy đủ vào script, dùng `ON_ERROR_STOP` và bảo đảm mỗi transaction chỉ được quản lý một nơi.

### 25.1. \copy tham gia transaction hiện tại

Psql sử dụng cùng kết nối để gửi `COPY FROM STDIN`, nên nếu đang `BEGIN`, dữ liệu từ `\copy` thuộc transaction đó.

### 25.2. Lỗi giữa chừng

Một lỗi parse CSV hoặc constraint trong COPY khiến statement thất bại. Trong transaction thông thường, PostgreSQL sẽ không cho tiếp tục câu SQL khác cho đến khi rollback (hoặc rollback về savepoint phù hợp).

### 25.3. Phân biệt all-or-nothing và batch commit

Nếu file hàng trăm GB được chia 100 batches, commit từng batch giúp tránh transaction khổng lồ nhưng mất khả năng rollback **toàn file** chỉ bằng một ROLLBACK. Cần lưu checkpoint, import ID và kế hoạch resume.

### 25.4. Không giữ transaction mở khi chờ file tải từ Internet

Nên lấy/kiểm tra file trên client trước khi bắt đầu transaction; việc giữ transaction chờ I/O bên ngoài có thể kéo dài lock/snapshot và chiếm connection.

## 26. COPY và constraints, triggers, rules

PostgreSQL xử lý `COPY FROM` như một thao tác nhập dữ liệu vào bảng với quy tắc riêng, không phải bypass toàn bộ schema.

### 26.1. CHECK và NOT NULL

Dữ liệu vi phạm constraint sẽ bị từ chối. Ví dụ `stock = -1` không thể đi vào `import_lab.products` nếu `CHECK (stock >= 0)` được áp.

### 26.2. UNIQUE và PRIMARY KEY

Indexes/constraints vẫn cần được cập nhật và kiểm tra. Nếu file có SKU trùng, COPY trực tiếp vào bảng đích có thể báo duplicate-key error.

### 26.3. FOREIGN KEY

COPY FROM áp các foreign-key checks khi cần. Không dùng nó làm đường lách integrity của quan hệ.

### 26.4. Triggers

COPY FROM trên bảng đích kích hoạt triggers phù hợp và áp CHECK constraints. Nếu một row trigger ghi audit hay gọi logic nặng, nạp hàng triệu rows có thể kéo dài đáng kể.

### 26.5. Rules

Theo cơ chế PostgreSQL, `COPY FROM` **không kích hoạt rewrite rules** như một số câu `INSERT` thông thường. Nếu application thiết kế xử lý dữ liệu qua rule, đừng cho rằng COPY đi qua cùng luồng.

### 26.6. RLS

`COPY FROM` không hỗ trợ trực tiếp việc nhập vào bảng đang có row-level security theo một số quy tắc PostgreSQL; khi cần nhập dưới RLS, dùng đường `INSERT` phù hợp hoặc staging với role/permission và policy được thiết kế rõ. Không tắt RLS chỉ để import nhanh mà không đánh giá phân quyền.

## 27. COPY và bảng phân vùng

Một partitioned table có thể nhận COPY theo những cơ chế/phiên bản hỗ trợ; PostgreSQL định tuyến hàng tới partitions dựa trên partition key.

### 27.1. Dữ liệu ngoài phạm vi partition

Nếu không có partition thích hợp (và không có default partition), COPY FROM có thể lỗi vì không có partition chứa row.

### 27.2. Trigger trên partitions

Những row triggers của partitioned table/partitions có thể thực thi theo cơ chế row routing; statement-level triggers tuân theo quan hệ được nhắm và semantics riêng. Cần thử workload thật khi có audit.

### 27.3. Không ngầm giả định file sorted

Nếu file chứa nhiều ngày/tháng, PostgreSQL vẫn phải route từng row theo key. Cân nhắc partitioning, index và import ordering nếu đo thấy ảnh hưởng.

### 27.4. COPY TO parent

Khi xuất dữ liệu của partitioned table, hãy kiểm tra tính năng/phạm vi của câu `COPY` theo phiên bản. Một mẫu rõ ràng và linh hoạt là `COPY (SELECT ... FROM parent ... ORDER BY ...) TO STDOUT` để điều khiển chính xác dữ liệu được lấy qua partitions.

## 28. Quyền SQL table và quyền file server

Một role có quyền:

~~~sql
GRANT INSERT ON import_lab.product_stage TO import_role;
GRANT SELECT ON import_lab.products TO export_role;
~~~

vẫn không mặc nhiên được thực hiện:

~~~sql
COPY import_lab.product_stage
FROM '/etc/sensitive-file'
WITH (FORMAT text);
~~~

### 28.1. Hai lớp quyền

- **Quyền bảng/cột:** `INSERT` cho COPY FROM, `SELECT` cho COPY TO hoặc query.
- **Quyền server file/program:** kiểm soát backend có được mở file/chạy command ở máy chủ không.

### 28.2. pg_read_server_files

Là predefined role có đặc quyền đọc các file mà server có thể truy cập theo cơ chế PostgreSQL. Đây là khả năng **rất rộng và nhạy cảm**.

### 28.3. pg_write_server_files

Cấp khả năng ghi server files theo những điều kiện hệ điều hành và PostgreSQL. Có thể tạo rủi ro khi ghi ra những vị trí do PostgreSQL service account có thể ghi.

### 28.4. pg_execute_server_program

Cho phép chạy server-side programs qua các tính năng như `COPY PROGRAM`. Đây có thể mở rộng thành code execution với quyền OS của PostgreSQL service account, cần bảo vệ chặt.

### 28.5. Không cấp các role trên cho ứng dụng thông thường

Trong phần lớn workflows, app/importer chỉ cần `INSERT/SELECT` trên bảng phù hợp và dùng `\copy` hoặc COPY STDIN/STDOUT. Không nâng `pg_read_server_files` chỉ để “import cho nhanh”.

## 29. Quyền hệ điều hành và PostgreSQL role

Một file trên server cần đồng thời:

1. File có thật trong filesystem mà backend nhìn thấy.
2. PostgreSQL OS process có quyền đọc/ghi tương ứng.
3. Database role được phép dùng server-file COPY.
4. Database role có quyền trên bảng/cột.

### 29.1. Thiếu quyền OS

Ngay cả superuser PostgreSQL cũng không thể tự đọc một file mà tiến trình OS PostgreSQL bị từ chối theo permission/ACL, trừ khi có quyền thực tế phù hợp qua cơ chế khác.

### 29.2. Thiếu database role

File OS có quyền đọc không đủ nếu PostgreSQL chặn role dùng server-file COPY.

### 29.3. Container mount

~~~text
Host: /home/dev/products.csv
Container: /input/products.csv
~~~

Nếu mount file vào container dưới `/input/products.csv`, server-side COPY bên trong container dùng **đường dẫn container**, không tự dùng đường dẫn host.

### 29.4. Managed databases

Trên dịch vụ PostgreSQL được quản lý, những đường dẫn tùy ý tới filesystem server có thể không được cấp cho khách hàng. Sử dụng client COPY stream hoặc cơ chế import/export chính thức của nhà cung cấp theo yêu cầu hệ thống.

## 30. COPY PROGRAM: chạy lệnh hệ điều hành phía server

PostgreSQL có cú pháp:

~~~sql
-- Ví dụ mô tả chức năng, không chạy với app role thường.
COPY import_lab.products
TO PROGRAM 'gzip > /var/lib/postgresql/export/products.csv.gz'
WITH (FORMAT csv, HEADER true);
~~~

Lúc này PostgreSQL server khởi chạy **một chương trình ở phía server**, gửi output COPY qua stdin của chương trình hoặc đọc stdout khi `FROM PROGRAM`, tùy hướng.

### 30.1. Không phải lệnh chạy trên laptop

`PROGRAM 'gzip ...'` trong **SQL COPY** chạy phía server. Nếu server là container Linux, nó cần có `gzip` trong môi trường container đó, không phải máy Windows đang gõ SQL.

### 30.2. Quyền cực kỳ nhạy cảm

Thường đòi quyền `pg_execute_server_program` hoặc superuser. Không cấp role này cho account chỉ cần import file CSV.

### 30.3. Shell injection

`PROGRAM` có thể được thực hiện qua shell; xây command string từ input không tin cậy có nguy cơ command injection. Không nối tên file do user gửi trực tiếp vào `PROGRAM`.

### 30.4. Quy trình an toàn hơn

Nếu cần gzip/compression, có thể xuất luồng COPY đến một client tin cậy rồi nén phía client, tách quyền OS program execution khỏi database server.

## 31. \copy PROGRAM: chương trình phía client

Psql hỗ trợ lựa chọn `PROGRAM` trong `\copy` ở những phiên bản phù hợp. Ví dụ:

~~~text
\copy (SELECT sku, product_name, unit_price FROM import_lab.products ORDER BY sku) TO PROGRAM 'gzip > /home/dev/export/products.csv.gz' WITH (FORMAT csv, HEADER true)
~~~

### 31.1. Chương trình chạy ở máy psql

Khác SQL `COPY TO PROGRAM`, `\copy ... TO PROGRAM` làm psql khởi chạy command **ở môi trường client**.

### 31.2. Quyền OS client

Tài khoản chạy psql cần có `gzip` và quyền ghi path phía client. Không cần `pg_execute_server_program` chỉ vì psql nén tệp local.

### 31.3. Shell syntax có thể khác

Ví dụ sử dụng shell Unix. Trên Windows, chương trình, quoting và redirection khác; cần chọn command được hệ điều hành hỗ trợ.

### 31.4. Không nhận command string từ user

Chạy command phía client vẫn có rủi ro code execution, dữ liệu lộ qua pipe và đường dẫn không an toàn. Không tạo lệnh `PROGRAM` từ input không được xác thực.

### 31.5. Nếu không cần PROGRAM, hãy dùng file

`\copy ... TO 'products.csv'` thường đơn giản, dễ audit và giảm surface tấn công hơn.

## 32. COPY trong giao dịch: thành công hoặc thất bại

PostgreSQL có transaction semantics cho `COPY` giống những thao tác ghi dữ liệu khác.

~~~sql
BEGIN;

COPY import_lab.product_stage (
    sku, product_name, unit_price_text, stock_text
)
FROM STDIN
WITH (FORMAT csv, HEADER true);

-- Luồng dữ liệu COPY được client cấp tại đây.

COMMIT;
~~~

### 32.1. Atomicity của statement

Nếu có lỗi parse/constraint trong một COPY FROM, transaction không thể commit những hàng của statement thất bại như thể một phần hợp lệ. Lỗi có thể khiến transaction bị aborted và cần rollback.

### 32.2. Khác với chi phí storage vật lý

Trong một COPY FROM lớn thất bại sau nhiều hàng, PostgreSQL có thể đã ghi các tuple rồi đánh dấu chúng không thể nhìn thấy sau thất bại; không gian lưu trữ đã tiêu thụ có thể cần **VACUUM** để thu hồi/tái sử dụng. Không ngầm kết luận lỗi COPY không làm tốn disk.

### 32.3. Không nên giữ transaction lâu ngoài nhu cầu

Một transaction nhập dữ liệu cực lớn có thể giữ locks, chiếm WAL và làm checkpoint/replication lag đáng kể. Cần cân nhắc batch size, lịch chạy và mức độ cho phép partial commit.

### 32.4. Rollback không giảm ngay WAL đã tạo

Transaction rollback bảo vệ tính đúng dữ liệu, nhưng I/O/WAL đã phát sinh không biến mất. Đây là lý do cần validate file và chuẩn hóa trước khi gửi file khổng lồ.

### 32.5. Nếu client mất kết nối

Một COPY đang diễn ra có thể thất bại khi connection bị ngắt. Với import pipelines, cần có job ID, checksum và khả năng kiểm tra trạng thái dữ liệu đã commit trước khi chạy lại.

## 33. COPY lớn và chiến lược chia batch

Giả sử một file có 15 triệu rows.

### 33.1. Một transaction lớn

Ưu điểm:

- All-or-nothing nếu thành công/rollback toàn bộ.
- Một pipeline dữ liệu nhất quán trong một transaction.

Đánh đổi:

- Transaction dài.
- WAL/disk/replication lag.
- Khả năng thất bại muộn khiến phải làm lại nhiều.

### 33.2. Chia thành nhiều batches

Ưu điểm:

- Dễ checkpoint.
- Giới hạn thời lượng/lock mỗi transaction.
- Có thể chạy lại phần lỗi.

Đánh đổi:

- Không có nguyên tử toàn file nếu đã commit các batch trước.
- Cần idempotency/unique keys và quy tắc upsert.
- Phải báo cáo trạng thái “đã nhập một phần”.

### 33.3. Raw staging và promotion

Một thiết kế cân bằng có thể nhập file vào **staging phân biệt batch**, validate đầy đủ, rồi chỉ promote những batches được phê duyệt theo transaction ngắn hơn.

### 33.4. Dedupe và source version

Nếu cùng SKU được nhập nhiều lần từ nhiều file, quy định dữ liệu mới ghi đè cũ theo nguồn/timestamp hay reject conflict. `ON CONFLICT DO UPDATE` cần có quy tắc nghiệp vụ, không chỉ vì có sẵn cú pháp.

## 34. COPY và hiệu năng

`COPY` thường hiệu quả hơn nhiều câu `INSERT` riêng lẻ do giảm overhead parser, statement và network round trips.

### 34.1. Điều gì vẫn phải làm?

PostgreSQL vẫn phải:

- Parse/chuyển kiểu dữ liệu.
- Ghi heap và WAL theo chế độ.
- Bảo đảm constraints.
- Duy trì indexes.
- Kích hoạt triggers phù hợp.
- Xử lý locks và transaction.

### 34.2. COPY không luôn là đường nhanh nhất trong mọi tình huống

Nếu dữ liệu cần nhiều transform và validation phức tạp, một pipeline staging + set-based INSERT có thể tốt hơn COPY thẳng vào bảng chính.

### 34.3. Indexes trên bảng đích

Thêm nhiều indexes làm import chậm hơn vì mỗi row cần cập nhật chúng. Tuy nhiên không nên bỏ những constraints/indexes thiết yếu trên production để tăng tốc tùy tiện.

### 34.4. Triggers nặng

Một trigger `FOR EACH ROW` có thể thực thi N lần với file N hàng; nếu mỗi lần query bảng lớn sẽ tạo N+1 workload. Cân nhắc chuyển logic batch sang statement-level/transition table khi phù hợp.

### 34.5. Sau import nhiều dữ liệu

Planner cần statistics phù hợp. Chạy:

~~~sql
ANALYZE import_lab.products;
~~~

khi có thay đổi phân bố dữ liệu lớn và autovacuum chưa cập nhật kịp.

### 34.6. Không đo trên production trước

Đánh giá throughput, WAL, disk, locks và thời gian import ở staging có dữ liệu đủ giống thật; không giả định mọi file đều có cùng tốc độ.

## 35. VACUUM, WAL và replication

### 35.1. COPY ghi dữ liệu vào PostgreSQL

Dù file vào qua `\copy`, dữ liệu vẫn được ghi ở server bằng hệ thống storage/WAL của PostgreSQL theo quy tắc. `\copy` không bỏ qua WAL chỉ vì file được đọc ở client.

### 35.2. WAL và logical/physical replicas

Import lớn có thể tạo WAL khiến replica lag. Nếu hệ thống chạy báo cáo trên replica, cần theo dõi độ trễ khi nhập.

### 35.3. VACUUM sau COPY lỗi

Một COPY thất bại sau khi đã tạo nhiều tuple không còn hiển thị có thể cần cleanup để giải phóng không gian có thể tái sử dụng. Cân nhắc `VACUUM` trên bảng liên quan theo vận hành DB.

### 35.4. COPY FREEZE

PostgreSQL có tùy chọn `FREEZE` với các điều kiện khá hạn chế (ví dụ table mới được tạo/truncate trong subtransaction hiện tại theo quy tắc, không phải partitioned/foreign table tùy điều kiện). Nó có thể cải thiện bulk loading trong môi trường thích hợp nhưng ảnh hưởng semantics MVCC và không dùng bừa trên bảng production có transaction đồng thời.

### 35.5. UNLOGGED và TEMP tables

Staging có thể dùng `UNLOGGED` hoặc `TEMP` khi yêu cầu durability/replication cho phép. Nhưng chúng có đánh đổi về crash recovery, replication và session scope; không mặc định dùng staging unlogged cho dữ liệu import bắt buộc phục hồi sau sự cố.

## 36. Theo dõi tiến độ với pg_stat_progress_copy

PostgreSQL hiện đại cung cấp view tiến độ COPY:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed
FROM pg_stat_progress_copy;
~~~

### 36.1. command

Cho biết loại thao tác, chẳng hạn `COPY FROM` hoặc `COPY TO`, theo dữ liệu của view và phiên bản.

### 36.2. type

Phân biệt cách COPY truyền dữ liệu như file, program hoặc pipe/callback. Những tên giá trị cụ thể phụ thuộc khả năng PostgreSQL, dùng view đang chạy để quan sát.

### 36.3. bytes_processed

Số bytes đã xử lý, hữu ích để biết import có tiếp tục tiến triển hay không.

### 36.4. bytes_total có thể bằng 0

Khi kích thước nguồn không xác định qua luồng, PostgreSQL có thể không biết tổng bytes. Đừng lấy bytes_total=0 rồi kết luận import rỗng hoặc bị treo.

### 36.5. tuples_processed

Giúp theo dõi số hàng đã được xử lý. Con số đang tăng không đảm bảo **transaction đã commit**; cuối cùng vẫn có thể rollback.

### 36.6. Quyền xem thông tin

Monitoring views có thể hạn chế chi tiết theo role. Tài khoản giám sát cần quyền phù hợp nhưng không nhất thiết là superuser.

## 37. pg_stat_activity và COPY

Khi một COPY đang chạy:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_prefix
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start DESC;
~~~

### 37.1. Đọc query cùng wait event

Nếu thấy một COPY chờ IO hoặc lock, nguyên nhân có thể là disk, network, constraint/index hoặc transaction khác chặn.

### 37.2. Không suy lock từ “đang COPY”

`COPY FROM` cần locks phù hợp để sửa bảng và có thể tương tác với DDL, VACUUM FULL hoặc các transaction khác. Phân tích `pg_locks` khi cần xác định blockers thật.

### 37.3. Ứng dụng dùng \copy vẫn hiện COPY FROM STDIN

Từ góc độ server, `\copy FROM local file` được gửi dưới dạng COPY protocol. Monitoring server không trực tiếp chỉ ra **tên file local** trên laptop psql.

### 37.4. ApplicationName

Đặt `application_name`/PGJDBC ApplicationName phù hợp để phân biệt import worker, ETL job, psql interactive và ứng dụng API.

## 38. PGJDBC CopyManager: đưa file client vào PostgreSQL

Trong Java, không thể chạy meta-command `\copy` như một câu SQL bằng `PreparedStatement`. PGJDBC cung cấp `CopyManager` thông qua API driver.

### 38.1. Ví dụ nhập bằng Reader

~~~java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

public final class ProductCsvImporter {
    private final DataSource dataSource;

    public ProductCsvImporter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long importCsv(Path localCsv) throws Exception {
        String copySql =
            "COPY import_lab.product_stage " +
            "(sku, product_name, unit_price_text, stock_text) " +
            "FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')";

        try (Connection connection = dataSource.getConnection();
             Reader input = Files.newBufferedReader(
                 localCsv, StandardCharsets.UTF_8
             )) {

            connection.setAutoCommit(false);
            try {
                PGConnection pgConnection =
                    connection.unwrap(PGConnection.class);
                CopyManager copyManager =
                    pgConnection.getCopyAPI();

                long copiedRows =
                    copyManager.copyIn(copySql, input);

                // Thực hiện validation/merge bằng SQL trên
                // cùng connection trước khi commit nếu cần.

                connection.commit();
                return copiedRows;
            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
~~~

Đây là ví dụ PGJDBC version hỗ trợ `PGConnection.getCopyAPI()`/`CopyManager.copyIn(String,Reader)`. Nó minh họa **một file local/stream → STDIN**, không cấp quyền server-file. Khi dùng implementation DataSource/pool cụ thể, phải xác nhận `unwrap(PGConnection.class)` hoạt động và connection được quản lý trong phạm vi của job.

### 38.2. Quyền

Role ứng dụng chỉ cần quyền `INSERT` phù hợp trên bảng stage, không cần `pg_read_server_files` vì nguồn là InputStream/Reader phía client.

### 38.3. Transaction rõ ràng

`setAutoCommit(false)`, `commit()`, `rollback()` điều khiển cùng transaction như những câu SQL khác. Có thể thực hiện validation/merge bằng `PreparedStatement` trên **cùng connection** trước commit.

### 38.4. Error handling

CopyManager có thể ném lỗi I/O hoặc SQL; ví dụ catch các lỗi SQL/runtime để rollback, còn một lỗi I/O checked khác do Reader có thể cần catch/rollback bổ sung. Trong code production, **mọi lỗi phát sinh trước commit** (bao gồm IOException) phải dẫn tới rollback rõ ràng trước khi connection đóng.

### 38.5. Không đọc toàn file vào String

Với file lớn, dùng Reader/InputStream giúp streaming thay vì giữ hàng trăm MB trong heap.

## 39. PGJDBC CopyManager: xuất dữ liệu

Một đường xuất là `CopyManager.copyOut` vào `Writer` hoặc `OutputStream` tùy API driver.

~~~java
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import javax.sql.DataSource;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

public final class ProductCsvExporter {
    public void exportCsv(
            DataSource dataSource,
            Path localCsv
    ) throws Exception {
        String copySql =
            "COPY (" +
            "SELECT sku, product_name, unit_price, stock " +
            "FROM import_lab.products ORDER BY sku" +
            ") TO STDOUT WITH (FORMAT csv, HEADER true)";

        try (Connection connection = dataSource.getConnection();
             Writer out = Files.newBufferedWriter(
                 localCsv, StandardCharsets.UTF_8
             )) {
            CopyManager copyManager =
                connection.unwrap(PGConnection.class)
                          .getCopyAPI();
            copyManager.copyOut(copySql, out);
        }
    }
}
~~~

Tùy phiên bản PGJDBC, các overloads `copyOut` hỗ trợ `Writer` hoặc `OutputStream` với hành vi mã hóa khác nhau. Nếu dự án dùng phiên bản chỉ có OutputStream, dùng API chính thức tương ứng và quản lý encoding rõ ràng.

### 39.1. File là client file

`localCsv` thuộc filesystem mà **Java process đang chạy**, không phải server DB. Nếu Java process chạy trong Kubernetes pod, đường dẫn thuộc pod/container.

### 39.2. Export lỗi giữa chừng

Tệp có thể đã được ghi một phần trước khi lỗi mạng/SQL. Quy trình production nên ghi vào **temporary file**, chỉ rename/publish khi copyOut hoàn tất và các kiểm tra cần thiết thành công.

### 39.3. Quyền SELECT

Role Java cần quyền đọc query được sử dụng. Không cần `pg_write_server_files` vì file được ghi phía client.

### 39.4. Không dùng OFFSET cho export khổng lồ một cách vô thức

`COPY (SELECT ... ORDER BY ...) TO STDOUT` stream kết quả; nếu cần resume giữa file lỗi, thiết kế keyset/chunks và manifest riêng.

## 40. JDBC batch hay CopyManager?

| Tiêu chí | JDBC batch INSERT | PGJDBC CopyManager |
| --- | --- | --- |
| Dữ liệu nguồn | Java objects/rows | CSV/text/binary stream |
| SQL mô hình | `INSERT ... VALUES (?,...)` nhiều lần | `COPY ... FROM STDIN` |
| Validation Java | Thuận tiện theo object | Thường staging sau COPY |
| Tốc độ bulk dữ liệu lớn | Tốt nếu batch hợp lý | Thường rất hiệu quả |
| RETURNING từng row | Linh hoạt hơn qua SQL API | COPY FROM không trả ResultSet từng row |
| Conflict handling | Có thể dùng `ON CONFLICT` trong INSERT | COPY trực tiếp không hỗ trợ `ON CONFLICT` |
| Quyền server file | Không | Không khi FROM STDIN |
| Transaction JDBC | Có | Có |
| Khả năng tái thử | Phụ thuộc business logic | Cần batch/checksum/idempotency |

### 40.1. Khi dùng batch

Ứng dụng đã có objects rõ type, cần upsert từng row với `ON CONFLICT`, hoặc cần báo lỗi riêng theo record.

### 40.2. Khi dùng COPY

Nguồn là file lớn/stream chuẩn, cần throughput cao và có thể chèn vào staging trước khi merge.

### 40.3. Không đánh giá chỉ theo rows/s

Cần tính cả parsing, validation, dead-letter file, commit, indexes, retry, kiểm toán, vận hành và độ phức tạp hệ thống.

## 41. COPY và pg_dump/pg_restore

`COPY` và `pg_dump` có mục đích khác nhau.

### 41.1. COPY

Phù hợp di chuyển **dữ liệu bảng hoặc kết quả query** ở format như CSV/TEXT/BINARY theo phạm vi chỉ định.

### 41.2. pg_dump

Xuất logic database, có khả năng bao gồm schema, data, privileges và object definitions theo chế độ backup. Nhiều chế độ dump sử dụng COPY để biểu diễn data bên trong dump.

### 41.3. pg_restore

Dùng để phục hồi những định dạng archive dump phù hợp. Không dùng `pg_restore` để nạp trực tiếp một CSV bình thường rồi mong nó tự tạo đúng schema.

### 41.4. Khi chọn backup/restore

Nếu mục tiêu là backup toàn database, khôi phục schema, indexes và dependencies, dùng chiến lược backup phù hợp (pg_dump/pg_restore hoặc physical backups). COPY CSV không phải bản sao lưu đầy đủ database.

## 42. Xuất CSV an toàn cho người dùng spreadsheet

Một file CSV thường được mở bằng Excel/LibreOffice hoặc dịch vụ BI. Điều này tạo rủi ro khác SQL injection.

### 42.1. CSV formula injection

Nếu một trường text không tin cậy bắt đầu bằng ký tự mà ứng dụng spreadsheet coi là công thức, chẳng hạn `=`, `+`, `-` hoặc `@` theo ngữ cảnh, phần mềm tiêu thụ có thể diễn giải nó như formula.

### 42.2. PostgreSQL COPY không tự chống công thức độc hại

`FORMAT csv` escape dấu phẩy/quote theo CSV syntax, nhưng điều đó không đồng nghĩa nội dung **an toàn khi một spreadsheet diễn giải**.

### 42.3. Phải xác định consumer

Nếu export dành cho machine-to-machine CSV, tự động thêm prefix vào mọi chuỗi bắt đầu bằng `=` có thể làm sai dữ liệu thật. Nếu export dành cho spreadsheet, cần chính sách escaping/sanitization theo consumer và test cách file được mở.

### 42.4. Bảo vệ dữ liệu nhạy cảm

CSV thường không có encryption-at-rest hay quyền theo hàng như database. Export PII cần review các cột được phép, masking, quyền file, nơi nhận và hạn lưu trữ.

## 43. Tự động hóa psql \copy trong script

Psql có thể chạy một file script chứa SQL và meta-commands:

~~~text
\set ON_ERROR_STOP on
BEGIN;
TRUNCATE import_lab.product_stage;
\copy import_lab.product_stage (sku, product_name, unit_price_text, stock_text) FROM '/home/dev/import/products.csv' WITH (FORMAT csv, HEADER true)
-- Các câu kiểm tra/merge thực tế sẽ được viết tiếp tại đây.
COMMIT;
~~~

### 43.1. ON_ERROR_STOP

Psql có thể dừng thực thi script khi gặp lỗi SQL/psql được xử lý theo thiết lập, giúp automation không chạy tiếp và báo thành công giả.

### 43.2. Exit code

Khi gọi psql từ CI/job runner, cần kiểm tra process exit code, không chỉ log dòng cuối có chữ `COMMIT`.

### 43.3. \copy có parser đặc biệt

Meta-command `\copy` không trải qua đầy đủ cơ chế variable interpolation thường dùng ở nhiều meta-commands psql; do đó, không mặc nhiên tin `:file_path` hay việc ghép chuỗi giống SQL sẽ hoạt động. Nếu cần đường dẫn động, cân nhắc cách truyền input/STDIN đã kiểm thử, script generation có kiểm soát hoặc client API.

### 43.4. Không nối raw shell input vào command

File path đến từ user cần được validate/quote đúng ở tầng shell và psql. Đừng tạo cả một `\copy ... PROGRAM ...` dựa trên string thiếu kiểm soát.

### 43.5. Không quản lý secret bằng script plaintext

Dùng secret injection, `.pgpass` với permissions phù hợp hoặc giải pháp tổ chức, tránh commit password vào script import.

## 44. Lỗi thường gặp: file không tồn tại

### 44.1. SQL COPY server file

Thông báo dạng:

~~~text
could not open file "...": No such file or directory
~~~

Kiểm tra **máy database**, container mount và path mà backend thực sự thấy.

### 44.2. Psql \copy client file

Psql báo không mở được file vì path không tồn tại trên **máy chạy psql**, không nhất thiết là server.

### 44.3. Đừng copy file vào server chỉ để “sửa nhanh”

Nếu yêu cầu ứng dụng chỉ upload CSV từ laptop, chuyển sang `\copy` thường rõ ràng và an toàn hơn so với tạo một kênh upload tùy ý vào máy database.

### 44.4. Path chứa spaces

Đặt đường dẫn theo cú pháp quote được hỗ trợ và đảm bảo filesystem đúng. Chú ý sự khác nhau giữa quote trong shell, SQL và psql meta-command.

## 45. Lỗi permission denied

### 45.1. SQL COPY FROM '/server/file'

Thiếu database role đọc server files hoặc OS postgres user không đọc được file.

### 45.2. SQL COPY TO '/server/file'

Thiếu database role ghi server files, thư mục đích không ghi được hoặc file đã tồn tại.

### 45.3. \copy FROM '/client/file'

User chạy psql không đọc được file local hoặc database role thiếu `INSERT`.

### 45.4. \copy TO '/client/file'

User chạy psql không ghi được thư mục local hoặc database role thiếu `SELECT`.

### 45.5. Đừng cấp superuser để sửa permission

Hãy xác định đúng **lớp quyền** đang thiếu. Thường chỉ cần cấu hình quyền file local phù hợp hoặc `GRANT INSERT/SELECT`, không cần đặc quyền truy cập file server.

## 46. Lỗi malformed CSV hoặc sai số cột

### 46.1. Missing data for column

Một dòng có ít trường hơn danh sách cột cần nhập, hoặc quoting làm parser hiểu thiếu delimiter.

### 46.2. Extra data after last expected column

Một dòng có nhiều trường hơn dự kiến, thường do dấu phẩy trong nội dung không được quote.

### 46.3. Unterminated CSV quoted field

Một giá trị bắt đầu dấu quote nhưng không kết thúc đúng, hoặc file bị cắt/truncated.

### 46.4. Dấu quote trong dữ liệu

Đúng CSV mặc định:

~~~csv
MS-02,"Chuột ""siêu nhẹ""",299000.00,15
~~~

Sai nếu chỉ viết:

~~~csv
MS-02,"Chuột "siêu nhẹ"",299000.00,15
~~~

### 46.5. Line number có thể khó đọc với multiline fields

Nếu một CSV field chứa newline, “dòng vật lý” và “bản ghi CSV” khác nhau. Dùng parser CSV đúng chuẩn và báo vị trí lỗi có ngữ cảnh.

## 47. Lỗi dữ liệu không đúng kiểu

### 47.1. Invalid input syntax

~~~text
invalid input syntax for type numeric: "one hundred"
~~~

đến từ cast CSV vào cột numeric; staging text giúp giữ raw value để kiểm tra.

### 47.2. Out of range

`integer` hoặc `numeric(14,2)` có giới hạn. Một file có số cực lớn có thể vượt phạm vi ngay cả khi chuỗi chỉ gồm chữ số.

### 47.3. Date/time parsing

Ngày/tháng sai format hoặc timezone không rõ dẫn tới lỗi hoặc hiểu khác mong muốn. Chuẩn hóa sang ISO 8601 và quy định time zone.

### 47.4. Encoding

Thông báo invalid byte sequence gợi ý vấn đề file encoding hoặc nội dung chứa byte không hợp lệ cho text encoding đã chọn.

### 47.5. NULL và NOT NULL

CSV unquoted empty bị hiểu là SQL NULL có thể gây NOT NULL violation, ngay cả khi người tạo file tưởng đó là chuỗi rỗng.

## 48. Những lỗi thiết kế cần tránh

### Lỗi 1. Nghĩ COPY SQL đọc file trên laptop

`COPY FROM '/path'` mở file phía database server.

### Lỗi 2. Nghĩ \copy là SQL PostgreSQL

`\copy` chỉ là meta-command của psql; JDBC không hiểu trực tiếp.

### Lỗi 3. Chạy psql trong container nhưng dùng path laptop

Psql client đang chạy **trong container**, nên \copy mở path container.

### Lỗi 4. Cấp pg_read_server_files cho app import

Quyền này cho phép đọc server files rất rộng. Dùng client-side COPY STDIN nếu phù hợp.

### Lỗi 5. Cấp pg_execute_server_program cho job thường

Có thể dẫn đến OS command execution với quyền postgres service account. Không cấp cho user ứng dụng chỉ cần nhập CSV.

### Lỗi 6. Không nêu danh sách cột

Thêm cột trong schema làm file nhập lệch vị trí và có thể phá dữ liệu.

### Lỗi 7. Tin HEADER true sẽ tự ghép cột theo tên

Chế độ cơ bản bỏ dòng header; thứ tự cột được xác định bởi câu COPY/danh sách cột.

### Lỗi 8. Nhầm SQL NULL với chuỗi rỗng

CSV quoted/unquoted empty có ý nghĩa khác với cấu hình NULL mặc định.

### Lỗi 9. Import file UTF-16 như CSV UTF-8

Encoding sai gây lỗi ký tự hoặc data corruption.

### Lỗi 10. Tách CSV bằng split(",")

Dấu phẩy trong quoted field không phải delimiter ngoài; còn có quote escaping và multiline values.

### Lỗi 11. COPY thẳng dữ liệu không tin cậy vào bảng chính

Thiếu validation/quarantine và khó báo lỗi theo dòng. Staging thường hữu ích.

### Lỗi 12. Bỏ hàng lỗi âm thầm

Import chỉ các hàng “match regex” mà không báo số hàng bị loại có thể tạo kết quả thiếu.

### Lỗi 13. Không kiểm tra duplicate sau normalize

`kb-01` và `KB-01` có thể đụng UNIQUE khi merge.

### Lỗi 14. Dùng ON CONFLICT DO UPDATE khi cùng batch trùng target

Có thể phát sinh lỗi vì một INSERT không được tác động cùng target row nhiều lần theo ngữ nghĩa UPSERT.

### Lỗi 15. Chia nhiều batches nhưng báo toàn file atomic

Commit từng batch làm một phần file có thể đã tồn tại khi batch cuối lỗi.

### Lỗi 16. Nghĩ COPY thất bại không tạo chi phí storage

Tuple đã ghi rồi thất bại có thể cần VACUUM để reclaim; WAL/I/O không biến mất.

### Lỗi 17. Bỏ qua index/trigger/constraint cost

COPY không bypass toàn bộ cơ chế bảo vệ bảng và có thể chậm do trigger row-level.

### Lỗi 18. Dựa vào bytes_total=0 để kết luận file rỗng

Tiến độ theo nguồn stream có thể không biết tổng kích thước.

### Lỗi 19. Không ANALYZE sau import lớn

Planner có thể dùng statistics cũ và tạo kế hoạch truy vấn kém phù hợp.

### Lỗi 20. COPY TO file server mà tưởng file ở local

Không tìm được CSV ở laptop vì file thực nằm trên host/container database.

### Lỗi 21. Thiết kế export không ORDER BY mà đòi thứ tự ổn định

Không có cam kết về thứ tự nghiệp vụ nếu không yêu cầu rõ trong query.

### Lỗi 22. Xuất PII rồi để file không bảo vệ

File CSV bên ngoài DB không tự được quản lý theo RLS/GRANT của PostgreSQL.

### Lỗi 23. Tin FORMAT csv chống formula injection

CSV escaping không ngăn spreadsheet giải thích chuỗi thành công thức.

### Lỗi 24. Dùng COPY CSV thay backup toàn database

CSV không có schema, indexes, roles và toàn bộ dependencies như một backup hợp lệ.

### Lỗi 25. Sử dụng JDBC executeQuery cho \copy

JDBC chỉ hiểu SQL và COPY protocol qua API phù hợp, không thực thi psql meta-command.

### Lỗi 26. Load toàn bộ file CSV vào String trước CopyManager

Tốn nhiều heap; hãy stream từ Reader/InputStream.

### Lỗi 27. Export thẳng vào file cuối rồi cho người dùng đọc khi chưa xong

Nếu copyOut lỗi giữa chừng, file bị cắt. Dùng file tạm, kiểm tra rồi publish/rename.

### Lỗi 28. Quên rollback sau COPY lỗi trong transaction

Connection có thể ở trạng thái aborted, những câu SQL sau lỗi cho đến khi rollback.

### Lỗi 29. Đưa server file path do user nhập trực tiếp vào PROGRAM

Có thể làm lộ dữ liệu hoặc command injection; chỉ dùng workflow file/command được kiểm soát.

### Lỗi 30. Chạy import đồng thời vào cùng staging không chia batch

Hai jobs có thể trộn dữ liệu, kiểm tra duplicate nhầm hoặc promote file của nhau.

## 49. Bài tập thực hành

Các bài dựa trên schema `import_lab` và file `products.csv` trong bài. Không chạy lệnh ghi server file hoặc `PROGRAM` trên production khi chưa được cấp quyền/quy trình chính thức.

### Bài 1. Vị trí file

Khi chạy `COPY ... FROM '/home/an/a.csv'` qua psql từ laptop, máy nào tìm file?

### Bài 2. \copy

Khi chạy `\copy ... FROM '/home/an/a.csv'` trong psql trên laptop, máy nào mở file?

### Bài 3. Container

Nếu chạy `docker exec ... psql`, `\copy` nhìn thấy file trên host hay container?

### Bài 4. JDBC

Tại sao `PreparedStatement.execute("\\copy ...")` không phải cách nhập file đúng?

### Bài 5. Role quyền bảng

Database role cần quyền gì để nhập vào staging bằng `\copy FROM`?

### Bài 6. Quyền server files

Nếu phải dùng SQL COPY FROM đường dẫn file server, cần quyền đặc biệt nào theo PostgreSQL?

### Bài 7. COPY TO server

Ai ghi file `'/var/lib/postgresql/export/products.csv'` trong SQL `COPY TO`?

### Bài 8. \copy TO client

Viết meta-command psql xuất các cột `sku,product_name,unit_price,stock` ra file client `'/home/dev/export/out.csv'` với CSV header.

### Bài 9. Chọn cột

Vì sao phải chỉ định danh sách cột khi file không có `product_id` và `imported_at`?

### Bài 10. TEXT và CSV

Khác biệt cơ bản về delimiter/NULL/escaping giữa `FORMAT text` và `FORMAT csv`?

### Bài 11. CSV dấu phẩy

Viết giá trị tên `Bàn phím, cơ` trong một field CSV.

### Bài 12. CSV dấu quote

Viết field CSV chứa đúng chuỗi `Chuột "siêu nhẹ"`.

### Bài 13. HEADER true

Nếu file không có header nhưng COPY đặt `HEADER true`, hàng đầu được xử lý thế nào?

### Bài 14. NULL

Trong CSV mặc định, unquoted empty và quoted empty (`""`) tương đương nhau không?

### Bài 15. ENCODING

Vì sao file chứa tiếng Việt UTF-16 không thể mặc nhiên nhập đúng với `ENCODING 'UTF8'`?

### Bài 16. Query export

Viết `COPY (SELECT ...) TO STDOUT` xuất các sản phẩm có tồn kho lớn hơn 0, sắp theo SKU và có header.

### Bài 17. STDIN

`COPY FROM STDIN` lấy dữ liệu từ file hệ điều hành PostgreSQL hay luồng client?

### Bài 18. \.

Trong psql khi nhập tương tác qua `COPY ... FROM STDIN`, dấu `\.` có ý nghĩa gì?

### Bài 19. CSV parser

Tại sao không dùng `String.split(",")` để xử lý mọi CSV?

### Bài 20. Staging

Nêu ba lợi ích của việc nhập vào bảng staging text trước khi ép kiểu.

### Bài 21. SKU kiểm tra

Viết SQL tìm những SKU không khớp `^[A-Z0-9-]{3,24}$` sau khi upper/btrim.

### Bài 22. Duplicate

Viết SQL tìm những SKU trùng sau `upper(btrim(sku))` trong staging.

### Bài 23. Promote

Vì sao phải kiểm tra dữ liệu trước `INSERT ... ON CONFLICT DO UPDATE`?

### Bài 24. Transaction

Nếu COPY FROM trong transaction có lỗi và chưa commit, ứng dụng cần làm gì?

### Bài 25. COPY lỗi nửa file

Vì sao một COPY thất bại muộn vẫn có thể tốn dung lượng bảng/WAL?

### Bài 26. Constraints

COPY FROM có bỏ qua `CHECK`, `UNIQUE` và trigger trên bảng không?

### Bài 27. Rules

COPY FROM có cùng behavior với INSERT đối với rewrite rules không?

### Bài 28. RLS

Vì sao nên thận trọng với COPY FROM trên bảng đang dùng RLS?

### Bài 29. COPY PROGRAM

`COPY TO PROGRAM 'gzip ...'` chạy ở máy nào và vì sao cần đặc quyền mạnh?

### Bài 30. \copy PROGRAM

`\copy TO PROGRAM 'gzip ...'` chạy ở máy nào?

### Bài 31. Security

Vì sao không cấp `pg_execute_server_program` cho app chỉ có nhu cầu nhập CSV?

### Bài 32. pg_stat_progress_copy

Viết query hiển thị `pid,command,type,bytes_processed,bytes_total,tuples_processed`.

### Bài 33. bytes_total

Nếu `bytes_total=0` trong COPY FROM STDIN, có thể kết luận file rỗng không?

### Bài 34. JDBC CopyManager

Mô tả cách PGJDBC nhập file local vào PostgreSQL mà không dùng psql.

### Bài 35. CopyManager transaction

Để import/validate/merge cùng nguyên tử, cần dùng mấy Connection và khi nào commit?

### Bài 36. Export failure

Để người dùng không nhận file CSV dang dở, nên làm gì trước khi publish file?

### Bài 37. Statistics

Sau một bulk import lớn làm thay đổi phân bố dữ liệu, lệnh PostgreSQL nào cập nhật planner statistics?

### Bài 38. Backup

Khi cần sao lưu cả schema và data, COPY CSV có thay thế đầy đủ pg_dump/pg_restore không?

### Bài 39. CSV injection

Tại sao xuất CSV cho Excel cần đánh giá nội dung bắt đầu bằng dấu `=`, `+`, `-`, `@`?

### Bài 40. Chọn phương án

Chọn giữa `COPY server file`, `psql \copy`, `PGJDBC CopyManager` và `pg_dump` cho bốn tình huống: file nằm server DB; file nằm laptop; Java service nhận stream; sao lưu database logic.

## 50. Lời giải tham khảo

### Bài 1–3. Nơi mở file

`COPY FROM 'file'`: PostgreSQL backend mở file tại server. `\copy FROM 'file'`: psql mở file tại client. Nếu psql chạy qua `docker exec`, client chính là tiến trình psql **trong container**, không phải host ngoài container.

### Bài 4. JDBC

`\copy` không phải SQL PostgreSQL. Java nên dùng SQL `COPY ... FROM STDIN` cùng PGJDBC `CopyManager`, hoặc xây pipeline JDBC batch.

### Bài 5–7. Quyền

`\copy FROM` cần `INSERT` phù hợp trên bảng và OS read permission của psql. SQL `COPY FROM server-file` cần quyền đặc biệt như `pg_read_server_files` hoặc superuser và OS read permission. `COPY TO server-file` do PostgreSQL backend ghi, cần quyền như `pg_write_server_files`/superuser cùng quyền OS ghi.

### Bài 8. \copy TO

~~~text
\copy import_lab.products (sku, product_name, unit_price, stock) TO '/home/dev/export/out.csv' WITH (FORMAT csv, HEADER true)
~~~

### Bài 9. Danh sách cột

File chỉ có bốn cột; chỉ định danh sách tránh lệch thứ tự schema và để identity/default columns như `product_id`/`imported_at` được xử lý bởi default của bảng tương ứng.

### Bài 10. Format

`FORMAT text` thường dùng TAB, escape kiểu PostgreSQL và ký hiệu NULL `\N`. `FORMAT csv` thường dùng dấu phẩy và quote kép; unquoted empty mặc định có thể biểu diễn SQL NULL, quoted empty chuỗi rỗng.

### Bài 11–12. Quoting

~~~csv
"Bàn phím, cơ"
"Chuột ""siêu nhẹ"""
~~~

### Bài 13. Header

Nếu `HEADER true`, dòng dữ liệu đầu sẽ bị đọc như header rồi bị bỏ qua, dẫn đến thiếu một bản ghi.

### Bài 14. SQL NULL

Không. Với CSV mặc định, unquoted empty là SQL NULL còn quoted empty là chuỗi rỗng text, trừ khi có cấu hình NULL/FORCE_* thay đổi.

### Bài 15. Encoding

UTF-16 và UTF-8 là các byte encodings khác nhau; PostgreSQL không tự chuyển file UTF-16 chỉ vì đã đặt `ENCODING 'UTF8'`. Cần chuyển mã file hoặc chọn cách đọc phù hợp.

### Bài 16. Query export

~~~sql
COPY (
    SELECT sku, product_name, unit_price, stock
    FROM import_lab.products
    WHERE stock > 0
    ORDER BY sku
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

### Bài 17–18. STDIN

`STDIN` là COPY data từ client qua kết nối PostgreSQL; trong psql interactive/script, `\.` đánh dấu kết thúc phần dữ liệu COPY.

### Bài 19. CSV parser

CSV cho phép delimiter, quote và newline nằm bên trong quoted field; `split(",")` không phân biệt comma dữ liệu với comma phân tách.

### Bài 20. Staging

Giúp (1) bảo toàn raw values khi cột numeric/date sai; (2) validate và báo lỗi theo hàng; (3) deduplicate/normalize; (4) quản lý batch/retry; (5) chỉ promote dữ liệu đã phê duyệt.

### Bài 21. SKU validation

~~~sql
SELECT stage_id, sku
FROM import_lab.product_stage
WHERE sku IS NULL
   OR upper(btrim(sku)) !~ '^[A-Z0-9-]{3,24}$';
~~~

### Bài 22. Dedupe

~~~sql
SELECT upper(btrim(sku)) AS sku, count(*)
FROM import_lab.product_stage
GROUP BY upper(btrim(sku))
HAVING count(*) > 1;
~~~

### Bài 23. Promote

Phải phát hiện SKU trùng sau normalize, số tiền/tồn kho sai định dạng, NULL/blank và business invariants. Nếu không, merge có thể lỗi toàn batch hoặc cập nhật sai.

### Bài 24–25. COPY lỗi

Sau SQL lỗi trong transaction, rollback hoặc rollback về savepoint phù hợp. COPY thất bại muộn có thể tạo dead tuples cần VACUUM, vẫn tiêu thụ I/O/WAL.

### Bài 26–28. Constraints/rules/RLS

`COPY FROM` áp constraints/triggers tương ứng, không bỏ qua chúng. Nó không gọi rewrite rules giống INSERT. Với RLS, phải xem giới hạn COPY FROM và sử dụng đường nhập phù hợp; không tự tắt RLS để vượt quyền.

### Bài 29–31. PROGRAM

SQL `COPY ... PROGRAM` chạy command ở server với quyền OS postgres service và đòi đặc quyền mạnh. `\copy ... PROGRAM` chạy ở máy psql client. Không cấp `pg_execute_server_program` cho app import vì quyền ấy có thể cho phép chạy chương trình OS trên database server.

### Bài 32. Progress

~~~sql
SELECT
    pid,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed
FROM pg_stat_progress_copy;
~~~

### Bài 33. Unknown total

Không. Với nguồn stream, PostgreSQL có thể không biết tổng số bytes nên `bytes_total=0` dù đang xử lý nhiều dữ liệu.

### Bài 34. Java COPY

Mở local file bằng Reader/InputStream, lấy `PGConnection.getCopyAPI()` từ JDBC connection, gọi `copyIn("COPY ... FROM STDIN ...", reader)` và xử lý SQL/rollback/commit trên connection ấy.

### Bài 35. Một connection

Dùng một `Connection` với `setAutoCommit(false)`, import bằng CopyManager, validate/merge trên cùng session, chỉ commit khi toàn bộ bước bắt buộc thành công; nếu lỗi thì rollback.

### Bài 36. Export temp file

Ghi vào temporary file ở client, chờ copyOut hoàn thành và kiểm tra các điều kiện cần thiết, rồi rename/publish theo quy trình filesystem thích hợp. Khi lỗi, không công bố file dang dở.

### Bài 37. ANALYZE

~~~sql
ANALYZE import_lab.products;
~~~

### Bài 38. Backup

Không. CSV chỉ chứa data đã chọn; `pg_dump/pg_restore` và chiến lược backup phù hợp quản lý schema, objects, data và metadata theo mục tiêu khôi phục.

### Bài 39. Formula injection

Một spreadsheet có thể diễn giải chuỗi bắt đầu bằng dấu công thức thành expression, dù CSV quoting đúng. Cần export policy phù hợp consumer, không chỉ escape dấu phẩy.

### Bài 40. Chọn đường truyền

| Tình huống | Lựa chọn |
| --- | --- |
| File thực sự nằm trên database server và role được phê duyệt | SQL `COPY FROM server-file` |
| File nằm trên laptop đang chạy psql | `\copy FROM client-file` |
| Java service có Reader/InputStream | PGJDBC `CopyManager` + `COPY FROM STDIN` |
| Backup logic cả schema/data | `pg_dump`, phục hồi bằng phương án tương ứng |

## 51. Bảng tra cứu nhanh

| Việc cần làm | Cú pháp/hướng xử lý |
| --- | --- |
| Server đọc file | `COPY table FROM '/server/path'` |
| Server ghi file | `COPY table TO '/server/path'` |
| Client psql đọc file | `\copy table FROM '/client/path'` |
| Client psql ghi file | `\copy table TO '/client/path'` |
| Client stream vào server | `COPY table FROM STDIN` |
| Server stream ra client | `COPY table TO STDOUT` |
| Xuất kết quả SELECT | `COPY (SELECT ...) TO STDOUT` |
| CSV có header | `WITH (FORMAT csv, HEADER true)` |
| CSV dùng semicolon | `DELIMITER ';'` |
| CSV quoted field | `QUOTE '"'` |
| Escape dấu quote | `ESCAPE '"'` |
| Kiểm soát NULL marker | `NULL '...'` |
| Giữ unquoted empty là text | `FORCE_NOT_NULL (column)` khi phù hợp |
| Ép quoted null marker thành NULL | `FORCE_NULL (column)` khi phù hợp |
| Encoding UTF-8 | `ENCODING 'UTF8'` theo phiên bản |
| Cột identity tự sinh | Lược cột đó khỏi COPY column list |
| Server đọc file có quyền | `pg_read_server_files`/superuser + OS quyền |
| Server ghi file có quyền | `pg_write_server_files`/superuser + OS quyền |
| Server chạy PROGRAM | `pg_execute_server_program`/superuser |
| Client chạy PROGRAM | `\copy ... PROGRAM` tại máy psql |
| Kiểm tra file trước nhập bảng chính | Staging text + validation |
| Merge khi có SKU trùng bảng đích | `INSERT ... ON CONFLICT` sau dedupe batch |
| Rollback import | `BEGIN`/`ROLLBACK` hoặc transaction JDBC |
| Theo dõi tiến độ COPY | `pg_stat_progress_copy` |
| Theo dõi session và chờ | `pg_stat_activity`/`pg_locks` |
| Cập nhật statistics | `ANALYZE table` |
| Java import stream | PGJDBC `CopyManager.copyIn` |
| Java export stream | PGJDBC `CopyManager.copyOut` |
| Sao lưu database logic | `pg_dump`/`pg_restore` |

## 52. Checklist triển khai import/export production

1. **Xác định file nằm trên máy nào**: laptop, app pod, ETL worker, database server hay object storage?
2. PostgreSQL server có thực sự nhìn thấy path nếu dùng server-side COPY?
3. Có tránh cấp đặc quyền server-file cho role ứng dụng không cần thiết?
4. Có `INSERT`/`SELECT` đúng bảng/cột, schema `USAGE` phù hợp?
5. File là CSV, text hay binary? Hợp đồng format đã chốt chưa?
6. Header có tồn tại, thứ tự cột có khớp, column list đã ghi rõ chưa?
7. Delimiter/quote/escape có đúng format nguồn?
8. Đã thống nhất SQL NULL, quoted/unquoted empty và missing values?
9. File có encoding đúng và có xử lý BOM không?
10. Ngày giờ có chuẩn ISO/time zone rõ, số tiền có quy tắc decimal rõ?
11. Có phân tách staging khỏi bảng chính khi file chưa đáng tin?
12. Có lưu raw values và lỗi theo stage_id/batch_id?
13. Có kiểm tra duplicate keys sau normalize?
14. Có chính sách reject all/quarantine/partial success minh bạch?
15. Có định nghĩa idempotency khi cùng file/job được chạy lại?
16. Có transaction boundaries và rollback khi bất kỳ bước bắt buộc lỗi?
17. Có kiểm soát psql `ON_ERROR_STOP` và process exit code?
18. Batch size có phù hợp WAL/locks/replication và yêu cầu atomicity?
19. Có bảo vệ triggers/constraints/RLS thay vì tắt tùy tiện?
20. Có xem xét index overhead và `ANALYZE` sau import lớn?
21. Có theo dõi `pg_stat_progress_copy` và connection state?
22. Có tránh shell injection khi dùng `COPY PROGRAM` hoặc `\copy PROGRAM`?
23. Có TLS/SSL policy phù hợp trên đoạn client–server?
24. Export có giới hạn cột/rows nhạy cảm, PII và tenant permission?
25. CSV cho spreadsheet có đánh giá formula injection không?
26. File export có temp/publish flow để tránh công bố file cắt dở?
27. Có retention/disk quota/checksum cho files và batch records?
28. Connection/app worker có timeout và retry policy đúng?
29. Có test file trống, header-only, multiline CSV, dấu quote và UTF-8?
30. Có runbook xử lý file missing, permission, invalid input và disk full?

## 53. Tổng kết

Sự khác nhau quan trọng nhất trong PostgreSQL import/export là **ai mở file**:

- **SQL `COPY ... FROM/TO 'path'`:** backend PostgreSQL mở file trên **máy chủ** bằng quyền hệ điều hành của dịch vụ database. Cần thêm quyền truy cập server file rất nhạy cảm ngoài quyền bảng.
- **`psql \copy ... FROM/TO 'path'`:** tiến trình **psql trên máy khách** mở file, truyền dữ liệu qua `COPY FROM STDIN` hoặc `COPY TO STDOUT`. Database role vẫn phải có quyền bảng, nhưng không phải nhận quyền đọc/ghi file tùy ý trên máy server.
- **`COPY FROM STDIN`/`TO STDOUT`:** là giao thức truyền dữ liệu phía SQL/PostgreSQL cho clients; PGJDBC `CopyManager` dùng cơ chế này để stream file/Reader của Java mà không cần chạy meta-command `\copy`.

Trong thực hành, hãy luôn chỉ rõ **danh sách cột**, chọn đúng `FORMAT`/`HEADER`/`NULL`/`ENCODING`, xử lý quoted CSV theo parser đúng và ưu tiên **staging + validation + transaction** khi nguồn dữ liệu chưa đáng tin. Với dữ liệu lớn, đánh giá WAL, locks, triggers, indexes, disk, replication lag và khả năng resume; `COPY` nhanh nhưng không miễn trừ quy tắc toàn vẹn của PostgreSQL.

Một câu hỏi quyết định công cụ rất hữu ích là: **“File nằm ở đâu, ai được phép mở nó, và dữ liệu cần qua những kiểm tra nào trước khi commit?”**. Trả lời đúng ba phần này sẽ giúp chọn `COPY`, `\copy` hay CopyManager an toàn, nhanh và vận hành được.
