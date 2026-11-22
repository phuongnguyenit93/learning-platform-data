# Phân biệt quan hệ toán học với bảng SQL có phần tử trùng hoặc NULL

## Mục tiêu bài học

Mô hình quan hệ là nền tảng toán học quan trọng cho việc thiết kế cơ sở dữ liệu. Tuy nhiên, câu nói “một bảng SQL là một quan hệ” chỉ đúng khi chấp nhận một số giản lược: **quan hệ trong mô hình cổ điển là một tập bộ**, còn **SQL thường xử lý dữ liệu theo ngữ nghĩa đa tập và cho phép giá trị NULL**. Hai khác biệt này tác động trực tiếp đến cách đọc kết quả truy vấn, thiết lập khóa, đếm dữ liệu và thực thi quy tắc nghiệp vụ.

Sau bài học, bạn có thể:

1. Giải thích tại sao quan hệ toán học không chứa bộ trùng, trong khi bảng hoặc kết quả truy vấn SQL có thể có dòng trùng.
2. Dự đoán kết quả của **SELECT**, **SELECT DISTINCT**, **GROUP BY**, **COUNT**, **JOIN** và **UNION ALL** khi dữ liệu có phần tử trùng.
3. Giải thích **NULL** và logic ba giá trị **TRUE / FALSE / UNKNOWN**, bao gồm hệ quả khi lọc dữ liệu và kiểm tra ràng buộc.
4. Phân biệt cách xử lý NULL trong **so sánh**, **DISTINCT**, **GROUP BY**, **UNIQUE**, **PRIMARY KEY** và **FOREIGN KEY**.
5. Áp dụng các khác biệt đó khi chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu quan hệ rõ ràng, dễ tiến hóa và kiểm chứng.

**Phạm vi:** Bài thuộc chương **Mô hình quan hệ** của module **DATABASE_DATA_MODELING**. Trong quá trình chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, ràng buộc, khóa, chỉ mục và lược đồ vật lý, cần tách bạch **ngữ nghĩa logic của dữ liệu** với **hành vi thực tế của SQL**. Hiểu điều này cũng là tiền đề để so sánh cách biểu diễn dữ liệu trong mô hình quan hệ, document, đồ thị và hệ thống phân tích.

## 1. Quan hệ toán học: tập các bộ, không có phần tử trùng

Trong mô hình quan hệ cổ điển, một **lược đồ quan hệ** gồm tên quan hệ, các thuộc tính và miền giá trị tương ứng:

\[
R(A_1:D_1, A_2:D_2, \ldots, A_n:D_n)
\]

Một **trạng thái quan hệ** tại thời điểm đang xét là một tập bộ:

\[
r(R) \subseteq D_1 \times D_2 \times \cdots \times D_n
\]

Mỗi bộ gán một giá trị thuộc miền tương ứng cho từng thuộc tính. Ký hiệu tích Descartes là cách biểu diễn hình thức; ý nghĩa của từng giá trị luôn gắn với tên thuộc tính trong lược đồ.

Ba tính chất cần nhớ:

- **Không trùng bộ:** Tập hợp không lưu cùng một phần tử hai lần. Nếu hai bộ có giá trị bằng nhau trên **mọi thuộc tính**, chúng là một bộ, không phải hai bộ khác nhau.
- **Không có thứ tự bộ:** Tập các bộ không có “bộ đầu tiên” hay “bộ cuối cùng” theo ý nghĩa của mô hình.
- **Không có NULL kiểu SQL trong mô hình cổ điển:** Mỗi vị trí thuộc tính chứa giá trị xác định thuộc miền của thuộc tính. Việc biểu diễn thiếu dữ liệu phải được thiết kế thêm; NULL của SQL là cơ chế riêng, không mặc nhiên thuộc lý thuyết quan hệ cổ điển.

Ví dụ, xét quan hệ toán học chỉ có một thuộc tính **mã loại sản phẩm**:

\[
LOAI = \{(10), (20)\}
\]

Viết thêm phần tử **(10)** lần nữa vẫn không tạo thành quan hệ có ba bộ. Quan hệ là tập nên giá trị **(10)** chỉ xuất hiện một lần.

Trong mô hình này, **bậc** của quan hệ là số thuộc tính; **lực lượng** là số bộ. Với ví dụ trên, bậc bằng 1 và lực lượng bằng 2. Khái niệm này khác với cách dùng “cardinality” để chỉ liên kết 1–1, 1–N hay N–N khi thiết kế thực thể.

### Tại sao quan hệ phải có khả năng định danh bộ?

Vì không có hai bộ giống hệt nhau, **toàn bộ tập thuộc tính** luôn đủ để phân biệt các bộ trong một quan hệ toán học. Trong thiết kế tốt, ta thường cần khóa nhỏ hơn: **khóa ứng viên** là tập thuộc tính tối thiểu mà giá trị của nó phân biệt mọi bộ trong tất cả trạng thái hợp lệ.

Ví dụ, đối với quan hệ **KHACH_HANG(ma_kh, ten, email)**, nếu **ma_kh** là mã định danh ổn định và duy nhất, ta chọn **ma_kh** làm khóa chính. Hai người có thể cùng tên **An**, nhưng không được cùng **ma_kh**.

## 2. Bảng SQL và kết quả truy vấn: thường là đa tập

SQL được lấy cảm hứng từ mô hình quan hệ nhưng có những quy tắc vận hành khác. **Đa tập** (*bag* hoặc *multiset*) cho phép một phần tử xuất hiện nhiều lần; mỗi phần tử có một **số lần xuất hiện** (*multiplicity*).

Ví dụ, đa tập:

\[
B = \{\!\{10, 10, 20\}\!\}
\]

chứa ba lần xuất hiện, trong đó giá trị 10 xuất hiện hai lần. Dấu ngoặc kép nhấn mạnh đây là **đa tập**, không phải tập toán học **{10, 20}**.

