# UPPER, LOWER, độ dài ký tự và độ dài byte trong SQL

> **Module:** Database SQL  
> **Chương:** Biểu thức và hàm  
> **Trọng tâm:** Biết cách chuyển đổi chữ hoa/chữ thường bằng **UPPER**, **LOWER**; phân biệt **độ dài chuỗi theo ký tự** với **độ dài theo byte**, nhất là khi làm việc với tiếng Việt và Unicode; lựa chọn đúng hàm cho từng hệ quản trị và đúng yêu cầu nghiệp vụ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích giá trị mà **UPPER(...)** và **LOWER(...)** trả về, và phân biệt biểu thức chuyển đổi chữ với thay đổi dữ liệu đã lưu.
- Dùng UPPER/LOWER trong **SELECT**, **WHERE**, **ORDER BY**, **GROUP BY** và các truy vấn phân loại dữ liệu, đồng thời nhận biết các giới hạn do **collation**, bộ ký tự và ngôn ngữ.
- Phân biệt **byte**, **ký tự/code point Unicode**, **đơn vị mã UTF-16** và **ký tự hiển thị (grapheme cluster)**.
- Dùng **CHAR_LENGTH/CHARACTER_LENGTH**, **OCTET_LENGTH**, **LENGTH**, **LEN**, **DATALENGTH**, **LENGTHB** đúng ngữ cảnh hệ quản trị.
- Dự đoán vì sao một chuỗi tiếng Việt có ít ký tự hơn số byte của nó khi được mã hóa UTF-8.
- Xử lý **NULL**, chuỗi rỗng, dấu cách cuối chuỗi, ký tự kết hợp dấu và emoji khi tính độ dài.
- Viết điều kiện kiểm tra độ dài văn bản và giới hạn dung lượng mà không nhầm **số ký tự** với **số byte**.
- Nhận diện tác động của hàm trên cột đối với chỉ mục, hiệu năng và kiểm tra dữ liệu đầu vào trong ứng dụng Java/JDBC.

## 2. Tại sao các thao tác chuỗi này quan trọng?

Trong một ứng dụng, dữ liệu văn bản xuất hiện ở tên khách hàng, email, mã hàng, nhãn hiển thị, ghi chú, địa chỉ và nhiều trường khác. Những nhu cầu thường gặp là:

1. Hiển thị mã sản phẩm theo chữ hoa: **abc-001** → **ABC-001**.
2. Tìm tên hoặc email mà không phân biệt kiểu viết hoa/thường.
3. Kiểm tra trường tên có vượt quá giới hạn ký tự mà giao diện quy định không.
4. Kiểm tra số byte trước khi gửi một chuỗi vào giao thức, tệp hoặc cột có giới hạn byte.
5. Tìm các bản ghi chỉ có khoảng trắng hoặc chưa có dữ liệu.
6. Thống kê độ dài nội dung, ví dụ nhận diện những nhãn quá dài trên màn hình.

Hai nhóm thao tác được dùng thường xuyên là:

- **Biến đổi hình thức văn bản:** UPPER, LOWER.
- **Đo độ dài văn bản:** theo ký tự hoặc theo byte.

Chúng có vẻ đơn giản nhưng dễ gây lỗi với Unicode. Chẳng hạn, chuỗi **'Café'** được mã hóa UTF-8 thường có **4 ký tự Unicode** nhưng **5 byte**, vì ký tự **é** chiếm hai byte. Nếu chỉ kiểm tra số ký tự trong khi hệ thống giới hạn byte, ứng dụng có thể chấp nhận một dữ liệu không vừa kích thước yêu cầu.

## 3. UPPER và LOWER hoạt động như thế nào?

### 3.1. UPPER: đổi chữ thường thành chữ hoa

Cú pháp SQL phổ biến:

~~~sql
UPPER(bieu_thuc_chuoi)
~~~

Ví dụ:

~~~sql
SELECT UPPER('sql basic') AS chu_hoa;
~~~

Kết quả mong đợi:

| chu_hoa |
|---|
| SQL BASIC |

Hàm UPPER nhận một biểu thức văn bản và trả về phiên bản được chuyển sang chữ hoa theo quy tắc của hệ quản trị, bộ ký tự và collation liên quan.

Ví dụ thực tế:

~~~sql
SELECT
    ma_san_pham,
    UPPER(ma_san_pham) AS ma_chu_hoa
FROM san_pham;
~~~

Nếu mã nguồn là **'sp-a01'**, cột kết quả **ma_chu_hoa** sẽ là **'SP-A01'** trong cách chuyển đổi chữ Latin thông thường.

**UPPER trong SELECT không tự thay đổi giá trị đang lưu.** Để lưu mã dạng chữ hoa vào bảng, cần một thao tác ghi dữ liệu có chủ đích như UPDATE hoặc một quy tắc chuẩn hóa tại thời điểm INSERT.

### 3.2. LOWER: đổi chữ hoa thành chữ thường

Cú pháp:

~~~sql
LOWER(bieu_thuc_chuoi)
~~~

Ví dụ:

~~~sql
SELECT LOWER('SQL BASIC') AS chu_thuong;
~~~

Kết quả:

| chu_thuong |
|---|
| sql basic |

Dùng với cột bảng:

~~~sql
SELECT
    email,
    LOWER(email) AS email_chu_thuong
FROM nguoi_dung;
~~~

Nếu email là **'LINH@EXAMPLE.COM'**, kết quả có thể là **'linh@example.com'** theo quy tắc chữ Latin thông thường.

**Chú ý:** LOWER chỉ đổi cách viết hoa/thường. Nó không tự xóa dấu, cắt khoảng trắng, loại ký tự đặc biệt hay bảo đảm hai chuỗi được coi là bằng nhau theo quy tắc nghiệp vụ.

### 3.3. Hai hàm thường được dùng trong các biểu thức lớn hơn

~~~sql
SELECT
    ma_nguoi_dung,
    UPPER(ten_hien_thi) AS ten_in_hoa,
    LOWER(email) AS email_chu_thuong
FROM nguoi_dung;
~~~

Có thể lồng với hàm khác:

~~~sql
SELECT
    ma_nguoi_dung,
    LOWER(TRIM(email)) AS email_da_chuan_hoa_hien_thi
FROM nguoi_dung;
~~~

**TRIM** thường xóa khoảng trắng ở đầu/cuối theo quy tắc của hệ quản trị; **LOWER** chuyển chữ hoa thành chữ thường. Kết quả biểu thức được tính khi truy vấn, không đồng nghĩa email đã được sửa trong bảng.

Tên **email_da_chuan_hoa_hien_thi** ở ví dụ chỉ là **bí danh cột đầu ra**. Chuẩn hóa email để dùng làm định danh trong hệ thống thực tế đòi hỏi chính sách rõ hơn nhiều, không thể tự mặc định chỉ cần LOWER/TRIM là đủ.

## 4. Bộ dữ liệu minh họa

Giả sử có bảng **nguoi_dung**:

| ma_nguoi_dung | ten_hien_thi | email |
|---:|---|---|
| 1 | An | An@Example.com |
| 2 | Bình | binh@example.com |
| 3 | LINH | LINH@EXAMPLE.COM |
| 4 | Café | cafe@example.com |
| 5 | Cafe + dấu sắc kết hợp trên e | cafe@example.net |
| 6 | 😊 | emoji@example.com |
| 7 | NULL | NULL |
| 8 | Chuỗi rỗng | empty@example.com |
| 9 | AB + một dấu cách cuối | space@example.com |

Để tránh nhầm lẫn trong bảng trình bày:

- Hàng **5** là một chuỗi Unicode gồm các điểm mã **C**, **a**, **f**, **e**, rồi **dấu sắc kết hợp U+0301**, thường được hiển thị thành **Café**. Nó nhìn gần giống **Café** của hàng 4, nhưng không cùng dãy điểm mã.
- Hàng **8** chứa **''** (chuỗi có độ dài 0) ở cột ten_hien_thi, nếu DBMS phân biệt chuỗi rỗng với NULL.
- Hàng **9** chứa đúng ba ký tự **'AB '**: A, B và một dấu cách ở cuối.
- Hàng **7** chứa NULL, không phải chuỗi ký tự gồm bốn chữ cái N-U-L-L.

Các ví dụ độ dài theo byte ở phần sau giả định **chuỗi được mã hóa UTF-8**, không phải quy tắc chung cho mọi cơ sở dữ liệu.

### 4.1. Xem kết quả chữ hoa và chữ thường

~~~sql
SELECT
    ma_nguoi_dung,
    ten_hien_thi,
    UPPER(ten_hien_thi) AS ten_hoa,
    LOWER(ten_hien_thi) AS ten_thuong
FROM nguoi_dung
ORDER BY ma_nguoi_dung;
~~~

Các hàng Latin đơn giản có kết quả trực quan:

| Dữ liệu | UPPER | LOWER |
|---|---|---|
| 'An' | 'AN' | 'an' |
| 'LINH' | 'LINH' | 'linh' |
| 'Café' | Phổ biến là 'CAFÉ' | Phổ biến là 'café' |
| 'AB ' | 'AB ' | 'ab ' |
| NULL | NULL | NULL |

Với ký tự Unicode đặc biệt, chữ có dấu và quy tắc ngôn ngữ, kết quả chính xác có thể phụ thuộc DBMS, collation và thư viện xử lý Unicode. Không dùng bảng này như một bảo đảm mọi hệ quản trị đều áp dụng cùng bảng ánh xạ chữ hoa/chữ thường.

## 5. Dùng UPPER và LOWER trong điều kiện WHERE

Một yêu cầu thường gặp là tìm tên mà không phân biệt chữ hoa và chữ thường.

Ví dụ, nếu người dùng nhập **'linh'**:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE LOWER(ten_hien_thi) = 'linh';
~~~

Với tập mẫu, hàng **3** có tên **LINH** được chọn trong quy tắc chữ Latin thông thường.

Cũng có thể chuyển hai phía:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE LOWER(ten_hien_thi) = LOWER(?);
~~~

Dấu **?** là chỗ giữ tham số theo cú pháp JDBC. Khi bind **'LiNh'**, hai phía cùng được chuyển về chữ thường trước khi so sánh.

### 5.1. Chuyển cả hai vế có thực sự “không phân biệt hoa/thường” trong mọi ngôn ngữ?

Không thể khẳng định như vậy cho mọi văn bản.

UPPER/LOWER dùng các quy tắc ánh xạ chữ hoa/thường do DBMS và collation quy định. Chúng **không nhất thiết tương đương** với phép so sánh không phân biệt chữ hoa/thường của một ngôn ngữ cụ thể. Các trường hợp như:

- Chữ **I/i** trong tiếng Thổ Nhĩ Kỳ và các biến thể có/không có dấu chấm.
- Chữ có dấu và chữ không dấu như **'a'** so với **'á'**.
- Chữ có nhiều cách biểu diễn Unicode (ký tự ghép sẵn so với ký tự kết hợp dấu).
- Một số ký tự khi chuyển đổi hoa/thường có thể tạo ra **nhiều điểm mã** hoặc đổi độ dài biểu diễn.

