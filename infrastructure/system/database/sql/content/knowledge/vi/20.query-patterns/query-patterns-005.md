# Tìm khoảng trống và các dãy giá trị liên tiếp trong SQL

Một hệ thống ghi nhận phiếu xử lý có các số `1, 2, 3, 6, 7, 10`. Ta có thể đặt hai câu hỏi khác nhau:

- **Khoảng trống (*gap*) ở đâu?** Trong đoạn từ số 1 đến số 10, các số 4, 5, 8, 9 không xuất hiện.
- **Những dãy liên tiếp (*island*) là gì?** Dữ liệu hiện có tạo thành ba dãy: `1–3`, `6–7` và `10`.

Đây là mẫu truy vấn **gaps and islands**, rất hữu ích trong Database SQL. Mẫu này xuất hiện ở nhật ký đăng nhập liên tục theo ngày, chuỗi số chứng từ, dữ liệu cảm biến, lịch đặt phòng, bảng giá có hiệu lực theo thời gian, khoảng bảo trì, trạng thái hoạt động và kiểm tra chất lượng dữ liệu.

Điểm cốt lõi không nằm ở một hàm SQL duy nhất mà ở cách xác định **thế nào là hai hàng liên tiếp**. Nếu hàng có ngày 01/10 và 03/10, đó là hai **bản ghi liên tiếp trong thứ tự dữ liệu**, nhưng **không phải hai ngày liên tiếp theo lịch**. Tương tự, hai khoảng đặt phòng có thể chồng lấn, liền kề hoặc cách nhau một khoảng trống thực sự.

Bài này xây dựng các mẫu truy vấn từ cơ bản đến nâng cao bằng **PostgreSQL**: `LAG`, `LEAD`, `ROW_NUMBER`, `SUM(...) OVER`, `generate_series`, `NOT EXISTS`, nhóm dãy ngày và hợp nhất khoảng thời gian. Sau đó, ta đối chiếu kỹ thuật tương ứng trên MySQL, SQL Server và Oracle Database.

## 1. Hiểu đúng hai bài toán: gaps và islands

Xét dãy số đã sắp xếp:

~~~text
Giá trị có thật:   1  2  3     6  7       10      12 13 14                20
Khoảng trống:               4  5      8  9     11          15 16 17 18 19
Các dãy:          [1--3]     [6--7]      [10]    [12--14]                 [20]
~~~

Ba khái niệm cần phân biệt:

1. **Hàng kế tiếp trong truy vấn**: hàng đứng ngay sau theo `ORDER BY`. Ví dụ, sau số 3 là số 6 trong tập dữ liệu có thật.
2. **Giá trị kế tiếp theo quy tắc liên tục**: nếu bước tăng là 1, sau số 3 phải là số 4; nếu bước là một ngày, sau 02/10 phải là 03/10.
3. **Khoảng trống**: giá trị hoặc khoảng giá trị đáng lẽ có thể xuất hiện theo **miền kỳ vọng đã xác định**, nhưng không được ghi nhận.

“Khoảng trống” không tự động là **lỗi**. Sequence trong database, số hóa đơn bị hủy, ID sinh phân tán hoặc các ngày cửa hàng nghỉ đều có thể có khoảng cách hợp lệ. Trước khi viết SQL, phải xác định **miền dữ liệu và quy tắc nghiệp vụ**.

### 1.1. Những câu hỏi thường gặp

| Yêu cầu | Kiểu kết quả | Mẫu SQL hay dùng |
| --- | --- | --- |
| Có những chỗ nhảy số nào? | Một dòng cho mỗi cặp mốc có khoảng cách | `LAG` hoặc `LEAD` |
| Những số cụ thể nào bị thiếu từ 1 đến 20? | Một dòng cho mỗi giá trị thiếu | Dãy số chuẩn + `NOT EXISTS` |
| Những đoạn số liên tiếp là gì? | Một dòng cho mỗi dãy | `ROW_NUMBER` hoặc cờ đầu dãy + cộng dồn |
| Người dùng có bao nhiêu ngày hoạt động liên tục? | Độ dài từng streak | Lọc trùng ngày + nhóm dãy ngày |
| Dãy dài nhất mỗi người là bao nhiêu? | Một dòng cho mỗi người | Kết quả dãy + `MAX`/`ROW_NUMBER` |
| Những khoảng đặt phòng nào chồng lấn/liền kề? | Các khoảng đã hợp nhất | `MAX(end)` lũy tiến + đánh số nhóm |
| Phòng trống giữa các lịch đặt ở đâu? | Khoảng thời gian không bị chiếm dụng | Hợp nhất khoảng rồi `LEAD(start)` |

Với mỗi bài toán, cần hỏi thêm: **xét riêng theo khách hàng, cửa hàng hay tổ chức nào?** Điều này quyết định `PARTITION BY` và các cột khóa trong `JOIN`.

## 2. Bộ dữ liệu thực hành PostgreSQL

Các ví dụ dùng bảng tạm, tồn tại trong **một phiên kết nối PostgreSQL**. Nếu mở phiên mới, hãy chạy lại các câu `CREATE TEMP TABLE` và `INSERT` bên dưới.

### 2.1. Dãy số phiếu theo bộ phận

~~~sql
CREATE TEMP TABLE so_phieu_gap (
    bo_phan_id INTEGER NOT NULL,
    so_phieu INTEGER NOT NULL,
    PRIMARY KEY (bo_phan_id, so_phieu)
);

INSERT INTO so_phieu_gap (bo_phan_id, so_phieu)
VALUES
    (10,  1), (10,  2), (10,  3),
    (10,  6), (10,  7),
    (10, 10),
    (10, 12), (10, 13), (10, 14),
    (10, 20),
    (20,  2), (20,  3),
    (20,  5), (20,  6),
    (20,  8);
~~~

Bảng có **15 dòng**. Mỗi hàng là **một số phiếu thuộc một bộ phận**. Khóa chính ghép `(bo_phan_id, so_phieu)` bảo đảm một bộ phận không có hai dòng cùng số phiếu, nhưng hai bộ phận **được phép** có cùng số.

| Bộ phận | Số phiếu có mặt | Dãy liên tiếp |
| ---: | --- | --- |
| 10 | 1, 2, 3, 6, 7, 10, 12, 13, 14, 20 | 1–3; 6–7; 10; 12–14; 20 |
| 20 | 2, 3, 5, 6, 8 | 2–3; 5–6; 8 |

Nếu cần tìm khoảng trống **theo từng bộ phận**, không được tính một chuỗi chung gồm cả hai bộ phận: số 4 của bộ phận 10 không được “bù” bởi một hàng khác của bộ phận 20.

### 2.2. Hoạt động theo ngày của người dùng

~~~sql
CREATE TEMP TABLE nguoi_dung_gap (
    id INTEGER PRIMARY KEY,
    ten TEXT NOT NULL
);

INSERT INTO nguoi_dung_gap (id, ten)
VALUES
    (101, 'An'),
    (102, 'Bình'),
    (103, 'Chi'),
    (104, 'Dung');

CREATE TEMP TABLE hoat_dong_ngay_gap (
    nguoi_dung_id INTEGER NOT NULL
        REFERENCES nguoi_dung_gap(id),
    ngay DATE NOT NULL,
    so_phien INTEGER NOT NULL CHECK (so_phien >= 0),
    PRIMARY KEY (nguoi_dung_id, ngay)
);

INSERT INTO hoat_dong_ngay_gap
    (nguoi_dung_id, ngay, so_phien)
VALUES
    (101, DATE '2026-10-01', 2),
    (101, DATE '2026-10-02', 1),
    (101, DATE '2026-10-03', 4),
    (101, DATE '2026-10-06', 1),
    (101, DATE '2026-10-07', 3),
    (101, DATE '2026-10-10', 1),
    (101, DATE '2026-10-12', 2),
    (101, DATE '2026-10-13', 1),
    (101, DATE '2026-10-14', 2),
    (101, DATE '2026-10-20', 1),
    (102, DATE '2026-10-02', 1),
    (102, DATE '2026-10-04', 2),
    (102, DATE '2026-10-05', 1),
    (102, DATE '2026-10-06', 3),
    (102, DATE '2026-10-09', 1),
    (102, DATE '2026-10-10', 2),
    (102, DATE '2026-10-12', 1),
    (103, DATE '2026-10-06', 1);
~~~

Bảng hoạt động có **18 hàng**: người 101 có 10 ngày ghi nhận, người 102 có 7 ngày, người 103 có 1 ngày, người 104 **không có ngày nào**. Trong ví dụ, một dòng có `so_phien = 3` vẫn chỉ đại diện cho **một ngày hoạt động**, không phải ba ngày.

Các dãy mong đợi:

| Người | Các dãy ngày liên tiếp theo lịch | Dãy dài nhất |
| ---: | --- | ---: |
| 101 | 01–03/10; 06–07/10; 10/10; 12–14/10; 20/10 | 3 ngày |
| 102 | 02/10; 04–06/10; 09–10/10; 12/10 | 3 ngày |
| 103 | 06/10 | 1 ngày |
| 104 | Không có hoạt động | 0 ngày |

**Định nghĩa trong bài:** hai ngày là liên tiếp nếu khác nhau đúng **một ngày dương lịch**. Nếu bài toán cần “ngày làm việc liên tiếp”, “ngày học” hoặc “ca trực liên tiếp” thì quy tắc này phải được thay bằng lịch nghiệp vụ.

### 2.3. Kiểm tra dữ liệu nguồn

~~~sql
SELECT bo_phan_id, so_phieu
FROM so_phieu_gap
ORDER BY bo_phan_id, so_phieu;

SELECT nguoi_dung_id, ngay, so_phien
FROM hoat_dong_ngay_gap
ORDER BY nguoi_dung_id, ngay;
~~~

Các `ORDER BY` ở đây chỉ phục vụ việc quan sát dữ liệu. Thứ tự hàng vật lý hoặc thứ tự `INSERT` **không bảo đảm** các phép phân tích “trước/sau” đúng; phải khai báo thứ tự trong từng hàm cửa sổ khi cần.

## 3. Phát hiện khoảng trống bằng LAG

`LAG(expr)` lấy giá trị của **hàng ngay trước** trong partition đã sắp xếp:

~~~sql
SELECT
    bo_phan_id,
    so_phieu,
    LAG(so_phieu) OVER (
        PARTITION BY bo_phan_id
        ORDER BY so_phieu
    ) AS so_phieu_truoc
FROM so_phieu_gap
ORDER BY bo_phan_id, so_phieu;
~~~

Ở bộ phận 10, số 6 có `so_phieu_truoc = 3`. Hai số khác nhau 3 đơn vị nên **thiếu hai số nằm giữa** là 4 và 5. Trong bộ phận 20, số 5 có `so_phieu_truoc = 3`, nên thiếu số 4.

Sơ đồ:

~~~mermaid
flowchart LR
    A["Bộ phận 10\n1, 2, 3"] -->|"LAG tại số 6 trả 3\nThiếu 4, 5"| B["6, 7"]
    B -->|"LAG tại số 10 trả 7\nThiếu 8, 9"| C["10"]
    C -->|"LAG tại số 12 trả 10\nThiếu 11"| D["12, 13, 14"]
    D -->|"LAG tại số 20 trả 14\nThiếu 15–19"| E["20"]
~~~

### 3.1. Tính số lượng giá trị bị thiếu trong mỗi khoảng

~~~sql
WITH phieu_co_hang_truoc AS (
    SELECT
        bo_phan_id,
        so_phieu,
        LAG(so_phieu) OVER (
            PARTITION BY bo_phan_id
            ORDER BY so_phieu
        ) AS so_phieu_truoc
    FROM so_phieu_gap
)
SELECT
    bo_phan_id,
    so_phieu_truoc AS moc_truoc,
    so_phieu AS moc_sau,
    so_phieu - so_phieu_truoc - 1 AS so_gia_tri_thieu
FROM phieu_co_hang_truoc
WHERE so_phieu_truoc IS NOT NULL
  AND so_phieu > so_phieu_truoc + 1
ORDER BY bo_phan_id, moc_truoc;
~~~

Kết quả:

| Bộ phận | Mốc trước | Mốc sau | Số giá trị thiếu |
| ---: | ---: | ---: | ---: |
| 10 | 3 | 6 | 2 |
| 10 | 7 | 10 | 2 |
| 10 | 10 | 12 | 1 |
| 10 | 14 | 20 | 5 |
| 20 | 3 | 5 | 1 |
| 20 | 6 | 8 | 1 |

Giải thích điều kiện `so_phieu > so_phieu_truoc + 1`:

- Nếu `so_phieu = so_phieu_truoc + 1`: hai số liên tiếp, **không có khoảng trống**.
- Nếu `so_phieu > so_phieu_truoc + 1`: có ít nhất một số nguyên bị thiếu giữa hai mốc.
- Hàng đầu partition có `LAG = NULL`; không có mốc trước để kết luận khoảng trống bên trong.

