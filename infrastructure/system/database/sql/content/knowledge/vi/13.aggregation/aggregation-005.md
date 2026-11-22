# Quy tắc chọn cột khi có GROUP BY trong SQL

> **Module:** Database SQL  
> **Chương:** Tổng hợp dữ liệu  
> **Bài học:** Quy tắc chọn cột khi có GROUP BY

## 1. Mục tiêu bài học

Sau khi hoàn thành bài học, bạn có thể:

- Giải thích được **GROUP BY tạo ra một dòng cho mỗi nhóm** và vì sao danh sách cột trong SELECT phải tuân theo quy tắc riêng.
- Phân biệt **cột dùng để nhóm**, **hàm tổng hợp** và **cột chi tiết không được xác định duy nhất trong nhóm**.
- Viết truy vấn SELECT kết hợp **GROUP BY**, **COUNT**, **SUM**, **AVG**, **MIN**, **MAX**, **WHERE**, **HAVING** và **ORDER BY** đúng ngữ nghĩa.
- Phát hiện câu lệnh kiểu **SELECT danh_muc, ten_san_pham, COUNT(*) ... GROUP BY danh_muc** có thể bị từ chối hoặc trả dữ liệu không xác định.
- Hiểu ngoại lệ **phụ thuộc hàm (functional dependency)** và sự khác nhau giữa PostgreSQL, MySQL, SQL Server, Oracle Database và SQLite.
- Biết khi nào cần bổ sung cột vào GROUP BY, khi nào cần tổng hợp cột bằng MIN/MAX, và khi nào phải chọn một **dòng đại diện** bằng truy vấn con hoặc hàm cửa sổ.
- Hiểu trường hợp nhóm chứa **NULL**, nhóm được tạo bởi biểu thức, cột sinh từ JOIN và dữ liệu bị nhân bản bởi quan hệ một-nhiều.
- Tránh ngộ nhận rằng **ORDER BY**, **DISTINCT**, **ANY_VALUE** hoặc **MAX** sẽ tự chọn “dòng đúng” cho mỗi nhóm.
- Kiểm tra kết quả tổng hợp bằng dữ liệu mẫu và diễn đạt đúng yêu cầu nghiệp vụ.

## 2. GROUP BY giải quyết vấn đề gì?

Trong SQL, một bảng giao dịch thường chứa **nhiều dòng chi tiết**. Ví dụ, mỗi đơn hàng là một dòng; mỗi khách hàng có thể có nhiều đơn. Khi cần thống kê “mỗi khách có bao nhiêu đơn” hoặc “mỗi danh mục mang lại bao nhiêu doanh thu”, ta cần gom các dòng chi tiết thành **nhóm**.

Giả sử bảng **don_hang** gồm:

| ma_don_hang | ma_khach_hang | trang_thai | tong_tien | ngay_dat |
|---:|---:|---|---:|---|
| 101 | 1 | PAID | 200000 | 2026-01-10 |
| 102 | 1 | PAID | 150000 | 2026-01-20 |
| 103 | 2 | PENDING | 100000 | 2026-02-01 |
| 104 | 2 | PAID | 300000 | 2026-02-05 |
| 105 | 3 | PAID | 120000 | 2026-02-07 |
| 106 | 2 | PAID | 250000 | 2026-02-10 |
| 107 | NULL | CANCELLED | 90000 | 2026-02-11 |

Các cột mang ý nghĩa:

- **ma_don_hang**: mã duy nhất của từng đơn.
- **ma_khach_hang**: mã khách sở hữu đơn, có thể NULL trong tập minh họa.
- **trang_thai**: trạng thái đơn.
- **tong_tien**: giá trị từng đơn, đơn vị đồng Việt Nam.
- **ngay_dat**: ngày đặt đơn, kiểu DATE trong ví dụ.

Không dùng GROUP BY:

~~~sql
SELECT
    ma_don_hang,
    ma_khach_hang,
    tong_tien
FROM don_hang;
~~~

Kết quả có một dòng cho mỗi đơn (7 dòng).

Dùng GROUP BY:

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang
ORDER BY ma_khach_hang;
~~~

Kết quả về mặt giá trị:

| ma_khach_hang | so_don |
|---:|---:|
| 1 | 2 |
| 2 | 3 |
| 3 | 1 |
| NULL | 1 |

GROUP BY gom các dòng có cùng giá trị **ma_khach_hang** thành nhóm. Mỗi nhóm tạo một dòng kết quả, và **COUNT(*)** đếm số dòng trong nhóm đó.

**Ý tưởng cốt lõi:** sau khi gom nhóm theo mã khách, mỗi nhóm chỉ có **một mã khách**, nhưng có thể có **nhiều mã đơn, nhiều ngày đặt và nhiều tổng tiền**. Vì vậy, SELECT không thể tùy ý lấy một cột chi tiết bất kỳ mà không quy định nó đại diện cho giá trị nào trong nhóm.

## 3. Quy tắc nền tảng khi chọn cột với GROUP BY

Trong một truy vấn SELECT có GROUP BY, các biểu thức được trả ra thông thường phải thuộc một trong những loại sau:

1. **Biểu thức khóa nhóm** hoặc biểu thức dựa trên những giá trị đã được xác định duy nhất cho mỗi nhóm.
2. **Biểu thức tổng hợp** như COUNT(*), SUM(...), AVG(...), MIN(...), MAX(...).
3. **Biểu thức hằng** hoặc biểu thức chỉ kết hợp các giá trị đã xác định được cho mỗi nhóm.
4. Trong những DBMS hỗ trợ, cột **phụ thuộc hàm** vào khóa nhóm cũng có thể được cho phép mà không cần liệt kê trực tiếp trong GROUP BY.

Cách diễn giải ngắn gọn cho người mới bắt đầu:

> **Mỗi giá trị xuất hiện ở một dòng kết quả nhóm phải có một ý nghĩa xác định đối với cả nhóm đó.** Nếu một cột có nhiều giá trị khác nhau trong cùng nhóm, bạn phải mô tả cách chọn/tổng hợp nó, hoặc thay đổi cách nhóm.

### 3.1. Ví dụ hợp lệ: khóa nhóm và phép tổng hợp

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don,
    SUM(tong_tien) AS tong_chi,
    MIN(ngay_dat) AS ngay_dau,
    MAX(ngay_dat) AS ngay_cuoi
FROM don_hang
GROUP BY ma_khach_hang
ORDER BY ma_khach_hang;
~~~

Ở mỗi nhóm khách:

- **ma_khach_hang** không đổi trong nhóm, nên có thể trả trực tiếp.
- **COUNT(*)** trả số dòng của nhóm.
- **SUM(tong_tien)** trả tổng tiền trong nhóm.
- **MIN(ngay_dat)** và **MAX(ngay_dat)** lần lượt trả ngày sớm nhất và muộn nhất trong nhóm.

Kết quả cho ba khách có mã không NULL:

| ma_khach_hang | so_don | tong_chi | ngay_dau | ngay_cuoi |
|---:|---:|---:|---|---|
| 1 | 2 | 350000 | 2026-01-10 | 2026-01-20 |
| 2 | 3 | 650000 | 2026-02-01 | 2026-02-10 |
| 3 | 1 | 120000 | 2026-02-07 | 2026-02-07 |

Nhóm ma_khach_hang NULL cũng có một dòng, với so_don = 1 và tong_chi = 90000.

### 3.2. Ví dụ không hợp lệ theo quy tắc nghiêm ngặt

~~~sql
-- Thiếu quy tắc chọn ma_don_hang của mỗi nhóm.
SELECT
    ma_khach_hang,
    ma_don_hang,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Với khách hàng 1, nhóm gồm **đơn 101 và 102**. Truy vấn không nói phải trả **101**, **102**, đơn đầu tiên hay đơn cuối cùng. Với khách hàng 2 còn có ba mã đơn **103, 104, 106**.

Các DBMS kiểm tra GROUP BY nghiêm ngặt thường từ chối truy vấn vì **ma_don_hang** không nằm trong GROUP BY và không được tổng hợp. Một số DBMS/chế độ có thể chạy nhưng chọn một giá trị không bảo đảm; đó **không** phải cách viết đáng tin cậy.

### 3.3. “Có mặt trong GROUP BY” và “có trong SELECT” không bắt buộc trùng nhau

Có thể nhóm theo nhiều cột nhưng chỉ hiển thị một số giá trị nhóm:

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang, trang_thai;
~~~

Truy vấn này có thể chạy nhưng dễ gây hiểu nhầm: mỗi cặp **(ma_khach_hang, trang_thai)** tạo một nhóm riêng, trong khi SELECT chỉ hiển thị mã khách. Do đó, cùng mã khách có thể xuất hiện ở **nhiều dòng kết quả** mà không có cột trạng thái giải thích tại sao.

**GROUP BY quyết định mức chi tiết của kết quả; SELECT không quyết định mức chi tiết đó.** Khi GROUP BY nhiều cột, thường nên hiển thị đủ các khóa nhóm để người đọc hiểu mỗi dòng đang biểu diễn gì.

## 4. Mức chi tiết (granularity/grain) của nhóm

Trước khi viết GROUP BY, nên trả lời:

> **Một dòng trong kết quả đại diện cho một đối tượng hoặc một tổ hợp khóa nào?**

Ví dụ:

| Yêu cầu | Khóa nhóm | Ý nghĩa mỗi dòng |
|---|---|---|
| Số đơn theo khách | ma_khach_hang | Một khách |
| Số đơn theo trạng thái | trang_thai | Một trạng thái |
| Số đơn theo khách và trạng thái | ma_khach_hang, trang_thai | Một cặp khách–trạng thái |
| Doanh thu theo ngày | ngay_dat | Một ngày |
| Doanh thu theo tháng | Biểu thức tháng/năm từ ngay_dat | Một tháng |
| Doanh thu toàn hệ thống | Không có GROUP BY tường minh, chỉ hàm tổng hợp | Một giá trị tổng thể |

Ví dụ thống kê theo khách và trạng thái:

~~~sql
SELECT
    ma_khach_hang,
    trang_thai,
    COUNT(*) AS so_don,
    SUM(tong_tien) AS tong_tien
FROM don_hang
GROUP BY ma_khach_hang, trang_thai
ORDER BY ma_khach_hang, trang_thai;
~~~

Với khách hàng 2:

| ma_khach_hang | trang_thai | so_don | tong_tien |
|---:|---|---:|---:|
| 2 | PAID | 2 | 550000 |
| 2 | PENDING | 1 | 100000 |

Nếu bỏ **trang_thai** khỏi GROUP BY, hai nhóm này nhập thành một nhóm, có **3 đơn** và **650000** tổng tiền. Nếu chỉ bỏ nó khỏi SELECT nhưng vẫn giữ GROUP BY, kết quả có thể có hai dòng mã khách 2 trông giống nhau ở cột khóa hiển thị.

**Sai mức chi tiết là nguyên nhân của nhiều báo cáo sai, kể cả khi cú pháp SQL được DBMS chấp nhận.**

## 5. Những biểu thức nào được phép nằm trong SELECT?

### 5.1. Cột thuộc khóa GROUP BY

~~~sql
SELECT
    trang_thai,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY trang_thai;
~~~

**trang_thai** đã được dùng để chia nhóm, nên giá trị của nó xác định duy nhất trong mỗi nhóm.

### 5.2. Hàm tổng hợp

~~~sql
SELECT
    trang_thai,
    COUNT(*) AS so_don,
    SUM(tong_tien) AS tong_tien,
    AVG(tong_tien) AS trung_binh,
    MIN(tong_tien) AS thap_nhat,
    MAX(tong_tien) AS cao_nhat
FROM don_hang
GROUP BY trang_thai;
~~~

Mỗi hàm có ý nghĩa rõ trong nhóm:

- **COUNT(*)** đếm tất cả dòng.
- **COUNT(cot)** đếm các giá trị cot **không NULL**.
- **SUM(cot)** cộng các giá trị không NULL.
- **AVG(cot)** tính trung bình các giá trị không NULL.
- **MIN(cot)** và **MAX(cot)** tìm giá trị nhỏ nhất/lớn nhất trong nhóm, bỏ qua NULL theo ngữ nghĩa thông thường.

