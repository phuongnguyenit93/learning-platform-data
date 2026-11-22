# EXCEPT và biến thể MINUS theo phương ngữ SQL

> **Module:** Database SQL  
> **Chương:** Phép toán tập hợp  
> **Bài học:** EXCEPT và biến thể MINUS theo phương ngữ

Trong SQL, nhiều câu hỏi không chỉ yêu cầu tìm những dòng **có** trong một tập kết quả, mà còn yêu cầu tìm những dòng **có ở tập A nhưng không có ở tập B**. Ví dụ: “Khách hàng nào có trong danh sách đăng ký nhưng chưa từng đặt hàng?”, “Mã sản phẩm nào có ở hệ thống cũ nhưng không có trong hệ thống mới?”, “Những quyền nào đã được cấp nhưng không nằm trong danh sách quyền được phép?”.

Phép toán tập hợp **EXCEPT** (và tên gọi **MINUS** trong một số phương ngữ, đặc biệt ở Oracle Database truyền thống) diễn đạt trực tiếp thao tác **lấy hiệu của hai tập kết quả**. Tuy nhiên, để dùng đúng, người học phải hiểu quy tắc loại trùng, cách so sánh hàng có NULL, thứ tự cột, tính tương thích kiểu dữ liệu và khả năng hỗ trợ cú pháp của từng hệ quản trị.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **hiệu tập hợp A − B** và đọc đúng biểu thức **SELECT ... EXCEPT SELECT ...**.
- Phân biệt **EXCEPT mặc định** với **EXCEPT ALL**; dự đoán kết quả khi đầu vào có dòng trùng.
- Hiểu rằng phép trừ tập hợp SQL xét **toàn bộ bộ giá trị của hàng được SELECT**, không dựa vào tên bảng, khóa chính hay các cột bị bỏ khỏi danh sách SELECT.
- Nắm cách **NULL** được xử lý trong phép toán tập hợp, khác với phép **=** thông thường trong WHERE và JOIN.
- Biết điều kiện **hai phía phải có cùng số cột** và các cột tương ứng phải tương thích về kiểu dữ liệu.
- Sử dụng **MINUS** trên Oracle truyền thống và chuyển đổi hợp lý giữa EXCEPT/MINUS theo DBMS.
- Biết sự khác nhau giữa **EXCEPT**, **NOT EXISTS**, **NOT IN**, **LEFT JOIN ... IS NULL** và **EXCEPT ALL**.
- Phối hợp EXCEPT với **UNION**, **INTERSECT**, **WHERE**, **CTE** và **ORDER BY** mà không hiểu nhầm độ ưu tiên.
- Lựa chọn mẫu truy vấn phù hợp cho kiểm toán, đồng bộ, phát hiện dữ liệu thiếu, so sánh dữ liệu giữa các phiên bản.
- Viết các ca kiểm thử có dữ liệu trùng, NULL, giá trị không khớp, nhiều cột và kiểu dữ liệu đặc biệt.

## 2. Ý tưởng toán học: A trừ B

Giả sử:

~~~text
Tập A = {1, 2, 3, 4}
Tập B = {2, 4, 5}

A - B = {1, 3}
B - A = {5}
~~~

**A − B** là những phần tử thuộc A nhưng **không thuộc B**.

Điểm quan trọng:

- Phép hiệu **có hướng**: A − B thường khác B − A.
- Nó **không** lấy những phần tử chỉ có trong B.
- Phần tử xuất hiện ở cả hai tập bị loại khỏi kết quả A − B.
- Kết quả của phép hiệu tập hợp thông thường không chứa hai bản sao của cùng một phần tử.

Trong SQL, có thể biểu diễn hiệu tập hợp:

~~~sql
SELECT ma_san_pham
FROM san_pham_he_thong_cu

EXCEPT

SELECT ma_san_pham
FROM san_pham_he_thong_moi;
~~~

Ý nghĩa: các mã sản phẩm xuất hiện ở bảng hệ thống cũ nhưng không xuất hiện trong bảng hệ thống mới.

Một số phương ngữ dùng tên khác:

~~~sql
SELECT ma_san_pham
FROM san_pham_he_thong_cu

MINUS

SELECT ma_san_pham
FROM san_pham_he_thong_moi;
~~~

**EXCEPT** và **MINUS** trong trường hợp mặc định loại trùng có chung ý tưởng **phép hiệu tập hợp**. Nhưng chúng **không phải hai từ khóa có thể thay thế tùy ý trên mọi DBMS**, và dạng ALL cũng có mức hỗ trợ khác nhau.

## 3. Bộ dữ liệu minh họa

Để thấy đủ những trường hợp khó, giả sử có hai nguồn ghi mã sản phẩm:

**nguon_a** — danh sách từ hệ thống A

| stt | ma_san_pham |
|---:|---|
| 1 | P01 |
| 2 | P01 |
| 3 | P02 |
| 4 | P03 |
| 5 | NULL |
| 6 | NULL |
| 7 | P04 |

**nguon_b** — danh sách từ hệ thống B

| stt | ma_san_pham |
|---:|---|
| 101 | P01 |
| 102 | P03 |
| 103 | P03 |
| 104 | NULL |
| 105 | P05 |

Dữ liệu được thiết kế có chủ đích:

- **P01** xuất hiện hai lần trong A nhưng một lần trong B.
- **P02** và **P04** chỉ có ở A.
- **P03** xuất hiện một lần trong A nhưng hai lần trong B.
- Cả hai nguồn đều có **NULL**; A có hai NULL, B có một NULL.
- **P05** chỉ có ở B.

Cột **stt** chỉ để nhận diện từng bản ghi nguồn. Khi thực hiện phép hiệu trên **ma_san_pham**, ta sẽ **không** đưa stt vào danh sách SELECT. Nếu chọn cả stt, phép hiệu sẽ so sánh **cặp (stt, ma_san_pham)** và cho kết quả khác.

### 3.1. Cấu trúc bảng minh họa

~~~sql
CREATE TABLE nguon_a (
    stt INTEGER PRIMARY KEY,
    ma_san_pham VARCHAR(20)
);

CREATE TABLE nguon_b (
    stt INTEGER PRIMARY KEY,
    ma_san_pham VARCHAR(20)
);
~~~

Để nạp dữ liệu trên các DBMS hỗ trợ cú pháp INSERT nhiều hàng theo VALUES (ví dụ PostgreSQL, MySQL hiện đại, SQL Server và SQLite), có thể dùng:

~~~sql
INSERT INTO nguon_a (stt, ma_san_pham) VALUES
    (1, 'P01'),
    (2, 'P01'),
    (3, 'P02'),
    (4, 'P03'),
    (5, NULL),
    (6, NULL),
    (7, 'P04');

INSERT INTO nguon_b (stt, ma_san_pham) VALUES
    (101, 'P01'),
    (102, 'P03'),
    (103, 'P03'),
    (104, NULL),
    (105, 'P05');
~~~

**Oracle Database 19c** dùng cách nạp nhiều hàng khác, chẳng hạn INSERT ALL hoặc từng INSERT riêng; ví dụ trên được cung cấp như tập dữ liệu logic chứ không cam kết chạy nguyên văn trên mọi phiên bản Oracle.

Những truy vấn tiếp theo mô tả ngữ nghĩa SQL chung. Cú pháp cụ thể và khả năng hỗ trợ sẽ được đối chiếu ở phần phương ngữ.

## 4. EXCEPT mặc định: trả giá trị có ở A nhưng không ở B

~~~sql
SELECT ma_san_pham
FROM nguon_a

EXCEPT

SELECT ma_san_pham
FROM nguon_b;
~~~

Ta có các giá trị phân biệt:

~~~text
A: {P01, P02, P03, P04, NULL}
B: {P01, P03, P05, NULL}

A EXCEPT B: {P02, P04}
~~~

Kết quả:

| ma_san_pham |
|---|
| P02 |
| P04 |

**P01** và **P03** bị loại vì có ở cả hai bên. **NULL** cũng không còn trong kết quả vì cả hai nguồn đều chứa NULL, theo quy tắc so sánh dòng của phép tập hợp. P05 không xuất hiện vì nó chỉ có ở **bên phải**.

Kết quả EXCEPT mặc định có **mỗi hàng phân biệt tối đa một lần**, nên hai bản ghi P01 ở A không làm P01 xuất hiện trong kết quả.

### 4.1. EXCEPT có hướng

Đảo hai SELECT:

~~~sql
SELECT ma_san_pham
FROM nguon_b

EXCEPT

SELECT ma_san_pham
FROM nguon_a;
~~~

Kết quả:

| ma_san_pham |
|---|
| P05 |

Đây là tập **có ở B nhưng thiếu ở A**.

Hai phép hiệu này thường trả các kết quả khác nhau:

~~~text
A EXCEPT B != B EXCEPT A
~~~

Nếu yêu cầu là **“tất cả điểm khác biệt giữa hai nguồn”**, chỉ dùng một chiều EXCEPT là chưa đủ. Cần lấy cả hai chiều, hoặc dùng một phương án đối soát khác với nhãn nguồn.

### 4.2. EXCEPT DISTINCT có nghĩa gì?

Trong nhiều hệ, EXCEPT mặc định hoạt động theo ngữ nghĩa **DISTINCT**. Ở các DBMS hỗ trợ cú pháp tường minh, có thể gặp:

~~~sql
SELECT ma_san_pham FROM nguon_a
EXCEPT DISTINCT
SELECT ma_san_pham FROM nguon_b;
~~~

Về ý nghĩa tập hợp, kết quả giống EXCEPT không có ALL. Tuy nhiên, **không phải mọi DBMS đều chấp nhận ghi DISTINCT ngay sau EXCEPT**, dù chúng vẫn mặc định loại trùng.

Để viết SQL dễ chuyển hệ, có thể dùng **EXCEPT** hoặc **MINUS** theo cú pháp sản phẩm mà không cố thêm DISTINCT khi không cần.

## 5. EXCEPT không giống WHERE lọc từng dòng

Xét:

~~~sql
SELECT ma_san_pham
FROM nguon_a
WHERE ma_san_pham <> 'P01';
~~~

WHERE này chỉ loại **P01**. Nó vẫn có thể trả **P03**, **NULL** bị loại vì UNKNOWN, còn **P02**, **P04** được giữ.

Trong khi:

~~~sql
SELECT ma_san_pham FROM nguon_a
EXCEPT
SELECT ma_san_pham FROM nguon_b;
~~~

loại **mọi giá trị có ở B**, gồm P01, P03 và NULL theo ngữ nghĩa tập hợp.

**WHERE** áp dụng điều kiện cho từng dòng của một nguồn. **EXCEPT** lấy hiệu của **hai kết quả SELECT**. Chúng có thể giải quyết các bài toán liên quan, nhưng không tự động tương đương.

### 5.1. Không cần hai bảng vật lý khác nhau

EXCEPT có thể dùng giữa:

- Hai bảng thật.
- Hai truy vấn con cùng một bảng với bộ lọc khác nhau.
- Hai CTE.
- Hai kết quả tổng hợp.
- Hai bản chụp dữ liệu.
- Hai tập giá trị được xây dựng trong cùng câu truy vấn.

Ví dụ: “Những khách từng mua hàng trước tháng 3 nhưng không có đơn trong tháng 3”:

~~~sql
SELECT ma_khach_hang
FROM don_hang
WHERE ngay_dat < DATE '2026-03-01'
  AND ma_khach_hang IS NOT NULL

EXCEPT

SELECT ma_khach_hang
FROM don_hang
WHERE ngay_dat >= DATE '2026-03-01'
  AND ngay_dat < DATE '2026-04-01'
  AND ma_khach_hang IS NOT NULL;
~~~

Câu trên mang tính minh họa trên DBMS nhận cú pháp **DATE 'YYYY-MM-DD'**. SQL Server thường cần bind tham số ngày hoặc dùng biểu thức/cách chuyển kiểu tương ứng.

