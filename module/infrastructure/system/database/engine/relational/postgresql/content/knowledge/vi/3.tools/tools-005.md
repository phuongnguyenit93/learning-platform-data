# Thao tác nhập xuất phía máy khách bằng lệnh \copy trong PostgreSQL

Trong quá trình phát triển và vận hành PostgreSQL, dữ liệu thường phải được chuyển qua lại giữa bảng trong database và tệp ở máy người dùng: nhập danh mục sản phẩm từ CSV, nạp dữ liệu cũ trước khi chuyển đổi, xuất báo cáo đối soát, hoặc bàn giao dữ liệu cho một hệ thống phân tích. PostgreSQL có SQL `COPY` để truyền dữ liệu số lượng lớn. Riêng chương trình dòng lệnh **`psql`** cung cấp **meta-command `\copy`**, giúp đọc hoặc ghi tệp **tại phía máy đang chạy `psql`**.

Điểm khác biệt này quyết định nơi đặt file, quyền hệ điều hành cần có, cách kết nối tới server từ xa và cách thiết kế script. Nếu database chạy trên một máy chủ nhưng `psql` chạy trên laptop của bạn, câu `\copy ... FROM 'products.csv'` sẽ tìm file trên **laptop**, không phải tìm file trong thư mục dữ liệu của máy chủ PostgreSQL.

Bài này hướng dẫn cú pháp `\copy FROM/TO`, luồng dữ liệu client/server, nhập và xuất CSV, các tùy chọn định dạng, xử lý `NULL`, encoding, quyền truy cập, transaction, staging và lỗi thường gặp.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

- Phân biệt rõ SQL `COPY` của PostgreSQL với meta-command `\copy` của `psql`.
- Nhập CSV từ file local vào một bảng, chỉ định cột, header và encoding.
- Xuất toàn bộ bảng hoặc kết quả truy vấn `SELECT` ra CSV local.
- Hiểu các tùy chọn `FORMAT`, `HEADER`, `DELIMITER`, `QUOTE`, `ESCAPE`, `NULL`.
- Xác định chính xác đường dẫn file và danh tính hệ điều hành đang thao tác với file.
- Phân biệt lỗi quyền database với lỗi đọc/ghi file phía client.
- Sử dụng transaction và staging table khi dữ liệu nhập cần kiểm tra.
- Tránh nhập trùng, lệch cột, lỗi kiểu dữ liệu và rò rỉ dữ liệu nhạy cảm.

Các ví dụ hướng tới PostgreSQL và `psql` hiện đại. Chỉ chạy lệnh tạo hoặc xóa bảng trên database **thực hành riêng**.

---

## 2. `\copy` khác `COPY` ở điểm nào?

### 2.1. SQL `COPY` chạy phía server

PostgreSQL có câu SQL:

```sql
COPY public.products
FROM '/var/lib/postgresql/import/products.csv'
WITH (FORMAT csv, HEADER true);
```

Khi dùng tên đường dẫn trên SQL `COPY`, file được hiểu là file trong filesystem của **máy chạy tiến trình PostgreSQL server**. Server phải có quyền đọc file (hoặc ghi file với `COPY TO`); tài khoản database cũng có thể cần đặc quyền đọc/ghi file server thích hợp.

Tệp nằm trên laptop sẽ không trở thành file của server chỉ vì bạn kết nối tới database từ laptop. Đường dẫn `/var/lib/postgresql/import/products.csv` cũng không phải đường dẫn thư mục local của người đang gõ lệnh, trừ khi client và server thực sự chạy trên cùng máy.

### 2.2. `\copy` chạy phía máy khách

Trong chương trình `psql`, dùng:

```text
\copy public.products FROM '/home/student/products.csv' WITH (FORMAT csv, HEADER true)
```

`psql` đọc file tại `/home/student/products.csv` **trên máy đang chạy psql**, rồi truyền dữ liệu qua kết nối PostgreSQL. Ở phía server, cơ chế underlying tương ứng là `COPY ... FROM STDIN`.

Chiều xuất tương tự: `\copy ... TO 'output.csv'` yêu cầu server gửi dữ liệu theo `COPY ... TO STDOUT` để `psql` ghi ra file local.

```text
                   NHẬP: \copy ... FROM 'products.csv'

       Máy chạy psql                         PostgreSQL server
  +--------------------------+          +------------------------------+
  | products.csv             |          | Bảng dữ liệu                 |
  |       |                  |          |      ^                       |
  |       v                  |          |      |                       |
  | psql đọc file local -----+--------->| COPY ... FROM STDIN          |
  +--------------------------+  mạng    +------------------------------+


                    XUẤT: \copy ... TO 'export.csv'

       Máy chạy psql                         PostgreSQL server
  +--------------------------+          +------------------------------+
  | export.csv               |          | Bảng / SELECT query          |
  |       ^                  |          |      |                       |
  |       |                  |          |      v                       |
  | psql ghi file local <----+----------+ COPY ... TO STDOUT            |
  +--------------------------+  mạng    +------------------------------+
```

| Khía cạnh | SQL `COPY` với tên file | `\copy` trong `psql` |
| --- | --- | --- |
| Nơi thực thi phần xử lý file | PostgreSQL server | Chương trình `psql` |
| Đường dẫn là filesystem của | Máy server | Máy client chạy `psql` |
| Quyền file OS | Tài khoản hệ điều hành chạy PostgreSQL | Tài khoản OS chạy `psql` |
| Quyền bảng PostgreSQL | Vẫn cần | Vẫn cần |
| Quyền truy cập file tùy ý trên server | Có thể cần đặc quyền bổ sung | Không cần đặc quyền file server chỉ để đọc/ghi file client |
| Truyền nội dung CSV qua kết nối client/server | Không theo cùng cách khi server tự mở file | Có |
| Khả năng chạy trong SQL editor thuần | SQL chuẩn của PostgreSQL | Không, trừ client có hỗ trợ meta-command |

**Cần nhớ:** `\copy` không phải câu SQL gửi nguyên văn lên server; nó là lệnh điều khiển của `psql`.

