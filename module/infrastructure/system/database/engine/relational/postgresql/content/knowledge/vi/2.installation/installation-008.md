# Nạp bộ dữ liệu mẫu có thể tái tạo trong PostgreSQL

Một môi trường học PostgreSQL có ích khi mọi người đều có thể **nạp lại cùng một bộ dữ liệu, chạy cùng truy vấn và nhận kết quả nhất quán**. Nếu mỗi người tự chèn vài dòng bằng tay, dùng giá trị thời gian hiện tại hoặc dữ liệu ngẫu nhiên không kiểm soát, rất khó so sánh bài tập, viết automated test và tìm nguyên nhân khi một câu SQL hoạt động khác nhau giữa các máy.

Bài học này hướng dẫn tạo và nạp một **seed dataset** — bộ dữ liệu mẫu có thể tái tạo — trên PostgreSQL. Ta sẽ tạo một môi trường thực hành riêng, xây dựng bảng có quan hệ khóa ngoại, lưu seed thành tệp SQL UTF-8, nạp bằng `psql` trong một transaction, kiểm tra kết quả, chạy lại nhiều lần mà không cộng dồn bản ghi, mở rộng tập dữ liệu bằng `generate_series` và tổ chức seed cho nhóm phát triển hoặc CI.

**Mục tiêu sau bài học:**

- Phân biệt dữ liệu seed, migration và backup.
- Tạo database hoặc schema dành riêng cho thực hành, tránh ảnh hưởng dữ liệu thật.
- Có tệp seed SQL chứa **ID, thời gian và quy tắc tạo dữ liệu cố định**.
- Nạp bằng `psql`, phát hiện lỗi và rollback cả lần nạp khi cần.
- Hiểu hai chiến lược tái tạo: **reset toàn bộ môi trường thử** và **nạp bổ sung idempotent**.
- Tạo thêm hàng nghìn bản ghi theo công thức có thể lặp lại.
- Xác minh số dòng, khóa ngoại, tổng tiền và một số đặc tính dữ liệu.

Các ví dụ sử dụng PostgreSQL với cú pháp thông dụng của các phiên bản hiện đại. Chạy chúng trên **database học tập hoặc môi trường CI có thể xóa**, không chạy phần reset schema trên production.

## 1. “Có thể tái tạo” nghĩa là gì?

Một bộ dữ liệu mẫu có thể tái tạo có các đặc tính:

1. **Cùng đầu vào, cùng trạng thái đích:** chạy quy trình từ một database trống sẽ tạo cùng bảng và các giá trị mẫu.
2. **Không phụ thuộc thao tác tay:** không cần click lần lượt vào công cụ quản trị để thêm dữ liệu.
3. **Thứ tự quan hệ rõ ràng:** bản ghi cha được tạo trước bản ghi con, không vi phạm khóa ngoại.
4. **Giá trị quan trọng cố định:** ID, số tiền, trạng thái và mốc thời gian không thay đổi theo ngày chạy.
5. **Quy trình chạy lại được xác định trước:** hoặc reset môi trường thử, hoặc UPSERT/kiểm tra để tránh nhân bản.
6. **Có phép kiểm chứng:** nếu nạp thiếu hàng hoặc sai dữ liệu thì phát hiện được.

Ví dụ: một bài tập JOIN yêu cầu có chính xác bốn khách hàng, bốn sản phẩm và bốn đơn hàng. Nếu mỗi lần chạy seed lại tạo đơn theo `now()` hoặc số lượng bằng `random()` không kiểm soát, kết quả báo cáo có thể khác, khiến bài tập khó đánh giá.

Một seed xác định cho dữ liệu mẫu thường dùng:

~~~text
customer_id: 1, 2, 3, 4
product_id : 101, 102, 103, 104
order_id   : 1001, 1002, 1003, 1004
time       : giá trị TIMESTAMPTZ cố định có +00
price      : NUMERIC, không dùng số thực gần đúng cho tiền
~~~

**Tái tạo dữ liệu không có nghĩa kết quả mọi truy vấn tự có thứ tự.** Khi kiểm tra thứ tự dòng, vẫn phải dùng `ORDER BY`.

## 2. Seed khác migration, fixture và backup thế nào?

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Schema migration** | Thay đổi cấu trúc database có lịch sử phiên bản | `CREATE TABLE`, `ALTER TABLE`, tạo index |
| **Seed data** | Tạo tập dữ liệu khởi đầu xác định | Khách hàng A, sản phẩm B, đơn hàng C |
| **Test fixture** | Dữ liệu phục vụ một ca kiểm thử cụ thể | Một đơn đã hủy để kiểm tra báo cáo |
| **Backup** | Lưu trạng thái dữ liệu có thật để phục hồi | `pg_dump`, base backup + WAL |
| **Data generator** | Sinh nhiều dữ liệu theo quy tắc | `generate_series(1, 100000)` |

Trong bài học, một tệp SQL có thể vừa tạo schema thực hành vừa thêm dữ liệu để dễ chạy độc lập. Trong dự án thực tế, thường tách **migration** khỏi **seed**: migration tạo phiên bản cấu trúc, seed thêm dữ liệu phát triển/kiểm thử. Hai việc có vòng đời khác nhau.

Seed **không thay thế backup**. Nếu dữ liệu người dùng bị mất, chạy lại seed chỉ tạo dữ liệu ví dụ, không phục hồi giao dịch thật.

## 3. Chuẩn bị PostgreSQL và công cụ kết nối

Cần có:

- Một PostgreSQL server local, trong container hoặc instance chỉ dành cho học tập.
- Client `psql` tương thích để chạy file SQL.
- Một role có quyền tạo database/schema và bảng trong môi trường thử.
- Trình soạn thảo lưu tệp ở **UTF-8**, để dữ liệu có dấu tiếng Việt không bị hỏng.
- Quyền làm sạch **schema riêng được chỉ định** nếu chọn phương án reset.

Đầu tiên xác minh kết nối bằng một database mà tài khoản được phép truy cập:

~~~bash
psql -h 127.0.0.1 -p 5432 -U lab_user -d postgres
~~~

Trong `psql`:

~~~sql
SELECT
    version() AS postgres_version,
    current_database() AS database_name,
    current_user AS role_name,
    current_setting('server_encoding') AS server_encoding,
    current_setting('TimeZone') AS server_timezone;
~~~

Nếu `psql` báo lỗi authentication, connection refused hoặc timeout, kiểm tra lại host, port, role, password, TCP/TLS và trạng thái server. Lỗi kết nối không liên quan trực tiếp tới nội dung seed.

### 3.1. Tạo database học tập một lần

Nếu role được phép tạo database:

~~~bash
createdb -h 127.0.0.1 -p 5432 -U lab_user -E UTF8 pg_seed_lab
~~~

`createdb` là tiện ích client dùng để yêu cầu PostgreSQL server tạo database. Đây là bước **thiết lập lần đầu**; nếu database `pg_seed_lab` đã tồn tại, lệnh có thể báo lỗi và không cần chạy lại.

Nếu môi trường được cung cấp sẵn database, sử dụng database đó sau khi xác nhận đây là môi trường học tập và bạn có quyền tạo schema riêng. Không nhất thiết phải có quyền superuser.

Khi đã có database:

~~~bash
psql -h 127.0.0.1 -p 5432 -U lab_user -d pg_seed_lab
~~~

### 3.2. Tránh ghi password vào source code

Không chèn password thật trong file seed hoặc commit vào Git. Có thể để `psql` hỏi mật khẩu, dùng credential store, `.pgpass`/`PGPASSFILE` với permission phù hợp hoặc secret manager của môi trường. Với CI, secret được cấu hình tại runner thay vì đặt cố định trong repo.

Không dùng tài khoản production để thử chạy file có `DROP SCHEMA`.

## 4. Tổ chức tệp để mọi người chạy giống nhau

Một cấu trúc dự án đơn giản:

~~~text
postgres-lab/
  README.md
  sql/
    seed.sql
    seed-large.sql
    verify.sql
  docs/
    sample-results.md
~~~

Nội dung và mục đích:

- `seed.sql`: tự tạo lại schema `lab_seed` và nạp dữ liệu cơ bản.
- `seed-large.sql`: tùy chọn tạo thêm dữ liệu lớn bằng công thức.
- `verify.sql`: chứa những câu kiểm tra kết quả.
- `README.md`: ghi phiên bản PostgreSQL mục tiêu, lệnh nạp, các giá trị dự kiến và lưu ý an toàn.