Điểm đáng chú ý: SELECT bên phải chỉ loại khách **có đơn trong tháng 3**; khách có đơn vào tháng 4 nhưng không có đơn tháng 3 vẫn có thể nằm trong kết quả. Điều kiện phải khớp với yêu cầu nghiệp vụ.

## 6. EXCEPT ALL: phép hiệu theo số lần xuất hiện

SQL thường xử lý tập kết quả theo ngữ nghĩa **đa tập** (*bag/multiset*). Một giá trị có thể xuất hiện nhiều lần. Dạng **EXCEPT ALL** (khi DBMS hỗ trợ) không tự loại mọi bản sao của phần tử còn lại như EXCEPT mặc định.

Với mỗi giá trị v:

\[
\operatorname{count}_{A\ \mathrm{EXCEPT\ ALL}\ B}(v)
=
\max(\operatorname{count}_{A}(v)-\operatorname{count}_{B}(v),\,0)
\]

Ý nghĩa:

1. Đếm số lần giá trị v xuất hiện bên trái.
2. Đếm số lần giá trị v xuất hiện bên phải.
3. Trừ số lần bên phải khỏi bên trái.
4. Nếu kết quả âm, dùng 0; nếu dương, giữ đúng số lần chênh lệch.

Với dữ liệu phần 3:

| Giá trị | Số lần trong A | Số lần trong B | EXCEPT mặc định | EXCEPT ALL |
|---|---:|---:|---:|---:|
| P01 | 2 | 1 | 0 | 1 |
| P02 | 1 | 0 | 1 | 1 |
| P03 | 1 | 2 | 0 | 0 |
| P04 | 1 | 0 | 1 | 1 |
| P05 | 0 | 1 | 0 | 0 |
| NULL | 2 | 1 | 0 | 1 |

Truy vấn:

~~~sql
SELECT ma_san_pham
FROM nguon_a

EXCEPT ALL

SELECT ma_san_pham
FROM nguon_b;
~~~

Kết quả có **bốn dòng**, xét như đa tập:

| ma_san_pham |
|---|
| P01 |
| P02 |
| P04 |
| NULL |

Không có thứ tự kết quả được bảo đảm nếu không ORDER BY.

### 6.1. Vì sao P01 và NULL xuất hiện trong EXCEPT ALL?

- A có **hai P01**, B có **một P01**, nên còn **một P01**.
- A có **hai NULL**, B có **một NULL**, nên còn **một NULL**.
- A có một P03, B có hai P03, nên còn **0 P03**.

Đây là khác biệt lớn giữa **“có tồn tại trong B hay không”** và **“B có đủ số bản sao để đối trừ A hay không”**.

### 6.2. Đảo chiều EXCEPT ALL

~~~sql
SELECT ma_san_pham FROM nguon_b
EXCEPT ALL
SELECT ma_san_pham FROM nguon_a;
~~~

Với dữ liệu mẫu, kết quả theo đa tập:

| ma_san_pham |
|---|
| P03 |
| P05 |

B có hai P03, A có một P03 nên bên B còn một; P05 chỉ có ở B.

### 6.3. EXCEPT ALL không được hỗ trợ ở mọi DBMS

- PostgreSQL hỗ trợ EXCEPT ALL.
- MySQL từ các phiên bản 8.0.31 có EXCEPT và hỗ trợ cú pháp ALL trong phép toán tập hợp tương ứng.
- Oracle Database ở thế hệ mới như 23ai có thêm các biến thể ALL cho những toán tử tập hợp, gồm EXCEPT/MINUS theo tài liệu phiên bản.
- SQL Server và SQLite trong các phiên bản thông dụng có EXCEPT theo ngữ nghĩa loại trùng nhưng **không có EXCEPT ALL trực tiếp**.

**Không viết EXCEPT ALL trong câu SQL đa hệ rồi giả định mọi server đều chấp nhận.** Nếu bài toán cần bảo toàn số bản sao và sản phẩm không hỗ trợ ALL, phải thiết kế truy vấn mô phỏng hoặc xử lý ở tầng ứng dụng.

## 7. Vì sao EXCEPT không phụ thuộc vào khóa chính?

EXCEPT so sánh **những cột mà SELECT thực sự trả ra**, không tự biết hay tự dùng khóa chính của bảng nguồn để so sánh.

Ví dụ:

~~~sql
SELECT stt, ma_san_pham
FROM nguon_a

EXCEPT

SELECT stt, ma_san_pham
FROM nguon_b;
~~~

Ở tập mẫu, **stt bên A** là 1–7, còn **stt bên B** là 101–105. Không có cặp (stt, ma_san_pham) nào trùng giữa hai phía. Vì vậy, kết quả trên gồm **cả 7 cặp hàng của A** (không phải chỉ P02/P04).

### 7.1. Chọn đúng khóa so sánh

Khi muốn tìm **mã sản phẩm chỉ có ở A**, hãy SELECT **mã sản phẩm**, không chọn thêm ID của bản ghi nguồn.

Khi muốn tìm **những bản ghi có cùng mã nhưng nội dung khác**, EXCEPT trên một cột mã **không đủ**. Cần so sánh thêm các thuộc tính quan trọng hoặc JOIN theo mã để xác định thay đổi.

Ví dụ, nếu hai nguồn có:

~~~text
A: (ma = P01, gia = 100000)
B: (ma = P01, gia = 120000)
~~~

Thì:

~~~sql
SELECT ma FROM a
EXCEPT
SELECT ma FROM b;
~~~

không trả P01 vì mã có ở cả hai.

Nhưng:

~~~sql
SELECT ma, gia FROM a
EXCEPT
SELECT ma, gia FROM b;
~~~

có thể trả **(P01, 100000)** vì cặp (mã, giá) ở A không có trong B.

**Chọn cột chính là xác định định nghĩa “hai hàng giống nhau” trong bài toán đang giải.**

## 8. Hai vế phải có cùng số cột

Các phép toán tập hợp không thể ghép hai danh sách SELECT với số lượng cột khác nhau.

Ví dụ không hợp lệ:

~~~sql
-- Bên trái 2 cột, bên phải 1 cột.
SELECT ma_san_pham, ten_san_pham
FROM san_pham_a

EXCEPT

SELECT ma_san_pham
FROM san_pham_b;
~~~

Để sửa, hai vế phải trả cùng số cột, theo cùng thứ tự ý nghĩa:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham_a

EXCEPT

SELECT ma_san_pham, ten_san_pham
FROM san_pham_b;
~~~

Không phải hai cột chỉ cần giống **tên** là đủ; SQL so sánh các cột **theo vị trí**.

### 8.1. Thứ tự cột quyết định ý nghĩa so sánh

Giả sử hai bảng có cột **ma_san_pham** và **ten_san_pham** đều là chuỗi. Câu sau có thể chạy mà sai mục đích:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham_a

EXCEPT

SELECT ten_san_pham, ma_san_pham
FROM san_pham_b;
~~~

Cột thứ nhất bên trái bị so với **tên**, còn cột thứ hai bên trái bị so với **mã**. Vì cả hai đều là chuỗi, DBMS có thể không báo lỗi kiểu dữ liệu.

Khi dùng phép toán tập hợp, hãy kiểm tra:

1. Số cột hai vế bằng nhau.
2. Cột thứ i ở hai vế mang **cùng ý nghĩa nghiệp vụ**.
3. Kiểu dữ liệu tương ứng tương thích.
4. Ngữ nghĩa **NULL**, collation và việc chuẩn hóa cùng quy tắc.
5. Những cột bổ sung vô tình làm thay đổi định nghĩa so sánh.

### 8.2. Tên cột đầu ra đến từ đâu?

Trong nhiều DBMS, tên cột kết quả của một biểu thức tập hợp lấy từ **SELECT bên trái**.

~~~sql
SELECT ma_san_pham AS ma
FROM nguon_a

EXCEPT

SELECT ma_san_pham AS ma_khac
FROM nguon_b;
~~~

Tên kết quả thường là **ma**, không phải ma_khac. Tuy nhiên, cách cho phép alias ở ORDER BY và phạm vi tên có thể khác theo phương ngữ; khi cần chắc chắn, bọc toàn phép hiệu bằng CTE hoặc bảng dẫn xuất và đặt tên rõ.

## 9. Kiểu dữ liệu phải tương thích

Hai cột tương ứng không chỉ cần cùng vị trí mà còn phải thuộc các kiểu dữ liệu mà DBMS cho phép so sánh trong phép toán tập hợp.

Ví dụ hợp lý:

~~~sql
SELECT ma_khach_hang FROM khach_hang_he_cu
EXCEPT
SELECT ma_khach_hang FROM khach_hang_he_moi;
~~~

Nếu cả hai cột là cùng kiểu INTEGER, ý nghĩa và phép so sánh rõ ràng.

Rủi ro xuất hiện khi:

- Một bên là **INTEGER**, bên kia là **VARCHAR** lưu số dưới dạng chữ.
- Một bên **DATE**, bên kia **TIMESTAMP**.
- Một bên **DECIMAL(12,2)**, bên kia **FLOAT/DOUBLE**.
- Hai bên dùng collation khác nhau cho mã chuỗi.
- Một bên là kiểu văn bản/binary đặc biệt không hỗ trợ so sánh tập hợp.
- Hai bên có độ dài/độ chính xác khác nhau và DBMS thực hiện ép kiểu theo quy tắc riêng.

SQL Server, PostgreSQL, MySQL, Oracle và SQLite có hệ thống kiểu dữ liệu và phép chuyển kiểu khác nhau. Ví dụ, không nên kỳ vọng mọi hệ chấp nhận so sánh trực tiếp một cột VARCHAR với một cột INTEGER theo cùng cách.

### 9.1. Chuẩn hóa kiểu rõ ràng trước khi trừ

Nếu mã là số nhưng nguồn khác lưu như chuỗi:

~~~sql
SELECT CAST(ma_khach_hang AS VARCHAR(30)) AS ma
FROM khach_hang_a

EXCEPT

SELECT ma_khach_hang_text AS ma
FROM khach_hang_b;
~~~

Đây chỉ là minh họa một hướng chuyển kiểu; **CAST sang chuỗi cũng có thể sai nghiệp vụ** nếu có số 00123, ký tự 0 đầu, khoảng trắng hoặc định dạng địa phương. Việc chọn miền so sánh phải dựa trên ý nghĩa mã chứ không chỉ “làm cho câu SQL chạy được”.

### 9.2. Với dữ liệu thời gian

Nếu muốn so sánh **ngày lịch**, hãy chọn/cast cả hai nguồn thành cùng đơn vị DATE theo DBMS và vùng giờ đúng. Nếu muốn so sánh **thời điểm tuyệt đối**, phải thống nhất timezone và kiểu timestamp trước khi EXCEPT. Hai giá trị hiển thị cùng ngày nhưng là hai thời điểm khác nhau có thể không tương đương.

### 9.3. Với dữ liệu tiền

Nếu một nguồn lưu 100000.00 dưới dạng DECIMAL và nguồn khác lưu kết quả tính bằng FLOAT, việc so sánh giá chính xác có thể chịu sai số. Khi đối soát tiền, cần quy định **currency, precision, scale và rounding** trước, không trừ hai kết quả theo kiểu dữ liệu bất kỳ.

## 10. NULL trong EXCEPT không giống NULL trong WHERE

Đây là một trong những phần quan trọng nhất.

Trong so sánh SQL thông thường:

~~~sql
NULL = NULL
~~~

cho kết quả **UNKNOWN**, không phải TRUE.

Nhưng trong các phép toán tập hợp **EXCEPT/INTERSECT** và xử lý **DISTINCT**, hai hàng có NULL ở cùng vị trí tương ứng có thể được xem là **không phân biệt được (not distinct)** để xác định một hàng xuất hiện ở cả hai tập.

Xét:

~~~text
A gồm: NULL, NULL, P02
B gồm: NULL
~~~

Khi lấy **A EXCEPT B** theo ngữ nghĩa DISTINCT:

~~~text
Kết quả: P02
~~~

NULL không được giữ vì đã có một hàng NULL tương ứng ở bên phải.