### 2.3. `\copy` ở laptop, SSH, Docker và CI

Nơi file thực sự nằm phụ thuộc **nơi tiến trình psql đang chạy**, không phải nơi bạn nhìn thấy cửa sổ terminal.

| Cách chạy `psql` | `\copy FROM 'file.csv'` tìm ở đâu? |
| --- | --- |
| Terminal trên laptop | Filesystem của laptop |
| SSH vào server ứng dụng, sau đó chạy psql | Filesystem của server ứng dụng |
| `docker exec ... psql` | Filesystem của container được exec vào |
| `psql` trong job CI | Filesystem của CI runner |
| `psql` ngay trên host database | Filesystem của host đó, vì client cùng máy với server |

Ví dụ bạn có file `C:/data/products.csv` trên Windows nhưng chạy `psql` **bên trong một container Linux**: lệnh `\copy FROM 'C:/data/products.csv'` không tự tìm được file Windows. Bạn cần mount/copy file vào filesystem mà tiến trình psql thật sự nhìn thấy.

---

## 3. Chuẩn bị bài thực hành

### 3.1. Kết nối PostgreSQL bằng `psql`

Ví dụ chạy từ terminal:

```bash
psql -h localhost -p 5432 -U postgres -d postgres
```

Tài khoản, host và database phải phù hợp với môi trường của bạn. Không ghi mật khẩu thật trực tiếp trên command line hoặc trong script có thể được đưa vào lịch sử shell.

Sau khi vào `psql`:

```sql
SELECT current_database(), current_user, version();
```

Có thể dùng meta-command:

```text
\conninfo
```

Nếu terminal chấp nhận lệnh `\conninfo` và hiển thị thông tin kết nối, bạn đang làm việc với client `psql` thích hợp cho các ví dụ `\copy`.

### 3.2. Tạo bảng mẫu

> **Chỉ dùng trong database lab.** Câu `DROP TABLE IF EXISTS` bên dưới xóa bảng cùng tên và dữ liệu cũ của bảng đó. Không chạy trên production.

```sql
CREATE SCHEMA IF NOT EXISTS client_copy_lab;

DROP TABLE IF EXISTS client_copy_lab.products;
DROP TABLE IF EXISTS client_copy_lab.products_stage;

CREATE TABLE client_copy_lab.products (
    product_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Bảng có các đặc điểm:

- `product_id` là khóa chính.
- `sku` phải có giá trị và không trùng.
- `unit_price` là số thập phân chính xác, không âm.
- `active` nhận giá trị boolean.
- `created_at` có giá trị mặc định từ server, nên **không bắt buộc có trong file CSV** nếu không nhập cột này.

### 3.3. Chuẩn bị file CSV local

Trên máy đang chạy `psql`, tạo file `products.csv` bằng editor hỗ trợ UTF-8:

```csv
product_id,sku,product_name,unit_price,active
1,BOOK-001,"Sách SQL, cơ bản",125000.00,true
2,PEN-002,"Bút ""mực"" xanh",15000.00,true
3,NOTE-003,"Sổ ghi chép",45000.00,false
```

Nội dung này có ba hàng dữ liệu và một dòng header.

Các trường đặc biệt:

- Tên `Sách SQL, cơ bản` chứa dấu phẩy, nên phải bao bằng `"..."`.
- Tên `Bút "mực" xanh` chứa dấu nháy kép, nên phần nháy trong dữ liệu được viết thành `""`.
- `true` và `false` là đầu vào hợp lệ của kiểu PostgreSQL `BOOLEAN`.
- Giá dùng dấu chấm thập phân, không dùng dấu phẩy thập phân tùy locale.
- File phải tồn tại tại phía client trước khi thực hiện lệnh import.

Không cần tạo file `row47.md` hay bất kỳ tệp module nào khác để thực hành. `products.csv` chỉ là ví dụ người học tự tạo trong máy thử nghiệm của họ.

---

## 4. Nhập CSV bằng `\copy ... FROM`

### 4.1. Cú pháp cơ bản

Trong `psql`, chạy **một dòng duy nhất**:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

Lệnh sẽ:

1. Mở `products.csv` ở máy client chạy `psql`.
2. Đọc dòng header và bỏ qua nó vì `HEADER true`.
3. Tách CSV theo quy tắc dấu phân cách và dấu quote.
4. Gửi từng giá trị vào các cột được liệt kê **theo thứ tự**.
5. PostgreSQL chuyển kiểu, kiểm tra constraint và ghi các hàng.
6. Trả về thông tin số hàng được nhập.

Với file mẫu và bảng trống, kết quả thông báo thường là:

```text
COPY 3
```

Kiểm tra bằng SQL:

```sql
SELECT product_id, sku, product_name, unit_price, active, created_at
FROM client_copy_lab.products
ORDER BY product_id;

SELECT COUNT(*) AS row_count
FROM client_copy_lab.products;
```

Số hàng dự kiến là **3**. Giá trị `created_at` được tạo bởi default vì không có trong danh sách cột nhập.

### 4.2. Tại sao phải liệt kê cột?

Không nên mặc định dùng:

```text
\copy client_copy_lab.products FROM 'products.csv' WITH (FORMAT csv, HEADER true)
```

Trong bảng mẫu, CSV chứa 5 trường nhưng bảng có thêm `created_at`. Nếu không liệt kê cột, PostgreSQL có thể mong dữ liệu cho toàn bộ các cột có thể nạp và báo lỗi thiếu trường.

Câu lệnh tường minh:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products.csv' WITH (FORMAT csv, HEADER true)
```

giúp xác định hợp đồng về số lượng và thứ tự trường. Các cột bị bỏ khỏi danh sách có thể nhận default nếu schema cho phép.

### 4.3. Header không tự căn cột theo tên

Giả sử file đổi thành:

```csv
sku,product_id,product_name,unit_price,active
BOOK-001,1,"Sách SQL, cơ bản",125000.00,true
```

