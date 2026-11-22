# CASE kết hợp NULLIF và COALESCE trong SQL

Trong truy vấn SQL, dữ liệu thực tế hiếm khi đồng nhất: có đơn hàng chưa biết trạng thái, người dùng để trống email, số lượng bằng `0`, mức giảm giá chưa nhập hoặc nhiều nguồn cùng cung cấp một thông tin. Nếu xử lý tất cả các tình huống đó bằng một biểu thức so sánh đơn giản, kết quả có thể sai hoặc khó hiểu. SQL cung cấp các biểu thức **`CASE`**, **`NULLIF`** và **`COALESCE`** để rẽ nhánh, quy một giá trị đặc biệt thành `NULL`, rồi chọn giá trị thay thế phù hợp.

Ba công cụ này thường được dùng **cùng nhau**, nhưng mỗi công cụ có trách nhiệm khác nhau:

| Công cụ | Ý tưởng chính | Ví dụ |
| --- | --- | --- |
| `CASE` | Chọn kết quả theo **điều kiện** | Đơn đã thanh toán trả `'HOAN_TAT'`, đơn bị hủy trả `'DUNG'` |
| `NULLIF(a, b)` | Trả `NULL` khi hai biểu thức **bằng nhau**; nếu không, trả `a` | Đổi mẫu số `0` thành `NULL` |
| `COALESCE(a, b, ...)` | Trả **biểu thức đầu tiên khác `NULL`** | Dùng tên liên hệ phụ nếu tên chính chưa có |

Ví dụ điển hình:

~~~sql
COALESCE(NULLIF(btrim(email), ''), '(chưa cung cấp)')
~~~

Trong PostgreSQL, `btrim` xóa khoảng trắng ở hai đầu; `NULLIF` biến chuỗi rỗng sau làm sạch thành `NULL`; `COALESCE` chọn nhãn hiển thị khi không còn giá trị. Nếu cần phân loại dựa trên điều kiện phức tạp hơn, ta đặt biểu thức đó bên trong một `CASE`.

Bài sử dụng **PostgreSQL** để minh họa thực hành. `CASE`, `NULLIF` và `COALESCE` là những cấu phần SQL phổ biến, nhưng các chi tiết như kiểu dữ liệu được suy ra, chuỗi rỗng và hàm riêng của từng hệ quản trị vẫn cần được lưu ý.

## 1. Nền tảng: NULL và logic ba giá trị

`NULL` có nghĩa **không có hoặc chưa biết giá trị**. Nó không đồng nghĩa với `0`, `FALSE`, `''` hay chuỗi ký tự `'NULL'`:

~~~sql
SELECT
    NULL = NULL AS so_sanh_null,
    NULL = 0 AS so_sanh_so_khong,
    NULL IS NULL AS kiem_tra_null;
~~~

Trong SQL, hai phép `=` ở trên có kết quả logic **`UNKNOWN`** (thường hiển thị như `NULL`); `IS NULL` trả `TRUE`. Điều đó ảnh hưởng trực tiếp đến rẽ nhánh:

~~~sql
SELECT CASE
         WHEN NULL = NULL THEN 'BANG_NHAU'
         ELSE 'KHONG_VAO_NHANH_TRUE'
       END AS ket_qua;
~~~

Kết quả là `KHONG_VAO_NHANH_TRUE` vì `CASE WHEN` chỉ chọn nhánh có điều kiện nhận giá trị **`TRUE`**. Điều kiện `FALSE` hoặc `UNKNOWN` đều không được chọn.

Khi cần kiểm tra sự thiếu dữ liệu:

~~~sql
SELECT CASE
         WHEN NULL IS NULL THEN 'CHUA_CO_DU_LIEU'
         ELSE 'DA_CO'
       END AS ket_qua;
~~~

Kết quả là `CHUA_CO_DU_LIEU`. Hãy ghi nhớ điểm này trước khi kết hợp các biểu thức, vì `NULLIF` và `COALESCE` đều dựa vào ý nghĩa riêng của `NULL`.

## 2. Tạo bảng dữ liệu để thực hành

Ta sử dụng một bảng đơn hàng nhỏ, có những trường hợp cố tình để `NULL`, chuỗi rỗng và số lượng bằng không. Ví dụ sau chạy trong một phiên **PostgreSQL**; bảng `TEMP` chỉ tồn tại trong phiên kết nối đó.

~~~sql
CREATE TEMP TABLE don_hang_case (
    id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL,
    kenh_ban TEXT,
    trang_thai TEXT,
    so_luong INTEGER CHECK (so_luong >= 0),
    don_gia NUMERIC(12, 2) NOT NULL CHECK (don_gia >= 0),
    giam_gia NUMERIC(12, 2) CHECK (giam_gia >= 0),
    email TEXT,
    ngay_giao DATE
);

INSERT INTO don_hang_case
    (id, khach_hang_id, kenh_ban, trang_thai,
     so_luong, don_gia, giam_gia, email, ngay_giao)
VALUES
    (101, 1, 'WEB',      'DA_THANH_TOAN', 2, 100000, 10000,
     ' an@example.com ', DATE '2026-10-10'),
    (102, 1, 'APP',      'MOI',           1, 250000, NULL,
     '', NULL),
    (103, 2, NULL,       'DA_HUY',        0, 150000, 0,
     NULL, NULL),
    (104, 3, 'CUA_HANG', NULL,            NULL, 200000, NULL,
     'binh@example.com', DATE '2026-10-12'),
    (105, 4, 'WEB',      'DA_THANH_TOAN', 3, 120000, 20000,
     '   ', NULL),
    (106, 5, 'APP',      'DA_THANH_TOAN', 0, 50000, NULL,
     'chi@example.com', NULL),
    (107, 6, NULL,       'MOI',           4, 75000, 0,
     ' DUNG@EXAMPLE.COM  ', DATE '2026-10-15'),
    (108, 7, 'WEB',      'MOI',           2, 90000, NULL,
     NULL, NULL);
~~~

Các tình huống đáng chú ý:

| id | trạng thái | số lượng | giảm giá | email |
| ---: | --- | ---: | ---: | --- |
| 101 | `DA_THANH_TOAN` | 2 | 10.000 | Có khoảng trắng đầu/cuối |
| 102 | `MOI` | 1 | `NULL` | `''` (chuỗi rỗng) |
| 103 | `DA_HUY` | 0 | 0 | `NULL` |
| 104 | `NULL` | `NULL` | `NULL` | Email có giá trị |
| 105 | `DA_THANH_TOAN` | 3 | 20.000 | `'   '` (chỉ có khoảng trắng) |
| 106 | `DA_THANH_TOAN` | 0 | `NULL` | Email có giá trị |
| 107 | `MOI` | 4 | 0 | Có chữ hoa và khoảng trắng |
| 108 | `MOI` | 2 | `NULL` | `NULL` |

Hai trường hợp `so_luong = 0` và `so_luong IS NULL` được giữ tách biệt có chủ đích: **0 là một giá trị đã biết; NULL là giá trị chưa có/không xác định**. Tương tự, giảm giá `NULL` chỉ được xem là `0` nếu quy tắc nghiệp vụ thực sự định nghĩa “chưa nhập giảm giá” là “không giảm”.

## 3. CASE: biểu thức rẽ nhánh theo điều kiện

`CASE` là **biểu thức** (*expression*) trả về một giá trị, không phải một câu lệnh điều khiển luồng của ngôn ngữ thủ tục. Nó có thể xuất hiện trong `SELECT`, `WHERE`, `ORDER BY`, biểu thức tổng hợp, `UPDATE SET` và nhiều ngữ cảnh SQL khác.

Có hai dạng chính: **searched CASE** và **simple CASE**.

### 3.1. Searched CASE: mỗi WHEN là một điều kiện

~~~sql
CASE
    WHEN dieu_kien_1 THEN gia_tri_1
    WHEN dieu_kien_2 THEN gia_tri_2
    ELSE gia_tri_mac_dinh
END
~~~

DBMS chọn kết quả của **nhánh `WHEN` đầu tiên có điều kiện `TRUE`**. Nếu không có nhánh phù hợp, lấy `ELSE`. Nếu bỏ `ELSE`, kết quả mặc định của biểu thức `CASE` là `NULL`.

Ví dụ phân loại theo giá trị đơn hàng:

~~~sql
SELECT
    id,
    don_gia,
    CASE
        WHEN don_gia >= 200000 THEN 'CAO'
        WHEN don_gia >= 100000 THEN 'TRUNG_BINH'
        ELSE 'THAP'
    END AS nhom_gia
FROM don_hang_case
ORDER BY id;
~~~