Trong SQL:

- Bảng cơ sở có thể chứa hai dòng trùng trên toàn bộ cột **nếu không có ràng buộc ngăn trùng**.
- Một bảng có **PRIMARY KEY** không thể chứa hai dòng giống nhau trên mọi cột vì chúng sẽ phải trùng khóa chính. Tuy vậy, **kết quả SELECT** từ bảng đó vẫn có thể trùng sau khi chỉ chọn một số cột hoặc sau khi kết nối.
- **SELECT** mặc định giữ các lần xuất hiện trùng; **SELECT DISTINCT** loại các dòng trùng của kết quả.
- Không thể dựa vào thứ tự hiển thị nếu không có **ORDER BY**, kể cả khi hệ quản trị thường trả ra một thứ tự quen thuộc.

Ví dụ SQL độc lập:

~~~~sql
CREATE TABLE ma_nhap_thu (
    ma INTEGER
);

INSERT INTO ma_nhap_thu (ma)
VALUES (10), (10), (20);

SELECT ma FROM ma_nhap_thu;
-- Có ba dòng: 10, 10, 20.

SELECT DISTINCT ma FROM ma_nhap_thu;
-- Có hai giá trị: 10, 20.
~~~~

Khác biệt ở đây không phải là SQL “lưu sai”; bảng **ma_nhap_thu** chưa khai báo quy tắc nào cấm trùng. Nếu một nghiệp vụ yêu cầu mã duy nhất, phải diễn đạt bằng khóa hoặc ràng buộc phù hợp, thay vì mong SQL tự suy ra ý định.

## 3. Bộ dữ liệu xuyên suốt: khách hàng và đơn hàng

Để quan sát đồng thời dòng trùng và NULL, ta dùng hai bảng. Quy tắc nghiệp vụ giả định:

- Mỗi khách hàng có một **ma_kh** duy nhất, tên bắt buộc.
- Email có thể chưa được cung cấp; **nếu được cung cấp thì phải duy nhất**.
- Mỗi đơn hàng có một **ma_dh** duy nhất, thuộc đúng một khách hàng.
- Đơn hàng có tổng tiền không âm và có thể không dùng mã ưu đãi.

Các câu lệnh dưới đây dùng cú pháp **PostgreSQL**; có thể chạy tuần tự trên một cơ sở dữ liệu thử nghiệm.

~~~~sql
CREATE TABLE khach_hang (
    ma_kh INTEGER PRIMARY KEY,
    ten VARCHAR(80) NOT NULL,
    email VARCHAR(254) UNIQUE
);

CREATE TABLE don_hang (
    ma_dh INTEGER PRIMARY KEY,
    ma_kh INTEGER NOT NULL REFERENCES khach_hang(ma_kh),
    tong_tien NUMERIC(12, 2) NOT NULL CHECK (tong_tien >= 0),
    ma_uu_dai VARCHAR(20)
);

INSERT INTO khach_hang (ma_kh, ten, email) VALUES
    (1, 'An',   NULL),
    (2, 'Bình', 'binh@example.com'),
    (3, 'Chi',  NULL),
    (4, 'An',   'an@example.com');

INSERT INTO don_hang (ma_dh, ma_kh, tong_tien, ma_uu_dai) VALUES
    (101, 1, 500000, NULL),
    (102, 1, 200000, 'SALE10'),
    (103, 2, 200000, NULL),
    (104, 3, 500000, 'SALE10');
~~~~

**Khách hàng:**

| ma_kh | ten | email |
| ---: | --- | --- |
| 1 | An | NULL |
| 2 | Bình | binh@example.com |
| 3 | Chi | NULL |
| 4 | An | an@example.com |

**Đơn hàng:**

| ma_dh | ma_kh | tong_tien | ma_uu_dai |
| ---: | ---: | ---: | --- |
| 101 | 1 | 500000 | NULL |
| 102 | 1 | 200000 | SALE10 |
| 103 | 2 | 200000 | NULL |
| 104 | 3 | 500000 | SALE10 |

Hai khách hàng cùng tên **An** không phải bản ghi trùng, vì **ma_kh** khác nhau. Tương tự, hai đơn hàng có **tong_tien = 200000** là hai sự kiện khác nhau dù cùng giá trị tiền.

> **Quy ước trình bày:** Các bảng kết quả trong bài được sắp xếp để dễ đọc. Khi viết truy vấn thực tế, cần thêm **ORDER BY** nếu người dùng hoặc chương trình cần một thứ tự xác định.

## 4. Trùng dữ liệu xuất hiện khi chiếu và kết nối

### 4.1. Phép chiếu trong đại số quan hệ và SELECT trong SQL

Phép **chiếu** (*projection*) của đại số quan hệ lấy một tập thuộc tính từ các bộ đầu vào. Vì đầu ra vẫn là một **tập**, các bộ trùng sau phép chiếu được loại bỏ.

\[
\pi_{ten}(KHACH\_HANG) = \{(An), (Bình), (Chi)\}
\]

Nhưng câu SQL:

~~~~sql
SELECT ten
FROM khach_hang
ORDER BY ten;
~~~~

cho ra **bốn dòng**: **An, An, Bình, Chi**. Bản chất SELECT thông thường là phép chọn cột **giữ số lần xuất hiện**. Muốn ngữ nghĩa giống phép chiếu theo tập:

~~~~sql
SELECT DISTINCT ten
FROM khach_hang
ORDER BY ten;
-- Ba dòng: An, Bình, Chi.
~~~~

Lưu ý, **DISTINCT xét toàn bộ các cột trong danh sách SELECT**, không chỉ một cột được nhắc tên đầu tiên:

