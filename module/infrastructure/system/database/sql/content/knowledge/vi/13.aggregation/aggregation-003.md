# SUM, AVG, MIN, MAX và cách xử lý NULL trong SQL

Trong các hệ thống bán hàng, quản lý nhân sự hoặc báo cáo, câu hỏi thường không chỉ là “có những bản ghi nào?” mà còn là **tổng doanh thu bao nhiêu**, **giá trị trung bình là bao nhiêu**, **mức thấp nhất và cao nhất là gì**. SQL cung cấp các hàm tổng hợp (*aggregate functions*) để biến nhiều giá trị thành một kết quả:

- `SUM`: tính tổng các giá trị số.
- `AVG`: tính giá trị trung bình cộng của các giá trị số.
- `MIN`: lấy giá trị nhỏ nhất.
- `MAX`: lấy giá trị lớn nhất.

Tuy nhiên, kết quả sẽ dễ bị hiểu sai khi dữ liệu có **`NULL`**, khi một nhóm không có hàng nào, khi dùng `LEFT JOIN` hoặc khi người viết truy vấn nhầm **giá trị bằng 0** với **giá trị chưa biết**.

Bài học thuộc chương **Tổng hợp dữ liệu** của module Database SQL. Ví dụ chính dùng **PostgreSQL** và một bộ dữ liệu tự chứa; những quy tắc phổ biến của SQL được giải thích cùng các khác biệt cần chú ý ở một số DBMS khác.

## 1. Hàm tổng hợp hoạt động như thế nào?

Giả sử có các giá trị doanh thu của những đơn hàng:

~~~text
250000, NULL, 150000, 0, NULL, 300000, NULL, NULL
~~~

Với `SUM`, `AVG`, `MIN` và `MAX` thông thường, SQL **bỏ qua các giá trị NULL** khi tính trên biểu thức đầu vào. Các giá trị thực sự tham gia là:

~~~text
250000, 150000, 0, 300000
~~~

Ta có:

| Phép tổng hợp | Kết quả | Giải thích |
|---|---:|---|
| `SUM(tong_tien)` | 700000 | 250000 + 150000 + 0 + 300000 |
| `AVG(tong_tien)` | 175000 | 700000 / **4 giá trị không NULL** |
| `MIN(tong_tien)` | 0 | Giá trị nhỏ nhất có mặt là số 0 |
| `MAX(tong_tien)` | 300000 | Giá trị lớn nhất |
| `COUNT(tong_tien)` | 4 | Đếm giá trị không NULL |
| `COUNT(*)` | 8 | Đếm tất cả hàng, kể cả hàng có tong_tien NULL |

**Hai quy tắc nền tảng:**

1. `NULL` không tự được coi là 0. Nó biểu thị việc thiếu hoặc chưa biết giá trị, tùy mô hình dữ liệu.
2. `AVG(x)` chia tổng các giá trị không NULL cho **số giá trị không NULL**, không chia cho tổng số hàng.

Hình dung luồng tính toán:

~~~text
Các hàng đầu vào
    │
    ├── Có giá trị số: 250000, 150000, 0, 300000
    │       ├── SUM → 700000
    │       ├── AVG → 175000
    │       ├── MIN → 0
    │       └── MAX → 300000
    │
    └── NULL: 4 hàng → không tham gia bốn phép tính trên
            └── COUNT(*) vẫn tính các hàng này
~~~

Khi **không có bất kỳ giá trị không NULL nào**, các hàm này có hành vi khác `COUNT`; chúng ta sẽ phân tích rõ ở phần 4.

## 2. Chuẩn bị dữ liệu PostgreSQL

Để có thể chạy tất cả ví dụ từ đầu, ta tạo một hệ thống đơn giản gồm khách hàng và đơn hàng.

**Môi trường:** PostgreSQL trong database thử nghiệm. Các bảng sử dụng `TEMP` nên tồn tại trong phiên kết nối hiện tại. Nếu phần mềm SQL mở một connection khác, các bảng tạm vừa tạo có thể không còn nhìn thấy; hãy giữ cùng một phiên trong khi học.

### 2.1. Tạo bảng và ràng buộc

~~~sql
CREATE TEMP TABLE agg_khach_hang (
    id INTEGER PRIMARY KEY,
    ho_ten VARCHAR(100) NOT NULL,
    khu_vuc VARCHAR(20) NOT NULL
);

CREATE TEMP TABLE agg_don_hang (
    id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL
        REFERENCES agg_khach_hang(id),
    ngay_dat DATE NOT NULL,
    trang_thai VARCHAR(20) NOT NULL
        CHECK (trang_thai IN ('NEW', 'PAID', 'CANCELLED')),
    tong_tien NUMERIC(12,2)
        CHECK (tong_tien >= 0)
);
~~~

Cột `tong_tien` **có thể NULL** vì không có `NOT NULL`. Ràng buộc `CHECK (tong_tien >= 0)` từ chối giá trị âm, nhưng trong PostgreSQL không tự từ chối NULL: biểu thức kiểm tra trở thành UNKNOWN và CHECK thông thường chấp nhận trường hợp này.

Trong bài học, ý nghĩa giả định:

- `tong_tien = 0`: đã ghi nhận giá trị là **không đồng**.
- `tong_tien > 0`: đã ghi nhận số tiền dương.
- `tong_tien IS NULL`: chưa có số liệu tiền hoặc chưa xác định được giá trị.

Đây là quy ước của dữ liệu mẫu, không phải quy tắc cho mọi hệ thống thương mại. Trong phần mềm thật, một đơn PAID có tổng NULL có thể là tình trạng cần rà soát.

### 2.2. Nạp dữ liệu

~~~sql
INSERT INTO agg_khach_hang (id, ho_ten, khu_vuc) VALUES
    (1, 'An',   'Bắc'),
    (2, 'Bình', 'Nam'),
    (3, 'Chi',  'Bắc'),
    (4, 'Dũng', 'Trung');

INSERT INTO agg_don_hang
    (id, khach_hang_id, ngay_dat, trang_thai, tong_tien)
VALUES
    (101, 1, DATE '2026-11-01', 'PAID',      250000),
    (102, 1, DATE '2026-11-03', 'NEW',       NULL),
    (103, 1, DATE '2026-11-05', 'PAID',      150000),
    (104, 2, DATE '2026-11-02', 'PAID',      0),
    (105, 2, DATE '2026-11-04', 'CANCELLED', NULL),
    (106, 2, DATE '2026-11-07', 'PAID',      300000),
    (107, 4, DATE '2026-11-08', 'NEW',       NULL),
    (108, 4, DATE '2026-11-09', 'PAID',      NULL);
~~~

### 2.3. Quan sát các dòng

~~~sql
SELECT
    dh.id,
    kh.ho_ten,
    dh.trang_thai,
    dh.ngay_dat,
    dh.tong_tien
FROM agg_don_hang AS dh
JOIN agg_khach_hang AS kh
    ON kh.id = dh.khach_hang_id
ORDER BY dh.id;
~~~

| id | ho_ten | trang_thai | ngay_dat | tong_tien |
|---:|---|---|---|---:|
| 101 | An | PAID | 2026-11-01 | 250000 |
| 102 | An | NEW | 2026-11-03 | NULL |
| 103 | An | PAID | 2026-11-05 | 150000 |
| 104 | Bình | PAID | 2026-11-02 | 0 |
| 105 | Bình | CANCELLED | 2026-11-04 | NULL |
| 106 | Bình | PAID | 2026-11-07 | 300000 |
| 107 | Dũng | NEW | 2026-11-08 | NULL |
| 108 | Dũng | PAID | 2026-11-09 | NULL |

Lưu ý: **Chi có trong bảng khách hàng nhưng chưa có đơn hàng**. Dũng có hai đơn nhưng **cả hai giá trị tong_tien đều NULL**. Bình có một đơn với tiền bằng **0**. Đây là ba trường hợp khác nhau, rất quan trọng khi dùng tổng hợp và JOIN.

## 3. SUM: tính tổng trên những giá trị không NULL

### 3.1. Cú pháp cơ bản

~~~sql
SELECT SUM(tong_tien) AS tong_tat_ca
FROM agg_don_hang;
~~~

Kết quả: `700000`.

Phép tính tương ứng:

\[
250000 + 150000 + 0 + 300000 = 700000
\]

Bốn dòng có `tong_tien = NULL` không tham gia phép cộng. Số 0 vẫn là **giá trị hợp lệ có tham gia**, nhưng không thay đổi kết quả tổng.

### 3.2. SUM của biểu thức

`SUM` không nhất thiết chỉ nhận tên cột; nó có thể tổng hợp một biểu thức tính toán:

~~~sql
-- Ví dụ cú pháp với bảng dòng hàng có các cột so_luong, don_gia:
SELECT SUM(so_luong * don_gia) AS tong_gia_tri
FROM chi_tiet_don;
~~~