Nhưng lệnh `\copy` vẫn dùng cột `(product_id, sku, ...)`: PostgreSQL sẽ cố chuyển `BOOK-001` thành integer cho `product_id`, dẫn tới lỗi.

Với `HEADER true` thông thường, header được **bỏ qua**, không tự ánh xạ tên cột file sang tên cột bảng. Khi file đổi thứ tự, bạn phải sửa danh sách cột hoặc chuẩn hóa file cho khớp. Tùy phiên bản có thể có lựa chọn header matching khác, nhưng không nên phụ thuộc vào nó mà không xác nhận khả năng của server.

### 4.4. `\copy` nhập dữ liệu, không tự UPSERT

Nếu chạy lại cùng file sau khi đã nhập thành công, khóa `product_id` hoặc `sku` có thể bị trùng và PostgreSQL báo `unique_violation`:

```text
ERROR: duplicate key value violates unique constraint ...
```

`\copy ... FROM` không tự thay hàng cũ, không có hành vi “bỏ qua nếu đã tồn tại” mặc định. Khi cần nạp file lặp đi lặp lại, nên dùng staging rồi hợp nhất có kiểm soát bằng `INSERT ... ON CONFLICT` hoặc một quy trình ETL tương đương.

---

## 5. Xuất CSV bằng `\copy ... TO`

### 5.1. Xuất toàn bộ một số cột của bảng

Trong `psql`:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) TO 'products_export.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

Tệp `products_export.csv` được tạo trên **máy chạy psql**. Nếu ghi tên tương đối, vị trí phụ thuộc vào **working directory của tiến trình psql**, không phải thư mục dữ liệu PostgreSQL.

Cột `created_at` không được xuất vì danh sách cột đã bỏ qua nó.

### 5.2. Xuất kết quả SELECT

Nếu chỉ cần hàng `active = true`:

```text
\copy (SELECT sku, product_name, unit_price FROM client_copy_lab.products WHERE active = true ORDER BY sku) TO 'active_products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

File đầu ra chứa header và hai hàng:

```csv
sku,product_name,unit_price
BOOK-001,"Sách SQL, cơ bản",125000.00
PEN-002,"Bút ""mực"" xanh",15000.00
```

Để xuất báo cáo tổng hợp:

```text
\copy (SELECT active, COUNT(*) AS product_count, SUM(unit_price) AS total_unit_price FROM client_copy_lab.products GROUP BY active ORDER BY active DESC) TO 'products_summary.csv' WITH (FORMAT csv, HEADER true)
```

Truy vấn trong ngoặc do PostgreSQL thực thi; psql chỉ nhận kết quả được phát dưới dạng COPY stream và ghi file local.

### 5.3. Xuất ra đầu ra chuẩn

```text
\copy (SELECT sku, unit_price FROM client_copy_lab.products ORDER BY sku) TO STDOUT WITH (FORMAT csv, HEADER true)
```

Câu này gửi CSV ra standard output của psql, hữu ích cho một số pipeline. Với người mới, `TO 'report.csv'` thường dễ kiểm soát file hơn. Khi kết hợp với chuyển hướng stdout của shell, cần tính tới thông báo của client và mã thoát lệnh, tránh làm lẫn dữ liệu CSV với nội dung khác.

### 5.4. Xuất file không tự bảo vệ dữ liệu

Một file CSV được tạo từ `SELECT` có thể chứa thông tin nhạy cảm. `\copy` không tự mã hóa, ẩn danh hoặc kiểm tra rằng người nhận file có quyền dùng các cột đó. Chỉ xuất cột và hàng được phép, bảo vệ thư mục đích và áp dụng chính sách lưu trữ dữ liệu.

---

## 6. Những tùy chọn định dạng quan trọng

Cú pháp CSV thường dùng:

```text
\copy some_table (col1, col2, col3) FROM 'file.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',', QUOTE '"', ESCAPE '"', NULL '')
```

| Tùy chọn | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| `FORMAT csv` | Dữ liệu theo CSV | Dùng cho file có dấu phân cách, quote và các trường chứa ký tự đặc biệt |
| `FORMAT text` | Định dạng text riêng của PostgreSQL COPY | Không đồng nghĩa CSV |
| `HEADER true` | Khi nhập bỏ header; khi xuất ghi tên cột | Không tự map cột theo tên |
| `DELIMITER ','` | Ký tự phân tách các trường | Mặc định CSV thường là dấu phẩy |
| `QUOTE '"'` | Dấu bao trường của CSV | Cho phép dấu phân cách và newline trong trường |
| `ESCAPE '"'` | Cách escape dấu quote | Dấu nháy kép trong trường thường viết `""` |
| `NULL ''` | Biểu diễn giá trị SQL NULL trong CSV | Cần phân biệt NULL với chuỗi rỗng |
| `ENCODING 'UTF8'` | Encoding dữ liệu COPY | Nên khớp encoding của file |
| `FORCE_NULL` | Điều chỉnh cách diễn giải null của CSV đầu vào trên cột chọn | Dùng khi nguồn dữ liệu cần |
| `FORCE_NOT_NULL` | Điều chỉnh cách diễn giải trường rỗng thành non-null | Cần hiểu hệ quả trên chuỗi rỗng |

### 6.1. File dùng dấu chấm phẩy

Nếu file dùng `;` thay cho dấu phẩy:

```csv
product_id;sku;product_name;unit_price;active
10;PEN-010;"Bút xanh";10000.00;true
```

Phải chỉ định:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products_semicolon.csv' WITH (FORMAT csv, HEADER true, DELIMITER ';')
```

Ngược lại, nếu dùng dấu `,` khi file thực tế phân cách bằng `;`, PostgreSQL có thể coi cả dòng là một trường hoặc báo thiếu dữ liệu.

### 6.2. Tên có dấu phẩy hoặc dấu quote

Các trường sau đều hợp lệ khi dùng CSV:

```csv
id,description
1,"Sách SQL, nâng cao"
2,"Tên có ""dấu nháy kép"""
```

