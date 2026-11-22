# NVL, NVL2, COALESCE, NULLIF và lựa chọn kiểu kết quả

Trong Oracle Database, **NULL** biểu thị giá trị chưa biết, chưa được cung cấp hoặc không áp dụng theo mô hình dữ liệu. Khi tính toán hoặc hiển thị, ứng dụng thường cần thay NULL bằng giá trị mặc định, chọn một trong nhiều nguồn thay thế, kiểm tra một giá trị có tồn tại hay không, hoặc biến một giá trị đặc biệt thành NULL để phép tính an toàn hơn.

Oracle cung cấp bốn hàm thường gặp cho những tình huống này:

- **NVL(expr1, expr2):** trả expr1 nếu không NULL, nếu NULL thì trả expr2.
- **NVL2(expr1, expr2, expr3):** trả expr2 khi expr1 không NULL, ngược lại trả expr3.
- **COALESCE(expr1, expr2, ...):** trả biểu thức đầu tiên không NULL trong danh sách.
- **NULLIF(expr1, expr2):** trả NULL nếu hai biểu thức bằng nhau, nếu không trả expr1.

Nhìn qua, các hàm đều liên quan đến NULL, nhưng **điều kiện chọn giá trị, số lượng đối số và quy tắc xác định kiểu dữ liệu kết quả khác nhau**. Nếu chỉ chú ý giá trị hiển thị mà bỏ qua kiểu dữ liệu, một câu SQL có thể gặp lỗi chuyển kiểu, cho kết quả không như mong muốn hoặc làm thay đổi khả năng sử dụng index.

## 1. NULL trong Oracle và logic ba giá trị

Trong SQL, NULL không phải số 0, không phải chuỗi ký tự "NULL" và cũng không đơn giản là một giá trị rỗng có thể so sánh bằng dấu bằng. NULL biểu thị trạng thái chưa biết hoặc không có giá trị theo mô hình dữ liệu.

~~~sql
SELECT
    CASE WHEN NULL = NULL THEN 'BANG NHAU'
         ELSE 'KHONG BANG'
    END AS ket_qua_so_sanh
FROM dual;
~~~

Điều kiện NULL = NULL có kết quả **UNKNOWN**, không phải TRUE. Trong searched CASE, nhánh WHEN chỉ được chọn khi điều kiện TRUE, nên ví dụ trả về KHONG BANG.

Muốn kiểm tra NULL, dùng IS NULL:

~~~sql
SELECT *
FROM nhan_vien
WHERE ngay_nghi IS NULL;
~~~

Không viết WHERE ngay_nghi = NULL, vì điều kiện không trở thành TRUE cho các hàng NULL.

SQL sử dụng logic ba giá trị:

| Biểu thức | Kết quả logic |
| --- | --- |
| 5 = 5 | TRUE |
| 5 = 7 | FALSE |
| 5 = NULL | UNKNOWN |
| NULL = NULL | UNKNOWN |
| NULL IS NULL | TRUE |
| NULL IS NOT NULL | FALSE |

Điều kiện WHERE chỉ giữ hàng khi biểu thức TRUE. FALSE và UNKNOWN đều không được chọn. Các hàm NVL, NVL2, COALESCE và NULLIF giúp xử lý giá trị NULL trong biểu thức, nhưng không thay đổi quy tắc logic ba giá trị của SQL.

### 1.1. Chuỗi rỗng trong Oracle

Với kiểu ký tự VARCHAR2, Oracle hiện coi chuỗi độ dài bằng 0 là NULL:

~~~sql
SELECT
    CASE WHEN '' IS NULL THEN 'LA NULL'
         ELSE 'KHONG NULL'
    END AS ket_qua
FROM dual;
~~~

Kết quả là LA NULL. Vì vậy:

~~~sql
SELECT NVL('', 'Chua nhap') AS gia_tri
FROM dual;
~~~

trả về Chua nhap.

Một chuỗi chỉ chứa dấu cách, ví dụ '   ', không phải chuỗi độ dài bằng 0; nó vẫn là giá trị ký tự không NULL. Nếu nghiệp vụ muốn coi chuỗi toàn dấu cách là chưa nhập, phải chuẩn hóa, ví dụ dùng TRIM:

~~~sql
SELECT NVL(TRIM(ho_ten), 'Chua cap nhat')
FROM khach_hang;
~~~

TRIM có thể trả chuỗi rỗng, và chuỗi rỗng đó được Oracle xem là NULL. Không áp dụng trim tự động nếu dấu cách đầu/cuối có ý nghĩa trong dữ liệu.

## 2. NVL: thay NULL bằng một giá trị khác

Cú pháp:

~~~sql
NVL(expr1, expr2)
~~~

- Nếu expr1 không NULL, kết quả là expr1.
- Nếu expr1 là NULL, kết quả là expr2.

Ví dụ:

~~~sql
SELECT ma_nhan_vien,
       ho_ten,
       NVL(thuong, 0) AS thuong_hien_thi
FROM nhan_vien;
~~~

Nếu cột THUONG là NULL, kết quả hiển thị 0. Nếu THUONG có giá trị 2.500.000, kết quả vẫn là 2.500.000.

### 2.1. NVL với NUMBER

~~~sql
SELECT NVL(NULL, 0) AS gia_tri
FROM dual;
~~~

Trong biểu thức thực tế, nên làm rõ kiểu số nếu có nhiều kiểu NUMBER/BINARY_FLOAT/BINARY_DOUBLE hoặc literal cần chuyển đổi:

~~~sql
SELECT NVL(CAST(NULL AS NUMBER(10,2)), 0) AS so_tien
FROM dual;
~~~

NVL áp dụng quy tắc chuyển đổi kiểu của Oracle. Khi expr1 là kiểu ký tự, Oracle chuyển expr2 sang kiểu ký tự của expr1 và trả VARCHAR2 theo bộ ký tự của expr1. Khi expr1 là kiểu số, Oracle xác định kiểu có độ ưu tiên số cao nhất trong các đối số và chuyển đổi đối số còn lại theo quy tắc số học.

Ví dụ:

~~~sql
SELECT NVL(CAST(NULL AS NUMBER), 100) AS ket_qua
FROM dual;
~~~

Kết quả mang kiểu số. Còn nếu cột đầu tiên là VARCHAR2:

~~~sql
SELECT NVL(ma_tham_chieu, 0) AS ma_hien_thi
FROM du_lieu_import;
~~~

thì Oracle có thể chuyển số 0 thành chuỗi '0', bởi đối số đầu là ký tự. Không nên mặc định kết quả luôn là NUMBER chỉ vì đối số thứ hai là số.

### 2.2. NVL với DATE

~~~sql
SELECT NVL(ngay_kich_hoat, DATE '2024-01-01') AS ngay_su_dung
FROM tai_khoan;
~~~

