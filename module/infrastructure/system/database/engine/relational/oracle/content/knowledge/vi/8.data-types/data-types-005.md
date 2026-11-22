# Ngữ nghĩa độ dài BYTE/CHAR và lưu trữ tiếng Việt trong Oracle Database

Một ứng dụng quản lý khách hàng có thể lưu tên `Ha Noi` thành công nhưng báo lỗi khi lưu `Hà Nội`, dù cả hai đều có sáu ký tự hiển thị. Nguyên nhân có thể là cột được định nghĩa `VARCHAR2(6 BYTE)`: Oracle giới hạn **sáu byte**, trong khi chữ tiếng Việt có dấu thường cần nhiều hơn một byte khi database sử dụng Unicode `AL32UTF8`. Cũng có trường hợp ứng dụng được sửa thành `VARCHAR2(6 CHAR)` nhưng vẫn không lưu được một chuỗi quá dài vì Oracle còn có giới hạn tối đa theo **byte** cho kiểu dữ liệu.

Bài học thuộc nhóm **Kiểu dữ liệu** trong Oracle Database, giải thích cách lựa chọn và kiểm tra ngữ nghĩa độ dài `BYTE`/**`CHAR`** khi lưu tiếng Việt. Không chỉ học cú pháp tạo bảng, bạn sẽ hiểu mối liên hệ giữa Unicode, character set, byte, code point, data dictionary, cấu hình phiên và giới hạn của JDBC/ứng dụng.

Sau bài này, bạn có thể:

- Phân biệt `VARCHAR2(20 BYTE)`, `VARCHAR2(20 CHAR)` và `VARCHAR2(20)`.
- Giải thích vì sao độ dài tiếng Việt theo **ký tự** có thể khác độ dài theo **byte** trong `AL32UTF8`.
- Dùng `LENGTH`, `LENGTHB`, `DUMP` và metadata `USER_TAB_COLUMNS` để kiểm tra dữ liệu và cấu trúc cột.
- Nhận biết tác dụng và giới hạn của `NLS_LENGTH_SEMANTICS`, `MAX_STRING_SIZE`, `CHAR`, `VARCHAR2`, `NVARCHAR2` và `CLOB`.
- Thiết kế cột cho tên người, địa chỉ, mã định danh và nội dung tiếng Việt một cách rõ ràng; xử lý lỗi `ORA-12899` hoặc dữ liệu bị sai ký tự mà không đoán mò.

> **Giả định ví dụ:** Database hoặc PDB đang thực hành dùng character set `AL32UTF8` và SQL*Plus/SQL Developer có thể gửi, hiển thị Unicode đúng. Đây là cấu hình phù hợp cho tiếng Việt hiện đại nhưng không phải mọi Oracle Database đều sử dụng. Đầu tiên hãy **kiểm tra character set thực tế**; số byte cụ thể trong ví dụ phụ thuộc vào nó và cách chuỗi được mã hóa.

## 1. Ba đơn vị cần phân biệt: byte, ký tự và ký tự hiển thị

Một chuỗi có thể được đo theo nhiều cách:

| Đơn vị | Ý nghĩa | Vì sao quan trọng? |
| --- | --- | --- |
| **Byte** | Đơn vị lưu trữ 8 bit; một Unicode code point có thể cần nhiều byte trong UTF-8 | `VARCHAR2(n BYTE)` và giới hạn tối đa dung lượng SQL |
| **Character/code point** | Một điểm mã trong character set; Oracle dùng đơn vị ký tự để diễn giải `VARCHAR2(n CHAR)` | Kiểm tra số ký tự logic của cột |
| **Grapheme cluster / ký tự người dùng nhìn thấy** | Một đơn vị hiển thị như chữ cái cộng dấu kết hợp hoặc emoji phức hợp | Form nhập liệu, giới hạn hiển thị, cắt chuỗi an toàn |

Trong trường hợp thông dụng, một chữ tiếng Việt có dấu như `à` là **một code point** nhưng có thể cần **hai byte** khi mã hóa bằng UTF-8. Chữ `ộ` thường là **một code point** và cần **ba byte**. Ký tự ASCII như `A`, dấu cách và các chữ số 0–9 chỉ cần một byte trong `AL32UTF8`.

Tuy nhiên, Unicode cho phép cùng một chữ nhìn thấy giống nhau được biểu diễn bằng **một code point dựng sẵn** hoặc **nhiều code point gồm chữ cái và dấu kết hợp**. Vì thế “6 ký tự người dùng thấy” không luôn đồng nghĩa “6 code point”. Khi xác định giới hạn thực tế, cần chú ý cả **encoding** và **Unicode normalization**.

### 1.1. Một số ký tự tiếng Việt trong AL32UTF8

| Chuỗi/điểm mã | Số code point khi ở dạng dựng sẵn (NFC) | Số byte trong AL32UTF8 | Diễn giải |
| --- | ---: | ---: | --- |
| `A` | 1 | 1 | ASCII |
| `à` (U+00E0) | 1 | 2 | Ký tự Latin có dấu |
| `đ` (U+0111) | 1 | 2 | Chữ đ tiếng Việt |
| `ộ` (U+1ED9) | 1 | 3 | Chữ Latin có nhiều dấu |
| `Ha Noi` | 6 | 6 | Chỉ chứa ASCII |
| `Hà Nội` | 6 | 9 | H = 1, à = 2, cách = 1, N = 1, ộ = 3, i = 1 |

Các con số minh họa dùng chuỗi đã được biểu diễn theo dạng dựng sẵn **NFC**. Một chuỗi trông giống `Hà Nội` nhưng chứa dấu kết hợp tách rời có thể có số code point và số byte khác. Oracle không nên bị xem là công cụ tự động chuẩn hóa mọi chuỗi nhập thành NFC.

### 1.2. Đường đi của một chuỗi tiếng Việt

~~~text
Nguoi dung go "Hà Nội"
         |
         v
UI / Java String / JDBC parameter
         |
         |  Chuyen doi theo driver, encoding va character set
         v
Oracle column VARCHAR2(...)
         |
         +--> Gioi han so character neu khai bao CHAR
         |
         +--> Gioi han byte cua cot / datatype van phai duoc ton trong
         |
         v
Gia tri duoc luu theo database character set
~~~

Nếu lỗi xảy ra ở khâu terminal/driver/encoding, việc tăng độ dài cột **không thể khôi phục những dấu tiếng Việt đã bị thay bằng dấu hỏi**. Nếu lỗi xảy ra do cột quá ngắn, đổi mã hóa của client một cách tùy tiện cũng không giải quyết đúng nguyên nhân.

## 2. `VARCHAR2(n BYTE)` và `VARCHAR2(n CHAR)`

### 2.1. `BYTE` giới hạn tổng số byte

~~~sql
CREATE TABLE vn_byte_example (
    display_name VARCHAR2(6 BYTE)
);
~~~

`VARCHAR2(6 BYTE)` cho phép mỗi giá trị dài tối đa **6 byte** theo database character set. Với `AL32UTF8`:

- `'Ha Noi'` cần 6 byte ⇒ vừa giới hạn.
- `'Hà Nội'` (NFC) cần 9 byte ⇒ vượt giới hạn.
- `'ààà'` cần 6 byte ⇒ vừa giới hạn dù chỉ có 3 ký tự.
- `'ộộộ'` cần 9 byte ⇒ vượt giới hạn dù cũng chỉ có 3 ký tự.

Không thể suy ra rằng một cột `VARCHAR2(6 BYTE)` sẽ chứa được “sáu chữ cái tiếng Việt”. Sáu byte là giới hạn byte; số ký tự có thể lưu được còn phụ thuộc nội dung.

### 2.2. `CHAR` giới hạn số ký tự/code point

~~~sql
CREATE TABLE vn_char_example (
    display_name VARCHAR2(6 CHAR)
);
~~~

`VARCHAR2(6 CHAR)` cho phép tối đa **6 ký tự** theo semantics của Oracle cho database character set. Với dữ liệu NFC:

- `'Ha Noi'`: 6 ký tự ⇒ hợp lệ.
- `'Hà Nội'`: 6 ký tự ⇒ hợp lệ dù cần 9 byte.
- `'ộộộộộộ'`: 6 ký tự ⇒ hợp lệ nếu không chạm giới hạn byte tuyệt đối của datatype.
- `'Hà Nội!'`: 7 ký tự ⇒ vượt giới hạn.

Khai báo `CHAR` ở đây là **length semantics**, không có nghĩa dữ liệu tự đổi sang kiểu `CHAR` cố định. Kiểu cột vẫn là **`VARCHAR2`**: giá trị có độ dài biến thiên, Oracle không tự thêm dấu cách để đủ sáu ký tự.

### 2.3. So sánh trên cùng một bảng

| Khai báo | Giới hạn được nêu trong DDL | `Ha Noi` (6 byte, 6 ký tự) | `Hà Nội` (9 byte, 6 ký tự) |
| --- | --- | --- | --- |
| `VARCHAR2(6 BYTE)` | Tối đa 6 byte | Lưu được | Không lưu được |
| `VARCHAR2(6 CHAR)` | Tối đa 6 ký tự, vẫn chịu byte cap datatype | Lưu được | Lưu được |
| `VARCHAR2(6)` | Theo `NLS_LENGTH_SEMANTICS` của phiên tạo cột | Phụ thuộc session | Phụ thuộc session |

Điểm quan trọng là **`BYTE` và `CHAR` mô tả tiêu chí độ dài**, không mô tả tên bộ mã. Một cột `VARCHAR2(30 CHAR)` trong database `AL32UTF8` vẫn lưu ký tự bằng `AL32UTF8`; nó không chuyển dữ liệu sang UTF-16 chỉ vì có chữ `CHAR`.

## 3. Thiết lập và xác định character set thực tế

### 3.1. Hai character set trong Oracle

Oracle phân biệt:

| Character set | Áp dụng chủ yếu cho | Ví dụ giá trị thường gặp |
| --- | --- | --- |
| **Database character set** | `CHAR`, `VARCHAR2`, `CLOB` và nhiều thông tin chuỗi trong database | `AL32UTF8` |
| **National character set** | `NCHAR`, `NVARCHAR2`, `NCLOB` | `AL16UTF16`, hoặc cấu hình national charset được Oracle hỗ trợ |

Với database character set `AL32UTF8`, cột `VARCHAR2(... CHAR)` hoàn toàn có thể lưu tiếng Việt. **Không bắt buộc chuyển sang `NVARCHAR2` chỉ vì dữ liệu có dấu tiếng Việt.** Việc chọn NCHAR types nên dựa trên yêu cầu cụ thể, driver và chính sách dữ liệu hiện có.

Kiểm tra bằng SQL trong database/PDB đang kết nối:

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
~~~

Ví dụ kết quả:

~~~text
PARAMETER               VALUE
----------------------  --------
NLS_CHARACTERSET        AL32UTF8
NLS_NCHAR_CHARACTERSET  AL16UTF16
~~~

Nếu `NLS_CHARACTERSET` là bộ mã khác, số byte dự đoán ở phần trước **không nhất thiết đúng**. Nếu một ký tự tiếng Việt không biểu diễn được trong character set của database, chuyển đổi ký tự có thể thất bại hoặc làm mất dữ liệu tùy đường truyền/cấu hình. Giải pháp dài hạn thường là chọn character set hỗ trợ đầy đủ Unicode, nhưng **chuyển character set của database là một dự án migration**, không phải chỉnh `NLS_LENGTH_SEMANTICS` là xong.

### 3.2. Tại sao ưu tiên AL32UTF8?

`AL32UTF8` là cách Oracle triển khai bộ mã UTF-8 hiện đại cho database character set, hỗ trợ ký tự Unicode trên nhiều ngôn ngữ. Nó phù hợp cho hệ thống vừa lưu tiếng Việt, vừa lưu tên nước ngoài, ký hiệu và những ký tự ngoài BMP (một code point có thể chiếm bốn byte).

Đừng nhầm tên character set Oracle legacy `UTF8` với `AL32UTF8`: Oracle có phân biệt giữa hai lựa chọn này, đặc biệt ở cách biểu diễn một số ký tự Unicode ngoài BMP. Với hệ thống mới, dùng `AL32UTF8` theo hướng dẫn Oracle là lựa chọn phổ biến.

Lựa chọn character set và lựa chọn `BYTE/CHAR` phục vụ **hai mục tiêu khác nhau**:

~~~text
AL32UTF8:  Ky tu nao co the bieu dien, va moi ky tu can bao nhieu byte?

BYTE/CHAR: Moi gia tri cua mot cot duoc gioi han theo byte hay code point?
~~~

Database đã hỗ trợ Unicode mà schema khai báo cột không hợp lý vẫn có thể báo lỗi quá độ dài.

## 4. `LENGTH`, `LENGTHB`, `LENGTHC` và các hàm liên quan

### 4.1. Đo chuỗi theo ký tự và byte

Oracle cung cấp nhiều hàm độ dài:

| Hàm | Đơn vị tính | Trường hợp sử dụng |
| --- | --- | --- |
| `LENGTH(text)` | Ký tự theo character set của expression | Kiểm tra số ký tự dữ liệu thông thường |
| `LENGTHB(text)` | Byte | Kiểm tra kích thước biểu diễn chuỗi ngắn trong character set tương ứng |
| `LENGTHC(text)` | Unicode complete characters theo định nghĩa Oracle | Kiểm tra các trường hợp Unicode cần cách đếm khác `LENGTH` |
| `LENGTH2(text)` | Đơn vị mã UCS-2 | Phân tích tình huống Unicode đặc biệt |
| `LENGTH4(text)` | Điểm mã UCS-4 | Phân tích số code point Unicode trong tình huống phù hợp |

Với một literal tiếng Việt được gửi vào database `AL32UTF8` **đúng mã hóa** và ở dạng NFC:

~~~sql
SELECT
    LENGTH('Hà Nội')  AS character_count,
    LENGTHB('Hà Nội') AS byte_count
FROM dual;
~~~

Kết quả mong đợi:

~~~text
CHARACTER_COUNT  BYTE_COUNT
---------------  ----------
6                9
~~~

Kiểm tra thêm:

~~~sql
SELECT
    LENGTH('Ha Noi')  AS ascii_chars,
    LENGTHB('Ha Noi') AS ascii_bytes,
    LENGTH('ộ')       AS viet_chars,
    LENGTHB('ộ')      AS viet_bytes
FROM dual;
~~~

Trong `AL32UTF8` và khi client nhập đúng Unicode, `Ha Noi` có 6/6 và `ộ` có 1/3. Nếu kết quả khác hoặc chuỗi xuất ra thành `H? N?i`, cần kiểm tra **quá trình nhập và chuyển mã**, không chỉ schema.

### 4.2. Dùng `DUMP` để xem biểu diễn byte

Hàm `DUMP` có thể cho biết datatype và biểu diễn byte của expression:

~~~sql
SELECT
    DUMP('Hà Nội', 1016) AS hex_dump,
    LENGTH('Hà Nội')     AS chars,
    LENGTHB('Hà Nội')    AS bytes
FROM dual;
~~~

Tham số `1016` yêu cầu dạng thập lục phân kèm thông tin character set thích hợp. Trong môi trường `AL32UTF8`, dãy byte của chuỗi NFC sẽ phản ánh mã UTF-8 của từng code point.

Nếu bạn muốn tạo một ký tự Unicode **mà không phụ thuộc cách terminal gõ dấu**, Oracle có hàm `UNISTR` với escape Unicode:

~~~sql
-- U+00E0 la chu a dau huyen.
SELECT
    CAST(UNISTR('\00E0') AS VARCHAR2(10 CHAR)) AS unicode_character
FROM dual;
~~~

`UNISTR` trả chuỗi thuộc national character set; `CAST ... AS VARCHAR2` chuyển sang database character set trong ví dụ. Nó hữu ích khi phân biệt lỗi dữ liệu nhập từ terminal với lỗi encoding trong database.

### 4.3. Unicode chuẩn hóa: ký tự nhìn giống nhau chưa chắc có cùng độ dài

Hai chuỗi dưới đây có thể hiển thị giống nhau:

~~~text
NFC:  "é"   = U+00E9                (1 code point)
NFD:  "é"  = U+0065 + U+0301       (2 code points)
~~~

Với `AL32UTF8`, chúng có độ dài:

| Dạng | Số code point | Byte UTF-8 |
| --- | ---: | ---: |
| Dựng sẵn `é` | 1 | 2 |
| Chữ `e` + dấu kết hợp | 2 | 3 |

Trong một DB `AL32UTF8`, có thể kiểm tra bằng expression tạo từ escape Unicode:

~~~sql
SELECT
    LENGTH(CAST(UNISTR('\00E9') AS VARCHAR2(20 CHAR)))    AS precomposed_len,
    LENGTHB(CAST(UNISTR('\00E9') AS VARCHAR2(20 CHAR)))   AS precomposed_bytes,
    LENGTH(CAST(UNISTR('e\0301') AS VARCHAR2(20 CHAR)))   AS decomposed_len,
    LENGTHB(CAST(UNISTR('e\0301') AS VARCHAR2(20 CHAR)))  AS decomposed_bytes
FROM dual;
~~~

Giá trị mong đợi tương ứng là **1/2** và **2/3**. Đây là lý do giới hạn tính theo “số ký tự người dùng nhìn thấy” của giao diện đôi khi không khớp số code point mà database/driver kiểm tra.

**Khuyến nghị:** Nếu ứng dụng cần các chuỗi tiếng Việt được lưu nhất quán, hãy thiết kế chính sách normalization Unicode (thường là NFC) ở lớp nhập liệu/ứng dụng và kiểm thử round-trip. Không mặc định `VARCHAR2(n CHAR)` hoặc `LENGTHC` thay thế được một thư viện xử lý grapheme cluster đầy đủ cho mọi ngôn ngữ và emoji phức hợp.

### 4.4. `SUBSTR` và `SUBSTRB`

Sự khác biệt BYTE/CHAR còn xuất hiện trong hàm cắt chuỗi:

~~~sql
-- Hai ky tu dau cua mot chuoi theo character semantics:
SELECT SUBSTR('Hà Nội', 1, 2) AS first_two_chars
FROM dual;

-- Chuoi duoc cat theo byte; co the khong phu hop cho text Unicode:
SELECT SUBSTRB('Hà Nội', 1, 2) AS first_two_bytes
FROM dual;
~~~

Với text tiếng Việt, khi nghiệp vụ nói “lấy hai ký tự đầu”, dùng `SUBSTR` thường phù hợp hơn `SUBSTRB`. Cắt giữa nhiều byte của một code point có thể tạo ra kết quả không mong muốn, phụ thuộc chuyển đổi và xử lý của hệ thống. Đừng dùng `SUBSTRB` để áp giới hạn UI ký tự.

Các hàm đo theo byte hữu ích cho mã giao thức, file format, giới hạn payload theo byte hoặc chẩn đoán lỗi, chứ không nên là mặc định cho tên người/địa chỉ.

## 5. Thực hành: một bảng có cả BYTE và CHAR semantics

Thực hiện trên schema lab được phép `CREATE TABLE` trong một PDB đang mở `READ WRITE`. Trước khi chạy, kiểm tra character set theo Mục 3. Các ví dụ dưới đây có giá trị kết quả cố định chỉ khi database dùng `AL32UTF8` và client gửi Unicode đúng.

### Bước 1 — Tạo bảng thực hành

~~~sql
CREATE TABLE vn_length_lab (
    id          NUMBER PRIMARY KEY,
    byte_label  VARCHAR2(6 BYTE),
    char_label  VARCHAR2(6 CHAR),
    code        VARCHAR2(6 BYTE)
);
~~~

Hai cột `BYTE_LABEL` và `CHAR_LABEL` đều chứa văn bản, nhưng ràng buộc độ dài khác nhau. Cột `CODE` cố ý sử dụng `BYTE` vì mã ví dụ được quy định chỉ gồm ký tự ASCII với chiều dài byte rõ ràng.

### Bước 2 — Lưu chuỗi ASCII

~~~sql
INSERT INTO vn_length_lab (id, byte_label, char_label, code)
VALUES (1, 'Ha Noi', 'Ha Noi', 'HN0001');

COMMIT;
~~~

Hai giá trị `'Ha Noi'` đều dài **6 ký tự và 6 byte** nên phù hợp cả hai kiểu cột.

### Bước 3 — Lưu tên tiếng Việt có dấu

~~~sql
INSERT INTO vn_length_lab (id, byte_label, char_label, code)
VALUES (2, NULL, 'Hà Nội', 'HN0002');

COMMIT;
~~~

Giá trị `'Hà Nội'` có 6 code point và 9 byte trong AL32UTF8/NFC; vì thế chỉ cột `CHAR_LABEL` nhận được nó theo giới hạn đã khai báo. Cột `BYTE_LABEL` để `NULL`.

### Bước 4 — Thử lỗi có chủ đích ở cột BYTE

~~~sql
-- Du kien loi ORA-12899 voi AL32UTF8/NFC:
INSERT INTO vn_length_lab (id, byte_label, char_label, code)
VALUES (3, 'Hà Nội', 'Hà Nội', 'HN0003');
~~~

Trong môi trường ví dụ, Oracle có thể báo `ORA-12899: value too large for column` cho `BYTE_LABEL`, với thực tế 9 byte vượt giới hạn 6 byte. Câu `INSERT` thất bại **không tạo một nửa hàng**: toàn bộ statement không được áp dụng thành công. Không cần tăng kích thước cột chỉ để làm biến mất lỗi demo; thông điệp của bài là hiểu thiết kế giới hạn.

### Bước 5 — Đọc lại giá trị và đo độ dài

~~~sql
SELECT
    id,
    byte_label,
    char_label,
    LENGTH(char_label)  AS char_count,
    LENGTHB(char_label) AS byte_count
FROM vn_length_lab
ORDER BY id;
~~~

Kỳ vọng:

| ID | BYTE_LABEL | CHAR_LABEL | CHAR_COUNT | BYTE_COUNT |
| --- | --- | --- | ---: | ---: |
| 1 | `Ha Noi` | `Ha Noi` | 6 | 6 |
| 2 | `NULL` | `Hà Nội` | 6 | 9 |

Giá trị `NULL` được trình bày bằng chữ để dễ đọc; trong kết quả SQL, NULL thường hiển thị trống. Hàng ID=3 không xuất hiện vì bước kiểm tra lỗi đã thất bại.

### Bước 6 — Xem metadata của hai cột

~~~sql
SELECT
    column_name,
    data_type,
    data_length,
    char_length,
    char_used
FROM user_tab_columns
WHERE table_name = 'VN_LENGTH_LAB'
ORDER BY column_id;
~~~

Trong Oracle dictionary:

- `DATA_LENGTH` phản ánh **độ dài tối đa bằng byte** mà metadata quy định cho kiểu cột.
- `CHAR_LENGTH` phản ánh thông tin độ dài theo ký tự dành cho các kiểu character, nhưng **không nên dùng một mình** để suy ra thực tế chuỗi đa byte sẽ lưu vừa ở cột có `BYTE` semantics.
- `CHAR_USED = 'B'` có nghĩa cột được khai báo theo **BYTE**.
- `CHAR_USED = 'C'` có nghĩa cột được khai báo theo **CHAR**.

Với `AL32UTF8`, cột `CHAR_LABEL VARCHAR2(6 CHAR)` có thể có `DATA_LENGTH=24` để phản ánh khả năng tối đa bốn byte/code point, trong khi `BYTE_LABEL VARCHAR2(6 BYTE)` có `DATA_LENGTH=6`. **`DATA_LENGTH` không phải số byte mà một hàng đã sử dụng.** `VARCHAR2` chỉ lưu độ dài thực tế của giá trị theo cơ chế lưu trữ và định dạng Oracle, không tự dành 24 byte cho mọi hàng.

### Bước 7 — Dọn bảng demo nếu không cần

~~~sql
-- Chi chay voi bang lab do chinh ban tao va da xac nhan khong can du lieu.
DROP TABLE vn_length_lab;
~~~

DDL của Oracle có hành vi commit theo cơ chế của database; không xem `DROP TABLE` như một phép thử có thể rollback ngay bằng `ROLLBACK`. Giữ lại bảng nếu cần quan sát metadata ở các phần sau.

## 6. `NLS_LENGTH_SEMANTICS`: mặc định khi không ghi BYTE/CHAR

### 6.1. Vì sao `VARCHAR2(30)` có thể gây bất ngờ?

Khi khai báo:

~~~sql
CREATE TABLE customer_example (
    full_name VARCHAR2(30)
);
~~~

DDL không nói rõ `BYTE` hay `CHAR`. Oracle sẽ lấy mặc định độ dài từ **`NLS_LENGTH_SEMANTICS` của phiên tạo đối tượng** (với một số ngoại lệ như đối tượng do `SYS` tạo).

Kiểm tra:

~~~sql
SHOW PARAMETER nls_length_semantics;

SELECT value
FROM nls_session_parameters
WHERE parameter = 'NLS_LENGTH_SEMANTICS';
~~~

Giá trị được hỗ trợ là `BYTE` hoặc `CHAR`; mặc định thường là `BYTE`. Hai phiên triển khai chạy cùng một `CREATE TABLE ... VARCHAR2(30)` nhưng có tham số session khác nhau có thể tạo hai cột với length semantics khác nhau.

### 6.2. Thay đổi mặc định theo phiên

Trên schema lab riêng:

~~~sql
-- Thay doi mac dinh cho DDL duoc tao sau lenh nay trong session.
ALTER SESSION SET NLS_LENGTH_SEMANTICS = CHAR;

CREATE TABLE implicit_char_lab (
    viet_name VARCHAR2(30),
    byte_code VARCHAR2(10 BYTE)
);

SELECT column_name, data_length, char_length, char_used
FROM user_tab_columns
WHERE table_name = 'IMPLICIT_CHAR_LAB'
ORDER BY column_id;

-- Khoi phuc gia tri muc dich cua lab.
ALTER SESSION SET NLS_LENGTH_SEMANTICS = BYTE;
~~~

Trong ví dụ này:

- `VIET_NAME VARCHAR2(30)` được tạo theo semantics `CHAR` do mặc định session lúc chạy DDL.
- `BYTE_CODE VARCHAR2(10 BYTE)` vẫn dùng `BYTE` do **khai báo explicit ưu tiên**.
- Đổi session trở lại `BYTE` **không tự đổi cột đã tạo** thành `VARCHAR2(30 BYTE)`.

Nếu muốn hoàn nguyên đúng cấu hình phiên ban đầu, hãy ghi nhận giá trị trước khi thao tác và đặt lại giá trị đó; không mặc định mọi phiên đều bắt đầu ở `BYTE`.

### 6.3. Vì sao không nên thay tham số toàn instance chỉ để hỗ trợ tiếng Việt?

Oracle khuyến nghị **đặt `BYTE`/`CHAR` tường minh trong DDL** khi mục tiêu là tài liệu hóa ý nghĩa cột và tránh phụ thuộc môi trường. Việc đổi `NLS_LENGTH_SEMANTICS` thành `CHAR` trên toàn instance có thể làm những script legacy bất ngờ tạo cột lớn hơn, gây khác biệt metadata hoặc lỗi ở code/migration vốn giả định byte.

Một số lưu ý:

- Tham số **session** quyết định mặc định cho những khai báo không explicit được tạo trong session đó; không phải giới hạn kiểm tra dữ liệu tức thời của mọi cột đã tồn tại.
- Tài khoản `SYS` có quy tắc mặc định đặc biệt và không nên được dùng tạo bảng ứng dụng.
- Client, công cụ migration và driver có thể khởi tạo session khác nhau. Đọc giá trị phiên thật đang chạy DDL thay vì chỉ nhìn cấu hình instance.
- `NLS_LENGTH_SEMANTICS` **không đổi character set của database**, không tự chuyển dữ liệu sang UTF-8 và không làm tăng giới hạn byte tối đa của SQL datatype.

Trên dự án có schema versioning, DDL explicit là giải pháp dễ kiểm thử và tái lập hơn:

~~~sql
CREATE TABLE customer_profile (
    customer_id   NUMBER PRIMARY KEY,
    full_name     VARCHAR2(120 CHAR) NOT NULL,
    contact_code  VARCHAR2(32 BYTE)
);
~~~

Mỗi cột ghi rõ mục đích sử dụng; dù session `NLS_LENGTH_SEMANTICS` đang là `BYTE` hay `CHAR`, hai định nghĩa ở đây vẫn có semantics như đã viết.

## 7. Giới hạn byte tối đa của `VARCHAR2` và ý nghĩa thực của CHAR

Một hiểu lầm phổ biến là: “`VARCHAR2(4000 CHAR)` chắc chắn lưu được 4.000 chữ Unicode bất kỳ”. Điều này không đúng nếu dữ liệu phải tuân theo giới hạn byte tối đa của `VARCHAR2` trong SQL.

### 7.1. `MAX_STRING_SIZE`

Đối với **SQL columns** kiểu `VARCHAR2`, giới hạn byte tuyệt đối phụ thuộc tham số `MAX_STRING_SIZE`:

| `MAX_STRING_SIZE` | Giới hạn byte tối đa của giá trị `VARCHAR2` trong SQL |
| --- | ---: |
| `STANDARD` | 4.000 byte |
| `EXTENDED` | 32.767 byte |

Kiểm tra trên môi trường mà bạn có quyền:

~~~sql
SHOW PARAMETER max_string_size;
~~~

Ngay cả khi cột khai báo theo `CHAR`, một giá trị thực tế không thể vượt giới hạn byte áp dụng. Ví dụ với `AL32UTF8` và `MAX_STRING_SIZE=STANDARD`, 2.000 ký tự mỗi ký tự 3 byte sẽ cần khoảng 6.000 byte; giá trị đó **không lưu vừa** một cột `VARCHAR2(2000 CHAR)` trong SQL, dù số ký tự bằng giới hạn khai báo.

Trong khi đó, `VARCHAR2(100 CHAR)` với tối đa 4 byte/code point cần nhiều nhất khoảng 400 byte, nằm dưới trần 4.000 byte của cấu hình `STANDARD`. Chọn độ dài vừa đủ theo nghiệp vụ làm mô hình dữ liệu dễ dự đoán hơn.

**Đừng suy ra trần SQL từ PL/SQL:** biến `VARCHAR2` trong PL/SQL có các quy tắc/khả năng kích thước khác so với cột `VARCHAR2` trong SQL table. Một chuỗi xử lý được trong PL/SQL chưa chắc lưu vừa một cột SQL.

### 7.2. CHAR là ràng buộc theo ký tự, không phải bảo đảm mọi chuỗi Unicode sẽ lưu được

Trong Oracle `VARCHAR2(n CHAR)`:

1. Có giới hạn **n ký tự/code point** theo semantics của datatype và database character set.
2. Vẫn có giới hạn byte tối đa do **`MAX_STRING_SIZE`** và định nghĩa cột áp dụng.
3. Byte thực tế phụ thuộc dữ liệu, Unicode normalization và character set.

Vì thế, giải pháp “đổi hết thành CHAR” chưa đủ để quyết định kích thước cột. Cần phân loại nghiệp vụ: tên người, địa chỉ, ghi chú dài, mã ký tự ASCII hoặc payload dạng JSON sẽ có nhu cầu khác nhau.

### 7.3. Khi nào nên dùng `CLOB`?

Nếu giá trị là **nội dung văn bản dài** như mô tả tài liệu, bài viết, chú thích nhiều trang hoặc dữ liệu văn bản có thể vượt giới hạn `VARCHAR2`, hãy cân nhắc `CLOB`:

~~~sql
CREATE TABLE vietnamese_documents (
    document_id NUMBER PRIMARY KEY,
    title       VARCHAR2(200 CHAR) NOT NULL,
    body_text   CLOB
);
~~~

`CLOB` dùng database character set và được thiết kế cho dữ liệu ký tự lớn; `NCLOB` dùng national character set. Chúng có cách lưu, truy cập và giới hạn API khác `VARCHAR2`. Với CLOB, `DBMS_LOB.GETLENGTH(clob_column)` trả về độ dài theo **ký tự**; `LENGTHB` không được hỗ trợ trực tiếp trên multibyte CLOB theo cách dùng cho `VARCHAR2`. Không thay mọi `VARCHAR2` bằng `CLOB` vì tìm kiếm, index, ràng buộc và performance cần được thiết kế theo mục đích.

## 8. `CHAR` cố định, `VARCHAR2` biến thiên và `NCHAR/NVARCHAR2`

### 8.1. `CHAR(10 CHAR)` khác `VARCHAR2(10 CHAR)` ra sao?

Ở cả hai kiểu, `(10 CHAR)` nói về **đơn vị độ dài theo ký tự**, nhưng:

| Kiểu cột | Cách lưu giá trị ngắn hơn độ dài khai báo | Phù hợp hơn với |
| --- | --- | --- |
| `CHAR(10 CHAR)` | Oracle **đệm dấu cách** đến độ dài cố định 10 ký tự | Mã có độ dài cố định thật sự, một vài cấu trúc legacy |
| `VARCHAR2(10 CHAR)` | Không đệm dấu cách theo độ dài khai báo | Tên, nhãn, địa chỉ, nội dung ngắn thay đổi độ dài |

Ví dụ:

~~~sql
CREATE TABLE fixed_vs_variable (
    fixed_code CHAR(5 CHAR),
    person_name VARCHAR2(5 CHAR)
);

INSERT INTO fixed_vs_variable VALUES ('AB', 'AB');

SELECT
    LENGTH(fixed_code)  AS fixed_chars,
    LENGTH(person_name) AS variable_chars
FROM fixed_vs_variable;
~~~

Với dữ liệu `'AB'`, giá trị `FIXED_CODE` thường dài 5 ký tự do có 3 dấu cách đệm, trong khi `PERSON_NAME` dài 2 ký tự. `LENGTH` trên kiểu `CHAR` bao gồm dấu cách cuối. Hãy tính đến **blank-padding và comparison semantics** khi chọn kiểu `CHAR`; đừng dùng nó chỉ vì nghĩ “CHAR hỗ trợ Unicode hơn VARCHAR2”.

### 8.2. `NVARCHAR2(n)` và national character set

`NVARCHAR2(n)` dùng **national character set** và có semantics theo **ký tự**, không thêm `BYTE`/`CHAR` vào khai báo như `VARCHAR2`:

~~~sql
CREATE TABLE national_text_lab (
    id          NUMBER PRIMARY KEY,
    regular_vn  VARCHAR2(50 CHAR),
    national_vn NVARCHAR2(50)
);
~~~

Cả hai có thể lưu tiếng Việt **khi database character set hỗ trợ Unicode**, chẳng hạn `AL32UTF8`. `NVARCHAR2` hữu ích trong các nhu cầu tương thích cụ thể hoặc khi database character set hiện tại không hỗ trợ đầy đủ Unicode, nhưng kéo theo cơ chế chuyển mã national character set, giới hạn byte và yêu cầu driver/ứng dụng riêng. **Không dùng `NVARCHAR2` như một bản vá mặc định cho lỗi `ORA-12899`.**

Tham số `NLS_LENGTH_SEMANTICS` chỉ chọn mặc định cho các khai báo character type áp dụng, chứ không chuyển `NCHAR/NVARCHAR2` sang kiểu byte semantics. Với national character types, đơn vị chiều dài đã là ký tự.

## 9. Thiết kế lưu trữ tiếng Việt theo từng loại trường

| Trường dữ liệu | Kiểu gợi ý | Lý do |
| --- | --- | --- |
| Họ tên khách hàng | `VARCHAR2(120 CHAR)` | Nghiệp vụ thường giới hạn theo số ký tự; có thể gồm dấu tiếng Việt |
| Tên quận/huyện, địa chỉ giao hàng | `VARCHAR2(255 CHAR)` hoặc giới hạn phù hợp nghiệp vụ | Dữ liệu đa ngôn ngữ và chiều dài biến thiên |
| Mã khách hàng chỉ cho phép ASCII | `VARCHAR2(32 BYTE)` cộng validation | Giới hạn theo byte rõ ràng, nhưng **BYTE không tự cấm ký tự Unicode** |
| Email | `VARCHAR2(n CHAR)` hoặc thiết kế theo chuẩn/giới hạn hệ thống liên quan | Phải phân biệt ký tự Unicode và giới hạn byte của các giao thức |
| Mô tả ngắn | `VARCHAR2(500 CHAR)` nếu phù hợp trần byte SQL | Có giới hạn nhập liệu theo code point |
| Nội dung dài/bài viết | `CLOB` | Không bị giới hạn nhỏ như `VARCHAR2` |
| Chuỗi quốc tế dùng national charset theo yêu cầu đặc thù | `NVARCHAR2(n)` | Có ý nghĩa khi hệ thống thực sự cần national character set |

Đây là **gợi ý mô hình dữ liệu**, không phải kích thước chuẩn bắt buộc. Quyết định thực tế còn phụ thuộc độ dài dữ liệu, dữ liệu có thể chứa emoji không, collations, chỉ mục, hệ thống nhận/gửi, UX validation, giao thức tích hợp và yêu cầu giữ dữ liệu lịch sử.

### 9.1. BYTE không đồng nghĩa ASCII-only

Một cột `VARCHAR2(20 BYTE)` có thể lưu một vài ký tự Unicode đa byte nếu tổng byte không vượt 20. Nếu nghiệp vụ nói mã định danh chỉ gồm `A-Z`, `0-9`, `_` hoặc `-`, cần **kiểm tra quy tắc nội dung riêng** bằng validation hoặc constraint thích hợp:

~~~sql
CREATE TABLE product_code_lab (
    code VARCHAR2(20 BYTE)
        CONSTRAINT ck_product_code_ascii
        CHECK (REGEXP_LIKE(code, '^[A-Z0-9_-]+$'))
);
~~~

Ràng buộc ví dụ này giới hạn ký tự theo biểu thức regex; nó không tồn tại tự động chỉ nhờ `BYTE` semantics. Nếu cột cần khóa chính hoặc `NOT NULL`, cần khai báo thêm theo nghiệp vụ.

### 9.2. Chọn kích thước theo dữ liệu thật

Trước khi thay đổi schema production, hãy thu thập:

1. Độ dài theo ký tự và byte của **dữ liệu đang có**.
2. Mẫu dữ liệu phải hỗ trợ: tên tiếng Việt NFC, dấu tách rời, tên quốc tế, emoji hay ký tự ngoài BMP.
3. Giới hạn do giao thức/API, UI, dữ liệu đầu vào và storage policy áp đặt.
4. Index, constraint, unique key hoặc giao diện bên ngoài phụ thuộc định nghĩa cột.
5. DDL hiện tại và `CHAR_USED`/`DATA_LENGTH` thay vì suy từ màn hình quản lý.

Ví dụ truy vấn thống kê:

~~~sql
-- Thay CUSTOMERS/FULL_NAME bang bang/cot thuc te.
SELECT
    MAX(LENGTH(full_name))  AS max_char_count,
    MAX(LENGTHB(full_name)) AS max_byte_count,
    COUNT(*)                AS row_count
FROM customers;
~~~

Nếu có giá trị `NULL`, `LENGTH` và `LENGTHB` của NULL cũng là NULL; `MAX` bỏ qua NULL. Hãy dùng thêm thống kê tỷ lệ dữ liệu gần giới hạn, không chỉ nhìn giá trị lớn nhất, khi lựa chọn chính sách tăng độ dài.

## 10. Liên hệ Java, JDBC và Unicode normalization

### 10.1. Java `String.length()` không luôn bằng số code point

Java lưu chuỗi theo **UTF-16 code units**, nên:

~~~java
String text = "Hà Nội";

int utf16Units = text.length();
int codePoints = text.codePointCount(0, text.length());
int utf8Bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;

System.out.println("UTF-16 units: " + utf16Units);
System.out.println("Code points: " + codePoints);
System.out.println("UTF-8 bytes: " + utf8Bytes);
~~~

Với chuỗi NFC `Hà Nội`, cả `utf16Units` và `codePoints` đều là 6, còn `utf8Bytes` là 9. Với emoji ngoài BMP, `String.length()` có thể là 2 cho một code point, vì UTF-16 dùng surrogate pair. Trong ứng dụng kiểm tra giới hạn ký tự cho Oracle `VARCHAR2(n CHAR)`, dùng `codePointCount` có thể phù hợp hơn `String.length()` ở trường hợp này.

Tuy nhiên số **grapheme clusters** của giao diện vẫn có thể khác số Unicode code points, nhất là khi dùng dấu kết hợp hoặc emoji nhiều thành phần. Nếu giới hạn được diễn đạt là “số ký tự người dùng nhìn thấy”, hãy chọn thư viện Unicode/grapheme segmentation phù hợp.

### 10.2. Chuẩn hóa Unicode trước khi lưu khi cần

Java có `java.text.Normalizer`:

~~~java
import java.text.Normalizer;

String raw = requestName;
String normalized = Normalizer.normalize(raw, Normalizer.Form.NFC);

int codePoints = normalized.codePointCount(0, normalized.length());
byte[] encodedUtf8 = normalized.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

if (codePoints > 120) {
    throw new IllegalArgumentException("Tên quá 120 code point");
}

// Sau validation, bind gia tri qua PreparedStatement/JPA.
~~~

Việc chuẩn hóa nên là **quyết định thiết kế rõ ràng**, áp dụng đồng bộ ở nhập liệu, tìm kiếm, so sánh và import. Dữ liệu lịch sử có thể chứa chuỗi đã tách dấu; thay đổi normalization có thể tác động unique constraints, tìm kiếm và dữ liệu tích hợp.

### 10.3. Bind parameter thay vì nối chuỗi SQL

JDBC:

~~~java
String sql = """
    INSERT INTO customer_profile(customer_id, full_name)
    VALUES (?, ?)
    """;

try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setString(2, normalized);
    ps.executeUpdate();
}
~~~

`PreparedStatement` tách dữ liệu ra khỏi cú pháp SQL, tránh SQL injection và giúp driver thực hiện chuyển đổi kiểu/charset phù hợp. Nó **không bỏ qua giới hạn BYTE/CHAR**: database vẫn có thể báo `ORA-12899` nếu giá trị vượt định nghĩa cột.

Oracle JDBC Thin xử lý chuyển mã qua driver, thường không phụ thuộc `NLS_LANG` giống một số client OCI/native; cần kiểm tra phiên bản driver và cấu hình ứng dụng. Khi SQL*Plus hiển thị sai dấu nhưng JDBC hiển thị đúng, hãy kiểm tra đường đi ký tự của từng client **riêng biệt**.

## 11. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Kiểm tra/cách xử lý |
| --- | --- | --- |
| `ORA-12899: value too large for column` | Giá trị vượt giới hạn BYTE hoặc CHAR của cột, hoặc byte cap của datatype | `USER_TAB_COLUMNS.CHAR_USED`, `DATA_LENGTH`; `LENGTH`/`LENGTHB` của dữ liệu; thiết kế lại giới hạn nếu cần |
| Văn bản tiếng Việt bị thay bằng `?` hoặc ký tự lạ | Sai encoding khi nhập/chuyển đổi, client charset hoặc import/export | Xem `NLS_CHARACTERSET`, đường đi terminal/file/driver, dữ liệu gốc và round-trip |
| Lưu `Ha Noi` được nhưng `Hà Nội` lỗi | Cột quá chặt theo byte với charset đa byte | So `LENGTHB` và giới hạn cột; cân nhắc explicit `CHAR` |
| `VARCHAR2(2000 CHAR)` vẫn không nhận 2.000 ký tự Unicode đa byte | Chạm trần tổng số byte của `VARCHAR2` (ví dụ 4.000 trong STANDARD) | Xem `MAX_STRING_SIZE`, số byte thực tế; cân nhắc `CLOB` |
| Cột khai báo `VARCHAR2(30)` trên môi trường A khác B | Session `NLS_LENGTH_SEMANTICS` khác khi DDL chạy | So `NLS_SESSION_PARAMETERS` và `USER_TAB_COLUMNS`; ghi explicit `BYTE`/`CHAR` |
| Dữ liệu hiển thị giống nhau nhưng độ dài khác | NFC/NFD hoặc ký tự kết hợp | Xem code point/byte bằng `LENGTH`/`LENGTHB`/`DUMP`; thống nhất normalization |
| Cắt chuỗi ở byte khiến chữ bị lỗi | Dùng byte count hoặc thuật toán byte slicing cho text Unicode | Dùng API theo ký tự/code point hoặc grapheme cho UI |
| Dữ liệu vào CLOB nhưng đo `LENGTHB` lỗi | `LENGTHB` có hạn chế với multibyte CLOB | Dùng API/`DBMS_LOB` thích hợp theo mục đích đo |
| Mở rộng cột rồi gặp lỗi index/key size | Giới hạn index key, expression hoặc thành phần phụ thuộc | Đánh giá chỉ mục/ràng buộc và kế hoạch migration, không thay đổi toàn cục mù quáng |
| SQL*Plus và Java trả kết quả hiển thị khác | Client encode/decode khác | Thử dữ liệu Unicode mẫu, xem charset của DB, kiểm tra file/console và JDBC |

### 11.1. Quy trình khoanh vùng khi gặp `ORA-12899`

Giả sử nhập tên `Hà Nội` vào cột `CUSTOMERS.FULL_NAME` bị lỗi.

**Bước 1 — Xem metadata thực tế của cột:**

~~~sql
SELECT
    column_name, data_type, data_length, char_length, char_used
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
  AND column_name = 'FULL_NAME';
~~~

**Bước 2 — Kiểm tra database character set và session:**

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter = 'NLS_CHARACTERSET';

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_LENGTH_SEMANTICS';
~~~

**Bước 3 — Đo input trong đúng đường đi nhận dữ liệu:**

~~~sql
SELECT LENGTH('Hà Nội') AS n_chars,
       LENGTHB('Hà Nội') AS n_bytes
FROM dual;
~~~

Nếu giá trị trong ứng dụng được truyền qua bind parameter, hãy lấy log chẩn đoán có kiểm soát hoặc test input tương đương; không ghi dữ liệu cá nhân nhạy cảm vào log công khai. Đảm bảo chuỗi đã tới database đúng mã hóa trước khi so kích thước.

**Bước 4 — Quyết định sửa đúng chỗ:**

- Nếu nghiệp vụ giới hạn theo ký tự và dữ liệu lớn hơn byte capacity hiện tại, cân nhắc tăng kích thước hoặc chuyển sang explicit `CHAR` sau khi kiểm tra tác động.
- Nếu input thực sự dài quá giới hạn nghiệp vụ, giữ constraint và trả thông báo kiểm tra dữ liệu hợp lý.
- Nếu dữ liệu bị sai dấu do chuyển mã, sửa pipeline encoding trước; tăng cột không chữa được dữ liệu bị biến đổi.
- Nếu vượt trần `VARCHAR2`, xem xét `CLOB`/thiết kế lưu trữ khác.

Đổi cột hiện hữu có thể cần thao tác `ALTER TABLE ... MODIFY` và có ràng buộc đối với dữ liệu, index, view, API, thời gian khóa hoặc downtime. Không chạy thay đổi đó trên production chỉ dựa vào một ví dụ lỗi.

### 11.2. Khi dữ liệu tiếng Việt hiển thị thành ký tự lạ

Một chuỗi bị biến thành `HÃ  Ná»™i` hoặc dấu hỏi có thể bắt nguồn từ UTF-8 bị giải mã sai hoặc từ ký tự không biểu diễn được trên đường chuyển mã. Tùy vị trí lỗi:

1. Nếu chuỗi **đã bị lưu sai**, thay đổi NLS của client sau đó không nhất thiết tự sửa dữ liệu cũ.
2. Nếu dữ liệu **lưu đúng nhưng chỉ hiển thị sai**, ưu tiên kiểm tra font, terminal encoding, code page, `NLS_LANG` của client native, format export và đường đi rendering.
3. Nếu file CSV import/export bị lỗi, kiểm tra encoding của **file nguồn và file đích**, thiết lập của tool và mapping charset, không chỉ kiểu cột.
4. Nếu JDBC và SQL*Plus khác kết quả, kiểm tra từng client thay vì mặc định cả hai dùng cùng môi trường.

Khi chẩn đoán, một giá trị kiểm thử có chứa `à`, `ộ`, `đ` và ký tự ngoài ASCII có thể giúp xác định lỗi; đối chiếu `LENGTHB`, `DUMP` và byte gốc của file/input.

## 12. Ghi nhớ các quy tắc thiết kế

**Quy tắc 1 — Chọn rõ đơn vị:** `VARCHAR2(100 BYTE)` là tối đa 100 byte; `VARCHAR2(100 CHAR)` là tối đa 100 code point theo Oracle, vẫn chịu giới hạn byte tuyệt đối.

**Quy tắc 2 — Ưu tiên khai báo explicit:** DDL nên ghi `BYTE`/`CHAR` tại mỗi cột mà semantics quan trọng. Điều này tránh phụ thuộc vào `NLS_LENGTH_SEMANTICS` của session migration.

**Quy tắc 3 — Tiếng Việt cần Unicode nhất quán:** `AL32UTF8` phù hợp với đa ngôn ngữ; client/import/export cũng phải giữ nguyên Unicode. `CHAR` semantics không tự bảo vệ trước sai encoding.

**Quy tắc 4 — Dùng hàm đúng mục đích:** `LENGTH` đo ký tự, `LENGTHB` đo byte; UI đo grapheme có thể cần thuật toán Unicode riêng.

**Quy tắc 5 — Kiểm tra metadata:** `USER_TAB_COLUMNS.CHAR_USED` cho biết thực tế cột sử dụng `B` hay `C`. Không suy ra từ tên kiểu hoặc cách UI hiển thị.

**Quy tắc 6 — Không dùng CHAR thay CLOB:** Văn bản rất dài cần chiến lược CLOB; thay `VARCHAR2(4000 BYTE)` thành `VARCHAR2(4000 CHAR)` không xóa trần byte của SQL.

**Quy tắc 7 — Thử dữ liệu có dấu thật:** Test tên ASCII thôi không phát hiện lỗi byte semantics. Dùng ít nhất một chuỗi như `Hà Nội`, một ký tự ba byte và một chuỗi kết hợp Unicode trong test dữ liệu.

## 13. Câu hỏi ôn tập

1. Trong database `AL32UTF8`, vì sao `'Ha Noi'` lưu được vào `VARCHAR2(6 BYTE)` nhưng `'Hà Nội'` có thể không lưu được?
2. `VARCHAR2(50 CHAR)` có luôn bảo đảm lưu được mọi chuỗi gồm đúng 50 code point không, nếu `MAX_STRING_SIZE=STANDARD`? Khi nào giới hạn byte còn quan trọng?
3. `VARCHAR2(20)` mặc định theo BYTE hay CHAR? Có thể tìm giá trị nào để biết cột đã được tạo thực sự dùng semantics nào?
4. `NLS_LENGTH_SEMANTICS` thay đổi có tự chuyển các cột đã tồn tại sang semantics mới không?
5. Nếu `'ộ'` là một Unicode code point, vì sao `LENGTH('ộ')` và `LENGTHB('ộ')` có thể trả về 1 và 3?
6. Tại sao ký tự người dùng nhìn thấy không luôn bằng một code point? Hãy nêu ví dụ Unicode normalization.
7. Khi dùng `VARCHAR2` trong database `AL32UTF8`, có cần chuyển sang `NVARCHAR2` chỉ để lưu tiếng Việt không?
8. `CHAR(10 CHAR)` và `VARCHAR2(10 CHAR)` khác nhau như thế nào khi lưu `'AB'`?
9. Tại sao dùng `LENGTHB` trực tiếp cho multibyte CLOB có thể không phù hợp? Nên chọn cách tiếp cận nào?
10. Tại sao “cột BYTE cho mã ASCII” vẫn cần một validation để thực sự cấm ký tự ngoài ASCII?
11. Java `String.length()` có luôn bằng số code point Oracle đếm cho `AL32UTF8` không?
12. Nếu tiếng Việt bị biến thành ký tự `?` trong file import, tăng `VARCHAR2(20 BYTE)` thành `VARCHAR2(100 CHAR)` có bảo đảm khắc phục không?

**Đáp án định hướng:** (1) 6 byte so với 9 byte với dữ liệu NFC; (2) không, vẫn có byte cap; (3) session `NLS_LENGTH_SEMANTICS` lúc tạo, xác nhận bằng `CHAR_USED` metadata; (4) không; (5) UTF-8 mã hóa `ộ` bằng 3 byte; (6) `é` dựng sẵn so với `e` cộng dấu kết hợp; (7) không nếu database charset phù hợp; (8) `CHAR` đệm dấu cách, `VARCHAR2` không; (9) dùng API/`DBMS_LOB.GETLENGTH` khi đo theo ký tự và công cụ phù hợp khi cần byte; (10) BYTE chỉ hạn chế dung lượng, không giới hạn tập ký tự; (11) không, Java đếm UTF-16 code units; (12) không, cần sửa đường chuyển mã và kiểm tra dữ liệu nguồn.

## Tài liệu tham khảo Oracle

- [Oracle SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Data-Types.html): cú pháp `VARCHAR2(size BYTE|CHAR)`, giới hạn byte, `CHAR` và `NVARCHAR2`.
- [Oracle Database Globalization Support Guide — Choosing a Character Set](https://docs.oracle.com/en/database/oracle/oracle-database/26/nlspg/choosing-character-set.html): bộ mã `AL32UTF8`, character semantics và lựa chọn Unicode.
- [Oracle SQL Language Reference — LENGTH](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/LENGTH.html): `LENGTH`, `LENGTHB`, `LENGTHC`, `LENGTH2` và `LENGTH4`.
- [Oracle Database Reference — NLS_LENGTH_SEMANTICS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/NLS_LENGTH_SEMANTICS.html): mặc định session và ảnh hưởng tới các định nghĩa cột mới.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): tra cứu `USER_TAB_COLUMNS` và các tham số cấu hình có liên quan.