~~~~sql
SELECT DISTINCT ma_kh, ten
FROM khach_hang
ORDER BY ma_kh;
-- Vẫn có bốn dòng vì mỗi ma_kh là một giá trị khác nhau.
~~~~

Sự tồn tại của hai dòng cùng tên **An** hoàn toàn hợp lệ nếu nghiệp vụ cho phép trùng tên. **Dòng trùng theo cột được chọn** không có nghĩa là **bản ghi nghiệp vụ bị nhân đôi**.

### 4.2. Đếm số lần xuất hiện

~~~~sql
SELECT ma_kh, COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_kh
ORDER BY ma_kh;
~~~~

| ma_kh | so_don |
| ---: | ---: |
| 1 | 2 |
| 2 | 1 |
| 3 | 1 |

Khách hàng 1 có hai đơn; việc giữ hai lần xuất hiện của **ma_kh = 1** là cần thiết để đếm chính xác. Nếu áp dụng **DISTINCT ma_kh** trước khi đếm đơn, sẽ đánh mất số lượng đơn thực tế. Vì vậy, không phải mọi kết quả trùng đều cần bị loại bỏ.

### 4.3. JOIN có thể tăng số dòng

~~~~sql
SELECT kh.ma_kh, kh.ten, dh.ma_dh
FROM khach_hang AS kh
JOIN don_hang AS dh ON dh.ma_kh = kh.ma_kh
ORDER BY kh.ma_kh, dh.ma_dh;
~~~~

| ma_kh | ten | ma_dh |
| ---: | --- | ---: |
| 1 | An | 101 |
| 1 | An | 102 |
| 2 | Bình | 103 |
| 3 | Chi | 104 |

Tên **An** lặp hai lần bởi một khách hàng có hai đơn. Nếu chỉ chiếu **ten** từ kết quả JOIN, ta sẽ thấy **An, An, Bình, Chi**. Đây là lặp do **bậc liên kết 1–N**, không phải hai khách hàng bị nhân bản.

Trong tổng quát, nếu một giá trị khóa nối xuất hiện **m** lần bên trái và **n** lần bên phải, kết nối thông thường có thể tạo **m × n** cặp khớp cho giá trị đó. Điều này đặc biệt quan trọng khi báo cáo tài chính hoặc phân tích dữ liệu:

- Giả sử đơn 101 có tổng tiền **500000** và hai dòng chi tiết.
- JOIN đơn với chi tiết sẽ tạo hai dòng cùng mang **don_hang.tong_tien = 500000**.
- **SUM(don_hang.tong_tien)** ngay sau JOIN có thể đếm đơn 101 thành **1000000**, dù tổng thực chỉ **500000**.

Không nên “chữa” lỗi này bằng **SUM(DISTINCT don_hang.tong_tien)**: hai đơn khác nhau có thể thật sự cùng tổng tiền và sẽ bị cộng thiếu. Cần xác định rõ **độ hạt** (*grain*) của dữ liệu, chẳng hạn “một dòng là một đơn hàng”, rồi tổng hợp ở đúng mức trước hoặc sau JOIN.

### 4.4. UNION và UNION ALL

Trong SQL, **UNION** mặc định loại trùng trên kết quả gộp, còn **UNION ALL** giữ lại tất cả lần xuất hiện.

~~~~sql
SELECT ma_kh FROM don_hang WHERE ma_dh <= 102
UNION
SELECT ma_kh FROM don_hang WHERE ma_dh >= 102;
-- Các giá trị: 1, 2, 3 (mỗi giá trị một lần).

SELECT ma_kh FROM don_hang WHERE ma_dh <= 102
UNION ALL
SELECT ma_kh FROM don_hang WHERE ma_dh >= 102;
-- Năm dòng: giá trị 1 xuất hiện ba lần; 2 và 3 mỗi giá trị một lần.
~~~~

Đơn 102 thuộc **cả hai nhánh**, nên **UNION ALL** đếm thêm một lần. Việc chọn **UNION** hay **UNION ALL** phải dựa trên ý nghĩa nghiệp vụ: đang gộp **tập đối tượng duy nhất** hay ghép **các lần xuất hiện/sự kiện**?

## 5. NULL không phải là một giá trị thông thường

Trong SQL, **NULL** là dấu hiệu không có giá trị xác định tại vị trí đang xét. Nó thường được dùng cho nhiều tình huống:

| Trường hợp | Ví dụ | Câu hỏi thiết kế |
| --- | --- | --- |
| Chưa biết | Chưa có email khách hàng | Có cần phân biệt “chưa thu thập” với “không có” không? |
| Không áp dụng | Đơn không sử dụng mã ưu đãi | NULL có mô tả đúng trường hợp không dùng mã không? |
| Chưa được tính hoặc chưa phát sinh | Chưa có thời điểm giao hàng | Có cần trạng thái giao hàng riêng không? |
| Dữ liệu lỗi hoặc thiếu khi nhập | Bản nhập thiếu trường bắt buộc | Có nên từ chối bản ghi thay vì chấp nhận NULL không? |

Những ý nghĩa này khác nhau về nghiệp vụ dù có thể cùng được lưu bằng NULL. **NULL không đồng nghĩa với số 0, chuỗi rỗng, FALSE hoặc một giá trị mặc định**.

Ví dụ:

- **tong_tien = 0** nói rằng tổng tiền đã xác định bằng không.
- **tong_tien IS NULL** nói rằng không có tổng tiền xác định ở trường đó.
- **ma_uu_dai = ''** là một chuỗi rỗng; tùy yêu cầu, nó có thể phải bị từ chối.
- **ma_uu_dai IS NULL** có thể được chọn để biểu đạt “không áp dụng mã ưu đãi”.

Trong ví dụ xuyên suốt, **ma_uu_dai** cho phép NULL, còn **tong_tien** bắt buộc **NOT NULL**. Điều đó là một **quyết định mô hình hóa**: hệ thống phải tính được tổng tiền trước khi lưu đơn.