CSV phải được parse theo quy tắc quote/escape, không thể xử lý bằng cách “tách từng dòng theo dấu phẩy” mà không để ý trường đã được quote.

### 6.3. Newline trong một ô CSV

CSV hợp lệ có thể có trường trải qua nhiều dòng vật lý:

```csv
id,description
1,"Dòng thứ nhất
Dòng thứ hai"
```

Đây vẫn là **một bản ghi dữ liệu** nếu parser đọc đúng. Vì thế đếm newline trong file không luôn bằng số bản ghi CSV; các công cụ đối soát cần dùng parser CSV thực sự.

### 6.4. Text format và `\N`

PostgreSQL COPY cũng có định dạng `text`. Với định dạng này, ký tự tab thường là delimiter mặc định và biểu diễn NULL mặc định thường là `\N`; các ký tự đặc biệt dùng quy tắc escape của COPY text.

Ví dụ:

```text
\copy (SELECT product_id, sku, product_name FROM client_copy_lab.products ORDER BY product_id) TO 'products.txt' WITH (FORMAT text)
```

Đừng xem `FORMAT text` và `FORMAT csv` là hai tên thay thế cho cùng một file; quy tắc escape và NULL khác nhau.

---

## 7. Phân biệt NULL với chuỗi rỗng

Trong chế độ CSV thông dụng của PostgreSQL, mặc định:

- Một trường **không được quote và trống** được diễn giải là SQL `NULL`.
- Một trường được quote là `""` được diễn giải là chuỗi rỗng `''`.
- Chuỗi chữ `NULL` trong file chỉ là dữ liệu text trừ khi đặt quy tắc `NULL 'NULL'` hoặc xử lý tương đương.

Ví dụ file `notes.csv`:

```csv
id,note
1,
2,""
3,NULL
```

Tạo bảng để học:

```sql
CREATE TABLE client_copy_lab.notes (
    id INTEGER PRIMARY KEY,
    note TEXT
);
```

Nhập trong psql:

```text
\copy client_copy_lab.notes (id, note) FROM 'notes.csv' WITH (FORMAT csv, HEADER true)
```

Kiểm tra:

```sql
SELECT
    id,
    note,
    note IS NULL AS is_null,
    note = '' AS is_empty_string
FROM client_copy_lab.notes
ORDER BY id;
```

Kết quả ý nghĩa:

| `id` | `note` | `is_null` | `is_empty_string` |
| --- | --- | --- | --- |
| 1 | SQL NULL | true | NULL |
| 2 | Chuỗi `''` | false | true |
| 3 | Chuỗi `'NULL'` | false | false |

Lưu ý `NULL = ''` không trả `FALSE` mà trả giá trị SQL `NULL` (unknown).

### 7.1. NULL khác với DEFAULT

Ở bảng `products`, cột `created_at` được bỏ khỏi danh sách cột nhập và có default. Nếu cột được **nêu trong danh sách nhập** và CSV chứa giá trị được hiểu là `NULL`, PostgreSQL không mặc nhiên dùng default thay nó. Nếu cột `NOT NULL` mà không cho phép NULL, lệnh nhập có thể thất bại.

Do đó, khi thiết kế file dữ liệu đầu vào, cần phân biệt:

- Cột **không có trong file/import** → có thể áp dụng default.
- Cột **có trong file và nhận NULL** → áp dụng NULL, trừ khi có cơ chế chuyển đổi cụ thể.
- Cột **có giá trị rỗng không phải NULL** → giữ chuỗi rỗng nếu kiểu cột chấp nhận.

---

## 8. Mã hóa, chữ tiếng Việt và dữ liệu số

### 8.1. UTF-8

Các sản phẩm như `Sách SQL, cơ bản` chứa tiếng Việt, vì vậy nên thống nhất:

1. File được lưu theo UTF-8.
2. Trong COPY, dùng `ENCODING 'UTF8'` khi cần quy định rõ.
3. Kiểm tra hệ thống phát file không dùng encoding khác như Windows-1252.
4. Khi file có BOM, xem xét chuyển về UTF-8 không BOM nếu quy trình khác gặp lỗi ký tự đầu.

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

Nếu file không hợp lệ theo UTF-8, server có thể báo `invalid byte sequence for encoding "UTF8"`. Đây là lỗi encoding hoặc nguồn dữ liệu; cấp thêm quyền database không giải quyết nó.

### 8.2. Dấu thập phân và locale

Cột `unit_price NUMERIC(12,2)` trong ví dụ nhận các chuỗi số như `125000.00`. Một nguồn dữ liệu có thể xuất `125.000,00` theo locale. PostgreSQL không tự hiểu mọi format số của từng quốc gia khi nạp vào `NUMERIC`.

Giải pháp tốt:

- Thống nhất format số trong hợp đồng CSV.
- Hoặc nhập giá trị raw dạng `TEXT` vào staging rồi chuyển đổi với quy tắc rõ ràng.

Không tự thay mọi dấu phẩy bằng dấu chấm khi file dùng dấu phẩy để phân cách các trường.

### 8.3. Ngày giờ

Nếu nhập `TIMESTAMPTZ` từ file, nên dùng định dạng timestamp có múi giờ rõ ràng, ví dụ:

```text
2026-11-14T09:30:00+07:00
```

Những chuỗi ngày như `14/11/2026` có thể phụ thuộc quy tắc `DateStyle` hoặc chuyển đổi. Bài lab dùng `created_at DEFAULT now()` để tránh lỗi nhập timestamp khi chưa cần.

---

## 9. Đường dẫn và quyền tệp

### 9.1. Đường dẫn tương đối

```text
\copy client_copy_lab.products TO 'export.csv' WITH (FORMAT csv, HEADER true)
```

File được tạo theo **thư mục làm việc của tiến trình psql**. Để không nhầm khi chạy script, bạn có thể dùng đường dẫn tuyệt đối.

### 9.2. Ví dụ Linux hoặc macOS

```text
\copy client_copy_lab.products TO '/home/student/exports/products.csv' WITH (FORMAT csv, HEADER true)
```

