# Logic ba giá trị TRUE, FALSE và UNKNOWN trong SQL

> **Chủ đề:** Database SQL → NULL và logic  
> **Trọng tâm:** Trong SQL, điều kiện không chỉ có hai kết quả đúng (**TRUE**) và sai (**FALSE**). Khi dữ liệu chứa **NULL**, nhiều biểu thức cho kết quả **UNKNOWN**. Hiểu trạng thái thứ ba này giúp viết đúng WHERE, JOIN, HAVING, CHECK, NOT IN và những truy vấn làm việc với dữ liệu thiếu.

## 1. Mục tiêu bài học

Sau khi học, bạn có thể:

- Giải thích vì sao SQL có **logic ba giá trị** (three-valued logic, viết tắt **3VL**).
- Phân biệt giá trị dữ liệu **NULL** với kết quả logic **UNKNOWN**, cũng như với **FALSE**, số **0** và chuỗi rỗng **''**.
- Tính đúng các bảng chân trị của **NOT**, **AND**, **OR** khi có UNKNOWN.
- Dự đoán hàng nào được giữ trong **WHERE**, **HAVING**, điều kiện **JOIN ... ON**; hiểu vì sao **CHECK** có cách chấp nhận UNKNOWN khác WHERE.
- Tránh các bẫy phổ biến với **= NULL**, **<>**, **NOT IN**, so sánh chuỗi, điều kiện phủ định và tổng hợp dữ liệu.
- Chủ động xử lý NULL bằng **IS NULL**, **IS NOT NULL**, **COALESCE**, **CASE**, **NOT EXISTS** hoặc phép so sánh an toàn với NULL khi DBMS hỗ trợ.
- Phân biệt ngữ nghĩa SQL chung với khác biệt triển khai ở PostgreSQL, MySQL, SQL Server, Oracle Database và SQLite.

## 2. Vấn đề xuất phát từ dữ liệu không có giá trị

Hãy xét bảng khách hàng:

| ma_khach_hang | ten_khach_hang | email | tuoi |
|---:|---|---|---:|
| 1 | An | an@example.com | 25 |
| 2 | Bình | NULL | 17 |
| 3 | Chi | chi@example.com | NULL |
| 4 | Dũng | NULL | 32 |
| 5 | Em | em@example.com | NULL |

Giả sử **ma_khach_hang** là khóa chính, **email** và **tuoi** cho phép NULL.

Trong ứng dụng, email NULL có thể xuất hiện vì khách hàng chưa cung cấp email; tuổi NULL có thể xuất hiện vì khách không khai báo ngày sinh. SQL dùng **NULL** để biểu thị **không có một giá trị dữ liệu** trong cột hoặc biểu thức. Lý do nghiệp vụ đằng sau sự thiếu vắng có thể là “chưa biết”, “chưa nhập”, “không áp dụng” hay “đã bị ẩn”; chỉ một giá trị NULL tự nó **không cho biết** lý do nào.

Giờ hỏi: “Chi có tuổi từ 18 trở lên không?”

~~~sql
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE tuoi >= 18;
~~~

Với **An**, biểu thức **25 >= 18** là TRUE. Với **Bình**, **17 >= 18** là FALSE. Với **Chi**, tuổi là NULL, nên không thể xác nhận điều kiện đúng hay sai chỉ bằng phép so sánh đó. Kết quả logic của **NULL >= 18** là **UNKNOWN**.

Đây là điểm khác logic hai giá trị thường gặp trong lập trình:

- **TRUE**: điều kiện được xác định là đúng.
- **FALSE**: điều kiện được xác định là sai.
- **UNKNOWN**: không thể xác định đúng hay sai theo phép toán đang dùng vì thông tin cần thiết bị thiếu.

**UNKNOWN là trạng thái của kết quả điều kiện; NULL là dấu hiệu không có giá trị trong dữ liệu.** Hai khái niệm liên quan chặt chẽ nhưng không phải cùng một loại đối tượng. Trong SQL, một biểu thức điều kiện UNKNOWN thường tương ứng với giá trị logic NULL ở những hệ có kiểu BOOLEAN; không nên coi chuỗi ký tự **'UNKNOWN'** là chính trạng thái logic UNKNOWN.

### 2.1. NULL không phải số 0, FALSE hay chuỗi rỗng

| Biểu diễn | Ý nghĩa |
|---|---|
| **0** | Một số cụ thể bằng không |
| **FALSE** | Điều kiện đã được xác định là sai |
| **''** | Chuỗi ký tự có độ dài bằng 0 trong các DBMS phân biệt chuỗi rỗng và NULL |
| **NULL** | Không có giá trị dữ liệu tại vị trí đó |
| **UNKNOWN** | Kết quả logic không được xác định là TRUE hoặc FALSE |

Ví dụ, khách có tuổi **0** (dù có thể không hợp lý về nghiệp vụ) khác với khách có tuổi **NULL**. Khi báo cáo số tuổi, biến NULL thành 0 một cách tùy tiện có thể làm sai các thống kê.

**Lưu ý về phương ngữ:** Oracle Database truyền thống xử lý chuỗi ký tự độ dài 0 như NULL trong nhiều ngữ cảnh; nhiều DBMS khác phân biệt hai giá trị này. Vì vậy, kiểm thử chuỗi rỗng và NULL trên đúng DBMS đang dùng là cần thiết.

## 3. Vì sao dùng dấu bằng với NULL không hoạt động như mong đợi?

Trong SQL, các toán tử so sánh thông thường như **=**, **<>**, **<**, **>**, **<=**, **>=** tạo ra UNKNOWN nếu một toán hạng là NULL.

| Biểu thức | Kết quả logic |
|---|---|
| **25 = 25** | TRUE |
| **25 = 17** | FALSE |
| **25 <> 17** | TRUE |
| **NULL = 25** | UNKNOWN |
| **NULL <> 25** | UNKNOWN |
| **NULL = NULL** | UNKNOWN |
| **NULL <> NULL** | UNKNOWN |
| **NULL > 0** | UNKNOWN |
| **0 * NULL = 0** | UNKNOWN, vì phép nhân với NULL thông thường cho NULL |

**NULL = NULL không trả TRUE**. Dù hai vị trí đều chưa có giá trị, SQL không suy ra chúng chứa cùng một giá trị đã biết. Dòng dữ liệu thiếu hai giá trị không phải bằng chứng hai giá trị thực tế bằng nhau.

Vì vậy, truy vấn sau không tìm được các khách có email NULL:

~~~sql
-- Sai ý định: email = NULL có kết quả UNKNOWN, không phải TRUE.
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE email = NULL;
~~~

Cách đúng:

~~~sql
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE email IS NULL;
~~~

Theo bảng ví dụ, kết quả gồm **Bình (2)** và **Dũng (4)**.

Ngược lại, để tìm người có email:

~~~sql
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE email IS NOT NULL;
~~~

Kết quả gồm **An (1)**, **Chi (3)** và **Em (5)**.

**IS NULL** và **IS NOT NULL** là các điều kiện chuyên dùng để kiểm tra tình trạng NULL và cho kết quả TRUE/FALSE. Chúng không phải phép so sánh bằng theo nghĩa thông thường.

## 4. Bảng chân trị của logic ba giá trị

Trong logic hai giá trị, mỗi điều kiện chỉ có TRUE hoặc FALSE. Trong 3VL của SQL, điều kiện còn có UNKNOWN.

Quy ước viết tắt trong bảng:

- **T** = TRUE.
- **F** = FALSE.
- **U** = UNKNOWN.

Các bảng dưới đây thể hiện ngữ nghĩa logic SQL cho **NOT**, **AND**, **OR**.

### 4.1. NOT — phủ định một điều kiện

| P | NOT P |
|---|---|
| T | F |
| F | T |
| U | U |

Nếu chưa biết **P** đúng hay sai, phủ định nó cũng không tạo ra thông tin mới.

Ví dụ:

~~~sql
-- Với tuoi = NULL:
tuoi >= 18         -- UNKNOWN
NOT (tuoi >= 18)   -- UNKNOWN
~~~

Đây là lý do **NOT (tuoi >= 18)** không có nghĩa là “bao gồm tất cả người không được xác nhận đủ 18 tuổi”. Người chưa biết tuổi vẫn không được chọn bởi điều kiện NOT đó.

### 4.2. AND — cả hai điều kiện phải đúng

| P | Q | P AND Q |
|---|---|---|
| T | T | T |
| T | F | F |
| T | U | U |
| F | T | F |
| F | F | F |
| F | U | F |
| U | T | U |
| U | F | F |
| U | U | U |

Cách suy luận:

- Nếu **ít nhất một vế chắc chắn FALSE**, toàn bộ **AND** là FALSE.
- Nếu **cả hai vế đều TRUE**, kết quả TRUE.
- Trong các trường hợp còn lại, có UNKNOWN nên kết quả UNKNOWN.

Ví dụ:

~~~text
(tuoi >= 18) AND (ten_khach_hang = 'Chi')
   UNKNOWN     AND          TRUE           = UNKNOWN

(tuoi >= 18) AND (ma_khach_hang = -1)
   UNKNOWN     AND          FALSE          = FALSE
~~~

Dù chưa biết tuổi, điều kiện “mã khách hàng bằng -1” đã chắc chắn sai đối với một dòng có mã là 3; toàn bộ phép AND trở thành FALSE.

### 4.3. OR — chỉ cần một điều kiện đúng

| P | Q | P OR Q |
|---|---|---|
| T | T | T |
| T | F | T |
| T | U | T |
| F | T | T |
| F | F | F |
| F | U | U |
| U | T | T |
| U | F | U |
| U | U | U |

Cách suy luận:

- Nếu **ít nhất một vế chắc chắn TRUE**, toàn bộ **OR** là TRUE.
- Nếu **cả hai vế đều FALSE**, kết quả FALSE.
- Các trường hợp còn lại có UNKNOWN cho kết quả UNKNOWN.

Ví dụ:

~~~text
(tuoi >= 18) OR (ma_khach_hang = 3)
   UNKNOWN    OR          TRUE            = TRUE

(tuoi >= 18) OR (ma_khach_hang = -1)
   UNKNOWN    OR          FALSE           = UNKNOWN
~~~

### 4.4. Bảng ghi nhớ nhanh

| Toán tử | Quy tắc đáng nhớ |
|---|---|
| **NOT UNKNOWN** | UNKNOWN |
| **FALSE AND UNKNOWN** | FALSE |
| **TRUE AND UNKNOWN** | UNKNOWN |
| **TRUE OR UNKNOWN** | TRUE |
| **FALSE OR UNKNOWN** | UNKNOWN |
| **UNKNOWN AND UNKNOWN** | UNKNOWN |
| **UNKNOWN OR UNKNOWN** | UNKNOWN |

**Quan trọng:** Bảng chân trị mô tả **kết quả logic**, không bảo đảm DBMS sẽ thực thi phép tính bên trái trước phép tính bên phải hoặc luôn dừng sớm khi đã biết kết quả. Bộ tối ưu có thể biến đổi và sắp xếp các biểu thức; không nên phụ thuộc thứ tự viết **AND/OR** để ngăn lỗi chia cho 0 hoặc các biểu thức khác có nguy cơ lỗi.

## 5. WHERE chỉ giữ dòng có điều kiện TRUE

Trong một câu SELECT, mệnh đề **WHERE** kiểm tra điều kiện cho từng dòng trước khi đưa dòng đó vào kết quả của giai đoạn kế tiếp.

| Kết quả của điều kiện WHERE | Dòng có được giữ lại? |
|---|---|
| TRUE | Có |
| FALSE | Không |
| UNKNOWN | Không |

Đây là nguyên tắc cốt lõi: **WHERE không cần phân biệt FALSE và UNKNOWN để quyết định có giữ dòng hay không; chỉ TRUE mới được giữ**.

Với dữ liệu minh họa:

~~~sql
SELECT ma_khach_hang, ten_khach_hang, tuoi
FROM khach_hang
WHERE tuoi >= 18
ORDER BY ma_khach_hang;
~~~

Kết quả:

| ma_khach_hang | ten_khach_hang | tuoi |
|---:|---|---:|
| 1 | An | 25 |
| 4 | Dũng | 32 |

Bình bị loại vì FALSE. Chi và Em bị loại vì UNKNOWN.

### 5.1. “Không đủ tuổi” không bao gồm “chưa biết tuổi”

~~~sql
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE NOT (tuoi >= 18);
~~~

Kết quả chỉ có **Bình** (tuổi 17). Chi và Em vẫn không xuất hiện.

Nếu nghiệp vụ yêu cầu “tất cả người **không được xác nhận** đủ 18 tuổi”, phải nói rõ chính sách xử lý dữ liệu thiếu:

~~~sql
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE tuoi < 18
   OR tuoi IS NULL
ORDER BY ma_khach_hang;
~~~

Kết quả gồm **Bình, Chi, Em**.

Hai câu hỏi nghiệp vụ khác nhau:

1. **“Ai chắc chắn dưới 18 tuổi?”** → **WHERE tuoi < 18**.
2. **“Ai chưa được chứng minh từ 18 tuổi trở lên?”** → **WHERE tuoi < 18 OR tuoi IS NULL**.

Không nên biến sự thiếu dữ liệu thành kết luận chắc chắn về tuổi của một người.

### 5.2. So sánh khác cũng bỏ qua dòng NULL

~~~sql
SELECT ma_khach_hang
FROM khach_hang
WHERE email <> 'an@example.com';
~~~

Kết quả chỉ gồm khách có email khác giá trị trên và **không NULL**: **Chi (3)** và **Em (5)**. Bình và Dũng có email NULL nên **NULL <> 'an@example.com'** là UNKNOWN; chúng không được giữ.

Nếu muốn nhận **mọi khách trừ người có email chính xác bằng 'an@example.com'**, bao gồm khách chưa có email:

~~~sql
SELECT ma_khach_hang
FROM khach_hang
WHERE email <> 'an@example.com'
   OR email IS NULL
ORDER BY ma_khach_hang;
~~~

Kết quả: **2, 3, 4, 5**.

## 6. Logic ba giá trị phá vỡ một số trực giác từ logic hai giá trị

### 6.1. P OR NOT P không còn luôn TRUE

Trong logic hai giá trị, **P OR NOT P** là đúng với mọi P (luật bài trung). Nhưng xét:

~~~text
P = (tuoi >= 18) với tuoi = NULL

P          = UNKNOWN
NOT P      = UNKNOWN
P OR NOT P = UNKNOWN
~~~

Vì vậy, truy vấn:

~~~sql
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE tuoi >= 18
   OR NOT (tuoi >= 18);
~~~

**Không** trả tất cả khách. Nó chỉ trả các khách có tuổi khác NULL; Chi và Em bị loại.

Muốn thực sự lấy tất cả dòng mà vẫn minh họa đủ ba trường hợp:

~~~sql
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE tuoi >= 18
   OR tuoi < 18
   OR tuoi IS NULL;
~~~

Tất nhiên, khi không cần lọc gì thì có thể bỏ WHERE.

### 6.2. P AND NOT P không luôn FALSE

Khi P = UNKNOWN:

~~~text
P AND NOT P = UNKNOWN AND UNKNOWN = UNKNOWN
~~~

Điều đó **không** có nghĩa tồn tại dòng “vừa đúng vừa sai”. Nó nghĩa là biểu thức ghép vẫn chưa có đủ thông tin để kết luận. Trong WHERE, UNKNOWN bị loại giống như FALSE, nên sự khác biệt chỉ thấy rõ khi xét giá trị logic hoặc dùng thêm các phép toán khác.

### 6.3. Một số quy tắc vẫn đúng

Các luật phân phối và De Morgan theo kiểu logic ba giá trị mà SQL sử dụng vẫn hữu ích:

~~~text
NOT (P AND Q) = (NOT P) OR (NOT Q)
NOT (P OR Q)  = (NOT P) AND (NOT Q)
~~~

Nhưng khi **P** là UNKNOWN, không thể đơn giản thay **NOT P** bằng một điều kiện được bảo đảm chọn mọi dòng ngoài tập P đúng. Tại tầng truy vấn, cần xử lý NULL một cách tường minh nếu nghiệp vụ yêu cầu phân chia toàn bộ dòng thành hai nhóm bổ sung cho nhau.

## 7. Tự quan sát TRUE, FALSE và UNKNOWN trong câu SQL

Để diễn tả kết quả điều kiện một cách dễ đọc giữa nhiều DBMS, có thể dùng **CASE** trả nhãn văn bản.

~~~sql
SELECT
    ma_khach_hang,
    ten_khach_hang,
    tuoi,
    CASE
        WHEN tuoi >= 18 THEN 'TRUE'
        WHEN NOT (tuoi >= 18) THEN 'FALSE'
        ELSE 'UNKNOWN'
    END AS ket_qua_dieu_kien
FROM khach_hang
ORDER BY ma_khach_hang;
~~~

Theo dữ liệu mẫu:

| ma_khach_hang | ten_khach_hang | tuoi | ket_qua_dieu_kien |
|---:|---|---:|---|
| 1 | An | 25 | TRUE |
| 2 | Bình | 17 | FALSE |
| 3 | Chi | NULL | UNKNOWN |
| 4 | Dũng | 32 | TRUE |
| 5 | Em | NULL | UNKNOWN |

Trong **CASE WHEN**, chỉ nhánh có điều kiện TRUE được chọn. Nếu điều kiện FALSE hoặc UNKNOWN, SQL xét nhánh kế tiếp hoặc chuyển đến ELSE.

Ở ví dụ này:

- Tuổi 25 hoặc 32 → nhánh đầu.
- Tuổi 17 → nhánh thứ hai, vì **NOT (FALSE)** là TRUE.
- Tuổi NULL → cả hai WHEN đều không TRUE → nhánh ELSE.