Khi lấy **A EXCEPT ALL B** trên DBMS hỗ trợ:

~~~text
Kết quả: NULL, P02
~~~

A có hai NULL, B có một NULL nên còn một bản sao NULL.

### 10.1. Không suy luận từ NULL = NULL

Một người mới học có thể nghĩ:

> “NULL không bằng NULL, vậy NULL ở A phải còn lại khi trừ B.”

Kết luận đó **sai** với EXCEPT. Phép toán tập hợp dùng **ngữ nghĩa so khớp và loại trùng của hàng**, khác với phép so sánh ba giá trị trong WHERE.

Quy tắc trực quan:

- Hai hàng có cùng số cột.
- Ở từng vị trí, các giá trị giống nhau theo quy tắc so sánh của phép tập hợp, bao gồm trường hợp hai vị trí cùng NULL.
- Khi tất cả các vị trí tương ứng không phân biệt, hai hàng được coi là trùng đối với EXCEPT DISTINCT.

### 10.2. NULL trong nhiều cột

Giả sử:

~~~text
A:
(P01, NULL)
(P02, NULL)
(P03, 10)

B:
(P01, NULL)
(P02, 10)
(P03, NULL)
~~~

**A EXCEPT B** trả:

~~~text
(P02, NULL)
(P03, 10)
~~~

Vì:

- **(P01, NULL)** có cả hai phía, bị loại.
- **(P02, NULL)** khác **(P02, 10)**, nên ở lại.
- **(P03, 10)** khác **(P03, NULL)**, nên ở lại.

Một hàng trùng khi **toàn bộ các cột đã SELECT** được coi là tương ứng, không phải chỉ vì cột mã giống nhau.

### 10.3. Chuỗi rỗng có thể thay đổi kết quả

Oracle Database truyền thống xử lý chuỗi rỗng **''** như NULL trong nhiều ngữ cảnh, trong khi nhiều DBMS khác phân biệt NULL với chuỗi độ dài 0. Nếu so sánh dữ liệu văn bản giữa nguồn Oracle và nguồn khác, cần biết giá trị rỗng đã được chuyển đổi thế nào trước khi dùng MINUS/EXCEPT.

## 11. EXCEPT so với NOT EXISTS

Một bài toán phổ biến là:

> “Lấy mã sản phẩm trong A chưa có trong B.”

Dùng EXCEPT:

~~~sql
SELECT ma_san_pham FROM nguon_a
EXCEPT
SELECT ma_san_pham FROM nguon_b;
~~~

Dùng NOT EXISTS:

~~~sql
SELECT a.ma_san_pham
FROM nguon_a a
WHERE NOT EXISTS (
    SELECT 1
    FROM nguon_b b
    WHERE b.ma_san_pham = a.ma_san_pham
);
~~~

Hai truy vấn **không tương đương trong mọi tình huống**.

### 11.1. Khác biệt thứ nhất: dòng trùng

EXCEPT mặc định loại trùng. NOT EXISTS lọc các **dòng gốc của A**, nên giữ các bản sao nếu chúng đều không có đối tượng khớp.

Ví dụ:

~~~text
A: P02, P02, P03
B: P03
~~~

- **A EXCEPT B** → một dòng P02.
- **NOT EXISTS** với phép bằng → hai dòng P02.

Nếu cần danh sách mã phân biệt từ NOT EXISTS, phải dùng:

~~~sql
SELECT DISTINCT a.ma_san_pham
FROM nguon_a a
WHERE NOT EXISTS (
    SELECT 1
    FROM nguon_b b
    WHERE b.ma_san_pham = a.ma_san_pham
);
~~~

### 11.2. Khác biệt thứ hai: NULL trong khóa

Với dữ liệu mẫu, B có NULL, A cũng có NULL. EXCEPT mặc định loại NULL khỏi kết quả A EXCEPT B.

Nhưng câu:

~~~sql
WHERE NOT EXISTS (
    SELECT 1 FROM nguon_b b
    WHERE b.ma_san_pham = a.ma_san_pham
)
~~~

**không coi NULL của A khớp với NULL của B**. Vì phép **NULL = NULL** cho UNKNOWN, truy vấn con không có dòng nào thỏa so sánh bằng cho khóa a.ma_san_pham NULL. Vì vậy, các dòng NULL ở A được giữ lại trong kết quả NOT EXISTS.

Với dữ liệu mẫu, NOT EXISTS trả (theo đa tập) **P02, P04, NULL, NULL**; nếu thêm DISTINCT thì trả **P02, P04, NULL**. Trong khi EXCEPT DISTINCT trả **P02, P04**.

### 11.3. Cách mô phỏng EXCEPT DISTINCT bằng NOT EXISTS

Khi cần so khớp NULL giống ngữ nghĩa tập hợp và DBMS hỗ trợ, có thể viết:

~~~sql
SELECT DISTINCT a.ma_san_pham
FROM nguon_a a
WHERE NOT EXISTS (
    SELECT 1
    FROM nguon_b b
    WHERE b.ma_san_pham IS NOT DISTINCT FROM a.ma_san_pham
);
~~~

**IS NOT DISTINCT FROM** coi hai NULL là tương đương trong phép so sánh.

Nếu DBMS không hỗ trợ cú pháp này, với một cột có thể dùng:

~~~sql
SELECT DISTINCT a.ma_san_pham
FROM nguon_a a
WHERE NOT EXISTS (
    SELECT 1
    FROM nguon_b b
    WHERE b.ma_san_pham = a.ma_san_pham
       OR (b.ma_san_pham IS NULL AND a.ma_san_pham IS NULL)
);
~~~

Với trường hợp nhiều cột, mỗi vị trí phải được so sánh theo **ngữ nghĩa null-safe tương ứng**, và SELECT DISTINCT phải bao gồm **toàn bộ bộ cột đang được trừ**. Ngoài ra, collation và kiểu dữ liệu có thể khiến kết quả khác; không coi đây là bản thay thế hoàn toàn tự động cho mọi EXCEPT có kiểu dữ liệu đặc biệt.

### 11.4. Khi nào NOT EXISTS thuận tiện hơn?

- Cần trả **nhiều cột của A**, nhưng chỉ muốn kiểm tra tồn tại theo **một khóa** hoặc một quan hệ.
- Muốn **giữ các dòng trùng** của A có chủ đích.
- Muốn thêm điều kiện tương quan giữa A và B ngoài phép bằng của toàn hàng.
- DBMS không hỗ trợ EXCEPT hoặc cần kiểm soát NULL theo quy tắc nghiệp vụ.
- Muốn biểu diễn điều kiện **“không có bản ghi liên quan”** rõ ràng.

EXCEPT thuận tiện hơn khi yêu cầu là **hiệu của hai tập dòng có cùng cấu trúc**.

## 12. EXCEPT so với NOT IN

Xét:

~~~sql
SELECT ma_san_pham
FROM nguon_a
WHERE ma_san_pham NOT IN (
    SELECT ma_san_pham
    FROM nguon_b
);
~~~

Câu này trông giống phép hiệu, nhưng **NOT IN** có một bẫy NULL rất lớn.

Vì nguon_b chứa NULL, với mã P02 hoặc P04:

~~~text
P02 <> P01  -> TRUE
P02 <> P03  -> TRUE
P02 <> P05  -> TRUE
P02 <> NULL -> UNKNOWN
~~~

Ở mức ý nghĩa, NOT IN yêu cầu không bằng mọi phần tử. Khi có một phép so sánh UNKNOWN và không có phần tử nào bằng chắc chắn, toàn bộ điều kiện có thể thành UNKNOWN; WHERE loại dòng.

Với dữ liệu mẫu, câu **NOT IN** nêu trên không trả P02 hay P04, trong khi EXCEPT trả cả hai.

### 12.1. Lọc NULL ở tập con có đủ không?

Có thể viết:

~~~sql
SELECT DISTINCT a.ma_san_pham
FROM nguon_a a
WHERE a.ma_san_pham IS NOT NULL
  AND a.ma_san_pham NOT IN (
      SELECT b.ma_san_pham
      FROM nguon_b b
      WHERE b.ma_san_pham IS NOT NULL
  );
~~~

Trong dữ liệu mẫu, câu này trả P02, P04. Nhưng nó chủ động **loại NULL ở A**; vì vậy chỉ tương đương EXCEPT trong trường hợp cụ thể khi B cũng có NULL và quy tắc nghiệp vụ chấp nhận. Nếu B không có NULL, **A EXCEPT B có thể giữ một dòng NULL**, còn truy vấn trên vẫn loại NULL.

Do đó, không thể nói chỉ cần thêm **IS NOT NULL** là đã mô phỏng EXCEPT trong mọi dữ liệu.

### 12.2. Lựa chọn khi dữ liệu có thể NULL

- Nếu muốn **hiệu tập hợp đúng theo các cột SELECT**: dùng EXCEPT/MINUS khi hỗ trợ.
- Nếu muốn **không có bản ghi liên quan**: dùng NOT EXISTS với điều kiện so sánh được thiết kế đúng.
- Nếu vẫn dùng NOT IN: phải chứng minh giá trị truy vấn con không NULL và xác định chính sách với giá trị NULL phía ngoài.

## 13. EXCEPT so với LEFT JOIN ... IS NULL

Một mẫu anti-join phổ biến:

~~~sql
SELECT a.ma_san_pham
FROM nguon_a a
LEFT JOIN nguon_b b
    ON b.ma_san_pham = a.ma_san_pham
WHERE b.ma_san_pham IS NULL;
~~~

Mẫu này giúp tìm các giá trị A không khớp B bằng phép **=**, nhưng có hai khác biệt so với EXCEPT:

1. **Không tự loại trùng** từ A.
2. NULL ở A không khớp NULL ở B bằng dấu bằng, nên vẫn được giữ.

Với dữ liệu mẫu, kết quả có thể gồm **P02, P04, NULL, NULL**, tương tự NOT EXISTS dùng phép =.

Nếu dùng một điều kiện JOIN **null-safe** cho phép NULL khớp NULL:

~~~sql
SELECT DISTINCT a.ma_san_pham
FROM nguon_a a
LEFT JOIN nguon_b b
    ON b.ma_san_pham = a.ma_san_pham
    OR (b.ma_san_pham IS NULL AND a.ma_san_pham IS NULL)
WHERE b.stt IS NULL;
~~~

Ta phải kiểm tra **b.stt**, giả định là khóa chính NOT NULL của bảng B, **không** kiểm tra **b.ma_san_pham**. Với điều kiện null-safe, một dòng B thật có ma_san_pham NULL vẫn có thể khớp, nên kiểm tra b.ma_san_pham IS NULL sẽ nhận nhầm nó là không khớp.

Đây là một điểm rất quan trọng khi mô phỏng EXCEPT bằng LEFT JOIN: **điều kiện xác định không khớp phải dựa trên cột của B được bảo đảm không NULL ở dòng B thật** hoặc một cấu trúc anti-join rõ ràng.

### 13.1. Kết quả so sánh các cách

Với dữ liệu A/B ở phần 3:

| Cách viết | Kết quả theo giá trị (bỏ qua thứ tự) |
|---|---|
| A EXCEPT B | P02, P04 |
| A EXCEPT ALL B | P01, P02, P04, NULL |
| NOT EXISTS với b.k = a.k | P02, P04, NULL, NULL |
| SELECT DISTINCT + NOT EXISTS với b.k = a.k | P02, P04, NULL |
| NOT IN với B có NULL | Thường không có dòng nào |
| SELECT DISTINCT + NOT EXISTS với so khớp null-safe | P02, P04 |

Bảng trên nêu chính xác sự khác biệt **set**, **bag** và **NULL**. Trong ứng dụng thật, chọn cách viết theo **ý nghĩa cần đạt**, không chỉ theo cú pháp dễ nhớ.

## 14. EXCEPT ALL khi DBMS không hỗ trợ: ý tưởng mô phỏng