Kết quả so sánh còn phụ thuộc **collation** của các biểu thức. Vì vậy, câu “LOWER(x) = LOWER(y) chắc chắn phát hiện mọi chuỗi tương đương về mặt ngôn ngữ” là quá mạnh.

**Cách làm thực tế:** xác định yêu cầu tìm kiếm là phân biệt hay không phân biệt chữ hoa, dấu và các quy tắc ngôn ngữ; sau đó chọn **collation**, kiểu dữ liệu, chuẩn hóa Unicode hoặc cơ chế tìm kiếm phù hợp. Kiểm thử với đúng DBMS và tập dữ liệu của ngôn ngữ được hỗ trợ.

### 5.2. So sánh bằng UPPER

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE UPPER(ten_hien_thi) = UPPER(?);
~~~

Cách viết này tương tự việc dùng LOWER cho một số nhu cầu. Không có quy tắc chung rằng UPPER luôn “đúng hơn” LOWER hoặc ngược lại.

Với mã định danh nghiệp vụ chỉ gồm **ASCII A–Z, 0–9**, việc chuẩn hóa về chữ hoa đôi khi thuận tiện:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE UPPER(ma_san_pham) = UPPER(?);
~~~

Dù vậy, cần quy định rõ mã có phân biệt chữ hoa/thường hay không. Với token, mật khẩu hoặc chuỗi bảo mật, **không được tự ý biến đổi hoa/thường**, vì thay đổi đó có thể làm mất ý nghĩa hoặc giảm không gian giá trị.

### 5.3. Chuỗi đầu vào NULL

~~~sql
SELECT ma_nguoi_dung
FROM nguoi_dung
WHERE LOWER(email) = LOWER(?);
~~~

Nếu cột email hoặc tham số là NULL, phép so sánh thông thường với NULL không cho TRUE. Khi muốn tìm người **chưa có email**, viết:

~~~sql
SELECT ma_nguoi_dung
FROM nguoi_dung
WHERE email IS NULL;
~~~

UPPER(NULL) và LOWER(NULL) thông thường trả NULL; chúng không biến dữ liệu thiếu thành chuỗi rỗng hay giá trị mặc định.

### 5.4. UPPER/LOWER với LIKE

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE LOWER(ten_hien_thi) LIKE LOWER(?);
~~~

Giả sử bind mẫu **'lin%'**, truy vấn tìm tên bắt đầu với dạng chữ tương ứng. Nhưng dấu **%** và **_** của LIKE vẫn là ký tự đại diện, không bị vô hiệu hóa bởi LOWER.

Nếu người dùng muốn tìm dấu phần trăm **thật**, ứng dụng phải xử lý ký tự escape theo cú pháp LIKE và DBMS, ngoài việc truyền tham số để tránh SQL injection.

**Nhớ rằng:** khả năng khớp chữ có dấu, ký tự kết hợp và chữ hoa/thường trong LIKE vẫn phụ thuộc quy tắc so sánh của hệ quản trị.

## 6. LOWER/UPPER trong ORDER BY, GROUP BY và DISTINCT

### 6.1. Sắp xếp theo dạng chuyển chữ

~~~sql
SELECT
    ma_nguoi_dung,
    ten_hien_thi
FROM nguoi_dung
ORDER BY LOWER(ten_hien_thi), ma_nguoi_dung;
~~~

Truy vấn yêu cầu sắp xếp theo dạng chữ thường của tên, rồi theo mã người dùng. Tuy nhiên, **thứ tự ký tự vẫn do collation quyết định**. LOW​ER không tự tạo thứ tự từ điển tiếng Việt chuẩn theo mọi quy tắc dấu.

Nếu hai tên sau LOWER được xem là bằng nhau, cột **ma_nguoi_dung** tạo tiêu chí phụ để thứ tự ổn định hơn trong trường hợp dữ liệu mẫu có khóa duy nhất.

Vị trí NULL trong ORDER BY có thể khác nhau giữa DBMS. Nếu muốn NULL đứng cuối:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
ORDER BY
    CASE WHEN ten_hien_thi IS NULL THEN 1 ELSE 0 END,
    LOWER(ten_hien_thi),
    ma_nguoi_dung;
~~~

### 6.2. Gom nhóm theo tên không phân biệt kiểu chữ

~~~sql
SELECT
    LOWER(trang_thai) AS trang_thai_thuong,
    COUNT(*) AS so_ban_ghi
FROM don_hang
GROUP BY LOWER(trang_thai)
ORDER BY trang_thai_thuong;
~~~

Nếu bảng có các giá trị trạng thái **'PAID'**, **'Paid'** và **'paid'**, các giá trị này có thể được nhóm chung sau LOWER trong quy tắc chữ Latin phù hợp. Tuy nhiên, nếu trạng thái là mã nghiệp vụ, cách tốt hơn thường là **quy định bộ giá trị chuẩn ngay khi ghi** để không phải biến đổi lặp lại ở mọi truy vấn.

### 6.3. Đếm giá trị khác biệt sau chuyển chữ

~~~sql
SELECT COUNT(DISTINCT LOWER(email)) AS so_email_phan_biet
FROM nguoi_dung;
~~~

Ví dụ này đếm các giá trị email khác nhau sau khi LOWER, theo quy tắc DISTINCT và collation của DBMS. **COUNT(DISTINCT expr)** thường bỏ qua kết quả expr NULL.

Không nên dùng kết quả này để khẳng định số danh tính người dùng duy nhất: email còn có quy tắc chuẩn hóa và xác minh riêng, có thể khác nhau theo hệ thống mail và chính sách sản phẩm.

## 7. “Độ dài” của một chuỗi có nhiều cách hiểu

Khi nhìn chữ **'Café'**, có ít nhất bốn câu hỏi khác nhau:

1. Chuỗi có bao nhiêu **byte** khi mã hóa để lưu hoặc truyền?
2. Chuỗi gồm bao nhiêu **điểm mã Unicode** (code point)?
3. Chuỗi có bao nhiêu **đơn vị mã UTF-16**?
4. Người dùng thấy bao nhiêu **cụm ký tự hiển thị** (grapheme cluster)?

Bốn con số có thể bằng nhau với ASCII đơn giản nhưng khác nhau với tiếng Việt có dấu, chữ ghép bằng dấu kết hợp và emoji.

### 7.1. Byte là gì?

**Byte** là đơn vị dữ liệu gồm 8 bit. Trong mã hóa UTF-8:

- Ký tự ASCII cơ bản như **A**, **0**, khoảng trắng thường dùng **1 byte**.
- Nhiều chữ Latin có dấu như **é**, **à** dùng **2 byte**.
- Nhiều ký tự khác, ví dụ một số chữ có dấu tiếng Việt như **ộ**, dùng **3 byte**.
- Nhiều emoji như **😊** dùng **4 byte**.

Một chuỗi gồm 10 ký tự không nhất thiết chỉ chiếm 10 byte trong UTF-8.

### 7.2. Điểm mã Unicode

Một **Unicode code point** là vị trí trong hệ thống ký tự Unicode. Chẳng hạn:

- **A** là U+0041.
- **é** ghép sẵn là U+00E9.
- Dấu sắc kết hợp là U+0301.
- Emoji **😊** là U+1F60A.

**'Café'** khi viết bằng **é ghép sẵn** có 4 code point: C, a, f, é.

Một dạng trông gần giống, **'Café'**, có thể là 5 code point: C, a, f, e, dấu sắc kết hợp. Người dùng thường vẫn nhìn thấy 4 cụm chữ.

### 7.3. Đơn vị mã UTF-16

UTF-16 mã hóa nhiều ký tự Unicode phổ biến bằng **một đơn vị mã 16 bit**, nhưng một số ký tự ngoài Basic Multilingual Plane như emoji **😊** cần **hai đơn vị mã UTF-16** (một cặp surrogate).

Điều này quan trọng khi so sánh SQL với Java:

~~~java
String s = "😊";
System.out.println(s.length());            // 2 đơn vị mã UTF-16
System.out.println(s.codePointCount(0, s.length())); // 1 code point
~~~

**String.length() của Java không trả số grapheme hiển thị.** Nó trả số đơn vị mã UTF-16.

### 7.4. Grapheme cluster: điều người dùng nhìn thấy

Một emoji có thể gồm nhiều code point ghép lại bằng ký tự nối và dấu biến thể. Một ký tự có dấu có thể gồm ký tự gốc và dấu kết hợp. Người dùng có thể nhìn thấy **một biểu tượng** trong khi chuỗi chứa **nhiều code point**, nhiều đơn vị UTF-16 và nhiều byte.

Ví dụ, dạng **'é'** gồm **e + dấu sắc kết hợp**:

- Số code point: **2**.
- Số grapheme cluster hiển thị thường là **1**.
- Số byte khi mã hóa UTF-8: **3**.

Vì vậy, “giới hạn 20 ký tự hiển thị” trong giao diện không thể được diễn giải một cách máy móc là **CHAR_LENGTH(x) <= 20** trên mọi DBMS. Hệ quản trị có thể đo ký tự theo đơn vị khác với thuật toán phân đoạn grapheme của ứng dụng.

## 8. Hàm đo độ dài ký tự

Trong SQL chuẩn, các tên hàm thường thấy là:

~~~sql
CHAR_LENGTH(bieu_thuc_chuoi)
~~~

hoặc:

~~~sql
CHARACTER_LENGTH(bieu_thuc_chuoi)
~~~

Với một chuỗi ký tự, các hàm này biểu diễn **độ dài theo ký tự** theo ngữ nghĩa của DBMS, khác với số byte cần để mã hóa chuỗi.

Ví dụ:

~~~sql
SELECT
    CHAR_LENGTH('ABC') AS so_ky_tu,
    CHAR_LENGTH('AB ') AS so_ky_tu_co_khoang_trang;
~~~

Trong các DBMS hỗ trợ CHAR_LENGTH và tính dấu cách cuối trong độ dài chuỗi như thông thường:

| so_ky_tu | so_ky_tu_co_khoang_trang |
|---:|---:|
| 3 | 3 |

Đừng đồng nhất tất cả hàm có tên **LENGTH** với CHAR_LENGTH. Tên LENGTH mang ý nghĩa khác nhau tùy phương ngữ: MySQL đo số byte, còn PostgreSQL và SQLite dùng LENGTH cho độ dài ký tự của chuỗi văn bản trong những trường hợp thông thường.

### 8.1. Độ dài của cột trong bảng

~~~sql
SELECT
    ma_nguoi_dung,
    ten_hien_thi,
    CHAR_LENGTH(ten_hien_thi) AS so_ky_tu
FROM nguoi_dung;
~~~

Khi DBMS hỗ trợ CHAR_LENGTH, truy vấn này giúp phát hiện tên vượt giới hạn ký tự.

Ví dụ, yêu cầu “tên không quá 30 ký tự”:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE CHAR_LENGTH(ten_hien_thi) > 30;
~~~