Với dãy số bước 1, công thức là:

\[
\text{số giá trị thiếu} = \text{mốc sau} - \text{mốc trước} - 1.
\]

Công thức này **không áp dụng nguyên xi** nếu miền giá trị tăng bước 5, chỉ tính ngày làm việc, hoặc sử dụng mã định danh phi số.

### 3.2. Trả ranh giới đầu–cuối của từng khoảng thiếu

~~~sql
WITH phieu_co_hang_truoc AS (
    SELECT
        bo_phan_id,
        so_phieu,
        LAG(so_phieu) OVER (
            PARTITION BY bo_phan_id
            ORDER BY so_phieu
        ) AS so_phieu_truoc
    FROM so_phieu_gap
)
SELECT
    bo_phan_id,
    so_phieu_truoc + 1 AS tu_so,
    so_phieu - 1 AS den_so,
    so_phieu - so_phieu_truoc - 1 AS so_luong_thieu
FROM phieu_co_hang_truoc
WHERE so_phieu_truoc IS NOT NULL
  AND so_phieu > so_phieu_truoc + 1
ORDER BY bo_phan_id, tu_so;
~~~

Kết quả bộ phận 10 là bốn khoảng **4–5**, **8–9**, **11–11**, **15–19**. Đoạn `11–11` nghĩa là chỉ thiếu **một số 11**; một khoảng đơn trị vẫn hợp lệ.

## 4. Dùng LEAD thay vì LAG

`LEAD(expr)` lấy giá trị của **hàng ngay sau** trong thứ tự:

~~~sql
WITH phieu_co_hang_sau AS (
    SELECT
        bo_phan_id,
        so_phieu,
        LEAD(so_phieu) OVER (
            PARTITION BY bo_phan_id
            ORDER BY so_phieu
        ) AS so_phieu_sau
    FROM so_phieu_gap
)
SELECT
    bo_phan_id,
    so_phieu + 1 AS tu_so,
    so_phieu_sau - 1 AS den_so
FROM phieu_co_hang_sau
WHERE so_phieu_sau > so_phieu + 1
ORDER BY bo_phan_id, tu_so;
~~~

Câu SQL này cũng trả sáu khoảng thiếu như ở mục 3. Nó mô tả khoảng trống theo **điểm bắt đầu trước khoảng thiếu**, trong khi `LAG` mô tả theo **điểm kết thúc sau khoảng thiếu**.

### 4.1. Nên chọn LAG hay LEAD?

| Câu hỏi | Cách nhìn tự nhiên |
| --- | --- |
| “Giữa phiếu này và phiếu trước thiếu gì?” | `LAG` |
| “Từ phiếu này đến phiếu kế tiếp còn thiếu số nào?” | `LEAD` |
| “Đâu là lần đăng nhập ngay trước người dùng hiện tại?” | `LAG` |
| “Khi nào diễn ra sự kiện tiếp theo?” | `LEAD` |

Hai hàm đều cần **`PARTITION BY` đúng đối tượng** và **`ORDER BY` xác định thứ tự**. Không có gì bắt buộc `LAG` hiệu quả hơn `LEAD` một cách tổng quát; bộ tối ưu hóa và công việc truy vấn thực tế mới quyết định chi phí.

## 5. Chỉ tìm khoảng trống giữa các mốc, hay trong một miền kỳ vọng?

Phát hiện khoảng trống bằng `LAG`/`LEAD` chỉ tìm được **những khoảng nằm giữa hai giá trị có thật**.

Với bộ phận 10, dữ liệu bắt đầu ở số 1 và kết thúc ở số 20. Nếu nghiệp vụ mong đợi các số từ **1 đến 25**, còn thiếu **21–25**, nhưng hai hàm `LAG`/`LEAD` trên dữ liệu nguồn **không thể tự suy ra** giới hạn 25.

Muốn tìm thiếu **ngoài hai đầu dữ liệu**, cần một miền kỳ vọng được khai báo:

- Khoảng số `1..25`;
- Khoảng ngày từ ngày khai trương đến ngày kết thúc báo cáo;
- Danh sách ngày làm việc của tổ chức;
- Danh sách các slot lịch đã cấu hình;
- Khoảng phiên bản hoặc trạng thái hợp lệ được định nghĩa bởi nghiệp vụ.

**Không tự coi `MIN(so_phieu)` và `MAX(so_phieu)` là giới hạn toàn bộ dữ liệu cần có**: đó chỉ là phạm vi các hàng hiện đã xuất hiện.

### 5.1. Ghi rõ giới hạn bằng một CTE tham số

Ví dụ chỉ xem số phiếu bộ phận 10 trong đoạn `1..20`:

~~~sql
WITH gioi_han AS (
    SELECT
        10::integer AS bo_phan_id,
        1::integer AS tu_so,
        20::integer AS den_so
)
SELECT *
FROM gioi_han;
~~~

Trong ứng dụng, `bo_phan_id`, `tu_so`, `den_so` nên được truyền làm **tham số truy vấn** hoặc lấy từ bảng cấu hình đáng tin cậy, không tự suy đoán từ các khoảng trống quan sát được.

## 6. Liệt kê từng giá trị thiếu bằng generate_series và NOT EXISTS

Nếu muốn trả **mỗi số còn thiếu thành một dòng**, thay vì chỉ trả ranh giới khoảng, PostgreSQL có thể sinh miền chuẩn bằng `generate_series`.

~~~sql
WITH gioi_han AS (
    SELECT
        10::integer AS bo_phan_id,
        1::integer AS tu_so,
        20::integer AS den_so
),
tat_ca_so AS (
    SELECT
        g.bo_phan_id,
        gs.so_phieu
    FROM gioi_han AS g
    CROSS JOIN LATERAL generate_series(g.tu_so, g.den_so, 1)
        AS gs(so_phieu)
)
SELECT
    s.bo_phan_id,
    s.so_phieu AS so_con_thieu
FROM tat_ca_so AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM so_phieu_gap AS p
    WHERE p.bo_phan_id = s.bo_phan_id
      AND p.so_phieu = s.so_phieu
)
ORDER BY s.so_phieu;
~~~

Kết quả là mười số:

~~~text
4, 5, 8, 9, 11, 15, 16, 17, 18, 19
~~~

Điểm đáng chú ý:

1. CTE `gioi_han` xác định **miền phải có**.
2. `generate_series(1,20,1)` tạo toàn bộ 20 số.
3. `NOT EXISTS` hỏi **“số này có xuất hiện trong bộ phận 10 không?”**.
4. Chỉ những số **không có hàng khớp** ở bảng thật được giữ.

### 6.1. Cùng bài toán bằng LEFT JOIN

~~~sql
WITH tat_ca_so AS (
    SELECT generate_series(1, 20) AS so_phieu
)
SELECT s.so_phieu
FROM tat_ca_so AS s
LEFT JOIN so_phieu_gap AS p
    ON p.bo_phan_id = 10
   AND p.so_phieu = s.so_phieu
WHERE p.so_phieu IS NULL
ORDER BY s.so_phieu;
~~~

Cũng trả mười số thiếu. Vì `p.so_phieu` là một phần của khóa chính, nó không thể `NULL` ở hàng nguồn thật; `p.so_phieu IS NULL` sau `LEFT JOIN` do đó nhận diện được hàng **không khớp**.

`NOT EXISTS` và `LEFT JOIN ... IS NULL` là hai mẫu **anti-join** phổ biến. Với tập dữ liệu và điều kiện tương ứng, chúng có thể cho cùng kết quả; hiệu năng nên được đánh giá bằng kế hoạch thay vì khẳng định một cách luôn nhanh hơn.

### 6.2. Tránh NOT IN với cột có NULL

~~~sql
-- Cần chú ý nếu danh sách trong subquery có NULL:
-- WHERE s.so_phieu NOT IN (SELECT so_phieu FROM bang_nguon)
~~~

Trong SQL, `NOT IN` có thể trả `UNKNOWN` thay vì `TRUE` khi tập con chứa `NULL`, khiến những số không khớp bị loại ngoài ý muốn. Bảng mẫu có khóa chính `NOT NULL`, nhưng trong bảng nhập liệu hoặc nguồn dữ liệu nullable thì rủi ro này có thật. Với kiểm tra thiếu theo khóa, `NOT EXISTS` thường thể hiện điều kiện rõ ràng hơn.

### 6.3. Đừng sinh miền quá lớn không cần thiết

Một dãy từ 1 đến một tỷ có thể tạo ra **một tỷ hàng trung gian**, rất tốn tài nguyên. Nếu chỉ cần các **khoảng thiếu**, dùng `LAG`/`LEAD` thường phù hợp hơn. Nếu thật sự cần từng giá trị để xuất báo cáo, hãy xác định giới hạn, chia phạm vi phù hợp và cân nhắc số lượng hàng trước khi sinh dữ liệu.

## 7. Tìm dãy giá trị liên tiếp bằng ROW_NUMBER

Một ý tưởng đẹp của mẫu *islands* là: với một chuỗi số nguyên **duy nhất, tăng từng bước 1**, đại lượng

\[
\text{khóa dãy} = \text{giá trị} - \text{số thứ tự hàng}
\]

sẽ **không đổi** trong một dãy liên tiếp.

Xét dữ liệu bộ phận 10:

| `so_phieu` | `ROW_NUMBER()` | `so_phieu - ROW_NUMBER()` | Dãy |
| ---: | ---: | ---: | --- |
| 1 | 1 | 0 | 1–3 |
| 2 | 2 | 0 | 1–3 |
| 3 | 3 | 0 | 1–3 |
| 6 | 4 | 2 | 6–7 |
| 7 | 5 | 2 | 6–7 |
| 10 | 6 | 4 | 10 |
| 12 | 7 | 5 | 12–14 |
| 13 | 8 | 5 | 12–14 |
| 14 | 9 | 5 | 12–14 |
| 20 | 10 | 10 | 20 |

Trong dãy `1,2,3`, cả giá trị và số thứ tự cùng tăng 1 nên hiệu luôn là 0. Khi nhảy từ 3 lên 6, giá trị tăng 3 nhưng số thứ tự chỉ tăng 1, khiến hiệu đổi từ 0 thành 2: **bắt đầu dãy mới**.

### 7.1. Viết SQL bằng CTE

~~~sql
WITH phieu_danh_so AS (
    SELECT
        bo_phan_id,
        so_phieu,
        ROW_NUMBER() OVER (
            PARTITION BY bo_phan_id
            ORDER BY so_phieu
        ) AS stt
    FROM so_phieu_gap
),
phieu_co_khoa_day AS (
    SELECT
        bo_phan_id,
        so_phieu,
        so_phieu::bigint - stt AS khoa_day
    FROM phieu_danh_so
)
SELECT
    bo_phan_id,
    MIN(so_phieu) AS tu_so,
    MAX(so_phieu) AS den_so,
    COUNT(*) AS do_dai_day
FROM phieu_co_khoa_day
GROUP BY bo_phan_id, khoa_day
ORDER BY bo_phan_id, tu_so;
~~~

Kết quả:

| Bộ phận | Từ số | Đến số | Độ dài dãy |
| ---: | ---: | ---: | ---: |
| 10 | 1 | 3 | 3 |
| 10 | 6 | 7 | 2 |
| 10 | 10 | 10 | 1 |
| 10 | 12 | 14 | 3 |
| 10 | 20 | 20 | 1 |
| 20 | 2 | 3 | 2 |
| 20 | 5 | 6 | 2 |
| 20 | 8 | 8 | 1 |

**Vì sao `GROUP BY bo_phan_id, khoa_day`?** Khóa dãy có thể trùng giữa **hai bộ phận khác nhau**. Nếu chỉ nhóm theo `khoa_day`, SQL có thể ghép dãy thuộc bộ phận 10 với dãy thuộc bộ phận 20, dẫn tới kết quả sai.

### 7.2. Vì sao ép sang BIGINT?

`ROW_NUMBER()` trong PostgreSQL trả `BIGINT`. Cột `so_phieu` là `INTEGER`. Viết `so_phieu::bigint - stt` làm kiểu phép trừ tường minh và tránh những nhầm lẫn chuyển kiểu; với dữ liệu số có phạm vi cực lớn, vẫn cần quan tâm nguy cơ tràn của kiểu số khi cộng/trừ biên.

### 7.3. Giới hạn của mẹo giá trị trừ ROW_NUMBER

Mẫu này đúng với **dữ liệu tăng đều bước 1 và không có giá trị trùng trong mỗi partition**. Nó có thể sai nếu:

- Cùng một số xuất hiện hai hàng vì dữ liệu chưa khử trùng;
- Quy tắc liên tục là bước 5 hoặc bước thay đổi;
- Số phiếu không theo thứ tự số học thông thường;
- Muốn nối các khoảng thời gian **chồng lấn** thay vì các điểm rời rạc;
- Cần xét ngày làm việc, bỏ cuối tuần hoặc ngày lễ.

Trong các tình huống đó, hãy điều chỉnh khóa dãy hoặc dùng mẫu **cờ bắt đầu dãy + cộng dồn** ở các mục tiếp theo.

## 8. Tìm dãy bằng LAG và tổng cộng dồn

Thay vì lấy `so_phieu - ROW_NUMBER()`, có thể xác định **mỗi lần bắt đầu dãy mới**:

~~~sql
WITH phieu_co_truoc AS (
    SELECT
        bo_phan_id,
        so_phieu,
        LAG(so_phieu) OVER (
            PARTITION BY bo_phan_id
            ORDER BY so_phieu
        ) AS so_truoc
    FROM so_phieu_gap
),
co_dau_day AS (
    SELECT
        *,
        CASE
            WHEN so_truoc IS NULL THEN 1
            WHEN so_phieu > so_truoc + 1 THEN 1
            ELSE 0
        END AS bat_dau_day_moi
    FROM phieu_co_truoc
),
co_ma_day AS (
    SELECT
        *,
        SUM(bat_dau_day_moi) OVER (
            PARTITION BY bo_phan_id
            ORDER BY so_phieu
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS ma_day
    FROM co_dau_day
)
SELECT
    bo_phan_id,
    MIN(so_phieu) AS tu_so,
    MAX(so_phieu) AS den_so,
    COUNT(*) AS do_dai_day
FROM co_ma_day
GROUP BY bo_phan_id, ma_day
ORDER BY bo_phan_id, tu_so;
~~~

Cũng trả **tám dãy** như mục 7.

Giải thích theo từng lớp:

1. `phieu_co_truoc` tính số phiếu ngay trước bằng `LAG`.
2. `co_dau_day` đánh dấu **1** nếu là hàng đầu partition hoặc giá trị hiện tại lớn hơn giá trị trước cộng 1.
3. `co_ma_day` cộng dồn các cờ `1`, tạo ID dãy `1,1,1,2,2,3,4,4,4,5` ở bộ phận 10.
4. `GROUP BY bo_phan_id, ma_day` gom từng dãy, lấy biên và độ dài.

### 8.1. Khi nào chọn cách cờ + cộng dồn?

Cách này thường dễ mở rộng khi “liền nhau” được định nghĩa bởi một **điều kiện nghiệp vụ**:

~~~sql
CASE
    WHEN gia_tri_truoc IS NULL THEN 1
    WHEN ngay - ngay_truoc > 1 THEN 1
    WHEN trang_thai IS DISTINCT FROM trang_thai_truoc THEN 1
    ELSE 0
END
~~~

Chẳng hạn, một dãy chỉ được tính là liên tục khi **ngày liền nhau và trạng thái không đổi**. Khi đó không chỉ hiệu số học mà **nhiều điều kiện** quyết định điểm cắt dãy.

### 8.2. Vì sao cần nhiều CTE?

Trong PostgreSQL, không thể tùy tiện lồng trực tiếp một hàm cửa sổ bên trong đối số của một hàm cửa sổ khác ở cùng cấp truy vấn. Chia thành các CTE để tính `LAG` trước, tạo cờ ở bước kế tiếp, sau đó mới `SUM(...) OVER` là cách rõ ràng và thường hợp lệ.

CTE không bảo đảm mỗi phần được lưu vật lý; đây trước hết là phương tiện **tổ chức các lớp tính toán**.

## 9. Phát hiện dãy ngày liên tiếp (*daily streaks*)

Giờ xét yêu cầu: **người dùng hoạt động trong những đoạn ngày liên tiếp nào?**

Đối với kiểu `DATE` trên PostgreSQL, phép `DATE - INTEGER` tạo ra một ngày dịch lùi tương ứng. Điều này cho phép chuyển mẹo `giá trị - ROW_NUMBER` từ số nguyên sang ngày.

### 9.1. ROW_NUMBER và khóa nhóm ngày

~~~sql
WITH ngay_danh_so AS (
    SELECT
        nguoi_dung_id,
        ngay,
        ROW_NUMBER() OVER (
            PARTITION BY nguoi_dung_id
            ORDER BY ngay
        ) AS stt
    FROM hoat_dong_ngay_gap
),
ngay_co_khoa_day AS (
    SELECT
        nguoi_dung_id,
        ngay,
        ngay - stt::integer AS khoa_day
    FROM ngay_danh_so
)
SELECT
    nguoi_dung_id,
    MIN(ngay) AS tu_ngay,
    MAX(ngay) AS den_ngay,
    COUNT(*) AS so_ngay_lien_tiep
FROM ngay_co_khoa_day
GROUP BY nguoi_dung_id, khoa_day
ORDER BY nguoi_dung_id, tu_ngay;
~~~

Kết quả:

| Người | Từ ngày | Đến ngày | Số ngày |
| ---: | --- | --- | ---: |
| 101 | 01/10 | 03/10 | 3 |
| 101 | 06/10 | 07/10 | 2 |
| 101 | 10/10 | 10/10 | 1 |
| 101 | 12/10 | 14/10 | 3 |
| 101 | 20/10 | 20/10 | 1 |
| 102 | 02/10 | 02/10 | 1 |
| 102 | 04/10 | 06/10 | 3 |
| 102 | 09/10 | 10/10 | 2 |
| 102 | 12/10 | 12/10 | 1 |
| 103 | 06/10 | 06/10 | 1 |

Người 104 không xuất hiện vì **không có hoạt động** để tạo dãy.

### 9.2. Tại sao hiệu ngày trừ ROW_NUMBER không đổi trong dãy?

Xét người 101:

| Ngày | Số thứ tự | `ngay - stt::int` |
| --- | ---: | --- |
| 01/10 | 1 | 30/09 |
| 02/10 | 2 | 30/09 |
| 03/10 | 3 | 30/09 |
| 06/10 | 4 | 02/10 |
| 07/10 | 5 | 02/10 |
| 10/10 | 6 | 04/10 |
| 12/10 | 7 | 05/10 |
| 13/10 | 8 | 05/10 |
| 14/10 | 9 | 05/10 |
| 20/10 | 10 | 10/10 |

Trong dãy liên tục, ngày tăng **1** và số thứ tự cũng tăng **1** nên hiệu ngày trừ số thứ tự không đổi. Khi ngày nhảy qua khoảng trống, hiệu đổi.

`khoa_day` là **khóa nhóm tạm trong truy vấn**, không phải ngày bắt đầu thực sự của dãy. Ví dụ dãy 01–03/10 có khóa 30/09; muốn ngày bắt đầu phải dùng `MIN(ngay)`.

### 9.3. Độ dài dãy: COUNT hay tính ngày?

Vì bảng có `PRIMARY KEY (nguoi_dung_id, ngay)`, mỗi người tối đa có **một hàng mỗi ngày**. Với các dãy đã được xác định liên tiếp, `COUNT(*)` bằng số ngày.

Nếu bảng gốc lưu **từng lần đăng nhập** và một người có thể đăng nhập năm lần trong cùng ngày, dùng `COUNT(*)` trên dữ liệu thô sẽ đếm **số sự kiện**, không phải số ngày. Khi đó cần khử trùng theo **người + ngày** trước khi đánh số.

## 10. Khử trùng trước khi tìm dãy

Giả sử nguồn là nhật ký từng sự kiện:

~~~sql
CREATE TEMP TABLE su_kien_dang_nhap_gap (
    id INTEGER PRIMARY KEY,
    nguoi_dung_id INTEGER NOT NULL,
    thoi_diem TIMESTAMPTZ NOT NULL
);

INSERT INTO su_kien_dang_nhap_gap
    (id, nguoi_dung_id, thoi_diem)
VALUES
    (1, 101, TIMESTAMPTZ '2026-10-01 08:00:00+07'),
    (2, 101, TIMESTAMPTZ '2026-10-01 18:00:00+07'),
    (3, 101, TIMESTAMPTZ '2026-10-02 09:00:00+07'),
    (4, 101, TIMESTAMPTZ '2026-10-03 10:00:00+07'),
    (5, 102, TIMESTAMPTZ '2026-10-04 12:00:00+07');
~~~

Người 101 có **4 sự kiện** nhưng chỉ **3 ngày hoạt động**. Nếu đánh số `ROW_NUMBER` trực tiếp trên bốn sự kiện, ngày 01/10 xuất hiện **hai lần**, khiến công thức `ngay - ROW_NUMBER()` thay đổi ngay trong cùng ngày và làm chia nhóm sai.

Một cách an toàn:

~~~sql
WITH ngay_hoat_dong AS (
    SELECT DISTINCT
        nguoi_dung_id,
        (thoi_diem AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS ngay
    FROM su_kien_dang_nhap_gap
),
ngay_danh_so AS (
    SELECT
        nguoi_dung_id,
        ngay,
        ROW_NUMBER() OVER (
            PARTITION BY nguoi_dung_id
            ORDER BY ngay
        ) AS stt
    FROM ngay_hoat_dong
),
co_khoa_nhom AS (
    SELECT
        nguoi_dung_id,
        ngay,
        ngay - stt::integer AS khoa_day
    FROM ngay_danh_so
)
SELECT
    nguoi_dung_id,
    MIN(ngay) AS tu_ngay,
    MAX(ngay) AS den_ngay,
    COUNT(*) AS so_ngay
FROM co_khoa_nhom
GROUP BY nguoi_dung_id, khoa_day
ORDER BY nguoi_dung_id, tu_ngay;
~~~

Kết quả người 101: **một dãy 01–03/10 gồm 3 ngày**; người 102: **một dãy 04/10 gồm 1 ngày**.

### 10.1. Ngày theo múi giờ nào?

Với dữ liệu `TIMESTAMPTZ`, một thời điểm tuyệt đối có thể thuộc **ngày khác nhau theo các múi giờ khác nhau**. Ở ví dụ, ta chọn rõ múi giờ `Asia/Ho_Chi_Minh` trước khi ép về `DATE`. Nếu ứng dụng phục vụ nhiều múi giờ, cần xác định **múi giờ của người dùng, cửa hàng hoặc tổ chức** theo quy tắc nghiệp vụ trước khi tính streak.

Không tự ép `timestamp` sang ngày theo múi giờ phiên database nếu báo cáo yêu cầu ngày địa phương khác.

### 10.2. DISTINCT phải dùng đúng khóa

`SELECT DISTINCT nguoi_dung_id, ngay` có nghĩa **một hàng trên mỗi người trong mỗi ngày**. Nếu chỉ `SELECT DISTINCT ngay`, ta có thể trộn ngày hoạt động giữa nhiều người và mất phân biệt partition.

## 11. Tìm dãy dài nhất của mỗi người

Từ các dãy ngày ở mục 9, ta có thể tìm **độ dài liên tục lớn nhất**:

~~~sql
WITH ngay_danh_so AS (
    SELECT
        nguoi_dung_id,
        ngay,
        ROW_NUMBER() OVER (
            PARTITION BY nguoi_dung_id ORDER BY ngay
        ) AS stt
    FROM hoat_dong_ngay_gap
),
co_khoa_day AS (
    SELECT
        nguoi_dung_id,
        ngay,
        ngay - stt::integer AS khoa_day
    FROM ngay_danh_so
),
cac_day AS (
    SELECT
        nguoi_dung_id,
        MIN(ngay) AS tu_ngay,
        MAX(ngay) AS den_ngay,
        COUNT(*) AS so_ngay
    FROM co_khoa_day
    GROUP BY nguoi_dung_id, khoa_day
),
day_dai_nhat AS (
    SELECT
        nguoi_dung_id,
        MAX(so_ngay) AS do_dai_lon_nhat
    FROM cac_day
    GROUP BY nguoi_dung_id
)
SELECT
    u.id AS nguoi_dung_id,
    u.ten,
    COALESCE(d.do_dai_lon_nhat, 0) AS so_ngay_lien_tiep_lon_nhat
FROM nguoi_dung_gap AS u
LEFT JOIN day_dai_nhat AS d
    ON d.nguoi_dung_id = u.id
ORDER BY u.id;
~~~

Kết quả:

| Người | Tên | Dãy dài nhất |
| ---: | --- | ---: |
| 101 | An | 3 |
| 102 | Bình | 3 |
| 103 | Chi | 1 |
| 104 | Dung | 0 |

`LEFT JOIN` giữ người 104 chưa có sự kiện; `COALESCE(...,0)` ở đây mang nghĩa báo cáo **“không có ngày hoạt động, nên độ dài liên tục bằng 0”**. Không sử dụng giá trị 0 làm đại diện `NULL` cho mọi chỉ tiêu khác theo thói quen.

### 11.1. Lấy cả biên của dãy dài nhất

Nếu muốn **ngày bắt đầu và ngày kết thúc** của dãy dài nhất, `MAX(so_ngay)` một mình chưa đủ. Có thể xếp hạng các dãy:

~~~sql
WITH ngay_danh_so AS (
    SELECT
        nguoi_dung_id,
        ngay,
        ROW_NUMBER() OVER (
            PARTITION BY nguoi_dung_id ORDER BY ngay
        ) AS stt
    FROM hoat_dong_ngay_gap
),
co_khoa_day AS (
    SELECT
        nguoi_dung_id,
        ngay,
        ngay - stt::integer AS khoa_day
    FROM ngay_danh_so
),
cac_day AS (
    SELECT
        nguoi_dung_id,
        MIN(ngay) AS tu_ngay,
        MAX(ngay) AS den_ngay,
        COUNT(*) AS so_ngay
    FROM co_khoa_day
    GROUP BY nguoi_dung_id, khoa_day
),
day_xep_hang AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY nguoi_dung_id
            ORDER BY so_ngay DESC, den_ngay DESC, tu_ngay DESC
        ) AS thu_hang
    FROM cac_day
)
SELECT nguoi_dung_id, tu_ngay, den_ngay, so_ngay
FROM day_xep_hang
WHERE thu_hang = 1
ORDER BY nguoi_dung_id;
~~~