Khi cần đối trừ số bản sao, một cách mô phỏng trên DBMS có **ROW_NUMBER()** là **đánh số từng lần xuất hiện trong cùng nhóm giá trị**, rồi loại những số thứ tự đã có ở bên B.

Với một cột ma_san_pham:

~~~sql
WITH a AS (
    SELECT
        ma_san_pham,
        ROW_NUMBER() OVER (
            PARTITION BY ma_san_pham
            ORDER BY stt
        ) AS lan
    FROM nguon_a
),
b AS (
    SELECT
        ma_san_pham,
        ROW_NUMBER() OVER (
            PARTITION BY ma_san_pham
            ORDER BY stt
        ) AS lan
    FROM nguon_b
)
SELECT
    a.ma_san_pham
FROM a
LEFT JOIN b
    ON a.lan = b.lan
   AND (
       a.ma_san_pham = b.ma_san_pham
       OR (a.ma_san_pham IS NULL AND b.ma_san_pham IS NULL)
   )
WHERE b.lan IS NULL;
~~~

Giải thích:

- Với mã P01, A có **lan = 1, 2**, B có **lan = 1**. Cặp lan=1 bị loại, còn lan=2.
- Với mã P03, A có lan=1, B có lan=1,2, nên không còn P03 từ A.
- Với NULL, A có lan=1,2, B có lan=1, nên còn một NULL.
- Với P02/P04, B không có giá trị tương ứng nên mỗi mã còn một dòng.

Kết quả theo đa tập đúng với ví dụ **EXCEPT ALL**: **P01, P02, P04, NULL**.

### 14.1. Điều kiện để cách mô phỏng đúng

- Phải so sánh **đúng toàn bộ các cột của hàng** mà phép EXCEPT ALL cần đối trừ. Nếu có hai hoặc ba cột, PARTITION BY và điều kiện ON phải dựa trên tất cả cột đó.
- Phải xử lý **NULL theo kiểu null-safe** trong điều kiện ghép.
- **ROW_NUMBER** cần đánh số từng bản sao; ORDER BY nên dựa trên khóa ổn định của nguồn nếu có. Khi các hàng giống nhau trên toàn bộ cột cần đối trừ, thứ tự giữa chúng không làm thay đổi **đa tập giá trị** còn lại, nhưng vẫn không tự chọn được “bản ghi gốc nào” phải xóa về mặt nghiệp vụ.
- Cách viết trên dùng **b.lan IS NULL** làm chỉ dấu không khớp vì lan là giá trị số thứ tự không NULL của một dòng B thật.
- Đối với kiểu dữ liệu/collation đặc biệt hoặc lượng dữ liệu lớn, phải kiểm tra kỹ tính tương đương và hiệu năng.

Không nên sao chép nguyên cách mô phỏng này cho một bài toán so sánh nhiều bảng mà không xác định rõ **đơn vị đối trừ**.

## 15. EXCEPT và MINUS theo phương ngữ SQL

Tính năng thực tế phụ thuộc phiên bản DBMS. Đây là bức tranh tổng quát của các dòng sản phẩm phổ biến.

| Hệ quản trị | Phép hiệu không giữ trùng | Phép hiệu giữ số bản sao | Ghi chú |
|---|---|---|---|
| **PostgreSQL** | **EXCEPT** | **EXCEPT ALL** | Không dùng MINUS như từ khóa phép toán tập hợp thông thường |
| **MySQL 8.0.31+** | **EXCEPT** | **EXCEPT ALL** | Các bản MySQL 8.0 cũ hơn không có EXCEPT; phải kiểm tra phiên bản |
| **SQL Server** | **EXCEPT** | Không có **EXCEPT ALL** trực tiếp trong các phiên bản thông dụng | Dùng EXCEPT theo ngữ nghĩa DISTINCT |
| **Oracle Database 19c** | **MINUS** | Không có MINUS ALL/EXCEPT ALL ở thế hệ 19c | EXCEPT không phải cú pháp phép hiệu truyền thống của 19c |
| **Oracle Database 23ai / thế hệ mới** | **MINUS** và **EXCEPT** (theo tài liệu phiên bản) | Có thêm các biến thể ALL tương ứng trong thế hệ mới | Kiểm tra đúng bản phát hành và cách ghi cú pháp |
| **SQLite** | **EXCEPT** | Không có EXCEPT ALL trực tiếp | Không dùng MINUS như toán tử tập hợp thông thường |

Bảng này là định hướng cú pháp. Các tên thương mại, phiên bản và bản vá có thể thay đổi theo thời gian. Khi chuyển câu SQL giữa các hệ thống, hãy kiểm tra tài liệu của **đúng DBMS/phiên bản**, không chỉ tìm từ khóa EXCEPT trong một trang tổng quan.

### 15.1. PostgreSQL

PostgreSQL hỗ trợ:

~~~sql
SELECT ma_san_pham FROM nguon_a
EXCEPT
SELECT ma_san_pham FROM nguon_b;
~~~

Và:

~~~sql
SELECT ma_san_pham FROM nguon_a
EXCEPT ALL
SELECT ma_san_pham FROM nguon_b;
~~~

PostgreSQL có các toán tử UNION, INTERSECT, EXCEPT theo SQL tập hợp. Trong các truy vấn phức tạp, cần dấu ngoặc khi kết hợp nhiều phép để tránh hiểu sai độ ưu tiên.

### 15.2. MySQL

Trong **MySQL 8.0.31 trở lên**, có thể dùng EXCEPT và EXCEPT ALL theo cú pháp phiên bản hỗ trợ.

~~~sql
SELECT ma_san_pham FROM nguon_a
EXCEPT
SELECT ma_san_pham FROM nguon_b;
~~~

Trên các bản MySQL trước khi hỗ trợ EXCEPT, cần viết lại theo NOT EXISTS, LEFT JOIN anti-join hoặc kỹ thuật khác. Không nên nhầm **MySQL** với **MariaDB**, vì hai sản phẩm có lịch sử bổ sung cú pháp phép tập hợp khác nhau dù có quan hệ nguồn gốc.

Nếu dự án tuyên bố “dùng MySQL 8” nhưng không xác định **8.0.xx**, chưa đủ để kết luận EXCEPT được chấp nhận.

### 15.3. SQL Server (Transact-SQL)

SQL Server hỗ trợ EXCEPT:

~~~sql
SELECT ma_san_pham FROM dbo.nguon_a
EXCEPT
SELECT ma_san_pham FROM dbo.nguon_b;
~~~

Trong những phiên bản SQL Server phổ biến, EXCEPT loại trùng và không hỗ trợ dạng EXCEPT ALL trực tiếp. Nếu cần số bản sao, cân nhắc truy vấn dùng ROW_NUMBER hoặc xử lý đếm theo khóa.

Một số kiểu dữ liệu đặc biệt của SQL Server không được phép dùng trực tiếp trong so sánh EXCEPT/INTERSECT; cần đối chiếu tài liệu kiểu dữ liệu khi các cột không phải kiểu số/chuỗi/ngày thông thường.

### 15.4. Oracle Database 19c và MINUS

Ở Oracle 19c và các thế hệ truyền thống, viết:

~~~sql
SELECT ma_san_pham
FROM nguon_a

MINUS

SELECT ma_san_pham
FROM nguon_b;
~~~

MINUS theo mặc định trả hiệu **loại trùng**.

Nếu lấy mã từ hệ thống A có ở bảng B hay không, cần chú ý Oracle thường coi chuỗi ký tự rỗng như NULL. Điều này có thể ảnh hưởng phép so sánh tập hợp trên dữ liệu text, nhất là khi một nguồn được chuyển từ hệ thống có phân biệt NULL với ''.

Không nên đơn giản đổi MINUS thành EXCEPT trong ứng dụng chạy Oracle 19c nếu không xác nhận hỗ trợ cú pháp.

### 15.5. Oracle Database thế hệ mới và EXCEPT

Oracle Database ở các thế hệ mới như **23ai** đã mở rộng khả năng xử lý toán tử tập hợp; tài liệu của các thế hệ này mô tả **EXCEPT** như tên tương ứng phép trừ tập hợp, cùng các biến thể ALL.

Khi chuyển từ Oracle 19c lên thế hệ mới, cần kiểm tra:

- Phiên bản/compatibility thực sự đang chạy.
- MINUS, EXCEPT và các biến thể ALL có được hỗ trợ không.
- Quy tắc kiểu dữ liệu, nhóm NULL và collation.
- Phép hiệu có đang được dùng cùng UNION/INTERSECT hay không.
- Các ngoại lệ với ORDER BY, alias và dấu ngoặc trong câu lệnh.

Không nên tuyên bố mọi phiên bản Oracle đều hỗ trợ EXCEPT ALL hoặc MINUS ALL.

### 15.6. SQLite

SQLite hỗ trợ EXCEPT theo ngữ nghĩa loại trùng:

~~~sql
SELECT ma_san_pham FROM nguon_a
EXCEPT
SELECT ma_san_pham FROM nguon_b;
~~~

SQLite thông thường không hỗ trợ EXCEPT ALL hay MINUS. Việc so sánh kiểu dữ liệu trong SQLite phụ thuộc vào hệ thống kiểu linh hoạt/affinity và collation; kết quả trên hai cột chứa giá trị có kiểu lưu khác nhau có thể cần phân tích riêng, không giả định mọi chuỗi số tự động tương đương số nguyên.

### 15.7. Câu hỏi thường gặp: dùng MINUS trong PostgreSQL/MySQL/SQL Server được không?

Không nên mặc định. Với những DBMS đó, cú pháp phổ biến là **EXCEPT** trên các phiên bản có hỗ trợ. MINUS là từ khóa quen thuộc với Oracle truyền thống, không phải một từ khóa SQL phổ quát có thể thay thế EXCEPT ở mọi nơi.

## 16. Kết hợp UNION, INTERSECT và EXCEPT

Ba phép toán tập hợp cơ bản:

| Toán tử | Ý nghĩa |
|---|---|
| **UNION** | Những hàng xuất hiện ở **A hoặc B** (loại trùng mặc định) |
| **INTERSECT** | Những hàng xuất hiện **ở cả A và B** |
| **EXCEPT/MINUS** | Những hàng xuất hiện ở **A nhưng không ở B** |

Ví dụ với dữ liệu A/B:

~~~sql
-- Tất cả mã phân biệt ở hai nguồn:
SELECT ma_san_pham FROM nguon_a
UNION
SELECT ma_san_pham FROM nguon_b;
~~~

Kết quả theo tập gồm **P01, P02, P03, P04, P05, NULL**.

~~~sql
-- Mã có ở cả hai nguồn:
SELECT ma_san_pham FROM nguon_a
INTERSECT
SELECT ma_san_pham FROM nguon_b;
~~~

Kết quả theo tập gồm **P01, P03, NULL**.

~~~sql
-- Mã chỉ có ở A:
SELECT ma_san_pham FROM nguon_a
EXCEPT
SELECT ma_san_pham FROM nguon_b;
~~~

Kết quả **P02, P04**.

### 16.1. Tính không giao hoán của EXCEPT

UNION và INTERSECT có ngữ nghĩa đối xứng về tập hợp, còn EXCEPT thì không:

~~~text
A UNION B = B UNION A
A INTERSECT B = B INTERSECT A
A EXCEPT B thường khác B EXCEPT A
~~~

Vì vậy, khi đọc một truy vấn EXCEPT dài, phải xác định rõ **bên trái** và **bên phải**.

## 17. Thứ tự ưu tiên khi ghép nhiều phép tập hợp

Xét:

~~~sql
SELECT ma FROM a
UNION
SELECT ma FROM b
EXCEPT
SELECT ma FROM c;
~~~

Người đọc có thể hiểu theo hai cách:

~~~text
(A UNION B) EXCEPT C
~~~

hoặc:

~~~text
A UNION (B EXCEPT C)
~~~

Hai cách có thể cho kết quả khác nhau. Các DBMS có quy tắc ưu tiên/kết hợp khác nhau, đặc biệt khi còn **INTERSECT** và các cú pháp mở rộng.