Ở đây, nhánh `>= 200000` đứng trước, nên đơn giá 250.000 được phân loại `CAO`, không bị gán `TRUNG_BINH`. Nếu đảo thứ tự:

~~~sql
CASE
    WHEN don_gia >= 100000 THEN 'TRUNG_BINH'
    WHEN don_gia >= 200000 THEN 'CAO'
    ELSE 'THAP'
END
~~~

nhánh `CAO` sẽ không bao giờ được chọn đối với các giá trị từ 200.000 trở lên, vì điều kiện `>= 100000` đã khớp trước. **Thứ tự WHEN là một phần của ngữ nghĩa**, nhất là khi điều kiện chồng lấn.

### 3.2. CASE và NULL

Nếu một trạng thái chưa được nhập, ta có thể muốn phân loại tường minh:

~~~sql
SELECT
    id,
    trang_thai,
    CASE
        WHEN trang_thai IS NULL THEN 'CHUA_XAC_DINH'
        WHEN trang_thai = 'DA_THANH_TOAN' THEN 'HOAN_TAT'
        WHEN trang_thai = 'DA_HUY' THEN 'KET_THUC_KHONG_THANH_CONG'
        WHEN trang_thai = 'MOI' THEN 'DANG_XU_LY'
        ELSE 'TRANG_THAI_KHAC'
    END AS nhom_trang_thai
FROM don_hang_case
ORDER BY id;
~~~

Dòng 104 có `trang_thai = NULL` đi vào nhánh `IS NULL`. Nếu bỏ nhánh đó, dòng 104 có thể rơi vào `ELSE`, nhưng khi ấy `TRANG_THAI_KHAC` sẽ gộp **giá trị chưa biết** với **giá trị bất thường nhưng đã biết** — có thể làm mất thông tin cần cho xử lý nghiệp vụ.

### 3.3. Simple CASE: so sánh một biểu thức với nhiều giá trị

Dạng thứ hai:

~~~sql
CASE bieu_thuc
    WHEN gia_tri_1 THEN ket_qua_1
    WHEN gia_tri_2 THEN ket_qua_2
    ELSE ket_qua_khac
END
~~~

Ví dụ:

~~~sql
SELECT
    id,
    CASE trang_thai
        WHEN 'MOI' THEN 'Chờ xử lý'
        WHEN 'DA_THANH_TOAN' THEN 'Đã thanh toán'
        WHEN 'DA_HUY' THEN 'Đã hủy'
        ELSE 'Khác hoặc chưa rõ'
    END AS hien_thi
FROM don_hang_case
ORDER BY id;
~~~

`simple CASE` phù hợp khi chỉ đối chiếu **một biểu thức** với nhiều giá trị cụ thể. Nhưng nó không có nghĩa “`WHEN NULL` sẽ khớp một cột `NULL`”:

~~~sql
-- KHÔNG dùng dạng này để bắt trường hợp NULL:
CASE trang_thai
    WHEN NULL THEN 'CHUA_CO_TRANG_THAI'
    ELSE 'KHAC'
END
~~~

Vì phép đối chiếu thông thường với `NULL` không cho `TRUE`, hãy dùng **searched CASE** với `WHEN trang_thai IS NULL` nếu cần xử lý riêng dữ liệu thiếu.

### 3.4. CASE không tự thay đổi bảng

~~~sql
SELECT
    id,
    CASE WHEN so_luong IS NULL THEN 'THIEU_SO_LUONG'
         ELSE 'DA_CO_SO_LUONG'
    END AS ket_qua_kiem_tra
FROM don_hang_case;
~~~

Kết quả của `CASE` ở đây là **một cột tính toán trong kết quả truy vấn**. Nó không cập nhật `so_luong`, không thêm cột vật lý vào bảng và không thay thế một ràng buộc dữ liệu. Muốn lưu nhãn, cần thiết kế cột thực/cột được sinh hoặc câu lệnh ghi phù hợp.

## 4. NULLIF: đổi giá trị đặc biệt thành NULL

Cú pháp:

~~~sql
NULLIF(bieu_thuc_1, bieu_thuc_2)
~~~

`NULLIF(a, b)` trả `NULL` khi phép so sánh `a = b` là `TRUE`; nếu không, trả giá trị `a` (sau các quy tắc giải quyết kiểu dữ liệu của DBMS).

Có thể hình dung bằng `CASE`:

~~~sql
CASE
    WHEN a = b THEN NULL
    ELSE a
END
~~~

Đây là cách mô tả **ngữ nghĩa thông thường**, không phải cam kết rằng bộ tối ưu hóa phải thực thi bằng đúng cấu trúc đó hoặc mọi hệ quản trị sẽ đưa các biểu thức có side effect qua cùng số lần đánh giá.

### 4.1. Ví dụ với số và chuỗi

~~~sql
SELECT
    NULLIF(0, 0) AS a,
    NULLIF(5, 0) AS b,
    NULLIF('MOI', 'MOI') AS c,
    NULLIF('MOI', 'DA_HUY') AS d;
~~~

Kết quả logic:

| Biểu thức | Kết quả |
| --- | --- |
| `NULLIF(0, 0)` | `NULL` |
| `NULLIF(5, 0)` | `5` |
| `NULLIF('MOI', 'MOI')` | `NULL` |
| `NULLIF('MOI', 'DA_HUY')` | `'MOI'` |

`NULLIF` hữu ích khi có một **giá trị đại diện cho việc chưa có dữ liệu** trong hệ thống cũ, ví dụ chuỗi rỗng hoặc mã `'N/A'`. Nhưng phép biến đổi chỉ đúng khi quy tắc nghiệp vụ xác nhận giá trị đó thực sự có nghĩa “không có”.

### 4.2. NULLIF kết hợp TRIM

Trên PostgreSQL, chuỗi `''` khác với `NULL`. Nếu email gồm toàn dấu cách thì `NULLIF(email, '')` **không** phát hiện được:

~~~sql
SELECT
    NULLIF('   ', '') AS chua_trim,
    NULLIF(btrim('   '), '') AS da_trim;
~~~

`chua_trim` là `'   '`; `da_trim` là `NULL`. Thứ tự cần thiết là:

~~~sql
NULLIF(btrim(email), '')
~~~

`btrim` đưa chuỗi chỉ có dấu cách thông thường thành rỗng, rồi `NULLIF` chuyển rỗng thành `NULL`. Nếu email ban đầu đã là `NULL`, kết quả vẫn là `NULL`.

Áp dụng vào bảng mẫu:

~~~sql
SELECT
    id,
    email AS email_goc,
    NULLIF(btrim(email), '') AS email_sau_lam_sach
FROM don_hang_case
ORDER BY id;
~~~

Dòng 102 (chuỗi rỗng), 105 (ba dấu cách), 103 và 108 (`NULL`) đều có `email_sau_lam_sach = NULL`. Dòng 101 có `'an@example.com'` sau khi bỏ khoảng trắng; dòng 107 vẫn có chữ hoa `DUNG@EXAMPLE.COM` vì phép này chưa gọi `LOWER`.

### 4.3. NULLIF không phải phép lọc bỏ hàng

~~~sql
SELECT id, NULLIF(so_luong, 0) AS so_luong_khac_khong
FROM don_hang_case;
~~~

Các dòng có `so_luong = 0` vẫn **xuất hiện trong kết quả**, nhưng biểu thức trả `NULL`. Nếu muốn loại hẳn hàng có số lượng bằng không, cần điều kiện `WHERE so_luong <> 0` hoặc điều kiện nghiệp vụ phù hợp. Cũng cần chú ý `WHERE so_luong <> 0` không giữ những hàng `so_luong IS NULL`.

### 4.4. NULLIF không tự “sửa” dữ liệu nguồn

Đọc `NULLIF(so_luong, 0)` không biến số lượng bằng không thành `NULL` trong bảng. Nếu không muốn lưu `0` như một trạng thái thiếu, cần thiết kế lại quy tắc nhập và ràng buộc; không nên chỉ đặt phép biến đổi ở mọi truy vấn để che dữ liệu mơ hồ.

## 5. COALESCE: chọn giá trị đầu tiên khác NULL

Cú pháp:

~~~sql
COALESCE(bieu_thuc_1, bieu_thuc_2, ...)
~~~

Kết quả là **giá trị đầu tiên không phải `NULL`** theo thứ tự đối số. Nếu tất cả đối số đều `NULL`, kết quả là `NULL`.

~~~sql
SELECT
    COALESCE(NULL, 'gia_tri_phu', 'gia_tri_sau') AS a,
    COALESCE('gia_tri_chinh', 'gia_tri_phu') AS b,
    COALESCE(NULL::text, NULL::text) AS c;