## 6. So sánh với NULL và logic ba giá trị

Đại số quan hệ cổ điển xét các giá trị xác định và logic mệnh đề thông thường. SQL lại sử dụng một kết quả logic thứ ba trong nhiều biểu thức: **UNKNOWN** (*không xác định*).

Ví dụ:

~~~~sql
SELECT ma_kh FROM khach_hang WHERE email = NULL;
-- Không trả dòng nào.

SELECT ma_kh FROM khach_hang WHERE email IS NULL
ORDER BY ma_kh;
-- ma_kh = 1, 3.
~~~~

Với toán tử **=** thông thường, cả **NULL = 'an@example.com'** và **NULL = NULL** đều cho **UNKNOWN**. Hai phép kiểm tra trạng thái NULL dùng **IS NULL** và **IS NOT NULL**, trả về TRUE hoặc FALSE.

### 6.1. Bảng chân trị tối thiểu cần nhớ

Gọi **U = UNKNOWN**, **T = TRUE**, **F = FALSE**:

| P | Q | P AND Q | P OR Q |
| --- | --- | --- | --- |
| T | T | T | T |
| T | F | F | T |
| T | U | U | T |
| F | F | F | F |
| F | U | F | U |
| U | U | U | U |

Đối với **NOT**:

| P | NOT P |
| --- | --- |
| T | F |
| F | T |
| U | U |

Hai điểm dễ gây nhầm:

- **FALSE AND UNKNOWN = FALSE**, vì dù vế chưa biết là gì, toàn bộ điều kiện vẫn sai.
- **TRUE OR UNKNOWN = TRUE**, vì chỉ một vế đúng đã đủ để toàn bộ điều kiện đúng.

Mệnh đề **WHERE** chỉ giữ các dòng mà điều kiện có kết quả **TRUE**. Cả **FALSE** và **UNKNOWN** đều không qua bộ lọc.

### 6.2. Tại sao phủ định một điều kiện không thu được toàn bộ phần còn lại?

~~~~sql
SELECT ma_dh
FROM don_hang
WHERE ma_uu_dai = 'SALE10'
ORDER BY ma_dh;
-- 102, 104

SELECT ma_dh
FROM don_hang
WHERE ma_uu_dai <> 'SALE10';
-- Không có dòng nào: hai mã còn lại là NULL nên điều kiện UNKNOWN.
~~~~

Nếu yêu cầu là “tìm đơn **không dùng SALE10**, bao gồm đơn không có mã ưu đãi”, ta phải nói rõ:

~~~~sql
SELECT ma_dh
FROM don_hang
WHERE ma_uu_dai <> 'SALE10'
   OR ma_uu_dai IS NULL
ORDER BY ma_dh;
-- 101, 103
~~~~

Trong PostgreSQL, còn có toán tử so sánh xét NULL như một trường hợp được xác định:

~~~~sql
SELECT ma_dh
FROM don_hang
WHERE ma_uu_dai IS DISTINCT FROM 'SALE10'
ORDER BY ma_dh;
-- 101, 103

SELECT ma_dh
FROM don_hang
WHERE ma_uu_dai IS NOT DISTINCT FROM NULL
ORDER BY ma_dh;
-- 101, 103; tương đương IS NULL trong ví dụ này.
~~~~

**IS DISTINCT FROM** trả về TRUE/FALSE khi có NULL: một NULL khác với giá trị khác NULL, và hai NULL được xét là *không khác nhau* theo phép so sánh này. Không đánh đồng hành vi này với toán tử **=**; khi chuyển SQL giữa các hệ quản trị, hãy kiểm tra hỗ trợ cú pháp và hành vi tương ứng.

## 7. Điều có vẻ nghịch lý: NULL = NULL là UNKNOWN, nhưng DISTINCT vẫn gom NULL

SQL có những phép toán cần xác định dòng nào được xem là **trùng** để loại trùng hoặc chia nhóm. Chúng sử dụng quy tắc riêng: khi xét tính trùng trong **DISTINCT**, **GROUP BY** và các phép tập hợp tương ứng, các NULL ở cùng vị trí được xem là **không phân biệt** với nhau.

### 7.1. DISTINCT với NULL

~~~~sql
SELECT DISTINCT email
FROM khach_hang;
~~~~

Kết quả gồm **ba giá trị hiển thị**: **NULL**, **binh@example.com**, **an@example.com**. Hai dòng khách hàng 1 và 3 có email NULL được gộp thành **một dòng NULL** trong kết quả DISTINCT.

Điều này **không hề nói rằng NULL = NULL cho TRUE**. Đó là hai quy tắc khác nhau:

- Trong biểu thức điều kiện **email = NULL**, kết quả so sánh là **UNKNOWN**.
- Trong phép **loại dòng trùng**, hai dòng chỉ có NULL ở cùng vị trí có thể được xem là không phân biệt.

### 7.2. GROUP BY với NULL

~~~~sql
SELECT ma_uu_dai, COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_uu_dai
ORDER BY ma_uu_dai NULLS LAST;
~~~~

| ma_uu_dai | so_don |
| --- | ---: |
| SALE10 | 2 |
| NULL | 2 |

SQL gom các bản ghi có **ma_uu_dai IS NULL** vào cùng một nhóm để thống kê. Trong bài toán báo cáo, nhóm này có thể được đặt nhãn “Không áp dụng ưu đãi” **nếu đó thực sự là nghĩa nghiệp vụ** của NULL.

### 7.3. COUNT(*) khác COUNT(cột)

~~~~sql
SELECT
    COUNT(*) AS tong_so_khach,
    COUNT(email) AS co_email,
    COUNT(DISTINCT email) AS email_khac_nhau
FROM khach_hang;
~~~~