Trong PostgreSQL và SQL Server, **INTERSECT** thường có ưu tiên cao hơn **UNION/EXCEPT**; các phép còn lại có quy tắc kết hợp theo cú pháp. Oracle truyền thống có lịch sử ưu tiên các phép tập hợp theo cách riêng và đã có lưu ý về thay đổi thứ tự ưu tiên INTERSECT trong các phiên bản tương lai. MySQL cũng có quy tắc ưu tiên trong các thế hệ hỗ trợ phép tập hợp.

**Cách ít gây nhầm nhất:** khi câu truy vấn có từ hai phép toán tập hợp trở lên và ý nghĩa phụ thuộc vào thứ tự, hãy **nhóm rõ bằng CTE hoặc subquery**. Cú pháp ngoặc trực tiếp quanh nhánh có thể khác theo DBMS nên CTE thường dễ đọc hơn.

### 17.1. Ví dụ sử dụng CTE để làm rõ

~~~sql
WITH hop_a_b AS (
    SELECT ma_san_pham FROM nguon_a
    UNION
    SELECT ma_san_pham FROM nguon_b
),
nguon_cam AS (
    SELECT ma_san_pham FROM danh_sach_cam
)
SELECT ma_san_pham FROM hop_a_b
EXCEPT
SELECT ma_san_pham FROM nguon_cam;
~~~

Ý định rõ: **lấy hợp A∪B rồi trừ danh sách cấm**.

Nếu muốn **A ∪ (B−C)**, viết truy vấn khác:

~~~sql
WITH b_tru_c AS (
    SELECT ma_san_pham FROM nguon_b
    EXCEPT
    SELECT ma_san_pham FROM danh_sach_cam
)
SELECT ma_san_pham FROM nguon_a
UNION
SELECT ma_san_pham FROM b_tru_c;
~~~

Đây là hai bài toán khác nhau; việc đặt tên CTE rõ giúp tránh phụ thuộc vào trí nhớ về thứ tự ưu tiên toán tử.

### 17.2. Khi cần giữ bản sao

**UNION ALL** và **EXCEPT ALL** làm việc theo đa tập; trộn ALL/DISTINCT có thể khiến số bản sao thay đổi. Không chuyển các phép từ dạng thường sang ALL một cách tự động vì mục đích “tăng hiệu năng”, vì kết quả nghiệp vụ có thể khác hẳn.

## 18. ORDER BY áp dụng cho toàn kết quả phép hiệu

Một truy vấn EXCEPT **không bảo đảm thứ tự hàng**. Nếu cần hiển thị tăng dần:

~~~sql
SELECT ma_san_pham
FROM nguon_a

EXCEPT

SELECT ma_san_pham
FROM nguon_b

ORDER BY ma_san_pham;
~~~

Trong những DBMS hỗ trợ cú pháp như trên, ORDER BY ở cuối sắp xếp **toàn kết quả sau EXCEPT**, không chỉ nhánh thứ hai.

Một sai lầm phổ biến là kỳ vọng:

~~~sql
SELECT ma_san_pham FROM nguon_a
ORDER BY ma_san_pham
EXCEPT
SELECT ma_san_pham FROM nguon_b;
~~~

chạy và giữ thứ tự nhánh đầu. Nhiều DBMS không cho ORDER BY trực tiếp như vậy ở nhánh đầu hoặc chỉ cho trong trường hợp dùng subquery có giới hạn/tính năng riêng.

### 18.1. Bao bên ngoài bằng CTE để sắp xếp rõ ràng

~~~sql
WITH chi_co_o_a AS (
    SELECT ma_san_pham FROM nguon_a
    EXCEPT
    SELECT ma_san_pham FROM nguon_b
)
SELECT ma_san_pham
FROM chi_co_o_a
ORDER BY ma_san_pham;
~~~

Cách này đặc biệt hữu ích khi muốn thêm điều kiện hiển thị hoặc xử lý NULL:

~~~sql
WITH chi_co_o_a AS (
    SELECT ma_san_pham FROM nguon_a
    EXCEPT
    SELECT ma_san_pham FROM nguon_b
)
SELECT ma_san_pham
FROM chi_co_o_a
ORDER BY
    CASE WHEN ma_san_pham IS NULL THEN 1 ELSE 0 END,
    ma_san_pham;
~~~

Vị trí NULL mặc định trong ORDER BY có thể khác nhau theo DBMS; CASE giúp đưa NULL về cuối theo ý định, thay vì phụ thuộc mặc định.

### 18.2. EXCEPT không phải cách chọn “dòng mới nhất”

EXCEPT trả hiệu tập hợp, không định nghĩa hàng đầu tiên/hàng mới nhất. Nếu yêu cầu phụ thuộc thời gian hoặc thứ tự, hãy chọn đúng dòng trong từng nguồn bằng **ROW_NUMBER**, **MAX + JOIN** hoặc cơ chế được thiết kế phù hợp rồi mới lấy hiệu nếu cần.

## 19. EXCEPT và việc so sánh toàn bộ hàng

Giả sử hai hệ thống cùng có bảng giá:

**bang_gia_a**

| ma_san_pham | gia |
|---|---:|
| P01 | 100000 |
| P02 | 200000 |
| P03 | 300000 |

**bang_gia_b**

| ma_san_pham | gia |
|---|---:|
| P01 | 100000 |
| P02 | 250000 |
| P04 | 400000 |

Truy vấn:

~~~sql
SELECT ma_san_pham, gia
FROM bang_gia_a

EXCEPT

SELECT ma_san_pham, gia
FROM bang_gia_b;
~~~

Kết quả:

| ma_san_pham | gia |
|---|---:|
| P02 | 200000 |
| P03 | 300000 |

Ở B có P02 nhưng **giá khác**, nên cặp **(P02, 200000)** không tồn tại ở B. P01 cùng cả mã và giá nên bị loại. P03 không có ở B nên giữ.

Đảo chiều:

~~~sql
SELECT ma_san_pham, gia FROM bang_gia_b
EXCEPT
SELECT ma_san_pham, gia FROM bang_gia_a;
~~~

Kết quả:

| ma_san_pham | gia |
|---|---:|
| P02 | 250000 |
| P04 | 400000 |

### 19.1. Chưa thể gọi tất cả kết quả là “sản phẩm bị xóa”

Trong hiệu A−B:

- P03 là mã chỉ có A, có thể là bản ghi bị mất khi đồng bộ.
- P02 cũng xuất hiện vì **thay đổi giá**, không phải vì mã bị thiếu ở B.

Nếu muốn phân loại **mã bị xóa**, **mã mới** và **mã giữ nguyên nhưng giá thay đổi**, cần đối soát bằng khóa mã rồi so sánh thuộc tính, chứ không chỉ trừ toàn bộ các cặp cột.

### 19.2. Phân loại bằng JOIN theo khóa

Ví dụ trên DBMS hỗ trợ LEFT JOIN:

~~~sql
SELECT
    a.ma_san_pham,
    a.gia AS gia_a,
    b.gia AS gia_b,
    CASE
        WHEN b.ma_san_pham IS NULL THEN 'CHI_CO_O_A'
        WHEN a.gia IS DISTINCT FROM b.gia THEN 'GIA_KHAC'
        ELSE 'GIA_GIONG'
    END AS tinh_trang
FROM bang_gia_a a
LEFT JOIN bang_gia_b b
    ON b.ma_san_pham = a.ma_san_pham
ORDER BY a.ma_san_pham;
~~~

**IS DISTINCT FROM** so sánh an toàn với NULL nhưng không được hỗ trợ đồng nhất ở mọi DBMS. Nếu bảng có khóa mã duy nhất không NULL, cách JOIN và CASE giúp phân loại theo mục tiêu nghiệp vụ rõ hơn một phép EXCEPT trên toàn hàng.

## 20. Đối soát hai chiều bằng EXCEPT

Khi cần tìm tất cả khác biệt về hàng giữa hai nguồn, có thể lấy hai hiệu rồi ghép lại kèm nhãn nguồn.

~~~sql
WITH chi_o_a AS (
    SELECT ma_san_pham FROM nguon_a
    EXCEPT
    SELECT ma_san_pham FROM nguon_b
),
chi_o_b AS (
    SELECT ma_san_pham FROM nguon_b
    EXCEPT
    SELECT ma_san_pham FROM nguon_a
)
SELECT 'CHI_O_A' AS nguon, ma_san_pham
FROM chi_o_a

UNION ALL

SELECT 'CHI_O_B' AS nguon, ma_san_pham
FROM chi_o_b

ORDER BY nguon, ma_san_pham;
~~~

Kết quả với dữ liệu mẫu:

| nguon | ma_san_pham |
|---|---|
| CHI_O_A | P02 |
| CHI_O_A | P04 |
| CHI_O_B | P05 |

Ở đây dùng **UNION ALL** vì hai phía đã được gắn nhãn khác nhau và cần giữ kết quả của cả hai hướng. Dù không có nhãn, A−B và B−A là hai tập phân biệt theo giá trị; nhưng nhãn nguồn giúp người đọc biết hành động cần làm.

### 20.1. Không kiểm tra được chênh lệch bản sao nếu chỉ EXCEPT DISTINCT

Trong dữ liệu mẫu, P01 có **hai bản sao ở A** và **một ở B**, nhưng đối soát hai chiều bằng EXCEPT DISTINCT không báo P01 vì cả hai nguồn đều có P01.

Nếu đồng bộ đòi **số lượng bản sao cũng phải trùng**, cần:

- EXCEPT ALL theo cả hai chiều nếu DBMS hỗ trợ, hoặc
- So sánh **COUNT(*) GROUP BY trên toàn bộ các cột định nghĩa hàng**, có so sánh null-safe.

Ví dụ:

~~~sql
WITH dem_a AS (
    SELECT ma_san_pham, COUNT(*) AS so_lan
    FROM nguon_a
    GROUP BY ma_san_pham
),
dem_b AS (
    SELECT ma_san_pham, COUNT(*) AS so_lan
    FROM nguon_b
    GROUP BY ma_san_pham
)
SELECT
    a.ma_san_pham,
    a.so_lan AS so_lan_a,
    b.so_lan AS so_lan_b
FROM dem_a a
LEFT JOIN dem_b b
    ON a.ma_san_pham = b.ma_san_pham
    OR (a.ma_san_pham IS NULL AND b.ma_san_pham IS NULL)
WHERE b.so_lan IS NULL OR a.so_lan <> b.so_lan;
~~~

Đây chỉ kiểm tra các nhóm xuất hiện ở **A**; muốn phát hiện mã **chỉ có ở B** như P05, phải đối soát thêm chiều B hoặc dùng FULL OUTER JOIN/null-safe phù hợp DBMS. Không nên coi một LEFT JOIN là báo cáo chênh lệch **hai chiều hoàn chỉnh**.

### 20.2. So sánh số lượng theo cả hai chiều

Cách rõ hơn là dựng hai bộ đếm rồi dùng FULL OUTER JOIN nếu DBMS hỗ trợ:

~~~sql
WITH dem_a AS (
    SELECT ma_san_pham, COUNT(*) AS so_lan_a
    FROM nguon_a
    GROUP BY ma_san_pham
),
dem_b AS (
    SELECT ma_san_pham, COUNT(*) AS so_lan_b
    FROM nguon_b
    GROUP BY ma_san_pham
)
SELECT
    a.ma_san_pham AS ma_a,
    b.ma_san_pham AS ma_b,
    COALESCE(a.so_lan_a, 0) AS so_lan_a,
    COALESCE(b.so_lan_b, 0) AS so_lan_b
FROM dem_a a
FULL OUTER JOIN dem_b b
    ON a.ma_san_pham = b.ma_san_pham
    OR (a.ma_san_pham IS NULL AND b.ma_san_pham IS NULL)
WHERE COALESCE(a.so_lan_a, 0) <> COALESCE(b.so_lan_b);
~~~