~~~

Kết quả: `a = 'gia_tri_phu'`, `b = 'gia_tri_chinh'`, `c = NULL`. Ép kiểu `NULL::text` ở ví dụ thứ ba giúp PostgreSQL biết kiểu của biểu thức một cách rõ ràng.

### 5.1. Thứ tự đối số phản ánh mức ưu tiên nguồn

Giả sử có tên hiển thị, tên pháp lý và nhãn mặc định:

~~~sql
COALESCE(ten_hien_thi, ten_phap_ly, '(khách chưa có tên)')
~~~

Nghĩa là: dùng tên hiển thị nếu có; nếu thiếu thì dùng tên pháp lý; nếu cả hai thiếu mới dùng nhãn mặc định. Đảo hai đối số đầu sẽ thay đổi **chính sách ưu tiên**, không chỉ thay đổi hiệu năng.

### 5.2. COALESCE không bỏ qua 0, FALSE hay chuỗi rỗng

~~~sql
SELECT
    COALESCE(0, 99) AS so,
    COALESCE(FALSE, TRUE) AS logic,
    COALESCE('', 'du_phong') AS van_ban;
~~~

Trong PostgreSQL, kết quả lần lượt là **`0`**, **`FALSE`** và **`''`**. Cả ba giá trị đều **khác `NULL`**. Vì vậy nếu muốn `COALESCE` bỏ qua giá trị `0` hoặc `''` như một ký hiệu cho “không hợp lệ”, phải **chủ động chuẩn hóa bằng `NULLIF` trước**:

~~~sql
SELECT
    COALESCE(NULLIF(0, 0), 99) AS so_du_phong,
    COALESCE(NULLIF('', ''), 'du_phong') AS chuoi_du_phong;
~~~

Kết quả là `99` và `'du_phong'`. Nhưng khi `0` là giá trị hợp lệ (ví dụ số lượng còn lại bằng 0), thay nó bằng 99 sẽ **làm sai dữ liệu**; không nên dùng `NULLIF` trừ khi có lý do nghiệp vụ.

### 5.3. COALESCE trong phép tính

Giả sử `giam_gia IS NULL` có nghĩa chưa áp dụng giảm giá và nghiệp vụ quy định số giảm giá mặc định bằng 0:

~~~sql
SELECT
    id,
    so_luong,
    don_gia,
    giam_gia,
    so_luong * don_gia - COALESCE(giam_gia, 0) AS thanh_tien
FROM don_hang_case
ORDER BY id;
~~~

Với dòng 101: `2 * 100000 - 10000 = 190000`. Với dòng 102: `1 * 250000 - 0 = 250000`. Với dòng 104: `so_luong IS NULL`, nên cả phép nhân và biểu thức thành tiền là **`NULL`**, mặc dù `giam_gia` được thay bằng 0. Điều này có thể là **tín hiệu đúng**: chưa biết số lượng thì không thể tính chính xác thành tiền.

Nếu viết:

~~~sql
COALESCE(so_luong, 0) * don_gia - COALESCE(giam_gia, 0)
~~~

dòng 104 sẽ được tính thành `0`, vô tình gộp “chưa nhập số lượng” với “số lượng thực tế bằng không”. Chỉ áp dụng cách thay thế này nếu nghiệp vụ khẳng định hai trường hợp tương đương.

## 6. Kết hợp CASE, NULLIF và COALESCE

Ba biểu thức có thể lồng nhau để giải quyết những quy tắc nhiều bước:

~~~text
Giá trị nguồn
    |
    v
Làm sạch / chuẩn hóa đầu vào
    |
    v
NULLIF: đổi giá trị đặc biệt thành NULL (nếu có quy tắc)
    |
    v
CASE: chọn cách xử lý theo điều kiện
    |
    v
COALESCE: chọn nguồn thay thế hoặc nhãn hiển thị
~~~

Đó là một **cách tổ chức ý nghĩa**, không phải thứ tự bắt buộc trong mọi biểu thức SQL. Có tình huống `COALESCE` nằm trong nhánh `CASE`; có tình huống `CASE` nằm trong `COALESCE`. Quan trọng là trả lời trước: **giá trị nào được coi là “thiếu”, điều kiện nào phân loại nó, và giá trị dự phòng có được phép thay thế không?**

### 6.1. Email: chuẩn hóa và phân loại dữ liệu thiếu

Yêu cầu minh họa:

1. Bỏ khoảng trắng thường ở đầu/cuối;
2. Chuỗi rỗng sau khi bỏ khoảng trắng được coi là chưa nhập;
3. Khi có email, tạo bản chữ thường để đối chiếu;
4. Khi hiển thị, dùng nhãn `'(chưa cung cấp)'` nếu thiếu.

~~~sql
SELECT
    id,
    email,
    NULLIF(lower(btrim(email)), '') AS email_khoa_so_khop,
    COALESCE(
        NULLIF(lower(btrim(email)), ''),
        '(chưa cung cấp)'
    ) AS email_hien_thi
FROM don_hang_case
ORDER BY id;
~~~

Một số kết quả:

| id | email_khoa_so_khop | email_hien_thi |
| ---: | --- | --- |
| 101 | `an@example.com` | `an@example.com` |
| 102 | `NULL` | `(chưa cung cấp)` |
| 103 | `NULL` | `(chưa cung cấp)` |
| 105 | `NULL` | `(chưa cung cấp)` |
| 107 | `dung@example.com` | `dung@example.com` |

Đây chỉ là một **chính sách chuẩn hóa ví dụ**. Quy tắc email thực tế có thể cần xử lý phần local-part khác với domain; không nên tự ý bỏ dấu chấm, phần sau `+` hoặc kết luận hai tài khoản là một chỉ vì khóa văn bản khớp. Giá trị hiển thị `'(chưa cung cấp)'` không nên được lưu làm email thật hay khóa duy nhất.

Có thể kết hợp thêm `CASE` để phân biệt **dữ liệu thiếu** và **dữ liệu có vẻ sai định dạng**:

~~~sql
WITH email_chuan AS (
    SELECT
        id,
        NULLIF(lower(btrim(email)), '') AS email_key
    FROM don_hang_case
)
SELECT
    id,
    email_key,
    CASE
        WHEN email_key IS NULL THEN 'CHUA_CO_EMAIL'
        WHEN email_key LIKE '%@%' THEN 'CAN_XAC_MINH'
        ELSE 'CAN_KIEM_TRA_DINH_DANG'
    END AS ket_qua
FROM email_chuan
ORDER BY id;
~~~

`LIKE '%@%'` chỉ là **phép kiểm tra rất sơ bộ có ký tự `@`**, không phải validation email đầy đủ. Nhãn `CAN_XAC_MINH` được dùng để nhắc rằng ngay cả chuỗi trông giống email cũng cần quy trình xác minh phù hợp.

### 6.2. Số lượng: phân biệt NULL, 0 và số dương

Giả sử ứng dụng cần một nhãn để hiển thị:

~~~sql
SELECT
    id,
    so_luong,
    CASE
        WHEN so_luong IS NULL THEN 'CHUA_NHAP'
        WHEN so_luong = 0 THEN 'BANG_KHONG'
        WHEN so_luong > 0 THEN 'DA_CO_SO_LUONG'
        ELSE 'GIA_TRI_KHONG_HOP_LE'
    END AS nhom_so_luong
FROM don_hang_case
ORDER BY id;
~~~

Với dữ liệu mẫu, dòng 104 là `CHUA_NHAP`, dòng 103 và 106 là `BANG_KHONG`, các dòng còn lại có số lượng dương. Nhánh cuối có thể không xuất hiện vì bảng đang có ràng buộc `CHECK (so_luong >= 0)`, nhưng nó diễn đạt chính sách cho trường hợp dữ liệu không phù hợp nếu mô hình thay đổi.

Để tạo **giá trị dùng khi tính tỷ lệ** mà bỏ qua số lượng bằng không:

~~~sql
SELECT
    id,
    so_luong,
    NULLIF(so_luong, 0) AS so_luong_lam_mau_so
FROM don_hang_case
ORDER BY id;
~~~

`NULLIF` đưa `0` thành `NULL` ở **biểu thức tính toán**, không làm mất khả năng phân biệt nguyên nhân ở cột gốc. Nếu muốn báo “chưa nhập” và “bằng không” khác nhau, hãy dùng `CASE` để tạo nhãn như trên, không chỉ nhìn vào biểu thức `NULLIF`.

### 6.3. Chia cho 0 an toàn bằng NULLIF

Giả sử cần tính **thành tiền bình quân trên một đơn vị**:

~~~sql
SELECT
    id,
    so_luong,
    (
        so_luong * don_gia - COALESCE(giam_gia, 0)
    ) / NULLIF(so_luong, 0) AS gia_binh_quan_moi_don_vi
FROM don_hang_case
ORDER BY id;
~~~

Các tình huống:

| id | so_luong | Kết quả biểu thức |
| ---: | ---: | --- |
| 101 | 2 | `95000.00` vì `(200000 - 10000) / 2` |
| 102 | 1 | `250000.00` |
| 103 | 0 | `NULL` vì mẫu số bị `NULLIF` đổi thành `NULL` |
| 104 | `NULL` | `NULL` vì chưa biết số lượng |
| 105 | 3 | Khoảng `113333.33` nếu được làm tròn đến hai chữ số |
| 106 | 0 | `NULL` do không chia cho 0 |

Đây là dạng **chia an toàn trước lỗi mẫu số bằng 0**. Nếu `NULLIF(so_luong, 0)` trả `NULL`, phép chia trả `NULL` thay vì lỗi chia cho 0 trong PostgreSQL. Biểu thức mẫu trên dùng kiểu `NUMERIC` do `don_gia` là `NUMERIC`, nên tránh lỗi chia số nguyên làm mất phần thập phân ở một số phép tính khác.

Nếu yêu cầu hiển thị đúng hai chữ số thập phân, có thể dùng:

~~~sql
SELECT
    id,
    ROUND(
        (so_luong * don_gia - COALESCE(giam_gia, 0))
        / NULLIF(so_luong, 0),
        2
    ) AS gia_binh_quan
FROM don_hang_case
ORDER BY id;
~~~

**Có nên thay kết quả `NULL` bằng 0 không?** Chỉ khi nghiệp vụ cho rằng “không tính được giá bình quân” nên được trình bày như 0. Với báo cáo tài chính và phép chia cho mẫu số bằng 0, `0` có thể gây hiểu nhầm là đã tính được kết quả thực sự bằng không. Một cách rõ hơn là dùng `CASE` để phân biệt:

~~~sql
SELECT
    id,
    CASE
        WHEN so_luong IS NULL THEN 'CHUA_CO_SO_LUONG'
        WHEN so_luong = 0 THEN 'KHONG_THE_CHIA_CHO_0'
        ELSE 'TINH_DUOC'
    END AS trang_thai_tinh,
    ROUND(
        (so_luong * don_gia - COALESCE(giam_gia, 0))
        / NULLIF(so_luong, 0),
        2
    ) AS gia_binh_quan
FROM don_hang_case
ORDER BY id;
~~~

Ở đây `CASE` nêu **lý do** còn `NULLIF` bảo vệ mẫu số.

### 6.4. CASE lồng COALESCE: ưu tiên trạng thái có giá trị

Ví dụ một báo cáo cần cột trạng thái hiển thị:

~~~sql
SELECT
    id,
    CASE
        WHEN trang_thai = 'DA_THANH_TOAN'
            THEN 'Đã thanh toán'
        WHEN trang_thai = 'DA_HUY'
            THEN 'Đã hủy'
        WHEN trang_thai = 'MOI'
            THEN 'Chờ xử lý'
        ELSE COALESCE(
            NULLIF(btrim(trang_thai), ''),
            'Chưa xác định'
        )
    END AS trang_thai_hien_thi
FROM don_hang_case
ORDER BY id;
~~~

Những trạng thái chuẩn được thay nhãn dễ đọc. `ELSE` giữ một trạng thái khác đã nhập (sau khi bỏ khoảng trắng) nếu có, nhưng dùng `'Chưa xác định'` khi trạng thái là `NULL` hoặc chuỗi rỗng sau trim. Đây là ví dụ **`CASE` điều khiển quy tắc nghiệp vụ**, còn `NULLIF` và `COALESCE` xử lý trường hợp dự phòng.

## 7. Dùng CASE trong thống kê và tổng hợp

`CASE` đặc biệt hữu ích khi cần tính nhiều chỉ tiêu từ **cùng một tập hàng**. Ta có thể đặt điều kiện vào bên trong `SUM`, `COUNT`, `AVG` hoặc các biểu thức tổng hợp khác.

### 7.1. Đếm đơn theo trạng thái

~~~sql
SELECT
    COUNT(*) AS tong_so_don,
    SUM(CASE WHEN trang_thai = 'MOI' THEN 1 ELSE 0 END) AS so_don_moi,
    SUM(CASE WHEN trang_thai = 'DA_THANH_TOAN' THEN 1 ELSE 0 END)
        AS so_don_da_thanh_toan,
    SUM(CASE WHEN trang_thai = 'DA_HUY' THEN 1 ELSE 0 END) AS so_don_huy,
    SUM(CASE WHEN trang_thai IS NULL THEN 1 ELSE 0 END)
        AS so_don_chua_ro
FROM don_hang_case;
~~~

Với tám dòng mẫu:

| tong_so_don | so_don_moi | so_don_da_thanh_toan | so_don_huy | so_don_chua_ro |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 3 | 3 | 1 | 1 |

Trong các biểu thức `SUM(CASE ... THEN 1 ELSE 0 END)`, mỗi hàng góp **1 nếu đúng điều kiện, 0 nếu không**. Nhờ `ELSE 0`, mỗi hàng đóng góp một số xác định vào chỉ tiêu, kể cả khi trạng thái `NULL`.

PostgreSQL cũng có dạng tổng hợp có `FILTER`:

~~~sql
SELECT
    COUNT(*) AS tong_so_don,
    COUNT(*) FILTER (WHERE trang_thai = 'MOI') AS so_don_moi,
    COUNT(*) FILTER (WHERE trang_thai = 'DA_THANH_TOAN')
        AS so_don_da_thanh_toan
FROM don_hang_case;
~~~

`FILTER (WHERE ...)` diễn đạt điều kiện ngay tại hàm tổng hợp, nhưng mức hỗ trợ giữa DBMS có thể khác; mẫu `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` phổ biến và dễ gặp trong SQL đa hệ.

### 7.2. COUNT(CASE ...) khác SUM(CASE ...)

~~~sql
SELECT
    COUNT(CASE WHEN trang_thai = 'MOI' THEN 1 END) AS dem_don_moi,
    SUM(CASE WHEN trang_thai = 'MOI' THEN 1 ELSE 0 END)
        AS cong_don_moi
FROM don_hang_case;
~~~

Cả hai trả `3` trong dữ liệu mẫu:

- `COUNT(expr)` chỉ đếm những kết quả **khác `NULL`**. Khi `CASE` không có `ELSE`, những dòng không khớp trả `NULL` và không được đếm.
- `SUM(CASE ... ELSE 0 END)` cộng các giá trị 1 và 0.

**Bẫy:**

~~~sql
COUNT(CASE WHEN trang_thai = 'MOI' THEN 1 ELSE 0 END)
~~~

sẽ đếm **cả tám hàng** vì cả 1 và 0 đều **khác `NULL`**. Muốn đếm có điều kiện bằng `COUNT`, hãy để nhánh không khớp trả `NULL`; muốn dùng `ELSE 0`, hãy dùng `SUM`.

### 7.3. SUM với NULL và tập không có hàng

Ví dụ chỉ tính tổng tiền các đơn đã thanh toán:

~~~sql
SELECT
    SUM(
        CASE
            WHEN trang_thai = 'DA_THANH_TOAN'
                THEN so_luong * don_gia - COALESCE(giam_gia, 0)
            ELSE 0
        END
    ) AS doanh_thu_da_thanh_toan
FROM don_hang_case;
~~~

Theo dữ liệu mẫu, giá trị là **530.000**:

- Đơn 101: `2 * 100000 - 10000 = 190000`;
- Đơn 105: `3 * 120000 - 20000 = 340000`;
- Đơn 106: `0 * 50000 - 0 = 0`.

Đây là phép tính **minh họa** theo giả định giảm giá áp trên cả dòng đơn. Trong hệ thống thật, số tiền thanh toán và doanh thu có thể phụ thuộc hoàn tiền, thuế, phí, ghi nhận doanh thu hoặc lịch sử trạng thái; không suy ra nghiệp vụ kế toán chỉ từ tên cột.

Nếu **lọc `WHERE` không còn hàng nào**, `SUM(...)` trong PostgreSQL thường trả `NULL`, không phải 0:

~~~sql
SELECT
    SUM(tong) AS tong_goc,
    COALESCE(SUM(tong), 0) AS tong_hien_thi