| tong_so_khach | co_email | email_khac_nhau |
| ---: | ---: | ---: |
| 4 | 2 | 2 |

- **COUNT(*)** đếm tất cả các dòng.
- **COUNT(email)** đếm những dòng mà **email không NULL**.
- **COUNT(DISTINCT email)** đếm các **giá trị email phân biệt và không NULL**.

Đặc biệt, **SELECT DISTINCT email** trả về **ba dòng** (bao gồm một dòng NULL), nhưng **COUNT(DISTINCT email)** trả về **2** vì COUNT không tính NULL. Nhớ rõ hai phép toán này để tránh kết luận sai về số lượng.

Các hàm tổng hợp phổ biến như **SUM**, **AVG**, **MIN**, **MAX** thường bỏ qua các đầu vào NULL; ngoại lệ về cách đếm là **COUNT(*)**, vì nó không tham chiếu cột cụ thể. Nếu không có giá trị khác NULL để tổng hợp, **SUM** trả NULL, còn **COUNT(cột)** trả 0:

~~~~sql
SELECT
    COUNT(ma_uu_dai) AS so_don_co_ma,
    COUNT(DISTINCT ma_uu_dai) AS so_ma_khac_nhau
FROM don_hang;
-- 2, 1
~~~~

Khi dùng **COALESCE** để thay NULL thành một giá trị mặc định, phải biết ý nghĩa dữ liệu: chuyển **chưa biết** thành **0** có thể làm sai thống kê, còn chuyển tổng của tập dòng rỗng thành **0** đôi khi phù hợp với yêu cầu báo cáo.

## 8. NULL trong JOIN, anti-join và NOT IN

### 8.1. INNER JOIN chỉ nối những cặp thỏa điều kiện TRUE

Trong ví dụ, **don_hang.ma_kh** là khóa ngoại **NOT NULL**, nên JOIN bằng mã khách hàng hoạt động trực tiếp. Nếu điều kiện JOIN so sánh hai cột có thể NULL bằng **=**, các dòng có NULL ở hai phía **không** được ghép với nhau: **NULL = NULL** là UNKNOWN, không phải TRUE.

**LEFT JOIN** vẫn giữ những dòng bên trái không tìm được đối tác, và đặt NULL ở các cột của phần bên phải. Vì vậy phải rất cẩn thận khi đếm:

~~~~sql
SELECT
    kh.ma_kh,
    COUNT(*) AS so_dong_sau_join,
    COUNT(dh.ma_dh) AS so_don
FROM khach_hang AS kh
LEFT JOIN don_hang AS dh ON dh.ma_kh = kh.ma_kh
GROUP BY kh.ma_kh
ORDER BY kh.ma_kh;
~~~~

| ma_kh | so_dong_sau_join | so_don |
| ---: | ---: | ---: |
| 1 | 2 | 2 |
| 2 | 1 | 1 |
| 3 | 1 | 1 |
| 4 | 1 | 0 |

Khách hàng 4 **không có đơn** nhưng **COUNT(*) = 1** vì LEFT JOIN vẫn tạo một dòng kết quả cho khách hàng này. Trong khi đó **COUNT(dh.ma_dh) = 0**, vì cột khóa của đơn hàng ở dòng đó là NULL. Đếm bản ghi con bằng khóa không NULL của bảng con là cách thường phù hợp cho bài toán này.

### 8.2. Bẫy NOT IN khi danh sách chứa NULL

~~~~sql
SELECT ma_kh
FROM khach_hang
WHERE ma_kh NOT IN (1, 2, NULL);
-- Không có dòng nào, kể cả khách hàng 3 và 4.
~~~~

Với **ma_kh = 3**, các so sánh “3 khác 1” và “3 khác 2” đều đúng, nhưng so sánh với NULL cho UNKNOWN. Toàn bộ **NOT IN** không đạt TRUE nên dòng bị loại. Trên dữ liệu thật, danh sách của **NOT IN** có thể đến từ truy vấn con và tình cờ chứa NULL.

Nếu muốn tìm khách hàng **chưa từng có đơn hàng**, có thể viết:

~~~~sql
SELECT kh.ma_kh, kh.ten
FROM khach_hang AS kh
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang AS dh
    WHERE dh.ma_kh = kh.ma_kh
)
ORDER BY kh.ma_kh;
-- Kết quả: khách hàng 4, An.
~~~~

**NOT EXISTS** kiểm tra có hay không một dòng phù hợp; nó không mắc đúng bẫy “một giá trị NULL trong danh sách làm kết quả NOT IN thành UNKNOWN”. Dẫu vậy, vẫn phải bảo đảm điều kiện đối sánh trong truy vấn con diễn đạt đúng quy tắc nghiệp vụ.

### 8.3. Sai số do JOIN không phải lúc nào cũng sửa được bằng DISTINCT

Khi một đơn có nhiều dòng chi tiết, JOIN sinh nhiều dòng. Nếu bỏ trùng sau JOIN, ta có thể:

- **Làm mất dữ liệu hợp lệ**, nếu hai dòng hàng cùng mức giá nhưng thực sự khác sản phẩm.
- **Giấu lỗi nối sai khóa**, nếu JOIN tạo ra tổ hợp sai nhưng DISTINCT tình cờ làm giảm số dòng.
- **Đếm sai**, nếu tính COUNT hoặc SUM ở mức độ hạt không đúng.

Quy trình an toàn là xác định trước **một dòng đại diện cho cái gì**, khóa nào đảm bảo tính duy nhất ở mức đó, rồi mới tổng hợp hoặc loại trùng khi có yêu cầu rõ ràng.

## 9. NULL tác động đến khóa và ràng buộc như thế nào?

Thiết kế bảng SQL phải ghi rõ **không trùng ở phạm vi nào**, **cột nào bắt buộc** và **NULL mang ý nghĩa gì**.