Câu trên là **mẫu cho bảng giả định `chi_tiet_don`**, không phải bảng tạm đã tạo ở phần 2. Nếu mỗi dòng có số lượng và đơn giá, `SUM(so_luong * don_gia)` cộng thành tiền của từng dòng.

**Quan trọng:** nếu `so_luong` hoặc `don_gia` NULL, phép nhân của dòng đó cho NULL và sẽ bị `SUM` bỏ qua. Nếu nghiệp vụ bắt buộc đủ giá/số lượng, nên đặt `NOT NULL` ngay trong định nghĩa bảng và xác minh dữ liệu.

### 3.3. SUM không tự phân biệt trạng thái đơn hàng

~~~sql
SELECT SUM(tong_tien)
FROM agg_don_hang;
~~~

Kết quả 700000 là tổng trên **tất cả trạng thái** có giá trị tiền, vì chưa có điều kiện lọc. Nếu muốn tổng riêng các đơn đã thanh toán:

~~~sql
SELECT SUM(tong_tien) AS tong_paid
FROM agg_don_hang
WHERE trang_thai = 'PAID';
~~~

Kết quả của dữ liệu này vẫn là 700000, vì những đơn NEW và CANCELLED đều đang có tiền NULL. Đó là **đặc điểm ngẫu nhiên của dữ liệu mẫu**, không phải bằng chứng rằng điều kiện trạng thái không quan trọng. Trong hệ thống thật, đơn NEW có thể có giá trị tiền và không nên tự động được xem là doanh thu đã thanh toán.

## 4. AVG: trung bình cộng và mẫu số thật sự

`AVG(x)` tính trung bình trên các giá trị `x` **khác NULL**.

~~~sql
SELECT
    AVG(tong_tien) AS trung_binh_tien_don,
    COUNT(*) AS tong_so_don,
    COUNT(tong_tien) AS so_don_co_so_tien
FROM agg_don_hang;
~~~

Kết quả:

| trung_binh_tien_don | tong_so_don | so_don_co_so_tien |
|---:|---:|---:|
| 175000 | 8 | 4 |

Mẫu số của AVG là **4**, không phải 8.

\[
AVG(tong\_tien)
=\frac{250000+150000+0+300000}{4}
=175000
\]

### 4.1. AVG bỏ qua NULL nhưng không bỏ qua số 0

Đơn 104 của Bình có số tiền **0**. Giá trị 0 tham gia AVG và làm trung bình giảm xuống. Đây là điều đúng: số 0 là một dữ kiện, còn NULL là giá trị thiếu.

Một sai lầm phổ biến là cho rằng AVG chỉ tính số dương. Thực tế, nó nhận mọi giá trị **không NULL**, bao gồm 0 hoặc số âm nếu kiểu dữ liệu và ràng buộc cho phép.

### 4.2. AVG(COALESCE(x, 0)) thay đổi ý nghĩa

So sánh:

~~~sql
SELECT
    AVG(tong_tien) AS avg_bo_qua_null,
    AVG(COALESCE(tong_tien, 0)) AS avg_coi_null_la_0
FROM agg_don_hang;
~~~

Kết quả:

| avg_bo_qua_null | avg_coi_null_la_0 |
|---:|---:|
| 175000 | 87500 |

Giải thích:

- `AVG(tong_tien)` có 4 giá trị: 250000, 150000, 0, 300000 → 700000 / 4.
- `AVG(COALESCE(tong_tien, 0))` thay cả 4 NULL thành 0 **trước khi tính AVG** → 700000 / 8.

Không thể nói công thức nào luôn đúng. Nếu NULL nghĩa là “chưa có dữ liệu”, biến nó thành 0 có thể làm sai báo cáo. Nếu nghiệp vụ định nghĩa NULL được **cố ý tính bằng 0**, cần ghi rõ quy tắc đó và cân nhắc vì sao dữ liệu được lưu NULL thay vì 0.

### 4.3. AVG theo đơn hay theo khách hàng?

Trung bình giá trị **đơn hàng** và trung bình **tổng chi tiêu mỗi khách hàng** là hai chỉ số khác nhau.

- `AVG(tong_tien)` trên bảng đơn: trung bình của các đơn có số tiền.
- Tổng hợp `SUM(tong_tien)` theo khách hàng rồi `AVG` bên ngoài: trung bình của các **tổng theo khách hàng**, với cách xử lý nhóm NULL/không có đơn phải được định nghĩa.

Thứ tự tổng hợp quan trọng. Nếu các khách hàng có số đơn khác nhau, trung bình của trung bình nhóm **không tự bằng** trung bình trên mọi đơn. Phần 12 sẽ minh họa trung bình có trọng số.

## 5. MIN và MAX: lấy giá trị nhỏ nhất, lớn nhất

### 5.1. MIN và MAX trên cột số

~~~sql
SELECT
    MIN(tong_tien) AS gia_tri_nho_nhat,
    MAX(tong_tien) AS gia_tri_lon_nhat
FROM agg_don_hang;
~~~

Kết quả:

| gia_tri_nho_nhat | gia_tri_lon_nhat |
|---:|---:|
| 0 | 300000 |

`MIN` bỏ qua NULL và trả **0** vì dữ liệu thực sự có một đơn tổng tiền bằng 0. `MAX` trả 300000. Nếu muốn tìm **giá trị dương nhỏ nhất**, cần lọc:

~~~sql
SELECT MIN(tong_tien) AS tien_duong_nho_nhat
FROM agg_don_hang
WHERE tong_tien > 0;
~~~

Kết quả: `150000`.

Đừng tự hiểu `MIN(tong_tien)` là “đơn hàng có giá trị dương nhỏ nhất”: MIN không biết “dương” là điều kiện nghiệp vụ nếu bạn không viết điều kiện.

### 5.2. MIN và MAX không chỉ áp dụng cho số

Chúng cũng có thể tổng hợp ngày, thời điểm và một số kiểu dữ liệu có quy tắc so sánh.

~~~sql
SELECT
    MIN(ngay_dat) AS ngay_dat_som_nhat,
    MAX(ngay_dat) AS ngay_dat_muon_nhat
FROM agg_don_hang;
~~~

Kết quả:

| ngay_dat_som_nhat | ngay_dat_muon_nhat |
|---|---|
| 2026-11-01 | 2026-11-09 |

Một ví dụ khác:

~~~sql
SELECT
    MIN(ho_ten) AS ten_nho_nhat_theo_collation,
    MAX(ho_ten) AS ten_lon_nhat_theo_collation
FROM agg_khach_hang;
~~~

Với kiểu chuỗi, thứ tự phụ thuộc **collation** (quy tắc so sánh ký tự, dấu tiếng Việt, chữ hoa/thường). `MIN(ho_ten)` không có nghĩa là “tên ngắn nhất”; nó là giá trị đứng sớm nhất theo quy tắc so sánh của cơ sở dữ liệu.

### 5.3. MIN/MAX cho giá trị và lấy cả dòng là hai yêu cầu khác nhau

~~~sql
SELECT MAX(tong_tien)
FROM agg_don_hang;
~~~

trả **giá trị cao nhất**, không tự trả toàn bộ thông tin của đơn có giá trị đó. Nếu muốn tìm các đơn bằng giá trị lớn nhất:

~~~sql
SELECT id, khach_hang_id, tong_tien
FROM agg_don_hang
WHERE tong_tien = (
    SELECT MAX(tong_tien)
    FROM agg_don_hang
)
ORDER BY id;
~~~

Với dữ liệu mẫu, truy vấn trả đơn **106**. Nếu có nhiều đơn cùng giá trị lớn nhất, nó có thể trả **nhiều hàng**. Nếu muốn chỉ một hàng theo quy tắc phá hòa, có thể dùng `ORDER BY tong_tien DESC NULLS LAST, id` rồi `LIMIT 1` trong PostgreSQL.

Không nên dùng `MAX(id)` để suy ra “đơn mới nhất” nếu ID không được bảo đảm phản ánh thời gian nghiệp vụ. Khi cần bản ghi mới nhất, thường dùng cột thời gian và tiêu chí phá hòa rõ ràng.

## 6. Ba tình huống khác nhau: có số 0, toàn NULL và không có hàng

Phân biệt chính xác ba tình huống sau giúp tránh báo cáo sai.

### 6.1. Có ít nhất một giá trị 0

Ví dụ đơn của Bình số 104 có `tong_tien = 0`. Dù các hàm tổng hợp bỏ qua NULL, số 0 vẫn được xem là một giá trị hợp lệ:

~~~sql
SELECT
    SUM(tong_tien),
    AVG(tong_tien),
    MIN(tong_tien),
    MAX(tong_tien)
FROM agg_don_hang
WHERE id = 104;
~~~

Kết quả: **0, 0, 0, 0**.

### 6.2. Có hàng nhưng mọi giá trị đều NULL

Hai đơn của Dũng (107, 108) đều có tong_tien NULL:

~~~sql
SELECT
    COUNT(*) AS so_hang,
    COUNT(tong_tien) AS so_gia_tri,
    SUM(tong_tien) AS tong,
    AVG(tong_tien) AS trung_binh,
    MIN(tong_tien) AS nho_nhat,
    MAX(tong_tien) AS lon_nhat
FROM agg_don_hang
WHERE khach_hang_id = 4;
~~~

Kết quả:

| so_hang | so_gia_tri | tong | trung_binh | nho_nhat | lon_nhat |
|---:|---:|---|---|---|---|
| 2 | 0 | NULL | NULL | NULL | NULL |

Có **2 hàng**, nhưng không có giá trị số nào để tính tổng, trung bình, min hay max.

### 6.3. Không có hàng nào thỏa điều kiện

~~~sql
SELECT
    COUNT(*) AS so_hang,
    COUNT(tong_tien) AS so_gia_tri,
    SUM(tong_tien) AS tong,
    AVG(tong_tien) AS trung_binh,
    MIN(tong_tien) AS nho_nhat,
    MAX(tong_tien) AS lon_nhat
FROM agg_don_hang
WHERE khach_hang_id = 3;
~~~

Vì Chi chưa có đơn, tập đầu vào rỗng. Khi tổng hợp **không có GROUP BY**, truy vấn vẫn trả **một hàng**:

| so_hang | so_gia_tri | tong | trung_binh | nho_nhat | lon_nhat |
|---:|---:|---|---|---|---|
| 0 | 0 | NULL | NULL | NULL | NULL |

Trong SQL thông thường:

- `COUNT(*)` trên tập rỗng → **0**.
- `COUNT(cot)` trên tập rỗng → **0**.
- `SUM`, `AVG`, `MIN`, `MAX` trên tập rỗng → **NULL**.

Một hàng tổng hợp có các cột NULL **không có nghĩa đã tìm thấy một dòng dữ liệu nguồn**.

### 6.4. Bảng so sánh nhanh

| Tình huống đầu vào | COUNT(*) | COUNT(x) | SUM(x) | AVG(x) | MIN(x) | MAX(x) |
|---|---:|---:|---|---|---|---|
| Một hàng, x = 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| Hai hàng, x đều NULL | 2 | 0 | NULL | NULL | NULL | NULL |
| Không có hàng | 0 | 0 | NULL | NULL | NULL | NULL |
| Hai hàng, x = 0 và 100 | 2 | 2 | 100 | 50 | 0 | 100 |
| Hai hàng, x = NULL và 100 | 2 | 1 | 100 | 100 | 100 | 100 |

Đây là bảng rất hữu ích khi kiểm tra các số liệu hiển thị trên dashboard hoặc API.

## 7. COALESCE đặt ở đâu thì đúng?

`COALESCE(a, b, ...)` trả đối số đầu tiên không NULL. Nó thường được dùng để hiển thị **0 thay cho kết quả tổng hợp NULL**, nhưng vị trí đặt COALESCE có thể thay đổi ý nghĩa phép tính.

### 7.1. COALESCE bọc bên ngoài SUM

~~~sql
SELECT
    COALESCE(SUM(tong_tien), 0) AS tong_hien_thi
FROM agg_don_hang
WHERE khach_hang_id = 4;
~~~

Kết quả: `0` thay cho SUM trả NULL.

Đây là cách phù hợp **nếu màn hình chỉ cần hiển thị 0 khi không có tổng tính được**. Tuy nhiên, nó làm mất khác biệt giữa “thực sự tổng bằng 0” và “không có giá trị nào để tính”.

Có thể giữ thêm chỉ số để giải thích:

~~~sql
SELECT
    COUNT(*) AS so_don,
    COUNT(tong_tien) AS so_don_co_tien,
    COALESCE(SUM(tong_tien), 0) AS tong_hien_thi
FROM agg_don_hang
WHERE khach_hang_id = 4;
~~~

Kết quả là `so_don = 2`, `so_don_co_tien = 0`, `tong_hien_thi = 0`. Nhờ vậy, người đọc biết con số 0 là **giá trị hiển thị**, không phải phép cộng trên các giá trị tiền thực có.

### 7.2. COALESCE bên trong SUM

~~~sql
SELECT SUM(COALESCE(tong_tien, 0)) AS tong
FROM agg_don_hang
WHERE khach_hang_id = 4;
~~~

Dũng có hai hàng, mỗi NULL được chuyển thành 0 trước khi cộng, vì vậy kết quả bằng **0**.

Nhưng trên **tập rỗng**:

~~~sql
SELECT SUM(COALESCE(tong_tien, 0)) AS tong
FROM agg_don_hang
WHERE khach_hang_id = 3;
~~~

kết quả vẫn là **NULL**: không có dòng đầu vào nào để biểu thức bên trong được tính.

Do đó:

| Biểu thức | Có hai hàng toàn NULL | Không có hàng |
|---|---|---|
| `SUM(x)` | NULL | NULL |
| `SUM(COALESCE(x, 0))` | 0 | NULL |
| `COALESCE(SUM(x), 0)` | 0 | 0 |
| `COALESCE(SUM(COALESCE(x, 0)), 0)` | 0 | 0 |

Nếu chỉ cần hiển thị 0 khi không có tổng, cách `COALESCE(SUM(x), 0)` thường ngắn gọn và biểu đạt ý định tốt hơn.

### 7.3. COALESCE ngoài AVG khác COALESCE trong AVG

~~~sql
SELECT
    COALESCE(AVG(tong_tien), 0) AS avg_hien_thi,
    AVG(COALESCE(tong_tien, 0)) AS avg_null_thanh_0
FROM agg_don_hang;
~~~

Với dữ liệu mẫu:

- `COALESCE(AVG(tong_tien),0)` → **175000**, vì AVG đã có giá trị, COALESCE không thay đổi mẫu số.
- `AVG(COALESCE(tong_tien,0))` → **87500**, vì mọi NULL trở thành 0 và được tính trong mẫu số.

Hai câu chỉ khác vị trí COALESCE nhưng **định nghĩa chỉ số khác nhau**. Đối với thống kê, đây là quyết định nghiệp vụ quan trọng.

### 7.4. Khi nào không nên đổi NULL thành 0?

Ví dụ, một đơn PAID nhưng tong_tien NULL có thể biểu thị thiếu dữ liệu hóa đơn. Hiển thị 0 mà không báo thiếu số liệu có thể khiến người đọc tưởng rằng đơn đã được xác nhận trị giá 0.

Có thể trả cả kết quả và trạng thái:

~~~sql
SELECT
    COUNT(*) AS so_don,
    COUNT(tong_tien) AS so_don_co_so_tien,
    SUM(tong_tien) AS tong_chua_thay_the_null,
    COALESCE(SUM(tong_tien), 0) AS tong_de_hien_thi
FROM agg_don_hang
WHERE trang_thai = 'PAID';
~~~

Một báo cáo cần chất lượng dữ liệu tốt nên kiểm tra **độ đầy đủ của nguồn số liệu** bên cạnh tổng được trình bày.

## 8. GROUP BY: tổng hợp theo từng nhóm

Khi không có `GROUP BY`, các hàm tổng hợp thường cho một kết quả chung của tập dòng. Với `GROUP BY`, mỗi nhóm tạo ra một hàng tổng hợp.

### 8.1. Theo trạng thái đơn hàng

~~~sql
SELECT
    trang_thai,
    COUNT(*) AS so_don,
    COUNT(tong_tien) AS so_don_co_tien,
    SUM(tong_tien) AS tong,
    AVG(tong_tien) AS trung_binh,
    MIN(tong_tien) AS nho_nhat,
    MAX(tong_tien) AS lon_nhat
FROM agg_don_hang
GROUP BY trang_thai
ORDER BY trang_thai;
~~~

Kết quả logic:

| trang_thai | so_don | so_don_co_tien | tong | trung_binh | nho_nhat | lon_nhat |
|---|---:|---:|---|---|---|---|
| CANCELLED | 1 | 0 | NULL | NULL | NULL | NULL |
| NEW | 2 | 0 | NULL | NULL | NULL | NULL |
| PAID | 5 | 4 | 700000 | 175000 | 0 | 300000 |

PAID có năm đơn: 101, 103, 104, 106, 108. Nhưng đơn 108 có tiền NULL, nên chỉ **bốn giá trị** tham gia SUM/AVG/MIN/MAX. Cả NEW và CANCELLED đều có nhóm (vì có các hàng) nhưng mọi tong_tien trong nhóm là NULL.

### 8.2. WHERE lọc dòng trước GROUP BY

~~~sql
SELECT
    khach_hang_id,
    SUM(tong_tien) AS tong_paid
FROM agg_don_hang
WHERE trang_thai = 'PAID'
GROUP BY khach_hang_id
ORDER BY khach_hang_id;
~~~

Kết quả:

| khach_hang_id | tong_paid |
|---:|---|
| 1 | 400000 |
| 2 | 300000 |
| 4 | NULL |

