# CHAR, VARCHAR2, NCHAR và NVARCHAR2 trong Oracle Database

## 1. Bốn kiểu dữ liệu ký tự giải quyết bài toán gì?

Ứng dụng Java có thể cần lưu mã trạng thái, tên khách hàng, số điện thoại, địa chỉ và nội dung đa ngôn ngữ. Trong Oracle Database, bốn kiểu dữ liệu thường gặp cho chuỗi có độ dài được giới hạn là **`CHAR`**, **`VARCHAR2`**, **`NCHAR`** và **`NVARCHAR2`**. Chúng khác nhau theo hai trục:

1. **Độ dài cố định hay thay đổi**: có tự đệm thêm dấu cách tới chiều dài khai báo hay chỉ lưu độ dài thực tế của giá trị?
2. **Bộ ký tự sử dụng**: lưu bằng *database character set* hay *national character set* của Oracle?

| Kiểu dữ liệu | Độ dài | Bộ ký tự dùng lưu trữ | Phù hợp khi |
|---|---|---|---|
| `CHAR(n [BYTE\|CHAR])` | **Cố định**; đệm dấu cách khi giá trị ngắn hơn độ dài khai báo | Database character set | Mã thực sự có chiều dài cố định; cần hiểu rõ tác động của padding |
| `VARCHAR2(n [BYTE\|CHAR])` | **Biến thiên**; không đệm tới chiều dài tối đa khai báo | Database character set | Tên, mô tả ngắn, mã, email và đa số dữ liệu chuỗi ứng dụng |
| `NCHAR(n)` | **Cố định**, đệm dấu cách | National character set | Trường hợp thực sự cần chuỗi quốc gia cố định theo cách thiết kế hiện có |
| `NVARCHAR2(n)` | **Biến thiên** | National character set | Trường hợp yêu cầu lưu ở national character set riêng của database |

Ví dụ ý nghĩa:

```text
Lưu chuỗi "AB":

CHAR(5 CHAR)       -> giá trị dạng "AB   " (đệm 3 dấu cách)
VARCHAR2(5 CHAR)   -> giá trị "AB"      (không đệm)
NCHAR(5)           -> giá trị dạng "AB   " (ở national character set)
NVARCHAR2(5)       -> giá trị "AB"      (ở national character set)
```

Với `CHAR` và `NCHAR`, phần đệm có thể ảnh hưởng tới `LENGTH`, so sánh, nối chuỗi và cách ứng dụng nhận dữ liệu. Với `VARCHAR2` và `NVARCHAR2`, độ dài khai báo là **giới hạn**, không có nghĩa Oracle luôn chứa đủ số ký tự đó.

Trong môi trường dùng **`AL32UTF8` làm database character set**, `VARCHAR2` đã hỗ trợ tiếng Việt và các ký tự Unicode phù hợp. Không cần tự động chọn `NVARCHAR2` chỉ vì ứng dụng có dữ liệu tiếng Việt.

## 2. Hai trục phải nhớ: fixed/variable và database/national character set

Sơ đồ khái niệm:

```text
                       KIỂU DỮ LIỆU CHUỖI ORACLE
                                  |
                  +---------------+----------------+
                  |                                |
         Database character set          National character set
                  |                                |
           +------+-------+                 +------+-------+
           |              |                 |              |
        Fixed          Variable           Fixed          Variable
           |              |                 |              |
         CHAR           VARCHAR2          NCHAR         NVARCHAR2
```

**Trục fixed/variable** quyết định quy tắc đệm và lưu chiều dài thực tế. **Trục character set** quyết định cách ký tự được mã hóa thành byte, khả năng chuyển đổi dữ liệu và cách giới hạn byte được áp dụng.

Một bảng có thể chứa đồng thời cả bốn kiểu; không cần tạo một database riêng cho các cột `NCHAR` hoặc `NVARCHAR2`.

## 3. `CHAR`: chuỗi có độ dài cố định

### 3.1. Cú pháp

```sql
CHAR(size BYTE)
CHAR(size CHAR)
CHAR(size)
CHAR
```

`size` là độ dài khai báo; cú pháp không ghi `BYTE`/`CHAR` lấy ngữ nghĩa độ dài mặc định của môi trường. Nếu không chỉ định kích thước, `CHAR` có độ dài mặc định là **1** theo ngữ nghĩa ký tự/byte áp dụng.

Ví dụ:

```sql
CREATE TABLE demo_fixed_code (
    country_code CHAR(2 CHAR) NOT NULL,
    state_code   CHAR(4 BYTE)
);
```

`CHAR(2 CHAR)` cho phép tối đa hai đơn vị ký tự theo ngữ nghĩa ký tự của Oracle, với điều kiện giá trị không vượt giới hạn byte của kiểu dữ liệu. `CHAR(4 BYTE)` giới hạn bốn byte trong database character set; nếu ký tự cần nhiều byte, số ký tự lưu được có thể ít hơn bốn.

### 3.2. Cơ chế đệm dấu cách

Khi gán `'AB'` vào cột `CHAR(5 CHAR)`, Oracle lưu giá trị cố định với các dấu cách đệm ở cuối cho đủ độ dài:

```sql
CREATE TABLE demo_char_padding (
    fixed_text CHAR(5 CHAR)
);

INSERT INTO demo_char_padding (fixed_text) VALUES ('AB');
COMMIT;

SELECT fixed_text, LENGTH(fixed_text) AS length_chars
FROM demo_char_padding;
```

`LENGTH(fixed_text)` thường cho kết quả **5**, không phải 2, vì phần dấu cách đệm thuộc biểu diễn của giá trị `CHAR`. Khi ứng dụng đọc cột, cần biết giá trị có thể chứa khoảng trắng ở cuối.

Các dấu cách là ký tự **space** được Oracle dùng để đệm, không phải byte `0` hay ký tự `NULL`. Dùng `RTRIM` có thể bỏ khoảng trắng cuối, nhưng cũng có thể bỏ **dấu cách có ý nghĩa** vốn đã có từ dữ liệu nguồn; đừng tự động trim mọi cột mà không xét nghiệp vụ.

### 3.3. Khi nào dùng `CHAR`?

Một số mã có chiều dài được quy định cố định, như mã quốc gia hai ký tự, có thể dùng `CHAR(2 CHAR)`. Tuy nhiên, việc lựa chọn còn liên quan nhu cầu so sánh, nhập liệu, tích hợp và index. Có nhiều trường hợp dùng `VARCHAR2(2 CHAR)` cùng một ràng buộc độ dài lại thuận tiện hơn cho backend:

```sql
CREATE TABLE demo_country_code (
    code VARCHAR2(2 CHAR)
         CONSTRAINT ck_demo_country_code_len CHECK (LENGTH(code) = 2)
);
```

Nếu cần đảm bảo một mã dài đúng hai ký tự và không cho phép dấu cách không hợp lệ, hãy thiết kế thêm quy tắc kiểm tra cần thiết. **Bản thân `CHAR(2)` không tự chứng minh dữ liệu đầu vào có đúng hai ký tự có ý nghĩa**, vì Oracle sẽ đệm chuỗi ngắn.