Truy vấn tìm các hàng **có tên không NULL** và vượt giới hạn theo phép đếm CHAR_LENGTH. Với tên NULL, kết quả CHAR_LENGTH(NULL) thông thường là NULL, rồi NULL > 30 là UNKNOWN và WHERE loại dòng. Nếu cần tìm cả tên NULL, phải thêm điều kiện **OR ten_hien_thi IS NULL** theo yêu cầu nghiệp vụ.

## 9. Hàm đo độ dài byte

Tên hàm trong SQL chuẩn thường là:

~~~sql
OCTET_LENGTH(bieu_thuc)
~~~

**Octet** là một nhóm 8 bit, tương đương byte theo cách dùng hiện đại. OCTET_LENGTH đo số octet của biểu diễn dữ liệu do DBMS sử dụng cho kiểu đầu vào phù hợp.

Ví dụ trong cơ sở dữ liệu dùng UTF-8:

~~~sql
SELECT
    CHAR_LENGTH('Café') AS do_dai_ky_tu,
    OCTET_LENGTH('Café') AS do_dai_byte;
~~~

Kết quả mong đợi nếu literal được hiểu là chuỗi Unicode UTF-8 với **é ghép sẵn**:

| do_dai_ky_tu | do_dai_byte |
|---:|---:|
| 4 | 5 |

Trong UTF-8: C (1 byte) + a (1) + f (1) + é (2) = 5 byte.

### 9.1. Các ví dụ so sánh trong UTF-8

| Chuỗi | Cách biểu diễn | Số code point | Số byte UTF-8 |
|---|---|---:|---:|
| **'SQL'** | ASCII | 3 | 3 |
| **'AB '** | ASCII, có khoảng trắng cuối | 3 | 3 |
| **'Café'** | é ghép sẵn | 4 | 5 |
| **'Café'** | e + dấu sắc kết hợp | 5 | 6 |
| **'😊'** | Một code point emoji | 1 | 4 |
| **'Hà Nội'** | à, ộ ghép sẵn | 6 | 9 |
| **''** | Chuỗi rỗng | 0 | 0 |
| **NULL** | Không có giá trị | Không áp dụng | Không áp dụng |

Các con số trên là phép đếm cho **đúng dãy code point đã nêu khi mã hóa UTF-8**. Chúng không bảo đảm một hàm SQL cụ thể trên mọi hệ sẽ trả đúng cột “số code point”, vì DBMS còn có kiểu dữ liệu, mã hóa, collation và quy tắc tính độ dài riêng. Với Oracle truyền thống, chuỗi rỗng còn có thể được coi là NULL.

### 9.2. Tại sao byte liên quan đến giới hạn lưu trữ?

Giả sử một API giới hạn tên ở **10 byte UTF-8**. Chuỗi **'Hà Nội'** có 6 code point và 9 byte UTF-8, nên nằm trong giới hạn; chuỗi **'😊😊😊'** có 3 code point nhưng 12 byte UTF-8, nên vượt giới hạn.

Một điều kiện chỉ kiểm tra **CHAR_LENGTH(ten) <= 10** sẽ không phát hiện trường hợp ba emoji chiếm 12 byte. Nếu yêu cầu thực sự là **dung lượng UTF-8**, cần đo byte theo đúng mã hóa mà API nhận; OCTET_LENGTH trên cột chỉ tương đương số byte UTF-8 nếu biểu diễn mà nó đo là UTF-8.

### 9.3. Độ dài byte của giá trị khác dung lượng vật lý của một hàng

OCTET_LENGTH hoặc hàm tương đương thường đo **độ dài biểu diễn giá trị**. Nó không nhất thiết bằng tổng dung lượng thật của hàng trong tệp cơ sở dữ liệu, vì còn:

- Header/metadata của hàng, cột và kiểu dữ liệu.
- Cơ chế nén và lưu trữ ngoài trang.
- Căn chỉnh bộ nhớ, độ dài biến thiên, chỉ mục.
- Mã hóa lưu trữ của sản phẩm.
- Bản ghi giao dịch hoặc lịch sử phiên bản dữ liệu.

Nếu mục tiêu là đo kích thước một bảng hay dung lượng đĩa, dùng công cụ thống kê lưu trữ của DBMS, không cộng OCTET_LENGTH của vài cột rồi coi đó là số byte trên đĩa.

## 10. Phân biệt CHAR_LENGTH, LENGTH, OCTET_LENGTH, LEN và DATALENGTH theo DBMS

Tên hàm thay đổi đáng kể giữa các hệ quản trị. Bảng dưới đây là định hướng dành cho các kiểu chuỗi văn bản phổ biến.

| DBMS | Đếm độ dài theo ký tự | Đếm độ dài theo byte | Lưu ý |
|---|---|---|---|
| **PostgreSQL** | CHAR_LENGTH(), CHARACTER_LENGTH(), LENGTH() với text | OCTET_LENGTH() với text | Byte phụ thuộc encoding của giá trị; cơ sở dữ liệu UTF-8 cho các số như bảng ví dụ |
| **MySQL** | CHAR_LENGTH(), CHARACTER_LENGTH() | LENGTH(), OCTET_LENGTH() | **LENGTH() đếm byte**, là điểm rất dễ nhầm với PostgreSQL |
| **SQL Server** | LEN() | DATALENGTH() | **LEN() bỏ qua khoảng trắng cuối**, DATALENGTH đo byte; UTF-16, UTF-8 và collation ảnh hưởng ngữ nghĩa |
| **Oracle Database** | LENGTH(), LENGTHC() theo quy tắc ký tự của Oracle | LENGTHB() | Có thêm LENGTH2()/LENGTH4(); dữ liệu và kiểu ký tự ảnh hưởng chi tiết |
| **SQLite** | length() với giá trị TEXT | octet_length() (từ bản 3.43.0) hoặc đo byte qua BLOB đúng kiểu | Với TEXT, length() có quy tắc riêng đối với ký tự NUL; SQLite dùng hệ thống kiểu linh hoạt |

**Không nên suy luận chỉ từ tên hàm.** Câu **LENGTH(ten)** có thể đang đếm ký tự trên PostgreSQL nhưng đếm byte trên MySQL. Đó là lý do một câu lệnh đúng ở DBMS này có thể lọc sai ở DBMS khác dù cùng chạy thành công.

### 10.1. PostgreSQL: LENGTH và OCTET_LENGTH

PostgreSQL hỗ trợ:

~~~sql
SELECT
    LENGTH('Café') AS do_dai_ky_tu,
    CHAR_LENGTH('Café') AS do_dai_ky_tu_2,
    OCTET_LENGTH('Café') AS do_dai_byte;
~~~

Với cơ sở dữ liệu UTF-8 và literal như mô tả, kết quả dự kiến là **4, 4, 5**.

Dùng trên cột:

~~~sql
SELECT
    ma_nguoi_dung,
    LENGTH(ten_hien_thi) AS ky_tu,
    OCTET_LENGTH(ten_hien_thi) AS byte
FROM nguoi_dung;
~~~

Khi giá trị thuộc kiểu cố định **CHAR(n)**, các quy tắc khoảng trắng đệm và phép ép kiểu có thể làm kết quả khác kỳ vọng khi so với TEXT/VARCHAR. Vì vậy, nếu công việc phụ thuộc chính xác vào dấu cách cuối, phải thử trên đúng kiểu cột.

### 10.2. MySQL: LENGTH đo byte, CHAR_LENGTH đo ký tự

Ví dụ phổ biến trong cơ sở dữ liệu/cột có bộ ký tự **utf8mb4**:

~~~sql
SELECT
    CHAR_LENGTH('Café') AS ky_tu,
    LENGTH('Café') AS byte,
    OCTET_LENGTH('Café') AS byte_2;
~~~

Nếu literal được truyền với mã hóa hỗ trợ đúng ký tự, kết quả dự kiến là **4, 5, 5**.

Giả sử cần phát hiện nội dung hơn 20 ký tự:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE CHAR_LENGTH(ten_hien_thi) > 20;
~~~

Nếu cần phát hiện hơn 20 byte của biểu diễn chuỗi trong bộ ký tự cột:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE LENGTH(ten_hien_thi) > 20;
~~~

Hai truy vấn có thể trả những tập hàng khác nhau với tiếng Việt và emoji. Nếu cột dùng một bộ ký tự không phải UTF-8, số byte cũng khác. MySQL phân biệt các bộ ký tự và collation; khi kiểm thử, phải biết cột và kết nối thực sự dùng loại nào.

### 10.3. SQL Server: LEN khác DATALENGTH

SQL Server thường dùng:

~~~sql
SELECT
    LEN('ABC') AS so_ky_tu,
    DATALENGTH('ABC') AS so_byte;
~~~

Nhưng ví dụ có dấu cách cuối mới thể hiện khác biệt đặc biệt:

~~~sql
SELECT
    LEN('AB ') AS do_dai_len,
    DATALENGTH('AB ') AS do_dai_byte;
~~~

Trong ví dụ với chuỗi ASCII kiểu VARCHAR thông thường, **LEN('AB ') = 2** vì bỏ qua khoảng trắng cuối, còn **DATALENGTH('AB ') = 3** vì tính cả byte biểu diễn dấu cách.

Với Unicode NVARCHAR:

~~~sql
SELECT
    LEN(N'AB ') AS do_dai_len,
    DATALENGTH(N'AB ') AS do_dai_byte;
~~~

Ở biểu diễn NVARCHAR UTF-16 thông thường, kết quả là **2** và **6**. Dấu **N** giúp literal là chuỗi Unicode kiểu NVARCHAR, có vai trò quan trọng khi chứa ký tự tiếng Việt/emoji trong các môi trường SQL Server.

**Chú ý UTF-16 và collation:** với ký tự ngoài BMP như emoji, LEN có thể đếm **một cặp surrogate là một ký tự** khi dùng collation hỗ trợ supplementary character (SC), nhưng với collation khác quy tắc đếm có thể khác. DATALENGTH(N'😊') thường là **4 byte** nếu ký tự được lưu bằng hai đơn vị UTF-16; điều đó không có nghĩa emoji gồm bốn ký tự.

Ngoài ra, kiểu **VARCHAR** dưới collation hỗ trợ UTF-8 ở SQL Server có thể có độ dài byte khác với VARCHAR dùng bảng mã đơn byte hoặc kiểu NVARCHAR. Đừng mặc định **DATALENGTH(x) / 2** luôn là số ký tự của mọi chuỗi Unicode.

### 10.4. Oracle Database: LENGTH, LENGTHB, LENGTHC

Oracle có nhiều hàm độ dài:

~~~sql
SELECT
    LENGTH('Café') AS do_dai_ky_tu,
    LENGTHB('Café') AS do_dai_byte
FROM dual;
~~~

Nếu cơ sở dữ liệu dùng bộ ký tự **AL32UTF8**, literal được lưu đúng dạng ghép sẵn và kiểu dữ liệu tương ứng, kết quả dự kiến là **4** và **5**.

Các hàm **LENGTHC**, **LENGTH2**, **LENGTH4** cho phép đo theo những định nghĩa ký tự/mã Unicode khác nhau trong Oracle. Việc chọn hàm cần dựa vào ý định đo *ký tự trong bộ ký tự hiện tại*, *ký tự Unicode hoàn chỉnh* hay *đơn vị UCS2/UCS4* và giới hạn kiểu đối số.