Đây là truy vấn minh họa về đối soát đa tập. Không dùng FULL OUTER JOIN nguyên văn trên MySQL thông dụng vì không hỗ trợ trực tiếp; ngoài ra phải bảo đảm các nhóm dữ liệu đã được đếm ở đúng grain. Với NULL, cột ma_a và ma_b có thể cùng NULL ngay cả khi đã ghép nhóm, nên muốn nhãn giá trị dễ đọc cần CASE riêng.

## 21. EXCEPT cho dữ liệu khách hàng và quyền truy cập

### 21.1. Khách đã đăng ký nhưng chưa có đơn

Giả sử:

~~~text
khach_hang(ma_khach_hang PRIMARY KEY, ten_khach_hang)
don_hang(ma_don_hang PRIMARY KEY, ma_khach_hang)
~~~

Dùng EXCEPT:

~~~sql
SELECT ma_khach_hang
FROM khach_hang

EXCEPT

SELECT ma_khach_hang
FROM don_hang
WHERE ma_khach_hang IS NOT NULL;
~~~

Kết quả là mã khách có trong bảng khách nhưng chưa xuất hiện ở đơn hàng.

Nếu cột khach_hang.ma_khach_hang là PRIMARY KEY NOT NULL, việc lọc NULL ở bên phải chủ yếu giúp diễn đạt yêu cầu; theo ngữ nghĩa EXCEPT, NULL bên phải sẽ không trùng với khóa không NULL ở trái. Với NOT IN, việc lọc NULL bên phải lại đặc biệt quan trọng.

Một cách khác:

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang d
    WHERE d.ma_khach_hang = k.ma_khach_hang
);
~~~

NOT EXISTS thuận tiện nếu muốn trả cả **tên khách** và các thuộc tính khác ở bảng khách mà không đưa chúng vào phép so sánh set.

### 21.2. Quyền được cấp nhưng không nằm trong danh sách cho phép

Giả sử bảng **quyen_duoc_cap** và **quyen_cho_phep** đều có **ma_nguoi_dung** và **ma_quyen**.

~~~sql
SELECT ma_nguoi_dung, ma_quyen
FROM quyen_duoc_cap

EXCEPT

SELECT ma_nguoi_dung, ma_quyen
FROM quyen_cho_phep;
~~~

Câu truy vấn tìm các **cặp người dùng–quyền** có ở danh sách cấp thực tế nhưng không có trong danh sách cho phép. Đây là ví dụ hai cột phải được so sánh cùng lúc.

**Lưu ý nghiệp vụ:** trong hệ thống phân quyền, có thể còn tenant, phạm vi tài nguyên, thời gian hiệu lực và vai trò kế thừa. Nếu thiếu một phần định danh quyền, EXCEPT có thể gộp hoặc so khớp sai những quyền có ý nghĩa khác nhau. Phải đưa đủ cột cấu thành “một quyền được cấp” theo mô hình bảo mật.

### 21.3. Kỹ thuật chống mất dòng do JOIN

Nếu có nhiều dòng đơn cho một khách, phép JOIN từ khách sang đơn có thể nhân khách. Khi chỉ cần danh sách mã khách chưa có đơn, EXCEPT mặc định vốn trả **các mã phân biệt**, tránh vấn đề nhân số dòng. Nhưng nếu cần theo từng đơn hoặc thống kê tần suất, tính loại trùng mặc định lại có thể làm mất thông tin quan trọng.

## 22. WHERE trước hay sau EXCEPT?

Có hai việc khác nhau:

1. **Lọc dữ liệu đầu vào** của từng vế rồi trừ.
2. **Trừ xong** mới lọc kết quả hiệu.

Ví dụ:

~~~sql
SELECT ma_san_pham
FROM nguon_a
WHERE ma_san_pham LIKE 'P0%'

EXCEPT

SELECT ma_san_pham
FROM nguon_b
WHERE ma_san_pham LIKE 'P0%';
~~~

Hai vế đều chỉ gồm các mã bắt đầu P0.

Nếu yêu cầu là “chỉ hiển thị kết quả hiệu thuộc mẫu P0”, có thể bọc phép hiệu:

~~~sql
WITH hieu AS (
    SELECT ma_san_pham FROM nguon_a
    EXCEPT
    SELECT ma_san_pham FROM nguon_b
)
SELECT ma_san_pham
FROM hieu
WHERE ma_san_pham LIKE 'P0%';
~~~

Hai cách **có thể tương đương về kết quả** trong những điều kiện lọc cụ thể áp dụng như nhau trên các cột so sánh, nhưng không phải mọi phép lọc hay mọi phép biến đổi đều được phép chuyển qua EXCEPT tùy ý. Nếu bên phải lọc **ít hơn hoặc nhiều hơn** bên trái, phép hiệu sẽ thay đổi.

### 22.1. Ví dụ sai do chỉ lọc một vế

Giả sử yêu cầu: “Mã sản phẩm thuộc danh mục Điện tử có ở A nhưng không có ở B, bất kể danh mục ở B”.

Nếu bên trái lọc Điện tử nhưng bên phải cũng chỉ lọc Điện tử, một mã sản phẩm có ở B với **danh mục khác** có thể bị bỏ khỏi tập trừ và xuất hiện sai ở kết quả.

Cần xác định rõ:

- Đang kiểm tra **mã có ở B hay không**?
- Hay kiểm tra **cặp (mã, danh mục) có ở B hay không**?
- Hay chỉ so sánh phần dữ liệu đã được chọn bởi cùng một bộ lọc ở hai bên?

Việc đặt WHERE phải theo câu hỏi nghiệp vụ.

## 23. EXCEPT với kết quả tổng hợp

EXCEPT có thể so sánh những chỉ số tổng hợp, miễn hai phía trả cùng cấu trúc.

Ví dụ: “Những cặp **(mã danh mục, số sản phẩm)** ở hệ thống A không có ở B”:

~~~sql
SELECT
    ma_danh_muc,
    COUNT(*) AS so_san_pham
FROM san_pham_a
GROUP BY ma_danh_muc

EXCEPT

SELECT
    ma_danh_muc,
    COUNT(*) AS so_san_pham
FROM san_pham_b
GROUP BY ma_danh_muc;
~~~

Nếu hai hệ có cùng mã danh mục nhưng số sản phẩm khác, cặp (mã, số lượng) từ A vẫn xuất hiện trong kết quả.

### 23.1. EXCEPT kết quả nhóm khác với EXCEPT bản ghi

- EXCEPT trên **ma_danh_muc** hỏi danh mục nào chỉ có ở A.
- EXCEPT trên **(ma_danh_muc, COUNT(*))** hỏi **cặp danh mục–số lượng** nào khác.
- EXCEPT trên từng **ma_san_pham** hỏi mã sản phẩm nào thiếu.
- EXCEPT ALL trên mã sản phẩm so sánh cả **số lần xuất hiện** mỗi mã.

Một truy vấn tổng hợp có thể che giấu các thay đổi bù trừ. Ví dụ A mất một sản phẩm và có thêm một sản phẩm khác trong cùng danh mục, COUNT(*) vẫn giữ nguyên. Vì vậy, đối soát số lượng là một kiểm tra **tổng quan**, không thay cho đối soát khóa chi tiết.

## 24. EXCEPT, INTERSECT và NULL trong kiểm thử dữ liệu

Khi tạo bộ test cho EXCEPT, nên có đủ các trường hợp sau:

| Tình huống | Ví dụ | EXCEPT DISTINCT A−B |
|---|---|---|
| Chỉ ở A | A có P02, B không có | Giữ P02 |
| Chỉ ở B | B có P05, A không có | Không giữ P05 |
| Có ở cả hai | Cả hai có P03 | Loại P03 |
| Trùng trong A | A có P02 hai lần, B không có | Giữ một P02 |
| Trùng trong B | A có P03 một lần, B có hai | Loại P03 |
| NULL ở cả hai | A và B đều có NULL | Loại NULL |
| NULL chỉ ở A | A có NULL, B không có | Giữ một NULL |
| NULL chỉ ở B | B có NULL, A không có | Không thêm NULL |
| Hai cột, một cột khác | A có (P01,100), B có (P01,200) | Giữ (P01,100) |
| Cột đổi vị trí | SELECT (mã,tên) vs (tên,mã) | Sai ý nghĩa, có thể vẫn chạy |
| Kiểu số vs chuỗi | A có 1, B có '1' | Phụ thuộc kiểu/chuyển đổi DBMS |
| Collation khác | 'ABC' và 'abc' | Phụ thuộc phép so sánh/collation |

Bộ test cần so sánh **tập hàng mong đợi**, không chỉ số dòng. Nếu có EXCEPT ALL, so sánh cả **số lần xuất hiện của từng bộ giá trị**.

## 25. Hiệu năng: EXCEPT có luôn nhanh hơn NOT EXISTS?

Không có kết luận chung. Các hệ quản trị có thể thực thi EXCEPT bằng:

- **Sort + loại trùng/so sánh**.
- **Hash aggregate / hash anti-semi join** hoặc biến thể khác.
- Tận dụng **chỉ mục** và thống kê dữ liệu.
- Kế hoạch song song, lưu trung gian hoặc spill xuống đĩa nếu dữ liệu lớn.

Chi phí phụ thuộc vào:

- Số dòng ở hai vế.
- Số cột và độ rộng mỗi hàng.
- Tỷ lệ giá trị trùng/không trùng.
- Kiểu dữ liệu và collation.
- Chỉ mục phù hợp trên các cột được so sánh.
- Tỷ lệ NULL.
- Phiên bản, bộ tối ưu và thống kê DBMS.
- Việc cần DISTINCT hay ALL.

### 25.1. EXCEPT có thể cần loại trùng

EXCEPT mặc định trả các hàng phân biệt. Nếu bảng A có hàng triệu dòng với nhiều bản sao, thao tác loại trùng có thể có chi phí. Trong khi, với bài toán chỉ tìm hàng A không có tham chiếu ở B, NOT EXISTS có thể thuận lợi nếu chỉ số tốt và không cần loại trùng.

Ngược lại, EXCEPT có thể rõ ràng và được tối ưu tốt cho hai tập cùng cấu trúc. Không nên chuyển EXCEPT thành một JOIN phức tạp chỉ dựa vào suy đoán.

### 25.2. Xem execution plan

Khi truy vấn chậm, đo trên DBMS thật:

- PostgreSQL: **EXPLAIN**, **EXPLAIN ANALYZE**.
- SQL Server: execution plan trong công cụ phù hợp.
- MySQL: **EXPLAIN** và các phương tiện phân tích theo phiên bản.
- Oracle Database: execution plan/DBMS_XPLAN.
- SQLite: **EXPLAIN QUERY PLAN**.

Cần xác nhận kết quả đúng trước khi tối ưu. Một truy vấn NOT EXISTS chạy nhanh hơn nhưng **giữ NULL/duplicate khác EXCEPT** không phải tối ưu tương đương.

### 25.3. Không thêm ORDER BY vô ích vào từng nhánh

EXCEPT không bảo đảm thứ tự giữa hai nguồn. Việc cố sắp xếp từng nhánh trước khi trừ thường không tạo ra đầu ra có thứ tự và có thể làm kế hoạch khó hiểu. Chỉ sắp xếp **kết quả cuối** khi người dùng hoặc xử lý tiếp cần thứ tự.

### 25.4. Đối soát cực lớn

Nếu mỗi nguồn có hàng trăm triệu dòng, có thể cần phân vùng theo thời gian/tenant, so sánh trước bằng checksum hoặc tổng hợp và sau đó kiểm tra chi tiết. Nhưng checksum chỉ là tín hiệu **nghi vấn khác biệt**, không phải bằng chứng tuyệt đối hai tập dòng giống nhau do khả năng va chạm và khác biệt chuẩn hóa.

Khi dùng EXCEPT để phát hiện khác biệt trong dữ liệu đang thay đổi, cần chú ý **transaction isolation/snapshot** để không nhầm sự thay đổi đồng thời với lỗi đồng bộ.