Nếu một nhóm chỉ có giá trị NULL cho tong_tien, SUM/AVG/MIN/MAX có thể trả NULL. **COUNT(*) vẫn đếm dòng**, không phụ thuộc tong_tien có NULL hay không.

### 5.3. Biểu thức tính từ khóa nhóm

Nếu **ma_khach_hang** đã là khóa nhóm, có thể áp dụng một phép tính xác định lên nó:

~~~sql
SELECT
    ma_khach_hang,
    ma_khach_hang + 1000 AS ma_bao_cao,
    COUNT(*) AS so_don
FROM don_hang
WHERE ma_khach_hang IS NOT NULL
GROUP BY ma_khach_hang;
~~~

**ma_khach_hang + 1000** xác định duy nhất bởi giá trị nhóm. Đây không phải một cột chi tiết biến động giữa các dòng.

Tương tự, với cột **ngay_dat** là khóa nhóm:

~~~sql
SELECT
    ngay_dat,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ngay_dat
ORDER BY ngay_dat;
~~~

Khi chỉ cần năm được tính từ ngày đã có trong GROUP BY, có thể dùng một hàm trích xuất năm nếu DBMS hỗ trợ đúng cú pháp:

~~~sql
SELECT
    ngay_dat,
    EXTRACT(YEAR FROM ngay_dat) AS nam,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ngay_dat;
~~~

**EXTRACT** là cú pháp phổ biến theo SQL chuẩn, nhưng SQL Server dùng **YEAR()** hoặc **DATEPART()**, và các DBMS có khác biệt về kiểu ngày. Ví dụ này minh họa quy tắc “biểu thức xác định từ cột đã được nhóm”, không khẳng định cú pháp chạy ở mọi DBMS.

### 5.4. Hằng số

~~~sql
SELECT
    trang_thai,
    'BAO_CAO_DON_HANG' AS loai_bao_cao,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY trang_thai;
~~~

Chuỗi **'BAO_CAO_DON_HANG'** là hằng số giống nhau cho tất cả dòng kết quả. Nó không làm phát sinh nhập nhằng khi gom nhóm.

### 5.5. Biểu thức kết hợp khóa nhóm và giá trị tổng hợp

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don,
    SUM(tong_tien) AS tong_chi,
    CASE
        WHEN SUM(tong_tien) >= 500000 THEN 'CAO'
        ELSE 'THAP_HOAC_CHUA_BIET'
    END AS nhom_chi_tieu
FROM don_hang
WHERE ma_khach_hang IS NOT NULL
GROUP BY ma_khach_hang;
~~~

Ở đây:

- **ma_khach_hang** là khóa nhóm.
- **SUM(tong_tien)** đã được tổng hợp trên mỗi nhóm.
- **CASE** đánh giá một giá trị tổng hợp cho cả nhóm.

Nhãn ELSE ở ví dụ được đặt cẩn thận: nếu SUM trả NULL, điều kiện **SUM(...) >= 500000** cho UNKNOWN và ELSE được chọn. Điều đó không có nghĩa chắc chắn chi tiêu thấp, nên nhãn gồm cả “chưa biết”.

## 6. Vì sao một cột không nhóm và không tổng hợp bị xem là mơ hồ?

Giả sử cần thống kê số đơn mỗi khách nhưng đồng thời hiển thị **ngày đặt đơn**:

~~~sql
SELECT
    ma_khach_hang,
    ngay_dat,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Với khách 1 có hai ngày **2026-01-10** và **2026-01-20**, giá trị **ngay_dat** nào phải được trả?

Câu SQL trên **không chứa quy tắc chọn**. Người viết có thể đang có một trong các ý định sau:

1. Muốn **ngày đầu tiên** của khách → MIN(ngay_dat).
2. Muốn **ngày gần nhất** → MAX(ngay_dat).
3. Muốn **mỗi ngày một dòng** → đưa ngay_dat vào GROUP BY.
4. Muốn **chi tiết mọi đơn kèm số đơn của khách** → dùng hàm cửa sổ, không gom thành một dòng/khách.
5. Muốn **dòng của đơn mới nhất**, bao gồm cả mã đơn và tổng tiền từ đúng dòng đó → dùng ROW_NUMBER hoặc truy vấn chọn dòng cụ thể.

Một lỗi cú pháp GROUP BY thường là dấu hiệu yêu cầu chưa được mô tả đủ, chứ không chỉ là thiếu một cột trong danh sách GROUP BY.

### 6.1. Sửa bằng MIN/MAX khi thật sự cần giá trị cực trị

~~~sql
SELECT
    ma_khach_hang,
    MIN(ngay_dat) AS ngay_dat_dau,
    MAX(ngay_dat) AS ngay_dat_cuoi,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Câu này trả một dòng mỗi khách và ngày sớm nhất/muộn nhất có ý nghĩa xác định.

**Không nên tự thay một cột chi tiết bằng MIN hoặc MAX chỉ để DBMS hết báo lỗi**. Hàm tổng hợp phải phù hợp ý nghĩa nghiệp vụ. Ví dụ MIN(ten_san_pham) có thể trả tên nhỏ nhất theo collation, không có nghĩa là “tên sản phẩm đại diện” được người dùng mong muốn.

### 6.2. Sửa bằng cách thêm cột vào GROUP BY nếu muốn mức chi tiết mới

~~~sql
SELECT
    ma_khach_hang,
    ngay_dat,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang, ngay_dat
ORDER BY ma_khach_hang, ngay_dat;
~~~

Câu này có một dòng cho **mỗi cặp khách–ngày**, không còn một dòng/khách. Với khách 1, kết quả có hai dòng, mỗi dòng đếm 1 đơn.

Đây là cách sửa **về cú pháp**, nhưng chỉ đúng **về nghiệp vụ** nếu báo cáo mong muốn nhóm theo cả khách và ngày.

## 7. Phụ thuộc hàm (functional dependency) — ngoại lệ quan trọng

Quy tắc “mọi cột không tổng hợp phải nằm trong GROUP BY” rất hữu ích khi mới học, nhưng là cách nói **chưa đầy đủ** đối với mọi tính năng và phương ngữ SQL.

**Phụ thuộc hàm** có nghĩa: khi đã biết giá trị của một tập cột A, ta xác định được một giá trị duy nhất của cột B. Ký hiệu:

~~~text
A -> B
~~~

Ví dụ, giả sử bảng **khach_hang** có:

~~~text
khach_hang(
    ma_khach_hang PRIMARY KEY,
    ten_khach_hang,
    thanh_pho
)
~~~

Do **ma_khach_hang** là khóa chính, mỗi mã khách chỉ gắn với một dòng khách. Trong bảng đó:

~~~text
ma_khach_hang -> ten_khach_hang
ma_khach_hang -> thanh_pho
~~~

Dù tên và thành phố không nằm trong GROUP BY, chúng có giá trị xác định nếu nhóm được tạo theo **khóa chính** của đúng bảng khách.

### 7.1. Ví dụ GROUP BY khóa chính

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COUNT(d.ma_don_hang) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY k.ma_khach_hang;
~~~

Trong những DBMS hỗ trợ suy luận phụ thuộc hàm phù hợp, cột **k.ten_khach_hang** được chấp nhận vì khóa chính **k.ma_khach_hang** xác định duy nhất tên khách trên mỗi nhóm.

Tuy nhiên, **không phải tất cả DBMS đều cho phép cú pháp này**, dù con người có thể suy luận rằng nó không mơ hồ.

Cách viết rộng rãi, dễ bảo trì hơn:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COUNT(d.ma_don_hang) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY
    k.ma_khach_hang,
    k.ten_khach_hang
ORDER BY k.ma_khach_hang;
~~~

Cách này thể hiện đủ các cột chi tiết được hiển thị và thường phù hợp nhiều hệ quản trị.

### 7.2. Phụ thuộc hàm không có nghĩa mọi cột ở bảng JOIN đều được chọn

Giả sử:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang,
    COUNT(*) AS so_dong
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY k.ma_khach_hang;
~~~

Ngay cả khi **k.ma_khach_hang** là khóa chính, một khách vẫn có thể có **nhiều ma_don_hang**. Vì thế:

~~~text
k.ma_khach_hang -> k.ten_khach_hang    (đúng)
k.ma_khach_hang -> d.ma_don_hang       (thường không đúng)
~~~

Sự hiện diện của JOIN không biến mọi cột thuộc các bảng liên quan thành dữ liệu duy nhất cho từng khách.

### 7.3. Unique key và nullable key

Một ràng buộc **UNIQUE** có thể biểu thị quan hệ một-đối-một khi các cột của khóa được bảo đảm không NULL, nhưng quy tắc NULL trong UNIQUE và cách DBMS chứng minh phụ thuộc hàm khác nhau. Không nên tự suy luận rằng mọi cột có UNIQUE là đủ để DBMS luôn cho phép bỏ cột khỏi GROUP BY.

Nếu muốn câu truy vấn có tính khả chuyển, hãy liệt kê các cột không tổng hợp cần dùng trong GROUP BY hoặc nhóm ở một truy vấn con rồi JOIN ra thông tin chi tiết sau đó.

## 8. Khác biệt giữa các hệ quản trị SQL

Cách kiểm tra GROUP BY phụ thuộc vào DBMS và phiên bản. Bảng dưới đây mô tả xu hướng quan trọng trong các truy vấn thông thường.

| DBMS | Cột không tổng hợp, không thuộc GROUP BY | Điểm cần lưu ý |
|---|---|---|
| **PostgreSQL** | Thường bị từ chối, trừ một số trường hợp phụ thuộc hàm được nhận diện | PostgreSQL có thể nhận diện phụ thuộc hàm khi khóa chính của bảng xuất hiện trong GROUP BY |
| **MySQL 5.7+/8.x** | Thường bị từ chối khi bật **ONLY_FULL_GROUP_BY**, trừ trường hợp DBMS suy ra phụ thuộc hàm hoặc giá trị đơn nhất theo điều kiện | Nếu tắt chế độ nghiêm ngặt, MySQL có thể chọn giá trị không bảo đảm từ nhóm |
| **SQL Server** | Thường yêu cầu cột không tổng hợp phải nằm trong GROUP BY hoặc được biểu diễn qua cột nhóm | Không nên giả định SQL Server cho bỏ tên khách chỉ vì đã nhóm theo khóa chính |
| **Oracle Database** | Những phiên bản phổ biến như 19c kiểm tra chặt các biểu thức không nhóm | Cú pháp GROUP BY và hỗ trợ alias có thay đổi giữa các bản; cần đối chiếu phiên bản |
| **SQLite** | Cho phép **bare columns** trong nhiều truy vấn GROUP BY | Giá trị cột không nhóm có thể được lấy từ một dòng không xác định; có quy tắc đặc biệt hạn chế với MIN/MAX |

**Bare column** là cột được đưa thẳng vào SELECT trong truy vấn tổng hợp nhưng không được nhóm và không nằm trong hàm tổng hợp.

### 8.1. PostgreSQL và ràng buộc khóa chính

Giả sử **khach_hang.ma_khach_hang** thật sự được khai báo **PRIMARY KEY**. PostgreSQL có thể chấp nhận:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COUNT(*) AS so_dong
FROM khach_hang k
GROUP BY k.ma_khach_hang;
~~~

Vì **ma_khach_hang** xác định duy nhất **ten_khach_hang**.

Nhưng nếu lấy dữ liệu từ **CTE**, bảng dẫn xuất hoặc một phép biến đổi khác, bộ phân tích SQL có thể không giữ đủ thông tin metadata để nhận diện cùng phụ thuộc hàm:

~~~sql
WITH k AS (
    SELECT ma_khach_hang, ten_khach_hang
    FROM khach_hang
)
SELECT
    ma_khach_hang,
    ten_khach_hang,
    COUNT(*) AS so_dong
FROM k
GROUP BY ma_khach_hang;
~~~

Không nên mặc định truy vấn này được chấp nhận chỉ vì nguồn CTE xuất phát từ bảng có khóa chính. Cách chắc chắn hơn là thêm **ten_khach_hang** vào GROUP BY hoặc viết lại truy vấn.

### 8.2. MySQL với ONLY_FULL_GROUP_BY