Người 101 có **hai dãy dài 3 ngày**: 01–03/10 và 12–14/10. Truy vấn trên có tiêu chí **khi đồng độ dài thì lấy dãy kết thúc muộn hơn**, nên chọn **12–14/10**. Nếu nghiệp vụ cần trả **mọi dãy đồng dài nhất**, hãy dùng `RANK()` hoặc điều kiện so sánh với `MAX` thay vì `ROW_NUMBER() = 1`.

### 11.2. “Streak hiện tại” khác “streak dài nhất trong lịch sử”

Dãy dài nhất của người 101 là 3 ngày, nhưng **ngày cuối có hoạt động của người đó là 20/10**, chỉ tạo một dãy 1 ngày. Nếu cần streak **tính đến một ngày báo cáo**, phải xác định xem người dùng có hoạt động trong ngày đó hoặc ngày được phép tính gần nhất không.

Ví dụ một báo cáo tại `DATE '2026-10-20'` có thể yêu cầu streak kết thúc **đúng ngày 20/10**. Khi ấy nên lọc các dãy có `den_ngay = DATE '2026-10-20'` sau khi đã tính dãy trên lịch sử phù hợp. Không mặc định “dãy cuối trong dữ liệu” luôn là “streak tính đến hôm nay”, vì dữ liệu có thể chưa cập nhật hoặc người dùng đã nghỉ nhiều ngày.

## 12. Tìm ngày thiếu bằng lịch chuẩn

Mẫu `LAG` nhận diện **khoảng ngày nằm giữa hai ngày đã ghi nhận**. Nếu muốn biết **từng ngày còn thiếu** trong một khoảng báo cáo, dùng một lịch chuẩn.

Ví dụ: kiểm tra hoạt động người 101 **từ 01/10 đến 14/10**, bao gồm cả hai đầu:

~~~sql
WITH lich_ngay AS (
    SELECT gs::date AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01 00:00:00',
        TIMESTAMP '2026-10-14 00:00:00',
        INTERVAL '1 day'
    ) AS gs
)
SELECT
    l.ngay AS ngay_khong_co_hoat_dong
FROM lich_ngay AS l
WHERE NOT EXISTS (
    SELECT 1
    FROM hoat_dong_ngay_gap AS a
    WHERE a.nguoi_dung_id = 101
      AND a.ngay = l.ngay
)
ORDER BY l.ngay;
~~~

Kết quả:

~~~text
04/10, 05/10, 08/10, 09/10, 11/10
~~~

**Điểm khác với khoảng trống bên trong dữ liệu:** lịch chuẩn có thể chỉ ra ngày ở đầu hoặc cuối phạm vi ngay cả khi không có bản ghi nào gần đó. Ví dụ nếu mở phạm vi tới 22/10, nó cũng tìm ra 21/10 và 22/10 thiếu, dù trong bảng của người 101 mốc cuối cùng chỉ là 20/10.

### 12.1. Lịch cho tất cả người dùng

Để kiểm tra **mọi người dùng, kể cả người chưa hoạt động lần nào**, có thể tạo lưới người dùng × ngày:

~~~sql
WITH lich_ngay AS (
    SELECT gs::date AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01 00:00:00',
        TIMESTAMP '2026-10-07 00:00:00',
        INTERVAL '1 day'
    ) AS gs
),
moi_nguoi_moi_ngay AS (
    SELECT
        u.id AS nguoi_dung_id,
        u.ten,
        l.ngay
    FROM nguoi_dung_gap AS u
    CROSS JOIN lich_ngay AS l
)
SELECT
    x.nguoi_dung_id,
    x.ten,
    x.ngay
FROM moi_nguoi_moi_ngay AS x
WHERE NOT EXISTS (
    SELECT 1
    FROM hoat_dong_ngay_gap AS a
    WHERE a.nguoi_dung_id = x.nguoi_dung_id
      AND a.ngay = x.ngay
)
ORDER BY x.nguoi_dung_id, x.ngay;
~~~

Trong phạm vi bảy ngày và bốn người, CTE `moi_nguoi_moi_ngay` có **28 dòng kỳ vọng**. Người 104 không có hoạt động nên xuất hiện với **cả bảy ngày thiếu**.

**Cảnh báo về quy mô:** lưới 100.000 người × 365 ngày tạo **36,5 triệu dòng** chỉ để bắt đầu so sánh. Với báo cáo lớn, nên giới hạn người, thời gian, phân vùng dữ liệu hoặc dùng bảng lịch/bảng tổng hợp thích hợp.

### 12.2. Ngày thiếu bản ghi không nhất thiết là ngày vi phạm

Một ngày không có hoạt động có thể là ngày nghỉ, ngày hệ thống ngừng thu thập hoặc người dùng chưa đăng ký. Nếu yêu cầu là **ngày làm việc bắt buộc**, phải nối với **bảng lịch làm việc** và chỉ kiểm tra những ngày được xác định là bắt buộc. Sinh mọi ngày theo lịch dương không tự cho biết quy định nghiệp vụ.

## 13. Gaps theo ngày chỉ làm việc và ngày lễ

Với ngày làm việc, bước liên tục có thể không cố định theo phép `ngay + 1`. Ví dụ thứ Sáu và thứ Hai kế tiếp **không kề nhau theo lịch**, nhưng có thể **liên tiếp theo lịch làm việc** nếu thứ Bảy, Chủ Nhật là ngày nghỉ.

Một mẫu tổng quát là tạo bảng lịch:

~~~sql
-- Bảng lich_lam_viec sau đây là ví dụ về mô hình, chưa được tạo
-- trong bộ dữ liệu thực hành.
-- Các cột: ngay DATE, la_ngay_lam_viec BOOLEAN,
--           thu_tu_ngay_lam_viec INTEGER
~~~

Ý tưởng:

1. Xây bảng `lich_lam_viec` có mỗi ngày một hàng, đánh dấu cuối tuần/ngày lễ/ca nghỉ theo **tổ chức**.
2. Gán số thứ tự **chỉ cho các ngày làm việc**: `1,2,3,...`.
3. JOIN các hoạt động với lịch làm việc để lấy `thu_tu_ngay_lam_viec`.
4. Áp dụng công thức **số thứ tự làm việc trừ `ROW_NUMBER()`** cho những ngày được ghi nhận.

Mẫu:

~~~sql
-- Chỉ là mẫu khi đã có bảng lịch phù hợp.
WITH ngay_hoat_dong_hop_le AS (
    SELECT DISTINCT
        a.nguoi_dung_id,
        l.thu_tu_ngay_lam_viec
    FROM hoat_dong_ngay_gap AS a
    JOIN lich_lam_viec AS l
      ON l.ngay = a.ngay
    WHERE l.la_ngay_lam_viec = TRUE
),
co_so_thu_tu AS (
    SELECT
        nguoi_dung_id,
        thu_tu_ngay_lam_viec,
        ROW_NUMBER() OVER (
            PARTITION BY nguoi_dung_id
            ORDER BY thu_tu_ngay_lam_viec
        ) AS rn
    FROM ngay_hoat_dong_hop_le
)
SELECT
    nguoi_dung_id,
    MIN(thu_tu_ngay_lam_viec) AS tu_thu_tu,
    MAX(thu_tu_ngay_lam_viec) AS den_thu_tu,
    COUNT(*) AS so_ngay_lam_viec_lien_tiep
FROM co_so_thu_tu
GROUP BY nguoi_dung_id, thu_tu_ngay_lam_viec - rn
ORDER BY nguoi_dung_id, tu_thu_tu;
~~~

Không chạy nguyên văn nếu chưa có bảng `lich_lam_viec` với các cột đúng kiểu. Mục đích ở đây là **thay đơn vị bước 1 của dãy ngày dương lịch bằng bước 1 của dãy ngày làm việc**.

## 14. Nhiều chuỗi độc lập: khóa ghép và phạm vi tổ chức

Trong thực tế, một mã số phiếu có thể được cấp **riêng cho từng tổ chức và từng bộ phận**. Khi đó khóa định danh có thể là `(to_chuc_id, bo_phan_id, so_phieu)`.

Mẫu cửa sổ tương ứng:

~~~sql
-- Minh họa trên bảng phieu_da_to_chuc giả định.
SELECT
    to_chuc_id,
    bo_phan_id,
    so_phieu,
    LAG(so_phieu) OVER (
        PARTITION BY to_chuc_id, bo_phan_id
        ORDER BY so_phieu
    ) AS so_truoc
FROM phieu_da_to_chuc;
~~~

Nếu chỉ `PARTITION BY bo_phan_id`, các số phiếu của hai tổ chức trùng mã bộ phận có thể bị trộn thành một chuỗi. Kết quả phát hiện gap hoặc island khi đó **sai phạm vi dữ liệu**.

**Quy tắc:** mọi cột xác định “một chuỗi độc lập” cần được cân nhắc trong `PARTITION BY` và `GROUP BY` kết quả. Không coi cột số phiếu có cùng tên hoặc cùng kiểu là một chuỗi chung nếu business key của chúng khác nhau.

## 15. LAG, ROW_NUMBER và dữ liệu trùng

Mẫu gaps-and-islands rất nhạy với **dữ liệu bị trùng ở mức chi tiết đang phân tích**.

Giả sử bảng sự kiện thô có các số:

~~~text
1, 2, 2, 3, 6, 7
~~~

Nếu dùng `ROW_NUMBER()` trực tiếp:

| Số | RN theo số | Số - RN |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 2 | 3 | -1 |
| 3 | 4 | -1 |
| 6 | 5 | 1 |
| 7 | 6 | 1 |

Hai số 2 bị đánh số **khác nhau**, khiến khóa nhóm thay đổi ngay trong dãy `1,2,3`. Một dòng số 3 thậm chí có thể bị nhóm chung với một dòng số 2 khác, thay vì dãy hợp lệ.

Khắc phục bằng cách lấy **giá trị duy nhất theo partition** trước:

~~~sql
-- Mẫu khi nguồn là bảng thô có thể trùng:
WITH phieu_khong_trung AS (
    SELECT DISTINCT bo_phan_id, so_phieu
    FROM bang_phieu_tho
),
co_rn AS (
    SELECT
        bo_phan_id,
        so_phieu,
        ROW_NUMBER() OVER (
            PARTITION BY bo_phan_id
            ORDER BY so_phieu
        ) AS rn
    FROM phieu_khong_trung
)
SELECT
    bo_phan_id,
    MIN(so_phieu) AS tu_so,
    MAX(so_phieu) AS den_so
FROM co_rn
GROUP BY bo_phan_id, so_phieu::bigint - rn
ORDER BY bo_phan_id, tu_so;
~~~

`bang_phieu_tho` là tên bảng **giả định** để diễn giải lỗi trùng, không thuộc bộ dữ liệu đã tạo. Bảng `so_phieu_gap` ở mục 2 có khóa chính nên bản thân nó **không chứa hai hàng trùng cùng bộ phận và số phiếu**.

### 15.1. DENSE_RANK có thay DISTINCT được không?

Với các giá trị trùng nhau, `DENSE_RANK()` gán cùng thứ hạng cho các hàng đồng giá trị. Điều đó có thể hỗ trợ tạo khóa nhóm không bị thay đổi bởi bản ghi trùng, nhưng **`COUNT(*)` sau đó vẫn đếm cả những bản ghi trùng**. Nếu cần **số giá trị khác biệt** hoặc **số ngày khác biệt** trong một dãy, cách rõ nhất thường là chuẩn hóa nguồn về một hàng mỗi giá trị bằng `DISTINCT` hoặc `GROUP BY`, rồi mới áp dụng thuật toán.

