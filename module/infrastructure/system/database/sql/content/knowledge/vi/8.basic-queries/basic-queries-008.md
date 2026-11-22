# Kết hợp truy vấn với bảng dẫn xuất trong SQL

Trong nhiều bài toán truy vấn, một câu `SELECT` đơn giản không đủ để biểu diễn kết quả theo đúng thứ tự xử lý bạn muốn. Chẳng hạn, bạn cần **tính tổng tiền của từng đơn hàng trước**, sau đó chỉ lấy những đơn có tổng tiền lớn hơn một ngưỡng; hoặc cần **đếm số đơn theo khách hàng trước**, sau đó ghép kết quả đếm với danh sách khách hàng để vẫn hiển thị người chưa từng đặt hàng.

**Bảng dẫn xuất (derived table)** cho phép đặt một truy vấn `SELECT` trong mệnh đề `FROM` hoặc `JOIN`, rồi sử dụng kết quả của nó như một bảng tạm có tên trong phạm vi câu lệnh SQL hiện tại. Đây là kỹ thuật quan trọng để kết hợp các bước lọc, JOIN và tổng hợp thành một truy vấn dễ hiểu.

Bài học thuộc nhóm **Truy vấn cơ bản** của Database SQL và dùng **PostgreSQL** làm môi trường thực hành. Khái niệm bảng dẫn xuất áp dụng cho nhiều hệ quản trị quan hệ, nhưng cú pháp về bí danh, giới hạn dòng và truy vấn tương quan có thể khác ở MySQL, SQL Server, Oracle hoặc SQLite.

## 1. Bảng dẫn xuất là gì?

Truy vấn thông thường đọc dữ liệu từ bảng đã tồn tại:

~~~sql
SELECT id, ho_ten
FROM khach_hang;
~~~

Bảng dẫn xuất là kết quả của một `SELECT` khác được đặt trong phần `FROM`:

~~~sql
SELECT dt.id, dt.ho_ten
FROM (
    SELECT id, ho_ten
    FROM khach_hang
) AS dt;
~~~

Phần bên trong dấu ngoặc:

~~~sql
(
    SELECT id, ho_ten
    FROM khach_hang
) AS dt
~~~

đóng vai trò là một **nguồn dữ liệu dạng bảng** cho truy vấn bên ngoài. Tên `dt` là **bí danh (alias)** của bảng dẫn xuất, dùng để tham chiếu các cột trong kết quả của truy vấn bên trong.

Sơ đồ logic:

~~~text
Bảng gốc
   │
   ▼
SELECT bên trong: lọc / JOIN / tính cột / GROUP BY
   │
   ▼
Kết quả dạng bảng dẫn xuất, bí danh dt
   │
   ▼
SELECT bên ngoài: lọc tiếp / JOIN / sắp xếp / tính toán
   │
   ▼
Bảng kết quả cuối cùng
~~~

Điểm cần ghi nhớ:

- Bảng dẫn xuất **không nhất thiết được lưu vật lý thành một bảng mới**. Nó là kết quả logic của truy vấn con trong một câu lệnh; hệ quản trị có thể tối ưu hoặc gộp các bước thực thi.
- Bảng dẫn xuất tồn tại về **phạm vi tên** trong câu SQL đang chạy; bí danh `dt` không phải tên bảng để truy vấn ở một statement độc lập sau đó.
- Truy vấn bên trong quyết định **các cột và những hàng mà truy vấn ngoài nhìn thấy**. Các cột không có trong danh sách `SELECT` bên trong không thể được tham chiếu trực tiếp từ `dt` ở bên ngoài.
- Bảng dẫn xuất có thể đứng sau `FROM` hoặc là một nguồn dữ liệu được `JOIN` với bảng khác.

Đây là một dạng *subquery* (truy vấn con), nhưng **không phải mọi subquery đều là bảng dẫn xuất**. Subquery trong `WHERE EXISTS (...)` thường dùng kiểm tra sự tồn tại; subquery vô hướng trong `SELECT` dùng để lấy một giá trị; còn bảng dẫn xuất đặt ở vị trí **nguồn dữ liệu**.

## 2. Cú pháp cơ bản: SELECT từ một SELECT khác

Mẫu thường dùng:

~~~sql
SELECT dt.cot_a, dt.cot_b
FROM (
    SELECT
        b.cot_goc AS cot_a,
        b.cot_khac AS cot_b
    FROM bang_goc AS b
    WHERE dieu_kien_ben_trong
) AS dt
WHERE dieu_kien_ben_ngoai
ORDER BY dt.cot_a;
~~~

Các thành phần có vai trò riêng:

| Thành phần | Vai trò |
|---|---|
| `SELECT ... FROM bang_goc` bên trong | Tạo tập dòng và cột của bảng dẫn xuất |
| Dấu ngoặc `(...)` | Giới hạn truy vấn con ở vị trí nguồn dữ liệu |
| `AS dt` | Gán bí danh để tham chiếu kết quả |
| `dt.cot_a` | Truy cập một cột do truy vấn bên trong xuất ra |
| `WHERE` bên trong | Lọc những dòng đầu vào cho bước tiếp theo |
| `WHERE` bên ngoài | Lọc những hàng mà bảng dẫn xuất cung cấp |
| `JOIN` bên ngoài | Ghép kết quả đã được xử lý với bảng khác |
| `ORDER BY` ngoài cùng | Xác định thứ tự của kết quả cuối cùng |

Trong ví dụ cơ bản, dùng tên có bí danh như `dt.cot_a` giúp phân biệt cột thuộc nguồn nào. Khi bảng dẫn xuất xuất hiện cùng các bảng khác, bí danh càng cần thiết để tránh tên cột mơ hồ.

### 2.1. Vì sao cần hai mức SELECT?

Ví dụ, bạn muốn tính một cột `thanh_tien = so_luong * don_gia` và lọc các dòng có thành tiền từ 100.000 trở lên. Trong SQL thông thường, bí danh của cột vừa tạo trong `SELECT` thường **không được dùng trực tiếp trong `WHERE` cùng cấp**:

~~~sql
-- Không phù hợp với cú pháp PostgreSQL:
SELECT
    so_luong * don_gia AS thanh_tien
FROM chi_tiet_don_hang
WHERE thanh_tien >= 100000;
~~~

Một cách là lặp biểu thức:

~~~sql
SELECT so_luong * don_gia AS thanh_tien
FROM chi_tiet_don_hang
WHERE so_luong * don_gia >= 100000;
~~~

Nếu biểu thức dài và được dùng nhiều lần, bảng dẫn xuất giúp đặt tên một lần:

~~~sql
SELECT dt.thanh_tien
FROM (
    SELECT so_luong * don_gia AS thanh_tien
    FROM chi_tiet_don_hang
) AS dt
WHERE dt.thanh_tien >= 100000;
~~~

Hai ví dụ trên là **mẫu cú pháp**; các phần sau cung cấp bộ dữ liệu có tên bảng riêng để chạy được từ đầu. Việc sử dụng bảng dẫn xuất nhằm thể hiện rõ ranh giới xử lý và phạm vi cột. Cơ sở dữ liệu có thể tối ưu tính toán mà không bắt buộc tính ra rồi lưu toàn bộ bảng trung gian.

## 3. Chuẩn bị dữ liệu thực hành

Dùng một hệ thống bán hàng đơn giản gồm khách hàng, đơn hàng, sản phẩm và chi tiết đơn hàng.

Chạy toàn bộ khối SQL sau trên **PostgreSQL thử nghiệm**, trong **cùng một phiên kết nối**. Tên bảng bắt đầu bằng `dt_` để phân biệt với các bảng nghiệp vụ khác. Các bảng được khai báo `TEMP` nên thường chỉ tồn tại trong phiên hiện tại; nếu phần mềm SQL tự tạo kết nối mới, bạn có thể không nhìn thấy bảng vừa tạo.

~~~sql
CREATE TEMP TABLE dt_khach_hang (
    id INTEGER PRIMARY KEY,
    ho_ten VARCHAR(100) NOT NULL,
    khu_vuc VARCHAR(20) NOT NULL
);

