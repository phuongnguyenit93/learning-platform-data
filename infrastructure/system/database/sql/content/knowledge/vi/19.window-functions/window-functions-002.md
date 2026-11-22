# Cấu trúc OVER, PARTITION BY và ORDER BY trong hàm cửa sổ SQL

Khi xem báo cáo giao dịch, bạn có thể muốn vừa thấy **từng giao dịch riêng lẻ**, vừa biết **tổng tiền của khu vực**, **vị trí giao dịch trong khu vực** hoặc **tổng lũy kế theo ngày**. Nếu dùng `GROUP BY`, nhiều dòng giao dịch bị gộp thành một dòng đại diện cho nhóm. Nhưng nếu muốn giữ nguyên từng giao dịch và gắn thêm chỉ số so sánh, SQL có **hàm cửa sổ** (*window functions*).

Ba thành phần quan trọng nhất để hiểu cửa sổ là:

- **`OVER (...)`**: khai báo ngữ cảnh cửa sổ mà hàm sẽ tính.
- **`PARTITION BY`**: chia những hàng đầu vào thành các nhóm độc lập để tính toán, **không gộp các hàng thành một hàng**.
- **`ORDER BY` bên trong `OVER`**: xác định thứ tự các hàng **trong từng cửa sổ** khi tính hạng, độ trễ, tổng lũy kế hoặc các hàm phụ thuộc thứ tự.

Một điểm nâng cao nhưng rất quan trọng: với nhiều hàm, **khung cửa sổ** (*window frame*) như `ROWS BETWEEN ...` quyết định chính xác **những hàng nào tham gia phép tính tại mỗi dòng**. Nếu không khai báo frame, việc có hay không có `ORDER BY` bên trong `OVER` có thể làm thay đổi kết quả `SUM` hoặc `AVG`.

Bài học nằm trong chương **Hàm cửa sổ** của module **Database SQL**. Các ví dụ thực hành dùng **PostgreSQL** và dữ liệu mẫu đầy đủ, có ngày trùng nhau, giá trị số 0 và giá trị `NULL`. Các kiến thức nền tảng áp dụng rộng rãi cho SQL, nhưng cú pháp và quy tắc frame ở một số DBMS sẽ được phân biệt rõ.

## 1. Cửa sổ giải quyết bài toán gì?

Giả sử bảng giao dịch có những hàng:

| Giao dịch | Khu vực | Số tiền |
|---:|---|---:|
| 101 | Bắc | 100 |
| 102 | Bắc | 200 |
| 103 | Bắc | 150 |
| 201 | Nam | 300 |
| 202 | Nam | 100 |

Bạn muốn một báo cáo có cột **tổng giao dịch trong khu vực** bên cạnh **mỗi giao dịch**:

| Giao dịch | Khu vực | Số tiền | Tổng khu vực |
|---:|---|---:|---:|
| 101 | Bắc | 100 | 450 |
| 102 | Bắc | 200 | 450 |
| 103 | Bắc | 150 | 450 |
| 201 | Nam | 300 | 400 |
| 202 | Nam | 100 | 400 |

Có thể hình dung:

~~~text
Các hàng nguồn:
   Bắc: 101 (100), 102 (200), 103 (150)
   Nam: 201 (300), 202 (100)

PARTITION BY khu_vuc:
   Bắc ──► tập 3 hàng ──► SUM = 450
   Nam ──► tập 2 hàng ──► SUM = 400

Kết quả:
   Mỗi giao dịch vẫn giữ một hàng,
   nhưng có thêm tổng tương ứng của khu vực.
~~~

Câu SQL chính:

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
    ) AS tong_khu_vuc
FROM giao_dich;
~~~

`giao_dich` ở trên là tên bảng minh họa. Phần 3 sẽ tạo bảng thử nghiệm `wc_giao_dich` để bạn chạy từng ví dụ.

**Điểm cốt lõi:** hàm cửa sổ trả một kết quả gắn với **từng hàng đang xét**. Khác với `GROUP BY` thông thường, nó không tự làm mất danh tính từng hàng nguồn.

## 2. Cú pháp tổng quát của OVER

Dạng phổ biến:

~~~sql
ham_cua_so(...) OVER (
    PARTITION BY bieu_thuc_phan_nhom
    ORDER BY bieu_thuc_sap_xep [ASC | DESC]
    frame_clause
)
~~~

Ba phần nằm trong ngoặc của `OVER` có vai trò khác nhau:

| Thành phần | Có bắt buộc với mọi hàm? | Vai trò |
|---|---|---|
| `OVER (...)` | Có, khi dùng hàm dưới dạng window function | Xác định ngữ cảnh tính theo cửa sổ |
| `PARTITION BY` | Thường là tùy chọn | Chia tập đầu vào thành các partition |
| `ORDER BY` trong OVER | Tùy hàm và DBMS; một số hàm bắt buộc | Xác định trình tự trong từng partition |
| `ROWS / RANGE / GROUPS ...` | Tùy chọn với những hàm hỗ trợ frame | Chọn các hàng trong frame của dòng hiện tại |
| `ORDER BY` ngoài cùng | Không bắt buộc, nhưng cần nếu muốn thứ tự hiển thị xác định | Sắp xếp kết quả cuối cùng |

Một số mẫu cơ bản:

~~~sql
-- Toàn bộ các dòng là một cửa sổ.
SUM(so_tien) OVER ()

-- Chia cửa sổ theo khu vực, không có thứ tự nội bộ.
SUM(so_tien) OVER (PARTITION BY khu_vuc)

-- Chia theo khu vực rồi xác định thứ tự ngày.
SUM(so_tien) OVER (
    PARTITION BY khu_vuc
    ORDER BY ngay_giao_dich, id
)