**'TRUE'**, **'FALSE'**, **'UNKNOWN'** trong câu lệnh trên là **nhãn chuỗi do chúng ta tự đặt**, không phải một yêu cầu DBMS lưu ba chuỗi này làm kiểu BOOLEAN.

### 7.1. Phân loại giá trị bị thiếu theo mục đích nghiệp vụ

~~~sql
SELECT
    ma_khach_hang,
    CASE
        WHEN tuoi IS NULL THEN 'CHUA_CO_THONG_TIN'
        WHEN tuoi >= 18 THEN 'DU_TUOI'
        ELSE 'CHUA_DU_TUOI'
    END AS nhom_tuoi
FROM khach_hang;
~~~

Trường hợp NULL được kiểm tra trước để có nhãn đúng. Đây thường là cách xây dựng quy tắc nghiệp vụ rõ ràng hơn việc chỉ để UNKNOWN xuất hiện rồi hy vọng WHERE tự xử lý như mong muốn.

## 8. IS NULL, IS NOT NULL và phép so sánh an toàn với NULL

### 8.1. Kiểm tra sự thiếu vắng

~~~sql
-- Đã có email:
WHERE email IS NOT NULL

-- Chưa có email:
WHERE email IS NULL
~~~

Hai biểu thức trên cho TRUE/FALSE ngay cả khi email NULL. Chúng giúp chia dữ liệu thành hai tập không chồng nhau và bao phủ tất cả dòng.

### 8.2. So sánh xem hai giá trị có khác nhau, kể cả khi có NULL

SQL chuẩn có các điều kiện **IS DISTINCT FROM** và **IS NOT DISTINCT FROM**, cung cấp ngữ nghĩa hai giá trị khi so sánh kể cả trường hợp NULL:

| a | b | a = b | a IS NOT DISTINCT FROM b | a IS DISTINCT FROM b |
|---|---|---|---|---|
| 5 | 5 | TRUE | TRUE | FALSE |
| 5 | 7 | FALSE | FALSE | TRUE |
| 5 | NULL | UNKNOWN | FALSE | TRUE |
| NULL | 5 | UNKNOWN | FALSE | TRUE |
| NULL | NULL | UNKNOWN | TRUE | FALSE |

Như vậy:

- **IS NOT DISTINCT FROM** xem hai NULL là “không khác biệt” cho mục đích so sánh.
- **IS DISTINCT FROM** xem NULL và giá trị không NULL là khác biệt.
- Hai phép này **không trả UNKNOWN**.

Ví dụ minh họa:

~~~sql
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE email IS NOT DISTINCT FROM NULL;
~~~

Về ý nghĩa, nó tương đương **WHERE email IS NULL**.

**Tính khả chuyển:** PostgreSQL và một số DBMS khác hỗ trợ trực tiếp các toán tử này; SQL Server hỗ trợ từ phiên bản 2022. SQLite có cú pháp tương ứng ở các phiên bản hiện đại, còn MySQL thường dùng toán tử so sánh an toàn với NULL **<=>**. Việc hỗ trợ, tên toán tử và phiên bản khác nhau, nên **IS NULL** vẫn là cách phổ biến và dễ đọc nhất khi chỉ cần kiểm tra một giá trị có NULL hay không.

### 8.3. Vì sao không dùng COALESCE tùy tiện để so sánh NULL?

Một cách làm thường thấy:

~~~sql
WHERE COALESCE(email, '') = ''
~~~

Trong những hệ phân biệt NULL với chuỗi rỗng, biểu thức trên **gộp cả email NULL và email bằng chuỗi rỗng**. Nó không tương đương hoàn toàn với **email IS NULL**.

Tương tự, với số:

~~~sql
WHERE COALESCE(tuoi, 0) = 0
~~~

sẽ gom cả tuổi thực sự bằng 0 lẫn tuổi chưa biết. Phải xác định rõ phép gộp này có phù hợp nghiệp vụ không.

## 9. IN và NOT IN khi tập so sánh chứa NULL

Đây là một trong các bẫy quan trọng nhất của logic ba giá trị.

### 9.1. IN kết hợp nhiều phép so sánh bằng

Ở mức ý nghĩa, biểu thức:

~~~sql
ma_khach_hang IN (1, 3, 5)
~~~

gần tương đương với:

~~~sql
ma_khach_hang = 1
OR ma_khach_hang = 3
OR ma_khach_hang = 5
~~~

Với mã là 3, kết quả TRUE. Với mã là 2, tất cả so sánh FALSE nên kết quả FALSE.

Nhưng nếu tập có NULL:

~~~sql
ma_khach_hang IN (1, 3, NULL)
~~~

với mã là 2:

~~~text
2 = 1      -> FALSE
2 = 3      -> FALSE
2 = NULL   -> UNKNOWN

FALSE OR FALSE OR UNKNOWN -> UNKNOWN
~~~

Điều kiện IN không TRUE nên WHERE loại dòng mã 2.

Với mã là 1:

~~~text
TRUE OR FALSE OR UNKNOWN -> TRUE
~~~

Chỉ cần một giá trị chắc chắn khớp thì IN TRUE, kể cả tập có NULL.

### 9.2. NOT IN với NULL có thể loại tất cả dòng không khớp

Xét:

~~~sql
SELECT ma_khach_hang
FROM khach_hang
WHERE ma_khach_hang NOT IN (1, 3, NULL);
~~~

Một trực giác sai là kết quả gồm 2, 4 và 5. Thực tế, với mã 2, 4 và 5, điều kiện IN có kết quả UNKNOWN, do đó NOT IN là **NOT UNKNOWN = UNKNOWN**, và WHERE loại dòng.

Mã 1 hoặc 3 thì IN TRUE, NOT IN FALSE, cũng bị loại. Vì vậy ví dụ này **không trả dòng nào**.

Khi tập giá trị đến từ truy vấn con, vấn đề còn khó nhìn hơn:

~~~sql
-- Rủi ro nếu don_hang.ma_khach_hang có NULL.
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE k.ma_khach_hang NOT IN (
    SELECT d.ma_khach_hang
    FROM don_hang d
);
~~~

Nếu truy vấn con trả ít nhất một giá trị NULL, mọi khách có mã không khớp một mã cụ thể đều có thể bị loại vì UNKNOWN.

### 9.3. Cách dùng NOT EXISTS cho bài toán “không có bản ghi liên quan”

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang d
    WHERE d.ma_khach_hang = k.ma_khach_hang
);
~~~

**EXISTS** chỉ hỏi truy vấn con có dòng thỏa điều kiện hay không. Nó trả TRUE hoặc FALSE, không trả UNKNOWN chỉ vì cột của một dòng trong truy vấn con chứa NULL. **NOT EXISTS** vì vậy thường phù hợp để tìm khách không có đơn hàng liên quan.

Điểm cần phân biệt: nếu **khóa ở bảng ngoài cũng có thể NULL**, NOT EXISTS với phép so sánh bằng thông thường không xem hai NULL là khớp; cần xác định lại yêu cầu nghiệp vụ. Trong ví dụ này, **k.ma_khach_hang** là khóa chính nên không NULL.

Nếu vẫn dùng NOT IN, có thể lọc NULL khỏi tập con:

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE k.ma_khach_hang NOT IN (
    SELECT d.ma_khach_hang
    FROM don_hang d
    WHERE d.ma_khach_hang IS NOT NULL
);
~~~

Với khóa ngoài không NULL như ví dụ, cách này khắc phục bẫy tập con chứa NULL. Tuy nhiên, **NOT EXISTS** thường bộc lộ ý định “không tồn tại quan hệ” rõ hơn.

### 9.4. EXISTS và NOT EXISTS

| Truy vấn con | EXISTS (...) | NOT EXISTS (...) |
|---|---|---|
| Trả ít nhất một dòng | TRUE | FALSE |
| Không trả dòng nào | FALSE | TRUE |
| Trả dòng nhưng các cột được chọn có NULL | TRUE | FALSE |

Sự có mặt của NULL trong **giá trị được SELECT** ở truy vấn con không tự biến EXISTS thành UNKNOWN. Điều quan trọng là truy vấn con có trả **dòng** hay không.

## 10. BETWEEN, LIKE và các phép so sánh khác

Nhiều điều kiện SQL thường dùng vẫn chịu ảnh hưởng từ NULL.

### 10.1. BETWEEN

~~~sql
SELECT ma_khach_hang, tuoi
FROM khach_hang
WHERE tuoi BETWEEN 18 AND 30;
~~~

Nếu **tuoi** NULL, hai phép so sánh giới hạn không thể xác định đúng/sai và điều kiện BETWEEN cho UNKNOWN. WHERE loại dòng đó.

**NOT BETWEEN** cũng không tự bao gồm tuổi NULL:

~~~sql
SELECT ma_khach_hang, tuoi
FROM khach_hang
WHERE tuoi NOT BETWEEN 18 AND 30;
~~~