Dùng DATE literal giúp tránh việc Oracle phải parse một chuỗi ngày theo NLS_DATE_FORMAT của session.

Tránh:

~~~sql
-- Không nên dựa vào implicit conversion của chuỗi ngày.
SELECT NVL(ngay_kich_hoat, '01/01/2024')
FROM tai_khoan;
~~~

Chuỗi '01/01/2024' có thể được hiểu hoặc từ chối khác nhau tùy thiết lập định dạng ngày. Nếu đầu vào là chuỗi, hãy chuyển kiểu tường minh:

~~~sql
SELECT NVL(
           ngay_kich_hoat,
           TO_DATE('01/01/2024', 'DD/MM/YYYY')
       ) AS ngay_su_dung
FROM tai_khoan;
~~~

### 2.3. NVL không có nhiều lựa chọn

NVL nhận đúng hai đối số. Khi cần nhiều phương án dự phòng, có thể lồng NVL:

~~~sql
SELECT NVL(email_cong_ty,
           NVL(email_ca_nhan, 'Chua co email')) AS email_lien_he
FROM nhan_vien;
~~~

Nhưng với ba hoặc nhiều biểu thức, COALESCE thường dễ đọc hơn:

~~~sql
SELECT COALESCE(
           email_cong_ty,
           email_ca_nhan,
           email_khac,
           'Chua co email'
       ) AS email_lien_he
FROM nhan_vien;
~~~

## 3. NVL2: chọn một trong hai kết quả dựa trên NULL

Cú pháp:

~~~sql
NVL2(expr1, expr2, expr3)
~~~

- Nếu expr1 không NULL, trả expr2.
- Nếu expr1 là NULL, trả expr3.

Ví dụ:

~~~sql
SELECT ma_nhan_vien,
       ho_ten,
       NVL2(ngay_nghi_viec,
            'DA NGHI VIEC',
            'DANG LAM VIEC') AS trang_thai
FROM nhan_vien;
~~~

Nếu NGAY_NGHI_VIEC có ngày, kết quả là DA NGHI VIEC; nếu NULL, kết quả là DANG LAM VIEC.

**NVL2 không trả lại expr1.** Đối số đầu chỉ là điều kiện kiểm tra NULL, hai đối số sau là hai giá trị kết quả.

### 3.1. So sánh NVL và NVL2

| Hàm | Đối số | Quy tắc |
| --- | --- | --- |
| NVL(a, b) | 2 | a NULL thì b, ngược lại a |
| NVL2(a, b, c) | 3 | a không NULL thì b, a NULL thì c |

Ví dụ với cột BONUS:

~~~sql
SELECT ma_nhan_vien,
       NVL(bonus, 0) AS bonus,
       NVL2(bonus, 'Co thuong', 'Chua co thuong') AS nhan_xet
FROM nhan_vien;
~~~

Một người có BONUS = 0 vẫn là **không NULL**, nên NVL2 trả Co thuong. Nếu nghiệp vụ muốn coi bonus bằng 0 là không có thưởng, điều kiện phải kiểm tra cả NULL và 0, ví dụ dùng CASE:

~~~sql
CASE
    WHEN bonus IS NULL OR bonus = 0 THEN 'Khong co thuong'
    ELSE 'Co thuong'
END
~~~

NULL và 0 là hai trạng thái khác nhau; không nên nhập nhằng chỉ vì màn hình muốn hiển thị giống nhau.

### 3.2. Kiểu dữ liệu kết quả của NVL2

Đối với NVL2, expr1 quyết định nhánh nào được chọn, còn **kiểu kết quả chủ yếu được xác định từ expr2 và expr3**:

- Nếu expr2 là kiểu ký tự, Oracle trả VARCHAR2 theo bộ ký tự của expr2; expr3 được chuyển sang kiểu tương ứng theo quy tắc chuyển đổi ký tự, với các ngoại lệ cho kiểu national character.
- Nếu expr2 là kiểu số, Oracle xác định kiểu số có độ ưu tiên cao nhất giữa expr2 và expr3, rồi chuyển đổi đối số còn lại phù hợp.
- Với các kiểu khác, phải tuân theo quy tắc chuyển đổi kiểu tương thích của Oracle; không nên trộn tùy tiện DATE, NUMBER và chuỗi.

Ví dụ:

~~~sql
SELECT NVL2(
           CAST(NULL AS NUMBER),
           100,
           0
       ) AS ket_qua_so
FROM dual;
~~~

Vì đối số thứ nhất NULL, giá trị kết quả là 0; kiểu kết quả vẫn là kiểu số theo các đối số nhánh.

~~~sql
SELECT NVL2(
           DATE '2024-01-01',
           'Da kich hoat',
           'Chua kich hoat'
       ) AS trang_thai
FROM dual;
~~~

Đối số đầu không NULL, nên trả Da kich hoat.

Không dựa vào kiểu của expr1 để đoán kiểu kết quả NVL2. Khi biểu thức phức tạp, có thể dùng DUMP, VSIZE hoặc metadata của result set để quan sát kiểu Oracle/driver thực tế.

## 4. COALESCE: lấy giá trị không NULL đầu tiên

Cú pháp:

~~~sql
COALESCE(expr1, expr2, ...)
~~~

COALESCE trả **biểu thức đầu tiên không NULL**, đọc từ trái sang phải. Hàm yêu cầu ít nhất hai biểu thức và có thể nhận nhiều hơn hai.

Ví dụ:

~~~sql
SELECT ma_khach_hang,
       COALESCE(
           so_dien_thoai,
           email,
           'Chua co thong tin lien he'
       ) AS thong_tin_lien_he
FROM khach_hang;
~~~

Nếu SO_DIEN_THOAI có giá trị, kết quả là số điện thoại; nếu NULL thì lấy EMAIL; nếu cả hai NULL thì trả chuỗi mặc định.

### 4.1. Thứ tự đối số là thứ tự ưu tiên

~~~sql
SELECT COALESCE(email_cong_ty, email_ca_nhan, email_khac)
       AS email_duoc_chon
FROM nhan_vien;
~~~

Nếu email công ty và email cá nhân đều có, COALESCE chọn email công ty vì nó đứng trước. Đổi thứ tự đối số sẽ đổi kết quả. Đây không phải hàm tìm giá trị tốt nhất hoặc mới nhất; nó chỉ tuân theo thứ tự đã viết.

### 4.2. COALESCE và CASE

COALESCE có ngữ nghĩa tương đương một searched CASE:

~~~sql
COALESCE(a, b, c)
~~~

tương đương về ý nghĩa chọn giá trị với:

~~~sql
CASE
    WHEN a IS NOT NULL THEN a
    WHEN b IS NOT NULL THEN b
    ELSE c
END
~~~