MySQL có chế độ SQL **ONLY_FULL_GROUP_BY** kiểm tra liệu các biểu thức không tổng hợp có nằm trong GROUP BY hoặc có thể được xác định từ khóa nhóm/theo điều kiện hay không.

Với chế độ này được bật, truy vấn:

~~~sql
SELECT ma_khach_hang, ma_don_hang, COUNT(*)
FROM don_hang
GROUP BY ma_khach_hang;
~~~

thường bị từ chối vì **ma_don_hang** không được xác định bởi mã khách.

Nếu tắt **ONLY_FULL_GROUP_BY**, MySQL có thể cho phép truy vấn nhưng chọn một mã đơn không có bảo đảm. Điều đó **không phải** tính năng “tự động lấy đơn đầu tiên”.

MySQL có hàm **ANY_VALUE(expr)** để khai báo rằng người viết chấp nhận một giá trị không xác định riêng từ nhóm hoặc nhằm giải quyết kiểm tra tính xác định trong trường hợp cụ thể:

~~~sql
SELECT
    ma_khach_hang,
    ANY_VALUE(ma_don_hang) AS mot_ma_don,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang;
~~~

**ANY_VALUE không chọn dòng nhỏ nhất, lớn nhất, đầu tiên hay mới nhất một cách có cam kết.** Dùng nó chỉ khi thực sự không quan trọng giá trị cụ thể, và nhớ rằng đây là cú pháp/khả năng theo phương ngữ, không phải một giải pháp SQL đa hệ phổ quát.

Một số truy vấn MySQL cũng cho phép biểu thức không nhóm nếu điều kiện WHERE bảo đảm giá trị đơn nhất, nhưng quy tắc này có giới hạn. Không sử dụng ngoại lệ chỉ vì truy vấn tình cờ chạy được trên một bộ dữ liệu nhỏ.

### 8.3. SQL Server và Oracle

Trong SQL Server, nên viết:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COUNT(d.ma_don_hang) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY
    k.ma_khach_hang,
    k.ten_khach_hang;
~~~

Việc **k.ma_khach_hang** là khóa chính không tự cho phép bỏ **k.ten_khach_hang** theo cách mà PostgreSQL hoặc MySQL có thể hỗ trợ.

Oracle Database ở nhiều phiên bản phổ biến cũng yêu cầu biểu thức SELECT không tổng hợp phải phù hợp với GROUP BY; lỗi thường gặp là **not a GROUP BY expression**. Hãy sửa theo ngữ nghĩa, không chỉ tìm cách vô hiệu hóa cơ chế kiểm tra.

### 8.4. SQLite và bare columns

SQLite hỗ trợ chọn cột không nằm trong GROUP BY ở nhiều truy vấn tổng hợp. Ví dụ:

~~~sql
SELECT
    ma_khach_hang,
    ma_don_hang,
    MAX(tong_tien) AS tien_cao_nhat
FROM don_hang
GROUP BY ma_khach_hang;
~~~

SQLite có cách xử lý đặc biệt với **một hàm MIN() hoặc MAX() built-in**: các cột bare có thể được lấy từ một dòng chứa giá trị cực trị tương ứng, nhưng **nếu nhiều dòng cùng cực trị, dòng được chọn vẫn không xác định**; có thêm những giới hạn và ngoại lệ khác. Nếu có nhiều MIN/MAX hoặc các hàm tổng hợp khác, không thể suy ra mọi bare column đến từ một dòng nghiệp vụ duy nhất mong muốn.

Đây là hành vi theo phương ngữ SQLite; không nên mang truy vấn sang PostgreSQL/SQL Server/Oracle rồi kỳ vọng cùng kết quả. Nếu cần “đơn có tổng tiền cao nhất và mã của đúng đơn đó”, dùng hàm cửa sổ hoặc một truy vấn chọn dòng rõ ràng, có quy tắc xử lý hòa.

## 9. Quy tắc chọn cột khác với việc chọn tên bí danh

Bí danh cột trong SELECT:

~~~sql
SELECT
    ma_khach_hang,
    SUM(tong_tien) AS tong_chi
FROM don_hang
GROUP BY ma_khach_hang;
~~~

**tong_chi** là tên đầu ra của SUM, không phải một cột có sẵn trong bảng trước khi GROUP BY.

Ví dụ:

~~~sql
-- Phụ thuộc DBMS, không nên coi là portable.
SELECT
    LOWER(trang_thai) AS trang_thai_thuong,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY trang_thai_thuong;
~~~

Một số DBMS cho phép tham chiếu alias SELECT trong GROUP BY; các hệ khác không. Cách viết ít phụ thuộc hơn:

~~~sql
SELECT
    LOWER(trang_thai) AS trang_thai_thuong,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY LOWER(trang_thai);
~~~

Nếu biểu thức quá dài, đặt nó ở một truy vấn con hoặc CTE:

~~~sql
WITH don_da_chuan_hoa AS (
    SELECT
        ma_don_hang,
        LOWER(trang_thai) AS trang_thai_thuong
    FROM don_hang
)
SELECT
    trang_thai_thuong,
    COUNT(*) AS so_don
FROM don_da_chuan_hoa
GROUP BY trang_thai_thuong;
~~~

Ở SELECT ngoài, **trang_thai_thuong** đã là cột của nguồn CTE, nên việc GROUP BY theo cột này rõ ràng hơn.

### 9.1. GROUP BY theo số thứ tự cột

Một số DBMS cho phép:

~~~sql
SELECT trang_thai, COUNT(*)
FROM don_hang
GROUP BY 1;
~~~

Số **1** ở đây có thể tham chiếu biểu thức SELECT thứ nhất, nhưng không phải mọi DBMS đều hỗ trợ. Hơn nữa, nếu chèn thêm một biểu thức vào trước **trang_thai**, ý nghĩa GROUP BY có thể đổi mà không được nhận ra.

Khi viết truy vấn để học, bảo trì lâu dài hoặc chuyển hệ, ưu tiên **tên cột và biểu thức rõ ràng** hơn việc dựa vào vị trí số.

## 10. GROUP BY theo biểu thức: phải chọn gì?

### 10.1. Nhóm theo một biểu thức đơn giản

Giả sử cần nhóm đơn theo trạng thái chữ thường:

~~~sql
SELECT
    LOWER(trang_thai) AS trang_thai_chuan,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY LOWER(trang_thai);
~~~

Một nhóm được xác định bằng **LOWER(trang_thai)**, không nhất thiết bằng giá trị gốc **trang_thai**.

Không nên viết:

~~~sql
-- Không portable và có thể không xác định:
SELECT
    trang_thai,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY LOWER(trang_thai);
~~~

Nếu bảng chứa cả **'PAID'**, **'Paid'** và **'paid'**, chúng có thể thuộc cùng nhóm sau LOWER nhưng **trang_thai gốc** có nhiều giá trị khác nhau. DBMS không có quy tắc chung để chọn một cách viết làm đại diện.

### 10.2. Nhóm theo nhóm giá trị (bucket)

Yêu cầu: “Chia đơn theo hai mức tổng tiền, dưới 200000 và từ 200000 trở lên”.

~~~sql
SELECT
    CASE
        WHEN tong_tien < 200000 THEN 'DUOI_200K'
        ELSE 'TU_200K_HOAC_THIEU'
    END AS nhom_tien,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY
    CASE
        WHEN tong_tien < 200000 THEN 'DUOI_200K'
        ELSE 'TU_200K_HOAC_THIEU'
    END;
~~~

Truy vấn này hợp lệ về mặt nguyên tắc nhóm theo biểu thức CASE, nhưng **nhãn ELSE đang gộp hai trạng thái khác nhau**: tiền >= 200000 và tiền NULL. Nếu nghiệp vụ cần ba loại rõ ràng:

~~~sql
SELECT
    CASE
        WHEN tong_tien IS NULL THEN 'CHUA_BIET'
        WHEN tong_tien < 200000 THEN 'DUOI_200K'
        ELSE 'TU_200K'
    END AS nhom_tien,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY
    CASE
        WHEN tong_tien IS NULL THEN 'CHUA_BIET'
        WHEN tong_tien < 200000 THEN 'DUOI_200K'
        ELSE 'TU_200K'
    END;
~~~

Có thể dùng CTE để không phải viết lặp biểu thức CASE:

~~~sql
WITH phan_loai AS (
    SELECT
        ma_don_hang,
        CASE
            WHEN tong_tien IS NULL THEN 'CHUA_BIET'
            WHEN tong_tien < 200000 THEN 'DUOI_200K'
            ELSE 'TU_200K'
        END AS nhom_tien
    FROM don_hang
)
SELECT
    nhom_tien,
    COUNT(*) AS so_don
FROM phan_loai
GROUP BY nhom_tien
ORDER BY nhom_tien;
~~~

### 10.3. Khi GROUP BY một biểu thức, không tự do chọn cột gốc

Với bảng giá trị x:

~~~sql
SELECT
    x,
    COUNT(*) AS so_dong
FROM du_lieu
GROUP BY x / 10;
~~~

Nếu các giá trị x = 10, 11, 12 nằm trong cùng nhóm theo phép chia nguyên của DBMS, SELECT x sẽ mơ hồ. Ngay cả khi cách chia/kiểu trả về khác nhau, nhóm theo một **biểu thức từ x** không tự bảo đảm một giá trị x duy nhất.

Cách viết theo đúng ý định là SELECT **biểu thức khóa nhóm**:

~~~sql
SELECT
    x / 10 AS nhom,
    COUNT(*) AS so_dong
FROM du_lieu
GROUP BY x / 10;
~~~