## 4. `VARCHAR2`: chuỗi có độ dài thay đổi

### 4.1. Cú pháp và hành vi

```sql
VARCHAR2(size BYTE)
VARCHAR2(size CHAR)
VARCHAR2(size)
```

`VARCHAR2` yêu cầu khai báo một kích thước dương trong giới hạn mà phiên bản/cấu hình Oracle hỗ trợ. Nó chỉ chứa giá trị thực tế, **không tự thêm dấu cách** cho đủ kích thước tối đa.

Ví dụ:

```sql
CREATE TABLE demo_customer_text (
    customer_code VARCHAR2(20 CHAR) NOT NULL,
    full_name     VARCHAR2(100 CHAR) NOT NULL,
    email         VARCHAR2(254 CHAR)
);
```

Nếu `full_name` lưu `'Lan'`, độ dài logic là ba ký tự; Oracle không thêm 97 dấu cách. Nếu lưu `'Nguyễn Lan'`, số byte thực tế phụ thuộc database character set, nhưng giới hạn `100 CHAR` mô tả kích thước theo ngữ nghĩa ký tự, không có nghĩa 100 byte.

### 4.2. `VARCHAR2` khác `VARCHAR` như thế nào?

Oracle hiện coi `VARCHAR` là đồng nghĩa với `VARCHAR2` trong những tình huống phổ biến, nhưng tài liệu Oracle khuyến cáo **dùng `VARCHAR2`** vì ngữ nghĩa của `VARCHAR` có thể dành cho thay đổi trong tương lai. Khi tạo schema mới, ưu tiên viết rõ `VARCHAR2` để tránh phụ thuộc không cần thiết vào tên thay thế.

### 4.3. `VARCHAR2` có tự động giải quyết mọi vấn đề Unicode không?

Không hoàn toàn. Dữ liệu có được lưu đúng ký tự hay không còn phụ thuộc:

- **`NLS_CHARACTERSET`** của database: ví dụ `AL32UTF8` hỗ trợ Unicode.
- **Cách chương trình kết nối và gửi chuỗi**: driver/client cần truyền đúng ký tự, tránh lỗi chuyển mã ở đầu vào.
- **Độ dài khai báo** và giới hạn byte của kiểu: `100 CHAR` không có nghĩa Oracle bỏ qua giới hạn byte.
- **Collation và quy tắc so sánh**: Unicode encoding không tự quyết định so sánh có phân biệt chữ hoa, dấu hay không.

Với database character set `AL32UTF8`, `VARCHAR2(100 CHAR)` là lựa chọn phổ biến cho tên có dấu tiếng Việt. Với database character set cũ không biểu diễn được một số ký tự, việc chọn `VARCHAR2` có thể không đủ; cần đánh giá character set và chiến lược dữ liệu của toàn hệ thống.

## 5. `NCHAR`: chuỗi cố định trong national character set

`NCHAR` tương tự `CHAR` về nguyên tắc **độ dài cố định và đệm dấu cách**, nhưng dữ liệu được lưu bằng **national character set** của Oracle.

```sql
CREATE TABLE demo_national_fixed (
    n_code NCHAR(5)
);
```

Khi chèn một giá trị ngắn hơn năm đơn vị ký tự, Oracle đệm đến độ dài cố định theo quy tắc của kiểu. Khác với `CHAR`, kích thước `NCHAR(n)` được khai báo theo **ngữ nghĩa ký tự**, không dùng cú pháp `BYTE`/`CHAR` để đổi đơn vị như `CHAR` hoặc `VARCHAR2`.

Các cách viết liên quan như `NATIONAL CHAR` hoặc `NATIONAL CHARACTER` thuộc nhóm khai báo kiểu dữ liệu ký tự quốc gia trong Oracle.

Ví dụ dữ liệu:

```sql
INSERT INTO demo_national_fixed (n_code)
VALUES (N'AB');
```

`N'AB'` là **national character literal**. Để giữ nguyên ký tự Unicode khi viết literal có dấu trong script, cần quan tâm encoding file, driver/client và quy tắc chuyển mã. Trong ứng dụng dùng bind variable, thường để driver truyền chuỗi đúng kiểu thay vì dựng literal bằng phép ghép văn bản.

**Lưu ý:** `NCHAR` không phải kiểu “lưu mọi Unicode miễn phí”. Bộ ký tự quốc gia có thể dùng nhiều byte hơn cho một ký tự; kiểu vẫn bị giới hạn theo byte. Và tương tự `CHAR`, các dấu cách cuối được đệm có thể gây khó chịu cho logic so sánh và xử lý chuỗi.

## 6. `NVARCHAR2`: chuỗi biến thiên trong national character set

`NVARCHAR2` là kiểu ký tự **độ dài thay đổi** ở **national character set**:

```sql
CREATE TABLE demo_national_variable (
    display_name NVARCHAR2(80),
    note         NVARCHAR2(200)
);
```

`NVARCHAR2(80)` khai báo độ dài tối đa theo **ngữ nghĩa ký tự** của kiểu dữ liệu này. Khi lưu `'Lan'`, Oracle không đệm thêm các dấu cách giống `NCHAR`.

Ví dụ sử dụng national literal:

```sql
INSERT INTO demo_national_variable (display_name, note)
VALUES (N'Lan', N'Tên hiển thị');
```

Lựa chọn này có ý nghĩa khi bạn phải làm việc với cột national character set do yêu cầu di sản, khả năng tương thích với hệ thống khác, hoặc chính sách thiết kế cụ thể. Nếu database đã dùng `AL32UTF8`, lựa chọn thường gặp hơn cho phần lớn ứng dụng mới là **`VARCHAR2`**, trừ khi có lý do xác đáng để tách sang national character set.

### `NCHAR` và `NVARCHAR2` có phải kiểu dành riêng cho tiếng Việt?

Không. Chữ “N” gợi liên hệ tới **national character set**, không phải “ngôn ngữ quốc gia Việt Nam”. Oracle dùng national character set riêng và có thể biểu diễn ký tự từ nhiều ngôn ngữ. `VARCHAR2` trên database `AL32UTF8` cũng có thể lưu tiếng Việt, tiếng Nhật, tiếng Hàn và nhiều ngôn ngữ khác.

## 7. Database character set và national character set

### 7.1. Database character set

Database character set được cấu hình cho database, dùng bởi các kiểu ký tự thông thường như `CHAR`, `VARCHAR2` và các thành phần ký tự liên quan.

Ví dụ thường gặp:

```text
NLS_CHARACTERSET = AL32UTF8
```

`AL32UTF8` là bộ mã UTF-8 Unicode được Oracle khuyến nghị cho nhiều database mới. Nó hỗ trợ ký tự đa byte; vì vậy không thể giả định **một ký tự luôn bằng một byte**.

### 7.2. National character set