FROM (
    SELECT so_luong * don_gia AS tong
    FROM don_hang_case
    WHERE trang_thai = 'TRANG_THAI_KHONG_TON_TAI'
) AS x;
~~~

`tong_goc = NULL`, `tong_hien_thi = 0`. Thay `NULL` bằng 0 có thể hợp lý cho **tổng doanh thu không có bản ghi**, nhưng không nhất thiết hợp lý cho `AVG` khi không có dữ liệu, bởi “không có mẫu quan sát” khác với “giá trị trung bình bằng 0”.

### 7.4. Phân loại nhóm dữ liệu rồi GROUP BY

Ví dụ chia đơn thành nhóm dựa vào trạng thái:

~~~sql
WITH don_da_phan_loai AS (
    SELECT
        id,
        CASE
            WHEN trang_thai IS NULL THEN 'CHUA_RO'
            WHEN trang_thai = 'DA_THANH_TOAN' THEN 'HOAN_TAT'
            WHEN trang_thai = 'DA_HUY' THEN 'KET_THUC'
            ELSE 'DANG_XU_LY'
        END AS nhom
    FROM don_hang_case
)
SELECT
    nhom,
    COUNT(*) AS so_don
FROM don_da_phan_loai
GROUP BY nhom
ORDER BY nhom;
~~~

CTE giúp xác định công thức `CASE` **một lần**, sau đó dùng nhãn phân nhóm để thống kê. Tuy nhiên cách phân loại phải có quy tắc rõ: `ELSE 'DANG_XU_LY'` cũng chứa trạng thái lạ có giá trị nếu bảng không có ràng buộc trạng thái. Nếu muốn phát hiện trạng thái bất thường, thêm một nhánh `ELSE 'KHAC'` phù hợp.

## 8. Rẽ nhánh trong WHERE, ORDER BY và JOIN

`CASE`, `NULLIF`, `COALESCE` không chỉ dùng trong danh sách `SELECT`.

### 8.1. WHERE: lọc thiếu dữ liệu sau chuẩn hóa

Muốn lấy những đơn **chưa có email có nghĩa** (bao gồm `NULL`, chuỗi rỗng và toàn dấu cách):

~~~sql
SELECT id, email
FROM don_hang_case
WHERE NULLIF(btrim(email), '') IS NULL
ORDER BY id;
~~~

Kết quả: các ID **102, 103, 105, 108**. Với PostgreSQL, `btrim(NULL)` là `NULL`; `NULLIF('', '')` là `NULL`. Vì vậy một phép kiểm tra `IS NULL` bao phủ cả ba dạng dữ liệu thiếu theo quy tắc đã chọn.

Nếu chỉ viết:

~~~sql
WHERE email IS NULL
~~~

thì **không** bao gồm dòng 102 (`''`) hoặc 105 (`'   '`). Việc hai cách có khác nhau là lý do nên chuẩn hóa dữ liệu nguồn hoặc xác định rõ hợp đồng nhập liệu.

### 8.2. ORDER BY: ưu tiên trạng thái do nghiệp vụ định nghĩa

Sắp xếp chữ cái không nhất thiết là thứ tự xử lý mong muốn. Với thứ tự `MOI` trước, `DA_THANH_TOAN` tiếp theo, `DA_HUY` sau cùng:

~~~sql
SELECT id, trang_thai
FROM don_hang_case
ORDER BY
    CASE
        WHEN trang_thai = 'MOI' THEN 1
        WHEN trang_thai = 'DA_THANH_TOAN' THEN 2
        WHEN trang_thai = 'DA_HUY' THEN 3
        ELSE 4
    END,
    id;
~~~

`CASE` tạo một **khóa sắp xếp số** tạm thời. `id` là tiêu chí phụ để thứ tự ổn định giữa các hàng cùng nhóm. Cách này không cần ghi đè giá trị trạng thái gốc.

### 8.3. JOIN: giá trị dự phòng cần có quy tắc

Giả sử bảng cấu hình kênh bán được khai báo:

~~~sql
CREATE TEMP TABLE kenh_ban_mau (
    ma_kenh TEXT PRIMARY KEY,
    ten_hien_thi TEXT
);

INSERT INTO kenh_ban_mau (ma_kenh, ten_hien_thi)
VALUES
    ('WEB', 'Website'),
    ('APP', 'Ứng dụng'),
    ('CUA_HANG', NULL);
~~~

Muốn hiện nhãn kênh bán, ưu tiên tên đã cấu hình; nếu tên cấu hình trống thì dùng mã kênh; nếu đơn chưa có mã thì dùng nhãn mặc định:

~~~sql
SELECT
    d.id,
    COALESCE(
        NULLIF(btrim(k.ten_hien_thi), ''),
        NULLIF(btrim(d.kenh_ban), ''),
        '(chưa rõ kênh)'
    ) AS kenh_hien_thi
FROM don_hang_case AS d
LEFT JOIN kenh_ban_mau AS k
    ON k.ma_kenh = d.kenh_ban
ORDER BY d.id;
~~~

Với `WEB`, hiển thị `Website`; với `APP`, hiển thị `Ứng dụng`; với `CUA_HANG`, do tên cấu hình `NULL` nên hiển thị chính mã `CUA_HANG`; với dòng không có kênh, hiển thị `(chưa rõ kênh)`.

**Lưu ý:** `COALESCE` là chính sách **chọn nguồn giá trị**, không thay thế điều kiện `ON` hoặc bảo đảm quan hệ JOIN. Nếu mã kênh khác nhau nhưng được cố gộp bằng `COALESCE` hoặc giá trị mặc định, có thể vô tình ghép sai nhiều bản ghi.

## 9. Kiểu dữ liệu, ép kiểu và thứ tự đánh giá

Ba biểu thức khá ngắn gọn nhưng dễ gây lỗi nếu trộn các kiểu không tương thích.

### 9.1. Các nhánh CASE phải có kiểu có thể dung hòa

~~~sql
SELECT
    CASE
        WHEN TRUE THEN 10
        ELSE 20
    END AS gia_tri_so;
~~~

Các kết quả đều là số. Nhưng ví dụ:

~~~sql
-- Không nên trộn số với nhãn văn bản mà không có chủ đích:
-- CASE WHEN so_luong IS NULL THEN 'CHUA_CO' ELSE so_luong END
~~~

có thể thất bại khi PostgreSQL tìm kiểu chung cho nhánh `'CHUA_CO'` và `INTEGER`. Nếu cần hiển thị kiểu văn bản, hãy chuyển **cả nhánh số** thành chuỗi:

~~~sql
SELECT
    id,
    CASE
        WHEN so_luong IS NULL THEN 'CHUA_CO'
        ELSE so_luong::text
    END AS so_luong_hien_thi
FROM don_hang_case
ORDER BY id;
~~~

Ngược lại, nếu muốn kết quả dùng để tính toán, nên giữ nó là kiểu số và dùng cột nhãn riêng cho tình trạng thiếu dữ liệu.

`COALESCE` cũng yêu cầu các đối số có thể hợp nhất thành kiểu kết quả phù hợp:

~~~sql
SELECT COALESCE(so_luong, 0) AS so_luong_de_tinh
FROM don_hang_case;
~~~

Trong PostgreSQL, `COALESCE(so_luong, 'không biết')` không phù hợp khi `so_luong` là số nguyên, trừ khi có chuyển kiểu hợp lệ; giá trị chữ không thể được hiểu như một số nguyên. Việc nhãn hiển thị trở thành chuỗi là một quyết định khác với giá trị dùng tính toán.

### 9.2. NULLIF dùng toán tử so sánh có quy tắc kiểu

`NULLIF(a,b)` cần một phép so sánh `a = b` hợp lệ. Với kiểu dữ liệu khác nhau, DBMS có thể chuyển đổi kiểu ngầm định hoặc từ chối. Kiểu trả về theo kết quả phân giải kiểu/toán tử so sánh, không nên giả định mọi `NULLIF(a,b)` giữ đúng kiểu của `a` trong mọi tổ hợp.

Thực hành an toàn là cung cấp **hai đối số cùng kiểu hoặc tương thích rõ ràng**, ví dụ `NULLIF(so_luong, 0)` khi `so_luong` là `INTEGER`, hoặc `NULLIF(btrim(email), '')` với chuỗi văn bản.

### 9.3. Không phụ thuộc tuyệt đối vào short-circuit để tránh mọi lỗi

Về mặt **ngữ nghĩa**, `CASE` chọn nhánh phù hợp đầu tiên và `COALESCE` chọn biểu thức đầu tiên khác `NULL`. PostgreSQL thường chỉ cần đánh giá các nhánh cần thiết tại thời điểm thực thi. Tuy nhiên **bộ lập kế hoạch truy vấn có thể xử lý trước các biểu thức hằng hoặc thực hiện tối ưu hóa**, nên không nên coi đây là cam kết rằng mọi lỗi trong nhánh không được chọn đều luôn bị bỏ qua.