### 9.1. PRIMARY KEY luôn cần định danh xác định

Một **PRIMARY KEY** yêu cầu giá trị khóa duy nhất và **không NULL**. Với khóa ghép, không thành phần khóa nào được NULL. Trong ví dụ, **khach_hang.ma_kh** và **don_hang.ma_dh** là các khóa chính.

Điều này phù hợp với mục tiêu định danh bộ trong mô hình quan hệ, nhưng **không đồng nghĩa mọi cột của bảng đều không NULL**: email khách hàng vẫn có thể thiếu.

### 9.2. UNIQUE và NULL là vấn đề phải kiểm tra theo DBMS

Trong **PostgreSQL**, một ràng buộc **UNIQUE** thông thường cho phép nhiều dòng có NULL ở cột được ràng buộc. Vì vậy bảng **khach_hang** chứa hai dòng có email NULL vẫn hợp lệ, dù không cho hai khách hàng cùng email xác định.

~~~~sql
-- Hợp lệ trong ví dụ PostgreSQL vì cả hai email đều NULL:
SELECT ma_kh, email
FROM khach_hang
WHERE email IS NULL
ORDER BY ma_kh;
-- 1, NULL
-- 3, NULL
~~~~

Nếu email là thuộc tính **bắt buộc và duy nhất**, lược đồ cần **NOT NULL UNIQUE**:

~~~~sql
-- Ví dụ cấu trúc thay thế, không chạy trực tiếp
-- trên dữ liệu mẫu đang có email NULL:
CREATE TABLE khach_hang_bat_buoc_email (
    ma_kh INTEGER PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE
);
~~~~

Khi email có thể NULL, **UNIQUE(email)** không tự khiến email trở thành **khóa ứng viên theo nghĩa định danh luôn có giá trị**, vì nhiều dòng có thể thiếu email. Một số hệ quản trị hoặc cấu hình ràng buộc xử lý NULL trong UNIQUE khác nhau; luôn kiểm tra hệ thống đích trước khi suy luận.

### 9.3. FOREIGN KEY và NULL

Một khóa ngoại **có thể cho phép NULL** nếu cột không khai báo NOT NULL. Theo hành vi thông thường của khóa ngoại một cột, **NULL** nghĩa là không phải tìm dòng cha tương ứng để kiểm chứng. Ví dụ, một phiếu hỗ trợ có thể chưa được giao nhân viên xử lý:

~~~~sql
-- Ví dụ minh họa độc lập:
-- phieu_ho_tro.ma_nv_phu_trach có thể NULL,
-- nhưng khi có mã thì phải tham chiếu nhân viên tồn tại.
-- ma_nv_phu_trach INTEGER NULL
--     REFERENCES nhan_vien(ma_nv)
~~~~

Nếu nghiệp vụ nói “mỗi đơn hàng **phải** thuộc một khách hàng”, khóa ngoại đơn thuần chưa đủ; cần **ma_kh NOT NULL REFERENCES khach_hang(ma_kh)** như DDL đã viết.

Đối với khóa ngoại ghép, cách xử lý khi **một vài thành phần NULL** phụ thuộc chế độ kiểm tra liên kết (chẳng hạn MATCH SIMPLE/MATCH FULL) và khả năng hỗ trợ của hệ quản trị. Không nên tự suy ra mọi cấu hình khóa ngoại ghép đều bắt buộc đủ các thành phần.

### 9.4. CHECK có thể cho UNKNOWN đi qua

Một ràng buộc **CHECK** trong SQL chỉ chặn hàng khi biểu thức là **FALSE**; nếu biểu thức là **TRUE hoặc UNKNOWN**, hàng có thể vượt qua CHECK. Vì vậy:

~~~~sql
CREATE TABLE kiem_tra_gia (
    gia NUMERIC(12, 2) CHECK (gia > 0)
);

INSERT INTO kiem_tra_gia (gia) VALUES (NULL);
-- Hợp lệ trong PostgreSQL: (NULL > 0) là UNKNOWN,
-- CHECK không từ chối UNKNOWN.
~~~~

Nếu giá bắt buộc dương và phải tồn tại, cần kết hợp:

~~~~sql
CREATE TABLE kiem_tra_gia_bat_buoc (
    gia NUMERIC(12, 2) NOT NULL CHECK (gia > 0)
);
~~~~

Đây là lý do thiết kế miền giá trị không thể chỉ dừng ở câu “phải lớn hơn 0”; cũng phải hỏi “có cho phép không có giá trị hay không?”.

## 10. So sánh trực diện: quan hệ toán học và SQL

| Tiêu chí | Quan hệ toán học cổ điển | Bảng/kết quả SQL phổ biến |
| --- | --- | --- |
| Kiểu tập hợp | Tập các bộ | Có thể là đa tập các dòng |
| Bộ trùng toàn phần | Không tồn tại hai phần tử giống nhau | Có thể xuất hiện nếu thiếu ràng buộc; SELECT có thể tạo trùng |
| Phép chiếu | Tự loại bộ trùng vì đầu ra là tập | SELECT giữ trùng; SELECT DISTINCT loại trùng |
| Vị trí hàng | Không có thứ tự logic | Không bảo đảm thứ tự nếu thiếu ORDER BY |
| Giá trị thiếu | Không có NULL theo cách SQL sử dụng | Có thể có NULL trong cột cho phép |
| So sánh thông thường | Logic trên giá trị xác định | Thường có TRUE, FALSE và UNKNOWN |
| Gom nhóm/loại trùng với NULL | Không phát sinh vấn đề NULL kiểu SQL | NULL được gom thành một nhóm trong DISTINCT/GROUP BY |
| Khóa | Tính duy nhất dựa trên quy tắc logic, ứng viên khóa tối thiểu | PRIMARY KEY, UNIQUE, NOT NULL biểu đạt ràng buộc trong DDL |
| Đếm dòng | Lực lượng là số bộ của tập | COUNT(*) đếm số dòng, kể cả các lần trùng |