Thư mục `/home/student/exports` phải tồn tại và user OS chạy psql có quyền ghi. PostgreSQL không tự tạo thư mục client chưa có.

### 9.3. Ví dụ Windows

Nếu `psql` chạy trực tiếp trên Windows:

```text
\copy client_copy_lab.products TO 'C:/data/exports/products.csv' WITH (FORMAT csv, HEADER true)
```

Đường dẫn Windows này không có nghĩa lý trên container Linux nếu psql chạy trong container. Dùng `/` trong ví dụ giúp tránh nhầm dấu gạch chéo ngược trong một số ngữ cảnh.

### 9.4. Phân biệt lỗi filesystem với lỗi SQL

| Thông báo/triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| `No such file or directory` | Sai tên file, sai working directory, file không ở filesystem client |
| `Permission denied` khi mở file | User OS chạy psql không có quyền đọc/ghi |
| `permission denied for table ...` | Vai trò PostgreSQL thiếu `INSERT` hoặc `SELECT` |
| `invalid input syntax for type ...` | Nội dung CSV không phù hợp kiểu dữ liệu |
| `duplicate key value violates unique constraint ...` | Giá trị đầu vào trùng khóa |
| File xuất bị ghi vào vị trí không mong đợi | Nhầm nơi tiến trình psql chạy hoặc dùng đường dẫn tương đối |
| Lỗi gần ký tự `\` ở SQL editor | Client không hỗ trợ meta-command psql |

Khi file chỉ tồn tại trên client, cấp PostgreSQL `SUPERUSER` không khiến đường dẫn xuất hiện ở máy client.

---

## 10. Quyền database cần cho `\copy`

`\copy` dùng quyền của tài khoản PostgreSQL đã kết nối:

| Thao tác | Quyền liên quan |
| --- | --- |
| `\copy table FROM 'file.csv'` | `INSERT` trên bảng/cột đích, cùng các quyền khác nếu thao tác yêu cầu |
| `\copy table TO 'file.csv'` | `SELECT` trên bảng/cột đọc |
| `\copy (SELECT ...) TO ...` | Quyền chạy truy vấn, thường gồm `SELECT` trên đối tượng liên quan |
| Đưa dữ liệu từ staging vào bảng thật | `INSERT` hoặc `UPDATE` tương ứng trên bảng đích |
| SQL `COPY ... FROM '/server/file'` | Ngoài quyền bảng có thể cần superuser hoặc đặc quyền đọc tệp server |
| SQL `COPY ... TO '/server/file'` | Ngoài quyền bảng có thể cần superuser hoặc đặc quyền ghi tệp server |

Một DBA trong môi trường lab có thể tạo account nhập chỉ có quyền cần thiết:

```sql
CREATE ROLE client_copy_importer LOGIN PASSWORD 'THAY_MAT_KHAU_MANH';
GRANT USAGE ON SCHEMA client_copy_lab TO client_copy_importer;
GRANT INSERT ON client_copy_lab.products TO client_copy_importer;
```

Tài khoản xuất chỉ đọc:

```sql
CREATE ROLE client_copy_exporter LOGIN PASSWORD 'THAY_MAT_KHAU_KHAC';
GRANT USAGE ON SCHEMA client_copy_lab TO client_copy_exporter;
GRANT SELECT ON client_copy_lab.products TO client_copy_exporter;
```

Đây là ví dụ cấp quyền trong lab. Ở hệ thống thực còn cần quản lý host, TLS, password/secret, credential rotation và chính sách truy cập.

**Giới hạn với Row-Level Security:** PostgreSQL không hỗ trợ `COPY FROM` trên bảng áp dụng RLS theo cùng cách câu `INSERT` thông thường. Khi nhập vào hệ thống dùng RLS, cần thiết kế đường ghi phù hợp (ví dụ insert thông qua logic ứng dụng), không dùng `\copy` như cách đi vòng qua policy.

---

## 11. Transaction và tính nguyên tử của việc nhập

Dữ liệu nhập cần tuân thủ ràng buộc database. Nếu trong file có một hàng sai số hoặc trùng khóa, `COPY FROM` có thể thất bại.

### 11.1. Bao import trong transaction

Trong một session `psql`:

```sql
BEGIN;
```

Tiếp đó nhập trên **một dòng**:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products.csv' WITH (FORMAT csv, HEADER true)
```

Nếu import thành công và kiểm tra đạt yêu cầu:

```sql
SELECT COUNT(*) FROM client_copy_lab.products;
COMMIT;
```

Nếu import báo lỗi hoặc kết quả không đạt:

```sql
ROLLBACK;
```

Đây là **hai nhánh xử lý khác nhau**, không phải chạy cả `COMMIT` và `ROLLBACK` liên tiếp. Sau lỗi trong transaction, PostgreSQL thường đánh dấu transaction là aborted cho tới khi rollback.

### 11.2. `ON_ERROR_STOP` cho script

Ví dụ một file script `import_products.sql` (là tệp **do người học tự tạo trên máy client**, không phải tệp của project được giao):