## 26. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Hiểu EXCEPT là lọc giá trị của một cột tùy ý | Bỏ qua cấu trúc dòng của hai SELECT | Xác định bộ cột thực sự được trừ |
| Đảo A và B | Trả tập khác | Viết rõ “có ở A nhưng không ở B” |
| Chọn thêm ID nguồn | Hai hàng vốn cùng mã trở thành khác nhau | Chỉ SELECT các cột định nghĩa phần tử cần so sánh |
| Quên EXCEPT loại trùng mặc định | Mất số bản sao quan trọng | Dùng EXCEPT ALL khi hỗ trợ hoặc đối soát COUNT |
| Nghĩ EXCEPT ALL giống EXCEPT | Sai số bản sao | Áp dụng công thức max(countA-countB,0) |
| Nghĩ NULL không thể trùng vì NULL = NULL UNKNOWN | Dự đoán sai kết quả | EXCEPT so sánh NULL theo ngữ nghĩa set |
| Thay EXCEPT bằng NOT EXISTS với dấu bằng rồi cho là hoàn toàn tương đương | Khác NULL và duplicate | Null-safe comparison + DISTINCT nếu cần mô phỏng |
| Thay EXCEPT bằng NOT IN khi B chứa NULL | Có thể trả kết quả rỗng | Dùng EXCEPT/NOT EXISTS phù hợp |
| LEFT JOIN null-safe nhưng kiểm tra b.k IS NULL | Nhận nhầm dòng B có khóa NULL thật là không khớp | Kiểm tra khóa định danh NOT NULL của B |
| Dùng EXCEPT ALL trên SQL Server/SQLite | Lỗi cú pháp | Dùng phiên bản hỗ trợ hoặc mô phỏng |
| Dùng MINUS trên PostgreSQL/SQL Server | Lỗi cú pháp | Dùng EXCEPT theo DBMS |
| Dùng EXCEPT trên Oracle 19c | Không phù hợp cú pháp truyền thống | Dùng MINUS |
| Giả định “MySQL 8 nào cũng có EXCEPT” | Có phiên bản 8.0 cũ không hỗ trợ | Kiểm tra 8.0.31+ |
| Hai SELECT khác số cột | Lỗi cú pháp/kiểu dữ liệu | Căn chỉnh cấu trúc |
| Cột cùng tên nhưng khác vị trí | Trả kết quả sai dù SQL có thể chạy | So sánh cột theo vị trí |
| Kiểu dữ liệu/collation khác | Lỗi hoặc so sánh không như mong đợi | Chuẩn hóa đúng miền dữ liệu |
| Trộn UNION/INTERSECT/EXCEPT không nhóm rõ | Kết quả phụ thuộc độ ưu tiên | Dùng CTE/subquery để thể hiện ý định |
| ORDER BY trong nhánh và nghĩ nó sắp kết quả cuối | Thứ tự không bảo đảm | ORDER BY ngoài cùng |
| Dùng EXCEPT bản ghi để tìm “mã bị xóa” | Bản ghi cùng mã nhưng giá khác cũng xuất hiện | So sánh theo mã, rồi phân loại thuộc tính |
| Tưởng EXCEPT tự xác minh toàn bộ tính nhất quán | Không phát hiện khác biệt số bản sao với DISTINCT | Đối soát ALL/COUNT và cả hai chiều |
| Dùng checksum như bằng chứng tuyệt đối | Rủi ro va chạm hoặc chuẩn hóa không thống nhất | Xác nhận chi tiết bằng phép so sánh hàng |
| So sánh dữ liệu đang thay đổi không có snapshot phù hợp | Sai khác do thời gian đọc | Xác định mức nhất quán khi đối soát |

## 27. Cách chọn công cụ cho yêu cầu nghiệp vụ

| Yêu cầu | Gợi ý ban đầu | Lưu ý |
|---|---|---|
| Các hàng phân biệt có ở A nhưng không ở B | **EXCEPT** / **MINUS** | So sánh đủ cột, loại trùng |
| Số bản sao ở A vượt số bản sao ở B | **EXCEPT ALL** | Chỉ nơi hỗ trợ; có thể mô phỏng bằng ROW_NUMBER |
| Bản ghi A không có quan hệ tương ứng ở B | **NOT EXISTS** | Thiết kế điều kiện tương quan/NULL |
| Danh sách khách có đơn | **EXISTS** | Tránh nhân dòng vì JOIN một–nhiều |
| Các mã có ở cả hai nguồn | **INTERSECT** | Loại trùng mặc định |
| Tất cả mã ở ít nhất một nguồn | **UNION** | Loại trùng mặc định |
| Đối soát mọi chênh lệch hai chiều | **A EXCEPT B + B EXCEPT A** | Gắn nhãn nguồn |
| Phân loại thêm/sửa/xóa theo khóa | **JOIN/FULL JOIN + CASE** hoặc CTE | Không dùng EXCEPT trên toàn bộ hàng rồi gọi tất cả là “đã xóa” |
| So sánh số bản ghi mỗi mã | **GROUP BY COUNT + so sánh hai phía** | Xử lý NULL, khóa trùng |
| Tìm những hàng không khớp nhưng vẫn cần tất cả cột A | **NOT EXISTS** hoặc anti-join | EXCEPT trên nhiều cột thay đổi ý nghĩa so sánh |

Không có một cú pháp “tốt nhất” cho mọi bài toán. Hãy bắt đầu bằng **định nghĩa thế nào là một phần tử/hàng cần so sánh**, sau đó mới chọn toán tử.

## 28. Bài tập thực hành

### Bài 1 — Hiệu tập hợp đơn giản

Cho:

~~~text
A = {A, B, C, D}
B = {B, D, E}
~~~

Kết quả A EXCEPT B là gì? B EXCEPT A là gì?

<details>
<summary>Đáp án gợi ý</summary>

**A EXCEPT B = {A, C}** và **B EXCEPT A = {E}**. Phép hiệu có hướng.

</details>

### Bài 2 — Dòng trùng và EXCEPT mặc định

Cho:

~~~text
A: X, X, Y, Z
B: X, Z
~~~

EXCEPT mặc định trả những giá trị nào?

<details>
<summary>Đáp án gợi ý</summary>

**Chỉ Y**. X bị loại vì có ở B dù A có hai bản sao; Z cũng có B. EXCEPT mặc định trả các giá trị phân biệt.

</details>

### Bài 3 — EXCEPT ALL

Vẫn với:

~~~text
A: X, X, Y, Z
B: X, Z
~~~

EXCEPT ALL trả bao nhiêu dòng và những giá trị nào?

<details>
<summary>Đáp án gợi ý</summary>

**Hai dòng: X và Y**. A có hai X, B có một X, nên còn một X; Y không có ở B; Z bị trừ hết.

</details>

### Bài 4 — NULL ở cả hai nguồn

Cho:

~~~text
A: NULL, NULL, 10
B: NULL
~~~

Dự đoán A EXCEPT B và A EXCEPT ALL B.

<details>
<summary>Đáp án gợi ý</summary>

- **EXCEPT mặc định:** chỉ **10**.
- **EXCEPT ALL:** **10** và **một NULL**.

NULL được xử lý theo ngữ nghĩa của phép toán tập hợp, không theo phép NULL = NULL trong WHERE.

</details>

### Bài 5 — Chọn cột so sánh

Hai nguồn có:

~~~text
A: (stt=1, ma=P01)
B: (stt=101, ma=P01)
~~~

Vì sao:

~~~sql
SELECT stt, ma FROM a
EXCEPT
SELECT stt, ma FROM b;
~~~

trả một dòng từ A, còn EXCEPT chỉ trên ma thì không?

<details>
<summary>Đáp án gợi ý</summary>

Cặp **(1, P01)** không có ở B vì stt khác. Nhưng khi chỉ chọn **ma**, cả A và B đều có P01 nên P01 bị loại khỏi hiệu.

</details>

### Bài 6 — Hai cột, một cột khác

Cho:

~~~text
A: (P01, 100), (P02, 200)
B: (P01, 100), (P02, 250)
~~~

EXCEPT toàn bộ hai cột A−B trả gì?

<details>
<summary>Đáp án gợi ý</summary>

Trả **(P02, 200)**. Cặp P01 giống nhau; P02 có giá khác nên cả bộ hai cột không trùng. Không được kết luận mã P02 vắng mặt hoàn toàn ở B.

</details>

### Bài 7 — NOT EXISTS và NULL

A có hai NULL, B có một NULL. Vì sao:

~~~sql
SELECT a.k
FROM a
WHERE NOT EXISTS (
    SELECT 1 FROM b WHERE b.k = a.k
);
~~~

vẫn có thể giữ hai hàng NULL ở A, trong khi EXCEPT không giữ NULL?

<details>
<summary>Đáp án gợi ý</summary>

Trong truy vấn con, **NULL = NULL** là UNKNOWN nên không có dòng b nào thỏa điều kiện bằng với a.k NULL; NOT EXISTS là TRUE. EXCEPT dùng ngữ nghĩa so sánh dòng của phép toán tập hợp, coi hai hàng NULL tương ứng là không phân biệt nên loại NULL.

</details>

### Bài 8 — Dùng NOT EXISTS để mô phỏng EXCEPT DISTINCT

Viết một câu SQL mô phỏng hiệu một cột nullable từ A trừ B, loại trùng.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT DISTINCT a.k
FROM a
WHERE NOT EXISTS (
    SELECT 1
    FROM b
    WHERE b.k = a.k
       OR (b.k IS NULL AND a.k IS NULL)
);
~~~

Cần đảm bảo kiểu và collation tương thích. Nếu DBMS hỗ trợ **IS NOT DISTINCT FROM**, có thể dùng để diễn đạt so sánh null-safe ngắn hơn.

</details>

### Bài 9 — Bẫy NOT IN

Nếu B chứa **NULL**, điều gì có thể xảy ra với:

~~~sql
SELECT a.k
FROM a
WHERE a.k NOT IN (SELECT b.k FROM b);
~~~

<details>
<summary>Đáp án gợi ý</summary>

Những giá trị a.k không khớp phần tử cụ thể nào ở B vẫn có thể cho NOT IN = UNKNOWN do một phần tử NULL ở B. WHERE loại UNKNOWN, khiến truy vấn không trả các giá trị mong đợi. Dùng EXCEPT hoặc NOT EXISTS với điều kiện phù hợp.

</details>

### Bài 10 — Phương ngữ Oracle

Một hệ thống dùng **Oracle Database 19c**. Cần dùng từ khóa phổ biến nào để lấy hiệu hai SELECT theo cách mặc định loại trùng?

<details>
<summary>Đáp án gợi ý</summary>

Dùng **MINUS**:

~~~sql
SELECT ma_san_pham FROM nguon_a
MINUS
SELECT ma_san_pham FROM nguon_b;
~~~

Không giả định Oracle 19c hỗ trợ EXCEPT như Oracle 23ai/thế hệ mới.

</details>

### Bài 11 — MySQL phiên bản cũ

Một ứng dụng chạy MySQL **8.0.28**. Có thể dùng EXCEPT trực tiếp như trên MySQL 8.0.31+ không?

<details>
<summary>Đáp án gợi ý</summary>

Không nên. EXCEPT được bổ sung vào MySQL ở dòng 8.0.31; với 8.0.28 cần cách viết khác như NOT EXISTS/anti-join, và phải xử lý đúng duplicate/NULL theo yêu cầu.

</details>

### Bài 12 — Chênh lệch hai chiều

Viết truy vấn tìm các mã có ở A nhưng thiếu B **và** các mã có ở B nhưng thiếu A, gắn nhãn 'A'/'B'.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
WITH chi_a AS (
    SELECT ma FROM a EXCEPT SELECT ma FROM b
),
chi_b AS (
    SELECT ma FROM b EXCEPT SELECT ma FROM a
)
SELECT 'A' AS nguon, ma FROM chi_a
UNION ALL
SELECT 'B' AS nguon, ma FROM chi_b;
~~~

Trong Oracle 19c, thay EXCEPT bằng MINUS và đối chiếu cú pháp CTE tương ứng.

</details>

### Bài 13 — Thứ tự cột