Không nên kết luận SQL “không theo mô hình quan hệ”. SQL là ngôn ngữ thực tế xây dựng trên nhiều ý tưởng quan hệ nhưng dùng quy tắc khác ở một số chỗ. Khi phân tích yêu cầu, hãy quyết định **ý nghĩa dữ liệu và khóa** từ mô hình logic trước, sau đó xem SQL cụ thể thực thi những yêu cầu đó ra sao.

## 11. Hệ quả đối với thiết kế dữ liệu và báo cáo

Ba câu hỏi quan trọng khi bước từ lược đồ logic sang lược đồ SQL:

### 11.1. “Trùng” là hai lần xuất hiện hợp lệ hay một lỗi dữ liệu?

| Tình huống | Cách hiểu | Thiết kế thường phù hợp |
| --- | --- | --- |
| Hai khách hàng tên An | Hợp lệ; tên không phải định danh | Khóa chính ma_kh, cho phép tên trùng |
| Hai dòng đơn có cùng sản phẩm trong cùng đơn | Tùy quy tắc bán hàng | Nếu cấm: UNIQUE(ma_dh, ma_sp); nếu cho phép: bổ sung định danh dòng |
| Hai giao dịch có cùng số tiền | Hợp lệ; số tiền không phải khóa | Khóa theo mã giao dịch, giữ đủ các lần phát sinh |
| Hai bản ghi nhập ngoài giống hệt nhau | Có thể là dữ liệu trùng cần xử lý | Xác định business key, nguồn, thời điểm và quy tắc loại trùng |
| Kết quả JOIN có nhiều dòng trên một đơn | Có thể là quan hệ 1–N bình thường | Chọn đúng mức độ hạt trước khi thống kê |

Đặc biệt trong kho dữ liệu phân tích, phép JOIN và việc chọn mức độ hạt là nguồn phổ biến gây **đếm lặp doanh thu**. Trong mô hình document hoặc đồ thị, một đối tượng hay một cạnh cũng có thể được biểu diễn nhiều cách; vì vậy việc xác định định danh, ý nghĩa mỗi bản ghi và ràng buộc vẫn cần thiết dù không dùng bảng quan hệ.

### 11.2. NULL đang chứa thông tin nghiệp vụ nào?

Khi một thuộc tính được phép thiếu, cần xác định:

1. Thiếu vì **chưa biết**, **không áp dụng** hay **chưa phát sinh**?
2. Có cần phân biệt những nguyên nhân đó trong truy vấn và báo cáo không?
3. Khi nào cần bắt buộc cập nhật giá trị (ví dụ trước lúc chốt đơn)?
4. Có thể dùng ràng buộc **NOT NULL**, **CHECK** hoặc trạng thái riêng để diễn đạt tốt hơn không?

Nếu doanh nghiệp cần phân biệt “chưa hỏi khách hàng”, “khách từ chối cung cấp email” và “khách chưa có email”, một cột email NULL đơn lẻ là không đủ. Có thể thêm trạng thái thu thập email được kiểm soát bởi tập giá trị hợp lệ, hoặc tách mô hình theo yêu cầu quản lý thông tin.

Không tự động thay mọi NULL bằng chuỗi “N/A” hay số 0. Làm như vậy có thể biến một trạng thái thiếu dữ liệu thành một giá trị sai về mặt nghiệp vụ, khiến phép tính hoặc điều kiện lọc trả kết quả không mong muốn.

### 11.3. Truy vấn cần tập hay đa tập?

- Danh sách **mã khách hàng duy nhất** đã mua hàng: dùng **DISTINCT** hoặc truy vấn phù hợp để lấy tập định danh.
- Số **đơn hàng** theo khách: đếm ở mức độ hạt **đơn hàng**; không loại trùng mã khách trước khi đếm.
- Số **khách có email**: dùng **COUNT(email)**, vì không tính email NULL.
- Số **khách hàng** trong bảng: dùng **COUNT(*)**.
- Tổng **doanh thu** sau khi JOIN nhiều bảng: kiểm tra mức độ hạt và sự nhân dòng, không dùng DISTINCT một cách cảm tính.
- Danh sách khách **chưa mua hàng**: dùng điều kiện **NOT EXISTS** hoặc cách nối/kiểm tra tương đương, nhất là khi tập con có khả năng chứa NULL.

Những lựa chọn này quyết định tính đúng đắn của kết quả, trước cả khi bàn tới chỉ mục hay hiệu năng.

## 12. Thực hành tự kiểm tra

Các bài tập sử dụng dữ liệu khách hàng và đơn hàng ở mục 3. Hãy dự đoán kết quả trước khi chạy truy vấn.

### Bài 1 — DISTINCT có phải luôn giảm dòng?

~~~~sql
-- A
SELECT ten FROM khach_hang;

-- B
SELECT DISTINCT ten FROM khach_hang;

-- C
SELECT DISTINCT ma_kh, ten FROM khach_hang;
~~~~

**Câu hỏi:** A, B và C lần lượt trả bao nhiêu dòng? Vì sao?

**Đáp án:** A có **4 dòng** vì tên An xuất hiện hai lần; B có **3 dòng** vì An bị gộp; C có **4 dòng** vì mỗi cặp **(ma_kh, ten)** là khác nhau. DISTINCT xét **cả dòng kết quả**, không kiểm tra “người” theo ý nghĩa ngoài dữ liệu.

### Bài 2 — NULL và logic ba giá trị

~~~~sql
-- A
SELECT ma_dh FROM don_hang
WHERE ma_uu_dai = NULL;

-- B
SELECT ma_dh FROM don_hang
WHERE ma_uu_dai IS NULL;