**Điểm dễ sai:** Oracle truyền thống coi chuỗi ký tự độ dài 0 như **NULL** trong nhiều ngữ cảnh. Do đó, biểu thức như:

~~~sql
SELECT LENGTH('') FROM dual;
~~~

có thể cho NULL, khác với kết quả 0 ở PostgreSQL/MySQL/SQLite đối với chuỗi rỗng thông thường. Không xây quy tắc “chuỗi rỗng luôn có độ dài 0” nếu ứng dụng cần chạy nhiều DBMS.

Ngoài ra, khi khai báo **VARCHAR2(n BYTE)** hoặc **VARCHAR2(n CHAR)**, Oracle phân biệt giới hạn byte và giới hạn ký tự; các thiết lập độ dài mặc định và giới hạn vật lý của cột phải được đối chiếu theo DBMS/phiên bản.

### 10.5. SQLite: length(TEXT) và octet_length()

SQLite có hàm **length(X)**:

~~~sql
SELECT
    length('Café') AS so_ky_tu;
~~~

Với chuỗi Unicode được lưu như TEXT, length() thông thường trả **4** cho cách biểu diễn ghép sẵn.

Các phiên bản SQLite hiện đại (từ **3.43.0**) có hàm **octet_length()**:

~~~sql
SELECT
    length('Café') AS so_ky_tu,
    octet_length('Café') AS so_byte;
~~~

Trong cơ sở dữ liệu mã hóa UTF-8 và chuỗi ví dụ, kết quả kỳ vọng là **4** và **5**.

Nếu cần đo byte trên SQLite cũ hơn hoặc đo dữ liệu binary, có thể dùng phép chuyển sang BLOB phù hợp và **length()**:

~~~sql
SELECT length(CAST('Café' AS BLOB)) AS so_byte;
~~~

Tuy nhiên, số byte khi CAST sang BLOB phụ thuộc biểu diễn/encoding đang dùng. SQLite có thể lưu dữ liệu văn bản ở UTF-8 hoặc UTF-16 và có cách xử lý động theo kiểu giá trị. Khi dữ liệu cần đúng số byte UTF-8 gửi qua mạng, nên mã hóa UTF-8 có chủ đích ở tầng ứng dụng hoặc xác định rõ biểu diễn trong truy vấn.

Một trường hợp khác thường bị bỏ sót: với TEXT chứa **ký tự NUL U+0000**, hàm length(X) của SQLite có thể chỉ đếm tới ký tự NUL đầu tiên. Vì vậy, không dùng length(TEXT) như bằng chứng tuyệt đối về số code point thực nếu dữ liệu có thể chứa ký tự NUL nhúng.

## 11. Cách diễn giải độ dài của VARCHAR(n) và NVARCHAR(n)

Cú pháp định nghĩa cột như:

~~~sql
CREATE TABLE khach_hang (
    ma_khach_hang INTEGER PRIMARY KEY,
    ten VARCHAR(100)
);
~~~

nhìn rất quen thuộc nhưng **100 không có cùng ý nghĩa ở mọi hệ**.

| Hệ/kiểu | Điều cần hiểu |
|---|---|
| PostgreSQL VARCHAR(n) | Thường giới hạn theo số ký tự của chuỗi, không đơn giản là n byte UTF-8 |
| MySQL VARCHAR(n) | n biểu diễn số ký tự theo charset của cột; dung lượng byte tối đa còn phụ thuộc charset và giới hạn hàng |
| SQL Server VARCHAR(n) | n là số byte trong định nghĩa kiểu; với UTF-8 có thể chứa ít hơn n ký tự Unicode nếu nhiều byte/ký tự |
| SQL Server NVARCHAR(n) | n là số **cặp byte** (đơn vị mã UTF-16); một ký tự supplementary có thể cần hai đơn vị |
| Oracle VARCHAR2(n BYTE/CHAR) | Phân biệt rõ ngữ nghĩa độ dài theo byte hoặc ký tự tùy cú pháp và thiết lập |
| SQLite VARCHAR(n) | SQLite thường **không tự thực thi giới hạn n ký tự** chỉ vì khai báo VARCHAR(n) theo mô hình kiểu linh hoạt của nó |

Vì vậy, kiểm tra độ dài khi người dùng nhập dữ liệu nên bắt đầu từ một câu hỏi chính xác:

- Yêu cầu **tối đa 100 ký tự người dùng nhìn thấy**?
- Tối đa **100 code point Unicode**?
- Tối đa **100 đơn vị mã UTF-16**?
- Tối đa **100 byte UTF-8**?
- Hay chỉ cần dữ liệu **không vượt kích thước cột của DBMS cụ thể**?

Nếu chưa xác định đúng đơn vị, việc sử dụng LENGTH hoặc CHAR_LENGTH có thể cho kết luận sai.

### 11.1. Không thay thế ràng buộc bằng bộ lọc hiển thị

~~~sql
SELECT ma_khach_hang, ten
FROM khach_hang
WHERE CHAR_LENGTH(ten) <= 100;
~~~

Truy vấn trên chỉ **lọc hàng** đã lưu, không ngăn dữ liệu quá dài vào bảng. Nếu muốn thực thi giới hạn, có thể cần:

- Kiểu cột có giới hạn phù hợp.
- **NOT NULL**, **CHECK** hoặc validation tại tầng ứng dụng.
- Chuẩn hóa Unicode và quy tắc tính độ dài được định nghĩa nhất quán.
- Kiểm thử trên đúng DBMS và kiểu cột.

Ví dụ, một ràng buộc kiểm tra biểu thức độ dài trên hệ hỗ trợ:

~~~sql
CREATE TABLE mo_ta_ngan (
    ma INTEGER PRIMARY KEY,
    noi_dung VARCHAR(200) NOT NULL,
    CONSTRAINT ck_do_dai
        CHECK (CHAR_LENGTH(noi_dung) <= 100)
);
~~~

Cần điều chỉnh cú pháp theo DBMS. CHECK chỉ có hiệu lực nếu DBMS thực sự thực thi ràng buộc đó; các hệ khác nhau còn có quy tắc xử lý NULL, chuỗi rỗng và CHAR_LENGTH.

## 12. NULL, chuỗi rỗng và khoảng trắng: ba bài kiểm thử không thể thiếu

### 12.1. UPPER/LOWER(NULL) và LENGTH(NULL)

Với các hàm chuỗi nêu trong bài, kết quả từ đầu vào NULL thường là NULL:

~~~sql
SELECT
    UPPER(NULL) AS gia_tri_hoa,
    LOWER(NULL) AS gia_tri_thuong,
    CHAR_LENGTH(NULL) AS so_ky_tu;
~~~

Trong những DBMS hỗ trợ cú pháp ví dụ, cả ba biểu thức cho NULL theo ngữ nghĩa thông thường. **NULL không có độ dài 0**, vì không tồn tại giá trị để đo.

Nếu muốn hiển thị “chưa nhập”:

~~~sql
SELECT
    ma_nguoi_dung,
    COALESCE(ten_hien_thi, 'CHUA_NHAP') AS ten_hien_thi
FROM nguoi_dung;
~~~

**COALESCE** thay giá trị NULL cho mục đích biểu thức; nó không khiến NULL và chuỗi rỗng trở thành cùng một thứ theo mô hình dữ liệu.

### 12.2. Chuỗi rỗng

Ở PostgreSQL, MySQL và SQLite, với giá trị văn bản rỗng thông thường:

~~~sql
SELECT CHAR_LENGTH('') AS so_ky_tu;
~~~

Kết quả kỳ vọng là **0** đối với những DBMS hỗ trợ CHAR_LENGTH. Nhưng ở Oracle truyền thống, chuỗi rỗng có thể được xem là NULL. Với SQL Server, dùng LEN('') cho kết quả **0** trong trường hợp thông thường.

Khi cần phát hiện **cả NULL và rỗng**, điều kiện có thể là:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE ten_hien_thi IS NULL
   OR ten_hien_thi = '';
~~~

Kết quả chính xác của vế **= ''** trên các DBMS chịu ảnh hưởng bởi ngữ nghĩa chuỗi rỗng; luôn kiểm tra trên môi trường mục tiêu. Nếu yêu cầu chỉ phát hiện NULL, dùng **IS NULL**, không dùng phép so sánh bằng.

### 12.3. Khoảng trắng cuối chuỗi

Chuỗi **'AB '** chứa ba ký tự nếu tính cả dấu cách cuối. Các hàm khác nhau có thể cho kết quả khác nhau:

| Trường hợp | Kết quả điển hình |
|---|---|
| PostgreSQL CHAR_LENGTH('AB ') với TEXT/VARCHAR | 3 |
| MySQL CHAR_LENGTH('AB ') | 3 |
| MySQL LENGTH('AB ') với ASCII/UTF-8 | 3 byte |
| SQL Server LEN('AB ') | 2 |
| SQL Server DATALENGTH('AB ') với VARCHAR ASCII thông thường | 3 byte |
| Oracle LENGTH('AB ') với dữ liệu VARCHAR2 phù hợp | 3 |
| SQLite length('AB ') với TEXT | 3 |

Đây là lý do **LEN** ở SQL Server không phải một thay thế hoàn toàn tương đương của CHAR_LENGTH trong mọi truy vấn cần tính cả trailing spaces.

Nếu mục tiêu là tìm những dòng có dữ liệu chỉ gồm dấu cách, có thể dùng TRIM:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE TRIM(ten_hien_thi) = '';
~~~

Tuy nhiên, TRIM thường xử lý một tập ký tự trắng cụ thể và có thể không loại bỏ mọi ký tự Unicode trông giống khoảng trắng. Với Oracle, kết quả chuỗi rỗng cũng cần xét thêm. Một yêu cầu “chỉ có whitespace” phải xác định những ký tự nào được coi là whitespace.

### 12.4. Hàm TRIM rồi đo độ dài

~~~sql
SELECT
    ma_nguoi_dung,
    ten_hien_thi,
    CHAR_LENGTH(ten_hien_thi) AS do_dai_goc,
    CHAR_LENGTH(TRIM(ten_hien_thi)) AS do_dai_sau_trim
FROM nguoi_dung;
~~~

Với **'AB '** trong DBMS mà CHAR_LENGTH đếm dấu cách cuối, **do_dai_goc = 3**, **do_dai_sau_trim = 2**.

Hai con số phục vụ hai yêu cầu khác nhau:

- **Độ dài gốc:** số ký tự thực có trong giá trị.
- **Độ dài sau trim:** độ dài của biểu thức đã chủ động loại một số dấu cách biên.

Không nên dùng TRIM ngầm nếu khoảng trắng đầu/cuối có ý nghĩa nghiệp vụ, chẳng hạn trong mật khẩu hoặc các giá trị cần so khớp chính xác.

## 13. Unicode chuẩn hóa: “trông giống nhau” không bảo đảm cùng độ dài

Hai chuỗi sau có thể trông như nhau khi hiển thị:

- **Café**: ký tự **é** ghép sẵn.
- **Café**: ký tự **e** + dấu sắc kết hợp.