Ví dụ, một biểu thức hằng không hợp lệ như `1 / 0` có thể bị PostgreSQL phát hiện ở giai đoạn lập kế hoạch ngay cả khi người lập trình đặt nó trong một nhánh `CASE` tưởng như không thể chạy.

Với phép chia theo dữ liệu hàng:

~~~sql
gia_tri / NULLIF(mau_so, 0)
~~~

thường rõ ràng và vững hơn việc dựa hoàn toàn vào thứ tự đánh giá các điều kiện tách rời trong `WHERE`. Với chuyển kiểu dữ liệu đầu vào có thể lỗi, nên dùng kiểm tra và cơ chế chuyển đổi an toàn được DBMS hỗ trợ thay vì giả định vế `AND` bên trái sẽ luôn chạy trước.

### 9.4. Cần biết khi nào giá trị dự phòng đang che dữ liệu lỗi

`COALESCE(giam_gia, 0)` là lựa chọn hợp lý **nếu `NULL` có nghĩa không áp dụng giảm giá**. Nhưng:

~~~sql
COALESCE(so_luong, 0)
~~~

có thể gây sai nếu `NULL` có nghĩa “chưa nhập số lượng”. Việc cho một con số thay thế giúp câu SQL không trả `NULL` **không đồng nghĩa kết quả đúng về nghiệp vụ**. Nên hiển thị trạng thái thiếu, đặt `NOT NULL` khi phù hợp, hoặc chuẩn hóa dữ liệu ở nơi nhập để giảm nhu cầu “đoán” giá trị sau này.

## 10. Hiệu năng và tính rõ nghĩa

Một biểu thức `CASE`, `NULLIF` hay `COALESCE` có thể làm truy vấn dài hơn, nhưng **không có quy tắc rằng cứ sử dụng hàm là luôn chậm**. Chi phí phụ thuộc số dòng, kiểu dữ liệu, độ phức tạp biểu thức, chỉ mục, collation và kế hoạch thực thi.

### 10.1. Hàm áp lên cột có thể ảnh hưởng index

~~~sql
SELECT id
FROM don_hang_case
WHERE COALESCE(so_luong, 0) > 2;
~~~

Nếu chỉ cần các hàng có `so_luong > 2`, điều kiện gọn hơn là:

~~~sql
SELECT id
FROM don_hang_case
WHERE so_luong > 2;
~~~

Hai biểu thức cho cùng tập hàng trong bối cảnh so sánh số thông thường: `NULL` không được chọn trong cả hai. Điều kiện trực tiếp trên cột thường dễ tận dụng một chỉ mục B-tree thông thường hơn, dù quyết định cuối vẫn thuộc bộ tối ưu hóa. Không thêm `COALESCE` vào mọi `WHERE` chỉ để tránh `NULL` nếu nó không thay đổi ý nghĩa cần thiết.

Với tìm kiếm email chuẩn hóa:

~~~sql
WHERE lower(btrim(email)) = 'an@example.com'
~~~

một index thường trên `email` có thể không phù hợp. PostgreSQL hỗ trợ **expression index** nếu truy vấn này thường xuyên xuất hiện trên bảng lớn. Tuy nhiên chỉ mục biểu thức cần chiến lược đặt tên, bảo trì khi cập nhật và tương thích với quy tắc collation/chuẩn hóa đã thống nhất.

### 10.2. Dùng CTE/subquery để tránh công thức lặp

Khi một phép chuẩn hóa dùng nhiều lần:

~~~sql
WITH du_lieu_chuan AS (
    SELECT
        id,
        NULLIF(lower(btrim(email)), '') AS email_key,
        so_luong,
        don_gia,
        COALESCE(giam_gia, 0) AS muc_giam_gia
    FROM don_hang_case
)
SELECT
    id,
    email_key,
    CASE
        WHEN email_key IS NULL THEN 'CHUA_CO_EMAIL'
        ELSE 'DA_CO_EMAIL'
    END AS tinh_trang_email,
    so_luong * don_gia - muc_giam_gia AS thanh_tien
FROM du_lieu_chuan
ORDER BY id;
~~~

CTE giúp **đặt tên cho các bước biến đổi** và giảm việc chép cùng biểu thức nhiều lần. Nó không tự bảo đảm chỉ tính mỗi biểu thức một lần ở cấp vật lý, vì DBMS có thể tối ưu hóa/inlining theo phiên bản và ngữ cảnh. Giá trị chính của cách viết là giúp người đọc hiểu rõ cấu trúc và quy tắc nghiệp vụ.

### 10.3. Kiểm tra kế hoạch khi cần

Trong PostgreSQL:

~~~sql
EXPLAIN
SELECT id
FROM don_hang_case
WHERE NULLIF(btrim(email), '') IS NULL;
~~~

`EXPLAIN` mô tả kế hoạch dự kiến, nhưng bảng tạm chỉ có tám hàng nên không đại diện cho hiệu năng sản xuất. Khi đánh giá hệ thống thật, cần dữ liệu và chỉ mục phù hợp, so sánh kế hoạch/truy vấn với kỳ vọng. `EXPLAIN ANALYZE` thực thi truy vấn thật để đo; chỉ dùng ở môi trường và thời điểm thích hợp.

## 11. Khác biệt và hàm tương đương giữa các DBMS

`CASE`, `NULLIF`, `COALESCE` có mặt ở nhiều DBMS hiện đại, nhưng một số hệ có tên hàm dự phòng hoặc đặc điểm riêng:

| Mục đích | PostgreSQL | MySQL | SQL Server | Oracle Database |
| --- | --- | --- | --- | --- |
| Rẽ nhánh theo điều kiện | `CASE WHEN ... THEN ... END` | `CASE`; có thêm hàm `IF()` | `CASE`; có thêm `IIF()` | `CASE`; có thêm `DECODE()` với quy tắc riêng |
| Đổi giá trị trùng thành NULL | `NULLIF(a,b)` | `NULLIF(a,b)` | `NULLIF(a,b)` | `NULLIF(a,b)` |
| Chọn giá trị đầu tiên không NULL | `COALESCE(a,b,...)` | `COALESCE`, `IFNULL(a,b)` | `COALESCE`, `ISNULL(a,b)` | `COALESCE`, `NVL(a,b)` |
| Loại khoảng trắng biên | `btrim(s)`, `TRIM(s)` | `TRIM(s)` | `TRIM(s)` trên phiên bản hỗ trợ | `TRIM(s)` |
| Chuỗi rỗng so với NULL | `''` khác `NULL` | `''` thông thường khác `NULL` | `''` khác `NULL` | Chuỗi rỗng trong các kiểu chuỗi thông dụng thường được coi là `NULL` |

### 11.1. SQL Server: ISNULL không đồng nhất hoàn toàn với COALESCE

Trong SQL Server, `ISNULL(expr, replacement)` là hàm riêng với **hai đối số**. `COALESCE(expr1, expr2, ...)` có thể nhận nhiều đối số và tuân theo quy tắc phân giải kiểu của biểu thức tương tự `CASE`. `ISNULL` có các quy tắc **kiểu trả về, độ dài và nullable metadata** khác `COALESCE`. Thay một hàm bằng hàm kia chỉ vì chúng cùng cho kết quả trên dữ liệu mẫu có thể khiến kết quả bị chuyển kiểu hoặc cắt chuỗi trong trường hợp khác.

Trong SQL Server, `COALESCE` được mô tả như một dạng được chuyển hóa thành `CASE` trong quá trình xử lý, và các biểu thức đối số có thể bị đánh giá nhiều lần ở một số ngữ cảnh, đặc biệt với truy vấn con hoặc biểu thức không ổn định. Với logic phụ thuộc truy vấn con, cần xét mức cô lập, cách tách truy vấn hoặc cơ chế khác phù hợp.

### 11.2. Oracle: chuỗi rỗng và NVL/DECODE

Oracle thường xử lý chuỗi ký tự rỗng `''` như `NULL`; do đó:

~~~sql
COALESCE(NULLIF(TRIM(email), ''), 'CHUA_CO')
~~~

cần được hiểu theo ngữ nghĩa Oracle thay vì giả định `TRIM('')` sẽ tạo một chuỗi rỗng độc lập như trong PostgreSQL. Kết quả mong muốn “hiển thị nhãn khi email không có nội dung” có thể tương tự, nhưng các bước trung gian và ràng buộc chuỗi có thể khác.