Dũng có đơn 108 PAID nên nhóm của Dũng tồn tại, nhưng tong_tien của đơn đó NULL. Chi hoàn toàn không có đơn nên **không có nhóm** trong kết quả.

Những dòng bị WHERE loại không có mặt trong phép tổng hợp. Nếu thay điều kiện trạng thái hoặc thêm điều kiện ngày, mẫu số của AVG và giá trị SUM cũng có thể thay đổi.

### 8.3. HAVING lọc nhóm sau tổng hợp

Yêu cầu: tìm khách hàng có **tổng tiền PAID lớn hơn 300000**.

~~~sql
SELECT
    khach_hang_id,
    SUM(tong_tien) AS tong_paid
FROM agg_don_hang
WHERE trang_thai = 'PAID'
GROUP BY khach_hang_id
HAVING SUM(tong_tien) > 300000
ORDER BY khach_hang_id;
~~~

Kết quả chỉ có khách hàng **1 — An, tổng 400000**. Bình có đúng 300000 nên không đạt điều kiện dấu lớn hơn.

**Phân biệt:**

- `WHERE trang_thai = 'PAID'` lọc **các dòng nguồn** trước khi GROUP BY.
- `HAVING SUM(tong_tien) > 300000` lọc **các nhóm đã tính tổng**.

Không thể viết `WHERE SUM(tong_tien) > 300000` ở cùng cấp theo cách thông thường, vì WHERE không phải nơi đánh giá điều kiện tổng hợp của nhóm.

### 8.4. GROUP BY trên cột có NULL

Nếu nhóm theo một cột nullable, SQL thường gom các hàng có khóa nhóm NULL thành **một nhóm NULL**. Điều này khác với phép so sánh thông thường `NULL = NULL`, vốn cho UNKNOWN.

Ví dụ, trong một bảng có cột `khu_vuc` nullable, những hàng chưa có khu vực thường xuất hiện chung một nhóm khi `GROUP BY khu_vuc`. Nhưng việc có nhóm NULL không tự cho biết đó là một vùng địa lý; khi báo cáo cần hiển thị rõ “Chưa xác định”.

## 9. LEFT JOIN: giữ nhóm không có bản ghi liên quan

Một yêu cầu phổ biến: **hiển thị tất cả khách hàng**, kể cả người chưa có đơn, cùng số đơn và tổng tiền.

Nếu chỉ GROUP BY từ bảng đơn, khách hàng Chi không thể xuất hiện vì không có đơn. Cần lấy bảng khách hàng làm nguồn bên trái:

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    COUNT(dh.id) AS so_don,
    COUNT(dh.tong_tien) AS so_don_co_tien,
    SUM(dh.tong_tien) AS tong,
    AVG(dh.tong_tien) AS trung_binh,
    MIN(dh.tong_tien) AS nho_nhat,
    MAX(dh.tong_tien) AS lon_nhat
FROM agg_khach_hang AS kh
LEFT JOIN agg_don_hang AS dh
    ON dh.khach_hang_id = kh.id
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

Kết quả:

| id | ho_ten | so_don | so_don_co_tien | tong | trung_binh | nho_nhat | lon_nhat |
|---:|---|---:|---:|---|---|---|---|
| 1 | An | 3 | 2 | 400000 | 200000 | 150000 | 250000 |
| 2 | Bình | 3 | 2 | 300000 | 150000 | 0 | 300000 |
| 3 | Chi | 0 | 0 | NULL | NULL | NULL | NULL |
| 4 | Dũng | 2 | 0 | NULL | NULL | NULL | NULL |

Đây là kết quả rất đáng quan sát:

- **An:** ba đơn nhưng chỉ hai đơn có tong_tien. Tổng 400000, AVG 200000.
- **Bình:** ba đơn, hai giá trị tiền là 0 và 300000. AVG 150000, MIN 0.
- **Chi:** không có đơn, nhưng có hàng trong kết quả nhờ LEFT JOIN. Tổng tiền là NULL.
- **Dũng:** có hai đơn, nhưng cả hai số tiền đều NULL; tổng tiền cũng là NULL.

### 9.1. Vì sao dùng COUNT(dh.id), không phải COUNT(*)?

Trong LEFT JOIN, nếu khách hàng chưa có đơn, SQL vẫn giữ một hàng đại diện cho khách hàng, với **các cột bên phải bằng NULL**. Do đó:

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    COUNT(*) AS so_hang_sau_join,
    COUNT(dh.id) AS so_don_that
FROM agg_khach_hang AS kh
LEFT JOIN agg_don_hang AS dh
    ON dh.khach_hang_id = kh.id
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

Kết quả:

| ho_ten | so_hang_sau_join | so_don_that |
|---|---:|---:|
| An | 3 | 3 |
| Bình | 3 | 3 |
| Chi | 1 | 0 |
| Dũng | 2 | 2 |

`COUNT(*)` đếm cả hàng được giữ lại bởi LEFT JOIN, nên Chi là **1**, mặc dù không có đơn. `COUNT(dh.id)` bỏ qua NULL của phía bảng đơn và trả đúng **0**. Vì `dh.id` là khóa chính và không NULL đối với đơn thật, đây là cột phù hợp để đếm đơn khớp.

### 9.2. Hiển thị tổng bằng 0 mà vẫn cho biết mức độ đầy đủ

~~~sql
SELECT
    kh.ho_ten,
    COUNT(dh.id) AS so_don,
    COUNT(dh.tong_tien) AS so_don_co_tien,
    COALESCE(SUM(dh.tong_tien), 0) AS tong_hien_thi
FROM agg_khach_hang AS kh
LEFT JOIN agg_don_hang AS dh
    ON dh.khach_hang_id = kh.id
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

| ho_ten | so_don | so_don_co_tien | tong_hien_thi |
|---|---:|---:|---:|
| An | 3 | 2 | 400000 |
| Bình | 3 | 2 | 300000 |
| Chi | 0 | 0 | 0 |
| Dũng | 2 | 0 | 0 |

Chi và Dũng cùng có `tong_hien_thi = 0` nhưng **không cùng tình trạng dữ liệu**. Chi không có đơn; Dũng có đơn mà tiền chưa xác định. Hai cột đếm bổ sung giúp phân biệt trường hợp đó.

### 9.3. Đặt điều kiện ở ON hay WHERE?

Yêu cầu: giữ tất cả khách hàng nhưng chỉ tổng hợp **đơn PAID**. Hãy đặt điều kiện trạng thái trong `ON`:

~~~sql
SELECT
    kh.ho_ten,
    COUNT(dh.id) AS so_don_paid,
    SUM(dh.tong_tien) AS tong_paid
FROM agg_khach_hang AS kh
LEFT JOIN agg_don_hang AS dh
    ON dh.khach_hang_id = kh.id
   AND dh.trang_thai = 'PAID'
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

Kết quả giữ cả bốn khách hàng. Nếu đưa `dh.trang_thai = 'PAID'` vào `WHERE` bên ngoài, khách hàng không có đơn PAID sẽ bị loại do giá trị NULL phía bảng đơn không thỏa điều kiện.

**Quy tắc:** trong LEFT JOIN, điều kiện xác định **dòng bên phải nào được phép ghép** thường đặt tại `ON` nếu bạn muốn giữ toàn bộ bảng bên trái.

## 10. Tổng hợp có điều kiện

Nhiều báo cáo cần hiển thị các chỉ số theo điều kiện khác nhau trong cùng một hàng, ví dụ số đơn PAID, số đơn NEW và tổng tiền PAID.

### 10.1. PostgreSQL: FILTER

PostgreSQL hỗ trợ cú pháp `FILTER (WHERE ...)` cho nhiều hàm tổng hợp:

~~~sql
SELECT
    COUNT(*) AS tong_so_don,
    COUNT(*) FILTER (
        WHERE trang_thai = 'PAID'
    ) AS so_don_paid,
    COUNT(*) FILTER (
        WHERE trang_thai = 'NEW'
    ) AS so_don_new,
    COUNT(*) FILTER (
        WHERE trang_thai = 'CANCELLED'
    ) AS so_don_huy,
    SUM(tong_tien) FILTER (
        WHERE trang_thai = 'PAID'
    ) AS tong_paid,
    AVG(tong_tien) FILTER (
        WHERE trang_thai = 'PAID'
    ) AS avg_paid
FROM agg_don_hang;
~~~

Kết quả:

| tong_so_don | so_don_paid | so_don_new | so_don_huy | tong_paid | avg_paid |
|---:|---:|---:|---:|---:|---:|
| 8 | 5 | 2 | 1 | 700000 | 175000 |

`FILTER` chỉ cho những dòng đáp ứng điều kiện đi vào **hàm tổng hợp tương ứng**, không loại chúng khỏi toàn bộ câu SELECT.