```sql
\set ON_ERROR_STOP on
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

Từ terminal:

```bash
psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 --single-transaction -f import_products.sql
```

- `ON_ERROR_STOP` yêu cầu psql dừng xử lý khi gặp lỗi thay vì tiếp tục các lệnh sau.
- `--single-transaction` bao script trong một transaction để commit/rollback toàn bộ phần công việc trong phạm vi cho phép.
- Nếu dùng `--single-transaction` thì script **không cần tự thêm `BEGIN` và `COMMIT`**.
- File `products.csv` với tên tương đối được tìm theo **working directory của tiến trình psql**, không mặc định theo thư mục chứa script.
- Pipeline cần kiểm tra **exit code** và log lỗi, không chỉ kiểm tra file hoặc dòng thông báo cuối.

### 11.3. COPY thất bại và dung lượng vật lý

Trong PostgreSQL, nếu `COPY FROM` lỗi sau khi đã xử lý một số hàng, những hàng từ câu COPY thất bại không được commit như dữ liệu hợp lệ. Tuy nhiên, có thể còn các phiên bản hàng vật lý cần PostgreSQL dọn dẹp sau đó; với file nhập rất lớn lỗi muộn, có thể cần quan sát dung lượng/VACUUM.

Cần phân biệt rõ **tính hiển thị theo transaction** với **dung lượng trên đĩa chưa được dọn**.

---

## 12. Staging table: nhận dữ liệu trước khi đưa vào bảng nghiệp vụ

Với file từ bên ngoài, nạp thẳng vào bảng production có nhiều rủi ro: sai format, trùng khóa, dòng không hợp lệ, khác kiểu dữ liệu hoặc quy tắc nghiệp vụ chưa được kiểm chứng.

**Staging table** cho phép nhập raw rồi đối soát.

### 12.1. Tạo bảng staging bằng TEXT

```sql
CREATE TABLE client_copy_lab.products_stage (
    product_id_text TEXT,
    sku TEXT,
    product_name TEXT,
    unit_price_text TEXT,
    active_text TEXT
);
```

Nhập từ file:

```text
\copy client_copy_lab.products_stage (product_id_text, sku, product_name, unit_price_text, active_text) FROM 'products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

Dữ liệu raw được giữ ở dạng text, giảm lỗi parse kiểu ngay trong bước lấy file vào.

### 12.2. Kiểm tra dữ liệu nhập

```sql
SELECT *
FROM client_copy_lab.products_stage
WHERE product_id_text IS NULL
   OR product_id_text !~ '^[0-9]+$'
   OR sku IS NULL
   OR btrim(sku) = ''
   OR product_name IS NULL
   OR btrim(product_name) = ''
   OR unit_price_text IS NULL
   OR unit_price_text !~ '^[0-9]+(\.[0-9]{1,2})?$'
   OR active_text IS NULL
   OR lower(active_text) NOT IN ('true', 'false');
```

Regex chỉ là quy tắc đơn giản cho file mẫu: chỉ cho số nguyên không âm, giá không âm với tối đa hai chữ số thập phân. Nó **chưa chặn số vượt giới hạn kiểu `NUMERIC(12,2)`**, và có thể cần xử lý thêm khoảng trắng, quy tắc locale hoặc trường hợp ngoại lệ.

Kiểm tra trùng key trong staging:

```sql
SELECT product_id_text, COUNT(*) AS duplicate_count
FROM client_copy_lab.products_stage
GROUP BY product_id_text
HAVING COUNT(*) > 1;
```

Kiểm tra `sku` trùng:

```sql
SELECT sku, COUNT(*) AS duplicate_count
FROM client_copy_lab.products_stage
GROUP BY sku
HAVING COUNT(*) > 1;
```

Nếu file có lỗi, hãy sửa nguồn hoặc lọc batch theo chính sách đã xác định; không bỏ qua dòng một cách âm thầm.

### 12.3. Hợp nhất dữ liệu có kiểm soát

Sau khi validation đạt yêu cầu, có thể chủ động UPSERT theo `product_id`:

```sql
BEGIN;

INSERT INTO client_copy_lab.products (
    product_id, sku, product_name, unit_price, active
)
SELECT
    product_id_text::INTEGER,
    btrim(sku),
    product_name,
    unit_price_text::NUMERIC(12,2),
    active_text::BOOLEAN
FROM client_copy_lab.products_stage
ON CONFLICT (product_id) DO UPDATE
SET sku = EXCLUDED.sku,
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    active = EXCLUDED.active;

COMMIT;
```

Quy tắc trên là **một chính sách cập nhật minh họa**:

- Product ID mới → thêm sản phẩm.
- Product ID đã có → cập nhật một số cột.
- `created_at` của sản phẩm cũ không bị thay đổi vì không nằm trong phần UPDATE.

Cẩn thận:

- Hai hàng staging trùng cùng `product_id` trong một lệnh UPSERT có thể gây lỗi không thể cập nhật cùng một hàng đích hai lần.
- Hai `product_id` khác nhau nhưng cùng `sku` vẫn có thể vi phạm `UNIQUE(sku)`.
- Ép kiểu giá và ID có thể thất bại nếu dữ liệu không hợp lệ hoặc vượt giới hạn kiểu.
- Không dùng UPSERT để ghi đè thông tin nghiệp vụ nếu yêu cầu thực tế chỉ cho phép insert mới hoặc cần phê duyệt.

Với hệ thống có nhiều batch nhập song song, staging nên có `batch_id` hoặc một phương án tách dữ liệu theo job để tránh hai lần nhập bị trộn.

---

## 13. Nhập tương tác bằng STDIN

Có thể gửi dữ liệu trực tiếp qua psql mà không cần tạo file:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM STDIN WITH (FORMAT csv)
```

Sau đó nhập dữ liệu trên các dòng:

```text
10,ERASER-010,Tẩy trắng,5000.00,true
11,RULER-011,Thước kẻ,12000.00,true
\.
```

Dòng chỉ chứa `\.` là dấu kết thúc luồng nhập trong psql. Dữ liệu mẫu **không chứa header** vì câu `\copy` không dùng `HEADER true`.

Đây là cách thuận tiện để học cơ chế `FROM STDIN`, nhưng với file lớn nên dùng `FROM 'file.csv'` để tránh sai sót thủ công. Khi đặt vào script, cần đặt dữ liệu và dấu `\.` đúng vị trí; nếu quên, các câu SQL phía sau có thể bị hiểu thành dữ liệu CSV.

---

## 14. Cú pháp đặc biệt của meta-command psql

Một câu SQL thông thường có thể xuống dòng:

```sql
SELECT
    product_id,
    sku