-- C
SELECT ma_dh FROM don_hang
WHERE NOT (ma_uu_dai = 'SALE10');
~~~~

**Câu hỏi:** Câu nào tìm được đơn 101 và 103?

**Đáp án:** Chỉ **B**. A so sánh bằng NULL nên điều kiện UNKNOWN ở mọi dòng. C cũng không giữ đơn 101 và 103: **NOT UNKNOWN** vẫn là UNKNOWN. Nếu muốn “không dùng SALE10, gồm cả không có mã”, dùng **IS DISTINCT FROM** (PostgreSQL) hoặc **ma_uu_dai <> 'SALE10' OR ma_uu_dai IS NULL**.

### Bài 3 — Tại sao đếm đơn bằng COUNT(*) bị sai?

~~~~sql
SELECT kh.ma_kh, COUNT(*) AS so_don
FROM khach_hang AS kh
LEFT JOIN don_hang AS dh ON dh.ma_kh = kh.ma_kh
GROUP BY kh.ma_kh
ORDER BY kh.ma_kh;
~~~~

**Câu hỏi:** Kết quả của khách hàng 4 là gì? Hãy sửa truy vấn để đếm số đơn chính xác.

**Đáp án:** Khách hàng 4 cho **COUNT(*) = 1** dù không có đơn, vì LEFT JOIN sinh một dòng với các cột phía đơn hàng bằng NULL. Thay thành **COUNT(dh.ma_dh)** vì **ma_dh** là khóa chính không NULL: khi không có đơn tương ứng, kết quả bằng **0**.

### Bài 4 — UNIQUE có cho phép hai email NULL?

Giả sử vẫn dùng PostgreSQL và lược đồ **email VARCHAR(254) UNIQUE** trong mục 3.

**Câu hỏi:** Hai khách hàng có email NULL có vi phạm UNIQUE không? Nếu email phải có giá trị, cần thêm gì?

**Đáp án:** Không vi phạm UNIQUE thông thường của PostgreSQL; nhiều NULL được chấp nhận. Nếu email bắt buộc, bổ sung **NOT NULL** bên cạnh **UNIQUE**. Không được suy ra cách xử lý giống hệt trên mọi DBMS nếu chưa kiểm tra.

### Bài 5 — Hai lần trùng số tiền có phải doanh thu trùng?

~~~~sql
SELECT
    SUM(tong_tien) AS tong_dung,
    SUM(DISTINCT tong_tien) AS tong_khong_phu_hop
FROM don_hang;
~~~~

**Câu hỏi:** Hai biểu thức cho kết quả nào, và tại sao phép thứ hai không phù hợp để tính doanh thu?

**Đáp án:** **SUM(tong_tien) = 1400000**; **SUM(DISTINCT tong_tien) = 700000** vì chỉ giữ hai giá trị phân biệt 200000 và 500000. Hai đơn hàng khác nhau có cùng giá trị tiền vẫn là các sự kiện bán hàng riêng, phải được cộng đủ. DISTINCT theo **giá trị tiền** làm mất thông tin số lần giao dịch.

### Bài 6 — Tạo truy vấn cho khách hàng chưa có đơn

**Yêu cầu:** Trả mã và tên của khách hàng không có đơn hàng; kết quả mong đợi là khách hàng **4 — An**. Hãy viết truy vấn không phụ thuộc vào hành vi của NOT IN khi tập con có NULL.

**Đáp án tham khảo:**

~~~~sql
SELECT kh.ma_kh, kh.ten
FROM khach_hang AS kh
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang AS dh
    WHERE dh.ma_kh = kh.ma_kh
)
ORDER BY kh.ma_kh;
~~~~

## 13. Tổng kết

| Khái niệm | Nguyên tắc ghi nhớ |
| --- | --- |
| Quan hệ toán học | **Tập** các bộ; không trùng bộ và không có NULL kiểu SQL cổ điển |
| SQL SELECT | Mặc định có **ngữ nghĩa đa tập**: có thể trả nhiều dòng trùng |
| DISTINCT | Loại dòng trùng trên **toàn bộ danh sách cột SELECT** |
| UNION ALL | Giữ mọi lần xuất hiện; UNION thường loại trùng |
| NULL | Dấu hiệu thiếu giá trị xác định; không phải 0, chuỗi rỗng hay FALSE |
| Logic ba giá trị | Biểu thức điều kiện có thể là TRUE, FALSE hoặc UNKNOWN |
| WHERE | Chỉ giữ dòng khi điều kiện là TRUE |
| IS NULL | Kiểm tra trạng thái NULL; không dùng **= NULL** |
| GROUP BY/DISTINCT với NULL | Các NULL được đặt vào cùng nhóm hoặc gộp khi loại trùng |
| COUNT(*) | Đếm dòng, kể cả dòng có NULL và các lần lặp |
| COUNT(cột) | Đếm các dòng có giá trị cột **không NULL** |
| PRIMARY KEY | Duy nhất và không NULL |
| UNIQUE nullable | Hành vi với NULL cần kiểm tra theo DBMS |
| CHECK | Biểu thức UNKNOWN không bị từ chối như FALSE |
| JOIN | Có thể nhân số dòng; cần phân biệt sự kiện và mức độ hạt |

Khi thiết kế mô hình dữ liệu, hãy làm rõ **mỗi bộ đại diện cho điều gì**, **tập thuộc tính nào định danh duy nhất**, **bản ghi được phép thiếu thông tin nào** và **truy vấn cần đếm các sự kiện hay chỉ lấy các giá trị phân biệt**. Những câu hỏi này nối lý thuyết quan hệ với cách SQL vận hành, giúp các bước chuẩn hóa, thiết kế khóa, viết truy vấn, chọn chỉ mục và đánh giá mô hình dữ liệu diễn ra trên một nền tảng logic có thể kiểm chứng.