Trong dữ liệu mẫu, Bình (17) và Dũng (32) thỏa điều kiện; Chi và Em có tuổi NULL không thỏa vì điều kiện là UNKNOWN.

### 10.2. LIKE

~~~sql
SELECT ma_khach_hang, email
FROM khach_hang
WHERE email LIKE '%@example.com';
~~~

Với email NULL, điều kiện LIKE là UNKNOWN nên dòng không xuất hiện. **NOT LIKE** cũng cho UNKNOWN khi email NULL.

Nếu nghiệp vụ là “email không thuộc tên miền này hoặc chưa cung cấp email”, cần:

~~~sql
SELECT ma_khach_hang, email
FROM khach_hang
WHERE email NOT LIKE '%@example.com'
   OR email IS NULL;
~~~

### 10.3. Phép toán số học

Trong các phép toán số học thông thường, đầu vào NULL làm kết quả phép toán thành NULL:

~~~sql
SELECT
    tong_tien,
    tong_tien * 0.10 AS thue_du_kien
FROM don_hang;
~~~

Nếu **tong_tien** NULL, **thue_du_kien** thường là NULL, không phải 0. Sau đó, điều kiện như **thue_du_kien > 0** sẽ cho UNKNOWN nếu đặt ở query block khác.

Không nên suy luận “NULL tham gia biểu thức nào cũng khiến mọi thứ thành UNKNOWN”: UNKNOWN là trạng thái của **điều kiện logic**; phép toán số học thường cho kết quả dữ liệu **NULL**. Hơn nữa, các hàm như COALESCE, phép kiểm tra IS NULL và các hàm tổng hợp có quy tắc đặc biệt.

## 11. JOIN ... ON: TRUE tạo khớp, FALSE/UNKNOWN không tạo khớp

Cho bảng đơn hàng:

| ma_don_hang | ma_khach_hang | trang_thai | tong_tien |
|---:|---:|---|---:|
| 101 | 1 | PAID | 200000 |
| 102 | 2 | PENDING | NULL |
| 103 | NULL | PAID | 100000 |
| 104 | 3 | PAID | 300000 |

Ở đây, đơn **103** chưa gắn với một khách hàng xác định.

### 11.1. INNER JOIN chỉ chọn cặp dòng có ON TRUE

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
ORDER BY k.ma_khach_hang;
~~~

Kết quả có các cặp **(1, 101)**, **(2, 102)** và **(3, 104)**.

Đơn 103 có **d.ma_khach_hang = NULL** nên so sánh **NULL = k.ma_khach_hang** là UNKNOWN với mọi khách. Nó không khớp ai. Đơn 103 cũng không thể tự khớp một dòng khác có mã khách NULL chỉ bằng toán tử **=**.

**Trong điều kiện ON của JOIN thông thường, TRUE mới tạo cặp khớp; FALSE và UNKNOWN đều không tạo cặp khớp.**

### 11.2. LEFT JOIN vẫn giữ dòng bên trái không khớp

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
ORDER BY k.ma_khach_hang;
~~~

Kết quả gồm các dòng khớp phía trên cộng thêm **Dũng (4)** và **Em (5)**, có **ma_don_hang = NULL** vì không có dòng đơn hàng khớp.

Điểm quan trọng: NULL trong các cột phía phải của kết quả LEFT JOIN **có thể do không tìm được dòng khớp**, không nhất thiết có nghĩa cột gốc của một dòng đơn hàng thật chứa NULL.

### 11.3. Đặt điều kiện trong ON khác với đặt trong WHERE

**Cách A — chỉ nối đơn đã thanh toán nhưng vẫn giữ mọi khách:**

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID'
ORDER BY k.ma_khach_hang;
~~~

Theo dữ liệu mẫu:

| ma_khach_hang | ten_khach_hang | ma_don_hang |
|---:|---|---:|
| 1 | An | 101 |
| 2 | Bình | NULL |
| 3 | Chi | 104 |
| 4 | Dũng | NULL |
| 5 | Em | NULL |

**Cách B — nối tất cả đơn rồi dùng WHERE lọc đơn đã thanh toán:**

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
WHERE d.trang_thai = 'PAID'
ORDER BY k.ma_khach_hang;
~~~

Kết quả chỉ còn **An (101)** và **Chi (104)**. Với Bình, trạng thái PENDING là FALSE. Với Dũng và Em, dòng phía phải được đệm NULL nên **NULL = 'PAID'** là UNKNOWN; WHERE loại họ.

**Bài học:** điều kiện trong **ON** quyết định các cặp dòng khớp; điều kiện trong **WHERE** lọc kết quả sau bước JOIN logic. Với OUTER JOIN, chuyển một điều kiện từ ON sang WHERE có thể làm mất các dòng cần giữ.

### 11.4. Tìm khách chưa có đơn: chọn cột kiểm tra đáng tin cậy

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
WHERE d.ma_don_hang IS NULL;
~~~

Nếu **ma_don_hang** là khóa chính NOT NULL, điều kiện này chỉ nhận khách không có dòng đơn khớp.

Không nên thay bằng **WHERE d.tong_tien IS NULL** khi tổng tiền của đơn hàng thật có thể NULL. Trong dữ liệu mẫu, Bình có đơn 102 nhưng tổng tiền NULL, nên cách thay thế đó sẽ phân loại nhầm Bình thành “không có đơn”.

Khi phù hợp, **NOT EXISTS** thể hiện ý định rõ hơn:

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang d
    WHERE d.ma_khach_hang = k.ma_khach_hang
);
~~~

## 12. HAVING và biểu thức tổng hợp cũng chịu quy tắc 3VL

**HAVING** lọc các nhóm được tạo ra bởi GROUP BY. Tương tự WHERE, HAVING chỉ giữ nhóm có điều kiện TRUE.

Ví dụ:

~~~sql
SELECT
    d.ma_khach_hang,
    SUM(d.tong_tien) AS tong_tien
FROM don_hang d
GROUP BY d.ma_khach_hang
HAVING SUM(d.tong_tien) > 150000;
~~~

Với dữ liệu mẫu:

- Nhóm khách 1: SUM = 200000, so sánh TRUE → giữ.
- Nhóm khách 2: chỉ có đơn tổng tiền NULL, SUM = NULL, so sánh UNKNOWN → loại.
- Nhóm khách 3: SUM = 300000, TRUE → giữ.
- Nhóm mã khách NULL (đơn 103): SUM = 100000, FALSE → loại.

Kết quả gồm nhóm khách **1** và **3**.

Nếu muốn xem cả nhóm có tổng tiền chưa xác định, phải nêu điều kiện:

~~~sql
SELECT
    d.ma_khach_hang,
    SUM(d.tong_tien) AS tong_tien
FROM don_hang d
GROUP BY d.ma_khach_hang
HAVING SUM(d.tong_tien) > 150000
    OR SUM(d.tong_tien) IS NULL;
~~~

Truy vấn này giữ thêm nhóm khách 2. Tuy nhiên, đó là một **quyết định nghiệp vụ**: không được tự hiểu giá trị SUM NULL đồng nghĩa “tổng tiền lớn hơn 150000”.

## 13. COUNT, SUM, AVG và GROUP BY xử lý NULL thế nào?

Logic ba giá trị giải thích điều kiện lọc; còn hàm tổng hợp có **quy tắc riêng về dữ liệu NULL**.

Xét bảng **don_hang** ở trên:

| Biểu thức tổng hợp | Kết quả | Giải thích |
|---|---:|---|
| **COUNT(*)** | 4 | Đếm mọi dòng, không phân biệt cột nào NULL |
| **COUNT(ma_khach_hang)** | 3 | Bỏ qua dòng có ma_khach_hang NULL |
| **COUNT(tong_tien)** | 3 | Bỏ qua tổng tiền NULL ở đơn 102 |
| **SUM(tong_tien)** | 600000 | Cộng 200000 + 100000 + 300000; bỏ qua NULL |
| **AVG(tong_tien)** | 200000 | Trung bình của 3 giá trị không NULL |

Truy vấn:

~~~sql
SELECT
    COUNT(*) AS so_dong,
    COUNT(ma_khach_hang) AS so_dong_co_khach,
    COUNT(tong_tien) AS so_dong_co_tien,
    SUM(tong_tien) AS tong_tien,
    AVG(tong_tien) AS trung_binh
FROM don_hang;
~~~

**COUNT(*)** không “bỏ qua dòng NULL”; nó đếm dòng. **COUNT(cot)** mới bỏ qua các dòng có **cot** NULL.

### 13.1. Tổng hợp toàn NULL khác với tổng bằng 0

Nếu một nhóm có dòng nhưng mọi giá trị **tong_tien** đều NULL, **SUM(tong_tien)** trả NULL (trong ngữ nghĩa SQL thông thường), không phải 0. Với một tập đầu vào rỗng, **COUNT** trả 0, trong khi **SUM** thường trả NULL.