National character set là bộ ký tự Oracle dùng cho `NCHAR`, `NVARCHAR2` và `NCLOB`. Hai lựa chọn thường được gặp là **`AL16UTF16`** và **`UTF8`** theo tên Oracle. Trên nhiều bản cài đặt, national character set là `AL16UTF16`. Tên `UTF8` trong ngữ cảnh national character set là tên character set Oracle có đặc tính lịch sử riêng, không nên tự đồng nhất với `AL32UTF8`.

```text
Kiểu CHAR/VARCHAR2   -> NLS_CHARACTERSET
Kiểu NCHAR/NVARCHAR2 -> NLS_NCHAR_CHARACTERSET
```

Trong một database, hai bộ ký tự này có thể khác nhau. Oracle thực hiện chuyển đổi ký tự khi cần trao đổi dữ liệu giữa các kiểu/biểu thức, tùy ngữ cảnh.

### 7.3. Cách kiểm tra cấu hình trên database đang kết nối

Với quyền truy cập dictionary phù hợp:

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
```

Ví dụ đầu ra **chỉ mang tính minh họa**:

```text
PARAMETER                  VALUE
-------------------------  --------
NLS_CHARACTERSET           AL32UTF8
NLS_NCHAR_CHARACTERSET     AL16UTF16
```

Giá trị thực tế của môi trường phải lấy từ database đang kết nối. Trong kiến trúc CDB/PDB, cần chú ý đúng database/container và điều kiện truy cập metadata phù hợp.

### 7.4. Có nên chuyển toàn bộ cột sang `NVARCHAR2` để “hỗ trợ Unicode”?

Không nên coi đó là quy tắc chung. Trong database đã dùng `AL32UTF8`, `VARCHAR2` vốn là Unicode-capable. Chuyển sang `NVARCHAR2` có thể gây thêm thao tác chuyển đổi ký tự, khác biệt về giới hạn byte, ánh xạ kiểu ở driver/ORM và chi phí lưu trữ/index tùy dữ liệu.

Thay đổi character set của một database hoặc kiểu cột trên hệ thống đang chạy cần kế hoạch migration, đánh giá dữ liệu, index, ràng buộc và ứng dụng. Không tự chạy các lệnh thay đổi character set để giải quyết một vài ký tự hiển thị sai.

## 8. `BYTE` và `CHAR`: cùng số 10 nhưng có thể khác giới hạn

### 8.1. `VARCHAR2(10 BYTE)` so với `VARCHAR2(10 CHAR)`

Ví dụ:

```sql
CREATE TABLE demo_length_semantics (
    text_by_bytes VARCHAR2(10 BYTE),
    text_by_chars VARCHAR2(10 CHAR)
);
```

Hai cột cùng ghi `10`, nhưng:

- `text_by_bytes`: tối đa **10 byte** sau khi mã hóa theo database character set.
- `text_by_chars`: tối đa **10 ký tự** theo ngữ nghĩa ký tự của Oracle, **vẫn phải tuân theo giới hạn byte của kiểu dữ liệu/cột**.

Với `AL32UTF8`, chữ Latin ASCII thường chiếm 1 byte, một số ký tự tiếng Việt có dấu thường chiếm nhiều byte. Do đó chuỗi trông như “10 ký tự” có thể không vừa `VARCHAR2(10 BYTE)`.

Ví dụ minh họa về kích thước byte:

```sql
SELECT LENGTH('ABC') AS char_count,
       LENGTHB('ABC') AS byte_count
FROM dual;
```

Với chuỗi ASCII trên database `AL32UTF8`, hai giá trị thường đều là 3. Với chuỗi có ký tự đa byte, hai kết quả có thể khác:

```sql
SELECT LENGTH('Tiếng Việt') AS char_count,
       LENGTHB('Tiếng Việt') AS byte_count
FROM dual;
```

Để ví dụ có ý nghĩa, script và client phải truyền đúng ký tự Unicode; nếu dữ liệu đã bị sai encoding trước khi đến Oracle thì mọi kết quả đo sau đó đều phản ánh chuỗi sai.

### 8.2. Tại sao `10 CHAR` vẫn có giới hạn byte?

Giới hạn `CHAR` giúp diễn đạt yêu cầu nghiệp vụ theo số ký tự, nhưng Oracle vẫn cần mã hóa chúng thành byte và kiểm soát dung lượng tối đa mà kiểu/phiên bản cho phép. Một số ký tự Unicode cần nhiều byte hơn ASCII. Vì vậy, **khai báo theo ký tự không làm kích thước lưu trữ trở nên vô hạn**.

Với ký tự hiển thị phức tạp như emoji hoặc một chữ có nhiều dấu kết hợp, “một ký tự người dùng nhìn thấy” còn có thể gồm nhiều code point/đơn vị mã hóa. Không được mặc định mọi hàm đếm ký tự đều trả về đúng số *grapheme clusters* mà người dùng cảm nhận.

### 8.3. `NLS_LENGTH_SEMANTICS`

Khi với `CHAR`/`VARCHAR2` không ghi rõ `BYTE` hay `CHAR`, môi trường có tham số **`NLS_LENGTH_SEMANTICS`** ảnh hưởng đến cách diễn giải kích thước không được chỉ định đơn vị:

```sql
-- Có thể xem bằng lệnh client SQL*Plus/SQLcl:
SHOW PARAMETER nls_length_semantics
```

Hoặc tùy quyền/trạng thái:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_LENGTH_SEMANTICS';
```

Ví dụ:

```sql
CREATE TABLE demo_implicit_length (
    code VARCHAR2(20)
);
```

Tùy ngữ nghĩa độ dài của môi trường tạo bảng, `VARCHAR2(20)` có thể được hiểu theo byte hoặc theo ký tự. Với schema dùng nhiều ngôn ngữ và triển khai qua các môi trường, việc ghi rõ:

```sql
VARCHAR2(20 CHAR)
```

thường giúp hạn chế phụ thuộc vào cấu hình của session chạy migration. **`NCHAR` và `NVARCHAR2` được khai báo theo ngữ nghĩa ký tự**, không thêm `BYTE` hay `CHAR` sau độ dài như hai kiểu thông thường.

### 8.4. Tên cột của data dictionary có ý nghĩa gì?

Oracle có metadata để kiểm tra một cột cụ thể được khai báo thế nào. Ví dụ:

```sql
SELECT column_name,
       data_type,
       data_length,
       char_length,
       char_used
FROM user_tab_columns
WHERE table_name = 'DEMO_LENGTH_SEMANTICS'
ORDER BY column_id;
```

| Cột metadata | Ý nghĩa |
|---|---|
| `DATA_TYPE` | Kiểu của cột: `CHAR`, `VARCHAR2`, `NCHAR`, `NVARCHAR2`... |
| `DATA_LENGTH` | Chiều dài theo byte mà Oracle ghi nhận cho cột |
| `CHAR_LENGTH` | Chiều dài theo đơn vị ký tự mà Oracle ghi nhận |
| `CHAR_USED` | Cho biết ngữ nghĩa độ dài byte (`B`) hoặc ký tự (`C`) khi thích hợp |

Đọc metadata thực tế hữu ích hơn suy đoán từ câu DDL gốc, đặc biệt khi script đã chạy ở môi trường có cấu hình NLS khác nhau.

