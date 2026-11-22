# Tổng lũy kế, trung bình trượt và tỷ lệ đóng góp trong SQL

Trong báo cáo hoạt động, một con số riêng lẻ thường chưa đủ để trả lời câu hỏi nghiệp vụ. Tổng tiền ngày 8/10 là 400, nhưng điều quan trọng có thể là **đến ngày đó đã tích lũy bao nhiêu**, **xu hướng ba ngày gần đây tăng hay giảm**, hoặc **danh mục Sách đóng góp bao nhiêu phần trăm vào toàn kỳ**.

Ba mẫu truy vấn thường dùng là:

1. **Tổng lũy kế (*running total/cumulative sum*)**: cộng dồn dữ liệu theo một thứ tự, thường là thời gian.
2. **Trung bình trượt (*moving/rolling average*)**: lấy trung bình của một khung quan sát liên tiếp để theo dõi xu hướng.
3. **Tỷ lệ đóng góp (*contribution percentage/share of total*)**: so sánh giá trị của một hàng hoặc nhóm với tổng của một tập tham chiếu.

Chúng thường được xây dựng từ `SUM`, `AVG`, `GROUP BY` và **hàm cửa sổ** với `OVER`, `PARTITION BY`, `ORDER BY`, `ROWS` hoặc `RANGE`. Điểm quan trọng không chỉ là thuộc cú pháp, mà còn phải xác định đúng **đơn vị phân tích** (giao dịch, ngày, danh mục), **mẫu số** và **ý nghĩa của dữ liệu thiếu**.

Bài thuộc chương **Mẫu truy vấn** của module **Database SQL**. Toàn bộ phần thực hành dùng **PostgreSQL** và bộ dữ liệu thử nghiệm có thể tạo từ đầu. Một số cú pháp khác biệt giữa các DBMS sẽ được trình bày ở phần cuối.

## 1. Hình dung ba chỉ số trên cùng một dãy ngày

Giả sử số tiền ghi nhận trong mười ngày là:

| Ngày tháng 10/2026 | Tổng tiền ngày |
|---|---:|
| 01/10 | 180 |
| 02/10 | 290 |
| 03/10 | 180 |
| 04/10 | 250 |
| 05/10 | 100 |
| 06/10 | 300 |
| 07/10 | 0 |
| 08/10 | 400 |
| 09/10 | 200 |
| 10/10 | 100 |

Tổng toàn kỳ là **2.000**.

### 1.1. Tổng lũy kế

Tại ngày thứ ba:

\[
180+290+180=650
\]

Tại ngày thứ sáu:

\[
180+290+180+250+100+300=1300
\]

Tổng lũy kế trả lời: **“Đến hết ngày này, tổng đã ghi nhận là bao nhiêu?”**

### 1.2. Trung bình trượt ba ngày

Tại ngày 04/10, lấy ngày 02, 03 và 04:

\[
\frac{290+180+250}{3}=240
\]

Tại ngày 08/10, lấy ngày 06, 07 và 08:

\[
\frac{300+0+400}{3}\approx233.33
\]

Trung bình trượt trả lời: **“Trong một khung thời gian hoặc số quan sát gần nhất, mức điển hình là bao nhiêu?”**

### 1.3. Tỷ lệ đóng góp

Ngày 08/10 có tổng 400 trên tổng kỳ 2.000:

\[
\frac{400}{2000}\times100=20\%
\]

Nếu nhóm Sách có tổng 900 trên 2.000:

\[
\frac{900}{2000}\times100=45\%
\]

Tỷ lệ đóng góp trả lời: **“Phần này chiếm bao nhiêu trong tổng tham chiếu?”**

Một giá trị có thể được chia cho **tổng tháng**, **tổng khu vực**, **tổng ngày**, hoặc **tổng danh mục**. Nếu không nói rõ mẫu số, cùng một số tiền có thể tạo nhiều tỷ lệ đều đúng về phép tính nhưng khác ý nghĩa nghiệp vụ.

## 2. Công thức SQL cốt lõi

Giả sử bạn đã có một tập gồm **một hàng cho mỗi ngày**, cột `ngay` và `tong_ngay`:

~~~sql
SELECT
    ngay,
    tong_ngay,

    SUM(tong_ngay) OVER (
        ORDER BY ngay
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke,

    AVG(tong_ngay) OVER (
        ORDER BY ngay
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS trung_binh_3_hang,

    100.0 * tong_ngay
    / NULLIF(SUM(tong_ngay) OVER (), 0)
        AS ty_le_dong_gop

FROM bang_tong_theo_ngay
ORDER BY ngay;
~~~

`bang_tong_theo_ngay` ở đây là tên **nguồn minh họa**. Phần 5 sẽ tạo nguồn tương ứng bằng CTE từ dữ liệu thực hành.

Ba công thức dùng ba phạm vi:

| Chỉ số | Phạm vi tính | Điểm cần lưu ý |
|---|---|---|
| Tổng lũy kế | Từ đầu thứ tự đến dòng hiện tại | Cần `ORDER BY` rõ và frame phù hợp |
| Trung bình trượt ba hàng | Dòng hiện tại cùng tối đa hai dòng trước | `ROWS` đếm **hàng**, chưa chắc là ngày |
| Tỷ lệ đóng góp toàn kỳ | Giá trị của dòng / tổng trên toàn bộ tập | `OVER ()` không chia nhóm; xử lý mẫu số bằng 0 |

Với nhiều nhóm hàng, thêm `PARTITION BY nhom` vào các hàm phù hợp để mỗi nhóm tính độc lập.

## 3. Chuẩn bị dữ liệu thực hành

Ta có một hệ thống nhỏ với bốn nhóm hàng: **Sách**, **Văn phòng phẩm**, **Phụ kiện** và **Dịch vụ**. Nhóm Dịch vụ hiện chưa có giao dịch để minh họa trường hợp danh mục có sẵn nhưng không phát sinh dữ liệu.

**Môi trường:** PostgreSQL, database thử nghiệm, trong cùng một phiên kết nối. Các bảng đều là `TEMP TABLE` nên không phải đối tượng nghiệp vụ vĩnh viễn. Nếu trình quản lý SQL dùng kết nối mới, bạn cần tạo lại bảng tạm.

### 3.1. Danh mục nhóm

~~~sql
CREATE TEMP TABLE pt_nhom (
    ma_nhom VARCHAR(20) PRIMARY KEY,
    ten_nhom VARCHAR(100) NOT NULL,
    thu_tu INTEGER NOT NULL UNIQUE
);

INSERT INTO pt_nhom (ma_nhom, ten_nhom, thu_tu) VALUES
    ('SACH',      'Sách',             1),
    ('VPP',       'Văn phòng phẩm',   2),
    ('PHU_KIEN',  'Phụ kiện',         3),
    ('DICH_VU',   'Dịch vụ',          4);
~~~

### 3.2. Bảng giao dịch

~~~sql
CREATE TEMP TABLE pt_giao_dich (
    id INTEGER PRIMARY KEY,
    ngay DATE NOT NULL,
    ma_nhom VARCHAR(20) NOT NULL
        REFERENCES pt_nhom(ma_nhom),
    so_tien NUMERIC(12,2)
        CHECK (so_tien >= 0)
);
~~~

Một dòng đại diện cho **một giao dịch**, không phải một ngày. Một ngày có thể có nhiều dòng; một nhóm hàng cũng có thể có nhiều giao dịch trong cùng ngày.

Cột `so_tien` cho phép `NULL`. Trong bài, ta giả định:

- `so_tien > 0`: số tiền dương đã ghi nhận.
- `so_tien = 0`: giao dịch có số tiền được xác định là bằng 0.
- `so_tien IS NULL`: giao dịch tồn tại, nhưng số tiền **chưa được xác định**.

Đây là quy ước dữ liệu mẫu. Trong hệ thống thật, không nên coi mọi NULL là tiền bằng 0 nếu chưa có quy tắc nghiệp vụ cho phép.

### 3.3. Nạp dữ liệu Sách

~~~sql
INSERT INTO pt_giao_dich (id, ngay, ma_nhom, so_tien) VALUES
    (101, DATE '2026-10-01', 'SACH', 100),
    (102, DATE '2026-10-02', 'SACH', 200),
    (103, DATE '2026-10-02', 'SACH', 50),
    (104, DATE '2026-10-04', 'SACH', 150),
    (105, DATE '2026-10-05', 'SACH', NULL),
    (106, DATE '2026-10-07', 'SACH', 0),
    (107, DATE '2026-10-08', 'SACH', 300),
    (108, DATE '2026-10-10', 'SACH', 100);
~~~

Sách có **8 giao dịch**, trong đó **7 giao dịch có giá trị tiền**, tổng tiền là:

\[
100+200+50+150+0+300+100=900
\]

Hai giao dịch 102 và 103 cùng ngày 02/10. Giao dịch 105 có tiền NULL; giao dịch 106 có số tiền bằng 0.

### 3.4. Nạp dữ liệu Văn phòng phẩm

~~~sql
INSERT INTO pt_giao_dich (id, ngay, ma_nhom, so_tien) VALUES
    (201, DATE '2026-10-01', 'VPP', 80),
    (202, DATE '2026-10-03', 'VPP', 120),
    (203, DATE '2026-10-04', 'VPP', 100),
    (204, DATE '2026-10-06', 'VPP', 200),
    (205, DATE '2026-10-08', 'VPP', 100),
    (206, DATE '2026-10-09', 'VPP', NULL),
    (207, DATE '2026-10-10', 'VPP', 0);
~~~

Văn phòng phẩm có **7 giao dịch**, **6 giá trị tiền không NULL**, tổng:

\[
80+120+100+200+100+0=600
\]

### 3.5. Nạp dữ liệu Phụ kiện

~~~sql
INSERT INTO pt_giao_dich (id, ngay, ma_nhom, so_tien) VALUES
    (301, DATE '2026-10-02', 'PHU_KIEN', 40),
    (302, DATE '2026-10-03', 'PHU_KIEN', 60),
    (303, DATE '2026-10-05', 'PHU_KIEN', 100),
    (304, DATE '2026-10-06', 'PHU_KIEN', 100),
    (305, DATE '2026-10-09', 'PHU_KIEN', 200),
    (306, DATE '2026-10-10', 'PHU_KIEN', NULL);
~~~

Phụ kiện có **6 giao dịch**, **5 giá trị tiền không NULL**, tổng:

\[
40+60+100+100+200=500
\]

Không có dòng INSERT nào cho nhóm Dịch vụ.

### 3.6. Kiểm tra số lượng và tổng theo nhóm

~~~sql
SELECT
    n.ma_nhom,
    n.ten_nhom,
    COUNT(g.id) AS so_giao_dich,
    COUNT(g.so_tien) AS so_co_tien,
    SUM(g.so_tien) AS tong_chua_thay_null,
    COALESCE(SUM(g.so_tien), 0) AS tong_hien_thi
FROM pt_nhom AS n
LEFT JOIN pt_giao_dich AS g
    ON g.ma_nhom = n.ma_nhom
GROUP BY n.ma_nhom, n.ten_nhom, n.thu_tu
ORDER BY n.thu_tu;
~~~

Kết quả:

| Nhóm | Số giao dịch | Có tiền | SUM gốc | Tổng hiển thị |
|---|---:|---:|---:|---:|
| Sách | 8 | 7 | 900 | 900 |
| Văn phòng phẩm | 7 | 6 | 600 | 600 |
| Phụ kiện | 6 | 5 | 500 | 500 |
| Dịch vụ | 0 | 0 | NULL | 0 |

Tổng trên tất cả giao dịch là **21 hàng**, **18 giá trị tiền không NULL** và **2.000 đơn vị tiền**. Nhóm Dịch vụ được giữ bởi `LEFT JOIN`. Dùng `COUNT(g.id)` thay cho `COUNT(*)` vì khách/nhóm không có giao dịch vẫn có hàng bên trái được giữ lại, nhưng không có giao dịch thực để đếm.

## 4. Xác định cấp dữ liệu trước khi tính chỉ số

Đây là quyết định quan trọng hơn bản thân cú pháp `OVER`.

| Yêu cầu | Cấp hàng cần dùng trước khi tính |
|---|---|
| Tổng lũy kế sau **mỗi giao dịch** | Một hàng/giao dịch, có thứ tự ngày + ID |
| Tổng lũy kế đến **hết mỗi ngày** | Một hàng/ngày, đã cộng giao dịch trong ngày |
| Trung bình **ba giao dịch gần nhất** | Một hàng/giao dịch, `ROWS 2 PRECEDING` |
| Trung bình **ba ngày gần nhất** | Một hàng/ngày, đủ ngày lịch nếu tính theo ba ngày liên tiếp |
| Tỷ lệ **một giao dịch** trong tổng nhóm | Một hàng/giao dịch và tổng nhóm qua window |
| Tỷ lệ **một nhóm hàng** trong toàn kỳ | Một hàng/nhóm sau `GROUP BY` |
| Tỷ lệ **một nhóm hàng trong mỗi ngày** | Một hàng/nhóm/ngày, cộng qua nhóm trong ngày |
| Tỷ lệ **tổng lũy kế** so với toàn kỳ | Một hàng/ngày, tổng lũy kế và tổng kỳ |

Nếu bạn cần một hàng mỗi ngày nhưng truy vấn vẫn có nhiều giao dịch cho một ngày, `AVG` và `SUM` sẽ xử lý các **dòng giao dịch**, không tự hiểu một ngày là một đơn vị quan sát. Đây là nguồn gốc của rất nhiều báo cáo có số đúng về SQL nhưng sai về chỉ số.

## 5. Tạo nguồn một hàng mỗi ngày bằng GROUP BY

Trước khi làm tổng lũy kế và trung bình theo ngày, hãy tổng hợp giao dịch:

~~~sql
SELECT
    ngay,
    COUNT(*) AS so_giao_dich,
    COUNT(so_tien) AS so_co_tien,
    SUM(so_tien) AS tong_ngay_chua_thay_null,
    COALESCE(SUM(so_tien), 0) AS tong_ngay
FROM pt_giao_dich
GROUP BY ngay
ORDER BY ngay;
~~~

Kết quả:

| Ngày | Số giao dịch | Số có tiền | Tổng ngày |
|---|---:|---:|---:|
| 2026-10-01 | 2 | 2 | 180 |
| 2026-10-02 | 3 | 3 | 290 |
| 2026-10-03 | 2 | 2 | 180 |
| 2026-10-04 | 2 | 2 | 250 |
| 2026-10-05 | 2 | 1 | 100 |
| 2026-10-06 | 2 | 2 | 300 |
| 2026-10-07 | 1 | 1 | 0 |
| 2026-10-08 | 2 | 2 | 400 |
| 2026-10-09 | 2 | 1 | 200 |
| 2026-10-10 | 3 | 2 | 100 |

Kiểm tra tổng:

\[
180+290+180+250+100+300+0+400+200+100=2000
\]

### 5.1. Có giao dịch khác với có số tiền

Ngày 05/10 có hai giao dịch, nhưng chỉ giao dịch Phụ kiện 303 có tiền 100; giao dịch Sách 105 có tiền NULL. Tương tự, ngày 09/10 có một giao dịch VPP với tiền NULL và một giao dịch Phụ kiện có tiền 200.

Trong các ngày trên, `SUM` vẫn có ít nhất một giá trị không NULL, nên kết quả không phải NULL. Nhưng khi tổng hợp riêng theo **nhóm/ngày**, có những tổ hợp có giao dịch mà tất cả `so_tien` đều NULL. Ta sẽ giữ cột đếm để phân biệt ở phần 11.

### 5.2. Ngày không có giao dịch không tự xuất hiện

Bảng trên chỉ có ngày 01–10/10. Nếu báo cáo yêu cầu cả **11/10 và 12/10**, `GROUP BY` không tự sinh hai ngày đó. Một phép trung bình trượt trên các hàng trả về lúc này là **trung bình các ngày có bản ghi**, chưa chắc là trung bình trên các ngày lịch.

Khi cần lịch đầy đủ, hãy tạo tập ngày rồi `LEFT JOIN` vào dữ liệu; chi tiết ở phần 10.

## 6. Mẫu 1: tổng lũy kế theo ngày

Truy vấn PostgreSQL tự chứa từ bảng `pt_giao_dich`:

~~~sql
WITH theo_ngay AS (
    SELECT
        ngay,
        COALESCE(SUM(so_tien), 0) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
)
SELECT
    ngay,
    tong_ngay,
    SUM(tong_ngay) OVER (
        ORDER BY ngay
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke
FROM theo_ngay
ORDER BY ngay;
~~~

Kết quả:

| Ngày | Tổng ngày | Tổng lũy kế |
|---|---:|---:|
| 01/10 | 180 | 180 |
| 02/10 | 290 | 470 |
| 03/10 | 180 | 650 |
| 04/10 | 250 | 900 |
| 05/10 | 100 | 1000 |
| 06/10 | 300 | 1300 |
| 07/10 | 0 | 1300 |
| 08/10 | 400 | 1700 |
| 09/10 | 200 | 1900 |
| 10/10 | 100 | 2000 |

### 6.1. Đọc từng phần SQL

~~~sql
SUM(tong_ngay) OVER (
    ORDER BY ngay
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

- `SUM(tong_ngay)` cộng các tổng ngày.
- `OVER` cho biết đây là phép tổng hợp dạng cửa sổ, giữ một hàng trên mỗi ngày.
- `ORDER BY ngay` xếp các ngày để tích lũy.
- `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` lấy từ hàng đầu đến hàng hiện tại.
- Không có `PARTITION BY` nên tổng lũy kế chạy xuyên qua **mọi nhóm hàng** trong tập theo ngày.

Cột tổng lũy kế sau ngày 07/10 không tăng vì tổng của ngày này bằng 0, nhưng **vẫn có một hàng cho ngày 07/10**.

### 6.2. Vì sao nên tổng hợp theo ngày trước?

Bảng nguồn có ba giao dịch vào ngày 02/10. Nếu tính lũy kế trực tiếp theo từng giao dịch, bạn sẽ có **ba mốc trong ngày 02/10**, không phải một tổng cuối ngày.

CTE `theo_ngay` định nghĩa đúng cấp hạt: **một hàng = một ngày**. Sau đó window dễ diễn đạt quy tắc “đến hết mỗi ngày”.

### 6.3. Không cần GROUP BY lại ở truy vấn ngoài

`GROUP BY ngay` đã nằm trong CTE. Khi truy vấn ngoài dùng `SUM(tong_ngay) OVER (...)`, nó không làm gộp các hàng ngày. Câu SQL trả **10 hàng**, mỗi hàng là một ngày.

Nếu thay window bằng `SUM(tong_ngay)` không có `OVER` và không nhóm theo ngày, kết quả sẽ chỉ có **một hàng tổng 2000**, không còn chuỗi lũy kế.

## 7. Tổng lũy kế theo từng giao dịch

Nếu bài toán là **lũy kế sau mỗi giao dịch**, bỏ bước GROUP BY ngày và dùng ngày + ID để tạo thứ tự xác định:

~~~sql
SELECT
    id,
    ngay,
    ma_nhom,
    so_tien,
    SUM(so_tien) OVER (
        ORDER BY ngay, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_sau_giao_dich
FROM pt_giao_dich
ORDER BY ngay, id;
~~~

Với những hàng đầu:

| id | Ngày | Nhóm | Số tiền | Tổng sau giao dịch |
|---:|---|---|---:|---:|
| 101 | 01/10 | SACH | 100 | 100 |
| 201 | 01/10 | VPP | 80 | 180 |
| 102 | 02/10 | SACH | 200 | 380 |
| 103 | 02/10 | SACH | 50 | 430 |
| 301 | 02/10 | PHU_KIEN | 40 | 470 |
| 202 | 03/10 | VPP | 120 | 590 |
| 302 | 03/10 | PHU_KIEN | 60 | 650 |

### 7.1. ORDER BY phải có tiêu chí phá hòa

Ngày 02/10 có ba giao dịch. Nếu chỉ viết:

~~~sql
SUM(so_tien) OVER (
    ORDER BY ngay
)
~~~

các giao dịch **cùng ngày** là *peers* theo ORDER BY. Với aggregate window trong PostgreSQL và frame mặc định khi có ORDER BY, các hàng cùng ngày có thể được đưa **đồng thời** vào tổng lũy kế. Cả ba giao dịch 02/10 sẽ cùng thấy tổng đến hết ngày ấy là 470.

Điều này phù hợp với yêu cầu **tổng cuối ngày**, nhưng khác yêu cầu **sau mỗi giao dịch**.

### 7.2. Frame mặc định: RANGE và các hàng ngang hàng

Trong PostgreSQL, với aggregate window có ORDER BY nhưng không chỉ rõ frame, phạm vi mặc định thường tương đương:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Ở chế độ RANGE, `CURRENT ROW` bao gồm **mọi peers có cùng khóa ORDER BY**, nên khi `ORDER BY ngay`, các giao dịch cùng ngày được nhìn như một nhóm tại ranh giới frame.

Muốn lũy kế từng giao dịch rõ ràng, dùng:

~~~sql
ORDER BY ngay, id
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Vì ID là khóa chính, cặp `(ngay, id)` xác định thứ tự từng giao dịch. `ROWS` mô tả chính xác mục tiêu cộng theo **vị trí hàng**, không phải theo nhóm ngày.

### 7.3. Vì sao tổng lũy kế có thể giữ nguyên khi gặp NULL?

Nếu giao dịch có `so_tien = NULL`, `SUM` bỏ qua giá trị này. Khi frame đã có các số tiền khác NULL trước đó, tổng tích lũy giữ nguyên. Nhưng nếu toàn bộ giá trị trong frame đều NULL, `SUM` trả NULL.

Nếu báo cáo muốn nhìn thấy cả **số giao dịch tích lũy**, thêm một window khác:

~~~sql
SELECT
    id,
    ngay,
    so_tien,
    COUNT(*) OVER (
        ORDER BY ngay, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS so_giao_dich_luy_ke,
    COUNT(so_tien) OVER (
        ORDER BY ngay, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS so_co_tien_luy_ke,
    SUM(so_tien) OVER (
        ORDER BY ngay, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_tien_luy_ke
FROM pt_giao_dich
ORDER BY ngay, id;
~~~

`COUNT(*)` và `COUNT(so_tien)` giúp phân biệt số lượng dòng đã gặp với số lượng giá trị thực sự tham gia tổng.

## 8. Tổng lũy kế theo từng nhóm hàng

Nếu muốn **Sách bắt đầu lũy kế từ 0 riêng, VPP từ 0 riêng**, thêm `PARTITION BY ma_nhom`:

~~~sql
SELECT
    id,
    ma_nhom,
    ngay,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY ma_nhom
        ORDER BY ngay, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke_trong_nhom
FROM pt_giao_dich
ORDER BY ma_nhom, ngay, id;
~~~

Với Sách:

| id | Ngày | Số tiền | Lũy kế Sách |
|---:|---|---:|---:|
| 101 | 01/10 | 100 | 100 |
| 102 | 02/10 | 200 | 300 |
| 103 | 02/10 | 50 | 350 |
| 104 | 04/10 | 150 | 500 |
| 105 | 05/10 | NULL | 500 |
| 106 | 07/10 | 0 | 500 |
| 107 | 08/10 | 300 | 800 |
| 108 | 10/10 | 100 | 900 |

Với VPP, tổng lũy kế cuối nhóm là **600**; với Phụ kiện là **500**.

### 8.1. PARTITION BY không gộp giao dịch

`PARTITION BY ma_nhom` chỉ chia phạm vi tính toán. Số hàng trả về vẫn là **21 giao dịch**, không phải ba dòng tổng theo nhóm.

Nếu bạn muốn **mỗi nhóm một hàng**, cần `GROUP BY ma_nhom`; nếu muốn một hàng mỗi **nhóm và ngày**, cần `GROUP BY ma_nhom, ngay` trước khi tính window.

### 8.2. Nếu nhóm chưa có giao dịch?

Nhóm Dịch vụ có trong `pt_nhom` nhưng không có dòng `pt_giao_dich`. Một SELECT bắt đầu từ bảng giao dịch như trên **không tạo dòng Dịch vụ**. Nếu báo cáo phải hiển thị cả nhóm chưa phát sinh, cần lấy danh mục làm nguồn và `LEFT JOIN`, hoặc tạo **lưới ngày × nhóm** như phần 11.

## 9. Trung bình trượt theo số hàng

Để lấy **trung bình hiện tại và hai quan sát ngay trước**, dùng:

~~~sql
AVG(gia_tri) OVER (
    ORDER BY thu_tu
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
~~~

`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` nghĩa là **tối đa ba hàng**: dòng đang xét + hai dòng đứng trước. Nó không tự có nghĩa là “ba ngày” nếu có ngày trùng hoặc thiếu ngày.

### 9.1. Trung bình trượt ba hàng trên tổng ngày

~~~sql
WITH theo_ngay AS (
    SELECT
        ngay,
        COALESCE(SUM(so_tien), 0) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
)
SELECT
    ngay,
    tong_ngay,
    ROUND(
        AVG(tong_ngay) OVER (
            ORDER BY ngay
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS trung_binh_3_hang
FROM theo_ngay
ORDER BY ngay;
~~~

Kết quả:

| Ngày | Tổng ngày | Trung bình trượt ba hàng |
|---|---:|---:|
| 01/10 | 180 | 180.00 |
| 02/10 | 290 | 235.00 |
| 03/10 | 180 | 216.67 |
| 04/10 | 250 | 240.00 |
| 05/10 | 100 | 176.67 |
| 06/10 | 300 | 216.67 |
| 07/10 | 0 | 133.33 |
| 08/10 | 400 | 233.33 |
| 09/10 | 200 | 200.00 |
| 10/10 | 100 | 233.33 |

### 9.2. Vì sao hai ngày đầu chia cho 1 hoặc 2?

Ở 01/10, chưa có hai ngày trước trong tập dữ liệu → frame chỉ có một hàng → AVG là 180.

Ở 02/10, frame có hai hàng:

\[
(180+290)/2=235
\]

Từ 03/10 trở đi trong dãy mười ngày liên tục, frame thường có ba hàng.

**AVG không tự chia cố định cho 3 ở những frame đầu chưa đủ ba dòng.** Nếu nghiệp vụ bắt buộc trung bình của **đúng ba ngày**, cần chọn chính sách: không báo cho hai ngày đầu, bổ sung dữ liệu lịch trước kỳ, hoặc cố ý giả định các ngày trước có giá trị 0. Đó là ba quyết định khác nhau.

### 9.3. Kiểm soát số hàng trong frame

~~~sql
WITH theo_ngay AS (
    SELECT
        ngay,
        COALESCE(SUM(so_tien), 0) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
)
SELECT
    ngay,
    tong_ngay,
    COUNT(*) OVER (
        ORDER BY ngay
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS so_ngay_trong_frame,
    ROUND(
        AVG(tong_ngay) OVER (
            ORDER BY ngay
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS tb_3_hang
FROM theo_ngay
ORDER BY ngay;
~~~

Cột `so_ngay_trong_frame` lần lượt là 1, 2, rồi 3 từ ngày thứ ba trở đi trong dữ liệu mẫu.

### 9.4. Chỉ hiện trung bình khi đủ ba hàng

~~~sql
WITH theo_ngay AS (
    SELECT
        ngay,
        COALESCE(SUM(so_tien), 0) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
),
co_frame AS (
    SELECT
        ngay,
        tong_ngay,
        COUNT(*) OVER (
            ORDER BY ngay
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS so_ngay,
        AVG(tong_ngay) OVER (
            ORDER BY ngay
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS tb_3_hang
    FROM theo_ngay
)
SELECT
    ngay,
    tong_ngay,
    CASE WHEN so_ngay = 3 THEN ROUND(tb_3_hang, 2)
         ELSE NULL END AS trung_binh_du_3_ngay
FROM co_frame
ORDER BY ngay;
~~~

Với hai ngày đầu, kết quả trung bình là NULL để biểu thị **chưa đủ ba quan sát**. Từ 03/10, kết quả theo bảng phần 9.1.

## 10. Ba hàng gần nhất chưa chắc là ba ngày lịch gần nhất

Giả sử bảng chỉ có các ngày 01/10, 02/10 và 04/10. Khi xét 04/10:

- `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` bao gồm **01, 02 và 04/10**.
- Khoảng **từ hai ngày trước đến 04/10** về lịch là **02, 03, 04/10**, không gồm 01/10.

Nếu ngày 03/10 không có dòng, hai khung này khác nhau.

### 10.1. PostgreSQL RANGE theo khoảng thời gian

Với một hàng mỗi ngày và cột thời gian phù hợp:

~~~sql
AVG(tong_ngay) OVER (
    ORDER BY ngay::TIMESTAMP
    RANGE BETWEEN INTERVAL '2 days' PRECEDING
              AND CURRENT ROW
)
~~~

Ở PostgreSQL, mẫu này xét những hàng có thời điểm nằm trong khoảng **hai ngày trước đến ngày hiện tại** theo giá trị thời gian, thay vì lấy hai dòng liền trước bất kể khoảng cách lịch.

Ví dụ chỉ có ngày 01, 02, 04/10: ngày 04 chỉ tính các hàng **02 và 04/10** theo khung hai ngày trước; ngày 03 không tự sinh ra nếu nguồn thiếu nó.

**RANGE theo thời gian không tự điền ngày không có dữ liệu.** Nó chỉ chọn các hàng **đang tồn tại** trong khoảng.

### 10.2. RANGE và ROWS xử lý các ngày trùng khác nhau

Nếu dữ liệu đầu vào vẫn là giao dịch thô, một ngày có thể có nhiều hàng:

- `ROWS 2 PRECEDING` lấy tối đa **ba giao dịch**.
- `RANGE INTERVAL '2 days' PRECEDING` có thể lấy **mọi giao dịch thuộc ba ngày lịch** trong khoảng, với số hàng khác nhau theo lượng giao dịch mỗi ngày.

Muốn **trung bình tổng tiền mỗi ngày**, nên **tổng hợp theo ngày trước**, rồi dùng một trong hai cách với phạm vi thời gian được định nghĩa rõ.

### 10.3. Để ROWS chính xác là ba ngày liên tiếp, hãy tạo lịch đầy đủ

Nếu báo cáo định nghĩa “không có giao dịch” là **doanh thu ngày bằng 0**, hãy tạo một hàng cho mọi ngày của kỳ rồi mới lấy ROWS. Khi mỗi ngày lịch có đúng một hàng, `ROWS 2 PRECEDING` tương ứng với **tối đa ba ngày liên tiếp**.

Nếu dữ liệu không xuất hiện vì **hệ thống chưa gửi số liệu**, không được tự quy nó bằng 0 nếu chưa xác minh. Trường hợp ấy cần giữ trạng thái dữ liệu thiếu hoặc dùng quy tắc riêng.

## 11. Sinh lịch đầy đủ và phân biệt ngày rỗng, ngày toàn NULL, ngày bằng 0

PostgreSQL có `generate_series` để tạo một dãy ngày. Ta xét từ **01/10 đến hết 12/10/2026**, có 12 ngày.

### 11.1. Tạo danh sách ngày

~~~sql
WITH lich AS (
    SELECT g.ngay_ts::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01 00:00:00',
        TIMESTAMP '2026-10-12 00:00:00',
        INTERVAL '1 day'
    ) AS g(ngay_ts)
)
SELECT ngay
FROM lich
ORDER BY ngay;
~~~

Kết quả có **12 ngày**, trong đó 11 và 12/10 chưa có giao dịch ở bảng nguồn.

### 11.2. LEFT JOIN lịch với giao dịch

~~~sql
WITH lich AS (
    SELECT g.ngay_ts::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01 00:00:00',
        TIMESTAMP '2026-10-12 00:00:00',
        INTERVAL '1 day'
    ) AS g(ngay_ts)
),
theo_ngay AS (
    SELECT
        lich.ngay,
        COUNT(gd.id) AS so_giao_dich,
        COUNT(gd.so_tien) AS so_co_tien,
        SUM(gd.so_tien) AS tong_raw,
        COALESCE(SUM(gd.so_tien), 0) AS tong_hien_thi
    FROM lich
    LEFT JOIN pt_giao_dich AS gd
        ON gd.ngay = lich.ngay
    GROUP BY lich.ngay
)
SELECT *
FROM theo_ngay
ORDER BY ngay;
~~~

Những dòng cuối:

| Ngày | so_giao_dich | so_co_tien | tong_raw | tong_hien_thi |
|---|---:|---:|---|---:|
| 10/10 | 3 | 2 | 100 | 100 |
| 11/10 | 0 | 0 | NULL | 0 |
| 12/10 | 0 | 0 | NULL | 0 |

**`COUNT(gd.id)` chứ không phải `COUNT(*)`** đếm giao dịch thật, vì LEFT JOIN vẫn giữ một hàng lịch dù không có giao dịch.

### 11.3. Tạo một lưới ngày × nhóm

Khi muốn tổng lũy kế riêng từng nhóm với những ngày không phát sinh, dùng:

~~~sql
WITH lich AS (
    SELECT g.ngay_ts::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01 00:00:00',
        TIMESTAMP '2026-10-12 00:00:00',
        INTERVAL '1 day'
    ) AS g(ngay_ts)
),
luoi AS (
    SELECT
        lich.ngay,
        n.ma_nhom,
        n.ten_nhom,
        n.thu_tu
    FROM lich
    CROSS JOIN pt_nhom AS n
),
theo_ngay_nhom AS (
    SELECT
        luoi.ngay,
        luoi.ma_nhom,
        luoi.ten_nhom,
        luoi.thu_tu,
        COUNT(gd.id) AS so_giao_dich,
        COUNT(gd.so_tien) AS so_co_tien,
        SUM(gd.so_tien) AS tong_raw,
        COALESCE(SUM(gd.so_tien), 0) AS tong_hien_thi
    FROM luoi
    LEFT JOIN pt_giao_dich AS gd
        ON gd.ngay = luoi.ngay
       AND gd.ma_nhom = luoi.ma_nhom
    GROUP BY
        luoi.ngay,
        luoi.ma_nhom,
        luoi.ten_nhom,
        luoi.thu_tu
)
SELECT *
FROM theo_ngay_nhom
ORDER BY thu_tu, ngay;
~~~

Có **12 ngày × 4 nhóm = 48 dòng**, ngay cả khi nhóm Dịch vụ không có giao dịch.

### 11.4. Ba tình trạng dữ liệu không được đánh đồng

Ví dụ từ lưới:

| Ngày | Nhóm | Số giao dịch | Có tiền | tong_raw | tong_hien_thi |
|---|---|---:|---:|---|---:|
| 05/10 | SACH | 1 | 0 | NULL | 0 |
| 07/10 | SACH | 1 | 1 | 0 | 0 |
| 06/10 | SACH | 0 | 0 | NULL | 0 |
| 11/10 | SACH | 0 | 0 | NULL | 0 |
| 01/10 | DICH_VU | 0 | 0 | NULL | 0 |

Ba trường hợp:

- **Không có giao dịch**: `so_giao_dich = 0`.
- **Có giao dịch nhưng toàn số tiền NULL**: `so_giao_dich > 0` và `so_co_tien = 0`.
- **Có số tiền xác định là 0**: `so_co_tien > 0` và `tong_raw = 0` (trong bộ dữ liệu không âm).

Cột `tong_hien_thi` đều có thể bằng 0, nhưng ý nghĩa nghiệp vụ không giống nhau.

### 11.5. Gắn trạng thái dữ liệu bằng CASE

~~~sql
CASE
    WHEN so_giao_dich = 0 THEN 'KHONG_CO_GIAO_DICH'
    WHEN so_co_tien = 0 THEN 'THIEU_SO_TIEN'
    ELSE 'CO_GIA_TRI'
END AS tinh_trang_du_lieu
~~~

Đây là đoạn biểu thức đặt trong SELECT **bên ngoài CTE `theo_ngay_nhom`**, nơi đã có các cột đếm. Việc giữ trạng thái này giúp dashboard không trình bày một ngày toàn dữ liệu thiếu như một ngày doanh thu bằng 0 mà không kèm cảnh báo.

## 12. Trung bình trượt ba ngày trên lịch đầy đủ

Nếu chính sách báo cáo là **ngày không phát sinh giao dịch được xem là 0**, ta dùng lưới ngày để có một hàng cho mỗi ngày:

~~~sql
WITH lich AS (
    SELECT g.ngay_ts::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01 00:00:00',
        TIMESTAMP '2026-10-12 00:00:00',
        INTERVAL '1 day'
    ) AS g(ngay_ts)
),
theo_ngay AS (
    SELECT
        lich.ngay,
        COUNT(gd.id) AS so_giao_dich,
        COALESCE(SUM(gd.so_tien), 0) AS tong_ngay
    FROM lich
    LEFT JOIN pt_giao_dich AS gd
        ON gd.ngay = lich.ngay
    GROUP BY lich.ngay
)
SELECT
    ngay,
    so_giao_dich,
    tong_ngay,
    SUM(tong_ngay) OVER (
        ORDER BY ngay
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke,
    ROUND(
        AVG(tong_ngay) OVER (
            ORDER BY ngay
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS tb_truot_3_ngay
FROM theo_ngay
ORDER BY ngay;
~~~

Kết quả:

| Ngày | Tổng ngày | Lũy kế | TB trượt 3 ngày |
|---|---:|---:|---:|
| 01/10 | 180 | 180 | 180.00 |
| 02/10 | 290 | 470 | 235.00 |
| 03/10 | 180 | 650 | 216.67 |
| 04/10 | 250 | 900 | 240.00 |
| 05/10 | 100 | 1000 | 176.67 |
| 06/10 | 300 | 1300 | 216.67 |
| 07/10 | 0 | 1300 | 133.33 |
| 08/10 | 400 | 1700 | 233.33 |
| 09/10 | 200 | 1900 | 200.00 |
| 10/10 | 100 | 2000 | 233.33 |
| 11/10 | 0 | 2000 | 100.00 |
| 12/10 | 0 | 2000 | 33.33 |

Ngày 11/10 tính trung bình ba ngày 09, 10, 11:

\[
(200+100+0)/3=100
\]

Ngày 12/10 tính từ ngày 10, 11, 12:

\[
(100+0+0)/3\approx33.33
\]

### 12.1. Trung bình không phát sinh khác trung bình thiếu dữ liệu

Nếu 11/10 và 12/10 thực sự không có giao dịch, điền 0 có thể hợp lý. Nhưng nếu hệ thống chỉ mới nạp dữ liệu đến 10/10, thì 11/10–12/10 chưa được xác nhận và **không nên gọi chắc chắn là doanh thu bằng 0**.

Một mô hình báo cáo nghiêm ngặt thường tách:

- **Ngày đã chốt báo cáo nhưng không giao dịch**: số tiền 0.
- **Ngày chưa có dữ liệu hoặc chưa chốt**: số tiền NULL, hoặc một trạng thái riêng.

Tùy mục tiêu, trung bình trượt có thể **bỏ qua NULL** (AVG chỉ chia theo ngày có giá trị) hoặc **trả NULL nếu khung chưa đủ ngày hợp lệ**. Không có một lựa chọn phổ quát cho mọi nghiệp vụ.

## 13. Trung bình trượt theo giao dịch và theo ngày khác nhau

Để minh họa, xét riêng nhóm Sách.

### 13.1. Ba giao dịch Sách gần nhất

~~~sql
SELECT
    id,
    ngay,
    so_tien,
    ROUND(
        AVG(so_tien) OVER (
            PARTITION BY ma_nhom
            ORDER BY ngay, id
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS tb_3_giao_dich
FROM pt_giao_dich
WHERE ma_nhom = 'SACH'
ORDER BY ngay, id;
~~~

Kết quả:

| id | Ngày | Số tiền | TB tối đa 3 giao dịch |
|---:|---|---:|---:|
| 101 | 01/10 | 100 | 100.00 |
| 102 | 02/10 | 200 | 150.00 |
| 103 | 02/10 | 50 | 116.67 |
| 104 | 04/10 | 150 | 133.33 |
| 105 | 05/10 | NULL | 100.00 |
| 106 | 07/10 | 0 | 75.00 |
| 107 | 08/10 | 300 | 150.00 |
| 108 | 10/10 | 100 | 133.33 |

Ở giao dịch 105, frame gồm 103 (50), 104 (150) và 105 (NULL). `AVG` bỏ qua NULL, nên trung bình là `(50+150)/2 = 100`.

Ở 106, frame gồm 104 (150), 105 (NULL), 106 (0). Trung bình là `(150+0)/2 = 75`.

### 13.2. Ba ngày gần nhất theo số tiền nhóm

Muốn **trung bình tổng tiền Sách trên ba ngày lịch**, phải có một hàng Sách cho từng ngày. Ví dụ lưới ở phần 11 tạo được:

~~~text
01/10 Sách: 100
02/10 Sách: 250
03/10 Sách:   0 (không có giao dịch)
04/10 Sách: 150
05/10 Sách:   0 (có giao dịch nhưng tiền NULL, đã đổi để hiển thị)
06/10 Sách:   0 (không có giao dịch)
07/10 Sách:   0 (giao dịch tiền thực bằng 0)
08/10 Sách: 300
09/10 Sách:   0 (không có giao dịch)
10/10 Sách: 100
~~~

Nếu chấp nhận chính sách điền 0, tại **04/10** trung bình ba ngày 02, 03, 04 là:

\[
(250+0+150)/3\approx133.33
\]

Con số trùng ngẫu nhiên với trung bình ba giao dịch ở ID 104 trong ví dụ này, nhưng **các hàng tham gia khác nhau**. Tại 08/10, trung bình ba ngày 06, 07, 08 là:

\[
(0+0+300)/3=100
\]

trong khi trung bình ba giao dịch tại ID 107 là **150**. Đây là khác biệt bản chất giữa **đơn vị giao dịch** và **đơn vị ngày**.

## 14. Trung bình theo giao dịch, theo ngày có giao dịch và theo mọi ngày

Ba KPI dễ bị gọi cùng tên “trung bình doanh thu” nhưng mẫu số khác nhau.

### 14.1. Trung bình một giao dịch có số tiền

~~~sql
SELECT
    COUNT(*) AS so_giao_dich,
    COUNT(so_tien) AS so_giao_dich_co_tien,
    SUM(so_tien) AS tong,
    ROUND(AVG(so_tien), 2) AS tb_theo_giao_dich_co_tien
FROM pt_giao_dich;
~~~

Kết quả:

| so_giao_dich | so_giao_dich_co_tien | tong | tb_theo_giao_dich_co_tien |
|---:|---:|---:|---:|
| 21 | 18 | 2000 | 111.11 |

\[
2000/18\approx111.11
\]

### 14.2. Trung bình một ngày có ít nhất một giao dịch

~~~sql
WITH theo_ngay AS (
    SELECT
        ngay,
        COALESCE(SUM(so_tien), 0) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
)
SELECT
    COUNT(*) AS so_ngay_co_giao_dich,
    SUM(tong_ngay) AS tong,
    ROUND(AVG(tong_ngay), 2) AS tb_ngay_co_giao_dich
FROM theo_ngay;
~~~

Kết quả: **10 ngày**, tổng 2000, trung bình **200.00**.

\[
2000/10=200
\]

### 14.3. Trung bình một ngày trong kỳ 12 ngày có ngày rỗng bằng 0

Nếu kỳ báo cáo gồm 01–12/10 và ngày rỗng được xem là 0:

\[
2000/12\approx166.67
\]

Truy vấn:

~~~sql
WITH lich AS (
    SELECT g.ngay_ts::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01',
        TIMESTAMP '2026-10-12',
        INTERVAL '1 day'
    ) AS g(ngay_ts)
),
theo_ngay AS (
    SELECT
        lich.ngay,
        COALESCE(SUM(gd.so_tien), 0) AS tong_ngay
    FROM lich
    LEFT JOIN pt_giao_dich AS gd
        ON gd.ngay = lich.ngay
    GROUP BY lich.ngay
)
SELECT
    COUNT(*) AS so_ngay_trong_ky,
    ROUND(AVG(tong_ngay), 2) AS tb_moi_ngay_trong_ky
FROM theo_ngay;
~~~

Kết quả: **12 ngày**, trung bình **166.67**.

| KPI | Mẫu số | Kết quả |
|---|---:|---:|
| Trung bình mỗi giao dịch có tiền | 18 | 111.11 |
| Trung bình mỗi ngày có giao dịch | 10 | 200.00 |
| Trung bình mỗi ngày trong lịch 12 ngày, ngày rỗng = 0 | 12 | 166.67 |

**Không có phép AVG nào bị sai:** các câu SQL trả lời **ba câu hỏi khác nhau**.

## 15. Mẫu 2: tỷ lệ đóng góp theo nhóm trong tổng toàn kỳ

Yêu cầu: nhóm Sách, VPP, Phụ kiện, Dịch vụ chiếm bao nhiêu phần trăm tổng tiền?

### 15.1. Tổng hợp từng nhóm trước

~~~sql
WITH theo_nhom AS (
    SELECT
        n.ma_nhom,
        n.ten_nhom,
        n.thu_tu,
        COUNT(g.id) AS so_giao_dich,
        COUNT(g.so_tien) AS so_co_tien,
        COALESCE(SUM(g.so_tien), 0) AS tong_nhom
    FROM pt_nhom AS n
    LEFT JOIN pt_giao_dich AS g
        ON g.ma_nhom = n.ma_nhom
    GROUP BY n.ma_nhom, n.ten_nhom, n.thu_tu
)
SELECT
    ma_nhom,
    ten_nhom,
    so_giao_dich,
    tong_nhom,
    ROUND(
        100.0 * tong_nhom
        / NULLIF(SUM(tong_nhom) OVER (), 0),
        2
    ) AS ty_le_phan_tram
FROM theo_nhom
ORDER BY tong_nhom DESC, thu_tu;
~~~

Kết quả:

| Nhóm | Số giao dịch | Tổng nhóm | Tỷ lệ đóng góp |
|---|---:|---:|---:|
| Sách | 8 | 900 | 45.00% |
| Văn phòng phẩm | 7 | 600 | 30.00% |
| Phụ kiện | 6 | 500 | 25.00% |
| Dịch vụ | 0 | 0 | 0.00% |

### 15.2. Giải thích mẫu số

Trong CTE `theo_nhom`, mỗi nhóm chỉ có một hàng; tổng `tong_nhom` là 900, 600, 500, 0.

Khi đó:

~~~sql
SUM(tong_nhom) OVER ()
~~~

trả **2000 trên mỗi hàng nhóm**. Nó không làm gộp bốn nhóm thành một hàng vì có `OVER ()`.

Tỷ lệ đóng góp mỗi nhóm:

\[
\text{Tỷ lệ nhóm}=
\frac{\text{Tổng nhóm}}{\text{Tổng tất cả nhóm}}\times100
\]

Với VPP:

\[
600/2000\times100=30\%
\]

### 15.3. Vì sao nên dùng NULLIF ở mẫu số?

Nếu toàn kỳ có tổng tiền bằng 0, biểu thức:

~~~sql
100.0 * tong_nhom / SUM(tong_nhom) OVER ()
~~~

có thể gây lỗi chia cho 0. Dùng:

~~~sql
100.0 * tong_nhom
/ NULLIF(SUM(tong_nhom) OVER (), 0)
~~~

giúp mẫu số 0 trở thành NULL, phép chia trả NULL thay vì kết quả vô nghĩa. Đối với báo cáo, **tỷ lệ trên tổng bằng 0 thường không xác định được**; không nên tự hiển thị 0% cho mọi nhóm trừ khi đó là chính sách nghiệp vụ được xác nhận.

### 15.4. Vì sao dùng 100.0 thay vì 100?

`100.0` thể hiện rõ ý định tính tỷ lệ có phần thập phân. Một số DBMS có quy tắc phép chia số nguyên làm mất phần thập phân; nếu dùng các cột nguyên, hãy ép kiểu `NUMERIC`/`DECIMAL` phù hợp để giữ độ chính xác.

Với dữ liệu tiền kiểu `NUMERIC(12,2)` trên PostgreSQL, biểu thức này phù hợp để dùng cùng `ROUND(..., 2)`. Các DBMS khác có thể cần `CAST` theo kiểu số tương ứng.

## 16. Tỷ lệ đóng góp của từng giao dịch trong nhóm

Nếu muốn mỗi giao dịch có **tỷ lệ so với tổng nhóm của chính nó**, không cần `GROUP BY` trước:

~~~sql
SELECT
    id,
    ngay,
    ma_nhom,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY ma_nhom
    ) AS tong_nhom,
    ROUND(
        100.0 * so_tien
        / NULLIF(
            SUM(so_tien) OVER (PARTITION BY ma_nhom),
            0
        ),
        2
    ) AS ty_le_trong_nhom
FROM pt_giao_dich
ORDER BY ma_nhom, ngay, id;
~~~

Ví dụ Sách:

| id | so_tien | Tổng Sách | Tỷ lệ trong Sách |
|---:|---:|---:|---:|
| 101 | 100 | 900 | 11.11% |
| 102 | 200 | 900 | 22.22% |
| 103 | 50 | 900 | 5.56% |
| 104 | 150 | 900 | 16.67% |
| 105 | NULL | 900 | NULL |
| 106 | 0 | 900 | 0.00% |
| 107 | 300 | 900 | 33.33% |
| 108 | 100 | 900 | 11.11% |

### 16.1. Tại sao NULL không ra 0%?

Giao dịch 105 có `so_tien NULL`, nên tử số chưa có giá trị. Phép chia với NULL trả NULL. Đây là khác biệt có ích: **không biết tỷ lệ** không giống **tỷ lệ đúng bằng 0**.

Giao dịch 106 có số tiền xác định là 0 và tổng Sách 900, nên tỷ lệ của nó là **0%**.

### 16.2. Tổng các tỷ lệ sau làm tròn có thể không đúng 100.00

Các tỷ lệ thực trước làm tròn của các giao dịch có tiền trong một nhóm không âm có thể cộng thành 100%. Nhưng sau khi làm tròn từng hàng tới hai chữ số thập phân, tổng hiển thị có thể lệch đôi chút khỏi 100.00%.

Đây là sai số làm tròn, không tự chứng minh tổng dữ liệu bị sai. Nếu báo cáo cần phân bổ chính xác tới đơn vị nhỏ nhất, phải có quy tắc phân bổ phần dư thay vì làm tròn độc lập từng hàng.

### 16.3. Tỷ lệ theo nhóm khác tỷ lệ theo toàn kỳ

Giao dịch Sách 101 có giá trị 100:

- Trong Sách: `100/900 × 100 ≈ 11.11%`.
- Trong toàn kỳ: `100/2000 × 100 = 5%`.

Hai tỷ lệ đều đúng với **hai mẫu số khác nhau**. Nên đặt tên cột `ty_le_trong_nhom` hoặc `ty_le_toan_ky` thay vì một tên chung như `percentage`.

## 17. Tỷ lệ đóng góp theo ngày và theo nhóm trong ngày

Yêu cầu: trong **mỗi ngày**, Sách, VPP, Phụ kiện và Dịch vụ chiếm bao nhiêu phần trăm tổng ngày?

Đầu ra phải có **một hàng/nhóm/ngày**, không phải một hàng/giao dịch. Ta dùng lịch đầy đủ và danh mục nhóm để giữ cả những cặp không phát sinh:

~~~sql
WITH lich AS (
    SELECT g.ngay_ts::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01',
        TIMESTAMP '2026-10-12',
        INTERVAL '1 day'
    ) AS g(ngay_ts)
),
theo_ngay_nhom AS (
    SELECT
        lich.ngay,
        n.ma_nhom,
        n.ten_nhom,
        n.thu_tu,
        COUNT(gd.id) AS so_giao_dich,
        COUNT(gd.so_tien) AS so_co_tien,
        COALESCE(SUM(gd.so_tien), 0) AS tong_nhom_ngay
    FROM lich
    CROSS JOIN pt_nhom AS n
    LEFT JOIN pt_giao_dich AS gd
        ON gd.ngay = lich.ngay
       AND gd.ma_nhom = n.ma_nhom
    GROUP BY
        lich.ngay,
        n.ma_nhom,
        n.ten_nhom,
        n.thu_tu
),
co_tong_ngay AS (
    SELECT
        ngay,
        ma_nhom,
        ten_nhom,
        thu_tu,
        so_giao_dich,
        so_co_tien,
        tong_nhom_ngay,
        SUM(tong_nhom_ngay) OVER (
            PARTITION BY ngay
        ) AS tong_ngay
    FROM theo_ngay_nhom
)
SELECT
    ngay,
    ma_nhom,
    tong_nhom_ngay,
    tong_ngay,
    ROUND(
        100.0 * tong_nhom_ngay
        / NULLIF(tong_ngay, 0),
        2
    ) AS ty_le_trong_ngay,
    so_giao_dich,
    so_co_tien
FROM co_tong_ngay
ORDER BY ngay, thu_tu;
~~~

Cửa sổ:

~~~sql
SUM(tong_nhom_ngay) OVER (PARTITION BY ngay)
~~~

cộng **bốn nhóm trong cùng ngày**, tạo mẫu số tổng ngày. Vì có 12 ngày và 4 nhóm, kết quả có **48 hàng**.

### 17.1. Kết quả ngày 02/10

| Nhóm | Tổng nhóm ngày 02/10 | Tổng ngày | Tỷ lệ |
|---|---:|---:|---:|
| Sách | 250 | 290 | 86.21% |
| Văn phòng phẩm | 0 | 290 | 0.00% |
| Phụ kiện | 40 | 290 | 13.79% |
| Dịch vụ | 0 | 290 | 0.00% |

Tỷ lệ Sách:

\[
250/290\times100\approx86.21\%
\]

Ngày 02/10 không có giao dịch VPP hoặc Dịch vụ; chính sách hiển thị đưa tổng của các tổ hợp đó thành 0.

### 17.2. Ngày có tổng bằng 0

Ngày 07/10 có giao dịch Sách bằng 0 và không có tiền dương ở nhóm khác. Vì vậy **tổng ngày bằng 0**.

Với `NULLIF(tong_ngay, 0)`, tỷ lệ nhóm trong ngày trả **NULL** cho mọi nhóm. Không nên khẳng định Sách chiếm 100% chỉ vì đó là nhóm duy nhất có một giao dịch: câu hỏi này đang phân bổ **số tiền**, không phân bổ **số lượng giao dịch**.

Nếu muốn tỷ lệ **số giao dịch** theo nhóm, phải đổi tử số và mẫu số sang COUNT:

~~~sql
100.0 * so_giao_dich
/ NULLIF(
    SUM(so_giao_dich) OVER (PARTITION BY ngay),
    0
)
~~~

Khi đó ngày 07/10, Sách chiếm **100% số lượng giao dịch**, nhưng **không có tỷ lệ tiền hợp lệ** vì tổng tiền bằng 0.

### 17.3. Dữ liệu thiếu cần được giữ dấu

Ngày 05/10, nhóm Sách có một giao dịch tiền NULL; phép tổng hiển thị của nhóm Sách được đưa về 0. Tỷ lệ ngày có thể hiển thị 0% cho nhóm này, nhưng điều đó **không chứng minh giao dịch Sách thực sự bằng 0**.

Vì thế truy vấn giữ thêm `so_giao_dich` và `so_co_tien`. Báo cáo đáng tin cậy có thể gắn cảnh báo khi `so_giao_dich > so_co_tien`, thay vì chỉ trình bày tỷ lệ đã COALESCE.

## 18. Tỷ lệ lũy kế so với tổng kỳ

Một KPI rất hay dùng cho tiến độ chiến dịch: **đến ngày hiện tại đã đạt bao nhiêu phần trăm tổng giá trị của cả kỳ?**

~~~sql
WITH theo_ngay AS (
    SELECT
        ngay,
        COALESCE(SUM(so_tien), 0) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
),
chi_so AS (
    SELECT
        ngay,
        tong_ngay,
        SUM(tong_ngay) OVER (
            ORDER BY ngay
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS tong_luy_ke,
        SUM(tong_ngay) OVER () AS tong_ca_ky
    FROM theo_ngay
)
SELECT
    ngay,
    tong_ngay,
    tong_luy_ke,
    tong_ca_ky,
    ROUND(
        100.0 * tong_luy_ke
        / NULLIF(tong_ca_ky, 0),
        2
    ) AS phan_tram_luy_ke
FROM chi_so
ORDER BY ngay;
~~~

Kết quả:

| Ngày | Tổng ngày | Lũy kế | % lũy kế của 2.000 |
|---|---:|---:|---:|
| 01/10 | 180 | 180 | 9.00% |
| 02/10 | 290 | 470 | 23.50% |
| 03/10 | 180 | 650 | 32.50% |
| 04/10 | 250 | 900 | 45.00% |
| 05/10 | 100 | 1000 | 50.00% |
| 06/10 | 300 | 1300 | 65.00% |
| 07/10 | 0 | 1300 | 65.00% |
| 08/10 | 400 | 1700 | 85.00% |
| 09/10 | 200 | 1900 | 95.00% |
| 10/10 | 100 | 2000 | 100.00% |

### 18.1. Phân biệt hai chỉ số “phần trăm”

Ngày 08/10:

- **Tỷ lệ đóng góp riêng ngày 08/10** = `400/2000 = 20%`.
- **Tỷ lệ lũy kế đến hết ngày 08/10** = `1700/2000 = 85%`.

Nếu cột chỉ có tên `phan_tram`, người đọc rất dễ nhầm. Nên đặt tên `ty_le_ngay_trong_ky` và `ty_le_luy_ke_trong_ky`.

### 18.2. Tổng kỳ là tổng của tập nào?

Truy vấn tính `tong_ca_ky` từ **chính CTE `theo_ngay`**. Nếu CTE này có điều kiện lọc, chẳng hạn chỉ tháng 10 hoặc chỉ nhóm Sách, mẫu số sẽ thay đổi theo tập đã lọc.

Nếu cần tính phần trăm so với **mục tiêu kế hoạch** thay vì tổng thực tế, mẫu số phải lấy từ nguồn mục tiêu, không nên dùng `SUM(tong_ngay) OVER ()` rồi gọi là “phần trăm hoàn thành mục tiêu”.

### 18.3. Nếu dữ liệu có số âm?

Bộ dữ liệu mẫu chỉ cho số tiền không âm. Trong hệ thống có hoàn trả hoặc điều chỉnh âm, tổng lũy kế có thể **giảm**, tỷ lệ lũy kế có thể không đơn điệu và tỷ lệ đóng góp có thể âm hoặc vượt 100% nếu tổng thuần nhỏ. Khi đó cần xác định chỉ số là **doanh thu gộp**, **doanh thu thuần** hay **dòng tiền**; không tự coi tất cả tỷ lệ là phần chia tích cực cộng đẹp thành 100%.

## 19. Tỷ lệ đóng góp lũy kế theo nhóm: mẫu Pareto

Một báo cáo có thể muốn biết **nhóm lớn nhất đã đóng góp bao nhiêu**, rồi sau hai nhóm lớn nhất đóng góp bao nhiêu. Đây là mẫu **cumulative share**, thường dùng trong phân tích Pareto.

### 19.1. Tính tổng nhóm, xếp giảm dần và cộng tỷ lệ

~~~sql
WITH theo_nhom AS (
    SELECT
        n.ma_nhom,
        n.ten_nhom,
        n.thu_tu,
        COALESCE(SUM(g.so_tien), 0) AS tong
    FROM pt_nhom AS n
    LEFT JOIN pt_giao_dich AS g
        ON g.ma_nhom = n.ma_nhom
    GROUP BY n.ma_nhom, n.ten_nhom, n.thu_tu
),
xep_nhom AS (
    SELECT
        ma_nhom,
        ten_nhom,
        thu_tu,
        tong,
        SUM(tong) OVER () AS tong_ca_ky,
        SUM(tong) OVER (
            ORDER BY tong DESC, thu_tu
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS tong_luy_ke_nhom
    FROM theo_nhom
)
SELECT
    ma_nhom,
    tong,
    ROUND(
        100.0 * tong / NULLIF(tong_ca_ky, 0),
        2
    ) AS ty_le_rieng,
    ROUND(
        100.0 * tong_luy_ke_nhom
        / NULLIF(tong_ca_ky, 0),
        2
    ) AS ty_le_luy_ke
FROM xep_nhom
ORDER BY tong DESC, thu_tu;
~~~

Kết quả:

| Nhóm | Tổng | Tỷ lệ riêng | Tỷ lệ lũy kế |
|---|---:|---:|---:|
| Sách | 900 | 45.00% | 45.00% |
| Văn phòng phẩm | 600 | 30.00% | 75.00% |
| Phụ kiện | 500 | 25.00% | 100.00% |
| Dịch vụ | 0 | 0.00% | 100.00% |

### 19.2. ORDER BY quan trọng hơn PARTITION BY trong trường hợp này

Câu hỏi là lũy kế **các nhóm trên toàn báo cáo**, nên ta **không đặt PARTITION BY ma_nhom**: nếu làm vậy, mỗi nhóm chỉ có một dòng và tổng lũy kế nhóm sẽ bằng chính tổng của nó.

Ta dùng:

~~~sql
ORDER BY tong DESC, thu_tu
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

để cộng nhóm lớn nhất trước, rồi nhóm tiếp theo. `thu_tu` phá hòa khi hai nhóm có cùng tổng, giúp thứ tự xác định. Nếu chính sách muốn các nhóm đồng tổng cùng hạng/đồng mốc, cần định nghĩa quy tắc riêng thay vì tùy ý phá hòa.

### 19.3. Tìm nhóm cho đến khi vượt một ngưỡng đóng góp

Giả sử bạn muốn giữ **ít nhóm nhất từ nhóm lớn nhất trở xuống để đạt ít nhất 70% tổng kỳ**. Sách đạt 45%, thêm VPP đạt 75%, nên tập cần giữ là **Sách và VPP**.

Có thể dùng tổng lũy kế **trước dòng hiện tại** để xác định dòng nào vẫn cần được thêm:

~~~sql
WITH theo_nhom AS (
    SELECT
        n.ma_nhom,
        n.ten_nhom,
        n.thu_tu,
        COALESCE(SUM(g.so_tien), 0) AS tong
    FROM pt_nhom AS n
    LEFT JOIN pt_giao_dich AS g
        ON g.ma_nhom = n.ma_nhom
    GROUP BY n.ma_nhom, n.ten_nhom, n.thu_tu
),
xep AS (
    SELECT
        ma_nhom,
        ten_nhom,
        tong,
        thu_tu,
        SUM(tong) OVER () AS tong_ky,
        COALESCE(
            SUM(tong) OVER (
                ORDER BY tong DESC, thu_tu
                ROWS BETWEEN UNBOUNDED PRECEDING
                         AND 1 PRECEDING
            ),
            0
        ) AS tong_truoc_nhom
    FROM theo_nhom
)
SELECT
    ma_nhom,
    ten_nhom,
    tong
FROM xep
WHERE tong_ky > 0
  AND 100.0 * tong_truoc_nhom / tong_ky < 70
ORDER BY tong DESC, thu_tu;
~~~

Kết quả là **Sách và Văn phòng phẩm**. Điều kiện chọn dòng khi **tổng trước khi thêm dòng vẫn chưa đạt 70%**, nên giữ luôn dòng làm vượt mốc. Với 80%, tập này sẽ cần thêm Phụ kiện vì hai nhóm đầu mới đạt 75%.

Đây là một chính sách phân tích cụ thể. Trong thực tế, khi nhiều nhóm đồng tổng, việc chọn bao nhiêu nhóm ở ranh giới cần quy tắc rõ để tránh kết quả tùy tiện.

## 20. Một báo cáo kết hợp cả ba chỉ số

Một dashboard thường cần đồng thời tổng ngày, tổng lũy kế, trung bình ba ngày và tỷ lệ đóng góp.

Đoạn SQL dưới dùng **lịch đầy đủ 12 ngày**, quy ước **ngày không giao dịch = 0**, rồi tính các chỉ số trong một báo cáo:

~~~sql
WITH lich AS (
    SELECT g.ngay_ts::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01',
        TIMESTAMP '2026-10-12',
        INTERVAL '1 day'
    ) AS g(ngay_ts)
),
tong_theo_ngay AS (
    SELECT
        lich.ngay,
        COUNT(gd.id) AS so_giao_dich,
        COUNT(gd.so_tien) AS so_co_tien,
        COALESCE(SUM(gd.so_tien), 0) AS tong_ngay
    FROM lich
    LEFT JOIN pt_giao_dich AS gd
        ON gd.ngay = lich.ngay
    GROUP BY lich.ngay
),
chi_so_cua_so AS (
    SELECT
        ngay,
        so_giao_dich,
        so_co_tien,
        tong_ngay,
        SUM(tong_ngay) OVER (
            ORDER BY ngay
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS tong_luy_ke,
        AVG(tong_ngay) OVER (
            ORDER BY ngay
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS tb_3_ngay,
        SUM(tong_ngay) OVER () AS tong_ky
    FROM tong_theo_ngay
)
SELECT
    ngay,
    so_giao_dich,
    so_co_tien,
    tong_ngay,
    tong_luy_ke,
    ROUND(tb_3_ngay, 2) AS tb_3_ngay,
    ROUND(
        100.0 * tong_ngay / NULLIF(tong_ky, 0),
        2
    ) AS ty_le_ngay_trong_ky,
    ROUND(
        100.0 * tong_luy_ke / NULLIF(tong_ky, 0),
        2
    ) AS ty_le_luy_ke_trong_ky
FROM chi_so_cua_so
ORDER BY ngay;
~~~

### 20.1. Vai trò của từng CTE

~~~text
generate_series
      │
      ▼
     lich ────────────────┐
                          ▼
pt_giao_dich ───────► tong_theo_ngay
                       (1 hàng/ngày)
                          │
                          ▼
                    chi_so_cua_so
          ┌───────────────┼─────────────────────┐
          │               │                     │
      SUM lũy kế      AVG 3 ngày             SUM toàn kỳ
          │               │                     │
          └───────────────┼─────────────────────┘
                          ▼
                       SELECT cuối
                (tỷ lệ và làm tròn)
~~~

Tách theo CTE khiến người đọc dễ thấy: **trước tiên phải chuẩn hóa cấp dữ liệu**, sau đó mới dùng window để tính các chỉ số.

### 20.2. Đầu ra giải thích được ba loại phần trăm khác nhau

- `ty_le_ngay_trong_ky`: tỷ lệ đóng góp của riêng ngày.
- `ty_le_luy_ke_trong_ky`: tỷ lệ đã tích lũy đến ngày đó.
- Một chỉ số **so với kế hoạch** sẽ cần mẫu số từ bảng mục tiêu, không có trong truy vấn mẫu này.

### 20.3. Cẩn trọng khi thay đổi khoảng ngày

Nếu `lich` chỉ tạo đến 08/10 nhưng `pt_giao_dich` có dữ liệu đến 10/10, tổng kỳ trong truy vấn sẽ là **1700**, không còn 2000. Do mẫu số đến từ **tập ngày đã chọn**, các tỷ lệ sẽ là tỷ lệ **trong kỳ 01–08/10**, không phải tỷ lệ toàn bộ 01–10/10.

Khi hiển thị nhãn thời gian trên báo cáo, phải ghi rõ kỳ tính và chính sách đối với ngày chưa có số liệu.

## 21. Phân vùng theo kỳ: lũy kế tháng tự bắt đầu lại

Trong báo cáo nhiều tháng, bạn có thể muốn tổng lũy kế **bắt đầu lại từ đầu mỗi tháng**. Khi đó, partition phải bao gồm khóa kỳ.

Giả sử một bảng dữ liệu sản xuất có cột ngày và tiền. Một mẫu PostgreSQL:

~~~sql
WITH theo_ngay AS (
    SELECT
        ngay,
        DATE_TRUNC('month', ngay)::DATE AS dau_thang,
        SUM(so_tien) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay, DATE_TRUNC('month', ngay)::DATE
)
SELECT
    dau_thang,
    ngay,
    tong_ngay,
    SUM(tong_ngay) OVER (
        PARTITION BY dau_thang
        ORDER BY ngay
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke_trong_thang
FROM theo_ngay
ORDER BY dau_thang, ngay;
~~~

Bộ dữ liệu mẫu chỉ chứa tháng 10/2026 nên ở đây chưa thấy hiệu ứng bắt đầu lại. Khi có dữ liệu tháng 11/2026, nó trở thành **partition khác**, tổng lũy kế sẽ bắt đầu từ tổng của ngày đầu tiên có dữ liệu trong tháng 11.

### 21.1. Đừng chỉ PARTITION BY số tháng

Không nên viết:

~~~sql
PARTITION BY EXTRACT(MONTH FROM ngay)
~~~

trong báo cáo nhiều năm nếu muốn tháng 10/2026 khác tháng 10/2027. Dùng **khóa năm–tháng**, chẳng hạn `DATE_TRUNC('month', ngay)`, hoặc `EXTRACT(YEAR FROM ngay), EXTRACT(MONTH FROM ngay)`.

### 21.2. Lũy kế theo nhóm và theo tháng

Có thể dùng:

~~~sql
PARTITION BY ma_nhom, DATE_TRUNC('month', ngay)
ORDER BY ngay, id
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

trong một biểu thức window trên dữ liệu giao dịch. Khi đó mỗi **nhóm–tháng** có dãy lũy kế riêng.

Nếu cần **một hàng mỗi nhóm/ngày**, phải tổng hợp lên cấp đó trước thay vì dùng trực tiếp từng giao dịch.

## 22. Named WINDOW để tránh lặp cấu trúc cửa sổ

Trong PostgreSQL, một SELECT có thể đặt tên cấu hình cửa sổ bằng mệnh đề `WINDOW`.

Ví dụ trên nguồn tổng theo ngày:

~~~sql
WITH theo_ngay AS (
    SELECT
        ngay,
        COALESCE(SUM(so_tien), 0) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
)
SELECT
    ngay,
    tong_ngay,
    SUM(tong_ngay) OVER w_luy_ke AS tong_luy_ke,
    AVG(tong_ngay) OVER w_3_ngay AS tb_3_ngay
FROM theo_ngay
WINDOW
    w_luy_ke AS (
        ORDER BY ngay
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_3_ngay AS (
        ORDER BY ngay
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )
ORDER BY ngay;
~~~

`w_luy_ke` và `w_3_ngay` là tên của **cấu hình cửa sổ**, không phải bảng dữ liệu.

- CTE `theo_ngay` định nghĩa **đầu vào một hàng mỗi ngày**.
- Named WINDOW định nghĩa **thứ tự và frame**.
- SELECT ngoài hiển thị các chỉ số.

Khi nhiều hàm dùng chung cùng `PARTITION BY/ORDER BY/frame`, named WINDOW có thể làm SQL ngắn và nhất quán hơn. Nhưng đừng gom những frame có ý nghĩa khác nhau vào một định nghĩa chỉ để giảm dòng code.

## 23. Những lỗi phổ biến khi áp dụng mẫu truy vấn

| Sai lầm | Tác động | Cách xử lý |
|---|---|---|
| Tính AVG trên giao dịch rồi gọi “trung bình ngày” | Mẫu số là số giao dịch có tiền, không phải ngày | `GROUP BY ngay` trước |
| Dùng ROWS 2 PRECEDING trên dữ liệu thiếu ngày | Chọn ba **hàng có dữ liệu**, không phải ba ngày liên tiếp | Tạo lịch hoặc dùng RANGE theo ngày |
| Lũy kế ORDER BY ngày khi nhiều giao dịch cùng ngày | Frame mặc định RANGE có thể cộng cùng lúc các peers | Dùng `ORDER BY ngay, id ROWS ...` nếu cần từng giao dịch |
| Không dùng ORDER BY bên ngoài | Thứ tự hiển thị không được bảo đảm | Thêm ORDER BY ở SELECT cuối |
| Lọc dữ liệu sau/before window sai chỗ | Thay đổi tổng tham chiếu hoặc làm mất dữ liệu cần tính | Dùng CTE để phân biệt tính trước, lọc sau |
| Không nói rõ mẫu số tỷ lệ | Tỷ lệ nhóm, ngày và kỳ bị nhầm | Đặt tên cột và mô tả phạm vi |
| Chia trực tiếp cho tổng có thể bằng 0 | Lỗi chia cho 0 hoặc chỉ số không xác định | `NULLIF(mau_so, 0)` |
| Dùng phép chia số nguyên ở DBMS có integer division | Mất phần thập phân | Ép kiểu NUMERIC/DECIMAL phù hợp |
| COALESCE mọi NULL thành 0 | Gộp thiếu dữ liệu với doanh thu thực bằng 0 | Giữ COUNT và trạng thái chất lượng dữ liệu |
| COUNT(*) sau LEFT JOIN danh mục | Nhóm rỗng vẫn có hàng đệm nên bị đếm thành 1 | Dùng `COUNT(gd.id)` |
| Tính % đóng góp nhóm ngay trên dữ liệu nhiều dòng | Mỗi giao dịch nhận tỷ lệ riêng thay vì một hàng/nhóm | Tổng hợp theo nhóm trước nếu yêu cầu một hàng/nhóm |
| Cộng % sau làm tròn phải bằng đúng 100.00 | Làm tròn độc lập có thể gây lệch | Phân biệt tỷ lệ chính xác và tỷ lệ hiển thị |
| Cộng tổng của bảng cha sau JOIN 1:N | Một giá trị bị nhân theo số dòng liên quan | Tổng hợp ở đúng cấp trước JOIN |
| Bỏ PARTITION BY khi cần reset theo nhóm/tháng | Tổng lũy kế chạy xuyên các nhóm | Định nghĩa partition đủ khóa |
| Thêm ID vào RANK khi muốn giữ đồng hạng | ID phá nhóm peers, làm hết đồng hạng | Chỉ dùng tiêu chí định nghĩa hạng |
| Dùng MAX(id) để xác định ngày mới nhất | ID không bảo đảm phản ánh thời gian | Dùng ngày/thời điểm và tie-breaker |
| Đánh đồng “ngày không có bản ghi” với “ngày chưa nạp dữ liệu” | KPI có thể bị giảm giả tạo | Dùng lịch trạng thái/chốt số liệu |
| Dùng `SUM(DISTINCT so_tien)` để sửa nhân hàng | Hai giao dịch khác nhau cùng số tiền bị loại nhầm | Sửa JOIN và mức dữ liệu |
| Dùng CTE để “bảo đảm chạy nhanh” | CTE không tự hứa materialize hay tăng tốc | Xem EXPLAIN và đo trên dữ liệu thật |

### 23.1. Tỷ lệ đúng nhưng mẫu số sai

Ví dụ:

~~~sql
SELECT
    ma_nhom,
    ROUND(
        100.0 * SUM(so_tien)
        / (SELECT SUM(so_tien) FROM pt_giao_dich),
        2
    ) AS ty_le
FROM pt_giao_dich
WHERE ngay <= DATE '2026-10-05'
GROUP BY ma_nhom;
~~~

Tử số chỉ đến **05/10**, nhưng mẫu số là tổng **toàn bộ 01–10/10**. Câu SQL có thể chạy đúng nhưng diễn đạt chỉ số “tỷ lệ từng nhóm của giai đoạn đầu so với **tổng toàn kỳ**”, không phải “tỷ lệ từng nhóm trong **01–05/10**”.

Nếu yêu cầu là tỷ lệ trong 01–05/10, mẫu số phải có **cùng phạm vi ngày** với tử số. Một CTE `du_lieu_trong_ky` rồi cả tử số/mẫu số đều đọc từ đó giúp giảm sai lệch định nghĩa.

### 23.2. Không tự thay đổi cấp hạt khi thêm JOIN

Giả sử bảng doanh thu có mỗi ngày một dòng, nhưng JOIN sang bảng khuyến mãi có nhiều khuyến mãi cùng ngày. Nếu SUM doanh thu sau JOIN, tổng ngày có thể bị lặp theo số khuyến mãi.

Chỉ số lũy kế đúng hay tỷ lệ đóng góp đúng cần **đúng cấp dữ liệu trước khi áp dụng window**. Một công thức window không tự sửa lỗi JOIN nhân dòng.

## 24. Hiệu năng của tổng lũy kế và trung bình trượt

Các window có `ORDER BY` thường cần một thứ tự nội bộ. Trên dữ liệu lớn, việc sắp xếp và tổ chức partition có thể tốn CPU, bộ nhớ hoặc đĩa tạm.

### 24.1. Xác định tập đầu vào nhỏ nhất nhưng đúng nghiệp vụ

Nếu chỉ cần tổng lũy kế theo ngày, hãy **GROUP BY ngày trước** để giảm số hàng cho bước window, miễn bạn không cần giữ chi tiết giao dịch.

Ví dụ:

~~~sql
WITH theo_ngay AS (
    SELECT ngay, SUM(so_tien) AS tong_ngay
    FROM pt_giao_dich
    WHERE ngay >= DATE '2026-10-01'
      AND ngay < DATE '2026-11-01'
    GROUP BY ngay
)
SELECT
    ngay,
    SUM(tong_ngay) OVER (
        ORDER BY ngay
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS tong_luy_ke
FROM theo_ngay
ORDER BY ngay;
~~~

Một bảng có hàng triệu giao dịch trong tháng có thể được thu về khoảng vài chục hàng tổng theo ngày. Nhưng nếu KPI yêu cầu lũy kế **theo từng giao dịch**, không thể thay nguồn bằng tổng ngày mà vẫn giữ đầy đủ ý nghĩa từng giao dịch.

### 24.2. EXPLAIN PostgreSQL

~~~sql
EXPLAIN
WITH theo_ngay AS (
    SELECT ngay, SUM(so_tien) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
)
SELECT
    ngay,
    SUM(tong_ngay) OVER (
        ORDER BY ngay
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke
FROM theo_ngay;
~~~

`EXPLAIN` cho kế hoạch dự kiến. Bạn có thể thấy các bước như Aggregate/HashAggregate, Sort, WindowAgg hoặc các lựa chọn khác tùy bộ tối ưu, thống kê và phiên bản.

`EXPLAIN ANALYZE` thực sự chạy truy vấn để đo; chỉ dùng ở môi trường phù hợp và khi hiểu tác động của statement. Không nên suy ra hiệu năng của hệ thống triệu dòng từ bảng tạm vài chục dòng.

### 24.3. Index và thứ tự

Trên bảng thật, index theo `(ngay, id)` có thể hữu ích cho những truy vấn lọc/sắp theo ngày–ID. Nếu thường phân vùng theo nhóm rồi sắp ngày, index `(ma_nhom, ngay, id)` có thể phù hợp với một số kế hoạch.

Ví dụ **tùy chọn** trong môi trường học:

~~~sql
CREATE INDEX pt_giao_dich_nhom_ngay_id_idx
ON pt_giao_dich (ma_nhom, ngay, id);
~~~

Index không bảo đảm máy chủ luôn bỏ được Sort, cũng không tự giúp một phép tổng hợp cấp ngày chạy nhanh trong mọi trường hợp. Cần xem lượng dữ liệu, điều kiện, mức phân bố, chi phí ghi và kế hoạch thật.

### 24.4. CTE không phải bảng cache bảo đảm

Trong PostgreSQL hiện đại, một CTE không đệ quy có thể được optimizer inline hoặc materialize tùy điều kiện. Đặt nhiều CTE trước window **giúp diễn đạt các bước** nhưng không mặc nhiên làm chúng được tính sẵn một lần rồi tái sử dụng như bảng vật lý.

Khi báo cáo chạy lặp thường xuyên trên dữ liệu lớn, có thể cân nhắc bảng tổng hợp theo ngày hoặc materialized view được cập nhật theo chính sách, nhưng đó là quyết định kiến trúc dữ liệu ngoài phạm vi một truy vấn mẫu.

## 25. Khác biệt giữa các hệ quản trị SQL

Hầu hết DBMS hiện đại hỗ trợ các hàm cửa sổ, nhưng **hỗ trợ frame, kiểu số, cách sinh lịch và cách xử lý NULL/DATE** có thể khác.

| Hệ quản trị | Khả năng chính | Lưu ý |
|---|---|---|
| **PostgreSQL** | `SUM/AVG OVER`, `PARTITION BY`, `ROWS/RANGE/GROUPS`, `generate_series` | Cú pháp `::DATE`, `INTERVAL '2 days'`, `NULLS FIRST/LAST`, named WINDOW tùy phiên bản |
| **MySQL 8.0+** | Window functions và nhiều loại frame | Cú pháp tạo dãy ngày, RANGE với khoảng thời gian và kiểu trả về tùy phiên bản |
| **MariaDB** | Window functions ở các phiên bản phù hợp | Kiểm tra chi tiết giới hạn frame và hàm số |
| **SQL Server** | `SUM/AVG OVER`, `PARTITION BY`, `ROWS` | Không dùng `generate_series` với cú pháp PostgreSQL; `NULLIF` và `CAST` vẫn hữu ích; kiểm tra khả năng tạo dãy theo phiên bản |
| **Oracle** | Analytic functions và frame | Cú pháp ngày, INTERVAL, khung thời gian và sắp xếp có đặc điểm riêng |
| **SQLite 3.25+** | Window functions, các loại frame ở phiên bản hỗ trợ | Không dùng cú pháp PostgreSQL `::NUMERIC`; ngày thường cần hàm/CTE riêng |

### 25.1. Mẫu SUM lũy kế tương đối di động

~~~sql
SELECT
    ngay,
    tong_ngay,
    SUM(tong_ngay) OVER (
        ORDER BY ngay
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke
FROM bao_cao_theo_ngay;
~~~

`bao_cao_theo_ngay` là bảng/CTE minh họa một hàng mỗi ngày. Mẫu `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` được nhiều DBMS hỗ trợ, nhưng vẫn cần kiểm tra phiên bản và cú pháp chính xác.

### 25.2. SQL Server: phần trăm với DECIMAL

~~~sql
SELECT
    Ngay,
    TongNgay,
    CAST(100.0 * TongNgay
         / NULLIF(SUM(TongNgay) OVER (), 0)
         AS DECIMAL(10,2)) AS TyLePhanTram
FROM dbo.BaoCaoNgay;
~~~

Nguồn `dbo.BaoCaoNgay` là **bảng giả định** có một hàng/ngày. SQL Server thường dùng `CAST(... AS DECIMAL(...))` để kiểm soát kiểu và độ chính xác; cú pháp `::NUMERIC` của PostgreSQL không được dùng nguyên xi.

### 25.3. MySQL: rolling average với ROWS

~~~sql
SELECT
    ngay,
    tong_ngay,
    AVG(tong_ngay) OVER (
        ORDER BY ngay
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS tb_3_hang
FROM bao_cao_theo_ngay;
~~~

Ở MySQL 8.0+ có hỗ trợ window functions, đây là mẫu trung bình **tối đa ba hàng**. Muốn “ba ngày lịch” khi dữ liệu thiếu ngày, vẫn cần chuẩn hóa tập ngày hoặc dùng phương pháp khoảng thời gian phù hợp.

### 25.4. Khác biệt kiểu dữ liệu và phép chia

Đối với những cột kiểu nguyên, một số DBMS có hành vi chia nguyên hoặc kiểu AVG khác PostgreSQL. Khi tính tỷ lệ, nên ép kiểu số thập phân phù hợp:

~~~sql
CAST(gia_tri AS DECIMAL(18,4))
/
NULLIF(CAST(tong AS DECIMAL(18,4)), 0)
~~~

Đây là đoạn **biểu thức minh họa**, với các tên cột giả định. Chọn độ chính xác/scale theo yêu cầu tiền tệ và phạm vi tổng; không cố định `DECIMAL(18,4)` cho mọi hệ thống.

### 25.5. ROUND và hiển thị tỷ lệ

Chức năng và kiểu trả về của `ROUND` có thể khác khi đối số là số thực hoặc số thập phân; trong PostgreSQL `ROUND(numeric, so_chu_so)` là dạng thường dùng cho tính tiền có kiểm soát.

Không dùng việc hiển thị hai số lẻ như một chứng minh dữ liệu chính xác tới hai chữ số; cần phân biệt **phép tính nội bộ** và **định dạng kết quả**.

## 26. Bài tập thực hành có lời giải

Các bài dùng bảng `pt_nhom` và `pt_giao_dich` đã tạo ở phần 3. Không chạy các lệnh làm thay đổi dữ liệu trong phần bài tập. Khi dùng lịch, hãy giữ đúng phạm vi ngày được nêu trong bài.

### Bài 1. Tổng lũy kế theo ngày

**Yêu cầu:** tính tổng tiền mỗi ngày có giao dịch, rồi cộng dồn từ 01/10 đến 10/10.

~~~sql
WITH theo_ngay AS (
    SELECT ngay, COALESCE(SUM(so_tien), 0) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
)
SELECT
    ngay,
    tong_ngay,
    SUM(tong_ngay) OVER (
        ORDER BY ngay
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke
FROM theo_ngay
ORDER BY ngay;
~~~

**Đáp án:** lần lượt 180, 470, 650, 900, 1000, 1300, 1300, 1700, 1900, 2000.

### Bài 2. Tổng lũy kế theo từng giao dịch

**Yêu cầu:** giữ 21 dòng, cộng theo ngày rồi ID.

~~~sql
SELECT
    id,
    ngay,
    so_tien,
    SUM(so_tien) OVER (
        ORDER BY ngay, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke
FROM pt_giao_dich
ORDER BY ngay, id;
~~~

**Đáp án:** 01/10 giao dịch 101 có lũy kế 100, giao dịch 201 là 180. Ngày 02/10 lần lượt ID 102 → 380, 103 → 430, 301 → 470.

### Bài 3. Lũy kế của riêng Sách

~~~sql
SELECT
    id,
    ngay,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY ma_nhom
        ORDER BY ngay, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke_sach
FROM pt_giao_dich
WHERE ma_nhom = 'SACH'
ORDER BY ngay, id;
~~~

**Đáp án:** giao dịch 101–108 có lũy kế 100, 300, 350, 500, 500, 500, 800, 900.

### Bài 4. Trung bình trượt ba ngày có giao dịch

~~~sql
WITH theo_ngay AS (
    SELECT ngay, COALESCE(SUM(so_tien), 0) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
)
SELECT
    ngay,
    ROUND(
        AVG(tong_ngay) OVER (
            ORDER BY ngay
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS tb_3_hang
FROM theo_ngay
ORDER BY ngay;
~~~

**Đáp án:** ngày 04/10 = 240.00; ngày 07/10 = 133.33; ngày 10/10 = 233.33. Với dữ liệu 01–10/10 liên tục mỗi ngày có giao dịch, ba hàng này tương ứng ba ngày lịch.

### Bài 5. Vì sao ngày đầu không chia cho 3?

**Đề bài:** ở 01/10, `ROWS 2 PRECEDING` chỉ có một dòng. Tại sao AVG bằng 180 mà không phải 60?

**Đáp án:** frame chỉ có **một hàng hiện có** nên AVG chia cho 1. SQL không tự sinh ngày 29 và 30/9 với giá trị 0. Nếu bắt buộc đủ ba ngày, cần thêm dữ liệu lịch trước kỳ hoặc chọn chính sách chờ đủ ba ngày mới hiện trung bình.

### Bài 6. Trung bình ba ngày cuối của kỳ 12 ngày

~~~sql
WITH lich AS (
    SELECT g.ngay_ts::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-10-01',
        TIMESTAMP '2026-10-12',
        INTERVAL '1 day'
    ) AS g(ngay_ts)
),
ngay_co_tong AS (
    SELECT
        lich.ngay,
        COALESCE(SUM(gd.so_tien), 0) AS tong_ngay
    FROM lich
    LEFT JOIN pt_giao_dich AS gd
        ON gd.ngay = lich.ngay
    GROUP BY lich.ngay
)
SELECT
    ngay,
    tong_ngay,
    ROUND(
        AVG(tong_ngay) OVER (
            ORDER BY ngay
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS tb_3_ngay
FROM ngay_co_tong
ORDER BY ngay;
~~~

**Đáp án:** ngày 11/10 trung bình 100.00, ngày 12/10 trung bình 33.33. Điều này dựa trên giả định hai ngày không có giao dịch được xem là 0.

### Bài 7. Tỷ lệ đóng góp nhóm trong tổng kỳ

~~~sql
WITH theo_nhom AS (
    SELECT
        n.ma_nhom,
        n.thu_tu,
        COALESCE(SUM(g.so_tien), 0) AS tong
    FROM pt_nhom AS n
    LEFT JOIN pt_giao_dich AS g
        ON g.ma_nhom = n.ma_nhom
    GROUP BY n.ma_nhom, n.thu_tu
)
SELECT
    ma_nhom,
    tong,
    ROUND(
        100.0 * tong
        / NULLIF(SUM(tong) OVER (), 0),
        2
    ) AS ty_le
FROM theo_nhom
ORDER BY tong DESC, thu_tu;
~~~

**Đáp án:** Sách 45%, VPP 30%, Phụ kiện 25%, Dịch vụ 0%.

### Bài 8. Tỷ lệ của giao dịch 107 trong nhóm Sách

**Đề bài:** ID 107 có tiền 300, tổng Sách 900. Tính tỷ lệ và viết truy vấn cho toàn bộ giao dịch Sách.

~~~sql
SELECT
    id,
    so_tien,
    ROUND(
        100.0 * so_tien
        / NULLIF(
            SUM(so_tien) OVER (PARTITION BY ma_nhom),
            0
        ),
        2
    ) AS ty_le_trong_nhom
FROM pt_giao_dich
WHERE ma_nhom = 'SACH'
ORDER BY id;
~~~

**Đáp án:** ID 107 đóng góp **33.33%** vào tổng tiền Sách.

### Bài 9. Tỷ lệ của Sách trong ngày 02/10

~~~sql
WITH theo_ngay_nhom AS (
    SELECT
        ngay,
        ma_nhom,
        SUM(so_tien) AS tong_nhom_ngay
    FROM pt_giao_dich
    WHERE ngay = DATE '2026-10-02'
    GROUP BY ngay, ma_nhom
)
SELECT
    ma_nhom,
    tong_nhom_ngay,
    ROUND(
        100.0 * tong_nhom_ngay
        / NULLIF(
            SUM(tong_nhom_ngay) OVER (PARTITION BY ngay),
            0
        ),
        2
    ) AS ty_le
FROM theo_ngay_nhom
ORDER BY ty_le DESC;
~~~

**Đáp án:** Sách 250/290 = **86.21%**, Phụ kiện 40/290 = **13.79%**. VPP và Dịch vụ không có giao dịch ngày ấy nên không xuất hiện trong truy vấn chỉ đọc dữ liệu nguồn; muốn đủ bốn nhóm, dùng lưới ngày × nhóm như phần 17.

### Bài 10. Tỷ lệ lũy kế tới ngày 08/10

~~~sql
WITH theo_ngay AS (
    SELECT ngay, SUM(so_tien) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
),
chi_so AS (
    SELECT
        ngay,
        SUM(tong_ngay) OVER (
            ORDER BY ngay
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS luy_ke,
        SUM(tong_ngay) OVER () AS tong_ky
    FROM theo_ngay
)
SELECT
    ngay,
    luy_ke,
    ROUND(
        100.0 * luy_ke / NULLIF(tong_ky, 0),
        2
    ) AS phan_tram_luy_ke
FROM chi_so
WHERE ngay = DATE '2026-10-08';
~~~

**Đáp án:** lũy kế 1700, chiếm **85.00%** tổng kỳ 2000. Vì việc lọc ngày được đặt **ở SELECT ngoài**, cửa sổ ở CTE đã nhìn thấy toàn bộ các ngày trước 08/10.

### Bài 11. Tỷ lệ lũy kế của các nhóm theo thứ tự giảm dần

~~~sql
WITH theo_nhom AS (
    SELECT
        n.ma_nhom,
        n.thu_tu,
        COALESCE(SUM(g.so_tien), 0) AS tong
    FROM pt_nhom AS n
    LEFT JOIN pt_giao_dich AS g
        ON g.ma_nhom = n.ma_nhom
    GROUP BY n.ma_nhom, n.thu_tu
),
xep AS (
    SELECT
        ma_nhom,
        tong,
        thu_tu,
        SUM(tong) OVER () AS tong_ky,
        SUM(tong) OVER (
            ORDER BY tong DESC, thu_tu
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS tong_luy_ke
    FROM theo_nhom
)
SELECT
    ma_nhom,
    ROUND(
        100.0 * tong_luy_ke / NULLIF(tong_ky, 0),
        2
    ) AS ty_le_luy_ke
FROM xep
ORDER BY tong DESC, thu_tu;
~~~

**Đáp án:** Sách 45%, VPP 75%, Phụ kiện 100%, Dịch vụ 100%.

### Bài 12. Tại sao AVG theo giao dịch khác AVG theo ngày?

**Đề bài:** tính hai chỉ số:

~~~sql
SELECT ROUND(AVG(so_tien), 2)
FROM pt_giao_dich;

WITH theo_ngay AS (
    SELECT ngay, COALESCE(SUM(so_tien), 0) AS tong_ngay
    FROM pt_giao_dich
    GROUP BY ngay
)
SELECT ROUND(AVG(tong_ngay), 2)
FROM theo_ngay;
~~~

**Đáp án:** trung bình giao dịch có tiền là **111.11** vì chia 2000/18; trung bình ngày có giao dịch là **200.00** vì chia 2000/10. Hai mẫu số khác nhau.

### Bài 13. Phân biệt NULL và 0 của Sách

**Yêu cầu:** chỉ ra trạng thái ngày 05/10 và 07/10 của Sách.

~~~sql
SELECT
    ngay,
    COUNT(*) AS so_giao_dich,
    COUNT(so_tien) AS so_co_tien,
    SUM(so_tien) AS tong_raw
FROM pt_giao_dich
WHERE ma_nhom = 'SACH'
  AND ngay IN (
      DATE '2026-10-05',
      DATE '2026-10-07'
  )
GROUP BY ngay
ORDER BY ngay;
~~~

**Đáp án:** 05/10 có một giao dịch, không có số tiền và SUM NULL; 07/10 có một giao dịch, một số tiền không NULL và SUM bằng 0. Nếu COALESCE cả hai tổng thành 0, người đọc sẽ mất khác biệt này nếu không giữ cột đếm.

### Bài 14. Đếm ba giao dịch thay vì ba ngày

**Đề bài:** vì sao trên Sách, trung bình ba giao dịch tại ID 107 bằng 150, trong khi trung bình ba ngày 06–08/10 (với các ngày không có giao dịch được coi là 0) bằng 100?

**Đáp án:** frame theo **giao dịch** của ID 107 gồm ba dòng 105 (NULL), 106 (0), 107 (300), nên AVG chỉ tính 0 và 300 → 150. Frame theo **ngày** gồm tổng Sách 06/10 = 0, 07/10 = 0, 08/10 = 300 → AVG = 100. Cần xác định đầu vào là giao dịch hay ngày.

### Bài 15. Tỷ lệ trên một tổng bằng 0

**Đề bài:** ngày 07/10 có tổng tiền 0. Truy vấn `100.0 * tong_nhom_ngay / tong_ngay` có vấn đề gì?

**Đáp án:** có mẫu số bằng 0. Cần dùng:

~~~sql
100.0 * tong_nhom_ngay / NULLIF(tong_ngay, 0)
~~~

để kết quả NULL, hoặc định nghĩa một chính sách hiển thị khác nếu nghiệp vụ yêu cầu. Không được mặc nhiên coi nhóm duy nhất có giao dịch là nhóm đóng góp 100% **số tiền** trong khi tổng tiền bằng 0.

### Bài 16. Lũy kế tháng phải reset khi nào?

**Đề bài:** trong một bảng chứa nhiều năm, vì sao `PARTITION BY EXTRACT(MONTH FROM ngay)` không đủ?

**Đáp án:** nó đưa tháng 10 của các năm khác nhau vào chung một partition. Hãy dùng `PARTITION BY DATE_TRUNC('month', ngay)` hoặc khóa gồm năm và tháng để mỗi kỳ bắt đầu lũy kế độc lập.

### Bài 17. Top nhóm đạt ít nhất 70% tổng

**Đề bài:** các nhóm có tỷ lệ Sách 45%, VPP 30%, Phụ kiện 25%, Dịch vụ 0%. Nếu chọn nhóm lớn nhất trước cho đến khi đạt ít nhất 70%, cần bao nhiêu nhóm?

**Đáp án:** **hai nhóm**: Sách 45%, cộng VPP thành 75%. Cần lấy **dòng làm vượt ngưỡng**, không chỉ những dòng có tỷ lệ lũy kế còn dưới 70% (cách lọc đó sẽ bỏ VPP và không đạt mục tiêu).

## 27. Checklist áp dụng trong báo cáo thực tế

Trước khi đưa ba mẫu truy vấn vào dashboard hoặc hệ thống phân tích, hãy tự xác nhận:

1. **Một hàng nguồn đại diện cho gì?** Giao dịch, ngày, nhóm/ngày hay một đơn?
2. **Tổng lũy kế theo thứ tự nào?** Ngày, thời điểm, hay ngày + ID để phá hòa?
3. **Có cần reset lũy kế theo nhóm/tháng không?** Nếu có, dùng PARTITION BY đủ khóa.
4. **Tôi muốn trung bình ba hàng, ba ngày lịch hay ba ngày có dữ liệu?** Ba định nghĩa không giống nhau.
5. **Có ngày thiếu dữ liệu không?** Nếu cần đủ lịch, phải sinh hàng và chọn chính sách ngày rỗng.
6. **Ngày không giao dịch có chắc bằng 0 không?** Hay hệ thống chưa chốt hoặc chưa gửi dữ liệu?
7. **Trung bình trên những giá trị nào?** AVG bỏ qua NULL; COALESCE bên trong AVG thay đổi mẫu số.
8. **Tỷ lệ đóng góp so với tổng nào?** Toàn kỳ, từng ngày, từng nhóm, ngân sách hay mục tiêu?
9. **Mẫu số có thể bằng 0 hoặc NULL không?** Dùng NULLIF và quy tắc hiển thị phù hợp.
10. **Có JOIN một-nhiều trước khi tổng hợp không?** Kiểm tra nguy cơ nhân số tiền.
11. **Có dùng GROUP BY đúng cấp trước window không?** Nếu yêu cầu một hàng/ngày, phải gom giao dịch trong ngày.
12. **Frame có được chỉ rõ không?** Đặc biệt với tổng lũy kế cần ROWS và dữ liệu có peers.
13. **Cột tỷ lệ có tên đủ rõ không?** Phân biệt tỷ lệ ngày, tỷ lệ nhóm và tỷ lệ lũy kế.
14. **Làm tròn ở bước nào?** Nên tính trên số gốc rồi làm tròn khi trình bày, trừ khi quy định nghiệp vụ khác.
15. **Kết quả có cần thứ tự ổn định không?** Viết ORDER BY ở SELECT ngoài cùng.
16. **Có đang chạy trên DBMS/phiên bản nào?** Kiểm tra cú pháp generate_series, frame theo khoảng thời gian, kiểu DECIMAL và ROUND.
17. **Hiệu năng đã được đo chưa?** Dùng EXPLAIN và khối lượng dữ liệu thực thay vì đoán.

## 28. Tổng kết

**Tổng lũy kế, trung bình trượt và tỷ lệ đóng góp** là ba mẫu báo cáo SQL rất gần nhau về cú pháp nhưng khác nhau về **phạm vi tính toán**:

- Tổng lũy kế dùng `SUM(...) OVER (ORDER BY ... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` để cộng dồn theo thứ tự đã chọn.
- Trung bình trượt dùng `AVG(...) OVER (ORDER BY ... ROWS BETWEEN n PRECEDING AND CURRENT ROW)`, nhưng `ROWS` đếm hàng; muốn trung bình theo ngày lịch phải chuẩn hóa nguồn theo ngày hoặc dùng khung thời gian phù hợp.
- Tỷ lệ đóng góp lấy **giá trị thành phần chia tổng tham chiếu**, thường dùng `SUM(...) OVER ()` hoặc `SUM(...) OVER (PARTITION BY ...)` làm mẫu số và `NULLIF(..., 0)` để tránh chia cho 0.
- Khi yêu cầu một hàng mỗi ngày hoặc nhóm, hãy `GROUP BY` **trước** khi tính window; khi yêu cầu một hàng mỗi giao dịch, giữ cấp giao dịch và khai báo khóa sắp xếp rõ ràng.
- `NULL`, số 0, ngày không có dòng và ngày chưa được ghi nhận **không đồng nghĩa**. Các quyết định COALESCE và điền lịch cần phản ánh đúng quy tắc dữ liệu.
- Cùng một số tiền có thể cho tỷ lệ **theo ngày**, **theo danh mục**, **toàn kỳ** hoặc **lũy kế** khác nhau; tên cột và mô tả mẫu số phải rõ ràng.

Khi xác định đúng **cấp dữ liệu → thứ tự → frame → mẫu số**, bạn sẽ xây dựng được các chỉ số xu hướng và đóng góp vừa có ý nghĩa nghiệp vụ, vừa dễ kiểm tra và mở rộng trong SQL.