**Không bắt buộc tách thành nhiều file** để làm theo bài: file `seed.sql` dưới đây tự chứa cấu trúc và dữ liệu cần thiết. Những file khác chỉ là bước mở rộng.

Nếu một dự án đã có migration framework, nên tích hợp seed với quy trình chuẩn của dự án để tránh trùng lặp DDL và khác biệt giữa các môi trường.

## 5. Mô hình dữ liệu sẽ nạp

Ta dùng ví dụ nhỏ về cửa hàng:

~~~text
lab_seed.khach_hang (1)
        |
        | 1 - n
        v
lab_seed.don_hang (1) ---- (n) lab_seed.chi_tiet_don_hang
                                            |
                                            | n - 1
                                            v
                                   lab_seed.san_pham
~~~

Bốn bảng:

| Bảng | Vai trò | Khóa chính |
|---|---|---|
| `khach_hang` | Lưu khách hàng | `khach_hang_id` |
| `san_pham` | Lưu sản phẩm và giá hiện hành | `san_pham_id` |
| `don_hang` | Lưu đơn của khách và trạng thái | `don_hang_id` |
| `chi_tiet_don_hang` | Lưu sản phẩm, số lượng và giá tại thời điểm đặt | Khóa ghép `(don_hang_id, san_pham_id)` |

Mối quan hệ:

- `don_hang.khach_hang_id` tham chiếu `khach_hang`.
- `chi_tiet_don_hang.don_hang_id` tham chiếu `don_hang`.
- `chi_tiet_don_hang.san_pham_id` tham chiếu `san_pham`.

Ta cố ý lưu `don_gia` trong dòng chi tiết để bài tập có thể tính thành tiền theo **giá tại lúc đặt**, thay vì luôn lấy giá hiện tại từ bảng sản phẩm.

## 6. File seed.sql hoàn chỉnh: reset schema riêng rồi nạp dữ liệu

Dưới đây là **toàn bộ nội dung** cho `sql/seed.sql`. File sử dụng một schema tên `lab_seed` tách khỏi `public`.

**Cảnh báo:** dòng `DROP SCHEMA IF EXISTS lab_seed CASCADE` sẽ xóa schema `lab_seed` cùng mọi đối tượng bên trong và cả những đối tượng phụ thuộc phù hợp với quy tắc `CASCADE`. Chỉ chạy khi `lab_seed` thuộc **database học tập có thể reset** và không có dữ liệu cần giữ hay phụ thuộc từ bên ngoài. Không chạy trên production hoặc database dùng chung chưa được kiểm soát.

~~~sql
-- sql/seed.sql
-- Chỉ dùng trên database học tập có thể reset.
-- Gọi bằng psql --single-transaction và ON_ERROR_STOP=1.

SET client_encoding TO 'UTF8';
SET TIME ZONE 'UTC';

DROP SCHEMA IF EXISTS lab_seed CASCADE;
CREATE SCHEMA lab_seed;

CREATE TABLE lab_seed.khach_hang (
    khach_hang_id INTEGER PRIMARY KEY,
    ho_ten TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    tao_luc TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_khach_hang_ho_ten
        CHECK (length(btrim(ho_ten)) > 0)
);

CREATE TABLE lab_seed.san_pham (
    san_pham_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    ten_san_pham TEXT NOT NULL,
    gia NUMERIC(12, 2) NOT NULL,
    dang_ban BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_san_pham_gia
        CHECK (gia >= 0)
);

CREATE TABLE lab_seed.don_hang (
    don_hang_id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL
        REFERENCES lab_seed.khach_hang(khach_hang_id),
    dat_luc TIMESTAMPTZ NOT NULL,
    trang_thai TEXT NOT NULL,
    CONSTRAINT chk_don_hang_trang_thai
        CHECK (trang_thai IN ('moi', 'da_thanh_toan', 'da_huy'))
);

CREATE TABLE lab_seed.chi_tiet_don_hang (
    don_hang_id INTEGER NOT NULL
        REFERENCES lab_seed.don_hang(don_hang_id),
    san_pham_id INTEGER NOT NULL
        REFERENCES lab_seed.san_pham(san_pham_id),
    so_luong INTEGER NOT NULL,
    don_gia NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (don_hang_id, san_pham_id),
    CONSTRAINT chk_chi_tiet_so_luong
        CHECK (so_luong > 0),
    CONSTRAINT chk_chi_tiet_don_gia
        CHECK (don_gia >= 0)
);

-- Bảng cha: khách hàng.
INSERT INTO lab_seed.khach_hang
    (khach_hang_id, ho_ten, email, tao_luc)
VALUES
    (1, 'Nguyễn An', 'an@example.test',
        TIMESTAMPTZ '2026-01-01 08:00:00+00'),
    (2, 'Trần Bình', 'binh@example.test',
        TIMESTAMPTZ '2026-01-02 08:00:00+00'),
    (3, 'Lê Chi', 'chi@example.test',
        TIMESTAMPTZ '2026-01-03 08:00:00+00'),
    (4, 'Phạm Dũng', 'dung@example.test',
        TIMESTAMPTZ '2026-01-04 08:00:00+00');

-- Bảng cha: sản phẩm.
INSERT INTO lab_seed.san_pham
    (san_pham_id, sku, ten_san_pham, gia, dang_ban)
VALUES
    (101, 'BOOK-SQL', 'Sách PostgreSQL', 150000.00, TRUE),
    (102, 'KEYBOARD', 'Bàn phím', 450000.00, TRUE),
    (103, 'MOUSE', 'Chuột', 180000.00, TRUE),
    (104, 'HEADSET', 'Tai nghe', 650000.00, FALSE);

-- Bảng con: đơn hàng tham chiếu khách hàng.
INSERT INTO lab_seed.don_hang
    (don_hang_id, khach_hang_id, dat_luc, trang_thai)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-01-10 08:00:00+00',
        'da_thanh_toan'),
    (1002, 2, TIMESTAMPTZ '2026-01-11 09:00:00+00',
        'moi'),
    (1003, 1, TIMESTAMPTZ '2026-01-12 10:00:00+00',
        'da_huy'),
    (1004, 3, TIMESTAMPTZ '2026-01-13 11:00:00+00',
        'da_thanh_toan');

-- Bảng con: chi tiết đơn tham chiếu đơn và sản phẩm.
INSERT INTO lab_seed.chi_tiet_don_hang
    (don_hang_id, san_pham_id, so_luong, don_gia)
VALUES
    (1001, 101, 2, 150000.00),
    (1001, 103, 1, 180000.00),
    (1002, 102, 1, 450000.00),
    (1003, 104, 1, 650000.00),
    (1004, 101, 1, 150000.00),
    (1004, 102, 1, 450000.00);

-- Kiểm tra bên trong lần nạp: nếu sai, báo lỗi
-- để psql dừng và transaction rollback.
DO $seed_verify$
BEGIN
    IF (SELECT count(*) FROM lab_seed.khach_hang) <> 4 THEN
        RAISE EXCEPTION 'Seed khach_hang: expected 4 rows';
    END IF;

    IF (SELECT count(*) FROM lab_seed.san_pham) <> 4 THEN
        RAISE EXCEPTION 'Seed san_pham: expected 4 rows';
    END IF;

    IF (SELECT count(*) FROM lab_seed.don_hang) <> 4 THEN
        RAISE EXCEPTION 'Seed don_hang: expected 4 rows';
    END IF;

    IF (SELECT count(*) FROM lab_seed.chi_tiet_don_hang) <> 6 THEN
        RAISE EXCEPTION 'Seed chi_tiet_don_hang: expected 6 rows';
    END IF;
END;
$seed_verify$;
~~~

Tệp không chứa `BEGIN` hoặc `COMMIT` vì phần tiếp theo sẽ để `psql --single-transaction` bao bọc toàn bộ. Nếu chạy trong GUI thay vì `psql`, phải chủ động điều khiển transaction tương đương.

### 6.1. Vì sao tạo bảng theo thứ tự đó?

Bảng `don_hang` có khóa ngoại tới `khach_hang`, nên bảng khách phải tồn tại trước. Bảng `chi_tiet_don_hang` tham chiếu cả `don_hang` và `san_pham`, nên được tạo sau các bảng đó.

Thứ tự nạp dữ liệu cũng tuân theo quan hệ:

~~~text
khach_hang ---+
              +--> don_hang ---+
san_pham -----+               +--> chi_tiet_don_hang
~~~

Trong thực tế, các mối quan hệ phức tạp hơn có thể cần chiến lược khởi tạo khác, nhưng **không nên tắt kiểm tra khóa ngoại để che lỗi seed**. Nếu dữ liệu seed không thỏa ràng buộc, ưu tiên sửa dữ liệu hoặc thiết kế quá trình nạp.