Trong UTF-8:

| Dạng | Code point | Byte |
|---|---:|---:|
| C + a + f + é | 4 | 5 |
| C + a + f + e + U+0301 | 5 | 6 |

Sự khác biệt gây ảnh hưởng trực tiếp:

1. **CHAR_LENGTH** có thể trả 4 với dạng ghép sẵn nhưng 5 với dạng kết hợp.
2. **OCTET_LENGTH** ở UTF-8 trả 5 so với 6.
3. Một điều kiện bằng hoặc UNIQUE có thể xử lý hai dạng khác nhau tùy collation và normalization.
4. UPPER/LOWER có thể biến đổi các code point theo quy tắc khác nhau.
5. Nếu ứng dụng kiểm tra độ dài ở Java còn DBMS ở SQL, hai bên có thể áp dụng đơn vị đếm khác nhau.

### 13.1. NFC và NFD là gì?

Unicode có các dạng chuẩn hóa, trong đó:

- **NFC:** thường ưu tiên dạng tổ hợp/ghép sẵn khi có thể.
- **NFD:** thường tách ký tự thành phần cơ sở và dấu kết hợp theo phân rã chuẩn.

Ví dụ, một biểu diễn có dấu kết hợp có thể được chuyển thành dạng ghép sẵn theo NFC trong những trường hợp tương ứng. Kết quả chuẩn hóa ảnh hưởng số code point và số byte mà không nhất thiết thay đổi cách người dùng nhìn chuỗi.

SQL chuẩn không cung cấp một hàm chuẩn hóa Unicode phổ quát được triển khai giống nhau trên mọi DBMS. Nếu ứng dụng cần lưu chuỗi ở một dạng Unicode thống nhất, hãy xác định nơi thực hiện normalization và kiểm thử với đúng công cụ, driver, charset và collation.

### 13.2. Không nhầm chuyển chữ với bỏ dấu

~~~sql
SELECT LOWER('Café') AS ket_qua;
~~~

Kết quả thông thường là **café**, vẫn giữ dấu. LOWER không phải hàm “bỏ dấu tiếng Việt”.

Ví dụ về hai yêu cầu khác nhau:

- **Không phân biệt chữ hoa:** 'Café' và 'CAFÉ' cần được coi tương đương.
- **Không phân biệt dấu:** 'Café' và 'Cafe' cần được coi tương đương.

Một hệ có thể hỗ trợ yêu cầu đầu nhưng không mặc định hỗ trợ yêu cầu sau. Cần chọn collation hoặc cơ chế chuẩn hóa/tìm kiếm riêng theo nghiệp vụ.

## 14. Emoji, ký tự kết hợp và giới hạn giao diện

Xét các chuỗi sau:

| Giá trị hiển thị | Cấu trúc | Điểm cần thử |
|---|---|---|
| **😊** | Một code point ngoài BMP | UTF-8 4 byte, UTF-16 hai đơn vị mã |
| **é** | e + dấu sắc kết hợp | Hai code point nhưng thường một grapheme hiển thị |
| Một emoji gia đình ghép bằng ZWJ | Nhiều code point | Một biểu tượng hiển thị có thể dài nhiều byte |
| Cờ quốc gia dưới dạng hai regional indicator | Hai code point | Có thể hiển thị một lá cờ |
| Ký tự có variation selector | Ký tự cơ sở + dấu biến thể | Hình dạng hiển thị khác nhưng số code point nhiều hơn một |

Nếu yêu cầu “tối đa 10 ký tự **người dùng nhìn thấy**”, cần áp dụng **phân đoạn grapheme** bằng công cụ được thiết kế cho Unicode, thay vì mặc định dùng:

~~~sql
WHERE CHAR_LENGTH(ten_hien_thi) <= 10
~~~

Câu SQL trên chỉ đo một đại lượng theo định nghĩa của DBMS. Nó có thể đủ cho một quy tắc “tối đa 10 ký tự theo DBMS”, nhưng không chứng minh đúng quy tắc “10 grapheme hiển thị” ở mọi ngôn ngữ.

Cũng không nên coi số byte UTF-8 là thước đo độ rộng hiển thị. Cùng một ký tự có thể chiếm 1 hoặc 2 ô trong terminal, khác kích thước trong phông chữ hoặc hiển thị thành một cụm emoji. Độ dài lưu trữ và chiều rộng hiển thị là hai bài toán riêng.

## 15. Kiểm tra độ dài trong WHERE

Giả sử nghiệp vụ quy định:

- Tên hiển thị **không được rỗng**.
- Tên hiển thị có tối đa **30 ký tự** theo phép đếm được chấp nhận của DBMS.
- Giá trị NULL không được coi là tên hợp lệ.

Truy vấn tìm dòng cần kiểm tra:

~~~sql
SELECT
    ma_nguoi_dung,
    ten_hien_thi
FROM nguoi_dung
WHERE ten_hien_thi IS NULL
   OR CHAR_LENGTH(TRIM(ten_hien_thi)) = 0
   OR CHAR_LENGTH(ten_hien_thi) > 30;
~~~

Trong môi trường phân biệt chuỗi rỗng với NULL, điều kiện có thể phát hiện NULL, rỗng/chỉ khoảng trắng và quá dài. Với Oracle, cách kiểm tra sau TRIM cần điều chỉnh theo ngữ nghĩa chuỗi rỗng như NULL. Nếu có whitespace Unicode đặc biệt, TRIM mặc định có thể không phát hiện hết.

**Không nên tự khẳng định truy vấn này là validation cuối cùng cho mọi đầu vào.** Nếu hệ thống cần giới hạn grapheme hoặc bộ ký tự được phép, cần thêm logic theo yêu cầu nghiệp vụ.

### 15.1. Tách điều kiện của dữ liệu thiếu và dữ liệu quá dài

Để không làm mất thông tin phân loại, có thể dùng CASE:

~~~sql
SELECT
    ma_nguoi_dung,
    ten_hien_thi,
    CASE
        WHEN ten_hien_thi IS NULL THEN 'THIEU'
        WHEN CHAR_LENGTH(TRIM(ten_hien_thi)) = 0 THEN 'RONG'
        WHEN CHAR_LENGTH(ten_hien_thi) > 30 THEN 'QUA_DAI'
        ELSE 'HOP_LE_THEO_DO_DAI'
    END AS ket_qua
FROM nguoi_dung;
~~~

CASE nêu rõ lý do. Với một số DBMS, phép kiểm tra rỗng cần điều chỉnh; đồng thời “hợp lệ theo độ dài” không có nghĩa đã hợp lệ theo mọi quy tắc tên.

### 15.2. Kiểm tra giới hạn byte

Giả sử một dịch vụ tích hợp chỉ nhận chuỗi có tối đa **64 byte UTF-8**. Trong PostgreSQL đang dùng database UTF-8:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE OCTET_LENGTH(ten_hien_thi) > 64;
~~~

Trong MySQL với cột dùng utf8mb4:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE LENGTH(ten_hien_thi) > 64;
~~~

Trong SQL Server, **DATALENGTH** đo byte theo kiểu và mã hóa đang dùng:

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE DATALENGTH(ten_hien_thi) > 64;
~~~

Nhưng nếu **ten_hien_thi** là NVARCHAR, DATALENGTH thường đo byte UTF-16, **không** phải byte UTF-8 gửi qua mạng. Nếu giới hạn thật là UTF-8, hãy đo số byte sau khi **mã hóa UTF-8** ở tầng ứng dụng hoặc theo một phép chuyển mã được DBMS hỗ trợ và đã kiểm chứng.

### 15.3. Khi nào điều kiện đo chiều dài ảnh hưởng hiệu năng?

~~~sql
SELECT ma_nguoi_dung
FROM nguoi_dung
WHERE CHAR_LENGTH(ten_hien_thi) > 30;
~~~

Biểu thức gọi hàm trên cột có thể khiến DBMS khó sử dụng một chỉ mục B-tree thông thường theo giá trị cột để tìm ngay những dòng phù hợp. Nếu cần lọc thường xuyên:

- Cân nhắc cột tính toán/generate hoặc **expression index / functional index** nếu DBMS hỗ trợ.
- Cân nhắc lưu/kiểm tra độ dài có chủ đích tại thời điểm ghi nếu dữ liệu rất lớn và nghiệp vụ cần.
- Không tạo chỉ mục chỉ dựa trên suy đoán; xem kế hoạch thực thi, mức chọn lọc, tần suất truy vấn và chi phí cập nhật.
- Giữ phép đo đồng nhất với quy tắc nghiệp vụ và bộ mã ký tự.

## 16. Hàm trên cột và hiệu năng tìm kiếm không phân biệt chữ hoa

Xét truy vấn:

~~~sql
SELECT ma_nguoi_dung, email
FROM nguoi_dung
WHERE LOWER(email) = LOWER(?);
~~~

Nếu có chỉ mục thông thường trên **email**, việc bọc cột trong **LOWER(email)** có thể làm điều kiện khó tận dụng trực tiếp chỉ mục đó, tùy bộ tối ưu và kiểu chỉ mục.

Các hướng thiết kế thường gặp:

1. **Collation không phân biệt chữ hoa/thường** cho cột hoặc phép so sánh khi yêu cầu cho phép.
2. **Expression index/functional index** trên LOWER(email) nếu DBMS hỗ trợ.
3. **Computed/generated column** chứa một khóa tìm kiếm chuẩn hóa, kèm chỉ mục và quy tắc đồng bộ.
4. **Chuẩn hóa tại thời điểm ghi** khi nghiệp vụ xác định một dạng lưu duy nhất, đồng thời giữ giá trị gốc nếu cần hiển thị.
5. Một kiểu dữ liệu hoặc tính năng chuyên biệt cho so sánh không phân biệt chữ hoa trong sản phẩm cụ thể.

Ví dụ khái niệm chỉ mục biểu thức trong PostgreSQL:

~~~sql
CREATE INDEX idx_nguoi_dung_email_lower
ON nguoi_dung (LOWER(email));
~~~

Sau đó, truy vấn WHERE LOWER(email) = LOWER(?) có thể hưởng lợi từ chỉ mục phù hợp, nhưng việc bộ tối ưu có dùng nó còn phụ thuộc số lượng dòng, thống kê và kế hoạch thực thi.

Trong MySQL, SQL Server, Oracle và SQLite, cú pháp/khả năng hỗ trợ các chỉ mục trên biểu thức hoặc cột tính toán khác nhau. Kiểm tra theo **phiên bản và phương ngữ** trước khi sử dụng.

### 16.1. Chuẩn hóa ở tầng ứng dụng không thay thế ràng buộc duy nhất

Nếu muốn **email không trùng khi viết khác chữ hoa**, cần quy tắc dữ liệu và ràng buộc ở cơ sở dữ liệu phù hợp. Chỉ viết:

~~~sql
SELECT ma_nguoi_dung
FROM nguoi_dung
WHERE LOWER(email) = LOWER(?);
~~~