COALESCE có **short-circuit evaluation**: Oracle đánh giá các biểu thức từ trái sang phải và không cần đánh giá những biểu thức sau khi đã tìm được biểu thức không NULL đầu tiên. Điều này hữu ích khi danh sách có nhiều lựa chọn, nhưng không nên thiết kế biểu thức có side effect hoặc dựa vào thứ tự thực thi của hàm tự viết để điều khiển giao dịch.

### 4.3. COALESCE có quy tắc kiểu dữ liệu

Oracle phải xác định kiểu dữ liệu chung cho các đối số. Nếu các biểu thức là số hoặc có thể chuyển đổi theo quy tắc số, Oracle sử dụng **numeric precedence** để xác định kiểu kết quả. Với các kiểu ký tự hoặc kiểu khác, các biểu thức phải tương thích theo quy tắc chuyển đổi kiểu của Oracle.

Ví dụ số:

~~~sql
SELECT COALESCE(
           CAST(NULL AS NUMBER),
           10,
           20.5
       ) AS gia_tri
FROM dual;
~~~

Ví dụ chuỗi:

~~~sql
SELECT COALESCE(
           email_cong_ty,
           email_ca_nhan,
           CAST('Chua co email' AS VARCHAR2(100))
       ) AS email
FROM nhan_vien;
~~~

Không trộn một DATE, một NUMBER và một chuỗi tùy tiện với kỳ vọng Oracle sẽ tự chọn kiểu phù hợp theo giá trị runtime đầu tiên không NULL. **Kiểu kết quả được xác định khi phân tích biểu thức SQL**, không chờ đến lúc biết hàng nào sẽ đi vào nhánh nào.

Nếu cần một kiểu đích rõ ràng, hãy CAST các đối số về kiểu tương thích:

~~~sql
SELECT COALESCE(
           CAST(so_tien_thuc_te AS NUMBER(12,2)),
           CAST(so_tien_du_kien AS NUMBER(12,2)),
           CAST(0 AS NUMBER(12,2))
       ) AS so_tien
FROM don_hang;
~~~

### 4.4. COALESCE khác NVL ở điểm nào?

| Tiêu chí | NVL | COALESCE |
| --- | --- | --- |
| Số đối số | Chính xác 2 | Từ 2 trở lên |
| Quy tắc chọn | expr1 NULL thì expr2 | Chọn biểu thức đầu tiên không NULL |
| Kiểu dữ liệu | Quy tắc chuyển đổi đặc trưng theo expr1 và numeric precedence | Quy tắc kiểu chung của biểu thức, numeric precedence khi các đối số là số |
| Đánh giá nhánh | Không nên dùng làm cơ chế điều khiển thứ tự đánh giá | Oracle tài liệu hóa short-circuit evaluation |
| Cú pháp tương đương | Có thể biểu diễn bằng CASE | Là cách viết ngắn của CASE nhiều nhánh |

Ví dụ NVL và COALESCE cùng trả giá trị trong trường hợp đơn giản:

~~~sql
SELECT NVL(CAST(NULL AS NUMBER), 5) AS bang_nvl,
       COALESCE(CAST(NULL AS NUMBER), 5) AS bang_coalesce
FROM dual;
~~~

Nhưng không nên kết luận hai hàm luôn tương đương về kiểu dữ liệu, cách đánh giá biểu thức hoặc khả năng xử lý các đối số phức tạp.

## 5. NULLIF: biến giá trị bằng nhau thành NULL

Cú pháp:

~~~sql
NULLIF(expr1, expr2)
~~~

- Nếu expr1 = expr2 là TRUE, trả NULL.
- Nếu hai biểu thức khác nhau, trả expr1.
- Nếu phép so sánh là UNKNOWN vì có NULL, hàm không xem hai giá trị là bằng nhau; kết quả theo nhánh trả expr1, nên nếu expr1 NULL thì kết quả vẫn NULL.

NULLIF tương đương về ý nghĩa với:

~~~sql
CASE
    WHEN expr1 = expr2 THEN NULL
    ELSE expr1
END
~~~

Đối số đầu tiên của NULLIF **không được là literal NULL**. Hãy truyền một biểu thức có kiểu dữ liệu phù hợp.

### 5.1. Ví dụ loại bỏ giá trị sentinel

Một hệ thống cũ có thể dùng 0 để biểu thị chưa xác định, dù miền dữ liệu thực tế không nên coi 0 là kết quả:

~~~sql
SELECT NULLIF(diem, 0) AS diem_hop_le
FROM ket_qua_thi;
~~~

Nếu DIEM bằng 0, kết quả là NULL; nếu khác 0, giữ nguyên điểm. Chỉ dùng cách này khi quy ước dữ liệu thật sự định nghĩa 0 là sentinel. Nếu 0 là một điểm hợp lệ, NULLIF sẽ làm mất thông tin.

### 5.2. NULLIF để tránh chia cho 0

Một ứng dụng tính tỷ lệ:

~~~sql
SELECT doanh_thu / NULLIF(so_don, 0) AS doanh_thu_moi_don
FROM thong_ke;
~~~

Nếu SO_DON = 0, NULLIF(so_don, 0) trả NULL; phép chia cho NULL trả NULL thay vì lỗi chia cho 0. Nếu SO_DON vốn NULL, kết quả cũng NULL.

Nếu báo cáo muốn hiển thị 0 thay cho tỷ lệ chưa xác định:

~~~sql
SELECT NVL(
           doanh_thu / NULLIF(so_don, 0),
           0
       ) AS doanh_thu_moi_don_hien_thi
FROM thong_ke;
~~~

Nhưng cần phân biệt:
- SO_DON = 0: không có đơn để tính trung bình.
- SO_DON IS NULL: chưa biết số đơn.
- Kết quả 0: một giá trị báo cáo được quy ước để hiển thị.

Việc NVL kết quả thành 0 là **quyết định trình bày/nghiệp vụ**, không phải kết luận toán học rằng doanh thu mỗi đơn bằng 0.

### 5.3. Kiểu dữ liệu của NULLIF

NULLIF trả kiểu của expr1, theo các quy tắc chuyển đổi và so sánh tương ứng. Với đối số số có kiểu khác nhau, Oracle áp dụng numeric precedence. Với ký tự, kiểu và collation của phép so sánh cần tương thích.

~~~sql
SELECT NULLIF(
           CAST(10 AS NUMBER(8,2)),
           CAST(10 AS NUMBER(8,2))
       ) AS ket_qua
FROM dual;
~~~

Kết quả là NULL, nhưng biểu thức vẫn có kiểu số phù hợp với đối số thứ nhất.

## 6. Bảng so sánh bốn hàm

| Hàm | Điều kiện | Giá trị trả về | Số đối số |
| --- | --- | --- | --- |
| NVL(a,b) | a NULL? | a nếu có giá trị, ngược lại b | 2 |
| NVL2(a,b,c) | a có NULL không? | b nếu a không NULL, c nếu a NULL | 3 |
| COALESCE(a,b,c,...) | Tìm từ trái sang phải | Giá trị đầu tiên không NULL | 2 trở lên |
| NULLIF(a,b) | a bằng b? | NULL nếu bằng, nếu khác trả a | 2 |