### 10.2. Một hàm SUM có FILTER vẫn bỏ qua NULL

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE trang_thai = 'PAID'
    ) AS so_don_paid,
    COUNT(tong_tien) FILTER (
        WHERE trang_thai = 'PAID'
    ) AS so_paid_co_tien,
    SUM(tong_tien) FILTER (
        WHERE trang_thai = 'PAID'
    ) AS tong_paid
FROM agg_don_hang;
~~~

Kết quả: **5 đơn PAID, 4 đơn PAID có số tiền, tổng 700000**. `FILTER` chọn hàng theo trạng thái; sau đó `COUNT(cot)` và `SUM(cot)` vẫn áp dụng quy tắc bỏ qua NULL của đối số.

Nếu lọc NEW:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE trang_thai = 'NEW') AS so_new,
    SUM(tong_tien) FILTER (WHERE trang_thai = 'NEW') AS tong_new
FROM agg_don_hang;
~~~

Kết quả: `so_new = 2`, `tong_new = NULL` vì hai đơn NEW không có giá trị tiền.

### 10.3. CASE WHEN để tổng hợp có điều kiện

Để dùng cú pháp có tính di động rộng hơn, có thể đưa CASE vào hàm:

~~~sql
SELECT
    SUM(
        CASE
            WHEN trang_thai = 'PAID' THEN tong_tien
            ELSE NULL
        END
    ) AS tong_paid,
    COUNT(
        CASE
            WHEN trang_thai = 'PAID' THEN 1
            ELSE NULL
        END
    ) AS so_don_paid
FROM agg_don_hang;
~~~

Kết quả: `tong_paid = 700000`, `so_don_paid = 5`.

Vì `SUM` bỏ qua NULL, cách viết `SUM(CASE WHEN ... THEN tong_tien END)` thường tương đương việc chỉ truyền giá trị tiền của các dòng khớp. `COUNT(CASE WHEN ... THEN 1 END)` đếm **số dòng khớp**, bất kể giá trị tiền của dòng đó NULL hay không.

### 10.4. ELSE 0 và ELSE NULL không phải lúc nào cũng giống nhau

~~~sql
SELECT
    SUM(CASE
            WHEN trang_thai = 'PAID' THEN tong_tien
            ELSE NULL
        END) AS tong_paid_null,
    SUM(CASE
            WHEN trang_thai = 'PAID' THEN tong_tien
            ELSE 0
        END) AS tong_paid_zero
FROM agg_don_hang;
~~~

Với dữ liệu hiện tại, hai cột đều bằng 700000. Nhưng khi nhóm chỉ có đơn NEW (không có dòng PAID):

- `ELSE NULL` → SUM có thể trả **NULL**.
- `ELSE 0` → SUM có thể trả **0**, vì các dòng không PAID được thay bằng số 0.

Sự khác biệt này đặc biệt rõ khi GROUP BY theo khách hàng. Với Dũng, có một đơn NEW và một đơn PAID có tiền NULL. `SUM(CASE WHEN PAID THEN tong_tien END)` trả NULL, nhưng `SUM(CASE WHEN PAID THEN tong_tien ELSE 0 END)` trả 0 nhờ dòng NEW.

Không nên tùy tiện đổi NULL thành 0 nếu doanh thu chưa xác định có ý nghĩa nghiệp vụ khác với doanh thu đã xác nhận bằng 0.

## 11. SUM(DISTINCT) và AVG(DISTINCT): không phải cách sửa JOIN bị nhân dòng

Ngoài cách viết thông thường:

~~~sql
SUM(tong_tien)
AVG(tong_tien)
~~~

SQL còn hỗ trợ biến thể `DISTINCT` cho những hàm phù hợp:

~~~sql
SUM(DISTINCT tong_tien)
AVG(DISTINCT tong_tien)
~~~

`DISTINCT` loại bỏ **giá trị biểu thức trùng nhau** trước khi tổng hợp, không phải loại bỏ đơn hàng trùng ID.

### 11.1. Ví dụ nhỏ với các số trùng nhau

~~~sql
SELECT
    SUM(x) AS tong_thuong,
    SUM(DISTINCT x) AS tong_distinct,
    ROUND(AVG(x), 2) AS avg_thuong,
    ROUND(AVG(DISTINCT x), 2) AS avg_distinct
FROM (
    VALUES
        (100::NUMERIC),
        (100::NUMERIC),
        (200::NUMERIC),
        (NULL::NUMERIC)
) AS v(x);
~~~

Kết quả:

| tong_thuong | tong_distinct | avg_thuong | avg_distinct |
|---:|---:|---:|---:|
| 400 | 300 | 133.33 | 150.00 |

- SUM thường: 100 + 100 + 200 = 400.
- SUM DISTINCT: 100 + 200 = 300.
- AVG thường: 400 / 3 ≈ 133.33.
- AVG DISTINCT: 300 / 2 = 150.

Nếu hai đơn hàng **khác nhau nhưng tình cờ có cùng giá trị tiền**, cả hai phải được tính trong tổng doanh thu. Dùng `SUM(DISTINCT tong_tien)` sẽ loại nhầm một giá trị và làm báo cáo sai.

### 11.2. DISTINCT không thay thế hiểu đúng khóa JOIN

Nếu dữ liệu bị lặp do JOIN một-nhiều, vấn đề cần giải quyết là **mức chi tiết và điều kiện JOIN**, không phải làm biến mất các số tiền giống nhau bằng DISTINCT. Phần tiếp theo minh họa cụ thể.

## 12. Tránh SUM/AVG sai khi JOIN nhân nhiều dòng

Giả sử bạn JOIN đơn hàng với các dòng sản phẩm. Mỗi đơn có thể có nhiều dòng chi tiết; nếu cộng `tong_tien` của **đơn** sau JOIN, cùng một đơn có thể bị tính lặp.

### 12.1. Tạo dữ liệu dòng chi tiết

~~~sql
CREATE TEMP TABLE agg_dong_hang (
    don_hang_id INTEGER NOT NULL
        REFERENCES agg_don_hang(id),
    so_thu_tu INTEGER NOT NULL,
    mo_ta VARCHAR(100) NOT NULL,
    PRIMARY KEY (don_hang_id, so_thu_tu)
);

INSERT INTO agg_dong_hang (don_hang_id, so_thu_tu, mo_ta) VALUES
    (101, 1, 'Sản phẩm A'),
    (101, 2, 'Sản phẩm B'),
    (103, 1, 'Sản phẩm C'),
    (104, 1, 'Sản phẩm D'),
    (106, 1, 'Sản phẩm E'),
    (106, 2, 'Sản phẩm F');
~~~

Đơn 101 có hai dòng, 103 có một dòng, 104 có một dòng, 106 có hai dòng. Đơn 108 PAID nhưng chưa có chi tiết.

### 12.2. Truy vấn dễ đếm trùng

~~~sql
SELECT SUM(dh.tong_tien) AS tong_bi_nhan
FROM agg_don_hang AS dh
JOIN agg_dong_hang AS ct
    ON ct.don_hang_id = dh.id
WHERE dh.trang_thai = 'PAID';
~~~

Kết quả:

\[
250000 \times 2 + 150000 + 0 + 300000 \times 2
= 1250000
\]

**1.250.000 là tổng sai** nếu bạn đang hỏi tổng tiền theo đơn. Giá trị 250000 của đơn 101 được cộng hai lần, 300000 của đơn 106 cũng được cộng hai lần.

### 12.3. Tổng hợp đúng ở đúng cấp

Nếu tổng tiền đã nằm trên bảng đơn, hãy cộng **trực tiếp từ bảng đơn**:

~~~sql
SELECT SUM(tong_tien) AS tong_paid_dung
FROM agg_don_hang
WHERE trang_thai = 'PAID';
~~~

Kết quả: **700000**.

Nếu vẫn cần số dòng chi tiết, hãy tổng hợp chi tiết thành **một dòng mỗi đơn** rồi JOIN:

~~~sql
SELECT
    dh.id,
    dh.tong_tien,
    COALESCE(ct.so_dong, 0) AS so_dong_chi_tiet
FROM agg_don_hang AS dh
LEFT JOIN (
    SELECT
        don_hang_id,
        COUNT(*) AS so_dong
    FROM agg_dong_hang
    GROUP BY don_hang_id
) AS ct
    ON ct.don_hang_id = dh.id
WHERE dh.trang_thai = 'PAID'
ORDER BY dh.id;
~~~

Bảng dẫn xuất `ct` có tối đa một dòng cho mỗi đơn, nên không nhân số dòng của bảng `dh`.

**Nguyên tắc quan trọng:** trước khi tổng hợp qua JOIN, hãy hỏi **mỗi hàng kết quả đại diện cho một đơn, một khách hàng hay một dòng chi tiết?**. Phép tính phải được thực hiện ở đúng cấp hạt (*grain*) của dữ liệu.

## 13. Trung bình có trọng số và những phép AVG dễ gây nhầm