### 6.2. Vì sao dùng INTEGER và ID cố định?

Dữ liệu mẫu không cần tạo ID tự động trong mọi lần chạy. Gắn ID rõ ràng giúp bài tập JOIN và khóa ngoại luôn có cùng kết quả.

Ví dụ đơn `1001` luôn thuộc khách `1` và có hai dòng chi tiết. Nếu các ID được sinh bằng một sequence đã tăng trước đó, việc chạy lại seed theo cách `INSERT` thông thường có thể sinh ID khác hoặc vi phạm khóa ngoại.

PostgreSQL vẫn hỗ trợ `GENERATED ... AS IDENTITY` và sequence trong ứng dụng thực tế. Seed đơn giản này cố tình dùng ID cố định để tránh phải đồng bộ lại sequence ở bước cơ bản.

### 6.3. Vì sao dùng NUMERIC cho tiền?

`NUMERIC(12,2)` lưu số thập phân với độ chính xác xác định theo khai báo, phù hợp hơn `REAL` hoặc `DOUBLE PRECISION` cho các phép tính tiền đơn giản trong bài học. Giá trong dòng chi tiết có hai chữ số thập phân và luôn cố định.

### 6.4. Vì sao thời gian có +00?

`TIMESTAMPTZ '2026-01-10 08:00:00+00'` xác định một thời điểm cụ thể. Nếu viết `now()` trong seed thì cùng file chạy ở hai ngày khác nhau sẽ tạo giá trị khác. Nếu dùng literal thời gian thiếu timezone trong ngữ cảnh nhạy với múi giờ, cách diễn giải có thể phụ thuộc cấu hình session.

`TIMESTAMPTZ` lưu thời điểm có thể được hiển thị theo timezone của session. Câu `SET TIME ZONE 'UTC'` ở đầu tệp giúp kết quả in ra dễ so sánh; giá trị thời điểm đã được định nghĩa với offset `+00` ngay trong dữ liệu.

## 7. Nạp file bằng psql trong một transaction

Từ thư mục dự án chứa `sql/seed.sql`:

~~~bash
psql \
  -X \
  -v ON_ERROR_STOP=1 \
  --single-transaction \
  -h 127.0.0.1 \
  -p 5432 \
  -U lab_user \
  -d pg_seed_lab \
  -f sql/seed.sql
~~~