Ví dụ cùng một dữ liệu:

~~~sql
WITH du_lieu AS (
    SELECT CAST(NULL AS NUMBER) AS a,
           10 AS b,
           20 AS c
    FROM dual
)
SELECT NVL(a, b) AS ket_qua_nvl,
       NVL2(a, b, c) AS ket_qua_nvl2,
       COALESCE(a, b, c) AS ket_qua_coalesce,
       NULLIF(b, c) AS ket_qua_nullif
FROM du_lieu;
~~~

Kết quả:
- NVL(a,b) trả 10 vì a NULL.
- NVL2(a,b,c) trả 20 vì a NULL nên chọn đối số thứ ba.
- COALESCE(a,b,c) trả 10 vì b là giá trị không NULL đầu tiên.
- NULLIF(b,c) trả 10 vì 10 khác 20.

Đổi a thành 5 sẽ làm NVL trả 5, NVL2 trả b = 10, COALESCE trả 5, còn NULLIF(b,c) vẫn là 10. Bốn hàm giải quyết bốn mục đích khác nhau.

## 7. Lựa chọn kiểu kết quả: điểm dễ gây lỗi nhất

Oracle xác định kiểu dữ liệu của biểu thức trong giai đoạn phân tích/biên dịch SQL. Giá trị NULL ở runtime không khiến Oracle thay đổi kiểu trả về theo từng hàng. Vì vậy, khi dùng hàm NULL, phải xem cả **giá trị** lẫn **datatype**.

### 7.1. NVL với cột VARCHAR2 và giá trị NUMBER

Giả sử MA_THAM_CHIEU là VARCHAR2:

~~~sql
SELECT NVL(ma_tham_chieu, 0) AS ma_hien_thi
FROM du_lieu_import;
~~~

Do đối số đầu là ký tự, giá trị 0 có thể được chuyển thành chuỗi. Nếu tầng Java đọc kết quả bằng getString, điều này có thể phù hợp; nếu đọc bằng getBigDecimal, không nên giả định kiểu cột đã là NUMBER.

Ngược lại:

~~~sql
SELECT NVL(so_luong, '0') AS so_luong_hien_thi
FROM chi_tiet_don_hang;
~~~

Nếu SO_LUONG là NUMBER, chuỗi '0' có thể được chuyển sang kiểu số. Với chuỗi không phải số, phép chuyển đổi có thể thất bại.

### 7.2. Lỗi do implicit conversion

~~~sql
SELECT NVL(
           CAST(NULL AS NUMBER),
           'khong phai so'
       )
FROM dual;
~~~

Oracle phải chuyển đối số thứ hai về kiểu số theo quy tắc NVL; chuỗi không chuyển được thành số sẽ gây lỗi chuyển đổi, thường là ORA-01722 hoặc lỗi liên quan tùy biểu thức/phiên bản.

Không dựa vào việc một hàng hiện tại có expr1 không NULL để cho rằng expr2 sai kiểu sẽ không bao giờ gây lỗi. Kiểu dữ liệu của biểu thức phải tương thích ngay từ lúc parse.

### 7.3. CAST để xác định kiểu đích

Nếu muốn kết quả là NUMBER có precision/scale cụ thể:

~~~sql
SELECT COALESCE(
           CAST(tien_thuc_te AS NUMBER(12,2)),
           CAST(tien_du_kien AS NUMBER(12,2)),
           CAST(0 AS NUMBER(12,2))
       ) AS tong_tien
FROM don_hang;
~~~

Nếu muốn kết quả là VARCHAR2:

~~~sql
SELECT COALESCE(
           CAST(ma_tham_chieu AS VARCHAR2(30)),
           CAST(ma_legacy AS VARCHAR2(30)),
           CAST('CHUA CO MA' AS VARCHAR2(30))
       ) AS ma_hien_thi
FROM du_lieu_import;
~~~

CAST hữu ích khi:
- Các cột có NUMBER precision/scale khác nhau.
- Kết quả phải có kiểu nhất quán cho JDBC hoặc view.
- Literal NULL không mang đủ thông tin kiểu.
- Cần tránh implicit conversion phụ thuộc NLS.
- Biểu thức được dùng trong UNION, CASE, COALESCE hoặc cột tính toán.

Không CAST một cách tùy tiện nếu làm mất precision hoặc gây chuyển đổi không cần thiết.

### 7.4. NULL có kiểu trong biểu thức

Một literal NULL đứng một mình không nêu rõ kiểu dữ liệu mong muốn. Khi kết hợp nhiều biểu thức, nên CAST để Oracle xác định kiểu đích:

~~~sql
SELECT COALESCE(
           CAST(NULL AS DATE),
           DATE '2024-01-01'
       ) AS ngay_mac_dinh
FROM dual;
~~~

Tương tự với TIMESTAMP:

~~~sql
SELECT NVL(
           CAST(NULL AS TIMESTAMP(3)),
           TIMESTAMP '2024-01-01 08:30:00.000'
       ) AS thoi_diem
FROM dual;
~~~

Cách viết tường minh làm rõ hợp đồng kiểu dữ liệu giữa SQL và ứng dụng.

## 8. Hàm NULL trong phép tính, tổng hợp và báo cáo

### 8.1. Phép toán số học với NULL

Trong Oracle, phép toán số học có toán hạng NULL thường cho kết quả NULL:

~~~sql
SELECT 100 + NULL AS ket_qua
FROM dual;
~~~

Kết quả là NULL. Nếu nghiệp vụ quy ước một khoản phụ phí chưa nhập được tính bằng 0:

~~~sql
SELECT gia_co_ban + NVL(phu_phi, 0) AS tong_gia
FROM san_pham;
~~~

Chỉ dùng NVL khi NULL thật sự có nghĩa không có khoản phí. Nếu NULL có nghĩa chưa được xác định, việc thay 0 có thể làm báo cáo sai.

### 8.2. COUNT, SUM và AVG xử lý NULL

Hàm tổng hợp thường bỏ qua NULL ở cột đối số, nhưng COUNT(*) đếm mọi hàng:

| Biểu thức | Hành vi với NULL |
| --- | --- |
| COUNT(*) | Đếm tất cả hàng |
| COUNT(cot) | Đếm hàng có COT không NULL |
| SUM(cot) | Cộng các giá trị không NULL; nếu không có giá trị nào để cộng thì trả NULL |
| AVG(cot) | Tính trung bình trên các giá trị không NULL; nếu không có giá trị nào thì trả NULL |
| MIN(cot), MAX(cot) | Bỏ qua NULL; nếu không có giá trị thì trả NULL |