Vì sao câu sau có thể sai dù cả hai bảng có hai cột kiểu VARCHAR?

~~~sql
SELECT ma, ten FROM a
EXCEPT
SELECT ten, ma FROM b;
~~~

<details>
<summary>Đáp án gợi ý</summary>

SQL so sánh **theo vị trí**: ma của A với ten của B, ten của A với ma của B. Câu SQL có thể không báo lỗi kiểu nhưng đang so sánh sai ý nghĩa. Cần đặt cùng thứ tự **ma, ten** ở hai vế.

</details>

### Bài 14 — EXCEPT và JOIN

Nếu yêu cầu là “mỗi khách chưa có đơn, hiển thị mã, tên và địa chỉ”, cách nào có thể rõ ràng hơn EXCEPT chỉ trên mã khách?

<details>
<summary>Đáp án gợi ý</summary>

**NOT EXISTS**:

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang, k.dia_chi
FROM khach_hang k
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang d
    WHERE d.ma_khach_hang = k.ma_khach_hang
);
~~~

Vì chỉ cần kiểm tra tồn tại theo mã, nhưng muốn trả các cột mô tả không thuộc khóa so sánh.

</details>

### Bài 15 — Chênh lệch số bản sao

A có ba dòng P01; B có hai dòng P01. EXCEPT mặc định và EXCEPT ALL trả mấy dòng P01?

<details>
<summary>Đáp án gợi ý</summary>

- **EXCEPT mặc định:** 0.
- **EXCEPT ALL:** 1.

</details>

### Bài 16 — ORDER BY

Viết truy vấn EXCEPT nhưng sắp kết quả mã tăng dần, đẩy NULL xuống cuối một cách tường minh.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
WITH hieu AS (
    SELECT ma FROM a
    EXCEPT
    SELECT ma FROM b
)
SELECT ma
FROM hieu
ORDER BY
    CASE WHEN ma IS NULL THEN 1 ELSE 0 END,
    ma ASC;
~~~

</details>

### Bài 17 — Ưu tiên phép toán

Vì sao nên dùng CTE khi câu truy vấn có cả UNION, INTERSECT và EXCEPT/MINUS?

<details>
<summary>Đáp án gợi ý</summary>

Vì phép nhóm có thể làm kết quả khác nhau và quy tắc ưu tiên/kết hợp không hoàn toàn giống giữa các phương ngữ hoặc phiên bản. CTE hoặc các nhánh được nhóm rõ cho biết chính xác muốn tính hiệu của hợp, hợp với hiệu hay giao với hiệu.

</details>

### Bài 18 — Bài toán đối soát giá

Hai bảng có cùng mã P01 nhưng giá khác nhau. EXCEPT chỉ trên mã có phát hiện thay đổi không? Nếu cần phát hiện sự khác biệt giá, nên làm gì?

<details>
<summary>Đáp án gợi ý</summary>

EXCEPT chỉ trên mã **không phát hiện** vì P01 có ở cả hai phía. Có thể EXCEPT trên cặp **(ma, gia)** để thấy khác biệt hàng, hoặc JOIN theo mã và so sánh giá với điều kiện null-safe để phân loại “mã mới”, “mã mất”, “giá đổi”.

</details>

### Bài 19 — Đếm lỗi dữ liệu

Nếu A và B có cùng các mã phân biệt nhưng số dòng mỗi mã khác nhau, truy vấn EXCEPT DISTINCT hai chiều sẽ báo gì?

<details>
<summary>Đáp án gợi ý</summary>

Có thể **không báo khác biệt nào** vì tập mã phân biệt hai phía giống nhau. Cần EXCEPT ALL theo hai chiều hoặc so sánh COUNT(*) GROUP BY ma để kiểm tra số bản sao.

</details>

### Bài 20 — Tổng kết lựa chọn

Chọn EXCEPT, EXCEPT ALL hoặc NOT EXISTS cho từng yêu cầu:

1. Mã chỉ có ở nguồn A, một lần mỗi mã.
2. Các bản sao còn dư của A sau khi đối trừ đúng số lần xuất hiện bên B.
3. Mỗi dòng khách hàng chưa có đơn, cần trả cả tên/địa chỉ.

<details>
<summary>Đáp án gợi ý</summary>

1. **EXCEPT** (hoặc MINUS trên Oracle truyền thống).
2. **EXCEPT ALL** khi DBMS hỗ trợ; nếu không, mô phỏng bằng đếm hoặc ROW_NUMBER.
3. **NOT EXISTS** với điều kiện theo mã khách, giúp giữ các cột mô tả từ bảng khách.

</details>

## 29. Tình huống tổng hợp: đối soát dữ liệu chuyển hệ

Giả sử cần kiểm tra dữ liệu sản phẩm giữa hệ thống cũ và hệ thống mới. Các câu hỏi phải tách bạch:

**Câu hỏi 1: Mã sản phẩm nào bị thiếu trong hệ thống mới?**

~~~sql
SELECT ma_san_pham FROM san_pham_cu
EXCEPT
SELECT ma_san_pham FROM san_pham_moi;
~~~

**Câu hỏi 2: Mã sản phẩm nào có trong hệ thống mới nhưng không có ở cũ?**

~~~sql
SELECT ma_san_pham FROM san_pham_moi
EXCEPT
SELECT ma_san_pham FROM san_pham_cu;
~~~

**Câu hỏi 3: Cặp (mã, giá) nào không còn giống nhau?**

~~~sql
SELECT ma_san_pham, gia_ban FROM san_pham_cu
EXCEPT
SELECT ma_san_pham, gia_ban FROM san_pham_moi;
~~~

**Câu hỏi 4: Có bị mất bản sao hay tạo dư bản sao không?**

Nếu mỗi bảng lẽ ra có **một mã duy nhất**, kiểm tra ràng buộc khóa trùng:

~~~sql
SELECT ma_san_pham, COUNT(*) AS so_dong
FROM san_pham_moi
GROUP BY ma_san_pham
HAVING COUNT(*) > 1;
~~~

Nếu dữ liệu hợp lệ cho phép nhiều dòng cùng bộ cột, cần đối soát **EXCEPT ALL** hai chiều hoặc COUNT theo toàn bộ bộ cột định nghĩa hàng.

**Câu hỏi 5: Có giá trị NULL trong mã không?**

~~~sql
SELECT COUNT(*) AS so_ma_thieu
FROM san_pham_moi
WHERE ma_san_pham IS NULL;
~~~

Dù EXCEPT có ngữ nghĩa rõ đối với NULL, khóa mã sản phẩm NULL có thể không được phép về nghiệp vụ và cần xử lý riêng, không chỉ suy ra từ kết quả phép hiệu.

**Câu hỏi 6: Kết quả có nhất quán giữa hai lần đọc không?**

Nếu nguồn đang được ghi dữ liệu song song, hai bản đọc có thể thuộc thời điểm khác nhau. Cần snapshot, watermark hoặc quy tắc đồng bộ phù hợp để tránh báo chênh lệch giả.

Một quy trình đối soát đầy đủ có thể gồm:

1. Xác nhận **cùng khóa nghiệp vụ**, cùng kiểu và cùng quy tắc chuẩn hóa.
2. Kiểm tra **NULL/duplicate** ở từng nguồn.
3. Tính **A EXCEPT B** và **B EXCEPT A** trên khóa.
4. So sánh **thuộc tính** của những khóa có ở cả hai.
5. Đối soát **số bản sao** nếu cần.
6. Lập báo cáo chênh lệch với **mã nguồn, giá trị, loại lỗi và thời điểm chụp dữ liệu**.
7. Xác nhận lại trên các mẫu có khả năng phát hiện sai về NULL, collation, số thập phân và ngày giờ.
8. Chỉ sau khi đã phân loại nguyên nhân mới thực hiện cập nhật/bổ sung/xóa dữ liệu.

## 30. Ghi nhớ trọng tâm

1. **EXCEPT** lấy những hàng có ở kết quả **bên trái** nhưng không có trong kết quả **bên phải**. Đảo vế có thể đổi kết quả.
2. **EXCEPT mặc định** có ngữ nghĩa **DISTINCT**: loại các hàng trùng; nó không giữ số bản sao dư.
3. **EXCEPT ALL** lấy hiệu theo số lần xuất hiện: **max(countA − countB, 0)** cho mỗi hàng, kể cả nhóm NULL theo ngữ nghĩa set.
4. SQL so sánh **toàn bộ danh sách cột SELECT theo vị trí**, không tự dùng khóa chính hay tên cột để xác định phần tử cần trừ.
5. Hai vế phải có **cùng số cột** và **kiểu dữ liệu tương thích**. Cùng tên cột nhưng đổi thứ tự vẫn có thể sai.
6. **NULL trong EXCEPT** được xử lý theo quy tắc hàng **not distinct**; đừng suy luận rằng NULL ở hai tập không thể khớp chỉ vì NULL = NULL là UNKNOWN.
7. **NOT EXISTS với phép =** giữ các dòng khóa NULL ở A không khớp B; nó cũng không tự loại trùng. Vì vậy không phải bản thay thế hoàn toàn tương đương của EXCEPT.
8. **NOT IN** có thể cho kết quả bất ngờ khi tập con chứa NULL. Với ý định tìm bản ghi không có quan hệ, NOT EXISTS thường rõ hơn.
9. **MINUS** là cú pháp truyền thống của Oracle; Oracle 19c phổ biến dùng MINUS. **PostgreSQL, SQL Server, SQLite, MySQL 8.0.31+** dùng EXCEPT theo hỗ trợ của từng hệ.
10. **EXCEPT ALL không được hỗ trợ đồng nhất**. Đừng dùng nó trên SQL Server/SQLite thông thường nếu không có giải pháp thay thế.
11. **UNION/INTERSECT/EXCEPT** khi kết hợp cần thể hiện nhóm phép tính rõ bằng CTE/subquery; **ORDER BY** phải áp dụng ở kết quả cuối nếu cần thứ tự.
12. EXCEPT trên **mã** tìm mã thiếu; EXCEPT trên **(mã, giá)** tìm cặp hàng khác biệt. Hai câu hỏi không giống nhau.
13. Đối soát hai hệ nên kiểm tra **hai chiều**, **NULL**, **khóa trùng**, **kiểu/collation**, **số bản sao** và **snapshot dữ liệu**, không chỉ một EXCEPT duy nhất.
14. Truy vấn chạy đúng cú pháp chưa đủ: kết quả đúng phải khớp với **định nghĩa hàng**, **chính sách dữ liệu thiếu** và **yêu cầu nghiệp vụ**.

### Tài liệu tham khảo định hướng

Khi cần áp dụng vào sản phẩm thật, nên đối chiếu tài liệu chính thức ở các mục **Set Operations**, **EXCEPT**, **MINUS**, **UNION/INTERSECT**, **NULL handling**, **data type compatibility** và **query execution plans**:

- **PostgreSQL Documentation:** *Combining Queries (UNION, INTERSECT, EXCEPT)*, *SELECT*, *Aggregate Functions*.
- **MySQL Reference Manual:** *Set Operations with UNION, INTERSECT, and EXCEPT*; cần xem **phiên bản 8.0.31+** khi sử dụng EXCEPT.
- **Microsoft Learn — Transact-SQL:** *Set Operators — EXCEPT and INTERSECT*, *Query Processing*, *Data Type Precedence*.
- **Oracle Database SQL Language Reference:** *The Set Operators* và *MINUS/EXCEPT*, đối chiếu riêng **19c** với **23ai hoặc thế hệ mới**.
- **SQLite Documentation:** *SELECT — Compound Select Statements*, *NULL Handling*.

**Câu hỏi kiểm tra quan trọng nhất trước khi viết EXCEPT/MINUS:** **“Một hàng được coi là giống nhau khi những cột nào giống nhau, có cần phân biệt số bản sao không, và DBMS này xử lý NULL/kiểu dữ liệu theo quy tắc nào?”**. Trả lời chính xác ba điều đó giúp phép hiệu tập hợp phản ánh đúng ý định đối soát dữ liệu.