để kiểm tra “đã tồn tại chưa” rồi mới INSERT có thể gặp điều kiện chạy đua khi nhiều yêu cầu đồng thời. Bảo đảm dữ liệu duy nhất cần cơ chế **UNIQUE/index** có cùng ngữ nghĩa chuẩn hóa, giao dịch và xử lý xung đột phù hợp DBMS. Đồng thời, cần hiểu chính sách nhận dạng email của sản phẩm trước khi khẳng định mọi email chỉ khác hoa/thường phải được gộp.

## 17. Kiểm thử các trường hợp biên về độ dài

Khi đặt giới hạn, nên chuẩn bị dữ liệu nằm **ngay dưới**, **bằng** và **ngay trên** ngưỡng.

Ví dụ, giới hạn **10 ký tự** theo CHAR_LENGTH:

| Tình huống | Ví dụ | Mong đợi |
|---|---|---|
| 9 ký tự | 'ABCDEFGHI' | Hợp lệ |
| 10 ký tự | 'ABCDEFGHIJ' | Hợp lệ |
| 11 ký tự | 'ABCDEFGHIJK' | Không hợp lệ |
| 10 ký tự chứa dấu tiếng Việt | Chuỗi có 10 code point | Kiểm tra đúng theo DBMS |
| Emoji | Số code point khác đơn vị UTF-16 | Xác định đơn vị đếm |
| Chuỗi rỗng | '' | Tùy quy tắc rỗng |
| NULL | NULL | Tùy quy tắc bắt buộc nhập |
| Khoảng trắng cuối | 'ABC ' | Xác định có tính dấu cách hay TRIM |

Với giới hạn **10 byte UTF-8**, cần bộ dữ liệu khác:

| Chuỗi | Số code point | Số byte UTF-8 | Qua giới hạn 10 byte? |
|---|---:|---:|---|
| 'ABCDEFGHIJ' | 10 | 10 | Không |
| 'ABCDEFGHIJK' | 11 | 11 | Có |
| '😊😊' | 2 | 8 | Không |
| '😊😊😊' | 3 | 12 | Có |
| 'Café' | 4 | 5 | Không |
| 'Hà Nội' | 6 | 9 | Không |

Bộ thử cần làm rõ mục tiêu: một trường hợp có ít code point nhưng nhiều byte sẽ phát hiện lỗi dùng **CHAR_LENGTH** khi nghiệp vụ cần **giới hạn byte**; một trường hợp nhiều dấu kết hợp sẽ phát hiện sự khác biệt giữa code point và grapheme.

### 17.1. Một bài kiểm thử dành riêng cho trailing spaces

Dùng đúng giá trị **'AB '**:

- Nếu kiểm tra chiều dài **bao gồm dấu cách cuối**, kết quả mong đợi là 3.
- Nếu dùng **LEN** của SQL Server, kết quả thường là 2.
- Nếu chủ động TRIM rồi đo, kết quả có thể là 2.
- Nếu dùng kiểu CHAR cố định, quy tắc khoảng trắng đệm có thể làm kết quả khác.

Câu hỏi cần chốt trước: có tính **khoảng trắng cuối dữ liệu gốc** vào giới hạn hay không?

### 17.2. Một bài kiểm thử dành riêng cho Unicode normalization

Tạo hai giá trị:

- Một giá trị chứa **é ghép sẵn**.
- Một giá trị chứa **e + U+0301**.

Sau đó kiểm tra:

- Chúng có được lưu thành cùng chuỗi khi không chủ động chuẩn hóa không?
- Hàm đếm ký tự trên DBMS trả bao nhiêu?
- Hàm đo byte trả bao nhiêu?
- UPPER/LOWER có làm chúng tương đương trong phép bằng không?
- Nếu tạo UNIQUE, DBMS/collation có xem chúng trùng nhau không?

Kết quả kiểm thử phải được gắn với **DBMS, phiên bản, charset và collation**. Không nên mặc định hai dãy Unicode giống nhau chỉ vì khi hiển thị mắt thường khó phân biệt.

## 18. Hàm độ dài cho BLOB và dữ liệu nhị phân

Một cột **BLOB/BINARY/VARBINARY** chứa dữ liệu nhị phân, không nhất thiết đại diện cho văn bản. Khi cần đo độ dài một tệp ảnh hoặc gói dữ liệu:

- Nên đo **số byte** của dữ liệu nhị phân.
- Không dùng UPPER/LOWER trên dữ liệu nhị phân như thể đó là văn bản.
- Không diễn giải số byte BLOB thành số ký tự nếu chưa giải mã bằng một charset cụ thể.

Ví dụ, ở những DBMS có hàm DATALENGTH hoặc OCTET_LENGTH phù hợp với kiểu nhị phân, ta có thể lấy số byte của giá trị.

Tuy nhiên, **cùng tên LENGTH** có thể có hành vi khác theo kiểu đầu vào:

- Trong SQLite, **length(BLOB)** đếm byte, còn **length(TEXT)** đếm ký tự theo quy tắc của SQLite.
- Trong MySQL, **LENGTH(string)** đếm byte của chuỗi biểu diễn theo bộ ký tự.
- Trong SQL Server, **DATALENGTH(varbinary_col)** trả byte dữ liệu nhị phân.

Vì vậy, trước khi so sánh số đo, phải biết cột chứa **TEXT** hay **BLOB** và hàm đang được áp dụng lên kiểu nào.

## 19. Chuyển đổi qua lại giữa chuỗi và byte trong Java/JDBC

Khi ứng dụng Java làm việc với SQL, cần nhớ **Java String.length()** không giống **độ dài byte UTF-8** và cũng không luôn giống số ký tự theo SQL.

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;

public class DoDaiChuoi {
    public static void main(String[] args) {
        String s1 = "Café";
        String s2 = "😊";

        System.out.println(s1.length()); // 4 đơn vị UTF-16
        System.out.println(s1.codePointCount(0, s1.length())); // 4 code point
        System.out.println(s1.getBytes(StandardCharsets.UTF_8).length); // 5 byte

        System.out.println(s2.length()); // 2 đơn vị UTF-16
        System.out.println(s2.codePointCount(0, s2.length())); // 1 code point
        System.out.println(s2.getBytes(StandardCharsets.UTF_8).length); // 4 byte
    }
}
~~~

Đây là ba phép đo khác nhau:

| Java | Trả về |
|---|---|
| **s.length()** | Số đơn vị mã UTF-16 |
| **s.codePointCount(0, s.length())** | Số Unicode code point trong đoạn chuỗi |
| **s.getBytes(UTF_8).length** | Số byte khi mã hóa UTF-8 |

**Không tự suy luận codePointCount là số ký tự người dùng nhìn thấy.** Một grapheme có thể gồm nhiều code point.

### 19.1. Chuẩn hóa Unicode với Java

Nếu yêu cầu lưu dạng Unicode NFC, Java có API chuẩn:

~~~java
import java.text.Normalizer;

String input = "Cafe\u0301";
String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
~~~

Trong ví dụ, **input** gồm e + dấu sắc kết hợp, còn **normalized** có thể dùng é ghép sẵn. Việc chuẩn hóa nên là một quyết định của kiến trúc ứng dụng, áp dụng thống nhất ở mọi đường ghi và trước kiểm tra giới hạn đã chọn.

### 19.2. Đổi chữ hoa/thường bằng Java khác đổi trong SQL

Trong Java:

~~~java
import java.util.Locale;

String key = "ABC-123";
String lower = key.toLowerCase(Locale.ROOT);
String upper = key.toUpperCase(Locale.ROOT);
~~~

**Locale.ROOT** thường phù hợp cho các mã/ký hiệu không gắn với ngôn ngữ tự nhiên cụ thể. Nếu xử lý tên người hoặc văn bản tiếng địa phương, phải chọn chính sách ngôn ngữ phù hợp.

Kết quả **toLowerCase/toUpperCase của Java** không được bảo đảm luôn giống **LOWER/UPPER của DBMS** cho mọi Unicode và mọi phiên bản. Nguyên nhân có thể là khác phiên bản Unicode, locale, collation hoặc thuật toán ánh xạ.

Nếu ứng dụng cần một khóa tìm kiếm ổn định qua nhiều môi trường, hãy xác định **một quy tắc chuẩn hóa chính thức** và kiểm thử end-to-end thay vì dựa vào suy đoán rằng tất cả tầng xử lý giống nhau.

### 19.3. Truyền giá trị bằng PreparedStatement