Ví dụ:

~~~sql
SELECT COUNT(*) AS tong_hang,
       COUNT(thuong) AS so_hang_co_thuong,
       SUM(thuong) AS tong_thuong,
       NVL(SUM(thuong), 0) AS tong_thuong_hien_thi
FROM nhan_vien;
~~~

NVL(SUM(thuong), 0) thay kết quả tổng NULL thành 0. Điều này khác với:

~~~sql
SELECT SUM(NVL(thuong, 0))
FROM nhan_vien;
~~~

Nếu bảng có ít nhất một hàng nhưng toàn bộ THUONG đều NULL, SUM(NVL(THUONG,0)) có thể trả 0. Nếu tập đầu vào không có hàng nào, SUM vẫn trả NULL vì không có hàng để tính. Trong khi đó NVL(SUM(THUONG),0) sẽ trả 0 ngay cả khi không có hàng.

### 8.3. AVG(NVL(cot,0)) khác NVL(AVG(cot),0)

~~~sql
SELECT AVG(diem) AS trung_binh_bo_qua_null,
       AVG(NVL(diem, 0)) AS trung_binh_tinh_null_bang_0,
       NVL(AVG(diem), 0) AS trung_binh_hien_thi
FROM ket_qua_thi;
~~~

- AVG(DIEM) bỏ qua hàng có điểm NULL.
- AVG(NVL(DIEM,0)) coi mỗi điểm NULL là 0 trong mẫu số, nếu có hàng.
- NVL(AVG(DIEM),0) chỉ thay kết quả AVG NULL bằng 0 ở đầu ra.

Ba biểu thức có thể cho kết quả khác nhau đáng kể. Phải xác định NULL là không tham gia mẫu số, được tính là 0, hay toàn bộ kết quả chưa xác định.

### 8.4. Dùng NULLIF với tỷ lệ

~~~sql
SELECT ma_phong,
       SUM(doanh_thu) / NULLIF(SUM(so_don), 0) AS doanh_thu_moi_don
FROM thong_ke_phong
GROUP BY ma_phong;
~~~

Nếu tổng số đơn bằng 0, mẫu số trở thành NULL và tỷ lệ là NULL thay vì lỗi chia cho 0. Nếu muốn báo cáo hiển thị dấu gạch ngang cho tỷ lệ không xác định, có thể dùng NVL/COALESCE với kiểu ký tự, nhưng khi đó kiểu kết quả có thể chuyển thành VARCHAR2; không nên dùng biểu thức hiển thị thay cho cột số cần tính tiếp.

## 9. Điều kiện lọc: NVL và index

Dùng NVL trong SELECT để hiển thị thường đơn giản. Nhưng khi đặt hàm lên cột trong WHERE, cần xem tác động đến index.

Ví dụ:

~~~sql
SELECT *
FROM nhan_vien
WHERE NVL(ma_phong, 0) = :ma_phong;
~~~

Cột MA_PHONG được bọc trong NVL. Một index B-tree thông thường trên MA_PHONG có thể không được dùng theo cách truy cập trực tiếp như MA_PHONG = :ma_phong, vì biểu thức cần so sánh là NVL(MA_PHONG,0).

Nếu nghiệp vụ muốn tìm hàng có MA_PHONG bằng bind, và khi bind bằng 0 thì muốn tìm cả hàng NULL, có thể viết rõ:

~~~sql
SELECT *
FROM nhan_vien
WHERE ma_phong = :ma_phong
   OR (ma_phong IS NULL AND :ma_phong = 0);
~~~

Phải xác nhận 0 không phải mã phòng hợp lệ nếu dùng nó làm giá trị quy ước cho NULL. Câu truy vấn rewrite có thể tạo OR access path hoặc plan khác; không đảm bảo optimizer luôn chọn index.

### 9.1. Function-based index

Nếu workload thường xuyên tìm theo cùng biểu thức NVL và việc này đã được đo lường, có thể cân nhắc function-based index:

~~~sql
CREATE INDEX ix_nv_phong_nvl
ON nhan_vien (NVL(ma_phong, 0));
~~~

Truy vấn phải dùng biểu thức tương thích:

~~~sql
SELECT *
FROM nhan_vien
WHERE NVL(ma_phong, 0) = :ma_phong;
~~~

Cần cân nhắc:
- 0 có thể xung đột với giá trị phòng thực tế hay không.
- Index tăng dung lượng và chi phí INSERT/UPDATE/DELETE.
- Biểu thức query có khớp với biểu thức index không.
- Quyền và thiết lập cần thiết cho function-based index.
- Execution plan thực tế có cải thiện không.

Không tạo function-based index chỉ vì thấy NVL trong một câu SQL. Đo workload và plan trước.

### 9.2. NULL trong B-tree index

Một B-tree index đơn cột của Oracle thường không lưu entry cho hàng mà giá trị cột index hoàn toàn NULL. Composite index có thể vẫn có entry nếu ít nhất một thành phần key không NULL. Vì vậy, không suy luận rằng mọi index đều có thể tìm NULL giống nhau hoặc mọi truy vấn IS NULL đều bắt buộc full scan.

Cấu trúc index, predicate, số hàng NULL và optimizer statistics quyết định access path.

## 10. Lựa chọn hàm theo tình huống nghiệp vụ

| Nhu cầu | Hàm thường phù hợp | Ví dụ |
| --- | --- | --- |
| Thay một cột NULL bằng giá trị mặc định | NVL | NVL(thuong, 0) |
| Chọn một nhãn theo việc cột có NULL hay không | NVL2 | NVL2(ngay_nghi, 'Da nghi', 'Dang lam') |
| Chọn giá trị đầu tiên có dữ liệu từ nhiều nguồn | COALESCE | COALESCE(email_cong_ty, email_ca_nhan, email_khac) |
| Biến một giá trị sentinel thành NULL | NULLIF | NULLIF(diem, 0) |
| Tránh mẫu số bằng 0 | NULLIF | doanh_thu / NULLIF(so_don, 0) |
| Thay kết quả tổng hợp NULL ở đầu ra | NVL/COALESCE | COALESCE(SUM(tien), 0) |
| Nhiều điều kiện phức tạp, mỗi nhánh có logic riêng | CASE | Phân loại nhiều trạng thái |
| Cần kiểm soát kiểu kết quả | CAST kết hợp với các hàm | COALESCE(CAST(a AS NUMBER(12,2)), CAST(b AS NUMBER(12,2))) |

### 10.1. Khi nào nên dùng CASE?

CASE phù hợp khi điều kiện không chỉ là NULL:

~~~sql
SELECT ma_nhan_vien,
       CASE
           WHEN ngay_nghi IS NULL THEN 'DANG LAM'
           WHEN ngay_nghi < DATE '2024-01-01' THEN 'DA NGHI TRUOC 2024'
           ELSE 'DA NGHI TU 2024'
       END AS nhom_trang_thai