FROM client_copy_lab.products
ORDER BY product_id;
```

Ngược lại, `\copy` có quy tắc parse đặc biệt: psql coi phần còn lại của dòng là tham số của meta-command. Để dễ chạy:

- Viết **toàn bộ `\copy` trên một dòng**.
- Không thêm dấu `;` theo thói quen viết câu SQL.
- Không chia `\copy (SELECT ...) TO ...` tùy ý thành nhiều dòng như SQL.
- Không cho rằng mọi cú pháp nội suy biến `:variable` hoặc backtick của những meta-command khác đều hoạt động tương tự trong `\copy`.
- Không đặt thêm meta-command sau `\copy` trên cùng dòng.

Ví dụ:

```text
\copy (SELECT sku FROM client_copy_lab.products ORDER BY sku) TO 'sku.csv' WITH (FORMAT csv, HEADER true)
```

Nếu truy vấn export dài, cân nhắc tạo view được phép truy cập hoặc tạo lệnh một dòng bằng script cẩn thận. Việc dùng SQL `COPY (query) TO STDOUT` cùng API/driver hỗ trợ cũng là lựa chọn cho ứng dụng không chạy psql.

---

## 15. Theo dõi tiến độ và hiệu năng

### 15.1. Vì sao `\copy` thường nhanh hơn INSERT từng dòng?

COPY truyền dữ liệu dưới dạng luồng và giảm số lần client phải gửi các câu `INSERT` riêng lẻ. Với nhiều hàng, điều này thường có lợi cho throughput.

Nhưng tổng thời gian vẫn phụ thuộc:

- Băng thông mạng client ↔ server.
- Tốc độ đọc/ghi file local.
- Tốc độ parse CSV, chuyển kiểu.
- Index, foreign key, triggers và constraints của bảng.
- WAL, I/O, checkpoint và contention.
- Kích thước file, transaction và công việc validation.

Không nên tắt constraints/triggers một cách tùy tiện để tăng tốc khi dữ liệu cần đúng. Với dữ liệu rất lớn, có thể dùng staging, chia batch hoặc chiến lược bulk load được đo trên môi trường tương đương.

### 15.2. `pg_stat_progress_copy`

PostgreSQL có view quan sát tiến độ COPY trên những phiên bản hỗ trợ:

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed,
    tuples_excluded
FROM pg_stat_progress_copy;
```

View này cho thấy trạng thái COPY đang chạy, tùy quyền và phiên bản. Với dữ liệu truyền qua STDIN/STDOUT, tổng số byte có thể không được xác định đầy đủ từ phía server. `tuples_processed` không đồng nghĩa những hàng đó **đã được commit** nếu operation đang chạy hoặc cuối cùng rollback.

Đối với bảng mẫu chỉ có vài hàng, COPY hoàn tất quá nhanh để quan sát bằng một kết nối khác.

### 15.3. Đối soát theo batch

Để biết file nhập có đúng:

1. Đếm số bản ghi CSV bằng parser hiểu quote và newline trong trường.
2. So sánh số hàng do COPY báo.
3. So sánh số hàng trong bảng **của batch liên quan**, không dùng tổng cả bảng nếu dữ liệu cũ đã có.
4. Kiểm tra khóa, tỷ lệ NULL, giá trị ngoài miền hợp lệ và số liệu tổng hợp cần thiết.
5. Lưu metadata batch, checksum, thời gian xử lý và lỗi để có thể truy vết.

Khi `\copy` đã ghi file nhưng job bị lỗi sau đó, vẫn cần đối soát trước khi cho rằng dữ liệu có thể sử dụng.

---

## 16. Bảo mật file CSV và tài khoản nhập xuất

Những biện pháp quan trọng:

- **Quyền tối thiểu:** tài khoản nhập chỉ có `INSERT` cần thiết; tài khoản xuất chỉ có `SELECT` trong phạm vi được giao.
- **Kết nối mã hóa:** khi psql chạy từ xa, dùng TLS phù hợp với cấu hình client và server.
- **Secret riêng:** không hard-code password vào script, Git hoặc command line dễ lộ.
- **Thư mục đích:** hạn chế quyền đọc/ghi file, đặc biệt khi xuất dữ liệu cá nhân.
- **Giới hạn SELECT:** chỉ lấy cột/hàng phục vụ nhu cầu cụ thể.
- **Lưu trữ và xóa:** không để file xuất tồn tại vô hạn trên laptop, CI runner hay thư mục chia sẻ.
- **Kiểm tra file khi mở bằng bảng tính:** `\copy` không chống CSV formula injection. Một chuỗi người dùng nhập bắt đầu bằng `=`, `+`, `-` hoặc `@` có thể được phần mềm bảng tính hiểu là công thức. Nếu đích là Excel hoặc ứng dụng tương tự, cần cách xử lý đầu ra phù hợp mà vẫn giữ tính đúng của dữ liệu.

Chỉ vì file ở phía client không có nghĩa công việc hoàn toàn an toàn: file vẫn có thể chứa thông tin nhạy cảm, bị đồng bộ tự động hoặc được đọc bởi tiến trình khác trên máy.

---

## 17. Những lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| `syntax error at or near "\"` | Gửi `\copy` như SQL thông thường | Chạy trong `psql` |
| `No such file or directory` | File không có ở máy chạy psql hoặc sai working directory | Xác minh filesystem client và dùng đường dẫn tuyệt đối |
| `Permission denied` khi mở file | User OS của psql không có quyền | Dùng thư mục/file với quyền hợp lý |
| `permission denied for table` | Vai trò PostgreSQL thiếu quyền `SELECT`/`INSERT` | Cấp tối thiểu đúng thao tác |
| `missing data for column` | File có ít trường hơn danh sách cột | Kiểm tra cấu trúc file và danh sách cột |
| `extra data after last expected column` | Dấu phẩy trong trường chưa quote hoặc file dư cột | Sửa CSV/quote hoặc danh sách cột |
| `invalid input syntax for type numeric` | Giá không đúng format số | Chuẩn hóa dữ liệu hoặc staging |
| `duplicate key value violates unique constraint` | Nạp lại key đã có | Dùng staging và chính sách merge |
| Tiếng Việt bị lỗi | Sai encoding hoặc BOM | Xác định encoding nguồn, dùng UTF-8 đúng |
| Header bị hiểu là dữ liệu | Quên `HEADER true` | Thêm header option |
| Cột nhập sai dù header đúng | Header không tự map tên cột | Điều chỉnh thứ tự danh sách cột |
| File xuất nằm trong container | psql thực sự chạy trong container | Mount/chuyển file theo quy trình |
| Script tiếp tục sau lỗi nhập | Không có xử lý lỗi | `ON_ERROR_STOP`, transaction và exit code |
| Có CSV nhưng số dòng không đúng | File có newline trong quote hoặc job chỉ xuất một phần | Dùng parser CSV và kiểm tra điều kiện truy vấn |