~~~java
String sql = """
    SELECT ma_nguoi_dung, email
    FROM nguoi_dung
    WHERE LOWER(email) = LOWER(?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "LINH@EXAMPLE.COM");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("ma_nguoi_dung"));
        }
    }
}
~~~

**PreparedStatement** truyền tham số dưới dạng giá trị, giảm nguy cơ SQL injection và vấn đề dấu nháy. Nó không tự giải quyết các khác biệt collation, độ dài ký tự hoặc Unicode normalization. Nếu tham số có NULL, cần xử lý ý định “không lọc” khác với “tìm giá trị NULL”.

## 20. Những tình huống ứng dụng thực tế

### 20.1. Chuẩn hóa mã sản phẩm khi hiển thị

Giả sử mã sản phẩm được lưu dưới dạng **'abc-001'** nhưng giao diện quy định hiển thị chữ hoa:

~~~sql
SELECT
    ma_san_pham,
    UPPER(ma_san_pham) AS ma_hien_thi,
    ten_san_pham
FROM san_pham;
~~~

Ưu điểm: không cần thay đổi mã gốc trong bảng. Tuy nhiên, nếu mã sản phẩm là khóa tích hợp có phân biệt chữ hoa, việc hiển thị sau UPPER có thể khiến người dùng hiểu nhầm hai mã khác nhau thành một. Nên xác định bộ ký tự hợp lệ và tính phân biệt của mã từ đầu.

### 20.2. Tìm các tên dài trên giao diện

Giả sử giao diện dành chỗ cho tên dài không quá 30 ký tự theo quy tắc DBMS:

~~~sql
SELECT
    ma_nguoi_dung,
    ten_hien_thi,
    CHAR_LENGTH(ten_hien_thi) AS do_dai
FROM nguoi_dung
WHERE CHAR_LENGTH(ten_hien_thi) > 30;
~~~

Danh sách giúp người quản trị nhận diện dữ liệu có thể cần rút gọn. Nhưng **chiều rộng thực tế trên màn hình** còn phụ thuộc font, ký tự có độ rộng khác nhau, emoji và cách xuống dòng. Một chuỗi 30 chữ “W” có thể dài hơn 30 chữ “i” khi hiển thị.

### 20.3. Kiểm tra dữ liệu vượt byte cho một API

Giả sử một hệ thống chỉ chấp nhận tên file với **tối đa 255 byte UTF-8**. Ở tầng Java:

~~~java
import java.nio.charset.StandardCharsets;

boolean valid = fileName.getBytes(StandardCharsets.UTF_8).length <= 255;
~~~

Ở tầng SQL, nếu cột lưu đúng UTF-8 và hàm OCTET_LENGTH đo byte tương ứng, có thể viết:

~~~sql
SELECT ma_tai_lieu, ten_file
FROM tai_lieu
WHERE OCTET_LENGTH(ten_file) > 255;
~~~

Nhưng nếu DBMS lưu UTF-16 hoặc charset khác, phải chuyển mã/đo ở đúng tầng; DATALENGTH trên NVARCHAR không trực tiếp biểu diễn số byte UTF-8 mà API sẽ nhận.

Ngoài số byte, tên file còn chịu giới hạn ký tự cấm, tên dành riêng, quy tắc đường dẫn và Unicode normalization của hệ thống đích. Đo độ dài byte chỉ là một phần của validation.

### 20.4. Lọc dữ liệu bất thường trước khi di chuyển hệ quản trị

Nếu đang chuyển từ PostgreSQL sang MySQL, truy vấn cũ:

~~~sql
SELECT ma_nguoi_dung
FROM nguoi_dung
WHERE LENGTH(ten_hien_thi) > 50;
~~~

trên PostgreSQL với text thường kiểm tra độ dài ký tự. Nếu mang nguyên truy vấn sang MySQL, **LENGTH** chuyển thành phép đo byte. Một tên có 40 ký tự tiếng Việt nhưng 65 byte UTF-8 có thể bị chọn ở MySQL trong khi không bị chọn ở PostgreSQL.

Để giữ ý nghĩa “hơn 50 ký tự” ở MySQL, dùng:

~~~sql
SELECT ma_nguoi_dung
FROM nguoi_dung
WHERE CHAR_LENGTH(ten_hien_thi) > 50;
~~~

Đây là một ví dụ điển hình của lỗi **chuyển hệ mà cú pháp vẫn hợp lệ nhưng ý nghĩa thay đổi**. Một bộ dữ liệu chỉ gồm ASCII không phát hiện được vấn đề vì ở UTF-8, số ký tự ASCII thường trùng số byte.

### 20.5. Tìm chuỗi chưa có nội dung hữu ích

Giả sử tên hiển thị có thể là NULL, rỗng hoặc chỉ có dấu cách:

~~~sql
SELECT
    ma_nguoi_dung,
    ten_hien_thi
FROM nguoi_dung
WHERE ten_hien_thi IS NULL
   OR CHAR_LENGTH(TRIM(ten_hien_thi)) = 0;
~~~

Đây là mẫu minh họa cho DBMS hỗ trợ CHAR_LENGTH và phân biệt chuỗi rỗng. Nếu dùng Oracle hoặc cần nhận diện Unicode whitespace ngoài dấu cách mặc định, hãy điều chỉnh điều kiện. Trong một hệ thống production, nên quy định rõ những ký tự nào được coi là “không có nội dung”.

## 21. Bảng kiểm thử: ký tự, byte, NULL và biến đổi chữ

Một bài kiểm thử tốt có **đầu vào xác định** và **đơn vị đo mong đợi**.

| Tình huống | Giá trị | Điều cần xác nhận |
|---|---|---|
| ASCII | 'ABC' | Số ký tự và số byte UTF-8 đều bằng 3 |
| Chữ có dấu ghép sẵn | 'Café' | 4 code point, 5 byte UTF-8 |
| Dấu kết hợp | 'Café' | 5 code point, 6 byte UTF-8 |
| Emoji | '😊' | 1 code point, 4 byte UTF-8, 2 đơn vị UTF-16 |
| Dấu cách cuối | 'AB ' | LEN(SQL Server) và CHAR_LENGTH có thể khác |
| Rỗng | '' | 0 ở nhiều DBMS; Oracle có ngữ nghĩa rỗng đặc biệt |
| Thiếu dữ liệu | NULL | Hàm chuỗi thường trả NULL |
| Chữ hoa | 'LINH' | LOWER trả 'linh' theo Latin thông thường |
| Chữ thường | 'linh' | UPPER trả 'LINH' theo Latin thông thường |
| Dấu tiếng Việt | 'Hà Nội' | Phải kiểm tra charset/collation đúng |
| NUL nhúng | TEXT chứa U+0000 | SQLite length(TEXT) có giới hạn đếm riêng |
| Tên rất dài | 100, 101 ký tự | Phân biệt >=, > và giới hạn đầu vào |

Khi kiểm thử trên nhiều DBMS, cần lưu thêm:

- **Phiên bản DBMS**.
- **Encoding/charset** cơ sở dữ liệu và cột.
- **Collation** liên quan đến biểu thức.
- **Kiểu cột**: VARCHAR, CHAR, NVARCHAR, TEXT, BLOB...
- **Cách nạp chuỗi** qua driver; có dùng tiền tố Unicode hay tham số bind không.
- **Ngữ nghĩa kỳ vọng**: code point, grapheme, đơn vị UTF-16 hay byte ở mã hóa nào.

Không thể dùng duy nhất ảnh chụp kết quả hiển thị để chứng minh dãy Unicode giống nhau: chuỗi có dấu ghép sẵn và dấu kết hợp đôi khi được render giống hệt.

## 22. Các lỗi và ngộ nhận thường gặp

| Ngộ nhận hoặc lỗi | Vì sao sai hoặc dễ gây nhầm | Cách xử lý |
|---|---|---|
| “UPPER/LOWER sẽ bỏ dấu tiếng Việt.” | Chúng chủ yếu chuyển chữ hoa/thường | Tách yêu cầu phân biệt hoa/thường khỏi phân biệt dấu |
| “LOWER ở mọi DBMS tạo cùng một chuỗi.” | Unicode, locale, collation và phiên bản có thể khác | Xác định quy tắc chuẩn hóa và kiểm thử |
| “Gọi UPPER trong SELECT đã sửa dữ liệu.” | SELECT chỉ tính biểu thức đầu ra | Dùng quy tắc ghi dữ liệu nếu muốn lưu dạng chuẩn |
| “LENGTH luôn trả số ký tự.” | MySQL LENGTH đo byte, PostgreSQL LENGTH(text) thường đo ký tự | Chọn đúng hàm theo DBMS |
| “Một ký tự Unicode luôn bằng một byte.” | UTF-8 dùng 1–4 byte cho một code point | Đo OCTET_LENGTH/byte đúng encoding |
| “Java String.length() = số ký tự hiển thị.” | Java đếm đơn vị UTF-16, grapheme có thể gồm nhiều code point | Dùng phép đo phù hợp mục đích |
| “Một emoji luôn dài đúng một đơn vị trong mọi hệ.” | Có emoji ghép từ nhiều code point; UTF-16 có surrogate pairs | Xác định code point, grapheme và byte |
| “LEN('AB ') = 3 ở SQL Server.” | LEN thường bỏ qua khoảng trắng cuối | Dùng hàm phù hợp đơn vị và dấu cách cần tính |
| “Chuỗi rỗng luôn giống NULL.” | Nhiều DBMS phân biệt, Oracle có ngoại lệ | Thử riêng NULL và '' |
| “CHAR_LENGTH <= 50 chứng minh vừa cột 50 byte.” | Ký tự Unicode có thể cần nhiều byte | Kiểm tra số byte theo đúng encoding |
| “DATALENGTH(NVARCHAR) = số byte UTF-8.” | NVARCHAR của SQL Server thường mã hóa UTF-16 | Đo sau chuyển sang UTF-8 nếu đó là yêu cầu |
| “Hai chuỗi nhìn giống nhau chắc chắn có cùng length.” | Unicode có nhiều dạng biểu diễn | Kiểm tra NFC/NFD và dãy code point |
| “LOWER(x) = LOWER(?) luôn tận dụng index thường trên x.” | Hàm trên cột có thể cản index trực tiếp | Xem plan, collation, expression index |
| “UPPER(email) trước INSERT đủ ngăn email trùng.” | Có vấn đề ngữ nghĩa và điều kiện chạy đua | Dùng constraint/index theo quy tắc duy nhất |
| “Dữ liệu có dấu cách cuối không quan trọng.” | Ảnh hưởng độ dài, so sánh và giao thức tích hợp | Quy định giữ/trim và thử trường hợp biên |
| “DATALENGTH bằng dung lượng đĩa.” | Dung lượng hàng còn metadata/nén/index | Dùng công cụ thống kê lưu trữ |
| “Một ký tự nhìn thấy có chiều rộng hiển thị cố định.” | Font, grapheme, emoji và bố cục khác nhau | Đo theo giao diện nếu mục tiêu là layout |

## 23. Bài tập tự luyện

### Bài 1 — Chuyển chữ trong SELECT

Bảng **san_pham** có mã **'sp-a01'**. Viết câu SQL trả mã sản phẩm dưới dạng chữ hoa nhưng không sửa cột gốc.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_san_pham, UPPER(ma_san_pham) AS ma_hien_thi
FROM san_pham;
~~~

Với dữ liệu đã cho, ma_hien_thi thường là **SP-A01**. SELECT không thay đổi giá trị đang lưu.

</details>

### Bài 2 — Tìm dữ liệu không phân biệt kiểu chữ

Viết điều kiện để tìm dòng có ten_hien_thi bằng **LINH**, **Linh** hoặc **linh** theo quy tắc Latin thông thường.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE LOWER(ten_hien_thi) = LOWER(?);
~~~

Bind tham số **'linh'**. Kết quả vẫn cần được kiểm tra dưới collation/DBMS mục tiêu; nếu yêu cầu hệ thống có quy tắc chữ hoa/thường chuyên biệt, cân nhắc collation phù hợp.

</details>

### Bài 3 — Ký tự so với byte

Giả sử mã hóa UTF-8. Chuỗi **'Café'** dùng é ghép sẵn có bao nhiêu code point và bao nhiêu byte?

<details>
<summary>Gợi ý đáp án</summary>

**4 code point** và **5 byte UTF-8**. Ba chữ ASCII C, a, f dùng mỗi chữ một byte; é ghép sẵn dùng hai byte.

</details>

### Bài 4 — Hai dạng Unicode nhìn giống nhau

Chuỗi thứ nhất gồm **C + a + f + é**. Chuỗi thứ hai gồm **C + a + f + e + U+0301**. Độ dài ký tự và byte UTF-8 có giống nhau không?

<details>
<summary>Gợi ý đáp án</summary>

Không. Dạng thứ nhất có 4 code point, 5 byte UTF-8. Dạng thứ hai có 5 code point, 6 byte UTF-8. Chúng có thể trông gần như nhau khi hiển thị và có thể được chuyển về dạng chuẩn hóa chung theo quy tắc phù hợp.

</details>

### Bài 5 — Chuyển câu SQL từ PostgreSQL sang MySQL

Trong PostgreSQL, truy vấn:

~~~sql
SELECT ma_nguoi_dung
FROM nguoi_dung
WHERE LENGTH(ten_hien_thi) > 30;
~~~

nhằm tìm tên dài hơn 30 ký tự. Khi chuyển sang MySQL, nên đổi LENGTH thành hàm nào?

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_nguoi_dung
FROM nguoi_dung
WHERE CHAR_LENGTH(ten_hien_thi) > 30;
~~~

MySQL LENGTH thường đếm byte; CHAR_LENGTH đếm ký tự theo quy tắc của MySQL.

</details>

### Bài 6 — LEN và khoảng trắng cuối

Trong SQL Server, biểu thức **LEN('AB ')** và **DATALENGTH('AB ')** có cùng kết quả không, nếu literal dùng kiểu VARCHAR ASCII thông thường?

<details>
<summary>Gợi ý đáp án</summary>

Không. **LEN('AB ') thường trả 2** vì bỏ qua dấu cách cuối; **DATALENGTH('AB ') trả 3 byte**.

</details>

### Bài 7 — Emoji và Java String

Đối với Java String chứa **'😊'**, các giá trị sau là bao nhiêu?

- s.length()
- s.codePointCount(0, s.length())
- s.getBytes(StandardCharsets.UTF_8).length

<details>
<summary>Gợi ý đáp án</summary>

Lần lượt là **2**, **1**, **4**. Emoji này cần hai đơn vị UTF-16, là một Unicode code point và dùng bốn byte khi mã hóa UTF-8.

</details>

### Bài 8 — Ràng buộc byte của API

Một API giới hạn tên file ở 10 byte UTF-8. Trong hai chuỗi **'ABCDEFGHIJ'** và **'😊😊😊'**, chuỗi nào vượt giới hạn? Vì sao CHAR_LENGTH <= 10 chưa đủ?

<details>
<summary>Gợi ý đáp án</summary>

'ABCDEFGHIJ' có 10 byte UTF-8, không vượt. '😊😊😊' có 12 byte UTF-8, vượt dù chỉ gồm ba code point. CHAR_LENGTH đo ký tự chứ không trực tiếp đo byte UTF-8.

</details>

### Bài 9 — NULL

Nếu ten_hien_thi = NULL thì điều kiện nào tìm được dòng đó?

~~~sql
-- A
WHERE LOWER(ten_hien_thi) = ''

-- B
WHERE CHAR_LENGTH(ten_hien_thi) = 0

-- C
WHERE ten_hien_thi IS NULL
~~~

<details>
<summary>Gợi ý đáp án</summary>

**C**. LOWER(NULL) và CHAR_LENGTH(NULL) thường trả NULL; phép so sánh = với giá trị NULL cho UNKNOWN nên WHERE không chọn. Dùng IS NULL để tìm đúng trường hợp thiếu giá trị.

</details>

### Bài 10 — Kiểm tra chuỗi sau TRIM

Bảng có giá trị ten_hien_thi là **'  LINH  '**. Viết biểu thức lấy dạng chữ thường không có dấu cách đầu/cuối.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT LOWER(TRIM(ten_hien_thi)) AS ten_da_chuan_hoa
FROM nguoi_dung;
~~~

Kết quả thông thường là **'linh'**. Quy tắc TRIM mặc định không nhất thiết bao phủ mọi ký tự trắng Unicode.

</details>

### Bài 11 — Tìm bản ghi dài hơn 50 ký tự hoặc thiếu tên

Viết WHERE để tìm tên có độ dài lớn hơn 50 ký tự **hoặc** tên NULL trong DBMS hỗ trợ CHAR_LENGTH.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_nguoi_dung, ten_hien_thi
FROM nguoi_dung
WHERE CHAR_LENGTH(ten_hien_thi) > 50
   OR ten_hien_thi IS NULL;
~~~

Hai nhánh tách việc vượt giới hạn và việc thiếu dữ liệu.

</details>

### Bài 12 — Vì sao chức năng tìm kiếm có thể chậm?

Truy vấn có **WHERE LOWER(email) = LOWER(?)**; bảng có chỉ mục thường trên email nhưng nhiều triệu hàng. Hãy nêu hai hướng cải thiện có thể cân nhắc.

<details>
<summary>Gợi ý đáp án</summary>

Có thể dùng **collation không phân biệt hoa/thường** phù hợp nghiệp vụ, hoặc tạo **expression/functional index** trên LOWER(email) nếu DBMS hỗ trợ. Một hướng khác là computed/generated search key có chỉ mục. Phải kiểm tra execution plan và dữ liệu thật; không thể bảo đảm mọi phương án đều nhanh hơn.

</details>

### Bài 13 — Chuỗi rỗng trong Oracle

Vì sao không nên giả định **LENGTH('') = 0** nếu ứng dụng cần chạy trên Oracle Database?

<details>
<summary>Gợi ý đáp án</summary>

Oracle truyền thống xử lý chuỗi rỗng như NULL trong nhiều ngữ cảnh. Vì vậy LENGTH('') có thể trả NULL. Cần kiểm tra đúng sản phẩm, phiên bản và kiểu dữ liệu.

</details>

### Bài 14 — Phân biệt byte biểu diễn và byte trên đĩa

Một cột có OCTET_LENGTH = 100. Có thể kết luận bản ghi chứa cột ấy dùng chính xác 100 byte trên đĩa không?

<details>
<summary>Gợi ý đáp án</summary>

Không. OCTET_LENGTH đo byte của biểu diễn giá trị theo hàm/DBMS; dung lượng đĩa còn phụ thuộc metadata hàng, căn chỉnh, nén, lưu trữ ngoài trang, chỉ mục và nhiều yếu tố khác.

</details>

## 24. Quy trình lựa chọn hàm trong dự án thật

Khi nhận yêu cầu liên quan UPPER, LOWER hoặc đo độ dài, làm theo các bước:

### Bước 1 — Viết rõ mục đích

- Cần **hiển thị chữ hoa/thường** hay cần **so khớp không phân biệt hoa/thường**?
- Cần **giữ hay bỏ dấu**?
- Cần độ dài theo **code point**, **grapheme**, **UTF-16** hay **byte**?
- Nếu là byte, **byte theo mã hóa nào**?

### Bước 2 — Xác định kiểu cột và DBMS

Kiểm tra **VARCHAR, NVARCHAR, CHAR, TEXT hay BLOB**, cùng charset, collation, phiên bản và cấu hình. Không mang nguyên giả định từ MySQL sang PostgreSQL hoặc từ SQL Server sang Oracle.

### Bước 3 — Chọn hàm tương ứng

- UPPER/LOWER để chuyển chữ theo quy tắc DBMS.
- CHAR_LENGTH/CHARACTER_LENGTH hoặc hàm ký tự tương ứng để đếm ký tự.
- OCTET_LENGTH/LENGTHB/DATALENGTH hoặc hàm byte tương ứng khi cần byte.
- TRIM, COALESCE, CASE nếu nghiệp vụ cần xử lý khoảng trắng hoặc NULL.
- Công cụ Unicode ở tầng ứng dụng nếu cần normalization hoặc số grapheme hiển thị.

### Bước 4 — Thử với bộ dữ liệu có khả năng phát hiện sai

Ít nhất thử **ASCII, tiếng Việt có dấu, emoji, dạng Unicode kết hợp dấu, chuỗi rỗng, NULL, khoảng trắng đầu/cuối và giá trị ngay sát giới hạn**. Một bộ thử chỉ có ASCII không thể chứng minh đã dùng đúng phép đo byte/ký tự.

### Bước 5 — Kiểm tra tác động đến dữ liệu và hiệu năng

Dùng UPPER/LOWER trong SELECT chỉ biến đổi đầu ra; dùng trong WHERE có thể ảnh hưởng index. Nếu định tạo cột chuẩn hóa và UNIQUE, cần xem chính sách nghiệp vụ, quy tắc ghi và tính đồng thời. Khi kiểm tra dung lượng, phân biệt biểu diễn chuỗi với kích thước tệp cơ sở dữ liệu.

## 25. Ghi nhớ cuối bài

1. **UPPER** chuyển văn bản theo hướng chữ hoa, **LOWER** chuyển theo hướng chữ thường; chúng **không tự sửa dữ liệu đã lưu** khi dùng trong SELECT.
2. Chuyển hoa/thường **không đồng nghĩa bỏ dấu**, chuẩn hóa Unicode hoặc so khớp ngôn ngữ hoàn chỉnh. **Collation** và phiên bản DBMS có thể làm kết quả khác nhau.
3. **Số ký tự** và **số byte** là hai đại lượng khác nhau. Trong UTF-8, chữ ASCII thường dùng 1 byte, nhiều chữ có dấu dùng 2–3 byte, emoji có thể dùng 4 byte.
4. **Một ký tự người dùng nhìn thấy** có thể gồm nhiều Unicode code point; **Java String.length()** đếm đơn vị UTF-16, không phải số byte UTF-8 hay số grapheme.
5. **PostgreSQL LENGTH(text)** thường đếm ký tự; **MySQL LENGTH(text)** đếm byte; **SQL Server LEN** bỏ qua khoảng trắng cuối; **DATALENGTH** đo byte theo kiểu chuỗi; **Oracle LENGTHB** đo byte; **SQLite length(TEXT)** có quy tắc riêng.
6. **CHAR_LENGTH/CHARACTER_LENGTH** và **OCTET_LENGTH** giúp diễn đạt rõ ý định hơn khi DBMS hỗ trợ, nhưng vẫn phải xét kiểu cột, charset và đặc thù triển khai.
7. **NULL không có độ dài 0**. Hàm chuỗi với NULL thông thường trả NULL; dùng **IS NULL** nếu cần kiểm tra dữ liệu thiếu.
8. Giới hạn **VARCHAR(n)** không luôn cùng đơn vị đo trên các DBMS. Nếu yêu cầu là số byte của API, đo theo **mã hóa API sử dụng**, không chỉ dựa vào số ký tự hoặc giới hạn cột.
9. Hàm trong WHERE như **LOWER(email)** có thể ảnh hưởng chỉ mục; cân nhắc collation, expression index hoặc khóa tìm kiếm chuẩn hóa dựa trên nhu cầu thật.
10. Với dữ liệu quốc tế và tiếng Việt, hãy kiểm thử cả **dấu, Unicode normalization, emoji, chuỗi rỗng, dấu cách cuối** trước khi triển khai quy tắc độ dài hoặc tìm kiếm.

### Tài liệu tra cứu khi triển khai

Để xác minh tên hàm, hỗ trợ kiểu dữ liệu và hành vi trên phiên bản thực tế, đối chiếu tài liệu chính thức ở các mục **string functions**, **character sets**, **collation**, **Unicode**, **length semantics** và **index expressions**:

- **PostgreSQL Documentation:** *String Functions and Operators*, *Character Types*, *Collation Support*.
- **MySQL Reference Manual:** *String Functions and Operators*, *Character Sets and Collations*, *String Data Types*.
- **Microsoft Learn — Transact-SQL:** *UPPER*, *LOWER*, *LEN*, *DATALENGTH*, *Collation and Unicode Support*.
- **Oracle Database SQL Language Reference:** *UPPER*, *LOWER*, *LENGTH*, *LENGTHB*, *LENGTHC*, *LENGTH2*, *LENGTH4*, *Data Type Comparison Rules*.
- **SQLite Documentation:** *Core Functions*, *Datatypes In SQLite*, *The SQLite Expression Language*, *Collation*.

Trong một hệ thống thật, câu hỏi quan trọng nhất luôn là **“đang đo hoặc chuyển đổi đơn vị nào, theo quy tắc và bộ mã nào?”**. Trả lời câu hỏi ấy trước khi chọn hàm sẽ tránh phần lớn lỗi liên quan đến chữ hoa/thường và độ dài văn bản.