FROM nhan_vien;
~~~

CASE cho phép nhiều nhánh, điều kiện kết hợp và kiểu kết quả có thể được xác định rõ. NVL2 chỉ kiểm tra NULL/không NULL của một biểu thức; COALESCE chỉ tìm giá trị không NULL đầu tiên.

## 11. Bộ dữ liệu mẫu để thực hành

Chạy các câu lệnh trong một schema sandbox có quyền tạo bảng. Bộ dữ liệu cố ý có NULL, số 0, chuỗi rỗng và giá trị bình thường để thấy sự khác nhau giữa các hàm.

### 11.1. Tạo bảng

~~~sql
CREATE TABLE nhan_vien_null_demo (
    ma_nv       NUMBER(6)
        CONSTRAINT pk_nv_null_demo PRIMARY KEY,
    ho_ten      VARCHAR2(100 CHAR) NOT NULL,
    thuong      NUMBER(12,2),
    diem        NUMBER(5,2),
    email_cty   VARCHAR2(150 CHAR),
    email_cn    VARCHAR2(150 CHAR),
    ngay_nghi   DATE,
    so_don      NUMBER(8)
);
~~~

### 11.2. Nạp dữ liệu

~~~sql
INSERT INTO nhan_vien_null_demo
VALUES (101, 'An', 2500000, 9.50, 'an@congty.test',
        'an.ca.nhan@test', NULL, 5);

INSERT INTO nhan_vien_null_demo
VALUES (102, 'Binh', NULL, 0, NULL,
        'binh@test', DATE '2024-02-01', 0);

INSERT INTO nhan_vien_null_demo
VALUES (103, 'Chi', 0, NULL, NULL,
        NULL, NULL, NULL);

INSERT INTO nhan_vien_null_demo
VALUES (104, 'Dung', 1250000, 7.25, 'dung@congty.test',
        NULL, DATE '2023-12-31', 2);

INSERT INTO nhan_vien_null_demo
VALUES (105, 'Giang', NULL, NULL, '', '',
        NULL, 0);

COMMIT;
~~~

Trong Oracle, hai giá trị '' ở hàng 105 được lưu/diễn giải như NULL đối với VARCHAR2. Dữ liệu phân biệt:
- THUONG NULL với THUONG = 0.
- DIEM NULL với DIEM = 0.
- EMAIL NULL và EMAIL có chuỗi thực.
- SO_DON NULL với SO_DON = 0.

### 11.3. Thay NULL bằng 0 bằng NVL

~~~sql
SELECT ma_nv,
       ho_ten,
       thuong,
       NVL(thuong, 0) AS thuong_hien_thi
FROM nhan_vien_null_demo
ORDER BY ma_nv;
~~~

Hàng 102 và 105 có THUONG NULL nên hiển thị 0. Hàng 103 vốn có THUONG = 0 cũng hiển thị 0, nhưng nguồn dữ liệu của hai trường hợp khác nhau. Nếu báo cáo cần phân biệt chưa có dữ liệu và giá trị bằng 0, không nên chỉ xuất cột NVL đã thay thế.

### 11.4. Chọn email đầu tiên có dữ liệu bằng COALESCE

~~~sql
SELECT ma_nv,
       COALESCE(
           email_cty,
           email_cn,
           'Chua co email'
       ) AS email_lien_he
FROM nhan_vien_null_demo
ORDER BY ma_nv;
~~~

- Hàng 101 chọn email công ty.
- Hàng 102 chọn email cá nhân.
- Hàng 103 và 105 trả chuỗi mặc định.
- Hàng 104 chọn email công ty.

### 11.5. Phân loại ngày nghỉ bằng NVL2

~~~sql
SELECT ma_nv,
       NVL2(ngay_nghi,
            'DA NGHI',
            'DANG LAM') AS trang_thai
FROM nhan_vien_null_demo
ORDER BY ma_nv;
~~~

Hàng có NGAY_NGHI NULL được phân loại DANG LAM; hàng 102 và 104 có ngày nghỉ nên được phân loại DA NGHI.

### 11.6. Biến điểm 0 thành NULL bằng NULLIF

~~~sql
SELECT ma_nv,
       diem,
       NULLIF(diem, 0) AS diem_sau_nullif
FROM nhan_vien_null_demo
ORDER BY ma_nv;
~~~

- Hàng 101 giữ 9.50.
- Hàng 102 có điểm 0 nên kết quả NULL.
- Hàng 103 và 105 vốn NULL nên vẫn NULL.
- Hàng 104 giữ 7.25.

Chỉ dùng cách biến 0 thành NULL nếu quy ước dữ liệu định nghĩa 0 là chưa chấm. Nếu 0 là điểm hợp lệ, truy vấn sẽ làm sai dữ liệu.

### 11.7. Chia an toàn với NULLIF

~~~sql
SELECT ma_nv,
       thuong,
       so_don,
       thuong / NULLIF(so_don, 0) AS thuong_moi_don
FROM nhan_vien_null_demo
ORDER BY ma_nv;
~~~

Với hàng 102 và 105, SO_DON = 0 nên mẫu số thành NULL và kết quả không phát sinh lỗi chia cho 0. Hàng 103 có cả THUONG và SO_DON NULL, kết quả cũng NULL. Hàng 101 có 2.500.000 / 5 = 500.000.

### 11.8. So sánh COALESCE và NVL trên kết quả tổng hợp

~~~sql
SELECT SUM(thuong) AS tong_thuong,
       NVL(SUM(thuong), 0) AS tong_thuong_nvl,
       COALESCE(SUM(thuong), 0) AS tong_thuong_coalesce
FROM nhan_vien_null_demo;
~~~

Trong tập dữ liệu này tổng thưởng bằng 3.750.000; cả NVL và COALESCE đều trả cùng giá trị vì SUM không NULL.

Để thấy khác biệt khi không có giá trị để cộng, có thể lọc một tập rỗng:

~~~sql
SELECT SUM(thuong) AS tong_thuong,
       NVL(SUM(thuong), 0) AS tong_thuong_hien_thi
FROM nhan_vien_null_demo
WHERE ma_nv < 0;
~~~

SUM trả NULL vì không có hàng; NVL thay kết quả thành 0.

### 11.9. Kiểm tra kiểu kết quả

Có thể xem thông tin kiểu/biểu diễn của biểu thức qua DUMP trong môi trường thực hành:

~~~sql
SELECT DUMP(NVL(CAST(NULL AS NUMBER), 10)) AS dump_nvl_number,
       DUMP(COALESCE(CAST(NULL AS NUMBER), 10)) AS dump_coalesce_number,
       DUMP(NVL2(CAST(NULL AS NUMBER), 10, 20)) AS dump_nvl2_number
FROM dual;
~~~