Nếu nghiệp vụ quyết định xem dữ liệu tổng tiền thiếu như 0:

~~~sql
SELECT
    d.ma_khach_hang,
    COALESCE(SUM(d.tong_tien), 0) AS tong_tien_hien_thi
FROM don_hang d
GROUP BY d.ma_khach_hang;
~~~

Việc này hữu ích cho báo cáo, nhưng **có thể che giấu dữ liệu thiếu**. Hãy cân nhắc hiển thị thêm **COUNT(d.tong_tien)** hoặc một cờ dữ liệu chưa đầy đủ khi cần phân biệt “không có tiền” với “chưa biết tổng tiền”.

### 13.2. GROUP BY gom các giá trị NULL vào cùng nhóm

Điều này dễ gây bất ngờ:

~~~sql
SELECT
    d.ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang d
GROUP BY d.ma_khach_hang
ORDER BY d.ma_khach_hang;
~~~

Mặc dù **NULL = NULL** là UNKNOWN, các dòng có ma_khach_hang NULL vẫn được xem cùng một nhóm trong GROUP BY. SQL sử dụng quy tắc **không phân biệt (not distinct)** cho việc tạo nhóm, không dùng phép **=** thông thường để xác định nhóm.

Đồng thời:

- **SELECT DISTINCT cot** thường gộp nhiều dòng có cot NULL thành một giá trị NULL trong kết quả.
- **COUNT(DISTINCT cot)** chỉ đếm các giá trị phân biệt **không NULL**, theo quy tắc COUNT(cot).
- **UNION** (không có ALL) loại trùng giữa các dòng theo ngữ nghĩa tập hợp, trong đó NULL có cách xử lý phù hợp với việc loại dòng trùng.

Không suy luận sai rằng vì hai NULL không bằng nhau theo **=**, nên GROUP BY hay DISTINCT phải tách chúng thành nhiều nhóm riêng.

### 13.3. UNIQUE và NULL có quy tắc khác GROUP BY

Ràng buộc **UNIQUE** và chỉ mục duy nhất có cách xử lý NULL thay đổi theo DBMS, loại khóa và tùy chọn cụ thể. Một số hệ cho phép nhiều dòng có giá trị NULL ở cột UNIQUE, hệ khác có quy tắc hạn chế hơn. Do đó, không dùng kết quả của GROUP BY hoặc phép **NULL = NULL** để đoán chính sách UNIQUE.

## 14. CHECK: UNKNOWN có thể được chấp nhận

Đây là một khác biệt rất quan trọng giữa điều kiện lọc dữ liệu và điều kiện ràng buộc.

Trong SQL, một ràng buộc **CHECK** thông thường được thỏa khi biểu thức kiểm tra **không phải FALSE**. Nói cách khác, kết quả TRUE hoặc UNKNOWN đều **không vi phạm CHECK**; chỉ FALSE mới vi phạm.

Ví dụ:

~~~sql
CREATE TABLE san_pham (
    ma_san_pham INTEGER PRIMARY KEY,
    ten_san_pham VARCHAR(100) NOT NULL,
    so_luong INTEGER,
    CONSTRAINT ck_so_luong_duong CHECK (so_luong > 0)
);
~~~

Giả sử DBMS thực thi CHECK theo ngữ nghĩa SQL thông thường:

| so_luong | CHECK (so_luong > 0) | Có bị CHECK từ chối? |
|---:|---|---|
| 10 | TRUE | Không |
| 0 | FALSE | Có |
| -3 | FALSE | Có |
| NULL | UNKNOWN | Không |

Người mới thường tưởng **CHECK (so_luong > 0)** tự động bắt buộc phải nhập số lượng. Không đúng: **so_luong = NULL** vẫn có thể được chấp nhận.

Nếu nghiệp vụ yêu cầu số lượng luôn là số nguyên dương:

~~~sql
CREATE TABLE san_pham (
    ma_san_pham INTEGER PRIMARY KEY,
    ten_san_pham VARCHAR(100) NOT NULL,
    so_luong INTEGER NOT NULL,
    CONSTRAINT ck_so_luong_duong CHECK (so_luong > 0)
);
~~~

**NOT NULL** yêu cầu có giá trị; **CHECK** yêu cầu giá trị đó lớn hơn 0.

### 14.1. So sánh ba nơi dùng điều kiện

| Nơi dùng điều kiện | TRUE | FALSE | UNKNOWN |
|---|---|---|---|
| **WHERE** | Giữ dòng | Loại dòng | Loại dòng |
| **HAVING** | Giữ nhóm | Loại nhóm | Loại nhóm |
| **JOIN ... ON** | Tạo cặp khớp | Không khớp | Không khớp |
| **CHECK** thông thường | Chấp nhận | Vi phạm | Chấp nhận |

Với **LEFT/RIGHT/FULL OUTER JOIN**, một dòng không khớp vẫn có thể được giữ với các cột phía còn thiếu được đệm NULL. Bảng trên mô tả việc **điều kiện ON có tạo cặp khớp hay không**, không phải kết quả cuối cùng của toàn phép OUTER JOIN.

**Lưu ý phiên bản:** một số DBMS/phiên bản lịch sử từng chấp nhận khai báo CHECK nhưng không thực sự áp dụng nó. Khi cần kiểm soát chất lượng dữ liệu, phải dùng phiên bản hỗ trợ và kiểm thử ràng buộc thật.

## 15. UPDATE và DELETE: UNKNOWN cũng không chọn dòng để thay đổi

Quy tắc WHERE chỉ giữ TRUE không chỉ áp dụng cho SELECT.

~~~sql
UPDATE khach_hang
SET trang_thai = 'CAN_XAC_MINH'
WHERE tuoi < 18;
~~~

Giả sử bảng có cột **trang_thai**. Câu lệnh trên cập nhật người có tuổi biết chắc dưới 18; người có tuổi NULL không được cập nhật vì điều kiện UNKNOWN.

Tương tự:

~~~sql
DELETE FROM khach_hang
WHERE email <> 'an@example.com';
~~~

Nếu thực thi, câu lệnh xóa các khách có email khác một giá trị cho trước **và không NULL**, nhưng không xóa khách email NULL. Đây là minh họa ngữ nghĩa; không chạy DELETE trên dữ liệu thật khi chưa xác nhận đúng yêu cầu.

Nếu mục tiêu là xử lý cả những người chưa khai báo email, điều kiện phải thể hiện rõ:

~~~sql
WHERE email <> 'an@example.com'
   OR email IS NULL
~~~

Với UPDATE/DELETE, hiểu sai UNKNOWN có thể làm bỏ sót các bản ghi cần xử lý hoặc xử lý sai quy tắc nghiệp vụ.

## 16. COALESCE, NULLIF và CASE: công cụ xử lý NULL có chủ đích

### 16.1. COALESCE — lấy giá trị đầu tiên không NULL

~~~sql
SELECT
    k.ma_khach_hang,
    COALESCE(k.email, 'CHUA_CUNG_CAP') AS email_hien_thi
FROM khach_hang k;
~~~

**COALESCE(email, 'CHUA_CUNG_CAP')** trả email gốc nếu không NULL, nếu NULL thì trả chuỗi **'CHUA_CUNG_CAP'**.

COALESCE **không làm thay đổi dữ liệu đã lưu**; nó chỉ quyết định giá trị của biểu thức kết quả, trừ khi được dùng trong một câu lệnh ghi dữ liệu.

Đối với số:

~~~sql
SELECT
    d.ma_don_hang,
    COALESCE(d.tong_tien, 0) AS tong_tien_hien_thi
FROM don_hang d;
~~~

Điều này giúp hiển thị 0 thay cho NULL, nhưng cần phân biệt **giá trị thiếu** với **giá trị thật bằng 0**. Việc thay thế chỉ phù hợp khi nghiệp vụ cho phép.

### 16.2. NULLIF — trả NULL khi hai giá trị bằng nhau

~~~sql
SELECT NULLIF(10, 10);  -- NULL
SELECT NULLIF(10, 20);  -- 10
~~~

Một trường hợp dùng là tránh chia cho số 0 trong biểu thức:

~~~sql
SELECT
    so_san_pham,
    tong_doanh_thu / NULLIF(so_san_pham, 0) AS doanh_thu_trung_binh
FROM thong_ke;
~~~

Nếu **so_san_pham = 0**, NULLIF tạo NULL, và phép chia thường trả NULL thay vì thực hiện chia cho 0. Kiểu dữ liệu và cách xử lý lỗi số học vẫn cần xét theo DBMS. Cách viết này bộc lộ ý định rõ hơn giả định rằng:

~~~sql
WHERE so_san_pham <> 0
  AND tong_doanh_thu / so_san_pham > 100
~~~

sẽ luôn đánh giá vế WHERE từ trái sang phải rồi mới thực hiện phép chia.

### 16.3. CASE — mô tả chính sách khi dữ liệu thiếu