## 9. Giới hạn tối đa: vì sao phải phân biệt byte và ký tự?

Giới hạn của các kiểu ký tự còn phụ thuộc tham số **`MAX_STRING_SIZE`** và bộ ký tự.

| Kiểu | Trần theo byte trong cấu hình thông dụng | Ghi chú |
|---|---|---|
| `CHAR` | Tối đa **2.000 byte** | Fixed-length, vẫn phụ thuộc số byte/ký tự được yêu cầu |
| `VARCHAR2` | **4.000 byte** khi `MAX_STRING_SIZE=STANDARD`; tối đa **32.767 byte** khi `EXTENDED` | Số ký tự tối đa thực tế phụ thuộc character set |
| `NCHAR` | Tối đa **2.000 byte** | Kích thước khai báo theo ký tự; byte tiêu thụ theo national character set |
| `NVARCHAR2` | **4.000 byte** khi `STANDARD`; tối đa **32.767 byte** khi `EXTENDED` | Kích thước khai báo theo ký tự nhưng chịu trần byte |

Giới hạn byte là trần của kiểu, **không nên hiểu là luôn có thể khai báo số ký tự bằng đúng số byte tối đa**. Với national character set `AL16UTF16`, chẳng hạn, ký tự thường tiêu thụ hai byte, còn ký tự bổ sung Unicode có thể chiếm nhiều hơn; kích thước ký tự và giới hạn byte phải được xét cùng nhau.

`MAX_STRING_SIZE=EXTENDED` không tự động cho phép mở rộng kiểu `CHAR`/`NCHAR` lên 32.767 byte. Đây là cấu hình database có quy trình thiết lập và tác động hệ thống; không thay đổi chỉ để làm cho một câu `CREATE TABLE` thử nghiệm thành công.

Nếu cần lưu văn bản rất dài (hàng chục nghìn hoặc hàng triệu ký tự), hãy đánh giá `CLOB` hoặc `NCLOB` thay vì cố mở rộng `VARCHAR2`/`NVARCHAR2` vượt nhu cầu thiết kế. Việc dùng LOB cũng có khác biệt về truy cập, driver, index và hiệu năng cần học riêng.

## 10. Dấu cách ở cuối: lưu trữ và so sánh là hai vấn đề

### 10.1. Giá trị được đệm như thế nào?

Ví dụ bảng có hai cột:

```sql
CREATE TABLE demo_spaces (
    fixed_value    CHAR(5 CHAR),
    varying_value  VARCHAR2(5 CHAR)
);

INSERT INTO demo_spaces (fixed_value, varying_value)
VALUES ('A', 'A');

COMMIT;
```

Quan sát độ dài:

```sql
SELECT '[' || fixed_value || ']' AS fixed_display,
       '[' || varying_value || ']' AS varying_display,
       LENGTH(fixed_value) AS len_fixed,
       LENGTH(varying_value) AS len_varying
FROM demo_spaces;
```

Kết quả khái niệm:

```text
fixed_display    -> [A    ]
varying_display  -> [A]
len_fixed        -> 5
len_varying      -> 1
```

Khi nối chuỗi, dấu cách đệm trong `CHAR` có thể lộ ra. Nếu hệ thống tạo mã ghép như `'ORDER-' || code`, việc tự đệm dấu cách có thể dẫn đến kết quả không mong muốn nếu không thống nhất cách xử lý.

### 10.2. Blank-padded và nonpadded comparison semantics

Oracle có quy tắc so sánh chuỗi **có đệm** (*blank-padded*) và **không đệm** (*nonpadded*), tùy kiểu của hai toán hạng:

- Khi cả hai toán hạng thuộc nhóm `CHAR`, `NCHAR`, chuỗi literal hoặc biểu thức phù hợp với quy tắc của Oracle, so sánh có thể **đệm phía ngắn hơn bằng dấu cách** trước khi so.
- Khi ít nhất một toán hạng thuộc nhóm `VARCHAR2` hoặc `NVARCHAR2`, Oracle áp dụng **nonpadded comparison semantics** trong những trường hợp so sánh thông thường; dấu cách cuối có thể làm giá trị khác nhau.

Ví dụ minh họa về hai literal có ngữ nghĩa `CHAR`:

```sql
SELECT CASE
           WHEN 'A' = 'A ' THEN 'EQUAL'
           ELSE 'DIFFERENT'
       END AS comparison_result
FROM dual;
```

Theo quy tắc blank-padding dành cho các literal ký tự Oracle, kết quả có thể là `EQUAL`. Ngược lại, để quan sát phép so sánh có biến thiên, có thể ép kiểu rõ:

```sql
SELECT CASE
           WHEN CAST('A' AS VARCHAR2(1)) =
                CAST('A ' AS VARCHAR2(2))
           THEN 'EQUAL'
           ELSE 'DIFFERENT'
       END AS comparison_result
FROM dual;
```

Với nonpadded comparison, hai chuỗi này khác nhau. Đây là một ví dụ quan trọng vì lập trình viên đôi khi cho rằng **mọi so sánh chuỗi trong Oracle tự bỏ khoảng trắng cuối**; điều đó không đúng.

Quy tắc so sánh thực tế còn có thể chịu ảnh hưởng từ **collation**, `NLS_COMP`, `NLS_SORT` hoặc thiết lập collation của biểu thức/cột ở các phiên bản hỗ trợ. Đừng suy ra chỉ dựa trên một ví dụ ASCII rằng mọi dữ liệu đa ngôn ngữ đều so sánh theo byte.

### 10.3. `TRIM`, `RTRIM` và dữ liệu có nghĩa

Một cách chuẩn hóa được dùng trong ứng dụng:

```sql
SELECT RTRIM(fixed_value) AS code_without_padding
FROM demo_spaces;
```

Tuy nhiên, `RTRIM` bỏ **các dấu cách ở cuối**, kể cả dấu cách thực sự là một phần dữ liệu nghiệp vụ. Trong hệ thống cần bảo toàn nội dung văn bản nguyên bản, phải phân biệt padding do kiểu cố định với khoảng trắng do người dùng nhập.

Nếu mã có quy tắc cứng về độ dài, một thiết kế ổn định thường là `VARCHAR2` cộng ràng buộc kiểm tra, thay vì dựa vào việc `CHAR` sẽ làm ngắn thành dài.

## 11. Oracle xử lý `NULL` và chuỗi rỗng ra sao?

Trong Oracle Database hiện hành, với kiểu dữ liệu ký tự, chuỗi độ dài bằng không `''` được xử lý như `NULL`. Điều này khác với một số hệ quản trị hoặc ngôn ngữ lập trình, nơi `""` và `null` là hai giá trị riêng.

Ví dụ:

```sql
SELECT CASE
           WHEN '' IS NULL THEN 'NULL'
           ELSE 'NOT NULL'
       END AS empty_value_check
FROM dual;
```

Trong Oracle hiện hành, kết quả minh họa là `NULL`.

Với cột:

```sql
CREATE TABLE demo_required_text (
    label VARCHAR2(30 CHAR) NOT NULL
);
```