Các tùy chọn quan trọng:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-X` | Không đọc cấu hình khởi động người dùng của `psql`, giảm khác biệt giữa các máy |
| `-v ON_ERROR_STOP=1` | Dừng xử lý script khi một lệnh báo lỗi |
| `--single-transaction` hoặc `-1` | Bọc các lệnh của lần chạy trong một transaction |
| `-h`, `-p` | Chọn host và port của server |
| `-U` | Chọn PostgreSQL role |
| `-d` | Chọn database đích |
| `-f` | Đọc nội dung SQL từ file |

Vì `seed.sql` chỉ dùng các lệnh phù hợp với transaction, `psql` có thể chạy cả reset schema, tạo bảng và nạp hàng trong cùng một đơn vị nguyên tử. Nếu một lệnh hoặc bước xác minh làm `psql` dừng do lỗi, transaction không được commit; các thay đổi của lần nạp đó được rollback.

**Đặc biệt quan trọng:** `DROP SCHEMA` ở đây chạy trong PostgreSQL transaction, nên nếu script thất bại trước commit, schema cũ của lần chạy trước không bị thay bằng trạng thái nạp dở. Đây là một lợi thế cho môi trường thử — nhưng không biến việc xóa schema của môi trường sai thành hành động an toàn. Cần luôn kiểm tra đúng database.

### 7.1. Không trộn BEGIN/COMMIT trong file với --single-transaction

Nếu muốn dùng `psql -1` thì để `psql` quản lý ranh giới transaction. Không nên viết thêm các lệnh `BEGIN` và `COMMIT` tùy tiện trong seed rồi giả định `-1` sẽ vẫn bao trùm mọi thay đổi. Với công cụ GUI, có thể tự thực hiện `BEGIN` và `COMMIT`, nhưng phải hiểu chế độ autocommit của công cụ.

### 7.2. Chạy lại một lần nữa

Chạy **cùng lệnh** lần thứ hai. Trên database học tập dành riêng, schema `lab_seed` bị thay bằng cùng bốn bảng và cùng các hàng cố định. Số lượng và giá trị không tăng gấp đôi.

Đây là kiểu tái tạo **reset-and-seed**:

~~~text
Lần 1: schema trống -> 4 khách, 4 sản phẩm, 4 đơn, 6 chi tiết
Lần 2: xóa schema lab_seed -> tạo lại -> đúng cùng trạng thái
Lần 3: xóa schema lab_seed -> tạo lại -> đúng cùng trạng thái
~~~

Đổi lại, mọi chỉnh sửa thủ công trong `lab_seed` bị mất sau lần chạy tiếp theo. **Chỉ áp dụng trên môi trường đã chủ động cho phép reset.**

## 8. Kiểm chứng dữ liệu sau khi nạp

### 8.1. Kiểm tra số dòng

~~~sql
SELECT 'khach_hang' AS bang, count(*) AS so_dong
FROM lab_seed.khach_hang
UNION ALL
SELECT 'san_pham', count(*)
FROM lab_seed.san_pham
UNION ALL
SELECT 'don_hang', count(*)
FROM lab_seed.don_hang
UNION ALL
SELECT 'chi_tiet_don_hang', count(*)
FROM lab_seed.chi_tiet_don_hang
ORDER BY bang;
~~~

Kỳ vọng:

| bang | so_dong |
|---|---:|
| chi_tiet_don_hang | 6 |
| don_hang | 4 |
| khach_hang | 4 |
| san_pham | 4 |

### 8.2. Kiểm tra JOIN và tổng tiền theo đơn

~~~sql
SELECT
    d.don_hang_id,
    k.ho_ten,
    d.trang_thai,
    SUM(ct.so_luong * ct.don_gia) AS tong_tien
FROM lab_seed.don_hang AS d
JOIN lab_seed.khach_hang AS k
    ON k.khach_hang_id = d.khach_hang_id
JOIN lab_seed.chi_tiet_don_hang AS ct
    ON ct.don_hang_id = d.don_hang_id
GROUP BY
    d.don_hang_id,
    k.ho_ten,
    d.trang_thai
ORDER BY d.don_hang_id;
~~~

Kết quả kỳ vọng:

| don_hang_id | ho_ten | trang_thai | tong_tien |
|---:|---|---|---:|
| 1001 | Nguyễn An | da_thanh_toan | 480000.00 |
| 1002 | Trần Bình | moi | 450000.00 |
| 1003 | Nguyễn An | da_huy | 650000.00 |
| 1004 | Lê Chi | da_thanh_toan | 600000.00 |

Đơn `1003` là đơn đã hủy nhưng vẫn có dòng chi tiết để thực hành lọc trạng thái. Khi tính doanh thu thực tế trong bài tập, cần định nghĩa rõ có loại trừ đơn đã hủy và đơn chưa thanh toán hay không.

### 8.3. Kiểm tra tính toàn vẹn khóa ngoại

Do bảng đã có các ràng buộc `REFERENCES`, PostgreSQL kiểm tra khóa ngoại khi thao tác chèn/cập nhật theo quy định. Có thể viết truy vấn quan sát để người học hiểu:

~~~sql
SELECT ct.don_hang_id, ct.san_pham_id
FROM lab_seed.chi_tiet_don_hang AS ct
LEFT JOIN lab_seed.don_hang AS d
    ON d.don_hang_id = ct.don_hang_id
LEFT JOIN lab_seed.san_pham AS p
    ON p.san_pham_id = ct.san_pham_id
WHERE d.don_hang_id IS NULL
   OR p.san_pham_id IS NULL;
~~~

Kết quả kỳ vọng: **0 dòng**. Nếu một ứng dụng sau này nhập dữ liệu bỏ qua ràng buộc hoặc khôi phục theo quy trình đặc biệt, những phép kiểm tra rõ ràng như vậy hỗ trợ đối soát.

### 8.4. Kiểm tra câu truy vấn có ORDER BY

~~~sql
SELECT khach_hang_id, ho_ten
FROM lab_seed.khach_hang
ORDER BY khach_hang_id;
~~~

Không nên đánh giá bài học bằng cách so sánh thứ tự tự nhiên của `SELECT *` thiếu `ORDER BY`. PostgreSQL không bảo đảm thứ tự hàng nếu không yêu cầu sắp xếp.

## 9. Hai chiến lược tái tạo: reset và idempotent

### 9.1. Reset-and-seed

Ý tưởng: xóa phạm vi thử, tạo lại schema và nạp một tập xác định.

**Ưu điểm:**

- Đảm bảo trạng thái sau lần chạy giống trạng thái chuẩn, kể cả khi trước đó người học đã sửa dữ liệu.
- Dễ kiểm tra số dòng và kết quả query.
- Không cần quan tâm những bản ghi cũ bị sửa sai.
- Phù hợp test database tạm và môi trường học có thể xóa.

**Nhược điểm:**

- Mất dữ liệu đang có trong phạm vi reset.
- Có thể làm mất đối tượng phụ thuộc nếu dùng `CASCADE`.
- Không phù hợp môi trường chứa dữ liệu thật hoặc schema chia sẻ.

### 9.2. Idempotent seed

Ý tưởng: chạy lặp lại không tạo bản ghi trùng; thường dùng khóa nghiệp vụ hoặc khóa chính cùng `ON CONFLICT`.

Ví dụ chỉ thêm khách nếu chưa có:

~~~sql
INSERT INTO lab_seed.khach_hang
    (khach_hang_id, ho_ten, email, tao_luc)
VALUES
    (5, 'Võ Hà', 'ha@example.test',
        TIMESTAMPTZ '2026-01-05 08:00:00+00')
ON CONFLICT (khach_hang_id) DO NOTHING;
~~~

Chạy lại sẽ không thêm bản ghi ID 5 lần thứ hai, **nếu ID 5 đã tồn tại**. Nhưng nếu bản ghi ID 5 trước đó có email hoặc tên khác, `DO NOTHING` sẽ để nguyên giá trị cũ. Vì vậy `ON CONFLICT DO NOTHING` là **chống trùng**, chưa chắc bảo đảm trạng thái đích khớp seed.

Nếu muốn giá trị cuối đồng bộ với file, dùng UPSERT:

~~~sql
INSERT INTO lab_seed.khach_hang
    (khach_hang_id, ho_ten, email, tao_luc)
VALUES
    (5, 'Võ Hà', 'ha@example.test',
        TIMESTAMPTZ '2026-01-05 08:00:00+00')
ON CONFLICT (khach_hang_id)
DO UPDATE SET
    ho_ten = EXCLUDED.ho_ten,
    email = EXCLUDED.email,
    tao_luc = EXCLUDED.tao_luc;
~~~

`EXCLUDED` đại diện cho giá trị hàng mà lệnh `INSERT` dự định chèn. Cách này giúp đưa ID 5 về đúng giá trị đã khai báo, nhưng phải xét **unique key khác**: nếu email đã thuộc về ID 6, thao tác vẫn có thể lỗi. Đây là điều đúng đắn; không nên bỏ qua mâu thuẫn dữ liệu tùy tiện.

### 9.3. Dùng phương án nào?

| Môi trường | Lựa chọn phù hợp |
|---|---|
| Database học tập cá nhân có thể xóa | Reset-and-seed |
| CI tạo database tạm cho mỗi test suite | Reset-and-seed hoặc fixture riêng |
| Dữ liệu danh mục chuẩn trong staging | Idempotent seed/migration có kiểm soát |
| Database shared giữa nhiều nhóm | Không tự reset; cần phạm vi và quyền cụ thể |
| Production có dữ liệu người dùng | Không dùng script reset; dữ liệu nền phải được triển khai theo quy trình quản lý thay đổi |

Tính idempotent là đặc tính của **logic thao tác trên trạng thái cụ thể**, không phải cứ có `ON CONFLICT` thì toàn bộ script tự an toàn cho production.

## 10. Tạo dữ liệu lớn có quy luật bằng generate_series

PostgreSQL cung cấp `generate_series` để sinh dãy số hoặc thời gian trong truy vấn. Đây là cách thuận tiện để có hàng nghìn/hàng triệu dòng học tập **không phụ thuộc số ngẫu nhiên**.

Ví dụ xem dãy:

~~~sql
SELECT g
FROM generate_series(1, 5) AS g;
~~~

Kết quả gồm 1, 2, 3, 4, 5.

### 10.1. Thêm 1.000 khách hàng tổng hợp

Sau khi chạy `seed.sql` cơ bản, có thể chạy đoạn sau như một bài thực hành riêng:

~~~sql
INSERT INTO lab_seed.khach_hang
    (khach_hang_id, ho_ten, email, tao_luc)
SELECT
    g,
    'Khách hàng ' || g::text,
    'kh' || lpad(g::text, 5, '0') || '@example.test',
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + ((g - 10001) * INTERVAL '1 minute')
FROM generate_series(10001, 11000) AS g
ON CONFLICT (khach_hang_id)
DO UPDATE SET
    ho_ten = EXCLUDED.ho_ten,
    email = EXCLUDED.email,
    tao_luc = EXCLUDED.tao_luc;
~~~

Công thức bảo đảm:

- ID luôn từ 10001 đến 11000.
- Email có cấu trúc xác định theo ID.
- Mốc thời gian bắt đầu từ một timestamp cố định.
- Mỗi ID có cùng tên, email và timestamp ở những lần nạp.
- Khi chạy lại trên dữ liệu bổ sung này, các bản ghi được cập nhật chứ không cộng dồn.

Sau bước này, bảng `khach_hang` có **1.004 dòng** nếu ban đầu chỉ có bốn khách từ `seed.sql`.

### 10.2. Thêm 5.000 đơn hàng theo công thức

~~~sql
INSERT INTO lab_seed.don_hang
    (don_hang_id, khach_hang_id, dat_luc, trang_thai)
SELECT
    g,
    10001 + ((g - 20001) % 1000),
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
        + ((g - 20001) * INTERVAL '1 minute'),
    CASE (g % 3)
        WHEN 0 THEN 'moi'
        WHEN 1 THEN 'da_thanh_toan'
        ELSE 'da_huy'
    END
FROM generate_series(20001, 25000) AS g
ON CONFLICT (don_hang_id)
DO UPDATE SET
    khach_hang_id = EXCLUDED.khach_hang_id,
    dat_luc = EXCLUDED.dat_luc,
    trang_thai = EXCLUDED.trang_thai;
~~~

Với `g` từ 20001 đến 25000:

- `10001 + ((g - 20001) % 1000)` chỉ tạo ID khách trong dãy đã nạp.
- Mỗi đơn có timestamp và trạng thái theo quy tắc, không cần `random()`.
- Tất cả đơn đều tham chiếu khách hợp lệ nếu bước 10.1 đã thành công.

### 10.3. Thêm mỗi đơn một dòng chi tiết

~~~sql
INSERT INTO lab_seed.chi_tiet_don_hang
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    g,
    101 + (g % 4),
    1 + (g % 3),
    p.gia
FROM generate_series(20001, 25000) AS g
JOIN lab_seed.san_pham AS p
    ON p.san_pham_id = 101 + (g % 4)
ON CONFLICT (don_hang_id, san_pham_id)
DO UPDATE SET
    so_luong = EXCLUDED.so_luong,
    don_gia = EXCLUDED.don_gia;
~~~

Vì bảng sản phẩm có các ID 101–104, phép `101 + (g % 4)` luôn chọn một trong bốn sản phẩm đã seed. Giá chi tiết lấy theo giá trong bảng `san_pham`. Trong ví dụ này, giá sản phẩm từ seed cơ bản vẫn cố định.

Sau ba bước mở rộng, trạng thái kỳ vọng:

| Bảng | Ban đầu | Thêm | Tổng |
|---|---:|---:|---:|
| `khach_hang` | 4 | 1.000 | 1.004 |
| `san_pham` | 4 | 0 | 4 |
| `don_hang` | 4 | 5.000 | 5.004 |
| `chi_tiet_don_hang` | 6 | 5.000 | 5.006 |

**Giới hạn:** dữ liệu được sinh bởi công thức này thích hợp cho luyện `JOIN`, `GROUP BY`, index và pagination cơ bản, nhưng **không đại diện cho phân bố dữ liệu production**. Các workload thật có thể có xu hướng mua hàng không đều, nhiều chi tiết trên một đơn, mùa vụ, hot keys và tương quan giữa các cột.

### 10.4. Đặt lệnh mở rộng vào file riêng

Nên lưu ba đoạn lệnh vào `sql/seed-large.sql` và nạp sau `seed.sql`. Không chạy lệnh mở rộng trước vì sẽ vi phạm foreign key.

Ví dụ:

~~~bash
psql -X -v ON_ERROR_STOP=1 --single-transaction \
  -h 127.0.0.1 -p 5432 -U lab_user -d pg_seed_lab \
  -f sql/seed-large.sql
~~~

Nếu cần trạng thái đúng chuẩn của bộ dữ liệu lớn, luôn chạy **seed cơ bản trước, rồi seed lớn**. Nếu chạy lại `seed.sql`, nó sẽ reset schema và xóa dữ liệu lớn theo thiết kế.

## 11. Vì sao không nên dùng random() tùy tiện?

Câu lệnh:

~~~sql
SELECT
    g,
    random() AS diem
FROM generate_series(1, 10) AS g;
~~~

cho giá trị khác giữa các lần chạy. Điều này đôi khi hữu ích để mô phỏng ngẫu nhiên, nhưng gây khó khăn cho phép kiểm chứng bằng giá trị cố định.

PostgreSQL có `setseed` để điều chỉnh chuỗi pseudo-random của `random()` trong session, ví dụ:

~~~sql
SELECT setseed(0.42);

SELECT random();
~~~

Tuy nhiên, nếu số lần gọi hoặc thứ tự thực thi khác nhau — chẳng hạn do thay đổi query plan, parallelism, phiên bản hoặc logic sinh dữ liệu — kết quả gắn với từng hàng có thể thay đổi. Đặt seed cho bộ sinh ngẫu nhiên **không tự bảo đảm bộ dữ liệu giống tuyệt đối trong mọi môi trường**.

Với một seed cần tính xác định cao, ưu tiên công thức phụ thuộc trực tiếp vào ID:

~~~sql
SELECT
    g AS id,
    1 + ((g * 17) % 5) AS so_luong,
    10000 + ((g * 97) % 90000) AS gia_mau
FROM generate_series(1, 10) AS g
ORDER BY g;
~~~

Mỗi ID sẽ luôn tạo cùng giá trị. Nếu cần mô phỏng phân bố gần thực tế hơn, có thể chuẩn bị một tệp fixture có version rõ ràng hoặc dùng thuật toán sinh dữ liệu có seed, cấu hình và phiên bản được cố định.

## 12. Tạo dữ liệu mẫu bằng CSV và \copy

Không phải lúc nào seed cũng tiện viết thành nhiều lệnh `INSERT`. Với một bảng dữ liệu độc lập hoặc dữ liệu do nhóm nghiệp vụ cung cấp, tệp CSV có thể dễ đọc và so sánh thay đổi hơn.

Ví dụ file `sql/products.csv` (UTF-8):

~~~csv
san_pham_id,sku,ten_san_pham,gia,dang_ban
101,BOOK-SQL,Sách PostgreSQL,150000.00,true
102,KEYBOARD,Bàn phím,450000.00,true
103,MOUSE,Chuột,180000.00,true
104,HEADSET,Tai nghe,650000.00,false
~~~

Có hai cách nhập file thường bị nhầm:

### 12.1. COPY SQL đọc file ở phía server

~~~sql
COPY lab_seed.san_pham
    (san_pham_id, sku, ten_san_pham, gia, dang_ban)
FROM '/srv/data/products.csv'
WITH (FORMAT csv, HEADER true);
~~~

Đường dẫn là ở **máy chạy PostgreSQL server**; server phải đọc được file và quyền thực thi `COPY FROM file` bị giới hạn. Với managed PostgreSQL, bạn thường không thể tự đặt file vào thư mục server.

### 12.2. \copy đọc file ở phía client psql

Trong `psql`:

~~~text
\copy lab_seed.san_pham (san_pham_id, sku, ten_san_pham, gia, dang_ban) FROM 'sql/products.csv' WITH (FORMAT csv, HEADER true)
~~~

`\copy` là meta-command của `psql`, đọc file ở **máy chạy psql** rồi truyền qua kết nối. Đây thường là lựa chọn phù hợp khi file CSV nằm trên laptop/CI runner, còn PostgreSQL chạy trong Docker hoặc remote.

**Chú ý:** bảng `san_pham` từ seed cơ bản đã có ID 101–104. Nếu chạy `\copy` vào bảng đó mà không reset/loại dữ liệu cũ, sẽ gặp lỗi khóa chính. Muốn dùng CSV làm nguồn seed thay cho các `INSERT` sản phẩm, hãy bỏ phần `INSERT` tương ứng trong bản seed thay thế, hoặc nhập CSV vào staging table và hợp nhất bằng UPSERT có kiểm soát.

### 12.3. \copy không phải SQL thuần

Lệnh `\copy` hoạt động trong `psql`, nhưng không được gửi nguyên văn như một câu SQL thông thường từ JDBC hoặc query editor chỉ nhận SQL. Nếu cần dữ liệu từ ứng dụng, có thể dùng driver PostgreSQL với COPY API hỗ trợ hoặc gửi các `INSERT` parametrized.

### 12.4. CSV và locale

Khi dùng CSV:

- Chốt encoding UTF-8.
- Chọn delimiter và quoting rõ ràng.
- Ghi cách biểu diễn NULL, boolean, số và timestamp.
- Không phụ thuộc cách Excel tự đổi định dạng ID, dấu phân cách thập phân hoặc giá trị ngày.
- Đưa tệp CSV vào version control nếu không chứa dữ liệu nhạy cảm.

Nếu CSV có dấu phẩy trong tên hoặc văn bản, phải tuân thủ quoting CSV. Không split thủ công theo dấu phẩy rồi mong dữ liệu luôn đúng.

## 13. Seed trong Docker: database tạm và vòng đời volume

Docker giúp nhiều người chạy PostgreSQL cùng phiên bản major trên máy cá nhân. Ví dụ cấu hình `compose.yaml` cho phòng lab:

~~~yaml
services:
  db:
    image: postgres:16
    env_file:
      - .env
    ports:
      - "127.0.0.1:55432:5432"
    volumes:
      - pg_seed_data:/var/lib/postgresql/data

volumes:
  pg_seed_data:
~~~

File `.env` ở máy local chứa cấu hình cho container:

~~~text
POSTGRES_USER=lab_user
POSTGRES_DB=pg_seed_lab
POSTGRES_PASSWORD=<mật-khẩu-local-không-commit>
~~~

Giá trị password trong ví dụ là chỗ điền, không phải mật khẩu hợp lệ đã được thiết lập. Không commit file chứa secret lên Git; dùng `.gitignore` và cách phân phối cấu hình phù hợp.

Khởi động:

~~~bash
docker compose up -d
~~~

Kết nối từ máy host, nơi đã cài `psql`:

~~~bash
psql -X -h 127.0.0.1 -p 55432 \
  -U lab_user -d pg_seed_lab
~~~

Nạp seed:

~~~bash
psql -X -v ON_ERROR_STOP=1 --single-transaction \
  -h 127.0.0.1 -p 55432 \
  -U lab_user -d pg_seed_lab \
  -f sql/seed.sql
~~~

Các cổng ví dụ:

- Bên trong container, PostgreSQL lắng nghe cổng 5432 theo cấu hình mặc định của image.
- Ở máy host, ví dụ ánh xạ `127.0.0.1:55432` tới cổng 5432 của container.
- Chỉ bind loopback cho mục đích lab, không tự mở PostgreSQL ra mạng công cộng.

### 13.1. Vì sao thay file init.sql mà container không tự nạp lại?

Với các image PostgreSQL Docker phổ biến, script đặt trong `/docker-entrypoint-initdb.d` thường chỉ được xử lý khi **data directory chưa được khởi tạo**. Nếu volume đã chứa cluster PostgreSQL, restart container không tự chạy lại những script khởi tạo.

Đừng dựa vào việc restart container để bảo đảm seed chạy lại. Trong bài này, **nạp chủ động bằng lệnh `psql -f sql/seed.sql`** nên kết quả không phụ thuộc vào cơ chế init-only.

### 13.2. Cảnh báo về volume

Lệnh xóa volume như `docker compose down -v` có thể làm mất toàn bộ dữ liệu PostgreSQL trong volume của dự án. Chỉ thực hiện khi chắc chắn volume là dữ liệu lab có thể xóa. Không cần xóa volume để thử lại bộ seed: script đã tự reset schema `lab_seed`.

### 13.3. Cố định version của image

`postgres:16` cố định nhánh major trong ví dụ, nhưng patch release có thể thay đổi theo thời gian. Nếu một bài test yêu cầu môi trường **giống chính xác** giữa mọi lần chạy, nên ghi version cụ thể hoặc image digest được kiểm soát và dùng cùng extension, collation/locale, config và client version theo quy trình dự án.

## 14. Seed trong CI và automated tests

Trong CI, mục tiêu là mỗi lần chạy test khởi đầu từ **database riêng, có dữ liệu xác định**.

Một trình tự tổng quát:

~~~text
[1] Khởi động PostgreSQL test container/service
       |
       v
[2] Tạo database test riêng hoặc schema riêng
       |
       v
[3] Chạy schema migration (nếu dự án có)
       |
       v
[4] Nạp seed/fixtures có phiên bản
       |
       v
[5] Kiểm tra dữ liệu bắt buộc
       |
       v
[6] Chạy integration tests
       |
       v
[7] Thu thập log, dọn môi trường test
~~~

Với file tự chứa đang học, các bước migration và nạp cơ bản có thể gộp thành `seed.sql`. Với dự án có schema migration chuẩn, nên tách migration khỏi seed để không bị hai nguồn cấu trúc cạnh tranh.

### 14.1. Dùng biến môi trường cho kết nối

`psql` có thể lấy một số thông số kết nối từ các biến môi trường như `PGHOST`, `PGPORT`, `PGUSER` và `PGDATABASE`:

~~~bash
psql -X -v ON_ERROR_STOP=1 \
  --single-transaction -f sql/seed.sql
~~~

Ở đây giả định runner đã cung cấp biến kết nối và secret phù hợp; câu lệnh không chứa thông tin xác thực. Các bước CI phải dừng khi `psql` trả exit code lỗi. Đừng nuốt lỗi rồi tiếp tục chạy test trên một database nạp dở.

### 14.2. Tách dữ liệu mẫu chung và fixture theo bài test

Không nên đưa mọi trường hợp lỗi vào cùng seed cơ bản. Có thể tổ chức:

~~~text
sql/
  seed.sql              # Bộ dữ liệu chuẩn dùng chung
  fixtures/
    empty-order.sql     # Một đơn không có chi tiết
    cancelled-order.sql # Dữ liệu cho test đơn đã hủy
    many-records.sql    # Dữ liệu số lượng lớn
~~~

Mỗi test suite cần biết fixture nào được nạp, thứ tự chạy và cách hoàn tác. Nếu test thay đổi dữ liệu, nên bắt đầu từ một database/schema sạch ở lần chạy kế tiếp.

## 15. Đồng bộ sequence khi dùng IDENTITY hoặc SERIAL

Ví dụ cơ bản dùng ID `INTEGER` tự nhập. Trong ứng dụng thực, các bảng có thể dùng:

~~~sql
CREATE TABLE lab_seed.nhat_ky_seed (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    noi_dung TEXT NOT NULL
);
~~~

Có thể chèn ID cố định:

~~~sql
INSERT INTO lab_seed.nhat_ky_seed (id, noi_dung)
VALUES (10, 'Dòng seed có ID cố định');
~~~

Nhưng khi chèn explicit ID vào cột identity `BY DEFAULT`, sequence gắn với cột **không bắt buộc tự nhảy tới 11**. Lần sau chèn một hàng không chỉ định ID có thể lấy giá trị từ sequence đang ở mức thấp và gặp xung đột khi dãy tăng tới ID đã chiếm.

Có thể đồng bộ sequence sau khi đã nạp các ID cố định:

~~~sql
SELECT setval(
    pg_get_serial_sequence('lab_seed.nhat_ky_seed', 'id'),
    (SELECT max(id) FROM lab_seed.nhat_ky_seed),
    true
);
~~~

Đoạn này giả định bảng **có ít nhất một hàng** và đang sở hữu sequence tương ứng. Tham số `true` nghĩa là lần gọi `nextval` kế tiếp thường sinh giá trị sau số đã đặt. Với sequence trống hoặc cấu hình bước tăng khác, cần xử lý theo quy tắc cụ thể.

Ví dụ:

~~~sql
INSERT INTO lab_seed.nhat_ky_seed (noi_dung)
VALUES ('Dòng tự sinh ID');

SELECT id, noi_dung
FROM lab_seed.nhat_ky_seed
ORDER BY id;
~~~

Với sequence mặc định tăng 1 và hàng ID 10 được seed trước đó, dòng mới thường có ID 11.

### 15.1. SERIAL và IDENTITY khác gì trong seed?

- `SERIAL` là cú pháp tiện ích tạo sequence, default và cơ chế sở hữu liên quan.
- `GENERATED ... AS IDENTITY` là cách khai báo identity theo SQL hiện đại của PostgreSQL.
- `GENERATED ALWAYS AS IDENTITY` yêu cầu cơ chế `OVERRIDING SYSTEM VALUE` nếu cố ý chèn ID explicit.
- `GENERATED BY DEFAULT AS IDENTITY` cho phép chèn giá trị explicit thông thường.

Nếu seed sử dụng explicit IDs, hãy biết sequence/identity đang dùng và đồng bộ sau nạp khi cần. Không giả định sequence được rollback giống mọi thay đổi dữ liệu trong transaction; các giá trị sequence đã cấp có thể tạo khoảng trống là hành vi bình thường.

## 16. Transaction, rollback và tính nguyên tử của lần nạp

Nạp seed bao gồm nhiều câu lệnh. Nếu bước cuối thất bại nhưng các bước trước đã commit, database có thể ở trạng thái nửa mới, nửa cũ.

Ví dụ phương án **không có transaction bao bọc**:

~~~text
DROP schema       -> thành công, commit
CREATE tables     -> thành công, commit
INSERT customers  -> thành công, commit
INSERT orders     -> lỗi khóa ngoại
Kết quả: database nạp dở
~~~

Phương án `psql --single-transaction -v ON_ERROR_STOP=1` cho seed toàn SQL transactional:

~~~text
BEGIN
  DROP SCHEMA lab_seed
  CREATE SCHEMA lab_seed
  CREATE TABLE...
  INSERT...
  DO kiểm chứng...
COMMIT chỉ khi toàn bộ lệnh thành công

Nếu lỗi -> transaction bị rollback
~~~

Trong PostgreSQL, nhiều thao tác DDL như `CREATE TABLE`, `DROP TABLE` được hỗ trợ trong transaction. Tuy nhiên không phải mọi lệnh quản trị PostgreSQL đều được phép chạy trong transaction block, ví dụ `CREATE DATABASE`; vì thế bước tạo database được thực hiện **riêng** trước khi chạy file seed.

### 16.1. Thực hành lỗi khóa ngoại có kiểm soát

Trên schema lab đã nạp, mở một session thử:

~~~sql
BEGIN;

INSERT INTO lab_seed.don_hang
    (don_hang_id, khach_hang_id, dat_luc, trang_thai)
VALUES
    (9999, 999999,
        TIMESTAMPTZ '2026-03-01 10:00:00+00',
        'moi');

-- Câu INSERT sẽ lỗi vì khách 999999 không tồn tại.
-- Transaction hiện ở trạng thái aborted.

ROLLBACK;
~~~

Lỗi vi phạm khóa ngoại cho thấy PostgreSQL bảo vệ tính nhất quán. Sau khi một câu lệnh lỗi bên trong transaction, các lệnh tiếp theo thường bị từ chối cho đến khi rollback (hoặc xử lý bằng savepoint phù hợp). Không cố `COMMIT` một transaction đã thất bại rồi cho rằng mọi bước trước vẫn hợp lệ.

Bài thực hành lỗi này **không được đặt trong `seed.sql`**; file seed chính phải kết thúc thành công.

## 17. Kiểm tra dữ liệu bằng assertion thay vì nhìn bảng bằng mắt

Ngoài `DO` kiểm tra số dòng, có thể kiểm tra những bất biến khác.

### 17.1. Kiểm tra tổng tiền của đơn 1001

~~~sql
DO $check_total$
DECLARE
    v_total NUMERIC(14, 2);
BEGIN
    SELECT SUM(so_luong * don_gia)
    INTO v_total
    FROM lab_seed.chi_tiet_don_hang
    WHERE don_hang_id = 1001;

    IF v_total IS DISTINCT FROM 480000.00 THEN
        RAISE EXCEPTION
            'Unexpected total for order 1001: %', v_total;
    END IF;
END;
$check_total$;
~~~

`IS DISTINCT FROM` so sánh kể cả trường hợp NULL, tránh việc một phép `<>` với NULL không cho kết quả boolean như mong muốn.

### 17.2. Kiểm tra không có email trùng

~~~sql
SELECT email, count(*) AS so_lan
FROM lab_seed.khach_hang
GROUP BY email
HAVING count(*) > 1;
~~~

Vì bảng có `UNIQUE (email)`, truy vấn kỳ vọng không trả dòng nào; ràng buộc giúp phát hiện sớm trong lúc ghi.

### 17.3. Kiểm tra số dòng với bộ seed lớn

~~~sql
SELECT count(*) AS so_khach
FROM lab_seed.khach_hang;

SELECT count(*) AS so_don
FROM lab_seed.don_hang;

SELECT count(*) AS so_dong_chi_tiet
FROM lab_seed.chi_tiet_don_hang;
~~~

Kỳ vọng là `1004`, `5004` và `5006` **sau khi đã chạy đủ ba phần của seed lớn** trên seed cơ bản. Nếu chỉ chạy seed cơ bản, kỳ vọng là `4`, `4` và `6`. Không dùng cùng bộ assertion cho hai cấu hình dữ liệu khác nhau mà không ghi rõ profile.

### 17.4. Kiểm tra hash dữ liệu khi cần so sánh nhiều môi trường

Có thể tạo chữ ký dựa trên tập kết quả có thứ tự:

~~~sql
SELECT md5(
    string_agg(
        khach_hang_id::text || ':' || email,
        '|'
        ORDER BY khach_hang_id
    )
) AS fingerprint
FROM lab_seed.khach_hang;
~~~

Đây là checksum ở mức biểu diễn dữ liệu được chọn; không chứng minh toàn bộ database hoàn toàn giống nhau. Nếu cần đối soát chặt, phải định nghĩa rõ cột, cách chuẩn hóa NULL, timezone, numeric và thứ tự. MD5 trong ví dụ chỉ phục vụ **phát hiện khác biệt đơn giản** cho bài học, không dùng làm giải pháp bảo mật hoặc chống giả mạo.

## 18. Giữ bộ dữ liệu mẫu ổn định qua nhiều phiên bản PostgreSQL

SQL seed có thể cố định dữ liệu, nhưng môi trường chạy cũng ảnh hưởng kết quả và hiệu năng.

Những yếu tố cần ghi lại:

- Phiên bản PostgreSQL server và client `psql`.
- Encoding của database và file.
- Timezone, locale và collation.
- Extensions được cài.
- Schema migration version.
- Tên role và phạm vi quyền.
- Kiểu dữ liệu, quy tắc làm tròn và số học.
- Version của script seed.
- Những biến môi trường ảnh hưởng cách thực thi.

Ví dụ việc sắp xếp chuỗi có dấu có thể khác giữa các collation/locale. Vì vậy khi bài tập cần so sánh kết quả có thứ tự, **không dựa vào thứ tự mặc định của TEXT trên mọi hệ thống** trừ khi collation được quy định và thử nghiệm. Với seed cơ bản, sắp xếp theo ID là lựa chọn rõ ràng hơn.

### 18.1. Timestamps và định dạng đầu ra

Hai session với timezone khác nhau có thể in `TIMESTAMPTZ` dưới dạng giờ địa phương khác nhau dù chỉ cùng một thời điểm. Để kiểm chứng bằng văn bản, có thể chuẩn hóa:

~~~sql
SELECT
    don_hang_id,
    dat_luc AT TIME ZONE 'UTC' AS dat_luc_utc
FROM lab_seed.don_hang
ORDER BY don_hang_id;
~~~

`AT TIME ZONE 'UTC'` trong biểu thức này chuyển giá trị `TIMESTAMPTZ` thành thời gian local không kèm timezone tương ứng với UTC để hiển thị. Khi lưu/chuyển dữ liệu giữa hệ thống, cần hiểu rõ kiểu dữ liệu và thời điểm mà kết quả biểu thị.

## 19. Seed và dữ liệu nhạy cảm

Không nên lấy bản sao database production chứa tên, email, số điện thoại hoặc giao dịch thật rồi đưa thẳng vào Git để làm seed.

Với ví dụ thực hành, sử dụng:

- Email với domain dự trữ cho tài liệu như `example.test`.
- Tên và dữ liệu giả, không gắn với người dùng thật.
- Giá trị thanh toán minh họa.
- Không chứa mật khẩu, token, API key, số tài khoản hoặc thông tin nhận dạng thực.

Nếu nhóm cần dữ liệu gần với production, phải dùng quy trình **ẩn danh/masking có kiểm chứng**, hạn chế truy cập và xác định thời hạn lưu giữ. Việc thay tên đơn thuần chưa chắc bảo vệ được dữ liệu nhạy cảm nếu còn ID, địa chỉ, timestamp và những trường liên kết có thể tái nhận diện.

## 20. Những lỗi thường gặp khi nạp seed

### Lỗi 1: Chạy script reset trên database không đúng

`DROP SCHEMA ... CASCADE` có thể xóa các đối tượng phụ thuộc.

**Cách xử lý:** chỉ dùng database/schema lab riêng, kiểm tra `current_database()` và endpoint trước khi chạy; không dùng script reset với dữ liệu thật.

### Lỗi 2: Chạy seed hai lần rồi có hàng trùng

Script chỉ có `INSERT` vào bảng giữ nguyên nên lần hai gặp `duplicate key` hoặc tạo bản ghi lặp nếu thiếu ràng buộc.

**Cách xử lý:** chọn reset-and-seed hoặc UPSERT đúng khóa, không dựa vào thao tác tay.

### Lỗi 3: Dùng now() khiến kết quả thay đổi

Một báo cáo lọc thời gian sẽ cho kết quả khác vào ngày hôm sau.

**Cách xử lý:** dùng timestamp cố định có offset nếu bài tập cần dữ liệu ổn định.

### Lỗi 4: Dùng random() không kiểm soát

Giá trị và phân bố thay đổi giữa các lần nạp.

**Cách xử lý:** dùng công thức phụ thuộc ID hoặc bộ fixture có version khi cần kết quả xác định.

### Lỗi 5: Chèn bảng con trước bảng cha

Khóa ngoại khiến insert lỗi vì chưa có dòng được tham chiếu.

**Cách xử lý:** nạp theo quan hệ phụ thuộc; không tắt ràng buộc tùy tiện.

### Lỗi 6: Quên dùng ON_ERROR_STOP

Script có thể tiếp tục chạy sau một câu lệnh lỗi, tạo trạng thái khó nhận biết.

**Cách xử lý:** dùng `-v ON_ERROR_STOP=1` và kiểm tra exit code ở terminal/CI.

### Lỗi 7: Bỏ qua transaction

Một phần seed được commit dù lệnh sau lỗi.

**Cách xử lý:** dùng `--single-transaction` cho các lệnh transactional phù hợp và không thêm lệnh quản trị không được phép chạy trong transaction block.

### Lỗi 8: Quên reset sequence sau explicit ID

Lần insert không chỉ định ID sau đó có thể va chạm khóa chính.

**Cách xử lý:** đồng bộ sequence của `SERIAL`/`IDENTITY BY DEFAULT` khi seed ID cố định, nếu cần dùng auto-generated ID tiếp.

### Lỗi 9: File CSV bị sai encoding

Tên tiếng Việt bị biến thành ký tự lỗi.

**Cách xử lý:** lưu UTF-8 và kiểm tra `client_encoding`, `server_encoding`, công cụ editor/export.

### Lỗi 10: Nhầm COPY và \copy

File trên laptop nhưng SQL `COPY FROM '/home/...csv'` lại yêu cầu server đọc file.

**Cách xử lý:** dùng `\copy` trong `psql` cho file client, hoặc đưa file tới vị trí server được phép theo quy trình phù hợp.

### Lỗi 11: Docker restart không nạp lại init script

Volume đã có cluster, nên init script chạy một lần không tự chạy lại.

**Cách xử lý:** thực thi seed bằng `psql -f` như một bước chủ động.

### Lỗi 12: Dựa vào SELECT * không ORDER BY

Cùng dữ liệu nhưng thứ tự dòng khác.

**Cách xử lý:** luôn `ORDER BY` khi cần kết quả có thứ tự.

### Lỗi 13: Dùng dữ liệu synthetic để kết luận hiệu năng production

Dãy ID đều và giá trị phân bố đơn giản không phản ánh hot keys hay skew.

**Cách xử lý:** dùng synthetic data cho học cú pháp; benchmark sản xuất cần dữ liệu/tải đại diện.

### Lỗi 14: Nạp vào schema sai do search_path

Nếu câu SQL không có tên schema, dữ liệu có thể được tạo trong `public` hoặc schema khác tùy `search_path`.

**Cách xử lý:** trong seed dùng tên đầy đủ như `lab_seed.khach_hang`, hoặc đặt `search_path` rõ ràng và kiểm tra môi trường.

### Lỗi 15: Chỉ kiểm tra file seed đã chạy, không kiểm tra kết quả

Lệnh kết thúc nhưng data bị thiếu hoặc giá trị không đúng mong đợi.

**Cách xử lý:** thêm assertion số hàng, khóa ngoại và chỉ số nghiệp vụ như tổng tiền.

## 21. Quy trình thực hiện từ đầu đến cuối

Để luyện bài trên máy riêng:

**Bước 1 — Có PostgreSQL server và psql:** xác nhận kết nối, role và version.

**Bước 2 — Tạo database `pg_seed_lab`:** dùng `createdb` một lần nếu cần và role có quyền.

**Bước 3 — Lưu `sql/seed.sql` bằng UTF-8:** dùng đúng nội dung hoàn chỉnh ở mục 6.

**Bước 4 — Chạy bằng `psql -X -v ON_ERROR_STOP=1 --single-transaction -f sql/seed.sql`:** chọn đúng host, port, user, database.

**Bước 5 — Kiểm tra bốn bảng:** kỳ vọng 4 khách, 4 sản phẩm, 4 đơn và 6 dòng chi tiết.

**Bước 6 — Chạy JOIN tính tổng tiền:** đơn 1001 phải có tổng 480000.00; đơn 1004 là 600000.00.

**Bước 7 — Chạy lại `seed.sql`:** kết quả và số hàng không thay đổi.

**Bước 8 — Nếu muốn dữ liệu lớn, tạo `sql/seed-large.sql`:** đặt ba đoạn `generate_series` ở mục 10, nạp lần lượt và kiểm tra tổng dòng.

**Bước 9 — Thử một ca lỗi trong transaction riêng:** dùng khóa ngoại sai và `ROLLBACK` như mục 16.

**Bước 10 — Đưa seed và hướng dẫn vào version control:** bảo đảm không có secret hoặc dữ liệu cá nhân thật.

Khi làm theo nhóm, mọi người nên sử dụng cùng phiên bản file, cùng profile seed cơ bản/mở rộng và cùng quy tắc xác minh. Đây là nền tảng để các bài học tiếp theo về `JOIN`, `GROUP BY`, index, transaction và `EXPLAIN` có dữ liệu đầu vào đáng tin.

## 22. Bài tập tự luyện

### Bài 1 — Xác minh kết quả cố định

Sau khi chạy seed cơ bản, hãy viết SQL đếm khách hàng, sản phẩm, đơn hàng và chi tiết. Kết quả phải là bao nhiêu?

**Gợi ý:** lần lượt 4, 4, 4 và 6.

### Bài 2 — Tính tổng đơn

Viết SQL tính tổng tiền cho đơn 1001 từ `so_luong * don_gia` mà không lấy giá hiện tại ở bảng sản phẩm.

**Gợi ý:** hai dòng 2 × 150000 và 1 × 180000, tổng 480000.00.

### Bài 3 — Thêm một khách có thể chạy lại

Tạo khách hàng ID 5 với email `ha@example.test` sao cho chạy script hai lần vẫn chỉ có một dòng và giá trị cuối đúng seed.

**Gợi ý:** `INSERT ... ON CONFLICT (khach_hang_id) DO UPDATE SET ...`.

### Bài 4 — Khóa ngoại

Thử tạo đơn với `khach_hang_id = 999999`. Vì sao bị từ chối?

**Gợi ý:** không có khách hàng ID đó, ràng buộc `REFERENCES` chặn dữ liệu mồ côi.

### Bài 5 — Thử lỗi trong transaction

Bắt đầu transaction, chèn một dòng hợp lệ rồi một dòng sai khóa ngoại. Có thể tiếp tục ghi bình thường mà không rollback không?

**Gợi ý:** sau lỗi, transaction ở trạng thái aborted; cần rollback hoặc xử lý bằng savepoint phù hợp.

### Bài 6 — Sinh số lượng lớn

Viết `generate_series` tạo 2.000 sản phẩm có ID 50001–52000, SKU duy nhất và giá xác định theo ID.

**Gợi ý:** dùng `'SKU-' || g::text`, `1000 + ((g * 7) % 90000)` và điều kiện `ON CONFLICT` nếu muốn chạy lặp.

### Bài 7 — Thời gian xác định

Vì sao dùng `TIMESTAMPTZ '2026-01-10 08:00:00+00'` thích hợp hơn `now()` cho fixture?

**Gợi ý:** thời điểm cố định không phụ thuộc ngày chạy; test thời gian có thể dự đoán.

### Bài 8 — CSV trong Docker

Bạn có file `products.csv` trên máy host nhưng PostgreSQL ở container. Nên dùng `COPY FROM '/home/...'` hay `\copy` từ `psql` host?

**Gợi ý:** `\copy` đọc file ở client, giúp không phải đặt file trong filesystem của server.

### Bài 9 — Idempotency và dữ liệu bị sửa

Một dòng ID 5 đã tồn tại nhưng email khác seed. `ON CONFLICT DO NOTHING` có sửa được email không?

**Gợi ý:** không; cần UPSERT `DO UPDATE` nếu muốn trạng thái cuối khớp seed.

### Bài 10 — Sequence

Một bảng `GENERATED BY DEFAULT AS IDENTITY` đã nạp explicit ID 100. Vì sao lần insert sau có thể gặp trùng ID nếu không đồng bộ sequence?

**Gợi ý:** chèn explicit ID không tự bảo đảm sequence cập nhật tới mốc đã chèn.

### Bài 11 — CI

Hãy đề xuất ba tiêu chí để CI dừng ngay khi nạp seed lỗi và không chạy test trên dữ liệu nạp dở.

**Gợi ý:** `ON_ERROR_STOP=1`, transaction bao bọc, kiểm tra exit code/assertions.

### Bài 12 — Tính tái tạo

Một nhóm dùng cùng tệp seed nhưng khác locale, timezone và version image. Tập dữ liệu logic có thể giống nhau nhưng kết quả hiển thị/sắp xếp có thể khác ở đâu?

**Gợi ý:** thời gian được format theo timezone, chuỗi `TEXT` theo collation, thứ tự truy vấn thiếu `ORDER BY` và sự khác biệt tính năng giữa các bản server.

## 23. Ghi nhớ

- **Seed data** là bộ dữ liệu khởi tạo để học và kiểm thử; nó không thay thế migration hoặc backup.
- Muốn **tái tạo được**, cần có dữ liệu xác định, lệnh nạp rõ ràng, giới hạn phạm vi và phép kiểm chứng.
- File `seed.sql` nên được **version control**, lưu UTF-8 và không chứa thông tin nhạy cảm.
- `psql -X -v ON_ERROR_STOP=1 --single-transaction -f ...` là cách nạp phù hợp khi file chỉ chứa những thao tác được phép chạy trong một transaction.
- Reset-and-seed có thể tạo trạng thái y hệt sau mỗi lần chạy, nhưng **chỉ dùng trên schema/database học tập có thể xóa**.
- `ON CONFLICT DO NOTHING` chống lỗi trùng theo khóa được chỉ định nhưng không bảo đảm dữ liệu cuối khớp seed; `DO UPDATE` có thể đồng bộ giá trị theo chính sách.
- `generate_series` cùng công thức theo ID tạo dữ liệu lớn có thể lặp lại; `random()` không kiểm soát làm kết quả khó dự đoán.
- Nạp theo thứ tự **bảng cha trước, bảng con sau** và để PostgreSQL kiểm tra khóa ngoại.
- `COPY` đọc file ở phía server; `\copy` trong `psql` đọc file phía client.
- Khi seed explicit ID vào `IDENTITY`/`SERIAL`, hãy xem xét trạng thái sequence.
- Phải **kiểm tra số dòng, quan hệ, tổng tiền và thứ tự hiển thị**, không chỉ thấy công cụ báo chạy thành công.
- Cùng dữ liệu chưa chắc đồng nghĩa cùng thứ tự truy vấn hoặc cùng benchmark; hãy kiểm soát timezone, collation, version và workload.

Một bộ dữ liệu mẫu tốt cho PostgreSQL không cần phức tạp, nhưng cần **được thiết kế để người khác có thể chạy lại từ đầu, kiểm chứng được kết quả và hiểu chính xác phạm vi mà script thay đổi**. Đó là nền tảng cho việc học SQL, viết integration test và vận hành môi trường phát triển nhất quán.