Lưu ý phép **/** với số nguyên có ngữ nghĩa khác nhau giữa DBMS và kiểu dữ liệu. Nếu muốn chia nhóm mười đơn vị chính xác, cần định nghĩa rõ công thức bucket, kiểu số và cách làm tròn/sàn, thay vì chỉ dùng ví dụ chia số một cách mặc định.

## 11. WHERE, GROUP BY, HAVING, SELECT và ORDER BY

Trật tự cú pháp thường gặp:

~~~sql
SELECT
    khoa_nhom,
    HAM_TONG_HOP(cot) AS chi_so
FROM bang
WHERE dieu_kien_hang
GROUP BY khoa_nhom
HAVING dieu_kien_nhom
ORDER BY chi_so DESC;
~~~

Mô hình xử lý logic đơn giản:

~~~text
1. FROM / JOIN : tạo tập dòng nguồn
2. WHERE       : lọc từng dòng nguồn
3. GROUP BY    : phân chia các dòng còn lại thành nhóm
4. HAVING      : lọc từng nhóm
5. SELECT      : tạo cột kết quả của nhóm
6. ORDER BY    : sắp xếp các dòng kết quả
~~~

Đây là **mô hình logic để hiểu ngữ nghĩa**, không phải cam kết DBMS luôn chạy các thao tác vật lý theo thứ tự này. Bộ tối ưu có thể sử dụng chỉ mục, đẩy điều kiện xuống dưới hoặc chọn kế hoạch song song khác.

### 11.1. WHERE lọc dòng trước khi nhóm

Yêu cầu: “Đếm số đơn **PAID** theo khách”.

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don_paid
FROM don_hang
WHERE trang_thai = 'PAID'
GROUP BY ma_khach_hang
ORDER BY ma_khach_hang;
~~~

Theo dữ liệu mẫu, khách 1 có **2** đơn PAID, khách 2 có **2** đơn PAID, khách 3 có **1** đơn PAID. Dòng CANCELLED có mã khách NULL bị WHERE loại.

### 11.2. HAVING lọc nhóm sau khi tổng hợp

Yêu cầu: “Chỉ lấy khách có **ít nhất hai đơn PAID**”.

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don_paid
FROM don_hang
WHERE trang_thai = 'PAID'
GROUP BY ma_khach_hang
HAVING COUNT(*) >= 2
ORDER BY ma_khach_hang;
~~~

Kết quả:

| ma_khach_hang | so_don_paid |
|---:|---:|
| 1 | 2 |
| 2 | 2 |

Không thể đặt **COUNT(*) >= 2** trực tiếp trong WHERE của cùng query block vì WHERE diễn ra trước bước tạo nhóm về mặt logic.

### 11.3. HAVING cũng tuân thủ quy tắc chọn cột

~~~sql
-- Thường không hợp lệ: ngay_dat không xác định trên cả nhóm.
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang
HAVING ngay_dat >= DATE '2026-02-01';
~~~

Ngoài khác biệt cú pháp literal **DATE** giữa DBMS, việc dùng **ngay_dat** ở HAVING là vấn đề chính: mỗi nhóm khách có thể có nhiều ngày. Điều kiện “ngày của nhóm >= ...” chưa được xác định.

Nếu ý định là **chỉ tính các đơn từ 01/02/2026 trở đi**, đặt điều kiện ở WHERE:

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang
WHERE ngay_dat >= ?
GROUP BY ma_khach_hang;
~~~

Nếu ý định là **chỉ chọn các khách có ngày đặt đơn gần nhất từ mốc đó trở đi**, dùng MAX:

~~~sql
SELECT
    ma_khach_hang,
    MAX(ngay_dat) AS ngay_gan_nhat
FROM don_hang
GROUP BY ma_khach_hang
HAVING MAX(ngay_dat) >= ?;
~~~

Hai truy vấn giải quyết **hai câu hỏi nghiệp vụ khác nhau**.

### 11.4. ORDER BY có thể dùng alias đầu ra

~~~sql
SELECT
    ma_khach_hang,
    SUM(tong_tien) AS tong_chi
FROM don_hang
GROUP BY ma_khach_hang
ORDER BY tong_chi DESC, ma_khach_hang;
~~~

Nhiều DBMS cho dùng bí danh **tong_chi** ở ORDER BY. Nhưng ORDER BY **không biến cột không nhóm thành hợp lệ**, và cũng không chọn “dòng đầu tiên” của mỗi nhóm.

Ví dụ sau vẫn không nên sử dụng:

~~~sql
-- Sai ngữ nghĩa dù có ORDER BY.
SELECT ma_khach_hang, ma_don_hang, COUNT(*)
FROM don_hang
GROUP BY ma_khach_hang
ORDER BY ma_don_hang DESC;
~~~

Nếu DBMS cho chạy, ORDER BY chỉ sắp xếp các **dòng kết quả sau nhóm** theo giá trị đã được chọn, không bảo đảm ma_don_hang lấy từ đơn lớn nhất trong mỗi nhóm.

## 12. NULL trong khóa nhóm và trong phép tổng hợp

### 12.1. GROUP BY gom các khóa NULL vào một nhóm

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Các dòng có ma_khach_hang NULL thuộc **một nhóm NULL**. Điều này có thể gây bất ngờ vì phép so sánh thông thường **NULL = NULL** cho UNKNOWN, nhưng GROUP BY sử dụng quy tắc phân nhóm riêng, coi các giá trị NULL thuộc cùng một nhóm.

Nếu dữ liệu có nhiều đơn chưa xác định khách, tất cả chúng có thể nằm trong cùng nhóm ma_khach_hang NULL; không có nghĩa chúng thật sự thuộc cùng một người.

Nếu không muốn nhóm “khách chưa xác định” xuất hiện:

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang
WHERE ma_khach_hang IS NOT NULL
GROUP BY ma_khach_hang;
~~~

Nếu cần hiển thị nhãn dễ đọc, có thể dùng CASE hoặc COALESCE ở query block ngoài để tránh nhầm kiểu dữ liệu:

~~~sql
WITH thong_ke AS (
    SELECT ma_khach_hang, COUNT(*) AS so_don
    FROM don_hang
    GROUP BY ma_khach_hang
)
SELECT
    CASE
        WHEN ma_khach_hang IS NULL THEN 'CHUA_XAC_DINH'
        ELSE 'DA_CO_MA'
    END AS tinh_trang_ma,
    ma_khach_hang,
    so_don
FROM thong_ke;
~~~

### 12.2. COUNT(*) khác COUNT(cot)

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_dong,
    COUNT(tong_tien) AS so_dong_co_tien,
    SUM(tong_tien) AS tong_chi
FROM don_hang
GROUP BY ma_khach_hang;
~~~

- **COUNT(*)** đếm số dòng trong nhóm.
- **COUNT(tong_tien)** chỉ đếm những dòng mà tong_tien không NULL.
- **SUM(tong_tien)** bỏ qua giá trị NULL.
- Nếu mọi giá trị tong_tien trong nhóm đều NULL, SUM thường trả NULL, không phải 0.

Nên thêm trường hợp có tong_tien NULL vào dữ liệu thử nếu yêu cầu phân biệt “không có số tiền” với “tổng bằng 0”.

### 12.3. COALESCE trong GROUP BY có thể gộp các nhóm ngoài ý muốn

Giả sử cột **ma_khach_hang** là số và người viết dùng:

~~~sql
SELECT
    COALESCE(ma_khach_hang, 0) AS ma_hien_thi,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY COALESCE(ma_khach_hang, 0);
~~~

Nếu giá trị **0** cũng là một mã khách hợp lệ, nhóm có mã 0 và nhóm NULL sẽ **bị nhập làm một**. Do đó, không chọn giá trị thay thế khi chưa chắc chắn nó không xuất hiện trong dữ liệu hoặc khi chưa thật sự muốn gộp.

## 13. Tổng hợp có điều kiện: chọn cột không đồng nghĩa thêm khóa nhóm

Đôi khi báo cáo cần **một dòng cho mỗi khách** nhưng có nhiều chỉ số theo trạng thái. Không nên thêm **trang_thai** vào GROUP BY chỉ để đếm từng trạng thái, vì điều đó làm mỗi khách có nhiều dòng.

Dùng **tổng hợp có điều kiện**:

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don,
    SUM(
        CASE
            WHEN trang_thai = 'PAID' THEN 1
            ELSE 0
        END
    ) AS so_don_paid,
    SUM(
        CASE
            WHEN trang_thai = 'PENDING' THEN 1
            ELSE 0
        END
    ) AS so_don_pending,
    SUM(
        CASE
            WHEN trang_thai = 'PAID' THEN tong_tien
            ELSE 0
        END
    ) AS tien_paid
FROM don_hang
WHERE ma_khach_hang IS NOT NULL
GROUP BY ma_khach_hang
ORDER BY ma_khach_hang;
~~~

Kết quả:

| ma_khach_hang | so_don | so_don_paid | so_don_pending | tien_paid |
|---:|---:|---:|---:|---:|
| 1 | 2 | 2 | 0 | 350000 |
| 2 | 3 | 2 | 1 | 550000 |
| 3 | 1 | 1 | 0 | 120000 |

Ở đây, **trang_thai** không phải cột kết quả chi tiết; nó được sử dụng bên trong CASE để xác định giá trị tổng hợp. Mỗi biểu thức SUM vẫn trả một giá trị cho cả nhóm khách.

### 13.1. COUNT(CASE WHEN ... THEN ... END)

Một cách khác:

~~~sql
SELECT
    ma_khach_hang,
    COUNT(
        CASE
            WHEN trang_thai = 'PAID' THEN 1
        END
    ) AS so_don_paid
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Khi điều kiện không đúng, CASE không có ELSE trả NULL; COUNT(expr) không đếm NULL. Vì vậy, COUNT(CASE WHEN ... THEN 1 END) đếm những dòng thỏa điều kiện, trong cách viết thông thường.

Phải phân biệt với:

~~~sql
COUNT(
    CASE WHEN trang_thai = 'PAID' THEN 1 ELSE 0 END
)
~~~

Với ELSE 0, **mọi dòng đều có giá trị không NULL**, nên COUNT đếm toàn bộ dòng, không chỉ PAID.

### 13.2. FILTER ở DBMS hỗ trợ

Một số hệ, chẳng hạn PostgreSQL, hỗ trợ cú pháp:

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) FILTER (WHERE trang_thai = 'PAID') AS so_don_paid
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Đây là cách thể hiện rõ ràng, nhưng không nên mặc định mọi DBMS hỗ trợ cùng cú pháp. **SUM(CASE...)** và **COUNT(CASE...)** thường là lựa chọn dễ chuyển hệ hơn.

## 14. JOIN và hiện tượng nhân dòng trước GROUP BY

Một trong các lỗi tổng hợp nguy hiểm nhất là **JOIN làm tăng số dòng đầu vào** mà người viết không nhận ra.

Giả sử có:

**don_hang**

| ma_don_hang | ma_khach_hang | tong_tien |
|---:|---:|---:|
| 201 | 1 | 100000 |
| 202 | 1 | 200000 |

**chi_tiet_don_hang**

| ma_don_hang | ma_san_pham | so_luong |
|---:|---:|---:|
| 201 | 10 | 1 |
| 201 | 11 | 2 |
| 202 | 12 | 1 |

Một đơn có thể có **nhiều dòng chi tiết**.

Nếu JOIN rồi cộng tổng tiền đơn:

~~~sql
-- Sai ý nghĩa tổng tiền đơn nếu một đơn có nhiều dòng chi tiết.
SELECT
    d.ma_khach_hang,
    SUM(d.tong_tien) AS tong_chi
FROM don_hang d
JOIN chi_tiet_don_hang ct
    ON ct.ma_don_hang = d.ma_don_hang
GROUP BY d.ma_khach_hang;
~~~

Sau JOIN, đơn 201 xuất hiện **hai lần**, nên phép SUM cộng:

~~~text
100000 + 100000 + 200000 = 400000
~~~

Nhưng tổng giá trị của **hai đơn gốc** là:

~~~text
100000 + 200000 = 300000
~~~

Điểm này **không được giải quyết** bằng việc thêm d.tong_tien vào GROUP BY hay dùng SUM(DISTINCT d.tong_tien) một cách tùy tiện. SUM(DISTINCT) có thể bỏ một giá trị hợp lệ nếu hai đơn khác nhau trùng tổng tiền.

### 14.1. Chọn đúng nguồn hạt dữ liệu cần tổng hợp

Nếu yêu cầu chỉ tính tổng tiền từ bảng đơn hàng, không cần JOIN bảng chi tiết:

~~~sql
SELECT
    ma_khach_hang,
    SUM(tong_tien) AS tong_chi
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Nếu cần kết hợp nhiều thông tin tổng hợp từ hai bảng, tổng hợp từng nguồn **ở đúng mức chi tiết** rồi JOIN các kết quả:

~~~sql
WITH tong_theo_khach AS (
    SELECT
        ma_khach_hang,
        COUNT(*) AS so_don,
        SUM(tong_tien) AS tong_chi
    FROM don_hang
    GROUP BY ma_khach_hang
),
so_luong_theo_khach AS (
    SELECT
        d.ma_khach_hang,
        SUM(ct.so_luong) AS tong_so_luong
    FROM don_hang d
    JOIN chi_tiet_don_hang ct
        ON ct.ma_don_hang = d.ma_don_hang
    GROUP BY d.ma_khach_hang
)
SELECT
    t.ma_khach_hang,
    t.so_don,
    t.tong_chi,
    COALESCE(s.tong_so_luong, 0) AS tong_so_luong
FROM tong_theo_khach t
LEFT JOIN so_luong_theo_khach s
    ON s.ma_khach_hang = t.ma_khach_hang;
~~~

Với ví dụ hai đơn của khách 1, kết quả mong đợi **so_don = 2**, **tong_chi = 300000**, **tong_so_luong = 4**.

**Chú ý NULL ở khóa JOIN:** ví dụ trên giả định mã khách được xác định. Nếu cả hai phía có mã khách NULL, điều kiện **s.ma_khach_hang = t.ma_khach_hang** không tự coi hai NULL là bằng nhau. Khi cần ghép cả nhóm NULL, phải phát biểu quy tắc nghiệp vụ và dùng điều kiện phù hợp.

### 14.2. COUNT(DISTINCT) có ích nhưng không chữa mọi lỗi JOIN

Trong ví dụ có JOIN, nếu chỉ cần **số đơn khác nhau**:

~~~sql
SELECT
    d.ma_khach_hang,
    COUNT(DISTINCT d.ma_don_hang) AS so_don
FROM don_hang d
JOIN chi_tiet_don_hang ct
    ON ct.ma_don_hang = d.ma_don_hang
GROUP BY d.ma_khach_hang;
~~~

COUNT(DISTINCT d.ma_don_hang) cho số đơn phân biệt **có ít nhất một dòng chi tiết**. Nó có thể phù hợp nếu ý định đó chính xác; tuy nhiên, đơn không có chi tiết sẽ bị INNER JOIN loại, nên tổng số đơn toàn hệ vẫn có thể bị thiếu.

**Quy tắc:** trước khi tổng hợp sau JOIN, kiểm tra số dòng được nhân lên và mối quan hệ một–một, một–nhiều, nhiều–nhiều.

## 15. Chọn cột từ bảng khác khi nhóm theo khóa khách

Giả sử có thêm bảng:

~~~text
khach_hang(
    ma_khach_hang PRIMARY KEY,
    ten_khach_hang,
    thanh_pho
)
~~~

Yêu cầu: “Mỗi khách một dòng, hiển thị tên, thành phố, số đơn và tổng tiền”.

Hai cách:

### 15.1. GROUP BY tất cả cột không tổng hợp cần hiển thị

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    k.thanh_pho,
    COUNT(d.ma_don_hang) AS so_don,
    COALESCE(SUM(d.tong_tien), 0) AS tong_chi
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY
    k.ma_khach_hang,
    k.ten_khach_hang,
    k.thanh_pho
ORDER BY k.ma_khach_hang;
~~~

Cách này thường dễ chuyển giữa các DBMS và làm rõ mọi cột hiển thị ở cấp khách.

**Vì sao COUNT(d.ma_don_hang), không phải COUNT(*)?**

Với LEFT JOIN, khách chưa có đơn vẫn có thể tạo **một dòng kết quả được đệm NULL phía phải**. COUNT(*) khi đó trả 1, không phải 0. Vì ma_don_hang là khóa chính không NULL ở bảng đơn, COUNT(d.ma_don_hang) chỉ đếm dòng đơn thật đã khớp.

### 15.2. Tổng hợp bảng đơn trước, rồi JOIN bảng khách

~~~sql
WITH thong_ke_don AS (
    SELECT
        ma_khach_hang,
        COUNT(*) AS so_don,
        SUM(tong_tien) AS tong_chi
    FROM don_hang
    GROUP BY ma_khach_hang
)
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    k.thanh_pho,
    COALESCE(t.so_don, 0) AS so_don,
    COALESCE(t.tong_chi, 0) AS tong_chi
FROM khach_hang k
LEFT JOIN thong_ke_don t
    ON t.ma_khach_hang = k.ma_khach_hang
ORDER BY k.ma_khach_hang;
~~~

Ở query block **ngoài**, không còn GROUP BY. Các cột tên và thành phố là cột bình thường của bảng khach_hang, còn các chỉ số so_don/tong_chi đã được tính ở CTE.

Cách này có lợi về **độ rõ mức chi tiết** khi bảng khách chứa nhiều cột mô tả. Tuy vậy, nếu dữ liệu thực tế có sai lệch khóa hoặc nhiều bảng JOIN, vẫn cần phân tích quan hệ và NULL. Bộ tối ưu cũng có thể lập kế hoạch thực thi khác nhau; không mặc định CTE luôn nhanh hơn.

## 16. Khi cần “một dòng đại diện của nhóm”, GROUP BY không đủ

Một yêu cầu rất phổ biến là:

> “Với mỗi khách hàng, lấy **đơn mới nhất** và hiển thị cả **mã đơn, ngày đặt và tổng tiền của đúng đơn đó**.”

Nhiều người thử:

~~~sql
-- Không đúng: MAX(ngay_dat) không chỉ ra ma_don_hang đi kèm.
SELECT
    ma_khach_hang,
    ma_don_hang,
    MAX(ngay_dat) AS ngay_moi_nhat,
    tong_tien
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Theo quy tắc nghiêm ngặt, ma_don_hang và tong_tien không hợp lệ vì không được nhóm hay tổng hợp. Trong các DBMS cho phép, chúng có thể không thuộc đúng dòng có MAX(ngay_dat).

### 16.1. Sai lầm: MAX từng cột có thể “ghép nhầm” hai dòng

~~~sql
SELECT
    ma_khach_hang,
    MAX(ma_don_hang) AS ma_don_lon_nhat,
    MAX(ngay_dat) AS ngay_moi_nhat,
    MAX(tong_tien) AS tien_cao_nhat
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Truy vấn này hợp lệ nhưng các giá trị MAX được tính **độc lập**. Mã đơn lớn nhất, ngày gần nhất và tiền cao nhất có thể thuộc **ba đơn khác nhau**. Một dòng kết quả tổng hợp không có nghĩa là nó sao chép thông tin từ một dòng chi tiết duy nhất.

Với khách 2 ở bảng mẫu:

- **ma_don_hang lớn nhất = 106**.
- **ngay_dat gần nhất = 2026-02-10** (đơn 106).
- **tong_tien cao nhất = 300000** (đơn 104).

Nếu hiển thị ba giá trị này như một “đơn mới nhất có giá 300000” thì sai: đơn 106 có tổng tiền **250000**.

### 16.2. Dùng ROW_NUMBER để chọn đúng một dòng

Một cách thường dùng trên DBMS hỗ trợ hàm cửa sổ:

~~~sql
WITH don_xep_hang AS (
    SELECT
        d.ma_don_hang,
        d.ma_khach_hang,
        d.ngay_dat,
        d.tong_tien,
        ROW_NUMBER() OVER (
            PARTITION BY d.ma_khach_hang
            ORDER BY d.ngay_dat DESC, d.ma_don_hang DESC
        ) AS stt
    FROM don_hang d
)
SELECT
    ma_khach_hang,
    ma_don_hang,
    ngay_dat,
    tong_tien
FROM don_xep_hang
WHERE stt = 1
ORDER BY ma_khach_hang;
~~~

Giải thích:

- **PARTITION BY ma_khach_hang** phân vùng các dòng theo khách; không gộp thành một dòng ở bước này.
- **ORDER BY ngay_dat DESC** chọn ngày gần nhất trước.
- **ma_don_hang DESC** là khóa phụ để quyết định khi nhiều đơn có cùng ngày, giả sử mã đơn duy nhất.
- **ROW_NUMBER()** đánh số từng dòng trong mỗi phân vùng.
- Query block ngoài lọc **stt = 1**, lấy đúng một dòng cho mỗi khách.

Với khách 2, dòng được chọn là **đơn 106, ngày 2026-02-10, tổng tiền 250000**.

**Chú ý NULL:** mặc định sắp xếp NULL trong ORDER BY khác nhau theo DBMS. Nếu ngay_dat có thể NULL và nghiệp vụ muốn ngày không NULL ưu tiên trước, hãy quy định một khóa sắp xếp tường minh hoặc xử lý dữ liệu trước.

### 16.3. Trường hợp đồng hạng (ties)

Nếu hai đơn có cùng **ngay_dat** và người dùng yêu cầu lấy **tất cả đơn cùng ngày mới nhất**, ROW_NUMBER với khóa phụ chỉ trả một dòng. Có thể dùng **RANK()** hoặc **DENSE_RANK()** theo ngày để lấy tất cả các dòng hạng 1:

~~~sql
WITH don_xep_hang AS (
    SELECT
        d.ma_don_hang,
        d.ma_khach_hang,
        d.ngay_dat,
        d.tong_tien,
        DENSE_RANK() OVER (
            PARTITION BY d.ma_khach_hang
            ORDER BY d.ngay_dat DESC
        ) AS hang_ngay
    FROM don_hang d
)
SELECT
    ma_khach_hang,
    ma_don_hang,
    ngay_dat,
    tong_tien
FROM don_xep_hang
WHERE hang_ngay = 1;
~~~

Nhưng cần xử lý cách sắp xếp NULL theo DBMS; trường hợp một nhóm chỉ có ngày NULL đòi hỏi chính sách riêng. Nếu nghiệp vụ muốn một đơn duy nhất, hãy dùng ROW_NUMBER với một **tiêu chí phụ ổn định**.

### 16.4. Có thể JOIN ngược vào MAX, nhưng phải xử lý hòa

~~~sql
WITH ngay_gan_nhat AS (
    SELECT
        ma_khach_hang,
        MAX(ngay_dat) AS ngay_moi_nhat
    FROM don_hang
    WHERE ma_khach_hang IS NOT NULL
    GROUP BY ma_khach_hang
)
SELECT
    d.ma_khach_hang,
    d.ma_don_hang,
    d.ngay_dat,
    d.tong_tien
FROM don_hang d
JOIN ngay_gan_nhat g
    ON g.ma_khach_hang = d.ma_khach_hang
   AND g.ngay_moi_nhat = d.ngay_dat;
~~~

Cách này trả tất cả đơn cùng ngày cực đại của từng khách; nếu hai đơn cùng ngày mới nhất, kết quả có thể có **hai dòng cho một khách**. Đây không phải lỗi nếu yêu cầu là “tất cả đơn mới nhất đồng hạng”, nhưng không đáp ứng yêu cầu “đúng một đơn mỗi khách”.

## 17. Hàm cửa sổ không thay thế trực tiếp GROUP BY

Hàm cửa sổ (window function) có thể tính chỉ số cho từng nhóm **mà vẫn giữ các dòng chi tiết**:

~~~sql
SELECT
    d.ma_don_hang,
    d.ma_khach_hang,
    d.tong_tien,
    COUNT(*) OVER (
        PARTITION BY d.ma_khach_hang
    ) AS so_don_cua_khach,
    SUM(d.tong_tien) OVER (
        PARTITION BY d.ma_khach_hang
    ) AS tong_chi_cua_khach
FROM don_hang d
ORDER BY d.ma_khach_hang, d.ma_don_hang;
~~~

Khách 1 xuất hiện **hai dòng** (đơn 101, 102), và trên mỗi dòng đều có **so_don_cua_khach = 2**, **tong_chi_cua_khach = 350000**.

So sánh:

| Công cụ | Số dòng đầu ra | Trường hợp phù hợp |
|---|---|---|
| **GROUP BY** | Thường một dòng mỗi nhóm | Báo cáo tổng hợp |
| **COUNT/SUM OVER(PARTITION BY ...)** | Vẫn giữ các dòng chi tiết | Chi tiết kèm chỉ số nhóm |
| **ROW_NUMBER OVER(...) + lọc ngoài** | Chọn dòng cụ thể mỗi nhóm | Đơn mới nhất, hàng đại diện |
| **JOIN từ tổng hợp vào bảng chi tiết** | Theo mức chi tiết sau JOIN | Bổ sung chỉ số tổng hợp cho từng dòng |

Không nên đưa hàm cửa sổ trực tiếp vào WHERE cùng cấp rồi giả định nó chạy như phép lọc bình thường. Nhiều DBMS yêu cầu đặt tính toán cửa sổ trong CTE/bảng dẫn xuất và lọc ở query block ngoài; một số hệ hỗ trợ cú pháp chuyên biệt **QUALIFY**.

## 18. GROUP BY không có SELECT khóa nhóm

Đôi khi yêu cầu chỉ là: “Có bao nhiêu trạng thái khác nhau?” hoặc “Mỗi nhóm có số hàng như thế nào?” Có thể không cần hiển thị tất cả cột nhóm, nhưng cần hiểu hệ quả.

Ví dụ:

~~~sql
SELECT COUNT(*) AS so_don
FROM don_hang
GROUP BY trang_thai;
~~~

Câu này trả **một dòng cho mỗi trạng thái** nhưng không hiển thị tên trạng thái. Với bảng mẫu, có thể thấy các số như 5, 1, 1 mà không biết số nào ứng với nhóm nào; ngoài ra, thứ tự các dòng không được bảo đảm nếu thiếu ORDER BY.

Nếu cần **tổng số trạng thái**, câu hỏi khác:

~~~sql
SELECT COUNT(DISTINCT trang_thai) AS so_trang_thai
FROM don_hang;
~~~

Với bảng mẫu có PAID, PENDING và CANCELLED, kết quả là **3**. COUNT(DISTINCT cot) thường bỏ qua giá trị NULL của cot.

**COUNT(DISTINCT trang_thai)** không phải cùng ngữ nghĩa với **COUNT(*) GROUP BY trang_thai**. Câu thứ nhất trả một con số; câu thứ hai trả một dòng cho mỗi nhóm.

## 19. Không có GROUP BY nhưng vẫn có hàm tổng hợp

Một truy vấn chỉ có hàm tổng hợp nhưng không có GROUP BY có thể tổng hợp **toàn bộ tập đầu vào** thành một kết quả:

~~~sql
SELECT
    COUNT(*) AS so_don,
    SUM(tong_tien) AS tong_tien
FROM don_hang;
~~~

Kết quả là **một dòng**, ví dụ so_don = 7 với tập dữ liệu bài học.

Nhưng:

~~~sql
-- Thường không hợp lệ: trang_thai không được xác định duy nhất.
SELECT
    trang_thai,
    COUNT(*) AS so_don
FROM don_hang;
~~~

Vì COUNT(*) tổng hợp mọi dòng thành một kết quả, còn trang_thai có nhiều giá trị. Nếu muốn một dòng cho từng trạng thái, phải thêm **GROUP BY trang_thai**.

### 19.1. Tập đầu vào rỗng

Nếu không có dòng nào thỏa WHERE:

~~~sql
SELECT COUNT(*) AS so_don
FROM don_hang
WHERE trang_thai = 'KHONG_TON_TAI';
~~~

Truy vấn không GROUP BY thường vẫn trả **một dòng** với **COUNT(*) = 0**.

Trong khi:

~~~sql
SELECT
    trang_thai,
    COUNT(*) AS so_don
FROM don_hang
WHERE trang_thai = 'KHONG_TON_TAI'
GROUP BY trang_thai;
~~~

không tạo nhóm nào, nên trả **0 dòng**.

Đây là khác biệt cần nhớ khi ứng dụng đang chờ “một dòng số 0” nhưng truy vấn có GROUP BY lại trả một tập rỗng.

### 19.2. Tổng hợp trên tập rỗng và NULL

Thông thường:

~~~sql
SELECT
    COUNT(*) AS so_don,
    SUM(tong_tien) AS tong_tien
FROM don_hang
WHERE trang_thai = 'KHONG_TON_TAI';
~~~

cho **COUNT(*) = 0**, còn **SUM(tong_tien) = NULL**. Nếu muốn màn hình hiển thị 0, có thể dùng **COALESCE(SUM(tong_tien), 0)** nhưng phải xác định đó là cách hiển thị nghiệp vụ.

## 20. DISTINCT không thay thế quy tắc GROUP BY

**DISTINCT** loại các dòng trùng nhau trong đầu ra SELECT, còn **GROUP BY** tạo nhóm để tổng hợp.

Ví dụ:

~~~sql
SELECT DISTINCT ma_khach_hang
FROM don_hang;
~~~

Trả danh sách mã khách phân biệt (bao gồm một giá trị NULL nếu có), không tính số đơn.

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Trả số đơn cho từng mã khách.

Nếu thêm DISTINCT vào một truy vấn GROUP BY có cột không xác định:

~~~sql
-- DISTINCT không giải quyết ma_don_hang mơ hồ.
SELECT DISTINCT
    ma_khach_hang,
    ma_don_hang,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang;
~~~

truy vấn vẫn không có quy tắc xác định chọn mã đơn nào trong mỗi nhóm. DISTINCT chỉ làm việc sau khi các biểu thức SELECT đã được xác định, nên không chữa được vấn đề lựa chọn giá trị bên trong nhóm.

### 20.1. PostgreSQL DISTINCT ON là tính năng riêng

PostgreSQL hỗ trợ **DISTINCT ON (...)** để chọn một dòng cho mỗi tập giá trị theo ORDER BY:

~~~sql
SELECT DISTINCT ON (ma_khach_hang)
    ma_khach_hang,
    ma_don_hang,
    ngay_dat,
    tong_tien
FROM don_hang
ORDER BY ma_khach_hang, ngay_dat DESC, ma_don_hang DESC;
~~~

Đây là tính năng đặc thù PostgreSQL và cần ORDER BY phù hợp để có dòng đại diện xác định. Không nên nhầm **DISTINCT ON** với **DISTINCT** chuẩn hoặc GROUP BY; để viết đa DBMS, dùng ROW_NUMBER khi được hỗ trợ.

## 21. Nhóm đa cấp: ROLLUP, CUBE và GROUPING SETS

Ngoài GROUP BY thông thường, SQL còn có các công cụ tạo **nhóm tổng phụ (subtotal)** và **nhóm tổng toàn bộ (grand total)**:

~~~sql
SELECT
    ma_khach_hang,
    trang_thai,
    SUM(tong_tien) AS tong_tien
FROM don_hang
GROUP BY ROLLUP (ma_khach_hang, trang_thai);
~~~

Cú pháp và mức hỗ trợ khác nhau giữa DBMS, phiên bản. Trong hệ hỗ trợ ROLLUP, kết quả có thể chứa:

- Nhóm chi tiết theo **(ma_khach_hang, trang_thai)**.
- Nhóm tổng phụ theo **ma_khach_hang**.
- Nhóm tổng toàn bộ.

Các dòng tổng phụ thường dùng NULL ở một số cột khóa để biểu diễn mức tổng hợp, **nhưng NULL này có thể là NULL do ROLLUP tạo**, không phải giá trị NULL thật trong dữ liệu đầu vào.

### 21.1. Cần phân biệt NULL thật với NULL do tổng phụ

Khi sử dụng ROLLUP hoặc GROUPING SETS, nhiều DBMS có hàm **GROUPING(cot)** hoặc cơ chế tương đương để nhận biết một cột đang bị gộp vào mức tổng phụ hay đang có giá trị NULL thật.

Ví dụ theo cú pháp SQL phổ biến ở hệ có hỗ trợ:

~~~sql
SELECT
    ma_khach_hang,
    GROUPING(ma_khach_hang) AS la_nhom_tong,
    SUM(tong_tien) AS tong_tien
FROM don_hang
GROUP BY ROLLUP (ma_khach_hang);
~~~

Về ý nghĩa, **la_nhom_tong** giúp phân biệt dòng grand total với dòng nhóm có ma_khach_hang NULL thật. Cách đặt alias, thứ tự nhóm và hàm GROUPING cần kiểm tra trên DBMS cụ thể.

**Điểm liên hệ với chủ đề bài học:** ngay cả khi GROUP BY mở rộng tạo nhiều mức tổng hợp, cột SELECT vẫn phải có ý nghĩa rõ ở từng mức. Không thể tùy tiện chọn một cột chi tiết rồi coi nó thuộc về nhóm tổng.

## 22. Ảnh hưởng của dữ liệu sai và ràng buộc đến quy tắc chọn cột

### 22.1. Tên khách hàng trùng nhau không có nghĩa cùng khách

Giả sử:

| ma_khach_hang | ten_khach_hang |
|---:|---|
| 1 | An |
| 2 | An |
| 3 | Bình |

Nếu nhóm theo **ten_khach_hang**:

~~~sql
SELECT
    ten_khach_hang,
    COUNT(*) AS so_khach
FROM khach_hang
GROUP BY ten_khach_hang;
~~~

hai khách tên An bị nhóm chung. Nếu mục tiêu là đếm **số người có cùng tên**, điều này đúng; nếu mục tiêu là báo cáo **mỗi khách một dòng**, nhóm theo tên là sai. Phải nhóm theo mã định danh phù hợp.

### 22.2. Một cột “tình cờ giống nhau” không phải phụ thuộc hàm

Giả sử trong dữ liệu hiện tại, tất cả đơn của một khách có cùng trạng thái PAID. Truy vấn:

~~~sql
SELECT
    ma_khach_hang,
    trang_thai,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang;
~~~

vẫn không được xem là an toàn chỉ vì một vài nhóm tình cờ chứa cùng một trang_thai. Chỉ cần một đơn PENDING mới được thêm vào, giả định trở nên sai.

**Phụ thuộc hàm có ý nghĩa bền vững** phải đến từ quy tắc dữ liệu, khóa và ràng buộc được xác định, không phải chỉ từ một ảnh chụp dữ liệu nhất thời.

### 22.3. Trạng thái thay đổi theo thời gian

Nếu bảng lưu lịch sử trạng thái (mỗi đơn có nhiều bản ghi trạng thái theo thời gian), việc GROUP BY ma_don_hang rồi chọn trang_thai không tổng hợp cũng mơ hồ. Muốn trạng thái mới nhất, cần xác định **dòng lịch sử mới nhất** trước; không thể chỉ chọn MAX(ngay_cap_nhat) rồi tùy ý lấy trang_thai.

Ví dụ thiết kế:

~~~sql
WITH trang_thai_xep_hang AS (
    SELECT
        ma_don_hang,
        trang_thai,
        ngay_cap_nhat,
        ROW_NUMBER() OVER (
            PARTITION BY ma_don_hang
            ORDER BY ngay_cap_nhat DESC, ma_lich_su DESC
        ) AS stt
    FROM lich_su_trang_thai
)
SELECT
    ma_don_hang,
    trang_thai
FROM trang_thai_xep_hang
WHERE stt = 1;
~~~

Giả định bảng **lich_su_trang_thai** có khóa duy nhất **ma_lich_su**, dùng để phá hòa khi nhiều dòng có cùng thời điểm cập nhật. Nếu không có quy tắc phá hòa, “mới nhất” có thể chưa đủ để xác định đúng một dòng.

## 23. Những lỗi thường gặp và cách sửa

| Lỗi hoặc ngộ nhận | Hệ quả | Cách xử lý |
|---|---|---|
| Chọn cột chi tiết không nhóm, không tổng hợp | Lỗi SQL hoặc giá trị không xác định | Xác định ý định: thêm khóa nhóm, dùng tổng hợp hoặc chọn dòng |
| Thêm mọi cột SELECT vào GROUP BY theo máy móc | Biến một dòng/khách thành nhiều dòng/khách | Xác định mức chi tiết trước khi sửa |
| Dùng MIN/MAX chỉ để “qua lỗi” | Lấy cực trị không có ý nghĩa nghiệp vụ | Chỉ dùng khi thật sự muốn giá trị min/max |
| Dùng MAX(ngay_dat), MAX(tong_tien) và coi là một đơn | Các cực trị có thể ở các dòng khác nhau | Dùng ROW_NUMBER hoặc JOIN theo khóa được chọn |
| Dùng ORDER BY để chọn dòng đầu tiên trong nhóm | ORDER BY cuối không quyết định bare column | Chọn dòng rõ ràng trước khi sắp xếp |
| Dùng DISTINCT để chữa GROUP BY | DISTINCT không giải quyết cột mơ hồ | Sửa mức chi tiết hoặc cách tổng hợp |
| Dựa vào MySQL tắt ONLY_FULL_GROUP_BY | Chọn cột từ dòng không được bảo đảm | Bật kiểm tra chặt, sửa truy vấn |
| Dựa vào SQLite bare columns như chuẩn chung | Sai hoặc không chạy trên DBMS khác | Dùng SQL có ý nghĩa xác định |
| Cho rằng khóa chính một bảng xác định cột ở mọi bảng JOIN | Quan hệ một-nhiều vẫn có nhiều giá trị | Phân tích phụ thuộc hàm từng bảng |
| GROUP BY thêm trạng thái khi muốn một dòng/khách | Mỗi khách xuất hiện nhiều lần | Dùng SUM(CASE...) để tạo chỉ số theo trạng thái |
| COUNT(*) với LEFT JOIN và khách chưa có đơn | Có thể đếm 1 dòng NULL đệm | COUNT(khóa NOT NULL của bảng phải) |
| SUM sau JOIN một-nhiều | Giá trị ở bảng gốc bị nhân | Tổng hợp ở grain phù hợp trước JOIN |
| SUM(DISTINCT tong_tien) để loại dòng JOIN trùng | Có thể gộp hai đơn thật cùng tiền | Dùng khóa nghiệp vụ, không DISTINCT trên giá trị tiền |
| Không xử lý NULL trong khóa nhóm | Nhiều dòng thiếu khóa bị nhóm chung | IS NULL/IS NOT NULL và chính sách dữ liệu |
| Nhóm theo tên thay vì mã khách | Gộp nhiều người trùng tên | Nhóm theo khóa định danh |
| Chọn alias GROUP BY theo giả định mọi DBMS hỗ trợ | Lỗi cú pháp/phân giải tên | Lặp biểu thức hoặc dùng CTE |
| Cố định một tên alias trùng cột thật | GROUP BY/ORDER BY có thể phân giải tên khác | Đặt alias rõ, tránh tên trùng |
| Đếm số nhóm bằng COUNT(*) không GROUP BY | Đếm dòng, không đếm nhóm | COUNT(DISTINCT ...) theo yêu cầu |
| Tin rằng truy vấn có GROUP BY luôn trả 1 dòng khi không có dữ liệu | Truy vấn có khóa nhóm có thể trả 0 dòng | Phân biệt aggregate không GROUP BY và GROUP BY có khóa |

## 24. Cách tự phân tích một truy vấn GROUP BY

Khi gặp truy vấn có nhiều SELECT, JOIN và GROUP BY, làm theo trình tự sau:

### Bước 1: Viết yêu cầu kết quả bằng một câu

Ví dụ: “Mỗi khách hàng một dòng, gồm mã, tên, số đơn PAID và tổng tiền PAID”.

Cụm **“mỗi khách một dòng”** quyết định mức chi tiết của kết quả. Mọi cột SELECT phải có một giá trị duy nhất hoặc một phép tổng hợp phù hợp ở cấp khách.

### Bước 2: Xác định khóa nhóm

Có thể là **k.ma_khach_hang**. Nếu truy vấn cần hiển thị **k.ten_khach_hang** và muốn chuyển hệ rộng rãi, thường đưa cả mã và tên vào GROUP BY hoặc tổng hợp bảng đơn trước rồi JOIN ra tên.

### Bước 3: Phân loại từng biểu thức SELECT

| Biểu thức | Phân loại |
|---|---|
| k.ma_khach_hang | Khóa nhóm |
| k.ten_khach_hang | Cột mô tả khách; cần xử lý đúng quy tắc GROUP BY |
| COUNT(d.ma_don_hang) | Phép tổng hợp |
| SUM(d.tong_tien) | Phép tổng hợp |
| d.ma_don_hang | Cột chi tiết nhiều giá trị; không thể chọn tùy ý |
| MAX(d.ngay_dat) | Phép tổng hợp ngày |
| 'PAID' | Hằng số |

### Bước 4: Kiểm tra nguồn dòng sau FROM/JOIN

- Một khách có thể ghép bao nhiêu đơn?
- Một đơn có thể ghép bao nhiêu dòng chi tiết?
- LEFT JOIN có thể sinh dòng phía phải NULL không?
- Có cần lọc trạng thái trong ON hoặc WHERE để giữ đủ khách không?
- Có dòng trùng vì dữ liệu hoặc do quan hệ một-nhiều không?

### Bước 5: Kiểm tra điều kiện lọc trước và sau nhóm

- **WHERE** lọc từng dòng đầu vào, ví dụ chỉ đơn PAID.
- **HAVING** lọc nhóm, ví dụ khách có từ hai đơn PAID trở lên.
- Nếu lọc nhóm có SUM NULL, kết quả UNKNOWN cần được xử lý theo nghiệp vụ.

### Bước 6: Kiểm tra đầu ra qua dữ liệu có nhiều dòng mỗi nhóm

Đừng chỉ thử một khách có một đơn. Ít nhất cần:

- Khách có **0 đơn**.
- Khách có **1 đơn**.
- Khách có **2 hoặc nhiều đơn**.
- Khách có các trạng thái đơn **khác nhau**.
- Hai đơn cùng ngày hoặc cùng tiền để phát hiện trường hợp đồng hạng.
- Một dòng có cột tổng hợp NULL.
- Hai khách trùng tên nhưng khác mã.
- Một đơn có nhiều chi tiết để phát hiện nhân dòng sau JOIN.

### Bước 7: Đối chiếu khả chuyển DBMS

Nếu câu SQL dựa vào ngoại lệ phụ thuộc hàm, alias GROUP BY, ANY_VALUE, bare columns, DISTINCT ON hoặc cú pháp tổng hợp mở rộng, cần xác định **DBMS và phiên bản**. Với nội dung dùng nhiều hệ, ưu tiên các mẫu thể hiện ngữ nghĩa rõ ràng.

## 25. Bài tập thực hành

### Bài 1 — Câu truy vấn nào có quy tắc chọn cột đúng?

Xét bảng don_hang ở phần 2. Truy vấn nào được viết theo quy tắc GROUP BY chặt chẽ?

**A**

~~~sql
SELECT ma_khach_hang, COUNT(*)
FROM don_hang
GROUP BY ma_khach_hang;
~~~

**B**

~~~sql
SELECT ma_khach_hang, ma_don_hang, COUNT(*)
FROM don_hang
GROUP BY ma_khach_hang;
~~~

**C**

~~~sql
SELECT ma_khach_hang, MAX(ngay_dat), COUNT(*)
FROM don_hang
GROUP BY ma_khach_hang;
~~~

<details>
<summary>Đáp án gợi ý</summary>

**A và C** hợp lệ theo quy tắc cơ bản. B không xác định được ma_don_hang cho các nhóm khách có nhiều đơn. Một DBMS có thể cho B chạy theo chế độ mở rộng, nhưng không nên dựa vào điều đó.

</details>

### Bài 2 — Sửa một truy vấn sai

~~~sql
SELECT
    trang_thai,
    ma_don_hang,
    SUM(tong_tien) AS tong_tien
FROM don_hang
GROUP BY trang_thai;
~~~

Yêu cầu nghiệp vụ thật sự là **tổng tiền theo trạng thái**. Hãy sửa truy vấn.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT
    trang_thai,
    SUM(tong_tien) AS tong_tien
FROM don_hang
GROUP BY trang_thai;
~~~

Bỏ ma_don_hang vì đây là mã của từng đơn, không có giá trị duy nhất ở cấp trạng thái.

</details>

### Bài 3 — Vì sao thêm cột vào GROUP BY có thể sai nghiệp vụ?

Một người sửa câu trên thành:

~~~sql
SELECT
    trang_thai,
    ma_don_hang,
    SUM(tong_tien) AS tong_tien
FROM don_hang
GROUP BY trang_thai, ma_don_hang;
~~~

Câu này có thể chạy nhưng còn trả “tổng tiền theo trạng thái” như yêu cầu ban đầu không?

<details>
<summary>Đáp án gợi ý</summary>

**Không.** Khi nhóm theo cả trạng thái và mã đơn, mỗi nhóm về cơ bản đại diện cho một đơn (giả sử mã duy nhất). Nó không còn tổng hợp toàn bộ các đơn của cùng trạng thái thành một dòng.

</details>

### Bài 4 — Mức chi tiết kết quả

Cho:

~~~sql
SELECT ma_khach_hang, COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang, trang_thai;
~~~

Một khách có hai trạng thái đơn có thể xuất hiện bao nhiêu dòng?

<details>
<summary>Đáp án gợi ý</summary>

Có thể xuất hiện **hai dòng** hoặc nhiều hơn tùy số trạng thái phân biệt. SELECT không hiển thị trang_thai nhưng GROUP BY vẫn tạo các nhóm theo cặp (ma_khach_hang, trang_thai). Nên hiển thị trang_thai hoặc sửa GROUP BY theo mức chi tiết cần thiết.

</details>

### Bài 5 — Chọn ngày đầu và ngày gần nhất

Viết truy vấn trả một dòng mỗi mã khách với **ngày đơn đầu tiên** và **ngày đơn gần nhất**.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT
    ma_khach_hang,
    MIN(ngay_dat) AS ngay_dau,
    MAX(ngay_dat) AS ngay_cuoi
FROM don_hang
GROUP BY ma_khach_hang;
~~~

</details>

### Bài 6 — COUNT(*) và LEFT JOIN

Bảng khách có một người chưa phát sinh đơn. Tại sao câu:

~~~sql
SELECT k.ma_khach_hang, COUNT(*) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY k.ma_khach_hang;
~~~

có thể trả **so_don = 1** cho người không có đơn? Viết lại cách đếm phù hợp.

<details>
<summary>Đáp án gợi ý</summary>

LEFT JOIN giữ khách không có đơn bằng một dòng đệm NULL phía phải. COUNT(*) đếm dòng đó. Dùng:

~~~sql
SELECT k.ma_khach_hang, COUNT(d.ma_don_hang) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY k.ma_khach_hang;
~~~

Giả sử ma_don_hang là khóa chính NOT NULL, COUNT(d.ma_don_hang) trả 0 cho khách không có đơn khớp.

</details>

### Bài 7 — COUNT(*) và COUNT(cot)

Một nhóm có 4 dòng với tong_tien lần lượt là **100**, **NULL**, **200**, **NULL**. Hãy tính COUNT(*), COUNT(tong_tien), SUM(tong_tien).

<details>
<summary>Đáp án gợi ý</summary>

**COUNT(*) = 4**, **COUNT(tong_tien) = 2**, **SUM(tong_tien) = 300**.

</details>

### Bài 8 — Một dòng mỗi khách, nhiều chỉ số trạng thái

Viết truy vấn một dòng mỗi khách, gồm tổng số đơn và số đơn PAID, không thêm trang_thai vào GROUP BY.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don,
    SUM(CASE WHEN trang_thai = 'PAID' THEN 1 ELSE 0 END)
        AS so_don_paid
FROM don_hang
GROUP BY ma_khach_hang;
~~~

COUNT(CASE WHEN trang_thai = 'PAID' THEN 1 END) cũng là một cách đếm đơn PAID theo nhóm.

</details>

### Bài 9 — Phụ thuộc hàm

Giả sử bảng khach_hang có ma_khach_hang là PRIMARY KEY. Truy vấn chỉ GROUP BY k.ma_khach_hang nhưng SELECT thêm k.ten_khach_hang có bảo đảm chạy trên mọi DBMS không?

<details>
<summary>Đáp án gợi ý</summary>

**Không.** Một số DBMS như PostgreSQL và MySQL có thể chấp nhận nhờ suy luận phụ thuộc hàm, nhưng SQL Server và các phiên bản Oracle phổ biến yêu cầu liệt kê cột không tổng hợp phù hợp với GROUP BY. Nếu muốn khả chuyển, thêm k.ten_khach_hang vào GROUP BY hoặc tổng hợp trước rồi JOIN ra tên.

</details>

### Bài 10 — Cột thuộc bảng JOIN

Tại sao **ma_khach_hang** là PRIMARY KEY ở bảng khách không có nghĩa **d.ma_don_hang** được chọn tự do khi GROUP BY k.ma_khach_hang?

<details>
<summary>Đáp án gợi ý</summary>

Một khách có thể có nhiều đơn, nên một mã khách **không xác định duy nhất** mã đơn. Phụ thuộc hàm **k.ma_khach_hang -> k.ten_khach_hang** không kéo theo **k.ma_khach_hang -> d.ma_don_hang** trong quan hệ một-nhiều.

</details>

### Bài 11 — MAX không phải một dòng

Với khách 2 trong bảng minh họa, hãy cho biết:

- MAX(ma_don_hang).
- MAX(ngay_dat).
- MAX(tong_tien).

Các giá trị này có thuộc cùng một đơn không?

<details>
<summary>Đáp án gợi ý</summary>

- **MAX(ma_don_hang) = 106**.
- **MAX(ngay_dat) = 2026-02-10**.
- **MAX(tong_tien) = 300000**.

Ngày và mã thuộc đơn **106**, nhưng tiền cao nhất thuộc đơn **104**. Vì vậy ba phép MAX không thể được diễn giải là thông tin của một đơn duy nhất.

</details>

### Bài 12 — Tìm đơn mới nhất mỗi khách

Viết truy vấn lấy **mã, ngày và tiền của đúng đơn mới nhất** mỗi khách, giả sử ngày và mã đơn xác định thứ tự, dùng ROW_NUMBER.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
WITH x AS (
    SELECT
        ma_khach_hang,
        ma_don_hang,
        ngay_dat,
        tong_tien,
        ROW_NUMBER() OVER (
            PARTITION BY ma_khach_hang
            ORDER BY ngay_dat DESC, ma_don_hang DESC
        ) AS rn
    FROM don_hang
)
SELECT ma_khach_hang, ma_don_hang, ngay_dat, tong_tien
FROM x
WHERE rn = 1;
~~~

Nếu ngay_dat có thể NULL hoặc nhiều dòng đồng hạng, cần quy định xử lý NULL và khóa phá hòa phù hợp.

</details>

### Bài 13 — SUM sau JOIN

Hai đơn có giá 100000 và 200000; đơn thứ nhất có 2 chi tiết, đơn thứ hai có 1 chi tiết. Nếu JOIN hai bảng rồi SUM(d.tong_tien), kết quả sai thường là bao nhiêu?

<details>
<summary>Đáp án gợi ý</summary>

**400000** vì đơn đầu tiên bị nhân thành hai dòng: 100000 + 100000 + 200000. Tổng tiền đúng ở cấp đơn là **300000**. Nên tổng hợp từ bảng đơn hoặc tổng hợp riêng các cấp rồi JOIN.

</details>

### Bài 14 — GROUP BY và NULL

Nếu có ba đơn với ma_khach_hang = NULL, GROUP BY ma_khach_hang sẽ tạo bao nhiêu nhóm NULL? Vì sao không mâu thuẫn với NULL = NULL cho UNKNOWN?

<details>
<summary>Đáp án gợi ý</summary>

Thông thường tạo **một nhóm NULL**. Quy tắc GROUP BY gộp các khóa NULL thuộc cùng nhóm khác với phép so sánh bình thường **=** trong WHERE.

</details>

### Bài 15 — Tập rỗng

So sánh số dòng kết quả của hai truy vấn khi WHERE không chọn đơn nào:

~~~sql
SELECT COUNT(*) FROM don_hang WHERE trang_thai = 'X';
~~~

~~~sql
SELECT trang_thai, COUNT(*)
FROM don_hang
WHERE trang_thai = 'X'
GROUP BY trang_thai;
~~~

<details>
<summary>Đáp án gợi ý</summary>

Truy vấn thứ nhất thường trả **một dòng COUNT(*) = 0**. Truy vấn thứ hai trả **0 dòng**, vì không có khóa nhóm nào tồn tại sau WHERE.

</details>

### Bài 16 — GROUP BY biểu thức LOWER

Giả sử có cả 'PAID', 'Paid' và 'paid'. Vì sao:

~~~sql
SELECT trang_thai, COUNT(*)
FROM don_hang
GROUP BY LOWER(trang_thai);
~~~

có thể bị từ chối hoặc trả giá trị trang_thai khó đoán?

<details>
<summary>Đáp án gợi ý</summary>

Nhóm được định nghĩa theo **LOWER(trang_thai)** nhưng cột gốc **trang_thai** có thể có nhiều cách viết trong cùng nhóm. Hãy SELECT **LOWER(trang_thai)** hoặc tạo cột chuẩn hóa ở CTE rồi GROUP BY cột đó.

</details>

### Bài 17 — DISTINCT và GROUP BY

Có thể sửa:

~~~sql
SELECT ma_khach_hang, ma_don_hang, COUNT(*)
FROM don_hang
GROUP BY ma_khach_hang;
~~~

bằng cách thêm DISTINCT trước SELECT không?

<details>
<summary>Đáp án gợi ý</summary>

**Không.** DISTINCT chỉ loại dòng trùng sau khi kết quả SELECT đã được xác định; nó không giải quyết vấn đề chọn mã đơn nào từ một nhóm có nhiều đơn.

</details>

### Bài 18 — Thiết kế truy vấn báo cáo

Yêu cầu: “Mỗi khách một dòng gồm mã khách, tên khách, số đơn PAID và tổng tiền PAID. Giữ cả khách chưa có đơn PAID.”

Hãy viết một truy vấn với LEFT JOIN, GROUP BY đúng cột, điều kiện trạng thái đặt ở nơi phù hợp.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COUNT(d.ma_don_hang) AS so_don_paid,
    COALESCE(SUM(d.tong_tien), 0) AS tong_tien_paid
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID'
GROUP BY
    k.ma_khach_hang,
    k.ten_khach_hang
ORDER BY k.ma_khach_hang;
~~~

Đặt điều kiện PAID trong **ON** giữ khách không có đơn PAID. COUNT(d.ma_don_hang) không đếm dòng đệm NULL từ LEFT JOIN. Việc dùng COALESCE(SUM(...), 0) ở đây là quy tắc báo cáo để hiển thị 0 khi không có tổng tiền, cần được xác nhận theo nghiệp vụ.

</details>

## 26. Tình huống tổng hợp: từ yêu cầu đến câu SQL đúng

Giả sử hệ thống bán hàng cần báo cáo:

> “Với **mỗi khách hàng**, hiển thị mã, tên, **số đơn đã thanh toán**, **tổng tiền đã thanh toán**, **ngày thanh toán gần nhất**; chỉ lấy khách có từ hai đơn PAID trở lên; sắp xếp tổng tiền giảm dần.”

Bảng sử dụng:

~~~text
khach_hang(
    ma_khach_hang PRIMARY KEY,
    ten_khach_hang
)

don_hang(
    ma_don_hang PRIMARY KEY,
    ma_khach_hang,
    trang_thai,
    tong_tien,
    ngay_dat
)
~~~

### Bước 1: Xác định mức chi tiết

**Mỗi dòng = một khách hàng**. Khóa nhóm là **ma_khach_hang**; tên là cột mô tả khách.

### Bước 2: Xác định phép tổng hợp

- Số đơn PAID = COUNT(d.ma_don_hang) sau khi chỉ nối các đơn PAID.
- Tổng tiền PAID = SUM(d.tong_tien).
- Ngày PAID gần nhất = MAX(d.ngay_dat).
- Điều kiện ít nhất hai đơn = HAVING COUNT(...) >= 2.

### Bước 3: Viết truy vấn

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COUNT(d.ma_don_hang) AS so_don_paid,
    SUM(d.tong_tien) AS tong_tien_paid,
    MAX(d.ngay_dat) AS ngay_paid_gan_nhat
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID'
GROUP BY
    k.ma_khach_hang,
    k.ten_khach_hang
HAVING COUNT(d.ma_don_hang) >= 2
ORDER BY
    tong_tien_paid DESC,
    k.ma_khach_hang ASC;
~~~

Ở đây, dù dùng LEFT JOIN, HAVING từ hai đơn PAID trở lên sẽ loại các khách không đủ số đơn, đúng với yêu cầu cuối cùng.

### Bước 4: Phân loại cột trong SELECT

| Cột hoặc biểu thức | Vì sao hợp lệ? |
|---|---|
| k.ma_khach_hang | Khóa nhóm |
| k.ten_khach_hang | Có mặt trong GROUP BY |
| COUNT(d.ma_don_hang) | Hàm tổng hợp, đếm đơn khớp |
| SUM(d.tong_tien) | Hàm tổng hợp, tính tiền theo nhóm |
| MAX(d.ngay_dat) | Hàm tổng hợp, trả ngày muộn nhất |
| ORDER BY tong_tien_paid | Sắp xếp theo kết quả tổng hợp |

Nếu muốn thêm **d.ma_don_hang** vào SELECT để hiển thị mã đơn PAID gần nhất, không được thêm trực tiếp vào cùng truy vấn mà chưa xác định dòng đại diện. Khi đó, cần một truy vấn riêng chọn dòng PAID mới nhất rồi JOIN vào kết quả tổng hợp theo khách, hoặc dùng hàm cửa sổ với tiêu chí rõ.

### Bước 5: Xem xét dữ liệu bất thường

- Nếu **tong_tien NULL** ở một đơn PAID, SUM bỏ qua số tiền thiếu nhưng COUNT vẫn đếm đơn.
- Nếu nhiều đơn cùng ngày gần nhất, MAX(ngay_dat) chỉ cho ngày, không chọn một mã đơn.
- Nếu một khách có cùng tên với khách khác, GROUP BY có **ma_khach_hang** nên vẫn là hai nhóm riêng.
- Nếu bảng đơn JOIN thêm bảng chi tiết nhiều dòng, cần tránh nhân số tiền.
- Nếu cần hiển thị khách chưa có đơn PAID, phải bỏ HAVING hiện tại hoặc đổi yêu cầu lọc nhóm.

Đây là một ví dụ cho thấy **quy tắc chọn cột khi có GROUP BY** gắn chặt với việc xác định **một dòng kết quả đang đại diện cho cái gì**.

## 27. Ghi nhớ quan trọng

1. **GROUP BY quyết định mức chi tiết của kết quả:** một dòng cho mỗi nhóm khóa, không phải một dòng cho mỗi chi tiết ban đầu.
2. Các biểu thức trong SELECT phải **được xác định ở cấp nhóm**: khóa nhóm, hàm tổng hợp, hằng số, biểu thức từ giá trị đã xác định hoặc phụ thuộc hàm được DBMS nhận diện.
3. **Không chọn tùy ý cột chi tiết** khi trong một nhóm có nhiều giá trị của cột đó. Một số DBMS sẽ báo lỗi; một số có thể cho giá trị không bảo đảm.
4. **Thêm cột vào GROUP BY có thể đổi yêu cầu nghiệp vụ** bằng cách tạo nhóm chi tiết hơn. Đừng sửa lỗi chỉ bằng cách liệt kê mọi cột SELECT.
5. **MIN/MAX** chọn giá trị cực trị của một biểu thức, không tự chọn tất cả các cột từ cùng dòng chứa cực trị.
6. Khi cần **một dòng cụ thể của mỗi nhóm**, dùng ROW_NUMBER, RANK, truy vấn con hoặc JOIN ngược với quy tắc xử lý đồng hạng.
7. **Phụ thuộc hàm** cho phép một số DBMS suy ra cột theo khóa chính; khả năng áp dụng khác giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite.
8. **SQLite bare columns, MySQL ANY_VALUE, DISTINCT ON** là những hành vi/tính năng theo phương ngữ; không xem chúng là giải pháp SQL phổ quát.
9. **COUNT(*) và COUNT(cot)** khác nhau khi cột NULL; với LEFT JOIN, COUNT(khóa NOT NULL phía phải) thường phù hợp hơn để đếm bản ghi khớp.
10. **GROUP BY gom các khóa NULL thành nhóm**, không giống phép so sánh NULL = NULL trong WHERE.
11. **JOIN một-nhiều có thể nhân dòng trước khi tổng hợp**. Kiểm tra mức chi tiết của từng bảng và tổng hợp đúng nguồn trước khi JOIN nếu cần.
12. **WHERE lọc dòng trước nhóm, HAVING lọc nhóm sau tổng hợp, ORDER BY sắp xếp kết quả**. Không mệnh đề nào tự giải quyết việc chọn một cột mơ hồ.
13. Một truy vấn có thể **đúng cú pháp nhưng sai số liệu báo cáo**. Luôn đối chiếu với dữ liệu có 0, 1, nhiều dòng mỗi nhóm, cột NULL và giá trị đồng hạng.

### Tài liệu tham khảo định hướng

Khi áp dụng vào hệ quản trị thật, nên tra cứu tài liệu chính thức của sản phẩm và **đúng phiên bản đang triển khai**, đặc biệt là các mục SELECT, GROUP BY, HAVING, aggregate functions, functional dependencies, window functions và SQL mode:

- **PostgreSQL Documentation:** *SELECT*, *GROUP BY*, *Aggregate Functions*, *Window Functions*.
- **MySQL Reference Manual:** *MySQL Handling of GROUP BY*, *Detection of Functional Dependence*, *ONLY_FULL_GROUP_BY*, *ANY_VALUE()*.
- **Microsoft Learn — Transact-SQL:** *SELECT — GROUP BY*, *Aggregate Functions*, *OVER Clause*.
- **Oracle Database SQL Language Reference:** *SELECT*, *GROUP BY Clause*, *Aggregate Functions*, *Analytic Functions*.
- **SQLite Documentation:** *SELECT — Bare Columns in an Aggregate Query*, *Aggregate Functions*, *Window Functions*.

**Thông điệp quan trọng nhất:** trước khi đưa một cột vào SELECT của truy vấn GROUP BY, hãy tự hỏi **“ở mỗi nhóm, cột này có duy nhất một giá trị có nghĩa hay chưa; nếu chưa, quy tắc nào sẽ quyết định giá trị được trả?”**. Câu hỏi đó giúp tránh cả lỗi cú pháp lẫn những báo cáo tổng hợp sai mà SQL vẫn có thể chạy.