`INSERT ... VALUES ('')` không thể được coi là chèn một chuỗi rỗng hợp lệ để qua `NOT NULL`; Oracle nhìn nhận giá trị như `NULL` theo hành vi hiện hành.

**Phân biệt chuỗi rỗng với chuỗi dấu cách**:

```text
''        -> được Oracle xử lý như NULL (hành vi hiện hành)
' '       -> một ký tự space, không phải NULL
'   '     -> ba ký tự space, không phải NULL
```

Với `CHAR`, dữ liệu `' '` có thể được đệm thêm dấu cách để đủ độ dài khai báo nhưng vẫn không trở thành `NULL`.

Trong Java, `String.isEmpty()` và `String.isBlank()` cũng khác nhau. Nếu nghiệp vụ coi chuỗi chỉ gồm khoảng trắng là “không có nội dung”, cần chuẩn hóa và kiểm tra ở tầng thích hợp, đồng thời định nghĩa ràng buộc database khi cần. Không phụ thuộc duy nhất vào `NOT NULL` để loại bỏ toàn bộ giá trị chỉ gồm dấu cách.

Oracle có lưu ý về khả năng thay đổi cách xử lý chuỗi rỗng trong tương lai; khi thiết kế, nên biểu đạt ý định `NULL` một cách tường minh thay vì xây dựng logic phụ thuộc vào sự tương đương đó.

## 12. Literal, chuyển đổi kiểu và Unicode trong SQL

### 12.1. Literal thường và national literal

Trong SQL Oracle:

```sql
SELECT 'Hello'  AS database_charset_text,
       N'Hello' AS national_charset_text
FROM dual;
```

- `'Hello'` là literal ký tự thông thường.
- `N'Hello'` là **national character literal**.

Để lưu ký tự có dấu, file `.sql` và client phải xử lý encoding đúng cách. Nếu dữ liệu đã bị giải mã sai thành `?` hoặc một chuỗi mojibake trước khi Oracle nhận lệnh, việc dùng `N'...'` không tự khôi phục nội dung gốc.

### 12.2. `UNISTR` và ký tự Unicode có escape

Oracle cung cấp hàm `UNISTR` để biểu diễn ký tự Unicode theo cú pháp escape, hữu ích khi cần tránh nhập trực tiếp một số ký tự trong script:

```sql
SELECT UNISTR('\0048\00E0\0020\004E\1ED9\0069') AS city_name
FROM dual;
```

Chuỗi escape minh họa cho **“Hà Nội”**. `UNISTR` trả kết quả thuộc nhóm ký tự quốc gia; với các ký tự Unicode bổ sung cần cách biểu diễn escape thích hợp theo cơ chế Oracle.

Không nên biến mọi giá trị người dùng thành literal `UNISTR` bằng cách ghép chuỗi trong code. Với dữ liệu chạy từ ứng dụng, **bind parameter** vẫn là cách truyền giá trị phù hợp.

### 12.3. `TO_CHAR`, `TO_NCHAR` và chuyển đổi ký tự

Oracle có các cơ chế chuyển đổi dữ liệu giữa các dạng ký tự. `TO_NCHAR` có thể chuyển một biểu thức phù hợp sang biểu diễn quốc gia; `TO_CHAR` chuyển về biểu diễn ký tự thông thường trong bối cảnh hỗ trợ.

Ví dụ:

```sql
SELECT TO_NCHAR('Sample') AS national_text
FROM dual;
```

Việc chuyển đổi không bảo đảm mọi character set đích đều biểu diễn được mọi ký tự nguồn. Nếu database character set không hỗ trợ ký tự cần chuyển, có thể xảy ra thay thế ký tự hoặc lỗi phụ thuộc cấu hình. Khi làm việc với dữ liệu đa ngôn ngữ, giải pháp bền vững thường là chọn character set và driver phù hợp ngay từ thiết kế.

### 12.4. `LENGTH`, `LENGTHB`, `LENGTHC`, `LENGTH2`, `LENGTH4`

Các hàm giúp quan sát độ dài theo nhiều cách:

| Hàm | Ý nghĩa |
|---|---|
| `LENGTH(expr)` | Độ dài theo ký tự mà Oracle áp dụng cho biểu thức |
| `LENGTHB(expr)` | Độ dài theo byte |
| `LENGTHC(expr)` | Độ dài theo Unicode complete characters theo quy tắc Oracle |
| `LENGTH2(expr)` | Độ dài tính theo đơn vị UCS2 |
| `LENGTH4(expr)` | Độ dài tính theo đơn vị UCS4 |

Ví dụ:

```sql
SELECT LENGTH('A')  AS chars,
       LENGTHB('A') AS bytes
FROM dual;
```

Với ký tự ASCII và database `AL32UTF8`, thường cho `1` ở cả hai cột. Với dữ liệu chứa ký tự bổ sung Unicode, các cách đếm theo byte, code unit và code point có thể khác nhau. Đặc biệt, **độ dài theo Oracle không tự động bằng số ký tự hiển thị trên giao diện người dùng** khi một grapheme có nhiều thành phần.

### 12.5. `DUMP` hỗ trợ quan sát biểu diễn

```sql
SELECT DUMP('ABC') AS dump_text
FROM dual;
```

`DUMP` có thể cho biết kiểu nội bộ và dữ liệu byte, hữu ích khi điều tra khác biệt encoding hoặc dấu cách không nhìn thấy. Không nên dựa vào một số mã nội bộ từ `DUMP` để xây quy tắc nghiệp vụ; dùng các hàm và metadata được hỗ trợ để kiểm soát dữ liệu.

## 13. Thực hành: đặt bốn kiểu dữ liệu cạnh nhau

Ví dụ dành cho **schema thực hành** có quyền `CREATE TABLE`, quota phù hợp và một Oracle Database hoạt động. Các câu DDL/DML sẽ thay đổi dữ liệu của schema, nên **không chạy trên bảng nghiệp vụ thật**.

### Bước 1. Kiểm tra character set

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
```

Ghi lại database và national character set. Nếu cơ sở dữ liệu dùng `AL32UTF8` và `AL16UTF16`, hãy nhớ các kiểu thông thường và kiểu quốc gia có thể mã hóa cùng chữ theo số byte khác nhau.

### Bước 2. Tạo bảng thử nghiệm

```sql
CREATE TABLE demo_four_text_types (
    id             NUMBER PRIMARY KEY,
    code_fixed     CHAR(5 CHAR),
    code_varying   VARCHAR2(5 CHAR),
    code_nfixed    NCHAR(5),
    code_nvarying  NVARCHAR2(5),
    full_name      VARCHAR2(100 CHAR)
);
```

Tên `DEMO_FOUR_TEXT_TYPES` được viết dưới dạng không nháy kép, nên Oracle lưu metadata thường theo chữ hoa. Mục đích của bảng là so sánh hành vi lưu ký tự; khóa chính ở đây chỉ để phân biệt các hàng ví dụ.

### Bước 3. Chèn cùng giá trị ngắn

```sql
INSERT INTO demo_four_text_types (
    id, code_fixed, code_varying,
    code_nfixed, code_nvarying, full_name
) VALUES (
    1, 'AB', 'AB',
    N'AB', N'AB', 'Lan'
);