`AVG(x)` cho mọi hàng có giá trị `x` khác NULL **trọng số bằng nhau**. Điều này phù hợp khi mỗi hàng đại diện cùng loại đối tượng, nhưng có thể không đúng khi mỗi hàng đại diện một nhóm có quy mô khác nhau.

### 13.1. Ví dụ giá trung bình theo số lượng

Giả sử có hai dòng hàng:

| Số lượng | Đơn giá |
|---:|---:|
| 2 | 100 |
| 1 | 300 |

Nếu dùng `AVG(don_gia)` trên hai dòng, ta có (100 + 300) / 2 = **200**. Nhưng giá bình quân **trên mỗi sản phẩm thực bán** phải dùng trọng số số lượng:

\[
\frac{2 \times 100 + 1 \times 300}{2 + 1}
=\frac{500}{3}
\approx 166.67
\]

SQL PostgreSQL:

~~~sql
SELECT
    ROUND(AVG(don_gia), 2) AS avg_theo_dong,
    ROUND(
        SUM(so_luong * don_gia)
        / NULLIF(SUM(so_luong), 0),
        2
    ) AS avg_theo_so_luong
FROM (
    VALUES
        (2::NUMERIC, 100::NUMERIC),
        (1::NUMERIC, 300::NUMERIC)
) AS v(so_luong, don_gia);
~~~

Kết quả: `avg_theo_dong = 200.00`, `avg_theo_so_luong = 166.67`.

`NULLIF(SUM(so_luong), 0)` biến mẫu số bằng 0 thành NULL để tránh lỗi chia cho 0. Khi mẫu số NULL, biểu thức chia cũng NULL; ứng dụng có thể hiển thị trạng thái “không thể tính” thay vì làm tròn thành 0.

### 13.2. Trung bình của trung bình

Ví dụ khách hàng A có 100 đơn, khách hàng B có 1 đơn. Trung bình tiền mỗi đơn của A là 100, của B là 1000.

Trung bình hai chỉ số **(100 + 1000)/2 = 550** là **trung bình giữa hai khách hàng**, cho mỗi khách hàng cùng trọng số. Nhưng trung bình trên **101 đơn** phải là:

\[
\frac{100 \times 100 + 1 \times 1000}{101}
\approx 108.91
\]

Không được gọi hai phép tính trên là cùng một chỉ số. Khi tổng hợp từ những nhóm có số lượng khác nhau, hãy quyết định rõ mẫu số và trọng số trước khi viết AVG.

### 13.3. AVG trên cột kiểu nguyên

Kiểu dữ liệu trả về của AVG và quy tắc chia phụ thuộc DBMS và kiểu dữ liệu đầu vào. Trong PostgreSQL, `AVG` của một số kiểu nguyên thường trả `NUMERIC`, nhưng không thể mặc định mọi DBMS đều giữ phần thập phân giống nhau.

Nếu cần kết quả chính xác về phần lẻ, có thể ép kiểu phù hợp:

~~~sql
SELECT AVG(so_nguyen::NUMERIC) AS avg_chinh_xac
FROM (
    VALUES (1), (2)
) AS v(so_nguyen);
~~~

Kết quả PostgreSQL là **1.5**. Trên hệ khác, cú pháp ép kiểu có thể là `CAST(so_nguyen AS DECIMAL(...))`.

Với các số tiền, nên cân nhắc dùng `NUMERIC/DECIMAL` thay vì kiểu floating-point nhị phân khi cần phép tính thập phân chính xác, đồng thời chọn quy tắc làm tròn ở đúng lớp nghiệp vụ.

## 14. MIN/MAX theo thời gian và dữ liệu phân nhóm

### 14.1. Ngày đơn đầu và cuối của mỗi khách hàng

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    MIN(dh.ngay_dat) AS ngay_dat_dau,
    MAX(dh.ngay_dat) AS ngay_dat_cuoi
FROM agg_khach_hang AS kh
LEFT JOIN agg_don_hang AS dh
    ON dh.khach_hang_id = kh.id
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

Kết quả:

| ho_ten | ngay_dat_dau | ngay_dat_cuoi |
|---|---|---|
| An | 2026-11-01 | 2026-11-05 |
| Bình | 2026-11-02 | 2026-11-07 |
| Chi | NULL | NULL |
| Dũng | 2026-11-08 | 2026-11-09 |

Chi không có đơn nên MIN/MAX ngày NULL. Dũng có hai ngày đặt đơn đầy đủ dù số tiền của cả hai đơn NULL: **NULL được xử lý riêng cho từng biểu thức tổng hợp**. `MIN(ngay_dat)` không phụ thuộc `tong_tien` nếu truy vấn không đặt điều kiện liên quan.

### 14.2. Tìm khách hàng có đơn mới nhất

Truy vấn:

~~~sql
SELECT MAX(ngay_dat) AS ngay_cuoi_cung
FROM agg_don_hang;
~~~

chỉ trả **2026-11-09**, không trả tên khách hàng. Nếu muốn cả thông tin đơn mới nhất:

~~~sql
SELECT
    dh.id,
    kh.ho_ten,
    dh.ngay_dat
FROM agg_don_hang AS dh
JOIN agg_khach_hang AS kh
    ON kh.id = dh.khach_hang_id
WHERE dh.ngay_dat = (
    SELECT MAX(ngay_dat)
    FROM agg_don_hang
)
ORDER BY dh.id;
~~~

Kết quả là đơn **108 của Dũng**. Khi có nhiều đơn cùng ngày cuối, truy vấn sẽ trả nhiều hàng, đúng với yêu cầu “mọi đơn ở ngày mới nhất”.

### 14.3. MAX trạng thái không phải trạng thái quan trọng nhất

`MAX(trang_thai)` trên cột chuỗi chọn giá trị lớn nhất theo quy tắc so sánh của DBMS, không phải trạng thái có ưu tiên cao nhất. Nếu muốn biết trạng thái ưu tiên, cần **định nghĩa thứ hạng bằng CASE hoặc bảng cấu hình** trước khi lấy hạng, không dùng MIN/MAX chuỗi rồi gán nhãn nghiệp vụ một cách tùy tiện.

## 15. Hàm tổng hợp cửa sổ khác gì GROUP BY?

`GROUP BY` gộp nhiều hàng thành một hàng cho mỗi nhóm. Trong PostgreSQL và nhiều DBMS, cùng các hàm SUM/AVG/MIN/MAX còn được dùng như **window functions** với `OVER(...)`: giữ lại từng hàng và bổ sung kết quả tổng hợp của một cửa sổ.

~~~sql
SELECT
    id,
    khach_hang_id,
    tong_tien,
    SUM(tong_tien) OVER (
        PARTITION BY khach_hang_id
    ) AS tong_tien_cua_khach,
    AVG(tong_tien) OVER (
        PARTITION BY khach_hang_id
    ) AS avg_tien_cua_khach
FROM agg_don_hang
ORDER BY khach_hang_id, id;
~~~

Mỗi đơn hàng vẫn xuất hiện như một dòng; hai cột tính toán lặp lại tổng/trung bình của khách hàng tương ứng.

| Đơn | Khách hàng | tong_tien | tong_tien_cua_khach | avg_tien_cua_khach |
|---:|---:|---:|---|---|
| 101 | An | 250000 | 400000 | 200000 |
| 102 | An | NULL | 400000 | 200000 |
| 103 | An | 150000 | 400000 | 200000 |
| 104 | Bình | 0 | 300000 | 150000 |
| 105 | Bình | NULL | 300000 | 150000 |
| 106 | Bình | 300000 | 300000 | 150000 |
| 107 | Dũng | NULL | NULL | NULL |
| 108 | Dũng | NULL | NULL | NULL |

Các hàm tổng hợp dạng cửa sổ vẫn áp dụng quy tắc bỏ qua NULL của đối số. Nhưng **số lượng dòng kết quả không bị gộp lại** như GROUP BY.

Nếu dùng `ORDER BY` bên trong `OVER` để tính tổng lũy kế, cần xác định frame phù hợp, ví dụ:

~~~sql
SELECT
    id,
    khach_hang_id,
    ngay_dat,
    tong_tien,
    SUM(tong_tien) OVER (
        PARTITION BY khach_hang_id
        ORDER BY ngay_dat, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke
FROM agg_don_hang
ORDER BY khach_hang_id, ngay_dat, id;
~~~

Với Dũng, tổng lũy kế vẫn NULL vì chưa có giá trị không NULL nào. Với An, dòng có tong_tien NULL không tăng tổng; kết quả lũy kế vẫn giữ tổng các giá trị đã gặp trước đó. Việc dùng `ROWS` và khóa phá hòa `id` làm thứ tự frame rõ ràng.

## 16. Các lỗi thường gặp và cách đọc kết quả

| Nhận định hoặc cách viết | Vì sao dễ sai? | Cách tiếp cận đúng |
|---|---|---|
| “SUM coi NULL là 0” | SUM bỏ qua NULL; khi toàn NULL có thể trả NULL | Phân biệt quy tắc bỏ qua với thay bằng 0 |
| “AVG chia cho COUNT(*)” | AVG chia theo số giá trị đầu vào khác NULL | Xem `COUNT(x)` |
| “MIN chỉ tính số dương” | Số 0 và số âm cũng tham gia nếu có | Lọc `WHERE x > 0` khi cần |
| “SUM của tập rỗng là 0” | Trong SQL thông thường, SUM trả NULL | Dùng `COALESCE(SUM(x), 0)` nếu nghiệp vụ cần hiển thị 0 |
| “COUNT(x) đếm tất cả dòng” | COUNT(x) bỏ qua NULL | Dùng COUNT(*) khi muốn đếm hàng |
| “COALESCE trong và ngoài AVG giống nhau” | Trong AVG thay đổi mẫu số | Chọn công thức dựa trên ý nghĩa NULL |
| “LEFT JOIN và COUNT(*) đếm đúng số đơn” | Khách hàng không có đơn vẫn có một hàng sau LEFT JOIN | `COUNT(dh.id)` để đếm đơn thật |
| “SUM sau JOIN luôn đúng” | Quan hệ một-nhiều có thể nhân giá trị tiền của bảng cha | Tổng hợp ở đúng cấp dữ liệu |
| “SUM(DISTINCT) sửa được lặp JOIN” | Hai đơn khác nhau có cùng số tiền sẽ bị loại nhầm | Sửa JOIN hoặc tiền tổng hợp |
| “MIN/MAX ngày cho biết mọi cột của dòng đó” | Hàm trả một giá trị, không tự mang toàn bộ hàng | JOIN/subquery/window phù hợp |
| “HAVING và WHERE giống nhau” | WHERE lọc dòng, HAVING lọc nhóm | Đặt điều kiện ở đúng cấp |
| “Không có hàng cũng sẽ không có dòng kết quả” | Tổng hợp không GROUP BY trên tập rỗng vẫn trả một hàng | Kiểm tra COUNT(*) và NULL |
| “Cộng các tổng nhóm rồi AVG là đủ” | Trung bình nhóm có trọng số khác nhau | Định nghĩa mẫu số/trọng số |
| “NULL ở mọi cột được xử lý cùng nhau” | Mỗi phép tổng hợp đánh giá đối số riêng | MIN(ngày) có thể có giá trị khi SUM(tiền) NULL |

### 16.1. Nhìn COUNT trước khi diễn giải AVG

Khi thấy trung bình bất thường, nên xuất kèm:

~~~sql
SELECT
    COUNT(*) AS so_hang,
    COUNT(tong_tien) AS so_gia_tri,
    SUM(tong_tien) AS tong,
    AVG(tong_tien) AS trung_binh
FROM agg_don_hang;
~~~

Chỉ một cột AVG chưa cho biết dữ liệu thiếu bao nhiêu. Hai cột đếm giúp xác nhận mẫu số và tình trạng đầy đủ dữ liệu.

### 16.2. Không xóa NULL bằng WHERE khi cần đo mức thiếu dữ liệu

Một câu:

~~~sql
SELECT AVG(tong_tien)
FROM agg_don_hang
WHERE tong_tien IS NOT NULL;
~~~

cho cùng AVG với `AVG(tong_tien)` không có WHERE trong bộ dữ liệu này, vì AVG vốn bỏ qua NULL. Nhưng khi bạn cần **COUNT(*)**, cơ cấu trạng thái hoặc tỷ lệ thiếu dữ liệu, việc lọc các hàng NULL trước có thể làm báo cáo mất thông tin.

Chọn lọc theo ý nghĩa nghiệp vụ; đừng lọc NULL chỉ vì nghĩ mọi hàm tổng hợp đều gặp lỗi khi thấy NULL.

## 17. Khác biệt giữa các hệ quản trị SQL

Quy tắc bỏ qua giá trị NULL trong `SUM`, `AVG`, `MIN` và `MAX` là phổ biến trong SQL quan hệ. Tuy vậy, một số DBMS khác nhau về **cú pháp điều kiện, kiểu dữ liệu kết quả, làm tròn và hành vi chuyển kiểu**.

| Hệ quản trị | Lưu ý khi tổng hợp |
|---|---|
| **PostgreSQL** | Hỗ trợ `FILTER (WHERE ...)`, `NUMERIC` và cú pháp `::NUMERIC`; AVG kiểu số nguyên thường trả NUMERIC |
| **MySQL/MariaDB** | SUM/AVG/MIN/MAX bỏ qua NULL; cần chú ý chuyển kiểu đầu vào, chế độ SQL và kiểu kết quả |
| **SQL Server** | Có `SUM`, `AVG`, `MIN`, `MAX`; cú pháp `FILTER` kiểu PostgreSQL không phải cách phổ biến; AVG trên kiểu số nguyên có thể trả kiểu nguyên với phần lẻ không được giữ |
| **Oracle** | Các hàm tổng hợp tương ứng có mặt; xử lý số và cú pháp ép kiểu/NULL có đặc điểm riêng |
| **SQLite** | `sum(x)` trả NULL khi không có giá trị số khác NULL; còn `total(x)` riêng của SQLite trả 0.0 và dùng số thực, không phải hàm SQL chung |

### 17.1. COALESCE có tính di động hơn một số hàm thay NULL riêng

Ví dụ PostgreSQL:

~~~sql
SELECT COALESCE(SUM(tong_tien), 0)
FROM agg_don_hang;
~~~

`COALESCE` được nhiều DBMS hỗ trợ. Một số hệ còn có hàm riêng như `ISNULL`, `IFNULL` hoặc `NVL` với cú pháp/quy tắc kiểu dữ liệu khác. Khi viết SQL đa hệ, nên chọn cách diễn đạt và kiểu kết quả phù hợp với DBMS thực tế.

### 17.2. Kiểu số đầu vào ảnh hưởng AVG

Ví dụ trong PostgreSQL:

~~~sql
SELECT AVG(x::NUMERIC)
FROM (
    VALUES (1), (2)
) AS v(x);
~~~

Kết quả trung bình là 1.5. Trên SQL Server, biểu thức AVG trên cột `INT` có thể cho kiểu trả về `INT`, nên nếu cần phần lẻ, thường phải `CAST` sang `DECIMAL` thích hợp trước khi tính AVG. Không nên mặc định mọi DBMS tự nâng kiểu số giống PostgreSQL.

### 17.3. SQLite có hàm total riêng

SQLite phân biệt:

~~~sql
SELECT SUM(x), TOTAL(x)
FROM bang_sqlite;
~~~

Nếu không có giá trị đầu vào khác NULL, `SUM` thường trả NULL, còn `TOTAL` trả **0.0** theo đặc tả của SQLite. `TOTAL` không phải hàm được hỗ trợ ở mọi SQL DBMS và có quy tắc số thực riêng; không nên mang nguyên truy vấn này sang PostgreSQL, SQL Server hoặc Oracle.

### 17.4. FILTER không có mặt đồng đều

`COUNT(*) FILTER (WHERE ...)` có ở PostgreSQL và một số DBMS hỗ trợ cú pháp này, nhưng không có tính tương thích hoàn toàn với mọi hệ.

Khi chuyển sang SQL Server hoặc một dialect không hỗ trợ FILTER, một cách thay thế thường dùng là:

~~~sql
SELECT
    SUM(CASE WHEN trang_thai = 'PAID' THEN 1 ELSE 0 END)
        AS so_don_paid,
    SUM(CASE WHEN trang_thai = 'PAID' THEN tong_tien ELSE NULL END)
        AS tong_paid
FROM bang_don_hang;
~~~

Ví dụ dùng tên `bang_don_hang` giả định; hãy đổi thành tên thật của bảng. Với tập rỗng, `SUM(CASE... THEN 1 ELSE 0 END)` vẫn có thể trả NULL vì không có hàng. Nếu yêu cầu số đếm luôn là 0, có thể dùng `COUNT(CASE WHEN trang_thai = 'PAID' THEN 1 END)` hoặc bọc SUM trong COALESCE tùy ý định.

### 17.5. MIN/MAX trên văn bản phụ thuộc collation

Mỗi DBMS có cơ chế collation và kiểu chuỗi riêng. `MIN(ten)` hoặc `MAX(ma_trang_thai)` có thể khác thứ tự giữa các môi trường ngôn ngữ/collation. Không nên sử dụng MIN/MAX chuỗi để xác định **ưu tiên nghiệp vụ** nếu chỉ dựa vào tên trạng thái.

## 18. Bài tập thực hành có lời giải

Dùng các bảng `agg_khach_hang` và `agg_don_hang` của phần 2. Các bài đọc dữ liệu; bài liên quan JOIN chi tiết chỉ yêu cầu bảng `agg_dong_hang` được tạo ở phần 12.

### Bài 1. Tính bốn phép tổng hợp cơ bản

**Yêu cầu:** trả tổng tiền, trung bình, nhỏ nhất, lớn nhất trên toàn bộ đơn hàng, đồng thời hiển thị số đơn và số đơn có số tiền.

~~~sql
SELECT
    COUNT(*) AS so_don,
    COUNT(tong_tien) AS so_don_co_tien,
    SUM(tong_tien) AS tong,
    AVG(tong_tien) AS trung_binh,
    MIN(tong_tien) AS nho_nhat,
    MAX(tong_tien) AS lon_nhat
FROM agg_don_hang;
~~~

**Đáp án:** `so_don = 8`, `so_don_co_tien = 4`, `tong = 700000`, `trung_binh = 175000`, `nho_nhat = 0`, `lon_nhat = 300000`.

### Bài 2. Phân biệt số 0 và NULL

**Yêu cầu:** lấy đơn có giá trị tiền bằng 0; sau đó lấy đơn có tong_tien NULL.

~~~sql
SELECT id
FROM agg_don_hang
WHERE tong_tien = 0
ORDER BY id;

SELECT id
FROM agg_don_hang
WHERE tong_tien IS NULL
ORDER BY id;
~~~

**Đáp án:** câu đầu trả đơn **104**; câu sau trả **102, 105, 107, 108**. Phép so sánh `tong_tien = NULL` không phải cách tìm giá trị thiếu.

### Bài 3. Tính số đơn PAID và giá trị tiền

~~~sql
SELECT
    COUNT(*) AS so_paid,
    COUNT(tong_tien) AS so_paid_co_tien,
    SUM(tong_tien) AS tong_paid,
    AVG(tong_tien) AS avg_paid
FROM agg_don_hang
WHERE trang_thai = 'PAID';
~~~

**Đáp án:** 5 đơn PAID, trong đó 4 đơn có giá trị tiền; tổng 700000 và trung bình 175000. Đơn 108 PAID nhưng tiền NULL làm `COUNT(*)` lớn hơn `COUNT(tong_tien)`.

### Bài 4. Tìm khách hàng chưa có đơn

**Yêu cầu:** giữ mọi khách hàng và đếm số đơn thật.

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    COUNT(dh.id) AS so_don
FROM agg_khach_hang AS kh
LEFT JOIN agg_don_hang AS dh
    ON dh.khach_hang_id = kh.id
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

**Đáp án:** An 3, Bình 3, Chi 0, Dũng 2. Nếu thay `COUNT(dh.id)` bằng `COUNT(*)`, Chi có thể bị đếm sai thành 1 vì LEFT JOIN vẫn tạo một hàng cho phía khách hàng.

### Bài 5. Tìm khách hàng có tổng PAID ít nhất 300000

~~~sql
SELECT
    khach_hang_id,
    SUM(tong_tien) AS tong_paid
FROM agg_don_hang
WHERE trang_thai = 'PAID'
GROUP BY khach_hang_id
HAVING SUM(tong_tien) >= 300000
ORDER BY khach_hang_id;
~~~

**Đáp án:** An (ID 1) có 400000 và Bình (ID 2) có 300000. Dùng dấu `>=` nên Bình vẫn được chọn.

### Bài 6. SUM trên nhóm toàn NULL

**Yêu cầu:** tính SUM/AVG của Dũng và hiển thị thêm COUNT.

~~~sql
SELECT
    COUNT(*) AS so_hang,
    COUNT(tong_tien) AS so_gia_tri,
    SUM(tong_tien) AS tong,
    AVG(tong_tien) AS avg_tien,
    COALESCE(SUM(tong_tien), 0) AS tong_hien_thi
FROM agg_don_hang
WHERE khach_hang_id = 4;
~~~

**Đáp án:** 2 hàng, 0 giá trị không NULL, SUM NULL, AVG NULL và tổng hiển thị 0. `tong_hien_thi = 0` không chứng minh hai đơn thật sự có giá trị tiền bằng 0.

### Bài 7. Ngày đặt đơn sớm nhất và muộn nhất theo khách hàng

~~~sql
SELECT
    kh.ho_ten,
    MIN(dh.ngay_dat) AS dau,
    MAX(dh.ngay_dat) AS cuoi
FROM agg_khach_hang AS kh
LEFT JOIN agg_don_hang AS dh
    ON dh.khach_hang_id = kh.id
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

**Đáp án:** An từ 01/11 đến 05/11, Bình từ 02/11 đến 07/11, Chi NULL/NULL, Dũng từ 08/11 đến 09/11 năm 2026.

### Bài 8. Tại sao AVG khác nhau?

Cho hai biểu thức:

~~~sql
SELECT
    AVG(tong_tien) AS a,
    AVG(COALESCE(tong_tien, 0)) AS b
FROM agg_don_hang;
~~~

**Đáp án:** a = 175000 vì chỉ tính 4 giá trị không NULL; b = 87500 vì NULL được biến thành 0 và mẫu số thành 8. Sự khác biệt không phải lỗi SQL mà là **hai cách định nghĩa chỉ số khác nhau**.

### Bài 9. Vì sao tổng sau JOIN bị tăng?

Sau khi tạo bảng `agg_dong_hang` ở phần 12:

~~~sql
SELECT SUM(dh.tong_tien)
FROM agg_don_hang AS dh
JOIN agg_dong_hang AS ct
    ON ct.don_hang_id = dh.id
WHERE dh.trang_thai = 'PAID';
~~~

**Đáp án:** 1250000, không phải 700000, vì giá trị tiền của đơn 101 và 106 bị lặp theo số dòng chi tiết. Cách sửa là tổng hợp trên bảng đơn hoặc tiền tổng hợp phía chi tiết thành một dòng mỗi đơn trước khi JOIN.

### Bài 10. Viết báo cáo chất lượng số liệu theo trạng thái

**Yêu cầu:** với mỗi trạng thái, hiển thị số đơn, số đơn có tiền, số đơn thiếu tiền và tổng tiền nếu có.

~~~sql
SELECT
    trang_thai,
    COUNT(*) AS so_don,
    COUNT(tong_tien) AS so_don_co_tien,
    COUNT(*) - COUNT(tong_tien) AS so_don_thieu_tien,
    SUM(tong_tien) AS tong
FROM agg_don_hang
GROUP BY trang_thai
ORDER BY trang_thai;
~~~

**Kết quả:**

| trang_thai | so_don | so_don_co_tien | so_don_thieu_tien | tong |
|---|---:|---:|---:|---|
| CANCELLED | 1 | 0 | 1 | NULL |
| NEW | 2 | 0 | 2 | NULL |
| PAID | 5 | 4 | 1 | 700000 |

Đây là ví dụ báo cáo kết hợp **chỉ số tổng hợp** và **chỉ số chất lượng dữ liệu**. Một tổng tiền lớn không nói lên đầy đủ mức độ tin cậy khi vẫn còn các đơn thiếu giá trị.

## 19. Kết luận

`SUM`, `AVG`, `MIN` và `MAX` là các hàm cốt lõi để tổng hợp dữ liệu SQL. Chúng có thể hoạt động trên toàn bộ bảng, trong từng nhóm `GROUP BY`, qua các điều kiện `FILTER/CASE` và trong cửa sổ `OVER(...)` khi DBMS hỗ trợ.

Những điều cần luôn ghi nhớ:

1. **SUM, AVG, MIN và MAX thông thường bỏ qua NULL** trong biểu thức đầu vào; số 0 vẫn là giá trị hợp lệ.
2. **AVG chia cho số giá trị không NULL**, không tự chia cho tổng số hàng.
3. **Khi tất cả đầu vào đều NULL hoặc không có giá trị nào**, bốn hàm này trả NULL theo ngữ nghĩa SQL thông thường; `COUNT` trả 0 trên tập rỗng.
4. **COALESCE bên trong và bên ngoài hàm tổng hợp có thể mang ý nghĩa khác nhau**, nhất là với AVG và tập rỗng.
5. **GROUP BY, WHERE, HAVING, LEFT JOIN** thay đổi tập dòng và mức chi tiết của phép tính; phải xác định rõ đang tổng hợp theo đơn, theo khách hàng hay theo dòng sản phẩm.
6. **Không dùng SUM(DISTINCT) để che lỗi JOIN nhân dòng**; cần xử lý đúng khóa JOIN và mức chi tiết nguồn.
7. **MIN/MAX trên ngày và chuỗi không đồng nghĩa tìm cả bản ghi** hoặc suy ra thứ tự ưu tiên nghiệp vụ.
8. Khi báo cáo có dữ liệu thiếu, hãy hiển thị thêm **COUNT(*) và COUNT(cot)** để người đọc hiểu số lượng giá trị thực sự tham gia phép tính.

Hiểu đúng cách xử lý NULL và mẫu số của các hàm tổng hợp là nền tảng để xây dựng báo cáo SQL chính xác, đặc biệt khi dữ liệu chưa hoàn chỉnh hoặc được kết hợp từ nhiều bảng.