-- Định nghĩa cụ thể frame lũy kế theo hàng.
SUM(so_tien) OVER (
    PARTITION BY khu_vuc
    ORDER BY ngay_giao_dich, id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Các biểu thức trên **không phải statement độc lập**; chúng cần đặt trong `SELECT` hay vị trí được DBMS hỗ trợ. Ở PostgreSQL, hàm cửa sổ được phép xuất hiện trong danh sách `SELECT` và trong `ORDER BY` của truy vấn; các trường hợp như `WHERE`, `GROUP BY` và `HAVING` không cho đặt trực tiếp hàm cửa sổ cùng cấp.

### 2.1. Hàm tổng hợp cũng có thể trở thành hàm cửa sổ

So sánh:

~~~sql
-- Hàm tổng hợp thông thường: một kết quả cho toàn bộ dữ liệu.
SELECT SUM(so_tien)
FROM giao_dich;
~~~

với:

~~~sql
-- Hàm tổng hợp dùng dưới dạng cửa sổ:
-- vẫn trả một hàng cho mỗi giao dịch.
SELECT
    id,
    so_tien,
    SUM(so_tien) OVER () AS tong_tat_ca
FROM giao_dich;
~~~

Khi có `OVER`, các hàm `SUM`, `AVG`, `COUNT`, `MIN` và `MAX` có thể tính theo cửa sổ thay vì gộp hàng theo kiểu aggregate thông thường.

Ngoài ra còn có các hàm được thiết kế cho cửa sổ như `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `LAG`, `LEAD`, `FIRST_VALUE` và `LAST_VALUE`. Những hàm này phụ thuộc rất nhiều vào thứ tự khai báo trong `OVER`.

## 3. Bộ dữ liệu thực hành PostgreSQL

Hãy thực hành trong **database thử nghiệm**, cùng một phiên PostgreSQL. Ta tạo bảng tạm `wc_giao_dich` để không làm thay đổi dữ liệu nghiệp vụ đang có.

### 3.1. Tạo bảng

~~~sql
CREATE TEMP TABLE wc_giao_dich (
    id INTEGER PRIMARY KEY,
    khu_vuc VARCHAR(20) NOT NULL,
    nhan_vien VARCHAR(60) NOT NULL,
    ngay_giao_dich DATE NOT NULL,
    so_tien NUMERIC(12,2)
        CHECK (so_tien >= 0)
);
~~~

Giải thích:

- `id` là khóa chính duy nhất, dùng để phá hòa khi hai giao dịch có cùng ngày.
- `khu_vuc` là khóa để minh họa `PARTITION BY`.
- `nhan_vien` là chiều phân tích bổ sung.
- `ngay_giao_dich` giúp tạo thứ tự thời gian.
- `so_tien` có thể `NULL` vì không đặt `NOT NULL`. Nó cũng có thể bằng 0.

Trong bài này, `NULL` ở `so_tien` được hiểu là **chưa có số tiền được xác định**, khác với **đã ghi nhận số tiền bằng 0**. Đó là quy ước của dữ liệu mẫu, không áp dụng bắt buộc cho mọi hệ thống giao dịch.

### 3.2. Nạp 12 giao dịch

~~~sql
INSERT INTO wc_giao_dich
    (id, khu_vuc, nhan_vien, ngay_giao_dich, so_tien)
VALUES
    (101, 'Bắc', 'An',    DATE '2026-10-01', 100),
    (102, 'Bắc', 'Bình',  DATE '2026-10-03', 200),
    (103, 'Bắc', 'An',    DATE '2026-10-03', 150),
    (104, 'Bắc', 'Chi',   DATE '2026-10-05', NULL),
    (105, 'Bắc', 'Bình',  DATE '2026-10-07', 50),

    (201, 'Nam', 'Dũng',  DATE '2026-10-02', 300),
    (202, 'Nam', 'Hà',    DATE '2026-10-03', 100),
    (203, 'Nam', 'Dũng',  DATE '2026-10-03', 100),
    (204, 'Nam', 'Giang', DATE '2026-10-06', 0),
    (205, 'Nam', 'Hà',    DATE '2026-10-08', NULL),

    (301, 'Trung', 'Khôi', DATE '2026-10-02', NULL),
    (302, 'Trung', 'Lan',  DATE '2026-10-04', NULL);
~~~

### 3.3. Quan sát bảng nguồn

~~~sql
SELECT
    id,
    khu_vuc,
    nhan_vien,
    ngay_giao_dich,
    so_tien
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

| id | khu_vuc | nhan_vien | ngay_giao_dich | so_tien |
|---:|---|---|---|---:|
| 101 | Bắc | An | 2026-10-01 | 100 |
| 102 | Bắc | Bình | 2026-10-03 | 200 |
| 103 | Bắc | An | 2026-10-03 | 150 |
| 104 | Bắc | Chi | 2026-10-05 | NULL |
| 105 | Bắc | Bình | 2026-10-07 | 50 |
| 201 | Nam | Dũng | 2026-10-02 | 300 |
| 202 | Nam | Hà | 2026-10-03 | 100 |
| 203 | Nam | Dũng | 2026-10-03 | 100 |
| 204 | Nam | Giang | 2026-10-06 | 0 |
| 205 | Nam | Hà | 2026-10-08 | NULL |
| 301 | Trung | Khôi | 2026-10-02 | NULL |
| 302 | Trung | Lan | 2026-10-04 | NULL |

Những chi tiết cần ghi nhớ:

- Bắc và Nam có **5 hàng** mỗi khu vực; Trung có **2 hàng**.
- Tổng tiền của Bắc = 100 + 200 + 150 + 50 = **500**.
- Tổng tiền của Nam = 300 + 100 + 100 + 0 = **500**.
- Trung có **hai dòng nhưng toàn bộ số tiền NULL**, nên `SUM(so_tien)` của Trung trả NULL.
- Tổng trên toàn bộ bảng = **1000**, gồm 8 giá trị số không NULL.
- Bắc có hai giao dịch **cùng ngày 03/10** (102 và 103); Nam cũng có hai giao dịch cùng ngày ấy (202 và 203).
- Nam có **hai giao dịch cùng số tiền 100** (202 và 203), thuận tiện để học `RANK`.
- Nam có một số tiền **0** (204), giúp phân biệt 0 với NULL.

Các ví dụ ở những phần tiếp theo **chỉ đọc dữ liệu**, trừ lệnh tạo/nạp bảng ở phần này.

## 4. OVER () không có PARTITION BY, không có ORDER BY

Đơn giản nhất:

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    SUM(so_tien) OVER () AS tong_tat_ca
FROM wc_giao_dich
ORDER BY id;
~~~

`OVER ()` xem **mọi hàng thuộc tập đầu vào của bước tính cửa sổ** như một partition duy nhất.

Kết quả có 12 dòng; cột `tong_tat_ca` đều là **1000**:

| id | khu_vuc | so_tien | tong_tat_ca |
|---:|---|---:|---:|
| 101 | Bắc | 100 | 1000 |
| 102 | Bắc | 200 | 1000 |
| 103 | Bắc | 150 | 1000 |
| 104 | Bắc | NULL | 1000 |
| 105 | Bắc | 50 | 1000 |
| 201 | Nam | 300 | 1000 |
| 202 | Nam | 100 | 1000 |
| 203 | Nam | 100 | 1000 |
| 204 | Nam | 0 | 1000 |
| 205 | Nam | NULL | 1000 |
| 301 | Trung | NULL | 1000 |
| 302 | Trung | NULL | 1000 |

### 4.1. Nhiều hàm trên cùng một cửa sổ

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    COUNT(*) OVER () AS so_hang_tat_ca,
    COUNT(so_tien) OVER () AS so_gia_tri_co_tien,
    SUM(so_tien) OVER () AS tong_tien,
    AVG(so_tien) OVER () AS avg_tien,
    MIN(so_tien) OVER () AS min_tien,
    MAX(so_tien) OVER () AS max_tien
FROM wc_giao_dich
ORDER BY id;
~~~

Ở mỗi dòng, các cột tổng hợp toàn cục có kết quả:

| so_hang_tat_ca | so_gia_tri_co_tien | tong_tien | avg_tien | min_tien | max_tien |
|---:|---:|---:|---:|---:|---:|
| 12 | 8 | 1000 | 125 | 0 | 300 |

`COUNT(*)` tính cả 12 dòng. `COUNT(so_tien)` chỉ tính 8 dòng có tiền không NULL. `AVG(so_tien)` = 1000/8 = **125**, không phải 1000/12.

### 4.2. So với GROUP BY

~~~sql
-- Trả một hàng vì có tổng hợp, không GROUP BY.
SELECT SUM(so_tien) AS tong_tien
FROM wc_giao_dich;
~~~

Kết quả: **một hàng** có tổng 1000.

Trong khi:

~~~sql
-- Trả 12 hàng, mỗi giao dịch vẫn xuất hiện.
SELECT
    id,
    SUM(so_tien) OVER () AS tong_tien
FROM wc_giao_dich
ORDER BY id;
~~~

Kết quả: **12 hàng**. Cách dùng OVER không làm gộp danh tính mỗi giao dịch.

## 5. PARTITION BY: tạo các nhóm độc lập nhưng không gộp hàng

Khi đặt `PARTITION BY khu_vuc`, mỗi khu vực có một tập tính toán riêng:

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
    ) AS tong_khu_vuc
FROM wc_giao_dich
ORDER BY khu_vuc, id;
~~~

Kết quả:

| id | khu_vuc | so_tien | tong_khu_vuc |
|---:|---|---:|---:|
| 101 | Bắc | 100 | 500 |
| 102 | Bắc | 200 | 500 |
| 103 | Bắc | 150 | 500 |
| 104 | Bắc | NULL | 500 |
| 105 | Bắc | 50 | 500 |
| 201 | Nam | 300 | 500 |
| 202 | Nam | 100 | 500 |
| 203 | Nam | 100 | 500 |
| 204 | Nam | 0 | 500 |
| 205 | Nam | NULL | 500 |
| 301 | Trung | NULL | NULL |
| 302 | Trung | NULL | NULL |

Dữ liệu được **phân vùng logic**, mỗi vùng có một tổng riêng. Hàng của khu vực Trung vẫn xuất hiện, nhưng tổng của Trung là NULL do không có giá trị số nào tham gia `SUM`.

### 5.1. Số dòng không giảm

`PARTITION BY` thường gây nhầm với `GROUP BY` vì cả hai đều có khái niệm “nhóm”.

So sánh:

~~~sql
-- GROUP BY: 3 hàng, một hàng cho mỗi khu vực.
SELECT khu_vuc, SUM(so_tien) AS tong
FROM wc_giao_dich
GROUP BY khu_vuc
ORDER BY khu_vuc;
~~~

~~~sql
-- PARTITION BY: 12 hàng, một hàng cho mỗi giao dịch.
SELECT
    id,
    khu_vuc,
    SUM(so_tien) OVER (PARTITION BY khu_vuc) AS tong
FROM wc_giao_dich
ORDER BY khu_vuc, id;
~~~

Bảng so sánh:

| Đặc điểm | GROUP BY khu_vuc | OVER (PARTITION BY khu_vuc) |
|---|---|---|
| Số hàng với dữ liệu mẫu | 3 | 12 |
| Cấp chi tiết kết quả | Một hàng/khu vực | Một hàng/giao dịch |
| Tổng Bắc | Một dòng 500 | Lặp 500 trên 5 giao dịch Bắc |
| Có thể hiển thị id giao dịch riêng mà không tổng hợp thêm? | Không như cột thường không thuộc nhóm | Có |
| Mục đích | Tạo báo cáo tổng kết nhóm | Bổ sung chỉ số nhóm cho từng dòng |

**PARTITION BY không phải GROUP BY thứ hai.** Nó xác định phạm vi tính hàm cửa sổ trên những hàng đã đi đến giai đoạn window processing.

### 5.2. Đếm số hàng và giá trị không NULL theo partition

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    COUNT(*) OVER (
        PARTITION BY khu_vuc
    ) AS so_giao_dich_khu_vuc,
    COUNT(so_tien) OVER (
        PARTITION BY khu_vuc
    ) AS so_giao_dich_co_tien,
    AVG(so_tien) OVER (
        PARTITION BY khu_vuc
    ) AS tien_trung_binh
FROM wc_giao_dich
ORDER BY khu_vuc, id;
~~~

Các chỉ số lặp trên mỗi hàng cùng khu vực:

| khu_vuc | so_giao_dich_khu_vuc | so_giao_dich_co_tien | tien_trung_binh |
|---|---:|---:|---:|
| Bắc | 5 | 4 | 125 |
| Nam | 5 | 4 | 125 |
| Trung | 2 | 0 | NULL |

Không có giá trị nào để tính AVG ở Trung; không nên tự gọi đó là **trung bình bằng 0** nếu dữ liệu chỉ cho biết chưa có số tiền.

### 5.3. PARTITION BY nhiều biểu thức

Bạn có thể phân chia theo **kết hợp nhiều cột**:

~~~sql
SELECT
    id,
    khu_vuc,
    nhan_vien,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc, nhan_vien
    ) AS tong_nhan_vien_trong_vung
FROM wc_giao_dich
ORDER BY khu_vuc, nhan_vien, id;
~~~

Ví dụ:

- Bắc–An: giao dịch 101 (100) và 103 (150) → tổng 250.
- Bắc–Bình: 102 (200) và 105 (50) → tổng 250.
- Bắc–Chi: chỉ có 104 (NULL) → tổng NULL.
- Nam–Dũng: 201 (300) và 203 (100) → tổng 400.
- Nam–Hà: 202 (100) và 205 (NULL) → tổng 100.

**Một partition** là tập các hàng có cùng giá trị ở **toàn bộ biểu thức** trong PARTITION BY. Vì vậy, PARTITION BY hai cột không nhất thiết cho kết quả giống PARTITION BY từng cột riêng.

### 5.4. PARTITION BY bằng biểu thức tính toán

Trong PostgreSQL, có thể phân chia theo tháng và khu vực:

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    SUM(so_tien) OVER (
        PARTITION BY
            khu_vuc,
            DATE_TRUNC('month', ngay_giao_dich)
    ) AS tong_khu_vuc_thang
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Vì dữ liệu mẫu đều thuộc **tháng 10/2026**, kết quả tổng theo khu vực–tháng trùng tổng theo khu vực. Nếu có dữ liệu tháng 11, mỗi tháng sẽ tạo partition mới cho cùng khu vực.

Sử dụng `DATE_TRUNC('month', ngay_giao_dich)` thay vì chỉ `EXTRACT(MONTH FROM ngay_giao_dich)` giúp tránh vô tình gộp tháng 10 của **nhiều năm khác nhau** vào một partition.

### 5.5. Nếu khóa phân vùng NULL thì sao?

`PARTITION BY` có thể dùng một cột nullable. Khi đó, các hàng có cùng bộ giá trị phân vùng — kể cả những hàng có giá trị NULL ở khóa phân vùng — được xếp trong cùng partition theo quy tắc nhóm của window function.

Ví dụ độc lập:

~~~sql
SELECT
    v.id,
    v.nhom,
    v.gia_tri,
    COUNT(*) OVER (
        PARTITION BY v.nhom
    ) AS so_hang_trong_nhom
FROM (
    VALUES
        (1, 'A'::TEXT, 10),
        (2, 'A'::TEXT, 20),
        (3, NULL::TEXT, 30),
        (4, NULL::TEXT, 40)
) AS v(id, nhom, gia_tri)
ORDER BY v.id;
~~~

Kết quả mỗi dòng có `so_hang_trong_nhom = 2`: hai dòng nhóm A và hai dòng nhóm NULL. Không nên nhầm cơ chế phân vùng nhóm với phép so sánh `NULL = NULL` trong WHERE, phép so sánh này không trả TRUE.

## 6. ORDER BY trong OVER có ý nghĩa gì?

Thêm `ORDER BY` bên trong cửa sổ khi cần xác định **trình tự các hàng trong mỗi partition**.

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    so_tien,
    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich ASC, id ASC
    ) AS so_thu_tu_trong_vung
FROM wc_giao_dich
ORDER BY khu_vuc, so_thu_tu_trong_vung;
~~~

Kết quả theo khu vực Bắc:

| id | ngay_giao_dich | so_thu_tu_trong_vung |
|---:|---|---:|
| 101 | 2026-10-01 | 1 |
| 102 | 2026-10-03 | 2 |
| 103 | 2026-10-03 | 3 |
| 104 | 2026-10-05 | 4 |
| 105 | 2026-10-07 | 5 |

Kết quả theo khu vực Nam: 201 → 1, 202 → 2, 203 → 3, 204 → 4, 205 → 5. Khu vực Trung: 301 → 1, 302 → 2.

### 6.1. Vì sao cần thêm id sau ngày?

Bắc có hai hàng cùng ngày 03/10 (102 và 103). Nếu chỉ viết:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY khu_vuc
    ORDER BY ngay_giao_dich
)
~~~

thứ tự giữa hai dòng có cùng ngày **không được xác định chỉ bởi khóa ngày**. DBMS có thể chọn thứ tự tùy kế hoạch hoặc dữ liệu, khiến `ROW_NUMBER` của 102 và 103 có thể hoán đổi trong những lần chạy khác nhau.

Thêm `id ASC` làm tiêu chí phá hòa:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY khu_vuc
    ORDER BY ngay_giao_dich ASC, id ASC
)
~~~

Vì `id` duy nhất, thứ tự theo cặp `(ngay_giao_dich, id)` là xác định trên tập dữ liệu tại một thời điểm.

### 6.2. ORDER BY của cửa sổ không phải ORDER BY hiển thị

Hai câu này không nói cùng một việc:

~~~sql
-- Sắp xếp để ROW_NUMBER đánh số từng khu vực theo thời gian.
ROW_NUMBER() OVER (
    PARTITION BY khu_vuc
    ORDER BY ngay_giao_dich, id
)
~~~

~~~sql
-- Sắp xếp những hàng trả về của SELECT cuối.
ORDER BY khu_vuc DESC, id DESC
~~~

Bạn có thể đánh số theo **ngày tăng dần** nhưng hiển thị các hàng theo **ID giảm dần**:

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich ASC, id ASC
    ) AS stt_theo_ngay
FROM wc_giao_dich
ORDER BY khu_vuc DESC, id DESC;
~~~

Ví dụ ở khu vực Bắc, dòng 105 có `stt_theo_ngay = 5` nhưng có thể xuất hiện trước 104 và 103 trong phần hiển thị theo ID giảm dần.

**Cửa sổ tính toán theo trật tự nào** và **kết quả cuối hiển thị theo trật tự nào** là hai yêu cầu độc lập. Nếu câu SELECT ngoài không có ORDER BY, SQL không bảo đảm thứ tự hiển thị, kể cả khi các hàm cửa sổ có ORDER BY nội bộ.

### 6.3. Có thể dùng ASC, DESC và nhiều khóa

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY khu_vuc
    ORDER BY so_tien DESC NULLS LAST, id ASC
)
~~~

Ở PostgreSQL, đoạn này đánh số giao dịch có tiền lớn nhất trước trong từng khu vực; các giao dịch có tiền NULL được đưa về cuối; khi trùng tiền, ID nhỏ hơn đứng trước.

Tùy DBMS, `NULLS FIRST`/`NULLS LAST` có thể không được hỗ trợ cùng cú pháp. Một giải pháp khi cần biểu diễn cách xếp NULL rõ ràng là dùng khóa CASE:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY khu_vuc
    ORDER BY
        CASE WHEN so_tien IS NULL THEN 1 ELSE 0 END,
        so_tien DESC,
        id
)
~~~

Các biểu thức này dùng được trong danh sách SELECT của truy vấn hoàn chỉnh. Chúng tạo một **khóa thứ tự**, không lọc các giao dịch có NULL.

## 7. ORDER BY có thể thay đổi SUM: tổng lũy kế

Đây là phần quan trọng nhất khi tìm hiểu cấu trúc OVER.

### 7.1. Không có ORDER BY: tổng toàn partition

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
    ) AS tong_khu_vuc
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Với mọi giao dịch Bắc, `tong_khu_vuc = 500`; với mọi giao dịch Nam cũng bằng 500. Không có thứ tự để xây dựng tổng lũy kế từng thời điểm; hàm SUM xem toàn bộ partition làm phạm vi tổng hợp.

### 7.2. Có ORDER BY: mặc định thường là frame lũy kế

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich
    ) AS tong_theo_ngay
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Trong **PostgreSQL**, khi có ORDER BY nhưng không viết frame, frame mặc định của các hàm dùng frame có ngữ nghĩa tương đương:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Cần hiểu từ `CURRENT ROW` trong chế độ `RANGE`: frame kéo dài **qua tất cả các hàng ngang hàng (*peers*) có cùng khóa ORDER BY với dòng hiện tại**, không nhất thiết chỉ tới đúng dòng vật lý đang xét.

Vì hai giao dịch Bắc cùng ngày 03/10, khi ORDER BY **chỉ theo ngày**, cả 102 và 103 nằm trong cùng nhóm peers. Tổng của cả ngày 03/10 đã xuất hiện ở cả hai hàng.

### 7.3. Kết quả frame mặc định khi ngày trùng

Các hàng Bắc:

| id | ngay_giao_dich | so_tien | SUM mặc định khi ORDER BY ngày |
|---:|---|---:|---:|
| 101 | 2026-10-01 | 100 | 100 |
| 102 | 2026-10-03 | 200 | 450 |
| 103 | 2026-10-03 | 150 | 450 |
| 104 | 2026-10-05 | NULL | 450 |
| 105 | 2026-10-07 | 50 | 500 |

Tại ngày 03/10:

\[
100 + 200 + 150 = 450
\]

Cả 102 và 103 nhận 450, vì **RANGE theo ngày** xét cả các hàng có ngày 03/10. Điều này có thể hợp lý khi muốn tổng lũy kế **đến hết ngày**, nhưng có thể gây bất ngờ nếu bạn muốn tổng lũy kế **sau mỗi giao dịch theo ID**.

Khu vực Nam:

| id | ngay_giao_dich | so_tien | SUM mặc định theo ngày |
|---:|---|---:|---:|
| 201 | 2026-10-02 | 300 | 300 |
| 202 | 2026-10-03 | 100 | 500 |
| 203 | 2026-10-03 | 100 | 500 |
| 204 | 2026-10-06 | 0 | 500 |
| 205 | 2026-10-08 | NULL | 500 |

Ở khu vực Trung, cả hai dòng có số tiền NULL nên các tổng lũy kế SUM vẫn NULL.

## 8. ROWS: lũy kế theo từng hàng với thứ tự xác định

Nếu yêu cầu là **sau mỗi giao dịch, tổng đã ghi nhận tới dòng ấy**, hãy dùng `ROWS` cùng một thứ tự có khóa phá hòa.

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich ASC, id ASC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke_theo_giao_dich
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Giải thích:

- `PARTITION BY khu_vuc`: mỗi khu vực có tổng riêng.
- `ORDER BY ngay_giao_dich, id`: xác định vị trí giao dịch theo ngày rồi ID.
- `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`: lấy tất cả những hàng từ **đầu partition đến đúng hàng hiện tại** trong thứ tự trên.
- `SUM(so_tien)`: cộng các số tiền không NULL trong frame ấy.

Kết quả Bắc:

| id | so_tien | tong_luy_ke_theo_giao_dich |
|---:|---:|---:|
| 101 | 100 | 100 |
| 102 | 200 | 300 |
| 103 | 150 | 450 |
| 104 | NULL | 450 |
| 105 | 50 | 500 |

Kết quả Nam:

| id | so_tien | tong_luy_ke_theo_giao_dich |
|---:|---:|---:|
| 201 | 300 | 300 |
| 202 | 100 | 400 |
| 203 | 100 | 500 |
| 204 | 0 | 500 |
| 205 | NULL | 500 |

### 8.1. Tại sao ROWS khác RANGE?

`ROWS` xác định frame theo **vị trí hàng** trong thứ tự window. `RANGE` xác định frame theo **giá trị khóa ORDER BY** và nhóm peers, với các quy tắc khác nhau tùy frame được khai báo.

Ở Bắc, hai giao dịch 102/103 cùng ngày:

- `RANGE ... CURRENT ROW` với `ORDER BY ngay_giao_dich`: cả hai cùng nhận tổng **450**.
- `ROWS ... CURRENT ROW` với `ORDER BY ngay_giao_dich, id`: giao dịch 102 nhận **300**, 103 nhận **450**.

Không phải RANGE “sai” hay ROWS “đúng” trong mọi bài. Hai kiểu frame phù hợp hai định nghĩa **“tính đến hiện tại”** khác nhau.

### 8.2. Có ORDER BY id nhưng không viết ROWS thì sao?

Khi `ORDER BY ngay_giao_dich, id`, cặp khóa là duy nhất vì ID duy nhất; mỗi dòng không còn peer khác cùng **toàn bộ khóa ORDER BY**. Vì thế, trong **bộ dữ liệu hiện tại**, frame RANGE mặc định có thể cho kết quả giống ROWS lũy kế.

Tuy nhiên, viết tường minh:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

giúp thể hiện rõ ý định **lũy kế theo hàng**, giảm sự lệ thuộc vào việc người đọc phải nhớ frame mặc định hoặc các khóa sắp xếp có luôn duy nhất hay không.

### 8.3. Giá trị NULL trong tổng lũy kế

`SUM` bỏ qua `NULL` khi cộng. Vì vậy, ở giao dịch Bắc 104 số tiền NULL, tổng lũy kế tiếp tục bằng 450. Giá trị NULL **không làm tổng trở về NULL** nếu frame đã có giá trị số trước đó.

Nhưng với khu vực Trung, cả 301 và 302 đều có tiền NULL; không frame nào có giá trị tiền không NULL, nên `SUM` trả NULL tại cả hai dòng.

Nếu yêu cầu **chỉ là hiển thị số 0 cho frame chưa có số tiền**, có thể dùng:

~~~sql
COALESCE(
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    0
) AS tong_luy_ke_hien_thi
~~~

Nhưng điều đó xóa khác biệt giữa “không có giá trị để cộng” và “đã có tổng thực bằng 0”. Cần quyết định dựa trên ý nghĩa chỉ số.

## 9. Frame là gì và vì sao cần phân biệt với partition?

Một cách nhìn ba lớp:

~~~text
Tập đầu vào của SELECT
       │
       ▼
PARTITION BY
  Bắc | Nam | Trung          ← chia thành các partition
       │
       ▼
ORDER BY trong OVER          ← xếp thứ tự trong từng partition
       │
       ▼
Window frame                 ← chọn các hàng tham gia phép tính
  cho mỗi dòng hiện tại
       │
       ▼
SUM / AVG / FIRST_VALUE / ...
~~~

**Partition** là toàn bộ nhóm do `PARTITION BY` xác định. **Frame** là tập con được xác định tương ứng với dòng hiện tại, theo frame specification và thứ tự.

Một partition 5 hàng có thể sinh:

- Frame 5 hàng ở mọi dòng, nếu hàm tính trên cả partition.
- Frame 1, 2, 3, 4, 5 hàng ở các vị trí khi lũy kế theo ROWS.
- Frame 3 hàng trượt liên tiếp ở những vị trí đủ hàng.
- Frame thay đổi theo nhóm peers khi dùng RANGE hoặc GROUPS.

### 9.1. Cấu trúc ROWS BETWEEN

~~~sql
ROWS BETWEEN frame_start AND frame_end
~~~

Một số giới hạn thường gặp:

| Cú pháp | Ý nghĩa trong thứ tự cửa sổ |
|---|---|
| `UNBOUNDED PRECEDING` | Từ đầu partition |
| `n PRECEDING` | Cách hiện tại n hàng về phía trước |
| `CURRENT ROW` | Hàng hiện tại đối với ROWS |
| `n FOLLOWING` | Cách hiện tại n hàng về phía sau |
| `UNBOUNDED FOLLOWING` | Đến cuối partition |

Ví dụ lũy kế:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Ví dụ cửa sổ trượt ba hàng gồm hiện tại và hai hàng trước:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

Ví dụ cả partition trong một thứ tự đã khai báo:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

Không phải mọi cách kết hợp các điểm đầu/cuối đều hợp lệ; cần dùng thứ tự điểm đầu và điểm cuối có ý nghĩa theo cú pháp DBMS.

### 9.2. Trung bình trượt ba giao dịch

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    so_tien,
    AVG(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS avg_3_giao_dich
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Với Bắc:

| id | Các giao dịch trong frame | Giá trị có tiền | AVG |
|---:|---|---|---:|
| 101 | 101 | 100 | 100 |
| 102 | 101–102 | 100, 200 | 150 |
| 103 | 101–103 | 100, 200, 150 | 150 |
| 104 | 102–104 | 200, 150, NULL | 175 |
| 105 | 103–105 | 150, NULL, 50 | 100 |

Ở dòng 104, frame có **ba giao dịch** nhưng chỉ **hai giá trị tiền không NULL**, nên AVG là (200 + 150)/2 = **175**. Không chia cho 3 trừ khi bạn cố ý thay NULL thành 0 trước khi tính AVG.

### 9.3. ROWS khác “ba ngày lịch gần nhất”

`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` nghĩa là **tối đa ba hàng trong thứ tự**, không phải ba ngày trước tới hôm nay.

Nếu trong một ngày có hàng trăm giao dịch, frame ba hàng có thể chỉ chứa giao dịch của cùng ngày. Nếu bạn cần khoảng thời gian thực như “từ hai ngày trước đến hôm nay”, hãy thiết kế theo ngày, cú pháp RANGE với offset thích hợp hoặc bảng lịch/tổng hợp ngày, tùy DBMS và định nghĩa nghiệp vụ.

### 9.4. RANGE và GROUPS

Trong PostgreSQL hiện đại, `RANGE` và `GROUPS` là hai loại frame khác:

- `RANGE` xét **giá trị của khóa ORDER BY**, và khi có peers, các hàng ngang hàng thường cùng được đưa vào frame ở ranh giới tương ứng.
- `GROUPS` đếm các **nhóm peers**, tức nhóm các hàng có cùng khóa sắp xếp, thay vì đếm từng hàng.
- `ROWS` đếm **vị trí hàng**.

Ví dụ với các ngày giao dịch của Bắc:

~~~sql
SUM(so_tien) OVER (
    PARTITION BY khu_vuc
    ORDER BY ngay_giao_dich
    GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
)
~~~

Ở ngày 05/10, frame gồm **nhóm ngày 03/10** và **nhóm ngày 05/10**, nên cộng 200 + 150 + NULL = **350**; không gồm ngày 01/10. `GROUPS 1 PRECEDING` nghĩa là **nhóm ngày có dữ liệu đứng liền trước**, không phải “một ngày lịch trước”.

Tính khả dụng và cú pháp RANGE/GROUPS khác nhau theo DBMS/phiên bản. Để bắt đầu và cần lũy kế theo từng giao dịch, `ROWS` với khóa phá hòa duy nhất là lựa chọn dễ hiểu.

## 10. ROW_NUMBER, RANK và DENSE_RANK: ORDER BY quyết định hạng

Các hàm xếp hạng làm rõ một tác dụng khác của `ORDER BY` trong `OVER`: chúng không tính tổng, mà gán **vị trí/hạng** theo một quy tắc.

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC NULLS LAST, id
    ) AS so_thu_tu,
    RANK() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC NULLS LAST
    ) AS hang_co_khoang_trong,
    DENSE_RANK() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC NULLS LAST
    ) AS hang_lien_tiep
FROM wc_giao_dich
ORDER BY khu_vuc, so_tien DESC NULLS LAST, id;
~~~

Với Nam:

| id | so_tien | so_thu_tu | hang_co_khoang_trong | hang_lien_tiep |
|---:|---:|---:|---:|---:|
| 201 | 300 | 1 | 1 | 1 |
| 202 | 100 | 2 | 2 | 2 |
| 203 | 100 | 3 | 2 | 2 |
| 204 | 0 | 4 | 4 | 3 |
| 205 | NULL | 5 | 5 | 4 |

### 10.1. Ba kiểu đánh số không giống nhau

- **`ROW_NUMBER()`**: số thứ tự duy nhất cho mỗi hàng trong partition; 202 và 203 nhận 2 và 3 nhờ `id` phá hòa.
- **`RANK()`**: các hàng đồng hạng cùng số; sau hai hàng hạng 2, hạng tiếp theo là **4** (có khoảng trống).
- **`DENSE_RANK()`**: các hàng đồng hạng cùng số nhưng hạng tiếp theo là **3** (không có khoảng trống).

### 10.2. Vì sao không thêm id vào ORDER BY của RANK?

Xét:

~~~sql
RANK() OVER (
    PARTITION BY khu_vuc
    ORDER BY so_tien DESC NULLS LAST, id
)
~~~

Khi thêm `id` duy nhất vào danh sách ORDER BY, hai hàng có cùng tiền 100 nhưng khác ID **không còn peers** theo toàn bộ khóa. Cả hai có thể bị xếp hạng khác nhau, làm mất mục tiêu “cùng số tiền thì cùng hạng”.

Vì vậy:

- Với **ROW_NUMBER** để chọn một hàng xác định: thường thêm khóa phá hòa `id`.
- Với **RANK/DENSE_RANK** để bảo toàn quan hệ đồng hạng theo số tiền: chỉ ORDER BY các tiêu chí **định nghĩa hạng**, không thêm khóa chỉ nhằm làm duy nhất nếu nó không thuộc định nghĩa hạng.

### 10.3. NULL cũng được xếp theo thứ tự khai báo

Ở khu vực Trung, cả hai giao dịch có `so_tien = NULL`. Với `ORDER BY so_tien DESC NULLS LAST` trong PostgreSQL, chúng là peers và cùng nhận hạng 1 theo `RANK` và `DENSE_RANK`, mặc dù không có giá trị tiền thực để so.

Nếu nghiệp vụ không muốn xếp hạng các giao dịch thiếu tiền, có thể lọc chúng trước khi xếp hạng hoặc dùng CASE để trả hạng NULL cho những dòng thiếu tiền. Hai lựa chọn có tác động khác nhau đến tập được đánh số, nên cần nói rõ quy tắc báo cáo.

## 11. LAG và LEAD: xem hàng trước/sau trong cùng partition

`LAG` và `LEAD` là các hàm hữu ích để so sánh các hàng theo thứ tự thời gian:

- `LAG(bieu_thuc)`: lấy giá trị của hàng **đứng trước** theo ORDER BY của cửa sổ.
- `LEAD(bieu_thuc)`: lấy giá trị của hàng **đứng sau**.
- Cả hai thường nhận thêm đối số khoảng cách và giá trị mặc định.

Ví dụ:

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    so_tien,
    LAG(id) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
    ) AS id_giao_dich_truoc,
    LAG(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
    ) AS tien_truoc,
    LEAD(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
    ) AS tien_sau
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Một phần kết quả Bắc:

| id | so_tien | id_giao_dich_truoc | tien_truoc | tien_sau |
|---:|---:|---:|---:|---:|
| 101 | 100 | NULL | NULL | 200 |
| 102 | 200 | 101 | 100 | 150 |
| 103 | 150 | 102 | 200 | NULL |
| 104 | NULL | 103 | 150 | 50 |
| 105 | 50 | 104 | NULL | NULL |

### 11.1. LAG trả NULL có hai nguyên nhân khác nhau

Ở 101, `LAG(so_tien)` trả NULL vì **không có hàng đứng trước**.

Ở 105, `LAG(so_tien)` cũng NULL, nhưng vì hàng đứng trước là giao dịch **104 có so_tien NULL**. Có hàng trước, chỉ là giá trị của hàng ấy chưa biết.

Nếu cần phân biệt, lấy thêm `LAG(id)` như ví dụ: ở 105, ID trước là 104; ở 101, ID trước NULL.

### 11.2. Giá trị mặc định của LAG không thay mọi NULL nguồn

Ví dụ:

~~~sql
LAG(so_tien, 1, 0) OVER (
    PARTITION BY khu_vuc
    ORDER BY ngay_giao_dich, id
)
~~~

Đối số `0` là **giá trị mặc định khi không có hàng ở vị trí được yêu cầu**; nó **không tự thay NULL thực sự lưu trên hàng trước**. Vì thế ở 101 kết quả mặc định có thể là 0, nhưng ở 105 vẫn là NULL do giao dịch 104 có số tiền NULL.

Nếu viết `COALESCE(LAG(so_tien) OVER (...), 0)` thì cả hai loại NULL đều thành 0; đó là một quyết định hiển thị khác và có thể che mất tình trạng thiếu số liệu.

### 11.3. ORDER BY quan trọng với LAG/LEAD

Không có thứ tự giao dịch rõ ràng, khái niệm “hàng trước” hoặc “hàng sau” không có ý nghĩa nghiệp vụ ổn định. Với dữ liệu trùng ngày, hãy thêm tiêu chí phá hòa mà doanh nghiệp chấp nhận, ví dụ ID hay thời điểm đến mức chi tiết hơn.

## 12. FIRST_VALUE và LAST_VALUE: cẩn trọng với frame

`FIRST_VALUE` lấy giá trị ở **hàng đầu tiên của frame**, `LAST_VALUE` lấy giá trị ở **hàng cuối cùng của frame**. Khác với cách nhiều người hình dung, `LAST_VALUE` không tự động trả “giá trị cuối của toàn partition” nếu frame mặc định chỉ kết thúc tại hàng hiện tại.

### 12.1. LAST_VALUE với frame mặc định

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    LAST_VALUE(id) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
    ) AS last_id_mac_dinh
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Với Bắc, vì `ORDER BY ngay_giao_dich, id` là duy nhất, frame RANGE mặc định kết thúc tại chính dòng hiện tại, nên `last_id_mac_dinh` lần lượt là **101, 102, 103, 104, 105**.

Nhiều người mong mọi dòng Bắc đều trả **105** và tưởng hàm sai. Thực tế, họ chưa xác định frame tới cuối partition.

### 12.2. Chỉ rõ frame bao trùm toàn partition

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    FIRST_VALUE(id) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS id_dau_tien,
    LAST_VALUE(id) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS id_cuoi_cung
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Kết quả theo khu vực:

| khu_vuc | id_dau_tien ở mọi dòng vùng | id_cuoi_cung ở mọi dòng vùng |
|---|---:|---:|
| Bắc | 101 | 105 |
| Nam | 201 | 205 |
| Trung | 301 | 302 |

`ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` bao gồm cả partition, nên FIRST_VALUE và LAST_VALUE nhìn thấy dòng đầu/cuối thực sự của partition theo thứ tự thời gian đã khai báo.

### 12.3. Không nên suy ra “cuối cùng” từ MAX(id) một cách tùy tiện

Trong bộ dữ liệu mẫu, ID tăng cùng ngày nên kết quả cuối tình cờ trùng ID lớn nhất. Nhưng trong hệ thống thật, ID không nhất thiết phản ánh thời gian. Nếu yêu cầu giao dịch mới nhất, dùng **`ORDER BY ngay_giao_dich DESC, id DESC`** hoặc tiêu chí thời gian phù hợp rồi xác định frame và cách lấy hàng theo mục đích.

## 13. Cùng một SELECT có thể chứa nhiều cửa sổ khác nhau

Một báo cáo có thể đồng thời hiển thị tổng vùng, tổng toàn hệ thống, hạng theo số tiền và tổng lũy kế theo ngày:

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    so_tien,

    SUM(so_tien) OVER () AS tong_toan_bo,

    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
    ) AS tong_khu_vuc,

    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC NULLS LAST, id
    ) AS thu_tu_theo_tien,

    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke

FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Cùng một dòng có thể thuộc các **cửa sổ khác nhau** tùy biểu thức:

- `SUM(...) OVER ()`: mọi khu vực, tổng 1000.
- `SUM(...) OVER (PARTITION BY khu_vuc)`: tổng vùng, Bắc/Nam bằng 500.
- `ROW_NUMBER(...) OVER (PARTITION BY khu_vuc ORDER BY so_tien DESC ...)`: thứ tự theo **tiền** trong vùng.
- `SUM(...) OVER (PARTITION BY khu_vuc ORDER BY ngay_giao_dich, id ROWS ...)`: tổng lũy kế theo **ngày**.

Không có yêu cầu các hàm cửa sổ trong cùng SELECT phải dùng chung PARTITION BY hay ORDER BY.

### 13.1. Mỗi cột có nghĩa độc lập

Giả sử giao dịch Bắc 102 có tiền 200, là giao dịch lớn nhất Bắc, nên `thu_tu_theo_tien = 1`. Nhưng vì ngày của nó là 03/10, sau giao dịch 101, tổng lũy kế theo ngày/ID tại 102 bằng **300**. Cột hạng và cột lũy kế dùng **hai thứ tự khác nhau**, nên không có mâu thuẫn.

### 13.2. Khi nào nhiều cửa sổ làm câu SQL khó đọc?

Nếu cùng câu SELECT lặp đi lặp lại phần `PARTITION BY khu_vuc ORDER BY ngay_giao_dich, id` dài nhiều lần, PostgreSQL hỗ trợ khai báo **cửa sổ có tên** bằng mệnh đề `WINDOW`. Phần tiếp theo trình bày cách dùng.

## 14. Cửa sổ có tên với WINDOW

Cú pháp PostgreSQL:

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    COUNT(*) OVER w_khu_vuc AS so_giao_dich_vung,
    SUM(so_tien) OVER w_khu_vuc AS tong_vung,
    SUM(so_tien) OVER w_luy_ke AS tong_luy_ke
FROM wc_giao_dich
WINDOW
    w_khu_vuc AS (
        PARTITION BY khu_vuc
    ),
    w_luy_ke AS (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Lợi ích:

- Tên `w_khu_vuc` mô tả cửa sổ chỉ phân theo khu vực.
- Tên `w_luy_ke` mô tả cửa sổ có thứ tự và frame để tính lũy kế.
- Các hàm cùng dùng một cấu hình cửa sổ không cần chép nguyên phần `OVER(...)`.
- Khi đổi quy tắc frame, có thể sửa ở phần định nghĩa có tên.

### 14.1. Vị trí mệnh đề WINDOW

Trong một SELECT PostgreSQL đơn giản, `WINDOW` đứng sau các mệnh đề lọc/nhóm như WHERE, GROUP BY, HAVING (nếu có), và trước `ORDER BY` cuối cùng.

Ví dụ tổng quát:

~~~sql
SELECT
    ...,
    SUM(cot) OVER w AS ket_qua
FROM bang
WHERE dieu_kien
WINDOW w AS (PARTITION BY nhom)
ORDER BY ...;
~~~

Đây là cấu trúc minh họa; thay `...`, `bang`, `cot` và `nhom` bằng nguồn thực tế.

### 14.2. Khác biệt với CTE

CTE đặt tên **tập hàng trung gian**; `WINDOW` đặt tên **cấu hình cửa sổ** trong một SELECT. Chúng giải quyết hai loại lặp khác nhau:

- `WITH ban_da_loc AS (...)`: định nghĩa dữ liệu mà SELECT sẽ sử dụng.
- `WINDOW w AS (PARTITION BY ...)`: định nghĩa phạm vi tính cho các hàm cửa sổ.

Một câu SQL có thể dùng **cả CTE và WINDOW**:

~~~sql
WITH giao_dich_co_tien AS (
    SELECT *
    FROM wc_giao_dich
    WHERE so_tien IS NOT NULL
)
SELECT
    id,
    khu_vuc,
    so_tien,
    SUM(so_tien) OVER w AS tong_vung
FROM giao_dich_co_tien
WINDOW w AS (PARTITION BY khu_vuc)
ORDER BY khu_vuc, id;
~~~

Lưu ý: vì CTE đã loại các hàng NULL, SELECT ngoài chỉ còn **8 giao dịch**, không còn 12. Đây là thay đổi **tập hàng**, không phải thay đổi cú pháp window.

## 15. Tính tỷ trọng từng giao dịch trong khu vực

Yêu cầu: mỗi dòng hiển thị **số tiền giao dịch chiếm bao nhiêu phần trăm tổng tiền khu vực**.

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
    ) AS tong_vung,
    ROUND(
        100.0 * so_tien
        / NULLIF(
            SUM(so_tien) OVER (PARTITION BY khu_vuc),
            0
        ),
        2
    ) AS ty_trong_phan_tram
FROM wc_giao_dich
ORDER BY khu_vuc, id;
~~~

Kết quả một số dòng:

| id | khu_vuc | so_tien | tong_vung | ty_trong_phan_tram |
|---:|---|---:|---:|---:|
| 101 | Bắc | 100 | 500 | 20.00 |
| 102 | Bắc | 200 | 500 | 40.00 |
| 103 | Bắc | 150 | 500 | 30.00 |
| 105 | Bắc | 50 | 500 | 10.00 |
| 201 | Nam | 300 | 500 | 60.00 |
| 202 | Nam | 100 | 500 | 20.00 |
| 203 | Nam | 100 | 500 | 20.00 |
| 204 | Nam | 0 | 500 | 0.00 |
| 301 | Trung | NULL | NULL | NULL |

Ý nghĩa các phép xử lý:

- `SUM(so_tien) OVER (PARTITION BY khu_vuc)` là **mẫu số** theo khu vực.
- `100.0 * so_tien` tạo tử số ở thang phần trăm và hỗ trợ phép chia có phần thập phân phù hợp trong PostgreSQL.
- `NULLIF(tong_vung, 0)` đổi mẫu số bằng 0 thành NULL để tránh chia cho 0.
- `ROUND(..., 2)` làm tròn tới hai chữ số thập phân trong PostgreSQL.

Với khu vực Trung, mẫu số SUM là NULL vì không có giá trị tiền; tỷ trọng cũng NULL. Với giao dịch 204 có tiền đúng bằng 0 nhưng tổng vùng Nam bằng 500, tỷ trọng là **0.00%** — một giá trị có thể tính được.

Nếu muốn tránh viết lại biểu thức SUM trong SELECT, có thể tạo CTE trung gian chứa `tong_vung` rồi tính tỷ trọng ở SELECT ngoài. Đây là cách hữu ích khi có nhiều chỉ số dùng lại cùng tổng.

## 16. Hàm cửa sổ và WHERE: thứ tự xử lý logic

Một nguyên tắc quan trọng: **WHERE lọc hàng trước khi các hàm cửa sổ của SELECT cùng cấp được tính** theo mô hình xử lý logic SQL.

### 16.1. Lọc chỉ giao dịch có số tiền sẽ thay đổi partition

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    COUNT(*) OVER (
        PARTITION BY khu_vuc
    ) AS so_hang_vung
FROM wc_giao_dich
WHERE so_tien IS NOT NULL
ORDER BY khu_vuc, id;
~~~

Ở đây:

- Bắc còn **4 dòng**, không phải 5.
- Nam còn **4 dòng**, không phải 5.
- Trung không còn dòng nào vì cả hai số tiền NULL.

Các hàm cửa sổ chỉ nhìn thấy tập đã qua `WHERE` của truy vấn hiện tại. Vì vậy, `COUNT(*) OVER (PARTITION BY khu_vuc)` trả 4 ở Bắc/Nam chứ không phải 5.

### 16.2. Muốn tính tổng trên toàn bộ rồi chỉ hiển thị một phần?

Dùng CTE hoặc bảng dẫn xuất để **tính trước, lọc sau**:

~~~sql
WITH da_tinh AS (
    SELECT
        id,
        khu_vuc,
        so_tien,
        COUNT(*) OVER (
            PARTITION BY khu_vuc
        ) AS so_hang_vung,
        SUM(so_tien) OVER (
            PARTITION BY khu_vuc
        ) AS tong_vung
    FROM wc_giao_dich
)
SELECT *
FROM da_tinh
WHERE so_tien IS NOT NULL
ORDER BY khu_vuc, id;
~~~

Kết quả chỉ hiển thị **8 dòng có tiền**, nhưng `so_hang_vung` ở Bắc/Nam vẫn là **5**, vì window ở CTE đã tính trên tập 12 dòng trước khi SELECT ngoài lọc.

Đây không chỉ là khác biệt về cú pháp mà còn là khác biệt **định nghĩa chỉ số**:

- “Số giao dịch có tiền trong khu vực” → lọc NULL trước rồi COUNT.
- “Số giao dịch tổng cộng trong khu vực, chỉ hiển thị những giao dịch có tiền” → tính cửa sổ trước, lọc kết quả ngoài.

### 16.3. Không thể lọc trực tiếp bằng ROW_NUMBER trong WHERE cùng cấp

Câu dưới không hợp lệ trong PostgreSQL:

~~~sql
SELECT
    id,
    khu_vuc,
    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich DESC, id DESC
    ) AS rn
FROM wc_giao_dich
WHERE rn = 1;
~~~

`WHERE` không dùng được bí danh cửa sổ `rn` mới tính ở SELECT cùng cấp. Cũng không thể đặt trực tiếp hàm cửa sổ ở WHERE cùng cấp như một điều kiện bình thường.

Cách đúng là **tính hạng ở CTE, lọc ở truy vấn ngoài**:

~~~sql
WITH xep_hang AS (
    SELECT
        id,
        khu_vuc,
        ngay_giao_dich,
        ROW_NUMBER() OVER (
            PARTITION BY khu_vuc
            ORDER BY ngay_giao_dich DESC, id DESC
        ) AS rn
    FROM wc_giao_dich
)
SELECT id, khu_vuc, ngay_giao_dich
FROM xep_hang
WHERE rn = 1
ORDER BY khu_vuc;
~~~

Kết quả:

| id | khu_vuc | ngay_giao_dich |
|---:|---|---|
| 105 | Bắc | 2026-10-07 |
| 205 | Nam | 2026-10-08 |
| 302 | Trung | 2026-10-04 |

**Lưu ý:** giao dịch mới nhất của Nam và Trung có `so_tien = NULL`, nhưng bài này hỏi **giao dịch mới nhất**, không phải **giao dịch mới nhất có tiền**.

Nếu chỉ muốn xét những giao dịch đã có tiền, đặt `WHERE so_tien IS NOT NULL` trong CTE **trước khi tính ROW_NUMBER**:

~~~sql
WITH xep_hang AS (
    SELECT
        id,
        khu_vuc,
        ngay_giao_dich,
        so_tien,
        ROW_NUMBER() OVER (
            PARTITION BY khu_vuc
            ORDER BY ngay_giao_dich DESC, id DESC
        ) AS rn
    FROM wc_giao_dich
    WHERE so_tien IS NOT NULL
)
SELECT id, khu_vuc, so_tien
FROM xep_hang
WHERE rn = 1
ORDER BY khu_vuc;
~~~

Kết quả chỉ có Bắc 105 (50) và Nam 204 (0). Trung không còn partition trong tập đầu vào vì không có giao dịch có tiền.

## 17. GROUP BY, HAVING và cửa sổ có thể dùng cùng nhau

Hàm cửa sổ không chỉ hoạt động trên bảng giao dịch thô. Nó cũng có thể hoạt động trên kết quả **đã tổng hợp theo GROUP BY**, ví dụ tính doanh thu từng ngày rồi tính tổng lũy kế các ngày.

### 17.1. Bước 1: tổng hợp theo ngày trong từng khu vực

~~~sql
SELECT
    khu_vuc,
    ngay_giao_dich,
    COUNT(*) AS so_giao_dich,
    SUM(so_tien) AS tong_tien_ngay
FROM wc_giao_dich
GROUP BY khu_vuc, ngay_giao_dich
ORDER BY khu_vuc, ngay_giao_dich;
~~~

Ví dụ Bắc:

| ngay_giao_dich | so_giao_dich | tong_tien_ngay |
|---|---:|---:|
| 2026-10-01 | 1 | 100 |
| 2026-10-03 | 2 | 350 |
| 2026-10-05 | 1 | NULL |
| 2026-10-07 | 1 | 50 |

Khác với dữ liệu 5 giao dịch, bảng kết quả theo ngày của Bắc có **4 hàng** vì hai giao dịch 03/10 đã được nhóm lại.

### 17.2. Bước 2: tổng lũy kế theo những ngày đã tổng hợp

~~~sql
WITH theo_ngay AS (
    SELECT
        khu_vuc,
        ngay_giao_dich,
        COUNT(*) AS so_giao_dich,
        SUM(so_tien) AS tong_tien_ngay
    FROM wc_giao_dich
    GROUP BY khu_vuc, ngay_giao_dich
)
SELECT
    khu_vuc,
    ngay_giao_dich,
    so_giao_dich,
    tong_tien_ngay,
    SUM(tong_tien_ngay) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke_den_ngay
FROM theo_ngay
ORDER BY khu_vuc, ngay_giao_dich;
~~~

Với Bắc, tổng lũy kế theo ngày lần lượt **100, 450, 450, 500**.

### 17.3. Tại sao nên dùng CTE theo ngày?

Vì yêu cầu là **một hàng trên mỗi ngày–khu vực**, không phải một hàng trên mỗi giao dịch. CTE `theo_ngay` làm rõ cấp chi tiết trước khi áp dụng window. Truy vấn cuối xử lý một tập đã nhóm, giúp tránh việc nhầm “lũy kế theo giao dịch” với “lũy kế cuối mỗi ngày”.

Có thể viết một số kết hợp aggregate và window trong cùng SELECT GROUP BY bằng biểu thức dạng `SUM(SUM(so_tien)) OVER (...)` trên PostgreSQL, nhưng cách chia CTE thường dễ giải thích khi mới học.

### 17.4. HAVING và các hàng vào cửa sổ

Trong mô hình logic, cửa sổ của cùng SELECT được tính **sau bước WHERE, GROUP BY và HAVING**. Nếu HAVING loại một nhóm ngày vì không đạt ngưỡng, cửa sổ của SELECT cùng cấp chỉ hoạt động trên những nhóm còn lại.

Muốn **tính lũy kế trên tất cả ngày rồi chỉ hiển thị ngày đạt một ngưỡng**, hãy tính lũy kế trong CTE, sau đó lọc ở SELECT ngoài. Cách đặt bước lọc quyết định ý nghĩa của tổng lũy kế.

## 18. PARTITION BY và ORDER BY có bắt buộc cùng xuất hiện?

Không. Phụ thuộc loại hàm và kết quả cần tính.

| Mẫu | Khi thường dùng | Lưu ý |
|---|---|---|
| `SUM(x) OVER ()` | Tổng toàn tập gắn trên từng dòng | Không phân vùng, không thứ tự |
| `SUM(x) OVER (PARTITION BY nhom)` | Tổng nhóm gắn trên từng dòng | Toàn partition thường tham gia |
| `SUM(x) OVER (ORDER BY ngay, id ROWS ...)` | Tổng lũy kế toàn tập | Không chia partition, lũy kế xuyên mọi khu vực |
| `SUM(x) OVER (PARTITION BY nhom ORDER BY ngay, id ROWS ...)` | Tổng lũy kế riêng từng nhóm | Bắt đầu lại tại mỗi partition |
| `ROW_NUMBER() OVER (PARTITION BY nhom ORDER BY ngay, id)` | Đánh số trong nhóm | Thứ tự cần rõ để có kết quả ổn định |
| `RANK() OVER (ORDER BY diem DESC)` | Xếp hạng toàn tập | Không chia theo nhóm |
| `LAG(x) OVER (PARTITION BY nhom ORDER BY ngay, id)` | Lấy giá trị trước trong nhóm | Cần ý nghĩa “trước/sau” rõ ràng |

Một số DBMS **bắt buộc ORDER BY** đối với các hàm như ROW_NUMBER, RANK hoặc LAG. PostgreSQL cho phép một số cách gọi không có ORDER BY ở những hàm xếp hạng, nhưng thứ tự/nhóm peers khi đó có thể không có ý nghĩa nghiệp vụ. Không nên dựa vào quy tắc “cứ có OVER là dùng được không cần ORDER BY” cho mọi DBMS.

### 18.1. Không có PARTITION BY nhưng có ORDER BY

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    so_tien,
    SUM(so_tien) OVER (
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke_toan_bo
FROM wc_giao_dich
ORDER BY ngay_giao_dich, id;
~~~

Truy vấn tính tổng lũy kế **qua tất cả khu vực**, theo thứ tự ngày và ID, chứ không bắt đầu lại khi khu vực thay đổi. Nếu bạn muốn lũy kế riêng từng khu vực, cần thêm `PARTITION BY khu_vuc`.

### 18.2. Có PARTITION BY nhưng không ORDER BY

~~~sql
SELECT
    id,
    khu_vuc,
    MAX(so_tien) OVER (
        PARTITION BY khu_vuc
    ) AS tien_lon_nhat_vung
FROM wc_giao_dich
ORDER BY id;
~~~

Kết quả MAX lặp trong từng vùng: Bắc 200, Nam 300, Trung NULL. Vì không yêu cầu vị trí theo thời gian nên không cần ORDER BY trong OVER.

## 19. Một số tình huống nâng cao với frame

### 19.1. Tính tổng trên toàn partition dù có ORDER BY

Nếu bạn muốn thứ tự có mặt vì dùng các hàm khác, nhưng SUM vẫn tính **toàn bộ partition**, đừng để mặc định lũy kế gây nhầm.

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tong_toan_vung
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Kết quả với Bắc/Nam vẫn là 500 trên mọi hàng, Trung NULL. Frame đã được mở rộng **đến cả cuối partition** thay vì dừng tại dòng hiện tại.

Cách đơn giản hơn trong ví dụ chỉ cần SUM toàn vùng vẫn là bỏ ORDER BY:

~~~sql
SUM(so_tien) OVER (PARTITION BY khu_vuc)
~~~

### 19.2. Tổng ba hàng trượt

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS tong_3_hang
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Ở Bắc:

| id | Các ID trong frame | tong_3_hang |
|---:|---|---:|
| 101 | 101 | 100 |
| 102 | 101, 102 | 300 |
| 103 | 101, 102, 103 | 450 |
| 104 | 102, 103, 104 | 350 |
| 105 | 103, 104, 105 | 200 |

Frame của 105 không còn 101/102 dù hai dòng ấy cùng partition Bắc, vì ta chỉ yêu cầu **hai hàng trước cộng hàng hiện tại**.

### 19.3. Trung bình tới thời điểm hiện tại

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    AVG(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS avg_luy_ke
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

Bắc lần lượt có trung bình:

- 101: 100.
- 102: (100 + 200)/2 = 150.
- 103: (100 + 200 + 150)/3 = 150.
- 104: vẫn 150 vì giá trị NULL bị bỏ qua.
- 105: (100 + 200 + 150 + 50)/4 = 125.

Ở Trung, AVG lũy kế tiếp tục NULL do không có giá trị tiền nào khác NULL.

### 19.4. FIRST_VALUE/LAST_VALUE có thể bị ảnh hưởng bởi peers

Khi ORDER BY chỉ một cột ngày và hai hàng trùng ngày, ranh giới frame kiểu RANGE có thể bao gồm nhiều peers. Nếu muốn “dòng cuối” có nghĩa xác định, hãy đặt thứ tự đủ chi tiết (ví dụ ngày + ID) và frame phù hợp.

Với các hàm truy cập vị trí trong frame như `FIRST_VALUE`, `LAST_VALUE` và `NTH_VALUE`, việc đọc kỹ frame thường quan trọng không kém việc đọc ORDER BY.

## 20. Hiệu năng và cách tổ chức cửa sổ

Hàm cửa sổ rất tiện để tính hạng, lũy kế và tổng nhóm mà vẫn giữ từng hàng, nhưng trên bảng lớn chúng có thể cần sắp xếp, phân vùng và lưu dữ liệu tạm theo kế hoạch của optimizer.

### 20.1. Những yếu tố ảnh hưởng chi phí

- **Số hàng đầu vào** sau WHERE/GROUP BY.
- **Số partition** và kích thước partition lớn nhất.
- **Khóa ORDER BY**: có sẵn thứ tự từ index/kế hoạch hay cần sắp xếp.
- **Số cấu hình cửa sổ khác nhau**: một SELECT có nhiều PARTITION BY/ORDER BY khác nhau có thể cần nhiều cách tổ chức dữ liệu.
- **Frame**: lũy kế đơn giản, trượt, hoặc truy cập hàng cuối partition có đặc tính xử lý khác nhau.
- **Dữ liệu bị trùng khóa** và phân bố giá trị: ảnh hưởng peers và kích thước nhóm.
- **Điều kiện lọc**: có làm giảm tập đầu vào mà vẫn đúng nghiệp vụ không.

### 20.2. EXPLAIN trong PostgreSQL

~~~sql
EXPLAIN
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke
FROM wc_giao_dich;
~~~

`EXPLAIN` hiển thị kế hoạch dự kiến. Bạn có thể gặp bước `WindowAgg`, `Sort`, `Seq Scan` hoặc cách tổ chức khác, tùy phiên bản, kích thước dữ liệu, chỉ mục và các điều kiện.

`EXPLAIN ANALYZE` thực thi truy vấn để đo thực tế, nên cần cẩn trọng trong hệ thống sản xuất hoặc với statement làm thay đổi dữ liệu. Bộ dữ liệu mẫu chỉ 12 hàng; không nên suy ra tốc độ trên hàng triệu giao dịch từ ví dụ nhỏ này.

### 20.3. Index có thể hỗ trợ thứ tự nhưng không thay thế tư duy về kết quả

Với truy vấn thường xuyên phân chia theo khu vực rồi sắp theo ngày và ID, một index trên bảng thật theo các cột:

~~~sql
-- Ví dụ tùy chọn trên bảng tạm của bài học:
CREATE INDEX wc_giao_dich_vung_ngay_id_idx
ON wc_giao_dich (khu_vuc, ngay_giao_dich, id);
~~~

có thể phù hợp cho một số đường truy cập, nhưng **không bảo đảm** optimizer sẽ dùng index hay tránh mọi phép sort. Index có chi phí ghi và lưu trữ; chỉ tạo trên hệ thống thật khi đã đánh giá workload.

### 20.4. Có nhiều cửa sổ giống nhau thì làm gì?

Nếu nhiều hàm dùng chung cấu hình, có thể:

- Dùng mệnh đề `WINDOW` đặt tên cho partition và frame.
- Nhóm các chỉ số có cùng ý nghĩa trong một SELECT.
- Dùng CTE để phân chia **tập đầu vào** và **đầu ra đã tính cửa sổ**, đặc biệt khi cần lọc theo `ROW_NUMBER`.
- Giữ các điều kiện lọc ở đúng bước, không làm mất dữ liệu nền cần cho các chỉ số.

Không nên chia thành nhiều CTE chỉ vì muốn “chạy nhanh hơn”: CTE chủ yếu giúp cấu trúc rõ ràng, còn kế hoạch thực thi phụ thuộc DBMS.

## 21. Khác biệt giữa các hệ quản trị

Cấu trúc `OVER` và các ý tưởng `PARTITION BY`, `ORDER BY` xuất hiện rộng rãi trong SQL hiện đại. Nhưng hỗ trợ chi tiết của hàm, frame và thứ tự NULL khác nhau theo DBMS/phiên bản.

| Hệ quản trị | Window functions | Những điểm cần kiểm tra |
|---|---|---|
| **PostgreSQL** | Hỗ trợ rộng | `ROWS`, `RANGE`, `GROUPS` ở phiên bản phù hợp, cửa sổ có tên `WINDOW`, `NULLS FIRST/LAST`, nhiều hàm ranking/offset/value |
| **MySQL 8.0+** | Có | Các giới hạn frame theo hàm, named windows và cách NULL được sắp xếp; không nên sao chép mọi ví dụ PostgreSQL nguyên xi |
| **MariaDB** | Có trong các phiên bản phù hợp | Mức hỗ trợ hàm/frame và tối ưu khác PostgreSQL |
| **SQL Server** | Có | Một số hàm xếp hạng yêu cầu ORDER BY; không hỗ trợ `NULLS LAST` bằng cú pháp PostgreSQL; `ROWS/RANGE` có giới hạn riêng |
| **Oracle** | Có các hàm phân tích | Cú pháp analytic functions và frame phong phú; cần kiểm tra cách khai báo loại frame, NULL, alias |
| **SQLite 3.25+** | Có window functions | `WINDOW`, `ROWS/RANGE/GROUPS` trên phiên bản phù hợp; kiểu dữ liệu và các hàm phụ trợ khác PostgreSQL |

### 21.1. SQL Server: không dùng NULLS LAST kiểu PostgreSQL

Trong T-SQL, để đưa tiền NULL xuống cuối khi xếp giảm dần, có thể dùng CASE:

~~~sql
SELECT
    Id,
    KhuVuc,
    SoTien,
    ROW_NUMBER() OVER (
        PARTITION BY KhuVuc
        ORDER BY
            CASE WHEN SoTien IS NULL THEN 1 ELSE 0 END,
            SoTien DESC,
            Id
    ) AS Stt
FROM dbo.GiaoDich;
~~~

Bảng `dbo.GiaoDich` là tên minh họa cho một bảng SQL Server có cột tương ứng, không phải bảng tạm PostgreSQL `wc_giao_dich`. Điểm cần học là **chính sách xếp NULL** phải được diễn đạt rõ khi cú pháp giữa các DBMS khác nhau.

### 21.2. MySQL: một ví dụ ROW_NUMBER

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
    ) AS stt
FROM giao_dich;
~~~

Câu này minh họa cấu trúc trên MySQL 8.0+, giả sử có bảng `giao_dich`. Không phải mọi phiên bản MySQL cũ đều có window functions.

### 21.3. Oracle: analytic SUM

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke
FROM giao_dich;
~~~

Về ý nghĩa, đây là tổng lũy kế theo khu vực. Nhưng cần dùng tên bảng, kiểu dữ liệu và cú pháp phù hợp với hệ Oracle đang sử dụng.

### 21.4. Frame mặc định cần được xác nhận

Với các hàm aggregate dạng window, có `ORDER BY` nhưng không chỉ rõ frame, nhiều DBMS dựa trên mô hình RANGE lũy kế với peers, nhưng mức hỗ trợ, giới hạn RANGE và chi tiết mỗi hàm có thể khác.

Nếu kết quả lũy kế có ngày trùng quan trọng, hãy **khai báo frame tường minh** và chọn tiêu chí ORDER BY đủ rõ. Đây là cách giảm bất ngờ khi chuyển hệ quản trị.

### 21.5. Một số DBMS hỗ trợ QUALIFY, PostgreSQL không

Một số công cụ SQL như BigQuery, Snowflake hoặc DuckDB có mệnh đề `QUALIFY` để lọc theo kết quả window. Tuy nhiên, **PostgreSQL không hỗ trợ QUALIFY** trong cú pháp thông thường của bài này. Vì thế ta dùng:

~~~sql
WITH xep_hang AS (
    SELECT
        id,
        khu_vuc,
        ROW_NUMBER() OVER (
            PARTITION BY khu_vuc
            ORDER BY ngay_giao_dich DESC, id DESC
        ) AS rn
    FROM wc_giao_dich
)
SELECT id, khu_vuc
FROM xep_hang
WHERE rn = 1;
~~~

Khi chuyển SQL giữa các hệ, cần kiểm tra xem nguồn nào hỗ trợ QUALIFY và nguồn nào yêu cầu CTE/bảng dẫn xuất.

## 22. Lỗi và nhầm lẫn thường gặp

| Hiểu nhầm/lỗi | Điều gì không đúng? | Cách xử lý |
|---|---|---|
| `PARTITION BY` giống `GROUP BY` | Partition không gộp dòng | Xác định cần một dòng/giao dịch hay một dòng/nhóm |
| `OVER()` nghĩa là không tính gì | OVER() tính trên toàn tập đầu vào như một partition | Hiểu phạm vi toàn bộ tập |
| `ORDER BY` trong OVER sắp kết quả ngoài | Nó sắp để tính hàm cửa sổ | Thêm ORDER BY ngoài cùng để hiển thị |
| `SUM OVER(PARTITION BY ...)` luôn là lũy kế | Không có ORDER BY thường tính toàn partition | Thêm ORDER BY và frame khi cần lũy kế |
| `SUM OVER(... ORDER BY ngay)` luôn cộng từng giao dịch | Frame mặc định RANGE có thể gộp peers trùng ngày | Dùng ROWS và khóa phá hòa nếu cần từng dòng |
| `CURRENT ROW` trong RANGE chỉ gồm một hàng | Nó có thể bao gồm các peers | Hiểu ranh giới theo giá trị |
| ROW_NUMBER trên ngày trùng luôn cố định | Thiếu khóa phá hòa gây thứ tự không xác định | Thêm ID hoặc thời điểm chi tiết |
| RANK và DENSE_RANK giống nhau | RANK có khoảng trống sau đồng hạng | Chọn loại hạng đúng mục đích |
| Thêm ID vào RANK để ổn định mà vẫn giữ đồng hạng tiền | ID làm các hàng khác peers | Không thêm khóa phá hòa nếu nó thay đổi định nghĩa hạng |
| LAST_VALUE tự lấy cuối partition | Mặc định frame có thể chỉ tới dòng hiện tại | Dùng frame tới UNBOUNDED FOLLOWING |
| NULL trong SUM luôn làm cả tổng NULL | SUM bỏ qua NULL khi có giá trị khác NULL | Phân biệt frame toàn NULL với frame có số |
| 0 và NULL giống nhau | 0 là giá trị thật; NULL biểu thị thiếu/chưa biết | Giữ ý nghĩa dữ liệu, cẩn thận COALESCE |
| LAG mặc định 0 sẽ thay số tiền NULL của dòng trước | Default chỉ dùng khi vị trí trước không tồn tại | Dùng LAG(id) để phân biệt hoặc xử lý NULL có chủ đích |
| Có thể lọc ROW_NUMBER bằng WHERE cùng SELECT | Window không dùng trực tiếp trong WHERE cùng cấp ở PostgreSQL | CTE/bảng dẫn xuất rồi lọc ngoài |
| WHERE không ảnh hưởng tổng cửa sổ | WHERE loại hàng trước window | Tính trước rồi lọc ngoài nếu cần giữ ngữ cảnh |
| ROWS 2 PRECEDING nghĩa hai ngày trước | ROWS đếm số hàng, không đếm ngày | Chọn frame theo yêu cầu thời gian |
| Index đảm bảo không cần sort | Optimizer có thể chọn kế hoạch khác | Xem EXPLAIN trên dữ liệu thật |

## 23. Bài tập thực hành có lời giải

Các bài dưới sử dụng bảng `wc_giao_dich` của phần 3. Các statement chỉ đọc dữ liệu trừ khi được ghi chú rõ.

### Bài 1. Tính tổng toàn bảng nhưng giữ mọi giao dịch

**Yêu cầu:** hiển thị id, khu vực, số tiền và tổng tiền toàn bảng bằng hàm cửa sổ.

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    SUM(so_tien) OVER () AS tong_toan_bo
FROM wc_giao_dich
ORDER BY id;
~~~

**Đáp án:** 12 hàng; mỗi hàng có `tong_toan_bo = 1000`.

### Bài 2. Tính số giao dịch và trung bình theo khu vực

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    COUNT(*) OVER (
        PARTITION BY khu_vuc
    ) AS so_hang_vung,
    AVG(so_tien) OVER (
        PARTITION BY khu_vuc
    ) AS avg_vung
FROM wc_giao_dich
ORDER BY khu_vuc, id;
~~~

**Đáp án:** Bắc 5 hàng, AVG 125; Nam 5 hàng, AVG 125; Trung 2 hàng, AVG NULL.

### Bài 3. Đánh số giao dịch theo ngày trong từng khu vực

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
    ) AS stt
FROM wc_giao_dich
ORDER BY khu_vuc, stt;
~~~

**Đáp án:** Bắc có các ID 101–105 với STT 1–5; Nam 201–205 với STT 1–5; Trung 301–302 với STT 1–2.

### Bài 4. Giải thích tổng lũy kế mặc định khi ngày trùng

~~~sql
SELECT
    id,
    ngay_giao_dich,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich
    ) AS tong
FROM wc_giao_dich
WHERE khu_vuc = 'Bắc'
ORDER BY ngay_giao_dich, id;
~~~

**Câu hỏi:** tại sao cả ID 102 và 103 cùng có tổng 450?

**Đáp án:** chúng có cùng ngày 03/10, là peers theo ORDER BY ngày. Frame RANGE mặc định với CURRENT ROW đi qua toàn bộ peers cùng khóa, nên cả hai tổng hợp từ 101, 102 và 103.

### Bài 5. Viết lũy kế theo từng giao dịch

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

**Đáp án:** Bắc lần lượt 100, 300, 450, 450, 500; Nam lần lượt 300, 400, 500, 500, 500; Trung cả hai dòng là NULL.

### Bài 6. So sánh ROW_NUMBER, RANK và DENSE_RANK ở Nam

~~~sql
SELECT
    id,
    so_tien,
    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC NULLS LAST, id
    ) AS stt,
    RANK() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC NULLS LAST
    ) AS hang,
    DENSE_RANK() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC NULLS LAST
    ) AS hang_dac
FROM wc_giao_dich
WHERE khu_vuc = 'Nam'
ORDER BY so_tien DESC NULLS LAST, id;
~~~

**Đáp án:** 201 có (1,1,1), 202 có (2,2,2), 203 có (3,2,2), 204 có (4,4,3), 205 có (5,5,4), theo thứ tự `(stt, hang, hang_dac)`.

### Bài 7. Giao dịch mới nhất trong mỗi khu vực

~~~sql
WITH xep_hang AS (
    SELECT
        id,
        khu_vuc,
        ngay_giao_dich,
        ROW_NUMBER() OVER (
            PARTITION BY khu_vuc
            ORDER BY ngay_giao_dich DESC, id DESC
        ) AS rn
    FROM wc_giao_dich
)
SELECT id, khu_vuc, ngay_giao_dich
FROM xep_hang
WHERE rn = 1
ORDER BY khu_vuc;
~~~

**Đáp án:** Bắc 105, Nam 205, Trung 302. CTE cần thiết trong PostgreSQL vì WHERE cùng cấp không lọc trực tiếp kết quả ROW_NUMBER vừa tính.

### Bài 8. Giao dịch mới nhất đã có tiền

**Yêu cầu:** như bài 7 nhưng không xét những giao dịch có `so_tien IS NULL`.

~~~sql
WITH xep_hang AS (
    SELECT
        id,
        khu_vuc,
        so_tien,
        ROW_NUMBER() OVER (
            PARTITION BY khu_vuc
            ORDER BY ngay_giao_dich DESC, id DESC
        ) AS rn
    FROM wc_giao_dich
    WHERE so_tien IS NOT NULL
)
SELECT id, khu_vuc, so_tien
FROM xep_hang
WHERE rn = 1
ORDER BY khu_vuc;
~~~

**Đáp án:** Bắc 105 (50), Nam 204 (0); không có Trung. Lọc NULL **trước ROW_NUMBER** thay đổi tập ứng viên được xếp thứ tự.

### Bài 9. Trung bình trượt ba giao dịch

~~~sql
SELECT
    id,
    khu_vuc,
    AVG(so_tien) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS avg_3
FROM wc_giao_dich
ORDER BY khu_vuc, ngay_giao_dich, id;
~~~

**Đáp án với Bắc:** ID 101 → 100; 102 → 150; 103 → 150; 104 → 175; 105 → 100. Ở 104, frame ba giao dịch có một số tiền NULL nên AVG chia cho hai giá trị còn lại.

### Bài 10. Lấy ID cuối của toàn partition

**Yêu cầu:** ở mỗi giao dịch, bổ sung ID giao dịch cuối cùng của khu vực theo thời gian.

~~~sql
SELECT
    id,
    khu_vuc,
    LAST_VALUE(id) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich, id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS id_cuoi_vung
FROM wc_giao_dich
ORDER BY khu_vuc, id;
~~~

**Đáp án:** mọi hàng Bắc có id_cuoi_vung = 105; Nam = 205; Trung = 302. Nếu bỏ frame tường minh, LAST_VALUE mặc định có thể trả ID của dòng hiện tại.

### Bài 11. Tạo cửa sổ có tên

~~~sql
SELECT
    id,
    khu_vuc,
    COUNT(*) OVER w AS so_hang,
    SUM(so_tien) OVER w AS tong_vung
FROM wc_giao_dich
WINDOW w AS (
    PARTITION BY khu_vuc
)
ORDER BY khu_vuc, id;
~~~

**Đáp án:** cửa sổ `w` được dùng lại cho COUNT và SUM. Bắc/Nam có `so_hang = 5`, `tong_vung = 500`; Trung có `so_hang = 2`, `tong_vung = NULL`.

### Bài 12. Tại sao COUNT theo khu vực thay đổi sau WHERE?

~~~sql
SELECT
    id,
    khu_vuc,
    COUNT(*) OVER (
        PARTITION BY khu_vuc
    ) AS dem
FROM wc_giao_dich
WHERE so_tien IS NOT NULL
ORDER BY khu_vuc, id;
~~~

**Đáp án:** `WHERE` loại các giao dịch tiền NULL trước khi cửa sổ được tính. Bắc có 4 hàng, Nam 4 hàng, Trung không còn hàng. Muốn hiển thị 8 dòng có tiền nhưng vẫn kèm tổng số giao dịch Bắc/Nam là 5, tính COUNT trong CTE trước rồi lọc ở SELECT ngoài.

### Bài 13. Tỷ trọng giao dịch trong vùng

~~~sql
SELECT
    id,
    khu_vuc,
    so_tien,
    ROUND(
        100.0 * so_tien
        / NULLIF(
            SUM(so_tien) OVER (PARTITION BY khu_vuc),
            0
        ),
        2
    ) AS phan_tram
FROM wc_giao_dich
ORDER BY khu_vuc, id;
~~~

**Đáp án:** Bắc: ID 101 = 20%, 102 = 40%, 103 = 30%, 105 = 10%. Nam: ID 201 = 60%, 202 = 20%, 203 = 20%, 204 = 0%. Các hàng tiền NULL có tỷ trọng NULL; Trung không có tổng tiền xác định nên không có tỷ trọng.

### Bài 14. Tổng theo ngày rồi lũy kế theo ngày

~~~sql
WITH theo_ngay AS (
    SELECT
        khu_vuc,
        ngay_giao_dich,
        SUM(so_tien) AS tong_ngay
    FROM wc_giao_dich
    GROUP BY khu_vuc, ngay_giao_dich
)
SELECT
    khu_vuc,
    ngay_giao_dich,
    tong_ngay,
    SUM(tong_ngay) OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke
FROM theo_ngay
ORDER BY khu_vuc, ngay_giao_dich;
~~~

**Đáp án với Bắc:** các ngày 01, 03, 05, 07/10 có tổng ngày 100, 350, NULL, 50 và lũy kế tương ứng 100, 450, 450, 500. CTE đảm bảo một hàng theo ngày trước khi tính cửa sổ.

### Bài 15. Phân biệt ORDER BY trong và ngoài OVER

~~~sql
SELECT
    id,
    khu_vuc,
    ngay_giao_dich,
    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY ngay_giao_dich ASC, id ASC
    ) AS rn
FROM wc_giao_dich
ORDER BY khu_vuc DESC, id DESC;
~~~

**Câu hỏi:** tại sao trong khu vực Bắc, ID 105 có thể xuất hiện ở trên cùng dù `rn = 5`?

**Đáp án:** ROW_NUMBER tính theo **ngày tăng dần**, còn SELECT cuối hiển thị theo **khu vực giảm dần rồi ID giảm dần**. Hai ORDER BY làm hai nhiệm vụ khác nhau.

## 24. Checklist trước khi viết hàm cửa sổ

Khi gặp một yêu cầu có `OVER`, hãy tự hỏi:

1. **Một hàng kết quả phải đại diện cho đối tượng nào?** Nếu cần giữ từng dòng gốc, hàm cửa sổ có thể thích hợp hơn GROUP BY.
2. **Tôi tính trên toàn tập hay từng nhóm?** Không có PARTITION BY nghĩa là một partition chung; có PARTITION BY nghĩa là mỗi nhóm được tính riêng.
3. **Có thực sự cần thứ tự trong cửa sổ không?** Tổng cả vùng không cần thứ tự; ROW_NUMBER, LAG và tổng lũy kế thường cần.
4. **ORDER BY bên trong OVER gồm những cột nào?** Với trùng ngày hoặc trùng tiền, kết quả có cần phá hòa không?
5. **Tôi muốn giữ đồng hạng?** Nếu muốn RANK theo tiền, thêm ID có thể làm mất đồng hạng.
6. **Hàm có phụ thuộc frame không?** Đặc biệt SUM/AVG có ORDER BY và LAST_VALUE.
7. **Frame mặc định có tạo peers không?** Với ORDER BY ngày trùng, RANGE có thể đưa cả nhóm cùng ngày vào kết quả.
8. **ROWS có đúng nghĩa “số hàng” không?** Đừng nhầm ROWS 2 PRECEDING với hai ngày lịch trước.
9. **NULL và 0 có ý nghĩa gì?** SUM/AVG bỏ qua NULL, còn 0 tham gia.
10. **WHERE có lọc mất dữ liệu cần cho chỉ số không?** Nếu cần tính trên toàn tập rồi lọc hiển thị, dùng CTE/bảng dẫn xuất.
11. **Có muốn lọc theo ROW_NUMBER không?** Trong PostgreSQL, hãy tính ở lớp trong rồi lọc ở lớp ngoài.
12. **ORDER BY cuối cùng đã có chưa?** Nếu cần hiển thị hoặc phân trang ổn định, phải sắp kết quả ngoài cùng.
13. **Có thể dùng WINDOW để giảm lặp cấu hình không?** Hữu ích khi nhiều hàm dùng cùng partition/frame.
14. **Có cần xem EXPLAIN hoặc điều chỉnh index không?** Với dữ liệu lớn, kiểm tra kế hoạch thay vì suy đoán.
15. **SQL sẽ chạy trên DBMS nào?** Kiểm tra hỗ trợ frame, NULLS FIRST/LAST, QUALIFY và các hàm cụ thể của phiên bản đó.

## 25. Tổng kết

**`OVER` xác định ngữ cảnh tính hàm cửa sổ; `PARTITION BY` xác định ranh giới nhóm; `ORDER BY` bên trong OVER xác định thứ tự để tính.** Chúng phối hợp nhưng không làm cùng một việc.

- `SUM(x) OVER ()` tính tổng toàn tập rồi lặp giá trị trên từng hàng.
- `SUM(x) OVER (PARTITION BY nhom)` tính tổng riêng mỗi nhóm mà không gộp dòng.
- `ROW_NUMBER() OVER (PARTITION BY nhom ORDER BY ngay, id)` đánh số hàng theo thứ tự xác định trong nhóm.
- `SUM(x) OVER (PARTITION BY nhom ORDER BY ngay, id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` tính lũy kế theo từng hàng.
- Khi có ORDER BY nhưng **không khai báo frame**, một số hàm aggregate và value functions có thể dùng frame mặc định khác ý định; đặc biệt cần chú ý **các hàng cùng khóa sắp xếp** và `LAST_VALUE`.
- `ORDER BY` trong OVER phục vụ tính toán, còn `ORDER BY` ở SELECT ngoài cùng phục vụ thứ tự hiển thị.
- `WHERE` có thể thay đổi tập được tính cửa sổ; khi cần lọc theo kết quả window, hãy dùng CTE/bảng dẫn xuất trong PostgreSQL.

Khi hiểu rõ ba tầng **partition → order → frame**, bạn sẽ chủ động xây dựng được chỉ số theo nhóm, thứ hạng, so sánh giao dịch trước/sau và tổng lũy kế mà vẫn giữ nguyên từng hàng dữ liệu cần phân tích.