COMMIT;
```

Chúng ta chỉ dùng dữ liệu ASCII để tránh bị ảnh hưởng bởi cấu hình encoding client trong bước quan sát padding.

### Bước 4. Quan sát độ dài ký tự và byte

```sql
SELECT id,
       LENGTH(code_fixed)    AS len_char,
       LENGTH(code_varying)  AS len_varchar2,
       LENGTH(code_nfixed)   AS len_nchar,
       LENGTH(code_nvarying) AS len_nvarchar2
FROM demo_four_text_types;
```

Kết quả độ dài ký tự mong đợi:

```text
ID  LEN_CHAR  LEN_VARCHAR2  LEN_NCHAR  LEN_NVARCHAR2
--  --------  ------------  ---------  -------------
 1         5             2          5              2
```

So sánh byte:

```sql
SELECT LENGTHB(code_fixed)    AS bytes_char,
       LENGTHB(code_varying)  AS bytes_varchar2,
       LENGTHB(code_nfixed)   AS bytes_nchar,
       LENGTHB(code_nvarying) AS bytes_nvarchar2
FROM demo_four_text_types;
```

Kết quả byte của national types phụ thuộc `NLS_NCHAR_CHARACTERSET`; không nên ghi một con số cứng cho mọi database. Với `AL16UTF16` và ký tự Latin cơ bản, national character thường tiêu thụ nhiều byte hơn so với ký tự tương ứng trong `AL32UTF8` khi là ASCII.

### Bước 5. Nhìn rõ dấu cách đệm

```sql
SELECT '[' || code_fixed || ']'   AS fixed_display,
       '[' || code_varying || ']' AS varying_display,
       '[' || code_nfixed || ']'  AS nfixed_display,
       '[' || code_nvarying || ']' AS nvarying_display
FROM demo_four_text_types;
```

Khi client hiển thị chính xác, bạn sẽ thấy `CHAR`/`NCHAR` chứa dấu cách sau `AB`, trong khi hai kiểu biến thiên không đệm theo chiều dài tối đa.

### Bước 6. Xem metadata của từng cột

```sql
SELECT column_name,
       data_type,
       data_length,
       char_length,
       char_used
FROM user_tab_columns
WHERE table_name = 'DEMO_FOUR_TEXT_TYPES'
ORDER BY column_id;
```

Quan sát sự khác nhau giữa `CHAR_LENGTH` và `DATA_LENGTH`. Đây là cách kiểm tra thực tế thay vì kết luận từ vẻ ngoài của giá trị chuỗi.

### Bước 7. Thử chuỗi Unicode trên môi trường hỗ trợ

Nếu database dùng `AL32UTF8`, client và file script đều truyền Unicode đúng, có thể thử:

```sql
INSERT INTO demo_four_text_types (
    id, full_name, code_nvarying
) VALUES (
    2, 'Hà Nội', N'Hà'
);

COMMIT;

SELECT full_name,
       LENGTH(full_name) AS char_count,
       LENGTHB(full_name) AS byte_count,
       code_nvarying