DUMP hiển thị thông tin kiểu nội bộ và biểu diễn byte của giá trị. Kết quả cụ thể phụ thuộc kiểu dữ liệu của biểu thức; không dùng chuỗi DUMP làm API trao đổi dữ liệu.

### 11.10. Dọn bảng sandbox

~~~sql
DROP TABLE nhan_vien_null_demo PURGE;
~~~

Chỉ xóa bảng thực hành do bài này tạo khi chắc chắn không cần giữ dữ liệu. DROP TABLE là DDL có quy tắc implicit commit; PURGE bỏ qua recycle bin theo hành vi thông thường.

## 12. JDBC và kiểu dữ liệu trả về

Các hàm NULL thường xuất hiện trong SELECT mà ứng dụng Java đọc qua JDBC. Điều quan trọng là **kiểu Oracle của biểu thức quyết định kiểu dữ liệu JDBC quan sát được**, không chỉ kiểu Java mà lập trình viên mong muốn.

### 12.1. Đọc một giá trị NUMBER có thể NULL

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class NhanVienRepository {
    private final DataSource dataSource;

    public NhanVienRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public BigDecimal layThuong(long maNv) throws SQLException {
        String sql = """
            SELECT thuong
            FROM nhan_vien_null_demo
            WHERE ma_nv = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, maNv);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }
                return rs.getBigDecimal("THUONG");
            }
        }
    }
}
~~~

getBigDecimal trả Java null khi SQL NULL. Đây là cách giữ nguyên trạng thái chưa có giá trị. Nếu query dùng NVL(thuong, 0), Java sẽ nhận số 0 thay vì null; tầng ứng dụng không còn phân biệt được hai trạng thái chỉ qua cột kết quả đó.

### 12.2. Đọc kết quả đã thay NULL

~~~java
String sql = """
    SELECT NVL(thuong, 0) AS thuong_hien_thi
    FROM nhan_vien_null_demo
    WHERE ma_nv = ?
    """;
~~~

Kết quả có kiểu số theo quy tắc NVL; dùng getBigDecimal("THUONG_HIEN_THI") nếu cần độ chính xác số tiền. Không dùng getString rồi parse ngược nếu có thể đọc trực tiếp kiểu số.

### 12.3. Phân biệt NULL với 0 khi đọc primitive

Với JDBC, các getter primitive như getInt() có thể trả 0 khi cột NULL. Phải gọi wasNull() ngay sau getter để phân biệt:

~~~java
int soDon = rs.getInt("SO_DON");
boolean soDonBiNull = rs.wasNull();

if (soDonBiNull) {
    // Chưa biết số đơn.
} else {
    // Có số đơn, kể cả giá trị 0.
}
~~~

Hoặc dùng kiểu object như getObject với kiểu tương thích driver/phiên bản, hoặc getBigDecimal cho số. Đừng coi primitive 0 là bằng chứng database lưu 0.

### 12.4. Bind giá trị thay thế với kiểu rõ ràng

~~~java
String sql = """
    SELECT COALESCE(email_cty, email_cn, ?) AS email_lien_he
    FROM nhan_vien_null_demo
    WHERE ma_nv = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "Chua co email");
    ps.setLong(2, maNv);
    // Thực thi và đọc kết quả...
}
~~~

Bind variable giữ dữ liệu đầu vào tách khỏi SQL text. Tuy nhiên, vẫn cần bảo đảm các đối số COALESCE tương thích kiểu; nếu đối số cuối là chuỗi mà các cột trước thuộc kiểu khác, cần CAST hoặc chuyển đổi rõ ràng.

### 12.5. Không ghép chuỗi người dùng vào biểu thức SQL

Không xây câu SQL bằng cách nối trực tiếp giá trị người dùng vào NVL/COALESCE/NULLIF. Dùng PreparedStatement cho giá trị. Tên cột hoặc tên hàm không thể bind bằng dấu ?; nếu ứng dụng cho phép chọn cột, phải ánh xạ qua danh sách cho phép.

## 13. Ảnh hưởng đến hiệu năng và khả năng bảo trì

Các hàm NVL, NVL2, COALESCE và NULLIF thường nhẹ, nhưng cách đặt chúng có thể ảnh hưởng optimizer, index, chuyển đổi kiểu và khả năng đọc của SQL.

### 13.1. Tránh hàm trên cột trong predicate nếu không cần

Ví dụ:

~~~sql
WHERE NVL(ma_phong, 0) = 10
~~~

khác với:

~~~sql
WHERE ma_phong = 10
~~~

Nếu mục tiêu chỉ là tìm MA_PHONG bằng 10, không cần NVL. Việc bọc cột bằng hàm có thể làm index thường không được sử dụng theo cách mong đợi.

### 13.2. Không thay NULL bằng sentinel tùy tiện

Dùng 0, -1, DATE '1900-01-01' hoặc chuỗi N/A làm giá trị thay thế có thể gây va chạm với dữ liệu thật. Nếu sentinel xuất hiện hợp lệ trong tương lai, các biểu thức NVL/NULLIF/COALESCE có thể nhập nhằng trạng thái.

Ưu tiên giữ NULL nếu nó mang nghĩa riêng. Chỉ thay bằng giá trị mặc định ở ranh giới trình bày hoặc khi quy tắc nghiệp vụ đã định nghĩa rõ.

### 13.3. Tránh implicit conversion phụ thuộc NLS

~~~sql
NVL(ngay_tao, '01/01/2024')
~~~

có thể phụ thuộc NLS_DATE_FORMAT. Dùng DATE literal hoặc TO_DATE với format tường minh.

Tương tự, chuyển số thành chuỗi hoặc ngược lại có thể phụ thuộc định dạng số theo session. CAST và bind đúng kiểu giúp kết quả ổn định hơn.

### 13.4. COALESCE có short-circuit, nhưng không dùng để che mọi lỗi

COALESCE không đánh giá các đối số sau khi đã tìm thấy giá trị không NULL đầu tiên. Tuy vậy, không nên viết các hàm có side effect hoặc phụ thuộc thứ tự đánh giá để thực hiện cập nhật, ghi log hoặc điều khiển transaction trong biểu thức SQL. SQL nên biểu diễn tính toán; side effect nên nằm ở thủ tục/ứng dụng có luồng điều khiển rõ ràng.

### 13.5. Xem execution plan thay vì đoán

~~~sql
EXPLAIN PLAN FOR
SELECT ma_nv
FROM nhan_vien
WHERE NVL(ma_phong, 0) = 10;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Plan có thể hiển thị full table scan, index access hoặc function-based index tùy dữ liệu, index và thống kê. EXPLAIN PLAN là ước lượng; khi cần phân tích production, xem cursor plan và runtime statistics theo quyền được cấp.

## 14. Những nhầm lẫn thường gặp