---

## 18. Bài tập tự luyện

### Bài 1 — Phân biệt phía client và server

PostgreSQL chạy ở `db.internal`, còn `psql` chạy trên laptop. Nếu chạy:

```text
\copy client_copy_lab.products TO '/tmp/products.csv' WITH (FORMAT csv, HEADER true)
```

Tệp nằm ở đâu? Nếu `psql` chạy trong Docker container, câu trả lời thay đổi thế nào? Vì sao không cần PostgreSQL server đọc/ghi thư mục laptop?

### Bài 2 — Nhập và xác nhận ba sản phẩm

Tạo file `products.csv` theo mục 3.3, chạy lệnh nhập có danh sách 5 cột và `HEADER true`. Đọc lại bảng bằng `SELECT`. Kiểm tra dấu phẩy trong tên sách, dấu nháy kép của sản phẩm `PEN-002`, và giá trị `created_at`.

### Bài 3 — Xuất chỉ sản phẩm active

Dùng:

```text
\copy (SELECT sku, product_name, unit_price FROM client_copy_lab.products WHERE active = true ORDER BY sku) TO 'active_products.csv' WITH (FORMAT csv, HEADER true)
```

Kiểm tra số dòng và thứ tự các sản phẩm. Tại sao nên nêu rõ `ORDER BY` khi yêu cầu file đầu ra có thứ tự ổn định?

### Bài 4 — NULL và chuỗi rỗng

Tạo `notes.csv` ở mục 7, nhập vào `notes` và chạy `note IS NULL` cùng `note = ''`. Giải thích vì sao `COUNT(note)` bỏ qua hàng id 1 nhưng không bỏ qua id 2.

### Bài 5 — Dấu phân cách và quote

Tệp nhận được có dòng:

```csv
21,BOOK-021,Sách, nâng cao,129000.00,true
```

Nếu mong 5 cột nhưng dòng này có thêm dấu phẩy trong tên, parser sẽ hiểu thành bao nhiêu trường? Viết lại trường tên thành `"Sách, nâng cao"` để hợp lệ.

### Bài 6 — Import lần hai

Sau khi nhập file mẫu, chạy lại cùng `\copy` vào bảng `products`. Giải thích lỗi unique violation và đề xuất dùng staging + `ON CONFLICT` thay vì xóa mọi dữ liệu bảng thật.

### Bài 7 — Transaction lỗi

Tạo CSV gồm một hàng hợp lệ và một hàng có `unit_price` bằng `abc`. Thử import trong transaction. Quan sát lỗi, rollback và kiểm tra số hàng trong bảng. Vì sao không thể chỉ nhìn một số dòng đã được xử lý trung gian mà kết luận đã commit?

### Bài 8 — Quyền truy cập

Thiết kế hai role: một chỉ được nạp vào `products_stage`, một chỉ được xuất từ `products`. Viết những quyền `GRANT` tối thiểu và giải thích vì sao không cần `SUPERUSER` chỉ để dùng `\copy` trên file client.

### Bài 9 — Script tự động

Thiết kế job hằng ngày xuất `sku` và `unit_price` ra CSV, có kiểm tra exit code, mã hóa/kho lưu file, chính sách giữ file và thông tin batch. Nếu job chạy trong CI runner, file đầu ra cần được lấy từ đâu?

---

## 19. Quy trình nhập xuất đáng tin cậy

```text
NHẬP
File từ nguồn hợp lệ
        |
        v
Xác nhận encoding + header + delimiter + số cột
        |
        v
\copy FROM vào staging (nếu cần kiểm tra)
        |
        v
Kiểm tra dữ liệu, khóa trùng, NULL, chuyển kiểu
        |
        v
BEGIN -> hợp nhất vào bảng đích -> COMMIT
        |
        v
Đối soát số hàng + lưu thông tin batch + quản lý file

XUẤT
Xác định mục đích và quyền đọc
        |
        v
SELECT đúng cột và hàng được phép
        |
        v
\copy (SELECT ...) TO local CSV
        |
        v
Kiểm tra nội dung + bảo vệ file + chuyển giao an toàn
```

Vai trò của từng lớp:

| Thành phần | Chịu trách nhiệm |
| --- | --- |
| PostgreSQL server | Thực thi SQL/COPY, kiểm tra kiểu dữ liệu, constraints, quyền bảng và transaction |
| `psql` client | Mở tệp local, truyền dữ liệu qua kết nối, ghi file local và báo lỗi |
| Script/ứng dụng vận hành | Chọn đúng file, validation, bảo vệ secret, đối soát, retry/idempotency và lưu trữ |

## Kết luận

`\copy` là meta-command của **psql** dùng để nhập và xuất dữ liệu giữa PostgreSQL với **tệp ở phía client**. Khi `FROM`, psql đọc file local và gửi dữ liệu lên server bằng COPY protocol; khi `TO`, psql nhận dữ liệu từ server rồi ghi file local.

Hãy nhớ bốn nguyên tắc: **(1) đường dẫn là của máy chạy psql; (2) CSV cần khớp thứ tự cột, encoding và định dạng; (3) quyền và constraints PostgreSQL vẫn có hiệu lực; (4) nhập xuất production cần transaction, kiểm tra lỗi, đối soát và bảo vệ tệp**. Khi hiểu rõ ranh giới client/server và hợp đồng dữ liệu, bạn có thể sử dụng `\copy` để xây dựng quy trình nhập xuất đơn giản, hiệu quả và an toàn mà không cần cấp quyền thao tác tùy ý với filesystem của database server.