FROM demo_four_text_types
WHERE id = 2;
```

Nếu dùng máy/terminal không xử lý Unicode đúng, trước khi kết luận kiểu cột lỗi, cần kiểm tra encoding của file script, font hiển thị và thiết lập client. National literal không sửa được văn bản đã bị hỏng ở nguồn.

### Bước 8. Dọn đối tượng thử nghiệm

Khi chắc chắn đây là bảng do chính bạn tạo trong schema thực hành và không cần giữ dữ liệu:

```sql
DROP TABLE demo_four_text_types PURGE;
```

`DROP TABLE ... PURGE` là thao tác phá hủy có commit ngầm và bỏ qua cơ chế recycle bin cho bảng phù hợp. Không chạy trên đối tượng dùng chung hoặc dữ liệu cần khôi phục.

## 14. Java/JDBC: chọn đúng kiểu và truyền chuỗi an toàn

Đối với ứng dụng Java, giao diện nghiệp vụ thường sử dụng `String` cho cả chuỗi `VARCHAR2` lẫn `NVARCHAR2`. Nhưng cách **bind** và cách driver chuyển đổi ký tự phải phù hợp với kiểu cột và khả năng của driver.

### 14.1. `VARCHAR2` qua `PreparedStatement`

Ví dụ bảng:

```sql
CREATE TABLE app_people (
    person_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(100 CHAR) NOT NULL
);
```

Trong Java:

```java
String sql = "INSERT INTO app_people (person_id, full_name) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 101L);
    ps.setString(2, "Nguyễn Lan");
    ps.executeUpdate();
}
```

`setString` truyền giá trị theo cơ chế bind của JDBC, không ghép chuỗi vào SQL. Việc ký tự tiếng Việt có được lưu đúng hay không phụ thuộc character set database và khả năng chuyển mã của driver/client.

### 14.2. `NVARCHAR2` và API `setNString`/`getNString`

Ví dụ cột kiểu national:

```sql
CREATE TABLE app_people_national (
    person_id NUMBER PRIMARY KEY,
    full_name NVARCHAR2(100) NOT NULL
);
```

Với driver JDBC hỗ trợ các API ký tự quốc gia:

```java
String sql = "INSERT INTO app_people_national (person_id, full_name)"
           + " VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 102L);
    ps.setNString(2, "Nguyễn Lan");
    ps.executeUpdate();
}
```

Đọc lại:

```java
String sql = "SELECT full_name FROM app_people_national WHERE person_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 102L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String name = rs.getNString("full_name");
            System.out.println(name);
        }
    }
}
```

Các đoạn này giả định đã có `Connection`, import JDBC, transaction/commit được quản lý ở tầng ứng dụng và driver hỗ trợ những lời gọi đó. Một số framework/ORM có cơ chế ánh xạ nationalized type riêng; hãy kiểm tra mapping thực tế thay vì chỉ đổi annotation rồi tin rằng cột Oracle tự biến đổi đúng mong muốn.

**Nguyên tắc:** nếu database dùng `AL32UTF8`, dữ liệu tiếng Việt trong `VARCHAR2` đi qua `setString` là một thiết kế bình thường. `setNString` dành cho luồng dữ liệu/cột national character set khi cần, không phải thao tác bắt buộc với mọi `String` chứa Unicode.

### 14.3. Những vấn đề thực tế với `CHAR`

Ứng dụng có thể đọc `CHAR(5)` và nhận một `String` chứa dấu cách đệm cuối. Do đó:

- Không giả định giá trị trả về luôn bằng chính xác số ký tự người dùng đã nhập.
- Không gọi `trim()` tùy tiện với họ tên, ghi chú hoặc dữ liệu cần bảo toàn khoảng trắng.
- Nếu mã yêu cầu chuẩn hóa, hãy đặt chính sách nhất quán: chọn `VARCHAR2`, kiểm tra chiều dài và chuẩn hóa theo nghiệp vụ khi có thể.

Nếu ORM sinh schema theo cấu hình, hãy đọc DDL thực tế và metadata Oracle để chắc chắn nó dùng `VARCHAR2` hay `NVARCHAR2`, và ngữ nghĩa là `BYTE` hay `CHAR`. Đừng suy luận chỉ từ tên kiểu của `String` trong Java.

### 14.4. `PreparedStatement` không bị thay thế bởi literal `N'...'`

Đây là ví dụ **không nên làm**:

```java
// Sai: ghép chuỗi người dùng trực tiếp vào câu SQL.
String sql = "SELECT * FROM app_people WHERE full_name = '" + userInput + "'";
```

Nguy cơ ở đây là SQL injection và lỗi khi dữ liệu chứa dấu nháy; thay dấu `'` bằng `N'` cũng không làm truy vấn an toàn. Cách đúng là:

```java
String sql = "SELECT person_id FROM app_people WHERE full_name = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, userInput);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý kết quả.
        }
    }
}
```

## 15. Hiệu năng, index, so sánh và quyết định thiết kế

### 15.1. `CHAR` có luôn nhanh hơn `VARCHAR2` không?

Không. “Fixed-length” không tự đồng nghĩa thao tác SQL nhanh hơn trong mọi tình huống. `CHAR` có thể chiếm thêm không gian vì padding; độ dài hàng ảnh hưởng số hàng trong một data block, I/O và hiệu quả cache. `VARCHAR2` thường phù hợp hơn với chuỗi có độ dài biến thiên.

Hiệu năng cần được đánh giá bằng workload, kích thước dữ liệu, index, execution plan và môi trường thật. Không nên đổi tất cả cột sang `CHAR` chỉ vì nghĩ bộ nhớ cố định sẽ truy cập nhanh hơn.

### 15.2. Chọn `NCHAR`/`NVARCHAR2` có tác động lưu trữ không?

Có thể có. National character set như `AL16UTF16` mã hóa nhiều ký tự thông dụng theo số byte khác `AL32UTF8`. Index key, giới hạn byte và conversion trong SQL/JDBC có thể chịu tác động. Tuy nhiên, không thể nói chính xác `NVARCHAR2` luôn tốn gấp đôi bộ nhớ vì ký tự, phân bố dữ liệu và encoding khác nhau.

Khi cần chọn kiểu để làm khóa index, phải xem **giới hạn chiều dài index key theo byte** và đặc điểm so sánh, thay vì chỉ đọc số `NVARCHAR2(100)`.

### 15.3. Encoding khác collation

- **Encoding/character set**: ký tự được biểu diễn thành byte như thế nào.
- **Collation**: chuỗi được so sánh/sắp xếp theo quy tắc nào (có thể phân biệt hoa-thường, dấu, ngôn ngữ...).

Ví dụ, lưu được chữ **“Đ”** không đồng nghĩa Oracle tự biết bạn muốn `"đ"` được coi là tương đương `"Đ"` khi tìm kiếm. Tùy phiên bản và cấu hình, các tính năng `NLS_SORT`, `NLS_COMP` hoặc collation của cột/biểu thức có thể điều chỉnh hành vi so sánh và sắp xếp.

Đối với dữ liệu người dùng có dấu tiếng Việt, ngoài kiểu cột cần xác định yêu cầu tìm kiếm: có phân biệt dấu không, có phân biệt chữ hoa không, có cần chuẩn hóa Unicode không. Đây là yêu cầu độc lập với việc chọn `VARCHAR2` hay `NVARCHAR2`.

### 15.4. Giới hạn số ký tự hiển thị khác độ dài SQL

Một emoji có thể là một code point Unicode, nhưng nhiều emoji hoặc ký tự có dấu phức tạp được dựng từ nhiều code point. Do đó thiết kế giới hạn “50 ký tự người dùng nhìn thấy” có thể **khác** `LENGTH(value) <= 50`.

Đối với ô nhập liệu có yêu cầu đặc biệt về giao diện, cần định nghĩa rõ đơn vị đếm ký tự và đồng bộ quy tắc giữa frontend, Java và database. Dù chọn `VARCHAR2(50 CHAR)`, giới hạn byte của Oracle vẫn tồn tại.

## 16. Hướng dẫn chọn kiểu dữ liệu cho tình huống thực tế

| Dữ liệu nghiệp vụ | Kiểu thường được cân nhắc | Vì sao | Điều phải kiểm soát thêm |
|---|---|---|---|
| Họ tên, địa chỉ, tên sản phẩm | `VARCHAR2(n CHAR)` nếu database dùng `AL32UTF8` | Độ dài biến thiên; Unicode trong database character set | Giới hạn byte, encoding client, chuẩn hóa đầu vào |
| Email, username | `VARCHAR2(n CHAR)` hoặc `VARCHAR2(n BYTE)` theo chính sách kỹ thuật rõ ràng | Độ dài biến thiên | Case/collation, uniqueness, validation |
| Mã quốc gia đúng hai ký tự | `CHAR(2 CHAR)` hoặc `VARCHAR2(2 CHAR)` kèm ràng buộc | Có thể là mã cố định | Padding của `CHAR`; độ dài thực tế và ký tự hợp lệ |
| Trạng thái đơn hàng như `NEW`, `PAID` | `VARCHAR2(n CHAR)` | Mã có độ dài khác nhau | `CHECK` hoặc bảng tham chiếu cho danh sách giá trị |
| Chuỗi national trong schema di sản | `NCHAR(n)`/`NVARCHAR2(n)` theo đặc tả hiện có | Tương thích cấu trúc và luồng chuyển mã đã thiết kế | JDBC/ORM mapping, giới hạn byte và conversion |
| Văn bản rất dài | `CLOB` hoặc `NCLOB` khi thực sự phù hợp | Vượt nhu cầu/giới hạn kiểu chuỗi ngắn | API LOB, storage, index, migration |

### Nguyên tắc thực hành

1. **Ưu tiên `VARCHAR2` cho chuỗi biến thiên** trong database có character set Unicode phù hợp.
2. **Ghi rõ `BYTE` hoặc `CHAR`** với `CHAR`/`VARCHAR2` khi số ký tự hay số byte là ràng buộc thiết kế cần giữ ổn định giữa môi trường.
3. **Chỉ dùng `CHAR` khi hiểu tác động của padding**; mã cố định cũng có thể lưu bằng `VARCHAR2` với kiểm tra độ dài.
4. **Chọn `NCHAR`/`NVARCHAR2` khi có lý do gắn với national character set**, không chọn chỉ vì thấy chữ Unicode hay tiếng Việt.
5. **Kiểm tra `NLS_CHARACTERSET`, `NLS_NCHAR_CHARACTERSET`, `MAX_STRING_SIZE` và metadata cột** trước khi kết luận kích thước thực tế.
6. **Tách độ dài ký tự khỏi độ dài byte và ký tự hiển thị**; với Unicode phức tạp có thể cần quy tắc đếm riêng ở ứng dụng.
7. **Dùng bind parameter trong Java** để giữ an toàn và đúng kiểu, thay vì tự ghép chuỗi SQL hoặc national literals.
8. **Quy định cách xử lý dấu cách, chuỗi rỗng và `NULL`** ở cả tầng API và database.

## 17. Những nhầm lẫn phổ biến

| Nhận định | Đánh giá | Giải thích |
|---|---|---|
| “`CHAR(10)` luôn chứa đúng mười ký tự có ý nghĩa.” | Sai | Giá trị ngắn được đệm thêm space đến chiều dài cố định |
| “`VARCHAR2(10)` tự đệm đến mười ký tự.” | Sai | Đây là kiểu độ dài biến thiên |
| “`NCHAR` và `NVARCHAR2` là kiểu bắt buộc khi lưu tiếng Việt.” | Sai | `VARCHAR2` dùng database `AL32UTF8` hỗ trợ Unicode |
| “`VARCHAR2(10 CHAR)` có thể chứa bao nhiêu byte cũng được.” | Sai | Vẫn có trần byte của kiểu/cột |
| “`NVARCHAR2(100)` luôn dùng đúng 100 byte.” | Sai | Có tối đa theo ký tự; byte thực tế phụ thuộc dữ liệu và national character set |
| “`NLS_LENGTH_SEMANTICS` quyết định đơn vị cho `NCHAR(n)`.” | Sai | `NCHAR`/`NVARCHAR2` dùng ngữ nghĩa ký tự |
| “`CHAR` và `VARCHAR2` luôn so sánh dấu cách cuối giống nhau.” | Sai | Có blank-padded và nonpadded comparison semantics |
| “`''` trong Oracle giống chuỗi rỗng độc lập trong Java.” | Sai theo hành vi Oracle hiện hành | Oracle coi zero-length string như `NULL` |
| “`LENGTH` luôn bằng `LENGTHB`.” | Sai | Unicode có thể dùng nhiều byte cho một ký tự |
| “Dùng `N'...'` sẽ sửa được ký tự đã bị lỗi encoding.” | Sai | Literal không thể khôi phục dữ liệu nguồn đã chuyển mã sai |
| “Đổi `VARCHAR2` sang `NVARCHAR2` chắc chắn nhanh hơn.” | Sai | Có thể phát sinh conversion và kích thước lưu trữ khác; phải đo |
| “Người dùng nhập một emoji thì mọi hàm độ dài Oracle đều trả `1`.” | Không bảo đảm | Có code point, code unit và grapheme cluster; cách đếm khác nhau |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Khi lưu `'AB'` vào `CHAR(5 CHAR)` và `VARCHAR2(5 CHAR)`, độ dài trả về bởi `LENGTH` khác nhau như thế nào?

**Trả lời:** Với `CHAR`, Oracle đệm đủ năm ký tự, thường `LENGTH = 5`. Với `VARCHAR2`, không có padding, `LENGTH = 2`.

**Câu 2.** Database dùng `AL32UTF8`. Để lưu họ tên tiếng Việt, có bắt buộc chọn `NVARCHAR2` không?

**Trả lời:** Không. `VARCHAR2(n CHAR)` thường phù hợp; điều kiện là dữ liệu được gửi đúng Unicode và kích thước cột đủ cho byte thực tế.

**Câu 3.** Điểm khác nhau giữa `VARCHAR2(20 BYTE)` và `VARCHAR2(20 CHAR)`?

**Trả lời:** Kiểu thứ nhất có giới hạn 20 byte, kiểu thứ hai có giới hạn 20 ký tự theo ngữ nghĩa Oracle nhưng vẫn chịu giới hạn byte tối đa.

**Câu 4.** `NCHAR(10 BYTE)` có phải cách khai báo đúng để giới hạn national text ở 10 byte?

**Trả lời:** Không. `NCHAR` khai báo độ dài theo ký tự bằng `NCHAR(n)`; không dùng `BYTE`/`CHAR` như với `CHAR`.

**Câu 5.** Có phải đặt `MAX_STRING_SIZE=EXTENDED` sẽ làm `CHAR` nhận được 32.767 byte?

**Trả lời:** Không. Chế độ extended chủ yếu mở trần byte của `VARCHAR2`/`NVARCHAR2` và các kiểu được hỗ trợ tương ứng, còn `CHAR`/`NCHAR` có giới hạn riêng.

**Câu 6.** Vì sao hai chuỗi `'A'` và `'A '` đôi khi so sánh bằng nhau, nhưng hai giá trị `VARCHAR2` tương ứng có thể khác nhau?

**Trả lời:** Oracle có quy tắc blank-padding cho một số loại toán hạng `CHAR`/literal; khi phép so sánh áp dụng nonpadded semantics của `VARCHAR2`/`NVARCHAR2`, dấu cách cuối được tính đến.

**Câu 7.** Lưu `''` vào cột `VARCHAR2 NOT NULL` có hợp lệ không?

**Trả lời:** Theo hành vi Oracle hiện hành, `''` được xử lý như `NULL`, nên vi phạm `NOT NULL`.

**Câu 8.** Muốn biết một cột thật sự dùng byte hay character semantics, nên xem gì?

**Trả lời:** Xem `USER_TAB_COLUMNS` hoặc `ALL_TAB_COLUMNS` với `DATA_TYPE`, `DATA_LENGTH`, `CHAR_LENGTH`, `CHAR_USED`, đồng thời kiểm tra các thiết lập NLS liên quan.

**Câu 9.** JDBC `setString` khác `setNString` ở mục đích gì?

**Trả lời:** `setString` phù hợp với bind chuỗi thông thường, `setNString` phục vụ bind theo kiểu national character khi driver hỗ trợ. Chúng không thay đổi cấu hình character set của database.

**Câu 10.** Có thể dùng `CHAR(2 CHAR)` để bảo đảm người dùng thực sự gửi đúng hai ký tự mã không?

**Trả lời:** Chưa đủ. Giá trị ngắn có thể được đệm bằng dấu cách. Nếu bắt buộc đúng định dạng, dùng thêm validation/ràng buộc và thống nhất việc xử lý khoảng trắng.

## 19. Kết luận

`CHAR`, `VARCHAR2`, `NCHAR`, `NVARCHAR2` là bốn kiểu ký tự của Oracle được phân biệt bằng **độ dài cố định hay biến thiên** và **database character set hay national character set**. `CHAR` và `NCHAR` có quy tắc đệm dấu cách; `VARCHAR2` và `NVARCHAR2` lưu giá trị biến thiên. Các cột thông thường dùng database character set, còn hai kiểu bắt đầu bằng `N` dùng national character set.

Khi thiết kế Oracle cho ứng dụng Java, hãy ưu tiên **kiểu đúng với bản chất dữ liệu**: chuỗi có độ dài thay đổi thường phù hợp `VARCHAR2` trên database `AL32UTF8`; kiểu national cần lý do riêng về dữ liệu hoặc khả năng tương thích. Kiểm tra ngữ nghĩa `BYTE`/`CHAR`, giới hạn byte, Unicode, so sánh khoảng trắng, `NULL` và cách bind qua JDBC để tránh lỗi chỉ xuất hiện khi dữ liệu hoặc môi trường thay đổi.