Hàm `NVL(a,b)` là lựa chọn quen thuộc ở Oracle cho hai giá trị, còn `COALESCE` phù hợp khi cần nhiều nguồn dự phòng. `DECODE` có quy tắc so sánh đặc thù, gồm cách xử lý `NULL`, nên không được thay thế máy móc bằng **simple `CASE` với `WHEN NULL`**. Khi muốn logic ba giá trị tường minh và tính di chuyển cao, thường ưu tiên `CASE WHEN ... IS NULL`.

### 11.3. MySQL: IFNULL/IF và phép ép kiểu

MySQL hỗ trợ `IFNULL(a,b)` và `IF(dieu_kien, ket_qua_dung, ket_qua_sai)` như những lựa chọn ngắn gọn. Tuy vậy, `COALESCE` và `CASE` phổ biến hơn khi viết SQL có thể chuyển giữa nhiều DBMS. Phép chuyển kiểu tự động và cách so sánh chuỗi của MySQL có thể khác PostgreSQL; khi làm việc với dữ liệu tiền tệ, ngày giờ và chuỗi Unicode, nên xác định kiểu/collation rõ.

### 11.4. PostgreSQL: một vài khả năng bổ sung

PostgreSQL hỗ trợ:

- `NULLIF(a,b)` và `COALESCE(...)` trực tiếp;
- `CASE` trong gần như mọi biểu thức hợp lệ;
- `IS DISTINCT FROM` / `IS NOT DISTINCT FROM` để so sánh **null-safe** khi cần;
- `FILTER (WHERE ...)` trên các hàm tổng hợp hỗ trợ;
- Ép kiểu `::text`, `::numeric` và các hàm văn bản như `btrim`, `regexp_replace`.

Ví dụ so sánh rõ hai giá trị cùng thiếu:

~~~sql
SELECT
    NULL IS NOT DISTINCT FROM NULL AS cung_thieu,
    NULL IS DISTINCT FROM 0 AS null_khac_so_khong;
~~~

Cả hai biểu thức trả `TRUE`. Đây là **phép so sánh null-safe**, khác việc `COALESCE` thay `NULL` bằng một giá trị giả. Nếu cần xét hai cột có cùng giá trị hoặc cùng thiếu mà không muốn mất thông tin, có thể phù hợp hơn việc ép cả hai về một sentinel như `-1`.

## 12. Các lỗi dễ gặp và cách hiểu đúng

| Cách hiểu dễ sai | Vì sao sai | Cách dùng phù hợp |
| --- | --- | --- |
| “`CASE WHEN x = NULL` bắt được giá trị thiếu.” | So sánh `=` với `NULL` cho `UNKNOWN`. | Dùng `WHEN x IS NULL`. |
| “Simple `CASE x WHEN NULL` bắt được `NULL`.” | Simple CASE dựa trên đối chiếu thông thường. | Searched CASE với `IS NULL`. |
| “Thứ tự WHEN không quan trọng.” | Nhánh đúng đầu tiên được chọn, nhánh sau có thể bị che. | Đặt điều kiện ưu tiên/cụ thể trước. |
| “`NULLIF(x,0)` xóa hàng có x = 0.” | Nó chỉ trả `NULL` cho biểu thức, không xóa/lọc hàng. | Dùng `WHERE` nếu cần lọc, `NULLIF` nếu cần biến đổi. |
| “`COALESCE(0,99)` trả 99.” | `0` khác `NULL`. | Chỉ dùng `NULLIF(0,0)` khi 0 thật sự đại diện giá trị không dùng được. |
| “`COALESCE('', 'khac')` bỏ qua chuỗi rỗng.” | PostgreSQL phân biệt chuỗi rỗng và `NULL`. | `COALESCE(NULLIF(btrim(s),''),'khac')`. |
| “Thay mọi `NULL` bằng 0 giúp dữ liệu đúng hơn.” | Có thể đánh mất sự khác biệt giữa chưa biết và số 0 thực. | Xác định chính sách của từng cột. |
| “`SUM` không có dòng luôn bằng 0.” | `SUM` trên tập rỗng trả `NULL` trong PostgreSQL. | `COALESCE(SUM(...),0)` khi tổng rỗng được phép hiển thị 0. |
| “`COUNT(CASE ... ELSE 0 END)` chỉ đếm hàng khớp.” | COUNT đếm cả 0 vì khác `NULL`. | `COUNT(CASE WHEN ... THEN 1 END)` hoặc `SUM(CASE ... ELSE 0 END)`. |
| “`CASE`/COALESCE luôn chặn mọi lỗi ở nhánh không chọn.” | Có tối ưu hóa và đánh giá biểu thức ở các giai đoạn khác nhau. | Thiết kế biểu thức an toàn, không phụ thuộc tuyệt đối vào thứ tự vật lý. |
| “`COALESCE` luôn cùng kiểu ở mọi DBMS.” | Cách suy kiểu, collation và nullable metadata khác nhau. | Kiểm tra kiểu cụ thể, ép kiểu tường minh nếu cần. |
| “`NULLIF` và `COALESCE` thay thế được `NOT NULL`.” | Chúng chỉ biến đổi kết quả biểu thức khi đọc/ghi được yêu cầu. | Dùng ràng buộc để bảo vệ dữ liệu nguồn. |

## 13. Bài tập thực hành có lời giải

Các bài tập sau dùng bảng `don_hang_case` ở mục 2. Hãy dự đoán trước rồi đối chiếu lời giải. Khi câu hỏi yêu cầu hiển thị hoặc tính toán, cần phân biệt **giá trị thực tế** với **nhãn trình bày**.

### Bài 1: Simple CASE và NULL

~~~sql
SELECT
    id,
    CASE trang_thai
        WHEN 'MOI' THEN 'Đang xử lý'
        WHEN NULL THEN 'Thiếu'
        ELSE 'Khác'
    END AS hien_thi
FROM don_hang_case
WHERE id = 104;
~~~

**Câu hỏi:** Dòng 104 trả nhãn gì?

**Lời giải:** `'Khác'`, không phải `'Thiếu'`, vì `WHEN NULL` không khớp với giá trị `NULL` trong simple CASE. Sửa bằng:

~~~sql
SELECT
    id,
    CASE
        WHEN trang_thai IS NULL THEN 'Thiếu'
        WHEN trang_thai = 'MOI' THEN 'Đang xử lý'
        ELSE 'Khác'
    END AS hien_thi
FROM don_hang_case
WHERE id = 104;
~~~

### Bài 2: COALESCE có bỏ qua số 0?

~~~sql
SELECT
    COALESCE(0, 5) AS a,
    COALESCE(NULLIF(0, 0), 5) AS b;
~~~

**Lời giải:** `a = 0`, `b = 5`. Biểu thức đầu xem 0 là giá trị hợp lệ; biểu thức thứ hai chủ động đổi 0 thành `NULL` trước khi chọn giá trị dự phòng.

### Bài 3: Chuỗi chỉ gồm dấu cách

~~~sql
SELECT
    COALESCE(email, '(chưa có)') AS a,
    COALESCE(NULLIF(btrim(email), ''), '(chưa có)') AS b
FROM don_hang_case
WHERE id = 105;
~~~

**Lời giải:** `a` là chuỗi có **ba dấu cách**, không phải nhãn dự phòng; `b = '(chưa có)'` vì `btrim` tạo chuỗi rỗng và `NULLIF` đổi nó thành `NULL`.

### Bài 4: Tính giá trên đơn vị

Tính thành tiền bình quân của mỗi đơn theo `(so_luong * don_gia - giam_gia) / so_luong`, nhưng không được gặp lỗi khi `so_luong = 0`. Nếu `giam_gia IS NULL`, xem như không giảm giá. Viết biểu thức.

**Một lời giải:**

~~~sql
SELECT
    id,
    ROUND(
        (so_luong * don_gia - COALESCE(giam_gia, 0))
        / NULLIF(so_luong, 0),
        2
    ) AS gia_binh_quan
FROM don_hang_case
ORDER BY id;
~~~

Với ID 103 và 106 (`so_luong = 0`), kết quả là `NULL` thay vì chia cho 0. Với ID 104 (`so_luong = NULL`), kết quả cũng là `NULL`, nhưng **nguyên nhân khác nhau**; nếu ứng dụng phải hiển thị thông báo chính xác, thêm cột trạng thái bằng `CASE`.

### Bài 5: Đếm đơn đã thanh toán

Cho:

~~~sql
SELECT
    COUNT(CASE WHEN trang_thai = 'DA_THANH_TOAN' THEN 1 ELSE 0 END)
        AS dem_a,
    COUNT(CASE WHEN trang_thai = 'DA_THANH_TOAN' THEN 1 END)
        AS dem_b,
    SUM(CASE WHEN trang_thai = 'DA_THANH_TOAN' THEN 1 ELSE 0 END)
        AS dem_c
FROM don_hang_case;
~~~

**Lời giải:** `dem_a = 8`, `dem_b = 3`, `dem_c = 3`. Đối với `COUNT`, `0` vẫn là giá trị khác `NULL`; còn `SUM` thực sự cộng các giá trị 1/0.

### Bài 6: Giá trị dự phòng nhiều cấp

Giả sử bảng khách có ba cột `ten_uu_tien`, `ten_phap_ly`, `ma_khach`. Bạn cần hiển thị giá trị không rỗng đầu tiên sau khi bỏ khoảng trắng; nếu cả ba thiếu, hiển thị `'(không rõ)'`.

**Một lời giải PostgreSQL:**

~~~sql
SELECT
    COALESCE(
        NULLIF(btrim(ten_uu_tien), ''),
        NULLIF(btrim(ten_phap_ly), ''),
        NULLIF(btrim(ma_khach), ''),
        '(không rõ)'
    ) AS ten_hien_thi
FROM bang_khach_hang;
~~~

`bang_khach_hang` là tên bảng **giả định**, vì bài này minh họa biểu thức, không tạo bảng đó trong dữ liệu mẫu. Để chạy nguyên văn cần có bảng với ba cột tương ứng. Thứ tự các đối số là thứ tự ưu tiên nghiệp vụ; chuyển `'(không rõ)'` lên đầu sẽ khiến mọi hàng đều nhận nhãn này.

### Bài 7: Rẽ nhánh theo tình trạng số lượng

Yêu cầu trả về `'CHUA_NHAP'` khi `so_luong IS NULL`, `'HET_HANG'` khi bằng 0, còn lại là `'CON_HANG'`.

**Lời giải:**

~~~sql
SELECT
    id,
    CASE
        WHEN so_luong IS NULL THEN 'CHUA_NHAP'
        WHEN so_luong = 0 THEN 'HET_HANG'
        ELSE 'CON_HANG'
    END AS trang_thai_so_luong
FROM don_hang_case
ORDER BY id;
~~~

Đây là nhãn minh họa cho tình trạng số lượng; trong hệ thống bán hàng thật, “hết hàng” thường liên quan **tồn kho sản phẩm**, không trực tiếp suy ra từ số lượng trên một dòng đơn hàng. Khi vận dụng, phải chọn cột đúng với quy tắc nghiệp vụ.

### Bài 8: Sắp xếp trạng thái theo ưu tiên

Muốn trạng thái `MOI` hiển thị trước, `DA_THANH_TOAN` tiếp theo, `DA_HUY` sau cùng, trạng thái lạ/`NULL` ở cuối, rồi sắp theo ID. Viết `ORDER BY`.

**Lời giải:**

~~~sql
SELECT id, trang_thai
FROM don_hang_case
ORDER BY
    CASE
        WHEN trang_thai = 'MOI' THEN 1
        WHEN trang_thai = 'DA_THANH_TOAN' THEN 2
        WHEN trang_thai = 'DA_HUY' THEN 3
        ELSE 4
    END,
    id;
~~~

`CASE` tạo khóa ưu tiên tạm; không làm thay đổi giá trị trạng thái trong bảng.

### Bài 9: Không có dữ liệu để tính AVG

~~~sql
SELECT
    AVG(don_gia) AS gia_trung_binh,
    COALESCE(AVG(don_gia), 0) AS gia_trung_binh_hien_thi
FROM don_hang_case
WHERE trang_thai = 'KHONG_TON_TAI';
~~~

**Lời giải:** `gia_trung_binh` là `NULL`, còn cột dùng `COALESCE` hiển thị `0`. Nhưng lựa chọn hiển thị 0 có thể gây hiểu nhầm rằng trung bình của dữ liệu thực sự bằng 0; với báo cáo thống kê, có thể thích hợp hơn nếu hiển thị “không đủ dữ liệu”.

### Bài 10: Kết hợp cả ba biểu thức

Yêu cầu: từ `email`, bỏ khoảng trắng biên, chuyển rỗng thành `NULL`; nếu thiếu thì trả nhãn `'CAN_BO_SUNG'`, nếu có đuôi `@example.com` thì `'MIEN_MAU'`, các email còn lại thì `'MIEN_KHAC'`. Viết truy vấn bằng `CASE`, `NULLIF`, `COALESCE`.

**Một lời giải:**

~~~sql
WITH chuan_hoa AS (
    SELECT
        id,
        NULLIF(lower(btrim(email)), '') AS email_key
    FROM don_hang_case
)
SELECT
    id,
    CASE
        WHEN COALESCE(email_key, '') = '' THEN 'CAN_BO_SUNG'
        WHEN email_key LIKE '%@example.com' THEN 'MIEN_MAU'
        ELSE 'MIEN_KHAC'
    END AS nhom_email
FROM chuan_hoa
ORDER BY id;
~~~

`NULLIF` chuẩn hóa đầu vào, `COALESCE` giúp nhánh đầu kiểm tra dữ liệu thiếu theo chính sách ví dụ, `CASE` phân loại. Có thể viết nhánh đầu gọn hơn thành `WHEN email_key IS NULL`, vẫn đúng và thường dễ hiểu hơn; bài tập cố ý dùng cả ba biểu thức để minh họa cách kết hợp.

Điều kiện `LIKE '%@example.com'` là kiểm tra **hậu tố chuỗi** rất đơn giản; không tự chứng minh email hợp lệ hoặc thuộc về người dùng.

## 14. Gợi ý chọn biểu thức phù hợp

| Yêu cầu | Biểu thức thường dùng | Cần chú ý |
| --- | --- | --- |
| Phân nhánh theo nhiều điều kiện | `CASE WHEN ... THEN ... ELSE ... END` | Thứ tự nhánh, `UNKNOWN`, kiểu kết quả |
| Đối chiếu một giá trị với tập giá trị cụ thể | `CASE x WHEN ... THEN ... END` | Không dùng `WHEN NULL` để bắt `NULL` |
| Dùng một giá trị thay thế khi cột thiếu | `COALESCE(cot, gia_tri_phu)` | Không bỏ qua 0, FALSE, chuỗi rỗng |
| Ưu tiên nguồn A, rồi B, rồi C | `COALESCE(A, B, C)` | Thứ tự nguồn là quy tắc nghiệp vụ |
| Biến một sentinel thành NULL | `NULLIF(cot, sentinel)` | Sentinel có thực sự nghĩa là thiếu không |
| Coi chuỗi chỉ có dấu cách là thiếu | `NULLIF(btrim(cot), '')` | Phạm vi ký tự `btrim` loại bỏ |
| Hiển thị nhãn khi chuỗi thiếu | `COALESCE(NULLIF(btrim(cot), ''), nhan)` | Không lưu nhãn hiển thị như giá trị gốc |
| Tránh chia cho 0 | `tu_so / NULLIF(mau_so, 0)` | Kết quả `NULL` có thể phải hiển thị lý do |
| Đếm dòng thỏa điều kiện | `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` | `COUNT(... ELSE 0)` sẽ đếm cả 0 |
| Chỉ lấy tổng khác `NULL` để hiển thị 0 | `COALESCE(SUM(expr), 0)` | Không phải lúc nào `NULL` cũng nên thành 0 |
| Sắp xếp theo ưu tiên nghiệp vụ | `ORDER BY CASE WHEN ... THEN n ... END` | Thêm tiêu chí phụ để thứ tự ổn định |
| Giữ phân biệt dữ liệu lỗi và dữ liệu thiếu | `CASE` trả nhãn và biểu thức giá trị riêng | Tránh che lỗi bằng các giá trị giả |

**Kết luận:** `CASE` trả lời **“với điều kiện này, chọn kết quả nào?”**; `NULLIF` trả lời **“giá trị đặc biệt này có cần được xem là thiếu không?”**; `COALESCE` trả lời **“khi thiếu, nguồn dự phòng nào được ưu tiên?”**. Khi kết hợp cả ba trong SQL, hãy giữ rõ ranh giới giữa **dữ liệu thực, dữ liệu chưa biết, quy tắc tính toán và nhãn hiển thị**. Một biểu thức ngắn có thể ngăn lỗi chia cho 0 hoặc làm sạch chuỗi rỗng; nhưng chỉ thiết kế nghiệp vụ và ràng buộc dữ liệu phù hợp mới bảo đảm kết quả không vô tình che mất thông tin quan trọng.