~~~sql
SELECT
    k.ma_khach_hang,
    CASE
        WHEN k.email IS NULL THEN 'THIEU_EMAIL'
        WHEN k.email LIKE '%@example.com' THEN 'EMAIL_EXAMPLE'
        ELSE 'EMAIL_KHAC'
    END AS loai_email
FROM khach_hang k;
~~~

Đặt nhánh **IS NULL** lên đầu làm cho trường hợp thiếu thông tin được phân loại rõ. Câu lệnh dễ đọc hơn việc cố biến NULL thành một giá trị đại diện rồi so sánh theo kiểu thông thường.

### 16.4. Có nên dùng IS TRUE, IS FALSE, IS UNKNOWN?

SQL có các phép kiểm tra giá trị chân trị trong một số ngữ cảnh, chẳng hạn **IS TRUE**, **IS FALSE** hoặc **IS UNKNOWN**. Nhưng mức hỗ trợ, cú pháp và kiểu BOOLEAN khác nhau giữa DBMS; SQL Server truyền thống không có kiểu cột BOOLEAN độc lập theo cùng cách PostgreSQL có.

Nếu cần truy vấn đa DBMS, **CASE WHEN ... ELSE**, **IS NULL** và các điều kiện tường minh thường dễ kiểm soát hơn việc dựa vào mọi hệ đều nhận cùng một cú pháp kiểm tra giá trị chân trị.

## 17. NULL trong điều kiện kết hợp: phân tích từng bước

Xét yêu cầu: “Chọn khách có email thuộc example.com **và** đủ 18 tuổi”.

~~~sql
SELECT
    ma_khach_hang,
    ten_khach_hang,
    email,
    tuoi
FROM khach_hang
WHERE email LIKE '%@example.com'
  AND tuoi >= 18
ORDER BY ma_khach_hang;
~~~

Ta suy luận theo từng khách:

| Khách | email LIKE mẫu | tuoi >= 18 | AND | Trong kết quả? |
|---|---|---|---|---|
| An | TRUE | TRUE | TRUE | Có |
| Bình | UNKNOWN | FALSE | FALSE | Không |
| Chi | TRUE | UNKNOWN | UNKNOWN | Không |
| Dũng | UNKNOWN | TRUE | UNKNOWN | Không |
| Em | TRUE | UNKNOWN | UNKNOWN | Không |

Ở dòng Bình, **UNKNOWN AND FALSE = FALSE**; thiếu email không làm thay đổi kết luận chung vì điều kiện tuổi đã sai chắc chắn.

Ở dòng Dũng, **UNKNOWN AND TRUE = UNKNOWN**. Dũng đủ tuổi nhưng chưa biết email có khớp mẫu không, vì vậy dòng không thỏa toàn bộ điều kiện.

### 17.1. Thay AND bằng OR

~~~sql
SELECT
    ma_khach_hang,
    ten_khach_hang
FROM khach_hang
WHERE email LIKE '%@example.com'
   OR tuoi >= 18
ORDER BY ma_khach_hang;
~~~

| Khách | email LIKE mẫu | tuoi >= 18 | OR | Trong kết quả? |
|---|---|---|---|---|
| An | TRUE | TRUE | TRUE | Có |
| Bình | UNKNOWN | FALSE | UNKNOWN | Không |
| Chi | TRUE | UNKNOWN | TRUE | Có |
| Dũng | UNKNOWN | TRUE | TRUE | Có |
| Em | TRUE | UNKNOWN | TRUE | Có |

Các hàng Chi và Em được giữ vì một vế đã TRUE, dù tuổi UNKNOWN. Dũng được giữ vì đã biết tuổi đủ 18, dù email UNKNOWN.

### 17.2. Thay NOT vào toàn bộ điều kiện

Giả sử cần chọn “không thỏa yêu cầu có cả email example.com và tuổi từ 18”:

~~~sql
SELECT ma_khach_hang
FROM khach_hang
WHERE NOT (
    email LIKE '%@example.com'
    AND tuoi >= 18
);
~~~

Kết quả chỉ có **Bình**: vì điều kiện tuổi FALSE nên phép AND FALSE, NOT trở thành TRUE.

Chi, Dũng và Em cho AND UNKNOWN, rồi NOT UNKNOWN vẫn UNKNOWN. Nếu nghiệp vụ muốn **bao gồm cả những trường hợp chưa đủ thông tin để xác nhận**, cần biểu diễn chính sách đó, chẳng hạn:

~~~sql
SELECT ma_khach_hang
FROM khach_hang
WHERE NOT (
    email LIKE '%@example.com'
    AND tuoi >= 18
)
OR email IS NULL
OR tuoi IS NULL;
~~~

Điều kiện trên được thiết kế để lấy tất cả người không được xác nhận thỏa cả hai tiêu chí; với dữ liệu mẫu nó chọn **Bình, Chi, Dũng, Em** và loại **An**. Khi viết điều kiện phủ định trong ứng dụng thực tế, hãy xác định rõ khách có thông tin thiếu cần được giữ hay loại.

## 18. NULL trong truy vấn con và phép so sánh lượng hóa

Ngoài IN/NOT IN, SQL còn có các phép so sánh với kết quả truy vấn con, ví dụ **= ANY** hoặc **> ALL**. Chúng có thể cho UNKNOWN khi tồn tại giá trị NULL và chưa có so sánh nào đủ để khẳng định TRUE/FALSE.

Ý tưởng:

- **x = ANY (tập giá trị)** tương đương về mặt ý nghĩa với “có ít nhất một giá trị bằng x”; nếu không có giá trị khớp nhưng có phép so sánh UNKNOWN, kết quả có thể UNKNOWN.
- **x > ALL (tập giá trị)** cần vượt qua mọi giá trị; nếu có một so sánh FALSE thì cả điều kiện FALSE, còn nếu không có FALSE nhưng có UNKNOWN thì điều kiện có thể UNKNOWN.
- Với tập rỗng, **ANY** có kết quả FALSE và **ALL** có kết quả TRUE theo logic lượng hóa, dù trường hợp đó có vẻ không trực quan.

Mức hỗ trợ cú pháp **ANY/ALL** và các giới hạn truy vấn con khác nhau theo DBMS. Người học nên nắm nguyên tắc: **NULL trong kết quả truy vấn con có thể làm câu hỏi “không thuộc tập nào?” hoặc “lớn hơn tất cả?” trở nên chưa xác định**. Khi cần diễn đạt “có/không có dòng phù hợp”, hãy cân nhắc EXISTS/NOT EXISTS.

## 19. Thứ tự sắp xếp NULL không phải là kết quả của UNKNOWN

**ORDER BY** sắp xếp các giá trị dữ liệu; nó không trực tiếp kiểm tra điều kiện TRUE/FALSE/UNKNOWN như WHERE. Vị trí của NULL khi sắp xếp tăng/giảm phụ thuộc vào DBMS và cấu hình.

Ví dụ:

~~~sql
SELECT ma_khach_hang, email
FROM khach_hang
ORDER BY email ASC;
~~~

Một DBMS có thể đặt NULL trước chuỗi; DBMS khác có thể đặt NULL cuối cùng. Một số hệ có cú pháp **NULLS FIRST** hoặc **NULLS LAST**, nhưng không phải mọi hệ đều dùng cùng cú pháp ở mọi phiên bản.

Nếu muốn **NULL xuống cuối** theo cách dùng CASE rộng rãi:

~~~sql
SELECT
    ma_khach_hang,
    email
FROM khach_hang
ORDER BY
    CASE WHEN email IS NULL THEN 1 ELSE 0 END ASC,
    email ASC,
    ma_khach_hang ASC;
~~~

- Giá trị email không NULL có khóa sắp xếp 0 nên đứng trước.
- Email NULL có khóa sắp xếp 1 nên đứng sau.
- **ma_khach_hang** làm tiêu chí phụ giúp thứ tự ổn định khi email trùng nhau.

Không suy ra rằng **NULL = NULL** UNKNOWN nghĩa là hai NULL “không thể sắp xếp cạnh nhau”. Quy tắc ORDER BY, GROUP BY và phép so sánh bằng là các quy tắc khác nhau của SQL.

## 20. Những khác biệt phương ngữ đáng chú ý

Ngữ nghĩa 3VL cơ bản được sử dụng rộng rãi, nhưng tính năng hỗ trợ và cách thể hiện khác nhau theo DBMS.