CREATE TEMP TABLE dt_don_hang (
    id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL
        REFERENCES dt_khach_hang(id),
    ngay_dat DATE NOT NULL,
    trang_thai VARCHAR(20) NOT NULL
        CHECK (trang_thai IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TEMP TABLE dt_san_pham (
    id INTEGER PRIMARY KEY,
    ten VARCHAR(100) NOT NULL
);

CREATE TEMP TABLE dt_chi_tiet_don (
    don_hang_id INTEGER NOT NULL REFERENCES dt_don_hang(id),
    san_pham_id INTEGER NOT NULL REFERENCES dt_san_pham(id),
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12,2) NOT NULL CHECK (don_gia >= 0),
    PRIMARY KEY (don_hang_id, san_pham_id)
);

INSERT INTO dt_khach_hang (id, ho_ten, khu_vuc) VALUES
    (1, 'An',   'Bắc'),
    (2, 'Bình', 'Nam'),
    (3, 'Chi',  'Bắc'),
    (4, 'Dũng', 'Trung');

INSERT INTO dt_don_hang
    (id, khach_hang_id, ngay_dat, trang_thai)
VALUES
    (101, 1, DATE '2026-06-01', 'PAID'),
    (102, 1, DATE '2026-06-03', 'NEW'),
    (103, 2, DATE '2026-06-04', 'PAID'),
    (104, 2, DATE '2026-06-05', 'CANCELLED'),
    (105, 4, DATE '2026-06-06', 'PAID');

INSERT INTO dt_san_pham (id, ten) VALUES
    (10, 'Sách SQL'),
    (20, 'Sổ tay'),
    (30, 'Bút');

INSERT INTO dt_chi_tiet_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
VALUES
    (101, 10, 2, 120000),
    (101, 20, 1,  30000),
    (102, 20, 3,  30000),
    (103, 10, 1, 120000),
    (103, 30, 2,  15000);
~~~

### 3.1. Quan hệ giữa các bảng

~~~mermaid
erDiagram
    DT_KHACH_HANG ||--o{ DT_DON_HANG : dat
    DT_DON_HANG ||--o{ DT_CHI_TIET_DON : chua
    DT_SAN_PHAM ||--o{ DT_CHI_TIET_DON : xuat_hien
~~~

Một khách hàng có thể đặt nhiều đơn; mỗi đơn có thể có nhiều dòng sản phẩm. Bảng chi tiết chứa `so_luong` và `don_gia` tại thời điểm ghi nhận để tính giá trị dòng.

### 3.2. Các tổng tiền mẫu để đối chiếu

Nếu tính tổng tiền mỗi đơn dựa trên các dòng chi tiết:

| Mã đơn | Khách hàng | Trạng thái | Các dòng chi tiết | Tổng tiền |
|---:|---|---|---|---:|
| 101 | An | PAID | 2 × 120.000 + 1 × 30.000 | 270.000 |
| 102 | An | NEW | 3 × 30.000 | 90.000 |
| 103 | Bình | PAID | 1 × 120.000 + 2 × 15.000 | 150.000 |
| 104 | Bình | CANCELLED | Chưa có chi tiết | 0 |
| 105 | Dũng | PAID | Chưa có chi tiết | 0 |

Khách hàng **Chi chưa có đơn hàng nào**. Đơn 104 và 105 vẫn tồn tại nhưng chưa có dòng chi tiết. Những trường hợp này giúp thấy rõ khác biệt giữa `INNER JOIN`, `LEFT JOIN` và cách xử lý giá trị `NULL`.

## 4. Ví dụ đầu tiên: tạo bảng dẫn xuất từ cột tính toán

Yêu cầu: **Liệt kê những dòng sản phẩm có thành tiền từ 100.000 trở lên**.

### 4.1. Truy vấn con tạo dữ liệu

~~~sql
SELECT
    ct.don_hang_id,
    ct.san_pham_id,
    ct.so_luong,
    ct.don_gia,
    ct.so_luong * ct.don_gia AS thanh_tien
FROM dt_chi_tiet_don AS ct;
~~~

Truy vấn này tạo 5 dòng, trong đó cột `thanh_tien` là biểu thức tính từ hai cột gốc.

### 4.2. Đặt truy vấn vào FROM

~~~sql
SELECT
    dong.don_hang_id,
    dong.san_pham_id,
    dong.thanh_tien
FROM (
    SELECT
        ct.don_hang_id,
        ct.san_pham_id,
        ct.so_luong * ct.don_gia AS thanh_tien
    FROM dt_chi_tiet_don AS ct
) AS dong
WHERE dong.thanh_tien >= 100000
ORDER BY dong.don_hang_id, dong.san_pham_id;
~~~

Kết quả:

| don_hang_id | san_pham_id | thanh_tien |
|---:|---:|---:|
| 101 | 10 | 240000 |
| 103 | 10 | 120000 |

Có thể đọc theo hai bước logic:

1. `dong` là bảng dẫn xuất với ba cột `don_hang_id`, `san_pham_id` và `thanh_tien`.
2. `SELECT` bên ngoài lọc những dòng có `dong.thanh_tien >= 100000` rồi sắp xếp.

**Phạm vi cột:** nếu truy vấn bên trong không trả ra `ct.so_luong`, truy vấn ngoài không thể viết `dong.so_luong`. Muốn sử dụng số lượng ở ngoài, hãy thêm cột đó vào `SELECT` bên trong.

### 4.3. JOIN sản phẩm với bảng dẫn xuất

Nếu cần cả tên sản phẩm:

~~~sql
SELECT
    dong.don_hang_id,
    sp.ten AS ten_san_pham,
    dong.thanh_tien
FROM (
    SELECT
        don_hang_id,
        san_pham_id,
        so_luong * don_gia AS thanh_tien
    FROM dt_chi_tiet_don
) AS dong
JOIN dt_san_pham AS sp
    ON sp.id = dong.san_pham_id
WHERE dong.thanh_tien >= 100000
ORDER BY dong.don_hang_id;
~~~

Kết quả là hai dòng sản phẩm `Sách SQL`, lần lượt thuộc đơn 101 và 103. Đây là ví dụ trực tiếp của **kết hợp truy vấn bên trong với JOIN bên ngoài**.

## 5. Tổng hợp trong bảng dẫn xuất rồi lọc kết quả

Yêu cầu: **Tìm các đơn có tổng tiền từ 100.000 trở lên**. Tổng tiền của mỗi đơn chỉ có thể biết sau khi tổng hợp các dòng chi tiết.

### 5.1. Tổng hợp theo đơn

~~~sql
SELECT
    ct.don_hang_id,
    SUM(ct.so_luong * ct.don_gia) AS tong_tien
FROM dt_chi_tiet_don AS ct
GROUP BY ct.don_hang_id
ORDER BY ct.don_hang_id;
~~~

Kết quả có ba dòng:

| don_hang_id | tong_tien |
|---:|---:|
| 101 | 270000 |
| 102 | 90000 |
| 103 | 150000 |

Đơn 104 và 105 không xuất hiện vì bảng chi tiết không có dòng tương ứng.

### 5.2. Lọc tổng tiền ở truy vấn ngoài

~~~sql
SELECT
    tong.don_hang_id,
    tong.tong_tien
FROM (
    SELECT
        ct.don_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong_tien
    FROM dt_chi_tiet_don AS ct
    GROUP BY ct.don_hang_id
) AS tong
WHERE tong.tong_tien >= 100000
ORDER BY tong.tong_tien DESC, tong.don_hang_id;
~~~

Kết quả:

| don_hang_id | tong_tien |
|---:|---:|
| 101 | 270000 |
| 103 | 150000 |

Truy vấn trong tạo **một hàng cho mỗi đơn có chi tiết**, còn truy vấn ngoài chọn các nhóm có tổng tiền đủ lớn.

### 5.3. Có thể dùng HAVING thay thế không?

Có. Nếu chỉ cần lọc một điều kiện tổng hợp đơn giản, không JOIN thêm dữ liệu và không cần tái sử dụng cột tổng tiền, `HAVING` có thể ngắn hơn:

~~~sql
SELECT
    ct.don_hang_id,
    SUM(ct.so_luong * ct.don_gia) AS tong_tien
FROM dt_chi_tiet_don AS ct
GROUP BY ct.don_hang_id
HAVING SUM(ct.so_luong * ct.don_gia) >= 100000
ORDER BY tong_tien DESC, ct.don_hang_id;
~~~

Hai truy vấn ở ví dụ này trả cùng dữ liệu. Bảng dẫn xuất hữu ích khi muốn **biến một kết quả tổng hợp thành nguồn dữ liệu để JOIN hoặc xử lý tiếp**. Không phải mọi điều kiện có `SUM` đều bắt buộc viết bảng dẫn xuất.

### 5.4. WHERE, GROUP BY, HAVING và WHERE ngoài khác nhau thế nào?

| Vị trí điều kiện | Thời điểm logic | Ví dụ |
|---|---|---|
| `WHERE` trong truy vấn con | Lọc dòng nguồn trước khi tổng hợp | Chỉ lấy các đơn PAID |
| `GROUP BY` trong truy vấn con | Tạo nhóm từ các dòng còn lại | Một nhóm theo `don_hang_id` |
| `HAVING` trong truy vấn con | Lọc các nhóm đã tổng hợp | Nhóm có `SUM(...) >= 100000` |
| `WHERE` của truy vấn ngoài | Lọc hàng do bảng dẫn xuất cung cấp | `WHERE tong.tong_tien >= 100000` |

Về mặt thực thi, optimizer có thể di chuyển hoặc kết hợp các phép xử lý khi vẫn bảo toàn kết quả. Bảng trên mô tả **ý nghĩa logic** của SQL, không phải cam kết máy chủ luôn tính vật lý từng bước đúng thứ tự đó.

## 6. Giữ cả những đơn không có chi tiết

Nếu muốn mỗi đơn vẫn có **một hàng tổng tiền**, kể cả đơn chưa có sản phẩm, hãy lấy đơn hàng làm bảng bên trái của `LEFT JOIN`:

~~~sql
SELECT
    dh.id AS ma_don,
    COALESCE(SUM(ct.so_luong * ct.don_gia), 0) AS tong_tien
FROM dt_don_hang AS dh
LEFT JOIN dt_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
GROUP BY dh.id
ORDER BY dh.id;
~~~

Kết quả:

| ma_don | tong_tien |
|---:|---:|
| 101 | 270000 |
| 102 | 90000 |
| 103 | 150000 |
| 104 | 0 |
| 105 | 0 |

Với đơn 104/105, phía chi tiết của LEFT JOIN là NULL; biểu thức nhân các cột chi tiết cũng cho NULL. `SUM` bỏ qua giá trị NULL và với một nhóm không có đầu vào số hợp lệ sẽ trả NULL; `COALESCE(..., 0)` thay kết quả đó bằng số 0.

### 6.1. Đóng gói kết quả này thành bảng dẫn xuất

~~~sql
SELECT
    tong.ma_don,
    tong.tong_tien
FROM (
    SELECT
        dh.id AS ma_don,
        COALESCE(SUM(ct.so_luong * ct.don_gia), 0) AS tong_tien
    FROM dt_don_hang AS dh
    LEFT JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    GROUP BY dh.id
) AS tong
WHERE tong.tong_tien = 0
ORDER BY tong.ma_don;
~~~

Kết quả là đơn **104** và **105**. Đây là những đơn đang có tổng giá trị chi tiết bằng 0 trong dữ liệu mẫu; điều kiện này không tự suy ra trạng thái nghiệp vụ của đơn.

### 6.2. NULL và 0 khác nhau

Nếu bỏ `COALESCE`, đơn chưa có chi tiết có `SUM(...) = NULL`. Khi đó `WHERE tong_tien = 0` sẽ không chọn những dòng này, vì phép so sánh `NULL = 0` cho kết quả UNKNOWN.

Bạn cần quyết định rõ ý nghĩa:

- Muốn tổng tiền thiếu được trình bày là 0: dùng `COALESCE(SUM(...), 0)`.
- Muốn phân biệt **chưa có dòng chi tiết** với một tổng thực sự bằng 0: giữ NULL hoặc thêm một cột đếm `COUNT(ct.san_pham_id)`.

Ví dụ:

~~~sql
SELECT
    dh.id,
    COUNT(ct.san_pham_id) AS so_dong_chi_tiet,
    SUM(ct.so_luong * ct.don_gia) AS tong_tien_nullable
FROM dt_don_hang AS dh
LEFT JOIN dt_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
GROUP BY dh.id
ORDER BY dh.id;
~~~

Với đơn 104 và 105, `so_dong_chi_tiet = 0`, còn `tong_tien_nullable = NULL`. Đây là hai thông tin bổ sung nhau.

## 7. Kết hợp bảng dẫn xuất với bảng khách hàng

Một cách dùng phổ biến nhất là **tổng hợp trước, ghép với bảng danh mục sau**.

Yêu cầu: **Hiển thị mọi khách hàng cùng tổng tiền các đơn PAID có dòng chi tiết**. Khách hàng không có tiền thanh toán phải vẫn xuất hiện với giá trị 0.

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    COALESCE(dt.tong_da_thanh_toan, 0) AS tong_da_thanh_toan
FROM dt_khach_hang AS kh
LEFT JOIN (
    SELECT
        dh.khach_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong_da_thanh_toan
    FROM dt_don_hang AS dh
    JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    WHERE dh.trang_thai = 'PAID'
    GROUP BY dh.khach_hang_id
) AS dt
    ON dt.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

Kết quả:

| id | ho_ten | tong_da_thanh_toan |
|---:|---|---:|
| 1 | An | 270000 |
| 2 | Bình | 150000 |
| 3 | Chi | 0 |
| 4 | Dũng | 0 |

Các bước:

1. **Bên trong:** chỉ chọn các đơn `PAID`, JOIN với chi tiết, tính tổng theo `khach_hang_id`. Bảng dẫn xuất trả hai dòng: An 270.000, Bình 150.000.
2. **Bên ngoài:** bắt đầu từ **toàn bộ khách hàng**. `LEFT JOIN` ghép tổng tiền nếu có kết quả phù hợp.
3. **Trình bày:** `COALESCE` đổi NULL của khách hàng không khớp thành 0.

Dũng có đơn PAID (105), nhưng đơn đó chưa có dòng chi tiết; `JOIN` bên trong không tạo dòng doanh thu cho Dũng. Truy vấn ngoài vẫn giữ Dũng và hiển thị 0.

**Điểm then chốt:** bảng dẫn xuất ở đây có tối đa **một hàng cho mỗi khách hàng**, vì `GROUP BY dh.khach_hang_id`. Nhờ đó, ghép nó vào bảng khách hàng không làm nhân số dòng khách hàng.

### 7.1. Vì sao không dùng INNER JOIN ở ngoài?

Nếu đổi `LEFT JOIN` ngoài thành `JOIN`, chỉ còn An và Bình vì Chi/Dũng không có dòng tương ứng trong bảng dẫn xuất. Muốn giữ khách hàng chưa phát sinh dữ liệu, phải chọn đúng bảng làm phía trái và loại JOIN phù hợp.

### 7.2. Đặt điều kiện trạng thái bên trong có tác dụng gì?

Trong bảng dẫn xuất:

~~~sql
WHERE dh.trang_thai = 'PAID'
~~~

bảo đảm chỉ đơn PAID tham gia tính tổng. Đơn 102 của An đang NEW, có 90.000 tiền chi tiết, **không được cộng vào tổng đã thanh toán**. Đơn 104 bị hủy cũng không được tính.

Nếu bỏ điều kiện trạng thái, tổng giá trị các dòng chi tiết của An sẽ là 360.000, khác với tổng 270.000 của các đơn PAID.

### 7.3. Lọc khách hàng theo tổng tiền đã thanh toán

Yêu cầu: chỉ lấy khách hàng đã có tổng tiền PAID ít nhất 200.000:

~~~sql
SELECT
    kh.ho_ten,
    COALESCE(dt.tong_da_thanh_toan, 0) AS tong_da_thanh_toan
FROM dt_khach_hang AS kh
LEFT JOIN (
    SELECT
        dh.khach_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong_da_thanh_toan
    FROM dt_don_hang AS dh
    JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    WHERE dh.trang_thai = 'PAID'
    GROUP BY dh.khach_hang_id
) AS dt
    ON dt.khach_hang_id = kh.id
WHERE COALESCE(dt.tong_da_thanh_toan, 0) >= 200000
ORDER BY kh.id;
~~~

Kết quả chỉ có **An — 270.000**. Khi lọc ở truy vấn ngoài, phải nhớ đây là điều kiện trên **giá trị đã tổng hợp**, không phải trên từng dòng chi tiết.

## 8. Tính từng đơn trước rồi ghép nhiều bảng

Yêu cầu: **Xem danh sách đơn, khách hàng, trạng thái và tổng tiền của mỗi đơn**, kể cả đơn chưa có chi tiết.

Thay vì JOIN trực tiếp tất cả các dòng chi tiết ở câu ngoài, hãy tổng hợp chúng thành **một dòng mỗi đơn**:

~~~sql
SELECT
    dh.id AS ma_don,
    kh.ho_ten,
    dh.trang_thai,
    COALESCE(tong.tong_tien, 0) AS tong_tien
FROM dt_don_hang AS dh
JOIN dt_khach_hang AS kh
    ON kh.id = dh.khach_hang_id
LEFT JOIN (
    SELECT
        don_hang_id,
        SUM(so_luong * don_gia) AS tong_tien
    FROM dt_chi_tiet_don
    GROUP BY don_hang_id
) AS tong
    ON tong.don_hang_id = dh.id
ORDER BY dh.id;
~~~

Kết quả:

| ma_don | ho_ten | trang_thai | tong_tien |
|---:|---|---|---:|
| 101 | An | PAID | 270000 |
| 102 | An | NEW | 90000 |
| 103 | Bình | PAID | 150000 |
| 104 | Bình | CANCELLED | 0 |
| 105 | Dũng | PAID | 0 |

Phần trong bảng dẫn xuất trả đúng **một hàng theo `don_hang_id`**; phần ngoài thêm thông tin khách hàng và trạng thái đơn. Cách tách này giúp người đọc thấy rõ mức chi tiết của kết quả cuối: **một hàng cho mỗi đơn**.

### 8.1. Vì sao cần xác định “một hàng đại diện cho gì”?

Nếu JOIN trực tiếp `dt_don_hang` với `dt_chi_tiet_don`, đơn 101 xuất hiện **hai hàng** vì có hai sản phẩm. Điều đó đúng nếu mục tiêu là **một hàng cho mỗi dòng sản phẩm trong đơn**, nhưng sai nếu mục tiêu là **một hàng cho mỗi đơn hàng**.

Bảng dẫn xuất có `GROUP BY don_hang_id` thay đổi mức chi tiết từ “dòng sản phẩm” thành “đơn hàng”, giúp JOIN với `dt_don_hang` mà không làm lặp mã đơn.

## 9. Ghép nhiều bảng dẫn xuất để tránh nhân số dòng

Một khách hàng có nhiều đơn, và mỗi đơn lại có nhiều chi tiết. Khi JOIN qua chuỗi 1:N, một đơn có thể xuất hiện nhiều lần. Nếu đếm trực tiếp:

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    COUNT(dh.id) AS so_dong_sau_join
FROM dt_khach_hang AS kh
LEFT JOIN dt_don_hang AS dh
    ON dh.khach_hang_id = kh.id
LEFT JOIN dt_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

Số đếm của An sẽ là **3**, vì đơn 101 có 2 dòng chi tiết và đơn 102 có 1 dòng. Nhưng số **đơn hàng** thật của An chỉ là **2**. `COUNT(dh.id)` đang đếm mã đơn bị lặp theo JOIN.

Một cách giải quyết khi chỉ cần đếm đơn là `COUNT(DISTINCT dh.id)`. Tuy nhiên, nếu truy vấn có **nhiều nhánh 1:N độc lập**, JOIN trực tiếp cũng có thể nhân các khoản tổng. Bảng dẫn xuất giúp tính **mỗi chỉ số ở đúng mức chi tiết trước**.

### 9.1. Tính số đơn và tổng tiền PAID ở hai bảng dẫn xuất

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    COALESCE(so_don.so_don_hang, 0) AS so_don_hang,
    COALESCE(doanh_thu.tong_paid, 0) AS tong_paid
FROM dt_khach_hang AS kh
LEFT JOIN (
    SELECT
        khach_hang_id,
        COUNT(*) AS so_don_hang
    FROM dt_don_hang
    GROUP BY khach_hang_id
) AS so_don
    ON so_don.khach_hang_id = kh.id
LEFT JOIN (
    SELECT
        dh.khach_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong_paid
    FROM dt_don_hang AS dh
    JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    WHERE dh.trang_thai = 'PAID'
    GROUP BY dh.khach_hang_id
) AS doanh_thu
    ON doanh_thu.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

Kết quả:

| id | ho_ten | so_don_hang | tong_paid |
|---:|---|---:|---:|
| 1 | An | 2 | 270000 |
| 2 | Bình | 2 | 150000 |
| 3 | Chi | 0 | 0 |
| 4 | Dũng | 1 | 0 |

Bảng dẫn xuất `so_don` có một dòng cho mỗi khách hàng có đơn; bảng `doanh_thu` có một dòng cho mỗi khách hàng có tổng giá trị chi tiết từ các đơn PAID. Do đều được GROUP BY theo `khach_hang_id`, hai nguồn kết quả không làm số dòng khách hàng nhân lên.

### 9.2. Quy tắc một hàng trên mỗi khóa ghép

Một mẹo tư duy rất hữu ích:

> Trước khi JOIN một bảng dẫn xuất vào bảng khách hàng qua `khach_hang_id`, hãy hỏi: “Bảng dẫn xuất này **có tối đa một hàng trên mỗi khach_hang_id không?**”

Nếu có, JOIN sẽ không nhân bản khách hàng do riêng nguồn đó. Nếu không, nhiều dòng đầu ra có thể là hành vi đúng hoặc một lỗi thiết kế truy vấn, tùy mục tiêu.

**Không phải cứ thấy dữ liệu lặp là thêm `DISTINCT`.** `DISTINCT` có thể che dấu nguyên nhân JOIN và loại bỏ những dòng hợp lệ khác nhau trong nghiệp vụ. Hãy làm rõ mức chi tiết đầu ra trước.

## 10. Lọc trước hay lọc sau bảng dẫn xuất?

Điều kiện đặt ở truy vấn trong và ngoài có thể dẫn đến các ý nghĩa khác nhau.

### 10.1. Lọc dòng trước khi tổng hợp

Yêu cầu: **Tổng tiền của riêng các đơn PAID theo khách hàng**.

~~~sql
SELECT
    dt.khach_hang_id,
    dt.tong_paid
FROM (
    SELECT
        dh.khach_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong_paid
    FROM dt_don_hang AS dh
    JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    WHERE dh.trang_thai = 'PAID'
    GROUP BY dh.khach_hang_id
) AS dt
ORDER BY dt.khach_hang_id;
~~~

Điều kiện `trang_thai = 'PAID'` lọc **các đơn đầu vào** trước khi cộng.

### 10.2. Lọc sau khi tổng hợp

Yêu cầu: **Khách hàng có tổng tiền của mọi đơn ít nhất 300.000**:

~~~sql
SELECT
    dt.khach_hang_id,
    dt.tong_tat_ca
FROM (
    SELECT
        dh.khach_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong_tat_ca
    FROM dt_don_hang AS dh
    JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    GROUP BY dh.khach_hang_id
) AS dt
WHERE dt.tong_tat_ca >= 300000;
~~~

Kết quả: khách hàng An có **360.000** vì bao gồm đơn 101 PAID và đơn 102 NEW. Điều kiện ở truy vấn ngoài không loại bỏ đơn NEW trước khi tính tổng.

### 10.3. Đừng nhầm điều kiện dòng với điều kiện nhóm

Sai về yêu cầu “tổng từng đơn từ 100.000 trở lên”:

~~~sql
-- Chỉ giữ DÒNG chi tiết >= 100000 trước khi SUM.
SELECT
    don_hang_id,
    SUM(so_luong * don_gia) AS tong_tien
FROM dt_chi_tiet_don
WHERE so_luong * don_gia >= 100000
GROUP BY don_hang_id;
~~~

Với dữ liệu mẫu, tổng đơn 101 trong kết quả này sẽ là **240.000**, vì dòng Sổ tay 30.000 bị loại trước khi tổng hợp. Trong khi tổng thực của đơn 101 là **270.000**.

Nếu ý định là “tính đủ tổng đơn rồi xét ngưỡng”, cần `HAVING SUM(...) >= 100000` hoặc bảng dẫn xuất tổng hợp trước và `WHERE` bên ngoài.

## 11. LEFT JOIN bảng dẫn xuất và điều kiện lọc

Bảng dẫn xuất thường được LEFT JOIN để giữ các đối tượng chưa có dữ liệu liên quan. Tuy nhiên, điều kiện đặt ở `WHERE` ngoài có thể làm mất những hàng vốn được giữ bởi LEFT JOIN.

### 11.1. Điều kiện trong ON giúp giữ khách hàng

Giả sử bạn chỉ muốn hiển thị tổng PAID **nếu tổng đó lớn hơn 200.000**, nhưng vẫn giữ mọi khách hàng:

~~~sql
SELECT
    kh.ho_ten,
    t.tong_paid
FROM dt_khach_hang AS kh
LEFT JOIN (
    SELECT
        dh.khach_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong_paid
    FROM dt_don_hang AS dh
    JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    WHERE dh.trang_thai = 'PAID'
    GROUP BY dh.khach_hang_id
) AS t
    ON t.khach_hang_id = kh.id
   AND t.tong_paid > 200000
ORDER BY kh.id;
~~~

Kết quả: An có 270.000; Bình, Chi và Dũng vẫn có dòng nhưng `tong_paid` là NULL. Điều kiện trong `ON` quyết định **dòng từ bảng dẫn xuất nào được ghép**, không loại hàng bên trái.

### 11.2. Đặt điều kiện ở WHERE sẽ lọc cả khách hàng

~~~sql
SELECT kh.ho_ten, t.tong_paid
FROM dt_khach_hang AS kh
LEFT JOIN (
    SELECT
        dh.khach_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong_paid
    FROM dt_don_hang AS dh
    JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    WHERE dh.trang_thai = 'PAID'
    GROUP BY dh.khach_hang_id
) AS t
    ON t.khach_hang_id = kh.id
WHERE t.tong_paid > 200000;
~~~

Kết quả chỉ còn **An**. Với người không có bản ghi khớp, `t.tong_paid` là NULL, nên `NULL > 200000` không phải TRUE và hàng bị loại.

Cả hai câu đều có thể đúng nếu phù hợp câu hỏi. Sự khác nhau nằm ở yêu cầu **giữ toàn bộ khách hàng** hay **chỉ lấy khách hàng thỏa điều kiện**.

## 12. Bảng dẫn xuất với DISTINCT và UNION

Không phải mọi bảng dẫn xuất đều phải chứa `GROUP BY`. Nó có thể lấy nguồn từ một kết quả đã loại trùng hoặc hợp nhất nhiều tập dữ liệu.

### 12.1. DISTINCT để tạo tập giá trị riêng biệt

~~~sql
SELECT khu.khu_vuc
FROM (
    SELECT DISTINCT khu_vuc
    FROM dt_khach_hang
) AS khu
ORDER BY khu.khu_vuc;
~~~

Kết quả có các khu vực **Bắc**, **Nam** và **Trung** (theo thứ tự sắp xếp thực tế của collation đang dùng). Bảng dẫn xuất chỉ có một cột `khu_vuc` và một dòng cho mỗi giá trị riêng biệt.

Trong trường hợp đơn giản này, `SELECT DISTINCT khu_vuc FROM dt_khach_hang ORDER BY khu_vuc` là đủ. Bảng dẫn xuất trở nên có ích khi tập khu vực riêng biệt cần **JOIN**, đếm hoặc xử lý thêm ở truy vấn ngoài.

### 12.2. UNION ALL trong bảng dẫn xuất

Giả sử muốn có một tập hoạt động giả lập gồm đơn hàng mới và đơn đã thanh toán, rồi đếm tổng số dòng theo loại:

~~~sql
SELECT
    hoat_dong.loai,
    COUNT(*) AS so_don
FROM (
    SELECT id, 'NEW' AS loai
    FROM dt_don_hang
    WHERE trang_thai = 'NEW'

    UNION ALL

    SELECT id, 'PAID' AS loai
    FROM dt_don_hang
    WHERE trang_thai = 'PAID'
) AS hoat_dong
GROUP BY hoat_dong.loai
ORDER BY hoat_dong.loai;
~~~

Kết quả:

| loai | so_don |
|---|---:|
| NEW | 1 |
| PAID | 3 |

`UNION ALL` nối các tập dòng, **giữ các dòng trùng nếu có**; `UNION` sẽ loại trùng theo toàn bộ cột được chọn. Số cột và kiểu dữ liệu tương ứng giữa các nhánh phải tương thích. Ở bài toán thực tế, kiểu bảng dẫn xuất này hữu ích khi hợp nhất nhiều nguồn sự kiện cùng cấu trúc, sau đó thống kê chung.

## 13. Dùng bảng dẫn xuất để lấy Top N

Một trường hợp phổ biến là tính giá trị trước, sắp xếp và giới hạn kết quả sau.

Yêu cầu: **Hai đơn có tổng tiền cao nhất**, tính cả đơn chưa có chi tiết.

~~~sql
SELECT
    tong.ma_don,
    tong.tong_tien
FROM (
    SELECT
        dh.id AS ma_don,
        COALESCE(SUM(ct.so_luong * ct.don_gia), 0) AS tong_tien
    FROM dt_don_hang AS dh
    LEFT JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    GROUP BY dh.id
) AS tong
ORDER BY tong.tong_tien DESC, tong.ma_don
LIMIT 2;
~~~

Kết quả:

| ma_don | tong_tien |
|---:|---:|
| 101 | 270000 |
| 103 | 150000 |

Đây là tổng hợp trong bảng dẫn xuất, còn `ORDER BY ... LIMIT` ở truy vấn ngoài chọn hai dòng cuối cùng. Phần `tong.ma_don` được thêm làm tiêu chí sắp xếp thứ hai để kết quả có thứ tự ổn định khi tổng tiền trùng nhau.

### 13.1. LIMIT bên trong thay đổi dữ liệu đầu vào

Hai mẫu dưới đây có **ý nghĩa khác nhau**:

~~~sql
-- Mẫu A: tổng hợp tất cả đơn trước, rồi chọn Top 2.
SELECT *
FROM (
    SELECT don_hang_id, SUM(so_luong * don_gia) AS tong_tien
    FROM dt_chi_tiet_don
    GROUP BY don_hang_id
) AS t
ORDER BY tong_tien DESC, don_hang_id
LIMIT 2;
~~~

~~~sql
-- Mẫu B: chọn 2 DÒNG CHI TIẾT trước, rồi mới tổng hợp.
SELECT
    t.don_hang_id,
    SUM(t.so_luong * t.don_gia) AS tong_tien
FROM (
    SELECT don_hang_id, so_luong, don_gia
    FROM dt_chi_tiet_don
    ORDER BY so_luong * don_gia DESC, don_hang_id
    LIMIT 2
) AS t
GROUP BY t.don_hang_id;
~~~

Mẫu A trả Top 2 **đơn theo tổng tiền**. Mẫu B chỉ cộng **hai dòng chi tiết có thành tiền cao nhất**, có thể bỏ qua các dòng khác của cùng đơn. Phải biết `LIMIT` giới hạn tập nào: tập dòng chi tiết hay tập đơn đã tổng hợp.

### 13.2. ORDER BY bên trong không bảo đảm thứ tự ngoài cùng

Nếu truy vấn con có `ORDER BY` nhưng truy vấn ngoài không có, **không nên suy ra bảng kết quả cuối luôn có thứ tự mong muốn**. Thứ tự của kết quả SQL chỉ được bảo đảm theo `ORDER BY` của truy vấn ngoài cùng phù hợp.

`ORDER BY` trong truy vấn con có thể mang ý nghĩa khi đi cùng `LIMIT`/`FETCH` để **chọn những hàng nào** vào bảng dẫn xuất. Tuy nhiên, nếu muốn **trình bày kết quả cuối theo thứ tự**, vẫn cần `ORDER BY` bên ngoài.

Một số hệ quản trị, ví dụ SQL Server, còn giới hạn dùng `ORDER BY` trong derived table nếu không đi cùng `TOP`, `OFFSET` hoặc cấu trúc được hỗ trợ.

## 14. Nhiều tầng bảng dẫn xuất

Có thể lồng một bảng dẫn xuất vào một bảng dẫn xuất khác, ví dụ:

1. Tính tổng tiền từng đơn.
2. Tính trung bình tổng tiền trên các đơn của mỗi khách hàng.
3. Lọc khách hàng có giá trị trung bình từ 150.000 trở lên.

~~~sql
SELECT
    trung_binh.khach_hang_id,
    trung_binh.avg_tong_don
FROM (
    SELECT
        don.khach_hang_id,
        AVG(don.tong_tien) AS avg_tong_don
    FROM (
        SELECT
            dh.id AS ma_don,
            dh.khach_hang_id,
            COALESCE(SUM(ct.so_luong * ct.don_gia), 0) AS tong_tien
        FROM dt_don_hang AS dh
        LEFT JOIN dt_chi_tiet_don AS ct
            ON ct.don_hang_id = dh.id
        GROUP BY dh.id, dh.khach_hang_id
    ) AS don
    GROUP BY don.khach_hang_id
) AS trung_binh
WHERE trung_binh.avg_tong_don >= 150000
ORDER BY trung_binh.khach_hang_id;
~~~

Trong dữ liệu mẫu:

| khach_hang_id | avg_tong_don |
|---:|---:|
| 1 | 180000 |

An có hai đơn với tổng 270.000 và 90.000, trung bình là 180.000. Bình có 150.000 và 0, trung bình 75.000; Dũng có một đơn 0. Chi không có đơn nên không xuất hiện trong kết quả tổng hợp theo đơn.

**Lưu ý về mẫu số:** truy vấn trên tính trung bình giá trị **mỗi đơn**, bao gồm đơn hủy và đơn chưa có dòng chi tiết với giá trị 0. Nếu muốn trung bình trên đơn PAID có chi tiết, điều kiện và cách chọn mẫu số phải được thay đổi rõ ràng. Không thể lấy một trung bình bất kỳ rồi gọi nó là “giá trị đơn hàng trung bình” mà không xác định tập đơn được tính.

Nhiều tầng có thể diễn đạt rõ các bước, nhưng cũng khiến SQL khó đọc nếu lồng quá sâu. Khi có nhiều lớp xử lý, `WITH` (CTE) có thể làm các bước dễ theo dõi hơn.

## 15. Bảng dẫn xuất, CTE, VIEW và TEMP TABLE khác nhau thế nào?

Bốn công cụ có thể biểu diễn hoặc tái sử dụng một kết quả truy vấn, nhưng có phạm vi và cơ chế khác nhau.

| Cơ chế | Cách tạo | Phạm vi sử dụng | Có tạo dữ liệu lưu riêng không? |
|---|---|---|---|
| **Bảng dẫn xuất** | `FROM (SELECT ...) AS dt` | Câu lệnh đang chạy | Không có yêu cầu lưu dữ liệu riêng; optimizer quyết định cách thực thi |
| **CTE (Common Table Expression)** | `WITH dt AS (SELECT ...)` | Câu lệnh đang chạy, có thể tham chiếu nhiều lần tùy DBMS/cú pháp | Thường là kết quả logic; có thể được inline hoặc materialize |
| **VIEW** | `CREATE VIEW ... AS SELECT ...` | Đối tượng đặt tên trong database, dùng ở nhiều câu lệnh | View thông thường không lưu bản sao dữ liệu kết quả |
| **Bảng tạm** | `CREATE TEMP TABLE ...` | Theo phiên/transaction tùy DBMS | Là đối tượng bảng tạm, có dữ liệu được ghi và lưu trong phạm vi tạm |
| **Bảng vật lý** | `CREATE TABLE ...` | Cho đến khi bị xóa theo quản lý database | Có lưu dữ liệu của bảng |

### 15.1. Viết cùng một ý bằng CTE

Truy vấn bảng dẫn xuất:

~~~sql
SELECT tong.don_hang_id, tong.tong_tien
FROM (
    SELECT
        don_hang_id,
        SUM(so_luong * don_gia) AS tong_tien
    FROM dt_chi_tiet_don
    GROUP BY don_hang_id
) AS tong
WHERE tong.tong_tien > 100000;
~~~

Có thể viết thành CTE:

~~~sql
WITH tong AS (
    SELECT
        don_hang_id,
        SUM(so_luong * don_gia) AS tong_tien
    FROM dt_chi_tiet_don
    GROUP BY don_hang_id
)
SELECT tong.don_hang_id, tong.tong_tien
FROM tong
WHERE tong.tong_tien > 100000;
~~~

Cả hai cho đơn **101 và 103** với dữ liệu mẫu. Bảng dẫn xuất thuận tiện khi đoạn xử lý chỉ dùng một lần trong `FROM/JOIN`. CTE có thể giúp chia nhiều bước thành các phần đặt tên rõ ràng, nhất là khi các bước được sử dụng hoặc liên kết nhiều lần.

Không nên kết luận CTE luôn chạy nhanh hơn hoặc bảng dẫn xuất luôn được tính trước. Tùy phiên bản DBMS và cấu trúc truy vấn, optimizer có thể inline hoặc materialize CTE; trong PostgreSQL hiện đại còn có tùy chọn `MATERIALIZED`/`NOT MATERIALIZED` đối với các trường hợp phù hợp.

### 15.2. Khi nào nên tạo VIEW?

Nếu nhiều nhóm truy vấn đều cần “tổng tiền theo đơn”, view có thể giúp dùng lại định nghĩa:

~~~sql
-- Ví dụ cho môi trường có bảng nghiệp vụ lâu dài.
CREATE VIEW v_tong_tien_don_demo AS
SELECT
    don_hang_id,
    SUM(so_luong * don_gia) AS tong_tien
FROM dt_chi_tiet_don
GROUP BY don_hang_id;
~~~

**Không chạy trực tiếp ví dụ tạo view lâu dài này trên PostgreSQL với bảng `dt_chi_tiet_don` dạng TEMP**: một view lâu dài không thể phụ thuộc an toàn vào đối tượng tạm thuộc phiên; nếu cần minh họa trên bảng TEMP, có thể tạo `TEMP VIEW` hoặc dùng các bảng nghiệp vụ lâu dài.

VIEW là đối tượng cần quản lý quyền, phiên bản định nghĩa và phụ thuộc. Nếu chỉ cần một kết quả trung gian trong một câu lệnh, bảng dẫn xuất hoặc CTE thường gọn hơn.

### 15.3. Khi nào cần TEMP TABLE?

Bảng tạm có ích khi bạn phải ghi ra tập trung gian để thao tác qua **nhiều câu SQL**, thêm chỉ mục, hoặc áp dụng quy trình xử lý từng bước trong một phiên. Bảng dẫn xuất không giúp giữ lại kết quả sau khi câu SQL kết thúc. Tuy vậy, bảng tạm có thêm chi phí tạo đối tượng, ghi dữ liệu và quản lý phiên; không nên dùng chỉ để thay một bảng dẫn xuất đơn giản.

## 16. Phạm vi bí danh và các lỗi cú pháp thường gặp

### 16.1. Quên bí danh của derived table

~~~sql
-- Không di động giữa nhiều DBMS:
SELECT *
FROM (
    SELECT id, ho_ten
    FROM dt_khach_hang
);
~~~

Một số hệ quản trị bắt buộc mỗi bảng dẫn xuất phải có tên bí danh. PostgreSQL từ phiên bản 16 có thể cho phép bỏ bí danh trong những trường hợp này, nhưng MySQL và nhiều môi trường khác vẫn yêu cầu; vì tính rõ ràng và dễ chuyển đổi, nên luôn đặt:

~~~sql
SELECT dt.id, dt.ho_ten
FROM (
    SELECT id, ho_ten
    FROM dt_khach_hang
) AS dt;
~~~

### 16.2. Tham chiếu cột không được SELECT bên trong

~~~sql
-- Sai: dt.khu_vuc không tồn tại trong kết quả bên trong.
SELECT dt.id, dt.khu_vuc
FROM (
    SELECT id, ho_ten
    FROM dt_khach_hang
) AS dt;
~~~

Sửa bằng cách đưa `khu_vuc` vào danh sách cột:

~~~sql
SELECT dt.id, dt.khu_vuc
FROM (
    SELECT id, ho_ten, khu_vuc
    FROM dt_khach_hang
) AS dt;
~~~

Bảng dẫn xuất **chỉ xuất ra các cột mà nó định nghĩa**. Truy vấn ngoài không thể “nhìn xuyên” vào bảng gốc để lấy cột bị bỏ qua.

### 16.3. Đặt tên trùng hoặc thiếu tên cho cột tính toán

~~~sql
SELECT dt.thanh_tien
FROM (
    SELECT so_luong * don_gia AS thanh_tien
    FROM dt_chi_tiet_don
) AS dt;
~~~

Dùng `AS thanh_tien` để cột tính toán có tên rõ ràng. Nếu nhiều cột bên trong cùng tên, truy vấn ngoài có thể gặp tham chiếu mơ hồ hoặc bị DBMS từ chối; hãy đặt bí danh riêng biệt cho các cột cần sử dụng.

### 16.4. Quên ngoặc quanh SELECT bên trong

~~~sql
-- Sai cấu trúc: thiếu ngoặc bao truy vấn con ở FROM.
SELECT *
FROM SELECT id FROM dt_khach_hang;
~~~

Cần:

~~~sql
SELECT *
FROM (
    SELECT id
    FROM dt_khach_hang
) AS dt;
~~~

Ngoặc xác định vị trí của nguồn dữ liệu là kết quả SELECT thay vì tên bảng hiện hữu.

### 16.5. Lẫn lộn alias giữa truy vấn trong và ngoài

~~~sql
SELECT dt.id
FROM (
    SELECT kh.id
    FROM dt_khach_hang AS kh
) AS dt;
~~~

Bí danh `kh` chỉ có ý nghĩa trong truy vấn bên trong. Truy vấn ngoài sử dụng `dt`. Tương tự, nếu bên trong đổi `kh.id AS ma_khach`, truy vấn ngoài cần dùng `dt.ma_khach` thay cho `dt.id`.

### 16.6. Bảng dẫn xuất không tự mang theo mọi ràng buộc

Kết quả của `SELECT` có hình thức bảng nhưng không có nghĩa nó là một bảng mới với các ràng buộc `PRIMARY KEY`, `FOREIGN KEY` hoặc `UNIQUE` được sao chép. Số dòng có thể lặp theo JOIN, điều kiện WHERE hoặc UNION ALL.

Nếu cần đảm bảo **một dòng trên mỗi khóa**, hãy thiết kế điều kiện hoặc phép tổng hợp như `GROUP BY`, `DISTINCT` hay bộ lọc phù hợp, rồi suy luận về ngữ nghĩa của kết quả.

## 17. Bảng dẫn xuất có thể tham chiếu bảng bên ngoài không?

Một bảng dẫn xuất thông thường trong `FROM` **không thể tùy ý tham chiếu alias của bảng đứng trước** ở truy vấn ngoài.

Ví dụ, ý định lấy đơn mới nhất của từng khách hàng:

~~~sql
-- Không hợp lệ như một derived table thông thường trong PostgreSQL:
SELECT kh.ho_ten, don_moi.id
FROM dt_khach_hang AS kh
LEFT JOIN (
    SELECT id
    FROM dt_don_hang
    WHERE khach_hang_id = kh.id
    ORDER BY ngay_dat DESC
    LIMIT 1
) AS don_moi ON TRUE;
~~~

Bí danh `kh` thuộc truy vấn ngoài. PostgreSQL hỗ trợ từ khóa **`LATERAL`** để truy vấn con ở `FROM/JOIN` được phép dùng cột của nguồn đứng trước:

~~~sql
SELECT
    kh.ho_ten,
    don_moi.id AS ma_don_moi_nhat
FROM dt_khach_hang AS kh
LEFT JOIN LATERAL (
    SELECT dh.id
    FROM dt_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
    ORDER BY dh.ngay_dat DESC, dh.id DESC
    LIMIT 1
) AS don_moi ON TRUE
ORDER BY kh.id;
~~~

Kết quả:

| ho_ten | ma_don_moi_nhat |
|---|---:|
| An | 102 |
| Bình | 104 |
| Chi | NULL |
| Dũng | 105 |

Ở đây mỗi khách hàng làm tham số ngầm cho truy vấn `LATERAL`, rồi `LIMIT 1` chọn một đơn mới nhất; khách hàng Chi vẫn được giữ lại bởi `LEFT JOIN`.

Đây là kỹ thuật mở rộng; để học **truy vấn cơ bản**, trước hết hãy thành thạo bảng dẫn xuất độc lập, JOIN và GROUP BY. SQL Server có cơ chế tương tự qua `CROSS APPLY` và `OUTER APPLY`; cú pháp không chuyển nguyên xi từ PostgreSQL.

## 18. Hiệu năng và cách bộ tối ưu xử lý bảng dẫn xuất

Sơ đồ nhiều bước là **cách người viết SQL diễn đạt ý nghĩa**. Máy chủ không bắt buộc tạo một bảng trung gian vật lý cho mỗi cặp ngoặc.

Các hệ quản trị hiện đại có thể:

- Gộp bảng dẫn xuất đơn giản vào truy vấn ngoài.
- Đẩy một số điều kiện lọc xuống gần bảng gốc khi không làm thay đổi kết quả.
- Chọn dùng index, scan, sort, hash aggregate hoặc các thuật toán JOIN thích hợp.
- Materialize kết quả trung gian khi cần vì `LIMIT`, tổng hợp, chi phí ước lượng hay các điều kiện khác.

Vì vậy, **bảng dẫn xuất không tự động nhanh hơn hay chậm hơn** truy vấn viết trực tiếp hoặc CTE.

### 18.1. Ưu tiên điều kiện có chọn lọc ở đúng vị trí ngữ nghĩa

Ví dụ, nếu chỉ tính tổng cho các đơn `PAID`, điều kiện:

~~~sql
WHERE dh.trang_thai = 'PAID'
~~~

trong bảng dẫn xuất có thể giảm số dòng tham gia JOIN/tổng hợp mà vẫn đúng yêu cầu. Nhưng không được đưa một điều kiện trên **tổng tiền đã GROUP BY** xuống thành điều kiện trên từng dòng chi tiết, vì điều đó thay đổi kết quả.

### 18.2. Xác định chỉ mục trên bảng gốc

Không thể tạo index trực tiếp lên một bí danh bảng dẫn xuất tạm thời trong `FROM`. Các index phục vụ truy vấn được đặt trên bảng gốc hoặc những đối tượng lưu trữ thích hợp (bảng tạm thực sự, materialized view tùy DBMS).

Ở mô hình ví dụ có thể cân nhắc index theo nhu cầu thật trên:

- `dt_don_hang.khach_hang_id` khi JOIN hoặc tìm đơn theo khách.
- `dt_chi_tiet_don.don_hang_id` khi tổng hợp chi tiết theo đơn.
- `dt_don_hang.trang_thai` khi lọc nhiều dữ liệu theo trạng thái, nếu có đủ tính chọn lọc.

Dữ liệu mẫu chỉ vài dòng nên không cần tạo index phục vụ hiệu năng. Trong PostgreSQL, PK tổng hợp `(don_hang_id, san_pham_id)` đã có index bắt đầu bằng `don_hang_id`. Việc có nên thêm index còn phụ thuộc quy mô, tần suất đọc/ghi và kế hoạch truy vấn.

### 18.3. Đọc kế hoạch thực thi

Với dữ liệu lớn, dùng PostgreSQL:

~~~sql
EXPLAIN
SELECT
    tong.don_hang_id,
    tong.tong_tien
FROM (
    SELECT
        don_hang_id,
        SUM(so_luong * don_gia) AS tong_tien
    FROM dt_chi_tiet_don
    GROUP BY don_hang_id
) AS tong
WHERE tong.tong_tien >= 100000;
~~~

`EXPLAIN` cho biết kế hoạch dự kiến; `EXPLAIN ANALYZE` thực sự chạy truy vấn để đo đạc, nên cần thận trọng nếu SQL bên dưới có thay đổi dữ liệu. Bạn có thể thấy các bước Aggregate, Filter, Scan..., nhưng cách hiển thị phụ thuộc phiên bản và kế hoạch được chọn. Đừng đoán rằng mỗi bảng dẫn xuất nhất định xuất hiện dưới tên “temporary table” trong kế hoạch.

## 19. Khác biệt cú pháp theo hệ quản trị

Bảng dẫn xuất là khái niệm được sử dụng rộng rãi, nhưng cú pháp nhỏ có thể ảnh hưởng tính di động.

| Hệ quản trị | Bí danh của bảng dẫn xuất | Điểm khác cần lưu ý |
|---|---|---|
| **PostgreSQL** | Nên dùng `AS dt`; từ bản 16 có thể bỏ bí danh trong một số trường hợp | Hỗ trợ `LIMIT`, `LATERAL`, `FILTER` và nhiều cú pháp tổng hợp |
| **MySQL/MariaDB** | Bảng dẫn xuất phải có bí danh | `LIMIT` phổ biến; có khác biệt phiên bản về optimizer và truy vấn tương quan |
| **SQL Server** | Cần bí danh cho bảng dẫn xuất; `AS dt` hợp lệ | Dùng `TOP`/`OFFSET ... FETCH` thay `LIMIT`; `APPLY` cho nguồn phụ thuộc |
| **Oracle** | Dùng bí danh bảng theo cú pháp Oracle, thường **không có AS** trước bí danh bảng | Dùng `FETCH FIRST ... ROWS ONLY` hoặc các cách giới hạn dòng phù hợp phiên bản |
| **SQLite** | Hỗ trợ subquery trong `FROM` và bí danh | Hỗ trợ `LIMIT`; các chi tiết tối ưu và một số tính năng nâng cao khác PostgreSQL |

Ví dụ viết mẫu tổng hợp tương đối gần SQL chuẩn:

~~~sql
SELECT dt.don_hang_id, dt.tong_tien
FROM (
    SELECT
        don_hang_id,
        SUM(so_luong * don_gia) AS tong_tien
    FROM chi_tiet_don_hang
    GROUP BY don_hang_id
) dt
WHERE dt.tong_tien >= 100000;
~~~

`chi_tiet_don_hang` ở đây là tên bảng minh họa không kèm tiền tố `dt_`; để chạy trên bộ dữ liệu của bài, đổi thành `dt_chi_tiet_don`. Cú pháp **không viết AS trước alias bảng** hữu ích khi cần gần với Oracle, còn PostgreSQL/MySQL/SQL Server thường chấp nhận cả cách viết có `AS`.

SQL Server có thể cần đổi tên bảng, kiểu dữ liệu hoặc cú pháp khác nếu chạy đầy đủ script tạo dữ liệu PostgreSQL. **Đừng cho rằng cùng một SELECT luôn chạy nguyên văn trên mọi DBMS** khi những phần khác của script sử dụng cú pháp đặc thù.

## 20. Bài tập thực hành

Hãy dùng dữ liệu `dt_khach_hang`, `dt_don_hang` và `dt_chi_tiet_don` đã tạo ở phần 3. Các lời giải dưới đây đều đọc dữ liệu, không sửa bảng mẫu.

### Bài 1. Liệt kê mọi khách hàng và số đơn

Yêu cầu: mỗi khách hàng có một hàng; nếu chưa có đơn, số đơn bằng 0. Hãy dùng **bảng dẫn xuất** để đếm theo `khach_hang_id`.

**Lời giải:**

~~~sql
SELECT
    kh.ho_ten,
    COALESCE(dt.so_don, 0) AS so_don
FROM dt_khach_hang AS kh
LEFT JOIN (
    SELECT
        khach_hang_id,
        COUNT(*) AS so_don
    FROM dt_don_hang
    GROUP BY khach_hang_id
) AS dt
    ON dt.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

| ho_ten | so_don |
|---|---:|
| An | 2 |
| Bình | 2 |
| Chi | 0 |
| Dũng | 1 |

**Giải thích:** bảng dẫn xuất có tối đa một dòng cho mỗi khách hàng có đơn. LEFT JOIN giữ Chi, còn COALESCE chuyển NULL thành 0.

### Bài 2. Tìm đơn có tổng tiền lớn nhất

Yêu cầu: tính tổng tiền theo từng đơn, rồi lấy đơn có tổng tiền lớn nhất.

**Lời giải:**

~~~sql
SELECT
    dt.don_hang_id,
    dt.tong_tien
FROM (
    SELECT
        don_hang_id,
        SUM(so_luong * don_gia) AS tong_tien
    FROM dt_chi_tiet_don
    GROUP BY don_hang_id
) AS dt
ORDER BY dt.tong_tien DESC, dt.don_hang_id
LIMIT 1;
~~~

Kết quả: đơn **101 — 270.000**. Nếu có nhiều đơn đồng hạng, câu này chỉ lấy một đơn theo tiêu chí thứ hai; muốn giữ toàn bộ đồng hạng cần cách khác như `RANK()` hoặc xác định ngưỡng bằng truy vấn riêng.

### Bài 3. Đếm khách hàng có tổng PAID lớn hơn 100.000

Yêu cầu: đếm **số khách hàng**, không phải số đơn hoặc số dòng chi tiết.

**Lời giải:**

~~~sql
SELECT COUNT(*) AS so_khach_hang
FROM (
    SELECT
        dh.khach_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong_paid
    FROM dt_don_hang AS dh
    JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    WHERE dh.trang_thai = 'PAID'
    GROUP BY dh.khach_hang_id
) AS dt
WHERE dt.tong_paid > 100000;
~~~

Kết quả: **2 khách hàng**, là An và Bình.

**Lý do:** bảng dẫn xuất trả tối đa một dòng trên mỗi khách hàng có chi tiết PAID; COUNT ngoài đếm những khách hàng qua ngưỡng. Nếu tính trực tiếp trên dòng chi tiết chưa GROUP BY, có thể đếm nhầm số sản phẩm hoặc số đơn.

### Bài 4. Khách hàng chưa có đơn PAID

Yêu cầu: tìm mọi khách hàng **chưa có đơn trạng thái PAID**, bất kể họ có đơn NEW hay CANCELLED.

**Lời giải:**

~~~sql
SELECT kh.id, kh.ho_ten
FROM dt_khach_hang AS kh
LEFT JOIN (
    SELECT DISTINCT khach_hang_id
    FROM dt_don_hang
    WHERE trang_thai = 'PAID'
) AS dt
    ON dt.khach_hang_id = kh.id
WHERE dt.khach_hang_id IS NULL
ORDER BY kh.id;
~~~

Kết quả: **Chi**. Trong dữ liệu mẫu, An, Bình và Dũng đều có ít nhất một đơn PAID; Dũng được tính là **có đơn PAID** dù đơn 105 chưa có dòng chi tiết.

**Chú ý:** câu hỏi “chưa có đơn PAID” khác câu hỏi “chưa có tiền từ các đơn PAID”. Phải chọn bảng nguồn đúng với ý nghĩa muốn kiểm tra.

### Bài 5. Tổng tiền theo khu vực

Yêu cầu: tính tổng tiền từ **mọi dòng chi tiết**, nhóm theo khu vực khách hàng, và trả một hàng cho mỗi khu vực. Khu vực chưa có đơn phải có tổng 0.

**Lời giải:**

~~~sql
SELECT
    kv.khu_vuc,
    COALESCE(SUM(kv.tong_khach), 0) AS tong_khu_vuc
FROM (
    SELECT
        kh.id AS khach_hang_id,
        kh.khu_vuc,
        COALESCE(SUM(ct.so_luong * ct.don_gia), 0) AS tong_khach
    FROM dt_khach_hang AS kh
    LEFT JOIN dt_don_hang AS dh
        ON dh.khach_hang_id = kh.id
    LEFT JOIN dt_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    GROUP BY kh.id, kh.khu_vuc
) AS kv
GROUP BY kv.khu_vuc
ORDER BY kv.khu_vuc;
~~~

Kết quả theo khu vực:

| khu_vuc | tong_khu_vuc |
|---|---:|
| Bắc | 360000 |
| Nam | 150000 |
| Trung | 0 |

An ở Bắc có đơn tổng 270.000 và 90.000, còn Chi cũng ở Bắc nhưng chưa có đơn. Bình ở Nam có 150.000 từ chi tiết, Dũng ở Trung có 0.

Câu này dùng **hai mức tổng hợp**: từ dòng chi tiết lên từng khách hàng, rồi từ từng khách hàng lên khu vực. Nó không lọc trạng thái đơn hàng, nên các đơn NEW vẫn được tính; nếu muốn doanh thu PAID, cần thêm điều kiện trạng thái đúng chỗ và xác định cách giữ khách hàng chưa có đơn PAID.

### Bài 6. Dự đoán kết quả khi JOIN sai mức chi tiết

Xét:

~~~sql
SELECT
    kh.ho_ten,
    COUNT(dh.id) AS so_dong_dem
FROM dt_khach_hang AS kh
JOIN dt_don_hang AS dh
    ON dh.khach_hang_id = kh.id
JOIN dt_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

Hỏi: An sẽ có `so_dong_dem` bằng 2 hay 3? Chi và Dũng có xuất hiện không?

**Đáp án:** An là **3** vì hai dòng chi tiết của đơn 101 và một dòng chi tiết của đơn 102. Chi không có đơn; Dũng có đơn 105 nhưng không có chi tiết, nên đều bị loại bởi INNER JOIN. Nếu mục tiêu đếm số đơn theo khách hàng, nên tổng hợp trực tiếp từ `dt_don_hang` hoặc dùng `COUNT(DISTINCT dh.id)` cùng lựa chọn JOIN phù hợp.

### Bài 7. Sửa truy vấn có cột ngoài phạm vi

Truy vấn sau bị lỗi:

~~~sql
SELECT dt.ho_ten, dt.khu_vuc
FROM (
    SELECT ho_ten
    FROM dt_khach_hang
) AS dt;
~~~

**Vì sao?** Bảng dẫn xuất `dt` chỉ trả cột `ho_ten`, không xuất `khu_vuc`.

**Sửa:**

~~~sql
SELECT dt.ho_ten, dt.khu_vuc
FROM (
    SELECT ho_ten, khu_vuc
    FROM dt_khach_hang
) AS dt;
~~~

Bí danh bảng dẫn xuất không giúp truy cập những cột gốc chưa được truy vấn bên trong chọn ra.

## 21. Checklist tư duy khi kết hợp truy vấn với bảng dẫn xuất

Khi dùng `FROM (SELECT ...) AS dt` trong thực tế, hãy tự trả lời:

1. **Bảng dẫn xuất biểu diễn dữ liệu ở mức nào?** Một hàng cho một dòng chi tiết, một đơn, một khách hàng hay một khu vực?
2. **Nó xuất ra cột nào?** Các khóa cần JOIN và các chỉ số cần lọc đã xuất hiện trong `SELECT` bên trong chưa?
3. **Điều kiện nào phải áp dụng trước tổng hợp?** Ví dụ lọc đơn PAID trước khi tính tổng.
4. **Điều kiện nào áp dụng sau tổng hợp?** Ví dụ tổng chi tiêu đạt 200.000 mới được chọn.
5. **Có cần giữ những bản ghi không có liên kết không?** Nếu có, chọn đúng phía trái của `LEFT JOIN`.
6. **NULL cần hiểu là gì?** Chưa có dữ liệu, tổng rỗng hay một giá trị thật sự bằng 0?
7. **Mỗi khóa JOIN có bao nhiêu dòng ở bảng dẫn xuất?** Nếu nhiều hơn một, kết quả ngoài sẽ được nhân theo số dòng khớp.
8. **ORDER BY và LIMIT thuộc tập nào?** Trên dòng nguồn hay trên kết quả đã tổng hợp?
9. **Bí danh và tên cột có rõ ràng không?** Tránh tham chiếu cột nằm ngoài phạm vi hoặc cùng tên từ nhiều nguồn.
10. **Có cần lưu hoặc tái sử dụng kết quả qua nhiều statement không?** Nếu có, cân nhắc CTE, VIEW hoặc bảng tạm theo đúng nhu cầu.

Bảng dẫn xuất là cách chia một truy vấn SQL phức hợp thành những phần có ý nghĩa rõ ràng: **tạo tập kết quả bên trong, rồi sử dụng tập đó như một nguồn dữ liệu để lọc, JOIN, sắp xếp hoặc tổng hợp tiếp**. Nắm được mức chi tiết của mỗi nguồn và vị trí của điều kiện lọc giúp bạn tránh số liệu bị nhân bản, đếm sai và bỏ sót những hàng không có liên kết.