### 15.2. NULL trong giá trị của chuỗi

`ROW_NUMBER` vẫn gán số thứ tự cho hàng có `NULL` nếu nó đi vào cửa sổ, nhưng phép `gia_tri - rn` trả `NULL` khi `gia_tri IS NULL`, khiến khóa nhóm không có ý nghĩa liên tục số học. Với các cột định nghĩa chuỗi, nên xác định **giá trị hợp lệ, không NULL và ràng buộc duy nhất** trước khi tính. Không dùng `COALESCE(gia_tri,0)` tùy tiện vì có thể biến dữ liệu thiếu thành giá trị số 0 thật.

## 16. Dãy tăng theo bước khác 1

Không phải dãy liên tục nào cũng tăng 1. Ví dụ cảm biến phát mỗi **5 phút**, hoặc mã phiếu hợp lệ `100, 105, 110, 120, 125`.

Nếu bước hợp lệ là `5`, ta có thể so sánh:

~~~sql
LAG(gia_tri) OVER (... ORDER BY gia_tri)
~~~

và bắt đầu dãy mới khi:

~~~sql
gia_tri - gia_tri_truoc <> 5
~~~

Miễn là giá trị được sắp xếp tăng và đã loại trùng theo ngữ nghĩa, có thể tạo khóa nhóm:

\[
\text{khóa dãy} = \text{giá trị} - 5 \times \text{ROW_NUMBER()}.
\]

Ví dụ PostgreSQL độc lập:

~~~sql
WITH so_mau(gia_tri) AS (
    VALUES (100), (105), (110), (120), (125)
),
co_stt AS (
    SELECT
        gia_tri,
        ROW_NUMBER() OVER (ORDER BY gia_tri) AS rn
    FROM so_mau
),
co_khoa AS (
    SELECT
        gia_tri,
        gia_tri::bigint - 5 * rn AS khoa_day
    FROM co_stt
)
SELECT
    MIN(gia_tri) AS tu_so,
    MAX(gia_tri) AS den_so,
    COUNT(*) AS so_phan_tu
FROM co_khoa
GROUP BY khoa_day
ORDER BY tu_so;
~~~

Kết quả: dãy **100–110** gồm 3 phần tử và dãy **120–125** gồm 2 phần tử. Các số 115 chưa có, nên không thể gộp hai dãy.

### 16.1. Khi bước tăng không cố định

Nếu hệ thống làm việc theo lịch ca, giờ mở cửa, ngày lễ hay khoảng giờ biến đổi, công thức `gia_tri - buoc * rn` không còn đủ. Nên ánh xạ về một **thứ tự nghiệp vụ hợp lệ**, ví dụ `thu_tu_ca`, `thu_tu_ngay_lam_viec`, rồi nhóm theo thứ tự đó; hoặc dùng cờ đầu dãy với điều kiện kết nối do nghiệp vụ định nghĩa.

## 17. Dãy theo trạng thái và điều kiện kết hợp

Một nhật ký có thể ghi trạng thái theo ngày:

~~~sql
CREATE TEMP TABLE trang_thai_ngay_gap (
    thiet_bi_id INTEGER NOT NULL,
    ngay DATE NOT NULL,
    trang_thai TEXT NOT NULL,
    PRIMARY KEY (thiet_bi_id, ngay)
);

INSERT INTO trang_thai_ngay_gap
    (thiet_bi_id, ngay, trang_thai)
VALUES
    (1, DATE '2026-10-01', 'ON'),
    (1, DATE '2026-10-02', 'ON'),
    (1, DATE '2026-10-03', 'OFF'),
    (1, DATE '2026-10-04', 'OFF'),
    (1, DATE '2026-10-06', 'OFF'),
    (1, DATE '2026-10-07', 'ON'),
    (1, DATE '2026-10-08', 'ON'),
    (2, DATE '2026-10-01', 'ON'),
    (2, DATE '2026-10-03', 'ON');
~~~

Yêu cầu: **một dãy chỉ liên tục khi vừa liền ngày, vừa cùng trạng thái**. Thiết bị 1 có các dãy:

~~~text
01–02/10: ON
03–04/10: OFF
06/10:    OFF  (tách vì thiếu 05/10)
07–08/10: ON
~~~

Nếu chỉ `PARTITION BY thiet_bi_id, trang_thai`, tất cả ngày `ON` có thể bị nhóm theo những quy tắc khác khi trạng thái `ON` quay lại sau `OFF`. Một cách tổng quát và rõ hơn là xác định **điểm cắt theo cả hai điều kiện**:

~~~sql
WITH co_hang_truoc AS (
    SELECT
        thiet_bi_id,
        ngay,
        trang_thai,
        LAG(ngay) OVER (
            PARTITION BY thiet_bi_id
            ORDER BY ngay
        ) AS ngay_truoc,
        LAG(trang_thai) OVER (
            PARTITION BY thiet_bi_id
            ORDER BY ngay
        ) AS trang_thai_truoc
    FROM trang_thai_ngay_gap
),
co_dau_day AS (
    SELECT
        *,
        CASE
            WHEN ngay_truoc IS NULL THEN 1
            WHEN ngay > ngay_truoc + 1 THEN 1
            WHEN trang_thai IS DISTINCT FROM trang_thai_truoc THEN 1
            ELSE 0
        END AS bat_dau_day
    FROM co_hang_truoc
),
co_ma_day AS (
    SELECT
        *,
        SUM(bat_dau_day) OVER (
            PARTITION BY thiet_bi_id
            ORDER BY ngay
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS ma_day
    FROM co_dau_day
)
SELECT
    thiet_bi_id,
    MIN(ngay) AS tu_ngay,
    MAX(ngay) AS den_ngay,
    MIN(trang_thai) AS trang_thai,
    COUNT(*) AS so_ngay
FROM co_ma_day
GROUP BY thiet_bi_id, ma_day
ORDER BY thiet_bi_id, tu_ngay;
~~~

`MIN(trang_thai)` trong kết quả là hợp lý ở **bộ dữ liệu và quy tắc này** vì mỗi `ma_day` được tạo sao cho mọi hàng trong dãy có **cùng trạng thái**. Nó không có nghĩa tổng quát rằng `MIN` là cách chọn trạng thái đúng nếu điều kiện cờ sai.

### 17.1. Ngày liền nhau nhưng trạng thái khác nhau

Ngày 02/10 và 03/10 của thiết bị 1 cách nhau đúng một ngày, nhưng `ON → OFF`, nên phải chia dãy. Ngày 04/10 và 06/10 đều `OFF` nhưng cách hai ngày nên cũng phải chia. Từ đó thấy rõ **tên “dãy liên tục” luôn cần định nghĩa điều kiện liền nhau**.

## 18. Khoảng thời gian: khác với những điểm số rời rạc

Đến đây, mỗi hàng nguồn có thể xem như **một điểm** trên trục số hoặc thời gian. Nhiều hệ thống lại lưu **khoảng thời gian có bắt đầu và kết thúc**:

- Phòng được đặt từ 09:00 đến 10:00;
- Phòng khác được đặt từ 09:30 đến 09:45;
- Một phiên làm việc kéo dài từ 10:00 đến 11:00.

Lúc này cần quyết định:

1. Hai khoảng **chồng lấn** có được hợp nhất?
2. Hai khoảng **chạm biên** (khoảng A kết thúc đúng lúc khoảng B bắt đầu) có được coi là liên tục?
3. Biên kết thúc có được tính là thuộc khoảng hay không?

Một lựa chọn phổ biến là dùng **khoảng nửa mở** `[bat_dau, ket_thuc)`: bao gồm điểm bắt đầu, **không bao gồm** điểm kết thúc. Với quy tắc này, `[09:00, 10:00)` và `[10:00, 11:00)` **không chồng lấn**, nhưng **liền kề không có khoảng trống**.

### 18.1. Tạo dữ liệu lịch sử đặt phòng

~~~sql
CREATE TEMP TABLE lich_phong_gap (
    id INTEGER PRIMARY KEY,
    phong_id TEXT NOT NULL,
    bat_dau TIMESTAMPTZ NOT NULL,
    ket_thuc TIMESTAMPTZ NOT NULL,
    CHECK (ket_thuc > bat_dau)
);

INSERT INTO lich_phong_gap
    (id, phong_id, bat_dau, ket_thuc)
VALUES
    (1, 'A',
     TIMESTAMPTZ '2026-10-01 09:00:00+07',
     TIMESTAMPTZ '2026-10-01 10:00:00+07'),
    (2, 'A',
     TIMESTAMPTZ '2026-10-01 09:30:00+07',
     TIMESTAMPTZ '2026-10-01 09:45:00+07'),
    (3, 'A',
     TIMESTAMPTZ '2026-10-01 10:00:00+07',
     TIMESTAMPTZ '2026-10-01 11:00:00+07'),
    (4, 'A',
     TIMESTAMPTZ '2026-10-01 12:00:00+07',
     TIMESTAMPTZ '2026-10-01 12:30:00+07'),
    (5, 'A',
     TIMESTAMPTZ '2026-10-01 12:15:00+07',
     TIMESTAMPTZ '2026-10-01 13:00:00+07'),
    (6, 'A',
     TIMESTAMPTZ '2026-10-01 14:00:00+07',
     TIMESTAMPTZ '2026-10-01 14:30:00+07'),
    (7, 'B',
     TIMESTAMPTZ '2026-10-01 09:00:00+07',
     TIMESTAMPTZ '2026-10-01 09:15:00+07'),
    (8, 'B',
     TIMESTAMPTZ '2026-10-01 09:30:00+07',
     TIMESTAMPTZ '2026-10-01 10:00:00+07');
~~~

Với phòng A:

~~~text
09:00       10:00       11:00       12:00       13:00       14:00   14:30
|-------------|-----------|            |-----------|            |-------|
   [1]       [3]                      [4] + [5]                  [6]
     [2] nằm trọn bên trong [1]
<--- khoảng bận 09:00–11:00 --->  gap  <--- 12:00–13:00 --> gap <14:00–14:30>
~~~

Theo quy tắc **hợp nhất khoảng chồng lấn hoặc chạm biên**, phòng A có ba khoảng bận:

- 09:00–11:00 (các dòng 1, 2, 3);
- 12:00–13:00 (các dòng 4, 5);
- 14:00–14:30 (dòng 6).

Hai khoảng trống **bên trong lịch đã biết** là 11:00–12:00 và 13:00–14:00. Phòng B có khoảng trống 09:15–09:30.

## 19. Vì sao LAG(ket_thuc) chưa đủ để hợp nhất khoảng?

Một ý tưởng ban đầu là: sắp theo `bat_dau`, rồi dùng `LAG(ket_thuc)` để so điểm bắt đầu của khoảng hiện tại với điểm kết thúc **ngay trước**. Tuy nhiên dữ liệu lồng nhau cho thấy cách này dễ sai.

Ví dụ phòng A:

| ID | Bắt đầu | Kết thúc |
| ---: | --- | --- |
| 1 | 09:00 | 10:00 |
| 2 | 09:30 | 09:45 |
| 3 | 10:00 | 11:00 |

Với dòng 3, `LAG(ket_thuc)` của dòng 2 là **09:45**, còn dòng 3 bắt đầu **10:00**, trông như có gap 15 phút. Nhưng **dòng 1** kéo dài đến **10:00**, nối liền với dòng 3. Toàn bộ chuỗi **không có khoảng trống**.

Do đó, khi hợp nhất các khoảng **có thể chồng lấn hoặc lồng nhau**, cần so `bat_dau` hiện tại với **điểm kết thúc xa nhất của mọi khoảng đứng trước**, không chỉ với `ket_thuc` của đúng một hàng trước.

### 19.1. Tính điểm kết thúc lớn nhất của các hàng đứng trước

~~~sql
SELECT
    phong_id,
    id,
    bat_dau,
    ket_thuc,
    MAX(ket_thuc) OVER (
        PARTITION BY phong_id
        ORDER BY bat_dau, ket_thuc, id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND 1 PRECEDING
    ) AS ket_thuc_xa_nhat_truoc
FROM lich_phong_gap
ORDER BY phong_id, bat_dau, ket_thuc, id;
~~~

Đây là **running maximum của các hàng trước**, được tính bằng khung cửa sổ kết thúc ở `1 PRECEDING` để **không tính chính hàng hiện tại**.

Với phòng A, dòng 3 được so với điểm kết thúc lớn nhất **10:00** (từ dòng 1), nên `bat_dau = 10:00` **không phải điểm mở dãy mới** theo chính sách chạm biên được hợp nhất.

### 19.2. Đánh dấu đầu khoảng bận mới

~~~sql
WITH co_max_truoc AS (
    SELECT
        *,
        MAX(ket_thuc) OVER (
            PARTITION BY phong_id
            ORDER BY bat_dau, ket_thuc, id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND 1 PRECEDING
        ) AS max_ket_thuc_truoc
    FROM lich_phong_gap
),
co_dau_nhom AS (
    SELECT
        *,
        CASE
            WHEN max_ket_thuc_truoc IS NULL THEN 1
            WHEN bat_dau > max_ket_thuc_truoc THEN 1
            ELSE 0
        END AS bat_dau_nhom_moi
    FROM co_max_truoc
),
co_ma_nhom AS (
    SELECT
        *,
        SUM(bat_dau_nhom_moi) OVER (
            PARTITION BY phong_id
            ORDER BY bat_dau, ket_thuc, id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS ma_nhom
    FROM co_dau_nhom
)
SELECT
    phong_id,
    MIN(bat_dau) AS bat_dau_hop_nhat,
    MAX(ket_thuc) AS ket_thuc_hop_nhat,
    COUNT(*) AS so_khoang_goc
FROM co_ma_nhom
GROUP BY phong_id, ma_nhom
ORDER BY phong_id, bat_dau_hop_nhat;
~~~

Kết quả (hiển thị giờ địa phương `+07` để dễ đọc):

| Phòng | Bắt đầu hợp nhất | Kết thúc hợp nhất | Số khoảng gốc |
| --- | --- | --- | ---: |
| A | 01/10 09:00 | 01/10 11:00 | 3 |
| A | 01/10 12:00 | 01/10 13:00 | 2 |
| A | 01/10 14:00 | 01/10 14:30 | 1 |
| B | 01/10 09:00 | 01/10 09:15 | 1 |
| B | 01/10 09:30 | 01/10 10:00 | 1 |

**Điều kiện `bat_dau > max_ket_thuc_truoc`** coi hai khoảng chạm biên là **liền nhau**, nên không tách 09:00–10:00 và 10:00–11:00. Nếu nghiệp vụ muốn **chỉ hợp nhất khoảng thực sự chồng lấn, không hợp nhất khoảng chạm biên**, cần xem xét dùng phép so sánh `>=` thay vì `>` để bắt đầu nhóm mới tại điểm chạm. Chính sách biên phải được nói rõ trước.

### 19.3. Vì sao phải có điều kiện dừng của running MAX?

Nếu dùng:

~~~sql
MAX(ket_thuc) OVER (
    PARTITION BY phong_id
    ORDER BY bat_dau, ket_thuc, id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

thì giá trị max bao gồm **khoảng hiện tại**. Vì khoảng hợp lệ có `ket_thuc > bat_dau`, phép so `bat_dau > max` hầu như không thể phát hiện điểm mở nhóm mới. Cần lấy **max kết thúc của các khoảng trước**, dùng `1 PRECEDING`, để biết có cầu nối từ lịch sử hay không.

## 20. Tìm khoảng trống giữa các khoảng thời gian đã hợp nhất

Khi đã hợp nhất lịch bận, mỗi hàng đại diện cho **một khoảng chiếm dụng không có lỗ bên trong**. Lúc này có thể dùng `LEAD(bat_dau_hop_nhat)` để tìm **khoảng trống từ cuối khoảng hiện tại đến đầu khoảng kế tiếp**.

~~~sql
WITH co_max_truoc AS (
    SELECT
        *,
        MAX(ket_thuc) OVER (
            PARTITION BY phong_id
            ORDER BY bat_dau, ket_thuc, id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND 1 PRECEDING
        ) AS max_ket_thuc_truoc
    FROM lich_phong_gap
),
co_dau_nhom AS (
    SELECT
        *,
        CASE
            WHEN max_ket_thuc_truoc IS NULL
              OR bat_dau > max_ket_thuc_truoc
                THEN 1 ELSE 0
        END AS dau_nhom
    FROM co_max_truoc
),
co_ma_nhom AS (
    SELECT
        *,
        SUM(dau_nhom) OVER (
            PARTITION BY phong_id
            ORDER BY bat_dau, ket_thuc, id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS ma_nhom
    FROM co_dau_nhom
),
khoang_ban AS (
    SELECT
        phong_id,
        MIN(bat_dau) AS tu_luc,
        MAX(ket_thuc) AS den_luc
    FROM co_ma_nhom
    GROUP BY phong_id, ma_nhom
),
co_khoang_sau AS (
    SELECT
        phong_id,
        den_luc AS bat_dau_ranh,
        LEAD(tu_luc) OVER (
            PARTITION BY phong_id
            ORDER BY tu_luc
        ) AS ket_thuc_ranh
    FROM khoang_ban
)
SELECT
    phong_id,
    bat_dau_ranh AS trong_tu_luc,
    ket_thuc_ranh AS trong_den_truoc_luc,
    ket_thuc_ranh - bat_dau_ranh AS do_dai_khoang_trong
FROM co_khoang_sau
WHERE ket_thuc_ranh > bat_dau_ranh
ORDER BY phong_id, trong_tu_luc;
~~~

Kết quả gồm ba khoảng trống **nằm giữa các lịch bận đã ghi nhận**:

| Phòng | Trống từ | Trống đến trước | Độ dài |
| --- | --- | --- | --- |
| A | 01/10 11:00 | 01/10 12:00 | 1 giờ |
| A | 01/10 13:00 | 01/10 14:00 | 1 giờ |
| B | 01/10 09:15 | 01/10 09:30 | 15 phút |

Giống bài toán số nguyên, `LEAD` không tự tìm khoảng trống **trước lịch đầu tiên hoặc sau lịch cuối cùng**. Để tìm phòng trống từ **08:00 đến 18:00**, cần khai báo thời gian hoạt động và lấy giao giữa lịch bận với cửa sổ hoạt động. Khoảng trống ngoài hai đầu chỉ có ý nghĩa trong **phạm vi phục vụ đã định nghĩa**.

### 20.1. Khoảng chồng lấn khác khoảng thiếu

Hai lịch A = `[09:00,10:00)`, B = `[09:30,09:45)` có chồng lấn. Nếu nghiệp vụ **cấm đặt phòng chồng lấn**, câu hỏi đầu tiên phải là **phát hiện vi phạm**, không chỉ hợp nhất và báo phòng bận.

Một mẫu kiểm tra chồng lấn của hai khoảng nửa mở là:

~~~sql
-- Hai khoảng [a.bat_dau, a.ket_thuc)
-- và [b.bat_dau, b.ket_thuc) chồng lấn khi:
-- a.bat_dau < b.ket_thuc
-- AND b.bat_dau < a.ket_thuc
~~~

Điều kiện nghiêm ngặt `<` loại trường hợp chỉ chạm biên khỏi định nghĩa **chồng lấn**, nhưng vẫn cho phép hợp nhất khoảng chạm biên theo chính sách riêng.

### 20.2. PostgreSQL có kiểu RANGE

PostgreSQL hỗ trợ các kiểu miền như `tsrange`, `tstzrange`, `daterange` và các toán tử quan hệ khoảng. Ví dụ:

~~~sql
SELECT
    id,
    phong_id,
    tstzrange(bat_dau, ket_thuc, '[)') AS khoang_ban
FROM lich_phong_gap;
~~~

Toán tử `&&` kiểm tra hai range có chồng lấn, còn `-|- ` (viết liền `-|-`) dùng cho các range kề nhau trong các ngữ cảnh tương ứng. Với yêu cầu **ngăn lịch đặt chồng lấn** ở cấp database, PostgreSQL còn có các phương án như **exclusion constraint** dùng range và toán tử phù hợp. Đây là hướng thiết kế dữ liệu riêng cần xác định khóa phòng, loại range, chỉ mục và quy tắc thời gian chính xác; mẫu CTE ở trên chủ yếu dùng để **phân tích và hợp nhất các khoảng đã lưu**.

## 21. Kết quả thiếu ở đầu/cuối và khoảng quan sát

Trong các bài toán kiểm tra dữ liệu, phần “miền kỳ vọng” thường là yếu tố quyết định:

| Nguồn | Khoảng quan sát | Điều LAG/LEAD tự thấy | Điều cần giới hạn bổ sung |
| --- | --- | --- | --- |
| Số phiếu 1, 2, 3, 6, 7 | 1..10 | Thiếu 4–5 | Thiếu 8–10 nếu 10 là mốc cuối kỳ vọng |
| Hoạt động ngày 01/10 và 03/10 | 01..05/10 | Thiếu 02/10 | Thiếu 04–05/10 ở cuối kỳ |
| Phòng bận 09–10, 12–13 | Giờ mở cửa 08–18 | Trống 10–12 | Trống 08–09 và 13–18 |

Trước khi tính khoảng trống, hãy ghi rõ:

1. **Biên trái** và **biên phải** có được tính vào miền không?
2. **Bước liên tục** là gì: một số nguyên, một ngày, 15 phút, một ca?
3. Có những ngày không bắt buộc hay những đoạn thời gian bị loại trừ?
4. Thế nào là **thiếu dữ liệu** và thế nào là **giá trị 0 hợp lệ**?
5. Cần kết quả theo **từng đối tượng** hay toàn hệ thống?

Nếu thiếu những thông tin đó, câu SQL có thể đúng về cú pháp nhưng trả những “khoảng trống” **không có ý nghĩa nghiệp vụ**.

## 22. Hiệu năng: chọn phương pháp theo loại đầu ra

### 22.1. Khi chỉ cần khoảng trống, đừng sinh mọi giá trị

Nếu bảng có 100.000 số phiếu trong phạm vi 1 đến 1 tỷ, `generate_series(1,1000000000)` sẽ tạo một tập trung gian khổng lồ. Trong khi đó:

~~~sql
LAG(so_phieu) OVER (
    PARTITION BY bo_phan_id ORDER BY so_phieu
)
~~~

chỉ cần xét **những hàng thực sự hiện có** để tìm các khoảng bị nhảy giữa những mốc. Lựa chọn phương pháp phải gắn với yêu cầu:

- **Khoảng thiếu, số lượng thiếu:** thường bắt đầu bằng `LAG`/`LEAD`.
- **Từng giá trị thiếu:** cần miền chuẩn và anti-join, hoặc mở rộng từ các khoảng đã tính với giới hạn kiểm soát.
- **Dãy liên tục:** dùng `ROW_NUMBER` hoặc cờ đầu dãy + `SUM`.
- **Khoảng thời gian chồng lấn:** dùng running `MAX(end)`, không chỉ `LAG(end)`.

### 22.2. Chỉ mục phù hợp

Bảng `so_phieu_gap` đã có `PRIMARY KEY (bo_phan_id, so_phieu)`, nên PostgreSQL tạo chỉ mục duy nhất theo đúng hai cột này. Bảng `hoat_dong_ngay_gap` cũng có khóa chính `(nguoi_dung_id, ngay)`. Chúng phù hợp với nhiều truy vấn phân nhóm theo đối tượng và sắp xếp theo giá trị.

Với bảng lịch:

~~~sql
CREATE INDEX idx_lich_phong_gap_thu_tu
ON lich_phong_gap (phong_id, bat_dau, ket_thuc, id);
~~~

Chỉ mục này **có thể** hữu ích cho các truy vấn xét từng phòng theo thời gian, nhưng không bảo đảm DBMS luôn sử dụng nó. Trên bảng tạm chỉ tám dòng, quét tuần tự và sắp xếp có thể rẻ hơn dùng index.

### 22.3. Kế hoạch thực thi

~~~sql
EXPLAIN
WITH x AS (
    SELECT
        bo_phan_id,
        so_phieu,
        LAG(so_phieu) OVER (
            PARTITION BY bo_phan_id ORDER BY so_phieu
        ) AS so_truoc
    FROM so_phieu_gap
)
SELECT *
FROM x
WHERE so_phieu > so_truoc + 1;
~~~

`EXPLAIN` mô tả kế hoạch dự kiến. Có thể thấy các bước đọc dữ liệu, sắp xếp và `WindowAgg` tùy kế hoạch. Khi đánh giá hệ thống thật, dùng dữ liệu đủ đại diện, thống kê hiện hành và `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường phù hợp; `ANALYZE` thực sự chạy câu truy vấn.

### 22.4. CTE không mặc định lưu vật lý

Các ví dụ chia một phép phân tích thành nhiều CTE để **dễ đọc và diễn đạt bước biến đổi**. PostgreSQL có thể inline hoặc materialize CTE theo phiên bản, đặc tính câu truy vấn và số lần tham chiếu. Không suy rằng mỗi CTE tự động tạo bảng tạm có chỉ mục hoặc rằng nhiều CTE luôn nhanh hơn một truy vấn lồng.

## 23. Khác biệt giữa PostgreSQL, MySQL, SQL Server và Oracle

Tư duy gaps-and-islands có thể chuyển qua nhiều hệ quản trị, nhưng cần đổi cú pháp tạo dãy số, phép cộng trừ ngày, giới hạn đệ quy và một số hàm.

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle Database |
| --- | --- | --- | --- | --- |
| Hàng trước/sau | `LAG`, `LEAD` | `LAG`, `LEAD` trong 8.0+ | `LAG`, `LEAD` | `LAG`, `LEAD` |
| Đánh số / cộng dồn | `ROW_NUMBER`, `SUM OVER` | Window functions 8.0+ | Window functions | Analytic functions |
| Sinh dãy số | `generate_series` | Recursive CTE hoặc bảng số | `GENERATE_SERIES` ở phiên bản/compatibility phù hợp, hoặc bảng số/CTE | `CONNECT BY LEVEL`, recursive subquery factoring |
| Ngày trừ số ngày | `date - integer` | `DATE_SUB(date, INTERVAL n DAY)` | `DATEADD(day, -n, date)` | `DATE - n` với kiểu `DATE` |
| Chênh lệch hai ngày | `date1 - date2` | `DATEDIFF(date1,date2)` | `DATEDIFF(day,date2,date1)` | Phép trừ `DATE` theo ngữ nghĩa Oracle |
| Khoảng thời gian | `INTERVAL`, `tstzrange` | Hàm ngày giờ, kiểu thời gian tương ứng | `datetime2`, `datetimeoffset`, `DATEDIFF` | `DATE`/`TIMESTAMP`, `INTERVAL` |

### 23.1. Mẫu đánh số dãy trên MySQL 8.0+

Với bảng `phieu(bo_phan_id, so_phieu)` đã có dữ liệu duy nhất:

~~~sql
WITH co_rn AS (
    SELECT
        bo_phan_id,
        so_phieu,
        ROW_NUMBER() OVER (
            PARTITION BY bo_phan_id ORDER BY so_phieu
        ) AS rn
    FROM phieu
)
SELECT
    bo_phan_id,
    MIN(so_phieu) AS tu_so,
    MAX(so_phieu) AS den_so,
    COUNT(*) AS do_dai
FROM co_rn
GROUP BY bo_phan_id, so_phieu - rn
ORDER BY bo_phan_id, tu_so;
~~~

Về mặt ý tưởng tương tự PostgreSQL. Với dãy ngày, MySQL dùng `DATE_SUB(ngay, INTERVAL rn DAY)` theo kiểu dữ liệu và cú pháp thích hợp, thay vì dựa vào phép `DATE - INTEGER` của PostgreSQL.

### 23.2. Mẫu nhóm ngày trong SQL Server

Với bảng `dbo.hoat_dong_ngay(nguoi_dung_id, ngay)` đã khử trùng theo ngày:

~~~sql
WITH co_rn AS (
    SELECT
        nguoi_dung_id,
        ngay,
        ROW_NUMBER() OVER (
            PARTITION BY nguoi_dung_id ORDER BY ngay
        ) AS rn
    FROM dbo.hoat_dong_ngay
),
co_khoa AS (
    SELECT
        nguoi_dung_id,
        ngay,
        DATEADD(day, -CAST(rn AS int), ngay) AS khoa_day
    FROM co_rn
)
SELECT
    nguoi_dung_id,
    MIN(ngay) AS tu_ngay,
    MAX(ngay) AS den_ngay,
    COUNT(*) AS so_ngay
FROM co_khoa
GROUP BY nguoi_dung_id, khoa_day;
~~~

Mẫu trên giả định số thứ tự vừa phạm vi `int` khi chuyển kiểu. SQL Server có các khả năng khác nhau tùy phiên bản cho đối số `number` của `DATEADD`; khi xử lý tập cực lớn, cần xác nhận giới hạn kiểu số/phiên bản thay vì ép kiểu không kiểm soát.

### 23.3. Oracle: ngày và số thứ tự

Với cột ngày kiểu `DATE` và dữ liệu đã được chuẩn hóa:

~~~sql
WITH co_rn AS (
    SELECT
        nguoi_dung_id,
        ngay,
        ROW_NUMBER() OVER (
            PARTITION BY nguoi_dung_id ORDER BY ngay
        ) AS rn
    FROM hoat_dong_ngay
)
SELECT
    nguoi_dung_id,
    MIN(ngay) AS tu_ngay,
    MAX(ngay) AS den_ngay,
    COUNT(*) AS so_ngay
FROM co_rn
GROUP BY nguoi_dung_id, ngay - rn;
~~~

Oracle `DATE` có thể chứa cả **phần giờ**. Nếu đang phân tích streak theo ngày, cần chuẩn hóa `TRUNC(ngay)` và khử trùng theo ngày trước khi áp dụng mẹo `ngay - rn`; nếu không, hai thời điểm trong cùng một ngày có thể làm hỏng điều kiện liên tiếp.

### 23.4. Tạo lịch ngày khác nhau giữa các DBMS

PostgreSQL có `generate_series` rất thuận tiện. MySQL thường dùng `WITH RECURSIVE` tạo ngày kế tiếp và phải kiểm soát độ sâu đệ quy; SQL Server có thể dùng bảng lịch, bảng số, CTE đệ quy hoặc `GENERATE_SERIES` khi phiên bản/compatibility phù hợp; Oracle có thể dùng `CONNECT BY LEVEL` hoặc recursive subquery factoring.

Với báo cáo lớn và nhiều quy tắc ngày lễ/ngày làm việc, một **bảng lịch chuẩn** có cột ngày, số thứ tự ngày làm việc, cờ ngày lễ và phạm vi tổ chức thường linh hoạt hơn sinh lịch tạm trong mỗi truy vấn.

## 24. Những lỗi thường gặp

| Sai sót | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Xem hai hàng liền nhau là hai ngày liền nhau | Phát hiện streak ngày sai khi thiếu ngày ở giữa | Dùng `ngay - ngay_truoc = 1` hoặc khóa nhóm ngày |
| Bỏ `PARTITION BY bo_phan_id` | Trộn hai chuỗi số phiếu | Phân nhóm theo đúng khóa nghiệp vụ |
| Bỏ cột tổ chức khi khóa là ghép | Có thể gộp dữ liệu chéo tổ chức | Giữ đủ các thành phần khóa trong window/JOIN |
| Áp dụng `ROW_NUMBER` trực tiếp lên dữ liệu trùng | Một dãy bị tách hoặc đếm sai | `DISTINCT`/`GROUP BY` theo grain trước |
| Coi mọi lỗ số ID là mất dữ liệu | Sequence hoặc ID phân tán không gapless | Chỉ kiểm tra khi có miền kỳ vọng rõ ràng |
| Tìm gap bằng LAG rồi kết luận không thiếu ngoài hai đầu | Không nhìn thấy miền ngoài `MIN..MAX` | Khai báo biên kỳ vọng |
| Sinh hàng tỷ số bằng `generate_series` | Tập trung gian quá lớn | Chọn trả khoảng thiếu, giới hạn miền |
| Dùng `NOT IN` trên tập có `NULL` | Có thể không nhận diện số thiếu | `NOT EXISTS` hoặc xử lý `NULL` có chủ đích |
| Dùng `COUNT(*)` trên nhiều login cùng ngày | Đếm sự kiện thay vì ngày | Khử trùng người–ngày |
| Bỏ múi giờ khi đổi timestamp sang ngày | Streak bị lệch ngày địa phương | Xác định timezone nghiệp vụ |
| Coi cuối tuần là gap vi phạm | Ngày nghỉ có thể không bắt buộc | Dùng lịch làm việc |
| Dùng `LAG(end)` để hợp nhất khoảng lồng nhau | Báo gap giả dù khoảng xa hơn vẫn phủ | Dùng running `MAX(end)` |
| Không xác định biên `[)` hay `[]` | Chạm biên bị coi nhầm là giao nhau hoặc có gap | Định nghĩa nhất quán loại khoảng |
| Thiếu khóa phân xử khi các mốc trùng nhau | Kết quả hàng trước/sau không ổn định | `ORDER BY` thêm khóa có nghĩa |
| Lọc dữ liệu trước window sai thời điểm | Hàng tham chiếu ở đầu phạm vi bị mất | Phân biệt lọc nguồn và lọc kết quả |
| Dùng CTE nhưng không kiểm tra grain đầu ra | Kết quả SUM/COUNT sai | Xác định một hàng đại diện cho gì ở mỗi bước |
| Hiểu CTE luôn materialize | Đánh giá hiệu năng sai | Xem `EXPLAIN` và đặc tính DBMS |

## 25. Bài tập thực hành có lời giải

Các bài tập dưới đây dựa trên bảng `so_phieu_gap`, `hoat_dong_ngay_gap`, `nguoi_dung_gap`, `trang_thai_ngay_gap` và `lich_phong_gap` đã tạo. Hãy tự xác định **phạm vi**, **đơn vị bước** và **grain của đầu ra** trước khi xem đáp án.

### Bài 1. Khoảng thiếu giữa các số phiếu bộ phận 10

**Yêu cầu:** trả mỗi khoảng thiếu bằng `tu_so`, `den_so`, `so_luong` mà không sinh từng giá trị.

**Lời giải:**

~~~sql
WITH x AS (
    SELECT
        so_phieu,
        LAG(so_phieu) OVER (ORDER BY so_phieu) AS so_truoc
    FROM so_phieu_gap
    WHERE bo_phan_id = 10
)
SELECT
    so_truoc + 1 AS tu_so,
    so_phieu - 1 AS den_so,
    so_phieu - so_truoc - 1 AS so_luong
FROM x
WHERE so_phieu > so_truoc + 1
ORDER BY tu_so;
~~~

Kết quả: **4–5 (2 số)**, **8–9 (2 số)**, **11–11 (1 số)**, **15–19 (5 số)**.

### Bài 2. Đổi LAG thành LEAD

**Yêu cầu:** viết lại bài 1 bằng `LEAD`.

**Lời giải:**

~~~sql
WITH x AS (
    SELECT
        so_phieu,
        LEAD(so_phieu) OVER (ORDER BY so_phieu) AS so_sau
    FROM so_phieu_gap
    WHERE bo_phan_id = 10
)
SELECT
    so_phieu + 1 AS tu_so,
    so_sau - 1 AS den_so
FROM x
WHERE so_sau > so_phieu + 1
ORDER BY tu_so;
~~~

Kết quả có **bốn khoảng**, giống bài 1.

### Bài 3. Liệt kê tất cả số thiếu từ 1 đến 20

**Yêu cầu:** mỗi số thiếu là một dòng, chỉ xét bộ phận 10.

**Lời giải:**

~~~sql
SELECT gs.so AS so_thieu
FROM generate_series(1, 20) AS gs(so)
WHERE NOT EXISTS (
    SELECT 1
    FROM so_phieu_gap AS p
    WHERE p.bo_phan_id = 10
      AND p.so_phieu = gs.so
)
ORDER BY gs.so;
~~~

Kết quả: `4,5,8,9,11,15,16,17,18,19`. `NOT EXISTS` so với **miền 1..20 đã xác định**, không chỉ so với mốc có thật.

### Bài 4. Dãy số liên tiếp của bộ phận 20

**Yêu cầu:** nhóm các số `2,3,5,6,8` bằng `ROW_NUMBER`.

**Lời giải:**

~~~sql
WITH x AS (
    SELECT
        so_phieu,
        so_phieu::bigint -
        ROW_NUMBER() OVER (ORDER BY so_phieu) AS khoa_day
    FROM so_phieu_gap
    WHERE bo_phan_id = 20
)
SELECT
    MIN(so_phieu) AS tu_so,
    MAX(so_phieu) AS den_so,
    COUNT(*) AS so_phan_tu
FROM x
GROUP BY khoa_day
ORDER BY tu_so;
~~~

Kết quả **2–3**, **5–6**, **8–8**; độ dài lần lượt 2, 2, 1.

### Bài 5. Đếm số khoảng trống ở từng bộ phận

**Yêu cầu:** đếm **số khoảng gap**, không phải số giá trị thiếu.

**Lời giải:**

~~~sql
WITH x AS (
    SELECT
        bo_phan_id,
        so_phieu,
        LAG(so_phieu) OVER (
            PARTITION BY bo_phan_id ORDER BY so_phieu
        ) AS so_truoc
    FROM so_phieu_gap
)
SELECT
    bo_phan_id,
    COUNT(*) AS so_khoang_trong,
    SUM(so_phieu - so_truoc - 1) AS so_gia_tri_thieu
FROM x
WHERE so_phieu > so_truoc + 1
GROUP BY bo_phan_id
ORDER BY bo_phan_id;
~~~

Bộ phận 10 có **4 khoảng**, **10 giá trị thiếu**; bộ phận 20 có **2 khoảng**, **2 giá trị thiếu**. Hai chỉ tiêu khác nhau.

### Bài 6. Các dãy hoạt động của người 101

**Yêu cầu:** dùng `ngay - ROW_NUMBER` để nhóm các ngày liên tiếp.

**Lời giải:**

~~~sql
WITH x AS (
    SELECT
        ngay,
        ngay - ROW_NUMBER() OVER (ORDER BY ngay)::integer AS khoa_day
    FROM hoat_dong_ngay_gap
    WHERE nguoi_dung_id = 101
)
SELECT
    MIN(ngay) AS tu_ngay,
    MAX(ngay) AS den_ngay,
    COUNT(*) AS so_ngay
FROM x
GROUP BY khoa_day
ORDER BY tu_ngay;
~~~

Kết quả **năm dãy**: 01–03, 06–07, 10, 12–14, 20/10. Dãy dài nhất dài **3 ngày**.

### Bài 7. Khách chưa có hoạt động

**Yêu cầu:** trả tên người không có bất kỳ ngày hoạt động nào.

**Lời giải:**

~~~sql
SELECT u.id, u.ten
FROM nguoi_dung_gap AS u
WHERE NOT EXISTS (
    SELECT 1
    FROM hoat_dong_ngay_gap AS a
    WHERE a.nguoi_dung_id = u.id
)
ORDER BY u.id;
~~~

Kết quả **Dung (104)**. Nếu chỉ truy vấn bảng `hoat_dong_ngay_gap`, sẽ không có hàng nào đại diện cho người 104; cần xuất phát từ **danh sách người dùng**.

### Bài 8. Dãy dài nhất mỗi người, kể cả chưa hoạt động

**Yêu cầu:** một dòng cho mỗi người với số ngày liên tục lớn nhất.

**Lời giải:** Dùng các CTE `ngay_danh_so` → `co_khoa_day` → `cac_day` → `MAX(so_ngay)` như mục 11, rồi `LEFT JOIN` với `nguoi_dung_gap` và `COALESCE(...,0)`.

Kết quả theo ID người `101,102,103,104` là **3,3,1,0**. Cần giữ bảng người làm phía trái để người 104 không bị mất.

### Bài 9. Streak theo ngày đăng nhập thô

Nguồn có hai lần đăng nhập của người 101 vào ngày 01/10. Có thể dùng `ROW_NUMBER` ngay trên tất cả sự kiện để nhóm các ngày không?

**Lời giải:** Không nên. Phải chuẩn hóa sang **một hàng mỗi `nguoi_dung_id, ngay`** bằng `SELECT DISTINCT` hoặc `GROUP BY` trước; nếu không, sự kiện trùng ngày khiến `ROW_NUMBER` tăng hai lần trong khi ngày không tăng, dẫn đến khóa nhóm sai. Ngoài ra, cần xác định múi giờ khi chuyển timestamp sang ngày.

### Bài 10. Khoảng ngày thiếu trong kỳ

**Yêu cầu:** tìm tất cả ngày người 101 không có hoạt động trong **01–07/10**, bao gồm cả hai đầu.

**Lời giải:**

~~~sql
WITH lich AS (
    SELECT gs::date AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01',
        TIMESTAMP '2026-10-07',
        INTERVAL '1 day'
    ) AS gs
)
SELECT l.ngay
FROM lich AS l
WHERE NOT EXISTS (
    SELECT 1
    FROM hoat_dong_ngay_gap AS a
    WHERE a.nguoi_dung_id = 101
      AND a.ngay = l.ngay
)
ORDER BY l.ngay;
~~~

Kết quả: **04/10 và 05/10**. Nếu không có biên kỳ vọng, một truy vấn chỉ dựa vào dữ liệu có thật không tự biết ngày nào ngoài đầu/cuối là bắt buộc.

### Bài 11. Phân biệt khoảng ngày và khoảng phiếu

Ngày hoạt động `2026-10-02` và `2026-10-04` có một ngày thiếu. Nếu dùng công thức `ngay_sau - ngay_truoc - 1` trong PostgreSQL, kết quả bằng mấy?

**Lời giải:** `DATE - DATE` trong PostgreSQL trả **số ngày nguyên**, nên `04/10 - 02/10 = 2`; trừ 1 còn **1 ngày** (03/10). Công thức này đúng cho các ngày dương lịch nguyên và bước một ngày. Với timestamp theo giờ hoặc ngày làm việc thì cần cách tính khác.

### Bài 12. Trạng thái thay đổi và ngày thiếu

**Yêu cầu:** trên `trang_thai_ngay_gap`, tách dãy nếu **trạng thái thay đổi** hoặc **ngày không liền nhau**.

**Lời giải:** Dùng `LAG(ngay)` và `LAG(trang_thai)` theo `PARTITION BY thiet_bi_id ORDER BY ngay`, tạo cờ `1` khi `ngay_truoc IS NULL` hoặc `ngay > ngay_truoc + 1` hoặc `trang_thai IS DISTINCT FROM trang_thai_truoc`; `SUM(co) OVER (... ROWS UNBOUNDED PRECEDING)` làm mã dãy. Với thiết bị 1, kết quả **ON 01–02**, **OFF 03–04**, **OFF 06**, **ON 07–08**.

### Bài 13. Tại sao LAG(end) chưa đủ cho lịch chồng lấn?

Có các khoảng `[09:00,10:00)`, `[09:30,09:45)`, `[10:00,11:00)`. Nếu so điểm bắt đầu khoảng thứ ba với `LAG(end)`, kết quả có cho rằng có khoảng trống không?

**Lời giải:** Có nguy cơ kết luận **sai** rằng có gap từ 09:45 đến 10:00, vì `LAG(end)` trả 09:45 của khoảng lồng bên trong. Thực tế khoảng đầu tiên còn phủ đến 10:00. Cần **`MAX(ket_thuc)` của tất cả hàng trước**, không phải end của một hàng ngay trước.

### Bài 14. Các khoảng bận hợp nhất của phòng A

**Yêu cầu:** dùng quy tắc nửa mở `[)`, hợp nhất những lịch chồng lấn hoặc chạm nhau; đưa ra ranh giới các khoảng bận.

**Lời giải:** Sắp theo `(bat_dau, ket_thuc, id)`, tính `MAX(ket_thuc) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)`, tạo cờ dãy mới khi `bat_dau > max_ket_thuc_truoc`, cộng dồn cờ rồi lấy `MIN(bat_dau)`, `MAX(ket_thuc)`. Phòng A có **09:00–11:00**, **12:00–13:00**, **14:00–14:30**.

### Bài 15. Các khoảng trống giữa lịch bận

**Yêu cầu:** sau khi hợp nhất lịch bận, tìm khoảng trống bên trong của phòng A và B.

**Lời giải:** Với bảng `khoang_ban` một dòng mỗi khoảng bận đã hợp nhất, dùng `LEAD(tu_luc) OVER (PARTITION BY phong_id ORDER BY tu_luc)`, so với `den_luc` và chỉ giữ `LEAD(tu_luc) > den_luc`. Kết quả phòng A **11:00–12:00**, **13:00–14:00**, phòng B **09:15–09:30**. Để tìm trống ở đầu/cuối giờ mở cửa, phải có giới hạn thời gian hoạt động.

### Bài 16. Dãy số tăng bước 5

**Yêu cầu:** nhóm `100,105,110,120,125` thành dãy liên tục theo bước 5.

**Lời giải:** Dùng khóa `gia_tri::bigint - 5 * ROW_NUMBER() OVER (ORDER BY gia_tri)` trên tập đã loại trùng, rồi `GROUP BY` khóa. Kết quả **100–110** gồm 3 phần tử và **120–125** gồm 2 phần tử. Không dùng `gia_tri - ROW_NUMBER()` của bước 1.

### Bài 17. Dữ liệu ID tự tăng có lỗ

Một bảng ghi có ID `101,102,105,108`. Có thể kết luận các bản ghi ID 103,104,106,107 đã bị xóa không?

**Lời giải:** **Không.** Sequence/`IDENTITY` có thể tạo khoảng trống do rollback, cấp trước, cache, giao dịch lỗi, thao tác nhập liệu hoặc kiến trúc phân tán. Kỹ thuật gaps-and-islands chỉ cho biết **các giá trị số không có trong tập quan sát**, không chứng minh nguyên nhân thiếu. Nếu nghiệp vụ cần chứng từ không được đứt số, phải có cơ chế cấp số, trạng thái và kiểm toán riêng.

## 26. Chọn nhanh kỹ thuật phù hợp

| Mục tiêu | Hướng làm | Cảnh báo chính |
| --- | --- | --- |
| Biết **khoảng nào** thiếu số | `LAG`/`LEAD` và so khoảng cách | Không thấy thiếu ngoài biên dữ liệu |
| Biết **mỗi số** thiếu | Miền số chuẩn + `NOT EXISTS` | Kiểm soát kích thước miền |
| Gom dãy số tăng bước 1 | `gia_tri - ROW_NUMBER()` | Giá trị phải không trùng trong partition |
| Gom dãy số bước k | `gia_tri - k * ROW_NUMBER()` | Bước k phải cố định và dữ liệu hợp lệ |
| Gom dãy ngày theo lịch dương | `ngay - rn::integer` | Phải có một hàng mỗi người/ngày |
| Gom dãy theo điều kiện tùy biến | `LAG` + `CASE` + running `SUM` | Định nghĩa rõ điều kiện mở dãy |
| Gom dãy ngày làm việc | Bảng lịch + thứ tự ngày làm việc | Cuối tuần, ngày lễ và phạm vi tổ chức |
| Lấy dãy dài nhất | Tính các dãy rồi `MAX`/`ROW_NUMBER` | Quy định cách xử lý dãy đồng độ dài |
| Thấy người không có sự kiện | `LEFT JOIN` từ bảng người hoặc `NOT EXISTS` | Không thể tìm họ từ bảng sự kiện trống |
| Hợp nhất khoảng thời gian chồng lấn | Running `MAX(ket_thuc)` + cờ mở nhóm | `LAG(end)` đơn lẻ có thể báo gap giả |
| Tìm thời gian rảnh giữa lịch bận | Hợp nhất trước rồi `LEAD(tu_luc)` | Cần giờ mở cửa để tính rảnh hai đầu |
| So sánh dữ liệu nhiều tổ chức | Partition/JOIN theo đầy đủ business key | Tránh trộn hoặc ghép sai phạm vi |

## 27. Kết luận

Mẫu **gaps and islands** giúp trả lời hai câu hỏi đối ngẫu: **“Đâu là phần bị thiếu giữa những giá trị cần liên tục?”** và **“Những giá trị nào tạo thành một dãy không bị ngắt?”**.

Hãy nhớ quy trình tư duy:

1. **Xác định grain:** một hàng là số phiếu, ngày hoạt động, sự kiện hay khoảng thời gian? Khử trùng nếu nhiều hàng cùng biểu diễn một giá trị.
2. **Xác định partition:** các chuỗi của khách hàng, bộ phận, thiết bị hoặc tổ chức nào phải được xét độc lập?
3. **Định nghĩa thế nào là liên tiếp:** chênh 1 số, chênh 1 ngày, bước 5, ngày làm việc, trạng thái giống nhau hay khoảng thời gian chạm/chồng lấn?
4. **Xác định biên kỳ vọng:** `LAG`/`LEAD` chỉ cho thấy gap giữa mốc có thật; muốn tìm thiếu ở đầu/cuối phải có miền chuẩn.
5. **Chọn thuật toán:** `LAG`/`LEAD` để phát hiện gap; `ROW_NUMBER` hoặc cờ + tổng cộng dồn để nhóm islands; `generate_series` với anti-join để liệt kê giá trị thiếu; running `MAX(end)` để hợp nhất các khoảng có thể lồng nhau.
6. **Kiểm tra ngữ nghĩa dữ liệu:** `NULL`, ngày nghỉ, múi giờ, số ID tự sinh và quy tắc biên có thể làm diễn giải “thiếu” khác nhau.
7. **Đo hiệu năng khi dữ liệu lớn:** ưu tiên chỉ tính khoảng nếu chỉ cần ranh giới; dùng khóa/chỉ mục phù hợp, giới hạn miền sinh và xem kế hoạch thực tế.

**Điểm cốt lõi:** SQL có thể phát hiện mọi khoảng nhảy số hay nhóm các đoạn liên tục, nhưng **SQL không tự biết một khoảng nhảy có phải lỗi hay không**. Kết quả đáng tin cậy bắt đầu từ việc định nghĩa **đối tượng so sánh, đơn vị liên tục, phạm vi kỳ vọng và ý nghĩa của dữ liệu thiếu**; sau đó mới chọn kỹ thuật window function, tổng hợp hoặc anti-join thích hợp.