| Vấn đề | Điều cần lưu ý khi triển khai |
|---|---|
| So sánh bằng NULL | Phần lớn phép so sánh thông thường cho UNKNOWN; dùng IS NULL / IS NOT NULL khi kiểm tra NULL |
| So sánh an toàn với NULL | PostgreSQL có IS [NOT] DISTINCT FROM; MySQL có **<=>**; SQL Server có IS [NOT] DISTINCT FROM từ SQL Server 2022; các hệ khác cần đối chiếu phiên bản |
| Kiểu BOOLEAN | PostgreSQL có kiểu BOOLEAN thực; SQL Server thường dùng BIT; MySQL thường dùng kiểu số tương ứng; SQLite có mô hình kiểu động |
| Giá trị chuỗi rỗng | Oracle truyền thống xử lý chuỗi rỗng như NULL trong nhiều ngữ cảnh; các hệ khác thường phân biệt |
| Thứ tự NULL trong ORDER BY | Mặc định và cú pháp NULLS FIRST/LAST có thể khác |
| CHECK và UNIQUE | Kiểm thử thực thi ràng buộc theo DBMS, phiên bản, cấu hình; UNIQUE với NULL có khác biệt |
| Hàm liên quan NULL | COALESCE phổ biến; ISNULL, IFNULL, NVL và các hàm riêng có cú pháp/hành vi khác |
| Thiết lập tương thích | Một số chế độ tương thích hoặc thiết lập lịch sử có thể ảnh hưởng hành vi liên quan NULL; không dựa vào chế độ đặc thù khi viết SQL đa hệ |