**NVL và COALESCE luôn hoàn toàn giống nhau.** Không đúng. COALESCE nhận nhiều đối số và có short-circuit được tài liệu hóa; NVL có quy tắc chuyển đổi kiểu riêng.

**NVL2 trả expr1 nếu expr1 không NULL.** Không đúng. NVL2 dùng expr1 làm điều kiện, trả expr2 hoặc expr3.

**COALESCE chọn giá trị lớn nhất hoặc mới nhất.** Không đúng. Hàm chọn đối số đầu tiên không NULL theo thứ tự đã viết.

**NULLIF(a,b) trả b nếu a khác b.** Không đúng. Khi khác, NULLIF trả expr1.

**0 và NULL là một.** Không đúng. 0 là một giá trị số xác định; NULL là không có giá trị theo mô hình.

**Chuỗi rỗng luôn khác NULL trong Oracle.** Không đúng với chuỗi độ dài bằng 0 của VARCHAR2; Oracle coi chuỗi rỗng là NULL. Chuỗi toàn dấu cách vẫn là giá trị không NULL.

**NVL(col, '0') luôn trả VARCHAR2.** Không đúng. Kiểu kết quả chịu quy tắc chuyển đổi của đối số đầu và kiểu số/kiểu dữ liệu tương ứng.

**Chỉ cần hàng đầu tiên không NULL thì các đối số sau có thể sai kiểu.** Không đúng. Oracle vẫn phải phân tích và xác định kiểu của toàn biểu thức.

**AVG(NVL(col,0)) giống NVL(AVG(col),0).** Không đúng. Cách thứ nhất có thể đưa hàng NULL vào mẫu số dưới dạng 0; cách thứ hai chỉ thay kết quả tổng hợp NULL.

**NVL trong WHERE không ảnh hưởng index.** Không đúng. Hàm trên cột có thể làm thay đổi access path; cần xem plan và có thể cân nhắc function-based index.

**getInt() trả 0 nghĩa là database có số 0.** Không đúng. JDBC primitive getter có thể trả 0 cho SQL NULL; dùng wasNull() hoặc kiểu object.

**NULLIF luôn giải quyết mọi lỗi chia cho 0.** Nó giúp khi mẫu số được so sánh với 0 và kiểu dữ liệu tương thích; vẫn cần kiểm tra logic phép tính và kiểu kết quả.

## 15. Quy trình chọn hàm

Khi viết biểu thức xử lý NULL, hãy đi theo thứ tự:

1. Xác định NULL có nghĩa gì: chưa biết, chưa nhập, không áp dụng hay được quy ước thay bằng giá trị khác?
2. Nếu chỉ cần thay một giá trị NULL, cân nhắc NVL.
3. Nếu muốn trả một trong hai kết quả tùy expr1 có NULL không, dùng NVL2.
4. Nếu có nhiều nguồn dự phòng theo thứ tự ưu tiên, dùng COALESCE.
5. Nếu cần biến một giá trị sentinel hoặc mẫu số 0 thành NULL, dùng NULLIF.
6. Nếu logic có nhiều điều kiện nghiệp vụ, dùng CASE.
7. Kiểm tra kiểu dữ liệu kết quả; CAST các đối số khi cần.
8. Kiểm tra chuỗi rỗng, NLS và implicit conversion.
9. Nếu hàm nằm trong WHERE hoặc JOIN, xem ảnh hưởng index và execution plan.
10. Ở JDBC, giữ trạng thái SQL NULL khi cần; không để primitive getter làm mất khác biệt giữa NULL và 0.

## 16. Bài tập tự luyện

1. Viết truy vấn thay BONUS NULL bằng 0 bằng NVL, sau đó giải thích vì sao BONUS = 0 và BONUS IS NULL vẫn khác nhau.
2. Dùng NVL2 để phân loại khách hàng đã có EMAIL và chưa có EMAIL. Nếu EMAIL là chuỗi rỗng trong Oracle, kết quả thuộc nhánh nào?
3. Viết COALESCE chọn số điện thoại công ty, số cá nhân, số dự phòng, rồi cuối cùng là chuỗi mặc định.
4. Giải thích vì sao đổi thứ tự hai đối số đầu của COALESCE có thể đổi kết quả.
5. Dùng NULLIF để biến số lượng bằng 0 thành NULL trước khi tính đơn giá trung bình.
6. Cho biết kiểu kết quả có thể là gì trong NVL(varchar2_col, 0) và NVL(number_col, '0').
7. Viết lại biểu thức NVL(a,b) bằng CASE. Khi nào nên dùng CASE thay vì NVL?
8. So sánh AVG(score), AVG(NVL(score,0)) và NVL(AVG(score),0) trên tập có một số hàng NULL.
9. Vì sao SUM(NVL(amount,0)) và NVL(SUM(amount),0) có thể khác nhau khi không có hàng?
10. Viết biểu thức tính doanh thu trên đơn hàng an toàn khi số đơn bằng 0 bằng NULLIF.
11. Tại sao NVL(date_col, '01/01/2024') không nên dùng trong hệ thống nhiều NLS session?
12. Dùng CAST để bảo đảm COALESCE của ba cột số trả NUMBER(12,2).
13. Dùng DUMP để quan sát kiểu kết quả của NVL2 với đối số kết quả là NUMBER.
14. Giải thích vì sao NVL(ma_phong,0)=:p có thể làm thay đổi khả năng sử dụng index thông thường.
15. Khi nào function-based index trên NVL(cot, sentinel) có thể hữu ích, và cần kiểm tra điều gì về sentinel?
16. Trong Java, vì sao phải gọi ResultSet.wasNull() sau getInt() nếu cần phân biệt NULL với 0?
17. Một cột điểm có giá trị 0 hợp lệ. Vì sao NULLIF(diem,0) có thể làm sai báo cáo?
18. Thiết kế biểu thức COALESCE cho ngày kích hoạt, ngày nhập dữ liệu và ngày mặc định; xác định kiểu kết quả và thứ tự ưu tiên.
19. Một query trả NUMBER ở cột gốc nhưng VARCHAR2 sau NVL. Điều gì có thể xảy ra với code JDBC đang gọi getBigDecimal?
20. Với dữ liệu chưa biết, vì sao giữ NULL ở tầng lưu trữ có thể tốt hơn thay bằng một sentinel rồi chuyển lại ở mọi câu SQL?

**NVL, NVL2, COALESCE và NULLIF đều xử lý NULL nhưng có mục tiêu khác nhau.** Khi chọn đúng hàm, hiểu quy tắc chuyển đổi kiểu và giữ sự khác biệt giữa NULL với 0/chuỗi rỗng, biểu thức SQL sẽ rõ nghĩa hơn. Với ứng dụng Oracle, cần kiểm tra cả kết quả, datatype, tác động đến index và cách JDBC đọc NULL để dữ liệu không bị thay đổi ý nghĩa giữa database và tầng Java.