Một trường hợp lịch sử cần biết là tùy chọn **ANSI_NULLS** của SQL Server, từng liên quan cách so sánh NULL bằng toán tử **=**/**<>**. Trong các phiên bản hiện đại, hãy theo ngữ nghĩa chuẩn và viết **IS NULL** thay vì dựa vào cấu hình cũ để khiến **= NULL** “hoạt động”.

Bất kỳ bảng đối chiếu phương ngữ nào cũng chỉ là hướng dẫn. Khi triển khai thực tế, cần kiểm tra **tên sản phẩm, phiên bản và thiết lập cụ thể**.

## 21. Làm việc với NULL qua JDBC trong ứng dụng Java

Ở tầng SQL, NULL gây UNKNOWN trong phép so sánh. Ở tầng Java, NULL còn ảnh hưởng cách đọc và truyền dữ liệu thông qua JDBC.

### 21.1. Đọc cột số có thể NULL

~~~java
String sql = "SELECT ma_khach_hang, tuoi FROM khach_hang WHERE ma_khach_hang = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, 3);

    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            int tuoi = rs.getInt("tuoi");
            boolean tuoiBiNull = rs.wasNull();

            if (tuoiBiNull) {
                System.out.println("Khách chưa khai báo tuổi");
            } else {
                System.out.println("Tuổi: " + tuoi);
            }
        }
    }
}
~~~

Với **ResultSet.getInt**, JDBC trả giá trị Java nguyên thủy **0** khi cột SQL là NULL; phải gọi **wasNull()** ngay sau thao tác lấy cột đó nếu cần phân biệt NULL với số 0 thật. Có thể dùng **getObject** với kiểu đối tượng phù hợp khi driver hỗ trợ.

### 21.2. Gắn tham số NULL không thay đổi ngữ nghĩa SQL

~~~java
String sql = "SELECT ma_khach_hang FROM khach_hang WHERE email = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setNull(1, java.sql.Types.VARCHAR);

    try (ResultSet rs = statement.executeQuery()) {
        // email = NULL vẫn cho UNKNOWN trên các dòng,
        // nên không phải cách tìm email chưa được khai báo.
    }
}
~~~

Nếu cần tìm email NULL, hãy dùng câu SQL có điều kiện **email IS NULL**. Nếu bộ lọc có thể nhận giá trị cụ thể hoặc NULL, ứng dụng nên có hai nhánh truy vấn hoặc sinh điều kiện thích hợp, thay vì gửi NULL vào toán tử **=** rồi mong có kết quả.

Ví dụ pseudocode:

~~~text
if emailFilter is null:
    use WHERE email IS NULL
else:
    use WHERE email = ?; bind emailFilter
~~~

**Tham số hóa** vẫn cần thiết để truyền giá trị an toàn và đúng kiểu. Nó giúp tránh nối chuỗi SQL từ dữ liệu người dùng, nhưng không thay đổi phép so sánh **= NULL** thành **IS NULL**.

## 22. Quy trình suy luận một điều kiện có NULL

Khi gặp một truy vấn có điều kiện phức tạp, hãy làm theo trình tự sau.

### Bước 1: Xác định cột có thể NULL

Từ lược đồ và nghiệp vụ, xác định cột nào cho phép NULL, cột nào là khóa NOT NULL và NULL có thể được tạo bởi phép OUTER JOIN hay không.

### Bước 2: Tách biểu thức thành điều kiện nhỏ

Ví dụ:

~~~sql
WHERE (tuoi >= 18 OR email IS NOT NULL)
  AND thanh_pho = 'Hà Nội'
~~~

Đặt:

~~~text
P = tuoi >= 18
Q = email IS NOT NULL
R = thanh_pho = 'Hà Nội'
~~~

### Bước 3: Tính kết quả T/F/U cho mỗi vế

Nếu tuổi NULL thì **P = U**. Nếu email NULL thì **Q = F** (không phải U, vì IS NOT NULL cho T/F). Nếu thanh_pho = 'Hà Nội', **R = T**.

### Bước 4: Áp dụng bảng chân trị và dấu ngoặc

~~~text
(P OR Q) AND R
= (U OR F) AND T
= U AND T
= U
~~~

### Bước 5: Áp dụng quy tắc của nơi dùng điều kiện

Nếu điều kiện nằm ở **WHERE**, dòng bị loại. Nếu nó là ràng buộc **CHECK** thông thường, UNKNOWN không làm ràng buộc bị vi phạm. Nếu nằm trong **ON của INNER JOIN**, nó không tạo cặp khớp.

### Bước 6: Xác nhận chính sách dữ liệu thiếu

Nếu yêu cầu kinh doanh muốn coi tuổi NULL như “chưa đủ điều kiện”, hãy quyết định rõ trạng thái xử lý. Không tự coi UNKNOWN là FALSE trong mọi nơi dùng, vì điều đó có thể không đúng với CHECK hoặc các phép toán tiếp theo.

## 23. Các lỗi thường gặp và cách sửa

| Cách nghĩ/cách viết | Vấn đề | Cách xử lý |
|---|---|---|
| **email = NULL** | Kết quả UNKNOWN, không tìm được email NULL | **email IS NULL** |
| **email <> NULL** | Kết quả UNKNOWN, không tìm được email không NULL | **email IS NOT NULL** |
| **NOT (tuoi >= 18)** để lấy mọi người chưa đủ tuổi xác minh | Tuổi NULL vẫn UNKNOWN nên bị lọc | Thêm **OR tuoi IS NULL** nếu nghiệp vụ muốn gồm dữ liệu thiếu |
| **ma NOT IN (SELECT nullable_col ...)** | NULL trong tập con có thể làm điều kiện UNKNOWN | **NOT EXISTS** hoặc lọc NULL trong tập con khi phù hợp |
| **CHECK (so_luong > 0)** để bắt buộc nhập số lượng | CHECK cho phép UNKNOWN | Thêm **so_luong NOT NULL** |
| **COUNT(cot) = COUNT(*)** | COUNT(cot) bỏ qua NULL | Dùng đúng kiểu đếm cần thiết |
| **SUM(cot) = 0** khi toàn NULL | SUM có thể trả NULL | Chỉ dùng **COALESCE(SUM(cot), 0)** nếu nghiệp vụ cho phép |
| Đưa điều kiện cột phải của LEFT JOIN từ ON xuống WHERE | Dòng không khớp bị loại vì FALSE/UNKNOWN | Giữ điều kiện lọc bản ghi ghép trong ON khi cần bảo toàn phía trái |
| Tìm dòng chưa khớp bằng **d.cot_nullable IS NULL** | Dòng khớp vẫn có thể có cột NULL | Kiểm tra khóa NOT NULL phía phải hoặc dùng NOT EXISTS |
| **COALESCE(cot, 0) = 0** để kiểm tra NULL | Gộp NULL với số 0 thật | Dùng IS NULL khi cần đúng sự thiếu vắng |
| Cho rằng **P OR NOT P** luôn TRUE | Nếu P UNKNOWN thì cả biểu thức UNKNOWN | Xử lý NULL một cách tường minh |
| Tin rằng AND luôn đánh giá vế trái trước | Bộ tối ưu không cam kết thứ tự vật lý | Viết biểu thức an toàn độc lập thứ tự, dùng NULLIF hoặc cấu trúc khác phù hợp |

## 24. Bài tập tự luyện

### Bài 1. Tính bảng chân trị

Cho **P = UNKNOWN** và **Q = FALSE**. Hãy tính:

1. NOT P
2. P AND Q
3. P OR Q
4. NOT (P OR Q)

<details>
<summary>Đáp án gợi ý</summary>

1. **NOT UNKNOWN = UNKNOWN**.
2. **UNKNOWN AND FALSE = FALSE**.
3. **UNKNOWN OR FALSE = UNKNOWN**.
4. **NOT UNKNOWN = UNKNOWN**.

</details>

### Bài 2. Chọn dòng với WHERE

Với bảng khách hàng ở phần 2, truy vấn:

~~~sql
SELECT ma_khach_hang
FROM khach_hang
WHERE tuoi < 18 OR email IS NULL
ORDER BY ma_khach_hang;
~~~

trả những mã nào?

<details>
<summary>Đáp án gợi ý</summary>

- An: FALSE OR FALSE = FALSE → loại.
- Bình: TRUE OR TRUE = TRUE → giữ.
- Chi: UNKNOWN OR FALSE = UNKNOWN → loại.
- Dũng: FALSE OR TRUE = TRUE → giữ.
- Em: UNKNOWN OR FALSE = UNKNOWN → loại.

Kết quả **2, 4**.

</details>

### Bài 3. Vì sao NOT IN không trả dòng?

~~~sql
SELECT 1 AS ma
WHERE 1 NOT IN (2, NULL);
~~~

Dự đoán kết quả.

<details>
<summary>Đáp án gợi ý</summary>

**1 IN (2, NULL)** tương ứng **FALSE OR UNKNOWN = UNKNOWN**. Phủ định UNKNOWN vẫn UNKNOWN nên WHERE loại dòng; kết quả rỗng.

Lưu ý khả năng viết SELECT hằng không có FROM có khác biệt giữa các phương ngữ; ví dụ trên nhằm minh họa ngữ nghĩa, có thể cần điều chỉnh cú pháp cho DBMS mục tiêu.

</details>

### Bài 4. CHECK và NOT NULL

Cho bảng:

~~~sql
CREATE TABLE hang_hoa (
    ma INTEGER PRIMARY KEY,
    khoi_luong DECIMAL(10, 2),
    CHECK (khoi_luong > 0)
);
~~~

Một dòng có **khoi_luong = NULL** có bị CHECK từ chối theo ngữ nghĩa SQL thông thường không? Cần làm gì để bắt buộc khối lượng dương và không NULL?

<details>
<summary>Đáp án gợi ý</summary>

Không. **NULL > 0** là UNKNOWN, và CHECK không coi UNKNOWN là vi phạm. Phải thêm **NOT NULL** cho khoi_luong, đồng thời giữ CHECK (khoi_luong > 0).

</details>

### Bài 5. COUNT và SUM

Một bảng có các giá trị tiền: **100**, **NULL**, **200**, **NULL**.

Hãy xác định:

- COUNT(*)
- COUNT(tien)
- SUM(tien)
- AVG(tien)

<details>
<summary>Đáp án gợi ý</summary>

**COUNT(*) = 4**, **COUNT(tien) = 2**, **SUM(tien) = 300**, **AVG(tien) = 150**.

Các phép tổng hợp này bỏ qua giá trị NULL theo ngữ nghĩa của chúng, ngoại trừ COUNT(*) vốn đếm mọi dòng.

</details>

### Bài 6. LEFT JOIN và WHERE

Một ứng dụng cần liệt kê tất cả khách hàng cùng đơn đã thanh toán gần đây, kể cả khách chưa có đơn thanh toán. Nên đặt **d.trang_thai = 'PAID'** trong ON hay WHERE của LEFT JOIN?

<details>
<summary>Đáp án gợi ý</summary>

Đặt trong **ON**:

~~~sql
SELECT k.ma_khach_hang, d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID';
~~~

Nếu đặt trong WHERE, khách không có đơn thanh toán bị loại vì trạng thái phía phải có thể là NULL (UNKNOWN khi so sánh) hoặc một trạng thái khác (FALSE).

</details>

### Bài 7. Phân biệt NULL và UNKNOWN

Giải thích sự khác nhau giữa:

~~~sql
tong_tien * 0.10
~~~

và:

~~~sql
tong_tien * 0.10 > 5000
~~~

khi **tong_tien = NULL**.

<details>
<summary>Đáp án gợi ý</summary>

Biểu thức số học **tong_tien * 0.10** trả kết quả dữ liệu **NULL**. Biểu thức so sánh **tong_tien * 0.10 > 5000** có kết quả logic **UNKNOWN** vì so sánh giá trị NULL với số.

</details>

### Bài 8. Viết điều kiện đúng theo yêu cầu

Yêu cầu nghiệp vụ: “Lấy các khách hàng **chưa được xác nhận có email thuộc example.com**”, bao gồm người chưa nhập email.

Hãy viết điều kiện WHERE.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT ma_khach_hang, email
FROM khach_hang
WHERE email NOT LIKE '%@example.com'
   OR email IS NULL;
~~~

**NOT LIKE** một mình sẽ không chọn email NULL, vì NOT UNKNOWN vẫn UNKNOWN.

</details>

### Bài 9. Đúng hay sai?

Nhận định: “Vì NULL = NULL cho UNKNOWN, các dòng có NULL ở cùng cột chắc chắn được tách thành các nhóm khác nhau trong GROUP BY”.

<details>
<summary>Đáp án gợi ý</summary>

**Sai.** GROUP BY đặt các giá trị NULL thuộc một nhóm chung theo quy tắc nhóm của SQL, khác với so sánh **=**. SELECT DISTINCT cũng xử lý NULL theo quy tắc loại trùng riêng.

</details>

### Bài 10. Đánh giá điều kiện phức tạp

Cho **P = UNKNOWN**, **Q = TRUE**, **R = FALSE**. Tính:

~~~text
(P AND Q) OR (NOT R AND NOT P)
~~~

Nếu là điều kiện WHERE, dòng có được giữ không?

<details>
<summary>Đáp án gợi ý</summary>

~~~text
(P AND Q) = UNKNOWN AND TRUE = UNKNOWN
(NOT R AND NOT P) = TRUE AND UNKNOWN = UNKNOWN
UNKNOWN OR UNKNOWN = UNKNOWN
~~~

WHERE loại dòng vì kết quả không phải TRUE.

</details>

## 25. Ghi nhớ trọng tâm

1. **NULL** biểu thị sự vắng mặt của một giá trị dữ liệu; **UNKNOWN** biểu thị một điều kiện không thể được xác định là TRUE hay FALSE theo phép tính hiện tại.
2. Với toán tử so sánh thông thường, NULL thường dẫn đến UNKNOWN: **NULL = NULL**, **NULL <> 5** và **NULL > 0** đều không phải TRUE hay FALSE.
3. **NOT UNKNOWN = UNKNOWN**, **FALSE AND UNKNOWN = FALSE**, **TRUE OR UNKNOWN = TRUE**. Thuộc bảng chân trị giúp dự đoán điều kiện phức tạp.
4. **WHERE/HAVING** chỉ giữ TRUE; **JOIN ON** chỉ tạo cặp khớp khi TRUE; **CHECK** thông thường chấp nhận TRUE hoặc UNKNOWN và chỉ từ chối FALSE.
5. Dùng **IS NULL/IS NOT NULL** để kiểm tra sự thiếu vắng; đừng thay bằng **= NULL**/**<> NULL**.
6. **NOT IN** có thể gặp bẫy NULL từ tập con. Khi tìm “không có bản ghi liên quan”, **NOT EXISTS** thường dễ diễn đạt đúng hơn.
7. **COUNT(*)** đếm dòng, còn **COUNT(cot)** bỏ qua NULL; **SUM/AVG** bỏ qua giá trị NULL nhưng SUM của nhóm toàn NULL vẫn có thể là NULL.
8. **GROUP BY/DISTINCT** có quy tắc gộp NULL, khác với phép so sánh **=**.
9. **COALESCE**, **CASE**, **NULLIF** giúp xử lý dữ liệu thiếu, nhưng việc thay NULL bằng 0 hoặc chuỗi rỗng luôn cần dựa trên yêu cầu nghiệp vụ.
10. Khi viết SQL thực tế, **nêu rõ chính sách đối với dữ liệu thiếu**, kiểm thử với các dòng NULL và đối chiếu tài liệu của đúng DBMS/phiên bản.

### Tài liệu tra cứu thêm

Có thể đối chiếu với tài liệu SQL chính thức của từng hệ quản trị tại các mục **NULL values**, **comparison operators**, **Boolean expressions**, **logical operators**, **subquery expressions**, **aggregate functions**, **JOIN**, **CHECK constraints**:

- **PostgreSQL Documentation:** các mục *Comparison Functions and Operators*, *Logical Operators*, *Conditional Expressions*, *Subquery Expressions*.
- **MySQL Reference Manual:** các mục *Working with NULL Values*, *Logical Operators*, *Comparison Functions and Operators*.
- **Microsoft Learn — Transact-SQL:** các mục *NULL and UNKNOWN*, *Search Condition*, *IS NULL*, *EXISTS*, *CHECK Constraints*.
- **Oracle Database SQL Language Reference:** các mục *Nulls*, *Conditions*, *Logical Conditions*, *IN Condition*.
- **SQLite Documentation:** các mục *SQL Language Expressions*, *NULL Handling*, *CHECK Constraints*.

Các ví dụ trong bài minh họa logic SQL thông dụng; cú pháp hoặc hành vi đặc thù cần được xác nhận trên hệ quản trị và phiên bản thực tế.
